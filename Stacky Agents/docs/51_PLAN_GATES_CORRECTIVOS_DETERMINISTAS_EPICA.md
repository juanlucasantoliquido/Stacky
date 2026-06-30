# Plan 51 — Gates Correctivos Deterministas de Épica (Contrato-Verde-o-Reintenta + Golden Catalog Diff)

> Estado: IMPLEMENTADO 2026-06-19.
>
> Evidencia: F0/F1/F2/F3 en `backend/harness/epic_gate.py` (GateDecision, GateVerdict, classify_structural_severity, golden_catalog_diff, evaluate_epic_gate). F2 refactor de extracción: `api/tickets.py` `catalog_unknown_processes` (núcleo puro extraído de `_catalog_grounding_warnings`, string idéntico). F2 golden-set: `evals/catalog_diff_fixtures/` (6 fixtures) + `evals/catalog_diff_runner.py`. F3 wiring: helpers `_epic_gate_enabled`/`_epic_catalog_gate_enabled` + gate en `autopublish_epic_from_run` (bloqueo ruidoso `epic_gate_blocked`) + enriquecimiento del pase correctivo en `claude_code_cli_runner.py` (dispara REPAIR por defectos de forma cuando el gate está ON). F4: `build_epic_summary(..., gate_decision=...)` sellado en el call-site. F5: 4 casos en `tests/conformance/test_runtime_conformance.py` (determinismo, locale, sorted, import). Flags `STACKY_EPIC_GATE_ENABLED`/`STACKY_EPIC_CATALOG_GATE_ENABLED` (default OFF) en `services/harness_flags.py` + `.env.example`. Tests verdes (por archivo, .venv): test_epic_gate.py 18, test_golden_catalog_diff.py 10, test_epic_autopublish_backend.py 26 (incl. F3/F4), conformance 25, test_harness_flags.py 23. No-regresión plan 50 (catálogo refactor): 64 verdes. C1 confirmado: wiring autopublish Claude-CLI-only; funciones puras compartidas por los 3 runtimes.
>
> Estado original: PROPUESTO 2026-06-19. Formaliza un debate cerrado entre Brainstormer y UltraEficientCode. NO re-deliberar.
> Construye SOBRE los planes 44-50 (no los duplica). Reusa: `_extract_epic_html`, `_sanitize_epic_html`, `_looks_like_epic`, `_structural_epic_warnings`, `_catalog_grounding_warnings`, `autopublish_epic_from_run`, el patrón `epic_repair` del runner, los golden-sets del plan 49 y el conformance del plan 49 F3.

## 1. Objetivo, KPI e impacto

**Objetivo (1 párrafo).** Dar el salto de OBSERVAR/limpiar (planes 44-50) a ACTUAR determinísticamente sobre la salida del agente: convertir los warnings que hoy solo se *registran* (planes 42/50) en **gates correctivos automáticos** antes de publicar una épica/issue en ADO. Dos gates, ambos como funciones PURAS testeables con golden-set escrito a mano: (1) **Contrato-Verde-o-Reintenta** — validación estructural endurecida que, ante un defecto concreto, dispara UN único pase correctivo condicional (reusando el patrón `epic_repair`) o degrada a `needs_review` ruidoso; (2) **Golden Catalog Diff** — detección determinista de procesos/entidades INVENTADOS comparando la épica contra el `process_catalog`/`technical_master` del `client_profile`, marcando lo no presente (warning + bloqueo opcional de autopublish) sin alucinar reemplazos.

**KPI / impacto esperado:**
- **K1 — Épicas-basura publicadas → 0.** Toda épica que llega a ADO pasó el contrato estructural duro (heading + ≥1 RF + sin defectos estructurales bloqueantes). Hoy `_looks_like_epic` solo exige heading + 1 RF; los defectos estructurales del plan 50 (RF duplicados, huecos, bloques vacíos) se *registran* pero **no bloquean**.
- **K2 — Procesos inventados publicados sin marca → 0.** Cuando hay catálogo, todo proceso/módulo citado que no esté en él queda marcado y (opt-in) bloquea autopublish.
- **K3 — Costo de tokens en el caso feliz ≈ 0.** El reintento correctivo es CONDICIONAL al defecto detectado por función pura; si la épica está verde, cero tokens extra.
- **K4 — `gate_decision` telemetría.** % de runs que pasan limpio vs. reparadas vs. degradadas a `needs_review`, observable en `epic_summary` sin trabajo del operador.

## 2. Por qué ahora / gap que cierra

