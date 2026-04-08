# Fault: Aggressive Connection Retry Logic in User Service

## Description
Modified the user service (`user/server.js`) to use aggressive connection retry logic for both MongoDB and Redis dependencies:

1. **MongoDB connection retry**: Reduced retry interval from 2000ms to 100ms, causing rapid reconnection attempts
2. **Redis connection**: Added aggressive retry strategy with:
   - Short connect_timeout (500ms)
   - High max_attempts (20)
   - Aggressive retry delays that scale quickly
   - Automatic reconnection in error handler

## Symptom
- Users experience failures when accessing the application
- Login and registration operations fail
- Unique ID generation (required for browsing) fails
- High CPU usage on user service pods due to connection storms
- Application logs show repeated connection errors to MongoDB and Redis

## Root Cause
During a network partition where the user service cannot reach MongoDB and Redis:
- The 100ms retry interval causes 600 connection attempts per minute to MongoDB
- Redis retry logic with auto-reconnect creates additional connection storms
- Combined effect creates resource exhaustion (CPU, memory, network connections)

## Fix
1. Increase MongoDB connection retry interval to 2000ms or higher
2. Remove aggressive Redis retry configuration - use default settings
3. Remove automatic reconnection call in Redis error handler
4. Consider adding circuit breaker pattern for database connections
