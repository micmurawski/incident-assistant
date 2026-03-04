# Title: Insufficient Memory Limit for Payment Service

## Description
The Kubernetes deployment manifest for the payment service (`k8s/robot-shop-eks.yaml`) was modified to set an extremely low memory limit for the `payment` container. The memory limit was changed from `512Mi` to `10Mi`.

## Symptom
The payment service will be unstable and likely crash frequently with `OOMKilled` (Out of Memory) errors. Users attempting to make payments will experience failures or timeouts. Kubernetes will show the payment pod restarting repeatedly. Monitoring will show high memory usage followed by a crash for the payment pod.

## Root Cause
The `payment` service, a Python application, requires more than 10Mi of memory to run. By setting the limit this low, the Kubernetes scheduler will terminate the pod as soon as its memory usage exceeds the limit, which will happen almost immediately upon startup or during any transaction.

## Fix
To fix this issue, revert the memory limit for the `payment` service in `k8s/robot-shop-eks.yaml` back to a reasonable value, such as `512Mi`. After applying the corrected manifest, the pod will be recreated with adequate memory, and the service will function correctly.
