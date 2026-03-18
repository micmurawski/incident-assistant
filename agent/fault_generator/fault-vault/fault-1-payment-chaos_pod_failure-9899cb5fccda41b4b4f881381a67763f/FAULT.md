# Fault: Payment Service Health Check Dependent on RabbitMQ

## Description
Modified the payment service's health check endpoint (`/health`) to verify RabbitMQ connectivity instead of returning a simple OK status. The health check now calls `publisher.is_connected()` which checks if the RabbitMQ connection is open. Additionally, added a verification step in `queueOrder()` that raises an exception if the connection drops after publishing.

## Changes Made
- **payment/payment.py**: 
  - Modified the `/health` route to check RabbitMQ connection status via `publisher.is_connected()`
  - Added connection verification in `queueOrder()` that raises an exception if connection is lost after publishing
- **payment/rabbitmq.py**: 
  - Added `is_connected()` method to the Publisher class to expose connection status

## Symptom
- Health check endpoint (`/health`) returns HTTP 503 "service unavailable" when RabbitMQ connection is down
- Payment processing fails with HTTP 500 "Queue connection failed" when attempting to queue orders
- Users cannot complete purchases; all payment requests fail
- Kubernetes may restart the pod repeatedly due to failed health checks

## Root Cause
The payment service's health check was changed from a simple pass-through to requiring an active RabbitMQ connection. During a pod-failure chaos experiment, when the pod becomes unavailable and then restarts, the RabbitMQ connection may be lost. The new health check immediately fails when RabbitMQ is unreachable, preventing the service from being considered healthy even after the pod restarts.

## Fix
Revert the health check to return 'OK' without checking RabbitMQ connectivity:
```python
@app.route('/health', methods=['GET'])
def health():
    return 'OK'
```

Alternatively, remove the verification step in `queueOrder()` that throws an exception when connection status changes after publish.
