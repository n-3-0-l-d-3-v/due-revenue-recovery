"""Generative priors for the simulator.

This file IS the credibility argument. Anyone evaluating this project can read it
and see exactly what world we assumed. Every constant is tagged:

    [CITED]    derived from published data — source on the line above
    [DERIVED]  computed from a CITED value plus a stated rule
    [ASSUMED]  our judgement. No source exists. Sensitivity analysis sweeps these.

If a number is ASSUMED, the sensitivity harness must vary it. Claims that survive
only at one setting of an ASSUMED parameter are not claims we make.
"""

from __future__ import annotations

from decimal import Decimal

from recoup.core.models import (
    ActionType,
    DeclineClass,
    Instrument,
    RootCause,
)

# ---------------------------------------------------------------------------
# Instrument mix
# ---------------------------------------------------------------------------

# [CITED] UPI dominates Indian digital retail payments by volume; cards and
# netbanking form the remainder. NPCI product statistics.
# https://www.npci.org.in/what-we-do/upi/product-statistics
ONE_TIME_INSTRUMENT_MIX: dict[Instrument, float] = {
    Instrument.UPI: 0.62,
    Instrument.CARD: 0.26,
    Instrument.NETBANKING: 0.12,
}

# [ASSUMED] Recurring mandates split between UPI Autopay and card/bank e-mandate.
# UPI Autopay has grown fast but e-mandate remains significant for higher ticket sizes.
RECURRING_INSTRUMENT_MIX: dict[Instrument, float] = {
    Instrument.UPI_AUTOPAY: 0.58,
    Instrument.EMANDATE: 0.42,
}


# ---------------------------------------------------------------------------
# Decline class split
# ---------------------------------------------------------------------------

# [CITED] NPCI: 81.7% of failed transactions are business declines (user-side:
# invalid PIN, insufficient balance, limits), 18.26% technical declines
# (system/network unavailability at bank or NPCI).
# https://www.business-standard.com/amp/article/economy-policy/insufficient-balance-wrong-pin-top-reasons-for-failed-digital-transactions-121122700487_1.html
#
# This is the single most important prior in the file. It is why blind-retry
# strategies underperform: they spend attempts on the 81.7% that will decline
# identically, and are only ever right about the 18.3%.
DECLINE_CLASS_SPLIT: dict[DeclineClass, float] = {
    DeclineClass.BUSINESS: 0.817,
    DeclineClass.TECHNICAL: 0.183,
}


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------

# Reason code -> (root cause, decline class, evidence anchor).
# [CITED] Codes and their documented semantics come from Razorpay's error tables.
# https://razorpay.com/docs/errors/payments/cards/
# https://razorpay.com/docs/errors/payments/upi/
REASON_TO_ROOT_CAUSE: dict[str, tuple[RootCause, DeclineClass, str]] = {
    # --- cards ---
    "bank_technical_error": (RootCause.ISSUER_DOWN, DeclineClass.TECHNICAL, "rzp:cards#bank_technical_error"),
    "gateway_technical_error": (RootCause.GATEWAY_DOWN, DeclineClass.TECHNICAL, "rzp:cards#gateway_technical_error"),
    "payment_timed_out": (RootCause.TIMEOUT, DeclineClass.TECHNICAL, "rzp:cards#payment_timed_out"),
    "insufficient_funds": (RootCause.INSUFFICIENT_FUNDS, DeclineClass.BUSINESS, "rzp:cards#insufficient_funds"),
    "transaction_limit_exceeded": (RootCause.LIMIT_EXCEEDED, DeclineClass.BUSINESS, "rzp:cards#transaction_limit_exceeded"),
    "payment_cancelled": (RootCause.CUSTOMER_ABANDONED, DeclineClass.BUSINESS, "rzp:cards#payment_cancelled"),
    "authentication_failed": (RootCause.AUTH_FAILED, DeclineClass.BUSINESS, "rzp:cards#authentication_failed"),
    "incorrect_cvv": (RootCause.AUTH_FAILED, DeclineClass.BUSINESS, "rzp:cards#incorrect_cvv"),
    "card_expired": (RootCause.INSTRUMENT_EXPIRED, DeclineClass.BUSINESS, "rzp:cards#card_expired"),
    "card_not_enrolled": (RootCause.INSTRUMENT_NOT_ENABLED, DeclineClass.BUSINESS, "rzp:cards#card_not_enrolled"),
    "card_disabled_for_online_payments": (RootCause.INSTRUMENT_NOT_ENABLED, DeclineClass.BUSINESS, "rzp:cards#card_disabled"),
    "debit_instrument_inactive": (RootCause.INSTRUMENT_NOT_ENABLED, DeclineClass.BUSINESS, "rzp:cards#debit_instrument_inactive"),
    "debit_instrument_blocked": (RootCause.INSTRUMENT_BLOCKED, DeclineClass.BUSINESS, "rzp:cards#debit_instrument_blocked"),
    "payment_risk_check_failed": (RootCause.RISK_BLOCKED, DeclineClass.BUSINESS, "rzp:cards#payment_risk_check_failed"),
    "card_declined": (RootCause.AMBIGUOUS_DECLINE, DeclineClass.UNKNOWN, "rzp:cards#card_declined"),
    "payment_failed": (RootCause.AMBIGUOUS_DECLINE, DeclineClass.UNKNOWN, "rzp:cards#payment_failed"),
    # --- upi ---
    "partner_bank_downtime": (RootCause.ISSUER_DOWN, DeclineClass.TECHNICAL, "rzp:upi#partner_bank_downtime"),
    "partner_bank_technical_issues": (RootCause.ISSUER_DOWN, DeclineClass.TECHNICAL, "rzp:upi#partner_bank_technical_issues"),
    "credit_failed": (RootCause.GATEWAY_DOWN, DeclineClass.TECHNICAL, "rzp:upi#credit_failed"),
    "payment_collect_request_expired": (RootCause.TIMEOUT, DeclineClass.TECHNICAL, "rzp:upi#collect_expired"),
    "payment_declined": (RootCause.AMBIGUOUS_DECLINE, DeclineClass.UNKNOWN, "rzp:upi#payment_declined"),
    "customer_bank_account_mismatch": (RootCause.CUSTOMER_ABANDONED, DeclineClass.BUSINESS, "rzp:upi#account_mismatch"),
    "invalid_vpa": (RootCause.INVALID_VPA, DeclineClass.BUSINESS, "rzp:upi#invalid_vpa"),
    "vpa_resolution_failed": (RootCause.INVALID_VPA, DeclineClass.BUSINESS, "rzp:upi#vpa_resolution_failed"),
}

