# Fault: Reduced retry resilience in MySQL-dependent services

## Description
Modified the retry configuration and connection settings for services that depend on MySQL:

1. **Shipping Service (`shipping/src/main/java/com/instana/robotshop/shipping/RetryableDataSource.java`)**: Changed retry configuration from `@Retryable(maxAttempts = 10, backoff = @Backoff(multiplier = 2.3, maxDelay = 30000))` to `@Retryable(maxAttempts = 2, backoff = @Backoff(multiplier = 1.0, maxDelay = 500))` for both `getConnection()` methods. This reduces the number of retry attempts from 10 to 2 and reduces the max delay from 30 seconds to 500ms.

2. **Shipping Service (`shipping/src/main/java/com/instana/robotshop/shipping/JpaConfig.java`)**: Changed JDBC URL parameter from `autoReconnect=true` to `autoReconnect=false`, disabling automatic reconnection when connections are lost.

3. **Ratings Service (`ratings/html/src/Database.php`)**: Added `PDO::MYSQL_ATTR_CONNECT_TIMEOUT => 1` to the PDO options, setting the connection timeout to 1 second instead of default.

4. **Ratings Service (`ratings/html/src/Service/HealthCheckService.php`)**: Modified health check to properly handle null PDO connection by returning false when prepare() fails.

## Symptom
When the MySQL pod becomes unavailable, both the shipping and ratings services will fail immediately without the benefit of extended retry logic. Users will see:
- 500 errors when trying to calculate shipping costs
- 500 errors when trying to view shipping data (codes, cities)
- Errors when trying to retrieve or update product ratings

The services will become unavailable much faster during MySQL outages.

## Root Cause
The retry configuration changes remove the resilience that would normally allow services to tolerate brief MySQL outages. The shipping service previously could retry for up to 30 seconds with exponential backoff (10 attempts), which would typically allow it to survive short MySQL interruptions. Now it only attempts 2 retries with a fixed 500ms delay. The disabled auto-reconnect and the 1-second connection timeout further reduce the ability to recover from MySQL unavailability.

## Fix
Restore the original configurations:

1. In `RetryableDataSource.java`, change back to:
   - `@Retryable(maxAttempts = 10, backoff = @Backoff(multiplier = 2.3, maxDelay = 30000))`

2. In `JpaConfig.java`, change JDBC URL parameter back to `autoReconnect=true`

3. In `Database.php`, remove `PDO::MYSQL_ATTR_CONNECT_TIMEOUT => 1` from the options array

4. In `HealthCheckService.php`, restore the original implementation
