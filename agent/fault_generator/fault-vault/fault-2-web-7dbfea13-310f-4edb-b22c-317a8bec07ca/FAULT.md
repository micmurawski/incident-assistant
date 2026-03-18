# Fault: Cart Quantity Not Accumulated

## Description

Changed the cart item quantity accumulation logic in the `mergeList` function in `cart/server.js`. The original code used `+=` to add the new quantity to the existing item quantity, but was changed to `=` which simply overwrites the existing quantity with the new quantity.

## Symptom

When a user adds the same product to their cart multiple times (e.g., adds 2 of item A, then adds 3 more of item A), the cart will only show the most recent quantity (3) instead of the accumulated total (5). This results in:
- Cart totals being incorrect (lower than expected)
- Users being undercharged for their orders
- Customer complaints about incorrect order quantities

## Root Cause

In the `mergeList` function, the line `list[idx].qty += qty;` was changed to `list[idx].qty = qty;`. This changes the behavior from accumulating quantities to overwriting them. When adding an item that's already in the cart, instead of adding the new quantity to the existing quantity, it replaces the existing quantity entirely.

## Fix

Change line 337 in `cart/server.js` back from:
```javascript
list[idx].qty = qty;
```
to:
```javascript
list[idx].qty += qty;
```
