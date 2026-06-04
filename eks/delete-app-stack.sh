#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-application}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Deleting Robot Shop resources from namespace '${NAMESPACE}'..."

# Keep delete scope aligned with deploy path in eks/deploy-app-stack.sh.
export NAMESPACE
bash -e "${SCRIPT_DIR}/../services/robot-shop/k8s/delete.sh"

echo "Robot Shop cleanup complete in namespace '${NAMESPACE}'."