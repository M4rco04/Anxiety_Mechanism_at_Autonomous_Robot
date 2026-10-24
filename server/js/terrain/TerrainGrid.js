/**
 * Creates grid-aligned terrain cubes and the navigation grid helper.
 */
import * as THREE from "three";
import { TerrainMaterial } from "./TerrainMaterial.js";

/**
 * Terrain grid mesh factory.
 */
export class TerrainGrid {
  /**
   * @param {object} assets Loaded terrain assets.
   */
  constructor(assets) {
    this.materials = new TerrainMaterial(assets);
  }

  /**
   * @param {{x: number, y: number, type: string}} cell Terrain cell.
   * @param {number} height Cube height.
   * @returns {THREE.Mesh} Textured terrain cube.
   */
  createCube(cell, height) {
    const cube = new THREE.Mesh(
      new THREE.BoxGeometry(1, height, 1),
      this.materials.create(cell),
    );
    cube.position.set(cell.x, height / 2, cell.y);
    cube.userData.gridPosition = { x: cell.x, y: cell.y };
    cube.userData.terrain = cell;
    return cube;
  }

  /**
   * @param {number} width Grid width.
   * @param {number} height Grid height.
   * @returns {THREE.GridHelper} Visible grid helper.
   */
  createHelper(width, height) {
    const grid = new THREE.GridHelper(Math.max(width, height), Math.max(width, height), 0x8b6a52, 0x3a2d27);
    grid.position.y = -0.01;
    return grid;
  }
}
