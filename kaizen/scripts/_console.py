#!/usr/bin/env python3
"""Helper de E/S portable — fuerza salida UTF-8 tolerante. stdlib pura.

En consolas Windows (cp1252) imprimir contenido unicode (acentos, flechas '→', etc.) lanza
UnicodeEncodeError y aborta el comando. Llamar enable_utf8() al inicio de cualquier script que
imprima contenido de sesiones evita ese fallo de forma portable (no-op en consolas ya UTF-8).
"""
from __future__ import annotations

import sys


def enable_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
