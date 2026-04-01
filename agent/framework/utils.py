import inspect
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from framework import Node
from pydantic import BaseModel, Field, create_model

# JSON-serializable primitives; anything else (dict/list we recurse; iterators/models we materialize).
_JSON_PRIMITIVES = (type(None), str, int, float, bool)


def _deep_materialize(obj: Any, preserve_custom_objects: bool = False) -> Any:
    """
    Recursively convert to JSON-serializable plain dict/list/primitive.
    Consumes one-shot iterators (e.g. Pydantic SerializationIterator) and
    converts Pydantic models via model_dump().

    Args:
        obj: The object to materialize.
        preserve_custom_objects: If True, objects with model_dump() (like Task)
            are preserved as-is. Useful when injecting into nodes so they
            receive rich objects. If False (default), they are materialized.
    """
    if obj is None or isinstance(obj, _JSON_PRIMITIVES):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value

    # If it's a custom object we want to preserve during node execution
    if preserve_custom_objects and hasattr(obj, "model_dump"):
        return obj

    if hasattr(obj, "model_dump"):
        return _deep_materialize(obj.model_dump(), preserve_custom_objects=preserve_custom_objects)
    if isinstance(obj, dict):
        return {k: _deep_materialize(v, preserve_custom_objects=preserve_custom_objects) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_materialize(x, preserve_custom_objects=preserve_custom_objects) for x in obj]
    
    # Handle other iterables (e.g., Pydantic's ValidatorIterator/SerializationIterator)
    if hasattr(obj, "__iter__"):
        try:
            return [_deep_materialize(x, preserve_custom_objects=preserve_custom_objects) for x in obj]
        except (TypeError, ValueError):
            # If it's supposedly iterable but fails, we fall through to the exception
            pass

    raise TypeError(f"Object of type {type(obj).__name__} is not JSON-serializable and cannot be materialized.")


def signature_to_field_definitions(parameters: dict[str, inspect.Parameter]) -> dict:
    res = {}
    for name, field in parameters.items():
        res[name] = {
            "type": field.annotation,
            "default": ... if field.default is inspect._empty else field.default,
        }
    return res


def signature_to_input_model(name, signature: inspect.Signature) -> dict:
    return create_model_from_dict(f"{name}_input", signature_to_field_definitions(signature.parameters))


def create_model_from_dict(model_name: str, field_definitions: dict):
    """Create a Pydantic model from field definitions"""
    fields = {}

    for field_name, field_config in field_definitions.items():
        field_type = field_config["type"]
        default = field_config.get("default", ...)
        description = field_config.get("description", "")
        if description:
            fields[field_name] = (field_type, Field(default=default, description=description))
        else:
            fields[field_name] = (field_type, default)
    return create_model(model_name, **fields)


def __init(self, **kwargs: dict[str, Any]):
    super(type(self), self).__init__()
    self.max_retries = kwargs.get("max_retries", 1)
    self.wait = kwargs.get("wait", 0)


def create_prep(signature: inspect.Signature) -> Callable[[Node, Any], dict]:
    def prep_inner(self, shared: Any) -> dict:
        res = {}
        for name, field in signature.parameters.items():
            res[name] = shared.get(name)
            if field.default is inspect._empty and res[name] is None:
                raise ValueError(f"Parameter {name} has no default value")
            elif res[name] is None:
                res[name] = field.default
        return res

    return prep_inner


def shallow_deserialize(model: BaseModel) -> dict:
    res = {}
    for k in model.model_fields:
        res[k] = getattr(model, k)
    return res


def __reduce_shared(self, shared, prep_res, exec_res) -> str:
    if isinstance(exec_res, tuple) and len(exec_res) > 1:
        state, action = exec_res
    else:
        state, action = exec_res, "default"

    if state is None:
        return action

    if not isinstance(state, dict):
        raise ValueError(f"Error at {self.__name__}: state must be a dict, got {type(state)}")
    # Never store non-JSON-serializable values (e.g. SerializationIterator, Pydantic models) in shared.
    state = _deep_materialize(state)
    shared.update(state)
    return action


def node(func=None, *, max_retries=1, wait=0):
    """
    Decorator that creates a PocketFlow Node instance from a function.

    Can be used as:
    - @node (uses default args)
    - @node() (uses default args)
    - @node(max_retries=3, wait=2) (custom args)

    Args:
        func: The function to decorate (when used as @node)
        max_retries (int): Maximum number of retries for the node (default: 1)
        wait (int): Wait time in seconds between retries (default: 0)

    Returns:
        A Node instance with the function name as the class name
    """

    def decorator(func):
        class_name = func.__name__
        signature = inspect.signature(func)

        node_class = type(
            class_name,
            (Node,),
            {
                "__init__": lambda self, **kwargs: __init(self, max_retries=max_retries, wait=wait, **kwargs),
                "_input_model": signature_to_input_model(f"{class_name}_input_model", signature),
                "exec": lambda self, prep_res: func(**_deep_materialize(shallow_deserialize(self._input_model(**prep_res)))),
                "prep": create_prep(signature),
                "post": __reduce_shared,
                "__doc__": func.__doc__,
                "__module__": func.__module__,
                "__name__": func.__name__,
            },
        )

        return node_class()

    if func is None:
        return decorator
    else:
        return decorator(func)
