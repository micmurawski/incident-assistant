# Title: Inverted cart validation logic prevents all payments

## Description
In `payment/payment.py`, the condition to check for a valid cart total was changed from `cart.get('total', 0) == 0` to `cart.get('total', 0) > 0`. This inverts the logic, causing the payment service to reject any cart with a non-zero total.

## Symptom
Users will be unable to complete any purchases. The payment service will consistently return a "cart not valid" error (HTTP 400) for any cart that has items in it.

## Root cause
The logical operator in the cart validation check was flipped. The service now incorrectly identifies valid carts as invalid, effectively blocking all transactions.

## Fix
Revert the change in `payment/payment.py` from `>` back to `==` to restore the correct validation logic.
