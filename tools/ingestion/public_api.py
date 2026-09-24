#!/usr/bin/env python3
"""Shared safety helpers for read-only public API ingestion."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "LoteDiretor-PublicEvents/0.1 (+https://github.com/paulohspred/Lotediretor)"
DEFAULT_MAX_BYTES = 25 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_public_https(url: str, allowed_hosts: set[str]) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("only HTTPS public API URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("credentials embedded in URLs are not allowed")
    if parsed.hostname not in allowed_hosts:
        raise ValueError(f"host is not allowlisted: {parsed.hostname}")

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        }
    except socket.gaierror as exc:
        raise ValueError(
            f"hostname resolution failed for {parsed.hostname}: {exc}"
        ) from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(
                f"refusing non-public destination {parsed.hostname} -> {address}"
            )


class AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        validate_public_https(absolute, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def fetch_json(
    url: str,
    *,
    allowed_hosts: set[str],
    timeout: int = 60,
    max_bytes: int = DEFAULT_MAX_BYTES,
):
    validate_public_https(url, allowed_hosts)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    opener = urllib.request.build_opener(
        AllowlistedRedirectHandler(allowed_hosts)
    )
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        validate_public_https(final_url, allowed_hosts)
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"response exceeds max_bytes={max_bytes}")
        parsed = json.loads(body.decode("utf-8"))
        return {
            "body": body,
            "json": parsed,
            "status": getattr(response, "status", None),
            "final_url": final_url,
            "headers": dict(response.headers.items()),
        }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
