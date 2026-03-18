# Incident: User Service Memory Growth and Crashes

## Description
User service memory usage grows over time as more users log in. The container may be OOM killed or crash. Performance degrades and the pod may restart repeatedly. Health checks can fail as the process becomes unresponsive.