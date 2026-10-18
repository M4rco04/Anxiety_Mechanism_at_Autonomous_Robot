import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createGridHelper, createTerrainMeshes } from "./terrain.js";

export function createTerrainScene(container, terrain) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x090b10);

  const camera = new THREE.PerspectiveCamera(
    45,
    container.clientWidth / container.clientHeight,
    0.1,
    1000,
  );
  camera.position.set(
    terrain.width * 0.8,
    terrain.height * 0.9,
    terrain.height * 0.8,
  );

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.maxPolarAngle = Math.PI / 2 - 0.05;
  controls.minDistance = 3;
  controls.maxDistance = Math.max(terrain.width, terrain.height) * 3;
  controls.update();

  scene.add(new THREE.HemisphereLight(0xffe0bf, 0x202735, 2));
  const sun = new THREE.DirectionalLight(0xffffff, 3);
  sun.position.set(10, 20, 10);
  scene.add(sun);

  scene.add(createTerrainMeshes(terrain));
  scene.add(createGridHelper(terrain.width, terrain.height));

  function resize() {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  }

  window.addEventListener("resize", resize);

  function animate() {
    controls.update();
    renderer.render(scene, camera);
  }

  renderer.setAnimationLoop(animate);
}
