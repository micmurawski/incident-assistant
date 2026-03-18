"""
    Build a YAML status report for LLM consumption.

    The structure is:

    ```yaml
    namespace: <namespace>
    window: <window>
    services:
      <service-name>:
        latency_p50_ms: <float>
        latency_p95_ms: <float>
        latency_p99_ms: <float>
        cpu_cores: <float>
        cpu_cores_percent_of_limit: <float>
        memory_mb: <float>
        memory_percent_of_limit: <float>
        request_rate_rps: <float>
        success_rate: <float>  # 0-1
        http_4xx: <float>
        http_5xx: <float>
        error_log_count: <int>
        error_logs_samples: <list>
          - count: <int>
            truncated_message: <str>
    ```
"""


import time


def detect_differences(metrics_before: dict, metrics_after: dict, threshold: float = 10.0) -> dict:
    # 1. compare differences in metrics between before and after
    # 2. If difference is greater than the threshold for any metric, return the include to service in the diff dictionary
    diff = {}

    services_before = metrics_before.get("services", {})
    services_after = metrics_after.get("services", {})

    for service_name, after_metrics in services_after.items():
        before_metrics = services_before.get(service_name)

        if not before_metrics:
            # If the service wasn't present before, it's considered a difference
            diff[service_name] = after_metrics
            continue

        has_significant_change = False
        for key, after_val in after_metrics.items():
            if key == "error_logs_samples":
                continue

            before_val = before_metrics.get(key, 0.0)

            # Some metrics need scaling or special handling
            if key == "success_rate":
                # success_rate is 0-1, convert to 0-100 for threshold comparison
                current_diff = abs(after_val - before_val) * 100.0
            else:
                # Most other metrics are already in reasonable units (ms, cores%, MB, counts)
                current_diff = abs(after_val - before_val)

            if current_diff >= threshold:
                has_significant_change = True
                break

        if has_significant_change:
            diff[service_name] = after_metrics

    return diff


def live_timer(seconds):
    start_time = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= seconds:
                break
            print(f"\rElapsed time: {elapsed:.0f} seconds", end="", flush=True)

            time.sleep(0.5)  # Update frequently for a smooth look
    except KeyboardInterrupt:
        print("\nTimer stopped.")
