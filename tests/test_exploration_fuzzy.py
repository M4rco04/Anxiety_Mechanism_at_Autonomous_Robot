"""Shared exploration, look-before-step, escape, chronic alarm, fuzzy rover."""

from __future__ import annotations

import pytest

from src.analytics.benchmark import rate_interval, wilson_interval
from src.environment.terrain import DeepShadow
from src.model.types import hex_distance, hex_to_rgb
from src.navigation.fuzzy import FuzzyInputs, caution, retreat_degree
from src.navigation.observation import build_observation
from src.navigation.registry import create_strategy
from tests.conftest import TERRAIN_BY_NAME, add_rover, layout, make_model

SIZE = 40
START = (20, 20)


def _world(mode: str, overrides=None, terrain: str = "SafeRegolith", size: int = SIZE, **config):
    model = make_model(
        width=size,
        height=size,
        terrain_layout=layout(size, size, terrain=terrain, overrides=overrides),
        num_rovers=0,
        seed=3,
        navigation_mode=mode,
        **config,
    )
    model.running = True  # the model starts stopped when built with no rovers
    return model


def _rover(model, position, mode: str, mission: str = "exploration"):
    return add_rover(
        model,
        position,
        navigation_mode=mode,
        mission_mode=mission,
        strategy=create_strategy(mode, model.config, 3),
    )


# ----------------------------------------------------------------------
# Exploration
# ----------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["online", "emotional", "fuzzy"])
def test_exploration_starts_around_the_rover(mode):
    model = _world(mode)
    rover = _rover(model, START, mode)
    farthest = 0
    for _ in range(40):
        model.step()
        farthest = max(farthest, hex_distance(START, rover.pos))
    # The rover explores its surroundings instead of driving off in a line
    # (40 steps in a line would take it to the edge of the map, 19 cells).
    assert farthest <= 10
    near = model.grid.get_neighborhood(START, include_center=True, radius=4)
    assert all(cell in rover.known_terrain for cell in near)


def test_rover_looks_before_driving_onto_unseen_cell():
    model = _world("online")
    rover = _rover(model, START, "online")
    turned = False
    for _ in range(40):
        known = set(rover.known_terrain)
        before = rover.pos
        model.step()
        if rover.pos != before:
            assert rover.pos in known
        else:
            turned = True
    assert turned and rover.turns > 0


def test_rover_stops_exploring_rather_than_cross_a_wide_feared_belt():
    # A pocket of safe ground surrounded by shadow in every direction.
    pocket = {START, (21, 20), (20, 21)}
    model = _world("emotional", terrain="DeepShadow", overrides={c: "SafeRegolith" for c in pocket})
    rover = _rover(model, START, "emotional")
    rover.learn_fear(hex_to_rgb(DeepShadow.color), intensity=1.0, source="self")
    for _ in range(30):
        model.step()
    assert rover.mission_status == "exploration_complete"
    assert rover.pos in pocket


# ----------------------------------------------------------------------
# Anxiety additions
# ----------------------------------------------------------------------
def test_rover_plans_a_way_out_of_feared_terrain():
    # Deep inside a shadow: every neighbour is feared as much as this cell.
    model = _world("emotional", terrain="DeepShadow", overrides={(24, 20): "SafeRegolith"}, vision_range=5)
    rover = _rover(model, START, "emotional")
    rover._face(START, (24, 20))
    rover.learn_fear(hex_to_rgb(DeepShadow.color), intensity=1.0, source="self")
    decision = rover.strategy.choose_next(rover, build_observation(rover))
    assert decision.reason == "leaving feared terrain"
    assert hex_distance(decision.next_position, (24, 20)) < hex_distance(START, (24, 20))


def test_stress_below_the_alarm_adds_up_per_terrain():
    model = _world("emotional")
    rover = _rover(model, START, "emotional")
    sand, dust = (230, 204, 128), (179, 139, 109)
    homeostat = model.config.homeostat
    step = homeostat.chronic_rest + homeostat.chronic_alarm / 2.5
    assert not rover._chronic_alarm(sand, step)
    assert not rover._chronic_alarm(dust, step)  # another terrain, own sum
    assert not rover._chronic_alarm(sand, step)
    assert rover._chronic_alarm(sand, step)
    # Stress the rover tolerates never adds up.
    assert not any(rover._chronic_alarm(dust, homeostat.chronic_rest) for _ in range(50))


