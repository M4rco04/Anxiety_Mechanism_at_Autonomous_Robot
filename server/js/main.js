import { createTerrainScene } from "./scene.js";

const container = document.querySelector("#scene-container");
const status = document.querySelector("#status");

async function loadTerrain() {
  const response = await fetch("/api/terrain");
  if (!response.ok) {
    throw new Error(`Terrain request failed with status ${response.status}`);
  }

  return response.json();
}

try {
  const terrain = await loadTerrain();
  createTerrainScene(container, terrain);
  status.textContent = `${terrain.width} × ${terrain.height} grid · ${terrain.cells.length} cells`;
  console.log("Generated terrain:", terrain);
} catch (error) {
  status.textContent = "Unable to load terrain";
  console.error("Could not load terrain:", error);
}
