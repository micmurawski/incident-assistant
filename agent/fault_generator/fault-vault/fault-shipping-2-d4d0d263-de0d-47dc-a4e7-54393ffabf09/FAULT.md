---
title: Incorrect HTTP Status Code Check in Shipping Service
description: The shipping service fails to add items to the cart because it incorrectly checks for a 201 Created status code instead of a 200 OK status code.
---

## Symptom

When a user attempts to add an item to their cart, the shipping service fails to process the request. This results in the item not being added to the cart, and an error message may be displayed to the user. The shipping service logs will show a "Failed with code 200" warning.

## Root Cause

The `addToCart` method in the `CartHelper` class of the shipping service is responsible for making an HTTP POST request to the cart service. The method incorrectly checks for a `201 Created` status code to determine if the request was successful. However, the cart service returns a `200 OK` status code upon successful addition of an item to the cart. This discrepancy causes the shipping service to misinterpret the successful response as a failure.

## Fix

To fix this issue, the `addToCart` method in `CartHelper.java` should be updated to check for a `200 OK` status code instead of a `201 Created` status code. This can be done by changing the following line of code:

```java
if (res.getCode() == 201) {
```

to:

```java
if (res.getCode() == 200) {
```
