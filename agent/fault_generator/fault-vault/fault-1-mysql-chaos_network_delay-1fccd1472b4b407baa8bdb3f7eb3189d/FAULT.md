# Fault: Reduced fault tolerance in MySQL-dependent services

## Description
Modified the retry configuration and connection timeouts in both shipping and ratings services to reduce fault tolerance against MySQL network issues.

### Changes Made:

1. **Shipping Service (RetryableDataSource.java)**
   - Changed `@Retryable(maxAttempts = 10, ...)` to `@Retryable(maxAttempts = 1, ...)`
   - This reduces the number of retry attempts from 10 to just 1, making the service fail faster instead of retrying through transient failures

2. **Shipping Service (JpaConfig.java)**
   - Added `connectTimeout=1000` to the JDBC connection string
   - This sets a 1-second timeout for establishing connections

3. **Ratings Service (Database.php)**
   - Added `PDO::MYSQL_ATTR_CONNECT_TIMEOUT => 1` to PDO connection options
   - This sets a 1-second connection timeout for PHP MySQL connections

## Symptom
- Shipping service endpoints (`/count`, `/codes`, `/cities/{code}`, `/match/{code}/{text}`, `/calc/{id}`, `/confirm/{id}`) will fail with connection errors
- Ratings service endpoints (`/api/rate/{sku}/{score}`, `/api/fetch/{sku}`) will fail with connection timeout errors
- Both services will experience 100% failure rate when MySQL has any network latency issues

## Root Cause
The Chaos Mesh network delay experiment adds 500ms latency to all traffic to/from MySQL. While the original code had retry logic (10 attempts with exponential backoff) to handle transient network issues, the modified code:
- Only attempts a single connection (reduced from 10)
- Has very short timeouts (1 second)
- Combined with 500ms network delay, these changes make the services fail almost immediately

## Fix
1. Revert the retry attempts in `RetryableDataSource.java` back to `maxAttempts = 10`
2. Remove or increase the `connectTimeout=1000` parameter in `JpaConfig.java` 
3. Remove or increase the `PDO::MYSQL_ATTR_CONNECT_TIMEOUT` value in `Database.php`
