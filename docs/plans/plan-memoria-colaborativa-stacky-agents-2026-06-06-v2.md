# Plan v2: memoria colaborativa versionada para Stacky Agents (revisado contra el código real)

| Campo | Valor |
|---|---|
| Fecha | 2026-06-06 |
| Estado | Propuesto (revisión crítica del v1) |
| Supersede a | `plan-memoria-colaborativa-stacky-agents-2026-06-06.md` (v1) |
| Método de revisión | Exploración ground-truth de 7 subsistemas + 5 críticas adversariales + síntesis (13 agentes) |
| Veredicto | Visión sólida, **sobredimensionado e infeasible tal cual está escrito**. El v1 arranca por las dos piezas de mayor riesgo y menor valor inmediato, hornea un RBAC inexistente, y duplica 6+ servicios ya productivos. Este v2 conserva el modelo de datos append-only (lo más fuerte del v1), corrige los 3 blockers y re-secuencia para entregar valor en días, no meses. |

---

## 0. Por qué un v2 (resumen de la crítica)

El v1 es un documento de diseño coherente, pero como **plan de implementación** tiene tres bloqueadores duros verificados contra el código y la máquina real:

1. **El pre-run git pull por defecto (`ff_only_block_on_dirty` + `required_before_run`) bloquearía casi toda ejecución en la única máquina real.** El workspace vivo `C:/desarrollo/GIT/RS/RSPACIFICO` está en la rama `PruebaFlujoAgentico` **sin upstream** (`git rev-parse @{u}` → `fatal: no upstream`) **y con working tree sucio**. Ambas son condiciones de bloqueo en el propio §5.4 del v1. La UX prometida ("el dev solo ve progreso") queda exactamente al revés: el dev se bloquea en el primer click.

2. **El RBAC (Developer/Lead/Curator/Admin + 403) es ficción.** No existe login, sesión, `app.secret_key`, tabla User/Role, decorador `@require_role`, ni un solo 403 en el backend. `current_user()` es literalmente `request.headers.get('X-User-Email') or 'dev@local'` (header sin validar). Es una herramienta mono-operador por construcción (DPAPI atado al usuario local). Cualquier gate "solo Curator" se evade cambiando un header.

3. **Toda la capa Git colaborativa es greenfield y empuja a un repo de cliente.** No hay ninguna infraestructura de `fetch/pull/push/clone/worktree` ni de credenciales git en el backend (`git_context.py`/`repo_explainer.py` son solo `rev-parse`/`log` locales y nunca autentican). El único credential helper configurado es **interactivo** (Git Credential Manager). El PAT DPAPI de `projects/<name>/auth` lo consume el cliente REST de ADO, **no** git. Un push de fondo o un pull síncrono **colgaría** en un prompt de credenciales en Windows.

Y un problema arquitectónico transversal: el v1 monta un **sistema de memoria paralelo** que duplica casi 1:1 servicios ya productivos (`decisions.py` con `supersedes_id`+`active`, `glossary_builder.py` con máquina de estados `pending→active`, `style_memory.py`=preference, `anti_patterns.py`=anti_pattern, `few_shot.py`=ranking de outputs aprobados, `embeddings.py`/`docs_rag.py`=TF-IDF). El v1 inyecta por el **user prompt** (`context_enrichment`) mientras esos servicios inyectan por el **system prompt** (`compose_system_prompt`): doble inyección del mismo conocimiento por dos canales, dos UIs de curación, dos implementaciones de supersede que compiten.

> **Decisión rectora del v2:** primero **memoria local inyectada** (días, riesgo casi nulo, reutiliza señales existentes). La colaboración por Git, el gate pre-run y el validador con LLM se difieren detrás de flags y solo se construyen cuando exista demanda real.

---

## 1. Hechos del código que el v1 asumió mal (ground truth)

Estos hechos condicionan todo el diseño. Cada uno está verificado.

