# Incident: User Service Degradation

## Description
The user service is experiencing degraded performance affecting authentication and user management functionality. Users are reporting inability to log in, register new accounts, or browse the application. Health checks indicate the service is unable to maintain stable connections to backend dependencies.

Metrics affected:
- Elevated error rates on user service endpoints (>50% failure rate)
- Increased latency on authentication requests
- High CPU utilization on user service pods
- Failed health checks

The issue is impacting all users attempting to access the shopping application.
