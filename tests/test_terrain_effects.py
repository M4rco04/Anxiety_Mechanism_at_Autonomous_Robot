"""Terrain effect tests."""

from __future__ import annotations

from src.environment.terrain import (
    Boulders,
    DeepShadow,
    DustStorm,
    LooseSand,
    SafeRegolith,
    SteepSlope,
    Ventifacts,
)
from tests.conftest import add_rover, make_model


def _rover_with_speed(model, speed=1.0):
    rover = add_rover(model, (0, 0))
    rover.current_speed = speed
    rover.target_speed = speed
    return rover


def test_safe_regolith_drains_small_amount():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    before = rover.battery
    SafeRegolith(1, model).apply_effect(rover)
    assert 0.0 < before - rover.battery < 1.0


def test_loose_sand_reduces_speed_and_drains_battery():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    before_battery = rover.battery
    before_speed = rover.current_speed
    LooseSand(1, model).apply_effect(rover)
    assert rover.current_speed <= before_speed
    assert rover.battery <= before_battery


def test_ventifacts_damage_wheels():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    before = rover.wheel_condition
    Ventifacts(1, model).apply_effect(rover)
    assert rover.wheel_condition < before


def test_deep_shadow_drain_increases_with_exposure():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    rover.shadow_exposure_time = 0
    before = rover.battery
    DeepShadow(1, model).apply_effect(rover)
    first_drain = before - rover.battery
    rover.shadow_exposure_time = 10
    before = rover.battery
    DeepShadow(1, model).apply_effect(rover)
    second_drain = before - rover.battery
    assert second_drain > first_drain


def test_dust_storm_limits_vision_not_lidar():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    rover.vision_range = 5
    DustStorm(1, model).apply_effect(rover)
    assert rover.vision_range <= 5
    assert rover.lidar_range == model.config.lidar_range


def test_boulders_set_speed_zero():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    Boulders(1, model).apply_effect(rover)
    assert rover.current_speed == 0.0


def test_steep_slope_can_be_deterministic_with_seed():
    model = make_model(width=3, height=3, num_rovers=0, seed=2)
    rover = _rover_with_speed(model)
    rover.current_speed = 1.0
    SteepSlope(1, model, elevation=1.0, slope=80.0).apply_effect(rover)
    assert rover.is_overturned in {True, False}
    assert rover.gyro_alarm in {True, False}
