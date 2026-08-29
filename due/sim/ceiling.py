"""Bayes-optimal ceiling for ambiguous-decline inference.

An accuracy number is unreadable without both bounds:

    majority-class floor  <=  achieved  <=  Bayes ceiling

The floor is what you get by always guessing the most common cause. The ceiling
is what a perfect reasoner gets — one that knows the true conditional
distribution exactly. The gap between them is the only headroom that exists;
everything else is irreducible error, because the generic decline genuinely does
not carry the information.

This module is EVALUATION-ONLY. It reads the simulator's generative parameters,
which no diagnoser may ever do. Importing it from `due.core` would make the
reported accuracy circular, so it lives in `sim/`.

Knowing the ceiling changes decisions. If the headroom is four points, spending
an LLM call per event to chase it is the wrong engineering call, and saying so is
worth more than a flattering number.
"""

from __future__ import annotations

from dataclasses import dataclass

from due.core.models import RootCause
from due.sim import priors
from due.sim.generator import SimWorld


@dataclass
class CeilingReport:
    n: int
    majority_floor: float
    bayes_ceiling: float
    per_cause_ceiling: dict[str, tuple[int, int]]

    @property
    def headroom(self) -> float:
        return self.bayes_ceiling - self.majority_floor

    def __str__(self) -> str:
        lines = [
            f"ambiguous declines     : {self.n}",
            f"majority-class floor   : {self.majority_floor:.1%}",
            f"Bayes-optimal ceiling  : {self.bayes_ceiling:.1%}",
            f"available headroom     : {self.headroom:.1%}",
            "",
            "ceiling per hidden cause (recoverable/total):",
        ]
        for cause, (ok, tot) in sorted(
            self.per_cause_ceiling.items(), key=lambda kv: -kv[1][1]
        ):
            lines.append(f"  {cause:22s} {ok:3d}/{tot:3d}  {ok / tot:6.1%}")
        return "\n".join(lines)


def _posterior(
    *,
    outage_active: bool,
    amount,
    prior_attempts: int,
    occurred_at,
    recent_success_count: int,
    max_recent_success_amount,
) -> dict[RootCause, float]:
    """The exact posterior given everything a diagnoser can observe.

        P(cause | context, history) ∝ P(cause | context) · P(history | cause)

    The prior comes from the context multipliers; the likelihood comes from the
    instrument success history. The history terms carry most of the signal —
    without them the posterior argmax collapsed onto the majority class for
    almost every event.
    """
    weights = dict(priors.AMBIGUOUS_HIDDEN_CAUSE)

    active: list[str] = []
    if outage_active:
        active.append("issuer_outage_active")
    if amount >= priors.AMBIGUOUS_HIGH_AMOUNT:
        active.append("amount_high")
    if prior_attempts >= priors.AMBIGUOUS_MANY_ATTEMPTS:
        active.append("many_prior_attempts")
    if occurred_at.day >= 25 or occurred_at.day <= 5:
        active.append("late_month")
    if occurred_at.hour < 6:
        active.append("odd_hour")

    for signal in active:
        for cause, mult in priors.AMBIGUOUS_CONTEXT_MULTIPLIERS[signal].items():
            weights[cause] = weights.get(cause, 0.0) * mult

    # Likelihood of the observed instrument history under each cause.
    for cause in list(weights):
        p_none = priors.P_NO_RECENT_SUCCESS.get(cause, 0.15)
        if recent_success_count == 0:
            weights[cause] *= p_none
        else:
            p_larger = priors.P_LARGER_SUCCESS_EXISTS.get(cause, 0.5)
            larger = (
                max_recent_success_amount is not None
                and max_recent_success_amount > amount
            )
            weights[cause] *= (1.0 - p_none) * (p_larger if larger else 1.0 - p_larger)

    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total else weights


def bayes_ceiling(world: SimWorld) -> CeilingReport:
    from due.core.diagnose import AMBIGUOUS_REASONS

    events = [e for e in world.events if e.error_reason in AMBIGUOUS_REASONS]
    if not events:
        return CeilingReport(0, 0.0, 0.0, {})

    counts: dict[RootCause, int] = {}
    correct = 0
    per_cause: dict[str, list[int]] = {}

    for e in events:
        truth = e.truth_root_cause
        counts[truth] = counts.get(truth, 0) + 1

        posterior = _posterior(
            outage_active=world.outage_at(e.issuer, e.occurred_at) is not None,
            amount=e.amount,
            prior_attempts=e.prior_attempts_30d,
            occurred_at=e.occurred_at,
            recent_success_count=e.recent_success_count,
            max_recent_success_amount=e.max_recent_success_amount,
        )
        best = max(posterior, key=lambda k: posterior[k])
        hit = int(best == truth)
        correct += hit

        bucket = per_cause.setdefault(truth.value if truth else "unknown", [0, 0])
        bucket[0] += hit
        bucket[1] += 1

    majority = max(counts.values()) / len(events)
    return CeilingReport(
        n=len(events),
        majority_floor=majority,
        bayes_ceiling=correct / len(events),
        per_cause_ceiling={k: (v[0], v[1]) for k, v in per_cause.items()},
    )