### 1.1 Ciclo de vida de ejecución
- `POST /api/agents/run` (`api/agents.py:187`) es **síncrono-luego-thread**: llama `agent_runner.run_agent(...)` y recién al volver responde `202 {execution_id, status:"running"}`. La fila se crea con `status="running"` **hardcodeado** (`agent_runner.py:56`).
- `AgentExecution.status` es `String(20)` **sin Enum ni CHECK** (`models.py:212`) → agregar `"preparing"` no requiere migración, pero **5+ sitios hardcodean** `["running","queued"]` / `("vscode_chat","running")`: el reaper (`ticket_status.py:414`), el guard de cancel (`executions.py:188`), `agent_completion.py:43`, `metrics.py:158`, y el front `useRunningStatus`. Una fila atascada en `preparing` sería **irreaprable, incancelable y no contada**.
- `metadata_json` se lee/escribe vía la property `metadata_dict` (`models.py:258-264`) con patrón read-modify-write. Agregar una clave `pre_run` es aditivo, sin migración.
- **Tres** sitios crean filas de ejecución, no uno: `run_agent` (copilot), y **cada CLI runner** crea su **propia** fila y marca la de `run_agent` como `cancelled`/`replaced_by` (`codex_cli_runner.py:80`, `claude_code_cli_runner.py:98`). Además `open_chat` inserta su propia fila `running` directo. Cualquier lógica pre-run puesta solo en `run_agent` se aplica a la fila descartada.

### 1.2 Inyección de contexto
- `context_enrichment.enrich_blocks` se llama desde `agent_runner.py:421` **y** ambos CLI runners (`claude_code_cli_runner.py:321`, `codex_cli_runner.py:276`) → un bloque agregado ahí cubre los tres runtimes automáticamente.
- **Todos** los `_inject_*` existentes hacen **append** (`list(blocks)+[block]`). Para que la memoria quede en índice 0 hay que **prepend** explícito.
- La memoria debe ir en `content`, **no** en `metadata` (metadata nunca llega al LLM).
- **No existe ningún cap de caracteres** en `enrich_blocks`/`render_blocks`/`build_ticket_context_text`, y `max_context_chars` **no existe** en config. Los caps por agente del v1 son **código nuevo**. (Y el v1 se contradice: §9.2 Developer=14000 vs §14 `max_context_chars=12000`.)
- El bloque pasa por `pii_masker.mask_blocks` y por `output_cache` (la memoria entra en la clave de caché).

### 1.3 Persistencia
- Hay ORM (SQLAlchemy) + patrón aditivo: clase ORM nueva + línea de import en `init_db`, y helper raw-DDL `IF NOT EXISTS` (`db.py::_ensure_agent_html_publish_indexes`). `create_all` **no** emite virtual tables.
- **No hay FTS5, ni virtual tables, ni triggers en todo el código.** Las dos búsquedas existentes (`embeddings.py`, `docs_rag.py`) son **TF-IDF puro en Python** sobre columnas JSON. FTS5 en el build congelado (PyInstaller) es **no verificado y load-bearing**, y el estilo `try/except: pass` haría un fallo **silencioso**.

### 1.4 Git / workspace / config
- Cero plumbing de red git. El remoto es ADO HTTPS. `agent_env.build_agent_env` **strippea** todas las vars `*PAT*`/`*TOKEN*`. No hay `GIT_TERMINAL_PROMPT`/`GIT_ASKPASS`/`GCM_INTERACTIVE` en ningún lado.
- `ado_client._resolve_auth_header` (`ado_client.py:113,159-170`) ya construye el `Basic base64(':'+PAT)` desde el PAT DPAPI → reutilizable para `http.extraheader`.
- `projects/` está **gitignored** (`.gitignore:24`) y existe en **dos copias que divergen** (dev vs `DeployStackyAgents`). El `config.json` no es una superficie colaborativa: es per-máquina.
- La rama `stacky-memory/<project>` **no existe** en el remoto. Un worktree en el mismo remoto hereda el refspec catch-all `+refs/heads/*:refs/remotes/origin/*` (contamina los `fetch --prune` del workspace), comparte object DB/gc (bloat del repo de producto), comparte locks de worktree en Windows, y deja ramas Stacky **visibles** en el repo del cliente (`Strategist_Pacifico`).

