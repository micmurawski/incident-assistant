# Incident: Redis Crashes and Session Failures

## Description
The Redis pod repeatedly crashes and restarts. Pod status shows OOMKilled. The user service cannot connect to Redis for session management. Features that rely on Redis (caching, sessions) fail. User sessions may be lost or cannot be created.