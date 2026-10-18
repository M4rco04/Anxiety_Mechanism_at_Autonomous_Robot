import * as THREE from "three";

const CELL_SIZE = 1;
const CELL_GAP = 0.08;
const MIN_HEIGHT = 0.15;
const HEIGHT_SCALE = 2.5;

export function createTerrainMeshes(terrain) {
  const elevations = terrain.cells.map((cell) => cell.elevation);
  const minimumElevation = Math.min(...elevations);
  const maximumElevation = Math.max(...elevations);
  const elevationRange = Math.max(maximumElevation - minimumElevation, 0.001);
  const group = new THREE.Group();

  for (const cell of terrain.cells) {
    const normalizedElevation =
      (cell.elevation - minimumElevation) / elevationRange;
    const height = MIN_HEIGHT + normalizedElevation * HEIGHT_SCALE;
    const geometry = new THREE.BoxGeometry(
      CELL_SIZE - CELL_GAP,
      height,
      CELL_SIZE - CELL_GAP,
    );
    const material = new THREE.MeshStandardMaterial({
      color: cell.color,
      roughness: 0.9,
    });
    const cube = new THREE.Mesh(geometry, material);

    // Keep integer grid coordinates available for future rover navigation.
    cube.position.set(
      cell.x - (terrain.width - 1) / 2,
      height / 2,
      cell.y - (terrain.height - 1) / 2,
    );
    cube.userData.gridPosition = { x: cell.x, y: cell.y };
    cube.userData.terrain = cell;
    group.add(cube);
  }

  return group;
}

export function createGridHelper(width, height) {
  const grid = new THREE.GridHelper(
    Math.max(width, height),
    Math.max(width, height),
    0x8b6a52,
    0x3a2d27,
  );
  grid.position.y = -0.01;
  return grid;
}
