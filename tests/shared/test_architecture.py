"""
What this repository is, and what it is not.

It is one project: Urithi. It began as a copy of another project on the same
machine, and that is where every check below comes from. The copy carried the other
project's name, its tutor, its port, its environment variables and its server command;
a server stopped by name took the other one down with it. Each check here closes one of
those, by reading the code rather than by trusting a promise in a README.
"""

import os
import pathlib
import re
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[2]

# What the repository is made of. Generated and local-only directories are not.
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "data", "node_modules",
             "models"}  # the embedding model: downloaded, gitignored, and its vocabulary is every word
SKIP_FILES = {".env", "uv.lock"}


THIS_FILE = pathlib.Path(__file__).resolve()


def _source_files(*, besides_this_one: bool = False):
    """Every file the repository is made of. With besides_this_one, not this test file,
    which has to name each hazard in order to look for it."""
    for path in ROOT.rglob("*"):
        if besides_this_one and path.resolve() == THIS_FILE:
            continue
        if path.is_dir() or any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.name in SKIP_FILES or path.suffix in {".pyc", ".sqlite3", ".wav", ".brf"}:
            continue
        yield path


# Spelled in pieces, so this file is not itself the one mention it forbids.
OTHER_PROJECT = re.compile("ak" + "ili", re.I)


def test_no_file_names_the_project_this_one_was_copied_from():
    offenders = []
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if OTHER_PROJECT.search(text) or OTHER_PROJECT.search(path.name):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"still named here: {offenders}"


def test_the_tutor_it_was_copied_from_is_gone():
    """Not unused: gone. Code nobody runs is code a reader still has to understand."""
    for package in ("api", "auth", "core", "demo", "embeddings", "escalation", "guardrails",
                    "notebook", "runtime", "storage", "sync", "tools", "ui/live"):
        assert not (ROOT / "apu" / package).exists(), f"apu/{package} is still here"
    # registries/ (people.json) and apu/mmu/ (docs/decisions/0015) are this project's own.
    for path in ("cloud_registry", "apu/ui/shared/socket.js"):
        assert not (ROOT / path).exists(), path


PACKAGES = ("apu", "library", "exchange", "guardian", "learner")


