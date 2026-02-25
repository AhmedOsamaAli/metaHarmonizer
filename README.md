# 🔬 MetaHarmonizer

**Automated biomedical metadata harmonization platform for cBioPortal-compatible clinical datasets.**

MetaHarmonizer bridges the gap between raw, inconsistent clinical metadata and standardized, ontology-annotated schemas. It combines a multi-stage ML pipeline with an interactive curator review dashboard, enabling researchers to harmonize metadata at scale while maintaining expert oversight.

---

## Problem

Biomedical research datasets come with heterogeneous metadata — column names like `gender`, `sex`, `M/F`, or `biological_sex` all represent the same concept. Manually mapping hundreds of columns across dozens of studies to a curated schema is time-consuming, error-prone, and doesn't scale.

MetaHarmonizer automates this process using a **4-stage cascade pipeline** backed by dictionary matching, ontology resolution, semantic embeddings, and optional LLM inference — then presents results in a curator-friendly dashboard for review.

---

## Key Features

### Harmonization Engine
- **4-Stage Cascade Pipeline**: Dict/Fuzzy → Value/Ontology → Semantic (SentenceTransformer) → LLM
- **Ontology Value Normalization**: Maps raw values to standard ontology terms (NCIT, UBERON, OHMI)
- **Confidence Scoring**: Each mapping includes a confidence score and the stage that produced it
- **Top-K Alternatives**: Returns up to 5 ranked alternative matches per column for curator review

### Curator Review Dashboard
- **Interactive Mapping Review**: Accept, reject, or manually edit automated mappings
- **Batch Operations**: Accept or reject multiple mappings at once
- **Ontology Browser**: Search and browse NCIT, UBERON, and OHMI ontology terms with fuzzy matching
- **Quality Analytics**: Confidence distributions, stage breakdowns, coverage metrics, and progress tracking
- **Audit Trail**: Full logging of all curator actions for reproducibility

### Export & Integration
- **Harmonized CSV**: Download data with standardized column names
- **cBioPortal Format**: Tab-separated export with proper header lines for direct cBioPortal ingestion
- **JSON Audit Report**: Complete mapping report with provenance and curator decisions

### Performance
- **Engine Caching**: SentenceTransformer model and dictionaries persist across requests
- **Pre-warming**: Background model loading at startup — first upload is fast
- **NCI Cache Persistence**: API responses are cached to disk, cutting repeat startup time

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
| **Database** | SQLite (WAL mode, foreign keys)                                     |
| **ML Engine**| SentenceTransformer, RapidFuzz, NCI EVS API, Pandas                 |
| **Infra**    | Local dev servers (Uvicorn + Vite)                                   |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### Setup

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate # source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

The frontend dev server runs at http://localhost:5173 and proxies API calls to the backend.

---

## Usage

### 1. Upload Metadata
Upload a CSV/TSV file containing raw clinical metadata. The pipeline automatically processes all columns through the 4-stage cascade.

### 2. Review Mappings
Each column mapping shows:
- **Matched Field**: The suggested standardized column name
- **Confidence Score**: How confident the model is (color-coded)
- **Stage**: Which pipeline stage produced the match (S1–S4)
- **Alternatives**: Up to 4 alternative matches to choose from

Accept high-confidence mappings, reject incorrect ones, or manually edit to assign the correct field.

### 3. Browse Ontology Mappings
View how raw values within mapped columns are resolved to ontology terms (NCIT, UBERON, OHMI).

### 4. Quality Dashboard
Monitor harmonization quality with:
- Coverage metrics (mapped vs. unmapped columns)
- Confidence score distribution
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
| **Stage 1** | Dict / Fuzzy | Exact and near-exact name matching via dictionaries |
| **Stage 2** | Value / Ontology | Matches columns based on their value distributions and ontology lookups |
| **Stage 3** | Semantic | SentenceTransformer embedding similarity between column names |
| **Stage 4** | LLM | Optional large language model inference for ambiguous columns |

Columns are processed through stages sequentially. If a stage produces a high-confidence match, later stages are skipped. Unmatched columns are flagged for manual review.

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
│   │   ├── database.py          # SQLite data layer
│   │   ├── routers/             # API route handlers
│   │   │   ├── harmonize.py     # Upload & pipeline execution
│   │   │   ├── mappings.py      # Curator review CRUD
│   │   │   ├── ontology.py      # Ontology search & browse
│   │   │   ├── quality.py       # Analytics metrics
│   │   │   └── export.py        # Data export endpoints
│   │   └── services/            # Business logic
│   │       ├── harmonizer.py    # ML engine wrapper
│   │       ├── analytics.py     # Quality metric computation
│   │       └── exporter.py      # Export format generators
│   ├── engine/                  # ML engine (SchemaMapEngine)
│   │   ├── src/
│   │   │   ├── models/schema_mapper/  # 4-stage cascade pipeline
│   │   │   │   ├── engine.py    # Main SchemaMapEngine class
│   │   │   │   ├── config.py    # Thresholds & model config
│   │   │   │   ├── loaders/     # Dictionary & value loaders
│   │   │   │   └── matchers/    # Stage 1–4 matcher classes
│   │   │   ├── utils/           # Schema mapping utilities
│   │   │   └── CustomLogger/    # Structured logging
│   │   └── data/schema/         # Curated dictionaries & ontology data
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main app with routing
│   │   ├── pages/               # Upload, Review, Quality, Export pages
│   │   ├── components/          # Reusable UI components
│   │   └── api/                 # Typed HTTP client
│   └── package.json
├── metadata_samples/            # Reference & sample data
└── README.md
```

---

## Sample Data

The repository includes sample metadata files in `metadata_samples/`:

- **`curated_meta.csv`** — Reference schema with 37 standardized columns (cBioPortal-compatible), including ontology term IDs
- **`new_meta.csv`** — Raw metadata with 131 heterogeneous columns from multiple studies, representing real-world data variability

---

## License

This project is provided as-is for research and educational purposes.

---

## Acknowledgments

- [MetaHarmonizer Engine](https://github.com/shbrief/MetaHarmonizer) — Core ML pipeline for schema mapping
- [cBioPortal](https://www.cbioportal.org/) — Target schema standard for cancer genomics
- [NCI Thesaurus (NCIt)](https://ncithesaurus.nci.nih.gov/) — Biomedical ontology for value normalization
