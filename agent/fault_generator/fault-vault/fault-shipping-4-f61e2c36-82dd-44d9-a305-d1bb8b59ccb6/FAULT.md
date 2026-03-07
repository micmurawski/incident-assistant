# HTTP Connection Pool Exhaustion in Cart Service

## Description

The `CartHelper.java` class was modified to use a static `CloseableHttpClient` instance that is never properly closed. The original code created a new HTTP client for each request using try-with-resources, ensuring proper cleanup. The modified version creates a single static client on first use and reuses it indefinitely without any shutdown or cleanup mechanism.

## Symptom

- Shipping service can initially process requests normally
- Over time, HTTP requests to the cart service begin to fail with connection timeouts
- Service logs may show "http client exception" warnings
- Eventually, the `/confirm/{id}` endpoint becomes unresponsive or returns errors
- Other services depending on shipping may experience cascading failures

## Root Cause

The static `sharedClient` field holds a reference to an HTTP client that maintains a connection pool. Since the client is never closed or shut down:
1. TCP connections remain in TIME_WAIT state
2. The underlying connection pool exhausts available connections
3. New requests block waiting for available connections
4. The application runs out of file descriptors and cannot create new connections

## Fix

Revert to the original implementation that creates a new HTTP client per request wrapped in try-with-resources, or properly shutdown the static client during application shutdown using a `@PreDestroy` method or Spring's `DisposableBean` interface.

Original code pattern:
```java
try (CloseableHttpClient httpClient = HttpClients.custom()...build()) {
    // use client
}
```
