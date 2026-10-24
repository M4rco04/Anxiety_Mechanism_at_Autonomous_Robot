"""Deterministic, non-scientific scaffold strategy.

This exists only so the robot, metrics and visualization pipeline can run
before Karol implements the scientific navigation variants.  It has no fear
model and no LRTA* heuristic; results produced with it must never be presented
as scientific evidence.
"""

from __future__ import annotations

from collections.abc import Mapping

from config.config import SimulationConfig
from src.model.types import Position
from src.navigation.board import HexGridBoard
from src.navigation.types import NavigationDecision, Observation


class ScaffoldStrategy:
    """A deterministic safe-neighbour walker for smoke tests only."""

    SCIENTIFIC = False
    IMPLEMENTED = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0

    def _board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        board = self._board(rover)
        if observation.mission_mode == "goal_navigation":
            if observation.target is None:
                return NavigationDecision(None, "missing target", "no_path")
            if observation.position == observation.target:
                return NavigationDecision(
                    None, "target reached", "goal_reached"
                )

        actions = board.actions(observation.position, observation)
        if not actions:
            return NavigationDecision(None, "no safe neighbour", "no_path")

        previous: Position | None = None
        if len(rover.path) >= 2:
            previous = rover.path[-2]
        if len(actions) > 1 and previous in actions:
            actions = [action for action in actions if action != previous]

        if observation.mission_mode == "goal_navigation":
            target = observation.target
            assert target is not None

            def goal_key(action: Position):
                return (
                    board.hex_distance(action, target),
                    1 if action in observation.visited else 0,
                    action,
                )

            chosen = min(actions, key=goal_key)
            self._moves += 1
            return NavigationDecision(chosen, "scaffold greedy goal")

        def explore_key(action: Position):
            unseen_neighbours = sum(
                1
                for neighbour in board.neighbors(action)
                if neighbour not in observation.visited
            )
            return (
                1 if action in observation.visited else 0,
                -unseen_neighbours,
                board.hex_distance(action, observation.position) * -1,
                action,
            )

        chosen = min(actions, key=explore_key)
        self._moves += 1
        return NavigationDecision(chosen, "scaffold frontier")

    def statistics(self) -> Mapping[str, int | float]:
        return {"moves": self._moves, "scientific": 0}


__all__ = ["ScaffoldStrategy"]
