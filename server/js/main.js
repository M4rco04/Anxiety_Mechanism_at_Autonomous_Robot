/**
 * Browser application bootstrap for the terrain + live rover viewer.
 */
import { TerrainScene } from "./scene/TerrainScene.js";
import { SimulationClient } from "./simulation/SimulationClient.js";

/**
 * Loads terrain JSON from the Python server.
 *
 * @returns {Promise<object>} Terrain payload.
 */
async function loadTerrain() {
  const response = await fetch("/api/terrain");
  if (!response.ok) {
    throw new Error(`Terrain request failed with status ${response.status}`);
  }
  return response.json();
}

/**
 * Coordinates terrain loading, scene startup and live simulation.
 */
class TerrainApplication {
  constructor() {
    this.container = document.querySelector("#scene-container");
    this.status = document.querySelector("#status");
  }

  async start() {
    try {
      const terrain = await loadTerrain();
      const scene = new TerrainScene(this.container, terrain);
      await scene.start();
      this.scene = scene;
      this.simulation = new SimulationClient(scene);
      await this.simulation.start();
      this.status.textContent = `${terrain.width} × ${terrain.height} grid · ${terrain.cells.length} cells · live rover mission`;
      console.log("Generated terrain:", terrain);
    } catch (error) {
      this.status.textContent = "Unable to load terrain";
      console.error("Could not load terrain:", error);
    }
  }
}

new TerrainApplication().start();
