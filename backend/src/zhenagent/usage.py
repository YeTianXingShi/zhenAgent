def token_count(value) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def total_tokens(usage) -> int | None:
    """只使用服务返回的统计；缓存与推理细分已包含在输入和输出中。"""
    if not isinstance(usage, dict):
        return None
    total = token_count(usage.get("total_tokens"))
    if total is not None:
        return total
    input_tokens = token_count(usage.get("input_tokens"))
    output_tokens = token_count(usage.get("output_tokens"))
    if input_tokens is not None and output_tokens is not None:
        return input_tokens + output_tokens
    return None
