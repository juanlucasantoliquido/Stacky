# Plan 42 — Épicas grounded en documentación del proyecto + selector de modelo de Claude CLI

> **Versión: v2 (reescrito tras crítica adversarial)** · Fecha: 2026-06-18 · Estado: PROPUESTO (no implementado)
> Numeración consecutiva calculada listando `Stacky Agents/docs/` (máx previo = 41).
> 
> **CHANGELOG v1→v2:**
> - **C1:** F4 REFORMULADO (no eliminado): el preview/checkbox bloqueante ANTES de publicar viola human-in-the-loop (rechazado en Plan 41: "épica auto-publica sin aprobación, no restaurar checkbox"). Se reemplaza por un "resumen post-épica accionable" solo-lectura que amplifica al operador SIN frenar la auto-publicación. Mantiene las 2 propuestas nuevas pedidas (F4 + F5).
> - **C2:** F0 asigna dueño del diccionario; inyección desde DeployStackyAgents o F5 como prerequisito suave. Sin diccionario, F0 es degradado (transparente en docs).
> - **C3:** F3 frontend detallado: EpicFromBriefModal.tsx, símbolos exactos, pseudocódigo de selects y handlers.
> - **C4:** TDD aclarado: tests de integración débil verifica que el bloque process-catalog se inyecta; limitación documentada (no requiere correr agente completo).
> - **C5:** Paridad runtime: comportamiento si operador cambia runtime POST modelo-selección → limpiar modelo, deshabilitar select.
> - **C6:** R-GROUNDING refinado: búsqueda dirigida en índices, no lectura completa; overhead de tokens controlado.
> - **C7:** F5 auto-perfilado: algoritmo especificado (escaneo determinista de headings, nunca inventa procesos).
> - **C8:** Orden: F5 marcado como "prerequisito suave" para F0 ganar impacto real.
> - **C9:** Combinación de flags documentada (independientes, comportamiento esperado con ambas OFF).
> - **[ADICIÓN ARQUITECTO]:** Guardrail de confidence de grounding: agente calcula métrica y marca alerta `[BAJA CONFIANZA]` si <0.5, reforzando human-in-the-loop sin bloquear.
> - **REUSO (post-crítica):** F3 cap de modelo REUSA `llm_router.clamp_model` (services/llm_router.py:33, ya cubierto por test_llm_router_cap.py y aplicado por el runner CLI) en vez de crear `clamp_brief_model`. Evita reinventar el cap sonnet/nunca-Opus.
> - **(post-crítica) F4:** restaurada como propuesta nueva 1 pero REFORMULADA a "resumen post-épica accionable" solo-lectura (no preview bloqueante), para honrar el pedido de 2 propuestas nuevas sin violar la decisión de auto-publicación del Plan 41.

## 1. Objetivo y KPI

Elevar la **calidad de las épicas** generadas desde brief y cerrar tres agujeros que el operador
detectó en producción:

1. **Épicas con convenciones inventadas.** En la última épica el agente usó términos/convenciones que el
   equipo NO usa, e **infirió mal cuál es el "proceso de carga"** (no sabía para qué sirve cada proceso
   del proyecto destino). El client-profile ya entrega *rutas a índices funcionales*, pero no garantiza
   que el agente los lea, no le da la documentación **técnica** ni un **diccionario de procesos**.
2. **No se puede SELECCIONAR el modelo** de Claude CLI al generar una épica: el backend ya soporta
   `model_override`, pero el frontend nunca lo expone y el backend no tiene cap de modelo (riesgo Opus).
3. **Dos capacidades nuevas** de alto valor que amplifican al operador sin sacarlo del lazo.

**KPI esperado:**
- % de RF de la épica que **citan un módulo/proceso fuente real** de la doc del proyecto: objetivo ≥ 80%
  (hoy 0% garantizado).
- # de épicas que disparan **needs_review por terminología inventada / proceso mal inferido**: objetivo
  reducir a ~0 (medido por el preflight de grounding F2 + el guard existente `_looks_like_epic`).
- # de re-runs por "elegí mal el modelo / esfuerzo": objetivo reducir vía selector explícito (F3).

## 2. Por qué ahora / gap que cierra

- **Plan 39** agregó historial de runs + fix épica CLI + directiva BD read-only en el client-profile.
- **Plan 40** dejó el BusinessAgent v1.2.0→v1.3.0 y la regla **F3 = wiring de `model_override` + `effort`
  high** en `run_brief` (backend) — pero el wiring quedó a medias: el backend lee `body["model"]`, el
  frontend no lo manda.
- **Plan 41** movió la publicación de la épica al backend (`autopublish_epic_from_run`) con guard
  anti-narración `_looks_like_epic` (heading + bloque `RF-XXX`).
- **Gap real que queda:** la épica se publica sola y con formato válido, **pero su contenido puede estar
  desanclado de la realidad del proyecto** (convenciones, procesos). El próximo salto de valor no es de
  plomería sino de **grounding**: obligar al agente a leer la doc técnica + funcional + un diccionario de
  procesos ANTES de generar, igual que ya hace `TechnicalAnalyst.v2.agent.md` (índice maestro técnico →
  tipo de tarea → docs). Y cerrar el wiring del selector de modelo que quedó colgado del Plan 40 F3.

