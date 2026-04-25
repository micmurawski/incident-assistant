# Fault: Catalogue Connection-Storm and Probe-Restart Loop When Mongo Is Unreachable

## Description

Two things coincide in this incident:

1. **Application and manifest change.** A recent commit to the catalogue service introduced fragile behaviour on top of an otherwise healthy MongoDB client loop:
   - `catalogue/server.js` now declares `connectionPool` and `syncTimer`, plus two new functions:
     - `maintainPool()` — while `mongoConnected === false`, fires **three concurrent `mongoConnect()` calls** (no backoff, no dedup).
     - `startDataSync()` — runs `setInterval(..., 5000)`: on every tick, either runs a `collection.find({}).limit(1)` probe, or (if not connected) calls `maintainPool()`. On any error from the probe it sets `mongoConnected = false` and recursively calls `mongoLoop()`.
   - `startDataSync()` is invoked at startup alongside `mongoLoop()`.
   - `k8s/manifests/catalogue.yaml` now defines **both** a `livenessProbe` and a `readinessProbe` hitting `/health`, both with `failureThreshold: 1` (and short `periodSeconds` / `timeoutSeconds`). Previously only a readiness probe with `failureThreshold: 10` existed.
   - The Service selector was also cleaned up to rely on `app: catalogue` alone.

2. **A `NetworkChaos partition`** between the `catalogue` pod and the `mongo` pod, in both directions, for 60 minutes.

## Symptom

- Catalogue pod enters `CrashLoopBackOff` or flaps between `Running` and `NotReady` within roughly one probe interval after the partition begins.
- Pod restart count climbs steadily throughout the incident window.
- Catalogue logs show a burst of `MongoNetworkError` entries every few seconds, with multiple overlapping connection attempts per burst ("pool maintenance error" / "sync error" / "MongoDB connected" sometimes interleaved as the pod briefly thinks it is recovering).
- CPU usage on the catalogue pod is elevated despite no extra incoming traffic.
- From the web / cart side, the catalogue service is intermittently unavailable — sometimes 5xx, sometimes connection refused (depending on whether the pod is currently being terminated by the kubelet).

## Root Cause

The primary application-level bug is the interaction between `maintainPool()` + `startDataSync()` + the tightened probes:

- When Mongo becomes unreachable, `mongoConnected` flips to `false` on the next query error.
- `startDataSync()` then calls `maintainPool()` every 5 seconds, which fans out **3 concurrent** connection attempts to the Mongo Service.
- Each failed sync also recursively re-enters `mongoLoop()`, stacking yet another reconnect chain on top of the ones that `maintainPool()` is already launching.
- Meanwhile, `/health` returns `{ mongo: false }`, which the liveness probe immediately interprets as a liveness failure because `failureThreshold: 1`. The kubelet kills the pod. On restart the entire storm begins again.

This is a classic **thundering-herd + premature-liveness** anti-pattern: instead of absorbing the dependency outage, the service amplifies load against the dependency (making recovery harder) and restarts itself every few seconds (losing whatever warm state it had).

The `NetworkChaos partition` between `catalogue` and `mongo` is the environmental condition that makes `mongoConnected` flip to `false` in the first place. Without the partition the patch is dormant; without the patch the partition would have produced a tidier failure mode (a single background retry loop, no restarts, a `503`-style response at the edge, and full auto-recovery once Mongo is reachable again).

## Fix

1. **Remove the chaos condition** so the catalogue pod can reach Mongo again (`kubectl delete networkchaos -n application chaos-network-partition-application`). The pod will stop crash-looping within a couple of probe intervals.
2. **Revert the fragile bits of the patch:**
   - Delete `maintainPool()`, `startDataSync()`, `connectionPool`, `syncTimer`, and the `startDataSync();` invocation. Keep the original `mongoLoop()`-only reconnect path (single attempt with a 2s backoff).
   - Raise `livenessProbe.failureThreshold` back to something tolerant (10+), or remove the liveness probe entirely and keep only readiness. A service that is temporarily unable to reach its database is not *unhealthy* — it is *not-ready*, which is what readiness is for.
   - Keep the Service selector cleanup (`app: catalogue`) — that part is fine.
3. **Defensive follow-up**: wrap Mongo calls in a circuit breaker with jittered exponential backoff and surface a 503 with `Retry-After` when the breaker is open, instead of letting every failed request start yet another reconnect.
