# Fault: User Service Connection Storm Against Mongo and Redis

## Description

A recent commit to `user/server.js` made the user service's dependency-connect logic much more aggressive in two places:

1. **MongoDB reconnect loop.** The `setTimeout(mongoLoop, 2000)` on failure was replaced with `setTimeout(mongoLoop, 100)`. The service now attempts to re-establish its Mongo connection roughly **10 times per second** when Mongo is unreachable — ~600 attempts per minute, per user pod.

2. **Redis client configuration.** A custom `retry_strategy` was added to `redis.createClient(...)` with:
   - `connect_timeout: 500`
   - `max_attempts: 20`
   - a schedule of `Math.min(options.attempt * 50, 2000)` (ramps quickly, no jitter)
   - early-return rules on `ECONNREFUSED` and on total retry time
   - and, critically, a `redisClient.on('error', ...)` handler that calls `redisClient.connect().catch(() => {})` **inside the error handler itself** — meaning every error triggers an immediate new connect attempt, which in turn raises another error, which triggers another connect attempt.

A `NetworkChaos partition` experiment concurrently isolates the `user` pod from both `mongo` and `redis` (target `app In [mongo, redis]`) in both directions, for 60 minutes.

## Symptom

- User service endpoints (`/uniqueid`, `/login`, `/register`, `/history/:id`) fail with 500 or hang on the client side.
- User pod CPU is pinned near its limit, dominated by the Node.js event loop churning through reconnect bookkeeping.
- User pod memory trends upward (many orphaned error/socket objects) and may eventually OOM.
- User pod logs are a near-continuous stream of `MongoDB ERROR ... ECONNREFUSED` and `Redis ERROR ... ECONNREFUSED` lines.
- Upstream services that call user (web login, cart anonymous-ID generation) see elevated latency and 5xx rates.

## Root Cause

The primary bug is the **tight, un-backoff-ed retry loops** introduced by the patch. Under healthy conditions they are invisible because connections succeed on the first attempt. As soon as a dependency becomes unreachable, three compounding effects kick in:

- The 100ms Mongo reconnect schedule issues ~10 connect attempts per second. Each attempt allocates a new Mongo client state machine; with no backoff and no ceiling, they pile up.
- The custom Redis `retry_strategy` schedules its own attempt cadence (50ms, 100ms, 150ms, ...).
- The Redis `error` handler independently calls `redisClient.connect().catch(() => {})` on every error. Because every failed attempt emits an `error` event, this creates a self-feeding loop on top of whatever `retry_strategy` is already doing — in effect a busy-loop reconnect.

Together these three loops saturate the event loop of the user pod. CPU spikes, request handling starves, and real user-facing requests start timing out or erroring. The service cannot make forward progress even on traffic that does not require Mongo or Redis, because the event loop has no headroom.

The `NetworkChaos partition` between `user` and `{mongo, redis}` is the environmental trigger that makes both dependencies unreachable simultaneously. It is not the root cause: with the pre-patch retry logic (2000ms Mongo backoff, default `node_redis` retry, passive error handler) the same partition would have produced a calm "user service degraded, recovers automatically when the partition heals" failure mode. The patch turns a recoverable outage into a resource-exhaustion incident that often requires a pod restart.

## Fix

1. **Remove the chaos condition** to restore user ↔ mongo and user ↔ redis connectivity (`kubectl delete networkchaos -n application chaos-network-partition-application`).
2. **Revert the retry-related additions in `user/server.js`:**
   - Restore `setTimeout(mongoLoop, 2000)` (the original 2-second reconnect interval).
   - Remove the custom `retry_strategy`, `connect_timeout`, and `max_attempts` options from `redis.createClient(...)`. Use the defaults.
   - Remove the `redisClient.connect().catch(() => {})` call inside the `error` handler. `node_redis` manages reconnection itself; calling `connect()` from inside `error` causes the busy-loop described above.
3. **Defensive follow-up**: put a circuit breaker in front of Mongo and Redis calls, and return a degraded response (e.g. 503 with `Retry-After`) when the breaker is open, so a dependency outage cannot saturate the service's event loop.
