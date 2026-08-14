#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
bundle_url=${KB_DEPLOY_BUNDLE_URL:-https://github.com/AhmedOsamaAli/metaHarmonizer/releases/download/kb-latest/kb_offline_bundle.tar.gz}
checksum_url=${KB_DEPLOY_CHECKSUM_URL:-https://github.com/AhmedOsamaAli/metaHarmonizer/releases/download/kb-latest/kb_offline_bundle.sha256}
state_dir=${KB_DEPLOY_STATE_DIR:-${HOME}/.local/state/metaharmonizer/kb-deploy}
lock_file=${KB_DEPLOY_LOCK_FILE:-/tmp/metaharmonizer-kb-deploy.lock}
keep_releases=${KB_DEPLOY_KEEP_RELEASES:-2}

mkdir -p "$state_dir"
exec 9>"$lock_file"
flock -n 9 || { echo "Another KB deployment is active; exiting."; exit 0; }

tmp=$(mktemp -d)
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

curl -fsSL --retry 5 --retry-delay 2 "$checksum_url" -o "$tmp/bundle.sha256"
target_sha=$(awk 'NF {print $1; exit}' "$tmp/bundle.sha256")
[[ "$target_sha" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "Invalid published KB checksum." >&2; exit 1; }
target_sha=${target_sha,,}
short_sha=${target_sha:0:12}

current_sha=$(sed -nE 's/^KB_BUNDLE_SHA256=([0-9a-fA-F]{64}).*/\1/p' .env | tail -1 | tr 'A-F' 'a-f')
if [[ "$current_sha" == "$target_sha" && "${KB_DEPLOY_FORCE:-0}" != "1" ]]; then
  echo "KB_ALREADY_CURRENT sha256=$target_sha"
  exit 0
fi
if [[ "${KB_DEPLOY_DRY_RUN:-0}" == "1" ]]; then
  echo "KB_UPDATE_AVAILABLE current=${current_sha:-none} target=$target_sha"
  exit 0
fi

bundle="$tmp/kb_offline_bundle.tar.gz"
curl -fsSL --retry 5 --retry-delay 2 "$bundle_url" -o "$bundle"
printf '%s  %s\n' "$target_sha" "$bundle" | sha256sum -c -

new_engine="metaharmonizer_engine_cache_${short_sha}"
new_corpus="metaharmonizer_corpus_data_${short_sha}"
new_hf="metaharmonizer_hf_cache_${short_sha}"
for volume in "$new_engine" "$new_corpus" "$new_hf"; do docker volume create "$volume" >/dev/null; done

stage_env="$tmp/stage.env"
cp .env "$stage_env"
write_deploy_env() {
  local file=$1 sha=$2 engine=$3 corpus=$4 hf=$5 replacement
  replacement=$(mktemp "$(dirname "$file")/.env.XXXXXX")
  sed -E '/^(KB_BUNDLE_SHA256|ENGINE_CACHE_VOLUME|CORPUS_DATA_VOLUME|HF_CACHE_VOLUME)=/d' "$file" > "$replacement"
  printf 'KB_BUNDLE_SHA256=%s\nENGINE_CACHE_VOLUME=%s\nCORPUS_DATA_VOLUME=%s\nHF_CACHE_VOLUME=%s\n' \
    "$sha" "$engine" "$corpus" "$hf" >> "$replacement"
  chmod 600 "$replacement"
  mv "$replacement" "$file"
}
restore_env() {
  local source=$1 destination=$2 replacement
  replacement=$(mktemp "$(dirname "$destination")/.env.XXXXXX")
  cp "$source" "$replacement"
  chmod 600 "$replacement"
  mv "$replacement" "$destination"
}
write_deploy_env "$stage_env" "$target_sha" "$new_engine" "$new_corpus" "$new_hf"

stage_compose=(docker compose --env-file "$stage_env" -f docker-compose.yml -f docker-compose.prod.yml)
"${stage_compose[@]}" --profile kb run --rm \
  -v "$bundle:/tmp/kb_offline_bundle.tar.gz:ro" \
  -e KB_BUNDLE_URL= \
  -e KB_ARCHIVE=__staged_candidate_only__ \
  kb-import

"${stage_compose[@]}" run --rm --no-deps \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  api python -m scripts.kb_probe

old_engine=$(sed -nE 's/^ENGINE_CACHE_VOLUME=(.+)$/\1/p' .env | tail -1)
old_corpus=$(sed -nE 's/^CORPUS_DATA_VOLUME=(.+)$/\1/p' .env | tail -1)
old_hf=$(sed -nE 's/^HF_CACHE_VOLUME=(.+)$/\1/p' .env | tail -1)
old_engine=${old_engine:-metaharmonizer_engine_cache}
old_corpus=${old_corpus:-metaharmonizer_corpus_data}
old_hf=${old_hf:-metaharmonizer_hf_cache}
cp .env "$tmp/original.env"

rollback() {
  local code=$?
  trap - ERR
  echo "KB deployment failed; restoring previous volumes." >&2
  restore_env "$tmp/original.env" .env
  "${compose[@]}" up -d --no-deps --force-recreate api worker || true
  exit "$code"
}
trap rollback ERR

write_deploy_env .env "$target_sha" "$new_engine" "$new_corpus" "$new_hf"
"${compose[@]}" up -d --no-deps --force-recreate api worker

for _ in $(seq 1 90); do
  api_id=$("${compose[@]}" ps -q api)
  worker_id=$("${compose[@]}" ps -q worker)
  api_health=$(docker inspect -f '{{.State.Health.Status}}' "$api_id" 2>/dev/null || true)
  worker_health=$(docker inspect -f '{{.State.Health.Status}}' "$worker_id" 2>/dev/null || true)
  [[ "$api_health" == healthy && "$worker_health" == healthy ]] && break
  sleep 2
done
[[ "$api_health" == healthy && "$worker_health" == healthy ]]
"${compose[@]}" exec -T api curl -fsS http://localhost:8000/healthz >/dev/null

snapshot_source=$("${compose[@]}" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "select source from ontology_snapshots where is_current is true limit 1"')
[[ "$snapshot_source" == "$target_sha" ]] || {
  echo "Current ontology snapshot does not match deployed bundle: $snapshot_source" >&2
  false
}

trap - ERR
printf '%s\n' "$target_sha" > "$state_dir/current.sha256"
printf '%s\n' "$old_engine" "$old_corpus" "$old_hf" > "$state_dir/previous-volumes"
history="$state_dir/releases"
{
  printf '%s\n' "$short_sha"
  [[ -f "$history" ]] && cat "$history"
} | awk 'NF && !seen[$0]++' | head -n "$keep_releases" > "$history.tmp"
mv "$history.tmp" "$history"

mapfile -t release_shas < <(docker volume ls --format '{{.Name}}' \
  | sed -nE 's/^metaharmonizer_engine_cache_([0-9a-f]{12})$/\1/p' \
  | sort -u || true)
if (( ${#release_shas[@]} > keep_releases )); then
  for sha in "${release_shas[@]}"; do
    grep -qxF "$sha" "$history" && continue
    docker volume rm \
      "metaharmonizer_engine_cache_${sha}" \
      "metaharmonizer_corpus_data_${sha}" \
      "metaharmonizer_hf_cache_${sha}" >/dev/null 2>&1 || true
  done
fi

echo "KB_DEPLOY_OK sha256=$target_sha previous=${current_sha:-none}"
