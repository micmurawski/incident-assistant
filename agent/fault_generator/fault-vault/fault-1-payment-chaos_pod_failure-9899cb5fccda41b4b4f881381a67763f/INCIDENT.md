# Incident: Payment Service Unavailable

## Description
Users are experiencing failures when attempting to complete purchases on the e-commerce platform. Payment processing requests are returning HTTP 500 errors, and the payment service health check is reporting as unavailable (HTTP 503).

### Observed Issues
- Payment service `/health` endpoint returns HTTP 503 "service unavailable"
- POST requests to `/pay/<id>` fail with HTTP 500 errors
- Users cannot complete checkout - orders are not being processed
- Payment transactions fail silently from the user perspective

### Affected Metrics
- Payment service availability: 0% (health check failing)
- Successful payment transactions: Dropped to 0
- Order queue throughput: Dropped to 0
- Checkout completion rate: Significantly reduced

### Impact
- Customers cannot complete purchases
- Cart contents may be lost when checkout fails
- Order history not being updated for completed orders
- No new orders being dispatched

### Next Steps
Team is investigating the payment service and its dependencies to restore functionality.
