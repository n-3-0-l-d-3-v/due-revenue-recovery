"""Candidate action enumeration.

Maps a diagnosis to the actions worth *considering*. Nothing here decides whether
an action is permitted (the gate does) or worth taking (the scorer does) — this
stage only refuses to propose actions that are nonsensical for the cause.

The mapping is the operational half of the failure taxonomy in
docs/domain-primer.md Part 3. A blind-retry system has exactly one entry in this
table for every cause; the whole thesis is that different causes need different
treatments, and this is where that becomes code.

Timing lives here too, because *when* to retry is part of proposing the action,
not an afterthought. For an empty balance the retry time is the single largest
lever available — an `insufficient_funds` failure on the 28th is a different
proposition on the 1st.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from due.core.models import ActionType, CandidateAction, Diagnosis, EventType, RiskEvent, RootCause

# Merchant-side unit costs. These are the merchant's own operating costs — known
# quantities, not latent truth — so they legitimately live system-side.
COST_RETRY = Decimal("1.80")
COST_SMS = Decimal("0.28")
COST_EMAIL = Decimal("0.04")
COST_CONTACT = COST_SMS + COST_EMAIL

# Indian salaried pay cycles cluster on the 1st and the last working day. Used
# only when a customer has no observed history of their own.
SALARY_WINDOW = (1, 2, 3, 4, 5)


def next_salary_window(now: datetime, success_days: list[int]) -> datetime:
    """When is this customer's balance most likely to be healthy again?

    A customer's own observed payment days beat the calendar prior whenever they
    exist — a gig worker paid on the 12th is not served by a 1st-of-month rule.
    Thin history is common, which is why the calendar fallback stays.
    """
    targets = sorted(set(success_days)) if success_days else list(SALARY_WINDOW)

    for day in targets:
        if day > now.day:
            try:
                return now.replace(day=day, hour=10, minute=0, second=0, microsecond=0)
            except ValueError:
                continue

    # Nothing left this month — roll to the first target next month.
    first = targets[0]
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(year, month, min(first, 28), 10, 0)


def enumerate_actions(
    event: RiskEvent, diagnosis: Diagnosis, now: datetime
) -> list[CandidateAction]:
    """Actions worth considering for this event, given its diagnosis."""
    cause = diagnosis.root_cause
    out: list[CandidateAction] = []

    # --- already halted ---------------------------------------------------
    # Razorpay's T+3 retries are exhausted before a subscription reaches this
    # state. Proposing another retry ignores that history — and because a retry
    # always outscores a win-back on raw expected value, it also meant the
    # post-halted playbook was emitted 45 times and chosen zero times. Retry is
    # not on the menu here; the question is whether the customer can be saved.
    if event.event_type is EventType.HALTED_SUBSCRIPTION:
        if cause in (
            RootCause.INSTRUMENT_EXPIRED,
            RootCause.INSTRUMENT_BLOCKED,
            RootCause.INSTRUMENT_NOT_ENABLED,
            RootCause.INVALID_VPA,
        ):
            out.append(
                CandidateAction(
                    action_type=ActionType.REQUEST_INSTRUMENT_SWITCH,
                    contact_cost=COST_CONTACT,
                    rationale=f"subscription halted on {cause.value}; only a new instrument revives it",
                )
            )
        elif cause is RootCause.RISK_BLOCKED:
            out.append(
                CandidateAction(
                    action_type=ActionType.STOP_UNCOLLECTIBLE,
                    rationale="halted after a fraud flag; pursuing it is card-testing behaviour",
                )
            )
        else:
            out.append(
                CandidateAction(
                    action_type=ActionType.WINBACK_SEQUENCE,
                    contact_cost=COST_CONTACT,
                    rationale=(
                        "retries exhausted and the subscription is halted; win-back "
                        "before the customer is permanently lost"
                    ),
                )
            )
        return out

    def retry_now(why: str) -> None:
        out.append(
            CandidateAction(
                action_type=ActionType.RETRY_NOW, attempt_cost=COST_RETRY, rationale=why
            )
        )

    def retry_at(when: datetime, why: str) -> None:
        out.append(
            CandidateAction(
                action_type=ActionType.RETRY_SCHEDULED,
                execute_at=when,
                attempt_cost=COST_RETRY,
                rationale=why,
            )
        )

    def nudge(why: str) -> None:
        out.append(
            CandidateAction(
                action_type=ActionType.NUDGE_PAYMENT_LINK,
                contact_cost=COST_CONTACT,
                rationale=why,
            )
        )

    def switch(action: ActionType, why: str) -> None:
        out.append(
            CandidateAction(action_type=action, contact_cost=COST_CONTACT, rationale=why)
        )

    # --- authorised but not captured -------------------------------------
    # Not a failure. The bank approved and the customer consented; the merchant
    # simply has not claimed the money yet. No retry is involved.
    if cause is RootCause.UNCAPTURED:
        out.append(
            CandidateAction(
                action_type=ActionType.CAPTURE_AUTHORIZED,
                rationale="authorised payment not yet captured; capture before the window closes",
            )
        )
        return out

    # --- technical: the customer was willing and able ---------------------
    if cause is RootCause.ISSUER_DOWN:
        # Retrying into a live outage burns an attempt against the network cap
        # and fails for the same reason it failed the first time.
        retry_at(now + timedelta(hours=6), "issuer outage; retry once it has cleared")
        return out

    if cause is RootCause.GATEWAY_DOWN:
        retry_now("gateway-side failure; the customer's instrument is fine")
        return out

    if cause is RootCause.TIMEOUT:
        retry_now("customer ran out the payment clock; a fresh attempt often clears")
        nudge("send a fresh link in case they are no longer at the checkout")
        return out

    # --- transient business: timing is the lever --------------------------
    if cause is RootCause.INSUFFICIENT_FUNDS:
        when = next_salary_window(now, event.customer_success_days)
        basis = (
            f"customer historically pays on days {sorted(set(event.customer_success_days))}"
            if event.customer_success_days
            else "no payment history; using the salary-cycle prior"
        )
        retry_at(when, f"balance likely restored by {when:%d %b}; {basis}")
        nudge("offer the customer a link so they can pay when ready")
        return out

    if cause is RootCause.LIMIT_EXCEEDED:
        retry_at(
            (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0),
            "daily ceiling hit; the counter resets tomorrow",
        )
        switch(
            ActionType.REQUEST_INSTRUMENT_SWITCH,
            "a different instrument sidesteps this instrument's ceiling",
        )
        return out

    # --- needs the customer to act ---------------------------------------
    if cause in (RootCause.CUSTOMER_ABANDONED, RootCause.AUTH_FAILED):
        nudge("a human must complete this; auto-retry cannot supply an OTP or a decision")
        return out

    # --- terminal for this instrument ------------------------------------
    if cause in (
        RootCause.INSTRUMENT_EXPIRED,
        RootCause.INSTRUMENT_BLOCKED,
        RootCause.INSTRUMENT_NOT_ENABLED,
    ):
        switch(
            ActionType.REQUEST_INSTRUMENT_SWITCH,
            f"{cause.value}: no retry on this instrument can succeed",
        )
        return out

    if cause is RootCause.INVALID_VPA:
        switch(ActionType.REQUEST_VPA_REPAIR, "VPA cannot be resolved; the customer must correct it")
        return out

    # --- do not touch -----------------------------------------------------
    if cause is RootCause.RISK_BLOCKED:
        # Chasing a fraud-flagged payment — even via another instrument — is the
        # card-testing pattern. The merchant becomes the suspect.
        out.append(
            CandidateAction(
                action_type=ActionType.STOP_UNCOLLECTIBLE,
                rationale="issuer flagged fraud; any further attempt looks like card testing",
            )
        )
        return out

    # --- unmapped ---------------------------------------------------------
    out.append(
        CandidateAction(
            action_type=ActionType.ESCALATE_HUMAN,
            rationale=f"no confident diagnosis ({cause.value}); needs a human look",
        )
    )
    return out

