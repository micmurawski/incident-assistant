# Fault: Extended Connection Timeouts and Eager Connection Initialization

## Description
Multiple changes were made to the ratings service that increase the time it takes to detect and recover from failures:

1. **Database.php** (lines 44-46): Added `PDO::MYSQL_ATTR_CONNECT_TIMEOUT` and `PDO::ATTR_TIMEOUT` set to 30 seconds, which extends the time the service waits before considering database connections as failed.

2. **CatalogueService.php** (lines 31-32): Added `CURLOPT_CONNECTTIMEOUT` (15s) and `CURLOPT_TIMEOUT` (25s) to the cURL configuration, extending the timeout for catalogue service calls.

3. **Kernel.php** (line 108): Added `->setLazy(false)` to the PDO database connection, making it initialize eagerly at startup rather than lazily on first use. This causes the application to attempt database connection immediately.

4. **RatingsApiController.php** (lines 48-86): Added retry logic with 500ms (0.5 second) delays between attempts, extending request processing time during failures.

## Symptom
- During pod restarts, users experience significantly delayed error responses (up to 30+ seconds per request)
- Health check endpoints may fail faster during pod restarts due to eager connection initialization
- The ratings service appears unresponsive or slow to respond during failure scenarios
- Increased resource consumption due to retry logic

## Root Cause
The combination of longer timeout values and eager connection initialization means that when pods are killed:
1. The new pod starts and immediately attempts database connections (eager loading)
2. If connections are not ready, the 30-second timeout causes prolonged startup delays
3. Retry logic with 500ms delays causes multiple seconds of additional latency per request during failure recovery

This amplifies the impact of pod kills significantly, turning brief unavailability into extended service degradation.

## Fix
1. Revert the timeout values in Database.php to default (typically 30-60ms)
2. Remove the cURL timeout settings in CatalogueService.php or reduce them
3. Remove `->setLazy(false)` from the PDO connection in Kernel.php
4. Remove or reduce the retry logic in RatingsApiController.php
