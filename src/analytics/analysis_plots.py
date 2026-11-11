"""Figures for ``root/analyze.py`` (three-variant comparison).

Static PNGs in the same dark theme as ``src/analytics/plots.py``. Colours:
the three variants use the first three dark-mode slots of the validated
categorical palette (blue, orange, aqua; all-pairs CVD-safe on the dark
surface). Stress uses a single-hue orange ramp (sequential: dark = low,
bright = high).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection, PolyCollection

SURFACE = "#11151c"
FIGURE = "#090b10"
TEXT = "#f5f0e8"
TEXT_MUTED = "#b8c0cc"
GRID = "#2a303a"

VARIANT_COLORS = ["#3987e5", "#d95926", "#199e70", "#9a6fd1"]  # fixed order, never cycled
STRESS_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "stress", ["#2a1a12", "#7a3415", "#d95926", "#f5a06e", "#fde3cf"]
)
# Routes are thin lines: start the ramp at a visible step so low stress
# does not disappear into the terrain.
ROUTE_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "route_stress", STRESS_CMAP(np.linspace(0.38, 1.0, 64))
)


def _style() -> None:
    plt.style.use("dark_background")
    plt.rcParams.update(
        {
            "figure.facecolor": FIGURE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": "#4b5563",
            "axes.labelcolor": TEXT,
            "text.color": TEXT,
            "xtick.color": TEXT_MUTED,
            "ytick.color": TEXT_MUTED,
            "grid.color": GRID,
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _rate_bars(
    axis: plt.Axes,
    labels: Sequence[str],
    rates: Sequence[float],
    lows: Sequence[float],
    highs: Sequence[float],
) -> None:
    x = np.arange(len(labels))
    values = np.array(rates) * 100
    err = np.vstack([values - np.array(lows) * 100, np.array(highs) * 100 - values])
    axis.bar(x, values, width=0.62, color=VARIANT_COLORS[: len(labels)], zorder=2)
    axis.errorbar(x, values, yerr=err, fmt="none", ecolor=TEXT_MUTED, capsize=4, lw=1, zorder=3)
    for xi, value, high in zip(x, values, highs):
        axis.text(xi, high * 100 + 2.5, f"{value:.0f}%", ha="center", va="bottom", color=TEXT)
    axis.set_xticks(x, labels)
    axis.set_ylim(0, 115)
    axis.set_yticks([0, 25, 50, 75, 100])
    axis.grid(axis="y", alpha=0.5, zorder=0)


def plot_rates(summary: pd.DataFrame, output_dir: Path, tests: Mapping[str, str]) -> list[Path]:
    """Rover survival per test and route completion (goal test), with 95% CI."""

    _style()
    paths: list[Path] = []
    present = [t for t in tests if t in set(summary["test_id"])]
    if not present:
        return paths
    fig, axes = plt.subplots(1, len(present), figsize=(5.2 * len(present), 4), squeeze=False)
    for axis, test in zip(axes[0], present):
        rows = summary[summary["test_id"] == test]
        _rate_bars(
            axis,
            list(rows["variant"]),
            list(rows["rover_survival_rate"]),
            list(rows["rover_survival_ci_low"]),
            list(rows["rover_survival_ci_high"]),
        )
        axis.set_title(tests[test])
    axes[0][0].set_ylabel("Rovers that survived [%]")
    fig.suptitle("Rover survival (95% CI)", x=0.01, ha="left", fontsize=11)
    paths.append(_save(fig, output_dir / "plots" / "survival.png"))

    if "goal_navigation" in present:
        rows = summary[summary["test_id"] == "goal_navigation"]
        fig, axis = plt.subplots(figsize=(5.2, 4))
        _rate_bars(
            axis,
            list(rows["variant"]),
            list(rows["route_completed_rate"]),
            list(rows["route_completed_ci_low"]),
            list(rows["route_completed_ci_high"]),
        )
        axis.set_ylabel("Rovers that completed the route [%]")
        axis.set_title("Goal navigation: route completed (95% CI)", loc="left")
        paths.append(_save(fig, output_dir / "plots" / "goal_completion.png"))
    return paths


def plot_coverage(episodes: pd.DataFrame, variants: Sequence[str], output_dir: Path) -> Path | None:
    """Distribution of discovered terrain in the exploration test."""

    frame = episodes[episodes["test"] == "exploration"]
    if frame.empty:
        return None
    _style()
    fig, axis = plt.subplots(figsize=(6, 4))
    rng = np.random.default_rng(0)
    data = [frame[frame["variant"] == v]["terrain_discovered_pct"].to_numpy() for v in variants]
    box = axis.boxplot(
        data,
        positions=range(len(variants)),
        widths=0.5,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": TEXT, "lw": 1.5},
        whiskerprops={"color": TEXT_MUTED},
        capprops={"color": TEXT_MUTED},
    )
    for patch, color in zip(box["boxes"], VARIANT_COLORS):
        patch.set_facecolor(mcolors.to_rgba(color, 0.25))
        patch.set_edgecolor(color)
    for index, (values, color) in enumerate(zip(data, VARIANT_COLORS)):
        jitter = rng.uniform(-0.12, 0.12, len(values))
        axis.scatter(index + jitter, values, s=14, color=color, edgecolors=SURFACE, linewidths=0.6, zorder=3)
    axis.set_xticks(range(len(variants)), variants)
    axis.set_ylabel("Terrain discovered [% of passable cells]")
    axis.set_title("Exploration: terrain discovered per simulation", loc="left")
    axis.grid(axis="y", alpha=0.5)
    return _save(fig, output_dir / "plots" / "coverage.png")


def plot_time_series(
    curves: pd.DataFrame, variants: Sequence[str], tests: Mapping[str, str], output_dir: Path
) -> list[Path]:
    """Rovers still operational, mean stress and discovered terrain over time."""

    if curves.empty:
        return []
    _style()
    panels = [
        ("operational_pct", "Rovers still operational [%]"),
        ("mean_stress", "Mean stress of operational rovers"),
        ("discovered_pct", "Terrain discovered [%]"),
    ]
    paths: list[Path] = []
    for test, test_name in tests.items():
        frame = curves[curves["test"] == test]
        if frame.empty:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
        for axis, (column, title) in zip(axes, panels):
            for variant, color in zip(variants, VARIANT_COLORS):
                group = frame[frame["variant"] == variant]
                if group.empty:
                    continue
                stats = group.groupby("step")[column].agg(["mean", "std", "count"])
                if column == "mean_stress":
                    # Stress only exists for running rovers: skip thin samples
                    # and smooth step-to-step noise (10-step rolling mean).
                    stats = stats[stats["count"] >= 5]
                    stats = stats.rolling(10, min_periods=1).mean()
                stats = stats[stats["count"] > 0]
                sem = stats["std"].fillna(0) / np.sqrt(stats["count"].clip(lower=1))
                low = (stats["mean"] - 1.96 * sem).clip(lower=0)
                high = stats["mean"] + 1.96 * sem
                if column != "mean_stress":
                    high = high.clip(upper=100)
                axis.plot(stats.index, stats["mean"], color=color, lw=2, label=variant)
                axis.fill_between(stats.index, low, high, color=color, alpha=0.15, lw=0)
            axis.set_title(title, loc="left")
            axis.set_xlabel("Step")
            axis.grid(alpha=0.5)
        axes[0].set_ylim(0, 105)
        axes[1].set_ylim(bottom=0)
        axes[1].set_title("Mean stress of operational rovers (10-step mean)", loc="left")
        axes[0].legend(frameon=False, loc="lower left")
        fig.suptitle(f"{test_name}: mean over simulations (band = 95% CI)", x=0.01, ha="left", fontsize=11)
        fig.tight_layout()
        paths.append(_save(fig, output_dir / "plots" / f"time_series_{test}.png"))
    return paths


# ----------------------------------------------------------------------
# Swarm stress map
# ----------------------------------------------------------------------
def _hex_center(position: tuple[int, int]) -> tuple[float, float]:
    # Mesa odd-q layout (see src/model/types.py): odd columns are shifted up.
    x, y = position
    return 1.5 * x, math.sqrt(3) * (y - 0.5 * (x & 1))


def _hex_polygon(center: tuple[float, float]) -> list[tuple[float, float]]:
    cx, cy = center
    return [
        (cx + math.cos(math.radians(a)), cy + math.sin(math.radians(a)))
        for a in range(0, 360, 60)
    ]


def plot_swarm_stress_map(record: Mapping[str, Any], output_path: Path) -> Path:
    """Two panels for one swarm simulation.

    Left: the terrain with each rover's route coloured by its stress.
    Right: every cell the swarm drove over, coloured by the highest stress felt
    there. Crosses mark own fear imprints, rings mark where rovers were lost.
    """

    _style()
    terrain: dict[tuple[int, int], str] = record["terrain"]
    colors: dict[str, str] = record["terrain_colors"]
    tracks: list[dict[str, Any]] = record["tracks"]
    cells = sorted(terrain)
    polygons = [_hex_polygon(_hex_center(cell)) for cell in cells]
    muted = [mcolors.to_rgba(colors[terrain[cell]], 0.2) for cell in cells]
    norm = mcolors.Normalize(0, 100)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.6))
    # Left: terrain + routes
    left = axes[0]
    left.add_collection(PolyCollection(polygons, facecolors=muted, edgecolors="none"))
    for track in tracks:
        points = [_hex_center(p) for p in track["positions"]]
        if len(points) < 2:
            continue
        segments = [[points[i], points[i + 1]] for i in range(len(points) - 1)]
        lines = LineCollection(segments, cmap=ROUTE_CMAP, norm=norm, linewidths=2.2, capstyle="round")
        lines.set_array(np.array(track["stress"][1:]))
        left.add_collection(lines)
        sx, sy = points[0]
        left.scatter([sx], [sy], s=60, marker="o", facecolor=SURFACE, edgecolor=TEXT, lw=1.4, zorder=5)
        left.annotate(f"R{track['rover_id']}", (sx, sy), xytext=(6, 6), textcoords="offset points", color=TEXT, fontsize=8)
    left.set_title("Terrain and swarm routes, coloured by stress", loc="left")

    # Right: max stress per cell
    right = axes[1]
    max_stress: dict[tuple[int, int], float] = {}
    for track in tracks:
        for position, stress in zip(track["positions"], track["stress"]):
            max_stress[position] = max(max_stress.get(position, 0.0), stress)
    background = [mcolors.to_rgba(colors[terrain[cell]], 0.12) for cell in cells]
    right.add_collection(PolyCollection(polygons, facecolors=background, edgecolors="none"))
    visited = sorted(max_stress)
    heat = PolyCollection(
        [_hex_polygon(_hex_center(c)) for c in visited],
        array=np.array([max_stress[c] for c in visited]),
        cmap=STRESS_CMAP,
        norm=norm,
        edgecolors=SURFACE,
        linewidths=0.4,
    )
    right.add_collection(heat)
    right.set_title("Highest stress felt on each cell the swarm drove over", loc="left")

    for axis in axes:
        for track in tracks:
            for position in track["imprints"]:
                cx, cy = _hex_center(position)
                axis.scatter([cx], [cy], marker="x", s=55, color=TEXT, lw=1.6, zorder=6)
            if track["lost_at"] is not None:
                cx, cy = _hex_center(track["lost_at"])
                axis.scatter([cx], [cy], s=120, facecolor="none", edgecolor="#e66767", lw=1.8, zorder=6)
        axis.set_aspect("equal")
        axis.autoscale_view()
        axis.set_xticks([])
        axis.set_yticks([])
        for spine in axis.spines.values():
            spine.set_visible(False)

    colorbar = fig.colorbar(heat, ax=axes, fraction=0.025, pad=0.01)
    colorbar.set_label("Stress (smoothed, 0–100)")
    handles = [
        plt.Line2D([], [], ls="none", marker="h", ms=9, color=mcolors.to_rgba(colors[name], 0.6), label=name)
        for name in sorted(set(terrain.values()))
    ]
    handles += [
        plt.Line2D([], [], ls="none", marker="o", ms=7, mfc=SURFACE, mec=TEXT, label="Start (R = rover)"),
        plt.Line2D([], [], ls="none", marker="x", ms=7, color=TEXT, label="Fear imprint"),
        plt.Line2D([], [], ls="none", marker="o", ms=9, mfc="none", mec="#e66767", label="Rover lost"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=8)
    fig.suptitle(
        f"Swarm stress map — {record['test_name']}, seed {record['seed']}, {record['steps']} steps",
        x=0.01, ha="left", fontsize=12,
    )
    return _save(fig, output_path)


__all__ = [
    "VARIANT_COLORS",
    "plot_coverage",
    "plot_rates",
    "plot_swarm_stress_map",
    "plot_time_series",
]
