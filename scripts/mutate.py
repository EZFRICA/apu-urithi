#!/usr/bin/env python3
"""
Break each guarantee on purpose, and check a test notices.

    uv run python scripts/mutate.py
    uv run python scripts/mutate.py --list
    uv run python scripts/mutate.py --only "quotations paired"   # one guarantee, alone

A passing suite says the code does something. It does not say the tests would notice if it
stopped. This applies one deliberate defect at a time, runs the suite, and reports whether
anything failed. A mutant nobody catches is a guarantee nobody is holding.

**It restores the file whatever happens**, including on Ctrl-C and on a kill. An earlier
version of this script did not: it was interrupted between writing a mutant and restoring
it, and left `_applies_here` returning True for every country. The bug then shipped into a
live run and flagged a German rule against an American source. Hence the signal handlers,
and hence this paragraph.
"""

import argparse
import concurrent.futures
import os
import pathlib
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]

# (what it breaks, file, the real line, the broken line)
MUTANTS = [
    ("the jurisdiction filter", "guardian/engine/provenance.py",
     'return found in ("", "any", "international", country.lower())', "return True"),
    ("unchecked never becoming corroborated", "guardian/engine/provenance.py",
     "return Provenance(verdict=Verdict.UNCHECKED, checked_at=now, query=query,\n"
     "                          note=str(error))",
     "return Provenance(verdict=Verdict.CORROBORATED, checked_at=now, query=query,\n"
     "                          note=str(error))"),
    ("a conflict carrying both sides", "guardian/engine/provenance.py",
     'f"The expert said: {rail.quote}"', '""'),
    ("a contradicted rule being declared", "guardian/engine/tutor.py",
     'if (rail.provenance or {}).get("verdict") == "conflicted" and precedent is None:',
     "if False:"),
    ("failing closed on a rail it cannot read", "guardian/engine/tutor.py",
     "        return True, False\n    if verdict ==", "        return False, True\n    if verdict =="),
    ("discarding a half-formed question", "guardian/engine/questions.py",
     'if len(question) < 12 or not question.endswith("?"):', "if False:"),
    ("keeping the expert's sentence verbatim", "guardian/engine/absorb.py",
     "quote=said.strip(),", 'quote="",'),
    ("counting only the rails that were tested", "guardian/engine/tutor.py",
     "met = [r for r in rails if r.guardrail_id in seen]", "met = list(rails)"),
    ("a map with no reason refusing to teach", "guardian/engine/workmap.py",
     "and all(step.reason.strip() for step in self.steps)", "and True"),
    ("arithmetic deciding a numeric rule", "guardian/engine/tutor.py",
     "    if decided is not None:\n        return decided, True",
     "    if False:\n        return decided, True"),
    ("the exact boundary of a threshold", "guardian/engine/thresholds.py",
     "return amount >= threshold.value if threshold.inclusive else amount > threshold.value",
     "return amount >= threshold.value"),
    ("reading a German decimal comma", "guardian/engine/thresholds.py",
     'decimal = "," if digits.rfind(",") > digits.rfind(".") else "."', 'decimal = "."'),
    ("uncertainty said on a check rule", "guardian/engine/tutor.py",
     '    if not certain:\n        lead = "I cannot tell whether this one applies, so before you "\n    elif',
     "    if False:\n        pass\n    elif"),
    ("no timestamp on a page for a reader without the screen", "guardian/engine/braille.py",
     'lines.append(f"Step {step.number}. {step.title}")',
     'lines.append(f"Step {step.number}. {step.title} ({step.screen_moment})")'),
    ("a disputed rule said in words", "guardian/engine/braille.py",
     'return ("Note: a public source now says something different about this. "',
     'return ("'),
    ("refusing to hand over a blank page", "guardian/engine/braille.py",
     "        raise BrailleUnavailable(str(error)) from error",
     "        return BrailleWorkMap('', '', '', 0, int(grade))"),
    ("push to talk released on key up", "guardian/ui/teach/teach.js",
     'window.addEventListener("keyup"', 'window.addEventListener("keyupx"'),
    ("the debrief asking the most expensive question first", "guardian/engine/probe.py",
     "    found.sort(key=lambda p: ORDER[p.kind])", "    pass"),
    ("money read beside its currency, not from a year", "guardian/engine/probe.py",
     'public = thresholds.money_in(citation.get("says", ""))',
     'public = thresholds._digits_to_number(citation.get("says", ""))'),
    ("not asking what was already decided", "guardian/engine/probe.py",
     "            if probe and (probe.guardrail_id, probe.kind) not in asked:",
     "            if probe:"),
    ("asking what she would do, not whether her rule applies", "guardian/engine/probe.py",
     '                f"The action: {probe.action or \'what the rule says\'}\\n"',
     '                ""'),
    ("a decided case outranking the rule", "guardian/engine/tutor.py",
     "        if ruling.kind != \"collision\" and _same_case(ruling.case, case):",
     "        if False:"),
    ("one source ruling moving the threshold for every case", "guardian/engine/tutor.py",
     'if r.kind == "source" and r.applies and r.case.get("public_threshold")), None)',
     'if False), None)'),
    ("saying two rules in the order she works", "guardian/engine/tutor.py",
     "    interventions = _in_the_experts_order(interventions, work_map)", "    pass"),
    ("telling the new hire who cleared a case", "guardian/engine/tutor.py",
     "                cleared.append(precedent)", "                pass"),
    ("descriptions never matching as facts", "guardian/engine/tutor.py",
     "if isinstance(v, (bool, int, float)) and k != \"public_threshold\"}",
     "if k != \"public_threshold\"}"),
    ("an empty search staying unchecked", "guardian/engine/provenance.py",
     "    if not sources:\n", "    if False:\n"),
    ("a rule with an amount always looked up", "guardian/engine/provenance.py",
     "    if not public and thresholds.threshold_in(rail.when) is not None:",
     "    if False:"),
    ("the exam explaining a mistake in her words", "guardian/engine/probe.py",
     '"because": f"{ruling.by} said: \\"{ruling.said}\\"",', '"because": "",'),
    ("a spoken yes and no together never graded", "apu/language.py",
     "    if yes == no:\n        return None", "    if False:\n        return None"),
    ("hesitation never taken for an answer", "apu/language.py",
     "    if not said or _UNSURE.search(said):", "    if not said:"),
    ("the screen's braille pages being the embosser's", "apu/modality/braille/sheet.py",
     "braille_ascii_to_unicode(line) for line in page.lines)",
     "braille_ascii_to_unicode(line) for line in page.lines[:1])"),
    ("an unclear exam answer asked again on the stage", "apu/ui/presentation/stage.js",
     "      if (!reply.understood) {", "      if (false) {"),
    ("a key with nothing to do saying so", "apu/ui/presentation/stage.js",
     '        : "Talk answers the exam. Turn the wheel to the exam, or press 3.");',
     '        : "");'),
    ("the showcase at the root", "server.py",
     'app.mount("/", FreshStaticFiles(directory=SHARED_UI / "showcase"',
     'app.mount("/", FreshStaticFiles(directory=GUARDIAN_UI / "apprentice"'),
    ("a class sending only a changed screen", "guardian/ui/teach/capture.js",
     "      if (first || changed > 0) {", "      if (true) {"),
    ("a small change counted as a change", "guardian/ui/teach/capture.js",
     "    if (d / 3 > pixelThreshold) changed += 1;", "    if (d / 3 > pixelThreshold * 20) changed += 1;"),
    ("a class question opening the microphone", "guardian/ui/teach/teach.js",
     "this.voice(reply.audio, reply.words, reply.question, () => this.listenForAnswer());",
     "this.voice(reply.audio, reply.words, reply.question);"),
    ("what a class saw kept in its notes", "guardian/ui/teach/teach.js",
     '        this.note("saw", change);\n', ""),
    ("a class answer said back", "guardian/api/routes.py",
     '            "noted": _noted(work_map.language, proposal),', '            "noted": "",'),
    ("a class question carrying what was seen", "guardian/api/routes.py",
     '            "change": change.changed if change else None,', '            "change": None,'),
    ("hearing falling back when the key is refused", "apu/modality/voice.py",
     "            text = _transcribe_gemini(audio, mime_type)\n    else:",
     "            raise\n    else:"),
    ("a class answer not heard said so", "guardian/ui/teach/teach.js",
     'if (reply.error) { this.line("apprentice", reply.error); this.prompter.speaking(reply.error); }',
     "if (reply.error) { }"),
    ("listening not left on screen", "guardian/ui/teach/teach.js",
     '    this.prompter.show("you", this.t("writingDown"), { linger: 15000 });\n', ""),
    ("a class read by its own fast model", "guardian/engine/vision.py",
     "            model=config.CLASS_VISION_MODEL,", "            model=config.VISION_MODEL,"),
    ("a list of changes read, not a class stopped", "guardian/engine/vision.py",
     "            seen = seen[0] if seen else {}", "            pass"),
    ("a gap answered not asked again", "guardian/engine/questions.py",
     "    if not work_map.guardrails and QuestionKind.LIMIT not in asked:", "    if not work_map.guardrails:"),
    ("what was said worded as said", "guardian/engine/questions.py",
     '                + (f"What they just said: {observation.changed}\\n" if said',
     '                + (f"What just changed on screen: {observation.changed}\\n" if said'),
    ("no threshold nobody mentioned", "guardian/engine/questions.py",
     '    "a number, an amount or a threshold they did not mention.\\n"', '    "\\n"'),
    ("the question worded by its own model", "guardian/engine/questions.py",
     "        ], temperature=0.3, max_tokens=2000, model=config.QUESTION_MODEL)",
     "        ], temperature=0.3, max_tokens=2000)"),
    ("a remembered screen cited by its step", "guardian/api/source_routes.py",
     "                said_at=said_at, cites=(cite,))", "                said_at=said_at)"),
    ("a remembered screen asked about", "guardian/api/source_routes.py",
     '            "asked_at": body.at, "cites": (cite,)}', '            "asked_at": body.at}'),
    ("an answer about a kept screen named by its words", "guardian/api/routes.py",
     '        title=absorb.title_for(said, "", limit=140),\n',
     '        title=absorb.title_for(step_observed, ""),\n'),
    ("a remembered screen read by the fast model", "guardian/api/source_routes.py",
     '        described = picture.describe(raw, "image/jpeg", model=shared_config.CLASS_VISION_MODEL,',
     '        described = picture.describe(raw, "image/jpeg",'),
    ("remember this said aloud", "guardian/ui/teach/teach.js",
     "const REMEMBER = /^\\s*(?:please\\s+)?(?:remember|", "const REMEMBER = /^\\s*(?:please\\s+)?(?:rememberzz|"),
    ("a deleted knowledge leaving no older map", "guardian/api/library_routes.py",
     '            if entry["expert"] == who.name and body_id_for(get_maps().load(entry["map_id"])) == body_id]',
     '            if entry["map_id"] == map_id]'),
    ("a deleted knowledge withdrawn from the library", "guardian/api/library_routes.py",
     "    withdrawn = get_store().withdraw(work_map.organisation, body_id)", "    withdrawn = False"),
    ("a deleted knowledge's archived copies removed", "guardian/api/library_routes.py",
     '                    get_archive().remove(record["archived"])', "                    pass"),
    ("only its own guardian deletes a knowledge", "guardian/api/library_routes.py",
     "    if work_map.expert != who.name:\n        raise HTTPException(status_code=403, detail=f\"This knowledge is",
     "    if False:\n        raise HTTPException(status_code=403, detail=f\"This knowledge is"),
    ("deleting asked twice", "guardian/ui/teach/teach.js",
     '        button.textContent = this.t("deleteSure");\n        window.setTimeout(() => { armed = false; button.textContent = this.t("deleteIt"); }, 4000);\n        return;',
     '        button.textContent = this.t("deleteSure");\n        window.setTimeout(() => { armed = false; button.textContent = this.t("deleteIt"); }, 4000);'),
    ("a request to keep heard anywhere in a sentence", "guardian/ui/teach/teach.js",
     "      if (this.classroom.open && said && REMEMBER_ANYWHERE.test(said)) return await this.rememberScreen(said);\n", ""),
    ("the part named is the part kept", "guardian/api/source_routes.py",
     "                                     focus=body.said.strip())", "                                     focus=\"\")"),
    ("a named part copied, not the screen described", "apu/modality/picture.py",
     "                      FOCUS_PROMPT.format(focus=focus[:600]) if focus.strip() else DESCRIBE_PROMPT],",
     "                      DESCRIBE_PROMPT],"),
    ("a class begun again can ask again", "guardian/api/routes.py",
     '    if body.at < session.get("last_at", -1.0):', '    if False:'),
    ("a question naming no value it was not given", "guardian/engine/questions.py",
     '    "- Name only values written in what you are given. When it names no value, name none: "\n',
     ""),
    ("speech reaching the live relay as bytes", "apu/ui/shared/live.js",
     "this.socket.send(chunk);", "this.socket.send(chunk.buffer);"),
    ("a class recording heard before it is routed", "guardian/ui/teach/teach.js",
     "      if (heard.said) said.text = heard.said;", "      if (false) said.text = heard.said;"),
    ("an answer ending though the same words come again", "guardian/ui/teach/teach.js",
     "      if (text !== heard) { heard = text; spoke = true; last = performance.now(); }",
     "      { heard = text; spoke = true; last = performance.now(); }"),
    ("a question never said over the guardian", "guardian/ui/teach/teach.js",
     "        if (this.listening) {\n          this.classroom.pending = null;", "        if (false) {\n          this.classroom.pending = null;"),
    ("the class vision naming the values", "guardian/engine/vision.py",
     '    "- In \\"changed\\", name each control that changed and its new value exactly as written on "\n', ""),
    ("a learner asking aloud heard without live words", "learner/ui/learn/learn.js",
     "        if (heard.said) said.text = heard.said;", "        if (false) said.text = heard.said;"),
    ("a kept screen named by what to keep", "guardian/api/source_routes.py",
     '    title = absorb.title_for(_named(said), "", limit=140)', '    title = absorb.title_for(said, "", limit=140)'),
    ("a learner's answer worded by its own model", "learner/tutor/answer.py",
     '    model = config.MAIN_MODEL_CHEAPER if step == "near" and config.MAIN_MODEL_CHEAPER else config.ANSWER_MODEL',
     '    model = config.MAIN_MODEL_CHEAPER if step == "near" and config.MAIN_MODEL_CHEAPER else None'),
    ("a kept body read again once republished", "library/reader.py",
     "        key = (id(self._store), self._organisation, body_id, frozenset(allowed), stamp)",
     "        key = (id(self._store), self._organisation, body_id, frozenset(allowed))"),
    ("a withdrawn body never served from what was kept", "library/reader.py",
     "            return None                     # withdrawn, or never published: nothing kept is served",
     "            pass"),
    ("a kept body handed out as a copy", "library/reader.py",
     "                return copy.deepcopy(_KEPT[key])", "                return _KEPT[key]"),
    ("the server warming up the library", "server.py",
     '        getattr(store, "ensure_schema", lambda: None)()\n', ""),
    ("a question waiting kept through a kept screen", "guardian/ui/teach/teach.js",
     "    if (asked && !this.classroom.pending && !reply.question) {", "    if (false) {"),
    ("teaching that mentions keeping not taken for a request", "guardian/ui/teach/teach.js",
     "const REMEMBER_ANYWHERE = /(?:(?<![\\wÀ-ÿ])(?:you|tu|vous)(?![\\wÀ-ÿ])[^.?!]{0,25}?|(?<![\\wÀ-ÿ])(?:want|need|wanna|like)\\s+to\\s+|(?<![\\wÀ-ÿ])please[\\s,]+|^[\\s,]*(?:(?:ok(?:ay)?|so|alors|bon|euh)[\\s,]+)*)(?:remember|keep|",
     "const REMEMBER_ANYWHERE = /(?<![\\wÀ-ÿ])(?:remember|keep|"),
    ("the class never opening the microphone by itself", "guardian/ui/teach/classroom.js",
     "    if (listen) await this.microphone(true);", "    await this.microphone(true);"),
    ("the microphone off until the guardian turns it on", "guardian/ui/teach/teach.js",
     'this.micOn = store.get("urithi.class.mic", false);', 'this.micOn = store.get("urithi.class.mic", true);'),
    ("listening after a question only when the guardian allows it", "guardian/ui/teach/teach.js",
     "    if (!byHand && !this.handsFree) return;", "    if (false) return;"),
    ("no answer aloud with the microphone off", "guardian/ui/teach/teach.js",
     '    if (!this.micOn) { $("class-status").textContent = this.t("micIsOff"); return; }', ""),
    ("the showcase saying what is inside", "apu/ui/showcase/index.html",
     "reads, listens, practises, asks; never writes to the library",
     "reads, listens, practises, asks"),
    ("the server on loopback", "apu/config.py",
     'HOST = os.environ.get("URITHI_HOST", "127.0.0.1")',
     'HOST = os.environ.get("URITHI_HOST", "0.0.0.0")'),
    ("a new decision asked about after the first answer", "guardian/engine/questions.py",
     "    if observation.changed and not any(s.observed == observation.changed for s in work_map.steps):",
     "    if False:"),
    ("typing counted as one edit", "guardian/api/routes.py",
     "            if last is None or body.at - last > questions.SAME_EDIT_SECONDS:",
     "            if True:"),
    ("one question for frames observed at once", "guardian/api/routes.py",
     '    with session["lock"]:', "    if True:"),
    ("the library filtering before it ranks", "library/store.py",
     'if u["status"] == PUBLISHED and u["access"] in allowed\n                    and (body_id is None',
     'if True\n                    and (body_id is None'),
    ("a learner's path holding only what they may see", "library/store.py",
     '        units = [_public(u) for u in found["units"]\n                 if u["status"] == PUBLISHED and u["access"] in allowed]',
     '        units = [_public(u) for u in found["units"]]'),
    ("a case hidden from who may not see it", "library/store.py",
     'if unit["unit_id"] in c["decides"] and c["access"] in allowed]',
     'if unit["unit_id"] in c["decides"]]'),
    ("a case never more open than what it decides", "guardian/publish.py",
     "access=_most_restricted(unit_access[u] for u in decides)))", 'access="public"))'),
    ("restricted words restricted wherever they were said", "guardian/publish.py",
     "            if stricter:", "            if False:"),
    ("a misspelt access level refused", "guardian/publish.py",
     "    if unknown:\n        raise KnowledgeError(f\"No such unit",
     "    if False:\n        raise KnowledgeError(f\"No such unit"),
    ("only a guardian publishes", "library/access.py",
     '    if who.role != "guardian":', "    if False:"),
    ("an answer only for a validated turn", "learner/tutor/answer.py",
     "    require(turn, body_id, question)\n", "    pass\n"),
    ("a wording shown only if every sentence cites", "learner/tutor/answer.py",
     "        if not cited or not cited <= known:", "        if False:"),
    ("a quotation shown only if verbatim", "learner/tutor/answer.py",
     "    return all(_flat(q) in _flat(sources) for q in quoted if len(q.strip()) >= 8)", "    return True"),
    ("nothing invented when nothing is close", "learner/tutor/answer.py",
     "    if not results:\n        # Which way a question went to the guardian",
     "    if False:\n        # Which way a question went to the guardian"),
    ("the guard failing closed", "learner/tutor/guard.py",
     '        raise GuardUnavailable("The guard is unavailable, so nothing is answered.") from error',
     '        raw = "TOPIC"'),
    ("welfare never counted", "learner/tutor/guard.py",
     "        return Verdict(outcome, reply=WELFARE_REPLY[language])",
     "        _counts[session] = _counts.get(session, 0) + 1\n        return Verdict(outcome, reply=WELFARE_REPLY[language])"),
    ("ambiguity never on topic", "learner/tutor/guard.py",
     "    if on and not off:\n        return Outcome.ON_TOPIC", "    if on:\n        return Outcome.ON_TOPIC"),
    ("nothing before what it rests on", "learner/tutor/path.py",
     "if uid not in placed and needs[uid] <= placed", "if uid not in placed"),
    ("a hidden unit not found, not refused", "learner/api/routes.py",
     '        raise HTTPException(status_code=404, detail="No such unit.")',
     '        raise HTTPException(status_code=403, detail="You may not see this unit.")'),
    ("the inbox keeps no person", "exchange/questions.py",
     '        return [{"id": r[0], "question": r[1], "language": r[2], "asked_at": r[3]} for r in rows]',
     '        return [{"id": r[0], "question": r[1], "language": r[2], "asked_at": r[3], "person": "?"} for r in rows]'),
    ("passages that do not answer pass the question on", "learner/tutor/answer.py",
     '    if worded and NO_ANSWER in worded:\n        logger.info("Passed on: the model found no answer',
     '    if False:\n        logger.info("Passed on: the model found no answer'),
    ("collisions only where a rule says to stop", "guardian/engine/probe.py",
     '                  if "stop" in (first.severity, second.severity)\n', "                  if True\n"),
    ("fewer than read as a threshold", "guardian/engine/thresholds.py",
     '"less than", "fewer than",', '"less than",'),
    ("a body taught again keeps its parts' levels", "guardian/api/library_routes.py",
     "    return {**kept, **asked}", "    return dict(asked)"),
    ("a question closed only from its own body", "guardian/api/inbox_routes.py",
     "    closed = [i for i in body.ids[:100] if box.body_of_question(who.organisation, i) == body_id]\n"
     "    for question_id in closed:\n        box.close_question(who.organisation, question_id, \"declined\")",
     "    closed = list(body.ids[:100])\n"
     "    for question_id in closed:\n        get_questions().close_question(question_id, \"declined\")"),
    ("an answer closed against the library's version", "guardian/api/inbox_routes.py",
     "    version = get_store().version_of(who.organisation, body_id)", "    version = 1"),
    ("a ticket per question", "exchange/questions.py",
     "        ticket = secrets.token_urlsafe(16)", '        ticket = body_id'),
    ("a closed question stays closed", "exchange/questions.py",
     "WHERE organisation=? AND id=? AND status='open'\",", "WHERE organisation=? AND id=?\","),
    ("teaching more needs confirming again", "guardian/api/routes.py",
     "    work_map.confirmed_at = None          # captured in class: a draft, until validated\n    get_maps().save(work_map)",
     "    get_maps().save(work_map)"),
    ("a near miss told what is settled", "guardian/engine/probe.py",
     "            probe = _near_miss(rail, work_map.rulings_for(rail.guardrail_id), work_map.language)",
     "            probe = _near_miss(rail, (), work_map.language)"),
    ("a guardian's maps are their own", "guardian/api/library_routes.py",
     '        if entry["expert"] != who.name:\n            continue', '        pass'),
    ("every drawing looked at for writing", "apu/modality/picture.py",
     "        if not has_writing(drawn):", "        if True:"),
    ("a check with no clear answer shows nothing", "apu/modality/picture.py",
     '    raise PictureUnavailable(f"The check gave no clear answer: {said[:40]!r}")', "    return False"),
    ("a package never draws", "learner/packages/package.py",
     '"picture": renderings.picture_kept(u, organisation=organisation)}', '"picture": renderings.picture(u, organisation=organisation)}'),
    ("one drawing per version of a unit", "learner/renderings.py",
     "raw = f\"{unit['unit_id']}|{unit.get('version', 1)}|{unit['text']}|{unit['quote']}|{config.PICTURE_MODEL}\"",
     "raw = f\"{unit['unit_id']}|{unit['text']}|{unit['quote']}|{config.PICTURE_MODEL}\""),
    ("no count the rule turns on", "apu/modality/picture.py",
     "Never show a countable quantity that the know-how turns on", "Show the know-how"),
    ("a withdrawn package leaves the device", "learner/ui/learn/learn.js",
     "        await this.forgetKept(bodyId);\n        removed += 1;", "        removed += 1;"),
    ("an expired package is not opened", "learner/ui/learn/learn.js",
     "      if (this.expired(kept)) {", "      if (false) {"),
    ("an article is not a number", "guardian/engine/thresholds.py",
     '- {"un", "une", "a"}', ""),
    ("a French guardian's rules extracted in French", "guardian/engine/absorb.py",
     'EXTRACT_SYSTEM + (EXTRACT_FRENCH if language == "fr" else "")', "EXTRACT_SYSTEM"),
    ("when a sentence was said, stamped", "guardian/api/routes.py",
     "guardrail_ids=tuple(r.guardrail_id for r in rails), said_at=said_at)",
     "guardrail_ids=tuple(r.guardrail_id for r in rails))"),
    ("the teach-back in the language taught", "guardian/engine/probe.py",
     "    language = work_map.language\n    say = wording.say", '    language = "en"\n    say = wording.say'),
    ("the debrief in the language taught", "guardian/engine/probe.py",
     "            probe = build(rail, work_map.language)", "            probe = build(rail)"),
    ("a rule kept in the language it was taught in", "guardian/publish.py",
     "language = wording.language_of(language or work_map.language)", 'language = wording.language_of(language or "en")'),
    ("the exam shows no answer", "learner/api/routes.py",
     '            "cases": [{"case_id": c["case_id"], "question": for_learner(c["question"], c["by"]), "kind": c["kind"],\n'
     '                       "rests_on": _unlearned_before(found, list(c["decides"]), who)}\n'
     "                      for c in _decided(found)]}",
     '            "cases": _decided(found)}'),
    ("a learner is asked about what the guardian said", "learner/packages/package.py",
     '"cases": [{**c, "question": for_learner(c["question"], c["by"])}', '"cases": [{**c}'),
    ("a near miss is a yes or no question", "guardian/engine/probe.py",
     " or not described or _A_OR_B.search(question)\n", " or not described\n"),
    ("a package changed after signing is refused", "learner/packages/package.py",
     "    if not signing.verify(signed_bytes(manifest_json, content_json), signature, public_key):",
     "    if False:"),
    ("a package's key kept across restarts", "learner/packages/signing.py",
     "    if os.path.exists(path):", "    if False:"),
    ("a file opens at its reader's level, never above", "learner/ui/learn/learn.js",
     '        throw new Error(this.t("tooHigh"));', "        void 0;"),
    ("the extractor told what is already noted", "guardian/engine/absorb.py",
     '{"role": "user", "content": _with_known(said, known)},', '{"role": "user", "content": said},'),
    ("a title cut at a word", "guardian/engine/absorb.py",
     '    return first[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."', '    return first[:limit] + "..."'),
    ("a refused search said as refused", "guardian/engine/sources.py",
     "        if status != 200:", "        if False:"),
    ("a refusing service hands over to the next", "guardian/engine/sources.py",
     "                refused.append(f\"{backend.name}: {error}\")\n                continue",
     "                raise"),
    ("a post on a social network is not a source", "guardian/engine/provenance.py",
     "for s in sources if _an_authority(s.domain)", "for s in sources"),
    ("a case answered again replaces the earlier answer", "guardian/api/routes.py",
     "    work_map.rulings = [r for r in work_map.rulings if r.ruling_id != replaced]\n", ""),
    ("a rule taken out takes its cases with it", "guardian/api/routes.py",
     "                        if r.guardrail_id != gone and r.case.get(\"other\") != gone]",
     "                        if r.guardrail_id != gone]"),
    ("the order kept across hidden parts", "library/store.py",
     '                "links": _bridged(found["links"], visible),',
     '                "links": [link for link in found["links"] if link["source_id"] in visible and link["target_id"] in visible],'),
    ("a case naming closed words is raised", "guardian/publish.py",
     "    _raise_cases_that_name_restricted_words(publication)\n", ""),
    ("only distinctive words raise a case", "guardian/publish.py",
     "if (len(w) >= 2 and w.isupper()) or len(w) >= 7}", "if len(w) >= 3}"),
    ("a choice is not put to a learner as yes or no", "apu/language.py",
     '    return case.get("applies") is not None and not _A_CHOICE.search(case.get("question", ""))',
     '    return case.get("applies") is not None'),
    ("kept audio is compressed", "apu/modality/voice.py",
     'params={"output_format": "mp3_44100_64" if compressed else "pcm_24000"},',
     'params={"output_format": "pcm_24000"},'),
    ("levels remembered after a withdrawal", "guardian/api/library_routes.py",
     "if published else dict(work_map.access))", "if published else {})"),
    ("a kept lesson refreshed once at a time", "learner/ui/learn/learn.js",
     "    if (this.refreshing.has(bodyId)) return;\n", ""),
    ("no Unlocker zone, no Unlocker request", "guardian/engine/sources.py",
     "        self.unlocker_zone = os.environ.get(BRIGHTDATA_UNLOCKER_ZONE_ENV) or None",
     '        self.unlocker_zone = os.environ.get(BRIGHTDATA_UNLOCKER_ZONE_ENV) or "web_unlocker"'),
    ("a failure on the far side tried once more", "guardian/engine/sources.py",
     "            if refused.status < 500:\n                raise", "            raise"),
    ("a cut snippet never contradicts", "guardian/engine/provenance.py",
     "    disagreeing = [c for c in citations if not c.agrees and not c.snippet_only]",
     "    disagreeing = [c for c in citations if not c.agrees]"),
    ("thinking counted as output", "apu/inference/llm.py",
     "output_tokens=max(total - prompt, 0)", "output_tokens=answer"),
    ("quotations paired by their own marks", "learner/tutor/answer.py",
     '_QUOTED = re.compile(r\'"([^"\\n]+)"|“([^”\\n]+)”|«\\s*([^»\\n]+?)\\s*»\')',
     '_QUOTED = re.compile(r\'["“«]([^"”»]{8,})["”»]()()\')'),
    ("stopping this server by its port, never by name", "scripts/serve.sh",
     'for pid in $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null); do',
     'for pid in $(pgrep -f server); do'),
    # The boundary between the two sides (tests/shared/test_boundaries.py).
    ("the learner never importing the guardian's side", "learner/api/routes.py",
     "from exchange.asking import follow_tickets, for_learners\n",
     "from exchange.asking import follow_tickets, for_learners\nfrom guardian import config as _guardian  # noqa: F401\n"),
    ("the library importing no side", "library/store.py",
     "from library import config as library_config\n",
     "from library import config as library_config\nfrom learner import config as _learner  # noqa: F401\n"),
    ("only the guardian writing to the library", "learner/api/routes.py",
     '    return {"bodies": [b for b in get_reader(who.organisation).bodies_for(who.allowed) if b["units"]],',
     '    withdraw = get_reader(who.organisation).withdraw  # noqa: F841\n'
     '    return {"bodies": [b for b in get_reader(who.organisation).bodies_for(who.allowed) if b["units"]],'),
    ("each side under its own address", "learner/api/routes.py",
     'router = APIRouter(prefix="/api/learner")', 'router = APIRouter(prefix="/api/learn")'),
    ("the learner's memory in the learner's directory", "learner/config.py",
     'os.environ.get("LEARNER_PROGRESS_PATH", os.path.join(DATA_DIR, "learners.sqlite3"))',
     'os.environ.get("LEARNER_PROGRESS_PATH", os.path.join(_HERE, "..", "data", "learners.sqlite3"))'),
    ("a cut answer never handed on as whole", "apu/inference/llm.py",
     "    if _cut(response, used, settings.max_output_tokens):", "    if False:"),
    ("a near miss asked with little thinking", "guardian/engine/probe.py",
     "], temperature=0.4, max_tokens=2000, thinking=\"low\"))", "], temperature=0.4, max_tokens=2000))"),
    ("a lead-in is not a step title", "guardian/engine/absorb.py",
     "    while (len(sentences) > 1 and len(sentences[0].split()) < 4", "    while (False"),
    ("a name read back with its capitals", "guardian/engine/probe.py",
     'task=absorb._clause(task) if language == "en" else task)]', 'task=task.lower() if language == "en" else task)]'),
    ("knowledge, never a lesson", "learner/ui/learn/learn.js",
     'openFile: "Open a knowledge file"', 'openFile: "Open a lesson file"'),
    ("a language switch rebuilding the home page", "learner/ui/learn/learn.js",
     '      if (!$("home").hidden) this.showHome();\n', '      if (!$("home").hidden) {}\n'),
    ("a guardian route asking who is there", "guardian/api/routes.py",
     "        who = access.require_guardian(person_id, organisation=organisation)\n", "        who = access.person(\"sabine\")\n"),
    ("a map being its own guardian's", "guardian/api/routes.py",
     "        if work_map is not None and (work_map.expert != who.name or work_map.organisation != who.organisation):",
     "        if False:"),
    ("who teaches being who asks", "guardian/api/routes.py",
     "get_maps().new(body.task, who.name,", "get_maps().new(body.task, body.expert or \"\","),
    ("the learner reading the library through the reader", "learner/api/routes.py",
     "from library.reader import get_reader\n", "from library.reader import get_reader\nfrom library.store import get_store  # noqa: F401\n"),
    ("the learner asking the box, not reading it", "learner/api/routes.py",
     "from exchange.asking import follow_tickets, for_learners\n",
     "from exchange.asking import follow_tickets, for_learners\nfrom exchange.questions import get_questions  # noqa: F401\n"),
    ("the guardian never importing the learner's side", "guardian/api/inbox_routes.py",
     "from exchange.questions import get_questions\n", "from exchange.questions import get_questions\nfrom learner import config as _learner  # noqa: F401\n"),
    ("the reader offering no write", "library/reader.py",
     "    def body_units(self, body_id: str, allowed) -> dict | None:",
     "    def publish(self, publication):\n        return self._store.publish(publication)\n\n    def body_units(self, body_id: str, allowed) -> dict | None:"),
    ("the guardian's data in the guardian's directory", "guardian/config.py",
     'os.path.join(DATA_DIR, "workmap.sqlite3")', 'os.path.join(_HERE, "..", "data", "workmap.sqlite3")'),
    ("the guardian's page saying who is asking", "guardian/ui/teach/teach.js",
     "const post = (path, body) => fetch(withWho(path), {", "const post = (path, body) => fetch(path, {"),
    ("the guardian's page drawing nothing from the learner's", "guardian/ui/teach/index.html",
     '  <link rel="stylesheet" href="/shared/urithi.css">\n', '  <link rel="stylesheet" href="../learn/learn.css">\n'),
    ("the theme chosen before the page paints", "learner/ui/learn/index.html",
     '  <script src="/shared/theme.js"></script>\n', ''),
    ("the tree opening with Enter", "apu/ui/shared/tree.js",
     '      case "Enter": event.preventDefault(); if (node) this.choose(node); break;\n', ''),
    ("only an unlearned prerequisite reminded", "learner/ui/learn/learn.js",
     'detail.prerequisites.filter((p) => states.get(p.unit_id)?.state !== "learned")', 'detail.prerequisites'),
    # Organisations (tests/shared/test_organisations.py, tests/shared/test_library.py).
    ("the library read in one organisation", "library/store.py",
     "        return [b for (org, _), b in self.bodies.items() if org == organisation]",
     "        return [b for (org, _), b in self.bodies.items()]"),
    ("the vector index filtering on the organisation", "library/store.py",
     '        eligible = "u.organisation = $org AND u.status = $published AND u.access IN $allowed" + body_filter',
     '        eligible = "u.status = $published AND u.access IN $allowed" + body_filter'),
    ("no organisation never read as all of them", "library/model.py",
     "    if not organisation or not str(organisation).strip():\n        raise KnowledgeError(",
     "    if False:\n        raise KnowledgeError("),
    ("an organisation one is not in refused", "library/access.py",
     "    raise NotAMember(f\"{theirs[0].name} does not belong to {organisation!r}.\")",
     "    return theirs[0]"),
    ("the question box read in one organisation", "exchange/questions.py",
     '"WHERE organisation=? AND body_id=? AND status=\'open\' ORDER BY id",\n                              (_org(organisation), body_id))',
     '"WHERE body_id=? AND status=\'open\' ORDER BY id",\n                              (body_id,))'),
    ("progress kept per organisation", "learner/memory/progress.py",
     '"SELECT card, reviews, lapses FROM cards WHERE organisation=? AND person_id=? "\n                             "AND unit_id=?", (_org(organisation), person_id, unit_id)',
     '"SELECT card, reviews, lapses FROM cards WHERE person_id=? "\n                             "AND unit_id=?", (person_id, unit_id)'),
    ("a rendering under its organisation", "learner/memory/files.py",
     '        folder = os.path.join(root, _safe(organisation, "organisation"))',
     '        folder = root'),
    ("a map published in its own organisation", "guardian/publish.py",
     "                organisation=work_map.organisation)", "                organisation=\"acme\")"),
    ("a learner reading in the organisation they act in", "learner/api/routes.py",
     "    found = get_reader(who.organisation).body_units(body_id, who.allowed)",
     "    found = get_reader(\"urithi\").body_units(body_id, who.allowed)"),
    # Stores behind interfaces (tests/shared/test_stores.py).
    ("a map never filed without an organisation", "guardian/engine/workmap.py",
     "    if not organisation:\n        raise WorkMapError(", "    if False:\n        raise WorkMapError("),
    ("a session made once and kept", "guardian/memory/store.py",
     "            if map_id not in self._held:", "            if True:"),
    ("no state held in a route module", "learner/api/routes.py",
     'router = APIRouter(prefix="/api/learner")\n', 'router = APIRouter(prefix="/api/learner")\n_answered: dict = {}\n'),
    ("no database opened outside a store", "learner/tutor/answer.py",
     "import re\n", "import re\nimport sqlite3  # noqa: F401\n"),
    # The meter (tests/shared/test_meter.py).
    ("no model call past a ceiling", "apu/inference/llm.py",
     "never_refuse=always)", "never_refuse=True)"),
    ("the cost recorded with the thinking billed", "apu/inference/llm.py",
     "    meter().record(budget, cost(role, used.prompt_tokens, used.output_tokens))",
     "    meter().record(budget, cost(role, used.prompt_tokens, 0))"),
    ("a quota that stops", "apu/meter.py",
     "                if stop is not None and used + estimate > stop:", "                if False:"),
    ("an organisation narrowing, never widening", "apu/meter.py",
     "    return min(platform, organisation)", "    return organisation"),
    ("the guard never refused", "learner/tutor/guard.py",
     "max_tokens=400, always=True)", "max_tokens=400)"),
    ("a question counted against the quota", "learner/api/routes.py",
     '    budget = meter.meter().grant("questions", 1)', '    budget = meter.meter().grant("questions", 0)'),
    ("the answer already given, from the cache", "learner/api/routes.py",
     "    if kept:\n        return {**kept, \"cached\": True, \"warning\"", "    if False:\n        return {**kept, \"cached\": True, \"warning\""),
    ("the guardian's words at a ceiling", "learner/tutor/answer.py",
     '    if step == "stop":', '    if False:'),
    ("heavy work deferred near a ceiling", "learner/api/routes.py",
     '    if meter.meter().level() != "ok":\n        # Heavy work', '    if False:\n        # Heavy work'),
    ("a ceiling met on the way said as a step down", "learner/tutor/answer.py",
     "    except meter.Refused:\n        # The ceiling was met on the way", "    except ZeroDivisionError:\n        # The ceiling was met on the way"),
    ("the guardian's words that answer the question", "learner/tutor/answer.py",
     "    best = max(citations, key=lambda c: (len(asked & _distinctive(f\"{c['text']} {c['quote']}\")), -c[\"n\"]))",
     "    best = citations[0]"),
    ("only a worded answer kept", "learner/api/routes.py",
     '    if result["kind"] == "worded":\n        cache.put(', '    if result["kind"] in ("worded", "extractive"):\n        cache.put('),
    # The teleprompter (tests/shared/test_live.py, tests/shared/test_voice.py).
    ("each word with when it is said", "apu/modality/voice.py",
     '        if char.isspace():\n            if current:', '        if False:\n            if current:'),
    ("a page from elsewhere refused", "apu/modality/live.py",
     '    return origin.split("://", 1)[-1].rstrip("/") == host', '    return True'),
    ("live words metered", "apu/modality/live.py",
     '        meter.meter().grant("transcribed_seconds", 1, principal)\n    except', '        pass\n    except'),
    ("a service that never opens bounded", "apu/modality/live.py",
     "await asyncio.wait_for(opener(send, loop, said), OPEN_WAIT)", "await opener(send, loop, said)"),
    ("a word lit when the voice reaches it", "apu/ui/shared/teleprompter.js",
     'span.classList.toggle("said", words[i].start <= t)', 'span.classList.toggle("said", true)'),
    ("? never acting while typing", "apu/ui/shared/keys.js",
     '      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;\n', ''),
    ("audio kept without its words made again", "learner/renderings.py",
     "        if kept is not None and timed is not None:", "        if kept is not None:"),
    # Step 2: the working memory, the three states, the contents (tests/guardian/test_memory.py).
    ("only the validated version published", "guardian/publish.py",
     "        raise KnowledgeError(\"The guardian has not validated this map; it cannot be published.\")\n    work_map = validated\n",
     "        raise KnowledgeError(\"The guardian has not validated this map; it cannot be published.\")\n"),
    ("validating keeps the version", "guardian/api/routes.py",
     "        work_map.validated = work_map.snapshot()     # what is published from now on, until validated again\n", ""),
    ("a part changed since validation a draft", "guardian/engine/workmap.py",
     '        return {key: "validated" if held.get(key) == value else "draft" for key, value in now.items()}',
     '        return {key: "validated" for key, value in now.items()}'),
    ("the path in the order the guardian set", "guardian/publish.py",
     "    for step in work_map.ordered_steps():\n        unit_id = f\"{body_id}:step-{step.number}\"",
     "    for step in sorted(work_map.steps, key=lambda s: s.number):\n        unit_id = f\"{body_id}:step-{step.number}\""),
    ("a debrief surviving a restart", "guardian/api/routes.py",
     "    if not pending and work_map is not None:", "    if False:"),
    ("a contents that drops no step", "guardian/api/routes.py",
     "    if sorted(body.order) != sorted(known) or len(set(body.order)) != len(body.order):",
     "    if len(set(body.order)) != len(body.order):"),
    ("the working memory ordered by kind", "guardian/memory/working.py",
     '        if block["kind"] == "recent":\n            self._link_after(block, None)',
     '        if True:\n            self._link_after(block, None)'),
    # Step 3: sources (tests/guardian/test_sources.py).
    ("only cited documents archived", "guardian/api/routes.py",
     '        if record["source_id"] not in cited:', '        if False:'),
    ("an excerpt at its part's level", "guardian/publish.py",
     "            excerpt=cite.get(\"text\", \"\")[:600], access=unit.access))",
     "            excerpt=cite.get(\"text\", \"\")[:600], access=\"public\"))"),
    ("evidence read at the person's levels", "library/store.py",
     '                             if e["unit_id"] in visible and e["access"] in allowed]}',
     '                             if True]}'),
    ("an image never a step without the guardian's words", "guardian/api/source_routes.py",
     '    if chosen.get("described"):', '    if False:'),
    ("a PDF cited by its page", "guardian/sources/passages.py",
     '    passages = [{"n": i, "where": f"page {i}", "page": i,', '    passages = [{"n": i, "where": "the document", "page": i,'),
    ("a deposit counted against the quota", "guardian/api/source_routes.py",
     '    budget = meter.meter().grant("deposited_bytes", len(raw))   # refused plainly at the limit',
     '    budget = meter.meter().grant("deposited_bytes", 0)   # refused plainly at the limit'),
    ("a failed archive never undoing a validation", "guardian/api/routes.py",
     "        except Exception as error:\n            # Measured live: the bucket named",
     "        except ZeroDivisionError as error:\n            # Measured live: the bucket named"),
    ("an archive_pending document uploaded and cleared at the next validation", "guardian/api/routes.py",
     '            record["archived"] = get_archive().put(path, data, record["mime"]) or "local"\n'
     '            record.pop("archive_pending", None)',
     '            if not record.get("archive_pending"):\n'
     '                record["archived"] = get_archive().put(path, data, record["mime"]) or "local"'),
    # Step 4: the classroom (tests/guardian/test_memory.py, tests/shared/test_pages.py).
    ("what a class sees kept in the working memory", "guardian/api/routes.py",
     '        memory.put("recent", "saw", {"changed": change.changed, "field": change.field, "at": body.at})',
     '        pass'),
    ("what a class captures a draft", "guardian/api/routes.py",
     "    work_map.confirmed_at = None          # captured in class: a draft, until validated\n", ""),
    # The class keeps watching while a question waits (2026-10-10); one question at a time is the server's.
    ("one class question at a time", "guardian/api/routes.py",
     '    if session["pending"] or not session["detector"].is_pause(at):', '    if not session["detector"].is_pause(at):'),
    # Step 5: the learner's tutor (tests/learner/test_tutor.py).
    ("only an unlearned prerequisite reminded in an answer", "learner/api/routes.py",
     '            if uid in by_id and states[uid]["state"] != "learned"]', '            if uid in by_id]'),
    ("the part in view answering first", "learner/tutor/answer.py",
     '    results.sort(key=lambda r: r["unit"]["unit_id"] != focus)', '    results.sort(key=lambda r: False)'),
    ("where the learner was remembered", "learner/api/routes.py",
     '    _remember(who, body["body"]["body_id"], on=unit_id)', '    pass'),
    ("what was found hard remembered", "learner/api/routes.py",
     "    if body.rating <= 2:", "    if False:"),
    ("reading aloud bounded", "learner/api/routes.py",
     "    if not text or len(text) > 600:", "    if not text:"),
    # P1-P3 fixes: the guardian's expert pupil and camera rules.
    ("forget that undoing only what this class captured", "guardian/api/source_routes.py",
     "            not captured\n            or not work_map.steps\n            or work_map.confirmed_at is not None\n            or work_map.steps[-1].step_id != captured[-1]",
     "            not work_map.steps"),
    ("a compare step keeping the guardian's words verbatim", "guardian/api/source_routes.py",
     "        title = f\"{prefix}: {absorb.title_for(diff or cmd.what or said, '', limit=110)}\"\n        reason = said",
     "        title = f\"{prefix}: {absorb.title_for(diff or cmd.what or said, '', limit=110)}\"\n        reason = f\"{said} ({diff})\""),
    ("an empty face list never skipping camera blurring", "guardian/api/source_routes.py",
     "        faces.extend(vision.last_other_faces(map_id) or vision.detect_other_faces(raw, map_id))",
     "        pass"),
    ("camera numbers requiring guardian confirmation before entering a rule", "guardian/api/routes.py",
     '        rails, unconfirmed = absorb.confirm_camera_rails(\n            rails, said, pending.get("camera_text") or observation.changed, work_map.language\n        )',
     '        unconfirmed = []'),
    ("passing a question preventing the next of the same kind and importance", "guardian/engine/questions.py",
     "        by_kind[kind] = min(6, max(by_kind.get(kind, level), importance + 1))",
     "        by_kind[kind] = min(5, max(by_kind.get(kind, level), importance))"),
    # Decision 0015: the APU memory (MMU: L1, L2 DLL, L3 LanceDB, BMJ, page-in).
    ("L1 cache dropping expired entries on read", "apu/mmu/cache_l1.py",
     "        if now < expiry:", "        if True:"),
    ("L2 inserting fundamental blocks before the tail", "apu/mmu/dll.py",
     '    elif block_type == "fundamental":', "    elif False:"),
    ("L2 paging out the least recently accessed dynamic block at the cap", "apu/mmu/dll.py",
     "    if dynamic_count >= dynamic_max:", "    if False:"),
    ("a paged-out L3 block paged back into the active DLL on search", "apu/mmu/dll.py",
     '            if b_id not in dll["nodes"] and res.get("source_table") == "user_memory":',
     "            if False:"),
    ("BMJ promoting the first relevant DLL block to HEAD", "apu/mmu/dll.py",
     '            if not promoted and b_id in dll["nodes"]:',
     "            if False:"),
    ("L3 refusing a mismatched embedding space", "apu/mmu/lance_driver.py",
     "    if table_dim is not None and table_dim != expected_dim:", "    if False:"),
    ("the guardian's learned pupil threshold kept in their MMU across knowledges", "guardian/engine/questions.py",
     "        mmu_level, mmu_by_kind, _ = get_guardian_mmu().load_threshold(organisation, guardian_id)",
     "        mmu_level, mmu_by_kind = DEFAULT_THRESHOLD, {}"),
    ("the MMU isolating organisations and people", "apu/mmu/store.py",
     "        return Path(self.base_dir) / org / pid",
     "        return Path(self.base_dir) / pid"),
    ("L1 cache keys scoped by organisation and person on direct DLL updates", "apu/mmu/dll.py",
     '        if org or pid:\n            return f"{org}:{pid}:{block_id}"',
     '        if False:\n            return f"{org}:{pid}:{block_id}"'),
    ("the expert pupil asking nothing when the model judges kind is none", "guardian/engine/questions.py",
     '                if kind_raw == "none":',
     '                if False:'),
    ("an expert pupil question refusing invented values not seen or said", "guardian/engine/questions.py",
     "                    if not _question_grounded(question, context_text, work_map.language):",
     "                    if False:"),
    ("pointing at a region of the classroom screen showing #class-point", "guardian/ui/teach/classroom.js",
     "    box.hidden = false;\n    if (box.style) {",
     "    box.hidden = true;\n    if (box.style) {"),
    ("a classroom command noting each step and rule once", "guardian/ui/teach/classroom.js",
     '    if (reply.intent && reply.intent !== "none") {\n      this.point(null);\n    }\n    return reply;',
     '    if (reply.intent && reply.intent !== "none") {\n      this.point(null);\n      if (reply.step) this.onCaptured(reply);\n    }\n    return reply;'),
    ("compare using the frame before the last change instead of the current screen", "guardian/engine/vision.py",
     "    chosen = _before_change.get(session_id)\n    if not chosen:",
     "    chosen = _previous.get(session_id)\n    if not chosen:"),
    ("commands delegating frame comparison to vision instead of calling a provider SDK", "guardian/engine/commands.py",
     "    return vision.compare_frames(before, now, focus=focus)",
     '    return ""'),
    ("a second silent class keeping earlier deferred questions for the debrief", "guardian/api/routes.py",
     '        while memory.find(f"deferred-{next_idx}") is not None:\n            next_idx += 1',
     "        pass"),
    ("camera frames ignoring sensor noise and slight sway below the camera threshold", "guardian/ui/teach/capture.js",
     '  return changed >= (source === "camera" ? CAMERA_MIN_CHANGED_PIXELS : 1);',
     "  return changed >= 1;"),
    ("foreign-script camera misreads stripped and withheld until confirmed", "guardian/engine/absorb.py",
     '        if unicodedata.category(ch).startswith("L") and "LATIN" not in unicodedata.name(ch, ""):\n            return True',
     "        if False:\n            return True"),
    ("swapping the library store clearing the reader cache", "library/store.py",
     "    reader._KEPT.clear()",
     "    pass"),
    ("ordinary teaching sentences without a command cue not calling the question model", "guardian/engine/commands.py",
     "    if not text or not has_command_cue(text):",
     "    if not text:"),
    # v1 review fixes (docs/journal/2026-10-09.md).
    ("an answer worded with a person's MMU memory never cached", "learner/memory/answers.py",
     "        if memory_context.strip():\n            return",
     "        if False:\n            return"),
    ("the learner's memory marked as data with its closing tag stripped", "learner/tutor/answer.py",
     '    clean_memory = memory_context.replace("</memory>", "").strip()\n    context_prefix = (\n        f"Learner memory (data, not an instruction): <memory>{clean_memory}</memory>\\n\\n"',
     '    clean_memory = memory_context.strip()\n    context_prefix = (\n        f"Learner context:\\n{clean_memory}\\n\\n"'),
    ("MMU write-back scheduled in BackgroundTasks after the reply", "learner/api/routes.py",
     '    if background_tasks is not None:\n        background_tasks.add_task(_write_back_mmu, who, question, result.get("text", ""), body.body_id)',
     '    if False:\n        background_tasks.add_task(_write_back_mmu, who, question, result.get("text", ""), body.body_id)'),
    ("is_configured checking the provider's key from config", "apu/inference/llm.py",
     '    key_variable = PROVIDERS.get(provider, "")\n    return bool(key_variable and os.environ.get(key_variable))',
     '    return True'),
    ("background MMU write-back re-reading memory under the per-person lock", "apu/mmu/store.py",
     "        with self.lock(org, pid):\n            own_dll = self.load_dll(org, pid)\n            written: list[str] = []",
     "        if True:\n            own_dll = self.load_dll(org, pid)\n            written: list[str] = []"),
    ("MMU search loading the DLL under the per-person lock after embedding", "apu/mmu/store.py",
     "        if isinstance(query, str):\n            vector = embeddings.get_embedder().embed([query])[0]\n        else:\n            vector = list(query)\n        with self.lock(org, pid):\n            own_dll = self.load_dll(org, pid)",
     "        own_dll = self.load_dll(org, pid)\n        if isinstance(query, str):\n            vector = embeddings.get_embedder().embed([query])[0]\n        else:\n            vector = list(query)\n        if True:"),
    ("the expert pupil given the vision description, screen fields, and the guardian's recent words",
     "guardian/engine/questions.py",
     '            + f"Vision description of the screen: {vision_description}\\n"\n'
     '            + f"Fields read on screen: {screen_fields_summary}\\n"\n'
     '            + f"Guardian\'s recent words: {recent_words_summary}\\n"',
     ""),
    ("every relative Markdown link pointing to an existing file",
     "docs/architecture.md",
     "- [architecture-memory.md](architecture-memory.md): the memories and the APU memory hierarchy.",
     "- [architecture-memory.md](missing-memory.md): the memories and the APU memory hierarchy."),
    ("a question addressed to Urithi classified as ask_pupil and answered without becoming a step",
     "guardian/engine/commands.py",
     '    if _ASK_PUPIL_RE.search(text) or _ASK_PUPIL_RE.search(cleaned):\n        return Command(intent="ask_pupil", what=text)',
     '    if False:\n        return Command(intent="ask_pupil", what=text)'),
    ("a whole class without a save leaving the knowledge empty",
     "guardian/api/routes.py",
     '    proposal, note = _store_step_proposal(work_map, memory, step, rails, origin="tell")',
     '    work_map.steps.append(step)\n    get_maps().save(work_map)\n    proposal, note = _store_step_proposal(work_map, memory, step, rails, origin="tell")'),
    ("no route saving to the knowledge without the guardian's request",
     "guardian/api/routes.py",
     '    proposal, note = _store_step_proposal(work_map, memory, step, rails, origin="answer")',
     '    work_map.steps.append(step)\n    get_maps().save(work_map)\n    proposal, note = _store_step_proposal(work_map, memory, step, rails, origin="answer")'),
    ("a saved proposal keeping the guardian's words",
     "guardian/api/routes.py",
     '            reason=proposal["reason"],',
     '            reason=proposal["title"],'),
    ("proposals replacing previous ones instead of piling up and keeping non-teaching notes as notes",
     "guardian/api/routes.py",
     '                if pid_old:\n                    memory.drop(f"proposal-{pid_old}")',
     '                if False:\n                    memory.drop(f"proposal-{pid_old}")'),
    ("proposals judged by one QUESTION_MODEL call with deterministic fallback",
     "guardian/engine/absorb.py",
     '    if use_model and _proposal_model_ready():',
     '    if False:'),
    ("a limit stated by the guardian proposed as a rule and saved as a rule by save this",
     "guardian/api/routes.py",
     '    is_rule_only = proposal.get("kind") == "rule"',
     '    is_rule_only = False'),
    ("notes counting as answered so Urithi never repeats a question already asked and never replies with silence",
     "guardian/engine/questions.py",
     '                    if _gap_already_answered_or_asked(\n                        kind, work_map, observation, asked, said=said\n                    ) or _is_repeated_question(question, active_asked_questions):\n                        return PupilJudgment(kind=None, importance=0, why="", question="")',
     '                    if False:\n                        return PupilJudgment(kind=None, importance=0, why="", question="")'),
    ("save this saving one proposal or asking which when multiple are open",
     "guardian/api/routes.py",
     "        elif len(open_proposals) > 1:\n            msg = _ask_which_proposal(work_map.language, open_proposals)",
     "        elif False:\n            msg = _ask_which_proposal(work_map.language, open_proposals)"),
    ("questions to Urithi recalling uncited rules and giving distinct grounded answers",
     "guardian/engine/commands.py",
     "    if ans.strip().lower() not in used:\n        return ans",
     "    if True:\n        return ans"),
    ("confirm refusing validation until a teach-back was produced since the last change",
     "guardian/api/routes.py",
     "        if not _has_current_teach_back(work_map):",
     "        if False:"),
    # The four fixes of 2026-10-10, 18:10 (speed, a whole rule, spoken answers, the transcript).
    ("an answer to the guardian kept to one short sentence", "guardian/engine/commands.py",
     '                candidate = _spoken_length(sentences[0]) if sentences else ""',
     '                candidate = " ".join(sentences[:2])'),
    ('a note named in a few words, never read back whole', 'guardian/engine/commands.py',
     '            note = _short(note_texts[0], 8).rstrip(".")',
     '            note = note_texts[0].rstrip(".")'),
    ("a rule keeping what the guardian forbids", "guardian/engine/absorb.py",
     "    if not (_keep_words(source) - _keep_words(read)):",
     "    if True:"),
    ("the question which proposal to save written in the conversation", "guardian/ui/teach/teach.js",
     '        this.line("apprentice", msg);\n        this.say(msg);',
     '        this.say(msg);'),
    ("forget that last step dropping the proposal just made", "guardian/api/source_routes.py",
     '        explicit_saved = bool(re.search(r"\\b(?:saved|sauvegard\\w*|enregistr\\w*)\\b", said, re.IGNORECASE))',
     '        explicit_saved = bool(re.search(r"\\b(?:saved|step|sauvegard\\w*|enregistr\\w*)\\b", said, re.IGNORECASE))'),
    ("a reply that is only noted written in the conversation", "guardian/ui/teach/teach.js",
     '        if (spoken) {\n          this.line("apprentice", spoken);',
     '        if (false) {\n          this.line("apprentice", spoken);'),
    ("a spoken answer kept to about twenty-five words", "guardian/engine/commands.py",
     "    if len(cut) <= words:\n        return sentence",
     "    if True:\n        return sentence"),
    # Found shooting the keynote footage (2026-10-10): the class kept honest while a question waits.
    ("an answer titled from what the guardian did since the question", "guardian/api/routes.py",
     '    if seen_since and pending.get("source", "screen") == "screen":',
     '    if False:'),
    ("a proposal said back as a proposal, never as a step", "guardian/api/routes.py",
     '    if not title:\n        return "Noté. Continue." if language == "fr" else "Noted. Carry on."',
     '    if True:\n        return "Noté. Continue." if language == "fr" else "Noted. Carry on."'),
    ("the waiting question kept in view with Pass", "guardian/ui/teach/teach.js",
     '    if ($("class-pass")) $("class-pass").hidden = !waiting;',
     '    if ($("class-pass")) $("class-pass").hidden = true;'),
    ("the class watching while a question waits", "guardian/ui/teach/classroom.js",
     '    if (this.paused || !this.capture) return;\n    if (frame) this.onLooked',
     '    if (this.pending || this.paused || !this.capture) return;\n    if (frame) this.onLooked'),
    # The second pass on the keynote shoot (2026-10-10): what is stated is proposed, and said so.
    ("every rule stated proposed", "guardian/api/routes.py",
     "            if gid not in open_rule_ids:\n                made = absorb._build_rule_proposal",
     "            if False:\n                made = absorb._build_rule_proposal"),
    ("an ignored proposal never offered again", "guardian/api/routes.py",
     '            if pid_new in ignored or str(prop.get("guardrail_id") or "") in ignored:\n                continue',
     '            if False:\n                continue'),
    ("a rule proposed in conversation said as proposed", "guardian/api/routes.py",
     "    noted_msg = _noted(work_map.language, proposal)",
     "    noted_msg = _noted(work_map.language, None)"),
    ("only a question labelled asked on the class board", "guardian/ui/teach/teach.js",
     '(/\\?\\s*$/.test(text) ? "asked" : "urithi")',
     '"asked"'),
    ("what would be saved named, not read whole", "guardian/engine/commands.py",
     '                named.append(_short(f"{\'l’étape\' if french else \'the step\'} {p[\'title\']}", 12))',
     '                named.append(f"{p[\'title\']}: {p.get(\'reason\', \'\')}")'),
    # The review of 2026-10-14 (tests/guardian/test_saving_and_forgetting.py).
    ("a step saved without a rule holding none", "guardian/api/routes.py",
     '        step_gids = [r["guardrail_id"] for r in raw_rules]\n',
     '        step_gids = [r["guardrail_id"] for r in raw_rules] or [g.guardrail_id for g in work_map.guardrails]\n'),
    ("a forgotten step keeping a rule another step holds", "guardian/api/source_routes.py",
     "        gone_rails = said_with - still_held",
     "        gone_rails = said_with"),
    ("a forgotten proposal and its rules set aside", "guardian/api/source_routes.py",
     "                routes._set_aside(work_map, memory, pid, p_content)",
     "                pass"),
    ("a rule changed before saving saved in its new words", "guardian/api/routes.py",
     "        first.update(when=found[0].when, then=found[0].then, severity=found[0].severity)",
     "        pass"),
    ("a changed proposal kept when the notes are judged again", "guardian/api/routes.py",
     '            elif p.get("origin") in ("tell", "answer", "note") and not p.get("edited"):',
     '            elif p.get("origin") in ("tell", "answer", "note"):'),
    ("a working memory written meanwhile not overwritten", "guardian/memory/working.py",
     "            if stored is not None and version != memory.base_version:",
     "            if False:"),
    ("what is only judged again dropped on a conflict", "guardian/memory/working.py",
     "            if op[-1] and not derived:\n                continue",
     "            if False:\n                continue"),
    ("a command saving only on the guardian's words", "guardian/api/source_routes.py",
     '        if not commands.has_save_cue(said):\n            return {"intent": "none"}',
     '        if False:\n            return {"intent": "none"}'),
    ("save this naming nothing the model read into it", "guardian/engine/commands.py",
     '            return Command(intent="save", what=_extract_save_what(m_save))',
     '            return Command(intent="save", what=_extract_save_what(m_save) or what)'),
    ("a judge answering none proposing no step", "guardian/engine/absorb.py",
     "                if chosen_id.lower() in _NO_CHOICE:",
     "                if False:"),
    ("a follow-up in class the one question waiting", "guardian/api/routes.py",
     '        if "last_at" in session:',
     "        if False:"),
    ("a follow-up shown with Pass on the class page", "guardian/ui/teach/teach.js",
     "          this.classroom.onQuestion(reply);\n          await this.refreshMap();\n          return reply;",
     "          await this.refreshMap();\n          return reply;"),
    ("a rule saved without a severity saved as a check", "guardian/api/routes.py",
     '            severity=r.get("severity") or "check",',
     '            severity=r.get("severity", "warning"),'),
    ("a forgotten saved step's note set aside", "guardian/api/source_routes.py",
     '                memory.drop(n_block["ref"])\n                memory.drop(f"proposal-{nid}")\n'
     '                routes._set_aside(work_map, memory, nid, n_content)',
     '                pass'),
    ('derived changes kept when what they were judged from is unchanged', 'guardian/memory/working.py',
     'newer.replay(memory.journal, derived=_judged_from(stored) == memory.base_judged_from)',
     'newer.replay(memory.journal, derived=False)'),
    ('a deleted working memory not written again', 'guardian/memory/working.py',
     '            if stored is None and memory.base_version > 0:',
     '            if False:'),
    ('a polite request to save read as a save', 'guardian/engine/commands.py',
     '    r"(?:(?:can|could|would|will)\\s+you\\s+(?:please\\s+)?|"\n    r"(?:peux-tu|pourrais-tu|tu\\s+peux|est-ce\\s+que\\s+tu\\s+peux)\\s+)?"',
     '    r"(?:zz)?"'),
    ("the guardian's save words winning over the model", 'guardian/engine/commands.py',
     "        if m_save:   # the guardian's explicit words decide, whatever the model read",
     '        if m_save and intent in ("none", "remember", "save"):'),
    ('sauvegarder naming what follows it', 'guardian/engine/commands.py',
     'sauvegard(?:er|ez|es|e)|enregistr(?:er|ez|es|e))\\b"',
     'sauvegard(?:e|es|er|ez)|enregistr(?:e|es|er|ez))"'),
    ('a rule saved alone kept when the step before it is forgotten', 'guardian/api/source_routes.py',
     'if g.guardrail_id in (removed.guardrail_ids or ()) and removed.said_at and g.said_at == removed.said_at}',
     'if g.guardrail_id in (removed.guardrail_ids or ())}'),
    ('a set-aside note never saved by save this', 'guardian/api/routes.py',
     '                        and str(b["content"].get("note_id") or b["ref"].removeprefix("note-")) not in aside]',
     '                        ]'),
    ("a forgotten step's note found by its id", 'guardian/api/source_routes.py',
     'if n_id == saved_from or str(',
     'if str('),
    ('every rule in corrected words kept', 'guardian/api/routes.py',
     '            for g in found[1:]] if found else rules[1:]',
     '            for g in found[:0]] if found else rules[1:]'),
    ('a polite save sent as a save by the class page', 'guardian/ui/teach/teach.js',
     '(?:(?:can|could|would|will)\\s+you\\s+(?:please\\s+)?|(?:peux-tu|pourrais-tu|tu\\s+peux|est-ce\\s+que\\s+tu\\s+peux)\\s+)?(?:save|keep|garde',
     '(?:save|keep|garde'),
    ('save this never falling back to an older note', 'guardian/api/routes.py',
     '            if str(n0.get("note_id") or latest["ref"].removeprefix("note-")) in aside:',
     '            if False:'),
    ('a map saved from an older copy refused', 'guardian/engine/workmap.py',
     '            if row is not None and int(row[0]) != work_map.version:',
     '            if False:'),
    ('one writer of a map at a time', 'guardian/api/routes.py',
     '        with map_lock(str(getattr(body, "map_id", "") or "")):',
     '        with threading.Lock():'),
    ('a map changed elsewhere said, not overwritten', 'guardian/api/routes.py',
     '            except MapChanged as error:',
     '            except ZeroDivisionError as error:'),
    ('an import replacing a map whole', 'guardian/engine/workmap.py',
     '        work_map.version = current.version if current is not None else 0',
     '        work_map.version = 0'),
    ('a labelled step said once in the teach-back', 'guardian/engine/probe.py',
     '        if step.reason.strip().lower().startswith(title.lower()) or _said_in(step.title, step.reason):',
     '        if step.reason.strip().lower().startswith(title.lower()):'),
    ('a fluent model answer kept whatever its words', 'guardian/engine/commands.py',
     '                if candidate:\n                    return _ensure_distinct_answer(candidate, said, lang, previous_qa)',
     '                if candidate and "rule" in candidate:\n                    return _ensure_distinct_answer(candidate, said, lang, previous_qa)'),
    ('with no model, no rule noted said plainly', 'guardian/engine/commands.py',
     '        parts.append("aucune règle n\'est encore notée" if french else "no rule is noted yet")',
     '        pass'),
    ('the migration taking off only rules given by mistake', 'scripts/migrate_step_rules.py',
     '    return [gid for gid in ids[:run] if gid in held_before and said.get(gid) != step.said_at]',
     '    return [gid for gid in ids[:run] if said.get(gid) != step.said_at]'),
    ('a question found unanswered once read again before the guardian is asked', 'learner/tutor/answer.py',
     '            worded = _worded(question, citations, language, model=model)',
     '            worded = NO_ANSWER'),
    ("a learner's answer worded at temperature 0", 'learner/tutor/answer.py',
     'max_tokens=2000, temperature=0.0,',
     'max_tokens=2000,'),
    ("the learner's memory never deciding whether the passages answer", 'learner/tutor/answer.py',
     "The learner's memory, when given, is context about them only: it never decides whether the passages",
     "The learner's memory, when given, is context about them only: it may decide whether the passages"),
    ("a memory block the learner removes is gone from L3 too", 'apu/mmu/store.py',
     '            _run_sync(lance_driver.get_l3_store().delete_local_block(block_id, db_path=self.db_path(org, pid)))\n',
     ''),
    ("a memory block the learner removes is emptied", 'apu/mmu/store.py',
     '            node["content"] = ""\n            node.pop("knowledge_id", None)\n',
     '            node.pop("knowledge_id", None)\n'),
    ("the learner told which memory reaches answers here", 'apu/mmu/store.py',
     '                            "in_context": mmu_dll.in_scenario(node, knowledge_id)})',
     '                            "in_context": True})'),
    ("the learner's memory shown when a knowledge opens", 'learner/ui/learn/learn.js',
     '    this.loadNotebook();\n    this.loadRemembered();\n',
     '    this.loadNotebook();\n'),
    ("each memory remove button says what it removes", 'learner/ui/learn/learn.js',
     '      forget.setAttribute("aria-label", this.t("forgetMemory", block.content.slice(0, 80)));\n',
     ''),
    ("another knowledge's memory left out of the context", 'apu/mmu/dll.py',
     '    if knowledge_id is None or node.get("type") not in SCENARIO_BLOCK_TYPES:\n        return True',
     '    if True:\n        return True'),
    ("a memory block of unknown knowledge not read for a knowledge", 'apu/mmu/dll.py',
     '    return node.get("knowledge_id") == knowledge_id',
     '    return node.get("knowledge_id") in (knowledge_id, None)'),
    ("a block about the person belongs to no knowledge", 'apu/mmu/dll.py',
     '    else:\n        node.pop("knowledge_id", None)\n',
     '    else:\n        node["knowledge_id"] = knowledge_id or (dll.get("knowledge_selection") or {}).get("knowledge_id")\n'),
    ("the tutor reads the memory of the knowledge asked on", 'learner/memory/mmu.py',
     'context = self.read_context(organisation, person_id, knowledge_id=body_id)',
     'context = self.read_context(organisation, person_id)'),
    ("a write back tagged with the knowledge it was asked on", 'apu/mmu/store.py',
     '                            knowledge_id=knowledge_id,\n                            source=source,\n                        )\n                    )\n                    written.append(block_id)',
     '                            source=source,\n                        )\n                    )\n                    written.append(block_id)'),
    ("the background write back told its knowledge", 'learner/api/routes.py',
     '        background_tasks.add_task(_write_back_mmu, who, question, result.get("text", ""), body.body_id)',
     '        background_tasks.add_task(_write_back_mmu, who, question, result.get("text", ""))'),
    ("a memory block keeps what it was written from", 'apu/mmu/store.py',
     '        source = {"by": "extraction" if updates else "fallback", "said": user_text.strip()[:240]}',
     '        source = {"by": "extraction" if updates else "fallback"}'),
    ("the question's words fused with the meaning", 'library/store.py',
     '        ranked = [found[uid] for uid in keywords.fuse(by_meaning, by_words)]',
     '        ranked = [found[uid] for uid in keywords.fuse(by_meaning, [])]'),
    ("keywords compared only within one language", 'library/keywords.py',
     '    return bool(asked) and bool(taught) and asked.split("-")[0].lower() == taught.split("-")[0].lower()',
     '    return True'),
    ("keywords ranked only among what may be read", 'library/store.py',
     '        same = [(u, b) for u, b in eligible if body_id and keywords.same_language(lang, b["body"].get("language"))]',
     '        same = [(u, b) for b in self._of(organisation) for u in b["units"] if body_id and keywords.same_language(lang, b["body"].get("language"))]'),
    ("the words of one knowledge read under the same filter as the vectors", 'library/store.py',
     '"CALL () { MATCH (u:Unit)-[:BELONGS_TO]->(b:Body) WHERE " + eligible +',
     '"CALL () { MATCH (u:Unit)-[:BELONGS_TO]->(b:Body) WHERE u.organisation = $org" +'),
    ("words ranked only within one knowledge", 'library/store.py',
     '        same = [(u, b) for u, b in eligible if body_id and keywords.same_language(lang, b["body"].get("language"))]',
     '        same = [(u, b) for u, b in eligible if keywords.same_language(lang, b["body"].get("language"))]'),
    ("the learner's language passed to the search", 'learner/tutor/answer.py',
     '    found = store.search(question, allowed, k=4, body_id=body_id, lang=language)',
     '    found = store.search(question, allowed, k=4, body_id=body_id)'),
    ("no word left out of the keyword ranking", 'library/keywords.py',
     '    return _WORD.findall((text or "").lower())',
     '    return [w for w in _WORD.findall((text or "").lower()) if len(w) > 2]'),
    ("one sentence falling back twice is one rule", 'guardian/engine/absorb.py',
     '        if any(r.then.lower() == then.lower() for r in rails):\n            continue\n',
     ''),
    ("a note saved as a case marked as saved", 'guardian/api/routes.py',
     '            memory.put("retained", f"saved-case-{ruling.ruling_id}", {"note_id": proposal["proposal_id"]})\n',
     ''),
    ("a note saved in any form left out when proposals are judged again", 'guardian/api/routes.py',
     '    notes = [n for n in notes if str(n.get("note_id") or "") not in saved_from]\n',
     ''),
    ("a proposal judged before a note was saved not replayed", 'guardian/memory/working.py',
     'JUDGED_FROM = ("note-", "proposal-", "ignored-", "rule-", "saved-")',
     'JUDGED_FROM = ("note-", "proposal-", "ignored-", "rule-")'),
    ("a question found unanswered read again without the learner's memory", 'learner/tutor/answer.py',
     '            worded = _worded(question, citations, language, model=model)\n',
     '            worded = _worded(question, citations, language, model=model, memory_context=memory_context)\n'),
    ("an answer that is only a quotation given as the guardian's words", 'learner/tutor/answer.py',
     'if worded and check(worded, citations) and own_words(worded):',
     'if worded and check(worded, citations):'),
    ("a quotation alone not counted as words of the answer's own", 'learner/tutor/answer.py',
     '    rest = _CITATION.sub(" ", _QUOTED.sub(" ", text))',
     '    rest = _CITATION.sub(" ", text)'),
    ("the learner's answer written in their language whatever the passages' language", 'learner/tutor/answer.py',
     "Write your own sentences in {language} even when the passages are in another\nlanguage.",
     "Write your own sentences in {language}."),
    ("the pupil's facts deciding what it says", 'guardian/engine/commands.py',
     '    "- The facts decide what you say: name a rule when \'Rules already noted or saved\' lists one, and say "',
     '    "- Name a rule when \'Rules already noted or saved\' lists one, and say "'),
    ('an answer told apart keeping its capital I', 'guardian/engine/commands.py',
     '    rest = ans if re.match(r"I\\b", ans) else (ans[0].lower() + ans[1:] if len(ans) > 1 else ans)',
     '    rest = ans[0].lower() + ans[1:] if len(ans) > 1 else ans'),
    ('nothing known said plainly, not seen that yet', 'guardian/engine/commands.py',
     '    if not (seen_parts or last_q or steps_parts or rules_parts or proposal_parts):',
     '    if False:'),
    ('a rule removed from the map set aside', 'guardian/api/routes.py',
     '    _set_aside(work_map, memory, f"rule-{gone[:10]}", {"guardrail_id": gone})',
     '    pass'),
    ('a deposited recording heard when the first key is refused', 'apu/modality/voice.py',
     '        logger.warning("Timed transcription failed (%s); falling back to Gemini, untimed.", error)\n        return _heard_whole(audio, mime_type, budget)',
     '        logger.warning("Timed transcription failed (%s); falling back to Gemini, untimed.", error)\n        raise VoiceUnavailable(f"Transcription failed: {error}") from error'),
    ('an untimed recording cited as its whole length', 'apu/modality/voice.py',
     '    return text, [{"word": text, "start": 0.0, "end": length}]',
     '    return text, [{"word": text, "start": 0.0, "end": 0.0}]'),
    ('the teach page declaring its icon', 'guardian/ui/teach/index.html',
     '  <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2064%2064%22%3E%3Crect%20width%3D%2264%22%20height%3D%2264%22%20rx%3D%2214%22%20fill%3D%22%2314111c%22%2F%3E%3Cpath%20d%3D%22M16%2046V22l16-8%2016%208v24%22%20fill%3D%22none%22%20stroke%3D%22%23e6b85c%22%20stroke-width%3D%224%22%2F%3E%3Cpath%20d%3D%22M24%2046V30h16v16%22%20fill%3D%22none%22%20stroke%3D%22%23e6b85c%22%20stroke-width%3D%224%22%2F%3E%3C%2Fsvg%3E">\n',
     ''),
]