def test_chronic_alarm_can_be_disabled():
    from config.config import HomeostatConfig

    model = _world("emotional", homeostat=HomeostatConfig(chronic_alarm=0.0))
    rover = _rover(model, START, "emotional")
    assert not any(rover._chronic_alarm((1, 2, 3), 39.0) for _ in range(50))


# ----------------------------------------------------------------------
# Fuzzy rover
# ----------------------------------------------------------------------
def _inputs(**changes) -> FuzzyInputs:
    values = {"risk": 0.0, "slope": 5.0, "energy": 1.0, "condition": 100.0, "battery": 100.0, "stress": 0.0}
    values.update(changes)
    return FuzzyInputs(**values)


def test_fuzzy_rules_order_the_terrain():
    safe = caution(_inputs())
    sand = caution(_inputs(risk=0.15, energy=2.0))
    rocks = caution(_inputs(risk=0.35, energy=1.8))
    slope = caution(_inputs(risk=0.5, slope=36.0, energy=2.5))
    assert safe == 0.0
    assert safe < sand < rocks < slope
    assert slope == pytest.approx(1.0)


def test_fuzzy_rules_depend_on_the_rover_state():
    rocks = _inputs(risk=0.35, energy=1.8)
    assert caution(_inputs(risk=0.35, energy=1.8, condition=20.0)) > caution(rocks)
    assert caution(_inputs(risk=0.35, energy=1.8, stress=60.0)) > caution(rocks)
    shadow = _inputs(risk=0.2, energy=2.0)
    assert caution(_inputs(risk=0.2, energy=2.0, battery=20.0)) > caution(shadow)
    assert caution(_inputs(risk=0.2, energy=2.0, drain=7.0)) > caution(shadow)


def test_fuzzy_retreat_rule():
    assert retreat_degree(0.0, 80.0) == 0.0  # safe ground: never
    assert retreat_degree(0.9, 0.0) == 1.0  # very risky cell: always
    assert retreat_degree(0.3, 0.0) == 0.0  # risky, but calm
    assert retreat_degree(0.3, 60.0) == 1.0  # risky and alarmed


def test_fuzzy_rover_drives_around_a_steep_slope():
    # A wall of steep slope between start and goal, with one gap far north.
    wall = {(10, y): "SteepSlope" for y in range(3, 20)}
    model = make_model(
        width=20,
        height=20,
        terrain_layout={
            **layout(20, 20),
            **{cell: (TERRAIN_BY_NAME[name], 0.0, 36.0) for cell, name in wall.items()},
        },
        num_rovers=1,
        seed=8,
        navigation_mode="fuzzy",
        mission_mode="goal_navigation",
        targets=((16, 12),),
        goal_waypoints=1,
        max_steps=200,
    )
    rover = model.rovers()[0]
    while model.running:
        model.step()
    assert rover.mission_status == "goal_reached"
    assert rover.overturns == 0
    assert all(model.terrain_at(cell).terrain_type.value != "SteepSlope" for cell in rover.path)


def test_fuzzy_rover_retreats_from_dangerous_ground():
    model = _world("fuzzy", overrides={(5, 5): "Ventifacts"}, size=12)
    rover = _rover(model, (5, 5), "fuzzy")
    rover.wheel_condition = 20.0  # a damaged rover takes no risks
    decision = rover.strategy.choose_next(rover, build_observation(rover))
    assert decision.reason.startswith("retreating")
    assert model.terrain_at(decision.next_position).terrain_type.value == "SafeRegolith"
    assert rover.strategy.statistics()["retreats"] == 1


# ----------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------
def test_rate_interval_accounts_for_rovers_of_one_run():
    # One rover per run: the Wilson interval.
    assert rate_interval([1, 0, 1, 1], [1, 1, 1, 1]) == wilson_interval(3, 4)
    # At 100% the interval still contains the rate (no negative error bar).
    assert rate_interval([1] * 30, [1] * 30)[1] >= 1.0
    # Three rovers that always share their fate: wider than Wilson on 60 rovers.
    hits, sizes = [3, 0] * 10, [3] * 20
    low, high = rate_interval(hits, sizes)
    wilson_low, wilson_high = wilson_interval(30, 60)
    assert high - low > wilson_high - wilson_low
