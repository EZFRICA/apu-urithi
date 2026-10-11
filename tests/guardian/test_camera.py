"""P3: The camera's own rules: gestures, objects, a whiteboard, pauses from a moving camera, and faces of others blurred."""

import base64
import io
import json
from types import SimpleNamespace

from PIL import Image, ImageDraw

from apu.modality import picture, voice
from guardian.api import routes
from guardian.engine import absorb, questions, vision
from guardian.engine.workmap import WorkMapStore
from guardian.memory.store import set_maps
from guardian.sources.store import get_sources
from server import app
from tests.guardian.test_engine import taught_map
from tests.support import guardian_client


def _checker_jpeg(width: int = 200, height: int = 120) -> bytes:
    """An image with a sharp checkerboard in the right half (where a bystander's face might sit)
    and a solid left half (where the guardian stands)."""
    img = Image.new("RGB", (width, height), (40, 80, 140))
    draw = ImageDraw.Draw(img)
    for y in range(20, 80, 4):
        for x in range(120, 180, 4):
            color = (250, 250, 250) if ((x + y) // 4) % 2 == 0 else (10, 10, 10)
            draw.rectangle([x, y, x + 3, y + 3], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_faces_of_other_people_are_blurred_while_the_rest_of_the_camera_frame_stays_sharp():
    raw = _checker_jpeg()
    blurred = vision.blur_other_faces(raw, [[0.6, 0.15, 0.3, 0.55]])
    with Image.open(io.BytesIO(raw)) as before, Image.open(io.BytesIO(blurred)) as after:
        # Left side (guardian) stays near (40, 80, 140)
        r0, g0, b0 = before.getpixel((30, 50))
        r1, g1, b1 = after.getpixel((30, 50))
        assert abs(r0 - r1) < 8 and abs(g0 - g1) < 8 and abs(b0 - b1) < 8

        # Right side (bystander face checkerboard) had extremes ~10 and ~250; after Gaussian blur,
        # local contrast inside the box is smoothed toward the midtone.
        patch_before = [before.getpixel((x, 40))[0] for x in range(130, 170)]
        patch_after = [after.getpixel((x, 40))[0] for x in range(130, 170)]
        assert max(patch_before) - min(patch_before) > 150
        assert max(patch_after) - min(patch_after) < 60


def test_camera_observation_uses_camera_rules_for_gestures_objects_whiteboard_and_blurs_other_faces(tmp_path, monkeypatch):
    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    work_map = taught_map()
    maps.save(work_map)
    client = guardian_client(app)
    map_id = work_map.map_id

    seen_configs = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            seen_configs.append((model, contents, config.system_instruction))
            return SimpleNamespace(
                text=json.dumps({
                    "changed": "pointed at the brass pressure gauge and wrote \"2.4 bar max\" on the whiteboard",
                    "field": "whiteboard",
                    "decision": True,
                    "kind": "whiteboard",
                    "other_faces": [[0.6, 0.15, 0.3, 0.55]],
                }),
                usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=30),
            )

    monkeypatch.setattr(voice, "get_client", lambda: SimpleNamespace(models=FakeModels()))
    monkeypatch.setattr(picture, "describe", lambda raw, mime, **kw: "Whiteboard: 2.4 bar max")
    monkeypatch.setattr(absorb, "find_guardrails", lambda *a, **kw: [])
    monkeypatch.setattr(questions, "word_question", lambda *a, **kw: "Why 2.4 bar max?")
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})

    frame_b64 = base64.b64encode(_checker_jpeg()).decode("ascii")
    # First camera frame seeds the comparison (after guardian warning)
    client.post(
        "/api/guardian/observe",
        json={"map_id": map_id, "at": 0.0, "frame": frame_b64, "source": "camera", "camera_warned": True},
    )
    # Second camera frame triggers CAMERA_SYSTEM and detects a bystander's face
    obs = client.post(
        "/api/guardian/observe",
        json={"map_id": map_id, "at": 2.0, "frame": frame_b64, "source": "camera", "camera_warned": True},
    ).json()

    assert "2.4 bar max" in (obs.get("change") or "")
    assert seen_configs and "whiteboard" in seen_configs[0][2]
    assert vision.last_other_faces(map_id) == [[0.6, 0.15, 0.3, 0.55]]

    # Keeping the camera frame blurs the bystander's face in the stored source image
    kept = client.post(
        "/api/guardian/remember",
        json={
            "map_id": map_id,
            "frame": frame_b64,
            "said": "Remember the 2.4 bar max written on the whiteboard.",
            "at": 3.0,
            "source": "camera",
        },
    ).json()
    source_id = kept["source"]["source_id"]
    saved_bytes = get_sources().data("urithi", map_id, source_id)
    with Image.open(io.BytesIO(saved_bytes)) as saved_img:
        patch = [saved_img.getpixel((x, 40))[0] for x in range(130, 170)]
        assert max(patch) - min(patch) < 60