Los planes 44-50 construyeron un sustrato de OBSERVACIÓN robusto y determinista:
- Plan 42/50 producen warnings estructurales (`_structural_epic_warnings`, `tickets.py:5552`) y de catálogo (`_catalog_grounding_warnings`, `tickets.py:5581`), pero **solo los registran**: `autopublish_epic_from_run` (`tickets.py:5890`) loguea `grounding_warnings` y **publica igual** ("publicando igual").
- Plan 50 endureció el saneamiento de FORMA (`_sanitize_epic_html`, `tickets.py:5471`) pero explícitamente "NUNCA la semántica".
- El único gate que SÍ bloquea hoy es `_looks_like_epic` (`tickets.py:5507`): heading + ≥1 RF. Es un piso mínimo; deja pasar épicas con RF duplicados, secuencia rota, bloques vacíos o procesos fabricados.

**Gap concreto:** entre "detectamos el defecto" (plan 50) y "lo dejamos pasar a ADO" (autopublish actual) no hay ACCIÓN. El plan 51 cierra ese gap reusando exactamente las funciones puras ya escritas, agregando (a) un clasificador puro de severidad que decide pasar/reparar/degradar, y (b) un linter de catálogo que puede bloquear. Cero generación nueva de detección difusa.

## 3. Principios y guardarraíles (criterios de aceptación duros del documento)

1. **Núcleo = función pura testeable** con golden-set escrito A MANO. Prohibido golden capturado de la ejecución actual (tautológico). Patrón a copiar: `evals/extraction_golden_runner.py` + `evals/extraction_fixtures/*.json` (plan 49).
2. **Idempotencia verificable** `f(f(x)) == f(x)` para toda función que transforme, con test explícito.
3. **Degrada a NO-OP ante falta de evidencia:** sin catálogo → `[]` (ya lo hace `_catalog_grounding_warnings`, `tickets.py:5588`); output no parseable → input intacto + warning, nunca rompe ni inventa.
4. **Cero campos obligatorios nuevos en UI ni pasos al operador.** Backward-compatible.
5. **Costo de tokens ≈ 0 en generación:** el reintento correctivo es condicional al defecto detectado y va detrás de flag.
6. **Orden de iteración estable** (`sorted`), sin dependencia de reloj/locale/encoding. Reusar el centinela de no-determinismo del plan 49 F5 (`tests/conformance/test_runtime_conformance.py`).
7. **3 runtimes con fallback explícito.** La(s) función(es) pura(s) corren idénticas en los 3. PERO el WIRING de autopublish es **Claude-CLI-only** (`claude_code_cli_runner.py:1163` invoca `_maybe_autopublish_epic`; verificado: Codex/Copilot NO lo invocan). Para Codex/Copilot el gate degrada a warning/`needs_review` (sin reparación inline, porque no tienen el canal `_send_system_message` del pase correctivo). Esto se declara, no se oculta.
8. **Human-in-the-loop:** sin autonomía proactiva nueva. La única auto-publicación es la vigente (épica-desde-brief, decisión del operador 2026-06-17). Los gates solo *suben* el listón de calidad o degradan a `needs_review` (más revisión humana, nunca menos).
9. **Mono-operador sin auth real:** nada de RBAC.
10. **No re-implementar** arnés 49-50, grounding 42/44, observatorio 44, salud operativa 46, saneamiento 50.

## 4. Fases

Dependencias: F0 → F1 → F2 → F3 → F4 → F5. F1 y F2 son funciones puras independientes entre sí (pueden implementarse en paralelo tras F0). F3 cablea. F4 telemetría. F5 conformance + centinela.

---

### F0 — Módulo compartido `harness/epic_gate.py` (esqueleto + tipos puros)

**Objetivo (1 frase).** Crear el módulo compartido que aloja las funciones puras del gate, ubicado en `harness/` para que las 3 runtimes lo importen idénticamente.

**Valor.** Punto único de verdad del gate, separado de `api/tickets.py` (que ya es enorme) y del runner (Claude-CLI-only). Permite conformance estilo plan 49 F3.

**Archivos a crear:**
- `Stacky Agents/backend/harness/epic_gate.py`

**Contenido exacto (esqueleto + tipos; las funciones se llenan en F1/F2):**

```python
"""Plan 51 — Gates correctivos deterministas de épica.

Funciones PURAS sobre el HTML ya extraído de la épica. Sin LLM, sin red, sin
reloj, sin locale, sin datos personales. Determinismo total. Reusa los
detectores del plan 50 (importados desde api.tickets) y agrega la CLASIFICACIÓN
de severidad que decide pasar/reparar/degradar, y el diff contra el catálogo.

Las 3 runtimes importan este módulo idéntico. El WIRING del pase correctivo
inline es Claude-CLI-only (ver claude_code_cli_runner.py); Codex/Copilot
degradan a needs_review (ver Plan 51 §3 guardarraíl 7).
"""
from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class GateDecision(str, Enum):
    PASS = "pass"            # épica verde: publicar sin tocar
    REPAIR = "repair"        # defecto reparable: pedir UN pase correctivo
    NEEDS_REVIEW = "needs_review"  # defecto no reparable inline o catálogo inventado


class GateVerdict(NamedTuple):
    decision: GateDecision
    structural_defects: list  # códigos string deterministas, sorted
    catalog_unknown: list     # nombres de procesos inventados, sorted
    blocking: bool            # True si NO debe autopublicar tal cual
    # nota: el llamante decide repair vs needs_review según runtime
```

