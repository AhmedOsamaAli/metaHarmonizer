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
# Cached field_value_dict.json (loaded once on first ontology mapping call)
_cached_field_value_dict: dict | None = None


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
# Static NCIT term → code lookup table.
# These are canonical NCIT codes for the most common terms that appear in
# field_value_dict.json and ONTOLOGY_MAP.  Used when the NCI EVS API is
# disabled and nci_cache.json has not yet been populated.
# ---------------------------------------------------------------------------

_STATIC_NCIT: dict[str, str] = {
    # sex
    "male": "C20197", "female": "C16576",
    # vital_status
    "alive": "C37987", "dead": "C28554",
    # cancer_status
    "tumor free": "C17629", "with tumor": "C13104",
    # specimen_type
    "biopsy specimen": "C18009", "bone marrow aspirate": "C13286",
    "cell line": "C12508", "peripheral blood": "C25269",
    "resection": "C15189", "xenograft": "C19302",
    "organoid": "C172923", "leukocyte sample": "C12529",
    # sample_type
    "primary neoplasm": "C8509", "metastatic neoplasm": "C3261",
    "recurrent neoplasm": "C4798", "neoplasm": "C3262",
    "benign neoplasm": "C3677",
    # age_group
    "adult": "C17600", "adolescent": "C27954", "infant": "C27956",
    "elderly": "C9369", "children 2-11 years old": "C89831",
    # ancestry
    "african ancestry": "C43234", "asian ancestry": "C43469",
    "european ancestry": "C43851", "indigenous american": "C43462",
    # country (ISO3 → NCIT; canonical name also included)
    "australia": "C16311", "aus": "C16311",
    "brazil": "C16374", "bra": "C16374",
    "canada": "C16482", "can": "C16482",
    "china": "C16448", "chn": "C16448",
    "denmark": "C16500", "dnk": "C16500",
    "finland": "C16586", "fin": "C16586",
    "france": "C16592", "fra": "C16592",
    "germany": "C16636", "deu": "C16636",
    "india": "C16726", "ind": "C16726",
    "italy": "C16761", "ita": "C16761",
    "japan": "C16769", "jpn": "C16769",
    "korea, republic of": "C17202", "kor": "C17202",
    "netherlands": "C16903", "nld": "C16903",
    "poland": "C16954", "pol": "C16954",
    "sweden": "C17180", "swe": "C17180",
    "united kingdom": "C17234", "gbr": "C17234",
    "united states": "C17233", "usa": "C17233",
    "viet nam": "C17239", "vnm": "C17239",
    "singapore": "C17132", "sgp": "C17132",
    # body_site
    "feces": "UBERON:0001988", "stool": "UBERON:0001988",
    "blood": "UBERON:0000178", "colon": "UBERON:0001155",
    # disease
    "adenoma": "C3220",
    "colorectal cancer": "C9382", "crc": "C9382",
    "inflammatory bowel disease": "C3138", "ibd": "C3138",
    "crohn disease": "C2965", "cd": "C2965",
    "ulcerative colitis": "C3343", "uc": "C3343",
    "type 1 diabetes": "C2986", "t1d": "C2986",
    "type 2 diabetes": "C26747", "t2d": "C26747",
    # study_design
    "case-control": "C15197",
    # treatment_type (a subset – there are 100 values; key ones below)
    "surgery": "C17173", "chemotherapy": "C15632", "radiation": "C15313",
    "immunotherapy": "C15262",
}

# ---------------------------------------------------------------------------
# Ontology value mappings kept for legacy fallback + ontology router index.
# The live run_ontology_mapping() now uses field_value_dict.json (broader).
# ---------------------------------------------------------------------------

