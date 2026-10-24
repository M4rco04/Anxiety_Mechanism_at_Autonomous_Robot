"""Simulation configuration for the Mars rover anxiety project.

This module is the single source of truth for numerical parameters.  The
defaults follow ``src/agents/instruction.md`` and are intentionally explicit
so that every experiment can be reproduced from a serialized configuration.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

NAVIGATION_MODES = ("scaffold", "online", "emotional", "swarm_emotional")
MISSION_MODES = ("exploration", "goal_navigation")

DEFAULT_TERRAIN_COSTS: dict[str, float] = {
    "SafeRegolith": 1.0,
    "LooseSand": 2.0,
    "Ventifacts": 1.8,
    "SteepSlope": 2.5,
    "DeepShadow": 2.0,
    "DustStorm": 1.8,
    "Boulders": math.inf,
}

DEFAULT_TERRAIN_RISK: dict[str, float] = {
    "SafeRegolith": 0.0,
    "LooseSand": 0.15,
    "Ventifacts": 0.35,
    "SteepSlope": 0.5,
    "DeepShadow": 0.2,
    "DustStorm": 0.15,
    "Boulders": 1.0,
}


@dataclass(frozen=True)
class HomeostatConfig:
    """Parameters of the homeostat equation from ``instruction.md`` section 6."""

    w1: float = 5.0
    w2: float = 15.0
    w3: float = 3.0
    w4: float = 2.5
    w5: float = 2.0
    k: float = 0.05
    alpha_safe: float = 15.0
    beta: float = 0.7
    s_crit: float = 75.0
    rearm_factor: float = 0.8

    def validate(self) -> None:
        non_negative = {
            "w1": self.w1,
            "w2": self.w2,
            "w3": self.w3,
            "w4": self.w4,
            "w5": self.w5,
            "k": self.k,
            "s_crit": self.s_crit,
        }
        for name, value in non_negative.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Homeostat parameter {name} must be finite and >= 0")
        if not 0.0 <= self.beta <= 1.0:
            raise ValueError("Homeostat beta must be in [0, 1]")
        if not 0.0 <= self.rearm_factor <= 1.0:
            raise ValueError("Homeostat rearm_factor must be in [0, 1]")
        if not 0.0 <= self.s_crit <= 100.0:
            raise ValueError("Homeostat s_crit must be in [0, 100]")


@dataclass(frozen=True)
class SimulationConfig:
    """Complete, serializable simulation configuration."""

    # Grid and population
    width: int = 50
    height: int = 50
    seed: int | None = None
    num_rovers: int = 3

    # Mission and navigation
    navigation_mode: str = "scaffold"
    mission_mode: str = "exploration"
    targets: tuple[tuple[int, int], ...] | None = None
    max_steps: int = 500
    exploration_budget: int = 500
    coverage_target: float = 0.8
    allow_exploration_fallback: bool = False
    goal_target_fraction: float = 0.7

    # Sensors
    vision_range: int = 3
    lidar_range: int = 2
    rgb_fov_deg: float = 120.0
    rgb_noise_sigma: float = 0.0
    signature_jitter: int = 0

    # Anxiety
    fear_weight: float = 30.0
    fear_decay: float = 0.005
    fear_rgb_tolerance: float = 24.0
    radio_fear_gain: float = 0.8
    retreat_fear_threshold: float = 0.5
    allow_forced_fear_visit: bool = True

    # Radio
    R_radio: int = 20
    radio_enabled: bool = True

    # Terrain interpretation
    terrain_costs: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TERRAIN_COSTS)
    )
    terrain_risk: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TERRAIN_RISK)
    )
    max_slope_deg: float = 90.0

    # Spawning
    spawn_on_safe: bool = True
    min_spawn_distance: int = 2
    allow_rover_overlap: bool = False

    # Presentation only; never affects simulation physics.
    display_tick_ms: int = 450

    homeostat: HomeostatConfig = field(default_factory=HomeostatConfig)

    def __post_init__(self) -> None:
        # Frozen dataclasses can still contain mutable mappings.  Normalize
        # them once so callers cannot accidentally share/update a dictionary.
        object.__setattr__(self, "terrain_costs", dict(self.terrain_costs))
        object.__setattr__(self, "terrain_risk", dict(self.terrain_risk))
        if self.targets is not None:
            object.__setattr__(self, "targets", tuple(tuple(p) for p in self.targets))

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Grid dimensions must be positive")
        if self.num_rovers < 0:
            raise ValueError("num_rovers must be >= 0")
        if self.navigation_mode not in NAVIGATION_MODES:
            raise ValueError(
                f"Unknown navigation_mode {self.navigation_mode!r}; "
                f"expected one of {NAVIGATION_MODES}"
            )
        if self.mission_mode not in MISSION_MODES:
            raise ValueError(
                f"Unknown mission_mode {self.mission_mode!r}; "
                f"expected one of {MISSION_MODES}"
            )
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.exploration_budget <= 0:
            raise ValueError("exploration_budget must be positive")
        if not 0.0 <= self.coverage_target <= 1.0:
            raise ValueError("coverage_target must be in [0, 1]")
        if not 0.0 <= self.goal_target_fraction <= 1.0:
            raise ValueError("goal_target_fraction must be in [0, 1]")
        if self.vision_range < 0 or self.lidar_range < 0:
            raise ValueError("Sensor ranges must be >= 0")
        if not 0.0 <= self.rgb_fov_deg <= 360.0:
            raise ValueError("rgb_fov_deg must be in [0, 360]")
        if self.rgb_noise_sigma < 0:
            raise ValueError("rgb_noise_sigma must be >= 0")
        if self.signature_jitter < 0:
            raise ValueError("signature_jitter must be >= 0")
        if self.fear_weight < 0 or self.fear_decay < 0:
            raise ValueError("fear_weight and fear_decay must be >= 0")
        if self.fear_rgb_tolerance < 0:
            raise ValueError("fear_rgb_tolerance must be >= 0")
        if self.R_radio < 0:
            raise ValueError("R_radio must be >= 0")
        if self.max_slope_deg <= 0:
            raise ValueError("max_slope_deg must be positive")
        if self.min_spawn_distance < 0:
            raise ValueError("min_spawn_distance must be >= 0")
        if self.display_tick_ms <= 0:
            raise ValueError("display_tick_ms must be positive")
        if not 0.0 <= self.retreat_fear_threshold <= 1.0:
            raise ValueError("retreat_fear_threshold must be in [0, 1]")

        for name, costs in self.terrain_costs.items():
            if costs < 0 or (math.isinf(costs) and costs < 0):
                raise ValueError(f"Terrain cost for {name} must be non-negative")
        for name, risk in self.terrain_risk.items():
            if not 0.0 <= risk <= 1.0:
                raise ValueError(f"Terrain risk for {name} must be in [0, 1]")

        if self.mission_mode == "exploration" and self.targets is not None:
            raise ValueError("Explicit targets are only allowed in goal_navigation mode")
        if self.targets is not None:
            if len(self.targets) < self.num_rovers:
                raise ValueError("Not enough explicit targets for all rovers")
            for x, y in self.targets:
                if not (0 <= x < self.width and 0 <= y < self.height):
                    raise ValueError(f"Target {(x, y)} is outside the grid")

        self.homeostat.validate()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # asdict handles nested dataclasses; normalize Infinity for JSON.
        data["terrain_costs"] = {
            key: (None if math.isinf(value) else value)
            for key, value in data["terrain_costs"].items()
        }
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SimulationConfig:
        raw = dict(data)
        homeostat_data = raw.get("homeostat")
        if isinstance(homeostat_data, Mapping):
            raw["homeostat"] = HomeostatConfig(**homeostat_data)
        costs = raw.get("terrain_costs")
        if isinstance(costs, Mapping):
            raw["terrain_costs"] = {
                key: (math.inf if value is None else float(value))
                for key, value in costs.items()
            }
        risk = raw.get("terrain_risk")
        if isinstance(risk, Mapping):
            raw["terrain_risk"] = {key: float(value) for key, value in risk.items()}
        if raw.get("targets") is not None:
            raw["targets"] = tuple(tuple(p) for p in raw["targets"])
        # Ignore unknown keys from older/newer experiment files when possible.
        known = {item.name for item in fields(cls)}
        raw = {key: value for key, value in raw.items() if key in known}
        return cls(**raw)

    def replace(self, **changes: Any) -> SimulationConfig:
        return replace(self, **changes)

    def config_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> SimulationConfig:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


DEFAULT_CONFIG = SimulationConfig()
DEFAULT_CONFIG.validate()
SIMULATION_CONFIG = DEFAULT_CONFIG.to_dict()


def config_from_overrides(overrides: Mapping[str, Any] | None = None) -> SimulationConfig:
    """Create a validated config from a flat mapping of overrides."""

    config = DEFAULT_CONFIG
    if overrides:
        config = config.replace(**dict(overrides))
    config.validate()
    return config


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_TERRAIN_COSTS",
    "DEFAULT_TERRAIN_RISK",
    "MISSION_MODES",
    "NAVIGATION_MODES",
    "SIMULATION_CONFIG",
    "HomeostatConfig",
    "SimulationConfig",
    "config_from_overrides",
]
