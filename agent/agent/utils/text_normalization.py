NORMALIZATION_MAPS = {
    # Smart quotes to regular quotes
    "SMART_QUOTES": {
        "\u201c": '"',  # Left double quote (U+201C)
        "\u201d": '"',  # Right double quote (U+201D)
        "\u2018": "'",  # Left single quote (U+2018)
        "\u2019": "'",  # Right single quote (U+2019)
    },
    # Other typographic characters
    "TYPOGRAPHIC": {
        "\u2026": "...",  # Ellipsis
        "\u2014": "-",  # Em dash
        "\u2013": "-",  # En dash
        "\u00a0": " ",  # Non-breaking space
    },
}


def normalize_string(
    s: str, smart_quotes: bool = True, typographic_chars: bool = True, extra_whitespace: bool = True, trim: bool = True
) -> str:
    """
    Normalizes a string based on the specified options.

    :param s: The string to normalize
    :param options: NormalizeOptions object or None
    :return: The normalized string
    """
    normalized = s

    # Replace smart quotes
    if smart_quotes:
        for smart, regular in NORMALIZATION_MAPS["SMART_QUOTES"].items():
            normalized = normalized.replace(smart, regular)

    # Replace typographic characters
    if typographic_chars:
        for typographic, regular in NORMALIZATION_MAPS["TYPOGRAPHIC"].items():
            normalized = normalized.replace(typographic, regular)

    # Normalize whitespace
    if extra_whitespace:
        import re

        normalized = re.sub(r"\s+", " ", normalized)

    # Trim whitespace
    if trim:
        normalized = normalized.strip()

    return normalized


def unescape_html_entities(text: str) -> str:
    """
    Unescapes common HTML entities in a string.

    :param text: The string containing HTML entities to unescape
    :return: The unescaped string with HTML entities converted to their literal characters
    """
    if not text:
        return text

    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )
