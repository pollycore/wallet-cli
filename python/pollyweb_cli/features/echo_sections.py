"""Section builders and debug renderers for `pw echo`."""

from __future__ import annotations

from dataclasses import asdict
import json
from urllib.parse import quote

from rich.syntax import Syntax
from rich.text import Text

from pollyweb_cli.features.echo_rendering import (
    _build_echo_error_footer_panel,
    _format_echo_success_metrics,
    _json_debug_copy_text,
    _raw_json_debug_text,
    _render_labeled_lines,
    _yaml_debug_renderable,
)
from pollyweb_cli.features.echo_textual import _EchoTextualApp, _EchoTextualSection, _should_use_textual_echo_view
from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    DEBUG_VALUE_STYLE,
    parse_debug_payload,
    print_debug_json_payload,
    print_debug_payload,
    print_labeled_value_lines,
    print_section_title,
)


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
        copy_text = _yaml_debug_renderable(payload).plain
        body = _yaml_debug_renderable(payload)

    return _EchoTextualSection(
        title = title,
        body = body,
        copy_text = copy_text,
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
    response_metadata: object | None = None,
    client_timeout_seconds: float | None = None
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

    if isinstance(client_timeout_seconds, (int, float)):
        lines["Client timeout budget"] = f"{client_timeout_seconds:.1f} s"

    if response_metadata is not None and hasattr(response_metadata, "get"):
        latency_ms = response_metadata.get("LatencyMs")
        if isinstance(latency_ms, int):
            lines["Remote latency"] = f"{latency_ms} ms"

        cold_ms = response_metadata.get("ColdMs")
        if isinstance(cold_ms, int):
            lines["Cold start"] = f"{cold_ms} ms"

        total_ms = response_metadata.get("TotalMs")
        if isinstance(total_ms, int):
            lines["Message total"] = f"{total_ms} ms"

        handler_ms = response_metadata.get("HandlerMs")
        if isinstance(handler_ms, int):
            lines["Message handler"] = f"{handler_ms} ms"

        total_execution_ms = response_metadata.get("TotalExecutionMs")
        if isinstance(total_execution_ms, int):
            lines["Total execution"] = f"{total_execution_ms} ms"

        downstream_execution_ms = response_metadata.get("DownstreamExecutionMs")
        if isinstance(downstream_execution_ms, int):
            lines["Downstream execution"] = f"{downstream_execution_ms} ms"

    return lines


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
    transport_metadata: dict[str, object],
    client_timeout_seconds: float | None = None
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
                        client_timeout_seconds = client_timeout_seconds,
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
    transport_metadata: dict[str, object],
    client_timeout_seconds: float | None = None
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
                    client_timeout_seconds = client_timeout_seconds,
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


def _print_echo_timing_details(
    *,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None = None,
    client_timeout_seconds: float | None = None
) -> None:
    """Render the echo timing details as a dedicated debug section."""

    print()
    print_section_title("Network timing")

    timing_lines = _build_echo_timing_lines(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata,
        client_timeout_seconds = client_timeout_seconds,
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
    client_timeout_seconds: float | None,
    response_metadata: object | None,
    transport_metadata: dict[str, object],
    header_panel
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
            header_panel = header_panel,
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
                client_timeout_seconds = client_timeout_seconds,
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
                client_timeout_seconds = client_timeout_seconds,
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
                client_timeout_seconds = client_timeout_seconds,
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            ),
            footer_panel = footer_panel,
            initial_payload_format = "yaml" if not debug_json else "raw",
        ).run()
        return 1

    if outbound_payload is not None:
        print_section_title(f"Outbound payload to https://pw.{domain}/inbox")
        if debug_json:
            print_debug_json_payload("Echo request", outbound_payload)
        else:
            DEBUG_CONSOLE.print(_yaml_debug_renderable(outbound_payload))

    if response_payload is not None:
        print_section_title("Inbound payload")
        if debug_json:
            print_debug_json_payload("Echo response", parse_debug_payload(response_payload))
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
        response_metadata = response_metadata,
        client_timeout_seconds = client_timeout_seconds)
    _print_echo_edge_details(transport_metadata)
    print()
    DEBUG_CONSOLE.print(footer_panel)
    print()
    return 1