def test_every_module_is_reached_from_the_server():
    """The strict minimum, proved: each Python module is imported, directly or not, by the
    server, the mutation runner or a script."""
    import ast

    modules = {".".join(p.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__"): p
               for package in PACKAGES for p in (ROOT / package).rglob("*.py")
               if "__pycache__" not in p.parts}
    modules["server"] = ROOT / "server.py"
    seen, stack = set(), ["server"]
    while stack:
        name = stack.pop()
        if name in seen or name not in modules:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(modules[name].read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in PACKAGES:
                stack.append(node.module)
                stack.extend(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                stack.extend(a.name for a in node.names if a.name.split(".")[0] in PACKAGES + ("server",))
    packages = {m for m in modules if modules[m].name == "__init__.py"}
    unreached = set(modules) - seen - packages
    assert not unreached, f"no path from the server reaches: {sorted(unreached)}"


# ── nothing shared with another project on the same machine ─────────────────

def test_every_setting_has_this_projects_own_prefix():
    """
    The copy read APU_DATA_DIR, APU_LIVE_PORT and the rest: the same names as the project it
    came from. One export in a shell meant for that project would have moved this one's
    data, port or models without a word.
    """
    # The providers' own names: what a key or a voice is called where it comes from.
    shared_by_design = {"ELEVENLABS_VOICE_ID", "GEMINI_TRANSCRIBE_MODEL", "GEMINI_TTS_MODEL",
                        "GEMINI_TTS_VOICE", "GEMINI_API_KEY", "ELEVENLABS_API_KEY",
                        "BRIGHTDATA_API_TOKEN", "BRIGHTDATA_SERP_ZONE",
                        "BRIGHTDATA_UNLOCKER_ZONE", "TAVILY_API_KEY", "ARIZE_API_KEY", "ARIZE_SPACE_ID",
                        "GCS_BUCKET_NAME"}     # the bucket, as the machine names it for every project
    # Each package reads its own prefix: one side's settings can never move the other's data.
    prefixes = {"apu": "URITHI_", "library": "URITHI_", "exchange": "EXCHANGE_",
                "guardian": "GUARDIAN_", "learner": "LEARNER_"}
    for package, prefix in prefixes.items():
        config = (ROOT / package / "config.py").read_text(encoding="utf-8")
        names = re.findall(r'os\.environ\.get\(\s*"([A-Z0-9_]+)"', config)
        names += re.findall(r'_ENV = "([A-Z0-9_]+)"', config)
        assert names or package == "library", package
        for name in names:
            assert name.startswith(prefix) or name in shared_by_design or name.startswith("NEO4J_"), \
                f"{package}/config.py reads {name}"
    for path in _source_files(besides_this_one=True):
        if path.suffix in {".py", ".sh", ".toml", ".example"} or path.name == ".env.example":
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"\bAPU_[A-Z]", text), f"{path.relative_to(ROOT)} reads an APU_ variable"
            assert not re.search(r"\bAPPRENTICE_[A-Z]", text), f"{path.relative_to(ROOT)} still names an APPRENTICE_ variable"


def test_the_server_is_its_own_command_and_is_stopped_by_its_port():
    """
    `pkill -f apu.ui.live.proxy` is how the other project's server is stopped, and this one
    was started with exactly that command, so each stop took both down. This one is
    `python -m server`, and serve.sh finds what to stop by the port alone.
    """
    serve = (ROOT / "scripts/serve.sh").read_text(encoding="utf-8")
    assert "python -m server" in serve
    for by_name in ("pkill", "pgrep", "killall"):
        assert by_name not in serve, f"{by_name} finds processes by name"
    # The processes stopped are the ones the loop reads from lsof on this port, and only
    # those: the same lsof call also appears in the wait loop, so its presence alone proves
    # nothing about what is killed.
    assert re.search(r'for pid in \$\(lsof -nP -iTCP:"\$PORT" -sTCP:LISTEN -t[^)]*\); do\s+'
                     r'echo[^\n]*\n\s+kill "\$pid"', serve), "what is killed is not what holds the port"
    for path in _source_files(besides_this_one=True):
        if path.suffix in {".py", ".sh", ".md", ".js", ".html", ".toml"}:
            assert "apu.ui.live" not in path.read_text(encoding="utf-8"), path


def test_the_port_is_not_the_other_projects_and_the_server_listens_on_loopback():
    from apu import config

    assert config.PORT != 8765, "8765 belongs to the other project"
    assert config.HOST == "127.0.0.1", "what an expert says about their work is not for the LAN"
    for path in _source_files(besides_this_one=True):
        if path.suffix in {".py", ".sh", ".md", ".js", ".html", ".mjs"} \
                or path.name == ".env.example":
            assert "8765" not in path.read_text(encoding="utf-8"), path


def test_data_stays_in_this_repository_each_package_in_its_own_directory():
    from apu import config as shared
    from exchange import config as exchange
    from guardian import config as guardian
    from learner import config as learner

    places = {"GUARDIAN_DATA_DIR": guardian.DATA_DIR, "LEARNER_DATA_DIR": learner.DATA_DIR,
              "EXCHANGE_DATA_DIR": exchange.DATA_DIR, "URITHI_LOG_DIR": shared.LOG_DIR}
    for variable, place in places.items():
        assert pathlib.Path(place).resolve().is_relative_to(ROOT) or variable in os.environ, variable
    assert len({pathlib.Path(p).resolve() for p in places.values()}) == 4, "no two share a directory"


# ── the server ───────────────────────────────────────────────────────────────

def test_the_showcase_is_at_the_root_and_the_pages_beside_it():
    """/ is the static showcase (docs/plan.md, docs/plan-steps-3-to-8.md); watch me work became the classroom mode of /teach/."""
    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app)
    root = client.get("/")
    assert root.status_code == 200 and "<title>Urithi</title>" in root.text
    assert "/api/" not in root.text, "the showcase calls no side"
    for old in ("/watch/", "/watch"):
        moved = client.get(old, follow_redirects=False)
        assert moved.status_code == 308 and moved.headers["location"] == "/teach/", old
    stage = client.get("/presentation/")
    assert stage.status_code == 200 and "Apprentice Deck" in stage.text
    for path in ("/shared/audio.js", "/shared/practice.js", "/shared/urithi.css", "/shared/theme.js",
                 "/presentation/stage.js", "/teach/classroom.js", "/teach/capture.js", "/showcase.css"):
        assert client.get(path).status_code == 200, path
    # A guardian's maps are for that guardian: asked by nobody, or by a learner, refused.
    assert client.get("/api/guardian/maps", params={"person_id": "sabine"}).status_code == 200
    assert client.get("/api/guardian/maps").status_code == 403
    assert client.get("/api/guardian/maps", params={"person_id": "visitor"}).status_code == 403


def test_the_old_address_still_arrives():
    from fastapi.testclient import TestClient

    from server import app

    reply = TestClient(app).get("/apprentice/", follow_redirects=False)
    assert reply.status_code == 308 and reply.headers["location"] == "/teach/"


def test_pages_are_never_served_from_a_stale_cache():
    from fastapi.testclient import TestClient

    from server import app

    reply = TestClient(app).get("/presentation/stage.js")
    assert reply.headers["cache-control"] == "no-store, must-revalidate"


# ── providers ────────────────────────────────────────────────────────────────

def _run(code, env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, cwd=ROOT, env=env, timeout=180)


def test_the_server_starts_without_a_key_and_a_role_fails_loudly_on_first_use():
    proc = _run(
        """
        import tempfile
        import server
        import apu.inference.llm as llm
        from apu import meter
        from exchange.counters import SqliteCounters
        print("IMPORT_OK")
        meter.set_counters(SqliteCounters(tempfile.mkdtemp() + "/c.sqlite3"))   # as the server does at start
        try:
            llm.call_main_model([{"role": "user", "content": "hi"}])
        except llm.ProviderKeyMissing as e:
            print("RAISED:", e)
        """,
        {"GEMINI_API_KEY": ""},
    )
    assert "IMPORT_OK" in proc.stdout, proc.stdout + proc.stderr
    assert "RAISED:" in proc.stdout and "GEMINI_API_KEY is not set" in proc.stdout


# A provider SDK is imported in these modules only: text (the two model roles), speech, vision
# and pictures. Anywhere else, a module calls one of them, so a provider stays a setting.
SDK_PATHS = {"apu/inference/llm.py", "apu/modality/voice.py", "guardian/engine/vision.py",
             "apu/modality/picture.py"}


def test_only_speech_and_vision_reach_for_a_provider_sdk():
    forbidden = re.compile(
        r"^\s*(from|import)\s+(google\.genai|google\s+import\s+genai|google\.generativeai)\b", re.M)
    offenders = {
        str(p.relative_to(ROOT))
        for pkg in PACKAGES
        for p in (ROOT / pkg).rglob("*.py")
        if forbidden.search(p.read_text(encoding="utf-8"))
    }
    assert "apu/modality/voice.py" in offenders, "the voice module is the reference case"
    assert "guardian/engine/vision.py" in offenders, "the vision module is the guardian reference case"
    assert offenders <= SDK_PATHS, f"a text-only module imports an SDK: {offenders - SDK_PATHS}"


def test_one_readiness_check_in_llm_and_no_provider_key_name_or_test_detection_outside_config():
    """
    Production code never checks whether it was patched by a test or whether a key equals a test
    placeholder; `apu/inference/llm.py` has one `is_configured(role)` check, and no provider key
    environment variable name appears as a string literal outside `apu/config.py`.
    """
    import ast

    proc = _run(
        """
        import os
        from apu import config
        from apu.inference import llm
        os.environ[config.GEMINI_API_KEY_ENV] = ""
        assert llm.is_configured("main") is False
        assert llm.is_configured("extraction") is False
        os.environ[config.GEMINI_API_KEY_ENV] = "configured-key"
        assert llm.is_configured("main") is True
        assert llm.is_configured("extraction") is True
        os.environ[config.GEMINI_API_KEY_ENV] = ""
        llm.set_client(object(), provider="gemini")
        assert llm.is_configured("main") is True
        llm.set_client(None)
        config.EXTRACTION_PROVIDER = "unconfigured"
        assert llm.is_configured("extraction") is False
        print("READY_OK")
        """,
        {"GEMINI_API_KEY": ""},
    )
    assert "READY_OK" in proc.stdout, proc.stdout + proc.stderr

    provider_keys = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "BRIGHTDATA_API_TOKEN", "TAVILY_API_KEY")
    config_file = (ROOT / "apu" / "config.py").resolve()
    for path in _source_files(besides_this_one=True):
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        if path.resolve() not in {config_file, (ROOT / "tests" / "conftest.py").resolve()}:
            assert "_TEST_PLACEHOLDER_KEY" not in text, f"{path.relative_to(ROOT)} has _TEST_PLACEHOLDER_KEY"
            assert "_ORIGINAL_WORD_QUESTION" not in text, f"{path.relative_to(ROOT)} checks patched function"
            assert "is not llm.call_" not in text, f"{path.relative_to(ROOT)} checks patched function identity"
        if path.resolve() == config_file:
            continue
        tree = ast.parse(text)
        # Ignore module/class/function docstrings; check string literals in code.
        docstring_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                    docstring_nodes.add(node.body[0].value)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstring_nodes:
                for key_name in provider_keys:
                    assert node.value != key_name, (
                        f"{path.relative_to(ROOT)} hard-codes provider key name {key_name!r} outside apu/config.py"
                    )


