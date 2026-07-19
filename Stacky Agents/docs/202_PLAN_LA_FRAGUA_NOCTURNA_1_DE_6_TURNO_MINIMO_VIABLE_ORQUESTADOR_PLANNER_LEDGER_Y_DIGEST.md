# Plan 202 — La Fragua Nocturna (1/6): Turno Mínimo Viable (TMV) — Orquestador, Planner de cola derivada, Ledger durable y Digest triado

- **Estado:** PROPUESTO v1 — 2026-07-18 · Autor: StackyArchitectaUltraEficientCode
- **Serie:** "La Fragua Nocturna" (6 piezas: F0..F4 de serie + 1 hoja de ruta). ESTE documento es la **Fase 0 de la serie = Turno Mínimo Viable (TMV)**. Sus fases internas de implementación se numeran **Etapa 1..7 (E1..E7)** para no colisionar con las fases de serie F0..F4.
- **Nota de numeración:** la serie ocupa 202-207 (no 199-201): al redactar, 199 (cosecha telemetría), 200 (consola por incidencia) y 201 (taller de compilación) YA estaban tomados por planes ajenos. Verificado en frío listando `Stacky Agents/docs/` el 2026-07-18: el próximo `NN_` libre es 202.
- **Precedentes de formato en la casa:** plan 184 (hoja de ruta DB Compare), plan 195 (hoja de ruta DevOps), plan 197 (hoja de ruta UX), plan 198 (ledger de applies) — mismo rigor de contratos congelados y gates binarios.

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
| KPI-5 | AUDIT-ONLY duro: el worker auditor deja el árbol SIN cambios (`git status --porcelain` vacío tras auditar); si algo se modificó, el item se marca `failed` y el digest lo denuncia | `test_auditor_readonly_arbol_intacto` |
| KPI-6 | Anti-deuda-de-papel cableada: con backlog actual (>8 v2 sin implementar), el planner encola CERO items del carril proponedor | `test_gate_proposer_bloqueado_por_backlog` |
| KPI-7 | Digest triado: mergeabilidad correcta (rama limpia → `mergeable: true`; rama con conflicto sembrado → `false` + `conflict_paths`); decisiones deduplicadas por `target` y rankeadas | `test_digest_mergeabilidad_y_dedup` |
| KPI-8 | Kill-switches: con el archivo `STOP` presente O `STACKY_EVOLUTION_HARD_DISABLE=1`, la corrida no procesa NADA y sale limpio | `test_killswitches_detienen_todo` |
| KPI-9 | Cero costo ocioso: con la flag ON pero sin `/loop` armado, ninguna ruta ni daemon consume tokens (todo es on-demand / lectura local) | Revisión de que ningún hook de arranque llama al orquestador (grep en `app.py`) |

**Ganancia robusta.** El operador llega a la mañana con: N paquetes listos-para-el-día (mapa de archivos con anclas + tests a escribir + checklist + gotchas aplicables + gates), M ramas `impl/*` auditadas con su veredicto de mergeabilidad, y las críticas v2 que faltaban — todo inerte, todo revisable, cero autonomía sobre el merge.

**Onboarding casi nulo.** La Fragua no cambia ningún flujo diurno. El operador ve el digest en un panel read-only y decide. Nada corre hasta que el operador arma el `/loop` (opt-in por construcción).

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo el 2026-07-18):

