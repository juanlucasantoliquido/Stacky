# 34 — Plan Client Profile Efectivo y Sin Fricción: máxima calidad del output con el mínimo esfuerzo del operador

**Fecha:** 2026-06-16
**Estado:** PROPUESTO (ningún ítem implementado)
**Autor:** StackyArchitectaUltraEficientCode
**Predecesores directos (Client Profile):** `docs/16_PLAN_GENERALIZACION_AGENTES_MULTI_CLIENTE.md` (creó el sustrato: schema, store, inyección), `docs/17_PLAN_AUTOLLENADO_RUTAS_CLIENT_PROFILE.md` (prefill de layout + `resolve_layout_paths`), `docs/18_FIX_DEVELOPER_CLIENT_PROFILE_COMMENT_HTML.md`.
**Predecesores de método (formato/flags/jueces/KPIs):** `docs/29` (juicio semántico + criterios), `docs/30` (verificación determinista contra la realidad), `docs/31` (verificación ejecutable), `docs/32` (contrato de aceptación), `docs/33` (flags 100% configurables por UI).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia `file:line`, diseño con archivos exactos, flag (OFF por default), criterio de aceptación y test/gate.

**Tesis (innegociable):** el Client Profile hoy es un **formulario de ~35 campos que el operador llena a mano**, cuyo "default" está contaminado con valores de un cliente concreto (RIPLEY/RS), que se inyecta **completo y sin selección** a todos los agentes, y cuya única validación es de **tipo + secretos**. El salto del Plan 34 es invertir esa relación esfuerzo/valor: el perfil se **infiere** de las señales que ya existen (repo, ADO, docs, ejecuciones, memoria), el operador **confirma** en vez de **redactar**, los jueces deterministas detectan campos faltantes/ambiguos/contradictorios **antes** de gastar un run, y la inyección se vuelve **dirigida por agente y anclada a la realidad**. Menos trabajo del humano, más calidad del entregable. **Lo barato (el esfuerzo) baja; lo valioso (la calidad y la personalización) sube.** No están en conflicto.

**"Mínimo esfuerzo" NO significa "autónomo" (frontera dura, regla 11 — ver [[human-in-the-loop-fundamental]]):** la inferencia **propone**, nunca **fija**. Cada valor inferido o aprendido se le muestra al operador con su **procedencia** y su **confianza**; el operador confirma, corrige o descarta. Stacky no decide la identidad del cliente por su cuenta, no publica nada, no re-escribe un perfil que el humano ajustó a propósito. El TRABAJO se vuelve invisible (confirmar 3 cosas en vez de redactar 35); la DECISIÓN sigue siendo del humano.

**Calidad nunca se sacrifica (segundo eje):** todos los mecanismos son **aditivos** — o evitan gastar un run con un perfil contradictorio (no hay output que degradar), o **agregan una señal** (procedencia, frescura, validación de existencia) que solo puede mejorar el entregable. La inyección dirigida por agente **nunca** quita un campo que ese agente consume: el registro `consumed_by` (34.A4) es la fuente de verdad y el default conservador es el perfil completo.

---

## 1. Relación con los planes previos (qué reusa, qué NO re-implementa)

- **REUSA, no re-implementa:** el store y la validación (`services/client_profile.py`), los templates embebidos (`services/client_profile_default_templates.py`), el seam único de armado del bloque (`context_enrichment.build_client_profile_block`), el chequeo de rutas (`resolve_layout_paths`), el ranking/budget de contexto (`_BLOCK_PRIORITY`, `_HIGH_PRIORITY_THRESHOLD`), y el panel de flags genérico del doc 33 (`HarnessFlagsPanel`).
- **Frontera con el doc 30 (verdad contra la realidad):** el 30 verifica **el run** (precondiciones, referencias del output, escritura efectiva). El 34 verifica **el perfil** (que los campos existan, sean coherentes entre sí y contra el repo/ADO) **antes** de que alimenten al run. El 34 **alimenta** el preflight del 30 con un predicado nuevo ("perfil coherente"); no re-implementa el gate de run.
- **Frontera con el doc 29/31/32 (calidad del entregable):** esos planes juzgan **el output**. El 34 mejora **el insumo** (el contexto que entra). Un perfil más rico y mejor inyectado sube el techo de calidad que esos gates miden; el 34 usa sus KPIs (pass-rate del gate de aceptación, tasa de repair) como **medida de su propio impacto**, sin tocar su lógica.
- **Frontera con el doc 33 (flags por UI):** todo flag nuevo del 34 entra en `config.py` + `FLAG_REGISTRY` y aparece solo en `HarnessFlagsPanel`, sin tocar el frontend de flags.
- **SUBSUME / REEMPLAZA:** nada. Los ítems pendientes de 28-32 siguen vigentes.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es auto-intake ni autonomía.** El perfil se infiere y se propone; el operador confirma. Stacky nunca "adopta" un cliente solo.
2. **No agrega RBAC ni multi-usuario.** Mono-operador sin auth real (`current_user` es un header sin validar — ver [[stacky-no-auth-substrate]]). El perfil es por-proyecto, no por-usuario.
3. **No mete secretos en el perfil.** La regla del doc 16 sigue: passwords/PAT viven cifrados fuera (`auth/db_readonly.json`); el detector de secretos (`client_profile.py:167-182`) se mantiene y se endurece, no se relaja.
4. **No rompe el contrato del schema actual.** Toda adición es **aditiva** con `schema_version` bump + migrador; los `config.json` existentes siguen cargando.
5. **No borra campos a ciegas.** Una eliminación solo procede tras la auditoría `consumed_by` (34.A4) que pruebe que ningún agente lo lee; mientras tanto el campo se marca *deprecated*, no se elimina.
6. **No introduce deps nuevas (npm/py) ni FTS5.** Inferencia con stdlib + los seams de lectura ya existentes (workspace scan, caché de lectura ADO del 27/I3.2, memoria).
7. **No cambia QUÉ/CUÁNDO se publica a ADO.** La inferencia desde ADO es **solo lectura de existencia/estado**.

