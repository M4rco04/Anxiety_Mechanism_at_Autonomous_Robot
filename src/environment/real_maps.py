"""Terrain from real maps: the Atacama Desert (Earth) and Jezero crater (Mars).

The source maps live in ``real_maps/`` as GeoPackages whose polygons carry a
``sim_terrain`` class (safe regolith, loose sand, ventifacts, steep slope,
boulders). They are tens of kilometres across, so one simulation uses a
window of ``width`` x ``height`` hex cells cut out of the map; the seed picks
the window. The same seed always gives the same window.

Pipeline:

1. ``build_raster`` (``uv run build-real-maps``) burns the polygons into a
   10 m class raster (``real_maps/<key>.npz``). Small gaps between the
   simplified polygons get the class of the nearest pixel.
2. ``RealMapGenerator`` samples the class under the centre of every hex cell
   (one hex = ``cell_m`` metres), so the class proportions of the map are
   kept. A window is accepted only if it is drivable (see ``WindowRules``).
3. What a geological map cannot contain is added on top:
   * landforms smaller than the mapped units (``ReliefParams``): small
     impact craters, wind drifts and dune slip faces on Mars; dune slip
     faces, wind-eroded rock outcrops and dry ravines in the Atacama, fields
     of large boulders on both. They
     are fixed to map coordinates, like the slopes. A window is accepted only
     if it has at least three kinds of hazardous ground;
   * slopes: steep-slope cells get 30-42 deg (the class definition), the
     other classes gentle slopes below the traction limit of the rover, and
     ground next to a steep slope is steeper (foothill);
   * deep shadow: cast by steep slopes away from the sun, whose direction
     the seed picks;
   * dust storms: weather, a smooth random field picked by the seed.
   Slopes depend only on the place on the map, so a place has the same
   slope in every simulation; shadow and dust change with the seed.
"""

from __future__ import annotations

import functools
import math
import random
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.environment.terrain import (
    Boulders,
    DeepShadow,
    DustStorm,
    LooseSand,
    SafeRegolith,
    SteepSlope,
    TerrainPatch,
    Ventifacts,
)
from src.model.types import Position, squeezed

REAL_MAPS_DIR = Path(__file__).resolve().parents[2] / "real_maps"
RASTER_RESOLUTION_M = 10.0

# Raster class codes (0 = no data).
SAFE, SAND, VENT, SLOPE, BOULDER = 1, 2, 3, 4, 5
CLASS_LABELS = {
    SAFE: "Safe regolith",
    SAND: "Loose sand",
    VENT: "Ventifacts",
    SLOPE: "Steep slope",
    BOULDER: "Boulders",
}
CLASS_TERRAIN: dict[int, type[TerrainPatch]] = {
    SAFE: SafeRegolith,
    SAND: LooseSand,
    VENT: Ventifacts,
    SLOPE: SteepSlope,
    BOULDER: Boulders,
}

# Even-q hex layout of Mesa's HexMultiGrid: (x, y) and (x+-1, y), (x+-1, y-1)
# are neighbours for odd x, so odd columns sit half a cell lower.
_EVEN_COL_NEIGHBOURS = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, 1))
_ODD_COL_NEIGHBOURS = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, -1), (-1, -1))


@dataclass(frozen=True)
class RealMapSpec:
    key: str
    title: str
    body: str
    source: str
    member: str | None
    # Default size of one hex cell. The Atacama classification resolves
    # structures of tens of metres, the Jezero geological map of hundreds.
    cell_m: float
    # Landforms smaller than the mapped units, added on top of the map (see
    # ``RealMapGenerator.relief``): "craters", "drifts", "dunes", "outcrops",
    # "ravines", "boulders".
    relief: tuple[str, ...] = ()
    # Direction the prevailing wind blows towards [deg, from east,
    # anticlockwise]; dune slip faces form on the downwind side of sand.
    wind_to_deg: float = 45.0


REAL_MAPS: dict[str, RealMapSpec] = {
    "atacama": RealMapSpec(
        key="atacama",
        title="Atacama Desert (Earth, UTM 19S)",
        body="Earth",
        source="atakama_better.zip",
        member="atakama_better.gpkg",
        cell_m=20.0,
        relief=("dunes", "outcrops", "ravines", "boulders"),
        wind_to_deg=45.0,
    ),
    "mars": RealMapSpec(
        key="mars",
        title="Jezero crater (Mars, MTM 77.5E)",
        body="Mars",
        source="jezoro_simplified.gpkg",
        member=None,
        cell_m=50.0,
        relief=("craters", "drifts", "dunes", "boulders"),
        wind_to_deg=200.0,
    ),
}


