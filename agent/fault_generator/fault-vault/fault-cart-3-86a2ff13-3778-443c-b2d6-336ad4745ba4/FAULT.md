# Fault: Cart Service Selector Mismatch

## Description
The `selector` for the `cart` Service in `k8s/robot-shop-eks.yaml` has been misconfigured. It was changed from `app: cart` to `app: cart-backend`.

## Symptom
The cart service will have no endpoints, meaning that other services (like the web frontend) will be unable to communicate with the cart pods. Users will experience failures when attempting to add items to the cart, view cart contents, or perform any cart-related operations. The web interface might show errors or fail to load cart data.

## Root cause
The `cart` Service uses a selector to identify which pods it should route traffic to. Because the selector was changed to `app: cart-backend`, it no longer matches the labels on the `cart` Deployment pods (`app: cart`). As a result, the Service has no endpoints and cannot route any incoming requests to the actual application pods.

## Fix
Revert the `selector` in the `cart` Service to match the labels of the `cart` Deployment pods.

```yaml
spec:
  selector:
    app: cart