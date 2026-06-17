# 35 — Plan Aprendizaje del Arnés: convertir las señales de verificación que hoy se descartan en patrones persistentes y reutilizables que amplifican al operador, sin sacarlo del lazo

**Fecha:** 2026-06-16
**Estado:** PROPUESTO (ningún ítem implementado)
**Autor:** StackyArchitectaUltraEficientCode
**Predecesores directos (motor + verificación):** `docs/27` (qué entra al modelo: contexto/retrieval/routing/caché — IMPLEMENTADO salvo I2.2), `docs/28` (lifecycle/escritura/telemetría — propuesto/parcial), `docs/29` (criterios + few-shot CLI + repair semántico — IMPLEMENTADO), `docs/30` (verificación determinista de existencia — implementado/parcial), `docs/31` (verificación ejecutable del entregable — propuesto/parcial), `docs/32` (contrato de aceptación ejecutable pre-run — propuesto/parcial).
**Predecesores de método (memoria/flags/telemetría/KPIs):** `docs/26` (memoria configurable + directivas — IMPLEMENTADO), memoria colaborativa (Fase A-E + hardening — IMPLEMENTADO), `docs/33` (flags 100% configurables por UI — IMPLEMENTADO), `docs/34` (Client Profile efectivo — PROPUESTO).
**Audiencia:** dev agéntico junior (Haiku, Codex CLI, GitHub Copilot Pro). Cada fase es autocontenida: objetivo en 1 frase, archivos EXACTOS, símbolos EXACTOS, pseudocódigo/diff, tests primero con comando exacto, criterio de aceptación binario, flag + default seguro, impacto por runtime con fallback, y línea de "trabajo del operador".

**Tesis (innegociable):** los planes 27-32 construyeron un motor que **piensa mejor, no se ahoga, cumple el encargo, está anclado a la realidad, ejecuta lo producido y deriva un contrato ejecutable antes de trabajar.** Toda esa maquinaria emite, en cada run, **señales de altísimo valor**: qué criterio falló, qué finding determinista saltó, qué pase correctivo (repair) lo arregló y con qué prompt, qué verificador quedó en rojo y luego en verde, cuántos reintentos costó. **Esas señales mueren al terminar el run.** No hay memoria del arnés: el run N+1 del **mismo proyecto** y del **mismo tipo de ticket** re-deriva criterios desde cero, re-tropieza con el mismo fallo, y re-paga el mismo pase correctivo — aunque el run N ya descubrió el patrón y su remedio. El operador, además, **no ve** qué falla recurrentemente ni qué arreglo funciona: revisa cada `needs_review` aislado, sin el contexto de "este mismo fallo apareció 4 veces este mes y el repair que lo cierra es X". Este plan cierra el **séptimo lado**: un **lazo de aprendizaje del arnés** que **cosecha** (harvest) las señales que 29-32 ya producen, las **agrega en patrones** (por proyecto + tipo de agente + tipo de ticket), las **persiste reusando la memoria colaborativa existente** (no inventa store nuevo), las **reinyecta como pistas baratas** en runs futuros del mismo patrón (test-first contra fallos conocidos), y las **muestra al operador** como insight accionable en la DiagnosticsPage existente. **Lo barato baja** (menos repairs repetidos, menos re-derivación, menos tokens) **y lo valioso sube** (el arnés mejora con el uso, el operador ve patrones en vez de incidentes sueltos). No están en conflicto.

**"Aprendizaje" NO significa "autonomía" (frontera dura, regla 11 — ver [[human-in-the-loop-fundamental]]):** el sistema **observa, agrega y propone**; nunca **decide ni aplica solo**. Un patrón aprendido se inyecta como **pista de bajo peso** (hint podable, prioridad media, nunca pisa criterios ni contrato), y todo insight para el operador es **lectura** — botones "confirmar / descartar / ignorar este patrón", jamás una acción automática sobre ADO ni sobre el work item. Stacky no reabre tickets, no relanza runs, no transiciona estados, no re-escribe entregables. El operador conserva cada decisión; el arnés solo le da mejor contexto y al motor mejores pistas. Cada fase trae su línea **"Por qué NO viola regla 11"**.

**Calidad nunca se sacrifica (segundo eje):** todos los mecanismos son **aditivos y degradables**. La cosecha (harvest) es **pasiva**: lee metadata que 29-32 ya escriben, no altera el run. La reinyección es una **pista podable de prioridad media** — bajo presión de budget se descarta **antes** que criterios/contrato/grounding (que mandan); nunca quita ni contradice una señal autoritativa. Si un patrón resulta ruidoso, su `confidence` cae y deja de inyectarse; el operador puede descartarlo de por vida. No hay ninguna acción cuyo "ahorro" pueda producir un peor resultado: en el peor caso, una pista irrelevante se poda y el run procede idéntico a hoy. Cada fase trae su línea **"Salvaguarda de calidad (y cómo se mide)"**.

---

## 1. Relación con los planes previos (qué reusa, qué NO re-implementa)

- **REUSA, no re-implementa:**
  - **Memoria colaborativa / `services/memory_store.py`** como sustrato de persistencia: `save_observation` (`memory_store.py:429`), `upsert_by_topic_key` (`:519`), `search` (`:910`), `list_observations` (`:821`), `set_status` (`:615`), `StackyMemoryObservation` (`:198`). Un patrón aprendido es **una observación más** con un `scope`/`topic_key` reservado; no hay tabla nueva.
  - **Telemetría del arnés / `harness/telemetry.py`**: `RunTelemetry` (`:29`), `persist` (`:122`). Las señales a cosechar ya viajan en la metadata de la ejecución.
  - **Seam post-run / `harness/post_run.py`**: `finalize_run` (`:35`). La cosecha se engancha aquí, después de que el gate decidió, sin alterar su lógica.
  - **Inyección de contexto / `services/context_enrichment.py`**: `enrich_blocks` (`:34`), el ranking `_BLOCK_PRIORITY` y el umbral de poda. La reinyección es **un bloque más** de prioridad media.
  - **Salud / KPIs**: `services/harness_health.py` (`compute_health` `:206`, `RuntimeStats` `:30`, `by_project` `:254`) + `api/diag.py` para exponer. No se crea endpoint de métricas nuevo si `harness_health` alcanza.
  - **Flags por UI**: `services/harness_flags.py` (`FlagSpec` `:19`, `FLAG_REGISTRY` `:29`) + `api/harness_flags.py`. Todo flag nuevo entra al registry y aparece en `HarnessFlagsPanel` (doc 33) **sin tocar frontend**.
