"""Terrain JSON serialization shared by the static and live server paths."""

from __future__ import annotations

from typing import Any

from src.model.model import MarsSimulation


def terrain_payload_from_model(model: MarsSimulation) -> dict[str, Any]:
    """Serialize the model's terrain using the existing API contract."""

    cells: list[dict[str, Any]] = []
    for x in range(model.grid.width):
        for y in range(model.grid.height):
            terrain = model.terrain_at((x, y))
            if terrain is None:
                raise RuntimeError(f"No terrain generated for cell ({x}, {y})")
            cells.append(
                {
                    "x": x,
                    "y": y,
                    "type": type(terrain).__name__,
                    "color": terrain.color,
                    "elevation": float(terrain.elevation),
                    "slope": float(terrain.slope),
                }
            )
    return {
        "width": model.grid.width,
        "height": model.grid.height,
        "cells": cells,
    }


def generate_terrain_grid(
    width: int,
    height: int,
    model: MarsSimulation | None = None,
) -> dict[str, Any]:
    """Backward-compatible terrain generator used by tests/show_map."""

    if model is None:
        model = MarsSimulation(width=width, height=height, num_rovers=0)
    return terrain_payload_from_model(model)


__all__ = ["generate_terrain_grid", "terrain_payload_from_model"]
