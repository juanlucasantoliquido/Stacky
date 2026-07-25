# Plan 238 — Bandeja de Incidencias Abiertas dentro de Tickets ADO

**Estado:** IMPLEMENTADO — F-1..F9 (2026-07-25)
**Implementación:** F-1, F0, F1, F2, F3, F4, F5, F6, F7, F8, F9 completas. Ver §12.
**Estado previo:** CRITICADO v2 — RECHAZADO en v1, corregido (2026-07-25)
**Fecha:** 2026-07-25
**Autor:** StackyArchitectaUltraEficientCode
**Numeración:** **238**. Los números **219..236 están RESERVADOS** por el catálogo del plan 218 (`Stacky Agents/docs/_roadmap/serie_paridad_218.json`, verificado que existe). El número **237 pertenece al plan hermano** `237_PLAN_TRIAGE_DE_PLANES_EN_EL_CENTRO_DE_EVOLUCION.md` (mismo día). Este plan nació como 237, colisionó, y el operador resolvió que el triage conserva el 237 y la bandeja pasa a 238. **Todo símbolo, test, comentario e id de este plan usa `238` / `plan238`.**

---

## 0. Historial de versiones — v1 → v2 (2026-07-25)

Revisión adversarial (juez severo + arquitecto). **Veredicto de la v1: RECHAZADO** — 5 bloqueantes. Todas las anclas `archivo:línea` de la v1 fueron re-verificadas contra el código real; las que fallaron están corregidas abajo.

| # | Hallazgo v1 | Sev. | Resuelto en v2 |
|---|---|---|---|
| C1 | F0 no registraba la ayuda llana de la flag ⇒ `test_plain_help_covers_all_registry_keys` rojo | BLOQ | F0 pasa a **5 archivos**: `harness_flags_help.py` con la entrada literal `PlainHelp(...)` (§F0-e) |
| C2 | F0 mandaba registrar los tests en `HARNESS_TEST_FILES` **y también** en la allowlist ⇒ rompe `test_allowlist_no_se_solapa_con_ratchet` | BLOQ | Regla dura: **exactamente uno de los dos**; prohibido tocar la allowlist (§F0-d) |
| C3 | F7 rompía un 4º test de `shellNav.test.ts` que el plan no listaba, y citaba mal el título de otro | BLOQ | Rediseño del gate del tab ⇒ **solo 3 ediciones literales**, todas verificadas (§F7-c) |
| C4 | P9 prometía "con la flag OFF la superficie desaparece" pero el tab/paleta/nav v1 quedaban visibles; y la justificación ("shellNav es puro, no puede consultar la flag") era falsa | BLOQ | `computeVisibleTabs` recibe `incidentInboxEnabled?: boolean` — el mismo patrón que `migradorEnabled`/`evolutionEnabled` (§F7) |
| C5 | Ceguera silenciosa con `tracker_provider=gitlab`: `work_item_type` queda NULL y el filtro SQL descarta NULL ⇒ bandeja vacía sin explicación | BLOQ | **[ADICIÓN ARQUITECTO A2]** `untyped_count` + `provider` + EmptyState explicativo + test GitLab-shaped (§4.2, §F1, §F2, §F6) |
| C6 | El "guard del contrato con el 216" no podía detectar nada (perfil fabricado en el propio test) ⇒ falso verde | IMP | **[ADICIÓN ARQUITECTO A3]** guard cruzado real condicional a que exista `_check_state_flow` (§F1) |
| C7 | F8 decía "usar `navigateToRoute` si existe": existe pero es clausura local de App ⇒ trampa de import circular | IMP | Instrucción literal + prohibición explícita de exportarla (§F8) |
| C8 | "Copiar lista" ignoraba la flag 194 del portapapeles | IMP | Gate con `resolveCopyExportEnabled` (§F6) |
| C9 | `counts` prometía "todas las incidencias" pero se calculaba sobre las ≤1000 traídas ⇒ mentira con `truncated:true` | IMP | **[ADICIÓN ARQUITECTO A4]** counts por agregación SQL, independientes del LIMIT (§F2) |
| C10 | Anclas por número de línea sobre archivos que otra sesión está editando; `TicketBoard.tsx:83` ya está corrido a `:82` | IMP | **[ADICIÓN ARQUITECTO A5]** fase **F-1** de pre-flight + toda ancla sobre archivo sucio es textual (§F-1) |
| C11 | Renumeración 237→238 incompleta; colisión de prefijo `test_plan237_*` con el plan hermano | IMP | Renumerado completo a `plan238` (títulos, tests, ids, comentarios) |
| C12 | 6 instrucciones condicionales ("si existiera…", "si el linter exige…") que un modelo menor debe inferir | MEN | Todas resueltas contra el código y vueltas literales |
| C13 | No reusaba `INCIDENT_ICON` y duplicaba "🚑" en 4 lugares | MEN | Reuso obligatorio (§F6, §F7, §F8) |
| C14 | Trampa del ratchet: un comentario que contenga `style={{` se auto-cuenta | MEN | Advertencia explícita (§F6) |
| C15 | Sin huella de regresión | MEN | §F9 registra 2 huellas en `docs/sistema/error_fingerprints.json` |
| C16 | Doble ordenamiento (server + cliente) | MEN | El server ordena; el cliente **respeta** salvo búsqueda (§F4) |
| C17 | Los tests sembraban en la BD compartida sin `try/finally` | MEN | `try/finally` obligatorio + rango reservado (§F2) |

### Anclas verificadas contra el código (2026-07-25)

**Correctas:** `backend/api/tickets.py:347-354` (`_ticket_project_filter`), `:625-633` (jerarquía), `:659` (`.limit(500)`), `:665-672` (N+1), `:6873`/`:6886` (`work_item_type="Issue"`), `:282` (`_request_project_name`) · `backend/services/ticket_assigner.py:41` · `backend/models.py:105` (`to_dict`), `:119-139` (vocabulario canónico 218 F5) · `backend/api/incidents.py:9-10`, `:13-31` · `backend/services/harness_flags.py:370`, `:375`, `:376`, `:3915-3927` · `backend/config.py:1523` · `backend/tests/test_harness_flags.py:467`, `:725`, `:816-825` · `backend/scripts/run_harness_tests.sh:657` · `backend/api/__init__.py:65`, `:136` · `backend/tests/test_plan218_parity_endpoint.py:15-18`, `:24-31` · `frontend/src/utils/workItemTypeColor.ts:34`, `:43`, `:53` · `frontend/src/services/copyService.ts:29` · `frontend/src/services/routes.ts:5-8`, `:14-20`, `:73-74` · `frontend/src/components/shell/shellNav.ts:5-9`, `:16-34`, `:43`, `:62-64` · `frontend/src/components/shell/AppSidebar.tsx:22`, `:34` · `frontend/src/components/commandPaletteData.ts:59-73` · `frontend/src/api/client.ts:86`, `:88`, `:106-109` · `frontend/src/App.tsx:171-175`, `:284-299`, `:287`, `:335`, `:349` · `frontend/src/pages/TicketBoard.tsx:18-21`, `:805`, `:821`, `:870`, `:968-970`, `:999`, `:1008-1017`, `:1018` · `docs/216_...md:80`, `:115`.

**Falsa / corrida:** `frontend/src/pages/TicketBoard.tsx:83` para `CLOSED_STATES` → **hoy está en `:82`** (la sesión paralela corrió el archivo). Corregida en todo el documento y convertida en la justificación de §F-1.

**Hallazgos nuevos de la verificación (no eran citas del plan):**
- `frontend/src/components/shell/shellIcons.ts:8-12` — `ICON_BY_NAME` tiene 17 íconos y **NO** contiene `Ambulance` **ni** `AlertTriangle`.
- `backend/services/harness_flags_help.py` — **no** tiene entrada para `STACKY_CONNECTION_RESILIENCE_ENABLED` (plan 192) ⇒ `test_harness_flags_help.py::test_plain_help_covers_all_registry_keys` **ya está rojo por deuda ajena**. Este plan **agrega la suya** (no suma deuda) y declara el rojo previo.
- `backend/services/gitlab_provider.py:55-56,74-91` — GitLab codifica el tipo de ítem como **label** `type::<x>`; `_normalize_issue` no devuelve campo de tipo. Origen del bloqueante C5.
- `frontend/src/services/copyService.ts:10,101-108` — el gate de la flag 194 es `resolveCopyExportEnabled`, **no** está dentro de `copyText`.

---

## 1. Objetivo + KPI

### Objetivo (1 párrafo)

Agregar a Stacky una **vista dedicada de incidencias** —accesible desde el módulo "Tickets ADO"— que muestre **solo las incidencias** (work items de tipo `Issue` y `Bug`), con foco en las que están **ABIERTAS**, para que dejen de perderse entre el resto de los tickets. La vista es **100% ADITIVA**: el tablero general (`TicketBoard`) **NO cambia de aspecto ni de comportamiento**, salvo por un único botón nuevo en su cabecera. La clasificación "abierta / cerrada" **no se cablea con literales sueltos**: se resuelve en el backend con un orden de precedencia determinista que ya contempla la centralización de estados del plan 216. Y cuando el proyecto activo usa un tracker cuyo tipo de ítem no está sincronizado localmente (caso GitLab), la bandeja **lo dice**, en vez de mostrar una lista vacía mentirosa.

### KPI / impacto esperado

| KPI | Hoy | Con el plan |
|---|---|---|
| Clics + scroll para saber cuántas incidencias abiertas hay | indeterminado (hay que recorrer el árbol/grafo completo del board) | 1 clic, número visible en la cabecera |
| Incidencias invisibles por el tope de 500 filas de `GET /api/tickets` (`backend/api/tickets.py:659`) | posible: una incidencia vieja cae fuera del `LIMIT 500` ordenado por `last_synced_at desc` | 0: la bandeja filtra **por tipo en la consulta SQL**, con tope propio de 1000 y bandera `truncated` |
| Fuentes de verdad de "qué estado es cerrado" | 2 copias divergentes: `frontend/src/pages/TicketBoard.tsx:82` y `backend/services/ticket_assigner.py:41` | 1 resolvedor backend (`services/incident_inbox.py`) con precedencia perfil > 216 > default |
| Pantallas vacías sin explicación cuando el tracker no es ADO | 100% (nadie lo detecta) | 0: `untyped_count` + mensaje explícito |
| Exactitud de `counts` con más de 1000 incidencias | — | exacto (agregación SQL, no depende del `LIMIT`) |
| Cambios visuales en el tablero general | — | 1 botón nuevo; el resto sin tocar |
| Pasos manuales nuevos para el operador | — | **0** (flag default ON, sin configuración obligatoria) |

---

## 2. Por qué ahora / gap que cierra

**Necesidad textual del operador:** *"Dentro de tickets ADO me debe de permitir entrar a algún apartado de incidencias donde las vea claramente cuáles son las que están abiertas y solo ver incidencias, para que no se me pierdan entre los tickets. Pero en la vista general sí verla como está hoy."*

Evidencia de que el gap es real (verificado en el código actual):

1. **Stacky YA sabe qué es una incidencia, pero solo para pintarla, no para agruparla.**
   `frontend/src/utils/workItemTypeColor.ts:34` define `INCIDENT_TYPES = new Set(["issue", "bug"])`, `:37` exporta `INCIDENT_ICON = "🚑"`, `:43` exporta `isIncidentWorkItemType()` y `:53` `formatWorkItemTypeLabel()`. Ese helper hoy solo alimenta color e ícono del badge. **No existe ninguna vista que filtre por él.**

2. **El tablero mezcla todo por diseño.**
   `frontend/src/pages/TicketBoard.tsx:805` fija `viewMode` default `"graph"`, y `:968-970` arma `filteredEpics` + `filteredOrphans` sobre la jerarquía completa (`GET /api/tickets/hierarchy`, `backend/api/tickets.py:625-633`). Las incidencias no tienen contenedor propio: caen como hijas de una épica o como huérfanas, mezcladas con Tasks.

3. **El tope de 500 puede esconder incidencias.**
   `backend/api/tickets.py:659` hace `.order_by(Ticket.last_synced_at.desc()...).limit(500)`. Una incidencia abierta pero vieja compite por ese cupo contra todas las Tasks.

4. **La serie de incidencias construyó el ciclo, pero nunca la vista.**
   Plan 131 (captura multimodal, botón en `TicketBoard.tsx:1008-1017`) · Plan 166 (MERGEADO: publica la incidencia como `Issue`, `backend/api/tickets.py:6873,6886`; "Resolver con agente" en `TicketBoard.tsx:821`) · Plan 177 (auto-PR) · Plan 188 (del fallo de deploy a la incidencia) · Plan 200 (sin implementar: consola por incidencia).
   **Ninguno de los cinco entrega un lugar donde ver la lista de incidencias abiertas.**

5. **La infraestructura para hacerlo barato ya está.**
   Deep-links (`frontend/src/services/routes.ts`, plan 165: `parseRoute` preserva query params desconocidos verbatim, `:73-74`) · navegación declarativa del shell (`components/shell/shellNav.ts`, plan 139; `AppSidebar.tsx:22` itera `orderedVisibleGroups()`) · portapapeles (`services/copyService.ts:29 copyText` + gate `:101-108`, plan 194) · `LoadErrorState` / `EmptyState` / `SkeletonList` (importados en `TicketBoard.tsx:18-20`) · vocabulario canónico multi-proveedor (`models.py:119-139`, plan 218 F5).

**Gap en una frase:** Stacky sabe qué es una incidencia y sabe crearlas, pero no tiene **ningún lugar donde verlas juntas**; este plan agrega ese lugar sin tocar la vista general.

---

## 3. Principios y guardarraíles (NO negociables)

| # | Guardarraíl | Cómo se cumple en este plan |
|---|---|---|
| P1 | **La vista general NO cambia.** | `TicketBoard.tsx` recibe **exactamente 2 líneas nuevas** (1 import + 1 elemento JSX autocontenido), insertadas por **ancla textual**. `TicketBoard.module.css` **NO se toca**. Cero cambios en el árbol, el grafo, los filtros o el orden. |
| P2 | **Paridad de 3 runtimes** (Codex CLI / Claude Code CLI / GitHub Copilot Pro). | La bandeja es **solo lectura** sobre la tabla `tickets` local. No lanza agentes, no invoca modelos, no depende de ningún runtime. El único campo runtime-adyacente es `stacky_status`, que escribe `services/ticket_status.py` igual para los 3. Fallback: si falta o es desconocido, la UI muestra "idle". |
| P3 | **Cero trabajo extra para el operador.** | Flag `STACKY_INCIDENT_INBOX_ENABLED` **default ON**. Ninguna de las 4 excepciones duras aplica: no bypassea revisión humana, no es destructiva ni irreversible (solo lectura), no tiene prerequisitos (usa la DB que ya se sincroniza), no reduce seguridad. Sin configuración obligatoria. |
| P4 | **Human-in-the-loop.** | La bandeja **no decide ni actúa**: no cierra, no reasigna, no publica, no lanza agentes. Solo muestra y deja copiar/abrir. Amplifica al operador; no lo reemplaza. |
| P5 | **Mono-operador sin auth.** | Cero RBAC, cero roles, cero multiusuario. El campo de asignado reusa `assigned_to_ado`, que es informativo, no un control de acceso. |
| P6 | **"Abierta" NUNCA es un literal cableado.** | Se resuelve en `backend/services/incident_inbox.py` con precedencia declarada (§4.1). Contrato explícito con el plan 216 (§4.1.3) **y guard cruzado real** (§F1). |
| P7 | **No degradar performance.** | Filtro por tipo **en SQL**, **sin N+1** (no trae `last_execution` ni `pipeline_summary`, a diferencia de `list_tickets`, `backend/api/tickets.py:665-672`). Tope duro de 1000 filas con bandera `truncated`. `counts` por agregación (2 `COUNT(*)`), no por materialización. |
| P8 | **Reusar, no reinventar.** | Reusa: `isIncidentWorkItemType` + `INCIDENT_ICON` + `getWorkItemTypeColor` (166/177), `copyText` + `resolveCopyExportEnabled` (194), `routes.ts` (165), `shellNav.ts` (139), `EmptyState`/`LoadErrorState`/`SkeletonList` (140), `Ticket.to_dict()` (218 F5), `_request_project_name`/`_ticket_project_filter` (`api/tickets.py:282,347`). |
| P9 | **Backward-compatible y rollback total.** | Todo aditivo. **Con la flag OFF desaparecen: el tab de la barra lateral, el botón del tablero, la entrada de la paleta, el botón de la nav v1 y el contenido de la página**, y el endpoint de ítems devuelve 404 `feature_disabled`. La app queda idéntica a hoy. *(v1 prometía esto pero dejaba 3 superficies vivas: corregido en §F7.)* |
| P10 | **Nunca una pantalla vacía mentirosa.** | Si la bandeja no puede filtrar por tipo porque el tracker no sincroniza ese campo (caso GitLab), la respuesta trae `untyped_count > 0` y la UI explica el motivo (§4.2, §F6). |

