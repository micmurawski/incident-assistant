# Incident: Intermittent Failures in Shipping and Ratings Services

## Title
Intermittent Failures in Shipping and Ratings Services

## Description
Users are reporting intermittent errors when trying to calculate shipping costs during checkout and when viewing or submitting product ratings. Monitoring systems show a spike in HTTP 500 errors originating from the `shipping` and `ratings` services. The issue appears to be correlated with periods of higher traffic, suggesting a potential resource bottleneck or exhaustion issue affecting these specific services. Database connection errors are also being observed in the logs for these services.