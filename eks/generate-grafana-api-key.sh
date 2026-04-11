#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
: "${O8S_ROOT:=$REPO_ROOT}"

NAMESPACE="bastion"
SVC_NAME="loki-grafana"
ADMIN_USER="admin"
PROTOCOL="http"

echo "Fetching Grafana admin password..."
ADMIN_PASS="admin"
echo "Fetching External IP..."
EXTERNAL_IP=""

while [ -z "$EXTERNAL_IP" ]; do
  EXTERNAL_IP=$(kubectl get svc $SVC_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
  
  if [ -z "$EXTERNAL_IP" ]; then
    echo "Waiting for External IP to be provisioned... checking again in 5 seconds."
    sleep 5
  fi
done

GRAFANA_URL="${PROTOCOL}://${EXTERNAL_IP}"
echo "Grafana is available at: $GRAFANA_URL"

echo "Creating Service Account..."
SA_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"name": "my-automation-sa", "role": "Admin"}' \
  $GRAFANA_URL/api/serviceaccounts \
  -u "$ADMIN_USER:$ADMIN_PASS")
echo $SA_RESPONSE
SA_ID=$(echo $SA_RESPONSE | jq -r .id)
echo $SA_ID
echo "Generating Token..."
TOKEN_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"name": "my-automation-token"}' \
  $GRAFANA_URL/api/serviceaccounts/$SA_ID/tokens \
  -u "$ADMIN_USER:$ADMIN_PASS")
echo $TOKEN_RESPONSE
TOKEN=$(echo $TOKEN_RESPONSE | jq -r .key)

#echo "Saving Token to Kubernetes Secret..."
#kubectl create secret generic grafana-api-token \
#  --from-literal=token=$TOKEN \
#  -n $NAMESPACE \
#  --dry-run=client -o yaml | kubectl apply -f -
# add grafana_api_token to ${O8S_ROOT}/api_key.json

JSON_FILE="${O8S_ROOT}/api_key.json"
jq '. += {"grafana_api_token": "'$TOKEN'"}' $JSON_FILE > $JSON_FILE.tmp && mv $JSON_FILE.tmp $JSON_FILE
jq '. += {"grafana_url": "'$GRAFANA_URL'"}' $JSON_FILE > $JSON_FILE.tmp && mv $JSON_FILE.tmp $JSON_FILE
echo "Done! The API token is securely stored."