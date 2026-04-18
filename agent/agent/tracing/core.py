"""
Graph execution tracer: one span per node with shared state before (prep) and after (post).
No LLM/model/usage — graph and shared only.
"""

import json
import os
import uuid
from logging import getLogger
from typing import Any, Dict, Optional

from opentelemetry import trace as otel_trace
from opentelemetry.context import attach, detach
from opentelemetry.trace import StatusCode, set_span_in_context
from phoenix.otel import register

logger = getLogger(__name__)


def _serialize_shared(data: Any, depth: int = 0) -> Any:
    if depth > 10:
        return "<...>"
    if data is None or isinstance(data, (str, int, float, bool)):
        return data
    if isinstance(data, (list, tuple)):
        return [_serialize_shared(x, depth + 1) for x in data]
    if isinstance(data, dict):
        return {str(k): _serialize_shared(v, depth + 1) for k, v in data.items()}
    return str(data)


def snapshot_shared(shared: Any) -> Any:
    """Serializable snapshot of shared state (safe for objects that can't be deep-copied)."""
    return _serialize_shared(shared)


def _shared_to_attribute(shared: Any) -> Optional[str]:
    try:
        raw = _serialize_shared(shared)
        if isinstance(raw, str):
            return raw[:32000] if len(raw) > 32000 else raw
        s = json.dumps(raw, default=str)
        return s[:32000] if len(s) > 32000 else s
    except Exception:
        return None


PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")


def ensure_tracer_provider(project_name: str = "graph-executions") -> Any:
    """Ensure a global TracerProvider is registered. Returns the provider."""
    # Arize Phoenix register() sets the global tracer provider and returns it.
    return register(project_name=project_name)


def ensure_anthropic_instrumentation(tracer_provider=None):
    """Ensure Anthropic is instrumented with the given (or global) provider."""
    try:
        from openinference.instrumentation.anthropic import \
            AnthropicInstrumentor

        # Avoid double-instrumenting
        if not AnthropicInstrumentor().is_instrumented_by_opentelemetry:
            AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
    except (ImportError, Exception) as e:
        logger.warning(f"[Tracing] Could not instrument Anthropic: {e}")


def ensure_openai_instrumentation(tracer_provider=None):
    """Ensure OpenAI (and OpenAI-compatible) clients are instrumented."""
    try:
        from openinference.instrumentation.openai import OpenAIInstrumentor

        if not OpenAIInstrumentor().is_instrumented_by_opentelemetry:
            OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
    except (ImportError, Exception) as e:
        logger.warning(f"[Tracing] Could not instrument OpenAI: {e}")


def ensure_google_genai_instrumentation(tracer_provider=None):
    """Ensure Google GenAI (Gemini) is instrumented."""
    try:
        from openinference.instrumentation.google_genai import \
            GoogleGenAIInstrumentor

        if not GoogleGenAIInstrumentor().is_instrumented_by_opentelemetry:
            GoogleGenAIInstrumentor().instrument(
                tracer_provider=tracer_provider
            )
    except (ImportError, Exception) as e:
        logger.warning(f"[Tracing] Could not instrument Google GenAI: {e}")


# Provider -> instrumentation function. Providers that share a wire protocol
# share an instrumentor (e.g. minimax's Anthropic-compatible endpoint, and
# OpenAI-compatible providers like groq/openrouter/ovh).
_PROVIDER_INSTRUMENTORS = {
    "anthropic": ensure_anthropic_instrumentation,
    "minimax": ensure_anthropic_instrumentation,
    "openai": ensure_openai_instrumentation,
    "groq": ensure_openai_instrumentation,
    "openrouter": ensure_openai_instrumentation,
    "ovh": ensure_openai_instrumentation,
    "gemini": ensure_google_genai_instrumentation,
}