Evidencia (citas confirmadas en código a 2026-06-18):
- `backend/api/agents.py:565` — `run_brief` lee `model_override = (payload.get("model") or "").strip() or None`.
- `backend/api/agents.py:616` — pasa `effort_override="high"` hardcodeado y `model_override` a `run_agent`.
- `frontend/src/components/EpicFromBriefModal.tsx` — envía solo `{brief, runtime, project}`; **no hay
  control de modelo ni effort**.
- `frontend/src/api/endpoints.ts` (~línea 930) — `runBrief` no acepta `model` ni `effort` en su payload.
- `backend/services/context_enrichment.py` — `enrich_blocks()` inyecta client-profile con
  `docs_indexes.functional_online/batch` (rutas), **no** doc técnica ni diccionario de procesos.
- `backend/Stacky/agents/BusinessAgent.agent.md` v1.3.0 — PASO 1 navega índices funcionales; no exige
  leer doc técnica ni cita obligatoria del proceso fuente.
- Referencia conceptual: `backend/Stacky/agents/TechnicalAnalyst.v2.agent.md` — patrón índice maestro
  técnico → tipo de tarea → leer SOLO los docs indicados.

## 3. Principios y guardarraíles (no negociables)

- **Paridad 3 runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Todo cambio de prompt/contexto
  viaja por `enrich_blocks()` (común a los 3) o por el `.agent.md` (común a los 3). El selector de modelo
  degrada por runtime con fallback explícito (ver F3).
- **Cero trabajo extra al operador:** F1/F2 son **automáticos** (el grounding ocurre solo). F3 agrega un
  control opcional con **default seguro** (modelo recomendado preseleccionado; si el operador no toca
  nada, se comporta igual que hoy). F4/F5 son **opt-in, default off**.
- **Human-in-the-loop:** el operador sigue aprobando/viendo todo; ningún ítem introduce autonomía
  proactiva. El grounding amplifica la calidad, no decide por él.
- **Mono-operador sin auth:** nada de RBAC ni multiusuario.
- **No degradar:** todo cambio es backward-compatible y protegido por flag con default seguro. Reusa
  `context_enrichment`, `harness_flags`, el client-profile y el guard `_looks_like_epic` existentes.

## 4. Fases

> Convención de tests: intérprete del repo = `Stacky Agents/backend/.venv/Scripts/python.exe`.
> Correr SIEMPRE por archivo (la full-suite está contaminada). Frontend se valida con
> `node_modules/.bin/tsc --noEmit -p tsconfig.json` (vitest no instalado).

---

### F0 — Diccionario de procesos del proyecto (fuente de verdad del "para qué sirve cada proceso")

**Objetivo (1 frase):** dar al agente un mapa explícito `proceso → propósito` del proyecto destino, para
que NO infiera mal cuál es el "proceso de carga".

**Valor:** ataca directo la causa del bug ("infirió mal cuál es el proceso de carga"); **prerequisito suave para F2** (si el diccionario está vacío, F2 gana menos valor).

**Dueño del diccionario (CRÍTICO — C2):** el `process_catalog` debe venir de una de estas fuentes (por orden de preferencia):
1. **DeployStackyAgents** — parte del client-profile del proyecto, inyectada por el operador/admin al setup de proyecto.
2. **F5 (auto-perfilado)** — generado automáticamente escaneando la doc del proyecto (opt-in flag, prerequisito suave; ver F5).
3. **Manual**: el operador popula manualmente en el client-profile **una sola vez por proyecto**.
Si ninguna fuente proporciona el diccionario, F0 es **degradado pero correcto**: el bloque no se inyecta, la épica se genera igual (backward-compatible).

**Archivos a editar/crear:**
- `Stacky Agents/backend/services/context_enrichment.py` (editar).
- `Stacky Agents/backend/services/harness_flags.py` (editar — registrar flag).
- `Stacky Agents/backend/tests/test_process_dictionary_block.py` (crear — TDD).

**Símbolos exactos:**
- Nueva función pura: `build_process_dictionary_block(client_profile: dict | None) -> dict | None` en
  `context_enrichment.py`.
- Nueva clave del client-profile que se lee: `client_profile["process_catalog"]` — lista de objetos
  `{ "name": str, "purpose": str, "kind": "carga" | "calculo" | "cierre" | "reporte" | "otro" }`.
- Nuevo flag: `STACKY_INJECT_PROCESS_CATALOG` (bool, **default `True`** — es información que solo ayuda;
  si el client-profile no tiene `process_catalog`, la función devuelve `None` y no inyecta nada → no
  degrada). Registrar en `FLAG_REGISTRY` de `harness_flags.py` con tipo bool y default `True`.

**Pseudocódigo:**
```python
def build_process_dictionary_block(client_profile):
    if not client_profile:
        return None
    catalog = client_profile.get("process_catalog") or []
    if not catalog:
        return None  # no hay catálogo → no inyectar (backward-compatible)
    lines = ["DICCIONARIO DE PROCESOS DEL PROYECTO (fuente de verdad — NO inventes nombres ni propósitos):"]
    for p in catalog:
        name = (p.get("name") or "").strip()
        purpose = (p.get("purpose") or "").strip()
        kind = (p.get("kind") or "otro").strip()
        if name and purpose:
            lines.append(f"- {name} [{kind}]: {purpose}")
    if len(lines) == 1:
        return None
    return {"id": "process-catalog", "kind": "process-catalog", "content": "\n".join(lines)}
```
Cablear en `enrich_blocks()` justo DESPUÉS del bloque `client-profile` (respetar el orden de inyección
existente), gated por `STACKY_INJECT_PROCESS_CATALOG`.

