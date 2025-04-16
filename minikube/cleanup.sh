#!/bin/bash
set -e

echo "Removing Grafana, Loki deployments..."
helm uninstall loki --namespace monitoring

echo "Removing monitoring namespace..."
kubectl delete namespace monitoring

echo "Resources have been cleaned up successfully!"
echo "To stop Minikube, run: minikube stop"
echo "To delete the Minikube cluster, run: minikube delete"
minikube stop
minikube delete