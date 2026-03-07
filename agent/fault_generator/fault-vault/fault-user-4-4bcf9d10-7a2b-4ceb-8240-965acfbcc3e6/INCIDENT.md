# INCIDENT.md

## Title
User Service Crashing and Redis Connection Spikes

## Description
We are observing intermittent crashes in the user service, accompanied by alerts for high memory usage and file descriptor exhaustion. Additionally, the Redis monitoring dashboard shows a massive, continuous spike in active connections. Users are reporting that they cannot check out as anonymous users, and the site is generally unstable.
