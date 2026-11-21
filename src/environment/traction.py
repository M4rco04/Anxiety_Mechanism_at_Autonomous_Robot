"""Wheel-ground traction of a skid-steered Pioneer P3-AT.

Source: Wang T., Wu Y., Liang J., Han C., Chen J., Zhao Q. (2015). *Analysis
and Experimental Kinematics of a Skid-Steering Wheeled Robot Based on a Laser
Scanner Sensor*. Sensors 15, 9681-9702 (``sensors-15-09681.pdf``).

What is taken from the paper:

* Table 1 - P3-AT parameters: mass 31 kg, track width B = 0.40 m, tyre
  radius 0.11 m, wheel width b = 0.05 m, shear deformation modulus
  K = 0.00054 m, rolling resistance coefficient f_r = 0.0371, friction
  coefficients mu = 0.4437 and 0.3093 (left and right wheels).
* Eq. (17) - shear stress vs shear displacement (Janosi-Hanamoto):
  tau = p * mu * (1 - exp(-j / K)). Over a contact patch of length l a wheel
  with slip ratio i has j = i * x (x = 0..l), so the mean traction ratio is

      F / N = mu * (1 - K / (i l) * (1 - exp(-i l / K)))

* Eq. (45) - ICR coefficient chi(a) = 1 + 0.4728 / (1 + 0.0538 |a|); turning
  in place (a = 0) gives chi = 1.4728: the treads skid as if the robot were
  1.47 times wider than it is, so turning costs friction work.
* Section 1 - skid steering "tends to be energy inefficient" and "the tires
  tend to wear out faster".

What is *not* in the paper (assumptions, see README "Terrain"):

* The patch length l is not given; we use the wheel width b = 0.05 m.
* The experiments were on a tiled lab floor. We use its coefficients for
  firm ground (regolith); the paper names loose soil as future work, so
  loose sand keeps its own slip model.
* The heading of the rover relative to the fall line of a cell is random
  (uniform), and mu is drawn between the two measured values per entry.
* An overturn on a crater wall happens when the side force exceeds lateral
  grip (tan(slope) * |sin(heading)| > mu): the rover slides sideways down
  the wall and rolls. The paper gives the grip, not the tip-over geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Wang et al. (2015), Table 1 (Pioneer P3-AT on the lab surface).
P3AT_MASS_KG = 31.0
P3AT_TRACK_M = 0.40
P3AT_LENGTH_M = 0.31
P3AT_C_M = 0.24
P3AT_TYRE_RADIUS_M = 0.11
P3AT_WHEEL_WIDTH_M = 0.05
SHEAR_MODULUS_K_M = 0.00054
ROLLING_RESISTANCE = 0.0371
FRICTION_MU_MAX = 0.4437
FRICTION_MU_MIN = 0.3093
FRICTION_MU_MEAN = 0.5 * (FRICTION_MU_MAX + FRICTION_MU_MIN)
# Eq. (45) at a = 0 (turning in place).
ICR_CHI_SPIN = 1.0 + 0.4728
# Assumption: contact patch length = wheel width.
PATCH_LENGTH_M = P3AT_WHEEL_WIDTH_M


def icr_coefficient(curvature: float) -> float:
    """Eq. (45): ICR coefficient chi of the P3-AT for path curvature ``a``."""

    return 1.0 + 0.4728 / (1.0 + 0.0538 * abs(curvature))


def traction_ratio(
    slip: float,
    mu: float = FRICTION_MU_MEAN,
    k: float = SHEAR_MODULUS_K_M,
    patch: float = PATCH_LENGTH_M,
) -> float:
    """Mean traction / normal load of a wheel at slip ratio ``slip`` (Eq. 17)."""

    if slip <= 0.0:
        return 0.0
    ratio = slip * patch / k
    return mu * (1.0 - (1.0 - math.exp(-ratio)) / ratio)


def slip_for_demand(
    demand: float,
    mu: float = FRICTION_MU_MEAN,
    k: float = SHEAR_MODULUS_K_M,
    patch: float = PATCH_LENGTH_M,
) -> float:
    """Slip ratio at which the wheels deliver ``demand`` (traction / load).

    1.0 when the demand exceeds the grip: the wheels spin (or skid) and the
    rover does not hold its line.
    """

    if demand <= 0.0:
        return 0.0
    if demand >= traction_ratio(1.0, mu, k, patch):
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(50):
        mid = 0.5 * (low + high)
        if traction_ratio(mid, mu, k, patch) < demand:
            low = mid
        else:
            high = mid
    return high


def climb_limit_deg(mu: float = FRICTION_MU_MEAN, rolling: float = ROLLING_RESISTANCE) -> float:
    """Steepest slope the rover can drive straight up: sin a + f_r cos a = F_max/N."""

    grip = traction_ratio(1.0, mu)
    # sin a + f cos a = g  ->  sqrt(1 + f^2) sin(a + atan f) = g
    value = grip / math.sqrt(1.0 + rolling**2)
    return math.degrees(math.asin(min(1.0, value)) - math.atan(rolling))


def turn_energy_factor(angle_rad: float, cell_m: float) -> float:
    """Energy of an in-place turn in units of driving one flat cell.

    Turning in place, each side's wheels skid over chi * (B/2) * angle
    against friction mu * W/2; driving a flat cell of length d costs
    f_r * W * d. The weight W cancels.
    """

    if angle_rad <= 0.0 or cell_m <= 0.0:
        return 0.0
    work_turn = FRICTION_MU_MEAN * ICR_CHI_SPIN * (P3AT_TRACK_M / 2.0) * angle_rad
    work_cell = ROLLING_RESISTANCE * cell_m
    return work_turn / work_cell


@dataclass(frozen=True)
class DriveOutcome:
    """Effect of driving one cell of a given slope."""

    slip: float
    energy_factor: float  # tractive work in units of one flat cell
    lateral_slide: bool
    heading_rad: float
    mu: float


def drive_effect(slope_deg: float, rng: np.random.Generator) -> DriveOutcome:
    """Traction on a cell with slope ``slope_deg`` for a random heading."""

    heading = float(rng.uniform(0.0, math.pi))  # 0 = straight uphill
    mu = float(rng.uniform(FRICTION_MU_MIN, FRICTION_MU_MAX))
    alpha = math.radians(max(0.0, min(89.0, slope_deg)))
    cos_a, sin_a, tan_a = math.cos(alpha), math.sin(alpha), math.tan(alpha)

    # Force along the track per unit weight: rolling resistance plus the
    # downhill component of gravity (negative = the motors must brake).
    along = ROLLING_RESISTANCE * cos_a + sin_a * math.cos(heading)
    demand = abs(along) / cos_a
    slip = slip_for_demand(demand, mu)
    grip = traction_ratio(1.0, mu) * cos_a
    # Non-regenerative motors: braking costs current like driving.
    energy = min(abs(along), grip) / ROLLING_RESISTANCE
    lateral = tan_a * abs(math.sin(heading)) > mu
    return DriveOutcome(
        slip=slip,
        energy_factor=energy,
        lateral_slide=lateral,
        heading_rad=heading,
        mu=mu,
    )


__all__ = [
    "FRICTION_MU_MAX",
    "FRICTION_MU_MEAN",
    "FRICTION_MU_MIN",
    "ICR_CHI_SPIN",
    "ROLLING_RESISTANCE",
    "SHEAR_MODULUS_K_M",
    "DriveOutcome",
    "climb_limit_deg",
    "drive_effect",
    "icr_coefficient",
    "slip_for_demand",
    "traction_ratio",
    "turn_energy_factor",
]
