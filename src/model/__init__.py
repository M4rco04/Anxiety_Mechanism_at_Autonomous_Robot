"""Simulation model and shared types."""

from src.model.types import (
    RGB,
    Position,
    clamp,
    hex_distance,
    hex_to_rgb,
    rgb_distance,
)

__all__ = [
    "RGB",
    "MarsSimulation",
    "Position",
    "clamp",
    "hex_distance",
    "hex_to_rgb",
    "rgb_distance",
]


def __getattr__(name):
    if name == "MarsSimulation":
        from src.model.model import MarsSimulation

        return MarsSimulation
    raise AttributeError(name)
