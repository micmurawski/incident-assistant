# Fault: Incorrect Cart Total Calculation

## Description
Changed the total calculation logic in the `calcTotal` function in `cart/server.js`. The original code summed the `subtotal` of each item (which is `price * qty`), but it was changed to sum the `price` of each item, ignoring the quantity.

## Symptom
When a user adds multiple quantities of the same item to their cart, the total price will only reflect the price of a single item, not the quantity. This results in:
- Cart totals being incorrect (lower than expected)
- Users being undercharged for their orders
- Customer complaints about incorrect order totals

## Root Cause
In the `calcTotal` function, the line `total += list[idx].subtotal;` was changed to `total += list[idx].price;`. This changes the behavior from summing the subtotal of each item to summing the price of each item. When adding an item with a quantity greater than 1, the total will only reflect the price of a single item.

## Fix
Change line 349 in `cart/server.js` back from:
```javascript
total += list[idx].price;
```
to:
```javascript
total += list[idx].subtotal;