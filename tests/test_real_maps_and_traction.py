"""Real-map terrain, GeoPackage rasterizer and the P3-AT traction model."""

from __future__ import annotations

import math

import numpy as np
import pytest

from config.config import SimulationConfig
from src.environment.gpkg import rasterize_rings
from src.environment.real_maps import (
    BOULDER,
    SAND,
    SLOPE,
    RealMapGenerator,
    WindowRules,
    hex_neighbours,
    window_stats,
)
from src.environment.terrain import SafeRegolith, SteepSlope, TerrainType
from src.environment.traction import (
    FRICTION_MU_MAX,
    FRICTION_MU_MEAN,
    FRICTION_MU_MIN,
    climb_limit_deg,
    drive_effect,
    icr_coefficient,
    slip_for_demand,
    traction_ratio,
    turn_energy_factor,
)
from src.model.model import MarsSimulation
from tests.conftest import add_rover, layout, make_model


# -- GeoPackage rasterizer ---------------------------------------------------
def test_rasterize_square_with_hole():
    outer = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=float)
    hole = np.array([[3, 3], [3, 7], [7, 7], [7, 3], [3, 3]], dtype=float)
    mask = rasterize_rings([outer, hole], (0.0, 0.0), 1.0, (12, 12))
    assert mask.sum() == 100 - 16
    assert not mask[5, 5] and mask[1, 1] and not mask[11, 11]


# -- traction (Wang et al. 2015) ----------------------------------------------
def test_icr_coefficient_matches_eq_45():
    assert icr_coefficient(0.0) == pytest.approx(1.4728)
    assert icr_coefficient(10.0) < icr_coefficient(1.0) < icr_coefficient(0.0)


def test_traction_grows_with_slip_and_is_bounded_by_friction():
    values = [traction_ratio(s) for s in (0.001, 0.01, 0.1, 1.0)]
    assert values == sorted(values)
    assert values[-1] < FRICTION_MU_MEAN
    assert slip_for_demand(0.0371) < 0.01
    assert slip_for_demand(0.5) == 1.0


def test_climb_limit_brackets_the_manufacturer_grade():
    spec = math.degrees(math.atan(0.40))  # Pioneer AT: max grade 40%
    assert climb_limit_deg(FRICTION_MU_MIN) < spec < climb_limit_deg(FRICTION_MU_MAX)
    assert climb_limit_deg(FRICTION_MU_MEAN) == pytest.approx(19.7, abs=0.1)
    assert SimulationConfig().homeostat.alpha_safe == pytest.approx(20.0)


def test_steep_slopes_slip_and_overturn_gentle_ground_does_not():
    rng = np.random.default_rng(0)
    gentle = [drive_effect(10.0, rng) for _ in range(2000)]
    steep = [drive_effect(36.0, rng) for _ in range(2000)]
    assert max(o.slip for o in gentle) < 0.2
    assert not any(o.lateral_slide for o in gentle)
    assert 0.55 < np.mean([o.lateral_slide for o in steep]) < 0.75
    assert np.mean([o.slip >= 0.7 for o in steep]) > 0.5


def test_turn_costs_less_with_larger_cells():
    assert turn_energy_factor(math.pi / 3, 50.0) < turn_energy_factor(math.pi / 3, 20.0)
    assert turn_energy_factor(0.0, 20.0) == 0.0


def test_turning_drains_battery_only_with_traction_model():
    for traction, drained in ((True, True), (False, False)):
        model = make_model(6, 6, terrain_layout=layout(6, 6), num_rovers=0, traction_model=traction)
        rover = add_rover(model, (2, 2))
        before = rover.battery
        rover._face((2, 2), (2, 1))  # turn around: 180 deg
        assert (rover.battery < before) is drained


def test_previous_slope_model_is_kept_behind_the_switch():
    def overturns(traction: bool) -> float:
        model = make_model(3, 3, num_rovers=0, traction_model=traction, terrain_layout=layout(3, 3))
        hits = 0
        for _ in range(400):
            rover = add_rover(model, (0, 0))
            SteepSlope(1, model, 1.0, 36.0).apply_effect(rover)
            hits += rover.is_overturned
            model.grid.remove_agent(rover)
            model.schedule.remove(rover)
        return hits / 400

    assert overturns(False) > 0.85
    assert 0.5 < overturns(True) < 0.8


