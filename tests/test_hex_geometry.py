"""Hex geometry regression tests."""

from __future__ import annotations

import mesa
import pytest

from src.model.types import hex_distance, hex_to_rgb, rgb_distance


def test_hex_distance_matches_mesa_neighbours():
    grid = mesa.space.HexMultiGrid(9, 9, torus=False)
    for x in range(9):
        for y in range(9):
            for neighbour in grid.get_neighborhood(
                (x, y), include_center=False, radius=1
            ):
                assert hex_distance((x, y), neighbour) == 1


def test_hex_distance_radius_three():
    grid = mesa.space.HexMultiGrid(30, 30, torus=False)
    position = (10, 10)
    for neighbour in grid.get_neighborhood(
        position, include_center=False, radius=3
    ):
        assert hex_distance(position, neighbour) <= 3


def test_interior_hex_degree_is_six():
    grid = mesa.space.HexMultiGrid(10, 10, torus=False)
    assert len(grid.get_neighborhood((5, 5))) == 6
    assert len(grid.get_neighborhood((0, 0))) == 3


def test_rgb_helpers():
    assert hex_to_rgb("#d2b48c") == (210, 180, 140)
    assert hex_to_rgb("#fff") == (255, 255, 255)
    assert rgb_distance((0, 0, 0), (3, 4, 0)) == pytest.approx(5.0)
