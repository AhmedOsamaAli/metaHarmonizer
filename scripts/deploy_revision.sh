#!/usr/bin/env bash
# Deploy one exact merged application revision on the production host.
#
# The routine path deliberately refuses Alembic changes. Database migrations
# follow the reviewed maintenance-window procedure in docs/release-process.md.
set -Eeuo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  DEPLOY_BASE_URL=https://example.org ./scripts/deploy_revision.sh <git-ref>
  DEPLOY_BASE_URL=https://example.org ./scripts/deploy_revision.sh --rollback <git-ref>
  DEPLOY_BASE_URL=https://example.org ./scripts/deploy_revision.sh --schema <git-ref> <from-revision> <to-revision>
  DEPLOY_BASE_URL=https://example.org ./scripts/deploy_revision.sh --record-current <git-ref>
  DEPLOY_BASE_URL=https://example.org ./scripts/deploy_revision.sh --finalize-schema <git-ref> <alembic-revision>

The first form performs a backup-first deployment of origin/main. The rollback
form deploys an older mainline revision only when it supports the live database
revision. The schema form executes a reviewed migration in a fail-closed
maintenance window. The record form is a one-time bootstrap for the known live
revision. The finalize form validates and records a repaired schema release.

Optional environment:
  DEPLOY_DRY_RUN=1
  DEPLOY_REPO_ROOT=/home/ubuntu/metaHarmonizer
  DEPLOY_STATE_DIR=/var/lib/metaharmonizer/deploy-state
  DEPLOY_LOCK_FILE=/tmp/metaharmonizer-deploy.lock
  DEPLOY_BACKUP_SERVICE=metaharmonizer-backup.service
  DEPLOY_KB_TIMER=metaharmonizer-kb-update.timer
  DEPLOY_KB_SERVICE=metaharmonizer-kb-update.service
EOF
  exit 64
}

