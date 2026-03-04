Title: Simulated Database Latency in Ratings Service

Description:
A 500ms delay has been introduced in the `ratingBySku` method of the `RatingsService.php` file. This delay occurs after the database query fetches data, simulating a slow database operation or a resource-intensive task that holds the database connection.

File: `ratings/html/src/Service/RatingsService.php`
Line: 39 (after `$data = $stmt->fetch();`)
Change: Added `usleep(500000);`

Symptom:
Users will experience increased latency when requesting product ratings. Under heavy load, the ratings service may become unresponsive or return errors due to database connection exhaustion or timeouts. Monitoring tools will show increased response times for the ratings service and potentially a backlog of database connections.

Root cause:
The `usleep(500000);` call artificially pauses the execution for 500 milliseconds within the `ratingBySku` method. This delay occurs while a database connection is held open, preventing other requests from utilizing that connection. If multiple concurrent requests hit this code path, the database connection pool can quickly become exhausted, leading to degraded performance and service unavailability.

Fix:
Remove the `usleep(500000);` line from `ratings/html/src/Service/RatingsService.php` at line 39.