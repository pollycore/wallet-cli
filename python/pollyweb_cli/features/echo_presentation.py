"""Presentation helpers for the `pw echo` command."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version as get_installed_version
import json
import sys
from urllib.parse import quote

from rich.box import ROUNDED
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Link, Static
except ImportError:  # pragma: no cover - dependency is expected in runtime envs
    App = None
    ComposeResult = object
    Horizontal = None
    Vertical = None
    VerticalScroll = None
    Link = None
    Static = None

from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    build_json_syntax,
    build_yaml_payload,
    parse_debug_payload,
    print_debug_json_payload,
    print_debug_payload,
    print_labeled_value_lines,
    print_section_title,
    render_debug_yaml,
    DEBUG_KEY_STYLE,
    DEBUG_PUNCTUATION_STYLE,
    DEBUG_SECTION_TITLE_STYLE,
    DEBUG_VALUE_STYLE,
)


CLI_PACKAGE_NAME = "pollyweb-cli"
TEXTUAL_AVAILABLE = App is not None


@dataclass(frozen = True)
class _EchoTextualSection:
    """One section shown in the interactive Textual echo viewer."""

    title: str
    body: object
    copy_text: str | None = None


SectionBuilder = Callable[[], list[_EchoTextualSection]]


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
                "Sends an Echo@Domain request, then shows the outbound payload, "
                "inbound reply, verification checks, DNS details "
                "and timing so you can confirm delivery, "
                "signature validity, DNS trust, and edge routing."
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
    dkim_and_dnssec_verified: bool,
    cdn_distribution_detected: bool
) -> Panel:
    """Build the bottom summary panel for the echo command."""

    accent_style = "bold #d7875f"
    body_style = "bold white"
    total_milliseconds = max(0, round(total_seconds * 1000))
    latency_share = 0.0

    if total_seconds > 0:
        latency_share = (network_seconds / total_seconds) * 100

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
    network_seconds: float
) -> Panel:
    """Build the bottom summary panel for a failed echo debug run."""

    accent_style = "bold #d7875f"
    body_style = "bold white"
    total_milliseconds = max(0, round(total_seconds * 1000))
    latency_share = 0.0

    if total_seconds > 0:
        latency_share = (network_seconds / total_seconds) * 100

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


def _print_echo_footer_summary(
    *,
    total_seconds: float,
    network_seconds: float,
    dkim_and_dnssec_verified: bool,
    cdn_distribution_detected: bool
) -> None:
    """Render the bottom summary panel for the plain CLI path."""

    DEBUG_CONSOLE.print(
        _build_echo_footer_panel(
            total_seconds = total_seconds,
            network_seconds = network_seconds,
            dkim_and_dnssec_verified = dkim_and_dnssec_verified,
            cdn_distribution_detected = cdn_distribution_detected,
        )
    )


def _print_echo_error_footer_summary(
    *,
    total_seconds: float,
    network_seconds: float
) -> None:
    """Render the bottom failure-summary panel for the plain CLI path."""

    DEBUG_CONSOLE.print(
        _build_echo_error_footer_panel(
            total_seconds = total_seconds,
            network_seconds = network_seconds,
        )
    )


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


def _build_payload_section(
    *,
    title: str,
    payload: object,
    payload_format: str
) -> _EchoTextualSection:
    """Build one payload-style section while serializing the payload only once."""

    if payload_format == "json":
        copy_text = _json_debug_copy_text(payload)
        body = Syntax(
            copy_text,
            "json",
            line_numbers = False,
            word_wrap = True,
        )
    elif payload_format == "raw":
        copy_text = _raw_json_debug_text(payload)
        body = Text(
            copy_text,
            style = DEBUG_VALUE_STYLE,
        )
    else:
        copy_text = build_yaml_payload(payload)
        body = render_debug_yaml(copy_text)

    return _EchoTextualSection(
        title = title,
        body = body,
        copy_text = copy_text,
    )


def _build_echo_edge_lines(
    transport_metadata: dict[str, object]
) -> dict[str, str]:
    """Collect edge and CDN hints for display."""

    headers = _normalize_response_headers(transport_metadata)
    if not headers:
        return {"Transport headers": "unavailable in this runtime"}

    edge_lines: dict[str, str] = {}
    provider = _detect_edge_provider(headers)
    pop_value = _detect_edge_pop(
        headers,
        provider = provider)

    request_url = transport_metadata.get("request_url")
    if isinstance(request_url, str) and request_url:
        edge_lines["Request URL"] = request_url

    http_status = transport_metadata.get("http_status")
    http_reason = transport_metadata.get("http_reason")
    if isinstance(http_status, int):
        if isinstance(http_reason, str) and http_reason:
            edge_lines["HTTP status"] = f"{http_status} {http_reason}"
        else:
            edge_lines["HTTP status"] = str(http_status)

    edge_lines["Edge provider"] = (
        provider if provider is not None else "no CDN fingerprint detected"
    )
    edge_lines["Edge PoP"] = pop_value if pop_value is not None else "unavailable"

    for key, label in (
        ("server", "Server header"),
        ("via", "Via header"),
        ("x-cache", "X-Cache"),
        ("x-amz-cf-id", "CloudFront request ID"),
        ("cf-ray", "Cloudflare Ray ID"),
    ):
        value = headers.get(key)
        if value:
            edge_lines[label] = value

    return edge_lines


def _build_echo_timing_lines(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None
) -> dict[str, str]:
    """Collect timing details for display."""

    total_milliseconds = max(0, round(total_seconds * 1000))
    network_milliseconds = max(0, round(network_seconds * 1000))
    client_overhead_milliseconds = max(0, total_milliseconds - network_milliseconds)
    lines = {"Total duration": f"{total_milliseconds} ms"}

    if total_seconds > 0:
        lines["Latency share"] = (
            f"{(network_seconds / total_seconds) * 100:.0f}% "
            f"({network_milliseconds} ms)"
        )
    else:
        lines["Latency share"] = f"0% ({network_milliseconds} ms)"

    lines["Client overhead"] = f"{client_overhead_milliseconds} ms"

    if response_metadata is not None and hasattr(response_metadata, "get"):
        latency_ms = response_metadata.get("LatencyMs")
        if isinstance(latency_ms, int):
            lines["Remote latency"] = f"{latency_ms} ms"

        total_execution_ms = response_metadata.get("TotalExecutionMs")
        if isinstance(total_execution_ms, int):
            lines["Total execution"] = f"{total_execution_ms} ms"

        downstream_execution_ms = response_metadata.get("DownstreamExecutionMs")
        if isinstance(downstream_execution_ms, int):
            lines["Downstream execution"] = f"{downstream_execution_ms} ms"

    return lines


def _build_echo_textual_sections(
    *,
    domain: str,
    debug: bool,
    payload_format: str,
    outbound_payload: object | None,
    response_payload: str,
    parsed_response_payload: object | None = None,
    dns_diagnostics,
    dns_link_context: tuple[str, str] | None,
    verification_lines: dict[str, str],
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None,
    transport_metadata: dict[str, object]
) -> list[_EchoTextualSection]:
    """Build the section renderables shown in the Textual echo viewer."""

    sections: list[_EchoTextualSection] = []

    if debug:
        outbound_payload_value = {} if outbound_payload is None else outbound_payload
        inbound_payload_value = (
            parsed_response_payload
            if parsed_response_payload is not None
            else parse_debug_payload(response_payload)
        )
        sections.append(
            _build_payload_section(
                title = f"Outbound payload to https://pw.{domain}/inbox",
                payload = outbound_payload_value,
                payload_format = payload_format,
            )
        )
        sections.append(
            _build_payload_section(
                title = "Inbound payload",
                payload = inbound_payload_value,
                payload_format = payload_format,
            )
        )
        sections.append(
            _EchoTextualSection(
                title = f"Verified echo response from {domain}",
                body = _render_labeled_lines(verification_lines),
            )
        )
        if dns_diagnostics is not None:
            diagnostics_payload = asdict(dns_diagnostics)
            sections.append(
                _build_payload_section(
                    title = "DNS verification diagnostics",
                    payload = diagnostics_payload,
                    payload_format = payload_format,
                )
            )
        if dns_link_context is not None:
            sections.append(
                _EchoTextualSection(
                    title = "External DNS checks",
                    body = _render_labeled_lines(_echo_dns_reference_links(*dns_link_context)),
                )
            )
        sections.append(
            _EchoTextualSection(
                title = "Network timing",
                body = _render_labeled_lines(
                    _build_echo_timing_lines(
                        total_seconds = total_seconds,
                        network_seconds = network_seconds,
                        response_metadata = response_metadata,
                    )
                ),
            )
        )
        sections.append(
            _EchoTextualSection(
                title = "Edge / CDN hints",
                body = _render_labeled_lines(_build_echo_edge_lines(transport_metadata)),
            )
        )
    else:
        sections.append(
            _EchoTextualSection(
                title = "Verified response",
                body = Text(
                    _format_echo_success_metrics(
                        total_seconds = total_seconds,
                        network_seconds = network_seconds,
                    ),
                    style = DEBUG_VALUE_STYLE,
                ),
            )
        )

    return sections


def _build_echo_error_textual_sections(
    *,
    domain: str,
    payload_format: str,
    outbound_payload: object | None,
    response_payload: str | None,
    parsed_response_payload: object | None = None,
    verification_lines: dict[str, str] | None,
    dns_diagnostics,
    dns_link_context: tuple[str, str] | None,
    error_lines: dict[str, str],
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None,
    transport_metadata: dict[str, object]
) -> list[_EchoTextualSection]:
    """Build the error sections shown in the Textual echo viewer."""

    outbound_payload_value = {} if outbound_payload is None else outbound_payload
    sections: list[_EchoTextualSection] = [
        _build_payload_section(
            title = f"Outbound payload to https://pw.{domain}/inbox",
            payload = outbound_payload_value,
            payload_format = payload_format,
        ),
    ]

    if response_payload is not None:
        inbound_payload_value = (
            parsed_response_payload
            if parsed_response_payload is not None
            else parse_debug_payload(response_payload)
        )
        sections.append(
            _build_payload_section(
                title = "Inbound payload",
                payload = inbound_payload_value,
                payload_format = payload_format,
            )
        )

    sections.append(
        _EchoTextualSection(
            title = "Error summary",
            body = _render_labeled_lines(error_lines),
        )
    )

    if verification_lines:
        sections.append(
            _EchoTextualSection(
                title = f"Reply details from {domain}",
                body = _render_labeled_lines(verification_lines),
            )
        )

    diagnostics_payload = (
        {"Status": "unavailable for this failure"}
        if dns_diagnostics is None
        else asdict(dns_diagnostics)
    )
    sections.append(
        _build_payload_section(
            title = "DNS verification diagnostics",
            payload = diagnostics_payload,
            payload_format = payload_format,
        )
    )

    if dns_link_context is not None:
        sections.append(
            _EchoTextualSection(
                title = "External DNS checks",
                body = _render_labeled_lines(_echo_dns_reference_links(*dns_link_context)),
            )
        )

    sections.append(
        _EchoTextualSection(
            title = "Network timing",
            body = _render_labeled_lines(
                _build_echo_timing_lines(
                    total_seconds = total_seconds,
                    network_seconds = network_seconds,
                    response_metadata = response_metadata,
                )
            ),
        )
    )
    sections.append(
        _EchoTextualSection(
            title = "Edge / CDN hints",
            body = _render_labeled_lines(_build_echo_edge_lines(transport_metadata)),
        )
    )
    return sections


class _EchoTextualApp(App[None] if TEXTUAL_AVAILABLE else object):
    """TTY-only Textual viewer for the interactive echo result layout."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #header-bar {
        height: auto;
        margin: 0 0 1 0;
    }

    #header-panel {
        width: 1fr;
    }

    #header-controls {
        width: auto;
        height: auto;
        align: right middle;
        border: round #d7875f;
        border-title-align: left;
        border-title-color: #d7875f;
        border-title-style: bold;
        padding: 0 0;
    }

    .section-bar {
        height: auto;
        margin: 0 0 0 0;
    }

    .section-title {
        width: 1fr;
    }

    .section-controls {
        width: auto;
        height: auto;
        align: right middle;
    }

    .section-block {
        height: auto;
        margin: 0 0 1 0;
    }

    .section-content {
        height: auto;
    }

    .code-content {
        width: 1fr;
        background: #262620;
    }

    .control-link {
        width: auto;
        min-width: 0;
        min-height: 1;
        margin: 0 0 0 0;
        padding: 0 1 0 0;
        color: #3b82f6;
    }

    .copy-link {
        width: auto;
        min-width: 0;
        min-height: 1;
        margin: 0 0 0 1;
        padding: 0 0;
        color: #3b82f6;
    }

    .is-active {
        color: #d7875f;
        text-style: bold underline;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("x", "quit", "Quit"),
        ("escape", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+w", "quit", "Quit"),
        ("up", "scroll_up", "Up"),
        ("down", "scroll_down", "Down"),
        ("pageup", "scroll_page_up", "Page up"),
        ("pagedown", "scroll_page_down", "Page down"),
        ("y", "show_yaml", "YAML"),
        ("j", "show_json", "JSON"),
        ("r", "show_raw", "Raw"),
    ]

    def __init__(
        self,
        *,
        header_panel: Panel,
        yaml_sections: list[_EchoTextualSection] | SectionBuilder,
        json_sections: list[_EchoTextualSection] | SectionBuilder,
        raw_sections: list[_EchoTextualSection] | SectionBuilder,
        footer_panel: Panel,
        initial_payload_format: str
    ) -> None:
        """Store the renderables needed by the echo viewer."""

        super().__init__()
        self._header_panel = header_panel
        self._yaml_sections = yaml_sections
        self._json_sections = json_sections
        self._raw_sections = raw_sections
        self._footer_panel = footer_panel
        self._payload_format = initial_payload_format
        self._copied_section: tuple[str, int] | None = None
        self._copied_reset_timer = None
        self._section_cache: dict[str, list[_EchoTextualSection]] = {}

    def _resolve_sections(
        self,
        payload_format: str
    ) -> list[_EchoTextualSection]:
        """Build and cache section lists only when a view is first opened."""

        cached_sections = self._section_cache.get(payload_format)
        if cached_sections is not None:
            return cached_sections

        section_source: list[_EchoTextualSection] | SectionBuilder
        if payload_format == "json":
            section_source = self._json_sections
        elif payload_format == "raw":
            section_source = self._raw_sections
        else:
            section_source = self._yaml_sections

        resolved_sections = (
            section_source()
            if callable(section_source)
            else section_source
        )
        self._section_cache[payload_format] = resolved_sections
        return resolved_sections

    def _current_sections(self) -> list[_EchoTextualSection]:
        """Return the current section list for the selected payload format."""

        return self._resolve_sections(self._payload_format)

    def _body_scroll(self, method_name: str) -> None:
        """Forward a keyboard scroll action to the main scrollable body."""

        scroll_view = self.query_one("#body")
        getattr(scroll_view, method_name)(animate = False)

    def action_show_yaml(self) -> None:
        """Switch the interactive payload view to YAML."""

        self._payload_format = "yaml"
        self._clear_copied_feedback()
        self.refresh(recompose = True)

    def action_show_json(self) -> None:
        """Switch the interactive payload view to JSON."""

        self._payload_format = "json"
        self._clear_copied_feedback()
        self.refresh(recompose = True)

    def action_show_raw(self) -> None:
        """Switch the interactive payload view to raw JSON."""

        self._payload_format = "raw"
        self._clear_copied_feedback()
        self.refresh(recompose = True)

    def action_scroll_up(self) -> None:
        """Scroll the interactive body upward by one line."""

        self._body_scroll("scroll_up")

    def action_scroll_down(self) -> None:
        """Scroll the interactive body downward by one line."""

        self._body_scroll("scroll_down")

    def action_scroll_page_up(self) -> None:
        """Scroll the interactive body upward by one page."""

        self._body_scroll("scroll_page_up")

    def action_scroll_page_down(self) -> None:
        """Scroll the interactive body downward by one page."""

        self._body_scroll("scroll_page_down")

    def _clear_copied_feedback(self) -> None:
        """Clear any active copy feedback and stop its pending reset timer."""

        self._copied_section = None
        if self._copied_reset_timer is not None:
            self._copied_reset_timer.stop()
            self._copied_reset_timer = None

    def _reset_copied_feedback(
        self,
        copied_section: tuple[str, int]
    ) -> None:
        """Restore the copy link label after the transient copied state."""

        self._copied_reset_timer = None
        if self._copied_section == copied_section:
            self._copied_section = None
            self.refresh(recompose = True)

    def open_url(
        self,
        url: str,
        *,
        new_tab: bool = True
    ) -> None:
        """Route internal link actions without leaving the Textual app."""

        if url == "action://show-yaml":
            self.action_show_yaml()
            return

        if url == "action://show-json":
            self.action_show_json()
            return

        if url == "action://show-raw":
            self.action_show_raw()
            return

        if url.startswith("action://copy/"):
            copy_index = int(url.removeprefix("action://copy/"))
            section = self._current_sections()[copy_index]
            if section.copy_text is not None:
                self.copy_to_clipboard(section.copy_text)
                copied_section = (self._payload_format, copy_index)
                self._clear_copied_feedback()
                self._copied_section = copied_section
                self._copied_reset_timer = self.set_timer(
                    1.0,
                    lambda: self._reset_copied_feedback(copied_section),
                )
                self.refresh(recompose = True)
            return

        super().open_url(url, new_tab = new_tab)

    def compose(self) -> ComposeResult:
        """Compose the reactive echo layout."""

        header_controls = Vertical(
            Link(
                "Yaml",
                url = "action://show-yaml",
                id = "toggle-yaml",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "yaml"
                    else "control-link"
                ),
            ),
            Link(
                "Json",
                url = "action://show-json",
                id = "toggle-json",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "json"
                    else "control-link"
                ),
            ),
            Link(
                "Raw",
                url = "action://show-raw",
                id = "toggle-raw",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "raw"
                    else "control-link"
                ),
            ),
            id = "header-controls",
        )
        yield Horizontal(
            Static(self._header_panel, id = "header-panel"),
            header_controls,
            id = "header-bar",
        )
        yield VerticalScroll(
            *[
                Vertical(
                    Horizontal(
                        Static(
                            _render_section_title(section.title),
                            classes = "section-title",
                        ),
                        Horizontal(
                            *(
                                [
                                    Link(
                                        (
                                            "Copied"
                                            if self._copied_section == (self._payload_format, index)
                                            else "Copy"
                                        ),
                                        url = (
                                            None
                                            if self._copied_section == (self._payload_format, index)
                                            else f"action://copy/{index}"
                                        ),
                                        id = f"copy-{index}",
                                        classes = (
                                            "copy-link is-active"
                                            if self._copied_section == (self._payload_format, index)
                                            else "copy-link"
                                        ),
                                    )
                                ]
                                if section.copy_text is not None
                                else []
                            ),
                            classes = "section-controls",
                        ),
                        classes = "section-bar",
                    ),
                    Static(
                        section.body,
                        classes = (
                            "section-content code-content"
                            if section.copy_text is not None
                            else "section-content"
                        ),
                    ),
                    classes = "section-block",
                )
                for index, section in enumerate(self._current_sections())
            ],
            id = "body",
        )
        yield Static(self._footer_panel, classes = "section-block")


