"""Scientific navigation strategies.

- ``online``: plain rover (A* to the goal over known terrain, greedy
  frontier exploration), no anxiety.
- ``emotional``: the same rules plus the conditioned-anxiety mechanism
  (retreat, fear as a route cost, no circling in feared pockets).
- ``swarm_emotional``: ``emotional`` plus radio-shared fear and map and
  area splitting between swarm rovers.

``LRTAStarStrategy`` is a reference LRTA* agent, not registered as a mode.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from config.config import SimulationConfig
from src.model.types import RGB, Position, hex_distance, rgb_distance
from src.navigation.board import HexGridBoard
from src.navigation.energy import seek_charging_spot
from src.navigation.planning import plan_first_step
from src.navigation.types import NavigationDecision, Observation

# Extra cost per cell a swarm target lies beyond ``swarm_cohesion_radius``
# from a peer: the swarm may stretch out, but prefers to stay close.
SWARM_SPREAD_COST = 3.0
# Extra cost of a target in a peer's area (closer to that peer).
SWARM_PEER_AREA_COST = 10.0
# How many of the nearest unvisited cells a rover tries to plan a route to.
FRONTIER_CANDIDATES = 5
# A rover that spent this many recent steps on at most two cells is bouncing.
BOUNCE_WINDOW = 6


def _bounce_cells(rover) -> frozenset[Position]:
    """Cells a rover keeps bouncing between (empty when it is not)."""

    recent = rover.path[-BOUNCE_WINDOW:]
    if len(recent) == BOUNCE_WINDOW and len(set(recent)) <= 2:
        return frozenset(recent)
    return frozenset()


def _match_fear_intensity(
    signature: RGB | None,
    anxiety_memory: Mapping[RGB, Any],
    tolerance: float = 30.0,
) -> float:
    """Find the highest effective fear intensity matching the given RGB signature."""
    if signature is None or not anxiety_memory:
        return 0.0

    max_intensity = 0.0
    for stored_rgb, fear_view in anxiety_memory.items():
        if rgb_distance(signature, stored_rgb) <= tolerance:
            # FearView.intensity is already decayed (see Pioneer3DXAgent.fear_map).
            intensity = float(getattr(fear_view, "intensity", 0.0))
            max_intensity = max(max_intensity, intensity)
    return max_intensity


def _retreat_decision(
    rover, observation: Observation, board: HexGridBoard, actions: list[Position]
) -> NavigationDecision | None:
    """Step back to a neighbour the rover fears less than its current cell.

    Fear is read from terrain the rover has seen (also cells behind it).
    If no neighbour is less frightening (e.g. inside a large shadow area),
    returns ``None`` so the strategy keeps navigating normally instead of
    oscillating between two equally feared cells.
    """

    def fear_at(position: Position) -> float:
        cell = rover.known_terrain.get(position)
        return rover.fear_intensity(cell.rgb_signature) if cell is not None else 0.0

    current_fear = rover.current_fear_intensity()
    safer = [action for action in actions if fear_at(action) < current_fear]
    if not safer:
        return None
    previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
    metadata = {"fear_intensity": current_fear}
    if previous in safer:
        return NavigationDecision(
            previous, "retreating along recent path", "moving", metadata
        )
    chosen = min(
        safer, key=lambda action: (fear_at(action), board.movement_cost(action), action)
    )
    return NavigationDecision(
        chosen, "retreating to safest neighbour", "moving", metadata
    )



def _fearful_goal_step(
    strategy,
    rover,
    observation: Observation,
    board: HexGridBoard,
    actions: list[Position],
    reason: str,
) -> NavigationDecision:
    """Goal step where fear is a cost (detour) rather than a hard ban.

    The rover prefers a detour around feared terrain. When the detour is more
    expensive than crossing (fear_weight * intensity per cell), it crosses on
    purpose and does not retreat (``strategy._crossing``). The LRTA* update
    raises the estimate of the current cell, so a rover stuck in front of a
    feared area eventually finds the way instead of circling.
    """

    target = observation.target
    assert target is not None

    def fear_of(signature) -> float:
        return float(strategy.config.fear_weight) * rover.fear_intensity(signature)

    planned = plan_first_step(rover, observation, board, target, fear_of)
    if planned is not None:
        step, fear = planned
        strategy._crossing = fear > 0.0
        if strategy._crossing:
            strategy._forced_visits += 1
        strategy._moves += 1
        status = "forced_fear_visit" if strategy._crossing else "moving"
        return NavigationDecision(step, reason, status)

    # No route through known terrain: greedy LRTA* step as a fallback.
    strategy.h_cost[target] = 0.0
    fear_costs = {a: strategy._get_fear_cost(a, observation, rover) for a in actions}

    def h(position: Position) -> float:
        return strategy.h_cost.get(position, float(board.hex_distance(position, target)))

    def total(action: Position) -> float:
        terrain = observation.visible_cells.get(action)
        cost = terrain.movement_cost if terrain else board.movement_cost(action)
        return cost + fear_costs[action] + h(action)

    chosen = min(actions, key=lambda action: (total(action), action))
    position = observation.position
    strategy.h_cost[position] = max(h(position), total(chosen))
    strategy._crossing = fear_costs[chosen] > 0.0
    if strategy._crossing:
        strategy._forced_visits += 1
    strategy._moves += 1
    status = "forced_fear_visit" if strategy._crossing else "moving"
    return NavigationDecision(chosen, reason, status)


def _frontier_step(
    strategy,
    rover,
    observation: Observation,
    board: HexGridBoard,
    reason: str,
    allowed: Callable[[Position], bool] | None = None,
) -> NavigationDecision | None:
    """Plan a route to the nearest unvisited known cell.

    Used when there is nothing new next to the rover, so a purely local rule
    would circle in a small pocket of safe cells surrounded by feared
    terrain. As in goal navigation, fear is a cost here, not a ban: the
    rover prefers a detour, and crosses feared terrain on purpose when no
    detour exists (``strategy._crossing``, so it does not retreat halfway).
    ``allowed`` can reject a first step (e.g. one that leaves radio range).
    """

    position = observation.position
    fear_weight = float(strategy.config.fear_weight)

    def fear_of(signature) -> float:
        return fear_weight * rover.fear_intensity(signature)

    frontier = sorted(
        (
            hex_distance(position, cell) + fear_of(info.rgb_signature),
            cell,
        )
        for cell, info in rover.known_terrain.items()
        if cell != position
        and info.traversable
        and cell not in observation.visited
        and cell not in observation.lidar_obstacles
    )
    for _, target in frontier[:FRONTIER_CANDIDATES]:
        planned = plan_first_step(rover, observation, board, target, fear_of)
        if planned is None:
            continue
        step, fear = planned
        if allowed is not None and not allowed(step):
            continue
        strategy._crossing = fear >= 0.1 * fear_weight
        if strategy._crossing:
            strategy._forced_visits += 1
        status = "forced_fear_visit" if strategy._crossing else "moving"
        return NavigationDecision(step, reason, status)
    return None


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

        # Low battery: go to the nearest known safe cell to charge.
        charge = seek_charging_spot(rover, observation, board)
        if charge is not None:
            self._moves += 1
            return charge

        # 3. Goal navigation: A* over known terrain, replanned every step.
        if observation.mission_mode == "goal_navigation":
            target = observation.target
            assert target is not None
            planned = plan_first_step(rover, observation, board, target)
            if planned is not None:
                self._moves += 1
                return NavigationDecision(planned[0], "online goal search", "moving")

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
            # LRTA* update (same as the emotional variants): avoids circling.
            position = observation.position
            self.h_cost[position] = max(
                self.h_cost.get(
                    position, float(board.hex_distance(position, target))
                ),
                goal_key(chosen)[0],
            )
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

        charge = seek_charging_spot(rover, observation, board)
        if charge is not None:
            self._moves += 1
            return charge

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
    GOAL_REASON = "emotional goal navigation"

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self._forced_visits = 0
        self._retreats = 0
        self._crossing = False
        self.h_cost: dict[Position, float] = {}

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def _get_fear_cost(
        self, position: Position, observation: Observation, rover=None
    ) -> float:
        if not observation.anxiety_memory:
            return 0.0

        signature = observation.rgb_signatures.get(position)
        if signature is None and position in observation.visible_cells:
            signature = observation.visible_cells[position].rgb_signature
        # Cells outside the forward camera view: use the remembered terrain,
        # otherwise most neighbours would look fear-free.
        if signature is None and rover is not None:
            remembered = rover.known_terrain.get(position)
            signature = remembered.rgb_signature if remembered is not None else None

        tolerance = float(self.config.fear_rgb_tolerance)
        fear_weight = float(self.config.fear_weight)

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
        # Low battery: go to the nearest known safe cell, avoiding feared terrain.
        charge = seek_charging_spot(
            rover,
            observation,
            board,
            lambda signature: float(self.config.fear_weight)
            * rover.fear_intensity(signature),
        )
        if charge is not None:
            self._moves += 1
            return charge

        if observation.retreat_required and not self._crossing:
            retreat = _retreat_decision(rover, observation, board, actions)
            if retreat is not None:
                self._retreats += 1
                self._moves += 1
                return retreat

        if observation.mission_mode == "goal_navigation":
            return _fearful_goal_step(
                self, rover, observation, board, actions, self.GOAL_REASON
            )

        # 4. Fear-cost evaluation and filtering
        fear_costs: dict[Position, float] = {
            a: self._get_fear_cost(a, observation, rover) for a in actions
        }
        # Weak fears (decayed or context fears) only add cost, they do not block.
        block_level = 0.1 * float(self.config.fear_weight)
        non_fear_actions = [a for a in actions if fear_costs[a] < block_level]
        forced_visit = False

        if not non_fear_actions:
            if observation.allow_forced_fear_visit:
                non_fear_actions = actions
                forced_visit = True
                self._forced_visits += 1
            else:
                frontier = _frontier_step(
                    self, rover, observation, board, "crossing feared terrain to new ground"
                )
                if frontier is not None:
                    self._moves += 1
                    return frontier
                return NavigationDecision(
                    None, "blocked by fear on all paths", "blocked"
                )

        candidate_actions = non_fear_actions

        # 5. Exploration mode (goal navigation returned above)
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
        if chosen in observation.visited:
            # Nothing new nearby: plan a route to new terrain instead of
            # circling inside a pocket of safe cells.
            frontier = _frontier_step(
                self, rover, observation, board, "emotional exploration (to new terrain)"
            )
            if frontier is not None:
                self._moves += 1
                return frontier
        self._crossing = False
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
    """Emotional navigation with own and radio-received fear memory."""

    IMPLEMENTED = True
    SCIENTIFIC = True
    GOAL_REASON = "swarm emotional goal navigation"

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self._forced_visits = 0
        self._retreats = 0
        self._crossing = False
        self.h_cost: dict[Position, float] = {}
        # Last position heard from each swarm peer (rover id -> position).
        self.peer_memory: dict[int, Position] = {}
        self._regroups = 0
        self._area_moves = 0
        self._waits = 0
        self.following = False
        # Current exploration target and the reason it was chosen.
        self.area_target: tuple[Position, str] | None = None

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def _get_fear_cost(
        self, position: Position, observation: Observation, rover=None
    ) -> float:
        if not observation.anxiety_memory:
            return 0.0

        signature = observation.rgb_signatures.get(position)
        if signature is None and position in observation.visible_cells:
            signature = observation.visible_cells[position].rgb_signature
        # Cells outside the forward camera view: use the remembered terrain,
        # otherwise most neighbours would look fear-free.
        if signature is None and rover is not None:
            remembered = rover.known_terrain.get(position)
            signature = remembered.rgb_signature if remembered is not None else None

        tolerance = float(self.config.fear_rgb_tolerance)
        fear_weight = float(self.config.fear_weight)

        intensity = _match_fear_intensity(signature, observation.anxiety_memory, tolerance)
        return fear_weight * intensity

    def _radio_limit(self) -> int:
        # Keep a margin: two rovers may each move one cell apart per step.
        cohesion = int(self.config.swarm_cohesion_radius)
        return max(cohesion, int(self.config.R_radio) - 2)

    def _within_radio(self, cell: Position, peers: Mapping[int, Position]) -> bool:
        limit = self._radio_limit()
        return all(hex_distance(peer, cell) <= limit for peer in peers.values())

    @staticmethod
    def _area_targets(
        candidates: list[tuple[float, Position, bool, bool]],
        own_area_only: bool = True,
        radio_limited: bool = True,
    ) -> list[tuple[float, Position]]:
        """Filter the sorted area candidates for one target tier."""

        return [
            (score, cell)
            for score, cell, in_peer_area, too_far in candidates
            if not (too_far and radio_limited)
            and not (in_peer_area and own_area_only)
        ]

    def _area_candidates(
        self,
        rover,
        observation: Observation,
        peers: Mapping[int, Position],
    ) -> list[tuple[float, Position, bool, bool]]:
        """Unvisited, not feared known cells, cheapest first.

        Returns ``(score, cell, in_peer_area, too_far)``. A cell belongs to
        the rover's own area when no peer is closer to it (ties go to the
        lower id), so the swarm splits the terrain between its rovers. Cells
        of a peer's area cost extra. Cells farther than
        ``swarm_cohesion_radius`` from a peer cost extra, so the rovers
        prefer to stay close; ``too_far`` marks cells near the edge of radio
        range. Computed once per step and filtered per tier by
        ``_area_targets`` (the score does not depend on the tier).
        """

        position = observation.position
        cohesion = int(self.config.swarm_cohesion_radius)
        radio_limit = self._radio_limit()
        fear_weight = float(self.config.fear_weight)
        block_level = 0.1 * fear_weight
        own_id = rover.unique_id
        # Many cells share a signature; match each one against memory once.
        fear_cache: dict[RGB | None, float] = {}
        targets: list[tuple[float, Position, bool, bool]] = []
        for cell, info in rover.known_terrain.items():
            if (
                cell == position
                or not info.traversable
                or cell in observation.visited
                or cell in observation.lidar_obstacles
            ):
                continue
            distance = hex_distance(position, cell)
            in_peer_area = False
            too_far = False
            spread = 0
            for peer_id, peer in peers.items():
                peer_distance = hex_distance(peer, cell)
                if peer_distance > radio_limit:
                    too_far = True
                if peer_distance < distance or (
                    peer_distance == distance and peer_id < own_id
                ):
                    in_peer_area = True
                spread = max(spread, peer_distance - cohesion)
            signature = info.rgb_signature
            fear = fear_cache.get(signature)
            if fear is None:
                fear = fear_weight * rover.fear_intensity(signature)
                fear_cache[signature] = fear
            if fear >= block_level:
                continue
            score = (
                distance
                + info.movement_cost
                + fear
                + SWARM_SPREAD_COST * spread
                + (SWARM_PEER_AREA_COST if in_peer_area else 0.0)
            )
            targets.append((score, cell, in_peer_area, too_far))
        targets.sort(key=lambda item: (item[0], item[1]))
        return targets

    def _swarm_explore_step(
        self, rover, observation: Observation, board: HexGridBoard
    ) -> NavigationDecision | None:
        """Explore the rover's own area while staying with the swarm.

        Returns ``None`` when there is nothing to do here, so the strategy
        falls back to local exploration.
        """

        peers = dict(observation.swarm_peers)
        self.peer_memory.update(peers)
        position = observation.position
        fear_weight = float(self.config.fear_weight)
        # Bouncing between two cells (e.g. at the edge of radio range): do not
        # step onto them again, pick another target instead.
        bounce = _bounce_cells(rover)
        if bounce:
            self.area_target = None

        def fear_of(signature) -> float:
            return fear_weight * rover.fear_intensity(signature)

        def head_to(target: Position, reason: str) -> NavigationDecision | None:
            planned = plan_first_step(rover, observation, board, target, fear_of)
            if planned is None:
                return None
            step, fear = planned
            if step in bounce:
                return None
            # A strongly feared first step: let the local rule handle it.
            if fear >= 0.1 * fear_weight:
                return None
            self._crossing = False
            return NavigationDecision(step, reason, "moving")

        # Lost contact: drive back to where the swarm was last heard. If
        # nobody answers there, that peer is forgotten.
        if not peers and self.peer_memory:
            near = max(2, int(self.config.swarm_cohesion_radius) // 2)
            for peer_id, last in sorted(
                self.peer_memory.items(),
                key=lambda item: (hex_distance(position, item[1]), item[0]),
            ):
                if hex_distance(position, last) <= near:
                    del self.peer_memory[peer_id]
                    continue
                decision = head_to(last, "regrouping with the swarm")
                if decision is not None:
                    self.area_target = None
                    self._regroups += 1
                    return decision
            if self.peer_memory:
                return None

        # 1. Own area within radio range. 2. A peer's area within radio
        # range (help out). 3. New terrain farther away: the swarm moves on
        # together, one step at a time, never leaving radio range.
        # The rover keeps its target until it is reached, visited by a peer,
        # feared or out of reach, so it does not switch targets back and forth
        # every time the peers (and so the area borders) move.
        # Once following the leader, keep following until close to it,
        # instead of turning back out at every step.
        if self.following:
            decision = self._follow_step(rover, observation, board, peers, fear_of)
            if decision is not None:
                return decision

        if self.area_target is not None:
            target, reason = self.area_target
            info = rover.known_terrain.get(target)
            still_valid = (
                target != position
                and target not in observation.visited
                and info is not None
                and fear_of(info.rgb_signature) < 0.1 * fear_weight
            )
            decision = head_to(target, reason) if still_valid else None
            if decision is not None and self._within_radio(
                decision.next_position, peers
            ):
                self._area_moves += 1
                return decision
            self.area_target = None

        tiers = (
            (True, True, "swarm emotional exploration (own area)"),
            (False, True, "swarm emotional exploration (helping a peer)"),
            (False, False, "swarm moving on to new terrain"),
        )
        # Held back: there is new terrain, but every way there leaves radio
        # range or goes back and forth.
        held_back = bool(bounce)
        candidates = self._area_candidates(rover, observation, peers)
        for own_area_only, radio_limited, reason in tiers:
            targets = self._area_targets(candidates, own_area_only, radio_limited)
            for _, target in targets[:FRONTIER_CANDIDATES]:
                decision = head_to(target, reason)
                if decision is None:
                    continue
                if not radio_limited and not self._within_radio(
                    decision.next_position, peers
                ):
                    held_back = True
                    continue
                self.area_target = (target, reason)
                self._area_moves += 1
                return decision

        if held_back and peers:
            return self._follow_or_wait(rover, observation, board, peers, fear_of)
        return None

    def _follow_or_wait(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        peers: Mapping[int, Position],
        fear_of: Callable[[RGB | None], float],
    ) -> NavigationDecision:
        """The swarm is stretched to the edge of radio range.

        The rover with the lowest id in contact leads: it waits, and the other
        rovers drive towards it. So two rovers pulling in opposite directions
        cannot keep each other bouncing at the edge of radio range.
        """

        self.area_target = None
        leader_id = min(peers)
        if leader_id < rover.unique_id:
            self.following = True
            decision = self._follow_step(rover, observation, board, peers, fear_of)
            if decision is not None:
                return decision
        self._waits += 1
        return NavigationDecision(None, "waiting for the swarm", "waiting")

    def _follow_step(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        peers: Mapping[int, Position],
        fear_of: Callable[[RGB | None], float],
    ) -> NavigationDecision | None:
        """Drive towards the leader until close to it (then stop following)."""

        leader_id = min(peers, default=None)
        if leader_id is None or leader_id > rover.unique_id:
            self.following = False
            return None
        leader = peers[leader_id]
        close = max(1, int(self.config.swarm_cohesion_radius) // 2)
        if hex_distance(observation.position, leader) <= close:
            self.following = False
            return None
        planned = plan_first_step(rover, observation, board, leader, fear_of)
        if planned is None:
            self.following = False
            return None
        step, fear = planned
        # The route to the leader is the cheapest one including fear: if it
        # still crosses feared terrain, cross on purpose and do not retreat.
        self._crossing = fear >= 0.1 * float(self.config.fear_weight)
        if self._crossing:
            self._forced_visits += 1
        self._regroups += 1
        status = "forced_fear_visit" if self._crossing else "moving"
        return NavigationDecision(step, "following the swarm leader", status)

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

        # Low battery: go to the nearest known safe cell, avoiding feared terrain.
        charge = seek_charging_spot(
            rover,
            observation,
            board,
            lambda signature: float(self.config.fear_weight)
            * rover.fear_intensity(signature),
        )
        if charge is not None:
            self._moves += 1
            return charge

        if observation.retreat_required and not self._crossing:
            retreat = _retreat_decision(rover, observation, board, actions)
            if retreat is not None:
                self._retreats += 1
                self._moves += 1
                return retreat

        if observation.mission_mode == "goal_navigation":
            return _fearful_goal_step(
                self, rover, observation, board, actions, self.GOAL_REASON
            )

        if self.config.swarm_split_area:
            decision = self._swarm_explore_step(rover, observation, board)
            if decision is not None:
                self._moves += 1
                return decision

        fear_costs: dict[Position, float] = {
            a: self._get_fear_cost(a, observation, rover) for a in actions
        }
        # Weak fears (decayed or context fears) only add cost, they do not block.
        block_level = 0.1 * float(self.config.fear_weight)
        non_fear_actions = [a for a in actions if fear_costs[a] < block_level]
        forced_visit = False

        if not non_fear_actions:
            if observation.allow_forced_fear_visit:
                non_fear_actions = actions
                forced_visit = True
                self._forced_visits += 1
            else:
                frontier = _frontier_step(
                    self, rover, observation, board, "crossing feared terrain to new ground"
                )
                if frontier is not None:
                    self._moves += 1
                    return frontier
                return NavigationDecision(
                    None, "blocked by fear on all paths", "blocked"
                )

        candidate_actions = non_fear_actions
        # Do not wander out of radio range of the swarm.
        if self.config.swarm_split_area and observation.swarm_peers:
            in_range = [
                a
                for a in candidate_actions
                if self._within_radio(a, observation.swarm_peers)
            ]
            candidate_actions = in_range or candidate_actions

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
        if chosen in observation.visited:
            peers = observation.swarm_peers
            bounce = _bounce_cells(rover)
            limit_radio = bool(self.config.swarm_split_area and peers)
            frontier = _frontier_step(
                self,
                rover,
                observation,
                board,
                "swarm emotional exploration (to new terrain)",
                allowed=lambda step: step not in bounce
                and (not limit_radio or self._within_radio(step, peers)),
            )
            if frontier is not None:
                self._moves += 1
                return frontier
        self._crossing = False
        self._moves += 1
        status = "forced_fear_visit" if forced_visit else "moving"
        return NavigationDecision(chosen, "swarm emotional exploration", status)

    def statistics(self) -> Mapping[str, int | float]:
        return {
            "moves": self._moves,
            "forced_visits": self._forced_visits,
            "retreats": self._retreats,
            "regroups": self._regroups,
            "area_moves": self._area_moves,
            "waits": self._waits,
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
