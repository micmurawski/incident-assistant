# Fault: Tax Calculation Disabled in Cart Service

## Description
In `cart/server.js`, the `calcTax` function was modified to always return 0. This function is responsible for calculating the tax based on the cart's total.

**Changed line:**
```javascript
return 0;
```
Should be:
```javascript
return (total - (total / 1.2));
```

## Symptom
When users add items to their cart, the tax amount displayed will always be 0, regardless of the cart's total. This will lead to an incorrect final price for the customer and a loss of revenue for the business.

## Root Cause
The `calcTax` function, which is supposed to calculate a 20% tax, was altered to return a fixed value of 0. This bypasses the actual tax calculation logic.

## Fix
Revert the `calcTax` function in `cart/server.js` to its original implementation:
```javascript
function calcTax(total) {
    // tax @ 20%
    return (total - (total / 1.2));
}
```
