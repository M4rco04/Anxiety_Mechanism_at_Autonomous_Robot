"""Solar charging on safe ground."""

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


def _rover(terrain: str, battery: float, **overrides):
    model = make_model(
        width=6,
        height=6,
        terrain_layout=layout(6, 6, terrain=terrain),
        num_rovers=0,
        seed=4,
        **overrides,
    )
    rover = add_rover(model, (2, 2), strategy=FirstMove())
    rover.battery = battery
    return rover


def test_low_battery_on_safe_ground_charges_until_stop_level():
    rover = _rover("SafeRegolith", 20.0)
    start = rover.pos
    rover.step()
    assert rover.pos == start
    assert rover.mission_status == "charging"
    assert rover.battery == 25.0

    while rover.charging:
        rover.step()
        assert rover.pos == start
    assert rover.battery == rover.model.config.solar_charge_stop
    assert rover.mission_status == "active"

    rover.step()
    assert rover.pos != start  # drives on after charging


def test_no_charging_in_shadow_or_when_disabled():
    shadow = _rover("DeepShadow", 20.0)
    shadow.step()
    assert shadow.charging_steps == 0

    disabled = _rover("SafeRegolith", 20.0, solar_charging=False)
    disabled.step()
    assert disabled.charging_steps == 0


def test_charged_battery_does_not_stop_the_rover():
    rover = _rover("SafeRegolith", 80.0)
    start = rover.pos
    rover.step()
    assert rover.pos != start
    assert rover.charging_steps == 0


def test_low_battery_rover_heads_to_nearest_safe_cell():
    from src.navigation.registry import create_strategy

    # Rover in shadow; one safe cell two steps to the east.
    terrain = layout(8, 8, terrain="DeepShadow", overrides={(5, 3): "SafeRegolith"})
    model = make_model(width=8, height=8, terrain_layout=terrain, num_rovers=0, seed=4)
    strategy = create_strategy("online", model.config)
    rover = add_rover(model, (3, 3), navigation_mode="online", strategy=strategy)
    rover._face(rover.pos, (5, 3))  # cameras look east
    rover.battery = 25.0

    for _ in range(4):
        rover.step()
        if rover.pos == (5, 3):
            break
    assert rover.pos == (5, 3)
    rover.step()
    assert rover.mission_status == "charging"