- **Frontera con 29 (criterios semánticos):** el 29 **deriva** criterios del ticket por LLM en cada run. El 35 **no deriva nada nuevo**: cosecha **cuáles de esos criterios fallaron** y los reinyecta como "ojo, este criterio suele fallar en este tipo de ticket". *Derivar* (29) vs *recordar qué falló al derivar* (35): disjuntos.
- **Frontera con 31/32 (ejecución + contrato):** 31 ejecuta verificadores; 32 deriva el contrato ejecutable. El 35 **no ejecuta ni deriva contratos**: cosecha el **resultado** (qué verificador/contrato quedó en rojo, qué repair lo cerró) y lo **agrega como patrón**. *Ejecutar/derivar el examen* (31/32) vs *aprender del historial de exámenes* (35): disjuntos.
- **Frontera con 27 (retrieval/caché):** el 27 decide **qué documento/contexto entra** por similitud semántica del ticket. El 35 inyecta un bloque distinto: **patrones de fallo/remedio** del arnés, no documentos del repo. Coexisten en `enrich_blocks` con prioridades separadas.
- **Frontera con 26 / memoria colaborativa:** esos planes capturan **conocimiento del dominio** que el operador o los runs registran como observaciones. El 35 captura **conocimiento del proceso de verificación** (qué falla y qué lo arregla), usando el **mismo store** con un `scope` reservado para no contaminar la memoria de dominio.
- **SUBSUME / REEMPLAZA:** nada. Los ítems pendientes de 28/30/31/32/34 siguen vigentes y no se tocan.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía.** No relanza runs, no reabre tickets, no transiciona estados, no aplica parches solo. Observa, agrega, propone. (Regla 11.)
2. **No agrega RBAC ni multi-usuario.** Mono-operador sin auth real (`current_user` es header sin validar — ver [[stacky-no-auth-substrate]]). Los patrones son por-proyecto, no por-usuario.
3. **No crea un store nuevo.** Persiste en `memory_store` con `scope="harness_pattern"` reservado. Cero tabla nueva, cero migración de schema de DB, cero dep nueva (npm/py), cero FTS5.
4. **No deriva criterios ni contratos nuevos.** Solo **lee** lo que 29-32 ya producen en la metadata del run.
5. **No cambia QUÉ/CUÁNDO se publica a ADO.** La cosecha es solo-lectura sobre la ejecución ya terminada.
6. **No re-implementa telemetría, gate, repair, ni ranking de contexto.** Se engancha a los seams existentes.
7. **No degrada el run cuando un patrón es ruidoso.** La pista es podable y de prioridad media; en el peor caso se descarta y el run procede idéntico a hoy.

---

## 3. Diagnóstico: dónde mueren hoy las señales de verificación (con evidencia)

| # | Debilidad | Evidencia (`file:line`) | Impacto |
|---|---|---|---|
| **D1** | **Las señales del gate/repair/verificadores no se persisten más allá del run.** `finalize_run` (`harness/post_run.py:35`) decide y devuelve `PostRunResult`; la metadata viaja a telemetría (`harness/telemetry.py:122` `persist`) y queda en la ejecución, pero **nadie la agrega ni la reusa** en runs futuros. | `post_run.py:35`; `telemetry.py:122` | Cada run del mismo patrón re-tropieza con el mismo fallo y re-paga el mismo repair. Conocimiento de proceso desperdiciado. |
| **D2** | **No hay reinyección de "lo que suele fallar".** `enrich_blocks` (`services/context_enrichment.py:34`) inyecta contexto del repo/memoria/criterios, pero **ningún bloque** trae el historial de fallos/remedios del propio arnés para ese proyecto+tipo de ticket. | `context_enrichment.py:34` | El agente no aprende del pasado del proyecto: re-comete errores que el arnés ya vio y arregló. |
| **D3** | **El operador ve incidentes sueltos, no patrones.** `harness_health.compute_health` (`services/harness_health.py:206`) agrega costo/fiabilidad por runtime y por proyecto, pero **no** "este fallo apareció N veces" ni "el repair X lo cierra el 90% de las veces". | `harness_health.py:206,254` | El operador revisa cada `needs_review` sin el contexto de recurrencia. No puede priorizar la causa raíz que más cuesta. |
| **D4** | **Los repairs exitosos no dejan rastro reutilizable.** Existen seams de reparación (`harness/run_repair.py`, `harness/criteria_repair.py`, `harness/exec_repair.py`) que arreglan en el run, pero **el prompt/diagnóstico que funcionó** no se guarda como pista para la próxima. | `harness/criteria_repair.py`, `harness/exec_repair.py` | Se re-descubre el mismo remedio una y otra vez, gastando un pase correctivo evitable. |

**Lectura central:** el sustrato (telemetría, memoria, ranking de contexto, salud, flags por UI) **ya existe y es sólido**. El valor del 35 NO es construir un store de aprendizaje: es **(a) cosechar** las señales que ya se emiten, **(b) agregarlas en patrones** con confianza, **(c) reinyectarlas como pista barata**, y **(d) mostrarlas al operador** — todo con flags OFF y comportamiento byte-idéntico al actual cuando están OFF.

---

## 4. Objetivos medibles y KPIs

