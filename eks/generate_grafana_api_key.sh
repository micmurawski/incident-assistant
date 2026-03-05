NAMESPACE="bastion"

#!/bin/bash

SVC_NAME="grafana" # Ensure this matches your Service name
ADMIN_USER="admin"
PROTOCOL="http" # Change to https if your LoadBalancer handles TLS

# 1. Extract the admin password securely from Kubernetes
echo "Fetching Grafana admin password..."
ADMIN_PASS=$(kubectl get secret grafana -n $NAMESPACE -o jsonpath="{.data.admin-password}" | base64 --decode)

# 2. Dynamically fetch the External IP (with a wait loop)
echo "Fetching External IP..."
EXTERNAL_IP=""

while [ -z "$EXTERNAL_IP" ]; do
  # Try to get IP first, then fallback to hostname (for AWS compatibility)
  EXTERNAL_IP=$(kubectl get svc $SVC_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
  if [ -z "$EXTERNAL_IP" ]; then
    EXTERNAL_IP=$(kubectl get svc $SVC_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
  fi
  
  if [ -z "$EXTERNAL_IP" ]; then
    echo "Waiting for External IP to be provisioned... checking again in 5 seconds."
    sleep 5
  fi
done

GRAFANA_URL="${PROTOCOL}://${EXTERNAL_IP}"
echo "Grafana is available at: $GRAFANA_URL"

# 3. Create the Service Account
echo "Creating Service Account..."
SA_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"name": "my-automation-sa", "role": "Admin"}' \
  $GRAFANA_URL/api/serviceaccounts \
  -u "$ADMIN_USER:$ADMIN_PASS")

SA_ID=$(echo $SA_RESPONSE | jq -r .id)

# 4. Generate the Token 
echo "Generating Token..."
TOKEN_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"name": "my-automation-token"}' \
  $GRAFANA_URL/api/serviceaccounts/$SA_ID/tokens \
  -u "$ADMIN_USER:$ADMIN_PASS")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r .key)

# 5. Save the new token back into a Kubernetes Secret
echo "Saving Token to Kubernetes Secret..."
kubectl create secret generic grafana-api-token \
  --from-literal=token=$TOKEN \
  -n $NAMESPACE \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Done! The API token is securely stored."