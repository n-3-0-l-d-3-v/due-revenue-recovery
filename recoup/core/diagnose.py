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

from recoup.core.models import DeclineClass, Diagnosis, EventType, RiskEvent, RootCause

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

