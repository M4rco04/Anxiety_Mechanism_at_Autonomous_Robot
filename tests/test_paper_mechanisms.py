"""Mechanisms taken from Bielecki et al. (2017, 2025): slip alarm, sand trap,
short-term memory with context imprinting and multi-leg goal missions."""

from __future__ import annotations

import math

import numpy as np
import pytest

from config.config import HomeostatConfig
from src.agents.homeostat import Homeostat
from src.environment.terrain import LooseSand, SafeRegolith, Ventifacts
from src.model.types import hex_to_rgb
from src.navigation.board import HexGridBoard
from src.navigation.types import NavigationDecision
from tests.conftest import add_rover, layout, make_model


class FirstMove:
    def choose_next(self, rover, observation):
        actions = HexGridBoard(rover.model).actions(observation.position, observation)
        return NavigationDecision(actions[0], "test move") if actions else None

    def statistics(self):
        return {}


def _slip(homeostat):
    return homeostat.update(
        delta_battery=0.0,
        target_speed=1.0,
        current_speed=0.0,
        hull_condition=100.0,
        wheel_condition=100.0,
        current_slope=0.0,
    )


def test_slip_alarm_after_consecutive_slip_steps():
    homeostat = Homeostat(HomeostatConfig())
    first = _slip(homeostat)
    assert first.instantaneous < HomeostatConfig().s_crit
    assert first.alarm is None
    second = _slip(homeostat)
    assert second.critical and second.alarm == "slip"


def test_specification_has_no_slip_alarm():
    homeostat = Homeostat(HomeostatConfig.specification())
    _slip(homeostat)
    assert _slip(homeostat).alarm is None


def _sand_rover(**overrides):
    model = make_model(
        width=6,
        height=6,
        terrain_layout=layout(6, 6, terrain="LooseSand"),
        num_rovers=0,
        seed=2,
        sand_stuck_probability=1.0,
        **overrides,
    )
    return add_rover(model, (2, 2), navigation_mode="emotional", strategy=FirstMove())


def test_rover_digs_out_of_sand_and_learns_to_fear_it():
    rover = _sand_rover(sand_stuck_min_steps=3, sand_stuck_max_steps=3)
    rover.step()
    assert rover.mission_status == "digging_out"
    position = rover.pos
    for _ in range(3):
        rover.step()
        assert rover.pos == position
    assert rover.mission_status == "active"
    assert rover.stuck_events == 1
    # Spinning wheels raise the slip alarm -> fear of sand.
    assert rover.fear_intensity(hex_to_rgb(LooseSand.color)) > 0.5


def test_sand_never_traps_the_rover_for_good():
    # Even with no escape chance the rover is out after the max steps.
    rover = _sand_rover(
        sand_escape_probability=0.0, sand_stuck_min_steps=2, sand_stuck_max_steps=8
    )
    rover.step()
    assert rover.is_digging and rover.is_active
    position = rover.pos
    for _ in range(7):
        rover.step()
        assert rover.pos == position
        assert rover.mission_status == "digging_out"
    rover.step()
    assert not rover.is_digging
    assert rover.mission_status == "active"


def test_worn_wheels_make_digging_out_slower():
    def dig_time(wheels: float) -> float:
        total = 0
        for seed in range(40):
            rover = _sand_rover(
                sand_escape_probability=1.0,
                sand_stuck_min_steps=1,
                sand_stuck_max_steps=30,
                sand_stuck_wheel_wear=0.0,
            )
            rover.model.rng = np.random.default_rng(seed)
            rover.step()
            rover.wheel_condition = wheels
            while rover.is_digging:
                rover.step()
                total += 1
        return total / 40

    assert dig_time(100.0) == 1.0  # healthy wheels: out after the minimum
    assert dig_time(30.0) > 2.0


def test_context_imprint_covers_preceding_unfamiliar_terrain():
    model = make_model(width=6, height=6, terrain_layout=layout(6, 6), num_rovers=0, seed=3)
    rover = add_rover(model, (2, 2), navigation_mode="emotional")
    sand, rocks = hex_to_rgb(LooseSand.color), hex_to_rgb(Ventifacts.color)
    safe = hex_to_rgb(SafeRegolith.color)
    rover.exposures[safe] = 50  # long familiar with regolith
    rover.exposures[sand] = 1
    rover.short_term_memory.extend([((1, 1), safe), ((1, 2), sand), ((2, 2), rocks)])

    rover._imprint(rocks)

    assert rover.fear_intensity(rocks) == pytest.approx(1.0)
    expected = model.config.context_imprint_weight * math.exp(
        -1 / model.config.habituation_steps
    )
    assert rover.fear_intensity(sand) == pytest.approx(expected)
    assert rover.fear_intensity(safe) == 0.0  # habituated: no panic
    assert rover.context_imprints == 1


def test_goal_mission_continues_with_next_waypoint():
    model = make_model(
        width=10,
        height=10,
        terrain_layout=layout(10, 10),
        num_rovers=1,
        seed=4,
        mission_mode="goal_navigation",
        navigation_mode="online",
        goal_waypoints=2,
    )
    rover = model.rovers()[0]
    first_target = rover.target
    assert rover.waypoints_left == 1
    rover.mission_status = "goal_reached"
    model._apply_mission_controller()
    assert rover.mission_status == "active"
    assert rover.waypoints_reached == 1
    assert rover.waypoints_left == 0
    assert rover.target is not None and rover.target != first_target
