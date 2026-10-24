/**
 * Creates terrain materials with stable per-cell texture variation.
 */
import * as THREE from "three";
import { CellRandom } from "../core/CellRandom.js";

/**
 * Material factory for terrain cubes.
 */
export class TerrainMaterial {
  /**
   * @param {{cubeTextures: object, safeRegolith: THREE.Texture}} assets Terrain assets.
   */
  constructor(assets) {
    this.assets = assets;
  }

  /**
   * @param {{x: number, y: number, type: string}} cell Terrain cell.
   * @returns {THREE.Material} Configured terrain material.
   */
  create(cell) {
    const texture = this.assets.cubeTextures[cell.type] ?? this.assets.safeRegolith;
    const material = cell.type === "DeepShadow"
      ? new THREE.MeshBasicMaterial({ map: texture })
      : new THREE.MeshStandardMaterial({ map: texture, roughness: 0.9 });
    const random = new CellRandom(cell);
    const transform = new THREE.Vector4(
      1.35 + random.next() * 0.45,
      random.next() * Math.PI * 2,
      random.next(),
      random.next(),
    );
    material.onBeforeCompile = (shader) => {
      shader.uniforms.terrainUvTransform = { value: transform };
      const shadowSample = cell.type === "DeepShadow"
        ? `
          vec4 shadowTexture = texture2D(map, terrainUv(vMapUv));
          float luminance = dot(shadowTexture.rgb, vec3(0.299, 0.587, 0.114));
          diffuseColor *= vec4(luminance * vec3(0.22, 0.27, 0.36), shadowTexture.a);
        `
        : "diffuseColor *= texture2D(map, terrainUv(vMapUv));";
      shader.fragmentShader = `
        uniform vec4 terrainUvTransform;
        vec2 terrainUv(vec2 uv) {
          float scale = terrainUvTransform.x;
          float angle = terrainUvTransform.y;
          vec2 centered = (uv - 0.5) * scale;
          centered = vec2(
            centered.x * cos(angle) - centered.y * sin(angle),
            centered.x * sin(angle) + centered.y * cos(angle)
          );
          return fract(centered + 0.5 + terrainUvTransform.zw);
        }
      ` + shader.fragmentShader;
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <map_fragment>",
        shadowSample,
      );
    };
    return material;
  }
}
