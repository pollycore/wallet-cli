"""Echo feature verification and command implementation."""

from __future__ import annotations

from dataclasses import asdict
import json
import time
import urllib.error
from pathlib import Path
from urllib.parse import quote

from pollyweb import Msg, MsgValidationError

from pollyweb_cli.tools.debug import (
    print_debug_payload,
    print_echo_response,
    print_labeled_value_lines,
)
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import (
    describe_bind_network_error,
    get_first_bind_for_domain,
    load_binds,
)
from pollyweb_cli.tools.transport import send_wallet_message


ECHO_SUBJECT = "Echo@Domain"
ALLOWED_ECHO_RESPONSE_FIELDS = frozenset({"Body", "Hash", "Header", "Signature"})


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
    print("External DNS checks:")
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
    print("Network timing:")
    print(f" - Total duration: {max(0, round(total_seconds * 1000))} ms")
    if total_seconds > 0:
        print(f" - Latency share: {(network_seconds / total_seconds) * 100:.0f}%")
    else:
        print(" - Latency share: 0%")


def _print_echo_edge_details(
    transport_metadata: dict[str, object]
) -> None:
    """Render best-effort CDN and edge-routing hints from HTTP transport."""

    print()
    print("Edge / CDN hints:")

    headers = _normalize_response_headers(transport_metadata)
    if not headers:
        print(" - Transport headers unavailable in this runtime")
        return

    provider = _detect_edge_provider(headers)
    pop_value = _detect_edge_pop(
        headers,
        provider = provider)

    request_url = transport_metadata.get("request_url")
    if isinstance(request_url, str) and request_url:
        print(f" - Request URL: {request_url}")

    http_status = transport_metadata.get("http_status")
    http_reason = transport_metadata.get("http_reason")
    if isinstance(http_status, int):
        if isinstance(http_reason, str) and http_reason:
            print(f" - HTTP status: {http_status} {http_reason}")
        else:
            print(f" - HTTP status: {http_status}")

    if provider is not None:
        print(f" - Edge provider: {provider}")
    else:
        print(" - Edge provider: no CDN fingerprint detected")

    if pop_value is not None:
        print(f" - Edge PoP: {pop_value}")
    else:
        print(" - Edge PoP: unavailable")

    server_value = headers.get("server")
    if server_value:
        print(f" - Server header: {server_value}")

    via_value = headers.get("via")
    if via_value:
        print(f" - Via header: {via_value}")

    x_cache_value = headers.get("x-cache")
    if x_cache_value:
        print(f" - X-Cache: {x_cache_value}")

    cloudfront_id = headers.get("x-amz-cf-id")
    if cloudfront_id:
        print(f" - CloudFront request ID: {cloudfront_id}")

    cf_ray_value = headers.get("cf-ray")
    if cf_ray_value:
        print(f" - Cloudflare Ray ID: {cf_ray_value}")


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

    if not debug:
        print(
            _format_echo_success_metrics(
                total_seconds = total_seconds,
                network_seconds = network_seconds)
        )
        return 0

    print_echo_response(response_payload)
    _print_echo_dns_diagnostics(dns_diagnostics)
    if dns_link_context is not None:
        _print_echo_dns_reference_links(*dns_link_context)
    print(f"Verified echo response from {domain}:")
    if verification is not None:
        print(f" - Schema validated: {verification.schema}")
        print(" - Required signed headers were present")
        print(" - Canonical payload hash matched the signed content")
        if verification.dns_lookup_used:
            print(
                f" - Signature verified via DKIM lookup for selector "
                f"{verification.selector} on {verification.from_value}"
            )
        else:
            print(" - Signature verified with the provided public key")
    else:
        print(f" - Schema validated: {response.Schema}")
        print(" - Required signed headers were present")
        print(" - Canonical payload hash matched the signed content")
        print(
            f" - Signature verified via DKIM lookup for selector {response.Selector} "
            f"on {response.From}"
        )
    print(f" - From matched expected domain: {response.From}")
    print(f" - To matched expected sender: {response.To}")
    print(f" - Subject matched expected echo subject: {response.Subject}")
    print(f" - Correlation matched the request: {response.Correlation}")
    _print_echo_timing_details(
        total_seconds = total_seconds,
        network_seconds = network_seconds)
    _print_echo_edge_details(transport_metadata)
    return 0