@dataclass(frozen=True)
class ReliefParams:
    """Sizes and frequencies of the added landforms (model choices).

    * craters (Mars): small impact craters, diameter 120-500 m with a
      power-law size distribution (N(>D) ~ D^-2), ``crater_density`` per
      km^2. Fresh craters have a steep inner wall, a sand-filled floor
      (aeolian fill) and blocky ejecta; degraded ones only the sand floor.
    * drifts (Mars): fields of wind ripples and transverse aeolian ridges on
      the plains, as loose sand.
    * dunes: the slip face on the downwind side of a sand body at least
      ``dune_min_length_m`` long, at the angle of repose of dry sand.
    * outcrops (Atacama): wind-eroded rock outcrops (ventifacts, yardangs)
      with blocky cores.
    * ravines (Atacama): dry gullies (quebradas) with steep walls and a sandy
      bed; the walls are broken by ramps every ``ravine_ramp_every_m``.
    * boulder fields (both maps): patches of large blocks on firm ground
      (rock falls, weathered bedrock, old ejecta), ``boulder_field_scale_m``
      across, filled with probability ``boulder_field_density``, plus single
      blocks scattered over firm ground with probability ``boulder_scatter``.
    """

    crater_density: float = 1.2
    crater_d_min: float = 120.0
    crater_d_max: float = 500.0
    crater_fresh: float = 0.6
    crater_ejecta_boulders: float = 0.2
    drift_scale_m: float = 450.0
    drift_threshold: float = 0.67
    dune_min_length_m: float = 120.0
    dune_face_deg: tuple[float, float] = (30.0, 34.0)
    outcrop_scale_m: float = 180.0
    outcrop_threshold: float = 0.66
    outcrop_core_threshold: float = 0.73
    ravine_tile_m: float = 1500.0
    ravine_probability: float = 0.6
    ravine_length_m: tuple[float, float] = (800.0, 2000.0)
    ravine_ramp_every_m: float = 250.0
    ravine_ramp_width_m: float = 60.0
    boulder_field_scale_m: float = 300.0
    boulder_field_threshold: float = 0.68
    boulder_field_density: float = 0.2
    boulder_scatter: float = 0.008


@dataclass(frozen=True)
class WindowRules:
    """When a window of the map is a usable test terrain.

    The rover must be able to live there and to learn: enough safe ground to
    start and charge, something dangerous to learn about, but not so much
    that every route is forced through it (on Jezero the crater rim unit,
    all of it steep slope, is 1-1.5 km wide, and etched units cover whole
    windows). The procedural maps had about 25% hazardous terrain.
    """

    max_boulders: float = 0.25
    min_safe: float = 0.03
    min_hazard: float = 0.05
    max_hazard: float = 0.60
    max_slope: float = 0.15
    min_connected: float = 0.60
    # Varied terrain: at least ``min_hazard_types`` of the hazardous ground
    # classes (loose sand, ventifacts, steep slope) cover ``min_type_share``
    # of the window each, so the rover can meet different dangers.
    min_hazard_types: int = 3
    min_type_share: float = 0.01
    attempts: int = 400


# ----------------------------------------------------------------------
# Raster building
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class RealRaster:
    key: str
    classes: np.ndarray  # (rows, cols) uint8, row 0 = south
    resolution: float
    origin: tuple[float, float]
    crs: str

    @property
    def extent_m(self) -> tuple[float, float]:
        rows, cols = self.classes.shape
        return cols * self.resolution, rows * self.resolution


def raster_path(key: str, directory: Path | None = None) -> Path:
    return (directory or REAL_MAPS_DIR) / f"{key}.npz"


def _class_code(label: str) -> int | None:
    for code, prefix in CLASS_LABELS.items():
        if label.strip().lower().startswith(prefix.lower()):
            return code
    return None


