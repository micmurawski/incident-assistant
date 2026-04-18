#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export REPO="${REPO:-189429133920.dkr.ecr.us-east-1.amazonaws.com}"
export TAG="${TAG:-latest}"

echo "Deploying load generator to 'bastion' namespace (client-side Linkerd injection)..."
echo "REPO: ${REPO}"
echo "TAG: ${TAG}"

if ! command -v linkerd >/dev/null 2>&1; then
  echo "ERROR: 'linkerd' CLI not found in PATH. Install it (https://linkerd.io/2/getting-started/) so the proxy sidecar can be injected client-side." >&2
  exit 1
fi

# 'bastion' has config.linkerd.io/admission-webhooks=disabled, so the
# auto-injector never runs for this namespace. Inject the sidecar manually
# with `linkerd inject` before applying.
envsubst < "${SCRIPT_DIR}/load-gen-bastion.yaml" \
  | linkerd inject --linkerd-namespace bastion - \
  | kubectl apply -f -