import mesa
from src.environment.generator import MarsMapGenerator
from src.agents.rover import Pioneer3DXAgent

class MarsSimulation(mesa.Model):
    """Główny model łączący środowisko 3D(Hex) oraz łaziki."""
    def __init__(self, width=50, height=50, num_rovers=3):
        super().__init__()
        self.num_rovers = num_rovers
        self.step_count = 0

        # 1. Siatka Heksagonalna (MultiGrid: pozwala trzymać teren i łazik na tym samym polu)
        self.grid = mesa.space.MultiGrid(width, height, torus=False)
        self.schedule = mesa.time.RandomActivation(self)

        # 2. Generacja Mapy i Topografii
        generator = MarsMapGenerator(width, height)
        elevation_map, slope_map = generator.generate_topography()
        terrain_layout = generator.assign_terrain_classes(self, elevation_map, slope_map)

        # Wypełnianie Gridu terenem (Strefy)
        for pos, patch in terrain_layout:
            self.grid.place_agent(patch, pos)

        # 3. Dodawanie łazików (Rovers)
        occupied = set()
        for i in range(self.num_rovers):
            rover = Pioneer3DXAgent(i, self)
            self.schedule.add(rover)

            # Losujemy wolne pole (każde pole zajmuje już TerrainPatch - Mesa
            # dopuszcza wielu agentów tylko w Grid, nie w HexGrid).
            for _ in range(1000):
                pos = (
                    self.random.randrange(self.grid.width),
                    self.random.randrange(self.grid.height),
                )
                if pos not in occupied:
                    occupied.add(pos)
                    self.grid.place_agent(rover, pos)
                    break

    def step(self):
        """Krok symulacji - wywoływane w głównej pętli"""
        self.step_count += 1
        self.schedule.step()