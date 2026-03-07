# Fault: Cart Service Liveness and Readiness Probe Path Misconfiguration

## Description
The `livenessProbe` and `readinessProbe` paths for the `cart` service Deployment in `k8s/robot-shop-eks.yaml` have been changed from `/health` to `/nonexistent-health`.

## Symptom
The cart service pods will fail their liveness and readiness checks, causing Kubernetes to repeatedly restart the pods or mark them as unhealthy. Users will experience unavailability of the cart service, leading to failures when attempting to add items to the cart, view cart contents, or perform any cart-related operations. The service will appear to be in a crash loop or perpetually in a `NotReady` state.

## Root cause
The `cart` service's liveness and readiness probes are configured to check a non-existent `/nonexistent-health` endpoint. Since this path does not exist, the probes will continuously fail, indicating to Kubernetes that the application is unhealthy. This results in Kubernetes taking action to restart the pod or prevent traffic from being routed to it, effectively making the service unavailable.

## Fix
Revert the `livenessProbe` and `readinessProbe` paths in the `cart` Deployment to the correct `/health` endpoint.

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
    httpHeaders:
    - name: X-INSTANA-SYNTHETIC
      value: "1"
  initialDelaySeconds: 30
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /health
    port: 8080
    httpHeaders:
    - name: X-INSTANA-SYNTHETIC
      value: "1"
  initialDelaySeconds: 30
  periodSeconds: 10