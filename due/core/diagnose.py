"""Diagnosis: reason code -> root cause.

Two paths, and the distinction between them is the honest part of this module.

**Table path (documented codes).** `insufficient_funds` means insufficient funds.
Razorpay documents it, so mapping it is a LOOKUP, not a prediction. Accuracy here
is 100% by construction and reporting it as a model metric would be dishonest.

**Inference path (ambiguous codes).** `card_declined`, `payment_failed`, and
`payment_declined` mean the issuer refused without saying why — the cause was
never transmitted. It must be inferred from context: amount, issuer health,
attempt history, time of month, instrument. This is the only subset where
diagnosis is a genuine prediction, and it is the only subset the submission
reports accuracy on.

A heuristic inferencer ships alongside the LLM one deliberately. It runs with no
API key, and it is the baseline the LLM has to beat — without it, "the agent
diagnoses failures" is an unfalsifiable claim.

This module's table is derived from Razorpay's public error documentation and is
INDEPENDENT of the simulator's generative table. They agree on documented codes
because both derive from the same public docs; they must never be imported from
one another, or measured accuracy becomes circular.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from due.core.models import DeclineClass, Diagnosis, EventType, RiskEvent, RootCause

# ---------------------------------------------------------------------------
# Table — documented codes
# ---------------------------------------------------------------------------

# reason -> (root cause, decline class, evidence anchor)
# https://razorpay.com/docs/errors/payments/cards/
# https://razorpay.com/docs/errors/payments/upi/
DIAGNOSIS_TABLE: dict[str, tuple[RootCause, DeclineClass, str]] = {
    # technical — customer was willing and able
    "bank_technical_error": (RootCause.ISSUER_DOWN, DeclineClass.TECHNICAL, "rzp:cards#bank_technical_error"),
    "partner_bank_downtime": (RootCause.ISSUER_DOWN, DeclineClass.TECHNICAL, "rzp:upi#partner_bank_downtime"),
    "partner_bank_technical_issues": (RootCause.ISSUER_DOWN, DeclineClass.TECHNICAL, "rzp:upi#partner_bank_technical_issues"),
    "gateway_technical_error": (RootCause.GATEWAY_DOWN, DeclineClass.TECHNICAL, "rzp:cards#gateway_technical_error"),
    "credit_failed": (RootCause.GATEWAY_DOWN, DeclineClass.TECHNICAL, "rzp:upi#credit_failed"),
    "payment_timed_out": (RootCause.TIMEOUT, DeclineClass.TECHNICAL, "rzp:cards#payment_timed_out"),
    "payment_collect_request_expired": (RootCause.TIMEOUT, DeclineClass.TECHNICAL, "rzp:upi#collect_expired"),
    # transient business — depends heavily on timing
    "insufficient_funds": (RootCause.INSUFFICIENT_FUNDS, DeclineClass.BUSINESS, "rzp:cards#insufficient_funds"),
    "transaction_limit_exceeded": (RootCause.LIMIT_EXCEEDED, DeclineClass.BUSINESS, "rzp:cards#transaction_limit_exceeded"),
    # needs the customer to act
    "payment_cancelled": (RootCause.CUSTOMER_ABANDONED, DeclineClass.BUSINESS, "rzp:cards#payment_cancelled"),
    "customer_bank_account_mismatch": (RootCause.CUSTOMER_ABANDONED, DeclineClass.BUSINESS, "rzp:upi#account_mismatch"),
    "authentication_failed": (RootCause.AUTH_FAILED, DeclineClass.BUSINESS, "rzp:cards#authentication_failed"),
    "incorrect_cvv": (RootCause.AUTH_FAILED, DeclineClass.BUSINESS, "rzp:cards#incorrect_cvv"),
    # terminal for same-instrument retry
    "card_expired": (RootCause.INSTRUMENT_EXPIRED, DeclineClass.BUSINESS, "rzp:cards#card_expired"),
    "card_not_enrolled": (RootCause.INSTRUMENT_NOT_ENABLED, DeclineClass.BUSINESS, "rzp:cards#card_not_enrolled"),
    "card_disabled_for_online_payments": (RootCause.INSTRUMENT_NOT_ENABLED, DeclineClass.BUSINESS, "rzp:cards#card_disabled"),
    "debit_instrument_inactive": (RootCause.INSTRUMENT_NOT_ENABLED, DeclineClass.BUSINESS, "rzp:cards#debit_instrument_inactive"),
    "debit_instrument_blocked": (RootCause.INSTRUMENT_BLOCKED, DeclineClass.BUSINESS, "rzp:cards#debit_instrument_blocked"),
    "payment_risk_check_failed": (RootCause.RISK_BLOCKED, DeclineClass.BUSINESS, "rzp:cards#payment_risk_check_failed"),
    "invalid_vpa": (RootCause.INVALID_VPA, DeclineClass.BUSINESS, "rzp:upi#invalid_vpa"),
    "vpa_resolution_failed": (RootCause.INVALID_VPA, DeclineClass.BUSINESS, "rzp:upi#vpa_resolution_failed"),
}

# The issuer refused and did not say why. These require inference.
AMBIGUOUS_REASONS: frozenset[str] = frozenset(
    {"card_declined", "payment_failed", "payment_declined"}
)

# Candidate causes behind an ambiguous decline.
AMBIGUOUS_CANDIDATES: tuple[RootCause, ...] = (
    RootCause.INSUFFICIENT_FUNDS,
    RootCause.LIMIT_EXCEEDED,
    RootCause.RISK_BLOCKED,
    RootCause.INSTRUMENT_BLOCKED,
    RootCause.ISSUER_DOWN,
)


# ---------------------------------------------------------------------------
# Inference context
# ---------------------------------------------------------------------------


@dataclass
class BatchContext:
    """Observable signals derived from the merchant's own at-risk traffic.

    A naive "decline rate per issuer" is meaningless here: this batch is ALREADY
    filtered to at-risk events, so every issuer's decline rate is near 100% and
    nothing is ever elevated relative to anything.

    The signal that survives that filtering is **composition**. During an outage,
    an issuer's failures shift toward technical reason codes. Comparing an
    issuer's technical share on a given day against the batch-wide technical share
    detects outages using only data a merchant already has — no privileged feed.

    Amount thresholds are likewise taken from the batch's own distribution rather
    than hardcoded, so the same heuristics work for a merchant selling Rs 99
    subscriptions and one selling Rs 90,000 appliances.
    """

    technical_share_by_issuer_day: dict[tuple[str, object], float]
    batch_technical_share: float
    amount_p50: float
    amount_p90: float

    @classmethod
    def from_events(cls, events: list[RiskEvent]) -> BatchContext:
        totals: dict[tuple[str, object], int] = {}
        technical: dict[tuple[str, object], int] = {}
        batch_total = batch_tech = 0

        for e in events:
            if not e.error_reason:
                continue
            key = (e.issuer, e.occurred_at.date())
            totals[key] = totals.get(key, 0) + 1
            batch_total += 1
            mapped = DIAGNOSIS_TABLE.get(e.error_reason)
            if mapped and mapped[1] is DeclineClass.TECHNICAL:
                technical[key] = technical.get(key, 0) + 1
                batch_tech += 1

        shares = {
            k: technical.get(k, 0) / v
            for k, v in totals.items()
            if v >= 3  # a single failure is noise, not a signal
        }
        amounts = sorted(float(e.amount) for e in events)

        def pct(p: float) -> float:
            if not amounts:
                return 0.0
            return amounts[min(len(amounts) - 1, int(len(amounts) * p))]

        return cls(
            technical_share_by_issuer_day=shares,
            batch_technical_share=(batch_tech / batch_total) if batch_total else 0.0,
            amount_p50=pct(0.50),
            amount_p90=pct(0.90),
        )

    def technical_share(self, issuer: str, when) -> float | None:
        return self.technical_share_by_issuer_day.get((issuer, when.date()))

    def outage_suspected(self, issuer: str, when, factor: float = 2.0) -> bool:
        """This issuer's failures skew technical today, well above the batch norm."""
        share = self.technical_share(issuer, when)
        if share is None or not self.batch_technical_share:
            return False
        return share > self.batch_technical_share * factor


