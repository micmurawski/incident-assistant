#!/bin/bash
set -e

echo "Starting Minikube with sufficient resources..."
minikube start --cpus=4 --memory=8192 --driver=docker --kubernetes-version=stable --addons=metrics-server

echo "Enabling metrics-server addon for monitoring..."
minikube addons enable metrics-server

echo "Verifying cluster status..."
kubectl cluster-info
kubectl get nodes

echo "Minikube is ready for Grafana and Loki deployment!"