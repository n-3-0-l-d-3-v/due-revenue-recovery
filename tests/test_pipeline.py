"""End-to-end decision path.

The claims these tests defend are the ones the submission actually makes:
every decision is recorded with its full gate evaluation, no action escapes the
gate, the attempt-cap invariant holds across a whole batch, and refusing to act
is recorded with a reason rather than silently dropped.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from due.core.models import ActionType, GateVerdict, RootCause, TERMINAL_FOR_RETRY
from due.core.pipeline import RecoveryPipeline
from due.core.policy.engine import UNGATED_ACTIONS, PolicyEngine
from due.sim.generator import generate_batch

RETRY_ACTIONS = {ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED}


@pytest.fixture(scope="module")
def world():
    return generate_batch(n_events=1000, seed=42)


@pytest.fixture(scope="module")
def run(world):
    pipe = RecoveryPipeline()
    result = pipe.run(world.events)
    result = pipe.execute_pending(result, {e.event_id: e for e in world.events})
    return pipe, result


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_every_event_produces_exactly_one_decision(world, run):
    _pipe, result = run
    assert len(result.decisions) == len(world.events)
    assert {d.event_id for d in result.decisions} == {e.event_id for e in world.events}


def test_every_gateable_candidate_is_evaluated(run):
    """A money-moving action with no gate results would be unaudited.

    ESCALATE_HUMAN and STOP_UNCOLLECTIBLE are excluded by design — they move no
    money and contact nobody, so there is nothing to gate. See UNGATED_ACTIONS.
    """
    _pipe, result = run
    for decision in result.decisions:
        gateable = [c for c in decision.candidates if c.action_type not in UNGATED_ACTIONS]
        if gateable:
            assert decision.gate_results, f"{decision.decision_id} has no gate evaluation"


def test_gate_records_passes_not_only_blocks(run):
    """Logging only refusals proves you noticed some violations, not compliance."""
    _pipe, result = run
    verdicts = {g.verdict for d in result.decisions for g in d.gate_results}
    assert GateVerdict.PASS in verdicts
    assert GateVerdict.BLOCK in verdicts


def test_every_gate_result_cites_a_source(run):
    _pipe, result = run
    for decision in result.decisions:
        for gate in decision.gate_results:
            assert gate.source, f"{gate.rule_id} produced a verdict with no cited source"


def test_inaction_always_carries_a_reason(run):
    """Declining to act is a decision. It must be explained, not merely absent."""
    _pipe, result = run
    for decision in result.decisions:
        if decision.chosen is None:
            assert decision.not_chosen_why or decision.blocked_by or decision.deferred_until


def test_acted_decisions_carry_full_ev_and_an_idempotency_key(run):
    _pipe, result = run
    assert result.acted
    for decision in result.acted:
        assert decision.ev_components is not None
        assert decision.idempotency_key, "an action without an idempotency key can double-charge"


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------


def test_no_action_bypasses_the_gate(run):
    """The chosen action must be one the gate permitted. This is the whole
    safety argument — if it can fail, learning could route around the gate."""
    _pipe, result = run
    for decision in result.acted:
        permitted = {(a.action_type, a.execute_at) for a in decision.permitted}
        assert (decision.chosen.action_type, decision.chosen.execute_at) in permitted


def test_merchant_retry_cap_holds_across_the_whole_batch(run):
    """The headline invariant, asserted over real batch execution.

    The property-based version comes later; this is the integration-level check
    that the counters actually bind during a run rather than merely existing.
    """
    pipe, _result = run
    cap = PolicyEngine().invariant_max_merchant_retries()
    for payment_id, count in pipe.counters._merchant_retries.items():
        assert count <= cap, f"{payment_id} received {count} retries, cap is {cap}"


def test_terminal_causes_never_receive_a_retry(run):
    """Retrying an expired card or a fraud-flagged payment is what generates
    network fines and gets a merchant classified as an attacker."""
    _pipe, result = run
    for decision in result.acted:
        if decision.diagnosis.root_cause in TERMINAL_FOR_RETRY:
            assert decision.chosen.action_type not in RETRY_ACTIONS


def test_uncaptured_authorisations_are_captured_not_retried(run):
    """The bank already approved. There is nothing to retry."""
    _pipe, result = run
    seen = 0
    for decision in result.acted:
        if decision.diagnosis.root_cause is RootCause.UNCAPTURED:
            assert decision.chosen.action_type is ActionType.CAPTURE_AUTHORIZED
            seen += 1
    assert seen > 0, "batch contained no capturable authorisations to check"


def test_withdrawn_consent_blocks_debits_and_contact(run):
    """Consent withdrawal stops future debits and outbound contact.

    It does NOT stop capturing an authorisation the customer already granted —
    capture is not a new debit. See the note on consent.active in rules.yaml.
    """
    _pipe, result = run
    checked = 0
    for decision in result.decisions:
        if decision.event.consent_active or not decision.candidates:
            continue
        checked += 1
        if decision.chosen is not None:
            assert decision.chosen.action_type is ActionType.CAPTURE_AUTHORIZED, (
                f"{decision.chosen.action_type.value} fired despite withdrawn consent"
            )
    assert checked > 0


def test_capture_survives_consent_withdrawal(run):
    """The converse, asserted directly so the exemption is intentional and tested,
    not an omission someone later 'fixes' into a revenue leak."""
    _pipe, result = run
    captured = [
        d
        for d in result.acted
        if not d.event.consent_active
        and d.chosen.action_type is ActionType.CAPTURE_AUTHORIZED
    ]
    assert captured, "no revoked-consent capture in this batch to verify"


def test_invalid_obligation_is_never_pursued(run):
    """Recovering money against a cancelled order buys a refund and a dispute."""
    _pipe, result = run
    for decision in result.decisions:
        if not decision.event.obligation_valid:
            assert decision.chosen is None


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def test_batch_chain_verifies(run):
    _pipe, result = run
    assert result.ledger.verify().ok
    assert len(result.ledger) == len(result.decisions) + len(result.revalidations)


def test_batch_is_deterministic(world):
    """Same batch, same chain head. 'Replayable audit trail' means this."""
    heads = []
    for _ in range(2):
        pipe = RecoveryPipeline()
        res = pipe.run(world.events)
        pipe.execute_pending(res, {e.event_id: e for e in world.events})
        heads.append(res.ledger.head)
    assert heads[0] == heads[1]


def test_compliance_certificate_reflects_the_run(run):
    _pipe, result = run
    cert = result.ledger.compliance_certificate()
    assert cert["chain_verified"] is True
    assert cert["decisions"] == len(result.decisions)
    assert cert["blocks_by_rule"], "a run with zero gate blocks is not exercising the gate"


# ---------------------------------------------------------------------------
# Deferral and re-validation
# ---------------------------------------------------------------------------


def test_mandate_debits_are_deferred_for_the_rbi_notice_window(run):
    _pipe, result = run
    assert result.pending, "no mandate debits were deferred; the RBI rule is not firing"
    for pending in result.pending:
        assert pending.deferred_by_rule == "rbi.emandate_pre_debit_notice"
        assert pending.notice_sent_at is not None
        assert pending.scheduled_for >= pending.notice_sent_at + timedelta(hours=24)


def test_revalidation_detects_state_drift(run):
    """The point of re-validating is noticing what moved, not just re-deciding."""
    _pipe, result = run
    drifted = [r for r in result.revalidations if r.changed_since_decision]
    assert drifted, "no re-validation observed any change; the snapshot is not being compared"


def test_revalidation_rejects_when_consent_is_withdrawn(world):
    """The scenario the whole deferral mechanism exists for: a customer opts out
    after the pre-debit notification and before the debit fires."""
    pipe = RecoveryPipeline()
    result = pipe.run(world.events)
    assert result.pending

    pending = result.pending[0]
    events = {e.event_id: e for e in world.events}
    events[pending.event_id] = events[pending.event_id].model_copy(
        update={"consent_active": False}
    )

    before = len(result.revalidations)
    pipe.execute_pending(result, events)
    new = result.revalidations[before:]

    revoked = [r for r in new if r.event_id == pending.event_id]
    assert revoked, "the revoked-consent action was never re-validated"
    assert not revoked[0].approved
    assert "consent.active" in revoked[0].blocking_rules
    assert any("consent" in c for c in revoked[0].changed_since_decision)


def test_revalidation_entries_chain_after_their_decision(run):
    _pipe, result = run
    decision_ids = {d.decision_id for d in result.decisions}
    for entry in result.revalidations:
        assert entry.decision_id in decision_ids
