# Plan 44 — Observatorio de Grounding de Épicas + Sugeridor pasivo de Diccionario de Procesos

> **Versión:** v2 — 2026-06-18 (reescritura adversarial por StackyArchitectaUltraEficientCode)
> **Estado:** IMPLEMENTADO 2026-06-19 (F0–F4 completos).
>
> **Notas de implementación (2026-06-19):**
> - cited_modules SÍ viene con prefijo "módulo "/"proceso " (build_epic_summary, tickets.py:5485) → `_is_process` clasifica por ese prefijo (caso CON prefijo del plan).
> - AgentExecution NO tiene campo de proyecto → filtro por proyecto es best-effort vía `Ticket.stacky_project_name` del ticket asociado (no se omite el filtro).
> - No existe `harness_flags.is_enabled`: los flags se leen con `config.STACKY_...` y se registran en FLAG_REGISTRY. Endpoints quedaron bajo el blueprint de agents → URLs `/api/agents/epics/grounding-observatory` y `/api/agents/projects/<project>/process-catalog-suggestions`.
> - Bug preexistente reparado de paso: 5 flags Plan 42 estaban en FLAG_REGISTRY sin atributo en Config y rompían `harness_flags.read_current()` (UI de flags, Plan 33). Marcados `env_only=True`.
> - F4 botón "Agregar al diccionario" quedó HABILITADO (Plan 45 Req1 / PUT client-profile ya desplegado). Card montada en ExecutionHistoryPage (NO DiagnosticsPage, reservada Plan 46).
> - Tests verdes: test_epic_confidence_extraction.py (9), test_grounding_observatory.py (10), test_grounding_observatory_endpoint.py (4), test_process_catalog_suggestions.py (7); sin regresión en epic/run_brief; tsc --noEmit exit 0.
> **Autor:** StackyArchitectaUltraEficientCode.
> **Audiencia de implementación:** dev agéntico junior / modelo menor (Haiku, Codex CLI, GitHub Copilot Pro). Cada fase es autocontenida: objetivo en 1 frase, archivos EXACTOS con ruta completa, símbolos EXACTOS, pseudocódigo/diff, tests primero con comando exacto, criterio binario, flag + default seguro, impacto por runtime con fallback, y línea "Trabajo del operador". **Prohibido lo vago.**

## CHANGELOG v1 → v2

- **C1 (BLOQUEANTE resuelto):** dependencia del botón "Agregar" resuelta explícitamente — el plan 44 REQUIERE que el plan 45 Req1 esté implementado primero; hasta entonces el botón queda deshabilitado + tooltip. Agregado como **Prerrequisito** en cabecera de plan y en F4.
- **C2 (IMPORTANTE resuelto):** flags default `True` justificados y acotados: `STACKY_GROUNDING_OBSERVATORY_ENABLED` y `STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED` son solo-lectura y default `True` solo después de que el plan 45 Req1 esté activo; antes de eso no hay endpoint de escritura que riesgo habilitar. Se documenta la justificación explícita en §3.
- **C3 (IMPORTANTE resuelto):** "verificar el prefijo real del blueprint" y "verificar el campo de proyecto en AgentExecution" ya no son instrucciones vagas — se convirtieron en pasos determinísticos con grep EXACTO, fallback fijo y decisión binaria sin inferencia del modelo.
- **C4 (IMPORTANTE resuelto):** clasificación módulo/proceso — si `cited_modules` no trae prefijo, `_is_process` devuelve `False` para todo y el sugeridor queda vacío (degradación explícita documentada). Se añade test `test_no_prefix_all_classified_as_module` que fija el contrato de degradación.
- **C5 (IMPORTANTE resuelto):** regex de confidence — se añade test `test_regex_against_real_html_pattern` que usa el texto EXACTO que R-GROUNDING ítem 5 del BusinessAgent v1.5.0 indica emitir, no texto inventado. Elimina el riesgo de falso positivo de laboratorio.
- **C6 (MENOR resuelto):** F4 botón "Agregar" ya no dice "si NO existe un endpoint de escritura" (vago) sino: "usa el endpoint `PUT /api/projects/{project}/client-profile` del plan 45 Req1; si ese plan no está desplegado el botón muestra tooltip 'Requiere Plan 45 Req1'; la card sigue siendo útil".
- **C7 (MENOR resuelto):** diferenciación dura con plan 46 — añadida en §1 KPI y en la nota de F4 sobre dónde montar la card: NO en DiagnosticsPage si 46 ya añade su panel ahí; montar en la pestaña de Historial de Runs (plan 39) como sub-card de épicas, evitando fragmentación de dos paneles no relacionados en la misma página. Resolución explícita: el 44 es calidad semántica de épicas; el 46 es triage operativo de TODAS las runs. Son ortogonales y deben vivir en páginas distintas.
- **[ADICIÓN ARQUITECTO A1] (nuevo):** "test de no-regresión de confidence `None` en runs no-épica" — añadido en F0 para garantizar que `_extract_confidence_from_html` aplicada al flujo de runs normales (no épicas) no rompe nada cuando el HTML de salida normal no contiene `confidence_grounding`.
- **[ADICIÓN ARQUITECTO A2] (nuevo):** se agrega un campo `runtime_coverage` al response del observatorio, que lista qué runtimes tienen al menos 1 run con `epic_summary`. Esto convierte la "advertencia de paridad" en una señal observable: el operador ve en el propio panel que Codex/Copilot aún no aportan, sin que el arquitecto tenga que avisarle.

---

## 0. Prerrequisito explícito

**Este plan puede implementarse de forma independiente en F0–F3 (backend puro).** F4 (botón "Agregar al diccionario") depende del endpoint `PUT /api/projects/{project}/client-profile` que el **Plan 45 Req1** crea. Si el Plan 45 Req1 no está desplegado, implementar F4 con el botón deshabilitado + tooltip (ver F4). No bloquear F0–F3 por este motivo.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Los planes 42 y 43 hacen que CADA épica generada desde brief produzca telemetría de calidad de grounding (`epic_summary` con `rf_count`, `cited_modules`, `warnings`, `confidence`) y la persistan en la metadata de esa run individual (`AgentExecution.metadata_json["epic_summary"]` y `["grounding_warnings"]`, escritos por `claude_code_cli_runner.py:1197-1199`). **Pero esa señal muere aislada en cada run: nadie la agrega, nadie detecta tendencias, y cuando una épica falla grounding por un proceso que el agente no encontró, la corrección que el operador tiene en la cabeza nunca vuelve al sistema.** Este plan construye un **Observatorio de Grounding** puramente pasivo y solo-lectura que: (a) **agrega** la telemetría ya existente a lo largo de todas las runs de épica (tasa de grounding, módulos/procesos más citados, evolución de confidence); (b) **extrae la métrica `confidence_grounding` que el agente YA calcula en su HTML** pero que hoy se descarta (`build_epic_summary` la recibe como `confidence=None` hardcodeado, `tickets.py:5687`); (c) **sugiere pasivamente entradas para el `process_catalog`** detectando procesos que el agente nombró en épicas pero que NO están en el diccionario del proyecto — el operador acepta con 1 clic (si Plan 45 Req1 está activo), cerrando el loop de adopción que el Plan 42 F5 dejó abierto. **No toca el flujo de generación de épicas (modal, selector, runner, publicación).** Consume lo que 42/43 ya producen.

