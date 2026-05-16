"""
runtime_guard.py - hard operational guardrails for QA UAT.

QA UAT is a consumer of the already-running Agenda Web instance. It must not
start, stop, restart, repair, or configure IIS Express / Visual Studio. This
module is intentionally small and dependency-free so command wrappers and
standalone scripts can import it before doing any side-effecting work.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union


_MANUAL_OVERRIDE_ENV = "STACKY_MANUAL_IIS_CONFIG_EDIT"
_MANUAL_OVERRIDE_VALUE = "I_UNDERSTAND"

_FORBIDDEN_TOKENS = (
    "iisexpress.exe",
    "devenv.exe",
    "taskkill",
    "stop-process",
    "start-process",
    "applicationhost.config",
    "fix_iis_config.py",
)

_FRT_WRITE_FLAGS = (
    "--enable-frt",
    "--disable-frt",
    "--iis-config",
)


@dataclass(frozen=True)
class RuntimeGuardViolation:
    reason: str
    token: str
    message: str


class RuntimeGuardError(RuntimeError):
    """Raised when QA UAT attempts forbidden runtime management."""

    def __init__(self, violation: RuntimeGuardViolation):
        super().__init__(violation.message)
        self.violation = violation
        self.reason = violation.reason
        self.token = violation.token

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "verdict": "BLOCKED",
            "category": "OPS",
            "reason": self.reason,
            "token": self.token,
            "message": str(self),
        }


def validate_command(cmd: Union[str, Sequence[object]]) -> None:
    """Block commands that would manage IIS Express, Visual Studio, or IIS config."""
    text = _command_to_text(cmd)
    lowered = text.lower()

    for token in _FORBIDDEN_TOKENS:
        if token in lowered:
            _raise(token)

    if "server_exception_monitor.py" in lowered:
        for flag in _FRT_WRITE_FLAGS:
            if flag in lowered:
                _raise(flag)


def validate_path(path: Union[str, Path]) -> None:
    """Block direct access to known IIS Express config paths from QA UAT."""
    lowered = str(path).lower()
    for token in ("applicationhost.config", "iisexpress\\config", "iisexpress/config"):
        if token in lowered:
            _raise(token)


def require_manual_iis_override() -> None:
    """Allow dangerous IIS maintenance only with an explicit out-of-band opt-in."""
    import os

    if os.environ.get(_MANUAL_OVERRIDE_ENV) == _MANUAL_OVERRIDE_VALUE:
        return
    _raise(_MANUAL_OVERRIDE_ENV)


def _command_to_text(cmd: Union[str, Sequence[object]]) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(str(part) for part in cmd)


def _raise(token: str) -> None:
    raise RuntimeGuardError(
        RuntimeGuardViolation(
            reason="FORBIDDEN_RUNTIME_MANAGEMENT",
            token=token,
            message=(
                "QA UAT no administra IIS Express, Visual Studio ni "
                "applicationhost.config. La Agenda Web debe quedar bajo control "
                f"humano. Intento bloqueado: {token}"
            ),
        )
    )
