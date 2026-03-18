# Cart Service Operation Limit Exceeded

## Description

Modified the `saveCart` function in `cart/server.js` to introduce an artificial operation limit. A global counter `operationCount` is incremented with each call to `saveCart`. If `operationCount` exceeds `operationLimit` (set to 100), the `saveCart` function will reject the promise, preventing further cart saves.

## Symptom

- After approximately 100 cart save operations (e.g., adding items to cart, updating quantities, or adding shipping), the cart service will start returning 500 errors for operations that involve saving the cart.
- Users will be unable to add items to their cart, update quantities, or add shipping information after the limit is reached.
- Existing carts might still be retrievable, but any modification attempts will fail.
- The `/health` endpoint will still report OK, as Redis connectivity is not directly affected, but the application will be functionally impaired.

## Root Cause

The `saveCart` function has been artificially limited to 100 operations. Once this limit is reached, all subsequent attempts to save a cart will fail, leading to functional degradation of the cart service. This simulates a resource exhaustion scenario where a critical operation becomes unavailable after a certain threshold.

## Fix

Remove the `operationCount` and `operationLimit` variables and the conditional check within the `saveCart` function. Revert the `saveCart` function to its original implementation:

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