# 34 — Plan Client Profile Efectivo y Sin Fricción: máxima calidad del output con el mínimo esfuerzo del operador

**Versión:** v1 -> v2
**Fecha v1:** 2026-06-16 · **Fecha v2:** 2026-08-01
**Estado:** PROPUESTO — v1 RECHAZADO por el juez (7 bloqueantes). Esta v2 los resuelve y declara un **CORTE** (§10).
**Autor:** StackyArchitectaUltraEficientCode
**Veredicto de la crítica v1:** RECHAZADO — 7 BLOQUEANTES, 10 IMPORTANTES, 4 MENORES.

---

## CHANGELOG v1 -> v2 (qué cambió y qué hallazgo lo forzó)

- **Defaults de flags reescritos a la regla vigente (C1).** Las 14 flags "todas OFF" se caen: la regla del operador es **default ON** salvo que se cite por escrito la categoría **(A) quema tokens en reposo llamando a un modelo** o **(B) escribe en un sistema real / le saca la decisión al operador**. Sobreviven **7 flags nuevas** (no 14) y **una sola nace OFF** (`..._PRERUN_GATE_ENABLED`, categoría B, justificada en §7.1).
- **`_meta` y `_inference` dejan de contaminar el prompt (C2).** El bloque `client-profile` es un `json.dumps` del perfil **entero** a prioridad 95 que nunca se poda: meter `_meta` ahí duplicaba el bloque más caro en **todo run de todo agente**. En v2 `_meta` se **excluye del serializado** y `_inference` **deja de ser una clave del perfil** (pasa a ser cuerpo de respuesta de un GET, patrón del plan 42).
- **§5 reescrito al schema REAL de hoy (C3).** El perfil creció ~2,5x desde la v1: entran `process_catalog` (42), `state_flow` (216), `devops_pipeline_drafts`/`devops_publication_presets`/`devops_publication_settings`/`devops_environment_settings` (87/88/89), `incident_inbox` (238), `port_residue` (211), `build.allow_csproj_entry` (210). El registro de consumo pasa a **DOS EJES** (agente / servicio) porque esas secciones las lee el backend, no un `.agent.md`.
- **34.D1 vuelto satisfacible (C4).** `build_client_profile_block` **no recibe `agent_type`**. La v2 nombra el cambio de firma y el cableado de los **3 call sites de producción**.
- **Colisión de `schema_version` resuelta (C5).** `project_autoprofile.draft_profile_from_docs` **ya emite `schema_version: 2`** contra un `SCHEMA_VERSION = 1` que `validate_client_profile` **rechaza**. El migrador ya no se ancla al número de versión sino a la **ausencia de `_meta`**, y se corrige el emisor.
- **Gate pre-run degradado y diferido (C6).** Sin seam nombrado y verificable no es implementable por un modelo menor; además bloquear un run ya lanzado es categoría (B). Pasa a tanda 2, warn-only por default, flag OFF justificada.
- **Escaneo de repo con contrato de terminación numérico (C7).** Caps exactos, deny-set, `followlinks=False` y de-duplicación por `realpath` — este árbol tiene una junction `N:` ↔ `C:\desarrollo`.
- **Reuso exigido contra 42 / 98 / 133 / 216 (C8, C11, C12, C13).** Se eliminan `client_profile_infer_docs.py` (duplicaba `project_autoprofile.py`), el PUT del wizard (pasa a **PATCH por key**, plan 98) y la reabsorción de `state_flow` (es del plan 216, con página propia). Se **revive** el contrato muerto `stacky_requires_client_profile` (plan 133).
- **Anclajes re-anclados por SÍMBOLO (C18).** Los `archivo:línea` de la v1 sobrevivieron 1 de cada ~21 en 6 semanas. En v2 se cita **función/constante en archivo**, y la línea solo como pista.
- **Tanda declarada (C9).** 14 flags × 6 lugares de registro + 8 módulos nuevos + un wizard no entra en una tanda. §10 define qué entra (F0..F7) y qué se difiere, **sin cambiar el número del plan ni partirlo en archivos**.
- **[ADICIÓN ARQUITECTO] ×2** en §9: contrato de perfil por agente ejecutable y bidireccional, y la deduplicación medida de `process_catalog`, que hoy viaja **dos veces** en cada run.

---

**Predecesores directos (Client Profile):** `docs/16` (sustrato: schema, store, inyección), `docs/17` (prefill de layout + `resolve_layout_paths` + `complete_client_profile`), `docs/18`.
**Predecesores que YA construyeron parte de lo que la v1 proponía (reuso obligatorio, no re-implementar):** `docs/42` (`services/project_autoprofile.py` — inferencia determinista desde docs + endpoint autodetect no-persistente), `docs/98` (PATCH por key + `services/client_profile_keys.py`), `docs/133` (frontmatter `stacky_requires_client_profile`), `docs/216` (`state_flow` + `StatesConfigPage.tsx`).
**Predecesores de método:** `docs/29` (juicio semántico), `docs/30` (verificación contra la realidad), `docs/31` (verificación ejecutable), `docs/32` (contrato de aceptación), `docs/33` (flags 100% por UI).
**Audiencia:** dev agéntico junior (Haiku / Codex / GitHub Copilot Pro). Cada ítem nombra **archivos exactos, símbolos exactos, comando exacto y criterio binario**. Donde la v1 decía "según corresponda" o "umbral", la v2 pone un número.

**Tesis (sin cambios respecto de v1):** el Client Profile es hoy un formulario que el operador llena a mano, cuyo default está contaminado con valores de un cliente concreto, que se inyecta completo y sin selección a todos los agentes, y cuya única validación es de tipo + secretos. El salto es invertir la relación esfuerzo/valor: el perfil se **infiere**, el operador **confirma**, jueces deterministas detectan lo roto **antes** de gastar un run, y la inyección se vuelve **dirigida y anclada a la realidad**.

**Frontera dura (regla 11, human-in-the-loop):** la inferencia **propone**, nunca **fija**. Stacky no decide la identidad del cliente por su cuenta, no publica nada, no re-escribe un valor que el humano ajustó a propósito.

---

## 1. Relación con los planes previos (qué reusa, qué NO re-implementa)

- **REUSA, no re-implementa:**
  - store y validación → `services/client_profile.py` (`validate_client_profile`, `_contains_secret_keys`, `merge_with_defaults`, `complete_client_profile`, `resolve_layout_paths`, `load_effective_client_profile`).
  - templates embebidos + mirror JSON → `services/client_profile_default_templates.py` (`AZURE_DEVOPS`, `JIRA`, `MANTIS`, `GITLAB`, `DEFAULT_TEMPLATES`) y `services/client_profile_defaults/*.json`, resueltos por `_read_default_template` (JSON en disco primero, embebido como fallback de deploy congelado).
  - seam único de armado del bloque → `build_client_profile_block` en `services/context_enrichment.py`.
  - ranking/budget → `_BLOCK_PRIORITY` (**21 ids**, no 6) y `_HIGH_PRIORITY_THRESHOLD = 75` en `services/context_enrichment.py`.
  - panel genérico de flags → `FLAG_REGISTRY` + `_CATEGORY_KEYS` en `services/harness_flags.py`, renderizado por `HarnessFlagsPanel`.
- **REUSA de planes que la v1 no conocía (obligatorio):**
  - **Plan 42** — `draft_profile_from_docs(docs_root)` en `services/project_autoprofile.py` (determinista, sin LLM, deriva `docs_indexes.*` + `process_catalog`) y el endpoint `autodetect_process_catalog` (`GET /projects/<p>/process-catalog/autodetect`, en `api/client_profile.py`) que devuelve **candidatos efímeros NO persistidos** (GET → merge en el cliente → PUT). **Ese es el patrón de `_inference`; no se construye otro.**
  - **Plan 98** — `patch_client_profile_key` (`PATCH /projects/<p>/client-profile/keys/<key>`) + `PATCHABLE_PROFILE_KEYS` y `validate_profile_key` en `services/client_profile_keys.py`. **Toda aceptación de un valor sugerido va por acá, nunca por el PUT completo.**
  - **Plan 133** — `stacky_requires_client_profile: true|false` en el frontmatter de los `.agent.md`. Gate **binario** por agente. Hoy está **declarado y muerto** (0 lectores en `.py`/`.ts`/`.tsx`); este plan lo revive (§9, ADICIÓN 1).
  - **Plan 216** — `state_flow` + `_check_state_flow` (en `services/client_profile.py`) + `set_client_profile_state_flow` + `StatesConfigPage.tsx`, **fuera** del `ClientProfileEditor`. Este plan **no toca `state_flow` ni reabsorbe esa página**.
- **Frontera con docs 29/30/31/32:** esos planes juzgan **el output**; el 34 mejora **el insumo**. El 34 alimenta el preflight del 30 con un predicado nuevo ("perfil coherente") — pero **solo cuando el seam del 30 esté verificado en código** (ver §10, tanda 2).
- **SUBSUME / REEMPLAZA:** nada.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es auto-intake ni autonomía.** El perfil se infiere y se propone; el operador confirma.
2. **No agrega RBAC ni multi-usuario.** Mono-operador sin auth real (`current_user` es un header sin validar).
3. **No mete secretos en el perfil.** `_SECRET_KEYS` + `_contains_secret_keys` (en `services/client_profile.py`) se mantienen y se endurecen, no se relajan.
4. **No rompe el contrato del schema actual.** Toda adición es aditiva; los `config.json` existentes siguen cargando **byte-idénticos en su efecto**.
5. **No borra campos a ciegas.** Una eliminación solo procede tras la auditoría de consumo (34.A4) que pruebe que **ni un agente ni un servicio** lo leen.
6. **No introduce deps nuevas (npm/py) ni FTS5.**
7. **No cambia QUÉ/CUÁNDO se publica al tracker.** Toda lectura de ADO/GitLab es solo lectura.
8. **NUEVO — no reabsorbe `state_flow` ni la `StatesConfigPage`** (plan 216, implementado).
9. **NUEVO — no crea un segundo motor de inferencia desde docs.** Se extiende `project_autoprofile.py`.