| KPI | Definición | Baseline (hoy) | Objetivo |
|---|---|---|---|
| **K1 — Tasa de repair repetido** | % de runs cuyo fallo (criterio/verificador/contrato) ya había aparecido ≥1 vez en el mismo proyecto+tipo de ticket en los últimos 30 días | n/d (no medido) | medible y decreciente con la reinyección ON |
| **K2 — Cobertura de patrones** | nº de patrones de fallo/remedio con `confidence` ≥ umbral, por proyecto | 0 | creciente y reportado |
| **K3 — Δ reintentos por run** | reintentos de repair promedio con reinyección ON vs OFF, sobre runs del mismo patrón | n/d | reintentos − (medible y positivo) |
| **K4 — Δ tokens de re-derivación** | tokens gastados re-derivando criterios/diagnósticos que un patrón ya conocía | n/d | − (la pista evita re-trabajo) |
| **K5 — Insight accionable** | nº de patrones que el operador confirma/descarta (señal de que el insight es útil) | 0 | reportado; ratio confirmados/descartados sano |

Todos los KPIs se exponen en la **DiagnosticsPage existente** vía el seam `harness_health`/`api/diag.py` (igual que 30-32), sin UI de métricas nueva.

**Glosario rápido (términos que un modelo menor podría no conocer): ver sección 11.**

---

## Principios y guardarraíles (vinculantes en todas las fases)

1. **3 runtimes con paridad:** cada ítem funciona en Codex CLI, Claude Code CLI y GitHub Copilot Pro, o degrada con fallback explícito. La cosecha lee metadata **runtime-agnóstica** del `PostRunResult`/telemetría; la reinyección usa el **mismo** `enrich_blocks` que los 3 runners ya llaman.
2. **Cero trabajo extra al operador:** todo es invisible/automático u opt-in con default OFF. Sin pasos manuales nuevos, sin nueva config obligatoria, backward-compatible.
3. **Human-in-the-loop innegociable:** observar/agregar/proponer, nunca decidir/aplicar. Regla 11.
4. **Mono-operador sin auth real:** nada de RBAC ni multiusuario.
5. **No degradar performance/seguridad/estabilidad/DX.** Reusar lo existente; cero deps nuevas; cero FTS5; cero tabla nueva.
6. **Flag nuevo → `config.py` + `FLAG_REGISTRY` en la MISMA fase/PR que lo introduce, default OFF, retro-compat byte-idéntica con flag OFF** (idéntico a 29-34). **Regla dura (doc 33): TODO flag del 35 es configurable por UI desde el momento en que existe** — se registra su `FlagSpec` en `FLAG_REGISTRY` (grupo `harness_learning`) en el mismo PR que lo agrega a `config.py`, de modo que aparece en `HarnessFlagsPanel` sin tocar frontend. **Nunca** existe un flag del 35 que no se pueda prender/apagar desde la UI; F4 no "habilita" los flags por UI, solo agrega la tarjeta de patrones.
7. **Suite contaminada → validar por archivo con el python del `.venv`** (pin pywin32==306 roto en 3.13 — ver [[stacky-backend-dev-test-env]]). **vitest frontend no instalado** → UI: solo `tsc` + degradación con gracia.
8. **Sin secretos en los patrones:** la cosecha **redacta** cualquier valor sospechoso antes de persistir (reusa el detector de secretos de la memoria colaborativa); un patrón nunca transporta PAT/passwords/paths sensibles.

> **Comando base de tests** (todas las fases lo usan, ajustando el archivo):
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/<ARCHIVO>" -q`
> Si el `.venv` no resuelve, usar el intérprete del repo declarado en [[stacky-backend-dev-test-env]]. **Nunca** correr la suite completa (contaminada): siempre por archivo.

---

## FASE F0 — Sustrato: tipo de patrón + persistencia en la memoria existente (habilita todo lo demás)

**Objetivo (1 frase):** definir el tipo `HarnessPattern` y su persistencia reutilizando `memory_store`, con `scope` reservado para no contaminar la memoria de dominio. **Valor:** sustrato común de las fases F1-F4.

**Archivos a crear/editar (rutas exactas):**
- CREAR `backend/services/harness_learning.py` — módulo único del aprendizaje del arnés.
- EDITAR `backend/config.py` — agregar las env vars de los flags (ver cada fase).
- EDITAR `backend/services/harness_flags.py` — agregar los `FlagSpec` (ver F4).

**Símbolos exactos a crear (en `harness_learning.py`):**
```python
HARNESS_PATTERN_SCOPE = "harness_pattern"   # scope reservado en memory_store

@dataclass(frozen=True)
class HarnessPattern:
    project: str
    agent_type: str           # "FunctionalAnalyst" | "TechnicalAnalyst" | "Developer"
    ticket_kind: str          # categoría barata: "bug" | "feature" | "task" | "unknown"
    signal_kind: str          # "criterion_fail" | "verifier_fail" | "contract_fail" | "repair_success"
    signal_key: str           # id estable del fallo (p.ej. nombre del criterio o del verificador)
    remedy_hint: str          # texto corto, redactado, del diagnóstico/prompt que lo cerró (puede ser "")
    occurrences: int          # cuántas veces se observó
    confidence: float         # [0,1], derivada de occurrences y recencia
    last_seen: str            # ISO date

def pattern_topic_key(p: HarnessPattern) -> str:
    # clave estable de upsert: agrupa el MISMO fallo en el MISMO contexto
    return f"{p.project}|{p.agent_type}|{p.ticket_kind}|{p.signal_kind}|{p.signal_key}"

def persist_pattern(p: HarnessPattern) -> str:
    # usa memory_store.upsert_by_topic_key con scope=HARNESS_PATTERN_SCOPE
    # title = signal_key ; content = json del patrón ; topic_key = pattern_topic_key(p)
    # redacta secretos antes de guardar (reusar detector de la memoria colaborativa)
    ...

def list_patterns(project: str, *, min_confidence: float = 0.0) -> list[HarnessPattern]:
    # memory_store.list_observations(scope=HARNESS_PATTERN_SCOPE, project=project) -> deserializa
    ...
```

