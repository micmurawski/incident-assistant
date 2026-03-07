# Fault: Cart Service Catalogue Host Misconfiguration

## Description
The `CATALOGUE_HOST` environment variable for the `cart` service Deployment in `k8s/robot-shop-eks.yaml` has been misconfigured. It was added and set to "catalogue-wrong".

## Symptom
The cart service will fail to connect to the catalogue service, leading to errors when users try to add items to their cart. The service might appear to be running, but its core functionality will be broken, resulting in a degraded user experience. Logs for the cart service will show connection errors to the catalogue service.

## Root cause
The `cart` service relies on the catalogue service to verify product details when adding items to the cart. By setting the `CATALOGUE_HOST` environment variable to a non-existent hostname, the service is unable to establish a connection with the catalogue service, causing operations that depend on it to fail.

## Fix
Remove the `CATALOGUE_HOST` environment variable in the `cart` Deployment or set it to the correct catalogue service hostname, which is typically "catalogue".

```yaml
env:
- name: CATALOGUE_HOST
  value: "catalogue"