**Tests PRIMERO (TDD):**
- Ruta: `Stacky Agents/backend/tests/test_epic_gate.py` (creado en F1; en F0 basta que el import no falle).
- Caso F0: `from harness.epic_gate import GateDecision, GateVerdict, evaluate_epic_gate` no lanza ImportError (los símbolos existen aunque `evaluate_epic_gate` se complete en F1/F2).

**Comando de verificación (venv del repo, por archivo):**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_epic_gate.py" -q
```

**Criterio de aceptación BINARIO.** El import del módulo y de los 3 símbolos no lanza. (En F0 el test puede ser un `test_imports_ok`.)

**Flag que lo protege.** Ninguno en F0 (módulo inerte hasta el wiring de F3).

**Impacto por runtime.** Idéntico en los 3 (solo define tipos). Fallback: N/A.

**Trabajo del operador:** ninguno.

---

### F1 — `classify_structural_severity` (clasificador puro de severidad)

**Objetivo (1 frase).** Función pura que recibe los warnings estructurales del plan 50 y los clasifica en REPAIR (reparable inline) vs NEEDS_REVIEW (no reparable), sin re-detectar nada.

**Valor.** Convierte la lista plana de warnings (hoy informativa) en una DECISIÓN. Es el cerebro determinista del gate Contrato-Verde-o-Reintenta.

**Archivos a editar:**
- `Stacky Agents/backend/harness/epic_gate.py`

**Diseño exacto.** Reusa los detectores existentes; NO los reimplementa. Los códigos de defecto provienen de `_structural_epic_warnings` (`tickets.py:5552`), que produce strings con prefijos fijos:
- `epic_structure: números RF duplicados: ...`
- `epic_structure: secuencia RF no consecutiva, faltan: ...`
- `epic_structure: hay headings vacíos`
- `epic_structure: hay bloques RF sin contenido`

**Política de severidad acordada (determinista, sin umbrales difusos):**

| Defecto | Código canónico | Severidad |
|---|---|---|
| Falta heading o falta bloque RF (`not _looks_like_epic`) | `not_epic` | REPAIR |
| RF duplicados | `rf_duplicated` | REPAIR |
| Secuencia RF no consecutiva (huecos) | `rf_non_consecutive` | NEEDS_REVIEW |
| Headings vacíos | `empty_heading` | REPAIR |
| Bloques RF sin contenido | `rf_empty_body` | NEEDS_REVIEW |

Justificación de la partición (escrita para que el implementador no infiera): REPAIR = defectos de FORMA que un re-emit del agente arregla barato (duplicados, headings vacíos, falta de estructura). NEEDS_REVIEW = defectos que sugieren CONTENIDO faltante o numeración pensada mal (huecos en la secuencia, cuerpo de RF ausente) — re-emitir no garantiza arreglarlo, mejor que lo vea un humano.

```python
import re

# Mapea el TEXTO del warning del plan 50 → código canónico estable.
_DEFECT_PATTERNS = (
    (re.compile(r"números RF duplicados", re.I), "rf_duplicated"),
    (re.compile(r"secuencia RF no consecutiva", re.I), "rf_non_consecutive"),
    (re.compile(r"headings vacíos", re.I), "empty_heading"),
    (re.compile(r"bloques RF sin contenido", re.I), "rf_empty_body"),
)
_REPAIRABLE = frozenset({"not_epic", "rf_duplicated", "empty_heading"})


def classify_structural_severity(structural_warnings: list) -> dict:
    """PURA. Mapea warnings de plan 50 → {code: severity}. Orden estable (sorted).
    Nunca lanza; ante warning desconocido lo ignora (no opina)."""
    codes: set[str] = set()
    for w in structural_warnings or []:
        for pat, code in _DEFECT_PATTERNS:
            if pat.search(str(w)):
                codes.add(code)
                break
    return {
        c: ("repair" if c in _REPAIRABLE else "needs_review")
        for c in sorted(codes)
    }
```

**Casos borde:** lista vacía → `{}`. Warning no reconocido (p.ej. un `epic_grounding_low`) → ignorado. `None` → `{}`.

**Tests PRIMERO (TDD).**
- Ruta: `Stacky Agents/backend/tests/test_epic_gate.py`
- Casos:
  1. `[]` → `{}`.
  2. `None` → `{}`.
  3. warning de duplicados → `{"rf_duplicated": "repair"}`.
  4. warning de huecos → `{"rf_non_consecutive": "needs_review"}`.
  5. mezcla duplicados + huecos → `{"rf_duplicated": "repair", "rf_non_consecutive": "needs_review"}` y las claves vienen `sorted`.
  6. warning ajeno (`"epic_grounding_low: ..."`) → `{}`.
  7. **Idempotencia/determinismo:** dos llamadas con la misma entrada en distinto orden de lista → mismo dict.

**Comando.**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_epic_gate.py" -q
```

