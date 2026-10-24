"""Acceptance checks and scientific-mode handoff tests."""

from __future__ import annotations

import pytest

from config.config import SimulationConfig
from src.analytics.benchmark import run_episode
from src.environment.terrain import Boulders
from src.navigation.board import HexGridBoard
from src.navigation.registry import create_strategy
from src.navigation.types import NavigationDecision
from tests.conftest import layout, make_model


def test_unimplemented_scientific_modes_fail_loudly():
    for mode in ("online", "emotional", "swarm_emotional"):
        with pytest.raises(NotImplementedError):
            create_strategy(mode, SimulationConfig(), seed=1)


def test_scaffold_never_enters_boulders():
    terrain_layout = layout(
        8,
        8,
        overrides={
            (1, 0): "Boulders",
            (0, 1): "Boulders",
            (1, 1): "Boulders",
        },
    )
    model = make_model(
        width=8,
        height=8,
        terrain_layout=terrain_layout,
        num_rovers=1,
        seed=9,
        max_steps=10,
    )
    rover = model.rovers()[0]
    for _ in range(10):
        model.step()
        assert not isinstance(model.terrain_at(rover.pos), Boulders)


def test_exploration_does_not_require_target():
    model = make_model(width=10, height=10, num_rovers=1, seed=2, max_steps=5)
    assert model.rovers()[0].target is None


def test_goal_reached_stops_movement():
    class GoalStrategy:
        def choose_next(self, rover, observation):
            board = HexGridBoard(rover.model)
            actions = board.actions(observation.position, observation)
            if not actions:
                return NavigationDecision(None, "none", "no_path")
            chosen = min(
                actions,
                key=lambda cell: board.hex_distance(cell, observer_target),
            )
            return NavigationDecision(chosen, "goal test")

        def statistics(self):
            return {}

    observer_target = (4, 4)
    model = make_model(
        width=5,
        height=5,
        terrain_layout=layout(5, 5),
        num_rovers=1,
        seed=4,
        mission_mode="goal_navigation",
        targets=(observer_target,),
        max_steps=30,
        strategy_factory=lambda mode, config, seed: GoalStrategy(),
    )
    rover = model.rovers()[0]
    assert rover.target == observer_target
    for _ in range(20):
        if model.running:
            model.step()
    assert rover.pos == observer_target
    assert rover.mission_status == "goal_reached"
    position = rover.pos
    rover.step()
    assert rover.pos == position


@pytest.mark.xfail(
    reason="TODO(Karol): emotional navigation path and retreat not implemented",
    strict=False,
)
def test_emotional_variant_prefers_safe_alternative():
    result = run_episode(
        SimulationConfig(width=10, height=10, num_rovers=1, seed=1),
        navigation_mode="emotional",
        mission_mode="exploration",
        seed=1,
    )
    assert result.is_scientific


@pytest.mark.xfail(
    reason="TODO(Karol): swarm emotional navigation not implemented",
    strict=False,
)
def test_swarm_variant_is_scientific():
    result = run_episode(
        SimulationConfig(width=10, height=10, num_rovers=2, seed=1),
        navigation_mode="swarm_emotional",
        mission_mode="exploration",
        seed=1,
    )
    assert result.is_scientific
