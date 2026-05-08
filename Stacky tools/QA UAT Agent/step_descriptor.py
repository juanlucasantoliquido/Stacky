"""
step_descriptor.py — Build human-readable descriptions for screenshot steps.

For every screenshot in a UAT scenario, produce a short Spanish sentence
explaining what action the test performed at that step (and what was expected).

Inputs:
    - runner_output.json   (per-scenario stdout has lines like "[STEP 01] click btn_buscar")
    - scenarios.json       (each scenario has 'pasos' with action/target/valor and 'oraculos')

Output:
    Dict[scenario_id, List[StepDescription]] where each StepDescription is:
        {
            "screenshot": "<absolute path>",
            "screenshot_name": "step_00_setup.png",
            "step_index": 0 | 1 | ... | "final",
            "action": "navigate" | "click" | "fill" | ...   (when known)
            "target": "btn_buscar"                            (when known)
            "value":  "0001"                                  (when known)
            "description": "Se navegó a FrmAgenda.aspx para preparar la pantalla."
            "description_source": "llm" | "deterministic"
        }

Strategy:
  1. Build a deterministic baseline description from action/target/value + oracles.
     This always works (no network, no creds) and is the LLM fallback.
  2. If LLM credentials are available (gpt-5-mini via llm_client.call_llm),
     enrich each step's description in a single LLM call per scenario
     (batched: input = list of step facts, output = list of polished sentences).
  3. The "step_00_setup.png" screenshot maps to "preparación inicial".
     The "step_final_state.png" screenshot maps to "estado final tras ejecutar
     todos los pasos" (and should reference oracles when present).

This module is import-only (no CLI). Used from uat_dossier_builder and
ado_evidence_publisher.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.step_descriptor")

_STEP_LOG_RE = re.compile(r"\[STEP\s+(\d+)\]\s+(\S+)(?:\s+(.+))?", re.IGNORECASE)
_FINAL_STEP_NAMES = ("step_final_state.png", "step_final.png")
_SETUP_STEP_NAMES = ("step_00_setup.png", "step_setup.png")


# ── Public API ────────────────────────────────────────────────────────────────

def build_step_descriptions(
    runner_runs: list,
    scenarios: list,
    *,
    use_llm: bool = True,
    llm_model: str = "gpt-5-mini",
    llm_timeout: int = 60,
) -> dict[str, list[dict]]:
    """
    Returns {scenario_id: [StepDescription, ...]} aligned by screenshot list.

    Each scenario in `runner_runs` carries `artifacts.screenshots` (paths) and
    `raw_stdout` (Playwright JSON with [STEP NN] log lines).
    Each scenario in `scenarios` carries `pasos` (action/target/valor) and
    `oraculos` (assertions to validate).
    """
    scenario_index = {s.get("scenario_id"): s for s in scenarios or []}
    out: dict[str, list[dict]] = {}

    for run in runner_runs or []:
        sid = run.get("scenario_id") or ""
        scenario = scenario_index.get(sid, {})
        pasos = scenario.get("pasos") or []
        oraculos = scenario.get("oraculos") or []
        screenshots = (run.get("artifacts") or {}).get("screenshots") or []

        # Parse step lines from raw_stdout (more accurate than relying on indices).
        observed_steps = _extract_observed_steps(run.get("raw_stdout") or "")

        descriptions = []
        for shot_path in screenshots:
            shot_name = Path(shot_path).name.lower()
            step_meta = _resolve_step_for_shot(
                shot_name=shot_name,
                pasos=pasos,
                observed_steps=observed_steps,
            )
            base_desc = _baseline_description(
                shot_name=shot_name,
                step_meta=step_meta,
                scenario=scenario,
                oraculos=oraculos,
            )
            descriptions.append({
                "screenshot": shot_path,
                "screenshot_name": Path(shot_path).name,
                "step_index": step_meta.get("step_index"),
                "action": step_meta.get("action"),
                "target": step_meta.get("target"),
                "value": step_meta.get("value"),
                "description": base_desc,
                "description_source": "deterministic",
            })

        if use_llm and descriptions:
            enriched = _try_llm_polish(
                scenario=scenario,
                descriptions=descriptions,
                model=llm_model,
                timeout=llm_timeout,
            )
            if enriched is not None:
                descriptions = enriched

        out[sid] = descriptions

    return out


# ── Step parsing ──────────────────────────────────────────────────────────────

def _extract_observed_steps(raw_stdout: str) -> list[dict]:
    """Parse '[STEP NN] action target' lines that the playwright spec emitted."""
    if not raw_stdout:
        return []
    # raw_stdout may be a JSON-encoded Playwright report (single line, with
    # STEP markers buried in results[].stdout[].text — which uses literal '\\n'
    # escapes, not real newlines). Detect JSON first to avoid greedy plain-text
    # matches that swallow the rest of the report.
    lines: list[str] = []
    stripped = raw_stdout.lstrip()
    parsed_json = False
    if stripped.startswith("{"):
        try:
            doc = json.loads(raw_stdout)
            parsed_json = True
            for suite in (doc.get("suites") or []):
                for inner in (suite.get("suites") or [suite]):
                    for spec in (inner.get("specs") or []):
                        for test in (spec.get("tests") or []):
                            for res in (test.get("results") or []):
                                for so in (res.get("stdout") or []):
                                    txt = so.get("text") if isinstance(so, dict) else str(so)
                                    if txt and "[STEP" in txt:
                                        lines.extend(
                                            re.findall(r"\[STEP\s+\d+\][^\n]+", txt)
                                        )
        except Exception:
            parsed_json = False

    if not parsed_json:
        # Plain text path
        lines.extend(re.findall(r"\[STEP\s+\d+\][^\n]+", raw_stdout))

    parsed: list[dict] = []
    for ln in lines:
        m = _STEP_LOG_RE.search(ln)
        if not m:
            continue
        idx = int(m.group(1))
        action = (m.group(2) or "").strip()
        target = (m.group(3) or "").strip()
        # The convention is "[STEP NN] <action> <target>" — but for some actions
        # like "expand collapsible" the second token IS the target.
        parsed.append({
            "step_index": idx,
            "action": action,
            "target": target,
        })
    return parsed


def _resolve_step_for_shot(
    *,
    shot_name: str,
    pasos: list,
    observed_steps: list,
) -> dict:
    """Map a screenshot name to the step it represents."""
    if shot_name in _SETUP_STEP_NAMES:
        return {"step_index": "setup"}
    if shot_name in _FINAL_STEP_NAMES:
        return {"step_index": "final"}
    # step_NN_after.png  ->  observed_steps index NN (1-based)
    m = re.match(r"step_(\d+)_after\.png$", shot_name)
    if m:
        idx = int(m.group(1))  # 1-based
        # Prefer the live runtime log when available
        observed = next((o for o in observed_steps if o.get("step_index") == idx), None)
        if observed:
            return {
                "step_index": idx,
                "action": observed.get("action"),
                "target": observed.get("target"),
                "value": _value_for_step(idx, pasos),
            }
        # Fallback to the planned step
        if 0 < idx <= len(pasos):
            paso = pasos[idx - 1]
            return {
                "step_index": idx,
                "action": paso.get("accion"),
                "target": paso.get("target"),
                "value": paso.get("valor"),
            }
    return {"step_index": None}


def _value_for_step(idx: int, pasos: list) -> Optional[str]:
    if 0 < idx <= len(pasos):
        return pasos[idx - 1].get("valor")
    return None


# ── Baseline description (always available) ───────────────────────────────────

def _baseline_description(
    *,
    shot_name: str,
    step_meta: dict,
    scenario: dict,
    oraculos: list,
) -> str:
    """Generate a deterministic Spanish description from metadata."""
    pantalla = scenario.get("pantalla") or scenario.get("screen") or ""
    titulo = scenario.get("titulo") or ""
    si = step_meta.get("step_index")

    if si == "setup":
        if pantalla:
            return f"Preparación inicial: navegación a {pantalla} antes de ejecutar el escenario."
        return "Preparación inicial del escenario antes de ejecutar los pasos."

    if si == "final":
        oraculo_text = _oraculos_to_text(oraculos)
        if oraculo_text:
            return (
                f"Estado final tras ejecutar todos los pasos. Se valida que: {oraculo_text}."
            )
        if titulo:
            return f"Estado final tras ejecutar el escenario '{titulo}'."
        return "Estado final del escenario tras la ejecución completa."

    action = (step_meta.get("action") or "").lower()
    target = step_meta.get("target") or ""
    value = step_meta.get("value")
    return _action_to_phrase(action, target, value)


def _action_to_phrase(action: str, target: str, value) -> str:
    target_h = _humanize_target(target)
    if action in ("navigate", "goto"):
        return f"Navegar a {target or 'la pantalla'}."
    if action == "click":
        return f"Hacer click sobre {target_h}."
    if action == "fill":
        if value:
            return f"Completar {target_h} con el valor '{value}'."
        return f"Completar el campo {target_h}."
    if action in ("select", "select_by_value"):
        if value:
            return f"Seleccionar la opción '{value}' en {target_h}."
        return f"Seleccionar una opción en {target_h}."
    if action == "select_by_index":
        if value:
            return f"Seleccionar el ítem en posición {value} de {target_h}."
        return f"Seleccionar un ítem en {target_h}."
    if action == "expand":
        return f"Expandir el panel colapsable {target_h}."
    if action == "wait":
        return f"Esperar a que {target_h} cumpla la condición esperada."
    if action == "assert":
        return f"Verificar el estado de {target_h}."
    if action and target:
        return f"Ejecutar acción '{action}' sobre {target_h}."
    if action:
        return f"Ejecutar acción '{action}'."
    return "Paso intermedio del escenario."


def _humanize_target(target: str) -> str:
    if not target:
        return "el elemento"
    # Strip common prefixes for readability
    raw = target
    if target.startswith("input_"):
        return f"el campo '{target[len('input_'):]}'"
    if target.startswith("select_"):
        return f"el desplegable '{target[len('select_'):]}'"
    if target.startswith("btn_") or target.startswith("link_"):
        rest = target.split("_", 1)[1] if "_" in target else target
        return f"el botón '{rest}'"
    if target.startswith("grid_"):
        return f"la grilla '{target[len('grid_'):]}'"
    if target.startswith("msg_"):
        return f"el mensaje '{target[len('msg_'):]}'"
    return f"'{raw}'"


def _oraculos_to_text(oraculos: list) -> str:
    parts = []
    for o in oraculos or []:
        tipo = (o.get("tipo") or "").lower()
        target = _humanize_target(o.get("target") or "")
        valor = o.get("valor")
        if tipo == "visible":
            parts.append(f"{target} es visible")
        elif tipo == "not_visible":
            parts.append(f"{target} no es visible")
        elif tipo == "count_eq":
            parts.append(f"{target} contiene exactamente {valor} ítems")
        elif tipo == "count_gt":
            parts.append(f"{target} contiene más de {valor} ítems")
        elif tipo == "count_lt":
            parts.append(f"{target} contiene menos de {valor} ítems")
        elif tipo == "value_eq" and valor is not None:
            parts.append(f"{target} tiene el valor '{valor}'")
        elif tipo == "text_contains" and valor is not None:
            parts.append(f"{target} contiene el texto '{valor}'")
        else:
            parts.append(f"{target} cumple la regla {tipo}")
    return "; ".join(parts)


# ── Optional LLM polishing ────────────────────────────────────────────────────

def _try_llm_polish(
    *,
    scenario: dict,
    descriptions: list,
    model: str,
    timeout: int,
) -> Optional[list]:
    """Call gpt-5-mini to polish all step descriptions in one shot.

    Returns the same list with `description` replaced and `description_source`
    set to 'llm', or None if the LLM is unavailable (caller keeps deterministic).
    """
    try:
        from llm_client import call_llm, LLMError
    except Exception as exc:
        logger.debug("llm_client import failed: %s", exc)
        return None

    titulo = scenario.get("titulo") or scenario.get("scenario_id") or ""
    pantalla = scenario.get("pantalla") or ""
    payload = {
        "scenario": {
            "id": scenario.get("scenario_id"),
            "titulo": titulo,
            "pantalla": pantalla,
            "oraculos": scenario.get("oraculos") or [],
        },
        "steps": [
            {
                "n": i,
                "screenshot": d.get("screenshot_name"),
                "step_index": d.get("step_index"),
                "action": d.get("action"),
                "target": d.get("target"),
                "value": d.get("value"),
                "baseline": d.get("description"),
            }
            for i, d in enumerate(descriptions)
        ],
    }
    user = (
        "Para cada step de la lista, escribí UNA oración en español "
        "(máximo 180 caracteres) que explique en lenguaje natural qué se "
        "intentó hacer y, cuando aplique, qué se quería validar. "
        "Mantené el orden y devolvé estrictamente JSON con la forma "
        '{"steps":[{"n":0,"description":"..."},{"n":1,"description":"..."}]}'
        " sin texto adicional ni markdown.\n\n"
        f"Datos:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        result = call_llm(
            model=model,
            system=(
                "Eres un QA analyst senior que documenta evidencia UAT en "
                "español neutro y profesional. Devolvés solo JSON válido."
            ),
            user=user,
            max_tokens=900,
            timeout=timeout,
        )
    except LLMError as exc:
        logger.info("LLM polish unavailable, keeping deterministic descriptions: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected LLM error, keeping deterministic: %s", exc)
        return None

    raw = (result.get("text") or "").strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("LLM returned non-JSON, keeping deterministic: %s", exc)
        return None

    items = parsed.get("steps") if isinstance(parsed, dict) else None
    if not isinstance(items, list) or not items:
        return None

    by_n = {int(it.get("n", -1)): str(it.get("description") or "").strip()
            for it in items if isinstance(it, dict)}
    out = []
    for i, d in enumerate(descriptions):
        polished = by_n.get(i)
        if polished:
            out.append({**d, "description": polished[:300], "description_source": "llm"})
        else:
            out.append(d)
    return out
