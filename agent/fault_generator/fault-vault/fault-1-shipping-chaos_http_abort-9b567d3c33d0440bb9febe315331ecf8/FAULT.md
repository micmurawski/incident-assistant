# Fault: Shipping Service Failure Amplification Under HTTP 503 Injection

## Description
This scenario combines infrastructure and code-level degradation:

1. Chaos Mesh injects `HTTPChaos` for the shipping service, replacing matched HTTP responses with status `503` for 60 minutes.
2. `CartHelper` is modified to use much longer HTTP timeouts (60s connect, 60s connection request, 120s response) and explicit retry attempts (5 attempts with incremental sleep).
3. `RetryableDataSource` backoff is made more aggressive (`multiplier=3.5`, `maxDelay=60000` instead of `2.3/30000`).
4. A large `taskExecutor` bean (core 50 / max 100 / queue 200) is added, increasing concurrency pressure under sustained failures.

## Symptom
When 503 responses are injected, shipping cannot complete request flows reliably. The timeout/retry changes amplify impact, resulting in:
- Elevated error rates for shipping-related endpoints
- Slower checkout and order confirmation paths (including `/confirm`)
- Increased in-flight request buildup due to retries and long waits
- Higher pressure on dependent resources, including DB connection acquisition

Users experience failed or delayed checkout attempts and inconsistent order completion.

## Root Cause
The primary trigger is HTTP 503 response injection into shipping traffic. The code changes then amplify the blast radius by holding requests longer and retrying more aggressively, which increases contention and delays across the request path.

## Fix
1. Restore conservative HTTP client timeouts for `CartHelper` (for example, 5-10s range)
2. Limit or remove custom retry loop for shipping-to-cart calls
3. Revert DB retry backoff values to safer defaults
4. Remove or right-size the custom task executor unless explicitly required
5. Add resilience controls (circuit breaker / bulkhead / bounded retries)
