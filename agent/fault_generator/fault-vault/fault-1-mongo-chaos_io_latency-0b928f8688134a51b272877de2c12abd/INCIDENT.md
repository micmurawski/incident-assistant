# Incident: Service Degradation Affecting Catalogue and User Services

## Description

Users are experiencing significant performance issues when browsing the product catalogue and when logging in. The catalogue service endpoints are timing out or responding very slowly, and the user service is also experiencing elevated latency.

Affected endpoints:
- Product listing pages are slow to load
- Product search is timing out
- User login has high latency
- User registration may be affected

Impacted metrics:
- Increased response times (p99 latency elevated)
- Elevated error rates on catalogue and user service
- Reduced throughput for e-commerce operations

The operations team is investigating the root cause. Services remain operational but with degraded performance.