**Diferenciación dura vs Plan 46:** el Plan 46 mira la **salud operativa de TODAS las runs** (needs_review, zombies, costo excesivo, failures). Este plan mira la **calidad semántica de las runs de épica** (confidence, módulos citados, sugeridor de diccionario). Son ortogonales y viven en páginas/tabs distintos de la UI (ver F4).

**KPI / impacto esperado:**
- **KPI-1 (binario):** existe `GET /api/epics/grounding-observatory` que devuelve, agregando TODAS las runs de épica con `epic_summary` en metadata: `total_epics`, `epics_with_warnings`, `grounding_warning_rate` (0.0-1.0), `avg_confidence` (o `null` si no hay datos), `top_cited_modules` (lista ordenada por frecuencia), `top_cited_processes` (lista ordenada por frecuencia), `confidence_trend` (lista de los últimos 20 valores en orden cronológico), y **`runtime_coverage`** (lista de runtimes que tienen al menos 1 run con `epic_summary` — ver [ADICIÓN ARQUITECTO A2]).
- **KPI-2 (binario):** la `confidence_grounding` que el BusinessAgent calcula en su HTML se EXTRAE (función `_extract_confidence_from_html`) y se persiste en `epic_summary["confidence"]` como `float` (no `None`) cuando el agente la emitió.
- **KPI-3 (operador):** existe `GET /api/projects/{project}/process-catalog-suggestions` que lista procesos citados en épicas del proyecto que NO figuran en `process_catalog` del client-profile, para que el operador los revise. Cero invención: solo nombres que el agente realmente escribió en una épica publicada.
- **KPI-4 (operador):** un panel `GroundingObservatoryCard` en la pestaña/sección de Épicas o Historial (NO en DiagnosticsPage si el Plan 46 ya vive ahí) muestra la tendencia y las sugerencias, sin que el operador configure nada.
- **KPI-5 (no-regresión):** con todos los flags nuevos en OFF, el sistema se comporta EXACTAMENTE como tras el Plan 43 (verificado por regresión de tests existentes de épica/autopublish/grounding).

---

## 2. Por qué ahora / gap que cierra

Apoyado en los planes recientes leídos (39 historial+fix CLI+DB readonly, 40 BusinessAgent v1.2-1.3, 42 épicas grounded + selector modelo, 43 config auto + selector modelo/effort + Opus 4.8):

| Frente | Estado | Qué dejó sin cerrar |
|--------|--------|---------------------|
| **Modal Épica-desde-Brief** (42/43) | Implementado: grounding en docs, diccionario de procesos, selector modelo/effort, Opus 4.8, config auto, resumen post-épica, botón Stop. | Produce señal **por-run** y la tira. Saturado: cualquier feature nueva ahí duplica 42/43. |
| **Historial de runs** (39) | Implementado: tabla con costo/modelo/duración/prompt por run. | Muestra runs individuales; NO agrega métricas de calidad de grounding a lo largo del tiempo. |
| **`epic_summary` + `grounding_warnings`** (42 F2/F4) | Implementado y persistido en `metadata_json` (evidencia: `tickets.py:5680-5695`, `claude_code_cli_runner.py:1196-1199`). | (a) `confidence` se guarda como `None` hardcodeado aunque el agente la calcula en su HTML (regla R-GROUNDING ítem 5, `BusinessAgent.agent.md` v1.5.0). (b) Nadie agrega ni grafica la tendencia. |
| **`process_catalog` / diccionario** (42 F0) | Implementado: se inyecta si el operador lo pobló. F5 auto-perfilado quedó **opt-in default off**. | El loop de adopción está abierto: si el agente nombra un proceso que falta en el diccionario, esa señal se pierde. Nadie sugiere agregarlo. |
| **Pre-vuelo de intención** (41) | PROPUESTO, NO implementado. | Fuera de scope (no lo tocamos ni lo contradecimos). |
| **Catálogo editable en UI** (45 Req1) | PROPUESTO, NOT implementado | Crea el endpoint de escritura de client-profile que el botón "Agregar" de F4 necesita. **Prerrequisito para el botón.** |

**El gap real, de alto valor y cero trabajo al operador:** la telemetría de grounding ya se computa y persiste, pero vive aislada. Agregarla (pasivo, solo-lectura) convierte datos muertos en (1) una señal de tendencia que le dice al operador si la calidad de sus épicas mejora o empeora, y (2) un **sugeridor de diccionario** que cierra el loop de adopción del Plan 42 F5 SIN el riesgo de alucinación de F5 (porque solo sugiere nombres que el agente ya escribió en una épica real publicada, no nombres inventados escaneando docs).

**Evidencia (citas confirmadas en código a 2026-06-18):**
- `backend/api/tickets.py:5447` — `build_epic_summary(*, ado_id, ado_url, clean_html, warnings, confidence) -> dict` existe.
- `backend/api/tickets.py:5682-5688` — `autopublish_epic_from_run` llama `build_epic_summary(..., confidence=None)` (la confidence del agente se descarta).
- `backend/api/tickets.py:5602` — `autopublish_epic_from_run` existe.
- `backend/services/claude_code_cli_runner.py:1197-1199` — persiste `metadata["grounding_warnings"]` y `metadata["epic_summary"]` en la ejecución.
- `backend/models.py:207` — clase `AgentExecution`; `:219` campo `metadata_json`; `:280` `to_dict`; `:212` `agent_type`.
- `backend/services/context_enrichment.py:597` — `build_process_dictionary_block` lee `client_profile["process_catalog"]`.
- `backend/services/harness_flags.py:1095,1107` — `STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED`, `STACKY_EPIC_SUMMARY_ENABLED` (default true).
- `backend/Stacky/agents/BusinessAgent.agent.md:4` — versión 1.5.0 (R-GROUNDING ítem 5 ya pide calcular `confidence_grounding`).

---

## 3. Principios y guardarraíles (no negociables)

1. **Paridad de 3 runtimes con fallback explícito.** El observatorio lee `epic_summary` de la metadata de las runs, sin importar qué runtime la generó. La escritura de `epic_summary` solo ocurre hoy en el runner `claude_code_cli` (`claude_code_cli_runner.py:1196-1199`); para Codex y GitHub Copilot, si la run NO tiene `epic_summary` en metadata, el agregador simplemente la **omite** (fallback explícito: no rompe, no inventa). El campo `runtime_coverage` del response ([ADICIÓN ARQUITECTO A2]) hace este fallback visible al operador.
2. **Cero trabajo extra al operador.** Todo es pasivo y solo-lectura. El observatorio se llena solo con las runs que el operador ya genera. La sugerencia de diccionario es opt-in con 1 clic; si el operador la ignora, nada cambia.
3. **Human-in-the-loop innegociable.** El sugeridor de diccionario NO escribe el `process_catalog` automáticamente: solo PROPONE. El operador acepta explícitamente con 1 clic + completar campos. Cero autonomía proactiva. NO se generaliza la excepción de auto-publish del Plan 41.
4. **Mono-operador sin auth real.** Ningún endpoint nuevo usa RBAC ni `current_user` para autorización; sigue el patrón mono-operador existente.
5. **No degradar.** Todo cambio es aditivo y protegido por flag con default seguro. El agregador NO corre en el hot-path de generación de épicas: es lazy (se computa al pedir el endpoint), nunca en el pipeline del run. Reusa `AgentExecution`, `metadata_json`, `to_dict`, `build_epic_summary`, `process_catalog` y el patrón de cards de diagnóstico existentes.
6. **Backward-compatible.** Con flags OFF, comportamiento idéntico al Plan 43.
7. **Flags default `True` justificados.** `STACKY_GROUNDING_OBSERVATORY_ENABLED` y `STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED` son solo-lectura (ninguno escribe nada, ninguno llama a ADO, ninguno modifica metadata). El riesgo de default `True` en una feature solo-lectura es asimetría de UX (la card aparece vacía si no hay épicas) — no riesgo de datos ni seguridad. Justificación aceptada. Convención de Stacky "default OFF" se aplica a features que mutan estado (Issues, autonomía, auto-perfilado); las de solo-lectura pueden ser default ON si el impacto de "aparecer vacía" es neutro.