---

## 3. Diagnóstico: dónde el Client Profile cuesta esfuerzo y no rinde calidad (con evidencia)

| # | Debilidad | Evidencia (`file:line`) | Impacto |
|---|---|---|---|
| **D1** | **Carga 100% manual: ~35 campos, cero inferencia.** El editor expone 8 secciones con ~35 inputs (identidad, 5 rutas de layout + extensiones + capas, 4 de lenguaje, 8 de BD, 5 de build, 4 de convenciones, 3 de docs, 3 roles × 4 de la máquina de estados). Nada lee el repo/ADO/docs para prellenar; `resolve_layout_paths` solo **verifica** existencia, nunca **descubre**. | `ClientProfileEditor.tsx:706-902`; `client_profile.py:428-448` | Configurar "desde cero" es un trabajo de 30-40 decisiones manuales propenso a typos. El operador lo posterga o lo deja en defaults → perfil pobre → output genérico. |
| **D2** | **El default "genérico" está contaminado con un cliente concreto.** El template `azure_devops` —que se usa como fallback para cualquier proyecto sin configurar— trae valores RS/RIPLEY hardcodeados: `ridioma_helper: "RSFac.Idioma"`, `string_sanitizer: "cFormat.StToBD()"`, `ridioma_message_const: "coMens.m{id}"`, `table_prefix: "R"`, `languages_in_ridioma: ["ESP","ENG","POR"]`, capas `RSBus (BLL)/RSDalc (DAL)`, y un `msbuild_path` fijo a VS2022 Community. | `client_profile_default_templates.py:40,44,46,57,69-72,63` | Un cliente que NO sea RS recibe convenciones ajenas como si fueran suyas. El "default" miente: el agente arranca con datos plausibles pero **incorrectos**, peor que un campo vacío honesto. |
| **D3** | **Validación anémica: tipo + secretos, sin semántica ni completitud.** `validate_client_profile` solo chequea tipos de sección, detecta secretos y avisa de secciones requeridas **como warning** (no error): un perfil casi vacío valida `ok=True`. No hay detección de contradicciones (p. ej. `language.primary=csharp` con `build.tool=maven`), ni coherencia BD (`type` vs `connection_kind`), ni verificación de que los estados del tracker existan en el board real, ni scoring de completitud. | `client_profile.py:185-242` (required→warning `:213-215`) | Perfiles incompletos o auto-contradictorios pasan silenciosamente y degradan el output sin que nadie lo note hasta ver el entregable. |
| **D4** | **Inyección sin selección: dump completo a todos los agentes.** `build_client_profile_block` serializa el perfil **entero** (`json.dumps(..., indent=2, sort_keys=True)`) en un solo bloque idéntico para FunctionalAnalyst, TechnicalAnalyst y Developer. Además `merge_with_defaults` rellena con el default del tracker **incluyendo** BD y campos vacíos (`server:""`, `product_name:""`), así que se inyecta ruido. | `context_enrichment.py:529,550`; `client_profile.py:373-381` | El FunctionalAnalyst recibe `msbuild_path`/`naming_conventions` que no usa; el Developer recibe lo mismo que el funcional. Tokens gastados en campos irrelevantes por agente + dilución de la señal. |
| **D5** | **Prioridad 95 = nunca se poda ni se deduplica, a cualquier tamaño.** El bloque `client-profile` tiene prioridad 95, por encima del umbral 75, así que el budget de contexto **nunca** lo recorta y el dedup **nunca** le quita líneas, aunque la mitad sean campos vacíos o irrelevantes para ese agente. | `context_enrichment.py:319,200,261-269` | Un perfil obeso (extensiones, catálogos, capas) ocupa presupuesto fijo en todo run, desplazando contexto que sí importa (comentarios, similares). |
| **D6** | **Sin frescura ni procedencia.** El perfil no tiene `updated_at` por campo ni a nivel raíz, ni marca de origen (manual vs default vs inferido), ni confianza. El único evento es `record_event(... fields_present ...)` al guardar, que no dice cuándo se tocó cada campo ni si sigue siendo cierto. | `api/client_profile.py:144-154`; templates sin timestamp | Imposible distinguir un dato confirmado por el operador de un default copiado; imposible detectar campos rancios (una ruta que el repo movió hace meses). |
| **D7** | **`client_type` no existe: tracker ≠ stack.** El único eje de template es el tracker (ADO/Jira/Mantis), pero las convenciones reales (lenguaje, capas, helpers, naming) dependen del **stack del cliente**, no del tracker. Hoy ambos se mezclan en un template por-tracker. | `client_profile_default_templates.py:264-268` (mapa solo por tracker) | No se puede ofrecer "plantilla por tipo de cliente" (p. ej. *RS WebForms*, *Java/Spring*, *.NET moderno*) sin duplicar todo el bloque del tracker. La D2 es consecuencia de esto. |
| **D8** | **Aprendizaje cero: lo que el run descubre no vuelve al perfil.** Un run puede descubrir el `.sln` real, la ruta efectiva de `online`, o el estado real del board; nada de eso se propone como corrección del perfil. El operador repite el error en cada proyecto. | (ausencia) `post_run.py` / `output_watcher.py` no escriben sugerencias al perfil | El perfil no mejora con el uso; el costo de mantenerlo correcto recae siempre en el humano. |

