"""
The stage: Urithi on the deck a blind or low-vision learner works with, the learner's routes only.

Target: apu/ui/presentation/

What a test can know about a stage is not whether it looks right. It is whether each key
reaches a route that exists, whether the braille shown is the braille the server laid out,
whether a part that is only a concept says so, and the handful of layout rules that made
the stage unusable when they were broken. The behaviour itself is run under node, in
tests/presentation, and collected here.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
UI = ROOT / "apu/ui/presentation"
PROMPTER = (UI / "prompter.js").read_text(encoding="utf-8")
BRIDGE = (UI / "bridge.js").read_text(encoding="utf-8")
STAGE = (UI / "stage.js").read_text(encoding="utf-8")
PRESENTATION = (UI / "presentation.js").read_text(encoding="utf-8")
HARDWARE3D = (UI / "hardware3d.js").read_text(encoding="utf-8")
INDEX = (UI / "index.html").read_text(encoding="utf-8")
STYLES = (UI / "styles.css").read_text(encoding="utf-8")
SHARED_AUDIO = (ROOT / "apu/ui/shared/audio.js").read_text(encoding="utf-8")

KEYS = ["btn_talk", "btn_read", "btn_book", "btn_braille"]


def _rule(stylesheet: str, selector: str) -> str:
    """One rule, to its closing brace. A fixed slice silently drops what a comment pushes out."""
    start = stylesheet.index(selector)
    return stylesheet[start:stylesheet.index("}", start) + 1]


# ── the behaviour, run ───────────────────────────────────────────────────────

@pytest.mark.parametrize("suite", ["prompter", "bridge", "stage", "audio", "capture", "remember", "live"])
def test_the_stage_behaves_the_way_it_reads(suite):
    """
    Grepping a file proves a line was typed. These suites run the real prompter, bridge and
    stage against a stub browser and a fake server, which is what proves they work.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run([node, f"tests/presentation/{suite}.test.mjs"],
                            cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert ", 0 failed" in result.stdout


# ── every key reaches something real ────────────────────────────────────────

def _routes() -> set[tuple[str, str]]:
    """What the server publishes, read from its schema: what a client can actually call."""
    from server import app

    return {(method.upper(), path)
            for path, methods in app.openapi()["paths"].items() for method in methods}


def _as_route(path: str) -> str:
    """A template literal path from bridge.js, as FastAPI writes the same route: the learner's side."""
    path = path.split("?")[0]
    path = re.sub(r"\$\{encodeURIComponent\(bodyId\)\}", "{body_id}", path)
    return "/api/learner/" + re.sub(r"\$\{encodeURIComponent\(unitId\)\}", "{unit_id}", path)


def test_every_route_the_stage_calls_exists_on_the_server():
    """A key wired to a route that is not there is a key that does nothing, said silently."""
    routes = _routes()
    gets = re.findall(r"this\._get\(`([^`]+)`\)|this\._get\(\"([^\"]+)\"\)", BRIDGE)
    posts = re.findall(r"this\._post\(`([^`]+)`|this\._post\(\"([^\"]+)\"", BRIDGE)
    assert gets and posts, "the bridge's calls were not found"
    for path in [a or b for a, b in gets]:
        route = _as_route(path)
        assert ("GET", route) in routes, f"GET {route} is called by the stage and served by nothing"
    for path in [a or b for a, b in posts]:
        route = _as_route(path)
        assert ("POST", route) in routes, f"POST {route} is not served"


def test_each_key_on_the_deck_does_something_in_the_stage():
    for part in ("btn_read", "btn_book", "btn_braille", "mode_wheel", "speaker_grille"):
        assert f'partId === "{part}"' in STAGE, f"{part} is on the deck and does nothing"
    assert "async talk()" in STAGE and "async release()" in STAGE, "Talk is held, not clicked"


def _parts() -> dict[str, str]:
    block = HARDWARE3D[HARDWARE3D.index("export const HARDWARE_PARTS_INFO"):
                       HARDWARE3D.index("const SHOTS")]
    return dict(re.findall(r'id: "(\w+)",\s*status: "(\w+)"', block))


def test_every_part_says_whether_it_works_here_or_is_a_concept():
    """
    The deck is drawn hardware. The keys are wired to the apprentice and work on this stage;
    the embosser is simulated in code; the headphone socket and the cable are a concept.
    Whoever presses each one is told which is which, rather than left to assume it all is.
    """
    parts = _parts()
    assert set(parts) >= {*KEYS, "mode_wheel", "port_embosser", "port_headphones", "port_power"}
    assert set(parts.values()) <= {"wired", "simulated", "concept"}
    for part, status in parts.items():
        block = HARDWARE3D[HARDWARE3D.index(f'id: "{part}"'):][:1400]
        if status == "concept":
            assert "A hardware concept" in block, f"{part} is a concept and does not say so"
        if status == "simulated":
            assert "simulated" in block.lower(), f"{part} is simulated and does not say so"
    assert "STATUS_WORDS[info.status]" in PRESENTATION, "the status reaches the inspector"


def test_the_list_beside_the_deck_holds_the_same_parts():
    """The list is the deck for anyone not holding a mouse; a part missing from it is
    unreachable without one."""
    listed = set(re.findall(r'\{ id: "(\w+)", icon', PRESENTATION))
    assert listed >= {*KEYS, "mode_wheel", "port_embosser", "port_headphones", "port_power"}
    assert listed <= set(_parts())


# ── braille is printed, and only the server makes it ────────────────────────

def test_the_stage_never_makes_braille_of_its_own():
    """
    The stage used to carry a letter-to-cell table as a fallback. A table like that is
    uncontracted, wrong for numbers and capitals, and looks exactly like the real thing to
    anyone who cannot read it. Only the server, through liblouis, makes cells now.
    """
    for name, source in (("prompter.js", PROMPTER), ("stage.js", STAGE),
                         ("presentation.js", PRESENTATION), ("bridge.js", BRIDGE)):
        assert not re.search(r'\b[a-z]: "[⠀-⣿]"', source), f"{name} holds a braille table"
    assert "reply.pages_unicode" in STAGE, "the pages shown are the server's pages"


def test_the_sheet_is_a_page_of_paper_not_a_scrolling_strip():
    sheet = _rule(STYLES, ".braille-sheet {")
    assert "max-height" in sheet and "overflow: auto" in sheet, \
        "the page scrolls inside its own box instead of pushing the prompter away"
    assert "clamp(" in _rule(STYLES, ".braille-page {"), "the cell size follows the window"


def _relative_luminance(colour: str) -> float:
    channels = [int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    a, b = _relative_luminance(first), _relative_luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_the_cells_are_readable_without_being_the_brightest_thing_on_the_stage():
    """21:1 was spent on decoration as much as on the cells. Lower, but never hard to read."""
    block = STYLES[STYLES.index("--braille-card:"):STYLES.index(".braille-keynote-card {")]
    tokens = dict(re.findall(r"--(braille-[a-z-]+): (#[0-9a-f]{6});", block))
    cells = _contrast(tokens["braille-cells"], tokens["braille-well"])
    assert 7.0 <= cells <= 16.0, f"the cells are at {cells:.1f}:1"
    labels = _contrast(tokens["braille-label"], tokens["braille-card"])
    assert 4.5 <= labels < cells


# ── a person who cannot see the stage ────────────────────────────────────────

def test_each_sentence_reaches_a_screen_reader_whole():
    assert 'id="prompter-announcer"' in INDEX
    assert 'aria-live="polite"' in INDEX and 'aria-atomic="true"' in INDEX
    show = PROMPTER[PROMPTER.index("  show(text"):][:700]
    assert "this._announce(this.activeText)" in show


def test_a_failure_is_said_where_the_sentences_are_not_in_a_corner():
    notice = PROMPTER[PROMPTER.index("showNotice(message) {"):][:300]
    assert "this.show(message" in notice
    assert "this.prompter.showNotice(" in STAGE


def test_the_canvas_is_hidden_from_the_reader_and_the_list_stands_in_for_it():
    stage = INDEX[INDEX.index('id="equipment-3d-stage"'):][:200]
    assert 'aria-hidden="true"' in stage
    assert 'role="group"' in INDEX and "Press a part of the deck" in INDEX
    assert 'button.setAttribute("aria-label", `${part.name}. ${part.sub}`)' in PRESENTATION
    assert 'icon.setAttribute("aria-hidden", "true")' in PRESENTATION, "an emoji is not a label"


def test_every_toggle_says_whether_it_is_on():
    """`class="active"` is a colour. aria-pressed is the state."""
    for selector in ("model-pill-btn", "view-shot-btn"):
        buttons = re.findall(rf'<button class="{selector}[^>]*>', INDEX)
        assert buttons, selector
        assert all("aria-pressed=" in b for b in buttons)
    for toggle in ("toggle-mic-btn", "toggle-camera-btn", "toggle-mirror-btn", "toggle-drawer-btn"):
        assert "aria-pressed=" in INDEX[INDEX.index(f'id="{toggle}"'):][:400], toggle
    assert "_pressedState(" in PRESENTATION


def test_a_panel_slid_off_the_stage_is_out_of_the_reading_order_too():
    toggle = PRESENTATION[PRESENTATION.index("this.dom.drawerBtn?.addEventListener"):][:600]
    assert "panel.hidden = collapsed" in toggle


def test_the_keyboard_is_the_deck_key_for_key():
    keys = PRESENTATION[PRESENTATION.index("  _keyDown(event) {"):][:2600]
    for key, part in (('"Enter"', "btn_book"), ('"r"', "btn_read"), ('"b"', "btn_braille")):
        assert f"key === {key}" in keys and part in keys, f"{key} does not reach {part}"
    assert 'key === " "' in keys and "this.stage.talk()" in keys, "Space is Talk"
    assert "event.repeat" in keys, "a held key repeats; the microphone opens once"
    assert '["INPUT", "SELECT", "TEXTAREA"].includes(tag)' in keys, \
        "choosing a map with the keyboard must not press the deck"
    assert "metaKey" in keys, "a browser shortcut is not ours to take"
    release = PRESENTATION[PRESENTATION.index('window.addEventListener("keyup"'):][:300]
    assert "this.stage.release()" in release, "letting go of Space is letting go of Talk"


def test_motion_can_be_turned_off_and_focus_can_be_seen():
    assert "prefers-reduced-motion" in STYLES
    assert "focus-visible" in STYLES
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in HARDWARE3D
    assert "prefers-reduced-motion: reduce" in PROMPTER, "the sheet appears at once, not line by line"


# ── the deck itself ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("part", KEYS)
def test_every_key_has_a_target_wider_than_itself(part):
    """The moulded keys are 28 to 49 pixels across; the pointer aims at a wider disc."""
    assert re.search(rf'_addHitTarget\(\w+, "{part}", [\d.]+\)', HARDWARE3D), part


def test_no_aiming_disc_reaches_another_key():
    """A disc that covered the next key's centre made pressing braille open the microphone."""
    import math

    groups = dict(re.findall(r"(\w+G)\.position\.set\(([-\d., ]+)\);", HARDWARE3D))
    found = re.findall(r'_addHitTarget\((\w+), "(\w+)", ([\d.]+)\)', HARDWARE3D)
    targets = {part: tuple(float(v) for v in groups[name].split(",")[:2])
               for name, part, _ in found}
    radii = {part: float(radius) for _, part, radius in found}
    assert len(targets) >= 4
    for part, centre in targets.items():
        for other, other_centre in targets.items():
            if other != part:
                assert radii[part] < math.dist(centre, other_centre), (part, other)


def test_the_canvas_follows_the_capsule_and_the_stage_fits_the_window():
    assert "new ResizeObserver(() => this._onResize())" in HARDWARE3D
    capsule = _rule(STYLES, ".elevenlabs-capsule-frame {")
    assert "max-height: calc(100vh" in capsule


def test_the_microphone_does_not_reach_the_speakers_it_is_recording():
    audio = SHARED_AUDIO[SHARED_AUDIO.index("async start()"):SHARED_AUDIO.index("  stop()")]
    assert "this.processor.connect(this.audioContext.destination)" not in audio
    assert "this.sink.gain.value = 0" in audio


def test_the_interface_speaks_one_language():
    """Everything shown is English; accented French in the interface is a leftover."""
    for name, source in (("prompter.js", PROMPTER), ("stage.js", STAGE), ("bridge.js", BRIDGE),
                         ("presentation.js", PRESENTATION), ("index.html", INDEX)):
        accented = [c for c in source if c in "éèêàùçœâîôÉÈÊÀÇ"]
        assert not accented, f"{name} holds French interface text: {set(accented)}"
