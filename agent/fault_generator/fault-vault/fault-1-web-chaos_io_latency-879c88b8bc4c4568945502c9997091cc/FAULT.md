# Fault: Background Order-Status Polling in Web Frontend

## Description

A background order-status polling routine was added to the web frontend's main controller. The `shopform` controller in `web/static/js/controller.js` now invokes the shipping service endpoint `/api/shipping/check/:id` every 15 seconds for any logged-in user, in order to "silently refresh" their order status in the page.

## Changes Made

- **File**: `web/static/js/controller.js` (applied by `git.patch`)
  - New `updateOrderStatus()` function inside the `shopform` controller that issues an HTTP `GET` to `/api/shipping/check/<uniqueid>`.
  - `setInterval(updateOrderStatus, 15000)` is registered, polling every 15 seconds.
  - Polling fires for any authenticated (non-anonymous) user; there is no opt-out and no backoff.

## Symptom

- Logged-in users experience intermittent slow page loads and a sluggish UI on the web frontend.
- API calls served by the web pod (including unrelated ones like static asset fetches and other XHRs from the same browser) show elevated response times.
- Browser network panels show frequent in-flight requests to `/api/shipping/check/...`, often piling up on top of each other.
- Anonymous browsing is noticeably less affected than logged-in browsing.
- Shipping service request rate increases without any user action.

## Root Cause

The application root cause is the unconditional 15-second polling loop introduced in `web/static/js/controller.js`. Every authenticated browser session now generates a steady stream of HTTP requests to the web pod, each of which is proxied to the shipping service. On a healthy network this is wasteful but invisible — most of the cost is hidden by sub-millisecond round-trips and connection reuse.

A `NetworkChaos delay` experiment is concurrently applied to the web pod (~200ms, correlation 50), adding latency to traffic in and out of that pod. The polling routine — multiplied across every logged-in session — turns the per-request latency into sustained queueing on the web pod and a noticeably sluggish UI for users browsing the storefront.

The chaos experiment is a contributing environmental condition, not the root cause. Removing the chaos would lower the absolute numbers but the polling loop would still generate constant background load on the web pod and downstream services, and would re-emerge as a visible problem under any future network slowness, increased session count, or shipping-service degradation.

## Fix

1. Remove (or comment out) the `setInterval(updateOrderStatus, 15000)` call in `web/static/js/controller.js`.
2. Optionally remove the entire `updateOrderStatus` function if periodic order-status refresh is not a real product requirement.
3. If background refresh is genuinely needed, use a much larger interval (e.g. 5+ minutes), trigger refresh on user actions rather than on a fixed timer, and cancel the interval when the user logs out or navigates away.
