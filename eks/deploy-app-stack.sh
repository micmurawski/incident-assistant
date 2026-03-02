export NAMESPACE="application"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl apply -f ${SCRIPT_DIR}/sample-app-application.yaml