---

## 4. Contratos y decisiones congeladas

### 4.1 Resolución de "qué cuenta como INCIDENCIA" y "qué cuenta como ABIERTA"

Todo vive en un módulo nuevo y **puro** (sin Flask, sin DB, sin I/O): `backend/services/incident_inbox.py`.

#### 4.1.1 Tipos de incidencia — precedencia

| Orden | Fuente | Valor |
|---|---|---|
| 1 | `client_profile["incident_inbox"]["incident_types"]` | lista de strings no vacía |
| 2 | **default** | `("issue", "bug")` |

El default replica **exactamente** `INCIDENT_TYPES` de `frontend/src/utils/workItemTypeColor.ts:34`, para que la bandeja y el badge del board nunca discrepen.

#### 4.1.2 Estados cerrados — precedencia

| Orden | Fuente | Nota |
|---|---|---|
| 1 | `client_profile["incident_inbox"]["closed_states"]` | override explícito del operador |
| 2 | `client_profile["state_flow"]["closed_states"]` | key aditiva del plan 216 (ver 4.1.3) |
| 3 | **default** `("Done", "Closed", "Resolved", "Removed", "Completed")` | idéntico a `TicketBoard.tsx:82` y a `backend/services/ticket_assigner.py:41` |

Comparación **case-insensitive** y con `strip()`. Una lista presente pero vacía o con elementos no-string se trata como **ausente** (cae al siguiente nivel) — nunca lanza.

> **Nota de proveedor (verificada):** GitLab expone el estado del issue como `"opened"` / `"closed"` (`gitlab_provider._normalize_issue`, `:74-91`, campo `state`). Con el default de arriba, `"closed"` cae en cerrado (comparación case-insensitive contra `"Closed"`) y `"opened"` cae en abierto. **No hace falta un default por proveedor.** El problema de GitLab es el **tipo**, no el estado (ver 4.1.4).

#### 4.1.3 Contrato con el plan 216 (CENTRALIZACIÓN DE ESTADOS)

El plan 216 está **CRITICADO v2 — APROBADO-CON-CAMBIOS (2026-07-23), SIN implementar** (verificado en el encabezado de `docs/216_...md`). Crea la key `client_profile.state_flow` con shape `{"version": "1.0", "rules": [...]}` (`docs/216_...md:80`). Ese shape **no incluye** `closed_states`, y su validador `_check_state_flow(value)` (`docs/216_...md:115`) **todavía no existe en el código**.

**Contrato declarado por este plan (238):**

- 238 lee `state_flow["closed_states"]` como key **ADITIVA y OPCIONAL**. Si no existe (que es el caso hoy, y también el día en que 216 aterrice sin agregarla), 238 **cae al default** y se comporta exactamente como el board de hoy.
- 216 **no debe borrar ni renombrar** claves desconocidas dentro de `state_flow`; su `_check_state_flow` debe **ignorar** (no rechazar) `closed_states`.
- Cuando 216 esté implementado, exponer `closed_states` en su pestaña "Estados" es un cambio de **una línea de UI** en 216 y **cero líneas** en 238.
- **Guard cruzado REAL (§F1, [ADICIÓN ARQUITECTO A3]):** `test_plan238_incident_inbox_core.py::test_216_check_state_flow_no_rechaza_closed_states` intenta importar `_check_state_flow` de `services.client_profile`; si **no existe**, hace `pytest.skip("Plan 216 sin implementar")`; si **existe**, le pasa un `state_flow` con `closed_states` y exige lista de errores vacía. Ese test **sí** se pone rojo el día que 216 aterrice rompiendo la key. *(La v1 tenía un test que fabricaba el perfil a mano y por eso no podía detectar nada: falso verde.)*

#### 4.1.4 Degradación explícita por proveedor — **[ADICIÓN ARQUITECTO A2]**

Hecho verificado: el único código que persiste `Ticket.work_item_type` es `backend/services/ado_sync.py:174,307`, que lee campos de la forma WIQL de Azure DevOps. `backend/services/gitlab_provider.py` **no menciona `work_item_type` en ninguna línea**; codifica el tipo como **label** `type::<x>` (`:55-56 _type_label`) y `_normalize_issue` (`:74-91`) no devuelve ningún campo de tipo.

Consecuencia: en un proyecto con tracker GitLab, `Ticket.work_item_type` queda **NULL**, y en SQL `NULL IN (...)` evalúa a NULL ⇒ la fila se descarta. Sin mitigación, **la bandeja mostraría una lista vacía sin explicación**.

**Contrato:** el endpoint de ítems devuelve siempre:

- `untyped_count`: cantidad de tickets del proyecto activo con `work_item_type` NULL o vacío (`COUNT(*)`).
- `provider`: valor de `Ticket.tracker_type` de la primera fila del proyecto, o `null` si no hay filas.

La UI (§F6, caso 5b) muestra un `EmptyState` **explicativo** —no "no hay incidencias"— cuando `items` viene vacío y `untyped_count > 0`. Este plan **no** arregla el sync de GitLab (fuera de scope, §7): lo hace visible.

### 4.2 Contrato de la API (congelado)

`GET /api/incident-inbox/status?project=<nombre>`

```json
{
  "ok": true,
  "enabled": true,
  "incident_types": ["issue", "bug"],
  "incident_types_source": "default",
  "closed_states": ["Done", "Closed", "Resolved", "Removed", "Completed"],
  "closed_states_source": "default"
}
```

- Con la flag OFF devuelve **200** con `"enabled": false` (para que el punto de entrada se oculte sin que la UI lo trate como error). Mismo patrón que `backend/api/incidents.py:13-31`.
- Valores posibles de `*_source`: `"profile_incident_inbox"` | `"profile_state_flow"` | `"default"`.

`GET /api/incident-inbox/items?project=<nombre>&scope=<open|all>`

```json
{
  "ok": true,
  "scope": "open",
  "counts": { "open": 7, "closed": 12, "total": 19 },
  "truncated": false,
  "untyped_count": 0,
  "provider": "ado",
  "incident_types": ["issue", "bug"],
  "closed_states": ["Done", "Closed", "Resolved", "Removed", "Completed"],
  "items": [
    { "id": 42, "ado_id": 1234, "title": "...", "work_item_type": "Issue",
      "ado_state": "Active", "ado_url": "https://...", "assigned_to_ado": "x@y.z",
      "stacky_status": "idle", "last_synced_at": "2026-07-24T10:00:00",
      "is_open": true }
  ]
}
```

- `items[]` es el payload de `Ticket.to_dict()` (`backend/models.py:105`) **más** la key `is_open` (bool). Ninguna key se quita ni se renombra. **Nota 218 F5:** con `STACKY_CANONICAL_VOCABULARY_ENABLED` en ON (default), `to_dict()` devuelve el vocabulario canónico (`tracker_state`, `item_type`, `item_url`, `assignee`, …) **más** los alias legacy vía `with_legacy_aliases` (`services/tracker_vocabulary.py:36-47`, que hace `setdefault` y **nunca quita claves**). Con la flag en OFF devuelve `_legacy_payload()`. **En ambos casos las claves legacy que consume esta bandeja están presentes**; por eso el modelo del frontend lee las legacy.
- `counts` se calcula por **agregación SQL sobre todas las incidencias del proyecto**, sin `LIMIT` — es exacto aunque `truncated` sea `true` (**[ADICIÓN ARQUITECTO A4]**; la v1 lo calculaba sobre las filas materializadas y mentía).
- Con la flag OFF devuelve **404** `{"ok": false, "error": "feature_disabled"}` (mismo shape que `backend/api/incidents.py:9-10`).
- `scope` inválido o ausente ⇒ se normaliza a `"open"` (nunca 400).
- Tope duro de `items`: 1000 filas; si se supera, `truncated: true` y la UI muestra un aviso.
- Orden de `items`: **abiertas primero**, luego `last_synced_at desc`, desempate `ado_id desc`. El orden lo fija el servidor; el cliente **no reordena** (§F4).

---

## 5. Fases

> **Orden obligatorio:** F-1 → F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9. Cada fase deja el repo verde y es verificable sola.

---

### F-1 — Pre-flight de convivencia con la sesión paralela — **[ADICIÓN ARQUITECTO A5]**

**Objetivo (1 frase):** capturar el estado del árbol de trabajo ANTES de tocar nada, para que al final se pueda demostrar qué cambió este plan y qué ya estaba cambiado por otra sesión.

**Valor:** convierte el "contrato de propiedad de archivos" de promesa a procedimiento. Sin esto, el criterio "+2 / -0 en `TicketBoard.tsx`" es inverificable.

**Trabajo del operador:** ninguno.

**Motivo (verificado hoy):** la v1 citaba `CLOSED_STATES` en `TicketBoard.tsx:83`; **hoy está en `:82`**. Otra sesión ya corrió el archivo. **Toda ancla de línea sobre un archivo sucio es orientativa: se re-verifica con `Select-String` antes de editar.**

#### Comandos exactos (SOLO LECTURA)

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
# 1) Foto del árbol (guardar la salida en el reporte final)
git status --short
git worktree list
# 2) Diff base de los archivos disputados (guardar la salida)
git diff --stat -- "frontend/src/pages/TicketBoard.tsx" "frontend/src/pages/TicketBoard.module.css"
# 3) Re-verificar las 3 anclas TEXTUALES que usa este plan
Select-String -Path "frontend\src\pages\TicketBoard.tsx" -Pattern "\{/\* Toggle vista \*/\}"
Select-String -Path "frontend\src\pages\TicketBoard.tsx" -Pattern "className=\{styles\.headerActions\}"
Select-String -Path "frontend\src\pages\TicketBoard.tsx" -Pattern "^const CLOSED_STATES"
# 4) Baseline de ratchets (guardar las 3 salidas para comparar al final)
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
npx vitest run src/components/shell/__tests__/shellIntegration.test.ts
```

#### Archivos PROHIBIDOS durante todo el plan (cambios sin commitear de otra sesión)

`frontend/src/pages/TicketBoard.module.css` · `frontend/src/pages/SprintBoardPage.tsx` · `frontend/src/pages/UnblockerPage.tsx` · `frontend/src/components/TicketGraphView.jsx` · `frontend/src/components/TicketGraphView.module.css` · `frontend/src/incidents/devResolverModel.ts` · `frontend/src/utils/workItemTypeColor.ts` (**solo importar, jamás editar**) · `frontend/src/utils/__tests__/workItemTypeColor.test.ts` (untracked, ajeno).

**Único archivo disputado que este plan edita:** `frontend/src/pages/TicketBoard.tsx`, **2 líneas**, en F8.

#### Criterio de aceptación (binario)

1. Los 4 bloques de comandos corrieron y su salida quedó guardada.
2. El paso 3 devuelve **≥ 1 línea** para cada uno de los 3 patrones. Si `{/* Toggle vista */}` devuelve 0, F8 usa el fallback declarado en §F8 y se deja constancia.
3. **No** se ejecutó ningún comando git que modifique estado.

---

### F0 — Flag del arnés `STACKY_INCIDENT_INBOX_ENABLED` (registro quíntuple)

**Objetivo (1 frase):** registrar la flag maestra de la bandeja, default ON y editable desde la UI del panel de flags, sin cambiar todavía ningún comportamiento.

**Valor:** rollback total del plan en un clic desde la UI, sin redeploy ni tocar `.env` a mano.

**Trabajo del operador:** ninguno (default ON; ninguna de las 4 excepciones duras aplica: es solo lectura, no bypassea revisión humana, no tiene prerequisitos, no reduce seguridad).

#### Archivos a editar (5) y crear (1)

**(a) `Stacky Agents/backend/services/harness_flags.py`** — dos ediciones:

*Edición 1* — agregar la key a la categoría `interfaz_ui`. Anclaje: el bloque que empieza en `:370` con `"interfaz_ui": (`. Insertar la línea nueva **inmediatamente después** de la línea `:375` (`"STACKY_CONNECTION_RESILIENCE_ENABLED", ...`) y antes del `),` de `:376`:

```python
        "STACKY_INCIDENT_INBOX_ENABLED",  # Plan 238 — bandeja de incidencias abiertas
```

*Edición 2* — agregar el `FlagSpec` al final de `FLAG_REGISTRY`. Anclaje: copiar el patrón EXACTO del bloque de `:3915-3927` (plan 192). Insertar **después** del último `FlagSpec(...)` de la tupla y **antes** del `)` que cierra `FLAG_REGISTRY`:

```python
    # ── Plan 238 — Bandeja de incidencias abiertas dentro de Tickets ADO ──────
    FlagSpec(
        key="STACKY_INCIDENT_INBOX_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Bandeja de incidencias abiertas",
        description=(
            "Plan 238 - Vista dedicada que lista SOLO incidencias (Issue/Bug) con foco "
            "en las abiertas, accesible desde Tickets ADO. Solo lectura: no lanza agentes "
            "ni modifica el tracker. OFF: la vista, el tab, la entrada de la paleta y el "
            "boton de entrada desaparecen, y el tablero general queda identico."
        ),
        group="global",
    ),
```

**(b) `Stacky Agents/backend/config.py`** — agregar el campo. Anclaje: insertar **inmediatamente después** del bloque `STACKY_BULK_ACTIONS_ENABLED` que termina en `:1523`:

```python
    # ── Plan 238 — Bandeja de incidencias abiertas (UI, solo lectura) ─────────
    # Default ON: no publica nada, no destruye, sin prerequisitos, no reduce
    # seguridad. OFF => el tab, la pagina y el boton de entrada desaparecen.
    STACKY_INCIDENT_INBOX_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_INBOX_ENABLED", "true"
    ).strip().lower() == "true"
```

> Este campo **también** satisface el centinela de cableado: `backend/tests/test_flag_wiring.py:24-33` declara que `config.py` **SÍ cuenta** como consumo productivo, así que F0 queda verde por sí sola sin necesitar F2.

**(c) `Stacky Agents/backend/tests/test_harness_flags.py`** — agregar la key al set `_CURATED_DEFAULTS_ON` (empieza en `:467`). Insertar **inmediatamente después** de la línea `:725` (`"STACKY_CONNECTION_RESILIENCE_ENABLED",`):

```python
    # ── Plan 238 — Bandeja de incidencias: bool default ON; solo lectura,
    # ninguna de las 4 excepciones duras aplica. ──
    "STACKY_INCIDENT_INBOX_ENABLED",
```

> **Por qué es obligatorio:** `test_default_known_only_for_curated` (`:816-825`) exige `known_keys == _CURATED_DEFAULTS_ON`. Un `FlagSpec` con `default=True` que no esté en el set pone ese test en rojo.

**(d) `Stacky Agents/backend/scripts/run_harness_tests.sh`** — registrar los 3 tests nuevos. Insertar **antes** del `)` que cierra la lista `HARNESS_TEST_FILES` (hoy en `:657`):

```sh
  # -- Plan 238 - Bandeja de incidencias abiertas --
  tests/test_plan238_inbox_flag.py
  tests/test_plan238_incident_inbox_core.py
  tests/test_plan238_incident_inbox_api.py
```

> **REGLA DURA (corrige C2 de la v1):** `backend/tests/test_harness_ratchet_meta.py` exige que todo `tests/test_*.py` esté en `HARNESS_TEST_FILES` **O** en `backend/tests/harness_ratchet_allowlist.txt` — y su test `test_allowlist_no_se_solapa_con_ratchet` **falla si un archivo está en los DOS**. Estos 3 archivos van **SOLO** en `HARNESS_TEST_FILES`. **PROHIBIDO tocar `harness_ratchet_allowlist.txt`.**
>
> Los tres archivos se registran **en F0** aunque dos se creen en F1/F2: `test_ratchet_clasifica_todos_los_tests` mira archivos existentes, así que registrar de más no rompe nada y registrar de menos sí.

**(e) `Stacky Agents/backend/services/harness_flags_help.py`** — **OBLIGATORIO (era el bloqueante C1 de la v1).** `backend/tests/test_harness_flags_help.py::test_plain_help_covers_all_registry_keys` exige `REGISTRY_KEYS - set(PLAIN_HELP) == []`: un `FlagSpec` nuevo sin ayuda llana pone ese centinela en rojo.

Agregar la entrada al dict `PLAIN_HELP`, junto a las demás keys de interfaz (el orden dentro del dict es libre):

```python
    "STACKY_INCIDENT_INBOX_ENABLED": PlainHelp(
        what="Una vista aparte que junta solo las incidencias (los tickets de tipo Issue y Bug) y pone primero las que siguen abiertas.",
        on_effect="Si la activás: aparece la sección Incidencias en el menú y un botón en el tablero de tickets que te lleva directo a la lista de abiertas.",
        off_effect="Si la apagás: desaparecen el botón del tablero y esa sección del menú, y todo queda igual que antes de tener la bandeja.",
        example="Como la bandeja de entrada del correo: en vez de buscar los reclamos sueltos entre todos los mensajes, los ves juntos y sabés cuántos siguen sin resolver.",
    ),