**Criterio de aceptación BINARIO.** 7 casos verdes.

**Flag.** Ninguno (función pura inerte).

**Impacto por runtime.** Idéntico en los 3.

**Trabajo del operador:** ninguno.

---

### F2 — `golden_catalog_diff` (linter puro de procesos inventados) + golden-set a mano

**Objetivo (1 frase).** Función pura que devuelve los procesos/módulos citados en la épica que NO existen en el catálogo del cliente, con golden-set escrito a mano.

**Valor.** Marca determinísticamente alucinaciones de proceso. Hoy `_catalog_grounding_warnings` (`tickets.py:5581`) ya hace el matching pero (a) está enterrado en tickets.py y (b) está detrás de un flag OFF y solo loguea. F2 lo expone como función reutilizable en `harness/` con cobertura golden a mano y lo deja listo para BLOQUEAR en F3.

**Decisión de reuso (NO duplicar).** `golden_catalog_diff` **delega** en `_catalog_grounding_warnings` para no tener dos regex de extracción divergentes, pero devuelve la LISTA de nombres desconocidos (no el string de warning), porque F3 necesita la lista para decidir bloqueo:

```python
def golden_catalog_diff(html, process_catalog) -> list:
    """PURA. Devuelve sorted(list) de procesos/módulos citados en `html` que NO
    están en `process_catalog` (matching normalizado: lower+trim+colapso espacios).
    Sin catálogo o sin HTML → [] (NO-OP, no opina sin fuente de verdad).
    NUNCA inventa reemplazos. Reusa la extracción de api.tickets para no divergir."""
    from api.tickets import _catalog_grounding_warnings
    # _catalog_grounding_warnings ya devuelve [] si falta evidencia y produce
    # un único string "catalog_grounding: procesos ... no presentes ...: [<lista>]".
    warns = _catalog_grounding_warnings(html, process_catalog)
    if not warns:
        return []
    # Re-derivar la lista pura es frágil parseando el string; en su lugar,
    # exponer un helper sibling en tickets.py que devuelva la LISTA (ver nota).
    ...
```

**Nota de implementación obligatoria (resuelve la fragilidad del parseo):** en vez de parsear el string del warning, **refactorizar** `_catalog_grounding_warnings` (`tickets.py:5581`) para extraer su núcleo a una función pura nueva en **el mismo tickets.py**: `catalog_unknown_processes(html, process_catalog) -> list[str]` (devuelve la lista `unknown` ya `sorted`), y que `_catalog_grounding_warnings` la llame para construir su string. Así `golden_catalog_diff` importa `catalog_unknown_processes` directamente. Esto es un refactor de extracción sin cambio de comportamiento (el string del warning queda idéntico).

```python
# tickets.py — refactor de extracción, comportamiento idéntico:
def catalog_unknown_processes(html, process_catalog) -> list[str]:
    """PURA. Procesos/módulos citados no presentes en el catálogo. sorted. NO-OP sin evidencia."""
    if not html or not process_catalog:
        return []
    def _norm(s): return re.sub(r"\s+", " ", str(s)).strip().lower()
    catalog_names = {_norm(i.get("name")) for i in process_catalog if i.get("name")}
    if not catalog_names:
        return []
    cited = set(re.findall(r"(?:proceso|m[oó]dulo)\s+([A-Za-z0-9_./-]+)", html, re.IGNORECASE))
    return sorted({c for c in cited if _norm(c) not in catalog_names})

def _catalog_grounding_warnings(html, process_catalog) -> list[str]:
    unknown = catalog_unknown_processes(html, process_catalog)
    if unknown:
        return [f"catalog_grounding: procesos citados no presentes en el catálogo: {unknown}"]
    return []

# harness/epic_gate.py
def golden_catalog_diff(html, process_catalog) -> list:
    from api.tickets import catalog_unknown_processes
    return catalog_unknown_processes(html, process_catalog)
```

**Golden-set a mano (anti-tautológico).** Crear `Stacky Agents/backend/evals/catalog_diff_fixtures/*.json` siguiendo el patrón de `evals/extraction_fixtures/`. Cada fixture: `{name, html, catalog, expect_unknown}`. Casos ESCRITOS a mano (no capturados):
1. `epica_solo_procesos_validos.json` — cita solo procesos del catálogo → `[]`.
2. `epica_proceso_inventado.json` — cita "proceso FacturacionFantasma" no en catálogo → `["FacturacionFantasma"]`.
3. `epica_sin_catalogo.json` — catálogo `[]` → `[]` (NO-OP).
4. `epica_sin_html.json` — html `""` → `[]`.
5. `epica_mixto.json` — 1 válido + 2 inventados → los 2 inventados `sorted`.
6. `epica_modulo_inventado.json` — "módulo XYZ" no en catálogo → `["XYZ"]`.

