"""SUPER harness error hierarchy.

All recoverable failures surface as typed exceptions so CLI, server, and
gates can map them to exit codes / HTTP status without string matching.
Stdlib only.
"""

from __future__ import annotations


class SuperError(Exception):
    """Base for all harness errors."""


class ConfigError(SuperError):
    """Invalid or unreadable configuration."""


class StoreError(SuperError):
    """Persistent state unreadable or unwritable."""


class GateRejected(SuperError):
    """A gate refused the operation. Carries gate id and evidence."""

    def __init__(self, gate: str, detail: str = "") -> None:
        super().__init__(f"gate {gate} rejected: {detail}")
        self.gate = gate
        self.detail = detail


class VerificationError(SuperError):
    """Verification ladder failure (lint, type, tests, mutation)."""


class SecurityViolation(SuperError):
    """Taint, secret, SAST, dependency, or sink violation."""


class AmbitionError(SuperError):
    """Ambition Contract / done-state gate failure."""


class AuthError(SuperError):
    """Missing or invalid auth token."""


class LLMError(SuperError):
    """Model endpoint unreachable or returned an unusable response."""


class SandboxError(SuperError):
    """Sandbox setup, probe, or patch-application failure."""
