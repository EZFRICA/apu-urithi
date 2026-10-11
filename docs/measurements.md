# What was measured

Nothing in the README is asserted from a blog post. This is where the numbers come from.

## Speech out, ElevenLabs

The same 230-character answer, synthesised three times per model, then transcribed back to
check nothing was dropped. Two timings matter and they are not the same: the whole answer,
and the **first audio**, which is what a person actually waits for.

| Model | Latency | First audio | Audio produced | Read-back WER |
|---|---:|---:|---:|---:|
| `eleven_flash_v2_5` | **0.85 s** | **0.32 s** | 13.8 s | 0% |
| `eleven_v4_turbo` (in use) | 1.68 s | 0.35 s | 16.1 s | 0% |
| `eleven_v4` | 3.15 s | 0.77 s | 16.1 s | 0% |

`eleven_v4_turbo` halves `eleven_v4`'s latency and more than halves its time to first
audio, for a reading that comes back transcribed without a single error. Both v4 models
speak about a sixth more slowly than the flash model for the same text.

The read-back error rate is 0% for all three, so **it separates nothing**. The choice
between turbo and flash is about how the voice sounds, by someone listening, and it costs
under a second either way. That is the honest reading and it is why the apprentice uses the
better voice rather than the faster one: it speaks a handful of times per session, not
continuously.

For contrast, the same protocol against nine Gemini speech models put the fastest at
**3.47 s** and the slowest at 10.77 s. The gap is why speech out is ElevenLabs.

## Speech in, ElevenLabs

Ten clips, half in French, spoken by two different engines so no transcriber is graded only
on audio from its own provider.

| Model | Mean WER | Worst clip | Median |
|---|---:|---:|---:|
| `scribe_v1` | 6.7% | 14% | 1.02 s |
| `scribe_v2` (in use) | 6.7% | 14% | 0.92 s |

A second set, ten French questions carrying twenty-two numbers, because for anything
numeric the digits are the payload: **both keep 16 of 22, failing on the same three clips,
in the same places.** An error both models make on the same clip is the clip, not the
transcriber. The latency ordering also reversed between runs, which is the network.

**Nothing separates them.** Either will do, and saying otherwise would be inventing a
result.

## The pause, measured

How does the apprentice know the expert has paused? It cannot read their keyboard:
they work in another window and a browser tab sees none of it. So it reads the screen they
shared.

Each frame is drawn at 64 by 36 and compared with the one before it. The score is the mean
absolute difference per pixel across three channels, 0 to 255.

| What the person is doing | Score |
|---|---:|
| reading a form | under 1 |
| a cursor blinking | about 1 |
| typing, scrolling, switching window | above 3 |

The threshold is **2.5** (`MOTION_BUSY` in `guardian/ui/apprentice/capture.js`), and a pause is
2.5 seconds under it. The microphone adds the second signal at an RMS of 0.02, an order of
magnitude above room noise.

Both numbers are displayed live in the bar while the session runs, so the claim is
watchable rather than quotable.

Further measurements by feature:
- [measured-loop-and-sources.md](measured-loop-and-sources.md): the end-to-end loop, BrightData against a search index, and mutation guarantees.
- [measured-debrief.md](measured-debrief.md): the debrief, probes, rulings, and server isolation.
- [measured-stage-and-page.md](measured-stage-and-page.md): the stage and the page driven end to end.
