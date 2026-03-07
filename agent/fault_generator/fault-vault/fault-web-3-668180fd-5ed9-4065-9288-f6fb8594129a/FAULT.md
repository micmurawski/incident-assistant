# Fault: MySQL Service Target Port Mismatch

**Title**: MySQL Service targetPort mismatch causes connection failures

**Description**: In the Kubernetes manifest `k8s/robot-shop-eks.yaml`, the MySQL Service has an incorrect `targetPort` value. The Service exposes port 3306 and attempts to route to targetPort 3307, but the MySQL container only listens on port 3306. This is a port mismatch between the Service and the Deployment.

**Symptom**: 
- The shipping service and any other components that depend on MySQL will fail to connect to the database
- Connection errors will be observed in the shipping service logs
- The shipping functionality in the robot shop application will be broken
- Health checks may pass for MySQL pod but application connectivity will fail

**Root cause**: The MySQL Service specifies `targetPort: 3307` while the MySQL container in the Deployment is configured to listen on port `3306`. Kubernetes will attempt to forward traffic to port 3307 on the pod, which has no listener, resulting in connection refused errors.

**Fix**: Change the MySQL Service targetPort from 3307 back to 3306:

```yaml
ports:
- port: 3306
  targetPort: 3306  # Change from 3307 to 3306
  type: ClusterIP
```
