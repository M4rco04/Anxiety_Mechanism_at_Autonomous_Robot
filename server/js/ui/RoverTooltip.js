/**
 * Rover telemetry tooltip, visually consistent with Robert's terrain tooltip.
 */

function escape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export class RoverTooltip {
  constructor(parent) {
    this.element = document.createElement("aside");
    this.element.className = "terrain-tooltip rover-tooltip";
    this.element.setAttribute("role", "tooltip");
    parent.appendChild(this.element);
    this.hide();
  }

  show(data, x, y) {
    if (!data) {
      this.hide();
      return;
    }
    const target = data.target ? `(${data.target[0]}, ${data.target[1]})` : "exploration";
    const battery = Number(data.battery ?? 0).toFixed(1);
    const stress = Number(data.stress_level ?? 0).toFixed(1);
    const wheel = Number(data.wheel_condition ?? 0).toFixed(1);
    const hull = Number(data.hull_condition ?? 0).toFixed(1);
    this.element.innerHTML = `
      <strong>R${escape(data.rover_id)} · ${escape(data.mission_status)}</strong>
      <span>Terrain: ${escape(data.current_terrain)} · target: ${escape(target)}</span>
      <span>Battery ${battery}% · stress ${stress}/100</span>
      <span>Wheels ${wheel}% · hull ${hull}%</span>
      <span>LIDAR ${escape(data.lidar_range)} · RGB ${escape(data.vision_range)}</span>
      <span>Own fears ${escape(data.fear_records)} · received ${escape(data.fear_events_received)}</span>
      <span class="rover-action">${escape(data.action_reason)}</span>
    `;
    this.element.style.left = `${x + 16}px`;
    this.element.style.top = `${y + 16}px`;
    this.element.classList.add("terrain-tooltip-visible");
  }

  hide() {
    this.element.classList.remove("terrain-tooltip-visible");
  }
}
