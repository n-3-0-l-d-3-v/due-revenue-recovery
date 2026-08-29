"""Oracle and counterfactual correctness.

These tests defend the submission's headline numbers. If any of them fail, the
counterfactual table is not measuring what it claims to measure.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from due.core.models import ActionType, RootCause
from due.harness.counterfactual import Counterfactual
from due.harness.strategies import BlindRetry, DoNothing, FixedT3, GatedAgent
from due.sim.generator import generate_batch
from due.sim.oracle import RecoveryOracle


@pytest.fixture(scope="module")
def world():
    return generate_batch(n_events=1000, seed=42)


@pytest.fixture(scope="module")
def results(world):
    cf = Counterfactual(world)
    return {s.name: cf.run(s) for s in (DoNothing(), FixedT3(), BlindRetry(), GatedAgent())}


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------


def test_oracle_is_deterministic(world):
    """The same query must always return the same answer.

    Without this, two strategies asking about the same counterfactual get
    different realities and the comparison between them means nothing.
    """
    event = next(e for e in world.events if e.error_reason)
    when = event.occurred_at + timedelta(days=3)

    a = RecoveryOracle(world).evaluate(event, ActionType.RETRY_SCHEDULED, when)
    b = RecoveryOracle(world).evaluate(event, ActionType.RETRY_SCHEDULED, when)

    assert a.success == b.success
    assert a.reason == b.reason


def test_oracle_answers_differ_by_timing(world):
    """If timing did not change outcomes, the whole thesis would be false."""
    funded = [
        e
        for e in world.events
        if world.latent[e.event_id].root_cause is RootCause.INSUFFICIENT_FUNDS
    ]
    oracle = RecoveryOracle(world)

    differed = 0
    for event in funded[:60]:
        early = oracle.evaluate(
            event, ActionType.RETRY_SCHEDULED, event.occurred_at + timedelta(hours=4)
        )
        late = oracle.evaluate(
            event, ActionType.RETRY_SCHEDULED, event.occurred_at + timedelta(days=20)
        )
        if early.success != late.success:
            differed += 1

    assert differed > 0, "retry timing never changed an outcome; the oracle is time-blind"


def test_retrying_an_empty_balance_before_payday_always_fails(world):
    """Mechanical, not probabilistic. Money does not appear because you asked twice."""
    oracle = RecoveryOracle(world)
    checked = 0
    for event in world.events:
        latent = world.latent[event.event_id]
        if latent.root_cause is not RootCause.INSUFFICIENT_FUNDS:
            continue
        if not latent.obligation_valid:
            continue
        funds_day = latent.funds_available_day or 1
        when = event.occurred_at + timedelta(hours=2)
        # Compare against the retry moment, not the failure day: a failure at
        # 23:00 plus two hours lands on the next date, which may already be payday.
        if when.day >= funds_day or when.month != event.occurred_at.month:
            continue

        result = oracle.evaluate(event, ActionType.RETRY_NOW, when)
        assert not result.success
        assert "balance not restored" in result.reason
        checked += 1

    assert checked > 0


def test_terminal_causes_never_recover_via_retry(world):
    oracle = RecoveryOracle(world)
    checked = 0
    for event in world.events:
        cause = world.latent[event.event_id].root_cause
        if cause not in (
            RootCause.INSTRUMENT_EXPIRED,
            RootCause.INSTRUMENT_BLOCKED,
            RootCause.INVALID_VPA,
            RootCause.RISK_BLOCKED,
        ):
            continue
        for offset in (1, 12, 72):
            result = oracle.evaluate(
                event, ActionType.RETRY_SCHEDULED, event.occurred_at + timedelta(hours=offset)
            )
            assert not result.success
        checked += 1

    assert checked > 0


def test_expired_authorisation_cannot_be_captured(world):
    oracle = RecoveryOracle(world)
    event = next(e for e in world.events if e.auth_expires_at)
    result = oracle.evaluate(
        event, ActionType.CAPTURE_AUTHORIZED, event.auth_expires_at + timedelta(hours=1)
    )
    assert not result.success
    assert "expired" in result.reason


def test_invalid_obligation_is_never_a_win(world):
    """Money collected against a cancelled order becomes a refund and a dispute."""
    oracle = RecoveryOracle(world)
    checked = 0
    for event in world.events:
        if world.latent[event.event_id].obligation_valid:
            continue
        result = oracle.evaluate(
            event, ActionType.RETRY_NOW, event.occurred_at + timedelta(days=2)
        )
        assert not result.success
        checked += 1
    assert checked > 0


# ---------------------------------------------------------------------------
# Counterfactual
# ---------------------------------------------------------------------------


def test_do_nothing_recovers_nothing(results):
    r = results["do_nothing"]
    assert r.amount_recovered == Decimal("0")
    assert r.attempts_spent == 0
    assert r.net_value == Decimal("0")


def test_gated_agent_commits_zero_policy_violations(results):
    """The core safety claim, measured over a full batch rather than asserted.

    Every strategy is scored against the same rulebook by the same code. The
    gated agent must score zero — not few.
    """
    r = results["gated_agent"]
    assert r.policy_violations == 0, f"violations: {r.violations_by_rule}"
    assert r.penalty_exposure == Decimal("0")


def test_baselines_do_commit_violations(results):
    """If the baselines were also clean, the gate would be decorative."""
    assert results["blind_retry"].policy_violations > 0
    assert results["fixed_t3"].policy_violations > 0
    assert results["blind_retry"].penalty_exposure > 0


def test_blind_retry_retries_terminal_declines(results):
    """The specific breach that generates Mastercard Excessive Attempts fees."""
    assert results["blind_retry"].violations_by_rule.get("network.do_not_retry_terminal", 0) > 0


def test_blind_retry_recovers_more_but_is_worth_less(results):
    """The entire thesis, in one assertion.

    Recovery rate is the metric that flatters blind retry. Net value is the one
    that decides. If this ever inverts, the submission's argument is wrong and
    the README must change.
    """
    blind = results["blind_retry"]
    gated = results["gated_agent"]

    assert blind.amount_recovered > gated.amount_recovered
    assert blind.net_value < gated.net_value


def test_gated_agent_has_the_highest_net_value(results):
    gated = results["gated_agent"]
    for name, other in results.items():
        if name == "gated_agent":
            continue
        assert gated.net_value > other.net_value, f"{name} beat the gated agent on net value"


def test_gated_agent_spends_far_fewer_attempts(results):
    """Efficiency, not just compliance. Attempts are a capped, costly budget."""
    gated = results["gated_agent"]
    assert gated.attempts_spent < results["blind_retry"].attempts_spent / 5
    assert gated.attempts_spent < results["fixed_t3"].attempts_spent / 2


def test_counterfactual_is_reproducible(world):
    """Same world, same numbers. A table that moves between runs is not evidence."""
    runs = []
    for _ in range(2):
        cf = Counterfactual(world)
        runs.append(
            {s.name: cf.run(s) for s in (FixedT3(), BlindRetry(), GatedAgent())}
        )

    for name in runs[0]:
        assert runs[0][name].amount_recovered == runs[1][name].amount_recovered
        assert runs[0][name].attempts_spent == runs[1][name].attempts_spent
        assert runs[0][name].policy_violations == runs[1][name].policy_violations
        assert runs[0][name].net_value == runs[1][name].net_value


def test_every_strategy_is_measured_by_identical_machinery(results):
    """All strategies must be charged the same way — no strategy scores itself."""
    for r in results.values():
        assert r.amount_at_risk == results["do_nothing"].amount_at_risk
        assert r.net_value == r.amount_recovered - r.total_cost


def test_churn_cost_saturates_at_customer_ltv(world):
    """A customer can only be lost once. Uncapped hazard would bill past their LTV
    and overstate the case against over-contacting."""
    cf = Counterfactual(world)
    result = cf.run(BlindRetry())

    total_ltv = sum(
        (e.customer_ltv or Decimal("0")) for e in world.events
    )
    assert result.churn_cost <= total_ltv


# ---------------------------------------------------------------------------
# Oracle completeness
# ---------------------------------------------------------------------------


def test_every_action_the_system_chooses_is_measurable(world):
    """An action with no oracle verdict is unmeasurable, and unmeasurable means
    it cannot appear in the counterfactual — it would be a feature that exists
    only in the README.

    This caught `winback_sequence` being emitted 45 times and chosen zero times,
    and `escalate_human` never being emitted at all.
    """
    from due.core.pipeline import RecoveryPipeline
    from due.sim.oracle import RecoveryOracle

    pipeline = RecoveryPipeline()
    result = pipeline.run(world.events)
    result = pipeline.execute_pending(result, {e.event_id: e for e in world.events})

    oracle = RecoveryOracle(world)
    events = {e.event_id: e for e in world.events}
    chosen_types = {d.chosen.action_type for d in result.acted}
    assert chosen_types, "pipeline chose no actions at all"

    for action_type in chosen_types:
        decision = next(d for d in result.acted if d.chosen.action_type is action_type)
        verdict = oracle.evaluate(
            events[decision.event_id],
            action_type,
            decision.chosen.execute_at or decision.decided_at,
        )
        assert "recovers no money directly" not in verdict.reason, (
            f"{action_type.value} falls through to the oracle's default branch — "
            "it is chosen by the system but cannot be scored"
        )


def test_post_halted_playbook_actually_fires(world):
    """Razorpay's retries end at `halted`; this is the gap the project claims to
    fill. A claim that never executes is not a feature."""
    from due.core.models import ActionType, EventType
    from due.core.pipeline import RecoveryPipeline

    pipeline = RecoveryPipeline()
    result = pipeline.run(world.events)

    halted = [
        d for d in result.decisions if d.event.event_type is EventType.HALTED_SUBSCRIPTION
    ]
    assert halted, "batch contained no halted subscriptions"

    acted = [d for d in halted if d.chosen is not None]
    assert acted, "no halted subscription received any action"
    assert any(d.chosen.action_type is ActionType.WINBACK_SEQUENCE for d in acted)

    # And retry is never proposed — Razorpay already exhausted T+3 before this state.
    for decision in halted:
        for candidate in decision.candidates:
            assert candidate.action_type not in (
                ActionType.RETRY_NOW,
                ActionType.RETRY_SCHEDULED,
            ), "retry proposed on an already-halted subscription"
