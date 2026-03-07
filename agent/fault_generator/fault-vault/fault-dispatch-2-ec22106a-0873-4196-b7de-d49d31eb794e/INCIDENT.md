# RabbitMQ Unacknowledged Messages Accumulation

## Description
We are observing a continuous increase in the number of unacknowledged messages in the `orders` queue within RabbitMQ. The memory usage of the RabbitMQ cluster is steadily growing. Additionally, during a recent pod restart of the dispatch service, users reported receiving duplicate order confirmations, indicating that previously processed messages were redelivered.
