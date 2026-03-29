# Title
Dispatch service configured with incorrect RabbitMQ host

# Description
The `AMQP_HOST` environment variable in `k8s/manifests/dispatch.yaml` was set to `rabbitmq-cluster` instead of the correct service name `rabbitmq`.

# Symptom
The dispatch service will fail to start or continuously crash loop because it cannot connect to RabbitMQ. Orders will not be processed by the dispatch service.

# Root cause
The dispatch service uses the `AMQP_HOST` environment variable to connect to RabbitMQ. Since it is set to a non-existent hostname (`rabbitmq-cluster`), the connection fails.

# Fix
Change the `AMQP_HOST` environment variable in `k8s/manifests/dispatch.yaml` back to `rabbitmq` or remove it so it defaults to `rabbitmq`.
