/**
 * Loads textures and GLB models used by terrain rendering.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const TEXTURE_FILES = {
  DeepShadow: "DeepShadow.png",
  DustStorm: "DustStorm.png",
  LooseSand: "LooseSand.png",
  SafeRegolith: "SafeRegolith.png",
  SteepSlope: "SteepSlope.png",
};

/**
 * Provides the browser paths and loaders for terrain assets.
 */
export class TerrainAssetLoader {
  /**
   * @param {string} textureRoot Texture URL prefix.
   * @param {string} modelRoot Model URL prefix.
   */
  constructor(textureRoot = "/textures/", modelRoot = "/models/") {
    this.textureRoot = textureRoot;
    this.modelRoot = modelRoot;
    this.textureLoader = new THREE.TextureLoader();
    this.modelLoader = new GLTFLoader();
  }

  /**
   * @returns {Promise<object>} Loaded terrain textures and models.
   */
  async load() {
    const textures = Object.fromEntries(
      await Promise.all(
        Object.entries(TEXTURE_FILES).map(async ([name, filename]) => [
          name,
          await this.textureLoader.loadAsync(`${this.textureRoot}${filename}`),
        ]),
      ),
    );
    const [boulder, ventifact] = await Promise.all([
      this.loadModel("Boulder.glb"),
      this.loadModel("Ventifact.glb"),
    ]);

    return {
      safeRegolith: textures.SafeRegolith,
      dustStorm: textures.DustStorm,
      cubeTextures: {
        SafeRegolith: textures.SafeRegolith,
        SteepSlope: textures.SteepSlope,
        LooseSand: textures.LooseSand,
        DeepShadow: textures.DeepShadow,
        DustStorm: textures.SafeRegolith,
        Boulders: textures.SafeRegolith,
        Ventifacts: textures.SafeRegolith,
      },
      models: { Boulders: boulder, Ventifacts: ventifact },
    };
  }

  /**
   * Loads and validates one GLB scene.
   *
   * @param {string} filename Model filename.
   * @returns {Promise<THREE.Object3D>} Loaded model scene.
   */
  async loadModel(filename) {
    const result = await this.modelLoader.loadAsync(`${this.modelRoot}${filename}`);
    const model = result.scene;
    const size = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3());
    if (Math.max(size.x, size.y, size.z) <= 0) {
      throw new Error(`Model ${filename} has no visible geometry`);
    }
    return model;
  }
}
