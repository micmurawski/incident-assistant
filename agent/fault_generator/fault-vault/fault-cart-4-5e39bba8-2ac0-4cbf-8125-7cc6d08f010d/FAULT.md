# Unbounded HTTP Connection Growth in Cart Service

## Description

Modified the `getProduct` function in `cart/server.js` to use `agent: false` in the HTTP request options. This disables HTTP agent pooling, causing each request to the catalogue service to create a new TCP connection instead of reusing an existing connection from a persistent pool.

## Symptom

- Under load, the cart service will accumulate open file descriptors (sockets) to the catalogue service
- Eventually, the service will hit the system's file descriptor limit, causing new requests to fail with EMFILE (too many open files) errors
- The `/health` endpoint may still report OK since Redis connectivity is independent
- Add-to-cart operations will fail with connection errors when contacting the catalogue service

## Root Cause

The `agent: false` option tells the Node.js HTTP client to create a fresh socket for each request rather than reusing connections from a pool. Under load, this creates unbounded socket growth as each request to `/add/:id/:sku/:qty` triggers a call to `getProduct()`. The system will run out of available file descriptors, causing the application to become unresponsive.

## Fix

Remove the `agent: false` option from the request configuration to enable default HTTP agent pooling:

```javascript
request({
    url: 'http://' + catalogueHost + ':8080/product/' + sku,
}, (err, res, body) => {
```

Or simply use the original form:

```javascript
request('http://' + catalogueHost + ':8080/product/' + sku, (err, res, body) => {
```
