"""Grid search of the anxiety parameters on calibration seeds (``uv run tune``).

Runs the anxious rover (1 rover) on both real maps and both tests for every
combination of ``S_crit``, ``fear_weight`` and ``alpha_safe`` on seeds
``--base-seed`` .. (default 0-99). The held-out maps of ``uv run study``
(seeds 1000+) are never used here. Score per map = mean of exploration
survival, exploration terrain discovered and goal route completion; the
total score is the mean over the maps. Writes ``results/tuning/``.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from config.config import HomeostatConfig, SimulationConfig

GRID = {
    "s_crit": (30.0, 40.0, 50.0),
    "fear_weight": (20.0, 30.0, 50.0),
    "alpha_safe": (18.0, 20.0, 22.0),
}
MAPS = ("mars", "atacama")
TESTS = ("exploration", "goal_navigation")


def _run(task: tuple) -> dict:
    from src.environment.terrain import SafeRegolith
    from src.model.model import MarsSimulation
    from src.model.types import hex_to_rgb

    s_crit, fear_weight, alpha_safe, map_source, test, seed, max_steps = task
    config = SimulationConfig(
        seed=seed,
        num_rovers=1,
        navigation_mode="emotional",
        mission_mode=test,
        map_source=map_source,
        max_steps=max_steps,
        exploration_budget=max_steps,
        fear_weight=fear_weight,
        homeostat=HomeostatConfig(s_crit=s_crit, alpha_safe=alpha_safe),
    )
    model = MarsSimulation(config)
    while model.running and model.step_count < max_steps:
        model.step()
    rover = model.rovers()[0]
    reached = rover.waypoints_reached + int(rover.mission_status == "goal_reached")
    fears_safe = rover.fear_intensity(hex_to_rgb(SafeRegolith.color)) > 0.0
    return {
        "s_crit": s_crit,
        "fear_weight": fear_weight,
        "alpha_safe": alpha_safe,
        "map": map_source,
        "test": test,
        "seed": seed,
        "survived": not rover.is_destroyed,
        "discovered": model.coverage()[1],
        "route_completed": reached >= config.goal_waypoints,
        "fears_safe": fears_safe,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--runs", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--output", type=Path, default=Path("results") / "tuning")
    args = parser.parse_args(argv)

    seeds = range(args.base_seed, args.base_seed + args.runs)
    tasks = [
        (*combo, m, t, s, args.max_steps)
        for combo in itertools.product(*GRID.values())
        for m in MAPS
        for t in TESTS
        for s in seeds
    ]
    print(f"Running {len(tasks)} simulations on calibration seeds {seeds.start}-{seeds.stop - 1} ...")
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        rows = list(executor.map(_run, tasks, chunksize=8))
    frame = pd.DataFrame(rows)
    keys = list(GRID)
    expl = frame[frame.test == "exploration"].groupby(keys + ["map"]).agg(
        survival=("survived", "mean"), discovered=("discovered", "mean"),
        fears_safe_expl=("fears_safe", "mean"),
    )
    goal = frame[frame.test == "goal_navigation"].groupby(keys + ["map"]).agg(
        route_completed=("route_completed", "mean"), fears_safe_goal=("fears_safe", "mean"),
    )
    per_map = expl.join(goal).reset_index()
    per_map["score"] = per_map[["survival", "discovered", "route_completed"]].mean(axis=1)
    total = per_map.groupby(keys)["score"].mean().rename("score").reset_index()
    total = total.sort_values("score", ascending=False)

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "episodes.csv", index=False)
    per_map.to_csv(out / "per_map.csv", index=False, float_format="%.4f")
    total.to_csv(out / "grid.csv", index=False, float_format="%.4f")
    best = total.iloc[0]
    lines = [
        "# Parameter tuning (calibration seeds)",
        "",
        (f"Anxious rover ×1, seeds {seeds.start}–{seeds.stop - 1}, maps {', '.join(MAPS)}, "
        f"{len(tasks)} simulations ({(time.perf_counter() - start) / 60:.1f} min). "
        "Score = mean over maps of (exploration survival + terrain discovered + goal route completion) / 3."),
        "",
        (f"Best: S_crit = {best.s_crit:g}, fear_weight = {best.fear_weight:g}, "
        f"alpha_safe = {best.alpha_safe:g} (score {best.score:.3f})."),
        "",
        "| S_crit | fear_weight | alpha_safe | score |",
        "|---:|---:|---:|---:|",
        *(f"| {r.s_crit:g} | {r.fear_weight:g} | {r.alpha_safe:g} | {r.score:.3f} |" for r in total.itertuples()),
        "",
        "Per map (survival and discovered: exploration; completed: goal test; fears safe = share of rovers that fear safe regolith):",
        "",
        "| S_crit | fear_weight | alpha_safe | map | survival | discovered | completed | fears safe (expl / goal) |",
        "|---:|---:|---:|---|---:|---:|---:|---:|",
        *(
            f"| {r.s_crit:g} | {r.fear_weight:g} | {r.alpha_safe:g} | {r.map} | {r.survival:.1%} | "
            f"{r.discovered:.1%} | {r.route_completed:.1%} | {r.fears_safe_expl:.0%} / {r.fears_safe_goal:.0%} |"
            for r in per_map.sort_values(keys + ["map"]).itertuples()
        ),
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12 + 10]))
    print(f"\nResults: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
