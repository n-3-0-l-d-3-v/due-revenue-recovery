"""Diagnosis correctness and the measurement that shaped the design.

The accuracy tests here are deliberately expressed as relationships between a
floor, an achieved score, and a ceiling — never as an absolute threshold. An
absolute number would encode one seed's luck; the relationships are the claims
the submission actually makes.
"""

from __future__ import annotations

import statistics

import pytest

from recoup.core.diagnose import (
    AMBIGUOUS_REASONS,
    DIAGNOSIS_TABLE,
    BatchContext,
    Diagnoser,
    HeuristicInferencer,
    MajorityClassInferencer,
    default_diagnoser,
    evaluate,
)
from recoup.core.models import DeclineClass, EventType, RootCause
from recoup.sim.ceiling import bayes_ceiling
from recoup.sim.generator import generate_batch

SEEDS = (42, 43, 44, 45, 46, 47, 48)


@pytest.fixture(scope="module")
def worlds():
    return {s: generate_batch(n_events=1000, seed=s) for s in SEEDS}


# ---------------------------------------------------------------------------
# Table path — lookup, not prediction
# ---------------------------------------------------------------------------


def test_every_table_row_cites_evidence():
    """A mapping with no citation is an assertion. The table's value is that it
    is checkable against Razorpay's published error docs."""
    for reason, (_cause, _cls, ref) in DIAGNOSIS_TABLE.items():
        assert ref, f"{reason} has no evidence_ref"
        assert ref.startswith("rzp:"), f"{reason} cites '{ref}', not a Razorpay doc anchor"


def test_ambiguous_reasons_are_not_in_the_table():
    """The two sets must stay disjoint, or an ambiguous code would silently
    resolve by lookup and the inference path would go dead."""
    assert not (AMBIGUOUS_REASONS & DIAGNOSIS_TABLE.keys())


def test_documented_codes_resolve_by_table_with_full_confidence(worlds):
    d = default_diagnoser()
    world = worlds[42]
    ctx = BatchContext.from_events(world.events)

    checked = 0
    for event in world.events:
        if event.error_reason not in DIAGNOSIS_TABLE:
            continue
        diagnosis = d.diagnose(event, ctx)
        assert diagnosis.reasoned_by == "table"
        assert diagnosis.confidence == 1.0
        assert diagnosis.root_cause == event.truth_root_cause
        checked += 1

    assert checked > 500, "expected the documented-code path to dominate the batch"


def test_uncaptured_events_are_not_diagnosed_as_failures(worlds):
    """An authorised-but-uncaptured payment did not fail. Treating it as a
    decline would send it down the retry path instead of the capture path."""
    d = default_diagnoser()
    world = worlds[42]
    ctx = BatchContext.from_events(world.events)

    for event in world.events:
        if event.event_type in (EventType.UNCAPTURED_AUTH, EventType.LATE_AUTHORIZATION):
            assert d.diagnose(event, ctx).root_cause is RootCause.UNCAPTURED


def test_unmapped_reason_code_escalates_rather_than_guesses(worlds):
    """A code we have never seen must reach a human, not a plausible default."""
    d = default_diagnoser()
    world = worlds[42]
    ctx = BatchContext.from_events(world.events)

    event = next(e for e in world.events if e.error_reason).model_copy(
        update={"error_reason": "some_future_code_razorpay_adds_in_2027"}
    )
    diagnosis = d.diagnose(event, ctx)
    assert diagnosis.root_cause is RootCause.AMBIGUOUS_DECLINE
    assert diagnosis.confidence == 0.0
    assert "escalate" in diagnosis.evidence_ref


# ---------------------------------------------------------------------------
# Inference path — the measurement
# ---------------------------------------------------------------------------


def test_inference_task_has_positive_headroom(worlds):
    """Regression guard on the simulator itself.

    Before instrument success history was modelled, the Bayes ceiling sat AT OR
    BELOW the majority floor on 4 of 5 seeds — the task was unlearnable by
    construction and any reported accuracy was meaningless. If a future change to
    the priors collapses the headroom again, this fails loudly rather than
    silently turning the diagnoser into an expensive coin flip.
    """
    for seed, world in worlds.items():
        report = bayes_ceiling(world)
        assert report.headroom > 0, (
            f"seed {seed}: ceiling {report.bayes_ceiling:.1%} <= floor "
            f"{report.majority_floor:.1%} — inference task is unlearnable"
        )


def test_heuristic_beats_majority_class_on_average(worlds):
    """Per-seed variance is large at n~60, so the claim is about the mean."""
    lifts = []
    for world in worlds.values():
        majority = evaluate(world.events, Diagnoser(MajorityClassInferencer()))
        heuristic = evaluate(world.events, Diagnoser(HeuristicInferencer()))
        lifts.append(heuristic.inference_accuracy - majority.inference_accuracy)

    assert statistics.mean(lifts) > 0.01, (
        f"heuristic mean lift over majority class is {statistics.mean(lifts):.1%}; "
        "it is not earning its complexity"
    )


def test_heuristic_never_exceeds_the_bayes_ceiling(worlds):
    """Sanity check on the measurement itself.

    Beating a Bayes-optimal reasoner is impossible, so if this fires the ceiling
    computation has drifted out of sync with the generator and every accuracy
    number in the submission is suspect.
    """
    for seed, world in worlds.items():
        ceiling = bayes_ceiling(world)
        achieved = evaluate(world.events, Diagnoser(HeuristicInferencer()))
        assert achieved.inference_accuracy <= ceiling.bayes_ceiling + 1e-9, (
            f"seed {seed}: heuristic {achieved.inference_accuracy:.1%} exceeds "
            f"ceiling {ceiling.bayes_ceiling:.1%}"
        )


def test_no_success_history_points_at_a_blocked_instrument(worlds):
    """The single strongest discriminator, asserted directly."""
    ctx = BatchContext.from_events(worlds[42].events)
    inferencer = HeuristicInferencer()

    event = next(
        e for e in worlds[42].events if e.error_reason in AMBIGUOUS_REASONS
    ).model_copy(update={"recent_success_count": 0, "max_recent_success_amount": None})

    cause, _confidence, why = inferencer.infer(event, ctx)
    assert cause is RootCause.INSTRUMENT_BLOCKED
    assert "no successful charge" in why


def test_larger_prior_success_rules_out_a_ceiling(worlds):
    """If a bigger charge already cleared, a per-transaction cap cannot be biting."""
    from decimal import Decimal

    ctx = BatchContext.from_events(worlds[42].events)
    inferencer = HeuristicInferencer()

    event = next(
        e for e in worlds[42].events if e.error_reason in AMBIGUOUS_REASONS
    ).model_copy(
        update={
            "amount": Decimal("1000"),
            "recent_success_count": 3,
            "max_recent_success_amount": Decimal("5000"),
        }
    )

    cause, _confidence, why = inferencer.infer(event, ctx)
    assert cause is not RootCause.LIMIT_EXCEEDED
    assert "rules out a cap" in why


def test_diagnosis_always_carries_evidence(worlds):
    """Every Diagnosis must justify itself — table anchor, inference rationale,
    or an explicit escalation note. This constraint is worth more than accuracy."""
    d = default_diagnoser()
    world = worlds[42]
    ctx = BatchContext.from_events(world.events)

    for event in world.events:
        assert d.diagnose(event, ctx).evidence_ref.strip()
