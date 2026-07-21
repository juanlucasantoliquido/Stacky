# Plan 209 — Guía de validación al usuario al completar una task ("Cómo validar esto")

Estado: PROPUESTO v1 (2026-07-20)
Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8)
Plan hermano en paralelo: **208** (auto-sync ADO + matriz de estados por tipo de ticket x agente). Se cita donde toca; 209 NO depende de 208.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Cuando un agente termina de atender una task, su entregable debe incluir, de forma automática, una sección **"Cómo validar esto (como usuario del sistema RS)"**: pasos concretos de UI/negocio del **producto RS del cliente** (OnLine/WebForms, Batch, su BD) que un usuario **novato** puede seguir para comprobar el desarrollo **sin depender de un experto** (ej.: "cómo entrar al detalle del cliente", "cómo asignar una obligación y que aparezca en la pantalla de inicio", como pregunta Esther). La sección es **texto** dentro del entregable: no ejecuta nada en RS, no toca Azure DevOps y no reemplaza al operador. Su valor central es **onboarding y autonomía** de gente que apenas está aprendiendo RS. Como enseñar un paso inventado es **peor** que no dar ninguno, la sección está **anclada (grounded)** en documentación real del cliente (bloque `func-docs` que el agente ya recibe, y/o `process_catalog` del perfil del cliente) y **cita su fuente**; si no hay evidencia suficiente, **degrada honestamente** en vez de inventar. El diseño es **híbrido**: enfoque A (el agente lo escribe, porque es quien tiene el contexto exacto) + enfoque B (relleno determinista por RAG local cuando A falta o queda pobre), con un **gate anti-alucinación** que verifica presencia + grounding.

**KPIs / impacto (binarios y medibles):**
- **KPI-1 Cobertura grounded:** ≥ 90% de los deliverables de tasks completadas por agentes user-facing tienen `execution.metadata.validation_playbook.status` ∈ {`agent_provided`, `enriched`} (es decir, sección presente **con ≥1 cita real**). Medible contando ese campo en logs/KPIs.
- **KPI-2 Cero pasos inventados:** en producción, el contador de logs `validation_playbook.ungrounded_step` = 0 y el sentinel de anti-alucinación (F5) queda verde. Todo paso o tiene fuente o no existe.
- **KPI-3 Autonomía (norte del operador):** baja la cantidad de preguntas tipo "¿cómo valido / cómo hago X en RS?" de novatos hacia expertos. Proxy medible: cantidad de ejecuciones cuyo pane "Cómo validar" se renderiza con status distinto de `disabled`.
- **KPI-4 Paridad 3 runtimes:** para Codex CLI, Claude Code CLI y Copilot Pro, la distribución de `status` muestra sección presente (por A o por B) en los tres; ningún runtime queda en `disabled` salvo flag OFF.

---

## 2. Por qué ahora / gap (anclado en código real)

Hoy el ciclo produce un entregable **técnicamente correcto** pero **mudo para el usuario de negocio**:

- El agente escribe su salida (HTML) en `Agentes/outputs/<ADO_ID>/comment.html` y Stacky la valida y publica. El validador `services/agent_html_output.py::read_and_validate` (`agent_html_output.py:123`) sólo chequea invariantes técnicas (NOT_FOUND, TOO_LARGE, EMPTY, SECRET_DETECTED, PATH_ESCAPE, INVALID_PATH); **nada** exige una guía de validación para el usuario. El gateway de completación `services/agent_completion.py::_validate_html` (`agent_completion.py:326`) usa ese mismo validador. → **Gap 1: el contrato de salida no pide pasos de validación de negocio.**
- El `system_prompt` de los agentes ya pide rigor de trazabilidad ("citás explícitamente los documentos consultados", `agents/functional.py:24`) y el agente **ya recibe la documentación funcional del producto**: `FunctionalAgent.default_blocks = ["ticket-meta", "epic-description", "func-docs"]` (`agents/functional.py:16`). Es decir, el contexto para redactar pasos correctos **ya está en la mano del agente**, pero **no se le pide** que lo convierta en una guía para el usuario. → **Gap 2: desperdiciamos contexto que ya pagamos.**
- Ya existe infraestructura de **grounding anti-alucinación** que podemos reutilizar en vez de inventar: `api/tickets.py::catalog_unknown_processes` (`tickets.py:6241`, PURA, NO-OP sin evidencia, "nunca inventa reemplazos") y `_catalog_grounding_warnings` (`tickets.py:6260`, degradación honesta: "no opina sin fuente de verdad"), gobernadas por `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` (default ON, `tickets.py:6235`). El catálogo sale de `profile.get("process_catalog")` (`tickets.py:6669`). También existe la convención de confianza `_extract_confidence_from_html` + `confidence_grounding = N` + marcador `[BAJA CONFIANZA]` (`tickets.py:6283`). → **Gap 3: la maquinaria anti-alucinación existe pero no cubre la guía al usuario.**
- Ya existe **retrieval local** reutilizable: `services/rag_retriever.py::retrieve` (`rag_retriever.py:75`) + `chunks_from_process_catalog` (`rag_retriever.py:94`), y el **DocConsultor vivo** `services/docs_rag.py::search(project_name, query, top_k)` (`docs_rag.py:265`) que indexa los `.md` funcionales del cliente. → **Gap 4: tenemos con qué armar el relleno B sin montar nada nuevo ni gastar LLM extra.**
- El deliverable se renderiza al operador en `frontend/src/components/OutputPanel.tsx` vía `<StructuredOutput output=... agentType=... />` (`OutputPanel.tsx:140`). Hay lugar natural para un pane distinguible. → **Gap 5: falta una vista novato-friendly.**

**Conclusión:** el contexto, el retrieval, el anti-alucinación y el punto de render **ya existen**. Falta **cablearlos** en una sección de validación al usuario. Bajo costo, alto valor de onboarding.

---

## 3. Principios y guardarraíles

