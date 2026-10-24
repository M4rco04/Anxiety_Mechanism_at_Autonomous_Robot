/**
 * Owns the Three.js scene, camera, controls, terrain and rover layers.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TerrainAssetLoader } from "../assets/TerrainAssetLoader.js";
import { TerrainGrid } from "../terrain/TerrainGrid.js";
import { TerrainRenderer } from "../terrain/TerrainRenderer.js";
import { TerrainTooltip } from "../ui/TerrainTooltip.js";
import { RoverTooltip } from "../ui/RoverTooltip.js";
import { RoverLayer } from "../rover/RoverLayer.js";

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
    this.camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      1000,
    );
    this.camera.position.set(
      terrain.width * 0.8,
      terrain.height * 0.9,
      terrain.height * 0.8,
    );
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(this.renderer.domElement);
    this.clock = new THREE.Clock();
    this.focusTarget = null;
    this.focusCamera = null;
    this.followRoverId = null;
    this.followOffset = null;
    this.userOrbiting = false;
    this.initialCameraPosition = this.camera.position.clone();
    this.roverLayer = null;
    this.terrainRenderer = null;
  }

  /**
   * Loads assets, adds terrain and rovers, and starts rendering.
   *
   * @returns {Promise<void>}
   */
  async start() {
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0, 0);
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05;
    this.controls.minDistance = 3;
    this.controls.maxDistance =
      Math.max(this.terrain.width, this.terrain.height) * 3;
    this.controls.update();
    this.controls.addEventListener("start", () => {
      this.userOrbiting = true;
    });
    this.controls.addEventListener("end", () => {
      this.userOrbiting = false;
      if (this.followRoverId !== null) {
        const followed = this.roverLayer?.focusPosition(this.followRoverId);
        if (followed) {
          this.followOffset = this.camera.position.clone().sub(followed);
        }
      }
    });

    this.scene.add(new THREE.HemisphereLight(0xffe0bf, 0x202735, 2));
    const sun = new THREE.DirectionalLight(0xffffff, 3);
    sun.position.set(10, 20, 10);
    this.scene.add(sun);

    this.assets = await new TerrainAssetLoader().load();
    this.terrainRenderer = new TerrainRenderer(this.assets);
    this.scene.add(this.terrainRenderer.create(this.terrain));
    this.scene.add(
      new TerrainGrid(this.assets).createHelper(
        this.terrain.width,
        this.terrain.height,
      ),
    );

    this.roverLayer = new RoverLayer({
      scene: this.scene,
      terrain: this.terrain,
      terrainRenderer: this.terrainRenderer,
      assets: this.assets,
    });
    this.terrainTooltip = new TerrainTooltip(this.container);
    this.roverTooltip = new RoverTooltip(this.container);

    const pointer = new THREE.Vector2();
    const raycaster = new THREE.Raycaster();
    this.renderer.domElement.addEventListener("pointermove", (event) => {
      const bounds = this.renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(pointer, this.camera);

      const roverId = this.roverLayer.pick(raycaster);
      if (roverId !== null) {
        const data = this.roverLayer.getRoverData(roverId);
        this.terrainTooltip.hide();
        this.roverTooltip.show(data, event.clientX, event.clientY);
        return;
      }
      this.roverTooltip.hide();

      const hit = raycaster.intersectObjects(
        this.terrainRenderer.cubes,
        false,
      )[0];
      if (hit?.object.userData.terrain) {
        this.terrainTooltip.show(
          hit.object.userData.terrain.type,
          event.clientX,
          event.clientY,
        );
      } else {
        this.terrainTooltip.hide();
      }
    });
    this.renderer.domElement.addEventListener("pointerleave", () => {
      this.terrainTooltip.hide();
      this.roverTooltip.hide();
    });
    window.addEventListener("resize", () => this.resize());

    this.renderer.setAnimationLoop(() => {
      const delta = Math.min(this.clock.getDelta(), 0.1);
      this.roverLayer.update(delta);
      if (this.followRoverId !== null) {
        const followed = this.roverLayer.focusPosition(this.followRoverId);
        if (followed) {
          this.focusTarget = followed.clone();
          if (this.followOffset && !this.userOrbiting) {
            this.focusCamera = followed.clone().add(this.followOffset);
          }
        }
      }
      if (this.focusTarget) {
        this.controls.target.lerp(
          this.focusTarget,
          1 - Math.exp(-delta * 4.0),
        );
        if (
          this.followRoverId === null
          && this.controls.target.distanceTo(this.focusTarget) < 0.02
        ) {
          this.controls.target.copy(this.focusTarget);
          this.focusTarget = null;
        }
      }
      if (this.focusCamera) {
        this.camera.position.lerp(
          this.focusCamera,
          1 - Math.exp(-delta * 3.0),
        );
        if (
          this.followRoverId === null
          && this.camera.position.distanceTo(this.focusCamera) < 0.05
        ) {
          this.camera.position.copy(this.focusCamera);
          this.focusCamera = null;
        }
      }
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    });
  }

  /**
   * Focus the orbit target on a rover without changing user zoom.
   *
   * @param {number} roverId Rover identifier.
   */
  focusRover(roverId) {
    const position = this.roverLayer?.focusPosition(roverId);
    if (!position) {
      return;
    }
    this.followRoverId = roverId;
    this.userOrbiting = false;
    const offset = this.camera.position
      .clone()
      .sub(this.controls.target)
      .normalize()
      .multiplyScalar(9.0);
    offset.y = Math.max(3.0, offset.y);
    this.followOffset = offset;
    this.focusTarget = position.clone();
    this.focusCamera = position.clone().add(offset);
  }

  /**
   * Return to the overview of the whole terrain.
   */
  resetView() {
    this.followRoverId = null;
    this.followOffset = null;
    this.focusTarget = new THREE.Vector3(0, 0, 0);
    this.focusCamera = this.initialCameraPosition.clone();
  }

  /**
   * Updates camera and renderer dimensions after a window resize.
   */
  resize() {
    this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(
      this.container.clientWidth,
      this.container.clientHeight,
    );
  }
}
