"""Typed radio packets and range helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.model.types import RGB, Position, clamp, hex_distance

if TYPE_CHECKING:  # pragma: no cover
    from src.model.model import MarsSimulation


@dataclass(frozen=True)
class RadioPacket:
    signature: RGB
    position: Position
    intensity: float
    sender_id: int
    created_at: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "signature", tuple(int(c) for c in self.signature)
        )
        object.__setattr__(self, "intensity", clamp(self.intensity, 0.0, 1.0))

    @property
    def key(self) -> tuple[int, int, RGB]:
        return (self.sender_id, self.created_at, self.signature)


class RadioModule:
    """Small range/query helper used by the broadcaster."""

    def __init__(
        self,
        model: MarsSimulation,
        range_hex: int = 20,
        enabled: bool = True,
    ) -> None:
        self.model = model
        self.range_hex = max(0, int(range_hex))
        self.enabled = bool(enabled)

    def in_range(self, a: Position, b: Position) -> bool:
        return hex_distance(a, b) <= self.range_hex

    def receivers(self, packet: RadioPacket) -> list:
        if not self.enabled:
            return []
        return [
            rover
            for rover in self.model.rovers_in_range(
                packet.position, self.range_hex
            )
            if rover.unique_id != packet.sender_id
        ]

    def create_packet(
        self, sender, signature: RGB, position: Position, intensity: float
    ) -> RadioPacket:
        return RadioPacket(
            signature=signature,
            position=position,
            intensity=intensity,
            sender_id=sender.unique_id,
            created_at=self.model.step_count,
        )


__all__ = ["RadioModule", "RadioPacket"]
