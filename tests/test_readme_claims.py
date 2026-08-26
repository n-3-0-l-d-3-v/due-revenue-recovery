"""The README must not drift from the code.

Every number a reviewer reads in the README is parsed back out of it here and
checked against a live run. A submission whose headline table no longer matches
its own output loses credibility the moment someone runs it — and README drift
is silent, because nothing else in a test suite reads documentation.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from recoup.harness.counterfactual import Counterfactual
from recoup.harness.strategies import BlindRetry, FixedT3, GatedAgent
from recoup.sim.generator import generate_batch

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
ARCHITECTURE = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

# The README documents seed 42 / 1000 events. If that changes, so must the table.
SEED, EVENTS = 42, 1000


@pytest.fixture(scope="module")
def measured():
    world = generate_batch(n_events=EVENTS, seed=SEED)
    cf = Counterfactual(world)
    results = {s.name: cf.run(s) for s in (FixedT3(), BlindRetry(), GatedAgent())}
    at_risk = sum((e.amount for e in world.events), Decimal("0"))
    return results, at_risk


def _normalise(text: str) -> str:
    """Strip thousands separators and unify minus signs.

    The README renders 4,652, uses a typographic minus (U+2212), and writes
    negative money as "-Rs 239,741" with the currency symbol BETWEEN the sign and
    the digits. Comparing raw strings made this fail on formatting rather than on
    facts, which is how a test gets ignored instead of fixed.
    """
    for old, new in ((",", ""), ("−", "-"), ("–", "-"), ("₹", ""), ("Rs ", "")):
        text = text.replace(old, new)
    return text


README_N = _normalise(README)


def _in_readme(value: Decimal | int) -> bool:
    """Is this figure present in the README, ignoring presentation?"""
    rendered = f"{value:,.0f}" if isinstance(value, Decimal) else str(value)
    return _normalise(rendered) in README_N


def test_amount_at_risk_matches(measured):
    _results, at_risk = measured
    assert _in_readme(at_risk), f"README does not state Rs {at_risk:,.0f} at risk"


@pytest.mark.parametrize("strategy", ["fixed_t3", "blind_retry", "gated_agent"])
def test_recovered_amounts_match(measured, strategy):
    results, _ = measured
    assert _in_readme(results[strategy].amount_recovered)


@pytest.mark.parametrize("strategy", ["fixed_t3", "blind_retry", "gated_agent"])
def test_net_values_match(measured, strategy):
    results, _ = measured
    assert _in_readme(results[strategy].net_value)


@pytest.mark.parametrize("strategy", ["blind_retry", "gated_agent"])
def test_attempt_and_contact_counts_match(measured, strategy):
    results, _ = measured
    assert _in_readme(results[strategy].attempts_spent)
    assert _in_readme(results[strategy].contacts_sent)


def test_violation_counts_match(measured):
    results, _ = measured
    assert _in_readme(results["blind_retry"].policy_violations)
    assert results["gated_agent"].policy_violations == 0
    assert "**0**" in README, "README must state zero violations in the table"


def test_the_headline_delta_is_arithmetically_correct(measured):
    """The two numbers the pitch leads with."""
    results, _ = measured
    blind, gated = results["blind_retry"], results["gated_agent"]

    more = blind.amount_recovered - gated.amount_recovered
    worth_less = gated.net_value - blind.net_value

    assert _in_readme(more), f"README should state blind retry recovers Rs {more:,.0f} more"
    assert _in_readme(worth_less), f"README should state it is worth Rs {worth_less:,.0f} less"


def test_test_count_in_docs_is_not_stale():
    """A README claiming more tests than exist is the cheapest possible own-goal."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    assert match, proc.stdout[-500:]
    actual = int(match.group(1))

    claimed = [int(n) for n in re.findall(r"(\d+) tests", README + ARCHITECTURE)]
    assert claimed, "docs no longer state a test count"
    for n in claimed:
        assert abs(n - actual) <= 5, f"docs claim {n} tests, suite collects {actual}"


def test_tier_split_is_present_and_ordered():
    """Tier A must lead. Leading with the net-value gap invites 'where does that
    number come from?' as the first question instead of the last."""
    a = README.index("Tier A")
    b = README.index("Tier B")
    assert a < b, "Tier B is presented before Tier A"
    assert "No cost parameter can move them" in README


def test_readme_publishes_the_failure_boundary():
    """The place our own claim breaks must be in the README, not only in the
    sensitivity appendix."""
    assert "blind retry wins" in README
    assert "docs/sensitivity.md" in README


def test_readme_discloses_the_known_limitations():
    for disclosure in (
        "We cut the LLM",
        "Tamper-evident, not tamper-proof",
        "Simulated under stated priors",
        "go to a human",
    ):
        assert disclosure in README, f"README no longer discloses: {disclosure}"
