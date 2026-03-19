"""Wallet-backed message helpers shared by CLI commands."""

from __future__ import annotations

from dataclasses import replace
import http.client
import io
import json
from pathlib import Path
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


def serialize_wallet_response(response: object) -> str:
    """Convert a PollyWeb response object into the CLI's raw string form."""

    if isinstance(response, Msg):
        return json.dumps(response.to_dict(), separators=(",", ":"))
    if isinstance(response, dict):
        return json.dumps(response, separators=(",", ":"))
    return str(response)


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
    effective_schema = DEFAULT_SCHEMA if schema_value is None else schema_value

    return Msg(
        To = normalized_domain,
        Subject = subject,
        Body = body,
        Schema = effective_schema,
    ), normalized_domain


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
    message_kwargs: dict[str, object] = {
        "To": normalized_domain,
        "Subject": subject,
        "Body": body,
    }

    # Keep the CLI-side request build as thin as possible until the published
    # `pollyweb` library exposes a partial-outbound builder/parser path.
    if schema_value is not None:
        message_kwargs["Schema"] = schema_value

    request_message = Msg(**message_kwargs)

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
        timeout: float = 10.0
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

    try:
        if transport_metadata is not None:
            pollyweb_transport._HTTPS_CONNECTION_POOL.post = MethodType(
                capture_pool_post,
                pollyweb_transport._HTTPS_CONNECTION_POOL,
            )

        send_started_at = time.perf_counter()

        try:
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
                        parse_debug_payload(error_body))
                except Exception:
                    pass
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
