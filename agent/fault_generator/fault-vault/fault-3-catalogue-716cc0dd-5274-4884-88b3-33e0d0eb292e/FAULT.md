# Catalogue Service MongoDB Port Misconfiguration

## Title
Catalogue service configured with incorrect MongoDB port

## Description
The `MONGO_URL` environment variable in the `k8s/manifests/catalogue.yaml` deployment manifest was explicitly set to use port `27018` instead of the default MongoDB port `27017`.

## Symptom
The catalogue service fails to connect to the MongoDB database. Users will see empty product lists or errors when trying to browse the shop. The catalogue service will return HTTP 500 errors for product and category requests, and its `/health` endpoint will show `mongo: false`. The catalogue service logs will show continuous MongoDB connection retry errors.

## Root cause
The catalogue service uses the `MONGO_URL` environment variable to connect to its database. By setting this variable to `mongodb://mongodb:27018/catalogue`, the service attempts to connect to port 27018, but the MongoDB service is listening on the standard port 27017. This causes the connection to fail, leaving the catalogue service without access to its data.

## Fix
Remove the incorrect `MONGO_URL` environment variable from `k8s/manifests/catalogue.yaml` to allow the service to use its default connection string (`mongodb://mongodb:27017/catalogue`), or correct the port in the environment variable to `27017`.