**Pseudocódigo de `persist_pattern` (casos borde explícitos):**
```
def persist_pattern(p):
    if contains_secret(p.remedy_hint) or contains_secret(p.signal_key):
        p = replace(p, remedy_hint=redact(p.remedy_hint), signal_key=redact(p.signal_key))
    payload = json.dumps(asdict(p), sort_keys=True)
    return memory_store.upsert_by_topic_key(
        scope=HARNESS_PATTERN_SCOPE,
        project=p.project,
        topic_key=pattern_topic_key(p),
        title=p.signal_key[:120],
        content=payload,
        # status inicial "active"; el operador puede pasarlo a "dismissed" (F4)
    )
# Caso borde: project vacío -> no persistir (return ""). agent_type/ticket_kind desconocidos -> "unknown".
# Idempotencia: dos persist del mismo topic_key incrementan occurrences, no duplican filas.
```

**Tests PRIMERO** — `backend/tests/test_harness_learning_store.py`:
- `test_pattern_topic_key_is_stable` — misma tupla → misma key; distinto `signal_key` → distinta key.
- `test_persist_is_idempotent_by_topic_key` — persistir dos veces el mismo patrón NO crea dos observaciones (upsert).
- `test_persist_redacts_secrets` — un `remedy_hint` con algo tipo PAT se guarda redactado.
- `test_list_patterns_filters_by_confidence` — `min_confidence` filtra.
- `test_empty_project_is_not_persisted` — `project=""` → no persiste.

**Comando exacto:** `& ".../backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_harness_learning_store.py" -q`

**Criterio de aceptación BINARIO:** los 5 tests pasan; `memory_store` no recibe schema nuevo (se usa el `scope`).

**Flag + default:** sin flag de runtime (estructura inerte; nadie escribe sin F1, nadie lee sin F2). No altera ningún comportamiento por sí sola.

**Impacto por runtime:** ninguno (no se invoca en runtime todavía). Fallback: n/a.

**Trabajo del operador: ninguno.**

**Por qué NO viola regla 11:** solo define un tipo y una forma de guardar; no decide ni actúa.

**Salvaguarda de calidad (y cómo se mide):** redacción de secretos testeada; idempotencia testeada (no infla `occurrences` por dobles escrituras accidentales).

---

## FASE F1 — Cosecha pasiva post-run (harvest): leer las señales que 29-32 ya emiten

**Objetivo (1 frase):** tras `finalize_run`, extraer de la metadata del run los fallos/remedios y persistirlos como patrones, sin alterar el run. **Valor:** convierte señal efímera en patrón (cierra D1/D4).

**Archivos a editar:**
- EDITAR `backend/harness/post_run.py` — al final de `finalize_run` (`:35`), llamar `harness_learning.harvest_from_result(...)` detrás del flag.
- EDITAR `backend/services/harness_learning.py` — agregar `harvest_from_result`.
- EDITAR `backend/config.py` — agregar `HARNESS_LEARNING_HARVEST_ENABLED`.
- EDITAR `backend/services/harness_flags.py` — **registrar su `FlagSpec` ya en esta fase** (grupo `harness_learning`) para que sea configurable por UI desde que existe (regla dura, guardarraíl 6).
- EDITAR `backend/.env.example` — documentar la key.

**Símbolos exactos a crear:**
```python
def classify_ticket_kind(ticket_title: str, ticket_type: str | None) -> str:
    # heurística barata, stdlib: "bug"/"feature"/"task"/"unknown". Sin LLM.

def harvest_from_result(*, project, agent_type, ticket_title, ticket_type,
                        result, telemetry_md, log) -> int:
    # lee result (PostRunResult) + telemetry_md (dict ya persistido) y extrae señales:
    #  - criterios fallidos (29)         -> signal_kind="criterion_fail"
    #  - verificadores en rojo (31)      -> signal_kind="verifier_fail"
    #  - contrato no cumplido (32)       -> signal_kind="contract_fail"
    #  - repair que cerró un fallo       -> signal_kind="repair_success" + remedy_hint
    # por cada señal: build HarnessPattern -> persist_pattern. Devuelve nº persistido.
    # best-effort: cualquier excepción se loguea y se ignora (NUNCA rompe el run).
```

**Diff ilustrativo en `post_run.py` (al final de `finalize_run`, después de decidir el verdict):**
```python
# --- F1: harvest de aprendizaje (best-effort, detrás de flag) ---
if config.HARNESS_LEARNING_HARVEST_ENABLED:
    try:
        harness_learning.harvest_from_result(
            project=project, agent_type=agent_type,
            ticket_title=ticket_title, ticket_type=ticket_type,
            result=post_run_result, telemetry_md=telemetry_md, log=log,
        )
    except Exception as exc:                     # nunca propaga
        log(f"[harness-learning] harvest skipped: {exc}")
return post_run_result                            # verdict inalterado
```

**Casos borde:**
- Metadata sin señales de 29-32 (planes no implementados aún en ese run) → `harvest` persiste 0 patrones, sin error.
- `repair_success` sin diagnóstico legible → `remedy_hint=""` (patrón válido igual).
- Flag OFF → la rama entera no se ejecuta; `finalize_run` byte-idéntico al actual.

**Tests PRIMERO** — `backend/tests/test_harness_learning_harvest.py`:
- `test_harvest_extracts_criterion_fail` — metadata con criterio fallido → 1 patrón `criterion_fail`.
- `test_harvest_extracts_repair_success_with_hint` — repair exitoso → patrón con `remedy_hint` no vacío.
- `test_harvest_is_noop_without_signals` — metadata vacía → 0 patrones, sin excepción.
- `test_harvest_never_raises` — metadata corrupta → no propaga (atrapado).
- `test_classify_ticket_kind` — títulos representativos → categoría correcta.
- `test_flag_off_does_not_harvest` (en `test_post_run` o aquí) — con flag OFF, `finalize_run` no llama harvest.

**Comando exacto:** `& ".../backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_harness_learning_harvest.py" -q`

**Criterio de aceptación BINARIO:** tests pasan; con flag OFF, el `PostRunResult` de un run de control es idéntico al actual (mismo verdict, misma metadata).

