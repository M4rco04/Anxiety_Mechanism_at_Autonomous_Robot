"""HTTP server regression tests for terrain and live simulation."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from server.server import STATIC_FILES, WebServer


def _request_json(url: str, method: str = "GET", payload: bytes | None = None):
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_server_terrain_and_simulation_api():
    server = WebServer(
        port=0, width=8, height=8, num_rovers=2, seed=17
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        status, terrain = _request_json(base + "/api/terrain")
        assert status == 200
        assert terrain["width"] == 8
        assert len(terrain["cells"]) == 64
        assert {
            "x",
            "y",
            "type",
            "color",
            "elevation",
            "slope",
        } <= set(terrain["cells"][0])

        status, snapshot = _request_json(base + "/api/simulation/state")
        assert status == 200
        assert snapshot["step"] == 0
        assert len(snapshot["rovers"]) == 2
        assert "metrics" in snapshot

        status, stepped = _request_json(
            base + "/api/simulation/step", method="POST", payload=b"{}"
        )
        assert status == 200
        assert stepped["step"] == 1

        status, reset = _request_json(
            base + "/api/simulation/reset", method="POST", payload=b"{}"
        )
        assert status == 200
        assert reset["step"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_all_registered_static_files_exist():
    root = Path(__file__).resolve().parents[1] / "server"
    for path, (relative, _) in STATIC_FILES.items():
        assert (root / relative).is_file(), path