---

## 3. Diagnóstico: dónde el Client Profile cuesta esfuerzo y no rinde calidad

Anclajes **por símbolo** (las líneas caducan; se dan como pista, verificadas 2026-08-01).

| # | Debilidad | Evidencia (símbolo · archivo:línea-pista) | Impacto |
|---|---|---|---|
| **D1** | **Carga casi 100% manual.** El editor es un formulario plano de ~35 inputs + un toggle a JSON crudo (`advancedJson`), **1288 líneas**, con **0 hits** de `wizard|suggest|autofill|autodetect`. `resolve_layout_paths` solo **verifica** existencia (devuelve `exists`), nunca **descubre**. | `ClientProfileEditor.tsx` (`advancedJson` :628/:671) · `resolve_layout_paths` en `services/client_profile.py:520` | 30-40 decisiones manuales. El operador lo posterga → perfil pobre → output genérico. |
| **D2** | **El default "genérico" trae valores de un cliente concreto.** El template `AZURE_DEVOPS` —fallback de cualquier proyecto sin configurar— trae RS/RIPLEY hardcodeado. | `client_profile_default_templates.py`: `architecture_layers ["UI","RSBus (BLL)","RSDalc (DAL)","BD"]` :40 · `languages_in_ridioma ["ESP","ENG","POR"]` :46 · `table_prefix "R"` :57 · `msbuild_path` VS2022 Community :63 · `ridioma_helper`/`ridioma_message_const`/`string_sanitizer` :72-:74 | Un cliente que no es RS recibe convenciones ajenas **como si fueran suyas**. Peor que un campo vacío honesto. |
| **D3** | **Validación anémica.** `validate_client_profile` chequea tipos de 9 secciones, secretos, `schema_version` y `state_flow`; las secciones requeridas (`_REQUIRED_SECTIONS`) salen como **warning**, no error → un perfil casi vacío valida `ok=True`. Cero detección de contradicciones (`language.primary=csharp` + `build.tool=maven`), cero coherencia BD, cero verificación de que los estados existan en el board real. | `validate_client_profile` en `services/client_profile.py:274` (required→warning en el loop sobre `_REQUIRED_SECTIONS`) | Perfiles auto-contradictorios pasan y degradan el output sin que nadie lo note. |
| **D4** | **Inyección sin selección: dump completo a todos los agentes.** El bloque es `json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True)` del perfil **entero** ya mergeado con el default, idéntico para FunctionalAnalyst, TechnicalAnalyst y Developer. `merge_with_defaults` rellena **incluyendo `database`** y campos vacíos. | `build_client_profile_block` en `services/context_enrichment.py:552` · `merge_with_defaults` en `services/client_profile.py:465` | El FunctionalAnalyst recibe `msbuild_path` y `port_residue`; el Developer recibe lo mismo que el funcional. |
| **D5** | **Prioridad 95 = nunca se poda ni se dedupe, a cualquier tamaño.** `"client-profile": 95` está por encima de `_HIGH_PRIORITY_THRESHOLD = 75`. | `_BLOCK_PRIORITY` :375 (`"client-profile": 95` :380) · `_HIGH_PRIORITY_THRESHOLD = 75` :257 · uso en `is_high_priority` :319 | Un perfil obeso ocupa presupuesto fijo en todo run y desplaza contexto que sí importa. |
| **D6** | **Sin frescura ni procedencia.** No hay `updated_at` por campo ni raíz, ni origen (manual/default/inferido), ni confianza. | (ausencia) `services/client_profile_default_templates.py` sin timestamps | Imposible distinguir un dato confirmado de un default copiado, ni detectar rutas rancias. |
| **D7** | **`client_type` no existe: tracker ≠ stack.** El único eje de template es el tracker (`DEFAULT_TEMPLATES` = `azure_devops`/`jira`/`mantis`/**`gitlab`**), pero las convenciones dependen del **stack**. | `DEFAULT_TEMPLATES` en `client_profile_default_templates.py:361-364` | No hay "plantilla por tipo de cliente" sin duplicar el bloque del tracker. D2 es consecuencia de esto. |
| **D8** | **Aprendizaje cero.** Nada de lo que el run descubre vuelve al perfil. | (ausencia) | El costo de mantener el perfil correcto recae siempre en el humano. |
| **D9 (NUEVO)** | **El perfil creció ~2,5x y la mitad de lo nuevo NO lo lee ningún agente: lo lee el backend.** `process_catalog`, `state_flow`, `incident_inbox`, `devops_*`, `port_residue` son configuración de servidor viajando dentro del bloque de prioridad 95. | consumidores en §5.1 | Tokens de prompt gastados en config que el LLM no puede usar. |
| **D10 (NUEVO)** | **`process_catalog` viaja DOS VECES en todo run de un proyecto con catálogo:** dentro del dump del perfil (prioridad 95) **y** como bloque propio `process-catalog` (prioridad 78). `_dedup_blocks` no lo ve: el texto difiere (`"name": "X",` vs `- X [batch]: propósito`). | `build_client_profile_block` vs `build_process_dictionary_block`, ambos en `services/context_enrichment.py` · `_dedup_blocks` :266 | Duplicación medible y silenciosa de tokens en cada ejecución. |
| **D11 (NUEVO)** | **La flag maestra del feature es invisible desde la UI.** `STACKY_INJECT_CLIENT_PROFILE` se lee por `os.getenv(..., "true")` y **no existe** en `FLAG_REGISTRY` (0 hits de `CLIENT_PROFILE` en `services/harness_flags.py`). | `context_enrichment.py:576` | Viola el riel "toda flag/config del operador va por UI" (doc 33), que este mismo plan invoca. |
| **D12 (NUEVO)** | **`schema_version` ya está en conflicto.** `draft_profile_from_docs` emite `"schema_version": 2` mientras `SCHEMA_VERSION = 1`; `validate_client_profile` devuelve **`ok=False`** para `schema_version > SCHEMA_VERSION`. | `services/project_autoprofile.py:93` vs `services/client_profile.py:40` y `:274` | Bug latente vivo: mergear el draft del plan 42 en un perfil lo vuelve inválido. |
| **D13 (NUEVO)** | **Los tests del Client Profile NO están en el arnés.** `tests/test_client_profile.py`, `test_client_profile_endpoints.py`, `test_context_enrichment_client_profile.py`, `test_project_autoprofile.py` **no figuran** en `backend/scripts/run_harness_tests.sh` (791 entradas) ni en `.ps1` (727). | `backend/scripts/run_harness_tests.{sh,ps1}` | "Verde" en esos archivos **no es el gate del producto**. |

**Lectura central:** el sustrato ya existe y es sólido. El valor del 34 es **(a)** limpiar el default sin mentir, **(b)** inferir en vez de pedir **reusando lo del plan 42**, **(c)** validar con jueces deterministas, **(d)** inyectar **dirigido, deduplicado y sin metadata**, y **(e)** aprender del uso — con defaults **ON** salvo la única excepción justificada.

---

## 4. Objetivos medibles y KPIs

| KPI | Definición **ejecutable** | Baseline (hoy) | Objetivo |
|---|---|---|---|
| **K1 — % de campos autoinferidos** | `len(inference.proposals) / len(FIELD_CONSUMERS)` para un proyecto con `workspace_root` + `docs_root` configurados | 0% | ≥ 70% |
| **K2 — Decisiones hasta "perfil usable"** | nº de llamadas a `PATCH .../client-profile/keys/<key>` desde el wizard hasta que `judges(profile)` no devuelva ningún `Finding` de severidad `critical` | ~35 | ≤ 3 |
| **K3 — Δ tokens del bloque `client-profile`** | `len(block["content"])` con vista dirigida vs dump completo, por `agent_type`, sobre el perfil de un proyecto real | dump completo a los 3 agentes | −30% a −50% **sin perder ningún campo mapeado a ese agente** |
| **K4 — Coherencia** | % de perfiles guardados que pasan `judges` sin `critical` | n/d | ≥ 95% |
| **K5 — Frescura** | % de paths con `_meta.fields.<path>.updated_at` < 90 días | n/d | reportado y decreciente |
| **K6 — Duplicación eliminada** | `"process_catalog" not in block("client-profile")["content"]` cuando el bloque `process-catalog` está presente | duplicado | 0 duplicados (criterio binario) |

**Exposición:** K3/K4/K6 se calculan en backend y se exponen por el endpoint de salud del perfil (34.C1), consumido por la tarjeta "Salud del Client Profile" en la `DiagnosticsPage` existente. **No se crea UI de métricas nueva.**
**K1/K2/K5 quedan diferidos a la tanda 2** (dependen de la inferencia). **K3/K4/K6 son los KPIs de la tanda 1** y son los únicos que este plan promete medir ahora.

---

## 5. Esquema REAL del Client Profile hoy (mantener / agregar / relocalizar)

**Principio (corregido):** el schema efectivo se define por **quién lo consume**, y hay **DOS clases de consumidor**: el **prompt de un agente** (`.agent.md`) y un **servicio/endpoint del backend**. Un campo que ningún agente lee **puede seguir siendo esencial** (lo lee el backend) — solo que **no debe viajar en el prompt**. La v1 tenía un solo eje y por eso habría marcado *deprecated* y habría **sacado del prompt** secciones vivas.

### 5.1 MANTENER — inventario COMPLETO verificado 2026-08-01

**Eje A — consumido por el prompt de algún agente (va al bloque inyectado):**
- `code_layout.{online_path, batch_path, db_scripts_path, lib_path, test_path, file_extensions, architecture_layers}`
- `language.{primary, ticket_token_pattern, comment_traceability, languages_in_ridioma}`
- `tracker_state_machine.{functional, technical, developer}` — validado por `_check_tracker_state_machine` (`services/client_profile.py:144`) y `_check_by_work_item_type` (`:169`)
- `database.{type, dml_policy, connection_kind, readonly_user_hint, naming_conventions, catalog_master_files}`
- `build.{tool, command|msbuild_path, configuration, online_solutions, batch_proj_glob}`
- `conventions.{ridioma_helper, ridioma_message_const, string_sanitizer, error_helpers}`
- `docs_indexes.{technical_master, functional_online, functional_batch}`
- `terminology.{product_name, client_label, domain_glossary_ref}`
- `extensions` (free dict)
- `process_catalog` — **pero por su bloque propio, no por el dump** (ver D10 y §9 ADICIÓN 2)

**Eje B — consumido SOLO por servicios/endpoints del backend (NO debe viajar en el prompt):**

| Sección | Plan | Consumidor de producción medido |
|---|---|---|
| `state_flow` | 216 | `_check_state_flow` y `set_client_profile_state_flow` en `services/client_profile.py` · `services/flow_config_store.py:170` · `services/incident_inbox.py:64` |
| `incident_inbox.{incident_types, closed_states}` | 238 | `services/incident_inbox.py:43,59` |
| `devops_pipeline_drafts` | 87 | `PATCHABLE_PROFILE_KEYS` + `_validate_pipeline_drafts` en `services/client_profile_keys.py` |
| `devops_publication_presets` / `devops_publication_settings` | 88 | `api/devops.py:292,298` |
| `devops_environment_settings` | 89 | `api/devops.py:336` |
| `port_residue.allowlist` | 211 | `services/dev_build_contributors.py:106` vía `port_residue_scanner.allowlist_for_project` · presente en el template (`client_profile_default_templates.py:108`) |
| `build.allow_csproj_entry` | 210 | `services/dev_build_verify.py:119` |
| `process_catalog` (también eje B) | 42 | `api/devops.py:297,359` · `api/agents.py:2043` · `api/client_profile.py:217` |

> **Consecuencia dura:** cualquier feature que **excluya** campos del prompt debe usar **ALLOWLIST del eje A**, nunca denylist. Y la auditoría de *deprecated* exige **ambos ejes vacíos**.

### 5.2 AGREGAR (aditivo)

- **`client_type`** (string) — id de plantilla de **stack** (`rs_webforms`, `dotnet_modern`, `java_spring`, `generic`), **ortogonal al tracker**. Resuelve D7.
- **`_meta`** — procedencia/confianza/frescura **sin tocar los valores**:
  - `_meta.updated_at` (raíz) + `_meta.fields.<path>.{source, confidence, updated_at}`
  - `source ∈ {operator, default, inferred:repo, inferred:tracker, inferred:docs, inferred:memory, learned:run}`
  - `confidence ∈ [0,1]`
  - **Tope duro:** `_meta.fields` acepta como máximo **200 paths**; al superarlo se descartan los de menor `confidence` (determinista, orden por `(confidence, path)`).
  - **`_meta` NUNCA se serializa en el bloque inyectado** (34.A2 / F2).
- **`_inference` NO es una clave del perfil** (corrección v1). Es el **cuerpo de respuesta** de `GET /projects/<p>/client-profile/inference`, efímero y no persistido — exactamente el patrón de `autodetect_process_catalog` (plan 42). Así no se persiste, no se inyecta y no puede transportar secretos a disco.

### 5.3 RELOCALIZAR a `client_type=rs_webforms` (default honesto SIN flag y SIN regresión)

Mover **fuera** del template `AZURE_DEVOPS` los valores RS/RIPLEY: `conventions.{ridioma_helper, ridioma_message_const, string_sanitizer, error_helpers}`, `language.languages_in_ridioma`, `code_layout.architecture_layers` con `RSBus/RSDalc`, `database.naming_conventions.table_prefix = "R"`, `build.msbuild_path` de VS2022 Community.

**Cómo se evita la regresión sin usar una flag** (la v1 usaba `..._NEUTRAL_DEFAULT_ENABLED` con la justificación "retro-compat", motivo invalidado por el operador):

> La composición del default es `tracker_template ⊕ STACK_TEMPLATES[client_type]`.
> **Resolución de `client_type` cuando el perfil no lo declara:**
> - si el perfil persistido existe y su `schema_version` es `1` (perfil pre-34) → `client_type = "rs_webforms"` ⇒ **el default efectivo es byte-idéntico al de hoy**;
> - si no hay perfil persistido → `client_type = "rs_webforms"` ⇒ **byte-idéntico al de hoy**;
> - si el perfil declara `client_type` explícito (lo hace el wizard y lo escribe el operador) → se usa ese.
>
> Resultado: **cero cambios observables** para todo lo que existe hoy, default honesto para todo lo que se cree con `client_type` explícito, y **una flag menos**. Función pura, testeable, sin migración escrita a disco.

### 5.4 CANDIDATOS A *DEPRECATED* (solo tras auditoría de DOS EJES)

- `database.readonly_user_hint` — **NO deprecar**: el `.agent.md` del TechnicalAnalyst lo lista explícitamente entre los campos a extraer. Eje A ocupado.
- `database.naming_conventions.column_prefix_len` — sin consumidor conocido en ninguno de los dos ejes → candidato real.
- Cualquier campo con `consumed_by_agent = []` **y** `consumed_by_service = []`.
> Mientras no se pruebe que **ni un agente ni un servicio** lo leen, se marca *deprecated* en `_meta`, no se borra.

---

## FASE F0 — Preparación del arnés (obligatoria, 15 min, habilita todo gate posterior)

### 34.F0.1 — Registrar en el arnés los tests del Client Profile
**Qué:** agregar a `backend/scripts/run_harness_tests.sh` **y** a `backend/scripts/run_harness_tests.ps1` (los DOS, sintaxis distinta cada uno) las rutas:
`tests/test_client_profile.py`, `tests/test_client_profile_endpoints.py`, `tests/test_context_enrichment_client_profile.py`, `tests/test_project_autoprofile.py`.
**Por qué:** D13 — hoy esos archivos no son el gate del producto; sin esto, todo "verde" de este plan es decorativo.
**Regla de costo:** **todo test nuevo de este plan va dentro de esos 4 archivos ya existentes.** No se crean archivos de test nuevos salvo el de F3 (`tests/test_client_profile_consumption.py`), que **también** debe registrarse en los dos scripts.
**Criterio binario:** `python -c "import pathlib,sys; sh=pathlib.Path('backend/scripts/run_harness_tests.sh').read_text(encoding='utf-8'); ps=pathlib.Path('backend/scripts/run_harness_tests.ps1').read_text(encoding='utf-8'); need=['tests/test_client_profile.py','tests/test_client_profile_endpoints.py','tests/test_context_enrichment_client_profile.py','tests/test_project_autoprofile.py','tests/test_client_profile_consumption.py']; missing=[n for n in need if n not in sh or n not in ps]; sys.exit(1 if missing else 0)"` → exit 0.
**Nota de mecanismo:** `tests/test_harness_ratchet_meta.py` exige que la ruta **exista en disco**; crear la entrada antes que el archivo rompe el ratchet.

---

## FASE A — Esquema efectivo y honesto (default sin mentira + procedencia + mapa de consumo)

### 34.A1 — Separar tracker (estados) de stack (convenciones), sin flag y sin regresión
**Qué:** en `services/client_profile_default_templates.py`, vaciar de `AZURE_DEVOPS` los campos de §5.3 y crear `STACK_TEMPLATES: dict[str, dict] = {"rs_webforms": {...}, "generic": {...}}` con exactamente esos campos. En `services/client_profile.py`, `get_default_client_profile(tracker_type, client_type=None)` compone `tracker ⊕ STACK_TEMPLATES[resolve_client_type(...)]` usando `_deep_merge`.
**Por qué:** D2/D7.
**Cómo (exacto):**
1. `client_profile_default_templates.py`: agregar `STACK_TEMPLATES` y exportarlo; **vaciar** (no borrar la clave: dejar `""` / `[]`) los campos RS en `AZURE_DEVOPS`. **Aplicar la misma neutralización a `JIRA`, `MANTIS` y `GITLAB`** — los cuatro traen el mismo bloque RS.
2. `client_profile_defaults/{azure_devops,jira,mantis,gitlab}.json`: espejar el cambio. El test de drift JSON↔embebido existente en `tests/test_client_profile.py` debe seguir verde.
3. `services/client_profile.py`: nueva función pura `resolve_client_type(persisted: dict | None) -> str` con la regla literal de §5.3.
**Flag:** **NINGUNA.** La retro-compat se garantiza por construcción (§5.3), no por una flag; "retro-compat byte-idéntica" es un motivo de OFF explícitamente invalidado por el operador.
**Test/gate (en `tests/test_client_profile.py`):**
- `test_neutral_default_has_no_rs_specifics` — con `client_type="generic"`, `json.dumps(default)` no contiene `RSFac`, `cFormat`, `RSBus`, `RSDalc`, ni `"table_prefix": "R"`.
- `test_legacy_profile_default_is_byte_identical` — para `persisted=None` y para `persisted={"schema_version": 1, ...}`, `json.dumps(get_default_client_profile("azure_devops"), sort_keys=True)` es **igual carácter a carácter** al output capturado antes del cambio (fixture congelada en el propio test).
- `test_stack_template_rs_webforms_restores_rs_values`.
- `test_all_four_trackers_are_neutral` — parametrizado sobre `("azure_devops","jira","mantis","gitlab")`.
**Comando:** `& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_client_profile.py -q`

### 34.A2 — Metadatos `_meta`, aditivos e **invisibles para el prompt**
**Qué:** `_meta` por-campo y raíz + helper `stamp_meta(profile, path, source, confidence) -> dict` (puro, devuelve copia).
**Por qué:** D6 — sin procedencia no hay scoring, frescura ni aprendizaje. **Corrección v1 (C2):** el bloque inyectado es `json.dumps` del perfil **entero** a prioridad 95 que **nunca se poda**; meter `_meta` ahí duplica el bloque más caro del contexto en **todo run de todo agente**.
**Cómo (exacto):**
1. `services/client_profile.py`: `validate_client_profile` acepta `_meta` (dict) y lo **excluye** del loop de tipos de sección; `_contains_secret_keys` lo barre igual (no se relaja).
2. `services/client_profile.py`: constante `NON_INJECTABLE_KEYS: frozenset = frozenset({"_meta", "_autoprofile_source"})`.
3. `services/context_enrichment.py`, dentro de `build_client_profile_block`, **antes** del `json.dumps`: `profile = {k: v for k, v in profile.items() if k not in NON_INJECTABLE_KEYS}`.
4. Tope de 200 paths en `_meta.fields` (§5.2), aplicado en `stamp_meta`.
**Flag:** **NINGUNA** (estructura aditiva inerte).
**Test/gate:**
- `tests/test_client_profile.py::test_meta_cannot_carry_secrets`
- `tests/test_client_profile.py::test_meta_fields_capped_at_200`
- `tests/test_context_enrichment_client_profile.py::test_meta_never_appears_in_injected_block` — construir un perfil con `_meta` poblado, llamar a `build_client_profile_block` y **asertar primero que el campo de control SÍ está** (`"code_layout" in content`) **y después** que `"_meta" not in content`. *(Un assert de ausencia solo, pasa por accidente si el bloque salió `None`.)*

### 34.A3 — Migrador anclado a la AUSENCIA de `_meta`, no al número de versión
**Qué:** `migrate_client_profile(profile: dict) -> dict`, idempotente, en `services/client_profile.py`.
**Por qué:** D12/C5 — `draft_profile_from_docs` **ya emite `"schema_version": 2`** (`services/project_autoprofile.py:93`) contra `SCHEMA_VERSION = 1`, y `validate_client_profile` devuelve `ok=False` para `schema_version > SCHEMA_VERSION`. Un migrador que dispare con `schema_version == 1` **saltea** esos perfiles y nunca les crea `_meta`.
**Cómo (exacto):**
1. Condición de migración: **`"_meta" not in profile`** (no `schema_version == 1`).
2. Subir `SCHEMA_VERSION` a `2` en `services/client_profile.py`.
3. **Corregir el emisor:** en `services/project_autoprofile.py`, `draft_profile_from_docs` devuelve un **fragmento parcial**, no un perfil: eliminar la clave `"schema_version"` de su dict de retorno. Ajustar `tests/test_project_autoprofile.py` si asertaba ese valor.
4. Invocar `migrate_client_profile` en `load_effective_client_profile` (`services/client_profile.py:388`) y en `put_client_profile` (`api/client_profile.py`) **antes** de validar.
**Test/gate (en `tests/test_client_profile.py`):** `test_migrate_idempotent` · `test_migrate_preserves_unknown_keys` (incl. `extensions`, `devops_*`, `port_residue`) · `test_migrate_profile_with_schema_version_2_and_no_meta` · `test_v1_profile_still_valid`.
**Test/gate (en `tests/test_project_autoprofile.py`):** `test_draft_does_not_declare_schema_version`.

### 34.A4 — Registro de consumo de **DOS EJES** + reanimación del contrato del plan 133
**Qué:** `services/client_profile_consumption.py` con:
```python
FIELD_CONSUMERS: dict[str, dict[str, frozenset[str]]]
# path -> {"agents": frozenset[str], "services": frozenset[str]}
INJECTABLE_PATHS: frozenset[str]   # = paths con agents != frozenset()
```
más el lector que revive el plan 133:
```python
def agent_requires_client_profile(agent_type: str) -> bool | None
# parsea el frontmatter `stacky_requires_client_profile` de backend/Stacky/agents/*.agent.md
# None = el agente no declara nada
```
**Por qué:** habilita completitud útil (C1), inyección dirigida (D1) y la auditoría de *deprecated*. **Corrección v1 (C3/C8):** un mapa de un solo eje (campo→agente) daría `consumed_by = []` a `state_flow`, `incident_inbox`, `devops_*` y `port_residue`, y la inyección dirigida los **sacaría del prompt** — lo cual, casualmente, es lo correcto para el prompt pero **catastrófico** para la auditoría de *deprecated*, que los borraría.
**Diseño elegido y por qué (respuesta explícita a "central en Python vs frontmatter"):**
- El eje **por-campo** vive **central en Python**. Razón: el test que lo valida **greppea los `.agent.md`**; si el mapa viviera dentro del archivo que audita, la auditoría sería circular. Además el runtime lee los agentes de `backend/Stacky/agents`, editable por el operador — un contrato de inyección no puede depender de un archivo que el operador cambia sin correr tests.
- El eje **binario** (¿este agente necesita perfil?) **se reusa del frontmatter del plan 133**, que ya existe en 5 `.agent.md` y **hoy no lo lee nadie** (0 lectores en `.py`/`.ts`/`.tsx`). Se cablea acá.
- Un test **bidireccional** impide que se desincronicen (§9, ADICIÓN 1).
**Cómo (exacto):** poblar `FIELD_CONSUMERS` a partir de §5.1 (los agentes salen del bloque "Extraer del `client-profile`" del `.agent.md` de cada agente; los servicios, de la tabla del eje B).
**Flag:** —
**Test/gate (archivo nuevo `tests/test_client_profile_consumption.py`, registrado en F0.1):**
- `test_every_agent_axis_field_appears_in_some_agent_md` — cada path con `agents != ∅` aparece textualmente en al menos uno de los `.agent.md` de `backend/Stacky/agents/`.
- `test_every_service_axis_field_has_a_grep_hit` — cada path del eje B tiene ≥1 hit en `backend/services/` o `backend/api/` **excluyendo `tests/`, el propio módulo y los baselines de ratchet**.
- `test_orphan_fields_are_flagged` — un path sin agentes **y** sin servicios se reporta como candidato *deprecated*.
- `test_agent_declaring_requires_profile_has_mapped_fields` y su recíproco (ADICIÓN 1).
- `test_backend_only_sections_are_not_injectable` — `state_flow`, `incident_inbox`, `devops_pipeline_drafts`, `devops_publication_presets`, `devops_publication_settings`, `devops_environment_settings`, `port_residue` **no** están en `INJECTABLE_PATHS`.

---

## FASE B — Inferencia (DIFERIDA A TANDA 2, diseño ya cerrado)

> **Ver §10.** El diseño queda fijado acá para que la tanda 2 no lo relitigue.

### 34.B1 — Inferencia desde el repo — contrato de terminación NUMÉRICO
**Qué:** proponer `code_layout.*`, `language.primary`, `build.online_solutions` (`*.sln`), `build.batch_proj_glob` (`*.csproj`), `code_layout.file_extensions`.
**Cómo (exacto, C7):** `services/client_profile_infer_repo.py`, stdlib.
- `os.walk(root, followlinks=False)` — **obligatorio**: este árbol tiene una junction `N:` ↔ `C:\desarrollo` que hace que seguir enlaces recorra el repo dos veces o no termine.
- De-duplicación por `os.path.realpath(dirpath)` en un `set` visitado; un directorio ya visto se poda.
- `max_depth = 4` (relativo a `workspace_root`), `max_files = 20000`, `wall_clock_budget = 5.0 s` medidos con `time.monotonic()`; alcanzado cualquiera de los tres, se devuelve lo acumulado con `partial=True`.
- Deny-set literal: `{".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", "obj", "bin", "packages", ".vs", ".idea"}`.
- Toda ruta propuesta se confirma con `resolve_layout_paths` (`exists == True`) antes de emitirse.
**Flag:** cubierta por el maestro (§7.1). **Nace ON**: es lectura determinista de disco, disparada por el operador, **sin llamar a ningún modelo**.
**Test/gate:** `tests/test_client_profile_infer_repo.py` — árbol fixture con `.sln`; `test_symlink_loop_terminates` (crear un symlink al padre; si el SO no lo permite, `pytest.skip` con motivo); `test_never_proposes_nonexistent_path`; `test_budget_exhaustion_sets_partial`.

### 34.B2 — Inferencia desde el tracker (estados reales del board) — **solo `tracker_state_machine`**
**Qué:** proponer `tracker_state_machine.{functional,technical,developer}.{input_states,next_state_ok,blocked_state}` a partir de los estados reales del board. **Solo lectura.**
**Corrección v1 (C11):** la v1 decía "inferir `tracker_state_machine` desde el board" pero el wizard habría reabsorbido la configuración de estados. **Prohibido tocar `state_flow`** — es del plan 216, tiene su validador (`_check_state_flow`), su setter (`set_client_profile_state_flow`) y su página propia (`StatesConfigPage.tsx`). El wizard **linkea** a esa página, no la duplica.
**Corrección v1 (C10):** el tracker **no es solo ADO**. `DEFAULT_TEMPLATES` tiene 4 entradas y GitLab es first-class desde los planes 276/277. El módulo se llama `services/client_profile_infer_tracker.py` (no `_infer_ado`) y despacha por `get_project_tracker_type(project_name)`; para un tracker sin lector de estados implementado devuelve `[]` con `reason="tracker_no_soportado"` — **nunca inventa**.
**Test/gate:** `tests/test_client_profile_infer_tracker.py` — board fake ADO y board fake GitLab; `test_unknown_tracker_returns_empty_with_reason`; `test_never_proposes_state_absent_from_board`; `test_does_not_touch_state_flow`.

### 34.B3 — Inferencia desde docs — **extiende `project_autoprofile.py`, NO crea módulo nuevo**
**Corrección v1 (C12):** la v1 proponía `client_profile_infer_docs.py`. Eso **duplica** `draft_profile_from_docs` en `services/project_autoprofile.py` (plan 42), que ya deriva `docs_indexes.technical_master/functional_online/functional_batch` + `process_catalog` de forma determinista y sin LLM.
**Qué:** extender `draft_profile_from_docs` para que además reconozca índices con patrón `*INDICE*` / `*INDEX*` / `00_*` (hoy usa `_find_master_index` + heurística online/batch por nombre), y envolverla como la fuente `docs` del orquestador B5.
**Deuda a saldar en el mismo cambio:** `STACKY_PROJECT_AUTOPROFILE_ENABLED` está en **default False**. Es **lectura determinista de disco sin modelo** ⇒ no cae en (A) ni en (B) ⇒ **se promueve a ON** en esta tanda 2 (y se cura en `_CURATED_DEFAULTS_ON`). Ese False es **deuda declarada del plan 42, no un precedente a imitar**.
**Test/gate:** en `tests/test_project_autoprofile.py` — `test_recognizes_indice_index_and_00_prefixed`; `test_never_proposes_nonexistent_file`.

### 34.B4 — Inferencia desde memoria/ejecuciones — umbral NUMÉRICO
**Qué:** proponer `conventions.*`/`terminology.*` a partir de tokens recurrentes en outputs aprobados y memoria del proyecto.
**Cómo (exacto):** `services/client_profile_infer_memory.py`. **Umbral literal: un token se propone si aparece en `>= 3` outputs aprobados distintos**, con `confidence = min(1.0, apariciones / 10)`. Con 1 o 2 apariciones **no se propone** (no se emite con confianza baja: no se emite).
**Test/gate:** fixture con 3 outputs citando `RSFac.Idioma` → se propone con `source="inferred:memory"`; con 2 → no aparece en la propuesta.

### 34.B5 — Orquestador — devuelve, no persiste
**Qué:** `infer_client_profile(project_name) -> InferenceResult` en `services/client_profile_inference.py`. Corre las fuentes habilitadas, fusiona por precedencia **literal** `operator > learned:run > inferred:repo > inferred:tracker > inferred:docs > inferred:memory > default`, y **devuelve** el resultado.
**Corrección v1 (C2):** **no escribe `_inference` en el perfil.** Se expone por `GET /projects/<p>/client-profile/inference` (espejo exacto de `autodetect_process_catalog`, plan 42): candidatos efímeros, no persistidos, human-in-the-loop.
**Best-effort:** cualquier fuente que lance se omite con warning (mismo patrón que `build_client_profile_block`).
**Test/gate:** `tests/test_client_profile_inference.py::test_merge_respects_confidence_order`, `::test_failure_in_one_source_is_isolated`, `::test_inference_never_writes_profile` (asertar que `load_client_profile` devuelve lo mismo antes y después).

---

## FASE C — Validación, jueces deterministas y completitud útil

### 34.C1 — Scoring de completitud ponderado por consumo + salud del perfil
**Qué:** `services/client_profile_quality.py`:
```python
def score_completeness(profile: dict) -> dict
# {"score": float, "missing_high_value": list[str], "orphans": list[str], "stale": list[str]}
```
Los pesos salen de `FIELD_CONSUMERS`: **peso = `len(agents) * 2 + len(services)`**. `missing_high_value` son los **3** paths de mayor peso con valor vacío, ordenados por `(-peso, path)` (criterio determinista, sin empates ambiguos). `stale` usa `_meta.fields.<path>.updated_at` con umbral **90 días** — esto absorbe el 34.E2 de la v1, que no necesitaba módulo ni flag propios.
**Endpoint:** `GET /projects/<p>/client-profile/health` en `api/client_profile.py`, junto a los existentes. Lo consume la tarjeta de la `DiagnosticsPage`.
**Flag:** `STACKY_CLIENT_PROFILE_HEALTH_ENABLED` — **default ON**. Solo lectura y cálculo puro: no llama a ningún modelo (no cae en A), no escribe en ningún sistema del operador y no le saca ninguna decisión (no cae en B). *La v1 la declaraba OFF con el motivo "default seguro", invalidado.*
**Test/gate (en `tests/test_client_profile.py` y `tests/test_client_profile_endpoints.py`):**
- `test_score_weights_by_consumption` — un path faltante con `agents={3 agentes}` baja el score más que tres paths de solo-servicio faltantes.
- `test_reports_exactly_top3_missing`
- `test_stale_uses_90_day_threshold`
- `test_health_endpoint_returns_score_and_findings`

### 34.C2 — Jueces deterministas de consistencia (sin LLM)
**Qué:** `services/client_profile_judges.py` → `judge_profile(profile, project_name) -> list[Finding]`, con `Finding = {severity: "critical"|"warning"|"info", path: str, message: str}`.
Chequeos (lista **cerrada**, no "etc."):
1. `language.primary == "csharp"` con `build.tool in {"maven","gradle","npm"}` → `critical`.
2. `database.type` vs `database.connection_kind` incompatibles (tabla literal en el módulo) → `critical`.
3. Ruta de `code_layout.*` o `docs_indexes.*` con `exists == False` según `resolve_layout_paths` → `warning`.
4. `build.online_solutions` / `build.batch_proj_glob` que no matchean ningún archivo bajo `workspace_root` → `warning`.
5. `_meta.fields.<path>.confidence` fuera de `[0,1]` o `source` fuera del enum de §5.2 → `warning`.
6. `tracker_state_machine` que referencia un estado ausente del board → **`info` en tanda 1** (requiere el lector de tracker de B2; sube a `critical` en tanda 2).
**Flag:** `STACKY_CLIENT_PROFILE_JUDGES_ENABLED` — **default ON**. Determinista, milisegundos, cero llamadas a modelo, solo reporta. No cae en (A) ni en (B).
**Test/gate (en `tests/test_client_profile.py`):** `test_csharp_with_maven_is_critical` · `test_missing_path_is_warning` · `test_coherent_rs_profile_has_zero_findings` · `test_confidence_out_of_range_is_warning` · `test_judges_never_mutate_profile`.

### 34.C3 — Gate de coherencia pre-run — **DIFERIDO a tanda 2**
**Por qué se difiere (C6):** la v1 decía "alimenta el predicado al gate de precondiciones del 30/G0.1" **sin nombrar archivo ni función**. Los anclajes del doc 30 tienen la misma antigüedad que los de este plan (supervivencia medida: 1 de 21). Un modelo menor no puede implementar "alimenta el predicado": tendría que **inferir** el seam, y eso es exactamente lo que este plan prohíbe.
**Precondición para desdiferirlo:** localizar y citar **por símbolo** la función de preflight del doc 30 en `backend/`, verificada abriendo el archivo. Sin eso, el ítem no entra.
**Flag cuando entre:** `STACKY_CLIENT_PROFILE_PRERUN_GATE_ENABLED` — **la ÚNICA flag de este plan que nace OFF**. Justificación escrita, categoría **(B)**: *bloquear un run que el operador ya lanzó le saca la decisión al operador*. Es el mismo corte de precedente que `STACKY_PIPELINE_NL_EDIT_ENABLED` (ON, propone) vs `..._COMMIT_ENABLED` (OFF, ejecuta): acá **`..._JUDGES_ENABLED` reporta y nace ON; `..._PRERUN_GATE_ENABLED` bloquea y nace OFF**.
**Comportamiento cuando esté ON:** bloquea solo ante `critical`; todo lo demás pasa como warning anotado; el operador puede forzar el run.

---

## FASE D — Uso activo en ejecución (inyección dirigida, deduplicada y sin metadata)

### 34.D1 — Vista del perfil por agente — cableado COMPLETO del seam
**Qué:** `project_profile_for_agent(profile, agent_type) -> dict` en `services/client_profile_consumption.py`, que proyecta usando `INJECTABLE_PATHS` (34.A4).
**Por qué:** D4/D5/D9 — el FunctionalAnalyst recibe hoy `msbuild_path`, `port_residue` y los `devops_*`.
**Corrección v1 (C4) — el defecto de mecanismo:** `build_client_profile_block(project_name, log=None)` **no recibe `agent_type`**. La v1 decía "filtrar por la vista del `agent_type`" sobre un parámetro **que no existe**. Sin cablearlo, el módulo queda construido, testeado, verde y **jamás llamado en producción**.
**Cómo (exacto — los 4 puntos, ninguno opcional):**
1. `services/context_enrichment.py` · `build_client_profile_block`: firma pasa a `build_client_profile_block(project_name, log=None, *, agent_type: str | None = None)`. **Keyword-only con default `None`** para no romper los call sites posicionales existentes. `agent_type=None` ⇒ dump completo (comportamiento actual).
2. `services/context_enrichment.py` · `_inject_client_profile_block`: agregar `agent_type` a la firma y pasarlo al seam.
3. `services/context_enrichment.py` · `enrich_blocks` (que **ya recibe `agent_type`**): pasarlo en la llamada a `_inject_client_profile_block` (~línea 110). **Este es el paso que la v1 omitía y sin el cual todo lo demás es inerte.**
4. `api/agents.py` · `open_chat` (llamada a `build_client_profile_block` con `log=lambda...`, ~línea 1670): pasar el `agent_type` del agente que se está abriendo. **Es el camino interactivo de GitHub Copilot y NO pasa por `enrich_blocks`** — si no se cablea acá, Copilot-chat recibe un perfil distinto al de los otros dos runtimes (C16, paridad).
   El tercer call site — el resumen de pre-vuelo en `api/agents.py` (~línea 2099, llamada posicional de un solo argumento) — **queda con `agent_type=None` a propósito**: es un resumen recortado a 1500 chars, no un prompt de agente.
**Default conservador:** un path **no mapeado** en `FIELD_CONSUMERS` **se incluye** (allowlist con fallback inclusivo). Solo se excluye lo que está explícitamente en el eje B y **ausente** del eje A.
**Flag:** `STACKY_CLIENT_PROFILE_SCOPED_INJECTION_ENABLED` — **default ON**. No llama a ningún modelo, no escribe nada, no decide nada. *La v1 la declaraba OFF por "retro-compat byte-idéntica", motivo invalidado.* El riesgo real (quitarle un campo a un agente) se cubre con el fallback inclusivo y con `test_unmapped_field_is_kept`, no con un OFF.
**Test/gate (en `tests/test_context_enrichment_client_profile.py`):**
- `test_scoped_view_drops_only_unconsumed` — con `agent_type="functional"`, el contenido **sí** trae `code_layout` y **no** trae `msbuild_path` ni `devops_publication_presets`.
- `test_unmapped_field_is_kept` — un path inventado dentro de `extensions` sobrevive.
- `test_agent_type_none_is_full_dump` — byte-idéntico al comportamiento previo.
- `test_enrich_blocks_threads_agent_type` — monkeypatch de `build_client_profile_block` que **registra los kwargs recibidos**; asertar `agent_type == "developer"` tras llamar a `enrich_blocks(agent_type="developer", ...)`. *(Este test es el que impide que el módulo quede sin cablear.)*
- `test_open_chat_threads_agent_type` — mismo patrón sobre el call site de `api/agents.py`.

### 34.D2 — Frescura y prioridad — SIN primitiva nueva de poda
**Corrección v1 (C14):** la v1 pedía "podar subsecciones de baja confianza dentro del bloque". **Esa primitiva no existe:** el budget y el dedup operan a granularidad de **bloque**, vía `_BLOCK_PRIORITY` y `_HIGH_PRIORITY_THRESHOLD = 75`. Construirla es un motor nuevo dentro de `context_enrichment`.
**Qué (rediseñado):** partir en **dos bloques**, usando la maquinaria existente tal cual:
- `client-profile` (prioridad **95**, sin cambios): solo valores con `_meta.source == "operator"` o sin `_meta` (o sea, todo lo de hoy). **Nunca podable.**
- `client-profile-inferred` (id NUEVO, prioridad **60** en `_BLOCK_PRIORITY`): valores con `source` inferido/aprendido **no confirmados**, cada línea anotada con `⚠ sin confirmar desde AAAA-MM-DD`. Al estar **por debajo de 75**, la maquinaria existente lo poda y dedupea sin una línea de motor nuevo.
**Flag:** cubierta por `..._SCOPED_INJECTION_ENABLED`. **Diferido a tanda 2** (no hay valores inferidos hasta que exista la Fase B).
**Test/gate:** `test_inferred_block_priority_is_below_threshold` · `test_confirmed_values_stay_in_priority_95_block`.

### 34.D3 — Anclaje a la realidad en tiempo de inyección
**Qué:** al armar el bloque, correr los jueces de existencia (C2, chequeos 3 y 4) en **modo anotación**: una ruta que no resuelve se inyecta con `⚠ ruta no encontrada en el workspace` en vez de como verdad.
**Flag:** `STACKY_CLIENT_PROFILE_INJECT_GROUNDING_ENABLED` — **default ON**. Es aditivo (anota, no quita), determinista y sin modelo. **Diferido a tanda 2** por costo de I/O: exige medir el `stat()` por ruta dentro del camino caliente de todo run.
**Test/gate:** `test_missing_path_is_annotated_not_removed` · `test_annotation_adds_no_more_than_one_line_per_path`.

---

## FASE E — Autocorrección y aprendizaje desde el uso (DIFERIDA A TANDA 2)

### 34.E1 — Detector de drift post-run → parche sugerido
**Qué:** tras un run, si el output reveló un valor más verdadero que el del perfil (el `.sln` real, una ruta efectiva), generar un parche sugerido con `source="learned:run"`, **pendiente de aprobación**, en una cola que la UI muestra.
**Cómo:** post-hook determinista (sin LLM). **Precondición para implementarlo:** citar por símbolo el chokepoint de fin de ejecución verificado en código — el seam correcto es `on_execution_end` / `register_post_hook`, **no** `run_on`. Nombrar el archivo exacto al desdiferirlo.
**Flag:** `STACKY_CLIENT_PROFILE_LEARN_FROM_RUNS_ENABLED` — **default ON**. Corre en un post-hook pero **no llama a ningún modelo** (no cae en A: la categoría exige llamar a un modelo sin que el operador pida nada) y **no escribe en ningún sistema real**: deja una sugerencia dentro de Stacky que el operador aprueba (no cae en B). *La v1 la declaraba OFF por "default seguro", invalidado.*
**Caps obligatorios:** máximo **20** rutas verificadas por run y **200 ms** de presupuesto; agotado, se omite en silencio.
**Riel:** propone, **nunca** aplica. Un valor con `_meta.source == "operator"` **jamás** se sobrescribe.
**Test/gate:** `test_drift_produces_suggestion_not_write` · `test_operator_confirmed_field_is_not_overwritten` · `test_posthook_respects_budget`.
**Riesgo conocido a mitigar:** un post-hook que toma la sesión de SQLite puede perder su trabajo en silencio si hay lock. La cola de sugerencias se escribe con reintento acotado y **loguea explícitamente** el fallo; no se traga la excepción.

### 34.E2 — Barredor de frescura — **ELIMINADO como ítem**
Absorbido por `score_completeness` (34.C1, campo `stale`). No necesitaba módulo, endpoint ni flag propios. **Una flag menos.**

---

## FASE F — Onboarding guiado + plantillas + UI (F1/F3 diferidos a tanda 2)

### 34.F1 — Asistente "Perfil en 3 pasos" — **TANDA 2**
**Qué:** (1) elegir `client_type` → (2) Stacky corre la inferencia (B5) y muestra la propuesta con procedencia → (3) el operador confirma/corrige solo lo crítico y ambiguo que marcan C1/C2.
**Cómo:** sub-componente `ClientProfileWizard.tsx`; el editor actual (1288 líneas, formulario + `advancedJson`) queda **intacto** y sigue siendo el camino por default hasta que el wizard esté verde. **Para estados, el wizard linkea a `StatesConfigPage.tsx`** (plan 216); no duplica esa configuración.
**Gate frontend:** `tsc` en **0 errores**. vitest/RTL no están instalados de forma confiable en este repo: **no se exigen tests de componente**, y un `.test.tsx` con RTL reporta "no tests" con **exit 0** (falso verde). El gate real es `tsc` + smoke visual manual.

### 34.F2 — Plantillas por tipo de cliente (`client_type`) — **TANDA 1**
**Qué:** materializar `STACK_TEMPLATES` (A1) + endpoint `GET /api/client-profile/stack-template?client_type=...`, espejo de `get_default_template` (`GET /client-profile/default`, en `api/client_profile.py`), + botón "Aplicar plantilla de stack" en el editor, análogo al "Aplicar template default" existente.
**Flag:** —
**Test/gate:** `tests/test_client_profile_endpoints.py::test_stack_template_endpoint_returns_rs_webforms` · `::test_stack_template_unknown_client_type_returns_400` · `tsc` en 0.

### 34.F3 — UI de confirmación por **PATCH**, no por PUT — **TANDA 2**
**Qué:** panel que muestra cada valor inferido/aprendido como **diff** (propuesto vs actual) con procedencia y confianza, y botones aceptar/editar/descartar **por campo**.
**Corrección v1 (C13):** la v1 decía "al aceptar, hace PUT". **El PUT reemplaza el perfil entero** (`put_client_profile` en `api/client_profile.py`): una edición concurrente en `StatesConfigPage` o en el panel de DevOps se pierde. El plan 98 ya construyó el contrato de escritura **parcial**.
**Cómo (exacto):**
1. Aceptar un campo ⇒ `PATCH /projects/<p>/client-profile/keys/<key>` (`patch_client_profile_key`).
2. `PATCHABLE_PROFILE_KEYS` en `services/client_profile_keys.py` hoy tiene **4** claves (`devops_pipeline_drafts`, `devops_publication_presets`, `devops_publication_settings`, `devops_environment_settings`). **Extenderla** con las claves confirmables por el wizard (`code_layout`, `language`, `build`, `docs_indexes`, `terminology`, `conventions`, `client_type`) y agregar el validador correspondiente en `validate_profile_key` — que hoy devuelve `f"key '{key}' no es parcheable."` para todo lo demás.
3. `_meta` se estampa server-side en el mismo PATCH (`source="operator"`, `confidence=1.0`).
**Test/gate:** `tests/test_client_profile_endpoints.py::test_patch_accepts_new_wizard_keys` · `::test_patch_rejects_unknown_key_with_existing_message` (mensaje **byte-idéntico** al actual) · `::test_patch_stamps_meta_source_operator` · `::test_discard_does_not_touch_profile`.

### 34.F4 — Flags visibles en `HarnessFlagsPanel` + registrar la flag maestra huérfana
**Qué:** registrar en `FLAG_REGISTRY` (`services/harness_flags.py`) las flags de §7.1 **y también `STACKY_INJECT_CLIENT_PROFILE`** (D11), que hoy gobierna todo el feature por `os.getenv` y es invisible desde la UI.
**Cómo — los 6 lugares por flag (registrar una flag NO es un lugar):**
1. `backend/config.py` — atributo con el default **efectivo**. *Sin esto, un consumidor que haga `getattr(config, "X", False)` se lleva el default del `getattr` y la flag queda **inerte** aunque esté en el registry.*
2. `services/harness_flags.py` · `FLAG_REGISTRY` — `FlagSpec(key, type="bool", label, description, group, default=True)`.
3. `services/harness_flags.py` · `_CATEGORY_KEYS` — **no existe categoría `client_profile`**; hoy hay 20 (`runtimes_cli`, `contexto_memoria`, …, `paridad_proveedores`). **Decisión: usar `contexto_memoria`**, donde ya vive `STACKY_INJECT_PROCESS_CATALOG`. No se crea una categoría 21 (evita tocar `CategorySpec` y sus tests de tier/intent).
4. `tests/test_harness_flags.py` · `_CURATED_DEFAULTS_ON` — **obligatorio para toda flag con `default=True`**; sin la curaduría, `test_default_known_only_for_curated` pasa de verde a rojo.
5. `.env.example` — una línea documentada por key.
6. `deployment/` — regenerar `harness_defaults.env` con su generador.
**Gates ajenos que se van a poner rojos (esperados, no son regresión):** `test_harness_flags_help` exige que la `description` contenga `"Si "` **sin tilde**; `env_read_meta` exige la entrada en `.env.example`. Verificar los dos **antes** de dar por cerrada la fase.
**Test/gate:** `tests/test_harness_flags.py::test_client_profile_flags_registered` — asertar por **igualdad exacta** el default de cada key nueva y la pertenencia a `_CURATED_DEFAULTS_ON`.
**Comando:** `& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_harness_flags.py -q`

---

## 6. Mecanismos transversales (resumen)

- **Inferencia → propuesta → confirmación:** las fuentes proponen; el resultado se **devuelve por GET** (nunca se persiste); F3 confirma **por PATCH por key**. Nada se fija sin el operador.
- **Procedencia y confianza:** `_meta` es el sustrato de scoring, frescura y aprendizaje — y **nunca viaja al prompt**.
- **Dos ejes de consumo:** agente (decide qué se inyecta) y servicio (decide qué NO se puede deprecar). Confundirlos era el defecto central de la v1.
- **Jueces deterministas (cero LLM):** reportan siempre (ON); **bloquear es otra flag, y esa nace OFF**.
- **Inyección dirigida, deduplicada y anotada:** allowlist del eje A + fallback inclusivo + `process_catalog` una sola vez + bloque secundario podable para lo no confirmado.

---

## 7. Flags y rollout

### 7.1 Tabla de flags — regla vigente aplicada (**default ON salvo (A) o (B) por escrito**)

| Flag | Default | Tanda | Justificación |
|---|---|---|---|
| `STACKY_INJECT_CLIENT_PROFILE` *(existente, hoy env-only)* | **ON** | 1 | Ya es `true` de hecho. Solo se **registra** para que sea configurable por UI (riel doc 33). |
| `STACKY_CLIENT_PROFILE_HEALTH_ENABLED` | **ON** | 1 | Cálculo puro + un GET. No llama a modelo ⇒ no (A). No escribe ni decide ⇒ no (B). |
| `STACKY_CLIENT_PROFILE_JUDGES_ENABLED` | **ON** | 1 | Determinista, solo reporta. No (A), no (B). |
| `STACKY_CLIENT_PROFILE_SCOPED_INJECTION_ENABLED` | **ON** | 1 | Proyecta el bloque. No (A), no (B). El riesgo se cubre con fallback inclusivo + test, no con OFF. |
| `STACKY_CLIENT_PROFILE_INFERENCE_ENABLED` | **ON** | 2 | Determinista, solo lectura, **disparada por el operador** desde el wizard. No (A), no (B). |
| `STACKY_CLIENT_PROFILE_INFERENCE_SOURCES` *(csv)* | `repo,docs,memory,tracker` | 2 | Selección de fuentes. `tracker` hace red, pero **solo cuando el operador abre el wizard**. |
| `STACKY_CLIENT_PROFILE_LEARN_FROM_RUNS_ENABLED` | **ON** | 2 | Post-hook determinista sin modelo; deja una sugerencia dentro de Stacky. No (A), no (B). Caps de 20 rutas / 200 ms. |
| `STACKY_CLIENT_PROFILE_INJECT_GROUNDING_ENABLED` | **ON** | 2 | Anota, no quita. Determinista. No (A), no (B). |
| `STACKY_CLIENT_PROFILE_PRERUN_GATE_ENABLED` | **OFF** | 2 | **Categoría (B): le saca la decisión al operador** — bloquea un run que él ya lanzó. Mismo corte que `STACKY_PIPELINE_NL_EDIT_ENABLED` (ON, propone) vs `..._COMMIT_ENABLED` (OFF, ejecuta). |
| `STACKY_PROJECT_AUTOPROFILE_ENABLED` *(existente, hoy OFF)* | **→ ON** | 2 | Lectura determinista de disco sin modelo. Su `False` actual es **deuda declarada del plan 42**, no un precedente. |

**Total: 7 flags nuevas (v1 proponía 14), 1 sola nace OFF, 2 existentes corregidas.** Eliminadas por rediseño: `NEUTRAL_DEFAULT` (resuelto por construcción, §5.3), las 4 `INFER_*` por fuente (colapsadas en un CSV), `COMPLETENESS` (fusionada en `HEALTH`), `FRESHNESS_ANNOTATION` (fusionada en el bloque secundario D2), `STALENESS_REPORT` (absorbida por `score_completeness`).

### 7.2 Rollout

1. **F0 + A1-A4 + F2** — arnés, default honesto, `_meta` invisible, migrador, registro de dos ejes, plantillas de stack.
2. **C1-C2 + F4** — salud + jueces (ambos ON, solo reportan) + flags visibles en el panel.
3. **D1** — inyección dirigida cableada en los 3 call sites. Medir K3 y K6.
4. *(tanda 2)* B1-B5 + F1/F3 + D2/D3 + E1 + C3.

**Restricciones vinculantes (no relitigar):**
- Flag nueva → los **6 lugares** de F4 en el mismo PR; **default ON salvo (A)/(B) por escrito**.
- Sin secretos en el perfil; solo lectura contra el tracker; mono-operador sin RBAC; claves de metadata existentes son contrato (agregar, nunca renombrar).
- **Backend:** `pytest` **por archivo** con `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe` (py3.11.9). `pytest tests` completo **NO es veredicto**; el gate real es `backend/scripts/run_harness_tests.{sh,ps1}`. `pytest -k` sin match **da exit 0** ⇒ todo criterio de test debe asertar el **número de casos seleccionados**, no solo el exit code.
- **Frontend:** el gate es `tsc` en **0 errores**. vitest/RTL no son confiables acá.
- Todo archivo de test nuevo se registra en los **dos** ratchets (`.sh` y `.ps1`), y la ruta debe **existir** antes de agregarla.
- Sin deps npm/py nuevas; sin FTS5.

---

## 8. Riesgos, mitigaciones y decisiones abiertas

| Riesgo | Mitigación |
|---|---|
| **La inferencia se toma como verdad.** | Nunca se aplica sola; el resultado se devuelve por GET y se acepta por PATCH por campo; cada valor lleva procedencia + confianza. |
| **El default honesto cambia lo que reciben los proyectos RS.** | Resuelto **por construcción** (§5.3): `client_type` se resuelve a `rs_webforms` para todo perfil pre-34 o ausente ⇒ default efectivo byte-idéntico, probado por `test_legacy_profile_default_is_byte_identical`. Sin flag. |
| **Eliminar campos rompe un agente o un servicio.** | Auditoría de **dos ejes**; se marca *deprecated* en `_meta`, no se borra. |
| **La inyección dirigida le quita un campo a un agente.** | Fallback inclusivo para paths no mapeados + `test_unmapped_field_is_kept` + `test_scoped_view_drops_only_unconsumed`. |
| **`_meta` infla el prompt.** | `NON_INJECTABLE_KEYS` lo excluye del serializado + tope de 200 paths + `test_meta_never_appears_in_injected_block` con guarda positiva previa. |
| **El escaneo de repo no termina.** | Caps numéricos (depth 4 / 20k archivos / 5 s), deny-set literal, `followlinks=False`, de-dup por `realpath` — este árbol tiene una junction `N:` ↔ `C:\desarrollo`. |
| **El módulo se construye, pasa verde y nunca se cablea.** | `test_enrich_blocks_threads_agent_type` y `test_open_chat_threads_agent_type` asertan el **call site de producción**, no el símbolo. El gate de "implementado" es **existe un consumidor de producción**, excluyendo `tests/`, el propio módulo y los baselines de ratchet. |
| **El post-hook de E1 pierde la sugerencia por lock de SQLite.** | Reintento acotado + log explícito del fallo; prohibido tragarse la excepción. |
| **GitLab queda afuera.** | `DEFAULT_TEMPLATES` tiene 4 trackers; A1 neutraliza los 4; B2 despacha por `get_project_tracker_type` con fallback `tracker_no_soportado`. |

**Decisiones abiertas para el operador:**
1. **Categoría de flags:** ¿queda `contexto_memoria` para las 7, o preferís una categoría `client_profile` nueva (implica tocar `CategorySpec` y sus tests de tier/intent)? *(Recomendado: `contexto_memoria`.)*
2. **`column_prefix_len`:** confirmado sin consumidor en ninguno de los dos ejes. ¿Se marca *deprecated* ahora o se espera una v3?
3. **`readonly_user_hint`:** el `.agent.md` del TechnicalAnalyst lo consume, pero duplica el `user` de `auth/db_readonly.json`. ¿Se deriva server-side (y se quita del perfil) o se deja?
4. **Tanda 2:** ¿se arranca apenas cierre la tanda 1, o se espera a medir K3/K6 en runs reales?

---

## 9. [ADICIÓN ARQUITECTO]

### ADICIÓN 1 — Contrato de perfil por agente, **ejecutable y bidireccional** (revive metadata muerta del plan 133)

**Hallazgo que la habilita:** `stacky_requires_client_profile` está declarado en 5 `.agent.md` (`backend/Stacky/agents/{Developer,FunctionalAnalyst,TechnicalAnalyst.v2,BusinessAgent}.agent.md:7` y `backend/agents/Developer.agent.md:7`) y tiene **cero lectores** en todo el código (`.py`, `.ts`, `.tsx`). Es un contrato **declarado y muerto**: el plan 133 lo escribió y nadie lo cableó.

**Qué se agrega (todo en tanda 1, costo marginal ~0 porque el módulo de A4 ya existe):**
1. `agent_requires_client_profile(agent_type) -> bool | None` en `services/client_profile_consumption.py` — parsea el frontmatter desde `backend/Stacky/agents/` (la ruta que **lee el runtime**, no `DeployStackyAgents`).
2. **Test bidireccional anti-drift** en `tests/test_client_profile_consumption.py`:
   - *(ida)* todo agente con `stacky_requires_client_profile: true` tiene **≥1 path** mapeado a él en el eje A de `FIELD_CONSUMERS`;
   - *(vuelta)* todo `agent_type` que aparece en el eje A de `FIELD_CONSUMERS` corresponde a un `.agent.md` que declara `true`.
   Si alguien agrega un agente o cambia el mapa, el test rompe. **El mapa central y el frontmatter dejan de poder desincronizarse.**
3. **Uso en runtime:** `build_client_profile_block` con `agent_type` cuyo `.agent.md` declara `false` (hoy: `BusinessAgent`) **devuelve `None`** — ese agente deja de cargar un bloque de prioridad 95 que su prompt nunca lee. Ahorro inmediato, medible, sin tocar ningún prompt.

**Por qué respeta los rieles:** no agrega autonomía, no escribe en ningún sistema, no toca RBAC, es determinista y funciona igual en los 3 runtimes (el frontmatter es del agente, no del runtime).
**Criterio binario:** `test_agent_declaring_false_gets_no_block` — con `agent_type="business"`, `build_client_profile_block(...) is None`; con `agent_type="developer"`, devuelve un bloque no vacío.

### ADICIÓN 2 — Deduplicación medida: `process_catalog` viaja **DOS VECES** en cada run

**Hallazgo:** `build_client_profile_block` serializa el perfil **entero** — incluido `process_catalog` — a prioridad **95**; y `build_process_dictionary_block` arma **además** un bloque `process-catalog` a prioridad **78** con la misma información en prosa. `_dedup_blocks` **no lo detecta**: normaliza línea a línea y los textos difieren (`"name": "Mul2Bane",` vs `- Mul2Bane [batch]: propósito`). Resultado: en **todo run de todo proyecto con catálogo no vacío**, el catálogo se paga dos veces, y la copia cara (95) es la que **nunca se poda**.

**Qué se agrega (tanda 1, dentro de D1):** `process_catalog` entra en `NON_INJECTABLE_KEYS` **condicionalmente**: se excluye del dump de `client-profile` **si y solo si** el bloque `process-catalog` va a estar presente (es decir, si `STACKY_INJECT_PROCESS_CATALOG` está ON y el catálogo no está vacío). Si el bloque dedicado no va, el dump lo conserva — cero pérdida de información en cualquier combinación de flags.

**Por qué vale:** es la única mejora de este plan que **reduce tokens hoy, sin inferencia, sin `_meta` y sin wizard** — y es la que menos código toca.
**Criterio binario (K6):** `tests/test_context_enrichment_client_profile.py::test_process_catalog_not_duplicated` — con un perfil con catálogo de 3 procesos y `STACKY_INJECT_PROCESS_CATALOG` ON: asertar **primero** que el bloque `process-catalog` existe y contiene los 3 nombres, y **después** que `"process_catalog"` no aparece en el contenido de `client-profile`. Y el recíproco: con la flag OFF, `"process_catalog"` **sí** está en el dump.

---

## 10. CORTE declarado (el plan v1 no era implementable en una tanda)

**Diagnóstico de tamaño:** la v1 pedía 14 flags × 6 lugares de registro cada una (84 ediciones + 14 curaciones + 14 líneas de `.env.example` + regeneración de `harness_defaults.env`), 8 módulos nuevos, un migrador de schema, un wizard de frontend y un gate pre-run sobre un seam no verificado. No entra en una tanda, y una tanda parcial deja módulos verdes y sin cablear.

**TANDA 1 — este plan, ahora (F0, A1-A4, C1, C2, D1, F2, F4 + ADICIÓN 1 + ADICIÓN 2):**
- 3 flags nuevas (todas ON) + 1 existente registrada.
- 2 módulos nuevos (`client_profile_consumption.py`, `client_profile_quality.py`, `client_profile_judges.py` — 3, ninguno con dependencias externas).
- 1 archivo de test nuevo; el resto va a los 4 archivos existentes ya registrados en F0.1.
- **Valor entregado sin ninguna inferencia:** default honesto sin regresión, `_meta` sin contaminar el prompt, migrador correcto, jueces + salud reportando, inyección dirigida cableada, y **dos ahorros de tokens medibles** (bloque suprimido para agentes que no lo leen; `process_catalog` deduplicado).

**TANDA 2 — diferido (B1-B5, C3, D2, D3, E1, F1, F3):** toda la inferencia, el wizard, el aprendizaje post-run y el gate pre-run. Su diseño ya está cerrado arriba y **no debe relitigarse**; lo que falta es (a) verificar por símbolo el seam de preflight del doc 30 y el chokepoint de fin de ejecución, y (b) medir K3/K6 de la tanda 1 antes de sumar superficie.

**El número del plan no cambia y no se parte en archivos nuevos:** la tanda 2 es una segunda iteración de **este** documento.

---

## 11. Ítems diferidos / no-objetivos

- **Auto-confirmación de inferencias de alta confianza** sin paso del operador: **no-objetivo permanente** (choca con la regla 11).
- **Perfil multi-repo / multi-board por proyecto:** fuera de scope (un proyecto = un `config.json`).
- **Editor visual de `extensions`** más allá de la vista JSON (`advancedJson`): diferido.
- **Borrado físico de campos *deprecated*:** diferido a una v3 explícita tras la auditoría de dos ejes.
- **Huella de regresión en `docs/sistema/error_fingerprints.json`:** agregar una huella para el modo de fallo "bloque `client-profile` ausente para un agente que lo declara requerido" al cerrar la tanda 1. *(MENOR — no bloquea.)*
