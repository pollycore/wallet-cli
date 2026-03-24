"""Debug formatting helpers for CLI payload output."""

from __future__ import annotations

import json
import re
import textwrap

import yaml
from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text


DEBUG_CONSOLE = Console()
DEBUG_WRAP_WIDTH = 64
DEBUG_LITERAL_KEYS = frozenset({"PublicKey", "Signature", "Hash"})
DEBUG_KEY_STYLE = "bold #0f62fe"
DEBUG_VALUE_STYLE = "#d0e2ff"
DEBUG_LITERAL_STYLE = "#08bdba"
DEBUG_PUNCTUATION_STYLE = "dim"
DEBUG_SECTION_TITLE_STYLE = "bold white"
DEBUG_CODE_BACKGROUND_STYLE = "on #262620"


class _LiteralDebugString(str):
    """Marker type for YAML literal block rendering in debug output."""


class _DebugDumper(yaml.SafeDumper):
    """YAML dumper for debug output formatting."""


def _represent_literal_debug_string(
    dumper: yaml.SafeDumper,
    data: _LiteralDebugString
) -> yaml.nodes.ScalarNode:
    """Render wrapped literals using YAML block scalar syntax."""

    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


_DebugDumper.add_representer(_LiteralDebugString, _represent_literal_debug_string)


def parse_debug_payload(payload: str) -> object:
    """Parse a payload for debug rendering, falling back to a simple body object."""

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"Body": payload}


def print_echo_response(payload: str) -> None:
    """Render an echo response through the shared debug formatter."""

    print_debug_payload("Echo response", parse_debug_payload(payload))


def _format_debug_value(value: object, key: str | None = None) -> object:
    """Prepare nested values for readable YAML-style debug rendering."""

    if isinstance(value, dict):
        return {
            child_key: _format_debug_value(item, key=child_key)
            for child_key, item in value.items()
        }
    if isinstance(value, list):
        return [_format_debug_value(item, key=key) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and type(value) is not str:
        value = str(value)
    elif not isinstance(value, str):
        value = str(value)
    if (
        isinstance(value, str)
        and not any(character.isspace() for character in value)
        and (
            key in DEBUG_LITERAL_KEYS or len(value) > DEBUG_WRAP_WIDTH
        )
    ):
        return _LiteralDebugString("\n".join(textwrap.wrap(value, DEBUG_WRAP_WIDTH)))
    return value


def print_debug_payload(title: str, payload: object) -> None:
    """Render a debug payload in a colorized YAML-like format."""

    print()
    print_section_title(title)
    print_yaml_payload(payload)
    print()


def build_compact_json_payload(payload: object) -> str:
    """Serialize one payload as compact, deterministic JSON."""

    return json.dumps(
        payload,
        sort_keys = False,
        ensure_ascii = False,
        separators = (",", ":"),
    )


def build_pretty_json_payload(payload: object) -> str:
    """Serialize one payload as indented JSON for human-facing displays."""

    return json.dumps(
        payload,
        sort_keys = False,
        ensure_ascii = False,
        indent = 2,
    )


def build_json_syntax(payload: object) -> Syntax:
    """Build a Rich JSON syntax renderable for one payload."""

    return Syntax(
        build_pretty_json_payload(payload),
        "json",
        line_numbers = False,
        word_wrap = True,
    )


def _should_colorize_json_output() -> bool:
    """Return whether JSON output should use terminal syntax coloring."""

    return DEBUG_CONSOLE.is_terminal and not DEBUG_CONSOLE.no_color


def print_json_payload(payload: object) -> None:
    """Render one payload as compact, deterministic JSON."""

    rendered_payload = build_compact_json_payload(payload)

    if _should_colorize_json_output():
        DEBUG_CONSOLE.print(
            build_json_syntax(payload),
            overflow = "fold",
        )
        return

    print(rendered_payload)


def print_debug_json_payload(title: str, payload: object) -> None:
    """Render a debug payload as raw JSON."""

    print()
    print_section_title(title)
    print_json_payload(payload)
    print()


def build_yaml_payload(payload: object) -> str:
    """Serialize one payload with the shared YAML debug dumper."""

    return yaml.dump(
        _format_debug_value(payload),
        sort_keys = False,
        allow_unicode = False,
        default_flow_style = False,
        Dumper = _DebugDumper,
    ).rstrip()


def print_yaml_payload(payload: object) -> None:
    """Render one payload using the shared YAML-like debug formatting."""

    yaml_payload = build_yaml_payload(payload)
    DEBUG_CONSOLE.print(render_debug_yaml(yaml_payload), overflow="fold")


def print_labeled_value_lines(
    values: dict[str, object],
    *,
    prefix: str = ""
) -> None:
    """Render colorized single-line `key: value` entries without YAML wrapping."""

    for key, value in values.items():
        rendered = Text()
        rendered.append(prefix, style=DEBUG_PUNCTUATION_STYLE)
        rendered.append(str(key), style=DEBUG_KEY_STYLE)
        rendered.append(":", style=DEBUG_PUNCTUATION_STYLE)
        rendered.append(f" {value}", style=DEBUG_VALUE_STYLE)
        DEBUG_CONSOLE.print(rendered, soft_wrap=True)


def print_section_title(title: str) -> None:
    """Render a colorized section title that ends with a colon."""

    rendered = Text()
    rendered.append(title, style=DEBUG_SECTION_TITLE_STYLE)
    rendered.append(":", style=DEBUG_PUNCTUATION_STYLE)
    DEBUG_CONSOLE.print(rendered)


def render_debug_yaml(yaml_payload: str) -> Text:
    """Apply syntax highlighting to YAML-like debug content."""

    rendered_lines: list[Text] = []
    literal_indent: int | None = None
    max_line_width = max(
        (len(line) for line in yaml_payload.splitlines()),
        default = 0,
    )

    for line in yaml_payload.splitlines():
        rendered = Text(style = DEBUG_CODE_BACKGROUND_STYLE)

        if not line:
            rendered.append(" " * max_line_width, style = DEBUG_CODE_BACKGROUND_STYLE)
            rendered_lines.append(rendered)
            continue

        indent_width = len(line) - len(line.lstrip(" "))
        stripped = line[indent_width:]
        indent = line[:indent_width]

        if literal_indent is not None and (
            indent_width > literal_indent or not stripped
        ):
            rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
            rendered.append(stripped, style=DEBUG_LITERAL_STYLE)
            rendered.append(
                " " * max(0, max_line_width - len(line)),
                style = DEBUG_CODE_BACKGROUND_STYLE,
            )
            rendered_lines.append(rendered)
            continue
        literal_indent = None

        match = re.match(r"([^:]+):(.*)", stripped)
        if match is None:
            rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
            rendered.append(stripped, style=DEBUG_LITERAL_STYLE)
            rendered.append(
                " " * max(0, max_line_width - len(line)),
                style = DEBUG_CODE_BACKGROUND_STYLE,
            )
            rendered_lines.append(rendered)
            continue

        key, remainder = match.groups()
        rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
        rendered.append(key, style=DEBUG_KEY_STYLE)
        rendered.append(":", style=DEBUG_PUNCTUATION_STYLE)
        if remainder:
            rendered.append(remainder, style=DEBUG_VALUE_STYLE)
        if remainder.strip() == "|":
            literal_indent = indent_width
        rendered.append(
            " " * max(0, max_line_width - len(line)),
            style = DEBUG_CODE_BACKGROUND_STYLE,
        )
        rendered_lines.append(rendered)

    return Text("\n").join(rendered_lines)
