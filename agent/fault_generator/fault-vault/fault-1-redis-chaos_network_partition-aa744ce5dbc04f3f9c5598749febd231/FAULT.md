# Fault: Aggressive Redis `retry_strategy` in Cart and User Services

## Description

The cart service (`cart/server.js`) and the user service (`user/server.js`) had a custom `retry_strategy` callback added to their `redis.createClient(...)` configuration. The callback abandons reconnection on any of three triggers:

- An `ECONNREFUSED` error is observed → returns an `Error` immediately, which permanently fails the client (`node_redis` will not reconnect).
- More than ~5 minutes of total retry time has elapsed.
- The retry counter exceeds 10 attempts.

The cart service's Redis `error` handler also flips a local `redisConnected = false` flag.

## Symptom

- Cart endpoints (add, update, delete, shipping) return 500 errors for the duration of the incident.
- User `/uniqueid` requests fail.
- Health checks on cart show Redis as not connected.
- After the underlying Redis connectivity issue clears, cart and user **do not recover automatically** — they continue to report Redis as unavailable until the pods are restarted (`kubectl rollout restart`).

## Root Cause

The application root cause is the custom `retry_strategy` introduced by the patch. The default `node_redis` client retries connection establishment indefinitely with backoff, so transient Redis unavailability is normally handled automatically. The new strategy abandons the connection within ~20 seconds (10 attempts × small delays) on the very first `ECONNREFUSED`, after which the client object is permanently dead and the service has no Redis until the process restarts.

A `NetworkChaos partition` experiment is concurrently applied between the redis pod and its consumers (`cart` and `user`) in both directions, for 60 minutes. While the partition is active, every Redis connection attempt from cart or user fails with `ECONNREFUSED` — exactly the trigger condition the patch's `retry_strategy` treats as fatal.

The chaos experiment is a contributing environmental condition, not the root cause. With the original `retry_strategy`-free client, cart and user would have stayed in their normal connect/retry loop and recovered automatically when the partition healed. With the patched client, they need a manual rollout restart to come back even after the partition is gone — which is the actual production hazard the SRE training scenario is meant to teach.

## Fix

1. Revert the Redis client configuration in both `cart/server.js` and `user/server.js` to remove the custom `retry_strategy` callback. The default behavior (infinite retries with backoff) is correct for this application.
2. Optionally keep the `redisConnected = false` flag flip in the error handler only if a paired `redisConnected = true` flip is added on the `ready` event — otherwise it is dead state.
3. As a defensive long-term improvement, wrap Redis calls in a circuit breaker so the application returns a graceful "service degraded" response instead of 500s when Redis is unreachable. This is an addition, not the fix.
