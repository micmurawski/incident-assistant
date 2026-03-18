# Fault: Performance Degradation Under CPU Stress

## Description

Several changes were made to the ratings service that degrade performance when the service is under CPU stress:

1. **CatalogueService.php**: Added retry logic with exponential backoff for catalogue service calls. When the catalogue service is slow or unavailable, this causes multiple retry attempts with increasing delays (100ms, 200ms, 400ms), holding CPU cycles during backoff periods.

2. **Database.php**: Added retry logic with exponential backoff for database connections. The connection retry loop can add up to ~1.5 seconds of delay (50ms + 100ms + 200ms + 400ms + 800ms) per failed connection attempt.

3. **RatingsService.php**: Added an in-memory cache with a computationally expensive cache key computation. The `computeCacheKey()` method runs 100 MD5 hash iterations per cache lookup, which consumes significant CPU cycles.

4. **RatingsApiController.php**: Added a "validation" method that performs 1000 SHA-256 hash computations per API request, adding unnecessary CPU overhead.

5. **HealthCheckService.php**: Added "additional checks" that perform 5000 MD5 hash computations per health check, adding significant CPU overhead on every health check probe.

## Symptom

Under normal conditions, the ratings service exhibits increased latency. When CPU stress is applied (2 workers at 100% load), these changes compound to cause:
- Elevated response times for rating API endpoints
- Increased CPU utilization
- Potential request timeouts
- Cascading failures when catalogue or database are slow to respond

## Root Cause

The added retry mechanisms and "optimizations" (caching, validation) were implemented without proper timeout handling or circuit breaker patterns. Under CPU stress:
- Retry backoffs compete for limited CPU resources
- The cache key computation adds unnecessary cryptographic overhead
- The SKU validation does 1000 hash computations that serve no functional purpose
- These changes make the service less resilient to high CPU load conditions

## Fix

1. Remove retry logic from CatalogueService or implement proper circuit breaker
2. Remove retry logic from Database connection or limit retries
3. Simplify the cache key computation in RatingsService (use direct key or single hash)
4. Remove the unnecessary SKU validation method from RatingsApiController
5. Remove the performAdditionalChecks method from HealthCheckService
