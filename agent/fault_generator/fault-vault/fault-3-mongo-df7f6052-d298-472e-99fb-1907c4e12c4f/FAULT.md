# Title: MongoDB Readiness Probe Port Misconfiguration

# Description
The readiness probe port for the MongoDB deployment in `k8s/manifests/mongodb.yaml` was changed from `27017` to `27018`.

# Symptom
The MongoDB pod will start but will never reach the `Ready` state. As a result, the `mongodb` Kubernetes Service will not have any endpoints, and no traffic will be routed to the MongoDB pod. Services that depend on MongoDB (such as `catalogue` and `user`) will fail to connect to the database, leading to application-wide errors, timeouts, and inability to browse products or log in.

# Root cause
The readiness probe is configured to check a TCP socket on port `27018`, but MongoDB is listening on port `27017`. The probe will continuously fail, preventing the pod from being marked as ready and added to the service endpoints.

# Fix
Revert the readiness probe port in `k8s/manifests/mongodb.yaml` back to `27017`.

```yaml
        readinessProbe:
          tcpSocket:
            port: 27017