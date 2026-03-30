# Fault: MySQL Ratings Update Delay

## Description
A trigger was added to the `ratings` table in the MySQL database initialization script (`mysql/scripts/20-ratings.sql`). This trigger executes `DO SLEEP(1.5)` before every update operation on the `ratings` table.

## Symptom
Users will experience a noticeable delay (at least 1.5 seconds) when submitting a new rating for a product. Monitoring systems will show increased latency for the `POST /api/ratings` endpoint in the ratings service, and potentially increased database connection times or connection pool exhaustion if many ratings are submitted concurrently.

## Root cause
The `before_rating_update` trigger intentionally pauses execution for 1.5 seconds for every row updated in the `ratings` table. This directly impacts the performance of the `updateRatingForSKU` function in the ratings service, which executes an `UPDATE` query.

## Fix
Remove the `before_rating_update` trigger from `mysql/scripts/20-ratings.sql` and drop the trigger from the live database if it has already been applied.

```sql
DROP TRIGGER IF EXISTS before_rating_update;