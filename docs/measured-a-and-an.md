# Measured: end-to-end "a" and "an", Bright Data, and the provider SDK

Part of [urithi-measured.md](urithi-measured.md).

## A real test, end to end: "a" and "an"

Every feature, as a guardian and as learners, with the real services: Ezekias taught how to
choose "a" or "an" in English, by typing and by voice, then a visitor and a community member
learned it, online and offline. Nineteen defects, one of them made by the fix of another,
each fixed and now a test:

- **Teaching.** The extractor made rules from a principle nobody stated as a rule, then added
  them again in other words: nine rules for seven. It is now given the rules already noted;
  measured after, five rules in five, twice. Step titles were cut inside a word ("I stop and
  chec..."). A model-built case pointed at "Roman numerals like this", a case it never named.
- **Sources.** Every lookup "returned no results": Bright Data was refusing the machine's
  address (its allow-list), and the refusal read as an empty search. It is said as a refusal,
  and Tavily takes over. The page asked for German sources, a leftover of the invoice
  example, for a grammar rule. One garbled social network post made a textbook rule
  "conflicted"; such posts are not sources. A model judged two agreeing pages as disagreeing;
  it is told that the same answer in other words agrees (not yet measured again).
- **The debrief.** A hurried "yes" to "an unique solution" was hidden in the teach-back ("close
  to it, but not it: yes") and could not be taken back, and an invented rule could not be
  removed. The teach-back now says each case, any case can be answered again, any rule taken
  out. Going back to the inbox forgot the question being answered.
- **Learning.** A step taught last came second for a visitor, because the step before it was
  kept to the community; the order now holds across hidden parts. A test case about "MBA"
  showed a visitor what had been kept closed; the first fix, on every word, also closed a case
  about Roman numerals, so only distinctive words count. A case settled by "which one is
  followed here?" was put to learners as yes or no. Kept knowledge was rebuilt twice at once.
  Its file weighed 10 MB for nine parts: the audio is now MP3, 153 kB a part instead of 908.
  The refusal of an off-topic question read "ask me about it", about what it had just refused.
- **Access.** Withdrawn and published again, a body would have opened what was closed: the
  levels lived only in the library. The guardian's map now remembers them.

Worked as built: the voice in both directions (a spoken sentence transcribed word for word, a
spoken quiz answer graded), braille on screen and for an embosser, FSRS reviews, the guard
(off topic refused, distress answered with care and stored nowhere), answers in French from
English teaching, nothing restricted shown to a visitor, the exam, offline learning and its
sync, a signed file refused once changed, the inbox loop to version 2, withdrawal reaching the
device, the screen-watching path and the stage. Not drivable here: screen sharing and the
camera, which the built-in browser blocks.

### Sources, once Bright Data answered again

With the machine's address allowed, the search answered, but every page came back a 400: no
Unlocker zone is set up, and the default name pointed at one that does not exist, so the judge
read 140-character snippets. Pages are now fetched as a browser would, and a snippet is used
only when that fails. A 502 from the search, four times in seven, is asked once more before
handing over to Tavily. And a snippet cut mid-sentence ("...sounds like it begins with a ...")
made Merriam-Webster contradict a textbook rule; a snippet may now confirm a rule, never
contradict it. Measured last: six rules in seven corroborated (Purdue OWL, Scribbr, QuillBot,
Merriam-Webster, The Guardian), no false conflict, one retry, one hand-over; the seventh,
checking a dictionary when unsure, is rightly a house rule. The judge's earlier false
conflicts (lawprose.org, the Canadian government's language portal) now read as agreeing.

### The provider's own SDK

The two text roles moved from Gemini's OpenAI-compatible endpoint to `google-genai`
(decision 0012). Neither returns a price; the endpoint hid the thinking it billed (2
completion tokens for a call of 121), the SDK reports it: wording one question spent 623
thinking tokens for a 17-token answer. Each role ran live after the change: extraction, the
apprentice's question, reading a verdict, the guard. The change surfaced a defect older than
it: the model now quotes with straight marks, and the faithful rail paired the closing mark
of one short quotation with the opening mark of the next, read the words between as a
quotation and refused three right answers in three. Quotations are now paired by their own
marks; the same three pass.
