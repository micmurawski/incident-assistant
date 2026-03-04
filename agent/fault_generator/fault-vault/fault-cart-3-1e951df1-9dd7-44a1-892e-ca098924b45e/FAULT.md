# Fault: Carts Never Expire from Redis

## Description

In `cart/server.js`, the `saveCart` function was modified to use `redisClient.set` instead of `redisClient.setex`. This change removes the Time-To-Live (TTL) on cart entries, causing them to persist in Redis indefinitely.

## Symptom

Redis memory usage will grow over time, leading to performance degradation. Eventually, Redis may run out of memory, causing the cart service to fail. Monitoring will show a steady increase in Redis memory usage and the number of keys.

## Root Cause

The `redisClient.setex` command sets a key with a specified TTL. By using `redisClient.set` instead, the TTL is removed, and the key will not expire. This creates a memory leak, as cart data is never garbage-collected.

## Fix

Revert the change in `cart/server.js` to use `redisClient.setex` with a reasonable TTL (e.g., 3600 seconds).
