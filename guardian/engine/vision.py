"""What changed on the screen, in one short line.

The apprentice does not need to understand the application. It needs to notice that
something was decided: a field took a new value, a different option was picked, a document
was opened. That is the hook a question hangs on.

Two frames go to the model, the one before and the one now, because "what changed" is a
question about a pair and asking it of a single image gets a description of a user
interface instead. When nothing changed, the answer is nothing, and the apprentice stays
quiet: most of a working session is a person reading.
"""

import base64
import io
import json

from apu import config
from apu.logger import get_logger
from guardian.engine.questions import Observation

logger = get_logger(__name__)

# Read at call time, like every setting: this runs whenever the shared screen changes, for
# the length of a class, so it is a fast model of its own (CLASS_VISION_MODEL, apu/config.py).

SYSTEM = (
    "You compare two screenshots of the same application, taken seconds apart, and report "
    "what a person changed between them.\n"
    'Return JSON only: {"changed": "...", "field": "...", "scene": "...", "fields": ["..."], '
    '"decision": true|false}\n'
    '- "changed": one short clause, the way a colleague would say it. '
    '"cost center changed from 4711 to 0400". Empty string if nothing meaningful changed.\n'
    '- "field": the name of the control that changed, if it is readable. Empty otherwise.\n'
    '- "scene": one or two plain sentences describing what the screen shows around the change '
    "(which panel or item is open, and what status banner, message, or log entries are visible).\n"
    '- "fields": list of "Label: value" strings for the fields, facts, statuses, and log lines '
    "readable on the screen in the second image.\n"
    '- "decision": true only if a person chose something, false for scrolling, loading, '
    "a cursor moving, or a clock ticking.\n"
    "Report only what you can see. Never guess what the application does.\n"
    # Measured in a live run: "Date and Announce in fields were filled", and the question
    # asked about it then guessed the date. Three in three now read 'Date set to "Thu 22 Oct,
    # 18:30", Announce in set to "#announcements"' from the same pair.
    "- In \"changed\", name each control that changed and its new value exactly as written on "
    "the screen, quoted: 'Cost center set to \"0400 Capital equipment\", Supplier set to "
    "\"Brenner GmbH\"'. Never say only that fields were filled or changed."
)

CAMERA_SYSTEM = (
    "You compare two camera frames from a guardian filming themselves teaching, taken seconds "
    "apart, and report what the guardian showed, did, or wrote between them.\n"
    'Return JSON only: {"changed": "...", "field": "...", "scene": "...", "fields": ["..."], '
    '"decision": true|false, "kind": "gesture|object|whiteboard|scene", "other_faces": [[x, y, w, h]]}\n'
    '- "changed": one short clause describing the gesture (pointing at a part, holding up a tool, '
    "demonstrating a hand motion), the physical object placed or adjusted, or the words/diagram "
    "written or erased on a whiteboard. Quote any whiteboard words or labels exactly. Empty string "
    "if only the camera swayed or the person shifted posture.\n"
    '- "field": the object, tool, or whiteboard section involved, if clear. Empty otherwise.\n'
    '- "scene": one or two plain sentences describing what the camera shows around the change.\n'
    '- "fields": list of labels, values, or whiteboard lines readable in the second frame.\n'
    '- "decision": true only for a deliberate teaching action (a gesture pointing or showing, '
    "bringing or changing an object, writing or drawing on a whiteboard), false for camera shake, "
    "blinking, or idle movement.\n"
    '- "kind": one of "gesture", "object", "whiteboard", or "scene".\n'
    '- "other_faces": list of normalized [x, y, w, h] boxes (0.0 to 1.0) for any face in the '
    "second frame OTHER than the guardian teaching (bystanders, colleagues, learners, photos on "
    "a wall). Empty list when only the guardian is visible."
)

CAMERA_PROMPT = (
    "The first image is before, the second is now. What gesture, object, or whiteboard change "
    "did the guardian make?"
)
SCREEN_PROMPT = "The first image is before, the second is now. What did the person change?"
COMPARE_PROMPT = (
    "The first image is the screen earlier, the second is the screen now. "
    "State in one or two plain sentences what changed between the first and the second, "
    "quoting exact labels and values as written on screen."
)

# Keyed by session, not global: two experts teaching at once would otherwise be compared
# against each other's screens, and the apprentice would report changes nobody made.
_previous: dict[str, str] = {}
_before_change: dict[str, str] = {}
_other_faces: dict[str, list[list[float]]] = {}


