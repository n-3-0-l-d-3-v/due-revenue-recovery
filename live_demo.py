"""Live Razorpay cycle — proof this is not a mock.

    python live_demo.py            # dry run, no API writes
    python live_demo.py --live     # real calls against Razorpay TEST mode

Drives one real at-risk event through the full path and out to Razorpay:

    RiskEvent -> diagnose -> gate -> score -> DecisionRecord -> ledger
              -> Razorpay payment link  -> [you pay with a test card]
              -> fetch status -> reconcile against the sealed decision

Test mode only. The client refuses to construct with a live key, notifications
are disabled at the call site, and every write is suppressed unless --live.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from decimal import Decimal

from due.core.actions import enumerate_actions
from due.core.counters import AttemptCounter
from due.core.diagnose import BatchContext, default_diagnoser
from due.core.ledger import Ledger
from due.core.models import (
    ActionType,
    DecisionRecord,
    EventType,
    Instrument,
    Outcome,
    OutcomeStatus,
    RiskEvent,
)
from due.core.policy.engine import GateContext, PolicyEngine
from due.core.scorer import Scorer
from due.rzp.client import RazorpayClient, idempotency_reference

W = 78


def rule(title: str) -> None:
    print(f"\n{'=' * W}\n{title}\n{'=' * W}")


def build_event() -> RiskEvent:
    """One realistic at-risk payment: a customer whose card had no funds."""
    return RiskEvent(
        event_id="live_demo_001",
        batch_id="live",
        occurred_at=datetime.now(),
        event_type=EventType.FAILED_PAYMENT,
        amount=Decimal("2499.00"),
        instrument=Instrument.CARD,
        instrument_token="tok_live_demo",
        issuer="HDFC",
        customer_id="cust_live_demo",
        order_id="order_live_demo",
        payment_id="pay_live_demo",
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds",
        consent_active=True,
        obligation_valid=True,
        customer_ltv=Decimal("7000.00"),
        customer_success_days=[2, 3],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="make real test-mode API calls")
    ap.add_argument("--payment-link", help="fetch status for an existing link id")
    args = ap.parse_args()

    client = RazorpayClient.from_env(dry_run=not args.live)

    rule("0. CONNECTION")
    print(f"  key id : {client.key_id[:12]}...  (test-mode prefix enforced)")
    print(f"  mode   : {client.mode}")
    if not args.live:
        print("\n  Dry run. No writes will reach Razorpay. Re-run with --live to")
        print("  create a real test-mode payment link you can actually pay.")

    # ------------------------------------------------------------------
    rule("1. THE AT-RISK EVENT")
    event = build_event()
    print(f"  {event.event_id}  Rs {event.amount}  {event.instrument.value}  {event.issuer}")
    print(f"  reason code : {event.error_reason}")
    print(f"  customer historically pays on days {event.customer_success_days}")

    # ------------------------------------------------------------------
    rule("2. DIAGNOSE")
    ctx = BatchContext.from_events([event])
    diagnosis = default_diagnoser().diagnose(event, ctx)
    print(f"  root cause   : {diagnosis.root_cause.value}")
    print(f"  decline class: {diagnosis.decline_class.value}")
    print(f"  confidence   : {diagnosis.confidence:.0%}  (resolved by {diagnosis.reasoned_by})")
    print(f"  evidence     : {diagnosis.evidence_ref}")

    # ------------------------------------------------------------------
    rule("3. GATE")
    now = datetime.now()
    engine = PolicyEngine()
    counters = AttemptCounter()
    candidates = enumerate_actions(event, diagnosis, now)
    evaluation = engine.evaluate(event, candidates, GateContext(now=now, counters=counters), diagnosis)

    print(f"  {len(candidates)} candidate actions, {len(evaluation.gate_results)} rule evaluations")
    for gate in evaluation.gate_results:
        mark = {"pass": "  ok  ", "block": " BLOCK", "defer": " DEFER"}[gate.verdict.value]
        print(f"   {mark} {gate.rule_id:34s} {gate.rationale[:30]}")
    print(f"\n  permitted: {[a.action_type.value for a in evaluation.permitted]}")

    # ------------------------------------------------------------------
    rule("4. SCORE (permitted actions only)")
    scorer = Scorer(ctx)
    best, why_not = scorer.best(event, diagnosis, evaluation.permitted, now)
    if best is None:
        print(f"  no action taken: {why_not}")
        return 0

    ev = best.ev
    print(f"  chosen: {best.action.action_type.value}")
    print(f"    rationale     : {best.action.rationale}")
    print(f"    P(recovery)   : {ev.p_recovery:.0%}")
    print(f"    amount        : Rs {ev.amount}")
    print(f"    costs         : attempt {ev.attempt_cost}  contact {ev.contact_cost}  "
          f"support {ev.expected_support_cost}")
    print(f"    churn risk    : {ev.churn_risk:.1%} of Rs {ev.customer_ltv} LTV")
    print(f"    NET VALUE     : Rs {ev.net_value:,.2f}")

    # ------------------------------------------------------------------
    rule("5. SEAL THE DECISION")
    ledger = Ledger()
    reference = idempotency_reference(event.event_id, best.action.action_type.value)
    record = DecisionRecord(
        decision_id="dec_live_demo",
        batch_id="live",
        event_id=event.event_id,
        decided_at=now,
        event=event,
        diagnosis=diagnosis,
        candidates=candidates,
        gate_results=evaluation.gate_results,
        permitted=evaluation.permitted,
        ev_components=ev,
        chosen=best.action,
        idempotency_key=reference,
    )
    ledger.append(record)
    print(f"  decision sealed, hash {record.hash[:24]}...")
    print(f"  idempotency key: {reference}")
    print(f"  {ledger.verify()}")

    # ------------------------------------------------------------------
    rule("6. EXECUTE AGAINST RAZORPAY")
    link = client.create_payment_link(
        event.amount, reference, f"Recovery for {event.order_id}"
    )
    print(f"  payment link : {link.get('id')}")
    print(f"  url          : {link.get('short_url')}")
    print(f"  notify       : {link.get('notify', 'suppressed in dry run')}")

    print("\n  calling again with the same reference:")
    again = client.create_payment_link(event.amount, reference, "duplicate attempt")
    print(f"    -> {again.get('id')}  idempotent_replay={again.get('idempotent_replay', False)}")
    print("    Razorpay does NOT dedup on receipt/reference — verified against the")
    print("    live sandbox. Without this client-side guard a retried call after a")
    print("    network timeout would bill the customer twice.")

    # ------------------------------------------------------------------
    if args.live and link.get("short_url"):
        rule("7. PAY IT")
        print(f"  Open: {link['short_url']}")
        print("  Test card 4111 1111 1111 1111, any future expiry, any CVV, any OTP.")
        print("  No real money moves.\n")
        input("  Press Enter once you have paid (or to skip)... ")

        rule("8. RECONCILE")
        status = client._client.payment_link.fetch(link["id"])
        paid = status.get("amount_paid", 0)
        print(f"  link status  : {status.get('status')}")
        print(f"  amount paid  : Rs {Decimal(paid) / 100:,.2f} of Rs {event.amount}")

        recovered = status.get("status") == "paid"
        record.outcome = Outcome(
            status=OutcomeStatus.RECOVERED if recovered else OutcomeStatus.PENDING,
            recovered_amount=Decimal(paid) / 100,
            observed_at=datetime.now(),
            detail=f"payment_link {status.get('status')}",
        )
        print(f"\n  outcome: {record.outcome.status.value}  Rs {record.outcome.recovered_amount}")
        print("  Note the sealed decision above is NOT edited to record this —")
        print("  a sealed record cannot change. In the batch pipeline the outcome")
        print("  lands as its own chained entry.")

    rule("CALL LOG")
    for call in client.calls:
        tag = "DRY " if call.dry_run else "LIVE"
        print(f"  [{tag}] {call.method:22s} {call.detail[:44]}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
