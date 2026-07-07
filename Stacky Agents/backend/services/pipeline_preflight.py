"""pipeline_preflight.py — Plan 93. Checks PUROS (sin I/O, sin config, sin flags).

El contrato de check es compartido por F2/F3:
{"id": str, "status": "ok"|"warn"|"fail"|"unavailable",
 "title": str_en_llano, "detail": str, "fix_hint": str}
"""
from __future__ import annotations

import re

# Literales EXACTOS de la serie (si 87/88 cambian sus defaults, actualizar AQUÍ
# y en el test test_f1_placeholder_literals_frozen en el mismo commit):
PLACEHOLDER_LITERALS = (
    'echo "reemplazar por el comando real"',          # 87 starterSpec (C11)
    'echo "[stacky] publicar ',                        # 88 §4 templates default (prefijo)
)

# Variables predefinidas que NUNCA cuentan como "sin definir":
_GITLAB_PREDEFINED_PREFIXES = ("CI_", "GITLAB_")
_ADO_PREDEFINED_PREFIXES = ("Build.", "Agent.", "System.", "Pipeline.", "Environment.")

# [C14] negative lookbehind: `$$VAR` es el ESCAPE de GitLab (dólar literal), no una referencia.
_GITLAB_VAR_RE = re.compile(r"(?<!\$)\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_ADO_VAR_RE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_.]*)\)")


def _iter_steps(spec_dict: dict):
    """Itera (stage_name, job_name, step_dict) sobre stages[].jobs[].steps[]. PURA."""
    for stage in spec_dict.get("stages") or []:
        stage_name = stage.get("name", "")
        for job in stage.get("jobs") or []:
            job_name = job.get("name", "")
            for step in job.get("steps") or []:
                yield stage_name, job_name, step


def check_placeholders(spec_dict: dict) -> dict:
    """id FIJO: 'placeholders' [C10]. Recorre stages[].jobs[].steps[].script; un
    step es placeholder si su script (strip) es igual a un literal de
    PLACEHOLDER_LITERALS o empieza con el prefijo.
    0 matches -> status 'ok'. N>0 -> 'warn' con title
    'N paso(s) siguen con el comando de ejemplo' y fix_hint que nombra los steps
    (stage/job/step) y dice 'reemplazá el script por el comando real de deploy'."""
    matches: list[str] = []
    for stage_name, job_name, step in _iter_steps(spec_dict):
        script = (step.get("script") or "").strip()
        if not script:
            continue
        is_placeholder = any(
            script == literal or script.startswith(literal) for literal in PLACEHOLDER_LITERALS
        )
        if is_placeholder:
            step_name = step.get("name", "")
            matches.append(f"{stage_name}/{job_name}/{step_name}")

    if not matches:
        return {
            "id": "placeholders",
            "status": "ok",
            "title": "Steps placeholder",
            "detail": "Ningún step quedó con el comando de ejemplo.",
            "fix_hint": "",
        }

    n = len(matches)
    paso_word = "paso" if n == 1 else "pasos"
    return {
        "id": "placeholders",
        "status": "warn",
        "title": f"{n} {paso_word} siguen con el comando de ejemplo",
        "detail": (
            f"El pipeline va a correr pero no va a desplegar nada real: "
            f"{', '.join(matches)}"
        ),
        "fix_hint": "Reemplazá el script por el comando real de deploy en: " + ", ".join(matches),
    }


def referenced_variables(spec_dict: dict, target: str) -> set[str]:
    """target 'gitlab' -> _GITLAB_VAR_RE sobre cada script; 'ado' -> _ADO_VAR_RE.
    Excluye las predefinidas por prefijo (case-sensitive GitLab, case-insensitive
    ADO). PURA."""
    pattern = _GITLAB_VAR_RE if target == "gitlab" else _ADO_VAR_RE
    predefined_prefixes = _GITLAB_PREDEFINED_PREFIXES if target == "gitlab" else _ADO_PREDEFINED_PREFIXES

    found: set[str] = set()
    for _stage_name, _job_name, step in _iter_steps(spec_dict):
        script = step.get("script") or ""
        for line in script.splitlines():
            for match in pattern.finditer(line):
                name = match.group(1)
                if target == "gitlab":
                    if any(name.startswith(p) for p in predefined_prefixes):
                        continue
                else:
                    if any(name.lower().startswith(p.lower()) for p in predefined_prefixes):
                        continue
                found.add(name)
    return found


