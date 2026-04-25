# Incident: Service Degradation Affecting Catalogue and User Services

## Description

Users are experiencing significant performance issues when browsing the product catalogue and when interacting with their account. Catalogue endpoints are timing out or responding very slowly, and the user service is also degraded.

**Affected endpoints:**
- Product listing pages are slow to load
- Product search is timing out for some queries
- User login has high latency
- Listing users (admin / internal) is degraded

**Metrics affected:**
- Elevated p95 / p99 response times on catalogue and user services
- Elevated error / timeout rate on catalogue endpoints
- Reduced throughput for storefront browsing flows

**Impact:**
- Storefront feels sluggish for most browsing actions
- Login is slower than usual

Services remain operational but with degraded performance. The on-call team is investigating.
