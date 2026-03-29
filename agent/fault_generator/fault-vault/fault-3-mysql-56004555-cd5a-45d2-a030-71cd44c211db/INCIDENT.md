# MySQL Service Unavailable

## Description
The MySQL service is currently unavailable. The MySQL pod is running but is not becoming "Ready". As a result, dependent services (such as the shipping service) are failing to connect to the database, leading to errors when users attempt to calculate shipping costs or complete their orders. Monitoring shows that the MySQL pod is failing its readiness checks.