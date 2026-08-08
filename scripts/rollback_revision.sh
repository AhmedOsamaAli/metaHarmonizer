#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ROLLBACK_BASE_URL=https://host ROLLBACK_SMOKE_EMAIL=user ROLLBACK_SMOKE_PASSWORD=pass $0 <git-ref>" >&2
  exit 2
fi

: "${ROLLBACK_BASE_URL:?set ROLLBACK_BASE_URL}"
: "${ROLLBACK_SMOKE_EMAIL:?set ROLLBACK_SMOKE_EMAIL}"
: "${ROLLBACK_SMOKE_PASSWORD:?set ROLLBACK_SMOKE_PASSWORD}"

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing rollback with tracked working-tree changes." >&2
  exit 2
fi

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
target_ref=$1
current_commit=$(git rev-parse HEAD)
target_commit=$(git rev-parse "${target_ref}^{commit}")

if [[ "$target_commit" == "$current_commit" ]]; then
  echo "Target is already deployed: $target_commit"
  exit 0
fi

db_revision=$("${compose[@]}" exec -T api alembic current 2>&1 | sed -nE 's/^([0-9a-f]+) \(head\)$/\1/p' | tail -1)
if [[ -z "$db_revision" ]]; then
  echo "Could not determine the live Alembic revision." >&2
  exit 1
fi

if ! git grep -q -E "revision(: str)?[[:space:]]*=[[:space:]]*['\"]${db_revision}['\"]" "$target_commit" -- backend/alembic/versions; then
  echo "Rollback blocked: target $target_commit does not know live DB revision $db_revision." >&2
  echo "Create and verify a database backup, review downgrade data loss, and run the downgrade from the newer revision before retrying." >&2
  exit 1
fi

if [[ "${ROLLBACK_DRY_RUN:-0}" == "1" ]]; then
  echo "ROLLBACK_CHECK_OK from=$current_commit to=$target_commit db_revision=$db_revision"
  exit 0
fi

previous_ref_file=$(git rev-parse --git-path metaharmonizer-previous-revision)
printf '%s\n' "$current_commit" > "$previous_ref_file"
start_epoch=$(date +%s)
switched=0

wait_healthy() {
  local api_id worker_id api_health worker_health
  for _ in $(seq 1 90); do
    api_id=$("${compose[@]}" ps -q api)
    worker_id=$("${compose[@]}" ps -q worker)
    api_health=$(docker inspect -f '{{.State.Health.Status}}' "$api_id" 2>/dev/null || true)
    worker_health=$(docker inspect -f '{{.State.Health.Status}}' "$worker_id" 2>/dev/null || true)
    if [[ "$api_health" == "healthy" && "$worker_health" == "healthy" ]]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

deploy_ref() {
  local ref=$1
  git switch --detach "$ref"
  "${compose[@]}" build api web
  "${compose[@]}" run --rm web
  "${compose[@]}" up -d --no-deps --force-recreate api worker caddy
  wait_healthy
}

login_smoke() {
  local payload status
  payload=$(ROLLBACK_SMOKE_EMAIL="$ROLLBACK_SMOKE_EMAIL" ROLLBACK_SMOKE_PASSWORD="$ROLLBACK_SMOKE_PASSWORD" python3 - <<'PY'
import json
import os
print(json.dumps({
    "email": os.environ["ROLLBACK_SMOKE_EMAIL"],
    "password": os.environ["ROLLBACK_SMOKE_PASSWORD"],
    "remember": False,
}))
PY
)
  status=$(curl -sS -o /tmp/metaharmonizer-rollback-login.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    "${ROLLBACK_BASE_URL%/}/api/v1/auth/login")
  [[ "$status" == "200" ]] && grep -q 'access_token' /tmp/metaharmonizer-rollback-login.json
  rm -f /tmp/metaharmonizer-rollback-login.json
}

recover() {
  local exit_code=$?
  trap - ERR
  if [[ "$switched" == "1" ]]; then
    echo "Rollback validation failed; restoring $current_commit." >&2
    deploy_ref "$current_commit" || true
  fi
  exit "$exit_code"
}
trap recover ERR

switched=1
deploy_ref "$target_commit"
curl -fsS "${ROLLBACK_BASE_URL%/}/healthz" >/dev/null
login_smoke
trap - ERR

elapsed=$(( $(date +%s) - start_epoch ))
echo "ROLLBACK_OK from=$current_commit to=$target_commit db_revision=$db_revision elapsed_seconds=$elapsed"
echo "To return to the tracked branch: git switch main && git pull --ff-only"