def _norm_boxes(raw_boxes: object) -> list[list[float]]:
    """Normalized [x, y, w, h] boxes in 0..1 for faces of others."""
    if not isinstance(raw_boxes, (list, tuple)):
        return []
    boxes: list[list[float]] = []
    for item in raw_boxes:
        try:
            if isinstance(item, dict):
                x = float(item.get("x", 0.0))
                y = float(item.get("y", 0.0))
                w = float(item.get("w", 0.0))
                h = float(item.get("h", 0.0))
            elif isinstance(item, (list, tuple)) and len(item) >= 4:
                x, y, w, h = float(item[0]), float(item[1]), float(item[2]), float(item[3])
            else:
                continue
        except (TypeError, ValueError):
            continue
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.0, min(1.0 - x, w))
        h = max(0.0, min(1.0 - y, h))
        if w > 0.01 and h > 0.01:
            boxes.append([x, y, w, h])
    return boxes


def blur_other_faces(raw: bytes, boxes: list | tuple = ()) -> bytes:
    """Blur the faces of other people in a camera frame before it is kept or shown."""
    norm = _norm_boxes(boxes)
    if not raw or not norm:
        return raw
    try:
        from PIL import Image, ImageFilter

        with Image.open(io.BytesIO(raw)) as img:
            rgb = img.convert("RGB")
            width, height = rgb.size
            for x, y, w, h in norm:
                left = max(0, int(round(x * width)))
                top = max(0, int(round(y * height)))
                right = min(width, max(left + 1, int(round((x + w) * width))))
                bottom = min(height, max(top + 1, int(round((y + h) * height))))
                patch = rgb.crop((left, top, right, bottom)).filter(
                    ImageFilter.GaussianBlur(radius=18)
                )
                rgb.paste(patch, (left, top))
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except Exception as error:
        logger.warning("Could not blur faces in camera frame: %s", error)
        return raw


def last_other_faces(session_id: str) -> list[list[float]]:
    """Normalized boxes of other faces seen in the latest camera frame for this session."""
    return list(_other_faces.get(session_id, []))


FACES_PROMPT = (
    "Return JSON only: {\"other_faces\": [[x, y, w, h]]} with normalized 0.0..1.0 boxes for any "
    "face in this camera frame OTHER than the main instructor teaching (bystanders, colleagues, "
    "learners, photos). Empty list when at most the instructor's face is present."
)


def detect_other_faces(raw: bytes, session_id: str = "") -> list[list[float]]:
    """Detect faces of other people in a single camera frame when none were cached yet."""
    if session_id and _other_faces.get(session_id):
        return list(_other_faces[session_id])
    if not raw:
        return []
    try:
        from google.genai import types

        from apu.inference.llm import usage_of
        from apu.meter import cost, meter
        from apu.modality.voice import get_client

        vision_model = config.CLASS_VISION_MODEL
        budget = meter().grant("model_cost", cost("vision", 1400, 200))
        response = get_client().models.generate_content(
            model=vision_model,
            contents=[types.Part.from_bytes(data=raw, mime_type="image/jpeg"), FACES_PROMPT],
            config=types.GenerateContentConfig(
                temperature=0.0, response_mime_type="application/json"
            ),
        )
        used = usage_of(response, "vision", "gemini", vision_model)
        meter().record(budget, cost("vision", used.prompt_tokens, used.output_tokens))
        parsed = json.loads(response.text)
        if isinstance(parsed, dict):
            faces = _norm_boxes(parsed.get("other_faces"))
            if session_id and faces:
                _other_faces[session_id] = faces
            return faces
    except Exception as error:
        logger.warning("Could not detect other faces in camera frame: %s", error)
    return []