```

> **Restricciones literales del centinela** (`backend/tests/test_harness_flags_help.py:17-23,44-73`), ya respetadas por el texto de arriba: `what` entre 10 y 200 caracteres; `on_effect` y `off_effect` **empiezan con `"Si "`** y ≤240; `example` ≤300; ningún campo vacío; **prohibidas** las palabras de la denylist (MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime — y sus plurales); prohibido citar keys en MAYÚSCULAS_CON_GUIONES y referencias a fases del tipo `F1`.
>
> **Rojo preexistente declarado:** `STACKY_CONNECTION_RESILIENCE_ENABLED` (plan 192) **no** tiene entrada en `PLAIN_HELP` (verificado). Por eso `test_plain_help_covers_all_registry_keys` puede estar rojo **antes** de este plan. Verificar con:
> `& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags_help.py -v` **antes** de editar, guardar la salida, y al final comprobar que la lista de "Flags sin ayuda llana" **no incluye** `STACKY_INCIDENT_INBOX_ENABLED`. **PROHIBIDO** arreglar la deuda del 192 (fuera de scope).

#### NO tocar

- `_REQUIRES_MAP_FROZEN`: la flag **no tiene** `requires=`, así que no lleva arista. **No agregar nada ahí.**
- `_FROZEN_BOUNDS`: es solo para flags numéricas (`type="int"`/`"float"`). La flag es `bool`. **No agregar nada ahí.**
- `RESERVED_KEYS` de `test_flag_wiring.py`: la flag **no** es reserved (tiene consumidor real).
- `backend/tests/harness_ratchet_allowlist.txt`: ver la regla dura de (d).
- `deployment/harness_defaults.env`: **PROHIBIDO editarlo a mano**; se genera con `deployment/export_harness_defaults.py`. Este plan **no** lo regenera.

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/backend/tests/test_plan238_inbox_flag.py`:

```python
"""tests/test_plan238_inbox_flag.py -- Plan 238 F0: flag STACKY_INCIDENT_INBOX_ENABLED.

Este archivo hace importlib.reload(config) y contamina tests flag-off de la
misma sesion pytest. Correr SIEMPRE por archivo (como todo el arnes).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS  # noqa: E402

KEY = "STACKY_INCIDENT_INBOX_ENABLED"


def test_flag_registrada_bool_default_on():
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    assert KEY in _CATEGORY_KEYS["interfaz_ui"]


def test_flag_tiene_ayuda_llana():
    """C1 v2: sin esto, test_harness_flags_help se pone rojo por culpa de este plan."""
    from services.harness_flags_help import PLAIN_HELP
    assert KEY in PLAIN_HELP
    entry = PLAIN_HELP[KEY]
    assert entry.on_effect.startswith("Si ")
    assert entry.off_effect.startswith("Si ")
    assert 10 <= len(entry.what.strip()) <= 200


def test_config_default_efectivo_on(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is True


def test_config_env_off_apaga(monkeypatch):
    monkeypatch.setenv(KEY, "false")
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is False
```

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan238_inbox_flag.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags_help.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_flag_wiring.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_ratchet_meta.py -v
```

> **Intérprete:** `backend\.venv\Scripts\python.exe` es **Python 3.13.5** (el correcto). `backend\venv\Scripts\python.exe` es 3.11.9 y **NO se usa**. Correr **siempre por archivo**: la suite completa da falsos rojos por contaminación entre tests.

#### Criterio de aceptación (binario)

1. `test_plan238_inbox_flag.py`: **5 passed, 0 failed**.
2. `test_harness_flags.py`, `test_flag_wiring.py` y `test_harness_ratchet_meta.py`: **0 failed**.
3. `test_harness_flags_help.py`: si falla, la lista de "Flags sin ayuda llana" **no** contiene `STACKY_INCIDENT_INBOX_ENABLED` (rojo ajeno del plan 192, declarado).
4. `Select-String -Path "backend\config.py" -Pattern "STACKY_INCIDENT_INBOX_ENABLED"` devuelve **≥ 1** línea.
5. `Select-String -Path "backend\services\harness_flags.py" -Pattern "STACKY_INCIDENT_INBOX_ENABLED"` devuelve **exactamente 2** líneas (categoría + FlagSpec).
6. `git status --short -- backend/tests/harness_ratchet_allowlist.txt` **sin cambios**.

#### Impacto por runtime

| Runtime | Impacto | Fallback |
|---|---|---|
| Codex CLI | ninguno | n/a — la flag no toca el pipeline de ejecución |
| Claude Code CLI | ninguno | n/a |
| GitHub Copilot Pro | ninguno | n/a |

---

### F1 — Núcleo puro de clasificación: `backend/services/incident_inbox.py`

**Objetivo (1 frase):** funciones puras que respondan "¿esto es una incidencia?" y "¿está abierta?", con la precedencia de §4.1, sin Flask ni DB.

**Valor:** elimina la divergencia entre las dos copias actuales de `CLOSED_STATES` (`TicketBoard.tsx:82` y `ticket_assigner.py:41`) y deja el criterio testeable en milisegundos.

**Trabajo del operador:** ninguno. **Flag:** el módulo es puro; la flag se consulta en F2.

#### Archivo a CREAR: `Stacky Agents/backend/services/incident_inbox.py`

```python
"""Plan 238 F1 -- Nucleo PURO de la bandeja de incidencias.

Sin Flask, sin SQLAlchemy, sin I/O: solo funciones deterministas sobre dicts.
Fuente UNICA de verdad de "que es una incidencia" y "que estado esta abierto".
"""
from __future__ import annotations

# Espejo EXACTO de INCIDENT_TYPES en frontend/src/utils/workItemTypeColor.ts:34.
DEFAULT_INCIDENT_TYPES: tuple[str, ...] = ("issue", "bug")

# Espejo EXACTO de CLOSED_STATES en frontend/src/pages/TicketBoard.tsx:82 y de
# _CLOSED_STATES en backend/services/ticket_assigner.py:41.
# Cubre tambien GitLab: sus estados son "opened"/"closed" y "closed" cae aca
# por comparacion case-insensitive contra "Closed".
DEFAULT_CLOSED_STATES: tuple[str, ...] = (
    "Done", "Closed", "Resolved", "Removed", "Completed",
)

# Tope duro de filas devueltas por la bandeja (P7).
MAX_ITEMS: int = 1000


def normalize(value: str | None) -> str:
    """'  Done ' -> 'done'. None/no-str -> ''."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _clean_string_list(raw) -> tuple[str, ...] | None:
    """Lista de strings no vacia -> tupla de strings ya stripeados. Si no lo es
    (None, no-list, vacia, con elementos no-str o todos vacios) devuelve None
    para que el caller caiga al siguiente nivel de precedencia. NUNCA lanza."""
    if not isinstance(raw, list):
        return None
    out = [v.strip() for v in raw if isinstance(v, str) and v.strip()]
    return tuple(out) if out else None


def resolve_incident_types(profile: dict | None) -> tuple[tuple[str, ...], str]:
    """(tipos_normalizados, fuente). Ver Plan 238 seccion 4.1.1."""
    if isinstance(profile, dict):
        section = profile.get("incident_inbox")
        if isinstance(section, dict):
            explicit = _clean_string_list(section.get("incident_types"))
            if explicit is not None:
                return tuple(normalize(v) for v in explicit), "profile_incident_inbox"
    return DEFAULT_INCIDENT_TYPES, "default"


def resolve_closed_states(profile: dict | None) -> tuple[tuple[str, ...], str]:
    """(estados_cerrados_tal_cual, fuente). Ver Plan 238 seccion 4.1.2.

    CONTRATO CON EL PLAN 216: la key `state_flow.closed_states` es ADITIVA y
    OPCIONAL. Si el plan 216 aterriza sin ella, esta funcion cae al default y el
    comportamiento es identico al del tablero de hoy.
    """
    if isinstance(profile, dict):
        section = profile.get("incident_inbox")
        if isinstance(section, dict):
            explicit = _clean_string_list(section.get("closed_states"))
            if explicit is not None:
                return explicit, "profile_incident_inbox"
        state_flow = profile.get("state_flow")
        if isinstance(state_flow, dict):
            from_216 = _clean_string_list(state_flow.get("closed_states"))
            if from_216 is not None:
                return from_216, "profile_state_flow"
    return DEFAULT_CLOSED_STATES, "default"


def is_incident_type(work_item_type: str | None, types: tuple[str, ...]) -> bool:
    """True si el tipo del work item esta en el conjunto de tipos-incidencia."""
    norm = normalize(work_item_type)
    if not norm:
        return False
    return norm in {normalize(t) for t in types}


def is_open_state(state: str | None, closed_states: tuple[str, ...]) -> bool:
    """True si el estado NO esta en el conjunto de estados cerrados.

    Estado vacio/None => ABIERTA (un item sin estado sincronizado es trabajo
    pendiente, no trabajo terminado: nunca se oculta silenciosamente).
    """
    norm = normalize(state)
    if not norm:
        return True
    return norm not in {normalize(s) for s in closed_states}


def normalize_scope(raw: str | None) -> str:
    """'all'/'todas' -> 'all'; cualquier otra cosa (incluido None) -> 'open'."""
    norm = normalize(raw)
    return "all" if norm in {"all", "todas"} else "open"


def build_counts(total: int, closed: int) -> dict[str, int]:
    """Counts a partir de dos agregados SQL. Nunca negativo. Ver Plan 238 4.2."""
    total = max(0, int(total))
    closed = max(0, min(int(closed), total))
    return {"open": total - closed, "closed": closed, "total": total}
```

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/backend/tests/test_plan238_incident_inbox_core.py` con **exactamente** estos 13 casos:

| # | Test | Qué verifica |
|---|---|---|
| 1 | `test_defaults_espejan_el_frontend` | `DEFAULT_INCIDENT_TYPES == ("issue","bug")` y `DEFAULT_CLOSED_STATES == ("Done","Closed","Resolved","Removed","Completed")` |
| 2 | `test_perfil_none_usa_default` | `resolve_incident_types(None) == (("issue","bug"), "default")` y `resolve_closed_states(None)[1] == "default"` |
| 3 | `test_perfil_sin_secciones_usa_default` | `resolve_closed_states({"otra_cosa": 1})[1] == "default"` |
| 4 | `test_incident_inbox_tiene_maxima_precedencia` | perfil con **ambas** `incident_inbox.closed_states=["Cerrado"]` y `state_flow.closed_states=["X"]` ⇒ `(("Cerrado",), "profile_incident_inbox")` |
| 5 | `test_state_flow_closed_states_tiene_precedencia_sobre_default` | perfil `{"state_flow": {"version":"1.0","rules":[],"closed_states":["Terminado","Cancelado"]}}` ⇒ `(("Terminado","Cancelado"), "profile_state_flow")`. **Congela el LECTOR de 238** (no el comportamiento del 216 — ver test 6). |
| 6 | `test_216_check_state_flow_no_rechaza_closed_states` | **[ADICIÓN A3]** `try: from services.client_profile import _check_state_flow` / `except ImportError: pytest.skip("Plan 216 sin implementar: no hay validador que probar")`. Si existe: `_check_state_flow({"version":"1.0","rules":[],"closed_states":["Terminado"]}) == []`. **Este SÍ se pone rojo si 216 rompe la key.** |
| 7 | `test_state_flow_sin_closed_states_cae_a_default` | perfil `{"state_flow": {"version":"1.0","rules":[]}}` (shape literal del 216, `docs/216_...md:80`) ⇒ fuente `"default"` |
| 8 | `test_listas_corruptas_caen_al_siguiente_nivel` | `[]`, `["", "  "]`, `[1, 2]`, `"Done"`, `None` ⇒ todos fuente `"default"`, sin excepción |
| 9 | `test_is_incident_type_case_insensitive` | `"Issue"`, `"ISSUE"`, `" bug "` ⇒ True; `"Task"`, `"Epic"`, `""`, `None` ⇒ False |
| 10 | `test_is_open_state_case_insensitive` | `"Active"`, `"New"`, `"En Progreso"` ⇒ True; `"Done"`, `"closed"`, `" Resolved "` ⇒ False |
| 11 | `test_gitlab_states_opened_closed` | **paridad de proveedor:** `is_open_state("opened", DEFAULT_CLOSED_STATES) is True` y `is_open_state("closed", DEFAULT_CLOSED_STATES) is False` |
| 12 | `test_estado_vacio_es_abierta` | `is_open_state(None, ...)` y `is_open_state("", ...)` ⇒ True |
| 13 | `test_build_counts` | `build_counts(19, 12) == {"open":7,"closed":12,"total":19}`; `build_counts(0,0) == {"open":0,"closed":0,"total":0}`; `build_counts(5, 99)` ⇒ `closed` se clampa a 5 y `open` a 0 |

Más `test_normalize_scope` (14): `"all"`/`"ALL"`/`"todas"` ⇒ `"all"`; `"open"`/`None`/`""`/`"basura"` ⇒ `"open"`.

Encabezado obligatorio del archivo de test (mismo patrón verificado en `backend/tests/test_plan218_parity_endpoint.py:15-18`):

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.incident_inbox import (  # noqa: E402
    DEFAULT_CLOSED_STATES, DEFAULT_INCIDENT_TYPES, build_counts, is_incident_type,
    is_open_state, normalize_scope, resolve_closed_states, resolve_incident_types,
)
```

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan238_incident_inbox_core.py -v
```

#### Criterio de aceptación (binario)

1. **14 tests: 13 passed + 1 skipped** (el 6, mientras el plan 216 no esté implementado), **0 failed**.
2. `Select-String -Path "backend\services\incident_inbox.py" -Pattern "import flask|sqlalchemy|from models"` devuelve **0 líneas** (el módulo es puro).

#### Impacto por runtime

Ninguno en los 3 (módulo puro, sin ejecución de agentes). Fallback: n/a.

---

### F2 — Endpoint de solo lectura `backend/api/incident_inbox.py`

**Objetivo (1 frase):** exponer `GET /api/incident-inbox/status` y `GET /api/incident-inbox/items` respetando §4.2, sin tocar `backend/api/tickets.py` (351 KB, disputado).

**Valor:** la lista sale filtrada desde SQL, sin el tope de 500 del listado general, sin N+1, con `counts` exactos y con degradación explícita por proveedor.

**Trabajo del operador:** ninguno.

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED` (default ON). Leída como `config.config.STACKY_INCIDENT_INBOX_ENABLED`, **nunca** del módulo `config` pelado.

#### Archivo a CREAR: `Stacky Agents/backend/api/incident_inbox.py`

```python
"""Plan 238 F2 -- Bandeja de incidencias abiertas (solo lectura).

Blueprint independiente: NO se toca backend/api/tickets.py (351 KB, disputado
por los planes 212/213 y por una sesion paralela viva).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("incident_inbox", __name__, url_prefix="/incident-inbox")


def _enabled() -> bool:
    # GOTCHA REAL: `config` importado como MODULO devuelve el default y mata el
    # branch OFF. La instancia es `config.config`.
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_ENABLED", True))


def _feature_disabled_response():
    return jsonify({"ok": False, "error": "feature_disabled"}), 404


def _profile_for(project_name: str | None) -> dict | None:
    """client_profile del proyecto activo. Nunca lanza: si no se puede leer,
    devuelve None y el resolvedor cae al default.

    Simbolos verificados 2026-07-25:
      services/client_profile.py:266  def load_client_profile(project_name)
      services/project_context.py:151 def resolve_project_context(...)
    """
    try:
        from services.client_profile import load_client_profile
        if not project_name:
            from services.project_context import resolve_project_context
            ctx = resolve_project_context()
            project_name = getattr(ctx, "stacky_project_name", None) if ctx else None
        if not project_name:
            return None
        return load_client_profile(project_name)
    except Exception:
        return None


@bp.get("/status")
def incident_inbox_status():
    from services.incident_inbox import resolve_closed_states, resolve_incident_types

    project_name = (request.args.get("project") or "").strip() or None
    profile = _profile_for(project_name)
    types, types_source = resolve_incident_types(profile)
    closed, closed_source = resolve_closed_states(profile)
    return jsonify({
        "ok": True,
        "enabled": _enabled(),
        "incident_types": list(types),
        "incident_types_source": types_source,
        "closed_states": list(closed),
        "closed_states_source": closed_source,
    })


