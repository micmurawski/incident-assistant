# Misconfigured CATALOGUE_HOST environment variable in cart deployment

## Description
The `CATALOGUE_HOST` environment variable in the `cart` deployment manifest (`k8s/manifests/cart.yaml`) was explicitly set to `catalog` instead of the correct service name `catalogue`.

## Symptom
Users will not be able to add items to their cart. The cart service will fail to fetch product details from the catalogue service, resulting in errors when trying to add items. Monitoring will show increased error rates for the cart service and failed requests to the catalogue service (or rather, failed DNS resolution for `catalog`).

## Root cause
The cart service relies on the `CATALOGUE_HOST` environment variable to locate the catalogue service. By default, it uses `catalogue`, which matches the Kubernetes service name. Setting it to `catalog` causes the cart service to attempt to connect to a non-existent host, leading to connection failures when it tries to retrieve product information during the "add to cart" operation.

## Fix
Remove the `CATALOGUE_HOST` environment variable from the `cart` deployment manifest, or correct its value to `catalogue`.

```yaml
        env:
        - name: CATALOGUE_HOST
          value: "catalogue"
```
