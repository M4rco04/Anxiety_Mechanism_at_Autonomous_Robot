"""Homeostat equation tests."""

from __future__ import annotations

import pytest

from config.config import HomeostatConfig
from src.agents.homeostat import Homeostat


def test_homeostat_known_value():
    homeostat = Homeostat(HomeostatConfig())
    reading = homeostat.update(
        delta_battery=1.0,
        target_speed=1.0,
        current_speed=0.5,
        hull_condition=100.0,
        wheel_condition=100.0,
        current_slope=15.0,
    )
    # instantaneous = 5*1 + 15*0.5 = 12.5; smoothed = 0.7*0 + 0.3*12.5
    assert reading.instantaneous == pytest.approx(12.5)
    assert reading.smoothed == pytest.approx(3.75)
    assert reading.critical is False


def test_zero_target_speed_has_no_slip_term():
    homeostat = Homeostat()
    reading = homeostat.update(
        delta_battery=0.0,
        target_speed=0.0,
        current_speed=0.0,
        hull_condition=100.0,
        wheel_condition=100.0,
        current_slope=0.0,
    )
    assert reading.instantaneous == pytest.approx(0.0)


def test_stress_is_clamped():
    homeostat = Homeostat()
    reading = homeostat.update(
        delta_battery=100.0,
        target_speed=1.0,
        current_speed=0.0,
        hull_condition=0.0,
        wheel_condition=0.0,
        current_slope=90.0,
    )
    assert 0.0 <= reading.smoothed <= 100.0
    assert reading.critical is True


def test_condition_terms_are_non_negative():
    homeostat = Homeostat()
    reading = homeostat.update(
        delta_battery=0.0,
        target_speed=1.0,
        current_speed=1.0,
        hull_condition=60.0,
        wheel_condition=40.0,
        current_slope=0.0,
    )
    assert reading.components["hull"] > 0
    assert reading.components["wheel"] > 0


def test_non_finite_inputs_are_safe():
    homeostat = Homeostat()
    reading = homeostat.update(
        delta_battery=float("nan"),
        target_speed=float("inf"),
        current_speed=float("nan"),
        hull_condition=float("nan"),
        wheel_condition=float("inf"),
        current_slope=float("nan"),
    )
    assert reading.smoothed == reading.smoothed  # not NaN
