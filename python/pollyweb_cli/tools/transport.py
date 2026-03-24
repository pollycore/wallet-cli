"""Wallet-backed message helpers shared by CLI commands."""

from __future__ import annotations

from dataclasses import replace
import http.client
import io
import json
from pathlib import Path
from threading import Lock
import time
from types import MethodType
from urllib.parse import urlsplit
import uuid

import urllib.error

from pollyweb import KeyPair, Msg, Wallet, normalize_domain_name
import pollyweb._transport as pollyweb_transport
import pollyweb.msg as pollyweb_msg
import yaml

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.debug import (
    parse_debug_payload,
    print_debug_json_payload,
    print_debug_payload,
)

DEFAULT_SCHEMA = "pollyweb.org/MSG:1.0"


DEFAULT_BINDS_PATH = Path.home() / ".pollyweb" / "binds.yaml"
DEFAULT_SEND_TIMEOUT_SECONDS = 100.0
PROXY_DOMAIN_SUBJECT = "Proxy@Domain"
WALLET_SEND_LOCK = Lock()


def serialize_wallet_response(response: object) -> str:
    """Convert a PollyWeb response object into the CLI's raw string form."""

    if isinstance(response, Msg):
        return json.dumps(response.to_dict(), separators=(",", ":"))
    if isinstance(response, dict):
        return json.dumps(response, separators=(",", ":"))
    return str(response)


def rewrite_backend_validation_error(
    message: str
) -> str:
    """Translate backend validation paths into the user's outbound payload shape."""

    rewritten_message = message

    for backend_path, user_path in (
        ("Body.Message.Header", "Outbound.Body.Header"),
        ("Body.Message.Body", "Outbound.Body.Body"),
        ("Body.Message", "Outbound.Body"),
    ):
        rewritten_message = rewritten_message.replace(
            backend_path,
            user_path)

    return rewritten_message


def _sanitize_proxy_message_header(
    body: dict[str, object]
) -> dict[str, object]:
    """Keep required proxied header fields and drop unsupported extras."""

    nested_header = body.get("Header")
    if not isinstance(nested_header, dict):
        return body

    normalized_to = nested_header.get("To")
    if not isinstance(normalized_to, str) or not normalized_to.strip():
        raise UserFacingError(
            "Missing Outbound.Body.Header.To."
        ) from None

    normalized_subject = nested_header.get("Subject")
    if not isinstance(normalized_subject, str) or not normalized_subject.strip():
        raise UserFacingError(
            "Missing Outbound.Body.Header.Subject."
        ) from None

    # The current broker contract routes proxied messages by `To` and
    # `Subject`. Extra user-supplied header fields such as `From` should not
    # make the request fail, so normalize the nested wire header down to the
    # required keys before sending.
    return {
        **body,
        "Header": {
            "To": normalized_to,
            "Subject": normalized_subject,
        },
    }


def normalize_proxy_domain_body(
    subject: str,
    body: dict[str, object]
) -> dict[str, object]:
    """Normalize known `Proxy@Domain` nested-message shapes before transport."""

    if subject != PROXY_DOMAIN_SUBJECT:
        return body

    normalized_body = _sanitize_proxy_message_header(body)
    nested_message = normalized_body.get("Message")
    if not isinstance(nested_message, dict):
        return normalized_body

    return {
        **normalized_body,
        "Message": _sanitize_proxy_message_header(nested_message),
    }


def build_debug_outbound_payload(
    wallet: Wallet,
    request_message: Msg,
    *,
    unsigned: bool = False
) -> dict[str, object]:
    """Render the actual outbound payload shape used by `wallet.send()`."""

    outbound_message = build_wallet_outbound_message(
        wallet,
        request_message,
        unsigned = unsigned)

    return outbound_message.to_dict()


def build_wallet_outbound_message(
    wallet: Wallet,
    request_message: Msg,
    *,
    unsigned: bool = False
) -> Msg:
    """Build the concrete outbound message for the current wallet mode."""

    if unsigned:
        return replace(
            request_message,
            From = wallet.ID,
            Selector = "",
            Algorithm = "",
            Hash = None,
            Signature = None)

    if wallet.ID == "Anonymous":
        return request_message

    return wallet.sign(request_message)


