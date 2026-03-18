# FAULT.md

## Title
Catalogue service requires inter-pod coordination that fails during network partition

## Description
The catalogue service was modified to include a load coordination mechanism that periodically checks the health of other catalogue service instances through the Kubernetes service. This coordination is used as a prerequisite for serving API requests - the service will not serve product data until it has successfully coordinated with another instance.

**Location of change:** `catalogue/server.js`

**Changes made:**
1. Added HTTP client module import for inter-service communication
2. Added `coordinationState` object to track coordination status between instances
3. Added `coordinateLoadBalancing()` function that makes HTTP requests to the catalogue service every 5 seconds
4. Modified all product API endpoints (`/products`, `/product/:sku`, `/products/:cat`, `/categories`, `/search/:text`) to check coordination status before serving requests
5. Added `isServiceReady()` helper function that returns `true` only when coordination is successful

## Symptom
When the Chaos Mesh network partition experiment is running:
- All catalogue API endpoints return HTTP 503 "service initializing" errors
- The service health check may show `coordinated: false`
- Users cannot browse products, search products, or view product categories
- The web application's product pages will fail to load

## Root Cause
The network partition isolates catalogue pods from each other. The catalogue service now requires successful inter-pod communication (via the Kubernetes service) before it will serve any API requests. When the partition blocks this communication, the coordination state becomes `ready: false`, causing all API endpoints to return 503 errors.

## Fix
To fix this issue, the coordination logic needs to be removed or made optional:

1. **Remove the coordination requirement:** Delete the `coordinateLoadBalancing()` function and the `coordinationState` dependency in the `isServiceReady()` function. Change `isServiceReady()` to simply return `true` when MongoDB is connected.

2. **Make coordination optional:** Add an environment variable (e.g., `ENABLE_COORDINATION=false`) that controls whether the coordination check is required. When disabled, the service works normally.

3. **Increase tolerance:** Modify the coordination failure handling to allow a grace period or multiple failures before marking the service as not ready.

The quickest fix is to change the `isServiceReady()` function to not depend on coordination:

```javascript
function isServiceReady() {
    return mongoConnected;  // Only require MongoDB connection
}
```
