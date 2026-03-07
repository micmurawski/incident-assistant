# FAULT.md

## Title
Redis Connection Leak on Unique ID Generation

## Description
In `user/server.js`, the `/uniqueid` endpoint was modified to create a new Redis client for every request instead of using the global `redisClient`. The newly created client is never closed or destroyed.

## Symptom
The user service will gradually consume more memory and file descriptors. Redis will also see a continuous increase in connected clients. Eventually, the user service will crash due to resource exhaustion (OOM or too many open files), or Redis will reject new connections, causing the `/uniqueid` endpoint and other Redis-dependent services to fail.

## Root Cause
A new Redis connection is established per request to `/uniqueid` without ever calling `quit()` or `end()` on the client, leading to a connection leak.

## Fix
Revert the `/uniqueid` endpoint to use the globally initialized `redisClient` instead of creating a new client per request.
