"""Emotional rovers must not circle forever in a pocket of safe cells."""

from __future__ import annotations

from src.environment.terrain import Ventifacts
from src.model.types import hex_to_rgb
from src.navigation.registry import create_strategy
from tests.conftest import add_rover, layout, make_model

SIZE = 14
POCKET = {(6, 6), (7, 6), (6, 7)}


def _pocket_model(mode: str):
    probe = make_model(width=SIZE, height=SIZE, terrain_layout=layout(SIZE, SIZE), num_rovers=0)
    ring = {
        neighbour
        for cell in POCKET
        for neighbour in probe.grid.get_neighborhood(cell, include_center=False, radius=1)
    } - POCKET
    model = make_model(
        width=SIZE,
        height=SIZE,
        terrain_layout=layout(SIZE, SIZE, overrides={cell: "Ventifacts" for cell in ring}),
        num_rovers=0,
        seed=7,
        navigation_mode=mode,
    )
    rover = add_rover(
        model,
        (6, 6),
        navigation_mode=mode,
        strategy=create_strategy(mode, model.config, 7),
    )
    # The rover already fears the rocks that surround the pocket.
    rover.learn_fear(hex_to_rgb(Ventifacts.color), intensity=1.0, source="self", source_position=(6, 6))
    model.running = True
    return model, rover




def test_emotional_rover_leaves_a_pocket_surrounded_by_feared_terrain():
    for mode in ("emotional", "swarm_emotional"):
        model, rover = _pocket_model(mode)
        for _ in range(30):
            model.step()
        outside = rover.visited - POCKET
        assert any(
            model.terrain_at(cell).terrain_type.value == "SafeRegolith" for cell in outside
        ), mode
