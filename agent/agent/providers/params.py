import math
from typing import Optional

from agent.providers.settings import (AnthropicReasoningParams, ApiProvider,
                                      ApiProviderSettings,
                                      GeminiReasoningParams, ModelInfo,
                                      OpenAIReasoning)

ANTHROPIC_DEFAULT_MAX_TOKENS = 8192
DEFAULT_HYBRID_REASONING_MODEL_MAX_TOKENS = 16_384
DEFAULT_HYBRID_REASONING_MODEL_THINKING_TOKENS = 8_192
GEMINI_25_PRO_MIN_THINKING_TOKENS = 128


ModelRecord = dict[str, ModelInfo]


def should_use_reasoning_budget(model: ModelInfo, settings: ApiProviderSettings) -> bool:
    """
    Determine if a model should use reasoning budget.
    Returns True if model["required_reasoning_budget"] is set OR
    (model["supports_reasoning_budget"] is set AND settings["enable_reasoning_effort"] is set).
    """
    if model.get("required_reasoning_budget"):
        return True
    if model.get("supports_reasoning_budget") and settings and settings.get("enable_reasoning_effort"):
        return True
    return False


def should_use_reasoning_effort(model: ModelInfo, settings: ApiProviderSettings) -> bool:
    """
    Determine if reasoning effort should be used for this model and settings.
    If settings['enable_reasoning_effort'] is explicitly set to False, return False.
    Otherwise, return True if model or settings indicate reasoning effort should be used.
    """
    if settings and settings.get("enable_reasoning_effort") is False:
        return False

    # Return True if model or settings indicate reasoning effort should be used
    return bool(
        (model.get("supports_reasoning_effort") and settings and settings.get("reasoning_effort"))
        or model.get("reasoning_effort")
    )


def get_model_max_output_tokens(
    model_id: str,
    model: ModelInfo,
    settings: ApiProviderSettings,
    format: ApiProvider,
) -> Optional[int]:
    """
    Get the maximum output tokens for a model, based on the model info, settings, and API format.
    """
    # Check for Claude Code specific max output tokens setting
    if settings and settings.get("api_provider") == "claude-code":
        return settings.get("claude_code_max_output_tokens") or ANTHROPIC_DEFAULT_MAX_TOKENS

    if should_use_reasoning_budget(model, settings):
        return (settings.get("model_max_tokens") if settings else None) or DEFAULT_HYBRID_REASONING_MODEL_MAX_TOKENS

    is_anthropic_context = (
        ("claude" in model_id)
        or (format == "anthropic")
        or (format == "openrouter" and model_id.startswith("anthropic/"))
    )

    # For "Hybrid" reasoning models, discard the model's actual max_tokens for Anthropic contexts
    if model.get("supports_reasoning_budget") and is_anthropic_context:
        return ANTHROPIC_DEFAULT_MAX_TOKENS

    # For Anthropic contexts, always ensure a max_tokens value is set
    max_tokens = model.get("max_tokens")
    context_window = model.get("context_window", 0)

    if is_anthropic_context and (not max_tokens or max_tokens == 0):
        return ANTHROPIC_DEFAULT_MAX_TOKENS

    # If model has explicit max_tokens, clamp it to 20% of the context window
    # Exception: GPT-5 models should use their exact configured max output tokens
    if max_tokens:
        # Check if this is a GPT-5 model (case-insensitive)
        is_gpt5_model = "gpt-5" in model_id.lower()

        # GPT-5 models bypass the 20% cap and use their full configured max tokens
        if is_gpt5_model:
            return max_tokens

        # All other models are clamped to 20% of context window
        return min(max_tokens, math.ceil(context_window * 0.2))

    # For non-Anthropic formats without explicit max_tokens, return None
    if format:
        return None

    # Default fallback
    return ANTHROPIC_DEFAULT_MAX_TOKENS


def get_anthropic_reasoning(
    model: ModelInfo, reasoning_budget: int, settings: ApiProviderSettings
) -> Optional[AnthropicReasoningParams]:
    """
    Returns Anthropic-specific reasoning parameters if applicable.
    """
    if should_use_reasoning_budget(model, settings):
        return {"type": "enabled", "budget_tokens": reasoning_budget}
    return None


