"""
The boundary between the guardian's side and the learner's side, proved from the code.

Target: apu/, library/, exchange/, guardian/, learner/, server.py

docs/architecture.md and .claude/skills/boundary-check: the two sides never import each other;
both may use the shared core, the library and the question box; only the guardian writes to
the library; each side answers under its own address. Read from the source, not promised.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGES = ("apu", "library", "exchange", "guardian", "learner")

# What each package may import, of the others.
ALLOWED = {
    "apu": set(),
    "library": {"apu"},
    "exchange": {"apu"},
    "guardian": {"apu", "library", "exchange"},
    "learner": {"apu", "library", "exchange"},
}


def _imports(package: str) -> dict[str, set[str]]:
    """For each module of a package, the other packages it imports."""
    found = {}
    for path in (ROOT / package).rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        names = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
        found[str(path.relative_to(ROOT))] = (names & set(PACKAGES)) - {package}
    return found


def test_each_package_imports_only_what_it_may():
    """The two sides never import each other; the core and the shared stores import no side."""
    for package, allowed in ALLOWED.items():
        for module, imported in _imports(package).items():
            assert imported <= allowed, f"{module} imports {sorted(imported - allowed)}"


# What learner/ may reach of the shared stores, module by module: the library to read, with a
# person's levels (library.reader), and the question box to ask (exchange.asking). Measured in
# the step 0 review: learner/ imported library.store and exchange.questions whole, so publishing,
# withdrawing, reading the box and closing a question were each one call away.
LEARNER_MAY_USE = {"library.access", "library.model", "library.reader", "exchange.asking"}


def _modules_used(path: pathlib.Path) -> set[str]:
    """Every module of library/ or exchange/ a file imports, `from library import access` as library.access."""
    used = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module in ("library", "exchange"):
                used.update(f"{node.module}.{a.name}" for a in node.names)
            else:
                used.add(node.module)
        elif isinstance(node, ast.Import):
            used.update(a.name for a in node.names)
    return {m for m in used if m.split(".")[0] in ("library", "exchange")}


def _sources(package: str):
    return [p for p in (ROOT / package).rglob("*.py") if "__pycache__" not in p.parts]


def test_the_learner_reads_the_library_and_asks_the_box_and_nothing_more():
    for path in _sources("learner"):
        extra = _modules_used(path) - LEARNER_MAY_USE
        assert not extra, f"{path.relative_to(ROOT)} reaches {sorted(extra)}"


def test_the_learner_never_reaches_behind_the_reader_or_the_box():
    """Reader and Asking hold the store and the box in a private attribute; learner/ never reads it."""
    for path in _sources("learner"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("_store", "_box"), f"{path.relative_to(ROOT)} reaches {node.attr}"


def test_the_reader_and_the_box_offer_no_write():
    from exchange.asking import Asking
    from library.reader import Reader

    assert {n for n in dir(Reader) if not n.startswith("_")} == {"bodies_for", "search", "body_units"}
    assert {n for n in dir(Asking) if not n.startswith("_")} == {"ask_guardian", "tickets"}


def test_no_package_imports_by_name_at_run_time():
    """An import the source does not spell out is one no test above can read."""
    for package in PACKAGES:
        for path in _sources(package):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                    assert "importlib" not in names, f"{path.relative_to(ROOT)} imports importlib"
                if isinstance(node, ast.Name) and node.id == "__import__":
                    raise AssertionError(f"{path.relative_to(ROOT)} calls __import__")


def test_only_the_guardian_writes_to_the_library():
    """The learner reads [B]; publishing and withdrawing are guardian actions."""
    for side in ("learner", "exchange", "apu"):
        for path in _sources(side):
            writes = [node.attr for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                      if isinstance(node, ast.Attribute) and node.attr in ("publish", "withdraw")]
            assert not writes, f"{path.relative_to(ROOT)} writes to the library: {writes}"


def test_each_side_answers_under_its_own_address():
    """A guardian action is under /api/guardian/, a learner's under /api/learner/, nothing between."""
    from fastapi.routing import APIRoute

    from server import app

    # Every route, not only those under /api/: a guardian action at /guardian-api/publish
    # would otherwise pass. The server's own redirect is the one route of neither side.
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        module = route.endpoint.__module__
        side = module.split(".")[0]
        if side == "server":
            assert not route.path.startswith("/api/"), f"{route.path} is served by the server itself"
            continue
        assert side in ("guardian", "learner"), f"{route.path} is served by {module}"
        assert route.path.startswith(f"/api/{side}/"), f"{route.path} is served by {module}"


def test_each_side_keeps_its_data_in_its_own_directory():
    from exchange import config as exchange
    from guardian import config as guardian
    from learner import config as learner

    assert pathlib.Path(guardian.WORKMAP_PATH).resolve().is_relative_to(pathlib.Path(guardian.DATA_DIR).resolve())
    assert pathlib.Path(guardian.MMU_DIR).resolve().is_relative_to(pathlib.Path(guardian.DATA_DIR).resolve())
    assert pathlib.Path(learner.PROGRESS_PATH).resolve().is_relative_to(pathlib.Path(learner.DATA_DIR).resolve())
    assert pathlib.Path(learner.MMU_DIR).resolve().is_relative_to(pathlib.Path(learner.DATA_DIR).resolve())
    assert pathlib.Path(exchange.QUESTIONS_PATH).resolve().is_relative_to(pathlib.Path(exchange.DATA_DIR).resolve())


def test_the_image_carries_every_package():
    """Measured: after the split the Dockerfile still copied apu/ alone, and the image would
    not have started. Every package the server imports travels in it."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for package in (*PACKAGES, "server.py"):
        assert f"COPY {package} " in dockerfile, f"the image is missing {package}"