def test_flat_regolith_drain_is_unchanged():
    model = make_model(3, 3, num_rovers=0, terrain_layout=layout(3, 3))
    drains = []
    for _ in range(300):
        rover = add_rover(model, (0, 0))
        SafeRegolith(1, model, 0.0, 0.0).apply_effect(rover)
        drains.append(100.0 - rover.battery)
        model.grid.remove_agent(rover)
        model.schedule.remove(rover)
    assert np.mean(drains) == pytest.approx(0.3, abs=0.03)


# -- real maps -----------------------------------------------------------------
@pytest.mark.parametrize("key", ["mars", "atacama"])
def test_windows_are_deterministic_and_follow_the_rules(key):
    a = RealMapGenerator(key, 30, 30, 7)
    b = RealMapGenerator(key, 30, 30, 7)
    c = RealMapGenerator(key, 30, 30, 8)
    assert np.array_equal(a.classes, b.classes) and a.origin_m == b.origin_m
    assert a.origin_m != c.origin_m
    stats = window_stats(a.classes)
    rules = WindowRules()
    assert a.accepted
    assert stats["boulders"] <= rules.max_boulders and stats["slope"] <= rules.max_slope
    assert stats["safe"] >= rules.min_safe


def test_fixed_origin_and_slopes_follow_the_class():
    g = RealMapGenerator("mars", 20, 20, 1, origin_m=(30000.0, 30000.0))
    assert g.origin_m == (30000.0, 30000.0)
    slopes = g.slopes()
    assert np.all(slopes[g.classes == SLOPE] >= 30.0)
    assert np.all(slopes[g.classes == BOULDER] >= 45.0)
    gentle = (g.classes != SLOPE) & (g.classes != BOULDER)
    assert np.all(slopes[gentle] <= 15.0)


def test_slope_of_a_place_does_not_depend_on_the_seed():
    a = RealMapGenerator("mars", 10, 10, 1, origin_m=(30000.0, 30000.0))
    b = RealMapGenerator("mars", 10, 10, 99, origin_m=(30000.0, 30000.0))
    assert np.array_equal(a.slopes(), b.slopes())


@pytest.mark.parametrize("key", ["mars", "atacama"])
def test_landforms_belong_to_the_place_not_the_seed(key):
    origin = (12000.0, 9000.0)
    a = RealMapGenerator(key, 40, 40, 1, origin_m=origin)
    b = RealMapGenerator(key, 40, 40, 77, origin_m=origin)
    assert np.array_equal(a.classes, b.classes)
    plain = RealMapGenerator(key, 40, 40, 1, origin_m=origin, relief=False)
    assert np.array_equal(plain.classes, plain.map_classes)
    assert np.array_equal(a.map_classes, plain.map_classes)
    # Landforms change only drivable ground; the boulders of the map stay.
    assert np.all(a.classes[a.map_classes == BOULDER] == BOULDER)


@pytest.mark.parametrize("key", ["mars", "atacama"])
def test_accepted_windows_have_varied_hazards(key):
    for seed in range(5):
        g = RealMapGenerator(key, 50, 50, seed)
        stats = window_stats(g.classes)
        assert g.accepted
        assert all(stats[k] >= 0.01 for k in ("sand", "ventifacts", "slope"))


def test_dune_slip_faces_stand_at_the_angle_of_repose():
    faces = 0
    for seed in range(5):
        g = RealMapGenerator("atacama", 50, 50, seed)
        face = (g.classes == SLOPE) & np.isfinite(g.slope_override)
        slopes = g.slopes()
        assert np.all((slopes[face] >= 30.0) & (slopes[face] <= 34.0))
        assert np.all(g.map_classes[face] == SAND)
        faces += int(face.sum())
    assert faces > 0


