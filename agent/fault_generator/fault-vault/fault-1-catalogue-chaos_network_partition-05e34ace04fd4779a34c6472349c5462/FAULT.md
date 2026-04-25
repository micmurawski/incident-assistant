# Fault: Catalogue Unreachable From Consumers, Plus Fragile Readiness Code

## Description

Two things coincide in this incident:

1. **Application change (`catalogue/server.js`).** A recent commit added an inter-service "load coordination" feature:
   - A `coordinateLoadBalancing()` function that issues an HTTP GET to `http://catalogue:8080/health` every 5 seconds.
   - A `coordinationState` object populated by those calls.
   - An `isServiceReady()` helper that returns `!coordinationState.initialized || coordinationState.ready`.
   - Every product-serving endpoint (`/products`, `/product/:sku`, `/products/:cat`, `/categories`, `/search/:text`) was modified from `if (mongoConnected)` to `if (mongoConnected && isServiceReady())`, and the unhappy path was changed from HTTP 500 "database not available" to HTTP 503 "service initializing".
   - The `/health` handler was overwritten to also report the coordination status.

2. **A `NetworkChaos partition` experiment** has been applied for 60 minutes between the `catalogue` pod and its two direct consumers `cart` and `web`, in both directions.

## Symptom

- Web frontend product pages fail to load; users see errors when opening the home page, a category, or a product detail page.
- Cart service fails when resolving SKUs against `catalogue` (request hangs until timeout, then 5xx bubbles up).
- Direct curl from cart or web pods to `catalogue:8080` either times out or is refused at the Service VIP.
- A curl from the catalogue pod itself to `http://catalogue:8080/health` still succeeds and returns `{app:'OK', mongo:true, coordinated:true}`.
- There are no crashes or restarts on the catalogue pod; its logs are quiet.

## Root Cause

The primary cause is the `NetworkChaos partition` dropping all traffic between the `catalogue` pod and `{cart, web}` in both directions. `cart` and `web` can no longer reach `catalogue`, so any user request that fans out to the catalogue (almost all product traffic) fails at the client side with a connect timeout or connection refused — not with an HTTP 503 from catalogue.

The recent patch's "load coordination" code is a **red herring** under this incident shape. Because there is only one `catalogue` replica, the `coordinateLoadBalancing()` call resolves `catalogue` to the Service VIP and iptables DNAT routes the packet straight back to the same pod — a loopback that the partition rules do **not** block (the partition is scoped to `cart` and `web`, not to the catalogue pod itself). So `coordinationState.ready` stays `true`, `isServiceReady()` keeps returning `true`, and catalogue keeps serving 200s to the tiny amount of traffic that can still reach it. The added check does not fire.

The coordination patch is still a code smell: with >1 catalogue replica (or a future partition that isolates catalogue from itself via the Service), it *would* cause spurious 503s on every product endpoint. It also rewrites the unhappy path from 500 to 503, which changes upstream retry behaviour. But for *this* incident, the operator-visible behaviour is fully explained by the partition alone.

## Fix

1. **Remove the chaos condition.** Delete the NetworkChaos resource (`kubectl delete networkchaos -n application chaos-network-partition-application`) to restore cart ↔ catalogue and web ↔ catalogue connectivity.
2. **Harden the application code** (follow-up, not required for recovery):
   - Revert the `coordinateLoadBalancing()` / `coordinationState` / `isServiceReady()` additions, or gate them behind an env var that defaults off.
   - Restore the endpoint handlers to `if (mongoConnected) { ... } else { 500 "database not available" }` so that the failure mode is a real dependency check rather than a self-loop readiness dance.
   - Keep `/health` as the original `{ app: 'OK', mongo: mongoConnected }` shape so Kubernetes probes are not entangled with application readiness logic.