# ── documentation ────────────────────────────────────────────────────────────

MAX_MARKDOWN_LINES = 100
# Any Markdown file that cannot be kept within MAX_MARKDOWN_LINES must be listed here with its reason.
MARKDOWN_LINE_EXCEPTIONS: dict[str, str] = {}
_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_no_markdown_file_is_longer_than_a_reader_will_read():
    """A reader gives a document minutes. Past this, the rest is not read, it is skipped."""
    for rel, reason in MARKDOWN_LINE_EXCEPTIONS.items():
        assert (ROOT / rel).exists() and reason.strip(), f"invalid Markdown exception: {rel!r}"
    too_long = {str(p.relative_to(ROOT)): n for p in _source_files() if p.suffix == ".md"
                and str(p.relative_to(ROOT)) not in MARKDOWN_LINE_EXCEPTIONS
                for n in [len(p.read_text(encoding="utf-8").splitlines())]
                if n > MAX_MARKDOWN_LINES}
    assert not too_long, f"over {MAX_MARKDOWN_LINES} lines: {too_long}"


def test_every_relative_markdown_link_points_to_an_existing_file():
    """Splitting documents leaves no broken link behind: every relative Markdown link resolves."""
    broken = []
    for path in _source_files():
        if path.suffix != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for match in _MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip().split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "file://")):
                continue
            if not (path.parent / target).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not broken, f"broken relative Markdown links: {broken}"


def test_the_image_never_carries_a_key_or_local_data():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for private in (".env", "data", ".venv"):
        assert private in ignored, f"{private} would be sent to the image build"
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . " not in dockerfile, "copy what runs, not the whole directory"
    assert "--set-secrets" in dockerfile, "keys come from Secret Manager at run time"
    assert "${PORT" in dockerfile, "Cloud Run says which port to listen on"
