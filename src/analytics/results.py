"""Serializable experiment result objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.model.types import Position


@dataclass
class EpisodeResult:
    config: dict[str, Any]
    seed: int
    navigation_mode: str
    mission_mode: str
    is_scientific: bool
    metrics: dict[str, Any]
    rovers: list[dict[str, Any]]
    trajectory: dict[int, list[Position]]
    terrain_hash: str
    termination_reason: str | None
    steps: list[dict[str, Any]] = field(default_factory=list)
    agent_steps: list[dict[str, Any]] = field(default_factory=list)
    wall_clock_s: float = 0.0

    def to_row(self) -> dict[str, Any]:
        row = {
            "seed": self.seed,
            "navigation_mode": self.navigation_mode,
            "mission_mode": self.mission_mode,
            "is_scientific": self.is_scientific,
            "terrain_hash": self.terrain_hash,
            "termination_reason": self.termination_reason,
            "wall_clock_s": self.wall_clock_s,
        }
        row.update(self.metrics)
        return row

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["trajectory"] = {
            str(key): [[int(x), int(y)] for x, y in value]
            for key, value in self.trajectory.items()
        }
        return data


__all__ = ["EpisodeResult"]
