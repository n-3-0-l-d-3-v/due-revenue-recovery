"""Ledger integrity tests.

These are proof artefacts, not hygiene. The submission claims "every decision is
recorded in a tamper-evident trail you can verify yourself". These tests are what
turns that from a sentence in a README into something a judge can run.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from recoup.core.ledger import GENESIS, Ledger
from recoup.core.models import (
    CandidateAction,
    DeclineClass,
    DecisionRecord,
    Diagnosis,
    EventType,
    GateResult,
    GateVerdict,
    Instrument,
    ActionType,
    RevalidationEntry,
    RiskEvent,
    RootCause,
)

T0 = datetime(2026, 8, 20, 12, 0, 0)


def make_event(i: int) -> RiskEvent:
    return RiskEvent(
        event_id=f"evt_{i}",
        batch_id="batch_test",
        occurred_at=T0 + timedelta(minutes=i),
        event_type=EventType.FAILED_PAYMENT,
        amount=Decimal("1500.00") + Decimal(i),
        instrument=Instrument.CARD,
        instrument_token=f"tok_{i}",
        issuer="HDFC",
        customer_id=f"cust_{i}",
        payment_id=f"pay_{i}",
        error_reason="insufficient_funds",
    )


def make_decision(i: int, blocked: bool = False) -> DecisionRecord:
    return DecisionRecord(
        decision_id=f"dec_{i}",
        batch_id="batch_test",
        event_id=f"evt_{i}",
        decided_at=T0 + timedelta(minutes=i),
        event=make_event(i),
        diagnosis=Diagnosis(
            root_cause=RootCause.INSUFFICIENT_FUNDS,
            decline_class=DeclineClass.BUSINESS,
            confidence=0.95,
            evidence_ref="rzp:cards#insufficient_funds",
        ),
        candidates=[CandidateAction(action_type=ActionType.RETRY_SCHEDULED)],
        gate_results=[
            GateResult(
                rule_id="network.merchant_retry_cap",
                verdict=GateVerdict.BLOCK if blocked else GateVerdict.PASS,
                rationale="3/3 merchant-initiated retries" if blocked else "0/3 retries",
                source="Recoup policy",
                applies_to=ActionType.RETRY_SCHEDULED,
            )
        ],
        permitted=[] if blocked else [CandidateAction(action_type=ActionType.RETRY_SCHEDULED)],
    )


def build_ledger(n: int = 5) -> Ledger:
    ledger = Ledger()
    for i in range(n):
        ledger.append(make_decision(i, blocked=(i % 3 == 0)))
    return ledger


# ---------------------------------------------------------------------------
# Chain integrity
# ---------------------------------------------------------------------------


def test_clean_chain_verifies():
    ledger = build_ledger()
    result = ledger.verify()
    assert result.ok, str(result)
    assert result.entries_checked == 5


def test_first_entry_commits_to_genesis():
    ledger = build_ledger(1)
    assert ledger.entries[0].prev_hash == GENESIS


def test_each_entry_commits_to_predecessor():
    ledger = build_ledger()
    entries = ledger.entries
    for prev, curr in zip(entries, entries[1:]):
        assert curr.prev_hash == prev.hash


def test_head_tracks_last_entry():
    ledger = build_ledger()
    assert ledger.head == ledger.entries[-1].hash


# ---------------------------------------------------------------------------
# Tamper detection — the demo
# ---------------------------------------------------------------------------


def test_content_mutation_is_detected():
    """Alter a recorded amount after sealing. Verification must localise it."""
    ledger = build_ledger()
    assert ledger.verify().ok

    ledger.entries[2].event.amount = Decimal("999999.00")
    # entries returns copies of the list, not of the objects, so mutate in place
    ledger._entries[2].event.amount = Decimal("999999.00")

    result = ledger.verify()
    assert not result.ok
    assert any(v.seq == 2 and "content hash mismatch" in v.detail for v in result.violations)


def test_changing_a_gate_verdict_is_detected():
    """The attack that matters: rewriting a BLOCK into a PASS to hide a violation."""
    ledger = build_ledger()
    ledger._entries[0].gate_results[0].verdict = GateVerdict.PASS

    result = ledger.verify()
    assert not result.ok
    assert result.violations[0].seq == 0


def test_deletion_is_detected():
    ledger = build_ledger()
    del ledger._entries[2]

    result = ledger.verify()
    assert not result.ok
    assert any("broken link" in v.detail for v in result.violations)


def test_reorder_is_detected():
    ledger = build_ledger()
    ledger._entries[1], ledger._entries[3] = ledger._entries[3], ledger._entries[1]

    result = ledger.verify()
    assert not result.ok
    assert any("broken link" in v.detail for v in result.violations)


def test_append_after_tamper_still_fails():
    """A forger who alters an entry and keeps writing does not repair the chain."""
    ledger = build_ledger()
    ledger._entries[1].event.amount = Decimal("1.00")
    ledger.append(make_decision(99))

    assert not ledger.verify().ok


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_jsonl_roundtrip_preserves_verification(tmp_path):
    ledger = build_ledger()
    path = ledger.to_jsonl(tmp_path / "ledger.jsonl")

    reloaded = Ledger.from_jsonl(path)
    assert reloaded.verify().ok
    assert len(reloaded) == len(ledger)
    assert reloaded.head == ledger.head


def test_tampered_file_fails_on_load(tmp_path):
    """Editing the file on disk must not survive a reload.

    This is why from_jsonl bypasses append(): re-sealing on load would silently
    launder a forged file into a valid chain.
    """
    ledger = build_ledger()
    path = ledger.to_jsonl(tmp_path / "ledger.jsonl")

    text = path.read_text(encoding="utf-8")
    assert '"1500.00"' in text
    # Alter a schema-valid field, so the forgery survives deserialisation and must
    # be caught by the hash chain rather than incidentally by type validation.
    path.write_text(text.replace('"1500.00"', '"15.00"', 1), encoding="utf-8")

    result = Ledger.from_jsonl(path).verify()
    assert not result.ok
    assert any("content hash mismatch" in v.detail for v in result.violations)


# ---------------------------------------------------------------------------
# Replay determinism
# ---------------------------------------------------------------------------


def test_replay_is_byte_identical():
    """Same inputs, same chain. Without this, 'replayable audit trail' is a slogan."""
    a, b = build_ledger(), build_ledger()

    assert a.head == b.head
    assert [e.hash for e in a.entries] == [e.hash for e in b.entries]


def test_replay_differs_when_input_differs():
    """The chain must actually be sensitive to content, not merely stable."""
    a = build_ledger()
    b = Ledger()
    for i in range(5):
        d = make_decision(i, blocked=(i % 3 == 0))
        if i == 4:
            d.event.amount = Decimal("2.00")
        b.append(d)

    assert a.head != b.head


# ---------------------------------------------------------------------------
# Revalidation entries
# ---------------------------------------------------------------------------


def test_revalidation_chains_alongside_decisions():
    """A sealed decision cannot be edited, so re-validation is its own entry."""
    ledger = Ledger()
    ledger.append(make_decision(0))
    ledger.append(
        RevalidationEntry(
            entry_id="rev_0",
            decision_id="dec_0",
            event_id="evt_0",
            at=T0 + timedelta(hours=24),
            approved=False,
            blocking_rules=["consent.active"],
            changed_since_decision=["consent True -> False"],
        )
    )

    assert ledger.verify().ok
    assert len(ledger.decisions()) == 1
    assert len(ledger.revalidations()) == 1
    assert ledger.revalidations()[0].prev_hash == ledger.decisions()[0].hash


def test_compliance_certificate_reports_blocks_and_head():
    ledger = build_ledger()
    ledger.append(
        RevalidationEntry(
            entry_id="rev_0",
            decision_id="dec_0",
            event_id="evt_0",
            at=T0,
            approved=False,
            blocking_rules=["consent.active"],
            changed_since_decision=["consent True -> False"],
        )
    )

    cert = ledger.compliance_certificate()
    assert cert["chain_verified"] is True
    assert cert["chain_head"] == ledger.head
    assert cert["revalidations_rejected"] == 1
    assert cert["blocks_by_rule"]["network.merchant_retry_cap"] == 2


def test_certificate_flags_a_broken_chain():
    ledger = build_ledger()
    ledger._entries[1].event.amount = Decimal("0.01")

    cert = ledger.compliance_certificate()
    assert cert["chain_verified"] is False
    assert cert["violations"]
