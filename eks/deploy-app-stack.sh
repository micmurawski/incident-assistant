export NAMESPACE="application"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl apply -f ${SCRIPT_DIR}/../services/robot-shop/k8s/robot-shop-eks.yaml
