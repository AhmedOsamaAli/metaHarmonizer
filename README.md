# 🔬 MetaHarmonizer

**Automated biomedical metadata harmonization platform for cBioPortal-compatible clinical datasets.**

MetaHarmonizer bridges the gap between raw, inconsistent clinical metadata and standardized, ontology-annotated schemas. It combines a multi-stage ML pipeline with an interactive curator review dashboard, enabling researchers to harmonize metadata at scale while maintaining expert oversight.

> **Demo submission** for [GSoC 2026 — Automated Clinical Metadata Harmonization Dashboard](https://github.com/cBioPortal/GSoC/issues/136)

---

## The Problem

cBioPortal hosts 400+ cancer genomics studies with clinical metadata from diverse sources. Cross-study metadata heterogeneity severely limits analysis:

| Issue | Examples |
|-------|----------|
| **Attribute naming** | `AGE`, `AGE_AT_DIAGNOSIS`, `DIAGNOSIS_AGE` — all mean the same thing |
| **Value encoding** | Sex recorded as `male`, `M`, `1`, `Male`, `MALE` |
| **Treatment synonyms** | 24+ variants: `RADIO_THERAPY`, `Rad`, `XRT`, `Radiation`, `RT` |
| **Staging inconsistency** | `TUMOR_STAGE_2009`, `AJCC_STAGE`, `STAGE`, `PATHOLOGIC_STAGE` |

Manual harmonization does not scale. MetaHarmonizer automates this using a **4-stage cascade pipeline** backed by dictionary matching, ontology resolution, semantic embeddings, and optional LLM inference — then presents results in a curator-friendly dashboard for review and correction.

---

## Dashboard Pages

### 1. Upload

Upload a CSV or TSV file containing raw clinical metadata. The pipeline automatically processes all columns through the 4-stage cascade and returns results in seconds.

![Upload Page](pics/upload_page.png)

---

### 2. Schema Mapping Review

The core curator workspace. Each column mapping displays the suggested standardized field name, confidence score (color-coded), the pipeline stage that produced the match, and up to 4 alternative candidates. Curators can accept, reject, or manually edit any mapping — individually or in batch.

![Schema Mapping Review](pics/schema_mapping.png)

---

### 3. Ontology Value Mapping

View how raw cell values within mapped columns are resolved to standard ontology terms from NCIT, UBERON, and OHMI. Curators can search and browse terms with fuzzy matching to verify or override automated assignments.

![Ontology Mapping](pics/ontlogy_mapping.png)

---

### 4. Quality Dashboard

Monitor harmonization quality at a glance — KPI cards for overall coverage and confidence, a confidence score histogram showing score distribution, stage breakdown charts revealing which pipeline stages contribute most matches, and review progress tracking.

![Quality Dashboard](pics/quality_dashboard.png)

---

### 5. Export

Download results in three formats: harmonized CSV with standardized column names, cBioPortal-compatible TSV with the proper 4-line header format for direct ingestion, and a JSON audit report capturing every mapping decision and curator action.

![Export](pics/export.png)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  Upload → Review → Ontology → Quality → Export       │
│  (TypeScript, Tailwind CSS, Recharts)                │
└──────────────────────┬──────────────────────────────┘
                       │ REST API (JSON)
┌──────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                       │
│  Routers: harmonize, mappings, ontology, quality,    │
│           export                                     │
│  Services: harmonizer (engine wrapper), analytics,   │
│            exporter                                  │
│  Database: SQLite with WAL mode                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│            MetaHarmonizer ML Engine                   │
│  SchemaMapEngine (4-stage cascade)                   │
│  SentenceTransformer embeddings                      │
│  NCI EVS API integration                             │
│  Dictionary + fuzzy matching                         │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, TypeScript, Tailwind CSS, Recharts, Lucide Icons |
| **Backend** | FastAPI, Pydantic v2, Uvicorn |
| **Database** | SQLite (WAL mode, foreign keys, indexes) |
| **ML Engine** | SentenceTransformer (`all-MiniLM-L6-v2`), RapidFuzz, NCI EVS API |

---

## Pipeline Stages

| Stage | Method | Description |
|-------|--------|-------------|
| **Stage 1** | Dict / Fuzzy | Exact and fuzzy name matching against curated standard fields and a ~220-entry alias dictionary (RapidFuzz `token_sort_ratio` ≥ 92%) |
| **Stage 2** | Value / Ontology | Matches by value-distribution similarity via `field_value_dict.json` embeddings (SentenceTransformer cosine ≥ 0.75) and NCI EVS ontology lookups |
| **Stage 3** | Numeric + Semantic | Numeric-family embedding matching with treatment/family boost; semantic cosine similarity across standard fields and aliases |
| **Stage 4** | LLM | On-demand Gemini API inference for ambiguous columns (requires `GEMINI_API_KEY`) |

Columns flow through stages sequentially. A high-confidence match at any stage skips all later stages. Columns that pass all stages without a match are flagged for manual review or LLM rematch.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

# Offline mode (no live API calls, faster startup):
$env:SKIP_NCI_API="1"
# Online mode (live NCI EVS lookups):
# $env:SKIP_NCI_API="0"

uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SKIP_NCI_API` | `0` | Set to `1` to bypass live NCI EVS API calls (offline / fast mode) |
| `GEMINI_API_KEY` | — | Required for Stage 4 LLM matching and `/api/v1/mappings/{id}/llm` |
| `FIELD_VALUE_JSON` | `data/schema/field_value_dict.json` | Override path to value-level ontology dictionary |

---

## API Reference

**Schema Mapping**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/harmonize` | POST | Upload file and run harmonization pipeline |
| `/api/v1/harmonize/{job_id}` | GET | Poll job status and results |
| `/api/v1/studies` | GET | List all studies |
| `/api/v1/mappings/{study_id}` | GET | Get all column mappings for a study |
| `/api/v1/mappings/{study_id}/suggestions` | GET | Low-confidence/unmapped columns with alternatives |
| `/api/v1/mappings/{id}/accept` | POST | Accept a mapping |
| `/api/v1/mappings/{id}/reject` | POST | Reject a mapping |
| `/api/v1/mappings/{id}/edit` | POST | Manually override a mapping |
| `/api/v1/mappings/{id}/llm` | POST | Trigger on-demand LLM rematch (requires `GEMINI_API_KEY`) |
| `/api/v1/mappings/batch` | POST | Batch accept/reject mappings |

**Ontology Value Mapping**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ontology/search` | GET | Fuzzy search across NCIT/UBERON/OHMI terms |
| `/api/v1/ontology/mappings/{study_id}` | GET | Get all value-level ontology mappings |
| `/api/v1/ontology/mappings/{id}/accept` | POST | Accept an ontology assignment |
| `/api/v1/ontology/mappings/{id}/reject` | POST | Reject an ontology assignment |
| `/api/v1/ontology/mappings/{id}` | PATCH | Curator override with custom term/ID |

**Quality & Export**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/quality/{study_id}` | GET | Coverage, confidence, stage breakdown |
| `/api/v1/quality/{study_id}/evaluate` | POST | F1/precision/recall vs ground-truth CSV |
| `/api/v1/export/{study_id}/harmonized` | GET | Harmonized CSV with standardized column names |
| `/api/v1/export/{study_id}/cbioportal` | GET | cBioPortal-compatible TSV (4-line header) |
| `/api/v1/export/{study_id}/report` | GET | JSON audit report |

---

## Project Structure

```
metaHarmonizer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── models.py            # Pydantic request/response schemas
│   │   ├── database.py          # SQLite data layer
│   │   ├── routers/             # API route handlers
│   │   └── services/            # Business logic
│   ├── engine/                  # ML engine (SchemaMapEngine)
│   │   ├── src/models/schema_mapper/
│   │   │   ├── engine.py        # 4-stage cascade
│   │   │   ├── config.py        # Thresholds & model config
│   │   │   ├── loaders/         # Dictionary & value loaders
│   │   │   └── matchers/        # Stage 1–4 matcher classes
│   │   └── data/schema/         # Curated dictionaries & ontology data
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main app with routing
│   │   ├── pages/               # Upload, Review, Ontology, Quality, Export
│   │   ├── components/          # Reusable UI components
│   │   └── api/                 # Typed HTTP client
│   └── package.json
├── pics/                        # Dashboard screenshots
├── metadata_samples/            # Reference & sample data
└── README.md
```

---

## Sample Data

| File | Description |
|------|-------------|
| `metadata_samples/curated_meta.csv` | Reference schema — 37 standardized columns with ontology term IDs |
| `metadata_samples/new_meta.csv` | Raw metadata — 131 heterogeneous columns from multiple studies |

---

## Performance

| Metric | Value |
|--------|-------|
| Upload-to-results (141 columns) | **< 2 second** |
| Cold start (original, incl. model download) | ~235 seconds |
| Cold start (model cached, NCI enabled) | ~120 seconds |
| Optimization | 99%+ latency reduction via engine caching, background pre-warming |

---

## Acknowledgments

- [MetaHarmonizer Engine](https://github.com/shbrief/MetaHarmonizer) — Core ML pipeline for schema mapping
- [cBioPortal](https://www.cbioportal.org/) — Target schema standard for cancer genomics
- [NCI Thesaurus (NCIt)](https://ncithesaurus.nci.nih.gov/) — Biomedical ontology for value normalization

