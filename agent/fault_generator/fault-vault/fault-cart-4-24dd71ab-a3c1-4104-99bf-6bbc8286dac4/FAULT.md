# Unbounded In-Memory Cart Cache

## Description

Modified the `saveCart` function in `cart/server.js` to store cart objects in a global in-memory array `cartCache` instead of persisting them to Redis.

## Symptom

- The cart service will experience a continuous increase in memory usage over time.
- Eventually, the service will run out of memory, leading to crashes or restarts.
- Users may experience intermittent failures when adding items to the cart or when their carts are not saved correctly.
- The `/health` endpoint may still report OK initially, but the service will become unresponsive as memory is exhausted.

## Root Cause

The `saveCart` function now stores every cart in a global array `cartCache` without any eviction policy or size limit. This causes unbounded memory growth as new carts are created or updated, eventually exhausting the available memory of the service.

## Fix

Revert the changes in `saveCart` to use Redis for cart persistence:

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
