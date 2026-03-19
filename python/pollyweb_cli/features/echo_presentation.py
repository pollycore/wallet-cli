"""Compatibility facade for `pw echo` presentation helpers."""

from __future__ import annotations

from pollyweb_cli.features.echo_rendering import (
    DEBUG_CONSOLE,
    _build_echo_error_footer_panel,
    _build_echo_footer_panel,
    _build_echo_header_panel,
    _format_echo_success_metrics,
    _json_debug_copy_text,
    _print_echo_header,
    _json_debug_renderable,
    _raw_json_debug_renderable,
    _render_labeled_lines,
    _render_section_title,
    _yaml_debug_renderable,
)
from pollyweb_cli.features.echo_sections import (
    _build_echo_edge_lines,
    _build_echo_error_textual_sections,
    _build_echo_textual_sections,
    _build_echo_timing_lines,
    _detect_edge_pop,
    _detect_edge_provider,
    _echo_dns_context,
    _echo_dns_reference_links,
    _extract_response_header,
    _normalize_response_headers,
    _print_echo_dns_diagnostics,
    _print_echo_dns_reference_links,
    _print_echo_edge_details,
    _print_echo_timing_details,
    _render_debug_echo_failure,
)
from pollyweb_cli.features.echo_textual import (
    ComposeResult,
    Horizontal,
    Link,
    Static,
    TEXTUAL_AVAILABLE,
    Vertical,
    VerticalScroll,
    _EchoTextualApp,
    _EchoTextualSection,
    _should_use_textual_echo_view,
)
