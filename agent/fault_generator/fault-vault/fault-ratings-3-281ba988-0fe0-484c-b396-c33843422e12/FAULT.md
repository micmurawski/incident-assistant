# Fault: Ratings Service Liveness and Readiness Probe Path Misconfiguration

## Description
In the Kubernetes manifest `k8s/robot-shop-eks.yaml`, the `livenessProbe` and `readinessProbe` paths for the ratings Deployment were changed from `/_health` to `/health`.

## Symptom
- Liveness and readiness probes will continuously fail with 404 Not Found errors.
- The ratings pod will never become ready and will be marked as `Unhealthy`.
- The ratings pod will be restarted repeatedly by Kubernetes due to liveness probe failures.
- The ratings service will be unreachable because the pod is never added to the Service endpoints.

## Root Cause
The ratings container exposes its health check endpoint at `/_health` (as defined in `ratings/html/src/Controller/HealthController.php`), but the Kubernetes probes are configured to check `/health`. This mismatch causes Kubernetes to receive 404 responses for health checks, leading it to conclude the container is unhealthy and needs to be restarted.

## Fix
Update the `livenessProbe` and `readinessProbe` paths in the ratings Deployment back to `/_health`:
1. Change liveness probe `path` from `/health` to `/_health`
2. Change readiness probe `path` from `/health` to `/_health`
