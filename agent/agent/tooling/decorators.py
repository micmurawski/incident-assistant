import asyncio
import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from inspect import Parameter
from typing import (Annotated, Any, Callable, GenericAlias, Literal, TypedDict,
                    TypeVar, Union, _AnnotatedAlias, _TypedDictMeta)

from agent.types import AnthropicMessage
from framework import AsyncNode
from framework.generic_messages import select_tools_use
from framework.utils import __reduce_shared as reduce_shared

# Mapping from Python types to OpenAPI schema types
CLASS_TO_TYPE = {
    int: "number",
    float: "number",
    str: "string",
    bool: "boolean",
    list: "array",
    set: "array",
    tuple: "array",
    dict: "object",
}

T = TypeVar("T")
type Hidden[T] = T

# Set of Python types considered complex (not simple scalar/object types)
COMPLEX_TYPES = {dict, list, set, tuple}
NoneType = type(None)  # Used for checking Optional types
ToolFormat = Literal["openai", "ollama", "anthropic", "gemini"]


class BaseTool(ABC):
    """
    Abstract base class for all tool wrappers.

    All tools must implement __call__, tags, and tool_definition.
    """
    
    @property
    def name(self) -> str:
        return self.tool_definition["name"]
    
    @abstractmethod
    def __call__(self, *args, **kwargs) -> Any:
        """
        Invoke the tool with arguments.

        This must be implemented by all subclasses.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def tags(self) -> set[str]:
        """
        Return a set of tags describing this tool.

        Used for filtering tools by type or use-case.
        """
        raise NotImplementedError

    @property
    def tool_definition(self) -> dict:
        return self.get_tool_definition()

    @abstractmethod
    def get_tool_definition(self) -> dict:
        """
        Return the metadata for this tool.

        This should include at least name, description, and parameters (schema).
        """
        raise NotImplementedError


def _is_hidden_param(param: Parameter) -> bool:
    """
    Returns True if the parameter is annotated with Hidden[T] (framework-injected, excluded from tool schema).
    """
    ann = getattr(param, "annotation", param)
    if ann is Parameter.empty:
        return False
    return hasattr(ann, "__origin__") and ann.__origin__ == Hidden


def is_typeddict(_type: Any) -> bool:
    """
    Returns True if the given type is a TypedDict.

    TypedDicts are handled as objects with defined properties.
    """
    return isinstance(_type, GenericAlias) and _type.__origin__ == TypedDict


def is_optional(annotation: Any) -> bool:
    """
    Returns True if the annotation describes an Optional type, i.e. Union[..., None].
    """
    return hasattr(annotation, "__origin__") and annotation.__origin__ == Union and NoneType in annotation.__args__


def is_annotated_alias(obj: _AnnotatedAlias | Parameter) -> bool:
    """
    Returns True if the object is a typing.Annotated type hint.
    """
    return isinstance(obj, _AnnotatedAlias)


def is_complex_type(_type: Any) -> bool:
    """
    Returns True if the type is considered complex (dict, list, set, tuple).

    Used to disallow certain complex nested structures as tool parameters.
    """
    return isinstance(_type, tuple(COMPLEX_TYPES))


def process_param(
    param: Parameter | _AnnotatedAlias,
    result: dict | None = None,
    additional_properties: bool = False,
    required: bool = True,
) -> tuple[dict, bool, bool]:
    """
    Convert a parameter annotation to an OpenAPI-style schema property.

    Args:
        param: The parameter's annotation or Parameter object.
        result: The schema dict (iteratively filled).
        additional_properties: If True, allow extra properties (e.g. for **kwargs).
        required: If True, this parameter is required.

    Returns:
        (schema_dict, required_bool, additional_properties_bool)

    Raises:
        Exception: If the parameter type is not supported.
    """
    if result is None:
        result = {}

    # Handle Parameter objects directly
    if isinstance(param, Parameter):
        # If parameter is *args or **kwargs, allow additional properties.
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            additional_properties = True
        return process_param(param.annotation, result, additional_properties, required)

    # Hide parameters wrapped in Hidden[T]
    if hasattr(param, "__origin__") and param.__origin__ == Hidden:
        return None, required, additional_properties
    if is_complex_type(param):
        raise Exception(f"Complex type {param} is not supported")
    elif param in CLASS_TO_TYPE:
        # Map scalar type or built-in class to OpenAPI type
        result["type"] = CLASS_TO_TYPE[param]
    elif is_optional(param):
        # Optionals: mark as not required, get the first non-None type
        required = False
        first_non_none_type = get_first_non_none_type_from_args(param)
        return process_param(first_non_none_type, result, additional_properties, required)
    elif is_annotated_alias(param):
        # Annotated: get description from annotation metadata, continue processing underlying type
        description = get_description_from_annotation_metadata(param)
        if description:
            result["description"] = description
        return process_param(param.__origin__, result, additional_properties, required)
    elif isinstance(param, GenericAlias):
        # Handle generic containers (e.g. list[int], dict[str, X])
        _type = CLASS_TO_TYPE.get(param.__origin__)
        if not _type:
            raise Exception(f"Unsupported GenericAlias {param}")
        result["type"] = _type
        if _type == "array":
            # Array types expect a single item type
            items, _, __ = process_param(param.__args__[0])
            result["items"] = items
        elif _type == "object":
            # Object types may come from dict types
            properties, _, __ = process_param(param.__args__[0])
            result["properties"] = properties
        else:
            raise Exception(f"Unsupported GenericAlias {param}")
    elif isinstance(param, _TypedDictMeta):
        # TypedDict: recursively parse fields as properties
        result = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
            "required": [],
        }
        _additional_properties = False
        for name, _param in param.__annotations__.items():
            prop, _required, _additional = process_param(_param)
            if _additional:
                result["additionalProperties"] = True
            result["properties"][name] = prop
            if _required:
                result["required"].append(name)
        return result, required, additional_properties
    else:
        # Any other types are not supported (e.g. custom class, Union, etc.)
        raise Exception(
            f"Unsupported parameter type {param}",
            type(param),
        )
    return result, required, additional_properties


def get_first_non_none_type_from_args(annotation: _AnnotatedAlias | Parameter) -> Any:
    """
    Given an Optional[...] Union, return the first non-None type argument.

    Raises an exception if there is no non-None type argument.
    """
    if isinstance(annotation, Parameter):
        annotation = annotation.annotation
    result = next((t for t in annotation.__args__ if t is not NoneType), None)
    if result is None:
        raise Exception(f"Annotation {annotation} has no non-none type")
    return result


def get_description_from_annotation_metadata(annotation: _AnnotatedAlias | Parameter) -> str:
    """
    Extract the first description from annotation metadata, if the annotation is Annotated.

    Returns the doc string/description or an empty string.
    """
    if isinstance(annotation, Parameter):
        annotation = annotation.annotation
    metadata = getattr(annotation, "__metadata__", None)
    if metadata and len(metadata) > 0:
        return metadata[0].strip()
    return ""


def add_param_to_required(res: dict, name: str) -> None:
    """
    Adds the given parameter name to the 'required' list in the result dictionary, if applicable.

    Args:
        res: The schema dictionary containing a 'required' key.
        name: The name of the parameter to add.
    """
    if "required" in res and name not in res["required"]:
        res["required"].append(name)


def process_signature(signature: inspect.Signature) -> dict:
    """
    Turn an inspect.Signature into an OpenAPI-style schema dictionary.

    This parses all parameters of a function and generates a JSON schema-style dict for parameters.

    Args:
        signature: Function signature to process.

    Returns:
        OpenAPI-style parameters schema.
    """
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    for name, param in signature.parameters.items():
        result, required, additional_properties = process_param(param)
        if result is None:
            continue
        schema["properties"][name] = result
        if required:
            add_param_to_required(schema, name)
        if additional_properties:
            schema["additionalProperties"] = True
    # Only include "required" if parameters are actually required
    if len(schema["required"]) == 0:
        del schema["required"]
    return schema


def tool(tags: list[str] | None = None):
    """
    Decorator to wrap a function as a BaseTool, attaching tool metadata and parameters schema.

    Args:
        tags: Optional list of string tags to associate with the tool.

    Returns:
        A callable decorator which wraps the function as a tool class instance.
    """

    def decorator(func: Callable[..., Any]) -> BaseTool:
        """
        Wraps the decorated function as a BaseTool subclass with OpenAPI-style metadata.

        Args:
            func: The function to decorate.

        Returns:
            An instance of a dynamically created subclass of BaseTool.
        """
        signature = inspect.signature(func)
        parameters_definition = process_signature(signature)
        inject_params = [
            name for name, param in signature.parameters.items()
            if _is_hidden_param(param)
        ]
        # Create a new subclass of BaseTool on the fly,
        # providing __call__, tool_definition, and tags as class-level attributes.
        tool_class = type(
            func.__name__,
            (BaseTool,),
            {
                "__call__": lambda self, *args, **kwargs: func(*args, **kwargs),
                "__doc__": func.__doc__,
                "_func": func,
                "_inject_params": inject_params,
                "get_tool_definition": lambda self: {
                    "name": func.__name__,
                    "description": (func.__doc__ or "").strip(),
                    "parameters": parameters_definition,
                },
                "tags": set(tags) if tags is not None else set(),
            },
        )
        return tool_class()

    return decorator


@dataclass
class Tools(AsyncNode):
    """
    Collection class for managing multiple tool instances.

    Args:
        tools: List of wrapped BaseTool instances.
    """

    tools: list[BaseTool]

    def __post_init__(self) -> None:
        super().__init__()

    def prep(self, shared: dict) -> dict:
        return shared
    
    def post(self, shared: dict, prep_res: dict, exec_res: dict) -> str:
        return reduce_shared(self, shared, prep_res, exec_res)

    async def prep_async(self, shared: dict) -> dict:
        return self.prep(shared)
    
    async def post_async(self, shared: dict, prep_res: dict, exec_res: dict) -> dict:
        return self.post(shared, prep_res, exec_res)
    
    async def exec_async(self, prep_res: dict) -> dict:
        return await self.exec(prep_res)

    async def exec(self, prep_res: dict) -> dict:
        messages: list[AnthropicMessage] = prep_res.get("messages", [])
        tools_to_call: list[AnthropicMessage] = select_tools_use(messages)

        tool_to_call: AnthropicMessage
        for tool_to_call in tools_to_call:
            name = tool_to_call["name"]
            llm_input = tool_to_call["input"]
            tool_use_id = tool_to_call["id"]
            tool = next((t for t in self.tools if t.name == name), None)
            if tool is None:
                raise Exception(f"Tool {name} not found")

            # Inject Hidden params from shared (convention: param name -> prep_res[key])
            inject_params = getattr(tool, "_inject_params", [])
            injected = {}
            for name in inject_params:
                if name not in prep_res:
                    raise ValueError(
                        f"Tool {tool.name} requires injected param '{name}' "
                        f"(Hidden param). Ensure shared['{name}'] is set when running the flow."
                    )
                injected[name] = prep_res[name]
            final_input = {**injected, **llm_input}
            result = tool(**final_input)
            if asyncio.iscoroutine(result):
                result = await result
            
            print(f"\033[95mResult of: {tool.name}({', '.join(f'{k}={v}' for k, v in llm_input.items())})=\033[0m")
            print(f"\033[95m{result}\033[0m")

            # Anthropic expects tool results in a user message with content blocks
            messages.append(
                AnthropicMessage(
                    role="user",
                    content=[{
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result,
                    }],
                )
            )
            return {"messages": messages}

    def __or__(self, other: "Tools") -> "Tools":
        return Tools(tools=self.tools + other.tools)

    @staticmethod
    def _strip_unsupported_schema_fields(schema: dict) -> dict:
        """
        Recursively strip fields not supported by Gemini function declaration schemas.

        Gemini does not support 'additionalProperties' in parameter schemas.
        """
        # Fields that Gemini does not accept in function declaration schemas
        unsupported = {"additionalProperties"}
        cleaned = {k: v for k, v in schema.items() if k not in unsupported}
        # Recurse into nested schema structures
        if "properties" in cleaned and isinstance(cleaned["properties"], dict):
            cleaned["properties"] = {
                k: Tools._strip_unsupported_schema_fields(v) if isinstance(v, dict) else v
                for k, v in cleaned["properties"].items()
            }
        if "items" in cleaned and isinstance(cleaned["items"], dict):
            cleaned["items"] = Tools._strip_unsupported_schema_fields(cleaned["items"])
        return cleaned

    def tools_definitions(
        self, format: ToolFormat, tags: set[str] | None = None, format_kwargs: dict[str, Any] | None = None
    ) -> list[dict]:
        """
        Return all tool definitions, optionally filtered by tags, with placeholder substitution.

        Args:
            tags: If provided, only definitions whose tags overlap will be included.
            format_kwargs: Optional dictionary for placeholder formatting (e.g. {workspace_name}).

        Returns:
            List of dict tool definitions.
        """
        # Filter the tools by tags (if provided)
        filtered = [t for t in self.tools if tags is None or t.tags & tags]
        definitions = [t.tool_definition for t in filtered]
        if format == "anthropic":
            for definition in definitions:
                definition["input_schema"] = definition.pop("parameters")
        elif format == "ollama":
            for definition in definitions:
                definition["type"] = "function"
                definition["function"] = {
                    "name": definition.pop("name"),
                    "description": definition.pop("description"),
                    "parameters": definition.pop("parameters")
                }
        elif format == "gemini":
            for definition in definitions:
                definition["parameters"] = self._strip_unsupported_schema_fields(
                    definition.get("parameters", {})
                )

        # Substitute formatted placeholders if requested
        if format_kwargs:
            txt = json.dumps(definitions)
            for k, v in format_kwargs.items():
                txt = txt.replace(f"{{{k}}}", v)
            definitions = json.loads(txt)
        return definitions


if __name__ == "__main__":

    @tool(tags=["math"])
    def add(context: Hidden[dict], a: Annotated[int, "This is a"], b: int = 0) -> int:
        """
        Example tool: Adds two numbers together.

        Returns:
            int: The sum of a and b.

        This is doc. You are working in in current workspace {workspace_name}
        """
        return a + b

    # Example usage of tool collection
    tools = Tools(tools=[add])
    print(tools.tools_definitions(
        tags={"not_math"}, format_kwargs={"workspace_name": "Workspace 1"}))
    print(tools.tools_definitions(
        tags={"math"}, format_kwargs={"workspace_name": "Workspace 2"}))