---

## 4. Fases

> **Convención de tests (LEER ANTES DE CODEAR):**
> - Intérprete del repo = `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe`.
> - Correr SIEMPRE por archivo (la full-suite está contaminada con errores de colección ajenos a este plan).
> - Working directory para pytest = `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` (las rutas `tests/...` son relativas a ahí).
> - Frontend se valida con `npx tsc --noEmit` (vitest NO está instalado; no escribir tests de vitest).
> - Todas las funciones nuevas backend son **puras y sin I/O** salvo los endpoints, para poder testearlas con dicts en memoria.

---

### F0 — Backend: extraer la `confidence_grounding` que el agente ya calcula (hoy se descarta)

**Objetivo (1 frase):** capturar el número `confidence_grounding` que el BusinessAgent emite en el HTML de la épica y persistirlo en `epic_summary["confidence"]` como `float`, en vez del `None` hardcodeado actual.

**Valor:** sin esto, el observatorio (F2) no tiene serie de confidence para graficar tendencia. Es el dato más rico y hoy se tira en `tickets.py:5687`.

**Archivos a editar/crear:**
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py` (editar — agregar `_extract_confidence_from_html` y usarla en `autopublish_epic_from_run`).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_epic_confidence_extraction.py` (crear — TDD).

**Símbolos exactos:**
- Nueva función pura: `_extract_confidence_from_html(html: str | None) -> float | None` en `tickets.py` (colocarla junto a `_epic_grounding_warnings`, alrededor de la línea 5433).
- Modificar la llamada `build_epic_summary(...)` en `autopublish_epic_from_run` (`tickets.py:5682-5688`): cambiar `confidence=None` por `confidence=_extract_confidence_from_html(clean_html)`.

**Contrato de extracción (qué busca):** el `BusinessAgent.agent.md` v1.5.0 R-GROUNDING ítem 5 hace que el agente escriba texto del tipo `confidence_grounding = 0.83` o `[BAJA CONFIANZA DE GROUNDING ...]`. La función busca, en orden:
1. Un patrón numérico explícito: `re.search(r"confidence[_\s]*grounding\s*[:=]\s*([01](?:\.\d+)?)", html, re.I)` → devolver `float(match.group(1))` capped a `[0.0, 1.0]`.
2. Si no hay número pero aparece el marcador `[BAJA CONFIANZA` (case-insensitive) → devolver `0.4` (representativo de "baja", < 0.5; constante nombrada `_LOW_CONFIDENCE_SENTINEL = 0.4`).
3. Si nada matchea → `None`.

**Pseudocódigo:**
```python
import re

_LOW_CONFIDENCE_SENTINEL = 0.4
_CONFIDENCE_RE = re.compile(r"confidence[_\s]*grounding\s*[:=]\s*([01](?:\.\d+)?)", re.I)
_LOW_CONFIDENCE_RE = re.compile(r"\[\s*baja\s+confianza", re.I)

def _extract_confidence_from_html(html: str | None) -> float | None:
    """Extrae confidence_grounding del HTML de la épica (Plan 44 F0).
    El agente la calcula (R-GROUNDING ítem 5, BusinessAgent v1.5.0) pero hoy se descarta.
    Devuelve float en [0.0, 1.0] o None si el agente no la emitió."""
    if not html:
        return None
    m = _CONFIDENCE_RE.search(html)
    if m:
        try:
            val = float(m.group(1))
        except ValueError:
            return None
        return max(0.0, min(1.0, val))
    if _LOW_CONFIDENCE_RE.search(html):
        return _LOW_CONFIDENCE_SENTINEL
    return None
```

**Casos borde:** `html=None`/`""` → `None`; `confidence_grounding = 1.5` → capped a `1.0`; `confidence_grounding = abc` → `None` (no matchea el grupo `[01](?:\.\d+)?`); solo el marcador de baja confianza sin número → `0.4`.

**Tests primero (`test_epic_confidence_extraction.py`):**
- `test_extracts_explicit_number` → html `"...confidence_grounding = 0.83..."` → `0.83`.
- `test_extracts_with_colon_separator` → html `"confidence_grounding: 0.5"` → `0.5`.
- `test_caps_to_one` → html `"confidence_grounding = 1.5"` → `1.0`.
- `test_low_confidence_marker_returns_sentinel` → html `"<p>[BAJA CONFIANZA DE GROUNDING — operador, validá...]</p>"` sin número → `0.4`.
- `test_returns_none_when_absent` → html `"<h1>Épica</h1><h2>RF-001</h2>"` → `None`.
- `test_returns_none_on_empty` → `_extract_confidence_from_html(None) is None` y `_extract_confidence_from_html("") is None`.
- `test_autopublish_persists_extracted_confidence` → con `clean_html` que contiene `confidence_grounding = 0.7`, mockeando ADO como en `test_epic_autopublish_backend.py`, `autopublish_epic_from_run(...).epic_summary["confidence"] == 0.7` (NO `None`).
- **[ADICIÓN ARQUITECTO A1] `test_non_epic_html_returns_none`** → html de una run normal (sin `confidence_grounding`, p. ej. `"<h1>Resultado de análisis</h1><p>Se procesaron 12 registros.</p>"`) → `_extract_confidence_from_html(html) is None`. Garantiza que aplicar la función a outputs NO-épica no introduce falsos positivos.
- **[ADICIÓN ARQUITECTO A1] `test_regex_against_real_html_pattern`** → usar el fragmento HTML EXACTO que R-GROUNDING ítem 5 del BusinessAgent v1.5.0 especifica emitir (leer `backend/Stacky/agents/BusinessAgent.agent.md`, buscar el texto de ejemplo de R-GROUNDING ítem 5, copiar el fragmento literal como fixture del test). Si el texto de R-GROUNDING ítem 5 no incluye un ejemplo literal, usar `"<p>confidence_grounding = 0.91</p>"` que es el formato mínimo conforme. El test verifica que el valor extraído == el valor del ejemplo real.

