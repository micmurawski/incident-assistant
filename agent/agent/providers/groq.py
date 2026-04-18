from agent.providers.models import GROQ_DEFAULT_MODEL_ID, GROQ_MODELS
from agent.providers.openai_compatible import OpenAICompatibleHandler
from agent.providers.params import get_model_params
from agent.providers.settings import ModelInfo, OpenAISettings


class GroqHandler(OpenAICompatibleHandler):
    provider: str = "groq"

    def __init__(self, *args, **kwargs):
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.groq.com/openai/v1"
        # `get_model` reads from ``self.kwargs`` (same pattern as OpenAIHandler /
        # OpenRouterHandler); ``OpenAICompatibleHandler`` only stores
        # ``self.options``, so keep a separate copy for parameter derivation.
        self.kwargs = dict(kwargs)
        super().__init__(*args, **kwargs)

    def get_model(self):
        is_thinking = self.model_id.endswith(":thinking")
        _model_id = self.model_id.replace(":thinking", "") if is_thinking else self.model_id
        model_id = _model_id if _model_id in GROQ_MODELS else GROQ_DEFAULT_MODEL_ID
        info = GROQ_MODELS[model_id]
        params: OpenAISettings = get_model_params(
            format="openai", model_id=model_id, model=info, settings=self.kwargs
        )
        if is_thinking and info.get("supports_reasoning_budget"):
            params["reasoning"] = {"type": "enabled", "budget_tokens": self.kwargs.pop("reasoning_budget", 1024)}
        data = {
            "id": model_id.replace(":thinking", "") if model_id.endswith(":thinking") else model_id,
            **info,
            **params,
        }
        return ModelInfo(**data)
