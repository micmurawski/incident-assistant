# Fault: Cart Validation Logic Inverted

## Description
Changed the cart validation condition in `payment/payment.py` from `or` to `and` on line 78. The original code correctly rejected carts that had zero total OR missing shipping. The changed code now only rejects carts when BOTH conditions are true (total is zero AND shipping is missing simultaneously).

## Symptom
Valid checkout requests are failing. Specifically:
- Carts with valid total (>0) but missing shipping items are being ACCEPTED (should be rejected)
- Carts with zero total but having shipping items are being ACCEPTED (should be rejected)

Users see "cart not valid" errors for legitimate carts, or payments go through for invalid carts.

## Root Cause
The logical operator change from `or` to `and` inverts the validation logic:
- Original (`or`): Reject if total=0 OR shipping missing (correct - needs both conditions to pass)
- Buggy (`and`): Only reject if total=0 AND shipping missing simultaneously

This means invalid carts can now pass validation when they shouldn't.

## Fix
Revert line 78 in `payment/payment.py` to use `or`:
```python
if cart.get('total', 0) == 0 or has_shipping == False:
```
