"""Low-battery behaviour: drive to the nearest known safe cell to charge.

A rover whose battery is below ``solar_charge_start`` and which is not on
SafeRegolith plans the cheapest route through terrain it has already seen to
the nearest known SafeRegolith cell. There the rover charges from its solar
panels (see ``Pioneer3DXAgent._charge_step``). Near a dust storm the panels
get less light, so a safe cell within ``dust_shading_radius`` of a dust storm
the rover has seen costs the extra charging steps it would need there.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable

from src.model.types import Position, hex_distance, squeezed
from src.navigation.board import HexGridBoard
from src.navigation.costs import TerrainCost, mean_cost
from src.navigation.types import NavigationDecision, Observation, TerrainObservation

SAFE_TERRAIN = "SafeRegolith"
DUST_TERRAIN = "DustStorm"


def shade_penalty(config) -> float:
    """Extra charging steps in the dust shade (route-cost units ~ steps)."""

    fraction = float(config.dust_solar_fraction)
    rate = float(config.solar_charge_rate)
    if fraction >= 1.0 or rate <= 0.0:
        return 0.0
    span = float(config.solar_charge_stop) - float(config.solar_charge_start)
    steps = span / rate
    return steps / max(fraction, 1e-6) - steps


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
    terrain_cost: TerrainCost = mean_cost,
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
    blocked = board.known_blocker(observation, rover.known_terrain)
    if not first_actions:
        return None

    config = rover.model.config
    radius = int(config.dust_shading_radius)
    penalty = shade_penalty(config)
    dust = [p for p, cell in known.items() if cell.terrain_type == DUST_TERRAIN]

    def shaded(position: Position) -> bool:
        return any(hex_distance(position, d) <= radius for d in dust)

    distance: dict[Position, float] = {start: 0.0}
    first_step: dict[Position, Position] = {}
    queue: list[tuple[float, Position]] = [(0.0, start)]
    best: tuple[float, Position] | None = None
    while queue:
        cost_so_far, position = heapq.heappop(queue)
        if best is not None and cost_so_far >= best[0]:
            break
        if cost_so_far > distance.get(position, math.inf):
            continue
        info = known.get(position)
        if position != start and info is not None and info.terrain_type == SAFE_TERRAIN:
            total = cost_so_far + (penalty if dust and shaded(position) else 0.0)
            if best is None or total < best[0]:
                best = (total, position)
            if total == cost_so_far:
                break
        neighbours = first_actions if position == start else board.neighbors(position)
        for neighbour in neighbours:
            cell = known.get(neighbour)
            if cell is None or not cell.traversable:
                continue
            if neighbour in observation.lidar_obstacles:
                continue
            if squeezed(position, neighbour, blocked):
                continue
            step_cost = terrain_cost(cell)
            if fear_cost is not None:
                step_cost += fear_cost(cell)
            new_cost = cost_so_far + step_cost
            if new_cost < distance.get(neighbour, math.inf):
                distance[neighbour] = new_cost
                first_step[neighbour] = (
                    neighbour if position == start else first_step[position]
                )
                heapq.heappush(queue, (new_cost, neighbour))
    if best is None:
        return None
    return NavigationDecision(
        first_step[best[1]],
        "low battery: heading to safe ground to charge",
        "moving",
        {"route_cost": best[0]},
    )


__all__ = ["needs_charging", "seek_charging_spot", "shade_penalty"]
