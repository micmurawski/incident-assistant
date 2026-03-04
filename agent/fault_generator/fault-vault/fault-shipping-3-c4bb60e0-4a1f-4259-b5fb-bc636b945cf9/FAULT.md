Title: Shipping service memory limit
Description: The maximum heap size for the Java application in the `shipping/Dockerfile` was reduced from 768m to 64m.
Symptom: The shipping service may experience OutOfMemoryError exceptions and become unstable or unresponsive, especially under load. This could lead to failed shipping requests.
Root cause: The Java application is configured with an insufficient maximum heap size, leading to memory exhaustion.
Fix: Revert the change in `shipping/Dockerfile` to set the `-Xmx` parameter back to an adequate value (e.g., `-Xmx768m`).