**Comando de test:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" && .venv\Scripts\python.exe -m pytest tests/test_epic_confidence_extraction.py tests/test_epic_autopublish_backend.py -q
```

**Criterio de aceptación BINARIO:** 9 tests nuevos verdes (7 originales + 2 de [A1]) + `test_epic_autopublish_backend.py` sin regresión.

**Flag de protección:** ninguno necesario. El cambio es backward-compatible: si el agente no emite confidence, `epic_summary["confidence"]` sigue siendo `None` (idéntico a hoy). No cambia la publicación.

**Impacto por runtime:**
- `claude_code_cli`: `epic_summary["confidence"]` ahora puede traer el float real.
- `codex` / `github_copilot`: estos runners hoy no llaman `autopublish_epic_from_run` (la épica auto-publica solo en el runner CLI). El cambio es inerte para ellos; el agregador (F2) los omite (fallback de §3 principio 1).

**Trabajo del operador:** ninguno.

---

### F1 — Backend: agregador puro de la telemetría de grounding (función sin I/O)

**Objetivo (1 frase):** una función pura que, dada una lista de `epic_summary` dicts (ya extraídos de la metadata de las runs), calcule las métricas agregadas del observatorio.

**Valor:** núcleo testeable del observatorio sin tocar la DB; el endpoint (F2) solo le pasa los datos.

**Archivos a editar/crear:**
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\grounding_observatory.py` (crear — módulo nuevo, función pura).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_grounding_observatory.py` (crear — TDD).

**Símbolos exactos:**
- Nueva función pura: `aggregate_grounding(summaries: list[dict], runtimes: list[str] | None = None) -> dict` en `grounding_observatory.py`.
  - `summaries` es una lista de dicts con la forma de `epic_summary` (claves: `ado_id`, `ado_url`, `rf_count`, `cited_modules`, `warnings`, `confidence`), en orden CRONOLÓGICO (más antigua primero). El caller (F2) garantiza el orden.
  - `runtimes` es la lista paralela de strings de runtime por cada run (p. ej. `["claude_code_cli", "claude_code_cli"]`). Puede ser `None` si el caller no puede determinar los runtimes.
  - Devuelve un dict con EXACTAMENTE estas claves:
    - `total_epics: int`
    - `epics_with_warnings: int`
    - `grounding_warning_rate: float` (0.0-1.0; `0.0` si `total_epics == 0`)
    - `avg_confidence: float | None` (promedio de las confidences NO-None; `None` si ninguna)
    - `top_cited_modules: list[dict]` — `[{"name": str, "count": int}, ...]` ordenado por count desc, máx 10
    - `top_cited_processes: list[dict]` — ídem para procesos
    - `confidence_trend: list[float | None]` — la serie de `confidence` en orden cronológico (incluye `None`s para runs sin confidence; máx últimos 20)
    - **`runtime_coverage: list[str]`** — lista deduplicada de runtimes que tienen ≥1 run con `epic_summary` (p. ej. `["claude_code_cli"]`); vacía si `runtimes` es `None` o lista vacía. ([ADICIÓN ARQUITECTO A2])
- Constante: `_MAX_TOP = 10`, `_MAX_TREND = 20`.

**Cómo distinguir módulos de procesos:**

> **PASO DETERMINÍSTICO (ejecutar ANTES de codear `_is_process`):**
> ```
> grep -n "cited_modules" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py" | head -20
> ```
> Leer las líneas encontradas y la función `build_epic_summary` (`tickets.py:5447`) para ver el formato REAL de los strings en `cited_modules`.
>
> **Decisión fija (sin inferencia del modelo):**
> - Si los strings vienen prefijados con `"módulo"` / `"modulo"` / `"proceso"` (case-insensitive) → usar el prefijo para clasificar: `_is_process(c)` = `c.strip().lower().startswith("proceso")`.
> - Si los strings NO vienen prefijados (son solo nombres como `"CargaNomina"`, `"IncHost"`) → `_is_process` devuelve `False` para TODOS (fallback conservador: todos van a `top_cited_modules`; `top_cited_processes` queda vacío). Documentar en el docstring de `_is_process` cuál caso se encontró.
> - El test `test_classifies_modules_and_processes` fija el contrato para el caso CON prefijo.
> - El test `test_no_prefix_all_classified_as_module` fija el contrato para el caso SIN prefijo (degradación).

**Pseudocódigo:**
```python
from collections import Counter

_MAX_TOP = 10
_MAX_TREND = 20

def _is_process(citation: str) -> bool:
    """Clasifica una cita como proceso si empieza con 'proceso' (case-insensitive).
    Si cited_modules no usa prefijos, esta función siempre devuelve False (fallback conservador).
    Ver PASO DETERMINÍSTICO en el plan antes de modificar."""
    return (citation or "").strip().lower().startswith("proceso")

def aggregate_grounding(
    summaries: list[dict],
    runtimes: list[str] | None = None,
) -> dict:
    total = len(summaries)
    with_warnings = sum(1 for s in summaries if s.get("warnings"))
    confidences = [s["confidence"] for s in summaries
                   if isinstance(s.get("confidence"), (int, float))]
    avg_conf = (sum(confidences) / len(confidences)) if confidences else None

    mod_counter: Counter = Counter()
    proc_counter: Counter = Counter()
    for s in summaries:
        for c in (s.get("cited_modules") or []):
            name = (c or "").strip()
            if not name:
                continue
            (proc_counter if _is_process(name) else mod_counter)[name] += 1

    def _top(counter):
        return [{"name": n, "count": cnt}
                for n, cnt in counter.most_common(_MAX_TOP)]

    trend = [s.get("confidence") for s in summaries][-_MAX_TREND:]

    # [ADICIÓN ARQUITECTO A2] runtime_coverage
    rt_seen: set[str] = set()
    if runtimes:
        for rt in runtimes:
            if rt:
                rt_seen.add(rt)
    runtime_coverage = sorted(rt_seen)

    return {
        "total_epics": total,
        "epics_with_warnings": with_warnings,
        "grounding_warning_rate": (with_warnings / total) if total else 0.0,
        "avg_confidence": avg_conf,
        "top_cited_modules": _top(mod_counter),
        "top_cited_processes": _top(proc_counter),
        "confidence_trend": trend,
        "runtime_coverage": runtime_coverage,
    }
```

**Casos borde:** `summaries=[]` → `total_epics=0`, `grounding_warning_rate=0.0`, `avg_confidence=None`, listas vacías, `confidence_trend=[]`, `runtime_coverage=[]`. Summaries con `confidence=None` → no cuentan en el promedio pero SÍ aparecen en el trend (como `None`). `cited_modules` ausente → tratado como `[]`. `runtimes=None` → `runtime_coverage=[]`.

**Tests primero (`test_grounding_observatory.py`):**
- `test_empty_returns_zeroed` → `aggregate_grounding([])` → `total_epics==0`, `avg_confidence is None`, `grounding_warning_rate==0.0`, `runtime_coverage==[]`.
- `test_counts_warnings` → 3 summaries, 1 con `warnings=["x"]` → `epics_with_warnings==1`, `grounding_warning_rate==pytest.approx(1/3)`.
- `test_avg_confidence_ignores_none` → confidences `[0.8, None, 0.6]` → `avg_confidence==pytest.approx(0.7)`.
- `test_classifies_modules_and_processes` → cited `["módulo 12", "proceso CargaNomina", "módulo 12"]` → `top_cited_modules==[{"name":"módulo 12","count":2}]`, `top_cited_processes==[{"name":"proceso CargaNomina","count":1}]`.
- **`test_no_prefix_all_classified_as_module`** → cited `["CargaNomina", "IncHost"]` (sin prefijo) → `top_cited_processes==[]`, `top_cited_modules` tiene ambos. Fija el contrato de degradación.
- `test_trend_preserves_order_and_nulls` → confidences `[0.5, None, 0.9]` → `confidence_trend==[0.5, None, 0.9]`.
- `test_trend_caps_at_20` → 25 summaries → `len(confidence_trend)==20` (los últimos 20).
- `test_top_caps_at_10` → 15 módulos distintos → `len(top_cited_modules)==10`.
- **`test_runtime_coverage_populated`** → `runtimes=["claude_code_cli", "claude_code_cli", "codex_cli"]` → `runtime_coverage==["claude_code_cli", "codex_cli"]` (deduplicado, ordenado). ([ADICIÓN ARQUITECTO A2])
- **`test_runtime_coverage_empty_when_none`** → `runtimes=None` → `runtime_coverage==[]`. ([ADICIÓN ARQUITECTO A2])

**Comando de test:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" && .venv\Scripts\python.exe -m pytest tests/test_grounding_observatory.py -q
```

