"""Build the immutable observation consumed by navigation strategies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.fear import FearView
from src.environment.terrain import TerrainPatch
from src.navigation.types import Observation, TerrainObservation

if TYPE_CHECKING:  # pragma: no cover
    from src.agents.rover import Pioneer3DXAgent


def _terrain_observation(
    rover: Pioneer3DXAgent, position, terrain: TerrainPatch
) -> TerrainObservation:
    occupied = rover.model.rover_at(position, exclude_id=rover.unique_id) is not None
    return TerrainObservation(
        position=position,
        terrain_type=terrain.terrain_type.value,
        traversable=terrain.traversable,
        movement_cost=terrain.movement_cost,
        damage_risk=terrain.damage_risk,
        slope_risk=terrain.slope_risk,
        rgb_signature=terrain.optical_signature,
        elevation=float(terrain.elevation),
        slope=float(terrain.slope),
        occupied_by_rover=occupied,
        visited=position in rover.visited,
    )


def build_observation(rover: Pioneer3DXAgent) -> Observation:
    rgb = rover.read_rgb_cameras()
    lidar = rover.read_lidar()
    positions = set(rgb)
    positions.update(lidar)
    positions.add(rover.pos)

    visible: dict[tuple[int, int], TerrainObservation] = {}
    for position in positions:
        terrain = rover.model.terrain_at(position)
        if terrain is not None:
            visible[position] = _terrain_observation(rover, position, terrain)

    rover.model.mark_discovered(positions)
    rover.known_terrain.update(visible)

    coverage_visited, coverage_discovered = rover.model.coverage()
    current_terrain = rover.model.terrain_at(rover.pos)
    current = (
        _terrain_observation(rover, rover.pos, current_terrain)
        if current_terrain is not None
        else None
    )

    # A swarm shares visited cells over the radio, so its rovers do not
    # explore the same area twice.
    visited = set(rover.visited)
    config = rover.model.config
    if (
        rover.navigation_mode == "swarm_emotional"
        and config.radio_enabled
        and config.swarm_share_map
    ):
        for other in rover.model.rovers_in_range(rover.pos, int(config.R_radio)):
            visited.update(other.visited)

    # Swarm rovers report their positions over the radio. A destroyed or
    # finished rover no longer transmits.
    swarm_peers: dict[int, tuple[int, int]] = {}
    if rover.navigation_mode == "swarm_emotional" and config.radio_enabled:
        for other in rover.model.rovers_in_range(rover.pos, int(config.R_radio)):
            if (
                other is not rover
                and other.navigation_mode == "swarm_emotional"
                and other.is_active
            ):
                swarm_peers[other.unique_id] = other.pos

    fear_view: dict[tuple[int, int, int], FearView] = rover.fear_map()
    retreat_required = (
        rover.current_fear_intensity()
        >= rover.model.config.retreat_fear_threshold
    )

    return Observation(
        position=rover.pos,
        target=rover.target,
        navigation_mode=rover.navigation_mode,  # type: ignore[arg-type]
        mission_mode=rover.mission_mode,  # type: ignore[arg-type]
        step=rover.model.step_count,
        visible_cells=visible,
        lidar_obstacles=frozenset(lidar),
        rgb_signatures=rgb,
        visited=frozenset(visited),
        anxiety_memory=fear_view,
        coverage_visited=coverage_visited,
        coverage_discovered=coverage_discovered,
        exploration_budget=rover.exploration_budget,
        coverage_target=rover.coverage_target,
        allow_forced_fear_visit=rover.model.config.allow_forced_fear_visit
        if hasattr(rover.model.config, "allow_forced_fear_visit")
        else True,
        retreat_required=retreat_required,
        current_terrain=current,
        swarm_peers=swarm_peers,
    )


__all__ = ["build_observation"]
