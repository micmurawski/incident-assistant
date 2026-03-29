# Title: Dispatch service configured with incorrect RabbitMQ host

# Description:
The `AMQP_HOST` environment variable in the `dispatch` deployment manifest (`k8s/manifests/dispatch.yaml`) was set to `rabbitmq-cluster` instead of the correct service name `rabbitmq`.

# Symptom:
The dispatch service will fail to connect to RabbitMQ. It will continuously log connection errors and fail to process orders from the message queue. Users will not see their orders being dispatched.

# Root cause:
The dispatch service uses the `AMQP_HOST` environment variable to determine the hostname of the RabbitMQ server. By setting it to a non-existent hostname (`rabbitmq-cluster`), the service cannot resolve the address and establish a connection.

# Fix:
Revert the `AMQP_HOST` environment variable in `k8s/manifests/dispatch.yaml` to `rabbitmq` or remove it entirely, as the application defaults to `rabbitmq` if the variable is not set.
