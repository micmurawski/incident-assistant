# Goroutine Leak in Dispatch Service

## Description

In `dispatch/main.go`, a new unbuffered channel `statChan` was introduced, and a goroutine is spawned in `processSale` to send a value to this channel. However, there is no receiver for `statChan`.

## Symptom

The dispatch service will experience a goroutine leak. Every time an order is processed, a new goroutine is created and blocks indefinitely trying to send to `statChan`. Over time, this will lead to increased memory usage and eventually cause the service to crash due to resource exhaustion (OOM).

## Root Cause

The `processSale` function spawns a goroutine that attempts to send a value to an unbuffered channel (`statChan`) that has no receiver. This causes the goroutine to block forever, leading to a goroutine leak.

## Fix

Remove the `statChan` channel and the goroutine that sends to it in `processSale`.

```go
// Remove this code from processSale:
// go func() {
// 	statChan <- 1
// }()
```
