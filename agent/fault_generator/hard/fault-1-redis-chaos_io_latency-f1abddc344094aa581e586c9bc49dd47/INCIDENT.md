# Incident: Elevated Latency in Cart and User Services

## Description

We are currently experiencing elevated response times on the cart and user services. Users are reporting slow page loads and delays when adding items to cart or generating unique identifiers.

**Affected services:**
- Cart service - all cart operations (add, update, delete, shipping)
- User service - unique ID generation

**Metrics affected:**
- Increased p95 and p99 latency on cart service endpoints
- Increased response time on user /uniqueid endpoint
- Overall throughput degradation

**Impact:**
- Slower shopping experience
- Potential timeout issues for users with slow connections

Investigation is ongoing to identify the root cause and implement a fix.
