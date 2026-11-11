# Anxiety Mechanism at Autonomous Robot

A hex-grid Mars rover simulation of the **conditioned-anxiety** control
mechanism described by Bielecki et al. (ICAISC 2017) and Bielecki & Bielecki
(2025). A rover that experiences a dangerous event learns in a single act to
avoid the circumstances of that event. The project compares this rover with a
rover without anxiety and with a swarm that shares learned dangers by radio.

## At a glance

The project uses [uv](https://docs.astral.sh/uv/); dependencies install on the
first run. Every command accepts `--help`.

### `uv run analyze` — main experiment

Runs the plain algorithm (1 rover), the anxiety mechanism (1 rover) and the
rover swarm (3 rovers) on the same maps in two tests (terrain exploration and
goal navigation), then writes tables, significance tests and figures to
`results/analysis/`.

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
uv run analyze -n 1000 --workers 14   # 6,000 simulations, ~15 min (README results)
```

### `uv run study` — publication study

Runs on **held-out maps** (seeds from 1000; the parameters were calibrated on
seeds 0–39) with the frozen default parameters, and writes
`results/study/report.md`, CSV tables and figures. Four parts:

- `swarm` – controls that separate the effect of more rovers, a shared map and shared fear,
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

```bash
uv run study --workers 10       # 6,600 simulations, ~35 min
```

### `uv run server` — live 3D viewer

Serves the terrain, animated rovers, telemetry and playback controls at
`http://127.0.0.1:8000`.

| Parameter | Default | Meaning |
|---|---|---|
| `--navigation-mode` | `scaffold` | `scaffold` (non-scientific walker), `online` (plain), `emotional` (anxiety), `swarm_emotional` (anxiety shared by radio). |
| `--mission-mode` | `exploration` | `exploration` or `goal_navigation`. |
| `--rovers` | `3` | Number of rovers. |
| `--seed` | `2025` | Map seed. |
| `--max-steps` | `500` | Step limit. |
| `--charging` / `--no-charging` | on | Solar charging. |
| `--host`, `--port` | `127.0.0.1`, `8000` | Server address. |

```bash
uv run server --navigation-mode emotional --rovers 1
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
| Similarity = Euclidean distance between RGB readings with a threshold (2025). | `fear_rgb_tolerance = 24`; camera readings are noisy (σ = 5 per channel), so recognition is not perfect. |
| If the circumstances are similar → stop and reverse until they no longer are; then go around (2025). | Retreat to a less feared neighbour, then fear is a cost in route planning (detour). If no detour exists, the rover crosses on purpose. |
| Small obstacles detectable only by a dedicated sensor damage the robot; a damaged robot continues (2017). | Ventifacts are invisible to LIDAR and damage wheels; overturned rovers get back on their wheels and continue. |
| Spirit stuck in sand; slippery pits trap the robot with probability 1/3 (2025). | Loose sand bogs the rover down (12% per entry). It always digs out: after 3 steps each step succeeds with 35% × wheel condition, at the latest after 12 steps. Digging drains the battery, wears the wheels and raises stress, so the rover survives to learn the fear of sand. |
| The mission leads across two sand pits (2025). | Goal test: 3 legs, each route crosses hazardous terrain; fear memory is kept between legs. |
| "Panic attack": after many dangers the robot fears almost everything (2025). | Measured: fears per rover and rovers that fear plain safe regolith. |
| Simple vs. emotional robot, 11–30 missions each. | Paired seeds (the same maps for every variant), Wilson CIs, McNemar and Wilcoxon tests. |

**Extensions not in the papers:** the swarm with radio sharing of fears,
exponential decay of fear, the homeostat stress formula, solar charging,
A* route planning.

## Results

### Held-out study (`uv run study`, seeds 1000–1099, n = 100)

Parameters were calibrated on seeds 0–39 and frozen; these maps were never
used for tuning. Survival and route completion are per rover; p-values are
paired and Holm-corrected. Full tables and figures: `results/study/report.md`.

| Condition | Exploration: survival | Exploration: terrain discovered | Goal: route completed |
|---|---|---|---|
| Plain ×1 | 9.0% | 19.7% | 76.0% |
| Anxiety ×1 | **78.0%** | 32.8% | 78.0% |
| Plain ×3 | 7.7% | 35.6% | 70.0% |
| Anxiety ×3 (no radio) | **73.0%** | 50.3% | 78.0% |
| Swarm: shared map only | 69.7% | 55.7% | 78.0% |
| Swarm: map + fear | **84.3%** | **60.0%** | 81.0% |

What holds and what does not:

- **The anxiety mechanism works in exploration.** Survival rises from 9% to
  78% (single rover) and from 8% to 73% (three rovers), p < 0.001 after
  correction; discovered terrain also rises (+13 and +15 points, significant).
- **No significant effect in the goal test** with 100 maps (+2 points for
  one rover, +8 points for three rovers, p = 0.05 after correction; with
  1,000 maps the single-rover gain of +5 points is significant, see the main
  experiment below): the plain rover
  already plans cost-aware A* routes around expensive terrain, every leg must
  cross a hazard anyway, and a rover learns only after its first accident.
- **Swarm:** sharing the map of visited cells increases discovered terrain
  (+5.4 points) but not survival. **Sharing fear by radio raises survival**
  (+0.44 survivors per run, 70% → 84% per rover) and discovered terrain
  (+4.3 points), both p < 0.001 after correction. In the goal test no swarm
  element has a significant effect.
- **Ablations:** the key element is the damage-based homeostat. With the
  specification homeostat survival drops to 7% (as without anxiety) and 23 of
  100 rovers end up fearing safe regolith ("panic"). Imprinting on the
  smoothed instead of the instantaneous stress costs 27 points (p < 0.001).
  The slip alarm helps a little (−7 points without it, not significant).
  Context imprinting and fear decay have no measurable effect.
- **Sensitivity:** a lower `S_crit` is better (25 → 74% survival, 75 → 52%);
  the default 40 is not the optimum, so the result is not a product of
  tuning. Fear weight hardly matters (64–74% over 5–100). Fear decay above
  0.005/step makes the rover forget too fast (0.05 → 20%).
- **Camera noise:** a single anxious rover is stable up to σ = 5, drops to
  43% at σ = 15 and to 25% at σ = 30 (still above the plain rover's 9%):
  noise breaks *recognition*, not *learning*. The swarm stays at 83–86% at
  every noise level.

### Main experiment (`uv run analyze -n 1000`, seeds 0–999)

6,000 simulations (1,000 maps × 3 variants × 2 tests, about 15 min with
`--workers 14`). The seeds include the calibration maps 0–39 and the
held-out maps of the study (1000+ are not used). Brackets: 95% Wilson CI;
p-values from paired tests against the plain algorithm (the same maps).
Full report: `results/analysis/report.md`.

**Test 1: terrain exploration**

| Variant | Rovers | Rover survival | Runs without losses | Terrain discovered [%] |
|---|---:|---|---|---|
| Plain algorithm | 1 | 3.7% [3–5] | 3.7% [3–5] | 19.8 ± 8.5 |
| Anxiety mechanism | 1 | **71.5%** [69–74] | 71.5% [69–74] | 31.2 ± 9.7 |
| Rover swarm | 3 | **80.2%** [79–82] | 52.7% [50–56] | **58.8** ± 8.6 |

**Test 2: goal navigation** (3 route points, each leg crosses hazardous terrain)

| Variant | Rovers | Route completed (per rover) | Route points reached | All rovers completed | Mean steps (completed) |
|---|---:|---|---|---|---|
| Plain algorithm | 1 | 68.1% [65–71] | 76.2% | 68.1% [65–71] | 155.9 |
| Anxiety mechanism | 1 | **73.1%** [70–76] | 78.9% | 73.1% [70–76] | 187.7 |
| Rover swarm | 3 | **76.7%** [75–78] | 82.8% | 55.3% [52–58] | 219.7 |

- **Exploration:** anxiety raises survival from 3.7% to 71.5% and discovered
  terrain from 19.8% to 31.2% (both p < 0.001). The swarm discovers three
  times as much terrain as one plain rover.
- **Goal navigation:** with 1,000 maps the anxiety mechanism gives a small
  but significant gain (+5 points, p < 0.001); with 30 or 100 maps it is too
  small to detect. The gain is small because the plain rover already plans
  A* routes that avoid expensive terrain, each leg has to cross a hazard
  anyway, and a rover learns only after its first accident. The anxious
  rover pays with detours (+32 steps on average).
- **Swarm in the goal test:** per rover the swarm does best (76.7%), but
  "all three rovers completed" (55.3%) is lower than for one plain rover,
  because three rovers must all succeed.
- **Limits of one-act learning:** some rovers are lost at their very first
  dangerous event (e.g. an overturn on a steep slope); no learning can help
  there.
- **Panic is rare:** 14 of 1,000 anxious rovers in exploration (24 in the
  goal test) end up fearing safe regolith.

For comparison, the papers report 42% → 73% (2017) and 33% → 77% (2025).

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

- On a cell with fear ≥ 0.5 the rover retreats to a less feared neighbour
  (not while crossing on purpose towards a goal).
- Exploration skips neighbours with fear ≥ 0.1 when other options exist.
- Goal navigation replans an A* route every step over the terrain the rover
  has seen (unknown cells cost 1); emotional variants add `fear_cost`.
- Swarm: an imprint is broadcast within `R_radio = 20` cells; receivers store
  it with gain 0.8 and `source="radio"`. Swarm rovers also share visited cells.
- Swarm exploration (`swarm_split_area`): rovers report their positions by
  radio and split the terrain: each one explores the cells that are closer to
  it than to any peer (its own area). Targets farther than
  `swarm_cohesion_radius = 12` cells from a peer cost extra, and no rover
  moves farther than `R_radio - 2` from a peer, so the swarm stays together.
  When its own area is explored, a rover helps a peer, and then the swarm
  moves on to new terrain together. A rover that loses contact drives back
  to where it last heard the others. When the swarm is stretched to the edge
  of radio range, the rover with the lowest id in contact leads: it waits and
  the others drive towards it, so rovers never bounce back and forth there.
- No circling: when there is nothing new next to an emotional rover (e.g. it
  stands in a small pocket of safe cells surrounded by terrain it fears), it
  plans an A* route to the nearest unvisited cell, with fear as a cost. If no
  detour exists it crosses the feared terrain on purpose and does not retreat
  halfway, as in goal navigation.

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
| `src/navigation/` | `strategies.py` (`online`, `emotional`, `swarm_emotional`), `planning.py` (A*), `energy.py` (drive to charge), `observation.py`, `board.py`, `registry.py`, `types.py`, `scaffold.py` (non-scientific walker). |
| `src/communication/` | `radio.py` (packets), `swarm.py` (broadcast and delivery). |
| `src/model/` | `model.py` (Mesa `HexMultiGrid` model, spawning, multi-leg goals, termination), `types.py` (hex geometry). |
| `src/simulation/session.py` | JSON snapshots for the viewer and headless runs. |
| `src/analytics/` | `metrics.py`, `analysis_plots.py` (figures of `analyze`), `study_plots.py` (figures of `study`), `benchmark.py`, `plots.py`, `reporting.py`, `results.py` (batch pipeline). |
| `root/` | `analyze.py` (main experiment), `study.py` (held-out study), `run.py` (`simulate`), `batch_run.py` (`batch-run`). |
| `server/` | `server.py`, `simulation_runtime.py`, `terrain_data.py`, `index.html`, `styles.css`, `js/` (Three.js scene, terrain, rover models, panels), `textures/`, `models/`. |
| `show_map.py` | Terrain preview (`show_map`). |
| `tests/` | 64 tests in 16 files, including `test_paper_mechanisms.py`, `test_swarm_exploration.py` and `test_navigation_loops.py`. |

Rover statuses shown in the viewer: `active`, `charging`, `recovering`,
`digging_out`, `overturned`, `destroyed`, `goal_reached`.

## Known limitations

- A discrete hex-grid abstraction, not a physics simulation like CoppeliaSim.
- All cells of one terrain type share one colour, so a fear generalises to the
  whole terrain type (camera noise makes recognition imperfect).
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
