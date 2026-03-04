**Title**: Cart service misconfigured Redis host

**Description**: The `REDIS_HOST` environment variable for the `cart` service deployment in `k8s/robot-shop-eks.yaml` was set to an incorrect value: `wrong-redis-host`.

**Symptom**: The cart service will be unable to connect to the Redis database, leading to failures in cart operations (e.g., adding items to cart, viewing cart contents). Users may experience errors or a non-functional cart.

**Root cause**: The `cart` service depends on Redis, and by providing an incorrect `REDIS_HOST` environment variable, the service will attempt to connect to a non-existent host, resulting in connection errors and operational failure.

**Fix**: Correct the `REDIS_HOST` environment variable in the `cart` service deployment in `k8s/robot-shop-eks.yaml` to the correct Redis service name, which is `redis`.