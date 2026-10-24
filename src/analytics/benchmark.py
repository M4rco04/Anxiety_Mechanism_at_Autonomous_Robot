"""Monte Carlo benchmark manager (Wiktor's experiment layer)."""

from __future__ import annotations

import json
import math
import platform
import subprocess
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.config import SimulationConfig
from src.analytics.metrics import (
    collect_episode_metrics,
    collect_rover_metrics,
    model_step_rows,
    rover_step_rows,
)
from src.analytics.results import EpisodeResult
from src.model.model import MarsSimulation
from src.navigation.registry import available_strategies


@dataclass(frozen=True)
class ExperimentSpec:
    navigation_mode: str
    mission_mode: str


@dataclass(frozen=True)
class _Task:
    config: SimulationConfig
    navigation_mode: str
    mission_mode: str
    seed: int
    collect_steps: bool


def run_episode(
    config: SimulationConfig,
    *,
    navigation_mode: str,
    mission_mode: str,
    seed: int,
    collect_steps: bool = True,
    collect_agents: bool = True,
) -> EpisodeResult:
    """Run one deterministic episode and return serializable results."""

    episode_config = replace(
        config,
        seed=int(seed),
        navigation_mode=navigation_mode,
        mission_mode=mission_mode,
        targets=None if mission_mode == "exploration" else config.targets,
    )
    start = time.perf_counter()
    model = MarsSimulation(config=episode_config)
    while model.running and model.step_count < episode_config.max_steps:
        model.step()
    wall_clock = time.perf_counter() - start

    metrics = collect_episode_metrics(model)
    rovers = [collect_rover_metrics(rover) for rover in model.rovers()]
    strategy_info = available_strategies().get(navigation_mode, {})
    is_scientific = bool(
        strategy_info.get("scientific", False)
        and strategy_info.get("implemented", False)
        and navigation_mode != "scaffold"
    )

    return EpisodeResult(
        config=episode_config.to_dict(),
        seed=int(seed),
        navigation_mode=navigation_mode,
        mission_mode=mission_mode,
        is_scientific=is_scientific,
        metrics=metrics,
        rovers=rovers,
        trajectory={rover.unique_id: list(rover.path) for rover in model.rovers()},
        terrain_hash=model.terrain_hash(),
        termination_reason=model.termination_reason,
        steps=model_step_rows(model) if collect_steps else [],
        agent_steps=rover_step_rows(model) if collect_agents else [],
        wall_clock_s=wall_clock,
    )


def _run_task(task: _Task) -> EpisodeResult:
    return run_episode(
        task.config,
        navigation_mode=task.navigation_mode,
        mission_mode=task.mission_mode,
        seed=task.seed,
        collect_steps=task.collect_steps,
    )


