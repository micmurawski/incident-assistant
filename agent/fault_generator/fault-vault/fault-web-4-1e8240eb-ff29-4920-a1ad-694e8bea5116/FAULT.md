# Fault: Unbounded Session Cache in User Service

## Title
Unbounded In-Memory Session Cache Causing Memory Exhaustion in User Service

## Description
A runtime/state fault was introduced in the user service (`user/server.js`). A global in-memory object `sessionCache` was added to track user login activity for analytics purposes, but no eviction policy or size limit was implemented.

**Changes made:**
- Added `var sessionCache = {}` as a global object at line 37
- Modified the `POST /login` endpoint (lines 118-147) to store login session information in the `sessionCache` object on each successful login, including:
  - Username (used as key)
  - Timestamp
  - Client IP address
  - User agent string

## Symptom
- User service memory usage grows continuously over time
- Under moderate to high traffic, the service will eventually exhaust available memory and crash (OOM kill)
- Response times may degrade before crash as V8 garbage collector works harder
- Kubernetes pod restarts due to memory limits being exceeded
- Health checks may fail as the process becomes unresponsive

## Root cause
The `sessionCache` object grows unbounded because:
1. Each unique user that logs in is stored as a key
2. There is no TTL (time-to-live) or eviction mechanism
3. The cache is never cleaned up, even when users stop using the system
4. Under load with many unique users, memory consumption scales linearly with login count
5. Even failed login attempts may populate cache if the code path is reached

## Fix
Remove or limit the session caching mechanism:

**Option 1 (Recommended):** Remove the session caching entirely
- Delete the `sessionCache` declaration (line 37)
- Remove the caching code from the `/login` endpoint handler (lines 126-131)

**Option 2:** Add a bounded cache with eviction
- Use a proper cache library like `lru-cache` with max size
- Example: `const cache = new LRU({ max: 1000 })`
- Implement TTL for entries

To revert the changes:
```bash
# Remove the sessionCache variable declaration (line 37)
# Remove the session caching code in /login handler (lines 126-131)
```
