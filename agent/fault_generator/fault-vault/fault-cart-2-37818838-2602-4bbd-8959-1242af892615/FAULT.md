# Fault: Unnecessary Delay in Product Lookup

## Description
In `cart/server.js`, a 2-second `setTimeout` was added to the `getProduct` function before resolving the promise with the product data.

## Symptom
Users will experience a noticeable delay (at least 2 seconds) every time they add an item to their cart. This makes the application feel sluggish and unresponsive during the shopping process.

## Root Cause
An artificial delay was introduced in the hot path of adding items to the cart. The `getProduct` function, which fetches product details from the catalogue service, now waits 2 seconds before returning the result.

## Fix
Remove the `setTimeout` wrapper in the `getProduct` function and resolve the promise immediately with `resolve(JSON.parse(body));`.
