"""Controlled probe: does OntoMapEngine load the prebuilt KB or rebuild from NCI?

Run with KNOWLEDGE_DB_DIR pointed at the built KB. Prints the single corpus
decision (load vs build) and whether a prebuilt FAISS index is found, without
triggering a full 26k-concept rebuild if we can help it.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

from metaharmonizer._paths import (  # noqa: E402
    KNOWLEDGE_DB_DIR, VECTOR_DB_PATH, FAISS_INDEX_DIR, corpus_path,
)

print("KNOWLEDGE_DB_DIR:", KNOWLEDGE_DB_DIR)
print("VECTOR_DB_PATH  :", VECTOR_DB_PATH, "exists:", VECTOR_DB_PATH.exists())
print("FAISS_INDEX_DIR :", FAISS_INDEX_DIR, "exists:", FAISS_INDEX_DIR.exists())
if FAISS_INDEX_DIR.exists():
    for p in sorted(FAISS_INDEX_DIR.glob("*treatment*")):
        print("  faiss:", p.name, p.stat().st_size)
csv = corpus_path("treatment", "ncit", "_corpus.csv")
print("corpus csv      :", csv, "exists:", csv.exists())

# Now construct the engine exactly like the app adapter does and inspect what it
# resolves. We stop before .run() to avoid a full rebuild; we call the corpus
# resolver directly.
import metaharmonizer as mh  # noqa: E402

eng = mh.OntoMapEngine(
    corpus_category="treatment",
    query_ls=["chemotherapy"],
    ontology_source="ncit",
    s2_method="sap-bert",
    s2_strategy="st",
)
print("--- calling _resolve_corpus_df (should LOAD, not build) ---")
df = eng._resolve_corpus_df()
print("corpus rows:", len(df))
print("PROBE DONE")
