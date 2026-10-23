/**
 * Builds irregular Boulder and Ventifact groups.
 */
import * as THREE from "three";
import { CellRandom } from "../core/CellRandom.js";

const ROCK_COUNT = { Boulders: 3, Ventifacts: 7 };
const EDGE_ROCK_COUNT = { Boulders: 2, Ventifacts: 0 };

/**
 * Creates rock clusters from loaded GLB source models.
 */
export class RockCluster {
  /**
   * @param {{models: object}} assets Loaded rock models.
   */
  constructor(assets) {
    this.assets = assets;
  }

  /**
   * @param {{x: number, y: number, type: string}} cell Rock terrain cell.
   * @returns {THREE.Group} Cluster positioned relative to its cell.
   */
  create(cell) {
    const cluster = new THREE.Group();
    const random = new CellRandom(cell);
    for (let index = 0; index < ROCK_COUNT[cell.type]; index += 1) {
      cluster.add(this.createInstance(cell.type, random, false));
    }
    for (let index = 0; index < EDGE_ROCK_COUNT[cell.type]; index += 1) {
      cluster.add(this.createInstance(cell.type, random, true));
    }
    return cluster;
  }

  /**
   * @param {string} type Rock terrain type.
   * @param {CellRandom} random Cell random generator.
   * @param {boolean} edgePosition Whether to use an edge position.
   * @returns {THREE.Object3D} Bounded randomized model instance.
   */
  createInstance(type, random, edgePosition) {
    const instance = this.assets.models[type].clone(true);
    const maximumHeight = type === "Ventifacts" ? 0.22 : 0.9;
    const maximumFootprint = type === "Ventifacts" ? 0.72 : 0.78;
    instance.rotation.set((random.next() - 0.5) * 0.16, random.next() * Math.PI * 2, (random.next() - 0.5) * 0.16);
    const rotatedSize = new THREE.Box3().setFromObject(instance).getSize(new THREE.Vector3());
    const limit = Math.min(
      maximumFootprint / Math.max(Math.hypot(rotatedSize.x, rotatedSize.z), 0.001),
      maximumHeight / Math.max(rotatedSize.y, 0.001),
    ) * (0.78 + random.next() * 0.18);
    const width = type === "Ventifacts" ? 1.05 + random.next() * 0.3 : 0.7 + random.next() * 0.28;
    const height = type === "Ventifacts" ? 0.35 + random.next() * 0.25 : 0.8 + random.next() * 0.25;
    const depth = type === "Ventifacts" ? 1 + random.next() * 0.3 : 0.62 + random.next() * 0.34;
    instance.scale.set(limit * width, limit * height, limit * depth);
    const bounds = new THREE.Box3().setFromObject(instance);
    const size = bounds.getSize(new THREE.Vector3());
    instance.scale.multiplyScalar(Math.min(1, maximumFootprint / Math.max(Math.hypot(size.x, size.z), 0.001), maximumHeight / Math.max(size.y, 0.001)));
    instance.position.y -= new THREE.Box3().setFromObject(instance).min.y;
    const edge = random.next() < 0.5;
    const direction = random.next() < 0.5 ? -1 : 1;
    if (edgePosition) {
      instance.position.x = edge ? direction * (0.42 + random.next() * 0.08) : (random.next() - 0.5) * 0.3;
      instance.position.z = edge ? (random.next() - 0.5) * 0.3 : direction * (0.42 + random.next() * 0.08);
    } else {
      const offset = type === "Ventifacts" ? 0.2 : 0.24;
      instance.position.x = (random.next() - 0.5) * offset;
      instance.position.z = (random.next() - 0.5) * offset;
    }
    return instance;
  }
}
