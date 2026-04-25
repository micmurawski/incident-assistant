# Incident: User Service Saturated and Unresponsive

## Description

The user service is failing under what looks like its own load. Login, registration, anonymous-ID generation and order history all time out or return 5xx. Upstream services that fan out to `user` (web and cart) are reporting elevated error rates and slow calls to `user` endpoints.

**Affected user journeys**
- Account login
- Account registration
- Anonymous shopping (requires a unique ID)
- Order history view

**Observed metrics**
- Elevated 5xx rate on user service endpoints.
- User pod CPU close to its limit; memory drifting upward.
- User pod logs dominated by repeated Mongo and Redis connection errors.
- No obvious traffic surge from the frontend — request rate is normal.

The incident is visible to every user attempting to authenticate or browse while signed out.
