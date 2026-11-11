"""Low-battery behaviour: drive to the nearest known safe cell to charge.

A rover whose battery is below ``solar_charge_start`` and which is not on
SafeRegolith plans the cheapest route through terrain it has already seen to
the nearest known SafeRegolith cell. There the rover charges from its solar
panels (see ``Pioneer3DXAgent._charge_step``).
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable

from src.model.types import Position
from src.navigation.board import HexGridBoard
from src.navigation.types import NavigationDecision, Observation, TerrainObservation

SAFE_TERRAIN = "SafeRegolith"


def needs_charging(rover, observation: Observation) -> bool:
    config = rover.model.config
    if not config.solar_charging or config.solar_charge_rate <= 0:
        return False
    if rover.battery >= config.solar_charge_start:
        return False
    current = observation.current_terrain
    return current is None or current.terrain_type != SAFE_TERRAIN


def seek_charging_spot(
    rover,
    observation: Observation,
    board: HexGridBoard,
    fear_cost: Callable[[TerrainObservation], float] | None = None,
) -> NavigationDecision | None:
    """Return the first step towards the nearest known safe cell, if needed.

    The route only goes through cells the rover has seen (``known_terrain``).
    ``fear_cost`` (extra cost of a known cell) lets emotional and fuzzy
    strategies avoid terrain they fear or distrust.
    Returns ``None`` when charging is not needed or no safe cell is known,
    so the strategy falls back to its normal behaviour.
    """

    if not needs_charging(rover, observation):
        return None
    known = rover.known_terrain
    start = observation.position
    first_actions = board.actions(start, observation)
    if not first_actions:
        return None

    distance: dict[Position, float] = {start: 0.0}
    first_step: dict[Position, Position] = {}
    queue: list[tuple[float, Position]] = [(0.0, start)]
    while queue:
        cost_so_far, position = heapq.heappop(queue)
        if cost_so_far > distance.get(position, math.inf):
            continue
        info = known.get(position)
        if position != start and info is not None and info.terrain_type == SAFE_TERRAIN:
            return NavigationDecision(
                first_step[position],
                "low battery: heading to safe ground to charge",
                "moving",
                {"route_cost": cost_so_far},
            )
        neighbours = first_actions if position == start else board.neighbors(position)
        for neighbour in neighbours:
            cell = known.get(neighbour)
            if cell is None or not cell.traversable:
                continue
            if neighbour in observation.lidar_obstacles:
                continue
            step_cost = cell.movement_cost
            if fear_cost is not None:
                step_cost += fear_cost(cell)
            new_cost = cost_so_far + step_cost
            if new_cost < distance.get(neighbour, math.inf):
                distance[neighbour] = new_cost
                first_step[neighbour] = (
                    neighbour if position == start else first_step[position]
                )
                heapq.heappush(queue, (new_cost, neighbour))
    return None


__all__ = ["needs_charging", "seek_charging_spot"]
