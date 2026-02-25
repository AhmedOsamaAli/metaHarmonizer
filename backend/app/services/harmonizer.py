"""
MetaHarmonizer Dashboard — Harmonizer Service (Real Engine Wrapper)

Wraps the real shbrief/MetaHarmonizer SchemaMapEngine with a clean interface.
The engine lives in backend/engine/ and provides a production-grade
4-stage cascade: Dict/Fuzzy → Value/Ontology → Numeric/Semantic → LLM.

Architecture:
  - SchemaMapEngine (real ML pipeline) is isolated behind this module
  - Our custom ontology value mapping uses a dictionary approach since
    the real OntoMapEngine requires additional infrastructure (FAISS, etc.)
  - The interface allows swapping in improved mappers without touching
    the dashboard frontend/backend contracts

Performance:
  - Engine instance is cached at module level after first creation.
    The SentenceTransformer model (~90 MB), dictionaries, and matchers
    persist across requests.  Only the input DataFrame and per-column
    caches are swapped on each upload, cutting subsequent requests from
    ~3-4 min down to ~20-40 s.
  - A pre_warm() function can be called during app startup so that
    even the first user upload benefits from a warm engine.

Public API:
  - run_schema_mapping(raw_df, curated_df, csv_path=None) -> list[dict]
  - run_ontology_mapping(raw_df, schema_mappings) -> list[dict]
  - generate_study_id(filename) -> str
  - pre_warm() -> None
  - ONTOLOGY_MAP  (re-exported for ontology router)
"""

from __future__ import annotations

import logging
import os
import sys
import time
import types
import re
import uuid
import threading
from pathlib import Path
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Real SchemaMapEngine Setup (lazy-loaded + cached)
# ---------------------------------------------------------------------------

_REPO_DIR = Path(__file__).resolve().parent.parent.parent / "engine"
_HAS_REAL_ENGINE = False
_SchemaMapEngine = None

# Cached engine instance — survives across requests
_cached_engine = None
_engine_lock = threading.Lock()
_engine_ready = False


def _init_real_engine() -> None:
    """Lazy-import the real SchemaMapEngine, bypassing heavy deps."""
    global _HAS_REAL_ENGINE, _SchemaMapEngine
    if _HAS_REAL_ENGINE or _SchemaMapEngine is not None:
        return

    try:
        repo_str = str(_REPO_DIR)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        # Bypass src.models.__init__.py (imports ontology mappers we don't need)
        if "src.models" not in sys.modules:
            mod = types.ModuleType("src.models")
            mod.__path__ = [os.path.join(repo_str, "src", "models")]
            mod.__package__ = "src.models"
            sys.modules["src.models"] = mod

        orig_cwd = os.getcwd()
        os.chdir(repo_str)
        from src.models.schema_mapper.engine import SchemaMapEngine as _Eng
        _SchemaMapEngine = _Eng
        _HAS_REAL_ENGINE = True
        os.chdir(orig_cwd)
        logger.info("Real SchemaMapEngine loaded from %s", repo_str)
    except Exception as e:
        logger.warning("Could not load real engine: %s", e)
        _HAS_REAL_ENGINE = False


# ---------------------------------------------------------------------------
# Ontology value mappings  (field -> {raw_value: (term, id)})
# Kept here because the real OntoMapEngine requires FAISS/SQLite
# infrastructure that is beyond the current scope.
# ---------------------------------------------------------------------------

