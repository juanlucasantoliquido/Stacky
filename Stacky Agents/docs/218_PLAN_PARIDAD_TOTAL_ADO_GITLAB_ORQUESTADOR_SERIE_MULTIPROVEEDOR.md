# Plan 218 — Paridad total Azure DevOps ↔ GitLab: plan ORQUESTADOR de la serie multi-proveedor

**Estado:** v1 — PROPUESTO (pasar por `criticar-y-mejorar-plan` antes de implementar)
**Autor:** generado con Claude Code (Opus 5) a pedido del operador (Juan Luca Santoliquido), 2026-07-25
**Tipo:** plan orquestador (hoja de ruta ejecutable) — define el sustrato técnico + los 18 subplanes 219..236
**Precedentes directos:** 65, 70, 71, 72, 73, 74, 75, 95 (serie GitLab) · 184, 195, 197 (planes hoja-de-ruta previos, cuyo formato se reusa) · 217 (migrador Mantis→GitLab, adyacente)

---

## 0. Resumen ejecutivo

Se pide un plan maestro que orqueste todos los planes necesarios para que **el 100 % de las funcionalidades de Stacky Agents funcionen igual con GitLab que con Azure DevOps**.

La conclusión del relevamiento (§2, todo con `archivo:línea` y verificación por ejecución) es contraintuitiva y cambia la forma del plan:

> **El problema NO es que falte abstracción. Hay 7 puertos formales y 2 adaptadores casi completos.
> El problema es que el camino GitLab NUNCA SE EJECUTA: está roto en producción por 4 defectos vivos,
> y la suite de tests está verde porque mockea exactamente los seams que debería ejercitar.**

Evidencia dura, **reproducida por ejecución en esta sesión** (§2.1): con `STACKY_GITLAB_ENABLED=true` en el entorno, `get_tracker_provider()` **igual levanta `TrackerConfigError: "…pero STACKY_GITLAB_ENABLED=false"`**, porque `tracker_provider.py:111` lee la flag del **módulo** `config` (que no la tiene) en lugar de la **instancia** `config.config`. Es decir: **hoy es imposible usar GitLab como tracker por la fábrica oficial**, y todo lo construido en los planes 65/70/71/72/73/75/95 para GitLab es código muerto en producción.

Por eso este plan hace dos cosas, en este orden:

1. **F0..F8 — construye el sustrato y lo prueba de verdad** (fases implementables ya, baratas, de altísimo apalancamiento): arregla los 4 defectos probados, congela un censo ejecutable del acoplamiento, crea el **registro de capacidades + matriz de paridad generada**, la **suite de contrato conductual cross-proveedor** (con transporte falso, no con mocks del provider), el **destino por proyecto**, el **vocabulario canónico con alias**, la **degradación declarada** y el **rollout/rollback por capacidad**.
2. **§5 — orquesta los 18 subplanes 219..236**, cada uno con objetivo, archivos que posee (mapa de colisiones), dependencias, prioridad, hito, criterios de aceptación y entregable.

**Este documento NO implementa código.** F0..F8 son fases que otro plan-implementador ejecuta; §5 es el catálogo que genera los subplanes.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Llevar Stacky Agents de "ADO nativo + GitLab en el papel" a "**dos proveedores de primer nivel, verificados por contrato**", sin duplicar lógica: un único núcleo de dominio, N adaptadores, una matriz de capacidades machine-readable que declara qué soporta cada proveedor, y una suite de contrato que corre **el mismo cuerpo de test contra los dos adaptadores** de modo que la paridad deje de ser una promesa de documento y pase a ser un gate de CI. El diseño queda abierto a un tercer proveedor (GitHub, Bitbucket) sin tocar el núcleo.

**KPI / impacto esperado (medibles, con línea base verificada hoy):**

| # | KPI | Línea base (medida 2026-07-25) | Meta al cierre de la serie | Cómo se mide |
|---|---|---|---|---|
| K1 | Proyecto GitLab operable de punta a punta (crear proyecto → sync → lanzar agente → publicar) | **0 %** (la fábrica levanta excepción; §2.1) | 100 % | `test_plan218_gitlab_reachable.py` + smoke del subplan 233 |
| K2 | Módulos no-test que importan `services.ado_*` directo | **36 archivos / 64 ocurrencias** | ≤ 6 (los 5 adaptadores + `project_context`) | `provider_coupling_audit.scan_backend_coupling()` |
| K3 | Líneas con `_ado_client_for_ticket(` en `api/tickets.py` | **20** (24 menciones totales del símbolo; frente a 25 de `_provider_for_ticket`) | 1 (solo la línea de la definición) | `grep -c "_ado_client_for_ticket(" "Stacky Agents/backend/api/tickets.py"` |
| K4 | Literales `"azure_devops"` en backend no-test | **85 en 33 archivos** | ≤ 20 (adaptadores + factories + defaults) | censo F1 |
| K5 | Capacidades del puerto verificadas por contrato conductual en AMBOS proveedores | **0** (la "conformance" actual solo hace `hasattr`/`callable`; §2.3) | ≥ 40 capacidades | `test_plan218_tracker_contract.py` |
| K6 | Dominios funcionales sin puerto formal | **10** (sync, publicación, contexto, outbox, identidad, edit-learning, read-cache, feedback, definiciones CI, PM/sprints) | 0 | matriz §6 |
| K7 | Defectos vivos del camino GitLab | **4 probados** (§2.1) | 0 | F0 |
| K8 | Tests que mockean el seam que deberían ejercitar | **3 identificados** (`test_tracker_factory.py:44-47`, `test_gitlab_provider.py:16`, `test_plan94_variables_providers.py:20`) | 0 | F0 + F3 |

---

## 2. Por qué ahora / gap que cierra (evidencia real)

### 2.1 Los 4 defectos que hacen que GitLab NO EXISTA hoy (probados por ejecución)

| # | Defecto | Evidencia | Consecuencia |
|---|---|---|---|
| **D1** | `tracker_provider.py:111` hace `getattr(config, "STACKY_GITLAB_ENABLED", False)` sobre el **módulo** (importado en `:102`), pero la flag vive en `class Config` (`config.py:1170`) y la instancia se crea recién en `config.py:1631` (`config = Config()`). | **Ejecutado en esta sesión:** `hasattr(config,'STACKY_GITLAB_ENABLED')` → `False`; con `STACKY_GITLAB_ENABLED=true` en el entorno, `config.config.STACKY_GITLAB_ENABLED` → `True` pero `get_tracker_provider('DEMO')` → `TrackerConfigError: "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"`. | **GitLab es inalcanzable por la fábrica oficial, siempre.** Es la memoria `gotcha-config-config-vs-modulo-tickets` materializada en el seam más caro del repo. Las fábricas hermanas lo hacen bien: `ci_provider.py:121`, `ci_logs_provider.py:38`, `ci_variables.py:82` usan `_config.config`. |
| **D2** | `gitlab_provider.py:34,35,38,39` leen `GITLAB_URL`, `GITLAB_PROJECT`, `STACKY_GITLAB_GROUP`, `STACKY_GITLAB_EPICS_NATIVE` del **módulo** `config`. Verificado: `hasattr(config,'GITLAB_URL')` → `False`. En el mismo archivo, `:174,184,194,205` sí usan `config.config`. | Ejecución de esta sesión. | `self._group` y `self._epics_native` quedan **permanentemente** `""`/`False`: épicas nativas y `epic_url` (`gitlab_provider.py:199-209`) están muertas. `GITLAB_URL`/`GITLAB_PROJECT` sobreviven solo porque `gitlab_client.py:56,59` cae a `os.getenv`. |
| **D3** | `GitLabTrackerProvider.__init__` tiene firma `(self, project=None)` (`gitlab_provider.py:33`), pero se construye con el kwarg inexistente `project_name=` en `gitlab_ci_provider.py:30` y `gitlab_variables.py:13`. | Verificado con `inspect.signature` en esta sesión. | **`TypeError` en construcción**: el proveedor CI de GitLab y el de variables de GitLab están muertos al instante. |
| **D4** | `gitlab_variables.py:28` llama `_request_paginated("GET", path)` (2 posicionales) contra `(self, path, *, params, page_cap)`; `:80,:90` pasan `json=` contra el kwarg real `json_body=`. | Verificado con `inspect.signature` en esta sesión. | `list_variables` y `set_variable` de GitLab levantan `TypeError`. |

**Por qué la suite está verde:** `tests/test_tracker_factory.py:44-47` parchea el **módulo `config` entero** con un `MagicMock` (así D1 nunca se ve); `tests/test_gitlab_provider.py:16` parchea `services.gitlab_provider.config` (así D2 nunca se ve); `tests/test_plan94_variables_providers.py:20` mockea `GitLabTrackerProvider` completo (así D3 y D4 nunca se ven). Es exactamente el antipatrón que ya combatieron el Plan 154 ("arnés veraz") y el Plan 210 ("fin del falso Build OK") — pero aplicado al eje multi-proveedor.

### 2.2 Los 3 bloqueos estructurales (además de los defectos)

| # | Bloqueo | Evidencia | Efecto |
|---|---|---|---|
| **B1 — Destino GitLab es un singleton global, no por proyecto** | `ProjectContext` (`project_context.py:45-53`) no tiene campo `base_url`. `_auth_path_for` (`:88-103`) tiene rama `jira` (`:95`) y `mantis` (`:97`) pero **no `gitlab`**: un proyecto GitLab cae en el `else` y apunta a `auth/ado_auth.json` (`:99`). Y `tracker_provider.py:116` pasa `project=project` — el **nombre Stacky** (`"RSPACIFICO"`) — a un constructor que lo interpreta como **path de proyecto GitLab** (`gitlab_provider.py:35`); ADO lo hace bien (`ado_provider.py:34` → `build_ado_client(project_name=…)`). | Lectura directa. | Todos los proyectos comparten una única URL/token de GitLab. No hay forma de tener dos proyectos GitLab, ni un GitLab y un ADO bien resueltos. |
| **B2 — El flujo más básico (sync de ítems) no existe para GitLab** | `api/tickets.py:677-695`: `_sync_via_provider_or_ado` levanta `NotImplementedError(f"Sync para tracker '{provider.name}' aun no implementado…")` para cualquier provider ≠ `azure_devops`. Consumido en `:706` y `:5779`. No existe `gitlab_sync.py`. | Lectura directa. | Un proyecto GitLab **nunca puebla el tablero de tickets**. Todo lo demás es irrelevante si esto no anda. |
| **B3 — No se puede ni dar de alta un proyecto GitLab desde la UI** | `frontend/src/components/NewProjectModal.tsx` tiene 3 botones de tracker: `azure_devops` (`:376`), `jira` (`:382`), `mantis` (`:389`) — **cero ocurrencias de `gitlab`** en el archivo. Solo `EditProjectModal.tsx:697-750` tiene panel GitLab. `project_manager.py` tiene `initialize_*` para ADO (`:270`), Jira (`:317`) y Mantis (`:560`), **no para GitLab**. `GET /api/projects/{n}/credentials` no devuelve `gitlab_user`. | Lectura directa. | GitLab es ciudadano de segunda: no hay onboarding. |

### 2.3 Lo que SÍ existe y hay que reusar (no reinventar)

| Pieza | Ubicación | Estado real |
|---|---|---|
| Puerto `TrackerProvider` + `PORT_METHODS` (18 métodos) | `services/tracker_provider.py:56-98` | Existe. GitLab implementa los 18 (`gitlab_provider.py:138-411`), ninguno levanta `NotImplementedError`. |
| Puerto `CIProvider` (3 métodos, congelado) | `services/ci_provider.py:83-100`, fábrica `:107` | Existe, 2 adaptadores. |
| Puerto `CILogsProvider` (2 métodos) | `services/ci_logs_provider.py:7-25` | Existe, 2 adaptadores, paridad real. |
| Puerto `MergeRequestProvider` (7 métodos) | `services/merge_request_provider.py:7-90` | Existe. ADO parcial **por diseño**: `get_merge_request_diff` devuelve `diff_available=False` (`ado_provider.py:455-457`); `approve_merge_request` solo GitLab (`gitlab_provider.py:777`), detectado por `hasattr` (`api/pr_review.py:368,409`). |
| Puerto `RepoWriter` (1 método) | `services/repo_writer.py:13-42` | Existe, 2 adaptadores. |
| Puertos `CIPreflightProvider` / `CIVariablesProvider` | `services/ci_preflight.py:9-40`, `services/ci_variables.py:45-89` | Existen. Variables roto en ambos lados (GitLab D3/D4; ADO `ado_variables.py:14` liga `AdoClient._request` sin bind). |
| **Patrón canónico de normalización sin duplicar lógica** | `services/pipeline_spec.py` + `services/pipeline_renderers.py` (`to_ado_yaml:23`, `to_gitlab_yaml:126`, `parse_ado_yaml:194`, `parse_gitlab_yaml:251`, `_ADO_TO_GITLAB_CONDITION_MAP:90`, pérdidas declaradas en `:140`) | **Es el modelo a generalizar**: spec neutral + renderers puros por dialecto + pérdidas explícitas. |
| Centinela de acoplamiento (alcance `api/*.py`) | `tests/test_plan70_no_typed_adoclient_in_api.py:49,72,102` | Existe. F1 lo **generaliza** a todo el backend, no lo reemplaza. |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh:20` + `tests/test_harness_ratchet_meta.py:43` | Existe. Todo test nuevo se registra ahí. |
| Breaker de degradación | `services/integration_breaker.py` (Plan 148) | Existe. F6 lo reusa, no crea otro. |
| Deep links GitLab puros | `services/gitlab_deep_links.py` (11 funciones puras) | Existe y es mejor que el lado ADO (que no tiene módulo equivalente). |

### 2.4 Divergencia documento ↔ código (a resolver en F7)

Los planes 65, 70, 71, 72 y 73 dicen **"PROPUESTO"** en su encabezado, pero su código **existe** (`tracker_provider.py`, `_provider_for_ticket` ×25 en `api/tickets.py`, `ci_provider.py`, `trigger_pipeline` en ambos adaptadores, `pipeline_spec.py`). No figuran en `docs/_supervision/ledger.json` (solo 74 y 75, ambos `TERMINADO-POR-SUPERVISOR` 2026-07-02). Los propios planes se contradicen: el 73 afirma "Plan 65 — IMPLEMENTADO"; el 74 afirma "Plan 70 — COMPLETO"; el 71 afirma "Plan 70 … NO implementado".

**Implicancia dura:** planificar sobre los encabezados de esos documentos produce trabajo duplicado. F7 congela el estado real medido contra el código, no contra la prosa.

---

## 3. Principios y guardarraíles (no negociables)

- **P1 — Un solo núcleo, N adaptadores.** Prohibido `if tracker_type == "gitlab": … else: …` fuera de un adaptador o de una fábrica. La lógica de dominio vive una sola vez.
- **P2 — Doctrina de normalización en 3 capas** (§3.1). Todo dominio nuevo la respeta.
- **P3 — Paridad probada, no declarada.** Ninguna capacidad se marca `full` en la matriz sin un test de contrato conductual verde **en los dos proveedores**. Un `hasattr` no es paridad.
- **P4 — Prohibido mockear el seam bajo prueba.** Los tests de contrato mockean **el transporte HTTP**, nunca el provider ni el módulo `config`. Un test que parchea `services.gitlab_provider.config` o `GitLabTrackerProvider` entero es un test inválido para paridad.
- **P5 — Leer flags SIEMPRE de la instancia** `config.config` (memoria `gotcha-config-config-vs-modulo-tickets`). D1/D2 son exactamente esta regla violada. F0 agrega un centinela que lo impide para siempre.
- **P6 — Backward-compatible o no va.** Ningún renombre destructivo. El vocabulario canónico se agrega **como alias aditivo** (`ado_id` sigue existiendo y funcionando); las 495 ocurrencias de campos `ado_*` en 88 archivos del frontend no se tocan en esta serie.
- **P7 — Cero trabajo extra para el operador.** Todo lo de este plan es invisible o automático. Las flags nuevas nacen **default ON** salvo las que caen en una de las 4 excepciones duras, y en ese caso se cita cuál. La única flag que queda **OFF** es `STACKY_GITLAB_ENABLED` (ya existente): aplica la **excepción 3 — prerequisito no garantizado en instalación default** (requiere una instancia GitLab alcanzable + un token válido, que no existen en una instalación limpia). Encenderla es un click en el panel de flags, no una tarea nueva.
- **P8 — Human-in-the-loop innegociable.** Nada de este plan crea autonomía proactiva. Toda escritura al tracker sigue pasando por el gate humano existente. La única excepción aceptada del producto sigue siendo épica-desde-brief, y este plan **no la amplía**.
- **P9 — Mono-operador, sin auth real.** No se propone RBAC ni multiusuario. Cuando §5 habla de "permisos", significa **preflight de scopes del token propio** (¿este PAT puede escribir acá?), nunca control de acceso dentro de Stacky.
- **P10 — Paridad de 3 runtimes.** Codex CLI, Claude Code CLI y GitHub Copilot Pro consumen el tracker por la **misma** ruta (`get_tracker_provider`, `agent_bootstrap`, inyección de contexto). Ningún ítem de este plan introduce una ruta específica de runtime. Los runners que ya tocan el puerto lo hacen de forma idéntica: `claude_code_cli_runner.py:142-152` y `codex_cli_runner.py:121-125`; el bridge de Copilot (`copilot_bridge.py`) **no toca el tracker** (cero ocurrencias de `get_tracker_provider`/`tracker_type`), por lo que hereda el comportamiento del backend sin cambios.
- **P11 — No degradar.** Con la flag maestra en OFF, el comportamiento es **byte-idéntico** al actual. Sin llamadas de red nuevas en el arranque. Sin tokens en logs.

### 3.1 Doctrina de normalización en 3 capas (cómo se abstrae sin duplicar)

Toda capacidad multi-proveedor de Stacky se implementa exactamente así — no hay una cuarta forma:

```
Capa 1 — PUERTO (Protocol + tupla de métodos congelada)
   Qué: contrato de COMPORTAMIENTO. Vive en services/<dominio>_provider.py.
   Ejemplo vivo: tracker_provider.TrackerProvider + PORT_METHODS (tracker_provider.py:56-98)
   Regla: el puerto nunca menciona un proveedor. Ni "wiql", ni "iid", ni "System.*".

