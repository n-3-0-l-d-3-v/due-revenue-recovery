"""Exception queue — the work the system refuses to do automatically.

A recovery system claiming 100% automation is either lying or unsafe. The
buildathon bar asks for an honest exception list, and this is it.

**Exceptions are derived from decisions, not emitted as an action.** An earlier
design had `ESCALATE_HUMAN` as a candidate action competing on expected value.
That was wrong twice over: it scored zero recovery so any positive action beat
it, and it only ever fired for unmapped reason codes — which never occur, so the
queue was permanently empty. A queue nothing reaches is not a safety feature.

The real triggers are conditions on a decision that a human can actually resolve:
money stranded by a rule, an uncertain diagnosis on a material amount, a deferred
action the world invalidated, or a code we have never seen.

Closure is idempotent across batches. The same underlying situation re-derives
the same exception key every run, so closing it once keeps it closed — otherwise
an operator would face the same resolved item every morning and stop reading the
queue, which is the failure mode that makes exception lists worthless in practice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from due.core.models import DecisionRecord, RevalidationEntry, RootCause

# A human review costs roughly this much analyst time. Below it, escalating
# destroys more value than it recovers — the queue has to earn its own keep.
HUMAN_REVIEW_COST = Decimal("60.00")

# Diagnoses at or below this confidence are treated as uncertain.
UNCERTAIN_BELOW = 0.55

# Rules a human can actually do something about.
#
# Consent can be re-granted — an account manager can call and ask. Everything
# else the gate blocks on is settled: a cancelled obligation stays cancelled, an
# expired authorisation stays expired, a network cap resolves by waiting, and a
# terminal decline is terminal. Escalating those produces items whose only
# possible resolution is "acknowledged", which is how exception queues become
# wallpaper and stop being read.
RESOLVABLE_BLOCKS: frozenset[str] = frozenset({"consent.active"})

# A correct automated write-off is not an exception. Only escalate a negative-EV
# decision when the amount is large enough that a human might see an option the
# system cannot price — a payment plan, a goodwill call, a known VIP.
NO_VIABLE_ACTION_FLOOR = HUMAN_REVIEW_COST * 10


class ExceptionReason(str, Enum):
    BLOCKED_BUT_VALUABLE = "blocked_but_valuable"
    UNCERTAIN_DIAGNOSIS = "uncertain_diagnosis"
    REVALIDATION_REJECTED = "revalidation_rejected"
    UNMAPPED_REASON_CODE = "unmapped_reason_code"
    NO_VIABLE_ACTION = "no_viable_action"


SUGGESTED: dict[ExceptionReason, str] = {
    ExceptionReason.BLOCKED_BUT_VALUABLE: (
        "A policy rule stopped recovery on a material amount. Confirm whether the "
        "underlying condition still holds — consent may have been re-granted, or "
        "the obligation reinstated — then release or write off."
    ),
    ExceptionReason.UNCERTAIN_DIAGNOSIS: (
        "The issuer gave a generic decline and the inferred cause is low-confidence. "
        "Check the customer's recent payment history before trusting the action taken."
    ),
    ExceptionReason.REVALIDATION_REJECTED: (
        "A scheduled action was cancelled at execution time because the world changed. "
        "Review what changed and decide whether to re-queue."
    ),
    ExceptionReason.UNMAPPED_REASON_CODE: (
        "An error code with no mapping in the diagnosis table. Add it to the table "
        "with a documentation citation, or escalate to Razorpay support."
    ),
    ExceptionReason.NO_VIABLE_ACTION: (
        "Every available action had negative expected value. Confirm the write-off, "
        "or override if this customer warrants special handling."
    ),
}


@dataclass
class ExceptionItem:
    key: str
    event_id: str
    decision_id: str
    reason: ExceptionReason
    amount: Decimal
    priority: Decimal
    summary: str
    suggested_action: str
    opened_at: datetime
    closed_at: datetime | None = None
    closed_by: str | None = None
    closure_note: str | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


@dataclass
class ExceptionQueue:
    """Derives, prioritises, and closes exceptions.

    `_closed_keys` is the memory that makes closure stick across batches.
    """

    items: dict[str, ExceptionItem] = field(default_factory=dict)
    _closed_keys: set[str] = field(default_factory=set)

    # -- derivation --------------------------------------------------------

    def ingest(
        self,
        decisions: list[DecisionRecord],
        revalidations: list[RevalidationEntry] | None = None,
    ) -> list[ExceptionItem]:
        """Derive exceptions from a batch. Returns only the newly opened ones."""
        opened: list[ExceptionItem] = []

        for decision in decisions:
            for reason, summary in self._reasons_for(decision):
                item = self._make(decision, reason, summary)
                if item is None:
                    continue
                opened.append(item)

        for entry in revalidations or []:
            if entry.approved:
                continue
            key = f"{entry.event_id}:{ExceptionReason.REVALIDATION_REJECTED.value}"
            if key in self._closed_keys or key in self.items:
                continue
            changed = "; ".join(entry.changed_since_decision) or "state changed"
            item = ExceptionItem(
                key=key,
                event_id=entry.event_id,
                decision_id=entry.decision_id,
                reason=ExceptionReason.REVALIDATION_REJECTED,
                amount=Decimal("0"),
                priority=Decimal("1000"),  # always worth a look; the world moved
                summary=f"blocked at execution by {', '.join(entry.blocking_rules)} — {changed}",
                suggested_action=SUGGESTED[ExceptionReason.REVALIDATION_REJECTED],
                opened_at=entry.at,
            )
            self.items[key] = item
            opened.append(item)

        return opened

    def _reasons_for(self, decision: DecisionRecord):
        diagnosis = decision.diagnosis
        amount = decision.event.amount

        if diagnosis.root_cause is RootCause.AMBIGUOUS_DECLINE and diagnosis.confidence == 0.0:
            yield (
                ExceptionReason.UNMAPPED_REASON_CODE,
                f"unrecognised error code '{decision.event.error_reason}'",
            )
            return

        if decision.chosen is None and decision.blocked_by:
            rules = sorted({g.rule_id for g in decision.blocked_by})
            resolvable = sorted(set(rules) & RESOLVABLE_BLOCKS)
            if resolvable:
                yield (
                    ExceptionReason.BLOCKED_BUT_VALUABLE,
                    f"Rs {amount:,.0f} stranded by {', '.join(resolvable)}",
                )
            # Blocked by something settled — correct, automated, and not work.
            return

        if decision.chosen is None and decision.not_chosen_why:
            if amount >= NO_VIABLE_ACTION_FLOOR:
                yield (ExceptionReason.NO_VIABLE_ACTION, decision.not_chosen_why)
            return

        if diagnosis.reasoned_by != "table" and diagnosis.confidence <= UNCERTAIN_BELOW:
            yield (
                ExceptionReason.UNCERTAIN_DIAGNOSIS,
                f"inferred {diagnosis.root_cause.value} at {diagnosis.confidence:.0%} confidence",
            )

    def _make(
        self, decision: DecisionRecord, reason: ExceptionReason, summary: str
    ) -> ExceptionItem | None:
        key = f"{decision.event_id}:{reason.value}"
        if key in self._closed_keys or key in self.items:
            return None

        amount = decision.event.amount
        if reason is ExceptionReason.UNCERTAIN_DIAGNOSIS:
            # Uncertainty only matters in proportion to what is at stake.
            priority = amount * Decimal(str(round(1.0 - decision.diagnosis.confidence, 4)))
        else:
            priority = amount

        # An exception a human cannot profitably work is noise. Filtering here is
        # what keeps the queue readable enough to actually be read.
        if priority < HUMAN_REVIEW_COST and reason is not ExceptionReason.UNMAPPED_REASON_CODE:
            return None

        item = ExceptionItem(
            key=key,
            event_id=decision.event_id,
            decision_id=decision.decision_id,
            reason=reason,
            amount=amount,
            priority=priority.quantize(Decimal("0.01")),
            summary=summary,
            suggested_action=SUGGESTED[reason],
            opened_at=decision.decided_at,
        )
        self.items[key] = item
        return item

    # -- operator actions --------------------------------------------------

    def close(self, key: str, by: str, note: str, at: datetime | None = None) -> ExceptionItem:
        item = self.items[key]
        if not item.is_open:
            raise ValueError(f"{key} is already closed")
        item.closed_at = at or datetime.now()
        item.closed_by = by
        item.closure_note = note
        self._closed_keys.add(key)
        return item

    # -- views -------------------------------------------------------------

    @property
    def open_items(self) -> list[ExceptionItem]:
        return sorted(
            (i for i in self.items.values() if i.is_open),
            key=lambda i: i.priority,
            reverse=True,
        )

    @property
    def closed_items(self) -> list[ExceptionItem]:
        return [i for i in self.items.values() if not i.is_open]

    def by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.open_items:
            counts[item.reason.value] = counts.get(item.reason.value, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    @property
    def value_awaiting_review(self) -> Decimal:
        return sum((i.amount for i in self.open_items), Decimal("0"))

    def render(self, limit: int = 10) -> str:
        lines = [
            f"{len(self.open_items)} open · {len(self.closed_items)} closed · "
            f"Rs {self.value_awaiting_review:,.0f} awaiting review",
            "",
        ]
        for item in self.open_items[:limit]:
            lines.append(
                f"  [{item.priority:>10,.0f}] {item.reason.value:22s} {item.event_id}"
            )
            lines.append(f"               {item.summary}")
        remaining = len(self.open_items) - limit
        if remaining > 0:
            lines.append(f"  ... {remaining} more")
        return "\n".join(lines)