1. **Anti-alucinación innegociable.** Ningún paso sin fuente citada. Sin evidencia → **degradación honesta** (mensaje fijo), nunca invención. Cableado con gate (F2) + sentinel (F5).
2. **Híbrido A + B con un único objeto canónico.** Una sola estructura `ValidationPlaybook` con dos productores (A: parseado del HTML del agente; B: construido por RAG) y **un solo renderer** → ADO y UI muestran exactamente lo mismo, venga de donde venga.
3. **Cero trabajo al operador.** Flag `STACKY_VALIDATION_PLAYBOOK_ENABLED` **default ON**. La guía se anexa sola. No dispara ninguna de las 4 excepciones duras (ver §5): es **texto**, no acción externa, no bypass de revisión, no destructivo, no baja seguridad y **no exige prerequisito nuevo** (si falta grounding, degrada; no rompe).
4. **Human-in-the-loop.** La guía **amplifica** al novato; el operador sigue siendo quien valida y aprueba. No auto-ejecuta nada en RS ni en ADO.
5. **No romper el contrato ADO.** Los agentes **no** tocan ADO (`agents/functional.py:25-27`); la guía es contenido del deliverable, no una acción.
6. **Paridad de 3 runtimes.** A = instrucción de prompt (la siguen Codex/Claude/Copilot por igual). B + gate = Python runtime-agnóstico. Si un runtime omite A, B rellena; si no hay grounding, degrada. Nada atado a un runtime.
7. **No degradar performance/estabilidad/seguridad/DX.** A no agrega llamadas LLM (es parte de la salida que el agente ya produce). B es retrieval **local** (TF-IDF, sin red, sin LLM). Backward-compatible: flag OFF o sin grounding → el deliverable queda como hoy. Reusar `agent_html_output`, `rag_retriever`, `docs_rag`, la maquinaria de grounding y el registry de flags existentes.
8. **Mono-operador sin auth.** Nada de RBAC/multiusuario.
9. **No bloquear el cierre.** El gate es **advisory** (como `_catalog_grounding_warnings`): emite warnings + métricas, nunca frena la completación ni la publicación.

---

## 4. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5**. Cada fase es autocontenida y verificable sola.

Convención de comando de test (venv del repo, **por archivo** por contaminación cross-file conocida):
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan209_XXX.py -q
```
Frontend (vitest **por archivo**):
```
cd "Stacky Agents/frontend" && npx vitest run src/components/__tests__/ValidationPlaybookPane.test.tsx
```
**Regla dura de ratchet:** cada `test_plan209_*.py` nuevo debe registrarse en `HARNESS_TEST_FILES` (archivos `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1`), o el meta-test `tests/test_harness_ratchet_meta.py` queda rojo.

---

### F0 — Flag + schema del objeto `ValidationPlaybook`

**Objetivo (1 frase).** Crear el flag `STACKY_VALIDATION_PLAYBOOK_ENABLED` (default ON) y la estructura de datos + constantes que todas las fases comparten. **Valor:** contrato único, sin ambigüedad para el resto.

**Archivos a crear/editar:**
- CREAR `backend/services/validation_playbook.py` (sólo schema + constantes en F0; lógica en F2/F3).
- EDITAR `backend/services/harness_flags.py` (FlagSpec + `_CATEGORY_KEYS`).
- EDITAR `backend/config.py` (atributo Config, espejo del default).
- EDITAR `backend/tests/test_harness_flags.py` (agregar la key a `_CURATED_DEFAULTS_ON`, línea 467).
- CREAR `backend/tests/test_plan209_playbook_schema.py`.
- CREAR `backend/tests/test_plan209_flag.py`.
- EDITAR `backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1` (registrar los 2 tests nuevos).

**Nombres exactos:**
- Flag key: `STACKY_VALIDATION_PLAYBOOK_ENABLED` (bool, default `True`, group `"global"`, categoría `calidad_verificacion`, `requires=None`).
- Dataclass `ValidationStep(n: int, action: str, expected_result: str, source: str)` — `source` es la referencia de la fuente citada (ej. `"func-docs:alta-cliente"` o `"catalog:IncHost"`). **`source` vacío es inválido** (lo garantiza F5).
- Dataclass `ValidationPlaybook(status: str, steps: list[ValidationStep], sources: list[str], confidence: float, degraded_reason: str | None)`.
  - `status` ∈ `{"agent_provided", "enriched", "degraded", "disabled"}`.
  - `to_dict()` / `from_dict(d)` para serializar a `execution.metadata`.
- Constantes de módulo:
  - `SECTION_TITLE = "Cómo validar esto (como usuario del sistema RS)"`
  - `DEGRADED_MESSAGE = "Estos pasos no pudieron verificarse contra la documentacion del producto. Confirma con un referente de RS antes de usarlos."`
  - `SECTION_MARKER = 'data-stacky="validation-playbook"'` (marca para parseo A e idempotencia de append).
  - `MARKER_COMMENT = "<!-- stacky:validation-playbook v1 -->"` (centinela de idempotencia para no anexar dos veces).
- Helper `flag_enabled() -> bool`: lee `config.config.STACKY_VALIDATION_PLAYBOOK_ENABLED` con fallback a `os.getenv(..., "true")`. Usar **`config.config`** (la instancia), no el módulo (gotcha conocido: el módulo devuelve el default y mata el branch OFF).

**Diff ilustrativo `harness_flags.py`** (agregar al tuple `FLAG_REGISTRY`; el nombre del tuple ya existe en el módulo):
```python
FlagSpec(
    key="STACKY_VALIDATION_PLAYBOOK_ENABLED",
    type="bool",
    label="Guia 'Como validar' en el entregable",
    description="Anexa al deliverable pasos de validacion para el usuario de RS, "
                "grounded en docs del cliente; degrada honestamente si no hay evidencia.",
    group="global",
    default=True,
),
```
Y en `_CATEGORY_KEYS["calidad_verificacion"]` agregar `"STACKY_VALIDATION_PLAYBOOK_ENABLED",`.

**Diff ilustrativo `config.py`** (patrón idéntico a `config.py:1382`):
```python
# ── Plan 209 — Guia de validacion al usuario ──────────────────────────────
# Anexa la seccion "Como validar" al deliverable, grounded en docs del cliente.
# Texto, sin red, sin LLM extra. Default ON (espejo del default=True de la
# FlagSpec homonima; curada en _CURATED_DEFAULTS_ON). Editable por UI.
STACKY_VALIDATION_PLAYBOOK_ENABLED: bool = os.getenv(
    "STACKY_VALIDATION_PLAYBOOK_ENABLED", "true"
).strip().lower() in ("1", "true", "yes")
```

**Casos borde:** flag OFF → `flag_enabled()` False (todas las fases quedan NO-OP). Config sin el atributo (deploy viejo) → fallback a env "true".

**Tests primero (`test_plan209_playbook_schema.py`):**
- `test_playbook_roundtrip`: `ValidationPlaybook(...).to_dict()` → `from_dict(...)` reconstruye igual.
- `test_status_values`: sólo se aceptan los 4 status; otro valor lanza `ValueError`.
- `test_degraded_message_constante`: `DEGRADED_MESSAGE` contiene "referente" y NO contiene dígitos de pasos.
- `test_step_source_required`: `ValidationStep` con `source=""` es rechazado por el validador de F5 (import del check).

**Tests primero (`test_plan209_flag.py`):**
- `test_flag_registrada`: la key aparece en `FLAG_REGISTRY` y en `_CATEGORY_KEYS["calidad_verificacion"]`.
- `test_flag_default_on`: `flag_enabled()` True con env sin setear; False con `STACKY_VALIDATION_PLAYBOOK_ENABLED=false`.
- `test_flag_en_curated`: `"STACKY_VALIDATION_PLAYBOOK_ENABLED" in _CURATED_DEFAULTS_ON`.

**Criterio de aceptación binario + comando:**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan209_playbook_schema.py tests/test_plan209_flag.py tests/test_harness_flags.py -q
```
Verde = F0 hecho. (Se incluye `test_harness_flags.py` porque el cambio en `_CURATED_DEFAULTS_ON` lo afecta.)

