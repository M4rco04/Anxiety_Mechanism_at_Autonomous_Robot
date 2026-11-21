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

from src.environment.traction import DriveOutcome, drive_effect
from src.model.types import RGB, Position, clamp, hex_to_rgb

# Idle current of the motors: driving downhill never costs less than this
# fraction of driving on flat ground.
MIN_ENERGY_FACTOR = 0.25

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
    def movement_cost_std(self) -> float:
        spreads = getattr(self.model.config, "terrain_cost_std", {})
        return float(spreads.get(type(self).__name__, 0.0))

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

    def _rng(self, rover: Pioneer3DXAgent) -> np.random.Generator:
        return rover.model.rng

    @staticmethod
    def _clamp_rover(rover: Pioneer3DXAgent) -> None:
        rover.battery = clamp(rover.battery, 0.0, 100.0)
        rover.wheel_condition = clamp(rover.wheel_condition, 0.0, 100.0)
        rover.hull_condition = clamp(rover.hull_condition, 0.0, 100.0)
        rover.current_speed = max(0.0, rover.current_speed)
        rover.vision_range = max(0, int(rover.vision_range))

    def _traction(
        self, rover: Pioneer3DXAgent, apply_slip: bool = True
    ) -> DriveOutcome | None:
        """Slope traction of the P3-AT (Wang et al. 2015), see traction.py.

        Slows the rover by the slip ratio and charges the gravity work of the
        slope: ``flat_drain * (energy_factor - 1)`` on top of the terrain's
        own drain (which is the drain on flat ground). ``None`` when the
        traction model is off (the previous, slope-free terrain effects).
        """

        config = rover.model.config
        if not getattr(config, "traction_model", False):
            return None
        outcome = drive_effect(self.slope, self._rng(rover))
        if apply_slip:
            rover.current_speed *= max(0.0, 1.0 - outcome.slip)
            rover.last_slip = outcome.slip
        # Down a slope the motors work less, but never below idle current.
        factor = max(MIN_ENERGY_FACTOR, outcome.energy_factor)
        rover.battery -= float(config.flat_drain) * (factor - 1.0)
        return outcome

    def _flat_drain(self, rover: Pioneer3DXAgent) -> float:
        config = rover.model.config
        mean = float(getattr(config, "flat_drain", 0.3))
        return max(0.05, float(self._rng(rover).normal(loc=mean, scale=mean / 6.0)))


class SafeRegolith(TerrainPatch):
    """Hard, stable ground: low energy cost, no damage."""

    terrain_type = TerrainType.SAFE_REGOLITH
    color = "#d2b48c"

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rover.battery -= self._flat_drain(rover)
        self._traction(rover)
        self._clamp_rover(rover)


class Boulders(TerrainPatch):
    """Physical obstacle; navigation must never enter this cell."""

    terrain_type = TerrainType.BOULDERS
    color = "#4d4d4d"
    traversable = False

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        # Defensive fallback: a correct navigation strategy never enters here.
        if self._rng(rover).random() < 0.4:
            damage = self._rng(rover).normal(loc=15.0, scale=4.0)
            rover.hull_condition -= max(0.0, float(damage))
        rover.current_speed = 0.0
        rover.battery -= max(0.0, float(self._rng(rover).normal(loc=1.5, scale=0.3)))
        self._clamp_rover(rover)


class LooseSand(TerrainPatch):
    """Wheel slip, speed reduction and increased energy consumption."""

    terrain_type = TerrainType.LOOSE_SAND
    color = "#e6cc80"

    def slope_risk(self, config) -> float:
        """0 on flat sand, 1 at the embedding slope (see ``sand_embed_slope_deg``).

        Field data: rovers in cohesionless sand slip moderately on 10 deg and
        embed on 17 deg (analog tests, Rothrock et al. 2016 "SPOC"); the
        Curiosity slip model reaches 100% slip at 18 deg; Curiosity slipped
        77% in the Hidden Valley sand already at about 4 deg (Arvidson et
        al. 2017). ``(slope / embed) ** exponent`` passes through these
        anchors: 0.12 at 10 deg, 1 at 17 deg.
        """

        if not getattr(config, "sand_slope_model", False):
            return 0.0
        embed = max(1e-6, float(config.sand_embed_slope_deg))
        ratio = max(0.0, self.slope) / embed
        return min(1.0, ratio ** float(config.sand_slope_exponent))

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        config = rover.model.config
        risk = self.slope_risk(config)
        # Sinkage slip of loose soil (flat sand: Beta(3, 5), mean 0.375),
        # rising to full slip at the embedding slope.
        slip_factor = float(rng.beta(a=3.0, b=5.0))
        slip_factor += (1.0 - slip_factor) * risk
        rover.current_speed *= max(0.0, 1.0 - slip_factor)

        # Spinning wheels cost energy: more slip, more drain.
        drain = float(rng.lognormal(mean=0.75 + slip_factor, sigma=0.3))
        rover.battery -= max(0.0, drain)
        # Grinding sand wears the wheels.
        rover.wheel_condition -= max(0.0, float(rng.normal(loc=0.5, scale=0.2)))
        # The slope adds its work. Its slip is already in the sand slip above
        # when the sand slope model is on (the firm-ground traction of Wang
        # et al. does not hold in loose soil).
        self._traction(rover, apply_slip=not getattr(config, "sand_slope_model", False))

        # The rover can dig itself in (the Spirit scenario), the more likely
        # the steeper the sand. It always gets out again; how long it takes
        # depends on its wheels.
        stuck = float(config.sand_stuck_probability)
        stuck += (1.0 - stuck) * risk
        if rng.random() < stuck:
            rover.current_speed = 0.0
            rover.is_digging = True
            rover.dig_steps = 0
        self._clamp_rover(rover)


