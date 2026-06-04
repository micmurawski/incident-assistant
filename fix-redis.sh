#!/usr/bin/env bash

# Scale all deployments and redis statefulset down to 0
# exit 0

./eks/delete-load-gen.sh

kubectl -n application scale statefulset redis --replicas=0
kubectl scale deployment shipping -n application --replicas=0
kubectl scale deployment shipping -n application --replicas=1
kubectl scale deployment web -n application --replicas=0
kubectl scale deployment catalogue -n application --replicas=0
kubectl scale deployment payment -n application --replicas=0
kubectl scale deployment rabbitmq -n application --replicas=0
kubectl scale deployment ratings -n application --replicas=0
kubectl scale deployment user -n application --replicas=0
kubectl scale deployment cart -n application --replicas=0
kubectl scale deployment dispatch -n application --replicas=0

# Wait for redis to scale down before proceeding
kubectl -n application rollout status statefulset redis --timeout=120s

# Delete redis data
kubectl -n application delete pvc data-redis-0

# Gradually bring everything up, with a pause between each
kubectl -n application scale statefulset redis --replicas=1
sleep 10
kubectl scale deployment payment -n application --replicas=1
sleep 10
kubectl scale deployment web -n application --replicas=1
sleep 10
kubectl scale deployment catalogue -n application --replicas=1
sleep 10
kubectl scale deployment rabbitmq -n application --replicas=1
sleep 10
kubectl scale deployment ratings -n application --replicas=1
sleep 10
kubectl scale deployment user -n application --replicas=1
sleep 10
kubectl scale deployment cart -n application --replicas=1
sleep 10
kubectl scale deployment dispatch -n application --replicas=1

# Show redis pod status after bringing up
kubectl -n application get pods -l app=redis -o wide



#./eks/deploy-load-gen.sh