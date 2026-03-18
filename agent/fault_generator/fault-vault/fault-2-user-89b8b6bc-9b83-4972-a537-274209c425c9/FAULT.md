# Fault: Anonymous Users Share the Same Cart

## Description
Changed the Redis command in the `/uniqueid` endpoint of `user/server.js` from `incr` to `get`. This endpoint is responsible for generating unique IDs for anonymous users.

## Symptom
All anonymous users will receive the same UUID (e.g., `anonymous-null` or `anonymous-1` if it was previously incremented). As a result, all anonymous users will share the same shopping cart, seeing each other's items and potentially checking out each other's orders.

## Root Cause
The `redisClient.get` command retrieves the current value of the `anonymous-counter` key without incrementing it. Since the value is never incremented, every call to `/uniqueid` returns the exact same value, leading to identical UUIDs for all anonymous sessions.

## Fix
Revert the Redis command in the `/uniqueid` endpoint back to `incr`:

```javascript
    redisClient.incr('anonymous-counter', (err, r) => {