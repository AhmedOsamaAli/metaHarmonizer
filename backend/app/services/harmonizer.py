"""Dashboard-owned value-to-ontology helpers (the engine pipeline lives behind
``app.engine_adapter``).

Exposes:
- ``ONTOLOGY_MAP``          curated raw→canonical mappings + fallback source.
- ``_STATIC_NCIT``          canonical NCIT/UBERON code lookup table.
- ``_load_field_value_dict``  field → canonical values (field_value_dict.json).
- ``run_ontology_mapping``  the dashboard's value-mapping routine.
- ``generate_study_id``     filename → unique study id.
"""

from __future__ import annotations

import json as _json
import logging
import re
import uuid
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


# Paths

# backend/data/ — dashboard-owned read-only assets (curated value dictionaries,
# the NCI EVS cache, etc.). Survives removal of the legacy vendored engine.
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SCHEMA_DIR = _DATA_DIR / "schema"
_NCI_CACHE_PATH = _DATA_DIR / "nci_cache.json"


# Static NCIT term → code lookup table. Canonical codes for the common terms in
# field_value_dict.json / ONTOLOGY_MAP; first lookup before the NCI EVS cache.

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
# The live run_ontology_mapping() also uses field_value_dict.json (broader).
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


# Confidence thresholds (used by run_ontology_mapping)
THRESHOLD_AUTO_ACCEPT = 0.90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(name: str) -> str:
    """Lowercase, strip, replace separators with underscore."""
    s = name.strip().lower()
    s = re.sub(r"[\s\-\.]+", "_", s)
    return s


# Cached field_value_dict.json (loaded once on first ontology mapping call)
_cached_field_value_dict: dict | None = None


def _load_field_value_dict() -> dict[str, list[str]]:
    """
    Load field_value_dict.json from backend/data/schema/.

    Returns {field_name: [canonical_value, ...]} for the curated fields.
    Cached at module level after first call.
    """
    global _cached_field_value_dict
    if _cached_field_value_dict is not None:
        return _cached_field_value_dict

    path = _SCHEMA_DIR / "field_value_dict.json"
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


def supports_ontology_mapping(field: str | None) -> bool:
    if not field:
        return False
    key = _normalise(field)
    return key in ONTOLOGY_MAP or key in {
        _normalise(name) for name in _load_field_value_dict()
    }


def _resolve_ncit_id(term: str, nci_term2code: dict, field: str) -> str | None:
    """
    Resolve a canonical term name to a NCIT/UBERON ID.
    Lookup order:
      1. Static _STATIC_NCIT table (term lowercase key)
      2. Persisted NCI API cache (nci_term2code, term lowercase key)
      3. ONTOLOGY_MAP for the same field.
    """
    key = term.strip().lower()

    # 1. Static table
    code = _STATIC_NCIT.get(key)
    if code:
        prefix = "UBERON" if code.startswith("UBERON") else "NCIT"
        return code if ":" in code else f"{prefix}:{code}"

    # 2. NCI API cache (populated by previous live API runs)
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

    Primary source: backend/data/schema/field_value_dict.json (curated values
    for fields like treatment_type, vital_status, ancestry, cancer_status,
    specimen_type, sample_type, country, sex, …).

    Supplemental source: ONTOLOGY_MAP (covers body_site, disease, age_group,
    sample_type additions, ancestry, vital_status, cancer_status, specimen_type,
    study_design — extends the value-dict coverage).

    Matching:
      - Exact lowercase match → score 1.0
      - RapidFuzz token_sort_ratio ≥ 70 → score proportional to ratio
      - Below 70 → term=None, id=None, score=0.0 (recorded for audit)

    NCIT IDs are resolved via _STATIC_NCIT → NCI API cache → ONTOLOGY_MAP fallback.
    """
    onto_results: list[dict] = []

    field_value_dict = _load_field_value_dict()

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

    # Merge: primary value_dict + ONTOLOGY_MAP (keyed by lowercase canonical value).
    # Structure: combined_map[field][raw_lower] = (canonical_term, resolved_id_or_None)
    def _build_combined_map() -> dict[str, dict[str, tuple[str, str | None]]]:
        combined: dict[str, dict[str, tuple[str, str | None]]] = {}

        for field, values in field_value_dict.items():
            combined.setdefault(field, {})
            for v in values:
                v_lower = v.strip().lower()
                resolved_id = _resolve_ncit_id(v, nci_term2code, field)
                combined[field][v_lower] = (v, resolved_id)

        for field, vmap in ONTOLOGY_MAP.items():
            combined.setdefault(field, {})
            for raw_lower, (term, ont_id) in vmap.items():
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
                "status": "accepted" if score >= THRESHOLD_AUTO_ACCEPT else "pending",
            })

    return onto_results


def generate_study_id(filename: str) -> str:
    """Create a study ID from the filename."""
    stem = Path(filename).stem
    short_uuid = uuid.uuid4().hex[:8]
    return f"{stem}_{short_uuid}"
