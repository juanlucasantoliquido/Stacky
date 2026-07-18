"""services/devops_evidence.py — Plan 188. Evidencia determinista de fallos de deploy.

PURO respecto de la red: lee SOLO el ledger local vía services.deploy_store.
NUNCA importa requests/remote_exec/ci_variables. Sin LLM.

El masking (claves secretas + valores con pinta de token) se DELEGA en el
módulo común services.secret_masking (Plan 195) — este archivo NO redefine
prefijos de token ni sufijos de clave (una sola fuente de verdad).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from services import deploy_store
from services.secret_masking import mask_token_values, strip_secret_keys

SCHEMA_VERSION = "188.1"

MAX_SUMMARY_CHARS = 120
MAX_MODAL_TEXT_CHARS = 18_000      # margen bajo MAX_TEXT_LEN=20_000 (incident_store.py:26)
MAX_MARKDOWN_CHARS = 100_000
MAX_JSON_BYTES = 1_000_000
TAIL_LINES = 60                    # cola de stdout/stderr por paso
_TAIL_MAX_CHARS = 8_000            # tope defensivo por cola (una sola línea gigante)


@dataclass(frozen=True)
class EvidenceBundle:
    summary: str        # 1 línea ≤120 chars — título sugerido de la incidencia
    modal_text: str     # texto prellenado del modal (≤18.000 chars)
    markdown: str       # evidencia.md completa (≤100.000 chars)
    json_payload: dict  # evidencia.json estructurada (≤1 MB serializada)

    def to_dict(self) -> dict:
        return asdict(self)


def _lookup_run(app_id: str, target: str, run_id: str) -> dict | None:
    """C1/C2 — REGLA ÚNICA: espeja el acceso de la ruta /runs/<run_id>
    (devops_deployments.py:277-278): lee TODO el ledger (limit=5000) y busca
    por run_id, sin inventar un limit propio ni filtrar por app/target
    (el run_id es globalmente único). app_id/target quedan disponibles para
    el resto del builder."""
    rows = deploy_store.read_ledger(limit=5000)
    return next((r for r in rows if r.get("run_id") == run_id), None)


def build_deploy_failure_evidence(
    app_id: str,
    target: str,
    run_id: str,
    now: datetime | None = None,   # inyectable para tests deterministas (KPI-1)
) -> EvidenceBundle | None:
    """None si el run no existe. F0: bundle mínimo (summary + textos vacíos).
    F1 completa markdown/json/caps/masking."""
    entry = _lookup_run(app_id, target, run_id)
    if entry is None:
        return None
    now = now or datetime.now(timezone.utc)
    app = deploy_store.get_app(app_id) or {"id": app_id, "name": app_id}
    app_name = app.get("name") or app.get("id") or app_id
    version = entry.get("version_id") or entry.get("version") or "?"
    status = entry.get("status") or "?"
    summary = _cap(f"Despliegue fallido: {app_name} → {target} ({status}, v{version})",
                   MAX_SUMMARY_CHARS)
    return EvidenceBundle(summary=summary, modal_text=summary, markdown="", json_payload={})


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
