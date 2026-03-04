# Title: Incorrect RabbitMQ hostname configuration in dispatch service

## Description
In `dispatch/main.go`, the environment variable used to configure the RabbitMQ host was changed from `AMQP_HOST` to `AMQP_HOS`. This typo causes the service to fail to read the correct configuration from its environment.

## Symptom
The dispatch service is unable to connect to RabbitMQ. It continuously tries to reconnect, logging connection error messages. As a result, orders are not dispatched, and the order processing pipeline is stalled.

## Root Cause
The dispatch service is designed to get the RabbitMQ hostname from the `AMQP_HOST` environment variable. The code was modified to look for `AMQP_HOS` instead. Since this environment variable is not defined in the deployment configuration, the service falls back to its default value, which is "rabbitmq". This hostname is not resolvable or reachable in the production environment, causing a persistent connection failure.

## Fix
To fix this issue, the environment variable name in `dispatch/main.go` must be corrected from `AMQP_HOS` back to `AMQP_HOST`. This will allow the service to correctly read the RabbitMQ hostname from the deployment configuration and establish a connection.
