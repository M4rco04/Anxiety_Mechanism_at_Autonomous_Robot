/**
 * Owns the Three.js scene, camera, controls, and render loop.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TerrainAssetLoader } from "../assets/TerrainAssetLoader.js";
import { TerrainGrid } from "../terrain/TerrainGrid.js";
import { TerrainRenderer } from "../terrain/TerrainRenderer.js";
import { TerrainTooltip } from "../ui/TerrainTooltip.js";

export class TerrainScene {
  /**
   * @param {HTMLElement} container Canvas host element.
   * @param {object} terrain Terrain payload.
   */
  constructor(container, terrain) {
    this.container = container;
    this.terrain = terrain;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x090b10);
    this.camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 1000);
    this.camera.position.set(terrain.width * 0.8, terrain.height * 0.9, terrain.height * 0.8);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(this.renderer.domElement);
  }

  /**
   * Loads assets, adds terrain, and starts rendering.
   *
   * @returns {Promise<void>}
   */
  async start() {
    const controls = new OrbitControls(this.camera, this.renderer.domElement);
    controls.target.set(0, 0, 0);
    controls.maxPolarAngle = Math.PI / 2 - 0.05;
    controls.minDistance = 3;
    controls.maxDistance = Math.max(this.terrain.width, this.terrain.height) * 3;
    controls.update();
    this.scene.add(new THREE.HemisphereLight(0xffe0bf, 0x202735, 2));
    const sun = new THREE.DirectionalLight(0xffffff, 3);
    sun.position.set(10, 20, 10);
    this.scene.add(sun);
    const assets = await new TerrainAssetLoader().load();
    const renderer = new TerrainRenderer(assets);
    this.scene.add(renderer.create(this.terrain));
    this.scene.add(new TerrainGrid(assets).createHelper(this.terrain.width, this.terrain.height));
    const tooltip = new TerrainTooltip(this.container);
    const pointer = new THREE.Vector2();
    const raycaster = new THREE.Raycaster();
    this.renderer.domElement.addEventListener("pointermove", (event) => {
      const bounds = this.renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(pointer, this.camera);
      const hit = raycaster.intersectObjects(renderer.cubes, false)[0];
      if (hit?.object.userData.terrain) {
        tooltip.show(
          hit.object.userData.terrain.type,
          event.clientX,
          event.clientY,
        );
      } else {
        tooltip.hide();
      }
    });
    this.renderer.domElement.addEventListener("pointerleave", () => tooltip.hide());
    window.addEventListener("resize", () => this.resize());
    this.renderer.setAnimationLoop(() => {
      controls.update();
      this.renderer.render(this.scene, this.camera);
    });
  }

  /**
   * Updates camera and renderer dimensions after a window resize.
   */
  resize() {
    this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
  }
}
