"""Pioneer 3-DX rover agent.

The rover owns its physical state, sensors, homeostat, fear memory and radio
behaviour.  It intentionally delegates route selection to an external
navigation strategy; this is the handoff point for Karol's algorithms.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import mesa

from src.agents.fear import (
    FearRecord,
    FearView,
    effective_intensity,
    find_matching_record,
)
from src.agents.homeostat import Homeostat, HomeostatReading
from src.communication.radio import RadioPacket
from src.environment.terrain import Boulders, TerrainPatch, TerrainType
from src.model.types import (
    RGB,
    Position,
    clamp,
    hex_distance,
    hex_vector,
)
from src.navigation.observation import build_observation
from src.navigation.types import NavigationDecision, NavigationStrategy

if TYPE_CHECKING:  # pragma: no cover
    from src.model.model import MarsSimulation


class Pioneer3DXAgent(mesa.Agent):
    """Autonomous rover with a conditioned-anxiety mechanism."""

    def __init__(
        self,
        unique_id: int,
        model: MarsSimulation,
        *,
        strategy: NavigationStrategy | None = None,
        target: Position | None = None,
        navigation_mode: str | None = None,
        mission_mode: str | None = None,
    ) -> None:
        super().__init__(unique_id, model)
        config = model.config

        self.strategy = strategy
        self.navigation_mode = navigation_mode or config.navigation_mode
        self.mission_mode = mission_mode or config.mission_mode
        self.target = target
        self.homeostat = Homeostat(config.homeostat)

        # Physical state
        self.battery = 100.0
        self.battery_prev = 100.0
        self.base_speed = 1.0
        self.target_speed = 1.0
        self.current_speed = 1.0
        self.wheel_condition = 100.0
        self.hull_condition = 100.0
        self.stress_level = 0.0
        self.stress_armed = True

        # Perception
        self.base_vision_range = int(config.vision_range)
        self.vision_range = int(config.vision_range)
        self.lidar_range = int(config.lidar_range)
        self.heading: Position = (0, 1)

        # Environment exposure / safety
        self.shadow_exposure_time = 0
        self.dust_exposure_time = 0
        self.gyro_alarm = False
        self.is_overturned = False
        self.is_destroyed = False

        # Mission state
        self.mission_status = "active"
        self.status_reason: str | None = None
        self.exploration_budget = int(config.exploration_budget)
        self.coverage_target = float(config.coverage_target)
        self.path: list[Position] = []
        self.visited: set[Position] = set()
        self.moves = 0
        self.backtracks = 0
        self.blocked_moves = 0
        self.collisions = 0
        self.overturns = 0
        self.stress_sum = 0.0
        self.stress_samples = 0
        self.critical_events = 0
        self.goal_step: int | None = None
        self.previous_position: Position | None = None
        self.previous_terrain_type: TerrainType | None = None
        self.current_terrain_type: TerrainType | None = None
        self.last_effect: dict = {}
        self.last_action_reason = ""

        # Anxiety memory
        self.anxiety_memory: dict[RGB, FearRecord] = {}
        self.fear_events_own = 0
        self.fear_events_received = 0
        self.fear_entries = 0
        self.forced_fear_entries = 0

        # Radio bookkeeping
        self._received_packet_keys: set[tuple[int, int, RGB]] = set()
        self._overturn_counted = False
        self._goal_event_sent = False

        self.emotional_enabled = self.navigation_mode in {
            "emotional",
            "swarm_emotional",
        }

    # ------------------------------------------------------------------
    # Status / geometry properties
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        if self.is_destroyed or self.is_overturned or self.battery <= 0.0:
            return False
        return self.mission_status not in {
            "goal_reached",
            "exploration_complete",
            "no_path",
            "destroyed",
            "overturned",
        }

    @property
    def current_terrain(self) -> TerrainPatch | None:
        return self.model.terrain_at(self.pos)

    @property
    def emotional_mode(self) -> bool:
        return self.emotional_enabled

    @property
    def current_slope(self) -> float:
        terrain = self.current_terrain
        if terrain is None:
            return 0.0
        return clamp(terrain.slope, 0.0, self.model.config.max_slope_deg)

    # ------------------------------------------------------------------
    # Sensors
    # ------------------------------------------------------------------
    def read_lidar(self) -> set[Position]:
        """Return LIDAR-visible physical obstacles (primarily boulders)."""

        if self.lidar_range <= 0:
            positions = [self.pos]
        else:
            positions = self.model.grid.get_neighborhood(
                self.pos,
                include_center=True,
                radius=self.lidar_range,
            )
        obstacles: set[Position] = set()
        for position in positions:
            terrain = self.model.terrain_at(position)
            if isinstance(terrain, Boulders):
                obstacles.add(position)
        return obstacles

    def read_rgb_cameras(self) -> dict[Position, RGB]:
        """Read visible terrain signatures through a forward camera FOV.

        Dust storms reduce ``vision_range``; LIDAR is deliberately unaffected.
        The current cell is always visible so the rover can imprint its own
        circumstances even in zero-visibility dust.
        """

        positions: list[Position] = [self.pos]
        if self.vision_range > 0:
            positions = list(
                self.model.grid.get_neighborhood(
                    self.pos,
                    include_center=True,
                    radius=int(self.vision_range),
                )
            )

        readings: dict[Position, RGB] = {}
        fov = float(self.model.config.rgb_fov_deg)
        sigma = float(self.model.config.rgb_noise_sigma)
        cos_limit = (
            math.cos(math.radians(fov / 2.0)) if fov < 359.9 else -2.0
        )
        heading_px = self._hex_to_pixel(hex_vector((0, 0), self.heading)) if self.heading != (0, 0) else (0.0, 1.0)
        heading_norm = math.hypot(*heading_px) or 1.0

        for position in positions:
            terrain = self.model.terrain_at(position)
            if terrain is None:
                continue
            if position != self.pos and fov < 359.9:
                vector = self._hex_to_pixel(hex_vector(self.pos, position))
                norm = math.hypot(*vector) or 1.0
                cosine = (vector[0] * heading_px[0] + vector[1] * heading_px[1]) / (
                    norm * heading_norm
                )
                if cosine < cos_limit:
                    continue
            readings[position] = self._sensor_signature(
                terrain.optical_signature, sigma
            )
        return readings

    def _sensor_signature(self, signature: RGB, sigma: float) -> RGB:
        if sigma <= 0:
            return signature
        rng = self.model.rng
        values = [
            int(clamp(channel + float(rng.normal(0.0, sigma)), 0, 255))
            for channel in signature
        ]
        return (values[0], values[1], values[2])

    @staticmethod
    def _hex_to_pixel(vector: tuple[int, int, int]) -> tuple[float, float]:
        q, r = vector[0], vector[1]
        return (
            math.sqrt(3.0) * (q + r / 2.0),
            1.5 * r,
        )

    def current_signature(self) -> RGB | None:
        terrain = self.current_terrain
        return terrain.optical_signature if terrain is not None else None

    # ------------------------------------------------------------------
    # Fear memory
    # ------------------------------------------------------------------
    def learn_fear(
        self,
        signature: RGB,
        *,
        intensity: float = 1.0,
        source: str = "self",
        source_position: Position | None = None,
    ) -> bool:
        if signature is None or len(signature) != 3:
            return False
        signature = tuple(int(clamp(channel, 0, 255)) for channel in signature)  # type: ignore[assignment]
        intensity = clamp(intensity, 0.0, 1.0)
        matched = find_matching_record(
            self.anxiety_memory,
            signature,
            float(self.model.config.fear_rgb_tolerance),
        )
        if matched is not None:
            _, record = matched
            record.intensity = clamp(record.intensity + intensity, 0.0, 1.0)
            record.visits += 1
            record.last_seen_step = int(self.model.step_count)
            if source_position is not None and record.source_position is None:
                record.source_position = source_position
            if record.source != source:
                record.source = "mixed"
        else:
            self.anxiety_memory[signature] = FearRecord(
                signature=signature,
                intensity=intensity,
                visits=1,
                last_seen_step=int(self.model.step_count),
                source_position=source_position,
                source=source,  # type: ignore[arg-type]
            )
        if source == "self":
            self.fear_events_own += 1
        elif source == "radio":
            self.fear_events_received += 1
        return True

    def fear_intensity(self, signature: RGB | None, step: int | None = None) -> float:
        if signature is None or not self.anxiety_memory:
            return 0.0
        matched = find_matching_record(
            self.anxiety_memory,
            signature,
            float(self.model.config.fear_rgb_tolerance),
        )
        if matched is None:
            return 0.0
        record = matched[1]
        return effective_intensity(
            record,
            current_step=self.model.step_count if step is None else step,
            decay=float(self.model.config.fear_decay),
        )

    def current_fear_intensity(self) -> float:
        return self.fear_intensity(self.current_signature())

    def fear_map(self) -> dict[RGB, FearView]:
        return {
            signature: FearView(
                signature=signature,
                intensity=effective_intensity(
                    record,
                    current_step=self.model.step_count,
                    decay=float(self.model.config.fear_decay),
                ),
                last_seen_step=record.last_seen_step,
                source_position=record.source_position,
                source=record.source,
            )
            for signature, record in self.anxiety_memory.items()
        }

    def receive_signal(self, packet: RadioPacket) -> bool:
        if self.navigation_mode != "swarm_emotional":
            return False
        if not getattr(self.model, "swarm", None) or not self.model.swarm.enabled:
            return False
        if packet.sender_id == self.unique_id:
            return False
        if packet.key in self._received_packet_keys:
            return False
        max_range = int(self.model.config.R_radio)
        if hex_distance(packet.position, self.pos) > max_range:
            return False
        self._received_packet_keys.add(packet.key)
        return self.learn_fear(
            packet.signature,
            intensity=packet.intensity * float(self.model.config.radio_fear_gain),
            source="radio",
            source_position=packet.position,
        )

    def broadcast_danger(self, signature: RGB, position: Position) -> bool:
        if self.navigation_mode != "swarm_emotional":
            return False
        if not getattr(self.model, "swarm", None):
            return False
        intensity = clamp(self.stress_level / 100.0, 0.1, 1.0)
        packet = self.model.swarm.radio.create_packet(
            self, signature, position, intensity
        )
        return self.model.swarm.broadcast(packet)

    # ------------------------------------------------------------------
    # Homeostat
    # ------------------------------------------------------------------
    def update_homeostat(
        self,
        delta_battery: float,
        target_speed: float,
        current_speed: float,
        hull_condition: float,
        wheel_condition: float,
        current_slope: float,
    ) -> HomeostatReading:
        reading = self.homeostat.update(
            delta_battery=delta_battery,
            target_speed=target_speed,
            current_speed=current_speed,
            hull_condition=hull_condition,
            wheel_condition=wheel_condition,
            current_slope=current_slope,
        )
        self.stress_level = reading.smoothed
        return reading

    # ------------------------------------------------------------------
    # Main step
    # ------------------------------------------------------------------
    def step(self) -> None:
        if self.mission_status in {
            "goal_reached",
            "exploration_complete",
            "no_path",
            "destroyed",
            "overturned",
        }:
            return
        if self.is_destroyed:
            return
        if self.is_overturned or self.battery <= 0.0:
            self._update_mission_status()
            return

        self.battery_prev = self.battery
        self.previous_position = self.pos
        self.previous_terrain_type = self.current_terrain_type
        self.gyro_alarm = False
        self.target_speed = 0.0
        self.current_speed = 0.0

        observation = build_observation(self)
        decision = (
            self.strategy.choose_next(self, observation)
            if self.strategy is not None
            else None
        )

        moved = False
        if decision is not None and decision.next_position is not None:
            moved = self._execute_move(decision)
            if not moved:
                self.mission_status = "blocked"
                self.status_reason = decision.reason
                self.last_action_reason = decision.reason
        else:
            if decision is not None and decision.status in {
                "goal_reached",
                "exploration_complete",
                "no_path",
                "blocked",
            }:
                self.mission_status = decision.status
                self.status_reason = decision.reason
            elif self.target is not None and self.pos == self.target:
                self.mission_status = "goal_reached"
                self.status_reason = "target reached"
            else:
                self.mission_status = "no_path"
                self.status_reason = "strategy returned no move"
            self.last_action_reason = self.status_reason or ""
            self._update_exposure(self.current_terrain_type, moved=False)

        reading = self.update_homeostat(
            delta_battery=max(0.0, self.battery_prev - self.battery),
            target_speed=self.target_speed,
            current_speed=self.current_speed,
            hull_condition=self.hull_condition,
            wheel_condition=self.wheel_condition,
            current_slope=self.current_slope,
        )
        self.stress_sum += self.stress_level
        self.stress_samples += 1
        if reading.critical:
            self.critical_events += 1
        self._handle_anxiety(reading)
        self._check_destruction()
        self._update_mission_status()

        if (
            self.mission_mode == "exploration"
            and self.mission_status == "active"
        ):
            _, discovered = self.model.coverage()
            if (
                discovered >= self.coverage_target
                or self.model.step_count >= self.exploration_budget
            ):
                self.mission_status = "exploration_complete"
                self.status_reason = "exploration budget/coverage reached"

    def _execute_move(self, decision: NavigationDecision) -> bool:
        next_position = decision.next_position
        if next_position is None or not self._is_valid_move(next_position):
            self.blocked_moves += 1
            return False
        if decision.status == "forced_fear_visit":
            self.forced_fear_entries += 1

        old_position = self.pos
        self.target_speed = self.base_speed
        self.current_speed = self.base_speed
        self.model.grid.move_agent(self, next_position)
        self.heading = self._direction_from_step(old_position, next_position)
        self.path.append(next_position)
        self.visited.add(next_position)
        self.moves += 1
        self.last_action_reason = decision.reason

        terrain = self.model.terrain_at(next_position)
        if terrain is None:  # pragma: no cover - defensive
            self.is_destroyed = True
            self.mission_status = "destroyed"
            return False

        self.current_terrain_type = terrain.terrain_type
        self._update_exposure(terrain.terrain_type, moved=True)

        before = (
            self.battery,
            self.hull_condition,
            self.wheel_condition,
            self.current_speed,
            self.vision_range,
        )
        terrain.apply_effect(self)
        self.last_effect = {
            "terrain": terrain.terrain_type.value,
            "battery_delta": self.battery - before[0],
            "hull_delta": self.hull_condition - before[1],
            "wheel_delta": self.wheel_condition - before[2],
            "speed_delta": self.current_speed - before[3],
            "vision_before": before[4],
            "vision_after": self.vision_range,
        }

        if terrain.terrain_type == TerrainType.BOULDERS:
            self.collisions += 1
        if self.is_overturned and not self._overturn_counted:
            self._overturn_counted = True
            self.overturns += 1
            self.model.record_event(
                "overturned", rover_id=self.unique_id, position=self.pos
            )

        signature = terrain.optical_signature
        if self.fear_intensity(signature) > 0.0:
            self.fear_entries += 1

        if self.target is not None and self.pos == self.target:
            self.mission_status = "goal_reached"
            self.status_reason = "target reached"
            self._send_goal_event()
        return True

    def _is_valid_move(self, position: Position) -> bool:
        if not self.model.is_in_bounds(position):
            return False
        terrain = self.model.terrain_at(position)
        if terrain is None or not terrain.traversable:
            return False
        return not (
            self.model.rover_at(position, exclude_id=self.unique_id) is not None
            and not self.model.config.allow_rover_overlap
        )

    @staticmethod
    def _direction_from_step(old: Position, new: Position) -> Position:
        return (new[0] - old[0], new[1] - old[1])

    def _update_exposure(
        self, terrain_type: TerrainType | None, *, moved: bool
    ) -> None:
        if terrain_type == TerrainType.DEEP_SHADOW:
            if moved:
                self.shadow_exposure_time += 1
            self.dust_exposure_time = 0
            if self.vision_range != self.base_vision_range:
                self.vision_range = self.base_vision_range
        elif terrain_type == TerrainType.DUST_STORM:
            if moved:
                self.dust_exposure_time += 1
            self.shadow_exposure_time = 0
        else:
            self.shadow_exposure_time = 0
            self.dust_exposure_time = 0
            self.vision_range = self.base_vision_range

    def _handle_anxiety(self, reading: HomeostatReading) -> None:
        if reading.critical and self.stress_armed:
            if self.emotional_enabled:
                signature = self.current_signature()
                if signature is not None:
                    self.learn_fear(
                        signature,
                        intensity=1.0,
                        source="self",
                        source_position=self.pos,
                    )
                    self.model.record_event(
                        "fear_imprint",
                        rover_id=self.unique_id,
                        position=self.pos,
                        signature=signature,
                    )
                    if self.navigation_mode == "swarm_emotional":
                        self.broadcast_danger(signature, self.pos)
            self.stress_armed = False
        elif self.stress_level < (
            self.model.config.homeostat.s_crit
            * self.model.config.homeostat.rearm_factor
        ):
            self.stress_armed = True

    def _check_destruction(self) -> None:
        if (
            self.battery <= 0.0
            or self.hull_condition <= 0.0
            or self.wheel_condition <= 0.0
        ):
            self.is_destroyed = True
            self.mission_status = "destroyed"
            self.status_reason = "critical damage or battery depletion"
            self.model.record_event(
                "destroyed", rover_id=self.unique_id, position=self.pos
            )

    def _update_mission_status(self) -> None:
        if self.is_destroyed:
            self.mission_status = "destroyed"
        elif self.is_overturned:
            self.mission_status = "overturned"
        elif self.battery <= 0.0:
            self.mission_status = "destroyed"
        elif self.target is not None and self.pos == self.target:
            self.mission_status = "goal_reached"
            self._send_goal_event()

    def _send_goal_event(self) -> None:
        if not self._goal_event_sent:
            self._goal_event_sent = True
            self.goal_step = int(self.model.step_count)
            self.model.record_event(
                "goal_reached", rover_id=self.unique_id, position=self.pos
            )

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------
    def move(self) -> None:
        """Deprecated compatibility wrapper.

        Movement is selected by the strategy inside :meth:`step`.  Calling
        this method simply executes a complete step and must not be used by
        new code.
        """

        self.step()


__all__ = ["Pioneer3DXAgent"]
