# Incident: Product Rating Failures

## Description
Users are experiencing failures when attempting to submit product ratings. Monitoring has detected an increase in HTTP 500 errors from the ratings service API. The rating submission endpoint (`/api/rate/{sku}/{score}`) is returning errors, preventing users from rating products. This is affecting a portion of the user traffic.

Affected endpoints:
- `PUT /api/rate/{sku}/{score}` - Rating submission
- `GET /api/fetch/{sku}` - Rating retrieval (may show stale data if rating update fails)

Investigation is ongoing to determine root cause and restore full functionality.