"""
Decorate AsyncFlow to trace graph execution: shared before prep and after post per node.
Session id is taken from the first shared (configurable key); optional session prefix.
"""

import functools
import inspect
from typing import Optional

from .core import GraphTracer, snapshot_shared


def trace_flow(
    flow_name: Optional[str] = None,
):
    """
    Decorator for AsyncFlow: one span per node with shared_before (before prep) and shared_after (after post).
    Session id is read from shared["session_id"] at flow start.

    Usage:
        @trace_flow()
        class MyFlow(AsyncFlow):
            ...
    """
    def decorator(flow_class_or_func):
        if inspect.isclass(flow_class_or_func):
            return _trace_flow_class(flow_class_or_func, flow_name)
        return _trace_flow_function(flow_class_or_func, flow_name)
    return decorator


def _trace_flow_class(flow_class, flow_name):
    if flow_name is None:
        flow_name = flow_class.__name__

    original_init = flow_class.__init__
    original_run_async = getattr(flow_class, "run_async", None)

    def traced_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._graph_tracer = None
        self._flow_trace_name = flow_name
        self._nodes_patched = False

    async def traced_run_async(self, shared):
        if original_run_async is None:
            return
        if not self._nodes_patched:
            _patch_async_flow_nodes(self)
            self._nodes_patched = True
        self._graph_tracer = GraphTracer()
        self._graph_tracer.start_trace(self._flow_trace_name, shared)
        try:
            await original_run_async(self, shared)
            self._graph_tracer.end_trace("success")
        except Exception:
            self._graph_tracer.end_trace("error")
            raise
        finally:
            self._graph_tracer.flush()

    def _patch_async_flow_nodes(flow_instance):
        start = getattr(flow_instance, "start_node", None)
        if not start:
            return
        visited = set()
        queue = [start]
        while queue:
            node = queue.pop(0)
            if id(node) in visited:
                continue
            visited.add(id(node))
            _patch_node(flow_instance, node)
            for succ in getattr(node, "successors", {}).values():
                if succ and id(succ) not in visited:
                    queue.append(succ)

    def _patch_node(flow_instance, node):
        if getattr(node, "_graph_traced", False):
            return
        node_name = type(node).__name__
        original_run_async = getattr(node, "_run_async", None)
        if not original_run_async or not inspect.iscoroutinefunction(original_run_async):
            return

        @functools.wraps(original_run_async)
        async def traced_run_async(shared):
            tracer = getattr(flow_instance, "_graph_tracer", None)
            shared_before = snapshot_shared(shared) if tracer else None
            span_id = tracer.start_node_span(node_name) if tracer else None
            try:
                result = await original_run_async(shared)
                shared_after = snapshot_shared(shared) if tracer else None
                if tracer and span_id is not None:
                    tracer.end_node_span(span_id, shared_before=shared_before, shared_after=shared_after)
                return result
            except Exception as e:
                if tracer and span_id is not None:
                    tracer.end_node_span(span_id, shared_before=shared_before, shared_after=None, error=e)
                raise

        node._run_async = traced_run_async
        node._graph_traced = True

    flow_class.__init__ = traced_init
    flow_class.run_async = traced_run_async
    return flow_class


def _trace_flow_function(flow_func, flow_name):
    if flow_name is None:
        flow_name = flow_func.__name__

    tracer = GraphTracer()

    @functools.wraps(flow_func)
    async def traced(*args, **kwargs):
        shared = args[0] if args else {}
        tracer.start_trace(flow_name, shared)
        try:
            result = await flow_func(*args, **kwargs)
            tracer.end_trace("success")
            return result
        except Exception:
            tracer.end_trace("error")
            raise
        finally:
            tracer.flush()

    return traced
