#!/bin/bash
set -e

echo "Cleaning up Grafana, Loki, and Linkerd deployments..."

echo "Removing Linkerd Viz..."
helm uninstall linkerd-viz --namespace linkerd-viz 2>/dev/null || echo "Linkerd Viz not found"

echo "Removing Linkerd Control Plane..."
helm uninstall linkerd-control-plane --namespace linkerd 2>/dev/null || echo "Linkerd Control Plane not found"

echo "Removing Linkerd CRDs..."
helm uninstall linkerd-crds --namespace linkerd 2>/dev/null || echo "Linkerd CRDs not found"

echo "Removing Grafana and Loki..."
helm uninstall loki --namespace monitoring 2>/dev/null || echo "Loki not found"

echo "Removing namespaces..."
kubectl delete namespace linkerd-viz 2>/dev/null || echo "linkerd-viz namespace not found"
kubectl delete namespace linkerd 2>/dev/null || echo "linkerd namespace not found"
kubectl delete namespace monitoring 2>/dev/null || echo "monitoring namespace not found"
kubectl delete namespace robot-shop 2>/dev/null || echo "robot-shop namespace not found"

echo "Resources have been cleaned up successfully!"
echo "To stop Minikube, run: minikube stop"
echo "To delete the Minikube cluster, run: minikube delete"