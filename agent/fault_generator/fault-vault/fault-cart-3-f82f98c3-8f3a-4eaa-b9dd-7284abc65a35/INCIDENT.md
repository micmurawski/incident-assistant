# Incident: Cart Service Failing to Add Items

## Description
Users are reporting that they are unable to add items to their shopping cart. The web interface shows an error when attempting to add a product. Monitoring indicates an increase in 500 Internal Server Error responses from the cart service, and logs show connection timeouts or "getaddrinfo ENOTFOUND" errors when the cart service attempts to communicate with other internal services.