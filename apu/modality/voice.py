"""Speech in and speech out, around text the apprentice already has.

Speech in is transcribed to text first: the expert's answer, a ruling on a probe, a new
hire's yes or no in the exam. What is stored and checked is always that text, so a spoken
answer is held to exactly the same rules as a typed one. Speech out reads a sentence the
apprentice already wrote: a question, an intervention, the teach-back. Nothing here decides
anything.

Two jobs, two models, each with its own provider in the configuration:
  - transcription: a speech-to-text model, given one recorded file per answer;
  - speech: a text-to-speech model, given the sentence to read out.

ElevenLabs is the default for both, by measurement rather than preference: it synthesises
a sentence in under a second where the Gemini batch model takes several, and Scribe keeps
every number in a spoken amount, which is the payload an accounts clerk cannot lose.
Gemini remains available for either job by changing one setting. See docs/measurements.md.
"""

import base64
import io
import os
import re
import struct
import wave
from dataclasses import dataclass

from apu.meter import meter
from apu import config
from apu.logger import get_logger
from apu.modality.plain_text import plain_text

logger = get_logger(__name__)

# Asks for the words only. Without it a multimodal model tends to describe the recording
# ("The speaker asks...") or to answer the question it just heard, and what would then be
# stored as the expert's answer would not be what they said.
TRANSCRIPTION_PROMPT = (
    "Transcribe the speech in this audio exactly as it was spoken, word for word. "
    "Return only the transcript, with no quotation marks, no translation, no commentary, "
    "and do not answer what is said."
)

# Sample format the Gemini speech models return when they send raw PCM: the mime type says
# audio/L16 with a rate, which browsers cannot play as is, so it is wrapped into a WAV file.
_PCM_MIME = re.compile(r"^audio/(l16|pcm)(;|$)", re.I)
_RATE_IN_MIME = re.compile(r"rate=(\d+)")
_DEFAULT_PCM_RATE = 24000


class VoiceUnavailable(RuntimeError):
    """Speech in or speech out could not be produced (no key, model error, empty result)."""


@dataclass(frozen=True)
class SpokenAudio:
    data: bytes
    mime_type: str
    # Each word with when it is said, in seconds into the audio: the teleprompter shows it
    # as it is heard. Empty when the provider gives no timings (the Gemini fallback).
    words: tuple = ()


