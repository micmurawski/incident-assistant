#!/bin/bash
set -e

echo "Adding Grafana Helm repository..."
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

#helm show values grafana/loki-stack > loki-values.yaml

echo "Helm repositories configured successfully!"