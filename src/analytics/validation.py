"""Model validation: real-map pipeline, traction model and terrain effects.

Used by ``uv run validate`` (root/validate.py). Every check returns plain
data (dicts / DataFrames) so the report and the tests can share it.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from config.config import HomeostatConfig, SimulationConfig
from src.environment.real_maps import (
    CLASS_LABELS,
    REAL_MAPS,
    RealMapGenerator,
    WindowRules,
    load_raster,
    window_stats,
)
from src.environment.terrain import (
    DeepShadow,
    DustStorm,
    LooseSand,
    SafeRegolith,
    SteepSlope,
    Ventifacts,
)
from src.environment.traction import (
    FRICTION_MU_MAX,
    FRICTION_MU_MEAN,
    FRICTION_MU_MIN,
    ICR_CHI_SPIN,
    climb_limit_deg,
    drive_effect,
    slip_for_demand,
    turn_energy_factor,
)

# Independent reference values (not used to build the model).
# Pioneer 2/3 user manual, Appendix "Specifications": traversable slope max
# (grade) 40% for the AT, 25% for the DX.
P3AT_SPEC_MAX_GRADE = 0.40
# Wang et al. (2015), Table 3: measured ICR coefficient on the tightest path.
MEASURED_CHI_TIGHTEST = 1.4662

TERRAIN_SLOPES = {
    # Slope ranges of the real-map cells (real_maps.py, foothill +4 included).
    "SafeRegolith": (2.0, 14.0),
    "LooseSand": (2.0, 14.0),
    "Ventifacts": (3.0, 15.0),
    "SteepSlope": (30.0, 42.0),
    "DeepShadow": (2.0, 14.0),
    "DustStorm": (2.0, 14.0),
}
TERRAIN_CLASSES = {
    "SafeRegolith": SafeRegolith,
    "LooseSand": LooseSand,
    "Ventifacts": Ventifacts,
    "SteepSlope": SteepSlope,
    "DeepShadow": DeepShadow,
    "DustStorm": DustStorm,
}


# ----------------------------------------------------------------------
# 1. Real maps
# ----------------------------------------------------------------------
def polygon_area_shares(key: str) -> dict[str, float]:
    """Class shares from the polygon areas (shoelace, holes subtract)."""

    import tempfile
    import zipfile
    from pathlib import Path

    from src.environment.gpkg import read_features
    from src.environment.real_maps import REAL_MAPS_DIR, _class_code

    spec = REAL_MAPS[key]
    source = REAL_MAPS_DIR / spec.source
    areas: dict[int, float] = {}
    with tempfile.TemporaryDirectory() as tmp:
        if source.suffix == ".zip":
            with zipfile.ZipFile(source) as archive:
                member = spec.member or archive.namelist()[0]
                archive.extract(member, tmp)
                gpkg = Path(tmp) / member
        else:
            gpkg = source
        for label, rings in read_features(gpkg, "sim_terrain"):
            code = _class_code(label)
            if code is None:
                continue
            # Signed ring areas: exterior and hole rings have opposite
            # orientation in GeoPackage/WKB, so the sum is the net area.
            total = 0.0
            for ring in rings:
                x, y = ring[:, 0], ring[:, 1]
                total += 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            areas[code] = areas.get(code, 0.0) + abs(total)
    whole = sum(areas.values())
    return {CLASS_LABELS[c]: a / whole for c, a in sorted(areas.items())}


def map_pipeline_checks(windows: int = 300) -> pd.DataFrame:
    """Raster vs polygon shares, and unfiltered window sampling vs raster."""

    rows = []
    for key in REAL_MAPS:
        polygon = polygon_area_shares(key)
        raster = load_raster(key)
        raster_share = {
            CLASS_LABELS[c]: float(np.mean(raster.classes == c)) for c in CLASS_LABELS
        }
        permissive = WindowRules(
            max_boulders=1.0, min_safe=0.0, min_hazard=0.0, max_hazard=1.0,
            max_slope=1.0, min_connected=0.0, min_hazard_types=0, attempts=1,
        )
        sampled = np.zeros(len(CLASS_LABELS))
        accepted = np.zeros(len(CLASS_LABELS))
        for seed in range(windows):
            g = RealMapGenerator(key, 50, 50, seed, rules=permissive, relief=False)
            sampled += [np.mean(g.classes == c) for c in CLASS_LABELS]
            a = RealMapGenerator(key, 50, 50, seed)
            accepted += [np.mean(a.map_classes == c) for c in CLASS_LABELS]
        sampled /= windows
        accepted /= windows
        for index, (code, label) in enumerate(CLASS_LABELS.items()):
            rows.append({
                "map": key,
                "class": label,
                "polygons": polygon.get(label, 0.0),
                "raster_10m": raster_share[label],
                "random_windows": sampled[index],
                "accepted_windows": accepted[index],
            })
    return pd.DataFrame(rows)


def determinism_check() -> dict[str, bool]:
    result = {}
    for key in REAL_MAPS:
        a = RealMapGenerator(key, 50, 50, 123)
        b = RealMapGenerator(key, 50, 50, 123)
        c = RealMapGenerator(key, 50, 50, 124)
        result[key] = bool(
            np.array_equal(a.classes, b.classes)
            and a.origin_m == b.origin_m
            and a.origin_m != c.origin_m
        )
    return result


# ----------------------------------------------------------------------
# 2. Traction model vs the paper and the manufacturer
# ----------------------------------------------------------------------
def traction_checks() -> dict[str, Any]:
    spec_deg = math.degrees(math.atan(P3AT_SPEC_MAX_GRADE))
    return {
        "climb_limit_mu_min": climb_limit_deg(FRICTION_MU_MIN),
        "climb_limit_mu_mean": climb_limit_deg(FRICTION_MU_MEAN),
        "climb_limit_mu_max": climb_limit_deg(FRICTION_MU_MAX),
        "spec_max_grade_deg": spec_deg,
        "spec_within_range": climb_limit_deg(FRICTION_MU_MIN)
        <= spec_deg
        <= climb_limit_deg(FRICTION_MU_MAX),
        "chi_model": ICR_CHI_SPIN,
        "chi_measured": MEASURED_CHI_TIGHTEST,
        "chi_rel_error": (ICR_CHI_SPIN - MEASURED_CHI_TIGHTEST) / MEASURED_CHI_TIGHTEST,
        "slip_flat": slip_for_demand(0.0371),
        "turn60_factor_20m": turn_energy_factor(math.pi / 3, 20.0),
        "turn60_factor_50m": turn_energy_factor(math.pi / 3, 50.0),
    }


def slope_response(slopes=(0, 5, 10, 14, 18, 22, 26, 30, 36, 42), n: int = 20000) -> pd.DataFrame:
    """Slip, energy and overturn (lateral slide) vs slope, and the old model."""

    rng = np.random.default_rng(7)
    rows = []
    for slope in slopes:
        out = [drive_effect(float(slope), rng) for _ in range(n)]
        slip = np.array([o.slip for o in out])
        energy = np.array([o.energy_factor for o in out])
        slide = np.array([o.lateral_slide for o in out])
        rows.append({
            "slope_deg": slope,
            "mean_slip": slip.mean(),
            "p_slip_alarm": float(np.mean(slip >= HomeostatConfig().slip_alarm)),
            "energy_factor": energy.mean(),
            "p_overturn_new": float(slide.mean()),
            "p_overturn_old": 1.0 / (1.0 + math.exp(-0.25 * (slope - 26.0))),
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# 3. Terrain effects per entry (Monte Carlo of apply_effect)
# ----------------------------------------------------------------------
class _Probe:
    """Minimal rover stand-in for apply_effect."""

    def __init__(self, model) -> None:
        self.model = model
        self.battery = 100.0
        self.wheel_condition = 100.0
        self.hull_condition = 100.0
        self.current_speed = 1.0
        self.base_vision_range = 3
        self.vision_range = 3
        self.shadow_exposure_time = 0
        self.dust_exposure_time = 0
        self.is_overturned = False
        self.is_digging = False
        self.dig_steps = 0
        self.last_slip = 0.0


class _ProbeModel:
    def __init__(self, config: SimulationConfig, seed: int) -> None:
        self.config = config
        self.rng = np.random.default_rng(seed)


def terrain_effects(traction: bool = True, n: int = 20000, seed: int = 11) -> pd.DataFrame:
    # traction=False: the previous terrain physics (no traction, flat sand).
    config = SimulationConfig(traction_model=traction, sand_slope_model=traction)
    model = _ProbeModel(config, seed)
    rng = np.random.default_rng(seed + 1)
    rows = []
    for name, cls in TERRAIN_CLASSES.items():
        lo, hi = TERRAIN_SLOPES[name]
        battery, wheels, hull, slow, overturn, stuck = [], [], [], [], [], []
        for i in range(n):
            patch = cls.__new__(cls)
            patch.model = model
            patch.slope = float(rng.uniform(lo, hi))
            probe = _Probe(model)
            if name == "DeepShadow":
                probe.shadow_exposure_time = i % 4
            if name == "DustStorm":
                probe.dust_exposure_time = i % 4
            patch.apply_effect(probe)
            battery.append(100.0 - probe.battery)
            wheels.append(100.0 - probe.wheel_condition)
            hull.append(100.0 - probe.hull_condition)
            slow.append(1.0 - probe.current_speed)
            overturn.append(probe.is_overturned)
            stuck.append(probe.is_digging)
        battery = np.array(battery)
        rows.append({
            "terrain": name,
            "slope_range": f"{lo:g}-{hi:g}",
            "battery": battery.mean(),
            "battery_cv": battery.std() / max(battery.mean(), 1e-9),
            "wheels": float(np.mean(wheels)),
            "hull": float(np.mean(hull)),
            "speed_loss": float(np.mean(slow)),
            "p_overturn": float(np.mean(overturn)),
            "p_stuck": float(np.mean(stuck)),
        })
    return pd.DataFrame(rows)


def window_stats_table(seeds: range = range(200)) -> pd.DataFrame:
    rows = []
    for key in REAL_MAPS:
        for seed in seeds:
            g = RealMapGenerator(key, 50, 50, seed)
            overlays = g.overlay_classes()
            for terrain, classes in (("map only", g.map_classes), ("map + landforms", g.classes)):
                info = window_stats(classes)
                if terrain == "map only":
                    info["shadow"] = info["dust"] = float("nan")
                else:
                    info["shadow"] = sum(v is DeepShadow for v in overlays.values()) / g.classes.size
                    info["dust"] = sum(v is DustStorm for v in overlays.values()) / g.classes.size
                info["hazard_types"] = sum(
                    info[k] >= 0.01 for k in ("sand", "ventifacts", "slope", "shadow", "dust")
                )
                info["attempts"] = g.attempts
                info["map"] = key
                info["terrain"] = terrain
                rows.append(info)
    return (pd.DataFrame(rows).groupby(["map", "terrain"], sort=False)
            .mean(numeric_only=True).reset_index())


__all__ = [
    "determinism_check",
    "dust_charging_check",
    "map_pipeline_checks",
    "polygon_area_shares",
    "sand_slope_response",
    "slope_response",
    "terrain_effects",
    "traction_checks",
    "window_stats_table",
]


# ----------------------------------------------------------------------
# 4. Field-data corrections: sand on slopes, dust and solar power
# ----------------------------------------------------------------------
SAND_FIELD_ANCHORS = {
    # slope [deg]: what the field data say
    4.0: "Curiosity, Hidden Valley sand: up to 77% slip at ~4 deg (megaripples)",
    10.0: "analog rover, cohesionless sand: moderate slip",
    17.0: "analog rover, cohesionless sand: embedding",
    18.0: "Curiosity slip model: 100% slip",
}


def sand_slope_response(slopes=(0, 4, 8, 10, 12, 14, 17, 18), n: int = 20000, seed: int = 5) -> pd.DataFrame:
    """Sand slip (entries without embedding) and embedding probability vs slope."""

    config = SimulationConfig()
    model = _ProbeModel(config, seed)
    rows = []
    for slope in slopes:
        slips, stuck = [], 0
        for _ in range(n):
            patch = LooseSand.__new__(LooseSand)
            patch.model = model
            patch.slope = float(slope)
            probe = _Probe(model)
            patch.apply_effect(probe)
            if probe.is_digging:
                stuck += 1
            else:
                slips.append(1.0 - probe.current_speed)
        rows.append({
            "slope_deg": slope,
            "mean_slip": float(np.mean(slips)) if slips else 1.0,
            "p_stuck": stuck / n,
            "field_data": SAND_FIELD_ANCHORS.get(float(slope), ""),
        })
    return pd.DataFrame(rows)


def dust_charging_check() -> dict[str, float]:
    config = SimulationConfig()
    clear = float(config.solar_charge_rate)
    shaded = clear * float(config.dust_solar_fraction)
    span = float(config.solar_charge_stop) - float(config.solar_charge_start)
    return {
        "opportunity_clear_wh": 700.0,
        "opportunity_storm_wh": 148.0,
        "measured_fraction": 148.0 / 700.0,
        "model_fraction": float(config.dust_solar_fraction),
        "charge_rate_clear": clear,
        "charge_rate_shaded": shaded,
        "steps_40_to_90_clear": span / clear,
        "steps_40_to_90_shaded": span / shaded,
    }
