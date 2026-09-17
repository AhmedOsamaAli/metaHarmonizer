# From a code change to production

This is the complete release path for another developer or operator. Merging a
pull request does **not** automatically change production. Application releases
are deliberately operator-triggered after protected checks pass.

## Roles

| Role | Responsibility | Access required |
|---|---|---|
| Developer | Implement a focused change, add tests, open a pull request | Repository write access |
| Maintainer/reviewer | Review behavior, migrations, security, and evidence; merge only green work | Repository maintain/write access |
| Production operator | Back up, deploy an exact merged commit, verify, and roll back if needed | Individual SSH key plus approved backup/systemd access |
| Organization owner | Manage branch protection, Actions secrets, deploy keys, and repository roles | Repository admin/organization owner |

A developer does not need production SSH access. A production operator should
not deploy an unmerged branch.

## 1. Make and validate a change

Start from current `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/short-description
```

Run the smallest relevant checks while developing, then the owning suite before
opening a pull request:

```bash
# Python
ruff check backend scripts mcp
cd backend && pytest -q

# Frontend
cd frontend && npm ci && npm run build && npm test -- --coverage

# MCP
cd mcp && pytest tests -q

# Browser tests require a running stack
cd e2e && npm ci && npx playwright test
```

Never commit `.env`, credentials, production data, uploaded studies, backup
keys, or provider recovery information.

## 2. Open and review a pull request

The pull request must state:

- user-visible behavior;
- tests run;
- whether configuration changes;
- whether database migrations are added;
- whether the KB, object storage, or deployment shape changes;
- rollout and rollback risk.

Protected CI repeats:

- backend tests and coverage;
- frontend typecheck, build, tests, and coverage;
- MCP tests;
- Python and npm dependency audits;
- secret scanning and CodeQL;
- deployment configuration and image scanning;
- external PostgreSQL deployment;
- encrypted dump/encrypt/decrypt/scratch-restore;
- authenticated browser journey and downloads.

Merge only when every required check passes and review conversations are
resolved.

## 3. What happens after merge?

### Application code

Nothing changes in production automatically. The operator selects the exact
merged commit and runs the application deployment command.

### Knowledge-base releases

The KB has a separate automated lifecycle. A scheduled or manually triggered
workflow builds and benchmarks a candidate bundle, publishes `kb-latest`, and
opens its checksum update. Production checks the release hourly, stages it in
new volumes, probes all indexes, switches API/worker, and restores the previous
volumes if validation fails.

### Admin changes

User roles, learned decisions, schema versions, and aliases made through the
admin interface take effect through their own persistence path; they do not
require an application image deployment.

## 4. Routine application deployment

The production command treats running image identity, the served SPA revision,
the live Alembic revision, and a durable state record as the deployed state.
Git checkout `HEAD` and a mutable `latest` tag are not accepted as proof.

### One-time state bootstrap

Before the first release with this process, record the last independently
verified live commit. The checkout must still be at that live commit because
tracked Caddy configuration and metadata samples are runtime inputs. Fetch the
new deployment tool without changing the checkout:

```bash
git fetch --all --tags --prune
LIVE=<known-currently-deployed-40-character-commit>
test "$(git rev-parse HEAD)" = "$LIVE"
git show origin/main:scripts/deploy_revision.sh > /tmp/deploy_revision.sh
chmod 700 /tmp/deploy_revision.sh
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
  /tmp/deploy_revision.sh --record-current "$LIVE"
rm /tmp/deploy_revision.sh
git show origin/main:deploy/systemd/metaharmonizer-kb-update.service \
  > /tmp/metaharmonizer-kb-update.service
sudo install -m 0644 /tmp/metaharmonizer-kb-update.service /etc/systemd/system/
rm /tmp/metaharmonizer-kb-update.service
sudo systemctl daemon-reload
```

This verifies public readiness and records the running API image, current web
image, and database revision under
`~/.local/state/metaharmonizer/deploy/current.env`. It also installs the
hardened operator command at
`~/.local/state/metaharmonizer/deploy/bin/deploy_revision.sh`, independent of
later checkout changes. Run bootstrap only once. Do not delete or recreate that
record to bypass a later mismatch; investigate the drift first.

