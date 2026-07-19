# Plan 202 — La Fragua Nocturna (1/6): Turno Mínimo Viable (TMV) — Orquestador, Planner de cola derivada, Ledger durable y Digest triado

- **Estado:** CRITICADO v2 (v1 RECHAZADO → corregido in place; ahora **APROBADO-CON-CAMBIOS**) — 2026-07-18 · Autor: StackyArchitectaUltraEficientCode
- **Serie:** "La Fragua Nocturna" (6 piezas: F0..F4 de serie + 1 hoja de ruta). ESTE documento es la **Fase 0 de la serie = Turno Mínimo Viable (TMV)**. Sus fases internas de implementación se numeran **Etapa 1..7 (E1..E7)** para no colisionar con las fases de serie F0..F4.
- **Nota de numeración:** la serie ocupa 202-207 (no 199-201): al redactar, 199 (cosecha telemetría), 200 (consola por incidencia) y 201 (taller de compilación) YA estaban tomados por planes ajenos. Verificado en frío listando `Stacky Agents/docs/` el 2026-07-18: el próximo `NN_` libre es 202.
- **Precedentes de formato en la casa:** plan 184 (hoja de ruta DB Compare), plan 195 (hoja de ruta DevOps), plan 197 (hoja de ruta UX), plan 198 (ledger de applies) — mismo rigor de contratos congelados y gates binarios.

## Changelog v1 → v2 (2026-07-18)

Veredicto del juez adversarial: **v1 RECHAZADO** (3 defectos BLOQUEANTES) → **corregido in place a v2 = APROBADO-CON-CAMBIOS**. Todos los anclajes portantes fueron re-verificados contra el código real; los cambios:

- **C1 (BLOQUEANTE)** `_docs_dir()` apuntaba a `app_root()/"docs"` = `Stacky Agents/backend/docs` (INEXISTENTE en dev; VERIFICADO `runtime_paths.py:30-33,36-45`: `app_root()==backend_root()` en dev) con un TODO "ajustar al helper real" ⇒ el planner escaneaba una carpeta vacía y TODA la Fragua era un no-op en producción mientras los tests (que monkeypatchean `_docs_dir`) pasaban verdes. Fijo: `backend_root().parent / "docs"` + guard de existencia + test de anclaje real.
- **C4 (BLOQUEANTE)** 9 helpers referenciados pero NUNCA definidos (`_derive_package_candidates`, `_derive_drift_candidates`, `_extract_files/_tests/_phases/_gates`, `_match_gotchas`, `_doc_for`, `_parse_conflict_paths`, `_dedup_by_key`) ⇒ E2/E4/E6 no implementables sin inventar. Fijo: nueva **§E0** con regex/lógica EXACTA de cada uno.
- **C6 (BLOQUEANTE)** `run_night` dejaba los critic sin dispatch en `pending` y `claim_next` los re-clamaba ⇒ **bucle infinito** al copiar el código verbatim (el guard vivía solo en una nota en prosa; el skip suma 0 tokens ⇒ el presupuesto nunca corta). Fijo: `claim_next(exclude_ids=…)` + set `seen` por corrida EN EL CÓDIGO.
- **C2 (IMPORTANTE)** la detección de versión negaba `v2|CRITICADO` sobre TODO el texto ⇒ un v1 genuino que menciona "CRITICADO v2" en prosa (como ESTE plan) era falso-negativo y nunca se encolaba a critic. Fijo: evaluar sobre la STATUS LINE (`derive_candidates` y `_count_backlog`).
- **C3 (IMPORTANTE)** `run_auditor` era un stub (pasos 1-4 en comentarios) y, aun implementado, corría pytest en el worktree `nightly/` (checkout de `main`), NO de la rama `impl/*` ⇒ auditaba el código equivocado y KPI-5 pasaba trivialmente (no-op ⇒ árbol intacto = falso verde). Fijo: auditor **GIT-ONLY real** (diffstat/test-files/fase→archivo por `git … base...branch`, sin checkout ni pytest); correr los tests de la rama pasa a F3.
- **C5 (IMPORTANTE)** `_match_gotchas` matcheaba contra "el índice de memoria" que vive FUERA del repo (`~/.claude/.../memory`), es del operador y no existe en Codex/Copilot ni en instalación fresca ⇒ rompía portabilidad (EXCEPCIÓN DURA #3). Fijo: `_match_gotchas` escanea el PROPIO doc (in-repo, portable).
- **C9 (IMPORTANTE)** precedentes citados (`STACKY_EVOLUTION_CENTER_ENABLED`, kill-switch del 167) viven SOLO en `impl/rsi` (sin mergear): no hay "reusa" en `main`. Fijo: precedente real `STACKY_DEVOPS_AGENT_ENABLED` (VERIFICADO `harness_flags.py:203`); kill-switch propio `STACKY_NIGHT_FOUNDRY_HARD_DISABLE` (independiente) + se sigue honrando el nombre del 167 (forward-compatible cuando RSI llegue a main).
- **C10 (IMPORTANTE)** la FlagSpec int omitía `min_value/max_value` (que `test_bounds_map_is_frozen` deriva de la FlagSpec, VERIFICADO `test_harness_flags_bounds.py:181-186`) y el plan decía NO curar la int, pero `default_is_known == (default is not None)` (VERIFICADO `harness_flags.py:3476`) ⇒ la int con `default=40000` DEBE ir a `_CURATED_DEFAULTS_ON`. Fijo: `min_value/max_value` en la FlagSpec + `_FROZEN_BOUNDS` + AMBAS keys en `_CURATED_DEFAULTS_ON`.
- **C7/C8 (MENORES)** `mergeability` trataba cualquier `rc!=0` como conflicto (rc>1 es error ⇒ ahora `unknown`); las citas a `deploy_store` sobre-afirmaban "atómico/retención/ALLOWLIST" (deploy_store NO los hace — VERIFICADO: `append_ledger` es append directo, sin `MAX_ROWS`: la Fragua EXTIENDE el patrón). Corregido.
- **[ADICIÓN ARQUITECTO]** (1) pre-reserva de presupuesto para el carril critic (`CRITIC_EST_TOKENS`) — un solo critic ya no puede exceder el techo (R2 real, no soft). (2) kill-switch de un clic desde el panel: `POST/DELETE /api/night_foundry/stop` (HITL; solo detiene/reanuda, nunca arranca autonomía).

---

## 1. Título, objetivo y KPIs

**Objetivo (1 párrafo).** Stacky ya tiene un pipeline de planes de 4 eslabones (`proponer-plan-stacky` → `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`), pero el **cuello de botella es el operador**: hoy hay decenas de planes v2 sin implementar, ramas `impl/*` sin auditar, y planes v1 sin criticar, y NADIE trabaja ese backlog cuando el operador no está mirando. La Fragua Nocturna es un **orquestador que trabaja de noche produciendo PAPEL listo-para-el-día** — críticas, auditorías read-only, y "paquetes de implementación" — que el operador revisa a la mañana ANTES de mergear o implementar. Este primer plan (TMV) construye el sustrato mínimo pero completo: (a) un **orquestador serializado** (un work item por iteración = cero colisión estructural) con presupuesto de tokens como corte duro y kill-switches redundantes; (b) un **Planner que DERIVA la cola del estado real del repo** (no una lista fija) y se regenera sola cada noche; (c) **workers por carril con dominio de archivos disjunto** — auditor AUDIT-ONLY (jamás implementa), constructor-de-paquetes, reconciliador de drift (deterministas, cero LLM) + el carril crítico que invoca el skill existente; (d) un **ledger JSONL durable** con hash de entrada para dedup + resumibilidad (si la noche se cae, la próxima retoma); (e) un **digest triado** — cola de decisiones rankeada y deduplicada (qué mergear con veredicto de mergeabilidad `git merge-tree`, qué implementar con su paquete adjunto, qué revisar) entregada por notificación. La tesis rectora está cableada como gate verificable: la Fragua **DES-ATASCA backlog, no fabrica papel** — el carril proponedor se auto-throttlea y en el TMV está reservado (no corre).

**KPIs / impacto esperado (binarios; comandos con el intérprete canónico del repo):**

| KPI | Criterio binario | Comando / verificación |
|-----|------------------|------------------------|
| KPI-1 | Ledger idempotente: 2 corridas del planner sobre el MISMO estado de repo NO duplican work items (mismo `input_hash` ⇒ se saltea) | `test_planner_idempotente_no_duplica` en `test_plan202_planner.py` |
| KPI-2 | Serialización dura: el orquestador procesa EXACTAMENTE 1 item por iteración; con 5 items en cola y kill tras el 2º, quedan 2 `done` + 3 `pending` (cero colisión) | `test_orquestador_serializa_uno_por_iteracion` |
| KPI-3 | Corte por presupuesto: con `budget=1000` y 3 items que suman 1500 tokens, el 3º NO se procesa y el digest marca `budget_exhausted: true` | `test_corte_duro_por_presupuesto` |
| KPI-4 | Resumibilidad: matar la corrida con 1 item `claimed` y re-correr ⇒ ese item se re-clama y termina; los `done` NO se re-ejecutan | `test_resume_por_hash_no_reejecuta_done` |
| KPI-5 | AUDIT-ONLY duro: el worker auditor es GIT-ONLY (diffstat/test-files/fase→archivo; cero pytest/checkout) y deja el árbol SIN cambios (`git status --porcelain` idéntico antes/después); si algo se modificó, el item se marca `failed` y el digest lo denuncia | `test_auditor_readonly_arbol_intacto` |
| KPI-6 | Anti-deuda-de-papel cableada: con backlog actual (>8 v2 sin implementar), el planner encola CERO items del carril proponedor | `test_gate_proposer_bloqueado_por_backlog` |
| KPI-7 | Digest triado: mergeabilidad correcta (rama limpia → `mergeable: true`; rama con conflicto sembrado → `false` + `conflict_paths`); decisiones deduplicadas por `target` y rankeadas | `test_digest_mergeabilidad_y_dedup` |
| KPI-8 | Kill-switches: con el archivo `STOP` presente O `STACKY_NIGHT_FOUNDRY_HARD_DISABLE=1` O `STACKY_EVOLUTION_HARD_DISABLE=1`, la corrida no procesa NADA y sale limpio | `test_killswitches_detienen_todo` |
| KPI-9 | Cero costo ocioso: con la flag ON pero sin `/loop` armado, ninguna ruta ni daemon consume tokens (todo es on-demand / lectura local) | Revisión de que ningún hook de arranque llama al orquestador (grep en `app.py`) |

**Ganancia robusta.** El operador llega a la mañana con: N paquetes listos-para-el-día (mapa de archivos con anclas + tests a escribir + checklist + gotchas aplicables + gates), M ramas `impl/*` auditadas con su veredicto de mergeabilidad, y las críticas v2 que faltaban — todo inerte, todo revisable, cero autonomía sobre el merge.

**Onboarding casi nulo.** La Fragua no cambia ningún flujo diurno. El operador ve el digest en un panel read-only y decide. Nada corre hasta que el operador arma el `/loop` (opt-in por construcción).

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo el 2026-07-18):

