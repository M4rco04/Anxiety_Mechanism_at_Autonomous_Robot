import random
import mesa

class TerrainPatch(mesa.Agent):
    """Bazowa klasa pola heksagonalnego z właściwościami 3D (Z, nachylenie)."""
    def __init__(self, unique_id, model, elevation=0.0, slope=0.0):
        super().__init__(unique_id, model)
        self.elevation = elevation
        self.slope = slope  # Nachylenie w stopniach
        self.color = "grey" # Domyślny kolor do portretowania na Canvas HTML5

    def apply_effect(self, rover):
        """Metoda polimorficzna nadpisywana przez konkretne typy terenu."""
        pass

class SafeRegolith(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#d2b48c"

    def apply_effect(self, rover):
        rover.battery -= 0.5

class Boulders(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#4d4d4d"

    def apply_effect(self, rover):
        pass

class LooseSand(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#e6cc80"

    def apply_effect(self, rover):
        rover.current_speed *= 0.5
        rover.battery -= 2.5
        rover.stress_level += 15.0

class Ventifacts(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#8b4513"

    def apply_effect(self, rover):
        rover.wheel_condition -= random.uniform(5, 15)
        rover.stress_level += 30.0
        rover.battery -= 1.0

class SteepSlope(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#ff6666"

    def apply_effect(self, rover):
        rover.gyro_alarm = True
        rover.stress_level += 25.0
        rover.battery -= 3.0

        overturn_chance = (self.slope - 30.0) / 50.0
        if random.random() < overturn_chance:
            rover.is_overturned = True

class DeepShadow(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#1a1a1a"

    def apply_effect(self, rover):
        rover.battery -= 4.0
        rover.stress_level += 5.0

class DustStorm(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#b38b6d"

    def apply_effect(self, rover):
        rover.vision_range = 1
        rover.stress_level += 10.0
        rover.battery -= 1.0