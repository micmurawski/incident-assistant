# Fault: Cart Service Image Name Misconfiguration

## Description
The `image` for the `cart` service Deployment in `k8s/robot-shop-eks.yaml` has been misconfigured. It was changed from `${REPO}/robot-shop-cart:${TAG}` to `${REPO}/robot-shop-cart-nonexistent:${TAG}`.

## Symptom
The cart service pods will fail to start because Kubernetes will be unable to pull the specified image. The pods will remain in a `ImagePullBackOff` or `ErrImagePull` state, and the cart service will be completely unavailable. Users will experience failures when attempting to add items to the cart, view cart contents, or perform any cart-related operations.

## Root cause
The `cart` service Deployment is configured to use an image that does not exist in the specified image repository. Kubernetes attempts to pull this non-existent image, fails, and consequently, the pod cannot start.

## Fix
Revert the `image` field in the `cart` Deployment to the correct image name:
```yaml
image: ${REPO}/robot-shop-cart:${TAG}