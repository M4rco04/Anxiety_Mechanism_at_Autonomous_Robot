"""Swarm radio propagation tests."""

from __future__ import annotations

from tests.conftest import add_rover, layout, make_model


def test_broadcast_reaches_only_radio_range_and_does_not_damage():
    model = make_model(
        width=30,
        height=8,
        terrain_layout=layout(30, 8),
        num_rovers=0,
        seed=11,
    )
    sender = add_rover(model, (0, 0), navigation_mode="swarm_emotional")
    near = add_rover(model, (15, 0), navigation_mode="swarm_emotional")
    far = add_rover(model, (25, 0), navigation_mode="swarm_emotional")
    sender.stress_level = 90.0
    model.step_count = 3
    before = (near.battery, near.hull_condition, far.battery, far.hull_condition)

    assert sender.broadcast_danger((200, 60, 40), sender.pos)
    delivered = model.swarm.process_signals(model)

    assert delivered >= 1
    assert near.fear_events_received == 1
    assert far.fear_events_received == 0
    assert (near.battery, near.hull_condition, far.battery, far.hull_condition) == before
    assert model.swarm.total_sent == 1