### 1.5 Post-run / outputs
- El gate del v1 §8.2 (`contract_result score >= umbral` **Y** `verdict approved`) es **lógicamente imposible en un solo momento**: `contract_result` existe en `agent_runner.py:535` (fin de run), pero `verdict='approved'` lo setea un humano **después** vía `POST /executions/<id>/approve` (`executions.py:129 _set_verdict`). Hay que partir en **dos hooks**.
- No existe ningún `umbral`; el único número es el `70` hardcodeado en `contract_validator.validate` (que hoy solo gatea `output_cache`).
- `output_watcher` Modo A crea Tasks **sin** `AgentExecution` → un extractor keyed por `execution_id` los perdería silenciosamente.

### 1.6 Seguridad
- Ya existe un detector de secretos probado: `agent_html_output.py::_SECRET_PATTERNS`/`_scan_secrets` (ghp_, Slack xox, Google AIza, AWS AKIA, claves PEM, ADO Basic, `ADO_PAT=`) que ya levanta `SECRET_DETECTED`.
- `pii_masker.py` **enmascara reversible** (mapa por-run que **no se persiste**) — **no** es un clasificador de severidad. Para memoria persistida/exportada hay que **redactar irreversible**, no enmascarar.
- Existe `pm_llm_client.call_llm` (síncrono, backends mock/anthropic/copilot, guard `_ensure_no_raw_pii`) → es el cliente correcto para el LLM judge. `llm_router.decide()` es solo un **selector de modelo**, no completa.

---

## 2. Principios de diseño (revisados)

Se conservan los principios del v1 (local-first, append-only, Stacky-owned, no data loss, memoria curada, validación continua, trazabilidad, inyección conservadora, privacidad explícita, fallo temprano), con estas correcciones:

1. **Reutilizar antes que duplicar.** La memoria unificada **consolida o lee** los servicios FA-* existentes; nunca corre un segundo canal de inyección en paralelo.
2. **Un solo canal de inyección por conocimiento.** Si la memoria va al user prompt (`context_enrichment`), las inyecciones de system prompt no re-emiten lo mismo.
3. **Default seguro = no bloqueante.** Ninguna feature nueva bloquea una ejecución por defecto. El gate pre-run nace OFF.
4. **Roles = atribución, no autorización.** `author_email`/`author_role` se guardan para auditoría; cualquier operador puede hacer cualquier acción. RBAC real, si alguna vez se quiere, es un épico separado.
5. **Nada cuelga.** Todo subproceso git de red corre con `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=Never`, timeout duro + `terminate()`.
6. **Quarantine-and-continue.** Un chunk corrupto se aísla; nunca frena el import del resto.

---

## 3. Blockers corregidos (lo que cambia respecto del v1)

