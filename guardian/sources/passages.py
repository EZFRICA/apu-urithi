"""A deposited document, read into passages a step can cite: evidence [A].

  PDF     one passage per page, its text as written       where: "page 3"
  audio   transcribed with word timings, cut at the end   where: "1:04–1:22"
          of each sentence (or every 30 seconds)
  image   described in words by the vision model          where: "the image"
          (Urithi's words, never the guardian's: a step is not made of them alone)

Every passage keeps exactly what the document holds, so a quote taken from it can be traced
back to its page or its moment. Costly reading is metered where it happens (apu/modality).
"""

import io
import re

from apu.modality import picture, voice

KINDS = {"application/pdf": "pdf", "image/png": "image", "image/jpeg": "image", "image/webp": "image",
         "audio/wav": "audio", "audio/x-wav": "audio", "audio/mpeg": "audio", "audio/mp4": "audio",
         "audio/webm": "audio", "audio/ogg": "audio"}
MAX_PASSAGE = 4000
AUDIO_SPAN = 30.0


class Unreadable(ValueError):
    """A document nothing could be read from, said as such."""


def kind_of(mime_type: str) -> str:
    kind = KINDS.get((mime_type or "").split(";")[0].strip().lower())
    if not kind:
        raise Unreadable("Audio, a PDF or an image (PNG, JPEG, WebP); not this kind of file.")
    return kind


def read(data: bytes, mime_type: str) -> list[dict]:
    kind = kind_of(mime_type)
    if kind == "pdf":
        return _pdf(data)
    if kind == "audio":
        return _audio(data, mime_type)
    return _image(data, mime_type)


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", text or "")).strip()


def _pdf(data: bytes) -> list[dict]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
    except Exception as error:
        raise Unreadable(f"This PDF could not be read: {error}") from error
    passages = [{"n": i, "where": f"page {i}", "page": i, "text": text[:MAX_PASSAGE]}
                for i, text in enumerate(pages, 1) if text]
    if not passages:
        raise Unreadable("No text could be read from this PDF (a scan with no text layer?).")
    return passages


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _audio(data: bytes, mime_type: str) -> list[dict]:
    try:
        _, words = voice.transcribe_timed(data, mime_type)
    except voice.VoiceUnavailable as error:
        raise Unreadable(str(error)) from error
    passages, current = [], []
    for word in words:
        current.append(word)
        ends = word["word"].rstrip().endswith((".", "?", "!"))
        if ends or word["end"] - current[0]["start"] >= AUDIO_SPAN:
            passages.append(current)
            current = []
    if current:
        passages.append(current)
    if not passages:
        raise Unreadable("Nothing could be heard in this recording.")
    return [{"n": i, "where": f"{_clock(p[0]['start'])}–{_clock(p[-1]['end'])}", "start": p[0]["start"],
             "end": p[-1]["end"], "text": " ".join(w["word"] for w in p)[:MAX_PASSAGE]}
            for i, p in enumerate(passages, 1)]


def _image(data: bytes, mime_type: str) -> list[dict]:
    try:
        text = picture.describe(data, mime_type)
    except picture.PictureUnavailable as error:
        raise Unreadable(str(error)) from error
    return [{"n": 1, "where": "the image", "text": text[:MAX_PASSAGE], "described": True}]


_PAGE = re.compile(r"\bpage\s+(\d+)\b", re.IGNORECASE)
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def find(said: str, passages: list[dict]) -> dict | None:
    """The passage a guardian names: "page 3", "what I said at 1:10". None when none is named."""
    page = _PAGE.search(said or "")
    if page:
        return next((p for p in passages if p.get("page") == int(page.group(1))), None)
    at = _TIME.search(said or "")
    if at:
        seconds = int(at.group(1)) * 60 + int(at.group(2))
        return next((p for p in passages if "start" in p and p["start"] - 1 <= seconds <= p["end"] + 1), None)
    return None
