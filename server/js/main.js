/**
 * Browser application bootstrap for the terrain viewer.
 */
import { TerrainScene } from "./scene/TerrainScene.js";

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
 * Coordinates terrain loading and scene startup.
 */
class TerrainApplication {
  /**
   * Finds the page elements used by the application.
   */
  constructor() {
    this.container = document.querySelector("#scene-container");
    this.status = document.querySelector("#status");
  }

  /**
   * Starts the browser application.
   *
   * @returns {Promise<void>}
   */
  async start() {
    try {
      const terrain = await loadTerrain();
      await new TerrainScene(this.container, terrain).start();
      this.status.textContent = `${terrain.width} × ${terrain.height} grid · ${terrain.cells.length} cells`;
      console.log("Generated terrain:", terrain);
    } catch (error) {
      this.status.textContent = "Unable to load terrain";
      console.error("Could not load terrain:", error);
    }
  }
}

new TerrainApplication().start();
