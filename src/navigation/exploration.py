"""Exploration shared by all scientific strategies.

The rover explores from where it stands: it drives to the nearest cell it
has not seen yet (cheapest route through the terrain it knows), so the known
area grows outwards from the start instead of the rover running in a
straight line to the edge of the map. Targets much farther from the start
than the nearest unseen cell cost extra (``explore_home_weight``,
``explore_home_slack``), so the rover works its way around the explored area.

The route cost is the terrain cost plus an optional ``cell_cost`` (fear of
the emotional rover, caution of the fuzzy rover), so every variant uses the
same control and differs only in how it values the terrain.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass

from src.model.types import Position, hex_distance
from src.navigation.board import HexGridBoard
from src.navigation.planning import UNKNOWN_CELL_COST
from src.navigation.types import Observation, TerrainObservation

CellCost = Callable[[TerrainObservation], float]

# How many of the nearest unseen cells are compared when choosing a target.
NEAREST_TARGETS = 24
# The current target is kept unless another one is clearly better, so the
# rover does not switch targets back and forth.
KEEP_TARGET_BONUS = 1.5


@dataclass(frozen=True)
class ExploreTarget:
    """An unseen cell next to known terrain and the way to it."""

    cost: float  # route cost through known terrain (incl. ``cell_cost``)
    target: Position
    first_step: Position
    # ``cell_cost`` of the first step (0 when it is unknown or not averse).
    first_step_aversion: float
    # Summed ``cell_cost`` of all cells on the route.
    aversion: float = 0.0


def frontier_targets(
    rover,
    observation: Observation,
    board: HexGridBoard,
    cell_cost: CellCost | None = None,
    limit: int = NEAREST_TARGETS,
    max_aversion: float = math.inf,
) -> list[ExploreTarget]:
    """The nearest unseen cells, cheapest route first.

    One Dijkstra search from the rover over the terrain it knows; an unseen
    neighbour of a known cell ends a route (the rover will see it on the
    way). Stops after ``limit`` targets. Routes whose summed ``cell_cost``
    exceeds ``max_aversion`` are not followed.
    """

    start = observation.position
    known = rover.known_terrain
    first_actions = board.actions(start, observation)
    if not first_actions:
        return []

    def aversion(info: TerrainObservation | None) -> float:
        return cell_cost(info) if cell_cost is not None and info is not None else 0.0

    distance: dict[Position, float] = {start: 0.0}
    averse: dict[Position, float] = {start: 0.0}
    first: dict[Position, Position] = {}
    found: dict[Position, ExploreTarget] = {}
    queue: list[tuple[float, Position]] = [(0.0, start)]
    worst = math.inf
    while queue:
        cost_so_far, position = heapq.heappop(queue)
        if cost_so_far > distance.get(position, math.inf):
            continue
        if len(found) >= limit and cost_so_far + UNKNOWN_CELL_COST >= worst:
            break
        neighbours = first_actions if position == start else board.neighbors(position)
        for neighbour in neighbours:
            if neighbour in observation.lidar_obstacles:
                continue
            step = neighbour if position == start else first[position]
            info = known.get(neighbour)
            if info is None:
                # Unseen cell: a target, not a way through.
                cost = cost_so_far + UNKNOWN_CELL_COST
                previous = found.get(neighbour)
                if previous is None or cost < previous.cost:
                    found[neighbour] = ExploreTarget(
                        cost,
                        neighbour,
                        step,
                        aversion(known.get(step)),
                        averse[position],
                    )
                    if len(found) >= limit:
                        worst = max(item.cost for item in found.values())
                continue
            if not info.traversable:
                continue
            extra = aversion(info)
            if averse[position] + extra > max_aversion:
                continue
            new_cost = cost_so_far + info.movement_cost + extra
            if new_cost < distance.get(neighbour, math.inf):
                distance[neighbour] = new_cost
                averse[neighbour] = averse[position] + extra
                first[neighbour] = step
                heapq.heappush(queue, (new_cost, neighbour))
    return sorted(found.values(), key=lambda item: (item.cost, item.target))


def choose_target(
    targets: list[ExploreTarget],
    home: Position | None,
    home_weight: float,
    keep: Position | None = None,
    allowed: Callable[[Position], bool] | None = None,
    home_slack: float = 0.0,
) -> ExploreTarget | None:
    """Cheapest target; targets far outside the explored disc cost more."""

    best: tuple[float, Position] | None = None
    chosen: ExploreTarget | None = None
    anchored = home is not None and home_weight > 0
    # Distance from home of the nearest unseen cell: the explored area is a
    # disc of about this radius; targets up to ``home_slack`` cells farther
    # out cost nothing extra, so the rover works its way around the disc.
    inner = (
        min((hex_distance(home, item.target) for item in targets), default=0)
        if anchored
        else 0
    )
    for item in targets:
        if allowed is not None and not allowed(item.first_step):
            continue
        score = item.cost
        if anchored:
            outside = hex_distance(home, item.target) - inner - home_slack
            score += home_weight * max(0.0, outside)
        if item.target == keep:
            score -= KEEP_TARGET_BONUS
        key = (score, item.target)
        if best is None or key < best:
            best, chosen = key, item
    return chosen


__all__ = [
    "KEEP_TARGET_BONUS",
    "NEAREST_TARGETS",
    "CellCost",
    "ExploreTarget",
    "choose_target",
    "frontier_targets",
]
