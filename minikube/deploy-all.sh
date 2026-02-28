#!/bin/bash
set -e

echo "Starting full deployment of Grafana with Loki on Minikube..."

export REPO=${REPO:-"robotshop"}
export TAG=${TAG:-"2.2.0"}
#eval $(minikube -p minikube docker-env)

# Run all the setup and deployment scripts in sequence
./start-minikube.sh
./deploy-o11y-stack.sh
./deploy-robot-shop.sh
./deploy-chaos-mesh.sh


echo "Deployment complete! Here's how to access your services:"

# Get Grafana access details
GRAFANA_PASSWORD=$(kubectl get secret --namespace monitoring loki-grafana -o jsonpath="{.data.admin-password}" | base64 --decode)


echo "-------------------------------------------"
echo "Run: minikube service loki-grafana -n monitoring"
echo "Username: admin"
echo "Password: $GRAFANA_PASSWORD"
echo "-------------------------------------------"

echo "-------------------------------------------"
echo "Make tunnel: sudo minikube tunnel"
echo "http://localhost:8080"
echo "-------------------------------------------"