**Flag + default:** `HARNESS_LEARNING_HARVEST_ENABLED` (bool, **OFF**). **Registrado en `FLAG_REGISTRY` en este mismo PR** (`FlagSpec` con `group="harness_learning"` — ver bloque en F4) → aparece en `HarnessFlagsPanel` y se prende/apaga por UI desde ya. Agregar también `test_harness_learning_harvest_flag_registered` en `backend/tests/test_harness_flags.py`.

**Impacto por runtime:**
- **Codex CLI / Claude Code CLI / Copilot:** idéntico — `finalize_run` es el seam común post-run de los 3. La cosecha lee metadata runtime-agnóstica.
- **Fallback:** si un runtime no escribió alguna señal (plan 31/32 no activo en ese run), harvest extrae las que sí estén y omite el resto. Best-effort.

**Trabajo del operador: ninguno** (invisible; opt-in default OFF).

**Por qué NO viola regla 11:** lee y guarda; no decide, no actúa sobre el ticket, no publica.

**Salvaguarda de calidad (y cómo se mide):** harvest es **pasivo y best-effort** — envuelto en try/except que nunca propaga; con flag OFF el run es byte-idéntico (test de control). Mide: `test_flag_off_does_not_harvest`.

---

## FASE F2 — Reinyección como pista barata (hint podable de prioridad media)

**Objetivo (1 frase):** en runs futuros del mismo patrón, inyectar un bloque corto "fallos conocidos y su remedio" como hint de prioridad media, podable antes que criterios/contrato. **Valor:** el agente trabaja test-first contra fallos conocidos (cierra D2; mueve K1/K3/K4).

**Archivos a editar:**
- EDITAR `backend/services/context_enrichment.py` — dentro de `enrich_blocks` (`:34`), agregar el bloque `harness-patterns` detrás del flag, con prioridad MEDIA (por debajo de criterios/contrato/grounding, por encima de "similares").
- EDITAR `backend/services/harness_learning.py` — agregar `build_pattern_hint_block`.
- EDITAR `backend/config.py` — agregar `HARNESS_LEARNING_INJECT_ENABLED`, `HARNESS_LEARNING_INJECT_MAX`, `HARNESS_LEARNING_INJECT_MIN_CONF`.
- EDITAR `backend/services/harness_flags.py` — **registrar los 3 `FlagSpec` ya en esta fase** (grupo `harness_learning`, incluidos los de tipo `int`/`float`) para que sean configurables por UI desde que existen (regla dura, guardarraíl 6).
- EDITAR `backend/.env.example` — documentar las 3 keys.

**Símbolos exactos:**
```python
HARNESS_PATTERN_BLOCK_NAME = "harness-patterns"
HARNESS_PATTERN_BLOCK_PRIORITY = 50      # MEDIA: < criterios/contrato/grounding (>=75), > similares

def build_pattern_hint_block(project, agent_type, ticket_title, ticket_type, *,
                             max_patterns: int = 5, min_confidence: float = 0.5) -> str | None:
    # list_patterns(project, min_confidence) filtrado por agent_type + ticket_kind(ticket)
    # toma los top-N por confidence; arma texto corto:
    #   "Fallos recurrentes en este tipo de ticket (pistas, no obligatorias):
    #    - [criterion_fail] X suele fallar; remedio que funcionó: Y
    #    ..."
    # devuelve None si no hay patrones (no inyecta bloque vacío).
```

**Diff ilustrativo en `enrich_blocks`:**
```python
# --- F2: bloque de patrones aprendidos (hint podable, prioridad media) ---
if config.HARNESS_LEARNING_INJECT_ENABLED:
    hint = harness_learning.build_pattern_hint_block(
        project, agent_type, ticket_title, ticket_type,
        max_patterns=config.HARNESS_LEARNING_INJECT_MAX,        # default 5
        min_confidence=config.HARNESS_LEARNING_INJECT_MIN_CONF, # default 0.5 (float)
    )
    if hint:
        blocks.append(Block(name=HARNESS_PATTERN_BLOCK_NAME,
                            priority=HARNESS_PATTERN_BLOCK_PRIORITY,
                            text=hint))      # sujeto a budget/poda como cualquier bloque
```

**Casos borde:**
- Sin patrones para el contexto → `build_pattern_hint_block` devuelve `None` → no se agrega bloque (cero ruido).
- Budget ajustado → al ser prioridad 50 (< umbral de protección), se poda **antes** que criterios/contrato. Nunca desplaza una señal autoritativa.
- Flag OFF → no se agrega el bloque; `enrich_blocks` byte-idéntico.

**Tests PRIMERO** — `backend/tests/test_harness_learning_inject.py`:
- `test_hint_block_lists_top_patterns_by_confidence` — con 8 patrones, inyecta los 5 de mayor confianza.
- `test_hint_block_filters_by_agent_and_ticket_kind` — patrón de otro agente/tipo no aparece.
- `test_no_patterns_returns_none` — sin patrones → `None`, no bloque vacío.
- `test_block_priority_is_below_criteria` — `HARNESS_PATTERN_BLOCK_PRIORITY` < prioridad de criterios/contrato (constante comparada).
- `test_flag_off_no_block` — flag OFF → `enrich_blocks` no agrega `harness-patterns`.

**Comando exacto:** `& ".../backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_harness_learning_inject.py" -q`

**Criterio de aceptación BINARIO:** tests pasan; con flag OFF, los bloques que produce `enrich_blocks` para un caso de control son idénticos a hoy (mismo conjunto/orden).

**Flag + default:** `HARNESS_LEARNING_INJECT_ENABLED` (bool, **OFF**); `HARNESS_LEARNING_INJECT_MAX` (int, default 5); `HARNESS_LEARNING_INJECT_MIN_CONF` (float, default 0.5). **Los 3 registrados en `FLAG_REGISTRY` en este mismo PR** (`group="harness_learning"` — ver bloque en F4), configurables por UI desde ya; el `int` y el `float` usan el control numérico que el panel del doc 33 ya soporta. Agregar `test_harness_learning_inject_flags_registered` en `backend/tests/test_harness_flags.py`.

