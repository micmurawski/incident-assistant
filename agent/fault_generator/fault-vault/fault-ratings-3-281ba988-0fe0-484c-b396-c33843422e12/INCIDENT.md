# Incident: Ratings Service Unavailable and Pods Restarting

## Description
The ratings service is currently unavailable. Users are unable to view or submit ratings for products. Monitoring shows that the ratings pods are continuously failing their health checks and are in a crash loop, being repeatedly restarted by Kubernetes. The service endpoints are empty, meaning no traffic is being routed to the ratings application.
