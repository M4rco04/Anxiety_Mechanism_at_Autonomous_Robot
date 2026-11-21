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

NAVIGATION_MODES = ("scaffold", "online", "emotional", "fuzzy", "swarm_emotional")
MISSION_MODES = ("exploration", "goal_navigation")
# Terrain source: windows of the real maps in ``real_maps/`` (Jezero crater on
# Mars, the Atacama Desert on Earth).
MAP_SOURCES = ("mars", "atacama")
# Size of one hex cell [m] when ``cell_m`` is not set (see real_maps.py).
DEFAULT_CELL_M = {"mars": 50.0, "atacama": 20.0}

DEFAULT_TERRAIN_COSTS: dict[str, float] = {
    "SafeRegolith": 1.0,
    "LooseSand": 2.0,
    "Ventifacts": 1.8,
    "SteepSlope": 2.5,
    "DeepShadow": 2.0,
    "DustStorm": 1.8,
    "Boulders": math.inf,
}

# Spread (std) of the route cost. ``terrain_costs`` is the mean; the std is
# the mean times the coefficient of variation of the battery drain of one
# entry (Monte Carlo of ``apply_effect`` with the traction and sand-slope models over the
# slopes of the real-map cells; shadow and dust over exposures 0-3; see
# ``uv run validate``). Only energy: multi-step events (stuck in sand,
# overturn recovery) and damage are what the anxiety has to learn, so they
# are left out. Safe regolith varies most: its drain follows the slope.
DEFAULT_TERRAIN_COST_STD: dict[str, float] = {
    "SafeRegolith": 0.70,
    "LooseSand": 0.71,
    "Ventifacts": 0.76,
    "SteepSlope": 0.92,
    "DeepShadow": 0.38,
    "DustStorm": 0.66,
    "Boulders": 0.0,
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
    w5: float = 3.0
    k: float = 0.05
    # Traction limit of the Pioneer P3-AT: the steepest slope it can climb
    # with the mean friction of Wang et al. (2015), sin a + f_r cos a = mu
    # -> 19.7 deg (15.7-23.9 over the measured mu). Steeper ground is felt
    # as dangerous. (Before: 25 deg, a hand-picked value; spec: 15 deg.)
    alpha_safe: float = 20.0
    beta: float = 0.7
    # Raised from 40 so that only a larger danger is recorded as stress
    # (fear imprint); ordinary bumps and mild losses no longer trigger it.
    s_crit: float = 55.0
    rearm_factor: float = 0.8

    # Model changes against the specification (see README "Homeostat"):
    # damage_based - hull/wheel terms come from damage taken in this step
    #   (w_hull_damage * dC_hull + w_wheel_damage * dC_wheel) instead of the
    #   overall condition, so stress points at the terrain that hurts now.
    # imprint_on_instantaneous - imprint fear when the instantaneous stress
    #   crosses s_crit (acute event on the current cell) instead of the
    #   smoothed stress, which lags behind and imprints the wrong cell.
    # reimprint_below - a terrain can be imprinted again only when its fear
    #   has decayed below this intensity (replaces the global re-arm).
    damage_based: bool = True
    w_hull_damage: float = 4.0
    # Same weight as the hull: with 8 one entry into sharp rocks (ventifacts,
    # ~6% wheel wear) imprinted fear almost every time.
    w_wheel_damage: float = 4.0
    imprint_on_instantaneous: bool = True
    reimprint_below: float = 0.8
    # Slip alarm (Bielecki & Bielecki 2025): "a noticeable drop in velocity
    # despite constant motor force" is an alarming inner-detector state on its
    # own. Slip >= slip_alarm for slip_alarm_steps steps in a row triggers an
    # imprint even when the stress is below s_crit. 0 steps = disabled.
    slip_alarm: float = 0.8
    slip_alarm_steps: int = 3
    # Accumulated-stress alarm (chronic danger): stress below s_crit adds up
    # per terrain. Every step without an acute alarm adds
    # max(0, S_loss - chronic_rest) to the sum of the terrain the rover
    # stands on; when the sum reaches chronic_alarm, that terrain is
    # imprinted like after an acute event. So terrain that harms slowly
    # (dust, sand, a deepening shadow) is learned too, and earlier. S_loss
    # is S_inst without the slope term: only real losses add up.
    # chronic_alarm = 0 disables it.
    chronic_rest: float = 15.0
    chronic_alarm: float = 60.0
    # Optional leaky accumulator: every step all sums are multiplied by
    # ``chronic_retention`` (e.g. 0.9 = half-life of ~6.6 steps), so
    # occasional mild losses are forgotten. 1.0 = no leak (default): the sums
    # grow during the whole mission. Off because on maps 0-199 the leak cost
    # the anxious rover 4-5 points of survival in exploration (it learned
    # sand and shadow later) and gained nothing significant in the goal test.
    chronic_retention: float = 1.0
    # Graded fear: the imprint intensity follows the size of the danger
    # instead of always being 1.0. An acute or slip alarm imprints
    # clamp(S_inst / fear_full_stress, acute_min_intensity, 1); a chronic
    # alarm imprints ``chronic_intensity``. Repeated imprints of the same
    # terrain add up (``learn_fear``), so a fear grows with experience.
    # graded_fear = False restores the all-or-nothing imprint (1.0).
    graded_fear: bool = True
    fear_full_stress: float = 110.0
    acute_min_intensity: float = 0.5
    chronic_intensity: float = 0.35

    @classmethod
    def specification(cls) -> HomeostatConfig:
        """Original model from instruction.md section 6."""

        return cls(
            w5=2.0,
            alpha_safe=15.0,
            s_crit=75.0,
            damage_based=False,
            imprint_on_instantaneous=False,
            slip_alarm_steps=0,
            chronic_alarm=0.0,
            graded_fear=False,
        )

    def validate(self) -> None:
        non_negative = {
            "w1": self.w1,
            "w2": self.w2,
            "w3": self.w3,
            "w4": self.w4,
            "w5": self.w5,
            "k": self.k,
            "s_crit": self.s_crit,
            "w_hull_damage": self.w_hull_damage,
            "w_wheel_damage": self.w_wheel_damage,
            "chronic_rest": self.chronic_rest,
            "chronic_alarm": self.chronic_alarm,
        }
        for name, value in non_negative.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Homeostat parameter {name} must be finite and >= 0")
        if not 0.0 <= self.beta <= 1.0:
            raise ValueError("Homeostat beta must be in [0, 1]")
        if not 0.0 <= self.rearm_factor <= 1.0:
            raise ValueError("Homeostat rearm_factor must be in [0, 1]")
        if not 0.0 <= self.slip_alarm <= 1.0:
            raise ValueError("Homeostat slip_alarm must be in [0, 1]")
        if self.slip_alarm_steps < 0:
            raise ValueError("Homeostat slip_alarm_steps must be >= 0")
        if not 0.0 <= self.reimprint_below <= 1.0:
            raise ValueError("Homeostat reimprint_below must be in [0, 1]")
        if not 0.0 <= self.s_crit <= 100.0:
            raise ValueError("Homeostat s_crit must be in [0, 100]")
        if not 0.0 <= self.chronic_retention <= 1.0:
            raise ValueError("Homeostat chronic_retention must be in [0, 1]")
        if not math.isfinite(self.fear_full_stress) or self.fear_full_stress <= 0:
            raise ValueError("Homeostat fear_full_stress must be positive")
        for name in ("acute_min_intensity", "chronic_intensity"):
            if not 0.0 < getattr(self, name) <= 1.0:
                raise ValueError(f"Homeostat {name} must be in (0, 1]")


@dataclass(frozen=True)
class SimulationConfig:
    """Complete, serializable simulation configuration."""

    # Grid and population
    width: int = 50
    height: int = 50
    seed: int | None = None
    num_rovers: int = 3

    # Terrain source (src/environment/real_maps.py). For a real map the seed
    # picks the window of the map; ``real_map_origin_m`` fixes it instead
    # (metres from the south-west corner of the map). ``real_map_overlays``
    # adds what a geological map does not contain: shadows of steep slopes
    # and dust storms (weather). ``real_map_relief`` adds landforms smaller
    # than the mapped units (craters, dunes, outcrops, ravines, boulder fields; see
    # ``RealMapGenerator``). ``cell_m`` = size of one hex cell [m]
    # (None = the map's default, ``DEFAULT_CELL_M``).
    map_source: str = "mars"
    real_map_origin_m: tuple[float, float] | None = None
    real_map_overlays: bool = True
    real_map_relief: bool = True
    cell_m: float | None = None

    # Mission and navigation
    navigation_mode: str = "scaffold"
    mission_mode: str = "exploration"
    targets: tuple[tuple[int, int], ...] | None = None
    max_steps: int = 500
    exploration_budget: int = 500
    coverage_target: float = 0.8
    allow_exploration_fallback: bool = False
    goal_target_fraction: float = 0.7
    # Exploration starts around the rover: it drives to the nearest unseen
    # cell, and the explored area grows outwards from the start like a disc.
    # Unseen cells up to ``explore_home_slack`` cells farther from the start
    # than the nearest unseen one cost nothing extra; each cell beyond that
    # costs ``explore_home_weight``. Weight 0 = nearest unseen cell only
    # (on open ground the rover then drifts away in a line).
    explore_home_weight: float = 1.0
    explore_home_slack: float = 4.0
    # Exploration is optional, so a rover does not cross much terrain it
    # fears (or distrusts) only to see more: routes whose summed aversion
    # exceeds this many fully feared cells are not taken. When nothing else
    # is left, the rover stops exploring.
    explore_max_aversion: float = 1.0
    # Before driving onto a neighbour it has never seen (outside the camera
    # field of view), the rover turns in place to look at it first.
    look_before_step: bool = True

    # Sensors
    vision_range: int = 3
    lidar_range: int = 2
    rgb_fov_deg: float = 120.0
    # Camera noise (std per RGB channel). Real cameras never read a colour
    # exactly, so recognising a feared terrain is imperfect.
    rgb_noise_sigma: float = 5.0
    signature_jitter: int = 0

    # Anxiety
    # Route cost of a fully feared cell. Checked on the real maps (uv run
    # tune, seeds 0-99, S_crit x fear_weight x alpha_safe): all 27 settings
    # scored within 0.8 points, inside the noise of 100 maps, so the value
    # was kept (only S_crit = 30 was consistently, slightly worse).
    fear_weight: float = 30.0
    fear_decay: float = 0.005
    fear_rgb_tolerance: float = 24.0
    radio_fear_gain: float = 0.8
    retreat_fear_threshold: float = 0.5
    allow_forced_fear_visit: bool = True
    # Fuzzy rover (no learning): expert rules give every cell a caution
    # 0..1 (src/navigation/fuzzy.py). ``fuzzy_weight`` * caution is the extra
    # route cost; the rover steps back when the retreat rule fires at least
    # to ``fuzzy_retreat_level``.
    fuzzy_weight: float = 30.0
    fuzzy_retreat_level: float = 0.5

    # Short-term memory (Bielecki et al. 2017, 2025): the rover keeps the
    # circumstances of the last ``stm_steps`` steps. On an alarm the current
    # terrain is imprinted with full intensity and the terrain seen just
    # before it (the preceding circumstances) with ``context_imprint_weight``.
    # Familiar terrain is conditioned weakly (latent inhibition): the context
    # intensity is multiplied by exp(-exposures / habituation_steps) and
    # skipped below ``min_context_intensity``.
    stm_steps: int = 5
    context_imprint_weight: float = 0.5
    habituation_steps: float = 3.0
    min_context_intensity: float = 0.15

    # Radio
    R_radio: int = 20
    radio_enabled: bool = True
    # Swarm components (for control experiments): share imprinted fears by
    # radio, and share the map of visited cells.
    swarm_share_fear: bool = True
    swarm_share_map: bool = True
    # Swarm exploration: each rover explores the part of the terrain that is
    # closer to it than to its radio peers (its own area), and does not pick
    # targets farther than ``swarm_cohesion_radius`` from any peer, so the
    # swarm stays together within radio range. A rover that loses contact
    # drives back to where it last heard the others.
    swarm_split_area: bool = True
    swarm_cohesion_radius: int = 12

    # Terrain interpretation
    terrain_costs: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TERRAIN_COSTS)
    )
    terrain_cost_std: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TERRAIN_COST_STD)
    )
    terrain_risk: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TERRAIN_RISK)
    )
    max_slope_deg: float = 90.0
    # Wheel-ground traction of the Pioneer P3-AT (Wang et al. 2015,
    # src/environment/traction.py): slip and slope work on every cell from
    # the measured rolling resistance, shear modulus and friction; overturns
    # on crater walls when the side force exceeds lateral grip; turning in
    # place costs skid work. False = the previous slope-free effects.
    traction_model: bool = True
    # Battery drain of driving one cell of flat firm ground [%]; the slope
    # work and turns are charged in this unit.
    flat_drain: float = 0.3
    # Risk-sensitive route cost: the planners use
    #     (mean + lambda * std) / (1 + lambda * std_SafeRegolith)
    # (terrain_costs, terrain_cost_std) instead of the mean alone, so a
    # terrain with an uncertain cost looks more expensive; safe regolith stays
    # at 1, the unit of all other route constants. ``risk_aversion`` is lambda for every variant. The
    # anxious variants add ``stress_risk_aversion`` * min(1, S / S_crit):
    # a stressed anxious rover is more cautious (0 = off).
    risk_aversion: float = 0.5
    stress_risk_aversion: float = 1.5

    # Loose sand can bog the rover down (the Spirit scenario from Bielecki &
    # Bielecki 2025). On entering sand the rover gets stuck with
    # ``sand_stuck_probability`` and spins its wheels (full slip, battery
    # drain, wheel wear, stress). After ``sand_stuck_min_steps`` it digs out
    # each step with ``sand_escape_probability`` x wheel condition / 100,
    # and at the latest after ``sand_stuck_max_steps``. The rover is never
    # trapped for good: it is lost only if its battery or wheels run out
    # while digging, so it lives to learn the fear of sand.
    sand_stuck_probability: float = 0.12
    sand_escape_probability: float = 0.35
    sand_stuck_min_steps: int = 3
    sand_stuck_max_steps: int = 12
    sand_stuck_battery: float = 2.5
    sand_stuck_wheel_wear: float = 1.0
    # Sand on a slope (field data, see LooseSand.slope_risk): slip and the
    # chance to get stuck rise with (slope / sand_embed_slope_deg) **
    # sand_slope_exponent, from the flat-sand values to full slip and
    # certain embedding at 17 deg (analog rover in cohesionless sand:
    # moderate slip on 10 deg, embedding on 17 deg; Curiosity's slip model
    # reaches 100% at 18 deg). False = slope-independent sand.
    sand_slope_model: bool = True
    sand_embed_slope_deg: float = 17.0
    sand_slope_exponent: float = 4.0

    # Goal test: prefer targets whose shortest route crosses at least this
    # many hazardous cells, as in the 2025 experiment where the sand pits lay
    # on the way to the goal. 0 = any target.
    goal_min_hazard_cells: int = 2
    # Goal test: goals lie on safe regolith (a place to stop at); the danger
    # is on the way there. False = any traversable cell (before real maps).
    goal_on_safe_ground: bool = True
    # Goal test: prefer goals that can also be reached without crossing
    # hazardous terrain, so the danger on the shortest route can be learned
    # and avoided (the 2025 experiment: the robot can go around the sand
    # pits). On the real maps wide hazardous belts would otherwise force
    # every variant through them.
    goal_requires_detour: bool = True
    # Goal test: number of consecutive goals (legs); the simulation ends when
    # every rover has reached all of them. The fear memory is kept
    # between legs, so what the rover learns on one leg protects it later.
    goal_waypoints: int = 3
    # Goal navigation uses LRTA* (LSS-LRTA*, Koenig & Sun 2009): the number
    # of cells searched around the rover before every step, whose h values
    # are learned at once. 1 = the classic LRTA* of Korf (1990).
    lrta_lookahead: int = 100

    # Overturn recovery: an overturned rover spends this many steps getting
    # back on its wheels (standing still, draining battery, stress rising)
    # and then continues the mission. 0 = an overturn ends the mission.
    # ``overturn_recovery_probability``: chance that the rover gets back up
    # at all; otherwise the overturn breaks it and ends its mission.
    overturn_recovery_steps: int = 3
    overturn_recovery_probability: float = 0.7
    overturn_recovery_battery: float = 2.0

    # Solar charging: a rover whose battery drops below ``solar_charge_start``
    # drives to the nearest known SafeRegolith cell (src/navigation/energy.py),
    # stops there and charges ``solar_charge_rate`` percent per step until it
    # reaches ``solar_charge_stop``.
    solar_charging: bool = True
    solar_charge_rate: float = 5.0
    solar_charge_start: float = 40.0
    solar_charge_stop: float = 90.0
    # Dust storms block sunlight: charging within ``dust_shading_radius``
    # cells of a dust storm runs at ``dust_solar_fraction`` of the normal
    # rate. Opportunity's arrays gave ~700 Wh/sol in clear air and 148 Wh/sol
    # in the 2007 storm (JPL, 20 Jul 2007): 148 / 700 = 0.21. The charging
    # planner prefers safe ground outside the shade.
    dust_solar_fraction: float = 0.21
    dust_shading_radius: int = 2

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
        object.__setattr__(self, "terrain_cost_std", dict(self.terrain_cost_std))
        if self.targets is not None:
            object.__setattr__(self, "targets", tuple(tuple(p) for p in self.targets))
        if self.real_map_origin_m is not None:
            object.__setattr__(
                self, "real_map_origin_m", tuple(float(v) for v in self.real_map_origin_m)
            )

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
        if self.map_source not in MAP_SOURCES:
            raise ValueError(
                f"Unknown map_source {self.map_source!r}; expected one of {MAP_SOURCES}"
            )
        if self.cell_m is not None and not (math.isfinite(self.cell_m) and self.cell_m > 0):
            raise ValueError("cell_m must be positive")
        if self.flat_drain < 0:
            raise ValueError("flat_drain must be >= 0")
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
        if self.explore_home_weight < 0 or self.explore_home_slack < 0:
            raise ValueError("explore_home_weight and explore_home_slack must be >= 0")
        if self.explore_max_aversion < 0:
            raise ValueError("explore_max_aversion must be >= 0")
        if self.fuzzy_weight < 0 or not 0.0 <= self.fuzzy_retreat_level <= 1.0:
            raise ValueError("fuzzy_weight >= 0 and fuzzy_retreat_level in [0, 1]")
        if self.R_radio < 0:
            raise ValueError("R_radio must be >= 0")
        if not 1 <= self.swarm_cohesion_radius <= max(1, self.R_radio):
            raise ValueError("swarm_cohesion_radius must be in [1, R_radio]")
        if self.solar_charge_rate < 0:
            raise ValueError("solar_charge_rate must be >= 0")
        if not 0.0 <= self.solar_charge_start <= self.solar_charge_stop <= 100.0:
            raise ValueError(
                "solar charge thresholds must satisfy 0 <= start <= stop <= 100"
            )
        if self.stm_steps < 1:
            raise ValueError("stm_steps must be >= 1")
        if self.context_imprint_weight < 0 or self.habituation_steps <= 0:
            raise ValueError("context_imprint_weight >= 0 and habituation_steps > 0")
        for name in ("sand_stuck_probability", "sand_escape_probability"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if not 1 <= self.sand_stuck_min_steps <= self.sand_stuck_max_steps:
            raise ValueError("sand stuck steps must satisfy 1 <= min <= max")
        if not 0.0 <= self.dust_solar_fraction <= 1.0 or self.dust_shading_radius < 0:
            raise ValueError("dust_solar_fraction in [0, 1] and dust_shading_radius >= 0")
        if self.sand_embed_slope_deg <= 0 or self.sand_slope_exponent <= 0:
            raise ValueError("sand_embed_slope_deg and sand_slope_exponent must be positive")
        if self.lrta_lookahead < 1:
            raise ValueError("lrta_lookahead must be >= 1")
        if self.goal_waypoints < 1:
            raise ValueError("goal_waypoints must be >= 1")
        if self.goal_min_hazard_cells < 0:
            raise ValueError("goal_min_hazard_cells must be >= 0")
        if self.overturn_recovery_steps < 0:
            raise ValueError("overturn_recovery_steps must be >= 0")
        if not 0.0 <= self.overturn_recovery_probability <= 1.0:
            raise ValueError("overturn_recovery_probability must be in [0, 1]")
        if self.overturn_recovery_battery < 0:
            raise ValueError("overturn_recovery_battery must be >= 0")
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
        for name, std in self.terrain_cost_std.items():
            if not math.isfinite(std) or std < 0:
                raise ValueError(f"Terrain cost std for {name} must be finite and >= 0")
        if self.risk_aversion < 0 or self.stress_risk_aversion < 0:
            raise ValueError("risk_aversion and stress_risk_aversion must be >= 0")

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
        cost_std = raw.get("terrain_cost_std")
        if isinstance(cost_std, Mapping):
            raw["terrain_cost_std"] = {
                key: float(value) for key, value in cost_std.items()
            }
        if raw.get("targets") is not None:
            raw["targets"] = tuple(tuple(p) for p in raw["targets"])
        if raw.get("real_map_origin_m") is not None:
            raw["real_map_origin_m"] = tuple(raw["real_map_origin_m"])
        # Ignore unknown keys from older/newer experiment files when possible.
        known = {item.name for item in fields(cls)}
        raw = {key: value for key, value in raw.items() if key in known}
        return cls(**raw)

    @property
    def resolved_cell_m(self) -> float:
        """Size of one hex cell [m] for this map source."""

        if self.cell_m is not None:
            return float(self.cell_m)
        return DEFAULT_CELL_M[self.map_source]

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


__all__ = [
    "DEFAULT_CELL_M",
    "DEFAULT_CONFIG",
    "DEFAULT_TERRAIN_COSTS",
    "DEFAULT_TERRAIN_COST_STD",
    "DEFAULT_TERRAIN_RISK",
    "MAP_SOURCES",
    "MISSION_MODES",
    "NAVIGATION_MODES",
    "HomeostatConfig",
    "SimulationConfig",
]