ONTOLOGY_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "body_site": {
        "stool": ("feces", "UBERON:0001988"),
        "feces": ("feces", "UBERON:0001988"),
    },
    "sex": {
        "male": ("Male", "NCIT:C20197"),
        "female": ("Female", "NCIT:C16576"),
        "m": ("Male", "NCIT:C20197"),
        "f": ("Female", "NCIT:C16576"),
    },
    "country": {
        "can": ("Canada", "NCIT:C16482"),
        "canada": ("Canada", "NCIT:C16482"),
        "usa": ("United States", "NCIT:C17233"),
        "united states": ("United States", "NCIT:C17233"),
        "italy": ("Italy", "NCIT:C16761"),
        "chn": ("China", "NCIT:C16448"),
        "china": ("China", "NCIT:C16448"),
        "gbr": ("United Kingdom", "NCIT:C17234"),
        "deu": ("Germany", "NCIT:C16636"),
        "germany": ("Germany", "NCIT:C16636"),
        "fra": ("France", "NCIT:C16592"),
        "france": ("France", "NCIT:C16592"),
        "aus": ("Australia", "NCIT:C16311"),
        "australia": ("Australia", "NCIT:C16311"),
        "swe": ("Sweden", "NCIT:C17180"),
        "sweden": ("Sweden", "NCIT:C17180"),
        "isr": ("Israel", "NCIT:C16757"),
        "israel": ("Israel", "NCIT:C16757"),
        "nld": ("Netherlands", "NCIT:C16903"),
        "esp": ("Spain", "NCIT:C17152"),
        "jpn": ("Japan", "NCIT:C16769"),
        "kor": ("South Korea", "NCIT:C17202"),
        "ind": ("India", "NCIT:C16726"),
        "per": ("Peru", "NCIT:C16954"),
        "mdg": ("Madagascar", "NCIT:C16835"),
        "tza": ("Tanzania", "NCIT:C17194"),
        "fin": ("Finland", "NCIT:C16586"),
        "hun": ("Hungary", "NCIT:C16712"),
        "aut": ("Austria", "NCIT:C16312"),
        "dnk": ("Denmark", "NCIT:C16500"),
        "lux": ("Luxembourg", "NCIT:C16829"),
        "eth": ("Ethiopia", "NCIT:C16547"),
        "fji": ("Fiji", "NCIT:C16585"),
    },
    "disease": {
        "adenoma": ("Adenoma", "NCIT:C3220"),
        "healthy": ("Healthy", "NCIT:C115935"),
        "crc": ("Colorectal Cancer", "NCIT:C9382"),
        "colorectal cancer": ("Colorectal Cancer", "NCIT:C9382"),
        "ibd": ("Inflammatory Bowel Disease", "NCIT:C3138"),
        "cd": ("Crohn Disease", "NCIT:C2965"),
        "uc": ("Ulcerative Colitis", "NCIT:C3343"),
        "t1d": ("Type 1 Diabetes", "NCIT:C2986"),
        "t2d": ("Type 2 Diabetes", "NCIT:C26747"),
    },
    "age_group": {
        "adult": ("Adult", "NCIT:C17600"),
        "senior": ("Senior", "NCIT:C25195"),
        "infant": ("Infant", "NCIT:C27956"),
        "child": ("Child", "NCIT:C16423"),
        "newborn": ("Newborn", "NCIT:C14174"),
        "schoolage": ("School Age Child", "NCIT:C89831"),
    },
    "smoker": {
        "yes": ("Smoker", "NCIT:C67147"),
        "no": ("Non-Smoker", "NCIT:C65108"),
    },
    "control": {
        "study control": ("Study Control", "NCIT:C142703"),
        "case": ("Case", "NCIT:C49152"),
    },
}


# Confidence thresholds
THRESHOLD_AUTO_ACCEPT = 0.90
THRESHOLD_REVIEW = 0.50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(name: str) -> str:
    """Lowercase, strip, replace separators with underscore."""
    s = name.strip().lower()
    s = re.sub(r"[\s\-\.]+", "_", s)
    return s


# ---------------------------------------------------------------------------
# Real Engine Runner (cached — model + dictionaries persist across requests)
# ---------------------------------------------------------------------------

def _create_engine(csv_path: str):
    """Create a fresh SchemaMapEngine instance (expensive, ~10-15 s)."""
    engine = _SchemaMapEngine(csv_path, mode="manual", top_k=5)

    # NCI EVS REST API is enabled — Stage 2's OntologyMatcher will call
    # nci_client.map_value_to_schema() for columns that reach stage 2.
    # This adds network latency (~100 s on first run) but improves
    # ontology-based matching accuracy.  Resolved terms are cached to
    # nci_cache.json so subsequent runs are fast.

    return engine