ONTOLOGY_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "body_site": {
        "stool": ("feces", "UBERON:0001988"),
        "feces": ("feces", "UBERON:0001988"),
        "blood": ("Blood", "UBERON:0000178"),
        "colon": ("Colon", "UBERON:0001155"),
        "liver": ("Liver", "UBERON:0002107"),
        "lung": ("Lung", "UBERON:0002048"),
        "skin": ("Skin", "UBERON:0002097"),
    },
    "sex": {
        "male": ("Male", "NCIT:C20197"),
        "female": ("Female", "NCIT:C16576"),
        "m": ("Male", "NCIT:C20197"),
        "f": ("Female", "NCIT:C16576"),
        "1": ("Male", "NCIT:C20197"),
        "2": ("Female", "NCIT:C16576"),
    },
    "country": {
        "can": ("Canada", "NCIT:C16482"),
        "canada": ("Canada", "NCIT:C16482"),
        "usa": ("United States", "NCIT:C17233"),
        "us": ("United States", "NCIT:C17233"),
        "united states": ("United States", "NCIT:C17233"),
        "italy": ("Italy", "NCIT:C16761"),
        "ita": ("Italy", "NCIT:C16761"),
        "chn": ("China", "NCIT:C16448"),
        "china": ("China", "NCIT:C16448"),
        "gbr": ("United Kingdom", "NCIT:C17234"),
        "uk": ("United Kingdom", "NCIT:C17234"),
        "deu": ("Germany", "NCIT:C16636"),
        "germany": ("Germany", "NCIT:C16636"),
        "fra": ("France", "NCIT:C16592"),
        "france": ("France", "NCIT:C16592"),
        "aus": ("Australia", "NCIT:C16311"),
        "australia": ("Australia", "NCIT:C16311"),
        "swe": ("Sweden", "NCIT:C17180"),
        "sweden": ("Sweden", "NCIT:C17180"),
        "nld": ("Netherlands", "NCIT:C16903"),
        "esp": ("Spain", "NCIT:C17152"),
        "spain": ("Spain", "NCIT:C17152"),
        "jpn": ("Japan", "NCIT:C16769"),
        "japan": ("Japan", "NCIT:C16769"),
        "kor": ("South Korea", "NCIT:C17202"),
        "ind": ("India", "NCIT:C16726"),
        "india": ("India", "NCIT:C16726"),
        "bra": ("Brazil", "NCIT:C16374"),
        "brazil": ("Brazil", "NCIT:C16374"),
        "dnk": ("Denmark", "NCIT:C16500"),
        "fin": ("Finland", "NCIT:C16586"),
        "sgp": ("Singapore", "NCIT:C17132"),
        "vnm": ("Viet Nam", "NCIT:C17239"),
        "pol": ("Poland", "NCIT:C16954"),
    },
    "disease": {
        "adenoma": ("Adenoma", "NCIT:C3220"),
        "healthy": ("Healthy Subject", "NCIT:C35429"),
        "normal": ("Normal", "NCIT:C14165"),
        "crc": ("Colorectal Cancer", "NCIT:C9382"),
        "colorectal cancer": ("Colorectal Cancer", "NCIT:C9382"),
        "ibd": ("Inflammatory Bowel Disease", "NCIT:C3138"),
        "cd": ("Crohn Disease", "NCIT:C2965"),
        "crohn disease": ("Crohn Disease", "NCIT:C2965"),
        "uc": ("Ulcerative Colitis", "NCIT:C3343"),
        "ulcerative colitis": ("Ulcerative Colitis", "NCIT:C3343"),
        "t1d": ("Type 1 Diabetes Mellitus", "NCIT:C2986"),
        "t2d": ("Type 2 Diabetes Mellitus", "NCIT:C26747"),
    },
    "age_group": {
        "adult": ("Adult", "NCIT:C17600"),
        "adolescent": ("Adolescent", "NCIT:C27954"),
        "senior": ("Senior", "NCIT:C25195"),
        "elderly": ("Elderly", "NCIT:C9369"),
        "infant": ("Infant", "NCIT:C27956"),
        "child": ("Child", "NCIT:C16423"),
        "newborn": ("Newborn", "NCIT:C14174"),
        "schoolage": ("School Age Child", "NCIT:C89831"),
        "children 2-11 years old": ("School Age Child", "NCIT:C89831"),
    },
    "vital_status": {
        "alive": ("Alive", "NCIT:C37987"),
        "dead": ("Dead", "NCIT:C28554"),
        "deceased": ("Dead", "NCIT:C28554"),
        "living": ("Alive", "NCIT:C37987"),
        "dead with tumor": ("Dead", "NCIT:C28554"),
    },
    "cancer_status": {
        "tumor free": ("Tumor Status - Free", "NCIT:C17629"),
        "with tumor": ("Tumor Status - With Tumor", "NCIT:C13104"),
        "ned": ("No Evidence of Disease", "NCIT:C5641"),
        "no evidence of disease": ("No Evidence of Disease", "NCIT:C5641"),
    },
    "specimen_type": {
        "biopsy": ("Biopsy Specimen", "NCIT:C18009"),
        "biopsy specimen": ("Biopsy Specimen", "NCIT:C18009"),
        "blood": ("Peripheral Blood", "NCIT:C25269"),
        "peripheral blood": ("Peripheral Blood", "NCIT:C25269"),
        "resection": ("Resection Specimen", "NCIT:C15189"),
        "cell line": ("Cell Line", "NCIT:C12508"),
        "xenograft": ("Xenograft", "NCIT:C19302"),
        "organoid": ("Organoid", "NCIT:C172923"),
    },
    "ancestry": {
        "african": ("African Ancestry", "NCIT:C43234"),
        "african ancestry": ("African Ancestry", "NCIT:C43234"),
        "african american": ("African Ancestry", "NCIT:C43234"),
        "asian": ("Asian Ancestry", "NCIT:C43469"),
        "asian ancestry": ("Asian Ancestry", "NCIT:C43469"),
        "european": ("European Ancestry", "NCIT:C43851"),
        "european ancestry": ("European Ancestry", "NCIT:C43851"),
        "caucasian": ("European Ancestry", "NCIT:C43851"),
        "white": ("European Ancestry", "NCIT:C43851"),
        "hispanic": ("Latin or Admixed American", "NCIT:C43462"),
        "latino": ("Latin or Admixed American", "NCIT:C43462"),
    },
    "sample_type": {
        "primary": ("Primary Neoplasm", "NCIT:C8509"),
        "primary neoplasm": ("Primary Neoplasm", "NCIT:C8509"),
        "metastatic": ("Metastatic Neoplasm", "NCIT:C3261"),
        "metastatic neoplasm": ("Metastatic Neoplasm", "NCIT:C3261"),
        "recurrent": ("Recurrent Neoplasm", "NCIT:C4798"),
        "recurrent neoplasm": ("Recurrent Neoplasm", "NCIT:C4798"),
        "benign": ("Benign Neoplasm", "NCIT:C3677"),
    },
    "study_design": {
        "case-control": ("Case-Control Study", "NCIT:C15197"),
        "observational": ("Observational Study", "NCIT:C16084"),
        "longitudinal": ("Longitudinal Study", "NCIT:C15273"),
        "cross-sectional": ("Cross-Sectional Study", "NCIT:C15208"),
        "cross-sectional observational": ("Cross-Sectional Study", "NCIT:C15208"),
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

    # The NCI EVS REST API (api-evsrest.nci.nih.gov) is called by Stage 2's
    # OntologyMatcher to classify values such as disease names, body sites,
    # and treatment names into curated fields.
    #
    # Set SKIP_NCI_API=1 in the environment to bypass all API calls (e.g.
    # during offline tests or when NCI is unreachable).  By default the API
    # is enabled and results are accumulated in nci_cache.json so subsequent
    # runs of the same values are instant.
    if os.getenv("SKIP_NCI_API", "").strip() in ("1", "true", "yes"):
        if hasattr(engine, "nci_client"):
            engine.nci_client.search_candidates = lambda *a, **kw: []
        logger.info("NCI EVS API disabled via SKIP_NCI_API env var")

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
        # Only save entries where we actually got a code back (skip None = not-found
        # entries so they are retried on the next run without the API silenced).
        real_t2c = {k: v for k, v in nci.term2code.items() if v is not None}
        cache_data = {
            "term2code": real_t2c,
            "code2category": {k: v for k, v in nci.code2category.items()},
        }
        _NCI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_NCI_CACHE_PATH, "w") as f:
            _json.dump(cache_data, f)
        logger.info("Saved NCI cache (%d terms, %d codes)", len(real_t2c), len(nci.code2category))
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
        # Only load real codes — skip None entries that were poisoned while the
        # API was silenced so they get re-looked-up on the next run.
        t2c = {k: v for k, v in cache_data.get("term2code", {}).items() if v is not None}
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


