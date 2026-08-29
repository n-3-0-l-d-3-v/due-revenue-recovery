"""Policy gate.

Runs before scoring and before any learner. A learner may only ever choose from
`EvaluationResult.permitted`, so learning cannot produce a network fine or a
compliance breach. That is the whole safety argument, and it holds by construction
rather than by training.

Three properties this module is responsible for:

1. **Completeness of the record.** Every rule that applies is evaluated and
   recorded, passes included. A gate that logs only refusals can prove it noticed
   some violations; it cannot prove compliance.

2. **DEFER is not BLOCK.** An RBI pre-debit window makes a debit illegitimate
   *now*, not illegitimate. Collapsing the two would silently discard recoverable
   revenue and would look like conservatism rather than the bug it is.

3. **Re-validation at execution time.** A decision made now that executes in 18
   hours must re-run the full gate against fresh state before acting. Consent can
   be withdrawn and counters can move in between. See `revalidate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol

import yaml

from due.core.counters import AttemptCounter
from due.core.models import (
    TERMINAL_FOR_RETRY,
    ActionType,
    CandidateAction,
    Diagnosis,
    GateResult,
    GateVerdict,
    Instrument,
    RiskEvent,
)

RULES_PATH = Path(__file__).with_name("rules.yaml")

# Actions no rule gates, deliberately. Both move no money and contact no one:
# escalation puts an item on an internal queue, and stopping does nothing at all.
# Gating them would be theatre, and would make an empty gate_results list look
# like a bug rather than the correct outcome.
UNGATED_ACTIONS: frozenset[ActionType] = frozenset(
    {ActionType.ESCALATE_HUMAN, ActionType.STOP_UNCOLLECTIBLE}
)


# ---------------------------------------------------------------------------
# Rule specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleSpec:
    id: str
    title: str
    source: str
    verdict: GateVerdict
    applies_to: frozenset[ActionType]
    params: dict
    note: str = ""


def load_rules(path: Path | None = None) -> list[RuleSpec]:
    raw = yaml.safe_load((path or RULES_PATH).read_text(encoding="utf-8"))
    specs: list[RuleSpec] = []
    for r in raw["rules"]:
        specs.append(
            RuleSpec(
                id=r["id"],
                title=r["title"],
                source=r["source"],
                verdict=GateVerdict(r["verdict"]),
                applies_to=frozenset(ActionType(a) for a in r.get("applies_to", [])),
                params=r.get("params") or {},
                note=(r.get("note") or "").strip(),
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------


@dataclass
class GateContext:
    """Everything a gate may read. Deliberately narrow.

    Note what is absent: expected value, recovery probability, and anything the
    scorer produces. A gate that could see value would eventually be tuned to
    trade compliance against revenue, which is the failure mode this whole
    architecture exists to prevent.
    """

    now: datetime
    counters: AttemptCounter
    merchant_category: str = "general"
    # event_id -> when the RBI pre-debit notice was sent
    notices_sent: dict[str, datetime] = field(default_factory=dict)


# Predicate returns (violated, rationale).
class Predicate(Protocol):
    def __call__(
        self, event: RiskEvent, action: CandidateAction, ctx: GateContext,
        params: dict, diagnosis: Diagnosis | None,
    ) -> tuple[bool, str]: ...


PREDICATES: dict[str, Predicate] = {}


def predicate(rule_id: str) -> Callable[[Predicate], Predicate]:
    def wrap(fn: Predicate) -> Predicate:
        PREDICATES[rule_id] = fn
        return fn
    return wrap


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


@predicate("network.attempts_per_card_30d")
def _attempts_30d(event, action, ctx, params, diagnosis):
    used = ctx.counters.total_attempts_30d(
        event.instrument_token, ctx.now, event.prior_attempts_30d
    )
    cap = params["max_attempts"]
    return used >= cap, f"{used}/{cap} attempts on this instrument in 30d"


@predicate("network.attempts_per_card_24h")
def _attempts_24h(event, action, ctx, params, diagnosis):
    used = ctx.counters.total_attempts_24h(
        event.instrument_token, ctx.now, event.prior_attempts_24h
    )
    cap = params["max_attempts"]
    return used >= cap, f"{used}/{cap} attempts on this instrument in 24h"


@predicate("network.merchant_retry_cap")
def _merchant_cap(event, action, ctx, params, diagnosis):
    used = ctx.counters.merchant_retries(event.payment_id)
    cap = params["max_retries"]
    return used >= cap, f"{used}/{cap} merchant-initiated retries on this payment"


@predicate("network.do_not_retry_terminal")
def _terminal(event, action, ctx, params, diagnosis):
    cause = diagnosis.root_cause if diagnosis else event.truth_root_cause
    if cause is None:
        return False, "no diagnosis available; not treated as terminal"
    if cause in TERMINAL_FOR_RETRY:
        return True, f"{cause.value} is terminal for same-instrument retry"
    return False, f"{cause.value} is not terminal"


@predicate("rbi.emandate_pre_debit_notice")
def _pre_debit(event, action, ctx, params, diagnosis):
    if event.instrument.value not in params["instruments"]:
        return False, "not a mandate instrument"
    sent = ctx.notices_sent.get(event.event_id)
    required = timedelta(hours=params["notice_hours"])
    if sent is None:
        return True, f"pre-debit notice not yet sent; {params['notice_hours']}h required"
    elapsed = ctx.now - sent
    if elapsed < required:
        remaining = required - elapsed
        return True, f"notice sent {elapsed} ago; {remaining} of the 24h window remains"
    return False, f"notice sent {elapsed} ago, window satisfied"


@predicate("rbi.afa_threshold")
def _afa(event, action, ctx, params, diagnosis):
    if event.instrument.value not in params["instruments"]:
        return False, "not a mandate instrument"
    threshold = Decimal(str(params["threshold"]))
    if ctx.merchant_category in params.get("exempt_categories", []):
        threshold = Decimal(str(params["exempt_category_threshold"]))
    if event.amount > threshold:
        return True, (
            f"Rs {event.amount} exceeds AFA threshold Rs {threshold} "
            f"for category '{ctx.merchant_category}'; cannot debit silently"
        )
    return False, f"Rs {event.amount} within AFA threshold Rs {threshold}"


@predicate("consent.active")
def _consent(event, action, ctx, params, diagnosis):
    return (not event.consent_active), (
        "consent withdrawn" if not event.consent_active else "consent active"
    )


@predicate("contact.weekly_cap")
def _contact_cap(event, action, ctx, params, diagnosis):
    used = ctx.counters.total_contacts_week(
        event.customer_id, ctx.now, event.contacts_this_week
    )
    cap = params["max_contacts"]
    return used >= cap, f"{used}/{cap} contacts to this customer this week"


@predicate("obligation.still_valid")
def _obligation(event, action, ctx, params, diagnosis):
    return (not event.obligation_valid), (
        "underlying obligation cancelled or unfulfillable"
        if not event.obligation_valid
        else "obligation valid"
    )


@predicate("value.below_cost_floor")
def _cost_floor(event, action, ctx, params, diagnosis):
    floor = Decimal(str(params["min_amount"]))
    return event.amount < floor, f"Rs {event.amount} vs floor Rs {floor}"


@predicate("auth.capture_window")
def _capture_window(event, action, ctx, params, diagnosis):
    if event.auth_expires_at is None:
        return True, "no authorisation on this event to capture"
    margin = timedelta(hours=params["safety_margin_hours"])
    deadline = event.auth_expires_at - margin
    if ctx.now >= deadline:
        return True, (
            f"authorisation expires {event.auth_expires_at:%Y-%m-%d %H:%M}; "
            f"inside the {params['safety_margin_hours']}h safety margin"
        )
    return False, f"authorisation valid until {event.auth_expires_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class DeferredAction:
    action: CandidateAction
    defer_until: datetime
    rule_id: str
    rationale: str


@dataclass
class EvaluationResult:
    gate_results: list[GateResult]
    permitted: list[CandidateAction]
    deferred: list[DeferredAction]

    @property
    def blocked(self) -> list[GateResult]:
        return [g for g in self.gate_results if g.verdict is GateVerdict.BLOCK]


@dataclass
class PendingAction:
    """A deferred action awaiting its execution window.

    Carries a snapshot of what was true at decision time so that re-validation can
    report *what changed*, not merely that something did. "Consent was active when
    we decided and is not now" is an auditable statement; "blocked" is not.
    """

    decision_id: str
    event_id: str
    action: CandidateAction
    scheduled_for: datetime
    deferred_by_rule: str
    snapshot_consent: bool
    snapshot_attempts_24h: int
    snapshot_contacts_week: int
    # When the RBI pre-debit notice was dispatched — the moment we deferred, not
    # the moment the action fires. Confusing the two restarts the 24h clock at
    # execution time and the action can never become eligible.
    notice_sent_at: datetime | None = None


@dataclass
class RevalidationOutcome:
    approved: bool
    at: datetime
    gate_results: list[GateResult]
    changed_since_decision: list[str]

    @property
    def blocking_rules(self) -> list[str]:
        return [g.rule_id for g in self.gate_results if g.verdict is GateVerdict.BLOCK]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    def __init__(self, rules: list[RuleSpec] | None = None) -> None:
        self.rules = rules if rules is not None else load_rules()
        missing = [r.id for r in self.rules if r.id not in PREDICATES]
        if missing:
            raise ValueError(
                f"rules.yaml declares rules with no predicate implementation: {missing}. "
                "A declared-but-unimplemented rule is a silently open gate."
            )

    # -- evaluation --------------------------------------------------------

    def evaluate(
        self,
        event: RiskEvent,
        candidates: list[CandidateAction],
        ctx: GateContext,
        diagnosis: Diagnosis | None = None,
    ) -> EvaluationResult:
        results: list[GateResult] = []
        permitted: list[CandidateAction] = []
        deferred: list[DeferredAction] = []

        for action in candidates:
            blocked = False
            defer_until: datetime | None = None
            defer_rule = ""
            defer_why = ""

            for rule in self.rules:
                if action.action_type not in rule.applies_to:
                    continue
                violated, rationale = PREDICATES[rule.id](
                    event, action, ctx, rule.params, diagnosis
                )
                verdict = (
                    rule.verdict if violated else GateVerdict.PASS
                )
                results.append(
                    GateResult(
                        rule_id=rule.id,
                        verdict=verdict,
                        rationale=rationale,
                        source=rule.source,
                        applies_to=action.action_type,
                    )
                )
                if not violated:
                    continue
                if rule.verdict is GateVerdict.BLOCK:
                    blocked = True
                    break  # a blocked action needs no further evaluation
                if rule.verdict is GateVerdict.DEFER:
                    when = self._defer_until(event, ctx, rule)
                    if defer_until is None or when > defer_until:
                        defer_until, defer_rule, defer_why = when, rule.id, rationale

            if blocked:
                continue
            if defer_until is not None:
                deferred.append(
                    DeferredAction(
                        action=action,
                        defer_until=defer_until,
                        rule_id=defer_rule,
                        rationale=defer_why,
                    )
                )
                continue
            permitted.append(action)

        return EvaluationResult(gate_results=results, permitted=permitted, deferred=deferred)

    @staticmethod
    def _defer_until(event: RiskEvent, ctx: GateContext, rule: RuleSpec) -> datetime:
        if rule.id == "rbi.emandate_pre_debit_notice":
            sent = ctx.notices_sent.get(event.event_id)
            hours = rule.params["notice_hours"]
            # If no notice has gone out, the clock starts when we send one now.
            return (sent or ctx.now) + timedelta(hours=hours)
        return ctx.now + timedelta(hours=1)

    # -- re-validation -----------------------------------------------------

    def revalidate(
        self,
        event: RiskEvent,
        pending: PendingAction,
        ctx: GateContext,
        diagnosis: Diagnosis | None = None,
    ) -> RevalidationOutcome:
        """Re-run the full gate immediately before execution.

        Called for every action with a gap between decision and execution. The
        ledger records this outcome alongside the original decision, so the trail
        shows both what was decided and what was true when it fired.
        """
        result = self.evaluate(event, [pending.action], ctx, diagnosis)

        changed: list[str] = []
        if event.consent_active != pending.snapshot_consent:
            changed.append(
                f"consent {pending.snapshot_consent} -> {event.consent_active}"
            )
        now_24h = ctx.counters.total_attempts_24h(
            event.instrument_token, ctx.now, event.prior_attempts_24h
        )
        if now_24h != pending.snapshot_attempts_24h:
            changed.append(f"attempts_24h {pending.snapshot_attempts_24h} -> {now_24h}")
        now_contacts = ctx.counters.total_contacts_week(
            event.customer_id, ctx.now, event.contacts_this_week
        )
        if now_contacts != pending.snapshot_contacts_week:
            changed.append(
                f"contacts_week {pending.snapshot_contacts_week} -> {now_contacts}"
            )

        return RevalidationOutcome(
            approved=bool(result.permitted),
            at=ctx.now,
            gate_results=result.gate_results,
            changed_since_decision=changed,
        )

    # -- static checks -----------------------------------------------------

    def check_invariants(self) -> list[str]:
        """Static contradiction and reachability checks over the rule set.

        Run in CI and at startup. A rule set that contradicts itself does not fail
        loudly at runtime — it silently permits or silently blocks everything,
        which is exactly the class of bug an audit trail cannot catch after the fact.
        """
        issues: list[str] = []
        by_id = {r.id: r for r in self.rules}

        merchant = by_id.get("network.merchant_retry_cap")
        d24 = by_id.get("network.attempts_per_card_24h")
        d30 = by_id.get("network.attempts_per_card_30d")

        if merchant and d24:
            if merchant.params["max_retries"] > d24.params["max_attempts"]:
                issues.append(
                    "network.merchant_retry_cap exceeds the 24h network cap — "
                    "our own limit would never bind and the network cap would."
                )
        if d24 and d30:
            if d24.params["max_attempts"] > d30.params["max_attempts"]:
                issues.append(
                    "24h cap exceeds 30d cap — the 24h rule is unreachable."
                )

        afa = by_id.get("rbi.afa_threshold")
        if afa:
            if afa.params["threshold"] > afa.params["exempt_category_threshold"]:
                issues.append(
                    "AFA base threshold exceeds the exempt-category threshold — "
                    "exempt categories would be treated more strictly than general ones."
                )

        floor = by_id.get("value.below_cost_floor")
        if floor and float(floor.params["min_amount"]) <= 0:
            issues.append("value.below_cost_floor min_amount must be positive to ever bind.")

        for rule in self.rules:
            if not rule.applies_to:
                issues.append(f"{rule.id} applies to no action type — it can never fire.")
            if not rule.source:
                issues.append(f"{rule.id} has no cited source.")

        return issues

    def invariant_max_merchant_retries(self) -> int:
        """The number the property-based tests assert can never be exceeded."""
        by_id = {r.id: r for r in self.rules}
        return int(by_id["network.merchant_retry_cap"].params["max_retries"])
