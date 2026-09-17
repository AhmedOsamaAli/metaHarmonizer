#!/usr/bin/env bash
set -Eeuo pipefail

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

repo="$tmp/repo"
origin="$tmp/origin.git"
mocks="$tmp/mocks"
state="$tmp/state"
mkdir -p "$repo/scripts" "$repo/backend/alembic/versions" "$mocks"

cp "$source_root/scripts/deploy_revision.sh" "$repo/scripts/"
cp "$source_root/scripts/deploy_kb_bundle.sh" "$repo/scripts/"
printf 'revision = "abc123"\n' >"$repo/backend/alembic/versions/initial.py"
printf 'name: test\nservices: {}\n' >"$repo/docker-compose.yml"
printf 'services: {}\n' >"$repo/docker-compose.prod.yml"

cat >"$mocks/docker" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

args=" $* "
state="${MOCK_DOCKER_STATE:?}"
printf 'docker %s\n' "$*" >>"${MOCK_COMMAND_LOG:?}"

read_state() {
  local key="$1"
  local fallback="$2"
  if [[ -f "$state/$key" ]]; then
    cat "$state/$key"
  else
    printf '%s\n' "$fallback"
  fi
}

resolve_image() {
  local kind="$1"
  local reference="$2"
  case "$reference" in
    metaharmonizer-api:latest)
      read_state latest_api "$MOCK_API_IMAGE"
      ;;
    metaharmonizer-api:rollback)
      read_state rollback_api "$MOCK_API_IMAGE"
      ;;
    metaharmonizer-web:latest)
      read_state latest_web "$MOCK_WEB_IMAGE"
      ;;
    metaharmonizer-web:rollback)
      read_state rollback_web "$MOCK_WEB_IMAGE"
      ;;
    *)
      printf '%s\n' "$reference"
      ;;
  esac
}

if [[ "$1" == "compose" ]]; then
  if [[ "$args" == *" version "* ]]; then
    exit 0
  fi
  if [[ "$args" == *" ps -q api "* ]]; then
    printf 'api-container\n'
    exit 0
  fi
  if [[ "$args" == *" ps -q worker "* ]]; then
    printf 'worker-container\n'
    exit 0
  fi
  if [[ "$args" == *" exec -T api alembic current "* ]]; then
    printf '%s (head)\n' "$MOCK_DB_REVISION"
    exit 0
  fi
  if [[ "$args" == *" scripts.production_audit "* ]]; then
    test "${MOCK_AUDIT_FAIL:-0}" != "1"
    exit
  fi
  if [[ "$args" == *" exec -T caddy "* ]]; then
    if [[ -s "$state/served_web_revision" ]]; then
      cat "$state/served_web_revision"
    fi
    exit 0
  fi
  if [[ "$args" == *" web-volume-init "* ]]; then
    : >"$state/served_web_revision"
    exit 0
  fi
  if [[ "$args" == *" build api web "* ]]; then
    printf '%s\n' "$MOCK_BUILT_API_IMAGE" >"$state/latest_api"
    printf '%s\n' "$MOCK_BUILT_WEB_IMAGE" >"$state/latest_web"
    exit 0
  fi
  if [[ "$args" == *" run --rm web "* ]]; then
    latest_web="$(read_state latest_web "$MOCK_WEB_IMAGE")"
    if [[ "$latest_web" == "${MOCK_LEGACY_WEB_IMAGE:-}" ]]; then
      : >"$state/served_web_revision"
    else
      printf '%s\n' "$MOCK_IMAGE_REVISION" >"$state/served_web_revision"
    fi
    exit 0
  fi
  if [[ "$args" == *" up -d "* ]]; then
    read_state latest_api "$MOCK_API_IMAGE" >"$state/running_api"
    exit 0
  fi
  exit 0
fi

if [[ "$1" == "inspect" ]]; then
  if [[ "$args" == *"State.Health.Status"* ]]; then
    printf 'healthy\n'
  else
    read_state running_api "$MOCK_API_IMAGE"
  fi
  exit 0