def _load_field_value_dict() -> dict[str, list[str]]:
    """
    Load field_value_dict.json from the engine data directory.
    Returns {field_name: [canonical_value, ...]} for 14 curated fields.
    Cached at module level after first call.
    """
    global _cached_field_value_dict
    if _cached_field_value_dict is not None:
        return _cached_field_value_dict

    path = _REPO_DIR / "data" / "schema" / "field_value_dict.json"
    if path.exists():
        try:
            with open(path) as f:
                _cached_field_value_dict = _json.load(f)
            logger.info(
                "Loaded field_value_dict: %d fields",
                len(_cached_field_value_dict),
            )
        except Exception as e:
            logger.warning("Could not load field_value_dict.json: %s", e)
            _cached_field_value_dict = {}
    else:
        logger.warning("field_value_dict.json not found at %s", path)
        _cached_field_value_dict = {}
    return _cached_field_value_dict


def _resolve_ncit_id(term: str, nci_term2code: dict, field: str) -> str | None:
    """
    Resolve a canonical term name to a NCIT/UBERON ID.
    Lookup order:
      1. Static _STATIC_NCIT table (term lowercase key)
      2. Persisted NCI API cache (nci_term2code, term lowercase key)
    Returns fully-qualified ID string (e.g. "NCIT:C20197") or None.
    """
    key = term.strip().lower()
    # 1. Static table
    code = _STATIC_NCIT.get(key)
    if code:
        prefix = "UBERON" if code.startswith("UBERON") else "NCIT"
        return code if ":" in code else f"{prefix}:{code}"

    # 2. NCI API cache (populated by live API calls if ever enabled)
    code = nci_term2code.get(key)
    if code:
        return f"NCIT:{code}"

    # 3. Check ONTOLOGY_MAP legacy entries for this term
    for _field, vmap in ONTOLOGY_MAP.items():
        if _field != field:
            continue
        for _raw, (mapped_term, mapped_id) in vmap.items():
            if mapped_term.lower() == key and mapped_id:
                return mapped_id

    return None


