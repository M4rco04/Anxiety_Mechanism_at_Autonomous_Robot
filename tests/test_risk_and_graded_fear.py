"""Speed-independent terrain, bounded dust vision, leaky chronic alarm,
graded fear and the risk-sensitive route cost."""

from __future__ import annotations

from dataclasses import replace

import pytest

from config.config import HomeostatConfig
from src.agents.homeostat import HomeostatReading
from src.environment.terrain import DustStorm, LooseSand, SteepSlope, Ventifacts
from src.navigation.costs import mean_cost, risk_cost, stress_aversion
from src.navigation.registry import create_strategy
from src.navigation.types import TerrainObservation
from tests.conftest import add_rover, make_model


def _model(seed: int = 7, **config):
    return make_model(width=5, height=5, num_rovers=0, seed=seed, **config)


# ----------------------------------------------------------------------
# Terrain effects
# ----------------------------------------------------------------------
@pytest.mark.parametrize("terrain_class", [LooseSand, Ventifacts, SteepSlope])
def test_terrain_effect_does_not_depend_on_speed(terrain_class):
    results = []
    for speed in (0.3, 1.0, 2.0):
        model = _model(seed=11)
        rover = add_rover(model, (0, 0))
        rover.current_speed = speed
        patch = terrain_class(1, model, slope=33.0)
        patch.apply_effect(rover)
        results.append((rover.battery, rover.wheel_condition, rover.hull_condition))
    assert results[0] == pytest.approx(results[1])
    assert results[2] == pytest.approx(results[1])


def test_dust_storm_never_improves_vision():
    model = _model(seed=5)
    rover = add_rover(model, (0, 0))
    storm = DustStorm(1, model)
    seen = []
    for exposure in range(1, 8):
        for _ in range(200):
            rover.dust_exposure_time = exposure
            storm.apply_effect(rover)
            seen.append(rover.vision_range)
            assert 0 <= rover.vision_range <= rover.base_vision_range
    # Long exposure makes visibility worse on average.
    assert sum(seen[:200]) > sum(seen[-200:])


# ----------------------------------------------------------------------
# Leaky chronic alarm
# ----------------------------------------------------------------------
def test_occasional_mild_losses_are_forgotten_with_leak():
    model = _model(homeostat=HomeostatConfig(chronic_retention=0.9))
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    homeostat = model.config.homeostat
    dust, other = (179, 139, 109), (210, 180, 140)
    mild = homeostat.chronic_rest + 5.0
    # One mild step every 5 steps: the sum leaks away faster than it grows.
    for _ in range(40):
        assert not rover._chronic_alarm(dust, mild)
        for _ in range(4):
            assert not rover._chronic_alarm(other, homeostat.chronic_rest)


def test_without_leak_mild_losses_add_up():
    model = _model()  # default: no leak
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    homeostat = model.config.homeostat
    alarms = [
        rover._chronic_alarm((179, 139, 109), homeostat.chronic_rest + 5.0)
        for _ in range(int(homeostat.chronic_alarm / 5.0) + 1)
    ]
    assert any(alarms)


# ----------------------------------------------------------------------
# Graded fear
# ----------------------------------------------------------------------
def _reading(stress: float) -> HomeostatReading:
    return HomeostatReading(stress, stress, {"slope": 0.0}, True, "stress")


def test_fear_intensity_follows_the_size_of_the_danger():
    model = _model()
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    homeostat = model.config.homeostat
    at_threshold = rover._acute_intensity(_reading(homeostat.s_crit))
    rocks = rover._acute_intensity(_reading(homeostat.s_crit + 18.0))
    overturn = rover._acute_intensity(_reading(300.0))
    assert at_threshold == pytest.approx(homeostat.acute_min_intensity)
    assert at_threshold < rocks < overturn == pytest.approx(1.0)


def test_ungraded_fear_is_all_or_nothing():
    model = _model(homeostat=HomeostatConfig(graded_fear=False))
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    assert rover._acute_intensity(_reading(41.0)) == 1.0


def test_repeated_imprints_strengthen_a_fear():
    model = _model()
    rover = add_rover(model, (0, 0), navigation_mode="emotional")
    signature = (179, 139, 109)
    rover._imprint(signature, 0.35)
    first = rover.fear_intensity(signature)
    rover._imprint(signature, 0.35)
    assert first == pytest.approx(0.35)
    assert rover.fear_intensity(signature) == pytest.approx(0.7)


# ----------------------------------------------------------------------
# Risk-sensitive route cost
# ----------------------------------------------------------------------
def _cell(cost: float, std: float) -> TerrainObservation:
    return TerrainObservation(
        position=(0, 0), terrain_type="X", traversable=True, movement_cost=cost,
        damage_risk=0.0, slope_risk=0.0, rgb_signature=None, elevation=0.0,
        slope=0.0, occupied_by_rover=False, visited=False, movement_cost_std=std,
    )


def test_risk_cost_keeps_reference_and_penalises_spread():
    reference, sand = _cell(1.0, 0.17), _cell(2.0, 0.71)
    cost = risk_cost(1.0, reference_std=0.17)
    assert cost(reference) == pytest.approx(1.0)
    assert cost(sand) > mean_cost(sand)
    # Same mean, larger spread: more expensive.
    assert cost(_cell(2.0, 0.9)) > cost(_cell(2.0, 0.1))
    assert risk_cost(0.0) is mean_cost


