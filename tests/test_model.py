"""Board and model integration tests."""

from __future__ import annotations

import mesa

from config.config import SimulationConfig
from src.model.model import MarsSimulation
from src.navigation.board import HexGridBoard
from src.navigation.observation import build_observation
from tests.conftest import add_rover, layout, make_model


def test_board_excludes_known_boulders_and_occupied_cells():
    terrain_layout = layout(
        6,
        6,
        overrides={(1, 0): "Boulders"},
    )
    model = make_model(
        width=6,
        height=6,
        terrain_layout=terrain_layout,
        num_rovers=0,
        seed=4,
    )
    rover = add_rover(model, (0, 0))
    add_rover(model, (0, 1))
    observation = build_observation(rover)
    board = HexGridBoard(model)
    actions = board.actions(rover.pos, observation)
    assert (1, 0) not in actions
    assert (0, 1) not in actions
    assert all(0 <= x < 6 and 0 <= y < 6 for x, y in actions)


def test_model_uses_hex_multigrid():
    model = make_model(width=8, height=8, num_rovers=1)
    assert isinstance(model.grid, mesa.space.HexMultiGrid)
    assert len(model.grid.get_neighborhood((4, 4))) == 6


def test_goal_mode_assigns_reachable_targets():
    model = MarsSimulation(
        SimulationConfig(
            width=20,
            height=20,
            num_rovers=2,
            seed=9,
            mission_mode="goal_navigation",
        )
    )
    for rover in model.rovers():
        assert rover.target is not None
        assert model.is_in_bounds(rover.target)
        assert model.terrain_at(rover.target).traversable


def test_same_seed_reproduces_terrain_and_route():
    config = SimulationConfig(
        width=20, height=20, num_rovers=2, seed=123, max_steps=10
    )
    first = MarsSimulation(config=config)
    second = MarsSimulation(config=config)
    assert first.terrain_hash() == second.terrain_hash()
    assert [r.pos for r in first.rovers()] == [r.pos for r in second.rovers()]
    for _ in range(5):
        first.step()
        second.step()
    assert [r.pos for r in first.rovers()] == [r.pos for r in second.rovers()]
    assert [r.battery for r in first.rovers()] == [
        r.battery for r in second.rovers()
    ]


def test_exploration_terminates_at_max_steps():
    model = MarsSimulation(
        SimulationConfig(
            width=12,
            height=12,
            num_rovers=1,
            seed=3,
            max_steps=5,
            exploration_budget=100,
        ),
        terrain_layout=layout(12, 12),
    )
    for _ in range(10):
        model.step()
    assert model.running is False
    assert model.termination_reason in {
        "max_steps",
        "exploration_budget",
        "all_rovers_inactive",
    }


def test_no_rovers_model_is_not_running():
    model = MarsSimulation(
        SimulationConfig(width=5, height=5, num_rovers=0, seed=3)
    )
    assert model.running is False
    assert model.termination_reason == "no_rovers"