Capa 2 — MODELO CANÓNICO (dataclasses puras, sin I/O)
   Qué: la FORMA de los datos, independiente del proveedor.
   Ejemplos vivos: TrackerItem/TrackerQuery (tracker_provider.py:21-39),
                   PipelineSpec (pipeline_spec.py) + renderers puros (pipeline_renderers.py:23,126)
   Regla: si un campo solo existe en un proveedor, va en `fields: dict`, no en el modelo.

Capa 3 — REGISTRO DE CAPACIDADES + DEGRADACIÓN DECLARADA   ← LO QUE FALTA, lo crea este plan
   Qué: tabla machine-readable de qué soporta cada proveedor, con estado
        full | partial | absent | n/a, y la pérdida declarada cuando es `partial`.
   Regla de oro: una capacidad `absent` NUNCA se descubre por excepción en runtime.
        Se consulta ANTES (supports()) y se degrada con CapabilityUnavailable,
        que la UI sabe renderizar (patrón Plan 148 + Plan 135 "cero errores mudos").
```

**Contratos que este plan CONGELA** (ningún subplan 219..236 los cambia sin renegociar aquí):

| Contrato | Dueño | Congelado en |
|---|---|---|
| `CAPABILITY_KEYS` (tupla de claves de capacidad) | 218 F2 | `backend/services/provider_capabilities.py` |
| Estados de capacidad: `"full" \| "partial" \| "absent" \| "n/a"` | 218 F2 | idem |
| `CapabilityUnavailable(TrackerError)` y su payload HTTP | 218 F6 | `backend/services/tracker_provider.py` |
| `TrackerTarget` (dataclass de destino resuelto por proyecto) | 218 F4 | `backend/services/project_context.py` |
| `CANONICAL_FIELDS` y el mapa de alias legacy | 218 F5 | `backend/services/tracker_vocabulary.py` |
| Firma de la suite de contrato `run_tracker_contract(make_provider, capabilities)` | 218 F3 | `backend/tests/contract/provider_contract.py` |

---

## 4. Fases

> **Comando backend** (desde la raíz del repo, PowerShell): `& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>" -q` — **SIEMPRE por archivo**, nunca la suite completa (contaminación cross-run conocida; memorias `gotcha-config-reload-harness-flags-contamina` y `gotcha-vitest-test-order-pollution-frontend`). Variante equivalente usada por los planes 210/212/213/215/216: `cd "Stacky Agents/backend"` y luego `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q`.
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run <archivo>` + `npx tsc --noEmit`.
> **Registro obligatorio:** todo `backend/tests/test_*.py` nuevo se agrega como línea `  tests/<archivo>.py` (dos espacios de indentación, sin comentario en la misma línea) dentro de `HARNESS_TEST_FILES=(` en `backend/scripts/run_harness_tests.sh:20` **y** en `$HarnessTestFiles = @(` de `backend/scripts/run_harness_tests.ps1:13`, o `tests/test_harness_ratchet_meta.py:43` queda rojo.
> **Receta de flag default ON = 5 lugares:** (1) `FlagSpec(...)` en `services/harness_flags.py:379`; (2) la clave en la tupla correspondiente de `_CATEGORY_KEYS` (`harness_flags.py:117`); (3) la clave en `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`); (4) el atributo en `class Config` (`config.py`); (5) el read-site, **siempre** `config.config.<FLAG>`.

---

### F0 — Prueba de vida: que GitLab exista de verdad

**Objetivo (1 frase):** eliminar los 4 defectos que hacen que el camino GitLab sea inalcanzable, y dejar tests que **no se puedan falsear mockeando el módulo `config`**.

**Valor:** desbloquea absolutamente todo lo demás. Sin F0, los 18 subplanes construyen sobre código que nunca corre.

**Archivos a editar (exactos):**

1. `backend/services/tracker_provider.py` — línea 111.
```diff
-    if ttype == "gitlab":
-        if not getattr(config, "STACKY_GITLAB_ENABLED", False):
+    if ttype == "gitlab":
+        # P5 / D1: la flag vive en la INSTANCIA (config.py:1631 `config = Config()`),
+        # no en el módulo. Mismo patrón que ci_provider.py:121.
+        if not bool(getattr(config.config, "STACKY_GITLAB_ENABLED", False)):
             raise TrackerConfigError(
                 "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"
             )
```

2. `backend/services/gitlab_provider.py` — líneas 34, 35, 38, 39.
```diff
     def __init__(self, project: Optional[str] = None):
-        base_url = getattr(config, "GITLAB_URL", "") or ""
-        proj = project or getattr(config, "GITLAB_PROJECT", "") or ""
+        base_url = getattr(config.config, "GITLAB_URL", "") or ""
+        proj = project or getattr(config.config, "GITLAB_PROJECT", "") or ""
         self._client = GitLabClient(base_url=base_url, project=proj)
         self._project = proj
-        self._group = getattr(config, "STACKY_GITLAB_GROUP", "") or ""
-        self._epics_native = getattr(config, "STACKY_GITLAB_EPICS_NATIVE", False)
+        self._group = getattr(config.config, "STACKY_GITLAB_GROUP", "") or ""
+        self._epics_native = bool(getattr(config.config, "STACKY_GITLAB_EPICS_NATIVE", False))
```

3. `backend/services/gitlab_ci_provider.py` — línea 30: `GitLabTrackerProvider(project_name=project)` → `GitLabTrackerProvider(project=project)`.
4. `backend/services/gitlab_variables.py` — línea 13: idéntico cambio de kwarg.
5. `backend/services/gitlab_variables.py` — línea 28: `self._client._request_paginated("GET", f"/projects/{...}/variables")` → `self._client._request_paginated(f"/projects/{...}/variables")` (el método no acepta `method`; es GET por definición, `gitlab_client.py:177`).
6. `backend/services/gitlab_variables.py` — líneas 80 y 90: `json=body` → `json_body=body`.
7. `backend/services/ci_preflight.py` — línea 35: agregar el gate `STACKY_GITLAB_ENABLED` leído de `config.config`, para que las 6 fábricas seleccionen de forma idéntica (hoy es la única sin gate).

**Tests PRIMERO — `backend/tests/test_plan218_gitlab_reachable.py`:**
- `test_config_module_no_expone_flags_de_instancia` — afirma `not hasattr(config, "STACKY_GITLAB_ENABLED")` y `hasattr(config.config, "STACKY_GITLAB_ENABLED")`. Documenta la causa raíz; **no** parchea nada.
- `test_factory_devuelve_gitlab_con_flag_on` — `monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", True)` (instancia, nunca el módulo), stub de `resolve_project_context` que devuelve `tracker_type="gitlab"`, y afirma `get_tracker_provider("DEMO").name == "gitlab"`. **Con el código actual este test es ROJO.**
- `test_factory_rechaza_gitlab_con_flag_off` — con la flag en `False`, sigue levantando `TrackerConfigError` (kill-switch intacto).
- `test_gitlab_provider_lee_group_y_epics_de_instancia` — con `config.config.STACKY_GITLAB_GROUP="g1"` afirma `provider._group == "g1"`.
- `test_gitlab_ci_provider_construye` — construye `GitLabCIProvider(project="grupo/proyecto")` sin `TypeError`.
- `test_gitlab_variables_provider_construye` — idem `GitLabVariablesProvider`.
- `test_gitlab_variables_list_usa_firma_real` — con un doble de `GitLabClient` que **valida la firma real** (`_request_paginated(path, *, params, page_cap)`), `list_variables()` no levanta `TypeError`.
- `test_gitlab_variables_set_usa_json_body` — el doble afirma que se recibió `json_body=` y no `json=`.
- `test_centinela_no_getattr_sobre_modulo_config` — **centinela AST/regex sobre todo `backend/services/*.py` y `backend/api/*.py`**: cero coincidencias de `getattr(config,` y de `getattr(_config,` (debe ser `getattr(config.config,` o `getattr(_config.config,`), con una allowlist literal vacía. Este control es el que impide que D1/D2 vuelvan.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_gitlab_reachable.py" -q`

**Criterio de aceptación (binario):** el comando anterior verde con 9 tests; además, desde `Stacky Agents/backend`, `& ".venv\Scripts\python.exe" -c "import config, services.tracker_provider as tp; print(hasattr(config,'STACKY_GITLAB_ENABLED'))"` imprime `False` (la causa sigue documentada) y `grep -rn "getattr(config, \"STACKY" "Stacky Agents/backend/services" "Stacky Agents/backend/api"` devuelve **0 líneas**.

**Flag:** ninguna flag nueva. El kill-switch es la ya existente `STACKY_GITLAB_ENABLED` (default **OFF**, **excepción dura 3 — prerequisito no garantizado en instalación default**: exige instancia GitLab + token). Gatear una corrección de defecto detrás de una flag nueva conservaría el defecto; el rollback correcto es apagar GitLab entero, que ya es el default.

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — es backend puro por debajo de los tres; ninguno construye providers por su cuenta. Fallback de los tres: con `STACKY_GITLAB_ENABLED=false` (default) el comportamiento es byte-idéntico al de hoy.

**Trabajo del operador: ninguno.**

---

### F1 — Censo ejecutable del acoplamiento + ratchet que impide que crezca

**Objetivo (1 frase):** convertir el acoplamiento a ADO en un **número medido** que solo puede bajar, para que la serie 219..236 no compita contra deuda nueva.

**Valor:** sin esto, cada subplan reduce acoplamiento mientras otro lo aumenta. Es el mecanismo que hace converger 18 planes.

**Archivos a crear:**

1. `backend/services/provider_coupling_audit.py`
```python
"""Censo determinista del acoplamiento a un proveedor concreto. PURO (solo lee archivos)."""
from __future__ import annotations
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]

# Módulos que TIENEN derecho a importar services.ado_* (adaptadores + seam ADO-only)
ADAPTER_ALLOWLIST: frozenset[str] = frozenset({
    "services/tracker_provider.py", "services/ci_provider.py",
    "services/ci_logs_provider.py", "services/ci_preflight.py",
    "services/ci_variables.py", "services/project_context.py",
})

def scan_backend_coupling() -> dict:
    """Devuelve:
    {
      "ado_importers": {"<ruta relativa>": <n ocurrencias>},   # no-test, fuera de services/ado_*
      "ado_importers_count": int,
      "tracker_literals": {"<ruta>": <n>},                     # literal "azure_devops"
      "tracker_literals_count": int,
      "ado_client_sites_in_tickets": int,                      # LÍNEAS con '_ado_client_for_ticket(' en api/tickets.py
      "ado_routes": int,                                       # rutas con 'by-ado'|'publish-to-ado'|'/ado-'
    }
    Excluye: backend/tests/**, backend/.venv/**, backend/venv/**, backend/services/ado_*.py.
    Ordena las claves alfabéticamente (salida determinista)."""

def render_report_markdown(scan: dict) -> str:
    """Tabla Markdown del censo. PURA."""
```

2. `backend/tests/provider_coupling_baseline.json` — línea base congelada, generada por el implementador con el censo real del día. Valores medidos hoy 2026-07-25 (deben coincidir salvo drift del árbol):
```json
{
  "ado_importers_count": 36,
  "tracker_literals_count": 85,
  "ado_client_sites_in_tickets": 20,
  "ado_routes": 19
}
```

**Tests PRIMERO — `backend/tests/test_plan218_coupling_ratchet.py`:**
- `test_scan_es_determinista` — dos llamadas consecutivas devuelven el mismo dict.
- `test_scan_excluye_tests_y_venv` — ninguna clave contiene `tests/`, `.venv/`, `venv/`.
- `test_scan_excluye_familia_ado` — ninguna clave empieza con `services/ado_`.
- `test_ratchet_importers_no_crece` — `scan["ado_importers_count"] <= baseline["ado_importers_count"]`, con mensaje que lista los archivos nuevos.
- `test_ratchet_literales_no_crece` — idem para `tracker_literals_count`.
- `test_ratchet_sitios_adoclient_no_crece` — idem para `ado_client_sites_in_tickets`.
- `test_ratchet_rutas_ado_no_crece` — idem para `ado_routes`.
- `test_allowlist_de_adaptadores_es_exacta` — cada ruta de `ADAPTER_ALLOWLIST` existe en disco (no hay entradas fantasma).
- `test_reporte_markdown_tiene_todas_las_secciones` — `render_report_markdown` incluye las 4 métricas.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_coupling_ratchet.py" -q`

**Criterio de aceptación (binario):** comando verde con 9 tests; y agregar a mano un `from services.ado_client import AdoClient` en cualquier archivo no-allowlisteado hace **rojo** `test_ratchet_importers_no_crece` (verificación manual del implementador, documentada en el commit).

**Flag:** ninguna — es un módulo puro + tests, sin superficie de runtime (no se importa desde `app.py` ni desde ningún blueprint). No hay comportamiento que apagar.

**Impacto por runtime:** N/A — no participa de ninguna ejecución de agente. Los 3 runtimes son indiferentes.

**Trabajo del operador: ninguno.**

---

### F2 — Registro de capacidades y matriz de paridad generada (nunca a mano)

**Objetivo (1 frase):** una única fuente de verdad, machine-readable, de qué capacidad soporta cada proveedor y con qué pérdida, que además **genera** el documento de paridad para que no pueda quedar desactualizado.

**Valor:** es la "matriz de paridad funcional" pedida, pero ejecutable: la consulta el código (para degradar), la consulta la UI (para ocultar acciones imposibles) y la consulta el operador (para saber qué esperar).

**Archivos a crear:**

1. `backend/services/provider_capabilities.py`
```python
"""Registro de capacidades por proveedor. PURO (sin I/O de red, sin DB)."""
from __future__ import annotations

# CONGELADO por el Plan 218 (§3.1). Agregar claves es aditivo; renombrar NO.
CAPABILITY_KEYS: tuple[str, ...] = (
    # tracker
    "tracker.items.list", "tracker.items.get", "tracker.items.create",
    "tracker.items.update_state", "tracker.items.update_assignee", "tracker.items.url",
    "tracker.states.list", "tracker.types.list", "tracker.query.search",
    "tracker.comments.list", "tracker.comments.list_all", "tracker.comments.post",
    "tracker.comments.idempotent",
    "tracker.attachments.list", "tracker.attachments.upload", "tracker.attachments.link",
    "tracker.hierarchy.link_parent", "tracker.hierarchy.find_child",
    "tracker.updates.history", "tracker.sync.full", "tracker.sync.incremental",
    "tracker.epics.list", "tracker.epics.create_native",
    "tracker.iterations.list", "tracker.milestones.list", "tracker.labels.ensure",
    # repo
    "repo.file.read", "repo.file.commit", "repo.branch.list", "repo.branch.create",
    "repo.commit.list", "repo.tag.create",
    # merge request / pull request
    "mr.create", "mr.get", "mr.list", "mr.diff", "mr.comment", "mr.close",
    "mr.merge", "mr.approve", "mr.reviewers", "mr.policies",
    # ci
    "ci.pipeline.infer", "ci.pipeline.trigger", "ci.pipeline.monitor",
    "ci.pipeline.definition.find", "ci.pipeline.definition.ensure",
    "ci.jobs.failed", "ci.job.log", "ci.variables.list", "ci.variables.set",
    "ci.variables.delete", "ci.variables.masked", "ci.artifacts.list",
    "ci.artifacts.download", "ci.environments.list", "ci.approvals",
    # identidad y grupos (SOLO lectura del propio token — P9, nunca RBAC)
    "identity.me", "identity.user.find", "identity.members.list", "identity.groups.list",
    "identity.token.scopes",
    # eventos
    "events.webhook.inbound", "events.webhook.verify",
    # deep links
    "links.item", "links.mr", "links.commit", "links.pipeline", "links.epic",
)

CAPABILITY_STATUSES: tuple[str, ...] = ("full", "partial", "absent", "n/a")

# status + nota de pérdida obligatoria cuando status == "partial"
CAPABILITY_MATRIX: dict[str, dict[str, dict]] = {
    "azure_devops": { "<clave>": {"status": "...", "evidence": "archivo:línea", "loss": "..."} },
    "gitlab":       { ... },
}

def capability_status(provider: str, capability: str) -> str: ...
def supports(provider: str, capability: str) -> bool:
    """True solo si status == 'full' o 'partial'."""
def capability_loss(provider: str, capability: str) -> str:
    """Texto de la pérdida declarada; '' si status == 'full'."""
def render_markdown_matrix() -> str:
    """Documento de paridad completo. PURA y DETERMINISTA (orden = CAPABILITY_KEYS)."""
```

2. `docs/_roadmap/PARIDAD_ADO_GITLAB.md` — **generado** por `render_markdown_matrix()`, nunca editado a mano.

**Valores iniciales verificados** (el implementador los carga tal cual; §6 tiene la tabla completa): `mr.approve` → ADO `absent` (`ado_provider.py:476` no lo define), GitLab `full` (`gitlab_provider.py:777`). `mr.diff` → ADO `partial`, `loss="diff_available=False; el operador abre la PR en el navegador"` (`ado_provider.py:455-457`), GitLab `full` (`gitlab_provider.py:733`). `tracker.sync.full` → ADO `full` (`ado_sync.py:102`), GitLab `absent` (`api/tickets.py:692`). `ci.pipeline.definition.ensure` → ADO `full` (`ado_pipeline_definitions.py:125`), GitLab `n/a` (GitLab no tiene objeto "definition": commitea `.gitlab-ci.yml`, `gitlab_provider.py:590`). `ci.variables.masked` → ADO `absent` (`ado_variables.py:44` lo declara), GitLab `full`. `tracker.epics.create_native` → ADO `full`, GitLab `partial` (requiere licencia Premium; fallback issue-links en `gitlab_provider.py:102-128`).

**Tests PRIMERO — `backend/tests/test_plan218_capability_matrix.py`:**
- `test_toda_clave_declarada_en_ambos_proveedores` — `set(CAPABILITY_MATRIX["azure_devops"]) == set(CAPABILITY_MATRIX["gitlab"]) == set(CAPABILITY_KEYS)`.
- `test_status_pertenece_al_vocabulario` — todo `status` ∈ `CAPABILITY_STATUSES`.
- `test_partial_exige_loss_no_vacio` — si `status == "partial"`, `loss` tiene ≥ 10 caracteres.
- `test_full_y_partial_exigen_evidencia` — si `status` ∈ {`full`,`partial`}, `evidence` matchea `^[\w/\.]+\.py:\d+$`.
- `test_supports_es_consistente` — `supports()` es `True` exactamente para `full`/`partial`.
- `test_render_es_determinista` — dos renders idénticos byte a byte.
- `test_doc_de_paridad_esta_sincronizado` — `docs/_roadmap/PARIDAD_ADO_GITLAB.md` es **exactamente** `render_markdown_matrix()`. **Este test es el que impide que la matriz se pudra.**
- `test_claves_congeladas_no_se_renombran` — hash SHA-256 de `"\n".join(CAPABILITY_KEYS)` igual a la constante congelada `_KEYS_SHA` del propio test (renombrar una clave rompe a propósito).

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q`

**Criterio de aceptación (binario):** comando verde con 8 tests; `docs/_roadmap/PARIDAD_ADO_GITLAB.md` existe y contiene exactamente `len(CAPABILITY_KEYS)` filas de datos (verificable con `grep -c "^| \`" "Stacky Agents/docs/_roadmap/PARIDAD_ADO_GITLAB.md"`).

**Flag:** `STACKY_PROVIDER_PARITY_ENABLED` (bool, default **True**, categoría `integraciones`). Default ON porque es un registro puro leído en proceso: no agrega red, ni prerequisitos, ni reduce seguridad, ni bypasea revisión humana. Con OFF, `supports()` devuelve `True` para todo (comportamiento pre-plan, byte-idéntico).

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — módulo puro consultado por el backend antes de cualquier runtime. Fallback de los tres: flag OFF ⇒ nadie consulta la matriz y todo se comporta como hoy.

**Trabajo del operador: ninguno.**

---

### F3 — Suite de contrato conductual cross-proveedor (con transporte falso, no con mocks del provider)

**Objetivo (1 frase):** correr **el mismo cuerpo de test** contra `AdoTrackerProvider` y `GitLabTrackerProvider` reales, mockeando únicamente el transporte HTTP, para que la paridad sea un gate y no una declaración.

**Valor:** es el mecanismo central de todo el plan. Reemplaza la falsa conformance actual: `tests/test_tracker_provider_conformance.py:81-92` se llama `test_no_port_method_is_a_stub` pero su propio comentario en `:91` dice *"Solo verificamos que el atributo exista y sea callable (no que esté hardcoded NotImplementedError)"* — es decir, **no verifica lo que su nombre promete**.

**Archivos a crear:**

1. `backend/tests/contract/__init__.py` (vacío).
2. `backend/tests/contract/fake_transport.py`
```python
"""Transporte HTTP falso, guiado por fixtures grabados. NO mockea providers ni config."""
class FakeHttp:
    def __init__(self, fixtures_dir: str, provider: str): ...
    def expect(self, method: str, url_substring: str, *, status: int, body: dict | list) -> None: ...
    def calls(self) -> list[dict]:
        """[{'method','url','headers','body'}] — permite asertar la forma real del request."""
def install_for_ado(monkeypatch, fake: FakeHttp) -> None:
    """Parchea SOLO urllib.request.urlopen usado por services/ado_client.py:271,537."""
def install_for_gitlab(monkeypatch, fake: FakeHttp) -> None:
    """Parchea SOLO requests.request usado por services/gitlab_client.py:135."""
```
3. `backend/tests/contract/provider_contract.py`
```python
def run_tracker_contract(make_provider, provider_name: str, fake: FakeHttp) -> list[str]:
    """Ejecuta el contrato conductual del puerto contra un provider REAL.
    Devuelve la lista de capacidades verificadas (claves de CAPABILITY_KEYS).
    Para cada capacidad con status 'full' o 'partial' en la matriz, ejecuta su
    escenario; si la matriz dice 'absent'/'n/a', afirma que se levanta
    CapabilityUnavailable (F6) y NO un error genérico."""
```
4. `backend/tests/fixtures/provider_contract/azure_devops/*.json` y `backend/tests/fixtures/provider_contract/gitlab/*.json` — respuestas grabadas, **anonimizadas** (sin emails, sin tokens, sin nombres reales).

**Escenarios conductuales mínimos del contrato (idénticos para los dos proveedores):**

| Escenario | Aserción neutral (no menciona proveedor) |
|---|---|
| `create_item` con `TrackerItem(item_type="task", title=..., description_html=...)` | Devuelve dict con `id` (str), `url` (str no vacío); el request llevó el título tal cual. |
| `get_item(id)` sobre ítem inexistente | Levanta `TrackerApiError` con `kind == "not_found"` (no `Exception` pelada). |
| `post_comment` + `comment_exists(marker)` | Tras postear con marcador, `comment_exists` devuelve verdadero; **sin** el marcador, falso. |
| `fetch_all_comments` con 120 comentarios paginados | Devuelve los 120 (ADO por `continuationToken`, `ado_client.py:831`; GitLab por `X-Next-Page`, `gitlab_client.py:206`). **Hoy GitLab falla**: `fetch_all_comments` (`gitlab_provider.py:291`) es idéntico a `fetch_comments` y no acepta `marker`. |
| `update_item_state("done")` | El request contiene el estado del proveedor resuelto desde el perfil, no un literal hardcodeado. |
| `update_item_assignee("usuario-inexistente")` | Levanta error tipado. **Hoy GitLab lo silencia y BORRA el asignado** (`gitlab_provider.py:368-369`) — el contrato lo hace visible. |
| `item_url(id)` | Devuelve `str` no vacío **siempre**. **Hoy GitLab devuelve `None`** con la flag de deep links apagada (`gitlab_provider.py:174`), violando la firma del puerto (`tracker_provider.py:63`). |
| `fetch_states()` | Devuelve estados reales del tracker. **Hoy GitLab devuelve 4 claves lógicas hardcodeadas** (`gitlab_provider.py:82-90,212`). |
| `find_child_by_marker(parent, marker)` | Devuelve el **hijo**. **Hoy GitLab devuelve el padre como proxy** (`gitlab_provider.py:403`). |
| Rate limit 429 con `Retry-After: 2` | Reintenta y devuelve 200. Con `Retry-After: 99999`, **no** bloquea el hilo (ADO lo clampea a 30 s en `ado_client.py:49`; **GitLab hoy no clampea**, `gitlab_client.py:146-147`). |
| Respuesta no-JSON (HTML de login) | Ambos levantan error tipado de auth. **Hoy divergen**: ADO detecta el redirect HTML (`ado_client.py:88,277-285`), GitLab devuelve texto crudo (`gitlab_client.py:164-175`). |

**Tests PRIMERO — `backend/tests/test_plan218_tracker_contract.py`:**
- `@pytest.mark.parametrize("provider_name", ["azure_devops", "gitlab"])` sobre `test_contrato_del_puerto_tracker` — corre `run_tracker_contract` y afirma que devolvió ≥ 1 capacidad verificada.
- `test_contrato_cubre_toda_capacidad_full_o_partial` — para cada proveedor, el conjunto de capacidades ejercitadas ⊇ las marcadas `full`/`partial` en `CAPABILITY_MATRIX`. **Este test hace imposible marcar `full` sin probarlo.**
- `test_ningun_test_de_contrato_parchea_config_ni_provider` — centinela textual sobre `backend/tests/contract/**` y sobre `test_plan218_tracker_contract.py`: cero coincidencias de `patch("services.gitlab_provider.config`, `patch("config`, `MagicMock(spec=GitLabTrackerProvider`, `patch(...GitLabTrackerProvider`. Codifica P4.
- `test_fixtures_sin_pii` — ningún fixture contiene `@` seguido de dominio, ni `PRIVATE-TOKEN`, ni cadenas de ≥ 20 caracteres alfanuméricos que parezcan token (mismo patrón que el Plan 217 §15).
- `test_conformance_legacy_deja_de_mentir` — afirma que `tests/test_tracker_provider_conformance.py` ya **no** contiene la cadena `"no que esté hardcoded NotImplementedError"` (obliga a corregir el test mentiroso en esta misma fase).

**Además, editar** `backend/tests/test_tracker_provider_conformance.py:81-92`: renombrar `test_no_port_method_is_a_stub` → `test_port_methods_son_callables` (que es lo que realmente hace) y borrar el comentario engañoso. La verificación de "no es un stub" pasa a ser responsabilidad del contrato conductual.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_tracker_contract.py" -q`
y luego `& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_tracker_provider_conformance.py" -q`

**Criterio de aceptación (binario):** ambos comandos verdes; `grep -c "no que esté hardcoded" "Stacky Agents/backend/tests/test_tracker_provider_conformance.py"` devuelve **0**; y el parametrize corre exactamente 2 veces (un proveedor cada vez), verificable con `-v`.

**Flag:** ninguna — son tests. No hay superficie de runtime.

**Impacto por runtime:** N/A. Fallback: no aplica (no corre en producción).

**Trabajo del operador: ninguno.**

---

### F4 — Destino por proyecto: fin del GitLab singleton global

**Objetivo (1 frase):** que cada proyecto declare su propio destino de tracker (URL de instancia, path de proyecto, archivo de credenciales), igual que ya hace ADO, sin romper la configuración global existente.

**Valor:** cierra B1. Sin esto no hay dos proyectos GitLab, ni coexistencia ADO+GitLab, ni migración verificable.

**Archivos a editar:**

1. `backend/services/project_context.py`
```diff
 @dataclass(frozen=True)
 class ProjectContext:
     stacky_project_name: str
     tracker_type: str
     tracker_project: str
     organization: str | None = None
+    base_url: str | None = None          # URL de instancia (GitLab self-managed, Mantis, Jira)
+    tracker_group: str | None = None     # grupo/namespace (GitLab epics)
     workspace_root: str | None = None
     auth_path: str | None = None
     vscode_port: int | None = None
```
```diff
 def _auth_path_for(cfg: dict) -> str | None:
     ...
     if tracker_type == "jira":
         default_auth = "auth/jira_auth.json"
     elif tracker_type == "mantis":
         default_auth = "auth/mantis_auth.json"
+    elif tracker_type == "gitlab":
+        default_auth = "auth/gitlab_auth.json"
     else:
         default_auth = "auth/ado_auth.json"
```
Y una función nueva:
```python
@dataclass(frozen=True)
class TrackerTarget:
    """Destino resuelto de escritura/lectura. CONGELADO por el Plan 218 (§3.1)."""
    tracker_type: str
    project_path: str          # ADO: nombre de proyecto | GitLab: 'grupo/proyecto'
    base_url: str | None
    organization: str | None
    group: str | None
    auth_path: str | None

def build_tracker_target(project_name: str | None = None) -> TrackerTarget:
    """Resuelve el destino desde issue_tracker del config.json del proyecto.
    Compatibilidad: si el proyecto NO declara base_url/project para gitlab,
    cae a config.config.GITLAB_URL / GITLAB_PROJECT (comportamiento actual)."""
```

2. `backend/services/tracker_provider.py:110-116`
```diff
     if ttype == "gitlab":
         if not bool(getattr(config.config, "STACKY_GITLAB_ENABLED", False)):
             raise TrackerConfigError(...)
         from services.gitlab_provider import GitLabTrackerProvider
-        return GitLabTrackerProvider(project=project)
+        if bool(getattr(config.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", True)):
+            from services.project_context import build_tracker_target
+            tgt = build_tracker_target(project)
+            return GitLabTrackerProvider(
+                project=tgt.project_path, base_url=tgt.base_url,
+                group=tgt.group, auth_path=tgt.auth_path,
+            )
+        return GitLabTrackerProvider(project=project)   # ruta legacy, byte-idéntica
```

3. `backend/services/gitlab_provider.py:33-39` — la firma se amplía **de forma aditiva** (todos los parámetros nuevos son opcionales y caen a la config global si vienen `None`), de modo que `GitLabTrackerProvider(project="x")` sigue funcionando igual:
```python
def __init__(self, project=None, *, base_url=None, group=None, auth_path=None):
    base = base_url or (getattr(config.config, "GITLAB_URL", "") or "")
    proj = project or (getattr(config.config, "GITLAB_PROJECT", "") or "")
    self._client = GitLabClient(base_url=base, project=proj, auth_path=auth_path)
    self._project = proj
    self._group = group or (getattr(config.config, "STACKY_GITLAB_GROUP", "") or "")
    self._epics_native = bool(getattr(config.config, "STACKY_GITLAB_EPICS_NATIVE", False))
```
(`GitLabClient.__init__` ya acepta `auth_path` y sabe leer `auth/gitlab_auth.json` — `gitlab_client.py:49,75`.)

4. `backend/services/client_profile_defaults/gitlab.json` — **crear** (hoy existen solo `azure_devops.json`, `jira.json`, `mantis.json`). Misma estructura que `azure_devops.json`, con `language.ticket_token_pattern = "GL-{id}"` y un `tracker_state_machine` cuyos estados son etiquetas GitLab (`stacky::to-do`, `stacky::doing`, `stacky::blocked`, `stacky::review`), coherente con `gitlab_provider.py:82-90`.

**Tests PRIMERO — `backend/tests/test_plan218_tracker_target.py`:**
- `test_auth_path_gitlab_usa_su_propio_archivo` — un `config.json` con `type="gitlab"` resuelve `auth_path` terminando en `auth/gitlab_auth.json`, **no** en `ado_auth.json`.
- `test_target_toma_base_url_del_proyecto` — con `issue_tracker.base_url="https://git.interno/"`, `build_tracker_target().base_url` es esa.
- `test_target_cae_a_config_global_si_falta` — sin `base_url` en el proyecto, cae a `config.config.GITLAB_URL` (compatibilidad).
- `test_factory_pasa_project_path_no_nombre_stacky` — con proyecto Stacky `"RSPACIFICO"` e `issue_tracker.project="grupo/repo"`, el provider construido tiene `_project == "grupo/repo"` (**hoy sería `"RSPACIFICO"`**).
- `test_dos_proyectos_gitlab_distintos` — dos configs con base_url/project distintos producen providers con destinos distintos en la misma corrida.
- `test_flag_off_es_byte_identico` — con `STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED=False`, el provider se construye por la ruta legacy.
- `test_perfil_gitlab_existe_y_valida` — `client_profile_defaults/gitlab.json` existe, parsea, y tiene las mismas claves de primer nivel que `azure_devops.json`.
- `test_ado_no_cambia` — `build_ado_client` sigue resolviendo igual (regresión ADO).

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_tracker_target.py" -q`
Regresión obligatoria en la misma fase: `... -m pytest "Stacky Agents/backend/tests/test_ado_client_stacky_name_resolution.py" -q` y `... "Stacky Agents/backend/tests/test_tracker_factory.py" -q`.

**Criterio de aceptación (binario):** los 3 comandos verdes; `Test-Path "Stacky Agents/backend/services/client_profile_defaults/gitlab.json"` devuelve `True`; `grep -c "gitlab" "Stacky Agents/backend/services/project_context.py"` ≥ 1.

**Flag:** `STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED` (bool, default **True**, categoría `integraciones`). Default ON: es corrección de resolución interna, no agrega prerequisitos (si el proyecto no declara nada, cae a la config global de hoy), no bypasea revisión humana, no es destructiva, no reduce seguridad. OFF ⇒ ruta legacy byte-idéntica.

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — los 3 obtienen su provider por la misma fábrica (`claude_code_cli_runner.py:146`, `codex_cli_runner.py:125`, y el resto del backend para Copilot). Fallback de los tres: flag OFF.

**Trabajo del operador: ninguno** (los proyectos existentes no declaran nada nuevo y siguen funcionando; declarar `base_url` es opcional y solo hace falta para un segundo GitLab).

---

### F5 — Vocabulario canónico + alias de compatibilidad (aditivo, cero renombres)

**Objetivo (1 frase):** que el dominio hable en términos neutrales (`external_id`, `tracker_state`, `item_url`, `parent_external_id`, `assignee`) **sin romper** los 495 usos de campos `ado_*` que hoy tiene el frontend en 88 archivos.

**Valor:** desacopla el modelo del proveedor sin una migración de riesgo. Habilita que los subplanes 220..232 escriban código neutral.

**Archivos a crear/editar:**

1. `backend/services/tracker_vocabulary.py` (nuevo, puro)
```python
"""Vocabulario canónico del dominio + alias legacy. PURO. CONGELADO por el Plan 218."""
CANONICAL_FIELDS: tuple[str, ...] = (
    "external_id", "tracker_type", "tracker_project", "item_type",
    "title", "description", "tracker_state", "item_url",
    "parent_external_id", "assignee", "priority",
)
# canónico -> alias legacy que DEBE seguir emitiéndose (P6)
LEGACY_ALIASES: dict[str, str] = {
    "external_id": "ado_id", "tracker_state": "ado_state", "item_url": "ado_url",
    "parent_external_id": "parent_ado_id", "assignee": "assigned_to_ado",
    "item_type": "work_item_type",
}
def with_legacy_aliases(payload: dict) -> dict:
    """Devuelve payload + las claves legacy. NUNCA quita claves. Idempotente."""
def to_canonical(payload: dict) -> dict:
    """Acepta claves legacy o canónicas y devuelve solo canónicas."""
```

2. `backend/models.py` — `Ticket.to_dict()` (`:80-98`) pasa a devolver `with_legacy_aliases({...canónico...})`. **Ninguna columna se renombra** en esta serie: `ado_id` (`:42`), `ado_state` (`:52`), `ado_url` (`:53`), `parent_ado_id` (`:56`), `assigned_to_ado` (`:64`) quedan intactas. Solo cambia el payload emitido, que pasa a ser un superconjunto del actual.

3. `frontend/src/types.ts` — agregar a `interface Ticket` los campos canónicos como **opcionales** (`external_id?: number; tracker_state?: string; item_url?: string; parent_external_id?: number; assignee?: string; item_type?: string;`). No se toca ningún campo existente.

4. `frontend/src/services/trackerVocabulary.ts` (nuevo, puro) — `pickExternalId(t)`, `pickState(t)`, `pickUrl(t)`, `pickItemType(t)`: leen el canónico y caen al legacy. Es la función que los subplanes de UI van adoptando gradualmente.

**Tests PRIMERO:**
- `backend/tests/test_plan218_vocabulary_aliases.py`:
  - `test_with_legacy_aliases_es_superconjunto` — el dict resultante contiene todas las claves originales.
  - `test_with_legacy_aliases_es_idempotente` — aplicarlo dos veces da lo mismo.
  - `test_to_canonical_acepta_legacy` — `to_canonical({"ado_id": 5})["external_id"] == 5`.
  - `test_to_canonical_prefiere_canonico` — con ambas claves presentes y distintas, gana la canónica.
  - `test_ticket_to_dict_mantiene_todas_las_claves_legacy` — el `to_dict()` nuevo contiene las 14 claves que devolvía antes (lista literal en el test).
  - `test_ticket_to_dict_agrega_canonicas` — contiene además las 6 canónicas.
  - `test_flag_off_devuelve_payload_original` — con la flag en `False`, `to_dict()` devuelve exactamente el dict legacy.
- `frontend/src/services/__tests__/trackerVocabulary.test.ts`:
  - `pickExternalId` prefiere `external_id`, cae a `ado_id`, devuelve `null` si no hay ninguno.
  - `pickUrl` / `pickState` / `pickItemType`: mismos 3 casos cada uno.

**Comandos exactos:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_vocabulary_aliases.py" -q`
`cd "Stacky Agents/frontend"; npx vitest run src/services/__tests__/trackerVocabulary.test.ts`
`cd "Stacky Agents/frontend"; npx tsc --noEmit`

**Criterio de aceptación (binario):** los 3 comandos verdes; `grep -c "ado_id" "Stacky Agents/backend/models.py"` **no disminuye** respecto del valor previo (prueba de que no hubo renombre destructivo).

**Flag:** `STACKY_CANONICAL_VOCABULARY_ENABLED` (bool, default **True**, categoría `integraciones`). Default ON: el cambio es puramente aditivo (agrega claves al JSON), por lo que no puede romper un consumidor existente. OFF ⇒ payload idéntico al de hoy.

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — los 3 reciben el contexto del ticket por la misma serialización (`Ticket.to_dict()` alimenta la inyección de contexto de los tres). Fallback de los tres: flag OFF ⇒ payload legacy.

**Trabajo del operador: ninguno.**

---

### F6 — Degradación declarada: `CapabilityUnavailable` en vez de errores mudos

**Objetivo (1 frase):** que una capacidad no soportada por el proveedor activo se manifieste como un mensaje accionable y un `200 {available:false}`, nunca como un `NotImplementedError` que tira 500 ni como un silencio.

**Valor:** convierte los ~10 dominios sin paridad en una experiencia honesta mientras los subplanes los cierran. Es lo que permite hacer rollout gradual sin romper nada.

**Archivos a editar/crear:**

1. `backend/services/tracker_provider.py` — agregar al final de la sección de errores:
```python
class CapabilityUnavailable(TrackerError):
    """La capacidad no existe (o es parcial) en el proveedor activo. NO es un bug."""
    def __init__(self, capability: str, provider: str, *, reason: str, workaround: str = ""):
        super().__init__(f"'{capability}' no disponible en {provider}: {reason}")
        self.capability = capability
        self.provider = provider
        self.reason = reason
        self.workaround = workaround
    def to_payload(self) -> dict:
        return {"available": False, "capability": self.capability,
                "provider": self.provider, "reason": self.reason,
                "workaround": self.workaround}
```

2. `backend/api/errors.py` — registrar el handler que traduce `CapabilityUnavailable` a **HTTP 200** con `to_payload()`, siguiendo el patrón ya establecido por el Plan 148 (`200 + available:false` en vez de 502).

3. `backend/api/tickets.py:677-695` — reemplazar el `NotImplementedError` por:
```diff
-        raise NotImplementedError(
-            f"Sync para tracker '{provider.name}' aun no implementado. "
-            "Activá STACKY_TICKETS_PROVIDER_ENABLED=false o esperá Plan 71."
-        )
+        raise CapabilityUnavailable(
+            "tracker.sync.full", provider.name,
+            reason="el sync de ítems de este tracker todavía no está implementado",
+            workaround="Plan 220 lo implementa; mientras tanto usá un proyecto Azure DevOps.",
+        )
```
(F6 **no** implementa el sync de GitLab — eso es el subplan 220. F6 solo hace que el hueco sea visible y no rompa el proceso.)

**Tests PRIMERO — `backend/tests/test_plan218_capability_unavailable.py`:**
- `test_payload_tiene_las_5_claves` — `available`, `capability`, `provider`, `reason`, `workaround`.
- `test_es_subclase_de_tracker_error` — `issubclass(CapabilityUnavailable, TrackerError)`.
- `test_endpoint_de_sync_devuelve_200_con_available_false` — con un provider falso llamado `gitlab`, `POST /api/tickets/sync` responde **200** y `body["available"] is False` y `body["capability"] == "tracker.sync.full"`.
- `test_endpoint_de_sync_ado_no_cambia` — con provider `azure_devops`, el endpoint se comporta exactamente igual que antes (regresión).
- `test_no_quedan_notimplementederror_en_api` — centinela: `grep` de `NotImplementedError` en `backend/api/*.py` devuelve 0 (con allowlist literal vacía).
- `test_flag_off_restaura_excepcion_legacy` — con `STACKY_CAPABILITY_DEGRADATION_ENABLED=False`, vuelve el comportamiento anterior.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_unavailable.py" -q`
Regresión: `... -m pytest "Stacky Agents/backend/tests/test_plan70_group_sync.py" -q`

**Criterio de aceptación (binario):** ambos comandos verdes; `grep -c "NotImplementedError" "Stacky Agents/backend/api/tickets.py"` devuelve **0**.

**Flag:** `STACKY_CAPABILITY_DEGRADATION_ENABLED` (bool, default **True**, categoría `integraciones`). Default ON: convertir un 500 mudo en un 200 accionable **mejora** estabilidad y DX; no agrega prerequisitos ni reduce seguridad. OFF ⇒ excepción legacy.

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — la degradación ocurre en el backend, antes de invocar cualquier runtime; los 3 ven el mismo `available:false`. Fallback de los tres: flag OFF.

**Trabajo del operador: ninguno** (y gana un mensaje que le dice qué hacer, en vez de un error 500).

---

### F7 — El orquestador: catálogo de subplanes, mapa de colisiones y gates verificables

**Objetivo (1 frase):** materializar la serie 219..236 como un artefacto de datos validado por tests, para que el orden, las dependencias y la propiedad de archivos no dependan de la memoria de nadie.

**Valor:** es lo que convierte este documento en un **orquestador** y no en una lista de deseos. Resuelve además la divergencia doc↔código de §2.4.

**Archivos a crear:**

1. `docs/_roadmap/serie_paridad_218.json` — el catálogo. Estructura (una entrada por subplan, contenido completo en §5):
```json
{
  "schema_version": 1,
  "orchestrator": 218,
  "milestones": [
    {"id": "M0", "title": "Sustrato", "plans": [218]},
    {"id": "M1", "title": "GitLab usable de punta a punta", "plans": [219, 220, 221]},
    {"id": "M2", "title": "Escritura y dominio", "plans": [222, 223, 224]},
    {"id": "M3", "title": "DevOps completo", "plans": [226, 227, 228, 230]},
    {"id": "M4", "title": "Operación y superficie", "plans": [225, 229, 231, 232, 233]},
    {"id": "M5", "title": "Extensibilidad y cierre", "plans": [234, 235, 236]}
  ],
  "subplans": [
    {
      "number": 219,
      "slug": "ONBOARDING_Y_CREDENCIALES_GITLAB_POR_PROYECTO",
      "title": "...",
      "priority": "P0",
      "milestone": "M1",
      "depends_on": [218],
      "owns_files": ["backend/project_manager.py", "frontend/src/components/NewProjectModal.tsx"],
      "capabilities": ["identity.me", "identity.token.scopes"],
      "acceptance": "..."
    }
  ]
}
```

2. `backend/services/parity_series.py` (nuevo, puro) — `load_series() -> dict`, `validate_series(series) -> list[str]` (devuelve lista de violaciones), `topological_order(series) -> list[int]`.

**Tests PRIMERO — `backend/tests/test_plan218_serie_integridad.py`:**
- `test_numeros_unicos_y_consecutivos` — los `number` son únicos y forman el rango 219..236 sin huecos.
- `test_toda_dependencia_existe` — cada valor de `depends_on` está en la serie o es 218.
- `test_sin_ciclos` — `topological_order` no levanta.
- `test_sin_colision_de_propiedad` — **ningún archivo aparece en `owns_files` de dos subplanes**. Esta es la garantía ejecutable del "mapa de colisiones".
- `test_toda_capacidad_declarada_existe` — cada valor de `capabilities` ∈ `CAPABILITY_KEYS` (§F2).
- `test_toda_capacidad_no_full_tiene_dueño` — cada capacidad con status `absent`/`partial` en `CAPABILITY_MATRIX` para algún proveedor aparece en `capabilities` de **al menos un** subplan, **o** está listada en la constante literal `FUERA_DE_SCOPE_218` del propio test. **Este test hace imposible olvidarse de un gap.**
- `test_prioridad_y_hito_validos` — `priority` ∈ {`P0`,`P1`,`P2`}; `milestone` ∈ los ids declarados.
- `test_docs_existentes_coinciden` — si `Stacky Agents/docs/<number>_PLAN_*.md` existe, su nombre empieza con `<number>_PLAN_<slug>`.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_serie_integridad.py" -q`

**Criterio de aceptación (binario):** comando verde con 8 tests; `Test-Path "Stacky Agents/docs/_roadmap/serie_paridad_218.json"` → `True`; el JSON tiene exactamente 18 entradas en `subplans` (`(Get-Content ... | ConvertFrom-Json).subplans.Count` = 18).

**Flag:** ninguna — artefacto de datos + módulo puro + tests, sin superficie de runtime.

**Impacto por runtime:** N/A.

**Trabajo del operador: ninguno.**

---

### F8 — Rollout por capacidad, panel de paridad y rollback

**Objetivo (1 frase):** que el operador pueda ver, en una pantalla, qué funciona con su tracker y qué no — y que cada capacidad se pueda apagar sin tocar código.

**Valor:** cierra el lazo human-in-the-loop: la degradación deja de ser un error que aparece a mitad de un flujo y pasa a ser información disponible antes de empezar.

**Archivos a crear/editar:**

1. `backend/services/parity_rollout.py` (nuevo)
```python
def capability_enabled(capability: str, project: str | None = None) -> bool:
    """AND de tres niveles, en este orden:
       1) config.config.STACKY_PROVIDER_PARITY_ENABLED (maestra; OFF ⇒ True para todo)
       2) provider_capabilities.supports(tracker_type_del_proyecto, capability)
       3) override por proyecto: issue_tracker.parity_overrides.<capability> (bool, opcional)
    NO hace I/O de red. Cachea el config del proyecto por el TTL ya existente."""
def parity_report(project: str | None = None) -> dict:
    """{'provider': str, 'project': str, 'capabilities': [
         {'key','status','enabled','loss','owner_plan'} ]}"""
```

2. `backend/api/parity.py` (nuevo) — blueprint `parity_bp` con `GET /api/parity/matrix?project=<n>` (solo lectura). **Registrar en `backend/api/__init__.py` con `url_prefix="/api"` y la ruta declarada como `/parity/matrix`** — no `/api/parity/...` dentro del blueprint (los planes 72, 73 y 74 fueron rechazados por el doble prefijo `/api/api/...`; ver §9 R6).

3. `frontend/src/services/parityMatrixModel.ts` (nuevo, puro) — `groupByDomain(caps)`, `summarize(caps) -> {full, partial, absent, na}`, `statusLabel(status)`.

4. `frontend/src/components/ParityMatrixPanel.tsx` + `ParityMatrixPanel.module.css` (nuevos) — tabla agrupada por dominio con el estado por capacidad, renderizada dentro de `frontend/src/pages/DiagnosticsPage.tsx`. **Sin `style={{`, sin `confirm(`/`alert(`/`prompt(`** (ratchet `frontend/src/__tests__/uiDebtRatchet.test.ts:22,27`); todos los colores por tokens del `*.module.css`.

**Tests PRIMERO:**
- `backend/tests/test_plan218_parity_endpoint.py`:
  - `test_matrix_devuelve_todas_las_capacidades` — el endpoint responde 200 con `len(body["capabilities"]) == len(CAPABILITY_KEYS)`.
  - `test_override_por_proyecto_apaga_una_capacidad` — con `parity_overrides: {"mr.approve": false}`, esa capacidad viene `enabled=false` aunque el status sea `full`.
  - `test_flag_maestra_off_habilita_todo` — con `STACKY_PROVIDER_PARITY_ENABLED=False`, todas vienen `enabled=true` (comportamiento pre-plan).
  - `test_endpoint_es_solo_lectura` — `POST /api/parity/matrix` devuelve 405.
  - `test_ruta_registrada_sin_doble_prefijo` — la URL map contiene `/api/parity/matrix` y **no** `/api/api/parity/matrix`.
  - `test_no_filtra_secretos` — la respuesta no contiene `token`, `pat`, `PRIVATE-TOKEN` en ninguna clave ni valor.
- `frontend/src/services/__tests__/parityMatrixModel.test.ts`: `groupByDomain` agrupa por el prefijo antes del primer punto; `summarize` cuenta los 4 estados; `statusLabel` mapea los 4 sin caer en `undefined`.

**Comandos exactos:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_parity_endpoint.py" -q`
`cd "Stacky Agents/frontend"; npx vitest run src/services/__tests__/parityMatrixModel.test.ts`
`cd "Stacky Agents/frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts`
`cd "Stacky Agents/frontend"; npx tsc --noEmit`

**Criterio de aceptación (binario):** los 4 comandos verdes; `grep -c "style={{" "Stacky Agents/frontend/src/components/ParityMatrixPanel.tsx"` devuelve **0**.

**Flag:** `STACKY_PROVIDER_PARITY_ENABLED` (la misma de F2, default **True**). Con OFF: el endpoint devuelve 404, el panel no se monta y `capability_enabled` devuelve `True` para todo ⇒ comportamiento byte-idéntico al de hoy. **Ese es el rollback completo del plan 218 en un click.**

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — es superficie de UI + backend, ajena al motor de agentes. Fallback de los tres: flag OFF.

**Trabajo del operador: ninguno** (gana una pantalla informativa; no tiene que configurar nada para que aparezca).

---

## 5. Catálogo de subplanes 219..236 (la orquestación)

Cada subplan se genera con `/proponer-plan-stacky` usando el objetivo textual de su ficha, y se pasa por `criticar-y-mejorar-plan` antes de implementar. Los `owns_files` son **exclusivos**: F7 tiene un test que falla si dos subplanes reclaman el mismo archivo.

**"Responsable sugerido"** no es una persona (Stacky es mono-operador, P9): es **qué runtime/agente conviene** para ese trabajo, dada su naturaleza.

### 5.1 Tabla maestra

| # | Título corto | Prio | Hito | Depende de | Responsable sugerido | Entregable |
|---|---|---|---|---|---|---|
| **219** | Onboarding y credenciales GitLab por proyecto | P0 | M1 | 218 | Copilot Pro (UI) + Codex (backend acotado) | Alta de proyecto GitLab desde la UI, con credencial cifrada |
| **220** | Sincronización de ítems agnóstica (`tracker_sync`) | P0 | M1 | 218, 219 | Claude Code CLI (refactor amplio) | Tablero poblado con issues de GitLab |
| **221** | Cierre del desacople de `api/tickets.py` (Plan 70 → 100 %) | P0 | M1 | 220 | Claude Code CLI | `STACKY_TICKETS_PROVIDER_ENABLED` pasa a default ON |
| **222** | Publicación agnóstica: puerto `PublisherProvider` + outbox | P1 | M2 | 221 | Claude Code CLI | Publicar resultado de agente en GitLab |
| **223** | Identidad, usuarios y miembros multi-proveedor | P1 | M2 | 221 | Codex CLI | Asignación y "quién soy" funcionan en GitLab |
| **224** | Tipos de ítem, jerarquía, etiquetas, milestones e iteraciones | P1 | M2 | 220 | Claude Code CLI | Épica→hijos y tablero de sprint en GitLab |
| **225** | Aprendizaje de ediciones y ledger multi-proveedor | P2 | M4 | 224 | Codex CLI | Golden negativo alimentado también desde GitLab |
| **226** | CI/CD: definiciones, artefactos, ambientes y aprobaciones | P1 | M3 | 218 | Codex CLI | Paridad CI completa en la matriz |
| **227** | Repositorio: ramas, commits, tags y lectura de archivos | P1 | M3 | 218 | Codex CLI | Puerto `RepoProvider` (hoy solo `commit_file`) |
| **228** | MR/PR: diff real en ADO, revisores, aprobaciones y políticas | P1 | M3 | 227 | Claude Code CLI | `mr.diff` pasa a `full` en ADO |
| **229** | Eventos entrantes: webhooks ADO/GitLab → Stacky | P2 | M4 | 220 | Claude Code CLI | Fin del polling como único mecanismo |
| **230** | Seguridad: tokens, scopes mínimos y cifrado uniforme | P1 | M3 | 219 | Codex CLI | Token GitLab cifrado + preflight de scopes |
| **231** | Observabilidad por proveedor: telemetría, errores y salud | P1 | M4 | 218 | Codex CLI | Dimensión `provider` en toda la telemetría |
| **232** | Frontend agnóstico: vocabulario, capacidades y deep links | P1 | M4 | 218 F5, 218 F8 | Copilot Pro | UI que se adapta al proveedor activo |
| **233** | Banco de pruebas cross-proveedor: servidor falso + E2E | P1 | M4 | 218 F3 | Claude Code CLI | E2E de los 2 proveedores sin red real |
| **234** | Coexistencia y migración: dos trackers, cutover y rollback | P2 | M5 | 220, 222 | Claude Code CLI | Runbook de migración verificable |
| **235** | Tercer proveedor: kit de conformidad + adaptador de prueba | P2 | M5 | 233 | Codex CLI | Prueba de que la abstracción es extensible |
| **236** | Documentación viva y corpus RAG del modelo multi-proveedor | P2 | M5 | 235 | Claude Code CLI | Docs generadas desde la matriz + chunks RAG |

### 5.2 Fichas de los subplanes

---

**219 — Onboarding y credenciales GitLab por proyecto (paridad con `ado_auth.json`)**
- **Objetivo:** que se pueda dar de alta un proyecto GitLab desde la UI con la misma fricción que uno de ADO, con el token cifrado y verificable.
- **Gap que cierra:** B3. `NewProjectModal.tsx` no ofrece GitLab (solo `:376` ADO, `:382` Jira, `:389` Mantis); `project_manager.py` no tiene `initialize_gitlab_project` (sí ADO `:270`, Jira `:317`, Mantis `:560`); `GET /api/projects/{n}/credentials` no expone `gitlab_user`; `GITLAB_TOKEN` no tiene ninguna ruta de UI (`api/global_config.py:87` lo excluye a propósito de `_MANAGED_KEYS`).
- **`owns_files`:** `backend/project_manager.py`, `backend/api/projects.py`, `frontend/src/components/NewProjectModal.tsx`, `backend/services/gitlab_auth_store.py` (nuevo).
- **Capacidades:** `identity.me`, `identity.token.scopes`.
- **Criterio de aceptación:** crear un proyecto con `type=gitlab` desde la UI genera `backend/projects/<N>/config.json` con `issue_tracker.{type,base_url,project,group,auth_file}` y `backend/projects/<N>/auth/gitlab_auth.json` **cifrado**; `GET /api/projects/<N>/credentials` devuelve `{"tracker_type":"gitlab","has_credentials":true,"gitlab_user":"<username>"}`.
- **Nota de flags:** la flag del subplan nace ON; `STACKY_GITLAB_ENABLED` sigue OFF por **excepción 3** hasta que el operador cargue credenciales — y encenderla es un click, no una tarea.

---

**220 — Sincronización de ítems agnóstica (`tracker_sync`)** ⭐ *el desbloqueo principal*
- **Objetivo:** un único motor de sincronización tracker→BD local, alimentado por el puerto, que reemplace `NotImplementedError` por issues reales de GitLab en el tablero.
- **Gap que cierra:** B2 (`api/tickets.py:692`). No existe `gitlab_sync.py`; `ado_sync.sync_tickets` (`:102`) recibe un `AdoClient` y lee `System.*` (`:130-146`).
- **`owns_files`:** `backend/services/tracker_sync.py` (nuevo), `backend/services/ado_sync.py` (pasa a ser adaptador delgado), `backend/api/tickets.py` (solo la función `_sync_via_provider_or_ado`).
- **Capacidades:** `tracker.sync.full`, `tracker.sync.incremental`, `tracker.items.list`, `tracker.query.search`.
- **Criterio de aceptación:** con un proyecto GitLab y el servidor falso de 233 (o fixtures), `POST /api/tickets/sync` devuelve 200 y crea N filas `Ticket` con `tracker_type="gitlab"` y `external_id` = `iid`; re-correr no duplica (unicidad por `ux_tickets_stacky_tracker_external`, `models.py:71-77`); la regresión ADO (`test_plan70_group_sync.py`) queda verde.
- **Riesgo propio:** `iid` vs `id` de GitLab. El plan debe fijar **`iid` como `external_id`** (es el visible y el que usan los deep links, `gitlab_deep_links.py:38`) y guardar el `id` global en `fields`.

---

**221 — Cierre del desacople de `api/tickets.py` (Plan 70 al 100 %)**
- **Objetivo:** llevar las 20 líneas que invocan `_ado_client_for_ticket(` a 1 (solo la definición) y encender `STACKY_TICKETS_PROVIDER_ENABLED` por default.
- **Gap que cierra:** hoy la flag es **OFF** (`config.py:1178-1180`) y su comentario admite un bug ("verificado que NO comparte el bug de `STACKY_TICKETS_PROVIDER_ENABLED`", `config.py:1202`), o sea: el desacople del Plan 70 no está activo en producción.
- **`owns_files`:** `backend/api/tickets.py` (todo el archivo salvo `_sync_via_provider_or_ado`, que es de 220), `backend/tests/test_plan70_no_typed_adoclient_in_api.py`.
- **Capacidades:** todas las de `tracker.*` marcadas `full`.
- **Criterio de aceptación:** `grep -c "_ado_client_for_ticket(" "Stacky Agents/backend/api/tickets.py"` = **1**; `config.py` declara la flag con default `"true"` y la clave figura en `_CURATED_DEFAULTS_ON`; la suite de contrato de F3 verde con la flag ON.
- **Cuidado operativo:** `api/tickets.py` tiene 7245 líneas y es el archivo con más colisiones históricas (planes 70, 71, 148, 153, 208, 212). **Anclar por TEXTO, nunca por número de línea** (memoria `gotcha-shared-index-commit-sweeps-foreign` + advertencia del Plan 153).

---

**222 — Publicación agnóstica: puerto `PublisherProvider` + outbox neutral**
- **Objetivo:** que publicar el resultado de un agente funcione igual en los dos trackers, con el ledger transaccional del Plan 153 intacto.
- **Gap que cierra:** `ado_publisher.py` (913 líneas) no tiene contraparte GitLab; se declara a sí mismo el único autorizado a llamar `AdoClient().post_comment` (`:8,250`); requiere `Ticket.ado_id` (`:280,291`); `ado_write_outbox.py` (508 líneas) tiene tabla `ado_write_operations` y columnas `ado_request`/`ado_response` (`:158-162`). **Nota verificada:** el docstring de `ado_write_outbox.py:15-17` nombra `ado_write_executor.py`, `ado_write_worker.py` y `api/ado_writes.py` — **ninguno de los tres existe**; el subplan debe corregir el docstring, no crear los módulos.
- **`owns_files`:** `backend/services/publisher_provider.py` (nuevo), `backend/services/ado_publisher.py`, `backend/services/ado_write_outbox.py`, `backend/services/gitlab_publisher.py` (nuevo).
- **Capacidades:** `tracker.comments.post`, `tracker.comments.idempotent`, `tracker.attachments.upload`, `tracker.attachments.link`.
- **Criterio de aceptación:** publicar el HTML de una ejecución en un proyecto GitLab crea una nota con el marcador y adjunta los archivos; re-publicar no duplica (idempotencia por marcador, verificada por el contrato de F3); `publish_ledger` registra la operación con `provider="gitlab"`.

---

**223 — Identidad, usuarios y miembros multi-proveedor**
- **Objetivo:** resolver "quién soy" y "quién es este usuario" en ambos trackers, con caché por proyecto.
- **Gap que cierra:** `ado_identity.py` es ADO-only (mapa `ado_user_map.json:36`, `build_ado_client(...)` en `:138-140`); GitLab solo tiene `_resolve_assignee_id` (`gitlab_provider.py:92`) que **borra silenciosamente el asignado si el usuario no existe** (`:368-369`). `User` (`models.py:101-129`) tiene columnas `ado_unique_name`/`ado_display_name`.
- **`owns_files`:** `backend/services/identity_provider.py` (nuevo), `backend/services/ado_identity.py`, `backend/services/gitlab_identity.py` (nuevo), `backend/services/ticket_assigner.py`.
- **Capacidades:** `identity.me`, `identity.user.find`, `identity.members.list`, `identity.groups.list`.
- **Guardarraíl (P9):** "miembros" y "grupos" son **lectura del proveedor** para poder asignar y para preflight de permisos. **Prohibido** introducir roles o control de acceso dentro de Stacky.

---

**224 — Tipos de ítem, jerarquía, etiquetas, milestones e iteraciones**
- **Objetivo:** normalizar la taxonomía (Epic/Feature/User Story/Task/Bug ↔ etiquetas `type::*` + epics/issue-links) y los contenedores temporales (Iterations ↔ Milestones).
- **Gap que cierra:** el Plan 153 §7 dejó explícitamente fuera "traducción de tipos en providers no-ADO". `_ADO_TYPE_MAP` (`ado_provider.py:19-26`) no tiene espejo declarativo. `_state_map_for_gitlab` (`gitlab_provider.py:82-90`) está **hardcodeado**, no sale del perfil del cliente (colisiona conceptualmente con el Plan 216, que centraliza estados en el perfil). Sprints/iteraciones son 100 % ADO (`services/pm/ado_pm_collector.py:8-11`, y `api/pm.py` devuelve 400 `TRACKER_NOT_SUPPORTED` para no-ADO en `:105-107`).
- **`owns_files`:** `backend/services/item_taxonomy.py` (nuevo), `backend/api/pm.py`, `backend/services/pm/` (todo el paquete), `frontend/src/utils/workItemTypeColor.ts`, `frontend/src/utils/resolveSuggestedAgent.ts`.
- **Capacidades:** `tracker.types.list`, `tracker.hierarchy.link_parent`, `tracker.hierarchy.find_child`, `tracker.epics.list`, `tracker.epics.create_native`, `tracker.iterations.list`, `tracker.milestones.list`, `tracker.labels.ensure`.
- **Contrato con el Plan 216:** el mapa de estados **sale del perfil del cliente** (`state_flow`), no del código. Si 216 ya está implementado, 224 lo consume; si no, 224 declara la dependencia y usa `client_profile_defaults/gitlab.json` (creado en 218 F4).

---

**225 — Aprendizaje de ediciones y ledger multi-proveedor**
- **Objetivo:** que el golden negativo (Planes 60/81) se alimente también de las ediciones hechas en GitLab.
- **Gap que cierra:** `ado_edit_learning.py` usa revisiones ADO (`fetch_work_item_updates`, `:103`) y hardcodea `work_item_type="Epic"` (`:182,205`); `ado_edit_ledger.py` usa como clave de idempotencia `(ado_id, rev)` (`:142,165,189`) — GitLab no tiene `rev`, tiene `resource_state_events`/`resource_label_events` (`gitlab_provider.py:411-462`, hoy con las 3 sub-consultas silenciadas en `:431,447,462`).
- **`owns_files`:** `backend/services/ado_edit_learning.py`, `backend/services/ado_edit_ledger.py`, `backend/services/edit_learning_provider.py` (nuevo), `backend/harness/ado_edit_detect.py`.
- **Capacidades:** `tracker.updates.history`.

---

**226 — CI/CD: definiciones, artefactos, ambientes y aprobaciones**
- **Objetivo:** completar el eje CI: descubrimiento/creación de definiciones, artefactos descargables, ambientes y aprobaciones.
- **Gap que cierra:** `ado_pipeline_definitions.py` (`find_yaml_definition:82`, `ensure_yaml_definition:125`) no tiene contraparte GitLab (que no tiene objeto "definition"; commitea `.gitlab-ci.yml`). **Artefactos y ambientes faltan en AMBOS proveedores.** `AdoCIProvider.infer_item_pipeline` es inferencia por LLM (`ado_pipeline_inference.py`), la de GitLab lee pipelines reales (`gitlab_ci_provider.py:32`) — semánticas distintas bajo el mismo método, que la matriz debe declarar como `partial` con pérdida.
- **`owns_files`:** `backend/services/ci_definitions_provider.py` (nuevo), `backend/services/ado_pipeline_definitions.py`, `backend/services/gitlab_ci_definitions.py` (nuevo), `backend/services/ci_artifacts_provider.py` (nuevo), `backend/api/ci.py`.
- **Capacidades:** `ci.pipeline.definition.find`, `ci.pipeline.definition.ensure`, `ci.artifacts.list`, `ci.artifacts.download`, `ci.environments.list`, `ci.approvals`, `ci.variables.masked`.

---

**227 — Repositorio: ramas, commits, tags y lectura de archivos**
- **Objetivo:** ampliar `RepoWriter` (hoy 1 solo método, `repo_writer.py:17`) a un `RepoProvider` con lectura y gestión de ramas.
- **Gap que cierra:** los Planes 177 (auto-PR), 210 (gate de build) y 211 (inspector post-build) necesitan leer archivos y crear ramas por API, y hoy no hay puerto. `incident_dev_pr.py` hace git local, no API.
- **`owns_files`:** `backend/services/repo_writer.py`, `backend/services/repo_provider.py` (nuevo).
- **Capacidades:** `repo.file.read`, `repo.file.commit`, `repo.branch.list`, `repo.branch.create`, `repo.commit.list`, `repo.tag.create`.
- **Compatibilidad:** `RepoWriter` y `REPO_WRITER_METHODS` **se conservan** (los usa `merge_request_provider.get_merge_request_provider:82`); `RepoProvider` los extiende.

---

**228 — MR/PR: diff real en ADO, revisores, aprobaciones y políticas**
- **Objetivo:** cerrar la asimetría del puerto MR: ADO sin diff ni approve.
- **Gap que cierra:** `ado_provider.get_merge_request_diff:429` devuelve `diff_text=""`, `diff_available=False` (`:455-457`); `list_merge_requests` devuelve `pipeline_status:"none"` siempre (`:425`); `approve_merge_request` no existe en ADO y se detecta por `hasattr` (`api/pr_review.py:368,409`).
- **`owns_files`:** `backend/services/merge_request_provider.py`, `backend/api/pr_review.py`, `backend/api/devops_production.py`, `frontend/src/components/devops/PrReviewerSection.tsx`.
- **Capacidades:** `mr.diff`, `mr.approve`, `mr.reviewers`, `mr.policies`.
- **Guardarraíl:** el merge sigue exigiendo confirmación literal del operador (Plan 95). **Prohibido** auto-merge o merge-when-pipeline-succeeds (P8).

---

**229 — Eventos entrantes: webhooks ADO/GitLab → Stacky**
- **Objetivo:** recibir eventos del tracker en vez de solo poll.
- **Gap que cierra:** `services/webhooks.py` es **solo saliente** (Stacky → terceros, con HMAC en `:70-73`). No hay receptor entrante. Declarado fuera de scope por el Plan 65 §7 y el Plan 208 §6: **nadie lo cubre**.
- **`owns_files`:** `backend/api/webhooks_inbound.py` (nuevo), `backend/services/webhook_inbound.py` (nuevo).
- **Capacidades:** `events.webhook.inbound`, `events.webhook.verify`.
- **Flag: default OFF — excepción dura 3 (prerequisito no garantizado en instalación default):** requiere que la instancia de Stacky sea **alcanzable desde el tracker** (URL pública o de red interna) y un secreto compartido, ninguno de los cuales existe en una instalación limpia. Con OFF, el polling actual sigue igual. El subplan debe citar esta excepción textualmente.
- **Guardarraíl (P8):** un webhook entrante **jamás** dispara una escritura ni un agente por su cuenta; solo invalida caché y encola una notificación para el operador.

---

**230 — Seguridad: tokens, scopes mínimos y cifrado uniforme**
- **Objetivo:** que la credencial de GitLab tenga el mismo tratamiento que la de ADO y que el operador sepa, antes de fallar, si su token alcanza.
- **Gap que cierra:** el token GitLab hoy vive en `GITLAB_TOKEN` (env) o en `auth/gitlab_auth.json` **en texto plano** (`gitlab_client.py:75-82`), mientras que `secrets_store.py` ya cifra con DPAPI (gap ya detectado por el Plan 217). `secret_scanner.py:15` solo tiene regla para `ADO_PAT`. `ci_trigger_rules.py:15-18` ya modela scopes (`{"gitlab":{"api"}, "azure_devops":{"vso.build_execute"}}`) y es la base a extender.
- **`owns_files`:** `backend/services/secrets_store.py`, `backend/services/secret_scanner.py`, `backend/services/token_scopes.py` (nuevo), `backend/services/connection_doctor.py`.
- **Capacidades:** `identity.token.scopes`.
- **Nota de portabilidad:** DPAPI es Windows-only (`secrets_store.py:71`); el subplan debe declarar el backend de secretos enchufable, igual que hizo el Plan 217 §4.

---

**231 — Observabilidad por proveedor: telemetría, errores tipados y salud**
- **Objetivo:** que toda métrica, log y error lleve la dimensión `provider`, y que la salud de la integración se vea por proveedor.
- **Gap que cierra:** `ado_publisher.py:73` usa `tracker_provider or "ado"` como default y `api/tickets.py:6323,6336` igual ⇒ **una corrida GitLab se etiqueta como "ado"** en telemetría. `integration_breaker.py:27,149` y `api/integrations.py:9-18` tienen taxonomía ADO-only (`ado_pat_expired`, `ado_project_not_found`, `ado_identity_unresolved`).
- **`owns_files`:** `backend/services/integration_breaker.py`, `backend/api/integrations.py`, `backend/services/stacky_logger.py`, `backend/api/metrics.py`.
- **Capacidades:** ninguna nueva (es transversal).

---

**232 — Frontend agnóstico: vocabulario, capacidades y deep links**
- **Objetivo:** que la UI hable el idioma del proveedor activo y oculte lo que ese proveedor no puede hacer.
- **Gap que cierra:** `frontend/src/utils/trackerUrls.ts:10-12` **hardcodea la organización y el proyecto** (`https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`) — el peor acoplamiento del frontend; `StructuredOutput.tsx:78` solo reconoce citas `ADO-\d+`; hay 19 rutas REST con ADO en el path (`/api/tickets/by-ado/...`, `/api/executions/{id}/publish-to-ado`); `PMCommandCenter.tsx:995` se declara "azure_devops únicamente"; `SprintBoardPage.tsx` está **huérfana** (sin importadores).
- **`owns_files`:** `frontend/src/utils/trackerUrls.ts`, `frontend/src/components/StructuredOutput.tsx`, `frontend/src/components/shell/shellNav.ts`, `frontend/src/pages/TicketBoard.tsx`, `frontend/src/pages/PMCommandCenter.tsx`, `frontend/src/pages/SprintBoardPage.tsx`.
- **Capacidades:** `links.item`, `links.mr`, `links.commit`, `links.pipeline`, `links.epic`.
- **Restricción dura:** las rutas REST `by-ado` **se mantienen** (alias) y se agregan las neutrales — P6, backward-compatible. **Nada de renombrar campos** `ado_*` en el frontend: se adopta `trackerVocabulary.ts` (218 F5) donde toque, gradualmente.
- **Nota de testing:** el frontend **no tiene jsdom ni @testing-library** (verificado: ausentes de `node_modules`), por lo que los tests de este subplan deben ser de **lógica pura** (`.test.ts`), no de componentes (`.test.tsx`). Ver memoria `gotcha-rtl-jsdom-structural-gap`.

---

**233 — Banco de pruebas cross-proveedor: servidor falso + E2E**
- **Objetivo:** un doble de servidor ADO y uno de GitLab, en proceso, que permitan E2E reales sin red y sin credenciales.
- **Gap que cierra:** hoy no hay forma de probar un flujo completo de GitLab. Es el equivalente multi-proveedor del Plan 183 (sandbox demo del comparador con par SQLite en 1 click).
- **`owns_files`:** `backend/tests/e2e/` (paquete nuevo), `backend/services/provider_sandbox.py` (nuevo).
- **Capacidades:** ninguna nueva (es infraestructura de prueba).
- **Criterio de aceptación:** un test E2E que, contra el servidor falso, hace: crear proyecto GitLab → sync → lanzar agente (runtime `mock`) → publicar → verificar comentario, **y el mismo test contra el servidor falso de ADO**.

---

**234 — Coexistencia y migración: dos trackers, cutover y rollback**
- **Objetivo:** operar con proyectos ADO y GitLab simultáneamente, y tener un cutover reversible.
- **Gap que cierra:** el Plan 65 §7 excluyó "multi-provider simultáneo"; el Plan 74 §6 excluyó "migración inversa" y "sincronización bidireccional". El migrador del 74 existe (`migrator_*.py`, `api/migrator.py`) pero es one-shot.
- **`owns_files`:** `backend/services/migrator_verify.py`, `backend/api/migrator.py`, `frontend/src/components/MigratorWizard.tsx`, `docs/_roadmap/RUNBOOK_CUTOVER_ADO_GITLAB.md` (nuevo).
- **Capacidades:** ninguna nueva.
- **Guardarraíl (P8 + excepción 2):** el cutover es **destructivo/irreversible** en su fase de corte ⇒ exige confirmación literal del operador y un dry-run previo obligatorio. Su flag nace **OFF** citando la **excepción dura 2**.

---

**235 — Tercer proveedor: kit de conformidad + adaptador de prueba**
- **Objetivo:** demostrar que agregar un proveedor no toca el núcleo, con un adaptador mínimo (GitHub Issues) que solo se usa en tests.
- **Gap que cierra:** la extensibilidad hoy es una afirmación sin evidencia.
- **`owns_files`:** `docs/_roadmap/KIT_NUEVO_PROVEEDOR.md` (nuevo), `backend/tests/contract/stub_provider.py` (nuevo).
- **Criterio de aceptación:** el adaptador stub pasa la suite de contrato de 218 F3 **sin modificar ni un archivo de `backend/services/` fuera del propio adaptador**. Si hay que tocar el núcleo, la abstracción falló y el subplan lo reporta como hallazgo.
- **Alcance explícito:** el adaptador **no se registra** en la fábrica de producción (queda en `tests/`), para no crear un prerequisito ni una superficie nueva.

---

**236 — Documentación viva y corpus RAG del modelo multi-proveedor**
- **Objetivo:** que la documentación del modelo multi-proveedor se genere desde la matriz y entre al corpus RAG.
- **Gap que cierra:** `docs/_roadmap/API_ENDPOINTS_MANTIS_GITLAB.md` es Mantis↔GitLab, no ADO↔GitLab; no hay documento de arquitectura multi-proveedor.
- **`owns_files`:** `docs/sistema/` (archivos nuevos del eje multi-proveedor), `backend/services/docs_rag_corpus.py`.
- **Restricción dura:** el corpus RAG bajo `docs/` debe ser `.jsonl`/`.json`/`.txt`, **nunca `.md`** (memoria `gotcha-docs-md-contaminates-doctree`).

### 5.3 Mapa de colisiones (archivos calientes y su dueño único)

| Archivo | Dueño único en esta serie | Quién más lo toca (y con qué regla) |
|---|---|---|
| `backend/api/tickets.py` (7245 líneas) | **221** | 220 toca **solo** `_sync_via_provider_or_ado`; 218 F6 toca **solo** el `raise` de esa función. Regla: anclar por texto, nunca por línea. |
| `backend/services/gitlab_provider.py` | **218 F0/F4** | 6 planes previos ya escribieron acá (65, 71, 72, 73, 75, 95). Después de F4, ningún subplan lo edita salvo para agregar un método declarado en su propio puerto. |
| `backend/services/tracker_provider.py` | **218 F0/F4/F6** | Ningún subplan cambia `PORT_METHODS` sin renegociar §3.1 acá. |
| `backend/services/ci_provider.py` (contrato congelado por el 71, extendido por el 72) | **226** | Si 226 agrega un 4.º método, debe actualizar `test_plan72_ci_provider_trigger_port.py:127` en el mismo commit. |
| `backend/api/__init__.py` | **218 F8** fija el patrón | Todo subplan que registre blueprint usa `url_prefix="/api"` + ruta sin `/api` (evita el `/api/api/` que hizo rechazar a los planes 72, 73 y 74). |
| `backend/services/client_profile.py` / `state_flow` | **Plan 216** (externo a esta serie) | 224 lo **consume**, no lo modifica. |
| `backend/services/integration_breaker.py` | **231** | 218 F6 lo reusa sin editarlo. |
| `frontend/src/pages/TicketBoard.tsx`, `UnblockerPage.tsx` | **232** | Advertencia: hay cambios sin commitear de una sesión paralela sobre estos archivos (ver `git status`); coordinar antes de tocar. |

### 5.4 Hitos y orden canónico

| Hito | Contenido | Gate de salida (binario) |
|---|---|---|
| **M0 — Sustrato** | 218 F0..F8 | Los 9 comandos de test de §4 verdes; `GET /api/parity/matrix` responde 200; ratchet de acoplamiento congelado. |
| **M1 — GitLab usable** | 219, 220, 221 | Un proyecto GitLab creado desde la UI sincroniza issues y lanza un agente end-to-end contra el sandbox de 233 (o una instancia real). K1 = 100 %. |
| **M2 — Escritura y dominio** | 222, 223, 224 | Publicar, asignar y crear jerarquía en GitLab pasan el contrato. K6 baja de 10 a ≤ 5. |
| **M3 — DevOps completo** | 226, 227, 228, 230 | Todas las capacidades `ci.*`, `repo.*`, `mr.*` en estado `full` o `partial` **con pérdida declarada** en ambos proveedores. |
| **M4 — Operación** | 225, 229, 231, 232, 233 | E2E de los 2 proveedores verde; telemetría discrimina `provider`; UI sin literales de organización hardcodeados. |
| **M5 — Extensibilidad** | 234, 235, 236 | El stub del 235 pasa el contrato sin tocar el núcleo; runbook de cutover ejecutado en dry-run. |

---

## 6. Matriz de paridad funcional (estado inicial verificado)

Esta es la carga inicial de `CAPABILITY_MATRIX` (218 F2). Se muestra condensada por dominio; el artefacto generado (`docs/_roadmap/PARIDAD_ADO_GITLAB.md`) la lista clave por clave con su `evidence`.

| Dominio | Capacidad | ADO | GitLab | Pérdida declarada / evidencia | Subplan dueño |
|---|---|---|---|---|---|
| tracker | `items.list` | full (`ado_client.py:319` WIQL) | full (`gitlab_provider.py:153`) | ADO usa WIQL; GitLab no tiene equivalente de query guardada | 220 |
| tracker | `items.create` / `items.get` / `items.update_state` | full | full | — | — |
| tracker | `items.update_assignee` | full (`ado_provider.py:105`) | **partial** | GitLab borra el asignado si el usuario no resuelve (`gitlab_provider.py:368-369`) | 223 |
| tracker | `items.url` | full (`ado_provider.py:69`) | **partial** | GitLab devuelve `None` con deep links OFF, violando `-> str` (`gitlab_provider.py:174`) | 218 F0 / 232 |
| tracker | `states.list` | full (`ado_client.py:393`) | **partial** | GitLab devuelve 4 claves lógicas hardcodeadas, no estados reales (`gitlab_provider.py:82-90,212`) | 224 |
| tracker | `types.list` | full (`ado_client.py:416`) | **absent** | GitLab no tiene tipos; se emulan con etiquetas `type::*` (`gitlab_provider.py:43`) | 224 |
| tracker | `comments.list_all` | full (`ado_client.py:796`, paginado + marker) | **partial** | GitLab no acepta `marker` y es idéntico a `fetch_comments` (`gitlab_provider.py:291`) | 222 |
| tracker | `comments.idempotent` | full (`ado_client.py:836`) | full (`gitlab_provider.py:305`) | — | — |
| tracker | `attachments.list` | full (`ado_client.py:458`, `$expand=relations`) | **partial** | GitLab no tiene modelo de relaciones: regex sobre la descripción (`gitlab_provider.py:350`) | 222 |
| tracker | `hierarchy.find_child` | full (`ado_client.py:878`) | **partial** | GitLab devuelve el **padre** como proxy (`gitlab_provider.py:403`) | 224 |
| tracker | `epics.create_native` | full | **partial** | GitLab requiere Premium; fallback a issue-links (`gitlab_provider.py:102-128`) | 224 |
| tracker | `sync.full` | full (`ado_sync.py:102`) | **absent** | `api/tickets.py:692` levanta excepción | **220** |
| tracker | `sync.incremental` | **partial** (`ado_sync.py:235`) | absent | — | 220 |
| tracker | `iterations.list` | full (`services/pm/ado_pm_collector.py:8`) | **absent** | GitLab usa milestones, no iteration paths | 224 |
| tracker | `milestones.list` | absent | **partial** (`gitlab_provider.py:54-55`, solo filtro) | Sin CRUD en ninguno | 224 |
| repo | `file.commit` | full (`ado_provider.py:146`) | full (`gitlab_provider.py:590`) | — | — |
| repo | `file.read` / `branch.*` / `commit.list` / `tag.create` | **absent** | **absent** | Ningún puerto los expone hoy | **227** |
| mr | `create`/`get`/`list`/`comment`/`close`/`merge` | full (`ado_provider.py:265-475`) | full (`gitlab_provider.py:624-777`) | — | — |
| mr | `diff` | **partial** | full (`gitlab_provider.py:733`) | ADO: `diff_available=False` (`ado_provider.py:455-457`) | **228** |
| mr | `approve` | **absent** (`ado_provider.py:476`) | full (`gitlab_provider.py:777`) | Detectado por `hasattr` (`api/pr_review.py:368`) | 228 |
| mr | `reviewers` / `policies` | absent | absent | — | 228 |
| ci | `pipeline.infer` | **partial** (`ado_pipeline_inference.py`, es inferencia LLM) | full (`gitlab_ci_provider.py:32`, pipelines reales) | Semánticas distintas bajo el mismo método | 226 |
| ci | `pipeline.trigger` / `monitor` | full (`ado_ci_provider.py:54,25`) | full (`gitlab_provider.py:522,545`) | GitLab **roto por D3** hasta 218 F0 | 218 F0 |
| ci | `definition.find` / `definition.ensure` | full (`ado_pipeline_definitions.py:82,125`) | **n/a** | GitLab no tiene objeto "definition": commitea `.gitlab-ci.yml` | 226 |
| ci | `jobs.failed` / `job.log` | full (`ado_ci_logs.py:25,49`) | full (`gitlab_ci_logs.py:14,27`) | ADO expone id compuesto `build:log` (`ado_ci_logs.py:39`) | 231 |
| ci | `variables.list/set/delete` | **roto** (`ado_variables.py:14` liga `_request` sin bind) | **roto** por D3/D4 | Ambos lados rotos | 218 F0 + 226 |
| ci | `variables.masked` | **absent** (`ado_variables.py:44` lo declara) | full | ADO no tiene masking | 226 |
| ci | `artifacts.*` / `environments.list` / `approvals` | **absent** | **absent** | — | **226** |
| identity | `me` | full (`ado_identity.py:126`) | **partial** (`gitlab_provider.py:144`, sin caché ni mapa) | — | 223 |
| identity | `user.find` / `members.list` / `groups.list` / `token.scopes` | absent | absent | — | 223, 230 |
| events | `webhook.inbound` / `verify` | **absent** | **absent** | Solo hay webhooks salientes (`services/webhooks.py`) | **229** |
| links | `item`/`mr`/`commit`/`pipeline`/`epic` | **partial** (solo `item`, `ado_provider.py:69`) | full (`gitlab_deep_links.py`, 11 funciones) | ADO no tiene módulo de deep links | 232 |

---

## 7. Estrategia de pruebas

| Nivel | Qué cubre | Dónde vive | Comando |
|---|---|---|---|
| **Unitario (puro)** | `provider_capabilities`, `tracker_vocabulary`, `provider_coupling_audit`, `parity_series`, `parityMatrixModel.ts` | `backend/tests/test_plan218_*.py`, `frontend/src/services/__tests__/*.test.ts` | pytest por archivo / `npx vitest run <archivo>` |
| **Contrato conductual (el corazón)** | El mismo cuerpo de test contra los 2 providers reales, con transporte falso | `backend/tests/contract/` + `test_plan218_tracker_contract.py` | `pytest ... test_plan218_tracker_contract.py -q` |
| **Integración (Flask test client)** | Endpoints con provider falso: `/api/tickets/sync`, `/api/parity/matrix` | `backend/tests/test_plan218_capability_unavailable.py`, `..._parity_endpoint.py` | pytest por archivo |
| **E2E (sin red)** | Flujo completo contra servidor falso, los 2 proveedores | `backend/tests/e2e/` (subplan **233**) | pytest por archivo |
| **Regresión ADO** | Que nada de ADO cambie | Suites existentes: `test_ado_provider.py`, `test_ado_client_stacky_name_resolution.py`, `test_plan70_group_*.py`, `test_plan95_*.py` | pytest por archivo, obligatorio en cada fase que toque un seam compartido |
| **Compatibilidad flag ON/OFF** | Que OFF sea byte-idéntico | Un test `_flag_off_*` por cada fase con flag (F2, F4, F5, F6, F8) | incluido en cada archivo |
| **Ratchets (anti-regresión estructural)** | Acoplamiento (F1), matriz sincronizada (F2), no mockear seams (F3), sin `NotImplementedError` en `api/` (F6), colisiones de la serie (F7), deuda de UI | `test_plan218_coupling_ratchet.py`, `..._capability_matrix.py`, `..._tracker_contract.py`, `..._capability_unavailable.py`, `..._serie_integridad.py`, `frontend/src/__tests__/uiDebtRatchet.test.ts` | pytest por archivo / vitest |
| **Smoke real (opcional, HITL)** | Contra una instancia GitLab real del operador | Manual, documentado en el subplan 233 | — |

**Regla de oro de esta estrategia (P4):** un test que parchea `config`, `services.gitlab_provider.config` o `GitLabTrackerProvider` **no cuenta** como evidencia de paridad. El centinela `test_ningun_test_de_contrato_parchea_config_ni_provider` (F3) lo hace cumplir.

---

## 8. Observabilidad, errores, seguridad, despliegue gradual y rollback

**Observabilidad.** Toda operación contra un tracker emite la dimensión `provider` (valor real, no el default `"ado"` que hoy usan `ado_publisher.py:73` y `api/tickets.py:6323,6336`). El endpoint `GET /api/parity/matrix` es la fuente de verdad de estado. El breaker existente (`integration_breaker.py`, Plan 148) se reusa por proveedor — no se crea otro mecanismo. La telemetría se apoya en lo que ya existe (Planes 171 y 199), sin tabla nueva.

**Manejo de errores.** Jerarquía única: `TrackerError` → `TrackerConfigError` (config/credenciales) · `TrackerApiError` (con `status` y `kind` ∈ `auth|not_found|rate_limited|server|unknown`) · **`CapabilityUnavailable`** (nuevo, 218 F6: no es un bug, es un límite del proveedor). Prohibido dejar `NotImplementedError` en `backend/api/**` (centinela en F6). El contrato de F3 exige que un ítem inexistente levante `TrackerApiError(kind="not_found")` en **ambos** proveedores, y que el 429 con `Retry-After` hostil no bloquee el hilo (hoy GitLab no clampea, `gitlab_client.py:146-147`; ADO sí, `ado_client.py:49`).

**Seguridad.** Ningún token en logs (`gitlab_preflight.py:16-27` ya redacta `PRIVATE-TOKEN`/`Authorization`: ese patrón se generaliza en el subplan 230). Credenciales cifradas en reposo con el backend enchufable de `secrets_store.py`. `secret_scanner.py` gana la regla de token GitLab. El endpoint de paridad tiene un test que verifica que no filtra secretos. **P9 se respeta**: "permisos" = leer los scopes del propio token para avisar antes de fallar, nunca RBAC.

**Despliegue gradual.** Tres niveles, en este orden de evaluación (`parity_rollout.capability_enabled`): (1) flag maestra `STACKY_PROVIDER_PARITY_ENABLED`; (2) status de la capacidad en la matriz; (3) override opcional por proyecto en `issue_tracker.parity_overrides`. Un proyecto puede quedarse en el comportamiento viejo sin afectar a los demás.

**Rollback.** Por capas, de la más barata a la más cara:
1. `STACKY_PROVIDER_PARITY_ENABLED=false` → desaparece toda la superficie del 218 (endpoint, panel, degradación consultiva); el resto sigue igual.
2. `STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED=false` → vuelve la resolución global de GitLab.
3. `STACKY_CANONICAL_VOCABULARY_ENABLED=false` → vuelve el payload legacy exacto.
4. `STACKY_CAPABILITY_DEGRADATION_ENABLED=false` → vuelven las excepciones legacy.
5. `STACKY_GITLAB_ENABLED=false` (default de fábrica) → GitLab entero desaparece; Stacky queda exactamente como está hoy.
Las correcciones de F0 **no tienen rollback por flag y no deben tenerlo**: revertirlas sería restaurar 4 defectos. Su kill-switch es el nivel 5.

---

## 9. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| **R1** | Planificar sobre encabezados de documento desactualizados (§2.4: 5 planes dicen PROPUESTO con el código ya escrito) ⇒ trabajo duplicado | Alta | Alto | F1 (censo ejecutable) + F7 (`test_docs_existentes_coinciden`). Cada subplan arranca midiendo el código, no leyendo prosa. |
| **R2** | `api/tickets.py` (7245 líneas) editado en paralelo por otra sesión ⇒ conflicto o commit que se lleva trabajo ajeno | Alta | Alto | Anclar por texto, nunca por línea. `git worktree list` antes de tocar. `git commit -- "<ruta>"` con pathspec explícito. Prohibido `reset`/`amend`/`rebase` (memorias `parallel-session-confirmed-live` y `feedback_concurrent-branch-git-amend-hazard`). |
| **R3** | Los fixtures del contrato se desactualizan respecto de la API real ⇒ verde falso | Media | Alto | Cada fixture lleva `recorded_at` y la versión de API. El subplan 233 agrega el servidor falso y un smoke real opcional. La matriz declara que el contrato prueba **forma**, no disponibilidad del servicio. |
| **R4** | Explosión de flags (hoy ya hay ~10 relacionadas con GitLab/ADO) | Media | Medio | Este plan agrega **4** en total (F2/F8 comparten una) y define `parity_rollout` como único punto de evaluación. Ningún subplan agrega una flag por capacidad: usa `parity_overrides`. |
| **R5** | Renombrar campos `ado_*` rompe el frontend (495 usos en 88 archivos) | Media | Muy alto | P6: **prohibido renombrar** en esta serie. Solo alias aditivos (F5). Test que verifica que las 14 claves legacy de `to_dict()` siguen presentes. |
| **R6** | Registrar el blueprint de paridad con doble prefijo `/api/api/...` (hizo rechazar a los planes 72, 73 y 74) | Media | Medio | F8 incluye `test_ruta_registrada_sin_doble_prefijo` y fija el patrón para toda la serie en §5.3. |
| **R7** | GitLab Free vs Premium (épicas nativas) genera comportamiento distinto según licencia | Alta | Medio | La matriz marca `tracker.epics.create_native` como `partial` con la pérdida declarada; el fallback a issue-links ya existe (`gitlab_provider.py:102-128`) y el contrato prueba **los dos caminos**. |
| **R8** | Alcance que se desliza hacia RBAC al tocar "permisos/usuarios/grupos" | Media | Alto | P9 explícito en la ficha del subplan 223 y en §10 (fuera de scope). El test de F7 no admite capacidades fuera de `CAPABILITY_KEYS`, y no hay ninguna clave de autorización. |
| **R9** | Encender `STACKY_TICKETS_PROVIDER_ENABLED` (hoy OFF) destapa regresiones ADO latentes | Media | Alto | 221 lo enciende **después** de que el contrato de F3 esté verde con la flag ON, y con la batería `test_plan70_group_*.py` completa como gate. |
| **R10** | `id` vs `iid` de GitLab mal normalizado ⇒ enlaces rotos o duplicados | Media | Alto | Decisión congelada en la ficha 220: `external_id` = `iid`; el `id` global va en `fields`. El contrato de F3 lo verifica en `create_item` + `item_url`. |
| **R11** | El operador enciende GitLab sin token válido y ve errores confusos | Media | Bajo | `CapabilityUnavailable` + el panel de paridad de F8 + el doctor de conexiones (subplan 230) le dicen exactamente qué falta antes de intentar. |
| **R12** | La matriz se marca `full` por optimismo y la paridad vuelve a ser una promesa | Media | Muy alto | `test_contrato_cubre_toda_capacidad_full_o_partial` (F3): marcar `full` sin escenario de contrato deja el test **rojo**. |

---

## 10. Fuera de scope (explícito)

- **RBAC, roles, multiusuario o cualquier control de acceso dentro de Stacky.** Sigue siendo mono-operador (P9).
- **GraphQL de GitLab.** Solo REST v4 (decisión heredada del Plan 65 §7).
- **Migrar Jira y Mantis al puerto `TrackerProvider`.** `tracker_provider.py:122-124` los rechaza a propósito; el Plan 217 confirma la decisión y resuelve Mantis con un adaptador de lectura propio.
- **Sincronización continua bidireccional ADO↔GitLab** (espejo permanente). El subplan 234 hace coexistencia y cutover, no espejo.
- **Auto-merge, merge-when-pipeline-succeeds y resolución de conflictos desde la UI.** Viola P8.
- **Migración de pipelines CI reales end-to-end** (parseo inverso de YAML arbitrario). El Plan 73 §6 lo excluye y este plan no lo reabre.
- **Preservar autor y fecha originales al escribir en el destino.** Límite de la API salvo impersonación con token admin; se mitiga con cabecera de procedencia (patrón del Plan 217 §6).
- **Renombrar columnas de la BD o campos del contrato JSON.** Solo alias aditivos (P6).
- **Implementar código en esta corrida.** El entregable de 218 es este documento; F0..F8 los ejecuta `implementar-plan-stacky`.

---

## 11. Glosario

- **Puerto (Port):** `typing.Protocol` que define el contrato de comportamiento de un dominio, sin mencionar proveedor. Ej.: `TrackerProvider` (`tracker_provider.py:56`).
- **Adaptador (Adapter):** implementación concreta de un puerto para un proveedor. Ej.: `AdoTrackerProvider`, `GitLabTrackerProvider`.
- **Fábrica (Factory):** función que elige el adaptador según el proyecto activo. Ej.: `get_tracker_provider` (`tracker_provider.py:105`).
- **Capacidad (Capability):** unidad mínima de funcionalidad, identificada por una clave estable como `mr.approve`. Su estado por proveedor vive en `CAPABILITY_MATRIX`.
- **Matriz de paridad:** tabla capacidad × proveedor con estado `full`/`partial`/`absent`/`n/a` y la pérdida declarada cuando es `partial`.
- **Test de contrato conductual:** un único cuerpo de test que se ejecuta contra **todos** los adaptadores de un puerto, mockeando solo el transporte HTTP. Distinto de la "conformance estructural", que solo verifica que los métodos existan.
- **Ratchet:** test que congela una métrica y falla si empeora (solo puede mejorar). Ej.: `HARNESS_TEST_FILES`, `uiDebtRatchet`, y el censo de acoplamiento de F1.
- **Degradación declarada:** informar de antemano que una capacidad no existe (`CapabilityUnavailable`), en vez de descubrirlo por una excepción a mitad del flujo.
- **HITL (human-in-the-loop):** toda acción de impacto pasa por confirmación explícita del operador. Riel innegociable de Stacky.
- **Runtimes:** Codex CLI, Claude Code CLI y GitHub Copilot Pro — los tres motores de ejecución de agentes, que consumen el mismo contexto.
- **`iid` vs `id` (GitLab):** el `iid` es el número visible dentro del proyecto (el del `#123` y de las URLs); el `id` es global de la instancia. Confundirlos rompe enlaces y jerarquías.
- **WIQL:** Work Item Query Language de Azure DevOps. No tiene equivalente en GitLab.
- **Marcador (marker):** cadena embebida en un comentario o descripción que permite reconocer que Stacky ya escribió eso (base de la idempotencia).
- **Outbox:** cola persistida de escrituras pendientes al tracker, con reintentos y backoff (`ado_write_outbox.py`).
- **Instancia vs módulo `config`:** `config.py` define `class Config` y crea la instancia en `config.py:1631` (`config = Config()`). Leer una flag del **módulo** devuelve el default y mata la rama; hay que leerla de `config.config`. Causa raíz de D1 y D2.

---

## 12. Orden de implementación

1. **218 F0** — Prueba de vida (los 4 defectos + centinela `getattr(config,`). *Sin esto nada de lo demás corre.*
2. **218 F1** — Censo + ratchet de acoplamiento (congela la deuda antes de empezar).
3. **218 F2** — Registro de capacidades + matriz generada.
4. **218 F3** — Suite de contrato conductual (y corregir el test mentiroso de conformance).
5. **218 F4** — Destino por proyecto + `client_profile_defaults/gitlab.json`.
6. **218 F5** — Vocabulario canónico con alias.
7. **218 F6** — `CapabilityUnavailable` + degradación en el endpoint de sync.
8. **218 F7** — Catálogo de la serie + tests de integridad y colisiones.
9. **218 F8** — Rollout por capacidad, endpoint y panel de paridad.
10. **219** → **220** → **221** (hito M1: GitLab usable de punta a punta). *Aquí se mide K1 = 100 %.*
11. **222**, **223**, **224** (M2), en ese orden.
12. **226**, **227** → **228**, **230** (M3). 227 antes que 228 (el MR necesita ramas).
13. **225**, **229**, **231**, **232**, **233** (M4). 233 puede adelantarse si se necesita el sandbox antes.
14. **234**, **235**, **236** (M5).

---

## 13. Definición de Hecho (DoD) global del Plan 218

- [ ] Los 4 defectos D1..D4 corregidos; `test_plan218_gitlab_reachable.py` verde con 9 tests; `grep -rn "getattr(config, \"STACKY" backend/services backend/api` devuelve 0 líneas.
- [ ] `provider_coupling_audit.scan_backend_coupling()` corre y `test_plan218_coupling_ratchet.py` está verde con la línea base congelada en `backend/tests/provider_coupling_baseline.json`.
- [ ] `provider_capabilities.CAPABILITY_MATRIX` cargada con las 2 columnas completas; `docs/_roadmap/PARIDAD_ADO_GITLAB.md` **generado** y sincronizado (test de sincronía verde).
- [ ] La suite de contrato corre contra los 2 adaptadores reales; ninguna capacidad marcada `full`/`partial` queda sin escenario; el centinela anti-mock está verde; `test_tracker_provider_conformance.py` ya no contiene la cadena `"no que esté hardcoded NotImplementedError"`.
- [ ] `build_tracker_target()` resuelve destino por proyecto; existe `backend/services/client_profile_defaults/gitlab.json`; dos proyectos GitLab distintos conviven en una misma corrida de test.
- [ ] `Ticket.to_dict()` emite claves canónicas **y** las 14 legacy; `npx tsc --noEmit` limpio.
- [ ] `CapabilityUnavailable` existe, se traduce a HTTP 200 con `available:false`, y `grep -c "NotImplementedError" backend/api/tickets.py` = 0.
- [ ] `docs/_roadmap/serie_paridad_218.json` con 18 subplanes; `test_plan218_serie_integridad.py` verde (sin ciclos, sin colisiones de propiedad, sin capacidad huérfana).
- [ ] `GET /api/parity/matrix` responde 200 con todas las capacidades; el panel se ve en Diagnósticos; `uiDebtRatchet` verde; 0 ocurrencias de `style={{` en el componente nuevo.
- [ ] Las 4 flags nuevas están en los 5 lugares de la receta y `test_harness_flags.py` verde; con `STACKY_PROVIDER_PARITY_ENABLED=false` el comportamiento es byte-idéntico al previo.
- [ ] Todos los `test_plan218_*.py` registrados en `HARNESS_TEST_FILES` de `run_harness_tests.sh` **y** `run_harness_tests.ps1`; `test_harness_ratchet_meta.py` verde.
- [ ] Regresión ADO verde por archivo: `test_ado_provider.py`, `test_ado_client_stacky_name_resolution.py`, `test_tracker_factory.py`, `test_plan70_group_sync.py`, `test_plan95_mr_providers.py`.
- [ ] Ningún criterio binario de F0–F8 en rojo; el encabezado de este documento actualizado a IMPLEMENTADO.

---

## Changelog de este documento

- **v1 (2026-07-25)** — Versión inicial. Relevamiento con evidencia `archivo:línea` de todo el acoplamiento ADO del backend y del frontend; **4 defectos del camino GitLab reproducidos por ejecución** (D1..D4, §2.1); 3 bloqueos estructurales (§2.2); doctrina de normalización en 3 capas (§3.1); 9 fases de sustrato (F0..F8); catálogo de 18 subplanes 219..236 con mapa de colisiones ejecutable (§5); matriz de paridad inicial verificada (§6). Pendiente: pasar por `criticar-y-mejorar-plan`.
