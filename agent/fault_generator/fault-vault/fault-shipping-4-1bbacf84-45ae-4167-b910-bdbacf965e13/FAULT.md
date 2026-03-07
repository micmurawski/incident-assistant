# Unbounded In-Memory Cache Growth in City Match Endpoint

## Description

Added an unbounded `ConcurrentHashMap` to cache the results of the `/match/{code}/{text}` endpoint in `Controller.java`. The cache stores the list of cities returned for each unique combination of country code and search text.

## Symptom

- The shipping service's memory usage will grow continuously over time.
- Users may experience increasingly slow response times from the shipping service.
- Eventually, the service will crash with an `OutOfMemoryError` (OOM) and restart, causing intermittent failures during the checkout process.
- Monitoring will show a continuous upward trend in heap usage that does not recover after garbage collection.

## Root Cause

The `matchCache` map stores the results of city matches but has no eviction policy or size limit. Since the `text` parameter can be any string of 3 or more characters, the number of possible cache keys is virtually infinite. As users search for different cities, the cache grows indefinitely, leading to unbounded memory growth and eventual resource exhaustion.

## Fix

Remove the `matchCache` entirely and rely on the database query, or replace it with a properly configured cache that has a maximum size and eviction policy (e.g., using Spring Cache, Caffeine, or Guava Cache).

To revert the change, remove the `matchCache` field and the caching logic from the `match` method in `Controller.java`:

```java
    @GetMapping("/match/{code}/{text}")
    public List<City> match(@PathVariable String code, @PathVariable String text) {
        logger.info("match code {} text {}", code, text);

        if (text.length() < 3) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        List<City> cities = cityrepo.match(code, text);
        /*
         * This is a dirty hack to limit the result size
         * I'm sure there is a more spring boot way to do this
         * TODO - neater
         */
        if (cities.size() > 10) {
            cities = cities.subList(0, 9);
        }

        return cities;
    }