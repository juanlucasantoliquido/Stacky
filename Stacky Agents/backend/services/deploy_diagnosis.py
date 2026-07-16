"""services/deploy_diagnosis.py — Plan 120 F6. Diagnóstico IA local (costo cero,
opt-in) de un deploy fallido. Reusa el MISMO camino de generación que
services/local_insights.py (copilot_bridge.invoke_local_llm) — sin cliente
HTTP propio. HITL: solo explica y sugiere, JAMÁS ejecuta ni edita nada.
"""
from __future__ import annotations

from datetime import datetime

from services.local_insights import HITL_RULES, truncate_middle

ERROR_MAX = 300
TLDR_MAX = 500


def build_diagnosis_prompt(entry: dict) -> str:
    """PURA. Los `steps` de un run de deploy JAMÁS contienen credenciales
    (diseño F2/F4: SR_PASS solo viaja por env del subprocess) — igual se
    trunca defensivamente cualquier stderr largo."""
    steps = entry.get("steps") or []
    failed_steps = [s for s in steps if s.get("ok") is False]
    lines = [
        "Sos un ingeniero DevOps senior que audita un deploy fallido de Stacky. "
        "Tu ÚNICA tarea es explicar la causa probable y sugerir una remediación, en JSON estricto."
        + HITL_RULES,
        "",
        "== DEPLOY ==",
        f"app_id: {entry.get('app_id')}",
        f"target: {entry.get('target')}",
        f"action: {entry.get('action')}",
        f"status: {entry.get('status')}",
        f"version_id: {entry.get('version_id')}",
        "",
        "== PASOS FALLIDOS ==",
    ]
    if not failed_steps:
        lines.append("(ninguno registrado; ver 'error' general)")
    for s in failed_steps:
        detail = truncate_middle(str(s.get("detail") or ""), head=1500, tail=1500)
        lines.append(f"- paso '{s.get('name')}': {detail}")
    lines += [
        "",
        "== ERROR GENERAL ==",
        (entry.get("error") or "")[:2000],
        "",
        ('Respondé EXCLUSIVAMENTE con un objeto JSON (sin markdown) con las keys: '
         '{"tldr": "explicación en castellano de 1-3 líneas", '
         '"probable_cause": "...", "remediation": "sugerencia concreta y accionable"}.'),
    ]
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.splitlines()
        if parts and parts[0].startswith("```"):
            parts = parts[1:]
        if parts and parts[-1].strip().startswith("```"):
            parts = parts[:-1]
        t = "\n".join(parts).strip()
    return t


def _parse_diagnosis_response(text: str) -> dict:
    import json
    data = json.loads(_strip_fences(text))
    if not isinstance(data, dict):
        raise ValueError("json_parse_error: not an object")
    tldr = data.get("tldr")
    if not isinstance(tldr, str) or not tldr.strip():
        raise ValueError("tldr_missing")

    def _field(key, cap):
        v = data.get(key)
        return v.strip()[:cap] if isinstance(v, str) and v.strip() else None

    return {
        "tldr": tldr.strip()[:TLDR_MAX],
        "probable_cause": _field("probable_cause", 500),
        "remediation": _field("remediation", 500),
    }


def diagnose_run(run_id: str) -> dict:
    """Gating de flag + health-gate del modelo local ANTES de invocar
    generación (patrón C2 plan 117: nunca 'quemar' el run con un intento
    inútil si el modelo está caído). Persiste `{"insight": {...}}` en el
    entry del ledger vía update_ledger_entry. NUNCA lanza."""
    import config as _config
    from services import deploy_store as store
    from services.local_insights import _local_llm_reachable

    cfg = _config.config
    if not getattr(cfg, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", False):
        return {"ok": False, "error": "ai_diagnosis_disabled"}

    rows = store.read_ledger(limit=5000)
    entry = next((r for r in rows if r.get("run_id") == run_id), None)
    if entry is None:
        return {"ok": False, "error": "run_not_found"}

    if not _local_llm_reachable():
        return {"ok": False, "error": "local_llm_unreachable"}

    prompt = build_diagnosis_prompt(entry)
    model_cfg = getattr(cfg, "LOCAL_LLM_MODEL", "")

    from copilot_bridge import invoke_local_llm
    try:
        resp = invoke_local_llm(
            agent_type="deploy_diagnosis",
            system="",
            user=prompt,
            on_log=lambda level, msg: None,
            execution_id=None,
        )
    except Exception as e:  # noqa: BLE001 — bridge caído: error legible, sin crash
        return {"ok": False, "error": "bridge_failed", "detail": str(e)[:ERROR_MAX]}

    try:
        parsed = _parse_diagnosis_response(resp.text)
    except Exception as e:  # noqa: BLE001 — respuesta corrupta: degrada sin crash
        return {"ok": False, "error": "parse_failed", "detail": str(e)[:ERROR_MAX]}

    insight = {
        **parsed,
        "model": (getattr(resp, "metadata", None) or {}).get("model") or model_cfg,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    store.update_ledger_entry(run_id, {"insight": insight})
    return {"ok": True, "insight": insight}
