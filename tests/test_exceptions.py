"""Exception queue behaviour.

The queue's value is not that it exists — it is that it stays small enough to be
worked, contains only items a human can act on, and remembers what was already
resolved. All three are tested here, because all three are what separate an
honest exception list from a list nobody reads.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from due.core.exceptions import (
    HUMAN_REVIEW_COST,
    NO_VIABLE_ACTION_FLOOR,
    RESOLVABLE_BLOCKS,
    ExceptionQueue,
    ExceptionReason,
)
from due.core.pipeline import RecoveryPipeline
from due.sim.generator import generate_batch


@pytest.fixture(scope="module")
def batch():
    world = generate_batch(n_events=1000, seed=42)
    pipeline = RecoveryPipeline()
    result = pipeline.run(world.events)
    result = pipeline.execute_pending(result, {e.event_id: e for e in world.events})
    return world, result


@pytest.fixture
def queue(batch):
    _world, result = batch
    q = ExceptionQueue()
    q.ingest(result.decisions, result.revalidations)
    return q


# ---------------------------------------------------------------------------
# The queue is real
# ---------------------------------------------------------------------------


def test_queue_is_not_empty(queue):
    """An earlier design escalated only unmapped reason codes, which never
    occur — so the queue was permanently empty while the README claimed a
    human-in-the-loop path existed."""
    assert queue.open_items


def test_manual_rate_stays_workable(queue, batch):
    """Regression guard on volume.

    At 37% the queue was unworkable and would have been ignored in practice,
    which makes it decorative rather than a safety feature. The band below is
    wide but it will catch a change that floods or empties it.
    """
    _world, result = batch
    rate = len(queue.open_items) / len(result.decisions)
    assert 0.02 <= rate <= 0.25, f"manual rate {rate:.1%} is outside the workable band"


def test_items_are_ordered_by_priority(queue):
    priorities = [i.priority for i in queue.open_items]
    assert priorities == sorted(priorities, reverse=True)


def test_every_item_tells_an_operator_what_to_do(queue):
    for item in queue.open_items:
        assert item.summary.strip()
        assert item.suggested_action.strip()
        assert item.event_id and item.decision_id


# ---------------------------------------------------------------------------
# Only actionable things escalate
# ---------------------------------------------------------------------------


def test_settled_blocks_do_not_escalate(queue, batch):
    """A cancelled obligation stays cancelled and an expired authorisation stays
    expired. Escalating them yields items whose only resolution is
    'acknowledged' — the failure mode that turns a queue into wallpaper."""
    _world, result = batch
    escalated = {i.event_id for i in queue.open_items}

    for decision in result.decisions:
        if decision.chosen is not None or not decision.blocked_by:
            continue
        rules = {g.rule_id for g in decision.blocked_by}
        if rules & RESOLVABLE_BLOCKS:
            continue
        assert decision.event_id not in escalated or any(
            i.reason is not ExceptionReason.BLOCKED_BUT_VALUABLE
            for i in queue.open_items
            if i.event_id == decision.event_id
        )


def test_consent_blocks_do_escalate(queue):
    """Consent is the one block a human can genuinely resolve — someone can call
    and ask the customer to re-authorise."""
    blocked = [
        i for i in queue.open_items if i.reason is ExceptionReason.BLOCKED_BUT_VALUABLE
    ]
    assert blocked
    assert all("consent.active" in i.summary for i in blocked)


def test_small_amounts_are_filtered_out(queue):
    """An exception a human cannot profitably work is noise."""
    for item in queue.open_items:
        if item.reason is ExceptionReason.UNMAPPED_REASON_CODE:
            continue  # always escalated regardless of value
        assert item.priority >= HUMAN_REVIEW_COST


def test_negative_ev_only_escalates_above_the_floor(queue):
    """A correct automated write-off is not an exception."""
    for item in queue.open_items:
        if item.reason is ExceptionReason.NO_VIABLE_ACTION:
            assert item.amount >= NO_VIABLE_ACTION_FLOOR


def test_uncertain_diagnoses_are_weighted_by_stakes(queue):
    """Uncertainty only matters in proportion to the money behind it."""
    for item in queue.open_items:
        if item.reason is ExceptionReason.UNCERTAIN_DIAGNOSIS:
            assert item.priority <= item.amount


# ---------------------------------------------------------------------------
# Closure
# ---------------------------------------------------------------------------


def test_closure_survives_reingesting_the_same_batch(queue, batch):
    """The property that makes the queue usable day to day.

    Without it, an operator faces every previously-resolved item again on the
    next run and stops reading the queue entirely.
    """
    _world, result = batch
    target = queue.open_items[0]
    queue.close(target.key, by="ops", note="customer re-consented; released")

    reopened = queue.ingest(result.decisions, result.revalidations)

    assert reopened == []
    assert not queue.items[target.key].is_open
    assert target.key not in {i.key for i in queue.open_items}


def test_closure_records_who_and_why(queue):
    target = queue.open_items[0]
    at = datetime(2026, 8, 20, 9, 30)
    closed = queue.close(target.key, by="neil", note="wrote off, order cancelled", at=at)

    assert closed.closed_by == "neil"
    assert closed.closure_note == "wrote off, order cancelled"
    assert closed.closed_at == at


def test_closing_twice_is_rejected(queue):
    """Silent double-closure would corrupt the audit of who resolved what."""
    target = queue.open_items[0]
    queue.close(target.key, by="ops", note="done")
    with pytest.raises(ValueError):
        queue.close(target.key, by="someone_else", note="done again")


def test_closed_items_leave_the_open_view(queue):
    before = len(queue.open_items)
    queue.close(queue.open_items[0].key, by="ops", note="handled")
    assert len(queue.open_items) == before - 1
    assert len(queue.closed_items) == 1


def test_value_awaiting_review_tracks_open_items_only(queue):
    target = queue.open_items[0]
    before = queue.value_awaiting_review
    queue.close(target.key, by="ops", note="handled")
    assert queue.value_awaiting_review == before - target.amount


def test_rejected_revalidations_always_escalate(batch):
    """A scheduled action the world invalidated is always worth a human look,
    regardless of amount — something changed between deciding and acting."""
    world, result = batch
    events = {e.event_id: e for e in world.events}

    pipeline = RecoveryPipeline()
    fresh = pipeline.run(world.events)
    assert fresh.pending

    pending = fresh.pending[0]
    events[pending.event_id] = events[pending.event_id].model_copy(
        update={"consent_active": False}
    )
    pipeline.execute_pending(fresh, events)

    q = ExceptionQueue()
    q.ingest(fresh.decisions, fresh.revalidations)

    rejected = [
        i for i in q.open_items if i.reason is ExceptionReason.REVALIDATION_REJECTED
    ]
    assert rejected
    assert any("consent" in i.summary for i in rejected)