| # | Blocker v1 | Corrección v2 |
|---|---|---|
| B1 | Pre-run pull bloquea todo en la máquina real | `STACKY_PRE_RUN_GIT_PULL_ENABLED=false` por defecto. Cuando se habilite: `workspace_policy=fetch_only_warn`, `required_before_run=false`, "sin upstream" = warn no error. Primero solo el diagnóstico `/api/diag/git/pull-check` (report-only) para juntar datos antes de gatear. |
| B2 | `preparing` síncrono + SSE imposible contra el contrato actual | Partir `run()` en (a) crear fila `preparing` + abrir log_streamer + devolver `execution_id` ya; (b) pre-run + dispatch en thread de fondo que stremea etapas por el `event['type']` ya existente. Hilar `preparing` por reaper (con su **propio timeout corto** = `git_sync.timeout_seconds`, no 120 min), guard de cancel, metrics, agent_completion, `useRunningStatus`, `ExecutionStatus`. El orquestador implementa su **propio watchdog**. |
| B3 | Auth git inexistente cuelga el push/pull | Inyectar `-c http.extraheader="Authorization: Basic <b64>"` (reusar `ado_client._resolve_auth_header`) + `-c credential.helper=` (vacío) para deshabilitar GCM. Correr **solo** en el env propio del backend (nunca `build_agent_env`). Sonda `git ls-remote` en `/api/memory/status`. |
| B4 | RBAC + 403 sin sustrato | **Cortado.** `author_email`/`author_role` solo para atribución. Gates "admin" → flags de config (p.ej. `STACKY_MEMORY_ALLOW_AUTOSTASH`). Eliminar §20.6 y el test "403" del §16.4. |
| B5 | Sistema de memoria paralelo que duplica FA-* | Sección de **consolidación obligatoria** (ver §6). Elegir: (a) el store **subsume** decisions/anti_patterns/glossary/style con backfill y retira su inyección en system prompt; o (b) el store cubre solo tipos nuevos y **lee** las tablas existentes. Decidir el canal de inyección. |
| B6 | FTS5 con ranking imposible + caps inexistentes | **MVP sin FTS5**: TF-IDF al estilo `docs_rag/embeddings` (escala fino a miles, probado en build congelado). Si se quiere FTS5 luego: DDL literal de triggers (external-content, mapeo `tags_json→tags`), sonda de capacidad en `init_db` con fallback TF-IDF y log fuerte, verificación en `build_release.ps1`, ranking en 2 etapas. Resolver caps: per-agente autoritativo, `max_context_chars` techo absoluto, capping dentro de `get_context_for_run` sobre contenido post-PII. |

---

## 4. Modelo de memoria local (revisado, MVP)

### 4.1 Tabla principal
Igual al v1 §7.1 (`stacky_memory_observations`) con estas precisiones:
- Se crea como **clase ORM + import en `init_db`** (patrón aditivo existente). Sin FTS5 en MVP.
- **Clave de upsert por topic_key dependiente del scope**: `(project, scope, topic_key)` para project/team/global, pero `(project, scope, topic_key, author_email)` para personal/private (si no, dos memorias personales de devs distintos se pisan). Ajustar `ix_stacky_mem_topic` en consecuencia.
- Las columnas `author_email`/`author_role` se pueblan desde `X-User-Email` (atribución, no enforcement).

### 4.2 Búsqueda (MVP: TF-IDF, no FTS5)
- Reutilizar el tokenizer de `embeddings.py`/`docs_rag.py`. `topic_key` exacto (query con `/`) = lookup relacional por `ix_stacky_mem_topic`, **no** full-text.
- `get_context_for_run` es **dos fases**:
  1. candidatos por TF-IDF + filtro `status='active'`, `deleted_at IS NULL`, scope/project.
  2. **segunda pasada de relaciones**: cargar relaciones de los candidatos, ocultar targets de `supersedes` activos, ocultar **ambos** lados de `conflicts_with` activo-activo (y abrir finding), respetar `scoped`. *Nota:* cuando se crea una relación `supersedes`, además poner `status='superseded'` en la vieja (como hace `decisions.py`), así el filtro de status resuelve la mayoría y la pasada de relaciones solo hace falta para `conflicts_with`.

### 4.3 Ranking (corregido)
- TF-IDF/keyword da el **conjunto de candidatos**; luego se ordena por señales **0..1** (topic/agent/project/recency/confidence). No combinar linealmente un score TF-IDF crudo con indicadores 0/1 sin normalizar. (Si en el futuro se usa FTS5, normalizar bm25 a [0,1] sobre el conjunto devuelto.)

