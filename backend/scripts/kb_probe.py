"""Verify that every launch ontology resolves from a complete offline KB."""

from __future__ import annotations

import logging

from app.engine_adapter.kb_assets import (
    REQUIRED_ONTOLOGY_TUPLES,
    installed_kb_issues,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

PROBE_VALUES = {
    ("disease", "ncit"): "glioblastma",
    ("bodysite", "uberon"): "splen",
    ("treatment", "ncit"): "pembrolizumabb",
}


def main() -> int:
    issues = installed_kb_issues()
    if issues:
        for issue in issues:
            print(f"[kb-probe] ERROR: {issue}")
        return 1

    from metaharmonizer import OntoMapEngine

    for category, source in REQUIRED_ONTOLOGY_TUPLES:
        engine = OntoMapEngine(
            corpus_category=category,
            query_ls=[PROBE_VALUES[(category, source)]],
            ontology_source=source,
            s2_method="sap-bert",
            s2_strategy="st",
        )
        corpus = engine._resolve_corpus_df()
        if corpus is None or corpus.empty:
            print(f"[kb-probe] ERROR: empty corpus for {category}/{source}")
            return 1
        result = engine.run()
        if result is None or result.empty:
            print(f"[kb-probe] ERROR: no mapping result for {category}/{source}")
            return 1
        print(
            f"[kb-probe] {category}/{source}: "
            f"{len(corpus)} corpus rows, index query passed"
        )

    print("[kb-probe] complete offline KB verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