**Runner golden:** crear `Stacky Agents/backend/evals/catalog_diff_runner.py` clon de `extraction_golden_runner.py` (load_cases sobre `catalog_diff_fixtures/`, compara `golden_catalog_diff(html, catalog)` vs `expect_unknown`).

**Tests PRIMERO (TDD).**
- Ruta: `Stacky Agents/backend/tests/test_golden_catalog_diff.py` (clon de `tests/test_golden_extraction.py`).
- Casos: cada fixture verde; **idempotencia** `golden_catalog_diff(html, c) == golden_catalog_diff(html, c)`; **NO-OP** sin catálogo y sin html; **orden estable** (resultado siempre `sorted`).
- Test adicional en `tests/test_epic_gate.py`: el refactor de `_catalog_grounding_warnings` produce el MISMO string que antes (test de no-regresión con un input fijo).

**Comando.**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_golden_catalog_diff.py" "Stacky Agents/backend/tests/test_epic_gate.py" -q
```

**Criterio de aceptación BINARIO.** 6 fixtures + idempotencia + no-regresión del string verdes.

**Flag.** El BLOQUEO va detrás de flag en F3; la función pura no tiene flag (inerte).

**Impacto por runtime.** Idéntico en los 3.

**Trabajo del operador:** ninguno.

---

### F3 — `evaluate_epic_gate` + wiring condicional en autopublish (el gate que ACTÚA)

**Objetivo (1 frase).** Ensamblar F1+F2 en un veredicto único y cablearlo en `autopublish_epic_from_run` para que, ante defecto reparable, marque REPAIR; ante defecto no reparable o proceso inventado (flag ON), bloquee a `needs_review`; en caso feliz, publique sin costo extra.

**Valor.** Es donde el plan deja de observar y empieza a actuar. Caso feliz = cero tokens.

**Archivos a editar:**
- `Stacky Agents/backend/harness/epic_gate.py` (agrega `evaluate_epic_gate`)
- `Stacky Agents/backend/api/tickets.py` (cablea en `autopublish_epic_from_run`, `~tickets.py:5870-5895`)
- `Stacky Agents/backend/services/claude_code_cli_runner.py` (consume `decision==REPAIR` para disparar el pase correctivo existente, `~890-930`)

**`evaluate_epic_gate` (pura):**

```python
def evaluate_epic_gate(
    *,
    clean_html,
    structural_warnings,        # de _epic_grounding_warnings / _structural_epic_warnings
    process_catalog,            # del client_profile (puede ser None/[])
    catalog_blocking_enabled,   # flag STACKY_EPIC_CATALOG_GATE_ENABLED resuelto por el caller
    looks_like_epic_fn,         # inyectado: api.tickets._looks_like_epic (evita import circular)
) -> GateVerdict:
    """PURA. Ensambla F1+F2 en un veredicto. Nunca lanza.

    Reglas (deterministas, en orden):
      1. not looks_like_epic(clean_html) -> defecto 'not_epic' (repair).
      2. severidades = classify_structural_severity(structural_warnings).
      3. catalog_unknown = golden_catalog_diff(clean_html, process_catalog).
      4. blocking = hay alguna severidad 'needs_review'
                    OR (catalog_blocking_enabled AND catalog_unknown no vacío).
      5. decision:
           - blocking -> NEEDS_REVIEW
           - elif hay defectos 'repair' -> REPAIR
           - else -> PASS
    """
    defects = dict(classify_structural_severity(structural_warnings))
    if not looks_like_epic_fn(clean_html):
        defects["not_epic"] = "repair"
    catalog_unknown = golden_catalog_diff(clean_html, process_catalog)
    has_block_sev = any(v == "needs_review" for v in defects.values())
    blocking = has_block_sev or (bool(catalog_blocking_enabled) and bool(catalog_unknown))
    if blocking:
        decision = GateDecision.NEEDS_REVIEW
    elif any(v == "repair" for v in defects.values()):
        decision = GateDecision.REPAIR
    else:
        decision = GateDecision.PASS
    return GateVerdict(
        decision=decision,
        structural_defects=sorted(defects.keys()),
        catalog_unknown=catalog_unknown,
        blocking=blocking,
    )
