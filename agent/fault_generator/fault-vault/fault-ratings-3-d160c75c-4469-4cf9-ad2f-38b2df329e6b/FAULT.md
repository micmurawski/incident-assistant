# Fault: Ratings Service Port Mismatch

## Description
In the Kubernetes manifest `k8s/robot-shop-eks.yaml`, the ratings Deployment container port was changed from `80` to `8080`, but the liveness probe, readiness probe, and Service target port were not updated to match. This creates a port mismatch between the actual container listening port and the ports that Kubernetes uses for health checks and service routing.

## Symptom
- Liveness and readiness probes will continuously fail with connection refused errors
- The ratings pod will be marked as `Unhealthy` and may be restarted repeatedly
- Kubernetes events will show `Unhealthy` status for the ratings pod
- The ratings service will be unreachable because the Service target port (80) doesn't match the container port (8080)

## Root Cause
The ratings container now listens on port 8080, but:
- Liveness probe checks port 80 (`port: 80`)
- Readiness probe checks port 80 (`port: 80`)  
- Service routes traffic to port 80 (`targetPort: 80`)

This mismatch means Kubernetes cannot verify the container is healthy, and traffic cannot reach the application.

## Fix
Update the following in the ratings Deployment and Service:
1. Change liveness probe `port` from `80` to `8080`
2. Change readiness probe `port` from `80` to `8080`
3. Change Service `targetPort` from `80` to `8080`
