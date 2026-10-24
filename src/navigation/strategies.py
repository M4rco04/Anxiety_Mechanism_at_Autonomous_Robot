"""Scientific navigation algorithm placeholders — owned by Karol.

Do not implement these algorithms as part of the robot work.  The surrounding
robot, board, observation and registry already provide everything needed.
"""

from __future__ import annotations

from collections.abc import Mapping

from config.config import SimulationConfig
from src.navigation.types import NavigationDecision, Observation


class OnlineSearchStrategy:
    """TODO(Karol): online search baseline from instruction section 7.2."""

    IMPLEMENTED = False
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        # TODO(Karol): implement visited/path backtracking, HexGridBoard
        # actions, max_steps and deterministic tie-breaking.
        raise NotImplementedError(
            "TODO(Karol): online search strategy is not implemented"
        )

    def statistics(self) -> Mapping[str, int | float]:
        return {}


class LRTAStarStrategy:
    """TODO(Karol): LRTA* with a hex-distance heuristic."""

    IMPLEMENTED = False
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        # TODO(Karol): h[target]=0; update h[current] from known actions;
        # choose 1 + h[next] with terrain cost and deterministic tie-break.
        # Never read unobserved terrain.
        raise NotImplementedError(
            "TODO(Karol): LRTA* strategy is not implemented"
        )

    def statistics(self) -> Mapping[str, int | float]:
        return {}


class EmotionalStrategy:
    """TODO(Karol): baseline navigation plus fear cost and retreat."""

    IMPLEMENTED = False
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        # TODO(Karol): add fear_weight * decayed_intensity to movement cost.
        # When observation.retreat_required is True, choose a safe retreat
        # move.  Allow forced fear visits only when no reasonable alternative
        # exists or the cell is the target.
        raise NotImplementedError(
            "TODO(Karol): emotional navigation strategy is not implemented"
        )

    def statistics(self) -> Mapping[str, int | float]:
        return {}


class SwarmEmotionalStrategy:
    """TODO(Karol): emotional navigation with radio-sourced fear memory."""

    IMPLEMENTED = False
    SCIENTIFIC = True

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        # TODO(Karol): the radio module already merges received signatures
        # into observation.anxiety_memory with source="radio".  Use exactly
        # the same decision rule as EmotionalStrategy so the comparison is
        # clean.  Optional swarm extensions must remain disabled by default.
        raise NotImplementedError(
            "TODO(Karol): swarm emotional strategy is not implemented"
        )

    def statistics(self) -> Mapping[str, int | float]:
        return {}


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
