"""Plan 212 F6 — Preguntarle al CLI instalado qué modelos tiene, sin gastar tokens.

El catálogo de Claude Code era una foto fechada: si el CLI se actualiza y trae un
modelo nuevo, el operador no lo ve hasta que alguien edite el JSON a mano.

Esto lo consulta al CLI real. Tres reglas duras:

1. **Nunca invoca un modelo.** Solo subcomandos de LISTADO, que son de lectura.
   Costo de tokens: cero.
2. **Nunca resta.** Lo descubierto se suma a lo que ya está en el archivo; el
   probe puede ser incompleto y restar rompería una selección vigente.
3. **Nunca propaga una excepción.** Sin CLI, con timeout o con un JSON raro, el
   catálogo queda exactamente como estaba y se dice por qué.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger("stacky.services.model_probe")

__all__ = ["ProbeResult", "probe_claude_models", "extract_model_ids"]

# Candidatos de LISTADO en orden de preferencia. Si el subcomando no existe, el
# CLI sale con returncode != 0 y se prueba el siguiente.
_CANDIDATES: tuple = (
    ("models", "list", "--json"),
    ("models", "--json"),
    ("--list-models",),
)
_TIMEOUT_SEC = 5
# Presupuesto TOTAL, no por candidato: con 3 candidatos colgados el peor caso
# serían 15s bloqueando el catálogo. El plan pedía "<=5s"; esto lo hace cierto.
_TOTAL_BUDGET_SEC = 5


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    models: tuple
    command: str
    reason: str   # ok | cli_not_found | no_candidate_worked | timeout | parse_error


def extract_model_ids(data) -> list:
    """Saca ids de las formas plausibles del JSON. Tolerante a propósito.

    El formato del listado no está documentado y puede cambiar entre versiones
    del CLI; asumir una sola forma sería garantizar que se rompa.
    """
    def _de_lista(lista) -> list:
        ids: list = []
        for item in lista:
            if isinstance(item, str) and item.strip():
                ids.append(item.strip())
            elif isinstance(item, dict):
                valor = item.get("id") or item.get("name")
                if isinstance(valor, str) and valor.strip():
                    ids.append(valor.strip())
        return ids

    if isinstance(data, list):
        return _de_lista(data)
    if isinstance(data, dict):
        for clave in ("models", "data", "items"):
            valor = data.get(clave)
            if isinstance(valor, list):
                ids = _de_lista(valor)
                if ids:
                    return ids
    return []


def probe_claude_models(*, cli_bin: str, timeout_sec: int = _TIMEOUT_SEC) -> ProbeResult:
    """Descubre modelos preguntándole al CLI. NUNCA invoca un modelo."""
    if not cli_bin:
        return ProbeResult(False, (), "", "cli_not_found")

    hubo_timeout = False
    hubo_json_ilegible = False
    restante = float(min(timeout_sec, _TOTAL_BUDGET_SEC))

    for candidato in _CANDIDATES:
        if restante <= 0:
            hubo_timeout = True
            break
        comando = [cli_bin, *candidato]
        arranque = time.monotonic()
        try:
            proceso = subprocess.run(   # noqa: S603 — sin shell, args como lista
                comando,
                capture_output=True,
                text=True,
                timeout=restante,
                shell=False,
            )
        except FileNotFoundError:
            return ProbeResult(False, (), "", "cli_not_found")
        except subprocess.TimeoutExpired:
            hubo_timeout = True
            restante = 0.0
            continue
        except Exception:  # noqa: BLE001 — consultar el catálogo nunca puede romper
            logger.debug("model_probe: fallo inesperado con %r", candidato, exc_info=True)
            restante -= time.monotonic() - arranque
            continue
        restante -= time.monotonic() - arranque

        if proceso.returncode != 0:
            continue

        try:
            data = json.loads(proceso.stdout or "")
        except (ValueError, TypeError):
            hubo_json_ilegible = True
            continue

        ids = extract_model_ids(data)
        if not ids:
            hubo_json_ilegible = True
            continue

        # Dedup conservando el orden en que el CLI los declaró.
        vistos: set = set()
        unicos: list = []
        for i in ids:
            if i not in vistos:
                vistos.add(i)
                unicos.append(i)
        return ProbeResult(True, tuple(unicos), " ".join(candidato), "ok")

    if hubo_json_ilegible:
        return ProbeResult(False, (), "", "parse_error")
    if hubo_timeout:
        return ProbeResult(False, (), "", "timeout")
    return ProbeResult(False, (), "", "no_candidate_worked")
