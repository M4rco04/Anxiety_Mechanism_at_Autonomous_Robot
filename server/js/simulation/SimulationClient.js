/**
 * Drives the simulation by requesting steps and feeding snapshots to the
 * rover layer and telemetry panel.
 */
import { SimulationPanel } from "./SimulationPanel.js";

export class SimulationClient {
  /**
   * @param {import("../scene/TerrainScene.js").TerrainScene} scene
   */
  constructor(scene) {
    this.scene = scene;
    this.layer = scene.roverLayer;
    this.snapshot = null;
    this.playing = false;
    this.speed = 1;
    this.tickMs = 450;
    this.timer = null;
    this.busy = false;
    this._wasPlayingBeforeHidden = false;

    this.panel = new SimulationPanel({
      onToggle: () => this.toggle(),
      onStep: () => this.stepOnce(),
      onReset: () => this.reset(),
      onSpeed: (speed) => this.setSpeed(speed),
      onSelect: (id) => this.focus(id),
      onView: () => this.scene.resetView?.(),
    });

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this._wasPlayingBeforeHidden = this.playing;
        this.pause();
      } else if (this._wasPlayingBeforeHidden) {
        this.play();
      }
    });
  }

  async start() {
    try {
      const snapshot = await this._request("/api/simulation/state");
      this._apply(snapshot);
      if (snapshot.rovers?.length) {
        this.focus(snapshot.rovers[0].rover_id);
      }
      if (snapshot.running) {
        this.play();
      }
    } catch (error) {
      this.panel.setError(
        `Live simulation unavailable: ${error.message}. Terrain remains interactive.`,
      );
      console.error("Simulation start failed:", error);
    }
  }

  play() {
    if (!this.snapshot?.running || this.playing) {
      return;
    }
    this.playing = true;
    this.panel.setPlaying(true);
    this.panel.update(this.snapshot, { playing: true });
    this._schedule();
  }

  pause() {
    this.playing = false;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.panel.setPlaying(false);
    if (this.snapshot) {
      this.panel.update(this.snapshot, { playing: false });
    }
  }

  toggle() {
    if (this.playing) {
      this.pause();
    } else {
      this.play();
    }
  }

  async stepOnce() {
    this.pause();
    try {
      const snapshot = await this._request("/api/simulation/step", { method: "POST" });
      this._apply(snapshot);
    } catch (error) {
      this.panel.setError(`Step failed: ${error.message}`);
    }
  }

  async reset() {
    this.pause();
    try {
      const snapshot = await this._request("/api/simulation/reset", {
        method: "POST",
        body: JSON.stringify({}),
      });
      this._apply(snapshot);
      if (snapshot.running) {
        this.play();
      }
    } catch (error) {
      this.panel.setError(`Reset failed: ${error.message}`);
    }
  }

  setSpeed(speed) {
    this.speed = Math.max(0.25, Math.min(4, Number(speed) || 1));
    if (this.playing) {
      if (this.timer) {
        clearTimeout(this.timer);
        this.timer = null;
      }
      this._schedule();
    }
    if (this.snapshot) {
      this.panel.update(this.snapshot, { playing: this.playing });
    }
  }

  focus(id) {
    this.layer.setSelected(id);
    this.panel.select(id);
    this.scene.focusRover?.(id);
  }

  _schedule() {
    if (!this.playing || !this.snapshot?.running) {
      return;
    }
    if (this.timer) {
      clearTimeout(this.timer);
    }
    const interval = Math.max(120, this.tickMs / this.speed);
    this.timer = setTimeout(() => this._tick(), interval);
  }

  async _tick() {
    if (!this.playing || this.busy) {
      return;
    }
    this.busy = true;
    try {
      const snapshot = await this._request("/api/simulation/step", {
        method: "POST",
      });
      this._apply(snapshot);
    } catch (error) {
      this.panel.setError(`Simulation stopped: ${error.message}`);
      this.pause();
    } finally {
      this.busy = false;
      this._schedule();
    }
  }

  _apply(snapshot) {
    this.snapshot = snapshot;
    this.tickMs = Number(snapshot.display_tick_ms) || 450;
    const durationMs = Math.max(120, this.tickMs / this.speed);
    this.layer?.applySnapshot(snapshot, { durationMs });
    this.panel.update(snapshot, { playing: this.playing });
    if (!snapshot.running) {
      this.pause();
    }
  }

  async _request(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const payload = await response.json();
        detail = payload.error ?? detail;
      } catch {
        // Keep the status text.
      }
      throw new Error(detail);
    }
    return response.json();
  }

  destroy() {
    this.pause();
    this.panel.destroy();
  }
}
