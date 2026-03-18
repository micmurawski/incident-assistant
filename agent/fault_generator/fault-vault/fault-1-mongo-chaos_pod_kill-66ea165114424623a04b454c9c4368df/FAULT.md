# Fault: Extended MongoDB Connection Retry Delay

## Description
The MongoDB connection retry delay in both the catalogue and user services has been increased from the default 2 seconds to 60 seconds. This was done by:

1. Modifying `catalogue/server.js` - Added `process.env.MONGO_RETRY_DELAY || 60000` in the mongoLoop function (line 155)
2. Modifying `user/server.js` - Added `process.env.MONGO_RETRY_DELAY || 60000` in the mongoLoop function (line 271)
3. Added `MONGO_RETRY_DELAY: "60000"` environment variable to both `k8s/manifests/catalogue.yaml` and `k8s/manifests/user.yaml`

The environment variable name appears to be a legitimate configuration option but defaults to 60 seconds instead of the original 2 seconds.

## Symptom
When MongoDB pods are terminated by the Chaos Mesh pod-kill experiment:
- The catalogue service will take up to 60 seconds between connection retry attempts
- The user service will take up to 60 seconds between connection retry attempts
- Both services will report "database not available" for extended periods
- Product listings, user authentication, registration, and order history will all be unavailable
- The application health checks will show mongo: false for much longer during the experiment

## Root Cause
The MongoDB reconnection retry delay was increased from 2 seconds to 60 seconds. When MongoDB is killed, the services wait a full minute before attempting to reconnect, significantly extending the recovery time and the impact of the chaos experiment.

## Fix
Set the `MONGO_RETRY_DELAY` environment variable to "2000" in the Kubernetes deployments, or remove the environment variable entirely to use a faster reconnect interval. The code in both `catalogue/server.js` and `user/server.js` will fall back to a reasonable default if this variable is not set.
