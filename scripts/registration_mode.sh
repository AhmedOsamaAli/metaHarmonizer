#!/usr/bin/env bash
# Open or close new-account registration in one command.
#
#   scripts/registration_mode.sh status
#   scripts/registration_mode.sh close                       # invite-only
#   scripts/registration_mode.sh open --domains mskcc.org    # named domains
#   scripts/registration_mode.sh open --domains '*'          # anyone verified
#
# Closing registration does not sign out or disable existing accounts; use admin
# account deactivation for that.
set -Eeuo pipefail

usage() {
  echo "Usage: $0 status|close|open [--domains \"a.org,b.org\"]" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
command=$1
shift
domains=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --domains)
      [[ $# -ge 2 ]] || usage
      domains=$2
      shift 2
      ;;
    *) usage ;;
  esac
done

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"
env_file=${REGISTRATION_ENV_FILE:-.env}
[[ -f "$env_file" ]] || { echo "Missing $env_file" >&2; exit 1; }

# COMPOSE_FILE is not set in a non-interactive shell, so the production overlay
# must be named explicitly or Compose would apply the dev override.
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

current_value() {
  sed -nE 's/^ALLOWED_EMAIL_DOMAINS=(.*)$/\1/p' "$env_file" | tail -1
}

describe() {
  local value=$1
  if [[ -z "$value" ]]; then
    echo "closed (invite-only: no new self-registration is approved)"
  elif [[ "$value" == "*" ]]; then
    echo "open to any verified email address"
  else
    echo "open to: $value"
  fi
}

if [[ "$command" == "status" ]]; then
  value=$(current_value)
  echo "ALLOWED_EMAIL_DOMAINS=${value}"
  echo "Registration is $(describe "$value")"
  running=$("${compose[@]}" exec -T api sh -lc 'printf %s "${ALLOWED_EMAIL_DOMAINS-}"' 2>/dev/null || true)
  echo "Running API has: ${running:-<unset>}"
  [[ "$running" == "$value" ]] || echo "WARNING: the running API does not match $env_file; recreate the API."
  exit 0
fi

case $command in
  close) new_value="" ;;
  open)
    [[ -n "$domains" ]] || { echo "open requires --domains" >&2; exit 2; }
    new_value=$domains
    ;;
  *) usage ;;
esac

previous_value=$(current_value)
if [[ "$previous_value" == "$new_value" ]]; then
  echo "Registration is already $(describe "$new_value"); nothing to do."
  exit 0
fi

backup="${env_file}.registration-backup"
cp -p "$env_file" "$backup"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
if grep -qE '^ALLOWED_EMAIL_DOMAINS=' "$env_file"; then
  sed -E "s|^ALLOWED_EMAIL_DOMAINS=.*$|ALLOWED_EMAIL_DOMAINS=${new_value}|" "$env_file" > "$tmp"
else
  cat "$env_file" > "$tmp"
  printf 'ALLOWED_EMAIL_DOMAINS=%s\n' "$new_value" >> "$tmp"
fi
cat "$tmp" > "$env_file"

restore() {
  echo "Restoring the previous registration setting." >&2
  cat "$backup" > "$env_file"
  "${compose[@]}" up -d --no-deps --wait api >/dev/null 2>&1 || true
}

if ! "${compose[@]}" up -d --no-deps --wait api; then
  restore
  echo "API did not become healthy; previous setting restored." >&2
  exit 1
fi

applied=$("${compose[@]}" exec -T api sh -lc 'printf %s "${ALLOWED_EMAIL_DOMAINS-}"' 2>/dev/null || true)
if [[ "$applied" != "$new_value" ]]; then
  restore
  echo "API is running with '${applied}' instead of '${new_value}'; previous setting restored." >&2
  exit 1
fi

health_url=${REGISTRATION_HEALTH_URL:-https://metaharmonizer.online/healthz}
if ! curl -fsS -o /dev/null "$health_url"; then
  restore
  echo "Public health check failed; previous setting restored." >&2
  exit 1
fi

echo "Registration is now $(describe "$new_value")"
echo "Previous setting kept at $backup"
