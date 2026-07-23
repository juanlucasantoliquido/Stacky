# Plan 216 — Centralización de la configuración de estados en el Perfil del Cliente, dropdowns de estados reales y sección "Estados" independiente

**Estado:** CRITICADO v2 — APROBADO-CON-CAMBIOS (2026-07-23)
**Autor:** StackyArchitectaUltraEficientCode
**Depende de:** ninguno para implementarse. **Coordina con:** Plan 208 (matriz `by_work_item_type`) — ver §3.1 "Contrato de coherencia con 208".

---

## 0. Historial de versiones — v1 -> v2 (2026-07-23)

Revisión adversarial (juez + arquitecto). Veredicto: **APROBADO-CON-CAMBIOS** (sin bloqueantes; IMPORTANTES corregidos). Anclas re-verificadas contra código real: `flow_config_store.py` (símbolos y líneas OK), `client_profile.py` service (`save_client_profile:315` valida TODO el perfil y lanza; `validate_client_profile:185` preserva keys desconocidas vía deepcopy) y api (`put_client_profile:148`), `SettingsPage.tsx:150,190-193,246`, `ClientProfileEditor.tsx:404,461,992-993`, `FlowConfigPage.tsx:344-347,357`, `harness_flags.py:70,238`, `config_transfer.py:296`. Cambios aplicados:

- **C1 (IMPORTANTE):** la migración lazy corre DENTRO de un path de LECTURA (`_read_raw`) y escribe vía `save_client_profile`, que valida el perfil COMPLETO (`client_profile.py:315-331`) y lanza `ClientProfileError`. Un perfil con errores bloqueantes preexistentes en OTRA sección, o un `flow_config.json` editado a mano con `agent_type` inválido / `ado_state` duplicado, rompía `GET /api/flow-config` con 500 — el legacy jamás falla en lectura. Fix: la migración SANEA las reglas legacy (`_sanitize_rules`: descarta inválidas con warning, conserva válidas) y ante CUALQUIER excepción al escribir cae al dict legacy SIN migrar (la lectura nunca rompe; se reintenta en el próximo acceso). Tests nuevos en F1.
- **C2 (IMPORTANTE):** la mitigación v1 de R3 (invalidar `["client-profile", projectName]`) NO cerraba la ventana real de pisado: el editor de perfil guarda su draft en `useState` LOCAL (`baseProfile`, `ClientProfileEditor.tsx:461`) y una invalidación de cache no refresca ese draft. Secuencia rota: abrir editor (GET t0) → editar reglas en Estados (t1) → Guardar perfil → PUT full-object con `state_flow` de t0 → reglas revertidas en silencio. Fix determinista de DOS lados: backend merge-preserve en `put_client_profile` (payload sin la key ⇒ se preserva la almacenada, F1) + las UIs NUNCA envían `state_flow` en sus PUT (F2 editor la elimina al ingerir el GET; F3 la quita antes del PUT). Test `test_put_perfil_sin_state_flow_preserva_reglas`.
- **C3 (IMPORTANTE):** el criterio de aceptación de F2 ("0 hits en copys de usuario; comentarios de código pueden quedar") no era binario — exigía juicio humano, y el `<h2>` de `FlowConfigPage.tsx:357` más el comentario de `PipelineStatus.tsx:72` seguían matcheando el grep. Fix: se renombra también el `<h2>` legacy y el comentario; el criterio pasa a grep = **0 hits totales** en `frontend/src` (binario puro, sin excepciones interpretables).
- **C4 (IMPORTANTE):** F0 tenía una instrucción condicional ("si la categoría aún no existe… usar la primera que aplique") — un "según corresponda" encubierto que hacía inferir a un modelo menor. VERIFICADO: la categoría `flujo_funcional` YA existe hoy (`harness_flags.py:70` `CategorySpec("flujo_funcional", ...)`; `:238` su tupla en `_CATEGORY_KEYS`), independiente de que 208 no esté implementado. Instrucción ahora categórica.
- **C5 (MENOR):** `TicketBoard.tsx` está siendo modificado por una sesión paralela (colisión conocida de los planes 212/213): los copys a corregir en F2 se localizan por GREP DEL LITERAL, nunca por número de línea.
- **C6 (MENOR):** `statesConfigModel.ts` usaba los tipos `CoherenceIssue` y `Machine` sin definirlos. Ahora se declaran exportados, literales, en el propio archivo.
- **C7 (MENOR):** el plan mata la clase de error "estado tipeado inexistente" (`state_not_in_tracker`) pero no registraba su huella. F4 agrega la entrada en `docs/sistema/error_fingerprints.json` (convención de huellas de regresión).
- **C8 (MENOR):** la semántica de retorno de `seed_defaults_if_empty` cuando la migración cae al fallback legacy (C1) quedaba indefinida. Fijada: devuelve lo que devuelva el cuerpo legacy actual.
- **[ADICIÓN ARQUITECTO] Espejo legacy para rollback SIN pérdida:** v1 tenía un agujero de rollback real: editar reglas con flag ON y luego apagar la flag volvía al `flow_config.json` VIEJO (stale) — el operador perdía sus ediciones. Ahora, con flag ON, cada ESCRITURA de reglas (acto explícito del operador) también actualiza `flow_config.json` como espejo best-effort (try/except, nunca rompe el guardado). Apagar la flag ⇒ estado idéntico al último guardado. La MIGRACIÓN en sí sigue sin tocar el archivo (la propiedad "legacy intacto" se preserva donde importa: ningún acto automático pisa una config buena).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo):** hoy la configuración de estados del tracker vive DUPLICADA en dos ubicaciones con dos storages y dos UX distintas: (a) la pestaña **Configuración → Flujo** (`FlowConfigPage.tsx`, reglas `ado_state → agent_type` persistidas en `projects/<NAME>/flow_config.json` vía `services/flow_config_store.py`) y (b) la sección **"Máquina de estados del tracker"** enterrada dentro del editor de Perfil del Cliente (`ClientProfileEditor.tsx:992-1004`, key `tracker_state_machine` dentro de `client_profile` en `projects/<NAME>/config.json`), donde además los estados se tipean como **texto libre** (`TrackerRoleField`, `ClientProfileEditor.tsx:416-436`) con riesgo de typo/alucinación. Este plan centraliza TODO el mapeo de estados en el **perfil del cliente** (única fuente de verdad, con migración automática e idempotente del JSON legacy), convierte todos los campos de estado en **dropdowns poblados con los estados reales del proyecto** (reusando `GET /api/projects/<name>/tracker-states`, exactamente como ya lo hace la ventana de Flujo en `FlowConfigPage.tsx:102-116`), elimina la configuración de estados de la pestaña "Flujo" y la reagrupa junto con la "Máquina de estados" en una **sección independiente "Estados"** dentro del módulo Configuración, con una pasada de UX (copys, validación visible, coherencia entre reglas y máquina).

