# Deployment review resolution

This document resolves the deployment concerns raised during the final
deliverable review and records where each claim is enforced. It is the concise
companion to the full question-by-question verification response.

## 1. Fresh-checkout KB prerequisites and order

### Root cause

The old deployment text showed `package_kb` without first constructing the
ontology database, corpora, indexes, and models. Packaging also warned about
missing assets but still produced an incomplete archive.

### Resolved behavior

Normal deployments do not build a KB. They run:

```bash
cp .env.example .env
docker compose --profile kb run --rm kb-import
docker compose up --build
```

The importer downloads the published `kb-latest` bundle, verifies its SHA-256,
validates required archive members before extraction, imports it, and runs an
offline probe over disease/NCIt, bodysite/UBERON, and treatment/NCIt.

Maintainers creating a new bundle use this exact order:

```bash
cd backend
pip install -r requirements.txt
python -m scripts.build_kb
python -m scripts.warm_schema_cache
python -m scripts.package_kb -o ../kb/kb_offline_bundle.tar.gz
```

`package_kb` fails unless the engine database, all three corpora, FAISS indexes
and ID sidecars, ontology model, schema model, and warmed schema cache exist.
`--allow-incomplete` is an explicit development-only escape hatch.

### Evidence

- `backend/app/engine_adapter/kb_assets.py`
- `backend/scripts/build_kb.py`
- `backend/scripts/warm_schema_cache.py`
- `backend/scripts/package_kb.py`
- `backend/scripts/seed_kb.py`
- `backend/scripts/kb_probe.py`
- `docker-compose.yml` (`kb-import`)
- `.github/workflows/kb-refresh.yml`

## 2. First task cannot trigger an hours-long KB build

### Root cause

The upstream ontology engine builds a missing corpus/index when
`OntoMapEngine.run()` is constructed on a cache miss. The application previously
discovered that only inside a worker job, after the study had entered
`processing`.

### Resolved behavior

One completeness contract is now checked at four boundaries:

1. `/readyz` reports `ontology_kb=error` and returns 503 when the real engine's
   schema model, or enabled ontology path, is incomplete.
2. Pre-body ASGI middleware rejects harmonization with 503 before FastAPI parses
   or spools the multipart upload; the route repeats the check before
   application persistence.
3. The worker repeats the check and marks directly inserted work failed rather
   than constructing the engine.
4. The ontology bridge checks once more before `OntoMapEngine` construction.

No user request builds ontology corpora or FAISS indexes. An operator fixes an
incomplete instance with `docker compose --profile kb run --rm kb-import`.

## 3. Why the KB build is slow and how deployment avoids it

A cold KB refresh downloads source ontologies and two embedding models, embeds
three launch corpora, builds FAISS indexes, packages about 1.5 GB, and runs
before/after accuracy benchmarks. Historical clean workflow runs took about
3 hours 20 minutes. A successful retry that reused the pre-graft checkpoint
completed in about 8 minutes.

This cost is isolated to the quarterly maintainer workflow. `reuse_run_id`
reuses the expensive checkpoint after a late graft/package/publish failure.
Deployments only download and verify the published bundle; production never
builds it.

## 4. Previously skipped deployment validations

| Concern | Automated evidence | Operational evidence |
|---|---|---|
| Production TLS/Caddy | Production Compose render plus `caddy validate` in `deploy-smoke.yml` | Live HTTPS, HSTS, CSP, and authenticated production audit |
| External PostgreSQL | `External Database Deployment` job starts no bundled Postgres, migrates a separate DB, seeds and logs in | Production can switch through `EXTERNAL_DATABASE_URL` |
| Encrypted backup restore | Deployment CI performs a real PostgreSQL dump → AES-256-GCM encrypt/decrypt → scratch DB restore → Alembic query | R2 restore drill and fresh encrypted backups before rollouts |
| cBioPortal validation | CI checks out pinned `datahub-study-curation-tools` and runs its real `validateData.py` against a generated study | Export also runs the in-application LinkML gate |
| Real ontology engine | Scheduled/manual `Real Ontology Mapping` downloads the checksum-verified published bundle, seeds it, probes it, and runs FAISS-backed mapping | Production audit exercises real queue and ontology rerun |

## 5. Demo-site downloads

### Root cause

The export page used plain `<a href>` links for bearer-protected API endpoints.
Browser navigation does not attach the in-memory access token, so the server
returned 401 and Chromium reported “File wasn’t available on site.” Production
source uploads were present; this was not retention or data loss.

### Resolved behavior

All study and alias downloads use the shared authenticated HTTP client, including
the existing 401 refresh-and-retry path. Responses are downloaded as blobs,
server-provided filenames are honored, object URLs remain valid long enough for
Chromium to consume them, and API errors are shown to the curator.

Coverage includes unit tests for bearer injection, filenames, empty files, and
delayed URL cleanup, plus an authenticated Playwright journey that uploads a
study, waits for queue completion, downloads the harmonized CSV, verifies the
file, and deletes the temporary study.

## 6. Repository transfer blocker

GitHub rejected transfer to `shbrief/metaHarmonizer-app` because Dr. Sehyun
already owns `shbrief/MetaHarmonizerApp`, a fork in this repository's network.
GitHub does not allow one personal account to own two repositories in the same
network, even when their names differ.

The conflicting fork currently has only `main`, is nine commits behind this
repository, and has zero unique commits. Before deleting it, Dr. Sehyun should
still verify that it has no issues, Actions secrets, deploy keys, or other
settings she needs. Once it is deleted or detached from the fork network,
transfer can be retried as `shbrief/metaHarmonizer-app`; GitHub then emails her
an acceptance link that expires after one day.