SUITE_TIMEOUT = 600
PYTEST_ARGS = ["-q", "--no-header", "-x", "-p", "no:cacheprovider"]
DEFAULT_WORKERS = min(8, os.cpu_count() or 4)
COPY_IGNORE = shutil.ignore_patterns(
    ".venv",
    "data",
    "logs",
    "models",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
    ".env",
    ".mutating",
    "*.sqlite3",
    "*.pyc",
    "*.whl",
)


def _candidate_tests(relative: str) -> list[str]:
    """Fastest test files likely to catch a defect in `relative` before falling back to all `tests`."""
    if relative.endswith(".md"):
        return ["tests/shared/test_architecture.py"]
    if relative.endswith((".js", ".html")):
        return [
            "tests/shared/test_pages.py",
            "tests/shared/test_presentation.py",
            "tests/shared/test_architecture.py",
        ]
    if relative.startswith("apu/mmu/"):
        return ["tests/shared/test_mmu.py"]
    if relative == "apu/inference/llm.py":
        return ["tests/shared/test_llm.py", "tests/shared/test_architecture.py"]
    if relative == "apu/meter.py":
        return ["tests/shared/test_meter.py"]
    if relative == "apu/modality/voice.py":
        return ["tests/shared/test_voice.py"]
    if relative == "apu/modality/live.py":
        return ["tests/shared/test_live.py"]
    if relative == "apu/modality/picture.py":
        return ["tests/learner/test_picture.py", "tests/guardian/test_sources.py"]
    if "braille" in relative:
        return ["tests/shared/test_braille.py", "tests/guardian/test_engine.py"]
    if relative in ("apu/config.py", "scripts/serve.sh", "server.py"):
        return ["tests/shared/test_architecture.py", "tests/shared/test_organisations.py"]
    if relative == "apu/language.py":
        return ["tests/guardian/test_engine.py", "tests/guardian/test_french.py"]
    if relative == "library/reader.py":
        return ["tests/shared/test_reader.py", "tests/learner/test_tutor.py"]
    if relative.startswith("library/"):
        return [
            "tests/shared/test_library.py",
            "tests/shared/test_organisations.py",
            "tests/shared/test_stores.py",
            "tests/guardian/test_publishing.py",
        ]
    if relative.startswith("exchange/"):
        return [
            "tests/learner/test_learning.py",
            "tests/shared/test_organisations.py",
            "tests/guardian/test_publishing.py",
        ]
    if relative.startswith("learner/packages/"):
        return ["tests/learner/test_package.py"]
    if relative == "learner/renderings.py":
        return ["tests/learner/test_picture.py", "tests/learner/test_learning.py"]
    if relative.startswith("learner/"):
        return [
            "tests/learner/test_tutor.py",
            "tests/learner/test_learning.py",
            "tests/shared/test_mmu.py",
            "tests/shared/test_organisations.py",
            "tests/shared/test_stores.py",
        ]
    if relative == "guardian/engine/commands.py":
        return ["tests/guardian/test_commands.py"]
    if relative == "guardian/engine/vision.py":
        return [
            "tests/guardian/test_vision.py",
            "tests/guardian/test_camera.py",
            "tests/guardian/test_commands.py",
        ]
    if relative == "guardian/engine/questions.py":
        return [
            "tests/guardian/test_pupil.py",
            "tests/guardian/test_engine.py",
            "tests/guardian/test_french.py",
        ]
    if relative == "guardian/engine/absorb.py":
        return [
            "tests/guardian/test_pupil.py",
            "tests/guardian/test_camera.py",
            "tests/guardian/test_engine.py",
            "tests/guardian/test_french.py",
        ]
    if relative in ("guardian/engine/sources.py", "guardian/api/source_routes.py") or relative.startswith(
        "guardian/sources/"
    ):
        return [
            "tests/guardian/test_sources.py",
            "tests/guardian/test_commands.py",
            "tests/guardian/test_camera.py",
            "tests/guardian/test_memory.py",
        ]
    if relative in ("guardian/api/library_routes.py", "guardian/api/inbox_routes.py", "guardian/publish.py"):
        return [
            "tests/guardian/test_publishing.py",
            "tests/guardian/test_deleting.py",
            "tests/shared/test_organisations.py",
        ]
    if relative.startswith("guardian/memory/"):
        return [
            "tests/guardian/test_memory.py",
            "tests/shared/test_stores.py",
            "tests/shared/test_organisations.py",
        ]
    return [
        "tests/guardian/test_engine.py",
        "tests/guardian/test_pupil.py",
        "tests/guardian/test_camera.py",
        "tests/guardian/test_memory.py",
        "tests/guardian/test_sources.py",
        "tests/guardian/test_publishing.py",
        "tests/guardian/test_french.py",
    ]


