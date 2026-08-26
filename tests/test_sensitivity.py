"""Sensitivity regression tests.

These encode where the submission's claims hold and where they stop holding.
The most important test in this file is the one that asserts the ranking DOES
flip when all customer-retention cost is removed — because publishing a boundary
you have tested is honest, and publishing a claim whose boundary you never
looked for is not.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from recoup.harness.counterfactual import CostModel, Counterfactual
from recoup.harness.sensitivity import across_seeds, sweep
from recoup.harness.strategies import BlindRetry, FixedT3, GatedAgent
from recoup.sim.generator import generate_batch

# Published prior ranges. A claim that survives only outside these is not a claim.
CHURN_PER_CONTACT_RANGE = [0.0, 0.005, 0.010, 0.020, 0.050]
CHURN_PER_RETRY_RANGE = [0.0, 0.001, 0.004, 0.008]


@pytest.fixture(scope="module")
def world():
    return generate_batch(n_events=1000, seed=42)


# ---------------------------------------------------------------------------
# Claims that do NOT depend on any cost assumption
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "costs",
    [
        CostModel(),
        CostModel().with_(churn_per_contact=0.0, churn_per_retry=0.0),
        CostModel().with_(penalty_per_excess_attempt=Decimal("0")),
        CostModel().with_(retry_cost=Decimal("0"), contact_cost=Decimal("0")),
    ],
    ids=["baseline", "no_churn", "no_penalties", "free_actions"],
)
def test_zero_violations_is_independent_of_every_cost_assumption(world, costs):
    """The compliance claim rests on no economics whatsoever.

    Violations are counted by evaluating actions against the rulebook. No cost
    parameter can change that number, which is why it is the strongest claim in
    the submission and the one that leads the pitch.
    """
    cf = Counterfactual(world, costs=costs)
    assert cf.run(GatedAgent()).policy_violations == 0
    assert cf.run(BlindRetry()).policy_violations > 0


@pytest.mark.parametrize(
    "costs",
    [CostModel(), CostModel().with_(churn_per_contact=0.0, churn_per_retry=0.0)],
    ids=["baseline", "no_churn"],
)
def test_attempt_efficiency_is_independent_of_cost_assumptions(world, costs):
    """Attempt and contact counts are facts about behaviour, not economics."""
    cf = Counterfactual(world, costs=costs)
    gated = cf.run(GatedAgent())
    blind = cf.run(BlindRetry())

    assert gated.attempts_spent * 5 < blind.attempts_spent
    assert gated.contacts_sent * 3 < blind.contacts_sent
    # And it still recovers the large majority of what blind retry does.
    assert gated.amount_recovered > blind.amount_recovered * Decimal("0.8")


# ---------------------------------------------------------------------------
# The claim that DOES depend on an assumption
# ---------------------------------------------------------------------------


def test_ranking_holds_across_the_contact_churn_range():
    s = sweep("churn_per_contact", CHURN_PER_CONTACT_RANGE)
    assert s.gated_wins_everywhere, f"flips at churn_per_contact={s.flip_value()}"


def test_ranking_holds_across_the_retry_churn_range():
    s = sweep("churn_per_retry", CHURN_PER_RETRY_RANGE)
    assert s.gated_wins_everywhere, f"flips at churn_per_retry={s.flip_value()}"


@pytest.mark.parametrize(
    "parameter,values",
    [
        ("penalty_per_excess_attempt", [0.0, 8.5, 50.0, 200.0]),
        ("retry_cost", [0.0, 1.8, 10.0, 40.0]),
        ("contact_cost", [0.0, 0.32, 5.0, 25.0]),
        ("p_support_ticket", [0.0, 0.012, 0.05, 0.15]),
    ],
)
def test_ranking_is_insensitive_to_the_minor_cost_parameters(parameter, values):
    """None of these carries the result. Documented so nobody claims they do."""
    s = sweep(parameter, values)
    assert s.gated_wins_everywhere, f"{parameter} flips at {s.flip_value()}"


def test_ranking_flips_when_all_retention_cost_is_removed(world):
    """THE BOUNDARY. Published, not hidden.

    If repeated retries and repeated contact have literally zero effect on
    customer retention, blind retry wins on net value. That is the honest
    statement of what the net-value claim assumes: not a specific churn
    magnitude, but that annoying customers is not free.

    Neither churn term alone flips it — each is individually sufficient to
    preserve the ranking. Only removing both does.
    """
    cf = Counterfactual(world, costs=CostModel().with_(churn_per_contact=0.0, churn_per_retry=0.0))
    gated = cf.run(GatedAgent())
    blind = cf.run(BlindRetry())

    assert blind.net_value > gated.net_value, (
        "the documented boundary has moved — the sensitivity section of the "
        "README describes behaviour the code no longer has"
    )
    # Even here the gap is modest, and the compliance/efficiency claims survive.
    assert blind.net_value - gated.net_value < gated.net_value * Decimal("0.2")


# ---------------------------------------------------------------------------
# World stability
# ---------------------------------------------------------------------------


def test_ranking_is_stable_across_worlds():
    """Separates 'depends on an assumption' from 'depends on one lucky batch'."""
    for seed, nets in across_seeds().items():
        winner = max(nets, key=lambda k: nets[k])
        assert winner == "gated_agent", f"seed {seed} winner was {winner}: {nets}"


def test_blind_retry_is_value_destructive_across_worlds():
    for seed, nets in across_seeds().items():
        assert nets["blind_retry"] < 0, f"seed {seed}: blind retry net {nets['blind_retry']}"


def test_fixed_t3_beats_doing_nothing_across_worlds():
    """The baseline must be modelled fairly. If T+3 lost to inaction, it would be
    a strawman and the comparison would be worthless."""
    for seed, nets in across_seeds().items():
        assert nets["fixed_t3"] > 0, f"seed {seed}: T+3 net {nets['fixed_t3']}"
