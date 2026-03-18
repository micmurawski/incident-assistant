# Incident: Dispatch Service Memory Growth and Order Processing Failures After Reconnections

## Description
Over time, after network or broker reconnections, the dispatch service uses more memory and may eventually fail to process new orders. Order processing can stop working following reconnection events.