**Impacto por runtime:**
- **Codex CLI:** `enrich_blocks` se llama en `codex_cli_runner.py` (seam compartido) → recibe el bloque.
- **Claude Code CLI:** idem en `claude_code_cli_runner.py`.
- **Copilot:** usa el mismo `enrich_blocks`; si su pipeline de contexto fuese más restringido, el bloque de prioridad 50 es el **primero en podarse** → degradación natural sin romper.
- **Fallback común:** sin patrones o bajo budget → no se inyecta nada → comportamiento idéntico a hoy.

**Trabajo del operador: ninguno** (invisible; opt-in default OFF).

**Por qué NO viola regla 11:** es una **pista** explícitamente "no obligatoria"; no fuerza conducta, no decide, el agente y el operador mandan.

**Salvaguarda de calidad (y cómo se mide):** la pista es **podable y de prioridad media** — nunca desplaza criterios/contrato/grounding; en peor caso se descarta. Test `test_block_priority_is_below_criteria` lo fija. Mide: K3 (reintentos) y K4 (tokens) ON vs OFF sobre runs del mismo patrón.

---

## FASE F3 — Confianza, decaimiento y supresión de ruido

**Objetivo (1 frase):** calcular `confidence` por ocurrencias + recencia, y dejar de inyectar patrones rancios o que el operador descartó. **Valor:** la pista solo aparece cuando es fiable (evita ruido; sostiene calidad de F2).

**Archivos a editar:**
- EDITAR `backend/services/harness_learning.py` — agregar `compute_confidence`, `apply_decay`, y respetar `status="dismissed"` en `list_patterns`.

**Símbolos exactos:**
```python
def compute_confidence(occurrences: int, days_since_last_seen: int) -> float:
    # monótona creciente en occurrences, decreciente en antigüedad.
    # ej: base = min(1.0, occurrences / 5) ; decay = 0.5 ** (days_since_last_seen / 30)
    # return round(base * decay, 3). Determinista, sin LLM, sin deps.

def is_suppressed(pattern_status: str) -> bool:
    return pattern_status == "dismissed"   # operador lo descartó (F4) -> nunca se inyecta
```

**Diff en `list_patterns` (F0):** filtrar `status != "dismissed"` y recomputar `confidence` on-read con `apply_decay` (no escribe; se evalúa al leer, como el resto del sistema).

**Casos borde:**
- Patrón visto 1 vez hoy → `confidence` baja (no llega al `min_confidence` default 0.5) → no se inyecta hasta acumular evidencia.
- Patrón visto 6 veces pero hace 120 días → decay lo baja → deja de inyectarse (rancio).
- Patrón `dismissed` por el operador → `list_patterns` lo excluye siempre.

**Tests PRIMERO** — `backend/tests/test_harness_learning_confidence.py`:
- `test_confidence_grows_with_occurrences`.
- `test_confidence_decays_with_age`.
- `test_dismissed_pattern_is_never_listed`.
- `test_single_occurrence_below_default_threshold` — 1 ocurrencia hoy < 0.5.

**Comando exacto:** `& ".../backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_harness_learning_confidence.py" -q`

**Criterio de aceptación BINARIO:** los 4 tests pasan.

**Flag + default:** sin flag propio (es lógica interna de F2; gobernada por `HARNESS_LEARNING_INJECT_MIN_CONF`).

**Impacto por runtime:** ninguno directo; afecta qué inyecta F2 en los 3 por igual.

**Trabajo del operador: ninguno** (salvo el descarte opcional de F4).

**Por qué NO viola regla 11:** matemática determinista de relevancia; respeta el descarte del operador (lo amplifica, no lo ignora).

**Salvaguarda de calidad (y cómo se mide):** un patrón solo se inyecta con evidencia suficiente y reciente; el ruido se autoextingue por decay. Mide: K2 (cobertura de patrones con `confidence` ≥ umbral).

---

## FASE F4 — Visibilidad para el operador (insight de lectura + descartar/confirmar)

**Objetivo (1 frase):** mostrar los patrones aprendidos en la DiagnosticsPage existente (solo lectura + botones confirmar/descartar). **Valor:** el operador ve patrones en vez de incidentes sueltos (cierra D3; K5).

> **Nota sobre flags (regla dura, guardarraíl 6):** los **4 flags del 35 YA están registrados en `FLAG_REGISTRY` y son configurables por UI** desde F1 (harvest) y F2 (inject) — F4 **no** introduce ni "habilita por UI" ningún flag. El bloque `FlagSpec` de abajo es la **referencia canónica** de los 4; F4 solo verifica que el grupo `harness_learning` aparezca completo y ordenado en `HarnessFlagsPanel`. No existe en ningún momento un flag del 35 que no se pueda prender/apagar desde la UI.

**Archivos a editar:**
- EDITAR `backend/api/diag.py` — agregar `GET /api/diag/harness-patterns?project=...` (lista) y `POST /api/diag/harness-patterns/<id>/dismiss` y `.../confirm` (cambian `status` vía `memory_store.set_status` `memory_store.py:615`). Sin endpoint de métricas nuevo aparte.
- EDITAR `backend/services/harness_health.py` — en `compute_health`/`RuntimeStats` agregar contadores agregados: `patterns_total`, `patterns_high_conf`, `repeated_failure_rate` (K1) por proyecto, reusando `by_project` (`:254`). Solo lectura.
- EDITAR `frontend/src/components/.../DiagnosticsPage` (componente existente) — agregar una tarjeta `HarnessPatternsCard` (lista + botones). Sin librería nueva.
- (Los `FlagSpec` y las keys de `.env.example` **ya se agregaron en F1/F2**, no se repiten aquí.)

