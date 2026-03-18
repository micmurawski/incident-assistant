# Fault: Unbounded In-Memory Cache in Payment Service

## Description
Added an in-memory dictionary (`payment_cache`) to store payment verification data for audit trail purposes. The cache grows indefinitely with each payment request and is never cleared or evicted.

## Location
`payment/payment.py` - lines 28-29 (cache declaration) and lines 105-111 (cache usage in `/pay/<id>` endpoint)

## Symptom
- Continuous growth of memory usage in the payment service container
- Eventually leads to OOM (Out of Memory) errors and container restarts
- Monitoring shows increasing RSS memory for the payment pod
- Under high load, the service becomes unresponsive as memory allocation fails

## Root Cause
The code stores complete cart details (including all items, quantities, prices) in a global dictionary keyed by user ID for every successful payment. The cache has no:
- Maximum size limit
- TTL (Time To Live) for entries
- Eviction policy
- Cleanup mechanism

As the system processes payments, the cache accumulates all historical payment data indefinitely, causing unbounded memory growth.

## Fix
To fix this issue, implement one of the following:
1. Add a TTL-based eviction using a library like `cachetools` with `TTLCache`
2. Implement a maximum cache size with LRU eviction policy
3. Remove the cache entirely if not needed for the audit feature
4. Periodically clear old entries based on timestamp

Example fix using `cachetools`:
```python
from cachetools import TTLCache
payment_cache = TTLCache(maxsize=1000, ttl=3600)  # Max 1000 entries, 1 hour TTL
```
