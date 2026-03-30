# Fault: Catalogue Service HTTP Timeout Configuration in Ratings Service

## Description
The ratings service relies on calling the catalogue service to verify product SKUs before allowing ratings to be submitted. In `ratings/html/src/Service/CatalogueService.php`, the HTTP client was configured with explicit timeout values (`CURLOPT_TIMEOUT` set to 3 seconds and `CURLOPT_CONNECTTIMEOUT_MS` set to 200 milliseconds). Under normal network conditions, these values work correctly, but when network bandwidth is constrained, the catalogue service calls fail more frequently.

## Symptom
Users attempting to rate products may receive HTTP 500 errors with message "Unable to update rating" when the ratings service fails to connect to the catalogue service. The error log shows "failed to connect to catalogue" messages. This manifests as failed rating submissions even though the product exists in the system.

## Root Cause
The HTTP client timeouts in CatalogueService.php were set to 3 seconds total timeout and 200ms connection timeout. Under network congestion conditions (such as bandwidth throttling), HTTP requests to the catalogue service frequently exceed these thresholds, causing the curl requests to fail and throwing exceptions that propagate to the API endpoint.

## Fix
Adjust the timeout values in `ratings/html/src/Service/CatalogueService.php` to be more tolerant of network latency:
- Increase `CURLOPT_TIMEOUT` from 3 seconds to a higher value (e.g., 30 seconds)
- Increase `CURLOPT_CONNECTTIMEOUT_MS` from 200ms to a more reasonable value (e.g., 2000ms)

Or alternatively, remove explicit timeout configuration to use the system defaults (which are typically much higher).