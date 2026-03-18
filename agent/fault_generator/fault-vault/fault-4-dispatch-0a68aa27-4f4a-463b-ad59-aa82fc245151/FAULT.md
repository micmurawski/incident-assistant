# RabbitMQ Channel Leak on Reconnection

## Description

In `dispatch/main.go`, the `rabbitConnector` function manages RabbitMQ connections and channels. When a connection error occurs and the service reconnects, the old channel is stored in an `oldChannels` slice but never closed or cleaned up. This creates a memory leak and accumulates open channels.

## Symptom

Over time, as RabbitMQ reconnections occur (due to network issues or broker restarts), the dispatch service will accumulate unfreed AMQP channels. This leads to:
- Increasing memory usage
- Eventual failure to create new channels (channel limit exhaustion on RabbitMQ broker)
- Service unable to process orders after reconnections

## Root Cause

The `rabbitConnector` function was modified to store old channels in a slice (`oldChannels`) without any cleanup mechanism. When a reconnection happens, the previous channel reference is added to the slice but never closed, causing both memory growth and channel resource exhaustion.

## Fix

Remove the `oldChannels` slice and properly close the old channel before creating a new one:

```go
// Instead of storing old channels:
// if rabbitChan != nil {
//     oldChannels = append(oldChannels, rabbitChan)
// }

// Close the old channel properly before creating new one
if rabbitChan != nil {
    rabbitChan.Close()
}
```
