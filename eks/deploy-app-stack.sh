export NAMESPACE="application"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
: "${O8S_ROOT:=$REPO_ROOT}"
JSON_FILE="${O8S_ROOT}/api_key.json"

bash -e "${SCRIPT_DIR}/../services/robot-shop/k8s/deploy.sh"

SVC_NAME="web"
EXTERNAL_IP=$(kubectl get svc $SVC_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "Web service is available at: $EXTERNAL_IP"
export HOST="http://$EXTERNAL_IP:8080"
jq '. += {"web_host": "'$HOST'"}' $JSON_FILE > $JSON_FILE.tmp && mv $JSON_FILE.tmp $JSON_FILE