@bp.get("/items")
def incident_inbox_items():
    if not _enabled():
        return _feature_disabled_response()

    from sqlalchemy import func, or_

    from db import session_scope
    from models import Ticket
    from services.incident_inbox import (
        MAX_ITEMS, build_counts, is_open_state, normalize, normalize_scope,
        resolve_closed_states, resolve_incident_types,
    )

    # SEAM DELIBERADO: se reusan los helpers privados de api/tickets.py para NO
    # duplicar la semantica multi-proyecto del filtro (que es sutil: compara
    # stacky_project_name y cae a project cuando el primero es NULL,
    # api/tickets.py:347-354). Import LAZY dentro de la vista: evita ciclos.
    try:
        from api.tickets import _request_project_name, _ticket_project_filter
    except ImportError:
        return jsonify({
            "ok": False,
            "error": "project_filter_seam_missing",
            "message": (
                "Los helpers _request_project_name/_ticket_project_filter de "
                "api/tickets.py cambiaron de nombre. Ver Plan 238 F2."
            ),
        }), 200

    scope = normalize_scope(request.args.get("scope"))
    project_name = _request_project_name()
    profile = _profile_for(project_name)
    types, _ = resolve_incident_types(profile)
    closed, _ = resolve_closed_states(profile)

    types_norm = [normalize(t) for t in types]
    closed_norm = [normalize(s) for s in closed]
    state_expr = func.lower(func.coalesce(Ticket.ado_state, ""))

    with session_scope() as session:
        project_filter = _ticket_project_filter(project_name)

        def _scoped(q):
            return q.filter(project_filter) if project_filter is not None else q

        # (1) COUNTS EXACTOS por agregacion: NO dependen del LIMIT (Plan 238 4.2).
        incident_q = _scoped(session.query(Ticket)).filter(
            func.lower(Ticket.work_item_type).in_(types_norm)
        )
        total = incident_q.count()
        closed_count = incident_q.filter(state_expr.in_(closed_norm)).count()
        counts = build_counts(total, closed_count)

        # (2) DEGRADACION POR PROVEEDOR (Plan 238 4.1.4): tickets del proyecto
        # SIN tipo sincronizado. En GitLab el tipo viaja como label, no como
        # columna, asi que work_item_type queda NULL y el filtro de (1) los
        # descarta en silencio. Contarlos es lo que evita la pantalla vacia
        # mentirosa.
        untyped_count = _scoped(session.query(Ticket)).filter(
            or_(Ticket.work_item_type.is_(None), func.trim(Ticket.work_item_type) == "")
        ).count()
        first_row = _scoped(session.query(Ticket)).first()
        provider = getattr(first_row, "tracker_type", None) if first_row else None

        # (3) FILAS. Sin N+1: NO se consulta AgentExecution ni pipeline_summary.
        rows_q = incident_q
        if scope == "open":
            rows_q = rows_q.filter(~state_expr.in_(closed_norm))
        rows = rows_q.order_by(
            Ticket.last_synced_at.desc().nulls_last(), Ticket.ado_id.desc()
        ).limit(MAX_ITEMS + 1).all()

        truncated = len(rows) > MAX_ITEMS
        rows = rows[:MAX_ITEMS]

        items = []
        for t in rows:
            payload = t.to_dict()  # 218 F5: canonico + alias legacy, nunca quita keys
            payload["is_open"] = is_open_state(t.ado_state, closed)
            items.append(payload)

    # Abiertas primero; dentro de cada grupo se conserva el orden de la query.
    items.sort(key=lambda i: 0 if i["is_open"] else 1)

    return jsonify({
        "ok": True,
        "scope": scope,
        "counts": counts,
        "truncated": truncated,
        "untyped_count": untyped_count,
        "provider": provider,
        "incident_types": list(types),
        "closed_states": list(closed),
        "items": items,
    })
```

> **Por qué el filtro de `scope` pasó a SQL:** en la v1 se traían hasta 1000 filas y se filtraba en Python, así que con `scope=open` el tope se gastaba en cerradas. Ahora `scope=open` no compite con las cerradas y `counts` sigue siendo global.

#### Archivo a EDITAR: `Stacky Agents/backend/api/__init__.py`

Dos líneas, en los bloques que ya existen (`import` alrededor de `:65`, `register_blueprint` alrededor de `:136`):

```python
from .incident_inbox import bp as incident_inbox_bp  # Plan 238 - bandeja de incidencias
```

```python
api_bp.register_blueprint(incident_inbox_bp)  # Plan 238 - url_prefix="/incident-inbox"
```

> **GOTCHA de merge:** `api/__init__.py` es un registro compartido. Git puede fusionar dos ramas que agregan **la misma línea** sin marcar conflicto, dejando un duplicado silencioso. Tras cualquier merge:
> `Select-String -Path "backend\api\__init__.py" -Pattern "incident_inbox_bp"` ⇒ **exactamente 2** líneas.

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/backend/tests/test_plan238_incident_inbox_api.py`. Fixture de cliente calcada de `backend/tests/test_plan218_parity_endpoint.py:24-31`:

```python
@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c
```

> **GOTCHA:** `create_app()` fuera de pytest dispara daemons y sync real contra el tracker. **Solo instanciarlo dentro de un test de pytest**, nunca en un script suelto.

**Siembra y limpieza — OBLIGATORIO `try/finally`** (la DB es la real, en `DeployStackyAgents\data`). Rango reservado por este plan: `ado_id` **9200..9299** (el rango 9000-9099 lo usan otros tests).

```python
from db import session_scope
from models import Ticket

_ADO_MIN, _ADO_MAX = 9200, 9299


def _seed(rows: list[dict]) -> None:
    with session_scope() as s:
        for r in rows:
            s.add(Ticket(project="TEST", stacky_project_name=None, **r))


def _cleanup() -> None:
    with session_scope() as s:
        s.query(Ticket).filter(
            Ticket.ado_id >= _ADO_MIN, Ticket.ado_id <= _ADO_MAX
        ).delete(synchronize_session=False)
```

Cada test que siembre usa `try: ... finally: _cleanup()`.

Casos obligatorios (12):

| Test | Qué verifica |
|---|---|
| `test_status_200_con_flag_on` | `GET /api/incident-inbox/status` ⇒ 200, `enabled True`, `incident_types == ["issue","bug"]`, `closed_states_source == "default"` |
| `test_status_200_con_flag_off` | con `patch` de la flag en `False` ⇒ **200** y `enabled False` (no 404) |
| `test_items_404_con_flag_off` | con la flag en `False` ⇒ **404** y `data["error"] == "feature_disabled"` |
| `test_items_devuelve_solo_incidencias` | sembrar 1 `Issue` "Active", 1 `Bug` "Done", 1 `Task` "Active", 1 `Epic` "New" ⇒ con `scope=all`, ningún item tiene `work_item_type` en `{"Task","Epic"}` y los 2 sembrados de tipo incidencia están |
| `test_scope_open_filtra_cerradas` | `?scope=open` ⇒ el `Bug` "Done" no aparece; el `Issue` "Active" sí |
| `test_scope_invalido_cae_a_open` | `?scope=basura` ⇒ `data["scope"] == "open"`, sin 400 |
| `test_counts_cuenta_todas_no_solo_el_scope` | con `scope=open`, `counts["closed"] >= 1` y `counts["total"] == counts["open"] + counts["closed"]` |
| `test_item_conserva_las_keys_del_ticket` | cada item tiene `id`, `ado_id`, `title`, `work_item_type`, `ado_state`, `stacky_status` **y** `is_open` |
| `test_abiertas_primero` | con `scope=all`, `items[0]["is_open"] is True` |
| `test_gitlab_sin_tipo_reporta_untyped_count` | **[ADICIÓN A2]** sembrar 1 ticket con `work_item_type=None`, `ado_state="opened"`, `tracker_type="gitlab"` ⇒ no aparece en `items` **pero** `data["untyped_count"] >= 1`. **Nunca vacío mudo.** |
| `test_respuesta_declara_provider` | la respuesta trae la key `provider` (puede ser `None`) |
| `test_seam_de_filtro_de_proyecto_existe` | `from api.tickets import _request_project_name, _ticket_project_filter` no lanza `ImportError` (ratchet del seam) |

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan238_incident_inbox_api.py -v
```

#### Criterio de aceptación (binario)

1. **12 tests passed, 0 failed.**
2. `Select-String -Path "backend\api\incident_inbox.py" -Pattern "getattr\(config,"` devuelve **0 líneas** (la flag se lee de la instancia, no del módulo).
3. `Select-String -Path "backend\api\__init__.py" -Pattern "incident_inbox_bp"` devuelve **exactamente 2** líneas.
4. `& ".\.venv\Scripts\python.exe" -m compileall -q api services` sin errores.

#### Impacto por runtime

| Runtime | Impacto | Fallback |
|---|---|---|
| Codex CLI / Claude Code CLI / GitHub Copilot Pro | ninguno en los 3 | n/a — el endpoint es de solo lectura sobre la tabla local |

**Nota multi-proveedor (corregida respecto de la v1):** el endpoint lee la tabla `tickets`, y `Ticket.to_dict()` ya emite el vocabulario canónico + alias legacy (218 F5, `models.py:119-139`). **Pero el filtro por tipo depende de la columna `work_item_type`, que HOY solo pobla el sync de Azure DevOps** (`ado_sync.py:174,307`). Con GitLab la bandeja **no se rompe**: devuelve `items: []` con `untyped_count > 0` y la UI explica el motivo. Arreglar el sync de GitLab está **fuera de scope** (§7).

---

### F3 — Cliente HTTP: `rawGet` en `frontend/src/api/client.ts`

**Objetivo (1 frase):** agregar el gemelo de lectura de `rawPost` para poder leer el cuerpo de un 404 `feature_disabled` sin que la promesa lance.

**Valor:** cierra un gotcha real — hoy `api.get` **lanza** en cualquier non-2xx (`client.ts:106-109`), así que leer `error` del body dentro de un `.then()` es código muerto. **Verificado: `rawGet` no existe; el archivo solo tiene `rawPost` (`:44-86`).**

**Trabajo del operador:** ninguno. **Flag:** ninguna (utilidad aditiva; ningún caller existente cambia de comportamiento).

#### Archivo a EDITAR: `Stacky Agents/frontend/src/api/client.ts`

Insertar **inmediatamente después** de la línea `:86` (el `}` que cierra `rawPost`) y **antes** de `:88` (`export const apiBase = BASE;`):

```ts
/**
 * Plan 238 F3 — gemelo de lectura de rawPost: fetch GET que NO lanza en 4xx/5xx
 * y devuelve el cuerpo parseado. Necesario para distinguir 404 feature_disabled
 * de un backend caido (api.get lanza en todo non-2xx, :106-109).
 */
export async function rawGet<T>(
  path: string,
  extraHeaders: Record<string, string> = {}
): Promise<RawResponse<T>> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...extraHeaders,
      },
    });
  } catch (e) {
    if (!isAbortError(e)) reportConnectionFailure();
    throw e; // semantica intacta: el caller ve el mismo error de red
  }
  reportOutcome(res);

  let data: T | null = null;
  let errorBody: GatewayErrorBody | null = null;

  const text = await res.text().catch(() => "");
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (res.ok) {
        data = parsed as T;
      } else {
        errorBody = parsed as GatewayErrorBody;
      }
    } catch {
      if (!res.ok) {
        errorBody = { message: text };
      }
    }
  }

  return { status: res.status, ok: res.ok, data, errorBody };
}
```

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/frontend/src/api/__tests__/rawGet.test.ts` (crear la carpeta `__tests__` si no existe). Entorno **node**, sin jsdom: stubbear `fetch` con `vi.stubGlobal`, patrón de `frontend/src/services/__tests__/copyService.test.ts:6-10`.

| Test | Qué verifica |
|---|---|
| `devuelve ok:true y data en 200` | stub 200 con `{"ok":true,"a":1}` ⇒ `{ok:true, status:200, data:{ok:true,a:1}, errorBody:null}` |
| `devuelve ok:false y errorBody en 404` | stub 404 con `{"ok":false,"error":"feature_disabled"}` ⇒ `errorBody.error === "feature_disabled"` y **no lanza** |
| `body no-JSON en error se expone como message` | 500 con texto plano `"boom"` ⇒ `errorBody.message === "boom"` |
| `body vacio en 200 deja data null` | 200 con `""` ⇒ `data === null`, `ok === true` |
| `error de red re-lanza` | stub que rechaza ⇒ `await expect(...).rejects.toThrow()` |

> `connectionMonitor` se importa al tope de `client.ts`; si el test falla por ese import, stubbear el módulo con
> `vi.mock("../../services/connectionMonitor", () => ({ GATEWAY_DOWN_STATUSES: new Set([502,503,504]), reportConnectionSuccess: () => {}, reportConnectionFailure: () => {} }))`.

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/api/__tests__/rawGet.test.ts
```

> **Correr SIEMPRE por archivo.** `npx vitest run` sin filtro contamina entre archivos y da falsos rojos (gotcha conocido). `vitest` no está instalado global: usar `npx` desde `frontend/`.

#### Criterio de aceptación (binario)

1. **5 tests passed, 0 failed.**
2. `npx tsc --noEmit` sin errores **nuevos** respecto de la corrida guardada en F-1.

#### Impacto por runtime

Ninguno en los 3. Fallback: n/a.

---

### F4 — Modelo puro del frontend: `frontend/src/incidents/incidentInboxModel.ts`

**Objetivo (1 frase):** filtro por búsqueda, conteo por estado y formatos, en funciones puras testeables sin DOM.

**Valor:** la página queda como capa de render tonta. El repo **no tiene** `@testing-library/react` ni `jsdom`, así que la lógica tiene que vivir afuera para poder probarla.

**Trabajo del operador:** ninguno. **Flag:** ninguna (módulo puro).

> **Cambio v2 (C16):** el **orden lo fija el servidor** (§4.2). El cliente **no reordena**; `sortIncidents` queda como función de *desempate estable* usada solo cuando la búsqueda re-filtra, y **nunca** cambia el criterio del servidor.

#### Archivo a CREAR: `Stacky Agents/frontend/src/incidents/incidentInboxModel.ts`

```ts
/**
 * Plan 238 F4 — Modelo PURO de la bandeja de incidencias.
 * Sin React, sin DOM, sin fetch: testeable con vitest en entorno node
 * (el repo no tiene @testing-library/react ni jsdom instalados).
 */

export type IncidentScope = "open" | "all";

export interface IncidentInboxItem {
  id: number;
  ado_id: number;
  title: string;
  work_item_type?: string;
  ado_state?: string;
  ado_url?: string;
  assigned_to_ado?: string | null;
  stacky_status?: string;
  last_synced_at?: string;
  is_open: boolean;
}

export interface IncidentInboxCounts {
  open: number;
  closed: number;
  total: number;
}

export interface IncidentInboxResponse {
  ok: boolean;
  scope: IncidentScope;
  counts: IncidentInboxCounts;
  truncated: boolean;
  /** Plan 238 4.1.4 — tickets del proyecto SIN work_item_type sincronizado. */
  untyped_count: number;
  /** Tracker del proyecto activo ("ado" | "gitlab" | null). Solo informativo. */
  provider: string | null;
  incident_types: string[];
  closed_states: string[];
  items: IncidentInboxItem[];
}

export interface IncidentInboxStatus {
  ok: boolean;
  enabled: boolean;
  incident_types: string[];
  incident_types_source: string;
  closed_states: string[];
  closed_states_source: string;
}

/** "all"/"todas" -> "all"; cualquier otra cosa -> "open". Espejo de
 *  normalize_scope() en backend/services/incident_inbox.py. */
export function parseScope(raw: string | null | undefined): IncidentScope {
  const norm = (raw ?? "").trim().toLowerCase();
  return norm === "all" || norm === "todas" ? "all" : "open";
}

/** Desempate ESTABLE que replica el orden del servidor (abiertas primero,
 *  last_synced_at desc, ado_id desc). PURA: devuelve un array nuevo. */
export function sortIncidents(items: IncidentInboxItem[]): IncidentInboxItem[] {
  return items.slice().sort((a, b) => {
    if (a.is_open !== b.is_open) return a.is_open ? -1 : 1;
    const ta = a.last_synced_at ?? "";
    const tb = b.last_synced_at ?? "";
    if (ta !== tb) return tb.localeCompare(ta);
    return b.ado_id - a.ado_id;
  });
}

/** Busqueda case-insensitive sobre titulo, ado_id y estado. Texto vacio => todo. */
export function filterBySearch(
  items: IncidentInboxItem[],
  search: string
): IncidentInboxItem[] {
  const q = search.trim().toLowerCase();
  if (!q) return items.slice();
  return items.filter(
    (i) =>
      i.title.toLowerCase().includes(q) ||
      String(i.ado_id).includes(q) ||
      (i.ado_state ?? "").toLowerCase().includes(q)
  );
}

/** Conteo por estado del tracker, ordenado por cantidad desc y luego alfabetico.
 *  Estado vacio se reporta como "(sin estado)". */