```

**Wiring en `autopublish_epic_from_run` (`tickets.py`, justo ANTES de `_publish_epic_to_ado`, ~línea 5896).** El gate va detrás de `STACKY_EPIC_GATE_ENABLED` (default OFF en el primer release; se sube a ON tras validar):

```python
# Plan 51 — Gate correctivo determinista.
if _epic_gate_enabled():  # STACKY_EPIC_GATE_ENABLED, default "false"
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    _struct = _epic_grounding_warnings(clean_html)  # incluye _structural_epic_warnings (plan 50)
    _verdict = evaluate_epic_gate(
        clean_html=clean_html,
        structural_warnings=_struct,
        process_catalog=catalog if _catalog_grounding_warnings_enabled() else None,
        catalog_blocking_enabled=_epic_catalog_gate_enabled(),  # STACKY_EPIC_CATALOG_GATE_ENABLED, default false
        looks_like_epic_fn=_looks_like_epic,
    )
    grounding_warnings = grounding_warnings + [
        f"epic_gate: decision={_verdict.decision.value} "
        f"defects={_verdict.structural_defects} catalog_unknown={_verdict.catalog_unknown}"
    ]
    if _verdict.blocking:
        return _AutopublishResult(
            ado_id=None,
            error=(
                "epic_gate_blocked: la épica tiene defectos no reparables inline "
                f"(defects={_verdict.structural_defects}, catalog_unknown={_verdict.catalog_unknown}). "
                "Revisar/reintentar la generación."
            ),
            skipped=False,
            grounding_warnings=grounding_warnings,
        )
```

`decision == REPAIR` **no** se actúa en autopublish (autopublish ocurre al FINAL de la run, cuando ya no hay turno para reparar). El REPAIR se consume en el RUNNER, que corre durante la run. Por eso:

**Wiring en `claude_code_cli_runner.py` (~890-930).** El pase correctivo existente (`epic_repair`) ya detecta `not _looks_like_epic`. Se ENRIQUECE para disparar también cuando el gate dice REPAIR por OTROS defectos reparables (duplicados, headings vacíos):

```python
from harness.epic_gate import evaluate_epic_gate, GateDecision
from api.tickets import _extract_epic_html, _looks_like_epic, _epic_grounding_warnings
_current_output = "\n".join(final_output) if final_output else ""
_clean = _extract_epic_html(_current_output)
_verdict = evaluate_epic_gate(
    clean_html=_clean,
    structural_warnings=_epic_grounding_warnings(_clean),
    process_catalog=None,           # el runner no carga client_profile; catálogo se chequea en autopublish
    catalog_blocking_enabled=False, # el runner solo repara FORMA
    looks_like_epic_fn=_looks_like_epic,
)
if _verdict.decision == GateDecision.REPAIR and _ac_used < _ac_budget:
    # mensaje correctivo: si hay 'not_epic' usar _EPIC_REPAIR_MSG actual;
    # si hay defectos estructurales (rf_duplicated/empty_heading) agregar la instrucción puntual.
    ...
```

El mensaje correctivo se construye determinísticamente desde `_verdict.structural_defects` (mapa fijo código→frase imperativa; sin texto libre del LLM como fuente de verdad).

**Casos borde:** gate flag OFF → comportamiento idéntico a hoy (solo `_looks_like_epic` bloquea). Catálogo ausente → `catalog_unknown=[]`, no bloquea. `decision==PASS` → cero tokens, publica.

**Tests PRIMERO (TDD).**
- Ruta: `Stacky Agents/backend/tests/test_epic_gate.py` (suma casos de `evaluate_epic_gate`).
- Casos:
  1. épica verde → `GateDecision.PASS`, `blocking=False`.
  2. épica con RF duplicados → `REPAIR`, `blocking=False`.
  3. épica con huecos en secuencia → `NEEDS_REVIEW`, `blocking=True`.
  4. narración (no épica) → `REPAIR` (defecto `not_epic`).
  5. proceso inventado + `catalog_blocking_enabled=True` → `NEEDS_REVIEW`, `blocking=True`, `catalog_unknown` no vacío.
  6. proceso inventado + `catalog_blocking_enabled=False` → no bloquea por catálogo (solo warning).
  7. **Idempotencia/determinismo:** dos llamadas idénticas → mismo `GateVerdict`.
- Ruta: `Stacky Agents/backend/tests/test_epic_autopublish_backend.py` (extender el existente):
  8. con `STACKY_EPIC_GATE_ENABLED=true` y épica con hueco → `autopublish_epic_from_run` devuelve `error` con prefijo `epic_gate_blocked`, `ado_id=None`.
  9. con `STACKY_EPIC_GATE_ENABLED=false` → comportamiento idéntico al actual (no-regresión).

**Comando.**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_epic_gate.py" "Stacky Agents/backend/tests/test_epic_autopublish_backend.py" -q
```

**Criterio de aceptación BINARIO.** 9 casos verdes; con flag OFF, los tests preexistentes de autopublish siguen verdes (no-regresión).

