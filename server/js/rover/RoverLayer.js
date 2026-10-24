/**
 * Smoothly animates rover snapshots on top of Robert's terrain scene.
 *
 * Snapshot positions are grid cells; this layer interpolates them in world
 * space, animates wheels and instruments, and adds display-only trails,
 * radio/fear pulses and dust.
 */
import * as THREE from "three";
import { RoverModel } from "./RoverModel.js";

const ACCENTS = [0xd97b3f, 0x6fb7ff, 0x72e0b0, 0xf2c28f];
const FEAR_COLOR = 0xff5a4a;
const RADIO_COLOR = 0x7fd7ff;
const GOAL_COLOR = 0x62ff9a;
const DAMAGE_COLOR = 0xffb347;

const ease = (t) => t * t * (3 - 2 * t);
const clamp01 = (value) => Math.max(0, Math.min(1, value));

function shortestAngle(from, to) {
  let delta = (to - from + Math.PI) % (Math.PI * 2) - Math.PI;
  if (delta < -Math.PI) {
    delta += Math.PI * 2;
  }
  return delta;
}

export class RoverLayer {
  /**
   * @param {object} options
   * @param {THREE.Scene} options.scene
   * @param {object} options.terrain Terrain payload.
   * @param {object} options.terrainRenderer Robert's TerrainRenderer.
   * @param {object} options.assets Loaded terrain assets.
   */
  constructor({ scene, terrain, terrainRenderer, assets }) {
    this.scene = scene;
    this.terrain = terrain;
    this.terrainRenderer = terrainRenderer;
    this.assets = assets;
    this.group = new THREE.Group();
    this.group.name = "rover-layer";
    this.scene.add(this.group);
    this.rovers = new Map();
    this.trails = new Map();
    this.fearMarkers = new Map();
    this.effects = [];
    this.dust = [];
    this.elapsed = 0;
    this.selectedId = null;
    this.snapshot = null;
    this._lastStep = -1;
    this._seenEvents = new Set();
    this._dustTexture = assets?.dustStorm ?? null;
    this.fearGroup = new THREE.Group();
    this.group.add(this.fearGroup);
  }

  // ------------------------------------------------------------------
  // Snapshot intake
  // ------------------------------------------------------------------
  applySnapshot(snapshot, { durationMs = 450 } = {}) {
    if (this._lastStep >= 0 && snapshot.step < this._lastStep) {
      this._seenEvents.clear();
      this._clearEffects();
    }
    this.snapshot = snapshot;
    const duration = Math.max(0.08, Number(durationMs) / 1000);
    const incoming = new Set();

    for (const data of snapshot.rovers ?? []) {
      incoming.add(data.rover_id);
      const entry = this._ensureRover(data);
      const model = entry.model;
      const target = this._worldPosition(data.position[0], data.position[1]);
      const start = model.group.position.clone();
      const startHeading = model.group.rotation.y;
      const targetHeading = this._headingRadians(data);
      const current = entry.state;

      entry.state = {
        ...current,
        start,
        target,
        startY: start.y,
        targetY: target.y,
        startHeading,
        targetHeading,
        elapsed: 0,
        duration,
        data,
        moving: start.distanceToSquared(target) > 1e-8,
      };

      model.setTelemetry({
        battery: data.battery,
        stress: data.stress_level,
        mission_status: data.mission_status,
      });
      model.setTerrain({
        slope: data.terrain_slope ?? 0,
        type: data.current_terrain ?? null,
      });
      this._updateTrail(entry, data);
    }

    for (const [id, entry] of this.rovers) {
      if (!incoming.has(id)) {
        this._removeRover(id, entry);
      }
    }

    this._updateFearMarkers(snapshot.fear_positions ?? []);
    if (snapshot.step !== this._lastStep) {
      this._processEvents(snapshot.events ?? []);
      this._lastStep = snapshot.step;
    }
    this._applySelection();
  }

