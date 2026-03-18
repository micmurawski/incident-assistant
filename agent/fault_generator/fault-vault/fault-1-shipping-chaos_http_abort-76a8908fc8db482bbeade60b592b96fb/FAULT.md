# Fault: Shipping Service Cart Communication Failure Amplification

## Description
Modified the CartHelper HTTP client in the shipping service to use an extremely limited connection pool (max 1 connection). This change is in `shipping/src/main/java/com/instana/robotshop/shipping/CartHelper.java`. The connection pool configuration is set to `setMaxTotal(1)` and `setDefaultMaxPerRoute(1)`, severely restricting concurrent HTTP connections to the cart service.

## Symptom
When the HTTP Chaos experiment aborts connections to the shipping service, the already limited connection pool in the shipping-to-cart communication will amplify failures. Users attempting to complete orders will experience:
- Order confirmation failures
- Cart updates not propagating
- Failed checkout processes when shipping is involved
- Increased error rates in the order fulfillment workflow

## Root Cause
The CartHelper class now creates an HTTP client with a connection pool limited to just 1 connection. When combined with the HTTP Chaos experiment that aborts incoming connections to the shipping service, this creates a cascade of failures. The tiny connection pool prevents the shipping service from handling concurrent requests to the cart service, amplifying the impact of any transient network issues or aborted connections.

## Fix
Revert the connection pool configuration to use a more reasonable default. Replace the restrictive pool settings with proper connection pool configuration:
```java
PoolingHttpClientConnectionManager connectionManager = new PoolingHttpClientConnectionManager();
connectionManager.setMaxTotal(20);  // Increase from 1
connectionManager.setDefaultMaxPerRoute(10);  // Increase from 1
```

Alternatively, use the default HTTP client configuration which handles connection pooling automatically.
