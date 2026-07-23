"""
Performance patches for the upstream ``metaharmonizer`` engine.

This module lives inside ``engine_adapter/`` — the ONLY place the project is
allowed to import ``metaharmonizer`` (enforced by
``scripts/check_engine_boundary.py``). It applies, exactly once per process, two
behaviour-preserving performance optimisations (pure memoisation).

Why this is needed
------------------
The adapter builds a fresh ``SchemaMapEngine`` for every distinct uploaded CSV
(``MetaHarmonizerAdapter._engine_for`` is keyed by file path). Upstream's
per-study construction is expensive in two ways:

1. **Model reload.** ``SchemaMapEngine`` constructs a ``SentenceTransformer`` in
   three places (``engine``, ``loaders.value_loader``, ``loaders.dict_loader``)
   for *every* study. Loading ``all-MiniLM-L6-v2`` is ~2.5s and happens twice
   per construction. → Patch 1 shares one instance per model name process-wide.

2. **Repeated live NCI EVS calls.** Stage-2 ontology matching calls the live NCI
   EVS REST API (rate-limited to ~8 req/s) for every novel value in every
   non-numeric column. Upstream keeps the results in per-instance dicts that are
   discarded when the engine is rebuilt for the next study, so common clinical
   values (sex, stage, race, vital status, …) are re-fetched over the network on
   every upload. → Patch 2 points every ``NCIClientSync`` at the same
   process-wide dicts, seeded from disk and flushed back after each run, so each
   value is looked up at most once — ever.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module state (process-wide, guarded by locks)
# ---------------------------------------------------------------------------
_installed = False
_install_lock = threading.Lock()

# Patch 1 — one SentenceTransformer per model name.
_model_cache: dict[str, Any] = {}
_model_lock = threading.Lock()

# Patch 2 — persistent, shared NCI EVS lookup cache.
# Stored alongside the dashboard's other data assets. Kept separate from the
# dashboard-owned ``nci_cache.json`` (different schema/owner).
_NCI_CACHE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "nci_schema_cache.json"
)
_nci_term2code: dict[str, Any] = {}       # normalized term -> code | None
_nci_code2category: dict[str, Any] = {}   # code -> [category, ...] | None
_nci_lock = threading.Lock()
_nci_loaded = False
# Keys already persisted to the shared store, so each flush only writes deltas.
_nci_persisted_terms: set[str] = set()
_nci_persisted_codes: set[str] = set()

# Shared store (Redis) keys. When Redis is reachable the cache is shared across
# every api/worker process and survives restarts/redeploys; the JSON file above
# stays as a local fallback for single-process / no-Redis dev.
_REDIS_TERM_KEY = "mh:nci:schema:term2code"
_REDIS_CAT_KEY = "mh:nci:schema:code2category"
_NEG = "\x00"  # sentinel for a cached negative lookup (term -> no code)


def _redis_sync():
    """Best-effort sync Redis client from settings; ``None`` if unavailable."""
    try:
        import redis  # redis-py ships a sync client alongside redis.asyncio

        from app.core.settings import settings

        return redis.Redis.from_url(
            settings.redis_url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Patch 1: shared SentenceTransformer
# ---------------------------------------------------------------------------
def _make_cached_sentence_transformer(real_cls):
    """Return a factory that hands back one cached instance per model name.

    Only the plain ``SentenceTransformer(name)`` form is cached; any call with
    extra args/kwargs falls through to the real constructor untouched, so we
    never accidentally share a differently-configured model.
    """

    def factory(model_name_or_path=None, *args, **kwargs):
        if args or kwargs or model_name_or_path is None:
            return real_cls(model_name_or_path, *args, **kwargs)
        key = str(model_name_or_path)
        cached = _model_cache.get(key)
        if cached is None:
            with _model_lock:
                cached = _model_cache.get(key)
                if cached is None:
                    cached = real_cls(model_name_or_path)
                    _model_cache[key] = cached
        return cached

    return factory


def _patch_sentence_transformer() -> None:
    from metaharmonizer.models.schema_mapper import engine as _engine
    from metaharmonizer.models.schema_mapper.loaders import (
        dict_loader as _dl,
        value_loader as _vl,
    )

    real_cls = _engine.SentenceTransformer
    if getattr(real_cls, "_mh_is_cached_factory", False):
        return
    factory = _make_cached_sentence_transformer(real_cls)
    factory._mh_is_cached_factory = True  # type: ignore[attr-defined]
    for mod in (_engine, _vl, _dl):
        if getattr(mod, "SentenceTransformer", None) is real_cls:
            mod.SentenceTransformer = factory


def warm_model() -> None:
    """Load the default field model once so the cost is paid at startup."""
    try:
        from metaharmonizer.models.schema_mapper import engine as _engine
        from metaharmonizer.models.schema_mapper.config import FIELD_MODEL

        _engine.SentenceTransformer(FIELD_MODEL)
    except Exception:
        # Warming is best-effort; never block startup on it.
        pass


# ---------------------------------------------------------------------------
# Patch 2: persistent, shared NCI cache
# ---------------------------------------------------------------------------
def _load_from_redis() -> bool:
    """Seed the in-memory dicts from the shared Redis store. Returns success."""
    client = _redis_sync()
    if client is None:
        return False
    try:
        terms = client.hgetall(_REDIS_TERM_KEY) or {}
        cats = client.hgetall(_REDIS_CAT_KEY) or {}
    except Exception:
        return False
    for term, code in terms.items():
        _nci_term2code[term] = None if code == _NEG else code
        _nci_persisted_terms.add(term)
    for code, cat_json in cats.items():
        try:
            _nci_code2category[code] = json.loads(cat_json)
        except Exception:
            continue
        _nci_persisted_codes.add(code)
    return True


def _load_from_disk() -> None:
    try:
        if _NCI_CACHE_PATH.exists():
            raw = json.loads(_NCI_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw.get("term2code"), dict):
                _nci_term2code.update(raw["term2code"])
            if isinstance(raw.get("code2category"), dict):
                _nci_code2category.update(raw["code2category"])
    except Exception:
        # A corrupt cache must never break harmonization; start empty.
        pass


def _load_nci_cache() -> None:
    global _nci_loaded
    if _nci_loaded:
        return
    with _nci_lock:
        if _nci_loaded:
            return
        # Prefer the shared store; fall back to the local file when Redis is
        # unreachable (single-process dev). Load both so a machine that warmed
        # its file cache still contributes on first Redis flush.
        _load_from_redis()
        _load_from_disk()
        _nci_loaded = True


def _flush_to_redis() -> None:
    """Write only the new (unpersisted) entries to the shared Redis store."""
    new_terms = {k: v for k, v in _nci_term2code.items() if k not in _nci_persisted_terms}
    new_cats = {k: v for k, v in _nci_code2category.items() if k not in _nci_persisted_codes}
    if not new_terms and not new_cats:
        return
    client = _redis_sync()
    if client is None:
        return
    try:
        if new_terms:
            client.hset(_REDIS_TERM_KEY,
                        mapping={k: (_NEG if v is None else v) for k, v in new_terms.items()})
        if new_cats:
            client.hset(_REDIS_CAT_KEY,
                        mapping={k: json.dumps(v) for k, v in new_cats.items()})
    except Exception:
        return
    _nci_persisted_terms.update(new_terms)
    _nci_persisted_codes.update(new_cats)


def save_nci_cache() -> None:
    """Flush the shared NCI cache to Redis (shared) and the local file (fallback)."""
    if not _nci_loaded:
        return
    with _nci_lock:
        _flush_to_redis()
        try:
            payload = {
                "term2code": _nci_term2code,
                "code2category": _nci_code2category,
            }
            _NCI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _NCI_CACHE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, _NCI_CACHE_PATH)
        except Exception:
            pass


def _patch_nci_client() -> None:
    from metaharmonizer.utils.ncit_match_utils import NCIClientSync

    if getattr(NCIClientSync, "_mh_cache_patched", False):
        return
    orig_init = NCIClientSync.__init__

    def patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        # Share the SAME dicts across every instance/study so lookups
        # accumulate process-wide and persist across restarts.
        self.term2code = _nci_term2code
        self.code2category = _nci_code2category

    NCIClientSync.__init__ = patched_init
    NCIClientSync._mh_cache_patched = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def install_patches() -> None:
    """Idempotently install all engine performance + correctness patches."""
    global _installed
    if _installed:
        return
    with _install_lock:
        if _installed:
            return
        _patch_sentence_transformer()
        _patch_nci_client()
        _load_nci_cache()
        _installed = True