def _should_use_textual_echo_view(
    *,
    debug: bool
) -> bool:
    """Return whether `pw echo` should use the interactive Textual viewer."""

    return (
        debug
        and
        TEXTUAL_AVAILABLE
        and sys.stdout.isatty()
        and sys.stdin.isatty()
    )


def _extract_response_header(
    payload: str
) -> dict[str, object] | None:
    """Extract the raw response header when the payload is valid JSON."""

    try:
        loaded_payload = json.loads(payload)
    except json.JSONDecodeError:
        return None

    response = loaded_payload.get("Response")
    if isinstance(response, dict):
        header = response.get("Header")
        if isinstance(header, dict):
            return header

    header = loaded_payload.get("Header")
    if not isinstance(header, dict):
        return None

    return header


def _echo_dns_reference_links(
    domain: str,
    selector: str
) -> dict[str, str]:
    """Build click-through DNS inspection links for the verified selector."""

    branch = f"pw.{domain}"

    return {
        "MXToolbox DKIM test": (
            "https://mxtoolbox.com/SuperTool.aspx?action="
            f"{quote(f'dkim:{branch}:{selector}', safe='')}&run=toolpage"
        ),
        "DNSSEC Debugger test": f"https://dnssec-debugger.verisignlabs.com/{branch}",
        "Google DNS test": f"https://dns.google/query?name={branch}",
        "Google DNS A record test": f"https://dns.google/resolve?name={branch}&type=A",
    }


