from typing import Any

from httpx import AsyncClient, Client

from agent.providers.models import OLLAMA_DEFAULT_MODEL_INFO
from agent.providers.settings import ModelInfo

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def parse_ollama_model(model_id: str, raw_model: dict[str, Any]) -> ModelInfo:
    context_key = next((k for k in raw_model["model_info"].keys() if "context_length" in k), None)
    context_window = raw_model["model_info"].get(context_key, None) if context_key else None
    return ModelInfo(
        id=model_id,
        description=f"Family: {raw_model.get('details', {}).get('family', '')}, "
        f"Context: {context_window}, "
        f"Size: {raw_model.get('details', {}).get('parameter_size', '')}",
        context_window=context_window or OLLAMA_DEFAULT_MODEL_INFO["context_window"],
        max_tokens=context_window or OLLAMA_DEFAULT_MODEL_INFO["context_window"],
        supports_images="vision" in raw_model["capabilities"],
        supports_computer_use=False,
        supports_prompt_cache=True,
    )


def fetch_ollama_model(model_id: str, base_url: str = DEFAULT_OLLAMA_BASE_URL) -> ModelInfo:
    """
    Fetch the models from the Ollama API.
    """
    with Client(base_url=base_url) as client:
        response = client.get("/api/tags")
        if response.status_code // 100 == 2:
            model_names = set([model["name"] for model in response.json().get("models", [])])
            if model_id not in model_names:
                raise Exception(f"Model {model_id} not found. Available models: {', '.join(model_names)}")
            response = client.post("/api/show", json={"model": model_id})
            if response.status_code // 100 == 2:
                return parse_ollama_model(model_id, response.json())
            else:
                raise Exception(
                    f"Failed to fetch model {model_id} from Ollama API: {response.status_code} {response.text}"
                )
        else:
            raise Exception(f"Failed to fetch models from Ollama API: {response.status_code} {response.text}")


async def fetch_all_ollama_models(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> dict[str, ModelInfo]:
    """
    Fetch the models from the Ollama API.
    """
    async with AsyncClient(base_url=base_url) as client:
        response = await client.get("/api/tags")
        if response.status_code // 100 == 2:
            model_names = [model["name"] for model in response.json().get("models", [])]
            res: dict[str, ModelInfo] = {}
            for name in model_names:
                response = await client.post("/api/show", json={"model": name})
                if response.status_code // 100 == 2:
                    res[name] = parse_ollama_model(name, response.json())
            return res
        else:
            raise Exception(f"Failed to fetch models from Ollama API: {response.status_code} {response.text}")
