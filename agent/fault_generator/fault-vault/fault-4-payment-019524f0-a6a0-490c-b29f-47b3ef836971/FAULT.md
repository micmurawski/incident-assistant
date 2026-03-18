# Fault: Connection Leak in Payment Service

## Description
Added a global list `_recent_checks` to store the response objects from the user check endpoint. The `requests.get` call was also modified to use `stream=True`. The response objects are appended to the list but never closed or removed.

## Location
`payment/payment.py` - lines 54 (list declaration) and lines 66-67 (streaming request and appending to list in `/pay/<id>` endpoint)

## Symptom
- Continuous growth of memory usage in the payment service container
- Exhaustion of available connections/file descriptors
- Eventually leads to OOM (Out of Memory) errors or connection errors and container restarts
- Monitoring shows increasing RSS memory and open file descriptors for the payment pod
- Under high load, the service becomes unresponsive as memory allocation fails or connection limits are reached

## Root Cause
The code makes a streaming HTTP request to the user service and stores the response object in a global list. Because `stream=True` is used and the response is never closed or read completely, the underlying connection remains open. Furthermore, storing the response objects in a global list that is never cleared causes unbounded memory growth. This leads to both a connection leak and a memory leak.

## Fix
To fix this issue, remove the `_recent_checks` list and the `stream=True` parameter from the `requests.get` call. If streaming is required, ensure the response is properly closed or used within a context manager (`with requests.get(...) as req:`).

Example fix:
```python
    # check user exists
    try:
        req = requests.get('http://{user}:8080/check/{id}'.format(user=USER, id=id))
    except requests.exceptions.RequestException as err: