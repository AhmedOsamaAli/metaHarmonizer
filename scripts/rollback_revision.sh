#!/usr/bin/env bash
# Compatibility entry point for the shared state-aware deployment engine.
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ROLLBACK_BASE_URL=https://host ROLLBACK_DRY_RUN=1 $0 <git-ref>" >&2
  exit 64
fi

: "${ROLLBACK_BASE_URL:?Set ROLLBACK_BASE_URL to the public HTTPS origin}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
state_dir="${DEPLOY_STATE_DIR:-${HOME}/.local/state/metaharmonizer/deploy}"
stable_tool="${state_dir}/bin/deploy_revision.sh"
export DEPLOY_BASE_URL="$ROLLBACK_BASE_URL"
export DEPLOY_DRY_RUN="${ROLLBACK_DRY_RUN:-0}"
export DEPLOY_REPO_ROOT="$repo_root"

if [[ -x "$stable_tool" ]]; then
  exec "$stable_tool" --rollback "$1"
fi
exec "${script_dir}/deploy_revision.sh" --rollback "$1"
