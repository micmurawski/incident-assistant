#!/usr/bin/env bash
set -euo pipefail

export NAMESPACE="application"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
: "${O8S_ROOT:=$REPO_ROOT}"
JSON_FILE="${O8S_ROOT}/api_key.json"

echo "Ensuring namespace '${NAMESPACE}' has Linkerd injection enabled..."
kubectl label namespace "${NAMESPACE}" linkerd.io/inject=enabled --overwrite
kubectl annotate namespace "${NAMESPACE}" linkerd.io/inject=enabled --overwrite



bash -e "${SCRIPT_DIR}/../services/robot-shop/k8s/deploy.sh"

# Optional: restart workloads after deploy (disabled by default to avoid
# triggering a full rolling update that can leave old/new pods co-existing
# when cluster capacity is tight).
RESTART_AFTER_DEPLOY="${RESTART_AFTER_DEPLOY:-false}"
if [[ "${RESTART_AFTER_DEPLOY}" == "true" ]]; then
  echo "Restarting deployments in '${NAMESPACE}' (RESTART_AFTER_DEPLOY=true)..."
  kubectl rollout restart deployment -n "${NAMESPACE}"
  kubectl rollout status deployment -n "${NAMESPACE}" --timeout=300s
fi

SVC_NAME="web"
EXTERNAL_IP=$(kubectl get svc $SVC_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "Web service is available at: $EXTERNAL_IP"
export HOST="http://$EXTERNAL_IP:8080"
jq '. += {"web_host": "'$HOST'"}' $JSON_FILE > $JSON_FILE.tmp && mv $JSON_FILE.tmp $JSON_FILE