class Inferencer(Protocol):
    def infer(self, event: RiskEvent, ctx: BatchContext) -> tuple[RootCause, float, str]: ...


# ---------------------------------------------------------------------------
# Heuristic inferencer — the baseline
# ---------------------------------------------------------------------------


class HeuristicInferencer:
    """Rule-based inference over observable context. No API key required.

    This exists to be beaten. Reporting an LLM's accuracy without a baseline says
    nothing about whether the LLM contributed anything.
    """

    name = "heuristic"

    # Prior belief over causes before any signal is observed. These are a payments
    # engineer's judgement, NOT the simulator's generative weights — copying those
    # would make measured accuracy circular. Both reflect the same domain facts,
    # which is why the directions agree; the magnitudes are chosen independently.
    PRIOR: dict[RootCause, float] = {
        RootCause.INSUFFICIENT_FUNDS: 0.40,
        RootCause.LIMIT_EXCEEDED: 0.18,
        RootCause.RISK_BLOCKED: 0.16,
        RootCause.INSTRUMENT_BLOCKED: 0.13,
        RootCause.ISSUER_DOWN: 0.13,
    }

    def infer(self, event: RiskEvent, ctx: BatchContext) -> tuple[RootCause, float, str]:
        scores = dict(self.PRIOR)
        why: list[str] = []
        day = event.occurred_at.day

        # A failed early-exit chain was the previous shape of this function and it
        # scored BELOW the majority class: any single weak signal hijacked the
        # answer. Scoring every signal and taking the argmax lets weak evidence
        # nudge the belief without overturning the prior on its own.

        if ctx.outage_suspected(event.issuer, event.occurred_at):
            share = ctx.technical_share(event.issuer, event.occurred_at) or 0.0
            scores[RootCause.ISSUER_DOWN] *= 6.0
            why.append(
                f"{event.issuer} failures {share:.0%} technical today vs "
                f"{ctx.batch_technical_share:.0%} batch-wide"
            )

        if event.prior_attempts_30d >= 3:
            scores[RootCause.INSTRUMENT_BLOCKED] *= 3.5
            why.append(f"{event.prior_attempts_30d} prior attempts without success")

        # Instrument success history — the strongest available signal.
        if event.recent_success_count == 0:
            # Nothing has cleared on this instrument. A moving balance would have
            # let something through; a standing block would not.
            scores[RootCause.INSTRUMENT_BLOCKED] *= 5.0
            why.append("no successful charge on this instrument recently")
        else:
            scores[RootCause.INSTRUMENT_BLOCKED] *= 0.3
            top = event.max_recent_success_amount
            if top is not None and top > event.amount:
                # A larger charge already cleared, so a per-transaction ceiling
                # cannot be what is biting at this amount.
                scores[RootCause.LIMIT_EXCEEDED] *= 0.1
                why.append(
                    f"a larger charge (Rs {top:,.0f}) cleared recently — rules out a cap"
                )
            elif top is not None:
                scores[RootCause.LIMIT_EXCEEDED] *= 2.2
                why.append(
                    f"nothing above Rs {top:,.0f} has cleared — consistent with a cap"
                )

        if float(event.amount) >= ctx.amount_p90:
            scores[RootCause.LIMIT_EXCEEDED] *= 2.5
            scores[RootCause.RISK_BLOCKED] *= 1.8
            why.append(
                f"Rs {event.amount} at/above the merchant's p90 (Rs {ctx.amount_p90:,.0f})"
            )

        if day >= 25 or day <= 5:
            scores[RootCause.INSUFFICIENT_FUNDS] *= 1.7
            why.append(f"day {day} is in the late-month / pre-salary trough")

        if event.occurred_at.hour < 6:
            scores[RootCause.RISK_BLOCKED] *= 2.0
            why.append(f"{event.occurred_at.hour:02d}:00 is an odd hour for this customer")

        if not event.customer_success_days and float(event.amount) >= ctx.amount_p90:
            scores[RootCause.RISK_BLOCKED] *= 1.5
            why.append("large ticket on a customer with no payment history")

        total = sum(scores.values())
        cause = max(scores, key=lambda k: scores[k])
        confidence = scores[cause] / total if total else 0.0
        rationale = "; ".join(why) if why else "no distinguishing signal; prior only"
        return cause, confidence, rationale