**Lectura central:** el sustrato de almacenamiento, validación-de-tipo, inyección y verificación-de-rutas **ya existe y es sólido**. El valor del 34 NO es reescribirlo: es **(a) limpiar el default**, **(b) inferir en vez de pedir**, **(c) validar con jueces deterministas**, **(d) inyectar dirigido y fresco**, y **(e) aprender del uso** — todo con flags OFF y retro-compat byte-idéntica cuando están OFF.

---

## 4. Objetivos medibles y KPIs

| KPI | Definición | Baseline (hoy) | Objetivo |
|---|---|---|---|
| **K1 — % de campos autoinferidos** | campos con valor propuesto por inferencia / campos del schema efectivo, en un proyecto con repo + ADO conectados | 0% | ≥ 70% |
| **K2 — Decisiones del operador hasta "perfil usable"** | nº de confirmaciones/ediciones para alcanzar un perfil que pasa los jueces deterministas | ~35 (un input por campo) | ≤ 3 |
| **K3 — Δ calidad del output** | pass-rate del gate de aceptación (doc 32) y tasa de repair (doc 31) **con perfil rico** vs **default sin configurar**, sobre el golden-set | n/d | pass-rate +; repair − (medible y positivo) |
| **K4 — Coherencia pre-run** | % de runs cuyo perfil pasa los jueces deterministas (C2) sin contradicción crítica | n/d | ≥ 95%; contradicciones atrapadas antes de gastar el run |
| **K5 — Frescura** | % de campos con `updated_at` < 90 días; nº de campos marcados *stale* detectados por el barredor (E2) | n/d (sin timestamp) | reportado y decreciente |
| **K6 — Eficiencia de inyección** | tokens del bloque `client-profile` **por agente** (vista dirigida) vs dump completo | dump completo a los 3 agentes | −30% a −50% por agente sin perder campos consumidos |

Todos los KPIs se exponen en la **DiagnosticsPage existente** (sin UI nueva de métricas), vía el seam de telemetría del harness (H8 / `harness_health`), igual que hicieron 30-32.

---

## 5. Esquema propuesto del Client Profile (mantener / agregar / eliminar)

**Principio:** el schema efectivo se define por **quién lo consume** (registro `consumed_by`, 34.A4), no por "qué se podría guardar". Un campo que ningún agente lee no suma completitud: suma ruido.

### 5.1 MANTENER (núcleo consumido, evidencia de uso en agentes)
- `code_layout.{online_path, batch_path, db_scripts_path, lib_path, test_path, file_extensions, architecture_layers}` — rutas y stack que orientan a todos los agentes.
- `language.{primary, ticket_token_pattern, comment_traceability}` — trazabilidad y lenguaje primario (Developer/Technical).
- `tracker_state_machine.{functional, technical, developer}` — transiciones; consumido por el flujo de tickets.
- `database.{type, dml_policy, connection_kind, readonly_auth_ref, naming_conventions}` — política y forma de BD (Technical/Developer).
- `build.{tool, command|msbuild_path, configuration, online_solutions, batch_proj_glob}` — cómo compilar/validar (Developer; insumo del doc 31).
- `docs_indexes.{technical_master, functional_online, functional_batch}` — punto de entrada a la doc viva.
- `terminology.{product_name, client_label, domain_glossary_ref}` — identidad y glosario.
- `extensions` (free dict) — extensibilidad por cliente.

### 5.2 AGREGAR (todo aditivo, `schema_version` 1 → 2 + migrador)
- **`client_type`** (string) — id de plantilla de **stack** (p. ej. `rs_webforms`, `dotnet_modern`, `java_spring`, `generic`), ortogonal al tracker (resuelve **D7**).
- **`_meta`** — metadatos por-campo y a nivel raíz, **sin tocar los valores**:
  - `_meta.updated_at` (raíz) + `_meta.fields.<path>.{source, confidence, updated_at}`.
  - `source ∈ {operator, default, inferred:repo, inferred:ado, inferred:docs, inferred:memory, learned:run}`.
  - `confidence ∈ [0,1]`. Resuelve **D6** y habilita scoring (C1) y frescura (E2).
- **`_inference`** (raíz, efímero) — última propuesta de inferencia pendiente de confirmar (no persiste como verdad hasta que el operador la acepta). Resuelve **D1** sin violar regla 11.

> `_meta` y `_inference` son **aditivos y opcionales**: un perfil sin ellos es válido (migrador los crea vacíos). La validación de secretos (`client_profile.py:167-182`) se extiende para que `_meta`/`_inference` no puedan transportar secretos.

