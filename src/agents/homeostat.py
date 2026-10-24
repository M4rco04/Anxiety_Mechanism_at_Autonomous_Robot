"""Homeostat model from ``src/agents/instruction.md`` section 6."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from config.config import HomeostatConfig
from src.model.types import clamp


@dataclass(frozen=True)
class HomeostatReading:
    """Result of a single homeostat update."""

    instantaneous: float
    smoothed: float
    components: dict[str, float] = field(default_factory=dict)
    critical: bool = False


class Homeostat:
    """Tracks the robot's internal stress level.

    The implementation follows the formula from the project instructions::

        S_inst = w1 * dB + w2 * max(0, 1 - V_act / V_target)
               + w3 * (exp(k * (100 - hull)) - 1)
               + w4 * (exp(k * (100 - wheel)) - 1)
               + w5 * max(0, slope - alpha_safe)

        S_new = beta * S_prev + (1 - beta) * S_inst
    """

    def __init__(self, config: HomeostatConfig | None = None) -> None:
        self.config = config or HomeostatConfig()
        self.config.validate()
        self.previous = 0.0
        self.last_components: dict[str, float] = {}

    def reset(self) -> None:
        self.previous = 0.0
        self.last_components = {}

    def update(
        self,
        *,
        delta_battery: float,
        target_speed: float,
        current_speed: float,
        hull_condition: float,
        wheel_condition: float,
        current_slope: float,
    ) -> HomeostatReading:
        cfg = self.config

        delta_battery = max(0.0, _finite(delta_battery))
        target_speed = max(0.0, _finite(target_speed))
        current_speed = max(0.0, _finite(current_speed))
        hull_condition = clamp(_finite(hull_condition, 100.0), 0.0, 100.0)
        wheel_condition = clamp(_finite(wheel_condition, 100.0), 0.0, 100.0)
        current_slope = max(0.0, _finite(current_slope))

        slip = (
            0.0
            if target_speed <= 1e-9
            else max(0.0, 1.0 - current_speed / target_speed)
        )
        hull_term = math.exp(cfg.k * (100.0 - hull_condition)) - 1.0
        wheel_term = math.exp(cfg.k * (100.0 - wheel_condition)) - 1.0
        slope_term = max(0.0, current_slope - cfg.alpha_safe)

        components = {
            "battery": cfg.w1 * delta_battery,
            "slip": cfg.w2 * slip,
            "hull": cfg.w3 * hull_term,
            "wheel": cfg.w4 * wheel_term,
            "slope": cfg.w5 * slope_term,
        }
        instantaneous = sum(components.values())
        smoothed = clamp(
            cfg.beta * self.previous + (1.0 - cfg.beta) * instantaneous,
            0.0,
            100.0,
        )
        self.previous = smoothed
        self.last_components = components
        return HomeostatReading(
            instantaneous=instantaneous,
            smoothed=smoothed,
            components=components,
            critical=smoothed >= cfg.s_crit,
        )


def _finite(value: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


__all__ = ["Homeostat", "HomeostatReading"]
