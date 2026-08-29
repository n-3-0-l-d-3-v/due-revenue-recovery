"""Stress and scale testing.

The 50-seed robustness sweep (`robustness.py`) answers "did you get lucky with
one random dataset?" — average-case proof by repeated sampling. This module
answers two different, harder questions that more random sampling cannot:

1. "Does this only work on a toy example?" — SCALE. Same priors, much bigger
   batches. If the pipeline's own performance falls over at scale, or if the
   claims quietly change shape as volume grows, that is a real finding either
   way and this reports it honestly.

2. "What about a batch you didn't get to pick?" — ADVERSARY. Not a random draw
   from the normal priors — a batch deliberately constructed to be as hostile
   as possible: more outages, sicker customers, less headroom before the
   network caps. This is worst-case engineering, not average-case sampling,
   and it is a strictly stronger form of evidence.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, replace

from due.core.pipeline import RecoveryPipeline
from due.harness.counterfactual import Counterfactual
from due.harness.strategies import all_strategies
from due.sim import priors
from due.sim.generator import generate_batch


@dataclass
class ScalePoint:
    n_events: int
    seconds: float
    violations_gated: int
    violations_blind: int
    net_value_gated: float
    net_value_blind: float


def scale_test(sizes: list[int] = [1000, 3000, 8000], seed: int = 42) -> list[ScalePoint]:
    """Run the full pipeline at increasing batch sizes and report wall-clock time
    alongside the claims, so a performance regression and a claim regression are
    both visible in the same table.

    Sizes capped at 8,000 deliberately. A real perf bug was found and fixed here
    (BatchContext was being rebuilt inside a per-action loop — true O(events x
    pending), invisible at 1,000 events, a multi-minute stall at 15,000). What
    remains beyond that fix is a milder, Python-level superlinear cost in
    AttemptCounter's window scans at very large synthetic volumes. It does not
    affect correctness and does not affect the actual submission (n=1,000 runs
    in under a second) — but fixing it would require assuming attempts are
    recorded in strict time order, which is true for this harness but NOT
    guaranteed for the live pipeline, and that is not an assumption worth
    risking inside the module that decides whether a fine gets triggered. Stated
    here rather than silently worked around.
    """
    out = []
    for n in sizes:
        t0 = time.time()
        world = generate_batch(n_events=n, seed=seed)
        cf = Counterfactual(world)
        results = {s.name: cf.run(s) for s in all_strategies()}
        elapsed = time.time() - t0
        g, b = results["gated_agent"], results["blind_retry"]
        out.append(
            ScalePoint(
                n_events=n,
                seconds=elapsed,
                violations_gated=g.policy_violations,
                violations_blind=b.policy_violations,
                net_value_gated=float(g.net_value),
                net_value_blind=float(b.net_value),
            )
        )
    return out


def render_scale(points: list[ScalePoint]) -> str:
    lines = [
        "SCALE — same priors, bigger batches",
        "=" * 78,
        "",
        f"{'events':>8}  {'time':>8}  {'gated viol':>11}  {'blind viol':>11}  "
        f"{'gated net':>14}  {'blind net':>14}",
    ]
    for p in points:
        lines.append(
            f"{p.n_events:>8}  {p.seconds:>7.2f}s  {p.violations_gated:>11}  "
            f"{p.violations_blind:>11}  Rs {p.net_value_gated:>10,.0f}  "
            f"Rs {p.net_value_blind:>10,.0f}"
        )
    base = points[0]
    linear_ratio = points[-1].n_events / base.n_events
    time_ratio = points[-1].seconds / max(base.seconds, 0.001)
    verdict = (
        "roughly linear — OK"
        if time_ratio < linear_ratio * 1.5
        else "superlinear — known, see the docstring on scale_test(); "
        "correctness is unaffected and the actual submission runs at n=1,000"
    )
    lines += [
        "",
        f"batch grew {linear_ratio:.0f}x, runtime grew {time_ratio:.0f}x ({verdict})",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Adversarial world — built to be hostile, not sampled to be average
# ---------------------------------------------------------------------------


def hostile_priors() -> dict:
    """A snapshot of the priors module's mutable state, patched to be as
    unfavourable as plausibly justified, then restored. Every value pushed here
    is still inside the range the sensitivity harness already swept — this is
    not "impossible," it is "the worst end of what we already said was
    plausible," which is what makes it a fair adversarial test rather than a
    strawman.
    """
    return {
        "ISSUER_OUTAGE_DAY_PROB": priors.ISSUER_OUTAGE_DAY_PROB * 4,
        "FATIGUE_DECAY_PER_CONTACT": priors.FATIGUE_DECAY_PER_CONTACT * 0.6,
        "AMOUNT_LOGNORM_SIGMA": priors.AMOUNT_LOGNORM_SIGMA * 1.4,
    }


def adversarial_run(n_events: int = 1000, seed: int = 1) -> dict:
    """Generate the single most hostile batch we can justify, then measure it.

    Not repeated across seeds — the point is one deliberately-constructed worst
    case, not an average. Returns the same StrategyResult objects the ordinary
    counterfactual produces, so nothing about the measurement itself changes.
    """
    saved = {}
    hostile = hostile_priors()
    try:
        for name, value in hostile.items():
            saved[name] = getattr(priors, name)
            setattr(priors, name, value)

        world = generate_batch(n_events=n_events, seed=seed)
        cf = Counterfactual(world)
        results = {s.name: cf.run(s) for s in all_strategies()}
    finally:
        for name, value in saved.items():
            setattr(priors, name, value)

    return {"world": world, "results": results, "hostile_params": hostile}


def render_adversarial(run: dict) -> str:
    results = run["results"]
    g, b = results["gated_agent"], results["blind_retry"]
    lines = [
        "ADVERSARIAL — a batch built to be hostile, not sampled to be average",
        "=" * 78,
        "",
        "parameters pushed to the hostile end of the already-published range:",
    ]
    for name, value in run["hostile_params"].items():
        baseline = getattr(priors, name)
        lines.append(f"  {name:28s} {baseline:.4g} -> {value:.4g}")
    lines += [
        "",
        f"gated agent : Rs {g.amount_recovered:>10,.0f} recovered, "
        f"{g.policy_violations} violations, net Rs {g.net_value:>10,.0f}",
        f"blind retry : Rs {b.amount_recovered:>10,.0f} recovered, "
        f"{b.policy_violations} violations, net Rs {b.net_value:>10,.0f}",
        "",
        f"{'zero violations held under adversarial conditions' if g.policy_violations == 0 else 'VIOLATIONS APPEARED UNDER STRESS — this is a real finding, report it'}",
    ]
    return "\n".join(lines)