class BenchmarkManager:
    """Runs paired Monte Carlo episodes and writes a reproducible result set."""

    def __init__(self, base_config: SimulationConfig | None = None) -> None:
        self.base_config = base_config or SimulationConfig()

    def run_comparative_batch(
        self,
        specs: Sequence[ExperimentSpec],
        iterations: int,
        output_dir: str | Path,
        *,
        workers: int = 1,
        base_seed: int = 0,
        collect_steps: bool = True,
    ) -> Path:
        if iterations <= 0:
            raise ValueError("iterations must be positive")
        specs = list(specs)
        if not specs:
            raise ValueError("At least one experiment spec is required")

        # Fail before launching workers if a strategy is unfinished.
        metadata = available_strategies()
        for spec in specs:
            info = metadata.get(spec.navigation_mode)
            if info is None:
                raise ValueError(f"Unknown navigation mode: {spec.navigation_mode}")
            if not info["implemented"]:
                raise NotImplementedError(
                    f"Navigation mode {spec.navigation_mode!r} is not implemented. "
                    "Use --smoke for scaffold-only pipeline checks."
                )

        output_path = self._prepare_output_dir(output_dir)
        seeds = [int(base_seed) + index for index in range(iterations)]
        tasks = [
            _Task(
                config=self.base_config,
                navigation_mode=spec.navigation_mode,
                mission_mode=spec.mission_mode,
                seed=seed,
                collect_steps=collect_steps,
            )
            for seed in seeds
            for spec in specs
        ]

        results: list[EpisodeResult] = []
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_run_task, task) for task in tasks]
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for task in tasks:
                results.append(_run_task(task))

        results.sort(key=lambda item: (item.seed, item.mission_mode, item.navigation_mode))
        episodes = pd.DataFrame([result.to_row() for result in results])
        steps = self._steps_frame(results)
        agent_steps = self._agent_steps_frame(results)
        summary = summarize_episodes(episodes)
        paired = paired_comparisons(episodes)

        episodes.to_csv(output_path / "episodes.csv", index=False)
        if not steps.empty:
            steps.to_csv(output_path / "steps.csv", index=False)
        if not agent_steps.empty:
            agent_steps.to_csv(output_path / "agent_steps.csv", index=False)
        summary.to_csv(output_path / "summary.csv", index=False)
        (output_path / "summary.json").write_text(
            summary.to_json(orient="records", indent=2),
            encoding="utf-8",
        )
        if not paired.empty:
            paired.to_csv(output_path / "paired_tests.csv", index=False)

        self._write_metadata(output_path, results, seeds, specs)
        from src.analytics.plots import plot_all
        from src.analytics.reporting import write_report

        plot_all(results, steps, summary, output_path, self.base_config)
        write_report(
            output_path,
            self.base_config,
            results,
            summary,
            paired,
            episodes,
        )
        return output_path

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------
    def _prepare_output_dir(self, output_dir: str | Path) -> Path:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _steps_frame(results: Iterable[EpisodeResult]) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for result in results:
            if not result.steps:
                continue
            frame = pd.DataFrame(result.steps)
            frame.insert(0, "seed", result.seed)
            frame.insert(1, "navigation_mode", result.navigation_mode)
            frame.insert(2, "mission_mode", result.mission_mode)
            frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @staticmethod
    def _agent_steps_frame(results: Iterable[EpisodeResult]) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for result in results:
            if not result.agent_steps:
                continue
            frame = pd.DataFrame(result.agent_steps)
            frame.insert(0, "seed", result.seed)
            frame.insert(1, "navigation_mode", result.navigation_mode)
            frame.insert(2, "mission_mode", result.mission_mode)
            frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _write_metadata(
        self,
        output_path: Path,
        results: Sequence[EpisodeResult],
        seeds: Sequence[int],
        specs: Sequence[ExperimentSpec],
    ) -> None:
        config_data = self.base_config.to_dict()
        config_data["config_hash"] = self.base_config.config_hash()
        (output_path / "config.json").write_text(
            json.dumps(config_data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        environment = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": _package_versions(),
            "git_commit": _git_commit(),
            "seeds": list(seeds),
            "specs": [spec.__dict__ for spec in specs],
            "episodes": len(results),
            "scientific": all(result.is_scientific for result in results),
        }
        (output_path / "environment.json").write_text(
            json.dumps(environment, indent=2, sort_keys=True),
            encoding="utf-8",
        )


# ----------------------------------------------------------------------
# Summary and paired statistics
# ----------------------------------------------------------------------
def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 1.0)
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
        / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def summarize_episodes(episodes: pd.DataFrame) -> pd.DataFrame:
    if episodes.empty:
        return pd.DataFrame()
    group_columns = ["navigation_mode", "mission_mode"]
    rows: list[dict[str, Any]] = []
    for keys, group in episodes.groupby(group_columns, dropna=False):
        row: dict[str, Any] = dict(zip(group_columns, keys))
        row["n"] = len(group)
        row["is_scientific"] = bool(group["is_scientific"].all())
        successes = int(group["mission_success"].astype(bool).sum())
        low, high = wilson_interval(successes, len(group))
        row["success_rate"] = successes / len(group)
        row["success_ci_low"] = low
        row["success_ci_high"] = high
        numeric = group.select_dtypes(include=[np.number]).columns
        for column in numeric:
            if column in {"seed"}:
                continue
            values = group[column].astype(float)
            mean = float(values.mean())
            std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
            ci = 1.96 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
            row[f"{column}_mean"] = mean
            row[f"{column}_std"] = std
            row[f"{column}_ci95"] = ci
        rows.append(row)
    return pd.DataFrame(rows).sort_values(group_columns).reset_index(drop=True)


