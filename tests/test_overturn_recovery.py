"""Overturn recovery: the rover gets back on its wheels and can learn fear."""

from __future__ import annotations

from src.navigation.board import HexGridBoard
from src.navigation.types import NavigationDecision
from tests.conftest import add_rover, layout, make_model


class FirstMove:
    def choose_next(self, rover, observation):
        actions = HexGridBoard(rover.model).actions(observation.position, observation)
        return NavigationDecision(actions[0], "test move") if actions else None

    def statistics(self):
        return {}


def _overturned_rover(**overrides):
    # Very steep slope everywhere: entering any cell overturns the rover.
    model = make_model(
        width=6,
        height=6,
        terrain_layout=layout(6, 6, terrain="SteepSlope", slope=80.0),
        num_rovers=0,
        seed=3,
        **overrides,
    )
    rover = add_rover(model, (2, 2), navigation_mode="emotional", strategy=FirstMove())
    rover.step()
    assert rover.is_overturned
    return model, rover


def test_rover_recovers_after_overturn_and_imprints_fear():
    model, rover = _overturned_rover(overturn_recovery_steps=3)
    position = rover.pos
    assert rover.mission_status == "recovering"
    assert rover.is_active

    for _ in range(3):
        rover.step()
        assert rover.pos == position  # no movement while recovering

    assert not rover.is_overturned
    assert rover.mission_status == "active"
    assert rover.recoveries == 1
    assert rover.fear_events_own >= 1
    assert rover.fear_intensity(model.terrain_at(position).optical_signature) > 0


def test_zero_recovery_steps_keeps_overturn_terminal():
    _, rover = _overturned_rover(overturn_recovery_steps=0)
    assert rover.mission_status == "overturned"
    assert not rover.is_active
    position = rover.pos
    rover.step()
    assert rover.pos == position
    assert rover.is_overturned
