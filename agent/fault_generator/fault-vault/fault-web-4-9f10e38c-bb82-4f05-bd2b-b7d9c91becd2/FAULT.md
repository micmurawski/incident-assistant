Title: NGINX Image Request Rate Limit

Description: A rate limit was introduced in the NGINX configuration for the `/images/` endpoint in `web/default.conf.template`. The `limit_req_zone` directive defines a shared memory zone for tracking request rates, and `limit_req zone=img_zone burst=5 nodelay` applies a limit of 1 request per second with a burst of 5 to image requests.

Symptom: Users will experience HTTP 503 (Service Unavailable) errors when making more than 1 request per second to image resources, with a small burst allowance. This will manifest as broken image links or slow loading of images under heavy load.

Root cause: The NGINX server is configured to rate limit requests to the `/images/` location to prevent resource exhaustion. When the request rate exceeds 1 request per second, subsequent requests are delayed or rejected with a 503 error.

Fix: Remove the `limit_req_zone` directive from the http context and the `limit_req` directive from the `/images/` location block in `web/default.conf.template`.