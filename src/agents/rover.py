import mesa
from src.environment.terrain import TerrainPatch, Boulders

class Pioneer3DXAgent(mesa.Agent):
    """Model łazika poruszającego się po siatce heksagonalnej."""
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        # Parametry witalne i homeostat
        self.battery = 100.0
        self.wheel_condition = 100.0
        self.stress_level = 0.0

        # Sensory i ruch
        self.base_speed = 1.0
        self.current_speed = 1.0
        self.vision_range = 5
        self.gyro_alarm = False
        self.is_overturned = False

    def step(self):
        if self.is_overturned or self.battery <= 0 or self.wheel_condition <= 0:
            return

        self.move()
        self.stress_level = max(0.0, self.stress_level - 1.0)

    def move(self):
        self.current_speed = self.base_speed
        self.vision_range = 5
        self.gyro_alarm = False

        possible_steps = self.model.grid.get_neighborhood(self.pos, moore=True, include_center=False)

        # Wykrywanie LIDARem (omijanie Boulders)
        safe_steps = []
        for step in possible_steps:
            cell_agents = self.model.grid.get_cell_list_contents([step])
            terrain = next((a for a in cell_agents if isinstance(a, TerrainPatch)), None)

            if terrain and not isinstance(terrain, Boulders):
                safe_steps.append(step)

        if safe_steps:
            new_position = self.random.choice(safe_steps)
            self.model.grid.move_agent(self, new_position)

            # APLIKACJA EFEKTU ŚRODOWISKA
            cell_agents = self.model.grid.get_cell_list_contents([new_position])
            terrain = next((a for a in cell_agents if isinstance(a, TerrainPatch)), None)
            if terrain:
                terrain.apply_effect(self)