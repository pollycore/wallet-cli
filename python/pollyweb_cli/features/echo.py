"""Echo feature verification and command implementation."""

from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version as get_installed_version
import json
import sys
import time
import urllib.error
from pathlib import Path
from urllib.parse import quote

from pollyweb import Msg, MsgValidationError
from rich.box import ROUNDED
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import yaml

try:
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from textual.widgets import Static
except ImportError:  # pragma: no cover - dependency is expected in runtime envs
    App = None
    ComposeResult = object
    VerticalScroll = None
    Static = None

from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    parse_debug_payload,
    print_debug_payload,
    print_labeled_value_lines,
    print_section_title,
    print_yaml_payload,
    _format_debug_value,
    DEBUG_PUNCTUATION_STYLE,
    DEBUG_SECTION_TITLE_STYLE,
    DEBUG_KEY_STYLE,
    DEBUG_VALUE_STYLE,
    render_debug_yaml,
)
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import (
    describe_bind_network_error,
    get_first_bind_for_domain,
    load_binds,
)
from pollyweb_cli.tools.transport import send_wallet_message
from pollyweb_cli.tools.transport import (
    build_debug_outbound_payload,
    build_wallet_sender,
)


ECHO_SUBJECT = "Echo@Domain"
ALLOWED_ECHO_RESPONSE_FIELDS = frozenset({"Body", "Hash", "Header", "Signature"})
CLI_PACKAGE_NAME = "pollyweb-cli"
TEXTUAL_AVAILABLE = App is not None


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
                "the inbound signed reply, the verification checks, DNS details, "
                "timing, and the final summary below so you can confirm delivery, "
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
    summary.add_column(width = 1)
    summary.add_column(ratio = 1)
    summary.add_row(
        Text(
            "✅ DKIM and DNSSEC" if dkim_and_dnssec_verified else "⏳ DKIM and DNSSEC",
            style = body_style,
        ),
        Text("│", style = accent_style),
        Text(
            f" {'✅ CDN distribution' if cdn_distribution_detected else '⏳ CDN distribution'}",
            style = body_style,
        ),
    )
    summary.add_row(
        Text("✅ Signed message", style = body_style),
        Text("│", style = accent_style),
        Text(
            f" ⏳ Duration {total_milliseconds} ms  Latency {latency_share:.0f}%",
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


def _yaml_debug_renderable(payload: object) -> Text:
    """Render one payload to the shared YAML-like debug renderable."""

    yaml_payload = yaml.dump(
        _format_debug_value(payload),
        sort_keys = False,
        allow_unicode = False,
        default_flow_style = False,
    ).rstrip()
    return render_debug_yaml(yaml_payload)


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
    network_seconds: float
) -> dict[str, str]:
    """Collect timing details for display."""

    lines = {"Total duration": f"{max(0, round(total_seconds * 1000))} ms"}
    if total_seconds > 0:
        lines["Latency share"] = f"{(network_seconds / total_seconds) * 100:.0f}%"
    else:
        lines["Latency share"] = "0%"
    return lines


def _build_echo_textual_sections(
    *,
    domain: str,
    debug: bool,
    outbound_payload: object | None,
    response_payload: str,
    dns_diagnostics,
    dns_link_context: tuple[str, str] | None,
    verification_lines: dict[str, str],
    total_seconds: float,
    network_seconds: float,
    transport_metadata: dict[str, object]
) -> list[tuple[str, str]]:
    """Build the section renderables shown in the Textual echo viewer."""

    sections: list[Group] = []

    if debug:
        sections.append(
            Group(
                _render_section_title(f"Outbound payload to https://pw.{domain}/inbox"),
                _yaml_debug_renderable(
                    {} if outbound_payload is None else outbound_payload
                ),
            )
        )
        sections.append(
            Group(
                _render_section_title("Inbound payload"),
                _yaml_debug_renderable(parse_debug_payload(response_payload)),
            )
        )
        sections.append(
            Group(
                _render_section_title(f"Verified echo response from {domain}"),
                _render_labeled_lines(verification_lines),
            )
        )
        if dns_diagnostics is not None:
            sections.append(
                Group(
                    _render_section_title("DNS verification diagnostics"),
                    _yaml_debug_renderable(asdict(dns_diagnostics)),
                )
            )
        if dns_link_context is not None:
            sections.append(
                Group(
                    _render_section_title("External DNS checks"),
                    _render_labeled_lines(_echo_dns_reference_links(*dns_link_context)),
                )
            )
        sections.append(
            Group(
                _render_section_title("Network timing"),
                _render_labeled_lines(
                    _build_echo_timing_lines(
                        total_seconds = total_seconds,
                        network_seconds = network_seconds,
                    )
                ),
            )
        )
        sections.append(
            Group(
                _render_section_title("Edge / CDN hints"),
                _render_labeled_lines(_build_echo_edge_lines(transport_metadata)),
            )
        )
    else:
        sections.append(
            Group(
                _render_section_title("Verified response"),
                Text(
                    _format_echo_success_metrics(
                        total_seconds = total_seconds,
                        network_seconds = network_seconds,
                    ),
                    style = DEBUG_VALUE_STYLE,
                ),
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

    .section {
        margin: 0 0 1 0;
    }
    """
    BINDINGS = [("q", "quit", "Quit"), ("escape", "quit", "Quit")]

    def __init__(self, *, header_panel: Panel, sections: list[Group], footer_panel: Panel) -> None:
        """Store the renderables needed by the echo viewer."""

        super().__init__()
        self._header_panel = header_panel
        self._sections = sections
        self._footer_panel = footer_panel

    def compose(self) -> ComposeResult:
        """Compose the reactive echo layout."""

        yield Static(self._header_panel, classes = "section")
        with VerticalScroll(id = "body"):
            for renderable in self._sections:
                yield Static(renderable, classes = "section")
        yield Static(self._footer_panel, classes = "section")


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
    diagnostics
) -> None:
    """Render DNS verification diagnostics for the echo debug path."""

    if diagnostics is None:
        return

    print_debug_payload(
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

def _to_echo_user_facing_error(
    exc: MsgValidationError,
    *,
    domain: str
) -> UserFacingError:
    """Translate library verification failures into echo-specific CLI wording."""

    message = str(exc)
    diagnostics = getattr(exc, "dns_diagnostics", None)

    if message.startswith("Unexpected top-level field(s):"):
        lowered_message = message[0].lower() + message[1:]
        return UserFacingError(
            f"Echo response from {domain} had {lowered_message}",
            diagnostics = diagnostics)

    if message.startswith("Unexpected "):
        return UserFacingError(
            f"Echo response from {domain} had an {message[0].lower() + message[1:]}",
            diagnostics = diagnostics)

    return UserFacingError(
        f"Echo response from {domain} did not verify: {message}",
        diagnostics = diagnostics)


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
    network_seconds: float
) -> None:
    """Render the echo timing details as a dedicated debug section."""

    print()
    print_section_title("Network timing")

    timing_lines = {
        "Total duration": f"{max(0, round(total_seconds * 1000))} ms",
    }
    if total_seconds > 0:
        timing_lines["Latency share"] = (
            f"{(network_seconds / total_seconds) * 100:.0f}%"
        )
    else:
        timing_lines["Latency share"] = "0%"

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

    if provider is not None:
        edge_lines["Edge provider"] = provider
    else:
        edge_lines["Edge provider"] = "no CDN fingerprint detected"

    if pop_value is not None:
        edge_lines["Edge PoP"] = pop_value
    else:
        edge_lines["Edge PoP"] = "unavailable"

    server_value = headers.get("server")
    if server_value:
        edge_lines["Server header"] = server_value

    via_value = headers.get("via")
    if via_value:
        edge_lines["Via header"] = via_value

    x_cache_value = headers.get("x-cache")
    if x_cache_value:
        edge_lines["X-Cache"] = x_cache_value

    cloudfront_id = headers.get("x-amz-cf-id")
    if cloudfront_id:
        edge_lines["CloudFront request ID"] = cloudfront_id

    cf_ray_value = headers.get("cf-ray")
    if cf_ray_value:
        edge_lines["Cloudflare Ray ID"] = cf_ray_value

    print_labeled_value_lines(
        edge_lines,
        prefix = " - ",
    )


def _describe_echo_network_error(
    domain: str,
    reason: object,
    *,
    debug: bool
) -> str:
    """Format echo transport failures for either normal or debug output."""

    if debug:
        if isinstance(reason, str):
            return reason

        return repr(reason)

    return describe_bind_network_error(
        domain,
        reason)


def cmd_echo(
    domain: str,
    *,
    debug: bool,
    config_dir,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Run the echo command and verify the signed response."""

    dns_diagnostics = None
    dns_link_context: tuple[str, str] | None = None
    timing: dict[str, float] = {}
    transport_metadata: dict[str, object] = {}
    started_at = time.perf_counter()

    if debug:
        _print_echo_header()

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        response_payload, request_message, normalized_domain = send_wallet_message(
            domain=domain,
            subject=ECHO_SUBJECT,
            body={},
            key_pair=key_pair,
            debug=debug,
            binds_path=binds_path,
            anonymous=anonymous,
            unsigned=unsigned,
            timing=timing,
            transport_metadata=transport_metadata,
        )
        if debug:
            dns_link_context = _echo_dns_context(
                response_payload,
                fallback_domain = normalized_domain)
        allowed_to = {normalized_domain}

        # Some hosts echo back the caller bind UUID instead of the target domain.
        stored_bind = get_first_bind_for_domain(
            normalized_domain,
            load_binds(binds_path))
        if stored_bind is not None:
            allowed_to.add(stored_bind)

        try:
            response = Msg.parse(
                response_payload,
                allowed_top_level_fields = ALLOWED_ECHO_RESPONSE_FIELDS)
        except MsgValidationError as exc:
            raise _to_echo_user_facing_error(
                exc,
                domain = normalized_domain) from None
        except Exception as exc:
            raise UserFacingError(
                f"Could not parse the echo response from {normalized_domain}: {exc}"
            ) from None

        try:
            verification = response.verify_details(
                expected_from = normalized_domain,
                expected_subject = ECHO_SUBJECT,
                expected_correlation = request_message.Correlation,
                allowed_to_values = allowed_to)
        except MsgValidationError as exc:
            raise _to_echo_user_facing_error(
                exc,
                domain = normalized_domain) from None

        dns_diagnostics = verification.dns_diagnostics
    except UserFacingError as exc:
        dns_diagnostics = getattr(exc, "diagnostics", dns_diagnostics)
        if debug:
            _print_echo_dns_diagnostics(dns_diagnostics)
            if dns_link_context is not None:
                _print_echo_dns_reference_links(*dns_link_context)
        raise
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Echo request to {domain} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = _describe_echo_network_error(
            domain,
            exc.reason,
            debug = debug)
        raise UserFacingError(
            f"Echo request to {domain} failed: {reason}"
        ) from None

    total_seconds = time.perf_counter() - started_at
    network_seconds = timing.get("network_seconds", 0.0)
    dns_queries = getattr(dns_diagnostics, "Queries", []) if dns_diagnostics is not None else []
    dnssec_verified = bool(dns_queries) and all(
        getattr(query, "AuthenticData", False) for query in dns_queries
    )
    cdn_detected = _detect_edge_provider(
        _normalize_response_headers(transport_metadata)
    ) is not None

    verification_lines: dict[str, str] = {}
    if verification is not None:
        verification_lines["Schema validated"] = verification.schema
        verification_lines["Required signed headers"] = "were present"
        verification_lines["Canonical payload hash"] = "matched the signed content"
        if verification.dns_lookup_used:
            verification_lines["Signature verified"] = (
                f"via DKIM lookup for selector {verification.selector} "
                f"on {verification.from_value}"
            )
        else:
            verification_lines["Signature verified"] = "with the provided public key"
    else:
        verification_lines["Schema validated"] = response.Schema
        verification_lines["Required signed headers"] = "were present"
        verification_lines["Canonical payload hash"] = "matched the signed content"
        verification_lines["Signature verified"] = (
            f"via DKIM lookup for selector {response.Selector} on {response.From}"
        )
    verification_lines["From matched expected domain"] = response.From
    verification_lines["To matched expected sender"] = response.To
    verification_lines["Subject matched expected echo subject"] = response.Subject
    verification_lines["Correlation matched the request"] = response.Correlation

    dkim_and_dnssec_verified = verification.dns_lookup_used and dnssec_verified
    outbound_payload = None
    if debug:
        wallet, _ = build_wallet_sender(
            normalized_domain,
            key_pair,
            binds_path = binds_path,
            anonymous = anonymous,
        )
        outbound_payload = build_debug_outbound_payload(
            wallet,
            request_message,
            unsigned = unsigned,
        )
    footer_panel = None
    if debug:
        footer_panel = _build_echo_footer_panel(
            total_seconds = total_seconds,
            network_seconds = network_seconds,
            dkim_and_dnssec_verified = dkim_and_dnssec_verified,
            cdn_distribution_detected = cdn_detected)

    if _should_use_textual_echo_view(debug = debug):
        _EchoTextualApp(
            header_panel = _build_echo_header_panel(),
            sections = _build_echo_textual_sections(
                domain = normalized_domain,
                debug = debug,
                outbound_payload = outbound_payload,
                response_payload = response_payload,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                verification_lines = verification_lines,
                total_seconds = total_seconds,
                network_seconds = network_seconds,
                transport_metadata = transport_metadata,
            ),
            footer_panel = footer_panel,
        ).run()
        return 0

    if not debug:
        print(
            _format_echo_success_metrics(
                total_seconds = total_seconds,
                network_seconds = network_seconds)
        )
        return 0

    print_section_title(f"Verified echo response from {domain}")
    print_labeled_value_lines(
        verification_lines,
        prefix = " - ",
    )
    _print_echo_dns_diagnostics(dns_diagnostics)
    if dns_link_context is not None:
        _print_echo_dns_reference_links(*dns_link_context)
    _print_echo_timing_details(
        total_seconds = total_seconds,
        network_seconds = network_seconds)
    _print_echo_edge_details(transport_metadata)
    print()
    DEBUG_CONSOLE.print(footer_panel)
    print()
    return 0