**KPI / impacto esperado:**
- Fuentes de verdad del mapeo de estados: **2 → 1** (todo en `client_profile`; con flag ON `flow_config.json` ya no se LEE — queda como espejo de rollback que solo se escribe junto al perfil, [ADICIÓN ARQUITECTO]).
- Campos de estado de texto libre en el perfil: **5 por rol → 0** (todos dropdowns con estados reales del tracker).
- Warnings `state_not_in_tracker` por typo del operador (`task_states.py:171`): tienden a **0** (imposible tipear un estado inexistente desde la UI).
- Pantallas que el operador debe visitar para configurar estados: **2 → 1**.
- Trabajo manual de migración del operador: **0** (automática, lazy, idempotente, no destructiva).

---

## 2. Por qué ahora / gap que cierra (evidencia real)

1. **Duplicación real, verificada en código.** El mapeo "estado ↔ agente" está expresado dos veces:
   - `services/flow_config_store.py:57-62` (`_DEFAULT_RULES_SEED`: `New→business`, `Active→developer`, …) persistido en `projects/<NAME>/flow_config.json` (`flow_config_store.py:96-108`), editado en `FlowConfigPage.tsx` (montada en `SettingsPage.tsx:246`, pestaña "Flujo" `SettingsPage.tsx:190-194`).
   - `client_profile.tracker_state_machine.<rol>.input_states` (qué estados toma cada agente) + `in_progress` / `blocked_state` / `next_state_ok`, editado en `ClientProfileEditor.tsx:992-1004` y consumido por `backend/harness/task_states.py:56-74` (`resolve_task_state_plan`) y por los prompts de agentes (`backend/Stacky/agents/Developer.agent.md:53`).
2. **UX inconsistente:** la pestaña Flujo ya puebla dropdowns con estados reales (`Projects.trackerStates`, `frontend/src/api/endpoints.ts:1781-1782` → `backend/api/projects.py:724-807` que combina `fetch_states()` de ADO + estados de BD + defaults por tracker), pero el perfil usa `<input>` de texto libre (`ClientProfileEditor.tsx:422-436`), lo que obligó a crear el validador defensivo de typos (`task_states.py:171-198`, warnings en `api/client_profile.py:229-237`).
3. **La "Máquina de estados" está enterrada** al fondo de un formulario gigante de perfil (sección 12ª, `ClientProfileEditor.tsx:992`), lejos de la pestaña "Flujo" que configura la otra mitad del mismo dominio.
4. **El Plan 208 (CRITICADO v2, sin implementar)** agrega `tracker_state_machine.<agent_type>.by_work_item_type` al perfil y exige dropdowns sin texto libre (208 §P7). Centralizar AHORA en el perfil deja un único lugar donde 208 monta su matriz — sin este plan, 208 heredaría el editor de texto libre y la dispersión en dos pestañas.
5. **`flow_config.json` no viaja en Exportar/Importar** (`services/config_transfer.py:294-297` solo transfiere `agent_workflow_configs`; cero menciones a flow_config): al moverlo dentro de `client_profile` (que vive en `projects/<NAME>/config.json`, `services/client_profile.py:247-283`) la config de flujo deja de perderse en transfers y backups de proyecto.

**Gap en una frase:** el mismo dominio (estados del tracker) tiene dos storages, dos pestañas y dos calidades de UX; este plan lo unifica en el perfil del cliente con dropdowns reales y una sola sección, sin romper ningún consumidor (`/api/flow-config` conserva su contrato).

---

## 3. Principios y guardarraíles (no negociables)

- **P1 — Contratos intactos:** la API pública de `flow_config_store.py` (`list_rules`, `create_rule`, `update_rule`, `delete_rule`, `resolve`, `seed_defaults_if_empty`) y el blueprint `/api/flow-config` (`backend/api/flow_config.py:50,61,122,185,206`) NO cambian de firma ni de shape de respuesta. Consumidores que no se tocan: `TicketBoard.tsx:936` (Run Sugerido), `PipelineStatus.tsx`, `backend/api/tickets.py`, `TopBar.tsx:132` (invalidación de cache).
- **P2 — Migración automática, idempotente y NO destructiva:** el JSON legacy se copia al perfil en el primer acceso; la MIGRACIÓN no borra, renombra ni pisa el archivo viejo, y si no puede escribir el perfil cae al legacy sin romper la lectura (C1). Las ESCRITURAS explícitas del operador con flag ON sí actualizan el archivo como espejo best-effort ([ADICIÓN ARQUITECTO]) para que el rollback (flag OFF) no pierda ediciones. Cero pasos manuales del operador.
- **P3 — Flag default ON por UI:** `STACKY_STATE_CONFIG_CENTRALIZED_ENABLED` (bool, default **ON**) registrada en el arnés y editable desde Configuración → Arnés. No aplica ninguna de las 4 excepciones duras (no bypassa revisión humana, no es destructiva —el legacy queda intacto—, no tiene prerequisito no garantizado, no reduce seguridad).
- **P4 — Human-in-the-loop:** nada se guarda sin que el operador apriete Guardar/Agregar; los borrados usan el undo con gracia existente (`scheduleUndoable`, patrón de `FlowConfigPage.tsx:297-319`). Las acciones de coherencia (F3) son sugerencias con botón, jamás automáticas.
- **P5 — Estados reales, nunca texto libre:** todos los dropdowns se pueblan de `GET /api/projects/<name>/tracker-states` (mismo mecanismo que la ventana de Flujo). Valores preexistentes que no estén en el tracker se conservan como opción marcada "(no existe en el tracker)" — patrón ya implementado en `FlowConfigPage.tsx:211-215`.
- **P6 — Mono-operador sin auth:** cero RBAC/multiusuario (`current_user` es un header sin validar).
- **P7 — Paridad de 3 runtimes:** los agentes consumen `client_profile` por inyección de contexto idéntica en Codex CLI / Claude Code CLI / Copilot (el prompt se compone ANTES de elegir runtime; los `.agent.md` referencian `client_profile.tracker_state_machine.*`, p. ej. `Developer.agent.md:53`). Este plan no toca esa inyección: solo garantiza que la data inyectada tenga una única fuente. Fallback por runtime = el mismo de hoy (perfil ausente ⇒ el agente advierte y continúa, `Developer.agent.md:73-74`).
- **P8 — Reusar, no reinventar:** query `["tracker-states", project]` compartida (staleTime 5 min, `FlowConfigPage.tsx:343-348`), riel GET→merge→PUT del perfil (`api/client_profile.py:114,147`), validador `validate_states_against_tracker` (`task_states.py:171`), `useConfirm`/Dialog canónico (plan 164), `scheduleUndoable` (plan 185), primitivas de formulario existentes.
- **P9 — TDD sin falsos verdes:** cada fase con tests nombrados, corridos POR ARCHIVO con el venv del repo; criterios binarios por comando.

