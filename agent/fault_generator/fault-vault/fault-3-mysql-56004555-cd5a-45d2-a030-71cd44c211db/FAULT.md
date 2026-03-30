# MySQL Readiness Probe Misconfiguration

## Description
The readiness probe port for the MySQL deployment in `k8s/manifests/mysql.yaml` was changed from `3306` to `3307`.

## Symptom
The MySQL pod will start but will never become "Ready" because the readiness probe will fail to connect to port 3307 (MySQL is listening on 3306). As a result, the `mysql` service will not route traffic to the pod, causing dependent services (like `shipping`) to fail to connect to the database.

## Root cause
The readiness probe is configured to check port 3307, but the MySQL container is only listening on port 3306. Kubernetes uses the readiness probe to determine if a pod is ready to accept traffic. Since the probe fails, the pod is removed from the service endpoints.

## Fix
Revert the readiness probe port in `k8s/manifests/mysql.yaml` back to `3306`.
