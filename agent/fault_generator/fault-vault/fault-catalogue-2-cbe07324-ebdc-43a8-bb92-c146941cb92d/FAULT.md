# Fault: Catalogue Service Product Listing Delay

## Description
Modified the `/products` endpoint in `catalogue/server.js` to introduce an artificial delay of 2 seconds (default) before returning the list of all products. This delay is configurable via the `PRODUCT_LIST_DELAY` environment variable.

## Symptom
Users will experience a noticeable delay when loading the main product listing page or any other part of the application that fetches all products from the `/products` endpoint. The page will take longer to render, and network requests to `/products` will show increased latency.

## Root Cause
The `collection.find({}).toArray().then((products) => { ... })` block in the `/products` endpoint now wraps the `res.json(products)` call within a `setTimeout` function. This forces a delay before the response is sent, regardless of how quickly the database query completes.

## Fix
Remove the `setTimeout` wrapper from the `res.json(products)` call in the `/products` endpoint in `catalogue/server.js`:

```javascript
collection.find({}).toArray().then((products) => {
    res.json(products);
}).catch((e) => {
    req.log.error('ERROR', e);
    res.status(500).send(e);
});