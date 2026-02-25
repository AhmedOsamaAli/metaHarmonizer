# 🔬 MetaHarmonizer

**Automated biomedical metadata harmonization platform for cBioPortal-compatible clinical datasets.**

MetaHarmonizer bridges the gap between raw, inconsistent clinical metadata and standardized, ontology-annotated schemas. It combines a multi-stage ML pipeline with an interactive curator review dashboard, enabling researchers to harmonize metadata at scale while maintaining expert oversight.

> **Demo submission** for [GSoC 2026 — Automated Clinical Metadata Harmonization Dashboard](https://github.com/cBioPortal/GSoC/issues/136)

---

## Problem

cBioPortal hosts 400+ cancer genomics studies with clinical metadata from diverse sources. Metadata heterogeneity across studies severely limits cross-study analysis:

- Treatment appears as 24+ variants: `RADIO_THERAPY`, `Rad`, `XRT`, `Radiation`…
- Age attributes vary: `AGE`, `AGE_AT_DIAGNOSIS`, `DIAGNOSIS_AGE`…
- Staging is inconsistent: `TUMOR_STAGE_2009`, `AJCC_STAGE`, `PATHOLOGIC_STAGE`…

Manual harmonization cannot scale. MetaHarmonizer automates this using a **4-stage cascade pipeline** backed by dictionary matching, ontology resolution, semantic embeddings, and optional LLM inference — then presents results in a curator-friendly dashboard for review.

---

## Key Features

### Harmonization Engine
- **4-Stage Cascade Pipeline**: Dict/Fuzzy → Value/Ontology → Semantic (SentenceTransformer) → LLM
- **Ontology Value Normalization**: Maps raw values to standard terms (NCIT, UBERON, OHMI)
- **Confidence Scoring**: Each mapping includes a confidence score and the producing stage
- **Top-K Alternatives**: Returns up to 5 ranked alternative matches per column for curator review

### Curator Review Dashboard
- **Interactive Mapping Review**: Accept, reject, or manually edit automated mappings
- **Batch Operations**: Accept or reject multiple mappings at once
- **Ontology Browser**: Search and browse NCIT, UBERON, OHMI terms with fuzzy matching
- **Quality Analytics**: Confidence distributions, stage breakdowns, coverage metrics, progress tracking
- **Audit Trail**: Full logging of all curator actions for reproducibility

### Export & Integration
- **Harmonized CSV**: Download data with standardized column names
- **cBioPortal Format**: Tab-separated export with proper header lines for direct cBioPortal ingestion
- **JSON Audit Report**: Complete mapping report with provenance and curator decisions

### Performance
- **Engine Caching**: SentenceTransformer model and dictionaries persist across requests
- **Pre-warming**: Background model loading at startup — first upload is fast
- **NCI Cache Persistence**: API responses cached to disk, cutting repeat startup time

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

| Layer        | Technology                                                          |
|-------------|---------------------------------------------------------------------|
| **Frontend** | React 18, TypeScript, Tailwind CSS, Recharts, Lucide Icons          |
| **Backend**  | FastAPI, Pydantic v2, Uvicorn                                       |
| **Database** | SQLite (WAL mode, foreign keys, indexes)                            |
| **ML Engine**| SentenceTransformer (`all-MiniLM-L6-v2`), RapidFuzz, NCI EVS API    |

**Technical decisions rationale** — see the [GSoC Proposal](GSoC_Proposal.md) for detailed reasoning behind every technology choice.

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
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs

---

## Usage Workflow

### 1. Upload Metadata
Upload a CSV/TSV file containing raw clinical metadata. The pipeline automatically processes all columns through the 4-stage cascade.

### 2. Review Mappings
Each column mapping shows:
- **Matched Field** — the suggested standardized column name
- **Confidence Score** — how confident the model is (color-coded: green ≥90%, yellow 50–90%, red <50%)
- **Stage** — which pipeline stage produced the match (S1–S4)
- **Alternatives** — up to 4 alternative matches to choose from

Accept high-confidence mappings, reject incorrect ones, or manually edit to assign the correct field.

### 3. Browse Ontology Mappings
View how raw values within mapped columns are resolved to ontology terms (NCIT, UBERON, OHMI).

### 4. Quality Dashboard
Monitor harmonization quality with:
- Coverage metrics (mapped vs. unmapped columns)
- Confidence score distribution histogram
- Stage breakdown (which stages contribute most matches)
- Review progress tracking

### 5. Export
Download results in three formats:
- **Harmonized CSV** — data with standardized column names
- **cBioPortal Clinical** — tab-separated format ready for cBioPortal import
- **Mapping Report** — JSON audit trail of all mappings and curator decisions

---

## Pipeline Stages

| Stage | Method | Description |
|-------|--------|-------------|
| **Stage 1** | Dict / Fuzzy | Exact and near-exact name matching via curated dictionaries (RapidFuzz token_sort ≥92%) |
| **Stage 2** | Value / Ontology | Matches columns by value distributions and NCI EVS ontology lookups |
| **Stage 3** | Semantic | SentenceTransformer (`all-MiniLM-L6-v2`) cosine similarity between column names |
| **Stage 4** | LLM | Optional Gemini API inference for ambiguous columns (disabled by default) |

Columns flow through stages sequentially. If a stage produces a high-confidence match, later stages are skipped. Unmatched columns are flagged for manual review.

---

## API Reference

The backend exposes a RESTful API documented via OpenAPI/Swagger at `/docs`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/harmonize` | POST | Upload file and run harmonization pipeline |
| `/api/v1/harmonize/{job_id}` | GET | Get results for a harmonization job |
| `/api/v1/studies` | GET | List all studies |
| `/api/v1/mappings/{study_id}` | GET | Get mappings for a study |
| `/api/v1/mappings/{id}/accept` | POST | Accept a mapping |
| `/api/v1/mappings/{id}/reject` | POST | Reject a mapping |
| `/api/v1/mappings/{id}/edit` | POST | Manually edit a mapping |
| `/api/v1/mappings/batch` | POST | Batch accept/reject mappings |
| `/api/v1/ontology/search` | GET | Search ontology terms |
| `/api/v1/ontology/mappings/{study_id}` | GET | Get ontology mappings |
| `/api/v1/quality/{study_id}` | GET | Get quality metrics |
| `/api/v1/export/{study_id}/harmonized` | GET | Export harmonized CSV |
| `/api/v1/export/{study_id}/cbioportal` | GET | Export cBioPortal format |
| `/api/v1/export/{study_id}/report` | GET | Export JSON audit report |

---

## Project Structure

```
metaHarmonizer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── models.py            # Pydantic request/response schemas
│   │   ├── database.py          # SQLite data layer (4 tables, 17 functions)
│   │   ├── routers/             # API route handlers
│   │   │   ├── harmonize.py     # Upload & pipeline execution
│   │   │   ├── mappings.py      # Curator review CRUD + batch ops
│   │   │   ├── ontology.py      # Ontology search & browse
│   │   │   ├── quality.py       # Analytics metrics
│   │   │   └── export.py        # Data export endpoints
│   │   └── services/            # Business logic
│   │       ├── harmonizer.py    # ML engine wrapper + ontology mapping
│   │       ├── analytics.py     # Quality metric computation
│   │       └── exporter.py      # Export format generators
│   ├── engine/                  # ML engine (SchemaMapEngine)
│   │   ├── src/
│   │   │   ├── models/schema_mapper/
│   │   │   │   ├── engine.py    # Main SchemaMapEngine class (4-stage cascade)
│   │   │   │   ├── config.py    # Thresholds & model config
│   │   │   │   ├── loaders/     # Dictionary & value loaders
│   │   │   │   └── matchers/    # Stage 1–4 matcher classes
│   │   │   ├── utils/           # Schema mapping utilities
│   │   │   └── CustomLogger/    # Structured logging
│   │   └── data/
│   │       ├── schema/          # Curated dictionaries & ontology data
│   │       └── schema_mapping_eval/  # Pipeline evaluation outputs
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main app with routing (5 pages)
│   │   ├── pages/               # Upload, Review, Ontology, Quality, Export
│   │   ├── components/          # ConfidenceBadge, FileUploader, StageBadge, StatusBadge
│   │   └── api/                 # Typed HTTP client (12 functions, 10 interfaces)
│   └── package.json
├── metadata_samples/            # Reference & sample data
│   ├── curated_meta.csv         # 37 standardized columns (reference schema)
│   └── new_meta.csv             # 131 raw columns (test data)
├── GSoC_Proposal.md             # Full GSoC 2026 proposal
└── README.md
```

---

## Sample Data

| File | Description |
|------|-------------|
| `metadata_samples/curated_meta.csv` | Reference schema with 37 standardized columns (cBioPortal-compatible), including ontology term IDs |
| `metadata_samples/new_meta.csv` | Raw metadata with 131 heterogeneous columns from multiple studies |

---

## Acknowledgments

- [MetaHarmonizer Engine](https://github.com/shbrief/MetaHarmonizer) — Core ML pipeline for schema mapping
- [cBioPortal](https://www.cbioportal.org/) — Target schema standard for cancer genomics
- [NCI Thesaurus (NCIt)](https://ncithesaurus.nci.nih.gov/) — Biomedical ontology for value normalization

---

## License

This project is provided as-is for research and educational purposes.
