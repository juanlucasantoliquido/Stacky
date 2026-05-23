"""
services/secrets_store.py — Almacenamiento de secretos ligado al usuario local.

Objetivo:
  - Guardar PATs / tokens / passwords cifrados en disco.
  - Migrar automáticamente archivos legacy en texto plano al primer acceso.
  - Mantener compatibilidad con el formato histórico de Stacky Agents.

Formato recomendado:
  {
    "token": "<blob base64 DPAPI>",
    "token_format": "dpapi"
  }

Para Azure DevOps también soportamos:
  - pat_format = "preencoded"         (legacy)
  - pat_format = "dpapi_preencoded"   (migrado)
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ctypes import wintypes

logger = logging.getLogger("stacky_agents.secrets")

RAW_FORMAT = "raw"
PREENCODED_FORMAT = "preencoded"
DPAPI_FORMAT = "dpapi"
DPAPI_RAW_FORMAT = "dpapi_raw"
DPAPI_PREENCODED_FORMAT = "dpapi_preencoded"

_DPAPI_DESCRIPTION = "Stacky Agents secret"
_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")

try:
    import win32crypt  # type: ignore
except ImportError:  # pragma: no cover - depende del entorno
    win32crypt = None


class SecretsStoreError(RuntimeError):
    """Error del almacén de secretos local."""


@dataclass(slots=True)
class ResolvedSecret:
    value: str = ""
    storage_format: str | None = None
    is_preencoded: bool = False
    migrated: bool = False


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _ensure_windows() -> None:
    if os.name != "nt":
        raise SecretsStoreError("DPAPI sólo está disponible en Windows.")


def _blob_from_bytes(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buffer


def _protect_bytes_ctypes(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, _ = _blob_from_bytes(data)
    output_blob = _DATA_BLOB()

    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        _DPAPI_DESCRIPTION,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, wintypes.LPVOID))


def _unprotect_bytes_ctypes(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, _ = _blob_from_bytes(data)
    output_blob = _DATA_BLOB()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, wintypes.LPVOID))


def _protect_bytes(data: bytes) -> bytes:
    _ensure_windows()
    if win32crypt is not None:
        protected = win32crypt.CryptProtectData(data, _DPAPI_DESCRIPTION, None, None, None, 0)
        if isinstance(protected, tuple):
            protected = protected[1]
        return bytes(protected)
    return _protect_bytes_ctypes(data)


def _unprotect_bytes(data: bytes) -> bytes:
    _ensure_windows()
    if win32crypt is not None:
        unprotected = win32crypt.CryptUnprotectData(data, None, None, None, 0)
        if isinstance(unprotected, tuple):
            unprotected = unprotected[1]
        return bytes(unprotected)
    return _unprotect_bytes_ctypes(data)


def encrypt_secret(value: str) -> str:
    """Cifra un secreto con DPAPI y devuelve un blob base64."""
    if not value:
        return ""
    protected = _protect_bytes(value.encode("utf-8"))
    return base64.b64encode(protected).decode("ascii")


def decrypt_secret(blob_b64: str) -> str:
    """Descifra un blob base64 generado por `encrypt_secret`."""
    if not blob_b64:
        return ""
    try:
        encrypted = base64.b64decode(blob_b64.encode("ascii"))
    except Exception as exc:
        raise SecretsStoreError("Blob cifrado inválido.") from exc
    try:
        plain = _unprotect_bytes(encrypted)
    except Exception as exc:
        raise SecretsStoreError("No se pudo descifrar el secreto con DPAPI.") from exc
    return plain.decode("utf-8")


def load_json_file(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_json_file(path: str | Path, payload: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _looks_preencoded(value: str) -> bool:
    return len(value) >= 80 and bool(_B64_RE.match(value))


def set_encrypted_secret(
    payload: dict,
    field: str,
    value: str,
    *,
    format_field: str | None = None,
    preencoded: bool = False,
) -> None:
    payload[field] = encrypt_secret(value)
    if format_field:
        payload[format_field] = DPAPI_PREENCODED_FORMAT if preencoded else DPAPI_FORMAT


def resolve_secret_in_payload(
    payload: dict,
    field: str,
    *,
    format_field: str | None = None,
    allow_preencoded: bool = False,
    detect_preencoded: bool = False,
) -> ResolvedSecret:
    raw_value = str(payload.get(field) or "").strip()
    raw_format = str(payload.get(format_field) or "").strip().lower() if format_field else ""
    if not raw_value:
        return ResolvedSecret(storage_format=raw_format or None)

    if raw_format in {DPAPI_FORMAT, DPAPI_RAW_FORMAT}:
        return ResolvedSecret(
            value=decrypt_secret(raw_value),
            storage_format=raw_format,
        )

    if raw_format == DPAPI_PREENCODED_FORMAT:
        return ResolvedSecret(
            value=decrypt_secret(raw_value),
            storage_format=raw_format,
            is_preencoded=True,
        )

    migrated = False
    is_preencoded = False

    if raw_format == PREENCODED_FORMAT:
        if not allow_preencoded:
            raise SecretsStoreError(f"El campo '{field}' no soporta formato preencoded.")
        is_preencoded = True
    elif raw_format not in {"", RAW_FORMAT}:
        raise SecretsStoreError(f"Formato de secreto no soportado para '{field}': {raw_format}")
    elif allow_preencoded and detect_preencoded and _looks_preencoded(raw_value):
        is_preencoded = True

    set_encrypted_secret(
        payload,
        field,
        raw_value,
        format_field=format_field,
        preencoded=is_preencoded,
    )
    migrated = True
    return ResolvedSecret(
        value=raw_value,
        storage_format=payload.get(format_field) if format_field else None,
        is_preencoded=is_preencoded,
        migrated=migrated,
    )


def read_secret_from_file(
    path: str | Path,
    field: str,
    *,
    format_field: str | None = None,
    allow_preencoded: bool = False,
    detect_preencoded: bool = False,
) -> ResolvedSecret:
    payload = load_json_file(path)
    if not payload:
        return ResolvedSecret()

    result = resolve_secret_in_payload(
        payload,
        field,
        format_field=format_field,
        allow_preencoded=allow_preencoded,
        detect_preencoded=detect_preencoded,
    )
    if result.migrated:
        write_json_file(path, payload)
        logger.info("Secretos legacy migrados a DPAPI en %s", path)
    return result


__all__ = [
    "DPAPI_FORMAT",
    "DPAPI_PREENCODED_FORMAT",
    "DPAPI_RAW_FORMAT",
    "PREENCODED_FORMAT",
    "RAW_FORMAT",
    "ResolvedSecret",
    "SecretsStoreError",
    "decrypt_secret",
    "encrypt_secret",
    "load_json_file",
    "read_secret_from_file",
    "resolve_secret_in_payload",
    "set_encrypted_secret",
    "write_json_file",
]
