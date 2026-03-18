# Fault: Incorrect Subtotal Calculation in Cart Update

## Description
In `cart/server.js`, line 251, the subtotal calculation for cart item updates uses addition (`+`) instead of multiplication (`*`). This affects the `/update/:id/:sku/:qty` endpoint which is used to update item quantities in the cart.

**Changed line:**
```javascript
cart.items[idx].subtotal = cart.items[idx].price + qty;  // incorrect
```
Should be:
```javascript
cart.items[idx].subtotal = cart.items[idx].price * qty;  // correct
```

## Symptom
When a user updates the quantity of an item in their cart via the update endpoint, the subtotal for that item is calculated incorrectly. Instead of multiplying the unit price by the quantity, it adds the price and quantity together. This results in:
- Incorrect item subtotals displayed in the cart
- Incorrect cart total
- Incorrect tax calculation (since tax is derived from the total)
- Customers being overcharged or undercharged

## Root Cause
The arithmetic operator `*` (multiplication) was incorrectly replaced with `+` (addition) in the quantity update logic path. This is a logic error where the developer likely intended to calculate the subtotal as `price × quantity` but inadvertently used `price + quantity`.

## Fix
Change the operator from `+` back to `*` in the subtotal calculation on line 251 of `cart/server.js`:

```javascript
cart.items[idx].subtotal = cart.items[idx].price * qty;
```

Alternatively, revert to the original code from version control.
