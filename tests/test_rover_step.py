"""Rover step, sensor and exposure tests."""

from __future__ import annotations

from src.environment.terrain import DeepShadow, DustStorm, SafeRegolith
from src.navigation.board import HexGridBoard
from src.navigation.types import NavigationDecision
from tests.conftest import add_rover, layout, make_model


class FirstMoveStrategy:
    def __init__(self):
        self.calls = 0

    def choose_next(self, rover, observation):
        self.calls += 1
        board = HexGridBoard(rover.model)
        actions = board.actions(observation.position, observation)
        if not actions:
            return NavigationDecision(None, "none", "no_path")
        return NavigationDecision(actions[0], "test move")

    def statistics(self):
        return {"calls": self.calls}


def test_apply_effect_exactly_once_after_successful_move(monkeypatch):
    calls = {"count": 0}
    original = SafeRegolith.apply_effect

    def wrapped(self, rover):
        calls["count"] += 1
        return original(self, rover)

    monkeypatch.setattr(SafeRegolith, "apply_effect", wrapped)
    strategy = FirstMoveStrategy()
    model = make_model(
        width=6,
        height=6,
        terrain_layout=layout(6, 6),
        num_rovers=1,
        seed=13,
        strategy_factory=lambda mode, config, seed: strategy,
    )
    rover = model.rovers()[0]
    model.step()
    assert calls["count"] == 1
    assert rover.moves == 1
    assert rover.mission_status in {"active", "exploration_complete"}


def test_no_effect_when_strategy_returns_no_move(monkeypatch):
    calls = {"count": 0}
    original = SafeRegolith.apply_effect

    def wrapped(self, rover):
        calls["count"] += 1
        return original(self, rover)

    monkeypatch.setattr(SafeRegolith, "apply_effect", wrapped)

    class StopStrategy:
        def choose_next(self, rover, observation):
            return NavigationDecision(None, "stop", "no_path")

        def statistics(self):
            return {}

    model = make_model(
        width=5,
        height=5,
        terrain_layout=layout(5, 5),
        num_rovers=1,
        seed=2,
        strategy_factory=lambda mode, config, seed: StopStrategy(),
    )
    model.step()
    assert calls["count"] == 0
    assert model.rovers()[0].mission_status == "no_path"


def test_dust_limits_rgb_but_not_lidar():
    terrain_layout = layout(
        6,
        6,
        overrides={(1, 0): "Boulders", (0, 1): "DustStorm"},
    )
    model = make_model(
        width=6,
        height=6,
        terrain_layout=terrain_layout,
        num_rovers=0,
        seed=2,
    )
    rover = add_rover(model, (0, 0))
    rover.heading = (0, 1)
    rover.vision_range = 0
    readings = rover.read_rgb_cameras()
    assert (0, 0) in readings
    assert len(readings) == 1
    assert (1, 0) in rover.read_lidar()


def test_exposure_counters_increment_and_reset():
    model = make_model(width=4, height=4, num_rovers=0, seed=2)
    rover = add_rover(model, (0, 0))
    rover._update_exposure(DeepShadow.terrain_type, moved=True)
    assert rover.shadow_exposure_time == 1
    rover._update_exposure(DustStorm.terrain_type, moved=True)
    assert rover.shadow_exposure_time == 0
    assert rover.dust_exposure_time == 1
    rover.vision_range = 0
    rover._update_exposure(SafeRegolith.terrain_type, moved=True)
    assert rover.dust_exposure_time == 0
    assert rover.shadow_exposure_time == 0
    assert rover.vision_range == rover.base_vision_range


def test_destroyed_rover_does_not_move():
    model = make_model(width=4, height=4, num_rovers=0, seed=2)
    rover = add_rover(model, (0, 0))
    rover.is_destroyed = True
    rover.mission_status = "destroyed"
    position = rover.pos
    rover.step()
    assert rover.pos == position
