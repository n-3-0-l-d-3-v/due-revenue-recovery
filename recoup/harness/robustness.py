"""Multi-seed robustness sweep.

One seed proves nothing — a skeptic can always say "you got lucky with seed 42."
This module answers the only question that actually addresses that: run the
same four strategies across many independently-generated random worlds and
report how often each claim holds.

Nothing here is a new claim. It is the existing counterfactual, repeated N times
against N different fake worlds, with the results aggregated honestly —
including whichever seed makes the gated agent look WORST, reported explicitly
rather than discarded. A robustness report that hides its own worst case is not
a robustness report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from recoup.harness.counterfactual import Counterfactual, StrategyResult
from recoup.harness.strategies import all_strategies
from recoup.sim.generator import generate_batch


@dataclass
class SeedRun:
    seed: int
    results: dict[str, StrategyResult]

    @property
    def gated(self) -> StrategyResult:
        return self.results["gated_agent"]

    @property
    def blind(self) -> StrategyResult:
        return self.results["blind_retry"]

    @property
    def gated_has_best_net_value(self) -> bool:
        return all(
            self.gated.net_value >= r.net_value
            for name, r in self.results.items()
            if name != "gated_agent"
        )


@dataclass
class RobustnessReport:
    n_seeds: int
    n_events_per_seed: int
    runs: list[SeedRun] = field(default_factory=list)

    @property
    def zero_violation_rate(self) -> float:
        return sum(1 for r in self.runs if r.gated.policy_violations == 0) / len(self.runs)

    @property
    def best_net_value_rate(self) -> float:
        return sum(1 for r in self.runs if r.gated_has_best_net_value) / len(self.runs)

    @property
    def worst_seed_for_gated(self) -> SeedRun:
        """The seed where the gated agent's margin over the best rival is smallest.

        Reported explicitly, not hidden. Actively looking for the worst case and
        publishing it is what makes the average case credible.
        """
        def margin(run: SeedRun) -> Decimal:
            rivals = [r.net_value for n, r in run.results.items() if n != "gated_agent"]
            return run.gated.net_value - max(rivals)
        return min(self.runs, key=margin)

    @property
    def best_seed_for_gated(self) -> SeedRun:
        def margin(run: SeedRun) -> Decimal:
            rivals = [r.net_value for n, r in run.results.items() if n != "gated_agent"]
            return run.gated.net_value - max(rivals)
        return max(self.runs, key=margin)

    def net_values(self, strategy: str) -> list[Decimal]:
        return [r.results[strategy].net_value for r in self.runs]

    def mean_net_value(self, strategy: str) -> Decimal:
        vals = self.net_values(strategy)
        return sum(vals, Decimal("0")) / len(vals)

    def stats(self, strategy: str) -> tuple[Decimal, Decimal, Decimal]:
        """(min, mean, max) net value for a strategy across all seeds."""
        vals = sorted(self.net_values(strategy))
        return vals[0], self.mean_net_value(strategy), vals[-1]

    def render(self) -> str:
        lines = [
            f"ROBUSTNESS ACROSS {self.n_seeds} INDEPENDENT RANDOM WORLDS "
            f"({self.n_events_per_seed} events each, {self.n_seeds * self.n_events_per_seed:,} total)",
            "=" * 78,
            "",
            f"gated agent: zero policy violations in "
            f"{sum(1 for r in self.runs if r.gated.policy_violations == 0)}/{self.n_seeds} worlds "
            f"({self.zero_violation_rate:.0%})",
            f"gated agent: highest net value in "
            f"{sum(1 for r in self.runs if r.gated_has_best_net_value)}/{self.n_seeds} worlds "
            f"({self.best_net_value_rate:.0%})",
            "",
            "net value by strategy across all worlds (min / mean / max):",
        ]
        for name in ("do_nothing", "fixed_t3", "blind_retry", "gated_agent"):
            lo, mean, hi = self.stats(name)
            lines.append(f"  {name:14s}  Rs {lo:>12,.0f}   Rs {mean:>12,.0f}   Rs {hi:>12,.0f}")

        worst = self.worst_seed_for_gated
        rivals = {n: r.net_value for n, r in worst.results.items() if n != "gated_agent"}
        best_rival = max(rivals, key=lambda k: rivals[k])
        lines += [
            "",
            f"WORST CASE FOR US — seed {worst.seed} (smallest margin over the best rival):",
            f"  gated_agent net value      Rs {worst.gated.net_value:>12,.0f}",
            f"  best rival ({best_rival:<11s}) Rs {rivals[best_rival]:>12,.0f}",
            f"  margin                     Rs {worst.gated.net_value - rivals[best_rival]:>12,.0f}",
            f"  violations that seed       {worst.gated.policy_violations} "
            f"(vs blind retry's {worst.blind.policy_violations})",
        ]
        return "\n".join(lines)


def sweep(seeds: range | list[int], n_events: int = 1000) -> RobustnessReport:
    report = RobustnessReport(n_seeds=len(seeds), n_events_per_seed=n_events)
    for seed in seeds:
        world = generate_batch(n_events=n_events, seed=seed)
        cf = Counterfactual(world)
        results = {s.name: cf.run(s) for s in all_strategies()}
        report.runs.append(SeedRun(seed=seed, results=results))
    return report
