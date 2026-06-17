"""A0.1 — Derivador de contrato de aceptación ejecutable + juez determinista.

API pública:
    derive(ticket, workspace, complexity, runtime) -> AcceptanceContract

Diseño:
- 1 llamada LLM (bajo clamp_model → nunca opus/fable) por derivación.
- Cap por complejidad: S→0-1, M→1-2, L/XL→2-4 chequeos solicitados al LLM.
- Juez determinista contra baseline (antes del run del agente):
    - red (falla) → conservar (exige conducta nueva)
    - green (pasa) → descartar (vacuo)
    - sin assert/predicado real (AST) → descartar
    - could-not-baseline (timeout/toolchain ausente) → descartar para gate, anotar
- Si checks_kept vacío → n_a=True (sin gate; cae a planes 29+31)
- annotate: deriva+valida pero is_active_gate=False (no inyecta ni gatea)
- Metadata: claves NUEVAS bajo "acceptance_contract"
- Flag OFF → n_a inmediato, sin LLM, sin subprocess

Restricciones:
- Sin deps externas nuevas (solo stdlib + subprocess + llm_router existente)
- Cap duro de modelo: clamp_model() en toda llamada LLM
- Contención: cwd=workspace, timeout duro por chequeo
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("stacky.acceptance_contract")

# Tipos de chequeo soportados
_KINDS = {"generated_test", "schema", "command", "file_predicate"}

# Timeout por chequeo de baseline (segundos)
_BASELINE_TIMEOUT_S = 30


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class AcceptanceContract:
    """Resultado de la derivación del contrato de aceptación."""
    n_a: bool                               # True = sin gate (checks_kept vacío o flag OFF)
    checks_kept: list[dict]                 # chequeos que sobrevivieron el juez
    vacuous_discarded: int = 0              # pasaron en baseline → descartados
    no_assert_discarded: int = 0            # sin assert/predicado → descartados
    could_not_baseline: int = 0             # timeout/toolchain → descartados para gate
    is_active_gate: bool = False            # True solo si mode=gate y n_a=False
    workspace: str = ""
    complexity: str = "M"

    def to_metadata(self) -> dict:
        return {
            "acceptance_contract": {
                "n_a": self.n_a,
                "checks_kept": self.checks_kept,
                "vacuous_discarded": self.vacuous_discarded,
                "no_assert_discarded": self.no_assert_discarded,
                "could_not_baseline": self.could_not_baseline,
                "complexity": self.complexity,
            }
        }

    def to_enrichment_block(self) -> dict | None:
        """Bloque de contexto de alta prioridad para enrich_blocks (A1.1)."""
        if self.n_a or not self.checks_kept:
            return None
        lines = ["Tu entregable DEBE pasar estos chequeos ejecutables:"]
        for i, ch in enumerate(self.checks_kept, 1):
            lines.append(f"{i}. [{ch['kind']}] {ch['ticket_clause']}")
            if ch.get("artifact") and ch["kind"] != "generated_test":
                artifact_preview = str(ch["artifact"])[:200]
                lines.append(f"   Artefacto: {artifact_preview}")
        lines.append("Trabajá hasta que todos pasen.")
        return {
            "type": "acceptance-contract",
            "priority": "high",
            "content": "\n".join(lines),
        }


# ── Ayudantes internos ────────────────────────────────────────────────────────

def _cap_for_complexity(complexity: str) -> int:
    """Devuelve el máximo de chequeos que se solicitan al LLM según complejidad."""
    return {"S": 1, "M": 2, "L": 4, "XL": 4}.get(complexity.upper(), 2)


def _has_real_assert(artifact: str, kind: str) -> bool:
    """Verifica que el artefacto de tipo generated_test contiene al menos 1 assert real.

    Para Python: parse AST y busca nodos Assert.
    Para JS/TS: léxico acotado buscando 'expect(', 'assert.', 'should.'.
    """
    if kind != "generated_test":
        return True  # otros tipos no necesitan assert
    text = artifact or ""
    if not text.strip():
        return False

    # Intento Python AST
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                return True
        # También acepta llamadas a self.assert*/unittest.assert*
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name.lower().startswith("assert"):
                    return True
        return False
    except SyntaxError:
        pass

    # Fallback léxico (JS/TS o Python con sintaxis rota)
    patterns = [
        r"\bassert\b",
        r"expect\s*\(",
        r"\.should\b",
        r"\.to\.(equal|be|include|throw|exist|have)",
    ]
    for pat in patterns:
        if re.search(pat, text):
            return True
    return False


def _run_check_baseline(check: dict, workspace: str) -> tuple[str, str]:
    """Ejecuta un chequeo contra el workspace SIN modificaciones del agente.

    Returns:
        ("red", detail)    — falla → conservar
        ("green", detail)  — pasa → descartar (vacuo)
        ("could-not-baseline", detail) — no ejecutable
    """
    kind = check.get("kind", "command")
    artifact = check.get("artifact", "")

    if not artifact:
        return ("could-not-baseline", "artifact vacío")

    try:
        if kind == "file_predicate":
            # Verificar que el archivo NO existe aún (o existe pero NO cumple la predicción)
            path = Path(workspace) / artifact
            if path.exists():
                return ("green", f"ya existe: {artifact}")
            return ("red", f"no existe aún: {artifact}")

        if kind == "schema":
            # Parsear el JSON/YAML como schema check
            schema_path = Path(workspace) / artifact
            if not schema_path.exists():
                return ("could-not-baseline", f"schema file not found: {artifact}")
            try:
                import json as _json
                _json.loads(schema_path.read_text(encoding="utf-8", errors="replace"))
                return ("green", "schema válido en baseline")
            except Exception:
                return ("red", "schema inválido en baseline")

        if kind in ("command", "generated_test"):
            # Para generated_test materializar en temp file
            cmd_to_run = artifact
            tmp_file = None
            try:
                if kind == "generated_test":
                    suffix = ".py" if not artifact.strip().startswith("//") else ".ts"
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=suffix, dir=workspace,
                        prefix="_ac_baseline_", delete=False, encoding="utf-8"
                    ) as f:
                        f.write(artifact)
                        tmp_file = f.name
                    if suffix == ".py":
                        cmd_to_run = f"python -m pytest {tmp_file} -x -q"
                    else:
                        cmd_to_run = f"npx jest {tmp_file} --no-coverage"

                result = subprocess.run(
                    cmd_to_run,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=_BASELINE_TIMEOUT_S,
                    cwd=workspace,
                )
                detail = (result.stdout + result.stderr)[:500]
                if result.returncode == 0:
                    return ("green", detail)
                return ("red", detail)
            finally:
                if tmp_file:
                    try:
                        Path(tmp_file).unlink(missing_ok=True)
                    except Exception:
                        pass

    except subprocess.TimeoutExpired:
        return ("could-not-baseline", "timeout")
    except Exception as exc:  # noqa: BLE001
        return ("could-not-baseline", str(exc)[:200])

    return ("could-not-baseline", "kind desconocido")


def _call_llm(prompt: str, model: str) -> str:
    """Llama al LLM con el modelo dado (ya clampeado) y devuelve la respuesta raw."""
    try:
        import copilot_bridge
        response = copilot_bridge.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=1024,
        )
        return response.get("content", "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("_call_llm failed: %s", exc)
        return ""


def _build_derive_prompt(ticket_text: str, max_checks: int, criteria_text: str) -> str:
    return f"""Eres un ingeniero de QA. Dado el siguiente ticket y sus criterios de aceptación,
