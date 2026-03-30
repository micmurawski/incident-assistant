# Fault: MongoDB Readiness Probe Misconfiguration

## Description
The readiness probe port for the MongoDB deployment in `k8s/manifests/mongodb.yaml` was changed from `27017` to `27018`.

## Symptom
The MongoDB pod will start but will never become "Ready" because the readiness probe will fail to connect to port 27018 (MongoDB is listening on 27017). As a result, the MongoDB service will not route traffic to the pod, causing services that depend on MongoDB (like `catalogue` and `user`) to fail to connect to the database. Users will likely see errors when trying to view products or log in.

## Root cause
The Kubernetes readiness probe is configured to check port 27018, but the MongoDB container is only listening on its default port, 27017. Since the probe fails, Kubernetes removes the pod from the service endpoints.

## Fix
Revert the readiness probe port in `k8s/manifests/mongodb.yaml` back to `27017`.

```yaml
        readinessProbe:
          tcpSocket:
            port: 27017