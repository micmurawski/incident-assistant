# Incorrect REDIS_HOST environment variable in cart deployment

## Description
Added an environment variable `REDIS_HOST` with the value `redis-store` to the cart deployment manifest (`k8s/manifests/cart.yaml`).

## Symptom
The cart service will fail to connect to Redis. Users will not be able to add items to their cart, view their cart, or checkout. The cart service logs will show Redis connection errors.

## Root cause
The cart service uses the `REDIS_HOST` environment variable to determine the hostname of the Redis server. By default, it uses `redis`, which resolves to the Redis service in the Kubernetes cluster. By setting it to `redis-store`, the cart service attempts to connect to a non-existent host, causing all cart operations to fail.

## Fix
Remove the `REDIS_HOST` environment variable from the cart deployment manifest (`k8s/manifests/cart.yaml`), or set it to the correct value (`redis`).