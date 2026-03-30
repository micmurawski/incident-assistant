# Title: Incorrect MongoDB URL in User Service Deployment

# Description:
Added an incorrect `MONGO_URL` environment variable to the `user` deployment in `k8s/manifests/user.yaml`. The hostname is set to `mongo` instead of the correct `mongodb`.

# Symptom:
The user service will fail to connect to MongoDB. Users will not be able to log in, register, or view their history. The user service logs will show connection errors to MongoDB.

# Root cause:
The `user` service relies on MongoDB for storing user data. The incorrect `MONGO_URL` environment variable overrides the default connection string, causing the service to attempt to connect to a non-existent host (`mongo` instead of `mongodb`).

# Fix:
Remove the incorrect `MONGO_URL` environment variable from `k8s/manifests/user.yaml` or correct the hostname to `mongodb`.
