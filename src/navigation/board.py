"""Adapter between Mesa's HexMultiGrid and the navigation strategies."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from src.environment.terrain import Boulders, TerrainPatch
from src.model.types import Position, hex_distance
from src.navigation.types import Observation

if TYPE_CHECKING:  # pragma: no cover
    from src.model.model import MarsSimulation


class HexGridBoard:
    """Local, observation-aware view of the Mesa hex grid.

    The board never exposes the complete terrain map to a strategy.  It reads
    bounds from Mesa, filters obstacles known through the observation, and
    lets unknown adjacent cells remain valid moves (with an uncertainty cost
    chosen by the strategy).
    """

    def __init__(self, model: MarsSimulation) -> None:
        self.model = model

    def in_bounds(self, position: Position) -> bool:
        x, y = position
        return 0 <= x < self.model.grid.width and 0 <= y < self.model.grid.height

    def neighbors(self, position: Position) -> list[Position]:
        if not self.in_bounds(position):
            return []
        return self.model.grid.get_neighborhood(
            position, include_center=False, radius=1
        )

    def terrain_at(self, position: Position) -> TerrainPatch | None:
        return self.model.terrain_at(position)

    def is_traversable(self, position: Position) -> bool:
        terrain = self.terrain_at(position)
        return terrain is not None and terrain.traversable

    def is_occupied_by_rover(
        self, position: Position, exclude_id: int | None = None
    ) -> bool:
        return self.model.rover_at(position, exclude_id=exclude_id) is not None

    def movement_cost(self, position: Position) -> float:
        terrain = self.terrain_at(position)
        if terrain is None:
            return math.inf
        return terrain.movement_cost

    def actions(self, position: Position, observation: Observation) -> list[Position]:
        candidates = self.neighbors(position)
        result: list[Position] = []
        for candidate in candidates:
            if candidate in observation.lidar_obstacles:
                continue
            known = observation.visible_cells.get(candidate)
            if known is not None and not known.traversable:
                continue
            if known is not None and known.occupied_by_rover:
                continue
            if known is None and self.is_occupied_by_rover(candidate):
                continue
            result.append(candidate)
        return result

    def hex_distance(self, a: Position, b: Position) -> int:
        return hex_distance(a, b)

    def is_boulder(self, position: Position) -> bool:
        return isinstance(self.terrain_at(position), Boulders)


__all__ = ["HexGridBoard"]
