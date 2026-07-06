"""Build the ontology knowledge DB (SQLite corpus + FAISS indexes) offline.

Builds the app's first-class launch tuples by triggering the engine's own
corpus+index build (``OntoMapEngine.run`` builds on a cache miss, then persists
to ``KNOWLEDGE_DB_DIR``). Run this ONCE on a capable machine, then distribute the
result with ``python -m metaharmonizer.scripts.knowledge_db export`` — never
build on a small production VM.

Corpora fetch key-free (NCIt via EVSREST, UBERON via OLS4). ``UMLS_API_KEY`` only
adds optional synonym enrichment.

Usage::

    python -m scripts.build_kb                       # all launch tuples
    python -m scripts.build_kb --only disease/ncit   # one tuple
    KNOWLEDGE_DB_DIR=/data/kb python -m scripts.build_kb

This is an offline build tool (not app runtime), so it may import the engine
directly — the engine-adapter boundary only governs ``backend/app``.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

# (category, ontology_source, seed_query) — the seed drives one run so the full
# corpus AND the FAISS index build. It must NOT be an exact ontology label,
# otherwise Stage 1 short-circuits and Stage 2 (which builds the FAISS index) is
# skipped, leaving an index-less KB. A deliberately non-label probe forces Stage 2.
_PROBE = "kb build probe do not match"
LAUNCH_TUPLES = [
    ("disease", "ncit", _PROBE),
    ("bodysite", "uberon", _PROBE),
    ("treatment", "ncit", _PROBE),
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_kb")


def _build_one(category: str, source: str, seed: str) -> int:
    from metaharmonizer.engine.ontology_mapping_engine import OntoMapEngine

    t0 = time.perf_counter()
    engine = OntoMapEngine(
        corpus_category=category,
        query_ls=[seed],
        ontology_source=source,
        s2_method="sap-bert",
        s2_strategy="st",
    )
    result = engine.run()
    n = len(result) if result is not None else 0
    _verify_outputs(category, source)
    logger.info(
        "built %s/%s in %.1fs (seed query mapped %d row(s))",
        category, source, time.perf_counter() - t0, n,
    )
    return n


def _verify_outputs(category: str, source: str) -> None:
    """Completeness check: the ST corpus FAISS index plus its ids sidecar must
    exist and be non-empty for this category. Catches a build that died mid-way
    (partial KB), which the export CLI's checksums alone would not detect.

    Only the ST corpus index carries a ``.index.ids.npy`` sidecar; the auxiliary
    synonym index keeps its row ids in the SQLite synonym table, so it is checked
    for non-emptiness only (no sidecar requirement)."""
    from metaharmonizer import _paths

    faiss_dir = _paths.FAISS_INDEX_DIR
    corpus = [
        p for p in faiss_dir.glob(f"st_*_{source}_{category}*.index")
        if p.stat().st_size > 0
    ]
    if not corpus:
        raise RuntimeError(
            f"no non-empty ST corpus FAISS index for {category}/{source} under "
            f"{faiss_dir} — build did not complete."
        )
    for idx in corpus:
        ids = idx.with_suffix(".index.ids.npy")
        if not ids.exists() or ids.stat().st_size == 0:
            raise RuntimeError(f"missing/empty ids sidecar for {idx.name} — partial build.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ontology knowledge DB.")
    parser.add_argument(
        "--only",
        help="Build a single 'category/source' tuple (e.g. disease/ncit).",
    )
    args = parser.parse_args(argv)

    tuples = LAUNCH_TUPLES
    if args.only:
        cat, _, src = args.only.partition("/")
        tuples = [(c, s, q) for (c, s, q) in LAUNCH_TUPLES if c == cat and s == src]
        if not tuples:
            logger.error("unknown tuple %r; known: %s", args.only,
                         ", ".join(f"{c}/{s}" for c, s, _ in LAUNCH_TUPLES))
            return 2

    failures = 0
    for category, source, seed in tuples:
        logger.info("building %s/%s …", category, source)
        try:
            _build_one(category, source, seed)
        except Exception:  # noqa: BLE001 — report and continue with the next tuple
            failures += 1
            logger.exception("FAILED to build %s/%s", category, source)

    if failures:
        logger.error("%d/%d tuple(s) failed", failures, len(tuples))
        return 1
    logger.info("done — %d tuple(s) built", len(tuples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
