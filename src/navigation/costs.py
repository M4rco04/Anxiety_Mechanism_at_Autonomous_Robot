"""Risk-sensitive route cost of a known cell.

The cost of driving onto a terrain is not a fixed number but a distribution:
``movement_cost`` is its mean and ``movement_cost_std`` its spread (see
``DEFAULT_TERRAIN_COST_STD`` in the configuration). The planners do not draw
random costs (that would only make the route jump between replans); they
use a risk-sensitive value of the distribution::

    cost = (mean + lambda * std) / (1 + lambda * std_ref)

so of two terrains with the same mean, the one with the less predictable
cost looks more expensive. The divisor keeps the reference terrain (safe
regolith, mean 1) at exactly 1: all other route constants (unknown cell,
exploration weights, fear weight) are calibrated in that unit, and only
terrain riskier than the reference becomes relatively more expensive.

``lambda`` is ``risk_aversion`` for every variant; the anxious variants add
``stress_risk_aversion * min(1, S / S_crit)``.
"""

from __future__ import annotations

from collections.abc import Callable

from src.navigation.types import TerrainObservation

TerrainCost = Callable[[TerrainObservation], float]


def mean_cost(info: TerrainObservation) -> float:
    """Expected cost only (risk-neutral)."""

    return info.movement_cost


def risk_cost(aversion: float, reference_std: float = 0.0) -> TerrainCost:
    """Risk-sensitive cost, in units of the reference terrain (mean 1)."""

    if aversion <= 0.0:
        return mean_cost
    scale = 1.0 / (1.0 + aversion * max(0.0, reference_std))

    def cost(info: TerrainObservation) -> float:
        return (info.movement_cost + aversion * info.movement_cost_std) * scale

    return cost


def stress_aversion(
    base: float, stress_gain: float, stress: float, s_crit: float
) -> float:
    """Risk aversion of a rover whose stress raises its caution."""

    if stress_gain <= 0.0 or s_crit <= 0.0:
        return base
    return base + stress_gain * min(1.0, max(0.0, stress) / s_crit)


__all__ = ["TerrainCost", "mean_cost", "risk_cost", "stress_aversion"]
