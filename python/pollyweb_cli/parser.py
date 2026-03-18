"""Argument parser construction for the CLI entrypoint."""

from __future__ import annotations

import argparse


def add_wallet_send_flags(parser: argparse.ArgumentParser) -> None:
    """Attach the shared anonymous and unsigned send flags to one parser."""

    parser.add_argument(
        "--unsigned",
        action="store_true",
        help="Send without Hash or Signature fields.",
    )
    parser.add_argument(
        "--anonymous",
        action="store_true",
        help="Ignore stored binds and force From: Anonymous.",
    )


def build_parser(get_cli_version) -> argparse.ArgumentParser:
    """Construct the top-level command parser."""

    parser = argparse.ArgumentParser(
        prog="pw",
        description="PollyWeb command line wallet.",
    )
    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser(
        "version",
        help="Show the installed CLI version and exit.",
    )

    subparsers.add_parser(
        "upgrade",
        help="Force-install the latest published pollyweb-cli release.",
    )

    config_parser = subparsers.add_parser(
        "config",
        help="Generate a PollyWeb key pair in ~/.pollyweb.",
    )
    config_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing key pair.",
    )
    config_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound notifier payloads.",
    )

    bind_parser = subparsers.add_parser(
        "bind",
        help="Bind the configured wallet key to a domain.",
    )
    bind_parser.add_argument("domain", help="Domain that will receive the bind request.")
    bind_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound bind payloads.",
    )
    add_wallet_send_flags(bind_parser)

    echo_parser = subparsers.add_parser(
        "echo",
        help="Send an echo request to a domain and verify the signed response.",
    )
    echo_parser.add_argument(
        "domain",
        help="Domain that will receive the echo request.",
    )
    echo_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound echo payloads.",
    )
    add_wallet_send_flags(echo_parser)

    msg_parser = subparsers.add_parser(
        "msg",
        help="Send a signed message from a file, JSON object, or inline fields.",
    )
    msg_parser.add_argument(
        "message",
        nargs = "+",
        help="Message input as a file path, JSON object, or inline Key:Value fields.",
    )
    msg_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound message payloads.",
    )
    add_wallet_send_flags(msg_parser)

    test_parser = subparsers.add_parser(
        "test",
        help="Send a wrapped test fixture and verify the expected response.",
    )
    test_parser.add_argument(
        "path",
        nargs = "?",
        help="Path to a YAML test fixture with Outbound and optional Inbound sections.",
    )
    test_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound test payloads.",
    )
    add_wallet_send_flags(test_parser)

    shell_parser = subparsers.add_parser(
        "shell",
        help="Open an interactive shell against a domain.",
    )
    shell_parser.add_argument(
        "domain",
        help="Domain that will receive shell commands.",
    )
    shell_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound shell payloads.",
    )
    add_wallet_send_flags(shell_parser)

    chat_parser = subparsers.add_parser(
        "chat",
        help="Listen for notifier chat events on the configured wallet channel.",
    )
    chat_parser.add_argument(
        "domain",
        nargs = "?",
        help="Optional notifier domain that overrides Helpers.Notifier.",
    )
    chat_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print websocket connection and subscription details.",
    )
    chat_parser.add_argument(
        "--test",
        action="store_true",
        help="Publish a TEST message immediately after connecting.",
    )
    add_wallet_send_flags(chat_parser)

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync files from ~/.pollyweb/sync/{domain} to a domain.",
    )
    sync_parser.add_argument(
        "domain",
        help="Domain that will receive the sync request.",
    )
    sync_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound sync payloads.",
    )
    add_wallet_send_flags(sync_parser)

    return parser