1. **El pipeline de planes existe pero es 100% operador-driven.** Los 4 skills viven en `.claude/skills/` (`proponer-plan-stacky`, `criticar-y-mejorar-plan`, `implementar-plan-stacky`, `supervisar-implementaciones-planes` — verificado por `ls`). Cada uno se dispara a mano. No hay ningún mecanismo que trabaje el backlog cuando el operador no está.
2. **El backlog es masivo y crece.** `Stacky Agents/docs/` tiene planes hasta el 201; la memoria del proyecto lista decenas de "CRITICADO v2 … falta implementar" y "PROPUESTO v1 … falta criticar". Las hojas de ruta 184/195/197 existen justamente porque la serie de planes hermanos se acumuló más rápido de lo que se implementa.
3. **Hay ramas `impl/*` sin consolidar.** `git branch` (2026-07-18) muestra `impl/dbcompare`, `impl/devops`, `impl/plan-159`, `impl/plan-163`, `impl/rsi`, `impl/ux` — trabajo real sin auditar ni mergear. El gotcha "worktree branch vs plan hermano" (memoria) ya mordió: docs marcados IMPLEMENTADO cuyo código vive en una rama sin mergear.
4. **La infraestructura para hacerlo bien YA está madura:** ledgers JSONL con lock y retención son patrón de la casa (`services/deploy_store.py`: `from runtime_paths import data_dir`, `_LOCK = threading.Lock()`, `data_dir()/deploy_ledger.jsonl`, `append_ledger(entry)` — verificado `deploy_store.py:19,24,33,120`); el ledger de dev-tooling bajo el repo tiene precedente (`docs/_supervision/ledger.json`, keyed por hash del doc para no re-auditar salvo cambio — patrón que este plan REUSA para dedup/resumibilidad); `git merge-tree --write-tree` está disponible (git 2.50.1, probado read-only, devuelve tree hash sin tocar el árbol ni refs); `/loop` y `/schedule` son skills nativas de Claude Code (listadas en el harness).
5. **La serie RSI (167-170) prepara el norte pero no está mergeada.** `evolution_store.py` NO existe en el working tree (verificado: ausente); la RSI vive en la rama `impl/rsi` [INF: rama confirmada por `git branch`, código no verificado en este working tree]. F4 de esta serie conecta con RSI 167-170 — por eso F4 es futuro y depende de que RSI se merge (§8).

**Gap que cierra:** el pipeline de planes pasa de "el operador trabaja el backlog a mano, de día" a "la noche PROPONE y PREPARA papel revisable; el operador DISPONE a la mañana". Sin quitarle una sola decisión al operador.

---

## 3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop innegociable.** La noche produce PAPEL inerte (críticas, auditorías, paquetes) en archivos locales y en una rama namespaced `nightly/<fecha>`. **NUNCA** mergea a `main`, **NUNCA** hace push, **NUNCA** modifica el árbol de tests, **NUNCA** implementa código de producto. El operador revisa el digest a la mañana y decide qué mergear/implementar. Esta es la razón por la que correr de noche **NO bypasea revisión humana** (excepción dura #1 NO aplicada): la salida es inerte y se revisa ANTES de cualquier efecto.
2. **Cero trabajo extra para el operador.** Flag maestra `STACKY_NIGHT_FOUNDRY_ENABLED` default **ON** = la maquinaria está disponible (planner inspeccionable, ledger/digest legibles, botón manual "correr un turno"). **Costo ocioso = 0** (KPI-9): con la flag ON pero sin `/loop` armado, nada corre y nada consume tokens — es lectura local + on-demand. Alinea con el gotcha de la casa "ningún bool default-ON quema tokens pagos ocioso; solo SPECULATIVE (OFF) pre-ejecuta".
3. **La autonomía nocturna es opt-in POR CONSTRUCCIÓN.** No existe flag que haga correr la noche sola: el operador arma el `/loop`/`/schedule`. Si una fase FUTURA agrega un toggle in-app "armar autorun nocturno", ESE toggle nace default **OFF** citando **EXCEPCIÓN DURA #3 (prerequisito no garantizado en instalación default)** — `/loop` es nativo de Claude Code, no de Codex/Copilot — más el criterio de no-quema-ociosa. En el TMV NO hay ese toggle: se arma a mano.
4. **3 runtimes — paridad honesta con matiz declarado.** El **núcleo determinista** (ledger, planner, gate anti-deuda, auditor, constructor-de-paquetes, reconciliador, digest, mergeabilidad) es **Python puro, idéntico en los 3 runtimes, cero LLM**. La **orquestación nocturna** (`/loop`, worktrees, dispatch de skills, notificación) y **el carril crítico** (invoca el skill LLM `criticar-y-mejorar-plan`) son **Claude-Code-nativos**: Claude Code es el **runtime primario** de la Fragua. **Fallback explícito Codex/Copilot:** el operador dispara los mismos skills a mano y corre los CLIs Python deterministas; el ledger y el digest son archivos que cualquier runtime lee/escribe. NO se vende paridad falsa: solo el papel de salida y el núcleo determinista son runtime-agnósticos; el bucle y la crítica LLM son primario-Claude con degradación manual documentada (§6 por etapa).
5. **Mono-operador sin auth.** Ningún RBAC/rol. El header `current_user` no se valida ni se usa para gating.
6. **No degradar.** Backward-compatible: la Fragua agrega servicios y una ruta read-only; no toca ningún camino existente. Todo hook es best-effort (try/except + `stacky_logger`). El presupuesto de tokens es corte DURO (no hay "correr un poco más"). Reusa: patrón ledger de `deploy_store`, contrato de inyección 133, kill-switch 167, flags del arnés, memoria colaborativa.
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

