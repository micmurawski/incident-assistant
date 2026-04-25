# Fault: Redundant Redis Round-Trips in Cart and User Services

## Description

The cart service's `saveCart` function (`cart/server.js`) was modified to perform an additional read operation immediately after each write to Redis. The handler now issues a confirmation `GET` after every `SETEX`, ostensibly to verify that the saved data is immediately visible.

Similarly, the user service's `/uniqueid` endpoint (`user/server.js`) was changed to perform a `GET` on the counter immediately after `INCR`. A `retry_strategy` and a startup "warm-up" `GET` were also added to the Redis client setup, but those are benign on their own.

## Symptom

- Cart operations (add, update, shipping) take roughly twice the expected time end-to-end.
- `/uniqueid` requests show elevated latency.
- p95/p99 response times on the cart and user services climb noticeably.
- The effect is dramatically worse when there is any baseline latency between the application and Redis.

## Root Cause

The actual root cause is in the application code: each cart save and each unique-ID generation now requires two sequential Redis round-trips instead of one (an N+1 round-trip pattern). On a healthy local network this only doubles the latency, which is easy to miss in development and code review.

A `NetworkChaos delay` experiment is concurrently applied to the redis pod (~500ms with 50% correlation), which adds round-trip latency to every Redis call. The application bug — the redundant extra `GET` per write — turns this baseline latency into a per-operation amplifier: where one round-trip would have cost ~500ms, two round-trips now cost ~1000ms.

The chaos experiment is a contributing environmental condition, not the root cause. Removing the chaos would lower the absolute numbers but the cart and user services would still be doing twice the necessary work per request; the underlying inefficiency would re-emerge under any future Redis slowness (network, CPU saturation, replication lag, etc.).

## Fix

Revert the changes in:
1. `cart/server.js` — remove the extra `redisClient.get` call inside the `saveCart` `SETEX` callback.
2. `user/server.js` — remove the extra `redisClient.get` call inside the `/uniqueid` handler, and remove the startup warm-up `GET` if not otherwise needed.

The `retry_strategy` block introduced by the same patch is benign and may be kept.
