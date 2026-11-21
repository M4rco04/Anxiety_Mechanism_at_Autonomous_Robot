# Anxiety Mechanism at Autonomous Robot

A hex-grid rover simulation of the **conditioned-anxiety** control mechanism
described by Bielecki et al. (ICAISC 2017) and Bielecki & Bielecki (2025). A
rover that experiences a dangerous event learns in a single act to avoid the
circumstances of that event. The project compares this rover with a rover
without anxiety, with a rover driven by expert fuzzy rules (no learning) and
with a swarm that shares learned dangers by radio.

The terrain comes from **real maps**: the Jezero crater on Mars and the
Atacama Desert on Earth (`real_maps/`). The seed picks which part of the map
a simulation uses. The drive and traction of the rover follow the measured
Pioneer P3-AT of Wang et al. (2015); loose sand and dust storms are corrected
with field data of Mars rovers.

## At a glance

The project uses [uv](https://docs.astral.sh/uv/); dependencies install on the
first run. Every command accepts `--help`. All simulation commands take
`--map mars|atacama` (default `mars`) and `--cell-m` (size of one hex cell in
metres; default 50 on Mars, 20 in the Atacama).

### `uv run analyze` — main experiment

Runs the plain algorithm (1 rover), the anxiety mechanism (1 rover), the
rover swarm (3 rovers) and the fuzzy rules (1 rover) on the same maps in two
tests (terrain exploration and goal navigation), then writes tables,
significance tests and figures to `results/analysis/`.

| Parameter | Default | Meaning |
|---|---|---|
| `-n`, `--runs` | `30` | Simulations per variant and test. |
| `--workers` | `1` | Parallel processes. |
| `--map` | `mars` | `mars` (Jezero crater) or `atacama` (Atacama Desert). |
| `--cell-m` | map default | Size of one hex cell [m]. |
| `--tests` | both | `exploration` and/or `goal_navigation`. |
| `--base-seed` | `0` | First seed; seeds `base … base+n−1` pick the parts of the map. |
| `--width`, `--height` | `50`, `50` | Map window in hex cells. |
| `--max-steps` | `500` | Step limit per simulation. |
| `--waypoints` | `3` | Route points in the goal test. |
| `--s-crit` | `40` | Stress threshold that triggers a fear imprint. |
| `--charging` / `--no-charging` | on | Solar charging on safe ground. |
| `--rgb-noise` | `5` | Camera noise (std per RGB channel); `0` = perfect recognition. |
| `--traction` / `--no-traction` | on | Terrain physics from the literature; `--no-traction` = simplified physics without the traction, sand-slope and dust-charging models. |
| `--relief` / `--no-relief` | on | Landforms smaller than the mapped units (craters, dunes, outcrops, ravines, boulder fields); `--no-relief` = map classes only. |
| `--map-seed` | base seed | Seed of the simulation drawn on the swarm stress map. |
| `--no-plots` | off | Skip the figures. |
| `--output` | `results/analysis` | Output directory. |

```bash
uv run analyze -n 500 --workers 15 --map mars                                    # results/analysis
uv run analyze -n 500 --workers 15 --map atacama --output results/analysis_atacama
```

### `uv run study` — publication study

Runs on **held-out maps** (seeds from 1000; the parameters were checked on
seeds 0–99 with `uv run tune`) with the frozen default parameters, and writes
`results/study/report.md`, CSV tables and figures. Four parts:

- `swarm` – plain, anxiety and fuzzy rovers, and controls that separate the
  effect of more rovers, a shared map and shared fear,
- `ablation` – the full anxiety model vs. versions without each element,
- `sensitivity` – `S_crit`, fear weight, fear decay and the safe slope
  `alpha_safe`, one at a time,
- `noise` – survival as a function of camera noise.

| Parameter | Default | Meaning |
|---|---|---|
| `-n`, `--runs` | `100` | Simulations per condition and test. |
| `--sens-runs` | `50` | Simulations per sensitivity point. |
| `--parts` | all four | Subset of `swarm ablation sensitivity noise`. |
| `--map`, `--cell-m` | `mars`, map default | Terrain. |
| `--base-seed` | `1000` | First held-out seed. |
| `--workers` | `4` | Parallel processes. |
| `--max-steps` | `500` | Step limit per simulation. |
| `--output` | `results/study` | Output directory. |
| `--report-only` | off | Rebuild tables, figures and the report from the saved `episodes.csv`, without simulations. |

```bash
uv run study --workers 15 --map mars                                     # results/study
uv run study --workers 15 --map atacama --output results/study_atacama
```

### `uv run validate` — model validation

Checks without mission simulations (`results/validation/report.md`): the
real-map pipeline (polygons → raster → windows), the traction model against
the paper and the manufacturer's data, the terrain effects per entry, and sand and dust against Mars-rover field data.

### `uv run tune` — parameter check on calibration maps

Grid of `S_crit` × `fear_weight` × `alpha_safe` for the anxious rover on both
maps, seeds 0–99 (never the held-out seeds of `study`); writes
`results/tuning/`.

### `uv run build-real-maps` — rebuild the map rasters

Rasterizes `real_maps/*.gpkg` (Atacama: inside `atakama_better.zip`) into the
10 m class rasters `real_maps/atacama.npz` and `real_maps/mars.npz`. The
rasters are in the repository; they are also built automatically on first
use if missing.

### `uv run server` — live 3D viewer

Serves the terrain, animated rovers, telemetry and playback controls at
`http://127.0.0.1:8000`.

| Parameter | Default | Meaning |
|---|---|---|
| `--navigation-mode` | `scaffold` | `scaffold` (non-scientific walker), `online` (plain), `emotional` (anxiety), `fuzzy` (expert fuzzy rules), `swarm_emotional` (anxiety shared by radio). |
| `--mission-mode` | `exploration` | `exploration` or `goal_navigation`. |
| `--map`, `--cell-m` | `mars`, map default | Terrain. |
| `--rovers` | `3` | Number of rovers. |
| `--seed` | `2025` | Seed (part of the map). |
| `--max-steps` | `500` | Step limit. |
| `--charging` / `--no-charging` | on | Solar charging. |
| `--host`, `--port` | `127.0.0.1`, `8000` | Server address. |

```bash
uv run server --navigation-mode emotional --rovers 1 --map atacama --seed 7
```

### `uv run simulate` — one headless episode

Prints the end state of every rover and writes `episode.json`.

| Parameter | Default | Meaning |
|---|---|---|
| `--navigation-mode` | `scaffold` | As for the server. |
| `--mission-mode` | `exploration` | `exploration` or `goal_navigation`. |
| `--map`, `--cell-m` | `mars`, map default | Terrain. |
| `--seed` | `42` | Seed (part of the map). |
| `--rovers` | `3` | Number of rovers. |
| `--width`, `--height` | `50`, `50` | Map window. |
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
| `--seed-count` | `30` | Seeds (parts of the map) per variant. |
| `--base-seed` | `0` | First seed. |
| `--rovers` | `3` | Rovers in every variant. |
| `--map`, `--cell-m` | config default | Terrain. |
| `--workers` | `1` | Parallel processes. |
| `--width`, `--height`, `--max-steps` | `50`, `50`, `500` | Map window and step limit. |
| `--config` | – | JSON file with a saved `SimulationConfig`. |
| `--smoke` | off | Quick pipeline check with the non-scientific walker. |
| `--output` | `results/main` | Output directory. |

### `uv run show_map` — terrain preview

Shows a map window in Matplotlib: `uv run show_map --map atacama --seed 3`.

### Tests

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src config server root tests
```

## Real maps

| | Mars: Jezero crater | Earth: Atacama Desert |
|---|---|---|
| Source | `real_maps/jezoro_simplified.gpkg` (geological units, MTM 77.5°E, Mars 2000 sphere) | `real_maps/atakama_better.zip` → `atakama_better.gpkg` (terrain classification, UTM 19S) |
| Extent | 56 × 59 km | 52 × 29 km |
| Classes (area) | ventifacts 36%, boulders 31%, safe regolith 16%, loose sand 9%, steep slope 7% | safe regolith 48%, loose sand 42%, ventifacts 8%, boulders 2%, steep slope 0.3% |
| Hex cell | 50 m (the units are hundreds of metres to kilometres) | 20 m (the classification resolves tens of metres) |
| Window 50×50 | 2.2 × 2.6 km | 0.9 × 1.0 km |

Every polygon carries a `sim_terrain` class. The pipeline
(`src/environment/gpkg.py`, `src/environment/real_maps.py`) reads the
GeoPackage with the standard library (`sqlite3` + a WKB parser, no GDAL),
burns the polygons into a 10 m raster (even-odd scanline fill, holes kept;
small gaps between simplified polygons take the nearest class) and samples
the class under the centre of every hex cell of a window, in Mesa's even-q
hex layout.

**The seed picks the window.** Window origins are drawn at random (seeded)
until a window is a usable test terrain (`WindowRules`): boulders ≤ 25%,
safe regolith ≥ 3% (to start and charge), hazardous ground (sand,
ventifacts, slope) between 5% and 60%, steep slope ≤ 15%, at least three
kinds of hazardous ground (sand, ventifacts, steep slope) with ≥ 1% each,
and ≥ 60% of the cells in one connected drivable area (a gap between two
boulders does not connect). Rovers start only in the largest connected drivable
area, never in a pocket closed off by boulders. On Jezero these rules
reject the boulder fields (Nili Planum), whole etched units and the
1–1.5 km wide crater rim (all of it mapped as steep slope), which would force
every route through the hazard. `real_map_origin_m` in the configuration
fixes a window instead. The same seed always gives the same window, and the
report of `analyze` stores the window's map coordinates per simulation.

**Landforms smaller than the mapped units** are added to the map classes
(`ReliefParams` in `src/environment/real_maps.py`). The maps classify units
of hundreds of metres (Jezero) or tens of metres (Atacama); inside a unit
mapped as "safe regolith" a real rover still meets small craters, dunes,
rock outcrops, gullies and boulder fields. The landforms are fixed to map
coordinates (the same place always has the same crater), they change only
drivable ground (the mapped boulders stay) and their sizes are model
choices of typical dimensions:

| Landform | Map | Terrain | Model |
|---|---|---|---|
| Small impact craters | Mars | steep wall (30–42°), sandy floor, blocky ejecta | Diameter 120–500 m, N(>D) ∝ D⁻² (the usual crater size–frequency slope), 1.2 per km²; 60% fresh (wall, floor, 20% of the ejecta ring boulders), 40% degraded (sand-filled floor only). |
| Wind drifts | Mars | loose sand | Ripple fields and transverse aeolian ridges on the plains: a smooth field (450 m) fixed to the map, on safe regolith. |
| Dune slip faces | both | steep slope at 30–34° (angle of repose of dry sand) | The downwind edge of a sand body at least 120 m long; one prevailing wind per map. |
| Rock outcrops | Atacama | ventifacts with a boulder core | Wind-eroded outcrops and yardangs, 50–200 m across: a smooth field (180 m) on safe regolith; the core (field > 0.73) is boulders. |
| Boulder fields | both | boulders (not traversable) | Rock falls, weathered bedrock and old ejecta: a smooth field (300 m, cells where the field > 0.68) on firm ground (regolith, ventifacts); 20% of the cells in a field are blocks, plus 0.8% single blocks scattered over firm ground. |
| Ravines (quebradas) | Atacama | steep walls, sandy bed | Dry gullies 0.8–2 km long, meandering, in 60% of 1.5 km tiles; the walls are broken by a 60 m ramp every 250 m. |

`--no-relief` (`analyze`) or `real_map_relief=False` uses the map classes
alone (then the "three kinds of hazard" rule is off).

**What a geological map does not contain** is added on top:

- *Slopes*: steep-slope cells 30–42° (the class definition; dune slip faces
  30–34°), safe regolith and sand 2–10°, ventifacts 3–11°, +4° next to a
  steep slope (foothill), so all gentle ground stays below the traction
  limit even for the lowest measured friction (15.7°). Slopes depend only on
  the place on the map.
- *Deep shadow*: cast 2 cells by steep slopes (1 cell by the low dune slip
  faces) away from the sun, whose direction the seed picks.
- *Dust storms*: weather, a smooth random field (value noise) picked by the
  seed, about 9% of a window on average (0–25%).

Mean composition of the accepted windows (seeds 0–299, `results/validation`):

| Map | Safe | Sand | Ventifacts | Steep slope | Boulders | Shadow | Dust | Kinds of hazard ≥ 1% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mars (Jezero) | 59% | 13% | 20% | 4.0% | 4.4% | 2.4% | 9.3% | 4.8 |
| Atacama | 55% | 31% | 6.1% | 2.8% | 5.2% | 2.8% | 9.3% | 4.8 |

(Kinds of hazard: sand, ventifacts, steep slope, shadow, dust.)

Both maps offer every danger of the model. They remain
different test terrains: Jezero is dominated by sharp ventifacts with
scattered craters, the Atacama by loose sand with dunes, outcrops and
ravines (its large ventifact fields lie in windows with more than 60%
hazardous ground and are rejected).

## Relation to the papers

| Paper | In this project |
|---|---|
| Inner detectors track the robot's state; an alarming reading triggers learning. | Homeostat (`src/agents/homeostat.py`) with two alarms: instantaneous stress `>= S_crit`, or wheel slip (speed drop despite constant drive) for 3 steps in a row. |
| One-act learning: a single dangerous experience is enough. | One alarm imprints the terrain with full intensity 1.0. |
| Short-term memory of the last seconds; the whole content is stored as one danger pattern; "avoiding circumstances that preceded the dangerous event is even more efficient". | Short-term memory of the last 5 steps. The current terrain is imprinted with 1.0 and the preceding terrain (context) with up to 0.5, weakened for familiar terrain (latent inhibition), so the rover does not start fearing everything. |
| Similarity = Euclidean distance between RGB readings with a threshold (2025). | `fear_rgb_tolerance = 24`; camera readings are noisy (σ = 5 per channel), so recognition is not perfect. The rover remembers, imprints and plans with what its camera read (the mean of its readings of a cell), never with the true colour. |
| If the circumstances are similar → stop and reverse until they no longer are; then go around (2025). | Retreat the way the rover came (only onto cells it has driven on) to a less feared neighbour, or along the cheapest way out over driven cells when all neighbours are feared as much. Then fear is a cost in route planning (detour). If no detour exists, the rover crosses on purpose (in exploration at most one fully feared cell). |
| Small obstacles detectable only by a dedicated sensor damage the robot; a damaged robot continues (2017). | Ventifacts are invisible to LIDAR and damage wheels; the damaged rover continues. After an overturn the rover gets back on its wheels with probability 70% and continues; otherwise it is broken and its mission ends. |
| Simulated Pioneer robot (2017). | Drive and traction of the Pioneer P3-AT measured by Wang et al. (2015); the agent class keeps the name `Pioneer3DXAgent`. |
| Spirit stuck in sand; slippery pits trap the robot with probability 1/3 (2025). | Loose sand bogs the rover down: 12% per entry on flat sand, rising with the slope to certain embedding at 17° (field data, see *Terrain and rover physics*). It always digs out: after 3 steps each step succeeds with 35% × wheel condition, at the latest after 12 steps. Digging drains the battery, wears the wheels and raises stress, so the rover survives to learn the fear of sand. |
| The mission leads across two sand pits (2025). | Goal test: 3 legs, each route crosses hazardous terrain; fear memory is kept between legs. |
| "Panic attack": after many dangers the robot fears almost everything (2025). | Measured: fears per rover and rovers that fear plain safe regolith. |
| Simple vs. emotional robot, 11–30 missions each. | Paired seeds (the same maps for every variant), 95% CIs (Wilson; bootstrap over simulations for several rovers on one map), McNemar and Wilcoxon tests. |

**Extensions not in the papers:** real terrain maps, the traction model, the swarm with radio sharing of fears,
exponential decay of fear, the homeostat stress formula, the
accumulated-stress alarm, solar charging, LRTA* route search with a local lookahead, exploration
from the start outwards, looking before driving onto unseen ground, and the
fuzzy rover as a comparison without learning.

## Results

All results below use the real maps, the corrected terrain physics
(traction of the P3-AT, sand on slopes, dust blocking solar power), the
boulder fields (a rover cannot squeeze between two boulders), the current
homeostat (`S_crit` 55, `w_wheel` 4), the overturn rule (the rover gets back
up with probability 70%, otherwise it is broken), retreat only onto cells the
rover has driven on, and LRTA* (lookahead 100) as the goal planner of every
variant. A goal-navigation run ends when every rover has reached all 3 route
points. Survival and route completion are per rover; brackets are 95% CIs;
p-values are paired (same maps for every variant). Run on 20 Nov 2026.

Parameter choice: an earlier grid search on seeds 0–99 (`uv run tune`, all 27
combinations of `S_crit` ∈ {30, 40, 50}, `fear_weight` ∈ {20, 30, 50},
`alpha_safe` ∈ {18, 20, 22}) found no combination better than the noise of
100 maps. `S_crit` was later raised from 40 to 55 and `w_wheel` lowered from
8 to 4 so that only larger dangers are recorded as stress (one entry into
sharp rocks imprinted fear 57% of the time before, about 18% now). These two
changes were not tuned; the sensitivity analysis below shows what they cost.
`results/tuning/` still holds the earlier grid.

### Main experiment (`uv run analyze -n 500`, seeds 0–499)

4,000 simulations per map (500 windows × 4 variants × 2 tests). Full
reports: `results/analysis/report.md` (Mars), `results/analysis_atacama/report.md`.

**Mars (Jezero crater)**

| Variant | Rovers | Exploration: survival | Exploration: terrain discovered | Goal: route completed |
|---|---:|---|---|---|
| Plain algorithm | 1 | 5.4% [4–8] | 24.1% | 51.6% [47–56] |
| Anxiety mechanism | 1 | 48.6% [44–53] | 37.4% | 69.6% [65–73] |
| Fuzzy rules | 1 | **94.2%** [92–96] | 52.1% | **82.0%** [78–85] |
| Rover swarm | 3 | 68.1% [65–71] | **60.9%** | 76.7% [74–79] |

**Atacama Desert**

| Variant | Rovers | Exploration: survival | Exploration: terrain discovered | Goal: route completed |
|---|---:|---|---|---|
| Plain algorithm | 1 | 4.6% [3–7] | 26.0% | 59.2% [55–63] |
| Anxiety mechanism | 1 | 57.2% [53–61] | 34.2% | 55.2% [51–60] |
| Fuzzy rules | 1 | **96.4%** [94–98] | 49.1% | **74.0%** [70–78] |
| Rover swarm | 3 | 75.0% [72–77] | **52.4%** | 60.4% [57–64] |

The anxious rover survives exploration far more often than the plain one on
both maps (5.4% → 48.6% and 4.6% → 57.2%) and discovers more terrain, all
p < 0.001. In the goal test it completes more routes on Mars (51.6% → 69.6%,
p < 0.001) but not in the Atacama (59.2% vs 55.2%, p = 0.13).

Why rovers are lost: of the 500 anxious rovers in exploration on Mars, 171
were destroyed (battery, hull or wheels at 0) and 124 lie overturned (a rover
can be both); there were 168 successful recoveries after an overturn. A steep
slope overturns the rover on 65% of entries, so a rover often meets its first
slope with a 30% chance of being lost before it can learn anything from it.

Why the Atacama goal test does not improve: the anxious rover overturns more
often than the plain one there (0.25 vs 0.17 overturned rovers per run) and
needs more steps (243 vs 167). Its detours around feared sand and sharp rocks
lead it along the narrow Atacama ravines, whose walls are steep slopes; on
Mars, where steep ground lies mostly on crater rims, the same detours cost
nothing. 23 anxious rovers were still alive but had not finished the route
when the run ended (4 on Mars).

### Held-out study (`uv run study`, seeds 1000–1099, n = 100)

The parameters were never checked on these windows. 8,800 simulations per
map. Full reports: `results/study/report.md` (Mars),
`results/study_atacama/report.md`.

| Condition | Mars: expl. survival | Mars: discovered | Mars: route completed | Atacama: expl. survival | Atacama: discovered | Atacama: route completed |
|---|---|---|---|---|---|---|
| Plain ×1 | 3% | 23.2% | 37% | 4% | 27.8% | 56% |
| Anxiety ×1 | 43% | 36.8% | 61% | 51% | 37.1% | 48% |
| Fuzzy rules ×1 | **95%** | 51.2% | **74%** | **98%** | 51.3% | **75%** |
| Plain ×3 | 7% | 48.5% | 41% | 5% | 53.9% | 54% |
| Anxiety ×3 (no radio) | 43% | **62.8%** | 63% | 54% | **62.1%** | 45% |
| Swarm: shared map only | 52% | 60.1% | 66% | 60% | 55.5% | 51% |
| Swarm: map + fear | 64% | 59.7% | 73% | 66% | 52.8% | 51% |

What holds and what does not:

- **The anxiety mechanism keeps rovers alive much more often than no
  anxiety.** Exploration survival rises from 3% to 43% on Mars and from 4% to
  51% in the Atacama (held-out, p < 0.001), and the rover discovers more
  terrain (+13.6 and +9.3 percentage points). With three rovers the gain is
  the same (7% → 43%, 5% → 54%).
- **But learned fear is clearly worse than expert rules.** The fuzzy rover
  survives 95–98% of explorations and completes the most routes on both maps
  (exploration p < 0.001 on both maps; goal test p < 0.001 in the Atacama, on
  Mars 74% vs 61%, p = 0.065 after Holm). The rules know in advance that steep
  slopes overturn the rover; the anxious rover has to learn it from an
  overturn, and 30% of overturns end the mission. In an earlier model, where
  every overturn ended with the rover back on its wheels, the anxious rover
  survived 99% and matched the rules: the result depends on whether the first
  lesson about a danger can be lethal.
- **Goal test:** on Mars the anxious rover completes more routes than the
  plain one (37% → 61% held-out, p < 0.001; 52% → 70% on 500 maps). In the
  Atacama it does not (56% vs 48%, p = 0.68 after Holm; 59% vs 55% on 500
  maps); see the explanation above.
- **Swarm:** on Mars, sharing fear by radio raises exploration survival
  (shared map only 52% → map + fear 64%, p = 0.004 after Holm) and route
  completion (66% → 73%, p = 0.028). In the Atacama the same steps
  (60% → 66%) are not significant, but the whole communication together beats
  three anxious rovers without radio (54% → 66%, p = 0.046). Sharing the map
  *lowers* discovered terrain (Atacama 62% → 56%, p < 0.001; Mars 63% → 60%,
  not significant after Holm) because rovers keep within radio range.
- **Ablations:** the key elements are the damage-based homeostat (with the
  specification homeostat survival falls to 8% on Mars and 7% in the
  Atacama) and the instantaneous-stress trigger (18% / 13%); both p < 0.001.
  On Mars both also lower route completion (61% → 45%, p ≤ 0.018). No other
  element changes survival or route completion significantly after Holm
  correction.
- **Sensitivity (first 50 held-out maps):** in the Atacama a more sensitive
  homeostat survives more often (72% at `S_crit` 30 vs 52% at 55 and 36% at
  75); on Mars there is no clear trend (34–50%). Fear that decays slowly helps
  on both maps (decay 0.005: 38% / 52%; 0.05 per step: 18% / 16%). A higher
  fear weight helps exploration (Mars 26% at 5 → 42% at 100). `alpha_safe`
  (14–25°) has almost no effect: gentle ground has at most 15°, steep slopes
  at least 30°. Route completion changes little with any parameter. So the
  less sensitive homeostat makes the rover calmer at some cost in survival in
  the Atacama; the choice of `S_crit` is a trade-off, not an optimum.
- **Camera noise:** the anxious rover keeps 39–43% (Mars) and 50–52%
  (Atacama) survival up to σ = 10, then falls to 21% / 33% at σ = 15 and
  12% / 9% at σ = 30; the swarm stays above the single rover up to σ = 20.
- **Panic is rare:** 2 of 500 anxious rovers in exploration and 2 of 500 in
  the goal test fear safe regolith on Mars (7 and 11 in the Atacama).

For comparison, the papers report survival of 42% → 73% (2017) and 33% → 77%
(2025) without and with anxiety.

## Scientific model

### Terrain and rover physics

The terrain effects come from three kinds of sources, marked in every row
below: **[P]** the paper on the rover's drive (Wang et al. 2015, Pioneer
P3-AT, `sensors-15-09681.pdf`), **[F]** field data of Mars rovers, and
**[M]** model choices without a measured source.

**Rover and traction [P]** (`src/environment/traction.py`). Wang et al.
measured a skid-steered Pioneer P3-AT on a tiled lab floor (Table 1): mass
31 kg, track 0.40 m, tyre radius 0.11 m, wheel width 0.05 m, shear
deformation modulus K = 0.00054 m, rolling resistance f_r = 0.0371, friction
μ = 0.4437 and 0.3093 (left and right wheels). From these:

- *Slip* from the shear stress–displacement law of Eq. (17),
  τ = p·μ·(1 − e^(−j/K)), averaged over the contact patch: the slip ratio is
  the one at which the wheels deliver the force needed against rolling
  resistance and gravity. Above the grip the wheels spin (slip 1).
- *Energy* of a cell = the flat-ground drain × (force needed / rolling
  resistance), capped by the grip; braking downhill costs current too
  (non-regenerative motors), never less than 25% of the flat drain.
- *Traction limit* sin α + f_r cos α = μ: **19.7°** for the mean friction
  (15.7–23.9° over the measured μ). The manufacturer gives a maximum grade of
  40% = 21.8° for the AT, inside this range although not used to fit it.
  The homeostat's safe slope `alpha_safe` = 20° is this limit.
- *Overturn on a crater wall*: the rover slides sideways down the wall and
  rolls when the side force exceeds its lateral grip,
  tan α·|sin ψ| > μ [P + M: the paper gives the grip, not the tip-over
  geometry].
- *Turning*: skid steering scrubs the treads; turning in place the ICR
  coefficient is χ = 1.4728 (Eq. 45; measured 1.4662, Table 3). A turn costs
  μ·χ·(B/2)·angle of friction work, i.e. 16% (20 m cells) or 6% (50 m cells)
  of a flat cell per 60°.
- [M] The heading ψ relative to the fall line is random (the maps have no
  elevation model), μ is drawn between the two measured values per entry,
  the contact patch length is taken as the wheel width, and the lab-floor
  coefficients are used for all firm ground.

**Loose sand [F]**. Wang et al. measured firm ground only. Field data:
rovers in cohesionless sand slip moderately on 10° and embed on 17° (analog
rover tests reported by Rothrock et al. 2016, SPOC); Curiosity's operational
slip model reaches 100% slip at 18°; Curiosity slipped up to 77% in the
Hidden Valley megaripples at about 4° and sank up to 30% of the wheel
diameter (Arvidson et al. 2017). In the model slip and the chance to get
stuck rise as (slope/17°)^4 from the flat-sand values (Beta(3, 5) slip,
mean 0.375; 12% stuck) to full slip and certain embedding at 17°: 0.45 slip
and 23% stuck on 10°, 0.66 and 53% on 14°. The 77% at 4° is not reproduced
(megaripples are not resolved by the maps). [M] A stuck rover always digs
out (3–12 steps), so it lives to learn the fear of sand; Spirit did not.

**Dust storms [F]**. Opportunity's arrays gave about 700 Wh per sol in clear
air and 148 Wh in the July 2007 storm. Charging within 2 cells of a dust
storm runs at 148/700 = **21%** of the normal rate (1.05% instead of 5% per
step; 48 instead of 10 steps from 40 to 90%), and the charging planner
prefers safe ground outside the shade. [M] The camera range in dust is `Binomial(3, p)`,
`p = 0.85 − 0.15·exposure`.

**Ventifacts, deep shadow [M]**. Curiosity's wheels were torn by sharp,
wind-sculpted rocks, and the damage was reduced by avoiding them (Arvidson
et al. 2017; Toupet et al. 2020): this supports the mechanism (wheel damage,
avoidance pays), but no damage rate per distance was found in open sources,
so the values are model choices. The same holds for the cold of deep shadow.

Mean effect of one entry over the slopes of the real-map cells (Monte Carlo
of `apply_effect`, 20,000 draws, `uv run validate`):

| Terrain | Battery [%] | Wheels [%] | Hull [%] | Speed lost | Other |
|---|---|---|---|---|---|
| Safe regolith (2–14°) | 0.75 | 0 | 0 | 1% | Solar charging (5%/step, 1.05% near a dust storm). |
| Loose sand (2–14°) | 3.95 | 0.5 | 0 | 55% | Stuck 21%: 3–12 steps, −2.5 battery and −1 wheels per step. |
| Ventifacts (3–15°) | 1.33 | 6.0 (exponential) | 1.0 | 16% | Seen by the cameras only (LIDAR sees only boulders). |
| Steep slope (30–42°) | 2.0 | 16.8 | 25.9 | 100% | Overturn 65%: −40 hull, −25 wheels; 3 steps to get up with probability 70%, else the rover is broken; no overturn: −2 wheels. |
| Deep shadow (2–14°) | 5.6 | 0 | 0.4 | 1% | +0.75 battery per further step in the shadow; −1.5 hull per step from the 3rd. |
| Dust storm (2–14°) | 1.65 | 0.8 | 0.6 | 1% | Camera range reduced; LIDAR unaffected; charging nearby at 21%. |
| Boulders | – | – | – | – | Not traversable (seen by LIDAR). The rover cannot pass between two boulders: a move between two neighbouring cells is blocked when both cells beside their shared edge are boulders (the gap is narrower than the rover). |

A rover is lost when battery, hull or wheels reach 0 (also while digging out
of sand).

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
| `α`, `α_safe` | Terrain slope and the safe slope [°] | `α_safe = 20` (traction limit of the P3-AT) |
| `w1`, `w2`, `w_hull`, `w_wheel`, `w5` | Weights | `5`, `15`, `4`, `4`, `3` |
| `β` | Smoothing of the total stress | `0.7` |
| `S_crit` | Alarm threshold for `S_inst` | `55` |

Fear is imprinted when `S_inst >= S_crit` or the slip alarm fires
(`slip >= 0.8` for 3 steps in a row). `S_total` is the stress shown in the
viewer and on the swarm stress map.

The thresholds are set so that only a larger danger is recorded. One entry
into sharp rocks (ventifacts, ~6% wheel wear) gives `S_inst` ≈ 37 on average
and an acute imprint in about 18% of entries (before, with `w_wheel = 8` and
`S_crit = 40`: ≈ 61 and 57%, i.e. fear after almost every first contact).
Repeated entries are still learned through the accumulated-stress alarm.

**Accumulated-stress alarm** (chronic danger). Stress below `S_crit` adds up
per terrain: every step without an acute alarm adds

```text
max(0, S_loss − chronic_rest)      S_loss = S_inst without the slope term
```

to the sum of the terrain the rover stands on (`chronic_rest = 15`). When
the sum reaches `chronic_alarm = 60`, that terrain is imprinted like after an
acute event and the sum starts again. So terrain that harms slowly (dust,
sand, a deepening shadow) is learned too. The slope term is left out because
it is a warning, not a loss: with it the rover learned to fear plain regolith
on a gentle slope.

The sums never shrink, so every terrain that costs more than `chronic_rest`
per step is eventually feared, however far apart the entries are. A leaky version is available (`chronic_retention < 1`: every step all
sums are multiplied by it), but it is **off by default**: on maps 0–199 with
`chronic_retention = 0.9` the anxious rover survived exploration 4–5 points
less often (it learned sand and shadow later) and the goal test gained
nothing significant. The "oversensitive" accumulation protects the rover.

**Graded fear.** The imprint intensity follows the size of the danger
instead of always being 1.0:

```text
acute or slip alarm:  I = clamp(S_inst / fear_full_stress, acute_min_intensity, 1)   (110, 0.5)
chronic alarm:        I = chronic_intensity = 0.35
```

Repeated imprints of the same terrain add up (up to 1), so a fear grows with
experience. A terrain can be imprinted again once its fear is below
`reimprint_below = 0.8`. So the strength of a fear follows the size of the
danger (an overturn, with its large hull and wheel damage, imprints close to
1; terrain that harms slowly is learned through the chronic alarm at 0.35),
and repeated lessons make a fear stronger. `graded_fear = False` restores the all-or-nothing imprint.

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
I_context   = 0.5 · I · exp(−exposures / 3)  skipped below 0.15 (I = intensity of the main imprint)
```

- On a cell with fear ≥ 0.5 the rover retreats to a neighbour feared
  less than that (below 0.5), not while crossing on purpose. It flees only
  in a known direction: onto a cell it has driven on itself (preferably the
  one it just came from), never onto terrain it has only seen, which may
  hide a danger the camera does not show. A neighbour that
  is itself strongly feared is no refuge: before this rule a rover that had
  overturned on a slope retreated into sand, got stuck, and "retreated" back
  onto the slope, which it now feared slightly less. When no neighbour
  qualifies (deep inside a shadow), it takes the cheapest way out back over
  cells it has driven on; if there is none, it does not flee and continues
  with normal planning (fear as a route cost).
- A new fear (own imprint or one received by radio) ends a crossing on
  purpose: the crossing was decided with weaker fear. With graded fear a weak
  chronic fear (0.35) does not trigger a retreat, so the rover may drive on
  into the area and get a stronger shock; that shock turns it back.
- An exploring rover never stops on feared terrain: when nothing is left to
  explore it first leaves for ground it does not fear.
- Goal navigation uses **LRTA\*** for every variant, in the LSS-LRTA\* form
  of Koenig & Sun (2009). `h` starts as the hex distance to the goal and is
  learned. Before every step the rover searches `lrta_lookahead = 100` cells
  around itself with A\* over the terrain it knows (unknown cells cost 1,
  known obstacles are never entered), raises `h` of all searched cells to the
  cheapest cost of leaving them (Dijkstra from the search frontier), and takes
  the first move towards the frontier cell with the lowest `g + h`. The cost
  of entering a cell is its terrain cost plus `fear_cost` (anxious rover) or
  the fuzzy caution (fuzzy rover), so cells that stressed the rover are
  avoided while a way around exists. `lrta_lookahead = 1` is the classic
  LRTA\* of Korf (1990): it gets around a 17-cell wall of steep slope too, but
  in ~700 steps instead of ~30, beyond the 500-step limit of a mission.
- A goal mission has 3 goals (`goal_waypoints`); the simulation ends when
  every rover has reached all of them (or at the step limit / when no rover
  is active).
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

### Route cost (all variants)

The cost of driving onto a terrain is a distribution, not a number:
`terrain_costs` is its mean and `terrain_cost_std` its spread. The spread is
the mean times the coefficient of variation of the battery drain of one entry
(Monte Carlo of the terrain effects with the traction and sand-slope models
over the slopes of the real-map cells, `uv run validate`):

| | Safe | Sand | Ventifacts | Slope | Shadow | Dust |
|---|---|---|---|---|---|---|
| mean | 1.0 | 2.0 | 1.8 | 2.5 | 2.0 | 1.8 |
| std | 0.70 | 0.71 | 0.76 | 0.92 | 0.38 | 0.66 |

The planners (LRTA*, exploration, the way to a charging spot, the way out of
feared terrain) do not draw random costs, which would only make the route
jump between replans. They use a risk-sensitive value:

```text
cost = (mean + λ·std) / (1 + λ·std_SafeRegolith)
λ    = risk_aversion (0.5, all variants)
     + stress_risk_aversion · min(1, S / S_crit)   (1.5, anxious variants only)
```

The divisor keeps safe regolith at exactly 1, the unit in which all other
route constants are calibrated. The distribution covers **energy only**:
damage, overturns and getting stuck are what the anxious rover has to learn,
so they are not given to any variant in advance (otherwise the plain rover
would know the dangers too). On the test maps this cost has no measurable
effect on survival or route completion (ablation in the study): the energy
spread is similar for all terrains, so the risk premium hardly changes routes.

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
  route cost in LRTA* and in exploration, like `fear_cost`;
- **retreat:** the rover steps back (only onto cells it has driven on) when the cell it stands on is very risky,
  or risky while its stress is alarming (`fuzzy_retreat_level = 0.5`).

The rules know all terrain types in advance; the anxious rover knows nothing
and has to pay for every lesson with an accident. The comparison shows the
price of learning from experience.

### Other mechanics

- **Overturn:** with probability 70% (`overturn_recovery_probability`) the rover
  gets back on its wheels: 3 steps standing still (2% battery per step, stress
  keeps rising, so it can imprint fear of the slope), then the mission
  continues. Otherwise the overturn breaks the rover and ends its mission.
  `overturn_recovery_probability = 1` restores the always-recovering model,
  `overturn_recovery_steps = 0` makes every overturn final.
- **Solar charging:** below 40% battery the rover drives to the nearest known
  safe regolith and charges 5% per step up to 90% (1.05% per step within 2
  cells of a dust storm; such spots cost the extra charging steps in the
  choice of the charging spot).
- **Turning:** every change of heading costs skid work (see *Terrain and
  rover physics*).

All parameters live in `config/config.py` (`SimulationConfig`,
`HomeostatConfig`) with comments.

## Analysis output

`uv run analyze` writes to `results/analysis/`:

| File | Contents |
|---|---|
| `report.md` | Tables per test, details, significance tests, figures, column reference. |
| `summary.csv` | One row per variant and test (rates with 95% CI, means). |
| `simulations.csv` | One row per simulation (incl. the map and the window's map coordinates). |
| `significance.csv` | Paired tests against the plain algorithm. |
| `plots/survival.png` | Rover survival per test with 95% CI. |
| `plots/goal_completion.png` | Route completion in the goal test. |
| `plots/coverage.png` | Terrain discovered per simulation (exploration). |
| `plots/time_series_<test>.png` | Rovers still operational, mean stress and discovered terrain over time. |
| `plots/swarm_stress_map_<test>.png` | Swarm stress map: routes coloured by stress, the highest stress per cell, fear imprints and lost rovers. |

Other outputs: `results/study*/` (study: `report.md`, `episodes.csv`, tables,
figures), `results/validation/` (`uv run validate`), `results/tuning/`
(`uv run tune`), `results/main/` (`uv run batch-run`). `results/` is not
in git.

## Project structure

| Path | Contents |
|---|---|
| `config/config.py` | All parameters, validation, JSON round-trip, config hash. |
| `src/environment/` | `terrain.py` (terrain classes and effects), `traction.py` (P3-AT traction, Wang et al. 2015), `real_maps.py` (windows of the real maps, slopes, shadow, dust), `gpkg.py` (GeoPackage reader and rasterizer). |
| `real_maps/` | Source maps (`jezoro_simplified.gpkg`, `atakama_better.zip`) and their 10 m class rasters (`mars.npz`, `atacama.npz`). |
| `src/agents/` | `rover.py` (Pioneer rover: sensors, short-term memory, imprinting, recovery, sand, charging), `homeostat.py`, `fear.py`, specification notes `instruction.md`, `rover_moving_instruction.md`. |
| `src/navigation/` | `strategies.py` (`online`, `emotional`, `fuzzy`, `swarm_emotional`), `exploration.py` (nearest unseen terrain), `fuzzy.py` (fuzzy rules), `planning.py` (A* used by the swarm to regroup), `costs.py` (risk-sensitive route cost), `energy.py` (drive to charge), `observation.py`, `board.py`, `registry.py`, `types.py`, `scaffold.py` (non-scientific walker). |
| `src/communication/` | `radio.py` (packets), `swarm.py` (broadcast and delivery). |
| `src/model/` | `model.py` (Mesa `HexMultiGrid` model, spawning, multi-leg goals, termination), `types.py` (hex geometry). |
| `src/simulation/session.py` | JSON snapshots for the viewer and headless runs. |
| `src/analytics/` | `validation.py` (checks of `validate`), `metrics.py`, `analysis_plots.py` (figures of `analyze`), `study_plots.py` (figures of `study`), `benchmark.py`, `plots.py`, `reporting.py`, `results.py` (batch pipeline). |
| `root/` | `analyze.py` (main experiment), `study.py` (held-out study), `validate.py` (`validate`), `tune.py` (`tune`), `run.py` (`simulate`), `batch_run.py` (`batch-run`). |
| `server/` | `server.py`, `simulation_runtime.py`, `terrain_data.py`, `index.html`, `styles.css`, `js/` (Three.js scene, terrain, rover models, panels), `textures/`, `models/`. |
| `show_map.py` | Terrain preview (`show_map`). |
| `tests/` | 112 tests in 19 files, including `test_real_maps_and_traction.py` (maps, rasterizer, traction, sand and dust), `test_paper_mechanisms.py`, `test_swarm_exploration.py`, `test_navigation_loops.py`, `test_exploration_fuzzy.py` and `test_risk_and_graded_fear.py`. |

Rover statuses shown in the viewer: `active`, `charging`, `recovering`,
`digging_out`, `overturned`, `destroyed`, `goal_reached`.

## Known limitations

- A discrete hex-grid abstraction, not a physics simulation like CoppeliaSim.
  One hex is 50 m (Mars) or 20 m (Atacama); a terrain effect is applied once
  per entered cell.
- The traction coefficients were measured on a tiled lab floor (Wang et al.
  2015) and are used for all firm ground. The heading on a slope is random
  (the maps have no elevation model), the contact patch length is assumed,
  and the overturn rule (lateral grip exceeded) is a model choice.
- Sand on slopes and dust are calibrated to a few field data points (open
  sources; several primary papers are paywalled). Ventifact damage and the
  cold of deep shadow have no measured calibration.
- The maps classify terrain into 5 classes; all cells of one class share one
  colour, so a fear generalises to the whole class. On the Atacama, where
  loose sand covers 30% of a window, this makes the anxious rover avoid all
  sand; its longer detours then lead it into steep ravine walls, so in the
  goal test it does not beat the plain rover (see *Results*).
- Window rules reject parts of the maps (mapped boulder units, the crater rim of
  Jezero, the sand-and-ventifact fields of the Atacama); results hold for the
  accepted windows. Windows of different seeds may overlap.
- Shadows, dust storms and the small landforms (craters, drifts, dune slip
  faces, outcrops, ravines) are added to the maps, not mapped; their sizes
  and frequencies are typical values chosen for the model, not measured at
  these sites. Slopes of the gentle classes are drawn per place, not
  measured.
- Terrain acts only when the rover enters a cell. A rover that stands still
  (turning to look, waiting, or done exploring) pays nothing for the terrain.
- The fuzzy rules use the a-priori risk of every terrain type
  (`terrain_risk`), i.e. complete expert knowledge. The anxious rover starts
  with none, so the two are not on equal terms.
- An overturn ends the mission with probability 30% (a model choice, not
  measured). Because steep slopes overturn the rover on 65% of entries, the
  first lesson about a slope can be lethal; the results depend strongly on
  this probability (see *Results*).
- `S_crit` = 55 and `w_wheel` = 4 were set by hand to make the homeostat less
  sensitive, not tuned; the sensitivity analysis shows lower `S_crit` gives
  higher survival.
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
- Wang T., Wu Y., Liang J., Han C., Chen J., Zhao Q. (2015). *Analysis and
  Experimental Kinematics of a Skid-Steering Wheeled Robot Based on a Laser
  Scanner Sensor*. Sensors 15, 9681–9702, doi:10.3390/s150509681
  (`sensors-15-09681.pdf`).
- Pioneer 2/3 user manual, Appendix "Specifications": traversable slope max
  40% grade (AT), 25% (DX).
- Arvidson R. E. et al. (2017). *Mars Science Laboratory Curiosity Rover
  Megaripple Crossings up to Sol 710 in Gale Crater*. Journal of Field
  Robotics 34(3), 495–518.
- Arvidson R. E. et al. (2017). *Relating geologic units and mobility system
  kinematics contributing to Curiosity wheel damage at Gale Crater, Mars*.
  Journal of Terramechanics 73, 73–93.
- Rothrock B. et al. (2016). *SPOC: Deep Learning-based Terrain
  Classification for Mars Rover Missions*. AIAA SPACE 2016 (slip vs slope of
  analog rovers on bedrock, cohesive soil and sand).
- Toupet O. et al. (2020). *Terrain-adaptive wheel speed control on the
  Curiosity Mars rover: Algorithm and flight results*. Journal of Field
  Robotics 37(5).
- NASA/JPL (20 July 2007). Mars Exploration Rover status (Opportunity solar
  energy 700 → 148 Wh per sol in the 2007 dust storm).
