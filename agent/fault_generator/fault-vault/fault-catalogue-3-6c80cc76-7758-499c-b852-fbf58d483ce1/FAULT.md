# Fault: Catalogue Service Target Port Misconfiguration

## Description
The `targetPort` for the `catalogue` service in `k8s/robot-shop-eks.yaml` was changed from `8080` to `8081`.

## Symptom
- The `catalogue` service will not be able to route traffic to the `catalogue` pods.
- The Robot Shop frontend will not be able to display product listings, as the catalogue service will be unreachable.
- Other services that depend on the catalogue service will fail to communicate with it.

## Root Cause
The `catalogue` service is configured to route traffic to port `8081` on the pods, but the `catalogue` container is listening on port `8080`. This mismatch prevents the service from successfully forwarding requests to the application.

## Fix
Revert the `targetPort` in the `catalogue` service to the correct port:
```yaml
  ports:
  - port: 8080
    targetPort: 8080