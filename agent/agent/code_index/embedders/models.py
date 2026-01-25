
EMBEDDING_MODEL_PROFILES = {
    "ollama": {
        "nomic-embed-text": {"dimension": 768, "scoreThreshold": 0.4},
        "nomic-embed-code": {
            "dimension": 3584,
            "score_threshold": 0.15,
            "query_prefix": "Represent this query for searching relevant code: ",
        },
        "manutic/nomic-embed-code": {
            "dimension": 3584,
            "score_threshold": 0.15,
            "query_prefix": "Represent this query for searching relevant code: ",
        },
        "mxbai-embed-large": {"dimension": 1024, "scoreThreshold": 0.4},
        "all-minilm": {"dimension": 384, "scoreThreshold": 0.4},
    },
    "openai": {
        "text-embedding-3-small": {"dimension": 1536, "scoreThreshold": 0.4},
        "text-embedding-3-large": {"dimension": 3072, "scoreThreshold": 0.4},
        "text-embedding-ada-002": {"dimension": 1536, "scoreThreshold": 0.4},
    },
    "gemini": {
        "text-embedding-004": {"dimension": 768},
        "gemini-embedding-001": {"dimension": 3072, "scoreThreshold": 0.4},
    },
    "openai-compatible": {
        "text-embedding-3-small": {"dimension": 1536, "scoreThreshold": 0.4},
        "text-embedding-3-large": {"dimension": 3072, "scoreThreshold": 0.4},
        "text-embedding-ada-002": {"dimension": 1536, "scoreThreshold": 0.4},
        "nomic-embed-code": {
            "dimension": 3584,
            "scoreThreshold": 0.15,
            "queryPrefix": "Represent this query for searching relevant code: ",
        },
    },
}


def get_model_query_prefix(provider: str, model: str) -> str | None:
    profiles = EMBEDDING_MODEL_PROFILES.get(provider)
    if not profiles:
        return ""
    return profiles.get(model, {}).get("query_prefix")


def get_model_dimension(provider: str, model: str) -> int:
    profiles = EMBEDDING_MODEL_PROFILES.get(provider)
    if not profiles:
        raise Exception(f"Unknown model: {model} for provider: {provider}")
    dimension = profiles.get(model, {}).get("dimension")
    if not dimension:
        raise Exception(f"Unknown dimension for model: {model} for provider: {provider}")
    return dimension
