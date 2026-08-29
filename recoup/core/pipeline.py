"""The decision path.

    RiskEvent -> diagnose -> enumerate -> GATE -> score (permitted only)
              -> DecisionRecord -> ledger

Deferred actions take a second pass: at their execution window the gate is re-run
against fresh state, and the outcome is written as its own chained entry rather
than folded back into the sealed decision.

Everything the system decided, refused, and why is in the ledger when this
finishes. Nothing else in the codebase writes to it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from recoup.core.actions import enumerate_actions
from recoup.core.counters import AttemptCounter
from recoup.core.diagnose import BatchContext, Diagnoser, default_diagnoser
from recoup.core.ledger import Ledger
from recoup.core.models import (
    ActionType,
    DecisionRecord,
    RevalidationEntry,
    RiskEvent,
)
from recoup.core.policy.engine import GateContext, PendingAction, PolicyEngine
from recoup.core.scorer import Scorer

# Actions that consume an authorisation attempt against the network caps.
_ATTEMPT_ACTIONS = frozenset({ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED})


@dataclass
class BatchResult:
    ledger: Ledger
    decisions: list[DecisionRecord] = field(default_factory=list)
    pending: list[PendingAction] = field(default_factory=list)
    revalidations: list[RevalidationEntry] = field(default_factory=list)

    @property
    def acted(self) -> list[DecisionRecord]:
        return [d for d in self.decisions if d.chosen is not None]

    @property
    def blocked(self) -> list[DecisionRecord]:
        return [d for d in self.decisions if d.blocked_by]

    @property
    def declined_on_value(self) -> list[DecisionRecord]:
        return [
            d for d in self.decisions if d.chosen is None and d.not_chosen_why and not d.blocked_by
        ]

    def summary(self) -> dict:
        return {
            "decisions": len(self.decisions),
            "acted": len(self.acted),
            "blocked_by_gate": len(self.blocked),
            "declined_on_value": len(self.declined_on_value),
            "deferred": len(self.pending),
            "revalidations": len(self.revalidations),
            "revalidations_rejected": sum(1 for r in self.revalidations if not r.approved),
            "ledger_entries": len(self.ledger),
            "chain_verified": self.ledger.verify().ok,
        }


class RecoveryPipeline:
    def __init__(
        self,
        engine: PolicyEngine | None = None,
        diagnoser: Diagnoser | None = None,
        ledger: Ledger | None = None,
    ) -> None:
        self.engine = engine or PolicyEngine()
        self.diagnoser = diagnoser or default_diagnoser()
        self.ledger = ledger or Ledger()
        self.counters = AttemptCounter()

    def run(self, events: list[RiskEvent], now: datetime | None = None) -> BatchResult:
        now = now or datetime(2026, 8, 15, 10, 0)
        ctx = BatchContext.from_events(events)
        scorer = Scorer(ctx)
        result = BatchResult(ledger=self.ledger)

        for event in events:
            # Decide shortly after the failure, not at one fixed instant for a
            # batch spanning a month. A single batch clock made every event older
            # than that instant look like an expired authorisation.
            decided_at = max(now, event.occurred_at + timedelta(hours=1))
            gate_ctx = GateContext(now=decided_at, counters=self.counters)

            diagnosis = self.diagnoser.diagnose(event, ctx)
            candidates = enumerate_actions(event, diagnosis, decided_at)

            evaluation = self.engine.evaluate(event, candidates, gate_ctx, diagnosis)
            best, why_not = scorer.best(event, diagnosis, evaluation.permitted, decided_at)

            record = DecisionRecord(
                decision_id=f"dec_{uuid.uuid5(uuid.NAMESPACE_OID, event.event_id).hex[:16]}",
                batch_id=event.batch_id,
                event_id=event.event_id,
                decided_at=decided_at,
                event=event,
                diagnosis=diagnosis,
                candidates=candidates,
                gate_results=evaluation.gate_results,
                permitted=evaluation.permitted,
                ev_components=best.ev if best else None,
                chosen=best.action if best else None,
                not_chosen_why=why_not,
                deferred_until=(
                    min(d.defer_until for d in evaluation.deferred)
                    if evaluation.deferred
                    else None
                ),
                idempotency_key=(
                    f"{event.event_id}:{best.action.action_type.value}" if best else None
                ),
            )

            self.ledger.append(record)
            result.decisions.append(record)

            if best is not None:
                self._consume_budget(event, best.action, decided_at)

            # Deferred actions are held, not discarded. A pre-debit window makes
            # an action premature, not illegitimate.
            for deferred in evaluation.deferred:
                result.pending.append(
                    PendingAction(
                        decision_id=record.decision_id,
                        event_id=event.event_id,
                        action=deferred.action,
                        scheduled_for=deferred.defer_until,
                        deferred_by_rule=deferred.rule_id,
                        snapshot_consent=event.consent_active,
                        snapshot_attempts_24h=self.counters.total_attempts_24h(
                            event.instrument_token, decided_at, event.prior_attempts_24h
                        ),
                        snapshot_contacts_week=self.counters.total_contacts_week(
                            event.customer_id, decided_at, event.contacts_this_week
                        ),
                        notice_sent_at=decided_at,
                    )
                )

        return result

    def _consume_budget(self, event: RiskEvent, action, now: datetime) -> None:
        """Record what an action spends, so later decisions in the same batch see it.

        Without this the gate would evaluate every event against a pristine
        budget and the caps would never bind within a run — the counters would
        look correct and enforce nothing.
        """
        if action.action_type in _ATTEMPT_ACTIONS:
            self.counters.record_attempt(
                event.instrument_token,
                action.execute_at or now,
                event.payment_id,
                merchant_initiated=True,
            )
        if action.contact_cost > 0:
            self.counters.record_contact(event.customer_id, now)

    # -- deferred execution ------------------------------------------------

    def execute_pending(
        self,
        result: BatchResult,
        events_by_id: dict[str, RiskEvent],
        at: datetime | None = None,
    ) -> BatchResult:
        """Re-run the gate for every pending action whose window has opened.

        The outcome is appended as a RevalidationEntry. It is never folded into
        the original DecisionRecord — that record is sealed, and an append-only
        log whose entries can be edited afterwards is not an audit trail.
        """
        # Built once, not once per pending action. events_by_id is fixed for the
        # duration of this call, so re-deriving the batch-wide context (which
        # itself does a full pass and sorts every amount) inside the loop below
        # made this method O(events x pending) instead of O(events + pending) —
        # invisible at 1,000 events, a multi-minute stall at 15,000. Found by
        # running the new --stress scale test after this repo was already
        # published; fixed here rather than silently smoothed over.
        ctx = BatchContext.from_events(list(events_by_id.values()))

        for pending in result.pending:
            when = at or pending.scheduled_for
            if when < pending.scheduled_for:
                continue

            event = events_by_id[pending.event_id]
            gate_ctx = GateContext(
                now=when,
                counters=self.counters,
                # The pre-debit notice was sent when the action was deferred.
                notices_sent={pending.event_id: pending.notice_sent_at or pending.scheduled_for},
            )
            outcome = self.engine.revalidate(
                event, pending, gate_ctx, self.diagnoser.diagnose(event, ctx)
            )

            entry = RevalidationEntry(
                # Deterministic, not uuid4(): a random id makes every replay
                # produce a different chain and silently voids the
                # replayable-audit-trail claim. Caught by test_batch_is_deterministic.
                entry_id="rev_"
                + uuid.uuid5(
                    uuid.NAMESPACE_OID, f"{pending.decision_id}:{when.isoformat()}"
                ).hex[:16],
                decision_id=pending.decision_id,
                event_id=pending.event_id,
                at=when,
                approved=outcome.approved,
                blocking_rules=outcome.blocking_rules,
                changed_since_decision=outcome.changed_since_decision,
                gate_results=outcome.gate_results,
            )
            self.ledger.append(entry)
            result.revalidations.append(entry)

            if outcome.approved:
                self._consume_budget(event, pending.action, when)

        return result


def value_at_risk(events: list[RiskEvent]) -> Decimal:
    return sum((e.amount for e in events), Decimal("0"))
