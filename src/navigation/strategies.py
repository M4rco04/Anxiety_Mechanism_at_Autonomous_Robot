"""Scientific navigation strategies.

All variants share the same control: LRTA* to the goal (fear or caution
added to the cost of entering a cell) and
exploration of the nearest unseen terrain (``src/navigation/exploration.py``).
They differ only in how they value a cell:

- ``online``: plain rover, terrain cost only.
- ``emotional``: adds the learned fear of the conditioned-anxiety mechanism
  (fear as a route cost, retreat from strongly feared terrain).
- ``fuzzy``: no learning; expert fuzzy rules (``src/navigation/fuzzy.py``)
  turn terrain risk, slope and the rover's own state into caution, used as
  a route cost and to retreat.
- ``swarm_emotional``: ``emotional`` plus radio-shared fear and map and
  area splitting between swarm rovers.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable, Mapping

from config.config import SimulationConfig
from src.model.types import Position, hex_distance, squeezed
from src.navigation.board import HexGridBoard
from src.navigation.costs import TerrainCost, mean_cost, risk_cost, stress_aversion
from src.navigation.energy import seek_charging_spot
from src.navigation.exploration import (
    KEEP_TARGET_BONUS,
    CellCost,
    ExploreTarget,
    choose_target,
    frontier_targets,
)
from src.navigation.fuzzy import FuzzyInputs, caution, retreat_degree
from src.navigation.planning import UNKNOWN_CELL_COST, plan_first_step
from src.navigation.types import NavigationDecision, Observation

# Extra cost per cell a swarm target lies beyond ``swarm_cohesion_radius``
# from a peer: the swarm may stretch out, but prefers to stay close.
SWARM_SPREAD_COST = 3.0
# Extra cost of a target in a peer's area (closer to that peer).
SWARM_PEER_AREA_COST = 10.0
# How many of the nearest unseen cells a swarm rover compares.
SWARM_TARGETS = 60
# A rover that spent this many recent steps on at most two cells is bouncing.
BOUNCE_WINDOW = 6


def _bounce_cells(rover) -> frozenset[Position]:
    """Cells a rover keeps bouncing between (empty when it is not)."""

    recent = rover.path[-BOUNCE_WINDOW:]
    if len(recent) == BOUNCE_WINDOW and len(set(recent)) <= 2:
        return frozenset(recent)
    return frozenset()


def _retreat_decision(
    rover,
    board: HexGridBoard,
    actions: list[Position],
    cell_cost: CellCost,
    safe_level: float = math.inf,
) -> NavigationDecision | None:
    """Step back to a neighbour the rover fears (distrusts) less.

    The rover retreats only in a known direction: onto a cell it has driven
    on itself (``rover.visited``). A cell it has only seen from a distance
    may hide a danger the camera does not show (e.g. ventifacts or a slope
    under the same colour), so it is not a safe place to flee to. Only a
    neighbour below ``safe_level`` (the retreat threshold) counts: stepping
    from one strongly feared terrain onto another is not a retreat (e.g. from
    a slope back into the sand it just dug out of, and back again).
    If no neighbour qualifies (e.g. inside a large shadow area), returns
    ``None`` so the strategy takes the cheapest way out instead.
    """

    def cost_at(position: Position) -> float:
        cell = rover.known_terrain.get(position)
        return cell_cost(cell) if cell is not None else 0.0

    current = cost_at(rover.pos)
    driven = rover.visited
    safer = [
        action
        for action in actions
        if action in driven
        and action in rover.known_terrain
        and cost_at(action) < min(current, safe_level)
    ]
    if not safer:
        return None
    previous: Position | None = rover.path[-2] if len(rover.path) >= 2 else None
    metadata = {"aversion": current}
    if previous in safer:
        return NavigationDecision(
            previous, "retreating along recent path", "moving", metadata
        )
    chosen = min(
        safer, key=lambda action: (cost_at(action), board.movement_cost(action), action)
    )
    return NavigationDecision(
        chosen, "retreating to safest neighbour", "moving", metadata
    )


def _escape_decision(
    rover,
    observation: Observation,
    board: HexGridBoard,
    cell_cost: CellCost,
    level: float,
    terrain_cost: TerrainCost = mean_cost,
) -> NavigationDecision | None:
    """First step of the cheapest way out of feared (distrusted) terrain.

    Used when no neighbour is better than the current cell (e.g. deep
    inside a shadow area): the rover plans a route back over cells it has
    driven on (``rover.visited``) to the nearest such cell whose extra cost
    is below ``level``. It escapes only in a known direction, never into
    terrain it has only seen. ``None`` when no such way exists.
    """

    known = rover.known_terrain
    driven = rover.visited
    blocked = board.known_blocker(observation, known)
    start = observation.position
    first_actions = board.actions(start, observation)
    distance: dict[Position, float] = {start: 0.0}
    first: dict[Position, Position] = {}
    queue: list[tuple[float, Position]] = [(0.0, start)]
    while queue:
        cost_so_far, position = heapq.heappop(queue)
        if cost_so_far > distance.get(position, math.inf):
            continue
        if position != start and cell_cost(known[position]) < level:
            return NavigationDecision(
                first[position], "leaving feared terrain", "moving"
            )
        neighbours = first_actions if position == start else board.neighbors(position)
        for neighbour in neighbours:
            info = known.get(neighbour)
            if (
                info is None
                or neighbour not in driven
                or not info.traversable
                or neighbour in observation.lidar_obstacles
                or squeezed(position, neighbour, blocked)
            ):
                continue
            new_cost = cost_so_far + terrain_cost(info) + cell_cost(info)
            if new_cost < distance.get(neighbour, math.inf):
                distance[neighbour] = new_cost
                first[neighbour] = neighbour if position == start else first[position]
                heapq.heappush(queue, (new_cost, neighbour))
    return None


class _StrategyBase:
    """State and decision steps shared by all scientific strategies."""

    IMPLEMENTED = True
    SCIENTIFIC = True
    GOAL_REASON = "goal navigation"
    EXPLORE_REASON = "exploration"
    # Anxious variants: stress raises the risk aversion of the route cost.
    STRESS_AVERSE = False

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        self.config = config
        self.seed = seed
        self.board: HexGridBoard | None = None
        self._moves = 0
        self._forced_visits = 0
        self._retreats = 0
        self._looks = 0
        # Crossing feared terrain on purpose: do not retreat halfway.
        self._crossing = False
        # LRTA* heuristic table of the greedy goal fallback.
        self.h_cost: dict[Position, float] = {}
        # Unseen cell the rover is currently driving to (exploration).
        self._explore_target: Position | None = None
        # Risk-sensitive terrain cost of the current decision.
        self._terrain_cost: TerrainCost = mean_cost
        # Fear events seen at the last decision (a new one ends a crossing).
        self._fear_events = 0

    def reset_for_new_goal(self) -> None:
        """Called by the mission controller when the next waypoint is set."""

        self.h_cost.clear()
        self._crossing = False

    def _get_board(self, rover) -> HexGridBoard:
        if self.board is None or self.board.model is not rover.model:
            self.board = HexGridBoard(rover.model)
        return self.board

    def _block_level(self) -> float:
        """Extra cost from which entering a cell is "crossing on purpose"."""

        return 0.0

    def _max_aversion(self) -> float:
        """Summed extra cost an exploration route may have."""

        return math.inf

    def _risk_aversion(self, rover) -> float:
        """Lambda of ``mean + lambda * std`` for this decision."""

        base = float(self.config.risk_aversion)
        if not self.STRESS_AVERSE:
            return base
        return stress_aversion(
            base,
            float(self.config.stress_risk_aversion),
            float(rover.stress_level),
            float(self.config.homeostat.s_crit),
        )

    def choose_next(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        """Decide the next step; look first at a neighbour never seen."""

        self._terrain_cost = risk_cost(
            self._risk_aversion(rover),
            float(self.config.terrain_cost_std.get("SafeRegolith", 0.0)),
        )
        decision = self._decide(rover, observation)
        if (
            decision is not None
            and decision.next_position is not None
            and self.config.look_before_step
            and decision.next_position not in rover.known_terrain
            and not rover.is_facing(decision.next_position)
        ):
            self._looks += 1
            return NavigationDecision(
                None, "looking at unseen terrain", "turning", face=decision.next_position
            )
        return decision

    def _decide(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        raise NotImplementedError

    def _start(
        self,
        rover,
        observation: Observation,
        cell_cost: CellCost | None = None,
    ) -> tuple[HexGridBoard, list[Position], NavigationDecision | None]:
        """Mission end checks, candidate moves and low-battery charging.

        Returns ``(board, actions, decision)``; a decision is final.
        """

        board = self._get_board(rover)
        if observation.mission_mode == "goal_navigation":
            if observation.target is None:
                return board, [], NavigationDecision(None, "missing target", "no_path")
            if observation.position == observation.target:
                return board, [], NavigationDecision(
                    None, "target reached", "goal_reached"
                )
        elif observation.mission_mode == "exploration":
            if observation.coverage_visited >= observation.coverage_target:
                return board, [], NavigationDecision(
                    None, "coverage target reached", "exploration_complete"
                )

        actions = board.actions(observation.position, observation)
        if not actions:
            return board, actions, NavigationDecision(
                None, "no safe neighbour", "no_path"
            )

        # Low battery: go to the nearest known safe cell to charge.
        charge = seek_charging_spot(
            rover, observation, board, cell_cost, terrain_cost=self._terrain_cost
        )
        if charge is not None:
            self._moves += 1
            return board, actions, charge
        return board, actions, None

    def _lrta_step(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        actions: list[Position],
        cell_cost: CellCost | None = None,
    ) -> tuple[Position, float]:
        """One step of LRTA* towards ``observation.target``.

        LSS-LRTA* (Koenig & Sun 2009), the LRTA* of Korf (1990) with a local
        search space. ``h`` starts as the hex distance to the target
        (admissible: no cell costs less than 1) and is learned in
        ``self.h_cost``. Every step the rover:

        1. expands up to ``lrta_lookahead`` cells around itself with A*
           (g = cost from the rover, f = g + h);
        2. learns: ``h`` of every expanded cell is raised to the cheapest
           cost of leaving it through the search frontier (Dijkstra), so a
           dead end or a wall is learned for the whole area at once;
        3. takes the first move towards the frontier cell with the lowest f.

        With ``lrta_lookahead = 1`` this is exactly the classic LRTA*: h of
        the current cell becomes min(cost + h) over its neighbours and the
        rover moves to the best one.

        The cost of entering a known cell is its (risk-sensitive) terrain
        cost plus ``cell_cost`` (learned fear of the anxious rover, caution
        of the fuzzy rover), so cells that stress the rover are avoided
        while a way around exists. An unknown cell costs 1 (free-space
        assumption); known obstacles are never entered. Returns
        ``(chosen move, its cell_cost)``.
        """

        target = observation.target
        assert target is not None
        known = rover.known_terrain
        obstacles = observation.lidar_obstacles
        blocked = board.known_blocker(observation, known)
        self.h_cost[target] = 0.0

        def h(position: Position) -> float:
            value = self.h_cost.get(position)
            if value is None:
                value = float(board.hex_distance(position, target))
            return value

        def extra_of(cell: Position) -> float:
            info = known.get(cell)
            return cell_cost(info) if (cell_cost and info is not None) else 0.0

        def enter_cost(cell: Position) -> float:
            info = known.get(cell)
            if info is None:
                return UNKNOWN_CELL_COST
            return self._terrain_cost(info) + extra_of(cell)

        def successors(cell: Position) -> list[Position]:
            if cell == start:
                return actions
            result = []
            for neighbour in board.neighbors(cell):
                if neighbour in obstacles:
                    continue
                info = known.get(neighbour)
                if info is not None and not info.traversable:
                    continue
                if squeezed(cell, neighbour, blocked):
                    continue
                result.append(neighbour)
            return result

        # 1. A* lookahead from the rover's cell.
        start = observation.position
        limit = max(1, int(self.config.lrta_lookahead))
        g: dict[Position, float] = {start: 0.0}
        first: dict[Position, Position] = {}
        closed: set[Position] = set()
        heap: list[tuple[float, float, Position]] = [(h(start), 0.0, start)]
        while heap and len(closed) < limit:
            _, cost, cell = heapq.heappop(heap)
            if cell in closed or cost > g.get(cell, math.inf):
                continue
            if cell == target and cell != start:
                heapq.heappush(heap, (cost + h(cell), cost, cell))
                break
            closed.add(cell)
            for neighbour in successors(cell):
                if neighbour in closed:
                    continue
                new_cost = cost + enter_cost(neighbour)
                if new_cost < g.get(neighbour, math.inf):
                    g[neighbour] = new_cost
                    first[neighbour] = neighbour if cell == start else first[cell]
                    heapq.heappush(heap, (new_cost + h(neighbour), new_cost, neighbour))
        frontier = {cell for cell in g if cell not in closed}
        if not frontier:
            # Boxed in: the cheapest neighbour, as plain LRTA* would.
            chosen = min(actions, key=lambda a: (enter_cost(a) + h(a), a))
            self.h_cost[start] = max(h(start), enter_cost(chosen) + h(chosen))
            return chosen, extra_of(chosen)

        # 2. Learning: Dijkstra from the frontier back into the closed cells.
        learned = {cell: math.inf for cell in closed}
        queue = [(h(cell), cell) for cell in frontier]
        heapq.heapify(queue)
        while queue:
            value, cell = heapq.heappop(queue)
            if cell in learned and value > learned[cell]:
                continue
            for neighbour in board.neighbors(cell):
                if neighbour not in learned or cell not in successors(neighbour):
                    continue
                candidate = enter_cost(cell) + value
                if candidate < learned[neighbour]:
                    learned[neighbour] = candidate
                    heapq.heappush(queue, (candidate, neighbour))
        for cell, value in learned.items():
            if math.isfinite(value):
                self.h_cost[cell] = max(h(cell), value)

        # 3. Move towards the frontier cell with the lowest f = g + h.
        best = min(frontier, key=lambda cell: (g[cell] + h(cell), h(cell), cell))
        chosen = first[best]
        return chosen, extra_of(chosen)

    def _step_to(self, item: ExploreTarget, reason: str) -> NavigationDecision:
        """Decision for the first step towards an exploration target."""

        block_level = self._block_level()
        self._explore_target = item.target
        self._crossing = block_level > 0 and item.first_step_aversion >= block_level
        if self._crossing:
            self._forced_visits += 1
        self._moves += 1
        status = "forced_fear_visit" if self._crossing else "moving"
        return NavigationDecision(item.first_step, reason, status)

    def _explore(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        cell_cost: CellCost | None,
        allowed: Callable[[Position], bool] | None = None,
        targets: list[ExploreTarget] | None = None,
    ) -> NavigationDecision | None:
        """Drive to the nearest unseen terrain, starting around the rover.

        The extra cost (fear, caution) is a cost here, not a ban: the rover
        prefers a detour and crosses such terrain on purpose when no detour
        exists (``_crossing``, so it does not retreat halfway). Returns
        ``None`` when no unseen cell can be reached.
        """

        if targets is None:
            targets = frontier_targets(
                rover,
                observation,
                board,
                cell_cost,
                max_aversion=self._max_aversion(),
                terrain_cost=self._terrain_cost,
            )
        home: Position | None = rover.path[0] if rover.path else None
        chosen = choose_target(
            targets,
            home,
            float(self.config.explore_home_weight),
            keep=self._explore_target,
            allowed=allowed,
            home_slack=float(self.config.explore_home_slack),
        )
        if chosen is None:
            return None
        return self._step_to(chosen, self.EXPLORE_REASON)

    def statistics(self) -> Mapping[str, int | float]:
        return {
            "moves": self._moves,
            "forced_visits": self._forced_visits,
            "retreats": self._retreats,
            "looks": self._looks,
            "scientific": 1,
        }


EXPLORED = NavigationDecision(None, "nothing left to explore", "exploration_complete")


class OnlineSearchStrategy(_StrategyBase):
    """Plain rover: LRTA* to the goal, exploration of the nearest unseen terrain."""

    GOAL_REASON = "online goal search"
    EXPLORE_REASON = "online exploration"

    def _decide(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        board, actions, decision = self._start(rover, observation)
        if decision is not None:
            return decision

        # Goal navigation: LRTA* (terrain cost only).
        if observation.mission_mode == "goal_navigation":
            chosen, _ = self._lrta_step(rover, observation, board, actions)
            self._moves += 1
            return NavigationDecision(chosen, self.GOAL_REASON, "moving")

        return self._explore(rover, observation, board, None) or EXPLORED


class _AverseStrategy(_StrategyBase):
    """Plain control plus an extra cost per cell and a retreat reflex.

    Subclasses define the extra cost (``_cell_cost``: learned fear or fuzzy
    caution) and when to step back (``_wants_retreat``).
    """

    WEIGHT = "fear_weight"

    def _weight(self) -> float:
        return float(getattr(self.config, self.WEIGHT))

    def _block_level(self) -> float:
        # Weak aversion (decayed or context fear, slight caution) only adds
        # cost; from this level a step counts as crossing on purpose.
        return 0.1 * self._weight()

    def _max_aversion(self) -> float:
        return float(self.config.explore_max_aversion) * self._weight()

    def _retreat_level(self) -> float:
        """Extra cost below which a neighbour is a place to retreat to.

        The same level that makes the rover retreat (fear 0.5 or a fuzzy
        caution of 0.5): a cell the rover would retreat from is not a refuge.
        """

        return float(self.config.retreat_fear_threshold) * self._weight()

    def _cell_cost(self, rover, observation: Observation) -> CellCost:
        raise NotImplementedError

    def _wants_retreat(
        self, rover, observation: Observation, cell_cost: CellCost
    ) -> bool:
        raise NotImplementedError

    def _goal_step(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        actions: list[Position],
        cell_cost: CellCost,
    ) -> NavigationDecision:
        """LRTA* goal step where the extra cost means a detour, not a ban.

        Fear (or fuzzy caution) is added to the cost of entering a cell, so
        the rover goes around terrain that stressed it. Only when the learned
        ``h`` makes the way around more expensive than crossing does it
        cross on purpose, and then it does not retreat halfway
        (``_crossing``).
        """

        chosen, extra = self._lrta_step(rover, observation, board, actions, cell_cost)
        self._crossing = extra > 0.0
        if self._crossing:
            self._forced_visits += 1
        self._moves += 1
        status = "forced_fear_visit" if self._crossing else "moving"
        return NavigationDecision(chosen, self.GOAL_REASON, status)

    def _explore_decision(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        cell_cost: CellCost,
    ) -> NavigationDecision:
        return self._explore(rover, observation, board, cell_cost) or EXPLORED

    def _decide(
        self, rover, observation: Observation
    ) -> NavigationDecision | None:
        cell_cost = self._cell_cost(rover, observation)
        board, actions, decision = self._start(rover, observation, cell_cost)
        if decision is not None:
            return decision

        # A new fear (own alarm or one received by radio) while crossing on
        # purpose: the crossing was decided with weaker fear, so reconsider
        # it. With graded fear a weak (chronic) fear does not make the rover
        # retreat, but it may drive on and get a stronger shock; that shock
        # must be able to turn it back.
        fear_events = int(getattr(rover, "fear_events_own", 0)) + int(
            getattr(rover, "fear_events_received", 0)
        )
        if fear_events != self._fear_events:
            self._fear_events = fear_events
            self._crossing = False

        # On strongly feared terrain: step back to a less feared neighbour.
        if not self._crossing and self._wants_retreat(rover, observation, cell_cost):
            retreat = _retreat_decision(
                rover, board, actions, cell_cost, self._retreat_level()
            ) or _escape_decision(
                rover,
                observation,
                board,
                cell_cost,
                self._block_level(),
                self._terrain_cost,
            )
            if retreat is not None:
                self._retreats += 1
                self._moves += 1
                return retreat

        if observation.mission_mode == "goal_navigation":
            return self._goal_step(rover, observation, board, actions, cell_cost)
        decision = self._explore_decision(rover, observation, board, cell_cost)
        if decision.status == "exploration_complete":
            # Nothing left to explore, but do not stop on feared terrain
            # (e.g. deep inside a shadow area): get out to ground the rover
            # does not fear first.
            current = rover.known_terrain.get(observation.position)
            if current is not None and cell_cost(current) >= self._block_level():
                escape = _escape_decision(
                    rover,
                    observation,
                    board,
                    cell_cost,
                    self._block_level(),
                    self._terrain_cost,
                )
                if escape is not None:
                    self._crossing = False
                    self._retreats += 1
                    self._moves += 1
                    return escape
        return decision


class EmotionalStrategy(_AverseStrategy):
    """Plain rules plus the conditioned-anxiety mechanism (learned fear)."""

    GOAL_REASON = "emotional goal navigation"
    EXPLORE_REASON = "emotional exploration"
    STRESS_AVERSE = True

    def _cell_cost(self, rover, observation: Observation) -> CellCost:
        if not rover.anxiety_memory:
            return lambda info: 0.0
        weight = self._weight()
        # Many cells share a signature; match each one against memory once.
        cache: dict = {}

        def cost(info) -> float:
            signature = info.rgb_signature
            if signature is None:
                return 0.0
            value = cache.get(signature)
            if value is None:
                value = weight * rover.fear_intensity(signature)
                cache[signature] = value
            return value

        return cost

    def _wants_retreat(
        self, rover, observation: Observation, cell_cost: CellCost
    ) -> bool:
        return observation.retreat_required


class FuzzyStrategy(_AverseStrategy):
    """Plain control whose cost and retreat come from fuzzy expert rules.

    No fear memory and no learning: the rules in ``src/navigation/fuzzy.py``
    value every known cell from its terrain risk, slope and energy cost and
    from the rover's own state (hull and wheels, battery, stress).
    """

    WEIGHT = "fuzzy_weight"
    GOAL_REASON = "fuzzy goal navigation"
    EXPLORE_REASON = "fuzzy exploration"

    def _cell_cost(self, rover, observation: Observation) -> CellCost:
        weight = self._weight()
        condition = min(rover.hull_condition, rover.wheel_condition)
        battery = rover.battery
        stress = rover.stress_level
        drain = max(0.0, rover.battery_prev - rover.battery)
        cache: dict = {}

        def cost(info) -> float:
            key = (info.damage_risk, round(info.slope, 1), info.movement_cost)
            value = cache.get(key)
            if value is None:
                value = weight * caution(
                    FuzzyInputs(
                        risk=info.damage_risk,
                        slope=info.slope,
                        energy=info.movement_cost,
                        condition=condition,
                        battery=battery,
                        stress=stress,
                        drain=drain,
                    )
                )
                cache[key] = value
            return value

        return cost

    def _wants_retreat(
        self, rover, observation: Observation, cell_cost: CellCost
    ) -> bool:
        info = rover.known_terrain.get(observation.position)
        weight = self._weight()
        if info is None or weight <= 0:
            return False
        degree = retreat_degree(cell_cost(info) / weight, rover.stress_level)
        return degree >= float(self.config.fuzzy_retreat_level)


class SwarmEmotionalStrategy(EmotionalStrategy):
    """Emotional navigation with own and radio-received fear memory.

    Received radio signatures are already merged into the rover's fear
    memory by the radio layer. In exploration the rovers split the terrain
    and stay within radio range of each other.
    """

    GOAL_REASON = "swarm emotional goal navigation"
    EXPLORE_REASON = "swarm emotional exploration"

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        super().__init__(config, seed)
        # Last position heard from each swarm peer (rover id -> position).
        self.peer_memory: dict[int, Position] = {}
        self._regroups = 0
        self._area_moves = 0
        self._waits = 0
        self.following = False

    def _radio_limit(self) -> int:
        # Keep a margin: two rovers may each move one cell apart per step.
        cohesion = int(self.config.swarm_cohesion_radius)
        return max(cohesion, int(self.config.R_radio) - 2)

    def _within_radio(self, cell: Position, peers: Mapping[int, Position]) -> bool:
        limit = self._radio_limit()
        return all(hex_distance(peer, cell) <= limit for peer in peers.values())

    def _swarm_explore_step(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        cell_cost: CellCost,
        targets: list[ExploreTarget],
    ) -> NavigationDecision | None:
        """Explore the rover's own area while staying with the swarm.

        A target (unseen cell) belongs to the rover's own area when no peer
        is closer to it (ties go to the lower id), so the swarm splits the
        terrain between its rovers. Targets farther than
        ``swarm_cohesion_radius`` from a peer cost extra, and no step leaves
        radio range. Returns ``None`` when there is nothing to do here, so
        the strategy falls back to the common exploration rule.
        """

        peers = dict(observation.swarm_peers)
        self.peer_memory.update(peers)
        position = observation.position
        block_level = self._block_level()
        # Bouncing between two cells (e.g. at the edge of radio range): do not
        # step onto them again, pick another target instead.
        bounce = _bounce_cells(rover)
        if bounce:
            self._explore_target = None

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
                planned = plan_first_step(
                    rover, observation, board, last, cell_cost, self._terrain_cost
                )
                # A strongly feared first step: let the common rule handle it.
                if (
                    planned is not None
                    and planned[0] not in bounce
                    and planned[1] < block_level
                ):
                    self._explore_target = None
                    self._crossing = False
                    self._regroups += 1
                    self._moves += 1
                    return NavigationDecision(
                        planned[0], "regrouping with the swarm", "moving"
                    )
            if self.peer_memory:
                return None
        if not peers:
            return None

        # Once following the leader, keep following until close to it,
        # instead of turning back out at every step.
        if self.following:
            decision = self._follow_step(rover, observation, board, peers, cell_cost)
            if decision is not None:
                return decision

        # 1. Own area within radio range. 2. A peer's area within radio
        # range (help out). 3. New terrain farther away: the swarm moves on
        # together, one step at a time, never leaving radio range.
        tiers = (
            (True, True, "swarm emotional exploration (own area)"),
            (False, True, "swarm emotional exploration (helping a peer)"),
            (False, False, "swarm moving on to new terrain"),
        )
        cohesion = int(self.config.swarm_cohesion_radius)
        radio_limit = self._radio_limit()
        own_id = rover.unique_id
        # Held back: there is new terrain, but every way there leaves radio
        # range or goes back and forth.
        held_back = bool(bounce)
        scored: list[tuple[float, ExploreTarget, bool, bool]] = []
        for item in targets:
            if item.first_step in bounce or item.first_step_aversion >= block_level:
                continue
            if not self._within_radio(item.first_step, peers):
                held_back = True
                continue
            distance = hex_distance(position, item.target)
            in_peer_area = False
            too_far = False
            spread = 0
            for peer_id, peer in peers.items():
                peer_distance = hex_distance(peer, item.target)
                if peer_distance > radio_limit:
                    too_far = True
                if peer_distance < distance or (
                    peer_distance == distance and peer_id < own_id
                ):
                    in_peer_area = True
                spread = max(spread, peer_distance - cohesion)
            score = (
                item.cost
                + SWARM_SPREAD_COST * spread
                + (SWARM_PEER_AREA_COST if in_peer_area else 0.0)
                - (KEEP_TARGET_BONUS if item.target == self._explore_target else 0.0)
            )
            scored.append((score, item, in_peer_area, too_far))
        scored.sort(key=lambda entry: (entry[0], entry[1].target))
        for own_area_only, radio_limited, reason in tiers:
            for _, item, in_peer_area, too_far in scored:
                if (too_far and radio_limited) or (in_peer_area and own_area_only):
                    continue
                self._explore_target = item.target
                self._crossing = False
                self._area_moves += 1
                self._moves += 1
                return NavigationDecision(item.first_step, reason, "moving")

        if held_back:
            return self._follow_or_wait(rover, observation, board, peers, cell_cost)
        return None

    def _follow_or_wait(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        peers: Mapping[int, Position],
        cell_cost: CellCost,
    ) -> NavigationDecision:
        """The swarm is stretched to the edge of radio range.

        The rover with the lowest id in contact leads: it waits, and the other
        rovers drive towards it. So two rovers pulling in opposite directions
        cannot keep each other bouncing at the edge of radio range.
        """

        self._explore_target = None
        leader_id = min(peers)
        if leader_id < rover.unique_id:
            self.following = True
            decision = self._follow_step(rover, observation, board, peers, cell_cost)
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
        cell_cost: CellCost,
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
        planned = plan_first_step(
            rover, observation, board, leader, cell_cost, self._terrain_cost
        )
        if planned is None:
            self.following = False
            return None
        step, fear = planned
        # The route to the leader is the cheapest one including fear: if it
        # still crosses feared terrain, cross on purpose and do not retreat.
        self._crossing = fear >= self._block_level()
        if self._crossing:
            self._forced_visits += 1
        self._regroups += 1
        self._moves += 1
        status = "forced_fear_visit" if self._crossing else "moving"
        return NavigationDecision(step, "following the swarm leader", status)

    def _explore_decision(
        self,
        rover,
        observation: Observation,
        board: HexGridBoard,
        cell_cost: CellCost,
    ) -> NavigationDecision:
        targets = frontier_targets(
            rover,
            observation,
            board,
            cell_cost,
            limit=SWARM_TARGETS,
            max_aversion=self._max_aversion(),
            terrain_cost=self._terrain_cost,
        )
        peers = observation.swarm_peers
        if self.config.swarm_split_area:
            decision = self._swarm_explore_step(
                rover, observation, board, cell_cost, targets
            )
            if decision is not None:
                return decision
        # Common rule (also crossing feared terrain on purpose), but never
        # out of radio range of the swarm and never back and forth.
        bounce = _bounce_cells(rover)
        limit_radio = bool(self.config.swarm_split_area and peers)
        decision = self._explore(
            rover,
            observation,
            board,
            cell_cost,
            allowed=lambda step: step not in bounce
            and (not limit_radio or self._within_radio(step, peers)),
            targets=targets,
        )
        if decision is not None:
            return decision
        if targets and peers:
            self._waits += 1
            return NavigationDecision(None, "waiting for the swarm", "waiting")
        return EXPLORED

    def statistics(self) -> Mapping[str, int | float]:
        return {
            **super().statistics(),
            "regroups": self._regroups,
            "area_moves": self._area_moves,
            "waits": self._waits,
        }


STRATEGY_CLASSES = {
    "online": OnlineSearchStrategy,
    "emotional": EmotionalStrategy,
    "fuzzy": FuzzyStrategy,
    "swarm_emotional": SwarmEmotionalStrategy,
}

__all__ = [
    "STRATEGY_CLASSES",
    "EmotionalStrategy",
    "FuzzyStrategy",
    "OnlineSearchStrategy",
    "SwarmEmotionalStrategy",
]