class Restorer:
    """Puts the file back, once, whatever ends the process."""

    def __init__(self, path: pathlib.Path, original: str):
        self.path = path
        self.original = original
        self.done = False

    def restore(self, *_):
        if not self.done:
            self.path.write_text(self.original)
            self.done = True

    def __enter__(self):
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, lambda *_: (self.restore(), sys.exit(130)))
        return self

    def __exit__(self, *_):
        self.restore()
        return False


def _run_pytest(
    worker_dir: pathlib.Path, targets: list[str]
) -> tuple[subprocess.CompletedProcess, bool]:
    cmd = [sys.executable, "-m", "pytest", *targets, *PYTEST_ARGS]
    env = {
        **os.environ,
        "PYTHONPATH": str(worker_dir),
        "URITHI_MUTATING": "1",
        "URITHI_EMBEDDING_CACHE_DIR": str(ROOT / "models"),
    }
    try:
        proc = subprocess.run(
            cmd,
            cwd=worker_dir,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT,
            env=env,
        )
        return proc, False
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, stdout="", stderr="timed out"), True


def _prepare_worker(tmp_path: pathlib.Path, idx: int) -> pathlib.Path:
    wdir = tmp_path / f"worker-{idx}"
    shutil.copytree(ROOT, wdir, ignore=COPY_IGNORE)
    return wdir