def run_ontology_mapping(
    raw_df: pd.DataFrame,
    schema_mappings: list[dict],
) -> list[dict]:
    """
    Map raw column values to canonical ontology terms and IDs.

    Primary source: engine/data/schema/field_value_dict.json (14 fields,
    real curated vocabulary including treatment_type, vital_status, ancestry,
    cancer_status, specimen_type, sample_type, country, sex, etc.).

    Supplemental source: ONTOLOGY_MAP (covers body_site, disease, age_group,
    sample_type additions, ancestry, vital_status, cancer_status, specimen_type,
    study_design — extends the value dict coverage).

    Matching:
      - Exact lowercase match → score 1.0
      - RapidFuzz token_sort_ratio ≥ 70 → score proportional to ratio
      - Below 70 → term=None, id=None, score=0.0 (recorded for audit)

    NCIT IDs are resolved via _STATIC_NCIT → NCI API cache → ONTOLOGY_MAP fallback.
    """
    onto_results: list[dict] = []

    # Load primary value dict (field → [canonical values])
    field_value_dict = _load_field_value_dict()

    # Load NCI API cache for dynamic ID lookup
    nci_term2code: dict[str, str] = {}
    try:
        if _NCI_CACHE_PATH.exists():
            with open(_NCI_CACHE_PATH) as f:
                cache_data = _json.load(f)
            nci_term2code = {
                k.lower(): v for k, v in cache_data.get("term2code", {}).items()
            }
    except Exception as e:
        logger.debug("Could not read NCI cache for ontology lookup: %s", e)

    # Merge: primary value_dict + ONTOLOGY_MAP (keyed by lowercase canonical value)
    # Structure: combined_map[field][raw_lower] = (canonical_term, resolved_id_or_None)
    def _build_combined_map() -> dict[str, dict[str, tuple[str, str | None]]]:
        combined: dict[str, dict[str, tuple[str, str | None]]] = {}

        # From field_value_dict.json — canonical terms, IDs resolved lazily
        for field, values in field_value_dict.items():
            combined.setdefault(field, {})
            for v in values:
                v_lower = v.strip().lower()
                resolved_id = _resolve_ncit_id(v, nci_term2code, field)
                combined[field][v_lower] = (v, resolved_id)

        # From ONTOLOGY_MAP — adds body_site, disease, and supplemental entries
        # for fields already in value_dict (these have curated NCIT IDs)
        for field, vmap in ONTOLOGY_MAP.items():
            combined.setdefault(field, {})
            for raw_lower, (term, ont_id) in vmap.items():
                # Don't overwrite a value_dict entry that already has an ID
                existing = combined[field].get(raw_lower)
                if existing is None or (existing[1] is None and ont_id):
                    combined[field][raw_lower] = (term, ont_id if ont_id else None)

        return combined

    combined_map = _build_combined_map()

    for mapping in schema_mappings:
        matched = mapping.get("matched_field")
        if not matched or matched not in combined_map:
            continue

        raw_col = mapping["raw_column"]
        if raw_col not in raw_df.columns:
            continue

        value_map = combined_map[matched]
        known_lower_list = list(value_map.keys())
        unique_vals = raw_df[raw_col].dropna().unique()

        for val in unique_vals:
            val_lower = str(val).strip().lower()

            if val_lower in value_map:
                term, ont_id = value_map[val_lower]
                score = 1.0
            else:
                # Fuzzy match raw value against known canonical values
                fuzzy_result = process.extractOne(
                    val_lower, known_lower_list, scorer=fuzz.token_sort_ratio
                )
                if fuzzy_result and fuzzy_result[1] >= 70:
                    matched_key = fuzzy_result[0]
                    term, ont_id = value_map[matched_key]
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


