# Cart Expiry Configuration Issue

## Description
The cart service stores shopping cart data in Redis with a TTL (time-to-live). The expiry value was changed from 3600 seconds (1 hour) to 10 seconds in the `saveCart` function in `cart/server.js`.

## Symptom
Users shopping experience is disrupted because:
- Shopping carts expire prematurely during checkout flow
- Users see empty carts or "cart not found" errors
- Checkout failures increase during normal browsing sessions
- Carts disappear after a very short period (10 seconds)

## Root Cause
The `saveCart` function in `cart/server.js` uses a hardcoded expiry value of 10 seconds instead of the original 3600 seconds. This causes cart data to be evicted from Redis far too quickly, before users complete their shopping and checkout flow.

## Fix
Change the expiry value in the `saveCart` function back to an appropriate duration:

```javascript
function saveCart(id, cart) {
    logger.info('saving cart', cart);
    var expiry = 3600;  // Changed from 10 to 3600 (1 hour)
    return new Promise((resolve, reject) => {
        redisClient.setex(id, expiry, JSON.stringify(cart), (err, data) => {
            if(err) {
                reject(err);
            } else {
                resolve(data);
            }
        });
    });
}
```
