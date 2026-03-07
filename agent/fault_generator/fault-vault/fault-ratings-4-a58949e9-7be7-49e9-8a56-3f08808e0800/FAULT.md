# cURL Handle Resource Leak in Catalogue Service

## Description
Removed the `curl_close()` call from the `CatalogueService::checkSKU()` method in `ratings/html/src/Service/CatalogueService.php`. The cURL handle is initialized but never closed after use.

## Symptom
- The service will function normally initially
- Over time, as more rating PUT requests are made (which call `checkSKU` to validate the SKU against the catalogue service), file descriptors will accumulate
- Eventually the process will exhaust available file descriptors, causing subsequent cURL calls to fail with "Too many open files" errors
- The application may become unresponsive or return 500 errors for SKU validation

## Root Cause
Every call to `checkSKU()` creates a new cURL handle via `curl_init()` but does not call `curl_close()` to release the handle. In PHP, cURL handles are resources that must be explicitly closed. Without closing, each handle remains in memory and holds an open file descriptor to the network socket. Under load, this will rapidly exhaust system resources.

## Fix
Add `curl_close($curl);` before the return statement in the `checkSKU` method:

```php
$status = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
$this->logger->info("catalogue status $status");

curl_close($curl);  // <-- Add this line

return 200 === $status;
```
