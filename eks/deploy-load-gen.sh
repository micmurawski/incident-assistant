#!/usr/bin/env bash
set -euo pipefail

export REPO="${REPO:-189429133920.dkr.ecr.us-east-1.amazonaws.com}"
export TAG="${TAG:-latest}"

echo "Deploying load generator to bastion namespace..."
echo "REPO: ${REPO}"
echo "TAG: ${TAG}"

envsubst < eks/load-gen-bastion.yaml | kubectl apply -f -