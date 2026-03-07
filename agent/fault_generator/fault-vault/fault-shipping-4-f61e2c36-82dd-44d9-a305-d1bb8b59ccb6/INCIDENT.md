# Incident: Shipping Confirm Endpoint Failing Over Time

## Description
Shipping initially works, then HTTP requests to the cart service begin to time out. The confirm endpoint becomes unresponsive or returns errors. Logs may show HTTP client exceptions. Services that depend on shipping can see cascading failures.