fi

if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  if [[ "$args" == *"org.opencontainers.image.revision"* ]]; then
    printf '%s\n' "$MOCK_IMAGE_REVISION"
    exit 0
  fi
  if [[ "$args" == *" {{.Id}} "* ]]; then
    reference="${!#}"
    resolve_image web "$reference"
  fi
  exit 0
fi

if [[ "$1" == "tag" ]]; then
  source_image="$2"
  destination="$3"
  case "$destination" in
    metaharmonizer-api:latest)
      resolve_image api "$source_image" >"$state/latest_api"
      ;;
    metaharmonizer-api:rollback)
      resolve_image api "$source_image" >"$state/rollback_api"
      ;;
    metaharmonizer-web:latest)
      resolve_image web "$source_image" >"$state/latest_web"
      ;;
    metaharmonizer-web:rollback)
      resolve_image web "$source_image" >"$state/rollback_web"
      ;;
  esac
  exit 0
fi

printf 'Unexpected docker invocation: %s\n' "$*" >&2
exit 1
EOF

cat >"$mocks/curl" <<'EOF'
#!/usr/bin/env bash
printf '{"ready":true,"checks":{"postgres":"ok","redis":"ok","ontology_kb":"ok"}}\n'
EOF

cat >"$mocks/python3" <<'EOF'
#!/usr/bin/env bash
grep -q '"ready":true'
EOF

cat >"$mocks/sudo" <<'EOF'
#!/usr/bin/env bash
printf 'sudo %s\n' "$*" >>"${MOCK_COMMAND_LOG:?}"
exit 0
EOF
cat >"$mocks/systemctl" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf 'systemctl %s\n' "$*" >>"${MOCK_COMMAND_LOG:?}"
if [[ "$1" == "is-active" ]]; then
  [[ "${!#}" == *".timer" ]]
  exit
fi
if [[ "$1" == "show" && "$*" == *"ExecStart"* ]]; then
  printf '{ path=%s/bin/deploy_kb_bundle.sh ; }\n' "$DEPLOY_STATE_DIR"
elif [[ "$1" == "show" && "$*" == *"ExecMainStatus"* ]]; then
  printf '0\n'
elif [[ "$1" == "show" ]]; then
  printf 'success\n'
fi
EOF
cat >"$mocks/flock" <<'EOF'
#!/usr/bin/env bash
test "${MOCK_LOCK_BUSY:-0}" != "1"
EOF
chmod +x "$mocks"/*

export PATH="$mocks:$PATH"
export MOCK_API_IMAGE="sha256:api-live"
export MOCK_WEB_IMAGE="sha256:web-live"
export MOCK_DB_REVISION="abc123"
export MOCK_DOCKER_STATE="$tmp/docker-state"
export MOCK_COMMAND_LOG="$tmp/commands.log"
export MOCK_BUILT_API_IMAGE="sha256:api-built"
export MOCK_BUILT_WEB_IMAGE="sha256:web-built"
export DEPLOY_BASE_URL="https://example.test"
export DEPLOY_STATE_DIR="$state"
mkdir -p "$MOCK_DOCKER_STATE"

cd "$repo"
git init --initial-branch=main >/dev/null
git config user.name "Deployment Test"
git config user.email "deployment-test@example.test"
git add .
git commit -m "base" >/dev/null
base_commit="$(git rev-parse HEAD)"

printf 'live\n' >README.md
git add README.md
git commit -m "live" >/dev/null
live_commit="$(git rev-parse HEAD)"
export MOCK_IMAGE_REVISION="$live_commit"
printf '%s\n' "$MOCK_API_IMAGE" >"$MOCK_DOCKER_STATE/running_api"
printf '%s\n' "$MOCK_WEB_IMAGE" >"$MOCK_DOCKER_STATE/latest_web"
printf '%s\n' "$live_commit" >"$MOCK_DOCKER_STATE/served_web_revision"

git init --bare "$origin" >/dev/null
git remote add origin "$origin"
git push --set-upstream origin main >/dev/null
export MOCK_WEB_REVISION="$live_commit"

expect_failure() {
  if "$@" >/dev/null 2>&1; then
    printf 'Expected command to fail: %s\n' "$*" >&2
    exit 1
  fi
}

bash scripts/deploy_revision.sh --record-current "$live_commit"
grep -Fxq "commit=$live_commit" "$state/current.env"
grep -Fxq "api_image=$MOCK_API_IMAGE" "$state/current.env"
grep -Fxq "web_revision=$live_commit" "$state/current.env"

DEPLOY_DRY_RUN=1 bash scripts/deploy_revision.sh "$live_commit"
expect_failure env DEPLOY_DRY_RUN=1 \
  bash scripts/deploy_revision.sh --rollback "$base_commit"

sed -i \
  -e "s/^previous_commit=.*/previous_commit=$base_commit/" \
  -e "s/^previous_api_image=.*/previous_api_image=sha256:api-base/" \
  -e "s/^previous_web_image=.*/previous_web_image=sha256:web-base/" \
  -e "s/^previous_alembic_revision=.*/previous_alembic_revision=abc123/" \
  -e "s/^previous_web_revision=.*/previous_web_revision=legacy/" \
  "$state/current.env"