def what_changed(
    frame_b64: str, session_id: str, at: float, *, source: str = "screen"
) -> Observation | None:
    """
    The latest frame against the one before it, or None when nothing was decided.

    None is the common answer and the important one: an apprentice that finds a decision in
    every frame will ask about scrolling. `at` is the session clock the page keeps, not a
    guess from how many frames have been seen.
    """
    previous = _previous.get(session_id)
    _previous[session_id] = frame_b64
    if previous is None:
        return None

    is_camera = source == "camera"
    try:
        from google import genai
        from google.genai import types

        from apu.inference.llm import usage_of
        from apu.meter import cost, meter
        from apu.modality.voice import get_client
        client: genai.Client = get_client()
        # Two frames and a short answer: a budget before, what was billed after (apu/meter.py).
        budget = meter().grant("model_cost", cost("vision", 2600, 400))
        response = client.models.generate_content(
            model=config.CLASS_VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=base64.b64decode(previous), mime_type="image/jpeg"),
                types.Part.from_bytes(data=base64.b64decode(frame_b64), mime_type="image/jpeg"),
                CAMERA_PROMPT if is_camera else SCREEN_PROMPT,
            ],
            config=types.GenerateContentConfig(
                system_instruction=CAMERA_SYSTEM if is_camera else SYSTEM, temperature=0.0,
                response_mime_type="application/json"),
        )
        used = usage_of(response, "vision", "gemini", config.CLASS_VISION_MODEL)
        meter().record(budget, cost("vision", used.prompt_tokens, used.output_tokens))
        seen = json.loads(response.text)
        # Measured: a smaller model answered with a list of changes, not one; the first is
        # read, and anything else is a frame skipped rather than a class stopped.
        if isinstance(seen, list):
            seen = seen[0] if seen else {}
        if not isinstance(seen, dict):
            raise ValueError(f"not an object: {type(seen).__name__}")
    except Exception as error:
        # A frame the model could not read is a frame skipped, not a session lost.
        logger.warning("Could not read the screen: %s", error)
        return None

    if is_camera:
        faces = _norm_boxes(seen.get("other_faces"))
        _other_faces[session_id] = faces
        if faces:
            blurred = blur_other_faces(base64.b64decode(frame_b64), faces)
            _previous[session_id] = base64.b64encode(blurred).decode("ascii")

    changed = str(seen.get("changed", "")).strip()
    if not changed or not seen.get("decision"):
        return None
    raw_fields = seen.get("fields")
    if isinstance(raw_fields, (list, tuple)):
        screen_fields = tuple(str(item).strip() for item in raw_fields if str(item).strip())
    elif isinstance(raw_fields, str) and raw_fields.strip():
        screen_fields = (raw_fields.strip(),)
    else:
        screen_fields = ()
    scene = str(seen.get("scene", "")).strip()
    _before_change[session_id] = previous
    return Observation(
        at=at,
        changed=changed,
        field=str(seen.get("field", "")).strip(),
        scene=scene,
        screen_fields=screen_fields,
    )


def frame_before_change(session_id: str, current_b64: str = "") -> bytes | None:
    """The frame from before the last change on screen, kept on purpose so 'compare with
    before' never compares the current screen against itself."""
    chosen = _before_change.get(session_id)
    if not chosen:
        prev = _previous.get(session_id)
        if prev and prev != current_b64:
            chosen = prev
    if not chosen:
        return None
    try:
        return base64.b64decode(chosen)
    except ValueError:
        return None


def compare_frames(before: bytes | None, now: bytes, *, focus: str = "") -> str:
    """Compare the current screen against the earlier one using CLASS_VISION_MODEL."""
    if not before:
        from apu.modality import picture

        try:
            return picture.describe(now, "image/jpeg", model=config.CLASS_VISION_MODEL, focus=focus)
        except Exception:
            return ""
    try:
        from google.genai import types
        from apu.inference.llm import usage_of
        from apu.meter import cost, meter
        from apu.modality.voice import get_client

        client = get_client()
        vision_model = config.CLASS_VISION_MODEL
        budget = meter().grant("model_cost", cost("vision", 2600, 400))
        prompt = COMPARE_PROMPT + (f" Focus on: {focus[:300]}" if focus else "")
        response = client.models.generate_content(
            model=vision_model,
            contents=[
                types.Part.from_bytes(data=before, mime_type="image/jpeg"),
                types.Part.from_bytes(data=now, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=600),
        )
        used = usage_of(response, "vision", "gemini", vision_model)
        meter().record(budget, cost("vision", used.prompt_tokens, used.output_tokens))
        return (response.text or "").strip()
    except Exception as error:
        logger.warning("Could not compare frames: %s", error)
        return ""


def forget(session_id: str) -> None:
    """Drop a finished session's last frame."""
    _previous.pop(session_id, None)
    _before_change.pop(session_id, None)
    _other_faces.pop(session_id, None)