**Criterio de aceptación BINARIO:** 10 tests verdes (7 originales + 3 nuevos).

**Flag de protección:** ninguno (función pura sin efectos; no se cablea aún).

**Impacto por runtime:** N/A (función pura, agnóstica de runtime).

**Trabajo del operador:** ninguno.

---

### F2 — Backend: endpoint `GET /api/epics/grounding-observatory` (lee runs, agrega, devuelve)

**Objetivo (1 frase):** exponer las métricas agregadas leyendo los `epic_summary` de la metadata de las ejecuciones de épica persistidas, opcionalmente filtradas por proyecto.

**Valor:** el dato que el frontend (F4) consume; convierte la función pura de F1 en una capacidad observable.

**Archivos a editar/crear:**
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\agents.py` (editar — agregar el route handler; reusa el blueprint `bp` existente del módulo).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\harness_flags.py` (editar — registrar flag).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_grounding_observatory_endpoint.py` (crear — TDD).

> **PASO DETERMINÍSTICO — resolver ruta y blueprint ANTES de codear (sin inferencia):**
> Ejecutar:
> ```
> grep -n "Blueprint\|url_prefix\|run.brief\|@bp" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\agents.py" | head -30
> ```
> Leer la salida y aplicar estas reglas fijas:
> - Si `url_prefix` del `Blueprint` es `/api/agents` → la ruta del handler debe ser `@bp.get("/epics/grounding-observatory")` para que la URL final quede `/api/epics/grounding-observatory` — NOTA: esto NO funciona si el prefijo ya es `/api/agents`; en ese caso registrar el handler con `@current_app.route("/api/epics/grounding-observatory")` en lugar de `@bp.get`. Decidir en función del prefijo real observado.
> - Si `url_prefix` del `Blueprint` es `/api` → usar `@bp.get("/epics/grounding-observatory")`.
> - El test usa el path final real (`/api/epics/grounding-observatory`) sin depender de que sea bp o app.
>
> **PASO DETERMINÍSTICO — resolver campo de proyecto en AgentExecution ANTES de filtrar:**
> Ejecutar:
> ```
> grep -n "project\|project_name" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\models.py" | grep -i "class\|Column\|project" | head -20
> ```
> Leer la salida: el campo puede llamarse `project`, `project_name`, u otro. Usar el que EXISTA. Si no existe ningún campo de proyecto en `AgentExecution`, el filtro por proyecto en `_collect_epic_summaries` se omite (devuelve todo sin filtrar) y el test `test_endpoint_echoes_project_filter` verifica que el eco se incluye aunque no haya filtrado real.

**Símbolos exactos:**
- Nueva función helper privada en `agents.py`: `_collect_epic_summaries(project: str | None) -> tuple[list[dict], list[str]]`.
  - Devuelve una tupla `(summaries, runtimes)` donde `summaries` es la lista de `epic_summary` dicts y `runtimes` es la lista paralela de strings de runtime (p. ej. `AgentExecution.agent_type` o el campo `runtime` dentro de `metadata_json`; verificar cuál existe leyendo `models.py:207-280`).
  - Query a `AgentExecution` (importar de `models`): filtrar ejecuciones cuyo `metadata_json` contenga la clave `epic_summary`. Ordenar por `created_at` ASC. Si `project` no es `None` Y existe el campo de proyecto, filtrar por él.
  - Parsear `metadata_json` (es JSON serializado; usar `json.loads` defensivo con try/except → omitir runs con metadata corrupta).
  - Devolver `([summary_dicts], [runtime_strings])` en orden cronológico.
- Nuevo route handler: `grounding_observatory_route()` decorado con el método GET y la ruta resuelta (ver PASO DETERMINÍSTICO).
- Flag: `STACKY_GROUNDING_OBSERVATORY_ENABLED` (bool, **default `True`** — solo-lectura; no cambia nada del flujo de épicas). Registrar en `FLAG_REGISTRY` de `harness_flags.py` con tipo bool, default `True`, y descripción: "Plan 44 F2 — Si ON, expone GET /api/epics/grounding-observatory con métricas agregadas de grounding de épicas (solo-lectura). OFF = el endpoint responde 404/feature-disabled."

> **Verificar el API de flags (decisión fija):** ejecutar `grep -n "def is_enabled\|def get\b" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\harness_flags.py" | head -10`. Si existe `is_enabled(name)` → usarlo. Si no → replicar el patrón `os.getenv("STACKY_...", "true").lower() not in {"0","false","off"}` idéntico al de `tickets.py:5649`. El test mockea el flag por el mismo mecanismo.

**Pseudocódigo del handler:**
```python
@bp.get("/epics/grounding-observatory")   # ajustar según PASO DETERMINÍSTICO
def grounding_observatory_route():
    from services import harness_flags
    if not harness_flags.is_enabled("STACKY_GROUNDING_OBSERVATORY_ENABLED"):
        return jsonify({"error": "feature_disabled"}), 404
    project = (request.args.get("project") or "").strip() or None
    summaries, runtimes = _collect_epic_summaries(project)
    from services.grounding_observatory import aggregate_grounding
    result = aggregate_grounding(summaries, runtimes)
    result["project"] = project          # eco del filtro
    return jsonify(result), 200
```

**Casos borde:** sin ejecuciones de épica → `aggregate_grounding([], [])` → respuesta zeroed (200, no 404). Flag OFF → 404 `feature_disabled`. `project` inexistente → lista vacía → zeroed. Metadata corrupta en una run → se omite esa run, las demás cuentan.

**Tests primero (`test_grounding_observatory_endpoint.py`):**
> Patrón de test: monkeypatchear `_collect_epic_summaries` para devolver `(summaries, runtimes)` y aislar el handler de la DB (test rápido y determinista).
- `test_endpoint_returns_aggregated_metrics` → monkeypatch devuelve `([{...warnings: ["x"], confidence: 0.8}, {...confidence: 0.6}], ["claude_code_cli", "claude_code_cli"])` → 200 con `total_epics==2`, `epics_with_warnings==1`, `avg_confidence==pytest.approx(0.7)`, `runtime_coverage==["claude_code_cli"]`.
- `test_endpoint_404_when_flag_off` → flag OFF → status 404, body `{"error":"feature_disabled"}`.
- `test_endpoint_empty_when_no_epics` → `_collect_epic_summaries` devuelve `([], [])` → 200 con `total_epics==0`, `runtime_coverage==[]`.
- `test_endpoint_echoes_project_filter` → query `?project=RSPACIFICO` → respuesta incluye `"project":"RSPACIFICO"` y `_collect_epic_summaries` fue llamado con `"RSPACIFICO"`.