1. **El pipeline de planes existe pero es 100% operador-driven.** Los 4 skills viven en `.claude/skills/` (`proponer-plan-stacky`, `criticar-y-mejorar-plan`, `implementar-plan-stacky`, `supervisar-implementaciones-planes` — verificado por `ls`). Cada uno se dispara a mano. No hay ningún mecanismo que trabaje el backlog cuando el operador no está.
2. **El backlog es masivo y crece.** `Stacky Agents/docs/` tiene planes hasta el 201; la memoria del proyecto lista decenas de "CRITICADO v2 … falta implementar" y "PROPUESTO v1 … falta criticar". Las hojas de ruta 184/195/197 existen justamente porque la serie de planes hermanos se acumuló más rápido de lo que se implementa.
3. **Hay ramas `impl/*` sin consolidar.** `git branch` (2026-07-18) muestra `impl/dbcompare`, `impl/devops`, `impl/plan-159`, `impl/plan-163`, `impl/rsi`, `impl/ux` — trabajo real sin auditar ni mergear. El gotcha "worktree branch vs plan hermano" (memoria) ya mordió: docs marcados IMPLEMENTADO cuyo código vive en una rama sin mergear.
4. **La infraestructura para hacerlo bien YA está madura:** ledgers JSONL con lock son patrón de la casa (`services/deploy_store.py`: `from runtime_paths import data_dir`, `_LOCK = threading.Lock()`, `data_dir()/deploy_ledger.jsonl`, `append_ledger(entry)` — verificado `deploy_store.py:19,24,33,120`; **[C8 v2] `append_ledger` es append DIRECTO, sin tmp+replace ni `MAX_ROWS`: la Fragua EXTIENDE el patrón con escritura atómica tmp+replace, retención y ALLOWLIST**); el ledger de dev-tooling bajo el repo tiene precedente (`docs/_supervision/ledger.json`, keyed por hash del doc para no re-auditar salvo cambio — patrón que este plan REUSA para dedup/resumibilidad); `git merge-tree --write-tree` está disponible (git 2.50.1, probado read-only, devuelve tree hash sin tocar el árbol ni refs); `/loop` y `/schedule` son skills nativas de Claude Code (listadas en el harness).
5. **La serie RSI (167-170) prepara el norte pero no está mergeada.** `evolution_store.py` NO existe en el working tree (verificado: ausente); la RSI vive en la rama `impl/rsi` [INF: rama confirmada por `git branch`, código no verificado en este working tree]. F4 de esta serie conecta con RSI 167-170 — por eso F4 es futuro y depende de que RSI se merge (§8).

**Gap que cierra:** el pipeline de planes pasa de "el operador trabaja el backlog a mano, de día" a "la noche PROPONE y PREPARA papel revisable; el operador DISPONE a la mañana". Sin quitarle una sola decisión al operador.

---

