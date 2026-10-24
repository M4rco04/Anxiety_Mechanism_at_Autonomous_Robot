/**
 * Procedural Pioneer-style Mars rover with visible scientific instruments.
 *
 * The model is deliberately built from Three.js primitives: it needs no extra
 * GLB asset and plugs directly into Robert's existing scene and lighting.
 */
import * as THREE from "three";

const COLORS = {
  body: 0xe8e2d6,
  accent: 0xd97b3f,
  metal: 0x2b2f36,
  darkMetal: 0x171a1f,
  rubber: 0x121418,
  solar: 0x16324f,
  solarLine: 0x4e7ca8,
  lens: 0x7fd7ff,
  amber: 0xffb347,
  green: 0x62ff9a,
  fear: 0xff5a4a,
  white: 0xf5f0e8,
};

const clamp01 = (value) => Math.max(0, Math.min(1, Number(value) || 0));

function damp(current, target, lambda, dt) {
  return THREE.MathUtils.damp(current, target, lambda, dt);
}

function makeMaterial(color, options = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: 0.55,
    metalness: 0.18,
    ...options,
  });
}

function addBox(group, material, width, height, depth, x, y, z, rotation = null) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(width, height, depth),
    material,
  );
  mesh.position.set(x, y, z);
  if (rotation) {
    mesh.rotation.set(rotation.x ?? 0, rotation.y ?? 0, rotation.z ?? 0);
  }
  group.add(mesh);
  return mesh;
}

function addCylinder(group, material, radiusTop, radiusBottom, height, x, y, z, rotation = null) {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 20),
    material,
  );
  mesh.position.set(x, y, z);
  if (rotation) {
    mesh.rotation.set(rotation.x ?? 0, rotation.y ?? 0, rotation.z ?? 0);
  }
  group.add(mesh);
  return mesh;
}

export class RoverModel {
  /**
   * @param {number} id Rover identifier.
   * @param {{accent?: number}} options Visual options.
   */
  constructor(id, options = {}) {
    this.id = id;
    this.group = new THREE.Group();
    this.group.userData.roverId = id;
    this.bodyPivot = new THREE.Group();
    // Slightly larger than the physical cell footprint so the instruments
    // remain readable from the default orbit camera.
    this.bodyPivot.scale.setScalar(1.3);
    this.group.add(this.bodyPivot);

    this.wheels = [];
    this.batterySegments = [];
    this.cameraLenses = [];
    this.wheelRadius = 0.135;
    this._wheelRotation = 0;
    this._wheelSpeed = 0;
    this._radioPulse = 0;
    this._fearPulse = 0;
    this._targetPitch = 0;
    this._targetRoll = 0;
    this._status = "active";
    this._destroyed = false;
    this._overturned = false;

    this.materials = this._createMaterials(options.accent ?? COLORS.accent);
    this._build();
    this.group.traverse((object) => {
      if (object.isMesh) {
        object.userData.roverId = id;
      }
    });
    this.setTelemetry({ battery: 100, stress: 0, mission_status: "active" });
  }

