# Incident: Add-to-Cart Failing Under Load

## Description
Under load, add-to-cart operations begin to fail with connection or "too many open files" errors. The cart service may still report healthy initially. Over time, cart operations become unreliable or unresponsive.