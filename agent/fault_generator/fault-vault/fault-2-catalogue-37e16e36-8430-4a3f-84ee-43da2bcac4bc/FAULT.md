# Fault: Catalogue Service Products Always Out of Stock

## Description
Modified the `/product/:sku` endpoint in `catalogue/server.js` to always set the `instock` property of the returned product to `0`, regardless of the actual inventory level in the database.

## Symptom
When users view the details of any product, it will always be displayed as "Out of stock". Consequently, users will be unable to add any items to their shopping cart, preventing them from making purchases.

## Root Cause
In the `/product/:sku` endpoint, after successfully retrieving a product from the database, the code `product.instock = 0;` was added before sending the JSON response. This overrides the actual stock value with zero for every product detail request.

## Fix
Remove the `product.instock = 0;` line from the `/product/:sku` endpoint in `catalogue/server.js`:

```javascript
collection.findOne({sku: req.params.sku}).then((product) => {
    req.log.info('product', product);
    if(product) {
        res.json(product);
    } else {
        res.status(404).send('SKU not found');
    }
// ...
```
