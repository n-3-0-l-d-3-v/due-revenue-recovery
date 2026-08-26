"""Policy gate.

Runs before scoring and before any learner. A learner may only ever choose from
`EvaluationResult.permitted`, so learning cannot produce a network fine or a
compliance breach. That is the whole safety argument, and it holds by construction
rather than by training.

Three properties this module is responsible for:

1. **Completeness of the record.** Every rule that applies is evaluated and
   recorded, passes included. A gate that logs only refusals can prove it noticed
   some violations; it cannot prove compliance.

2. **DEFER is not BLOCK.** An RBI pre-debit window makes a debit illegitimate
   *now*, not illegitimate. Collapsing the two would silently discard recoverable
   revenue and would look like conservatism rather than the bug it is.

3. **Re-validation at execution time.** A decision made now that executes in 18
   hours must re-run the full gate against fresh state before acting. Consent can
   be withdrawn and counters can move in between. See `revalidate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol

import yaml

from recoup.core.counters import AttemptCounter
from recoup.core.models import (
    TERMINAL_FOR_RETRY,
    ActionType,
    CandidateAction,
    Diagnosis,
    GateResult,
    GateVerdict,
    Instrument,
    RiskEvent,
)

RULES_PATH = Path(__file__).with_name("rules.yaml")

# Actions no rule gates, deliberately. Both move no money and contact no one:
# escalation puts an item on an internal queue, and stopping does nothing at all.
# Gating them would be theatre, and would make an empty gate_results list look
# like a bug rather than the correct outcome.
UNGATED_ACTIONS: frozenset[ActionType] = frozenset(
    {ActionType.ESCALATE_HUMAN, ActionType.STOP_UNCOLLECTIBLE}
)


# ---------------------------------------------------------------------------
# Rule specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleSpec:
    id: str
    title: str
    source: str
    verdict: GateVerdict
    applies_to: frozenset[ActionType]
    params: dict
    note: str = ""


def load_rules(path: Path | None = None) -> list[RuleSpec]:
    raw = yaml.safe_load((path or RULES_PATH).read_text(encoding="utf-8"))
    specs: list[RuleSpec] = []
    for r in raw["rules"]:
        specs.append(
            RuleSpec(
                id=r["id"],
                title=r["title"],
                source=r["source"],
                verdict=GateVerdict(r["verdict"]),
                applies_to=frozenset(ActionType(a) for a in r.get("applies_to", [])),
                params=r.get("params") or {},
                note=(r.get("note") or "").strip(),
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------


@dataclass
class GateContext:
    """Everything a gate may read. Deliberately narrow.

    Note what is absent: expected value, recovery probability, and anything the
    scorer produces. A gate that could see value would eventually be tuned to
    trade compliance against revenue, which is the failure mode this whole
    architecture exists to prevent.
    """

    now: datetime
    counters: AttemptCounter
    merchant_category: str = "general"
    # event_id -> when the RBI pre-debit notice was sent
    notices_sent: dict[str, datetime] = field(default_factory=dict)


# Predicate returns (violated, rationale).
class Predicate(Protocol):
    def __call__(
        self, event: RiskEvent, action: CandidateAction, ctx: GateContext,
        params: dict, diagnosis: Diagnosis | None,
    ) -> tuple[bool, str]: ...


PREDICATES: dict[str, Predicate] = {}


def predicate(rule_id: str) -> Callable[[Predicate], Predicate]:
    def wrap(fn: Predicate) -> Predicate:
        PREDICATES[rule_id] = fn
        return fn
    return wrap


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


@predicate("network.attempts_per_card_30d")
def _attempts_30d(event, action, ctx, params, diagnosis):
    used = ctx.counters.total_attempts_30d(
        event.instrument_token, ctx.now, event.prior_attempts_30d
    )
    cap = params["max_attempts"]
    return used >= cap, f"{used}/{cap} attempts on this instrument in 30d"


@predicate("network.attempts_per_card_24h")
def _attempts_24h(event, action, ctx, params, diagnosis):
    used = ctx.counters.total_attempts_24h(
        event.instrument_token, ctx.now, event.prior_attempts_24h
    )
    cap = params["max_attempts"]
    return used >= cap, f"{used}/{cap} attempts on this instrument in 24h"


@predicate("network.merchant_retry_cap")
def _merchant_cap(event, action, ctx, params, diagnosis):
    used = ctx.counters.merchant_retries(event.payment_id)
    cap = params["max_retries"]
    return used >= cap, f"{used}/{cap} merchant-initiated retries on this payment"


@predicate("network.do_not_retry_terminal")
def _terminal(event, action, ctx, params, diagnosis):
    cause = diagnosis.root_cause if diagnosis else event.truth_root_cause
    if cause is None:
        return False, "no diagnosis available; not treated as terminal"
    if cause in TERMINAL_FOR_RETRY:
        return True, f"{cause.value} is terminal for same-instrument retry"
    return False, f"{cause.value} is not terminal"


@predicate("rbi.emandate_pre_debit_notice")
def _pre_debit(event, action, ctx, params, diagnosis):
    if event.instrument.value not in params["instruments"]:
        return False, "not a mandate instrument"
    sent = ctx.notices_sent.get(event.event_id)
    required = timedelta(hours=params["notice_hours"])
    if sent is None:
        return True, f"pre-debit notice not yet sent; {params['notice_hours']}h required"
    elapsed = ctx.now - sent
    if elapsed < required:
        remaining = required - elapsed
        return True, f"notice sent {elapsed} ago; {remaining} of the 24h window remains"
    return False, f"notice sent {elapsed} ago, window satisfied"


@predicate("rbi.afa_threshold")
def _afa(event, action, ctx, params, diagnosis):
    if event.instrument.value not in params["instruments"]:
        return False, "not a mandate instrument"
    threshold = Decimal(str(params["threshold"]))
    if ctx.merchant_category in params.get("exempt_categories", []):
        threshold = Decimal(str(params["exempt_category_threshold"]))
    if event.amount > threshold:
        return True, (
            f"Rs {event.amount} exceeds AFA threshold Rs {threshold} "
            f"for category '{ctx.merchant_category}'; cannot debit silently"
        )
    return False, f"Rs {event.amount} within AFA threshold Rs {threshold}"


@predicate("consent.active")
def _consent(event, action, ctx, params, diagnosis):
    return (not event.consent_active), (
        "consent withdrawn" if not event.consent_active else "consent active"
    )


@predicate("contact.weekly_cap")
def _contact_cap(event, action, ctx, params, diagnosis):
    used = ctx.counters.total_contacts_week(
        event.customer_id, ctx.now, event.contacts_this_week
    )
    cap = params["max_contacts"]
    return used >= cap, f"{used}/{cap} contacts to this customer this week"


@predicate("obligation.still_valid")
def _obligation(event, action, ctx, params, diagnosis):
    return (not event.obligation_valid), (
        "underlying obligation cancelled or unfulfillable"
        if not event.obligation_valid
        else "obligation valid"
    )


@predicate("value.below_cost_floor")
def _cost_floor(event, action, ctx, params, diagnosis):
    floor = Decimal(str(params["min_amount"]))
    return event.amount < floor, f"Rs {event.amount} vs floor Rs {floor}"


@predicate("auth.capture_window")
def _capture_window(event, action, ctx, params, diagnosis):
    if event.auth_expires_at is None:
        return True, "no authorisation on this event to capture"
    margin = timedelta(hours=params["safety_margin_hours"])
    deadline = event.auth_expires_at - margin
    if ctx.now >= deadline:
        return True, (
            f"authorisation expires {event.auth_expires_at:%Y-%m-%d %H:%M}; "
            f"inside the {params['safety_margin_hours']}h safety margin"
        )
    return False, f"authorisation valid until {event.auth_expires_at:%Y-%m-%d %H:%M}"

