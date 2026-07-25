# Plan 218 — Paridad total Azure DevOps ↔ GitLab: plan ORQUESTADOR de la serie multi-proveedor

**Estado:** **IMPLEMENTADO (F0..F8) — 2026-07-25.** 81 tests verdes en 9 archivos + 14 tests de frontend + `tsc --noEmit` limpio. Ver §15 (reporte de implementación). El catálogo §5 (subplanes 219..236) queda materializado en `docs/_roadmap/serie_paridad_218.json` y validado por tests; los subplanes **no** se implementan acá.
_v2 — CRITICADO (v1 RECHAZADO) → APROBADO-CON-CAMBIOS_
**Autor:** generado con Claude Code (Opus 5) a pedido del operador (Juan Luca Santoliquido), 2026-07-25 · **criticado y reescrito a v2 el 2026-07-25** (`criticar-y-mejorar-plan`)
**Tipo:** plan orquestador (hoja de ruta ejecutable) — define el sustrato técnico + los 18 subplanes 219..236
**Precedentes directos:** 65, 70, 71, 72, 73, 74, 75, 95 (serie GitLab) · 184, 195, 197 (planes hoja-de-ruta previos, cuyo formato se reusa) · 217 (migrador Mantis→GitLab, adyacente)

> **Nota de versión (v1 → v2).** El v1 fue **RECHAZADO** por 5 hallazgos BLOQUEANTES: tres criterios de aceptación **imposibles de cumplir** (F0, F3, F6), una **inversión de dependencia** (F3 usaba una clase creada en F6) y una **contradicción interna** (el ratchet de F1 se rompía al implementar F2). El más grave: el centinela de F0 exigía 0 coincidencias de `getattr(config,` con allowlist vacía, cuando hay **69 coincidencias reales** y **~65 son correctas** (esos módulos bindean `config` a la *instancia* vía `from config import config`); aplicar el "fix" que el centinela exigía habría introducido ~65 defectos nuevos y roto el motor de flags. El v2 corrige los 12 hallazgos accionables y agrega 2 mecanismos nuevos marcados **[ADICIÓN ARQUITECTO]**. Detalle en el Changelog (§14).

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
| K2 | Módulos no-test que importan `services.ado_*` directo | **36 archivos** (64 ocurrencias) | ≤ 6 archivos (los 5 adaptadores + `project_context`) | `provider_coupling_audit.scan_backend_coupling()["ado_importer_files"]` |
| K3 | Líneas con `_ado_client_for_ticket(` en `api/tickets.py` | **20** (verificado 2026-07-25) | 1 (solo la línea de la definición) | `(Select-String -Path "Stacky Agents/backend/api/tickets.py" -Pattern "_ado_client_for_ticket\(" -AllMatches).Count` |
| K4 | Líneas con el literal `"azure_devops"` en backend no-test | **82 líneas en ~33 archivos** (re-medido en la crítica v2; el v1 decía 85) | ≤ 20 (adaptadores + factories + defaults) | censo F1, clave `tracker_literal_occurrences` |
| K5 | Capacidades del puerto verificadas por contrato conductual en AMBOS proveedores | **0** (la "conformance" actual solo hace `hasattr`/`callable`; §2.3) | ≥ 40 capacidades | `test_plan218_tracker_contract.py` |
| K6 | Dominios funcionales sin puerto formal | **10** (sync, publicación, contexto, outbox, identidad, edit-learning, read-cache, feedback, definiciones CI, PM/sprints) | 0 | matriz §6 |
| K7 | Defectos vivos del camino GitLab | **4 probados** (§2.1) | 0 | F0 |
| K8 | Tests que mockean el seam que deberían ejercitar | **3 identificados** (`test_tracker_factory.py:44-47`, `test_gitlab_provider.py:16`, `test_plan94_variables_providers.py:20`) | 0 | F0 + F3 |
| K9 | **Módulos que leen una flag del MÓDULO `config` (rama muerta garantizada)** — [ADICIÓN ARQUITECTO 1] | **2 archivos / 5 sitios** (`gitlab_provider.py:34,35,38,39` + `tracker_provider.py:111`), medidos con resolución de binding por AST sobre 69 candidatos textuales | 0, congelado por ratchet | `flag_binding_audit.scan()` (F0) |
| K10 | **Gaps de paridad con dueño declarado y test que se rompe si alguien los arregla en silencio** — [ADICIÓN ARQUITECTO 2] | **0** (hoy los gaps viven en prosa) | = nº de capacidades `absent`/`partial` de §6 | `KNOWN_GAPS` + `xfail(strict=True)` (F3) |

---

## 2. Por qué ahora / gap que cierra (evidencia real)

### 2.1 Los 4 defectos que hacen que GitLab NO EXISTA hoy (probados por ejecución)

| # | Defecto | Evidencia | Consecuencia |
|---|---|---|---|
| **D1** | `tracker_provider.py:111` hace `getattr(config, "STACKY_GITLAB_ENABLED", False)` sobre el **módulo** (importado en `:102`), pero la flag vive en `class Config` (`config.py:1170`) y la instancia se crea recién en `config.py:1631` (`config = Config()`). | **Ejecutado en esta sesión:** `hasattr(config,'STACKY_GITLAB_ENABLED')` → `False`; con `STACKY_GITLAB_ENABLED=true` en el entorno, `config.config.STACKY_GITLAB_ENABLED` → `True` pero `get_tracker_provider('DEMO')` → `TrackerConfigError: "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"`. | **GitLab es inalcanzable por la fábrica oficial, siempre.** Es la memoria `gotcha-config-config-vs-modulo-tickets` materializada en el seam más caro del repo. Las fábricas hermanas lo hacen bien: `ci_provider.py:121`, `ci_logs_provider.py:38`, `ci_variables.py:82` usan `_config.config`. |
| **D2** | `gitlab_provider.py:34,35,38,39` leen `GITLAB_URL`, `GITLAB_PROJECT`, `STACKY_GITLAB_GROUP`, `STACKY_GITLAB_EPICS_NATIVE` del **módulo** `config`. Verificado: `hasattr(config,'GITLAB_URL')` → `False`. En el mismo archivo, `:174,184,194,205` sí usan `config.config`. | Ejecución de esta sesión. | `self._group` y `self._epics_native` quedan **permanentemente** `""`/`False`: épicas nativas y `epic_url` (`gitlab_provider.py:199-209`) están muertas. `GITLAB_URL`/`GITLAB_PROJECT` sobreviven solo porque `gitlab_client.py:56,59` cae a `os.getenv`. |
| **D3** | `GitLabTrackerProvider.__init__` tiene firma `(self, project=None)` (`gitlab_provider.py:33`), pero se construye con el kwarg inexistente `project_name=` en `gitlab_ci_provider.py:30` y `gitlab_variables.py:13`. | Verificado con `inspect.signature` en esta sesión. | **`TypeError` en construcción**: el proveedor CI de GitLab y el de variables de GitLab están muertos al instante. |
| **D4** | `gitlab_variables.py:28` llama `_request_paginated("GET", path)` (2 posicionales) contra `(self, path, *, params, page_cap)`; `:80,:90` pasan `json=` contra el kwarg real `json_body=`. | Verificado con `inspect.signature` en esta sesión. | `list_variables` y `set_variable` de GitLab levantan `TypeError`. |

> **Corrección de la crítica v2 — alcance REAL de la clase de defecto (medido, no estimado).** El v1 daba por hecho que "leer del módulo `config`" se podía cazar con el texto `getattr(config,`. **Falso, y peligrosamente falso:** hay **69 coincidencias** de `getattr(config,`/`getattr(_config,` en `backend/services` + `backend/api`, y **~65 son CORRECTAS**, porque en esos módulos el nombre `config` está bindeado a la **instancia** (`from config import config`) — verificado en `claude_code_cli_runner.py:49`, `context_enrichment.py:282`, `agent_contract.py:102`, `harness_flags.py:4077`, `harness_profiles.py:162`, `run_slots.py:21`, `doc_documenter.py:79`, `ado_context.py:235`. Reescribirlas a `config.config` (lo que exigía el centinela del v1) **rompería el motor de flags**: `Config` no tiene atributo `.config`. Lo que define el defecto **no es el texto, es el binding**: solo son bugs los módulos que hacen `import config` (el módulo) y leen la flag del nombre pelado — hoy exactamente **2**: `gitlab_provider.py` (`import config` en `:25`) y `tracker_provider.py` (`import config` en `:102`). El mismo `gitlab_provider.py` convive con lecturas correctas (`config.config` en `:174,184,194,205`), lo que prueba que ningún centinela textual puede decidir esto. De ahí el rediseño de F0 y la **[ADICIÓN ARQUITECTO 1]**.

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
| `CapabilityUnavailable(TrackerError)` y su payload | **218 F2** (v2: era F6; F3 lo necesita y F3 corre ANTES que F6 — ver C4) | `backend/services/tracker_provider.py` |
| Traducción HTTP de `CapabilityUnavailable` (200 + `available:false`) | 218 F6 | `backend/api/errors.py` |
| `TrackerTarget` (dataclass de destino resuelto por proyecto) | 218 F4 | `backend/services/project_context.py` |
| `CANONICAL_FIELDS` y el mapa de alias legacy | 218 F5 | `backend/services/tracker_vocabulary.py` |
| Firma de la suite de contrato `run_tracker_contract(make_provider, provider_name, fake)` | 218 F3 | `backend/tests/contract/provider_contract.py` |
| **`KNOWN_GAPS`** (capacidad → dueño + motivo del xfail) — [ADICIÓN ARQUITECTO 2] | 218 F3 | `backend/tests/contract/known_gaps.py` |
| **Regla de binding de flags** (`import config` ⇒ prohibido leer flags del nombre pelado) — [ADICIÓN ARQUITECTO 1] | 218 F0 | `backend/services/flag_binding_audit.py` |
| **Categoría de flags `paridad_proveedores`** (las 4 flags del plan viven ahí) | 218 F2 | `backend/services/harness_flags.py` |

---

## 4. Fases

