"""Data collection and episode-level metrics (Wiktor's analytics layer)."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import fmean
from typing import Any

import mesa


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return float(fmean(values)) if values else 0.0


def _alive(model: Any) -> int:
    return sum(1 for rover in model.rovers() if rover.is_active)


def _model_fear_own(model: Any) -> int:
    return sum(rover.fear_events_own for rover in model.rovers())


def _model_fear_received(model: Any) -> int:
    return sum(rover.fear_events_received for rover in model.rovers())


def _model_fear_records(model: Any) -> int:
    return sum(len(rover.anxiety_memory) for rover in model.rovers())


def _model_destroyed(model: Any) -> int:
    return sum(1 for rover in model.rovers() if rover.is_destroyed)


def _model_overturned(model: Any) -> int:
    return sum(1 for rover in model.rovers() if rover.is_overturned)


def _model_goal_reached(model: Any) -> int:
    return sum(
        1 for rover in model.rovers() if rover.mission_status == "goal_reached"
    )


def _model_radio_sent(model: Any) -> int:
    return int(getattr(model.swarm, "total_sent", 0))


def setup_datacollector(model: Any) -> mesa.DataCollector:
    """Configure Mesa's standard collector plus the project's metrics."""


    def mean_stress(m: Any) -> float:
        return _mean(r.stress_level for r in m.rovers())

    def max_stress(m: Any) -> float:
        return max((r.stress_level for r in m.rovers()), default=0.0)

    def mean_battery(m: Any) -> float:
        return _mean(r.battery for r in m.rovers())

    def min_battery(m: Any) -> float:
        return min((r.battery for r in m.rovers()), default=0.0)

    def coverage_visited(m: Any) -> float:
        return m.coverage()[0]

    def coverage_discovered(m: Any) -> float:
        return m.coverage()[1]

    collector = mesa.DataCollector(
        model_reporters={
            "step": lambda m: m.step_count,
            "alive_rovers": _alive,
            "mean_battery": mean_battery,
            "min_battery": min_battery,
            "mean_stress": mean_stress,
            "max_stress": max_stress,
            "fear_events_own": _model_fear_own,
            "fear_events_received": _model_fear_received,
            "fear_records_total": _model_fear_records,
            "coverage_visited": coverage_visited,
            "coverage_discovered": coverage_discovered,
            "destroyed": _model_destroyed,
            "overturned": _model_overturned,
            "goal_reached": _model_goal_reached,
            "radio_packets_sent": _model_radio_sent,
            "radio_packets_received": lambda m: int(
                getattr(m, "radio_packets_received", 0)
            ),
            "termination_reason": lambda m: m.termination_reason,
        },
        agent_reporters={
            "position": lambda a: a.pos,
            "battery": lambda a: a.battery,
            "stress_level": lambda a: a.stress_level,
            "wheel_condition": lambda a: a.wheel_condition,
            "hull_condition": lambda a: a.hull_condition,
            "mission_status": lambda a: a.mission_status,
            "target": lambda a: a.target,
            "fear_events_own": lambda a: a.fear_events_own,
            "fear_events_received": lambda a: a.fear_events_received,
            "moves": lambda a: a.moves,
            "fear_entries": lambda a: a.fear_entries,
            "current_terrain": lambda a: (
                a.current_terrain_type.value
                if a.current_terrain_type is not None
                else None
            ),
        },
    )
    collector.agenttype_reporters = {}
    model.datacollector = collector
    return collector


def collect_rover_metrics(rover: Any) -> dict[str, Any]:
    mean_stress = (
        rover.stress_sum / rover.stress_samples if rover.stress_samples else 0.0
    )
    strategy_stats: dict[str, Any] = {}
    if getattr(rover, "strategy", None) is not None:
        try:
            strategy_stats = dict(rover.strategy.statistics())
        except (AttributeError, NotImplementedError):
            strategy_stats = {}
    return {
        "rover_id": int(rover.unique_id),
        "alive": bool(rover.is_active),
        "mission_status": rover.mission_status,
        "steps_active": int(rover.moves),
        "moves": int(rover.moves),
        "backtracks": int(rover.backtracks),
        "unique_visited": len(rover.visited),
        "path_length": len(rover.path),
        "battery_used": 100.0 - float(rover.battery),
        "final_battery": float(rover.battery),
        "hull_damage": 100.0 - float(rover.hull_condition),
        "wheel_damage": 100.0 - float(rover.wheel_condition),
        "mean_stress": float(mean_stress),
        "max_stress": float(rover.stress_level),
        "critical_events": int(rover.critical_events),
        "fear_events_own": int(rover.fear_events_own),
        "fear_events_received": int(rover.fear_events_received),
        "fear_records": len(rover.anxiety_memory),
        "fear_entries": int(rover.fear_entries),
        "forced_fear_entries": int(rover.forced_fear_entries),
        "blocked_moves": int(rover.blocked_moves),
        "collisions": int(rover.collisions),
        "overturns": int(rover.overturns),
        "destroyed": bool(rover.is_destroyed),
        "overturned": bool(rover.is_overturned),
        "goal_reached": rover.mission_status == "goal_reached",
        "goal_step": rover.goal_step,
        "target": rover.target,
        "final_position": rover.pos,
        "strategy_statistics": strategy_stats,
    }


def collect_episode_metrics(model: Any) -> dict[str, Any]:
    rovers = model.rovers()
    n = len(rovers)
    coverage_visited, coverage_discovered = model.coverage()
    goal_mode = model.config.mission_mode == "goal_navigation"
    if goal_mode:
        mission_success = bool(rovers) and all(
            rover.mission_status == "goal_reached" for rover in rovers
        )
    else:
        mission_success = (
            coverage_discovered >= model.config.coverage_target
            and not any(rover.is_destroyed for rover in rovers)
        )

    return {
        "mission_success": mission_success,
        "survival_rate": (
            sum(
                1
                for rover in rovers
                if not rover.is_destroyed and not rover.is_overturned
            )
            / n
            if n
            else 0.0
        ),
        "coverage_visited": coverage_visited,
        "coverage_discovered": coverage_discovered,
        "mean_battery": _mean(r.battery for r in rovers),
        "min_battery": min((r.battery for r in rovers), default=0.0),
        "mean_stress": _mean(r.stress_level for r in rovers),
        "max_stress": max((r.stress_level for r in rovers), default=0.0),
        "fear_events_own": sum(r.fear_events_own for r in rovers),
        "fear_events_received": sum(
            r.fear_events_received for r in rovers
        ),
        "fear_records_total": sum(len(r.anxiety_memory) for r in rovers),
        "radio_packets_sent": int(getattr(model.swarm, "total_sent", 0)),
        "radio_packets_received": int(
            getattr(model, "radio_packets_received", 0)
        ),
        "fear_entries_total": sum(r.fear_entries for r in rovers),
        "forced_fear_entries_total": sum(
            r.forced_fear_entries for r in rovers
        ),
        "blocked_moves_total": sum(r.blocked_moves for r in rovers),
        "collisions": sum(r.collisions for r in rovers),
        "overturns": sum(r.overturns for r in rovers),
        "destroyed": sum(1 for r in rovers if r.is_destroyed),
        "overturned": sum(1 for r in rovers if r.is_overturned),
        "goal_reached": sum(
            1 for r in rovers if r.mission_status == "goal_reached"
        ),
        "steps": int(model.step_count),
        "termination_reason": model.termination_reason,
        "navigation_mode": model.config.navigation_mode,
        "mission_mode": model.config.mission_mode,
        "num_rovers": n,
    }


def model_step_rows(model: Any) -> list[dict[str, Any]]:
    """Return per-step model metrics from Mesa's DataCollector."""

    frame = model.datacollector.get_model_vars_dataframe().reset_index()
    return frame.to_dict(orient="records")


def rover_step_rows(model: Any) -> list[dict[str, Any]]:
    """Return per-rover, per-step metrics from Mesa's DataCollector."""

    frame = model.datacollector.get_agent_vars_dataframe().reset_index()
    return frame.to_dict(orient="records")


__all__ = [
    "collect_episode_metrics",
    "collect_rover_metrics",
    "model_step_rows",
    "rover_step_rows",
    "setup_datacollector",
]
