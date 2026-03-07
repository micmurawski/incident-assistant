# Fault: Dispatch Service Port Mismatch

## Description
The dispatch Service in `k8s/robot-shop-eks.yaml` has an incorrect `targetPort` configuration. The Service exposes port 80 but targets port 8080, while the dispatch container does not expose port 8080—it listens on port 80 by default.

## Symptom
When traffic is routed through the dispatch Service, connections will fail with connection refused errors. The Service will be unable to forward requests to the dispatch pods because the target port does not match the container's listening port.

## Root Cause
The dispatch Service was configured with `targetPort: 8080`, but the dispatch container does not define a port 8080 in its Deployment. The Go application listens on port 80 by default (no explicit port is defined in the container spec), causing a port mismatch between the Service and the backend pods.

## Fix
Change the dispatch Service `targetPort` from `8080` back to `80` in the Kubernetes manifest:

```yaml
ports:
- port: 80
  targetPort: 80  # Changed from 8080 to 80
  type: ClusterIP
```
