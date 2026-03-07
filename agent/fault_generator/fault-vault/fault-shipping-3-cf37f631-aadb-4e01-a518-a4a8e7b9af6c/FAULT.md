# Fault: Shipping Service Readiness Probe Misconfiguration

## Description
The `readinessProbe` path for the shipping service Deployment has been changed from `/health` to `/healthz` in the Kubernetes manifest file `k8s/robot-shop-eks.yaml`.

## Symptom
The shipping service pods will start but will never become "Ready". The readiness probe will continuously fail with HTTP 404 Not Found errors. As a result, the shipping service endpoints will not be added to the Kubernetes Service, and other services will be unable to communicate with the shipping service. Users will experience failures when trying to calculate shipping costs or complete orders.

## Root Cause
The shipping service application exposes its health check endpoint at `/health`. By changing the readiness probe path to `/healthz`, Kubernetes attempts to check the health of the pod at a non-existent endpoint. Since the probe fails, Kubernetes assumes the pod is not ready to receive traffic and removes it from the service endpoints.

## Fix
Change the `readinessProbe` path back to `/health` in the shipping Deployment in `k8s/robot-shop-eks.yaml`:

```yaml
        readinessProbe:
          httpGet:
            path: /health
            port: 8080