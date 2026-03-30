# Shipping Service Target Port Misconfiguration

## Description
The `targetPort` in the Kubernetes Service manifest for the shipping service (`k8s/manifests/shipping.yaml`) was changed from `8080` to `80`.

## Symptom
The shipping service becomes unreachable from other services within the cluster. Requests to the shipping service will fail with connection refused or timeout errors, as the Service is routing traffic to port 80 on the pods, but the application is listening on port 8080.

## Root cause
The Kubernetes Service acts as a load balancer for the pods. The `targetPort` specifies the port on the pod that the Service should forward traffic to. Since the shipping application (a Spring Boot app) is configured to listen on port 8080, routing traffic to port 80 results in failed connections because no process is listening on that port within the container.

## Fix
Revert the `targetPort` in `k8s/manifests/shipping.yaml` back to `8080`.

```yaml
spec:
  ports:
  - name: http
    port: 8080
    targetPort: 8080