"""
Decorator for tracing PocketFlow workflows with Phoenix (via OpenTelemetry).

Produces one span per node with messages-in / messages-out instead of
separate prep/exec/post spans.
"""

import functools
import inspect
import uuid
from typing import Optional

from .config import TracingConfig
from .core import PhoenixTracer


def trace_flow(
    config: Optional[TracingConfig] = None,
    flow_name: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None
):
    """
    Decorator to add Phoenix tracing to PocketFlow flows.

    Traces:
    - Flow execution as a root span (named after the agent when available)
    - Each node as a child span with input/output messages

    Args:
        config: TracingConfig instance. If None, loads from environment.
        flow_name: Fallback name for the root span. If None, uses class name.
        session_id: Session ID for grouping related traces.
        user_id: User ID for the trace.
    """
    def decorator(flow_class_or_func):
        if inspect.isclass(flow_class_or_func):
            return _trace_flow_class(flow_class_or_func, config, flow_name, session_id, user_id)
        else:
            return _trace_flow_function(flow_class_or_func, config, flow_name, session_id, user_id)

    return decorator


def _trace_flow_class(flow_class, config, flow_name, session_id, user_id):
    """Trace a Flow class by wrapping _run / _run_async on every node."""

    if config is None:
        config = TracingConfig.from_env()

    if session_id:
        config.session_id = session_id
    if user_id:
        config.user_id = user_id

    if flow_name is None:
        flow_name = flow_class.__name__

    original_init = flow_class.__init__
    original_run = getattr(flow_class, 'run', None)
    original_run_async = getattr(flow_class, 'run_async', None)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def traced_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._tracer = PhoenixTracer(config)
        self._flow_name = flow_name
        self._trace_id = None
        self._nodes_patched = False

    # ------------------------------------------------------------------
    # Name resolution — prefer agent.name from shared
    # ------------------------------------------------------------------

    def _resolve_flow_name(self, shared):
        agent = shared.get("agent") if isinstance(shared, dict) else None
        if agent and hasattr(agent, "name"):
            return agent.name
        return self._flow_name

    # ------------------------------------------------------------------
    # Run wrappers
    # ------------------------------------------------------------------

    def traced_run(self, shared):
        if not hasattr(self, '_tracer'):
            return original_run(self, shared) if original_run else None

        if not self._nodes_patched:
            self._patch_nodes()
            self._nodes_patched = True

        resolved_name = self._resolve_flow_name(shared)
        self._trace_id = self._tracer.start_trace(resolved_name, shared)

        try:
            result = original_run(self, shared) if original_run else None
            self._tracer.end_trace("success")
            return result
        except Exception:
            self._tracer.end_trace("error")
            raise
        finally:
            self._tracer.flush()

    async def traced_run_async(self, shared):
        if not hasattr(self, '_tracer'):
            return await original_run_async(self, shared) if original_run_async else None

        if not self._nodes_patched:
            self._patch_nodes()
            self._nodes_patched = True

        resolved_name = self._resolve_flow_name(shared)
        self._trace_id = self._tracer.start_trace(resolved_name, shared)

        try:
            result = await original_run_async(self, shared) if original_run_async else None
            self._tracer.end_trace("success")
            return result
        except Exception:
            self._tracer.end_trace("error")
            raise
        finally:
            self._tracer.flush()

    # ------------------------------------------------------------------
    # Node graph walking
    # ------------------------------------------------------------------

    def patch_nodes(self):
        if not hasattr(self, 'start_node') or not self.start_node:
            return

        visited = set()
        queue = [self.start_node]

        while queue:
            node = queue.pop(0)
            if id(node) in visited:
                continue

            visited.add(id(node))
            self._patch_node(node)

            if hasattr(node, 'successors'):
                for successor in node.successors.values():
                    if successor and id(successor) not in visited:
                        queue.append(successor)

    # ------------------------------------------------------------------
    # Per-node patching — wraps _run / _run_async
    # ------------------------------------------------------------------

    def patch_node(self, node):
        if hasattr(node, '_pocketflow_traced'):
            return

        node_id = str(uuid.uuid4())
        node_name = type(node).__name__

        original_node_run_async = getattr(node, '_run_async', None)
        original_node_run = getattr(node, '_run', None)

        if original_node_run_async and inspect.iscoroutinefunction(original_node_run_async):
            node._run_async = self._create_traced_run_async(
                original_node_run_async, node_id, node_name
            )

        if original_node_run and not inspect.iscoroutinefunction(original_node_run):
            node._run = self._create_traced_run(
                original_node_run, node_id, node_name
            )

        node._pocketflow_traced = True

    # ------------------------------------------------------------------
    # Traced wrappers that capture messages before/after
    # ------------------------------------------------------------------

    def _get_messages(shared):
        if isinstance(shared, dict) and "messages" in shared:
            return list(shared["messages"])
        return None

    def create_traced_run(self, original_method, node_id, node_name):
        @functools.wraps(original_method)
        def traced(shared):
            input_msgs = _get_messages(shared)
            span_id = self._tracer.start_node_span(node_name, node_id)
            try:
                result = original_method(shared)
                output_msgs = _get_messages(shared)
                self._tracer.end_node_span(
                    span_id, input_messages=input_msgs, output_messages=output_msgs
                )
                return result
            except Exception as e:
                self._tracer.end_node_span(span_id, input_messages=input_msgs, error=e)
                raise

        return traced

    def create_traced_run_async(self, original_method, node_id, node_name):
        @functools.wraps(original_method)
        async def traced(shared):
            input_msgs = _get_messages(shared)
            span_id = self._tracer.start_node_span(node_name, node_id)
            try:
                result = await original_method(shared)
                output_msgs = _get_messages(shared)
                self._tracer.end_node_span(
                    span_id, input_messages=input_msgs, output_messages=output_msgs
                )
                return result
            except Exception as e:
                self._tracer.end_node_span(span_id, input_messages=input_msgs, error=e)
                raise

        return traced

    # ------------------------------------------------------------------
    # Attach everything to the class
    # ------------------------------------------------------------------

    flow_class.__init__ = traced_init
    flow_class._resolve_flow_name = _resolve_flow_name
    flow_class._patch_nodes = patch_nodes
    flow_class._patch_node = patch_node
    flow_class._create_traced_run = create_traced_run
    flow_class._create_traced_run_async = create_traced_run_async

    if original_run:
        flow_class.run = traced_run
    if original_run_async:
        flow_class.run_async = traced_run_async

    return flow_class


def _trace_flow_function(flow_func, config, flow_name, session_id, user_id):
    """Trace a flow function (for functional-style flows)."""

    if config is None:
        config = TracingConfig.from_env()

    if session_id:
        config.session_id = session_id
    if user_id:
        config.user_id = user_id

    if flow_name is None:
        flow_name = flow_func.__name__

    tracer = PhoenixTracer(config)

    @functools.wraps(flow_func)
    def traced_flow_func(*args, **kwargs):
        shared = args[0] if args else {}

        tracer.start_trace(flow_name, shared)

        try:
            result = flow_func(*args, **kwargs)
            tracer.end_trace("success")
            return result
        except Exception:
            tracer.end_trace("error")
            raise
        finally:
            tracer.flush()

    return traced_flow_func
