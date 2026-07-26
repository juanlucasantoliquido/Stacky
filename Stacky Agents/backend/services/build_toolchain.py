"""Plan 201 F3 — Detección de toolchain de build + doctor.

Decide determinísticamente si esta máquina PUEDE compilar (MSBuild vía vswhere,
o `dotnet` en PATH). Si no puede, devuelve un "doctor" con la remediación exacta.

Este servicio **nunca instala nada**: solo reporta el comando. La instalación es
100% decisión del operador. Y nunca lanza: ante cualquier problema, doctor.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

_VSWHERE_REL = r"Microsoft Visual Studio\Installer\vswhere.exe"

_DOCTOR = {
    "available": False,
    "builder": None,
    "msbuild_path": None,
    "dotnet_path": None,
    "version": None,
    "remediation": {
        "message": ("No se encontró MSBuild ni .NET SDK. Instalá el .NET SDK o "
                    "Visual Studio Build Tools para compilar."),
        "command": "winget install --id Microsoft.DotNet.SDK.8 -e",
        "url": "https://dotnet.microsoft.com/download",
    },
}


def _doctor() -> dict:
    """Copia fresca del doctor (nunca se devuelve la constante mutable)."""
    payload = dict(_DOCTOR)
    payload["remediation"] = dict(_DOCTOR["remediation"])
    return payload


# ── Seams testeables (monkeypatch en tests: no dependemos del SO real) ───────

def _which(exe: str):
    return shutil.which(exe)


def _run(args: list, timeout: int = 20) -> tuple:
    """subprocess con LISTA de args — NUNCA un string de shell."""
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _vswhere_path():
    base = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    if not base:
        return None
    candidate = os.path.join(base, _VSWHERE_REL)
    return candidate if os.path.exists(candidate) else None


# ── API pública ──────────────────────────────────────────────────────────────

def detect_toolchain() -> dict:
    """Capacidad de build de esta máquina. Nunca lanza: si algo falla, doctor."""
    try:
        # 1) MSBuild vía vswhere (camino primario en Windows).
        vsw = _vswhere_path()
        if vsw:
            code, out, _err = _run([
                vsw, "-latest", "-products", "*",
                "-requires", "Microsoft.Component.MSBuild",
                "-find", r"MSBuild\**\Bin\MSBuild.exe",
            ])
            first = out.splitlines()[0].strip() if out.strip() else ""
            if code == 0 and first and os.path.exists(first):
                return {"available": True, "builder": "msbuild",
                        "msbuild_path": first, "dotnet_path": None,
                        "version": None, "remediation": None}

        # 2) dotnet en PATH.
        dn = _which("dotnet")
        if dn:
            code, out, _err = _run([dn, "--version"])
            if code == 0:
                return {"available": True, "builder": "dotnet",
                        "msbuild_path": None, "dotnet_path": dn,
                        "version": (out or "").strip(), "remediation": None}
    except Exception:  # noqa: BLE001 — subprocess roto/timeout: degradar a doctor
        logger.debug("detect_toolchain falló; se devuelve doctor", exc_info=True)

    # 3) Nada disponible → doctor.
    return _doctor()