def ensure_provider_instrumentation(provider: str, tracer_provider=None) -> None:
    """Install the OpenInference instrumentor that matches ``provider``.

    Unknown providers (e.g. ``ollama``) are silently skipped with a warning so
    tracing stays best-effort and never breaks the experiment.
    """
    instrumentor = _PROVIDER_INSTRUMENTORS.get(provider)
    if instrumentor is None:
        logger.warning(
            f"[Tracing] No instrumentor registered for provider '{provider}'; "
            "LLM spans will not be emitted."
        )
        return
    instrumentor(tracer_provider=tracer_provider)


class GraphTracer:
    """
    Tracer for flow graph execution only.
    Records shared state before and after each node (no prep/exec/post internals).
    Uses the existing global TracerProvider when present (e.g. Phoenix) so graph
    and LLM traces coexist; otherwise creates and sets its own provider.
    """

    def __init__(self):
        # Prefer existing global provider to ensure coexistence with other traces
        self._provider = otel_trace.get_tracer_provider()
        self._tracer = otel_trace.get_tracer("pocketflow-graph", "1.0")

        self._root_span = None
        self._root_token = None
        self._spans: Dict[str, Any] = {}

    def _session_id_from_shared(self, shared: Dict[str, Any]) -> Optional[str]:
        if not isinstance(shared, dict):
            return None
        sid = shared.get("session_id")
        if sid is None:
            return None
        sid = str(sid).strip()
        if not sid:
            return None
        # if self.config.session_prefix:
        #    return f"{self.config.session_prefix}:{sid}"
        return sid

    def start_trace(self, flow_name: str, shared: Dict[str, Any]) -> Optional[str]:
        """Start root span for this flow run. Session id taken from shared."""
        self._root_span = self._tracer.start_span(flow_name)
        ctx = set_span_in_context(self._root_span)
        self._root_token = attach(ctx)
        self._root_span.set_attribute("type", "graph-execution")

        session_id = self._session_id_from_shared(shared)
        if session_id:
            self._root_span.set_attribute("session.id", session_id)

        trace_id = format(self._root_span.get_span_context().trace_id, "032x")
        return trace_id

    def end_trace(self, status: str = "success") -> None:
        if not self._root_span:
            return
        if status == "error":
            self._root_span.set_status(StatusCode.ERROR, "Flow failed")
        else:
            self._root_span.set_status(StatusCode.OK)
        self._root_span.end()
        if self._root_token is not None:
            detach(self._root_token)
            self._root_token = None

    def start_node_span(self, node_name: str) -> Optional[str]:
        if not self._tracer or not self._root_span:
            return None

        span_id = str(uuid.uuid4())
        parent_ctx = set_span_in_context(self._root_span)
        span = self._tracer.start_span(node_name, context=parent_ctx)
        span.set_attribute("node_type", node_name)
        ctx = set_span_in_context(span)
        token = attach(ctx)
        self._spans[span_id] = (span, token)
        return span_id

    def end_node_span(
        self,
        span_id: str,
        shared_before: Optional[Dict[str, Any]] = None,
        shared_after: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        if span_id not in self._spans:
            return
        try:
            span, token = self._spans[span_id]
            if shared_before is not None:
                val = _shared_to_attribute(shared_before)
                if val is not None:
                    span.set_attribute("shared_before", val)
            if shared_after is not None:
                val = _shared_to_attribute(shared_after)
                if val is not None:
                    span.set_attribute("shared_after", val)
            if error is not None:
                span.set_status(StatusCode.ERROR, str(error))
                span.record_exception(error)
            else:
                span.set_status(StatusCode.OK)
            span.end()
            detach(token)
        except Exception as e:
            logger.error(f"[GraphTracer] end_node_span failed: {e}")
        finally:
            self._spans.pop(span_id, None)

    def flush(self) -> None:
        try:
            # Try to flush the provider if it supports it
            if hasattr(self._provider, "force_flush"):
                self._provider.force_flush()
        except Exception as e:
            logger.error(f"[GraphTracer] flush failed: {e}")

