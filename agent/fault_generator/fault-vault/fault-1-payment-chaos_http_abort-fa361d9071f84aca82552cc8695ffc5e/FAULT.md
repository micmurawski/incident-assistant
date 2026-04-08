# Fault: Premature Order Processing Before Payment Verification

## Description
The payment service has been modified to process orders before verifying payment. The order of operations in `payment/payment.py` has been changed so that:
1. The order is queued to RabbitMQ (via `queueOrder`) **before** the payment gateway is called
2. The cart is deleted **before** payment verification completes
3. The order history is updated **before** payment is confirmed

This reordering appears to be an optimization or refactoring but introduces a critical race condition.

## Symptom
When the HTTPChaos experiment aborts the payment request (returning 503), users experience:
- Order appears in the dispatch queue but user receives an error
- Cart is empty but payment failed
- Users may retry payment, creating duplicate orders
- User order history may show duplicate or missing orders
- Confusing customer experience with inconsistent order state

## Root Cause
The payment flow violates the atomic transaction pattern. By queueing the order and deleting the cart before the payment gateway verification, the system creates a non-atomic operation. When the payment request is aborted (as in the HTTPChaos experiment), the order has already been committed to the queue but the user sees a failure, leading to:
- Orphaned orders in the dispatch queue
- Potential duplicate orders when users retry
- Lost cart data after failed payment

## Fix
Revert the payment flow to the correct order of operations:
1. Verify payment with payment gateway first
2. Generate order ID
3. Queue order to RabbitMQ
4. Delete cart
5. Add to order history
6. Return success to user

This ensures payment is verified before any state changes are committed.
