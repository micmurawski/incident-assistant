# Fault: Category Products Endpoint Returns 404 for Valid Results

## Description

Modified the `/products/:cat` endpoint in `catalogue/server.js` to invert the conditional logic that checks for product results. The code now returns a 404 status code when products ARE found, and returns the products when nothing is found.

## Symptom

When users browse products by category (e.g., `/products/Electronics`), the API returns a 404 "No products for Electronics" error even though products exist in that category. The frontend displays an error message instead of showing the product list.

## Root Cause

The conditional logic in lines 109-113 of `catalogue/server.js` was inverted:
- Original: `if (products) { res.json(products); } else { res.status(404)... }`
- Faulty: `if (products) { res.status(404)... } else { res.json(products); }`

This causes the success path to execute the error handler and vice versa.

## Fix

Revert the conditional logic to its correct form:

```javascript
if(products) {
    res.json(products);
} else {
    res.status(404).send('No products for ' + req.params.cat);
}
```
