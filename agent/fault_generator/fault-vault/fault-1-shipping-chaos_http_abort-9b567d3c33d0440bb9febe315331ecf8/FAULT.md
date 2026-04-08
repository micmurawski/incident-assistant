# Fault: Increased Retry Delay and Timeout Amplification in Shipping Service

## Description
Modified the CartHelper HTTP client to use significantly longer timeouts (from 5 seconds to 60-120 seconds) and added retry logic with 5 attempts. Also increased the database connection retry backoff multiplier from 2.3 to 3.5 with max delay increased from 30s to 60s. Added an oversized thread pool configuration (50-100 threads) that can lead to thread exhaustion under load.

## Symptom
When the HTTP chaos abort experiment runs, shipping service requests will hang for extended periods (up to several minutes per request) due to:
- Very long HTTP client timeouts (60s connect, 60s connection request, 120s response)
- Retry attempts with exponential backoff (up to 5 attempts)
- Increased database connection retry delays
- Thread pool exhaustion from accumulated threads waiting on slow/failed HTTP calls

Users will experience very slow response times or timeouts when trying to complete orders.

## Root Cause
The combination of increased timeouts and retry logic causes each failed HTTP request to consume significant server resources (threads, connections) for extended periods. When the Chaos Mesh HTTP abort experiment runs, the service becomes overwhelmed with long-running requests that cannot complete, leading to resource exhaustion and cascading failures.

## Fix
1. Reduce HTTP client timeouts to reasonable values (5-10 seconds)
2. Remove or limit retry attempts for HTTP calls to the cart service
3. Reduce database connection retry backoff parameters
4. Properly size the thread pool based on expected load
5. Add circuit breaker pattern to handle failing dependencies
