"""Counterfactual harness.

Runs every strategy against the same world through identical machinery and
reports the numbers that actually decide whether a recovery system is good:

    money recovered · attempts spent · contacts sent
    policy violations · estimated penalty exposure · NET VALUE

Recovery rate alone is the metric that makes blind retry look good. It is
reported, but never alone — a strategy that recovers more while burning five
times the attempts, contacting customers past the fatigue cap, and retrying
do-not-retry codes can be worth strictly less than one that recovers less.

Violations are counted for every strategy by running each planned action back
through the same PolicyEngine the gated agent uses. The baselines are not
punished by a different rulebook; they are measured against the one they ignore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from recoup.core.actions import COST_CONTACT, COST_RETRY
from recoup.core.counters import AttemptCounter
from recoup.core.diagnose import BatchContext, default_diagnoser
from recoup.core.models import ActionType, CandidateAction, GateVerdict, RiskEvent
from recoup.core.policy.engine import UNGATED_ACTIONS, GateContext, PolicyEngine
from recoup.core.scorer import (
    CHURN_HAZARD_PER_CONTACT,
    CHURN_HAZARD_PER_RETRY,
    COST_PER_SUPPORT_TICKET,
    P_SUPPORT_TICKET,
)
from recoup.harness.strategies import PlannedAction, Strategy
from recoup.sim.generator import SimWorld
from recoup.sim.oracle import RecoveryOracle

# Estimated cost of one network-rule breach.
#
# Mastercard charges $0.10 per attempt after a "Do Not Try Again" response under
# its Excessive Attempts programme; roughly Rs 8.50. This is the CHEAP end of the
# range and is used deliberately: Visa's excessive-reattempt penalties start at
# $5,000/month and scale to $50,000-$100,000 at volume, but those are step
# functions on portfolio-level monitoring, not per-attempt charges, and modelling
# them per-action would inflate the result. The figure below therefore
# UNDERSTATES real exposure, which is the safe direction for a claim.
PENALTY_PER_EXCESS_ATTEMPT = Decimal("8.50")


@dataclass
class StrategyResult:
    name: str
    description: str

    amount_at_risk: Decimal
    amount_recovered: Decimal = Decimal("0")
    recovered_count: int = 0

    attempts_spent: int = 0
    contacts_sent: int = 0

    policy_violations: int = 0
    violations_by_rule: dict[str, int] = field(default_factory=dict)

    direct_cost: Decimal = Decimal("0")
    support_cost: Decimal = Decimal("0")
    churn_cost: Decimal = Decimal("0")
    penalty_exposure: Decimal = Decimal("0")

    @property
    def recovery_rate(self) -> float:
        if not self.amount_at_risk:
            return 0.0
        return float(self.amount_recovered / self.amount_at_risk)

    @property
    def total_cost(self) -> Decimal:
        return self.direct_cost + self.support_cost + self.churn_cost + self.penalty_exposure

    @property
    def net_value(self) -> Decimal:
        return self.amount_recovered - self.total_cost

    @property
    def cost_per_rupee_recovered(self) -> Decimal | None:
        if not self.amount_recovered:
            return None
        return (self.total_cost / self.amount_recovered).quantize(Decimal("0.0001"))


class Counterfactual:
    def __init__(self, world: SimWorld) -> None:
        self.world = world
        self.events = {e.event_id: e for e in world.events}
        self.amount_at_risk = sum((e.amount for e in world.events), Decimal("0"))
        self.engine = PolicyEngine()
        self.ctx = BatchContext.from_events(world.events)
        self.diagnoser = default_diagnoser()

    def run(self, strategy: Strategy) -> StrategyResult:
        oracle = RecoveryOracle(self.world)
        oracle.reset()
        counters = AttemptCounter()

        result = StrategyResult(
            name=strategy.name,
            description=strategy.description,
            amount_at_risk=self.amount_at_risk,
        )

        plan = sorted(strategy.plan(self.world.events), key=lambda p: p.execute_at)
        recovered: set[str] = set()
        # Cumulative churn hazard already charged per customer. A customer can
        # only be lost once, so hazard saturates at 1.0 of their LTV; charging
        # ten escalating hazards for ten contacts would bill more than the
        # customer is worth and make over-contacting look worse than it is.
        self._churn_charged: dict[str, float] = {}

        for planned in plan:
            event = self.events[planned.event_id]

            # Once an event is recovered, further actions on it are wasted spend.
            # A strategy that keeps hammering a paid invoice is charged for it.
            if planned.event_id in recovered:
                self._charge(result, planned, event, counters, wasted=True)
                continue

            self._count_violations(result, planned, event, counters)
            self._charge(result, planned, event, counters)

            outcome = oracle.evaluate(event, planned.action_type, planned.execute_at)
            if outcome.success:
                recovered.add(planned.event_id)
                result.amount_recovered += event.amount
                result.recovered_count += 1

        return result

    # -- costing -----------------------------------------------------------

    def _charge(
        self,
        result: StrategyResult,
        planned: PlannedAction,
        event: RiskEvent,
        counters: AttemptCounter,
        wasted: bool = False,
    ) -> None:
        if planned.is_attempt:
            result.attempts_spent += 1
            result.direct_cost += COST_RETRY
            result.churn_cost += self._churn_charge(
                event, CHURN_HAZARD_PER_RETRY
            )
            counters.record_attempt(
                event.instrument_token, planned.execute_at, event.payment_id
            )
        if planned.is_contact:
            result.contacts_sent += 1
            result.direct_cost += COST_CONTACT
            sent = counters.total_contacts_week(
                event.customer_id, planned.execute_at, event.contacts_this_week
            )
            # Churn hazard compounds with every additional contact — this is the
            # cost that makes an unbounded nudger lose money.
            result.churn_cost += self._churn_charge(
                event, CHURN_HAZARD_PER_CONTACT * (1 + sent)
            )
            counters.record_contact(event.customer_id, planned.execute_at)

        if not wasted:
            result.support_cost += COST_PER_SUPPORT_TICKET * Decimal(str(P_SUPPORT_TICKET))

    def _churn_charge(self, event: RiskEvent, hazard: float) -> Decimal:
        """Charge incremental churn hazard, saturating at 100% of customer LTV."""
        already = self._churn_charged.get(event.customer_id, 0.0)
        room = max(0.0, 1.0 - already)
        applied = min(hazard, room)
        if applied <= 0:
            return Decimal("0")
        self._churn_charged[event.customer_id] = already + applied
        return (Decimal(str(applied)) * (event.customer_ltv or Decimal("0"))).quantize(
            Decimal("0.01")
        )

    # -- violations --------------------------------------------------------

    def _count_violations(
        self,
        result: StrategyResult,
        planned: PlannedAction,
        event: RiskEvent,
        counters: AttemptCounter,
    ) -> None:
        """Score this action against the same rulebook the gated agent obeys."""
        if planned.action_type in UNGATED_ACTIONS:
            return

        notices = (
            {event.event_id: planned.notice_sent_at} if planned.notice_sent_at else {}
        )
        gate_ctx = GateContext(
            now=planned.execute_at, counters=counters, notices_sent=notices
        )
        diagnosis = self.diagnoser.diagnose(event, self.ctx)
        candidate = CandidateAction(action_type=planned.action_type)

        evaluation = self.engine.evaluate(event, [candidate], gate_ctx, diagnosis)
        breached = {
            g.rule_id for g in evaluation.gate_results if g.verdict is GateVerdict.BLOCK
        }
        # A DEFER that the strategy ignored is a real RBI breach: it debited
        # inside the mandatory pre-debit notification window.
        for deferred in evaluation.deferred:
            breached.add(deferred.rule_id)

        for rule in breached:
            result.policy_violations += 1
            result.violations_by_rule[rule] = result.violations_by_rule.get(rule, 0) + 1
            if rule.startswith("network."):
                result.penalty_exposure += PENALTY_PER_EXCESS_ATTEMPT


def render(results: list[StrategyResult]) -> str:
    rows = [
        ("strategy", "recovered", "rate", "attempts", "contacts", "violations", "penalty", "NET VALUE"),
    ]
    for r in results:
        rows.append(
            (
                r.name,
                f"{r.amount_recovered:,.0f}",
                f"{r.recovery_rate:.1%}",
                str(r.attempts_spent),
                str(r.contacts_sent),
                str(r.policy_violations),
                f"{r.penalty_exposure:,.0f}",
                f"{r.net_value:,.0f}",
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    out = []
    for idx, row in enumerate(rows):
        out.append("  ".join(cell.rjust(widths[i]) if i else cell.ljust(widths[i])
                             for i, cell in enumerate(row)))
        if idx == 0:
            out.append("-" * (sum(widths) + 2 * (len(widths) - 1)))
    return "\n".join(out)
