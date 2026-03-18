# Fault: Memory accumulation in order processing

## Description
Modified the dispatch service to add an order data caching mechanism. Each processed order now stores a duplicated version of the order data (2x the original size) in an in-memory cache (`orderCache`) that is never cleaned up. This creates a memory leak pattern where each order increases memory usage indefinitely. Additionally, reduced memory limits in the deployment manifest from 100Mi/50Mi to 80Mi/40Mi (limits/requests).

## Symptom
Under CPU stress conditions (Chaos Mesh StressChaos), the dispatch service becomes overwhelmed and cannot process orders efficiently. Users may experience:
- Delayed order dispatching
- RabbitMQ message queue backup
- Increased memory consumption leading to OOM kills
- Potential unavailability of dispatch functionality
- Service crashes due to memory exhaustion

## Root cause
The combination of reduced memory resource limits and the introduction of unbounded memory accumulation amplifies the impact of CPU stress. When CPU is throttled, the garbage collector cannot efficiently reclaim memory, and the continuous accumulation of order data in the cache eventually exhausts available memory. Under normal CPU conditions, the service might survive longer, but the memory footprint grows continuously. The order data duplication (2x size) accelerates memory consumption with each processed order.

## Fix
Revert the changes in `dispatch/main.go` to remove the order cache storage logic (lines 157-162), and restore the original memory resource limits in `k8s/manifests/dispatch.yaml`:
- limits.memory: 100Mi
- requests.memory: 50Mi