export function countByState(
  items: IncidentInboxItem[]
): { state: string; count: number }[] {
  const map = new Map<string, number>();
  for (const i of items) {
    const key = (i.ado_state ?? "").trim() || "(sin estado)";
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([state, count]) => ({ state, count }))
    .sort((a, b) => (b.count - a.count) || a.state.localeCompare(b.state));
}

/** Texto para el portapapeles (se copia con copyText de services/copyService.ts).
 *  Una linea por incidencia: "#<ado_id>\t<estado>\t<titulo>\t<url>". */
export function formatIncidentsForCopy(items: IncidentInboxItem[]): string {
  return items
    .map((i) =>
      [`#${i.ado_id}`, i.ado_state ?? "", i.title, i.ado_url ?? ""].join("\t")
    )
    .join("\n");
}

/** Resumen para la cabecera: "7 abiertas de 19". */
export function summaryLabel(counts: IncidentInboxCounts): string {
  return `${counts.open} abierta${counts.open === 1 ? "" : "s"} de ${counts.total}`;
}

/** Plan 238 4.1.4 — ¿la lista está vacía porque el tracker no sincroniza el
 *  tipo de ítem? Decide entre "no hay incidencias" y el mensaje explicativo. */
export function isProviderBlind(res: IncidentInboxResponse | null | undefined): boolean {
  if (!res) return false;
  return res.items.length === 0 && res.counts.total === 0 && (res.untyped_count ?? 0) > 0;
}
```

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/frontend/src/incidents/incidentInboxModel.test.ts` (co-locado, como `incidentModel.test.ts` del mismo directorio). **17 casos:**

| Test | Qué verifica |
|---|---|
| `parseScope` | `"all"`, `"ALL"`, `"todas"` ⇒ `"all"`; `"open"`, `null`, `undefined`, `""`, `"basura"` ⇒ `"open"` |
| `sortIncidents pone abiertas primero` | 1 cerrada + 1 abierta ⇒ `[0].is_open === true` |
| `sortIncidents ordena por fecha desc dentro del grupo` | 2 abiertas con fechas distintas ⇒ la más nueva primero |
| `sortIncidents desempata por ado_id desc` | 2 abiertas con la misma fecha ⇒ mayor `ado_id` primero |
| `sortIncidents no muta la entrada` | el array original conserva su orden |
| `sortIncidents tolera last_synced_at ausente` | items sin la key ⇒ no lanza, orden determinista |
| `filterBySearch por titulo` | búsqueda parcial case-insensitive encuentra |
| `filterBySearch por ado_id` | `"1234"` encuentra la incidencia `ado_id: 1234` |
| `filterBySearch por estado` | `"activ"` encuentra la de `ado_state: "Active"` |
| `filterBySearch vacio devuelve todo` | `""` y `"   "` ⇒ largo original |
| `countByState agrupa y ordena` | 2 "Active" + 1 "New" ⇒ `[{state:"Active",count:2},{state:"New",count:1}]` |
| `countByState mapea estado vacio` | item sin `ado_state` ⇒ `"(sin estado)"` |
| `formatIncidentsForCopy` | 2 items ⇒ 2 líneas, cada una con 4 campos separados por tab |
| `formatIncidentsForCopy con lista vacia` | `""` |
| `summaryLabel singular y plural` | `{open:1,...}` ⇒ `"1 abierta de 3"`; `{open:2,...}` ⇒ `"2 abiertas de 3"` |
| `isProviderBlind true con untyped_count` | `items: []`, `counts.total: 0`, `untyped_count: 5` ⇒ `true` |
| `isProviderBlind false si hay incidencias o no hay untyped` | `items: []`,`total:0`,`untyped_count:0` ⇒ `false`; con `items` no vacío ⇒ `false`; `null`/`undefined` ⇒ `false` |

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/incidents/incidentInboxModel.test.ts
```

#### Criterio de aceptación (binario)

1. **17 tests passed, 0 failed.**
2. `Select-String -Path "src\incidents\incidentInboxModel.ts" -Pattern "import React|document\.|window\."` devuelve **0 líneas**.

#### Impacto por runtime

Ninguno en los 3. Fallback: n/a.

---

### F5 — Namespace de API en el frontend

**Objetivo (1 frase):** exponer `IncidentInbox.status()` e `IncidentInbox.items()` usando `rawGet`, para que la UI pueda leer `feature_disabled` sin excepciones.

**Trabajo del operador:** ninguno. **Flag:** ninguna (wiring).

#### Archivo a EDITAR: `Stacky Agents/frontend/src/api/endpoints.ts`

1. Agregar `rawGet` a la lista de nombres importados desde `./client` (si ya figura, no duplicar).
2. **Los `import type` van AL TOPE del archivo**, junto a los demás imports (no al final): el proyecto compila con `verbatimModuleSyntax`/reglas estándar de TS y un `import` a mitad de archivo es un error de orden en el linter. *(La v1 dejaba esto como un "si el linter lo exige…": resuelto.)*

```ts
import type {
  IncidentInboxResponse,
  IncidentInboxStatus,
  IncidentScope,
} from "../incidents/incidentInboxModel";
```

3. Agregar el namespace **al final del archivo**:

```ts
// ─── Plan 238 — Bandeja de incidencias abiertas ────────────────────────────
export const IncidentInbox = {
  /** Nunca lanza por status: 200 siempre (enabled:false con la flag OFF). */
  status: (project?: string | null) => {
    const qs = project ? `?project=${encodeURIComponent(project)}` : "";
    return rawGet<IncidentInboxStatus>(`/api/incident-inbox/status${qs}`);
  },
  /** 404 feature_disabled llega como errorBody, NO como excepcion. */
  items: (project?: string | null, scope: IncidentScope = "open") => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    params.set("scope", scope);
    return rawGet<IncidentInboxResponse>(
      `/api/incident-inbox/items?${params.toString()}`
    );
  },
};
```

#### Tests

No hay test propio (es wiring de ~15 líneas sin lógica). Se cubre por `npx tsc --noEmit` y por el smoke de F9.

#### Criterio de aceptación (binario)

1. `npx tsc --noEmit` sin errores nuevos.
2. `Select-String -Path "src\api\endpoints.ts" -Pattern "incident-inbox"` devuelve **exactamente 2** líneas.

> **Nota de merge:** el plan hermano 237 también edita `frontend/src/api/endpoints.ts`. Tras cualquier merge, verificar que el bloque `export const IncidentInbox` aparezca **una sola vez**.

#### Impacto por runtime

Ninguno en los 3. Fallback: n/a.

---

### F6 — Página `IncidentInboxPage` (la vista dedicada)

**Objetivo (1 frase):** la pantalla que el operador pidió — solo incidencias, abiertas primero, con contador visible.

**Trabajo del operador:** ninguno.

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED` (la página consulta `IncidentInbox.status()` al montar).

#### Archivos a CREAR (2)

**(a) `Stacky Agents/frontend/src/pages/IncidentInboxPage.tsx`**

Estructura obligatoria (pseudocódigo fiel; el implementador escribe el JSX real):

```
imports:
  React, { useMemo, useState }
  useQuery de "@tanstack/react-query"
  { IncidentInbox } de "../api/endpoints"
  { filterBySearch, sortIncidents, summaryLabel, countByState,
    formatIncidentsForCopy, parseScope, isProviderBlind,
    type IncidentScope, type IncidentInboxItem } de "../incidents/incidentInboxModel"
  { copyText, resolveCopyExportEnabled } de "../services/copyService"
  { INCIDENT_ICON, getWorkItemTypeColor, formatWorkItemTypeLabel }
      de "../utils/workItemTypeColor"     // SOLO LECTURA: PROHIBIDO editar ese archivo
  { useWorkbench } de "../store/workbench"
  EmptyState, LoadErrorState, SkeletonList, Toast de "../components/..."
  styles de "./IncidentInboxPage.module.css"

estado local:
  scope: IncidentScope  -> inicial: parseScope(new URLSearchParams(window.location.search).get("scope"))
  search: string        -> ""
  toast: ToastState | null

datos:
  activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null)

  statusQ = useQuery({
    queryKey: ["incident-inbox-status", activeProjectName],
    queryFn: () => IncidentInbox.status(activeProjectName),
    staleTime: 5 * 60 * 1000,
  })

  itemsQ = useQuery({
    queryKey: ["incident-inbox-items", activeProjectName, scope],
    queryFn: () => IncidentInbox.items(activeProjectName, scope),
    enabled: statusQ.data?.data?.enabled === true,
    refetchInterval: 45_000,     // mismo ritmo que el board (TicketBoard.tsx:870)
    staleTime: 22_500,
    refetchOnWindowFocus: true,
  })

render, en este orden de precedencia:
  1. statusQ cargando o itemsQ cargando        -> <SkeletonList />
  2. statusQ.data?.data?.enabled === false     -> <EmptyState> "La bandeja de
        incidencias esta apagada. Activala en Configuracion > Flags del arnes >
        Interfaz UI > 'Bandeja de incidencias abiertas'." </EmptyState>
  3. itemsQ.data?.ok === false y
     errorBody.error === "feature_disabled"    -> mismo EmptyState del caso 2
  4. itemsQ.isError o itemsQ.data?.ok === false-> <LoadErrorState> con
        errorBody.message si existe y boton "Reintentar" -> itemsQ.refetch()
  5a. isProviderBlind(itemsQ.data?.data)       -> <EmptyState> "Este proyecto
        tiene N ticket(s) sin tipo de item sincronizado, asi que la bandeja no
        puede separarlos. Suele pasar cuando el tracker no es Azure DevOps.
        Las incidencias siguen visibles en el tablero general."
        (N = untyped_count; el texto NO dice 'no hay incidencias')
  5b. lista vacia y NO providerBlind           -> <EmptyState> "No hay
        incidencias abiertas en este proyecto." (scope==="open") /
        "Este proyecto no tiene incidencias." (scope==="all")
  6. caso feliz                                -> cabecera + lista

derivados (useMemo):
  raw      = itemsQ.data?.data?.items ?? []
  counts   = itemsQ.data?.data?.counts ?? {open:0, closed:0, total:0}
  visible  = sortIncidents(filterBySearch(raw, search))   // el server ya filtro por scope
  byState  = countByState(visible)

cabecera:
  h1 "Incidencias"
  span con summaryLabel(counts)                      // "7 abiertas de 19"
  toggle de 2 botones: "Solo abiertas" | "Todas"
      -> al cambiar: setScope(next) Y actualizar la URL sin recargar:
         const url = new URL(window.location.href);
         if (next === "all") url.searchParams.set("scope", "todas");
         else url.searchParams.delete("scope");
         window.history.replaceState({}, "", url.pathname + url.search);
         // Compatible con routes.ts: parseRoute preserva query params
         // desconocidos verbatim (services/routes.ts:73-74). replaceState NO
         // dispara popstate, asi que no re-monta la pagina.
  input de busqueda (value=search, onChange)
  boton "Copiar lista" -> SOLO si el gate del plan 194 lo permite (ver abajo);
      onClick: copyText(formatIncidentsForCopy(visible)) y setToast(...)
  si itemsQ.data?.data?.truncated -> banner "Mostrando las primeras 1000
      incidencias. Afina la busqueda para ver el resto."
  chips de byState (estado + cantidad), solo informativos, sin onClick

lista (una fila por incidencia):
  - punto/badge de tipo: formatWorkItemTypeLabel(item.work_item_type); el color
    se aplica por ref+effect (NUNCA con style={{...}}), leyendo
    getWorkItemTypeColor(item.work_item_type)
  - "#<ado_id>" + titulo
  - badge de estado (item.ado_state)
  - badge "Abierta" / "Cerrada" segun item.is_open
  - si item.stacky_status === "running": indicador "agente corriendo"
    (si stacky_status falta o es desconocido, tratar como "idle")
  - asignado: item.assigned_to_ado ?? "sin asignar"
  - link "Abrir en el tracker" -> item.ado_url (target="_blank",
    rel="noopener noreferrer"); si ado_url es falsy, NO renderizar el link
```

**Gate del portapapeles (C8, obligatorio).** `copyText` (`services/copyService.ts:29`) **no** consulta la flag 194: el gate es el wrapper `resolveCopyExportEnabled` (`copyService.ts:101-108`, sobre `flagEnabledFrom` de `services/flagGate.ts`). Procedimiento literal:

```powershell
Select-String -Path "src" -Pattern "resolveCopyExportEnabled" -Recurse
```

- Si aparecen call-sites: **copiar textualmente** el patrón de uno de ellos (de dónde sale el objeto `flags`) y aplicarlo al botón "Copiar lista".
- Si devuelve **0** call-sites fuera de `copyService.ts`: **NO inventar** un fetch de flags. Renderizar el botón siempre y dejar constancia en el reporte final ("gate 194 sin call-site de referencia; botón sin gatear, igual que el resto de las superficies actuales").

**REGLAS DURAS de este archivo (los ratchets las verifican):**

- **CERO `style={{...}}`.** El archivo es nuevo y el ratchet de deuda de UI exige alcance 0 en archivos nuevos. Para el color por tipo usar `useRef` + `useEffect` con `el.style.setProperty("--incident-type-color", color)`, o una clase CSS por tipo. **No hay excepción.**
- **TRAMPA VERIFICADA (C14):** el ratchet cuenta la secuencia `style={{` **también dentro de comentarios**. **PROHIBIDO** escribir esa secuencia en un comentario del `.tsx` (ni siquiera para explicar que no se usa). Referirse a ella como "estilos en línea".
- **CERO literales hexadecimales en el `.module.css`.** Usar `var(--...)` con los tokens que ya usan los CSS modules vecinos. (El hex que devuelve `getWorkItemTypeColor` viaja por TS, no por CSS: eso no cuenta.)
- **CERO `navigator.clipboard.writeText`.** Copiar **solo** con `copyText` (lo exige `src/__tests__/copyDebtRatchet.test.ts`).
- **CERO modales ad-hoc.** Esta página no abre diálogos (lo exige `src/__tests__/adhocModalRatchet.test.ts`).
- **CERO edición de `utils/workItemTypeColor.ts`** — está sucio por otra sesión (§F-1). Solo importar.

**(b) `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css`**

Clases mínimas: `.root`, `.header`, `.headerLeft`, `.headerActions`, `.title`, `.count`, `.scopeToggle`, `.scopeBtn`, `.scopeActive`, `.search`, `.copyBtn`, `.banner`, `.chips`, `.chip`, `.list`, `.row`, `.typeDot`, `.adoId`, `.rowTitle`, `.stateBadge`, `.openBadge`, `.closedBadge`, `.runningDot`, `.assignee`, `.link`.

Para `.typeDot`: `background: var(--incident-type-color, var(--color-text-muted));`.

#### Tests

