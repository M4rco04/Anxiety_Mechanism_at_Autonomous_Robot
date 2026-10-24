"""Configuration serialization and validation tests."""

from __future__ import annotations

import math

import pytest

from config.config import SimulationConfig


def test_config_round_trip_and_hash():
    config = SimulationConfig(
        width=12,
        height=10,
        num_rovers=2,
        seed=77,
        mission_mode="exploration",
        fear_weight=12.5,
    )
    restored = SimulationConfig.from_dict(config.to_dict())
    assert restored == config
    assert restored.config_hash() == config.config_hash()
    assert math.isinf(restored.terrain_costs["Boulders"])


def test_invalid_config_is_rejected():
    with pytest.raises(ValueError):
        SimulationConfig(width=0).validate()
    with pytest.raises(ValueError):
        SimulationConfig(
            mission_mode="exploration", targets=((1, 1),), num_rovers=1
        ).validate()
    with pytest.raises(ValueError):
        SimulationConfig(navigation_mode="not-a-mode").validate()
