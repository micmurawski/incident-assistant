from agent.providers._anthropic import AnthropicHandler
from agent.providers.models import MINIMAX_DEFAULT_MODEL_ID, MINIMAX_MODELS
from agent.providers.params import get_model_params
from agent.providers.settings import AnthropicSettings, ModelInfo


class MiniMaxHandler(AnthropicHandler):
    provider: str = "minimax"

    def __init__(self, *args, **kwargs):
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.minimax.io/anthropic"
        super().__init__(*args, **kwargs)

    def get_model(self):
        is_thinking = self.model_id.endswith(":thinking")
        _model_id = self.model_id.replace(":thinking", "") if is_thinking else self.model_id
        model_id = _model_id if _model_id in MINIMAX_MODELS else MINIMAX_DEFAULT_MODEL_ID
        info = MINIMAX_MODELS[model_id]
        params: AnthropicSettings = get_model_params(
            format="anthropic", model_id=model_id, model=info, settings=self.kwargs
        )
        if is_thinking and info.get("supports_reasoning_budget"):
            params["reasoning"] = {"type": "enabled", "budget_tokens": self.kwargs.pop("reasoning_budget", 1024)}
        data = {
            "id": model_id.replace(":thinking", "") if model_id.endswith(":thinking") else model_id,
            **info,
            **params,
        }
        return ModelInfo(**data)