rollback_output="$(
  DEPLOY_DRY_RUN=1 bash scripts/deploy_revision.sh --rollback "$base_commit"
)"
printf '%s' "$rollback_output" | grep -q 'exact retained image IDs'

cp "$state/current.env" "$tmp/live-state.env"
export MOCK_LEGACY_WEB_IMAGE="sha256:web-base"
expect_failure env MOCK_AUDIT_FAIL=1 \
  bash scripts/deploy_revision.sh --rollback "$base_commit"
test "$(git rev-parse HEAD)" = "$live_commit"
grep -Fxq "commit=$live_commit" "$state/current.env"
grep -Fxq "$MOCK_API_IMAGE" "$MOCK_DOCKER_STATE/running_api"
grep -Fxq "$live_commit" "$MOCK_DOCKER_STATE/served_web_revision"

bash scripts/deploy_revision.sh --rollback "$base_commit"
test "$(git rev-parse HEAD)" = "$base_commit"
grep -Fxq "commit=$base_commit" "$state/current.env"
grep -Fxq "previous_commit=$live_commit" "$state/current.env"
grep -Fxq "sha256:api-base" "$MOCK_DOCKER_STATE/running_api"
test ! -s "$MOCK_DOCKER_STATE/served_web_revision"

cp "$tmp/live-state.env" "$state/current.env"
git switch --quiet main
printf '%s\n' "$MOCK_API_IMAGE" >"$MOCK_DOCKER_STATE/running_api"
printf '%s\n' "$MOCK_WEB_IMAGE" >"$MOCK_DOCKER_STATE/latest_web"
printf '%s\n' "$live_commit" >"$MOCK_DOCKER_STATE/served_web_revision"

printf 'future\n' >>README.md
git add README.md
git commit -m "future application change" >/dev/null
future_commit="$(git rev-parse HEAD)"
git push origin main >/dev/null
git switch --quiet --detach "$live_commit"
DEPLOY_DRY_RUN=1 bash scripts/deploy_revision.sh "$future_commit"

printf 'sha256:unexpected\n' >"$MOCK_DOCKER_STATE/running_api"
expect_failure env DEPLOY_DRY_RUN=1 \
  bash scripts/deploy_revision.sh "$future_commit"
printf '%s\n' "$MOCK_API_IMAGE" >"$MOCK_DOCKER_STATE/running_api"

>"$MOCK_DOCKER_STATE/served_web_revision"
expect_failure env DEPLOY_DRY_RUN=1 \
  bash scripts/deploy_revision.sh "$future_commit"
