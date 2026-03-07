# Redis Key Expiration Leak in Cart Service

## Description

Modified the `saveCart` function in `cart/server.js` to use `redisClient.set` instead of `redisClient.setex`, removing the 3600-second (1 hour) expiration time for cart data stored in Redis.

## Symptom

- The Redis instance used by the cart service will experience a continuous, unbounded increase in memory usage over time.
- Eventually, Redis will hit its `maxmemory` limit. Depending on the Redis eviction policy, it may start evicting random keys (causing users to lose their carts unexpectedly) or return OOM (Out of Memory) errors.
- If OOM errors occur, the cart service will fail to save new carts or update existing ones, leading to 500 Internal Server Error responses for users trying to add items to their cart or checkout.
- Monitoring will show a steady climb in Redis memory consumption and potentially an increase in error rates for the cart service.

## Root Cause

By removing the expiration time (`setex` to `set`), every unique cart created by users is stored in Redis indefinitely. Since carts are typically transient data, this leads to a slow but steady memory leak in the Redis database, eventually exhausting its available memory resources.

## Fix

Revert the `saveCart` function to use `redisClient.setex` with the appropriate expiration time (e.g., 3600 seconds) to ensure old carts are automatically cleaned up:

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
