from typing import TypedDict, Literal, Any
from anthropic.types.thinking_config_param import ThinkingConfigParam
from openai.types.shared_params.reasoning import Reasoning as OpenAIReasoning
from google.genai.types import GenerateContentConfig


class OpenAiReasoningParam(TypedDict):
    reasoning_effort: OpenAIReasoning["reasoning_effort"]


class GeminiReasoningParams(TypedDict, total=False):
    include_thoughts: bool | None
    thinking_budget: int | None


AnthropicReasoningParams = ThinkingConfigParam
ApiProvider = Literal["anthropic", "openai", "gemini", "ollama"]


class ModelInfo(TypedDict, total=False):
    max_tokens: int
    context_window: int
    supports_prompt_cache: bool
    max_cache_points: int
    min_tokens_per_cache_point: int
    cachable_fields: list[Literal["system", "messages", "tools"]]


class BaseProviderSettings(TypedDict, total=False):
    include_max_tokens: bool | None
    diff_enabled: bool | None
    todo_list_enabled: bool | None
    fuzzy_match_threshold: int | None
    model_temperature: int | None
    rate_limit_seconds: int | None
    consecutive_mistake_limit: int | None
    enable_reasoning_effort: bool | None
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None
    model_max_tokens: int | None
    model_max_thinking_tokens: int | None
    verbosity: Literal["default", "low", "high"] | None


class ApiModelIdProviderSettings(BaseProviderSettings):
    api_model_id: str | None


class AnthropicSettings(ApiModelIdProviderSettings):
    api_ey: str
    anthropic_base_url: str
    anthropic_use_auth_token: bool
    anthropic_beta_1m_context: bool


class ModelInfo(TypedDict, total=False):
    max_tokens: int | None


class OpenAISettings(ApiModelIdProviderSettings):
    open_ai_base_url: str
    open_ai_api_key: str
    open_ai_legacy_format: bool
    open_ai_r1_format_enabled: bool
    open_ai_model_id: str
    open_ai_custom_model_info: ModelInfo | None
    open_ai_use_azure: bool
    azure_api_version: str
    open_ai_streaming_enabled: bool
    open_ai_host_header: str
    open_ai_headers: dict[str, str]
    open_ai_reasoning_effort: str | None


class OllamaSettings(ApiModelIdProviderSettings):
    ollama_model_id: str | None
    ollama_base_url: str | None
    ollama_api_key: str | None
    ollama_num_ctx: int | None


class GeminiSettings(ApiModelIdProviderSettings):
    gemini_api_key: str | None
    google_gemini_base_url: str | None
    enable_url_context: bool | None
    enable_grounding: bool | None


PROVIDER_SETTINGS_CLASSES = {
    "anthropic": AnthropicSettings,
    "openai": OpenAISettings,
    "ollama": OllamaSettings,
    "gemini": GeminiSettings,
}


class ApiProviderSettings(TypedDict, total=False):
    id: str
    api_provider: ApiProvider

    @classmethod
    def get_provider_settings_class(
        cls, api_provider: ApiProvider, **data: dict[str, Any]
    ) -> AnthropicSettings | OpenAISettings | OllamaSettings | GeminiSettings:
        if api_provider not in PROVIDER_SETTINGS_CLASSES:
            raise ValueError(f"Unknown api_provider: {api_provider}")
        cls = PROVIDER_SETTINGS_CLASSES[api_provider]
        allowed_fields = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in allowed_fields}
        return cls(api_provider=api_provider, **filtered)
