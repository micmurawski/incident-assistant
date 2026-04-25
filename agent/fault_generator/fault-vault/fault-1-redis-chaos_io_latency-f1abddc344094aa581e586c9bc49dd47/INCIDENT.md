# Incident: Elevated Latency in Cart and User Services

## Description

We are currently experiencing elevated response times on the cart and user services. Users are reporting slow page loads and delays when adding items to their cart and when generating new sessions.

**Affected services:**
- Cart service — all cart operations (add, update, delete, shipping)
- User service — `/uniqueid` (anonymous session creation)

**Metrics affected:**
- Increased p95 and p99 latency on cart service endpoints
- Increased response time on the user `/uniqueid` endpoint
- Overall throughput degradation on the storefront

**Impact:**
- Slower shopping experience
- Risk of timeouts for users on slow connections

Investigation is ongoing to identify the root cause and implement a fix.
