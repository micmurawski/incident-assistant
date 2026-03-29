# Title: Application Outage - Catalogue and User Services Failing

# Description
Users are reporting an inability to browse the product catalogue or log into their accounts. Monitoring shows that the `catalogue` and `user` services are experiencing high error rates and timeouts when attempting to connect to the database. The MongoDB pod is running but is not receiving any traffic, and the `mongodb` service has no active endpoints.