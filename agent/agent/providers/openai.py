from agent.providers.models import OPENAI_DEFAULT_MODEL_ID, OPENAI_MODELS
from agent.providers.openai_compatible import OpenAICompatibleHandler
from agent.providers.params import get_model_params
from agent.providers.settings import ModelInfo, OpenAISettings


class OpenAIHandler(OpenAICompatibleHandler):
    provider: str = "openai"

    def __init__(self, *args, **kwargs):
        if "base_url" not in kwargs or not kwargs["base_url"]:
            kwargs["base_url"] = "https://api.openai.com/v1"
        # `get_model` reads from ``self.kwargs`` (same pattern as other handlers);
        # ``OpenAICompatibleHandler`` itself only stores ``self.options``, so keep
        # a separate copy for parameter derivation.
        self.kwargs = dict(kwargs)
        super().__init__(*args, **kwargs)

    def get_model(self):
        is_thinking = self.model_id.endswith(":thinking") if self.model_id else False
        _model_id = (
            self.model_id.replace(":thinking", "")
            if is_thinking and self.model_id
            else self.model_id
        )
        model_id = _model_id if _model_id in OPENAI_MODELS else OPENAI_DEFAULT_MODEL_ID
        info = OPENAI_MODELS[model_id]
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
