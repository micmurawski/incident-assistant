Title: Web service liveness and readiness probes misconfigured

Description: The `livenessProbe` and `readinessProbe` paths for the `web` deployment in `k8s/robot-shop-eks.yaml` have been changed from `/` to `/nonexistent-health`.

Symptom: The `web` service pods will continuously fail their liveness and readiness checks, leading to them being restarted or never becoming ready to serve traffic. Users will experience the web application being unavailable or intermittently available.

Root cause: The liveness and readiness probes are configured with a path that does not exist on the `web` service. Kubernetes will repeatedly try to access this path to determine the health of the pods. Since the path is invalid, the probes will fail, causing Kubernetes to mark the pods as unhealthy and take action (e.g., restarting them).

Fix: Revert the `livenessProbe` and `readinessProbe` paths for the `web` deployment in `k8s/robot-shop-eks.yaml` from `/nonexistent-health` back to `/`.