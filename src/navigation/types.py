"""Public navigation contracts.

Navigation strategies are deliberately independent from Mesa and from the
rover's physical state.  A strategy receives an immutable observation and
returns the next cell; the rover validates and executes the move.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from src.agents.fear import FearView
from src.model.types import RGB, Position

MissionMode = Literal["exploration", "goal_navigation"]
NavigationMode = Literal["online", "emotional", "swarm_emotional", "scaffold"]


@dataclass(frozen=True)
class TerrainObservation:
    position: Position
    terrain_type: str
    traversable: bool
    movement_cost: float
    damage_risk: float
    slope_risk: float
    rgb_signature: RGB | None
    elevation: float
    slope: float
    occupied_by_rover: bool
    visited: bool


@dataclass(frozen=True)
class Observation:
    position: Position
    target: Position | None
    navigation_mode: NavigationMode
    mission_mode: MissionMode
    step: int
    visible_cells: Mapping[Position, TerrainObservation]
    lidar_obstacles: frozenset[Position]
    rgb_signatures: Mapping[Position, RGB]
    visited: frozenset[Position]
    anxiety_memory: Mapping[RGB, FearView]
    coverage_visited: float
    coverage_discovered: float
    exploration_budget: int
    coverage_target: float
    allow_forced_fear_visit: bool
    retreat_required: bool
    current_terrain: TerrainObservation | None


@dataclass(frozen=True)
class NavigationDecision:
    next_position: Position | None
    reason: str
    status: Literal[
        "moving",
        "goal_reached",
        "exploration_complete",
        "no_path",
        "blocked",
        "forced_fear_visit",
    ] = "moving"
    metadata: Mapping[str, float] = field(default_factory=dict)


class NavigationStrategy(Protocol):
    """Common strategy interface for all scientific variants."""

    def choose_next(self, rover, observation: Observation) -> NavigationDecision | None:
        ...

    def statistics(self) -> Mapping[str, int | float]:
        ...


__all__ = [
    "MissionMode",
    "NavigationDecision",
    "NavigationMode",
    "NavigationStrategy",
    "Observation",
    "TerrainObservation",
]
