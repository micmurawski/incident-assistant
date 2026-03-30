# Incident: Increased Latency on Product Ratings Submission

## Description
We are currently observing a significant increase in latency when users submit new ratings for products. Monitoring indicates that the `POST /api/ratings` endpoint in the ratings service is taking substantially longer to respond than usual, with response times consistently exceeding 1.5 seconds. This is leading to a degraded user experience and potential timeouts for users attempting to rate items. We are investigating the cause of this performance degradation.