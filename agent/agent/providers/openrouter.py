from agent.providers.models import (OPENROUTER_DEFAULT_MODEL_ID,
                                    OPENROUTER_MODELS)
from agent.providers.openai_compatible import OpenAICompatibleHandler
from agent.providers.params import get_model_params
from agent.providers.settings import ModelInfo, OpenAISettings


class OpenRouterHandler(OpenAICompatibleHandler):
    provider: str = "openrouter"

    def __init__(self, *args, **kwargs):
        if "base_url" not in kwargs or not kwargs["base_url"]:
            kwargs["base_url"] = "https://openrouter.ai/api/v1"
        # Same pattern as OpenAIHandler: keep kwargs for get_model() parameter
        # derivation, since OpenAICompatibleHandler only stashes ``self.options``.
        self.kwargs = dict(kwargs)
        super().__init__(*args, **kwargs)

    def get_model(self):
        is_thinking = self.model_id.endswith(":thinking") if self.model_id else False
        _model_id = (
            self.model_id.replace(":thinking", "")
            if is_thinking and self.model_id
            else self.model_id
        )
        model_id = _model_id if _model_id in OPENROUTER_MODELS else OPENROUTER_DEFAULT_MODEL_ID
        info = OPENROUTER_MODELS[model_id]
        params: OpenAISettings = get_model_params(
            format="openai", model_id=model_id, model=info, settings=self.kwargs
        )
        if is_thinking and info.get("supports_reasoning_budget"):
            params["reasoning"] = {
                "type": "enabled",
                "budget_tokens": self.kwargs.pop("reasoning_budget", 1024),
            }
        data = {
            "id": model_id,
            **info,
            **params,
        }
        return ModelInfo(**data)
