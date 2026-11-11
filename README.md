# Anxiety Mechanism at Autonomous Robot

A hex-grid Mars rover simulation of the **conditioned-anxiety** control
mechanism described by Bielecki et al. (ICAISC 2017) and Bielecki & Bielecki
(2025). A rover that experiences a dangerous event learns in a single act to
avoid the circumstances of that event. The project compares this rover with a
rover without anxiety, with a rover driven by expert fuzzy rules (no
learning) and with a swarm that shares learned dangers by radio.

## At a glance

The project uses [uv](https://docs.astral.sh/uv/); dependencies install on the
first run. Every command accepts `--help`.

### `uv run analyze` — main experiment

Runs the plain algorithm (1 rover), the anxiety mechanism (1 rover), the
rover swarm (3 rovers) and the fuzzy rules (1 rover) on the same maps in two
tests (terrain exploration and goal navigation), then writes tables,
significance tests and figures to `results/analysis/`.

| Parameter | Default | Meaning |
|---|---|---|
| `-n`, `--runs` | `30` | Simulations per variant and test. |
| `--workers` | `1` | Parallel processes. |
| `--tests` | both | `exploration` and/or `goal_navigation`. |
| `--base-seed` | `0` | First seed; seeds `base … base+n−1` define the maps. |
| `--width`, `--height` | `50`, `50` | Map size in hex cells. |
| `--max-steps` | `500` | Step limit per simulation. |
| `--waypoints` | `3` | Route points in the goal test. |
| `--s-crit` | `40` | Stress threshold that triggers a fear imprint. |
| `--charging` / `--no-charging` | on | Solar charging on safe ground. |
| `--rgb-noise` | `5` | Camera noise (std per RGB channel); `0` = perfect recognition. |
| `--map-seed` | base seed | Seed of the simulation drawn on the swarm stress map. |
| `--no-plots` | off | Skip the figures. |
| `--output` | `results/analysis` | Output directory. |

```bash
uv run analyze -n 1000 --workers 12   # 8,000 simulations (README results)
```

### `uv run study` — publication study

Runs on **held-out maps** (seeds from 1000; the parameters were calibrated on
seeds 0–39 and 5000–5159) with the frozen default parameters, and writes
`results/study/report.md`, CSV tables and figures. Four parts:

- `swarm` – plain, anxiety and fuzzy rovers, and controls that separate the
  effect of more rovers, a shared map and shared fear,
- `ablation` – the full anxiety model vs. versions without each element,
- `sensitivity` – `S_crit`, fear weight and fear decay, one at a time,
- `noise` – survival as a function of camera noise.

| Parameter | Default | Meaning |
|---|---|---|
| `-n`, `--runs` | `100` | Simulations per condition and test. |
| `--sens-runs` | `50` | Simulations per sensitivity point. |
| `--parts` | all four | Subset of `swarm ablation sensitivity noise`. |
| `--base-seed` | `1000` | First held-out seed. |
| `--workers` | `4` | Parallel processes. |
| `--max-steps` | `500` | Step limit per simulation. |
| `--output` | `results/study` | Output directory. |
| `--report-only` | off | Rebuild tables, figures and the report from the saved `episodes.csv`, without simulations. |

```bash
uv run study --workers 12       # 7,400 simulations
```

### `uv run server` — live 3D viewer

Serves the terrain, animated rovers, telemetry and playback controls at
`http://127.0.0.1:8000`.

| Parameter | Default | Meaning |
|---|---|---|
| `--navigation-mode` | `scaffold` | `scaffold` (non-scientific walker), `online` (plain), `emotional` (anxiety), `fuzzy` (expert fuzzy rules), `swarm_emotional` (anxiety shared by radio). |
| `--mission-mode` | `exploration` | `exploration` or `goal_navigation`. |
| `--rovers` | `3` | Number of rovers. |
| `--seed` | `2025` | Map seed. |
| `--max-steps` | `500` | Step limit. |
| `--charging` / `--no-charging` | on | Solar charging. |
| `--host`, `--port` | `127.0.0.1`, `8000` | Server address. |

```bash
uv run server --navigation-mode emotional --rovers 1
uv run server --navigation-mode fuzzy --rovers 1
```

### `uv run simulate` — one headless episode

Prints the end state of every rover and writes `episode.json`.

| Parameter | Default | Meaning |
|---|---|---|
| `--navigation-mode` | `scaffold` | As for the server. |
| `--mission-mode` | `exploration` | `exploration` or `goal_navigation`. |
| `--seed` | `42` | Map seed. |
| `--rovers` | `3` | Number of rovers. |
| `--width`, `--height` | `50`, `50` | Map size. |
| `--max-steps` | from config (`500`) | Step limit. |
| `--config` | – | JSON file with a saved `SimulationConfig`. |
| `--output` | `results/single_seed_<seed>` | Output directory. |

### `uv run batch-run` — general Monte Carlo pipeline

Paired-seed experiments over any variants and mission modes (all with the
same number of rovers), with plots and a Markdown report in `results/main/`.

| Parameter | Default | Meaning |
|---|---|---|
| `--variants` | `online emotional swarm_emotional` | Navigation modes to compare. |
| `--mission-modes` | both | `exploration` and/or `goal_navigation`. |
| `--seed-count` | `30` | Seeds (maps) per variant. |
| `--base-seed` | `0` | First seed. |
| `--rovers` | `3` | Rovers in every variant. |
| `--workers` | `1` | Parallel processes. |
| `--width`, `--height`, `--max-steps` | `50`, `50`, `500` | Map and step limit. |
| `--config` | – | JSON file with a saved `SimulationConfig`. |
| `--smoke` | off | Quick pipeline check with the non-scientific walker. |
| `--output` | `results/main` | Output directory. |

### `uv run show_map` — terrain preview

Shows the generated map in Matplotlib (no parameters).

### Tests

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src config server root tests
```

## Relation to the papers

| Paper | In this project |
|---|---|
| Inner detectors track the robot's state; an alarming reading triggers learning. | Homeostat (`src/agents/homeostat.py`) with two alarms: instantaneous stress `>= S_crit`, or wheel slip (speed drop despite constant drive) for 2 steps in a row. |
| One-act learning: a single dangerous experience is enough. | One alarm imprints the terrain with full intensity 1.0. |
| Short-term memory of the last seconds; the whole content is stored as one danger pattern; "avoiding circumstances that preceded the dangerous event is even more efficient". | Short-term memory of the last 5 steps. The current terrain is imprinted with 1.0 and the preceding terrain (context) with up to 0.5, weakened for familiar terrain (latent inhibition), so the rover does not start fearing everything. |
| Similarity = Euclidean distance between RGB readings with a threshold (2025). | `fear_rgb_tolerance = 24`; camera readings are noisy (σ = 5 per channel), so recognition is not perfect. The rover remembers, imprints and plans with what its camera read (the mean of its readings of a cell), never with the true colour. |
| If the circumstances are similar → stop and reverse until they no longer are; then go around (2025). | Retreat to a less feared neighbour, or along the cheapest known way out when all neighbours are feared as much. Then fear is a cost in route planning (detour). If no detour exists, the rover crosses on purpose (in exploration at most one fully feared cell). |
| Small obstacles detectable only by a dedicated sensor damage the robot; a damaged robot continues (2017). | Ventifacts are invisible to LIDAR and damage wheels; overturned rovers get back on their wheels and continue. |
| Spirit stuck in sand; slippery pits trap the robot with probability 1/3 (2025). | Loose sand bogs the rover down (12% per entry). It always digs out: after 3 steps each step succeeds with 35% × wheel condition, at the latest after 12 steps. Digging drains the battery, wears the wheels and raises stress, so the rover survives to learn the fear of sand. |
| The mission leads across two sand pits (2025). | Goal test: 3 legs, each route crosses hazardous terrain; fear memory is kept between legs. |
| "Panic attack": after many dangers the robot fears almost everything (2025). | Measured: fears per rover and rovers that fear plain safe regolith. |
| Simple vs. emotional robot, 11–30 missions each. | Paired seeds (the same maps for every variant), 95% CIs (Wilson; bootstrap over simulations for several rovers on one map), McNemar and Wilcoxon tests. |

**Extensions not in the papers:** the swarm with radio sharing of fears,
exponential decay of fear, the homeostat stress formula, the
accumulated-stress alarm, solar charging, A* route planning, exploration
from the start outwards, looking before driving onto unseen ground, and the
fuzzy rover as a comparison without learning.

## Results

### Held-out study (`uv run study`, seeds 1000–1099, n = 100)

Parameters were calibrated on seeds 0–39 and 5000–5159 and frozen; these
maps were never used for tuning. Survival and route completion are per rover;
p-values are paired and Holm-corrected. Full tables and figures:
`results/study/report.md`.

| Condition | Exploration: survival | Exploration: terrain discovered | Goal: route completed |
|---|---|---|---|
| Plain ×1 | 10.0% | 39.5% | 75.0% |
| Anxiety ×1 | **97.0%** | 59.9% | 82.0% |
| Fuzzy rules ×1 | **100.0%** | 60.9% | 83.0% |
| Plain ×3 | 25.0% | 67.7% | 72.0% |
| Anxiety ×3 (no radio) | 95.3% | **78.0%** | 79.7% |
| Swarm: shared map only | 97.0% | 71.6% | 85.3% |
| Swarm: map + fear | 96.3% | 73.4% | **86.7%** |

What holds and what does not:

- **The anxiety mechanism works in exploration.** Survival rises from 10% to
  97% (single rover) and from 25% to 95% (three rovers), and discovered
  terrain by 20 and 10 points; all p < 0.001 after correction.
- **The fuzzy rover is not measurably better than the anxious one.** It
  survives every run (100% vs 97%) and discovers 1 point more; neither
  difference is significant. Rules that know every terrain in advance buy
  only the last 3 points of survival; the anxious rover learns the rest
  from its own accidents.
- **No significant effect in the goal test with 100 maps** (anxiety +7
  points, fuzzy +8 points; with 1,000 maps both are significant, see below).
- **Swarm:** communication no longer raises survival in exploration, because
  three anxious rovers without radio already survive 95% of the time.
  Sharing the map *lowers* discovered terrain (78% → 72%, p < 0.001): rovers
  that keep within radio range of each other cover less ground than three
  independent ones. In the goal test the whole swarm communication helps
  (+0.21 rovers per run complete the route, p = 0.012 after correction).
- **Ablations:** the key element is still the damage-based homeostat (with
  the specification homeostat survival drops to 26%, and 24 of 100 rovers
  fear safe regolith) and the instantaneous-stress trigger (64% with the
  smoothed one); both p < 0.001. The accumulated-stress alarm gives +10
  points of survival in exploration but −9 points of completed routes in the
  goal test; neither is significant after correction, so its value is not
  established. The slip alarm, context imprinting, the crossing limit and
  look-before-step have no measurable effect on the anxious rover on these
  maps (without look-before-step 7 of 100 rovers end up fearing safe
  regolith). Without fear decay all 100 rovers survive.
- **Sensitivity:** survival hardly depends on `S_crit` (92–98% over 25–75)
  or on the fear weight (92–100% over 5–100). Fear decay above 0.005/step
  makes the rover forget too fast (0.02 → 76%, 0.05 → 62%).
- **Camera noise:** the anxious rover is stable up to σ = 10 (93–97%), then
  drops to 74% at σ = 15, 47% at σ = 20 and 19% at σ = 30. The swarm drops
  too (83%, 63%, 34%). Since the rover now remembers and plans with what its
  camera read, noise affects every part of the mechanism.

### Main experiment (`uv run analyze -n 1000`, seeds 0–999)

8,000 simulations (1,000 maps × 4 variants × 2 tests). The seeds include the
calibration maps 0–39 (the held-out maps of the study, 1000+, are not used).
Brackets: 95% CI; p-values from paired tests against the plain algorithm
(the same maps). Full report: `results/analysis/report.md`.

**Test 1: terrain exploration**

| Variant | Rovers | Rover survival | Runs without losses | Terrain discovered [%] |
|---|---:|---|---|---|
| Plain algorithm | 1 | 8.3% [7–10] | 8.3% [7–10] | 37.6 ± 17.8 |
| Anxiety mechanism | 1 | **95.8%** [94–97] | 95.8% [94–97] | 58.3 ± 15.9 |
| Fuzzy rules | 1 | **100.0%** | 100.0% | 59.4 ± 14.0 |
| Rover swarm | 3 | **97.4%** [97–98] | 92.8% [91–94] | **71.9** ± 11.5 |

**Test 2: goal navigation** (3 route points, each leg crosses hazardous terrain)

| Variant | Rovers | Route completed (per rover) | Route points reached | All rovers completed | Mean steps (completed) |
|---|---:|---|---|---|---|
| Plain algorithm | 1 | 68.6% [66–71] | 76.6% | 68.6% [66–71] | 157.6 |
| Anxiety mechanism | 1 | **81.1%** [79–83] | 86.6% | 81.1% [79–83] | 220.3 |
| Fuzzy rules | 1 | **79.2%** [77–82] | 85.2% | 79.2% [77–82] | 224.6 |
| Rover swarm | 3 | **83.3%** [82–85] | 88.1% | 65.4% [62–68] | 235.4 |

- **Exploration:** anxiety raises survival from 8.3% to 95.8% and discovered
  terrain from 37.6% to 58.3% (both p < 0.001). The fuzzy rover loses no
  rover in 1,000 runs and discovers 59.4%.
- **Goal navigation:** anxiety (+12.5 points) and the fuzzy rules (+10.6
  points) both complete significantly more routes than the plain rover
  (p < 0.001), at the price of longer routes (about +65 steps).
- **Swarm in the goal test:** per rover the swarm does best (83.3%), but
  "all three rovers completed" (65.4%) is not better than one plain rover
  (p = 0.07), because three rovers must all succeed.
- **Panic is rare:** 9 of 1,000 anxious rovers in exploration (14 in the
  goal test) end up fearing safe regolith.
- **How to read survival in exploration:** a rover that has nothing left to
  explore without crossing more than one feared cell stops and stays where
  it is. It counts as a survivor, and the terrain it did not see is missing
  from "terrain discovered".

For comparison, the papers report 42% → 73% (2017) and 33% → 77% (2025).

### Compared with the previous version of the model

On the same held-out maps (seeds 1000–1099) the previous version gave, for
a single rover: plain 9% survival and 20% discovered terrain, anxiety 78%
and 33%. The change comes from four things: exploration of the nearest
unseen terrain around the start instead of a greedy step to an unvisited
neighbour (the rover used to drive in a line across the map), looking
before driving onto unseen ground, a planned way out of feared terrain, and
the limit on crossing feared terrain in exploration. Previous outputs are
kept in `results/study_before_rework/` and `results/analysis_before_rework/`.

## Scientific model

### Terrain

| Terrain | Effect on entry |
|---|---|
| Safe regolith | Small battery use. Solar charging possible. |
| Loose sand | High battery use, slip, wheel wear 0.5; 12% chance to get stuck (see above). |
| Ventifacts | Wheels −6 (exponential), hull −1; invisible to LIDAR. |
| Steep slope (30–42°) | High battery use; overturn likely (hull −40, wheels −25, then 3 steps to get up); otherwise wheels −2. |
| Deep shadow | Battery −4 growing with exposure; after 3 steps hull −1.5 per step (cold). |
| Dust storm | Battery −1.2, wheels −0.8, hull −0.6, camera range reduced. |
| Boulders | Not traversable (seen by LIDAR). |

A rover is lost when battery, hull or wheels reach 0 (also while digging out of
sand).

### Homeostat

The default (damage-based) model:

```text
S_inst  = w1·ΔB + w2·slip + w_hull·ΔC_hull + w_wheel·ΔC_wheel + w5·max(0, α − α_safe)
S_total = β·S_prev + (1 − β)·S_inst

slip = max(0, 1 − V_actual / V_target)
```

| Symbol | Meaning | Default |
|---|---|---|
| `ΔB` | Battery drop in this step [%] | – |
| `slip` | Relative speed loss (actual vs. target speed) | – |
| `ΔC_hull`, `ΔC_wheel` | Hull / wheel damage taken in this step [%] | – |
| `α`, `α_safe` | Terrain slope and the safe slope [°] | `α_safe = 25` |
| `w1`, `w2`, `w_hull`, `w_wheel`, `w5` | Weights | `5`, `15`, `4`, `8`, `3` |
| `β` | Smoothing of the total stress | `0.7` |
| `S_crit` | Alarm threshold for `S_inst` | `40` |

Fear is imprinted when `S_inst >= S_crit` or the slip alarm fires
(`slip >= 0.7` for 2 steps in a row). `S_total` is the stress shown in the
viewer and on the swarm stress map.

**Accumulated-stress alarm** (chronic danger). Stress below `S_crit` adds up
per terrain: every step without an acute alarm adds

```text
max(0, S_loss − chronic_rest)      S_loss = S_inst without the slope term
```

to the sum of the terrain the rover stands on (`chronic_rest = 10`). When
the sum reaches `chronic_alarm = 40`, that terrain is imprinted like after an
acute event and the sum starts again. So terrain that harms slowly (dust,
sand, a deepening shadow) is learned too. The slope term is left out because
it is a warning, not a loss: with it the rover learned to fear plain regolith
on a gentle slope.

The original formula from the project specification is available as
`HomeostatConfig.specification()`:

```text
S_inst = w1·ΔB + w2·slip + w3·(exp(k·(100 − C_hull)) − 1) + w4·(exp(k·(100 − C_wheel)) − 1)
       + w5·max(0, α − α_safe)
w1=5, w2=15, w3=3, w4=2.5, w5=2, k=0.05, α_safe=15°, β=0.7, S_crit=75 (applied to S_total)
```

It was replaced because its hull/wheel terms measure overall wear
(`C_hull`, `C_wheel` = current condition) instead of the terrain that hurts
now: fear was imprinted on wrong cells (also safe regolith), and the most
damaging terrain never crossed the threshold.

### Anxiety memory and behaviour

```text
I_effective = I · exp(−λ · age)              λ = fear_decay = 0.005 per step
fear_cost   = w_fear · I_effective           w_fear = fear_weight = 30
I_context   = 0.5 · exp(−exposures / 3)      skipped below 0.15
```

- On a cell with fear ≥ 0.5 the rover retreats to a known, less feared
  neighbour (not while crossing on purpose). When every neighbour is feared
  as much (deep inside a shadow), it takes the cheapest known way out.
- Goal navigation replans an A* route every step over the terrain the rover
  has seen (unknown cells cost 1); emotional variants add `fear_cost`.
- Swarm: an imprint is broadcast within `R_radio = 20` cells; receivers store
  it with gain 0.8 and `source="radio"`. Swarm rovers also share the map of
  the terrain they have seen and their visited cells.
- Swarm exploration (`swarm_split_area`): rovers report their positions by
  radio and split the terrain: each one explores the unseen cells that are
  closer to it than to any peer (its own area). Targets farther than
  `swarm_cohesion_radius = 12` cells from a peer cost extra, and no rover
  moves farther than `R_radio - 2` from a peer, so the swarm stays together.
  When its own area is explored, a rover helps a peer, and then the swarm
  moves on to new terrain together. A rover that loses contact drives back
  to where it last heard the others. When the swarm is stretched to the edge
  of radio range, the rover with the lowest id in contact leads: it waits and
  the others drive towards it, so rovers never bounce back and forth there.

### Exploration (all variants)

Every variant explores with the same rule (`src/navigation/exploration.py`):

- The rover drives to the **nearest cell it has not seen yet**, by the
  cheapest route through the terrain it knows. The explored area therefore
  grows outwards from the start; the rover does not run in a line to the
  edge of the map.
- Unseen cells up to `explore_home_slack = 4` cells farther from the start
  than the nearest unseen one cost nothing extra; each cell beyond that
  costs `explore_home_weight = 1`. So the rover works its way around the
  explored disc. With weight 0 it drifts away on open ground.
- The route cost is the terrain cost plus the variant's extra cost: nothing
  (plain), `fear_cost` (anxiety) or the fuzzy caution. Fear is a cost, not a
  ban: the rover prefers a detour.
- Exploration is optional, so the rover does not cross much feared terrain
  only to see more: a route may cross at most `explore_max_aversion = 1`
  fully feared cell (enough to leave a pocket surrounded by feared terrain).
  When all the remaining unseen terrain lies behind more than that, the
  rover stops exploring and stays where it is.
- **Look before step** (`look_before_step`, also in goal navigation): the
  cameras look forward (120°). Before driving onto a neighbour it has never
  seen, the rover turns in place to look at it (one step, no terrain effect).

### Fuzzy rover (`fuzzy`)

The fuzzy rover uses the same control as the plain one. It has no fear
memory and learns nothing. Expert rules (`src/navigation/fuzzy.py`) give
every known cell a caution between 0 and 1 (zero-order Sugeno:
`caution = Σ μᵢ·zᵢ / Σ μᵢ`, AND = minimum):

| IF | THEN caution |
|---|---|
| risk is low AND slope is gentle | none (0) |
| risk is medium | moderate (0.35) |
| risk is high | extreme (1) |
| slope is steep | extreme (1) |
| risk is medium AND rover condition is poor | extreme (1) |
| risk is low AND rover condition is poor | slight (0.15) |
| risk is medium AND stress is alarming | high (0.8) |
| terrain is energy-costly AND battery is low | high (0.8) |
| terrain is energy-costly AND battery drains fast | extreme (1) |

Inputs: the a-priori damage risk of the terrain type (`terrain_risk` in the
configuration), the slope and energy cost of the cell, and the rover's own
state: condition (the worse of hull and wheels), battery, battery used in
the last step and stress. The caution is used in two ways:

- **direction:** `fuzzy_weight · caution` (`fuzzy_weight = 30`) is the extra
  route cost in A* and in exploration, like `fear_cost`;
- **retreat:** the rover steps back when the cell it stands on is very risky,
  or risky while its stress is alarming (`fuzzy_retreat_level = 0.5`).

The rules know all terrain types in advance; the anxious rover knows nothing
and has to pay for every lesson with an accident. The comparison shows the
price of learning from experience.

### Other mechanics

- **Overturn recovery:** 3 steps standing still (2% battery per step); stress keeps rising.
- **Solar charging:** below 40% battery the rover drives to the nearest known
  safe regolith and charges 5% per step up to 90%.

All parameters live in `config/config.py` (`SimulationConfig`,
`HomeostatConfig`) with comments.

## Analysis output

`uv run analyze` writes to `results/analysis/`:

| File | Contents |
|---|---|
| `report.md` | Tables per test, details, significance tests, figures, column reference. |
| `summary.csv` | One row per variant and test (rates with 95% CI, means). |
| `simulations.csv` | One row per simulation. |
| `significance.csv` | Paired tests against the plain algorithm. |
| `plots/survival.png` | Rover survival per test with 95% CI. |
| `plots/goal_completion.png` | Route completion in the goal test. |
| `plots/coverage.png` | Terrain discovered per simulation (exploration). |
| `plots/time_series_<test>.png` | Rovers still operational, mean stress and discovered terrain over time. |
| `plots/swarm_stress_map_<test>.png` | Swarm stress map: routes coloured by stress, the highest stress per cell, fear imprints and lost rovers. |

## Project structure

| Path | Contents |
|---|---|
| `config/config.py` | All parameters, validation, JSON round-trip, config hash. |
| `src/environment/` | `terrain.py` (terrain classes and effects), `generator.py` (seeded Perlin map). |
| `src/agents/` | `rover.py` (Pioneer 3-DX: sensors, short-term memory, imprinting, recovery, sand, charging), `homeostat.py`, `fear.py`, specification notes `instruction.md`, `rover_moving_instruction.md`. |
| `src/navigation/` | `strategies.py` (`online`, `emotional`, `fuzzy`, `swarm_emotional`), `exploration.py` (nearest unseen terrain), `fuzzy.py` (fuzzy rules), `planning.py` (A*), `energy.py` (drive to charge), `observation.py`, `board.py`, `registry.py`, `types.py`, `scaffold.py` (non-scientific walker). |
| `src/communication/` | `radio.py` (packets), `swarm.py` (broadcast and delivery). |
| `src/model/` | `model.py` (Mesa `HexMultiGrid` model, spawning, multi-leg goals, termination), `types.py` (hex geometry). |
| `src/simulation/session.py` | JSON snapshots for the viewer and headless runs. |
| `src/analytics/` | `metrics.py`, `analysis_plots.py` (figures of `analyze`), `study_plots.py` (figures of `study`), `benchmark.py`, `plots.py`, `reporting.py`, `results.py` (batch pipeline). |
| `root/` | `analyze.py` (main experiment), `study.py` (held-out study), `run.py` (`simulate`), `batch_run.py` (`batch-run`). |
| `server/` | `server.py`, `simulation_runtime.py`, `terrain_data.py`, `index.html`, `styles.css`, `js/` (Three.js scene, terrain, rover models, panels), `textures/`, `models/`. |
| `show_map.py` | Terrain preview (`show_map`). |
| `tests/` | 78 tests in 17 files, including `test_paper_mechanisms.py`, `test_swarm_exploration.py`, `test_navigation_loops.py` and `test_exploration_fuzzy.py`. |

Rover statuses shown in the viewer: `active`, `charging`, `recovering`,
`digging_out`, `overturned`, `destroyed`, `goal_reached`.

## Known limitations

- A discrete hex-grid abstraction, not a physics simulation like CoppeliaSim.
- All cells of one terrain type share one colour, so a fear generalises to the
  whole terrain type (camera noise makes recognition imperfect).
- Terrain acts only when the rover enters a cell. A rover that stands still
  (turning to look, waiting, or done exploring) pays nothing, also in a
  shadow or a dust storm.
- The fuzzy rules use the a-priori risk of every terrain type
  (`terrain_risk`), i.e. complete expert knowledge. The anxious rover starts
  with none, so the two are not on equal terms.
- The map generator estimates the slope from the neighbours of a square
  grid, not of the hex grid. It is kept as it is so the maps stay the same.
- The papers motivate the mechanism; their percentages are not claimed to be
  reproduced exactly.
- The viewer loads Three.js from a CDN and needs WebGL.

## References

- Bielecki A., Bielecka M., Bielecki P. (2017). *Conditioned Anxiety Mechanism
  as a Basis for a Procedure of Control Module of an Autonomous Robot*.
  ICAISC 2017, LNAI 10246, pp. 390–398 (`ICAISC_2017.pdf`).
- Bielecki A., Bielecki R. (2025). *Functional properties of the autonomous
  robot equipped with the model of conditioned anxiety*
  (`2025_Space_Konf_cor3.docx`).
