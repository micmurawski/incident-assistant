# FAULT.md

## Title
Unbounded In-Memory Session Cache Causes Memory Exhaustion

## Description
A new in-memory session cache (`userCache`) was introduced in the user service (`user/server.js`) to store login session data. Every time a user successfully authenticates via the `/login` endpoint, the full request body (including credentials) is pushed to this array without any eviction policy.

## Symptom
Over time, as more users log in to the application, the memory usage of the user service container will continuously grow. Eventually this will lead to:
- Container being OOM (Out of Memory) killed
- Degraded performance or crashes
- Kubernetes restarting the pod repeatedly

## Root Cause
The `userCache` array grows unbounded with each login request. There is no:
- Maximum size limit
- TTL (Time-To-Live) eviction
- Any cleanup mechanism

Each login pushes an object containing `userId`, `loginTime`, and the entire `sessionData` (including plaintext password) into the array, which is never removed.

## Fix
To fix this fault, remove the cache accumulation code from the login handler. The session data should either:
1. Not be stored in memory at all (stateless)
2. Use a proper cache with eviction (e.g., Redis with TTL)
3. Implement a bounded cache with LRU eviction

The simplest fix is to remove lines 129-137 that push to `userCache` and remove the `userCache` variable declaration.
