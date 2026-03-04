Title: Shortened Redis Cart Expiration

Description: In `cart/server.js`, the Redis expiration time for shopping carts has been reduced from 3600 seconds (1 hour) to 10 seconds. This change is located in the `saveCart` function.

Symptom: Users will experience their shopping carts being emptied much more frequently and unexpectedly, typically within 10 seconds of adding an item or modifying the cart. This will lead to frustration and incomplete purchases.

Root cause: The `redisClient.setex` function, which sets the expiration time for cart data in Redis, was configured with a significantly shorter time (10 seconds instead of 3600 seconds). This causes carts to be evicted from the cache much faster than intended.

Fix: Revert the change to the `saveCart` function in `cart/server.js`, setting the Redis expiration time back to its original value of 3600 seconds (or an appropriate longer duration as per application requirements).
