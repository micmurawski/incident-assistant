# Incident: Catalogue Service Unavailable During Network Partition

## Description

The catalogue service became unavailable during a network partition experiment. Users experienced failures when browsing the product catalogue, searching for products, and viewing product details. The service exhibited repeated restarts and was unable to recover while the network partition was in effect.

**Affected Components:**
- Catalogue service (all endpoints: /products, /product/:sku, /products/:cat, /categories, /search/:text)

**Impact:**
- Product catalogue not loading on the web frontend
- Product search functionality broken
- Users unable to browse products by category

**Metrics Observed:**
- Increased 5xx error rate from catalogue service
- Pod restart count increased significantly
- Health check failures on liveness and readiness probes
- High CPU usage on catalogue pods due to connection attempts

**Duration:**
- Service was unavailable for the duration of the network partition experiment
