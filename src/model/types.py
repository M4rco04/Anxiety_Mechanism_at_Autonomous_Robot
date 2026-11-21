"""Shared value types and geometry helpers."""

from __future__ import annotations

import math
from functools import cache

Position = tuple[int, int]
RGB = tuple[int, int, int]


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a value, treating non-finite inputs as ``low``."""

    if not math.isfinite(value):
        return low
    return max(low, min(high, value))


def hex_distance(a: Position, b: Position) -> int:
    """Hex distance in Mesa's odd-q offset coordinates.

    Mesa 2.4's ``HexMultiGrid`` uses the offset convention where the axial
    row is ``y - (x + (x & 1)) // 2``.  The common alternative formula with a
    minus sign is wrong for this layout and breaks radio ranges.
    """

    ax, ay = a
    bx, by = b
    aq, ar = ax, ay - (ax + (ax & 1)) // 2
    bq, br = bx, by - (bx + (bx & 1)) // 2
    dq, dr = aq - bq, ar - br
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def rgb_distance(a: RGB, b: RGB) -> float:
    """Euclidean distance between two 0..255 RGB signatures."""

    return math.sqrt(sum((int(x) - int(y)) ** 2 for x, y in zip(a, b)))


def hex_to_rgb(color: str) -> RGB:
    """Convert a ``#rrggbb`` or ``#rgb`` color to an RGB tuple."""

    value = color.strip()
    value = value.removeprefix("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return (128, 128, 128)
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (128, 128, 128)


def cube_coordinates(position: Position) -> tuple[int, int, int]:
    """Return cube coordinates for Mesa's odd-q offset layout."""

    x, y = position
    q = x
    r = y - (x + (x & 1)) // 2
    return (q, r, -q - r)


def hex_vector(start: Position, end: Position) -> tuple[int, int, int]:
    a = cube_coordinates(start)
    b = cube_coordinates(end)
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def from_cube(q: int, r: int) -> Position:
    """Inverse of :func:`cube_coordinates` (offset position of a cube cell)."""

    return (q, r + (q + (q & 1)) // 2)


@cache
def gap_cells(a: Position, b: Position) -> tuple[Position, Position] | None:
    """The two cells on both sides of the edge between neighbours ``a``, ``b``.

    On a hex grid two neighbouring cells share exactly two neighbours; a
    rover driving from ``a`` to ``b`` passes between them. ``None`` when
    ``a`` and ``b`` are not neighbours. Cached: it is called millions of
    times per simulation by the route planners.
    """

    if hex_distance(a, b) != 1:
        return None
    q, r, _ = cube_coordinates(a)
    dq, dr, ds = hex_vector(a, b)
    left = (-dr, -ds)  # direction rotated by 60 degrees one way
    right = (-ds, -dq)  # and the other way
    return (from_cube(q + left[0], r + left[1]), from_cube(q + right[0], r + right[1]))


def squeezed(a: Position, b: Position, blocked) -> bool:
    """True when both cells beside the edge ``a``-``b`` are ``blocked``.

    The rover cannot pass between two boulders: the gap between them is
    narrower than the rover. ``blocked(position)`` says whether a cell is an
    obstacle (cells outside the map are not).
    """

    cells = gap_cells(a, b)
    return cells is not None and blocked(cells[0]) and blocked(cells[1])


__all__ = [
    "RGB",
    "Position",
    "clamp",
    "cube_coordinates",
    "from_cube",
    "gap_cells",
    "hex_distance",
    "hex_to_rgb",
    "hex_vector",
    "rgb_distance",
    "squeezed",
]