def _verify_clean_worker(
    worker_dir: pathlib.Path,
) -> tuple[pathlib.Path, subprocess.CompletedProcess, bool]:
    result, timed_out = _run_pytest(worker_dir, ["tests"])
    return worker_dir, result, timed_out


def _check_one(
    mutant: tuple[str, str, str, str],
    worker_pool: "queue.Queue[pathlib.Path]",
    verbose: bool,
) -> tuple[bool, str]:
    label, relative, real, broken = mutant
    source_path = ROOT / relative
    original = source_path.read_text()
    if original.count(real) != 1:
        return False, f"SKIPPED  {label}: the line it breaks is not there, or is there twice"

    worker_dir = worker_pool.get()
    try:
        target_path = worker_dir / relative
        with Restorer(target_path, original):
            target_path.write_text(original.replace(real, broken))
            candidates = _candidate_tests(relative)
            result, timed_out = _run_pytest(worker_dir, candidates)
            if not timed_out and result.returncode == 0:
                result, timed_out = _run_pytest(worker_dir, ["tests"])
    finally:
        worker_pool.put(worker_dir)

    if timed_out:
        return False, f"TIMEOUT  {label}: test suite timed out after {SUITE_TIMEOUT}s"

    noticed = result.returncode != 0
    failing = next(
        (line.split("::")[-1].split()[0] for line in result.stdout.splitlines() if line.startswith("FAILED")),
        "",
    )
    line_out = ("caught  " if noticed else "MISSED  ") + label + (f"  -> {failing}" if failing and verbose else "")
    return noticed, line_out


