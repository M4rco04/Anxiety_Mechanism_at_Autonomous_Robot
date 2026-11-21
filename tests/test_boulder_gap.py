"""The rover cannot squeeze between two boulders."""

from __future__ import annotations

from itertools import pairwise

from src.model.types import gap_cells, squeezed
from src.navigation.board import HexGridBoard
from src.navigation.observation import build_observation
from src.navigation.registry import create_strategy
from src.navigation.types import NavigationDecision
from tests.conftest import add_rover, layout, make_model


def test_gap_cells_are_the_two_shared_neighbours():
    model = make_model(width=12, height=12, num_rovers=0)
    for a in [(4, 4), (5, 5), (5, 6), (6, 3)]:
        around = set(model.grid.get_neighborhood(a, include_center=False, radius=1))
        for b in around:
            shared = around & set(model.grid.get_neighborhood(b, include_center=False, radius=1))
            assert set(gap_cells(a, b)) == shared
    assert gap_cells((4, 4), (8, 8)) is None


def _gap_world(start=(5, 5), target_cell=None):
    """Two boulders beside one edge of ``start``; returns model, edge, gap."""

    model = make_model(width=12, height=12, num_rovers=0)
    neighbour = model.grid.get_neighborhood(start, include_center=False, radius=1)[0]
    gap = gap_cells(start, neighbour)
    overrides = {cell: "Boulders" for cell in gap}
    model = make_model(
        width=12,
        height=12,
        num_rovers=0,
        seed=1,
        rgb_fov_deg=360.0,
        rgb_noise_sigma=0.0,
        terrain_layout=layout(12, 12, overrides=overrides),
    )
    return model, neighbour, gap


class _Push:
    """Strategy that always tries to drive to one cell."""

    def __init__(self, cell):
        self.cell = cell

    def choose_next(self, rover, observation):
        return NavigationDecision(self.cell, "push", "moving")

    def statistics(self):
        return {}


def test_rover_cannot_drive_between_two_boulders():
    model, neighbour, _ = _gap_world()
    rover = add_rover(model, (5, 5), strategy=_Push(neighbour))
    assert squeezed((5, 5), neighbour, model.is_boulder)
    assert not rover._is_valid_move(neighbour)
    rover.step()
    assert rover.pos == (5, 5)


def test_one_boulder_leaves_the_way_open():
    model = make_model(width=12, height=12, num_rovers=0)
    neighbour = model.grid.get_neighborhood((5, 5), include_center=False, radius=1)[0]
    one = gap_cells((5, 5), neighbour)[0]
    model = make_model(
        width=12, height=12, num_rovers=0, seed=1,
        terrain_layout=layout(12, 12, overrides={one: "Boulders"}),
    )
    rover = add_rover(model, (5, 5), strategy=_Push(neighbour))
    assert rover._is_valid_move(neighbour)


def test_planner_does_not_offer_the_gap():
    model, neighbour, gap = _gap_world()
    rover = add_rover(model, (5, 5), navigation_mode="online")
    observation = build_observation(rover)
    assert all(cell in observation.lidar_obstacles or cell in rover.known_terrain for cell in gap)
    actions = HexGridBoard(model).actions((5, 5), observation)
    assert neighbour not in actions
    assert gap[0] not in actions and gap[1] not in actions


def test_goal_route_goes_around_the_gap():
    _, neighbour, _ = _gap_world()
    model = make_model(
        width=12,
        height=12,
        num_rovers=0,
        seed=1,
        rgb_fov_deg=360.0,
        rgb_noise_sigma=0.0,
        mission_mode="goal_navigation",
        goal_waypoints=1,
        max_steps=100,
        terrain_layout=layout(
            12, 12, overrides={cell: "Boulders" for cell in gap_cells((5, 5), neighbour)}
        ),
    )
    rover = add_rover(
        model, (5, 5), navigation_mode="online", mission_mode="goal_navigation",
        strategy=create_strategy("online", model.config, 1),
    )
    rover.target = neighbour
    model.running = True
    while model.running and rover.pos != neighbour:
        model.step()
    assert rover.pos == neighbour
    path = [(5, 5), *rover.path]
    assert all(not squeezed(a, b, model.is_boulder) for a, b in pairwise(path))
    assert len(rover.path) >= 2  # a detour, not the direct move
