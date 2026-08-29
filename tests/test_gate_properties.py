"""Property-based invariants for the policy gate.

The example-based tests prove the gate behaves correctly on the cases I thought
of. These prove it behaves correctly on cases I did not — Hypothesis generates
hundreds of event shapes per run, including the degenerate ones (zero amounts,
attempt counts already at the cap, revoked consent on a terminal decline, an
authorisation that expired before it was created).

This is what converts "fines are structurally impossible" from a sentence in a
README into something runnable. The invariants below are the actual safety
claims of the submission, stated as universally-quantified properties:

    for ANY event, and ANY set of candidate actions:
      - nothing permitted was also blocked
      - no terminal decline is ever retried
      - no action touches a customer who withdrew consent
      - no money is pursued against a dead obligation

    for ANY sequence of events:
      - merchant-initiated retries never exceed the cap
      - outbound contacts never exceed the weekly cap
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from due.core.actions import enumerate_actions
from due.core.counters import AttemptCounter
from due.core.diagnose import DIAGNOSIS_TABLE, BatchContext, default_diagnoser
from due.core.models import (
    TERMINAL_FOR_RETRY,
    ActionType,
    CandidateAction,
    Diagnosis,
    EventType,
    GateVerdict,
    Instrument,
    RiskEvent,
    RootCause,
)
from due.core.pipeline import RecoveryPipeline
from due.core.policy.engine import UNGATED_ACTIONS, GateContext, PolicyEngine

ENGINE = PolicyEngine()
DIAGNOSER = default_diagnoser()

RETRY_ACTIONS = frozenset({ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED})
CONTACT_ACTIONS = frozenset(
    {
        ActionType.NUDGE_PAYMENT_LINK,
        ActionType.REQUEST_INSTRUMENT_SWITCH,
        ActionType.REQUEST_VPA_REPAIR,
        ActionType.WINBACK_SEQUENCE,
    }
)

T0 = datetime(2026, 8, 15, 12, 0)

# Independent of rules.yaml on purpose. Reading the cap from the config under
# test makes an assertion tautological — loosen the config and the test loosens
# with it. A mutation raising max_retries 3 -> 99 passed the suite until these
# hardcoded ceilings existed.
HARD_RETRY_CEILING = 3
HARD_CONTACT_CEILING = 2

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

reason_codes = st.sampled_from(sorted(DIAGNOSIS_TABLE)) | st.sampled_from(
    ["card_declined", "payment_failed", "payment_declined"]
)


@st.composite
def risk_events(draw) -> RiskEvent:
    """Deliberately wider than the simulator's distribution.

    Includes shapes the generator would never produce — a zero-rupee at-risk
    amount, an instrument already at its 30-day cap, an expired authorisation on
    a live event — because the gate must hold on those too.
    """
    event_type = draw(st.sampled_from(list(EventType)))
    has_error = event_type in (EventType.FAILED_PAYMENT, EventType.FAILED_MANDATE, EventType.HALTED_SUBSCRIPTION)
    occurred = T0 - timedelta(hours=draw(st.integers(0, 400)))

    return RiskEvent(
        event_id=f"evt_{draw(st.integers(0, 10**6)):07d}",
        batch_id="prop",
        occurred_at=occurred,
        event_type=event_type,
        amount=Decimal(str(draw(st.integers(0, 500_000)))),
        instrument=draw(st.sampled_from(list(Instrument))),
        instrument_token=f"tok_{draw(st.integers(0, 50))}",
        issuer=draw(st.sampled_from(["HDFC", "SBI", "ICICI", "AXIS"])),
        customer_id=f"cust_{draw(st.integers(0, 40))}",
        # Small pool ON PURPOSE. With a wide range these never collide, the
        # per-payment retry cap never binds, and the sequence invariant below
        # passes vacuously. A mutation test caught exactly that.
        payment_id=f"pay_{draw(st.integers(0, 6))}",
        error_reason=draw(reason_codes) if has_error else None,
        prior_attempts_24h=draw(st.integers(0, 12)),
        prior_attempts_30d=draw(st.integers(0, 20)),
        contacts_this_week=draw(st.integers(0, 6)),
        consent_active=draw(st.booleans()),
        obligation_valid=draw(st.booleans()),
        auth_expires_at=(
            occurred + timedelta(days=draw(st.integers(-2, 6)))
            if event_type in (EventType.UNCAPTURED_AUTH, EventType.LATE_AUTHORIZATION)
            else None
        ),
        customer_ltv=Decimal(str(draw(st.integers(0, 200_000)))),
        customer_success_days=draw(st.lists(st.integers(1, 28), max_size=5)),
    )


@st.composite
def retryable_events(draw) -> RiskEvent:
    """Events that WILL produce a retry, sharing a tiny payment-id pool.

    The general strategy above is deliberately hostile — roughly three quarters
    of what it draws has withdrawn consent or a dead obligation, so almost
    nothing survives to a retry and the per-payment accumulation cap never
    binds. That made the headline invariant vacuous: a mutation raising the cap
    3 -> 99 passed it, because no payment ever reached even 2 retries.

    This strategy exists solely to drive accumulation. Everything is valid, the
    cause is retryable, the instrument is not a mandate (so no RBI deferral),
    and the amount is large enough to clear the value floor.
    """
    occurred = T0 - timedelta(hours=draw(st.integers(1, 72)))
    return RiskEvent(
        event_id=f"evt_{draw(st.integers(0, 10**6)):07d}",
        batch_id="prop",
        occurred_at=occurred,
        event_type=EventType.FAILED_PAYMENT,
        amount=Decimal(str(draw(st.integers(2_000, 40_000)))),
        instrument=Instrument.CARD,
        instrument_token=f"tok_{draw(st.integers(0, 3))}",
        issuer="HDFC",
        customer_id=f"cust_{draw(st.integers(0, 3))}",
        payment_id=f"pay_{draw(st.integers(0, 2))}",
        error_reason=draw(
            st.sampled_from(["gateway_technical_error", "insufficient_funds", "payment_timed_out"])
        ),
        prior_attempts_24h=0,
        prior_attempts_30d=0,
        contacts_this_week=0,
        consent_active=True,
        obligation_valid=True,
        customer_ltv=Decimal("50000"),
        customer_success_days=[],
    )


def _evaluate(event: RiskEvent, counters: AttemptCounter | None = None):
    ctx = BatchContext.from_events([event])
    diagnosis = DIAGNOSER.diagnose(event, ctx)
    candidates = enumerate_actions(event, diagnosis, T0)
    gate_ctx = GateContext(now=T0, counters=counters or AttemptCounter())
    return diagnosis, candidates, ENGINE.evaluate(event, candidates, gate_ctx, diagnosis)


PROP = settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ---------------------------------------------------------------------------
# Core gate invariants
# ---------------------------------------------------------------------------


@given(event=risk_events())
@PROP
def test_permitted_is_always_a_subset_of_candidates(event):
    """The gate filters. It must never invent an action."""
    _d, candidates, result = _evaluate(event)
    types = [c.action_type for c in candidates]
    for action in result.permitted:
        assert action.action_type in types


@given(event=risk_events())
@PROP
def test_nothing_permitted_was_also_blocked(event):
    """The central safety property.

    If an action can appear in `permitted` while carrying a BLOCK verdict, then a
    learner choosing from `permitted` could execute a blocked action — and the
    entire gate-before-learner argument collapses.
    """
    _d, _c, result = _evaluate(event)
    blocked_types = {
        g.applies_to for g in result.gate_results if g.verdict is GateVerdict.BLOCK
    }
    for action in result.permitted:
        assert action.action_type not in blocked_types


@given(event=risk_events())
@PROP
def test_terminal_declines_are_never_retried(event):
    """Retrying an expired card or a fraud-flagged payment is what produces
    Mastercard Excessive Attempts fees and card-testing classification."""
    diagnosis, _c, result = _evaluate(event)
    if diagnosis.root_cause not in TERMINAL_FOR_RETRY:
        return
    for action in result.permitted:
        assert action.action_type not in RETRY_ACTIONS
    for deferred in result.deferred:
        assert deferred.action.action_type not in RETRY_ACTIONS


@given(event=risk_events())
@PROP
def test_withdrawn_consent_permits_no_debit_and_no_contact(event):
    """Capture is the documented exemption — it completes an authorisation the
    customer already granted. Everything else must stop."""
    assume(not event.consent_active)
    _d, _c, result = _evaluate(event)
    for action in list(result.permitted) + [d.action for d in result.deferred]:
        assert action.action_type not in RETRY_ACTIONS
        assert action.action_type not in CONTACT_ACTIONS


@given(event=risk_events())
@PROP
def test_dead_obligations_are_never_pursued(event):
    """Collecting against a cancelled order buys a refund and a dispute."""
    assume(not event.obligation_valid)
    _d, _c, result = _evaluate(event)
    for action in list(result.permitted) + [d.action for d in result.deferred]:
        assert action.action_type in UNGATED_ACTIONS


@given(event=risk_events())
@PROP
def test_expired_authorisations_are_never_captured(event):
    assume(event.auth_expires_at is not None)
    assume(T0 >= event.auth_expires_at)
    _d, _c, result = _evaluate(event)
    for action in result.permitted:
        assert action.action_type is not ActionType.CAPTURE_AUTHORIZED


@given(event=risk_events())
@PROP
def test_network_attempt_caps_are_respected_at_the_boundary(event):
    """An instrument already at its network cap gets no further attempts."""
    assume(event.prior_attempts_24h >= 9 or event.prior_attempts_30d >= 15)
    _d, _c, result = _evaluate(event)
    for action in list(result.permitted) + [d.action for d in result.deferred]:
        assert action.action_type not in RETRY_ACTIONS


@given(event=risk_events())
@PROP
def test_contact_cap_is_respected_at_the_boundary(event):
    assume(event.contacts_this_week >= 2)
    _d, _c, result = _evaluate(event)
    for action in result.permitted:
        assert action.action_type not in CONTACT_ACTIONS


@given(event=risk_events())
@PROP
def test_mandate_debits_never_execute_inside_the_rbi_window(event):
    """A mandate debit with no prior notice must be deferred, never permitted."""
    assume(event.instrument in (Instrument.EMANDATE, Instrument.UPI_AUTOPAY))
    _d, _c, result = _evaluate(event)
    for action in result.permitted:
        assert action.action_type not in RETRY_ACTIONS


@given(event=risk_events())
@PROP
def test_every_gate_result_is_attributable(event):
    """Every verdict must name a rule and cite a source, or the audit trail is
    an unfalsifiable list of assertions."""
    _d, _c, result = _evaluate(event)
    for gate in result.gate_results:
        assert gate.rule_id
        assert gate.source
        assert gate.rationale


@given(event=risk_events())
@PROP
def test_evaluation_is_pure(event):
    """Evaluating twice with the same state yields the same verdicts.

    A gate whose answer depends on hidden mutable state cannot be replayed, and
    an audit trail you cannot replay is not evidence.
    """
    counters = AttemptCounter()
    first = _evaluate(event, counters)[2]
    second = _evaluate(event, counters)[2]
    assert [a.action_type for a in first.permitted] == [
        a.action_type for a in second.permitted
    ]
    assert [(g.rule_id, g.verdict) for g in first.gate_results] == [
        (g.rule_id, g.verdict) for g in second.gate_results
    ]


# ---------------------------------------------------------------------------
# Sequence invariants — the headline claim
# ---------------------------------------------------------------------------


@given(events=st.lists(retryable_events(), min_size=8, max_size=60))
@settings(max_examples=80, deadline=None, suppress_health_check=list(HealthCheck))
def test_merchant_retry_cap_holds_over_any_event_sequence(events):
    """THE invariant: no payment ever receives more merchant-initiated retries
    than the cap, for any sequence of events in any order.

    This is the claim the video makes. Asserting it over generated sequences
    rather than one fixture is the difference between showing it works and
    showing it cannot fail.
    """
    pipeline = RecoveryPipeline()
    pipeline.run(events)

    cap = ENGINE.invariant_max_merchant_retries()
    for payment_id, count in pipeline.counters._merchant_retries.items():
        assert count <= cap, f"{payment_id}: {count} retries against cap {cap}"
        assert count <= HARD_RETRY_CEILING, (
            f"{payment_id}: {count} retries exceeds hardcoded ceiling "
            f"{HARD_RETRY_CEILING}; config claims {cap}"
        )


@given(events=st.lists(risk_events(), min_size=1, max_size=60))
@settings(max_examples=60, deadline=None, suppress_health_check=list(HealthCheck))
def test_contact_cap_holds_over_any_event_sequence(events):
    pipeline = RecoveryPipeline()
    pipeline.run(events)

    for customer_id, timestamps in pipeline.counters._contacts.items():
        # Prior contacts observed at ingestion count against the same cap, so
        # the system's own contribution is what must stay inside it.
        assert len(timestamps) <= HARD_CONTACT_CEILING, (
            f"{customer_id}: {len(timestamps)} contacts sent"
        )


@given(events=st.lists(risk_events(), min_size=1, max_size=40))
@settings(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
def test_every_decision_is_recorded_and_the_chain_verifies(events):
    """No sequence produces an unrecorded decision or a broken chain."""
    pipeline = RecoveryPipeline()
    result = pipeline.run(events)

    assert len(result.decisions) == len(events)
    assert result.ledger.verify().ok


def test_configured_caps_stay_within_hardcoded_safe_bounds():
    """Config sanity, separate from enforcement.

    The sequence tests prove the gate ENFORCES whatever the config says. This
    proves the config says something safe. Both are needed — a correctly
    enforced bad limit is still a bad limit.
    """
    assert ENGINE.invariant_max_merchant_retries() <= HARD_RETRY_CEILING
    assert not ENGINE.check_invariants()


@given(events=st.lists(retryable_events(), min_size=20, max_size=60))
@settings(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))
def test_the_retry_cap_actually_binds(events):
    """Guards the guard.

    An invariant test that never reaches the boundary proves nothing. This
    asserts the boundary is genuinely exercised — that at least one payment in a
    sequence of retryable events accumulates more than one merchant retry, so
    the cap has something to cap.
    """
    pipeline = RecoveryPipeline()
    pipeline.run(events)
    counts = list(pipeline.counters._merchant_retries.values())
    assume(counts)
    assert max(counts) >= 2, (
        "no payment accumulated multiple retries; the cap invariant above is "
        "passing vacuously"
    )
