# Fault: Aggressive Connection Pool Maintenance Amplifies Network Partition

## Description

Modified the catalogue service to include connection pool maintenance and periodic data synchronization features. These were added to "ensure high availability" but they actually amplify the effects of network partition:

1. **In `catalogue/server.js`**:
   - Added `maintainPool()` function that creates 3 concurrent MongoDB connection attempts every 5 seconds when disconnected
   - Added `startDataSync()` function that runs a periodic sync every 5 seconds, triggering additional connection attempts and recursively calling `mongoLoop()` on any sync failure
   - Added `connectionPool` and `syncTimer` variables (declared but unused - creating unnecessary state)

2. **In `k8s/manifests/catalogue.yaml`**:
   - Added liveness and readiness probes with aggressive failure thresholds (failureThreshold: 1)
   - Added `app: catalogue` label to match the chaos experiment selector

## Symptom

When the network partition chaos experiment is running:
- The catalogue service experiences cascading failures
- Multiple concurrent connection attempts to MongoDB accumulate
- The data sync mechanism triggers on failures, creating a feedback loop
- Health checks start failing due to mongoConnected being false
- Kubernetes restarts the pod repeatedly due to low failureThreshold

## Root Cause

The combination of:
1. Network partition isolates catalogue pods from each other
2. The aggressive "pool maintenance" creates multiple concurrent connection attempts
3. The data sync on failure creates recursive reconnection attempts
4. With failureThreshold: 1 on both liveness and readiness probes, the pod gets restarted after just a few failed health checks

This creates a "thundering herd" problem where many connection attempts pile up during network issues, exhausting resources and causing the pod to be restarted before it can recover.

## Fix

1. Remove or disable the `maintainPool()` and `startDataSync()` functions
2. Increase the `failureThreshold` for liveness and readiness probes to allow more time for recovery
3. Consider using exponential backoff for connection retries instead of aggressive periodic attempts
4. Remove unused variables (`connectionPool`, `syncTimer`)
