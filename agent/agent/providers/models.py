import math

ANTHROPIC_DEFAULT_MODEL_ID = "claude-sonnet-4-6"
ANTHROPIC_DEFAULT_MAX_TOKENS = 8192

ANTHROPIC_MODELS = {
    "claude-sonnet-4-5": {
        # Overridden to 8k if `enableReasoningEffort` is false.
        "max_tokens": 64_000,
        # Default 200K, extendable to 1M with beta flag 'context-1m-2025-08-07'
        "context_window": 200_000,
        "supports_images": True,
        "supports_computer_use": True,
        "supports_prompt_cache": True,
        # $3 per million input tokens (≤200K context)
        "input_price": 3.0,
        # $15 per million output tokens (≤200K context)
        "output_price": 15.0,
        "cache_writes_price": 3.75,  # $3.75 per million tokens
        "cache_reads_price": 0.3,  # $0.30 per million tokens
        "supports_reasoning_budget": True,
        # Tiered pricing for extended context (requires beta flag 'context-1m-2025-08-07')
        "tiers": [
            {
                "context_window": 1_000_000,  # 1M tokens with beta flag
                # $6 per million input tokens (>200K context)
                "input_price": 6.0,
                # $22.50 per million output tokens (>200K context)
                "output_price": 22.5,
                # $7.50 per million tokens (>200K context)
                "cache_writes_price": 7.5,
                # $0.60 per million tokens (>200K context)
                "cache_reads_price": 0.6,
            },
        ],
    },
    "claude-opus-4-6": {
		"max_tokens": 128_000, 
		"context_window": 200_000, 
		"supports_images": True,
		"supports_prompt_cache": True,
		"input_price": 5.0, 
		"output_price": 25.0, 
		"cache_writes_price": 6.25, 
		"cache_reads_price": 0.5, 
		"supports_reasoning_budget": True,
		"tiers": [
			{
				"context_window": 1_000_000, 
				"input_price": 10.0, 
				"output_price": 37.5, 
				"cache_writes_price": 12.5, 
				"cache_reads_price": 1.0, 
			},
		],
	},
}

GEMINI_DEFAULT_MODEL_ID = "gemini-2.0-flash-001"

GEMINI_MODELS = {
    "gemini-2.5-flash:thinking": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0.30,
        "output_price": 2.5,
        "max_thinking_tokens": 24_576,
        "supports_reasoning_budget": True,
        "required_reasoning_budget": True,
    },
    "gemini-2.5-flash": {
        "max_tokens": 64_000,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 0.3,
        "output_price": 2.5,
        "cache_reads_price": 0.075,
        "cache_writes_price": 1.0,
        "max_thinking_tokens": 24_576,
        "supports_reasoning_budget": True,
    },
    "gemini-2.5-pro": {
        "max_tokens": 64_000,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        # This is the pricing for prompts above 200k tokens.
        "input_price": 2.5,
        "output_price": 15,
        "cache_reads_price": 0.625,
        "cache_writes_price": 4.5,
        "max_thinking_tokens": 32_768,
        "supports_reasoning_budget": True,
        "required_reasoning_budget": True,
        "tiers": [
            {
                "context_window": 200_000,
                "input_price": 1.25,
                "output_price": 10,
                "cache_reads_price": 0.31,
            },
            {
                "context_window": math.inf,
                "input_price": 2.5,
                "output_price": 15,
                "cache_reads_price": 0.625,
            },
        ],
    }
}

OLLAMA_DEFAULT_MODEL_ID = "devstral:24b"

OLLAMA_DEFAULT_MODEL_INFO = {
    "max_tokens": 4096,
    "context_window": 200_000,
    "supports_images": True,
    "supports_computer_use": True,
    "supports_prompt_cache": True,
    "input_price": 0,
    "output_price": 0,
    "cache_writes_price": 0,
    "cache_reads_price": 0,
    "description": "Ollama hosted models",
}

OLLAMA_MODELS = {
    "devstral:24b": OLLAMA_DEFAULT_MODEL_INFO,
}

OPENAI_DEFAULT_MODEL_INFO = {
    "max_tokens": -1,
    "context_window": 128_000,
    "supports_images": True,
    "supports_prompt_cache": False,
    "input_price": 0,
    "output_price": 0,
}