## 3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop innegociable.** La noche produce PAPEL inerte (críticas, auditorías, paquetes) en archivos locales y en una rama namespaced `nightly/<fecha>`. **NUNCA** mergea a `main`, **NUNCA** hace push, **NUNCA** modifica el árbol de tests, **NUNCA** implementa código de producto. El operador revisa el digest a la mañana y decide qué mergear/implementar. Esta es la razón por la que correr de noche **NO bypasea revisión humana** (excepción dura #1 NO aplicada): la salida es inerte y se revisa ANTES de cualquier efecto.
2. **Cero trabajo extra para el operador.** Flag maestra `STACKY_NIGHT_FOUNDRY_ENABLED` default **ON** = la maquinaria está disponible (planner inspeccionable, ledger/digest legibles, botón manual "correr un turno"). **Costo ocioso = 0** (KPI-9): con la flag ON pero sin `/loop` armado, nada corre y nada consume tokens — es lectura local + on-demand. Alinea con el gotcha de la casa "ningún bool default-ON quema tokens pagos ocioso; solo SPECULATIVE (OFF) pre-ejecuta".
3. **La autonomía nocturna es opt-in POR CONSTRUCCIÓN.** No existe flag que haga correr la noche sola: el operador arma el `/loop`/`/schedule`. Si una fase FUTURA agrega un toggle in-app "armar autorun nocturno", ESE toggle nace default **OFF** citando **EXCEPCIÓN DURA #3 (prerequisito no garantizado en instalación default)** — `/loop` es nativo de Claude Code, no de Codex/Copilot — más el criterio de no-quema-ociosa. En el TMV NO hay ese toggle: se arma a mano.
4. **3 runtimes — paridad honesta con matiz declarado.** El **núcleo determinista** (ledger, planner, gate anti-deuda, auditor, constructor-de-paquetes, reconciliador, digest, mergeabilidad) es **Python puro, idéntico en los 3 runtimes, cero LLM**. La **orquestación nocturna** (`/loop`, worktrees, dispatch de skills, notificación) y **el carril crítico** (invoca el skill LLM `criticar-y-mejorar-plan`) son **Claude-Code-nativos**: Claude Code es el **runtime primario** de la Fragua. **Fallback explícito Codex/Copilot:** el operador dispara los mismos skills a mano y corre los CLIs Python deterministas; el ledger y el digest son archivos que cualquier runtime lee/escribe. NO se vende paridad falsa: solo el papel de salida y el núcleo determinista son runtime-agnósticos; el bucle y la crítica LLM son primario-Claude con degradación manual documentada (§6 por etapa).
5. **Mono-operador sin auth.** Ningún RBAC/rol. El header `current_user` no se valida ni se usa para gating.
6. **No degradar.** Backward-compatible: la Fragua agrega servicios y una ruta read-only; no toca ningún camino existente. Todo hook es best-effort (try/except + `stacky_logger`). El presupuesto de tokens es corte DURO (no hay "correr un poco más"). Reusa (todo VERIFICADO en `main`): patrón ledger de `deploy_store`, contrato de inyección 133, flags del arnés (`FlagSpec`/`_CURATED_DEFAULTS_ON`/`_REQUIRES_MAP_FROZEN`/`_FROZEN_BOUNDS`). **[C9 v2]** NO reusa símbolos de `impl/rsi` (sin mergear): el kill-switch env `STACKY_NIGHT_FOUNDRY_HARD_DISABLE` es PROPIO (además se honra el nombre `STACKY_EVOLUTION_HARD_DISABLE` del 167 como forward-compat, aunque hoy no tenga reader en `main`); los gotchas los extrae del PROPIO doc (no de la memoria del operador, que vive fuera del repo).
7. **Gotchas de la casa (obligatorios):** flag default-ON en los 5 lugares (§E7); tests registrados en AMBOS runners (`run_harness_tests.sh` **y** `.ps1`) o el meta-test rompe; pytest **POR ARCHIVO** con `.venv\Scripts\python.exe` (py3.13.5) desde `Stacky Agents\backend` (NUNCA `venv\` = py3.11.9 ajeno); config es `_config.config` (instancia), no el módulo; datos bajo `docs/` deben ser `.jsonl/.json/.txt` nunca `.md` (por eso los datos van a `data_dir()`, fuera de `docs/`, §5); criterio NO-EMPEORAR para `ratchet_meta`.

---

## 4. Lugar en la serie (1/6)

"La Fragua Nocturna" es una serie de 6 piezas. Este plan (202) es **F0 = TMV** y **fija los contratos** que las demás citan.

| Pieza | Nombre | Qué agrega | Depende de contratos de |
|-------|--------|-----------|--------------------------|
| **202 (este) — F0** | **TMV** | Orquestador serializado, planner de cola derivada, ledger durable, digest triado, 3 carriles deterministas + carril crítico. **CONGELA: esquema del ledger, esquema del digest, fingerprint de dedup/resumibilidad** (§5). | — (fundacional) |
| 203 — F1 | Robustez | Circuit breakers por carril, presupuestos en capas (por carril + global), kill-switches redundantes ampliados, reintentos con backoff. | ledger (202) |
| 204 — F2 | Multi-carril paralelo | Varios carriles en worktrees simultáneos vía Workflow, con dominios de archivo disjuntos garantizados. | ledger + dominios disjuntos (202) |
| 205 — F3 | Verificación adversarial | Un "refutador" corre ANTES del digest: intenta tumbar cada decisión (mergeabilidad real, tests que el paquete promete, drift no detectado). | digest + fingerprint (202) |
| 206 — F4 | Evolutivo (NORTE) | Conecta RSI 167-170: GEPA muta los prompts de los propios workers, el fitness 168 los puntúa, Pareto 169 retiene, el flywheel 170 cosecha lecciones; adopción HITL matutina en el Centro de Evolución (167). | ledger + digest (202) + RSI 167-170 (rama `impl/rsi`, aún sin mergear) |
| 207 — F5 | Hoja de ruta | Orden canónico de 202-206, mapa de colisiones, módulos comunes, gates compuestos (molde 195/197). | todas |

**Regla de congelamiento:** los 3 contratos de §5 son la interfaz estable. F1-F4 pueden AGREGAR campos opcionales (aditivos, backward-compatible) pero NO cambiar los existentes. Cualquier cambio de contrato obliga a re-versionar este doc y avisar a las piezas que lo citan.

---

## 5. Contratos congelados (la interfaz estable de la serie)

Todos los datos operativos de la Fragua viven en **`runtime_paths.data_dir()/night_foundry/`** (NO bajo `docs/`). Justificación: (a) es estado operativo, no documentación — pertenece con la DB en `DeployStackyAgents\data`, igual que `deploy_ledger.jsonl`; (b) sobrevive a worktrees/ramas/noches naturalmente (path estable único); (c) esquiva por completo el gotcha del indexador de docs (`doc_indexer.py:270` hace `docs_dir.rglob("*.md")` — un `.md` bajo `docs/` se indexaría; un `.jsonl`/`.json` bajo `data_dir()` jamás). El worktree/rama `nightly/<fecha>` es solo el **espacio de EJECUCIÓN** de skills y tests (aislamiento), no dónde aterrizan los datos durables.

Layout:
```
data_dir()/night_foundry/
  ledger.jsonl                 # append-only, cross-noche, retención MAX_ROWS
  STOP                         # kill-switch por archivo (si existe ⇒ no procesar)
  digests/digest-<YYYY-MM-DD>.json
  packages/<plan-NN>-<YYYY-MM-DD>.json    # paquetes listos-para-el-día
  audits/<branch-slug>-<YYYY-MM-DD>.json  # reportes de auditoría read-only
```

### 5.1 Esquema del work item (ledger) — CONGELADO

`ENTRY_FIELDS` (ALLOWLIST estricta — cualquier clave fuera de esta tupla se DESCARTA al escribir; jamás un secreto por accidente):

```python
ENTRY_FIELDS = (
    "id",           # str: identificador único del item (uuid4 hex[:12])
    "input_hash",   # str: sha256(f"{lane}|{target}|{input_signature}")[:16] — dedup + resumibilidad (§5.3)
    "lane",         # str: "critic" | "auditor" | "package" | "reconciler"  ("proposer" RESERVADO, no corre en F0)
    "target",       # str: "plan:199" | "branch:impl/devops" | "order:195#next"
    "state",        # str: "pending" | "claimed" | "done" | "failed" | "skipped"
    "output_ref",   # str|None: ruta relativa a data_dir()/night_foundry/ del artefacto, o sha de commit, o None
    "cost_tokens",  # int: tokens consumidos por el item (0 si determinista/no-LLM; estimado si desconocido)
    "attempts",     # int: reintentos (empieza en 0)
    "night",        # str: "YYYY-MM-DD" de la corrida que lo creó
    "created_at",   # str: ISO-8601 UTC
    "updated_at",   # str: ISO-8601 UTC
    "error",        # str|None: motivo si state == "failed"
)
```

### 5.2 Esquema del digest — CONGELADO

```python
DIGEST_SCHEMA = {
    "night": "YYYY-MM-DD",
    "generated_at": "ISO-8601 UTC",
    "budget_tokens": int,           # STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET vigente
    "spent_tokens": int,            # suma de cost_tokens de los items done/failed de la noche
    "budget_exhausted": bool,       # True si se cortó por presupuesto
    "stopped_reason": str,          # "queue_empty" | "budget" | "stop_file" | "hard_disable" | "error"
    "counts": {"critic": int, "auditor": int, "package": int, "reconciler": int, "failed": int},
    "decisions": [                  # cola RANKEADA + DEDUP por target (§E6)
        {
            "rank": int,            # 1 = más prioritario
            "kind": str,            # "merge" | "implement" | "review" | "reconcile"
            "title": str,           # una línea legible para el operador
            "target": str,          # "plan:199" | "branch:impl/devops"
            "verdict": str|None,    # merge: "clean" | "conflict" | "unknown"; otros: None
            "mergeable": bool|None, # merge: True/False; otros: None
            "conflict_paths": [str],# merge+conflict: rutas en conflicto; si no, []
            "package_ref": str|None,# implement: ruta al paquete; si no, None
            "cost_tokens": int,
            "dedup_key": str,       # = target (dedup entre items y entre noches)
        },
    ],
}
```

### 5.3 Fingerprint de dedup/resumibilidad — CONGELADO

`input_hash = sha256(f"{lane}|{target}|{input_signature}".encode()).hexdigest()[:16]`, donde `input_signature` por carril:

| Carril | `input_signature` | Semántica |
|--------|-------------------|-----------|
| `critic` | `sha256(bytes del doc del plan)` | re-critica SOLO si el doc cambió |
| `auditor` | `git rev-parse <branch>` (sha del tip) | re-audita SOLO si la rama se movió |
| `package` | `sha256(bytes del doc) + "#" + posicion_orden_canonico` | re-arma SOLO si el doc cambió |
| `reconciler` | `sha256(linea_de_estado_del_doc + "|" + sha_tip_rama + "|" + flags_existencia_archivos)` | re-reconcilia SOLO si algo del par doc/rama cambió |

**Regla de dedup/resume (la usa el planner, §E2):** al derivar candidatos, para cada uno se computa `input_hash`; si el ledger ya tiene un entry con ese `input_hash` en estado `done` ⇒ **NO se encola** (dedup). Si está `failed` con `attempts < MAX_ATTEMPTS` ⇒ se **re-encola** (retry idempotente). Si está `claimed` (corrida caída) ⇒ se **re-clama** en la próxima corrida. Si no hay entry ⇒ se encola `pending`. Esto es exactamente el patrón verificado de `docs/_supervision/ledger.json` (hash del doc para no re-trabajar salvo cambio), generalizado a 4 carriles.

---

## 6. Etapas E1..E7 (todo el detalle — implementable por modelo menor sin inferir)

> Convención transversal para TODAS las etapas: intérprete `.venv\Scripts\python.exe` (py3.13.5) desde `Stacky Agents\backend`; pytest **POR ARCHIVO**; cada test nuevo se registra en `backend/scripts/run_harness_tests.sh` **y** `backend/scripts/run_harness_tests.ps1` (gotcha meta-test). Cada etapa se commitea sola con sus tests verdes ANTES de la siguiente.

### E0 — Helpers deterministas compartidos (especificación EXACTA — para no inferir) [C4/C5 v2]

Todos los helpers que E2/E4/E5/E6 usaban y v1 dejaba como "descriptos arriba"/cajas negras quedan aquí con su regex/lógica EXACTA. Cero LLM, cero red, cero dependencia de nada fuera del repo. Un modelo menor los copia sin inventar. **Ubicación:** los de planes (`_doc_for`, `_derive_*`) van en `night_foundry_planner.py`; los de parseo de doc que usa `build_package` (`_extract_*`, `_match_gotchas`) van en `night_foundry_workers.py`; `_parse_conflict_paths`/`_dedup_by_key` en `night_foundry_digest.py`. Cada uno lleva su test en el `test_plan202_*` del módulo dueño.

```python
# — en night_foundry_planner.py —
def _doc_for(nn: str) -> Path:
    for p in _plan_docs():
        if p.name.startswith(f"{nn}_"): return p
    raise FileNotFoundError(f"no hay doc para plan {nn}")   # el orquestador lo captura ⇒ item failed

def _extract_files(text: str) -> list[str]:
    """Rutas entre backticks tipo `Stacky Agents/…/x.py` (dedup preservando orden)."""
    seen, out = set(), []
    for m in re.findall(r"`(Stacky Agents/[\w /.\-]+\.\w+)`", text):
        if m not in seen: seen.add(m); out.append(m)
    return out

def _extract_tests(text: str) -> list[str]:
    return sorted(set(re.findall(r"(test_[\w]+\.py)", text)))

def _extract_phases(text: str) -> list[str]:
    return re.findall(r"^#+\s*(E\d+|F\d+)\b[^\n]*", text, re.M)

def _extract_gates(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if re.search(r"Criterio|gate|ratchet|KPI-\d", l)][:40]

def _match_gotchas(text: str) -> list[str]:
    """[C5 v2] IN-REPO y portable: escanea el PROPIO doc. NO lee la memoria de ~/.claude
    (user-specific, fuera del repo, ausente en Codex/Copilot/instalación fresca)."""
    keys = ("ratchet","HARNESS_TEST_FILES","_CURATED_DEFAULTS_ON","POR ARCHIVO",".venv","gotcha",
            "_REQUIRES_MAP_FROZEN","_FROZEN_BOUNDS","doc_indexer",".md","config.config")
    low = text.lower()
    return sorted({k for k in keys if k.lower() in low})

def _roadmap_docs() -> list[Path]:
    return [p for p in _plan_docs() if re.match(r"(195|197|184)_", p.name)]

def _derive_package_candidates() -> list[tuple[str,str,str]]:
    """Primer plan NO-IMPLEMENTADO citado bajo un encabezado 'Orden de implementaci…' de cada hoja de ruta."""
    out: list[tuple[str,str,str]] = []
    for rd in _roadmap_docs():
        try:
            rtext = rd.read_text(encoding="utf-8", errors="replace")
            block = ""
            lines = rtext.splitlines()
            for i, l in enumerate(lines):
                if re.search(r"Orden de implementaci", l, re.I):
                    block = "\n".join(lines[i:i+8]); break     # ventana del bloque de orden
            for pos, nn in enumerate(re.findall(r"\b(\d{2,3})\b", block)):
                doc = next((p for p in _plan_docs() if p.name.startswith(f"{nn}_")), None)
                if doc is None: continue
                st = _status_line(doc.read_text(encoding="utf-8", errors="replace"))
                if re.search(r"IMPLEMENTADO|IMPL\b", st): continue
                sig = hashlib.sha256(doc.read_bytes()).hexdigest()
                out.append(("package", f"plan:{nn}", f"{sig}#{pos}")); break   # 1 por ruta
        except Exception:
            continue                                            # ruta que no parsea ⇒ log+skip, no rompe
    return out

def _derive_drift_candidates() -> list[tuple[str,str,str]]:
    """Plan marcado IMPLEMENTADO cuyo(s) archivo(s) citados NO están en main ⇒ candidato reconciler."""
    out: list[tuple[str,str,str]] = []
    tip = _git(["rev-parse","HEAD"])
    for doc in _plan_docs():
        nn = re.match(r"(\d+)_", doc.name).group(1)
        text = doc.read_text(encoding="utf-8", errors="replace"); st = _status_line(text)
        if not re.search(r"IMPLEMENTADO|IMPL\b", st): continue
        named = _extract_files(text)[:20]
        missing = [f for f in named
                   if subprocess.run(["git","cat-file","-e",f"main:{f}"], capture_output=True).returncode != 0]
        if missing:
            flags = ",".join("miss" if f in missing else "main" for f in named)   # firma estable, sin resolver paths FS
            sig = hashlib.sha256(f"{st}|{tip}|{flags}".encode()).hexdigest()
            out.append(("reconciler", f"plan:{nn}", sig))
    return out

# — en night_foundry_digest.py —
def _parse_conflict_paths(stdout: str) -> list[str]:
    a = set(re.findall(r"CONFLICT \([^)]*\):.*?\b(\S+\.\w+)\b", stdout))
    b = set(re.findall(r"^\s*(?:both modified:|changed in both)\s+(\S+)$", stdout, re.M))
    return sorted(a | b)                                        # si nada matchea ⇒ [] (veredicto sigue 'conflict')

def _dedup_by_key(decisions: list[dict]) -> list[dict]:
    """1 decisión por dedup_key, conservando la de MEJOR kind (menor _KIND_RANK)."""
    best: dict[str, dict] = {}
    for d in decisions:
        k = d["dedup_key"]
        if k not in best or _KIND_RANK.get(d["kind"],9) < _KIND_RANK.get(best[k]["kind"],9):
            best[k] = d
    return list(best.values())
```

**Tests (uno por helper, en el `test_plan202_*` del módulo dueño):** `test_extract_files_rutas_backtick`, `test_extract_tests_nombres`, `test_extract_phases_En_Fn`, `test_match_gotchas_in_repo_no_lee_memoria` (doc sin gotchas ⇒ []; con "ratchet" ⇒ contiene "ratchet"), `test_derive_package_primer_no_implementado`, `test_derive_drift_archivo_ausente_en_main`, `test_parse_conflict_paths`, `test_dedup_by_key_conserva_mejor_kind`, `test_doc_for_encuentra_por_prefijo`.

---

### E1 — Ledger durable (`night_foundry_ledger.py`) + fingerprint

**Objetivo (1 frase):** bitácora JSONL append-only, con lock, retención y hash de entrada — el sustrato de dedup y resumibilidad. **Valor:** sin esto no hay idempotencia ni "retomar la noche caída".

**Archivos:**
- CREAR `Stacky Agents/backend/services/night_foundry_ledger.py`
- CREAR `Stacky Agents/backend/tests/test_plan202_ledger.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1` (registrar el test)

**Contenido de `night_foundry_ledger.py` (calca `deploy_store.py`; PURO local, cero red/provider/LLM):**

```python
"""services/night_foundry_ledger.py — Plan 202 (La Fragua Nocturna F0/TMV).
Ledger JSONL durable de work items de la Fragua. Patrón de la casa: deploy_store.py:19-33,120.
PURO: cero imports de red, providers o LLM. Datos en data_dir()/night_foundry/ (NO bajo docs/)."""
from __future__ import annotations
import hashlib, json, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
import runtime_paths

MAX_ROWS = 2000
MAX_ATTEMPTS = 2
_LOCK = threading.Lock()
ENTRY_FIELDS = ( "id","input_hash","lane","target","state","output_ref",
                 "cost_tokens","attempts","night","created_at","updated_at","error" )
VALID_LANES = frozenset({"critic","auditor","package","reconciler","proposer"})
VALID_STATES = frozenset({"pending","claimed","done","failed","skipped"})

def _dir() -> Path:
    d = Path(runtime_paths.data_dir()) / "night_foundry"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _ledger_path() -> Path:
    return _dir() / "ledger.jsonl"

def compute_input_hash(lane: str, target: str, input_signature: str) -> str:
    return hashlib.sha256(f"{lane}|{target}|{input_signature}".encode()).hexdigest()[:16]

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _read_all() -> list[dict]:
    p = _ledger_path()
    if not p.exists(): return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: continue   # tolerar líneas corruptas: saltearlas
    return out

def _write_all(rows: list[dict]) -> None:
    rows = rows[-MAX_ROWS:]                       # retención: conservar los más nuevos
    tmp = _ledger_path().with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    tmp.replace(_ledger_path())                  # reemplazo atómico mismo volumen

def _sanitize(entry: dict) -> dict:
    return {k: entry.get(k) for k in ENTRY_FIELDS}   # ALLOWLIST: descarta claves ajenas

def upsert_item(lane: str, target: str, input_hash: str, *, night: str) -> dict:
    """Encola un item pending si no existe uno done con ese input_hash. Devuelve el item vigente.
    Reglas §5.3: done→dedup (devuelve el done, no crea); failed&attempts<MAX→re-encola pending
    (mismo id, state=pending); claimed→lo deja (lo re-clamará claim_next); ausente→crea pending."""
    if lane not in VALID_LANES: raise ValueError(f"lane inválido: {lane}")
    with _LOCK:
        rows = _read_all()
        for r in rows:
            if r.get("input_hash") == input_hash:
                if r.get("state") == "done":
                    return r
                if r.get("state") == "failed" and int(r.get("attempts", 0)) < MAX_ATTEMPTS:
                    r["state"] = "pending"; r["updated_at"] = _now()
                    _write_all(rows); return r
                return r
        item = _sanitize({ "id": uuid.uuid4().hex[:12], "input_hash": input_hash, "lane": lane,
            "target": target, "state": "pending", "output_ref": None, "cost_tokens": 0,
            "attempts": 0, "night": night, "created_at": _now(), "updated_at": _now(), "error": None })
        rows.append(item); _write_all(rows); return item

def claim_next(exclude_ids: set[str] | None = None) -> dict | None:
    """Atómico: toma el primer pending (o claimed huérfano) por orden de carril (critic<auditor<
    package<reconciler) y luego FIFO; lo pasa a claimed, incrementa attempts, persiste, lo devuelve.
    [C6 v2] 'exclude_ids' = ids ya vistos/salteados en ESTA corrida (p.ej. critic sin dispatch, o
    critic sin presupuesto): se excluyen del candidato para NO re-clamarlos en bucle. La exclusión es
    SOLO de esta corrida (no se persiste): en la próxima noche esos pending vuelven a ser clamables."""
    exclude_ids = exclude_ids or set()
    order = {"critic":0,"auditor":1,"package":2,"reconciler":3,"proposer":4}
    with _LOCK:
        rows = _read_all()
        cands = [r for r in rows if r.get("state") in ("pending","claimed") and r.get("id") not in exclude_ids]
        if not cands: return None
        cands.sort(key=lambda r: (order.get(r.get("lane"), 9), r.get("created_at","")))
        pick = cands[0]
        pick["state"] = "claimed"; pick["attempts"] = int(pick.get("attempts",0)) + 1
        pick["updated_at"] = _now(); _write_all(rows); return pick

def record_result(item_id: str, state: str, *, output_ref=None, cost_tokens=0, error=None) -> None:
    if state not in VALID_STATES: raise ValueError(state)
    with _LOCK:
        rows = _read_all()
        for r in rows:
            if r.get("id") == item_id:
                r["state"] = state; r["output_ref"] = output_ref
                r["cost_tokens"] = int(cost_tokens or 0); r["error"] = error; r["updated_at"] = _now()
                break
        _write_all(rows)

def list_items(night: str | None = None, state: str | None = None) -> list[dict]:
    rows = _read_all()
    if night is not None: rows = [r for r in rows if r.get("night") == night]
    if state is not None: rows = [r for r in rows if r.get("state") == state]
    return rows

def spent_tokens(night: str) -> int:
    return sum(int(r.get("cost_tokens",0) or 0) for r in list_items(night=night) if r.get("state") in ("done","failed"))
```

**Tests PRIMERO — `tests/test_plan202_ledger.py`** (monkeypatch de `runtime_paths.data_dir` a `tmp_path`):
- `test_upsert_crea_pending` — item nuevo ⇒ state pending, campos exactos de `ENTRY_FIELDS`, nada más.
- `test_allowlist_descarta_claves_ajenas` — pasar (vía un dict con `"password"`) ⇒ el JSON escrito NO tiene esa clave.
- `test_dedup_done_no_recrea` (KPI-1) — upsert 2× con el mismo `input_hash` tras marcar el 1º done ⇒ devuelve el done, el ledger tiene 1 sola línea.
- `test_failed_reencola_hasta_max_attempts` — failed con attempts=1 ⇒ re-encola pending; con attempts=MAX ⇒ queda failed.
- `test_claim_next_orden_de_carril` — con pending de auditor y critic, `claim_next` devuelve el critic primero.
- `test_retencion_max_rows` — MAX_ROWS+5 items ⇒ archivo con MAX_ROWS líneas, las más nuevas.
- `test_lineas_corruptas_se_saltean` — sembrar una línea basura ⇒ `_read_all` la ignora sin romper.
- `test_spent_tokens_suma_done_y_failed`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_ledger.py -q` (cwd `Stacky Agents\backend`).
**Criterio de aceptación (binario):** los 8 tests pasan; `python -m compileall services/night_foundry_ledger.py` limpio.
**Flag:** protegido aguas arriba por `STACKY_NIGHT_FOUNDRY_ENABLED` (se cablea en E7); el módulo en sí es librería pura.
**Runtime + fallback:** idéntico en los 3 (Python puro). **Trabajo del operador:** ninguno.

---

### E2 — Planner: cola DERIVADA del estado del repo (`night_foundry_planner.py`)

**Objetivo (1 frase):** escanear el repo y DERIVAR (no listar fija) el trabajo real, priorizado, encolándolo en el ledger con dedup. **Valor:** la cola se regenera sola cada noche; refleja el backlog verdadero.

**Archivos:**
- CREAR `Stacky Agents/backend/services/night_foundry_planner.py`
- CREAR `Stacky Agents/backend/tests/test_plan202_planner.py`
- EDITAR ambos runners.

**Derivaciones (cada una produce candidatos `(lane, target, input_signature)`):**

1. **Planes v1 sin criticar → carril `critic`.** Escanear `Stacky Agents/docs/NNN_PLAN_*.md`; leer la línea de Estado (regex `Estado:` / `Versión:`); si dice `PROPUESTO v1` y NO existe marca `v2`/`CRITICADO` ⇒ candidato `("critic", f"plan:{NN}", sha256(doc_bytes))`.
2. **Ramas `impl/*` sin auditar → carril `auditor`.** `git for-each-ref --format='%(refname:short) %(objectname)' refs/heads/impl` ⇒ por cada rama, candidato `("auditor", f"branch:{rama}", tip_sha)`.
3. **Próximo del orden canónico → carril `package`.** Leer las hojas de ruta existentes (`195`, `197`, y `184` si existe) buscando su tabla de "Orden de implementación"; tomar el PRIMER plan de cada ruta cuyo doc NO esté marcado IMPLEMENTADO ⇒ candidato `("package", f"plan:{NN}", sha256(doc_bytes)+"#"+pos)`. Si una ruta no parsea, se saltea con log (no rompe).
4. **Drift doc-vs-rama → carril `reconciler`.** Por cada plan marcado `IMPLEMENTADO` en su doc, verificar si el/los archivo(s) que nombra existen en `main`; si el doc dice IMPLEMENTADO pero el archivo solo existe en una rama `impl/*` (o no existe) ⇒ candidato `("reconciler", f"plan:{NN}", sha256(estado+tip+flags))`.

```python
"""services/night_foundry_planner.py — Plan 202. Deriva la cola de trabajo del estado del repo.
Determinista, cero LLM. Reusa night_foundry_ledger para encolar con dedup."""
from __future__ import annotations
import hashlib, re, subprocess
from pathlib import Path
import runtime_paths
from services import night_foundry_ledger as L

MAX_V2_UNIMPLEMENTED = 8          # WIP kanban (§E3)

def _docs_dir() -> Path:
    # [C1 v2] VERIFICADO runtime_paths.py:30-33,36-45 — en dev app_root()==backend_root()==Stacky Agents/backend,
    # así que app_root()/"docs" apuntaría a Stacky Agents/backend/docs (INEXISTENTE). Los planes viven en
    # Stacky Agents/docs. La Fragua es una herramienta de repo (opera ramas/planes del working tree): resolvemos
    # SIEMPRE contra el árbol del repo = backend_root().parent/"docs".
    return runtime_paths.backend_root().parent / "docs"

def _docs_dir_ok() -> bool:
    d = _docs_dir()
    return d.exists() and d.is_dir()

def _plan_docs() -> list[Path]:
    if not _docs_dir_ok(): return []      # [C1 v2] docs dir ausente ⇒ [] (no crash), la noche no deriva nada
    return sorted(_docs_dir().glob("[0-9]*_PLAN_*.md"))

def _status_line(text: str) -> str:
    for line in text.splitlines()[:12]:
        if "Estado:" in line or "Versión:" in line or "Version:" in line:
            return line
    return ""

def _git(args: list[str]) -> str:
    try: return subprocess.run(["git", *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception: return ""

def derive_candidates() -> list[tuple[str, str, str]]:
    cands: list[tuple[str,str,str]] = []
    for doc in _plan_docs():
        nn = re.match(r"(\d+)_", doc.name).group(1)
        raw = doc.read_bytes(); text = raw.decode("utf-8", "replace"); status = _status_line(text)
        doc_sig = hashlib.sha256(raw).hexdigest()
        # [C2 v2] el negativo se evalúa sobre la STATUS LINE, no sobre todo el texto: un v1 genuino
        # puede mencionar "CRITICADO v2" en su prosa (como ESTE plan 202) y sería falso-negativo.
        if re.search(r"PROPUESTO v1", status) and not re.search(r"v2|CRITICADO", status):
            cands.append(("critic", f"plan:{nn}", doc_sig))
    for line in _git(["for-each-ref","--format=%(refname:short) %(objectname)","refs/heads/impl"]).splitlines():
        parts = line.split()
        if len(parts) == 2:
            cands.append(("auditor", f"branch:{parts[0]}", parts[1]))
    cands += _derive_package_candidates()
    cands += _derive_drift_candidates()
    return cands

def plan_night(night: str) -> dict:
    """Encola en el ledger todos los candidatos derivados (con dedup por input_hash) EXCEPTO el
    carril proposer, que pasa por el gate anti-deuda (§E3). Devuelve un resumen de conteos."""
    cands = derive_candidates()
    enq = {"critic":0,"auditor":0,"package":0,"reconciler":0,"proposer":0,"skipped_dedup":0}
    for lane, target, sig in cands:
        ih = L.compute_input_hash(lane, target, sig)
        before = L.list_items()
        item = L.upsert_item(lane, target, ih, night=night)
        if any(r["input_hash"] == ih and r["state"] == "done" for r in before):
            enq["skipped_dedup"] += 1
        else:
            enq[lane] += 1
    # proposer: SOLO si el gate lo permite (en F0 el backlog lo bloquea de facto — KPI-6)
    gate = foundry_backlog_gate()
    if gate["proposer_allowed"]:
        pass  # F0: derivación proposer reservada, no implementada; el gate ya devuelve False
    return {"enqueued": enq, "gate": gate}
```

(`_derive_package_candidates` y `_derive_drift_candidates`: **especificación EXACTA en §E0** — cada uno con su test.)

**Tests PRIMERO — `tests/test_plan202_planner.py`** (fixture: un `tmp_path/docs/` con 2-3 planes sembrados de estados distintos + monkeypatch de `_docs_dir` y de `_git`):
- `test_docs_dir_resuelve_a_carpeta_de_planes` ([C1] SIN monkeypatch: `_docs_dir()` existe y contiene `202_PLAN_*.md` — protege contra la regresión del path a `backend/docs`).
- `test_deriva_critic_de_v1_sin_criticar` — doc `PROPUESTO v1` sin v2 ⇒ candidato critic; doc con `v2` en su STATUS LINE ⇒ NO; **[C2] doc v1 que MENCIONA "CRITICADO v2" en su PROSA ⇒ SIGUE siendo candidato critic** (regresión del falso-negativo).
- `test_deriva_auditor_de_ramas_impl` — `_git` mockeado devuelve 2 ramas impl ⇒ 2 candidatos auditor con el tip sha correcto.
- `test_deriva_reconciler_por_drift` — doc IMPLEMENTADO cuyo archivo no está en main ⇒ candidato reconciler.
- `test_planner_idempotente_no_duplica` (KPI-1) — correr `plan_night` 2× sobre el mismo estado ⇒ la 2ª no agrega items nuevos (todos dedup).
- `test_proposer_no_se_encola_en_f0` (KPI-6) — con backlog >8 v2, `plan_night` deja `enqueued["proposer"] == 0`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_planner.py -q`.
**Criterio (binario):** los 5 tests pasan.
**Flag / runtime / operador:** protegido por la flag maestra (E7); Python puro idéntico en los 3; operador: ninguno.

---

### E3 — Gate anti-deuda-de-papel (`foundry_backlog_gate` en el planner) — la tesis cableada

**Objetivo (1 frase):** convertir la tesis "des-atascar, no fabricar papel" en un gate verificable que bloquea el carril proponedor. **Valor:** la Fragua no puede generar más papel del que el operador puede consumir.

**Archivos:** EDITAR `night_foundry_planner.py` (agregar la función); EDITAR `test_plan202_planner.py` (agregar casos). Sin archivos nuevos.

```python
def _count_backlog() -> dict:
    v1_uncriticized = v2_unimplemented = 0
    for doc in _plan_docs():
        text = doc.read_text(encoding="utf-8", errors="replace"); status = _status_line(text)
        # [C2 v2] mismos criterios sobre la STATUS LINE (no sobre todo el texto).
        if re.search(r"PROPUESTO v1", status) and not re.search(r"v2|CRITICADO", status):
            v1_uncriticized += 1
        if re.search(r"CRITICADO v2|APROBADO-CON-CAMBIOS", status) and not re.search(r"IMPLEMENTADO|IMPL\b", status):
            v2_unimplemented += 1
    return {"v1_uncriticized": v1_uncriticized, "v2_unimplemented": v2_unimplemented}

def foundry_backlog_gate(night: str | None = None) -> dict:
    """La tesis rectora como gate: el carril proposer NO corre si hay deuda de papel.
    Bloquea si: v1 sin criticar > 0  O  v2 sin implementar > MAX_V2_UNIMPLEMENTED  O  el ratio
    generar:consumir de la noche superaría 1:3 (proposer_items > floor(consume_items/3)).
    En F0 el proposer está reservado ⇒ este gate garantiza estructuralmente ratio 0:N."""
    b = _count_backlog()
    consume = 0
    if night is not None:
        consume = sum(1 for r in L.list_items(night=night) if r.get("lane") in ("critic","auditor","package","reconciler"))
    proposer_ceiling = consume // 3
    blocked_reason = ""
    if b["v1_uncriticized"] > 0: blocked_reason = "hay planes v1 sin criticar (criticá antes de proponer)"
    elif b["v2_unimplemented"] > MAX_V2_UNIMPLEMENTED: blocked_reason = f"{b['v2_unimplemented']} planes v2 sin implementar (> {MAX_V2_UNIMPLEMENTED})"
    elif proposer_ceiling < 1: blocked_reason = "ratio generar:consumir < 1:3 esta noche"
    return {"proposer_allowed": blocked_reason == "", "reason": blocked_reason,
            "proposer_ceiling": proposer_ceiling, "metrics": b}
```

**Tests PRIMERO (agregar a `test_plan202_planner.py`):**
- `test_gate_bloquea_por_v1_sin_criticar` — sembrar 1 v1 sin criticar ⇒ `proposer_allowed False`, reason menciona v1.
- `test_gate_bloquea_por_v2_sin_implementar` — sembrar 9 v2 sin implementar, 0 v1 ⇒ bloqueado por umbral WIP.
- `test_gate_bloquea_por_ratio` — 0 v1, 0 v2, night con 2 items consume ⇒ `proposer_ceiling 0` ⇒ bloqueado.
- `test_gate_permite_cuando_backlog_limpio` — 0 v1, 0 v2, night con 6 consume ⇒ `proposer_allowed True`, ceiling 2.
- `test_gate_proposer_bloqueado_por_backlog` (KPI-6, ya en E2) — end-to-end vía `plan_night`.

**Comando / criterio:** mismo archivo; los casos nuevos pasan.
**Flag / runtime / operador:** igual que E2.

---

### E4 — Workers deterministas por carril (`night_foundry_workers.py`) — auditor AUDIT-ONLY, paquetes, reconciliador

**Objetivo (1 frase):** ejecutar cada work item NO-LLM produciendo su artefacto, con dominio de archivos disjunto y el límite AUDIT-ONLY duro. **Valor:** 3 de los 4 carriles corren en cualquier runtime sin LLM.

**Archivos:**
- CREAR `Stacky Agents/backend/services/night_foundry_workers.py`
- CREAR `Stacky Agents/backend/tests/test_plan202_workers.py`
- EDITAR ambos runners.

**Dominios de salida DISJUNTOS (cada carril escribe SOLO en su namespace bajo `data_dir()/night_foundry/`):** auditor → `audits/`; package → `packages/`; reconciler → dentro del propio digest (no escribe archivo aparte, devuelve dict). El carril critic (E5/E7) escribe el doc del plan vía el skill, en la rama `nightly/<fecha>`. Con serialización (un item por iteración, §E5) NO hay dos escrituras simultáneas ni siquiera dentro de un carril.

```python
"""services/night_foundry_workers.py — Plan 202. Workers deterministas (cero LLM) por carril.
El carril 'critic' NO está acá: lo dispara el orquestador Claude-nativo (E5/E7) vía skill."""
from __future__ import annotations
import json, re, subprocess
from datetime import datetime, timezone
from pathlib import Path
import runtime_paths

def _nf_dir(sub: str) -> Path:
    d = Path(runtime_paths.data_dir()) / "night_foundry" / sub
    d.mkdir(parents=True, exist_ok=True); return d

def run_auditor(branch: str, base: str = "main") -> dict:
    """AUDIT-ONLY DURO, determinista, GIT-ONLY (cero pytest, cero checkout, cero LLM).
    [C3 v2] En F0 el auditor NO corre los tests de la rama: eso exige checkout de la rama en un
    worktree propio y es del refutador F3 (correr pytest en el worktree 'nightly/' —checkout de main—
    auditaría el código EQUIVOCADO). El auditor F0 produce un reporte read-only del delta rama-vs-base
    leyendo objetos git ('git … base...branch' NO altera árbol/index/refs):
      - diffstat:   'git diff --stat base...branch'
      - test_files: 'git diff --name-only base...branch' filtrado a rutas de test (…/test_*.py)
      - phase_map:  archivos .py cambiados (mapa fase→archivo determinista, sin ejecutar nada)
    POST-CONDICIÓN (KPI-5): 'git status --porcelain' idéntico antes/después; si difiere ⇒ readonly_ok
    False y el item se marca failed (denuncia de violación read-only). Devuelve dict + cost_tokens 0."""
    before = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True).stdout
    rng = f"{base}...{branch}"
    diffstat = subprocess.run(["git","diff","--stat",rng], capture_output=True, text=True, timeout=60).stdout
    names = subprocess.run(["git","diff","--name-only",rng], capture_output=True, text=True, timeout=60).stdout.splitlines()
    test_files = [n for n in names if re.search(r"(^|/)test_\w+\.py$", n)]
    changed_py = [n for n in names if n.endswith(".py")]
    after = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True).stdout
    report = {"branch": branch, "base": base, "diffstat": diffstat, "test_files": test_files,
              "changed_py": changed_py, "phase_map": changed_py, "readonly_ok": (before == after)}
    out = _nf_dir("audits") / f"{branch.replace('/','-')}-{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_ref": f"audits/{out.name}", "cost_tokens": 0, "readonly_ok": report["readonly_ok"]}

