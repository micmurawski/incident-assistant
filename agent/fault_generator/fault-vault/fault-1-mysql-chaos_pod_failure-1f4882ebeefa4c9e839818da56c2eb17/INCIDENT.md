# Incident: Shipping and Ratings services experiencing elevated errors

## Description
Shipping and ratings services are experiencing elevated error rates and are responding with 500 errors to user requests. Users are unable to:
- Calculate shipping costs
- View shipping codes and cities
- View or update product ratings

The services may appear to recover briefly but then fail again. Health checks may also report failures for both services.

Affected metrics:
- Elevated HTTP 5xx responses on shipping and ratings endpoints
- Increased latency in database-dependent operations
- Failed health check responses
