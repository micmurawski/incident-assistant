# Fault: Redis Memory Limit Too Low

**Title**: Redis container memory limit set too low causing OOMKilled

**Description**: In the Kubernetes manifest `k8s/manifests/redis.yaml`, the Redis Deployment has an excessively low memory limit of 32Mi, down from the original 256Mi. The memory request remains at 128Mi, but the limit is now insufficient for Redis to function properly.

**Symptom**:
- Redis pod repeatedly crashes and restarts
- Pod status shows OOMKilled (Out of Memory) in events
- User service fails to connect to Redis for session management
- Application features relying on Redis (caching, session store) fail
- User login sessions may be lost or unable to be created

**Root cause**: The Redis memory limit was reduced to 32Mi in the Deployment resource. Redis requires more memory to handle its internal data structures, persistence, and client connections. When Redis exceeds the 32Mi limit, the kernel OOM killer terminates the container, causing repeated crashes.

**Fix**: Increase the Redis memory limit back to an appropriate value in the Deployment:

```yaml
resources:
  limits:
    memory: "256Mi"  # Change from 32Mi back to 256Mi
```