**Flag que la protege + default:** `STACKY_VALIDATION_PLAYBOOK_ENABLED`, default **ON**. Justificación del ON: la guía es texto en un deliverable que el agente ya produce; no agrega costo de tokens (A) ni llamadas de red/LLM (B es TF-IDF local); si falta grounding, degrada (no rompe). No cae en ninguna excepción dura de "flags que quemen tokens ociosos".

**Impacto por runtime:** ninguno en F0 (sólo schema/flag). **Trabajo del operador: ninguno.**

---

### F1 — Enfoque A: extender el contrato de salida (system_prompt compartido)

**Objetivo (1 frase).** Instruir a **todos** los agentes, de forma uniforme y gateada por flag, a incluir en su entregable la sección "Cómo validar" con pasos de UI de RS **citando** los docs/catálogo que ya reciben. **Valor:** el productor primario es el agente, que tiene el contexto exacto; costo cero de tokens extra.

**Archivos a crear/editar:**
- EDITAR `backend/agents/base.py` (`compose_system_prompt`, `base.py:56`).
- EDITAR `backend/services/validation_playbook.py` (agregar la constante de instrucción).
- CREAR `backend/tests/test_plan209_prompt_contract.py`.
- EDITAR `run_harness_tests.sh` / `.ps1` (registrar el test).

**Nombres exactos:**
- Constante `VALIDATION_PLAYBOOK_INSTRUCTION` en `services/validation_playbook.py` (texto español, ver abajo).
- Función `validation_prompt_block() -> str`: devuelve `VALIDATION_PLAYBOOK_INSTRUCTION` si `flag_enabled()`, si no `""`.

**Texto EXACTO de la instrucción (`VALIDATION_PLAYBOOK_INSTRUCTION`):**
```
## Cómo validar esto (para el usuario del sistema RS)

Al final de tu entregable agregá SIEMPRE una sección con este título exacto:
"Cómo validar esto (como usuario del sistema RS)".

Contenido: pasos concretos de la interfaz/negocio del PRODUCTO RS del cliente
(pantallas, menús, campos, batch, consultas) que un usuario NOVATO puede seguir
para comprobar por sí mismo que este desarrollo funciona, SIN preguntarle a un
experto. Ejemplos del tipo de paso: "cómo entrar al detalle del cliente", "cómo
asignar una obligación y verla en la pantalla de inicio".

Reglas OBLIGATORIAS:
1. Cada paso DEBE apoyarse en la documentación que recibiste (bloque func-docs,
   descripción del épica, catálogo de procesos del cliente). Citá la fuente entre
   corchetes al final del paso, por ejemplo [func-docs: Alta de cliente].
2. Si NO tenés base documental para un paso, NO lo inventes. En su lugar escribí
   textualmente: "Estos pasos no pudieron verificarse contra la documentación del
   producto. Confirmá con un referente de RS antes de usarlos."
3. Si tu entregable NO cambia nada visible para un usuario en la UI del producto
   RS (ej. refactor interno, cambio de batch sin efecto de pantalla), decilo así:
   "Este cambio no tiene validación visible en la UI de RS" y, si aplica, indicá
   la verificación técnica pertinente.
4. Envolvé la sección en este HTML para que el sistema la reconozca:
   <section data-stacky="validation-playbook" data-confidence="0.0-1.0">
     <h2>Cómo validar esto (como usuario del sistema RS)</h2>
     <ol>
       <li data-source="func-docs:alta-cliente">Paso... <em>Resultado esperado:</em> ... [func-docs: Alta de cliente]</li>
     </ol>
     <p data-sources>Fuentes: ...</p>
   </section>
   Poné data-confidence según cuán sólida sea tu base documental (1.0 = docs
   explícitas; 0.4 o menos = dudoso, y en ese caso usá el texto de degradación).
5. NUNCA toques Azure DevOps por esto: es sólo texto en tu entregable.
```

**Diff ilustrativo `base.py`** (dentro de `compose_system_prompt`, justo antes del ensamblado final en `base.py:196`):
```python
        # Plan 209 — instrucción de "Cómo validar" (enfoque A), gateada por flag.
        try:
            from services import validation_playbook as _vp  # noqa: PLC0415
            _vp_block = _vp.validation_prompt_block()
            if _vp_block:
                prefix_parts.append(_vp_block)
                meta["validation_playbook_prompt"] = True
        except Exception as exc:  # noqa: BLE001
            meta["validation_playbook_prompt_error"] = str(exc)

        if prefix_parts:
            full = "\n\n".join(prefix_parts) + "\n\n# Instrucciones del agente\n\n" + base
        else:
            full = base
        return full, meta
```
(El bloque `if prefix_parts: ... return full, meta` ya existe en `base.py:196-200`; sólo se agrega el `try` de arriba **antes** de esas líneas y no se duplican.)

