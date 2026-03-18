# Unacknowledged RabbitMQ Messages in Dispatch Service

## Description
The `autoAck` parameter in the `rabbitChan.Consume` call within `dispatch/main.go` was changed from `true` to `false`. However, the code does not manually acknowledge the messages after processing them.

## Symptom
- The number of unacknowledged messages in RabbitMQ will grow continuously as orders are processed.
- RabbitMQ memory usage will increase over time.
- If the dispatch service restarts or the connection drops, all previously processed but unacknowledged messages will be redelivered, causing duplicate order processing.

## Root Cause
The consumer is configured to require manual message acknowledgment (`autoAck=false`), but the application logic lacks the corresponding `d.Ack(false)` call to acknowledge the messages once they are successfully processed.

## Fix
Revert the `autoAck` parameter back to `true` in the `rabbitChan.Consume` call:
Change `msgs, err := rabbitChan.Consume("orders", "", false, false, false, false, nil)` back to `msgs, err := rabbitChan.Consume("orders", "", true, false, false, false, nil)`. Alternatively, add `d.Ack(false)` at the end of the message processing loop.
