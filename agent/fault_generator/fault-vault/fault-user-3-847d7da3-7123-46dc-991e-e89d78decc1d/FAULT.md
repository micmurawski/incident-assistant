# Fault Documentation

## Title
User Service Redis Connection Failure

## Description
The `REDIS_HOST` environment variable in the user service Deployment has been changed from `"redis"` to `"redis-cache"`. This change is located in the Kubernetes manifest file `k8s/robot-shop-eks.yaml` at line 440 of the user Deployment specification.

## Symptom
The user service will fail to connect to Redis, resulting in connection errors. Users attempting to access user-related functionality (such as login, registration, or session management) will experience failures. The application logs will show connection refused or DNS resolution errors when trying to connect to the Redis host. The user service may also fail readiness/liveness probes if it cannot establish Redis connections required for proper operation.

## Root Cause
The environment variable `REDIS_HOST` points to `"redis-cache"` which does not correspond to any Service or pod in the Kubernetes cluster. The correct value should be `"redis"` to match the Redis Service name defined in the manifest. Since there is no service named "redis-cache", DNS resolution will fail, preventing the user service from establishing communication with the Redis backing store.

## Fix
Revert the `REDIS_HOST` environment variable value in the user service Deployment from `"redis-cache"` back to `"redis"`. The correct configuration should be:

```yaml
- name: REDIS_HOST
  value: "redis"
```

This can be applied by updating the Kubernetes manifest and reapplying it to the cluster, or by directly patching the Deployment using kubectl.
