# Contributing

Thank you for improving MetaHarmonizer.

## Workflow

1. Create a focused branch from the latest `main`.
2. Keep changes within the owning module and avoid unrelated refactors.
3. Add or update tests for behavioral changes.
4. Run the relevant backend, frontend, MCP, or end-to-end checks.
5. Open a pull request describing behavior, validation, migration impact, and
   operational risk.
6. Merge only after all protected checks pass.

See [SETUP.md](SETUP.md) for local development and [architecture](docs/architecture.md)
for ownership boundaries.

## Architectural rules

- Only `backend/app/engine_adapter/` may import the upstream `metaharmonizer`
  package.
- Routers own transport concerns; reusable workflows belong in services and
  persistence belongs in repositories.
- Schema changes require Alembic migrations and rollback/compatibility analysis.
- New asynchronous work requires bounded retries, timeouts, idempotency, and
  observable failure state.
- Never weaken data ownership, secret handling, upload limits, or queue
  backpressure to simplify a feature.

## Validation

```bash
cd backend && pytest
cd frontend && npm ci && npm run build && npm test
cd e2e && npm ci && npm test
python scripts/check_engine_boundary.py
```

Major dependency, engine, schema, and infrastructure changes need targeted
benchmarks or migration evidence in addition to the standard suite.

## Data and secrets

Use synthetic or de-identified fixtures. Never commit production data,
credentials, private URLs, or generated runtime databases. Follow
[SECURITY.md](SECURITY.md) for sensitive reports.

## License and future cBioPortal adoption

Contributions to this repository are accepted under the [MIT License](LICENSE).
The cBioPortal RFC 86 AGPL-to-Apache consent process applies to contributions in
cBioPortal repositories, not automatically to this independently hosted MIT
repository. If this work is later transferred or incorporated into a cBioPortal
repository, contributors may be asked to record the RFC 86 consent statement in
the relevant cBioPortal process. See [licensing notes](docs/licensing.md).
