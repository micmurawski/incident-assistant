# Fault: Aggressive Redis Connection Retry Configuration

## Description
Modified the Redis client configuration in both cart and user services to use an aggressive retry strategy. The retry_strategy now returns an error to stop retrying after only 10 attempts with small delays, rather than continuing to retry indefinitely.

## Changes Made
- **cart/server.js**: Added `retry_strategy` option to Redis client configuration that:
  - Stops retrying immediately on connection refused errors
  - Limits total retry attempts to 10
  - Stops retrying after 5 minutes total retry time
  
- **user/server.js**: Added identical `retry_strategy` option to Redis client configuration

## Symptom
- Cart service returns 500 errors when attempting to add, update, or retrieve cart items
- User service fails to generate unique IDs for anonymous users
- Health check shows Redis as not connected
- All cart operations fail with Redis connection errors

## Root Cause
When Redis experiences a network partition (as in the Chaos Mesh experiment), the connection will be refused. The new retry strategy stops retrying after only 10 attempts (~20 seconds), leaving the service without a Redis connection for the remainder of the 60-minute partition. Without Redis, cart operations cannot complete and unique user ID generation fails.

## Fix
Revert the Redis client configuration to remove the custom retry_strategy, allowing default infinite retry behavior that maintains connection attempts throughout the network partition. Replace the retry_strategy configuration with the default configuration:

```javascript
var redisClient = redis.createClient({
    host: redisHost
});
```