def build_package(plan_nn: str, doc_path: Path) -> dict:
    """Constructor del 'paquete listo-para-el-día' (determinista, extrae de la estructura del doc):
    - mapa de archivos a tocar con líneas ancla (parse de las secciones 'Archivos:' del plan)
    - lista de tests a escribir con qué asertan (parse de 'Tests PRIMERO')
    - checklist de fases F0..Fn (o E1..En)
    - gotchas aplicables extraídos del PROPIO doc ([C5 v2] `_match_gotchas` in-repo/portable; NO lee ~/.claude)
    - gates/ratchets a pasar (parse de 'Criterio' / 'gate' / 'ratchet' del doc)
    Todos los `_extract_*`/`_match_gotchas`: especificación EXACTA en §E0.
    Escribe packages/<plan-NN>-<fecha>.json. NO escribe código de producto."""
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    pkg = {"plan": plan_nn, "files_to_touch": _extract_files(text), "tests_to_write": _extract_tests(text),
           "phase_checklist": _extract_phases(text), "gotchas": _match_gotchas(text), "gates": _extract_gates(text)}
    out = _nf_dir("packages") / f"plan-{plan_nn}-{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_ref": f"packages/{out.name}", "cost_tokens": 0}

def run_reconciler(plan_nn: str, doc_path: Path) -> dict:
    """Compara el estado declarado del doc (IMPLEMENTADO / CRITICADO / PROPUESTO) contra la realidad
    del código (¿el archivo que nombra existe en main? ¿solo en impl/*? ¿no existe?). Devuelve un
    dict de drift para el digest (no escribe archivo aparte). Cero LLM, cero mutación."""
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    declared = "IMPLEMENTADO" if re.search(r"IMPLEMENTADO", text[:400]) else "otro"
    named = re.findall(r"`(Stacky Agents/backend/[\w/]+\.py)`", text)
    drift = []
    for f in named[:20]:
        in_main = subprocess.run(["git","cat-file","-e",f"main:{f}"], capture_output=True).returncode == 0
        if declared == "IMPLEMENTADO" and not in_main:
            drift.append({"file": f, "issue": "doc dice IMPLEMENTADO pero el archivo no está en main"})
    return {"plan": plan_nn, "declared": declared, "drift": drift, "cost_tokens": 0}