### 4.4 Caps por agente (código nuevo)
- Implementados dentro de `get_context_for_run` sobre el contenido **ya enmascarado por PII** (el enmascarado cambia la longitud). Per-agente autoritativo; `max_context_chars` techo absoluto; al exceder se dropean las memorias de menor rank.

### 4.5 Relaciones
Igual al v1 §7.3 (`stacky_memory_relations` con related/compatible/scoped/conflicts_with/supersedes/duplicates/not_conflict). Reglas de inyección del v1 §9.3 (correctas), implementadas en la segunda fase de `get_context_for_run`.

---

## 5. Inyección en contexto (revisada)

- Nuevo `_inject_stacky_memory_block` **PREPENDED** (`[block]+list(blocks)`) en `context_enrichment.enrich_blocks`, behind `STACKY_MEMORY_INJECTION_ENABLED` default **OFF**.
- Cubre los **tres** runtimes automáticamente (la función se llama en `agent_runner` + ambos CLI runners). Memoria en `content`. Pasa por `pii_masker.mask_blocks` y entra en la clave de `output_cache`.
- ContextBlock como el v1 §9.1 pero con el cuerpo en `content` (no `metadata`).

---

## 6. Consolidación con servicios existentes (sección nueva, obligatoria)

Antes de Fase B se decide **una** estrategia y se escribe:

- **Opción A (recomendada a término):** el store unificado **subsume** `decisions`/`anti_patterns`/`glossary`/`style` como `type`s de memoria, con **backfill migration**, y se **retira** su inyección en `compose_system_prompt`. Un solo canal (user prompt), una sola UI de curación, un solo supersede.
- **Opción B (MVP-friendly):** el store cubre solo tipos **genuinamente nuevos** (`session_summary`, `bugfix`, `discovery`, `client_policy`, `qa_finding`) y **lee** las tablas existentes read-only para inyectar sin re-almacenar.

> Decidir explícitamente para que el conocimiento **nunca se emita dos veces**.

---

## 7. Captura post-run (revisada: dos hooks)

- **Hook A — completion-time** (`agent_runner.py:535`): puede crear solo memorias **DRAFT** (no exportables). Reusa señales de outputs aprobados ya existentes (`few_shot._safe_score` default 70, `contract_result`).
- **Hook B — verdict-change** (`executions.py:129 _set_verdict` / endpoint approve): **promueve** draft→active (espejo de `glossary_builder.scan_approved` que ya filtra `verdict=='approved'`).
- Definir el `umbral` (hoy inexistente; el único número es `70`). Manejar ejecuciones sin `AgentExecution` (output_watcher Modo A) explícitamente.

---

## 8. Pre-run / git pull del workspace (diferido, opt-in)

- **MVP: solo `/api/diag/git/pull-check` report-only.** Reporta dirty/no-upstream/sin-credenciales **sin bloquear**.
- Cuando se habilite el gate: ver B1/B2/B3. Secuencia git corregida: `rev-parse --show-toplevel` → check enabled vs is-repo → `rev-parse --abbrev-ref HEAD` → `rev-parse @{u}` (capturar no-upstream → warn/block por policy, **no** seguir al pull) → `status --porcelain` → `fetch --prune` → `merge --ff-only @{u}` (no un segundo `pull`). Setear `core.longpaths=true`; `longPathAware` en el .exe; `GIT_TERMINAL_PROMPT=0` siempre.
- **Locks**: separar `lock_wait_timeout` de `pull_timeout`. En contención, la 2ª ejecución **no** pullea: reusa el resultado reciente si HEAD no cambió (ventana de frescura ~30s) en vez de errorear. Limpiar lockfiles git stale (`index.lock`/`HEAD.lock` por PID muerto) + `git worktree prune` en recovery.

---

## 9. Git colaborativo (diferido a Fase E, requiere consentimiento del cliente)