def build_raster(
    key: str,
    directory: Path | None = None,
    resolution: float = RASTER_RESOLUTION_M,
) -> Path:
    """Rasterize the GeoPackage of map ``key`` into ``<key>.npz``."""

    from scipy import ndimage

    from src.environment.gpkg import layer_bounds, rasterize_rings, read_features

    spec = REAL_MAPS[key]
    directory = directory or REAL_MAPS_DIR
    source = directory / spec.source
    if not source.exists():
        raise FileNotFoundError(f"Real map source not found: {source}")

    with tempfile.TemporaryDirectory() as tmp:
        if source.suffix.lower() == ".zip":
            with zipfile.ZipFile(source) as archive:
                member = spec.member or next(
                    n for n in archive.namelist() if n.endswith(".gpkg")
                )
                archive.extract(member, tmp)
                gpkg = Path(tmp) / member
        else:
            gpkg = source

        min_x, min_y, max_x, max_y = layer_bounds(gpkg)
        cols = math.ceil((max_x - min_x) / resolution)
        rows = math.ceil((max_y - min_y) / resolution)
        classes = np.zeros((rows, cols), dtype=np.uint8)
        features: dict[int, list] = {}
        for label, rings in read_features(gpkg, "sim_terrain"):
            code = _class_code(label)
            if code is not None:
                features.setdefault(code, []).extend(rings)
        # Overlaps between neighbouring polygons (simplification) go to the
        # more restrictive class: boulders, then slopes, ventifacts, sand.
        for code in (BOULDER, SLOPE, VENT, SAND, SAFE):
            if code in features:
                mask = rasterize_rings(
                    features[code], (min_x, min_y), resolution, (rows, cols)
                )
                classes[mask & (classes == 0)] = code
        crs = _crs_name(gpkg)

    gaps = classes == 0
    if gaps.any() and not gaps.all():
        index = ndimage.distance_transform_edt(
            gaps, return_distances=False, return_indices=True
        )
        classes = classes[index[0], index[1]]

    out = raster_path(key, directory)
    np.savez_compressed(
        out,
        classes=classes,
        resolution=np.float64(resolution),
        origin=np.array([min_x, min_y], dtype=np.float64),
        crs=np.array(crs),
    )
    return out


def _crs_name(gpkg: Path) -> str:
    import sqlite3

    connection = sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT s.definition FROM gpkg_geometry_columns g "
            "JOIN gpkg_spatial_ref_sys s ON s.srs_id = g.srs_id LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    text = row[0] if row else ""
    start = text.find('"')
    end = text.find('"', start + 1)
    return text[start + 1 : end] if start >= 0 and end > start else "unknown"


@functools.lru_cache(maxsize=4)
def load_raster(key: str, directory: str | None = None) -> RealRaster:
    """Load (and build on first use) the class raster of map ``key``."""

    if key not in REAL_MAPS:
        raise ValueError(f"Unknown real map {key!r}; expected one of {tuple(REAL_MAPS)}")
    folder = Path(directory) if directory else REAL_MAPS_DIR
    path = raster_path(key, folder)
    if not path.exists():
        build_raster(key, folder)
    with np.load(path) as data:
        return RealRaster(
            key=key,
            classes=np.ascontiguousarray(data["classes"]),
            resolution=float(data["resolution"]),
            origin=(float(data["origin"][0]), float(data["origin"][1])),
            crs=str(data["crs"]),
        )


# ----------------------------------------------------------------------
# Window sampling
# ----------------------------------------------------------------------
def hex_centres(width: int, height: int, cell_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Centres (metres) of the hex cells of a ``width`` x ``height`` window.

    Arrays are indexed ``[x, y]``. Hex centres are ``cell_m`` apart.
    """

    xs = np.arange(width)[:, None]
    ys = np.arange(height)[None, :]
    odd = xs & 1
    cx = (0.5 + xs * math.sqrt(3.0) / 2.0) * cell_m + 0.0 * ys
    cy = (ys + 1.0 - 0.5 * odd) * cell_m
    return cx, cy


def window_size_m(width: int, height: int, cell_m: float) -> tuple[float, float]:
    return ((width - 1) * math.sqrt(3.0) / 2.0 + 1.0) * cell_m, (height + 1.0) * cell_m


def hex_neighbours(position: Position, width: int, height: int) -> list[Position]:
    x, y = position
    offsets = _ODD_COL_NEIGHBOURS if x & 1 else _EVEN_COL_NEIGHBOURS
    return [
        (x + dx, y + dy)
        for dx, dy in offsets
        if 0 <= x + dx < width and 0 <= y + dy < height
    ]


def _hash_uniform(key: str, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Deterministic uniform [0, 1) per raster pixel (independent of seed)."""

    salt = np.uint64(sum(ord(ch) * 131**i for i, ch in enumerate(key)) % (2**61))
    with np.errstate(over="ignore"):
        z = rows.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
        z ^= cols.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F) + salt
        z ^= z >> np.uint64(30)
        z *= np.uint64(0xBF58476D1CE4E5B9)
        z ^= z >> np.uint64(27)
        z *= np.uint64(0x94D049BB133111EB)
        z ^= z >> np.uint64(31)
    return (z >> np.uint64(11)).astype(np.float64) / float(2**53)


