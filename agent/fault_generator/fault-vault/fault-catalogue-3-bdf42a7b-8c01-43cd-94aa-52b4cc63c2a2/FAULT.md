# Fault: Service Selector Mismatch for Dispatch

## Description
Modified the Kubernetes Service manifest for `dispatch` to use a selector that does not match the label of the underlying Deployment. The Service selector was changed from `app: dispatch` to `app: dispatch-svc`, while the Deployment's pod template label remains `app: dispatch`.

## Symptom
- The dispatch Service will not route traffic to any pods
- External clients attempting to reach the dispatch service will receive no response or connection failures
- `kubectl get endpoints dispatch` will show empty endpoints
- Pods for dispatch will be running but unreachable through the Service

## Root Cause
The Service selector `app: dispatch-svc` does not match the pod label `app: dispatch` defined in the Deployment's template. Kubernetes Service selectors must match the labels of the pods they intend to route traffic to. Since there are no pods with the label `app: dispatch-svc`, the Service will have no endpoints and cannot forward traffic.

## Fix
Revert the Service selector to match the Deployment label:
```yaml
spec:
  selector:
    app: dispatch
```
