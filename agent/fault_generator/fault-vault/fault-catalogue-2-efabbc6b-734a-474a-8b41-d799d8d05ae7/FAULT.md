# Fault: Category Filter Bypass in Catalogue Service

## Title
Category endpoint returns all products instead of filtered results

## Description
In the catalogue service (`catalogue/server.js`), the endpoint `/products/:cat` was modified. The MongoDB query no longer filters by category parameter - it returns all products from the database regardless of the category requested.

## Symptom
When users request products for a specific category (e.g., `/products/electronics`), they receive all products in the catalogue instead of only electronics products. This causes:
- Incorrect product listings on category pages
- Users seeing irrelevant products
- Broken filtering functionality in the UI

## Root Cause
The MongoDB query in the category endpoint was changed from:
```javascript
collection.find({ categories: req.params.cat })
```
to:
```javascript
collection.find({})
```

This removed the category filter, causing the endpoint to ignore the category parameter and return all products.

## Fix
To fix this fault, revert the change in `catalogue/server.js` line 108:
- Change: `collection.find({}).sort({ name: 1 })`
- Back to: `collection.find({ categories: req.params.cat }).sort({ name: 1 })`