**`FlagSpec` — referencia canónica de los 4 flags (registrados en F1/F2, NO en F4):**
```python
FlagSpec(key="HARNESS_LEARNING_HARVEST_ENABLED", type="bool",
         label="Aprendizaje del arnés: cosechar (F1)",
         description="35.F1 — Si ON, post-run cosecha fallos/remedios como patrones. Pasivo.",
         group="harness_learning"),
FlagSpec(key="HARNESS_LEARNING_INJECT_ENABLED", type="bool",
         label="Aprendizaje del arnés: reinyectar (F2)",
         description="35.F2 — Si ON, inyecta pistas de fallos conocidos (podables, prioridad media).",
         group="harness_learning"),
FlagSpec(key="HARNESS_LEARNING_INJECT_MAX", type="int",
         label="Máx. patrones por run",
         description="35.F2 — Cuántas pistas como máximo inyectar (default 5).",
         group="harness_learning"),
FlagSpec(key="HARNESS_LEARNING_INJECT_MIN_CONF", type="float",
         label="Confianza mínima de pista",
         description="35.F2/F3 — Solo inyecta patrones con confidence >= este valor (default 0.5).",
         group="harness_learning"),
```

**Pseudocódigo del endpoint de lista:**
```
GET /api/diag/harness-patterns?project=P:
    patterns = harness_learning.list_patterns(P, min_confidence=0.0)  # incluye baja conf para inspección
    return [asdict(p) + {"id": observation_id} ordenado por confidence desc]
POST .../<id>/dismiss:  memory_store.set_status(id, "dismissed"); return 200
POST .../<id>/confirm:  memory_store.set_status(id, "active");    return 200
```

**Casos borde:**
- Proyecto sin patrones → lista vacía → la tarjeta muestra "sin patrones aún" (no error).
- `dismiss`/`confirm` de un id inexistente → 404, sin efecto.
- Flags OFF → la tarjeta puede mostrarse vacía; los endpoints siguen siendo solo-lectura/estado, sin tocar runs.

**Tests PRIMERO:**
- `backend/tests/test_harness_learning_api.py`:
  - `test_list_endpoint_returns_patterns_sorted` — orden por confidence desc.
  - `test_dismiss_sets_status_dismissed` — luego `list_patterns(min_confidence=0)` lo excluye de inyección (F3).
  - `test_confirm_reactivates_pattern`.
  - `test_dismiss_unknown_id_returns_404`.
- `backend/tests/test_harness_flags.py` (existente, agregar): `test_harness_learning_group_complete` — las **4** keys están en `FLAG_REGISTRY` con grupo `harness_learning` y tipos correctos (`bool`/`bool`/`int`/`float`). (Los tests por-flag ya viven en F1/F2; este verifica el grupo completo y ordenado.)
- `backend/tests/test_harness_health.py` (existente, agregar): `test_health_reports_pattern_counts` — `patterns_total`/`patterns_high_conf` presentes por proyecto.

**Comando exacto:**
`& ".../backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_harness_learning_api.py" "backend/tests/test_harness_flags.py" "backend/tests/test_harness_health.py" -q`
Frontend: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" ; npx tsc --noEmit` (vitest no instalado — solo `tsc`).

**Criterio de aceptación BINARIO:** tests backend pasan; `tsc` limpio; con flags OFF, la DiagnosticsPage existente sigue funcionando (degradación con gracia: tarjeta vacía o ausente).

**Flag + default:** los 4 flags de arriba, todos default seguro (bools OFF; ints/floats con default conservador). La tarjeta de UI es **siempre de lectura**; los botones cambian estado de un patrón, nunca lanzan acciones sobre ADO/runs.

**Impacto por runtime:** ninguno en el run (es observabilidad). Los patrones mostrados provienen de cualquiera de los 3 runtimes por igual (harvest runtime-agnóstico).

**Trabajo del operador: ninguno obligatorio.** Opcionalmente puede confirmar/descartar un patrón (un click), lo que **amplifica** su control sin obligarlo a nada.

**Por qué NO viola regla 11:** todo es lectura + cambio de estado de una *pista*; ninguna acción decide trabajo, publica, ni transiciona el work item. El operador decide; el arnés informa.

**Salvaguarda de calidad (y cómo se mide):** la visibilidad no toca runs; el descarte del operador **suprime** ruido en F2/F3 (mejora la calidad de la pista). Mide: K5 (ratio confirmados/descartados).

---

## 5. Mecanismos transversales (resumen)

- **Cosecha pasiva (F1):** lee metadata que 29-32 ya emiten en `finalize_run`; best-effort; flag OFF → run byte-idéntico.
- **Persistencia reusada (F0):** `memory_store` con `scope="harness_pattern"`; cero tabla nueva; secretos redactados.
- **Reinyección podable (F2):** bloque de prioridad media en `enrich_blocks`; nunca desplaza criterios/contrato/grounding; sin patrones → sin bloque.
- **Confianza + decay (F3):** solo se inyecta lo fiable y reciente; el ruido se autoextingue; el descarte del operador manda.
- **Visibilidad de lectura (F4):** DiagnosticsPage + `harness_health`; confirmar/descartar como única interacción, siempre opcional.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Una pista aprendida sesga al agente hacia un error pasado.** | Es hint explícitamente "no obligatorio", prioridad media podable, nunca pisa criterios/contrato; `confidence` + decay la apagan; el operador la descarta de por vida (F4). |
| **La cosecha rompe o ralentiza el run.** | F1 es pasiva, best-effort, envuelta en try/except que nunca propaga; flag OFF → run byte-idéntico (test de control). |
| **Un patrón filtra un secreto.** | Redacción obligatoria antes de persistir (F0), testeada; reusa el detector de la memoria colaborativa. |
| **Contamina la memoria de dominio.** | `scope="harness_pattern"` reservado y separado; la búsqueda de dominio no lo incluye. |
| **Asimetría entre runtimes (un runtime no emite ciertas señales).** | Harvest extrae lo que haya y omite el resto; reinyección degrada podando el bloque primero. Paridad por seam compartido (`finalize_run`/`enrich_blocks`). |
| **Ruido de patrones de baja señal.** | Umbral `min_confidence` (default 0.5) + tope `max` (default 5) + decay; el operador descarta. |

