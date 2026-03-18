# Fault: Increased Database Query Complexity Amplifying MongoDB Latency Impact

## Description
The catalogue and user services have been modified to perform additional database queries per request, significantly amplifying the impact of MongoDB I/O latency.

### Changes Made:

1. **catalogue/server.js** - Modified multiple endpoints to perform redundant database lookups:
   - `/products` endpoint: Now performs an additional `findOne()` query for each product returned (N+1 query pattern)
   - `/products/:cat` endpoint: Added enrichment queries for each product in a category
   - `/search/:text` endpoint: Added enrichment queries for each search result

2. **user/server.js** - Modified endpoints to add additional MongoDB queries:
   - `/users` endpoint: Now fetches order history for each user, performing N additional queries
   - `/login` endpoint: Now queries the orders collection to include order count in response

These changes transform simple queries into N+1 query patterns, multiplying the number of MongoDB operations per request.

## Symptom
- Catalogue service response times increase significantly (each product lookup adds ~300ms due to IOChaos)
- User service login and user list endpoints become very slow
- Overall system appears sluggish as every catalog browsing action triggers multiple database queries
- Health checks may still report "OK" but endpoints timeout or take very long

## Root Cause
The Chaos Mesh IOChaos experiment introduces 300ms latency to all MongoDB I/O operations. By changing the application code to perform additional sequential queries per item (N+1 pattern), the latency multiplies:
- `/products` with 10 items: 1 initial query + 10 enrichment queries = ~3300ms (was ~300ms)
- `/users` with 3 users: 1 initial query + 3 order lookups = ~1200ms (was ~300ms)

## Fix
Revert the code changes in catalogue/server.js and user/server.js to remove the enrichment logic:
- Restore original `/products`, `/products/:cat`, `/search/:text` endpoints to return data directly without additional queries
- Restore original `/users` and `/login` endpoints to not fetch order data

Alternatively, optimize the queries by using MongoDB aggregation pipelines or `$in` queries to fetch all data in a single operation.