def _reset_engine_for_file(engine, csv_path: str) -> None:
    """
    Swap the underlying DataFrame and clear per-column caches so the
    cached engine can process a new file without re-loading the
    SentenceTransformer model or dictionaries.
    """
    # Read the new CSV
    if csv_path.endswith(".tsv"):
        engine.df = pd.read_csv(csv_path, sep="\t", dtype=str)
    else:
        engine.df = pd.read_csv(csv_path, sep=",", dtype=str)

    # Clear column-specific caches (data-dependent)
    engine._col_values_cache = {}
    engine._col_freq_cache = {}
    engine._numeric_embs = None

    # Clear lru_cache on instance methods that depend on column data
    if hasattr(engine.is_col_numeric, "cache_clear"):
        engine.is_col_numeric.cache_clear()
    # NOTE: _enc cache is text→embedding — safe to keep across files

    # Update output file path
    from src.models.schema_mapper.config import OUTPUT_DIR

    base = os.path.basename(csv_path)
    root, _ = os.path.splitext(base)
    engine.output_file = os.path.join(OUTPUT_DIR, f"{root}.csv")


import json as _json

_NCI_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "nci_cache.json"
_SAMPLE_CSV = Path(__file__).resolve().parent.parent.parent.parent / "metadata_samples" / "new_meta.csv"


def _save_nci_cache(engine) -> None:
    """Persist the NCI client's term→code and code→category caches to disk."""
    try:
        nci = engine.nci_client
        cache_data = {
            "term2code": {k: v for k, v in nci.term2code.items()},
            "code2category": {k: v for k, v in nci.code2category.items()},
        }
        _NCI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_NCI_CACHE_PATH, "w") as f:
            _json.dump(cache_data, f)
        logger.info("Saved NCI cache (%d terms, %d codes)", len(nci.term2code), len(nci.code2category))
    except Exception as e:
        logger.warning("Could not save NCI cache: %s", e)


def _load_nci_cache(engine) -> int:
    """Load persisted NCI caches into the engine. Returns number of terms loaded."""
    if not _NCI_CACHE_PATH.exists():
        return 0
    try:
        with open(_NCI_CACHE_PATH) as f:
            cache_data = _json.load(f)
        nci = engine.nci_client
        t2c = cache_data.get("term2code", {})
        c2c = cache_data.get("code2category", {})
        nci.term2code.update(t2c)
        nci.code2category.update(c2c)
        logger.info("Loaded NCI cache (%d terms, %d codes)", len(t2c), len(c2c))
        return len(t2c)
    except Exception as e:
        logger.warning("Could not load NCI cache: %s", e)
        return 0


def _run_real_engine(csv_path: str) -> pd.DataFrame:
    """
    Run the real SchemaMapEngine with instance caching.

    First call:  full init (~40-60 s — model download/load + dictionaries).
    Later calls: swap DataFrame + clear caches, then run (~2-5 s matching).

    Thread-safe: acquires _engine_lock for the ENTIRE operation so the
    pre-warm thread and request threads don't clobber each other.
    """
    global _cached_engine, _engine_ready

    orig_cwd = os.getcwd()
    os.chdir(str(_REPO_DIR))
    try:
        with _engine_lock:
            if _cached_engine is not None:
                # ---- Fast path: reuse the warm engine ----
                t0 = time.perf_counter()
                _reset_engine_for_file(_cached_engine, csv_path)
                logger.info(
                    "Reusing cached engine (reset took %.2fs)",
                    time.perf_counter() - t0,
                )
                engine = _cached_engine
            else:
                # ---- Cold path: first-time creation ----
                t0 = time.perf_counter()
                engine = _create_engine(csv_path)
                _cached_engine = engine
                _engine_ready = True
                _load_nci_cache(engine)
                logger.info(
                    "Engine created & cached (init took %.1fs)",
                    time.perf_counter() - t0,
                )

            # Run matching (inside lock to prevent concurrent mutations)
            t0 = time.perf_counter()
            result = engine.run_schema_mapping()
            elapsed = time.perf_counter() - t0
            logger.info("Schema mapping took %.1fs", elapsed)

            # Persist NCI caches after successful run
            _save_nci_cache(engine)

            return result
    finally:
        os.chdir(orig_cwd)


