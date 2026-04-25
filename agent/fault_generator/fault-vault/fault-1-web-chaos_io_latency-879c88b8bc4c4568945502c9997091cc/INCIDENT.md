# Incident: Elevated Latency on Web Frontend

## Description

We are experiencing elevated latency and slow response times on the web application. Users — particularly logged-in users — are reporting sluggish page loads and delays when navigating the storefront. Monitoring shows increased response times across the web service endpoints.

**Affected metrics:**
- Elevated p95 / p99 latency on the web service
- Increased request duration for API calls served by the web pod
- Users reporting delayed page transitions and slow interactions

**Impact:**
- Logged-in shopping experience feels sluggish
- Anonymous browsing is less affected but still degraded

The issue is under investigation.
