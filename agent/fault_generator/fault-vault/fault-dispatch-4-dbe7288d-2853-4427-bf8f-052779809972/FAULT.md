# Incomplete Error Handling in Dispatch Service

**Description**: The `failOnError` function in `dispatch/main.go` was changed from `log.Fatalf` to `log.Printf`. This prevents the service from exiting on critical errors, such as a failure to connect to RabbitMQ.

**Symptom**: The dispatch service may not process any orders, but it will continue running without any obvious signs of failure in its logs. Downstream services will not receive dispatched orders.

**Root cause**: The `failOnError` function is intended to stop the service when a critical error occurs. By changing `log.Fatalf` to `log.Printf`, the service logs the error but continues to run, leading to a silent failure where it's not processing messages.

**Fix**: Revert the change in `dispatch/main.go` to use `log.Fatalf` in the `failOnError` function.
