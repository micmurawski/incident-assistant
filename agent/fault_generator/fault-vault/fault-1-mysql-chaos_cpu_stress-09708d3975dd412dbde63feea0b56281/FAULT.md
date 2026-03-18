# Fault: Database Connection Pool Exhaustion Under CPU Stress

## Description
Modified the shipping service to amplify the impact of MySQL CPU stress:

1. **Increased HikariCP connection pool size** in `shipping/src/main/resources/application.properties`:
   - Changed maximum-pool-size from default (10) to 50
   - Changed minimum-idle from default (10) to 15
   - Set connection-timeout to 10000ms

2. **Added background sync task** in `shipping/src/main/java/com/instana/robotshop/shipping/ShippingServiceApplication.java`:
   - Added `@EnableScheduling` annotation
   - Created `DataSyncTask` component that queries MySQL every 5 seconds

3. **Added app label** to `k8s/manifests/mysql.yaml`:
   - Added `app: mysql` label to the pod template to ensure the Chaos Mesh experiment can target the MySQL pod

## Symptom
- Shipping service experiences slow database queries and timeouts
- Checkout process becomes slow or fails
- Connection pool exhaustion errors in shipping service logs
- Users see delays or failures when trying to complete orders

## Root Cause
When MySQL is under CPU stress (as triggered by the Chaos Mesh StressChaos experiment), database queries become slow. The combination of:
1. Large connection pool (50 connections) maintaining persistent connections
2. Background task continuously querying the database
3. Multiple concurrent requests from the application

This causes connection pool exhaustion as all connections are blocked waiting for slow MySQL responses, while new requests keep coming in. The 10-second connection timeout gets hit frequently, causing request failures.

## Fix
To fix this issue:
1. Reduce the HikariCP connection pool size to default or lower values (e.g., maximum-pool-size: 10, minimum-idle: 5)
2. Remove or disable the scheduled background sync task
3. Reduce the connection-timeout to allow faster failure detection (e.g., 3000ms)
4. Consider implementing circuit breaker pattern for database calls
