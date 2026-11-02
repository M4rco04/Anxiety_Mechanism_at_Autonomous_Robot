"""Scientific navigation algorithm placeholders — owned by Karol.

Do not implement these algorithms as part of the robot work.  The surrounding
robot, board, observation and registry already provide everything needed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

from config.config import SimulationConfig
from src.model.types import RGB, Position, rgb_distance
from src.navigation.board import HexGridBoard
from src.navigation.types import NavigationDecision, Observation


def _match_fear_intensity(
    signature: RGB | None,
    anxiety_memory: Mapping[RGB, any],
    tolerance: float = 30.0,
) -> float:
    """Find the highest effective fear intensity matching the given RGB signature."""
    if signature is None or not anxiety_memory:
        return 0.0

    max_intensity = 0.0
    for stored_rgb, fear_view in anxiety_memory.items():
        if rgb_distance(signature, stored_rgb) <= tolerance:
            intensity = getattr(fear_view, "effective_intensity", 0.0)
            if intensity > max_intensity:
                max_intensity = intensity
    return max_intensity

class OnlineSearchStrategy:

    IMPLEMENTED = True
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self._forced_visits = 0
        self._retreats = 0
        # Heuristic lookup for LRTA* / Online Search
        self.h_cost: dict[Position, float] = {}

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:

        board = self._get_board(rover)
        if observation.mission_mode == "goal_navigation":
            if observation.target is None:
                return NavigationDecision(None, "missing target", "no_path")
            if observation.position == observation.target:
                return NavigationDecision(None, "target reached", "goal_reached")
        elif observation.mission_mode == "exploration":
            if observation.coverage_visited >= observation.coverage_target:
                return NavigationDecision(
                    None, "coverage target reached", "exploration_complete"
                )

            # 2. Candidate actions
        actions = board.actions(observation.position, observation)
        if not actions:
            return NavigationDecision(None, "no safe neighbour", "no_path")

        # 3. Goal navigation
        if observation.mission_mode == "goal_navigation":
            target = observation.target
            assert target is not None

            for action in actions:
                if action not in self.h_cost:
                    self.h_cost[action] = float(board.hex_distance(action, target))
            self.h_cost[target] = 0.0

            def goal_key(action: Position):
                terrain = observation.visible_cells.get(action)
                cost = terrain.movement_cost if terrain else board.movement_cost(action)
                h_val = self.h_cost[action]
                visited_penalty = 1.5 if action in observation.visited else 0.0
                return (cost + h_val + visited_penalty, action)

            chosen = min(actions, key=goal_key)
            self._moves += 1
            return NavigationDecision(chosen, "online goal search", "moving")

        # 4. Exploration mode (Frontier / Unseen exploration)
        previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
        candidate_actions = actions
        if len(candidate_actions) > 1 and previous in candidate_actions:
            candidate_actions = [a for a in candidate_actions if a != previous]

        def explore_key(action: Position):
            unseen = sum(
                1
                for neighbour in board.neighbors(action)
                if neighbour not in observation.visited
            )
            terrain = observation.visible_cells.get(action)
            cost = terrain.movement_cost if terrain else board.movement_cost(action)
            return (
                1 if action in observation.visited else 0,
                -unseen,
                cost,
                action,
            )

        chosen = min(candidate_actions, key=explore_key)
        self._moves += 1
        return NavigationDecision(chosen, "online exploration", "moving")

    def statistics(self) -> Mapping[str, int | float]:
        return {
            "moves": self._moves,
            "forced_visits": self._forced_visits,
            "retreats": self._retreats,
            "scientific": 1,
        }


class LRTAStarStrategy:

    IMPLEMENTED = True
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self.h_cost: dict[Position, float] = {}

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        board = self._get_board(rover)

        if observation.mission_mode == "goal_navigation":
            if observation.target is None:
                return NavigationDecision(None, "missing target", "no_path")
            if observation.position == observation.target:
                return NavigationDecision(None, "target reached", "goal_reached")
        elif observation.mission_mode == "exploration":
            if observation.coverage_visited >= observation.coverage_target:
                return NavigationDecision(
                    None, "coverage target reached", "exploration_complete"
                )

        actions = board.actions(observation.position, observation)
        if not actions:
            return NavigationDecision(None, "no safe neighbour", "no_path")

        target = observation.target if observation.mission_mode == "goal_navigation" else None

        # Update heuristic table
        if target is not None:
            self.h_cost[target] = 0.0
            for action in actions:
                if action not in self.h_cost:
                    self.h_cost[action] = float(board.hex_distance(action, target))

            # LRTA* update rule for current position
            best_successor_cost = min(
                (observation.visible_cells.get(a).movement_cost if observation.visible_cells.get(a) else board.movement_cost(a)) + self.h_cost[a]
                for a in actions
            )
            self.h_cost[observation.position] = max(
                self.h_cost.get(observation.position, float(board.hex_distance(observation.position, target))),
                best_successor_cost,
            )

            def lrta_key(action: Position):
                terrain = observation.visible_cells.get(action)
                cost = terrain.movement_cost if terrain else board.movement_cost(action)
                return (cost + self.h_cost[action], action)

            chosen = min(actions, key=lrta_key)
            self._moves += 1
            return NavigationDecision(chosen, "lrta* step", "moving")

        # Exploration fallback for LRTA*
        def explore_key(action: Position):
            unseen = sum(
                1
                for neighbour in board.neighbors(action)
                if neighbour not in observation.visited
            )
            return (1 if action in observation.visited else 0, -unseen, action)

        chosen = min(actions, key=explore_key)
        self._moves += 1
        return NavigationDecision(chosen, "lrta* explore", "moving")

    def statistics(self) -> Mapping[str, int | float]:
        return {"moves": self._moves, "scientific": 1}


class EmotionalStrategy:

    IMPLEMENTED = True
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self._forced_visits = 0
        self._retreats = 0
        self.h_cost: dict[Position, float] = {}

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def _get_fear_cost(self, position: Position, observation: Observation) -> float:
        if not observation.anxiety_memory:
            return 0.0

        signature = observation.rgb_signatures.get(position)
        if signature is None and position in observation.visible_cells:
            signature = observation.visible_cells[position].rgb_signature

        tolerance = getattr(self.config, "rgb_tolerance", 30.0)
        fear_weight = getattr(self.config, "fear_weight", 10.0)

        intensity = _match_fear_intensity(signature, observation.anxiety_memory, tolerance)
        return fear_weight * intensity

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        board = self._get_board(rover)

        # 1. Termination checks
        if observation.mission_mode == "goal_navigation":
            if observation.target is None:
                return NavigationDecision(None, "missing target", "no_path")
            if observation.position == observation.target:
                return NavigationDecision(None, "target reached", "goal_reached")
        elif observation.mission_mode == "exploration":
            if observation.coverage_visited >= observation.coverage_target:
                return NavigationDecision(
                    None, "coverage target reached", "exploration_complete"
                )

        # 2. Candidate actions
        actions = board.actions(observation.position, observation)
        if not actions:
            return NavigationDecision(None, "no safe neighbour", "no_path")

        # 3. High-anxiety retreat handling
        if observation.retreat_required:
            self._retreats += 1
            previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
            if previous in actions:
                self._moves += 1
                return NavigationDecision(
                    previous,
                    "retreating along recent path",
                    "moving",
                    {"fear_intensity": rover.current_fear_intensity()},
                )

            def retreat_key(action: Position):
                fear = self._get_fear_cost(action, observation)
                terrain = observation.visible_cells.get(action)
                cost = terrain.movement_cost if terrain else board.movement_cost(action)
                return (fear, cost, action)

            chosen = min(actions, key=retreat_key)
            self._moves += 1
            return NavigationDecision(
                chosen,
                "retreating to safest neighbour",
                "moving",
                {"fear_intensity": rover.current_fear_intensity()},
            )

        # 4. Fear-cost evaluation and filtering
        fear_costs: dict[Position, float] = {
            a: self._get_fear_cost(a, observation) for a in actions
        }
        non_fear_actions = [a for a in actions if fear_costs[a] == 0.0]
        forced_visit = False

        if not non_fear_actions:
            if observation.allow_forced_fear_visit or (
                observation.mission_mode == "goal_navigation"
                and observation.target in actions
            ):
                non_fear_actions = actions
                forced_visit = True
                self._forced_visits += 1
            else:
                return NavigationDecision(
                    None, "blocked by fear on all paths", "blocked"
                )

        candidate_actions = non_fear_actions

        # 5. Goal navigation
        if observation.mission_mode == "goal_navigation":
            target = observation.target
            assert target is not None

            for action in candidate_actions:
                if action not in self.h_cost:
                    self.h_cost[action] = float(board.hex_distance(action, target))
            self.h_cost[target] = 0.0

            def goal_key(action: Position):
                terrain = observation.visible_cells.get(action)
                cost = terrain.movement_cost if terrain else board.movement_cost(action)
                fear = fear_costs.get(action, 0.0)
                h_val = self.h_cost[action]
                visited_penalty = 1.5 if action in observation.visited else 0.0
                return (cost + fear + h_val + visited_penalty, action)

            chosen = min(candidate_actions, key=goal_key)
            self._moves += 1
            status = "forced_fear_visit" if forced_visit else "moving"
            return NavigationDecision(chosen, "emotional goal navigation", status)

        # 6. Exploration mode
        previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
        if len(candidate_actions) > 1 and previous in candidate_actions:
            candidate_actions = [a for a in candidate_actions if a != previous]

        def explore_key(action: Position):
            unseen = sum(
                1
                for neighbour in board.neighbors(action)
                if neighbour not in observation.visited
            )
            terrain = observation.visible_cells.get(action)
            cost = terrain.movement_cost if terrain else board.movement_cost(action)
            fear = fear_costs.get(action, 0.0)
            return (
                1 if action in observation.visited else 0,
                -unseen,
                cost + fear,
                action,
            )

        chosen = min(candidate_actions, key=explore_key)
        self._moves += 1
        status = "forced_fear_visit" if forced_visit else "moving"
        return NavigationDecision(chosen, "emotional exploration", status)

    def statistics(self) -> Mapping[str, int | float]:
        return {
            "moves": self._moves,
            "forced_visits": self._forced_visits,
            "retreats": self._retreats,
            "scientific": 1,
        }


class SwarmEmotionalStrategy:
    """TODO(Karol): emotional navigation with radio-sourced fear memory."""

    IMPLEMENTED = True
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self._forced_visits = 0
        self._retreats = 0
        self.h_cost: dict[Position, float] = {}

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def _get_fear_cost(self, position: Position, observation: Observation) -> float:
        if not observation.anxiety_memory:
            return 0.0

        signature = observation.rgb_signatures.get(position)
        if signature is None and position in observation.visible_cells:
            signature = observation.visible_cells[position].rgb_signature

        tolerance = getattr(self.config, "rgb_tolerance", 30.0)
        fear_weight = getattr(self.config, "fear_weight", 10.0)

        intensity = _match_fear_intensity(signature, observation.anxiety_memory, tolerance)
        return fear_weight * intensity

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        # Same decision rule as EmotionalStrategy; received radio signatures
        # are already merged into observation.anxiety_memory by the radio layer.
        board = self._get_board(rover)

        if observation.mission_mode == "goal_navigation":
            if observation.target is None:
                return NavigationDecision(None, "missing target", "no_path")
            if observation.position == observation.target:
                return NavigationDecision(None, "target reached", "goal_reached")
        elif observation.mission_mode == "exploration":
            if observation.coverage_visited >= observation.coverage_target:
                return NavigationDecision(
                    None, "coverage target reached", "exploration_complete"
                )

        actions = board.actions(observation.position, observation)
        if not actions:
            return NavigationDecision(None, "no safe neighbour", "no_path")

        if observation.retreat_required:
            self._retreats += 1
            previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
            if previous in actions:
                self._moves += 1
                return NavigationDecision(
                    previous,
                    "retreating along recent path",
                    "moving",
                    {"fear_intensity": rover.current_fear_intensity()},
                )

            def retreat_key(action: Position):
                fear = self._get_fear_cost(action, observation)
                terrain = observation.visible_cells.get(action)
                cost = terrain.movement_cost if terrain else board.movement_cost(action)
                return (fear, cost, action)

            chosen = min(actions, key=retreat_key)
            self._moves += 1
            return NavigationDecision(
                chosen,
                "retreating to safest neighbour",
                "moving",
                {"fear_intensity": rover.current_fear_intensity()},
            )

        fear_costs: dict[Position, float] = {
            a: self._get_fear_cost(a, observation) for a in actions
        }
        non_fear_actions = [a for a in actions if fear_costs[a] == 0.0]
        forced_visit = False

        if not non_fear_actions:
            if observation.allow_forced_fear_visit or (
                observation.mission_mode == "goal_navigation"
                and observation.target in actions
            ):
                non_fear_actions = actions
                forced_visit = True
                self._forced_visits += 1
            else:
                return NavigationDecision(
                    None, "blocked by fear on all paths", "blocked"
                )

        candidate_actions = non_fear_actions

        if observation.mission_mode == "goal_navigation":
            target = observation.target
            assert target is not None

            for action in candidate_actions:
                if action not in self.h_cost:
                    self.h_cost[action] = float(board.hex_distance(action, target))
            self.h_cost[target] = 0.0

            def goal_key(action: Position):
                terrain = observation.visible_cells.get(action)
                cost = terrain.movement_cost if terrain else board.movement_cost(action)
                fear = fear_costs.get(action, 0.0)
                h_val = self.h_cost[action]
                visited_penalty = 1.5 if action in observation.visited else 0.0
                return (cost + fear + h_val + visited_penalty, action)

            chosen = min(candidate_actions, key=goal_key)
            self._moves += 1
            status = "forced_fear_visit" if forced_visit else "moving"
            return NavigationDecision(chosen, "swarm emotional goal navigation", status)

        previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
        if len(candidate_actions) > 1 and previous in candidate_actions:
            candidate_actions = [a for a in candidate_actions if a != previous]

        def explore_key(action: Position):
            unseen = sum(
                1
                for neighbour in board.neighbors(action)
                if neighbour not in observation.visited
            )
            terrain = observation.visible_cells.get(action)
            cost = terrain.movement_cost if terrain else board.movement_cost(action)
            fear = fear_costs.get(action, 0.0)
            return (
                1 if action in observation.visited else 0,
                -unseen,
                cost + fear,
                action,
            )

        chosen = min(candidate_actions, key=explore_key)
        self._moves += 1
        status = "forced_fear_visit" if forced_visit else "moving"
        return NavigationDecision(chosen, "swarm emotional exploration", status)

    def statistics(self) -> Mapping[str, int | float]:
        return {
            "moves": self._moves,
            "forced_visits": self._forced_visits,
            "retreats": self._retreats,
            "scientific": 1,
        }


STRATEGY_CLASSES = {
    "online": OnlineSearchStrategy,
    "emotional": EmotionalStrategy,
    "swarm_emotional": SwarmEmotionalStrategy,
}

__all__ = [
    "STRATEGY_CLASSES",
    "EmotionalStrategy",
    "LRTAStarStrategy",
    "OnlineSearchStrategy",
    "SwarmEmotionalStrategy",
]
