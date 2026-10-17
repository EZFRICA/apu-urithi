"""
The scripts a person runs by hand: they import, and they call routes the server still has.

Measured on 2026-10-17: scripts/demo_map.py imported guardian.engine.routes, gone since the routes
moved to guardian/api/, and called /answer to make steps, which decision 0016 ended; it failed at
its first line, and the stage on a machine without Sabine's map stayed on "No Work Map yet".
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_demo_map_script_calls_only_routes_the_server_has():
    demo = _load("demo_map")
    from server import app

    served = {path.removeprefix("/api/guardian/") for path in app.openapi()["paths"] if path.startswith("/api/guardian/")}
    assert set(demo.PATHS) <= served, set(demo.PATHS) - served
    source = (ROOT / "scripts" / "demo_map.py").read_text(encoding="utf-8")
    called = {re.sub(r"\{[^}]+\}", "{map_id}", p) for p in re.findall(r'call\("(?:GET|POST)", f?"([^"]+)"', source)}
    assert called and called <= set(demo.PATHS), called - set(demo.PATHS)
    sentences = source[source.index("for said in SAID:"):source.index('if "--quick"')]
    assert "'save'" in sentences or '"save"' in sentences, "each sentence is saved by the guardian's word (decision 0016)"
