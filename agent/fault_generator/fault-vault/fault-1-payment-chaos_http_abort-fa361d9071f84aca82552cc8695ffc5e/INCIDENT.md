# Incident: Payment Service Failures and Duplicate Orders

## Description

Users are experiencing payment failures and duplicate orders during checkout. The payment service is returning HTTP 503 errors ("Service is currently unavailable") causing checkout failures. Additionally, support has reported cases of:

- Customers being charged multiple times for the same order
- Empty shopping carts after failed payment attempts
- Duplicate orders appearing in the dispatch system
- Inconsistent order history records

**Affected Service**: payment (port 8080)

**Impact**:
- Checkout completion rate has dropped significantly
- Customer support tickets related to payment issues have increased
- Potential revenue loss from failed transactions
- Potential financial impact from duplicate charges

**Monitoring Observations**:
- HTTP 503 error rate spiked on the payment endpoint
- Anomalous spike in orders queued to dispatch without corresponding successful payment responses
- Cart service showing increased delete operations
- Customer complaints about being charged but not receiving order confirmation
