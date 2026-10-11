# Anxiety Mechanism at Autonomous Robot


## 📂 Project Structure

### Simulation Core and Environment Model (`src/model/` & `config/`)

| Directory | File | Class / Function | Method | Description and Responsibility |
| --- | --- | --- | --- | --- |
| `config/` | `config.py` | `SIMULATION_CONFIG` (Dictionary/Constants) | — | Stores simulation configuration constants: grid dimensions, homeostat critical thresholds ($S_{crit}$), radio wave range ($R_{radio}$), default number of rovers, and probability weights of obstacle classes. |
| `src/model/` | `model.py` | `MarsSimulation` (inherits from `mesa.Model`) | `__init__(width, height, num_rovers, rover_type, obstacle_density)` | Initializes the `MultiGrid`, `RandomActivation` scheduler, calls the terrain generator, and generates the rover population. |
| `src/model/` | `model.py` | `MarsSimulation` | `step()` | Main loop of the simulation clock. Triggers agent actions, collects metrics in `DataCollector`, and checks termination conditions. |
| `src/model/` | `model.py` | `MarsSimulation` | `get_neighborhood_info(pos, radius)` | Returns a list of terrain objects from neighboring cells for the rover's sensors (LIDAR and RGB camera). |

### Agent Logic and Emotional Engine (`src/agents/`)

| Directory | File | Class / Function | Method | Description and Responsibility |
| --- | --- | --- | --- | --- |
| `src/agents/` | `rover.py` | `Pioneer3DXAgent` (inherits from `mesa.Agent`) | `__init__(unique_id, model, agent_type)` | Initializes the Pioneer 3-DX rover. Assigns the navigation mode, vitality indicator, and the trauma memory dictionary `anxiety_memory`. |
| `src/agents/` | `rover.py` | `Pioneer3DXAgent` | `step()` | Agent's decision loop: retrieves sensor readings, checks for traumas in memory, selects and executes movement, and triggers homeostat evaluation. |
| `src/agents/` | `rover.py` | `Pioneer3DXAgent` | `_move_standard()`, `_move_fuzzy()`, `_move_emotional()` | Dedicated navigation sub-methods for control paradigms. |
| `src/agents/` | `rover.py` | `Pioneer3DXAgent` | `learn_fear(signature)` | Adds a new terrain optical signature to the `anxiety_memory` trauma database. |
| `src/agents/` | `homeostat.py` | `Homeostat` | `update(current_draw, wheel_slip)` | Tracks the robot's physical state. Calculates the stress level. When it exceeds the critical threshold, it generates a trauma signal. |
| `src/agents/` | `fuzzy_controller.py` | `FuzzyEngine` | `evaluate(distance, roughness)` | Mamdani/Sugeno fuzzy controller. Processes distance and roughness into output values (speed, steering). |

### Physics and Mars Terrain Generation (`src/environment/`)

| Directory | File | Class / Function | Method | Description and Responsibility |
| --- | --- | --- | --- | --- |
| `src/environment/` | `terrain.py` | `TerrainPatch` (inherits from `mesa.Agent`) | `__init__(unique_id, model, terrain_type)` | Passive agent representing a grid cell. Assigns terrain type and a unique RGB optical signature. |
| `src/environment/` | `terrain.py` | `TerrainPatch` | `get_surface_properties()` | Returns terrain properties: friction coefficient, roughness, probability of damage, and RGB color. |
| `src/environment/` | `terrain.py` | `TerrainType` (Enum) | — | Enumeration of obstacle classes (Safe, Boulder, Loose Sand, Ventifacts, Steep Slope, Shadow, Dust Storm). |
| `src/environment/` | `generator.py` | `generate_mars_surface(...)` | (Modular function) | Generates geographically coherent terrain zones on the grid using a 2D Perlin / Simplex Noise algorithm based on a random seed. |

### Network and Swarm Communication (`src/communication/`)

| Directory | File | Class / Function | Method | Description and Responsibility |
| --- | --- | --- | --- | --- |
| `src/communication/` | `radio.py` | `RadioModule` | `broadcast_danger(signature, position)` | Creates and broadcasts a digital radio packet containing the optical signature of the detected threat and the transmitter's position. |
| `src/communication/` | `swarm.py` | `SwarmBroadcaster` | `process_signals(model)` | Analyzes the Euclidean distance between the transmitter and receivers. Forwards the trauma packet (`learn_fear`) to the rest of the rovers in the swarm. |

### Analytics and Batch Experiments (`src/analytics/`)

| Directory | File | Class / Function | Method | Description and Responsibility |
| --- | --- | --- | --- | --- |
| `src/analytics/` | `benchmark.py` | `BenchmarkManager` | `run_comparative_batch(configs, iterations)` | Calls `mesa.batch_run` using multiprocessing for agent variants across hundreds of Monte Carlo repetitions. |
| `src/analytics/` | `metrics.py` | `setup_datacollector(model)` | (Helper function) | Configures the `mesa.DataCollector` object to continuously record the survival rate (`Survival_Rate`), energy level, and generated fears. |

### Graphical Interface and Web Server (`server/` & `root`)

| Directory | File | Class / Function | Method | Description and Responsibility |
| --- | --- | --- | --- | --- |
| `server/` | `server.py` | `rover_portrayal(agent)` | (Mapping function) | Transforms the rover's state into an HTML5 canvas graphical object (Canvas JSON). |
| `server/` | `server.py` | `terrain_portrayal(patch)` | (Mapping function) | Assigns the background color of a grid cell based on 1 of the terrain types. |
| `server/` | `server.py` | `build_server(model_cls)` | (Builder function) | Creates a `ModularServer` instance connecting the 2D CanvasGrid map, interactive sliders, and line charts. |
| `root/` | `run.py` | (Executable script) | — | Startup script that launches the local web server and opens the simulation's graphical interface in the browser. |
| `root/` | `batch_run.py` | (Executable script) | — | Startup script that triggers comparative batch tests and generates statistical reports into CSV/PNG files. |

## 🏜️ Environment and Terrain Classes

The environment on a 2D MultiGrid represents a diverse Martian surface procedurally generated using 2D Perlin Noise. The terrain consists of classes:

* **Safe regolith:** Hard, stable ground (no risk).
* **Large boulders:** Physical obstacles that completely block movement (detected by LIDAR).
* **Loose sand:** Causes wheel slip, speed reduction, and a spike in motor power consumption.
* **Sharp rocks (Ventifacts):** Damage the robot's wheels; invisible to the LIDAR sensor.
* **Steep crater slopes:** Pose a risk of overturning the rover.
* **Deep shadows:** Accelerate battery discharge.
* **Dust storms:** Temporarily limit RGB camera visibility.

