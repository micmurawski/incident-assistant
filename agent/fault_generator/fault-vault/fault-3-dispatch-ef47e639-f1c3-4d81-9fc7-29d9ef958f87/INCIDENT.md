# Title: Orders are not being dispatched

# Description:
We are observing that orders placed by users are not being processed and dispatched. The dispatch service is failing to connect to the message queue, resulting in a backlog of unprocessed orders. Metrics show a drop in processed orders and an increase in connection errors from the dispatch service.