def run(verbose: bool = False, only: list[str] | None = None, workers: int = DEFAULT_WORKERS) -> int:
    chosen = [m for m in MUTANTS if not only or any(word.lower() in m[0].lower() for word in only)]
    if not chosen:
        print(f"No mutant's label contains: {', '.join(only)}. See --list.")
        return 2
    num_workers = max(1, min(len(chosen), workers))
    with tempfile.TemporaryDirectory(prefix="urithi-mutate-") as tmp_root:
        tmp_path = pathlib.Path(tmp_root)
        worker_dirs = [_prepare_worker(tmp_path, idx) for idx in range(num_workers)]
        worker_pool: queue.Queue[pathlib.Path] = queue.Queue()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
            clean_checks = [pool.submit(_verify_clean_worker, wdir) for wdir in worker_dirs]
            for check in clean_checks:
                wdir, clean_res, clean_timed_out = check.result()
                if clean_timed_out:
                    print(
                        f"ABORTED  clean test suite timed out in worker copy {wdir.name} "
                        f"after {SUITE_TIMEOUT}s before any mutant was run.",
                        flush=True,
                    )
                    return 1
                if clean_res.returncode != 0:
                    summary = next(
                        (line for line in clean_res.stdout.splitlines() if line.startswith("FAILED")),
                        (clean_res.stdout or clean_res.stderr).strip().splitlines()[-1]
                        if (clean_res.stdout or clean_res.stderr).strip()
                        else f"exit code {clean_res.returncode}",
                    )
                    print(
                        f"ABORTED  clean test suite failed in worker copy {wdir.name} "
                        f"before any mutant was run: {summary}",
                        flush=True,
                    )
                    return 1
            for wdir in worker_dirs:
                worker_pool.put(wdir)

            caught = 0
            futures = [pool.submit(_check_one, m, worker_pool, verbose) for m in chosen]
            for fut in futures:
                noticed, line_out = fut.result()
                caught += int(noticed)
                print(line_out, flush=True)

    print(f"\n{caught}/{len(chosen)} mutants caught")
    return 0 if caught == len(chosen) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the mutants, run nothing")
    parser.add_argument("--verbose", action="store_true", help="name the test that caught each")
    parser.add_argument("--only", action="append", metavar="WORDS",
                        help="run only the mutants whose label contains WORDS (repeatable)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="parallel worker copies in a temporary directory")
    args = parser.parse_args()

    if args.list:
        for label, relative, _, _ in MUTANTS:
            print(f"{relative:38} {label}")
        return 0
    return run(verbose=args.verbose, only=args.only, workers=args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
