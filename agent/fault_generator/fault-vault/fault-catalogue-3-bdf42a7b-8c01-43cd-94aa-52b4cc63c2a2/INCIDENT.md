# Incident: Catalogue Health Checks Failing

## Description
The catalogue service health endpoint is slow or unresponsive. Orchestrators may mark the service unhealthy and restart it. Other catalogue endpoints may be delayed when health checks are called frequently.