"""Procedural Mars terrain generation using Perlin noise.

The layout algorithm and thresholds are frozen as Antoni's completed board
work.  This module only makes the random source injectable so experiments can
be reproduced from a seed.
"""

from __future__ import annotations

import math
import random

import numpy as np
from perlin_noise import PerlinNoise

from src.environment.terrain import (
    Boulders,
    DeepShadow,
    DustStorm,
    LooseSand,
    SafeRegolith,
    SteepSlope,
    TerrainPatch,
    Ventifacts,
)
from src.model.types import Position


class MarsMapGenerator:
    """Procedurally place hexagonal terrain zones using Perlin noise."""

    def __init__(self, width: int, height: int, seed: int | None = None) -> None:
        self.width = width
        self.height = height
        self.seed = seed if seed is not None else random.SystemRandom().randint(1, 1_000_000)
        self.rng = random.Random(self.seed)

        # Noise layers retain the original board-generation contract.
        self.noise1 = PerlinNoise(octaves=3, seed=self.seed)
        self.noise2 = PerlinNoise(octaves=8, seed=self.seed + 1)
        self.noise3 = PerlinNoise(octaves=4, seed=self.seed + 2)
        self.noise4 = PerlinNoise(octaves=12, seed=self.seed + 3)

    def generate_topography(self) -> tuple[np.ndarray, np.ndarray]:
        elevation_map = np.zeros((self.width, self.height))
        for x in range(self.width):
            for y in range(self.height):
                elevation_map[x][y] = self.noise1(
                    [x / self.width, y / self.height]
                ) * 2.0

        slope_map = np.zeros((self.width, self.height))
        for x in range(self.width):
            for y in range(self.height):
                current_z = elevation_map[x][y]
                max_diff = 0.0
                neighbors = [
                    (x - 1, y),
                    (x + 1, y),
                    (x, y - 1),
                    (x, y + 1),
                    (x - 1, y - 1),
                    (x + 1, y - 1),
                ]
                for nx, ny in neighbors:
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        diff = abs(current_z - elevation_map[nx][ny])
                        max_diff = max(max_diff, diff)
                slope_map[x][y] = math.degrees(math.atan(max_diff)) * 2.5

        return elevation_map, slope_map

    def assign_terrain_classes(
        self,
        model,
        elevation_map: np.ndarray,
        slope_map: np.ndarray,
    ) -> list[tuple[Position, TerrainPatch]]:
        terrain_agents: list[tuple[Position, TerrainPatch]] = []
        uid_counter = 10000

        for x in range(self.width):
            for y in range(self.height):
                z = float(elevation_map[x][y])
                slope = float(slope_map[x][y])

                sand_noise = self.noise2([x / self.width, y / self.height])
                dust_noise = self.noise3([x / self.width, y / self.height])
                rock_noise = self.noise4([x / self.width, y / self.height])

                if slope > 30.0:
                    patch: TerrainPatch = SteepSlope(uid_counter, model, z, slope)
                elif z > 0.6:
                    boulder_slope = min(
                        slope + self.rng.uniform(20.0, 45.0), 90.0
                    )
                    patch = Boulders(uid_counter, model, z, boulder_slope)
                elif z < -0.4:
                    patch = DeepShadow(uid_counter, model, z, slope)
                elif dust_noise > 0.25:
                    patch = DustStorm(uid_counter, model, z, slope)
                elif rock_noise > 0.2 and slope < 15.0:
                    patch = Ventifacts(uid_counter, model, z, slope)
                elif sand_noise > 0.2:
                    patch = LooseSand(uid_counter, model, z, slope)
                else:
                    patch = SafeRegolith(uid_counter, model, z, slope)

                terrain_agents.append(((x, y), patch))
                uid_counter += 1

        return terrain_agents


__all__ = ["MarsMapGenerator"]
