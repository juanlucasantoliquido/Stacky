"""services/devops_evidence.py — Plan 188. Evidencia determinista de fallos de deploy.

PURO respecto de la red: lee SOLO el ledger local vía services.deploy_store.
No importa clientes HTTP, ni ejecución remota, ni variables de CI. Sin LLM.
(El test de pureza verifica que este archivo no menciona esos módulos.)

El masking (claves secretas + valores con pinta de token) se DELEGA en el
módulo común services.secret_masking (Plan 195) — este archivo NO redefine
prefijos de token ni sufijos de clave (una sola fuente de verdad).
"""
from __future__ import annotations

import json
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
_JSON_TAIL_LINES = 20              # cola agresiva en el 2.º intento del cap de JSON
_STEP_TEXT_KEYS = ("stdout", "stderr", "detail")


@dataclass(frozen=True)
class EvidenceBundle:
    summary: str        # 1 línea ≤120 chars — título sugerido de la incidencia
    modal_text: str     # texto prellenado del modal (≤18.000 chars)
    markdown: str       # evidencia.md completa (≤100.000 chars)
    json_payload: dict  # evidencia.json estructurada (≤1 MB serializada)

    def to_dict(self) -> dict:
        return asdict(self)


# ── lookup (C1/C2) ────────────────────────────────────────────────────────────

def _lookup_run(app_id: str, target: str, run_id: str) -> dict | None:
    """C1/C2 — REGLA ÚNICA: espeja el acceso de la ruta /runs/<run_id>
    (devops_deployments.py:277-278): lee TODO el ledger (limit=5000) y busca
    por run_id, sin inventar un limit propio ni filtrar por app/target
    (el run_id es globalmente único). app_id/target quedan disponibles para
    el resto del builder."""
    rows = deploy_store.read_ledger(limit=5000)
    return next((r for r in rows if r.get("run_id") == run_id), None)


# ── helpers de texto/masking ─────────────────────────────────────────────────

def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _tail(text: str, n: int = TAIL_LINES) -> str:
    """Últimas n líneas de text ('' si vacío); prefija '… (truncado)' si se
    cortó (por líneas o por el tope defensivo de chars). El char-cap protege
    contra una única línea gigante que _tail por líneas no reduciría."""
    if not text:
        return ""
    lines = text.splitlines()
    truncated = len(lines) > n
    out = "\n".join(lines[-n:])
    if len(out) > _TAIL_MAX_CHARS:
        out = out[-_TAIL_MAX_CHARS:]
        truncated = True
    if truncated:
        out = "… (truncado)\n" + out
    return out


def _mask_text(value):
    return mask_token_values(value) if isinstance(value, str) else value


def _mask_step_text(step: dict) -> dict:
    """Enmascara valores con pinta de token en stdout/stderr/detail (in-place
    sobre la COPIA ya producida por strip_secret_keys)."""
    for k in _STEP_TEXT_KEYS:
        if isinstance(step.get(k), str):
            step[k] = mask_token_values(step[k])
    return step


def _mask_run(entry: dict) -> dict:
    """Copia profunda con claves secretas → '<omitido>' (por CLAVE) y valores
    con pinta de token en las colas → placeholder (por VALOR)."""
    masked = strip_secret_keys(entry)
    for step in masked.get("steps") or []:
        if isinstance(step, dict):
            _mask_step_text(step)
    return masked


def _mask_smoke(smoke):
    if not isinstance(smoke, dict):
        return smoke
    out = strip_secret_keys(smoke)
    if isinstance(out.get("detail"), str):
        out["detail"] = mask_token_values(out["detail"])
    return out


# ── builder principal ────────────────────────────────────────────────────────

def build_deploy_failure_evidence(
    app_id: str,
    target: str,
    run_id: str,
    now: datetime | None = None,   # inyectable para tests deterministas (KPI-1)
) -> EvidenceBundle | None:
    """None si el run no existe. Arma summary + markdown + json_payload sin
    secretos, con todos los caps respetados."""
    entry = _lookup_run(app_id, target, run_id)
    if entry is None:
        return None

    now = now or datetime.now(timezone.utc)
    generated_at = now.isoformat()
    app = deploy_store.get_app(app_id) or {"id": app_id, "name": app_id}
    app_name = app.get("name") or app.get("id") or app_id
    status = entry.get("status") or "?"
    version = entry.get("version_id") or entry.get("version") or "?"

    steps = entry.get("steps") or []
    smoke = entry.get("smoke")
    failed_step = next((s for s in steps if isinstance(s, dict) and not s.get("ok")), None)
    if failed_step is None and isinstance(smoke, dict) and smoke.get("ok") is False:
        failed_step = {"name": "smoke", "ok": False,
                       "kind": smoke.get("kind"), "detail": smoke.get("detail")}

    last_ok = deploy_store.last_success_version(app_id, target)
    prev_rows = deploy_store.read_ledger(app_id=app_id, target=target, limit=6)
    previous = [
        {"run_id": r.get("run_id"), "status": r.get("status"),
         "version": r.get("version_id") or r.get("version"),
         "started_at": r.get("started_at")}
        for r in prev_rows if r.get("run_id") != run_id
    ][:5]

    summary = _cap(f"Despliegue fallido: {app_name} → {target} ({status}, v{version})",
                   MAX_SUMMARY_CHARS)

    json_payload = _build_json(entry, app, target, generated_at, failed_step,
                               smoke, last_ok, previous)
    markdown = _build_markdown(app_name, target, entry, status, version,
                               failed_step, smoke, last_ok, previous, generated_at)

    base = summary + "\n\n" + markdown
    if len(base) > MAX_MODAL_TEXT_CHARS:
        sufijo = "\n\n[Evidencia completa en evidencia.md adjunta]"
        modal_text = base[: MAX_MODAL_TEXT_CHARS - len(sufijo)] + sufijo
    else:
        modal_text = base

    return EvidenceBundle(summary=summary, modal_text=modal_text,
                          markdown=markdown, json_payload=json_payload)


