# Incident: Ratings Service Performance Degradation

## Title

Ratings service experiencing elevated latency and increased error rates

## Description

The ratings service has been experiencing degraded performance affecting end-user experience. Users are reporting slow response times when viewing product ratings and submitting reviews. The issue is impacting both the `/api/rate/{sku}/{score}` and `/api/fetch/{sku}` endpoints.

**Affected endpoints:**
- PUT /api/rate/{sku}/{score}
- GET /api/fetch/{sku}

**Observations:**
- Elevated latency on rating API responses
- Increased CPU utilization on ratings pods
- Elevated 500 error rate from ratings service
- Cascading impact on web frontend product pages

**Metrics affected:**
- API response time p95/p99 increased significantly
- Error rate increased from <1% to ~15%
- CPU usage shows high sustained load

Investigation is ongoing to identify the root cause and implement remediation.
