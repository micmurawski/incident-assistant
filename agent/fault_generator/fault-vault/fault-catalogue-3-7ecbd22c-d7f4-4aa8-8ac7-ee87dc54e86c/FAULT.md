# Fault: Catalogue Service Memory Limit Too Low

## Description
The memory limit for the `catalogue` deployment in `k8s/robot-shop-eks.yaml` was reduced from `512Mi` to `10Mi`.

## Symptom
- The `catalogue` service pods will continuously crash with an `OOMKilled` status.
- The Robot Shop frontend will not be able to display product listings, as the catalogue service will be unreachable or unhealthy.
- Other services that depend on the catalogue service will fail to communicate with it.

## Root Cause
The `catalogue` service requires more than 10Mi of memory to run. By setting the memory limit to 10Mi, Kubernetes will terminate the pod as soon as it exceeds this limit, resulting in an `OOMKilled` error and continuous restarts.

## Fix
Revert the memory limit in the `catalogue` deployment to the correct value:
```yaml
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```
