# Anxiety Mechanism at Autonomous Robot

## At a glance

| Command | What it gives you |
|---|---|
| `uv run show_map` | A terrain-only preview: the procedural Mars map in Matplotlib, without rovers or simulation. |
| `uv run simulate` | One complete simulation episode — a single mission from spawn to termination, with one seed and one outcome. |
| `uv run batch-run` | A Monte Carlo experiment: many episodes across variants, mission modes and paired seeds, finished with statistics, plots and a Markdown report. Use `--smoke` until Karol's scientific navigation modes are registered. |
| `uv run server` | The interactive live 3D demo at `http://127.0.0.1:8000`: terrain, animated rovers, instruments, telemetry and playback controls. |

A grid-based Mars rover simulation that implements the **conditioned-anxiety**
control mechanism from the project papers and the internal
`src/agents/instruction.md` / `src/agents/rover_moving_instruction.md`
specifications.

The project contains:

- a deterministic hex-grid Mars terrain generated with Perlin noise,
- a Pioneer 3-DX rover with physical state, LIDAR/RGB sensors, homeostat,
  one-act fear imprinting and radio communication,
- an animated 3D rover viewer built on top of the existing Three.js terrain
  scene,
- ready interfaces for Karol's navigation algorithms,
- a reproducible Monte Carlo experiment and reporting pipeline.

## Quick start

