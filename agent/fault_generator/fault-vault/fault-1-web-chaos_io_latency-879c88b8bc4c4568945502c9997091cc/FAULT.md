# Fault: Background Order Status Polling Amplifies MySQL I/O Latency

## Description
Added background order status polling functionality to the web frontend's main controller. The `shopform` controller now calls the shipping service endpoint `/api/shipping/check/` every 15 seconds for logged-in users to periodically refresh order status information. This creates additional HTTP requests that proxy through to the shipping service, which relies on MySQL database.

## Changes Made
- **File**: `web/static/js/controller.js` (applied by `git.patch`)
  - Added `updateOrderStatus()` function in the `shopform` controller that makes HTTP GET requests to `/api/shipping/check/` endpoint
  - Configured `setInterval(updateOrderStatus, 15000)` to poll every 15 seconds
  - The polling only triggers for authenticated users (non-anonymous)

- **`k8s/manifests/web.yaml`**
  - The pod template already includes `app: web` in upstream `robot-shop` (needed for Chaos Mesh IOChaos to target web pods). The fault patch does not edit this file.

## Symptom
- Users experience intermittent slow page loads and delays on the web frontend
- The homepage and navigation become sluggish, especially for logged-in users
- HTTP request latency increases for the web service
- Observers will see increased response times for API calls to the shipping service

## Root Cause
The background polling mechanism creates a continuous stream of requests to the shipping service. When the Chaos Mesh IOChaos injects 200ms latency on 50% of MySQL I/O operations, these periodic requests have a high probability of hitting the latency injection. This amplifies the impact of the MySQL I/O chaos experiment, making the delays more noticeable to users as they navigate the site.

## Fix
1. Remove or comment out the `setInterval(updateOrderStatus, 15000)` call in `web/static/js/controller.js`
2. Optionally remove the entire `updateOrderStatus` function if background order status updates are not needed
3. Alternatively, increase the polling interval to reduce the frequency of requests