DUST_THRESHOLD = 0.17


def smooth_noise(width: int, height: int, seed: int, octaves: int = 4) -> np.ndarray:
    """Smooth random field (value noise, ``octaves`` octaves), shape (width, height).

    Each octave is a lattice of random values (2, 4, 8, ... cells across the
    window) interpolated with a smoothstep; amplitudes halve per octave. The
    result has mean 0 and standard deviation about 0.12.
    """

    rng = np.random.default_rng([int(seed), 0xD057])
    u = np.linspace(0.0, 1.0, width)[:, None]
    v = np.linspace(0.0, 1.0, height)[None, :]
    field = np.zeros((width, height))
    amplitude, total = 1.0, 0.0
    for octave in range(octaves):
        cells = 2 ** (octave + 1)
        lattice = rng.uniform(-0.5, 0.5, size=(cells + 1, cells + 1))
        fx, fy = u * cells, v * cells
        ix = np.minimum(fx.astype(int), cells - 1)
        iy = np.minimum(fy.astype(int), cells - 1)
        tx = fx - ix
        ty = fy - iy
        tx = tx * tx * (3 - 2 * tx)
        ty = ty * ty * (3 - 2 * ty)
        a = lattice[ix, iy]
        b = lattice[ix + 1, iy]
        c = lattice[ix, iy + 1]
        d = lattice[ix + 1, iy + 1]
        field += amplitude * ((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty)
        total += amplitude
        amplitude *= 0.5
    return field / total


def _key_salt(key: str) -> int:
    return zlib.crc32(key.encode("utf-8"))


def world_noise(key: str, x_m: np.ndarray, y_m: np.ndarray, scale_m: float,
                octaves: int = 3) -> np.ndarray:
    """Smooth field in [0, 1) fixed to map coordinates (value noise).

    The same place of the map always gets the same value, whatever the
    window or the seed. Mean 0.5; ``scale_m`` is the largest feature size.
    """

    total = np.zeros(np.shape(x_m), dtype=float)
    amplitude, norm = 1.0, 0.0
    for octave in range(octaves):
        spacing = scale_m / 2**octave
        fx, fy = x_m / spacing, y_m / spacing
        ix, iy = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
        tx, ty = fx - ix, fy - iy
        tx = tx * tx * (3 - 2 * tx)
        ty = ty * ty * (3 - 2 * ty)
        name = f"{key}/{octave}"
        a = _hash_uniform(name, iy, ix)
        b = _hash_uniform(name, iy, ix + 1)
        c = _hash_uniform(name, iy + 1, ix)
        d = _hash_uniform(name, iy + 1, ix + 1)
        total += amplitude * ((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty)
        norm += amplitude
        amplitude *= 0.5
    return total / norm


def _tile_rng(key: str, i: int, j: int) -> np.random.Generator:
    return np.random.default_rng([_key_salt(key), i + 2**20, j + 2**20])


def _craters(key: str, x_m: np.ndarray, y_m: np.ndarray, p: ReliefParams):
    """Craters (centre x, centre y, radius, fresh) that can touch the window."""

    tile = 1000.0
    reach = p.crater_d_max
    craters = []
    for i in range(int((x_m.min() - reach) // tile), int((x_m.max() + reach) // tile) + 1):
        for j in range(int((y_m.min() - reach) // tile), int((y_m.max() + reach) // tile) + 1):
            rng = _tile_rng(key + "/craters", i, j)
            for _ in range(int(rng.poisson(p.crater_density * (tile / 1000.0) ** 2))):
                cx = (i + rng.random()) * tile
                cy = (j + rng.random()) * tile
                ratio = (p.crater_d_min / p.crater_d_max) ** 2
                diameter = p.crater_d_min / math.sqrt(1.0 - rng.random() * (1.0 - ratio))
                craters.append((cx, cy, diameter / 2.0, bool(rng.random() < p.crater_fresh)))
    return craters


def _ravines(key: str, x_m: np.ndarray, y_m: np.ndarray, p: ReliefParams):
    """Ravine axes (anchor x, anchor y, angle, length, meander phase)."""

    tile = p.ravine_tile_m
    reach = p.ravine_length_m[1] / 2.0
    ravines = []
    for i in range(int((x_m.min() - reach) // tile), int((x_m.max() + reach) // tile) + 1):
        for j in range(int((y_m.min() - reach) // tile), int((y_m.max() + reach) // tile) + 1):
            rng = _tile_rng(key + "/ravines", i, j)
            if rng.random() >= p.ravine_probability:
                continue
            ravines.append((
                (i + rng.random()) * tile,
                (j + rng.random()) * tile,
                rng.uniform(0.0, math.pi),
                rng.uniform(*p.ravine_length_m),
                rng.uniform(0.0, 2 * math.pi),
            ))
    return ravines


def _largest_component_fraction(traversable: np.ndarray) -> float:
    """Largest hex-connected traversable area as a fraction of all cells.

    A move between two boulders does not connect (the gap is too narrow).
    """

    width, height = traversable.shape
    seen = np.zeros_like(traversable, dtype=bool)
    best = 0

    def boulder(position: Position) -> bool:
        px, py = position
        return 0 <= px < width and 0 <= py < height and not traversable[px, py]

    for x in range(width):
        for y in range(height):
            if not traversable[x, y] or seen[x, y]:
                continue
            stack = [(x, y)]
            seen[x, y] = True
            size = 0
            while stack:
                cx, cy = stack.pop()
                size += 1
                for nx, ny in hex_neighbours((cx, cy), width, height):
                    if (
                        traversable[nx, ny]
                        and not seen[nx, ny]
                        and not squeezed((cx, cy), (nx, ny), boulder)
                    ):
                        seen[nx, ny] = True
                        stack.append((nx, ny))
            best = max(best, size)
    return best / float(traversable.size)


def window_stats(classes: np.ndarray) -> dict[str, float]:
    total = float(classes.size)
    return {
        "safe": float(np.sum(classes == SAFE)) / total,
        "sand": float(np.sum(classes == SAND)) / total,
        "ventifacts": float(np.sum(classes == VENT)) / total,
        "slope": float(np.sum(classes == SLOPE)) / total,
        "boulders": float(np.sum(classes == BOULDER)) / total,
    }


class RealMapGenerator:
    """Cut a window out of a real map and turn it into terrain patches."""

    def __init__(
        self,
        map_key: str,
        width: int,
        height: int,
        seed: int,
        *,
        cell_m: float | None = None,
        origin_m: tuple[float, float] | None = None,
        overlays: bool = True,
        relief: bool = True,
        relief_params: ReliefParams | None = None,
        rules: WindowRules | None = None,
        directory: Path | None = None,
    ) -> None:
        if map_key not in REAL_MAPS:
            raise ValueError(f"Unknown real map {map_key!r}")
        self.spec = REAL_MAPS[map_key]
        self.width = int(width)
        self.height = int(height)
        self.seed = int(seed)
        self.cell_m = float(cell_m or self.spec.cell_m)
        self.overlays = bool(overlays)
        self.relief = bool(relief)
        self.relief_params = relief_params or ReliefParams()
        self.rules = rules or WindowRules()
        self.raster = load_raster(map_key, str(directory) if directory else None)
        self.rng = np.random.default_rng([self.seed, 0x4D4150, list(REAL_MAPS).index(map_key)])

        span_x, span_y = window_size_m(self.width, self.height, self.cell_m)
        extent_x, extent_y = self.raster.extent_m
        if span_x > extent_x or span_y > extent_y:
            raise ValueError(
                f"A {self.width}x{self.height} window of {self.cell_m:g} m cells "
                f"({span_x:.0f} x {span_y:.0f} m) does not fit in the {map_key} map "
                f"({extent_x:.0f} x {extent_y:.0f} m)"
            )
        self._max_origin = (extent_x - span_x, extent_y - span_y)
        cx, cy = hex_centres(self.width, self.height, self.cell_m)
        self._cx, self._cy = cx, cy
        self._downwind = self._downwind_neighbours()

        if origin_m is not None:
            self.origin_m = (
                float(np.clip(origin_m[0], 0.0, self._max_origin[0])),
                float(np.clip(origin_m[1], 0.0, self._max_origin[1])),
            )
            self._set_window(self.origin_m)
            self.accepted = self._acceptable(self.classes)
            self.attempts = 1
        else:
            self._choose_window()

    # -- window selection ------------------------------------------------
    def _sample(self, origin: tuple[float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        res = self.raster.resolution
        rows_n, cols_n = self.raster.classes.shape
        cols = np.clip(((origin[0] + self._cx) / res).astype(np.int64), 0, cols_n - 1)
        rows = np.clip(((origin[1] + self._cy) / res).astype(np.int64), 0, rows_n - 1)
        return self.raster.classes[rows, cols], rows, cols

    def _set_window(self, origin: tuple[float, float]) -> None:
        self.origin_m = origin
        self.map_classes, self.rows, self.cols = self._sample(origin)
        if self.relief:
            self.classes, self.slope_override = self._apply_relief(origin, self.map_classes)
        else:
            self.classes = self.map_classes.copy()
            self.slope_override = np.full(self.classes.shape, np.nan)

    def _acceptable(self, classes: np.ndarray) -> bool:
        stats = window_stats(classes)
        rules = self.rules
        if stats["boulders"] > rules.max_boulders or stats["safe"] < rules.min_safe:
            return False
        hazard = stats["sand"] + stats["ventifacts"] + stats["slope"]
        if not rules.min_hazard <= hazard <= rules.max_hazard:
            return False
        if stats["slope"] > rules.max_slope:
            return False
        # Only with the landforms: the map classes alone rarely have all three.
        types = sum(stats[k] >= rules.min_type_share for k in ("sand", "ventifacts", "slope"))
        if self.relief and types < rules.min_hazard_types:
            return False
        return _largest_component_fraction(classes != BOULDER) >= rules.min_connected

    def _choose_window(self) -> None:
        best: tuple[float, tuple[float, float]] | None = None
        for attempt in range(1, self.rules.attempts + 1):
            origin = (
                float(self.rng.uniform(0.0, self._max_origin[0])),
                float(self.rng.uniform(0.0, self._max_origin[1])),
            )
            self._set_window(origin)
            if self._acceptable(self.classes):
                self.accepted, self.attempts = True, attempt
                return
            stats = window_stats(self.classes)
            score = stats["safe"] - stats["boulders"]
            if self.relief:
                score += 0.1 * sum(
                    stats[k] >= self.rules.min_type_share for k in ("sand", "ventifacts", "slope")
                )
            if best is None or score > best[0]:
                best = (score, origin)
        assert best is not None
        self._set_window(best[1])
        self.accepted, self.attempts = False, self.rules.attempts

    # -- relief: landforms smaller than the mapped units ------------------
    def _downwind_neighbours(self) -> np.ndarray:
        """Index (x, y) of the neighbour in the wind direction, -1 at the edge."""

        angle = math.radians(self.spec.wind_to_deg)
        wind = (math.cos(angle), math.sin(angle))
        result = np.full((self.width, self.height, 2), -1, dtype=np.int64)
        for x in range(self.width):
            for y in range(self.height):
                best, best_dot = None, 0.5
                for nx, ny in hex_neighbours((x, y), self.width, self.height):
                    vx = self._cx[nx, ny] - self._cx[x, y]
                    vy = self._cy[nx, ny] - self._cy[x, y]
                    dot = (vx * wind[0] + vy * wind[1]) / math.hypot(vx, vy)
                    if dot > best_dot:
                        best, best_dot = (nx, ny), dot
                if best is not None:
                    result[x, y] = best
        return result

    def _apply_relief(self, origin: tuple[float, float],
                      base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Add the map's landforms; returns classes and slope overrides [deg]."""

        p = self.relief_params
        key = self.spec.key
        cell = self.cell_m
        classes = base.copy()
        override = np.full(base.shape, np.nan)
        x_m = origin[0] + self._cx
        y_m = origin[1] + self._cy
        u = _hash_uniform(key + "/relief", np.floor(y_m).astype(np.int64),
                          np.floor(x_m).astype(np.int64))
        ground = (classes == SAFE) | (classes == SAND) | (classes == VENT)

        if "dunes" in self.spec.relief:
            # Slip face: last sand cell before the sand body ends downwind,
            # with enough sand upwind to build a dune.
            need = max(2, round(p.dune_min_length_m / cell))
            sand = base == SAND
            lo, hi = p.dune_face_deg
            for x in range(self.width):
                for y in range(self.height):
                    if not sand[x, y]:
                        continue
                    dx, dy = self._downwind[x, y]
                    if dx < 0 or sand[dx, dy]:
                        continue
                    run, cx_, cy_ = 1, x, y
                    while run < need:
                        up = self._upwind(cx_, cy_)
                        if up is None or not sand[up]:
                            break
                        cx_, cy_ = up
                        run += 1
                    if run >= need:
                        classes[x, y] = SLOPE
                        override[x, y] = lo + (hi - lo) * u[x, y]

        if "drifts" in self.spec.relief:
            field = world_noise(key + "/drifts", x_m, y_m, p.drift_scale_m)
            classes[(classes == SAFE) & (field > p.drift_threshold)] = SAND

        if "outcrops" in self.spec.relief:
            field = world_noise(key + "/outcrops", x_m, y_m, p.outcrop_scale_m)
            rock = (classes == SAFE) & (field > p.outcrop_threshold)
            classes[rock] = VENT
            classes[rock & (field > p.outcrop_core_threshold)] = BOULDER

        if "ravines" in self.spec.relief:
            for ax, ay, theta, length, phase in _ravines(key, x_m, y_m, p):
                tx, ty = math.cos(theta), math.sin(theta)
                rx, ry = x_m - ax, y_m - ay
                along = rx * tx + ry * ty
                across = -rx * ty + ry * tx - 40.0 * np.sin(2 * math.pi * along / 300.0 + phase)
                inside = (np.abs(along) <= length / 2) & ground
                bed = inside & (np.abs(across) < 0.6 * cell)
                ramp = np.mod(along + length / 2, p.ravine_ramp_every_m) < p.ravine_ramp_width_m
                wall = inside & ~bed & (np.abs(across) < 1.6 * cell) & ~ramp
                classes[bed] = SAND
                classes[wall] = SLOPE
                override[bed] = np.nan

        if "craters" in self.spec.relief:
            for cx, cy, radius, fresh in _craters(key, x_m, y_m, p):
                dist = np.hypot(x_m - cx, y_m - cy)
                if dist.min() > 1.6 * radius:
                    continue
                floor = ground & (dist < 0.55 * radius)
                classes[floor] = SAND
                override[floor] = np.nan
                if not fresh:
                    continue
                wall = ground & ~floor & (dist < radius + 0.5 * cell)
                classes[wall] = SLOPE
                override[wall] = np.nan
                ejecta = (ground & ~floor & ~wall & (dist < 1.6 * radius)
                          & (u < p.crater_ejecta_boulders))
                classes[ejecta] = BOULDER

        if "boulders" in self.spec.relief:
            blocks = _hash_uniform(key + "/blocks", np.floor(y_m).astype(np.int64),
                                   np.floor(x_m).astype(np.int64))
            field = world_noise(key + "/boulder_fields", x_m, y_m, p.boulder_field_scale_m)
            firm = (classes == SAFE) | (classes == VENT)
            in_field = (field > p.boulder_field_threshold) & (blocks < p.boulder_field_density)
            scattered = blocks < p.boulder_scatter
            classes[firm & (in_field | scattered)] = BOULDER
        return classes, override

    def _upwind(self, x: int, y: int) -> Position | None:
        # The upwind neighbour is the one whose downwind neighbour is (x, y).
        for nx, ny in hex_neighbours((x, y), self.width, self.height):
            if tuple(self._downwind[nx, ny]) == (x, y):
                return (nx, ny)
        return None

    # -- terrain ----------------------------------------------------------
    def slopes(self) -> np.ndarray:
        """Slope [deg] of every cell; depends only on the place on the map."""

        u = _hash_uniform(self.spec.key, self.rows, self.cols)
        classes = self.classes
        slope = np.where(classes == VENT, 3.0 + 8.0 * u, 2.0 + 8.0 * u)
        slope = np.where(classes == SLOPE, 30.0 + 12.0 * u, slope)
        slope = np.where(classes == BOULDER, 45.0 + 30.0 * u, slope)
        # Dune slip faces stand at the angle of repose of dry sand.
        slope = np.where((classes == SLOPE) & np.isfinite(self.slope_override),
                         self.slope_override, slope)
        # Foothills: gentle ground next to a steep slope is steeper, but stays
        # below the traction limit even for the lowest measured friction (15.7
        # deg, src/environment/traction.py): at most 14 deg (15 for ventifacts).
        for x in range(self.width):
            for y in range(self.height):
                if classes[x, y] in (SAFE, SAND, VENT) and any(
                    classes[n] == SLOPE for n in hex_neighbours((x, y), self.width, self.height)
                ):
                    slope[x, y] += 4.0
        return slope

    def overlay_classes(self) -> dict[Position, type[TerrainPatch]]:
        """Deep shadow and dust storms placed over the ground classes."""

        if not self.overlays:
            return {}
        result: dict[Position, type[TerrainPatch]] = {}
        ground = {SAFE, SAND, VENT}

        # Shadow of steep slopes, cast away from the sun (2 cells long; 1 cell
        # for the low slip faces of dunes).
        sun = random.Random(self.seed * 7919 + 17).randrange(6)
        for x in range(self.width):
            for y in range(self.height):
                if self.classes[x, y] != SLOPE:
                    continue
                cell = (x, y)
                length = 1 if np.isfinite(self.slope_override[x, y]) else 2
                for _ in range(length):
                    offsets = _ODD_COL_NEIGHBOURS if cell[0] & 1 else _EVEN_COL_NEIGHBOURS
                    dx, dy = offsets[sun]
                    cell = (cell[0] + dx, cell[1] + dy)
                    if not (0 <= cell[0] < self.width and 0 <= cell[1] < self.height):
                        break
                    if self.classes[cell] == SLOPE:
                        continue
                    if self.classes[cell] in ground:
                        result[cell] = DeepShadow

        # Dust storms: weather, a smooth random field that changes with the
        # seed; storms cover about 8% of the window on average (0 to ~25%).
        noise = smooth_noise(self.width, self.height, self.seed)
        for x in range(self.width):
            for y in range(self.height):
                if (x, y) in result or self.classes[x, y] not in ground:
                    continue
                if noise[x, y] > DUST_THRESHOLD:
                    result[(x, y)] = DustStorm
        return result

    def assign_terrain_classes(self, model) -> list[tuple[Position, TerrainPatch]]:
        slopes = self.slopes()
        overlays = self.overlay_classes()
        jitter = _hash_uniform(self.spec.key + "/z", self.rows, self.cols)
        # Crater walls are only a little above the ground (the rover drives up
        # the wall, it does not jump onto it); boulders stand well above.
        base_elevation = {SAFE: 0.0, SAND: -0.05, VENT: 0.1, SLOPE: 0.2, BOULDER: 1.0}
        patches: list[tuple[Position, TerrainPatch]] = []
        uid = 10000
        for x in range(self.width):
            for y in range(self.height):
                code = int(self.classes[x, y])
                terrain_cls = overlays.get((x, y), CLASS_TERRAIN.get(code, SafeRegolith))
                elevation = base_elevation.get(code, 0.0) + 0.05 * float(jitter[x, y])
                if terrain_cls is DeepShadow:
                    elevation -= 0.3
                patch = terrain_cls(uid, model, elevation, float(slopes[x, y]))
                patches.append(((x, y), patch))
                uid += 1
        return patches

    def info(self) -> dict[str, object]:
        """Where on the map this window lies (for reports and the viewer)."""

        span_x, span_y = window_size_m(self.width, self.height, self.cell_m)
        ox, oy = self.raster.origin
        return {
            "map": self.spec.key,
            "title": self.spec.title,
            "crs": self.raster.crs,
            "cell_m": self.cell_m,
            "window_origin_m": [round(self.origin_m[0], 1), round(self.origin_m[1], 1)],
            "window_size_m": [round(span_x, 1), round(span_y, 1)],
            "window_min_xy": [round(ox + self.origin_m[0], 1), round(oy + self.origin_m[1], 1)],
            "accepted": bool(self.accepted),
            "relief": bool(self.relief),
            "attempts": int(self.attempts),
            **{k: round(v, 4) for k, v in window_stats(self.classes).items()},
        }


def build_main(argv: list[str] | None = None) -> int:
    """``uv run build-real-maps``: rebuild the class rasters from the GPKGs."""

    import argparse

    parser = argparse.ArgumentParser(description=build_main.__doc__)
    parser.add_argument("--maps", nargs="+", default=list(REAL_MAPS), choices=list(REAL_MAPS))
    parser.add_argument("--resolution", type=float, default=RASTER_RESOLUTION_M)
    args = parser.parse_args(argv)
    for key in args.maps:
        path = build_raster(key, resolution=args.resolution)
        raster = load_raster.__wrapped__(key)  # type: ignore[attr-defined]
        stats = window_stats(raster.classes)
        print(f"{key}: {path} {raster.classes.shape} px, "
              + ", ".join(f"{k} {v:.1%}" for k, v in stats.items()))
    return 0


__all__ = [
    "REAL_MAPS",
    "RealMapGenerator",
    "RealMapSpec",
    "ReliefParams",
    "WindowRules",
    "build_raster",
    "hex_centres",
    "load_raster",
    "window_stats",
    "world_noise",
]