  _ensureRover(data) {
    let entry = this.rovers.get(data.rover_id);
    if (entry) {
      return entry;
    }
    const model = new RoverModel(data.rover_id, {
      accent: ACCENTS[data.rover_id % ACCENTS.length],
    });
    const world = this._worldPosition(data.position[0], data.position[1]);
    const heading = this._headingRadians(data);
    model.place({
      x: world.x,
      y: world.y,
      z: world.z,
      headingRad: heading,
    });
    model.setTerrain({
      slope: data.terrain_slope ?? 0,
      type: data.current_terrain ?? null,
    });
    this.group.add(model.group);

    entry = {
      model,
      state: {
        start: world.clone(),
        target: world.clone(),
        startY: world.y,
        targetY: world.y,
        startHeading: heading,
        targetHeading: heading,
        elapsed: 1,
        duration: 1,
        data,
        moving: false,
        dustTimer: 0,
        trailLength: -1,
      },
      trail: null,
    };
    this.rovers.set(data.rover_id, entry);
    return entry;
  }

  _removeRover(id, entry) {
    this.group.remove(entry.model.group);
    entry.model.dispose();
    const trail = this.trails.get(id);
    if (trail) {
      trail.geometry.dispose();
      trail.material.dispose();
      this.group.remove(trail);
      this.trails.delete(id);
    }
    this.rovers.delete(id);
  }

  // ------------------------------------------------------------------
  // World mapping
  // ------------------------------------------------------------------
  _worldPosition(gridX, gridY) {
    const x = gridX - (this.terrain.width - 1) / 2;
    const z = gridY - (this.terrain.height - 1) / 2;
    const y = this._heightAt(gridX, gridY) + 0.025;
    return new THREE.Vector3(x, y, z);
  }

  _heightAt(gridX, gridY) {
    if (this.terrainRenderer?.heightAt) {
      return this.terrainRenderer.heightAt(gridX, gridY);
    }
    return 0.15;
  }

  _headingRadians(data) {
    const heading = data.heading ?? [0, 1];
    const dx = Number(heading[0]) || 0;
    const dz = Number(heading[1]) || 0;
    if (dx === 0 && dz === 0) {
      return this.rovers.get(data.rover_id)?.model.group.rotation.y ?? 0;
    }
    return Math.atan2(dx, dz);
  }

  // ------------------------------------------------------------------
  // Animation
  // ------------------------------------------------------------------
  update(dt) {
    const delta = Math.min(0.05, Math.max(0, dt));
    this.elapsed += delta;

    for (const entry of this.rovers.values()) {
      const state = entry.state;
      const model = entry.model;
      state.elapsed += delta;

      if (state.data) {
        const t = clamp01(state.elapsed / Math.max(0.001, state.duration));
        const headingDelta = shortestAngle(
          state.startHeading,
          state.targetHeading,
        );
        const needsTurn = Math.abs(headingDelta) > 0.18;
        const turnFraction = 0.24;
        let moveProgress;
        let heading;

        if (needsTurn && t < turnFraction) {
          const turnProgress = ease(t / turnFraction);
          heading = state.startHeading + headingDelta * turnProgress;
          moveProgress = 0;
        } else {
          heading = state.targetHeading;
          moveProgress = needsTurn
            ? ease((t - turnFraction) / (1 - turnFraction))
            : ease(t);
        }

        const x = THREE.MathUtils.lerp(
          state.start.x,
          state.target.x,
          moveProgress,
        );
        const z = THREE.MathUtils.lerp(
          state.start.z,
          state.target.z,
          moveProgress,
        );
        const y = THREE.MathUtils.lerp(state.startY, state.targetY, moveProgress);
        const previous = model.group.position.clone();
        model.place({ x, y, z, headingRad: heading });

        const travelled = Math.hypot(x - previous.x, z - previous.z);
        if (travelled > 0.0001) {
          model.addWheelDistance(travelled);
          this._emitDust(entry, delta, travelled);
        }
        model.update(delta, this.elapsed);
        this._updateSelectionRing(entry);
      } else {
        model.update(delta, this.elapsed);
      }
    }

    this._updateEffects(delta);
    this._updateFearPulse(delta);
  }

