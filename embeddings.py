"""Dual-signal similarity: sentence embeddings + word-vector association."""
import logging
import math
import os

import numpy as np

import config as cfg

log = logging.getLogger("hidden_word")


def calibrate(raw):
    """Monotonic mapping of blended raw similarity to the final 0..1 score."""
    x = np.asarray(raw, dtype=float)
    if cfg.CALIBRATION_MODE == "sigmoid":
        y = 1.0 / (1.0 + np.exp(-cfg.CALIBRATION_SIGMOID_STEEPNESS *
                                (x - cfg.CALIBRATION_SIGMOID_MIDPOINT)))
    else:
        xs, ys = zip(*sorted(cfg.CALIBRATION_ANCHORS))
        y = np.interp(x, xs, ys)
    y = np.clip(y, 0.0, 1.0)
    return float(y) if y.ndim == 0 else y


def blend(s_sem, s_assoc):
    a = cfg.EMBEDDING_ALPHA
    return a * s_sem + (1 - a) * s_assoc


def _load_file(path):
    from gensim.models import KeyedVectors
    if path.endswith(".kv"):
        return KeyedVectors.load(path)
    if path.endswith(".bin"):
        return KeyedVectors.load_word2vec_format(path, binary=True)
    try:                                   # gensim-data / word2vec text (has header)
        return KeyedVectors.load_word2vec_format(path)
    except ValueError:                     # raw GloVe text (no header)
        return KeyedVectors.load_word2vec_format(path, no_header=True)


def _load_assoc():
    """Local file first, then gensim downloader (retrying with certifi's CA bundle)."""
    name = cfg.ASSOC_MODEL_NAME
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (name, os.path.join(here, name), os.path.join(here, name + ".gz")):
        if p and os.path.isfile(p):
            return _load_file(p)
    try:
        import gensim.downloader as api
        try:
            return api.load(name)
        except Exception as first:  # noqa: BLE001  (typically Windows SSL errors)
            if "CERTIFICATE" not in str(first).upper() and "SSL" not in str(first).upper():
                raise
            import ssl
            import certifi
            ssl._create_default_https_context = lambda: ssl.create_default_context(
                cafile=certifi.where())
            return api.load(name)
    except Exception as exc:  # noqa: BLE001
        msg = (f"Could not load association model '{name}': {exc}\n"
               f"Fix: run `python download_vectors.py` (saves glove-wiki-gigaword-100.gz "
               f"next to server.py), or set ASSOC_MODEL_NAME to a local vector file.")
        if cfg.REQUIRE_ASSOC_MODEL:
            raise RuntimeError(msg) from exc
        log.warning("%s\nFalling back to semantic-only similarity.", msg)
        return None


class SimilarityScorer:
    def __init__(self, words):
        from sentence_transformers import SentenceTransformer
        log.info("Loading semantic model %s …", cfg.SEMANTIC_MODEL_NAME)
        self.sem_model = SentenceTransformer(cfg.SEMANTIC_MODEL_NAME)
        log.info("Loading association model %s …", cfg.ASSOC_MODEL_NAME)
        self.kv = _load_assoc()
        self._sem_cache, self._assoc_cache = {}, {}
        self.words = list(dict.fromkeys(w.casefold() for w in words))
        if self.words:
            log.info("Pre-computing embeddings for %d words …", len(self.words))
            vecs = self.sem_model.encode(self.words, normalize_embeddings=True,
                                         batch_size=128, show_progress_bar=False)
            self._sem_cache.update(zip(self.words, vecs))
            self.E = np.asarray(vecs, dtype=np.float32)
        else:
            self.E = np.zeros((0, 1), dtype=np.float32)
        self._build_assoc_matrix()

    def _build_assoc_matrix(self):
        n = len(self.words)
        dim = self.kv.vector_size if self.kv is not None else 1
        self.A = np.zeros((n, dim), dtype=np.float32)
        self.mask = np.zeros(n, dtype=bool)
        if self.kv is None:
            return
        for i, w in enumerate(self.words):
            v = self._assoc_vec(w)
            if v is not None:
                self.A[i], self.mask[i] = v, True

    def _sem_vec(self, w):
        w = w.casefold()
        if w not in self._sem_cache:
            self._sem_cache[w] = self.sem_model.encode(
                [w], normalize_embeddings=True, show_progress_bar=False)[0]
        return self._sem_cache[w]

    def _assoc_vec(self, w):
        w = w.casefold()
        if w in self._assoc_cache:
            return self._assoc_cache[w]
        v = None
        if self.kv is not None and w in self.kv.key_to_index:
            v = self.kv.get_vector(w, norm=True)
        self._assoc_cache[w] = v
        return v

    def score(self, hidden, hint):
        s_sem = float(self._sem_vec(hidden) @ self._sem_vec(hint))
        va, vb = self._assoc_vec(hidden), self._assoc_vec(hint)
        s_assoc = float(va @ vb) if va is not None and vb is not None else s_sem
        raw = blend(s_sem, s_assoc)
        return {"sem": s_sem, "assoc": s_assoc, "raw": raw, "score": calibrate(raw)}

    def nearest(self, hidden, exclude=()):
        """Closest vocabulary word to `hidden`, skipping `exclude`."""
        if not self.words:
            return None
        ex = {w.casefold() for w in exclude} | {hidden.casefold()}
        sem = self.E @ self._sem_vec(hidden)
        ha = self._assoc_vec(hidden)
        assoc = np.where(self.mask, self.A @ ha, sem) if ha is not None else sem
        raw = blend(sem, assoc)
        for i in np.argsort(-raw):
            if self.words[i] not in ex:
                w = self.words[i]
                return w, {"sem": float(sem[i]), "assoc": float(assoc[i]),
                           "raw": float(raw[i]), "score": calibrate(float(raw[i]))}
        return None
