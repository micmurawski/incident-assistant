# Fault: Order History Update Logic Inverted

## Description
Changed the condition for updating order history in `payment/payment.py` from `if not anonymous_user:` to `if anonymous_user:` on line 104.

## Symptom
Registered users will not see their new orders in their order history. Anonymous users will trigger an unnecessary API call to the user service (which will return 404 and be ignored).

## Root Cause
The logic for determining whether to update the order history was inverted. The payment service now attempts to update the order history for anonymous users (who don't have an account) and skips updating the order history for registered users.

## Fix
Revert line 104 in `payment/payment.py` to use `not`:
```python
    if not anonymous_user:
```