### 5.3 ELIMINAR del default genérico / RELOCALIZAR a `client_type=rs_webforms`
Mover **fuera** del template `azure_devops` (que debe quedar **neutral**) todos los valores RS/RIPLEY (resuelve **D2**):
- `conventions.ridioma_helper`, `conventions.ridioma_message_const`, `conventions.string_sanitizer`, `conventions.error_helpers`.
- `language.languages_in_ridioma` (los 3 idiomas concretos).
- `code_layout.architecture_layers` con `RSBus/RSDalc`.
- `database.naming_conventions.table_prefix = "R"`.
- `build.msbuild_path` fijo a VS2022 Community.
El `azure_devops` neutral deja esos campos **vacíos** (honestos), y la plantilla `rs_webforms` los reintroduce. Así el default no miente y RS sigue teniendo su perfil con un click (34.F2).

### 5.4 CANDIDATOS A *DEPRECATED* (eliminar solo tras auditoría `consumed_by`)
- `database.readonly_user_hint` — duplicado con el `user` de `auth/db_readonly.json`; candidato a derivarse, no a guardarse.
- `database.naming_conventions.column_prefix_len` — bajo valor de señal; confirmar si algún agente lo usa.
- Cualquier campo que la auditoría 34.A4 marque con `consumed_by = []`.
> Mientras `consumed_by` no pruebe que nadie lo lee, **se marca deprecated en `_meta`, no se borra** (regla anti-scope 5).

---

## FASE A — Esquema efectivo y honesto (default neutral + procedencia + mapa de consumo)

### 34.A1 — Neutralizar el default `azure_devops` y aislar lo RS en una plantilla de stack
**Qué:** separar **tracker** (estados) de **stack** (convenciones). El template `azure_devops` queda con estados + estructura neutral; los valores RS migran a una plantilla `client_type=rs_webforms`.
**Por qué:** D2/D7 — el default miente y mezcla ejes.
**Cómo:** en `client_profile_default_templates.py`, vaciar los campos RS del `AZURE_DEVOPS` (5.3) y crear `STACK_TEMPLATES = {"rs_webforms": {...}, "generic": {...}}`. El armado de un perfil nuevo compone `tracker_template ⊕ stack_template`.
**Flag:** `STACKY_CLIENT_PROFILE_NEUTRAL_DEFAULT_ENABLED` (OFF). OFF → se devuelve el `AZURE_DEVOPS` actual byte-idéntico (retro-compat para proyectos RS ya sembrados).
**Test/gate:** `test_client_profile.py::test_neutral_default_has_no_rs_specifics` (con flag ON, el default no contiene `RSFac`/`cFormat`/`table_prefix=R`); el test de drift JSON↔embedded existente sigue verde; `test_stack_template_rs_webforms_restores_rs_values`.

### 34.A2 — Metadatos `_meta` (procedencia, confianza, frescura) — aditivo, schema v2
**Qué:** agregar `_meta` por-campo y raíz; migrador v1→v2 que crea `_meta` vacío para perfiles existentes.
**Por qué:** D6 — sin procedencia no hay scoring, frescura ni aprendizaje.
**Cómo:** `SCHEMA_VERSION = 2`; `validate_client_profile` acepta `_meta`/`_inference` y los excluye del chequeo de secciones; extender `_contains_secret_keys` para barrerlos igual. Helper `stamp_meta(profile, path, source, confidence)`.
**Flag:** sin flag de runtime (es estructura aditiva inerte); gobernado por `schema_version`. Un perfil v1 sigue cargando.
**Test/gate:** `test_client_profile.py::test_migrate_v1_to_v2_adds_empty_meta`, `::test_meta_cannot_carry_secrets`, `::test_v1_profile_still_valid`.

### 34.A3 — Migrador y compatibilidad hacia atrás
**Qué:** `migrate_client_profile(profile)` idempotente que lleva cualquier perfil a v2 sin perder datos.
**Por qué:** anti-scope 4 — ningún `config.json` existente debe romperse.
**Cómo:** se invoca en `load_effective_client_profile` (`client_profile.py:296`) y en el PUT antes de validar. Idempotente: migrar dos veces = mismo resultado.
**Flag:** —
**Test/gate:** `::test_migrate_idempotent`, `::test_migrate_preserves_unknown_keys` (incl. `extensions`).

### 34.A4 — Registro `consumed_by`: qué agente lee cada campo (fuente de verdad de scoring e inyección dirigida)
**Qué:** tabla declarativa `FIELD_CONSUMERS: dict[path, set[agent_type]]` que mapea cada campo del schema a los agentes que lo consumen.
**Por qué:** habilita completitud **útil** (C1), inyección **dirigida** (D1 de la Fase D) y la auditoría de *deprecated* (5.4). Sin esto, "completitud" e "inyección por agente" serían adivinanza.
**Cómo:** nuevo `services/client_profile_consumption.py` con el mapa + un test que lo cruza contra los `.agent.md` (grep de los tokens del perfil en `FunctionalAnalyst`, `TechnicalAnalyst.v2`, `Developer`). Campos sin consumidor → reportados como candidatos *deprecated*.
**Flag:** —
**Test/gate:** `test_client_profile_consumption.py::test_every_consumed_field_appears_in_some_agent`, `::test_orphan_fields_are_flagged`.

---

## FASE B — Inferencia y defaults inteligentes (minimizar la carga manual)

> Todos los inferidores son **propuestas con procedencia**. Escriben en `_inference`, **no** en el perfil. El operador acepta en la UI (F3). Flag maestro `STACKY_CLIENT_PROFILE_INFERENCE_ENABLED` (OFF) + flag por-fuente.

