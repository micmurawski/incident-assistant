# Fault: Unbounded In-Memory Growth in Cart Service

## Title
Unbounded In-Memory Access Log Causing Memory Exhaustion

## Description
A runtime/state fault was introduced in the cart service (`cart/server.js`). A global in-memory object `accessLog` was added to track cart access patterns for analytics purposes, but no eviction policy or size limit was implemented.

**Changes made:**
- Added `var accessLog = {}` as a global object at line 30
- Modified the `GET /cart/:id` endpoint (lines 87-110) to store every cart access in the `accessLog` object, including:
  - Cart ID (used as key)
  - Timestamp
  - Client IP address
  - User agent string

## Symptom
- Cart service memory usage grows continuously over time
- Under moderate to high traffic, the service will eventually exhaust available memory and crash (OOM kill)
- Response times may degrade before crash as V8 garbage collector works harder
- Kubernetes pod restarts due to memory limits being exceeded
- Health checks may fail as the process becomes unresponsive

## Root cause
The `accessLog` object grows unbounded because:
1. Each unique cart ID accessed is stored as a key
2. There is no TTL (time-to-live) or eviction mechanism
3. The log is never cleaned up, even when carts are deleted
4. Under load with many unique users/carts, memory consumption scales linearly with request count

## Fix
Remove or limit the access logging mechanism:

**Option 1 (Recommended):** Remove the access logging entirely
- Delete the `accessLog` declaration
- Remove the logging code from the `/cart/:id` endpoint

**Option 2:** Add a bounded cache with eviction
- Use a proper cache library like `lru-cache` with max size
- Example: `const cache = new LRU({ max: 1000 })`

To revert the changes:
```bash
# Remove the accessLog variable declaration (line 29-30)
# Remove the access logging code in /cart/:id handler (lines 88-95)
```
