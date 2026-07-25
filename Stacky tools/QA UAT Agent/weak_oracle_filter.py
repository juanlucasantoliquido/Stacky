"""weak_oracle_filter.py — Filtro de oraculos NO verificables (Plan 240 F6b).

POR QUE EXISTE
--------------
El compilador de escenarios deriva oraculos del texto del ticket. Cuando el ticket
trae prosa rica (los de RSPACIFICO traen 12k chars de analisis), produce oraculos de
TEXTO LITERAL a partir de frases genericas. Caso real verificado (ticket 367, criterio
CA-03 "Una busqueda por Poliza/Obligacion con el valor completo retorna el cliente
esperado"):

    {"tipo": "page_contains_text", "target": "None", "valor": "Cliente esperado"}

=> el spec generado ejecuta expect(body).toContainText('Cliente esperado') y FALLA
SIEMPRE, porque esa cadena no existe ni debe existir en la pagina. Es un FALSO
NEGATIVO puro: el desarrollo esta bien y el agente reporta un defecto inexistente.

QUE HACE
--------
Marca como no verificables los oraculos de texto cuyo valor NO es un literal concreto
del ticket (entrecomillado, alfanumerico con formato, o numero), los quita del
escenario y deja constancia en `weak_oracles` para que el veredicto funcional los
cuente como `not_verifiable` (=> MIXED/PARTIAL_COVERAGE) en vez de FAIL.

NUNCA descarta un oraculo fuerte (equals sobre un selector, conteos, valores).
"""
from __future__ import annotations

import re

_TEXT_ORACLE_TYPES = frozenset({"page_contains_text", "contains_text", "text_contains"})

# Un valor de texto es CONCRETO (verificable) si:
#  - viene entrecomillado en el ticket (lo detecta el compilador y lo conserva), o
#  - tiene forma de identificador/codigo (mayusculas+digitos+guiones), o
#  - es un numero, o
#  - es una etiqueta corta de UI (<= 3 palabras) sin verbos de prosa.
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._\-/]{3,}$")
_NUM_RE = re.compile(r"^\d+([.,]\d+)?$")
_PROSE_VERBS_RE = re.compile(
    r"\b(debe|deberia|retorna|muestra|permite|persiste|incluye|refleja|admite|"
    r"observar|verificar|esperado|esperada|correcta|correctamente|sin\s+regresion)\b",
    re.I,
)


def is_concrete_text(value: str) -> bool:
    """True si el valor de un oraculo de texto es verificable literalmente."""
    v = (value or "").strip()
    if not v or len(v) < 2:
        return False
    if _NUM_RE.match(v):
        return True
    if _CODE_RE.match(v):
        return True
    if _PROSE_VERBS_RE.search(v):
        return False
    # Etiqueta corta de UI: hasta 3 palabras y sin puntuacion de frase.
    words = v.split()
    if len(words) <= 3 and not re.search(r"[.;:]", v):
        return True
    return False


def filter_scenario_oracles(scenario: dict) -> dict:
    """Devuelve {"kept": [...], "weak": [...]} para un escenario. NUNCA lanza."""
    kept, weak = [], []
    try:
        for oracle in scenario.get("oraculos") or []:
            if not isinstance(oracle, dict):
                continue
            tipo = str(oracle.get("tipo") or "").strip().lower()
            if tipo in _TEXT_ORACLE_TYPES and not is_concrete_text(str(oracle.get("valor") or "")):
                weak.append(oracle)
            else:
                kept.append(oracle)
    except Exception:  # noqa: BLE001
        return {"kept": scenario.get("oraculos") or [], "weak": []}
    return {"kept": kept, "weak": weak}


def apply_filter(compiler_result: dict) -> dict:
    """Muta compiler_result quitando oraculos debiles. Devuelve un resumen.

    Resumen: {"scenarios_touched": int, "weak_total": int,
              "by_scenario": {sid: [valores debiles]}}
    NUNCA lanza: ante cualquier error deja el input intacto.
    """
    summary = {"scenarios_touched": 0, "weak_total": 0, "by_scenario": {}}
    try:
        for scenario in (compiler_result or {}).get("scenarios") or []:
            if not isinstance(scenario, dict):
                continue
            res = filter_scenario_oracles(scenario)
            if not res["weak"]:
                continue
            sid = scenario.get("scenario_id") or "UNK"
            scenario["oraculos"] = res["kept"]
            scenario["weak_oracles"] = res["weak"]
            # Sin ningun oraculo fuerte, el escenario prueba navegacion + llegada,
            # pero NO puede declarar cumplido el criterio funcional.
            scenario["functional_status"] = ("not_verifiable" if not res["kept"]
                                             else scenario.get("functional_status"))
            summary["scenarios_touched"] += 1
            summary["weak_total"] += len(res["weak"])
            summary["by_scenario"][sid] = [str(o.get("valor"))[:80] for o in res["weak"]]
    except Exception:  # noqa: BLE001
        return summary
    return summary
