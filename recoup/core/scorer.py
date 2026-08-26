"""Net-value scoring.

Answers "should we?" — never "may we?". The gate has already run and this scorer
only ever sees actions it permitted. That ordering is what lets value reasoning
be tuned freely without it ever being able to buy its way past a compliance rule.

**Recovery beliefs here are the SYSTEM's, anchored to published benchmarks.**
They are deliberately NOT imported from `recoup.sim.priors`. If the scorer read
the simulator's generative parameters it would be scoring against answers it had
been handed, and every rupee figure in the submission would be circular. The two
sets of numbers are independent, and they disagree — which is the point: the
counterfactual measures how a system does with imperfect beliefs, which is the
only situation any real system is ever in.

The objective is net value, not recovery rate:

    EV = P(recovery) x amount
       - attempt_cost - contact_cost - expected_support_cost
       - churn_risk x customer_LTV
       - issuer_trust_penalty

A strategy that recovers more while burning attempts, annoying customers, and
degrading an issuer relationship can be worth strictly less than one that
recovers less. Reporting recovery rate alone hides exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from recoup.core.diagnose import BatchContext
from recoup.core.models import (
    ActionType,
    EventType,
    CandidateAction,
    Diagnosis,
    EVComponents,
    RiskEvent,
    RootCause,
)

# ---------------------------------------------------------------------------
# System beliefs
# ---------------------------------------------------------------------------

# P(recovery) for a well-timed retry, by root cause.
#
# Anchored to published figures, not to the simulator:
#   - smart retry alone recovers ~40% of failed subscription payments; layered
#     recovery reaches ~70%  (Recurly)
#   - Razorpay's Intelligent Retry Engine reports +8% over baseline
# The ordering (technical >> transient business >> customer-action >> terminal)
# follows from the mechanism, and is the part we are confident about. The
# magnitudes are estimates and are swept by the sensitivity harness.
BELIEF_RETRY_RECOVERY: dict[RootCause, float] = {
    RootCause.GATEWAY_DOWN: 0.75,
    RootCause.ISSUER_DOWN: 0.70,
    RootCause.TIMEOUT: 0.62,
    RootCause.LIMIT_EXCEEDED: 0.40,
    RootCause.INSUFFICIENT_FUNDS: 0.30,
    RootCause.AMBIGUOUS_DECLINE: 0.20,
    RootCause.CUSTOMER_ABANDONED: 0.08,
    RootCause.AUTH_FAILED: 0.10,
}

# Outreach is a response rate, not an approval rate — a human has to act.
BELIEF_NUDGE_RECOVERY: dict[RootCause, float] = {
    RootCause.CUSTOMER_ABANDONED: 0.26,
    RootCause.AUTH_FAILED: 0.30,
    RootCause.TIMEOUT: 0.22,
    RootCause.INSUFFICIENT_FUNDS: 0.18,
}

BELIEF_SWITCH_RECOVERY = 0.24
BELIEF_VPA_REPAIR_RECOVERY = 0.28
BELIEF_WINBACK_RECOVERY = 0.12
# The bank already approved this money. Capture is an API call, not a gamble.
BELIEF_CAPTURE_RECOVERY = 0.97

# Each additional contact in the window cuts response and adds churn hazard.
FATIGUE_DECAY_PER_CONTACT = 0.65
CHURN_HAZARD_PER_CONTACT = 0.020
CHURN_HAZARD_PER_RETRY = 0.004

COST_PER_SUPPORT_TICKET = Decimal("42.00")
P_SUPPORT_TICKET = 0.012
# The "Transaction Failed, Money Debited" pattern generates tickets at a far
# higher rate — the customer sees a debit they believe failed.
P_SUPPORT_TICKET_UNCAPTURED = 0.19

# Cap on the trust penalty, expressed as a fraction of the amount at risk.
ISSUER_TRUST_PENALTY_CAP = Decimal("0.04")


@dataclass
class ScoredAction:
    action: CandidateAction
    ev: EVComponents

    @property
    def net_value(self) -> Decimal:
        return self.ev.net_value


class Scorer:
    def __init__(self, ctx: BatchContext) -> None:
        self.ctx = ctx

    # -- probability -------------------------------------------------------

    def p_recovery(
        self, event: RiskEvent, diagnosis: Diagnosis, action: CandidateAction, now: datetime
    ) -> float:
        cause = diagnosis.root_cause
        kind = action.action_type

        if kind is ActionType.CAPTURE_AUTHORIZED:
            return BELIEF_CAPTURE_RECOVERY
        if kind in (ActionType.REQUEST_INSTRUMENT_SWITCH,):
            base = BELIEF_SWITCH_RECOVERY
        elif kind is ActionType.REQUEST_VPA_REPAIR:
            base = BELIEF_VPA_REPAIR_RECOVERY
        elif kind is ActionType.WINBACK_SEQUENCE:
            base = BELIEF_WINBACK_RECOVERY
        elif kind is ActionType.NUDGE_PAYMENT_LINK:
            base = BELIEF_NUDGE_RECOVERY.get(cause, 0.12)
        elif kind in (ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED):
            base = BELIEF_RETRY_RECOVERY.get(cause, 0.15)
        else:
            # ESCALATE_HUMAN / STOP_UNCOLLECTIBLE recover nothing directly.
            return 0.0

        # Timing: an empty balance retried before payday is close to hopeless,
        # and this is the largest single adjustment in the model.
        if cause is RootCause.INSUFFICIENT_FUNDS and kind is ActionType.RETRY_SCHEDULED:
            when = action.execute_at or now
            observed = set(event.customer_success_days)
            if observed and when.day in observed:
                base *= 2.5
            elif when.day <= 5:
                base *= 2.0
            elif when.day >= 26:
                base *= 0.55

        # Contact fatigue applies to anything that talks to a customer.
        if action.contact_cost > 0 and event.contacts_this_week:
            base *= FATIGUE_DECAY_PER_CONTACT ** event.contacts_this_week

        # A history of failed attempts on this instrument is evidence against
        # the next one working.
        if event.prior_attempts_30d >= 3 and kind in (
            ActionType.RETRY_NOW,
            ActionType.RETRY_SCHEDULED,
        ):
            base *= 0.55

        return max(0.0, min(1.0, base))

    # -- costs -------------------------------------------------------------

    def issuer_trust_penalty(self, event: RiskEvent, action: CandidateAction) -> Decimal:
        """Cost of pushing on an issuer that is already refusing us.

        Hammering an issuer degrades the merchant's standing with it and quietly
        lowers approval rates on future *good* transactions. That externality is
        invisible in a per-transaction view, which is exactly why a PSP-side
        retry engine cannot price it and a merchant-side one can.
        """
        if action.action_type not in (ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED):
            return Decimal("0")

        share = self.ctx.technical_share(event.issuer, event.occurred_at)
        if share is None:
            return Decimal("0")
        # Healthy issuer failing us anyway -> our declines are the problem.
        excess = max(0.0, self.ctx.batch_technical_share - share)
        penalty = event.amount * Decimal(str(round(excess, 4))) * Decimal("0.5")
        return min(penalty, event.amount * ISSUER_TRUST_PENALTY_CAP).quantize(Decimal("0.01"))

    def churn_risk(self, event: RiskEvent, action: CandidateAction) -> float:
        """Hazard that this action costs us the customer relationship.

        Zero once the relationship is already broken. A halted subscription means
        the customer is gone — the LTV is forfeit before we act, so a win-back
        attempt risks nothing that has not already been lost.

        Without this carve-out the arithmetic was perverse: churn cost came to
        0.02 x LTV, LTV is ~11x the amount for a recurring customer, so the
        penalty (0.22 x amount) always exceeded win-back's recovery (0.12 x
        amount). Every post-halted action scored negative and the playbook was
        proposed 45 times and chosen zero times — a feature that existed only in
        the README.
        """
        if event.event_type is EventType.HALTED_SUBSCRIPTION:
            return 0.0
        if action.contact_cost > 0:
            return CHURN_HAZARD_PER_CONTACT * (1 + event.contacts_this_week)
        if action.attempt_cost > 0:
            return CHURN_HAZARD_PER_RETRY
        return 0.0

    def expected_support_cost(self, event: RiskEvent, diagnosis: Diagnosis) -> Decimal:
        p = (
            P_SUPPORT_TICKET_UNCAPTURED
            if diagnosis.root_cause is RootCause.UNCAPTURED
            else P_SUPPORT_TICKET
        )
        return (COST_PER_SUPPORT_TICKET * Decimal(str(p))).quantize(Decimal("0.01"))

    # -- scoring -----------------------------------------------------------

    def score(
        self, event: RiskEvent, diagnosis: Diagnosis, action: CandidateAction, now: datetime
    ) -> ScoredAction:
        ev = EVComponents(
            p_recovery=self.p_recovery(event, diagnosis, action, now),
            amount=event.amount,
            attempt_cost=action.attempt_cost,
            contact_cost=action.contact_cost,
            expected_support_cost=self.expected_support_cost(event, diagnosis),
            churn_risk=self.churn_risk(event, action),
            customer_ltv=event.customer_ltv or Decimal("0"),
            issuer_trust_penalty=self.issuer_trust_penalty(event, action),
        )
        return ScoredAction(action=action, ev=ev)

    def best(
        self,
        event: RiskEvent,
        diagnosis: Diagnosis,
        actions: list[CandidateAction],
        now: datetime,
    ) -> tuple[ScoredAction | None, str | None]:
        """Highest positive-net-value action, or None with a reason.

        Declining to act is a first-class outcome. A system that always does
        something is a system with no opinion about value.
        """
        if not actions:
            return None, "no action survived the policy gate"

        scored = sorted(
            (self.score(event, diagnosis, a, now) for a in actions),
            key=lambda s: s.net_value,
            reverse=True,
        )
        top = scored[0]
        if top.net_value <= 0:
            return None, (
                f"best available action ({top.action.action_type.value}) has negative "
                f"expected value: Rs {top.net_value:.2f}"
            )
        return top, None
