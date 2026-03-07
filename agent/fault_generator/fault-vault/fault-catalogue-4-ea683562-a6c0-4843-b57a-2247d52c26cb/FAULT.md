# Fault: Unbounded In-Memory Product Cache

## Description
An unbounded in-memory cache was introduced in the cart service (`cart/server.js`) to cache product lookups from the catalogue service. A global `productCache` object stores product data indefinitely without any eviction policy.

## Changes Made
- Added `var productCache = {}` at line 30 of `cart/server.js`
- Modified the `getProduct()` function to check the cache before making HTTP requests and to store fetched products in the cache

## Symptom
- Gradually increasing memory usage in the cart service container
- Eventually causes the cart service to crash due to out-of-memory (OOM) errors
- The `/health` endpoint may become unresponsive as memory pressure increases

## Root Cause
The `productCache` object grows unbounded because:
1. Every unique SKU added to carts is stored in the cache
2. There is no TTL (time-to-live) for cached entries
3. There is no maximum cache size or eviction policy
4. As the catalogue grows or more diverse products are added to carts, memory usage increases indefinitely

## Fix
Remove the caching logic or implement a proper caching strategy with eviction:
- Option 1: Remove the `productCache` and always fetch from the catalogue service
- Option 2: Implement an LRU (Least Recently Used) cache with a maximum size
- Option 3: Add TTL to cache entries and periodically clean up expired entries

Example fix (remove caching):
```javascript
function getProduct(sku) {
    return new Promise((resolve, reject) => {
        request('http://' + catalogueHost + ':8080/product/' + sku, (err, res, body) => {
            if(err) {
                reject(err);
            } else if(res.statusCode != 200) {
                resolve(null);
            } else {
                resolve(JSON.parse(body));
            }
        });
    });
}
```
