# High Latency in Ratings Service

## Description
The ratings service is experiencing significantly increased latency. Users are reporting slow page loads when viewing products, and monitoring shows that requests to the ratings API are taking several seconds to complete.

## Symptom
- High response times for the `/api/fetch/{sku}` endpoint.
- Increased latency when loading product pages on the frontend.
- Potential backlog of requests and increased resource utilization (PHP-FPM workers, database connections) under load.
- No immediate errors, but the system feels sluggish.