### 34.B1 — Inferencia desde el repo (layout, lenguaje, build, soluciones)
**Qué:** escanear `workspace_root` para proponer `code_layout.*`, `language.primary` (por extensiones dominantes), `build.online_solutions` (`*.sln`), `build.batch_proj_glob` (`*.csproj`), `code_layout.file_extensions`.
**Por qué:** D1 — la mayoría de estos campos son **observables**, no opinables.
**Cómo:** `services/client_profile_infer_repo.py`, stdlib (`os.walk`/`glob`) con caps de profundidad y de archivos; reusa `resolve_layout_paths` para confirmar existencia. Cada propuesta lleva `source="inferred:repo"`, `confidence` por fuerza de la señal.
**Flag:** `STACKY_CLIENT_PROFILE_INFER_REPO_ENABLED` (OFF).
**Test/gate:** `test_client_profile_infer_repo.py` con un árbol fixture: detecta `.sln`, deriva `primary=csharp`, propone rutas existentes; nunca propone una ruta inexistente.

### 34.B2 — Inferencia desde ADO (máquina de estados real del board)
**Qué:** proponer `tracker_state_machine.*` a partir de los estados **reales** del board del proyecto (solo lectura).
**Por qué:** D3 — los estados del template pueden no coincidir con el board, y eso rompe transiciones silenciosamente.
**Cómo:** `services/client_profile_infer_ado.py` usando la **caché de lectura ADO existente** (27/I3.2), sin caminos de escritura. Mapea estados del board a los roles funcional/técnico/developer con heurística + confirmación.
**Flag:** `STACKY_CLIENT_PROFILE_INFER_ADO_ENABLED` (OFF).
**Test/gate:** `test_client_profile_infer_ado.py` con board fake: propone estados que existen; marca como ambiguo lo que no mapea limpio (no inventa).

### 34.B3 — Inferencia desde docs (descubrir índices)
**Qué:** proponer `docs_indexes.*` buscando índices conocidos (`*INDICE*`, `*INDEX*`, `00_*`) bajo las rutas de doc del repo.
**Por qué:** D1 — descubrir, no pedir.
**Cómo:** `client_profile_infer_docs.py`, glob acotado; `source="inferred:docs"`.
**Flag:** `STACKY_CLIENT_PROFILE_INFER_DOCS_ENABLED` (OFF).
**Test/gate:** fixture con árbol de docs → propone los índices reales; ninguno inexistente.

### 34.B4 — Inferencia desde memoria/ejecuciones (convenciones recurrentes)
**Qué:** proponer `conventions.*`/`terminology.*` a partir de patrones recurrentes en outputs aprobados y memoria del proyecto (p. ej. el helper de i18n que aparece en N entregables).
**Por qué:** D8 — lo aprendido debe poder sembrar el perfil.
**Cómo:** `client_profile_infer_memory.py` leyendo el store de memoria + outputs aprobados (seam del doc 29/few-shot). Señales débiles → `confidence` baja → no se auto-confirman.
**Flag:** `STACKY_CLIENT_PROFILE_INFER_MEMORY_ENABLED` (OFF).
**Test/gate:** fixture con N outputs citando `RSFac.Idioma` → lo propone con `source="inferred:memory"`; con 1 sola aparición → no lo propone (umbral).

### 34.B5 — Orquestador de inferencia (compone la propuesta, no la fija)
**Qué:** `infer_client_profile(project_name) -> InferenceResult` que corre los inferidores habilitados, fusiona por confianza (operator > learned:run > inferred:repo/ado/docs > inferred:memory > default), y deja todo en `_inference`.
**Por qué:** un solo punto de orquestación, una sola propuesta coherente para la UI.
**Cómo:** `services/client_profile_inference.py`; **best-effort** (cualquier inferidor que falle se omite con warning, igual que `build_client_profile_block`). No persiste en el perfil: solo `_inference`.
**Flag:** `STACKY_CLIENT_PROFILE_INFERENCE_ENABLED` (OFF) — gate maestro.
**Test/gate:** `test_client_profile_inference.py::test_merge_respects_confidence_order`, `::test_failure_in_one_source_is_isolated`, `::test_inference_never_writes_profile`.

---

## FASE C — Validación, jueces deterministas y completitud útil

### 34.C1 — Scoring de completitud **ponderado por consumo** (no por completar)
**Qué:** `score_completeness(profile) -> {score, missing_high_value, gratuitous}` donde cada campo pesa por `consumed_by` (A4) y por criticidad para la calidad.
**Por qué:** D3 — un score plano premia llenar campos que nadie lee. El score útil mide **cobertura de lo que cambia el output**.
**Cómo:** `services/client_profile_quality.py`; pesos derivados de `FIELD_CONSUMERS`; reporta los **3 campos faltantes de mayor impacto** (eso alimenta K2: el operador confirma solo lo que mueve la aguja).
**Flag:** `STACKY_CLIENT_PROFILE_COMPLETENESS_ENABLED` (OFF, solo afecta lo que reporta el endpoint/UI).
**Test/gate:** `test_client_profile_quality.py::test_score_weights_by_consumption` (un campo high-value faltante baja más el score que tres irrelevantes), `::test_reports_top3_missing`.

