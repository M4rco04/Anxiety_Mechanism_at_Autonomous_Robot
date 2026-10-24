"""Fear memory and radio tests."""

from __future__ import annotations

import pytest

from src.agents.homeostat import HomeostatReading
from src.communication.radio import RadioPacket
from tests.conftest import add_rover, make_model


def test_learn_fear_and_rgb_tolerance():
    model = make_model(width=4, height=4, num_rovers=0, seed=1)
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    assert rover.learn_fear((120, 80, 40), intensity=0.8, source="self")
    assert rover.fear_intensity((121, 82, 41)) > 0
    assert rover.fear_intensity((0, 0, 0)) == 0
    assert rover.fear_events_own == 1
    record = next(iter(rover.anxiety_memory.values()))
    assert record.visits == 1


def test_fear_reinforcement_and_decay():
    model = make_model(width=4, height=4, num_rovers=0, seed=1)
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    rover.learn_fear((120, 80, 40), intensity=0.4, source="self")
    rover.learn_fear((120, 80, 40), intensity=0.3, source="self")
    record = next(iter(rover.anxiety_memory.values()))
    assert record.visits == 2
    assert record.intensity == pytest.approx(0.7)
    model.step_count = 100
    assert rover.fear_intensity((120, 80, 40)) < 0.7


def test_one_imprint_per_critical_event_with_rearm():
    model = make_model(width=4, height=4, num_rovers=0, seed=1)
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    rover.stress_level = 80.0
    rover.stress_armed = True
    critical = HomeostatReading(
        instantaneous=100.0, smoothed=80.0, components={}, critical=True
    )
    rover._handle_anxiety(critical)
    assert rover.fear_events_own == 1
    rover._handle_anxiety(critical)
    assert rover.fear_events_own == 1
    rover.stress_level = 10.0
    noncritical = HomeostatReading(
        instantaneous=0.0, smoothed=10.0, components={}, critical=False
    )
    rover._handle_anxiety(noncritical)
    assert rover.stress_armed is True
    rover.stress_level = 80.0
    rover._handle_anxiety(critical)
    assert rover.fear_events_own == 2


def test_receive_signal_does_not_damage_rover():
    model = make_model(width=8, height=8, num_rovers=0, seed=1)
    rover = add_rover(model, (1, 1), navigation_mode="swarm_emotional")
    before = (rover.battery, rover.hull_condition, rover.wheel_condition)
    packet = RadioPacket(
        signature=(200, 50, 40),
        position=(2, 1),
        intensity=0.7,
        sender_id=99,
        created_at=1,
    )
    assert rover.receive_signal(packet)
    assert rover.fear_events_received == 1
    assert (rover.battery, rover.hull_condition, rover.wheel_condition) == before
    assert not rover.receive_signal(packet)  # duplicate


def test_radio_range_and_no_damage():
    model = make_model(width=30, height=10, num_rovers=0, seed=1)
    sender = add_rover(model, (0, 0), navigation_mode="swarm_emotional")
    near = add_rover(model, (20, 0), navigation_mode="swarm_emotional")
    far = add_rover(model, (22, 0), navigation_mode="swarm_emotional")
    assert near.unique_id in {r.unique_id for r in model.rovers_in_range((0, 0), 20)}
    assert far.unique_id not in {
        r.unique_id for r in model.rovers_in_range((0, 0), 20)
    }
    packet = RadioPacket((10, 20, 30), (0, 0), 0.9, sender.unique_id, 1)
    before = far.battery
    assert near.receive_signal(packet)
    assert not far.receive_signal(packet)
    assert far.battery == before
