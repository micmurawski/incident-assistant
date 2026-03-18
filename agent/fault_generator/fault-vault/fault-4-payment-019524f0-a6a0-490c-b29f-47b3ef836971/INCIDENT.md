# Incident: Payment Service Memory and Connection Exhaustion

## Description
The payment service is experiencing a continuous increase in memory usage and open file descriptors. Under sustained load, the service eventually becomes unresponsive, leading to container restarts due to Out of Memory (OOM) errors or connection exhaustion. Users may experience failed payments or significant delays during checkout. Monitoring metrics show a steady climb in RSS memory and active connections for the payment pods.