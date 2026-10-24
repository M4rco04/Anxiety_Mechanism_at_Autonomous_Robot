/**
 * Telemetry and playback panel for the live rover simulation.
 */
export class SimulationPanel {
  /**
   * @param {{onToggle: Function, onStep: Function, onReset: Function, onSpeed: Function, onSelect: Function}} callbacks
   */
  constructor(callbacks) {
    this.callbacks = callbacks;
    this.element = document.querySelector("#simulation-panel");
    if (!this.element) {
      this.element = document.createElement("aside");
      this.element.id = "simulation-panel";
      document.body.appendChild(this.element);
    }
    this.element.className = "simulation-panel";
    this.element.innerHTML = `
      <header class="simulation-panel-header">
        <div>
          <span class="simulation-eyebrow">MARS · LIVE MISSION</span>
          <strong data-step>Step 0</strong>
        </div>
        <span class="simulation-status" data-run>starting</span>
      </header>
      <div class="simulation-badge" data-badge hidden></div>
      <div class="simulation-controls">
        <button type="button" data-action="toggle" aria-label="Play or pause simulation">Pause</button>
        <button type="button" data-action="step" aria-label="Advance one simulation step">Step</button>
        <button type="button" data-action="reset" aria-label="Reset simulation">Reset</button>
        <button type="button" data-action="view" aria-label="Show the whole terrain">View</button>
        <label class="simulation-speed">Speed
          <select aria-label="Simulation speed">
            <option value="0.5">0.5×</option>
            <option value="1" selected>1×</option>
            <option value="2">2×</option>
          </select>
        </label>
      </div>
      <div class="simulation-rover-list" data-rovers></div>
      <footer class="simulation-panel-footer">
        <span data-coverage>coverage —</span>
        <span data-termination></span>
      </footer>
      <p class="simulation-error" data-error hidden></p>
    `;

    this.rows = new Map();
    this.selectedId = null;
    this.snapshot = null;

    this.element.querySelector('[data-action="toggle"]').addEventListener("click", () => {
      this.callbacks.onToggle?.();
    });
    this.element.querySelector('[data-action="step"]').addEventListener("click", () => {
      this.callbacks.onStep?.();
    });
    this.element.querySelector('[data-action="reset"]').addEventListener("click", () => {
      this.callbacks.onReset?.();
    });
    this.element.querySelector('[data-action="view"]').addEventListener("click", () => {
      this.callbacks.onView?.();
    });
    this.element.querySelector("select").addEventListener("change", (event) => {
      this.callbacks.onSpeed?.(Number(event.target.value));
    });
  }

  update(snapshot, { playing = false } = {}) {
    this.snapshot = snapshot;
    this.element.querySelector("[data-step]").textContent = `Step ${snapshot.step}`;
    this.element.querySelector("[data-run]").textContent = snapshot.running
      ? playing
        ? "running"
        : "paused"
      : snapshot.termination_reason ?? "finished";

    const toggle = this.element.querySelector('[data-action="toggle"]');
    toggle.textContent = playing ? "Pause" : "Play";
    toggle.disabled = !snapshot.running;
    this.element.querySelector('[data-action="step"]').disabled = !snapshot.running;

    const badge = this.element.querySelector("[data-badge]");
    if (!snapshot.is_scientific) {
      badge.hidden = false;
      badge.textContent = "PIPELINE SMOKE — SCAFFOLD NAVIGATION";
      badge.className = "simulation-badge simulation-badge-warning";
    } else {
      badge.hidden = false;
      badge.textContent = `${snapshot.navigation_mode.toUpperCase()} · SCIENTIFIC`;
      badge.className = "simulation-badge";
    }

    const coverage = Number(snapshot.metrics?.coverage_discovered ?? 0);
    this.element.querySelector("[data-coverage]").textContent =
      `coverage ${(coverage * 100).toFixed(1)}% · ${snapshot.metrics?.alive_rovers ?? 0}/${snapshot.rovers.length} alive`;
    this.element.querySelector("[data-termination]").textContent =
      snapshot.termination_reason ?? "";

    this._renderRovers(snapshot.rovers ?? []);
  }