def test_stress_raises_risk_aversion_of_anxious_rover_only():
    assert stress_aversion(0.5, 1.5, 0.0, 40.0) == pytest.approx(0.5)
    assert stress_aversion(0.5, 1.5, 20.0, 40.0) == pytest.approx(1.25)
    assert stress_aversion(0.5, 1.5, 400.0, 40.0) == pytest.approx(2.0)

    model = _model()
    rover = add_rover(model, (0, 0))
    config = model.config
    rover.stress_level = config.homeostat.s_crit
    emotional = create_strategy("emotional", config, 1)
    online = create_strategy("online", config, 1)
    fuzzy = create_strategy("fuzzy", config, 1)
    assert emotional._risk_aversion(rover) == pytest.approx(
        config.risk_aversion + config.stress_risk_aversion
    )
    assert online._risk_aversion(rover) == pytest.approx(config.risk_aversion)
    assert fuzzy._risk_aversion(rover) == pytest.approx(config.risk_aversion)


def test_config_round_trip_keeps_cost_spread():
    from config.config import SimulationConfig

    config = replace(SimulationConfig(), risk_aversion=0.8)
    loaded = SimulationConfig.from_dict(config.to_dict())
    assert loaded.terrain_cost_std == config.terrain_cost_std
    assert loaded.risk_aversion == 0.8
    assert loaded.homeostat.chronic_retention == config.homeostat.chronic_retention


# ----------------------------------------------------------------------
# Retreat between two feared terrains
# ----------------------------------------------------------------------
def test_retreat_never_goes_onto_another_strongly_feared_terrain():
    from src.environment.terrain import TERRAIN_COLORS
    from src.model.types import hex_to_rgb
    from src.navigation.observation import build_observation
    from src.navigation.strategies import _retreat_decision
    from tests.conftest import layout

    centre = (5, 5)
    model = make_model(
        width=11, height=11, num_rovers=0, seed=3, navigation_mode="emotional",
        rgb_fov_deg=360.0, rgb_noise_sigma=0.0, look_before_step=False,
        terrain_layout=None,
    )
    neighbours = model.grid.get_neighborhood(centre, include_center=False, radius=1)
    overrides = {centre: "LooseSand"}
    overrides.update({cell: "SteepSlope" for cell in neighbours[1:]})
    overrides[neighbours[0]] = "SafeRegolith"
    model = make_model(
        width=11, height=11, num_rovers=0, seed=3, navigation_mode="emotional",
        rgb_fov_deg=360.0, rgb_noise_sigma=0.0, look_before_step=False,
        terrain_layout=layout(11, 11, overrides=overrides),
    )
    model.running = True
    rover = add_rover(
        model, centre, navigation_mode="emotional",
        strategy=create_strategy("emotional", model.config, 3),
    )
    # The rover came from a slope, then got stuck in this sand; earlier it
    # had also driven over the safe neighbour.
    rover.path = [neighbours[1], centre]
    rover.visited.update({neighbours[0], neighbours[1], centre})
    rover.learn_fear(hex_to_rgb(TERRAIN_COLORS["SteepSlope"]), intensity=0.9)
    rover.learn_fear(hex_to_rgb(TERRAIN_COLORS["LooseSand"]), intensity=1.0)

    decision = rover.strategy.choose_next(rover, build_observation(rover))
    assert decision.reason.startswith("retreating")
    # Not back along the path onto the (slightly less) feared slope.
    assert decision.next_position == neighbours[0]

    # Without the safe neighbour there is no retreat to a neighbour at all.
    rover.known_terrain.pop(neighbours[0])
    strategy = rover.strategy
    cell_cost = strategy._cell_cost(rover, None)
    actions = [cell for cell in neighbours[1:]]
    assert _retreat_decision(
        rover, strategy._get_board(rover), actions, cell_cost, strategy._retreat_level()
    ) is None


def test_retreat_only_onto_cells_the_rover_has_driven_on():
    from src.navigation.strategies import _retreat_decision
    from tests.conftest import layout

    centre = (5, 5)
    model = make_model(
        width=11, height=11, num_rovers=0, seed=3, navigation_mode="emotional",
        rgb_fov_deg=360.0, rgb_noise_sigma=0.0, look_before_step=False,
        terrain_layout=layout(11, 11, overrides={centre: "LooseSand"}),
    )
    rover = add_rover(
        model, centre, navigation_mode="emotional",
        strategy=create_strategy("emotional", model.config, 3),
    )
    from src.environment.terrain import TERRAIN_COLORS
    from src.model.types import hex_to_rgb
    from src.navigation.observation import build_observation

    rover.learn_fear(hex_to_rgb(TERRAIN_COLORS["LooseSand"]), intensity=1.0)
    build_observation(rover)  # the cameras see the safe ground around
    strategy = rover.strategy
    board = strategy._get_board(rover)
    neighbours = model.grid.get_neighborhood(centre, include_center=False, radius=1)
    cell_cost = strategy._cell_cost(rover, None)
    level = strategy._retreat_level()
    # Seen but never driven on: no retreat.
    assert _retreat_decision(rover, board, neighbours, cell_cost, level) is None
    # Driven on: that is the way back.
    rover.visited.add(neighbours[2])
    decision = _retreat_decision(rover, board, neighbours, cell_cost, level)
    assert decision is not None and decision.next_position == neighbours[2]
