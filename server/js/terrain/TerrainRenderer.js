/**
 * Composes terrain cubes and terrain-specific overlays.
 */
import * as THREE from "three";
import { DustStormEffect } from "./DustStormEffect.js";
import { RockCluster } from "./RockCluster.js";
import { TerrainGrid } from "./TerrainGrid.js";

export class TerrainRenderer {
  constructor(assets) {
    this.assets = assets;
    this.grid = new TerrainGrid(assets);
    this.dustStorm = new DustStormEffect(assets.dustStorm);
    this.rocks = new RockCluster(assets);
    this.cubes = [];
    this.cellHeights = new Map();
  }

  /**
   * Returns the top surface height of a terrain cube.
   *
   * @param {number} x Grid x coordinate.
   * @param {number} y Grid y coordinate.
   * @returns {number} Cube top height in world units.
   */
  heightAt(x, y) {
    return this.cellHeights.get(`${x},${y}`) ?? 0.15;
  }

  /**
   * @param {{width: number, height: number, cells: Array<object>}} terrain Terrain payload.
   * @returns {THREE.Group} Centered terrain group.
   */
  create(terrain) {
    const elevations = terrain.cells.map((cell) => cell.elevation);
    const minimum = Math.min(...elevations);
    const range = Math.max(Math.max(...elevations) - minimum, 0.001);
    const group = new THREE.Group();
    for (const cell of terrain.cells) {
      const height = 0.15 + ((cell.elevation - minimum) / range) * 2.5;
      this.cellHeights.set(`${cell.x},${cell.y}`, height);
      const cube = this.grid.createCube(cell, height);
      group.add(cube);
      this.cubes.push(cube);
      if (cell.type === "DustStorm") {
        const effect = this.dustStorm.create();
        effect.position.copy(cube.position);
        effect.position.y += height / 2;
        group.add(effect);
      } else if (cell.type === "Boulders" || cell.type === "Ventifacts") {
        const cluster = this.rocks.create(cell);
        cluster.position.copy(cube.position);
        cluster.position.y += height / 2;
        group.add(cluster);
      }
    }
    group.position.set(-(terrain.width - 1) / 2, 0, -(terrain.height - 1) / 2);
    return group;
  }
}
