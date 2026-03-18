# Incident: Shipping and Ratings Services Outage

## Description
Shipping and ratings services are currently experiencing complete outages. All endpoints in both services are returning connection errors and are unavailable to users.

Affected services:
- Shipping service: All API endpoints returning 500 errors
- Ratings service: Rating fetch and update endpoints returning 500 errors

Impact:
- Users cannot view shipping options or calculate shipping costs
- Users cannot view or submit product ratings
- Checkout flow is disrupted

Monitoring shows elevated error rates on both services with database connection failures.
