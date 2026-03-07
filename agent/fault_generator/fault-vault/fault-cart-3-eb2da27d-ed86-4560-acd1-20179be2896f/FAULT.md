# Fault: Cart Service Redis Host Misconfiguration

## Description
The `REDIS_HOST` environment variable for the `cart` service Deployment in `k8s/robot-shop-eks.yaml` has been misconfigured. It was changed from its correct value (likely "redis") to "nonexistent-redis".

## Symptom
The cart service will fail to connect to the Redis instance, leading to errors when users try to add items to their cart, view cart contents, or perform any cart-related operations. The service might appear to be running, but its core functionality will be broken, resulting in a degraded user experience. Logs for the cart service will show connection errors to Redis.

## Root cause
The `cart` service relies on Redis for its operations. By setting the `REDIS_HOST` environment variable to a non-existent hostname, the service is unable to establish a connection with the Redis server, causing all Redis-dependent operations to fail.

## Fix
Revert the `REDIS_HOST` environment variable in the `cart` Deployment to the correct Redis service hostname, which is typically "redis".

```yaml
env:
- name: REDIS_HOST
  value: "redis"
```
