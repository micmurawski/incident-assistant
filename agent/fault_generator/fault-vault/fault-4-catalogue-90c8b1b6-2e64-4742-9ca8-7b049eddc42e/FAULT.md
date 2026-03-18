# Fault: Leaking MongoDB Connections

## Description
A fault was introduced in the `catalogue` service where the `mongoConnected` flag is always set to `true` in the `mongoLoop` function, regardless of whether the MongoDB connection was successfully established or not. This can lead to a continuous attempt to reconnect and open new connections without properly closing previous failed ones, resulting in a connection leak.

## Changes Made
- Modified `catalogue/server.js` at line 173. The `mongoConnected = true;` assignment was moved outside the `then` block of the `mongoConnect()` promise, causing it to always be set to true.

## Symptom
- The `catalogue` service will report itself as healthy via the `/health` endpoint (because `mongoConnected` is always true), even if it cannot establish a stable connection to MongoDB.
- Over time, the `catalogue` service might experience increased resource consumption (e.g., file descriptors, memory) due to accumulating open but unused or failed MongoDB connections.
- Database-related operations (e.g., `/products`, `/product/:sku`) might intermittently fail or become very slow, as the service attempts to use faulty connections.
- The MongoDB server might show an increasing number of open connections from the `catalogue` service.

## Root Cause
The `mongoConnected` flag, which indicates the health of the MongoDB connection, is prematurely and unconditionally set to `true`. If `mongoConnect()` fails, the `catch` block will trigger a retry, but the application will proceed as if connected. This means the application will continue to try and establish new connections on a timer, while the `mongoConnected` flag remains `true`, leading to a continuous accumulation of unclosed connections if the initial connection or subsequent retries fail.

## Fix
Move the `mongoConnected = true;` assignment back inside the `then` block of the `mongoConnect()` promise, ensuring it is only set to `true` upon a successful connection.

Example fix:
```javascript
function mongoLoop() {
    mongoConnect().then((r) => {
        mongoConnected = true;
        logger.info('MongoDB connected');
    }).catch((e) => {
        logger.error('ERROR', e);
        setTimeout(mongoLoop, 2000);
    });
}