class MajorityClassInferencer:
    """Always predicts the most common cause. The floor any diagnoser must clear.

    Without this reported alongside, an accuracy figure is unreadable — a model
    scoring 40% on a task whose majority class is 39% has contributed nothing.
    """

    name = "majority_class"

    def infer(self, event: RiskEvent, ctx: BatchContext) -> tuple[RootCause, float, str]:
        return RootCause.INSUFFICIENT_FUNDS, 0.40, "majority-class baseline"


# ---------------------------------------------------------------------------
# Claude inferencer
# ---------------------------------------------------------------------------

_SYSTEM = """You are a payments failure analyst for an Indian merchant using Razorpay.

An issuer declined a payment and returned an ambiguous code (card_declined, \
payment_failed, or payment_declined). These codes carry no reason — the issuer \
refused without transmitting why. Infer the most likely underlying cause from context.

Candidate causes:
- insufficient_funds  : balance too low at the moment of the attempt
- limit_exceeded      : per-transaction or daily ceiling hit
- risk_blocked        : issuer's fraud system flagged the transaction
- instrument_blocked  : card or account blocked by bank or customer
- issuer_down         : bank-side technical failure surfaced as a generic decline

Signals that matter:
- Indian salary cycles credit on the 1st-5th; the 25th-31st is the balance trough.
- A high prior attempt count with no success suggests a standing block, not a moving balance.
- Large amounts hit ceilings before they hit an empty balance.
- If this issuer is declining well above the batch rate, suspect issuer_down.
- A first-time large amount on an otherwise quiet customer can trip fraud rules.

Be calibrated. Insufficient funds is the single most common cause, so do not \
report high confidence for an exotic cause without a specific signal supporting it."""


