# Dispatch Service Memory Leak

## Description

The dispatch service is experiencing a memory leak. Over time, the memory usage of the service increases steadily until it crashes due to Out-Of-Memory (OOM) errors. This causes the service to restart frequently, leading to intermittent failures in processing orders.

## Symptoms

- Increasing memory usage over time
- Frequent service restarts due to OOM
- Intermittent failures in processing orders
- High latency in order processing during periods of high memory usage
