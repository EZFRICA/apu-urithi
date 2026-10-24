"""The one server: both sides, each under its own address, and the stage beside them.

    uv run python -m server              # http://localhost:8790/
    uv run python -m server --port 9000

  /teach/             the guardian's page                     (guardian/ui/teach)
  /learn/             the learner's page, works offline       (learner/ui/learn)
  /                   the showcase, static                    (apu/ui/showcase)
  /presentation/      the stage
  /api/guardian/*     what a guardian does: teach, publish, withdraw, answer the question box
  /api/learner/*      what a learner does: read, listen, practise, ask, review, keep
  /shared/*           the microphone, the loudspeaker and the prompter every page uses

The two sides never import each other (tests/shared/test_boundaries.py); this module is the
only place where both are mounted, and where the meter is given its counters.

Started as its own module, `server`, so stopping some other server by command name can
never stop this one, and found by its port alone in scripts/serve.sh.
"""

import argparse
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from apu import config, meter, observability  # noqa: E402
from exchange.counters import SqliteCounters  # noqa: E402
from guardian import config as guardian_config  # noqa: E402
from guardian.api.inbox_routes import router as inbox_router  # noqa: E402
from guardian.api.library_routes import router as knowledge_router  # noqa: E402
from guardian.api.live_routes import router as guardian_live_router  # noqa: E402
from guardian.api.source_routes import router as source_router  # noqa: E402
from guardian.api.routes import router as apprentice_router  # noqa: E402
from learner.api.routes import router as learning_router  # noqa: E402

ROOT = Path(__file__).parent
SHARED_UI = ROOT / "apu" / "ui"
GUARDIAN_UI = ROOT / "guardian" / "ui"
LEARNER_UI = ROOT / "learner" / "ui"


class FreshStaticFiles(StaticFiles):
    """
    Static files a browser is told not to keep.

    StaticFiles sends an etag and a last-modified date and no Cache-Control at all, which
    leaves a browser free to guess a freshness lifetime from the file's age and serve the
    file without asking again. Measured: an edited stylesheet kept being served from the
    browser's own cache while the server held the new one. These pages are looked at while
    they are being changed, so nothing here is worth keeping.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


def seed_an_empty_machine() -> None:
    """
    A fresh deployment has no Work Map, and a stage with nothing to present. With
    GUARDIAN_SEED_MAP pointing at an exported map, an empty store starts with that one.
    A store that already holds maps is never touched.
    """
    import json

    from guardian.memory.store import get_maps

    path = os.environ.get(guardian_config.SEED_MAP_ENV)
    if path and not get_maps().list_maps():
        get_maps().import_map(json.loads(Path(path).read_text(encoding="utf-8")))


def warm_up() -> None:
    """The library's connection and schema, and the embedder, made ready before anyone waits on
    them. Measured: the first question after a start took 8.7 s, the ones after it 1.7 s. A
    failure here is only a slower first question, said in the log."""
    import logging

    try:
        from apu import embeddings
        from library.store import get_store

        store = get_store()
        getattr(store, "ensure_schema", lambda: None)()
        embeddings.get_embedder().embed(["warm"])
    except Exception as error:
        logging.getLogger("server").warning("Could not warm up: %s", error)


@asynccontextmanager
async def lifespan(_app):
    # The meter's counts live in exchange/ (both sides spend); the rules stay in apu/meter.py.
    meter.set_counters(SqliteCounters())
    seed_an_empty_machine()
    if config.WARM_UP:
        import threading

        threading.Thread(target=warm_up, name="warm-up", daemon=True).start()
    observability.start()                  # model calls traced to Arize when it is set up, texts hidden
    yield
    observability.stop()


app = FastAPI(title="Urithi", lifespan=lifespan)


@app.exception_handler(meter.Refused)
async def refused(_request, error: meter.Refused) -> JSONResponse:
    """No budget: told plainly, with what ran out, and never another person's usage."""
    return JSONResponse(status_code=429, content={"detail": error.reason, "refused": error.capability})
app.include_router(apprentice_router)
app.include_router(knowledge_router)
app.include_router(learning_router)
app.include_router(inbox_router)
app.include_router(guardian_live_router)
app.include_router(source_router)


@app.get("/watch", include_in_schema=False)
@app.get("/watch/", include_in_schema=False)
@app.get("/apprentice", include_in_schema=False)
@app.get("/apprentice/", include_in_schema=False)
def moved() -> RedirectResponse:
    """Watch me work became the classroom mode of the guardian's page (step 4): a bookmark still arrives."""
    return RedirectResponse("/teach/", status_code=308)


app.mount("/shared", FreshStaticFiles(directory=SHARED_UI / "shared"), name="shared")
app.mount("/learn", FreshStaticFiles(directory=LEARNER_UI / "learn", html=True), name="learn")
app.mount("/teach", FreshStaticFiles(directory=GUARDIAN_UI / "teach", html=True), name="teach")
app.mount("/presentation",
          FreshStaticFiles(directory=SHARED_UI / "presentation", html=True), name="presentation")
# Last, because a mount at the root answers every path the ones above did not.
app.mount("/", FreshStaticFiles(directory=SHARED_UI / "showcase", html=True), name="showcase")


def main() -> None:
    parser = argparse.ArgumentParser(description="Urithi")
    parser.add_argument("--port", type=int, default=config.PORT,
                        help=f"port (default {config.PORT}, or set URITHI_PORT)")
    parser.add_argument("--host", default=config.HOST,
                        help=f"interface (default {config.HOST}, or set URITHI_HOST)")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