def test_camera_frames_require_page_blur_or_guardian_warning_and_an_empty_face_list_never_skips_blurring(tmp_path, monkeypatch):
    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    work_map = taught_map()
    maps.save(work_map)
    client = guardian_client(app)
    map_id = work_map.map_id

    vision_calls = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            vision_calls.append(config.system_instruction)
            return SimpleNamespace(
                text=json.dumps({"other_faces": [[0.6, 0.15, 0.3, 0.55]]}),
                usage_metadata=SimpleNamespace(prompt_token_count=60, candidates_token_count=20),
            )

    monkeypatch.setattr(voice, "get_client", lambda: SimpleNamespace(models=FakeModels()))
    monkeypatch.setattr(picture, "describe", lambda raw, mime, **kw: "Whiteboard frame")
    monkeypatch.setattr(absorb, "find_guardrails", lambda *a, **kw: [])
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})

    frame_b64 = base64.b64encode(_checker_jpeg()).decode("ascii")
    # Without blurred_on_page or camera_warned, no camera image is sent to the vision provider
    unwarned = client.post(
        "/api/guardian/observe",
        json={"map_id": map_id, "at": 0.0, "frame": frame_b64, "source": "camera"},
    ).json()
    assert unwarned.get("unwarned_camera") is True
    assert vision_calls == []

    # Even when the page sends an empty other_faces list [], remember() still detects and blurs bystander faces
    kept = client.post(
        "/api/guardian/remember",
        json={
            "map_id": map_id,
            "frame": frame_b64,
            "said": "Remember this setup.",
            "at": 1.0,
            "source": "camera",
            "other_faces": [],
        },
    ).json()
    source_id = kept["source"]["source_id"]
    saved_bytes = get_sources().data("urithi", map_id, source_id)
    with Image.open(io.BytesIO(saved_bytes)) as saved_img:
        patch = [saved_img.getpixel((x, 40))[0] for x in range(130, 170)]
        assert max(patch) - min(patch) < 60


