"""HTTP server that generates a Mars terrain grid and sends it to a browser."""

from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.environment.terrain import TerrainPatch
from src.model.model import MarsSimulation


WEBSITE_ROOT = Path(__file__).parent
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/js/main.js": ("js/main.js", "text/javascript; charset=utf-8"),
    "/js/core/CellRandom.js": ("js/core/CellRandom.js", "text/javascript; charset=utf-8"),
    "/js/assets/TerrainAssetLoader.js": ("js/assets/TerrainAssetLoader.js", "text/javascript; charset=utf-8"),
    "/js/terrain/TerrainMaterial.js": ("js/terrain/TerrainMaterial.js", "text/javascript; charset=utf-8"),
    "/js/terrain/DustStormEffect.js": ("js/terrain/DustStormEffect.js", "text/javascript; charset=utf-8"),
    "/js/terrain/RockCluster.js": ("js/terrain/RockCluster.js", "text/javascript; charset=utf-8"),
    "/js/terrain/TerrainGrid.js": ("js/terrain/TerrainGrid.js", "text/javascript; charset=utf-8"),
    "/js/terrain/TerrainRenderer.js": ("js/terrain/TerrainRenderer.js", "text/javascript; charset=utf-8"),
    "/js/scene/TerrainScene.js": ("js/scene/TerrainScene.js", "text/javascript; charset=utf-8"),
    "/js/ui/TerrainTooltip.js": ("js/ui/TerrainTooltip.js", "text/javascript; charset=utf-8"),
    "/textures/DeepShadow.png": ("textures/DeepShadow.png", "image/png"),
    "/textures/DustStorm.png": ("textures/DustStorm.png", "image/png"),
    "/textures/LooseSand.png": ("textures/LooseSand.png", "image/png"),
    "/textures/SafeRegolith.png": ("textures/SafeRegolith.png", "image/png"),
    "/textures/SteepSlope.png": ("textures/SteepSlope.png", "image/png"),
    "/models/Boulder.glb": ("models/Boulder.glb", "model/gltf-binary"),
    "/models/Ventifact.glb": ("models/Ventifact.glb", "model/gltf-binary"),
}


def generate_terrain_grid(width: int, height: int) -> dict[str, Any]:
    """Generate a JSON-serializable representation of the terrain grid."""
    model = MarsSimulation(width=width, height=height, num_rovers=0)
    cells: list[dict[str, Any]] = []

    for x in range(width):
        for y in range(height):
            terrain = next(
                (
                    agent
                    for agent in model.grid.get_cell_list_contents([(x, y)])
                    if isinstance(agent, TerrainPatch)
                ),
                None,
            )
            if terrain is None:
                raise RuntimeError(f"No terrain generated for cell ({x}, {y})")

            cells.append(
                {
                    "x": x,
                    "y": y,
                    "type": type(terrain).__name__,
                    "color": terrain.color,
                    "elevation": float(terrain.elevation),
                    "slope": float(terrain.slope),
                }
            )

    return {"width": width, "height": height, "cells": cells}


class TerrainRequestHandler(BaseHTTPRequestHandler):
    """Handle the browser page and terrain API requests."""

    def __init__(
        self,
        request: Any,
        client_address: Any,
        server: Any,
        *,
        web_server: "WebServer",
    ) -> None:
        self.web_server = web_server
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in STATIC_FILES:
            relative_path, content_type = STATIC_FILES[path]
            self._send_static_file(relative_path, content_type)
        elif path == "/api/terrain":
            terrain = generate_terrain_grid(
                self.web_server.width, self.web_server.height
            )
            payload = json.dumps(terrain).encode("utf-8")
            self._send_response(payload, "application/json; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _send_static_file(self, relative_path: str, content_type: str) -> None:
        file_path = WEBSITE_ROOT / relative_path
        try:
            body = file_path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Website file not found")
            return

        self._send_response(body, content_type)

    def _send_response(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebServer:
    """Serve a browser page and generated Mars terrain data."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        width: int = 50,
        height: int = 50,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Terrain dimensions must be positive")

        self.host = host
        self.port = port
        self.width = width
        self.height = height
        handler = partial(TerrainRequestHandler, web_server=self)
        self._http_server = ThreadingHTTPServer((host, port), handler)

    def serve_forever(self) -> None:
        """Start serving requests until interrupted."""
        print(f"Web server running at http://{self.host}:{self.port}")
        self._http_server.serve_forever()

    def shutdown(self) -> None:
        """Stop the server."""
        self._http_server.shutdown()
        self._http_server.server_close()


if __name__ == "__main__":
    WebServer().serve_forever()
