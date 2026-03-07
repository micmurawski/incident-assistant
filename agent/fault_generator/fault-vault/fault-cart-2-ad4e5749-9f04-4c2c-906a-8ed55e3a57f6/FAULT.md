# Fault: Incorrect Quantity Accumulation in Cart

## Description
In `cart/server.js`, line 337, the `mergeList` function was modified. The line `list[idx].qty += qty;` was changed to `list[idx].qty = qty;`. This affects the `/add/:id/:sku/:qty` endpoint when a user adds an item that is already present in their cart.

## Symptom
When a user adds an item to their cart that is already present, the quantity of that item in the cart is replaced by the newly added quantity, instead of being incremented. For example, if a user adds 2 of item A, then adds another 3 of item A, the cart will show 3 of item A, not 5. This leads to incorrect cart totals and potentially lost sales.

## Root Cause
The `mergeList` function, responsible for combining items in the cart, was altered to assign the new quantity directly (`=`) instead of adding it (`+=`) to an existing item's quantity. This prevents proper accumulation of item quantities when the same item is added multiple times.

## Fix
Change the operator from `=` back to `+=` in the quantity update logic on line 337 of `cart/server.js`: `list[idx].qty += qty;`