def test_a_value_read_by_the_camera_does_not_enter_a_rule_without_the_guardian_confirming_it(tmp_path, monkeypatch):
    from guardian.engine.workmap import Guardrail

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    work_map = taught_map()
    maps.save(work_map)
    client = guardian_client(app)
    map_id = work_map.map_id
    initial_rails = len(work_map.guardrails)

    monkeypatch.setattr(
        vision,
        "what_changed",
        lambda frame, sid, at, source="screen": questions.Observation(
            at=at, changed='Wrote "24 bar max" on the whiteboard'
        ),
    )
    monkeypatch.setattr(questions, "word_question", lambda *a, **kw: "Why did you write that limit on the whiteboard?")
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})

    obs = client.post(
        "/api/guardian/observe",
        json={"map_id": map_id, "at": 10.0, "frame": "x", "source": "camera", "camera_warned": True},
    ).json()
    assert "question" in obs

    # 1. Suppose a rail with the misread "24 bar" is extracted while the guardian did not state "24"
    monkeypatch.setattr(
        absorb,
        "find_guardrails",
        lambda said, **kw: [
            Guardrail(
                guardrail_id="g-misread",
                when="the pressure exceeds 24 bar",
                then="open the relief valve",
                quote=said,
                asked_at=10.0,
                severity="stop",
            )
        ],
    )
    first_ans = client.post(
        "/api/guardian/answer",
        json={"map_id": map_id, "said": "If pressure exceeds the limit on the board, open the relief valve."},
    ).json()
    assert first_ans["guardrails"] == []
    assert first_ans.get("confirm_value") == "24"
    assert len(maps.load(map_id).guardrails) == initial_rails

    # 2. When the guardian confirms the real value in their own words ("2.4 bar"), the rule enters the proposal and map when saved
    monkeypatch.setattr(
        absorb,
        "find_guardrails",
        lambda said, **kw: [
            Guardrail(
                guardrail_id="g-confirmed",
                when="the pressure exceeds 2.4 bar",
                then="open the relief valve",
                quote=said,
                asked_at=10.0,
                severity="stop",
            )
        ],
    )
    second_ans = client.post(
        "/api/guardian/answer",
        json={"map_id": map_id, "said": "It is 2.4 bar max: when pressure exceeds 2.4 bar, open the relief valve."},
    ).json()
    assert len(second_ans["proposal"]["guardrails"]) == 1
    assert "2.4 bar" in second_ans["proposal"]["guardrails"][0]["when"]
    client.post(
        "/api/guardian/save",
        json={"map_id": map_id, "proposal_id": second_ans["proposal"]["proposal_id"]},
    )
    saved_rails = maps.load(map_id).guardrails
    assert len(saved_rails) == initial_rails + 1
    assert saved_rails[-1].when == "the pressure exceeds 2.4 bar"


def test_a_word_read_by_the_camera_in_another_alphabet_does_not_enter_a_step_or_rule_without_confirmation(
    tmp_path, monkeypatch
):
    from guardian.engine.workmap import Guardrail

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    work_map = taught_map()
    maps.save(work_map)
    client = guardian_client(app)
    map_id = work_map.map_id
    initial_rails = len(work_map.guardrails)

    monkeypatch.setattr(
        vision,
        "what_changed",
        lambda frame, sid, at, source="screen": questions.Observation(
            at=at, changed='Wrote "2.벤트 bypass" on the whiteboard'
        ),
    )
    monkeypatch.setattr(
        questions,
        "judge_learner_gap",
        lambda *a, **kw: questions.PupilJudgment(
            kind=questions.QuestionKind.SKIPPED_STEP,
            importance=4,
            why="The learner needs to know why the bypass is vented first.",
            question="Why vent bypass before opening the main valve?",
        ),
    )
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})

    obs = client.post(
        "/api/guardian/observe",
        json={"map_id": map_id, "at": 12.0, "frame": "x", "source": "camera", "camera_warned": True},
    ).json()
    assert "question" in obs

    monkeypatch.setattr(
        absorb,
        "find_guardrails",
        lambda said, **kw: [
            Guardrail(
                guardrail_id="g-foreign",
                when="opening 2.벤트 bypass",
                then="check the relief gauge first",
                quote=said,
                asked_at=12.0,
                severity="check",
            )
        ],
    )
    ans = client.post(
        "/api/guardian/answer",
        json={"map_id": map_id, "said": "We vent the bypass first so trapped pressure does not slam the seat."},
    ).json()
    # The Hangul misread "2.벤트" never enters the proposal or saved step title, observed text, or guardrails
    assert "벤트" not in ans["proposal"]["title"]
    assert ans["proposal"]["guardrails"] == []
    assert ans.get("confirm_value") == "벤트"
    client.post(
        "/api/guardian/save",
        json={"map_id": map_id, "proposal_id": ans["proposal"]["proposal_id"]},
    )
    saved = maps.load(map_id)
    assert "벤트" not in saved.steps[-1].title
    assert "벤트" not in saved.steps[-1].observed
    assert "벤트" not in saved.steps[-1].decision
    assert len(saved.guardrails) == initial_rails
