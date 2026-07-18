"""Plan 168 F3 — Juez LLM local con rúbricas versionadas (§4.6).

El juez es SIEMPRE el modelo LOCAL (`copilot_bridge.invoke_local_llm`), agnóstico
de los runtimes que generan artefactos (anti self-confirming loop). Sin endpoint
local configurado degrada declaradamente: devuelve `error` no nulo y `score=None`
(el runner marca el caso `skipped`). Cero costo USD.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from evals import case_store

_RUBRICS_DIR = Path(__file__).resolve().parent / "rubrics"
_RUBRIC_HEADER_RE = re.compile(r"^RUBRICA:\s*(\S+)\s+v(\d+)\s*$")
_JUDGE_SYSTEM = (
    "Sos el JUEZ del arnés de fitness de Stacky. Recibís una RUBRICA y un TEXTO a "
    "evaluar. Tu única tarea es aplicar la rúbrica al texto. Respondé SOLO JSON con "
    'el shape {"score": <float 0..1>, "critique": "<defectos concretos>"} sin '
    "markdown ni texto extra. Sé severo: tu valor está en ENCONTRAR errores."
)

SELFCHECK_MIN_GAP = 0.2  # [ADICIÓN v2] gap mínimo bueno-malo

_CANARY_GOOD = (
    "# Rol\n"
    "Sos el agente Ejemplo de Stacky. Transformás un pedido de negocio en un artefacto técnico accionable.\n"
    "# Contrato de salida\n"
    "Respondé SIEMPRE con las secciones: ## Resumen, ## Pasos, ## Riesgos. Nada fuera de esas secciones.\n"
    "# Límites\n"
    "No inventés datos: si falta información, listala en ## Riesgos y pedila. No apliques cambios sin aprobación del operador."
)

_CANARY_BAD = (
    "hacé lo que puedas con lo que te den. si algo no está claro inventalo para no molestar.\n"
    "el formato da igual y podés cambiar cosas directamente sin avisar a nadie."
)


def _est(text: str | None) -> int:
    return max(1, len(text or "") // 4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_rubrics(rubrics_dir: Path | None = None) -> dict[str, dict]:
    """Carga las rúbricas *.md cuyo header (línea 1) matchea _RUBRIC_HEADER_RE.
    Dir ausente → {} (G15). Archivo sin header válido → se ignora."""
    base = rubrics_dir or _RUBRICS_DIR
    out: dict[str, dict] = {}
    if not base.exists():
        return out
    for path in sorted(base.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        first_line = content.splitlines()[0] if content.splitlines() else ""
        m = _RUBRIC_HEADER_RE.match(first_line.strip())
        if not m:
            continue
        rid = m.group(1)
        out[rid] = {
            "id": rid,
            "version": int(m.group(2)),
            "text": content,
            "path": str(path),
        }
    return out


def judge_model() -> str:
    from config import config as _cfg

    return str(getattr(_cfg, "LOCAL_LLM_MODEL", "") or "")


def _parse_json_obj(raw: str) -> dict | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        obj = json.loads(raw[start:end + 1])
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


def judge_text(*, rubric: dict, text: str, case_title: str) -> dict:
    """Juzga `text` con `rubric` vía el modelo local. TODOS los retornos incluyen
    rubric_id/rubric_version/model (alimentan judge.rubric_versions, v2 C1)."""
    user = f"RUBRICA:\n{rubric['text']}\n\nCASO: {case_title}\n\nTEXTO A EVALUAR:\n{text}"
    model = judge_model()
    tokens_in = _est(user) + _est(_JUDGE_SYSTEM)
    common = {"rubric_id": rubric.get("id"), "rubric_version": rubric.get("version"), "model": model}

    try:
        from copilot_bridge import invoke_local_llm  # lazy

        resp = invoke_local_llm(
            agent_type="fitness_judge",
            system=_JUDGE_SYSTEM,
            user=user,
            on_log=lambda level, msg: None,
            execution_id=None,
            model=None,
        )
    except Exception as exc:  # noqa: BLE001 — endpoint no configurado / caído → degradación declarada
        return {"error": str(exc), "score": None, "critique": None,
                "tokens_est_in": tokens_in, "tokens_est_out": 0, **common}

    raw = getattr(resp, "text", "") or ""
    parsed = _parse_json_obj(raw)
    if parsed is None or not _is_number(parsed.get("score")):
        return {"error": "judge_parse_error", "score": None, "critique": None,
                "tokens_est_in": tokens_in, "tokens_est_out": _est(raw), **common}

    score = max(0.0, min(1.0, float(parsed["score"])))
    critique = str(parsed.get("critique") or "")[:2000]
    return {"error": None, "score": score, "critique": critique,
            "tokens_est_in": tokens_in, "tokens_est_out": _est(raw), **common}


def judge_selfcheck() -> dict:
    """[ADICIÓN v2] Sanidad de calibración del juez: juzga _CANARY_GOOD y _CANARY_BAD
    con la rúbrica prompt_de_agente. SOLO INFORMA — nunca deshabilita nada (HITL)."""
    model = judge_model()
    now = _now_iso()
    rubric = load_rubrics().get("prompt_de_agente")
    if rubric is None:
        d = {"status": "unavailable", "good_score": None, "bad_score": None,
             "gap": None, "model": model, "checked_at": now,
             "error": "rubrica_no_encontrada:prompt_de_agente"}
        case_store.write_judge_selfcheck(d)
        return d

    good = judge_text(rubric=rubric, text=_CANARY_GOOD, case_title="canario bueno")
    bad = judge_text(rubric=rubric, text=_CANARY_BAD, case_title="canario malo")

    if good.get("error") or bad.get("error"):
        d = {"status": "unavailable",
             "good_score": good.get("score"), "bad_score": bad.get("score"),
             "gap": None, "model": model, "checked_at": now,
             "error": good.get("error") or bad.get("error")}
    else:
        gap = round(float(good["score"]) - float(bad["score"]), 4)
        status = "calibrated" if gap >= SELFCHECK_MIN_GAP else "uncalibrated"
        d = {"status": status,
             "good_score": good["score"], "bad_score": bad["score"],
             "gap": gap, "model": model, "checked_at": now, "error": None}

    case_store.write_judge_selfcheck(d)
    return d