```

**Tests PRIMERO — `tests/test_plan202_workers.py`** (fixtures con docs sembrados; `subprocess` monkeypatcheado donde toque):
- `test_auditor_readonly_arbol_intacto` (KPI-5) — `git status --porcelain` idéntico antes/después ⇒ `readonly_ok True`; simular una modificación ⇒ `readonly_ok False`.
- `test_auditor_reporta_diffstat_y_test_files` ([C3] git mock: `git diff --name-only` devuelve un `test_*.py` ⇒ `report["test_files"]` no vacío; el auditor NO invoca pytest — assert que `subprocess` de pytest jamás se llamó).
- `test_auditor_escribe_solo_en_audits` — el único archivo creado está bajo `audits/` (dominio disjunto).
- `test_build_package_extrae_secciones` — doc sembrado con "Archivos:"/"Tests PRIMERO" ⇒ el paquete tiene `files_to_touch` y `tests_to_write` no vacíos; el archivo cae en `packages/`.
- `test_build_package_matchea_gotchas` — doc que menciona "ratchet"/"HARNESS_TEST_FILES" ⇒ `gotchas` no vacío.
- `test_reconciler_detecta_drift` — doc IMPLEMENTADO nombrando un archivo ausente de main (git mock) ⇒ `drift` no vacío.
- `test_reconciler_sin_drift_cuando_archivo_en_main`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_workers.py -q`.
**Criterio (binario):** los 6 tests pasan; los 3 workers escriben SOLO en su namespace.
**Flag / runtime / operador:** flag maestra (E7); **Python puro idéntico en los 3 runtimes** (el operador Codex/Copilot los corre como CLI); operador: ninguno.

