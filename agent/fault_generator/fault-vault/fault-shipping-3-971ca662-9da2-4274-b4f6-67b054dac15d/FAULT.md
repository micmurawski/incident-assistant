# Fault: Shipping Service Database Connection Failure

## Description
The `DB_HOST` environment variable in the shipping service Deployment has been changed from `mysql` to `mysql-server` in the Kubernetes manifest file `k8s/robot-shop-eks.yaml` (line 614).

## Symptom
The shipping service will fail to start or become unhealthy because it cannot resolve the hostname `mysql-server`. The container will be unable to connect to the MySQL database, resulting in:
- Failed connection attempts to the database
- Readiness probe failures (HTTP 500 or connection timeout)
- Service endpoints not marked as ready
- Orders cannot be processed through the shipping service

## Root Cause
The shipping service relies on the `DB_HOST` environment variable to connect to the MySQL database. The Kubernetes Service for MySQL is named `mysql`, which is the correct hostname for internal cluster DNS resolution. Changing `DB_HOST` to `mysql-server` breaks the DNS resolution, as there is no service or endpoint named `mysql-server` in the cluster.

## Fix
Change the `DB_HOST` environment variable value back to `mysql` in the shipping Deployment:

```yaml
env:
- name: DB_HOST
  value: mysql
```

Alternatively, if a different hostname is required, create a Kubernetes Service named `mysql-server` that points to the MySQL pods.
