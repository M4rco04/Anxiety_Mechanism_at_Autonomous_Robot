"""Wiktor's comparative experiment runner."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from config.config import SimulationConfig
from src.analytics.benchmark import BenchmarkManager, ExperimentSpec
from src.analytics.reporting import print_summary
from src.navigation.registry import available_strategies


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run paired Monte Carlo experiments for the Mars rover."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["online", "emotional", "swarm_emotional"],
        choices=("scaffold", "online", "emotional", "swarm_emotional"),
    )
    parser.add_argument(
        "--mission-modes",
        nargs="+",
        default=["exploration", "goal_navigation"],
        choices=("exploration", "goal_navigation"),
    )
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--width", type=int, default=50)
    parser.add_argument("--height", type=int, default=50)
    parser.add_argument("--rovers", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a non-scientific scaffold pipeline check only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    config = (
        SimulationConfig.load(args.config)
        if args.config is not None
        else SimulationConfig()
    )
    config = replace(
        config,
        width=args.width,
        height=args.height,
        num_rovers=args.rovers,
        max_steps=args.max_steps,
        exploration_budget=min(config.exploration_budget, args.max_steps),
        targets=None,
    )
    config.validate()

    if args.smoke:
        variants = ["scaffold"]
        mission_modes = ["exploration"]
        seed_count = min(max(1, args.seed_count), 3)
        output = args.output or Path("results") / "smoke"
        print("PIPELINE SMOKE TEST — SCAFFOLD NAVIGATION — NOT SCIENTIFIC")
    else:
        variants = list(args.variants)
        mission_modes = list(args.mission_modes)
        seed_count = args.seed_count
        output = args.output or Path("results") / "main"

    metadata = available_strategies()
    missing = [
        variant
        for variant in variants
        if not metadata.get(variant, {}).get("implemented", False)
    ]
    if missing and not args.smoke:
        print(
            "The following navigation strategies are not implemented yet: "
            f"{', '.join(missing)}.\n"
            "Use --smoke for a pipeline check, or wait for TODO(Karol).",
            file=sys.stderr,
        )
        return 2

    specs = [
        ExperimentSpec(navigation_mode=variant, mission_mode=mission)
        for variant in variants
        for mission in mission_modes
    ]
    manager = BenchmarkManager(config)
    path = manager.run_comparative_batch(
        specs,
        iterations=seed_count,
        output_dir=output,
        workers=max(1, args.workers),
        base_seed=args.base_seed,
    )
    import pandas as pd

    summary = pd.read_csv(path / "summary.csv")
    print_summary(summary)
    print(f"\nResults: {path}")
    print(f"Report:  {path / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