def _echo_dns_context(
    payload: str,
    *,
    fallback_domain: str
) -> tuple[str, str] | None:
    """Extract the response domain and selector used for echo verification."""

    header = _extract_response_header(payload)
    if header is None:
        return None

    selector = header.get("Selector")
    if not isinstance(selector, str) or selector == "":
        return None

    from_value = header.get("From")
    domain = from_value if isinstance(from_value, str) and from_value else fallback_domain

    return domain, selector


def _print_echo_dns_diagnostics(
    diagnostics,
    *,
    json_output: bool
) -> None:
    """Render DNS verification diagnostics for the echo debug path."""

    if diagnostics is None:
        print()
        print_section_title("DNS verification diagnostics")
        print_labeled_value_lines(
            {"Status": "unavailable for this failure"},
            prefix = " - ",
        )
        return

    printer = print_debug_json_payload if json_output else print_debug_payload
    printer(
        "DNS verification diagnostics",
        asdict(diagnostics))


def _print_echo_dns_reference_links(
    domain: str,
    selector: str
) -> None:
    """Render click-through external DNS inspection links."""

    print()
    print_section_title("External DNS checks")
    print_labeled_value_lines(
        _echo_dns_reference_links(
            domain,
            selector),
        prefix = " - ",
    )
    print()


