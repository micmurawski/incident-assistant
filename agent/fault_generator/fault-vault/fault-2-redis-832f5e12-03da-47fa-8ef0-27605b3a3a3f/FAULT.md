# Title: Redis configured with extremely low memory limit and noeviction policy

# Description
Modified `k8s/manifests/redis.yaml` to add `args: ["redis-server", "--maxmemory", "2mb", "--maxmemory-policy", "noeviction"]` to the redis container.

# Symptom
Users will experience failures when trying to add items to their cart or perform other actions that require writing to Redis. The cart service will likely log errors about Redis being out of memory (OOM command not allowed).

# Root cause
Redis is configured with a maximum memory limit of 2MB and a policy of `noeviction`. Once the 2MB limit is reached, Redis will refuse any new write operations, causing dependent services to fail.

# Fix
Remove the `args` line from `k8s/manifests/redis.yaml` or increase the `maxmemory` limit to a reasonable value and change the policy to something like `allkeys-lru`.
