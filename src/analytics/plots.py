"""Publication-style plots for the rover experiments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config.config import SimulationConfig
from src.analytics.results import EpisodeResult
from src.model.model import MarsSimulation

PALETTE = {
    "online": "#8fb8ff",
    "emotional": "#f2a65a",
    "swarm_emotional": "#72e0b0",
    "scaffold": "#b8c0cc",
}


def _style() -> None:
    plt.style.use("dark_background")
    plt.rcParams.update(
        {
            "figure.facecolor": "#090b10",
            "axes.facecolor": "#11151c",
            "axes.edgecolor": "#4b5563",
            "axes.labelcolor": "#f5f0e8",
            "text.color": "#f5f0e8",
            "xtick.color": "#b8c0cc",
            "ytick.color": "#b8c0cc",
            "grid.color": "#2a303a",
            "font.size": 9,
        }
    )


def _label(navigation_mode: str, mission_mode: str) -> str:
    return f"{navigation_mode}\n{mission_mode}"


def plot_success_rate(summary: pd.DataFrame, output_dir: Path) -> Path | None:
    if summary.empty or "success_rate" not in summary:
        return None
    _style()
    labels = [
        _label(row.navigation_mode, row.mission_mode)
        for row in summary.itertuples()
    ]
    values = summary["success_rate"].to_numpy(dtype=float)
    lower = values - summary.get("success_ci_low", summary["success_rate"]).to_numpy(dtype=float)
    upper = summary.get("success_ci_high", summary["success_rate"]).to_numpy(dtype=float) - values
    colors = [PALETTE.get(mode, "#d2b48c") for mode in summary["navigation_mode"]]
    fig, axis = plt.subplots(figsize=(max(7, len(labels) * 1.2), 4.5))
    axis.bar(
        range(len(labels)),
        values * 100.0,
        color=colors,
        edgecolor="#f5f0e8",
        linewidth=0.4,
        yerr=np.vstack([lower * 100.0, upper * 100.0]),
        capsize=3,
    )
    axis.set_xticks(range(len(labels)))
    axis.set_xticklabels(labels, fontsize=7)
    axis.set_ylabel("Mission success rate [%]")
    axis.set_ylim(0, 105)
    axis.set_title("Mission success by navigation variant and task mode")
    axis.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = output_dir / "plots" / "success_rate.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def plot_time_series(steps: pd.DataFrame, output_dir: Path) -> list[Path]:
    if steps.empty:
        return []
    _style()
    metrics = [
        ("mean_battery", "Mean battery [%]"),
        ("mean_stress", "Mean stress [0..100]"),
        ("coverage_discovered", "Discovered coverage [fraction]"),
    ]
    paths: list[Path] = []
    for metric, ylabel in metrics:
        if metric not in steps:
            continue
        fig, axis = plt.subplots(figsize=(8, 4.5))
        for (mode, mission), group in steps.groupby(
            ["navigation_mode", "mission_mode"], dropna=False
        ):
            if metric not in group:
                continue
            curve = (
                group.groupby("step")[metric]
                .agg(["mean", "std", "count"])
                .reset_index()
            )
            sem = curve["std"].fillna(0.0) / np.sqrt(curve["count"].clip(lower=1))
            axis.plot(
                curve["step"],
                curve["mean"],
                label=f"{mode} / {mission}",
                color=PALETTE.get(mode, "#d2b48c"),
                linewidth=1.4,
            )
            axis.fill_between(
                curve["step"],
                curve["mean"] - 1.96 * sem,
                curve["mean"] + 1.96 * sem,
                color=PALETTE.get(mode, "#d2b48c"),
                alpha=0.12,
            )
        axis.set_xlabel("Simulation step")
        axis.set_ylabel(ylabel)
        axis.set_title(ylabel + " over time")
        axis.grid(alpha=0.25)
        axis.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        path = output_dir / "plots" / f"{metric}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=300)
        plt.close(fig)
        paths.append(path)
    return paths


def _terrain_background(
    config: SimulationConfig, seed: int
) -> tuple[np.ndarray, list[list[str]]]:
    terrain_config = replace(
        config,
        seed=int(seed),
        num_rovers=0,
        navigation_mode="scaffold",
        mission_mode="exploration",
        targets=None,
    )
    model = MarsSimulation(config=terrain_config)
    image = np.zeros((config.height, config.width, 3))
    types: list[list[str]] = []
    for y in range(config.height):
        row: list[str] = []
        for x in range(config.width):
            terrain = model.terrain_at((x, y))
            color = terrain.color if terrain is not None else "#808080"
            image[y, x] = mcolors.to_rgb(color)
            row.append(terrain.terrain_type.value if terrain is not None else "None")
        types.append(row)
    return image, types


def plot_sample_trajectories(
    results: Sequence[EpisodeResult],
    config: SimulationConfig,
    output_dir: Path,
) -> Path | None:
    if not results:
        return None
    sample: dict[tuple[str, str], EpisodeResult] = {}
    for result in results:
        key = (result.navigation_mode, result.mission_mode)
        sample.setdefault(key, result)
    if not sample:
        return None

    modes = sorted({key[0] for key in sample})
    missions = sorted({key[1] for key in sample})
    _style()
    fig, axes = plt.subplots(
        len(missions),
        len(modes),
        figsize=(4.2 * len(modes), 4.0 * len(missions)),
        squeeze=False,
    )
    for row, mission in enumerate(missions):
        for column, mode in enumerate(modes):
            axis = axes[row][column]
            episode = sample.get((mode, mission))
            if episode is None:
                axis.set_axis_off()
                continue
            image, _ = _terrain_background(config, episode.seed)
            axis.imshow(image, origin="lower", interpolation="nearest")
            for path in episode.trajectory.values():
                if not path:
                    continue
                xs = [position[0] for position in path]
                ys = [position[1] for position in path]
                axis.plot(
                    xs,
                    ys,
                    color=PALETTE.get(mode, "#f2c28f"),
                    linewidth=1.2,
                    alpha=0.9,
                )
                axis.scatter([xs[0]], [ys[0]], marker="o", s=18, color="#ffffff")
                axis.scatter([xs[-1]], [ys[-1]], marker="x", s=24, color="#ff6b5f")
            axis.set_title(f"{mode}\n{mission} · seed {episode.seed}", fontsize=8)
            axis.set_xlim(-0.5, config.width - 0.5)
            axis.set_ylim(-0.5, config.height - 0.5)
            axis.set_xticks([])
            axis.set_yticks([])
    fig.suptitle("Example trajectories on the same Mars terrain", fontsize=11)
    fig.tight_layout()
    path = output_dir / "plots" / "sample_trajectories.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def plot_fear_activity(summary: pd.DataFrame, output_dir: Path) -> Path | None:
    if summary.empty:
        return None
    _style()
    labels = [
        _label(row.navigation_mode, row.mission_mode)
        for row in summary.itertuples()
    ]
    own = summary.get("fear_events_own_mean", pd.Series(0, index=summary.index))
    received = summary.get(
        "fear_events_received_mean", pd.Series(0, index=summary.index)
    )
    entries = summary.get(
        "fear_entries_total_mean", pd.Series(0, index=summary.index)
    )
    positions = np.arange(len(labels))
    width = 0.26
    fig, axis = plt.subplots(figsize=(max(7, len(labels) * 1.2), 4.5))
    axis.bar(positions - width, own, width, label="own imprints", color="#f2a65a")
    axis.bar(positions, received, width, label="radio fears", color="#8fb8ff")
    axis.bar(positions + width, entries, width, label="feared entries", color="#ff6b5f")
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, fontsize=7)
    axis.set_ylabel("Mean count per episode")
    axis.set_title("Anxiety activity")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(fontsize=8)
    fig.tight_layout()
    path = output_dir / "plots" / "fear_activity.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def plot_all(
    results: Sequence[EpisodeResult],
    steps: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path,
    config: SimulationConfig,
) -> list[Path]:
    output_dir = Path(output_dir)
    paths: list[Path] = []
    for plotter in (
        lambda: plot_success_rate(summary, output_dir),
        lambda: plot_fear_activity(summary, output_dir),
        lambda: plot_sample_trajectories(results, config, output_dir),
    ):
        try:
            path = plotter()
            if path is not None:
                paths.append(path)
        except (ValueError, RuntimeError):
            # A missing/unsupported plot must not invalidate the raw results.
            continue
    paths.extend(plot_time_series(steps, output_dir))
    return paths


__all__ = [
    "plot_all",
    "plot_fear_activity",
    "plot_sample_trajectories",
    "plot_success_rate",
    "plot_time_series",
]
