# Incident: Ratings Service Errors Under Load

## Description
Over time, as more rating requests are made, the ratings service may start returning 500 errors or become unresponsive. SKU validation or rating operations fail with "too many open files" or similar errors. The service may stop responding.