### 3.1 Contrato de coherencia con el Plan 208

- Las claves del perfil NO cambian de nombre: `tracker_state_machine.<agent_type>.{input_states,in_progress,blocked_state,next_state_ok}` y (cuando 208 se implemente) `.by_work_item_type`. `resolve_task_state_plan` (`task_states.py:56`) sigue leyendo exactamente lo mismo.
- **Si 208 se implementa ANTES que 216:** su bloque UI "Estados por tipo de ticket" (208 F4, hoy destinado a `TrackerRoleField` en `ClientProfileEditor.tsx:404-438`) se muda tal cual al nuevo componente `TrackerRoleStateCard` de este plan (F3) — la key y el PUT son idénticos, solo cambia el archivo que lo renderiza.
- **Si 216 se implementa ANTES que 208:** el implementador de 208 debe montar su matriz en `frontend/src/pages/StatesConfigPage.tsx` (F2 de este plan) en lugar de `ClientProfileEditor.tsx`. Este plan deja un comentario ancla `{/* PLAN-208: matriz by_work_item_type va aquí */}` dentro de `TrackerRoleStateCard`.
- La centralización del storage (F1) es neutra para 208: 208 lee el perfil vía `load_effective_client_profile` y no toca `flow_config_store`.

---

## 4. Fases

> Orden de dependencia: **F0 → F1 → F2 → F3 → F4**. F0 y F1 son backend puros; F2-F4 frontend. Cada fase es shippeable sola.

### Nomenclatura fija (usar EXACTAMENTE estos nombres)