---

### E5 — Orquestador serializado (`night_foundry_orchestrator.py`): loop, corte por presupuesto, resume, kill-switches

**Objetivo (1 frase):** drenar la cola de a UN item por iteración, cortando duro por presupuesto o kill-switch, de forma resumible. **Valor:** el corazón de "un work item por iteración = cero colisión".

**Archivos:**
- CREAR `Stacky Agents/backend/services/night_foundry_orchestrator.py`
- CREAR `Stacky Agents/backend/tests/test_plan202_orchestrator.py`
- EDITAR ambos runners.

```python
"""services/night_foundry_orchestrator.py — Plan 202. Coordinador determinista del turno nocturno.
El dispatch del carril 'critic' (LLM) lo hace el skill Claude-nativo (E7) llamando a estas funciones;
los carriles deterministas los ejecuta run_deterministic_item() directamente."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
import runtime_paths
from services import night_foundry_ledger as L
from services import night_foundry_workers as W

def _stop_file() -> Path:
    return Path(runtime_paths.data_dir()) / "night_foundry" / "STOP"

def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1","true","yes","on")

def should_stop(night: str, budget: int) -> tuple[bool, str]:
    # [C9 v2] Dos kill-switches env: STACKY_NIGHT_FOUNDRY_HARD_DISABLE (PROPIO, independiente) y
    # STACKY_EVOLUTION_HARD_DISABLE (mismo nombre que el 167; hoy SIN reader en main —forward-compatible:
    # cuando RSI llegue a main, un solo botón detiene RSI Y la Fragua). Honramos ambos.
    if _env_on("STACKY_NIGHT_FOUNDRY_HARD_DISABLE") or _env_on("STACKY_EVOLUTION_HARD_DISABLE"):
        return True, "hard_disable"
    if _stop_file().exists():
        return True, "stop_file"
    if L.spent_tokens(night) >= budget:
        return True, "budget"
    return False, ""

def run_deterministic_item(item: dict) -> dict:
    """Ejecuta un item de carril determinista (auditor/package/reconciler). El critic NO entra acá."""
    lane, target = item["lane"], item["target"]
    if lane == "auditor":
        return W.run_auditor(target.split("branch:",1)[1])
    if lane == "package":
        nn = target.split("plan:",1)[1]
        return W.build_package(nn, _doc_for(nn))
    if lane == "reconciler":
        nn = target.split("plan:",1)[1]
        r = W.run_reconciler(nn, _doc_for(nn))
        return {"output_ref": None, "cost_tokens": 0, "reconciler": r}
    raise ValueError(f"carril no determinista: {lane}")

CRITIC_EST_TOKENS = 6000   # [ADICIÓN ARQUITECTO v2] estimado de costo de UNA crítica LLM. Se PRE-RESERVA
                           # contra el presupuesto ANTES de dispatchar: el costo real solo se conoce
                           # post-hoc, así que sin pre-carga un solo critic podría exceder el techo (R2).

def run_night(night: str | None = None, *, budget: int, dispatch_critic=None) -> dict:
    """Loop serializado. UN item por iteración. Antes de CADA item chequea should_stop.
    Idempotente/resumible: claim_next re-clama huérfanos; los done nunca se re-ejecutan.
    'dispatch_critic' (callable) lo inyecta el skill Claude-nativo para el carril LLM; si es None,
    los items critic se dejan pending (fallback Codex/Copilot: el operador los corre a mano).
    [C6 v2] 'seen' = ids salteados esta corrida (critic sin dispatch, o critic sin presupuesto): se
    pasan a claim_next(exclude_ids=seen) para NO re-clamarlos ⇒ el loop TERMINA en vez de colgarse."""
    night = night or f"{datetime.now(timezone.utc):%Y-%m-%d}"
    stopped = "queue_empty"; seen: set[str] = set()
    while True:
        stop, why = should_stop(night, budget)
        if stop: stopped = why; break
        item = L.claim_next(exclude_ids=seen)
        if item is None: stopped = "queue_empty"; break
        if item["lane"] == "critic":
            # [C6 v2] fallback sin runtime Claude: dejar pending y NO re-clamar esta corrida (seen).
            if dispatch_critic is None:
                L.record_result(item["id"], "pending"); seen.add(item["id"]); continue
            # [ADICIÓN ARQUITECTO v2] pre-reserva de presupuesto: si la estimación excede el techo, no
            # dispatchar (dejar pending para la próxima noche), marcar seen y cortar por budget.
            if L.spent_tokens(night) + CRITIC_EST_TOKENS > budget:
                L.record_result(item["id"], "pending"); seen.add(item["id"]); stopped = "budget"; break
        try:
            if item["lane"] == "critic":
                res = dispatch_critic(item)              # invoca el skill criticar-y-mejorar-plan
            else:
                res = run_deterministic_item(item)
            L.record_result(item["id"], "done", output_ref=res.get("output_ref"), cost_tokens=res.get("cost_tokens",0))
        except Exception as e:
            L.record_result(item["id"], "failed", error=str(e)[:300])
    return {"night": night, "stopped_reason": stopped, "spent_tokens": L.spent_tokens(night)}
```

Nota [C6 v2 — RESUELTO EN EL CÓDIGO]: el guard anti-bucle YA está implementado (set `seen` + `claim_next(exclude_ids=seen)`): un critic sin `dispatch` (o sin presupuesto para su pre-reserva) se deja `pending`, se agrega a `seen` y no se re-clama esta corrida; el loop corta cuando solo quedan items ya vistos (`claim_next` devuelve `None`). Cubierto por `test_critic_sin_dispatch_no_bucle` y `test_critic_precarga_presupuesto_no_excede`.

**Tests PRIMERO — `tests/test_plan202_orchestrator.py`** (ledger en `tmp_path`; workers monkeypatcheados para devolver `cost_tokens` fijos):
- `test_orquestador_serializa_uno_por_iteracion` (KPI-2) — 5 items; `should_stop` fuerza corte tras 2 ⇒ 2 done + 3 pending.
- `test_corte_duro_por_presupuesto` (KPI-3) — budget 1000; 3 items de 500 c/u ⇒ 2 done (1000), el 3º pending, `stopped_reason "budget"`.
- `test_resume_por_hash_no_reejecuta_done` (KPI-4) — dejar 1 claimed + 1 done; re-`run_night` ⇒ el done no se toca, el claimed se termina.
- `test_killswitches_detienen_todo` (KPI-8) — con `STOP` presente ⇒ 0 items procesados, `stopped_reason "stop_file"`; con env `STACKY_EVOLUTION_HARD_DISABLE=1` ⇒ `"hard_disable"`.
- `test_critic_sin_dispatch_no_bucle` — items critic con `dispatch_critic=None` ⇒ quedan pending, el loop termina (guard anti-bucle `seen`+`exclude_ids`; sin guard sería bucle infinito).
- `test_critic_precarga_presupuesto_no_excede` (ADICIÓN v2) — con `budget=1000`, `CRITIC_EST_TOKENS=6000` y 1 critic + deterministas: el critic NO se dispatcha (queda pending, `stopped_reason "budget"`), los deterministas sí corren.
- `test_hard_disable_propio_detiene` (C9) — con `STACKY_NIGHT_FOUNDRY_HARD_DISABLE=1` ⇒ 0 procesados, `stopped_reason "hard_disable"` (independiente del env del 167).
- `test_item_que_lanza_queda_failed` — worker que lanza ⇒ item failed con `error`, la corrida sigue.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_orchestrator.py -q`.
**Criterio (binario):** los 6 tests pasan.
**Flag:** `STACKY_NIGHT_FOUNDRY_ENABLED` + presupuesto `STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET` (E7).
**Runtime + fallback:** el loop determinista es Python puro (los 3 runtimes). El `dispatch_critic` es Claude-nativo; sin él, los critic quedan pending y el operador los corre a mano (fallback declarado). **Trabajo del operador:** ninguno en Claude; en Codex/Copilot, correr el skill critic a mano si quiere esas críticas.

---

### E6 — Digest triado (`night_foundry_digest.py`): rank + dedup + mergeabilidad + entrega

**Objetivo (1 frase):** convertir el ledger de la noche en una cola de DECISIONES rankeada, deduplicada y con veredicto de mergeabilidad, y entregarla. **Valor:** el operador ve QUÉ hacer, no un volcado de logs.

**Archivos:**
- CREAR `Stacky Agents/backend/services/night_foundry_digest.py`
- CREAR `Stacky Agents/backend/tests/test_plan202_digest.py`
- EDITAR ambos runners.

**Mergeabilidad (read-only, verificada [V] con git 2.50.1):** `git merge-tree --write-tree <base> <branch>` — exit 0 + tree hash ⇒ `mergeable: true, verdict: "clean"`; **[C7 v2] exit 1 ⇒ conflicto** (parsear secciones de conflicto para `conflict_paths`); **exit >1 (o excepción/timeout) ⇒ error ⇒ `verdict: "unknown", mergeable: None`** (NO confundir un error —ref inexistente— con un conflicto). NO toca working tree ni refs (escribe objetos sueltos inalcanzables que GC recolecta; `git status` queda limpio).

```python
"""services/night_foundry_digest.py — Plan 202. Digest triado de la noche (contrato §5.2)."""
from __future__ import annotations
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
import runtime_paths
from services import night_foundry_ledger as L