def claim_next() -> dict | None:
    """Atómico: toma el primer pending (o claimed huérfano) por orden de carril (critic<auditor<
    package<reconciler) y luego FIFO; lo pasa a claimed, incrementa attempts, persiste, lo devuelve."""
    order = {"critic":0,"auditor":1,"package":2,"reconciler":3,"proposer":4}
    with _LOCK:
        rows = _read_all()
        cands = [r for r in rows if r.get("state") in ("pending","claimed")]
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
    return Path(runtime_paths.app_root()) / "docs"    # ajustar al helper real que apunta a Stacky Agents/docs

def _plan_docs() -> list[Path]:
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
        if re.search(r"PROPUESTO v1", status) and not re.search(r"v2|CRITICADO", text):
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

(`_derive_package_candidates` y `_derive_drift_candidates` = helpers deterministas descriptos arriba; cada uno con su test.)

**Tests PRIMERO — `tests/test_plan202_planner.py`** (fixture: un `tmp_path/docs/` con 2-3 planes sembrados de estados distintos + monkeypatch de `_docs_dir` y de `_git`):
- `test_deriva_critic_de_v1_sin_criticar` — doc `PROPUESTO v1` sin v2 ⇒ candidato critic; doc con `v2` ⇒ NO.
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
        if re.search(r"PROPUESTO v1", status) and not re.search(r"v2|CRITICADO", text):
            v1_uncriticized += 1
        if re.search(r"CRITICADO v2|APROBADO-CON-CAMBIOS", text) and not re.search(r"IMPLEMENTADO|IMPL\b", status):
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

def run_auditor(branch: str) -> dict:
    """AUDIT-ONLY DURO. Mapea fases a código (grep del doc que la rama implementa) y corre SOLO los
    tests que el plan nombra, POR ARCHIVO, con el venv. JAMÁS implementa ni 'termina lo que falte'.
    POST-CONDICIÓN verificable (KPI-5): 'git status --porcelain' debe quedar VACÍO; si no, el item
    es 'failed' y el reporte lo denuncia (violación de read-only). Devuelve dict de reporte + costo 0."""
    before = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True).stdout
    # 1) resolver el plan que la rama implementa (heurística: nombre de rama ↔ doc; o leer commits)
    # 2) extraer de su doc los nombres de archivos de test (regex 'tests\\\\?[\\w/]*test_\\w+\\.py')
    # 3) por cada test: subprocess .venv\Scripts\python.exe -m pytest <archivo> -q  (timeout, capturar)
    # 4) mapear cada fase F0..Fn a archivo:símbolo por grep (sin modificar nada)
    report = {"branch": branch, "tests": [], "phase_map": [], "readonly_ok": True}
    after = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True).stdout
    report["readonly_ok"] = (before == after)          # KPI-5: el árbol quedó intacto
    out = _nf_dir("audits") / f"{branch.replace('/','-')}-{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_ref": f"audits/{out.name}", "cost_tokens": 0, "readonly_ok": report["readonly_ok"]}