---

## 7. Fuera de scope (no-objetivos de esta iteración)

- **Aplicar un remedio automáticamente** (re-prompt forzado, parche auto): diferido — choca con regla 11.
- **Aprendizaje cross-proyecto** (compartir patrones entre proyectos distintos): fuera de scope (los patrones son por-proyecto; un eje cross-proyecto requiere diseño aparte).
- **Clasificación de `ticket_kind` por LLM:** fuera de scope — se usa heurística barata stdlib; subir a LLM solo si la heurística resulta insuficiente (medible por K2).
- **Editor visual de patrones** más allá de la lista + confirmar/descartar: diferido.
- **Borrado físico de patrones rancios:** diferido; el decay + `dismissed` ya los neutraliza sin borrar.

---

## 8. Glosario (términos del dominio Stacky)

- **Arnés (harness):** la capa que envuelve cada ejecución del agente (gate, repair, verificación, telemetría) — `backend/harness/`.
- **Señal de verificación:** dato que el arnés produce al verificar un entregable (criterio fallido, verificador en rojo, contrato no cumplido, repair exitoso).
- **Patrón (HarnessPattern):** agregación de una señal recurrente en un contexto (proyecto + tipo de agente + tipo de ticket), con ocurrencias y confianza.
- **Harvest (cosecha):** leer las señales de un run terminado y persistirlas como patrones. Pasivo, no altera el run.
- **Reinyección (hint):** agregar al contexto del próximo run una pista corta de fallos conocidos. Podable, no obligatoria.
- **Repair:** pase correctivo que intenta cerrar un fallo dentro del run (`harness/run_repair.py`, `criteria_repair.py`, `exec_repair.py`).
- **`finalize_run`:** seam post-run común a los 3 runtimes donde se decide el verdict (`harness/post_run.py:35`).
- **`enrich_blocks`:** seam de armado de contexto común a los 3 runners (`services/context_enrichment.py:34`).
- **`memory_store` / scope:** store de la memoria colaborativa; `scope` particiona observaciones por uso (aquí `harness_pattern`).
- **Regla 11 / human-in-the-loop:** Stacky amplifica al operador, nunca lo reemplaza; ver [[human-in-the-loop-fundamental]].
- **Flag OFF byte-idéntico:** con el flag en su default OFF, el comportamiento debe ser exactamente el actual.

---

## 9. Orden de implementación (secuencial, por dependencia)

1. **F0** — tipo `HarnessPattern` + `persist_pattern`/`list_patterns` sobre `memory_store` (scope reservado). Sin efecto runtime. (Riesgo mínimo.)
2. **F1** — harvest en `finalize_run` detrás de `HARNESS_LEARNING_HARVEST_ENABLED` (OFF). **Registra su flag en `FLAG_REGISTRY` (UI) en el mismo PR.** Empieza a acumular patrones cuando el operador lo prenda desde la UI.
3. **F3** — confianza + decay + supresión (lógica interna que F2 necesita para no inyectar ruido).
4. **F2** — reinyección como bloque podable detrás de `HARNESS_LEARNING_INJECT_ENABLED` (OFF). **Registra sus 3 flags en `FLAG_REGISTRY` (UI) en el mismo PR.**
5. **F4** — visibilidad (DiagnosticsPage + `harness_health`). Los 4 flags **ya** son configurables por UI desde F1/F2; F4 solo verifica el grupo completo.

> Rollout sugerido: prender **F1** primero (cosecha en sombra, sin inyectar) para acumular patrones y medir K2; luego **F2** para medir K1/K3/K4; **F4** acompaña desde el inicio para que el operador vea qué se está aprendiendo.

---

## 10. Definición de Hecho (DoD) global

- [ ] Cada flag nuevo está en `config.py` **y** en `FLAG_REGISTRY` **en la misma fase/PR que lo introduce** (harvest en F1, inject en F2 — NO diferido a F4), default OFF/seguro, y aparece en `HarnessFlagsPanel` sin tocar frontend. **En ningún momento existe un flag del 35 que no sea configurable por UI** (regla dura, doc 33).
- [ ] Con **todos los flags OFF**, `finalize_run` y `enrich_blocks` son **byte-idénticos** a hoy (tests de control verdes).
- [ ] Cero tabla nueva, cero migración de DB, cero dep npm/py nueva, cero FTS5: persistencia 100% sobre `memory_store` con `scope="harness_pattern"`.
- [ ] Secretos redactados antes de persistir (test verde).
- [ ] Harvest es best-effort: nunca propaga excepción al run (test verde).
- [ ] Reinyección es podable y de prioridad media: nunca desplaza criterios/contrato/grounding (test de prioridad verde).
- [ ] Paridad en los 3 runtimes: harvest vía `finalize_run`, reinyección vía `enrich_blocks` (seams compartidos); degradación por poda si un runtime restringe contexto.
- [ ] Toda interacción del operador es opcional y de lectura/estado; ninguna acción decide trabajo, publica a ADO ni transiciona work items (regla 11).
- [ ] Tests por archivo con el python del `.venv` (no suite completa); `tsc` limpio en frontend.
- [ ] KPIs K1-K5 expuestos por `harness_health`/`api/diag.py` en la DiagnosticsPage existente.

---

## 11. Decisiones abiertas (requieren confirmación del operador antes de implementar)

1. **Umbral default de inyección:** `HARNESS_LEARNING_INJECT_MIN_CONF=0.5` y `MAX=5` — ¿valores razonables o más conservadores? (Recomendado: empezar conservador, subir con evidencia de K3/K4.)
2. **Granularidad de `ticket_kind`:** heurística stdlib `bug/feature/task/unknown` — ¿suficiente o se requiere un eje más fino? (Recomendado: empezar grueso; refinar solo si K2 lo exige.)
3. **Política de decay:** half-life de 30 días — ¿adecuada al ritmo de los proyectos? (Recomendado: 30 días; parametrizable si hace falta.)
