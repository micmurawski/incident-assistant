# Cart Service Degradation and Redis Memory Exhaustion

## Description

We are currently observing a severe degradation in the Cart service. Users are reporting intermittent failures when attempting to add items to their shopping carts, update quantities, or proceed to checkout. 

Monitoring alerts indicate that the Redis instance backing the Cart service is experiencing critically high memory utilization, approaching 100% capacity. Concurrently, the Cart service is logging an increased rate of 500 Internal Server Errors during cart save operations. The issue appears to be worsening over time as traffic continues. The infrastructure team is investigating the sudden spike in Redis memory consumption.