def words_from_alignment(alignment: dict) -> tuple[dict, ...]:
    """ElevenLabs times each character (measured: `characters`, `character_start_times_seconds`,
    `character_end_times_seconds`); the teleprompter shows words, so characters are joined
    between spaces, each word starting with its first character and ending with its last."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words, current, start, end = [], "", None, 0.0
    for char, begin, finish in zip(chars, starts, ends):
        if char.isspace():
            if current:
                words.append({"word": current, "start": round(start, 3), "end": round(end, 3)})
            current, start = "", None
            continue
        if start is None:
            start = begin
        current += char
        end = finish
    if current:
        words.append({"word": current, "start": round(start, 3), "end": round(end, 3)})
    return tuple(words)


_client = None
_http = None


def get_http():
    """The HTTP client for providers that are not the Gemini SDK, built on first use."""
    global _http
    if _http is None:
        import httpx

        _http = httpx.Client(timeout=120)
    return _http


def set_http(client) -> None:
    """Swap the HTTP client, for tests."""
    global _http
    _http = client


def _elevenlabs_key() -> str:
    api_key = os.environ.get(config.ELEVENLABS_API_KEY_ENV)
    if not api_key:
        raise VoiceUnavailable(
            f"{config.ELEVENLABS_API_KEY_ENV} is not set, so speech is unavailable. "
            "Add it to .env, switch the provider in the configuration, or use text or braille."
        )
    return api_key


def get_client():
    """
    The Gemini client, built on first use.

    Built lazily, like the text clients: a machine without a Gemini key must still start,
    run in text and braille, and fail only when someone actually asks for speech.
    """
    global _client
    if _client is None:
        api_key = os.environ.get(config.GEMINI_API_KEY_ENV)
        if not api_key:
            raise VoiceUnavailable(
                f"{config.GEMINI_API_KEY_ENV} is not set, so speech is unavailable. "
                "Add it to .env, or use the text or braille modes."
            )
        from google import genai  # imported here: the SDK is only needed for speech

        _client = genai.Client(api_key=api_key)
    return _client


def set_client(client) -> None:
    """Swap the client, for tests and for a device that builds its own."""
    global _client
    _client = client


def transcribe(audio: bytes, mime_type: str = "audio/wav") -> str:
    """
    One recording to the words it holds. The result is text like any other answer, and is
    checked exactly as a typed one would be.
    """
    if not audio:
        raise VoiceUnavailable("The recording is empty.")
    if len(audio) > config.VOICE_MAX_RECORDING_BYTES:
        raise VoiceUnavailable(
            f"The recording is too long ({len(audio) // 1024} kB, limit "
            f"{config.VOICE_MAX_RECORDING_BYTES // 1024} kB). Answer more briefly."
        )
    # Metered in seconds heard (apu/meter.py): 16 kHz, 16-bit, one channel, as the pages record.
    seconds = max(1.0, len(audio) / 32000)
    budget = meter().grant("transcribed_seconds", seconds)
    meter().record(budget)
    if config.VOICE_STT_PROVIDER == "elevenlabs":
        # Measured: the ElevenLabs key was refused (401) in the middle of a class, and every
        # answer said aloud was lost. Like speech (_synthesize_once), hearing falls back.
        try:
            text = _transcribe_elevenlabs(audio, mime_type)
        except VoiceUnavailable as error:
            logger.warning("ElevenLabs STT failed (%s); falling back to Gemini.", error)
            text = _transcribe_gemini(audio, mime_type)
    else:
        text = _transcribe_gemini(audio, mime_type)
    if not text:
        raise VoiceUnavailable("Nothing was transcribed. Record the answer again.")
    return text


def _transcribe_gemini(audio: bytes, mime_type: str) -> str:
    from google.genai import types

    try:
        response = get_client().models.generate_content(
            model=config.GEMINI_TRANSCRIBE_MODEL,
            contents=[
                TRANSCRIPTION_PROMPT,
                types.Part.from_bytes(data=audio, mime_type=mime_type),
            ],
        )
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Transcription failed: %s", error)
        raise VoiceUnavailable(f"Transcription failed: {error}") from error
    return _transcript_from_response(response)


def _transcribe_elevenlabs(audio: bytes, mime_type: str) -> str:
    extension = "mp3" if "mpeg" in mime_type else "wav"
    try:
        response = get_http().post(
            f"{config.ELEVENLABS_URL}/speech-to-text",
            headers={"xi-api-key": _elevenlabs_key()},
            data={"model_id": config.VOICE_STT_MODEL},
            files={"file": (f"answer.{extension}", audio, mime_type)},
        )
        response.raise_for_status()
        return (response.json().get("text") or "").strip()
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Transcription failed: %s", error)
        raise VoiceUnavailable(f"Transcription failed: {error}") from error


def transcribe_timed(audio: bytes, mime_type: str = "audio/wav") -> tuple[str, list[dict]]:
    """
    A recording to its words, each with when it is said: what a deposited recording is cut
    into, so a step proposed from it cites the exact moment. Measured: ElevenLabs returns
    `words` with `text`, `start`, `end` and `type` ("word" or "spacing") when asked for word
    timestamps. Metered in seconds heard. Raises VoiceUnavailable.
    """
    if not audio:
        raise VoiceUnavailable("The recording is empty.")
    if config.VOICE_STT_PROVIDER != "elevenlabs":
        raise VoiceUnavailable("Timed transcription needs the ElevenLabs transcriber.")
    seconds = max(1.0, len(audio) / 32000)
    budget = meter().grant("transcribed_seconds", seconds)
    extension = "mp3" if "mpeg" in mime_type else "wav"
    try:
        response = get_http().post(
            f"{config.ELEVENLABS_URL}/speech-to-text", headers={"xi-api-key": _elevenlabs_key()},
            data={"model_id": config.VOICE_STT_MODEL, "timestamps_granularity": "word"},
            files={"file": (f"source.{extension}", audio, mime_type)})
        response.raise_for_status()
        payload = response.json()
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Timed transcription failed: %s", error)
        raise VoiceUnavailable(f"Transcription failed: {error}") from error
    heard = float(payload.get("audio_duration_secs") or seconds)
    meter().record(budget, heard)
    words = [{"word": w["text"], "start": float(w["start"]), "end": float(w["end"])}
             for w in payload.get("words", []) if w.get("type", "word") == "word" and str(w.get("text", "")).strip()]
    return (payload.get("text") or "").strip(), words


def _transcript_from_response(response) -> str:
    """
    The transcript, wherever this model puts it.

    Measured live against a dedicated transcription model: it answers with an
    `audio_transcription` part, not a text one, and `response.text` is then empty (the SDK
    even warns about the non-text part). A general multimodal model used in its place would
    answer with plain text instead, so both are read.
    """
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            transcription = getattr(part, "audio_transcription", None)
            spoken_text = (getattr(transcription, "text", None) or "").strip() if transcription else ""
            if spoken_text:
                return spoken_text
            part_text = (getattr(part, "text", None) or "").strip()
            if part_text:
                return part_text
    return (getattr(response, "text", None) or "").strip()


# Knowledge kept on a device, or handed on as a file, carries its audio. Measured: nine parts
# read out as 24 kHz WAV made a 10 MB knowledge file. MP3 at 64 kbit/s is about six times smaller,
# and speech loses nothing a listener hears.
MP3_BITRATE = 64_000


def synthesize(text: str, voice: str | None = None, compressed: bool = False) -> SpokenAudio:
    """
    A sentence the apprentice already wrote, read out loud. `compressed` asks for MP3, for
    audio that is kept and carried rather than played once.

    Retried once when the audio comes back too short for the text, because the model
    sometimes stops early and someone listening has no way to know what was cut.
    """
    spoken = plain_text(text).strip()
    if not spoken:
        raise VoiceUnavailable("There is nothing to read out.")
    spoken = spoken[: config.VOICE_MAX_SPOKEN_CHARS]
    # Metered in characters read aloud, the unit the provider bills (apu/meter.py).
    budget = meter().grant("speech_chars", len(spoken))
    audio = _synthesize_once(spoken, voice, compressed)
    meter().record(budget)
    if _sounds_truncated(spoken, audio):
        logger.warning("Spoken answer looks cut (%s); reading it again.", _audio_seconds(audio))
        second_try = _synthesize_once(spoken, voice, compressed)
        return second_try if len(second_try.data) > len(audio.data) else audio
    return audio


def _synthesize_once(spoken: str, voice: str | None, compressed: bool = False) -> SpokenAudio:
    if config.VOICE_TTS_PROVIDER == "elevenlabs":
        try:
            return _synthesize_elevenlabs(spoken, voice, compressed)
        except Exception as exc:
            logger.warning("ElevenLabs TTS failed (%s); falling back to Gemini.", exc)
    return _synthesize_gemini(spoken, voice)


def _synthesize_elevenlabs(spoken: str, voice: str | None, compressed: bool = False) -> SpokenAudio:
    """
    Raw PCM rather than mp3 for what is played once, so the player gets the same WAV whatever
    the provider is; MP3 when asked, for what is kept (see MP3_BITRATE).
    """
    try:
        # With the time of every character, so the teleprompter can follow the voice word by word.
        response = get_http().post(
            f"{config.ELEVENLABS_URL}/text-to-speech/{voice or config.ELEVENLABS_VOICE_ID}/with-timestamps",
            params={"output_format": "mp3_44100_64" if compressed else "pcm_24000"},
            headers={"xi-api-key": _elevenlabs_key()},
            json={"text": spoken, "model_id": config.VOICE_TTS_MODEL},
        )
        response.raise_for_status()
        payload = response.json()
        audio = base64.b64decode(payload.get("audio_base64") or "")
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Speech synthesis failed: %s", error)
        raise VoiceUnavailable(f"Speech synthesis failed: {error}") from error
    if not audio:
        raise VoiceUnavailable("The speech model returned no audio.")
    words = words_from_alignment(payload.get("alignment") or {})
    if compressed:
        return SpokenAudio(audio, "audio/mpeg", words)
    return SpokenAudio(wav_from_pcm(audio, _DEFAULT_PCM_RATE), "audio/wav", words)


def _synthesize_gemini(spoken: str, voice: str | None) -> SpokenAudio:
    from google.genai import types

    try:
        response = get_client().models.generate_content(
            model=config.GEMINI_TTS_MODEL,
            contents=spoken,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice or config.GEMINI_TTS_VOICE
                        )
                    )
                ),
            ),
        )
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Speech synthesis failed: %s", error)
        raise VoiceUnavailable(f"Speech synthesis failed: {error}") from error

    return _audio_from_response(response)


def _audio_seconds(audio: SpokenAudio) -> float:
    """Duration of the WAV this module produces (16-bit mono at the model's rate), or of its MP3."""
    if audio.mime_type == "audio/mpeg":
        return len(audio.data) * 8 / MP3_BITRATE
    if not audio.mime_type.startswith("audio/wav") or len(audio.data) <= 44:
        return 0.0
    try:
        with wave.open(io.BytesIO(audio.data), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate() or _DEFAULT_PCM_RATE)
    except wave.Error:
        return 0.0


def _sounds_truncated(spoken: str, audio: SpokenAudio) -> bool:
    seconds = _audio_seconds(audio)
    if seconds <= 0:
        return False  # not a format this module can measure; take it as given
    expected = len(spoken) / config.VOICE_CHARS_PER_SECOND
    return seconds < expected * config.VOICE_MIN_AUDIO_RATIO


def _audio_from_response(response) -> SpokenAudio:
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                mime_type = getattr(inline, "mime_type", "") or "audio/wav"
                if _PCM_MIME.match(mime_type):
                    return SpokenAudio(wav_from_pcm(inline.data, _sample_rate(mime_type)), "audio/wav")
                return SpokenAudio(inline.data, mime_type)
    raise VoiceUnavailable("The speech model returned no audio.")


def _sample_rate(mime_type: str) -> int:
    match = _RATE_IN_MIME.search(mime_type)
    return int(match.group(1)) if match else _DEFAULT_PCM_RATE


def wav_from_pcm(pcm: bytes, sample_rate: int = _DEFAULT_PCM_RATE, channels: int = 1) -> bytes:
    """Wrap signed 16-bit PCM in a WAV container, which browsers and players accept."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def silence(seconds: float = 0.2, sample_rate: int = _DEFAULT_PCM_RATE) -> bytes:
    """A short silent WAV, used by the tests and as a placeholder recording."""
    frames = struct.pack("<h", 0) * int(seconds * sample_rate)
    return wav_from_pcm(frames, sample_rate)
