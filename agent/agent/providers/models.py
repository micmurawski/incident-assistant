import math

ANTHROPIC_DEFAULT_MODEL_ID = "claude-sonnet-4-20250514"
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
    "claude-sonnet-4-20250514": {
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
    "claude-opus-4-1-20250805": {
        "max_tokens": 8192,
        "context_window": 200_000,
        "supports_images": True,
        "supports_computer_use": True,
        "supports_prompt_cache": True,
        "input_price": 15.0,  # $15 per million input tokens
        "output_price": 75.0,  # $75 per million output tokens
        "cache_writes_price": 18.75,  # $18.75 per million tokens
        "cache_reads_price": 1.5,  # $1.50 per million tokens
        "supports_reasoning_budget": True,
    },
    "claude-opus-4-20250514": {
        # Overridden to 8k if `enableReasoningEffort` is false.
        "max_tokens": 32_000,
        "context_window": 200_000,
        "supports_images": True,
        "supports_computer_use": True,
        "supports_prompt_cache": True,
        "input_price": 15.0,  # $15 per million input tokens
        "output_price": 75.0,  # $75 per million output tokens
        "cache_writes_price": 18.75,  # $18.75 per million tokens
        "cache_reads_price": 1.5,  # $1.50 per million tokens
        "supports_reasoning_budget": True,
    },
    "claude-3-7-sonnet-20250219:thinking": {
        # Unlocked by passing `beta` flag to the model. Otherwise, it's 64k.
        "max_tokens": 128_000,
        "context_window": 200_000,
        "supports_images": True,
        "supports_computer_use": True,
        "supports_prompt_cache": True,
        "input_price": 3.0,  # $3 per million input tokens
        "output_price": 15.0,  # $15 per million output tokens
        "cache_writes_price": 3.75,  # $3.75 per million tokens
        "cache_reads_price": 0.3,  # $0.30 per million tokens
        "supports_reasoning_budget": True,
        "required_reasoning_budget": True,
    },
    "claude-3-7-sonnet-20250219": {
        # Since we already have a `:thinking` virtual model we aren't setting `supportsReasoningBudget: True` here.
        "max_tokens": 8192,
        "context_window": 200_000,
        "supports_images": True,
        "supports_computer_use": True,
        "supports_prompt_cache": True,
        "input_price": 3.0,  # $3 per million input tokens
        "output_price": 15.0,  # $15 per million output tokens
        "cache_writes_price": 3.75,  # $3.75 per million tokens
        "cache_reads_price": 0.3,  # $0.30 per million tokens
    },
    "claude-3-5-sonnet-20241022": {
        "max_tokens": 8192,
        "context_window": 200_000,
        "supports_images": True,
        "supports_computer_use": True,
        "supports_prompt_cache": True,
        "input_price": 3.0,  # $3 per million input tokens
        "output_price": 15.0,  # $15 per million output tokens
        "cache_writes_price": 3.75,  # $3.75 per million tokens
        "cache_reads_price": 0.3,  # $0.30 per million tokens
    },
    "claude-3-5-haiku-20241022": {
        "max_tokens": 8192,
        "context_window": 200_000,
        "supports_images": False,
        "supports_prompt_cache": True,
        "input_price": 1.0,
        "output_price": 5.0,
        "cache_writes_price": 1.25,
        "cache_reads_price": 0.1,
    },
    "claude-3-opus-20240229": {
        "max_tokens": 4096,
        "context_window": 200_000,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 15.0,
        "output_price": 75.0,
        "cache_writes_price": 18.75,
        "cache_reads_price": 1.5,
    },
    "claude-3-haiku-20240307": {
        "max_tokens": 4096,
        "context_window": 200_000,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 0.25,
        "output_price": 1.25,
        "cache_writes_price": 0.3,
        "cache_reads_price": 0.03,
    },
}

GEMINI_DEFAULT_MODEL_ID = "gemini-2.0-flash-001"

