#!/usr/bin/env bash
# Delete all Chaos Mesh experiments cluster-wide, then merge-patch finalizers to null on any
# remaining objects (e.g. stuck in Terminating). Order: delete first, then patch.
#
# Usage:
#   ./cleanup-chaos-experiments.sh [--dry-run]
#
# Requires: kubectl, jq

set -euo pipefail

RESOURCES="podchaos,networkchaos,stresschaos,iochaos,httpchaos"
RESOURCE_TYPES=(podchaos networkchaos stresschaos iochaos httpchaos)
PATCH='{"metadata":{"finalizers":null}}'

DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help)
      cat <<'EOF'
Delete all Chaos Mesh experiments (-A), then clear metadata.finalizers on any leftovers.

Usage:
  cleanup-chaos-experiments.sh [--dry-run]

  --dry-run   Print kubectl commands without running.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

delete_all() {
  local -a cmd=(kubectl delete "$RESOURCES" "--all" "-A" "--wait=false")
  if [[ "$DRY_RUN" == true ]]; then
    printf '%q ' "${cmd[@]}"
    printf '\n'
  else
    "${cmd[@]}" || echo "WARN: delete step exited non-zero (continuing to patch step)" >&2
  fi
}

patch_finalizers() {
  local kind ns name json
  patch_one() {
    local k=$1 ns=$2 name=$3
    local -a cmd
    if [[ -z "$ns" ]]; then
      cmd=(kubectl patch "$k" "$name" -p "$PATCH" --type=merge)
    else
      cmd=(kubectl patch "$k" "$name" -n "$ns" -p "$PATCH" --type=merge)
    fi
    if [[ "$DRY_RUN" == true ]]; then
      printf '%q ' "${cmd[@]}"
      printf '\n'
    else
      "${cmd[@]}" || echo "WARN: patch failed for ${k} ${ns:+$ns/}${name}" >&2
    fi
  }

  for kind in "${RESOURCE_TYPES[@]}"; do
    json=$(
      kubectl get "$kind" -A -o json 2>/dev/null \
        || kubectl get "$kind" -o json 2>/dev/null \
        || echo '{"items":[]}'
    )
    while IFS=$'\t' read -r ns name; do
      [[ -z "${name:-}" ]] && continue
      patch_one "$kind" "$ns" "$name"
    done < <(
      echo "$json" | jq -r '
        .items[]?
        | select(.metadata.finalizers != null)
        | [(.metadata.namespace // ""), .metadata.name]
        | @tsv
      '
    )
  done
}

echo "== Step 1: delete all Chaos Mesh experiments (cluster-wide) ==" >&2
delete_all

echo "== Step 2: clear finalizers on any remaining experiments ==" >&2
patch_finalizers

echo "Done." >&2
