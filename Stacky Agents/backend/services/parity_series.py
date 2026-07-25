"""services/parity_series.py -- Plan 218 F7.

Lectura y validación del catálogo EJECUTABLE de la serie multi-proveedor
(docs/_roadmap/serie_paridad_218.json). PURO: solo lee JSON del disco.

Convierte el orquestador en un artefacto de datos validado por tests, para que el
orden, las dependencias y la propiedad de archivos no dependan de la memoria de nadie.
"""
from __future__ import annotations

import json
from pathlib import Path

_STACKY_ROOT = Path(__file__).resolve().parents[2]
_ROADMAP = _STACKY_ROOT / "docs" / "_roadmap"
_SERIES_PATH = _ROADMAP / "serie_paridad_218.json"
_ESTADO_REAL_PATH = _ROADMAP / "estado_real_serie_gitlab.json"

ESTADOS_REALES_VALIDOS: tuple[str, ...] = (
    "IMPLEMENTADO",
    "IMPLEMENTADO_PARCIAL",
    "IMPLEMENTADO_INALCANZABLE",
    "NO_IMPLEMENTADO",
)


def series_path() -> Path:
    return _SERIES_PATH


def estado_real_path() -> Path:
    return _ESTADO_REAL_PATH


def load_series() -> dict:
    return json.loads(_SERIES_PATH.read_text(encoding="utf-8"))


def load_estado_real() -> dict:
    return json.loads(_ESTADO_REAL_PATH.read_text(encoding="utf-8"))


def _by_number(series: dict) -> dict[int, dict]:
    return {int(s["number"]): s for s in series.get("subplans", [])}


def validate_series(series: dict) -> list[str]:
    """Devuelve la lista de violaciones (vacía = catálogo sano)."""
    violaciones: list[str] = []
    subplans = series.get("subplans") or []

    numeros = [int(s["number"]) for s in subplans]
    if len(numeros) != len(set(numeros)):
        violaciones.append("hay números de subplan duplicados")

    esperados = list(range(min(numeros), max(numeros) + 1)) if numeros else []
    faltantes = sorted(set(esperados) - set(numeros))
    if faltantes:
        violaciones.append(f"huecos en la numeración: {faltantes}")

    conocidos = set(numeros)
    hitos = {m["id"] for m in series.get("milestones", [])}
    duenos: dict[str, int] = {}

    for s in subplans:
        n = int(s["number"])
        for dep in s.get("depends_on", []):
            if int(dep) not in conocidos:
                violaciones.append(f"{n}: depende de {dep}, que no está en la serie")
        if s.get("priority") not in ("P0", "P1", "P2"):
            violaciones.append(f"{n}: prioridad inválida {s.get('priority')!r}")
        if s.get("milestone") not in hitos:
            violaciones.append(f"{n}: hito inexistente {s.get('milestone')!r}")
        for archivo in s.get("owns_files", []):
            if archivo in duenos:
                violaciones.append(
                    f"colisión de propiedad: '{archivo}' lo reclaman {duenos[archivo]} y {n}"
                )
            else:
                duenos[archivo] = n

    return violaciones


def topological_order(series: dict) -> list[int]:
    """Orden topológico por depends_on. Levanta ValueError si hay un ciclo."""
    porn = _by_number(series)
    pendientes = {n: {int(d) for d in s.get("depends_on", []) if int(d) in porn}
                  for n, s in porn.items()}
    orden: list[int] = []

    while pendientes:
        listos = sorted(n for n, deps in pendientes.items() if not deps)
        if not listos:
            raise ValueError(f"ciclo de dependencias entre {sorted(pendientes)}")
        for n in listos:
            orden.append(n)
            del pendientes[n]
        for deps in pendientes.values():
            deps.difference_update(listos)

    return orden
