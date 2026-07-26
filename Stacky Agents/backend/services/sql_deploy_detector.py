"""Plan 200 R2 — ¿este ticket o incidencia implica desplegar SQL en otro ambiente?

Determinista y sin red: nada de LLM ni heurística difusa. Un `.sql` adjunto es
evidencia dura; el texto solo cuenta si co-ocurren la INTENCIÓN de desplegar y
una SEÑAL de que el cambio es SQL. Pedir las dos cosas evita la fatiga de
alarmas: mencionar "producción" en un ticket cualquiera no puede encender el
badge, o el operador aprende a ignorarlo y el aviso deja de servir.

El detector nunca adivina el ambiente correcto: sugiere TODOS los registrados y
el operador elige. Inventar el destino de un DDL sería exactamente el tipo de
autonomía que este producto no hace.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = [
    "DeployNeed",
    "detect_for_incident",
    "detect_for_ticket",
    "read_script",
    "asdict",
]

_DEPLOY_INTENT = (
    r"desplegar", r"despliegue", r"deploy", r"aplicar\s+en", r"correr\s+en",
    r"producci[oó]n", r"\bQA\b", r"\bUAT\b", r"staging",
)
_SQL_SIGNAL = (
    r"\bscript\s+SQL\b", r"\.sql\b", r"\btabla\b", r"\bstored\s+procedure\b",
    r"\bprocedure\b", r"\bmigraci[oó]n\b", r"\bDDL\b", r"\bDML\b", r"\bschema\b",
)

_RE_INTENT = re.compile("|".join(_DEPLOY_INTENT), re.IGNORECASE)
_RE_SQL = re.compile("|".join(_SQL_SIGNAL), re.IGNORECASE)


@dataclass
class DeployNeed:
    requires: bool
    confidence: str                 # "alta" (hay .sql) | "posible" (keywords) | "no"
    scripts: list = field(default_factory=list)
    suggested_environments: list = field(default_factory=list)
    reason: str = ""


def _suggested_envs() -> list:
    try:
        from services import dbcompare_registry

        return [e["alias"] for e in dbcompare_registry.list_environments()]
    except Exception:  # noqa: BLE001 — sin comparador configurado, no hay sugerencias
        return []


def _texto_dispara(texto: str) -> bool:
    """Ambas señales, no una: 'revisar el ambiente de producción' no es un deploy SQL."""
    texto = texto or ""
    return bool(_RE_INTENT.search(texto)) and bool(_RE_SQL.search(texto))


def _sin_necesidad() -> DeployNeed:
    return DeployNeed(requires=False, confidence="no", reason="sin señales de despliegue SQL")


def detect_for_incident(incident: dict) -> DeployNeed:
    scripts = [
        {"name": f.get("name"), "sha256": f.get("sha256"), "source": "incident_attachment"}
        for f in (incident or {}).get("files") or []
        if (f.get("ext") or "").lower() == ".sql"
    ]

    if scripts:
        return DeployNeed(
            requires=True, confidence="alta", scripts=scripts,
            suggested_environments=_suggested_envs(),
            reason=f"{len(scripts)} script(s) .sql adjuntos a la incidencia",
        )

    if _texto_dispara((incident or {}).get("text") or ""):
        return DeployNeed(
            requires=True, confidence="posible", scripts=[],
            suggested_environments=_suggested_envs(),
            reason="el texto menciona desplegar y un cambio de tipo SQL, pero no hay .sql adjunto",
        )

    return _sin_necesidad()


def detect_for_ticket(ticket, output_dir) -> DeployNeed:
    scripts = []
    if output_dir:
        base = Path(output_dir)
        if base.is_dir():
            for archivo in sorted(base.rglob("*.sql")):
                try:
                    datos = archivo.read_bytes()
                except OSError:
                    continue
                scripts.append({
                    "name": archivo.name,
                    "sha256": hashlib.sha256(datos).hexdigest(),
                    "source": "ticket_output",
                })

    if scripts:
        return DeployNeed(
            requires=True, confidence="alta", scripts=scripts,
            suggested_environments=_suggested_envs(),
            reason=f"{len(scripts)} script(s) .sql en la salida del ticket",
        )

    texto = " ".join(str(getattr(ticket, campo, "") or "")
                     for campo in ("title", "description"))
    if _texto_dispara(texto):
        return DeployNeed(
            requires=True, confidence="posible", scripts=[],
            suggested_environments=_suggested_envs(),
            reason="el ticket menciona desplegar y un cambio de tipo SQL, pero no hay .sql generado",
        )

    return _sin_necesidad()


def read_script(ref: dict) -> dict | None:
    """Re-lee un `.sql` server-side POR REFERENCIA, recomputando su sha256.

    Es la misma fuente que usa el preview y la que usaría la ejecución: leer del
    disco en vez de confiar en lo que manda el cliente es lo que impide que
    alguien ejecute un SQL distinto del que se aprobó.
    """
    ref = ref or {}
    origen = ref.get("source")
    sha_esperado = (ref.get("sha256") or "").lower()

    ruta = None
    if origen == "incident_attachment":
        from services import incident_store

        incidencia = incident_store.get_incident(ref.get("incident_id") or "")
        if incidencia is None:
            return None
        for archivo in incidencia.get("files") or []:
            if (archivo.get("sha256") or "").lower() == sha_esperado:
                ruta = (incident_store.incidents_root() / incidencia["id"]
                        / archivo["stored_name"])
                nombre = archivo.get("name")
                break
        else:
            return None
    elif origen == "ticket_output":
        base = ref.get("output_dir")
        nombre = ref.get("name") or ""
        if not base or not nombre:
            return None
        ruta = Path(base) / Path(nombre).name   # sin traversal
    else:
        return None

    if ruta is None or not Path(ruta).is_file():
        return None

    contenido = Path(ruta).read_bytes()
    sha_real = hashlib.sha256(contenido).hexdigest()
    if sha_esperado and sha_real != sha_esperado:
        # El archivo cambió desde que se listó: devolver el contenido nuevo bajo
        # el sha viejo sería exactamente cómo se ejecuta algo no aprobado.
        return None

    return {
        "name": nombre,
        "sha256": sha_real,
        "sql_text": contenido.decode("utf-8", errors="replace"),
    }
