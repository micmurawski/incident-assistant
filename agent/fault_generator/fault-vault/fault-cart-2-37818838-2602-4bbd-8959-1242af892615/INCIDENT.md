# Incident: Cart Add Operation is Slow

## Description
We are receiving reports from users that adding items to the shopping cart is taking unusually long. Metrics show a significant increase in latency for the `/add` endpoint in the cart service, with response times consistently spiking above 2 seconds. This is degrading the user experience and potentially leading to cart abandonment.