def _load_first_bind_for_domain(
    domain: str,
    binds_path: Path
) -> str | None:
    """Return the first stored bind UUID for a normalized domain."""

    if not binds_path.exists():
        return None

    loaded = yaml.safe_load(binds_path.read_text(encoding = "utf-8"))
    if not isinstance(loaded, list):
        return None

    normalized_domain = normalize_domain_name(domain)

    # Reuse the canonical recipient domain so `.dom` and `.pollyweb.org`
    # lookups find the same stored bind entry.
    for item in loaded:
        if not isinstance(item, dict):
            continue

        bind_value = item.get("Bind")
        bind_domain = item.get("Domain")

        if not isinstance(bind_value, str) or not isinstance(bind_domain, str):
            continue

        try:
            uuid.UUID(bind_value)
        except (ValueError, AttributeError, TypeError):
            continue

        if normalize_domain_name(bind_domain) == normalized_domain:
            return bind_value

    return None


def _resolve_wallet_sender(
    domain: str,
    from_value: str | None,
    binds_path: Path,
    *,
    anonymous: bool = False
) -> str | None:
    """Choose the wallet sender ID, preferring a stored bind over an empty sender."""

    if anonymous:
        return None

    if from_value not in (None, "", "Anonymous"):
        return str(from_value)

    stored_bind = _load_first_bind_for_domain(domain, binds_path)
    if stored_bind:
        return stored_bind

    if from_value == "Anonymous":
        return None

    return None


def build_wallet_request_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    *,
    schema_value: str | None = DEFAULT_SCHEMA
) -> tuple[Msg, str]:
    """Build one PollyWeb request message for the shared wallet send path."""

    normalized_domain = normalize_domain_name(domain)
    normalized_body = normalize_proxy_domain_body(
        subject,
        body)
    outbound_request: dict[str, object] = {
        "To": normalized_domain,
        "Subject": subject,
        "Body": normalized_body,
    }

    if schema_value is not None:
        outbound_request["Schema"] = schema_value

    return Msg.from_outbound(outbound_request), normalized_domain


def build_wallet_sender(
    domain: str,
    key_pair: KeyPair,
    from_value: str | None = "Anonymous",
    binds_path: Path | None = None,
    anonymous: bool = False
) -> tuple[Wallet, str]:
    """Create the wallet sender used for one outbound request."""

    normalized_domain = normalize_domain_name(domain)
    effective_binds_path = DEFAULT_BINDS_PATH if binds_path is None else binds_path
    sender_value = _resolve_wallet_sender(
        normalized_domain,
        from_value,
        effective_binds_path,
        anonymous = anonymous,
    )

    try:
        wallet_kwargs = {"KeyPair": key_pair}
        if sender_value is not None:
            wallet_kwargs["ID"] = sender_value

        wallet = Wallet(**wallet_kwargs)
    except ValueError:
        raise UserFacingError(
            "Wallet-backed commands only support `From: Anonymous` or a UUID bind value."
        ) from None

    return wallet, normalized_domain


def _extract_embedded_json_object(
    value: str
) -> object | None:
    """Extract one embedded JSON object or array from a longer string."""

    decoder = json.JSONDecoder()

    for index, character in enumerate(value):
        if character not in "[{":
            continue

        try:
            parsed_value, _ = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue

        if isinstance(parsed_value, (dict, list)):
            return parsed_value

    return None


def build_debug_http_error_payload(
    error_body: str | None
) -> object:
    """Build the debug payload shown for one HTTP error response."""

    if not isinstance(error_body, str) or not error_body.strip():
        return {}

    parsed_payload = parse_debug_payload(error_body)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    error_value = parsed_payload.get("error")
    if not isinstance(error_value, str) or not error_value.strip():
        return parsed_payload

    parsed_payload["error"] = rewrite_backend_validation_error(error_value)

    embedded_payload = _extract_embedded_json_object(error_value)
    if not isinstance(embedded_payload, dict):
        return parsed_payload

    nested_error = embedded_payload.get("error")
    debug_message_payload = dict(embedded_payload)
    concise_error = rewrite_backend_validation_error(error_value)

    if isinstance(nested_error, str) and nested_error.strip():
        concise_error = rewrite_backend_validation_error(nested_error)
        debug_message_payload["error"] = concise_error

    # Keep the server's returned message visible before the concise error
    # line so debug runs can show the full inbound payload and the final
    # extracted error detail side by side.
    return {
        "Message": debug_message_payload,
        **{
            key: value
            for key, value in parsed_payload.items()
            if key != "error"
        },
        "error": concise_error,
    }