genera exactamente {max_checks} chequeo(s) ejecutable(s) que:
1. Sean deterministas (no dependan del azar ni del tiempo)
2. Fallen HOY (antes de cualquier cambio) — si ya pasan hoy, no los incluyas
3. Tengan un artefacto concreto y corrible: comando shell, test Python/JS, predicado de archivo, o schema JSON

Ticket: {ticket_text[:1500]}

Criterios de aceptación: {criteria_text[:1000] if criteria_text else "(no disponibles — usá el título/descripción)"}

Devuelve SOLO JSON con la siguiente estructura (sin markdown, sin explicación):
{{
  "checks": [
    {{
      "kind": "command|generated_test|schema|file_predicate",
      "artifact": "<comando o código o ruta>",
      "ticket_clause": "<frase corta del criterio que verifica>"
    }}
  ]
}}

Máximo {max_checks} chequeos. Si no podés generar ninguno con confianza, devuelve {{"checks": []}}.
"""


def _extract_checks_from_response(response: str) -> list[dict]:
    """Extrae la lista de chequeos del JSON de respuesta LLM."""
    text = (response or "").strip()
    # Quitar bloque markdown si está
    block = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if block:
        text = block.group(1)
    try:
        parsed = json.loads(text)
        checks = parsed.get("checks") or []
        return [c for c in checks if isinstance(c, dict)]
    except (json.JSONDecodeError, ValueError):
        pass
    # Intento con regex
    obj = re.search(r"\{[\s\S]+\}", text)
    if obj:
        try:
            parsed = json.loads(obj.group(0))
            return parsed.get("checks") or []
        except Exception:
            pass
    return []


def _get_ticket_text(ticket: Any) -> str:
    parts = []
    if getattr(ticket, "title", None):
        parts.append(f"Título: {ticket.title}")
    if getattr(ticket, "description", None):
        parts.append(f"Descripción: {ticket.description}")
    return "\n".join(parts)


def _get_criteria_text(ticket: Any) -> str:
    """Intenta obtener los criterios de aceptación del ticket."""
    # Reutiliza _resolve_criteria si está disponible (plan 29)
    try:
        from services.self_review import _resolve_criteria
        return _resolve_criteria(ticket) or ""
    except Exception:
        pass
    return getattr(ticket, "acceptance_criteria", "") or ""


# ── API pública ───────────────────────────────────────────────────────────────

def derive(
    *,
    ticket: Any,
    workspace: str,
    complexity: str,
    runtime: str,
) -> AcceptanceContract:
    """Deriva el contrato de aceptación ejecutable para el ticket dado.

    1. Verifica flag STACKY_ACCEPTANCE_CONTRACT_ENABLED (OFF → n_a inmediato).
    2. Llama LLM (1 vez, bajo clamp_model) para derivar chequeos.
    3. Juez determinista: ejecuta cada chequeo contra el workspace SIN cambios.
    4. Conserva solo los que fallan (red). Descarta vacuos, sin-assert, could-not-baseline.
    5. Si ninguno sobrevive → n_a=True.
    """
    try:
        from config import config as _cfg
        enabled = getattr(_cfg, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", False)
    except Exception:
        enabled = False

    if not enabled:
        return AcceptanceContract(n_a=True, checks_kept=[], workspace=workspace, complexity=complexity)

    try:
        from config import config as _cfg
        mode = getattr(_cfg, "STACKY_ACCEPTANCE_CONTRACT_MODE", "off")
        global_max = getattr(_cfg, "STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS", 4)
    except Exception:
        mode = "off"
        global_max = 4

    # Cap por complejidad, respetando el global
    cap = min(_cap_for_complexity(complexity), global_max)

    is_active_gate = (mode == "gate")

    # Preparar prompt
    ticket_text = _get_ticket_text(ticket)
    criteria_text = _get_criteria_text(ticket)
    prompt = _build_derive_prompt(ticket_text, cap, criteria_text)

    # Llamada LLM bajo cap duro de modelo
    try:
        from services.llm_router import clamp_model
        model = clamp_model("claude-sonnet-4-6")
    except Exception:
        model = "claude-sonnet-4-6"

    llm_response = _call_llm(prompt, model)
    raw_checks = _extract_checks_from_response(llm_response)

    # Aplicar cap (solo pedimos cap al LLM pero podría devolver más)
    raw_checks = raw_checks[:cap]

    # Juez determinista
    checks_kept: list[dict] = []
    vacuous_discarded = 0
    no_assert_discarded = 0
    could_not_baseline = 0

    for check in raw_checks:
        kind = check.get("kind", "command")
        artifact = check.get("artifact", "")

        # Filtro 1: sin assert → descartar
        if not _has_real_assert(artifact, kind):
            no_assert_discarded += 1
            logger.debug("acceptance_contract: descartado (sin assert): %s", artifact[:80])
            continue

        # Juez de baseline
        baseline_status, baseline_detail = _run_check_baseline(check, workspace)

        if baseline_status == "green":
            vacuous_discarded += 1
            logger.debug("acceptance_contract: descartado (vacuo, ya pasa): %s", artifact[:80])
        elif baseline_status == "could-not-baseline":
            could_not_baseline += 1
            logger.debug("acceptance_contract: could-not-baseline: %s / %s", artifact[:80], baseline_detail[:80])
        else:  # red
            checks_kept.append({
                **check,
                "baseline_status": "red",
                "baseline_detail": baseline_detail[:300],
            })

    n_a = len(checks_kept) == 0

    if n_a:
        logger.debug(
            "acceptance_contract: n/a (kept=%d, vacuous=%d, no_assert=%d, cnb=%d)",
            len(checks_kept), vacuous_discarded, no_assert_discarded, could_not_baseline,
        )

    return AcceptanceContract(
        n_a=n_a,
        checks_kept=checks_kept,
        vacuous_discarded=vacuous_discarded,
        no_assert_discarded=no_assert_discarded,
        could_not_baseline=could_not_baseline,
        is_active_gate=is_active_gate and not n_a,
        workspace=workspace,
        complexity=complexity,
    )