Se conserva el **modelo de datos append-only del v1 §6** (chunks/relations/tombstones particionados por fecha, dedupe por `chunk_id`+`sha256`, sin manifest global, índices por autor) — es lo más fuerte del v1. Correcciones:

- **Default = repo de memoria DEDICADO y separado** (`<STACKY_HOME>/memory_repos/<project>/`), **no** un worktree sobre el remoto del producto. Object DB propio, refspec propio, sin locks compartidos, sin polución del repo del cliente, bootstrap trivial (`git init` + commit vacío, sin gimnasia de orphan branches). El worktree en el mismo remoto queda como opt-in para equipos que no puedan provisionar un 2º repo, y **requiere sign-off explícito** del cliente.
- **Auth no interactiva** (B3) probada end-to-end **antes** de construir UI encima.
- **Push retry con backoff + jitter + cap** (base 1s, factor 2, cap ~30s, full jitter, cap ~6); al agotar, las filas del outbox quedan `pending` para el próximo ciclo (**no** `dead` — el fallo de push es transitorio).
- **Escritura atómica** de `.jsonl.gz`: modo binario, `gzip` con `mtime=0` (sha reproducible), temp + `os.replace()`, `core.autocrlf=false`. Test que round-trips y asegura sha byte-idéntico en Windows.
- **Tamper = quarantine-and-continue** (no block-all). Distinguir "sha difiere porque ilegible/truncado" (transitorio, reintentar) de "sha difiere y parsea" (divergencia real, quarantine + finding).
- **Bootstrap** idempotente de la rama/repo bajo el lock de proyecto.
- El test multi-clone (§16.2 v1) es el gate correcto pero **debe incluir el camino de credenciales**, no solo append/dedupe a nivel archivo.
- Export gating: solo `status=active` AND `scope ∈ {project,team,global}`; nunca personal/private por default (correcto, pero solo relevante cuando exista esta fase).

---

## 10. Validador (MVP determinista; LLM judge diferido)

- **MVP (Fase D):** tablas `validation_runs` + `findings`; **solo 4 checks** baratos y de alto valor (schema, checksum, secret vía `secret_scanner` liftado, duplicado exacto); quarantine-on-secret antes de exportar; lista de findings read-only; corre en **thread de fondo** (queued→polled), paso de pull best-effort/no-bloqueante.
- **Diferido (Fase F):** duplicados semánticos, grafo de conflictos, LLM judge (vía `pm_llm_client.call_llm`, default `mock` en tests), UI de 7 acciones, findings-as-mutations.
- **Secret scanner**: **liftar** `_SECRET_PATTERNS`/`_scan_secrets` de `agent_html_output.py` a `services/secret_scanner.py` (una sola fuente) y que `agent_html_output` importe de ahí. No reinventar.
- **PII**: definir "PII alto" concreto (contar matches distintos de `pii_masker`; cualquier clase CARD/CBU). Para memoria exportada/reinyectada **redactar irreversible** (el mapa reversible es per-run y no sobrevive).

---

## 11. Frontend (revisado, MVP mínimo)

- **MVP MemoryPage = 2 sub-tabs**: `Memorias` (lista/filtro de activas) y `Drafts` (promover). Gateada detrás de un flag `useUiSectionsStore` como pm/logs/docs. Agregar la página = 4 ediciones en `App.tsx` (union de Tab, `TAB_PATHS`, botón nav, render).
- **Diferir** Conflictos/Validaciones/Git Sync/Quarantine (dependen de backends diferidos; shippear vacíos es ruido).
- **Badges por ticket**: **mover a TicketBoard** (que itera tickets); `TeamScreen` es agente-céntrico. Diferir de MVP.
- **PreRunProgress**: es un **cambio de contrato backend-first** (B2), no una tarea de UI. Solo cuando el split de `run()` exista.

---

## 12. Fases revisadas (con tiers de riesgo y tamaño)