**Honestidad obligatoria:** este archivo **no se puede testear con unit tests** — el repo **no tiene** `@testing-library/react` ni `jsdom` en `frontend/package.json`. Toda la lógica ya está probada en F4. El gate real de esta fase es: `npx tsc --noEmit`, los ratchets, y el smoke de F9. **Prohibido inventar un test de render que no puede correr.**

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
npx vitest run src/__tests__/adhocModalRatchet.test.ts
```

> **GOTCHA de ratchets:** `uiDebtRatchet` puede estar **rojo por deuda ajena**. La salida base ya quedó guardada en F-1. Al terminar, comparar: los archivos de este plan (`IncidentInboxPage.tsx`, `IncidentInboxEntryButton.tsx`, `incidentInboxModel.ts`) deben aparecer con **0**. Si el ratchet falla **solo** por archivos ajenos, el criterio se considera cumplido y se deja constancia. **PROHIBIDO** regenerar el baseline con `UI_DEBT_REGEN=1` (aborta si cualquier archivo ajeno subió).

#### Criterio de aceptación (binario)

1. `npx tsc --noEmit` sin errores nuevos.
2. `Select-String -Path "src\pages\IncidentInboxPage.tsx" -Pattern 'style=\{\{'` devuelve **0 líneas**.
3. `Select-String -Path "src\pages\IncidentInboxPage.module.css" -Pattern "#[0-9a-fA-F]{3,8}"` devuelve **0 líneas**.
4. `Select-String -Path "src\pages\IncidentInboxPage.tsx" -Pattern "navigator.clipboard"` devuelve **0 líneas**.
5. `uiDebtRatchet` no reporta deuda **atribuible a los 3 archivos nuevos de este plan**.
6. `git status --short -- src/utils/workItemTypeColor.ts` **idéntico a la foto de F-1**.

#### Impacto por runtime

| Runtime | Impacto | Fallback |
|---|---|---|
| Codex CLI / Claude Code CLI / GitHub Copilot Pro | ninguno en los 3 | la fila muestra `stacky_status` tal cual; valor ausente o desconocido ⇒ "idle" |

---

### F7 — Registro del tab, gate por flag y deep-link `/incidencias`

**Objetivo (1 frase):** que la bandeja tenga URL propia, entrada en la barra lateral (grupo "Trabajo", debajo de "Tickets ADO") y entrada en la paleta de comandos — **y que las tres desaparezcan con la flag OFF** (P9).

**Trabajo del operador:** ninguno.

> **Cambio de diseño v2 (bloqueantes C3 + C4).** La v1 metía `"incidencias"` en `ALWAYS_VISIBLE` argumentando que `shellNav.ts` es puro y no puede consultar la flag. **Eso es falso:** `computeVisibleTabs` recibe los gates como **booleanos de entrada** en `VisibilityInput` (`shellNav.ts:50-57`) — exactamente como `migradorEnabled`, `devopsEnabled`, `evolutionEnabled`. El módulo sigue puro y P9 pasa a ser verdad. Además, hacerlo así **reduce** las ediciones del test de 4 a 3 y no rompe `orderedVisibleGroups`.

#### Archivos a EDITAR (6)

**(a) `Stacky Agents/frontend/src/services/routes.ts`**

- `:5-8` — agregar `"incidencias"` a la unión `Tab`:
  ```ts
  | "migrador" | "devops" | "dbcompare" | "costcenter" | "planes" | "evolution"
  | "incidencias";
  ```
- `:14-20` — agregar la ruta en `TAB_PATHS`:
  ```ts
  incidencias: "/incidencias", // Plan 238
  ```

**(b) `Stacky Agents/frontend/src/components/shell/shellNav.ts`** — 4 ediciones:

1. `:5-9` — agregar `"incidencias"` a la unión `ShellTab`.
2. `:16-34` — agregar en `TAB_META`, **inmediatamente después** de la línea `tickets:`:
   ```ts
   incidencias: { label: "Incidencias",   iconName: "Ambulance" },
   ```
3. `:43` — reemplazar la línea del grupo "trabajo" por:
   ```ts
   { id: "trabajo", label: "Trabajo", tabs: ["team", "tickets", "incidencias", "review", "unblocker"] },
   ```
4. `VisibilityInput` (`:50-57`) y `computeVisibleTabs` (`:65+`) — agregar el gate **opcional**:
   ```ts
   // en VisibilityInput, junto a evolutionEnabled:
   incidentInboxEnabled?: boolean;   // Plan 238 — undefined => oculto
   // en computeVisibleTabs, junto a los demas gates:
   if (input.incidentInboxEnabled) v.add("incidencias");
   ```
   **`incidencias` NO va a `ALWAYS_VISIBLE` (`:62-64`).** El campo es **opcional** a propósito: los tests existentes que no lo pasan siguen verdes.

**(c) `Stacky Agents/frontend/src/components/shell/shellIcons.ts`** — **verificado 2026-07-25:** `ICON_BY_NAME` (`:8-12`) contiene exactamente 17 íconos y **NO** tiene `Ambulance` **ni** `AlertTriangle`. Hay que agregarlo, en **2 ediciones** (import + mapa). Procedimiento determinista:

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
Select-String -Path "node_modules\lucide-react\dist\lucide-react.d.ts" -Pattern "declare const Ambulance" -SimpleMatch
```

- **≥1 línea** ⇒ agregar `Ambulance` a las dos listas de `shellIcons.ts` (el `import { ... } from "lucide-react"` y el objeto `ICON_BY_NAME`), y dejar `iconName: "Ambulance"`.
- **0 líneas** ⇒ repetir la búsqueda con `AlertTriangle`; si aparece, usar ése y poner `iconName: "AlertTriangle"`.
- **Ninguno de los dos** ⇒ **NO inventar un ícono**: usar `iconName: "Inbox"` (ya está en `ICON_BY_NAME`, cero ediciones en `shellIcons.ts`).

> **Por qué importa:** `AppSidebar.tsx:34` hace `ICON_BY_NAME[meta.iconName]`; un nombre inexistente da `undefined` y **rompe el render de toda la barra lateral**.

**(d) `Stacky Agents/frontend/src/components/shell/__tests__/shellNav.test.ts`** — **exactamente 3 ediciones literales** (verificadas contra el archivo real):

1. `ALL_TABS` (`:11-15`): agregar `"incidencias"` ⇒ 18 entradas.
2. Título del primer test: reemplazar la cadena `"TAB_META cubre exactamente los 17 tabs"` por `"TAB_META cubre exactamente los 18 tabs"`.
3. En el test cuyo título es **exactamente** `"computeVisibleTabs: opcionales aparecen solo con su gate"`, agregar al objeto de entrada:
   ```ts
   incidentInboxEnabled: true,
   ```
   (sin esto, ese test compara contra `ALL_TABS` —que ahora incluye `"incidencias"`— y falla).

**NO tocar** (verificado que siguen verdes con este diseño):
- `"computeVisibleTabs: los 6 base siempre visibles (team NO, es ocultable)"` — su entrada no pasa `incidentInboxEnabled` ⇒ siguen siendo **6**. El título **no cambia**.
- `"orderedVisibleGroups oculta grupos vacíos y filtra tabs ocultos"` — su entrada tampoco lo pasa ⇒ `trabajo` sigue siendo `["review","tickets","unblocker"]`.
- `"cada tab aparece en exactamente un grupo (cobertura 16, sin duplicados)"` — el assert compara contra `ALL_TABS`, se arregla solo. El "16" del título ya estaba desactualizado antes de este plan: **no tocarlo** (fuera de scope).

**(e) `Stacky Agents/frontend/src/App.tsx`** — 4 inserciones:

1. Imports, junto a los demás de páginas:
   ```tsx
   import IncidentInboxPage from "./pages/IncidentInboxPage"; // Plan 238
   import { INCIDENT_ICON } from "./utils/workItemTypeColor"; // Plan 238 (reuso, C13)
   ```
2. Un gate booleano junto a los demás (`migradorEnabled`, `evolutionEnabled`, …), alimentado por la misma consulta de status que ya usa la página:
   ```tsx
   // Plan 238 — gate de la bandeja de incidencias (default ON del lado backend)
   const incidentInboxQ = useQuery({
     queryKey: ["incident-inbox-status", null],
     queryFn: () => IncidentInbox.status(null),
     staleTime: 5 * 60 * 1000,
   });
   const incidentInboxEnabled = incidentInboxQ.data?.data?.enabled === true;
   ```
   y pasarlo al `computeVisibleTabs({...})` existente como `incidentInboxEnabled`.
   > La `queryKey` es **la misma** que usan la página (F6) y el botón (F8): react-query comparte la respuesta, así que **no se agrega ni una request**.
3. Dentro del fragment `pages` (`:284-299`), **inmediatamente después** de la línea `{tab === "tickets"  && <TicketBoard />}` (`:287`):
   ```tsx
   {tab === "incidencias" && incidentInboxEnabled && <IncidentInboxPage />} {/* Plan 238 */}
   ```
4. En la `<nav>` v1 (`:335-369`), **inmediatamente después** del `</button>` de Tickets ADO (`:349`):
   ```tsx
   {incidentInboxEnabled && (
     <button
       className={`${styles.navTab} ${tab === "incidencias" ? styles.active : ""}`}
       onClick={() => selectTab("incidencias")}
     >
       {INCIDENT_ICON} Incidencias
     </button>
   )}
   ```

> **NO tocar** la línea `<nav className={styles.nav} data-tour="nav">` (`:335`). El test `src/components/shell/__tests__/shellIntegration.test.ts:8` espera `'<nav className={styles.nav}>'` **sin** el `data-tour` y por eso **ya está rojo desde antes de este plan** (comprobado en F-1). Deuda preexistente, **FUERA DE SCOPE**: no arreglarlo, no cambiar el markup para hacerlo pasar. Dejar constancia en el reporte final.

**(f) `Stacky Agents/frontend/src/components/commandPaletteData.ts`** — agregar la entrada en `NAV_COMMANDS` (`:59-73`), después de `nav-tickets`:

```ts
{ id: "nav-incidencias", path: "/incidencias", label: "Ir a Incidencias", icon: "🚑" },
```

> `NAV_COMMANDS` es **data pura** sin imports de utilidades; acá el emoji va literal (es el mismo valor que `INCIDENT_ICON`, `workItemTypeColor.ts:37`). El filtrado por flag de la paleta se resuelve en el consumidor: si la paleta ya filtra por tabs visibles, no hace falta nada; si no, filtrar la entrada `nav-incidencias` con el mismo `incidentInboxEnabled` de App.tsx. Verificar con `Select-String -Path "src" -Pattern "NAV_COMMANDS" -Recurse` y **copiar el patrón del consumidor**, sin inventar uno nuevo.

#### Tests PRIMERO (TDD)

Antes de editar, correr `npx vitest run src/components/shell/__tests__/shellNav.test.ts` y confirmar que está **verde**. Después de editar `shellNav.ts` (y **antes** de tocar el test), volver a correrlo: debe estar **rojo** en el assert de cobertura (18 vs 17). Recién entonces aplicar las 3 ediciones de (d). Eso prueba que el test cubre el drift de verdad.

**Test nuevo — [ADICIÓN ARQUITECTO A1]:** crear `Stacky Agents/frontend/src/components/shell/__tests__/shellIconsCoverage.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { TAB_META } from "../shellNav";
import { ICON_BY_NAME } from "../shellIcons";

describe("shellIcons — cobertura de iconos", () => {
  it("todo iconName de TAB_META existe en ICON_BY_NAME", () => {
    const faltantes = Object.entries(TAB_META)
      .filter(([, meta]) => ICON_BY_NAME[meta.iconName] === undefined)
      .map(([tab, meta]) => `${tab} -> ${meta.iconName}`);
    expect(faltantes).toEqual([]);
  });
});
```

> **Por qué vale:** `AppSidebar.tsx:34` resuelve el ícono por nombre en runtime. Hasta hoy, un `iconName` mal escrito **solo se descubría rompiendo la barra lateral en el navegador**. Este test de 8 líneas lo convierte en un rojo determinista, **para este plan y para todos los tabs futuros**. Cero costo en runtime.

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/shell/__tests__/shellNav.test.ts
npx vitest run src/components/shell/__tests__/shellIconsCoverage.test.ts
npx vitest run src/services/__tests__/routes.test.ts
npx vitest run src/services/__tests__/routesDeepLink.test.ts
npx tsc --noEmit
```

#### Criterio de aceptación (binario)

1. `shellNav.test.ts` **verde** con 18 tabs, **con exactamente 3 líneas modificadas** respecto de su versión previa.
2. `shellIconsCoverage.test.ts` **verde** (1 passed).
3. `routes.test.ts` y `routesDeepLink.test.ts` **verdes** (no deberían requerir cambios; si alguno rompiera, actualizarlo **agregando** el tab nuevo, nunca removiendo asserts).
4. `npx tsc --noEmit` sin errores nuevos.
5. `Select-String -Path "src\App.tsx" -Pattern "IncidentInboxPage"` devuelve **exactamente 2** líneas (import + render).
6. `Select-String -Path "src\components\shell\shellNav.ts" -Pattern "ALWAYS_VISIBLE"` — la lista sigue teniendo **6** elementos (incidencias **no** está ahí).
7. `shellIntegration.test.ts` sigue **exactamente igual de rojo que en F-1** (mismo test fallando, ni uno más).

#### Impacto por runtime

Ninguno en los 3. Fallback: si `IncidentInbox.status()` falla, `incidentInboxEnabled` queda `false` y la app se ve **idéntica a hoy**.

---

### F8 — Punto de entrada desde Tickets ADO (la única cirugía en `TicketBoard.tsx`)

**Objetivo (1 frase):** que desde el tablero de Tickets ADO se entre a la bandeja con un clic, sin alterar nada más del tablero.

**Valor:** cumple literalmente el pedido ("dentro de tickets ADO... entrar a algún apartado de incidencias") y hace la función descubrible sin explorar la barra lateral.

**Trabajo del operador:** ninguno.

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED`. El botón se auto-oculta cuando la flag está OFF (consulta `IncidentInbox.status()` él mismo, con la misma `queryKey` ⇒ 0 requests extra).

#### Archivos a CREAR (2)

**(a) `Stacky Agents/frontend/src/components/IncidentInboxEntryButton.tsx`**

Componente **autocontenido**: sin props obligatorias, sin estilos en línea, con su propio CSS module.

```tsx
/**
 * Plan 238 F8 — Punto de entrada a la bandeja de incidencias desde el tablero.
 * AUTOCONTENIDO a proposito: TicketBoard.tsx solo agrega el import y el
 * elemento. Cero props, cero estilos en linea, CSS module propio (no se toca
 * TicketBoard.module.css, que esta disputado por otra sesion).
 */
import { useQuery } from "@tanstack/react-query";
import { IncidentInbox } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { TAB_PATHS } from "../services/routes";
import { INCIDENT_ICON } from "../utils/workItemTypeColor";
import styles from "./IncidentInboxEntryButton.module.css";

export default function IncidentInboxEntryButton() {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const statusQ = useQuery({
    queryKey: ["incident-inbox-status", activeProjectName],
    queryFn: () => IncidentInbox.status(activeProjectName),
    staleTime: 5 * 60 * 1000,
  });

  const itemsQ = useQuery({
    queryKey: ["incident-inbox-items", activeProjectName, "open"],
    queryFn: () => IncidentInbox.items(activeProjectName, "open"),
    enabled: statusQ.data?.data?.enabled === true,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (statusQ.data?.data?.enabled !== true) return null;

  const openCount = itemsQ.data?.data?.counts?.open ?? null;

  const go = () => {
    // NAVEGACION DEL ROUTER CASERO. Verificado 2026-07-25: `navigateToRoute`
    // (App.tsx:108) es una CLAUSURA LOCAL del componente App, NO un export.
    // PROHIBIDO exportarla: crearia el ciclo App -> TicketBoard -> este
    // componente -> App. El listener de App.tsx:171-175 escucha "popstate" y
    // re-deriva TODO el estado con parseRoute, asi que este par es suficiente.
    window.history.pushState({}, "", TAB_PATHS.incidencias);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <button
      className={styles.entryBtn}
      onClick={go}
      title="Ver solo las incidencias, con las abiertas primero"
    >
      {INCIDENT_ICON} Incidencias
      {openCount !== null && openCount > 0 && (
        <span className={styles.badge} aria-label={`${openCount} incidencias abiertas`}>
          {openCount}
        </span>
      )}
    </button>
  );
}
```

**(b) `Stacky Agents/frontend/src/components/IncidentInboxEntryButton.module.css`**

Dos clases: `.entryBtn` y `.badge`.

**Cómo obtener el estilo sin tocar `TicketBoard.module.css`:** **leer** (no editar) `frontend/src/pages/TicketBoard.module.css`, localizar la regla `.syncBtn` (es la clase que usan los dos botones vecinos de la cabecera, `TicketBoard.tsx:1002` y `:1011`) y copiar sus declaraciones a `.entryBtn`, conservando **textualmente** los `var(--...)`. Si alguna declaración usa un literal hexadecimal, sustituirlo por el token `var(--...)` que ya se use en ese mismo archivo para el mismo rol; si no hay token equivalente, usar `var(--color-text-muted)` y dejar constancia. Para `.badge`, calcar la regla `.navBadge` de `App.module.css` con el mismo criterio.

#### Archivo a EDITAR: `Stacky Agents/frontend/src/pages/TicketBoard.tsx` — **EXACTAMENTE 2 LÍNEAS**

**Línea 1 (import).** Ancla textual: buscar la cadena `from "../components/IncidentResolverModal"` (hoy en `:21`) e insertar **inmediatamente después**:

```tsx
import IncidentInboxEntryButton from "../components/IncidentInboxEntryButton"; // Plan 238
```

**Línea 2 (JSX).** Ancla textual **primaria**: buscar la cadena literal `{/* Toggle vista */}` (hoy en `:1018`) e insertar la línea **inmediatamente antes**:

```tsx
          <IncidentInboxEntryButton /> {/* Plan 238 — bandeja de incidencias */}
```

**Fallback** (si F-1 reportó 0 coincidencias de esa cadena): insertar como **último hijo** de `<div className={styles.headerActions}>` (ancla textual `className={styles.headerActions}`, hoy en `:999`).

**NO** reordenar, reformatear ni reindentar ninguna otra línea del archivo. **Los números de línea de este archivo son orientativos: otra sesión lo está editando** (`CLOSED_STATES` ya se corrió de `:83` a `:82`).

**PROHIBIDO en esta fase:**
- Tocar `TicketBoard.module.css`.
- Tocar cualquier otra parte de `TicketBoard.tsx` (filtros, `CLOSED_STATES`, `viewMode`, `filterNode`, tarjetas, modales).
- Tocar cualquiera de los archivos de la lista de PROHIBIDOS de §F-1.

#### Tests

