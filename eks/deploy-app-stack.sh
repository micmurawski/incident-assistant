export NAMESPACE="application"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${SCRIPT_DIR}/../services/robot-shop/k8s/build-and-push.sh"
bash "${SCRIPT_DIR}/../services/robot-shop/k8s/deploy-eks-manifest.sh"
