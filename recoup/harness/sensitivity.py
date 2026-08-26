"""Sensitivity analysis.

The counterfactual table is only as trustworthy as the assumptions underneath
it. This module answers three questions, and it is designed to be able to
answer them *against* the project's own narrative:

1. Over what range of each assumed parameter does the gated agent still have the
   highest net value?
2. Where does the ranking flip?
3. How much of the "blind retry destroys value" result is carried by the churn
   assumption specifically, versus attempt cost, contact cost, and penalties?

If a claim survives only at one hand-picked parameter value, it is not a claim.
The output here is meant to be published as-is, including the flip points.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from recoup.harness.counterfactual import CostModel, Counterfactual
from recoup.harness.strategies import BlindRetry, FixedT3, GatedAgent
from recoup.sim.generator import generate_batch


@dataclass
class SweepPoint:
    value: float
    net_by_strategy: dict[str, Decimal]

    @property
    def winner(self) -> str:
        return max(self.net_by_strategy, key=lambda k: self.net_by_strategy[k])


@dataclass
class Sweep:
    parameter: str
    baseline: float
    points: list[SweepPoint]

    @property
    def gated_wins_everywhere(self) -> bool:
        return all(p.winner == "gated_agent" for p in self.points)

    def flip_value(self) -> float | None:
        """Lowest swept value at which the gated agent stops winning."""
        for point in self.points:
            if point.winner != "gated_agent":
                return point.value
        return None

    def render(self) -> str:
        names = list(self.points[0].net_by_strategy)
        header = f"{self.parameter}  (baseline {self.baseline:g})"
        lines = [header, "-" * len(header)]
        lines.append(
            f"{'value':>12}  " + "  ".join(f"{n:>13}" for n in names) + "   winner"
        )
        for point in self.points:
            cells = "  ".join(f"{point.net_by_strategy[n]:>13,.0f}" for n in names)
            mark = "" if point.winner == "gated_agent" else "   <-- FLIP"
            lines.append(f"{point.value:>12g}  {cells}   {point.winner}{mark}")
        return "\n".join(lines)


def _net_values(world, costs: CostModel) -> dict[str, Decimal]:
    cf = Counterfactual(world, costs=costs)
    return {
        s.name: cf.run(s).net_value for s in (FixedT3(), BlindRetry(), GatedAgent())
    }


def sweep(
    parameter: str,
    values: list[float],
    seed: int = 42,
    n_events: int = 1000,
) -> Sweep:
    world = generate_batch(n_events=n_events, seed=seed)
    base = CostModel()
    baseline = getattr(base, parameter)

    points = []
    for value in values:
        cast = Decimal(str(value)) if isinstance(baseline, Decimal) else value
        points.append(
            SweepPoint(value=value, net_by_strategy=_net_values(world, base.with_(**{parameter: cast})))
        )
    return Sweep(
        parameter=parameter,
        baseline=float(baseline),
        points=points,
    )


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


@dataclass
class Attribution:
    """How much each cost component contributes to blind retry's deficit."""

    full_gap: Decimal
    contribution: dict[str, Decimal]

    def render(self) -> str:
        lines = [
            f"gated_agent net value minus blind_retry net value: Rs {self.full_gap:,.0f}",
            "",
            "removing each cost component and re-measuring the gap:",
        ]
        for name, gap in sorted(
            self.contribution.items(), key=lambda kv: -(self.full_gap - kv[1])
        ):
            carried = self.full_gap - gap
            share = float(carried / self.full_gap) if self.full_gap else 0.0
            lines.append(
                f"  without {name:22s} gap becomes Rs {gap:>12,.0f}   "
                f"(this component carries {share:6.1%})"
            )
        return "\n".join(lines)


def attribute(seed: int = 42, n_events: int = 1000) -> Attribution:
    """Zero each cost component in turn and see how much of the gap disappears.

    This is the honest way to answer "is the result just the churn assumption?".
    """
    world = generate_batch(n_events=n_events, seed=seed)
    base = CostModel()

    def gap(costs: CostModel) -> Decimal:
        nets = _net_values(world, costs)
        return nets["gated_agent"] - nets["blind_retry"]

    full = gap(base)
    variants = {
        "churn": base.with_(churn_per_contact=0.0, churn_per_retry=0.0),
        "attempt cost": base.with_(retry_cost=Decimal("0")),
        "contact cost": base.with_(contact_cost=Decimal("0")),
        "network penalties": base.with_(penalty_per_excess_attempt=Decimal("0")),
        "support cost": base.with_(p_support_ticket=0.0),
    }
    return Attribution(
        full_gap=full,
        contribution={name: gap(costs) for name, costs in variants.items()},
    )


# ---------------------------------------------------------------------------
# Seed stability
# ---------------------------------------------------------------------------


def across_seeds(seeds: tuple[int, ...] = (42, 43, 44, 45, 46)) -> dict[int, dict[str, Decimal]]:
    """Ranking stability across worlds, holding the priors fixed.

    Separates "the result depends on an assumption" from "the result depends on
    one lucky batch" — different failure modes needing different disclosures.
    """
    out = {}
    for seed in seeds:
        out[seed] = _net_values(generate_batch(n_events=1000, seed=seed), CostModel())
    return out
