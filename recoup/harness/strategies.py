"""The four strategies the counterfactual compares.

Each produces a plan — a list of (event, action, when) — which the harness then
executes against the oracle. Planning and execution are separated so that every
strategy is measured by identical machinery and no strategy gets to score itself.

The baselines are written to be *fair*, not to lose. Fixed T+3 really is what
Razorpay's standard subscription retry does. Blind retry really is what a
reason-agnostic "AI retry agent" amounts to. If the gated agent only wins against
strawmen, it has not shown anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from recoup.core.models import ActionType, EventType, RiskEvent
from recoup.core.pipeline import RecoveryPipeline

_ATTEMPT_ACTIONS = frozenset({ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED})
_CONTACT_ACTIONS = frozenset(
    {
        ActionType.NUDGE_PAYMENT_LINK,
        ActionType.REQUEST_INSTRUMENT_SWITCH,
        ActionType.REQUEST_VPA_REPAIR,
        ActionType.WINBACK_SEQUENCE,
    }
)


@dataclass(frozen=True)
class PlannedAction:
    event_id: str
    action_type: ActionType
    execute_at: datetime

    @property
    def is_attempt(self) -> bool:
        return self.action_type in _ATTEMPT_ACTIONS

    @property
    def is_contact(self) -> bool:
        return self.action_type in _CONTACT_ACTIONS


class Strategy(Protocol):
    name: str
    description: str

    def plan(self, events: list[RiskEvent]) -> list[PlannedAction]: ...


# ---------------------------------------------------------------------------


class DoNothing:
    name = "do_nothing"
    description = "No recovery at all. The floor every other strategy must clear."

    def plan(self, events: list[RiskEvent]) -> list[PlannedAction]:
        return []


class FixedT3:
    """Razorpay's standard subscription retry: once a day for three days.

    Reason-agnostic by design — that is the actual behaviour, and it is the
    honest baseline. It retries an expired card three times because it has no
    notion that some declines are terminal.
    """

    name = "fixed_t3"
    description = "Retry once daily for 3 days, reason-agnostic, then give up."

    RETRYABLE_EVENTS = frozenset(
        {EventType.FAILED_PAYMENT, EventType.FAILED_MANDATE}
    )

    def plan(self, events: list[RiskEvent]) -> list[PlannedAction]:
        out: list[PlannedAction] = []
        for event in events:
            if event.event_type not in self.RETRYABLE_EVENTS:
                continue
            for day in (1, 2, 3):
                out.append(
                    PlannedAction(
                        event_id=event.event_id,
                        action_type=ActionType.RETRY_SCHEDULED,
                        execute_at=(event.occurred_at + timedelta(days=day)).replace(
                            hour=10, minute=0, second=0, microsecond=0
                        ),
                    )
                )
        return out


class BlindRetry:
    """A reason-agnostic recovery agent that maximises attempts.

    This is what most "AI payment recovery" demos actually amount to once the
    framing is stripped away: retry everything that failed, nudge everyone, and
    report the recovery rate. It has no concept of terminal declines, network
    attempt caps, RBI notice windows, contact fatigue, or the cost of an attempt.

    It is included because it will recover a respectable amount of money. The
    point of the counterfactual is not that it fails — it is what it costs.
    """

    name = "blind_retry"
    description = "Retry everything up to 5x, nudge every customer. No gate, no caps."

    MAX_RETRIES = 5

    def plan(self, events: list[RiskEvent]) -> list[PlannedAction]:
        out: list[PlannedAction] = []
        for event in events:
            if event.event_type in (
                EventType.UNCAPTURED_AUTH,
                EventType.LATE_AUTHORIZATION,
            ):
                # It does not know these exist as a separate category, so it
                # treats them like any other stuck payment and retries them.
                for hours in (2, 8):
                    out.append(
                        PlannedAction(
                            event.event_id,
                            ActionType.RETRY_NOW,
                            event.occurred_at + timedelta(hours=hours),
                        )
                    )
                continue

            for i in range(self.MAX_RETRIES):
                out.append(
                    PlannedAction(
                        event.event_id,
                        ActionType.RETRY_SCHEDULED,
                        event.occurred_at + timedelta(hours=6 * (i + 1)),
                    )
                )
            for i in range(2):
                out.append(
                    PlannedAction(
                        event.event_id,
                        ActionType.NUDGE_PAYMENT_LINK,
                        event.occurred_at + timedelta(days=i + 1),
                    )
                )
        return out


class GatedAgent:
    """The system under test: diagnose, gate, score, act.

    Its plan is exactly what the production pipeline decided — including the
    deferred mandate debits that passed re-validation. Nothing is added for the
    benefit of the counterfactual.
    """

    name = "gated_agent"
    description = "Diagnosis-driven, policy-gated, net-value-scored recovery."

    def __init__(self) -> None:
        self.pipeline = RecoveryPipeline()
        self.result = None

    def plan(self, events: list[RiskEvent]) -> list[PlannedAction]:
        result = self.pipeline.run(events)
        result = self.pipeline.execute_pending(result, {e.event_id: e for e in events})
        self.result = result

        out: list[PlannedAction] = []
        for decision in result.acted:
            action = decision.chosen
            out.append(
                PlannedAction(
                    event_id=decision.event_id,
                    action_type=action.action_type,
                    execute_at=action.execute_at or decision.decided_at,
                )
            )

        approved = {r.decision_id for r in result.revalidations if r.approved}
        for pending in result.pending:
            if pending.decision_id in approved:
                out.append(
                    PlannedAction(
                        event_id=pending.event_id,
                        action_type=pending.action.action_type,
                        execute_at=pending.scheduled_for,
                    )
                )
        return out


def all_strategies() -> list[Strategy]:
    return [DoNothing(), FixedT3(), BlindRetry(), GatedAgent()]
