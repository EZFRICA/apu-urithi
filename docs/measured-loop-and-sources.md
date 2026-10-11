# Measured: the loop, public sources, and mutation guarantees

Part of [measurements.md](measurements.md).

## The loop, end to end

Two frames of an invoicing screen twelve seconds apart, through the running server:

```
saw     : Cost center changed from 4711 (opex) to 0400 (capex)
paused  : 12 s
asked   : "What made you switch the cost center from 4711 opex to 0400 capex on this one?"
spoken  : yes

answered: "Equipment over five thousand euros is always capex. And if I do not
           recognise the supplier, I stop and ask the controller before booking anything."

learned : [check] when equipment is over five thousand euros -> treat it as capex
          [stop]  when the supplier is not recognised       -> stop and ask the controller
teachable: yes
```

Then a case the expert never showed, a 2,400 euro invoice from an unknown Czech supplier:

```
save allowed: false
caught      : the unknown-supplier rail, quoting Sabine, replay at 3:12, certain
not fired   : the five-thousand-euro rail, correctly, and listed as still to practise
mastery     : 1/2
```

## Three defects these runs found

Worth recording, because each was found by running the thing rather than reading it.

**JSON came back fenced**, and the tutor failed closed on a rule that did not apply. A new
hire would have been stopped for a reason that was not real. Failing closed is right;
failing closed because of a backtick is not. Fixed in `guardian/engine/jsonish.py`.

**Questions came back truncated** ("Why", "If the rule") because the token budget was sized
for one spoken sentence and a reasoning model spends it before the first word of the
answer. A half-formed question is now discarded rather than spoken.

**`hidden` was beaten by `display: flex`**, so the setup bar and the running bar were on
screen at the same time.

## Does the rule still hold? BrightData against a search index

The same question, asked two ways. The rule under test is Sabine's: *equipment over five
thousand euros is always capex*, in German accounts payable.

| Backend | Top sources returned | What the apprentice concluded |
|---|---|---|
| Tavily | `finance.duke.edu` (a US university's internal accounting manual) | **CONFLICTED**, against American policy. Wrong, and dangerous. |
| Tavily, after the jurisdiction filter | the same page, set aside | **HOUSE_RULE**. Honest, and useless: the rule is public, the index could not reach it. |
| BrightData SERP, country `de` | `gesetze-im-internet.de` (the statute), `haufe.de`, `norman.finance`, `gofinto.com` | **CONFLICTED**, against two German sources that both state 800 euros. Correct. |

The query the model wrote was right in every run, including in German
(`Aktivierungsgrenze Sachanlagen HGB 5000 Euro`). What changed was whether the backend
could reach a German authority. That is the whole case for a geo-targeted SERP, and it is
why the backend is recorded on every citation.

### The two defects this found

**A source from the wrong country raised a conflict.** A US university's internal manual,
cited against German law. Every citation now carries the jurisdiction the page speaks for,
and one outside the country of the work is set aside with a note saying how many were. A
rule flagged against the wrong law is worse than no flag, because somebody acts on it.

**The Web Unlocker returned 400 on every page**, because its zone is not created in the
account. The fallback behaved: the search snippet was used, about 150 characters, and the
reason was logged for each page rather than swallowed. Set `BRIGHTDATA_UNLOCKER_ZONE` to
read the statutes themselves instead of the snippet about them.

## The guarantees, broken on purpose

A passing suite says the code does something, not that a test would notice if it stopped.
`scripts/mutate.py` breaks each guarantee in turn and checks something fails. It started at
nine; one survived the first run (a test asserted a message, not the verdict).

### And the incident that script caused

An earlier version of the runner had no guaranteed restore. It was interrupted between
writing a mutant and putting the file back, and left `_applies_here` returning `True` for
every country. The broken filter then ran against live BrightData results and flagged a
German rule against an American source, which is exactly the defect the filter exists to
prevent.

It was found by reading the function after the result looked wrong, not by the suite:
`test_a_page_for_another_country_is_set_aside` would have failed, and did fail, which is
what the interrupted run was in the middle of proving. The runner now restores on exit, on
Ctrl-C, on SIGTERM and on SIGHUP, and the reason is written at the top of the file.
