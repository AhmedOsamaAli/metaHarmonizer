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

# (category, ontology_source, seed_query) — the seed just drives one run so the
# full corpus builds; the mapping result is discarded.
LAUNCH_TUPLES = [
    ("disease", "ncit", "breast cancer"),
    ("bodysite", "uberon", "lung"),
    ("treatment", "ncit", "chemotherapy"),
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
    logger.info(
        "built %s/%s in %.1fs (seed query mapped %d row(s))",
        category, source, time.perf_counter() - t0, n,
    )
    return n


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
