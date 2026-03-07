# Fault: Catalogue Service Liveness Probe Path Misconfiguration

## Description
The `livenessProbe` path for the `catalogue` deployment in `k8s/robot-shop-eks.yaml` was changed from `/health` to `/healthz`.

## Symptom
- The `catalogue` service pods will continuously restart.
- The `catalogue` service will be marked as unhealthy by Kubernetes.
- The Robot Shop frontend will not be able to display product listings, as the catalogue service will be unreachable or unhealthy.

## Root Cause
The `catalogue` service's liveness probe is configured to check the `/healthz` endpoint, which does not exist or is not the correct health check endpoint for the application. This causes the liveness probe to fail repeatedly, leading Kubernetes to believe the pod is unhealthy and restart it.

## Fix
Revert the `livenessProbe` path in the `catalogue` deployment to the correct endpoint:
```yaml
        livenessProbe:
          httpGet:
            path: /health
            port: 8080