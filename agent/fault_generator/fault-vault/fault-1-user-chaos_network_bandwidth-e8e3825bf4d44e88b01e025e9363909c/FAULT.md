# FAULT.md

## Title
User service session cache adds Redis dependency to critical endpoints

## Description
Added a session caching layer to the user service that adds Redis calls to the `/login` and `/check/:id` endpoints. These endpoints now first query Redis before falling back to MongoDB, effectively doubling or tripling the network operations per request.

Changes made to `user/server.js`:
- Added `getSessionCache()` and `setSessionCache()` helper functions that interface with Redis
- Modified `/login` endpoint to check Redis cache before querying MongoDB
- Modified `/check/:id` endpoint to check Redis cache before querying MongoDB

## Symptom
Under network bandwidth constraints (1mbps), the user service experiences significantly degraded performance. Users will experience:
- Slow login response times (several seconds)
- Failed login attempts with timeout errors
- Slow or failed user validation checks
- Increased error rates on the user service

## Root Cause
The Chaos Mesh experiment limiting bandwidth to 1mbps exposes a hidden dependency. Each login request now requires:
1. Redis GET (cache check)
2. MongoDB query (on cache miss)
3. Redis SETEX (on successful login)

This is 3 network round-trips instead of 1. Under the 1mbps bandwidth limit, these additional network operations create significant latency and can cause timeouts.

## Fix
To resolve this issue:
1. Remove the session caching layer from the `/login` endpoint - revert to direct MongoDB queries
2. Remove the session caching layer from the `/check/:id` endpoint - revert to direct MongoDB queries

The cache functions `getSessionCache()` and `setSessionCache()` can be removed entirely if no other endpoints use them.
