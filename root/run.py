"""Single-episode headless launcher.

Marek owns the final interactive/presentation orchestration.  This runner
already uses the public ``SimulationSession`` contract so a web or desktop
front-end can replace the print loop without touching the simulation core.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from config.config import SimulationConfig
from src.simulation.session import SimulationSession, snapshot_to_dict


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Mars rover anxiety episode headlessly."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=50)
    parser.add_argument("--height", type=int, default=50)
    parser.add_argument("--rovers", type=int, default=3)
    parser.add_argument(
        "--navigation-mode",
        choices=("scaffold", "online", "emotional", "swarm_emotional"),
        default="scaffold",
    )
    parser.add_argument(
        "--mission-mode",
        choices=("exploration", "goal_navigation"),
        default="exploration",
    )
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
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
        seed=args.seed,
        width=args.width,
        height=args.height,
        num_rovers=args.rovers,
        navigation_mode=args.navigation_mode,
        mission_mode=args.mission_mode,
        targets=None if args.mission_mode == "exploration" else config.targets,
    )
    config.validate()

    # TODO(Marek): final presentation orchestration and mission presets.
    # Keep this CLI contract stable; the session/API/viewer are ready.
    try:
        session = SimulationSession(config)
        snapshot = session.run(max_steps=args.max_steps)
    except NotImplementedError as error:
        print(str(error), file=sys.stderr)
        return 2

    print(
        f"seed={snapshot.seed} step={snapshot.step} "
        f"mode={snapshot.navigation_mode}/{snapshot.mission_mode} "
        f"scientific={snapshot.is_scientific}"
    )
    print(
        f"termination={snapshot.termination_reason} "
        f"coverage={snapshot.metrics.get('coverage_discovered', 0):.3f} "
        f"success={snapshot.metrics.get('mission_success')}"
    )
    for rover in snapshot.rovers:
        print(
            f"R{rover.rover_id} pos={rover.position} "
            f"battery={rover.battery:5.1f} stress={rover.stress_level:5.1f} "
            f"wheel={rover.wheel_condition:5.1f} hull={rover.hull_condition:5.1f} "
            f"status={rover.mission_status:16s} fear={rover.fear_records}"
        )

    output = args.output or Path("results") / f"single_seed_{snapshot.seed}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "episode.json").write_text(
        json.dumps(snapshot_to_dict(snapshot), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {output / 'episode.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
