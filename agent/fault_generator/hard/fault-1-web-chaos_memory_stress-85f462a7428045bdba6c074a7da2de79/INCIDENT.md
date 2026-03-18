# Incident: Web Service Unavailable Due to Memory Exhaustion

## Title
Web service experiencing intermittent failures and high memory usage

## Description
The web service (robot-shop-web) is currently experiencing availability issues. Users are reporting:
- Slow page load times or timeouts when accessing the storefront
- Intermittent 502/503/504 error pages
- Complete unavailability during peak periods

**Affected Metrics:**
- HTTP 5xx error rate: Elevated (15-30%)
- Response time: P95 > 5s, P99 > 10s  
- Service availability: < 95%
- Memory usage: At container limit with frequent OOM events
- Container restart count: Increasing

The web service is unable to proxy requests to backend services (catalogue, user, cart, shipping, payment, ratings) consistently.

## Impact
- Users cannot browse products or complete purchases
- Order flow is broken at multiple stages
- Customer-facing storefront is degraded
