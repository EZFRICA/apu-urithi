# Urithi, for Google Cloud Run.
#
#   gcloud run deploy urithi --source . --region europe-west1 --allow-unauthenticated --max-instances 1 \
#     --set-secrets GEMINI_API_KEY=gemini-api-key:latest,ELEVENLABS_API_KEY=elevenlabs-api-key:latest,BRIGHTDATA_API_TOKEN=brightdata-api-token:latest,NEO4J_URI=neo4j-uri:latest,NEO4J_USERNAME=neo4j-username:latest,NEO4J_PASSWORD=neo4j-password:latest,LEARNER_SIGNING_KEY=urithi-signing-key:latest
#
# Keys come from Secret Manager at run time, never from the image. Cloud Run sets PORT; the
# server listens on every interface inside the container, which is what Cloud Run routes to.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# liblouis and its tables: the braille Work Map and the slips. Checked below, at build time,
# so an image that cannot emboss never ships.
RUN apt-get update \
    && apt-get install -y --no-install-recommends liblouis20 liblouis-data \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Dependencies first, from the lock file, so a code change does not reinstall them.
COPY pyproject.toml uv.lock LICENSE NOTICE ./
RUN uv sync --frozen --no-dev --no-install-project

# The shared core, the library, the question box, and the two sides that use them.
COPY server.py ./
COPY apu ./apu
COPY library ./library
COPY exchange ./exchange
COPY guardian ./guardian
COPY learner ./learner
COPY deploy ./deploy
COPY registries ./registries
# The embedding model (about 240 MB): the library searches with it, and it is never
# downloaded at runtime, so it travels in the image.
COPY models ./models

RUN uv run --no-sync python -c "from apu.modality.braille.sheet import braille_sheet; \
assert braille_sheet('Equipment over five thousand euros is capex.').pages_unicode, 'no braille'"

# Cloud Run's filesystem lasts as long as one instance. The Work Maps live there, and an
# instance that starts empty is given Sabine's, so the stage always has something to show.
ENV URITHI_HOST=0.0.0.0 \
    GUARDIAN_DATA_DIR=/tmp/urithi/guardian \
    LEARNER_DATA_DIR=/tmp/urithi/learner \
    EXCHANGE_DATA_DIR=/tmp/urithi/exchange \
    URITHI_LOG_DIR=/tmp/urithi/logs \
    GUARDIAN_SEED_MAP=/app/deploy/sabine-workmap.json \
    PYTHONUNBUFFERED=1

CMD ["sh", "-c", "exec uv run --no-sync python -m server --host 0.0.0.0 --port ${PORT:-8080}"]
