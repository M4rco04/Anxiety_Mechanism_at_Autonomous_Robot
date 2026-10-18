import math
import random
import numpy as np
from perlin_noise import PerlinNoise

from src.environment.terrain import (
    SafeRegolith, Boulders, LooseSand,
    Ventifacts, SteepSlope, DeepShadow, DustStorm
)

class MarsMapGenerator:
    """Odpowiada za proceduralne rozmieszczenie stref heksagonalnych na podstawie szumu."""
    def __init__(self, width, height, seed=None):
        self.width = width
        self.height = height
        self.seed = seed if seed else random.randint(1, 100000)

        # WARSTWY SZUMU PERLINA
        self.noise1 = PerlinNoise(octaves=3, seed=self.seed)      # Makro-rzeźba (góry/doliny/cienie)
        self.noise2 = PerlinNoise(octaves=8, seed=self.seed + 1)  # Mikro-struktury (wydmy piaskowe)

        # NOWE WARSTWY:
        self.noise3 = PerlinNoise(octaves=4, seed=self.seed + 2)  # Burze pyłowe (duże, zbite chmury)
        self.noise4 = PerlinNoise(octaves=12, seed=self.seed + 3) # Ostre skały (gęste skupiska ~4x4)

    def generate_topography(self):
        elevation_map = np.zeros((self.width, self.height))
        for x in range(self.width):
            for y in range(self.height):
                val = self.noise1([x / self.width, y / self.height])
                elevation_map[x][y] = val * 2.0

        slope_map = np.zeros((self.width, self.height))
        for x in range(self.width):
            for y in range(self.height):
                current_z = elevation_map[x][y]
                max_diff = 0
                neighbors = [(x-1, y), (x+1, y), (x, y-1), (x, y+1), (x-1, y-1), (x+1, y-1)]
                for nx, ny in neighbors:
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        diff = abs(current_z - elevation_map[nx][ny])
                        if diff > max_diff:
                            max_diff = diff

                slope_deg = math.degrees(math.atan(max_diff))
                slope_map[x][y] = slope_deg * 2.5

        return elevation_map, slope_map

    def assign_terrain_classes(self, model, elevation_map, slope_map):
        terrain_agents = []
        uid_counter = 10000

        for x in range(self.width):
            for y in range(self.height):
                z = elevation_map[x][y]
                slope = slope_map[x][y]

                # Obliczanie dodatkowych warstw szumu
                sand_noise = self.noise2([x / self.width, y / self.height])
                dust_noise = self.noise3([x / self.width, y / self.height])
                rock_noise = self.noise4([x / self.width, y / self.height])

                # KLASYFIKATOR TERENU
                if slope > 30.0:
                    patch = SteepSlope(uid_counter, model, z, slope)
                elif z > 0.6:
                    patch = Boulders(uid_counter, model, z, slope)
                elif z < -0.4:
                    patch = DeepShadow(uid_counter, model, z, slope)
                elif dust_noise > 0.25:
                    # Szum > 0.25 tworzy zbite chmury. Przesłania inne tereny na płaskim.
                    patch = DustStorm(uid_counter, model, z, slope)
                elif rock_noise > 0.2 and slope < 15.0:
                    # Szum na 12 oktawach > 0.2 stworzy gęste klastry wielkości 3-5 heksagonów.
                    # Zwiększyliśmy ilość względem starego kodu i wyrzuciliśmy random().
                    patch = Ventifacts(uid_counter, model, z, slope)
                elif sand_noise > 0.2:
                    patch = LooseSand(uid_counter, model, z, slope)
                else:
                    patch = SafeRegolith(uid_counter, model, z, slope)

                terrain_agents.append(((x,y), patch))
                uid_counter += 1

        return terrain_agents