# Incident: Cart and User Services Failing

## Description

Users are reporting that they cannot add items to the cart, update quantities, or complete the checkout flow. New visitors are also unable to proceed past the landing page because anonymous ID generation fails. The web frontend shows repeated 500 errors coming from the cart and user services, and these errors persist even across several minutes of observation.

**Affected services / endpoints**
- `cart` — `/add`, `/update`, `/cart/*`, `/shipping`
- `user` — `/uniqueid`, `/login`, `/register`

**Observed metrics**
- 5xx rate on cart service elevated well above baseline.
- Cart service `/health` reports its Redis dependency as not connected.
- No automatic recovery observed over the monitoring window.

All users attempting to shop are impacted.
