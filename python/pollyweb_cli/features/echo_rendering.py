"""Shared rendering primitives for the `pw echo` feature."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as get_installed_version

from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    DEBUG_KEY_STYLE,
    DEBUG_PUNCTUATION_STYLE,
    DEBUG_SECTION_TITLE_STYLE,
    DEBUG_VALUE_STYLE,
    build_json_syntax,
    build_yaml_payload,
    render_debug_yaml,
)


CLI_PACKAGE_NAME = "pollyweb-cli"


def _get_echo_header_version() -> str:
    """Return the installed CLI version for the echo header."""

    try:
        return get_installed_version(CLI_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"


def _get_echo_panel_width() -> int | None:
    """Return the current terminal width for echo panels when available."""

    console_width = DEBUG_CONSOLE.size.width
    if console_width <= 0:
        return None

    return console_width


def _build_echo_header_panel() -> Panel:
    """Build the top banner panel for the echo command."""

    accent_style = "bold #d7875f"
    muted_style = "#a9a9b3"
    version = _get_echo_header_version()

    title = Text()
    title.append("pw echo", style = accent_style)
    title.append(f" v{version}", style = muted_style)
    return Panel(
        Text(
            (
                "Sends an Echo@Domain request to a target domain. \n"
                "Domains ending in '.dom' translate to '.pollyweb.org'. \n"
                "To change between Yaml, Json, and Raw view, hit Y/J/R."
            ),
            style = "#a9a9b3",
            justify = "left",
        ),
        title = title,
        title_align = "left",
        border_style = accent_style,
        box = ROUNDED,
        expand = True,
        width = _get_echo_panel_width(),
        padding = (0, 1),
    )


def _build_echo_footer_panel(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None,
    dkim_and_dnssec_verified: bool,
    cdn_distribution_detected: bool
) -> Panel:
    """Build the bottom summary panel for the echo command."""

    accent_style = "bold #d7875f"
    body_style = "bold white"
    total_milliseconds = max(0, round(total_seconds * 1000))
    latency_share = _resolve_echo_latency_share(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata,
    )

    summary = Table.grid(expand = True)
    summary.add_column(ratio = 1)
    summary.add_column(ratio = 1)
    summary.add_row(
        Text(
            "✅ DKIM and DNSSEC" if dkim_and_dnssec_verified else "⏳ DKIM and DNSSEC",
            style = body_style,
        ),
        Text(
            "✅ CDN distribution" if cdn_distribution_detected else "⏳ CDN distribution",
            style = body_style,
        ),
    )
    summary.add_row(
        Text("✅ Signed message", style = body_style),
        Text(
            f"⏳ Time {total_milliseconds} ms  Network {latency_share:.0f}%",
            style = body_style,
        ),
    )

    return Panel(
        summary,
        title = Text("Echo summary", style = accent_style),
        title_align = "left",
        border_style = accent_style,
        box = ROUNDED,
        expand = True,
        width = _get_echo_panel_width(),
        padding = (0, 1),
    )


def _build_echo_error_footer_panel(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None
) -> Panel:
    """Build the bottom summary panel for a failed echo debug run."""

    accent_style = "bold #d7875f"
    body_style = "bold white"
    total_milliseconds = max(0, round(total_seconds * 1000))
    latency_share = _resolve_echo_latency_share(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata,
    )

    summary = Table.grid(expand = True)
    summary.add_column(ratio = 1)
    summary.add_column(ratio = 1)
    summary.add_row(
        Text("❌ Echo request failed", style = body_style),
        Text("⏳ Verification incomplete", style = body_style),
    )
    summary.add_row(
        Text("Review the error summary above", style = body_style),
        Text(
            f"⏳ Time {total_milliseconds} ms  Network {latency_share:.0f}%",
            style = body_style,
        ),
    )

    return Panel(
        summary,
        title = Text("Echo summary", style = accent_style),
        title_align = "left",
        border_style = accent_style,
        box = ROUNDED,
        expand = True,
        width = _get_echo_panel_width(),
        padding = (0, 1),
    )


def _print_echo_header() -> None:
    """Render the top banner panel for the plain CLI path."""

    print()
    DEBUG_CONSOLE.print(_build_echo_header_panel())


def _yaml_debug_renderable(payload: object) -> Text:
    """Render one payload to the shared YAML-like debug renderable."""

    return render_debug_yaml(build_yaml_payload(payload))


def _json_debug_renderable(payload: object):
    """Render one payload to syntax-colored JSON for the Textual echo viewer."""

    return build_json_syntax(payload)


def _json_debug_copy_text(payload: object) -> str:
    """Render one payload to indented JSON text for clipboard copying."""

    return json.dumps(
        payload,
        sort_keys = False,
        ensure_ascii = False,
        indent = 2,
    )


def _raw_json_debug_text(payload: object) -> str:
    """Render one payload as compact raw JSON text."""

    return json.dumps(
        payload,
        sort_keys = False,
        ensure_ascii = False,
        separators = (",", ":"),
    )


def _raw_json_debug_renderable(payload: object) -> Text:
    """Render one payload as compact raw JSON text."""

    return Text(
        _raw_json_debug_text(payload),
        style = DEBUG_VALUE_STYLE,
    )


def _render_section_title(title: str) -> Text:
    """Build one section title renderable."""

    rendered = Text()
    rendered.append(title, style = DEBUG_SECTION_TITLE_STYLE)
    rendered.append(":", style = DEBUG_PUNCTUATION_STYLE)
    return rendered


def _render_labeled_lines(values: dict[str, object]) -> Text:
    """Render colored `key: value` lines for the Textual echo viewer."""

    rendered = Text()
    first_line = True

    for key, value in values.items():
        if not first_line:
            rendered.append("\n")
        first_line = False
        rendered.append(" - ", style = DEBUG_PUNCTUATION_STYLE)
        rendered.append(str(key), style = DEBUG_KEY_STYLE)
        rendered.append(":", style = DEBUG_PUNCTUATION_STYLE)
        rendered.append(f" {value}", style = DEBUG_VALUE_STYLE)

    return rendered


def _format_echo_success_metrics(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None
) -> str:
    """Format the echo success metrics for concise terminal output."""

    total_milliseconds = max(0, round(total_seconds * 1000))
    network_share = _resolve_echo_latency_share(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata,
    )

    return (
        f"✅ Verified echo response ({total_milliseconds} ms, "
        f"{network_share:.0f}% latency)"
    )


def _resolve_echo_latency_share(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None
) -> float:
    """Return the transport-latency percentage shown in echo timing output."""

    total_milliseconds = max(0, round(total_seconds * 1000))

    if total_milliseconds <= 0:
        return 0.0

    latency_milliseconds = _resolve_echo_latency_milliseconds(
        network_seconds = network_seconds,
        response_metadata = response_metadata,
    )
    return (latency_milliseconds / total_milliseconds) * 100


def _resolve_echo_latency_milliseconds(
    *,
    network_seconds: float,
    response_metadata: object | None = None
) -> int:
    """Return the estimated transport-only latency in milliseconds."""

    send_phase_milliseconds = max(0, round(network_seconds * 1000))
    if response_metadata is None or not hasattr(response_metadata, "get"):
        return send_phase_milliseconds

    message_total_milliseconds = response_metadata.get("TotalMs")
    if not isinstance(message_total_milliseconds, int):
        return send_phase_milliseconds

    # When the reply reports its own end-to-end message time, subtract that
    # server-side work from the measured send phase so "latency" reflects the
    # remaining transport time rather than double-counting server execution.
    return max(
        0,
        send_phase_milliseconds - min(
            send_phase_milliseconds,
            message_total_milliseconds,
        ),
    )