Sin unit test (no hay RTL/jsdom). Gate: `npx tsc --noEmit`, ratchets y el smoke de F9.

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/__tests__/uiDebtRatchet.test.ts
git diff --stat -- src/pages/TicketBoard.tsx
git status --short
```

#### Criterio de aceptación (binario)

1. `git diff --stat -- src/pages/TicketBoard.tsx` muestra **exactamente 2 líneas más** que el diff base capturado en F-1 (y **0 eliminadas** nuevas).
2. `git status --short` no lista **ningún** archivo de la lista de PROHIBIDOS de §F-1 con cambios distintos a los de la foto inicial.
3. `npx tsc --noEmit` sin errores nuevos.
4. `Select-String -Path "src\components\IncidentInboxEntryButton.tsx" -Pattern 'style=\{\{'` devuelve **0 líneas**.
5. `Select-String -Path "src" -Pattern "export const navigateToRoute" -Recurse` devuelve **0 líneas** (nadie exportó la clausura de App).

#### Impacto por runtime

Ninguno en los 3. Fallback: si `IncidentInbox.status()` falla (backend caído), el botón devuelve `null` y el tablero queda **idéntico a hoy**.

---

### F9 — Verificación integral, huellas de regresión y smoke manual

**Objetivo (1 frase):** probar de punta a punta que la bandeja muestra las incidencias reales del proyecto activo y que el tablero general no cambió.

**Trabajo del operador:** ninguno (el smoke lo hace quien implementa).

#### Comandos exactos

```powershell
# Backend: por archivo (nunca la suite completa)
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan238_inbox_flag.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan238_incident_inbox_core.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan238_incident_inbox_api.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags_help.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_flag_wiring.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_ratchet_meta.py -v
& ".\.venv\Scripts\python.exe" -m compileall -q api services

# Frontend: por archivo
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/incidents/incidentInboxModel.test.ts
npx vitest run src/api/__tests__/rawGet.test.ts
npx vitest run src/components/shell/__tests__/shellNav.test.ts
npx vitest run src/components/shell/__tests__/shellIconsCoverage.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
npx vitest run src/__tests__/adhocModalRatchet.test.ts
```

#### Huellas de regresión (obligatorio)

Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` dos entradas con el shape que ya usa el archivo (`id`, `patron`, `plan`, `fecha`, `guard_test`):

| id | patrón | guard_test |
|---|---|---|
| `PLAN238-INBOX-CIEGA-SIN-TIPO` | La bandeja devuelve `items: []` y `counts.total: 0` en un proyecto que sí tiene tickets, porque `Ticket.work_item_type` está NULL (tracker no-ADO). Síntoma: pantalla vacía sin explicación. | `tests/test_plan238_incident_inbox_api.py::test_gitlab_sin_tipo_reporta_untyped_count` |
| `PLAN238-SHELL-ICONO-INEXISTENTE` | `TAB_META[t].iconName` no existe en `ICON_BY_NAME` ⇒ `AppSidebar.tsx:34` renderiza `undefined` y rompe la barra lateral entera. | `src/components/shell/__tests__/shellIconsCoverage.test.ts` |

#### Smoke manual (7 pasos, obligatorio)

1. Levantar backend + frontend. Abrir el tablero de Tickets ADO. **Verificar que se ve exactamente igual que antes**, salvo el botón nuevo "🚑 Incidencias" en la cabecera.
2. Clic en el botón ⇒ la URL pasa a `/incidencias` y se ve la bandeja con solo Issues/Bugs.
3. Contar las incidencias abiertas en la bandeja y cruzarlo contra `GET /api/incident-inbox/items?scope=open` en el navegador. Deben coincidir, y `counts.total` debe coincidir con `?scope=all`.
4. Cambiar a "Todas" ⇒ aparecen las cerradas, la URL pasa a `/incidencias?scope=todas`. **Recargar con F5** ⇒ sigue en "Todas" (deep-link).
5. "Copiar lista" ⇒ pegar en un editor y verificar una línea por incidencia con 4 campos.
6. Apagar la flag desde **Configuración > Flags del arnés > Interfaz UI > "Bandeja de incidencias abiertas"**, recargar ⇒ **desaparecen los 4**: el botón del tablero, el tab de la barra lateral, el botón de la nav v1 y la entrada de la paleta. `/incidencias` no renderiza la página. Volver a encenderla.
7. **Paridad de proveedor:** si hay un proyecto con tracker GitLab, abrir la bandeja ahí y verificar que muestra el mensaje explicativo de `untyped_count` (§F6 caso 5a) y **no** "No hay incidencias". Si no hay proyecto GitLab disponible, dejar constancia de que el paso se cubrió solo con el test `test_gitlab_sin_tipo_reporta_untyped_count`.

#### Criterio de aceptación (binario)

1. Todos los comandos en verde, con **el output pegado en el reporte** — salvo los 2 rojos preexistentes declarados: `shellIntegration.test.ts` (`data-tour="nav"`) y `test_harness_flags_help.py` si su lista de faltantes contiene solo keys ajenas (192 y posteriores).
2. Los 7 pasos del smoke se cumplen tal cual están descritos.
3. Las 2 huellas están en `error_fingerprints.json` y el JSON parsea (`python -c "import json;json.load(open(...))"`).
4. Actualizar el encabezado de **este documento**: `**Estado:** IMPLEMENTADO` + fecha + lista de fases completadas.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | **Conflicto con la sesión paralela** en `TicketBoard.tsx`. | Alta | Medio | §F-1 captura el diff base; la cirugía es de 2 líneas con **ancla textual** (`{/* Toggle vista */}`), nunca por número de línea; `TicketBoard.module.css` no se toca; el botón es autocontenido. |
| R2 | **Colisión con los planes 212 y 213**, que también tocan `TicketBoard.tsx`. | Media | Medio | Operan en zonas distintas (selector de modelo/effort y analistas). Este plan solo inserta un hijo más en `headerActions`. Merge aditivo. |
| R3 | **Duplicado silencioso al mergear registros compartidos** (git no marca conflicto si dos ramas agregan la misma línea). | Media | Alto | Verificación de conteo exacto tras **cada** merge en: `api/__init__.py` (`incident_inbox_bp` = 2), `harness_flags.py` (key = 2), `endpoints.ts` (`incident-inbox` = 2), `App.tsx` (`IncidentInboxPage` = 2), `run_harness_tests.sh` (cada `test_plan238_*` = 1). |
| R4 | **Colisión con el plan hermano 237** (triage), que edita `config.py`, `harness_flags.py`, `harness_flags_help.py`, `test_harness_flags.py`, `run_harness_tests.sh` y `endpoints.ts`. | Alta | Medio | Todos los cambios de 238 en esos archivos son **aditivos y en bloques propios rotulados "Plan 238"**. R3 cubre la verificación post-merge. |
| R5 | **El plan 216 aterriza y cambia el shape de `state_flow`.** | Media | Bajo | El lector trata `state_flow.closed_states` como opcional y cae al default. El guard cruzado real (F1 test 6) se pone rojo el día que 216 rechace la key; mientras 216 no exista, hace `skip` explícito. |
| R6 | **`_request_project_name` / `_ticket_project_filter` se renombran** en `api/tickets.py`. | Baja | Alto | Import lazy con `try/except ImportError` ⇒ 200 con `project_filter_seam_missing` (error visible, nunca mudo). Ratchet `test_seam_de_filtro_de_proyecto_existe`. |
| R7 | **`iconName` inexistente en `ICON_BY_NAME`** ⇒ barra lateral rota. | Media | Alto | §F7-c da un procedimiento de 3 ramas con fallback garantizado (`Inbox`), y **[A1]** agrega un test permanente de cobertura de íconos. |
| R8 | **`uiDebtRatchet` rojo por deuda ajena** confunde el criterio. | Alta | Bajo | §F-1 captura la salida base; §F6 obliga a comparar solo los archivos de este plan. Prohibido regenerar el baseline. |
| R9 | **Proyecto con tracker GitLab: bandeja vacía.** | Alta (si hay proyectos GitLab) | Alto→Bajo | §4.1.4 + `untyped_count` + EmptyState explicativo + test dedicado. La causa raíz (sync de GitLab sin tipo) queda **declarada** y fuera de scope. |
| R10 | **Miles de incidencias**: consulta lenta. | Baja | Medio | Filtro por tipo y por scope en SQL, sin N+1, `LIMIT 1000` + `truncated`, `counts` con 2 `COUNT(*)` (baratos, sin materializar). |
| R11 | **El operador cree que la bandeja "actúa"** (cierra o lanza agentes). | Baja | Bajo | Solo lectura explícita; las acciones siguen en el tablero. El único enlace saliente abre el tracker. |
| R12 | **`shellIntegration.test.ts` rojo preexistente** se confunde con una regresión. | Alta | Bajo | Capturado en §F-1, documentado en §F7 y en el DoD. |

---

## 7. Fuera de scope (explícito)

Este plan **NO** hace nada de lo siguiente:

1. **No rediseña ni "mejora de paso" el tablero general.**
2. **No lanza agentes desde la bandeja.** "Resolver con agente" (166 F5) y "Abrir PR" (177) siguen viviendo solo en el tablero.
3. **No implementa el plan 216.** Solo declara el contrato de lectura de `state_flow.closed_states` y su guard cruzado.
4. **No agrega UI para editar `incident_inbox.incident_types` / `closed_states`** en el perfil del cliente. El lector ya las honra; la pantalla de edición es trabajo del 216.
5. **No arregla el sync de GitLab.** Que `Ticket.work_item_type` quede NULL con GitLab (porque el tipo viaja como label `type::<x>`, `gitlab_provider.py:55-56`) es un gap real del sustrato 218 y **le corresponde a la serie de paridad**. Este plan solo lo hace **visible** (§4.1.4).
6. **No arregla la deuda de `harness_flags_help.py`** del plan 192 (`STACKY_CONNECTION_RESILIENCE_ENABLED` sin entrada en `PLAIN_HELP`). Solo agrega la suya.
7. **No arregla `shellIntegration.test.ts`** (rojo preexistente por `data-tour="nav"`).
8. **No toca el flujo de captura de incidencias** (131 / 166): modal, store en disco y `/api/incidents/*` intactos.
9. **No implementa vistas guardadas (173), selección múltiple (187) ni menú contextual (175)** dentro de la bandeja.
10. **No regenera `deployment/harness_defaults.env`.**
11. **No agrega paginación server-side.** El tope de 1000 con `truncated` es suficiente.
12. **No hace `git add`, `commit`, `stash`, `reset`, `rebase` ni `checkout`.** El árbol de trabajo es compartido con una sesión paralela viva; los commits los hace el operador.

---

## 8. Glosario (términos del dominio Stacky)

| Término | Significado |
|---|---|
| **Incidencia** | En Stacky **no existe** un `work_item_type` llamado "Incidencia". Una incidencia es un work item de tipo **`Issue`** o **`Bug`** (`frontend/src/utils/workItemTypeColor.ts:34`). El plan 166 publica las incidencias como `Issue` (`backend/api/tickets.py:6886`). |
| **Work item / ticket** | Ítem del tracker (Azure DevOps o GitLab) sincronizado a la tabla local `tickets` (`backend/models.py:38`). |
| **`ado_state`** | Estado del ítem **en el tracker** ("Active", "New", "Done"…; en GitLab, "opened"/"closed"). Distinto de `stacky_status`. |
| **`stacky_status`** | Estado **interno** de Stacky para ese ticket: `idle` / `running` / `completed` / `error` / `cancelled`. Lo escribe el runtime al ejecutar un agente. |
| **Vocabulario canónico (218 F5)** | `Ticket.to_dict()` emite claves neutrales (`tracker_state`, `item_type`, `item_url`, `assignee`) **más** los alias legacy vía `with_legacy_aliases` (`services/tracker_vocabulary.py:36-47`), que hace `setdefault` y **nunca quita claves**. |
| **`untyped_count`** | Cantidad de tickets del proyecto sin `work_item_type` sincronizado. Señal de que el tracker no es Azure DevOps y de que la bandeja no puede filtrar por tipo (§4.1.4). |
| **Runtime** | Motor que ejecuta al agente: `codex_cli`, `claude_code_cli` o `copilot`. **No** es lo mismo que `LLM_BACKEND`. |
| **Flag del arnés** | Interruptor declarado en `backend/services/harness_flags.py` (`FLAG_REGISTRY`), con default efectivo en `backend/config.py`, ayuda llana en `backend/services/harness_flags_help.py` y edición por el operador desde la UI (panel de flags). |
| **Las 4 excepciones duras** | Únicos motivos válidos para que una flag nueva nazca en OFF: (1) bypassea revisión humana, (2) es destructiva o irreversible, (3) tiene un prerequisito no garantizado, (4) reduce la seguridad. Ninguna aplica acá. |
| **Ratchet** | Test que congela una métrica de deuda para que no empeore. Los de UI viven en `frontend/src/__tests__/*Ratchet.test.ts`. |
| **`HARNESS_TEST_FILES`** | Lista en `backend/scripts/run_harness_tests.sh` donde todo `test_*.py` nuevo debe registrarse — **o** en `harness_ratchet_allowlist.txt`, **nunca en los dos** (`test_harness_ratchet_meta.py`). |
| **Deep-link** | URL que restaura el estado de la vista (plan 165). El router es **casero**, no react-router: `frontend/src/services/routes.ts`. |
| **Seam** | Punto de acoplamiento explícito y documentado entre dos módulos, protegido por un test que falla si se rompe. |
| **HITL** | Stacky amplifica al operador y nunca decide por él. |

---

## 9. Orden de implementación

1. **F-1** — Pre-flight de convivencia (solo lectura; captura diff base, anclas y ratchets).
2. **F0** — Flag `STACKY_INCIDENT_INBOX_ENABLED` (**5** archivos editados + 1 test creado).
3. **F1** — `backend/services/incident_inbox.py` + `test_plan238_incident_inbox_core.py`.
4. **F2** — `backend/api/incident_inbox.py` + registro en `backend/api/__init__.py` + `test_plan238_incident_inbox_api.py`.
5. **F3** — `rawGet` en `frontend/src/api/client.ts` + `src/api/__tests__/rawGet.test.ts`.
6. **F4** — `frontend/src/incidents/incidentInboxModel.ts` + su test co-locado.
7. **F5** — Namespace `IncidentInbox` en `frontend/src/api/endpoints.ts`.
8. **F6** — `IncidentInboxPage.tsx` + `.module.css`.
9. **F7** — Tab + gate por flag: `routes.ts`, `shellNav.ts`, `shellIcons.ts`, `shellNav.test.ts`, `App.tsx`, `commandPaletteData.ts` + `shellIconsCoverage.test.ts`.
10. **F8** — `IncidentInboxEntryButton.tsx` + `.module.css` + **2 líneas** en `TicketBoard.tsx`.
11. **F9** — Verificación integral + huellas + smoke de 7 pasos + estado del documento.

> **Punto de corte seguro:** después de F7 la función ya es 100% usable por barra lateral, URL y paleta de comandos. F8 es la guinda de descubribilidad y la fase de mayor riesgo de conflicto: si la sesión paralela está muy activa sobre `TicketBoard.tsx`, **posponer F8** sin perder valor.

---

## 10. Mapa de colisiones

### Archivos con cambios SIN COMMITEAR de otra sesión (foto 2026-07-25)

| Archivo | Este plan lo… | Riesgo |
|---|---|---|
| `frontend/src/pages/TicketBoard.tsx` | **edita: 2 líneas** (F8), con anclaje textual | **Medio** — también disputado por los planes 212 y 213 |
| `frontend/src/utils/workItemTypeColor.ts` | **solo importa** (`isIncidentWorkItemType`, `INCIDENT_ICON`, `getWorkItemTypeColor`, `formatWorkItemTypeLabel`) | Nulo |
| `frontend/src/incidents/devResolverModel.ts` | **no toca** | Nulo |
| `frontend/src/pages/TicketBoard.module.css` | **lee, no edita** (para calcar `.syncBtn`) | Nulo |
| `frontend/src/pages/SprintBoardPage.tsx` | **no toca** | Nulo |
| `frontend/src/pages/UnblockerPage.tsx` | **no toca** | Nulo |
| `frontend/src/components/TicketGraphView.jsx` / `.module.css` | **no toca** | Nulo |
| `frontend/src/utils/__tests__/workItemTypeColor.test.ts` (untracked) | **no toca** | Nulo |

### Archivos compartidos (registros) — cambios ADITIVOS