def _format_echo_success_metrics(
    *,
    total_seconds: float,
    network_seconds: float
) -> str:
    """Format the echo success metrics for concise terminal output."""

    total_milliseconds = max(0, round(total_seconds * 1000))
    network_share = 0.0

    if total_seconds > 0:
        network_share = (network_seconds / total_seconds) * 100

    return (
        f"✅ Verified echo response ({total_milliseconds} ms, "
        f"{network_share:.0f}% latency)"
    )


def _normalize_response_headers(
    transport_metadata: dict[str, object]
) -> dict[str, str]:
    """Return lower-cased HTTP response headers captured from transport."""

    raw_headers = transport_metadata.get("response_headers")
    if not isinstance(raw_headers, dict):
        return {}

    normalized_headers: dict[str, str] = {}

    for key, value in raw_headers.items():
        if isinstance(key, str) and isinstance(value, str):
            normalized_headers[key.lower()] = value

    return normalized_headers


def _detect_edge_provider(
    headers: dict[str, str]
) -> str | None:
    """Infer the CDN or edge provider from captured response headers."""

    via_value = headers.get("via", "").lower()
    server_value = headers.get("server", "").lower()
    x_cache_value = headers.get("x-cache", "").lower()

    if (
        "x-amz-cf-pop" in headers
        or "x-amz-cf-id" in headers
        or "cloudfront" in via_value
        or "cloudfront" in x_cache_value
    ):
        return "CloudFront"

    if "cf-ray" in headers or "cloudflare" in server_value:
        return "Cloudflare"

    if "fastly" in server_value or "x-served-by" in headers:
        return "Fastly"

    return None