class ClaudeInferencer:
    """LLM inference over the ambiguous subset.

    Scoped narrowly on purpose: the LLM is used only where a table cannot work.
    Routing documented codes through a model would add cost, latency, and a
    failure mode, in exchange for replacing a correct lookup with a guess.
    """

    name = "claude"

    def __init__(self, model: str = "claude-opus-5") -> None:
        import anthropic
        from pydantic import BaseModel, Field

        class Inference(BaseModel):
            root_cause: str = Field(description="One of: " + ", ".join(c.value for c in AMBIGUOUS_CANDIDATES))
            confidence: float = Field(ge=0.0, le=1.0)
            reasoning: str = Field(description="One sentence citing the specific signals used.")

        self._schema = Inference
        self._client = anthropic.Anthropic()
        self._model = model

    def infer(self, event: RiskEvent, ctx: BatchContext) -> tuple[RootCause, float, str]:
        rate = ctx.technical_share(event.issuer, event.occurred_at) or 0.0
        prompt = f"""Payment failure to diagnose:

reason code        : {event.error_reason}
instrument         : {event.instrument.value}
issuer             : {event.issuer}
amount             : Rs {event.amount}
occurred           : {event.occurred_at:%Y-%m-%d %H:%M} (day {event.occurred_at.day} of month)
attempts, prior 24h: {event.prior_attempts_24h}
attempts, prior 30d: {event.prior_attempts_30d}
customer LTV       : Rs {event.customer_ltv or 'unknown'}
customer pays on   : days {event.customer_success_days or 'no history'}
issuer decline rate: {rate:.1%} (batch average {ctx.batch_technical_share:.1%})

What is the most likely underlying cause?"""

        response = self._client.messages.parse(
            model=self._model,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=self._schema,
        )
        out = response.parsed_output
        try:
            cause = RootCause(out.root_cause)
        except ValueError:
            # A model returning something off-menu must not become a silent
            # mis-diagnosis. Fall back to the base rate and say so.
            return (
                RootCause.INSUFFICIENT_FUNDS,
                0.30,
                f"model returned unrecognised cause '{out.root_cause}'; using base rate",
            )
        return cause, float(out.confidence), out.reasoning


# ---------------------------------------------------------------------------
# Diagnoser
# ---------------------------------------------------------------------------


