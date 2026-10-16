"""
Measure the library's search on labelled questions: by meaning alone, and with the question's words.

    uv run python scripts/measure_search.py

Runs the memory store's own search (the same ranking code as Neo4j's, library/keywords.py) with the
real embedding model, on scripts/search_bench.json. The parts of Ezekias's published knowledge are
read from the configured library; a knowledge not found there is skipped and said so. Prints, for
each, how often the right part comes first, in the first four (what an answer reads), and the mean
reciprocal rank. Measured on 2026-10-15: docs/measured-search.md.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from library import store as library_store  # noqa: E402
from library.model import Body, Publication, Unit, levels_up_to  # noqa: E402

ORG = "urithi"


def _knowledges(bench: dict) -> dict:
    memory = library_store.MemoryKnowledgeStore()
    found = {}
    for name, entry in bench["knowledges"].items():
        body_id = entry.get("body_id") or f"bench-{name}"
        parts = entry.get("units")
        if parts is None:
            published = library_store.get_store().body_units(ORG, body_id, levels_up_to("restricted"))
            if not published:
                print(f"{name}: {body_id} is not in the library here, skipped")
                continue
            parts = [{"id": u["unit_id"].split(":", 1)[1], "text": u["text"], "quote": u["quote"]} for u in published["units"]]
        memory.publish(Publication(
            body=Body(body_id=body_id, name=name, guardian="bench", organisation=ORG, version=1, published_at="now",
                      language=entry.get("language", "en")),
            units=[Unit(unit_id=f"{body_id}:{u['id']}", body_id=body_id, kind="limit", text=u["text"], quote=u["quote"],
                        at=1.0, access="public") for u in parts]))
        found[name] = (body_id, entry["questions"])
    return memory, found


def main() -> None:
    bench = json.loads((Path(__file__).parent / "search_bench.json").read_text(encoding="utf-8"))
    memory, found = _knowledges(bench)
    rows = {"meaning alone": [], "with the question's words": []}
    for name, (body_id, questions) in found.items():
        for lang, question, good in questions:
            for label, asked in (("meaning alone", None), ("with the question's words", lang)):
                ranked = [r["unit"]["unit_id"].split(":", 1)[1] for r in memory.search(
                    ORG, question, levels_up_to("public"), k=4, body_id=body_id, lang=asked)]
                rows[label].append((lang, next((i for i, uid in enumerate(ranked) if any(uid.startswith(g) for g in good)), None)))
    for label, results in rows.items():
        for lang in ("all", "en", "fr"):
            rs = [r for r in results if lang == "all" or r[0] == lang]
            if rs:
                print(f"{label:27} {lang:3} first {sum(r[1] == 0 for r in rs)}/{len(rs)}, in four {sum(r[1] is not None for r in rs)}/{len(rs)},"
                      f" MRR {sum(1 / (r[1] + 1) for r in rs if r[1] is not None) / len(rs):.3f}")


if __name__ == "__main__":
    main()
