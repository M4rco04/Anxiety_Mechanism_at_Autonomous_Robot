"""Publication study: controls, ablations, sensitivity and camera noise.

All experiments use **held-out maps** (seeds from ``--base-seed``, default
1000) that were not used while the model parameters were calibrated
(seeds 0-39), and the frozen default parameters from ``config/config.py``.

Parts:
  swarm        - which part of the swarm helps: more rovers, a shared map,
                 or shared fear?
  ablation     - what each element of the anxiety model contributes
  sensitivity  - how results change with S_crit, fear weight and fear decay
  noise        - survival as a function of camera RGB noise

Example:
    uv run study --runs 100 --sens-runs 50 --workers 6
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from config.config import HomeostatConfig, SimulationConfig
from root.analyze import TESTS, _run_one
from src.analytics.benchmark import rate_interval

PLAIN, ANXIETY = "Plain", "Anxiety"

# (condition, navigation mode, rovers, config overrides)
SWARM_CONDITIONS: list[tuple[str, str, int, dict[str, Any]]] = [
    ("Plain ×1", "online", 1, {}),
    ("Anxiety ×1", "emotional", 1, {}),
    ("Fuzzy rules ×1", "fuzzy", 1, {}),
    ("Plain ×3", "online", 3, {}),
    ("Anxiety ×3 (no radio)", "emotional", 3, {}),
    ("Swarm: shared map only", "swarm_emotional", 3, {"swarm_share_fear": False}),
    ("Swarm: map + fear", "swarm_emotional", 3, {}),
]

ABLATIONS: list[tuple[str, dict[str, Any]]] = [
    ("Full model", {}),
    ("Spec. homeostat (wear, S_crit 75)", {"homeostat": HomeostatConfig.specification()}),
    ("Smoothed-stress trigger", {"homeostat": HomeostatConfig(imprint_on_instantaneous=False)}),
    ("No slip alarm", {"homeostat": HomeostatConfig(slip_alarm_steps=0)}),
    ("No accumulated-stress alarm", {"homeostat": HomeostatConfig(chronic_alarm=0.0)}),
    ("No context imprint", {"context_imprint_weight": 0.0}),
    ("No fear decay", {"fear_decay": 0.0}),
    ("No crossing limit in exploration", {"explore_max_aversion": 1000.0}),
    ("No look before step", {"look_before_step": False}),
]

SENSITIVITY: dict[str, tuple[str, list[float], float]] = {
    # parameter: (label, values, default)
    "s_crit": ("Stress threshold S_crit", [25, 30, 40, 50, 60, 75], 40),
    "fear_weight": ("Fear weight (cost per feared cell)", [5, 10, 20, 30, 60, 100], 30),
    "fear_decay": ("Fear decay per step", [0.0, 0.0025, 0.005, 0.01, 0.02, 0.05], 0.005),
}

NOISE_LEVELS = [0.0, 2.5, 5.0, 10.0, 15.0, 20.0, 30.0]
NOISE_VARIANTS = [("Plain ×1", "online", 1), ("Anxiety ×1", "emotional", 1), ("Swarm ×3", "swarm_emotional", 3)]


def _apply(config: SimulationConfig, overrides: dict[str, Any]) -> SimulationConfig:
    homeostat = overrides.get("homeostat")
    rest = {k: v for k, v in overrides.items() if k != "homeostat"}
    if "s_crit" in rest:
        homeostat = replace(homeostat or config.homeostat, s_crit=rest.pop("s_crit"))
    config = replace(config, **rest)
    if homeostat is not None:
        config = replace(config, homeostat=homeostat)
    config.validate()
    return config


def _task(task: tuple[str, str, float | None, SimulationConfig, str, str, int, str, int]) -> dict[str, Any]:
    part, condition, value, config, variant, mode, rovers, test, seed = task
    episode = _run_one((config, variant, mode, rovers, test, seed))["episode"]
    episode.update(part=part, condition=condition, value=value)
    return episode


def build_tasks(args: argparse.Namespace, base: SimulationConfig) -> list[tuple]:
    seeds = list(range(args.base_seed, args.base_seed + args.runs))
    sens_seeds = seeds[: args.sens_runs]
    tasks: list[tuple] = []
    if "swarm" in args.parts:
        for condition, mode, rovers, overrides in SWARM_CONDITIONS:
            config = _apply(base, overrides)
            for test in TESTS:
                tasks += [("swarm", condition, None, config, condition, mode, rovers, test, s) for s in seeds]
    if "ablation" in args.parts:
        for condition, overrides in ABLATIONS:
            config = _apply(base, overrides)
            for test in TESTS:
                tasks += [("ablation", condition, None, config, ANXIETY, "emotional", 1, test, s) for s in seeds]
        for test in TESTS:  # reference without anxiety
            tasks += [("ablation", "No anxiety (plain)", None, base, PLAIN, "online", 1, test, s) for s in seeds]
    if "sensitivity" in args.parts:
        for parameter, (_, values, _) in SENSITIVITY.items():
            for value in values:
                config = _apply(base, {parameter: value})
                for test in TESTS:
                    tasks += [("sensitivity", parameter, value, config, ANXIETY, "emotional", 1, test, s) for s in sens_seeds]
        for test in TESTS:  # parameters do not affect the plain rover: one reference
            tasks += [("sensitivity", "plain", None, base, PLAIN, "online", 1, test, s) for s in sens_seeds]
    if "noise" in args.parts:
        for sigma in NOISE_LEVELS:
            config = _apply(base, {"rgb_noise_sigma": sigma})
            for name, mode, rovers in NOISE_VARIANTS:
                tasks += [("noise", name, sigma, config, name, mode, rovers, "exploration", s) for s in seeds]
    return tasks


# ----------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------
def rate_rows(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per group: rover survival and route completion with a 95% interval."""

    rows = []
    for key, group in frame.groupby(keys, sort=False, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        rovers = int(group["rovers"].sum())
        survived = int(group["rovers_survived"].sum())
        at_goal = int(group["rovers_at_goal"].sum())
        s_low, s_high = rate_interval(group["rovers_survived"], group["rovers"])
        g_low, g_high = rate_interval(group["rovers_at_goal"], group["rovers"])
        rows.append(
            {
                **dict(zip(keys, key)),
                "simulations": len(group),
                "rovers_total": rovers,
                "survival_rate": survived / rovers,
                "survival_ci_low": s_low,
                "survival_ci_high": s_high,
                "route_completed_rate": at_goal / rovers,
                "route_completed_ci_low": g_low,
                "route_completed_ci_high": g_high,
                "terrain_discovered_mean": float(group["terrain_discovered_pct"].mean()),
                "terrain_discovered_sem": float(group["terrain_discovered_pct"].sem()),
                "fear_imprints_mean": float(group["fear_imprints"].mean()),
                "fears_per_rover_mean": float(group["fears_per_rover"].mean()),
                "rovers_fearing_safe_ground": int(group["rovers_fearing_safe_ground"].sum()),
            }
        )
    return pd.DataFrame(rows)


def paired_test(frame: pd.DataFrame, a: str, b: str, test: str, column: str) -> dict[str, Any]:
    """Paired by seed: exact McNemar for 0/1 outcomes, Wilcoxon otherwise."""

    from scipy.stats import binomtest, wilcoxon

    sub = frame[frame["test"] == test]
    x = sub[sub["condition"] == a].set_index("seed")[column].astype(float)
    y = sub[sub["condition"] == b].set_index("seed")[column].astype(float)
    common = x.index.intersection(y.index)
    x, y = x.loc[common], y.loc[common]
    binary = set(x.unique()) | set(y.unique()) <= {0.0, 1.0}
    if binary:
        better, worse = int(((x == 0) & (y == 1)).sum()), int(((x == 1) & (y == 0)).sum())
        p = binomtest(min(better, worse), better + worse, 0.5).pvalue if better + worse else 1.0
        method = "McNemar (exact)"
    else:
        p = float(wilcoxon(x, y).pvalue) if (y - x).abs().sum() > 0 else 1.0
        method = "Wilcoxon"
    return {
        "test": TESTS[test],
        "comparison": f"{b} vs {a}",
        "measure": column,
        "mean_a": float(x.mean()),
        "mean_b": float(y.mean()),
        "difference": float(y.mean() - x.mean()),
        "pairs": len(common),
        "method": method,
        "p_value": p,
    }


def holm(frame: pd.DataFrame) -> pd.DataFrame:
    """Holm correction across all comparisons of one table."""

    if frame.empty:
        return frame
    order = frame["p_value"].sort_values().index
    m, running = len(order), 0.0
    adjusted = {}
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * frame.loc[index, "p_value"]))
        adjusted[index] = running
    frame = frame.copy()
    frame["p_holm"] = pd.Series(adjusted)
    frame["significant"] = frame["p_holm"] < 0.05
    return frame


