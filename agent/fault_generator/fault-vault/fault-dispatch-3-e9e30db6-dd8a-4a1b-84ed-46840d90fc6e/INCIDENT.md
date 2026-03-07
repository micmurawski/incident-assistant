# Incident: Order Dispatching Stalled

## Description
We are observing that orders are no longer being dispatched. The dispatch service is failing to process messages from the queue, leading to a backlog of unprocessed orders. Customers are reporting that their orders are stuck in the "processing" state and are not being fulfilled. Metrics indicate that the dispatch service is unable to establish a connection to the message broker.