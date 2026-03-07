# Fault: Cart Service Memory Limit Too Low

## Description
The memory limit for the cart service Deployment in `k8s/robot-shop-eks.yaml` has been set to an extremely low value. The request memory was changed from "256Mi" to "16Mi" and the limit memory was changed from "512Mi" to "32Mi".

## Symptom
The cart service pod will be repeatedly terminated by Kubernetes with an OOMKilled (Out of Memory) status. Users attempting to use the cart functionality will experience failures when adding items to cart, retrieving cart contents, or any cart-related operations. The service will be unstable and unable to handle requests.

## Root cause
The memory limit of 32Mi is insufficient for the Node.js cart service to start and operate. The application requires at least 256Mi to function properly. When Kubernetes enforces this limit, the process is killed, causing repeated restarts and complete service unavailability.

## Fix
Update the memory resources in the cart Deployment to appropriate values:
- Change `memory: "16Mi"` back to `memory: "256Mi"` (requests)
- Change `memory: "32Mi"` back to `memory: "512Mi"` (limits)

Alternatively, apply the manifest with corrected values:
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```
