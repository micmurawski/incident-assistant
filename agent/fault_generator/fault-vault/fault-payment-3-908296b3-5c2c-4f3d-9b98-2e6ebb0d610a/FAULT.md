# Fault: Payment Service Target Port Mismatch

## Description
The Kubernetes Service manifest for the payment service has an incorrect `targetPort` configuration. In the `k8s/robot-shop-eks.yaml` file, the payment Service defines `targetPort: 9090`, but the payment container in the Deployment listens on port 8080.

## Symptom
When attempting to access the payment service through the Kubernetes Service, connections will fail. The Service will not be able to route traffic to the backend pods because the target port does not match the container's listening port. External clients trying to process payments will receive connection errors or timeouts.

## Root Cause
The payment Service specifies `targetPort: 9090` while the payment container is configured to listen on port 8080 (as defined in the Deployment's containerPort). This port mismatch prevents the Service from forwarding traffic to the backend pods.

## Fix
Update the payment Service manifest to use the correct target port:

```yaml
ports:
- port: 8080
  targetPort: 8080
```

Change `targetPort: 9090` to `targetPort: 8080` in the payment Service definition within `k8s/robot-shop-eks.yaml`.
