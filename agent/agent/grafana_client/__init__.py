"""
Grafana client for SRE Agent: metrics, logs, and LLM-ready reports.

Usage:
    from grafana_client import GrafanaClient, build_status_report

    client = GrafanaClient(url="http://grafana.example.com/", api_key="glsa_...")
    report = build_status_report(
        client,
        namespace="application",
        apps=["cart", "frontend", "payment"],
        window="5m",
        similarity_threshold=0.5,
    )
    print(report)
"""

from .client import AsyncGrafanaClient, Datasource, GrafanaClient
from .logs import (count_error_logs, fetch_error_logs, get_error_counts_by_app,
                   get_grouped_errors_by_app, group_by_similarity)
from .metrics import (WINDOWS, get_cpu_usage, get_http_error_counts,
                      get_latency_percentiles, get_memory_usage,
                      get_request_rate, get_success_rate)
from .pandas_client import GrafanaPandasClient
from .report import build_status_report, format_status_report

__all__ = [
    "GrafanaClient",
    "AsyncGrafanaClient",
    "GrafanaPandasClient",
    "Datasource",
    "get_latency_percentiles",
    "get_http_error_counts",
    "get_request_rate",
    "get_success_rate",
    "get_cpu_usage",
    "get_memory_usage",
    "WINDOWS",
    "count_error_logs",
    "fetch_error_logs",
    "group_by_similarity",
    "get_error_counts_by_app",
    "get_grouped_errors_by_app",
    "format_status_report",
    "build_status_report",
]