- Flag: `STACKY_STATE_CONFIG_CENTRALIZED_ENABLED` (bool, default **True**, categoría `flujo_funcional`).
- Key nueva del perfil: `client_profile.state_flow` con shape `{"version": "1.0", "rules": [{"id","ado_state","agent_type","on_failure_state","created_at","updated_at"}]}` (misma shape de regla que `flow_config_store.py:10-22,231-238`).
- Funciones nuevas backend: `state_flow_centralized_enabled()`, `_read_state_flow_from_profile(project_name)`, `_write_state_flow_to_profile(project_name, data)`, `migrate_legacy_flow_config(project_name)` — todas en `backend/services/flow_config_store.py`; `set_client_profile_state_flow(project_name, state_flow)` y `_check_state_flow(value)` en `backend/services/client_profile.py`.
- Componentes nuevos frontend: `frontend/src/pages/StatesConfigPage.tsx` (+ `.module.css`), `frontend/src/pages/statesConfigModel.ts` (lógica pura testeable), `TrackerRoleStateCard` y `StateSelect` (dentro de `StatesConfigPage.tsx`).
- Tests backend: `backend/tests/test_plan216_state_flow_store.py`, `backend/tests/test_plan216_migration.py`, `backend/tests/test_plan216_profile_schema.py` — los TRES se registran en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh`; si el meta-test `backend/tests/test_harness_ratchet_meta.py` lo exige, también en `backend/tests/harness_ratchet_allowlist.txt`).
- Test frontend: `frontend/src/pages/__tests__/statesConfigModel.test.ts` (vitest, POR ARCHIVO).

---

### F0 — Flag del arnés + esquema y validación de `state_flow` en el perfil

**Objetivo (1 frase):** registrar la flag maestra (default ON, editable por UI) y enseñar al validador del perfil la key `state_flow`, sin cambiar ningún comportamiento todavía.

**Valor:** habilita rollback sin redeploy y garantiza que un PUT del perfil con `state_flow` malformado se rechace con error claro.

**Archivos a editar (exactos):**
1. `backend/services/harness_flags.py` — agregar al `FLAG_REGISTRY`:
   ```python
   FlagSpec(key="STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", type="bool", group="global",
       label="Config de estados centralizada en el perfil del cliente",
       description="Las reglas estado→agente (Flujo) se leen y escriben en client_profile.state_flow con migración automática desde flow_config.json. OFF: comportamiento legacy byte-idéntico (archivo flow_config.json). Default ON.",
       default=True),
   ```
   y agregar la key a `_CATEGORY_KEYS` bajo la categoría `flujo_funcional` — **VERIFICADO (C4): la categoría YA existe hoy**: `harness_flags.py:70` (`CategorySpec("flujo_funcional", "Flujo funcional (Tasks)", ...)`) y `:238` (su tupla dentro de `_CATEGORY_KEYS`). Agregar la key a ESA tupla existente. NUNCA dejar la key sin categorizar: `test_every_registry_flag_is_categorized` queda rojo.
2. `backend/config.py` — dentro de `class Config`, junto al bloque del Plan 79 (`config.py:1186-1194`):
   ```python
   # Plan 216 — fuente única de la config de estados en client_profile.state_flow.
   # ON: flow_config_store lee/escribe el perfil (con migración lazy desde
   # flow_config.json). OFF: byte-idéntico al legacy (archivo JSON).
   STACKY_STATE_CONFIG_CENTRALIZED_ENABLED: bool = os.getenv(
       "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   ```
3. `backend/tests/test_harness_flags.py` — agregar `"STACKY_STATE_CONFIG_CENTRALIZED_ENABLED"` a `_CURATED_DEFAULTS_ON` (línea ~467; si el test `test_bounds_map_is_frozen` u otro ratchet ajeno ya está rojo por deuda foránea, NO tocar nada ajeno: agregar SOLO esta key — ver memoria del ratchet).
4. `backend/services/client_profile.py` — nueva función pura y wiring:
   ```python
   def _check_state_flow(value) -> list[str]:
       """Valida client_profile.state_flow. Devuelve lista de errores (strings).
       Tolerante: None/ausente => []. Estructura esperada:
       {"version": str, "rules": [{"id": str, "ado_state": str no vacío,
        "agent_type": str en VALID_AGENT_TYPES, "on_failure_state": str|None, ...}]}
       Errores: no-dict, rules no-list, regla no-dict, ado_state vacío,
       agent_type inválido, ado_state duplicado entre reglas."""
   ```
   Importar `VALID_AGENT_TYPES` desde `services.flow_config_store` (`flow_config_store.py:50-52`). Llamar `_check_state_flow(profile.get("state_flow"))` dentro de `validate_client_profile` (`client_profile.py:185`) y anexar los errores como **errores bloqueantes** (mismo canal que las secciones tipadas, `_check_section_type` `client_profile.py:135`). Además, nueva función `set_client_profile_state_flow(project_name, state_flow: dict) -> dict` que hace `profile = load_client_profile(project_name) or {}`, valida con `_check_state_flow` (lanza `ClientProfileError` si hay errores), asigna `profile["state_flow"] = state_flow` y retorna `save_client_profile(project_name, profile)`. Exportarla en `__all__` (`client_profile.py:462`).

**Tests PRIMERO — `backend/tests/test_plan216_profile_schema.py`:**
- `test_state_flow_ausente_no_valida_nada` → perfil sin `state_flow` ⇒ `validate_client_profile` sin errores nuevos.
- `test_state_flow_valido_pasa` → 2 reglas correctas ⇒ sin errores.
- `test_state_flow_no_dict_falla`, `test_regla_sin_ado_state_falla`, `test_agent_type_invalido_falla`, `test_ado_state_duplicado_falla`.
- `test_set_client_profile_state_flow_persiste_y_relee` (usar `tmp_path` + monkeypatch de `PROJECTS_DIR`, patrón de `test_client_profile.py`).
- `test_flag_registrada_default_on`: la key está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS`, en `_CURATED_DEFAULTS_ON`, y `config.config.STACKY_STATE_CONFIG_CENTRALIZED_ENABLED is True`.

**Comando exacto:** `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan216_profile_schema.py -q` (y re-correr `tests/test_harness_flags.py` por archivo).

**Criterio de aceptación (binario):** ambos comandos verdes; `grep -c "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED" backend/config.py` devuelve ≥1; `grep -n "state_flow" backend/services/client_profile.py` devuelve ≥3.

**Flag:** `STACKY_STATE_CONFIG_CENTRALIZED_ENABLED` default ON. **Impacto por runtime:** N/A (config pura, idéntica para los 3). **Trabajo del operador:** ninguno.

---

### F1 — Store centralizado con migración automática (backend)

**Objetivo (1 frase):** que `flow_config_store.py` lea/escriba `client_profile.state_flow` cuando la flag está ON, migrando el JSON legacy de forma lazy, idempotente y no destructiva, con la API pública y el blueprint `/api/flow-config` intactos.

**Valor:** una sola fuente de verdad; las reglas de flujo pasan a viajar en backups/transfers del proyecto; rollback trivial (flag OFF ⇒ legacy byte-idéntico, el archivo nunca se tocó).

**Archivos a editar:** `backend/services/flow_config_store.py` y `backend/api/client_profile.py` (merge-preserve, C2). NO tocar `backend/api/flow_config.py` (el contrato HTTP no cambia).

**Cambios exactos (pseudocódigo):**
```python
# gotcha 208-C1: leer SIEMPRE la INSTANCIA config.config, no la clase Config.
def state_flow_centralized_enabled() -> bool:
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", False))
    except Exception:
        return False

def _resolve_project(project_name):        # reusa la lógica de _config_file_for:96-108
    normalized = _normalize_project_name(project_name)
    if normalized and get_project_config(normalized): return normalized
    active = _normalize_project_name(get_active_project())
    if active and get_project_config(active): return active
    return None                            # sin proyecto ⇒ SIEMPRE path legacy (data/flow_config.json)

def _read_state_flow_from_profile(project_name) -> dict | None:
    from services.client_profile import load_client_profile
    profile = load_client_profile(project_name) or {}
    sf = profile.get("state_flow")
    return sf if isinstance(sf, dict) and isinstance(sf.get("rules"), list) else None

def _write_state_flow_to_profile(project_name, data) -> None:
    from services.client_profile import set_client_profile_state_flow
    data["updated_at"] = _now_iso()
    set_client_profile_state_flow(project_name, data)

def _sanitize_rules(data: dict) -> dict:
    """C1. Devuelve un dict {"version","rules"} SOLO con reglas válidas del legacy:
    descarta (con _log.warning por cada una) las que tengan agent_type fuera de
    VALID_AGENT_TYPES, ado_state vacío/no-string, o ado_state duplicado (gana la
    primera aparición). Nunca lanza. Un legacy editado a mano no puede romper la
    migración ni la validación del perfil."""

def migrate_legacy_flow_config(project_name) -> dict:
    """Idempotente. Si el perfil YA tiene state_flow => lo devuelve sin tocar nada.
    Si no: lee el legacy con la lógica EXISTENTE del cuerpo actual de _read_raw
    (que ya resuelve projects/<NAME>/flow_config.json con fallback a
    data/flow_config.json, flow_config_store.py:132-161); si tampoco hay legacy =>
    siembra _DEFAULT_RULES_SEED (mismas 4 reglas de :57-62). SANEA con
    _sanitize_rules (C1), escribe el resultado en el perfil, loguea
    "flow_config migrado a client_profile.state_flow (N reglas)" con _log.info
    y devuelve el dict.
    C1 — LA LECTURA NUNCA ROMPE: si set_client_profile_state_flow lanza
    (ClientProfileError por errores preexistentes en OTRA sección del perfil, o
    cualquier otra excepción), _log.warning y DEVOLVER el dict legacy saneado
    SIN migrar (se reintenta en el próximo acceso).
    El archivo legacy NO se borra ni renombra."""
```
- En `_read_raw(project_name)` (`:132`): PRIMERA línea nueva — `project = _resolve_project(project_name)`; si `state_flow_centralized_enabled()` y `project` no es None ⇒ `return migrate_legacy_flow_config(project)`. Caso contrario ⇒ cuerpo actual sin cambios.
- En `_write(data, project_name)` (`:164`): mismo guard; con flag ON y proyecto resuelto ⇒ `_write_state_flow_to_profile(project, data)` **y además espejo legacy best-effort ([ADICIÓN ARQUITECTO]):** ejecutar el cuerpo legacy actual de `_write` dentro de `try/except Exception: _log.debug("mirror legacy falló (best-effort)", exc_info=True)` para que `flow_config.json` quede sincronizado con lo último guardado (rollback flag OFF sin pérdida de ediciones); luego `return`. Caso contrario ⇒ cuerpo actual sin cambios. El espejo NUNCA puede hacer fallar el guardado del perfil.
- En `seed_defaults_if_empty` (`:311`): con flag ON y proyecto resuelto ⇒ `migrate_legacy_flow_config(project)` cubre el seed; devolver la cantidad de reglas escritas si el perfil no tenía `state_flow`, 0 si ya tenía; si la migración cayó al fallback legacy (C1), devolver lo que devuelva el cuerpo legacy actual (C8).
- El override de tests `_CONFIG_FILE != _DEFAULT_CONFIG_FILE` (`:97-98`) conserva prioridad ABSOLUTA (si un test seteó `_CONFIG_FILE`, se usa el archivo aunque la flag esté ON) — así los tests legacy (`test_flow_config.py`, `test_b2_transition_from_config.py`) siguen verdes sin tocar.

**Merge-preserve del PUT del perfil (C2, backend — `backend/api/client_profile.py`):** en `put_client_profile` (`api/client_profile.py:148`), inmediatamente ANTES de la llamada que persiste (la que termina en `save_client_profile`): 
```python
# Plan 216 C2 — un PUT full-object que NO trae state_flow jamás borra las reglas
# (el editor de perfil trabaja sobre un snapshot local stale; ver ClientProfileEditor.tsx:461).
from services.flow_config_store import state_flow_centralized_enabled
from services.client_profile import load_client_profile
if state_flow_centralized_enabled() and "state_flow" not in profile:
    stored = load_client_profile(project_name) or {}
    if "state_flow" in stored:
        profile["state_flow"] = stored["state_flow"]
```
Consecuencia deliberada: borrar reglas se hace SOLO desde la pestaña Estados (vía `/api/flow-config`), nunca omitiendo la key en un PUT del perfil — eso es lo que cierra la ventana de pisado.

**Casos borde (cubrir en tests):**
- Sin proyecto activo ni parámetro (`_resolve_project` → None) ⇒ path legacy global aunque la flag esté ON.
- Perfil inexistente (`load_client_profile` → None) ⇒ la migración crea el perfil mínimo `{"state_flow": ...}` vía `set_client_profile_state_flow` (F0 lo permite: perfil parcial es válido).
- `state_flow` presente pero corrupto (rules no-list) ⇒ tratar como ausente ⇒ re-migrar desde legacy (defensivo, sin lanzar).
- Legacy con reglas inválidas o perfil con errores en otra sección ⇒ sanear / caer al legacy sin lanzar (C1, ver docstrings).
- Doble llamada a `migrate_legacy_flow_config` ⇒ segunda es no-op (idempotencia).
- Flag OFF ⇒ ningún acceso a `client_profile` (assert con monkeypatch espía).

**Tests PRIMERO:**
- `backend/tests/test_plan216_state_flow_store.py`: `test_flag_on_crud_lee_y_escribe_perfil` (create/list/update/delete/resolve contra perfil en `tmp_path`), `test_flag_off_byte_identico_legacy` (mismos asserts que hoy sobre el archivo), `test_duplicate_state_sigue_409` (DuplicateStateError con storage perfil), `test_override_config_file_gana_a_flag` (prioridad del override de tests), `test_sin_proyecto_usa_legacy_global`, `test_write_flag_on_espeja_legacy` ([ADICIÓN ARQUITECTO]: tras `create_rule` con flag ON, `flow_config.json` del proyecto contiene la misma regla), `test_put_perfil_sin_state_flow_preserva_reglas` (C2: PUT del perfil SIN la key ⇒ `state_flow` almacenada sobrevive; usar el test client Flask contra `put_client_profile` con `PROJECTS_DIR` monkeypatcheado).
- `backend/tests/test_plan216_migration.py`: `test_migra_archivo_proyecto_a_perfil`, `test_migra_fallback_legacy_global`, `test_sin_legacy_siembra_defaults` (4 reglas seed), `test_idempotente_segunda_llamada_noop`, `test_archivo_legacy_queda_intacto` (bytes idénticos post-migración — la migración sola NO escribe el espejo; solo las escrituras del operador lo hacen), `test_state_flow_corrupto_se_remigra`, `test_legacy_con_regla_invalida_se_sanea` (C1: legacy con `agent_type` inválido + `ado_state` duplicado ⇒ migra solo las válidas, sin lanzar), `test_perfil_invalido_no_rompe_lectura_cae_legacy` (C1: perfil con error bloqueante en otra sección ⇒ `list_rules` devuelve las reglas legacy sin 500 y el perfil queda sin tocar).
- Regresión obligatoria por archivo: `tests/test_flow_config.py` y `tests/test_b2_transition_from_config.py` sin modificar.

**Comando exacto:** `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan216_state_flow_store.py -q && .venv/Scripts/python.exe -m pytest tests/test_plan216_migration.py -q && .venv/Scripts/python.exe -m pytest tests/test_flow_config.py -q && .venv/Scripts/python.exe -m pytest tests/test_b2_transition_from_config.py -q`

**Criterio de aceptación (binario):** los 4 comandos verdes; `grep -n "state_flow_centralized_enabled" backend/services/flow_config_store.py` ≥2; `grep -c "def " backend/api/flow_config.py` devuelve el MISMO número que antes del plan (blueprint intacto).

**Flag:** `STACKY_STATE_CONFIG_CENTRALIZED_ENABLED` ON. **Impacto por runtime:** Codex/Claude/Copilot idéntico — los 3 consumen el resolve/list vía backend; fallback = flag OFF restaura el archivo. **Trabajo del operador:** ninguno (migración automática).

---

### F2 — Sección "Estados" independiente en Configuración (frontend, reorganización)

**Objetivo (1 frase):** reemplazar la pestaña "Flujo" por una pestaña "Estados" que agrupe (a) las reglas estado→agente y (b) la Máquina de estados del tracker, sacando esta última del formulario del perfil.

**Valor:** un solo lugar para todo el dominio de estados; el formulario de perfil se acorta; cumple el punto 3 del pedido del operador.

**Archivos a crear:**
- `frontend/src/pages/StatesConfigPage.tsx` — compone dos cards: `<FlowRulesCard/>` (el contenido actual de `FlowConfigPage` reusado) y `<TrackerRoleStateCard/>` por rol (F3). **Ratchet:** archivo `.tsx` NUEVO ⇒ CERO `style={{}}` inline (usar `StatesConfigPage.module.css`; ojo que `FlowConfigPage.tsx` hoy tiene inline styles en `:243,:282,:405` — esos quedan en el archivo viejo, que NO es nuevo; NO copiarlos al archivo nuevo).
- `frontend/src/pages/StatesConfigPage.module.css`.
- `frontend/src/pages/statesConfigModel.ts` — helpers puros (ver F3).

**Archivos a editar (cambios exactos):**
1. `frontend/src/pages/SettingsPage.tsx`:
   - `:2` → `import StatesConfigPage from "./StatesConfigPage";` (reemplaza el import de `FlowConfigPage`).
   - `:193` → label del botón: `Flujo` → `Estados`. El **id interno del sub-tab sigue siendo `"flow"`** (NO renombrarlo: es el default sin segmento de URL, `SettingsPage.tsx:150,181`, contrato de deep-links del plan 165; renombrarlo rompería `/settings`).
   - `:246` → `{sub === "flow" && <StatesConfigPage />}`.
2. `frontend/src/pages/FlowConfigPage.tsx`: exportar el contenido como card embebible — cambio mínimo: agregar prop opcional `embedded?: boolean` que (a) oculta el `<h2>` propio cuando `embedded`, (b) nada más de lógica; y (c) **cambiar el literal del `<h2>`** (`FlowConfigPage.tsx:357`) de `Config de Flujo` a `Reglas de flujo` (C3: el literal viejo desaparece del código y el criterio grep queda binario). `StatesConfigPage` lo renderiza con `embedded` bajo un heading propio "¿Qué agente toma cada estado?". (Alternativa PROHIBIDA: copiar/pegar el componente — duplicaría lógica.)
3. `frontend/src/components/ClientProfileEditor.tsx:992-1004`: reemplazar la `<Section title="Máquina de estados del tracker" required>` por una nota compacta (sin editor):
   ```tsx
   <Section title="Máquina de estados del tracker">
     <p className={styles.hint}>
       Se movió a Configuración → Estados (una sola fuente para todos los estados del tracker).
     </p>
   </Section>
   ```
   El JSON avanzado (`advancedJson`) sigue permitiendo editar `tracker_state_machine` a mano — no tocar.
   **Además (C2):** en el punto donde el GET puebla el estado local (`setBaseProfile`, buscar sus call-sites alrededor de `ClientProfileEditor.tsx:461`), ELIMINAR la key `state_flow` del objeto antes de setearla (`const { state_flow: _sf, ...rest } = fetched;` o `delete copy.state_flow;`). El editor de perfil (formulario Y vista JSON avanzada) NUNCA muestra ni re-manda `state_flow`; el backend la preserva cuando el payload no la trae (F1 merge-preserve). Editar/borrar reglas se hace SOLO en la pestaña Estados.
4. `frontend/src/pages/__tests__/SettingsPage.harness.test.tsx:75-76,118-119`: actualizar el mock (`vi.mock("../StatesConfigPage", ...)`) y el click al botón `"Estados"`.
5. Copys/comentarios que apuntan a la pestaña vieja — **localizar por GREP DEL LITERAL, nunca por número de línea (C5: `TicketBoard.tsx` lo está tocando una sesión paralela, planes 212/213):** correr `grep -rn "Config de Flujo" "Stacky Agents/frontend/src"` y corregir TODAS las ocurrencias. Hoy son 4: `TicketBoard.tsx` (copy `…Configurá el flujo en la pestaña Config de Flujo.` → `…Configurá el flujo en Configuración → Estados.`), `EmployeeEditDrawer.tsx` (`Usado por "Config de Flujo" para resolver…` → `Usado por Configuración → Estados para resolver…`), `PipelineStatus.tsx` (comentario → `…en la pestaña Estados (StatesConfig).`) y el `<h2>` de `FlowConfigPage.tsx` (punto 2c). Si el grep encuentra ocurrencias nuevas, corregirlas con el mismo criterio.

**Casos borde:** sin proyecto activo ⇒ ambos cards muestran el empty-state existente (`FlowConfigPage.tsx:364-368` ya lo hace; `TrackerRoleStateCard` replica el mismo mensaje); deep-link `/settings` sigue abriendo esta pestaña (id `"flow"` intacto).

**Tests PRIMERO:** actualizar `SettingsPage.harness.test.tsx` ANTES de tocar `SettingsPage.tsx` (rojo → verde). Gate de componentes: `tsc` (RTL/jsdom NO están instalados — no inventar harness de render, memoria del repo).

**Comandos exactos:** `cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/SettingsPage.harness.test.tsx` y `cd "Stacky Agents/frontend" && npx tsc --noEmit`.

**Criterio de aceptación (binario):** ambos comandos verdes; `grep -rn "Config de Flujo" "Stacky Agents/frontend/src"` devuelve **0 hits totales** (C3 — sin excepciones interpretables); `grep -n "Máquina de estados" "Stacky Agents/frontend/src/components/ClientProfileEditor.tsx"` sigue devolviendo la Section-nota (no se pierde el ancla visual); `grep -c "state_flow" "Stacky Agents/frontend/src/components/ClientProfileEditor.tsx"` ≥1 (el strip de C2 está presente).

**Flag:** sin gate de UI (reorganización pura; el storage ya está gateado por F1). **Impacto por runtime:** N/A (UI). **Trabajo del operador:** ninguno — encuentra lo mismo, mejor agrupado.

---

### F3 — Dropdowns de estados reales en la Máquina de estados + coherencia con las reglas

**Objetivo (1 frase):** editar `tracker_state_machine` (roles `functional`/`technical`/`developer`, mismas keys de siempre) con dropdowns poblados por `tracker-states`, más un chequeo de coherencia no bloqueante entre reglas de flujo e `input_states` con corrección 1-click (HITL).

**Valor:** imposible tipear estados inexistentes; el operador ve y corrige incoherencias regla↔máquina en el mismo lugar.

**Archivos:** `frontend/src/pages/StatesConfigPage.tsx` (componentes `TrackerRoleStateCard`, `StateSelect`), `frontend/src/pages/statesConfigModel.ts`, `frontend/src/pages/__tests__/statesConfigModel.test.ts`.

**Diseño exacto de `TrackerRoleStateCard`:**
- Carga el perfil con la MISMA query key que el editor de perfil: `["client-profile", projectName]` + `ClientProfileApi.get` (`ClientProfileEditor.tsx:448-452`) — cache compartida, cero requests extra.
- Estados del tracker con la query existente `["tracker-states", projectName]` (compartida con `FlowRulesCard`).
- Por cada rol (`functional`, `technical`, `developer` — el mismo array literal de `ClientProfileEditor.tsx:995`):
  - `input_states` (array): chips de los estados actuales + un `StateSelect` "Añadir estado…" que solo ofrece estados del tracker aún no elegidos para ese rol; cada chip tiene botón "×". Chip cuyo valor no existe en el tracker ⇒ clase CSS `warn` + title "(no existe en el tracker)". El ORDEN del array se preserva (los prompts usan `input_states[0]`, `TechnicalAnalyst.v2.agent.md:190` — NO ordenar alfabéticamente).
  - `in_progress`, `blocked_state`, `next_state_ok` (strings): `StateSelect` single con primera opción `"(sin configurar)"` (value `""` ⇒ se persiste string vacío, igual que hoy: `resolve_task_state_plan` ya trata `"" → None`, `task_states.py:67-68`). Si el valor guardado no está en el tracker, se agrega como opción extra marcada — patrón `FlowConfigPage.tsx:211-215`.
- Botón "Guardar máquina de estados" por card global (no por rol): construye `{...profile, tracker_state_machine: draft}`, **quita `state_flow` antes del PUT (C2: `const { state_flow: _sf, ...payload } = merged;` — las reglas viajan por `/api/flow-config`, nunca por este PUT; el backend preserva la almacenada)** y hace `ClientProfileApi.put` (riel PUT existente, `api/client_profile.py:147`); muestra `state_warnings` de la respuesta (`api/client_profile.py:239-244`) en el banner de la card. HITL: nada se persiste hasta el click.
- Preserva las keys que este editor no muestra (p. ej. `by_work_item_type` del 208, roles extra como `business`/`qa` si existieran en el JSON): el draft se construye con spread del objeto original por rol, nunca desde cero. Comentario ancla `{/* PLAN-208: matriz by_work_item_type va aquí */}`.

**`statesConfigModel.ts` (puro, sin React) — tipos y funciones exactas (C6: los tipos se definen y exportan ACÁ, literales):**
```ts
export type CoherenceIssue = {
  ado_state: string;
  agent_type: string;
  suggestion: "add_input_state";
};
export type RoleMachine = {
  input_states?: string[];
  in_progress?: string;
  blocked_state?: string;
  next_state_ok?: string;
  [k: string]: unknown; // preserva keys ajenas (p. ej. by_work_item_type del 208)
};
export type Machine = Record<string, RoleMachine>;

export function addableStates(trackerStates: string[], chosen: string[]): string[]
// trackerStates - chosen, preservando el orden de trackerStates.
export function staleValues(trackerStates: string[], values: string[]): string[]
// valores usados que no existen en el tracker (case-insensitive, trim).
export function coherenceIssues(rules: {ado_state: string; agent_type: string}[],
  machine: Record<string, {input_states?: string[]}>): CoherenceIssue[]
// por cada regla ado_state→agent_type cuyo rol exista en machine y cuyo ado_state
// NO esté (case-insensitive) en machine[agent_type].input_states =>
// {ado_state, agent_type, suggestion: "add_input_state"}.
export function applyAddInputState(machine, agentType, adoState): Machine
// devuelve copia con adoState appendeado al final de input_states (sin duplicar).
```
- UI de coherencia: banner amarillo no bloqueante bajo las cards listando cada issue con botón "Agregar '<estado>' a estados de entrada de <rol>" que aplica `applyAddInputState` al draft (el operador igual debe Guardar — doble HITL). Roles fuera de la máquina (`business`, `qa` — hoy la card solo edita 3 roles, igual que el editor actual) se omiten sin warning.

**Casos borde:** tracker sin estados (`trackerStates=[]`) ⇒ selects deshabilitados con opción "No hay estados disponibles" (mismos copys de `FlowConfigPage.tsx:109-112`) y los valores existentes se conservan intactos; perfil ausente ⇒ card muestra "Aún no hay perfil — se creará al guardar" y el PUT crea el perfil (F0/F1 lo permiten); jira/mantis ⇒ `tracker-states` ya devuelve defaults por tracker (`api/projects.py:801-807`), todo funciona igual.

**Tests PRIMERO — `frontend/src/pages/__tests__/statesConfigModel.test.ts`:** `addableStates` excluye elegidos y preserva orden; `staleValues` es case-insensitive; `coherenceIssues` detecta la regla faltante y NO reporta cuando el estado ya está; `applyAddInputState` no duplica y appendea al final; roles desconocidos se omiten.

**Comandos exactos:** `cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/statesConfigModel.test.ts` y `cd "Stacky Agents/frontend" && npx tsc --noEmit`.

**Criterio de aceptación (binario):** ambos verdes; `grep -c "input type=\"text\"" "Stacky Agents/frontend/src/pages/StatesConfigPage.tsx"` = 0 y `grep -c "<TextField" "Stacky Agents/frontend/src/pages/StatesConfigPage.tsx"` = 0 (cero texto libre para estados); `grep -n "PLAN-208" "Stacky Agents/frontend/src/pages/StatesConfigPage.tsx"` ≥1.

**Flag:** sin gate propio (hereda F1 para storage; los dropdowns son mejora pura). **Impacto por runtime:** los 3 runtimes reciben un `tracker_state_machine` más confiable por la misma inyección de contexto; fallback = igual que hoy si el perfil no define estados. **Trabajo del operador:** ninguno obligatorio; las correcciones de coherencia son opt-in por click.

---

### F4 — Pasada UX final + paridad flag-OFF + documentación

**Objetivo (1 frase):** pulir copys/jerarquía visual de la nueva sección, verificar la paridad flag-OFF de punta a punta y dejar el rastro documental.

**Valor:** cumple el punto 4 del pedido (claridad/comodidad) y blinda el rollback.

**Cambios exactos:**
1. `StatesConfigPage.tsx` — encabezado de página con 2 líneas fijas de copy: título "Estados del tracker" y subtítulo "Una sola fuente: qué agente toma cada estado, y qué estados aplica Stacky al iniciar y completar. Los cambios se guardan en el perfil del cliente del proyecto activo.". Orden vertical fijo: (1) card Reglas de flujo, (2) card Máquina de estados, (3) banner de coherencia. Ambas cards con el mismo patrón de header (`tableHeader` de `FlowConfigPage.module.css`).
2. Verificación flag-OFF manual + test: con `STACKY_STATE_CONFIG_CENTRALIZED_ENABLED=false` (vía UI del arnés), CRUD de reglas sigue funcionando contra el archivo legacy y la UI nueva no cambia (solo cambia el storage). Test backend ya cubierto en F1 (`test_flag_off_byte_identico_legacy`); aquí se agrega el smoke manual documentado en el PR.
3. `backend/scripts/run_harness_tests.sh` — confirmar los 3 `test_plan216_*.py` registrados (gotcha: test nuevo sin registrar ⇒ meta-test rojo).
4. Actualizar este doc a estado IMPLEMENTADO al cierre (feedback recurrente del operador: sincronizar el encabezado del plan).
5. Si `docs/sistema/` referencia la pestaña "Flujo" (verificar con `grep -rn "Config de Flujo" "Stacky Agents/docs/sistema"`), actualizar la mención puntual (corrección mínima, no reescritura).
6. **Huella de regresión (C7, convención):** agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` la entrada `{"id": "plan216-state-typo", "pattern": "state_not_in_tracker", "plan": "216", "date": "<fecha de implementación>", "guard_test": "backend/tests/test_plan216_profile_schema.py"}` respetando la shape existente del archivo (leerla antes de escribir; si el archivo no existe, crearlo como lista JSON con esa única entrada).

**Tests/comandos exactos:** re-correr POR ARCHIVO todo lo del plan: los 3 comandos backend de F0/F1 + los 2 comandos vitest de F2/F3 + `npx tsc --noEmit`.

**Criterio de aceptación (binario):** todos los comandos verdes; `grep -rn "test_plan216" "Stacky Agents/backend/scripts/run_harness_tests.sh"` devuelve 3 líneas; smoke manual flag-OFF anotado en el PR.

**Flag:** N/A. **Impacto por runtime:** N/A. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

- **R1 — Romper consumidores de `/api/flow-config` (Run Sugerido, PipelineStatus, tickets.py).** *Mitigación:* el blueprint y la API del store no cambian (P1); tests de regresión `test_flow_config.py` y `test_b2_transition_from_config.py` corren sin modificarse en F1.
- **R2 — Migración que pise una config buena.** *Mitigación:* la migración solo corre si el perfil NO tiene `state_flow` (idempotencia testeada); el archivo legacy queda byte-intacto (test `test_archivo_legacy_queda_intacto`); rollback = flag OFF.
- **R3 — PUT full-object del editor de perfil pisa `state_flow` (C2).** El draft del editor vive en `useState` LOCAL (`baseProfile`, `ClientProfileEditor.tsx:461`): es un snapshot stale y la invalidación de la query NO lo refresca — la "mitigación" v1 era insuficiente. *Mitigación real (doble cierre determinista):* backend merge-preserve en `put_client_profile` (payload sin la key ⇒ se preserva la almacenada, F1) + las UIs NUNCA envían `state_flow` (el editor la elimina al ingerir el GET, F2; `TrackerRoleStateCard` la quita antes del PUT, F3). Test `test_put_perfil_sin_state_flow_preserva_reglas`. `StatesConfigPage` igual invalida `["client-profile", projectName]` tras guardar (frescura de lectura, no de protección).
- **R4 — Renombrar el sub-tab rompe deep-links.** *Mitigación:* el id interno `"flow"` NO se renombra (solo el label visible); contrato del plan 165 intacto.
- **R5 — Ratchet inline-style / registro de tests.** *Mitigación:* archivos `.tsx` nuevos con CSS modules exclusivamente; `test_plan216_*` registrados en `HARNESS_TEST_FILES` (criterio binario en F4).
- **R6 — Colisión con la implementación futura del 208.** *Mitigación:* §3.1 fija el contrato en ambas direcciones; keys del perfil idénticas; comentario ancla `PLAN-208` en el componente.
- **R7 — Lectura de flag por clase en vez de instancia (falso verde OFF, gotcha 208-C1).** *Mitigación:* `state_flow_centralized_enabled()` lee `config.config` (instancia) y el branch OFF se testea con `monkeypatch.setattr(config.config, ...)`.

## 6. Fuera de scope

- La **matriz `by_work_item_type`** y toda transición automática al completar (Planes 208/209): aquí solo se garantiza el lugar donde su UI vivirá.
- `agent_workflow_configs.<agente>.{allowed_states, transition_state, on_failure_state}` (config POR EMPLEADO, `services/agent_completion_internal.py:329-380`, editada en `AgentWorkflowForm.tsx`/`EmployeeEditDrawer.tsx`): es otro dominio (workflow por empleado, no mapeo global) y tiene su propio consumidor B2; NO se migra ni se toca.
- Cambios en `next_agent.py` (deprecated, preservado para rollback, `next_agent.py:4-9`).
- Export/import explícito de `state_flow` en `config_transfer.py` (viaja implícito dentro de `client_profile` si el transfer incluye el perfil; ampliar el bundle es un follow-up).
- Roles `business`/`qa` en la máquina de estados (hoy el editor solo expone functional/technical/developer, `ClientProfileEditor.tsx:995`; ampliarlo es otro plan).

## 7. Glosario

- **Perfil del cliente (`client_profile`):** JSON por proyecto dentro de `projects/<NAME>/config.json` con convenciones del cliente (rutas, build, estados) que Stacky inyecta a los agentes; CRUD en `backend/api/client_profile.py`.
- **Máquina de estados del tracker (`tracker_state_machine`):** por rol de agente, qué estados toma (`input_states`), cuál aplica al iniciar (`in_progress`), al bloquearse (`blocked_state`, solo humano) y al terminar OK (`next_state_ok`). Resolver: `harness/task_states.py`.
- **Reglas de flujo (`flow_config` → `state_flow.rules`):** mapeo determinístico `ado_state → agent_type` que alimenta el botón "Run Sugerido" del tablero.
- **Estados del tracker (`tracker-states`):** lista real de `System.State` (u homólogos jira/mantis) del proyecto, servida por `GET /api/projects/<name>/tracker-states` (`api/projects.py:724`).
- **Arnés / flag:** registro central de feature-flags (`services/harness_flags.py`) editable por UI (Configuración → Arnés).
- **HITL:** human-in-the-loop — el operador aprueba; Stacky nunca decide sola.
- **Runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro — los tres motores de ejecución de agentes, que consumen el mismo prompt/contexto.

## 8. Orden de implementación

1. F0 — flag (5 lugares del arnés) + `_check_state_flow` + `set_client_profile_state_flow` + tests schema.
2. F1 — store centralizado + migración lazy con saneo/fallback (C1) + espejo legacy ([ADICIÓN ARQUITECTO]) + merge-preserve en `put_client_profile` (C2) + tests store/migración + regresión flow_config/B2 por archivo.
3. F2 — pestaña "Estados" (`StatesConfigPage` + `FlowConfigPage embedded` + nota en `ClientProfileEditor`) + test harness de SettingsPage + copys TicketBoard/EmployeeEditDrawer.
4. F3 — `TrackerRoleStateCard` con dropdowns + `statesConfigModel.ts` + coherencia 1-click + tests vitest por archivo.
5. F4 — pulido UX, paridad flag-OFF, registro en `HARNESS_TEST_FILES`, docs y cierre del doc.

## 9. Definición de Hecho (DoD) global

- [ ] `STACKY_STATE_CONFIG_CENTRALIZED_ENABLED` visible y toggleable en Configuración → Arnés, default ON.
- [ ] Con flag ON: crear/editar/borrar reglas en la pestaña Estados persiste en `client_profile.state_flow` (verificable leyendo `projects/<NAME>/config.json`) y el espejo legacy `flow_config.json` queda sincronizado con lo último guardado ([ADICIÓN ARQUITECTO]); la migración sola NO modifica el archivo (test de bytes intactos).
- [ ] Con flag OFF: comportamiento byte-idéntico al legacy (archivo), sin errores en la UI; apagar la flag tras editar con ON muestra las MISMAS reglas (rollback sin pérdida — smoke manual).
- [ ] Un PUT del perfil sin `state_flow` NO borra las reglas (C2: test backend verde; el editor de perfil y la card de máquina no envían la key).
- [ ] La pestaña "Flujo" ya no existe como tal; "Estados" agrupa reglas + máquina; el editor de perfil muestra la nota de reubicación y su JSON avanzado sigue editando `tracker_state_machine`.
- [ ] Cero campos de texto libre para estados en la nueva sección (criterio grep de F3).
- [ ] `Run Sugerido` del tablero sigue resolviendo agente por estado (smoke manual).
- [ ] Todos los tests del plan verdes POR ARCHIVO con `.venv/Scripts/python.exe -m pytest` (backend) y `npx vitest run <archivo>` (frontend); `npx tsc --noEmit` limpio; `test_plan216_*` registrados en `HARNESS_TEST_FILES`.
- [ ] Ningún criterio binario de F0–F4 en rojo; encabezado de este doc actualizado a IMPLEMENTADO.
