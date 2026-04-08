# User Service Performance Degradation Incident

## Title
User Service experiencing severe latency and timeouts

## Description
Users are reporting extremely slow response times when accessing the Robot Shop application. The homepage takes several seconds to load, and authentication operations (login/register) are timing out. Order history lookups are also failing or extremely slow.

**Impact:**
- Homepage loading slowly or timing out
- Login and registration failures
- Cart operations affected
- Overall application responsiveness severely degraded

**Metrics affected:**
- Increased error rates on user service endpoints (5xx errors)
- High latency on /api/user/* endpoints
- Elevated response times across all dependent services