printf '%s\n' "$live_commit" >"$MOCK_DOCKER_STATE/served_web_revision"

MOCK_LOCK_BUSY=1 \
  expect_failure env DEPLOY_DRY_RUN=1 \
  bash scripts/deploy_revision.sh "$future_commit"

touch backend/untracked-build-input.py
expect_failure env DEPLOY_DRY_RUN=1 \
  bash scripts/deploy_revision.sh "$future_commit"
rm backend/untracked-build-input.py

export MOCK_BUILT_API_IMAGE="sha256:api-future"
export MOCK_BUILT_WEB_IMAGE="sha256:web-future"
export MOCK_IMAGE_REVISION="$future_commit"
bash scripts/deploy_revision.sh "$future_commit"
test "$(git rev-parse HEAD)" = "$future_commit"
grep -Fxq "commit=$future_commit" "$state/current.env"
grep -Fxq "previous_commit=$live_commit" "$state/current.env"
grep -Fxq "$MOCK_BUILT_API_IMAGE" "$MOCK_DOCKER_STATE/running_api"
grep -Fxq "$future_commit" "$MOCK_DOCKER_STATE/served_web_revision"

printf 'revision = "def456"\ndown_revision = "abc123"\n' \
  >backend/alembic/versions/new_revision.py
git add backend/alembic/versions/new_revision.py
git commit -m "schema migration" >/dev/null
migration_commit="$(git rev-parse HEAD)"
git push origin main >/dev/null
git switch --quiet --detach "$future_commit"
expect_failure env DEPLOY_DRY_RUN=1 \
  bash scripts/deploy_revision.sh "$migration_commit"
DEPLOY_DRY_RUN=1 bash scripts/deploy_revision.sh \
  --schema "$migration_commit" abc123 def456

export MOCK_BUILT_API_IMAGE="sha256:api-schema"
export MOCK_BUILT_WEB_IMAGE="sha256:web-schema"
export MOCK_IMAGE_REVISION="$migration_commit"
expect_failure env MOCK_AUDIT_FAIL=1 \
  bash scripts/deploy_revision.sh \
  --schema "$migration_commit" abc123 def456
test "$(git rev-parse HEAD)" = "$future_commit"
grep -Fxq "commit=$future_commit" "$state/current.env"
grep -q 'alembic upgrade def456' "$MOCK_COMMAND_LOG"
grep -q 'sudo systemctl stop metaharmonizer-kb-update.timer' "$MOCK_COMMAND_LOG"
test "$(grep -c 'stop api worker caddy' "$MOCK_COMMAND_LOG")" -ge 2
grep -Fxq "$MOCK_BUILT_API_IMAGE" "$MOCK_DOCKER_STATE/running_api"
grep -Fxq "$migration_commit" "$MOCK_DOCKER_STATE/served_web_revision"

export MOCK_API_IMAGE="$MOCK_BUILT_API_IMAGE"
export MOCK_WEB_IMAGE="$MOCK_BUILT_WEB_IMAGE"
export MOCK_DB_REVISION="def456"
printf '%s\n' "$MOCK_API_IMAGE" >"$MOCK_DOCKER_STATE/running_api"
printf '%s\n' "$MOCK_WEB_IMAGE" >"$MOCK_DOCKER_STATE/latest_web"
printf '%s\n' "$migration_commit" >"$MOCK_DOCKER_STATE/served_web_revision"
git switch --quiet --detach "$migration_commit"
bash scripts/deploy_revision.sh \
  --finalize-schema "$migration_commit" "$MOCK_DB_REVISION"
grep -Fxq "commit=$migration_commit" "$state/current.env"
grep -Fxq "alembic_revision=$MOCK_DB_REVISION" "$state/current.env"
grep -Fxq "web_revision=$migration_commit" "$state/current.env"

printf 'deployment state tests passed\n'
