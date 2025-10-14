from agent.providers.settings import ModelInfo

MIL = 1_000_000


def calculate_api_cost_internal(
    model_info: ModelInfo,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    cache_write_cost = (model_info.get("cache_writes_price", 0) / MIL) * cache_creation_input_tokens
    cache_read_cost = (model_info.get("cache_reads_price", 0) / MIL) * cache_read_input_tokens
    base_input_cost = (model_info.get("input_price", 0) / MIL) * input_tokens
    output_cost = (model_info.get("output_price", 0) / MIL) * output_tokens
    total_cost = cache_write_cost + cache_read_cost + base_input_cost + output_cost
    return total_cost


def calculate_api_cost_anthropic(
    model_info: ModelInfo,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    return calculate_api_cost_internal(
        model_info, input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
    )


def calculate_api_cost_openai(
    model_info: ModelInfo,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    non_cached_input_tokens = max(0, input_tokens - cache_creation_input_tokens - cache_read_input_tokens)
    return calculate_api_cost_internal(
        model_info, non_cached_input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
    )


def parse_api_price(price: float | None) -> float | None:
    return price if price * MIL else None
