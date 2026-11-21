"""Model validation report (``uv run validate``).

Checks that do not need a mission simulation:

1. Real maps: class shares of the polygons vs the 10 m raster vs randomly
   placed windows (the sampling is unbiased), determinism of the windows,
   and the composition of the accepted test windows.
2. Traction model vs the paper it is built from (Wang et al. 2015) and an
   independent source (the Pioneer manual's maximum grade).
3. Terrain effects per entry: the traction model against the previous one.
4. Field-data corrections: sand on slopes and dust storms vs rover data.

Writes ``results/validation/`` (report.md, CSV tables, figures).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd


def _md(frame: pd.DataFrame, formats: dict[str, str]) -> str:
    headers = list(frame.columns)
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in frame.itertuples(index=False):
        cells = []
        for name, value in zip(headers, row):
            fmt = formats.get(name)
            cells.append(format(value, fmt) if fmt and isinstance(value, (int, float)) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _get(frame: pd.DataFrame, terrain: str, column: str) -> float:
    return float(frame.loc[frame.terrain == terrain, column].iloc[0])


def _plots(out: Path, slope: pd.DataFrame) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    from config.config import SimulationConfig
    from src.model.model import MarsSimulation

    paths = []
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(slope.slope_deg, slope.p_overturn_old, "o--", color="#888888", label="previous model (logistic)")
    ax1.plot(slope.slope_deg, slope.p_overturn_new, "o-", color="#c0392b", label="lateral grip exceeded (traction model)")
    ax1.axvspan(30, 42, color="#f5b7b1", alpha=0.3, lw=0)
    ax1.set_xlabel("slope [deg]")
    ax1.set_ylabel("P(overturn) per entry")
    ax1.set_title("Overturn on a slope (red band: steep-slope cells)")
    ax1.legend(frameon=False, fontsize=8)
    ax2.plot(slope.slope_deg, slope.mean_slip, "o-", color="#2471a3", label="mean slip ratio")
    ax2.plot(slope.slope_deg, slope.p_slip_alarm, "s-", color="#1abc9c", label="P(slip >= slip_alarm)")
    ax2b = ax2.twinx()
    ax2b.plot(slope.slope_deg, slope.energy_factor, "^-", color="#7d3c98", label="energy / flat cell")
    ax2b.set_ylabel("energy per cell [x flat]")
    ax2.axvline(19.7, color="#555555", ls=":", lw=1)
    ax2.text(20.2, 0.9, "traction limit 19.7 deg", fontsize=8)
    ax2.set_xlabel("slope [deg]")
    ax2.set_ylabel("slip")
    ax2.set_title("Traction of the P3-AT (Wang et al. 2015)")
    handles = ax2.get_legend_handles_labels()
    handles2 = ax2b.get_legend_handles_labels()
    ax2.legend(handles[0] + handles2[0], handles[1] + handles2[1], frameon=False, fontsize=8, loc="center left")
    fig.tight_layout()
    path = out / "plots" / "traction.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)

    fig, axes = plt.subplots(2, 4, figsize=(16, 8.5))
    for row, key in enumerate(("mars", "atacama")):
        for col, seed in enumerate((0, 1, 2, 3)):
            model = MarsSimulation(SimulationConfig(seed=seed, num_rovers=0, map_source=key))
            ax = axes[row, col]
            xs, ys, cs = [], [], []
            for x in range(model.grid.width):
                for y in range(model.grid.height):
                    terrain = model.terrain_at((x, y))
                    xs.append(x * math.sqrt(3) / 2)
                    ys.append(y - 0.5 * (x & 1))
                    cs.append(mcolors.to_rgb(terrain.color))
            ax.scatter(xs, ys, c=cs, marker="h", s=34, linewidths=0)
            info = model.map_info
            ax.set_title(f"{key}, seed {seed}\nx={info['window_min_xy'][0]:.0f}, y={info['window_min_xy'][1]:.0f} m",
                         fontsize=9)
            ax.set_aspect("equal")
            ax.axis("off")
    from matplotlib.patches import Patch

    from src.environment.terrain import TERRAIN_COLORS

    fig.legend(handles=[Patch(color=c, label=n) for n, c in TERRAIN_COLORS.items()],
               loc="lower center", ncol=7, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    path = out / "plots" / "map_windows.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Validation of the maps, traction and terrain model.")
    parser.add_argument("--windows", type=int, default=300, help="Windows per map for the sampling check.")
    parser.add_argument("--draws", type=int, default=20000, help="Monte Carlo draws per terrain / slope.")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("results") / "validation")
    args = parser.parse_args(argv)

    from src.analytics import validation as v

    out = args.output
    (out / "plots").mkdir(parents=True, exist_ok=True)

    pipeline = v.map_pipeline_checks(args.windows)
    pipeline["raster_error_pp"] = 100 * (pipeline.raster_10m - pipeline.polygons)
    pipeline.to_csv(out / "map_pipeline.csv", index=False, float_format="%.5f")
    determinism = v.determinism_check()
    windows = v.window_stats_table(range(args.windows))
    windows.to_csv(out / "window_composition.csv", index=False, float_format="%.4f")
    traction = v.traction_checks()
    pd.Series(traction).to_csv(out / "traction.csv", header=["value"])
    slope = v.slope_response(n=args.draws)
    slope.to_csv(out / "slope_response.csv", index=False, float_format="%.4f")
    new = v.terrain_effects(True, n=args.draws)
    old = v.terrain_effects(False, n=args.draws)
    new.to_csv(out / "terrain_effects.csv", index=False, float_format="%.4f")
    old.to_csv(out / "terrain_effects_previous.csv", index=False, float_format="%.4f")
    sand = v.sand_slope_response(n=args.draws)
    sand.to_csv(out / "sand_slope_response.csv", index=False, float_format="%.4f")
    dust = v.dust_charging_check()
    pd.Series(dust).to_csv(out / "dust_charging.csv", header=["value"])
    plots = [] if args.no_plots else _plots(out, slope)

    max_err = pipeline.raster_error_pp.abs().max()
    pct = {c: ".1%" for c in ("polygons", "raster_10m", "random_windows", "accepted_windows")}
    lines = [
        "# Model validation",
        "",
        "Generated by `uv run validate`. No mission simulations: these checks test the",
        "parts of the model that the experiments rely on.",
        "",
        "## 1. Real maps",
        "",
        "Class shares of the source polygons (area), of the 10 m raster, of randomly placed",
        f"50×50 windows ({args.windows} per map, no acceptance rules: tests the sampling) and of",
        "the accepted test windows (with the rules of `WindowRules`).",
        "",
        _md(pipeline[["map", "class", "polygons", "raster_10m", "random_windows", "accepted_windows"]],
            pct | {"raster_error_pp": ".2f"}),
        "",
        f"- Rasterization error: at most **{max_err:.2f} percentage points** per class.",
        "- Random windows reproduce the raster shares up to the sampling noise of",
        "  spatially clustered classes (windows are 1–2.5 km, the units several km).",
        "- The accepted windows (here: their map classes, before the landforms) differ on",
        "  purpose: boulder fields, the 1–1.5 km wide crater rim of Jezero (all of it steep",
        "  slope), windows with more than 60% hazardous ground and windows with fewer than",
        "  three hazardous classes (≥ 1% each, after the landforms) are rejected, so a rover",
        "  can start, charge, choose its way and meet different dangers.",
        "- Same seed → same window, different seed → different window: "
        + ", ".join(f"{k} {'OK' if ok else 'FAILED'}" for k, ok in determinism.items()) + ".",
        "",
        ("Mean composition of the accepted windows (seeds 0–"
        f"{args.windows - 1}), from the map classes alone and with the added landforms"),
        "(craters, wind drifts and dune slip faces on Mars; dune slip faces, rock outcrops and",
        "ravines in the Atacama; boulder fields on both) and overlays (shadow, dust). `hazard_types` = number of",
        "hazardous terrains (sand, ventifacts, slope, shadow, dust) with at least 1% of the window:",
        "",
        _md(windows[["map", "terrain", "safe", "sand", "ventifacts", "slope", "boulders", "shadow",
                     "dust", "hazard_types", "attempts"]],
            {c: ".1%" for c in ("safe", "sand", "ventifacts", "slope", "boulders", "shadow", "dust")}
            | {"attempts": ".1f", "hazard_types": ".1f"}),
        "",
        "## 2. Traction model (Wang et al. 2015) vs independent data",
        "",
        "| Quantity | Model | Reference | |",
        "|---|---:|---:|---|",
        (f"| Steepest climbable slope (μ = 0.309 / 0.377 / 0.444) | {traction['climb_limit_mu_min']:.1f} / "
        f"**{traction['climb_limit_mu_mean']:.1f}** / {traction['climb_limit_mu_max']:.1f}° | "
        f"{traction['spec_max_grade_deg']:.1f}° | Pioneer manual: max grade 40% for the AT "
        f"({'inside' if traction['spec_within_range'] else 'outside'} the model range) |"),
        (f"| ICR coefficient, turning in place | {traction['chi_model']:.4f} | {traction['chi_measured']:.4f} | "
        f"Eq. (45) vs Table 3 (tightest path), error {traction['chi_rel_error']:+.2%} |"),
        f"| Slip on flat firm ground | {traction['slip_flat']:.4f} | ≈ 0 | lab floor, Section 3 |",
        (f"| Energy of a 60° in-place turn [× one flat cell] | {traction['turn60_factor_20m']:.3f} (20 m) / "
        f"{traction['turn60_factor_50m']:.3f} (50 m) | – | follows from Eq. (45) and Table 1 |"),
        "",
        "The climb limit is not fitted to the manufacturer's value: it follows from the",
        "friction and rolling resistance of Table 1 alone. `alpha_safe` = 20° in the",
        "homeostat is this limit.",
        "",
        "Slope response (Monte Carlo, random heading, μ uniform between the two measured values):",
        "",
        _md(slope, {"mean_slip": ".3f", "p_slip_alarm": ".1%", "energy_factor": ".2f",
                    "p_overturn_new": ".1%", "p_overturn_old": ".1%"}),
        "",
        "## 3. Terrain effects per entry",
        "",
        "Mean loss of one entry (battery, wheels, hull in %), share of speed lost, and",
        "probabilities, over the slopes of the real-map cells. Traction model (now):",
        "",
        _md(new, {"battery": ".2f", "battery_cv": ".2f", "wheels": ".2f", "hull": ".2f",
                  "speed_loss": ".2f", "p_overturn": ".1%", "p_stuck": ".1%"}),
        "",
        "Previous model (`traction_model=False`, `sand_slope_model=False`), same slopes:",
        "",
        _md(old, {"battery": ".2f", "battery_cv": ".2f", "wheels": ".2f", "hull": ".2f",
                  "speed_loss": ".2f", "p_overturn": ".1%", "p_stuck": ".1%"}),
        "",
        (f"- Steep slopes: overturns fall from {_get(old, 'SteepSlope', 'p_overturn'):.0%} to "
        f"{_get(new, 'SteepSlope', 'p_overturn'):.0%} per entry, the battery drain from"),
        (f"  {_get(old, 'SteepSlope', 'battery'):.1f}% to {_get(new, 'SteepSlope', 'battery'):.1f}% "
        "(the old drain grew with exp(0.05·slope), the new one is the work"),
        "  against gravity, capped by the grip); the rover now also loses its speed (slip).",
        (f"- Gentle ground costs more than before ({_get(new, 'SafeRegolith', 'battery'):.2f}% instead of "
        f"{_get(old, 'SafeRegolith', 'battery'):.2f}% on regolith): the"),
        "  work on 2–14° slopes is 1.6–4× the work on flat ground with f_r = 0.0371.",
        "- Ventifacts, shadow and dust keep their own effects (the paper covers firm",
        "  ground only); the slope adds its work and slip on top. Sand: see section 4.",
        "",
        "## 4. Field data: sand on slopes, dust and solar power",
        "",
        "Wang et al. measured on firm ground only, so loose sand and dust were checked",
        "against rover data from the literature (open sources; full texts of some papers",
        "are paywalled, their figures are quoted from abstracts and reviews).",
        "",
        "Sand: slip of entries without embedding and probability of getting stuck vs slope",
        "(`sand_embed_slope_deg` = 17, `sand_slope_exponent` = 4):",
        "",
        _md(sand, {"mean_slip": ".2f", "p_stuck": ".1%"}),
        "",
        "- The curve passes through the anchors it was built from: moderate slip on 10°,",
        "  embedding on 17° (analog rover in cohesionless sand, Rothrock et al. 2016) and",
        "  full slip by 18° (Curiosity's operational slip model).",
        "- It does **not** reproduce Curiosity's 77% slip at about 4° in the Hidden Valley",
        "  megaripples (Arvidson et al. 2017): on gentle sand the model keeps the",
        "  slope-independent Beta(3, 5) slip (mean 0.375). Megaripples are a sand form the",
        "  maps do not resolve.",
        "",
        "Dust storms and solar power:",
        "",
        "| Quantity | Model | Data |",
        "|---|---:|---:|",
        (f"| Solar power in a dust storm / clear air | {dust['model_fraction']:.2f} | "
         f"{dust['measured_fraction']:.2f} (Opportunity, {dust['opportunity_storm_wh']:.0f} / "
         f"{dust['opportunity_clear_wh']:.0f} Wh per sol, July 2007) |"),
        (f"| Charging 40 → 90% [steps] | {dust['steps_40_to_90_clear']:.0f} clear / "
         f"{dust['steps_40_to_90_shaded']:.0f} near a storm | – |"),
        "",
        "Before this correction a dust storm only shortened the camera range; charging",
        "next to it ran at the full rate.",
    ]
    if plots:
        lines += ["", "## Figures", ""] + [f"![{p.stem}](plots/{p.name})" for p in plots]
    report = out / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
