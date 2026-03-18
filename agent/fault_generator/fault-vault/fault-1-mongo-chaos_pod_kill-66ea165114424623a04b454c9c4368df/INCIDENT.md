# Incident: MongoDB Service Interruption

## Description
During the scheduled chaos engineering experiment targeting the MongoDB service, we observed extended service disruption across multiple dependent services. The catalogue and user services experienced prolonged unavailability, significantly impacting the application's core functionality including:

- Product catalog browsing and search
- User authentication and registration
- Order history retrieval

Both services took significantly longer than expected to recover after the MongoDB pods were terminated. The health check endpoints continued to report database connection failures for an extended period, affecting the overall availability of the Robot Shop e-commerce application.

**Metrics affected:**
- Catalogue service availability: dropped to 0% during MongoDB pod termination
- User service availability: dropped to 0% during MongoDB pod termination  
- API response time: significantly increased when services eventually recovered

The incident lasted approximately 60 minutes, aligning with the chaos experiment duration. Services did not recover as quickly as expected from the MongoDB pod termination event.
