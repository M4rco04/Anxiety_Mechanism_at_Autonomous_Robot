"""Strategy registry and scientific-mode gating."""

from __future__ import annotations

from typing import Any

from config.config import SimulationConfig
from src.navigation.scaffold import ScaffoldStrategy
from src.navigation.strategies import STRATEGY_CLASSES
from src.navigation.types import NavigationStrategy


def create_strategy(
    navigation_mode: str,
    config: SimulationConfig,
    seed: int = 0,
) -> NavigationStrategy:
    """Create a strategy or fail loudly if a scientific mode is unfinished."""

    if navigation_mode == "scaffold":
        return ScaffoldStrategy(config, seed)  # type: ignore[return-value]

    strategy_class = STRATEGY_CLASSES.get(navigation_mode)
    if strategy_class is None:
        raise ValueError(f"Unknown navigation mode: {navigation_mode!r}")
    if not getattr(strategy_class, "IMPLEMENTED", False):
        raise NotImplementedError(
            f"TODO(Karol): navigation mode {navigation_mode!r} is not "
            "implemented yet. Use navigation_mode='scaffold' only for smoke "
            "tests; do not report its results as scientific evidence."
        )
    return strategy_class(config, seed)  # type: ignore[return-value]


def available_strategies() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {
        "scaffold": {"implemented": True, "scientific": False}
    }
    for name, cls in STRATEGY_CLASSES.items():
        result[name] = {
            "implemented": bool(getattr(cls, "IMPLEMENTED", False)),
            "scientific": bool(getattr(cls, "SCIENTIFIC", True)),
        }
    return result


__all__ = ["available_strategies", "create_strategy"]
