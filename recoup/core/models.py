"""Core domain models.

Design rules that this module encodes and the rest of the system must honour:

1. The policy gate runs BEFORE any scoring or learning. A learner may only ever
   choose from `DecisionRecord.permitted`, so learning cannot produce a network
   fine or a compliance breach.
2. Every rule evaluation is recorded — passes as well as failures. That is what
   makes the compliance claim provable instead of merely asserted.
3. No PAN ever enters this system. Instruments are identified by a salted token.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class EventType(str, Enum):
    """The five leak points. See docs/domain-primer.md Part 2."""

    FAILED_PAYMENT = "failed_payment"
    UNCAPTURED_AUTH = "uncaptured_auth"
    LATE_AUTHORIZATION = "late_authorization"
    ABANDONED_CHECKOUT = "abandoned_checkout"
    FAILED_MANDATE = "failed_mandate"
    HALTED_SUBSCRIPTION = "halted_subscription"


class Instrument(str, Enum):
    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"
    EMANDATE = "emandate"
    UPI_AUTOPAY = "upi_autopay"


class FailureSource(str, Enum):
    """Razorpay error `source` — who needs to act."""

    CUSTOMER = "customer"
    BUSINESS = "business"
    BANK = "bank"
    GATEWAY = "gateway"
    NETWORK = "network"


class FailureStep(str, Enum):
    """Razorpay error `step` — where in the flow it broke."""

    PAYMENT_INITIATION = "payment_initiation"
    PAYMENT_AUTHENTICATION = "payment_authentication"
    PAYMENT_AUTHORIZATION = "payment_authorization"
    PAYMENT_RESPONSE = "payment_response"


class DeclineClass(str, Enum):
    """The split that decides whether a plain retry can ever work.

    NPCI data: ~18.3% of UPI failures are technical, ~81.7% business.
    Blind-retry strategies attack the small slice and waste attempts on the large one.
    """

    TECHNICAL = "technical"  # infra broke; customer was willing and able
    BUSINESS = "business"  # issuer deliberately refused
    UNKNOWN = "unknown"  # issuer gave no reason


class RootCause(str, Enum):
    """Normalised root cause, mapped from Razorpay reason codes.

    Deliberately smaller than the raw reason-code space: many distinct codes
    share one correct treatment. The mapping is evidence-linked in diagnose.py.
    """

    ISSUER_DOWN = "issuer_down"
    GATEWAY_DOWN = "gateway_down"
    TIMEOUT = "timeout"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    LIMIT_EXCEEDED = "limit_exceeded"
    CUSTOMER_ABANDONED = "customer_abandoned"
    AUTH_FAILED = "auth_failed"
    INSTRUMENT_EXPIRED = "instrument_expired"
    INSTRUMENT_BLOCKED = "instrument_blocked"
    INSTRUMENT_NOT_ENABLED = "instrument_not_enabled"
    INVALID_VPA = "invalid_vpa"
    RISK_BLOCKED = "risk_blocked"
    UNCAPTURED = "uncaptured"
    AMBIGUOUS_DECLINE = "ambiguous_decline"


# Root causes where a same-instrument retry can never succeed.
# Retrying these is what generates network fines and fraud flags.
TERMINAL_FOR_RETRY: frozenset[RootCause] = frozenset(
    {
        RootCause.INSTRUMENT_EXPIRED,
        RootCause.INSTRUMENT_BLOCKED,
        RootCause.INSTRUMENT_NOT_ENABLED,
        RootCause.INVALID_VPA,
        RootCause.RISK_BLOCKED,
    }
)


class ActionType(str, Enum):
    RETRY_NOW = "retry_now"
    RETRY_SCHEDULED = "retry_scheduled"
    NUDGE_PAYMENT_LINK = "nudge_payment_link"
    REQUEST_INSTRUMENT_SWITCH = "request_instrument_switch"
    REQUEST_VPA_REPAIR = "request_vpa_repair"
    CAPTURE_AUTHORIZED = "capture_authorized"
    WINBACK_SEQUENCE = "winback_sequence"
    ESCALATE_HUMAN = "escalate_human"
    STOP_UNCOLLECTIBLE = "stop_uncollectible"


class GateVerdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    DEFER = "defer"  # allowed, but not yet — e.g. RBI 24h pre-debit window


class OutcomeStatus(str, Enum):
    RECOVERED = "recovered"
    FAILED = "failed"
    PENDING = "pending"
    NOT_ATTEMPTED = "not_attempted"
    QUARANTINED = "quarantined"  # executor circuit breaker tripped


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


class RiskEvent(BaseModel):
    """One at-risk rupee amount, from any of the five leak points."""

    event_id: str
    batch_id: str
    occurred_at: datetime
    event_type: EventType

    amount: Decimal = Field(description="At-risk amount in INR")
    currency: str = "INR"

    instrument: Instrument
    instrument_token: str = Field(description="Salted hash. Never a PAN.")
    issuer: str

    customer_id: str
    order_id: str | None = None
    payment_id: str | None = None
    subscription_id: str | None = None

    # Razorpay error triple, absent for non-failure leak types
    error_code: str | None = None
    error_source: FailureSource | None = None
    error_step: FailureStep | None = None
    error_reason: str | None = None

    # Context the gate and scorer need
    prior_attempts_24h: int = 0
    prior_attempts_30d: int = 0

    # Instrument success history — the merchant's own observations, no privileged
    # feed required. This is the signal that separates the three biggest causes
    # behind a generic decline:
    #   no recent successes at all        -> the instrument is blocked
    #   a LARGER charge cleared recently  -> not a per-transaction ceiling
    #   only smaller charges cleared      -> a ceiling or an empty balance
    recent_success_count: int = 0
    max_recent_success_amount: Decimal | None = None
    contacts_this_week: int = 0
    consent_active: bool = True
    obligation_valid: bool = True
    auth_expires_at: datetime | None = None
    customer_ltv: Decimal | None = None
    customer_success_days: list[int] = Field(
        default_factory=list,
        description="Days of month this customer has historically paid on. "
        "Beats a hard-coded salary-cycle window when non-empty.",
    )

    # Simulator ground truth — populated only by sim/, never in production paths.
    truth_root_cause: RootCause | None = None
    truth_recoverable: bool | None = None
    truth_best_action: ActionType | None = None


class Diagnosis(BaseModel):
    root_cause: RootCause
    decline_class: DeclineClass
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ref: str = Field(
        description="Citation for why this mapping holds — a Razorpay doc anchor "
        "or network rule id. Every mapping must justify itself."
    )
    reasoned_by: str = Field(default="table", description="'table' or 'llm'")


class CandidateAction(BaseModel):
    action_type: ActionType
    execute_at: datetime | None = None
    attempt_cost: Decimal = Decimal("0")
    contact_cost: Decimal = Decimal("0")
    rationale: str = ""