> **Comando backend** (desde la raíz del repo, PowerShell): `& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>" -q` — **SIEMPRE por archivo**, nunca la suite completa (contaminación cross-run conocida; memorias `gotcha-config-reload-harness-flags-contamina` y `gotcha-vitest-test-order-pollution-frontend`). Variante equivalente usada por los planes 210/212/213/215/216: `cd "Stacky Agents/backend"` y luego `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q`.
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run <archivo>` + `npx tsc --noEmit`.
> **Registro obligatorio:** todo `backend/tests/test_*.py` nuevo se agrega como línea `  tests/<archivo>.py` (dos espacios de indentación, sin comentario en la misma línea) dentro de `HARNESS_TEST_FILES=(` en `backend/scripts/run_harness_tests.sh:20` **y** en `$HarnessTestFiles = @(` de `backend/scripts/run_harness_tests.ps1:13`, o `tests/test_harness_ratchet_meta.py:43` queda rojo.
> **Receta de flag default ON = 7 lugares** (v2: el v1 decía 5 y nombraba una categoría **inexistente**, ver C6). Las 20 categorías reales son `runtimes_cli`, `contexto_memoria`, `calidad_verificacion`, `integridad_grounding`, `epicas_ado`, `flujo_funcional`, `routing_costo`, `fiabilidad_ciclo_vida`, `observabilidad_notif`, `aprendizaje`, `preflight_intencion`, `base_datos`, `avanzado`, `migrador_ado_gitlab`, `gitlab_deep_links`, `devops`, `capacidades_optin`, `comparador_bd`, `interfaz_ui`, `otros` — **`integraciones` NO existe**. Este plan crea una categoría nueva:
> 1. **Crear la categoría** — `CategorySpec("paridad_proveedores", "Paridad de proveedores (ADO ↔ GitLab)", "Plan 218 — registro de capacidades, destino por proyecto, vocabulario canónico y degradación declarada del eje multi-proveedor.", tier="advanced", intent="Ver y controlar la paridad entre Azure DevOps y GitLab")` dentro de la tupla de `CategorySpec` de `services/harness_flags.py` (bloque `:55-115`), **antes** de la entrada `otros` (que es el fallback).
> 2. **Registrar la tupla de claves** — `"paridad_proveedores": ("STACKY_PROVIDER_PARITY_ENABLED", "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", "STACKY_CANONICAL_VOCABULARY_ENABLED", "STACKY_CAPABILITY_DEGRADATION_ENABLED"),` en `_CATEGORY_KEYS` (`harness_flags.py:117`). **Obligatorio:** `tests/test_harness_flags.py:739` (`test_every_registry_flag_is_categorized`) exige **biyección** registry ↔ `_CATEGORY_KEYS`; una flag sin categoría deja el test ROJO.
> 3. `FlagSpec(...)` en el registry de `services/harness_flags.py` (~`:379`).
> 4. La clave en `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`) — obligatorio para **toda** flag con `default=True`.
> 5. El atributo en `class Config` (`config.py`, leyendo de `os.getenv` con default `"true"`).
> 6. El read-site, **siempre** `config.config.<FLAG>` (o `from config import config` + `config.<FLAG>`; ver la regla de binding de F0).
> 7. Verificación: `& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -q` verde.
>
> **Regla de comandos (v2, C9):** el shell primario del repo es **PowerShell**, donde `grep`/`wc` no existen como cmdlets y el backtick `` ` `` es el carácter de escape. Todo criterio binario de este plan se expresa con `Select-String` / `Test-Path`. Equivalencias canónicas:
> - contar coincidencias → `(Select-String -Path "<ruta>" -Pattern "<regex>" -AllMatches | Measure-Object).Count`
> - contar en un árbol → `(Get-ChildItem "<dir>" -Filter *.py -Recurse | Select-String -Pattern "<regex>" | Measure-Object).Count`
> - "devuelve 0 líneas" → la expresión anterior `-eq 0`.
> Si el implementador prefiere Bash, el repo tiene Git Bash disponible y `grep -c` es válido allí — pero **el criterio de aceptación se declara en PowerShell** para que sea ejecutable en el shell por defecto.

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

8. **[ADICIÓN ARQUITECTO 1] `backend/services/flag_binding_audit.py` — crear.** Auditoría **AST** (no textual) que resuelve, por módulo, a qué está bindeado el nombre `config` y solo entonces decide si una lectura de flag es un defecto. Es la generalización permanente de la memoria `gotcha-config-config-vs-modulo-tickets`, y la única forma correcta de impedir que D1/D2 vuelvan (ver la corrección de §2.1 y C1).

```python
"""Auditoría de binding del nombre `config`. PURA (solo lee y parsea archivos, sin ejecutarlos)."""
from __future__ import annotations
import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("services", "api", "harness")

# Prefijos de atributos que son FLAGS/CONFIG de la instancia (no submódulos ni helpers).
_FLAG_PREFIXES = ("STACKY_", "GITLAB_", "ADO_", "CLAUDE_CODE_CLI_", "CODEX_CLI_", "COPILOT_", "LLM_")

def scan() -> dict:
    """Devuelve {"violations": [ {"file","line","name","attr","binding"} ], "violation_count": int,
                 "module_bound_files": [rutas que hacen `import config`]}

    Un sitio es VIOLACIÓN si y solo si:
      1) el nombre base (`config`, `_config`, `_cfg`, o el alias de `import config as X`)
         está bindeado en ese módulo por un `import config` / `import config as X`
         —es decir, apunta al MÓDULO—, y
      2) se lee de él un atributo que empieza con uno de _FLAG_PREFIXES,
         sea por `getattr(<name>, "FLAG", ...)` o por acceso directo `<name>.FLAG`,
      3) y el atributo leído NO es `config` (leer `config.config.FLAG` es CORRECTO).

    Un módulo que hace `from config import config` bindea la INSTANCIA: sus lecturas
    `config.FLAG` / `getattr(config, "FLAG", ...)` son CORRECTAS y NO se reportan.
    Ignora strings y docstrings por construcción (se camina el AST, no el texto).
    Salida ordenada por (file, line) — determinista."""

def render_report(scan_result: dict) -> str:
    """Reporte legible con archivo:línea y el binding detectado. PURA."""
```

**Por qué es una adición de alto valor y no scope creep:** el v1 ya quería este control (su `test_centinela_no_getattr_sobre_modulo_config`), pero lo especificó como regex, lo que lo hacía **inservible y destructivo** (69 candidatos, ~65 correctos). Esta versión (a) es correcta por construcción, (b) cubre también el acceso directo `config.FLAG` que el regex del v1 dejaba pasar, (c) barre `harness/` además de `services/` y `api/`, y (d) **puede descubrir ramas muertas más allá de GitLab** — cualquier flag leída del módulo es una rama que nunca se ejecuta. Si el barrido encuentra violaciones fuera de los 5 sitios conocidos, el implementador **NO las arregla en esta fase**: las deja registradas en el baseline y las reporta como hallazgo para un subplan propio (arreglar una flag muerta cambia comportamiento y necesita su propio análisis). Esto respeta P11 (no degradar) y evita que F0 se convierta en un refactor masivo.

**Tests PRIMERO — `backend/tests/test_plan218_gitlab_reachable.py`:**
- `test_config_module_no_expone_flags_de_instancia` — afirma `not hasattr(config, "STACKY_GITLAB_ENABLED")` y `hasattr(config.config, "STACKY_GITLAB_ENABLED")`. Documenta la causa raíz; **no** parchea nada.
- `test_factory_devuelve_gitlab_con_flag_on` — `monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", True)` (instancia, nunca el módulo), stub de `resolve_project_context` que devuelve `tracker_type="gitlab"`, y afirma `get_tracker_provider("DEMO").name == "gitlab"`. **Con el código actual este test es ROJO.**
- `test_factory_rechaza_gitlab_con_flag_off` — con la flag en `False`, sigue levantando `TrackerConfigError` (kill-switch intacto).
- `test_gitlab_provider_lee_group_y_epics_de_instancia` — con `config.config.STACKY_GITLAB_GROUP="g1"` afirma `provider._group == "g1"`.
- `test_gitlab_ci_provider_construye` — construye `GitLabCIProvider(project="grupo/proyecto")` sin `TypeError`.
- `test_gitlab_variables_provider_construye` — idem `GitLabVariablesProvider`.
- `test_gitlab_variables_list_usa_firma_real` — con un doble de `GitLabClient` que **valida la firma real** (`_request_paginated(path, *, params, page_cap)`), `list_variables()` no levanta `TypeError`.
- `test_gitlab_variables_set_usa_json_body` — el doble afirma que se recibió `json_body=` y no `json=`.
- ~~`test_centinela_no_getattr_sobre_modulo_config`~~ — **ELIMINADO en v2 (C1): era incorrecto y su "fix" habría roto el motor de flags.** Lo reemplazan los 5 tests siguientes, sobre `flag_binding_audit`:
- `test_audit_no_marca_binding_de_instancia` — un módulo sintético (escrito en `tmp_path`) con `from config import config` + `getattr(config, "STACKY_X", False)` produce **cero** violaciones. **Este test es el que impide que el centinela vuelva a ser destructivo.**
- `test_audit_marca_binding_de_modulo` — un módulo sintético con `import config` + `getattr(config, "STACKY_X", False)` produce **una** violación, con `file`/`line`/`attr` correctos.
- `test_audit_marca_acceso_directo` — `import config` + `if config.STACKY_X:` también se reporta (cobertura que el regex del v1 no tenía).
- `test_audit_no_marca_config_config` — `import config` + `getattr(config.config, "STACKY_X", False)` produce **cero** violaciones.
- `test_audit_del_repo_real_esta_en_cero_para_los_5_sitios_conocidos` — tras aplicar los fixes 1-6 de esta fase, `scan()` **no reporta** ningún sitio en `services/tracker_provider.py` ni en `services/gitlab_provider.py`. El resto del repo se congela en `backend/tests/flag_binding_baseline.json` (generado, ver criterio) con la regla `violation_count <= baseline` — ratchet, **no** exigencia de cero global.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_gitlab_reachable.py" -q`

**Generar el baseline del audit (una sola vez, ANTES de correr el ratchet):**
`cd "Stacky Agents/backend"; & ".venv\Scripts\python.exe" -c "import json,sys; sys.path.insert(0,'.'); from services.flag_binding_audit import scan; s=scan(); json.dump({'violation_count': s['violation_count']}, open('tests/flag_binding_baseline.json','w'), indent=2)"`
Y **dejar el reporte completo en el mensaje del commit** (`render_report`), para que quede la evidencia de qué flags muertas existen fuera del alcance de este plan.

**Criterio de aceptación (binario):** el comando de pytest verde con **13 tests** (8 de defectos + 5 del audit); `hasattr(config,'STACKY_GITLAB_ENABLED')` sigue siendo `False` (la causa raíz sigue documentada, no parcheada); y **cero violaciones del audit en los 2 archivos del seam**:
`cd "Stacky Agents/backend"; & ".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'.'); from services.flag_binding_audit import scan; v=[x for x in scan()['violations'] if 'tracker_provider' in x['file'] or 'gitlab_provider' in x['file']]; print(len(v)); sys.exit(0 if not v else 1)"` imprime `0` y sale con código 0.

**Huella de regresión (v2, C14 — convención de la casa):** esta fase mata 2 clases de error, así que registra sus huellas en `Stacky Agents/docs/sistema/error_fingerprints.json` (una entrada por clase, no una por defecto):
- `flag-leida-del-modulo-config` — patrón: módulo con `import config` que lee un atributo `STACKY_*`/`GITLAB_*` del nombre pelado ⇒ rama muerta silenciosa. `plan: 218 F0`, `guard_test: tests/test_plan218_gitlab_reachable.py::test_audit_marca_binding_de_modulo`, fecha `2026-07-25`.
- `kwarg-inexistente-en-constructor-de-provider` — patrón: construir un provider con un kwarg que su `__init__` no declara (D3/D4) ⇒ `TypeError` en el primer uso real, invisible si el test mockea el provider. `plan: 218 F0`, `guard_test: tests/test_plan218_gitlab_reachable.py::test_gitlab_ci_provider_construye`.

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

# v2 (C5): archivos NEUTRALES del sustrato 218 que nombran a los DOS proveedores por
# definición (son el registro, no un acoplamiento). Sin esto, implementar F2 después de
# F1 rompe el ratchet de literales: CAPABILITY_MATRIX tiene "azure_devops" como CLAVE.
NEUTRAL_REGISTRY_ALLOWLIST: frozenset[str] = frozenset({
    "services/provider_capabilities.py",   # F2 — la matriz
    "services/provider_coupling_audit.py", # F1 — este mismo censo
    "services/flag_binding_audit.py",      # F0 — el audit de binding
    "services/tracker_vocabulary.py",      # F5 — vocabulario canónico
    "services/parity_rollout.py",          # F8 — evaluación de capacidades
    "api/parity.py",                       # F8 — endpoint de solo lectura
})

def scan_backend_coupling() -> dict:
    """Devuelve (v2: nombres con UNIDAD explícita, C8):
    {
      "ado_importer_files": {"<ruta relativa>": <n ocurrencias en ese archivo>},
      "ado_importer_file_count": int,        # nº de ARCHIVOS (baseline 36)
      "ado_importer_occurrences": int,       # suma de ocurrencias (baseline 64)
      "tracker_literal_files": {"<ruta>": <n>},   # literal "azure_devops"
      "tracker_literal_file_count": int,     # nº de ARCHIVOS
      "tracker_literal_occurrences": int,    # nº de LÍNEAS con el literal (baseline 82)
      "ado_client_lines_in_tickets": int,    # LÍNEAS con '_ado_client_for_ticket(' en api/tickets.py
      "ado_route_count": int,                # rutas con 'by-ado'|'publish-to-ado'|'/ado-'
    }
    Excluye: backend/tests/**, backend/.venv/**, backend/venv/**, backend/services/ado_*.py,
    y —solo para `tracker_literal_*`— los archivos de NEUTRAL_REGISTRY_ALLOWLIST.
    Ordena las claves alfabéticamente (salida determinista)."""

def render_report_markdown(scan: dict) -> str:
    """Tabla Markdown del censo. PURA."""
```

2. `backend/tests/provider_coupling_baseline.json` — línea base congelada. **v2 (C8): se GENERA, no se transcribe** — los números del v1 ya estaban desactualizados (decía 85 literales; medido 2026-07-25: **82**). Comando de generación, a correr **una sola vez** antes de escribir el ratchet:
```
cd "Stacky Agents/backend"; & ".venv\Scripts\python.exe" -c "import json,sys; sys.path.insert(0,'.'); from services.provider_coupling_audit import scan_backend_coupling as s; d=s(); json.dump({k:v for k,v in d.items() if isinstance(v,int)}, open('tests/provider_coupling_baseline.json','w'), indent=2, sort_keys=True)"
```
Valores esperados al 2026-07-25 (referencia, **no** para hardcodear): `ado_importer_file_count` 36, `ado_importer_occurrences` 64, `tracker_literal_occurrences` 82, `ado_client_lines_in_tickets` 20, `ado_route_count` 19. Si el generado difiere en más de ±10 %, el implementador **para** y reporta: significa que el árbol cambió y el relevamiento de §2 necesita re-medirse.

**Tests PRIMERO — `backend/tests/test_plan218_coupling_ratchet.py`:**
- `test_scan_es_determinista` — dos llamadas consecutivas devuelven el mismo dict.
- `test_scan_excluye_tests_y_venv` — ninguna clave contiene `tests/`, `.venv/`, `venv/`.
- `test_scan_excluye_familia_ado` — ninguna clave empieza con `services/ado_`.
- `test_ratchet_importers_no_crece` — `scan["ado_importer_file_count"] <= baseline[...]`, con mensaje que lista los archivos nuevos.
- `test_ratchet_literales_no_crece` — idem para `tracker_literal_occurrences`.
- `test_ratchet_sitios_adoclient_no_crece` — idem para `ado_client_lines_in_tickets`.
- `test_ratchet_rutas_ado_no_crece` — idem para `ado_route_count`.
- `test_allowlist_de_adaptadores_es_exacta` — cada ruta de `ADAPTER_ALLOWLIST` existe en disco (no hay entradas fantasma).
- `test_allowlist_neutral_no_se_usa_para_esconder_acoplamiento` — **v2 (C5):** cada ruta de `NEUTRAL_REGISTRY_ALLOWLIST` (a) existe en disco **o** todavía no fue creada por su fase, y (b) **no** importa `services.ado_*` — la exención vale solo para el literal, nunca para el import. Un archivo "neutral" que importa el cliente de ADO deja el test ROJO.
- `test_reporte_markdown_tiene_todas_las_secciones` — `render_report_markdown` incluye las 5 métricas enteras.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_coupling_ratchet.py" -q`

**Criterio de aceptación (binario):** comando verde con **10 tests**; el baseline existe y fue **generado** por el comando de arriba (no transcrito); y agregar a mano un `from services.ado_client import AdoClient` en cualquier archivo no-allowlisteado hace **rojo** `test_ratchet_importers_no_crece` (verificación manual del implementador, documentada en el commit y **revertida** antes de commitear).

**Orden dentro de la serie (v2, C5):** F1 congela el baseline **antes** de que F2/F4/F5/F8 creen sus archivos. Cada una de esas fases, al crear un archivo que nombra a los dos proveedores, **debe** agregarlo a `NEUTRAL_REGISTRY_ALLOWLIST` en el mismo commit. Si una fase omite ese paso, `test_ratchet_literales_no_crece` queda rojo — que es el comportamiento deseado (fuerza la decisión explícita: ¿es registro neutral o es acoplamiento nuevo?).

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
    # transporte del tracker (v2, C3): transversales, no métodos del puerto, pero
    # sí comportamiento que el contrato de F3 exige y que hoy divergen entre proveedores.
    "tracker.rate_limit.clamp", "tracker.auth.html_redirect",
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

2. `docs/_roadmap/PARIDAD_ADO_GITLAB.md` — **generado** por `render_markdown_matrix()`, nunca editado a mano. **v2 (C16):** escribirlo con `newline="\n"` explícito y comparar **normalizando** los saltos de línea (`content.replace("\r\n", "\n")`), porque en Windows `core.autocrlf` puede reescribir el archivo al checkout y una comparación byte-a-byte cruda quedaría intermitentemente roja.

3. **`backend/services/tracker_provider.py` — agregar `CapabilityUnavailable` en esta fase (v2, C4: el v1 la creaba en F6, pero F3 la necesita y F3 corre antes).** Es una clase de error pura, sin dependencias, ~12 líneas:
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
F6 conserva **solo** la traducción HTTP (`api/errors.py`) y el cambio del call-site de sync. Definir la clase acá no cambia ningún comportamiento (nadie la levanta todavía), así que no necesita flag.

4. **`backend/services/harness_flags.py`** — crear la categoría `paridad_proveedores` (2 sitios: tupla de `CategorySpec` y `_CATEGORY_KEYS`) según la receta de 7 pasos de §4. Las 4 flags del plan se registran ahí.

**Valores iniciales verificados** (el implementador los carga tal cual; §6 tiene la tabla completa): `mr.approve` → ADO `absent` (`ado_provider.py:476` no lo define), GitLab `full` (`gitlab_provider.py:777`). `mr.diff` → ADO `partial`, `loss="diff_available=False; el operador abre la PR en el navegador"` (`ado_provider.py:455-457`), GitLab `full` (`gitlab_provider.py:733`). `tracker.sync.full` → ADO `full` (`ado_sync.py:102`), GitLab `absent` (`api/tickets.py:692`). `ci.pipeline.definition.ensure` → ADO `full` (`ado_pipeline_definitions.py:125`), GitLab `n/a` (GitLab no tiene objeto "definition": commitea `.gitlab-ci.yml`, `gitlab_provider.py:590`). `ci.variables.masked` → ADO `absent` (`ado_variables.py:44` lo declara), GitLab `full`. `tracker.epics.create_native` → ADO `full`, GitLab `partial` (requiere licencia Premium; fallback issue-links en `gitlab_provider.py:102-128`).

**Tests PRIMERO — `backend/tests/test_plan218_capability_matrix.py`:**
- `test_toda_clave_declarada_en_ambos_proveedores` — `set(CAPABILITY_MATRIX["azure_devops"]) == set(CAPABILITY_MATRIX["gitlab"]) == set(CAPABILITY_KEYS)`.
- `test_status_pertenece_al_vocabulario` — todo `status` ∈ `CAPABILITY_STATUSES`.
- `test_partial_exige_loss_no_vacio` — si `status == "partial"`, `loss` tiene ≥ 10 caracteres.
- `test_full_y_partial_exigen_evidencia` — si `status` ∈ {`full`,`partial`}, `evidence` matchea `^[\w/\.]+\.py:\d+$`.
- `test_supports_es_consistente` — `supports()` es `True` exactamente para `full`/`partial`.
- `test_render_es_determinista` — dos renders idénticos byte a byte.
- `test_doc_de_paridad_esta_sincronizado` — `docs/_roadmap/PARIDAD_ADO_GITLAB.md`, **normalizado a `\n`**, es exactamente `render_markdown_matrix()` normalizado. **Este test es el que impide que la matriz se pudra.**
- `test_claves_congeladas_no_se_renombran` — hash SHA-256 de `"\n".join(CAPABILITY_KEYS)` igual a la constante congelada `_KEYS_SHA` del propio test (renombrar una clave rompe a propósito).
- **`test_matriz_no_miente_estructuralmente`** — **[ADICIÓN ARQUITECTO 2, parte a]** detector de mentiras de la matriz en el eje **estructural** (el conductual lo cubre F3): para cada capacidad del dominio `tracker.*` que la matriz marca `full`/`partial`, el método correspondiente del puerto **existe y es callable** en ese adaptador; y para cada una marcada `absent`, **no existe** o `supports()` es `False`. El mapa capacidad→método vive en una constante `_CAPABILITY_TO_PORT_METHOD` del propio módulo, y un test verifica que todo valor de ese mapa esté en `PORT_METHODS` (`tracker_provider.py:56-98`). **Por qué importa:** sin esto la matriz se puede podrir en el sentido contrario al que cubre F3 — un subplan implementa `mr.approve` en ADO y nadie actualiza la matriz, así que la UI sigue ocultando una acción que ya funciona. Barato (puro `hasattr`, sin red) y cierra el lazo en los dos sentidos.
- `test_capability_unavailable_existe_y_es_subclase` — `issubclass(CapabilityUnavailable, TrackerError)` y `to_payload()` trae las 5 claves (movido desde F6, C4).

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q`
Y, por la categoría nueva de flags: `& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q`

**Criterio de aceptación (binario):** ambos comandos verdes, el primero con **10 tests**; y el documento generado tiene una fila por capacidad — verificable **en PowerShell** (v2, C9: el criterio del v1 usaba un backtick dentro de comillas dobles, que en PowerShell es el carácter de escape y no parsea):
```
cd "Stacky Agents"; $m = (Select-String -Path "docs/_roadmap/PARIDAD_ADO_GITLAB.md" -Pattern '^\| `' | Measure-Object).Count; $k = & "backend/.venv/Scripts/python.exe" -c "import sys; sys.path.insert(0,'backend'); from services.provider_capabilities import CAPABILITY_KEYS; print(len(CAPABILITY_KEYS))"; if ([int]$m -eq [int]$k) { "OK $m" } else { "FALLA: $m filas vs $k claves" }
```

**Flag:** `STACKY_PROVIDER_PARITY_ENABLED` (bool, default **True**, categoría **`paridad_proveedores`** — v2, C6: `integraciones` no existe). Default ON porque es un registro puro leído en proceso: no agrega red, ni prerequisitos, ni reduce seguridad, ni bypasea revisión humana. Con OFF, `supports()` devuelve `True` para todo (comportamiento pre-plan, byte-idéntico).

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
    """Parchea el ATRIBUTO urllib.request.urlopen (no un call-site).
    v2 (C13): el v1 decía 'ado_client.py:271,537'; los sitios reales son 4
    —273, 499, 539, 717— y enumerarlos es frágil. Parchear el atributo del
    módulo cubre los 4 y sobrevive a cualquier renumeración."""
def install_for_gitlab(monkeypatch, fake: FakeHttp) -> None:
    """Parchea el ATRIBUTO requests.request (usado en gitlab_client.py:135)."""
```
3. `backend/tests/contract/provider_contract.py`
```python
def run_tracker_contract(make_provider, provider_name: str, fake: FakeHttp) -> list[str]:
    """Ejecuta el contrato conductual del puerto contra un provider REAL.
    Devuelve la lista de capacidades verificadas (claves de CAPABILITY_KEYS).

    v2 (C4) — reglas por status, corregidas:
      * 'full'    → ejecuta su escenario y EXIGE el comportamiento neutral.
      * 'partial' → ejecuta su escenario; si la capacidad está en KNOWN_GAPS,
                    el escenario corre bajo xfail(strict=True) (ver known_gaps.py).
      * 'absent'  → afirma que la capacidad NO está disponible por la vía
                    consultiva: `supports(provider, cap) is False` y, si la
                    capacidad mapea a un método del puerto, `not hasattr(provider, m)`
                    o que el método declare su indisponibilidad.
                    NO se afirma que se levante CapabilityUnavailable: NINGÚN
                    adaptador la levanta (p.ej. `mr.approve` ausente en ADO es
                    simplemente un método que no existe, detectado hoy por
                    `hasattr` en api/pr_review.py:368). Exigirlo, como hacía el
                    v1, era pedir un cambio en los 2 adaptadores que el plan
                    nunca especificó.
      * 'n/a'     → se saltea con `pytest.skip` y motivo (no es un gap: el
                    proveedor no tiene ese concepto).
    """
```
4. **`backend/tests/contract/known_gaps.py`** — **[ADICIÓN ARQUITECTO 2, parte b] — el ratchet inverso de paridad.** Registro congelado de los gaps conductuales conocidos, con dueño. Resuelve C3: sin esto, F3 es **imposible de poner en verde**, porque ≥6 de sus escenarios describen comportamiento que GitLab hoy NO cumple y cuyo arreglo pertenece a subplanes posteriores.
```python
"""Gaps conductuales conocidos del contrato. CONGELADO por el Plan 218 (§3.1).
Cada entrada es una PROMESA con dueño: el subplan que la cierra la BORRA de acá."""
KNOWN_GAPS: dict[tuple[str, str], dict] = {
    # (provider, capability): {"owner_plan": int, "reason": str, "evidence": "archivo:línea"}
    ("gitlab", "tracker.items.url"): {
        "owner_plan": 232, "reason": "item_url devuelve None con deep links OFF, violando '-> str'",
        "evidence": "services/gitlab_provider.py:174"},
    ("gitlab", "tracker.comments.list_all"): {
        "owner_plan": 222, "reason": "fetch_all_comments es idéntico a fetch_comments y no acepta marker",
        "evidence": "services/gitlab_provider.py:291"},
    ("gitlab", "tracker.states.list"): {
        "owner_plan": 224, "reason": "devuelve 4 claves lógicas hardcodeadas, no estados reales",
        "evidence": "services/gitlab_provider.py:82"},
    ("gitlab", "tracker.hierarchy.find_child"): {
        "owner_plan": 224, "reason": "devuelve el padre como proxy del hijo",
        "evidence": "services/gitlab_provider.py:403"},
    ("gitlab", "tracker.items.update_assignee"): {
        "owner_plan": 223, "reason": "silencia el usuario inexistente y BORRA el asignado",
        "evidence": "services/gitlab_provider.py:368"},
    ("gitlab", "tracker.rate_limit.clamp"): {
        "owner_plan": 231, "reason": "no clampea Retry-After hostil (ADO clampea a 30 s)",
        "evidence": "services/gitlab_client.py:146"},
    ("gitlab", "tracker.auth.html_redirect"): {
        "owner_plan": 231, "reason": "devuelve texto crudo ante HTML de login en vez de error de auth",
        "evidence": "services/gitlab_client.py:164"},
}
```
**Cómo funciona el ratchet inverso:** cada escenario cuyo `(provider, capability)` está en `KNOWN_GAPS` corre con `pytest.mark.xfail(strict=True, reason=...)`. Consecuencias, las dos deseadas:
- Si el gap **sigue** roto → `xfail` → la suite queda **verde** y F3 es implementable hoy.
- Si un subplan lo **arregla** → `XPASS` → con `strict=True` eso es **FALLO**, y el único modo de volver al verde es **borrar la entrada de `KNOWN_GAPS`**. Es decir: es imposible arreglar un gap sin actualizar el registro, e imposible dejar el registro mintiendo.
Las dos claves `tracker.rate_limit.clamp` y `tracker.auth.html_redirect` son **transversales del transporte**, no del puerto: se agregan a `CAPABILITY_KEYS` en F2 con status `partial` para GitLab y `full` para ADO (así el registro las cubre y F7 les exige dueño).

5. `backend/tests/fixtures/provider_contract/azure_devops/*.json` y `backend/tests/fixtures/provider_contract/gitlab/*.json` — respuestas grabadas, **anonimizadas** (sin emails, sin tokens, sin nombres reales).

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

> **Lectura obligatoria de la tabla (v2, C3).** Las 7 filas marcadas "**Hoy GitLab falla / divergen**" describen comportamiento que **hoy no se cumple** y cuyo arreglo pertenece a los subplanes 222/223/224/231/232, **no a F3**. En el v1 esto hacía que el criterio "ambos comandos verdes" fuese **inalcanzable**. En v2 cada una de esas filas corre bajo `xfail(strict=True)` con su entrada en `KNOWN_GAPS`, de modo que F3 cierra en verde **sin ocultar un solo gap** y sin que ningún subplan pueda arreglarlos en silencio.

**Tests PRIMERO — `backend/tests/test_plan218_tracker_contract.py`:**
- `@pytest.mark.parametrize("provider_name", ["azure_devops", "gitlab"])` sobre `test_contrato_del_puerto_tracker` — corre `run_tracker_contract` y afirma que devolvió ≥ 1 capacidad verificada.
- `test_contrato_cubre_toda_capacidad_full_o_partial` — **v2 (C3): acotado al dominio `tracker.*`** (el puerto que F3 ejercita). Para cada proveedor, las capacidades `tracker.*` ejercitadas ⊇ las marcadas `full`/`partial` en `CAPABILITY_MATRIX`. Los dominios `repo.*`, `mr.*`, `ci.*`, `identity.*`, `events.*`, `links.*` **no** se exigen acá: sus puertos los ejercitan los subplanes 226/227/228/223/229/232, cada uno extendiendo esta misma suite. Un `_DOMINIOS_CUBIERTOS: frozenset = {"tracker"}` en el archivo de test declara el alcance, y **cada subplan que cierra un puerto agrega su dominio a ese set en el mismo commit** — así el alcance crece de forma explícita y auditable en vez de ser una promesa global imposible. *Motivo del cambio:* §6 marca ~40 capacidades `full`/`partial` en dominios cuyos escenarios F3 nunca especificó; el test global habría quedado rojo con los 11 escenarios que F3 sí define.
- `test_known_gaps_bien_formado` — cada clave de `KNOWN_GAPS` es una tupla `(provider, capability)` con `provider ∈ {"azure_devops","gitlab"}` y `capability ∈ CAPABILITY_KEYS`; cada valor trae `owner_plan ∈ 219..236`, `reason` de ≥ 20 caracteres y `evidence` que matchea `^[\w/\.]+\.py:\d+$`.
- *(El cruce `KNOWN_GAPS` ↔ catálogo de la serie vive en **F7**, no acá: `serie_paridad_218.json` se crea en F7, que corre después. Poner ese test en F3 repetiría la inversión de dependencia del C4.)*
- `test_ningun_test_de_contrato_parchea_config_ni_provider` — centinela textual sobre `backend/tests/contract/**` y sobre `test_plan218_tracker_contract.py`: cero coincidencias de `patch("services.gitlab_provider.config`, `patch("config`, `MagicMock(spec=GitLabTrackerProvider`, `patch(...GitLabTrackerProvider`. Codifica P4.
- `test_fixtures_sin_pii` — ningún fixture contiene `@` seguido de dominio, ni `PRIVATE-TOKEN`, ni cadenas de ≥ 20 caracteres alfanuméricos que parezcan token (mismo patrón que el Plan 217 §15).
- `test_conformance_legacy_deja_de_mentir` — afirma que `tests/test_tracker_provider_conformance.py` ya **no** contiene la cadena `"no que esté hardcoded NotImplementedError"` (obliga a corregir el test mentiroso en esta misma fase).

**Además, editar** `backend/tests/test_tracker_provider_conformance.py:81-92`: renombrar `test_no_port_method_is_a_stub` → `test_port_methods_son_callables` (que es lo que realmente hace) y borrar el comentario engañoso. La verificación de "no es un stub" pasa a ser responsabilidad del contrato conductual.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_tracker_contract.py" -q`
y luego `& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_tracker_provider_conformance.py" -q`

**Criterio de aceptación (binario):** ambos comandos verdes (los `xfail` de `KNOWN_GAPS` cuentan como verde; un `XPASS` es **fallo** por `strict=True`); el parametrize corre exactamente 2 veces (un proveedor cada vez), verificable con `-v`; y la cadena engañosa desapareció — **en PowerShell** (v2, C9):
`(Select-String -Path "Stacky Agents/backend/tests/test_tracker_provider_conformance.py" -Pattern "no que esté hardcoded" | Measure-Object).Count` → **0**.

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

**Criterio de aceptación (binario):** los 3 comandos verdes; `Test-Path "Stacky Agents/backend/services/client_profile_defaults/gitlab.json"` devuelve `True`; y `(Select-String -Path "Stacky Agents/backend/services/project_context.py" -Pattern "gitlab" | Measure-Object).Count` ≥ 1.

> **Verificado en la crítica v2:** las claves de primer nivel de `client_profile_defaults/azure_devops.json` son exactamente `schema_version, code_layout, language, database, build, conventions, docs_indexes, tracker_state_machine, terminology, extensions` — así que `tracker_state_machine` **sí** existe y el `gitlab.json` nuevo debe traer esas 10 claves. Y en `_auth_path_for` (`project_context.py:88-103`) se confirmó que hay rama `jira` (`:93`) y `mantis` (`:95`) y **no** `gitlab`: el `else` manda todo proyecto GitLab a `auth/ado_auth.json`.

**Flag:** `STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED` (bool, default **True**, categoría **`paridad_proveedores`** — v2, C6). Default ON: es corrección de resolución interna, no agrega prerequisitos (si el proyecto no declara nada, cae a la config global de hoy), no bypasea revisión humana, no es destructiva, no reduce seguridad. OFF ⇒ ruta legacy byte-idéntica.

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

> **Corrección de la crítica v2 (C7) — el payload de HOY, leído del código, no de la memoria.** `Ticket.to_dict()` emite **16** claves (el v1 decía 14) y **ya emite 2 canónicas**: `external_id` y `tracker_type`. Lista literal verificada en `models.py:80-98`, en orden: `id`, `ado_id`, `external_id`, `project`, `stacky_project_name`, `tracker_type`, `title`, `description`, `ado_state`, `ado_url`, `priority`, `work_item_type`, `parent_ado_id`, `last_synced_at`, `stacky_status`, `assigned_to_ado`. Consecuencias para esta fase:
> - El test de no-regresión afirma la presencia de esas **16**, no de 14 (con 14 el test queda rojo o, peor, pasa dejando 2 claves sin cubrir).
> - Las claves canónicas que esta fase **agrega** son **5**: `tracker_state`, `item_url`, `parent_external_id`, `assignee`, `item_type`. `external_id` y `tracker_type` ya están; `title`, `description` y `priority` ya son canónicas y **no** llevan alias.
> - `CANONICAL_FIELDS` incluye `tracker_project`, que **no tiene correlato** en `to_dict()` (hoy hay `project` = proyecto del tracker y `stacky_project_name` = proyecto de Stacky, que son cosas distintas). Decisión congelada: `tracker_project` **mapea a `project`** y se agrega `LEGACY_ALIASES["tracker_project"] = "project"`; `stacky_project_name` **no es canónico** (es identidad interna de Stacky, no del tracker) y queda fuera de `CANONICAL_FIELDS`.

3. `frontend/src/types.ts` — agregar a `interface Ticket` los campos canónicos como **opcionales** (`external_id?: number; tracker_state?: string; item_url?: string; parent_external_id?: number; assignee?: string; item_type?: string;`). No se toca ningún campo existente.

4. `frontend/src/services/trackerVocabulary.ts` (nuevo, puro) — `pickExternalId(t)`, `pickState(t)`, `pickUrl(t)`, `pickItemType(t)`: leen el canónico y caen al legacy. Es la función que los subplanes de UI van adoptando gradualmente.

**Tests PRIMERO:**
- `backend/tests/test_plan218_vocabulary_aliases.py`:
  - `test_with_legacy_aliases_es_superconjunto` — el dict resultante contiene todas las claves originales.
  - `test_with_legacy_aliases_es_idempotente` — aplicarlo dos veces da lo mismo.
  - `test_to_canonical_acepta_legacy` — `to_canonical({"ado_id": 5})["external_id"] == 5`.
  - `test_to_canonical_prefiere_canonico` — con ambas claves presentes y distintas, gana la canónica.
  - `test_ticket_to_dict_mantiene_las_16_claves_legacy` — el `to_dict()` nuevo contiene las **16** claves verificadas arriba (lista literal en el test, en ese orden).
  - `test_ticket_to_dict_agrega_las_5_canonicas_nuevas` — contiene además `tracker_state`, `item_url`, `parent_external_id`, `assignee`, `item_type`.
  - `test_tracker_project_mapea_a_project` — `to_canonical({"project": "X"})["tracker_project"] == "X"` y `stacky_project_name` **no** aparece en `CANONICAL_FIELDS`.
  - `test_flag_off_devuelve_payload_original` — con la flag en `False`, `to_dict()` devuelve exactamente el dict legacy.
- `frontend/src/services/__tests__/trackerVocabulary.test.ts`:
  - `pickExternalId` prefiere `external_id`, cae a `ado_id`, devuelve `null` si no hay ninguno.
  - `pickUrl` / `pickState` / `pickItemType`: mismos 3 casos cada uno.

**Comandos exactos:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_vocabulary_aliases.py" -q`
`cd "Stacky Agents/frontend"; npx vitest run src/services/__tests__/trackerVocabulary.test.ts`
`cd "Stacky Agents/frontend"; npx tsc --noEmit`

**Criterio de aceptación (binario):** los 3 comandos verdes; y el conteo de `ado_id` en `models.py` **no disminuye** respecto del valor previo — prueba de que no hubo renombre destructivo. En PowerShell (v2, C9), medir **antes** y **después**:
`(Select-String -Path "Stacky Agents/backend/models.py" -Pattern "ado_id" -AllMatches | Measure-Object).Count`

**Flag:** `STACKY_CANONICAL_VOCABULARY_ENABLED` (bool, default **True**, categoría **`paridad_proveedores`** — v2, C6). Default ON: el cambio es puramente aditivo (agrega claves al JSON), por lo que no puede romper un consumidor existente. OFF ⇒ payload idéntico al de hoy.

**Impacto por runtime:** Codex / Claude Code / Copilot **idéntico** — los 3 reciben el contexto del ticket por la misma serialización (`Ticket.to_dict()` alimenta la inyección de contexto de los tres). Fallback de los tres: flag OFF ⇒ payload legacy.

**Trabajo del operador: ninguno.**

---

### F6 — Degradación declarada: `CapabilityUnavailable` en vez de errores mudos

**Objetivo (1 frase):** que una capacidad no soportada por el proveedor activo se manifieste como un mensaje accionable y un `200 {available:false}`, nunca como un `NotImplementedError` que tira 500 ni como un silencio.

**Valor:** convierte los ~10 dominios sin paridad en una experiencia honesta mientras los subplanes los cierran. Es lo que permite hacer rollout gradual sin romper nada.

**Archivos a editar/crear:**

1. ~~Definir `CapabilityUnavailable`~~ — **movido a F2 en v2 (C4)**: F3 la necesita y corre antes. Esta fase la **consume**, no la crea.

2. `backend/api/errors.py` — registrar el handler que traduce `CapabilityUnavailable` a **HTTP 200** con `to_payload()`, siguiendo el patrón ya establecido por el Plan 148 (`200 + available:false` en vez de 502). *(Verificado en la crítica v2: `backend/api/errors.py` existe; los `errorhandler` del app se registran desde `app.py`, así que el handler nuevo debe quedar alcanzado por la misma vía que usan los actuales — el implementador confirma leyendo `api/errors.py` completo antes de editar.)*

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
- `test_endpoint_de_sync_devuelve_200_con_available_false` — con un provider falso llamado `gitlab`, `POST /api/tickets/sync` (ruta real: `@bp.post("/sync")`, `api/tickets.py:700`) responde **200** y `body["available"] is False` y `body["capability"] == "tracker.sync.full"`.
- `test_endpoint_de_sync_ado_no_cambia` — con provider `azure_devops`, el endpoint se comporta exactamente igual que antes (regresión).
- `test_no_quedan_RAISE_notimplementederror_en_api` — **v2 (C2): el centinela caza `raise\s+NotImplementedError`, NO la mención del símbolo.** Con allowlist vacía sobre `backend/api/*.py`. **Motivo del cambio:** el criterio del v1 (`grep "NotImplementedError"` = 0) exigía borrar **4 `except NotImplementedError` legítimos** — `api/agents.py:1952`, `api/ci.py:124`, `api/ci.py:223`, `api/pipeline_generator.py:86` —, es decir, degradar el manejo de errores de endpoints ajenos al plan (viola P11) para satisfacer un grep. Medición real 2026-07-25: `raise NotImplementedError` en `backend/api/` = **1** (solo `tickets.py:692`), menciones totales = 6. El objetivo correcto es **0 raises**, no 0 menciones.
- `test_los_4_except_legitimos_siguen_en_pie` — afirma explícitamente que los 4 `except NotImplementedError` de arriba **siguen existiendo**. Es el guard que impide que un implementador celoso los borre "para poner el grep en cero".
- `test_flag_off_restaura_excepcion_legacy` — con `STACKY_CAPABILITY_DEGRADATION_ENABLED=False`, vuelve el comportamiento anterior.
*(`test_payload_tiene_las_5_claves` y `test_es_subclase_de_tracker_error` se movieron a F2 junto con la clase.)*

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_unavailable.py" -q`
Regresión: `... -m pytest "Stacky Agents/backend/tests/test_plan70_group_sync.py" -q`

**Criterio de aceptación (binario):** ambos comandos verdes; y en PowerShell (v2, C9 + C2):
- `(Get-ChildItem "Stacky Agents/backend/api" -Filter *.py | Select-String -Pattern "raise\s+NotImplementedError" | Measure-Object).Count` → **0**
- `(Get-ChildItem "Stacky Agents/backend/api" -Filter *.py | Select-String -Pattern "except NotImplementedError" | Measure-Object).Count` → **4** (sigue siendo 4: no se tocaron)

**Flag:** `STACKY_CAPABILITY_DEGRADATION_ENABLED` (bool, default **True**, categoría **`paridad_proveedores`** — v2, C6). Default ON: convertir un 500 mudo en un 200 accionable **mejora** estabilidad y DX; no agrega prerequisitos ni reduce seguridad. OFF ⇒ excepción legacy.

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
      "//": "v2 (C11): el ORQUESTADOR también declara sus archivos, o sus 12 archivos",
      "//2": "quedan fuera del test de colisiones y un subplan puede reclamarlos.",
      "number": 218,
      "slug": "PARIDAD_TOTAL_ADO_GITLAB_ORQUESTADOR_SERIE_MULTIPROVEEDOR",
      "title": "Sustrato multi-proveedor (F0..F8)",
      "priority": "P0",
      "milestone": "M0",
      "depends_on": [],
      "owns_files": [
        "backend/services/flag_binding_audit.py",
        "backend/services/provider_coupling_audit.py",
        "backend/services/provider_capabilities.py",
        "backend/services/tracker_vocabulary.py",
        "backend/services/parity_series.py",
        "backend/services/parity_rollout.py",
        "backend/api/parity.py",
        "backend/services/client_profile_defaults/gitlab.json",
        "frontend/src/services/trackerVocabulary.ts",
        "frontend/src/services/parityMatrixModel.ts",
        "frontend/src/components/ParityMatrixPanel.tsx",
        "frontend/src/pages/DiagnosticsPage.tsx"
      ],
      "capabilities": [],
      "acceptance": "Ver §13 (DoD global del Plan 218)."
    },
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

2b. `docs/_roadmap/estado_real_serie_gitlab.json` — **v2 (C12): el artefacto que de verdad resuelve §2.4.** El v1 prometía "F7 congela el estado real medido contra el código" pero ninguno de sus 8 tests lo hacía (`test_docs_existentes_coinciden` solo compara el **nombre** del archivo). Este JSON registra, por cada plan previo de la serie GitLab (65, 70, 71, 72, 73, 74, 75, 95), su estado **medido**: `{"plan": 70, "doc_dice": "PROPUESTO", "estado_real": "IMPLEMENTADO_PARCIAL", "evidencia": [{"file": "backend/api/tickets.py", "symbol": "_provider_for_ticket"}], "nota": "flag STACKY_TICKETS_PROVIDER_ENABLED en OFF ⇒ inactivo en producción"}`. Los `estado_real` válidos: `IMPLEMENTADO`, `IMPLEMENTADO_PARCIAL`, `IMPLEMENTADO_INALCANZABLE` (el código existe pero la fábrica nunca lo devuelve — caso 65/71/72/73/75/95 antes de F0), `NO_IMPLEMENTADO`.

**Tests PRIMERO — `backend/tests/test_plan218_serie_integridad.py`:**
- `test_numeros_unicos_y_consecutivos` — los `number` son únicos y forman el rango **218**..236 sin huecos (v2, C11: incluye al orquestador).
- `test_toda_dependencia_existe` — cada valor de `depends_on` está en la serie.
- `test_sin_ciclos` — `topological_order` no levanta.
- `test_sin_colision_de_propiedad` — **ningún archivo aparece en `owns_files` de dos entradas, incluida la 218**. Esta es la garantía ejecutable del "mapa de colisiones". *Motivo (C11): F8 edita `frontend/src/pages/DiagnosticsPage.tsx`, que ningún subplan reclamaba y que el 232 podía tomar sin conflicto detectado.*
- `test_toda_capacidad_declarada_existe` — cada valor de `capabilities` ∈ `CAPABILITY_KEYS` (§F2).
- `test_known_gaps_tiene_dueno_en_la_serie` — **v2 (C3/C4):** todo `owner_plan` de `KNOWN_GAPS` (F3) existe en la serie **y** esa capacidad figura en el `capabilities` del subplan dueño. Cierra el lazo del ratchet inverso: un gap sin dueño en el catálogo deja el test rojo. Vive acá (no en F3) porque el catálogo se crea acá.
- `test_estado_real_de_planes_previos_esta_verificado` — para cada entrada de `estado_real_serie_gitlab.json` con `estado_real ≠ NO_IMPLEMENTADO`, **cada `evidencia[].symbol` existe de verdad** en su `evidencia[].file` (búsqueda textual del nombre del símbolo en el archivo, que debe existir en disco). Un plan declarado implementado sin símbolo verificable deja el test rojo.
- `test_toda_capacidad_no_full_tiene_dueño` — cada capacidad con status `absent`/`partial` en `CAPABILITY_MATRIX` para algún proveedor aparece en `capabilities` de **al menos un** subplan, **o** está listada en la constante literal `FUERA_DE_SCOPE_218` del propio test. **Este test hace imposible olvidarse de un gap.**
- `test_prioridad_y_hito_validos` — `priority` ∈ {`P0`,`P1`,`P2`}; `milestone` ∈ los ids declarados.
- `test_docs_existentes_coinciden` — si `Stacky Agents/docs/<number>_PLAN_*.md` existe, su nombre empieza con `<number>_PLAN_<slug>`.

**Comando exacto:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_serie_integridad.py" -q`

**Criterio de aceptación (binario):** comando verde con **10 tests**; `Test-Path "Stacky Agents/docs/_roadmap/serie_paridad_218.json"` → `True`; `Test-Path "Stacky Agents/docs/_roadmap/estado_real_serie_gitlab.json"` → `True`; y el JSON tiene **19** entradas en `subplans` — los 18 subplanes **más** el orquestador 218 (v2, C11):
`(Get-Content "Stacky Agents/docs/_roadmap/serie_paridad_218.json" -Raw | ConvertFrom-Json).subplans.Count` = **19**

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

4. `frontend/src/components/ParityMatrixPanel.tsx` + `ParityMatrixPanel.module.css` (nuevos) — tabla agrupada por dominio con el estado por capacidad, renderizada dentro de `frontend/src/pages/DiagnosticsPage.tsx`. **Sin `style={{`, sin `confirm(`/`alert(`/`prompt(`** (ratchet `frontend/src/__tests__/uiDebtRatchet.test.ts:22,27`).
> **v2 (C10) — el ratchet de UI tiene TRES reglas, no dos.** Verificado en `uiDebtRatchet.test.ts:21`: además de `INLINE_STYLE_RE` y `NATIVE_DIALOG_RE`, hay **`HEX_RE = /#[0-9a-fA-F]{3,8}\b/g`** con baseline **por archivo** en `frontend/src/__tests__/uiDebtBaseline.json`. Un `.module.css` nuevo con colores hex crudos rompe el ratchet (y la memoria `gotcha-ratchet-nuevo-archivo-cero-inline-style` dice que el alcance de un archivo nuevo es **0**). Por lo tanto: **cero literales hex** en `ParityMatrixPanel.module.css` y `.tsx` — todos los colores por `var(--…)` de los tokens ya existentes; los 4 estados (`full`/`partial`/`absent`/`n/a`) se distinguen con tokens semánticos existentes **más** una marca no-cromática (texto/ícono), para no depender solo del color.

**Tests PRIMERO:**
- `backend/tests/test_plan218_parity_endpoint.py`:
  - `test_matrix_devuelve_todas_las_capacidades` — el endpoint responde 200 con `len(body["capabilities"]) == len(CAPABILITY_KEYS)`.
  - `test_override_por_proyecto_apaga_una_capacidad` — con `parity_overrides: {"mr.approve": false}`, esa capacidad viene `enabled=false` aunque el status sea `full`.
  - `test_flag_maestra_off_capability_enabled_es_true_para_todo` — **v2: el test llama a `parity_rollout.capability_enabled()` directamente, NO al endpoint.** Con `STACKY_PROVIDER_PARITY_ENABLED=False` devuelve `True` para toda capacidad (comportamiento pre-plan). *Motivo: el v1 ponía este test en el archivo del endpoint mientras la misma fase declaraba que con la flag OFF el endpoint responde **404** — dos afirmaciones incompatibles sobre el mismo escenario.*
  - `test_flag_maestra_off_el_endpoint_no_existe` — con la flag OFF, `GET /api/parity/matrix` devuelve **404** (el blueprint no se registra). Este es el rollback completo del 218.
  - `test_endpoint_es_solo_lectura` — `POST /api/parity/matrix` devuelve 405.
  - `test_ruta_registrada_sin_doble_prefijo` — la URL map contiene `/api/parity/matrix` y **no** `/api/api/parity/matrix`.
  - `test_no_filtra_secretos` — la respuesta no contiene `token`, `pat`, `PRIVATE-TOKEN` en ninguna clave ni valor.
- `frontend/src/services/__tests__/parityMatrixModel.test.ts`: `groupByDomain` agrupa por el prefijo antes del primer punto; `summarize` cuenta los 4 estados; `statusLabel` mapea los 4 sin caer en `undefined`.

**Comandos exactos:**
`& "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_parity_endpoint.py" -q`
`cd "Stacky Agents/frontend"; npx vitest run src/services/__tests__/parityMatrixModel.test.ts`
`cd "Stacky Agents/frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts`
`cd "Stacky Agents/frontend"; npx tsc --noEmit`

**Criterio de aceptación (binario):** los 4 comandos verdes; y en PowerShell (v2, C9 + C10) las tres reglas del ratchet en cero para los archivos nuevos:
```
cd "Stacky Agents/frontend/src"
(Select-String -Path "components/ParityMatrixPanel.tsx" -Pattern 'style=\{\{' -AllMatches | Measure-Object).Count      # 0
(Select-String -Path "components/ParityMatrixPanel.tsx","components/ParityMatrixPanel.module.css" -Pattern '#[0-9a-fA-F]{3,8}\b' -AllMatches | Measure-Object).Count   # 0
(Select-String -Path "components/ParityMatrixPanel.tsx" -Pattern '(?<![.\w])(?:window\.)?(?:confirm|alert|prompt)\s*\(' -AllMatches | Measure-Object).Count            # 0
```

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
| `frontend/src/pages/TicketBoard.tsx`, `UnblockerPage.tsx`, **`SprintBoardPage.tsx`** | **232** | Advertencia: hay cambios sin commitear de una sesión paralela sobre estos archivos (ver `git status`); coordinar antes de tocar. |
| **`frontend/src/utils/workItemTypeColor.ts`** (+ su test nuevo sin trackear `src/utils/__tests__/workItemTypeColor.test.ts`) | **224** | **v2 (C15):** también tiene cambios sin commitear de la sesión paralela — verificado en `git status` al momento de la crítica. El v1 solo advertía por TicketBoard/UnblockerPage. Releer el archivo en frío antes de editar; **jamás** `git stash`/`reset`/`amend` (memoria `feedback_concurrent-branch-git-amend-hazard`). |
| `frontend/src/pages/DiagnosticsPage.tsx` | **218 F8** | v2 (C11): ahora declarado en `owns_files` de la entrada 218 del catálogo, así que el test de colisiones lo protege. |

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

**Segunda regla de oro (v2, C3/C14) — un gap no se esconde: se firma.** Todo comportamiento que este plan sabe que hoy no se cumple vive en `KNOWN_GAPS` con `owner_plan`, `reason` y `evidence`, y corre bajo `xfail(strict=True)`. Consecuencia deliberada: **la suite puede estar verde con gaps abiertos, pero no puede estar verde con gaps mentidos.** Si alguien arregla uno sin borrar su entrada, el `XPASS` rompe el build; si alguien lo declara arreglado sin arreglarlo, el `xfail` no pasa a `XPASS` y la entrada sigue ahí, visible en el catálogo de F7. Esto también aplica al **alcance del contrato**: `_DOMINIOS_CUBIERTOS` empieza en `{"tracker"}` y cada subplan que cierra un puerto agrega su dominio en el mismo commit — nada de "cobertura total" declarada de entrada y nunca alcanzada.

> **Nota de registro en el ratchet de tests (verificado en la crítica v2):** `tests/test_harness_ratchet_meta.py` usa `_TESTS_DIR.rglob("test_*.py")` — es **recursivo**. Los archivos nuevos de `backend/tests/contract/` (`fake_transport.py`, `provider_contract.py`, `known_gaps.py`) **no** matchean `test_*.py` y por lo tanto no requieren registro; pero cualquier `test_*.py` dentro de un subdirectorio nuevo (p. ej. el `backend/tests/e2e/` del subplan 233) **sí** debe registrarse con su ruta relativa completa (`tests/e2e/test_x.py`) en `run_harness_tests.sh` **y** `.ps1`, o el meta-test queda rojo. Precedente en el árbol: `backend/tests/conformance/`.

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
| **R12** | La matriz se marca `full` por optimismo y la paridad vuelve a ser una promesa | Media | Muy alto | `test_contrato_cubre_toda_capacidad_full_o_partial` (F3, acotado a `tracker.*` + extensión por subplan): marcar `full` sin escenario de contrato deja el test **rojo**. Y en el sentido inverso, `test_matriz_no_miente_estructuralmente` (F2) caza la capacidad ya implementada que la matriz sigue declarando `absent`. |
| **R13** | **Un centinela textual "arregla" código correcto.** Un implementador (o un modelo menor) aplica mecánicamente `getattr(config,` → `getattr(config.config,` en los ~65 sitios donde `config` **ya es la instancia**, rompiendo el motor de flags de todo el repo | **Alta** (era exactamente lo que pedía el v1) | **Muy alto** | El centinela de F0 es **AST con resolución de binding**, nunca regex; `test_audit_no_marca_binding_de_instancia` falla si alguien lo vuelve textual; y el criterio de aceptación se acota a los **2 archivos del seam**, con el resto del repo en **ratchet**, no en cero. |
| **R14** | **Un criterio de aceptación imposible bloquea la fase y empuja a bajar la vara.** Ocurría en 3 fases del v1 (F0, F3, F6): el implementador honesto se traba, el apurado borra tests/handlers legítimos para "poner el grep en cero" | **Alta** | Alto | Todo criterio del v2 fue **ejecutado o medido** contra el árbol real durante la crítica (69 sitios de binding, 1 raise vs 4 except, 16 claves de `to_dict`, 82 literales, 20 líneas de `_ado_client_for_ticket`, 3 reglas del ratchet de UI, 20 categorías de flags). Los gaps que no se pueden cerrar en la fase viven en `KNOWN_GAPS` con `xfail(strict=True)` y dueño, no en un criterio inalcanzable. |
| **R15** | Un subplan arregla un gap de GitLab y nadie actualiza la matriz ni el registro ⇒ la UI sigue ocultando algo que ya funciona | Media | Medio | `xfail(strict=True)` sobre `KNOWN_GAPS`: arreglar el gap produce **XPASS = fallo**, y el único camino al verde es borrar la entrada. Es un ratchet que aprieta en los dos sentidos. |

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
3. **218 F2** — Registro de capacidades + matriz generada + **`CapabilityUnavailable`** (v2, C4) + **categoría de flags `paridad_proveedores`** (v2, C6).
4. **218 F3** — Suite de contrato conductual + **`KNOWN_GAPS`** (v2, C3) y corregir el test mentiroso de conformance.
5. **218 F4** — Destino por proyecto + `client_profile_defaults/gitlab.json`.
6. **218 F5** — Vocabulario canónico con alias.
7. **218 F6** — Traducción HTTP de `CapabilityUnavailable` (200 + `available:false`) + degradación en el endpoint de sync. *(La clase ya existe desde F2.)*
8. **218 F7** — Catálogo de la serie + tests de integridad y colisiones.
9. **218 F8** — Rollout por capacidad, endpoint y panel de paridad.
10. **219** → **220** → **221** (hito M1: GitLab usable de punta a punta). *Aquí se mide K1 = 100 %.*
11. **222**, **223**, **224** (M2), en ese orden.
12. **226**, **227** → **228**, **230** (M3). 227 antes que 228 (el MR necesita ramas).
13. **225**, **229**, **231**, **232**, **233** (M4). 233 puede adelantarse si se necesita el sandbox antes.
14. **234**, **235**, **236** (M5).

---

## 13. Definición de Hecho (DoD) global del Plan 218

- [ ] Los 4 defectos D1..D4 corregidos; `test_plan218_gitlab_reachable.py` verde con **13 tests**; **cero violaciones de `flag_binding_audit.scan()` en `tracker_provider.py` y `gitlab_provider.py`**, y el resto del repo congelado en `backend/tests/flag_binding_baseline.json` (ratchet, no cero global); las 2 huellas de regresión registradas en `docs/sistema/error_fingerprints.json`.
- [ ] `provider_coupling_audit.scan_backend_coupling()` corre y `test_plan218_coupling_ratchet.py` está verde con **10 tests** y la línea base **generada** (no transcrita) en `backend/tests/provider_coupling_baseline.json`; `NEUTRAL_REGISTRY_ALLOWLIST` cubre los 6 archivos neutrales del sustrato.
- [ ] `provider_capabilities.CAPABILITY_MATRIX` cargada con las 2 columnas completas; `docs/_roadmap/PARIDAD_ADO_GITLAB.md` **generado** y sincronizado (comparación normalizada a `\n`); `CapabilityUnavailable` definida; categoría `paridad_proveedores` creada y `test_harness_flags.py` verde.
- [ ] La suite de contrato corre contra los 2 adaptadores reales; ninguna capacidad `tracker.*` marcada `full`/`partial` queda sin escenario; los 7 gaps conocidos están en `KNOWN_GAPS` con dueño y corren bajo `xfail(strict=True)`; el centinela anti-mock está verde; `test_tracker_provider_conformance.py` ya no contiene la cadena `"no que esté hardcoded NotImplementedError"`.
- [ ] `build_tracker_target()` resuelve destino por proyecto; existe `backend/services/client_profile_defaults/gitlab.json`; dos proyectos GitLab distintos conviven en una misma corrida de test.
- [ ] `Ticket.to_dict()` emite las **16** claves previas **más** las 5 canónicas nuevas; `npx tsc --noEmit` limpio.
- [ ] `CapabilityUnavailable` se traduce a HTTP 200 con `available:false`; **`raise NotImplementedError` en `backend/api/` = 0** y los **4 `except NotImplementedError` legítimos siguen en pie**.
- [ ] `docs/_roadmap/serie_paridad_218.json` con **19** entradas (18 subplanes + el orquestador 218 con sus 12 archivos); `docs/_roadmap/estado_real_serie_gitlab.json` con los 8 planes previos medidos contra símbolos verificables; `test_plan218_serie_integridad.py` verde con 10 tests (sin ciclos, sin colisiones de propiedad, sin capacidad huérfana, sin gap sin dueño).
- [ ] `GET /api/parity/matrix` responde 200 con todas las capacidades; el panel se ve en Diagnósticos; `uiDebtRatchet` verde; **0** ocurrencias de `style={{`, **0** literales hex y **0** diálogos nativos en los archivos nuevos.
- [ ] Las 4 flags nuevas están en los **7** lugares de la receta (incluida la `CategorySpec` `paridad_proveedores`) y `test_harness_flags.py` verde; con `STACKY_PROVIDER_PARITY_ENABLED=false` el comportamiento es byte-idéntico al previo.
- [ ] Todos los `test_plan218_*.py` registrados en `HARNESS_TEST_FILES` de `run_harness_tests.sh` **y** `run_harness_tests.ps1`; `test_harness_ratchet_meta.py` verde.
- [ ] Regresión ADO verde por archivo: `test_ado_provider.py`, `test_ado_client_stacky_name_resolution.py`, `test_tracker_factory.py`, `test_plan70_group_sync.py`, `test_plan95_mr_providers.py`.
- [ ] Ningún criterio binario de F0–F8 en rojo; el encabezado de este documento actualizado a IMPLEMENTADO.

---

## 14. Changelog de este documento

- **v2 (2026-07-25) — CRITICADO (`criticar-y-mejorar-plan`). Veredicto sobre el v1: RECHAZADO → v2 APROBADO-CON-CAMBIOS.** 5 BLOQUEANTES, 8 IMPORTANTES y 3 MENORES resueltos; todo hallazgo fue **medido contra el árbol real**, no inferido.
  - **C1 (BLOQ, F0) — el centinela `getattr(config,` era incorrecto y destructivo.** Hay **69** coincidencias en `services`+`api` y **~65 son correctas** (binding a la instancia vía `from config import config`); el "fix" que exigía el v1 habría roto el motor de flags (`Config` no tiene `.config`). Los defectos reales son **2 archivos / 5 sitios**. Reemplazado por **[ADICIÓN ARQUITECTO 1]**: `flag_binding_audit.py`, auditoría **AST con resolución de binding por módulo**, que además caza el acceso directo `config.FLAG` que el regex no veía, barre `harness/`, y congela el resto del repo en ratchet en vez de exigir cero global. F0 pasa de 9 a 13 tests.
  - **C2 (BLOQ, F6) — "0 `NotImplementedError` en `backend/api/*.py` con allowlist vacía" exigía borrar 4 `except` legítimos** (`agent.py:1952`, `ci.py:124,223`, `pipeline_generator.py:86`), degradando endpoints ajenos al plan. Medido: `raise NotImplementedError` en `api/` = **1**. Centinela reescrito a `raise\s+NotImplementedError` + `test_los_4_except_legitimos_siguen_en_pie` como guard anti-celo.
  - **C3 (BLOQ, F3) — criterio de aceptación imposible:** ≥7 escenarios del contrato describen comportamiento hoy roto en GitLab cuyo arreglo pertenece a 222/223/224/231/232, y `test_contrato_cubre_toda_capacidad_full_o_partial` exigía escenario para ~40 capacidades de 6 dominios que F3 nunca especificó. Resuelto con **[ADICIÓN ARQUITECTO 2]**: `KNOWN_GAPS` + `xfail(strict=True)` (ratchet **inverso**: arreglar un gap sin actualizar el registro produce XPASS = fallo) + alcance del test acotado a `tracker.*` con `_DOMINIOS_CUBIERTOS` que cada subplan amplía en su commit.
  - **C4 (BLOQ, F3→F6) — inversión de dependencia:** F3 (paso 4) usaba `CapabilityUnavailable`, creada en F6 (paso 7). La clase se movió a **F2**; F6 conserva solo la traducción HTTP. Y se corrigió la aserción para capacidades `absent`: se verifica por `supports()`/`hasattr` (como ya hace `api/pr_review.py:368`), no por una excepción que **ningún adaptador levanta**.
  - **C5 (BLOQ, F1↔F2) — contradicción interna:** el ratchet "solo baja" de F1 se rompía al implementar F2, porque `CAPABILITY_MATRIX` tiene `"azure_devops"` como **clave**. Agregada `NEUTRAL_REGISTRY_ALLOWLIST` (6 archivos) + test que impide usarla para esconder acoplamiento real (la exención vale para el literal, nunca para el import).
  - **C6 (IMP) — la categoría de flags `integraciones` NO EXISTE.** Las 20 reales están enumeradas en §4; `test_harness_flags.py:739` exige biyección registry↔`_CATEGORY_KEYS`, así que las 4 flags habrían dejado el test rojo. Se crea la categoría `paridad_proveedores` y la receta pasa de **5 a 7 pasos**.
  - **C7 (IMP, F5) — `Ticket.to_dict()` emite 16 claves, no 14, y ya emite `external_id` y `tracker_type`.** Lista literal verificada en `models.py:80-98`; las canónicas **nuevas** son 5, no 6. Congelado además el mapeo `tracker_project → project` y la exclusión de `stacky_project_name` del vocabulario canónico.
  - **C8 (IMP, F1) — unidades inconsistentes:** `ado_importers_count`=36 eran **archivos** y `tracker_literals_count`=85 **ocurrencias**, con el mismo sufijo `_count`. Renombradas a `*_file_count`/`*_occurrences`; y el baseline **se genera con un comando** en vez de transcribirse (el número del v1 ya estaba desactualizado: medido **82**, no 85).
  - **C9 (IMP) — criterios en sintaxis Bash en un repo con PowerShell primario**, incluyendo uno que no parsea: `grep -c "^| \`"` (el backtick es el escape de PowerShell). Todos los criterios binarios reescritos con `Select-String`/`Measure-Object`, con la tabla de equivalencias en §4.
  - **C10 (IMP, F8) — el ratchet de UI tiene 3 reglas, no 2:** faltaba `HEX_RE` con baseline por archivo (`uiDebtRatchet.test.ts:21`). Exigido cero hex en los archivos nuevos + marca no-cromática por estado.
  - **C11 (IMP, F7) — los 12 archivos de 218 no estaban en el mapa de colisiones** ni en `test_sin_colision_de_propiedad` (que solo miraba 219..236); `DiagnosticsPage.tsx` quedaba reclamable por el 232. El orquestador ahora es la entrada `218` del catálogo (19 entradas) y el test lo cubre.
  - **C12 (IMP, F7) — F7 prometía resolver la divergencia doc↔código de §2.4 y ninguno de sus tests lo hacía.** Agregado `docs/_roadmap/estado_real_serie_gitlab.json` (estado **medido** de los planes 65/70-75/95, con estado nuevo `IMPLEMENTADO_INALCANZABLE`) + test que verifica que cada símbolo declarado exista de verdad.
  - **C13 (IMP, F3) — `urlopen` está en 4 sitios de `ado_client.py` (273, 499, 539, 717), no en los 2 que decía el v1.** Se parchea el **atributo del módulo**, sin enumerar líneas.
  - **C14 (MEN, F0) — faltaba la huella de regresión.** Registradas 2 clases en `error_fingerprints.json`: `flag-leida-del-modulo-config` y `kwarg-inexistente-en-constructor-de-provider`, cada una con su `guard_test`.
  - **C15 (MEN, §5.3) — `workItemTypeColor.ts` (dueño 224) también tiene cambios sin commitear de la sesión paralela**, igual que `SprintBoardPage.tsx`; el v1 solo advertía por 2 archivos.
  - **C16 (MEN, F2) — comparación byte-a-byte de un `.md` generado es intermitente en Windows** (`core.autocrlf`). Escritura con `newline="\n"` y comparación normalizada.
  - **Adiciones proactivas:** **[ADICIÓN ARQUITECTO 1]** `flag_binding_audit` (K9) — generaliza el gotcha de `config` a TODO el repo por AST y puede descubrir ramas muertas más allá de GitLab; **[ADICIÓN ARQUITECTO 2]** `KNOWN_GAPS` + `xfail(strict=True)` + `test_matriz_no_miente_estructuralmente` (K10) — la paridad queda apretada en los **dos** sentidos: no se puede declarar `full` sin probarlo (F3) ni dejar la matriz declarando `absent` algo ya implementado (F2), ni arreglar un gap en silencio (XPASS = fallo).
  - **Sin cambios:** los 3 rieles duros quedaron intactos — paridad de 3 runtimes (todas las fases son backend puro o UI ajena al motor de agentes, con fallback por flag), cero trabajo extra al operador (las 4 flags nacen ON; la única OFF es la preexistente `STACKY_GITLAB_ENABLED`, excepción dura 3 citada), human-in-the-loop (ninguna adición introduce autonomía; el ratchet inverso **exige** decisión humana explícita para borrar una entrada de `KNOWN_GAPS`), mono-operador sin RBAC (P9 verificado en 223/230), y backward-compatibilidad (P6: cero renombres).

- **v1 (2026-07-25)** — Versión inicial. Relevamiento con evidencia `archivo:línea` de todo el acoplamiento ADO del backend y del frontend; **4 defectos del camino GitLab reproducidos por ejecución** (D1..D4, §2.1); 3 bloqueos estructurales (§2.2); doctrina de normalización en 3 capas (§3.1); 9 fases de sustrato (F0..F8); catálogo de 18 subplanes 219..236 con mapa de colisiones ejecutable (§5); matriz de paridad inicial verificada (§6). Pendiente: pasar por `criticar-y-mejorar-plan`.

---

## 15. Reporte de implementación (2026-07-25)

Implementado con `implementar-plan-stacky` sobre la rama `feat/plan-217-migrador-mantis-gitlab`
(árbol compartido con una sesión paralela: commit con pathspec explícito, sin `stash`/`reset`/`amend`).

### 15.1 Estado por fase

| Fase | Estado | Comando corrido | Resultado real |
|---|---|---|---|
| F0 | IMPLEMENTADA | `pytest tests/test_plan218_gitlab_reachable.py -q` | **13 passed** |
| F1 | IMPLEMENTADA | `pytest tests/test_plan218_coupling_ratchet.py -q` | **10 passed** |
| F2 | IMPLEMENTADA | `pytest tests/test_plan218_capability_matrix.py -q` + `test_harness_flags.py` | **10 passed** + **56 passed** |
| F3 | IMPLEMENTADA | `pytest tests/test_plan218_tracker_contract.py -q` + `test_tracker_provider_conformance.py` | **10 passed** + **13 passed** |
| F4 | IMPLEMENTADA | `pytest tests/test_plan218_tracker_target.py -q` | **8 passed** |
| F5 | IMPLEMENTADA | `pytest tests/test_plan218_vocabulary_aliases.py -q` + `vitest trackerVocabulary` + `tsc` | **8 passed** + **5 passed** + **0 errores** |
| F6 | IMPLEMENTADA | `pytest tests/test_plan218_capability_unavailable.py -q` + `test_plan70_group_sync.py` | **5 passed** + **5 passed** |
| F7 | IMPLEMENTADA | `pytest tests/test_plan218_serie_integridad.py -q` | **10 passed** |
| F8 | IMPLEMENTADA | `pytest tests/test_plan218_parity_endpoint.py -q` + `vitest parityMatrixModel` + `uiDebtRatchet` + `tsc` | **7 passed** + **6 passed** + **3 passed** + **0 errores** |

Total propio: **81 tests backend** en 9 archivos + **14 tests frontend**. Regresión ADO verde por archivo:
`test_ado_provider.py` (8), `test_ado_client_stacky_name_resolution.py` (3), `test_tracker_factory.py` (4),
`test_plan70_group_sync.py` (5), `test_plan95_mr_providers.py` (11), `test_gitlab_provider.py` (26),
`test_plan94_variables_providers.py` (13), `test_plan93_preflight_providers.py` (15),
`test_plan70_no_typed_adoclient_in_api.py` (4), `test_harness_ratchet_meta.py` (4),
`test_error_fingerprints_catalog.py` (8).

### 15.2 Hallazgos nuevos (no estaban en el relevamiento de §2)

1. **`ado_provider.py:44` lee `ADO_PAT` del MÓDULO `config`** ⇒ `AdoTrackerProvider.credentials_present()`
   devuelve **siempre `False`**. Lo encontró `flag_binding_audit` (F0) fuera de los 5 sitios conocidos.
   Por P11 **no se arregla acá** (cambia comportamiento): queda congelado en
   `backend/tests/flag_binding_baseline.json` (`violation_count: 1`) y es trabajo del subplan **231**.
2. **`AdoTrackerProvider.get_item` propaga `AdoApiError` crudo** donde el puerto promete
   `TrackerApiError(kind="not_found")`. Lo encontró el contrato conductual de F3 — el relevamiento en papel
   solo había visto gaps de GitLab. La matriz baja esa capacidad de `full` a `partial` con su pérdida
   declarada y el gap queda firmado en `KNOWN_GAPS` con dueño **231**.
3. **`AdoTrackerProvider.fetch_open_items` nunca devuelve ítems**: llama a `self._client.list_work_items`,
   que **no existe** en `AdoClient` (tiene `fetch_open_work_items`), y el `except AttributeError` devuelve `[]`.
   Declarado sin escenario con dueño **220** en `_SIN_ESCENARIO_CON_DUENO`.
4. **Ruta con doble prefijo preexistente**: `/api/api/projects/<project_name>/tasks` (ajena al 218, R6).

### 15.3 Desvíos respecto del texto del plan (con motivo)

- **F3 — `xfail(strict=True)`**: la semántica (gap roto ⇒ verde; gap arreglado ⇒ FALLO hasta borrar la
  entrada) está implementada **dentro de `run_tracker_contract`**, no con el marcador de pytest. Motivo: el
  criterio binario exige que `test_contrato_del_puerto_tracker` parametrice **exactamente 2 veces**, y eso
  obliga a correr todos los escenarios dentro de un único test por proveedor. El efecto observable es idéntico.
- **F3 — cobertura**: `test_contrato_cubre_toda_capacidad_full_o_partial` exige que cada capacidad `tracker.*`
  esté **ejercitada o declarada con dueño** en `_SIN_ESCENARIO_CON_DUENO`. Motivo: 10 de las 28 capacidades
  `tracker.*` no tienen método del puerto (sync, épicas, iteraciones, milestones, etiquetas, tipos, query),
  así que el contrato del tracker no puede ejercitarlas; exigirlo sería el criterio imposible que el C3 corrigió.
- **F6 — flag OFF**: restaura la **respuesta HTTP legacy** (500 `unexpected`), no la excepción
  `NotImplementedError` literal. Motivo: reintroducirla contradiría el propio centinela de la fase
  (`raise NotImplementedError` en `backend/api/` = 0). Lo que el operador recupera es lo que consumen sus clientes.
- **F8 — apagado por flag**: el blueprint se registra siempre y el 404 se decide **dentro de la ruta**.
  Motivo: el registro se evalúa una sola vez al importar el módulo, así que gatearlo ahí obligaría a
  reiniciar el backend para que el operador viera el efecto de tocar la flag desde la UI.
- **F1 — alcance del censo de literales**: `tracker_literal_*` incluye la familia `services/ado_*.py`
  (los importadores no). Es la única lectura que reproduce los números medidos del propio plan
  (**33 archivos / 82 líneas**, §1 K4) y es coherente con su meta ("≤ 20: adaptadores + factories + defaults").

### 15.4 Pendientes / fuera de alcance de esta corrida

- **4 tests preexistentes en rojo, ajenos al 218** (verificado: los archivos que ejercitan son byte-idénticos
  a `HEAD` y ninguno está en el diff de este plan):
  `test_no_adoclient_outside_ado_provider.py` (4 módulos `ado_*` fuera de su allowlist),
  `test_plan71_ado_ci_provider.py::test_monitor_pipeline_not_implemented` (espera `NotImplementedError`;
  hoy `monitor_pipeline` intenta red real), `test_plan93_preflight_endpoint.py::test_f3_source_scan_readonly_allowlist`
  (`ado_pipeline_definitions.py:172`), y `test_agent_completion_gateway.py` (pasa aislado; está en
  `harness_ratchet_allowlist.txt` como *pendiente-de-triage*).
- **Smoke real contra una instancia GitLab** del operador: sigue siendo HITL y opcional (subplan 233).
- Los **18 subplanes 219..236** siguen sin implementar: este plan solo los cataloga y valida.
