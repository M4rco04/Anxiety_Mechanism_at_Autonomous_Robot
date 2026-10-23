/**
 * Displays terrain information for the grid cell under the pointer.
 */

const TERRAIN_DESCRIPTIONS = {
  SafeRegolith: {
    name: "Safe regolith",
    description: "Hard, stable ground (no risk).",
  },
  Boulders: {
    name: "Large boulders",
    description: "Physical obstacles that completely block movement (detected by LIDAR).",
  },
  LooseSand: {
    name: "Loose sand",
    description: "Causes wheel slip, speed reduction, and a spike in motor power consumption.",
  },
  Ventifacts: {
    name: "Sharp rocks (Ventifacts)",
    description: "Damage the robot's wheels; invisible to the LIDAR sensor.",
  },
  SteepSlope: {
    name: "Steep crater slopes",
    description: "Pose a risk of overturning the rover.",
  },
  DeepShadow: {
    name: "Deep shadows",
    description: "Accelerate battery discharge.",
  },
  DustStorm: {
    name: "Dust storms",
    description: "Temporarily limit RGB camera visibility.",
  },
};

/**
 * Owns the tooltip DOM element and its visibility state.
 */
export class TerrainTooltip {
  /**
   * @param {HTMLElement} parent Element to which the tooltip is appended.
   */
  constructor(parent) {
    this.element = document.createElement("aside");
    this.element.className = "terrain-tooltip";
    this.element.setAttribute("role", "tooltip");
    parent.appendChild(this.element);
    this.hide();
  }

  /**
   * Shows terrain information at a screen position.
   *
   * @param {string} type Terrain class name.
   * @param {number} x Pointer viewport X coordinate.
   * @param {number} y Pointer viewport Y coordinate.
   */
  show(type, x, y) {
    const terrain = TERRAIN_DESCRIPTIONS[type];
    if (!terrain) {
      this.hide();
      return;
    }

    this.element.innerHTML = `<strong>${terrain.name}</strong><span>${terrain.description}</span>`;
    this.element.style.left = `${x + 16}px`;
    this.element.style.top = `${y + 16}px`;
    this.element.classList.add("terrain-tooltip-visible");
  }

  /**
   * Hides the tooltip.
   */
  hide() {
    this.element.classList.remove("terrain-tooltip-visible");
  }
}