### 34.C2 — Jueces deterministas de consistencia (contradicciones, coherencia, existencia)
**Qué:** batería de chequeos **sin LLM** que detectan:
- contradicciones de stack (`language.primary` vs `build.tool`; `database.type` vs `connection_kind`),
- estados del tracker que no existen en el board real (cruza B2/caché ADO),
- rutas de `code_layout`/`docs_indexes` inexistentes (reusa `resolve_layout_paths`),
- `online_solutions`/globs que no matchean nada,
- `_meta` incoherente (confianza fuera de rango, source desconocido).
**Por qué:** D3 — hoy un perfil auto-contradictorio valida `ok=True`.
**Cómo:** `services/client_profile_judges.py` → `list[Finding{severity, path, message}]`. Determinista, milisegundos, cero costo de inferencia (eje del doc 30 aplicado al perfil).
**Flag:** `STACKY_CLIENT_PROFILE_JUDGES_ENABLED` (OFF).
**Test/gate:** `test_client_profile_judges.py` con perfiles fixture: csharp+maven → finding crítico; ruta inexistente → finding; perfil RS coherente → 0 findings.

### 34.C3 — Gate de coherencia pre-run (degrada con razón clara, no gasta)
**Qué:** antes de lanzar un run, si C2 reporta una contradicción **crítica** o falta un campo **crítico** que ese agente consume (A4), bloquear con razón explícita en vez de gastar el run; las severidades menores pasan como **warning anotado** en el bloque.
**Por qué:** D3 + alineación con el preflight del doc 30 — no gastes un run condenado por un perfil roto.
**Cómo:** alimenta el predicado "perfil coherente" al gate de precondiciones del 30/G0.1 (no crea un gate nuevo paralelo). Solo bloquea en crítico; nunca en ambigüedad menor.
**Flag:** `STACKY_CLIENT_PROFILE_PRERUN_GATE_ENABLED` (OFF).
**Por qué NO viola regla 11:** no decide trabajo ni publica; verifica una precondición determinista de un run que el operador ya lanzó, y le devuelve una razón accionable. El operador decide si corrige el perfil o fuerza el run.
**Test/gate:** `test_client_profile_prerun_gate.py::test_critical_contradiction_blocks_with_reason`, `::test_minor_finding_warns_not_blocks`, `::test_flag_off_is_noop`.

---

## FASE D — Uso activo en ejecución (inyección dirigida + frescura + prioridad)

### 34.D1 — Vistas del perfil por agente (proyectar solo lo que el agente consume)
**Qué:** `project_profile_for_agent(profile, agent_type)` que usa `FIELD_CONSUMERS` (A4) para inyectar **solo** los campos que ese agente lee.
**Por qué:** D4/D5 — el FunctionalAnalyst no necesita `msbuild_path`; el dump completo diluye y gasta tokens.
**Cómo:** en `build_client_profile_block` (`context_enrichment.py:478`), con flag ON, filtrar por la vista del `agent_type`; con flag OFF, dump completo byte-idéntico. **Default conservador:** si un campo no está mapeado en A4, se incluye (no se pierde nada por omisión).
**Flag:** `STACKY_CLIENT_PROFILE_SCOPED_INJECTION_ENABLED` (OFF).
**Test/gate:** `test_context_enrichment_client_profile.py::test_scoped_view_drops_only_unconsumed`, `::test_unmapped_field_is_kept`, `::test_flag_off_is_full_dump`.

### 34.D2 — Frescura y prioridad: anotar/depriorizar lo rancio, no romper
**Qué:** usar `_meta.updated_at` para **anotar** campos rancios (> umbral) en el bloque ("⚠ valor sin confirmar desde AAAA-MM-DD") y, bajo presión de budget, permitir que las **subsecciones de baja confianza** sean podables aunque el bloque siga en prioridad alta.
**Por qué:** D5/D6 — hoy el bloque entero es intocable a cualquier tamaño; lo confirmado y fresco debe pesar más que lo viejo y dudoso.
**Cómo:** sin bajar la prioridad global del bloque (sigue siendo fuente de verdad), separar las líneas confirmadas (nunca podables) de las inferidas-no-confirmadas (podables primero) dentro del bloque. Reusa el mecanismo de budget/dedup existente.
**Flag:** `STACKY_CLIENT_PROFILE_FRESHNESS_ANNOTATION_ENABLED` (OFF).
**Test/gate:** `::test_stale_field_is_annotated`, `::test_low_confidence_lines_pruned_first_under_budget`.

### 34.D3 — Resolución de referencias en tiempo de inyección (anclar a la realidad)
**Qué:** al armar el bloque, validar rutas/estados contra el repo/ADO (reusando C2) y **anotar** los que no resuelven ("ruta no encontrada en el workspace") en vez de inyectarlos como verdad.
**Por qué:** D3 aplicado al runtime — evita que el agente confíe en una ruta que ya no existe.
**Cómo:** `build_client_profile_block` llama a los jueces de existencia (C2) en modo anotación. Best-effort, sin romper si falla.
**Flag:** `STACKY_CLIENT_PROFILE_INJECT_GROUNDING_ENABLED` (OFF).
**Test/gate:** `::test_missing_path_is_annotated_not_asserted`, `::test_flag_off_is_byte_identical`.

---

## FASE E — Autocorrección y aprendizaje desde el uso

