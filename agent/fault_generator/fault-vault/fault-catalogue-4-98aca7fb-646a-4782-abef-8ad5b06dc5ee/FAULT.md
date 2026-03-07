# Fault: Shared State Race Condition in Product Lookup

## Description
A shared global variable `lastFetchedProduct` was introduced in the catalogue service (`catalogue/server.js`) to temporarily store the result of a product lookup before sending the response. Because Node.js handles multiple requests concurrently and the response is delayed using `setTimeout`, this shared state can be overwritten by subsequent requests.

## Changes Made
- Added a global variable `let lastFetchedProduct = null;` at line 81 of `catalogue/server.js`.
- Modified the `/product/:sku` endpoint to store the fetched product in `lastFetchedProduct` and then use a `setTimeout` to delay the response, sending `lastFetchedProduct` instead of the locally scoped `product` variable.

## Symptom
- Users may occasionally see the wrong product details when viewing a product page.
- If user A requests product X and user B requests product Y almost simultaneously, user A might receive the details for product Y.
- The issue becomes more frequent under high load or when the `GO_SLOW` delay is increased.

## Root Cause
The `lastFetchedProduct` variable is shared across all incoming requests to the `/product/:sku` endpoint. When a request fetches a product from the database, it updates this global variable. If another request fetches a different product before the first request's `setTimeout` callback executes, the global variable is overwritten. When the first request's callback finally runs, it sends the overwritten data, resulting in a cross-talk/race condition.

## Fix
Remove the global `lastFetchedProduct` variable and use the locally scoped `product` variable directly within the response callback.

Example fix:
```javascript
// product by SKU
app.get('/product/:sku', (req, res) => {
    if(mongoConnected) {
        // optionally slow this down
        const delay = process.env.GO_SLOW || 0;
        setTimeout(() => {
            collection.findOne({sku: req.params.sku}).then((product) => {
                req.log.info('product', product);
                if(product) {
                    res.json(product);
                } else {
                    res.status(404).send('SKU not found');
                }
            }).catch((e) => {
                req.log.error('ERROR', e);
                res.status(500).send(e);
            });
        }, delay);
    } else {
        req.log.error('database not available');
        res.status(500).send('database not available');
    }
});
```