def send_wallet_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    debug: bool = False,
    from_value: str | None = "Anonymous",
    schema_value: str | None = DEFAULT_SCHEMA,
    binds_path: Path | None = None,
    anonymous: bool = False,
    unsigned: bool = False,
    debug_json: bool = False,
    timing: dict[str, float] | None = None,
    transport_metadata: dict[str, object] | None = None
) -> tuple[str, Msg, str]:
    """Send one wallet-backed PollyWeb message and return the raw response."""

    wallet, normalized_domain = build_wallet_sender(
        domain = domain,
        key_pair = key_pair,
        from_value = from_value,
        binds_path = binds_path,
        anonymous = anonymous,
    )
    request_message, normalized_domain = build_wallet_request_message(
        domain = domain,
        subject = subject,
        body = body,
        schema_value = schema_value,
    )

    if debug:
        request_url = f"https://pw.{normalized_domain}/inbox"
        debug_printer = print_debug_json_payload if debug_json else print_debug_payload
        debug_printer(
            f"Outbound payload to {request_url}",
            build_debug_outbound_payload(
                wallet,
                request_message,
                unsigned = unsigned),
        )

    outbound_message = build_wallet_outbound_message(
        wallet,
        request_message,
        unsigned = unsigned)

    original_post = pollyweb_msg.post_json_bytes
    original_transport_post = pollyweb_transport.post_json_bytes
    original_pool_post = pollyweb_transport._HTTPS_CONNECTION_POOL.post

    def capture_pool_post(
        pool_self,
        url: str,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS
    ) -> bytes:
        """Mirror PollyWeb HTTPS transport while also collecting response metadata."""

        request_headers = {
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)

        parsed = urlsplit(url)
        if parsed.scheme != "https":
            raise ValueError("PollyWeb transport only supports https URLs")
        if not parsed.hostname:
            raise ValueError("PollyWeb transport requires a hostname")

        host = parsed.hostname
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        for attempt in range(2):
            connection = pool_self._get_connection(
                host,
                port,
                timeout = timeout)

            try:
                connection.request(
                    "POST",
                    path,
                    body = body,
                    headers = request_headers)
                response = connection.getresponse()
                raw = response.read()

                if transport_metadata is not None:
                    transport_metadata["http_status"] = response.status
                    transport_metadata["http_reason"] = response.reason
                    transport_metadata["request_url"] = url
                    transport_metadata["response_headers"] = dict(response.headers.items())

                if response.will_close:
                    pool_self._drop_connection(host, port)

                if response.status >= 400:
                    raise urllib.error.HTTPError(
                        url,
                        response.status,
                        response.reason,
                        response.headers,
                        io.BytesIO(raw))

                return raw
            except (
                OSError,
                http.client.HTTPException,
            ) as exc:
                pool_self._drop_connection(host, port)
                if attempt == 1:
                    raise urllib.error.URLError(exc) from exc

        raise RuntimeError("Unreachable HTTPS transport retry state")

    with WALLET_SEND_LOCK:
        try:
            if timing is not None:
                timing["client_timeout_seconds"] = DEFAULT_SEND_TIMEOUT_SECONDS

            if transport_metadata is not None:
                pollyweb_transport._HTTPS_CONNECTION_POOL.post = MethodType(
                    capture_pool_post,
                    pollyweb_transport._HTTPS_CONNECTION_POOL,
                )

            send_started_at = time.perf_counter()

            try:
                # PollyWeb currently reuses one cached HTTPSConnection per
                # host inside a process. Keep the send boundary serialized so
                # concurrent CLI test workers do not race that shared socket
                # or the temporary transport monkeypatches above.
                response = outbound_message.send()
                send_finished_at = time.perf_counter()
            except urllib.error.HTTPError as exc:
                send_finished_at = time.perf_counter()

                if timing is not None:
                    timing["network_seconds"] = send_finished_at - send_started_at

                error_body = None

                try:
                    error_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    error_body = None

                setattr(exc, "pollyweb_error_body", error_body)

                if debug:
                    try:
                        debug_printer = print_debug_json_payload if debug_json else print_debug_payload
                        debug_printer(
                            "Inbound payload",
                            build_debug_http_error_payload(error_body))
                        setattr(exc, "pollyweb_debug_error_payload_printed", True)
                    except Exception:
                        pass
                raise
            except Exception:
                send_finished_at = time.perf_counter()

                if timing is not None:
                    timing["network_seconds"] = send_finished_at - send_started_at

                raise

            if timing is not None:
                timing["network_seconds"] = send_finished_at - send_started_at

            response_payload = serialize_wallet_response(response)

            if debug:
                debug_printer = print_debug_json_payload if debug_json else print_debug_payload
                debug_printer("Inbound payload", parse_debug_payload(response_payload))

            return response_payload, request_message, normalized_domain
        finally:
            if transport_metadata is not None:
                pollyweb_transport._HTTPS_CONNECTION_POOL.post = original_pool_post
                pollyweb_msg.post_json_bytes = original_post
                pollyweb_transport.post_json_bytes = original_transport_post