### 34.E1 — Detector de drift post-run → parche sugerido (operador aprueba)
**Qué:** tras un run, si el output reveló un valor más verdadero que el del perfil (p. ej. el `.sln` real, una ruta efectiva, un estado del board), generar un **parche sugerido** con `source="learned:run"` y confianza, **pendiente de aprobación**.
**Por qué:** D8 — el perfil debe mejorar con el uso sin trabajo extra del humano.
**Cómo:** seam en `harness/post_run.py` (no escribe el perfil; deja el parche en una cola de sugerencias que la UI muestra). Reusa los hallazgos de existencia del doc 30 si están disponibles.
**Flag:** `STACKY_CLIENT_PROFILE_LEARN_FROM_RUNS_ENABLED` (OFF).
**Por qué NO viola regla 11:** propone, no aplica. El operador confirma el parche; nunca se reescribe un valor que el humano fijó.
**Test/gate:** `test_client_profile_learn.py::test_drift_produces_suggestion_not_write`, `::test_operator_confirmed_field_is_not_overwritten`.

### 34.E2 — Barredor de frescura (staleness sweeper)
**Qué:** job liviano que marca campos con `updated_at` > umbral como *stale* y los reporta (no los borra ni reconfirma solo).
**Por qué:** D6/K5 — visibilizar lo rancio para que el operador lo revise.
**Cómo:** función pura sobre `_meta`, expuesta vía endpoint de salud del perfil; sin timers nuevos (se evalúa on-read, como el resto).
**Flag:** `STACKY_CLIENT_PROFILE_STALENESS_REPORT_ENABLED` (OFF).
**Test/gate:** `::test_old_field_flagged_stale`, `::test_fresh_field_not_flagged`.

---

## FASE F — Onboarding guiado + plantillas + UI de confirmación (alineado a doc 33)

### 34.F1 — Asistente "Perfil en 3 pasos"
**Qué:** wizard de configuración desde cero: **(1)** elegir `client_type` (plantilla de stack) → **(2)** Stacky corre la inferencia (B5) y muestra la propuesta con procedencia → **(3)** el operador confirma/corrige solo los campos **críticos y ambiguos** que marcan C1/C2. Fin.
**Por qué:** K2 — pasar de ~35 inputs a ≤ 3 decisiones.
**Cómo:** nuevo flujo en `ClientProfileEditor.tsx` (o sub-componente `ClientProfileWizard.tsx`) que consume los endpoints de inferencia/validación; degrada con gracia si los flags están OFF (cae al formulario actual). Sin tests vitest obligatorios (no instalado): se exige que compile con `tsc` y que el formulario actual siga funcionando.
**Flag:** gobernado por `STACKY_CLIENT_PROFILE_INFERENCE_ENABLED`; sin él, el wizard no aparece.
**Test/gate:** `tsc` limpio; el editor existente intacto con flags OFF.

### 34.F2 — Plantillas por tipo de cliente (`client_type`)
**Qué:** materializar `STACK_TEMPLATES` (A1) y un botón "Aplicar plantilla de stack" análogo al "Aplicar template default" actual.
**Por qué:** D7 — RS se reconfigura con un click; clientes nuevos parten de `generic` u otra plantilla.
**Cómo:** endpoint `GET /api/client-profile/stack-template?client_type=...` (espejo del `client-profile/default` existente `api/client_profile.py:79`); botón en el editor.
**Flag:** —
**Test/gate:** `test_client_profile_endpoints.py::test_stack_template_endpoint_returns_rs_webforms`.

### 34.F3 — UI de confirmación de inferidos/sugeridos (diff, no formulario)
**Qué:** panel que muestra cada valor inferido/aprendido como **diff** (valor propuesto vs actual) con su procedencia y confianza, y botones aceptar/editar/descartar por campo.
**Por qué:** regla 11 — la inferencia se **confirma**, no se aplica sola; y reduce K2 a "revisar una lista corta".
**Cómo:** consume `_inference` (B5) y la cola de sugerencias (E1); al aceptar, hace PUT con `source` actualizado a `operator`/`learned:run` confirmado. Reusa el patrón de procedencia.
**Flag:** parte del flujo de inferencia (maestro B5).
**Test/gate:** `tsc` limpio; aceptar un campo persiste con `source=operator`; descartar no toca el perfil.

### 34.F4 — Flags del 34 visibles en `HarnessFlagsPanel` (doc 33)
**Qué:** registrar todos los flags `STACKY_CLIENT_PROFILE_*` en `FLAG_REGISTRY` con label/description/grupo `client_profile`.
**Por qué:** doc 33 — todo flag se configura desde UI sin tocar frontend.
**Cómo:** agregar specs al registry + líneas en `.env.example`. El panel genérico los renderiza solo.
**Test/gate:** `test_harness_flags.py::test_client_profile_flags_registered`; `.env.example` documenta cada key.

---

## 6. Mecanismos transversales (resumen)

- **Inferencia → propuesta → confirmación:** B1-B5 escriben en `_inference`; F3 confirma; nada se fija sin el operador (regla 11).
- **Procedencia y confianza:** `_meta` (A2) es el sustrato de scoring (C1), gate (C3), frescura (D2/E2) y aprendizaje (E1).
- **Jueces deterministas (cero LLM):** C2 detecta contradicciones/coherencia/existencia; C3 los gatea pre-run; D3 los usa para anotar en runtime. Mismo eje barato del doc 30.
- **Inyección dirigida y fresca:** D1 proyecta por agente con `consumed_by`; D2 prioriza lo confirmado/fresco; D3 ancla a la realidad. Default conservador = no perder campos.
- **Aprendizaje sin fricción:** E1 convierte hallazgos de run en parches sugeridos; E2 marca lo rancio. Siempre human-approved.