GEMINI_MODELS = {
    "gemini-2.5-flash-preview-04-17:thinking": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0.15,
        "output_price": 3.5,
        "max_thinking_tokens": 24_576,
        "supports_reasoning_budget": True,
        "required_reasoning_budget": True,
    },
    "gemini-2.5-flash-preview-04-17": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0.15,
        "output_price": 0.6,
    },
    "gemini-2.5-flash-preview-05-20:thinking": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 0.15,
        "output_price": 3.5,
        "cache_reads_price": 0.0375,
        "cache_writes_price": 1.0,
        "max_thinking_tokens": 24_576,
        "supports_reasoning_budget": True,
        "required_reasoning_budget": True,
    },
    "gemini-2.5-flash-preview-05-20": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 0.15,
        "output_price": 0.6,
        "cache_reads_price": 0.0375,
        "cache_writes_price": 1.0,
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
    "gemini-2.5-pro-exp-03-25": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-2.5-pro-preview-03-25": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        # This is the pricing for prompts above 200k tokens.
        "input_price": 2.5,
        "output_price": 15,
        "cache_reads_price": 0.625,
        "cache_writes_price": 4.5,
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
    },
    "gemini-2.5-pro-preview-05-06": {
        "max_tokens": 65_535,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        # This is the pricing for prompts above 200k tokens.
        "input_price": 2.5,
        "output_price": 15,
        "cache_reads_price": 0.625,
        "cache_writes_price": 4.5,
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
    },
    "gemini-2.5-pro-preview-06-05": {
        "max_tokens": 65_535,
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
    },
    "gemini-2.0-flash-001": {
        "max_tokens": 8192,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 0.1,
        "output_price": 0.4,
        "cache_reads_price": 0.025,
        "cache_writes_price": 1.0,
    },
    "gemini-2.0-flash-lite-preview-02-05": {
        "max_tokens": 8192,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-2.0-pro-exp-02-05": {
        "max_tokens": 8192,
        "context_window": 2_097_152,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-2.0-flash-thinking-exp-01-21": {
        "max_tokens": 65_536,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-2.0-flash-thinking-exp-1219": {
        "max_tokens": 8192,
        "context_window": 32_767,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-2.0-flash-exp": {
        "max_tokens": 8192,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-1.5-flash-002": {
        "max_tokens": 8192,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        # This is the pricing for prompts above 128k tokens.
        "input_price": 0.15,
        "output_price": 0.6,
        "cache_reads_price": 0.0375,
        "cache_writes_price": 1.0,
        "tiers": [
            {
                "context_window": 128_000,
                "input_price": 0.075,
                "output_price": 0.3,
                "cache_reads_price": 0.01875,
            },
            {
                "context_window": math.inf,
                "input_price": 0.15,
                "output_price": 0.6,
                "cache_reads_price": 0.0375,
            },
        ],
    },
    "gemini-1.5-flash-exp-0827": {
        "max_tokens": 8192,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-1.5-flash-8b-exp-0827": {
        "max_tokens": 8192,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-1.5-pro-002": {
        "max_tokens": 8192,
        "context_window": 2_097_152,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-1.5-pro-exp-0827": {
        "max_tokens": 8192,
        "context_window": 2_097_152,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-exp-1206": {
        "max_tokens": 8192,
        "context_window": 2_097_152,
        "supports_images": True,
        "supports_prompt_cache": False,
        "input_price": 0,
        "output_price": 0,
    },
    "gemini-2.5-flash-lite-preview-06-17": {
        "max_tokens": 64_000,
        "context_window": 1_048_576,
        "supports_images": True,
        "supports_prompt_cache": True,
        "input_price": 0.1,
        "output_price": 0.4,
        "cache_reads_price": 0.025,
        "cache_writes_price": 1.0,
        "supports_reasoning_budget": True,
        "max_thinking_tokens": 24_576,
    },
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
