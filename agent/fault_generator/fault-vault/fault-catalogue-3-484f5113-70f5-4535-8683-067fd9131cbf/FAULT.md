# Fault: Catalogue Service MongoDB Host Misconfiguration

## Description
The `MONGO_URL` environment variable for the `catalogue` deployment in `k8s/robot-shop-eks.yaml` was changed from `mongodb://mongodb:27017/catalogue` to `mongodb://nonexistent-mongodb:27017/catalogue`.

## Symptom
- The `catalogue` service will fail to start or will continuously crash and restart.
- Logs for the `catalogue` pod will show connection errors to MongoDB.
- The Robot Shop frontend will not be able to display product listings, as the catalogue service will be unreachable or unhealthy.
- Health checks for the `catalogue` service will fail.

## Root Cause
The `catalogue` service is configured to connect to a MongoDB instance at `nonexistent-mongodb`, which is not a valid or accessible hostname within the Kubernetes cluster. This prevents the service from establishing a connection to its required database, leading to application failure.

## Fix
Revert the `MONGO_URL` environment variable in the `catalogue` deployment to the correct MongoDB service hostname:
```yaml
        env:
        - name: MONGO_URL
          value: "mongodb://mongodb:27017/catalogue"