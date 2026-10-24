"""HTTP server for the Mars terrain and live rover simulation."""

from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config.config import SimulationConfig
from server.simulation_runtime import SimulationRuntime
from server.terrain_data import generate_terrain_grid as _generate_terrain_grid

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
    "/js/ui/RoverTooltip.js": ("js/ui/RoverTooltip.js", "text/javascript; charset=utf-8"),
    "/js/rover/RoverModel.js": ("js/rover/RoverModel.js", "text/javascript; charset=utf-8"),
    "/js/rover/RoverLayer.js": ("js/rover/RoverLayer.js", "text/javascript; charset=utf-8"),
    "/js/simulation/SimulationClient.js": ("js/simulation/SimulationClient.js", "text/javascript; charset=utf-8"),
    "/js/simulation/SimulationPanel.js": ("js/simulation/SimulationPanel.js", "text/javascript; charset=utf-8"),
    "/textures/DeepShadow.png": ("textures/DeepShadow.png", "image/png"),
    "/textures/DustStorm.png": ("textures/DustStorm.png", "image/png"),
    "/textures/LooseSand.png": ("textures/LooseSand.png", "image/png"),
    "/textures/SafeRegolith.png": ("textures/SafeRegolith.png", "image/png"),
    "/textures/SteepSlope.png": ("textures/SteepSlope.png", "image/png"),
    "/models/Boulder.glb": ("models/Boulder.glb", "model/gltf-binary"),
    "/models/Ventifact.glb": ("models/Ventifact.glb", "model/gltf-binary"),
}


def generate_terrain_grid(width: int, height: int) -> dict[str, Any]:
    """Backward-compatible static terrain payload."""

    return _generate_terrain_grid(width, height)


class TerrainRequestHandler(BaseHTTPRequestHandler):
    """Serve the browser app, terrain payload and live simulation API."""

    def __init__(
        self,
        request: Any,
        client_address: Any,
        server: Any,
        *,
        web_server: WebServer,
    ) -> None:
        self.web_server = web_server
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in STATIC_FILES:
            relative_path, content_type = STATIC_FILES[path]
            self._send_static_file(relative_path, content_type)
        elif path == "/api/terrain":
            self._send_json(self.web_server.runtime.terrain_payload())
        elif path == "/api/simulation/state":
            self._send_json(self.web_server.runtime.snapshot())
        elif path == "/api/simulation/config":
            self._send_json(self.web_server.runtime.metadata())
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except (TypeError, ValueError) as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            if path == "/api/simulation/step":
                self._send_json(self.web_server.runtime.step())
            elif path == "/api/simulation/reset":
                seed = payload.get("seed")
                self._send_json(
                    self.web_server.runtime.reset(
                        seed=int(seed) if seed is not None else None
                    )
                )
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except (ValueError, TypeError) as error:
            self._send_json(
                {"error": str(error)}, status=HTTPStatus.BAD_REQUEST
            )

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid JSON body") from error
        if not isinstance(parsed, dict):
            raise TypeError("JSON body must be an object")
        return parsed

    def _send_static_file(self, relative_path: str, content_type: str) -> None:
        file_path = WEBSITE_ROOT / relative_path
        try:
            body = file_path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Website file not found")
            return
        self._send_response(body, content_type)

    def _send_json(
        self,
        payload: Any,
        *,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_response(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebServer:
    """Serve the terrain viewer and a stateful simulation session."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        width: int = 50,
        height: int = 50,
        num_rovers: int = 3,
        seed: int = 2025,
        navigation_mode: str = "scaffold",
        mission_mode: str = "exploration",
        max_steps: int = 500,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Terrain dimensions must be positive")

        self.host = host
        self.width = width
        self.height = height
        config = SimulationConfig(
            width=width,
            height=height,
            seed=seed,
            num_rovers=num_rovers,
            navigation_mode=navigation_mode,
            mission_mode=mission_mode,
            max_steps=max_steps,
        )
        config.validate()
        self.config = config
        self.runtime = SimulationRuntime(config)

        handler = partial(TerrainRequestHandler, web_server=self)
        self._http_server = ThreadingHTTPServer((host, port), handler)
        self.port = int(self._http_server.server_address[1])

    def serve_forever(self) -> None:
        print(f"Web server running at http://{self.host}:{self.port}")
        self._http_server.serve_forever()

    def shutdown(self) -> None:
        self._http_server.shutdown()
        self._http_server.server_close()


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    WebServer(host=host, port=port).serve_forever()


if __name__ == "__main__":
    main()
