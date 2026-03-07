# Fault: Cart Overwritten on Add

## Description
In `cart/server.js`, the logic for adding an item to an existing cart was modified. Instead of parsing the existing cart data from Redis, it initializes a new, empty cart.

**Changed lines:**
```javascript
                if(data == null) {
                    // create new cart
                    cart = {
                        total: 0,
                        tax: 0,
                        items: []
                    };
                } else {
                    cart = {
                        total: 0,
                        tax: 0,
                        items: []
                    };
                }
```
Should be:
```javascript
                if(data == null) {
                    // create new cart
                    cart = {
                        total: 0,
                        tax: 0,
                        items: []
                    };
                } else {
                    cart = JSON.parse(data);
                }
```

## Symptom
When a user adds an item to their cart, any previously added items are lost. The cart will only ever contain the most recently added item (or items, if added in a single request). Users will be unable to purchase multiple different items in a single order.

## Root Cause
The `app.get('/add/:id/:sku/:qty', ...)` endpoint retrieves the existing cart from Redis. If the cart exists (`data != null`), it should parse the JSON data into the `cart` object. However, the code was changed to assign a new, empty cart object instead. This discards the existing cart contents before adding the new item.

## Fix
Revert the `else` block in the `app.get('/add/:id/:sku/:qty', ...)` endpoint in `cart/server.js` to parse the existing cart data:

```javascript
                } else {
                    cart = JSON.parse(data);
                }