  _emitDust(entry, delta, travelled) {
    const state = entry.state;
    const terrainType = state.data?.current_terrain;
    const dusty = terrainType === "LooseSand" || terrainType === "DustStorm";
    if (!dusty || travelled < 0.001 || !this._dustTexture) {
      return;
    }
    state.dustTimer = (state.dustTimer ?? 0) + delta;
    if (state.dustTimer < 0.09) {
      return;
    }
    state.dustTimer = 0;
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: this._dustTexture,
        transparent: true,
        opacity: 0.34,
        depthWrite: false,
        color: 0xe7d2b5,
      }),
    );
    const position = entry.model.group.position;
    sprite.position.set(
      position.x + (Math.random() - 0.5) * 0.18,
      position.y + 0.05,
      position.z + 0.18,
    );
    const scale = 0.18 + Math.random() * 0.12;
    sprite.scale.set(scale, scale * 0.7, 1);
    this.group.add(sprite);
    this.dust.push({
      sprite,
      life: 0.85,
      age: 0,
      drift: new THREE.Vector3(
        (Math.random() - 0.5) * 0.15,
        0.08 + Math.random() * 0.1,
        0.12 + Math.random() * 0.12,
      ),
    });
    if (this.dust.length > 90) {
      const oldest = this.dust.shift();
      this._disposeSprite(oldest.sprite);
    }
  }

  // ------------------------------------------------------------------
  // Trails, fear markers and event effects
  // ------------------------------------------------------------------
  _updateTrail(entry, data) {
    const id = data.rover_id;
    let line = this.trails.get(id);
    const path = data.path ?? [];
    if (!line) {
      const geometry = new THREE.BufferGeometry();
      const material = new THREE.LineBasicMaterial({
        color: ACCENTS[id % ACCENTS.length],
        transparent: true,
        opacity: 0.58,
        depthWrite: false,
      });
      line = new THREE.Line(geometry, material);
      line.frustumCulled = false;
      this.trails.set(id, line);
      this.group.add(line);
    }
    if (entry.state.trailLength === path.length) {
      return;
    }
    entry.state.trailLength = path.length;
    const samples = path.slice(-300);
    const positions = new Float32Array(samples.length * 3);
    samples.forEach((cell, index) => {
      const world = this._worldPosition(cell[0], cell[1]);
      positions[index * 3] = world.x;
      positions[index * 3 + 1] = world.y + 0.018;
      positions[index * 3 + 2] = world.z;
    });
    line.geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(positions, 3),
    );
    line.geometry.setDrawRange(0, samples.length);
    line.geometry.computeBoundingSphere();
  }

  _updateFearMarkers(positions) {
    const wanted = new Set(
      positions.map((position) => `${position[0]},${position[1]}`),
    );
    for (const [key, marker] of this.fearMarkers) {
      if (!wanted.has(key)) {
        marker.removeFromParent();
        marker.geometry.dispose();
        marker.material.dispose();
        this.fearMarkers.delete(key);
      }
    }
    for (const position of positions) {
      const key = `${position[0]},${position[1]}`;
      if (this.fearMarkers.has(key)) {
        continue;
      }
      const marker = new THREE.Mesh(
        new THREE.RingGeometry(0.22, 0.31, 32),
        new THREE.MeshBasicMaterial({
          color: FEAR_COLOR,
          transparent: true,
          opacity: 0.5,
          side: THREE.DoubleSide,
          depthWrite: false,
        }),
      );
      const world = this._worldPosition(position[0], position[1]);
      marker.position.set(world.x, world.y + 0.035, world.z);
      marker.rotation.x = -Math.PI / 2;
      marker.userData.phase = Math.random() * Math.PI * 2;
      this.fearGroup.add(marker);
      this.fearMarkers.set(key, marker);
    }
  }

  _updateFearPulse(dt) {
    for (const marker of this.fearMarkers.values()) {
      marker.userData.phase += dt * 2.2;
      const pulse = 0.5 + 0.5 * Math.sin(marker.userData.phase);
      marker.scale.setScalar(0.9 + pulse * 0.16);
      marker.material.opacity = 0.28 + pulse * 0.25;
    }
  }

  _processEvents(events) {
    for (const event of events) {
      const key = `${event.type}:${event.step}:${event.rover_id ?? ""}:${event.position ?? ""}`;
      if (this._seenEvents.has(key)) {
        continue;
      }
      this._seenEvents.add(key);
      const entry = this.rovers.get(event.rover_id);
      if (!entry || !event.position) {
        continue;
      }
      const model = entry.model;
      if (event.type === "fear_imprint") {
        model.pulseFear();
        this._addRing(event.position, FEAR_COLOR, 0.55);
      } else if (event.type === "radio_sent" || event.type === "radio_received") {
        model.pulseRadio();
        this._addRing(event.position, RADIO_COLOR, 0.8);
      } else if (event.type === "goal_reached") {
        this._addRing(event.position, GOAL_COLOR, 1.1);
      } else if (event.type === "destroyed" || event.type === "overturned") {
        this._addRing(event.position, DAMAGE_COLOR, 0.7);
      }
    }
    if (this._seenEvents.size > 500) {
      this._seenEvents.clear();
    }
  }

  _addRing(position, color, maxScale = 0.8) {
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.14, 0.20, 40),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.85,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    const world = this._worldPosition(position[0], position[1]);
    ring.position.set(world.x, world.y + 0.04, world.z);
    ring.rotation.x = -Math.PI / 2;
    ring.userData.age = 0;
    ring.userData.maxScale = maxScale;
    this.group.add(ring);
    this.effects.push(ring);
  }

  _updateEffects(dt) {
    for (let index = this.effects.length - 1; index >= 0; index -= 1) {
      const ring = this.effects[index];
      ring.userData.age += dt;
      const t = clamp01(ring.userData.age / 0.9);
      const scale = 1 + t * ring.userData.maxScale * 4;
      ring.scale.setScalar(scale);
      ring.material.opacity = (1 - t) * 0.8;
      if (t >= 1) {
        ring.removeFromParent();
        ring.geometry.dispose();
        ring.material.dispose();
        this.effects.splice(index, 1);
      }
    }

    for (let index = this.dust.length - 1; index >= 0; index -= 1) {
      const particle = this.dust[index];
      particle.age += dt;
      const t = clamp01(particle.age / particle.life);
      particle.sprite.position.addScaledVector(particle.drift, dt);
      particle.sprite.material.opacity = (1 - t) * 0.34;
      const scale = 0.18 + t * 0.3;
      particle.sprite.scale.set(scale, scale * 0.7, 1);
      if (t >= 1) {
        this._disposeSprite(particle.sprite);
        this.dust.splice(index, 1);
      }
    }
  }

  _disposeSprite(sprite) {
    sprite.removeFromParent();
    sprite.material.dispose();
  }

  _clearEffects() {
    for (const ring of this.effects) {
      ring.removeFromParent();
      ring.geometry.dispose();
      ring.material.dispose();
    }
    this.effects = [];
    for (const particle of this.dust) {
      this._disposeSprite(particle.sprite);
    }
    this.dust = [];
  }

  // ------------------------------------------------------------------
  // Selection / picking
  // ------------------------------------------------------------------
  setSelected(roverId) {
    this.selectedId = roverId;
    this._applySelection();
  }

  _applySelection() {
    for (const [id, entry] of this.rovers) {
      const selected = this.selectedId === id;
      const range = entry.state.data?.lidar_range ?? 2;
      entry.model.showScanRing(selected, range);
    }
  }

  _updateSelectionRing(entry) {
    if (this.selectedId == null) {
      return;
    }
    const selected = entry.state.data?.rover_id === this.selectedId;
    entry.model.showScanRing(
      selected,
      entry.state.data?.lidar_range ?? 2,
    );
  }

  pick(raycaster) {
    const hits = raycaster.intersectObjects(this.group.children, true);
    for (const hit of hits) {
      let object = hit.object;
      while (object) {
        if (object.userData?.roverId !== undefined) {
          return object.userData.roverId;
        }
        object = object.parent;
      }
    }
    return null;
  }

  getRoverData(id) {
    const entry = this.rovers.get(id);
    return entry?.state.data ?? null;
  }

  focusPosition(id) {
    const entry = this.rovers.get(id);
    return entry ? entry.model.group.position.clone() : null;
  }

  dispose() {
    for (const [id, entry] of [...this.rovers]) {
      this._removeRover(id, entry);
    }
    for (const marker of this.fearMarkers.values()) {
      marker.geometry.dispose();
      marker.material.dispose();
    }
    this.fearMarkers.clear();
    for (const ring of this.effects) {
      ring.geometry.dispose();
      ring.material.dispose();
    }
    this.effects = [];
    for (const particle of this.dust) {
      this._disposeSprite(particle.sprite);
    }
    this.dust = [];
    this.group.removeFromParent();
  }
}

export { ACCENTS as ROVER_ACCENTS };
