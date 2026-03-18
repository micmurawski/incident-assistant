# Fault: Incorrect Cart Total Calculation

## Description
In `cart/server.js`, the `calcTotal` function was modified to only sum the subtotal of the first item in the cart's item list. This function is responsible for calculating the total price of all items in the cart.

**Changed lines:**
```javascript
    var total = 0;
    if (list.length > 0) {
        total += list[0].subtotal;
    }
```
Should be:
```javascript
    var total = 0;
    for(var idx = 0, len = list.length; idx < len; idx++) {
        total += list[idx].subtotal;
    }
```

## Symptom
When a user adds multiple items to their cart, or multiple quantities of the same item, the displayed cart total will only reflect the subtotal of the first item added. All other items will be ignored in the total calculation. This will lead to:
- Incorrect cart totals displayed to the user.
- Incorrect tax calculation (as tax is based on the total).
- Customers being significantly undercharged for their orders.

## Root Cause
The `calcTotal` function, which is designed to sum the subtotals of all items in the cart, was altered to only consider the subtotal of the first item in the `list` array. This is a logical error that prevents the correct aggregation of all item prices.

## Fix
Revert the `calcTotal` function in `cart/server.js` to its original implementation, iterating through all items to sum their subtotals:

```javascript
function calcTotal(list) {
    var total = 0;
    for(var idx = 0, len = list.length; idx < len; idx++) {
        total += list[idx].subtotal;
    }
    return total;
}
```
Alternatively, revert to the original code from version control.