# ---------------------------------------------------------------------------
# Stage 4 — on-demand LLM match for a single column
# ---------------------------------------------------------------------------

def run_llm_match_for_column(csv_path: str, raw_column: str) -> list[dict]:
    """
    Run the LLMMatcher (Stage 4 / Gemini) for a single column on-demand.

    Returns a list of {"field": str, "confidence": float, "reasoning": str} dicts,
    sorted by confidence descending.  Raises RuntimeError on configuration
    or API errors so callers can convert them to HTTP 4xx/5xx.
    """
    import os

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.  Add it to the backend .env file to use "
            "on-demand LLM matching."
        )

    # Build / reuse an engine instance for this CSV
    try:
        engine = _create_engine(csv_path)
        _reset_engine_for_file(engine, csv_path)  # loads the CSV into engine.df
    except Exception as exc:
        raise RuntimeError(f"Failed to load CSV for LLM matcher: {exc}") from exc

    # Lazy import to avoid failing at startup when google-genai is absent
    try:
        from engine.src.models.schema_mapper.matchers.stage4_matchers import LLMMatcher
    except ImportError as exc:
        raise RuntimeError(
            "google-genai package is not installed.  "
            "Run: pip install google-genai"
        ) from exc

    matcher = LLMMatcher(engine)
    results_raw: list[tuple[str, float, str]] = matcher.match(raw_column)

    # Convert (field, score, source) tuples → dict list for the API response
    output = []
    for field, score, source in results_raw:
        output.append({"field": field, "confidence": round(score, 4), "reasoning": source})
    return output
