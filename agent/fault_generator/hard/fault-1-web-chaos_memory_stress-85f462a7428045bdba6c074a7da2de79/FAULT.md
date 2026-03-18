# Fault: Increased Memory Pressure on Web Service

## Description
The nginx configuration in the web service was modified to include upstream connection pooling with keepalive connections, larger buffer sizes, increased worker connections, and file caching. These changes were made to improve performance throughput but result in significantly higher memory consumption per worker process.

**Files Modified:**
- `web/default.conf.template` - Added upstream keepalive pools for all backend services and increased proxy buffer sizes
- `web/entrypoint.sh` - Added nginx performance tuning with more worker connections, larger header buffers, and file caching

## Symptom
When the memory stress chaos experiment is running, the web service experiences:
- Increased memory usage leading to OOM (Out of Memory) kills
- Intermittent 502/503/504 errors when proxying requests to backend services
- Slow response times or complete unavailability of the web interface
- Container restarts due to memory exhaustion

## Root Cause
The nginx configuration increases memory footprint through:
1. **Upstream keepalive pools**: Each backend maintains 32 persistent connections (6 backends × 32 = 192 connections)
2. **Larger buffers**: proxy_buffer_size 128k, proxy_buffers 8×256k = 2MB per connection
3. **Worker connections**: Increased from default 768 to 2048
4. **Header buffers**: 16k client headers and 4×32k large client headers
5. **File cache**: Caches up to 1000 open file descriptors

With only 100Mi container memory limit and 2 nginx workers, these settings cause rapid memory exhaustion under any load.

## Fix
Reduce the nginx memory footprint to match the container limits:

1. **In default.conf.template:**
   - Remove or reduce keepalive pool sizes (keepalive 8-16 instead of 32)
   - Reduce proxy buffer sizes (16k-32k instead of 128k-256k)
   
2. **In entrypoint.sh:**
   - Reduce worker_connections to 512-768
   - Reduce client_header_buffer_size to 4k
   - Reduce or disable open_file_cache

3. **In k8s/manifests/web.yaml:**
   - Increase memory limit to at least 256Mi to accommodate the original configuration
   - Or apply the nginx configuration fixes above