| Fase | Objetivo | Incluye | Tamaño/riesgo |
|---|---|---|---|
| **A — Store local + inyección (MVP)** | Inyectar memoria relevante al prompt, sin Git, sin gate | tabla `stacky_memory_observations`; TF-IDF (no FTS5); `_inject_stacky_memory_block` PREPEND en `enrich_blocks` behind flag OFF; caps por agente en `get_context_for_run`; upsert topic_key+revision_count; filtro de status; tests save/search/inject/superseded-no-inyecta | **Días / bajo** |
| **B — Captura post-run + consolidación** | Auto-alimentar y unificar FA-* | dos hooks (draft@535, promote@approve); definir `umbral`; **decisión de consolidación (A o B)**; reconciliar canal system vs user prompt; 2ª pasada de supresión por relaciones | **1-2 sem / medio** |
| **C — Pre-run opt-in (diagnóstico→gate)** | Frescura de workspace sin bloquear | split `run()` + `preparing` hilado por reaper(timeout propio)/cancel/metrics/agent_completion/useRunningStatus/ExecutionStatus; env git no interactivo; `/api/diag/git/pull-check` primero report-only; defaults OFF/`fetch_only_warn`/`required=false`; PreRunProgress SSE; cubre los 3 sitios de creación | **1-2 sem / alto** |
| **D — Validador MVP determinista** | Evitar basura/secretos/dups exactos | tablas runs/findings; 4 checks; quarantine-on-secret; lista read-only; thread de fondo | **1-2 sem / medio** |
| **E — Git sync (solo si la colaboración es real)** | Replicación multi-operador | chunks append-only + import idempotente + outbox; **repo dedicado separado**; auth no interactiva probada; push backoff/jitter/cap; recovery de lockfiles + worktree prune; escritura atómica gzip; bootstrap orphan/empty; quarantine-and-continue; E2E multi-clone **con credenciales**; **sign-off del cliente** | **Semanas / alto** |
| **F — LLM judge, UI avanzada, RBAC** | Curación avanzada y gobernanza multi-usuario | LLM judge (`pm_llm_client`); grafo de conflictos + UI 7 acciones; badges por ticket (TicketBoard). **RBAC es un épico separado**, fuera de este plan | **Maybe / fuera de scope** |

---

## 13. Decisiones del §20 del v1 (recomendación concreta)

| # | Decisión v1 | Recomendación v2 | Razón |
|---|---|---|---|
| 1 | `dedicated_memory_worktree` default | **NO para MVP** (local sin Git). Cuando haya colaboración: **repo dedicado separado**, no worktree en el remoto del cliente | Refspec catch-all, object DB/gc compartido, locks de worktree, ramas Stacky visibles en repo de producto |
| 2 | `ff_only_block_on_dirty` default | **NO** → `fetch_only_warn`; "sin upstream" = warn | El workspace real está dirty y sin upstream hoy; block_on_dirty bloquea casi todo |
| 3 | Bloquear si no se puede actualizar | **NO por default**; reporta y warnea, `required_before_run=false`; pre-run nace OFF | Bloquear destruye valor como primer cambio visible |
| 4 | Exportar solo active + no-personal | **SÍ**, pero **irrelevante hasta Fase E**; no bloquea MVP | Regla correcta y segura, pero solo aplica con Git sync |
| 5 | Humano para conflictos policy/decision/architecture | **SÍ**, pero el LLM judge está diferido a Fase F | Postura de seguridad correcta; solo activa cuando exista la capa semántica |
| 6 | Quién es Memory Curator | **ELIMINAR la pregunta** | No hay rol Curator ni sustrato de auth; usar `author_email`. Presupone RBAC inexistente |

---

## 14. Reutilizar, no duplicar (mapa concreto)