| Archivo | Cambio | Verificación post-merge | ¿También lo toca el plan 237? |
|---|---|---|---|
| `backend/services/harness_flags.py` | +1 línea en `_CATEGORY_KEYS`, +1 bloque `FlagSpec` | key = **2** ocurrencias | **Sí** |
| `backend/services/harness_flags_help.py` | +1 entrada `PlainHelp` | key = **1** ocurrencia | **Sí** |
| `backend/config.py` | +1 campo | key = **2** ocurrencias (nombre + getenv) | **Sí** |
| `backend/tests/test_harness_flags.py` | +1 línea en `_CURATED_DEFAULTS_ON` | key = **1** ocurrencia | **Sí** |
| `backend/scripts/run_harness_tests.sh` | +3 líneas | cada `test_plan238_*` = **1** | **Sí** |
| `backend/api/__init__.py` | +2 líneas | `incident_inbox_bp` = **2** | No |
| `frontend/src/api/client.ts` | +1 función `rawGet` | `export async function rawGet` = **1** | No |
| `frontend/src/api/endpoints.ts` | +1 import type + `rawGet` en el import + 1 namespace | `incident-inbox` = **2** | **Sí** |
| `frontend/src/App.tsx` | +4 inserciones | `IncidentInboxPage` = **2** | No |
| `frontend/src/services/routes.ts` | +2 líneas | `incidencias` = **2** | No |
| `frontend/src/components/shell/shellNav.ts` | +5 líneas (unión, `TAB_META`, grupo, `VisibilityInput`, gate) | `incidencias` = **3** | No |
| `frontend/src/components/shell/shellNav.test.ts` | **3** ediciones literales | — | No |
| `frontend/src/components/shell/shellIcons.ts` | +2 líneas **solo si falta el ícono elegido** | — | No |
| `frontend/src/components/commandPaletteData.ts` | +1 entrada | `nav-incidencias` = **1** | No |
| `docs/sistema/error_fingerprints.json` | +2 huellas | JSON parsea | No |

**PROHIBIDO tocar:** `backend/tests/harness_ratchet_allowlist.txt`, `deployment/harness_defaults.env`, `_REQUIRES_MAP_FROZEN`, `_FROZEN_BOUNDS`, `RESERVED_KEYS`.

### Archivos NUEVOS (colisión imposible)

- `backend/services/incident_inbox.py`
- `backend/api/incident_inbox.py`
- `backend/tests/test_plan238_inbox_flag.py`
- `backend/tests/test_plan238_incident_inbox_core.py`
- `backend/tests/test_plan238_incident_inbox_api.py`
- `frontend/src/incidents/incidentInboxModel.ts`
- `frontend/src/incidents/incidentInboxModel.test.ts`
- `frontend/src/api/__tests__/rawGet.test.ts`
- `frontend/src/pages/IncidentInboxPage.tsx`
- `frontend/src/pages/IncidentInboxPage.module.css`
- `frontend/src/components/IncidentInboxEntryButton.tsx`
- `frontend/src/components/IncidentInboxEntryButton.module.css`
- `frontend/src/components/shell/__tests__/shellIconsCoverage.test.ts`

**Total: 13 archivos nuevos, 15 archivos editados (todos con cambios aditivos salvo las 3 ediciones puntuales de `shellNav.test.ts`).**

---

## 11. Definición de Hecho (DoD) global

- [ ] **D0** — F-1 se corrió y su salida (git status, diff base, anclas, 3 ratchets) está pegada en el reporte.
- [ ] **D1** — Los 3 archivos de test backend del plan corren **por archivo** con `backend\.venv\Scripts\python.exe` (Python 3.13.5) y dan **verde**, con el output pegado (no basta con decir "pasó").
- [ ] **D2** — `test_harness_flags.py`, `test_flag_wiring.py` y `test_harness_ratchet_meta.py` **verdes**.
- [ ] **D3** — `test_harness_flags_help.py`: si falla, su lista de faltantes **no** contiene `STACKY_INCIDENT_INBOX_ENABLED`.
- [ ] **D4** — Los 4 archivos de test frontend del plan (`incidentInboxModel`, `rawGet`, `shellNav`, `shellIconsCoverage`) corren **por archivo** y dan **verde**.
- [ ] **D5** — `npx tsc --noEmit` sin **ningún error nuevo** respecto de F-1.
- [ ] **D6** — `uiDebtRatchet`, `copyDebtRatchet` y `adhocModalRatchet` no reportan deuda **atribuible a los archivos nuevos de este plan**.
- [ ] **D7** — `git diff --stat -- "Stacky Agents/frontend/src/pages/TicketBoard.tsx"` muestra **+2 / −0** respecto del diff base de F-1, y `TicketBoard.module.css` sin cambios nuevos.
- [ ] **D8** — El smoke manual de 7 pasos se completó, incluido apagar y volver a encender la flag desde la UI y el paso de paridad de proveedor.
- [ ] **D9** — Con la flag **OFF**: desaparecen el botón del tablero, **el tab de la barra lateral**, **el botón de la nav v1** y **la entrada de la paleta**; `GET /api/incident-inbox/items` devuelve 404 `feature_disabled`; el tablero general queda **idéntico a hoy** (P9 verificado de verdad).
- [ ] **D10** — Conteos exactos post-merge de §10 (todas las filas de la tabla de registros compartidos).
- [ ] **D11** — Ningún archivo de la lista de PROHIBIDOS de §F-1 fue modificado.
- [ ] **D12** — Las 2 huellas de regresión están en `docs/sistema/error_fingerprints.json` y el JSON parsea.
- [ ] **D13** — El renumerado llegó al **código**, no solo al documento. Los artefactos creados/editados por este plan no mencionan el número viejo. Comando (el patrón se arma por concatenación para que este mismo criterio no se auto-detecte):
      ```powershell
      Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
      $viejo = "plan" + "2" + "37"
      Select-String -Path "backend\services\incident_inbox.py","backend\api\incident_inbox.py","backend\tests\test_plan238_*.py","frontend\src\incidents\incidentInboxModel.ts","frontend\src\pages\IncidentInboxPage.tsx","frontend\src\components\IncidentInboxEntryButton.tsx" -Pattern $viejo
      Select-String -Path "backend\scripts\run_harness_tests.sh" -Pattern $viejo
      ```
      Ambos comandos devuelven **0 líneas**. (Las menciones al número vecino que quedan en **este documento** son referencias legítimas al plan hermano de triage y a la propia entrada C11 del changelog.)
- [ ] **D14** — El encabezado de este documento se actualizó a `**Estado:** IMPLEMENTADO` con fecha y fases completadas.
- [ ] **D15** — El reporte final declara explícitamente qué quedó **rojo preexistente** (`shellIntegration.test.ts:8`, `test_harness_flags_help.py` por deuda del 192, y `uiDebtRatchet` si falla solo por deuda ajena) para que nadie lo confunda con una regresión de este plan.
- [ ] **D16** — **No** se ejecutó ningún `git add`, `commit`, `stash`, `reset`, `rebase` ni `checkout`.

---

## 12. Reporte de implementación (2026-07-25)

**Rama:** `feat/plan-217-migrador-mantis-gitlab` (rama de trabajo activa; no se creó una nueva).

### D0 — Foto de F-1 (pre-flight, solo lectura)

```
git status --short  (antes de tocar nada)
 M frontend/src/components/TicketGraphView.jsx
 M frontend/src/components/TicketGraphView.module.css
 M frontend/src/incidents/devResolverModel.ts
 M frontend/src/pages/SprintBoardPage.tsx
 M frontend/src/pages/TicketBoard.module.css
 M frontend/src/pages/TicketBoard.tsx
 M frontend/src/pages/UnblockerPage.tsx
 M frontend/src/utils/workItemTypeColor.ts
?? frontend/src/utils/__tests__/workItemTypeColor.test.ts

git diff --stat  (base de los archivos disputados)
 TicketBoard.module.css | 28 ++++    TicketBoard.tsx | 16 +++++++++++--

anclas textuales:  {/* Toggle vista */} -> :1018    styles.headerActions -> :999
                   ^const CLOSED_STATES -> :82      IncidentResolverModal -> :21

ratchets base:  uiDebtRatchet 3 passed · copyDebtRatchet 3 passed
                shellIntegration 1 FAILED | 2 passed  (rojo PREEXISTENTE)
```

### D1..D6 — Fases y resultados reales

| Fase | Estado | Comando corrido | Resultado real |
|------|--------|-----------------|----------------|
| F-1 | IMPLEMENTADA | (solo lectura) | anclas ≥1 cada una; ningún comando git de escritura |
| F0 | IMPLEMENTADA | `pytest tests\test_plan238_inbox_flag.py -q` | **5 passed** |
| F1 | IMPLEMENTADA | `pytest tests\test_plan238_incident_inbox_core.py -q` | **13 passed + 1 skipped** (el guard del 216, como contrata el plan) |
| F2 | IMPLEMENTADA | `pytest tests\test_plan238_incident_inbox_api.py -q` | **12 passed** |
| F2 | IMPLEMENTADA | `compileall -q api services` | exit 0 |
| F3 | IMPLEMENTADA | `npx vitest run src/api/__tests__/rawGet.test.ts` | 5 passed |
| F4 | IMPLEMENTADA | `npx vitest run src/incidents/incidentInboxModel.test.ts` | **17 passed** |
| F5 | IMPLEMENTADA | `npx tsc --noEmit` | 0 errores |
| F6 | IMPLEMENTADA | `uiDebtRatchet` / `copyDebtRatchet` / `adhocModalRatchet` | 3 / 3 / 4 passed, **sin regenerar baseline** |
| F7 | IMPLEMENTADA | `shellNav.test.ts` / `shellIconsCoverage.test.ts` / `routes.test.ts` / `routesDeepLink.test.ts` / `commandPaletteData.test.ts` | 9 / 1 / 17 / 6 / 7 passed |
| F8 | IMPLEMENTADA | `git diff --stat -- src/pages/TicketBoard.tsx` | **+2 / −0** sobre la base de F-1 (14→16 inserciones) |
| F9 | IMPLEMENTADA | `pytest tests\test_error_fingerprints_catalog.py` + `_scan.py` | 8 + 9 passed (las 2 huellas registradas) |

**Conteos exigidos:** `harness_flags.py` key = 2 · `config.py` key = 2 · `test_harness_flags.py` key = 1 ·
`api/__init__.py incident_inbox_bp` = 2 · `endpoints.ts incident-inbox` = 2 · `App.tsx IncidentInboxPage` = 2 ·
`getattr(config,` en `api/incident_inbox.py` = 0 · `style={{` en los 2 `.tsx` nuevos = 0 · hex en el
`.module.css` nuevo = 0 · `navigator.clipboard` = 0 · `export const navigateToRoute` = 0 ·
`harness_ratchet_allowlist.txt` sin cambios.

**Rojos preexistentes declarados (NO causados por este plan):**
- `shellIntegration.test.ts`: **1 failed | 2 passed**, idéntico a F-1. El test busca la cadena literal
  `<nav className={styles.nav}>` y el markup real trae `data-tour="nav"`, así que el `indexOf` falla y vuelca
  el archivo entero. Fuera de alcance (§7.7).
- `test_harness_flags_help.py`: 3 tests rojos por deuda ajena (44 flags sin ayuda llana, jerga, un
  `off_effect` sin `"Si "`). **`STACKY_INCIDENT_INBOX_ENABLED` no aparece en ninguna lista de faltantes.**

### Desvíos respecto del plan (declarados)

1. **El gate del tab NO usa `useQuery`.** §F7-e mandaba un `useQuery` en `App.tsx`, pero `App.tsx` **no usa
   react-query en absoluto** (0 ocurrencias): su mecanismo canónico de gates es
   `probeFlagHealth` + `nextEnabledState` (`utils/flagHealth.ts`), que es sticky ante respuestas desconocidas
   y reintenta. Se usó ese patrón. Como `probeFlagHealth` **solo** entiende la clave `flag_enabled`, se
   agregó `flag_enabled` como **alias ADITIVO** en `GET /api/incident-inbox/status` (la clave `enabled` del
   contrato §4.2 sigue intacta y es la que consumen la página y el botón). Sin ese alias el tab quedaba
   invisible para siempre.
2. **La paleta de comandos sí necesitaba filtro.** §F7-f dejaba la rama abierta: verificado que
   `CommandPalette.tsx` renderiza `NAV_COMMANDS` **sin** filtrar por flag, así que P9 exigía filtrar. Se
   agregó la prop opcional `incidentInboxEnabled` (mismo patrón que `deepSearchEnabled`, ya existente) y el
   filtro de la entrada `nav-incidencias`. Consecuencia no enumerada por el plan:
   `commandPaletteData.test.ts` congelaba `NAV_COMMANDS.length === 13`; se actualizó a 14.
3. **La siembra de los tests de F2 no podía usar `project="TEST"`.** El helper `_ticket_project_filter`
   filtra por `stacky_project_name IS NULL AND project == ctx.tracker_project`, así que las filas sembradas
   con `"TEST"` quedaban **fuera** de la consulta y 4 tests daban falso rojo. La siembra resuelve el
   `tracker_project` del contexto activo. Rango `ado_id` 9200..9299 y `try/finally` respetados.
4. **La docstring literal de `incident_inbox.py` chocaba con su propio gate de pureza.** El plan escribía
   "Sin Flask, sin SQLAlchemy, sin I/O" y su criterio 2 de F1 hace `Select-String ... "sqlalchemy"` esperando
   0 líneas. Reescrita a "Sin web, sin ORM, sin I/O" (mismo sentido, gate honesto en 0).
5. **Las huellas usan el esquema real de `error_fingerprints.json`** (`title`/`class`/`status`/`log_pattern`/
   `log_guarded`/`self_test` con muestras `matches`/`clean` coherentes), no el shape del plan, que habría
   puesto rojo `test_error_fingerprints_catalog.py`.
6. **`.badge` sustituye los hex de `.navBadge`** por `var(--danger)` / `var(--bg-base)`: el theme no tiene un
   token de "texto sobre color de estado". Queda constancia, como pide §F8-b.

### Pendiente

- **Smoke de 7 pasos (§F9): PARCIALMENTE EJECUTADO 2026-07-25** — la mitad de API está verificada contra
  una instancia real; falta la confirmación visual.

  Se levantó una instancia **aislada** (`PORT=5099`, `STACKY_TEST_MODE=1` sin egress, `STACKY_DATA_DIR` a
  un temporal) en vez de reiniciar el backend del operador (5050), que corre código previo a este plan:
  reiniciarlo dispara `_startup_sync` (egress a ADO + purga) y es decisión del operador. Vite quedó en
  5199 con un config **fuera del repo**, proxyando `/api` a 5099. Cero archivos del repo tocados.

  | Paso del DoD | Resultado real |
  |---|---|
  | `GET /status` → 200 con `enabled` (contrato §4.2) | 200, `enabled: true` |
  | Alias aditivo `flag_enabled` (desvío 1, lo exige `probeFlagHealth`) | `flag_enabled: true` — presente |
  | Flag default **ON** de fábrica (cero trabajo al operador) | `enabled: true` sin setear nada |
  | `GET /items` → 200 con `items` / `counts` / `untyped_count` | 200; `counts={open:0,closed:0,total:0}`, `untyped_count=0` (DB temporal vacía) |
  | **D9** — con la flag OFF, `GET /items` → 404 `feature_disabled` | **404 `feature_disabled`** |
  | Con la flag OFF, `GET /status` sigue **200** con `enabled:false` | 200, `enabled:false` — correcto: es el endpoint que `probeFlagHealth` sondea; si diera 404 el gate quedaría en "desconocido" y el tab no podría apagarse nunca |

  **Compilación real de la UI (más fuerte que `tsc`):** `IncidentInboxPage.tsx`,
  `IncidentInboxEntryButton.tsx`, `incidentInboxModel.ts` y `App.tsx` se pidieron a través del pipeline de
  transformación de Vite y volvieron **200 sin un solo error**. `TicketBoard.tsx` también compila con la
  línea de F8 **más** las 14 inserciones ajenas sin commitear, sin conflicto.

- **Pendiente: la confirmación VISUAL** (paso 6 — ver desaparecer las 4 superficies con la flag OFF, y el
  render de la página). La extensión de Chrome no está conectada y el repo no tiene Playwright ni
  jsdom/RTL, así que no es automatizable desde acá. Queda listo en **http://localhost:5199/**.
  El paso 7 (proyecto GitLab real) sigue cubierto por `test_gitlab_sin_tipo_reporta_untyped_count`.
- ~~**La edición de `TicketBoard.tsx` (F8) quedó SIN COMMITEAR**~~ → **CERRADO 2026-07-25, commit
  `9249a504`.** Se commitearon **solo las 2 líneas del plan** sin llevarse el trabajo ajeno: el blob se
  construyó desde `HEAD` y se stageó con `git update-index --cacheinfo`, nunca desde el árbol de trabajo.
  Evidencia: el blob del árbol es `d578331d` **antes y después** del commit (intacto), `git diff --cached`
  dio exactamente **+2/−0** con 1 solo archivo staged, y lo que sigue sin commitear en ese archivo son las
  **14 inserciones ajenas** de la sesión paralela — el mismo número que la foto base de F-1.
  Nota de método: `git commit -- <ruta>` habría commiteado el **árbol de trabajo** (llevándose lo ajeno);
  por eso se commiteó el **índice** sin pathspec, con el índice previamente verificado vacío.