**Casos borde:**
- Flag OFF → `validation_prompt_block()` devuelve `""` → prompt idéntico al de hoy (backward-compatible, verificado por test).
- `system_prompt_override` activo (FA-50, `base.py:59`) → `compose_system_prompt` retorna temprano y **no** inyecta la instrucción. Correcto: si el operador overridea el prompt, respetamos su override (documentar como limitación conocida; B lo cubre igual en F3).
- Import de `validation_playbook` falla → se captura, se registra en meta, el prompt sigue funcionando (no rompe el run).

**Tests primero (`test_plan209_prompt_contract.py`):**
- `test_instruction_presente_flag_on`: con flag ON, `FunctionalAgent().compose_system_prompt(RunContext())[0]` contiene `SECTION_TITLE` y `"data-stacky=\"validation-playbook\""`.
- `test_instruction_ausente_flag_off`: con `STACKY_VALIDATION_PLAYBOOK_ENABLED=false`, el system prompt NO contiene `SECTION_TITLE`.
- `test_override_no_inyecta`: con `RunContext(system_prompt_override="X")`, el resultado es exactamente `"X"` (sin instrucción).
- `test_meta_flag`: `meta["validation_playbook_prompt"] is True` con flag ON.

**Criterio de aceptación binario + comando:**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan209_prompt_contract.py -q
```

**Flag + default:** misma `STACKY_VALIDATION_PLAYBOOK_ENABLED` (ON).

**Impacto por runtime + fallback:**
- **Claude Code CLI / Codex CLI / Copilot Pro:** los tres consumen el mismo `system_prompt` compuesto → los tres reciben la instrucción y la siguen. Paridad garantizada por construcción.
- **Fallback:** si un runtime/modelo ignora la instrucción o el operador usó override, la sección faltará en el HTML → **F3 (enfoque B)** la genera de forma determinista; si tampoco hay grounding, degrada. Ningún runtime queda sin cobertura.

**Trabajo del operador: ninguno.**

---

### F2 — Gate determinista: detectar presencia + evaluar grounding (advisory, no bloqueante)

**Objetivo (1 frase).** Parsear la sección del HTML del agente y evaluar su grounding, reutilizando la lógica anti-alucinación existente, emitiendo warnings (nunca bloqueando). **Valor:** convierte el HTML libre en el objeto canónico y detecta pasos sin fuente.

**Archivos a crear/editar:**
- EDITAR `backend/services/validation_playbook.py` (funciones `detect`, `assess_grounding`).
- CREAR `backend/tests/test_plan209_gate_detect_assess.py`.
- EDITAR `run_harness_tests.sh` / `.ps1`.

**Nombres exactos y firmas:**
- `detect(html: str | None) -> ValidationPlaybook | None`
  - Si `html` es None/sin `SECTION_MARKER` → devuelve `None` (señal de que A no produjo la sección; dispara B).
  - Si está la sección: parsea con regex tolerante (nunca lanza, patrón espejo de `_extract_confidence_from_html`, `tickets.py:6283`):
    - `<li ... data-source="X"> texto ... </li>` → `ValidationStep(n, action=texto_limpio, expected_result=parse de "Resultado esperado:", source="X")`.
    - `data-confidence="N"` → `confidence` (cap [0,1]; ausente → 0.5).
    - `<p data-sources>Fuentes: ...</p>` → `sources`.
  - Si el HTML contiene el texto exacto `DEGRADED_MESSAGE` → status `"degraded"`, `steps=[]`.
  - Si hay `<li>` sin `data-source` (o `source` vacío) → se conserva el paso pero se marca la lista como no-grounded (lo evalúa `assess_grounding`), status tentativo `"agent_provided"`.
- `assess_grounding(pb: ValidationPlaybook, process_catalog: list | None) -> tuple[ValidationPlaybook, list[str]]`
  - Reutiliza `api/tickets.py::catalog_unknown_processes` para detectar procesos citados en los pasos que NO están en el catálogo del cliente (importar la función; es PURA, `tickets.py:6241`).
  - Warnings (lista de strings, formato espejo de `_catalog_grounding_warnings`, `tickets.py:6260`):
    - `"validation_playbook.ungrounded_step: paso {n} sin fuente"` por cada paso con `source` vacío.
    - `"validation_playbook.process_not_in_catalog: {procs}"` si hay procesos citados fuera del catálogo.
  - Si `process_catalog` es None/vacío → **no opina** sobre catálogo (sólo evalúa presencia de `source`), igual que la degradación honesta existente.
  - Devuelve el playbook (posiblemente con `status` ajustado a `"degraded"` si TODOS los pasos quedaron sin fuente) + la lista de warnings.

**Pseudocódigo `detect` (núcleo):**
```python
def detect(html):
    if not html or SECTION_MARKER not in html:
        return None
    if DEGRADED_MESSAGE in html:
        return ValidationPlaybook(status="degraded", steps=[], sources=[],
                                  confidence=0.0, degraded_reason="agent_declared")
    conf = _parse_confidence(html)            # espejo de _extract_confidence_from_html
    steps = _parse_steps(html)                # regex <li ... data-source=...>
    sources = _parse_sources(html)
    return ValidationPlaybook(status="agent_provided", steps=steps,
                              sources=sources, confidence=conf, degraded_reason=None)
```

**Casos borde:** HTML sin marcador → None. Marcador presente pero 0 `<li>` → `agent_provided` con `steps=[]` (F3 puede enriquecer). Confianza inválida → 0.5. Paso sin `data-source` → warning `ungrounded_step`. Proceso citado no en catálogo → warning `process_not_in_catalog`. Catálogo None → sin warnings de catálogo.

**Tests primero (`test_plan209_gate_detect_assess.py`):**
- `test_detect_sin_marcador_devuelve_none`.
- `test_detect_parsea_pasos_y_fuentes`: HTML con 2 `<li data-source=...>` → 2 steps con `source` no vacío + confidence parseada.
- `test_detect_degradado`: HTML con `DEGRADED_MESSAGE` → status `"degraded"`, `steps==[]`.
- `test_assess_paso_sin_fuente_warning`: playbook con un step `source=""` → warning `ungrounded_step` y (si todos sin fuente) status `"degraded"`.
- `test_assess_proceso_fuera_de_catalogo`: paso cita "proceso Zeta" ausente del catálogo → warning `process_not_in_catalog`; con catálogo None → sin ese warning.
- `test_detect_nunca_lanza`: `detect("<b>roto")`, `detect(None)`, `detect("")` no lanzan.

**Criterio de aceptación binario + comando:**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan209_gate_detect_assess.py -q
```

