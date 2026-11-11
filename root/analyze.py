"""Compare the rover control variants over n simulations.

Variants:
  * Plain algorithm    - ``online``,          1 rover, no anxiety
  * Anxiety mechanism  - ``emotional``,       1 rover, conditioned anxiety
  * Rover swarm        - ``swarm_emotional``, 3 rovers, anxiety shared by radio
  * Fuzzy rules        - ``fuzzy``,           1 rover, expert rules, no learning

Tests:
  1. exploration      - how much terrain is discovered and how many rovers survive,
  2. goal navigation  - how often a rover completes a route through dangerous terrain.

Every variant gets the same seeds, so all variants drive on the same maps.

Example:
    uv run analyze -n 50 --workers 4
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from config.config import HomeostatConfig, SimulationConfig
from src.analytics.benchmark import rate_interval, wilson_interval
from src.analytics.metrics import collect_episode_metrics, collect_rover_metrics
from src.model.model import MarsSimulation

VARIANTS: tuple[tuple[str, str, int], ...] = (
    ("Plain algorithm", "online", 1),
    ("Anxiety mechanism", "emotional", 1),
    ("Rover swarm", "swarm_emotional", 3),
    ("Fuzzy rules", "fuzzy", 1),
)
VARIANT_NAMES = [name for name, _, _ in VARIANTS]
TESTS: dict[str, str] = {
    "exploration": "Terrain exploration",
    "goal_navigation": "Goal navigation",
}


# ----------------------------------------------------------------------
# Running simulations
# ----------------------------------------------------------------------
def _operational(rover) -> bool:
    if rover.is_destroyed or rover.battery <= 0:
        return False
    return not (rover.is_overturned and rover.recovery_steps_left <= 0)


def _run_one(task: tuple[SimulationConfig, str, str, int, str, int]) -> dict[str, Any]:
    config, variant, navigation_mode, rovers, test, seed = task
    model = MarsSimulation(
        config=replace(
            config,
            seed=seed,
            num_rovers=rovers,
            navigation_mode=navigation_mode,
            mission_mode=test,
        )
    )
    curve: list[tuple[int, float, float, float]] = []
    while model.running and model.step_count < model.config.max_steps:
        model.step()
        operational = [r for r in model.rovers() if _operational(r)]
        stress = (
            sum(r.stress_level for r in operational) / len(operational)
            if operational
            else float("nan")
        )
        curve.append(
            (
                model.step_count,
                100.0 * len(operational) / rovers,
                stress,
                100.0 * model.coverage()[1],
            )
        )

    metrics = collect_episode_metrics(model)
    rover_rows = [collect_rover_metrics(r) for r in model.rovers()]
    survived = sum(1 for r in model.rovers() if _operational(r))
    at_goal = sum(1 for r in rover_rows if r["goal_reached"])
    episode = {
        "variant": variant,
        "algorithm": navigation_mode,
        "test": test,
        "seed": seed,
        "rovers": rovers,
        "terrain_discovered_pct": 100.0 * float(metrics["coverage_discovered"]),
        "terrain_visited_pct": 100.0 * float(metrics["coverage_visited"]),
        "rovers_survived": survived,
        "all_survived": survived == rovers,
        "rovers_destroyed": int(metrics["destroyed"]),
        "rovers_overturned": int(metrics["overturned"]),
        "overturn_recoveries": int(metrics["recoveries"]),
        "sand_stuck_events": int(metrics["stuck_events"]),
        "waypoints_reached": int(metrics["waypoints_reached"]),
        "rovers_at_goal": at_goal,
        "all_at_goal": at_goal == rovers,
        "fear_imprints": int(metrics["fear_events_own"]),
        "context_imprints": int(metrics["context_imprints"]),
        "fears_received_by_radio": int(metrics["fear_events_received"]),
        "fears_per_rover": sum(r["fear_records"] for r in rover_rows) / rovers,
        "rovers_fearing_safe_ground": int(metrics["fears_safe_ground"]),
        "charging_steps": int(metrics["charging_steps"]),
        "steps": int(metrics["steps"]),
        "end_reason": model.termination_reason,
    }
    return {"episode": episode, "curve": curve}


def _extend_curves(results: list[dict[str, Any]], max_steps: int) -> pd.DataFrame:
    """Per-step curves; the final state is carried to ``max_steps``."""

    frames = []
    for result in results:
        episode, curve = result["episode"], result["curve"]
        if not curve:
            continue
        frame = pd.DataFrame(curve, columns=["step", "operational_pct", "mean_stress", "discovered_pct"])
        last = frame.iloc[-1]
        if last["step"] < max_steps:
            tail = pd.DataFrame(
                {
                    "step": range(int(last["step"]) + 1, max_steps + 1),
                    "operational_pct": last["operational_pct"],
                    "mean_stress": float("nan"),  # finished: no stress sample
                    "discovered_pct": last["discovered_pct"],
                }
            )
            frame = pd.concat([frame, tail], ignore_index=True)
        frame["variant"] = episode["variant"]
        frame["test"] = episode["test"]
        frame["seed"] = episode["seed"]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _swarm_map_record(config: SimulationConfig, test: str, seed: int) -> dict[str, Any]:
    """Run one swarm simulation and record every rover's route and stress."""

    from src.environment.terrain import TERRAIN_COLORS

    model = MarsSimulation(
        config=replace(
            config, seed=seed, num_rovers=3, navigation_mode="swarm_emotional", mission_mode=test
        )
    )
    tracks = {
        r.unique_id: {
            "rover_id": r.unique_id,
            "positions": [r.pos],
            "stress": [r.stress_level],
            "imprints": [],
            "lost_at": None,
        }
        for r in model.rovers()
    }
    own = {r.unique_id: 0 for r in model.rovers()}
    while model.running and model.step_count < model.config.max_steps:
        model.step()
        for rover in model.rovers():
            track = tracks[rover.unique_id]
            if track["lost_at"] is not None:
                continue
            track["positions"].append(rover.pos)
            track["stress"].append(rover.stress_level)
            if rover.fear_events_own > own[rover.unique_id]:
                own[rover.unique_id] = rover.fear_events_own
                track["imprints"].append(rover.pos)
            if not _operational(rover):
                track["lost_at"] = rover.pos
    return {
        "terrain": {pos: t.terrain_type.value for pos, t in model._terrain_by_pos.items()},
        "terrain_colors": TERRAIN_COLORS,
        "tracks": list(tracks.values()),
        "test_name": TESTS[test],
        "seed": seed,
        "steps": model.step_count,
    }


