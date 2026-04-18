import asyncio
import inspect
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from inspect import Parameter
from typing import (Annotated, Any, Callable, Coroutine, GenericAlias, Literal,
                    Optional, TypedDict, TypeVar, Union, _AnnotatedAlias,
                    _TypedDictMeta, get_args, get_origin)

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

MAX_OUTPUT_LENGTH = 8000
MAX_ERROR_LENGTH = 2000


@dataclass
class ToolResult:
    result: Any
    error: Optional[str] = None
    max_result_length: int = MAX_OUTPUT_LENGTH
    max_error_length: int = MAX_ERROR_LENGTH
    trim_result: bool = True

    def __post_init__(self):
        if self.trim_result:
            self._trim_result()

    def _trim_result(self) -> None:
        if isinstance(self.result, str) and len(self.result) > self.max_result_length:
            total_length = len(self.result)
            head = self.result[: self.max_result_length // 2]
            tail = self.result[-self.max_result_length // 2:]
            self.result = f"{head}\n...[trimmed {total_length - self.max_result_length} characters, use different tool ranges to get more data]...\n{tail}"
        if self.error and len(self.error) > self.max_error_length:
            total_length = len(self.error)
            head_len = int(self.max_error_length * 0.8)
            self.error = self.error[:head_len] + \
                f"\n...[trimmed {total_length - head_len} characters of stderr, use different tool ranges to get more data]..."

    @property
    def is_success(self) -> bool:
        return self.error is None


class BaseTool(ABC):
    """
    Abstract base class for all tool wrappers.

    All tools must implement __call__, tags, and tool_definition.
    """

    @property
    def name(self) -> str:
        return self.tool_definition["name"]

    @abstractmethod
    def __call__(self, *args, **kwargs) -> ToolResult:
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


def is_literal(annotation: Any) -> bool:
    """
    Returns True if the annotation is a typing.Literal.
    """
    return hasattr(annotation, "__origin__") and annotation.__origin__ == Literal


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
    elif is_literal(param):
        # Literals are represented as enums in the schema
        literal_values = getattr(param, "__args__", ())
        if not literal_values:
            raise Exception(f"Literal {param} has no values")
        first_value = next((v for v in literal_values if v is not None), None)
        if first_value is None:
            raise Exception(f"Literal {param} has only None values")
        value_type = type(first_value)
        result["type"] = CLASS_TO_TYPE.get(value_type, "string")
        result["enum"] = list(literal_values)
        return result, required, additional_properties
    elif is_annotated_alias(param):
        # Annotated: get description from annotation metadata, continue processing underlying type
        description = get_description_from_annotation_metadata(param)
        if description:
            result["description"] = description
        return process_param(param.__origin__, result, additional_properties, required)
    elif (origin := get_origin(param)) is not None and origin in CLASS_TO_TYPE:
        # Handle generic containers (list[X], List[X], dict[K,V], etc.) via get_origin/get_args
        # so we support both types.GenericAlias (list[int]) and typing._GenericAlias (List[Literal[...]])
        args = get_args(param)
        _type = CLASS_TO_TYPE[origin]
        result["type"] = _type
        if _type == "array":
            # Array types expect a single item type (e.g. List[Literal[...]], list[str])
            if args:
                items, _, __ = process_param(args[0])
                result["items"] = items
            else:
                result["items"] = {"type": "string"}
        elif _type == "object":
            if len(args) >= 2:
                value_schema, _, __ = process_param(args[1])
                result["additionalProperties"] = value_schema
            else:
                result["additionalProperties"] = True
        return result, required, additional_properties
    elif isinstance(param, GenericAlias):
        # Fallback for GenericAlias not matched by get_origin (e.g. same as above for older runtimes)
        _type = CLASS_TO_TYPE.get(param.__origin__)
        if not _type:
            raise Exception(f"Unsupported GenericAlias {param}")
        result["type"] = _type
        if _type == "array":
            if param.__args__:
                items, _, __ = process_param(param.__args__[0])
                result["items"] = items
            else:
                result["items"] = {"type": "string"}
        elif _type == "object":
            if len(param.__args__) >= 2:
                value_schema, _, __ = process_param(param.__args__[1])
                result["additionalProperties"] = value_schema
            else:
                result["additionalProperties"] = True
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
    debug_mode: bool = True

    def pick_tool_by_name(self, name: str) -> BaseTool:
        tool = next((t for t in self.tools if t.name == name), None)
        if tool is None:
            raise Exception(f"Tool {name} not found")
        return tool

    def set_debug_mode(self, debug_mode: bool = True) -> None:
        self.debug_mode = debug_mode

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

    @staticmethod
    def _missing_required_fields(tool: BaseTool, llm_input: dict[str, Any]) -> list[str]:
        """
        Return required LLM-visible fields missing from the agent's tool input.

        Hidden[...] / injected parameters are supplied by the framework (prep_res), not the model;
        they are excluded from the schema and must not be treated as agent omissions here.
        """
        inject_names = set(getattr(tool, "_inject_params", []))
        params = tool.tool_definition.get("parameters", {})
        required = params.get("required", [])
        if not isinstance(required, list):
            return []
        return [
            field
            for field in required
            if field not in llm_input and field not in inject_names
        ]

    async def exec(self, prep_res: dict) -> dict:
        messages: list[AnthropicMessage] = prep_res.get("messages", [])
        _messages_len_before_tools = len(messages)
        tools_to_call: list[AnthropicMessage] = select_tools_use(messages)

        tool_to_call: AnthropicMessage
        for tool_to_call in tools_to_call:
            name = tool_to_call["name"]
            llm_input = tool_to_call["input"]
            tool_use_id = tool_to_call["id"]
            tool = next((t for t in self.tools if t.name == name), None)
            if tool is None:
                tool_result = ToolResult(
                    result=None,
                    error=f"Tool {name} not found",
                )
                if tool_result.error:
                    print(f"Tool result error: {tool_result.error}")
                if self.debug_mode:
                    print(
                        f"\033[95mResult of: {name}({', '.join(f'{k}={v}' for k, v in llm_input.items())})=\033[0m"
                    )
                    print(f"\033[95m{tool_result.result}\033[0m")
                    if tool_result.error:
                        print(f"\033[91mError: {tool_result.error}\033[0m")
                messages.append(
                    AnthropicMessage(
                        role="user",
                        content=[
                            dict(
                                type="tool_result",
                                tool_use_id=tool_use_id,
                                content=tool_result.result
                                if tool_result.is_success
                                else tool_result.error,
                                is_error=not tool_result.is_success,
                            )
                        ],
                    )
                )
                continue

            tool_result: ToolResult | Coroutine[Any, Any, ToolResult]
            # Hidden params: framework must supply via prep_res; failure is not recoverable by the agent.
            inject_params = getattr(tool, "_inject_params", [])
            runtime_injected = {
                "tool_use_id": tool_use_id,
                "tool_name": name,
                "tool_input": llm_input,
            }
            injected = {}
            missing_injected = [
                param_name
                for param_name in inject_params
                if param_name not in prep_res and param_name not in runtime_injected
            ]
            if missing_injected:
                raise Exception(
                    f"Tool {tool.name} is missing required injected fields: "
                    f"{', '.join(missing_injected)}"
                )
            for param_name in inject_params:
                if param_name in prep_res:
                    injected[param_name] = prep_res[param_name]
                else:
                    injected[param_name] = runtime_injected[param_name]

            # Non-hidden required schema fields: agent omission → ToolResult error for the model to fix.
            missing_required = self._missing_required_fields(tool, llm_input)
            if missing_required:
                tool_result = ToolResult(
                    result=None,
                    error=(
                        f"Tool {tool.name} is missing required input fields: "
                        f"{', '.join(missing_required)}"
                    ),
                )
            else:
                final_input = {**injected, **llm_input}
                try:
                    tool_result = tool(**final_input)
                    if asyncio.iscoroutine(tool_result):
                        tool_result = await tool_result
                except TypeError as e:
                    # Convert runtime signature mismatch to tool error for LLM feedback loops.
                    print(f"Invalid tool input for {tool.name}: {e}")
                    tool_result = ToolResult(
                        result=None,
                        error=f"Invalid tool input for {tool.name}: {e}",
                    )
            if tool_result.error:
                print(f"Tool result error: {tool_result.error}")

            if self.debug_mode:
                print(f"\033[95mResult of: {tool.name}({', '.join(f'{k}={v}' for k, v in llm_input.items())})=\033[0m")
                print(f"\033[95m{tool_result.result}\033[0m")
                if tool_result.error:
                    print(f"\033[91mError: {tool_result.error}\033[0m")

            # Anthropic expects tool results in a user message with content blocks
            messages.append(
                AnthropicMessage(
                    role="user",
                    content=[
                        dict(
                            type="tool_result",
                            tool_use_id=tool_use_id,
                            content=tool_result.result if tool_result.is_success else tool_result.error,
                            is_error=not tool_result.is_success,
                        )
                    ]
                )
            )
        task = prep_res.get("task")
        if task is not None and len(messages) > _messages_len_before_tools:
            task.messages_history.extend(messages[_messages_len_before_tools:])
        return {"messages": messages}

    def __or__(self, other: "Tools | BaseTool") -> "Tools":
        if isinstance(other, BaseTool):
            deduplicated_tools = list(set(self.tools + [other]))
            return Tools(tools=deduplicated_tools)
        deduplicated_tools = list(set(self.tools + other.tools))
        return Tools(tools=deduplicated_tools)

    def select(self, tags: set[str]) -> "Tools":
        return Tools(tools=[t for t in self.tools if tags.issubset(t.tags)])

    def pop(self, name: str) -> BaseTool:
        tool = next((t for t in self.tools if t.name == name), None)
        if tool is None:
            raise Exception(f"Tool {name} not found")
        self.tools.remove(tool)
        return tool

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
        # Tool definition schema adjustment based on format
        if format in ["anthropic", "minimax"]:
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
        elif format in["openai", "openrouter", "groq", "ovh"]:
            # For OpenAI, must produce a list of objects with 'type': 'function' and a 'function' field.
            for i, definition in enumerate(definitions):
                # Create a copy to avoid side-effects in case tool_definition is reused elsewhere
                name = definition.get("name")
                description = definition.get("description")
                parameters = definition.get("parameters")
                definitions[i] = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                }
        else:
            raise ValueError(f"Unknown format: {format}")

        # Substitute formatted placeholders if requested
        if format_kwargs is None:
            format_kwargs = {}

        txt = json.dumps(definitions)
        to_replace = set(re.findall(r"\{(\w+)\}", txt))
        remaining_to_replace = to_replace.copy()
        for k in to_replace:
            v = format_kwargs.get(k, None)
            if v is None:
                continue
            txt = txt.replace(f"{{{k}}}", v)
            remaining_to_replace.remove(k)
        # After replacements, check if any unreplaced placeholders remain
        if remaining_to_replace:
            raise ValueError(f"Unresolved placeholders in tool definitions: {remaining_to_replace}")
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