**Casos borde:** `client_profile=None`, `process_catalog` ausente, lista vacía, entradas sin `name` o
`purpose` → en todos `None` o se omiten esas entradas; nunca crashea.

**Tests primero (`test_process_dictionary_block.py`):**
- `test_returns_none_when_no_profile` → `build_process_dictionary_block(None) is None`.
- `test_returns_none_when_no_catalog` → profile sin `process_catalog` → `None`.
- `test_builds_block_with_processes` → catálogo de 2 procesos → bloque contiene ambos nombres + propósitos
  + el header "NO inventes".
- `test_skips_incomplete_entries` → entrada sin `purpose` se omite, las completas quedan.
- `test_enrich_blocks_injects_process_catalog_when_flag_on` (monkeypatch flag ON + profile con catálogo)
  → el bloque `process-catalog` aparece en `enrich_blocks()`.
- `test_enrich_blocks_skips_when_flag_off` → flag OFF → no aparece.

**Comando:** `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest tests/test_process_dictionary_block.py -q`

**Criterio binario:** los 6 tests verdes.

**Impacto por runtime:** idéntico en los 3 (viaja por `enrich_blocks`, común). Fallback: sin catálogo,
no inyecta → comportamiento actual.

**Trabajo del operador:** ninguno (si el client-profile ya trae `process_catalog`, se usa; si no, no pasa
nada). Para ganar el valor completo de F2, el operador **debe poblar `process_catalog` una vez por proyecto** (manualmente o via F5 auto-perfilado). Sin diccionario, F0 y F2 no generan alertas (comportamiento existente preservado).

---

### F1 — Inyección de doc TÉCNICA al BusinessAgent (no solo funcional)

**Objetivo (1 frase):** que el BusinessAgent reciba también la ruta del índice **técnico** del proyecto,
para anclar convenciones reales del equipo (hoy solo recibe índices funcionales).

**Valor:** ataca "usó convenciones que el equipo NO usa" — las convenciones viven en la doc técnica.

**Archivos a editar:**
- `Stacky Agents/backend/services/context_enrichment.py` (editar `build_client_profile_block`).
- `Stacky Agents/backend/tests/test_client_profile_tech_index.py` (crear — TDD).

**Símbolos exactos:**
- En `build_client_profile_block`, además de `docs_indexes.functional_online` / `functional_batch`,
  incluir `docs_indexes.technical_master` (la MISMA clave que ya consume `TechnicalAnalyst.v2.agent.md`)
  cuando esté presente en el client-profile.
- Flag de protección: reutilizar el existente `STACKY_INJECT_CLIENT_PROFILE` (ya gobierna este bloque).
  **No** crear flag nuevo (el cambio es aditivo dentro del bloque ya gated).

**Pseudocódigo (diff conceptual dentro del armado del bloque):**
```
docs_indexes = client_profile.get("docs_indexes") or {}
# existente:
#   functional_online = docs_indexes.get("functional_online")
#   functional_batch  = docs_indexes.get("functional_batch")
# AGREGAR:
technical_master = docs_indexes.get("technical_master")
# incluir technical_master en el JSON legible del bloque client-profile SOLO si truthy
```

**Casos borde:** `docs_indexes` ausente, `technical_master` ausente/None/"" → el campo simplemente no se
incluye (backward-compatible; el bloque sigue igual que hoy).

**Tests primero (`test_client_profile_tech_index.py`):**
- `test_block_includes_technical_master_when_present` → profile con `docs_indexes.technical_master` →
  el contenido del bloque client-profile contiene esa ruta.
- `test_block_omits_technical_master_when_absent` → sin `technical_master` → el bloque NO menciona la
  clave (no rompe el formato actual).
- `test_block_still_includes_functional_indexes` → regresión: los índices funcionales siguen presentes.

**Comando:** `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest tests/test_client_profile_tech_index.py -q`

**Criterio binario:** 3 tests verdes + `test_context_db_directive.py` (regresión del bloque) sigue verde.

**Impacto por runtime:** idéntico en los 3 (bloque común). Fallback: sin `technical_master`, igual que hoy.

**Trabajo del operador:** ninguno.

---

### F2 — Contrato de GROUNDING en el BusinessAgent + preflight de grounding (backend) + métrica de confianza

**Objetivo (1 frase):** obligar al agente a LEER la doc (técnica + funcional + diccionario de procesos)
ANTES de generar y a CITAR el módulo/proceso fuente de cada RF; calcular una métrica de confianza de grounding para alertar al operador si es baja.

**Valor:** convierte el grounding de "sugerencia en el prompt" en **contrato verificable** y **señalado**, atacando de
raíz convenciones inventadas y procesos mal inferidos sin bloquear (amplifica human-in-the-loop).

**Archivos a editar/crear:**
- `Stacky Agents/backend/Stacky/agents/BusinessAgent.agent.md` (editar → bump a **v1.4.0**).
- `Stacky Agents/backend/api/tickets.py` (editar — agregar `_epic_grounding_warnings`).
- `Stacky Agents/backend/services/harness_flags.py` (editar — registrar flag).
- `Stacky Agents/backend/tests/test_epic_grounding.py` (crear — TDD).

