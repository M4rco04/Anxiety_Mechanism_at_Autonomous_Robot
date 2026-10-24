"""Mars terrain patches and their physical effects.

The visual contract (class names, ``color`` values and texture keys) is owned
by the board/visualization work.  This module adds physiological metadata and
uses the model's seeded RNG so simulation runs are reproducible.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import TYPE_CHECKING, Any

import mesa
import numpy as np

from src.model.types import RGB, Position, clamp, hex_to_rgb

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.agents.rover import Pioneer3DXAgent
    from src.model.model import MarsSimulation


class TerrainType(str, Enum):
    SAFE_REGOLITH = "SafeRegolith"
    BOULDERS = "Boulders"
    LOOSE_SAND = "LooseSand"
    VENTIFACTS = "Ventifacts"
    STEEP_SLOPE = "SteepSlope"
    DEEP_SHADOW = "DeepShadow"
    DUST_STORM = "DustStorm"


class TerrainPatch(mesa.Agent):
    """Base class for a hexagonal terrain cell.

    A patch is passive: it is placed on the grid but not added to the agent
    scheduler.  The rover calls :meth:`apply_effect` exactly once after a
    successful move.
    """

    terrain_type: TerrainType = TerrainType.SAFE_REGOLITH
    color: str = "#808080"
    traversable: bool = True
    friction: float = 0.85
    roughness: float = 0.1
    damage_probability: float = 0.0

    def __init__(
        self,
        unique_id: int,
        model: MarsSimulation,
        elevation: float = 0.0,
        slope: float = 0.0,
    ) -> None:
        super().__init__(unique_id, model)
        self.elevation = float(elevation)
        self.slope = float(slope)
        self.color = type(self).color
        self.optical_signature = self._make_signature(hex_to_rgb(self.color))
        self.last_effect: dict[str, Any] = {}

    def _make_signature(self, base: RGB) -> RGB:
        jitter = int(getattr(self.model.config, "signature_jitter", 0))
        if jitter <= 0:
            return base
        # Deterministic per-cell variation; no extra RNG stream is consumed.
        seed = int(self.unique_id)
        values = []
        for index, channel in enumerate(base):
            delta = ((seed * (index + 3) * 2654435761) % (2 * jitter + 1)) - jitter
            values.append(int(clamp(channel + delta, 0, 255)))
        return (values[0], values[1], values[2])

    @property
    def movement_cost(self) -> float:
        costs = getattr(self.model.config, "terrain_costs", {})
        return float(costs.get(type(self).__name__, 1.0))

    @property
    def damage_risk(self) -> float:
        risks = getattr(self.model.config, "terrain_risk", {})
        return float(risks.get(type(self).__name__, 0.0))

    @property
    def slope_risk(self) -> float:
        max_slope = max(1.0, float(getattr(self.model.config, "max_slope_deg", 90.0)))
        return clamp(self.slope / max_slope, 0.0, 1.0)

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        """Apply the terrain effect.  Overridden by concrete classes."""

    def get_surface_properties(self) -> dict[str, Any]:
        return {
            "terrain_type": self.terrain_type.value,
            "traversable": self.traversable,
            "movement_cost": self.movement_cost,
            "damage_risk": self.damage_risk,
            "slope_risk": self.slope_risk,
            "friction": self.friction,
            "roughness": self.roughness,
            "damage_probability": self.damage_probability,
            "color": self.color,
            "optical_signature": self.optical_signature,
            "elevation": self.elevation,
            "slope": self.slope,
        }

    def _rng(self, rover: Pioneer3DXAgent) -> np.random.Generator:
        return rover.model.rng

    @staticmethod
    def _clamp_rover(rover: Pioneer3DXAgent) -> None:
        rover.battery = clamp(rover.battery, 0.0, 100.0)
        rover.wheel_condition = clamp(rover.wheel_condition, 0.0, 100.0)
        rover.hull_condition = clamp(rover.hull_condition, 0.0, 100.0)
        rover.current_speed = max(0.0, rover.current_speed)
        rover.vision_range = max(0, int(rover.vision_range))


class SafeRegolith(TerrainPatch):
    """Hard, stable ground: low energy cost, no damage."""

    terrain_type = TerrainType.SAFE_REGOLITH
    color = "#d2b48c"
    friction = 0.92
    roughness = 0.08
    damage_probability = 0.0

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        mean_drain = 0.1 + (0.2 * rover.current_speed)
        drain = self._rng(rover).normal(loc=mean_drain, scale=0.05)
        rover.battery -= max(0.05, float(drain))
        self._clamp_rover(rover)


class Boulders(TerrainPatch):
    """Physical obstacle; navigation must never enter this cell."""

    terrain_type = TerrainType.BOULDERS
    color = "#4d4d4d"
    traversable = False
    friction = 0.0
    roughness = 1.0
    damage_probability = 1.0

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        # Defensive fallback: a correct navigation strategy never enters here.
        collision_prob = min(0.9, rover.current_speed * 0.4)
        if self._rng(rover).random() < collision_prob:
            damage = self._rng(rover).normal(
                loc=15.0 * rover.current_speed, scale=4.0
            )
            rover.hull_condition -= max(0.0, float(damage))
        rover.current_speed = 0.0
        rover.battery -= max(0.0, float(self._rng(rover).normal(loc=1.5, scale=0.3)))
        self._clamp_rover(rover)


class LooseSand(TerrainPatch):
    """Wheel slip, speed reduction and increased energy consumption."""

    terrain_type = TerrainType.LOOSE_SAND
    color = "#e6cc80"
    friction = 0.38
    roughness = 0.35
    damage_probability = 0.02

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        alpha = 2.0 + rover.current_speed
        beta_param = 5.0 / max(0.1, rover.current_speed)
        slip_factor = float(rng.beta(a=alpha, b=beta_param))
        rover.current_speed *= max(0.0, 1.0 - slip_factor)

        drain = float(
            rng.lognormal(mean=0.5 + rover.current_speed, sigma=0.3)
        )
        rover.battery -= max(0.0, drain)
        self._clamp_rover(rover)


class Ventifacts(TerrainPatch):
    """Sharp rocks that damage wheels; invisible to LIDAR."""

    terrain_type = TerrainType.VENTIFACTS
    color = "#8b4513"
    friction = 0.78
    roughness = 0.45
    damage_probability = 0.6

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        scale_damage = 3.0 * rover.current_speed
        damage = float(rng.exponential(scale=max(0.5, scale_damage)))
        rover.wheel_condition -= max(0.0, damage)
        rover.current_speed *= max(0.0, float(rng.normal(loc=0.85, scale=0.05)))
        rover.battery -= max(0.0, float(rng.normal(loc=0.8, scale=0.1)))
        self._clamp_rover(rover)


class SteepSlope(TerrainPatch):
    """Crater slope with a risk of overturning the rover."""

    terrain_type = TerrainType.STEEP_SLOPE
    color = "#ff6666"
    friction = 0.7
    roughness = 0.7
    damage_probability = 0.35

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        drain = float(
            rng.normal(loc=0.5 + math.exp(0.05 * self.slope), scale=0.3)
        )
        rover.battery -= max(0.1, drain)

        steepness_factor = self.slope - 30.0 + (rover.current_speed * 4.0)
        fall_prob = 1.0 / (1.0 + math.exp(-0.25 * steepness_factor))
        if rng.random() < fall_prob:
            rover.is_overturned = True
            hull_damage = float(rng.normal(loc=35.0, scale=10.0))
            wheel_damage = float(rng.normal(loc=20.0, scale=8.0))
            rover.hull_condition -= max(0.0, hull_damage)
            rover.wheel_condition -= max(0.0, wheel_damage)
            rover.current_speed = 0.0
        else:
            rover.gyro_alarm = self.slope > 20.0
        self._clamp_rover(rover)


class DeepShadow(TerrainPatch):
    """Shadow that accelerates battery discharge with exposure time."""

    terrain_type = TerrainType.DEEP_SHADOW
    color = "#1a1a1a"
    friction = 0.85
    roughness = 0.12
    damage_probability = 0.0

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        base_drain = 3.5 + (0.5 * rover.shadow_exposure_time)
        drain = float(self._rng(rover).normal(loc=base_drain, scale=0.4))
        rover.battery -= max(0.0, drain)
        self._clamp_rover(rover)


class DustStorm(TerrainPatch):
    """Dust limits RGB visibility but not LIDAR."""

    terrain_type = TerrainType.DUST_STORM
    color = "#b38b6d"
    friction = 0.8
    roughness = 0.2
    damage_probability = 0.0

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        current_lambda = max(0.1, 2.5 - (0.4 * rover.dust_exposure_time))
        rover.vision_range = int(
            max(0, self._rng(rover).poisson(lam=current_lambda))
        )
        rover.battery -= max(0.0, float(self._rng(rover).normal(loc=1.2, scale=0.3)))
        self._clamp_rover(rover)


def terrain_at(model: MarsSimulation, position: Position) -> TerrainPatch | None:
    """Return the terrain patch at ``position`` using the model's fast index."""

    if hasattr(model, "terrain_at"):
        return model.terrain_at(position)
    contents = model.grid.get_cell_list_contents([position])
    return next((agent for agent in contents if isinstance(agent, TerrainPatch)), None)


TERRAIN_CLASSES: dict[str, type[TerrainPatch]] = {
    "SafeRegolith": SafeRegolith,
    "Boulders": Boulders,
    "LooseSand": LooseSand,
    "Ventifacts": Ventifacts,
    "SteepSlope": SteepSlope,
    "DeepShadow": DeepShadow,
    "DustStorm": DustStorm,
}

TERRAIN_COLORS: dict[str, str] = {
    name: cls.color for name, cls in TERRAIN_CLASSES.items()
}


__all__ = [
    "TERRAIN_CLASSES",
    "TERRAIN_COLORS",
    "Boulders",
    "DeepShadow",
    "DustStorm",
    "LooseSand",
    "SafeRegolith",
    "SteepSlope",
    "TerrainPatch",
    "TerrainType",
    "Ventifacts",
    "terrain_at",
]