  _createMaterials(accent) {
    return {
      body: makeMaterial(COLORS.body, { roughness: 0.5, metalness: 0.12 }),
      accent: makeMaterial(accent, { roughness: 0.48, metalness: 0.2 }),
      metal: makeMaterial(COLORS.metal, { roughness: 0.34, metalness: 0.72 }),
      darkMetal: makeMaterial(COLORS.darkMetal, { roughness: 0.32, metalness: 0.75 }),
      rubber: makeMaterial(COLORS.rubber, { roughness: 0.96, metalness: 0.05 }),
      solar: makeMaterial(COLORS.solar, {
        roughness: 0.35,
        metalness: 0.42,
        emissive: 0x06111f,
      }),
      solarLine: makeMaterial(COLORS.solarLine, {
        roughness: 0.4,
        metalness: 0.35,
        emissive: 0x102a42,
      }),
      lens: makeMaterial(COLORS.lens, {
        roughness: 0.16,
        metalness: 0.55,
        emissive: COLORS.lens,
        emissiveIntensity: 1.1,
      }),
      amber: makeMaterial(COLORS.amber, {
        roughness: 0.3,
        emissive: COLORS.amber,
        emissiveIntensity: 1.0,
      }),
      antenna: makeMaterial(0xb9c4cf, { roughness: 0.32, metalness: 0.72 }),
      status: makeMaterial(COLORS.green, {
        roughness: 0.25,
        transparent: true,
        opacity: 0.62,
        emissive: COLORS.green,
        emissiveIntensity: 1.2,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
      fear: makeMaterial(COLORS.fear, {
        roughness: 0.25,
        transparent: true,
        opacity: 0,
        emissive: COLORS.fear,
        emissiveIntensity: 1.3,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
      battery: makeMaterial(COLORS.green, {
        roughness: 0.3,
        emissive: COLORS.green,
        emissiveIntensity: 1.1,
      }),
      shadow: new THREE.MeshBasicMaterial({
        color: 0x000000,
        transparent: true,
        opacity: 0.28,
        depthWrite: false,
      }),
      scan: new THREE.MeshBasicMaterial({
        color: COLORS.lens,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    };
  }

  _build() {
    const body = this.bodyPivot;
    const m = this.materials;

    // Chassis and lower deck.
    addBox(body, m.darkMetal, 0.64, 0.07, 0.94, 0, 0.15, 0);
    addBox(body, m.metal, 0.70, 0.05, 1.0, 0, 0.205, 0);
    addBox(body, m.body, 0.58, 0.16, 0.82, 0, 0.30, 0);
    addBox(body, m.accent, 0.60, 0.025, 0.84, 0, 0.39, 0);

    // Solar array with thin grid lines.
    addBox(body, m.solar, 0.56, 0.022, 0.58, 0, 0.435, -0.03);
    for (let index = -2; index <= 2; index += 1) {
      addBox(body, m.solarLine, 0.005, 0.026, 0.56, index * 0.11, 0.438, -0.03);
    }
    for (let index = -1; index <= 1; index += 1) {
      addBox(body, m.solarLine, 0.54, 0.026, 0.005, 0, 0.439, -0.03 + index * 0.17);
    }

    // Wheels and suspension arms.
    for (const side of [-1, 1]) {
      for (const z of [-0.31, 0, 0.31]) {
        const wheel = new THREE.Group();
        wheel.position.set(side * 0.415, 0.145, z);
        const tire = addCylinder(
          wheel,
          m.rubber,
          this.wheelRadius,
          this.wheelRadius,
          0.115,
          0,
          0,
          0,
          { z: Math.PI / 2 },
        );
        tire.rotation.z = Math.PI / 2;
        addCylinder(
          wheel,
          m.metal,
          0.052,
          0.052,
          0.122,
          0,
          0,
          0,
          { z: Math.PI / 2 },
        );
        const hub = addCylinder(
          wheel,
          m.accent,
          0.022,
          0.022,
          0.128,
          0,
          0,
          0,
          { z: Math.PI / 2 },
        );
        hub.rotation.z = Math.PI / 2;
        this.wheels.push(wheel);
        body.add(wheel);

        addBox(
          body,
          m.metal,
          0.16,
          0.035,
          0.045,
          side * 0.335,
          0.205,
          z,
        );
      }
    }

    // Front bumper, hazard lights and headlights.
    addBox(body, m.metal, 0.52, 0.045, 0.035, 0, 0.205, 0.485);
    this.headlights = [];
    for (const x of [-0.24, 0.24]) {
      const light = addCylinder(
        body,
        m.amber,
        0.022,
        0.022,
        0.026,
        x,
        0.24,
        0.492,
        { x: Math.PI / 2 },
      );
      this.headlights.push(light);
    }
    for (const x of [-0.3, 0.3]) {
      addCylinder(
        body,
        m.amber,
        0.014,
        0.014,
        0.018,
        x,
        0.32,
        -0.405,
        { x: Math.PI / 2 },
      );
    }

    // Camera mast with stereo RGB cameras.
    this.mastPivot = new THREE.Group();
    this.mastPivot.position.set(-0.17, 0.0, -0.20);
    body.add(this.mastPivot);
    addCylinder(this.mastPivot, m.metal, 0.022, 0.025, 0.30, 0, 0.52, 0);
    this.cameraHead = addBox(
      this.mastPivot,
      m.darkMetal,
      0.17,
      0.105,
      0.095,
      0,
      0.67,
      0.015,
    );
    for (const x of [-0.045, 0.045]) {
      const lens = addCylinder(
        this.mastPivot,
        m.lens,
        0.027,
        0.027,
        0.025,
        x,
        0.67,
        0.072,
        { x: Math.PI / 2 },
      );
      this.cameraLenses.push(lens);
    }

    // Spinning LIDAR puck.
    addCylinder(this.mastPivot, m.metal, 0.055, 0.055, 0.06, 0, 0.765, 0.015);
    this.lidar = new THREE.Group();
    this.lidar.position.set(0, 0.80, 0.015);
    this.mastPivot.add(this.lidar);
    addCylinder(this.lidar, m.darkMetal, 0.06, 0.065, 0.045, 0, 0, 0);
    addCylinder(this.lidar, m.lens, 0.065, 0.065, 0.012, 0, 0.028, 0);
    addBox(this.lidar, m.lens, 0.11, 0.012, 0.012, 0, 0.024, 0.052);

    // Radio antenna.
    this.antennaGroup = new THREE.Group();
    this.antennaGroup.position.set(-0.27, 0.32, -0.34);
    body.add(this.antennaGroup);
    addCylinder(this.antennaGroup, m.antenna, 0.006, 0.009, 0.38, 0, 0.19, 0);
    this.antennaTip = new THREE.Mesh(
      new THREE.SphereGeometry(0.026, 12, 10),
      m.amber,
    );
    this.antennaTip.position.set(0, 0.39, 0);
    this.antennaGroup.add(this.antennaTip);

    // Battery status strip on the rear deck.
    for (let index = 0; index < 4; index += 1) {
      const segment = addBox(
        body,
        m.battery,
        0.10,
        0.018,
        0.024,
        -0.22 + index * 0.145,
        0.407,
        -0.40,
      );
      this.batterySegments.push(segment);
    }

    // Ground contact shadow and status rings.
    this.shadow = new THREE.Mesh(
      new THREE.CircleGeometry(0.47, 32),
      m.shadow,
    );
    this.shadow.rotation.x = -Math.PI / 2;
    this.shadow.position.y = 0.006;
    this.group.add(this.shadow);

    this.statusRing = new THREE.Mesh(
      new THREE.RingGeometry(0.37, 0.44, 48),
      m.status,
    );
    this.statusRing.rotation.x = -Math.PI / 2;
    this.statusRing.position.y = 0.012;
    this.group.add(this.statusRing);

    this.fearRing = new THREE.Mesh(
      new THREE.RingGeometry(0.48, 0.58, 48),
      m.fear,
    );
    this.fearRing.rotation.x = -Math.PI / 2;
    this.fearRing.position.y = 0.014;
    this.group.add(this.fearRing);

    this.scanRing = new THREE.Mesh(
      new THREE.RingGeometry(0.90, 0.98, 80),
      m.scan,
    );
    this.scanRing.rotation.x = -Math.PI / 2;
    this.scanRing.position.y = 0.01;
    this.scanRing.visible = false;
    this.group.add(this.scanRing);
  }

  place({ x, y, z, headingRad }) {
    this.group.position.set(x, y, z);
    this.group.rotation.y = headingRad;
  }

  setTelemetry({ battery = 100, stress = 0, mission_status = "active" } = {}) {
    if (
      mission_status === "active"
      && (this._destroyed || this._overturned)
    ) {
      this.resetVisualState();
    }
    this.battery = clamp01(battery / 100) * 100;
    this.stress = clamp01(stress / 100) * 100;
    this._status = mission_status;

    const stressRatio = this.stress / 100;
    const color = new THREE.Color(COLORS.green);
    if (stressRatio > 0.5) {
      color.lerp(new THREE.Color(COLORS.fear), (stressRatio - 0.5) * 2);
    } else {
      color.lerp(new THREE.Color(COLORS.amber), stressRatio * 2);
    }
    this.materials.status.color.copy(color);
    this.materials.status.emissive.copy(color);
    this.materials.status.opacity = 0.48 + stressRatio * 0.28;

    const activeSegments = Math.max(0, Math.min(4, Math.ceil(this.battery / 25)));
    const batteryColor =
      this.battery > 50
        ? new THREE.Color(COLORS.green)
        : this.battery > 25
          ? new THREE.Color(COLORS.amber)
          : new THREE.Color(COLORS.fear);
    this.materials.battery.color.copy(batteryColor);
    this.materials.battery.emissive.copy(batteryColor);
    this.batterySegments.forEach((segment, index) => {
      segment.visible = index < activeSegments;
    });

    if (mission_status === "destroyed") {
      this.setDestroyed();
    } else if (mission_status === "overturned") {
      this.setOverturned();
    }
  }

  setTerrain({ slope = 0, type = null } = {}) {
    this._terrainType = type;
    const normalized = Math.min(1, Math.max(0, slope / 90));
    this._targetPitch = normalized * 0.16;
    this._targetRoll = normalized * 0.10;
  }

  addWheelDistance(distance) {
    if (!Number.isFinite(distance) || this._destroyed || this._overturned) {
      return;
    }
    this._wheelRotation += distance / this.wheelRadius;
  }

  pulseRadio() {
    this._radioPulse = 1.0;
  }

  pulseFear() {
    this._fearPulse = 1.0;
    this.materials.fear.opacity = 0.8;
    this.fearRing.scale.setScalar(0.85);
  }

  showScanRing(visible, range = 3) {
    this.scanRing.visible = Boolean(visible);
    this.scanRing.scale.setScalar(Math.max(1.0, range));
    this.materials.scan.opacity = visible ? 0.13 : 0;
  }

  resetVisualState() {
    this._destroyed = false;
    this._overturned = false;
    this._wheelRotation = 0;
    this.bodyPivot.rotation.set(0, 0, 0);
    this.bodyPivot.position.y = 0;
    this.materials.status.color.set(COLORS.green);
    this.materials.status.emissive.set(COLORS.green);
    this.materials.fear.opacity = 0;
    this.materials.scan.opacity = 0;
    this.materials.battery.color.set(COLORS.green);
    this.materials.battery.emissive.set(COLORS.green);
    this._fearPulse = 0;
    this._radioPulse = 0;
  }

  setDestroyed() {
    if (this._destroyed) {
      return;
    }
    this._destroyed = true;
    this._overturned = false;
    this.materials.status.color.set(0x4b5563);
    this.materials.status.emissive.set(0x111827);
    this.materials.fear.opacity = 0;
    this.materials.scan.opacity = 0;
    this.bodyPivot.rotation.z = 0.22;
    this.bodyPivot.position.y = -0.025;
    this.antennaTip.material.emissiveIntensity = 0.05;
  }

  setOverturned() {
    if (this._overturned) {
      return;
    }
    this._overturned = true;
    this._destroyed = false;
    this.bodyPivot.rotation.z = 0.95;
    this.bodyPivot.position.y = -0.055;
    this.materials.status.color.set(COLORS.amber);
    this.materials.status.emissive.set(COLORS.amber);
    this.materials.scan.opacity = 0;
  }

  update(dt, elapsed) {
    const delta = Math.min(0.05, Math.max(0, dt));
    if (!this._destroyed && !this._overturned) {
      this.bodyPivot.rotation.x = damp(
        this.bodyPivot.rotation.x,
        this._targetPitch,
        5.0,
        delta,
      );
      this.bodyPivot.rotation.z = damp(
        this.bodyPivot.rotation.z,
        this._targetRoll,
        5.0,
        delta,
      );
    }

    if (!this._destroyed && !this._overturned) {
      for (const wheel of this.wheels) {
        wheel.rotation.x = this._wheelRotation;
      }
      this.lidar.rotation.y += delta * 4.6;
      this.mastPivot.rotation.y = Math.sin(elapsed * 0.65) * 0.16;
      this.cameraLenses.forEach((lens, index) => {
        lens.material.emissiveIntensity =
          0.8 + 0.35 * Math.sin(elapsed * 2.4 + index * 0.8);
      });
    }

    const pulse = 0.5 + 0.5 * Math.sin(elapsed * 2.2);
    this.materials.status.opacity =
      (this._status === "destroyed" ? 0.25 : 0.48) + 0.12 * pulse;
    this.statusRing.scale.setScalar(1.0 + 0.025 * pulse);

    this._radioPulse = Math.max(0, this._radioPulse - delta * 2.2);
    this.antennaTip.material.emissiveIntensity =
      0.45 + 3.2 * this._radioPulse;
    this.antennaTip.scale.setScalar(1.0 + 0.35 * this._radioPulse);

    this._fearPulse = Math.max(0, this._fearPulse - delta * 0.9);
    this.materials.fear.opacity = Math.max(
      this.materials.fear.opacity,
      this._fearPulse * 0.55,
    );
    this.fearRing.scale.setScalar(0.85 + (1 - this._fearPulse) * 0.35);
    this.materials.fear.opacity = Math.max(0, this.materials.fear.opacity - delta * 0.35);

    this.materials.scan.opacity = this.scanRing.visible
      ? 0.10 + 0.04 * pulse
      : 0;
  }

  dispose() {
    this.group.traverse((object) => {
      if (object.isMesh) {
        object.geometry?.dispose();
      }
    });
    Object.values(this.materials).forEach((material) => material.dispose?.());
    this.group.removeFromParent();
  }
}

export { COLORS as ROVER_COLORS };
