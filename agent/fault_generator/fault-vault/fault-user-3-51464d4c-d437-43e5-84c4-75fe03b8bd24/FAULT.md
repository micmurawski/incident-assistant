# Fault Documentation

## Title
User Service MongoDB Connection Failure

## Description
The `MONGO_URL` environment variable in the user service Deployment has been changed from `"mongodb://mongodb:27017/users"` to `"mongodb://mongodb:27018/users"`. This change is located in the Kubernetes manifest file `k8s/robot-shop-eks.yaml` in the user Deployment specification.

## Symptom
The user service will fail to connect to MongoDB, resulting in connection errors. Users attempting to access user-related functionality (such as login, registration, or fetching user details) will experience failures. The application logs will show connection refused errors when trying to connect to the MongoDB host on port 27018.

## Root Cause
The environment variable `MONGO_URL` points to port `27018` which is incorrect. The correct port for MongoDB is `27017`. Since MongoDB is not listening on port 27018, the connection will fail, preventing the user service from establishing communication with the MongoDB backing store.

## Fix
Revert the `MONGO_URL` environment variable value in the user service Deployment from `"mongodb://mongodb:27018/users"` back to `"mongodb://mongodb:27017/users"`. The correct configuration should be:

```yaml
- name: MONGO_URL
  value: "mongodb://mongodb:27017/users"
```

This can be applied by updating the Kubernetes manifest and reapplying it to the cluster, or by directly patching the Deployment using kubectl.