def _detect_edge_pop(
    headers: dict[str, str],
    *,
    provider: str | None
) -> str | None:
    """Infer the edge PoP from provider-specific response headers."""

    if provider == "CloudFront":
        pop_value = headers.get("x-amz-cf-pop")
        if isinstance(pop_value, str) and pop_value:
            return pop_value

    if provider == "Cloudflare":
        cf_ray = headers.get("cf-ray")
        if isinstance(cf_ray, str) and "-" in cf_ray:
            return cf_ray.rsplit("-", 1)[-1]

    return None


def _print_echo_timing_details(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None
) -> None:
    """Render the echo timing details as a dedicated debug section."""

    print()
    print_section_title("Network timing")

    timing_lines = _build_echo_timing_lines(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata,
    )

    print_labeled_value_lines(
        timing_lines,
        prefix = " - ",
    )


def _print_echo_edge_details(
    transport_metadata: dict[str, object]
) -> None:
    """Render best-effort CDN and edge-routing hints from HTTP transport."""

    print()
    print_section_title("Edge / CDN hints")

    headers = _normalize_response_headers(transport_metadata)
    if not headers:
        print_labeled_value_lines(
            {"Transport headers": "unavailable in this runtime"},
            prefix = " - ",
        )
        return

    print_labeled_value_lines(
        _build_echo_edge_lines(transport_metadata),
        prefix = " - ",
    )