# Within-class reason weights per instrument.
# [DERIVED] Shapes follow NPCI's finding that insufficient balance and wrong PIN
# are the top business-decline reasons; exact splits are [ASSUMED] and swept.
BUSINESS_REASON_WEIGHTS: dict[Instrument, dict[str, float]] = {
    Instrument.CARD: {
        "insufficient_funds": 0.34,
        "authentication_failed": 0.19,
        "card_declined": 0.13,
        "transaction_limit_exceeded": 0.10,
        "payment_cancelled": 0.09,
        "incorrect_cvv": 0.05,
        "card_expired": 0.04,
        "debit_instrument_blocked": 0.03,
        "card_not_enrolled": 0.02,
        "payment_risk_check_failed": 0.01,
    },
    Instrument.UPI: {
        "insufficient_funds": 0.41,
        "authentication_failed": 0.22,  # wrong UPI PIN
        "payment_cancelled": 0.15,
        "payment_declined": 0.11,
        "customer_bank_account_mismatch": 0.06,
        "invalid_vpa": 0.03,
        "vpa_resolution_failed": 0.02,
    },
    Instrument.NETBANKING: {
        "insufficient_funds": 0.45,
        "authentication_failed": 0.30,
        "payment_cancelled": 0.25,
    },
}
# Mandate debits inherit the card/UPI business profile but never see
# interactive-auth failures — there is no customer at the keyboard.
BUSINESS_REASON_WEIGHTS[Instrument.EMANDATE] = {
    "insufficient_funds": 0.62,
    "transaction_limit_exceeded": 0.14,
    "card_expired": 0.11,
    "debit_instrument_blocked": 0.08,
    "payment_failed": 0.05,
}
BUSINESS_REASON_WEIGHTS[Instrument.UPI_AUTOPAY] = {
    "insufficient_funds": 0.68,
    "payment_declined": 0.16,
    "invalid_vpa": 0.09,
    "transaction_limit_exceeded": 0.07,
}

TECHNICAL_REASON_WEIGHTS: dict[Instrument, dict[str, float]] = {
    Instrument.CARD: {
        "bank_technical_error": 0.52,
        "gateway_technical_error": 0.28,
        "payment_timed_out": 0.20,
    },
    Instrument.UPI: {
        "partner_bank_downtime": 0.38,
        "partner_bank_technical_issues": 0.24,
        "payment_collect_request_expired": 0.22,
        "credit_failed": 0.16,
    },
    Instrument.NETBANKING: {
        "bank_technical_error": 0.60,
        "gateway_technical_error": 0.40,
    },
    Instrument.EMANDATE: {
        "bank_technical_error": 0.65,
        "gateway_technical_error": 0.35,
    },
    Instrument.UPI_AUTOPAY: {
        "partner_bank_downtime": 0.55,
        "partner_bank_technical_issues": 0.45,
    },
}


