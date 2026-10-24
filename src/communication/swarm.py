"""End-of-step swarm radio propagation."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from src.communication.radio import RadioModule, RadioPacket

if TYPE_CHECKING:  # pragma: no cover
    from src.model.model import MarsSimulation


class SwarmBroadcaster:
    """Queues fear packets and delivers them after every rover has acted.

    Delivering at the end of the model step avoids scheduler-order-dependent
    radio effects and makes the comparison between variants reproducible.
    """

    def __init__(
        self,
        model: MarsSimulation,
        range_hex: int = 20,
        enabled: bool = True,
    ) -> None:
        self.model = model
        self.enabled = bool(enabled)
        self.range_hex = max(0, int(range_hex))
        self.radio = RadioModule(model, self.range_hex, self.enabled)
        self._outbox: deque[RadioPacket] = deque()
        self.total_sent = 0
        self.total_delivered = 0

    @property
    def pending(self) -> int:
        return len(self._outbox)

    def broadcast(self, packet: RadioPacket) -> bool:
        if not self.enabled:
            return False
        self._outbox.append(packet)
        self.total_sent += 1
        self.model.record_event(
            "radio_sent",
            rover_id=packet.sender_id,
            position=packet.position,
            signature=packet.signature,
        )
        return True

    def process_signals(self, model: MarsSimulation) -> int:
        if not self._outbox:
            return 0
        delivered = 0
        packets = list(self._outbox)
        self._outbox.clear()
        for packet in packets:
            for receiver in self.radio.receivers(packet):
                if receiver.receive_signal(packet):
                    delivered += 1
                    model.record_event(
                        "radio_received",
                        rover_id=receiver.unique_id,
                        position=receiver.pos,
                        signature=packet.signature,
                    )
        self.total_delivered += delivered
        model.radio_packets_received += delivered
        return delivered


__all__ = ["SwarmBroadcaster"]
