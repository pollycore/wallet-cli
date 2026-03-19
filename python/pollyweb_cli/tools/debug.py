"""Debug formatting helpers for CLI payload output."""

from __future__ import annotations

import json
import re
import textwrap

import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text


DEBUG_CONSOLE = Console()
SHELL_CONSOLE = Console()
DEBUG_WRAP_WIDTH = 64
DEBUG_LITERAL_KEYS = frozenset({"PublicKey", "Signature", "Hash"})
DEBUG_KEY_STYLE = "bold #0f62fe"
DEBUG_VALUE_STYLE = "#d0e2ff"
DEBUG_LITERAL_STYLE = "#08bdba"
DEBUG_PUNCTUATION_STYLE = "dim"
DEBUG_SECTION_TITLE_STYLE = "bold white"
HTTP_CODE_STYLES = {
    1: "cyan",
    2: "green",
    3: "blue",
    4: "yellow",
    5: "bold red",
}


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


def extract_http_code(payload: str) -> int | None:
    """Extract a numeric HTTP-style code from a JSON payload when present."""

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    code_value = parsed.get("Code")
    if isinstance(code_value, int):
        return code_value
    if isinstance(code_value, str) and code_value.isdigit():
        return int(code_value)
    return None


def get_http_code_style(code: int) -> str | None:
    """Map a numeric code to the shell output style for its class."""

    return HTTP_CODE_STYLES.get(code // 100)


def parse_shell_response_body(payload: str) -> tuple[str | None, str | None]:
    """Extract rendered shell markdown and an optional style from a payload."""

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None, None

    if not isinstance(parsed, dict):
        return None, None

    rendered_text = parsed.get("Body")
    if not isinstance(rendered_text, str):
        rendered_text = parsed.get("Message")
    if not isinstance(rendered_text, str):
        return None, None

    code = parsed.get("Code")
    if isinstance(code, int):
        return rendered_text, get_http_code_style(code)
    if isinstance(code, str) and code.isdigit():
        return rendered_text, get_http_code_style(int(code))
    return rendered_text, None


def print_shell_response(payload: str) -> None:
    """Render a shell command response with optional markdown and status styling."""

    body, body_style = parse_shell_response_body(payload)
    if body is not None:
        SHELL_CONSOLE.print(Markdown(body), style=body_style)
        return

    code = extract_http_code(payload)
    style = get_http_code_style(code) if code is not None else None
    if style is None:
        print(payload)
        return
    SHELL_CONSOLE.print(payload, style=style)


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


def print_json_payload(payload: object) -> None:
    """Render one payload as compact, deterministic JSON."""

    print(
        json.dumps(
            payload,
            sort_keys = False,
            ensure_ascii = False,
            separators = (",", ":"),
        )
    )


def print_debug_json_payload(title: str, payload: object) -> None:
    """Render a debug payload as raw JSON."""

    print()
    print_section_title(title)
    print_json_payload(payload)
    print()


def print_yaml_payload(payload: object) -> None:
    """Render one payload using the shared YAML-like debug formatting."""

    yaml_payload = yaml.dump(
        _format_debug_value(payload),
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
        Dumper=_DebugDumper,
    ).rstrip()
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

    rendered = Text()
    literal_indent: int | None = None

    for line in yaml_payload.splitlines():
        if rendered:
            rendered.append("\n")

        if not line:
            continue

        indent_width = len(line) - len(line.lstrip(" "))
        stripped = line[indent_width:]
        indent = line[:indent_width]

        if literal_indent is not None and (
            indent_width > literal_indent or not stripped
        ):
            rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
            rendered.append(stripped, style=DEBUG_LITERAL_STYLE)
            continue
        literal_indent = None

        match = re.match(r"([^:]+):(.*)", stripped)
        if match is None:
            rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
            rendered.append(stripped, style=DEBUG_LITERAL_STYLE)
            continue

        key, remainder = match.groups()
        rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
        rendered.append(key, style=DEBUG_KEY_STYLE)
        rendered.append(":", style=DEBUG_PUNCTUATION_STYLE)
        if remainder:
            rendered.append(remainder, style=DEBUG_VALUE_STYLE)
        if remainder.strip() == "|":
            literal_indent = indent_width

    return rendered