# ----------------------------------------------------------------------
# Summary and statistics
# ----------------------------------------------------------------------
def summarize(episodes: pd.DataFrame, waypoints: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for test, test_name in TESTS.items():
        frame = episodes[episodes["test"] == test]
        for variant in VARIANT_NAMES:
            group = frame[frame["variant"] == variant]
            if group.empty:
                continue
            n = len(group)
            rovers_total = int(group["rovers"].sum())
            survived = int(group["rovers_survived"].sum())
            low, high = rate_interval(group["rovers_survived"], group["rovers"])
            clean = int(group["all_survived"].sum())
            clean_low, clean_high = wilson_interval(clean, n)
            row: dict[str, Any] = {
                "test_id": test,
                "test": test_name,
                "variant": variant,
                "simulations": n,
                "rovers_per_simulation": int(group["rovers"].iloc[0]),
                "rovers_survived": survived,
                "rovers_total": rovers_total,
                "rover_survival_rate": survived / rovers_total,
                "rover_survival_ci_low": low,
                "rover_survival_ci_high": high,
                "runs_without_losses_rate": clean / n,
                "runs_without_losses_ci_low": clean_low,
                "runs_without_losses_ci_high": clean_high,
                "mean_fear_imprints": float(group["fear_imprints"].mean()),
                "mean_overturn_recoveries": float(group["overturn_recoveries"].mean()),
                "mean_charging_steps": float(group["charging_steps"].mean()),
                "mean_sand_stuck_events": float(group["sand_stuck_events"].mean()),
                "mean_fears_per_rover": float(group["fears_per_rover"].mean()),
                "rovers_fearing_safe_ground": int(group["rovers_fearing_safe_ground"].sum()),
            }
            if test == "exploration":
                values = group["terrain_discovered_pct"]
                row.update(
                    terrain_discovered_mean_pct=float(values.mean()),
                    terrain_discovered_std_pct=float(values.std(ddof=1)) if n > 1 else 0.0,
                    terrain_discovered_min_pct=float(values.min()),
                    terrain_discovered_max_pct=float(values.max()),
                )
            else:
                at_goal = int(group["rovers_at_goal"].sum())
                goal_low, goal_high = rate_interval(group["rovers_at_goal"], group["rovers"])
                all_goal = int(group["all_at_goal"].sum())
                all_low, all_high = wilson_interval(all_goal, n)
                done = group[group["all_at_goal"]]
                row.update(
                    route_completed_rate=at_goal / rovers_total,
                    route_completed_ci_low=goal_low,
                    route_completed_ci_high=goal_high,
                    all_rovers_at_goal_rate=all_goal / n,
                    all_rovers_at_goal_ci_low=all_low,
                    all_rovers_at_goal_ci_high=all_high,
                    waypoints_reached_rate=group["waypoints_reached"].sum() / (waypoints * rovers_total),
                    mean_steps_completed_routes=float(done["steps"].mean()) if not done.empty else float("nan"),
                )
            rows.append(row)
    return pd.DataFrame(rows)


def significance(episodes: pd.DataFrame) -> pd.DataFrame:
    """Paired comparison of each variant with the plain algorithm.

    The same seeds give the same maps, so simulations are paired. Success /
    failure uses the exact McNemar test, discovered terrain the Wilcoxon test.
    """

    from scipy.stats import binomtest, wilcoxon

    base_name = VARIANT_NAMES[0]
    rows: list[dict[str, Any]] = []
    for test, test_name in TESTS.items():
        frame = episodes[episodes["test"] == test]
        base = frame[frame["variant"] == base_name].set_index("seed")
        if base.empty:
            continue
        measures = [("Run without losses", "all_survived", True)]
        if test == "exploration":
            measures.append(("Terrain discovered [%]", "terrain_discovered_pct", False))
        else:
            measures.insert(0, ("All rovers completed the route", "all_at_goal", True))
        for variant in VARIANT_NAMES[1:]:
            other = frame[frame["variant"] == variant].set_index("seed")
            common = base.index.intersection(other.index)
            if len(common) < 2:
                continue
            for name, column, binary in measures:
                x = base.loc[common, column].astype(float)
                y = other.loc[common, column].astype(float)
                if binary:
                    better = int(((x == 0) & (y == 1)).sum())
                    worse = int(((x == 1) & (y == 0)).sum())
                    pairs = better + worse
                    p = binomtest(min(better, worse), pairs, 0.5).pvalue if pairs else 1.0
                    base_value, other_value = f"{100 * x.mean():.1f}%", f"{100 * y.mean():.1f}%"
                    method = "McNemar (exact)"
                else:
                    p = float(wilcoxon(x, y).pvalue) if (y - x).abs().sum() > 0 else 1.0
                    base_value, other_value = f"{x.mean():.1f}", f"{y.mean():.1f}"
                    method = "Wilcoxon"
                rows.append(
                    {
                        "test": test_name,
                        "comparison": f"{variant} vs {base_name.lower()}",
                        "measure": name,
                        "plain_algorithm": base_value,
                        "variant_value": other_value,
                        "method": method,
                        "p_value": p,
                        "significant": p < 0.05,
                    }
                )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------
def _pct(rate: float, low: float, high: float) -> str:
    return f"{100 * rate:.1f}% [{100 * low:.0f}–{100 * high:.0f}]"


def _num(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "–"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _table(headers: list[str], rows: list[list[str]], right: set[int]) -> str:
    """Markdown table with padded columns (readable as plain text too)."""

    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def line(values: list[str]) -> str:
        cells = [v.rjust(w) if i in right else v.ljust(w) for i, (v, w) in enumerate(zip(values, widths))]
        return "| " + " | ".join(cells) + " |"

    divider = "|" + "|".join(
        "-" * (w + 1) + ":" if i in right else "-" * (w + 2) for i, w in enumerate(widths)
    ) + "|"
    return "\n".join([line(headers), divider, *(line(r) for r in rows)])


COLUMN_LEGEND: dict[str, dict[str, str]] = {
    "simulations.csv (one row per simulation)": {
        "variant / algorithm": "Control variant and its navigation strategy in the code.",
        "test": "exploration or goal_navigation.",
        "seed": "Random seed; the same seed = the same map and start positions.",
        "rovers": "Rovers in the simulation.",
        "terrain_discovered_pct": "Passable cells seen by the cameras/LIDAR [%].",
        "terrain_visited_pct": "Passable cells the rovers drove onto [%].",
        "rovers_survived / all_survived": "Rovers not destroyed or overturned for good at the end.",
        "rovers_destroyed": "Battery, hull or wheels reached 0.",
        "rovers_overturned": "Rovers lying overturned at the end.",
        "overturn_recoveries": "Times a rover got back on its wheels after an overturn.",
        "sand_stuck_events": "Times a rover got bogged down in loose sand (it always digs out).",
        "waypoints_reached": "Route points reached (goal test).",
        "rovers_at_goal / all_at_goal": "Rovers that completed their whole route.",
        "fear_imprints": "Alarms that imprinted a terrain as dangerous.",
        "context_imprints": "Preceding terrain from short-term memory imprinted as dangerous.",
        "fears_received_by_radio": "Danger warnings received from other rovers (swarm).",
        "fears_per_rover": "Dangerous terrains remembered per rover.",
        "rovers_fearing_safe_ground": "Rovers that fear plain safe regolith (the 'panic' of the 2025 paper).",
        "charging_steps": "Steps spent charging from the solar panels.",
        "steps / end_reason": "Simulation length and why it ended.",
    },
    "summary.csv (one row per variant and test)": {
        "rover_survival_rate (+ ci_low/high)": "Share of rovers that survived, 95% interval.",
        "runs_without_losses_rate": "Share of simulations where all rovers survived.",
        "terrain_discovered_*": "Discovered terrain: mean, standard deviation, min and max [%].",
        "route_completed_rate": "Share of rovers that completed the route (goal test).",
        "all_rovers_at_goal_rate": "Share of simulations where every rover completed its route.",
        "waypoints_reached_rate": "Share of all route points reached.",
        "mean_*": "Means per simulation.",
    },
    "significance.csv": {
        "comparison / measure": "Which variant is compared with the plain algorithm and on what.",
        "method / p_value / significant": "Paired test; significant = p < 0.05.",
    },
}


def write_report(
    path: Path,
    summary: pd.DataFrame,
    stats: pd.DataFrame,
    args: argparse.Namespace,
    plots: list[Path],
) -> Path:
    text = [
        "# Rover control variants – analysis",
        "",
        (
            f"Simulations per variant and test: **{args.runs}**, seeds {args.base_seed}–"
            f"{args.base_seed + args.runs - 1} (the same maps for every variant), map "
            f"{args.width}×{args.height}, step limit {args.max_steps}, stress threshold "
            f"S_crit = {args.s_crit:g}, solar charging {'on' if args.charging else 'off'}, "
            f"camera RGB noise σ = {args.rgb_noise:g}, route points {args.waypoints}."
        ),
        "",
        (
            "Brackets give the 95% confidence interval (Wilson; for several rovers per "
            "simulation a bootstrap over whole simulations, because rovers on one map are "
            "not independent). A rover *survived* when at the end it was not destroyed or "
            "overturned for good."
        ),
        "",
    ]
    exploration = summary[summary["test_id"] == "exploration"]
    if not exploration.empty:
        text += [
            "## Test 1: terrain exploration",
            "",
            "Terrain discovered = share of passable cells seen by the rover's (or swarm's) sensors.",
            "",
            _table(
                ["Variant", "Rovers", "Terrain discovered [%] (mean ± sd)", "Rover survival", "Runs without losses"],
                [
                    [
                        r.variant,
                        str(r.rovers_per_simulation),
                        f"{r.terrain_discovered_mean_pct:.1f} ± {r.terrain_discovered_std_pct:.1f}",
                        _pct(r.rover_survival_rate, r.rover_survival_ci_low, r.rover_survival_ci_high),
                        _pct(r.runs_without_losses_rate, r.runs_without_losses_ci_low, r.runs_without_losses_ci_high),
                    ]
                    for r in exploration.itertuples()
                ],
                {1, 2, 3, 4},
            ),
            "",
        ]
    goal = summary[summary["test_id"] == "goal_navigation"]
    if not goal.empty:
        text += [
            "## Test 2: goal navigation",
            "",
            (
                f"Every rover gets its own route of {args.waypoints} points; the way to each "
                "point crosses dangerous terrain and the fear memory is kept between legs "
                "(like the two sand pits in the 2025 experiment)."
            ),
            "",
            _table(
                ["Variant", "Rovers", "Route completed (per rover)", "Route points reached",
                 "All rovers completed", "Mean steps (completed)"],
                [
                    [
                        r.variant,
                        str(r.rovers_per_simulation),
                        _pct(r.route_completed_rate, r.route_completed_ci_low, r.route_completed_ci_high),
                        f"{100 * r.waypoints_reached_rate:.1f}%",
                        _pct(r.all_rovers_at_goal_rate, r.all_rovers_at_goal_ci_low, r.all_rovers_at_goal_ci_high),
                        _num(r.mean_steps_completed_routes),
                    ]
                    for r in goal.itertuples()
                ],
                {1, 2, 3, 4, 5},
            ),
            "",
        ]
    text += [
        "## Details (means per simulation)",
        "",
        _table(
            ["Test", "Variant", "Survived", "Fear imprints", "Fears per rover", "Fear safe ground",
             "Overturn recoveries", "Stuck in sand", "Charging steps"],
            [
                [
                    r.test,
                    r.variant,
                    f"{r.rovers_survived}/{r.rovers_total}",
                    _num(r.mean_fear_imprints),
                    _num(r.mean_fears_per_rover),
                    f"{r.rovers_fearing_safe_ground}/{r.rovers_total}",
                    _num(r.mean_overturn_recoveries),
                    _num(r.mean_sand_stuck_events),
                    _num(r.mean_charging_steps),
                ]
                for r in summary.itertuples()
            ],
            {2, 3, 4, 5, 6, 7, 8},
        ),
        "",
    ]
    if not stats.empty:
        text += [
            "## Statistical significance",
            "",
            (
                "Paired comparison with the plain algorithm (the same maps). Success/failure: "
                "exact McNemar test; discovered terrain: Wilcoxon signed-rank test. "
                "*Significant* = p < 0.05."
            ),
            "",
            _table(
                ["Test", "Comparison", "Measure", "Plain", "Variant", "Method", "p", "Significant"],
                [
                    [
                        r.test, r.comparison, r.measure, r.plain_algorithm, r.variant_value, r.method,
                        "< 0.001" if r.p_value < 0.001 else f"{r.p_value:.3f}",
                        "yes" if r.significant else "no",
                    ]
                    for r in stats.itertuples()
                ],
                {3, 4, 6},
            ),
            "",
        ]
    if plots:
        text += ["## Figures", ""]
        text += [f"![{p.stem}]({p.relative_to(path).as_posix()})" for p in plots]
        text.append("")
    text += [LEGEND_HEADING, ""]
    for title, columns in COLUMN_LEGEND.items():
        text += [f"### {title}", "", _table(["Column", "Meaning"], [[k, v] for k, v in columns.items()], set()), ""]
    report = path / "report.md"
    report.write_text("\n".join(text), encoding="utf-8")
    return report


LEGEND_HEADING = "## Column reference"


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    defaults = SimulationConfig()
    parser = argparse.ArgumentParser(
        description="Plain algorithm vs anxiety mechanism vs rover swarm."
    )
    parser.add_argument("-n", "--runs", type=int, default=30, help="Simulations per variant and test.")
    parser.add_argument("--tests", nargs="+", default=list(TESTS), choices=list(TESTS))
    parser.add_argument("--base-seed", type=int, default=0, help="First seed (map).")
    parser.add_argument("--workers", type=int, default=1, help="Parallel processes.")
    parser.add_argument("--width", type=int, default=50)
    parser.add_argument("--height", type=int, default=50)
    parser.add_argument("--max-steps", type=int, default=500, help="Step limit per simulation.")
    parser.add_argument("--waypoints", type=int, default=defaults.goal_waypoints,
                        help="Route points in the goal test.")
    parser.add_argument("--s-crit", type=float, default=HomeostatConfig().s_crit,
                        help="Stress threshold that triggers a fear imprint.")
    parser.add_argument("--charging", action=argparse.BooleanOptionalAction, default=True,
                        help="Solar charging on safe ground (--no-charging turns it off).")
    parser.add_argument("--rgb-noise", type=float, default=defaults.rgb_noise_sigma,
                        help="Camera RGB noise (std per channel); 0 = perfect recognition.")
    parser.add_argument("--map-seed", type=int, default=None,
                        help="Seed of the simulation drawn on the swarm stress map (default: base seed).")
    parser.add_argument("--no-plots", action="store_true", help="Skip the figures.")
    parser.add_argument("--output", type=Path, default=Path("results") / "analysis")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.runs <= 0:
        print("--runs must be positive", file=sys.stderr)
        return 2

    config = SimulationConfig(
        width=args.width,
        height=args.height,
        max_steps=args.max_steps,
        exploration_budget=args.max_steps,
        homeostat=HomeostatConfig(s_crit=args.s_crit),
        solar_charging=args.charging,
        rgb_noise_sigma=args.rgb_noise,
        goal_waypoints=args.waypoints,
    )
    config.validate()

    seeds = range(args.base_seed, args.base_seed + args.runs)
    tasks = [
        (config, name, mode, rovers, test, seed)
        for test in args.tests
        for name, mode, rovers in VARIANTS
        for seed in seeds
    ]
    print(f"Running {len(tasks)} simulations...")
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(_run_one, tasks, chunksize=4))
    else:
        results = []
        for index, task in enumerate(tasks, 1):
            results.append(_run_one(task))
            print(f"  {index}/{len(tasks)}", end="\r")
        print()

    episodes = pd.DataFrame([r["episode"] for r in results])
    summary = summarize(episodes, args.waypoints)
    stats = significance(episodes)

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    episodes.to_csv(output / "simulations.csv", index=False, float_format="%.3f")
    summary.drop(columns=["test_id"]).to_csv(output / "summary.csv", index=False, float_format="%.4f")
    if not stats.empty:
        stats.to_csv(output / "significance.csv", index=False, float_format="%.4g")

    plots: list[Path] = []
    if not args.no_plots:
        from src.analytics.analysis_plots import (
            plot_coverage,
            plot_rates,
            plot_swarm_stress_map,
            plot_time_series,
        )

        tests = {t: TESTS[t] for t in args.tests}
        plots += plot_rates(summary, output, tests)
        coverage = plot_coverage(episodes, VARIANT_NAMES, output)
        if coverage:
            plots.append(coverage)
        plots += plot_time_series(_extend_curves(results, args.max_steps), VARIANT_NAMES, tests, output)
        map_seed = args.base_seed if args.map_seed is None else args.map_seed
        for test in args.tests:
            record = _swarm_map_record(config, test, map_seed)
            plots.append(plot_swarm_stress_map(record, output / "plots" / f"swarm_stress_map_{test}.png"))

    report = write_report(output, summary, stats, args, plots)
    print(report.read_text(encoding="utf-8").split(LEGEND_HEADING)[0].split("## Figures")[0].rstrip())
    print(f"\nResults: {output.resolve()}")
    if plots:
        print(f"Figures: {(output / 'plots').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
