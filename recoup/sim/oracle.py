"""Recovery oracle — would this action, at this time, have actually worked?

EVALUATION-ONLY. Reads the latent world: the true root cause, the day the
customer's balance actually recovers, whether they would ever respond to
outreach, and whether the issuer was really down at that instant. Nothing under
`recoup.core` may import this. If the production path could see it, every
recovered rupee in the submission would be circular.

**Determinism is the whole contract.** The same `(event, action, time)` query
always returns the same answer, derived by hashing the query rather than drawing
from a stream. Two strategies asking about the same counterfactual must get the
same reality, or the comparison between them is meaningless — a shared RNG would
give a strategy a different world purely because it asked in a different order.

The model is mechanical rather than statistical wherever it can be. An empty
balance does not become full because you retried; it becomes full on payday. A
blocked card does not unblock. That is what makes timing matter and what a
blind-retry strategy cannot exploit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from recoup.core.models import ActionType, RiskEvent, RootCause
from recoup.sim import priors
from recoup.sim.generator import SimWorld

_RETRY_ACTIONS = frozenset({ActionType.RETRY_NOW, ActionType.RETRY_SCHEDULED})
_CONTACT_ACTIONS = frozenset(
    {
        ActionType.NUDGE_PAYMENT_LINK,
        ActionType.REQUEST_INSTRUMENT_SWITCH,
        ActionType.REQUEST_VPA_REPAIR,
        ActionType.WINBACK_SEQUENCE,
    }
)


@dataclass(frozen=True)
class OracleResult:
    success: bool
    reason: str

    def __bool__(self) -> bool:
        return self.success


def _draw(event_id: str, action: ActionType, when: datetime, attempt: int) -> float:
    """Deterministic uniform [0,1) keyed on the full query.

    Hashing rather than sampling is what lets four strategies interrogate the
    same world independently and consistently.
    """
    key = f"{event_id}|{action.value}|{when.isoformat()}|{attempt}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _next_funds_date(event_when: datetime, funds_day: int) -> date:
    """First occurrence of the customer's pay day at or after the failure."""
    if event_when.day <= funds_day:
        try:
            return event_when.date().replace(day=funds_day)
        except ValueError:
            pass
    year, month = (
        (event_when.year + 1, 1) if event_when.month == 12 else (event_when.year, event_when.month + 1)
    )
    return date(year, month, min(funds_day, 28))


