# Fault: Incorrect Tax Calculation in Cart Service

## Description

Changed the tax calculation formula in the `calcTax` function in `cart/server.js`. The original code calculated tax as `total - (total / 1.2)` which correctly derives the 20% VAT component from a net total, but was changed to `total * 0.2` which applies a flat 20% tax rate.

## Symptom

When customers add items to their cart and proceed to checkout, they will be overcharged for tax. For example:
- With a subtotal of $100, the correct tax should be approximately $16.67
- The buggy code calculates tax as $20.00
- Customers are overcharged by ~20% on the tax amount
- This results in customers paying more than expected and potential customer complaints about overbilling

## Root Cause

In the `calcTax` function, the line `return (total - (total / 1.2));` was changed to `return (total * 0.2);`. The original formula correctly calculates the VAT component (20% of the net amount = total/6), while the new formula incorrectly applies a flat 20% multiplier to the subtotal. This overcharges customers.

## Fix

Change line 357 in `cart/server.js` back from:
```javascript
return (total * 0.2);
```
to:
```javascript
return (total - (total / 1.2));
```
