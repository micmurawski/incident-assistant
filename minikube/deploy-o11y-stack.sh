#!/bin/bash
set -x

export NAMESPACE="monitoring"

# Deploy o11y stack on the dedicated monitoring node (EKS).
# Set DEPLOY_ON_MONITORING_NODE=1 when your cluster has a node group with
# label role=monitoring and taint dedicated=monitoring:NO_SCHEDULE (see aws/main.tf).
DEPLOY_ON_MONITORING_NODE="${DEPLOY_ON_MONITORING_NODE:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_VALUES=()
VIZ_VALUES=()
if [[ "$DEPLOY_ON_MONITORING_NODE" == "1" ]]; then
  MONITORING_VALUES=(-f "${SCRIPT_DIR}/values-o11y-monitoring-node.yaml")
  VIZ_VALUES=(-f "${SCRIPT_DIR}/values-viz-monitoring-node.yaml")
  echo "Scheduling o11y stack on monitoring node (nodeSelector role=monitoring, toleration dedicated=monitoring)"
fi

echo "Setting up Grafana with Linkerd metrics support..."

# Add Helm repositories
helm repo add grafana https://grafana.github.io/helm-charts

kubectl create namespace ${NAMESPACE}
# helm upgrade --install loki grafana/loki-stack -n ${NAMESPACE} --set grafana.enabled=true --set prometheus.enabled=true


linkerd check --pre
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/standard-install.yaml
linkerd install --crds | kubectl apply -f -
linkerd install --set proxyInit.runAsRoot=true | kubectl apply -f -
linkerd check


linkerd viz install "${VIZ_VALUES[@]}" | kubectl apply -f -
linkerd check


helm upgrade --install loki grafana/loki-stack \
  --namespace=${NAMESPACE} \
  --create-namespace \
  --set grafana.enabled=true \
  --set prometheus.enabled=false \
  --set grafana.adminPassword='admin' \
  --set promtail.enabled=true \
  --set loki.isDefault=false \
  -f data-sources.yml \
  "${MONITORING_VALUES[@]}"



kubectl -n linkerd-viz patch deployment prometheus \
  --type merge \
  -p '{"spec": {"template": {"metadata": {"annotations": {"config.linkerd.io/skip-inbound-ports": "9090"}}}}}'


kubectl -n linkerd-viz rollout status deploy/prometheus


kubectl run -i --tty --rm debug-curl --image=curlimages/curl --restart=Never -n ${NAMESPACE} -- \
  curl -v "http://prometheus.linkerd-viz.svc.cluster.local:9090/api/v1/query?query=up"

#
#
##kubectl get secret --namespace ${NAMESPACE} loki-grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
#
#linkerd install --crds | kubectl apply -f -
#linkerd install --set proxyInit.runAsRoot=true --set prometheus.enabled=false,prometheusUrl="http://loki-prometheus-server.${NAMESPACE}.svc.cluster.local:9090" | kubectl apply -f -
#linkerd viz install | kubectl apply -f -
#linkerd viz install --set prometheusUrl="http://loki-prometheus-server.${NAMESPACE}.svc.cluster.local:9090",prometheus.enabled=false,grafana.url="http://loki-grafana.${NAMESPACE}.svc.cluster.local:3000" | kubectl apply -f -

#kubectl apply -f - <<EOF
#apiVersion: policy.linkerd.io/v1beta1
#kind: AuthorizationPolicy
#metadata:
#  name: allow-grafana
#  namespace: linkerd-viz
#spec:
#  targetRef:
#    group: ""
#    kind: Namespace
#    name: linkerd-viz
#  rules:
#  - from:
#    - principalName: monitoring:grafana
#    toRoutes:
#    - name: allow-all
#EOF