def pre_warm() -> None:
    """
    Pre-warm the SchemaMapEngine during application startup.

    Holds _engine_lock for the entire duration so that any upload
    request arriving during warm-up blocks until caches are ready,
    then benefits from them immediately (~2 s matching vs ~2 min cold).

    Strategy:
    1. Create engine with the sample CSV (or a dummy CSV if absent).
    2. Load any persisted NCI API caches from disk.
    3. Run the mapping once so all caches (embeddings, NCI, numeric) are warm.
    4. Save NCI caches to disk for the next cold start.
    """
    global _cached_engine, _engine_ready
    _init_real_engine()
    if not _HAS_REAL_ENGINE:
        logger.info("Skipping pre-warm — real engine unavailable")
        return

    # Pick the best CSV for warm-up
    if _SAMPLE_CSV.exists():
        warmup_csv = str(_SAMPLE_CSV)
        logger.info("Pre-warming with sample: %s", _SAMPLE_CSV.name)
    else:
        warmup_csv = str(_REPO_DIR / "_warmup_dummy.csv")
        pd.DataFrame({"_warmup": ["x"]}).to_csv(warmup_csv, index=False)
        logger.info("Pre-warming with minimal dummy CSV")

    t0 = time.perf_counter()
    orig_cwd = os.getcwd()
    os.chdir(str(_REPO_DIR))
    try:
        with _engine_lock:
            engine = _create_engine(warmup_csv)
            _cached_engine = engine

            # Load persistent NCI cache (cuts ~100 s of API calls on repeat starts)
            _load_nci_cache(engine)

            # Run mapping to warm all runtime caches (embeddings, NCI, etc.)
            engine.run_schema_mapping()

            # Save NCI caches for next cold start
            _save_nci_cache(engine)

            _engine_ready = True
            elapsed = time.perf_counter() - t0
            logger.info("Engine fully pre-warmed in %.1fs", elapsed)
    except Exception as e:
        logger.error("Pre-warm failed: %s", e)
    finally:
        os.chdir(orig_cwd)
        # Clean up dummy file if we created one
        dummy = str(_REPO_DIR / "_warmup_dummy.csv")
        if os.path.exists(dummy):
            os.remove(dummy)


def _transform_engine_results(results_df: pd.DataFrame) -> list[dict]:
    """
    Transform SchemaMapEngine output DataFrame into dashboard format.

    Engine columns: query, stage, method, match1..match5, match1_score..match5_score
    Dashboard format: raw_column, matched_field, confidence_score, stage, method, alternatives, status
    """
    mappings: list[dict] = []

    for _, row in results_df.iterrows():
        raw_col = row.get("query", "")
        stage = row.get("stage", "unmapped")
        method = row.get("method", "")

        match1 = row.get("match1")
        score1 = row.get("match1_score")

        if pd.isna(match1) or str(match1).strip() == "" or match1 is None:
            matched_field = None
            confidence_score = 0.0
        else:
            matched_field = str(match1)
            confidence_score = float(score1) if pd.notna(score1) else 0.0

        # Build alternatives from match2–match5
        alternatives = []
        for i in range(2, 6):
            m = row.get(f"match{i}")
            s = row.get(f"match{i}_score")
            if pd.notna(m) and str(m).strip():
                alternatives.append({
                    "field": str(m),
                    "score": round(float(s), 4) if pd.notna(s) else 0.0,
                    "method": method,
                })

        # Status from confidence
        if stage == "invalid":
            status = "rejected"
        elif confidence_score >= THRESHOLD_AUTO_ACCEPT:
            status = "accepted"
        else:
            status = "pending"

        mappings.append({
            "raw_column": raw_col,
            "matched_field": matched_field,
            "confidence_score": round(confidence_score, 4),
            "stage": stage,
            "method": method,
            "alternatives": alternatives,
            "status": status,
        })

    return mappings


# ---------------------------------------------------------------------------
# Lightweight fallback (if real engine can't load)
# ---------------------------------------------------------------------------

