# Ratings Service Selector Mismatch

## Description
The Kubernetes Service selector for the ratings service was modified to have a typo in the `app` label (`app: rating` instead of `app: ratings`).

## Symptom
The ratings service is unreachable. Users cannot see or submit ratings. The service returns 503 Service Unavailable or connection refused errors.

## Root cause
The Kubernetes Service uses selectors to route traffic to the correct pods. Because the selector `app: rating` does not match the pod's label `app: ratings`, the Service has no endpoints and cannot route traffic to the ratings pods.

## Fix
Correct the selector in `k8s/manifests/ratings.yaml` to match the pod's labels:
```yaml
  selector:
    service: ratings
    app: ratings