Title: MongoDB Connection Leak

Description:
A MongoDB connection leak was introduced in `catalogue/server.js`. The `mongoConnect` function now stores every new MongoDB client connection in a global array `activeConnections` without ever closing them.

Symptom:
Over time, the catalogue service will consume an increasing amount of memory due to the accumulation of open MongoDB connections. This will eventually lead to resource exhaustion, slow response times, and potential service crashes. Monitoring tools might show a steady increase in memory usage for the catalogue service pod.

Root cause:
The `mongoConnect` function, which is responsible for establishing connections to MongoDB, was modified to store each new `client` object in the `activeConnections` array. Since these connections are never explicitly closed or removed from the array, they will accumulate in memory, leading to a leak.

Fix:
Remove the line `activeConnections.push(client);` from the `mongoConnect` function in `catalogue/server.js`. Ensure that MongoDB connections are properly closed when they are no longer needed, or that a connection pool is used and managed correctly.