**Flag + default:** `STACKY_VALIDATION_PLAYBOOK_ENABLED` (ON). Con flag OFF, el llamador (F3) no invoca el gate.

**Impacto por runtime + fallback:** F2 es Python puro, runtime-agnóstico. No depende de qué runtime generó el HTML. **Trabajo del operador: ninguno.**

---

### F3 — Enfoque B: relleno por RAG + post-hook de completación (compute_and_attach)

**Objetivo (1 frase).** Cuando A no produjo la sección (o quedó pobre) y hay flag ON, construir el playbook de forma determinista desde el grounding local (docs del cliente + catálogo de procesos) con citas, o degradar honestamente; y adjuntarlo a la ejecución para UI y ADO. **Valor:** garantiza cobertura en los 3 runtimes sin LLM extra y sin inventar.

**Seam CORRECTO (corregido por hallazgo del plan hermano 208, verificado):** el punto de completación **runtime-agnóstico** NO es `agent_completion.run_on` (no todos los runners pasan por el gateway). Es el **post-hook** `services/ticket_status.py::on_execution_end` (`ticket_status.py:231`) → `_run_post_hooks` (`:279`), con registro vía `register_post_hook(fn)` (`:307`). Los 3 runners y el output_watcher terminan ahí. Firma del hook: `fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)`. Corre en orden de registro y **nunca bloquea** (errores se loguean, `:325-330`) → advisory por construcción. Patrón de registro en arranque: `app.py:853-855` (`incident_autopublish.register(ticket_status.register_post_hook)`).

**Archivos a crear/editar:**
- EDITAR `backend/services/validation_playbook.py` (funciones `build_from_grounding`, `render_playbook_html`, `compute_and_attach`, el hook `validation_playbook_post_hook` y `register(register_post_hook)`).
- EDITAR `backend/app.py` (registrar el post-hook en `create_app`, junto a `incident_autopublish.register(...)`, `app.py:853-855`).
- CREAR `backend/tests/test_plan209_build_rag_fallback.py`.
- CREAR `backend/tests/test_plan209_compute_attach.py`.
- EDITAR `run_harness_tests.sh` / `.ps1`.

**Nombres exactos y firmas:**
- `build_from_grounding(*, ticket_title: str, ticket_text: str, project_name: str | None, process_catalog: list | None) -> ValidationPlaybook`
  - Retrieval 1 (docs funcionales del cliente): `docs_rag.search(project_name, query, top_k=5)` con `query = f"cómo validar {ticket_title}"` (envuelto en try/except; si el índice no existe → sin hits). (`docs_rag.py:265`.)
  - Retrieval 2 (catálogo de procesos): `rag_retriever.build_index(rag_retriever.chunks_from_process_catalog(process_catalog))` + `rag_retriever.retrieve(index, ticket_title + " " + ticket_text, top_k=5)`. (`rag_retriever.py:63,75,94`.)
  - **Regla anti-alucinación (núcleo):**
    - Si ambos retrievals vacíos → `ValidationPlaybook(status="degraded", steps=[], sources=[], confidence=0.0, degraded_reason="no_grounding")`. B **no** inventa pasos.
    - Si hay hits: cada paso se construye **a partir de un fragmento recuperado**, con `source` = ref del hit (nombre del doc/`DocHit` o `catalog:<proceso>`). B **no** redacta pasos sin un fragmento detrás. Si los fragmentos existen pero no describen pasos de UI accionables, el playbook se arma como "consultá estas fuentes documentadas" (status `"enriched"` con `steps` que apuntan a las fuentes, `confidence` baja) — sigue siendo grounded, sin inventar UI.
    - `assess_grounding` (F2) se corre sobre el resultado: cualquier paso que quede sin `source` se elimina; si no queda ninguno → `degraded`.
  - `confidence = min(1.0, 0.3 + 0.1 * n_sources)` (heurística acotada; documentada como tal, sin pretensión de precisión).
- `render_playbook_html(pb: ValidationPlaybook) -> str`
  - **Único renderer** para UI y ADO. Devuelve el `<section data-stacky="validation-playbook">...</section>` precedido por `MARKER_COMMENT`.
  - `status == "degraded"` → renderiza `<section>` con `<h2>` + un `<p class="stacky-degraded">` con `DEGRADED_MESSAGE` y **sin** `<ol>` de pasos.
  - `status in {"agent_provided","enriched"}` → `<ol>` con los pasos + `<p data-sources>`.
- `compute_and_attach(*, execution, html: str | None, project_name: str | None, process_catalog: list | None) -> ValidationPlaybook` (núcleo testeable, sin dependencia del hook):
  - Si `not flag_enabled()` → `ValidationPlaybook(status="disabled", ...)` y NO escribe nada.
  - `pb = detect(html)`; si `pb is None` o `pb.steps == []` → `pb = build_from_grounding(...)`.
  - `pb, warnings = assess_grounding(pb, process_catalog)`.
  - Persistir `pb.to_dict()` en `execution.metadata_json["validation_playbook"]` (merge idéntico al patrón de `_close_execution`, `agent_completion.py:800-813`).
  - Emitir por cada warning un log `validation_playbook.<warning>` (para KPI-2), sin bloquear.
  - Devolver `pb`.
- `validation_playbook_post_hook(*, ticket_id, execution_id, final_status, agent_type=None, error=None, **kwargs) -> None` (wrapper que registra el seam; firma EXACTA de `register_post_hook`, `ticket_status.py:310`):
  - Si `not flag_enabled()` → return.
  - Abrir `session_scope()`; cargar `execution = session.get(AgentExecution, execution_id)` y su `ticket` (para `ado_id` y `project`).
  - Leer el HTML del deliverable: `agent_html_output.read_and_validate(ado_id).html` dentro de try/except (si no hay HTML → `html=None`, B decide).
  - `_catalog = (load_client_profile(project) or {}).get("process_catalog") or []` (`services/client_profile.py:266`).
  - Llamar `compute_and_attach(execution=execution, html=html, project_name=project, process_catalog=_catalog)`; commit.
  - Todo envuelto en try/except (el `_run_post_hooks` ya loguea y no bloquea, pero reforzamos).
