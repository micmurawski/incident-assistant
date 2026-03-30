# MySQL Connection Limit Exhaustion

## Title
MySQL max_connections limit set too low

## Description
The `mysql/Dockerfile` was modified to create a custom configuration file (`/etc/mysql/conf.d/limits.cnf`) that sets the `max_connections` parameter to a very low value (12).

## Symptom
Services that depend on MySQL (like `shipping` and `ratings`) will start failing to connect to the database under load. Users will experience errors when trying to calculate shipping costs or view/submit ratings. Monitoring will show an increase in HTTP 500 errors from these services and database connection errors in their logs (e.g., "Too many connections").

## Root cause
The `max_connections` setting in MySQL dictates the maximum number of concurrent client connections. By setting it to 12, the database quickly runs out of available connections when multiple services or instances try to connect simultaneously, especially under load. This leads to connection exhaustion, preventing new requests from being processed.

## Fix
Remove the custom configuration file creation from the `mysql/Dockerfile` or increase the `max_connections` value to a reasonable number for the expected load.

```dockerfile
# Remove these lines from mysql/Dockerfile
RUN echo "[mysqld]" > /etc/mysql/conf.d/limits.cnf && \
    echo "max_connections = 12" >> /etc/mysql/conf.d/limits.cnf