---

## 7. Plan de medición y rollout

**Medición (sin UI nueva de métricas):** K1-K6 se calculan en backend y se exponen por el seam de `harness_health`/telemetría (H8), igual que 30-32; la DiagnosticsPage existente suma una tarjeta de "salud del Client Profile" (completitud, findings de jueces, campos stale, % inferido). K3 se mide corriendo el golden-set (docs 31/32) con perfil rico vs default y comparando pass-rate/repair.

**Rollout por flags (todos OFF por default, configurables desde `HarnessFlagsPanel` — doc 33):**
1. **A1-A4 + F2** (default neutral + `_meta` + migrador + `consumed_by` + plantillas de stack). Riesgo bajo, retro-compat por flag/`schema_version`. Habilita todo lo demás.
2. **C1-C2** (scoring + jueces) en modo **reporte** (no gatea). Observar K1/K4 sin afectar runs.
3. **B1-B5 + F1/F3** (inferencia + wizard + confirmación). Medir K1/K2.
4. **D1-D3** (inyección dirigida + frescura + grounding). Medir K6 y K3.
5. **C3** (gate pre-run) y **E1/E2** (aprendizaje) al final, cuando los jueces y la inferencia estén calibrados. Medir K3/K4/K5.

**Restricciones vinculantes (idénticas a 29-33, no relitigar):** flag nuevo → `config.py` + `FLAG_REGISTRY` en el mismo PR, default OFF, retro-compat byte-idéntica con flag OFF; sin secretos en el perfil; "solo Stacky escribe en ADO" (la inferencia ADO es solo lectura); mono-operador sin RBAC; claves de metadata existentes son contrato (agregar, nunca renombrar); suite contaminada → validar **por archivo** con el python del `.venv` (pin pywin32==306 roto en 3.13 — ver [[stacky-backend-dev-test-env]]); vitest frontend no instalado (UI: solo `tsc` + degradación con gracia); sin deps npm/py nuevas; sin FTS5.

---

## 8. Riesgos, mitigaciones y decisiones abiertas

| Riesgo | Mitigación |
|---|---|
| **Inferencia incorrecta se toma como verdad.** | Nunca se aplica sola (F3 confirma); cada valor lleva procedencia + confianza; flag maestro OFF. Regla 11. |
| **Neutralizar el default `azure_devops` cambia lo que reciben los proyectos RS no configurados** (hoy reciben las convenciones RS por el default contaminado). | 34.A1 detrás de flag OFF; **antes** de activarlo, sembrar los proyectos RS con `client_type=rs_webforms` (F2). El default neutral solo aplica a proyectos nuevos/genéricos. **Decisión abierta 1.** |
| **Eliminar campos rompe un agente que los leía.** | No se borra nada sin la auditoría `consumed_by` (A4); mientras tanto, *deprecated* en `_meta`. |
| **Inyección dirigida priva a un agente de un campo que sí necesitaba.** | `FIELD_CONSUMERS` es la fuente de verdad y se testea contra los `.agent.md`; default conservador = incluir lo no mapeado; flag OFF = dump completo. |
| **El gate pre-run bloquea runs legítimos.** | C3 solo bloquea en contradicción/faltante **crítico**; el resto es warning; flag OFF; el operador puede forzar. |
| **Escaneo de repo/ADO costoso o lento.** | Caps de profundidad/archivos en B1; reuso de la caché de lectura ADO (27/I3.2) en B2; todo best-effort con timeout, se omite el inferidor que tarde. |

**Decisiones abiertas que requieren confirmación del operador antes de implementar:**
1. **Compatibilidad del default neutral:** ¿sembramos primero los proyectos RS con `client_type=rs_webforms` y recién después activamos `STACKY_CLIENT_PROFILE_NEUTRAL_DEFAULT_ENABLED`? (Recomendado, para no cambiar lo que ya reciben los proyectos RS sin perfil propio.)
2. **Alcance de la eliminación de campos:** confirmar, tras la auditoría 34.A4, qué campos *deprecated* (`readonly_user_hint`, `column_prefix_len`, otros huérfanos) se borran en una v3 vs cuáles se mantienen por compat.
3. **Agresividad del gate pre-run (C3):** ¿bloquear duro ante contradicción crítica, o siempre solo advertir y dejar correr? (Recomendado: bloquear solo crítico, advertir el resto.)
4. **Permisos de lectura para inferencia:** confirmar que la inferencia puede escanear `workspace_root` y leer el board ADO dentro de la auth existente, sin pedir credenciales nuevas.

---

## Ítems diferidos / no-objetivos

- **Auto-confirmación de inferencias de alta confianza** sin paso del operador: diferido (choca con regla 11; revisar solo si K2 lo exige y con tope de confianza muy alto + auditoría).
- **Perfil multi-repo / multi-board por proyecto:** fuera de scope (hoy un proyecto = un `config.json`).
- **Editor visual de `extensions`** más allá de la vista JSON: diferido (bajo valor inmediato).
- **Borrado físico de campos *deprecated*:** diferido a una v3 explícita tras 34.A4 (no-objetivo en esta iteración).
