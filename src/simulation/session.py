"""Headless simulation session and JSON snapshots for the web UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from config.config import SimulationConfig
from src.analytics.metrics import collect_episode_metrics
from src.model.model import MarsSimulation
from src.model.types import Position
from src.navigation.registry import available_strategies


@dataclass(frozen=True)
class RoverSnapshot:
    rover_id: int
    position: Position
    previous_position: Position | None
    heading: Position
    battery: float
    wheel_condition: float
    hull_condition: float
    stress_level: float
    mission_status: str
    target: Position | None
    path: tuple[Position, ...]
    current_terrain: str | None
    terrain_slope: float
    terrain_type: str | None
    lidar_range: int
    vision_range: int
    action_reason: str
    fear_events_own: int
    fear_events_received: int
    fear_entries: int
    fear_records: int
    last_effect: dict[str, Any]


@dataclass(frozen=True)
class SimulationSnapshot:
    step: int
    running: bool
    termination_reason: str | None
    rovers: tuple[RoverSnapshot, ...]
    metrics: dict[str, Any]
    fear_positions: tuple[Position, ...]
    events: tuple[dict[str, Any], ...]
    seed: int
    navigation_mode: str
    mission_mode: str
    is_scientific: bool
    display_tick_ms: int
    width: int
    height: int


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SimulationSession:
    """Owns one MarsSimulation and exposes JSON-serializable snapshots."""

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.base_config = config or SimulationConfig()
        self._config = self.base_config
        self.model: MarsSimulation
        self.reset()

    @property
    def config(self) -> SimulationConfig:
        return self._config

    @property
    def running(self) -> bool:
        return bool(self.model.running)

    def reset(self, seed: int | None = None) -> SimulationSnapshot:
        config = self.base_config
        if seed is not None:
            config = replace(config, seed=int(seed))
        self._config = config
        self.model = MarsSimulation(config=config)
        return self.snapshot()

    def step(self) -> SimulationSnapshot:
        if self.model.running:
            self.model.step()
        return self.snapshot()

    def run(self, max_steps: int | None = None) -> SimulationSnapshot:
        limit = self._config.max_steps if max_steps is None else int(max_steps)
        while self.model.running and self.model.step_count < limit:
            self.model.step()
        return self.snapshot()

    def snapshot(self) -> SimulationSnapshot:
        model = self.model
        rovers = []
        for rover in model.rovers():
            terrain = model.terrain_at(rover.pos) if rover.pos is not None else None
            rovers.append(
                RoverSnapshot(
                    rover_id=int(rover.unique_id),
                    position=tuple(rover.pos) if rover.pos is not None else (0, 0),
                    previous_position=(
                        tuple(rover.previous_position)
                        if rover.previous_position is not None
                        else None
                    ),
                    heading=tuple(rover.heading),
                    battery=_safe_float(rover.battery),
                    wheel_condition=_safe_float(rover.wheel_condition),
                    hull_condition=_safe_float(rover.hull_condition),
                    stress_level=_safe_float(rover.stress_level),
                    mission_status=rover.mission_status,
                    target=tuple(rover.target) if rover.target is not None else None,
                    path=tuple(tuple(p) for p in rover.path),
                    current_terrain=(
                        terrain.terrain_type.value if terrain is not None else None
                    ),
                    terrain_slope=_safe_float(terrain.slope if terrain else 0.0),
                    terrain_type=(
                        terrain.terrain_type.value if terrain is not None else None
                    ),
                    lidar_range=int(rover.lidar_range),
                    vision_range=int(rover.vision_range),
                    action_reason=rover.last_action_reason,
                    fear_events_own=int(rover.fear_events_own),
                    fear_events_received=int(rover.fear_events_received),
                    fear_entries=int(rover.fear_entries),
                    fear_records=len(rover.anxiety_memory),
                    last_effect=_json_safe(rover.last_effect),
                )
            )

        strategy_info = available_strategies().get(
            model.config.navigation_mode, {}
        )
        is_scientific = bool(
            strategy_info.get("scientific", False)
            and strategy_info.get("implemented", False)
            and model.config.navigation_mode != "scaffold"
        )
        return SimulationSnapshot(
            step=int(model.step_count),
            running=bool(model.running),
            termination_reason=model.termination_reason,
            rovers=tuple(rovers),
            metrics=_json_safe(collect_episode_metrics(model)),
            fear_positions=tuple(model.fear_positions_snapshot()),
            events=tuple(model.events_snapshot()),
            seed=int(model.seed),
            navigation_mode=model.config.navigation_mode,
            mission_mode=model.config.mission_mode,
            is_scientific=is_scientific,
            display_tick_ms=int(model.config.display_tick_ms),
            width=int(model.config.width),
            height=int(model.config.height),
        )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def snapshot_to_dict(snapshot: SimulationSnapshot) -> dict[str, Any]:
    return _json_safe(asdict(snapshot))


__all__ = [
    "RoverSnapshot",
    "SimulationSession",
    "SimulationSnapshot",
    "snapshot_to_dict",
]
