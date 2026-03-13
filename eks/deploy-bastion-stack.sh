set -e
export NAMESPACE="bastion"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_VALUES=(-f "${SCRIPT_DIR}/values-o11y-monitoring-node.yaml")
VIZ_VALUES=(-f "${SCRIPT_DIR}/values-viz-monitoring-node.yaml")

kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace application --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace ${NAMESPACE} config.linkerd.io/admission-webhooks=disabled --overwrite
# check if ca.crt and ca.key exist
if [ ! -f "ca.crt" ] || [ ! -f "ca.key" ]; then
  echo "Creating CA..."
  step certificate create root.linkerd.cluster.local ca.crt ca.key --profile root-ca --no-password --insecure
fi

if [ ! -f "issuer.crt" ] || [ ! -f "issuer.key" ]; then
  echo "Creating Issuer..."
  step certificate create identity.linkerd.cluster.local issuer.crt issuer.key \
    --profile intermediate-ca --not-after 8760h --no-password --insecure \
    --ca ca.crt --ca-key ca.key --
fi

helm repo add grafana https://grafana.github.io/helm-charts
helm repo add linkerd https://helm.linkerd.io/stable
helm repo add linkerd-edge https://helm.linkerd.io/edge
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update


#helm upgrade --install linkerd-crds linkerd/linkerd-crds -n ${NAMESPACE} --wait
echo "Installing Gateway API..."
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/standard-install.yaml

echo "Installing Linkerd CRDs..."
helm upgrade --install linkerd-crds linkerd-edge/linkerd-crds -n ${NAMESPACE}

echo "Installing Linkerd Control Plane..."
helm upgrade --install linkerd-control-plane \
  -n ${NAMESPACE} \
  --set-file identityTrustAnchorsPEM=ca.crt \
  --set-file identity.issuer.tls.crtPEM=issuer.crt \
  --set-file identity.issuer.tls.keyPEM=issuer.key \
  linkerd-edge/linkerd-control-plane


echo "Installing Linkerd Viz..."
helm upgrade --install linkerd-viz linkerd/linkerd-viz -n ${NAMESPACE} ${VIZ_VALUES[@]}

# Escape newlines as \n so -----END CERTIFICATE----- is not parsed as YAML document separator (awk works on macOS and Linux)
export CA_CERT=$(awk '{printf "%s\\n", $0}' ca.crt)
envsubst < ${SCRIPT_DIR}/linkerd-config-map.yml | kubectl apply -f -

# linkerd check --linkerd-namespace ${NAMESPACE}

echo "Installing Loki..."
helm upgrade --install loki grafana/loki-stack \
  --namespace=${NAMESPACE} \
  "${MONITORING_VALUES[@]}"

echo "Installing Chaos Mesh..."

helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
  -n ${NAMESPACE} \
  -f "${SCRIPT_DIR}/values-chaos-mesh-bastion.yaml" --wait


echo "Patching Linkerd Viz..."
#kubectl -n ${NAMESPACE} patch deployment prometheus \
#  --type merge \
#  -p '{"spec": {"template": {"metadata": {"annotations": {"config.linkerd.io/skip-inbound-ports": "9090"}}}}}'

# Tap listens on 8089 but service targets 8088; proxy forwards to wrong port.
# Skip proxy for 8089 and point service at tap's real port.
#kubectl -n bastion patch deployment tap --type merge \
#  -p '{"spec": {"template": {"metadata": {"annotations": {"config.linkerd.io/skip-inbound-ports": "8088"}}}}}'

#kubectl -n ${NAMESPACE} patch svc tap --type merge \
#  -p '{"spec": {"ports": [{"name": "linkerd-tap", "port": 8088, "targetPort": 8089}]}}'

echo "Waiting for Linkerd Viz to be ready..."
kubectl -n ${NAMESPACE} rollout status deploy/prometheus

echo "Installing Chaos Mesh RBAC..."
kubectl apply -f "${SCRIPT_DIR}/chaos-meshr-rbac.yml"
kubectl apply -f "${SCRIPT_DIR}/incident-assistant-rbac.yml"
kubectl create token account-cluster-manager-zqqat --duration=8760h -n ${NAMESPACE} > cluster-manager-token.txt
kubectl create secret generic account-cluster-manager-zqqat --from-file=token=cluster-manager-token.txt --dry-run=client -o yaml -n ${NAMESPACE} | kubectl apply -f -
kubectl describe secrets account-cluster-manager-zqqat -n ${NAMESPACE}

echo "Annotating application namespace for Linkerd injection..."

kubectl annotate namespace application linkerd.io/inject=enabled

kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

