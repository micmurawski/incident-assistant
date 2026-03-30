# Title: Incorrect AMQP_HOST environment variable in payment deployment

# Description:
Added an incorrect `AMQP_HOST` environment variable (`rabbitmq-cluster`) to the `payment` deployment in `k8s/manifests/payment.yaml`. The correct host should be `rabbitmq`.

# Symptom:
The payment service will fail to connect to RabbitMQ to publish order messages. Users will experience errors when trying to complete a purchase, and orders will not be processed.

# Root cause:
The `payment` service uses the `AMQP_HOST` environment variable to determine the hostname of the RabbitMQ broker. By setting it to an incorrect value (`rabbitmq-cluster`), the service attempts to connect to a non-existent host, resulting in connection failures.

# Fix:
Remove the incorrect `AMQP_HOST` environment variable from the `payment` deployment in `k8s/manifests/payment.yaml` or set it to the correct value (`rabbitmq`).
