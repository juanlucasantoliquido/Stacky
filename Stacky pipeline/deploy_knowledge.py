"""
deploy_knowledge.py — Knowledge base de deploys fallidos para Stacky.

Cuando el usuario reporta un problema post-deploy, Stacky lo registra
y aprende qué tipos de cambios causan problemas.

En futuros deploys similares, muestra advertencias basadas en incidentes pasados.

Almacena: knowledge/deploy_incidents.json
"""

import json
import re
from datetime import datetime
from pathlib import Path


BASE_DIR      = Path(__file__).parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
INCIDENTS_FILE = KNOWLEDGE_DIR / "deploy_incidents.json"


def _load() -> dict:
    if INCIDENTS_FILE.exists():
        try:
            return json.loads(INCIDENTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"incidents": [], "pattern_index": {}}


def _save(data: dict):
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    INCIDENTS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def report_incident(ticket_id: str, description: str,
                    files_deployed: list[str], severity: str = "medium") -> dict:
    """
    Registra un incidente post-deploy.
    severity: 'low' | 'medium' | 'high' | 'critical'
    """
    data = _load()
    incident = {
        "id":             f"INC-{len(data['incidents']) + 1:04d}",
        "ticket_id":      ticket_id,
        "ts":             datetime.now().isoformat(),
        "description":    description,
        "severity":       severity,
        "files_deployed": files_deployed,
        "resolved":       False,
        "patterns":       _extract_patterns(files_deployed, description),
    }
    data["incidents"].append(incident)

    # Actualizar índice de patrones
    for pattern in incident["patterns"]:
        if pattern not in data["pattern_index"]:
            data["pattern_index"][pattern] = []
        data["pattern_index"][pattern].append({
            "incident_id": incident["id"],
            "ticket_id":   ticket_id,
            "severity":    severity,
            "ts":          incident["ts"],
        })

    _save(data)
    return incident


def resolve_incident(incident_id: str, resolution_note: str = "") -> bool:
    """Marca un incidente como resuelto."""
    data = _load()
    for inc in data["incidents"]:
        if inc["id"] == incident_id:
            inc["resolved"]         = True
            inc["resolved_at"]      = datetime.now().isoformat()
            inc["resolution_note"]  = resolution_note
            _save(data)
            return True
    return False


def get_warnings_for_files(files: list[str]) -> list[dict]:
    """
    Dado un conjunto de archivos a deployar, retorna advertencias basadas
    en incidentes anteriores con archivos similares.
    """
    data     = _load()
    warnings = []
    seen     = set()

    for pattern in _extract_patterns(files, ""):
        if pattern in data["pattern_index"]:
            hits = [h for h in data["pattern_index"][pattern] if not _is_resolved(data, h["incident_id"])]
            if hits:
                msg = f"Patrón '{pattern}' causó problemas en {len(hits)} deploy(s) anterior(es)"
                if msg not in seen:
                    warnings.append({
                        "pattern":  pattern,
                        "message":  msg,
                        "severity": max(h["severity"] for h in hits),
                        "count":    len(hits),
                        "tickets":  list({h["ticket_id"] for h in hits})[:3],
                    })
                    seen.add(msg)

    warnings.sort(key=lambda w: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(w["severity"], 9))
    return warnings


def list_incidents(resolved: bool = None, limit: int = 50) -> list[dict]:
    """Lista incidentes. resolved=None para todos, True/False para filtrar."""
    data = _load()
    incidents = data.get("incidents", [])
    if resolved is not None:
        incidents = [i for i in incidents if i.get("resolved", False) == resolved]
    return list(reversed(incidents))[:limit]


def _extract_patterns(files: list[str], description: str) -> list[str]:
    """Extrae patrones identificables de los archivos y descripción."""
    patterns = set()

    for f in files:
        fp = Path(f)
        # Extension
        ext = fp.suffix.lower()
        if ext:
            patterns.add(f"ext:{ext}")
        # Nombre sin extension
        stem = fp.stem.lower()
        if stem:
            patterns.add(f"file:{stem}")
        # Carpeta padre
        parent = fp.parent.name.lower()
        if parent and parent not in (".", ""):
            patterns.add(f"dir:{parent}")
        # Tipo: dll/exe/aspx etc
        if ext in (".dll", ".exe"):
            patterns.add("type:binary")
        elif ext in (".aspx", ".ascx", ".master"):
            patterns.add("type:webform")
        elif ext == ".sql":
            patterns.add("type:sql")

    # Patrones de descripción
    desc_up = description.upper()
    if "SESSION" in desc_up or "SESIÓN" in desc_up:
        patterns.add("issue:session")
    if "LOGIN" in desc_up or "AUTH" in desc_up:
        patterns.add("issue:auth")
    if "SQL" in desc_up or "ORACLE" in desc_up or "BD" in desc_up:
        patterns.add("issue:database")
    if "NULL" in desc_up or "EXCEPTION" in desc_up or "ERROR" in desc_up:
        patterns.add("issue:exception")
    if "CACHE" in desc_up or "CACHÉ" in desc_up:
        patterns.add("issue:cache")

    return list(patterns)


def _is_resolved(data: dict, incident_id: str) -> bool:
    for inc in data.get("incidents", []):
        if inc["id"] == incident_id:
            return inc.get("resolved", False)
    return False
