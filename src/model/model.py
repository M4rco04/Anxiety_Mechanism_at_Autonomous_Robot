"""Main Mesa model for the Mars rover conditioned-anxiety simulation."""

from __future__ import annotations

import hashlib
import random
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from typing import Any

import mesa
import numpy as np

from config.config import DEFAULT_CONFIG, SimulationConfig
from src.agents.rover import Pioneer3DXAgent
from src.communication.swarm import SwarmBroadcaster
from src.environment.generator import MarsMapGenerator
from src.environment.terrain import (
    SafeRegolith,
    TerrainPatch,
    TerrainType,
)
from src.model.types import Position, hex_distance
from src.navigation.registry import create_strategy


class MarsSimulation(mesa.Model):
    """Couples the hex terrain grid, rovers, radio and metrics collection."""

    def __init__(
        self,
        config: SimulationConfig | None = None,
        *,
        terrain_layout: Mapping[Position, Any] | None = None,
        strategy_factory: Callable[..., Any] | None = None,
        **overrides: Any,
    ) -> None:
        super().__init__()
        base = config or DEFAULT_CONFIG
        if overrides:
            base = replace(base, **overrides)
        self.config = base
        self.config.validate()

        self.seed = (
            int(self.config.seed)
            if self.config.seed is not None
            else random.SystemRandom().randint(0, 2**31 - 1)
        )
        self.reset_randomizer(self.seed)
        self.rng = np.random.default_rng(self.seed)
        self.num_rovers = int(self.config.num_rovers)

        # HexMultiGrid, not HexGrid: terrain patch and rover share a cell.
        self.grid = mesa.space.HexMultiGrid(
            self.config.width, self.config.height, torus=False
        )
        self.schedule = mesa.time.RandomActivation(self)

        self._terrain_by_pos: dict[Position, TerrainPatch] = {}
        self._rover_by_id: dict[int, Pioneer3DXAgent] = {}
        self._discovered_cells: set[Position] = set()
        self._events: deque[dict[str, Any]] = deque(maxlen=64)
        self._strategy_factory = strategy_factory
        self.spawn_positions: dict[int, Position] = {}
        self.radio_packets_received = 0
        self.termination_reason: str | None = None
        self.step_count = 0

        self._setup_terrain(terrain_layout)
        self.traversable_cells = frozenset(
            position
            for position, terrain in self._terrain_by_pos.items()
            if terrain.traversable
        )

        self.swarm = SwarmBroadcaster(
            self,
            range_hex=int(self.config.R_radio),
            enabled=bool(self.config.radio_enabled),
        )
        self._setup_rovers()

        from src.analytics.metrics import setup_datacollector

        setup_datacollector(self)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _setup_terrain(
        self, terrain_layout: Mapping[Position, Any] | None
    ) -> None:
        if terrain_layout is None:
            generator = MarsMapGenerator(
                self.config.width, self.config.height, seed=self.seed
            )
            elevation, slope = generator.generate_topography()
            layout: Iterable[tuple[Position, TerrainPatch]] = (
                generator.assign_terrain_classes(self, elevation, slope)
            )
            for position, patch in layout:
                self.grid.place_agent(patch, position)
                self._terrain_by_pos[position] = patch
            return

        # Test seam: mapping position -> (terrain class, elevation, slope)
        # or (terrain class, elevation, slope) as a list entry.
        items = (
            terrain_layout.items()
            if isinstance(terrain_layout, Mapping)
            else terrain_layout
        )
        uid = 10000
        for position, spec in items:
            if isinstance(spec, TerrainPatch):
                patch = spec
            else:
                terrain_cls, elevation, slope = spec
                patch = terrain_cls(uid, self, float(elevation), float(slope))
            self.grid.place_agent(patch, position)
            self._terrain_by_pos[tuple(position)] = patch
            uid += 1

        # A partial layout is filled with safe ground for deterministic tests.
        for x in range(self.config.width):
            for y in range(self.config.height):
                if (x, y) not in self._terrain_by_pos:
                    patch = SafeRegolith(uid, self, 0.0, 0.0)
                    self.grid.place_agent(patch, (x, y))
                    self._terrain_by_pos[(x, y)] = patch
                    uid += 1

    def _setup_rovers(self) -> None:
        if self.num_rovers <= 0:
            self.running = False
            self.termination_reason = "no_rovers"
            return

        safe = sorted(
            position
            for position, terrain in self._terrain_by_pos.items()
            if terrain.traversable
            and terrain.terrain_type
            in {TerrainType.SAFE_REGOLITH, TerrainType.LOOSE_SAND}
        )
        fallback = sorted(self.traversable_cells)
        candidates = safe if self.config.spawn_on_safe and safe else fallback
        if not candidates:
            raise ValueError("The generated map has no traversable spawn cells")

        chosen: list[Position] = []
        pool = list(candidates)
        for _ in range(self.num_rovers):
            valid = [
                position
                for position in pool
                if all(
                    hex_distance(position, other) >= self.config.min_spawn_distance
                    for other in chosen
                )
            ]
            if not valid:
                valid = pool
            if not valid:  # pragma: no cover - defensive
                raise ValueError("Not enough cells to spawn rovers")
            position = self.random.choice(valid)
            chosen.append(position)
            pool.remove(position)

        for index, position in enumerate(chosen):
            factory = self._strategy_factory or create_strategy
            strategy = factory(self.config.navigation_mode, self.config, self.seed)
            rover = Pioneer3DXAgent(
                index,
                self,
                strategy=strategy,
                target=None,
                navigation_mode=self.config.navigation_mode,
                mission_mode=self.config.mission_mode,
            )
            self.schedule.add(rover)
            self.grid.place_agent(rover, position)
            self._rover_by_id[rover.unique_id] = rover
            self.spawn_positions[rover.unique_id] = position
            rover.path = [position]
            rover.visited = {position}
            rover.current_terrain_type = (
                self.terrain_at(position).terrain_type
                if self.terrain_at(position)
                else None
            )

        self._assign_targets()

    def _assign_targets(self) -> None:
        if self.config.mission_mode == "exploration":
            for rover in self.rovers():
                rover.target = None
            return

        if self.config.targets is not None:
            for rover, target in zip(self.rovers(), self.config.targets):
                terrain = self.terrain_at(target)
                if terrain is None or not terrain.traversable:
                    raise ValueError(f"Explicit target {target} is not traversable")
                rover.target = tuple(target)
            return

        used: set[Position] = set()
        for rover in self.rovers():
            reachable = self._reachable_cells(rover.pos)
            if not reachable:
                raise ValueError(f"No reachable target from {rover.pos}")
            max_distance = max(hex_distance(rover.pos, cell) for cell in reachable)
            desired = max(1, round(max_distance * self.config.goal_target_fraction))
            ordered = sorted(
                reachable,
                key=lambda cell: (
                    abs(hex_distance(rover.pos, cell) - desired),
                    -hex_distance(rover.pos, cell),
                    cell,
                ),
            )
            target = next((cell for cell in ordered if cell not in used), None)
            if target is None:
                target = ordered[0]
            used.add(target)
            rover.target = target

    def _reachable_cells(self, start: Position) -> set[Position]:
        if not self.is_in_bounds(start):
            return set()
        seen = {start}
        queue = deque([start])
        while queue:
            position = queue.popleft()
            for neighbour in self.grid.get_neighborhood(
                position, include_center=False, radius=1
            ):
                if neighbour in seen:
                    continue
                terrain = self.terrain_at(neighbour)
                if terrain is None or not terrain.traversable:
                    continue
                seen.add(neighbour)
                queue.append(neighbour)
        return seen

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def is_in_bounds(self, position: Position) -> bool:
        x, y = position
        return 0 <= x < self.grid.width and 0 <= y < self.grid.height

    def terrain_at(self, position: Position) -> TerrainPatch | None:
        return self._terrain_by_pos.get(tuple(position))

    def rover_at(
        self, position: Position, exclude_id: int | None = None
    ) -> Pioneer3DXAgent | None:
        for rover in self._rover_by_id.values():
            if rover.pos == position and rover.unique_id != exclude_id:
                return rover
        return None

    def rovers(self) -> list[Pioneer3DXAgent]:
        return [self._rover_by_id[key] for key in sorted(self._rover_by_id)]

    def rovers_in_range(
        self, position: Position, radius: int
    ) -> list[Pioneer3DXAgent]:
        return [
            rover
            for rover in self.rovers()
            if rover.pos is not None and hex_distance(rover.pos, position) <= radius
        ]

    def get_neighborhood_info(
        self, position: Position, radius: int = 1
    ) -> list[TerrainPatch]:
        positions = self.grid.get_neighborhood(
            position, include_center=False, radius=radius
        )
        return [
            terrain
            for terrain in (self.terrain_at(cell) for cell in positions)
            if terrain is not None
        ]

    def mark_discovered(self, positions: Iterable[Position]) -> None:
        self._discovered_cells.update(positions)

    def coverage(self) -> tuple[float, float]:
        total = len(self.traversable_cells)
        if total == 0:
            return (0.0, 0.0)
        visited: set[Position] = set()
        for rover in self.rovers():
            visited.update(rover.visited)
        discovered = self._discovered_cells & self.traversable_cells
        return (
            len(visited & self.traversable_cells) / total,
            len(discovered) / total,
        )

    def terrain_hash(self) -> str:
        digest = hashlib.sha256()
        for x in range(self.grid.width):
            for y in range(self.grid.height):
                terrain = self.terrain_at((x, y))
                if terrain is None:
                    continue
                digest.update(
                    (
                        f"{x},{y},{terrain.terrain_type.value},"
                        f"{terrain.elevation:.6f},{terrain.slope:.6f};"
                    ).encode()
                )
        return digest.hexdigest()[:16]

    # ------------------------------------------------------------------
    # Clock / termination
    # ------------------------------------------------------------------
    def step(self) -> None:
        if not self.running:
            return
        # Mesa 2.4's BaseScheduler._wrapped_step calls model._advance_time().
        # Do not increment the model clock here or every step is counted twice.
        # Expose the step that is about to execute so agents stamp events,
        # fear records and radio packets with the correct time.
        self.step_count = self._steps + 1
        self.schedule.step()
        self.step_count = self._steps
        self.swarm.process_signals(self)
        self._apply_mission_controller()
        self.datacollector.collect(self)
        self._update_termination()

    def _apply_mission_controller(self) -> None:
        for rover in self.rovers():
            if (
                rover.mission_status == "no_path"
                and self.config.mission_mode == "goal_navigation"
                and self.config.allow_exploration_fallback
            ):
                rover.mission_mode = "exploration"
                rover.target = None
                rover.mission_status = "active"
                rover.status_reason = "fallback to exploration"
                self.record_event(
                    "exploration_fallback",
                    rover_id=rover.unique_id,
                    position=rover.pos,
                )

    def _update_termination(self) -> None:
        rovers = self.rovers()
        if self.step_count >= self.config.max_steps:
            self._finish("max_steps")
            return

        if not rovers:
            self._finish("no_rovers")
            return

        active = [rover for rover in rovers if rover.is_active]
        if active:
            if (
                self.config.mission_mode == "exploration"
                and self.coverage()[1] >= self.config.coverage_target
            ):
                self._finish("coverage_target")
                return
            if (
                self.config.mission_mode == "exploration"
                and self.step_count >= self.config.exploration_budget
            ):
                self._finish("exploration_budget")
                return
            return

        statuses = {rover.mission_status for rover in rovers}
        if self.config.mission_mode == "goal_navigation" and statuses == {
            "goal_reached"
        }:
            self._finish("all_goals_reached")
        elif self.config.mission_mode == "exploration" and statuses <= {
            "exploration_complete"
        }:
            self._finish("exploration_complete")
        else:
            self._finish("all_rovers_inactive")

    def _finish(self, reason: str) -> None:
        if self.running:
            self.running = False
            self.termination_reason = reason

    # ------------------------------------------------------------------
    # Events / visualization
    # ------------------------------------------------------------------
    def record_event(self, event_type: str, **payload: Any) -> None:
        event = {"type": event_type, "step": int(self.step_count)}
        for key, value in payload.items():
            if key == "signature" and isinstance(value, tuple):
                event[key] = list(value)
            else:
                event[key] = value
        self._events.append(event)

    def events_snapshot(self, limit: int = 32) -> list[dict[str, Any]]:
        return list(self._events)[-limit:]

    def fear_positions_snapshot(self, limit: int = 64) -> list[Position]:
        positions: list[Position] = []
        seen: set[Position] = set()
        for rover in self.rovers():
            for record in rover.anxiety_memory.values():
                position = record.source_position
                if position is not None and position not in seen:
                    seen.add(position)
                    positions.append(position)
                    if len(positions) >= limit:
                        return positions
        return positions


__all__ = ["MarsSimulation"]