  _renderRovers(rovers) {
    const container = this.element.querySelector("[data-rovers]");
    const incoming = new Set(rovers.map((rover) => rover.rover_id));
    for (const [id, row] of this.rows) {
      if (!incoming.has(id)) {
        row.element.remove();
        this.rows.delete(id);
      }
    }

    for (const rover of rovers) {
      let row = this.rows.get(rover.rover_id);
      if (!row) {
        row = this._createRow(rover.rover_id);
        this.rows.set(rover.rover_id, row);
        container.appendChild(row.element);
      }
      this._updateRow(row, rover);
    }

    if (this.selectedId == null && rovers.length) {
      this.select(rovers[0].rover_id);
    }
  }

  _createRow(id) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "rover-row";
    element.dataset.roverId = String(id);
    element.innerHTML = `
      <span class="rover-row-head">
        <span class="rover-dot"></span>
        <strong>R${id}</strong>
        <span class="rover-status" data-status></span>
        <span class="rover-fear" data-fear></span>
      </span>
      <span class="telemetry-line"><span>BAT</span><i class="telemetry-track"><b data-battery></b></i><em data-battery-text></em></span>
      <span class="telemetry-line"><span>STR</span><i class="telemetry-track"><b data-stress></b></i><em data-stress-text></em></span>
      <span class="telemetry-line telemetry-mini"><span>WHEEL</span><b data-wheel></b><span>HULL</span><b data-hull></b></span>
    `;
    element.addEventListener("click", () => {
      this.select(id);
      this.callbacks.onSelect?.(id);
    });
    return {
      element,
      status: element.querySelector("[data-status]"),
      fear: element.querySelector("[data-fear]"),
      battery: element.querySelector("[data-battery]"),
      batteryText: element.querySelector("[data-battery-text]"),
      stress: element.querySelector("[data-stress]"),
      stressText: element.querySelector("[data-stress-text]"),
      wheel: element.querySelector("[data-wheel]"),
      hull: element.querySelector("[data-hull]"),
    };
  }

  _updateRow(row, rover) {
    row.status.textContent = rover.mission_status;
    row.status.dataset.status = rover.mission_status;
    row.fear.textContent = `fear ${rover.fear_records}`;
    const battery = Number(rover.battery ?? 0);
    const stress = Number(rover.stress_level ?? 0);
    const wheel = Number(rover.wheel_condition ?? 0);
    const hull = Number(rover.hull_condition ?? 0);
    row.battery.style.width = `${Math.max(0, Math.min(100, battery))}%`;
    row.battery.dataset.level = battery > 50 ? "ok" : battery > 25 ? "warn" : "bad";
    row.batteryText.textContent = `${battery.toFixed(0)}%`;
    row.stress.style.width = `${Math.max(0, Math.min(100, stress))}%`;
    row.stress.dataset.level = stress > 65 ? "bad" : stress > 35 ? "warn" : "ok";
    row.stressText.textContent = stress.toFixed(0);
    row.wheel.textContent = `${wheel.toFixed(0)}%`;
    row.hull.textContent = `${hull.toFixed(0)}%`;
  }

  select(id) {
    this.selectedId = id;
    for (const [rowId, row] of this.rows) {
      row.element.classList.toggle("selected", rowId === id);
    }
  }

  setPlaying(playing) {
    const toggle = this.element.querySelector('[data-action="toggle"]');
    toggle.textContent = playing ? "Pause" : "Play";
  }

  setError(message = "") {
    const error = this.element.querySelector("[data-error]");
    error.hidden = !message;
    error.textContent = message;
  }

  destroy() {
    this.element.remove();
  }
}