def build_package(plan_nn: str, doc_path: Path) -> dict:
    """Constructor del 'paquete listo-para-el-día' (determinista, extrae de la estructura del doc):
    - mapa de archivos a tocar con líneas ancla (parse de las secciones 'Archivos:' del plan)
    - lista de tests a escribir con qué asertan (parse de 'Tests PRIMERO')
    - checklist de fases F0..Fn (o E1..En)
    - gotchas de memoria aplicables (match por keywords del doc contra el índice de memoria)
    - gates/ratchets a pasar (parse de 'Criterio' / 'gate' / 'ratchet' del doc)
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

def should_stop(night: str, budget: int) -> tuple[bool, str]:
    if os.getenv("STACKY_EVOLUTION_HARD_DISABLE","").strip().lower() in ("1","true","yes","on"):
        return True, "hard_disable"                      # reusa el kill-switch env del plan 167
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

def run_night(night: str | None = None, *, budget: int, dispatch_critic=None) -> dict:
    """Loop serializado. UN item por iteración. Antes de CADA item chequea should_stop.
    Idempotente/resumible: claim_next re-clama huérfanos; los done nunca se re-ejecutan.
    'dispatch_critic' (callable) lo inyecta el skill Claude-nativo para el carril LLM; si es None,
    los items critic se dejan pending (fallback Codex/Copilot: el operador los corre a mano)."""
    night = night or f"{datetime.now(timezone.utc):%Y-%m-%d}"
    stopped = "queue_empty"
    while True:
        stop, why = should_stop(night, budget)
        if stop: stopped = why; break
        item = L.claim_next()
        if item is None: stopped = "queue_empty"; break
        try:
            if item["lane"] == "critic":
                if dispatch_critic is None:
                    # sin runtime Claude: no procesar, dejar pending y seguir con deterministas
                    L.record_result(item["id"], "pending"); continue
                res = dispatch_critic(item)              # invoca el skill criticar-y-mejorar-plan
            else:
                res = run_deterministic_item(item)
            L.record_result(item["id"], "done", output_ref=res.get("output_ref"), cost_tokens=res.get("cost_tokens",0))
        except Exception as e:
            L.record_result(item["id"], "failed", error=str(e)[:300])
    return {"night": night, "stopped_reason": stopped, "spent_tokens": L.spent_tokens(night)}
```

Nota sobre el fallback critic sin Claude: para NO caer en loop infinito reclamando el mismo pending, cuando `dispatch_critic is None` el loop debe SALTEAR los critic pending (llevar un set de ids ya vistos esta corrida) y cortar cuando solo quedan critic. Implementar ese guard explícito (test lo cubre).

**Tests PRIMERO — `tests/test_plan202_orchestrator.py`** (ledger en `tmp_path`; workers monkeypatcheados para devolver `cost_tokens` fijos):
- `test_orquestador_serializa_uno_por_iteracion` (KPI-2) — 5 items; `should_stop` fuerza corte tras 2 ⇒ 2 done + 3 pending.
- `test_corte_duro_por_presupuesto` (KPI-3) — budget 1000; 3 items de 500 c/u ⇒ 2 done (1000), el 3º pending, `stopped_reason "budget"`.
- `test_resume_por_hash_no_reejecuta_done` (KPI-4) — dejar 1 claimed + 1 done; re-`run_night` ⇒ el done no se toca, el claimed se termina.
- `test_killswitches_detienen_todo` (KPI-8) — con `STOP` presente ⇒ 0 items procesados, `stopped_reason "stop_file"`; con env `STACKY_EVOLUTION_HARD_DISABLE=1` ⇒ `"hard_disable"`.
- `test_critic_sin_dispatch_no_bucle` — items critic con `dispatch_critic=None` ⇒ quedan pending, el loop termina (guard anti-bucle).
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

**Mergeabilidad (read-only, verificada [V] con git 2.50.1):** `git merge-tree --write-tree <base> <branch>` — exit 0 + tree hash ⇒ `mergeable: true, verdict: "clean"`; exit != 0 ⇒ conflicto: parsear las secciones de conflicto para `conflict_paths`; si el comando falla por otra razón ⇒ `verdict: "unknown", mergeable: None`. NO toca working tree ni refs.

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
    paths = _parse_conflict_paths(p.stdout)          # de las líneas "CONFLICT" / "changed in both"
    return {"verdict": "conflict", "mergeable": False, "conflict_paths": paths}

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
    group="global", default=True)   # master, sin requires (patrón STACKY_EVOLUTION_CENTER_ENABLED)

FlagSpec(key="STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET", type="int", label="Presupuesto de tokens por noche",
    description="Corte duro: la Fragua deja de tomar items nuevos cuando el gasto de la noche supera "
                "este techo.", group="global", default=40000,
    requires="STACKY_NIGHT_FOUNDRY_ENABLED")
```
- Agregar ambas keys a `_CATEGORY_KEYS`; `STACKY_NIGHT_FOUNDRY_ENABLED` a `_CURATED_DEFAULTS_ON` (SOLO la bool — la int NO va ahí; gotcha `test_default_known_only_for_curated`); default efectivo en `config.py`; edge `STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET → STACKY_NIGHT_FOUNDRY_ENABLED` en `_REQUIRES_MAP_FROZEN`. Para la flag int: entrada en el mapa de bounds (`[1000, 500000]`) — gotcha `test_bounds_map_is_frozen` (agregá SOLO tu flag; la deuda ajena preexistente no se toca).

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
```
Registrar el blueprint en `backend/api/__init__.py` (zona de imports :61 y de registers :122 — anclar por contenido; blueprints van ahí, NO en `app.py`).

**3) Skill `fragua-nocturna` (Claude-nativa, orquestación):** `SKILL.md` que documenta el turno: (1) crear worktree aislado `git worktree add ../_wt/nightly-<fecha> -b nightly/<fecha> main` (o EnterWorktree); (2) `should_stop`; (3) `plan_night(<fecha>)`; (4) loop `run_night(..., dispatch_critic=<invoca el skill criticar-y-mejorar-plan para el plan del item>)`; (5) `build_digest`; (6) notificar. **Kill-switches redundantes cableados:** archivo `data_dir()/night_foundry/STOP`, env `STACKY_EVOLUTION_HARD_DISABLE` (reusado del 167), `/loop` detenido / `TaskStop` / cerrar sesión, y (futuro F1) `CronDelete` del `/schedule`. El operador arma con `/loop` o `/schedule` a las 2am; en Codex/Copilot corre los CLIs Python y los skills a mano (fallback).

**Tests PRIMERO — `tests/test_plan202_api_flag.py`:**
- `test_flag_maestra_bool_default_on` + `test_flag_en_curated_defaults_on`.
- `test_flag_budget_int_default_y_bounds`.
- `test_edge_budget_requires_master`.
- `test_endpoints_404_con_flag_off` (los 3) y `test_digest_latest_ok_con_flag_on`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan202_api_flag.py -q` + `.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q` + `... test_harness_flags_requires.py -q` (POR ARCHIVO).
**Criterio (binario):** todos pasan; la flag aparece toggleable en el panel de flags del Arnés (default ON); `ratchet_meta` NO-EMPEORAR.
**Runtime + fallback:** flags/API/CLIs = los 3 runtimes; la skill orquestadora + `/loop` = Claude-primario, fallback manual Codex/Copilot. **Trabajo del operador:** ninguno para tener la maquinaria; opt-in armar el `/loop` (default ON de la maquinaria, autonomía opt-in por construcción).

---

## 7. Riesgos y mitigaciones (ejes que la crítica va a atacar — PREVENIDOS)

| # | Riesgo | Mitigación (cableada donde se pueda) |
|---|--------|---------------------------------------|
| R1 | **Falsos verdes en tests generados de noche.** | F0 **NO commitea tests al árbol de tests**. El constructor-de-paquetes (E4) los propone como TEXTO dentro del paquete `.json` (`tests_to_write`), no como archivos ejecutables. El auditor (E4) corre SOLO tests YA existentes que el plan nombra, read-only (KPI-5). Los "tests-rojos-como-spec" quedan para F3 (refutador) con gate. |
| R2 | **Costo de tokens nocturno.** | Presupuesto techo duro `STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET` con corte antes de tomar item nuevo (KPI-3); 3 de 4 carriles son deterministas (cost_tokens 0); costo ocioso 0 (KPI-9); autonomía opt-in (nada corre sin `/loop` armado). |
| R3 | **Complejidad del ledger.** | JSONL simple append-only con reescritura atómica (tmp+replace), ALLOWLIST y retención — calca `deploy_store.py` verificado. Nada de DB nueva. |
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
- **F3 (205) verificación adversarial:** el "refutador" que corre antes del digest; los tests-rojos-como-spec con gate.
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
- **AUDIT-ONLY:** el auditor mapea fases a código y corre tests existentes; **JAMÁS implementa ni "termina lo que falte"** (límite duro que lo separa del skill `supervisar-implementaciones-planes`, que sí implementa). Verificado por post-condición `git status --porcelain` vacío (KPI-5).
- **Paquete listo-para-el-día:** `.json` con mapa de archivos+anclas, tests a escribir con qué asertan, checklist de fases, gotchas de memoria aplicables, gates/ratchets. Producido por el constructor (E4), determinista.
- **Digest triado:** cola de decisiones rankeada y deduplicada (§5.2), NO un volcado de logs.
- **Mergeabilidad:** veredicto read-only vía `git merge-tree --write-tree` (clean/conflict/unknown).
- **Fingerprint de dedup/resumibilidad:** `input_hash` (§5.3) — dedup + retomar la noche caída.
- **Kill-switches redundantes:** archivo `STOP`, env `STACKY_EVOLUTION_HARD_DISABLE` (167), `/loop` detenido / `TaskStop` / cerrar sesión, `CronDelete` (F1).
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
- [ ] Contratos §5 (ledger, digest, fingerprint) congelados y citables por 203-207.
- [ ] Encabezado de estado del doc actualizado al implementar (PROPUESTO v1 → IMPLEMENTADO / según pipeline).
