"""Goal route planning shared by all scientific strategies.

The rover replans every step with A* over the terrain it knows
(``rover.known_terrain``). Unknown cells are assumed easy (cost 1, the
usual free-space assumption of planetary rovers), known obstacles are
skipped. Emotional strategies add the fear cost of each cell, so the plain
and the emotional rover differ only by the anxiety mechanism.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable

from src.model.types import RGB, Position
from src.navigation.board import HexGridBoard
from src.navigation.types import Observation

UNKNOWN_CELL_COST = 1.0


def plan_first_step(
    rover,
    observation: Observation,
    board: HexGridBoard,
    target: Position,
    fear_cost: Callable[[RGB | None], float] | None = None,
) -> tuple[Position, float] | None:
    """Return ``(first step, fear cost of that step)`` of the cheapest route."""

    start = observation.position
    first_actions = board.actions(start, observation)
    if not first_actions:
        return None
    known = rover.known_terrain

    def step_cost(cell: Position) -> float:
        info = known.get(cell)
        if info is None:
            return UNKNOWN_CELL_COST
        if not info.traversable:
            return math.inf
        cost = info.movement_cost
        if fear_cost is not None:
            cost += fear_cost(info.rgb_signature)
        return cost

    distance: dict[Position, float] = {start: 0.0}
    first: dict[Position, Position] = {}
    queue: list[tuple[float, float, Position]] = [
        (float(board.hex_distance(start, target)), 0.0, start)
    ]
    while queue:
        _, cost_so_far, position = heapq.heappop(queue)
        if cost_so_far > distance.get(position, math.inf):
            continue
        if position == target:
            step = first[position]
            info = known.get(step)
            fear = (
                fear_cost(info.rgb_signature)
                if fear_cost is not None and info is not None
                else 0.0
            )
            return step, fear
        neighbours = first_actions if position == start else board.neighbors(position)
        for neighbour in neighbours:
            if neighbour in observation.lidar_obstacles:
                continue
            cost = step_cost(neighbour)
            if math.isinf(cost):
                continue
            new_cost = cost_so_far + cost
            if new_cost < distance.get(neighbour, math.inf):
                distance[neighbour] = new_cost
                first[neighbour] = neighbour if position == start else first[position]
                estimate = new_cost + board.hex_distance(neighbour, target)
                heapq.heappush(queue, (estimate, new_cost, neighbour))
    return None


__all__ = ["UNKNOWN_CELL_COST", "plan_first_step"]