**Flags + defaults seguros.**
- `STACKY_EPIC_GATE_ENABLED` (default `false`). Helper `_epic_gate_enabled()` en tickets.py (patrón idéntico a `_epic_sanitize_enabled`, `tickets.py:5445`).
- `STACKY_EPIC_CATALOG_GATE_ENABLED` (default `false`). Helper `_epic_catalog_gate_enabled()`. Bloqueo por catálogo es opt-in dentro de opt-in.

**Impacto por runtime.**
- **Claude Code CLI:** gate completo. REPAIR dispara pase correctivo inline (`_send_system_message`); NEEDS_REVIEW bloquea autopublish con error ruidoso.
- **Codex CLI / GitHub Copilot Pro:** NO invocan `_maybe_autopublish_epic` (verificado: `claude_code_cli_runner.py:1163` es el único call site). Por tanto el gate de autopublish no corre para ellos hoy; la función pura está disponible si alguna vez se cablea su autopublish. **Fallback explícito:** Codex/Copilot no autopublican épica → el operador publica vía el handshake del navegador, que ya pasa por `_looks_like_epic` en el call site de `api/tickets.py` (publishEpic). El gate duro adicional queda pendiente de su wiring (declarado, no oculto). NO afirmar "paridad 3 runtimes" del wiring.

**Trabajo del operador:** ninguno (opt-in, default off; al activar sigue siendo invisible).

---

### F4 — Telemetría `gate_decision` en `epic_summary` (observable, sin UI nueva obligatoria)

**Objetivo (1 frase).** Sellar la decisión del gate en `epic_summary` para que K1-K4 sean medibles desde la telemetría existente, sin agregar campos obligatorios a la UI.

**Valor.** Observabilidad de cuántas épicas pasan limpio vs reparadas vs degradadas, reusando el canal `epic_summary` (plan 42 F4) que ya viaja a metadata.

**Archivos a editar:**
- `Stacky Agents/backend/api/tickets.py` (`build_epic_summary`, `tickets.py:5637`, y el call site `tickets.py:5922`)

**Diseño exacto.** Agregar parámetro OPCIONAL `gate_decision: str | None = None` a `build_epic_summary` (backward-compatible: default None = comportamiento actual) y un nuevo key en el dict resultante:

```python
def build_epic_summary(*, ..., sanitize_changed: bool = False, gate_decision: str | None = None) -> dict:
    return {
        ...,
        "epic_sanitize_changed": bool(sanitize_changed),
        "gate_decision": gate_decision,  # "pass" | "repair" | "needs_review" | None (gate OFF)
    }
```

En el call site (`tickets.py:5922`), pasar `gate_decision=_verdict.decision.value if _epic_gate_enabled() else None`.

**Tests PRIMERO (TDD).**
- Ruta: `Stacky Agents/backend/tests/test_epic_gate.py` o el test existente de `build_epic_summary` (verificar cuál con grep `build_epic_summary` en tests).
- Casos: `build_epic_summary(..., gate_decision="pass")` incluye `gate_decision="pass"`; sin pasar el kwarg → `gate_decision=None` (no-regresión del schema previo + las claves preexistentes intactas).

**Comando.**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_epic_gate.py" -q
```

**Criterio de aceptación BINARIO.** El dict de `build_epic_summary` contiene `gate_decision` y los tests preexistentes de `epic_summary` siguen verdes.

**Flag.** Hereda `STACKY_EPIC_GATE_ENABLED` (None cuando OFF).

**Impacto por runtime.** Solo aplica donde corre autopublish (Claude CLI). Fallback: `None` para los demás.

**Trabajo del operador:** ninguno.

---

### F5 — Conformance + centinela de no-determinismo (blindaje plan 49 F3/F5)

**Objetivo (1 frase).** Garantizar que `evaluate_epic_gate`, `classify_structural_severity` y `golden_catalog_diff` son deterministas y consistentes entre runtimes, reusando el conformance del plan 49.

**Valor.** Impide que el gate introduzca no-determinismo (reloj/locale/orden) o divergencia silenciosa entre runtimes.

**Archivos a editar:**
- `Stacky Agents/backend/tests/conformance/test_runtime_conformance.py`

**Diseño exacto.** Agregar a la suite de conformance:
1. **Centinela de pureza/determinismo:** para un set fijo de HTMLs+catálogos, llamar cada función pura 2 veces y assertar igualdad; assertar que el resultado NO cambia al variar `LANG`/`LC_ALL` (setear env temporal) ni el orden de los inputs de lista.
2. **Conformance de runtime:** assertar que las 3 runtimes resuelven el MISMO `GateVerdict` para el mismo `clean_html`+catálogo (las funciones son puras y compartidas, así que el assert es: importar `harness.epic_gate` no depende del runtime; documentar que el WIRING difiere pero la función pura no).

**Tests PRIMERO (TDD).**
- Casos: determinismo bajo cambio de locale; idempotencia de las 3 funciones; `GateVerdict` estable.

**Comando.**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/conformance/test_runtime_conformance.py" -q
```

