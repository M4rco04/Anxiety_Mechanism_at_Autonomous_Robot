"""Shared test fixtures and small deterministic worlds."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from config.config import SimulationConfig
from src.agents.rover import Pioneer3DXAgent
from src.environment.terrain import (
    Boulders,
    DeepShadow,
    DustStorm,
    LooseSand,
    SafeRegolith,
    SteepSlope,
    TerrainPatch,
    Ventifacts,
)
from src.model.model import MarsSimulation

TERRAIN_BY_NAME = {
    "SafeRegolith": SafeRegolith,
    "Boulders": Boulders,
    "LooseSand": LooseSand,
    "Ventifacts": Ventifacts,
    "SteepSlope": SteepSlope,
    "DeepShadow": DeepShadow,
    "DustStorm": DustStorm,
}


def layout(
    width: int,
    height: int,
    terrain: str = "SafeRegolith",
    overrides: Mapping[tuple[int, int], str] | None = None,
    slope: float = 0.0,
) -> dict[tuple[int, int], tuple[type[TerrainPatch], float, float]]:
    overrides = dict(overrides or {})
    result = {}
    for x in range(width):
        for y in range(height):
            name = overrides.get((x, y), terrain)
            result[(x, y)] = (TERRAIN_BY_NAME[name], 0.0, slope)
    return result


def make_model(
    width: int = 8,
    height: int = 8,
    *,
    terrain_layout=None,
    num_rovers: int = 1,
    seed: int = 5,
    **overrides,
) -> MarsSimulation:
    strategy_factory = overrides.pop("strategy_factory", None)
    config = SimulationConfig(
        width=width,
        height=height,
        num_rovers=num_rovers,
        seed=seed,
        **overrides,
    )
    return MarsSimulation(
        config=config,
        terrain_layout=terrain_layout,
        strategy_factory=strategy_factory,
    )


def add_rover(
    model: MarsSimulation,
    position: tuple[int, int],
    *,
    navigation_mode: str = "scaffold",
    mission_mode: str = "exploration",
    strategy=None,
) -> Pioneer3DXAgent:
    rover = Pioneer3DXAgent(
        model.next_id(),
        model,
        strategy=strategy,
        navigation_mode=navigation_mode,
        mission_mode=mission_mode,
    )
    model.schedule.add(rover)
    model.grid.place_agent(rover, position)
    model._rover_by_id[rover.unique_id] = rover
    rover.path = [position]
    rover.visited = {position}
    rover.current_terrain_type = (
        model.terrain_at(position).terrain_type
        if model.terrain_at(position)
        else None
    )
    return rover


@pytest.fixture
def safe_model() -> MarsSimulation:
    return make_model(
        width=6,
        height=6,
        terrain_layout=layout(6, 6),
        num_rovers=1,
        seed=13,
    )
