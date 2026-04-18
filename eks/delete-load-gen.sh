#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export REPO="${REPO:-189429133920.dkr.ecr.us-east-1.amazonaws.com}"
export TAG="${TAG:-latest}"

echo "Deleting load generator from 'bastion' namespace..."
echo "REPO: ${REPO}"
echo "TAG: ${TAG}"

# Also clean up any previous load-gen that may have been deployed into the
# 'application' namespace during the short-lived Option A/B experiment.
kubectl delete deployment load-gen -n application --ignore-not-found

envsubst < "${SCRIPT_DIR}/load-gen-bastion.yaml" | kubectl delete -f -