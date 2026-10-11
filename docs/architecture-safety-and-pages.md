# Architecture: capabilities behind interfaces and safety

Part of [architecture.md](architecture.md).

## Capabilities behind interfaces

| Capability | Online (default now) | Local (later, measured first) |
|---|---|---|
| Judgment, wording | Gemini | a small model (llama.cpp, Ollama) |
| Speech to text | ElevenLabs Scribe | Whisper |
| Text to speech | ElevenLabs (MP3 for what is kept) | Piper |
| Vision, documents | Gemini | a small vision-language model |
| Embeddings | | local ONNX |
| Braille | | liblouis |
| Illustration | Gemini image model, checked for writing | local image generation |
| Public sources | Bright Data, then Tavily | |
| Object storage | Cloud Storage, at saving | the local disk, temporary |
| Stores, cache, session state | a managed database and cache | SQLite, in process |

## Safety

- **An input guard** on both sides, failing closed: on topic, off topic, distress. Distress
  gets a caring reply and is never counted or stored.
- **A proof of a validated turn** before anything costly or risky runs.
- **The faithful output rail**: every sentence of an answer cites the guardian, every quote
  is verbatim, checked by code; otherwise the guardian's own words are shown.
- **Roles from a registry**, never from a request; identity is **simulated** and every page
  says so. A real sign-in replaces how a person is identified; nothing downstream changes.
- **Signed packages** (Ed25519): a changed word, answer, level or date is refused offline.
- **Withdrawing means everywhere**, the library and every device at its next connection.