# ---------------------------------------------------------------------------
# Recovery probabilities — the latent truth the oracle samples from
# ---------------------------------------------------------------------------

# Base probability that a well-timed, gate-permitted retry recovers the payment,
# conditioned on root cause.
#
# [DERIVED] Anchored to two published figures and shaped by the technical/business
# logic in docs/domain-primer.md Part 3:
#   - Razorpay's Intelligent Retry Engine reports +8% debit collections over baseline
#     https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/
#   - Smart retry alone recovers ~40% of failed subscription payments; layered
#     recovery reaches ~70%.  https://recurly.com/blog/failed-payment-recovery-data-based-strategy/
# The ORDERING here is well supported (technical >> transient business >> terminal).
# The exact values are [ASSUMED] and swept by the sensitivity harness.
BASE_RECOVERY_PROB: dict[RootCause, float] = {
    # Technical: the customer was willing and able. Retry works well.
    RootCause.ISSUER_DOWN: 0.78,
    RootCause.GATEWAY_DOWN: 0.82,
    RootCause.TIMEOUT: 0.71,
    # Transient business: depends heavily on WHEN.
    RootCause.INSUFFICIENT_FUNDS: 0.34,
    RootCause.LIMIT_EXCEEDED: 0.46,
    # Needs the customer to act. Retry alone is near-useless; a nudge is the lever.
    RootCause.CUSTOMER_ABANDONED: 0.11,
    RootCause.AUTH_FAILED: 0.14,
    # Terminal for same-instrument retry. Non-zero only via instrument switch.
    RootCause.INSTRUMENT_EXPIRED: 0.0,
    RootCause.INSTRUMENT_BLOCKED: 0.0,
    RootCause.INSTRUMENT_NOT_ENABLED: 0.0,
    RootCause.INVALID_VPA: 0.0,
    RootCause.RISK_BLOCKED: 0.0,
    # Uncaptured auth is not a recovery gamble — it is an operational miss.
    RootCause.UNCAPTURED: 0.97,
    RootCause.AMBIGUOUS_DECLINE: 0.22,
}

# Multiplier on recovery probability when the action matches the root cause.
# [ASSUMED] — encodes "the right treatment for the right diagnosis". Swept.
ACTION_FIT: dict[tuple[RootCause, ActionType], float] = {
    (RootCause.CUSTOMER_ABANDONED, ActionType.NUDGE_PAYMENT_LINK): 4.2,
    (RootCause.AUTH_FAILED, ActionType.NUDGE_PAYMENT_LINK): 3.8,
    (RootCause.INSTRUMENT_EXPIRED, ActionType.REQUEST_INSTRUMENT_SWITCH): 1.0,
    (RootCause.INSTRUMENT_BLOCKED, ActionType.REQUEST_INSTRUMENT_SWITCH): 1.0,
    (RootCause.INSTRUMENT_NOT_ENABLED, ActionType.REQUEST_INSTRUMENT_SWITCH): 1.0,
    (RootCause.INVALID_VPA, ActionType.REQUEST_VPA_REPAIR): 1.0,
    (RootCause.UNCAPTURED, ActionType.CAPTURE_AUTHORIZED): 1.0,
}

# Absolute recovery probability for switch/repair actions on terminal causes.
# [ASSUMED] Customer must act, so this is a response-rate, not an approval-rate.
TERMINAL_SWITCH_RECOVERY_PROB: float = 0.27

# Terminal for a same-instrument retry, but still recoverable if the customer
# switches instrument or repairs their VPA. Distinguishing these from truly
# unrecoverable events matters: counting them as lost understates what a
# well-designed system can reach, and counting them as retryable generates fines.
TERMINAL_FOR_RETRY_SWITCHABLE: frozenset[RootCause] = frozenset(
    {
        RootCause.INSTRUMENT_EXPIRED,
        RootCause.INSTRUMENT_BLOCKED,
        RootCause.INSTRUMENT_NOT_ENABLED,
        RootCause.INVALID_VPA,
    }
)
# RISK_BLOCKED is deliberately excluded: the bank flagged fraud. Chasing it with a
# different instrument is exactly the card-testing pattern that gets a merchant
# classified as the attacker.


