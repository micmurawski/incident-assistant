# Redis Connection Leak in Cart Service

## Description
A connection leak was introduced in the `cart` service. In the `saveCart` function, a new Redis client is created every time a cart is saved, but the client is never closed or destroyed.

## Symptom
The `cart` service will gradually consume more memory and file descriptors as users add items to their carts or update their carts. Eventually, the service will crash due to resource exhaustion (e.g., running out of file descriptors or memory), or the Redis server will reach its maximum connection limit and start rejecting new connections, causing the `cart` service to fail to save carts.

## Root Cause
The `saveCart` function in `cart/server.js` creates a new Redis client instance (`redis.createClient({ host: redisHost })`) for every save operation instead of reusing the existing global `redisClient`. Because these clients are never closed (`client.quit()`), they remain open, leaking connections and memory.

## Fix
Revert the change in `cart/server.js` to use the global `redisClient` instead of creating a new client in the `saveCart` function.

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