"""Markdown reports and console summaries."""

from __future__ import annotations

import json
import platform
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config.config import SimulationConfig
from src.analytics.results import EpisodeResult


def print_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        print("No results.")
        return
    columns = [
        column
        for column in (
            "navigation_mode",
            "mission_mode",
            "n",
            "success_rate",
            "coverage_discovered_mean",
            "mean_battery_mean",
            "mean_stress_mean",
            "fear_events_own_mean",
            "fear_events_received_mean",
            "destroyed_mean",
            "termination_reason",
        )
        if column in summary.columns
    ]
    print(summary[columns].to_string(index=False))


def write_report(
    output_dir: Path,
    config: SimulationConfig,
    results: Sequence[EpisodeResult],
    summary: pd.DataFrame,
    paired: pd.DataFrame,
    episodes: pd.DataFrame,
) -> Path:
    output_dir = Path(output_dir)
    scientific = bool(results) and all(result.is_scientific for result in results)
    modes = sorted({result.navigation_mode for result in results})
    missions = sorted({result.mission_mode for result in results})
    seeds = sorted({result.seed for result in results})
    generated = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "# Mars Rover Conditioned-Anxiety Experiment",
        "",
        f"Generated: `{generated}`  ",
        f"Config hash: `{config.config_hash()}`  ",
        f"Seeds: `{seeds}` ({len(seeds)} paired seeds)  ",
        f"Variants: `{', '.join(modes)}`  ",
        f"Mission modes: `{', '.join(missions)}`  ",
        f"Episodes: `{len(results)}`  ",
        "",
    ]

    if scientific:
        lines += [
            (
                "> **Scientific run.** All reported navigation modes are registered "
                "scientific strategies and all episodes were executed with paired seeds."
            ),
            "",
        ]
    else:
        lines += [
            (
                "> **PIPELINE SMOKE TEST — NOT SCIENTIFIC.** At least one episode "
                "used the scaffold strategy. These results validate the robot, "
                "metrics and visualization pipeline only; they must not be "
                "reported as evidence for or against the anxiety hypothesis."
            ),
            "",
        ]

    lines += [
        "## Method",
        "",
        (
            "The rover is a grid abstraction of the Pioneer 3-DX platform. "
            "Each rover tracks battery, wheel and hull condition, speed, exposure "
            "to shadows/dust and a homeostat stress level. A one-act imprint occurs "
            "when smoothed stress crosses `S_crit`; the current RGB signature is "
            "stored in the anxiety memory. The emotional variants add the decayed "
            "fear cost to movement evaluation. In the swarm variant, packets are "
            "delivered after all rovers act, within `R_radio` hexes."
        ),
        "",
        "Homeostat:",
        "",
        "```text",
        "S_inst = w1*dB + w2*max(0, 1 - V_act/V_target)",
        "       + w3*(exp(k*(100-hull))-1)",
        "       + w4*(exp(k*(100-wheel))-1)",
        "       + w5*max(0, slope-alpha_safe)",
        "S_new = beta*S_prev + (1-beta)*S_inst,  clamped to [0, 100]",
        "```",
        "",
        "Fear cost:",
        "",
        "```text",
        "cost_fear(signature) = fear_weight * intensity * exp(-decay * age)",
        "```",
        "",
        "## Aggregate results",
        "",
        "```text",
        summary.to_string(index=False) if not summary.empty else "No episodes",
        "```",
        "",
    ]

    if not episodes.empty:
        lines += [
            "### Episode count by condition",
            "",
            "```text",
            episodes.groupby(["navigation_mode", "mission_mode"])
            .size()
            .to_string(),
            "```",
            "",
        ]

    if not paired.empty:
        lines += [
            "## Paired comparisons",
            "",
            (
                "Paired by seed against the online baseline. `wilcoxon_p` is the "
                "raw paired test p-value; `p_holm` applies Holm correction within "
                "each mission-mode/metric family. Small samples should be treated "
                "as exploratory."
            ),
            "",
            "```text",
            paired.to_string(index=False),
            "```",
            "",
        ]

    plots_dir = output_dir / "plots"
    if plots_dir.exists():
        images = sorted(plots_dir.glob("*.png"))
        if images:
            lines += ["## Figures", ""]
            for image in images:
                lines += [
                    f"### {image.stem.replace('_', ' ').title()}",
                    "",
                    f"![{image.stem}](plots/{image.name})",
                    "",
                ]

    lines += [
        "## Limitations",
        "",
        (
            "- This is a discrete hex-grid abstraction, not a physics-level "
            "reproduction of the CoppeliaSim/V-REP experiments."
        ),
        (
            "- RGB signatures are class-level optical descriptors; real camera "
            "textures and lighting are not simulated."
        ),
        "- The scaffold strategy is not a scientific navigation algorithm.",
        (
            "- The papers motivate the mechanism; their reported percentages are "
            "not claimed to be reproduced by this grid experiment."
        ),
        "",
        "## Raw data",
        "",
        "- `episodes.csv` — one row per episode.",
        "- `steps.csv` — aggregated per-step metrics.",
        "- `agent_steps.csv` — per-rover, per-step telemetry.",
        "- `summary.csv` / `summary.json` — aggregate statistics.",
        "- `paired_tests.csv` — paired comparisons.",
        "- `environment.json` — versions, seeds and git commit.",
        "",
    ]

    path = output_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_single_episode_report(
    output_dir: Path,
    result: EpisodeResult,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "seed": result.seed,
        "navigation_mode": result.navigation_mode,
        "mission_mode": result.mission_mode,
        "scientific": result.is_scientific,
        "metrics": result.metrics,
        "rovers": result.rovers,
        "termination_reason": result.termination_reason,
        "terrain_hash": result.terrain_hash,
    }
    path = output_dir / "episode.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


__all__ = ["print_summary", "write_report", "write_single_episode_report"]