**Comando de test:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" && .venv\Scripts\python.exe -m pytest tests/test_grounding_observatory_endpoint.py -q
```

**Criterio de aceptación BINARIO:** 4 tests verdes; `test_run_brief_model_override.py` y `test_epic_autopublish_backend.py` sin regresión (correrlos juntos).

**Flag de protección:** `STACKY_GROUNDING_OBSERVATORY_ENABLED`, default `True` (solo-lectura, seguro). Con OFF → 404.

**Impacto por runtime:**
- `claude_code_cli`: sus runs de épica tienen `epic_summary` → cuentan en el observatorio.
- `codex` / `github_copilot`: sus runs hoy no persisten `epic_summary` → `_collect_epic_summaries` no las encuentra → se omiten. `runtime_coverage` mostrará esto explícitamente al operador ([ADICIÓN ARQUITECTO A2]).

**Trabajo del operador:** ninguno.

---

### F3 — Backend: sugeridor pasivo de diccionario de procesos (cierra el loop del Plan 42 F5 sin alucinar)

**Objetivo (1 frase):** listar procesos que el agente NOMBRÓ en épicas publicadas del proyecto pero que NO están en el `process_catalog` del client-profile, para que el operador los agregue con 1 clic.

**Valor:** cierra el loop de adopción del diccionario que el Plan 42 F5 dejó abierto, **sin el riesgo de alucinación de F5** (F5 escaneaba docs e inventaba; F3 solo sugiere nombres que el agente YA escribió en una épica real).

**Archivos a editar/crear:**
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\grounding_observatory.py` (editar — agregar `suggest_process_catalog_entries`).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\agents.py` (editar — agregar endpoint).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\harness_flags.py` (editar — registrar flag).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_process_catalog_suggestions.py` (crear — TDD).

**Símbolos exactos:**
- Nueva función pura en `grounding_observatory.py`: `suggest_process_catalog_entries(summaries: list[dict], existing_catalog: list[dict] | None) -> list[dict]`.
  - `summaries`: igual que F1.
  - `existing_catalog`: el `client_profile["process_catalog"]` actual (lista de `{name, purpose, kind}`) o `None`.
  - Recolecta todos los procesos citados (`cited_modules` que pasan `_is_process`), normaliza el nombre (strip + quitar el prefijo "proceso " case-insensitive para comparar), descarta los que YA están en `existing_catalog` (comparación case-insensitive por nombre normalizado), cuenta frecuencia, y devuelve `[{"name": str, "occurrences": int}, ...]` ordenado por occurrences desc, máx 10. **Nunca inventa:** todo nombre viene de un `cited_modules` real.
- Nueva función helper privada en `agents.py`: `_load_process_catalog(project: str | None) -> list[dict]`.

> **PASO DETERMINÍSTICO — resolver el loader de client-profile:**
> ```
> grep -n "def load_client_profile\|def get_client_profile\|def _load_client\|client_profile" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\context_enrichment.py" | head -20
> ```
> Usar el mismo loader que usa `build_process_dictionary_block` (`context_enrichment.py:597`). Si el loader no es importable directamente, copiar el patrón de lectura (JSON de config del proyecto) que ya existe en ese archivo. Si no se puede resolver → devolver `[]` (degradación explícita: todo proceso citado se sugiere).

- Nuevo route handler: `process_catalog_suggestions_route(project)` GET, ruta `/api/projects/<project>/process-catalog-suggestions`.
- Flag: `STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED` (bool, **default `True`** — solo sugiere, no escribe). Registrar en `FLAG_REGISTRY`.

**Normalización de nombres:**
```python
def _normalize_process_name(citation: str) -> str:
    s = (citation or "").strip()
    low = s.lower()
    if low.startswith("proceso"):
        s = s[len("proceso"):].strip()
    return s

def suggest_process_catalog_entries(summaries, existing_catalog):
    existing = {
        _normalize_process_name(e.get("name", "")).lower()
        for e in (existing_catalog or [])
        if e.get("name")
    }
    counter: Counter = Counter()
    for s in summaries:
        for c in (s.get("cited_modules") or []):
            if not _is_process(c):
                continue
            name = _normalize_process_name(c)
            if not name or name.lower() in existing:
                continue
            counter[name] += 1
    return [{"name": n, "occurrences": cnt}
            for n, cnt in counter.most_common(_MAX_TOP)]
```

**Pseudocódigo del handler:**
```python
@bp.get("/projects/<project>/process-catalog-suggestions")
def process_catalog_suggestions_route(project):
    from services import harness_flags
    if not harness_flags.is_enabled("STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED"):
        return jsonify({"error": "feature_disabled"}), 404
    proj = (project or "").strip() or None
    summaries, _ = _collect_epic_summaries(proj)            # reusa F2
    existing = _load_process_catalog(proj)
    from services.grounding_observatory import suggest_process_catalog_entries
    suggestions = suggest_process_catalog_entries(summaries, existing)
    return jsonify({"project": proj, "suggestions": suggestions}), 200
```

**Casos borde:** sin épicas → `suggestions=[]`. Proceso ya en catálogo → no se sugiere. Profile inexistente → `existing=[]` → todo proceso citado se sugiere (degradación útil, no crash). Comparación case-insensitive: "CargaNomina" en catálogo ⇒ "proceso cargaNomina" citado NO se sugiere.

**Tests primero (`test_process_catalog_suggestions.py`):**
- `test_suggests_uncataloged_process` → summaries citan `"proceso CargaNomina"`, catálogo vacío → suggestions `[{"name":"CargaNomina","occurrences":1}]`.
- `test_excludes_cataloged_process` → cita `"proceso CargaNomina"`, catálogo `[{"name":"CargaNomina",...}]` → suggestions `[]`.
- `test_case_insensitive_dedup` → cita `"proceso cargaNomina"`, catálogo `[{"name":"CargaNomina"}]` → `[]`.
- `test_ignores_modules_only_processes` → cita `"módulo 12"` (no proceso) → no aparece en suggestions.
- `test_counts_occurrences_and_sorts` → 3 épicas citan `"proceso A"`, 1 cita `"proceso B"` → orden `[A(3), B(1)]`.
- `test_endpoint_returns_suggestions` → monkeypatch loaders → 200 con `suggestions` no vacío + `"project"` ecoado.
- `test_endpoint_404_when_flag_off` → flag OFF → 404.

**Comando de test:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" && .venv\Scripts\python.exe -m pytest tests/test_process_catalog_suggestions.py -q
```

**Criterio de aceptación BINARIO:** 7 tests verdes.

**Flag de protección:** `STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED`, default `True` (solo sugiere, no escribe). OFF → 404.

**Impacto por runtime:** idéntico a F2. El sugeridor es agnóstico de runtime.

**Trabajo del operador:** ninguno para ver las sugerencias. Agregar una sugerencia al catálogo es opt-in (F4 expone el botón); aceptar reusa el endpoint de escritura de client-profile del **Plan 45 Req1** (cuando esté activo).

---

### F4 — Frontend: `GroundingObservatoryCard` (tendencia + sugerencias, solo-lectura + 1 clic opt-in)

**Objetivo (1 frase):** mostrar al operador la tendencia de grounding y las sugerencias de diccionario en una card, **en la pestaña de Historial de Runs** (o en una sección de Épicas dedicada — NO en DiagnosticsPage si el Plan 46 ya vive ahí), sin que el operador configure nada.

