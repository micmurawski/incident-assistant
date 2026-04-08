# Incident: Shipping Service Degradation

## Title
Shipping Service Experiencing High Latency and Timeouts

## Description
Users are reporting slow response times and failed checkout attempts when completing orders. The shipping service is not responding in a timely manner, causing order confirmations to fail. The issue is affecting all users attempting to complete purchases.

Monitoring shows:
- Increased error rates on shipping service endpoints
- High latency on /confirm endpoint (several minutes per request)
- Thread pool exhaustion indicators
- Database connection pool pressure

The issue is currently under investigation. Team is working to restore normal service.
