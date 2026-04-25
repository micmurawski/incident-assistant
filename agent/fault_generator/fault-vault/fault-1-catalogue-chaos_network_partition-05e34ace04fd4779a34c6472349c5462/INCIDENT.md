# Incident: Product Browsing Broken Across the Shop

## Description

Users report that product pages, category pages, and product search are failing on the storefront. Adding an item to cart frequently fails as well, because the cart cannot fetch the SKU details it needs. The problem is consistent across sessions — not user-specific — and is affecting all shoppers on the web application.

**Affected user journeys**
- Homepage product grid
- Category browse
- Product detail page
- Product search
- "Add to cart" on any new item

**Observed metrics**
- Elevated 5xx rate on the web frontend.
- Elevated client-side error rate on cart → catalogue calls (timeouts and connection refused).
- Catalogue service itself shows no pod restarts and stable CPU / memory.

No recent catalogue deploy was flagged by the change tracker at the start of the window, but a recent code change to the catalogue service is visible in git history.
