# Fault: Blocking Health Check

## Description
A blocking operation was introduced into the `/health` endpoint of the catalogue service. This operation simulates a long-running task by busy-waiting for a configurable number of seconds, controlled by the `HEALTH_CHECK_BLOCK_SECONDS` environment variable.

## Changes Made
- Modified `catalogue/server.js` at line 63 to introduce a busy-wait loop within the `/health` endpoint.
- The duration of the busy-wait is determined by the `HEALTH_CHECK_BLOCK_SECONDS` environment variable.

## Symptom
- The `/health` endpoint of the catalogue service will become unresponsive or take a long time to respond.
- Health checks from orchestrators (like Kubernetes) will fail, potentially leading to the service being restarted or marked as unhealthy.
- Other endpoints of the catalogue service might also experience delays if the health check is frequently called and consumes significant CPU.

## Root Cause
The `/health` endpoint, which is typically expected to be fast and lightweight, now includes a blocking busy-wait loop. This loop consumes CPU cycles and prevents the endpoint from responding promptly, causing it to appear unhealthy or unresponsive to external checks.

## Fix
Remove the busy-wait loop from the `/health` endpoint or set the `HEALTH_CHECK_BLOCK_SECONDS` environment variable to 0.

Example fix (remove busy-wait):
```javascript
app.get('/health', (req, res) => {
    var stat = {
        app: 'OK',
        mongo: mongoConnected
    };
    res.json(stat);
});