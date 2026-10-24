"""Analytics pipeline smoke test."""

from __future__ import annotations

from config.config import SimulationConfig
from src.analytics.benchmark import BenchmarkManager, ExperimentSpec


def test_batch_pipeline_writes_reproducible_artifacts(tmp_path):
    config = SimulationConfig(
        width=12,
        height=12,
        num_rovers=2,
        seed=4,
        max_steps=6,
        exploration_budget=100,
        navigation_mode="scaffold",
        mission_mode="exploration",
    )
    manager = BenchmarkManager(config)
    output = manager.run_comparative_batch(
        [ExperimentSpec("scaffold", "exploration")],
        iterations=1,
        output_dir=tmp_path,
        workers=1,
        base_seed=0,
    )
    for name in (
        "episodes.csv",
        "steps.csv",
        "summary.csv",
        "summary.json",
        "report.md",
        "config.json",
        "environment.json",
    ):
        assert (output / name).exists(), name
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "NOT SCIENTIFIC" in report
    assert "PIPELINE SMOKE" in report
    assert (output / "plots" / "success_rate.png").exists()
    episodes = (output / "episodes.csv").read_text(encoding="utf-8")
    assert "scaffold" in episodes
