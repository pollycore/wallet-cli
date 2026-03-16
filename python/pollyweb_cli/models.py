"""Data models used by CLI features."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EchoResponse:
    """Normalized echo response fields used after verification."""

    From: str
    To: str
    Subject: str
    Correlation: str
    Schema: str
    Selector: str = ""
    Algorithm: str = ""
