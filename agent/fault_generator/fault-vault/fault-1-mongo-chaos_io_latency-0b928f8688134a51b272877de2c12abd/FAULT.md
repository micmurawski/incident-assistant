# Fault: N+1 MongoDB Query Pattern in Catalogue and User Services

## Description

The catalogue and user services were modified to perform additional database queries per request, turning what were single-query handlers into N+1 query patterns and significantly multiplying the number of MongoDB round-trips per request.

### Changes Made

1. **`catalogue/server.js`** — endpoints rewritten to perform N+1 lookups:
   - `/products`: now performs an extra `findOne()` for each product returned.
   - `/products/:cat`: same enrichment loop for category listings.
   - `/search/:text`: same enrichment loop for search results.

2. **`user/server.js`** — endpoints add additional MongoDB calls:
   - `/users`: now fetches the order document for each user (N additional queries against `ordersCollection`).
   - `/login`: now queries the orders collection to include `orderCount` in the login response.

## Symptom

- Catalogue listing, category, and search endpoints become very slow under any non-trivial result set.
- `/users` and `/login` on the user service show greatly elevated latency.
- Health checks still report "OK" while user-facing endpoints either time out or take seconds to respond.
- The system feels sluggish across most browsing actions, especially as catalog size grows.

## Root Cause

The application code is the root cause: each handler now makes one MongoDB call per item returned (N+1 pattern) instead of a single bulk query. On a healthy MongoDB with sub-millisecond round-trips this is wasteful but rarely catastrophic, which is how the regression slipped through.

A `NetworkChaos delay` experiment is concurrently applied to the mongo pod (~300ms, correlation 100), adding sustained round-trip latency to every MongoDB call. The application bug — the N+1 query loops — multiplies that latency by the number of items in the result set:
- `/products` with ~10 items: `1 + 10` round-trips × `~300ms` ≈ `~3.3s` (was ~300ms).
- `/users` with ~3 users: `1 + 3` round-trips × `~300ms` ≈ `~1.2s` (was ~300ms).

The chaos experiment is a contributing environmental condition, not the root cause. The N+1 pattern would also amplify any future MongoDB slowness — replica failover, primary CPU saturation, network jitter from a noisy neighbor, etc.

## Fix

Revert the application code in `catalogue/server.js` and `user/server.js` to remove the enrichment loops:
- Restore the original `/products`, `/products/:cat`, and `/search/:text` handlers to return the initial query result directly.
- Restore the original `/users` and `/login` handlers to not fetch order data per item.

If the order/enrichment data is genuinely a product requirement, the correct long-term fix is a single bulk query — for example a `$lookup` aggregation, or a `find({ sku: { $in: [...] } })` followed by an in-memory join.
