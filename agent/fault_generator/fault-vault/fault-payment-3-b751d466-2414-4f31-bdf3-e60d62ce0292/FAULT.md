# Fault: Payment Service Liveness Probe Misconfiguration

## Description
The Kubernetes Deployment manifest for the payment service has an incorrect `livenessProbe` path. In the `k8s/robot-shop-eks.yaml` file, the payment container's liveness probe path was changed from `/health` to `/healthz`.

## Symptom
The payment service pod will continuously fail its liveness probe and be restarted by Kubernetes. Users will experience intermittent or complete failures when trying to process payments, as the payment service will frequently be in a `CrashLoopBackOff` or restarting state, making it unavailable to handle requests.

## Root Cause
The payment service application exposes its health check endpoint at `/health`. However, the Kubernetes liveness probe is configured to check `/healthz`. Since this endpoint does not exist, the probe receives a 404 Not Found response, causing Kubernetes to consider the pod unhealthy and restart it.

## Fix
Update the payment Deployment manifest to use the correct liveness probe path:

```yaml
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
```

Change `path: /healthz` back to `path: /health` in the payment Deployment definition within `k8s/robot-shop-eks.yaml`.