# Redis Connection Leak in Cart Service

## Description

Modified the `saveCart` function in `cart/server.js` to instantiate a new Redis client on every call without closing it, instead of reusing the global `redisClient`.

## Symptom

- The cart service will leak Redis connections and memory over time.
- Eventually, Redis will run out of available connections, or the cart service will crash due to memory exhaustion.
- Users will experience intermittent or complete failures when adding items to the cart, updating quantities, or checking out.
- The `/health` endpoint may still report OK initially, but the service will degrade as resources are exhausted.

## Root Cause

A new Redis client is created for every `saveCart` operation but is never closed (e.g., via `client.quit()`). This leads to an unbounded growth of open TCP connections to the Redis server and memory leaks within the Node.js application, eventually exhausting system resources.

## Fix

Revert the `saveCart` function to use the global `redisClient` instead of creating a new client for each operation:

```javascript
function saveCart(id, cart) {
    logger.info('saving cart', cart);
    return new Promise((resolve, reject) => {
        redisClient.setex(id, 3600, JSON.stringify(cart), (err, data) => {
            if(err) {
                reject(err);
            } else {
                resolve(data);
            }
        });
    });
}
```