def _build_json(entry, app, target, generated_at, failed_step, smoke, last_ok, previous) -> dict:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "deploy_failure",
        "generated_at": generated_at,
        "app": {"id": app.get("id"), "name": app.get("name") or app.get("id")},
        "target": target,
        "run": _mask_run(entry),
        "failed_step": _mask_step_text(strip_secret_keys(failed_step)) if failed_step else None,
        "smoke": _mask_smoke(smoke),
        "last_success_version": last_ok,
        "previous_runs": previous,
    }
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_JSON_BYTES:
        # 2.º intento: cola agresiva de stdout/stderr/detail — los caps de
        # texto dominan el tamaño, así que este intento SIEMPRE alcanza.
        for step in payload["run"].get("steps") or []:
            _shrink_step(step)
        if isinstance(payload["failed_step"], dict):
            _shrink_step(payload["failed_step"])
    return payload


def _shrink_step(step: dict) -> None:
    for k in _STEP_TEXT_KEYS:
        if isinstance(step.get(k), str):
            step[k] = _tail(step[k], _JSON_TAIL_LINES)


def _build_markdown(app_name, target, entry, status, version, failed_step,
                    smoke, last_ok, previous, generated_at) -> str:
    started = entry.get("started_at") or "?"
    duration = entry.get("duration_ms")
    dur_txt = f"{duration} ms" if duration is not None else "?"

    lines: list[str] = [
        f"# Fallo de despliegue — {app_name} → {target}",
        "",
        "## Resumen",
        "",
        "| Campo | Valor |",
        "| --- | --- |",
        f"| Estado | {status} |",
        f"| Versión | {version} |",
        f"| Inicio | {started} |",
        f"| Duración | {dur_txt} |",
        f"| Última versión OK | {last_ok or '—'} |",
        "",
        "## Paso fallido",
        "",
    ]

    if failed_step is None:
        lines.append(f"No se identificó un paso fallido (estado del run: {status}).")
    elif failed_step.get("name") == "smoke":
        detail = failed_step.get("detail") or (smoke or {}).get("detail") or ""
        lines.append(f"Falló el smoke: {mask_token_values(str(detail))}")
    else:
        lines.append(f"**Paso:** {failed_step.get('name') or '?'}")
        rendered = False
        for label, key in (("stdout", "stdout"), ("stderr", "stderr")):
            val = failed_step.get(key)
            if isinstance(val, str) and val:
                lines += ["", f"{label}:", "```text", mask_token_values(_tail(val)), "```"]
                rendered = True
        detail = failed_step.get("detail")
        if not rendered and isinstance(detail, str) and detail:
            lines += ["", "detalle:", "```text", mask_token_values(_tail(detail)), "```"]

    lines += ["", "## Smoke", ""]
    if isinstance(smoke, dict):
        lines.append(f"- Tipo: {smoke.get('kind')}")
        lines.append(f"- OK: {smoke.get('ok')}")
        lines.append(f"- Detalle: {mask_token_values(str(smoke.get('detail') or ''))}")
    else:
        lines.append("No llegó al smoke.")

    lines += ["", "## Historial reciente", ""]
    if previous:
        lines.append("| Run | Estado | Versión | Inicio |")
        lines.append("| --- | --- | --- | --- |")
        for p in previous:
            lines.append(
                f"| {p.get('run_id')} | {p.get('status')} | {p.get('version')} | {p.get('started_at')} |"
            )
    else:
        lines.append("Sin corridas previas.")

    lines += ["", "## Siguientes pasos sugeridos", ""]
    lines.append("- Revisar el Doctor de la sección de Despliegues.")
    lines.append("- Comparar el drift del target.")
    if last_ok:
        lines.append(f"- Rollback disponible a v{last_ok} si corresponde.")
    else:
        lines.append("- Rollback no disponible (sin versión OK previa).")

    lines += ["", f"_Generado por Stacky · evidencia {SCHEMA_VERSION} · {generated_at}_"]

    md = "\n".join(lines)
    if len(md) > MAX_MARKDOWN_CHARS:
        md = md[:MAX_MARKDOWN_CHARS]
    return md