### Normal release

The routine command accepts the exact `origin/main` commit and refuses:

- a checkout commit different from the recorded live commit;
- tracked changes or untracked/ignored files in release build inputs;
- a target other than the current `origin/main`;
- a mismatch between the state record and the running API, SPA, or database;
- a ref that does not know the live Alembic revision;
- any release that changes migration-related files;
- a concurrent application or KB rollout;
- a failed backup, preflight, readiness check, or production audit.

First run the dry check:

```bash
git fetch --all --tags --prune
TARGET=$(git rev-parse origin/main)
DEPLOY_TOOL="$HOME/.local/state/metaharmonizer/deploy/bin/deploy_revision.sh"
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
DEPLOY_DRY_RUN=1 \
  "$DEPLOY_TOOL" "$TARGET"
```

Then deploy:

```bash
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
  "$DEPLOY_TOOL" "$TARGET"
```

The command:

1. acquires the lock shared with the KB updater;
2. verifies recorded commit, image, SPA, and database identity;
3. pauses the KB timer and waits for any old updater process to finish;
4. runs and verifies the encrypted backup service;
5. tags the recorded API and web images for recovery;
6. stops API, worker, and Caddy before changing any tracked bind-mounted input;
7. checks out and builds the exact target with immutable revision labels;
8. preflights dependencies, KB assets, and Alembic head;
9. runs the idempotent Alembic command, publishes the SPA, and recreates
   services;
10. checks API/worker health, public readiness, the running API image, and the
    served SPA revision;
11. runs the self-cleaning authenticated production audit;
12. pins the checkout to the deployed revision, restarts the KB timer, and
    atomically records the current and immediately previous image IDs.

Any command error or `INT`, `TERM`, or `HUP` before success triggers idempotent
recovery of the old image tags, SPA, services, checkout, and KB timer. There is
no routine flag to skip the backup, deploy an unmerged branch, or skip the
audit. Builds occur inside the maintenance window because changing the checkout
while the previous services run would mix revisions through tracked bind
mounts.

## 5. Database-schema changes

The routine deployment command intentionally refuses migration-file changes.
A schema release therefore uses an announced maintenance window and a reviewed
operator plan rather than a bypass flag.

Before maintenance:

1. Add an Alembic migration with explicit upgrade and downgrade behavior.
2. Run migration contract tests and the encrypted backup/scratch-restore check
   in protected CI.
3. Record the expected current and target Alembic revisions in the pull request.
4. State whether the old application is compatible with the new schema and
   whether downgrade loses or transforms data.
5. Merge only after the migration and rollback plan are approved.

Run a dry check from the still-deployed checkout:

```bash
git fetch --all --tags --prune
TARGET=$(git rev-parse origin/main)
EXPECTED_FROM=<reviewed-current-alembic-revision>
EXPECTED_TO=<reviewed-target-alembic-revision>
DEPLOY_TOOL="$HOME/.local/state/metaharmonizer/deploy/bin/deploy_revision.sh"
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
DEPLOY_DRY_RUN=1 \
  "$DEPLOY_TOOL" --schema "$TARGET" "$EXPECTED_FROM" "$EXPECTED_TO"
```

After approval of the maintenance window, remove `DEPLOY_DRY_RUN=1`. Schema mode
uses the same exact-state checks, shared lock, backup, image retention, build,
preflight, readiness, audit, and atomic record as a routine release. It also
requires the live revision to equal `EXPECTED_FROM` and the target image head
to equal `EXPECTED_TO`.

```bash
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
  "$DEPLOY_TOOL" --schema "$TARGET" "$EXPECTED_FROM" "$EXPECTED_TO"
```

Before Alembic starts, any failure restores the recorded release. From the
instant Alembic starts, failure or termination is fail-closed: API, worker,
Caddy, and the KB timer remain stopped; the old state record and both image sets
remain available. The operator must then choose the reviewed path:

- run the reviewed `alembic downgrade "$EXPECTED_FROM"` from the new image
  before retagging `metaharmonizer-api:rollback` and
  `metaharmonizer-web:rollback`; or
