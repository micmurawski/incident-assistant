# Incident: User Service Memory Growth and Crashes

## Description
User service memory usage grows over time. Under moderate to high traffic the service can exhaust memory and crash. Response times may degrade before crash. The pod may restart due to memory limits. Health checks may fail as the process becomes unresponsive.