def check_undefined_variables(
    spec_dict: dict, target: str, defined_keys: list[str] | None = None
) -> dict:
    """id FIJO: 'variables' [C10] (F3 lo re-etiqueta 'variables_{target}').
    defined = keys de spec.variables + keys de jobs[].variables + defined_keys
    (aporte OPCIONAL del plan 94 — puede ser None). Las referenciadas y no
    definidas -> 'warn' (no 'fail': pueden venir del entorno del runner) listando
    las keys; vacío -> 'ok'."""
    referenced = referenced_variables(spec_dict, target)

    defined: set[str] = set((spec_dict.get("variables") or {}).keys())
    for stage in spec_dict.get("stages") or []:
        for job in stage.get("jobs") or []:
            defined |= set((job.get("variables") or {}).keys())
    if defined_keys:
        defined |= set(defined_keys)

    missing = sorted(referenced - defined)

    if not missing:
        return {
            "status": "ok",
            "title": "Variables referenciadas",
            "detail": "Todas las variables referenciadas están definidas.",
            "fix_hint": "",
        }

    return {
        "status": "warn",
        "title": f"{len(missing)} variable(s) referenciadas sin definir",
        "detail": (
            f"Se usan pero no están en spec.variables: {', '.join(missing)} "
            "(pueden venir del entorno del runner)."
        ),
        "fix_hint": f"Definí {', '.join(missing)} en las variables del pipeline si no las provee el runner.",
    }


def normalize_check(raw: dict, check_id: str, title: str) -> dict:
    """[C6] Completa el CONTRATO de check (el TS PreflightCheck declara los campos
    obligatorios): fuerza id=check_id y title=title; detail=raw.get('detail','');
    fix_hint=raw.get('fix_hint',''); si raw trae 'errors' (lint), los concatena al
    detail con '; '. Nunca devuelve keys faltantes. PURA."""
    detail = str(raw.get("detail") or "")
    errors = raw.get("errors")
    if errors:
        errors_str = "; ".join(str(e) for e in errors)
        detail = f"{detail}; {errors_str}" if detail else errors_str

    return {
        "id": check_id,
        "status": raw.get("status", "unavailable"),
        "title": title,
        "detail": detail,
        "fix_hint": str(raw.get("fix_hint") or ""),
    }


def runners_check(runners_result: dict, spec_dict: dict) -> dict:
    """[C4] id FIJO: 'runners'. Cruza los runner_tags de cada job contra los
    runners online de runners_result (contrato F2). Reglas:
    - runners_result['status'] == 'unavailable' -> propaga unavailable (mismo detail).
    - jobs SIN tags pedidos -> 'ok' si hay >=1 runner online (o hosted); 'warn' en
      llano si hay 0.
    - jobs CON tags: 'fail' "Ningún runner online atiende los tags [x, y]" si NO
      matchea ninguno; PERO si algún runner online tiene tags desconocidas
      (tags is None, ver F2 [C2]), degrada a 'unavailable' con detail en llano —
      NUNCA falso rojo.
    PURA (sin I/O)."""
    if runners_result.get("status") == "unavailable":
        return {
            "id": "runners",
            "status": "unavailable",
            "title": "Runners/agents disponibles",
            "detail": str(runners_result.get("detail") or ""),
            "fix_hint": "",
        }

    runners = runners_result.get("runners") or []
    online = [r for r in runners if r.get("online")]

    # Tags pedidas por cualquier job del spec
    requested_tags: set[str] = set()
    for stage in spec_dict.get("stages") or []:
        for job in stage.get("jobs") or []:
            requested_tags |= set(job.get("runner_tags") or ())

    if not requested_tags:
        if online:
            return {
                "id": "runners",
                "status": "ok",
                "title": "Runners/agents disponibles",
                "detail": f"{len(online)} runner(s)/agent(s) online.",
                "fix_hint": "",
            }
        return {
            "id": "runners",
            "status": "warn",
            "title": "Sin runners/agents online",
            "detail": "No hay ningún runner/agent online en este momento.",
            "fix_hint": "Verificá que al menos un runner/agent esté encendido y conectado.",
        }

    unknown_tags = any(r.get("tags") is None for r in online)

    matching = [
        r for r in online
        if r.get("tags") is not None and requested_tags.issubset(set(r.get("tags") or ()))
    ]

    if matching:
        return {
            "id": "runners",
            "status": "ok",
            "title": "Runners/agents disponibles",
            "detail": f"{len(matching)} runner(s) online atienden los tags {sorted(requested_tags)}.",
            "fix_hint": "",
        }

    if unknown_tags:
        return {
            "id": "runners",
            "status": "unavailable",
            "title": "Runners/agents disponibles",
            "detail": (
                "No se pudieron confirmar los tags de todos los runners online — "
                "no se puede verificar si atienden "
                f"{sorted(requested_tags)}."
            ),
            "fix_hint": "",
        }

    return {
        "id": "runners",
        "status": "fail",
        "title": "Runners/agents disponibles",
        "detail": f"Ningún runner online atiende los tags {sorted(requested_tags)}.",
        "fix_hint": f"Agregá un runner con los tags {sorted(requested_tags)} o ajustá runner_tags del job.",
    }
