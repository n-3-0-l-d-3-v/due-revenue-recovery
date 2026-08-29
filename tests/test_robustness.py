"""Multi-seed robustness.

One seed is an anecdote. These tests assert the claims hold across many
independently generated random worlds — and, just as importantly, that the
worst case is reported rather than buried.
"""

from __future__ import annotations

import pytest

from due.harness.robustness import sweep

N_SEEDS = 30


@pytest.fixture(scope="module")
def report():
    return sweep(range(1, N_SEEDS + 1), n_events=500)


def test_zero_violations_holds_in_every_world(report):
    """The compliance claim must be perfect, not merely typical. One violating
    seed would mean the gate can be beaten by an unlucky random draw."""
    assert report.zero_violation_rate == 1.0, (
        f"gated agent violated a rule in at least one of {N_SEEDS} random worlds"
    )


def test_best_net_value_holds_in_most_worlds(report):
    """Net value is a Tier B claim — conditional on retention cost being
    non-zero. It is not required to win every single random draw, only the
    large majority. If it started losing often, the README's framing would
    need to change from 'the gated agent wins' to something weaker."""
    assert report.best_net_value_rate >= 0.85, (
        f"gated agent only had the best net value in "
        f"{report.best_net_value_rate:.0%} of {N_SEEDS} worlds"
    )


def test_the_worst_case_is_still_compliant(report):
    """Even in the single worst seed for net value, zero violations must hold.
    Tier A is not allowed to degrade just because Tier B had a bad day."""
    worst = report.worst_seed_for_gated
    assert worst.gated.policy_violations == 0


def test_blind_retry_never_wins_on_violations(report):
    for run in report.runs:
        assert run.gated.policy_violations < run.blind.policy_violations


def test_report_identifies_its_own_worst_case(report):
    """A robustness report that cannot name its worst case is not credible."""
    worst = report.worst_seed_for_gated
    best = report.best_seed_for_gated
    assert worst.seed != best.seed or N_SEEDS == 1
    assert isinstance(worst.seed, int)