SWARM_COMPARISONS = [
    # (a, b, what b - a isolates)
    ("Plain ×1", "Anxiety ×1", "anxiety, single rover"),
    ("Plain ×1", "Fuzzy rules ×1", "expert fuzzy rules, single rover"),
    ("Anxiety ×1", "Fuzzy rules ×1", "expert rules instead of learned fear"),
    ("Plain ×3", "Anxiety ×3 (no radio)", "anxiety, three rovers"),
    ("Anxiety ×3 (no radio)", "Swarm: shared map only", "sharing the map"),
    ("Swarm: shared map only", "Swarm: map + fear", "sharing fear by radio"),
    ("Anxiety ×3 (no radio)", "Swarm: map + fear", "whole swarm communication"),
]


def swarm_tests(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for a, b, effect in SWARM_COMPARISONS:
        for test in TESTS:
            for column in ("rovers_survived", "terrain_discovered_pct", "rovers_at_goal"):
                if test == "exploration" and column == "rovers_at_goal":
                    continue
                if test == "goal_navigation" and column == "terrain_discovered_pct":
                    continue
                row = paired_test(frame, a, b, test, column)
                row["isolated_effect"] = effect
                rows.append(row)
    return holm(pd.DataFrame(rows))


def ablation_tests(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for condition, _ in ABLATIONS[1:]:
        for test, column in (("exploration", "rovers_survived"), ("goal_navigation", "rovers_at_goal")):
            rows.append(paired_test(frame, "Full model", condition, test, column))
    for test, column in (("exploration", "rovers_survived"), ("goal_navigation", "rovers_at_goal")):
        rows.append(paired_test(frame, "No anxiety (plain)", "Full model", test, column))
    return holm(pd.DataFrame(rows))


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------
def _pct(rate: float, low: float, high: float) -> str:
    return f"{100 * rate:.1f}% [{100 * low:.0f}–{100 * high:.0f}]"


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = lambda vals: "| " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)) + " |"
    return "\n".join([line(headers), "|" + "|".join("-" * (w + 2) for w in widths) + "|", *(line(r) for r in rows)])