class RecoveryOracle:
    def __init__(self, world: SimWorld) -> None:
        self.world = world
        self._events = {e.event_id: e for e in world.events}
        # Contacts already sent to a customer, so fatigue compounds across a run.
        self._contacts: dict[str, int] = {}
        self._attempts: dict[str, int] = {}

    def reset(self) -> None:
        """Clear per-strategy state. Call between strategies in a counterfactual."""
        self._contacts.clear()
        self._attempts.clear()

    # -----------------------------------------------------------------

    def evaluate(
        self, event: RiskEvent, action: ActionType, when: datetime
    ) -> OracleResult:
        latent = self.world.latent[event.event_id]
        cause = latent.root_cause
        attempt = self._attempts.get(event.event_id, 0)

        if action in _RETRY_ACTIONS:
            self._attempts[event.event_id] = attempt + 1
        if action in _CONTACT_ACTIONS:
            self._contacts[event.customer_id] = self._contacts.get(event.customer_id, 0) + 1

        # An obligation that no longer exists cannot be legitimately collected.
        # Money taken here becomes a refund and a dispute, so it is not a win.
        if not latent.obligation_valid:
            return OracleResult(False, "obligation no longer valid; collecting would be reversed")

        # --- capture ---------------------------------------------------
        if action is ActionType.CAPTURE_AUTHORIZED:
            if cause is not RootCause.UNCAPTURED:
                return OracleResult(False, "nothing authorised to capture")
            if event.auth_expires_at and when >= event.auth_expires_at:
                return OracleResult(False, "authorisation expired and was auto-refunded")
            roll = _draw(event.event_id, action, when, attempt)
            ok = roll < priors.BASE_RECOVERY_PROB[RootCause.UNCAPTURED]
            return OracleResult(ok, "captured" if ok else "capture failed at the gateway")

        # --- retries ---------------------------------------------------
        if action in _RETRY_ACTIONS:
            if cause in priors.TERMINAL_FOR_RETRY_SWITCHABLE or cause is RootCause.RISK_BLOCKED:
                return OracleResult(
                    False, f"{cause.value}: no retry on this instrument can ever succeed"
                )
            if cause is RootCause.UNCAPTURED:
                return OracleResult(False, "payment was authorised, not failed; retry is a no-op")

            base = priors.BASE_RECOVERY_PROB.get(cause, 0.0)

            if cause is RootCause.ISSUER_DOWN:
                if self.world.outage_at(event.issuer, when) is not None:
                    return OracleResult(
                        False, f"{event.issuer} still down at {when:%d %b %H:%M}"
                    )
                roll = _draw(event.event_id, action, when, attempt)
                ok = roll < base
                return OracleResult(ok, "issuer recovered" if ok else "issuer declined again")

            if cause is RootCause.INSUFFICIENT_FUNDS:
                funds_day = latent.funds_available_day or 1
                funded_on = _next_funds_date(event.occurred_at, funds_day)
                if when.date() < funded_on:
                    return OracleResult(
                        False,
                        f"balance not restored until {funded_on:%d %b}; retried {when:%d %b}",
                    )
                # Funded — but the money may have been spent again as time passes.
                elapsed = (when.date() - funded_on).days
                decay = 0.97 ** max(0, elapsed)
                roll = _draw(event.event_id, action, when, attempt)
                ok = roll < min(0.95, base * priors.SALARY_WINDOW_MULTIPLIER * decay)
                return OracleResult(
                    ok, "balance restored" if ok else "balance restored but spent again"
                )

            if cause is RootCause.LIMIT_EXCEEDED:
                if when.date() <= event.occurred_at.date():
                    return OracleResult(False, "daily counter has not reset yet")
                roll = _draw(event.event_id, action, when, attempt)
                ok = roll < base
                return OracleResult(ok, "limit reset" if ok else "limit hit again")

            # Customer-action causes: a retry cannot supply an OTP or a decision.
            roll = _draw(event.event_id, action, when, attempt)
            ok = roll < base
            return OracleResult(ok, "cleared on retry" if ok else "declined again")

        # --- outreach --------------------------------------------------
        if action in _CONTACT_ACTIONS:
            if cause is RootCause.RISK_BLOCKED:
                return OracleResult(False, "fraud-flagged; no channel recovers this")
            if not latent.responds_to_nudge:
                return OracleResult(False, "customer does not respond to outreach")

            sent = self._contacts.get(event.customer_id, 1)
            fatigue = priors.FATIGUE_DECAY_PER_CONTACT ** max(0, sent - 1)

            if action in (ActionType.REQUEST_INSTRUMENT_SWITCH, ActionType.REQUEST_VPA_REPAIR):
                p = priors.TERMINAL_SWITCH_RECOVERY_PROB * fatigue
            elif action is ActionType.WINBACK_SEQUENCE:
                p = 0.12 * fatigue
            else:
                base = priors.BASE_RECOVERY_PROB.get(cause, 0.10)
                fit = priors.ACTION_FIT.get((cause, ActionType.NUDGE_PAYMENT_LINK), 1.0)
                p = min(0.85, base * fit) * fatigue

            roll = _draw(event.event_id, action, when, attempt)
            ok = roll < p
            return OracleResult(
                ok,
                "customer paid after outreach"
                if ok
                else f"no response (fatigue factor {fatigue:.2f})",
            )

        # ESCALATE_HUMAN / STOP_UNCOLLECTIBLE recover nothing directly.
        return OracleResult(False, f"{action.value} recovers no money directly")