The project uses [uv](https://docs.astral.sh/uv/). Dependencies are installed
automatically on the first run.

```bash
# Terrain-only Matplotlib preview
uv run show_map

# Interactive live 3D terrain + rover mission at http://127.0.0.1:8000
uv run server

# One complete headless simulation episode
uv run simulate --seed 42 --navigation-mode scaffold --max-steps 100

# Non-scientific pipeline smoke test with many scaffold episodes
uv run batch-run --smoke --seed-count 2

# Test suite
uv sync --extra dev
uv run pytest -q
```

The default server uses a 50 × 50 hex map and three rovers. The live viewer
starts in a smooth follow close-up on the first rover; use **View** in the
telemetry panel to return to the whole-terrain overview and click any rover
row to follow that rover again.

## Project structure

### Configuration (`config/`)

| File | Contents | Description |
|---|---|---|
| `config/config.py` | `SimulationConfig`, `HomeostatConfig`, `DEFAULT_CONFIG` | Single source of truth for grid size, seeds, mission modes, homeostat weights, fear parameters, radio range, sensor ranges, terrain costs/risk and display timing. Includes validation, JSON round-trip and a configuration hash. |

### Environment (`src/environment/`)

| File | Main classes / functions | Description |
|---|---|---|
| `terrain.py` | `TerrainPatch`, `TerrainType`, `SafeRegolith`, `Boulders`, `LooseSand`, `Ventifacts`, `SteepSlope`, `DeepShadow`, `DustStorm`, `terrain_at` | Passive hex-cell agents with the original colors plus optical signatures, traversal/cost/risk metadata and seeded physical effects. |
| `generator.py` | `MarsMapGenerator.generate_topography`, `assign_terrain_classes` | Perlin-based terrain zones. The original layout logic and thresholds are preserved; randomness is seeded for reproducible experiments. |

### Robot and communication (`src/agents/`, `src/communication/`)

| File | Main classes / functions | Description |
|---|---|---|
| `agents/homeostat.py` | `Homeostat`, `HomeostatReading` | Implements the stress equation from `instruction.md` §6 with clamping, diagnostics and safe handling of `V_target = 0`. |
| `agents/fear.py` | `FearRecord`, `FearView`, `find_matching_record`, `effective_intensity` | RGB-keyed anxiety memory with tolerance matching, source tracking and exponential decay. |
| `agents/rover.py` | `Pioneer3DXAgent` | Rover state, LIDAR/RGB perception, exposure counters, one-shot imprinting, radio receive/broadcast, step loop and mission status. It delegates route selection to a navigation strategy. |
| `communication/radio.py` | `RadioPacket`, `RadioModule` | Typed radio packets and hex-range helpers. |
| `communication/swarm.py` | `SwarmBroadcaster` | End-of-step queue/delivery, deduplication and range filtering. Packets never cause physical damage. |

### Model and simulation (`src/model/`, `src/simulation/`)

| File | Main classes / functions | Description |
|---|---|---|
| `model/types.py` | `Position`, `RGB`, `hex_distance`, `rgb_distance`, `clamp` | Shared value types and Mesa-compatible odd-q hex geometry. |
| `model/model.py` | `MarsSimulation` | Mesa model using `HexMultiGrid`, seeded RNG, safe spawning, target assignment, scheduler, radio processing, DataCollector and termination logic. |
| `simulation/session.py` | `SimulationSession`, `SimulationSnapshot`, `RoverSnapshot` | JSON-serializable single-episode service used by the headless runner and the live web API. |

### Navigation (`src/navigation/`) — Karol's handoff

| File | Contents | Description |
|---|---|---|
| `types.py` | `Observation`, `TerrainObservation`, `NavigationDecision`, `NavigationStrategy` | Immutable navigation contract. The strategy receives sensors, visited cells, fear memory and mission state. |
| `board.py` | `HexGridBoard` | Mesa hex adapter: bounds, neighbours, known obstacles, rover occupancy and movement costs. |
| `observation.py` | `build_observation` | Builds the sensor/navigation observation from the rover. |
| `scaffold.py` | `ScaffoldStrategy` | Deterministic smoke-only walker. It is **not scientific**. |
| `strategies.py` | strategy skeletons | The scientific algorithms are intentionally left for Karol. They raise `NotImplementedError` until `IMPLEMENTED = True`. |
| `registry.py` | `create_strategy`, `available_strategies` | Scientific-mode gating. Scaffold is always available; unfinished modes fail loudly. |

The scientific variants are:

- `online` — no fear memory,
- `emotional` — own imprinted fear memory,
- `swarm_emotional` — own and radio-received fear.

Mission modes are `exploration` and `goal_navigation`; mode switching is
controlled by the model, not by the strategy.

### Analytics (`src/analytics/`) — Wiktor's pipeline

| File | Main functions | Description |
|---|---|---|
| `metrics.py` | `setup_datacollector`, `collect_rover_metrics`, `collect_episode_metrics` | Mesa DataCollector plus episode/rover metric definitions. |
| `results.py` | `EpisodeResult` | Serializable experiment result. |
| `benchmark.py` | `BenchmarkManager`, `run_episode`, `summarize_episodes`, `paired_comparisons` | Paired-seed Monte Carlo runner, summary statistics, Wilson intervals, Wilcoxon tests and Holm correction. |
| `plots.py` | `plot_all`, `plot_success_rate`, `plot_time_series`, `plot_sample_trajectories`, `plot_fear_activity` | Dark-theme PNG figures matching the Mars viewer. |
| `reporting.py` | `write_report`, `write_single_episode_report`, `print_summary` | Markdown report and console summary. |

### Web server and visualization (`server/`)

| File | Contents | Description |
|---|---|---|
| `server.py` | `WebServer`, HTTP handler | Serves the existing terrain JSON and the live simulation API. `/api/terrain` keeps its original schema. |
| `terrain_data.py` | `terrain_payload_from_model` | Serializes the same terrain used by the simulation. |
| `simulation_runtime.py` | `SimulationRuntime` | Owns one session, serializes concurrent requests and caches terrain. |
| `js/scene/TerrainScene.js` | `TerrainScene` | Robert's scene, extended with rover layer, rover tooltip, camera focus and per-frame rover updates. |
| `js/terrain/*` | terrain renderer/material/effects | Existing terrain visualization; the only additive change is a height lookup for rovers. |
| `js/rover/RoverModel.js` | `RoverModel` | Procedural rover with chassis, six wheels, suspension, solar panel, camera mast, stereo RGB cameras, LIDAR, antenna, battery strip, status ring and shadow. |
| `js/rover/RoverLayer.js` | `RoverLayer` | Smooth movement/turning, wheel rotation, trails, fear markers, radio pulses, dust and selection scan ring. |
| `js/simulation/SimulationClient.js` | `SimulationClient` | Fetches snapshots, drives playback, handles pause/step/reset/speed and visibility changes. |
| `js/simulation/SimulationPanel.js` | `SimulationPanel` | Telemetry, mission step, rover selection, playback and overview controls. |
| `js/ui/RoverTooltip.js` | `RoverTooltip` | Rover devices, battery, stress, damage and fear tooltip. |

### Entry points (`root/`)

| File | Description |
|---|---|
| `root/run.py` | Single-episode headless runner using `SimulationSession`. This is also Marek's final presentation extension point. |
| `root/batch_run.py` | Comparative experiment CLI: variants, mission modes, paired seeds, workers, output directory and Markdown report. |

## Scientific model

### Homeostat

For battery drop `ΔB`, target/current speed `V_zad`/`V_akt`, hull/wheel
condition `C_kadlub`/`C_kolo` and slope `α`:

```text
S_chwilowy =
    w1 * ΔB
  + w2 * max(0, 1 - V_akt / V_zad)
  + w3 * (exp(k * (100 - C_kadlub)) - 1)
  + w4 * (exp(k * (100 - C_kolo)) - 1)
  + w5 * max(0, α - α_bezp)

S_calkowity = β * S_poprzedni + (1 - β) * S_chwilowy
```

Default constants: `w1=5`, `w2=15`, `w3=3`, `w4=2.5`, `w5=2`,
`k=0.05`, `α_bezp=15°`, `β=0.7`, `S_crit=75`. Stress is clamped to
`[0, 100]`; `V_zad <= 0` produces no slip term.

### Conditioned anxiety

When smoothed stress crosses `S_crit`, the rover imprints the current stable
RGB terrain signature in one act. The memory record stores intensity, number of
reinforcements, step, source and source position. Matching uses Euclidean RGB
distance with a configurable tolerance. Effective fear decays exponentially:

```text
intensity_effective = intensity * exp(-fear_decay * age)
fear_cost = fear_weight * intensity_effective
```

The emotional navigation variants are expected to add this cost to movement
evaluation and to retreat when `Observation.retreat_required` is true.
Radio-received signatures enter the same memory with `source="radio"` and never
change battery, hull, wheels or stress directly.

### Hex geometry

Mesa 2.4's `HexGrid` is a `SingleGrid`, so the model uses:

```python
mesa.space.HexMultiGrid(width, height, torus=False)
```

The verified odd-q distance formula is implemented in `src/model/types.py`.
Neighbour queries use the Mesa radius API and never use `moore=True`.

## Live visualization

The viewer shows the real simulation, not a canned animation:

- six wheels with suspension and distance-based wheel rotation,
- solar panel and battery strip,
- camera mast with two RGB lenses,
- spinning LIDAR with optional scan ring,
- radio antenna with send/receive pulses,
- status ring driven by stress, battery strip driven by charge,
- smooth turn-then-drive interpolation and slope pitch/roll,
- path trail, fear markers, radio rings and dust on loose sand/dust storms,
- hover tooltip with device/telemetry state.

The server exposes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/terrain` | Existing terrain payload (unchanged schema). |
| GET | `/api/simulation/state` | Current JSON snapshot. |
| POST | `/api/simulation/step` | Advance one deterministic model step. |
| POST | `/api/simulation/reset` | Reset the session (same seed by default). |
| GET | `/api/simulation/config` | Display/experiment metadata. |

The front end is client-driven: `SimulationClient` requests steps at the
configured display interval and `RoverLayer` interpolates at 60 fps. This keeps
the simulation deterministic and avoids server-side timing races.

## Experiments

```bash
# Scientific comparison after Karol registers the strategies
uv run python root/batch_run.py \
  --variants online emotional swarm_emotional \
  --mission-modes exploration goal_navigation \
  --seed-count 30 \
  --workers 4 \
  --output results/main
```

Results are written to `results/<run>/`:

```text
config.json
environment.json
episodes.csv
steps.csv
agent_steps.csv
summary.csv
summary.json
paired_tests.csv
report.md
plots/
```

The design is paired by seed: every variant and mission mode sees the same
terrain and spawn positions. The report includes confidence intervals, paired
Wilcoxon tests, effect sizes and a clear scientific/smoke-test disclaimer.

## Team handoff

| Owner | Status | Files |
|---|---|---|
| **Antoni** | **Completed — frozen** | Board generator and terrain classes/colors. No handoff tasks remain. |
| **Robert** | **Completed — frozen** | Terrain 3D scene, textures, materials and tooltips. The rover layer is an additive integration; existing terrain behavior is preserved. |
| **Bartosz** | Implemented | Robot state, sensors, homeostat, fear, radio, model integration and live rover visualization. |
| **Karol** | Pending | `src/navigation/strategies.py`. The interfaces, board adapter, observation, registry and acceptance tests are ready. |
| **Marek** | Extension point | `root/run.py` and final presentation orchestration. `SimulationSession`, the live API and viewer are functional. |
| **Wiktor** | Implemented | Metrics, batch experiments, statistics, plots and report. |

## Testing

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src config server root tests
```

The suite covers hex geometry, homeostat, terrain effects, one-shot fear
imprinting, RGB tolerance/decay, radio range and deduplication, rover step
ordering, board filtering, seed reproducibility, analytics artifacts and the
HTTP API. Karol-dependent navigation tests are marked `xfail` with an explicit
expected-failure reason.

## Known limitations

- The simulation is a discrete hex-grid abstraction, not a physics-level
  reproduction of CoppeliaSim/V-REP.
- RGB signatures are class-level optical descriptors; real camera textures and
  lighting are not simulated.
- The scaffold strategy is only a pipeline fixture; its results are stamped
  **not scientific**.
- The papers motivate the mechanism; their reported percentages are not claimed
  to be reproduced by this grid experiment.
- The live viewer uses CDN-hosted Three.js and requires WebGL in the browser.

## References

- Bielecki, Bielecka, Bielecki (2017), *Conditioned Anxiety Mechanism as a Basis
  for a Procedure of Control Module of an Autonomous Robot*, ICAISC 2017,
  LNAI 10246, pp. 390–398.
- Bielecki & Bielecki (2025), *Functional properties of the autonomous robot
  equipped with the model of conditioned anxiety* (`2025_Space_Konf_cor3.docx`).
- Internal specifications: `src/agents/instruction.md`,
  `src/agents/rover_moving_instruction.md`.

## Legacy notes

- The project does **not** use Mesa's `ModularServer`; the browser view is the
  custom Three.js server in `server/`.
- `fuzzy_controller.py` is not part of the current scientific scope; the
  navigation comparison is defined by the three variants above.
- `HexGrid` in older documentation is replaced by `HexMultiGrid` because
  terrain and rovers share cells.
