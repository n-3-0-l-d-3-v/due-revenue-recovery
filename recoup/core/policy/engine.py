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