[[ $# -ge 1 ]] || usage

mode="deploy"
if [[ "$1" == "--record-current" ]]; then
  [[ $# -eq 2 ]] || usage
  mode="record"
  requested_ref="$2"
elif [[ "$1" == "--rollback" ]]; then
  [[ $# -eq 2 ]] || usage
  mode="rollback"
  requested_ref="$2"
elif [[ "$1" == "--schema" ]]; then
  [[ $# -eq 4 ]] || usage
  mode="schema"
  requested_ref="$2"
  expected_schema_from="$3"
  expected_schema_to="$4"
elif [[ "$1" == "--finalize-schema" ]]; then
  [[ $# -eq 3 ]] || usage
  mode="finalize-schema"
  requested_ref="$2"
  expected_schema_revision="$3"
else
  [[ $# -eq 1 ]] || usage
  requested_ref="$1"
fi

: "${DEPLOY_BASE_URL:?Set DEPLOY_BASE_URL to the public HTTPS origin}"

repo_root="${DEPLOY_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$repo_root"

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
state_dir="${DEPLOY_STATE_DIR:-${HOME}/.local/state/metaharmonizer/deploy}"
state_file="${state_dir}/current.env"
stable_tool="${state_dir}/bin/deploy_revision.sh"
stable_kb_tool="${state_dir}/bin/deploy_kb_bundle.sh"
lock_file="${DEPLOY_LOCK_FILE:-/tmp/metaharmonizer-deploy.lock}"
backup_service="${DEPLOY_BACKUP_SERVICE:-metaharmonizer-backup.service}"
kb_timer="${DEPLOY_KB_TIMER:-metaharmonizer-kb-update.timer}"
kb_service="${DEPLOY_KB_SERVICE:-metaharmonizer-kb-update.service}"
dry_run="${DEPLOY_DRY_RUN:-0}"

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$dry_run" =~ ^[01]$ ]] ||
  fail "DEPLOY_DRY_RUN must be 0 or 1"

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

resolve_commit() {
  git rev-parse --verify "$1^{commit}"
}

read_state_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$state_file" | tail -n 1
}

write_state() {
  local commit="$1"
  local api_image="$2"
  local web_image="$3"
  local alembic_revision="$4"
  local web_revision="$5"
  local previous_commit="$6"
  local previous_api_image="$7"
  local previous_web_image="$8"
  local previous_alembic_revision="$9"
  local previous_web_revision="${10}"
  local timestamp temp_file

  timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  mkdir -p "$state_dir"
  chmod 700 "$state_dir"
  temp_file="$(mktemp "${state_dir}/current.env.XXXXXX")"
  {
    printf 'commit=%s\n' "$commit"
    printf 'api_image=%s\n' "$api_image"
    printf 'web_image=%s\n' "$web_image"
    printf 'alembic_revision=%s\n' "$alembic_revision"
    printf 'web_revision=%s\n' "$web_revision"
    printf 'previous_commit=%s\n' "$previous_commit"
    printf 'previous_api_image=%s\n' "$previous_api_image"
    printf 'previous_web_image=%s\n' "$previous_web_image"
    printf 'previous_alembic_revision=%s\n' "$previous_alembic_revision"
    printf 'previous_web_revision=%s\n' "$previous_web_revision"
    printf 'deployed_at=%s\n' "$timestamp"
  } >"$temp_file"
  chmod 600 "$temp_file"
  mv -f "$temp_file" "$state_file"
}

install_file_atomically() {
  local source="$1"
  local destination="$2"
  local temp_file

  mkdir -p "$(dirname "$destination")"
  temp_file="$(mktemp "${destination}.XXXXXX")"
  cp "$source" "$temp_file"
  chmod 700 "$temp_file"
  mv -f "$temp_file" "$destination"
}

install_stable_tools() {
  local deploy_source="$1"
  local kb_source

  mkdir -p "$state_dir"
  chmod 700 "$state_dir"
  kb_source="$(mktemp "${state_dir}/kb-tool.XXXXXX")"
  if ! git show origin/main:scripts/deploy_kb_bundle.sh >"$kb_source"; then
    rm -f "$kb_source"
    return 1
  fi
  install_file_atomically "$deploy_source" "$stable_tool"
  install_file_atomically "$kb_source" "$stable_kb_tool"
  rm -f "$kb_source"
}

commit_success_state() {
  local tool_source="$1"
  shift

  trap '' INT TERM HUP
  install_stable_tools "$tool_source"
  write_state "$@"
  deployment_succeeded=1
  trap 'on_signal INT 130' INT
  trap 'on_signal TERM 143' TERM
  trap 'on_signal HUP 129' HUP
}

running_service_image() {
  local service="$1"
  local container_id
  container_id="$("${compose[@]}" ps -q "$service")"
  [[ -n "$container_id" ]] || fail "No running container found for service: $service"
  docker inspect --format '{{.Image}}' "$container_id"
}

image_id() {
  docker image inspect --format '{{.Id}}' "$1"
}

image_revision() {
  docker image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1"
}

served_web_revision() {
  "${compose[@]}" exec -T caddy sh -c \
    'test -f /srv/.release-revision && cat /srv/.release-revision' \
    2>/dev/null || true
}

web_revision_matches() {
  local expected="$1"
  local actual
  actual="$(served_web_revision)"
  if [[ "$expected" == "legacy" ]]; then
    [[ -z "$actual" ]]
  else
    [[ "$actual" == "$expected" ]]
  fi
}

clear_web_revision_marker() {
  "${compose[@]}" run --rm --no-deps --user 0 web-volume-init \
    sh -c 'rm -f /srv/.release-revision'
}

database_revision() {
  "${compose[@]}" exec -T api alembic current 2>/dev/null |
    awk 'NF {print $1; exit}'
}

verify_public_readiness() {
  local response
  response="$(curl --fail --silent --show-error \
    "${DEPLOY_BASE_URL%/}/readyz")" || return 1
  printf '%s' "$response" | python3 -c \
    'import json, sys; raise SystemExit(json.load(sys.stdin).get("ready") is not True)'
}

wait_healthy() {
  local api_id worker_id api_health worker_health

  for _ in $(seq 1 150); do
    api_id="$("${compose[@]}" ps -q api)"
    worker_id="$("${compose[@]}" ps -q worker)"
    api_health="$(docker inspect --format '{{.State.Health.Status}}' \
      "$api_id" 2>/dev/null || true)"
    worker_health="$(docker inspect --format '{{.State.Health.Status}}' \
      "$worker_id" 2>/dev/null || true)"
    if [[ "$api_health" == "healthy" && "$worker_health" == "healthy" ]]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_public() {
  for _ in $(seq 1 60); do
    if verify_public_readiness >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_for_service_inactive() {
  local service="$1"
  local attempts=60

  while systemctl is-active --quiet "$service"; do
    ((attempts--)) || return 1
    sleep 2
  done
}

restart_kb_timer() {
  if [[ "$kb_timer_was_active" == "1" &&
        "$kb_timer_is_stopped" == "1" ]]; then
    sudo systemctl start "$kb_timer" || return 1
    systemctl is-active --quiet "$kb_timer" || return 1
    kb_timer_is_stopped=0
  fi
}

restore_checkout() {
  if [[ "$checkout_changed" != "1" ]]; then
    return
  fi

  if [[ -n "$original_branch" ]]; then
    git switch --quiet "$original_branch" || return 1
  else
    git switch --quiet --detach "$original_checkout" || return 1
  fi
  checkout_changed=0
}

finalize_checkout() {
  if [[ "$mode" == "rollback" ]]; then
    checkout_changed=0
  else
    git switch --quiet main
    git merge --quiet --ff-only "$target_commit"
    checkout_changed=0
  fi
}

recover_deployment() {
  local recovery_failed=0

  log "Recovering the previously recorded application state"
  if [[ "$kb_timer_was_active" == "1" &&
        "$kb_timer_is_stopped" == "0" ]]; then
    sudo systemctl stop "$kb_timer" || recovery_failed=1
    kb_timer_is_stopped=1
  fi
  restore_checkout || recovery_failed=1

  if [[ "$rollback_tags_ready" == "1" ]]; then
    docker tag metaharmonizer-api:rollback metaharmonizer-api:latest ||
      recovery_failed=1
    docker tag metaharmonizer-web:rollback metaharmonizer-web:latest ||
      recovery_failed=1
  fi

  if [[ "$runtime_may_have_changed" == "1" ]]; then
    local recovered_api_container recovered_api_image
    local recovered_worker_container recovered_worker_image
    clear_web_revision_marker || recovery_failed=1
    "${compose[@]}" run --rm web || recovery_failed=1
    "${compose[@]}" up -d --no-deps --force-recreate api worker caddy ||
      recovery_failed=1
    "${compose[@]}" ps || true
    wait_healthy || recovery_failed=1
    wait_public || recovery_failed=1
    recovered_api_container="$("${compose[@]}" ps -q api)" ||
      recovery_failed=1
    recovered_api_image="$(docker inspect --format '{{.Image}}' \
      "$recovered_api_container" 2>/dev/null)" || recovery_failed=1
    recovered_worker_container="$("${compose[@]}" ps -q worker)" ||
      recovery_failed=1
    recovered_worker_image="$(docker inspect --format '{{.Image}}' \
      "$recovered_worker_container" 2>/dev/null)" || recovery_failed=1
    [[ "$recovered_api_image" == "$deployed_api_image" ]] ||
      recovery_failed=1
    [[ "$recovered_worker_image" == "$deployed_api_image" ]] ||
      recovery_failed=1
    web_revision_matches "$deployed_web_revision" || recovery_failed=1
  fi

  if [[ "$recovery_failed" == "0" ]]; then
    restart_kb_timer || recovery_failed=1
  fi
  return "$recovery_failed"
}

contain_schema_failure() {
  local containment_failed=0

  printf '[deploy] Schema migration may have changed the database; entering fail-closed recovery\n' >&2
  if [[ "$kb_timer_was_active" == "1" ]]; then
    sudo systemctl stop "$kb_timer" || containment_failed=1
    kb_timer_is_stopped=1
  fi
  "${compose[@]}" stop api worker caddy || containment_failed=1
  restore_checkout || containment_failed=1
  printf '[deploy] Application write services and the KB timer remain stopped.\n' >&2
  printf '[deploy] Use the reviewed downgrade or roll-forward procedure; do not restart traffic first.\n' >&2
  return "$containment_failed"
}

deployment_succeeded=0
checkout_changed=0
rollback_tags_ready=0
runtime_may_have_changed=0
kb_timer_was_active=0
kb_timer_is_stopped=0
schema_migration_started=0
original_checkout=""
original_branch=""
failed_command=""
failed_line=""
signal_name=""

on_error() {
  local code=$?
  failed_command="$BASH_COMMAND"
  failed_line="${BASH_LINENO[0]:-${LINENO}}"
  return "$code"
}

on_signal() {
  signal_name="$1"
  exit "$2"
}

on_exit() {
  local code=$?
  trap - ERR INT TERM HUP EXIT

  if [[ "$deployment_succeeded" != "1" ]]; then
    if [[ -n "$signal_name" ]]; then
      printf '[deploy] Interrupted by %s; starting recovery\n' "$signal_name" >&2
    elif [[ -n "$failed_command" ]]; then
      printf '[deploy] Command failed at line %s: %s\n' \
        "$failed_line" "$failed_command" >&2
    fi
    if [[ "$schema_migration_started" == "1" ]]; then
      if ! contain_schema_failure; then
        printf '[deploy] ERROR: schema failure containment was incomplete; operator action is required\n' >&2
      fi
      code=1
    elif [[ "$checkout_changed" == "1" ||
            "$rollback_tags_ready" == "1" ||
            "$runtime_may_have_changed" == "1" ||
            "$kb_timer_is_stopped" == "1" ]] &&
         ! recover_deployment; then
        printf '[deploy] ERROR: automatic recovery was incomplete; operator action is required\n' >&2
        code=1
    fi
  fi

  exit "$code"
}

trap on_error ERR
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP
trap on_exit EXIT

for command_name in awk curl docker flock git grep install mktemp python3 sed seq sort sudo systemctl; do
  require_command "$command_name"
done
docker compose version >/dev/null

exec 9>"$lock_file"
flock -n 9 || fail "Another application or knowledge-base deployment holds ${lock_file}"

git fetch --prune origin
target_commit="$(resolve_commit "$requested_ref")"
origin_main="$(resolve_commit origin/main)"
git merge-base --is-ancestor "$target_commit" origin/main ||
  fail "Target ${target_commit} is not reachable from origin/main"

original_checkout="$(git rev-parse HEAD)"
original_branch="$(git symbolic-ref --quiet --short HEAD || true)"

if [[ "$mode" =~ ^(deploy|schema|finalize-schema)$ &&
      "$target_commit" != "$origin_main" ]]; then
  fail "Forward deployment target must equal the current origin/main"
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "Tracked worktree changes are present; production builds require a clean checkout"
fi

untracked_release_inputs="$(
  {
    git ls-files --others --exclude-standard -- backend frontend metadata_samples
    git ls-files --others --ignored --exclude-standard -- backend frontend metadata_samples
    git ls-files --others --exclude-standard -- 'docker-compose*.yml' 'Caddyfile*'
    git ls-files --others --ignored --exclude-standard -- 'docker-compose*.yml' 'Caddyfile*'
  } | sort -u
)"
if [[ -n "$untracked_release_inputs" ]]; then
  printf '%s\n' "$untracked_release_inputs" >&2
  fail "Untracked or ignored files could enter a release build context"
fi

current_api_image="$(running_service_image api)"
current_worker_image="$(running_service_image worker)"
current_web_image="$(image_id metaharmonizer-web:latest)"
current_db_revision="$(database_revision)"
[[ -n "$current_db_revision" ]] ||
  fail "Could not read the current Alembic revision"

if [[ "$mode" == "record" ]]; then
  [[ "$original_checkout" == "$target_commit" ]] ||
    fail "State bootstrap requires the checkout to match the known live revision"
  [[ ! -e "$state_file" ]] ||
    fail "Deployment state already exists at ${state_file}; refusing to overwrite it"
  [[ "$current_worker_image" == "$current_api_image" ]] ||
    fail "API and worker do not use the same image"

  marker_revision="$(served_web_revision)"
  if [[ -n "$marker_revision" && "$marker_revision" != "$target_commit" ]]; then
    fail "Served web revision ${marker_revision} does not match ${target_commit}"
  fi
  recorded_web_revision="${marker_revision:-legacy}"

  verify_public_readiness
  commit_success_state "${BASH_SOURCE[0]}" \
    "$target_commit" "$current_api_image" "$current_web_image" \
    "$current_db_revision" "$recorded_web_revision" \
    "" "" "" "" ""
  log "Recorded current deployment state at ${state_file}"
  log "Commit: ${target_commit}"
  log "API image: ${current_api_image}"
  log "Web image: ${current_web_image}"
  exit 0
fi

[[ -f "$state_file" ]] ||
  fail "No deployment state exists; run --record-current for the known live revision first"

kb_service_exec="$(systemctl show "$kb_service" -p ExecStart --value)"
[[ "$kb_service_exec" == *"$stable_kb_tool"* ]] ||
  fail "${kb_service} must execute the stable KB deployment tool at ${stable_kb_tool}"
[[ -x "$stable_kb_tool" ]] ||
  fail "Stable KB deployment tool is missing or not executable: ${stable_kb_tool}"

deployed_commit="$(read_state_value commit)"
deployed_api_image="$(read_state_value api_image)"
deployed_web_image="$(read_state_value web_image)"
deployed_db_revision="$(read_state_value alembic_revision)"
deployed_web_revision="$(read_state_value web_revision)"
previous_commit="$(read_state_value previous_commit)"
previous_api_image="$(read_state_value previous_api_image)"
previous_web_image="$(read_state_value previous_web_image)"
previous_db_revision="$(read_state_value previous_alembic_revision)"
previous_web_revision="$(read_state_value previous_web_revision)"

[[ "$deployed_commit" =~ ^[0-9a-f]{40}$ ]] ||
  fail "Invalid commit in ${state_file}"
git cat-file -e "${deployed_commit}^{commit}" ||
  fail "Recorded commit is not available in the production checkout"
[[ "$deployed_api_image" == sha256:* ]] ||
  fail "Invalid API image ID in ${state_file}"
[[ "$deployed_web_image" == sha256:* ]] ||
  fail "Invalid web image ID in ${state_file}"
[[ "$deployed_web_revision" == "legacy" ||
   "$deployed_web_revision" =~ ^[0-9a-f]{40}$ ]] ||
  fail "Invalid web revision in ${state_file}"
[[ "$deployed_db_revision" =~ ^[0-9a-f]+$ ]] ||
  fail "Invalid Alembic revision in ${state_file}"
docker image inspect "$deployed_api_image" >/dev/null
docker image inspect "$deployed_web_image" >/dev/null

if [[ -n "$previous_commit" ]]; then
  [[ "$previous_commit" =~ ^[0-9a-f]{40}$ ]] ||
    fail "Invalid previous commit in ${state_file}"
  [[ "$previous_api_image" == sha256:* ]] ||
    fail "Invalid previous API image ID in ${state_file}"
  [[ "$previous_web_image" == sha256:* ]] ||
    fail "Invalid previous web image ID in ${state_file}"
  [[ "$previous_db_revision" =~ ^[0-9a-f]+$ ]] ||
    fail "Invalid previous Alembic revision in ${state_file}"
  [[ "$previous_web_revision" == "legacy" ||
     "$previous_web_revision" =~ ^[0-9a-f]{40}$ ]] ||
    fail "Invalid previous web revision in ${state_file}"
elif [[ -n "$previous_api_image$previous_web_image$previous_db_revision$previous_web_revision" ]]; then
  fail "Incomplete previous deployment state in ${state_file}"
fi

if [[ "$mode" == "finalize-schema" ]]; then
  [[ "$original_checkout" == "$target_commit" ]] ||
    fail "Schema finalization requires the checkout to match the target revision"
  [[ "$expected_schema_revision" =~ ^[0-9a-f]+$ ]] ||
    fail "Expected Alembic revision has an invalid format"
  git merge-base --is-ancestor "$deployed_commit" "$target_commit" ||
    fail "Schema finalization cannot move behind the recorded live revision"
  [[ "$current_db_revision" == "$expected_schema_revision" ]] ||
    fail "Live database revision does not match the reviewed schema target"
  [[ "$(image_revision "$current_api_image")" == "$target_commit" ]] ||
    fail "Running API image is not labeled with the schema-release revision"
  [[ "$current_worker_image" == "$current_api_image" ]] ||
    fail "Running worker does not use the schema-release API image"
  [[ "$(image_revision "$current_web_image")" == "$target_commit" ]] ||
    fail "Current web image is not labeled with the schema-release revision"
  [[ "$(served_web_revision)" == "$target_commit" ]] ||
    fail "Caddy is not serving the schema-release revision"
  verify_public_readiness ||
    fail "Schema release is not publicly ready"
  log "Running mandatory production audit before recording schema release"
  "${compose[@]}" exec -T api \
    python -m scripts.production_audit --origin "${DEPLOY_BASE_URL%/}"
  commit_success_state "$repo_root/scripts/deploy_revision.sh" \
    "$target_commit" "$current_api_image" "$current_web_image" \
    "$current_db_revision" "$target_commit" \
    "$deployed_commit" "$deployed_api_image" "$deployed_web_image" \
    "$deployed_db_revision" "$deployed_web_revision"
  log "Schema release state recorded for ${target_commit}"
  exit 0
fi

[[ "$original_checkout" == "$deployed_commit" ]] ||
  fail "Checkout revision does not match the recorded deployment state"
[[ "$current_api_image" == "$deployed_api_image" ]] ||
  fail "Running API image does not match the recorded deployment state"
[[ "$current_worker_image" == "$deployed_api_image" ]] ||
  fail "Running worker image does not match the recorded deployment state"
[[ "$current_db_revision" == "$deployed_db_revision" ]] ||
  fail "Database revision does not match the recorded deployment state"

if [[ "$deployed_web_revision" != "legacy" &&
      "$deployed_web_revision" != "$deployed_commit" ]]; then
  fail "Recorded web revision does not match the deployed commit"
fi
if ! web_revision_matches "$deployed_web_revision"; then
  fail "Served web revision does not match the recorded deployment state"
fi

if [[ "$target_commit" == "$deployed_commit" ]]; then
  verify_public_readiness ||
    fail "Recorded deployment is not publicly ready"
  deployment_succeeded=1
  log "Revision ${target_commit} is already deployed and matches live image state"
  exit 0
fi

if [[ "$mode" =~ ^(deploy|schema)$ ]]; then
  git merge-base --is-ancestor "$deployed_commit" "$target_commit" ||
    fail "Forward deployment cannot move behind the recorded live revision"

  migration_changes="$(
    git diff --name-only "$deployed_commit" "$target_commit" -- \
      backend/alembic.ini backend/alembic backend/app/db.py
  )"
  if [[ "$mode" == "deploy" && -n "$migration_changes" ]]; then
    printf '%s\n' "$migration_changes" >&2
    fail "Routine deploy refuses schema-related changes; use the reviewed migration procedure"
  elif [[ "$mode" == "schema" ]]; then
    [[ "$expected_schema_from" =~ ^[0-9a-f]+$ &&
       "$expected_schema_to" =~ ^[0-9a-f]+$ ]] ||
      fail "Expected Alembic revisions have an invalid format"
    [[ "$current_db_revision" == "$expected_schema_from" ]] ||
      fail "Live database revision does not match the reviewed migration source"
    [[ -n "$migration_changes" ]] ||
      fail "Schema mode requires a reviewed migration-related change"
    git grep -q -E \
      "revision(: str)?[[:space:]]*=[[:space:]]*['\"]${expected_schema_to}['\"]" \
      "$target_commit" -- backend/alembic/versions ||
      fail "Target does not contain the reviewed migration target"
  fi
else
  git merge-base --is-ancestor "$target_commit" "$deployed_commit" ||
    fail "Rollback target must be an ancestor of the recorded live revision"
fi

if ! git grep -q -E \
  "revision(: str)?[[:space:]]*=[[:space:]]*['\"]${current_db_revision}['\"]" \
  "$target_commit" -- backend/alembic/versions; then
  fail "Target does not support the live database revision ${current_db_revision}"
fi

retained_target=0
target_web_revision="$target_commit"
if [[ "$mode" == "rollback" ]]; then
  if [[ "$target_commit" == "$previous_commit" ]] &&
     docker image inspect "$previous_api_image" >/dev/null 2>&1 &&
     docker image inspect "$previous_web_image" >/dev/null 2>&1; then
    retained_target=1
    target_web_revision="$previous_web_revision"
  elif ! git grep -q "SOURCE_COMMIT" "$target_commit" -- backend/Dockerfile ||
       ! git grep -q "SOURCE_COMMIT" "$target_commit" -- frontend/Dockerfile; then
    fail "Rollback target has no retained images and predates release identity labels"
  fi
fi

expected_target_db_revision="$current_db_revision"
if [[ "$mode" == "schema" ]]; then
  expected_target_db_revision="$expected_schema_to"
fi

log "Action: ${mode}"
log "Current deployed revision: ${deployed_commit}"
log "Target mainline revision: ${target_commit}"
log "Current database revision: ${current_db_revision}"
if [[ "$retained_target" == "1" ]]; then
  log "Rollback source: exact retained image IDs"
fi

if [[ "$dry_run" == "1" ]]; then
  verify_public_readiness ||
    fail "Current deployment is not publicly ready"
  deployment_succeeded=1
  log "Dry run passed; no backup, build, checkout, or service change was made"
  exit 0
fi

install_file_atomically "${BASH_SOURCE[0]}" "$stable_tool"

if systemctl is-active --quiet "$kb_timer"; then
  kb_timer_was_active=1
  kb_timer_is_stopped=1
  sudo systemctl stop "$kb_timer"
fi
wait_for_service_inactive "$kb_service" ||
  fail "Timed out waiting for ${kb_service} to stop"

log "Creating and remotely verifying the required pre-deployment backup"
sudo systemctl start "$backup_service"
[[ "$(systemctl show "$backup_service" -p Result --value)" == "success" ]] ||
  fail "Backup service did not report a successful result"
[[ "$(systemctl show "$backup_service" -p ExecMainStatus --value)" == "0" ]] ||
  fail "Backup service exited unsuccessfully"

docker tag "$deployed_api_image" metaharmonizer-api:rollback
docker tag "$deployed_web_image" metaharmonizer-web:rollback
rollback_tags_ready=1

runtime_may_have_changed=1
log "Stopping application services before changing tracked release inputs"
"${compose[@]}" stop api worker caddy

git switch --quiet --detach "$target_commit"
checkout_changed=1

if [[ "$retained_target" == "1" ]]; then
  docker tag "$previous_api_image" metaharmonizer-api:latest
  docker tag "$previous_web_image" metaharmonizer-web:latest
  new_api_image="$previous_api_image"
  new_web_image="$previous_web_image"
else
  export SOURCE_COMMIT="$target_commit"
  log "Building exact target images with revision labels"
  "${compose[@]}" build api web

  new_api_image="$(image_id metaharmonizer-api:latest)"
  new_web_image="$(image_id metaharmonizer-web:latest)"
  [[ "$(image_revision "$new_api_image")" == "$target_commit" ]] ||
    fail "Built API image lacks the expected revision label"
  [[ "$(image_revision "$new_web_image")" == "$target_commit" ]] ||
    fail "Built web image lacks the expected revision label"
fi

log "Running target-image preflight checks"
"${compose[@]}" run --rm --no-deps api python -m pip check
"${compose[@]}" run --rm --no-deps api \
  python -m scripts.kb_probe
"${compose[@]}" run --rm --no-deps api \
  sh -c 'test "$(alembic heads | awk '\''NF {print $1; exit}'\'')" = "'"$expected_target_db_revision"'"'

log "Beginning controlled application cutover"
if [[ "$mode" == "schema" ]]; then
  schema_migration_started=1
  "${compose[@]}" run --rm --no-deps api \
    alembic upgrade "$expected_schema_to"
else
  "${compose[@]}" run --rm --no-deps api alembic upgrade head
fi
clear_web_revision_marker
"${compose[@]}" run --rm web
"${compose[@]}" up -d --no-deps --force-recreate api worker caddy

log "Verifying live image identity and public readiness"
wait_healthy || fail "API and worker did not become healthy"
wait_public || fail "Public readiness did not recover"
live_api_image="$(running_service_image api)"
live_worker_image="$(running_service_image worker)"
[[ "$live_api_image" == "$new_api_image" ]] ||
  fail "Running API container does not use the target image"
[[ "$live_worker_image" == "$new_api_image" ]] ||
  fail "Running worker container does not use the target image"
web_revision_matches "$target_web_revision" ||
  fail "Caddy is not serving the target web revision"
verify_public_readiness ||
  fail "Public readiness response did not report status=ok"

log "Running mandatory production audit"
"${compose[@]}" exec -T api \
  python -m scripts.production_audit --origin "${DEPLOY_BASE_URL%/}"

final_db_revision="$(database_revision)"
[[ "$final_db_revision" == "$expected_target_db_revision" ]] ||
  fail "Database revision does not match the expected deployment target"

finalize_checkout
restart_kb_timer
success_tool_source="$repo_root/scripts/deploy_revision.sh"
if [[ "$mode" == "rollback" ]]; then
  success_tool_source="$stable_tool"
fi
commit_success_state "$success_tool_source" \
  "$target_commit" "$new_api_image" "$new_web_image" \
  "$final_db_revision" "$target_web_revision" \
  "$deployed_commit" "$deployed_api_image" "$deployed_web_image" \
  "$deployed_db_revision" "$deployed_web_revision"

log "Deployment succeeded"
log "Revision: ${target_commit}"
log "API image: ${new_api_image}"
log "Web image: ${new_web_image}"
log "Rollback tags: metaharmonizer-api:rollback, metaharmonizer-web:rollback"