- `register(register_post_hook) -> None`: `register_post_hook(validation_playbook_post_hook)` (patrón idéntico a `incident_autopublish.register`, `incident_autopublish.py:52`).

**Wiring en `app.py`** (en `create_app`, junto a los registros existentes de `app.py:853-855`):
```python
    # Plan 209 — post-hook de "Cómo validar" (advisory, no bloquea; 3 runtimes).
    from services import validation_playbook as _vp
    _vp.register(ticket_status.register_post_hook)
```

**ADO publish (sub-paso F3.4 — degradado a best-effort a propósito):** el publish ADO (`ado_publisher.ado_publish_post_hook`, `ado_publisher.py:514`) es **otro post-hook**; el orden entre hooks es frágil. Por eso el diseño **NO** depende de reescribir `comment.html` para ADO. Regla: en el camino **A** (agente incluyó la sección, status `agent_provided`) la guía ya está en `comment.html` y por lo tanto en el comentario ADO — sin tocar nada. En el camino **B** (`enriched`/`degraded`), el **piso garantizado** es la **UI** (metadata → pane F4). Anexar el bloque B al comentario ADO queda como mejora futura, sólo si se garantiza que el post-hook de 209 corre antes que el de publish y se recomputa el sha; NO se implementa en este plan para no arriesgar la idempotencia de publicación. Esto respeta "no degradar estabilidad".

**Casos borde:**
- Sin `process_catalog` y sin docs indexados → `degraded` con `DEGRADED_MESSAGE`. (El ejemplo de Esther se cubre **sólo** cuando "asignar obligación" está en las docs/catálogo; si no, degrada honesto.)
- A produjo sección con pasos → `detect` la parsea, `build_from_grounding` NO corre (no se pisa el trabajo del agente).
- A produjo la sección pero con pasos sin fuente → `assess_grounding` los limpia; si quedan 0 → `degraded`.
- Runtime que omite A (o `system_prompt_override`) → `detect` None → B construye.
- `docs_rag.search` lanza (índice inexistente) → try/except → retrieval 1 vacío; se sigue con catálogo.
- Task sin docs funcionales y sin catálogo → `degraded` (nunca inventa).

**Tests primero (`test_plan209_build_rag_fallback.py`):**
- `test_build_sin_grounding_degrada`: `process_catalog=None` + `docs_rag.search` monkeypatch → `[]` ⇒ status `"degraded"`, `steps==[]`, `degraded_reason=="no_grounding"`.
- `test_build_con_catalogo_grounded`: catálogo con proceso "IncHost" + query afín ⇒ status `"enriched"`, todos los steps con `source` no vacío.
- `test_build_nunca_inventa`: ningún step tiene `source` vacío en ningún camino (property-style sobre varias entradas).
- `test_render_degradado_sin_ol`: `render_playbook_html(degraded)` contiene `DEGRADED_MESSAGE` y NO contiene `<ol>`.
- `test_render_idempotente`: el output empieza con `MARKER_COMMENT`.

**Tests primero (`test_plan209_compute_attach.py`):**
- `test_attach_persiste_metadata`: execution fake con `metadata_json` ⇒ tras `compute_and_attach`, `json.loads(execution.metadata_json)["validation_playbook"]["status"]` es válido.
- `test_flag_off_no_escribe`: con flag OFF ⇒ status `"disabled"` y `metadata_json` sin la key `validation_playbook`.
- `test_detect_gana_sobre_build`: si `html` ya trae la sección con pasos ⇒ status `"agent_provided"` (no se llama a `build_from_grounding`; verificar con monkeypatch que build no se invoca).
- `test_warning_ungrounded_emite_log`: paso sin fuente ⇒ se registró el log `validation_playbook.ungrounded_step`.
- `test_register_agrega_post_hook`: un `register(fake_register)` llama a `fake_register` con `validation_playbook_post_hook`.
- `test_post_hook_no_lanza_sin_html`: `validation_playbook_post_hook(ticket_id=..., execution_id=..., final_status="completed")` con execution sin `comment.html` NO lanza y deja status `degraded`/`disabled` según flag (nunca rompe el cierre).