_KIND_RANK = {"merge": 0, "implement": 1, "review": 2, "reconcile": 3}   # orden de valor para el operador

def mergeability(branch: str, base: str = "main") -> dict:
    try:
        p = subprocess.run(["git","merge-tree","--write-tree",base,branch], capture_output=True, text=True, timeout=60)
    except Exception:
        return {"verdict": "unknown", "mergeable": None, "conflict_paths": []}
    if p.returncode == 0:
        return {"verdict": "clean", "mergeable": True, "conflict_paths": []}
    if p.returncode == 1:                            # [C7 v2] SOLO rc==1 es conflicto real
        return {"verdict": "conflict", "mergeable": False, "conflict_paths": _parse_conflict_paths(p.stdout)}
    return {"verdict": "unknown", "mergeable": None, "conflict_paths": []}  # rc>1 = error (ref inexistente, etc.)

def build_digest(night: str, *, budget: int, stopped_reason: str) -> dict:
    items = L.list_items(night=night)
    decisions: list[dict] = []
    for it in items:
        if it["state"] not in ("done",): continue
        lane = it["lane"]
        if lane == "auditor":
            branch = it["target"].split("branch:",1)[1]; m = mergeability(branch)
            decisions.append({"kind":"merge","title":f"Rama {branch}: {m['verdict']}","target":it["target"],
                "verdict":m["verdict"],"mergeable":m["mergeable"],"conflict_paths":m["conflict_paths"],
                "package_ref":None,"cost_tokens":it["cost_tokens"],"dedup_key":it["target"]})
        elif lane == "package":
            decisions.append({"kind":"implement","title":f"Paquete listo: {it['target']}","target":it["target"],
                "verdict":None,"mergeable":None,"conflict_paths":[],"package_ref":it["output_ref"],
                "cost_tokens":it["cost_tokens"],"dedup_key":it["target"]})
        elif lane == "critic":
            decisions.append({"kind":"review","title":f"Crítica v2 lista: {it['target']}","target":it["target"],
                "verdict":None,"mergeable":None,"conflict_paths":[],"package_ref":it["output_ref"],
                "cost_tokens":it["cost_tokens"],"dedup_key":it["target"]})
        elif lane == "reconciler":
            decisions.append({"kind":"reconcile","title":f"Drift: {it['target']}","target":it["target"],
                "verdict":None,"mergeable":None,"conflict_paths":[],"package_ref":None,
                "cost_tokens":it["cost_tokens"],"dedup_key":it["target"]})
    decisions = _dedup_by_key(decisions)             # 1 decisión por dedup_key (target): la de mejor kind
    decisions.sort(key=lambda d: (_KIND_RANK.get(d["kind"],9), d["target"]))
    for i, d in enumerate(decisions, 1): d["rank"] = i
    counts = {k: sum(1 for it in items if it["lane"]==k and it["state"]=="done") for k in ("critic","auditor","package","reconciler")}
    counts["failed"] = sum(1 for it in items if it["state"]=="failed")
    digest = {"night":night,"generated_at":datetime.now(timezone.utc).isoformat(),"budget_tokens":budget,
        "spent_tokens":L.spent_tokens(night),"budget_exhausted":stopped_reason=="budget",
        "stopped_reason":stopped_reason,"counts":counts,"decisions":decisions}
    out = Path(runtime_paths.data_dir())/"night_foundry"/"digests"/f"digest-{night}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    return digest
```

**Entrega:** (a) el archivo `digests/digest-<fecha>.json` es la fuente durable (cualquier runtime lo lee); (b) una notificación con el resumen (top-3 decisiones + costo) — en Claude Code por su mecanismo de notificación nativo [INF: API exacta no verificada; el archivo es el fallback portable]; en Codex/Copilot no hay push: el operador abre el panel o el archivo a la mañana.

**Tests PRIMERO — `tests/test_plan202_digest.py`** (`subprocess` de `merge-tree` monkeypatcheado para simular clean/conflict):
- `test_digest_mergeabilidad_y_dedup` (KPI-7) — un item auditor de rama "limpia" (mock exit 0) ⇒ `mergeable True`; otro de rama con conflicto (mock exit 1 + stdout con paths) ⇒ `False` + `conflict_paths`; 2 items del mismo target ⇒ 1 sola decisión.
- `test_ranking_por_kind` — merge antes que implement antes que review antes que reconcile; `rank` 1..N consecutivo.
- `test_budget_exhausted_se_refleja` — `stopped_reason "budget"` ⇒ `budget_exhausted True`.
- `test_digest_solo_incluye_done` — items pending/failed no generan decisión (failed cuenta en `counts.failed`).
- `test_mergeability_rc_error_es_unknown` ([C7] `merge-tree` mock rc=128 ⇒ `verdict "unknown"`, `mergeable None`, NO `conflict`).
- `test_parse_conflict_paths`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_digest.py -q`.
**Criterio (binario):** los 5 tests pasan.
**Flag / runtime / operador:** flag maestra; mergeabilidad y digest son Python+git (los 3 runtimes); la notificación push es Claude-nativa con fallback archivo; operador: ninguno.

---

### E7 — Flag maestra + presupuesto + API read-only + skill orquestadora Claude-nativa + kill-switches + worktree

**Objetivo (1 frase):** cablear la feature: flag en los 5 lugares, presupuesto, ruta read-only para el panel, la skill `fragua-nocturna` que arma el `/loop`, y el worktree/rama namespaced. **Valor:** la Fragua queda disponible (default ON, costo ocioso 0) y armable por el operador.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py` (2 flags)
- EDITAR `Stacky Agents/backend/config.py` (2 defaults efectivos)
- EDITAR `Stacky Agents/backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`) y `test_harness_flags_requires.py` (edge) y el mapa de bounds (para la flag int)
- CREAR `Stacky Agents/backend/api/night_foundry.py` (blueprint read-only) + registrarlo en `backend/api/__init__.py`
- CREAR `.claude/skills/fragua-nocturna/SKILL.md` (orquestadora Claude-nativa)
- CREAR `Stacky Agents/backend/tests/test_plan202_api_flag.py`; EDITAR ambos runners.

**1) Flags (receta default-ON de 5 lugares, gotcha de memoria):**
```python
FlagSpec(key="STACKY_NIGHT_FOUNDRY_ENABLED", type="bool", label="La Fragua Nocturna",
    description="Habilita la maquinaria de la Fragua Nocturna (planner, ledger, digest, panel y "
                "botón manual 'correr un turno'). No corre nada solo: la corrida nocturna la arma "
                "el operador con /loop. Solo produce papel revisable; nunca mergea ni implementa.",
    group="global", default=True)   # [C9 v2] master bool default ON sin requires — patrón REAL
                                     # STACKY_DEVOPS_AGENT_ENABLED (VERIFICADO harness_flags.py:203).
                                     # (El STACKY_EVOLUTION_CENTER_ENABLED del 167 NO está en main.)

FlagSpec(key="STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET", type="int", label="Presupuesto de tokens por noche",
    description="Corte duro: la Fragua deja de tomar items nuevos cuando el gasto de la noche supera "
                "este techo.", group="global", default=40000,
    min_value=1000, max_value=500000,   # [C10 v2] OBLIGATORIO en la FlagSpec: test_bounds_map_is_frozen
                                         # deriva 'actual' de FlagSpec.min_value/max_value (bounds.py:181-186).
    requires="STACKY_NIGHT_FOUNDRY_ENABLED")
```
- Agregar ambas keys a `_CATEGORY_KEYS`. **[C10 v2 — CORRECCIÓN CLAVE]** `default_is_known(spec) == (spec.default is not None)` (VERIFICADO `harness_flags.py:3476`): como AMBAS FlagSpec declaran `default` explícito, `test_default_known_only_for_curated` exige que AMBAS keys estén en `_CURATED_DEFAULTS_ON` (la bool Y la int — NO "solo la bool"; el gotcha "solo bools" describe el set histórico, no la regla del test). Default efectivo en `config.py` para ambas. Edge `STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET → STACKY_NIGHT_FOUNDRY_ENABLED` en `_REQUIRES_MAP_FROZEN` (`test_harness_flags_requires.py:120`). Para la int: `min_value=1000, max_value=500000` EN la FlagSpec (arriba) **y** la MISMA entrada en `_FROZEN_BOUNDS` (`test_harness_flags_bounds.py:149`) — `test_bounds_map_is_frozen` deriva `actual` de `FlagSpec.min_value/max_value` (líneas 181-186), deben coincidir; agregá SOLO tu flag (la deuda ajena preexistente no se toca).

**2) API read-only `api/night_foundry.py`:**
```python
@bp.get("/digest/latest")
def latest_digest():
    if not getattr(_config.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False): abort(404)
    # lee el digest-<fecha>.json más reciente de data_dir()/night_foundry/digests/ (o {} si no hay)

@bp.get("/ledger")
def ledger_view():
    if not getattr(_config.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False): abort(404)
    # devuelve list_items(night=<hoy o param>) para el panel

@bp.post("/run-one-turn")
def run_one_turn():
    """Botón manual (on-demand, HITL explícito): corre UN item determinista y devuelve el resultado.
    NO arma autonomía. 404 con flag OFF."""
    if not getattr(_config.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False): abort(404)

@bp.post("/stop")   # [ADICIÓN ARQUITECTO v2] kill-switch de un clic desde el panel (HITL): crea el archivo STOP.
def stop_on():
    """Detiene la Fragua sin tocar env: crea data_dir()/night_foundry/STOP ⇒ la próxima iteración de
    run_night corta con stopped_reason 'stop_file'. Solo DETIENE; jamás arranca autonomía. 404 con flag OFF."""
    if not getattr(_config.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False): abort(404)
    # touch data_dir()/night_foundry/STOP  (mkdir parents + write_text(""))

@bp.delete("/stop")  # [ADICIÓN ARQUITECTO v2] rehabilitar: borra STOP. Detener/reanudar, nunca arrancar.
def stop_off():
    if not getattr(_config.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False): abort(404)
    # borra data_dir()/night_foundry/STOP si existe (no-op si no)
