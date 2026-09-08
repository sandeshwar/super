"""TLS helpers for outbound HTTP (fetch_url, canvas frame probe)."""

from __future__ import annotations

import ssl
from typing import Any


def ssl_context() -> ssl.SSLContext:
    """Prefer certifi CA bundle; fall back to system defaults."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx


def urlopen(req: Any, *, timeout: float = 15):
    """urllib.urlopen with a reliable CA bundle on macOS/Python.org installs."""
    import urllib.request

    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
