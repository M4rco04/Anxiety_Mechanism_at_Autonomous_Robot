"""Figures for ``root/study.py``.

Colour = variant family, always the same: blue = plain algorithm, orange =
anxiety mechanism, aqua = swarm (first three validated dark-mode slots).
Conditions within a family are told apart by their axis labels, never by
extra hues.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analytics.analysis_plots import TEXT, TEXT_MUTED, VARIANT_COLORS, _save, _style

BLUE, ORANGE, AQUA, VIOLET = VARIANT_COLORS


def _family_color(condition: str) -> str:
    name = condition.lower()
    if name.startswith("swarm"):
        return AQUA
    if name.startswith("fuzzy"):
        return VIOLET
    if name.startswith("plain") or "plain" in name:
        return BLUE
    return ORANGE


def _bars(axis, labels, values, lows, highs, colors, percent=True, horizontal=False):
    scale = 100 if percent else 1
    values = np.asarray(values, float) * scale
    err = np.vstack([values - np.asarray(lows, float) * scale, np.asarray(highs, float) * scale - values])
    positions = np.arange(len(labels))
    if horizontal:
        axis.barh(positions, values, height=0.62, color=colors, zorder=2)
        axis.errorbar(values, positions, xerr=err, fmt="none", ecolor=TEXT_MUTED, capsize=3, lw=1, zorder=3)
        for y, v, hi in zip(positions, values, np.asarray(highs, float) * scale):
            axis.text(hi + (2 if percent else 0.5), y, f"{v:.0f}%" if percent else f"{v:.1f}",
                      va="center", color=TEXT, fontsize=8)
        axis.set_yticks(positions, labels)
        axis.invert_yaxis()
        axis.grid(axis="x", alpha=0.5, zorder=0)
    else:
        axis.bar(positions, values, width=0.62, color=colors, zorder=2)
        axis.errorbar(positions, values, yerr=err, fmt="none", ecolor=TEXT_MUTED, capsize=3, lw=1, zorder=3)
        for x, v, hi in zip(positions, values, np.asarray(highs, float) * scale):
            axis.text(x, hi + (2 if percent else 0.8), f"{v:.0f}%" if percent else f"{v:.1f}",
                      ha="center", va="bottom", color=TEXT, fontsize=8)
        axis.set_xticks(positions, labels, rotation=20, ha="right")
        axis.grid(axis="y", alpha=0.5, zorder=0)


def plot_swarm_controls(rates: pd.DataFrame, path: Path) -> Path:
    _style()
    explore = rates[rates["test"] == "exploration"]
    goal = rates[rates["test"] == "goal_navigation"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    labels = list(explore["condition"])
    colors = [_family_color(c) for c in labels]
    _bars(axes[0], labels, explore["survival_rate"], explore["survival_ci_low"], explore["survival_ci_high"], colors)
    axes[0].set_ylim(0, 112)
    axes[0].set_title("Exploration: rover survival [%]", loc="left")
    sem = explore["terrain_discovered_sem"] * 1.96
    _bars(axes[1], labels, explore["terrain_discovered_mean"], explore["terrain_discovered_mean"] - sem,
          explore["terrain_discovered_mean"] + sem, colors, percent=False)
    axes[1].set_title("Exploration: terrain discovered [%]", loc="left")
    axes[1].set_ylim(0, max(explore["terrain_discovered_mean"] + sem) * 1.18)
    _bars(axes[2], list(goal["condition"]), goal["route_completed_rate"], goal["route_completed_ci_low"],
          goal["route_completed_ci_high"], colors)
    axes[2].set_ylim(0, 112)
    axes[2].set_title("Goal navigation: route completed [%]", loc="left")
    fig.suptitle("Swarm controls (per rover, 95% CI; blue = plain, orange = anxiety, aqua = swarm)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def plot_ablation(rates: pd.DataFrame, path: Path) -> Path:
    _style()
    conditions = list(dict.fromkeys(rates["condition"]))
    colors = [BLUE if "plain" in c.lower() else ORANGE if c == "Full model" else "#a8532f" for c in conditions]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for axis, test, column, title in (
        (axes[0], "exploration", "survival", "Exploration: rover survival [%]"),
        (axes[1], "goal_navigation", "route_completed", "Goal navigation: route completed [%]"),
    ):
        sub = rates[rates["test"] == test].set_index("condition").loc[conditions]
        _bars(axis, conditions, sub[f"{column}_rate"], sub[f"{column}_ci_low"], sub[f"{column}_ci_high"],
              colors, horizontal=True)
        full = sub.loc["Full model", f"{column}_rate"] * 100
        axis.axvline(full, color=ORANGE, ls=":", lw=1.2)
        axis.set_xlim(0, 112)
        axis.set_title(title, loc="left")
    fig.suptitle("Ablations of the anxiety model (single rover, 95% CI; dotted = full model)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def plot_sensitivity(rates: pd.DataFrame, parameters: Mapping[str, tuple], path: Path) -> Path:
    _style()
    plain = rates[rates["condition"] == "plain"]
    fig, axes = plt.subplots(2, len(parameters), figsize=(5 * len(parameters), 7), sharey=True)
    rows = (("exploration", "survival", "Exploration: survival [%]"),
            ("goal_navigation", "route_completed", "Goal: route completed [%]"))
    for col, (parameter, (label, values, default)) in enumerate(parameters.items()):
        for row, (test, column, ylabel) in enumerate(rows):
            axis = axes[row][col]
            sub = rates[(rates["condition"] == parameter) & (rates["test"] == test)].sort_values("value")
            x = np.arange(len(sub))
            axis.plot(x, sub[f"{column}_rate"] * 100, color=ORANGE, lw=2, marker="o", ms=5, label="Anxiety")
            axis.fill_between(x, sub[f"{column}_ci_low"] * 100, sub[f"{column}_ci_high"] * 100,
                              color=ORANGE, alpha=0.15, lw=0)
            ref = plain[plain["test"] == test].iloc[0]
            axis.axhline(ref[f"{column}_rate"] * 100, color=BLUE, ls="--", lw=1.5, label="Plain (reference)")
            axis.axhspan(ref[f"{column}_ci_low"] * 100, ref[f"{column}_ci_high"] * 100, color=BLUE, alpha=0.08)
            if default in list(sub["value"]):
                axis.axvline(list(sub["value"]).index(default), color=TEXT_MUTED, ls=":", lw=1)
            axis.set_xticks(x, [f"{v:g}" for v in sub["value"]])
            axis.set_ylim(0, 105)
            axis.grid(alpha=0.5)
            if row == 0:
                axis.set_title(label, loc="left")
            if row == 1:
                axis.set_xlabel("value (dotted = default)")
            if col == 0:
                axis.set_ylabel(ylabel)
    axes[0][0].legend(frameon=False, loc="upper right")
    fig.suptitle("Sensitivity of the anxiety rover (95% CI)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def plot_noise(rates: pd.DataFrame, path: Path) -> Path:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for condition in dict.fromkeys(rates["condition"]):
        sub = rates[rates["condition"] == condition].sort_values("value")
        color = _family_color(condition)
        axes[0].plot(sub["value"], sub["survival_rate"] * 100, color=color, lw=2, marker="o", ms=5, label=condition)
        axes[0].fill_between(sub["value"], sub["survival_ci_low"] * 100, sub["survival_ci_high"] * 100,
                             color=color, alpha=0.15, lw=0)
        axes[1].plot(sub["value"], sub["fears_per_rover_mean"], color=color, lw=2, marker="o", ms=5, label=condition)
    axes[0].set_ylim(0, 105)
    axes[0].set_title("Exploration: rover survival [%]", loc="left")
    axes[1].set_title("Remembered dangerous terrains per rover", loc="left")
    axes[1].set_ylim(bottom=0)
    for axis in axes:
        axis.set_xlabel("Camera RGB noise σ (per channel)")
        axis.grid(alpha=0.5)
    axes[0].legend(frameon=False)
    fig.suptitle("Effect of camera noise (band = 95% CI)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


__all__ = ["plot_ablation", "plot_noise", "plot_sensitivity", "plot_swarm_controls"]