def _render_debug_echo_failure(
    *,
    domain: str,
    debug_json: bool,
    error_lines: dict[str, str],
    outbound_payload: object | None,
    response_payload: str | None,
    verification_lines: dict[str, str] | None,
    dns_diagnostics,
    dns_link_context: tuple[str, str] | None,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None,
    transport_metadata: dict[str, object]
) -> int:
    """Render a debug-friendly echo failure summary without crashing out."""

    footer_panel = _build_echo_error_footer_panel(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
    )
    parsed_response_payload = (
        parse_debug_payload(response_payload)
        if response_payload is not None
        else None
    )

    if _should_use_textual_echo_view(debug = True):
        _EchoTextualApp(
            header_panel = _build_echo_header_panel(),
            yaml_sections = lambda: _build_echo_error_textual_sections(
                domain = domain,
                payload_format = "yaml",
                outbound_payload = outbound_payload,
                response_payload = response_payload,
                parsed_response_payload = parsed_response_payload,
                verification_lines = verification_lines,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                error_lines = error_lines,
                total_seconds = total_seconds,
                network_seconds = network_seconds,
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            ),
            json_sections = lambda: _build_echo_error_textual_sections(
                domain = domain,
                payload_format = "json",
                outbound_payload = outbound_payload,
                response_payload = response_payload,
                parsed_response_payload = parsed_response_payload,
                verification_lines = verification_lines,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                error_lines = error_lines,
                total_seconds = total_seconds,
                network_seconds = network_seconds,
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            ),
            raw_sections = lambda: _build_echo_error_textual_sections(
                domain = domain,
                payload_format = "raw",
                outbound_payload = outbound_payload,
                response_payload = response_payload,
                parsed_response_payload = parsed_response_payload,
                verification_lines = verification_lines,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                error_lines = error_lines,
                total_seconds = total_seconds,
                network_seconds = network_seconds,
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            ),
            footer_panel = footer_panel,
            initial_payload_format = "json",
        ).run()
        return 1

    if response_payload is not None:
        print_section_title("Inbound payload")
        if debug_json:
            print_json_payload(parse_debug_payload(response_payload))
        else:
            DEBUG_CONSOLE.print(_yaml_debug_renderable(parse_debug_payload(response_payload)))

    print_section_title("Error summary")
    print_labeled_value_lines(
        error_lines,
        prefix = " - ",
    )
    if verification_lines:
        print_section_title(f"Reply details from {domain}")
        print_labeled_value_lines(
            verification_lines,
            prefix = " - ",
        )
    _print_echo_dns_diagnostics(
        dns_diagnostics,
        json_output = debug_json)
    if dns_link_context is not None:
        _print_echo_dns_reference_links(*dns_link_context)
    _print_echo_timing_details(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata)
    _print_echo_edge_details(transport_metadata)
    print()
    DEBUG_CONSOLE.print(footer_panel)
    print()
    return 1