| Existente | Rol | Cómo reutilizar |
|---|---|---|
| `decisions.py` | `supersedes_id`+`active`+auto-deactivate | tipo `decision` y relación supersedes |
| `glossary_builder.py` | máquina `pending→active/rejected` | lifecycle draft/active |
| `style_memory.py` | UserStyleProfile de outputs aprobados | tipo `preference` |
| `anti_patterns.py` | scoped por agent/project, active | tipo `anti_pattern` |
| `few_shot.py` | ranking de aprobados + cap por ejemplo | ranking + `_safe_score` (default 70) |
| `embeddings.py`+`docs_rag.py` | TF-IDF coseno | búsqueda de memoria MVP (no FTS5) |
| `agent_html_output._scan_secrets` | detector de secretos probado | liftar a `secret_scanner.py` |
| `pii_masker.py` | enmascarado reversible per-run | redactar **irreversible** para memoria persistida |
| `pm_llm_client.call_llm` | LLM síncrono server-side | LLM judge (Fase F) |
| `ado_client._resolve_auth_header` | Basic base64 desde PAT DPAPI | `http.extraheader` de git (Fase E) |
| `db.py::init_db` + `_ensure_*` | patrón tabla aditiva + raw-DDL | tablas de memoria |
| `log_streamer` + `event['type']` | SSE arbitrario | progreso pre-run, sin transporte nuevo |
| `context_enrichment._inject_client_profile_block` | template de inyección | base de `_inject_stacky_memory_block` (pero PREPEND) |
| `project_manager.initialize_project` | dict-spread preserva claves | bloques `memory`/`git_sync` en config |

---

## 15. Cosas que el v1 omitió (deben quedar en el plan)

- Línea de corte de MVP explícita (este v2: Fase A).
- Estrategia de rollback por fase (qué pasa con chunks a medio importar, una ejecución atascada en `preparing`, un outbox a medio pushear al apagar un flag).
- Auth git no interactiva (el mayor riesgo práctico de cuelgue en Windows/ADO).
- Recovery de lockfiles git stale + `git worktree prune`.
- `core.longpaths`/`longPathAware` (paths profundos + árbol `.stacky-memory`).
- Sonda de capacidad FTS5 + fallback (si se adopta FTS5).
- Segunda pasada de relaciones en `get_context_for_run`.
- Reconciliación system-prompt vs user-prompt para no doble-inyectar.
- Definición operativa de `private` vs `personal`.
- Cómo sobreviven findings/relaciones mutables al modelo append-only (interplay mutation/tombstone al reabrir un finding).

---

## 16. Definición de Done (revisada, por fase)

**Fase A (MVP):** se guardan/buscan/inyectan memorias activas; topic_key actualiza revision_count; superseded/quarantined no aparecen en contexto; flag OFF por default no cambia ningún prompt; cubre los 3 runtimes; sin FTS5; sin Git; sin gate.

**Fases B–F:** criterios incrementales según la tabla §12; cada fase activable/desactivable por flag sin romper ejecuciones; diagnóstico claro.

---

## 17. Riesgos clave (revisados)

| Riesgo | Mitigación |
|---|---|
| Doble inyección por dos canales | Sección de consolidación §6, decidir antes de Fase B |
| Cuelgue por credenciales git | `GIT_TERMINAL_PROMPT=0` + `credential.helper=` vacío + extraheader + timeout/terminate; sonda `ls-remote` |
| `preparing` invisible a safety nets | Hilar por reaper(timeout propio)/cancel/metrics/agent_completion/useRunningStatus + watchdog propio |
| FTS5 falla solo en build congelado | MVP TF-IDF; si FTS5, sonda + fallback + verificación en build |
| Polución del repo del cliente | Repo de memoria dedicado separado + sign-off |
| Push livelock | backoff+jitter+cap; chunks de nombre único nunca chocan en contenido |
| Chunk corrupto frena todo | quarantine-and-continue |
| RBAC fantasma | atribución por `author_email`, sin enforcement |
