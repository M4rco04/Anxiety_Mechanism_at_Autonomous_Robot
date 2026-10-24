"""Stateful simulation runtime used by the local web API."""

from __future__ import annotations

import threading
from typing import Any

from config.config import SimulationConfig
from server.terrain_data import terrain_payload_from_model
from src.simulation.session import SimulationSession, snapshot_to_dict


class SimulationRuntime:
    """Owns one session, serializes access and caches the terrain payload."""

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self.session = SimulationSession(config)
        self._terrain_cache: dict[str, Any] | None = None
        self._terrain_seed: int | None = None

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        with self._lock:
            previous_seed = getattr(self.session, "model", None)
            previous_seed = previous_seed.seed if previous_seed is not None else None
            snapshot = self.session.reset(seed=seed)
            new_seed = self.session.model.seed
            if new_seed != previous_seed or self._terrain_cache is None:
                self._terrain_cache = None
                self._terrain_seed = None
            return snapshot_to_dict(snapshot)

    def step(self) -> dict[str, Any]:
        with self._lock:
            return snapshot_to_dict(self.session.step())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return snapshot_to_dict(self.session.snapshot())

    def terrain_payload(self) -> dict[str, Any]:
        with self._lock:
            seed = self.session.model.seed
            if self._terrain_cache is None or self._terrain_seed != seed:
                self._terrain_cache = terrain_payload_from_model(
                    self.session.model
                )
                self._terrain_seed = seed
            return self._terrain_cache

    def metadata(self) -> dict[str, Any]:
        from src.navigation.registry import available_strategies

        with self._lock:
            return {
                "config": self.session.config.to_dict(),
                "config_hash": self.session.config.config_hash(),
                "strategies": available_strategies(),
                "running": self.session.running,
                "step": self.session.model.step_count,
            }


__all__ = ["SimulationRuntime"]
