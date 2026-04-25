# Incident: Catalogue Service Flapping / Restarting

## Description

The catalogue microservice is unstable. It restarts repeatedly and its pod alternates between `Running` and `NotReady` states faster than it can serve meaningful traffic. When a user hits the storefront, product listings, search and product detail pages either error out or hang for the request timeout.

**Affected user journeys**
- Homepage product grid
- Category browse
- Product detail page
- Product search
- Cart operations that require a SKU lookup

**Observed metrics**
- 5xx rate from the catalogue service elevated and noisy.
- Catalogue pod restart counter climbing steadily during the incident.
- Liveness and readiness probe failures visible in Kubernetes events.
- Elevated CPU on the catalogue pod despite no traffic surge upstream.

The impact is fleet-wide: every user of the storefront sees broken or degraded product browsing.