- when downgrade is unsafe, repair or roll forward with writes stopped, check
  image/SPA/database identity and health, then run `--finalize-schema` for the
  target and expected Alembic revision.

For a reviewed downgrade, the target migration image remains tagged `latest`
and the old application images remain tagged `rollback`:

```bash
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
"${COMPOSE[@]}" run --rm --no-deps api \
  alembic downgrade "$EXPECTED_FROM"
docker tag metaharmonizer-api:rollback metaharmonizer-api:latest
docker tag metaharmonizer-web:rollback metaharmonizer-web:latest
"${COMPOSE[@]}" run --rm --no-deps --user 0 web-volume-init \
  sh -c 'rm -f /srv/.release-revision'
"${COMPOSE[@]}" run --rm web
"${COMPOSE[@]}" up -d --no-deps --force-recreate api worker caddy
curl --retry 30 --retry-all-errors --retry-delay 2 \
  --fail --silent --show-error https://metaharmonizer.online/readyz
"${COMPOSE[@]}" exec -T api \
  python -m scripts.production_audit --origin https://metaharmonizer.online
sudo systemctl start metaharmonizer-kb-update.timer
```

For a repaired roll-forward, keep the services stopped until the target image,
SPA, and database revision are mutually compatible. Then recreate the services,
verify readiness, and finalize the durable state before restarting KB updates:

```bash
git switch --detach "$TARGET"
"${COMPOSE[@]}" run --rm web
"${COMPOSE[@]}" up -d --no-deps --force-recreate api worker caddy
curl --retry 30 --retry-all-errors --retry-delay 2 \
  --fail --silent --show-error https://metaharmonizer.online/readyz
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
  "$DEPLOY_TOOL" --finalize-schema "$TARGET" "$EXPECTED_TO"
sudo systemctl start metaharmonizer-kb-update.timer
```

Restoring the pre-release database backup is a separate destructive recovery
decision because it discards writes made after that backup. The
`--finalize-schema` command verifies the new image labels, served SPA revision,
expected Alembic revision, readiness, and production audit before replacing the
durable deployment record.

Never infer backward compatibility merely because a migration appears additive.

## 6. Configuration-only changes

`.env.example` documents available variables; production `.env` is host-only
and must never enter Git.

For a reviewed configuration change:

1. Record the old non-secret value privately.
2. Edit production `.env` with mode `0600`.
3. Render and validate the production Compose configuration.
4. Recreate only affected services.
5. Verify `/readyz`, the running environment value, and the relevant workflow.
6. Restore the previous value if validation fails.

Changes to secrets additionally require provider-side rotation and recovery
verification.

## 7. Rollback

The deployment command retains the immediately previous API and web images.
For an explicit revision rollback, first run:

```bash
DEPLOY_TOOL="$HOME/.local/state/metaharmonizer/deploy/bin/deploy_revision.sh"
DEPLOY_DRY_RUN=1 \
DEPLOY_BASE_URL=https://metaharmonizer.online \
DEPLOY_REPO_ROOT="$PWD" \
  "$DEPLOY_TOOL" --rollback <previous-commit>
```

Remove `DEPLOY_DRY_RUN=1` only after the compatibility check passes.
Rollback uses the same shared lock, backup, image identity, health, production
audit, signal recovery, and durable state update as a forward release.
Application rollback never downgrades PostgreSQL automatically and is refused
unless the target revision supports the live Alembic revision. The immediately
previous release uses its exact retained image IDs, including the first
rollback to a pre-label release. A successful rollback leaves the checkout
detached at that revision so tracked runtime inputs remain consistent; the
stable deployment tool remains available for the next forward release.

## 8. Required release record

For every production deployment, retain:

- merged pull request;
- deployed commit SHA;
- required-check result;
- backup success/object timestamp;
- Alembic revision before and after;
- cutover duration;
- readiness and production-audit result;
- rollback image/ref;
- any configuration or KB version change.

## Current demonstrator behavior

The public demonstrator follows this manual application-release process. KB
updates are automated separately. Another developer can contribute through a
normal protected pull request; only an authorized operator performs the final
production command.
