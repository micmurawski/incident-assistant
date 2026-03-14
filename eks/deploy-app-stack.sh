export NAMESPACE="application"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JSON_FILE="/Users/micmur/GITHUB/o8s/api_key.json"

bash -e "${SCRIPT_DIR}/../services/robot-shop/k8s/build-and-push.sh"
bash -e "${SCRIPT_DIR}/../services/robot-shop/k8s/deploy-eks-manifests.sh"

SVC_NAME="web"
EXTERNAL_IP=$(kubectl get svc $SVC_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "Web service is available at: $EXTERNAL_IP"
export HOST="http://$EXTERNAL_IP:8080"
jq '. += {"web_host": "'$HOST'"}' $JSON_FILE > $JSON_FILE.tmp && mv $JSON_FILE.tmp $JSON_FILE
