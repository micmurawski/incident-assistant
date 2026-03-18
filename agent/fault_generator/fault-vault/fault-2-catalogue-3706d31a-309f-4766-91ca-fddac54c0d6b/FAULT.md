# Fault: Catalogue Service Product SKU Override

## Description
Modified the `/product/:sku` endpoint in `catalogue/server.js` to always return a hardcoded "Faulty Product" object, regardless of the SKU provided in the request. The original database lookup for the specific SKU has been replaced with a static JSON response.

## Symptom
When users attempt to view details for any product by its SKU (e.g., `/product/B008F0Y4Y8`), they will consistently see the details of the "Faulty Product" instead of the actual product they requested. This will lead to incorrect product information being displayed on product detail pages.

## Root Cause
The `collection.findOne({sku: req.params.sku}).then(...)` block in the `/product/:sku` endpoint has been replaced with a direct `res.json(faultyProduct)` call. This bypasses the database query and returns a predefined product object for all SKU requests.

## Fix
Revert the changes to the `/product/:sku` endpoint in `catalogue/server.js` to restore the original database lookup logic:

```javascript
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