# Redis service targetPort misconfiguration

## Description
Changed the `targetPort` of the `redis` Service in `k8s/manifests/redis.yaml` from `6379` to `6380`.

## Symptom
The `cart` and `user` services will fail to connect to Redis. Users will not be able to add items to their cart, and anonymous users cannot be created.

## Root cause
The `redis` Service is routing traffic to port `6380` on the Redis pods, but the Redis container is listening on port `6379`. This causes connection timeouts or connection refused errors for any service trying to reach Redis via the Service.

## Fix
Change the `targetPort` back to `6379` in `k8s/manifests/redis.yaml`.
