# Fault: Dispatch Service AMQP Host Misconfiguration

## Description
The `dispatch` Deployment in `k8s/robot-shop-eks.yaml` has been misconfigured with an incorrect `AMQP_HOST` environment variable. It is set to `rabbitmq-cluster` instead of the correct service name `rabbitmq`.

## Symptom
The dispatch service will fail to connect to RabbitMQ. It will continuously log connection errors and fail to process orders from the message queue. Users will not see their orders being dispatched, and monitoring will show the dispatch service failing to establish a connection to the message broker.

## Root Cause
The `AMQP_HOST` environment variable in the dispatch Deployment is pointing to a non-existent Kubernetes service (`rabbitmq-cluster`). The correct service name for RabbitMQ in this cluster is `rabbitmq`.

## Fix
Remove the incorrect `AMQP_HOST` environment variable from the dispatch Deployment in `k8s/robot-shop-eks.yaml` (it defaults to `rabbitmq` in the code) or change its value to `rabbitmq`:

```yaml
        env:
        - name: AMQP_HOST
          value: "rabbitmq"