**Diferenciación de ubicación vs Plan 46:**
- El Plan 46 monta su `OperationalHealthCard` en DiagnosticsPage (o similar) — triage de TODAS las runs.
- Este plan NO duplica esa página. Montar `GroundingObservatoryCard` en la sección/pestaña de **historial de épicas** o como tab del modal de épicas, según lo que exista. **Decisión fija:** grep `HistoryPage\|RunHistoryPage\|EpicFromBriefModal\|DiagnosticsPage` en `frontend/src/pages/` + `frontend/src/components/` para identificar la ubicación real, y elegir la más cercana al flujo de épicas que NO sea la página ya ocupada por el Plan 46.

**Relación con Plan 45 Req1 — botón "Agregar al diccionario":**
- El endpoint de escritura de client-profile es `PUT /api/projects/{project}/client-profile` (creado por **Plan 45 Req1**).
- Si el Plan 45 Req1 está desplegado: el botón "Agregar al diccionario" llama ese endpoint para agregar la entrada al `process_catalog`.
- Si el Plan 45 Req1 NO está desplegado: el botón se renderiza como `disabled` con `title="Requiere Plan 45 Req1 activo para editar el catálogo"`. La card sigue siendo útil mostrando tendencia y sugerencias.
- **No crear un endpoint de escritura de client-profile nuevo aquí.**

**Archivos a editar/crear:**
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\components\GroundingObservatoryCard.tsx` (crear).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\api\endpoints.ts` (editar — agregar 2 métodos GET + verificar si ya existe `updateClientProfile`).
- La página contenedora: **verificar con grep** dónde vive el historial de runs o las épicas; agregar `<GroundingObservatoryCard />` ahí.

> **PASO DETERMINÍSTICO — verificar ubicación de la card:**
> ```
> grep -rn "HarnessHealthCard\|OperationalHealthCard\|RunHistory\|DiagnosticsPage" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src" | head -20
> ```
> Si `DiagnosticsPage` ya tiene `HarnessHealthCard` Y el Plan 46 está activado ahí → elegir otra página (RunHistory, EpicModal, o crear una pestaña nueva bajo el modal de épicas). Si `DiagnosticsPage` tiene espacio sin conflicto con 46 → puede ir ahí.

**Símbolos exactos (endpoints.ts):**
```ts
// dentro del namespace adecuado (p. ej. Agents o un nuevo Grounding):
groundingObservatory: (project?: string) =>
  http.get(`/api/epics/grounding-observatory${project ? `?project=${encodeURIComponent(project)}` : ""}`),
processCatalogSuggestions: (project: string) =>
  http.get(`/api/projects/${encodeURIComponent(project)}/process-catalog-suggestions`),
// Reusar updateClientProfile si ya existe; si no existe, dejarlo pendiente hasta Plan 45 Req1
```
> Usar el cliente HTTP existente (`http`/`api`/`axios` wrapper — verificar el nombre real leyendo las primeras líneas de `endpoints.ts`). El path debe coincidir EXACTO con el resuelto en F2/F3.

**Símbolos exactos (GroundingObservatoryCard.tsx):**
- Componente funcional `GroundingObservatoryCard` que:
  - Usa `useQuery` (react-query, ya usado en el repo) para `groundingObservatory(project)` y `processCatalogSuggestions(project)`.
  - Toma el proyecto activo del mismo hook/contexto que las otras cards (verificar cómo `HarnessHealthCard` obtiene el proyecto; reusar ese mecanismo exacto — grep `useActiveProject\|useProject\|activeProject` en `frontend/src`).
  - Renderiza:
    1. Métricas: `total_epics`, `grounding_warning_rate` (como %), `avg_confidence` (como % o "—" si null).
    2. **`runtime_coverage`**: si contiene solo `["claude_code_cli"]`, mostrar nota `"Codex y Copilot aún sin cobertura"` (hace visible el fallback de §3 principio 1 sin trabajo del operador). Si está vacío, no mostrar nada. ([ADICIÓN ARQUITECTO A2])
    3. `confidence_trend` como un sparkline simple (fila de divs con altura proporcional; NO requiere librería de charts — cero dependencias nuevas).
    4. `top_cited_processes` y `top_cited_modules` como listas con su count.
    5. Sección "Procesos sugeridos para el diccionario": por cada sugerencia, nombre + `occurrences` + botón "Agregar al diccionario" (deshabilitado si Plan 45 Req1 no activo).
  - El botón "Agregar al diccionario" (opt-in, human-in-the-loop): al clickear, abre un pequeño form inline (nombre prellenado, campos `purpose` y `kind` vacíos para que el operador los complete) y al confirmar llama a `PUT /api/projects/{project}/client-profile` (Plan 45 Req1). Si ese endpoint no existe aún, el botón tiene `disabled={true}` y `title="Requiere Plan 45 Req1"`.

**Pseudocódigo (estructura JSX, simplificado):**
```tsx
function GroundingObservatoryCard() {
  const project = useActiveProject();   // mismo mecanismo que HarnessHealthCard
  const obs = useQuery(["grounding-obs", project], () => groundingObservatory(project));
  const sug = useQuery(["catalog-sug", project], () => processCatalogSuggestions(project), {
    enabled: !!project,
  });
  if (obs.isLoading) return <Card title="Observatorio de Grounding">Cargando…</Card>;
  if (obs.isError && obs.error?.status === 404) return null; // feature_disabled
  if (obs.isError) return <Card title="Observatorio de Grounding">No disponible</Card>;
  const d = obs.data;
  const missingRuntimes = !d.runtime_coverage?.includes("codex_cli")
    || !d.runtime_coverage?.includes("github_copilot");
  return (
    <Card title="Observatorio de Grounding de Épicas">
      {d.total_epics === 0 && <p>Aún no hay épicas para analizar.</p>}
      {d.total_epics > 0 && <>
        <Metric label="Épicas" value={d.total_epics} />
        <Metric label="% con warnings" value={pct(d.grounding_warning_rate)} />
        <Metric label="Confianza media" value={d.avg_confidence != null ? pct(d.avg_confidence) : "—"} />
        {missingRuntimes && d.runtime_coverage?.length > 0 && (
          <Note>Cobertura parcial: {d.runtime_coverage.join(", ")} — Codex/Copilot aún sin epic_summary.</Note>
        )}
        <Sparkline values={d.confidence_trend} />
        <TopList title="Procesos más citados" items={d.top_cited_processes} />
        <TopList title="Módulos más citados" items={d.top_cited_modules} />
      </>}
      {sug.data?.suggestions?.length > 0 && (
        <Suggestions items={sug.data.suggestions} project={project} />
      )}
    </Card>
  );
}
```

**Casos borde UI:** `total_epics===0` → "Aún no hay épicas para analizar". `avg_confidence===null` → "—". `confidence_trend` con `null`s → el sparkline dibuja un hueco/barra cero. Endpoint 404 (flag OFF) → `return null` (no ocupa espacio).

**Tests primero:** no hay vitest en el repo. Validar con TypeScript:
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit
```
Y build de producción:
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npm run build
```

**Criterio de aceptación BINARIO:** `tsc --noEmit` 0 errores; `npm run build` 0 errores; la card aparece en la página de historial/épicas correcta y, con datos sembrados, muestra métricas, runtime_coverage y sugerencias.

**Flag de protección:** la card respeta el flag vía el backend (404 → `return null`).

**Impacto por runtime:** la UI es agnóstica; muestra los datos que el backend agrega (hoy `claude_code_cli`). `runtime_coverage` hace visible la situación de Codex/Copilot al operador.

**Trabajo del operador:** ninguno para ver. Opt-in (1 clic + completar `purpose`/`kind`) para adoptar una sugerencia al diccionario, SOLO si Plan 45 Req1 está activo.