**Criterio de aceptación BINARIO.** Conformance verde; centinela detecta (en un test negativo controlado) si se introdujera un `sorted` faltante.

**Flag.** Ninguno (tests).

**Impacto por runtime.** Verifica los 3.

**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El gate bloquea épicas legítimas (falso positivo) y frena autopublish que antes funcionaba. | Flag `STACKY_EPIC_GATE_ENABLED` default OFF; partición de severidad conservadora (solo huecos/cuerpo-vacío bloquean); telemetría `gate_decision` para medir tasa antes de subir a ON. |
| R2 | El pase correctivo extra quema tokens. | REPAIR es CONDICIONAL al defecto puro detectado; UN solo intento (reusa `_epic_repair_done`/`autocorrect.attempts` budget existente); caso feliz = 0 tokens. |
| R3 | Refactor de `_catalog_grounding_warnings` cambia el string del warning y rompe tests/telemetría. | Test de no-regresión del string exacto (F2); el refactor es pura extracción sin cambio de salida. |
| R4 | Divergencia de detección entre runner (FORMA) y autopublish (FORMA+catálogo). | El runner pasa `process_catalog=None` y `catalog_blocking_enabled=False` a propósito (solo repara forma); el catálogo se chequea una sola vez, en autopublish. Documentado en el wiring. |
| R5 | No-determinismo por locale/orden en los regex/sets. | Todo resultado `sorted`; centinela F5; sin reloj/locale. |
| R6 | Import circular `harness.epic_gate` ↔ `api.tickets`. | `evaluate_epic_gate` recibe `looks_like_epic_fn` por inyección; los imports de tickets dentro de `golden_catalog_diff` son lazy (dentro de la función). |

## 6. Fuera de scope

- **Doble-generación / generar la épica dos veces y comparar** (riesgo de costo de tokens). Solo nota de futuro: posible opt-in atado a `effort=max`, fuera de este plan.
- **Reescribir/alucinar reemplazos** de procesos inventados. F2 solo MARCA; nunca sustituye.
- **Cablear autopublish en Codex/Copilot.** El gate corre donde corre autopublish (Claude CLI). Extender el wiring a otros runtimes es trabajo futuro.
- **Cambiar `_sanitize_epic_html`** (plan 50, FORMA) ni `_extract_epic_html`. Se reusan tal cual.
- **UI nueva.** `gate_decision` viaja en `epic_summary` (ya visible en el drawer existente); ninguna card nueva obligatoria.
- **Re-detectar** estructura/catálogo: F1/F2 reusan `_structural_epic_warnings` y `catalog_unknown_processes`.

## 7. Glosario, orden de implementación y DoD global

**Glosario:**
- **GateDecision:** enum `pass`/`repair`/`needs_review`. Decisión determinista del gate.
- **GateVerdict:** NamedTuple con decisión + defectos + procesos desconocidos + `blocking`.
- **REPAIR:** defecto de forma reparable inline por el pase correctivo (Claude CLI).
- **NEEDS_REVIEW (gate):** defecto no reparable inline o proceso inventado con bloqueo ON → autopublish bloqueado, run a `needs_review`.
- **Golden Catalog Diff:** lista pura de procesos citados ausentes del `process_catalog`.

**Orden de implementación:** F0 (esqueleto) → F1 (`classify_structural_severity`) ∥ F2 (`golden_catalog_diff` + refactor + golden-set) → F3 (`evaluate_epic_gate` + wiring) → F4 (telemetría) → F5 (conformance/centinela).

**Definition of Done global (binario):**
1. `harness/epic_gate.py` existe con `GateDecision`, `GateVerdict`, `classify_structural_severity`, `golden_catalog_diff`, `evaluate_epic_gate`.
2. Golden-set a mano en `evals/catalog_diff_fixtures/` (≥6 fixtures) + runner + test verde.
3. `tests/test_epic_gate.py`, `tests/test_golden_catalog_diff.py`, `tests/test_epic_autopublish_backend.py`, `tests/conformance/test_runtime_conformance.py` verdes con el python del `.venv` (por archivo).
4. Idempotencia y NO-OP probados explícitamente para las 3 funciones puras.
5. Con `STACKY_EPIC_GATE_ENABLED=false` (default): comportamiento idéntico al actual; cero regresiones.
6. Con `STACKY_EPIC_GATE_ENABLED=true`: épica con hueco → autopublish bloqueado ruidoso; épica verde → publica sin tokens extra.
7. `.env.example` documenta `STACKY_EPIC_GATE_ENABLED` y `STACKY_EPIC_CATALOG_GATE_ENABLED` (ambos default off).
8. Trabajo del operador: ninguno (opt-in, default off).
9. Sin datos personales en fixtures ni telemetría.
