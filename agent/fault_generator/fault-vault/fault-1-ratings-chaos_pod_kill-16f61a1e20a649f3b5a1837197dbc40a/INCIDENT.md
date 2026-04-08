# Incident: Ratings Service Degraded Performance

## Description
The ratings service is experiencing significantly degraded performance and availability. Users are reporting:
- Extremely slow or unresponsive rating API endpoints
- Timeouts when attempting to fetch or submit product ratings
- Intermittent 500 HTTP errors

Affected metrics:
- API response time increased significantly (p99 > 30s)
- Error rate elevated to ~15%
- Health check failures reported

The issue appears to be affecting all operations in the ratings service and is impacting the overall user experience on the e-commerce platform.
