# Performance Regression in Dispatch Service Order Processing

## Description
The artificial delay in order processing has been significantly increased in two locations within the dispatch service (`dispatch/main.go`):
- Line 146: The `createSpan` function now sleeps for 2500-4000ms instead of 42-84ms
- Line 164: The `processSale` function now sleeps for 2500-4000ms instead of 42-84ms

This represents a **~50x performance degradation** on the hot path of order processing.

## Symptom
- Order processing latency increases dramatically (from ~84-168ms to ~5000-8000ms per order)
- RabbitMQ message backlog grows as consumers cannot keep up with incoming orders
- End-to-end order fulfillment times increase significantly
- Throughput drops substantially (from ~6-12 orders/second to ~0.12-0.2 orders/second per consumer)

## Root Cause
The sleep duration on the critical path was increased from ~42-84ms to ~2500-4000ms. This is a performance regression introduced by modifying the sleep duration values without changing the underlying logic. The orders still process correctly, but the artificial delay simulates an extremely slow downstream dependency or inefficient processing code.

## Fix
Revert the sleep duration values to their original values:
- Line 146: Change `time.Sleep(time.Duration(2500+rand.Int63n(1500)) * time.Millisecond)` back to `time.Sleep(time.Duration(42+rand.Int63n(42)) * time.Millisecond)`
- Line 164: Change `time.Sleep(time.Duration(2500+rand.Int63n(1500)) * time.Millisecond)` back to `time.Sleep(time.Duration(42+rand.Int63n(42)) * time.Millisecond)`
