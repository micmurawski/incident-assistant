"""
Core tracing functionality for PocketFlow with Phoenix integration via OpenTelemetry.
"""

import json
from typing import Any, Dict, Optional

try:
    from opentelemetry import trace
    from opentelemetry.context import attach, detach
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
        OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import StatusCode, set_span_in_context

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    print(
        "Warning: opentelemetry packages not installed. "
        "Install with: pip install opentelemetry-api opentelemetry-sdk "
        "opentelemetry-exporter-otlp-proto-http"
    )

from .config import TracingConfig


class PhoenixTracer:
    """
    Core tracer class that sends OpenTelemetry traces to Arize Phoenix.
    """

    def __init__(self, config: TracingConfig):
        self.config = config
        self._tracer = None
        self._provider = None
        self._root_span = None
        self._root_token = None
        self.spans: Dict[str, Any] = {}

        if OTEL_AVAILABLE and config.validate():
            try:
                resource = Resource.create(
                    {"service.name": config.project_name or "pocketflow"}
                )
                self._provider = TracerProvider(resource=resource)

                endpoint = (config.phoenix_endpoint or "http://localhost:6006").rstrip(
                    "/"
                )
                exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
                self._provider.add_span_processor(BatchSpanProcessor(exporter))

                trace.set_tracer_provider(self._provider)
                self._tracer = trace.get_tracer("pocketflow")

                if config.debug:
                    print(
                        f"✓ Phoenix tracer initialized — sending to {endpoint}/v1/traces"
                    )
            except Exception as e:
                if config.debug:
                    print(f"✗ Failed to initialize Phoenix tracer: {e}")
                self._tracer = None
        else:
            if config.debug:
                print("✗ OpenTelemetry not available or configuration invalid")

    def start_trace(
        self, flow_name: str, input_data: Dict[str, Any]
    ) -> Optional[str]:
        """Start a new root span for a flow execution."""
        if not self._tracer:
            return None

        try:
            self._root_span = self._tracer.start_span(flow_name)
            ctx = set_span_in_context(self._root_span)
            self._root_token = attach(ctx)

            self._root_span.set_attribute("framework", "PocketFlow")

            if self.config.session_id:
                self._root_span.set_attribute("session.id", self.config.session_id)
            if self.config.user_id:
                self._root_span.set_attribute("user.id", self.config.user_id)

            trace_id = format(
                self._root_span.get_span_context().trace_id, "032x"
            )

            if self.config.debug:
                print(f"✓ Started trace: {trace_id} for flow: {flow_name}")

            return trace_id

        except Exception as e:
            if self.config.debug:
                print(f"✗ Failed to start trace: {e}")
            return None

    def end_trace(self, status: str = "success") -> None:
        """End the current root span."""
        if not self._root_span:
            return

        try:
            if status == "error":
                self._root_span.set_status(StatusCode.ERROR, "Flow execution failed")
            else:
                self._root_span.set_status(StatusCode.OK)

            self._root_span.end()

            if self.config.debug:
                print(f"✓ Ended trace with status: {status}")

        except Exception as e:
            if self.config.debug:
                print(f"✗ Failed to end trace: {e}")
        finally:
            if self._root_token is not None:
                detach(self._root_token)
            self._root_span = None
            self._root_token = None
            self.spans.clear()

    def start_node_span(self, node_name: str, node_id: str) -> Optional[str]:
        """
        Start a child span for a node execution.

        Returns:
            Span key if successful, None otherwise.
        """
        if not self._tracer or not self._root_span:
            return None

        try:
            parent_ctx = set_span_in_context(self._root_span)
            span = self._tracer.start_span(node_name, context=parent_ctx)
            span.set_attribute("node_type", node_name)
            span.set_attribute("node_id", node_id)

            self.spans[node_id] = span

            if self.config.debug:
                print(f"✓ Started span: {node_name} ({node_id})")

            return node_id

        except Exception as e:
            if self.config.debug:
                print(f"✗ Failed to start span: {e}")
            return None

    def end_node_span(
        self,
        span_id: str,
        input_messages: Any = None,
        output_messages: Any = None,
        error: Exception = None,
    ) -> None:
        """End a node span, recording messages in/out."""
        if span_id not in self.spans:
            return

        try:
            span = self.spans[span_id]

            if input_messages is not None and self.config.trace_inputs:
                val = self._serialize_for_attribute(input_messages)
                if val is not None:
                    span.set_attribute("input.messages", val)

            if output_messages is not None and self.config.trace_outputs:
                val = self._serialize_for_attribute(output_messages)
                if val is not None:
                    span.set_attribute("output.messages", val)

            if error and self.config.trace_errors:
                span.set_status(StatusCode.ERROR, str(error))
                span.record_exception(error)
            else:
                span.set_status(StatusCode.OK)

            span.end()

            if self.config.debug:
                status_label = "ERROR" if error else "OK"
                print(f"✓ Ended span: {span_id} [{status_label}]")

        except Exception as e:
            if self.config.debug:
                print(f"✗ Failed to end span: {e}")
        finally:
            self.spans.pop(span_id, None)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _serialize_for_attribute(self, data: Any) -> Optional[str]:
        """
        Serialize data into a JSON string suitable for an OTel span attribute.
        Returns None when serialisation fails completely.
        """
        raw = self._serialize_data(data)
        try:
            if isinstance(raw, str):
                return raw
            return json.dumps(raw, default=str)
        except Exception:
            return None

    @staticmethod
    def _serialize_data(data: Any, _depth: int = 0) -> Any:
        """Convert common Python types into JSON-friendly structures."""
        if _depth > 8:
            return "<...>"
        try:
            if data is None or isinstance(data, (str, int, float, bool)):
                return data
            if isinstance(data, (list, tuple)):
                return [
                    PhoenixTracer._serialize_data(item, _depth + 1)
                    for item in data
                ]
            if isinstance(data, dict):
                return {
                    str(k): PhoenixTracer._serialize_data(v, _depth + 1)
                    for k, v in data.items()
                }
            return f"<{type(data).__name__}>"
        except Exception:
            return "<serialization_failed>"

    def flush(self) -> None:
        """Force-flush any pending spans to Phoenix."""
        if self._provider:
            try:
                self._provider.force_flush()
                if self.config.debug:
                    print("✓ Flushed traces to Phoenix")
            except Exception as e:
                if self.config.debug:
                    print(f"✗ Failed to flush traces: {e}")