class Diagnoser:
    def __init__(self, inferencer: Inferencer | None = None) -> None:
        self.inferencer = inferencer or HeuristicInferencer()

    def diagnose(self, event: RiskEvent, ctx: BatchContext) -> Diagnosis:
        # Non-failure leak points carry no error code — their cause is the event
        # type itself. An authorised-but-uncaptured payment did not fail.
        if event.event_type in (EventType.UNCAPTURED_AUTH, EventType.LATE_AUTHORIZATION):
            return Diagnosis(
                root_cause=RootCause.UNCAPTURED,
                decline_class=DeclineClass.UNKNOWN,
                confidence=1.0,
                evidence_ref="rzp:payments/capture-settings",
                reasoned_by="table",
            )
        if event.event_type is EventType.ABANDONED_CHECKOUT:
            return Diagnosis(
                root_cause=RootCause.CUSTOMER_ABANDONED,
                decline_class=DeclineClass.BUSINESS,
                confidence=1.0,
                evidence_ref="due:abandoned_checkout",
                reasoned_by="table",
            )

        reason = event.error_reason
        if reason and reason in DIAGNOSIS_TABLE:
            cause, cls, ref = DIAGNOSIS_TABLE[reason]
            return Diagnosis(
                root_cause=cause,
                decline_class=cls,
                confidence=1.0,
                evidence_ref=ref,
                reasoned_by="table",
            )

        if reason in AMBIGUOUS_REASONS:
            cause, confidence, why = self.inferencer.infer(event, ctx)
            return Diagnosis(
                root_cause=cause,
                decline_class=DeclineClass.UNKNOWN,
                confidence=confidence,
                evidence_ref=f"inferred:{self.inferencer.name}:{why}",
                reasoned_by=self.inferencer.name,
            )

        return Diagnosis(
            root_cause=RootCause.AMBIGUOUS_DECLINE,
            decline_class=DeclineClass.UNKNOWN,
            confidence=0.0,
            evidence_ref=f"unmapped reason code '{reason}' — escalate to a human",
            reasoned_by="table",
        )


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


@dataclass
class DiagnosisReport:
    total: int
    table_resolved: int
    inferred: int
    inferred_correct: int
    per_cause: dict[str, tuple[int, int]]  # cause -> (correct, total)

    @property
    def inference_accuracy(self) -> float:
        return self.inferred_correct / self.inferred if self.inferred else 0.0

    def __str__(self) -> str:
        lines = [
            f"events                 : {self.total}",
            f"resolved by table      : {self.table_resolved} "
            f"({self.table_resolved / self.total:.1%}) — lookup, not prediction",
            f"required inference     : {self.inferred} ({self.inferred / self.total:.1%})",
            f"inference accuracy     : {self.inference_accuracy:.1%} "
            f"({self.inferred_correct}/{self.inferred})",
            "",
            "per hidden cause (correct/total):",
        ]
        for cause, (ok, tot) in sorted(self.per_cause.items(), key=lambda kv: -kv[1][1]):
            lines.append(f"  {cause:22s} {ok:3d}/{tot:3d}  {ok / tot:6.1%}")
        return "\n".join(lines)


def evaluate(events: list[RiskEvent], diagnoser: Diagnoser) -> DiagnosisReport:
    """Measure diagnosis quality, reporting the inference subset separately.

    Accuracy over all events would be a vanity number dominated by table lookups.
    """
    ctx = BatchContext.from_events(events)
    table_resolved = inferred = correct = 0
    per_cause: dict[str, list[int]] = {}

    for event in events:
        d = diagnoser.diagnose(event, ctx)
        is_inference = event.error_reason in AMBIGUOUS_REASONS
        if not is_inference:
            table_resolved += 1
            continue

        inferred += 1
        truth = event.truth_root_cause
        hit = int(d.root_cause == truth)
        correct += hit
        key = truth.value if truth else "unknown"
        bucket = per_cause.setdefault(key, [0, 0])
        bucket[0] += hit
        bucket[1] += 1

    return DiagnosisReport(
        total=len(events),
        table_resolved=table_resolved,
        inferred=inferred,
        inferred_correct=correct,
        per_cause={k: (v[0], v[1]) for k, v in per_cause.items()},
    )


def default_diagnoser() -> Diagnoser:
    """Heuristic by default. This is an evidence-based choice, not a fallback.

    MEASURED, 7 seeds x 1000 events (see `due.sim.ceiling`):

        majority-class floor    43.1%
        heuristic               46.6%
        Bayes-optimal ceiling   48.7%

    The heuristic already captures 62% of the total available headroom. What
    remains for any smarter model is ~2.1 points, on the 7% of events that need
    inference at all — roughly 0.15% of batch-level diagnosis accuracy.

    An LLM call per event cannot justify itself against that. `ClaudeInferencer`
    is kept because the measurement is reproducible and the decision should be
    revisitable, but it is not the default, and the submission does not claim an
    LLM classification win. The model's honest jobs in this system are unmapped
    reason codes and writing the human-readable explanation on the exception
    queue — not classifying where a table and five rules already reach the ceiling.
    """
    return Diagnoser(HeuristicInferencer())