def _fallback_schema_mapping(
    raw_df: pd.DataFrame, curated_df: pd.DataFrame
) -> list[dict]:
    """Simple fuzzy-match fallback used only when the real engine is unavailable."""
    raw_cols = list(raw_df.columns)
    curated_cols = list(curated_df.columns)
    norm_curated = {_normalise(c): c for c in curated_cols}
    curated_norms = list(norm_curated.keys())

    mappings: list[dict] = []
    for col in raw_cols:
        norm = _normalise(col)

        if norm in norm_curated:
            mappings.append({
                "raw_column": col,
                "matched_field": norm_curated[norm],
                "confidence_score": 1.0,
                "stage": "stage1",
                "method": "exact",
                "alternatives": [],
                "status": "accepted",
            })
            continue

        fuzzy_matches = process.extract(
            norm, curated_norms, scorer=fuzz.token_sort_ratio, limit=5
        )
        if fuzzy_matches and fuzzy_matches[0][1] >= 60:
            best = fuzzy_matches[0]
            alts = [
                {"field": norm_curated[m[0]], "score": round(m[1] / 100, 3), "method": "fuzzy"}
                for m in fuzzy_matches[1:]
                if m[1] >= 40
            ]
            score = round(best[1] / 100, 3)
            mappings.append({
                "raw_column": col,
                "matched_field": norm_curated[best[0]],
                "confidence_score": score,
                "stage": "stage3",
                "method": "fuzzy_fallback",
                "alternatives": alts,
                "status": "accepted" if score >= THRESHOLD_AUTO_ACCEPT else "pending",
            })
        else:
            mappings.append({
                "raw_column": col,
                "matched_field": None,
                "confidence_score": 0.0,
                "stage": "unmapped",
                "method": None,
                "alternatives": [],
                "status": "pending",
            })

    return mappings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_schema_mapping(
    raw_df: pd.DataFrame,
    curated_df: pd.DataFrame,
    csv_path: Optional[str] = None,
) -> list[dict]:
    """
    Run the schema mapping pipeline using the real SchemaMapEngine.

    Args:
        raw_df:      Raw metadata DataFrame (fallback info)
        curated_df:  Curated reference DataFrame (not used by real engine)
        csv_path:    Path to the raw CSV on disk (needed by SchemaMapEngine)

    Returns:
        List of mapping dicts ready for DB insertion.
    """
    _init_real_engine()

    if _HAS_REAL_ENGINE and csv_path and Path(csv_path).exists():
        try:
            logger.info("Running real SchemaMapEngine on %s", csv_path)
            results_df = _run_real_engine(csv_path)
            mappings = _transform_engine_results(results_df)
            logger.info("Real engine produced %d mappings", len(mappings))
            return mappings
        except Exception as e:
            logger.error("Real engine failed: %s — falling back to lightweight", e)

    return _fallback_schema_mapping(raw_df, curated_df)


def run_ontology_mapping(
    raw_df: pd.DataFrame,
    schema_mappings: list[dict],
) -> list[dict]:
    """
    For each mapped field with ontology definitions, map raw values
    to ontology terms.
    """
    onto_results: list[dict] = []

    for mapping in schema_mappings:
        matched = mapping.get("matched_field")
        if not matched or matched not in ONTOLOGY_MAP:
            continue

        raw_col = mapping["raw_column"]
        if raw_col not in raw_df.columns:
            continue

        value_map = ONTOLOGY_MAP[matched]
        unique_vals = raw_df[raw_col].dropna().unique()

        for val in unique_vals:
            val_lower = str(val).strip().lower()
            if val_lower in value_map:
                term, ont_id = value_map[val_lower]
                score = 1.0
            else:
                known_vals = list(value_map.keys())
                fuzzy_result = process.extractOne(
                    val_lower, known_vals, scorer=fuzz.ratio
                )
                if fuzzy_result and fuzzy_result[1] >= 70:
                    term, ont_id = value_map[fuzzy_result[0]]
                    score = round(fuzzy_result[1] / 100, 3)
                else:
                    term = None
                    ont_id = None
                    score = 0.0

            onto_results.append({
                "field_name": matched,
                "raw_value": str(val),
                "ontology_term": term,
                "ontology_id": ont_id,
                "confidence_score": score,
                "status": "accepted" if score >= 0.9 else "pending",
            })

    return onto_results


def generate_study_id(filename: str) -> str:
    """Create a study ID from the filename."""
    stem = Path(filename).stem
    short_uuid = uuid.uuid4().hex[:8]
    return f"{stem}_{short_uuid}"
