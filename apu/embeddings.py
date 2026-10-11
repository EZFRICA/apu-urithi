"""The one embedding model of the library, local ONNX through fastembed.

Local on purpose, even with the library online: a package searched offline must be embedded
by the same model as the library it was cut from, or the two vector spaces do not match and
a search returns noise ranked as though it were relevant.

  - The model is read from config.EMBEDDING_CACHE_DIR and never downloaded at runtime: on a
    machine with no connectivity a download hangs at the first question instead of failing.
  - It is built on first use, not at import, so importing this module costs nothing.
  - Vectors are normalised to unit length, so cosine similarity is the dot product whichever
    store holds them.
"""

import math
import threading
from collections.abc import Sequence

from apu import config
from apu.logger import get_logger

logger = get_logger(__name__)


class EmbedderUnavailable(RuntimeError):
    """The model is not on this machine."""


class LocalEmbedder:
    def __init__(self, model_name: str, cache_dir: str, dim: int):
        from fastembed import (
            TextEmbedding,  # imported here: a few seconds of ONNX setup
        )

        try:
            self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir,
                                        local_files_only=True)
        except Exception as error:
            raise EmbedderUnavailable(
                f"The embedding model {model_name!r} is not in {cache_dir}. It is never "
                "downloaded at runtime; copy an existing cache there, or set "
                "URITHI_EMBEDDING_CACHE_DIR to one.") from error
        self.model_name, self.dim = model_name, dim
        logger.info("Embedder: local ONNX, %s, %d dimensions", model_name, dim)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = [normalize([float(x) for x in v]) for v in self._model.embed(list(texts))]
        for vector in vectors:
            if len(vector) != self.dim:
                raise EmbedderUnavailable(
                    f"{self.model_name} returned {len(vector)} dimensions, configured {self.dim}.")
        return vectors

    def stamp(self) -> dict:
        """The model's identity, carried by a package and checked by the device that reads it."""
        return {"model": self.model_name, "dim": self.dim}


def normalize(vector: Sequence[float]) -> list[float]:
    """Unit length. A zero vector has no direction and is returned unchanged."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [float(x) / norm for x in vector] if norm else [float(x) for x in vector]


_embedder = None
_default_embedder = None
_lock = threading.Lock()


def get_embedder():
    global _embedder, _default_embedder
    with _lock:
        if _embedder is None:
            if (
                _default_embedder is None
                or _default_embedder.model_name != config.EMBEDDING_MODEL
                or _default_embedder.dim != config.EMBEDDING_DIM
            ):
                _default_embedder = LocalEmbedder(
                    config.EMBEDDING_MODEL, config.EMBEDDING_CACHE_DIR, config.EMBEDDING_DIM
                )
            _embedder = _default_embedder
    return _embedder


def set_embedder(embedder) -> None:
    """Swap the embedder, for tests. None goes back to the configured model."""
    global _embedder
    with _lock:
        _embedder = embedder