def paired_comparisons(
    episodes: pd.DataFrame,
    *,
    baseline: str = "online",
    metrics: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Paired by seed comparisons against the online baseline."""

    if episodes.empty:
        return pd.DataFrame()
    metrics = list(
        metrics
        or [
            "mission_success",
            "coverage_discovered",
            "mean_battery",
            "mean_stress",
            "fear_entries_total",
            "destroyed",
            "collisions",
        ]
    )
    rows: list[dict[str, Any]] = []
    for mission_mode, mode_frame in episodes.groupby("mission_mode", dropna=False):
        if baseline not in set(mode_frame["navigation_mode"]):
            continue
        for variant in sorted(
            set(mode_frame["navigation_mode"]) - {baseline}
        ):
            left = mode_frame[mode_frame["navigation_mode"] == baseline].set_index(
                "seed"
            )
            right = mode_frame[mode_frame["navigation_mode"] == variant].set_index(
                "seed"
            )
            common = left.index.intersection(right.index)
            if len(common) < 2:
                continue
            for metric in metrics:
                if metric not in left.columns or metric not in right.columns:
                    continue
                a = left.loc[common, metric].astype(float)
                b = right.loc[common, metric].astype(float)
                differences = b - a
                if differences.abs().sum() == 0:
                    p_value = 1.0
                else:
                    try:
                        from scipy.stats import wilcoxon

                        p_value = float(
                            wilcoxon(
                                a.to_numpy(),
                                b.to_numpy(),
                                zero_method="wilcox",
                            ).pvalue
                        )
                    except (ImportError, ValueError):
                        p_value = float("nan")
                std = float(differences.std(ddof=1)) if len(differences) > 1 else 0.0
                effect = (
                    float(differences.mean()) / std if std > 0 else 0.0
                )
                rows.append(
                    {
                        "mission_mode": mission_mode,
                        "baseline": baseline,
                        "variant": variant,
                        "metric": metric,
                        "n_pairs": len(common),
                        "baseline_mean": float(a.mean()),
                        "variant_mean": float(b.mean()),
                        "mean_difference": float(differences.mean()),
                        "cohens_dz": effect,
                        "wilcoxon_p": p_value,
                    }
                )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        # Holm correction within each mission mode/metric family.
        frame["p_holm"] = np.nan
        for (mission_mode, metric), group in frame.groupby(
            ["mission_mode", "metric"]
        ):
            ordered = group.sort_values("wilcoxon_p")
            m = len(ordered)
            adjusted = []
            previous = 0.0
            for rank, (_, row) in enumerate(ordered.iterrows()):
                value = min(1.0, (m - rank) * row["wilcoxon_p"])
                previous = max(previous, value)
                adjusted.append(previous)
            frame.loc[ordered.index, "p_holm"] = adjusted
    return frame


# ----------------------------------------------------------------------
# Environment metadata
# ----------------------------------------------------------------------
def _package_versions() -> dict[str, str]:
    packages = {}
    for name in ("mesa", "numpy", "pandas", "matplotlib", "scipy"):
        try:
            module = __import__(name)
            packages[name] = getattr(module, "__version__", "unknown")
        except ImportError:
            packages[name] = "not installed"
    return packages


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


__all__ = [
    "BenchmarkManager",
    "ExperimentSpec",
    "paired_comparisons",
    "run_episode",
    "summarize_episodes",
    "wilson_interval",
]