def get_openai_reasoning(
    model: ModelInfo, reasoning_effort: str, settings: ApiProviderSettings
) -> Optional[OpenAIReasoning]:
    """
    Returns OpenAI-specific reasoning parameters if applicable.
    """
    if not should_use_reasoning_effort(model, settings):
        return None

    # If model has reasoning effort capability, return object even if effort is undefined
    # This preserves the reasoning_effort field in the API call
    if reasoning_effort == "minimal":
        return None

    return {"reasoning_effort": reasoning_effort}


def get_gemini_reasoning(
    model: ModelInfo, reasoning_budget: int, settings: ApiProviderSettings
) -> Optional[GeminiReasoningParams]:
    """
    Returns Gemini-specific reasoning parameters if applicable.
    """
    if should_use_reasoning_budget(model, settings):
        return {"thinking_budget": reasoning_budget, "include_thoughts": True}
    return None


def get_model_params(
    format: ApiProvider,
    model_id: str,
    model: ModelInfo,
    settings: ApiProviderSettings,
    default_temperature: float = 0,
) -> dict:
    """
    Generate model parameter configuration dict based on the provider, model, and settings.
    """
    # Extract custom values or fallbacks from settings
    settings.get("model_max_tokens") if settings else None
    custom_max_thinking_tokens = settings.get("model_max_thinking_tokens") if settings else None
    custom_temperature = settings.get("model_temperature") if settings else None
    custom_reasoning_effort = settings.get("reasoning_effort") if settings else None
    custom_verbosity = settings.get("verbosity") if settings else None

    # Use centralized logic for max tokens
    max_tokens = get_model_max_output_tokens(
        model_id=model_id,
        model=model,
        settings=settings,
        format=format,
    )

    # Determine temperature
    temperature = custom_temperature if custom_temperature is not None else default_temperature
    reasoning_budget = None
    reasoning_effort = None
    verbosity = custom_verbosity

    # Reasoning Budget logic
    if should_use_reasoning_budget(model, settings):
        is_gemini_25_pro = "gemini-2.5-pro" in model_id
        default_thinking_tokens = (
            GEMINI_25_PRO_MIN_THINKING_TOKENS if is_gemini_25_pro else DEFAULT_HYBRID_REASONING_MODEL_THINKING_TOKENS
        )
        reasoning_budget = (
            custom_max_thinking_tokens if custom_max_thinking_tokens is not None else default_thinking_tokens
        )

        # Reasoning cannot exceed 80% of max_tokens
        if max_tokens is not None and reasoning_budget > int(math.floor(max_tokens * 0.8)):
            reasoning_budget = int(math.floor(max_tokens * 0.8))

        # Reasoning cannot be less than the minimum
        min_thinking_tokens = GEMINI_25_PRO_MIN_THINKING_TOKENS if is_gemini_25_pro else 1024
        if reasoning_budget < min_thinking_tokens:
            reasoning_budget = min_thinking_tokens

        temperature = 1.0

    # Reasoning Effort logic
    elif should_use_reasoning_effort(model, settings):
        # "Traditional" (non-budgeted) reasoning models use the `reasoning_effort` parameter.
        effort = custom_reasoning_effort if custom_reasoning_effort is not None else model.get("reasoning_effort")
        reasoning_effort = effort

    # Compose base params
    params = {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        "reasoning_budget": reasoning_budget,
        "verbosity": verbosity,
    }

    # Provider-specific return dict
    if format == "anthropic":
        result = {"format": format, **params}
        result["reasoning"] = get_anthropic_reasoning(
            model=model,
            reasoning_budget=reasoning_budget,
            # reasoning_effort=reasoning_effort,
            settings=settings,
        )
        return ApiProviderSettings.get_provider_settings_class(api_provider="anthropic", **result)
    elif format == "openai":
        # Special case: o1 and o3-mini do not support temperature
        if model_id.startswith("o1") or model_id.startswith("o3-mini"):
            params["temperature"] = None
        result = {"format": format, **params}
        result["reasoning"] = get_openai_reasoning(
            model=model,
            reasoning_budget=reasoning_budget,
            reasoning_effort=reasoning_effort,
            settings=settings,
        )
        return result
    elif format == "gemini":
        result = {"format": format, **params}
        result["reasoning"] = get_gemini_reasoning(
            model=model,
            reasoning_budget=reasoning_budget,
            # reasoning_effort=reasoning_effort,
            settings=settings,
        )
        return result
    else:
        raise ValueError(f"Unknown format: {format}")
