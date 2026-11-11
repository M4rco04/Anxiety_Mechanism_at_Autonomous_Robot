"""Swarm exploration: rovers split the terrain but stay within radio range."""

from __future__ import annotations

from src.model.types import hex_distance
from src.navigation.observation import build_observation
from src.navigation.registry import create_strategy
from tests.conftest import add_rover, layout, make_model

SIZE = 40


def _swarm(positions, **overrides):
    model = make_model(
        width=SIZE,
        height=SIZE,
        terrain_layout=layout(SIZE, SIZE),
        num_rovers=0,
        seed=4,
        navigation_mode="swarm_emotional",
        **overrides,
    )
    rovers = [
        add_rover(
            model,
            position,
            navigation_mode="swarm_emotional",
            strategy=create_strategy("swarm_emotional", model.config, 4),
        )
        for position in positions
    ]
    model.running = True  # the model starts stopped when built with no rovers
    return model, rovers


def _run(model, rovers, steps):
    max_distance = 0
    for _ in range(steps):
        model.step()
        max_distance = max(
            max_distance,
            *(
                hex_distance(a.pos, b.pos)
                for i, a in enumerate(rovers)
                for b in rovers[i + 1 :]
            ),
        )
    return max_distance


def _overlap(rovers) -> float:
    cells = [cell for rover in rovers for cell in rover.visited]
    return 1.0 - len(set(cells)) / len(cells)


def test_swarm_rovers_explore_separate_areas():
    model, rovers = _swarm([(19, 20), (20, 20), (21, 20)])
    _run(model, rovers, 80)
    assert _overlap(rovers) < 0.1
    # Each rover covered terrain of its own, not just the others' tracks.
    for rover in rovers:
        assert len(rover.visited) > 40


def test_swarm_stays_within_radio_range():
    model, rovers = _swarm([(19, 20), (20, 20), (21, 20)])
    max_distance = _run(model, rovers, 120)
    assert max_distance <= model.config.R_radio


def test_rover_regroups_after_losing_contact():
    _model, rovers = _swarm([(5, 20)])
    rover = rovers[0]
    rover._face(rover.pos, (30, 20))  # cameras look towards the swarm
    rover.strategy.peer_memory = {99: (30, 20)}
    decision = rover.strategy.choose_next(rover, build_observation(rover))
    assert decision is not None
    assert decision.reason == "regrouping with the swarm"
    assert hex_distance(decision.next_position, (30, 20)) < hex_distance(
        rover.pos, (30, 20)
    )


def test_leader_waits_and_follower_drives_to_it():
    _model, rovers = _swarm([(5, 20), (20, 20)])
    leader, follower = rovers
    observation = build_observation(follower)
    fear_of = lambda signature: 0.0

    decision = follower.strategy._follow_or_wait(
        follower, observation, follower.strategy._get_board(follower),
        {leader.unique_id: leader.pos}, fear_of,
    )
    assert decision.reason == "following the swarm leader"
    assert hex_distance(decision.next_position, leader.pos) < hex_distance(
        follower.pos, leader.pos
    )

    observation = build_observation(leader)
    decision = leader.strategy._follow_or_wait(
        leader, observation, leader.strategy._get_board(leader),
        {follower.unique_id: follower.pos}, fear_of,
    )
    assert decision.next_position is None
    assert decision.status == "waiting"


def test_waiting_rover_stays_active():
    _model, rovers = _swarm([(5, 20)])
    rover = rovers[0]

    class Wait:
        def choose_next(self, rover, observation):
            from src.navigation.types import NavigationDecision

            return NavigationDecision(None, "waiting for the swarm", "waiting")

    rover.strategy = Wait()
    rover.step()
    assert rover.pos == (5, 20)
    assert rover.mission_status == "active"
    assert rover.is_active
