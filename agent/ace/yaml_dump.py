"""YAML serialization with readable multiline strings (literal block scalars)."""

from __future__ import annotations

from typing import Any

import yaml


class BlockStr(str):
    """Marker for strings that must serialize as YAML literal blocks (``|``)."""


class MultilineYamlDumper(yaml.SafeDumper):
    """Like :class:`yaml.SafeDumper`, but honors ``|`` / ``>`` even when PyYAML would disallow block style.

    PyYAML's :meth:`Emitter.choose_scalar_style` refuses literal blocks when
    ``analysis.allow_block`` is false (e.g. space before newline, trailing spaces, some
    punctuation). That breaks ``read_file`` tool output. We still emit ``|`` when the
    representer asked for it.
    """

    def choose_scalar_style(self):
        if self.analysis is None:
            self.analysis = self.analyze_scalar(self.event.value)
        style = getattr(self.event, "style", None)
        if style in ("|", ">"):
            return style
        return super().choose_scalar_style()


def _represent_block_str(dumper: yaml.SafeDumper, data: BlockStr):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


def _represent_str(dumper: yaml.SafeDumper, data: str):
    if "\n" in data or "\r" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


MultilineYamlDumper.add_representer(BlockStr, _represent_block_str)
MultilineYamlDumper.add_representer(str, _represent_str)


def _promote_multiline_strings(obj: Any) -> Any:
    if isinstance(obj, BlockStr):
        return obj
    if isinstance(obj, dict):
        return {k: _promote_multiline_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_promote_multiline_strings(x) for x in obj]
    if isinstance(obj, str) and ("\n" in obj or "\r" in obj):
        return BlockStr(obj)
    return obj


def dump_yaml_multiline(data, *, indent: int = 4, sort_keys: bool = False) -> str:
    return yaml.dump(
        _promote_multiline_strings(data),
        indent=indent,
        sort_keys=sort_keys,
        Dumper=MultilineYamlDumper,
        allow_unicode=True,
        width=4096,
    )
