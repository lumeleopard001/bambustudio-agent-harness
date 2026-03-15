"""BambuStudio BBS INI-style config parser.

BBS config files use a simple key = value format without sections.
Comments start with #, blank lines are ignored.
Multi-value keys use ; as separator (e.g., "filament_colour = #FFFFFF;#000000").
"""

from __future__ import annotations


def parse_config(text: str) -> dict[str, str]:
    """Parse a BBS INI-style config string into a dictionary.

    Args:
        text: Raw config file content.

    Returns:
        Dictionary of key-value pairs. Values are kept as strings;
        multi-value entries retain their ; separators.
    """
    config: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Split on first '=' only
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        config[key.strip()] = value.strip()
    return config


def serialize_config(config: dict[str, str]) -> str:
    """Serialize a dictionary back to BBS INI-style config format.

    Args:
        config: Dictionary of key-value pairs.

    Returns:
        Config file content string with trailing newline.
    """
    lines: list[str] = []
    for key, value in config.items():
        lines.append(f"{key} = {value}")
    # Trailing newline for POSIX compatibility
    if lines:
        lines.append("")
    return "\n".join(lines)


def parse_multi_value(value: str) -> list[str]:
    """Split a ;-separated multi-value config entry.

    Args:
        value: Raw value string, e.g. "#FFFFFF;#000000;#FF0000".

    Returns:
        List of individual values.
    """
    return [v.strip() for v in value.split(";") if v.strip()]


def join_multi_value(values: list[str]) -> str:
    """Join a list of values into a ;-separated config entry.

    Args:
        values: List of individual value strings.

    Returns:
        Joined string with ; separators.
    """
    return ";".join(values)