**Criterio de aceptación binario + comando:**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan209_build_rag_fallback.py tests/test_plan209_compute_attach.py -q
```

**Flag + default:** `STACKY_VALIDATION_PLAYBOOK_ENABLED` (ON). Flag OFF → status `"disabled"`, nada se escribe ni se anexa.

**Impacto por runtime + fallback:**
- **Codex / Claude / Copilot:** el post-hook cuelga de `ticket_status.on_execution_end`, por el que **terminan los 3 runners y el output_watcher** (seam verificado, no `run_on`) → cobertura idéntica. Si A funcionó (cualquier runtime) se respeta; si no, B rellena; sin grounding, degrada. **Ningún runtime queda sin sección.**

**Trabajo del operador: ninguno.**

---

### F4 — Render distinguible en la UI (pane "Cómo validar", novato-friendly)

**Objetivo (1 frase).** Mostrar el playbook como un pane claramente diferenciado en el panel de output, con pasos, resultado esperado, fuentes y nivel de confianza (o el mensaje de degradación). **Valor:** el novato lo ve donde ya mira el deliverable.

**Archivos a crear/editar:**
- CREAR `frontend/src/components/ValidationPlaybookPane.tsx`.
- CREAR `frontend/src/components/ValidationPlaybookPane.module.css`.
- EDITAR `frontend/src/components/OutputPanel.tsx` (render del pane, `OutputPanel.tsx:140-145`).
- CREAR `frontend/src/components/__tests__/ValidationPlaybookPane.test.tsx`.
- (Opcional) EDITAR `frontend/src/api/endpoints.ts` para tipar `metadata.validation_playbook`.

**Nombres exactos:**
- Componente `ValidationPlaybookPane({ playbook }: { playbook: ValidationPlaybook })`.
- Tipo TS `ValidationPlaybook = { status: "agent_provided"|"enriched"|"degraded"|"disabled"; steps: {n:number; action:string; expected_result:string; source:string}[]; sources: string[]; confidence: number; degraded_reason: string|null }`.

**Diff ilustrativo `OutputPanel.tsx`** (tras el bloque `StructuredOutput`, dentro del `execution.output &&`):
```tsx
{execution.metadata?.validation_playbook &&
 (execution.metadata.validation_playbook as any).status !== "disabled" && (
  <ValidationPlaybookPane
    playbook={execution.metadata.validation_playbook as ValidationPlaybook}
  />
)}
```

**Comportamiento del pane:**
- Encabezado distinguible: título `SECTION_TITLE` + badge de confianza (reutilizar el patrón visual de `ConfidenceBadge`, ya importado en `OutputPanel.tsx:7`) y un ícono de "guía para vos".
- `status in {agent_provided, enriched}`: lista numerada de pasos (`action` + "Resultado esperado:" `expected_result`) y un pie "Fuentes: ..." con `sources`. Cada paso muestra su `source` como chip pequeño (transparencia de grounding).
- `status == "degraded"`: banner de advertencia (color `--warning`) con `DEGRADED_MESSAGE`, **sin** lista de pasos.
- `status == "disabled"`: no renderiza (el guard del OutputPanel ya lo evita).
- **Guardarraíl anti-inline-style / ratchet UI:** usar `.module.css` con `var(--token)` (sin hex inline), para no romper `uiDebtRatchet` (gotcha conocido). Archivo nuevo ⇒ alcance 0 de inline styles.

**Casos borde UI:** `steps` vacío + status no degradado → mostrar "Sin pasos de validación disponibles" (no romper). `metadata` sin `validation_playbook` (ejecuciones viejas) → no renderiza (backward-compatible).

**Tests primero (`ValidationPlaybookPane.test.tsx`, vitest):**
- `renderiza pasos y fuentes` (status enriched, 2 steps) → aparecen las 2 acciones + los chips de fuente.
- `renderiza degradado sin pasos` (status degraded) → aparece `DEGRADED_MESSAGE` y NO hay `<ol>`.
- `no renderiza si disabled`.
- `muestra confianza`.

**Criterio de aceptación binario + comando:**
```
cd "Stacky Agents/frontend" && npx vitest run src/components/__tests__/ValidationPlaybookPane.test.tsx
```
(Recordatorio: RTL/jsdom puede no estar disponible; si el harness de este repo no corre componentes React (gotcha `rtl-jsdom-structural-gap`), el criterio se degrada a **`npx tsc --noEmit` verde + smoke manual** del pane, documentado en el PR. El test se escribe igual para cuando el entorno lo soporte.)

**Flag + default:** `STACKY_VALIDATION_PLAYBOOK_ENABLED` (ON) — el backend ya no adjunta metadata si OFF, y el pane no renderiza sin metadata.

**Impacto por runtime + fallback:** la UI lee `metadata.validation_playbook` sin importar el runtime que lo generó. **Trabajo del operador: ninguno.**

---

### F5 — Sentinel anti-alucinación (rechaza pasos sin fuente; verifica degradación)

**Objetivo (1 frase).** Test-centinela que garantiza, de forma dura, que ningún camino produce pasos sin fuente y que la degradación honesta aparece cuando no hay evidencia. **Valor:** convierte el principio anti-alucinación en un invariante ejecutable.

**Archivos a crear/editar:**
- EDITAR `backend/services/validation_playbook.py` (helper `assert_no_invented_steps(pb) -> list[str]`, PURO; usado por F5 y por `assess_grounding`).
- CREAR `backend/tests/test_plan209_anti_hallucination_sentinel.py`.
- EDITAR `run_harness_tests.sh` / `.ps1`.

**Nombres exactos:**
- `assert_no_invented_steps(pb: ValidationPlaybook) -> list[str]`: devuelve la lista de violaciones (`"step {n} sin source"`). Vacía = OK. NO lanza (para que `assess_grounding` la use como filtro).

**Tests (`test_plan209_anti_hallucination_sentinel.py`):**
- `test_build_sin_grounding_es_degradado_con_mensaje_exacto`: `build_from_grounding` sin catálogo ni docs ⇒ status `"degraded"` y `render_playbook_html` contiene **exactamente** `DEGRADED_MESSAGE`.
- `test_ningun_step_sin_source_en_enriched`: para varios inputs con grounding, `assert_no_invented_steps(pb) == []` en todo playbook `enriched`.
- `test_assess_elimina_steps_sin_source`: playbook con mix de pasos (con y sin `source`) ⇒ tras `assess_grounding`, los sin `source` NO están; si quedan 0 ⇒ `degraded`.
- `test_proceso_fuera_de_catalogo_no_se_publica_como_grounded`: paso que cita proceso ausente del catálogo ⇒ warning `process_not_in_catalog` y el paso NO cuenta como grounded.
- `test_render_degradado_no_tiene_pasos`: `render_playbook_html(degraded)` no contiene `<li`.
- `test_detect_agente_con_pasos_sin_fuente_degrada`: HTML de A con `<li>` sin `data-source` ⇒ el pipeline (`detect`+`assess`) termina en `degraded` (no publica pasos huérfanos como válidos).

**Criterio de aceptación binario + comando:**
```
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan209_anti_hallucination_sentinel.py -q
```
Verde = la garantía anti-alucinación es un invariante del sistema.

**Flag + default:** N/A (test siempre corre; valida ambos estados de flag donde aplica).

**Impacto por runtime + fallback:** invariante compartido por A y B → cubre los 3 runtimes. **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación (anclada) |
|---|--------|-----------|----------------------|
| R1 | **Pasos inventados que engañan al novato** (el peor: enseñar mal). | ALTA | A cita fuente obligatoria (F1 regla 1-2); B sólo arma pasos desde fragmentos recuperados (F3); `assess_grounding` elimina pasos sin `source` (F2); sentinel `assert_no_invented_steps` (F5). Sin evidencia ⇒ `DEGRADED_MESSAGE`, nunca invención. |
| R2 | **Agente ignora la instrucción A** o hay `system_prompt_override`. | MEDIA | B (F3) rellena determinista desde el post-hook de `on_execution_end` (por el que pasan los 3 runners); si no hay grounding, degrada. |
| R3 | **Falso grounding**: cita un doc que no respalda el paso. | MEDIA | El `source` apunta al fragmento recuperado (B) o al doc que el agente declara (A); F2 valida procesos contra `process_catalog` (`catalog_unknown_processes`). Limitación honesta: compara nombres, no IDs (igual que `_catalog_grounding_warnings`, `tickets.py:6265`). Documentar. |
| R4 | **Append a `comment.html` cambia el sha** y rompe idempotencia de publish. | MEDIA | Append idempotente por `MARKER_COMMENT`; publish recomputa sha desde el archivo final (F3.4). Piso garantizado = UI (metadata), ADO best-effort. |
| R5 | **Costo/latencia** por el retrieval B. | BAJA | B es TF-IDF local (sin red, sin LLM); sólo corre cuando A faltó; top_k acotado. A no agrega tokens. |
| R6 | **Sección no aplica** (cambio backend sin efecto de UI). | BAJA | F1 regla 3: el agente declara "sin validación visible en la UI de RS"; B degrada. No se fuerza UI inexistente. |
| R7 | **Ruido visual** en el deliverable. | BAJA | Pane distinguible y colapsable (F4); sólo se muestra si status ≠ disabled. |
| R8 | **Ratchet UI rojo** por inline styles en el pane. | BAJA | `.module.css` con tokens `var(--...)`, archivo nuevo alcance 0 (gotcha conocido). |
| R9 | **Contaminación cross-file de pytest** da falsos verdes/rojos. | MEDIA | Correr **por archivo** siempre (comandos de cada fase). |

---

## 6. Fuera de scope (explícito)

- **NO** ejecutar validaciones en el producto RS (ni abrir pantallas, ni correr batch, ni tocar su BD). La guía es **texto**.
- **NO** tocar Azure DevOps por esta feature (se respeta `agents/functional.py:25-27`).
- **NO** indexar el producto RS si no está indexado: sólo se usa lo que ya existe (bloque `func-docs` en contexto del agente, `process_catalog` del perfil, y `docs_rag` si el proyecto tiene docs `.md` indexadas). Sin esas fuentes ⇒ degradación honesta.
- **NO** llamadas LLM extra para B (retrieval local). Una eventual versión LLM-assisted de B queda para un plan futuro, opt-in y con presupuesto acotado.
- **NO** RBAC/multiusuario (mono-operador).
- **NO** diseñar la matriz tipo-de-ticket x agente (eso es el **plan 208**); 209 usa el agente genérico. A futuro, 208 podría seleccionar plantillas de validación por tipo, pero 209 no lo requiere.
- **NO** traducción/exportación de la guía (ya existe `OutputTools`, `OutputTools.tsx`); si se quiere, se integra después sin cambiar 209.

---

## 7. Glosario, Orden de implementación y Definición de Hecho

### Glosario
- **Deliverable / HTML de salida:** lo que el agente produce para el ticket; se escribe en `Agentes/outputs/<ADO_ID>/comment.html` y se valida con `agent_html_output.read_and_validate` (`agent_html_output.py:123`).
- **Grounding:** anclar una afirmación en evidencia documental real y citarla. Aquí: bloque `func-docs` (contexto del agente) y `process_catalog` del perfil del cliente.
- **RAG / DocConsultor:** retrieval local TF-IDF sin LLM: `rag_retriever.retrieve` (`rag_retriever.py:75`) sobre el catálogo (`chunks_from_process_catalog`) y `docs_rag.search` (`docs_rag.py:265`) sobre docs `.md` del cliente (vivo). El `rag_corpus.jsonl` estático NO se usa (sin consumidor vivo).
- **Bloque `func-docs`:** entrada de `default_blocks` del agente (`agents/functional.py:16`) que le entrega documentación funcional del producto del cliente en el contexto del run.
- **Gate (advisory):** verificación determinista que emite warnings/métricas sin bloquear el cierre (patrón de `_catalog_grounding_warnings`, `tickets.py:6260`).
- **Degradación honesta:** cuando no hay evidencia suficiente, se emite `DEGRADED_MESSAGE` en vez de inventar pasos.
- **Objeto canónico `ValidationPlaybook`:** única representación estructurada; dos productores (A parseado / B por RAG), un renderer (`render_playbook_html`).
- **Enfoque A / Enfoque B:** A = el agente escribe la sección (instrucción de prompt, F1). B = relleno determinista por RAG cuando A falta/queda pobre (F3).

### Orden de implementación
F0 (flag + schema) → F1 (prompt A) → F2 (gate detect/assess) → F3 (build B + wiring gateway) → F4 (UI pane) → F5 (sentinel). F2 depende de F0; F3 depende de F0/F2; F4 depende de F3 (metadata); F5 depende de F0/F2/F3.

### Definición de Hecho (DoD) global
- [ ] `STACKY_VALIDATION_PLAYBOOK_ENABLED` en `FLAG_REGISTRY`, `_CATEGORY_KEYS`, `config.py` y `_CURATED_DEFAULTS_ON`; editable desde la UI (HarnessFlagsPanel), default ON. `test_harness_flags.py` verde.
- [ ] Con flag ON, todos los agentes reciben la instrucción A (F1); con override, no (documentado).
- [ ] `detect` + `assess_grounding` (F2) convierten HTML → objeto y emiten warnings sin bloquear.
- [ ] `build_from_grounding` (F3) nunca inventa: con grounding arma pasos citados; sin grounding degrada. `compute_and_attach` persiste en `execution.metadata.validation_playbook`, invocado por el post-hook `validation_playbook_post_hook` registrado en `on_execution_end` (3 runtimes, verificado).
- [ ] Pane `ValidationPlaybookPane` (F4) renderiza pasos+fuentes+confianza o el mensaje de degradación; no rompe ratchet UI.
- [ ] Sentinel (F5) verde: 0 pasos sin fuente en cualquier camino; degradación honesta verificada.
- [ ] Los 7 archivos de test `test_plan209_*.py` registrados en `HARNESS_TEST_FILES` (`run_harness_tests.sh` y `.ps1`); meta-test ratchet verde.
- [ ] Cada suite corre **verde por archivo** con el venv del repo.
- [ ] Backward-compatible: flag OFF ⇒ prompt y deliverable idénticos a hoy; ejecuciones sin metadata no rompen la UI.
- [ ] **Trabajo del operador: ninguno** en todas las fases.
- [ ] (Smoke E2E manual, fuera de tests) Correr un agente en cada runtime y confirmar que el pane aparece grounded o degradado según el proyecto tenga o no `process_catalog`/docs.