class Ventifacts(TerrainPatch):
    """Sharp rocks that damage wheels; LIDAR sees only boulders, not these."""

    terrain_type = TerrainType.VENTIFACTS
    color = "#8b4513"

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        damage = float(rng.exponential(scale=6.0))
        rover.wheel_condition -= max(0.0, damage)
        # Sharp rocks also hit the chassis.
        rover.hull_condition -= max(0.0, float(rng.exponential(scale=1.0)))
        rover.current_speed *= max(0.0, float(rng.normal(loc=0.85, scale=0.05)))
        rover.battery -= max(0.0, float(rng.normal(loc=0.8, scale=0.1)))
        self._traction(rover)
        self._clamp_rover(rover)


class SteepSlope(TerrainPatch):
    """Crater slope with a risk of overturning the rover."""

    terrain_type = TerrainType.STEEP_SLOPE
    color = "#ff6666"

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        traction = None
        if getattr(rover.model.config, "traction_model", False):
            # Wang et al. (2015): the slope work and slip follow from the
            # P3-AT's rolling resistance and grip; the rover overturns when
            # the side force exceeds its lateral grip and it slides down
            # the wall sideways.
            rover.battery -= self._flat_drain(rover)
            traction = self._traction(rover)
            falls = traction is not None and traction.lateral_slide
        else:
            drain = float(
                rng.normal(loc=0.5 + math.exp(0.05 * self.slope), scale=0.3)
            )
            rover.battery -= max(0.1, drain)
            steepness_factor = self.slope - 26.0
            fall_prob = 1.0 / (1.0 + math.exp(-0.25 * steepness_factor))
            falls = rng.random() < fall_prob
        if falls:
            rover.is_overturned = True
            hull_damage = float(rng.normal(loc=40.0, scale=10.0))
            wheel_damage = float(rng.normal(loc=25.0, scale=8.0))
            rover.hull_condition -= max(0.0, hull_damage)
            rover.wheel_condition -= max(0.0, wheel_damage)
            rover.current_speed = 0.0
        else:
            # Climbing a crater wall strains the wheels even without a fall.
            rover.wheel_condition -= max(0.0, float(rng.normal(loc=2.0, scale=1.0)))
        self._clamp_rover(rover)


class DeepShadow(TerrainPatch):
    """Shadow that accelerates battery discharge with exposure time."""

    terrain_type = TerrainType.DEEP_SHADOW
    color = "#1a1a1a"

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        base_drain = 4.0 + (0.75 * rover.shadow_exposure_time)
        drain = float(rng.normal(loc=base_drain, scale=0.4))
        rover.battery -= max(0.0, drain)
        # Long exposure to the cold damages the electronics in the hull.
        if rover.shadow_exposure_time >= 3:
            rover.hull_condition -= max(0.0, float(rng.normal(loc=1.5, scale=0.5)))
        self._traction(rover)
        self._clamp_rover(rover)


class DustStorm(TerrainPatch):
    """Dust limits RGB visibility but not LIDAR."""

    terrain_type = TerrainType.DUST_STORM
    color = "#b38b6d"

    def apply_effect(self, rover: Pioneer3DXAgent) -> None:
        rng = self._rng(rover)
        # Each of the base_vision_range rings stays visible with probability
        # p, which falls with time spent in the dust. A binomial is bounded by
        # the normal range by construction: dust never improves visibility.
        base_range = int(getattr(rover, "base_vision_range", rover.vision_range))
        visibility = clamp(0.85 - 0.15 * rover.dust_exposure_time, 0.05, 1.0)
        rover.vision_range = int(rng.binomial(n=max(0, base_range), p=visibility))
        rover.battery -= max(0.0, float(rng.normal(loc=1.2, scale=0.3)))
        # Abrasive dust wears wheels and hull.
        rover.wheel_condition -= max(0.0, float(rng.normal(loc=0.8, scale=0.3)))
        rover.hull_condition -= max(0.0, float(rng.normal(loc=0.6, scale=0.3)))
        self._traction(rover)
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