---

## 5. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| `cited_modules` no distingue módulos de procesos con el prefijo esperado → clasificación errónea | Media | PASO DETERMINÍSTICO en F1: verificar el formato real ANTES de codear `_is_process`. Si no hay prefijo, todo va a `top_cited_modules` (conservador). Test `test_no_prefix_all_classified_as_module` fija el contrato de degradación. |
| El regex de confidence (F0) no matchea el formato real del agente | Media | Test `test_regex_against_real_html_pattern` verifica contra el texto R-GROUNDING ítem 5 real. Si no matchea → `confidence=None` (idéntico a hoy, sin regresión). |
| El agregado recorre muchas runs y degrada el endpoint | Baja | Lazy (solo al pedir el endpoint). Si crece mucho, agregar `LIMIT` por fecha en iteración futura. |
| El sugeridor propone ruido | Baja | Solo sugiere; human-in-the-loop; ordenado por frecuencia. |
| Falta endpoint de escritura de client-profile | Media | F4 lo trata explícitamente: el botón queda disabled + tooltip hasta que Plan 45 Req1 esté activo. La card sigue siendo útil. |
| Runtimes Codex/Copilot no aparecen | Esperada | `runtime_coverage` lo hace visible al operador directamente en la card ([ADICIÓN A2]). |
| Flags nuevos rompen algo con OFF | Muy baja | Solo-lectura; con OFF cada endpoint responde 404. Regresión cubierta por tests existentes. |
| Fragmentación UI con Plan 46 | Mitigada | Ubicaciones distintas (Plan 46: triage operativo en DiagnosticsPage; Plan 44: calidad de épicas en sección de historial de épicas). PASO DETERMINÍSTICO en F4 resuelve el conflicto antes de codear. |

---

## 6. Fuera de scope

- **Tocar el flujo de generación de épicas** (modal, selector, runner, publicación): es territorio de 42/43.
- **Escritura automática del `process_catalog`** (autonomía): vetado. Solo sugiere.
- **Crear un endpoint de escritura de client-profile** si no existe: fuera de scope (lo crea Plan 45 Req1). El botón se deshabilita hasta entonces.
- **Auto-perfilado escaneando docs** (Plan 42 F5): reemplazado por la vía sin-alucinación.
- **Pre-vuelo de intención** (Plan 41): frente distinto, no se toca.
- **Persistir `epic_summary` en los runners Codex/Copilot:** mejora futura; `runtime_coverage` lo hace visible.
- **Librerías de charts nuevas:** sparkline con divs.
- **RBAC / multiusuario / auth real:** Stacky es mono-operador.
- **Implementación de código:** este documento es solo el plan.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario

- **`epic_summary`:** dict que `build_epic_summary` (`tickets.py:5447`) construye al publicar una épica: `{ado_id, ado_url, rf_count, cited_modules, warnings, confidence}`. Se persiste en `AgentExecution.metadata_json["epic_summary"]`.
- **`grounding_warnings`:** lista de avisos (Plan 42 F2) cuando una épica no cita módulos/procesos fuente.
- **`confidence_grounding`:** métrica `[0,1]` que el BusinessAgent (v1.5.0, R-GROUNDING ítem 5) calcula y escribe en el HTML de la épica; hoy se descarta (F0 la rescata).
- **`process_catalog`:** lista `[{name, purpose, kind}]` del client-profile. La inyecta `build_process_dictionary_block` (`context_enrichment.py:597`).
- **`cited_modules`:** lista de strings de módulos/procesos citados que `build_epic_summary` extrae del HTML.
- **`AgentExecution`:** modelo ORM (`models.py:207`). `metadata_json` (`:219`) guarda telemetría por-run.
- **`autopublish_epic_from_run`:** función (`tickets.py:5602`) que publica la épica en ADO al cerrar la run.
- **`runtime_coverage`:** lista deduplicada de runtimes que contribuyen al observatorio ([ADICIÓN A2]).
- **client-profile:** bloque JSON con identidad del proyecto destino.
- **harness flag:** flag booleano del arnés en `harness_flags.py` (`FLAG_REGISTRY`), con default seguro.

### Orden de implementación (por dependencia)

1. **F0** — Extraer `confidence_grounding` (independiente; habilita la serie de confidence).
2. **F1** — Función pura `aggregate_grounding` con `runtime_coverage` (independiente; núcleo testeable).
3. **F2** — Endpoint del observatorio (depende de F0 y F1).
4. **F3** — Sugeridor de diccionario + endpoint (depende de F1/F2: reusa `_collect_epic_summaries`).
5. **F4** — Frontend `GroundingObservatoryCard` (depende de F2, F3, y Plan 45 Req1 para el botón).

### Prerrequisito para F4 completo

El botón "Agregar al diccionario" requiere **Plan 45 Req1** (endpoint `PUT /api/projects/{project}/client-profile`). F0–F3 no dependen de él. F4 puede implementarse con el botón deshabilitado y activarse cuando Plan 45 Req1 esté desplegado.

### Definición de Hecho (DoD) global

- [ ] `test_epic_confidence_extraction.py`: 9/9 verde (7 originales + 2 de [A1]); `test_epic_autopublish_backend.py` sin regresión.
- [ ] `test_grounding_observatory.py`: 10/10 verde (7 originales + 3 de [A2] + `test_no_prefix_all_classified_as_module`).
- [ ] `test_grounding_observatory_endpoint.py`: 4/4 verde; `test_run_brief_model_override.py` y `test_epic_autopublish_backend.py` sin regresión.
- [ ] `test_process_catalog_suggestions.py`: 7/7 verde.
- [ ] `npx tsc --noEmit` en `frontend/`: 0 errores.
- [ ] `npm run build` en `frontend/`: 0 errores.
- [ ] 2 flags nuevos en `FLAG_REGISTRY`: `STACKY_GROUNDING_OBSERVATORY_ENABLED` (true), `STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED` (true). F0 no requiere flag.
- [ ] Con flags en OFF: ambos endpoints responden 404; la card no se monta; comportamiento idéntico al Plan 43.
- [ ] `epic_summary["confidence"]` trae el float real cuando el agente lo emitió (verificado por `test_autopublish_persists_extracted_confidence`).
- [ ] `aggregate_grounding` devuelve `runtime_coverage` como lista deduplicada de runtimes con datos ([ADICIÓN A2]).
- [ ] El observatorio agrega correctamente warnings, confidence y citas; el sugeridor NUNCA inventa procesos y NUNCA escribe el catálogo solo.
- [ ] Paridad de 3 runtimes documentada: el observatorio refleja runs con `epic_summary` (hoy `claude_code_cli`); Codex/Copilot omitidos con fallback explícito visible en `runtime_coverage` de la card.
- [ ] La card vive en la sección de historial/épicas (NO conflicto con Plan 46 en DiagnosticsPage).
- [ ] El botón "Agregar" está deshabilitado con tooltip si Plan 45 Req1 no está activo; funcional si está activo.
- [ ] Trabajo del operador: ninguno obligatorio; adoptar sugerencia es opt-in con 1 clic.
- [ ] Cero cambios en el flujo de generación de épicas.
- [ ] PASOS DETERMINÍSTICOS ejecutados antes de codear: blueprint prefix, campo de proyecto en AgentExecution, API de flags, loader de client-profile, ubicación de la card.
