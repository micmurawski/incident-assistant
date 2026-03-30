# Catalogue Service Database Connection Misconfiguration

## Description
The `MONGO_URL` environment variable in the `catalogue` Kubernetes deployment manifest (`k8s/manifests/catalogue.yaml`) has been misconfigured to point to an incorrect port (`27018` instead of the default `27017`).

## Symptom
The catalogue service will fail to connect to the MongoDB database. Users will not be able to view products, categories, or search for items. The catalogue service will continuously log connection errors and retry connecting to the database. The `/health` endpoint will report `mongo: false`.

## Root cause
The `catalogue` service relies on the `MONGO_URL` environment variable to connect to its backing MongoDB instance. By setting the port to `27018`, the connection attempts will fail because the MongoDB service is listening on port `27017`.

## Fix
Remove the misconfigured `MONGO_URL` environment variable from `k8s/manifests/catalogue.yaml` or correct it to point to the correct port (`27017`).
