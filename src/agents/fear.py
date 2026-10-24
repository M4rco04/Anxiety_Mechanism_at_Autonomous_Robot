"""Fear memory records and matching helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from src.model.types import RGB, Position, clamp, rgb_distance

FearSource = Literal["self", "radio", "mixed"]


@dataclass
class FearRecord:
    """One imprinted visual signature.

    ``intensity`` is normalized to 0..1.  ``source_position`` lets the
    visualization and result tables explain where a radio fear came from.
    """

    signature: RGB
    intensity: float = 1.0
    visits: int = 1
    last_seen_step: int = 0
    source_position: Position | None = None
    source: FearSource = "self"

    def __post_init__(self) -> None:
        self.signature = tuple(int(channel) for channel in self.signature)  # type: ignore[assignment]
        self.intensity = clamp(self.intensity, 0.0, 1.0)


@dataclass(frozen=True)
class FearView:
    """Immutable, decayed view of a fear record for navigation."""

    signature: RGB
    intensity: float
    last_seen_step: int
    source_position: Position | None
    source: str


def find_matching_record(
    records: dict[RGB, FearRecord] | dict[RGB, FearView],
    signature: RGB,
    tolerance: float,
) -> tuple[RGB, FearRecord | FearView] | None:
    """Find the nearest signature within ``tolerance``."""

    best: tuple[float, RGB, FearRecord | FearView] | None = None
    for key, record in records.items():
        distance = rgb_distance(key, signature)
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, key, record)
    if best is None:
        return None
    return (best[1], best[2])


def effective_intensity(
    record: FearRecord,
    *,
    current_step: int,
    decay: float,
) -> float:
    age = max(0, int(current_step) - int(record.last_seen_step))
    return record.intensity * math.exp(-max(0.0, decay) * age)


def fear_cost(
    record: FearRecord,
    *,
    current_step: int,
    decay: float,
    weight: float,
) -> float:
    return weight * effective_intensity(
        record, current_step=current_step, decay=decay
    )


__all__ = [
    "FearRecord",
    "FearSource",
    "FearView",
    "effective_intensity",
    "fear_cost",
    "find_matching_record",
]