```
Registrar el blueprint en `backend/api/__init__.py` (zona de imports :61 y de registers :122 — anclar por contenido; blueprints van ahí, NO en `app.py`).

**3) Skill `fragua-nocturna` (Claude-nativa, orquestación):** `SKILL.md` que documenta el turno: (1) crear worktree aislado `git worktree add ../_wt/nightly-<fecha> -b nightly/<fecha> main` (o EnterWorktree); (2) `should_stop`; (3) `plan_night(<fecha>)`; (4) loop `run_night(..., dispatch_critic=<invoca el skill criticar-y-mejorar-plan para el plan del item>)`; (5) `build_digest`; (6) notificar. **Kill-switches redundantes cableados:** archivo `data_dir()/night_foundry/STOP` (creable/borrable de un clic vía `POST/DELETE /api/night_foundry/stop` — ADICIÓN v2), env PROPIO `STACKY_NIGHT_FOUNDRY_HARD_DISABLE` y env `STACKY_EVOLUTION_HARD_DISABLE` (mismo nombre que el 167, forward-compat; [C9 v2] hoy sin reader en main), `/loop` detenido / `TaskStop` / cerrar sesión, y (futuro F1) `CronDelete` del `/schedule`. El operador arma con `/loop` o `/schedule` a las 2am; en Codex/Copilot corre los CLIs Python y los skills a mano (fallback).

**Tests PRIMERO — `tests/test_plan202_api_flag.py`:**
- `test_flag_maestra_bool_default_on` + `test_flag_en_curated_defaults_on`.
- `test_flag_budget_int_default_y_bounds` + `test_budget_int_en_curated_defaults_on` ([C10 v2] la int TAMBIÉN curada) + `test_budget_bounds_en_frozen_map`.
- `test_edge_budget_requires_master`.
- `test_endpoints_404_con_flag_off` (los 5: digest/ledger/run-one-turn/POST stop/DELETE stop) y `test_digest_latest_ok_con_flag_on`.
- `test_stop_endpoint_crea_y_borra_stop` (ADICIÓN v2) — `POST /stop` crea el archivo STOP, `DELETE /stop` lo borra; solo detiene/reanuda (nunca arranca una corrida).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_api_flag.py -q` + `.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q` + `... test_harness_flags_requires.py -q` (POR ARCHIVO).
**Criterio (binario):** todos pasan; la flag aparece toggleable en el panel de flags del Arnés (default ON); `ratchet_meta` NO-EMPEORAR.
**Runtime + fallback:** flags/API/CLIs = los 3 runtimes; la skill orquestadora + `/loop` = Claude-primario, fallback manual Codex/Copilot. **Trabajo del operador:** ninguno para tener la maquinaria; opt-in armar el `/loop` (default ON de la maquinaria, autonomía opt-in por construcción).

---

## 7. Riesgos y mitigaciones (ejes que la crítica va a atacar — PREVENIDOS)

| # | Riesgo | Mitigación (cableada donde se pueda) |
|---|--------|---------------------------------------|
| R1 | **Falsos verdes en tests generados de noche.** | F0 **NO commitea tests al árbol de tests**. El constructor-de-paquetes (E4) los propone como TEXTO dentro del paquete `.json` (`tests_to_write`), no como archivos ejecutables. [C3 v2] El auditor (E4) es GIT-ONLY read-only (diffstat/test-files/fase→archivo, KPI-5): NO ejecuta ningún test. Correr los tests de la rama/paquete (con checkout en worktree propio) y los "tests-rojos-como-spec" quedan para F3 (refutador) con gate. |
| R2 | **Costo de tokens nocturno.** | Presupuesto techo duro `STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET` con corte antes de tomar item nuevo (KPI-3); 3 de 4 carriles son deterministas (cost_tokens 0); costo ocioso 0 (KPI-9); autonomía opt-in (nada corre sin `/loop` armado). |
| R3 | **Complejidad del ledger.** | JSONL simple append-only con reescritura atómica (tmp+replace), ALLOWLIST y retención — [C8 v2] **EXTIENDE** el patrón de `deploy_store.py` (lock + `data_dir()` + jsonl + tolerar JSON corrupto, verificado) agregando tmp+replace/retención/ALLOWLIST (que deploy_store NO trae). Nada de DB nueva. |
| R4 | **Anti-deuda-de-papel (fabricar papel que nadie consume).** | Cableado como gate verificable (E3, KPI-6): proposer bloqueado por v1-sin-criticar / >8 v2-sin-implementar / ratio 1:3. En F0 el proposer está reservado ⇒ ratio 0:N (máximo des-atasque). |
| R5 | **Paridad honesta (vender lo que no es).** | Runtime primario declarado (Claude Code) para la orquestación y el carril crítico; núcleo determinista (6 de 7 componentes) runtime-agnóstico; fallback manual explícito para Codex/Copilot; ledger/digest son archivos que cualquier runtime lee/escribe (§3.4, líneas de runtime por etapa). |
| R6 | **Colisión estructural entre workers.** | Serialización dura (un item por iteración, KPI-2) + dominios de salida disjuntos por carril (E4) + worktree aislado `nightly/<fecha>`. El paralelismo real es F2 (204), no F0. |
| R7 | **La noche se cae a mitad.** | Resumibilidad por `input_hash` (KPI-4): claimed huérfanos se re-claman, done no se re-ejecutan, failed re-encolan hasta MAX_ATTEMPTS. |
| R8 | **La Fragua toca `main` o pushea.** | Prohibido por diseño (§3.1): todo aterriza en `nightly/<fecha>` o en `data_dir()`; el digest es inerte; el operador dispone. Ningún paso hace `git push` ni `git checkout main` ni merge. |
| R9 | **Sesión paralela / working tree sucio de día.** | El worktree namespaced aísla la ejecución nocturna del árbol diurno; el ledger vive en `data_dir()` (fuera del árbol). |
| R10 | **RSI aún no mergeada (F4 depende de `impl/rsi`).** | F4 (206) es futuro y su §4 declara la dependencia dura de que RSI 167-170 esté en `main`; el TMV no la toca. |

---

## 8. Fuera de scope (lo que NO es este plan)

- **F1 (203) robustez:** circuit breakers por carril, presupuestos en capas, reintentos con backoff, kill-switches ampliados. (El TMV trae MAX_ATTEMPTS y corte global; nada más.)
- **F2 (204) multi-carril paralelo** en worktrees vía Workflow. (El TMV es SERIAL a propósito.)
- **F3 (205) verificación adversarial:** el "refutador" que corre antes del digest; **corre los tests que la rama/paquete promete** (checkout de la rama en un worktree propio — lo que el auditor F0 NO hace, C3 v2) y los tests-rojos-como-spec con gate.
- **F4 (206) evolutivo:** conexión con RSI 167-170 (GEPA muta prompts de los workers, fitness 168 puntúa, Pareto 169 retiene, flywheel 170 cosecha; adopción HITL en el Centro de Evolución 167). Depende de que `impl/rsi` esté mergeada.
- **F5 (207) hoja de ruta** de la serie 202-206.
- El **carril proposer** (generar planes nuevos de noche): reservado, gateado (E3), NO corre en F0.
- **Auto-merge / auto-push / auto-implementación:** jamás (viola §3.1). La consolidación de ramas la hace el operador con el skill `consolidar-ramas-a-main`.
- **UI rica del panel:** el TMV expone la ruta read-only; el panel visual completo (timeline, filtros) es mejora posterior.

---

## 9. Glosario + Orden de implementación + DoD global

**Glosario (para modelos menores):**
- **TMV (Turno Mínimo Viable):** este plan (F0 de la serie); el sustrato mínimo completo de la Fragua.
- **Work item:** una unidad de trabajo derivada (§5.1): carril + target + estado + hash de entrada.
- **Carril (lane):** critic / auditor / package / reconciler (+ proposer reservado). Cada uno con dominio de salida disjunto.
- **AUDIT-ONLY:** [C3 v2] el auditor es GIT-ONLY (diffstat + test-files + mapa fase→archivo vía `git … base...branch`); **NO ejecuta tests, NO hace checkout, JAMÁS implementa ni "termina lo que falte"** (límite duro que lo separa del skill `supervisar-implementaciones-planes`, que sí implementa; correr los tests es de F3). Verificado por post-condición `git status --porcelain` idéntico antes/después (KPI-5).
- **Paquete listo-para-el-día:** `.json` con mapa de archivos+anclas, tests a escribir con qué asertan, checklist de fases, gotchas de memoria aplicables, gates/ratchets. Producido por el constructor (E4), determinista.
- **Digest triado:** cola de decisiones rankeada y deduplicada (§5.2), NO un volcado de logs.
- **Mergeabilidad:** veredicto read-only vía `git merge-tree --write-tree` (clean/conflict/unknown).
- **Fingerprint de dedup/resumibilidad:** `input_hash` (§5.3) — dedup + retomar la noche caída.
- **Kill-switches redundantes:** archivo `STOP` (un clic: `POST/DELETE /api/night_foundry/stop`), env PROPIO `STACKY_NIGHT_FOUNDRY_HARD_DISABLE` + `STACKY_EVOLUTION_HARD_DISABLE` (forward-compat 167), `/loop` detenido / `TaskStop` / cerrar sesión, `CronDelete` (F1).
- **Runtime primario:** Claude Code (orquestación + carril crítico LLM); fallback manual Codex/Copilot sobre los mismos archivos y skills.

**Orden de implementación:** E1 (ledger) → E2 (planner) → E3 (gate) → E4 (workers) → E5 (orquestador) → E6 (digest) → E7 (flag+API+skill+kill-switches). Cada etapa se commitea sola con sus tests verdes ANTES de la siguiente.

**DoD global:**
- [ ] Los 6 archivos de test (`test_plan202_ledger.py`, `_planner.py`, `_workers.py`, `_orchestrator.py`, `_digest.py`, `_api_flag.py`) pasan POR ARCHIVO con `.venv\Scripts\python.exe` (py3.13.5) desde `Stacky Agents\backend`.
- [ ] KPI-1..KPI-9 verificados por los tests nombrados.
- [ ] `python -m compileall backend` limpio; `test_harness_flags.py`, `test_harness_flags_requires.py`, `test_bounds_map_is_frozen`, `test_default_known_only_for_curated` verdes; `ratchet_meta` NO-EMPEORAR.
- [ ] Los 6 tests nuevos registrados en `run_harness_tests.sh` **y** `run_harness_tests.ps1` (gotcha meta-test).
- [ ] Ambas flags visibles/toggleables en el panel del Arnés; maestra default ON; con maestra OFF: las 3 rutas dan 404 y nada corre (cero diferencias vs. hoy).
- [ ] Datos SOLO en `data_dir()/night_foundry/` (`.jsonl`/`.json`, nunca `.md`); cero escritura fuera de los namespaces disjuntos por carril.
- [ ] Skill `.claude/skills/fragua-nocturna/SKILL.md` creada, con el turno documentado y los kill-switches; ninguna autonomía sin `/loop` armado por el operador.
- [ ] Ningún hook de arranque (`app.py`) invoca al orquestador (KPI-9: costo ocioso 0).
- [ ] [v2] `_docs_dir()` resuelve a `Stacky Agents/docs` (test de anclaje C1); guard anti-bucle del orquestador (`seen`+`exclude_ids`) verificado (C6); los 9 helpers de §E0 con test (C4); auditor GIT-ONLY sin pytest (C3); detección de versión sobre la STATUS LINE (C2); ambas flags en `_CURATED_DEFAULTS_ON` y bounds en la FlagSpec + `_FROZEN_BOUNDS` (C10).
- [ ] Contratos §5 (ledger, digest, fingerprint) congelados y citables por 203-207.
- [ ] Encabezado de estado del doc actualizado al implementar (PROPUESTO v1 → IMPLEMENTADO / según pipeline).
