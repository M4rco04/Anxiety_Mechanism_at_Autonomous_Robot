"""Minimal GeoPackage reader and polygon rasterizer (no GDAL needed).

A GeoPackage is an SQLite database; every geometry is a small GeoPackage
header followed by standard WKB. This module reads the (multi)polygons of one
feature table together with one attribute and burns them into a regular
raster with an even-odd scanline fill (holes are respected).
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Iterator
from pathlib import Path

import numpy as np

Ring = np.ndarray  # (N, 2) float64, closed or open


def _envelope_size(flags: int) -> int:
    code = (flags >> 1) & 0x07
    return {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(code, 0)


def _parse_wkb(blob: bytes, offset: int, rings: list[Ring]) -> int:
    """Append all polygon rings of a WKB geometry; return the new offset."""

    order = "<" if blob[offset] == 1 else ">"
    offset += 1
    (gtype,) = struct.unpack_from(order + "I", blob, offset)
    offset += 4
    has_z = (gtype // 1000) in (1, 3) or bool(gtype & 0x80000000)
    has_m = (gtype // 1000) in (2, 3) or bool(gtype & 0x40000000)
    base = (gtype & 0x0FFFFFFF) % 1000
    dims = 2 + int(has_z) + int(has_m)

    if base == 3:  # Polygon
        (n_rings,) = struct.unpack_from(order + "I", blob, offset)
        offset += 4
        for _ in range(n_rings):
            (n_points,) = struct.unpack_from(order + "I", blob, offset)
            offset += 4
            coords = np.frombuffer(
                blob, dtype=np.dtype(order + "f8"), count=n_points * dims, offset=offset
            ).reshape(n_points, dims)
            offset += n_points * dims * 8
            rings.append(np.array(coords[:, :2], dtype=np.float64))
        return offset
    if base in (6, 7):  # MultiPolygon, GeometryCollection
        (n_parts,) = struct.unpack_from(order + "I", blob, offset)
        offset += 4
        for _ in range(n_parts):
            offset = _parse_wkb(blob, offset, rings)
        return offset
    raise ValueError(f"Unsupported WKB geometry type {gtype}")


def geometry_rings(blob: bytes) -> list[Ring]:
    """Rings of a GeoPackage geometry blob (``GP`` header + WKB)."""

    if blob[:2] != b"GP":
        raise ValueError("Not a GeoPackage geometry blob")
    flags = blob[3]
    offset = 8 + _envelope_size(flags)
    rings: list[Ring] = []
    _parse_wkb(blob, offset, rings)
    return rings


def read_features(path: str | Path, attribute: str) -> Iterator[tuple[str, list[Ring]]]:
    """Yield ``(attribute value, rings)`` for every feature of the first layer."""

    connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        table, column = connection.execute(
            "SELECT table_name, column_name FROM gpkg_geometry_columns LIMIT 1"
        ).fetchone()
        query = f'SELECT "{attribute}", "{column}" FROM "{table}"'
        for value, blob in connection.execute(query):
            if blob is None:
                continue
            yield str(value), geometry_rings(bytes(blob))
    finally:
        connection.close()


def layer_bounds(path: str | Path) -> tuple[float, float, float, float]:
    connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        table = connection.execute(
            "SELECT table_name FROM gpkg_geometry_columns LIMIT 1"
        ).fetchone()[0]
        row = connection.execute(
            "SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name=?",
            (table,),
        ).fetchone()
        return tuple(float(v) for v in row)  # type: ignore[return-value]
    finally:
        connection.close()


def rasterize_rings(
    rings: list[Ring],
    origin: tuple[float, float],
    resolution: float,
    shape: tuple[int, int],
) -> np.ndarray:
    """Even-odd fill of ``rings`` sampled at pixel centres.

    ``origin`` is the (x, y) of the lower-left corner, row 0 is the lowest
    row (north up when plotted with ``origin="lower"``). Returns a boolean
    array of ``shape`` = (rows, cols).
    """

    rows, cols = shape
    x0, y0 = origin
    starts, ends = [], []
    for ring in rings:
        if len(ring) < 3:
            continue
        a = ring
        b = np.roll(ring, -1, axis=0)
        starts.append(a)
        ends.append(b)
    if not starts:
        return np.zeros(shape, dtype=bool)
    p0 = np.concatenate(starts)
    p1 = np.concatenate(ends)

    # Edge coordinates in pixel units (pixel centre of row r is at r + 0.5).
    ya = (p0[:, 1] - y0) / resolution - 0.5
    yb = (p1[:, 1] - y0) / resolution - 0.5
    xa = (p0[:, 0] - x0) / resolution - 0.5
    xb = (p1[:, 0] - x0) / resolution - 0.5
    keep = ya != yb
    ya, yb, xa, xb = ya[keep], yb[keep], xa[keep], xb[keep]
    lo = np.minimum(ya, yb)
    hi = np.maximum(ya, yb)
    # Rows r with lo <= r < hi (half-open, so shared vertices count once).
    r_first = np.clip(np.ceil(lo).astype(np.int64), 0, rows)
    r_last = np.clip(np.ceil(hi).astype(np.int64), 0, rows)  # exclusive
    counts = r_last - r_first
    valid = counts > 0
    if not np.any(valid):
        return np.zeros(shape, dtype=bool)
    r_first, counts = r_first[valid], counts[valid]
    ya, yb, xa, xb = ya[valid], yb[valid], xa[valid], xb[valid]

    edge = np.repeat(np.arange(len(counts)), counts)
    step = np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts, counts)
    row = r_first[edge] + step
    t = (row - ya[edge]) / (yb[edge] - ya[edge])
    xc = xa[edge] + t * (xb[edge] - xa[edge])

    order = np.lexsort((xc, row))
    row, xc = row[order], xc[order]
    # Pair consecutive crossings within each row (even-odd rule).
    first = np.ones(len(row), dtype=bool)
    first[1:] = row[1:] != row[:-1]
    parity = np.zeros(len(row), dtype=np.int64)
    group = np.cumsum(first) - 1
    group_start = np.flatnonzero(first)
    parity = np.arange(len(row)) - group_start[group]
    enter = parity % 2 == 0
    # An odd count in a row means a broken ring; drop the dangling crossing.
    leave_idx = np.flatnonzero(enter) + 1
    ok = leave_idx < len(row)
    enter_idx = np.flatnonzero(enter)[ok]
    leave_idx = leave_idx[ok]
    same_row = row[enter_idx] == row[leave_idx]
    enter_idx, leave_idx = enter_idx[same_row], leave_idx[same_row]

    c_start = np.clip(np.ceil(xc[enter_idx]).astype(np.int64), 0, cols)
    c_end = np.clip(np.ceil(xc[leave_idx]).astype(np.int64), 0, cols)
    span = c_end > c_start
    diff = np.zeros((rows, cols + 1), dtype=np.int32)
    np.add.at(diff, (row[enter_idx][span], c_start[span]), 1)
    np.add.at(diff, (row[enter_idx][span], c_end[span]), -1)
    return np.cumsum(diff[:, :cols], axis=1) % 2 == 1


__all__ = ["geometry_rings", "layer_bounds", "rasterize_rings", "read_features"]
