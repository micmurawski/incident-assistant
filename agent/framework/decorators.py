import inspect
import weakref
from typing import Any, Callable

from pydantic import Field, create_model

from framework import AsyncNode, Node


class _NodeDescriptor:
    """Descriptor so @node on a method gets the owning instance (owner) when exec runs."""

    def __init__(self, node_class: type, is_class_method: bool = False):
        self.node_class = node_class
        self._cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        if obj not in self._cache:
            self._cache[obj] = self.node_class(owner=obj)
        return self._cache[obj]


def signature_to_field_definitions(func_name: str, parameters: dict[str, inspect.Parameter]) -> dict:
    res = {}
    for name, field in parameters.items():
        if field.kind == inspect.Parameter.VAR_POSITIONAL:
            annotation = field.annotation if field.annotation is not inspect._empty else list[Any]
            res[name] = {"type": annotation, "default": []}
            continue
        if field.kind == inspect.Parameter.VAR_KEYWORD:
            annotation = field.annotation if field.annotation is not inspect._empty else dict[str, Any]
            res[name] = {"type": annotation, "default": {}}
            continue
        if field.annotation is inspect._empty:
            raise TypeError(
                f"@node function '{func_name}' parameter '{name}' has no type annotation. "
                f"All parameters must be typed, e.g. def {func_name}({name}: str)."
            )
        res[name] = {
            "type": field.annotation,
            "default": ... if field.default is inspect._empty else field.default,
        }
    return res


def signature_to_input_model(name, signature: inspect.Signature) -> dict:
    return create_model_from_dict(f"{name}_input_model_input", signature_to_field_definitions(name, signature.parameters))


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


def __init(self, **kwargs):
    super(type(self), self).__init__()
    self.max_retries = kwargs.get("max_retries", 1)
    self.wait = kwargs.get("wait", 0)


def create_prep(signature: inspect.Signature) -> Callable[[Node, Any], dict]:
    def prep_inner(self, shared: Any) -> dict:
        res = {}
        for name, field in signature.parameters.items():
            res[name] = shared.get(name)
            if res[name] is None:
                if field.kind == inspect.Parameter.VAR_KEYWORD:
                    res[name] = {}
                elif field.kind == inspect.Parameter.VAR_POSITIONAL:
                    res[name] = []
                elif field.default is not inspect._empty:
                    res[name] = field.default
                else:
                    raise ValueError(f"Parameter {name} has no default value")
        return res

    return prep_inner


def __reduce_shared(self, shared, prep_res, exec_res):
    if isinstance(exec_res, tuple) and len(exec_res) > 1:
        state, action = exec_res
    else:
        state, action = exec_res, "default"

    if state is None:
        return action

    if not isinstance(state, dict):
        raise ValueError(f"Error at {self.__name__}: state must be a dict, got {type(state)}")
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

        # Determine if 'self' is the first parameter (i.e., if the func is a method)
        parameters = list(signature.parameters.values())
        
        is_method = len(parameters) > 0 and parameters[0].name == "self"
        is_class_method = len(parameters) > 0 and parameters[0].name == "cls"
        is_async = inspect.iscoroutinefunction(func)
        
        if is_method or is_class_method:
            parameters = parameters[1:]
            signature = inspect.Signature(parameters)
        input_model = signature_to_input_model(class_name, signature)
        is_method_or_cls = is_method or is_class_method

        def make_node_init(owner_param: bool):
            def node_init(self, owner=None, **kwargs):
                if owner_param:
                    self.owner = owner
                __init(self, max_retries=max_retries, wait=wait, **kwargs)
            return node_init

        if not is_async:
            if is_method_or_cls:
                def exec_sync(self, prep_res):
                    return func(self.owner, **input_model(**prep_res).model_dump())
                node_class = type(
                    class_name,
                    (Node,),
                    {
                        "__init__": make_node_init(True),
                        "exec": exec_sync,
                        "prep": create_prep(signature),
                        "post": __reduce_shared,
                        "__doc__": func.__doc__,
                        "__module__": func.__module__,
                        "__name__": func.__name__,
                    },
                )
                return _NodeDescriptor(node_class)
            node_class = type(
                class_name,
                (Node,),
                {
                    "__init__": make_node_init(False),
                    "exec": lambda self, prep_res: func(**input_model(**prep_res).model_dump()),
                    "prep": create_prep(signature),
                    "post": __reduce_shared,
                    "__doc__": func.__doc__,
                    "__module__": func.__module__,
                    "__name__": func.__name__,
                },
            )
            return node_class()
        else:
            async def exec_async(self, prep_res):
                if is_method_or_cls:
                    return await func(self.owner, **input_model(**prep_res).model_dump())
                return await func(**input_model(**prep_res).model_dump())

            async def post(self, shared, prep_res, exec_res):
                return __reduce_shared(self, shared, prep_res, exec_res)

            async def prep(self, shared):
                return create_prep(signature)(self, shared)

            if is_method_or_cls:
                node_class = type(
                    class_name,
                    (AsyncNode,),
                    {
                        "__init__": make_node_init(True),
                        "exec_async": exec_async,
                        "prep_async": prep,
                        "post_async": post,
                        "__doc__": func.__doc__,
                        "__module__": func.__module__,
                        "__name__": func.__name__,
                    },
                )
                return _NodeDescriptor(node_class)
            node_class = type(
                class_name,
                (AsyncNode,),
                {
                    "__init__": make_node_init(False),
                    "exec_async": exec_async,
                    "prep_async": prep,
                    "post_async": post,
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

@node
async def noop_async(messages: list[dict]):
    return {"messages": messages}

@node
def noop(messages: list[dict]):
    return {"messages": messages}