def _test_table(tests: pd.DataFrame, extra: str | None = None) -> str:
    headers = ["Test", "Comparison", *( [extra.replace("_", " ").capitalize()] if extra else []),
               "Measure", "A", "B", "B − A", "p", "p (Holm)", "Significant"]
    rows = []
    for r in tests.itertuples():
        rows.append([
            r.test, r.comparison, *([getattr(r, extra)] if extra else []), r.measure,
            f"{r.mean_a:.2f}", f"{r.mean_b:.2f}", f"{r.difference:+.2f}",
            _p(r.p_value), _p(r.p_holm), "yes" if r.significant else "no",
        ])
    return _table(headers, rows)


def write_report(out: Path, args: argparse.Namespace, results: dict[str, Any], seconds: float | None) -> Path:
    text = [
        "# Publication study",
        "",
        (f"Held-out maps: seeds {args.base_seed}–{args.base_seed + args.runs - 1} (calibration used seeds 0–39 and 5000–5159). "
        f"Frozen default parameters. {args.runs} simulations per condition and test; sensitivity uses "
        f"the first {args.sens_runs} seeds. Brackets: 95% interval (Wilson; bootstrap over simulations for several rovers). Paired tests by seed, "
        "Holm-corrected within each table. Survival and route completion are per rover."),
        "",
        f"Total simulations: {results['simulations']}"
        + (f", run time {seconds / 60:.1f} min." if seconds is not None else "."),
        "",
    ]
    if "swarm" in results:
        rates, tests = results["swarm"]
        text += ["## 1. Swarm controls", "",
                 ("Plain, anxious and fuzzy rovers, and which part of the swarm helps: more rovers, "
                 "a shared map, or shared fear?"), ""]
        text.append(_table(
            ["Test", "Condition", "Rover survival", "Route completed", "Terrain discovered [%]"],
            [[TESTS[r.test], r.condition, _pct(r.survival_rate, r.survival_ci_low, r.survival_ci_high),
              _pct(r.route_completed_rate, r.route_completed_ci_low, r.route_completed_ci_high) if r.test == "goal_navigation" else "–",
              f"{r.terrain_discovered_mean:.1f} ± {1.96 * r.terrain_discovered_sem:.1f}" if r.test == "exploration" else "–"]
             for r in rates.itertuples()]))
        text += ["", "Paired tests (measure = survivors / discovered terrain / rovers at goal per simulation):", "",
                 _test_table(tests, "isolated_effect"), "", "![swarm controls](plots/swarm_controls.png)", ""]
    if "ablation" in results:
        rates, tests = results["ablation"]
        text += ["## 2. Ablations (single rover with anxiety)", ""]
        text.append(_table(
            ["Condition", "Exploration: survival", "Goal: route completed", "Fears per rover (expl.)", "Fear safe ground (expl.)"],
            [[c,
              _pct(*rates[(rates.condition == c) & (rates.test == "exploration")][["survival_rate", "survival_ci_low", "survival_ci_high"]].iloc[0]),
              _pct(*rates[(rates.condition == c) & (rates.test == "goal_navigation")][["route_completed_rate", "route_completed_ci_low", "route_completed_ci_high"]].iloc[0]),
              f"{rates[(rates.condition == c) & (rates.test == 'exploration')]['fears_per_rover_mean'].iloc[0]:.1f}",
              str(int(rates[(rates.condition == c) & (rates.test == 'exploration')]['rovers_fearing_safe_ground'].iloc[0]))]
             for c in rates["condition"].unique()]))
        text += ["", "Paired tests against the full model (and full model vs no anxiety):", "",
                 _test_table(tests), "", "![ablations](plots/ablation.png)", ""]
    if "sensitivity" in results:
        rates = results["sensitivity"]
        text += ["## 3. Sensitivity (single rover with anxiety)", "",
                 ("One parameter changed at a time, the others at their defaults. The plain rover does not "
                 "depend on these parameters and is shown as a reference."), ""]
        for parameter, (label, _, default) in SENSITIVITY.items():
            sub = rates[rates["condition"] == parameter]
            text += [f"**{label}** (default {default:g})", ""]
            text.append(_table(
                ["Value", "Exploration: survival", "Goal: route completed"],
                [[f"{v:g}",
                  _pct(*sub[(sub.value == v) & (sub.test == "exploration")][["survival_rate", "survival_ci_low", "survival_ci_high"]].iloc[0]),
                  _pct(*sub[(sub.value == v) & (sub.test == "goal_navigation")][["route_completed_rate", "route_completed_ci_low", "route_completed_ci_high"]].iloc[0])]
                 for v in sorted(sub["value"].unique())]))
            text.append("")
        plain = rates[rates["condition"] == "plain"]
        text += [
            "Plain rover (reference): exploration survival "
            + _pct(*plain[plain.test == "exploration"][["survival_rate", "survival_ci_low", "survival_ci_high"]].iloc[0])
            + ", route completed "
            + _pct(*plain[plain.test == "goal_navigation"][["route_completed_rate", "route_completed_ci_low", "route_completed_ci_high"]].iloc[0])
            + ".", "", "![sensitivity](plots/sensitivity.png)", ""]
    if "noise" in results:
        rates = results["noise"]
        text += ["## 4. Camera noise (exploration)", "",
                 "Survival per rover as a function of the camera RGB noise σ (per channel).", ""]
        conditions = list(dict.fromkeys(rates["condition"]))
        text.append(_table(
            ["σ", *conditions],
            [[f"{s:g}", *[_pct(*rates[(rates.value == s) & (rates.condition == c)][["survival_rate", "survival_ci_low", "survival_ci_high"]].iloc[0]) for c in conditions]]
             for s in sorted(rates["value"].unique())]))
        text += ["", "![camera noise](plots/noise.png)", ""]
    report = out / "report.md"
    report.write_text("\n".join(text), encoding="utf-8")
    return report


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controls, ablations, sensitivity and noise study.")
    parser.add_argument("-n", "--runs", type=int, default=100, help="Simulations per condition and test.")
    parser.add_argument("--sens-runs", type=int, default=50, help="Simulations per sensitivity point.")
    parser.add_argument("--base-seed", type=int, default=1000, help="First held-out seed.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--parts", nargs="+", default=["swarm", "ablation", "sensitivity", "noise"],
                        choices=["swarm", "ablation", "sensitivity", "noise"])
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--output", type=Path, default=Path("results") / "study")
    parser.add_argument("--report-only", action="store_true",
                        help="Rebuild tables, figures and the report from the saved episodes.csv (no simulations).")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    out = args.output
    (out / "plots").mkdir(parents=True, exist_ok=True)
    if args.report_only:
        frame = pd.read_csv(out / "episodes.csv")
        seconds = None
    else:
        base = SimulationConfig(max_steps=args.max_steps, exploration_budget=args.max_steps)
        tasks = build_tasks(args, base)
        print(f"Running {len(tasks)} simulations on held-out seeds {args.base_seed}+ ...")
        start = time.perf_counter()
        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
            episodes = []
            for index, episode in enumerate(executor.map(_task, tasks, chunksize=8), 1):
                episodes.append(episode)
                if index % 200 == 0 or index == len(tasks):
                    print(f"  {index}/{len(tasks)}  ({(time.perf_counter() - start) / 60:.1f} min)", flush=True)
        seconds = time.perf_counter() - start
        frame = pd.DataFrame(episodes)
        # Saved before the tables and figures, so a failure there loses nothing
        # (rebuild with --report-only).
        frame.to_csv(out / "episodes.csv", index=False, float_format="%.6g")

    from src.analytics import study_plots

    results: dict[str, Any] = {"simulations": len(frame)}
    if "swarm" in args.parts:
        sub = frame[frame["part"] == "swarm"]
        rates, tests = rate_rows(sub, ["test", "condition"]), swarm_tests(sub)
        rates.to_csv(out / "swarm_controls.csv", index=False, float_format="%.4f")
        tests.to_csv(out / "swarm_tests.csv", index=False, float_format="%.4g")
        study_plots.plot_swarm_controls(rates, out / "plots" / "swarm_controls.png")
        results["swarm"] = (rates, tests)
    if "ablation" in args.parts:
        sub = frame[frame["part"] == "ablation"]
        rates, tests = rate_rows(sub, ["test", "condition"]), ablation_tests(sub)
        rates.to_csv(out / "ablation.csv", index=False, float_format="%.4f")
        tests.to_csv(out / "ablation_tests.csv", index=False, float_format="%.4g")
        study_plots.plot_ablation(rates, out / "plots" / "ablation.png")
        results["ablation"] = (rates, tests)
    if "sensitivity" in args.parts:
        sub = frame[frame["part"] == "sensitivity"]
        rates = rate_rows(sub, ["test", "condition", "value"])
        rates.to_csv(out / "sensitivity.csv", index=False, float_format="%.4f")
        study_plots.plot_sensitivity(rates, SENSITIVITY, out / "plots" / "sensitivity.png")
        results["sensitivity"] = rates
    if "noise" in args.parts:
        sub = frame[frame["part"] == "noise"]
        rates = rate_rows(sub, ["condition", "value"])
        rates.to_csv(out / "noise.csv", index=False, float_format="%.4f")
        study_plots.plot_noise(rates, out / "plots" / "noise.png")
        results["noise"] = rates

    report = write_report(out, args, results, seconds)
    print(report.read_text(encoding="utf-8"))
    print(f"\nResults: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
