"""Fuzzy rule base of the ``fuzzy`` rover.

The fuzzy rover drives like the plain one (the same A* route planning and
exploration). It has no fear memory and learns nothing. Instead, a small set
of expert rules turns what the rover knows about a cell (terrain risk, slope,
energy cost) and about itself (condition of hull and wheels, battery, battery
drain, stress) into a *caution* between 0 and 1:

    caution(cell) = sum(mu_i * z_i) / sum(mu_i)        (zero-order Sugeno)

``mu_i`` is the degree to which rule ``i`` applies and ``z_i`` its output
level. The caution is used in two ways:

- as an extra route cost ``fuzzy_weight * caution`` (so the rules choose the
  direction: the rover prefers a detour and crosses risky terrain only when
  the detour is more expensive),
- to step back: the rover retreats from a cell it distrusts when
  ``retreat_degree`` reaches ``fuzzy_retreat_level``.

Edit ``RULES`` to change the behaviour; nothing else depends on the details.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


# ----------------------------------------------------------------------
# Membership functions
# ----------------------------------------------------------------------
def rising(x: float, low: float, high: float) -> float:
    """0 below ``low``, 1 above ``high``, linear in between."""

    if x <= low:
        return 0.0
    if x >= high:
        return 1.0
    return (x - low) / (high - low)


def falling(x: float, low: float, high: float) -> float:
    """1 below ``low``, 0 above ``high``, linear in between."""

    return 1.0 - rising(x, low, high)


def triangle(x: float, left: float, peak: float, right: float) -> float:
    if x <= left or x >= right:
        return 0.0
    if x <= peak:
        return (x - left) / (peak - left)
    return (right - x) / (right - peak)


# ----------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class FuzzyInputs:
    """Crisp inputs of one inference (one cell, the rover's current state)."""

    risk: float  # a-priori damage risk of the terrain, 0..1
    slope: float  # degrees
    energy: float  # movement (energy) cost of the terrain, 1 = easy
    condition: float  # min(hull, wheels), 0..100
    battery: float  # 0..100
    stress: float  # smoothed homeostat stress, 0..100
    drain: float = 0.0  # battery used in the last step [%]


# Linguistic terms: name -> membership of the crisp inputs.
TERMS: dict[str, Callable[[FuzzyInputs], float]] = {
    "risk_low": lambda i: falling(i.risk, 0.05, 0.20),
    "risk_medium": lambda i: triangle(i.risk, 0.10, 0.25, 0.40),
    "risk_high": lambda i: rising(i.risk, 0.30, 0.50),
    "slope_gentle": lambda i: falling(i.slope, 15.0, 25.0),
    "slope_steep": lambda i: rising(i.slope, 24.0, 32.0),
    "energy_costly": lambda i: rising(i.energy, 1.2, 2.0),
    "drain_high": lambda i: rising(i.drain, 3.0, 7.0),
    "condition_poor": lambda i: falling(i.condition, 30.0, 60.0),
    "battery_low": lambda i: falling(i.battery, 30.0, 55.0),
    "stress_alarmed": lambda i: rising(i.stress, 25.0, 50.0),
}

# Output levels of the caution.
NONE, SLIGHT, MODERATE, HIGH, EXTREME = 0.0, 0.15, 0.35, 0.8, 1.0

# IF all terms THEN caution level (AND = minimum).
RULES: list[tuple[tuple[str, ...], float, str]] = [
    (("risk_low", "slope_gentle"), NONE, "easy ground is safe"),
    (("risk_medium",), MODERATE, "risky terrain: prefer a detour"),
    (("risk_high",), EXTREME, "dangerous terrain: avoid"),
    (("slope_steep",), EXTREME, "steep slope: the rover may overturn"),
    (("risk_medium", "condition_poor"), EXTREME, "a damaged rover takes no risks"),
    (("risk_low", "condition_poor"), SLIGHT, "a damaged rover is careful everywhere"),
    (("risk_medium", "stress_alarmed"), HIGH, "under stress: be more careful"),
    (("energy_costly", "battery_low"), HIGH, "low battery: avoid costly terrain"),
    (("energy_costly", "drain_high"), EXTREME, "the battery is draining fast: get out"),
]


def caution(inputs: FuzzyInputs) -> float:
    """Caution of one cell, 0 (drive freely) .. 1 (avoid)."""

    memberships = {name: term(inputs) for name, term in TERMS.items()}
    total = 0.0
    weighted = 0.0
    for terms, level, _ in RULES:
        strength = min(memberships[name] for name in terms)
        if strength > 0.0:
            total += strength
            weighted += strength * level
    return weighted / total if total > 0.0 else 0.0


def retreat_degree(cell_caution: float, stress: float) -> float:
    """How strongly the rover wants to step back from the cell it stands on.

    IF the cell is very risky THEN retreat.
    IF the cell is risky AND the stress is alarming THEN retreat.
    """

    very_risky = rising(cell_caution, 0.4, 0.7)
    risky = rising(cell_caution, 0.1, 0.3)
    alarmed = rising(stress, 25.0, 50.0)
    return max(very_risky, min(risky, alarmed))


__all__ = [
    "RULES",
    "TERMS",
    "FuzzyInputs",
    "caution",
    "falling",
    "retreat_degree",
    "rising",
    "triangle",
]
