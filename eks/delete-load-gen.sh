#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export REPO="${REPO:-189429133920.dkr.ecr.us-east-1.amazonaws.com}"
export TAG="${TAG:-latest}"

echo "Deploying load generator to bastion namespace..."
echo "REPO: ${REPO}"
echo "TAG: ${TAG}"

envsubst < ${SCRIPT_DIR}/load-gen-bastion.yaml | kubectl delete -f -