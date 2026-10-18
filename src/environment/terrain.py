import math
import mesa
import numpy as np

class TerrainPatch(mesa.Agent):
    """Bazowa klasa pola heksagonalnego z właściwościami 3D (Z, nachylenie)."""
    def __init__(self, unique_id, model, elevation=0.0, slope=0.0):
        super().__init__(unique_id, model)
        self.elevation = elevation
        self.slope = slope
        self.color = "grey"

    def apply_effect(self, rover):
        """Metoda polimorficzna nadpisywana przez konkretne typy terenu."""
        pass

#Regolit
class SafeRegolith(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#d2b48c"

    def apply_effect(self, rover):
        mean_drain = 0.1 + (0.2 * rover.current_speed)
        drain = np.random.normal(loc=mean_drain, scale=0.05)
        rover.battery -= max(0.05, drain)

#Duże głazy
class Boulders(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#4d4d4d"

    def apply_effect(self, rover):
        collision_prob = min(0.9, rover.current_speed * 0.4) 
        
        if np.random.random() < collision_prob:
            damage = np.random.normal(loc=15.0 * rover.current_speed, scale=4.0)
            rover.hull_condition -= max(0.0, damage)
            
        rover.current_speed = 0.0
        rover.battery -= np.random.normal(loc=1.5, scale=0.3)

#Sypki piasek
class LooseSand(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#e6cc80"

    def apply_effect(self, rover):
        alpha = 2.0 + rover.current_speed
        beta_param = 5.0 / max(0.1, rover.current_speed)
        slip_factor = np.random.beta(a=alpha, b=beta_param)
        
        rover.current_speed *= (1.0 - slip_factor)
        
        drain = np.random.lognormal(mean=0.5 + rover.current_speed, sigma=0.3)
        rover.battery -= drain

# Ostre skały
class Ventifacts(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#8b4513"

    def apply_effect(self, rover):
        scale_damage = 3.0 * rover.current_speed
        damage = np.random.exponential(scale=max(0.5, scale_damage))
        
        rover.wheel_condition -= max(0.0, damage)
       
        rover.current_speed *= np.random.normal(loc=0.85, scale=0.05)
        rover.battery -= np.random.normal(loc=0.8, scale=0.1)

#Strome zbocza
class SteepSlope(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#ff6666"

    def apply_effect(self, rover):
        drain = np.random.normal(loc=0.5 + math.exp(0.05 * self.slope), scale=0.3)
        rover.battery -= max(0.1, drain)
        
        steepness_factor = self.slope - 30.0 + (rover.current_speed * 4.0)
        fall_prob = 1.0 / (1.0 + math.exp(-0.25 * steepness_factor))
        
        if np.random.random() < fall_prob:
            rover.is_overturned = True
            
            hull_damage = np.random.normal(loc=35.0, scale=10.0)
            wheel_damage = np.random.normal(loc=20.0, scale=8.0)
            
            rover.hull_condition -= max(0.0, hull_damage)
            rover.wheel_condition -= max(0.0, wheel_damage)
            rover.current_speed = 0.0
        else:
            rover.gyro_alarm = self.slope > 20.0

# Głębokie cienie
class DeepShadow(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#1a1a1a"

    def apply_effect(self, rover):
        rover.shadow_exposure_time += 1
        
        base_drain = 3.5 + (0.5 * rover.shadow_exposure_time)
        
        drain = np.random.normal(loc=base_drain, scale=0.4)
        rover.battery -= max(0.0, drain)

# Burza pyłowa
class DustStorm(TerrainPatch):
    def __init__(self, unique_id, model, elevation, slope):
        super().__init__(unique_id, model, elevation, slope)
        self.color = "#b38b6d"

    def apply_effect(self, rover):
        rover.dust_exposure_time += 1
        
        current_lam = max(0.1, 2.5 - (0.4 * rover.dust_exposure_time))
        rover.vision_range = np.random.poisson(lam=current_lam)

        rover.battery -= np.random.normal(loc=1.2, scale=0.3)