# Database Sleep in Ratings Service

## Description
Added a `SELECT SLEEP(1)` query execution before preparing the main query in the `ratingBySku` method of `ratings/html/src/Service/RatingsService.php`.

## Symptom
- The ratings service will experience a significant increase in latency.
- Fetching ratings for a SKU will take at least 2 seconds (since `ratingBySku` is called twice in the `get` endpoint).
- Under load, this will cause a backlog of requests, potentially exhausting PHP-FPM workers and database connections.
- Users will experience slow page loads when viewing products.

## Root Cause
The `SELECT SLEEP(1)` query forces the database to pause execution for 1 second before returning. Because this is in the hot path for fetching ratings, every request to get a rating is delayed. This ties up both the PHP worker process and the database connection for the duration of the sleep, leading to resource exhaustion under concurrent load.

## Fix
Remove the `$this->connection->exec("SELECT SLEEP(1)");` line from the `ratingBySku` method in `ratings/html/src/Service/RatingsService.php`:

```php
    public function ratingBySku(string $sku): array
    {
        $stmt = $this->connection->prepare(self::QUERY_RATINGS_BY_SKU);
        if (false === $stmt->execute([$sku])) {
            $this->logger->error('failed to query data');
            throw new \Exception('Failed to query data', 500);
        }
        // ...
    }