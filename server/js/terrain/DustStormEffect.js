/**
 * Builds the layered DustStorm visual effect.
 */
import * as THREE from "three";

/**
 * Creates the DustStorm overlay for a terrain cell.
 */
export class DustStormEffect {
  /**
   * @param {THREE.Texture} texture DustStorm texture.
   */
  constructor(texture) {
    this.texture = texture;
  }

  /**
   * @returns {THREE.Group} Layered cloud and particle group.
   */
  create() {
    const storm = new THREE.Group();
    const layers = [
      [-0.28, 0.22, 0.08, 0.9, 0.2, 0.2],
      [0.18, 0.38, -0.12, 1.05, 0.24, -0.45],
      [0.02, 0.62, 0.14, 0.8, 0.18, 0.65],
      [-0.12, 0.84, -0.08, 0.62, 0.14, -0.1],
    ];
    for (const [x, y, z, scale, opacity, rotation] of layers) {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: this.texture,
        transparent: true,
        opacity,
        depthWrite: false,
        color: 0xd9c2a7,
      }));
      sprite.position.set(x, y, z);
      sprite.scale.set(scale, scale * 0.72, 1);
      sprite.material.rotation = rotation;
      storm.add(sprite);
    }
    const positions = [];
    const sizes = [];
    for (let index = 0; index < 24; index += 1) {
      const angle = index * 2.39996;
      const radius = 0.12 + (index % 6) * 0.07;
      positions.push(Math.cos(angle) * radius, 0.12 + (index % 8) * 0.11, Math.sin(angle) * radius);
      sizes.push(0.08 + (index % 4) * 0.025);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("size", new THREE.Float32BufferAttribute(sizes, 1));
    storm.add(new THREE.Points(geometry, new THREE.PointsMaterial({
      map: this.texture,
      color: 0xe8d2b7,
      transparent: true,
      opacity: 0.32,
      depthWrite: false,
      size: 0.24,
      sizeAttenuation: true,
    })));
    return storm;
  }
}