def test_craters_have_steep_walls_and_sandy_floors():
    from src.environment.real_maps import _craters

    walls = floors = 0
    for seed in range(5):
        g = RealMapGenerator("mars", 50, 50, seed)
        x = g.origin_m[0] + g._cx
        y = g.origin_m[1] + g._cy
        for cx, cy, radius, fresh in _craters("mars", x, y, g.relief_params):
            dist = np.hypot(x - cx, y - cy)
            changed = g.classes != g.map_classes
            floor = changed & (dist < 0.55 * radius)
            assert np.all(g.classes[floor] == SAND)
            floors += int(floor.sum())
            if fresh:
                walls += int(np.sum(changed & (g.classes == SLOPE) & (dist < radius + 25.0)))
    assert walls > 0 and floors > 0


def test_hex_neighbours_match_mesa_grid():
    model = make_model(6, 6, terrain_layout=layout(6, 6), num_rovers=0)
    for pos in [(0, 0), (1, 1), (2, 3), (3, 2), (5, 5)]:
        expected = set(model.grid.get_neighborhood(pos, include_center=False, radius=1))
        assert set(hex_neighbours(pos, 6, 6)) == expected


@pytest.mark.parametrize("key", ["mars", "atacama"])
def test_model_runs_on_every_map_source(key):
    model = MarsSimulation(SimulationConfig(
        width=20, height=20, seed=3, num_rovers=1, map_source=key,
        navigation_mode="emotional", max_steps=20,
    ))
    assert model.map_info["map"] == key
    for _ in range(20):
        model.step()
    assert model.step_count > 0


def test_goals_lie_on_safe_ground():
    model = MarsSimulation(SimulationConfig(
        width=30, height=30, seed=4, num_rovers=1, map_source="mars",
        navigation_mode="online", mission_mode="goal_navigation",
    ))
    target = model.rovers()[0].target
    assert model.terrain_at(target).terrain_type == TerrainType.SAFE_REGOLITH


def test_config_round_trip_keeps_map_fields(tmp_path):
    config = SimulationConfig(map_source="atacama", real_map_origin_m=(1.0, 2.0), cell_m=25.0)
    path = tmp_path / "c.json"
    config.save(path)
    loaded = SimulationConfig.load(path)
    assert loaded == config and loaded.resolved_cell_m == 25.0
    with pytest.raises(ValueError):
        SimulationConfig(map_source="moon").validate()


# -- field-data terrain corrections --------------------------------------------
def _sand_entries(slope: float, n: int = 600, **overrides):
    from src.environment.terrain import LooseSand

    model = make_model(3, 3, num_rovers=0, terrain_layout=layout(3, 3), **overrides)
    slips, stuck = [], 0
    for _ in range(n):
        rover = add_rover(model, (0, 0))
        LooseSand(1, model, 0.0, slope).apply_effect(rover)
        if rover.is_digging:
            stuck += 1
        else:
            slips.append(1.0 - rover.current_speed)
        model.grid.remove_agent(rover)
        model.schedule.remove(rover)
    return (float(np.mean(slips)) if slips else 1.0), stuck / n


def test_sand_slips_more_and_embeds_on_slopes():
    flat_slip, flat_stuck = _sand_entries(0.0)
    mid_slip, _ = _sand_entries(10.0)
    steep_slip, steep_stuck = _sand_entries(17.0)
    assert flat_slip == pytest.approx(0.375, abs=0.03)
    assert flat_stuck == pytest.approx(0.12, abs=0.04)
    assert flat_slip < mid_slip < 0.6  # moderate slip on 10 deg
    assert steep_slip > 0.99 and steep_stuck == 1.0  # embedding on 17 deg


def test_sand_slope_model_switch_restores_flat_sand():
    slip, _ = _sand_entries(17.0, sand_slope_model=False, traction_model=False)
    assert slip == pytest.approx(0.375, abs=0.03)


def test_dust_storm_slows_charging():
    from src.environment.terrain import DustStorm

    overrides = {(3, 3): "DustStorm"}
    model = make_model(8, 8, terrain_layout={
        **layout(8, 8, overrides=overrides)}, num_rovers=0)
    assert model.terrain_at((3, 3)).__class__ is DustStorm
    near = add_rover(model, (3, 4))
    far = add_rover(model, (7, 7))
    for rover in (near, far):
        rover.battery = 30.0
        rover._charge_step()
    rate = model.config.solar_charge_rate
    assert far.battery == pytest.approx(30.0 + rate)
    assert near.battery == pytest.approx(30.0 + rate * model.config.dust_solar_fraction)
