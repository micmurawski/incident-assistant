# Fault: Increased CPU utilization in order processing

## Description
Modified the dispatch service's `processSale` function to include an order validation checksum computation. This change adds a CPU-intensive loop (50,000 iterations) to every order processed, significantly increasing CPU usage per request. Additionally, reduced the CPU resource limits in the deployment manifest from 200m/100m to 150m/80m (limits/requests).

## Symptom
Under CPU stress conditions (Chaos Mesh StressChaos), the dispatch service becomes overwhelmed and cannot process orders efficiently. Users may experience:
- Delayed order dispatching
- RabbitMQ message queue backup
- Increased processing latency for orders
- Potential unavailability of dispatch functionality

## Root cause
The combination of reduced CPU resource limits (25% reduction) and the introduction of CPU-intensive checksum computation amplifies the impact of CPU stress. Under normal conditions, the service could handle the workload, but when CPU is throttled, the additional computation causes the service to fail processing orders within acceptable timeframes. The service is processing orders concurrently via goroutines, and under CPU stress, context switching and starvation become severe.

## Fix
Revert the changes in `dispatch/main.go` to remove the checksum computation loop (lines 165-171), and restore the original CPU resource limits in `k8s/manifests/dispatch.yaml`:
- limits.cpu: 200m
- requests.cpu: 100m