**Cambios de prompt (BusinessAgent.agent.md → v1.4.0):**
Agregar regla dura **R-GROUNDING** (en el estilo de R-SALIDA / R-BATCH ya presentes):
```
R-GROUNDING (regla dura):
1. ANTES de redactar la épica, leé en este orden: (a) el índice técnico (docs_indexes.technical_master) —
   SOLO el TOC y secciones relevantes al brief; no leas > 20k caracteres, búscalo por palabras clave;
   (b) los índices funcionales relevantes al brief (rutas del client-profile; Plan 40 M1);
   (c) el DICCIONARIO DE PROCESOS (bloque "process-catalog") si está presente.
2. Usá la terminología y las convenciones que aparecen en esa documentación. PROHIBIDO inventar nombres
   de procesos, módulos o convenciones que no figuren en la doc o en el diccionario de procesos.
3. Cuando el brief mencione un "proceso" (carga, cálculo, cierre, reporte), identificá el proceso REAL
   por su propósito en el diccionario de procesos; NO asumas cuál es por el nombre.
4. Por cada RF, en "Relación con funcionalidad existente" CITÁ el módulo o proceso fuente real (ej:
   "módulo NN" o "proceso <nombre>"). Si no encontrás respaldo en la doc, marcá la línea con
   [SUPUESTO: ...] explicando qué asumiste y por qué (el operador lo valida al aprobar).
5. [ADICIÓN ARQUITECTO] Al terminar cada épica, calcula `confidence_grounding = (# módulos citados + # procesos nombrados) / (# RF × 2)` capped a 1.0.
   Si confidence_grounding < 0.5, agrega al bloque visible "Supuestos asumidos":
   `[BAJA CONFIANZA DE GROUNDING — operador, validá que los procesos/módulos nombrados son reales en tu arquitectura]`.
   Esto refuerza human-in-the-loop sin bloquear.
```
(Mantener intactas R-SALIDA y R-BATCH; v1.4.0 solo AGREGA R-GROUNDING con métrica de confianza.)

**Preflight de grounding (backend, suave, no bloqueante):**
- Nueva función pura en `tickets.py`: `_epic_grounding_warnings(html: str | None) -> list[str]`.
  - Si el HTML de la épica NO contiene NINGUNA cita de módulo/proceso (`re.search` de patrones
    `m[oó]dulo`, `proceso`, o `[SUPUESTO`, case-insensitive) → devolver
    `["epic_grounding_low: la épica no cita módulos/procesos fuente ni marca supuestos"]`.
  - Si todo OK → lista vacía.
- En `autopublish_epic_from_run`, DESPUÉS de pasar `_looks_like_epic` y ANTES de publicar: si
  `STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED` está ON y `_epic_grounding_warnings(clean_html)` no está
  vacío → **NO bloquear la publicación** (la épica es válida), pero **adjuntar los warnings a
  `metadata["grounding_warnings"]`** para que el operador los vea. (Human-in-the-loop: avisar, no
  decidir por él.)
- Flag: `STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED` (bool, **default `True`**; es solo telemetría/aviso,
  no cambia el resultado de publicación). Registrar en `FLAG_REGISTRY`.

**Casos borde:** HTML None/"" → `_looks_like_epic` ya lo rechaza antes; `_epic_grounding_warnings("")`
devuelve lista con el warning (defensivo) pero nunca se llega ahí con vacío. Épica con citas → sin
warnings → publica normal.

**Tests primero (`test_epic_grounding.py`):**
- `test_warnings_empty_when_epic_cites_modules` → HTML con "módulo 12" → `[]`.
- `test_warnings_empty_when_epic_marks_assumptions` → HTML con "[SUPUESTO: ...]" → `[]`.
- `test_warnings_present_when_no_grounding` → HTML solo con RF sin citas → lista con `epic_grounding_low`.
- `test_autopublish_attaches_grounding_warnings_not_blocks` → output de épica válida SIN citas + flag ON:
  `autopublish_epic_from_run` igual devuelve `ado_id` (publica) y expone los warnings (verificar vía el
  resultado/metadata, mockeando ADO como en `test_epic_autopublish_backend.py`).
- `test_autopublish_no_warnings_when_flag_off` → flag OFF → no se computan warnings.
- `test_confidence_grounding_marked_in_html` (C4 TDD integración débil) → verifica que un bloque
  `process-catalog` inyectado en `enrich_blocks` aparece en el payload final (sin correr el agente
  completo; solo verificar que `enrich_blocks` + proceso-catalog = output contiene el bloque).

**Comando:** `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest tests/test_epic_grounding.py tests/test_epic_autopublish_backend.py -q`

**Criterio binario:** todos verdes (incluida la regresión de autopublish). Test de integración débil (C4) verifica que el bloque se inyecta; **limitación documentada:** validar que el agente **usó** el diccionario (vs solo leyó) requeriría correr el agente con fixture real de brief+diccionario (out-of-scope TDD sintético; asumir que si el bloque llega al contexto del agente, el prompt de R-GROUNDING lo honorará).

**Impacto por runtime:** R-GROUNDING viaja en el `.agent.md` (común a los 3 runtimes). El preflight es
backend puro (común). Fallback: flag OFF → comportamiento del Plan 41 sin cambios.

**Trabajo del operador:** ninguno obligatorio (los warnings y la alerta de baja confianza aparecen solos en la metadata de la run que ya consulta). **Para ganar valor real:** poblar `process_catalog` en el client-profile (vía F5 auto-perfilado o manualmente).

---

### F3 — Selector de modelo + effort en "Épica desde Brief" (cierra Plan 40 F3) + cap de modelo en backend

**Objetivo (1 frase):** permitir elegir modelo y esfuerzo desde el modal, con default seguro, y blindar
el backend para que NUNCA acepte Opus; **resolver la ambigüedad de C3/C5 con detalles de frontend completos**.

**Valor:** desbloquea el control que el operador pide, elimina el riesgo de costo/Opus accidental, y cierra el gap del Plan 40 F3 frontend.

**Archivos a editar/crear:**
- `Stacky Agents/backend/api/agents.py` (editar `run_brief` — agregar cap/whitelist + leer `effort`).
- `Stacky Agents/backend/services/harness_flags.py` (editar — registrar flag del cap, si aplica).
- `Stacky Agents/backend/tests/test_run_brief_model_override.py` (editar — agregar casos del cap).
- `Stacky Agents/frontend/src/api/endpoints.ts` (editar firma `runBrief`).
- **`Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`** (editar — agregar selects de modelo/esfuerzo; C3 detalles exactos).

**Backend (cap de modelo — hacer PRIMERO, es la parte de seguridad):**
- **REUSO OBLIGATORIO (no reinventar):** ya existe `llm_router.clamp_model(model: str | None) -> str`
  en `Stacky Agents/backend/services/llm_router.py:33`, que CAPA cualquier modelo al máximo permitido
  (sonnet-4-6, nunca Opus/Fable) y ya lo usa el runner CLI (`claude_code_cli_runner.py:650`). Su cap está
  cubierto por `tests/test_llm_router_cap.py` (opus → `_CAP`). **NO crear una función nueva** —
  `run_brief` debe APLICAR `llm_router.clamp_model` al modelo pedido.
- En `run_brief` (api/agents.py): tras leer `requested = (payload.get("model") or "").strip() or None`,
  hacer `model_override = llm_router.clamp_model(requested) if requested else None`. Si `requested` venía
  con Opus/Fable, `clamp_model` lo baja a sonnet-4-6 (seguridad garantizada por el router, no por agents.py).
  Loggear `logger.info("run_brief: modelo solicitado=%s, efectivo=%s", requested, model_override)`.
- Leer effort: `effort = (payload.get("effort") or "").strip().lower()`; si NO está en
  `{"low", "medium", "high"}` → usar default `"high"` (preserva el comportamiento actual). Pasar
  `effort_override=effort` a `run_agent` (en vez del literal `"high"` hardcodeado en agents.py:616).
- Flag opcional `STACKY_BRIEF_MODEL_SELECT_ENABLED` (bool, default `True`) solo para poder apagar la
  feature de extremo a extremo si hiciera falta; el cap de modelo NO depende del flag (la seguridad
  siempre aplica vía `clamp_model`).

**Tests backend primero (editar `test_run_brief_model_override.py`):**
- `test_run_brief_clamps_opus_to_cap` → body `model:"claude-opus-4-7"` → `run_agent` recibe
  `model_override == llm_router._CAP` (NUNCA opus). (Mock de `run_agent`; reusa la constante del router.)
- `test_run_brief_allows_haiku` → body `model:"haiku"` → `run_agent` recibe un modelo permitido (no se
  eleva por encima del cap).
- `test_run_brief_model_none_when_empty` → body sin `model` → `model_override is None` (default del runner).
- `test_run_brief_passes_effort_from_body` → body con `effort:"medium"` → `run_agent` recibe
  `effort_override="medium"` (mock de `run_agent`).
- `test_run_brief_effort_defaults_high` → body sin effort (o effort inválido) → `effort_override="high"`.

**Comando backend:** `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest tests/test_run_brief_model_override.py -q`

**Frontend (`endpoints.ts`):** extender la firma de `runBrief`:
```ts
runBrief: (payload: {
  brief: string;
  runtime?: AgentRuntime;
  project?: string | null;
  vscode_agent_filename?: string;
  model?: string | null;     // NUEVO — opcional
  effort?: "low" | "medium" | "high";  // NUEVO — opcional
}) => ...
```
Incluir `model` y `effort` en el body del POST solo si están definidos (backward-compatible).

**Frontend (`EpicFromBriefModal.tsx`) — DETALLES EXACTOS (C3, C5):**

**Estado React nuevo (añadir a component props/state):**
```tsx
const [selectedModel, setSelectedModel] = useState<string>("sonnet-4-6");
const [selectedEffort, setSelectedEffort] = useState<"low" | "medium" | "high">("high");
```

**Cambios en el JSX** (junto al selector de runtime existente, en el paso "brief"):
```tsx
{/* Modelo (solo para Claude Code CLI) */}
<label htmlFor="model-select">Modelo:</label>
<select
  id="model-select"
  value={selectedModel}
  onChange={(e) => setSelectedModel(e.target.value)}
  disabled={runtime !== "claude_code_cli"}
  title={runtime !== "claude_code_cli" ? "El modelo se elige solo para Claude Code CLI" : ""}
>
  <option value="sonnet-4-6">Recomendado (Sonnet 4.6)</option>
  <option value="haiku">Rápido (Haiku)</option>
</select>

{/* Esfuerzo (todos los runtimes) */}
<label htmlFor="effort-select">Esfuerzo:</label>
<select
  id="effort-select"
  value={selectedEffort}
  onChange={(e) => setSelectedEffort(e.target.value as "low" | "medium" | "high")}
>
  <option value="high">Alto</option>
  <option value="medium">Medio</option>
  <option value="low">Bajo</option>
</select>
```

**En `handleGenerate` (C3):**
```tsx
const payload = {
  brief: briefText,
  runtime,
  project,
  model: runtime === "claude_code_cli" ? selectedModel : undefined,  // envía model SOLO para Claude Code CLI
  effort: selectedEffort,  // siempre se envía
};
await runBrief(payload);
```

**Comportamiento si operador cambia runtime DESPUÉS de elegir modelo (C5):**
Si `runtime` cambia a no-`claude_code_cli` y el usuario ya había seleccionado modelo:
```tsx
useEffect(() => {
  if (runtime !== "claude_code_cli" && selectedModel !== "sonnet-4-6") {
    setSelectedModel("sonnet-4-6");  // resetea al default
  }
}, [runtime]);
```
Esto evita que el modal mande un modelo irrelevante a un runtime que no lo entiende.

**Criterio binario frontend:** 
- `npm run build` en `frontend/` → 0 errores TypeScript.
- Selector de modelo **deshabilitado** cuando runtime no es `claude_code_cli` (verificable visualmente o por e2e).

**Impacto por runtime:**
- Claude Code CLI: el modelo seleccionado se aplica (capped a sonnet/haiku en backend).
- Codex CLI / GitHub Copilot Pro: ignoran `model` (no aplica el concepto de modelo Anthropic); el select
  queda deshabilitado en la UI → fallback explícito, sin error. `effort` sí aplica a todos donde el
  runner lo soporte; donde no, se ignora silenciosamente (backward-compatible).

**Trabajo del operador:** ninguno obligatorio (default preseleccionado = comportamiento actual). Control opcional disponible.

---

### F4 — PROPUESTA NUEVA 1 (reformulada por C1): "Resumen post-épica accionable" (NO preview bloqueante)

> **Nivel de audacia: MEDIO-BAJO.** **Supuesto a stress-testear:** que el operador, al NO querer un paso
> de aprobación previo (la épica auto-publica por decisión firme), igual valora un **resumen post-hoc** de
> qué se publicó y con qué nivel de confianza, para auditar rápido SIN frenar el flujo.

**Por qué NO un preview bloqueante (C1):** la propuesta original (preview/edición ANTES de publicar) está
**vetada**: reintroduciría el checkbox que el operador rechazó explícitamente en Plan 41
(`human-in-the-loop-fundamental`: _"épica-desde-brief AUTO-PUBLICA sin aprobación; NO restaurar el
checkbox"_). Cualquier preview obligatorio sería RECHAZADO. Por eso esta propuesta amplifica al operador
**después** de la publicación (solo-lectura), nunca frenándola.

**Objetivo (1 frase):** al cerrar una run de épica, adjuntar a la metadata (que el operador ya ve en el
historial del Plan 39) un **resumen accionable**: link ADO de la épica, # de RF, lista de
módulos/procesos citados, `grounding_warnings` (F2) y `confidence_grounding` (F2 ADICIÓN ARQUITECTO).

**Valor:** auditoría de 5 segundos sin abrir ADO; el operador detecta una épica débil y decide re-correr,
sin haber tenido que aprobar nada por adelantado. Reusa el historial existente y los campos de F2.

**Archivos a editar/crear (cuando se implemente):**
- `Stacky Agents/backend/api/tickets.py` (editar — en `autopublish_epic_from_run`, ensamblar el dict
  `epic_summary` y dejarlo en `metadata["epic_summary"]`).
- `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx` (editar — render del resumen si existe).
- `Stacky Agents/backend/tests/test_epic_summary.py` (crear — TDD).

**Símbolos exactos:**
- Nueva función pura: `build_epic_summary(*, ado_id: int | None, clean_html: str, warnings: list[str], confidence: float | None) -> dict` en `tickets.py`.
  - Devuelve `{"ado_id", "ado_url", "rf_count", "cited_modules": [...], "warnings": [...], "confidence": float|None}`.
  - `rf_count` = `len(re.findall(r"<h2[^>]*>\s*RF-", clean_html, re.I))`; `cited_modules` = matches de
    `m[oó]dulo\s+\S+` y `proceso\s+\S+` deduplicados.
- Flag: `STACKY_EPIC_SUMMARY_ENABLED` (bool, **default `True`** — es solo-lectura, no cambia publicación).

**Tests primero (`test_epic_summary.py`):**
- `test_summary_counts_rf` → HTML con 3 bloques RF → `rf_count == 3`.
- `test_summary_extracts_cited_modules` → HTML con "módulo 12" y "proceso CargaNomina" → ambos en `cited_modules`.
- `test_summary_carries_warnings_and_confidence` → warnings + confidence se reflejan tal cual.
- `test_autopublish_attaches_epic_summary_when_flag_on` → autopublish (mock ADO) deja `metadata["epic_summary"]` con `ado_id`.
- `test_autopublish_no_summary_when_flag_off` → flag OFF → sin `epic_summary`.

**Comando:** `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest tests/test_epic_summary.py -q`

**Criterio binario:** 5 tests verdes + `tsc --noEmit` 0 errores.

**Impacto por runtime:** backend común a los 3; UI común. Fallback: flag OFF → comportamiento Plan 41.

**Trabajo del operador:** ninguno (el resumen aparece solo en el historial que ya consulta). Human-in-the-loop:
amplifica (auditoría post-hoc), NO bloquea ni reintroduce aprobación previa.

---

### F5 — "Auto-perfilado del proyecto" (semilla del client-profile desde la doc del repo) — PREREQUISITO SUAVE DE F0/F2

> **Nivel de audacia: ALTO.** **Supuesto a stress-testear:** que se puede DERIVAR de forma confiable
> `docs_indexes` (technical_master / functional_*) y un borrador de `process_catalog` escaneando la
> estructura de carpetas de documentación del proyecto destino (p. ej. `docs/tecnica`, `docs/funcional`),
> sin alucinar procesos. Si el escaneo produce falsos procesos, contamina el grounding de F0/F2 → debe ser
> opt-in, generar SOLO un BORRADOR que el operador revisa, y nunca sobreescribir un client-profile existente.
> **Marcado como "prerequisito suave" (C8):** sin F5, el diccionario de procesos está vacío y F0/F2 no generan alertas (regresión permisible). Con F5 habilitado, el ciclo de adopción cierra automático.**

**Objetivo (1 frase):** un comando/endpoint opt-in que, dado el root de docs de un proyecto, **propone un
borrador** de `docs_indexes` y `process_catalog` para el client-profile, que el operador revisa y acepta.

**Valor:** elimina el único trabajo de configuración que F0/F1 podrían requerir (poblar `process_catalog`
y `docs_indexes`), cerrando el loop "cero trabajo extra al operador" a nivel de adopción. Convierte F0/F2
de "mejora si el operador configura" en "mejora casi automática".

**Guardarraíles duros:** genera SOLO un borrador (`*.draft.json`); NO escribe el client-profile vivo; el
operador acepta explícitamente (human-in-the-loop). **Escaneo DETERMINISTA** (C7: listar archivos/headings, NO
pedirle al LLM que invente nombres de procesos: los nombres salen de los títulos reales de la doc).

**Algoritmo de escaneo (C7 — DETALLES EXACTOS):**
```
1. Listar directorios bajo docs_root → buscar "tecnica", "técnica", "technical", etc.
   Para cada encontrado: docs_indexes.technical_master = "<ruta>/index.md" o "<ruta>/README.md" (si existe).
2. Análogo para "funcional", "functional", etc. → docs_indexes.functional_online, docs_indexes.functional_batch.
3. process_catalog: para cada .md bajo "tecnica" (o top-level si existe), extrae headings nivel 2-3.
   Si el heading matchea regex `(?i)(process|proceso|job|batch|tarea)`:
   - Nombre del proceso = el heading text limpio (sin ```markdown).
   - Propósito = la descripción en las próximas líneas (hasta el siguiente heading o 100 caracteres).
   - Kind = inferido del contexto del heading ("carga", "cálculo", "cierre", "reporte") o "otro" si no es claro.
4. NUNCA inventa un nombre: solo cita lo que está en los archivos de doc reales.
```

**Archivos (cuando se implemente):** 
- `backend/services/project_autoprofile.py` (nuevo, función pura `draft_profile_from_docs(docs_root: Path) -> dict`).
- `backend/api/agents.py` — endpoint GET `/api/projects/{project}/autoprofile` (GET, no POST; devuelve draft).
- Flag `STACKY_PROJECT_AUTOPROFILE_ENABLED` (default `False`).
- Tests `test_project_autoprofile.py` (usar un árbol de docs **fixture en `tests/`**, NO el repo real).

**Tests clave:** 
- `test_draft_finds_technical_index` — árbol fixture con `docs/tecnica/index.md` → draft contiene esa ruta.
- `test_draft_extracts_processes_from_headings` — `docs/tecnica/batch.md` con heading `## Facturación Nocturna` → `process_catalog` contiene `{name: "Facturación Nocturna", ...}`.
- `test_draft_never_invents_process` — árbol vacío → `process_catalog` = `[]` (nunca alucina procesos).
- `test_draft_respects_existing_profile` — si client-profile EXISTE, NO lo sobrescribe; solo propone diff.

**Impacto por runtime:** backend puro (independiente del runtime). Fallback: flag OFF = no existe.

**Trabajo del operador:** opt-in (default off); si lo usa, revisa un borrador en el endpoint + 1 clic de "Aceptar" → se guarda en el client-profile vivo.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El diccionario de procesos del client-profile está mal/incompleto → grounding pobre | F0 omite entradas incompletas; F2 solo AVISA (no bloquea, confidence <0.5 → [BAJA CONFIANZA]); F5 ayuda a poblarlo bien |
| R-GROUNDING hace al agente leer demasiada doc → más tokens/latencia | C6: El prompt limita "leé SOLO los módulos relacionados por palabras clave" (igual que TechnicalAnalyst.v2); effort sigue configurable (F3) |
| Preflight de grounding genera falsos "low" en épicas válidas (alertas innecesarias) | Es suave (solo alerta [BAJA CONFIANZA] en metadata, no bloquea); flag default ON pero apagable; TDD sintético verifica que el bloque se inyecta |
| Cap de modelo rompe un caso legítimo que usaba un id no listado | Whitelist incluye ids cortos y completos de haiku/sonnet-4-6; fuera de eso cae al default seguro (no falla, degrada) |
| Selector de modelo confunde/bloquea en runtimes no-Anthropic (C5) | Select deshabilitado + resetea modelo al default si runtime cambia POST selección |
| F5 alucina procesos (C7) | Escaneo determinista (títulos reales extraídos de .md, nunca inventa); solo borrador, no escribe perfil vivo, opt-in default off |
| Preview bloqueante ANTES de publicar viola human-in-the-loop (C1) | F4 REFORMULADO a resumen post-épica solo-lectura (amplifica sin frenar). Preview obligatorio queda vetado: si evidencia futura lo exige, es Plan 43. |
| Diccionario vacío → F0/F2 sin impacto (C2) | Documentado y transparente: con diccionario vacío, el bloque no se inyecta; con F5 poblado, impacto real. **Prerequisito suave** (opcional para operador). |
| Interacción de flags F2+F3 sin documentación (C9) | Flags independientes; comportamiento esperado documentado en "Riesgos". |

## 6. Fuera de scope

- RBAC / multiusuario / auth real (Stacky es mono-operador).
- Autonomía proactiva que saque al operador del lazo (M6 del Plan 40 preservado; pre-vuelo Plan 41 amplifica, no reemplaza).
- Soporte de Opus/Fable como modelo de brief (explícitamente vetado por el cap F3).
- Re-arquitectura de `enrich_blocks` o del runner; solo cambios aditivos.
- **Preview obligatorio / checkbox de aprobación ANTES de publicar:** vetado (Plan 41); requiere Plan 43 con evidencia de daño de auto-publish. (F4 de este plan es post-hoc solo-lectura, NO un preview bloqueante.)
- Implementación de código (este documento es solo el plan).

## 7. Glosario, Orden de implementación y DoD

### Glosario (términos del dominio Stacky)
- **client-profile:** bloque JSON con la identidad del proyecto destino (terminología, `docs_indexes`,
  `database`, etc.) que `context_enrichment` inyecta a TODOS los runtimes.
- **docs_indexes:** rutas a los índices de documentación del proyecto: `technical_master` (índice maestro
  técnico), `functional_online`, `functional_batch`.
- **process_catalog:** (nuevo, F0) lista `proceso → propósito → tipo` del proyecto destino.
- **enrich_blocks():** pipeline común a los 3 runtimes que arma los bloques de contexto inyectados al
  agente (`backend/services/context_enrichment.py`).
- **run_brief:** endpoint/función backend que dispara la generación de épica desde un brief
  (`backend/api/agents.py`).
- **autopublish_epic_from_run:** función backend (Plan 41) que publica la épica en ADO al cerrar la run.
- **`_looks_like_epic`:** guard anti-narración (heading + bloque `RF-XXX`) ya existente.
- **effort_override:** nivel de esfuerzo del runner (low/medium/high).
- **harness flag:** flag booleano del arnés en `harness_flags.py` (`FLAG_REGISTRY`), con default seguro.
- **R-SALIDA / R-BATCH / R-GROUNDING:** reglas duras del `BusinessAgent.agent.md`.

### Orden de implementación (por dependencia)
1. **F3 backend** (aplicar `llm_router.clamp_model` en run_brief + effort + tests) — seguridad primero, reusa el cap existente, independiente.
2. **F0** (diccionario de procesos) — base del grounding; prerequisito suave (sin diccionario, impacto reducido).
3. **F1** (índice técnico al client-profile) — aditivo, independiente.
4. **F2** (R-GROUNDING v1.4.0 + preflight + confidence) — depende de F0/F1 para tener qué citar; incluye [ADICIÓN ARQUITECTO] guardrail de confianza.
5. **F3 frontend** (endpoints.ts + EpicFromBriefModal con detalles C3/C5) — depende de F3 backend; cierra Plan 40 F3.
6. **F4** (resumen post-épica accionable, solo-lectura) — depende de F2 (usa warnings + confidence); propuesta nueva 1.
7. **F5** (auto-perfilado, opt-in, prerequisito suave de F0/F2) — cierra el loop de adopción sin trabajo obligatorio al operador; propuesta nueva 2; implementar después de F0-F3 pero antes de producción si se quiere impacto real del grounding.

### Definición de Hecho (DoD) global
- [ ] Todos los tests nuevos/editados verdes corriendo por archivo con el python del `.venv`.
- [ ] `npm run build` del frontend en 0 errores TypeScript.
- [ ] Cada feature protegida por su flag con default seguro; con flags OFF el sistema se comporta
      EXACTAMENTE como el Plan 40/41 (backward-compatible verificado por regresión de tests existentes).
- [ ] BusinessAgent.agent.md en v1.4.0 con R-GROUNDING (incluyendo métrica de confidence [ADICIÓN ARQUITECTO]); R-SALIDA y R-BATCH intactas.
- [ ] El backend NUNCA envía Opus al runner de brief (verificado por test); reusa `llm_router.clamp_model` (no función nueva).
- [ ] Frontend EpicFromBriefModal: selects de modelo/esfuerzo con handlers, reset de modelo si runtime cambia (C3/C5).
- [ ] F5 auto-perfilado: algoritmo determinista especificado (C7), nunca alucina procesos.
- [ ] Paridad de 3 runtimes documentada por ítem con fallback explícito.
- [ ] Diccionario de procesos: dueño asignado (DeployStackyAgents o F5) con degradación transparente (C2).
- [ ] Confidence de grounding: alerta [BAJA CONFIANZA] cuando <0.5, refuerza human-in-the-loop sin bloquear (ADICIÓN ARQUITECTO).
- [ ] F4 reformulado a resumen post-épica solo-lectura (C1): amplifica al operador SIN preview bloqueante; preview obligatorio sigue vetado.
- [ ] Las 2 propuestas nuevas presentes y viables: F4 (resumen post-épica) y F5 (auto-perfilado), cada una con nivel de audacia + supuesto a stress-testear.
- [ ] Trabajo del operador: ninguno obligatorio (F0-F4 default seguro; F5 opt-in default off, prerequisito suave).
