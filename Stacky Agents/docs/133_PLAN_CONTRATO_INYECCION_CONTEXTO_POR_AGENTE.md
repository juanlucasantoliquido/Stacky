# Plan 133 — Contrato de inyección de contexto por agente: preflight de prerequisitos, refresh just-in-time, directiva de modo server-side y garantía de bloques requeridos

**Estado:** PROPUESTO v1 (2026-07-13)
**Origen:** incidente real ADO-331 (FunctionalAnalyst lanzado sobre una Task en "Doing" → run quemado por aborto de contrato del agente). Tema fijado por el operador.
**Dependencias:** ninguna dura. Reusa: `services/run_preflight.py` (G0.1), `services/context_enrichment.py` (F2.4/I0.1/I2.1), `services/ado_sync.py` (`upsert_single_work_item`), `services/ado_read_cache.py` (I3.2), `services/ado_context.py`, registro de flags (`services/harness_flags.py` + `services/harness_flags_help.py` + `HarnessFlagsPanel`).
**Ortogonal a:** Planes 129/130/131/132 (no comparte archivos nuevos; comparte archivos editados `api/agents.py`, `config.py`, `harness_flags.py` → staging quirúrgico obligatorio, ver §3.8).

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Rutas, símbolos, flags y comandos son
> LITERALES. Prohibido desviarse de los nombres exactos, prohibido "mejorar" el alcance.
> Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPI

Hoy Stacky puede lanzar un agente sobre un ticket que NO cumple los prerequisitos que el
propio prompt del agente declara, y el agente (correctamente) aborta — pero DESPUÉS de
gastar el run CLI completo (tokens + minutos). Además, la decisión de qué contexto
inyectar se toma sobre un snapshot local del ticket que puede estar stale, la detección
del modo de trabajo (A/B) vive solo en el prompt del agente, y bloques que el prompt
declara "lectura OBLIGATORIA" son podables por el presupuesto de contexto.

Este plan convierte el contrato implícito agente↔contexto en un **contrato explícito y
verificado server-side**, en 4 garantías:

1. **Preflight de negocio** (F2): el `POST /api/agents/run` rechaza con **400 accionable**
   ANTES de gastar el run cuando el ticket no cumple los prerequisitos del agente.
2. **Refresh just-in-time** (F1): el ticket se re-sincroniza desde el tracker al momento
   del run — nunca más una decisión de inyección sobre `work_item_type`/`ado_state` stale.
3. **Directiva de modo server-side** (F3+F4): el backend detecta el bloqueante y calcula
   el modo (A/B) e inyecta un bloque `run-directive` de máxima prioridad; el paso de
   validación del agente pasa a ser un cross-check, no la única línea de defensa.
4. **Bloques requeridos garantizados** (F5+F6): el `.agent.md` declara qué bloques de
   contexto necesita (`stacky_required_blocks`), los 3 runtimes lo validan post-enrichment
   y pre-spawn, y los bloques críticos dejan de ser podables por el budget.

**KPI / impacto esperado (binarios):**

- **KPI-1 (0 runs quemados por prerequisitos):** relanzar el caso ADO-331 (functional
  sobre Task "Doing" sin comentario bloqueante) devuelve **400** con detalle accionable
  en <2 segundos, en vez de un run CLI abortado (~minutos y tokens). Test F2 caso 3.
- **KPI-2 (0 decisiones sobre snapshot stale):** con el tracker accesible, el
  `work_item_type` y `ado_state` usados por preflight e inyección son los del tracker al
  momento del run (test F1 caso 2: el estado local viejo se pisa antes de decidir).
- **KPI-3 (contrato garantizado):** un run de `functional` nunca llega al CLI sin
  `ado-epic-structured` o `ado-blocker` + `run-directive` en el contexto (o falla
  pre-spawn con error accionable, sin consumir tokens). Tests F5.
- **KPI-4 (menos tokens):** `STACKY_CONTEXT_DEDUP_ENABLED` pasa a default ON (F7): toda
  línea duplicada entre bloques se poda en TODOS los runs (ahorro puro; el dedup I0.1 ya
  existe y está testeado, solo estaba apagado).
- **KPI-5 (kill-switch limpio):** cualquiera de las 5 flags nuevas en OFF → el flujo
  correspondiente queda byte-idéntico al actual (tests de identidad por fase).

## 2. Por qué ahora / gap que cierra (evidencia verificada en HEAD)

**Incidente ADO-331 (2026-07-13):** el operador lanzó FunctionalAnalyst sobre la Task
ADO-331 (estado "Doing", con un comentario de Developer). El agente abortó por su propio
contrato: sin bloque `ado-epic-structured` (Modo A) ni `🚫 BLOQUEANTE TÉCNICO` en
`ado-comments` (Modo B), y estado fuera de `tracker_state_machine.functional.input_states`.
Run quemado, cero output útil. Causas raíz confirmadas en código:

1. `POST /api/agents/run` (`backend/api/agents.py:339`) toma `agent_type` del payload y
   lanza SIN validar `work_item_type` ni estado del ticket. El único preflight
   (`services/run_preflight.py:57 check()`, invocado en `agent_runner.py:106-134`) es
   solo de infraestructura (outputs_dir/repo/PAT/binario), está detrás de
   `STACKY_RUN_PREFLIGHT_GATE_ENABLED` default OFF y es fail-open.
2. `_inject_epic_structured` (`services/context_enrichment.py:989-1021`) solo inyecta
   `ado-epic-structured` si el Ticket LOCAL tiene `work_item_type=="Epic"` y
   `agent_type=="functional"`.
3. `Ticket.work_item_type`/`ado_state` solo se refrescan en el sync de arranque y en
   `POST /api/tickets/sync` (`services/ado_sync.py:102 sync_tickets`; `:235
   upsert_single_work_item`). NADIE re-sincroniza el ticket al momento del run → la
   decisión de inyección corre sobre snapshot stale.
4. `ado_context.enrich` (`services/ado_context.py:305`) vuelca hasta 30 comentarios
   crudos en `ado-comments`; la detección de `🚫 BLOQUEANTE TÉCNICO` vive SOLO en el
   prompt del agente (`backend/Stacky/agents/FunctionalAnalyst.agent.md:50,118-119,294`).
   El backend no marca nada.
5. `_BLOCK_PRIORITY` (`services/context_enrichment.py:360-375`) NO incluye
   `process-catalog`, `process-discipline` ni `acceptance-contract` → caen al default 50
   (`_DEFAULT_PRIORITY`, `:376`) y son PODABLES por el budget F2.4
   (`_HIGH_PRIORITY_THRESHOLD = 75`, `:243`), pese a que el prompt del agente declara el
   process_catalog "lectura OBLIGATORIA" y el bloque acceptance-contract se autodeclara
   `priority: high` (`context_enrichment.py:1406`) — campo que `_block_priority` (`:383`)
   IGNORA (solo mira el `id`).
6. Maquinaria de eficiencia ya existente pero apagada: dedup léxico I0.1
   (`_dedup_blocks`, `:252`, flag `STACKY_CONTEXT_DEDUP_ENABLED` default OFF, `:274`) y
   presupuesto+rerank F2.4/I2.1 (`_apply_context_budget`, `:398`, gateado por
   `cli_feature_flags.context_budget_enabled`, `:424`).
7. Los 3 runtimes convergen en `enrich_blocks` (`context_enrichment.py:60`; call sites:
   `agent_runner.py:695`, `codex_cli_runner.py:329`, `claude_code_cli_runner.py:581`) →
   cualquier fix ahí tiene **paridad automática**. El camino interactivo `open_chat`
   (`api/agents.py:991`) solo re-inyecta client-profile (fuera de scope, §6).
8. Precedente de contrato declarativo en frontmatter: `stacky_requires_client_profile:
   true` (`FunctionalAnalyst.agent.md:7`; también en Developer y TechnicalAnalyst.v2).
   Nota verificada: esa clave HOY no la parsea ningún `.py` del backend (grep sin hits) —
   este plan introduce el primer parser real de contrato de frontmatter (F5), con el
   parser de referencia de `tests/test_business_agent_bundled.py:16 _parse_frontmatter`.

## 3. Principios y guardarraíles (no negociables)

1. **Paridad 3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): F1/F2 viven
   en el endpoint `/run` (común a los 3); F3/F4/F6 viven dentro de `enrich_blocks`
   (común a los 3); F5 se engancha en los 3 call sites con el MISMO helper compartido.
   Cada fase declara su impacto por runtime y su fallback.
2. **Cero trabajo extra para el operador:** todo automático. El 400 accionable AYUDA
   (dice exactamente qué prerequisito falta y cómo resolverlo); no agrega pasos.
3. **Fail-open ante red, fail-closed ante hechos deterministas:** un timeout de ADO
   NUNCA bloquea un run (se degrada a warning y se sigue con el snapshot local); un
   prerequisito determinista incumplido (tipo/estado del snapshot fresco) SÍ bloquea.
4. **Human-in-the-loop:** este plan no automatiza ninguna decisión del operador; solo
   evita lanzamientos que iban a fallar y garantiza el contexto que el agente declara.
5. **Mono-operador sin auth real:** nada de RBAC; `current_user` sigue siendo un header
   sin validar.
6. **Directiva de flags del operador (verbatim):** "no quiero que haya flags default off
   que sirvan y no sean nosivas". TODAS las flags nuevas de este plan van **default ON**
   con el patrón triple del Plan 127: (1) `FlagSpec(default=True)` en
   `services/harness_flags.py`, (2) alta en `_CURATED_DEFAULTS_ON` en
   `tests/test_harness_flags.py:465`, (3) default `"true"` en `config.py`. Gotcha: un
   FlagSpec default ON fuera de `_CURATED_DEFAULTS_ON` rompe
   `test_default_known_only_for_curated`. Prohibido: asserts que fijen legacy `=false`;
   regenerar `harness_defaults.env` (§3.11 del Plan 127). Toda flag queda visible y
   toggleable en `HarnessFlagsPanel` automáticamente al darla de alta en el registry
   (patrón establecido; no requiere código frontend).
7. **Sin `requires` R4:** las 5 flags nuevas son independientes (ninguna arista en
   `_REQUIRES_MAP_FROZEN`). Cada una degrada sola a no-op si su insumo falta en runtime.
8. **Staging quirúrgico:** hay WIP ajeno vivo en el working tree (`api/agents.py`,
   `config.py`, `copilot_bridge.py`, etc.). Commitear SIEMPRE con pathspec explícito
   (`git commit -- <paths>`), NUNCA `git add -A` ni commit plano.
9. **Centinelas conocidos:** flag nueva sin entrada en `PLAIN_HELP`
   (`services/harness_flags_help.py`) deja rojo `tests/test_harness_flags_help.py`
   (cobertura 100% del registry). Test backend nuevo debe registrarse en
   `HARNESS_TEST_FILES` (los dos scripts, `.sh` y `.ps1`; ubicarlos con
   `grep -r "HARNESS_TEST_FILES"`) o falla el meta-test del Plan 49.
10. **Reusar, no crear:** prohibido reimplementar sync (`upsert_single_work_item`),
    caché (`ado_read_cache.get_or_fetch`), preflight (`run_preflight.PreflightResult`),
    o el pipeline de bloques. Este plan solo agrega predicados, un bloque, un parser y
    prioridades.

## 4. Fases

**Entorno de tests (leer antes de empezar):** venv real del repo =
`Stacky Agents/backend/.venv` (py3.13). Correr pytest SIEMPRE por archivo, desde
`Stacky Agents/backend`:

```powershell
.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q
```

La suite completa tiene fallas preexistentes (memoria documentada): NO usarla como gate.
Cada fase se cierra con sus archivos de test en verde + los centinelas nombrados.

---

### F0 — Flags nuevas (registro + help + config + curated) — fundación

**Objetivo:** dar de alta las 5 flags nuevas, default ON, visibles en la UI, con los 3
centinelas en verde, ANTES de escribir lógica (así cada fase siguiente solo lee config).

**Flags (nombres exactos, todas `default=True`):**

| Flag | Gatea | Fase |
|---|---|---|
| `STACKY_RUN_TICKET_REFRESH_ENABLED` | refresh just-in-time del ticket | F1 |
| `STACKY_BUSINESS_PREFLIGHT_ENABLED` | preflight de negocio en `/run` | F2 |
| `STACKY_ADO_BLOCKER_BLOCK_ENABLED` | bloque `ado-blocker` server-side | F3 |
| `STACKY_RUN_DIRECTIVE_ENABLED` | bloque `run-directive` server-side | F4 |
| `STACKY_REQUIRED_BLOCKS_ENABLED` | validación `stacky_required_blocks` | F5 |

**Justificación default ON (por directiva §3.6, una línea por flag):** F1 solo agrega
una lectura al tracker cacheable (no gasta tokens); F2/F5 AHORRAN runs quemados; F3/F4
agregan un bloque chico (~10 líneas) que evita abortos de contrato — beneficio >> costo.
Ninguna es nociva ni gasta tokens de forma material.

**Archivos y cambios exactos:**

1. `Stacky Agents/backend/services/harness_flags.py` — 5 `FlagSpec` nuevos, copiando la
   estructura del FlagSpec de `STACKY_RUN_PREFLIGHT_GATE_ENABLED` (`harness_flags.py:1056`):
   misma categoría, `default=True`, `restart_required=False`, sin `requires`, sin
   `min/max`. `label`/`description` en español, 1 línea cada una (texto libre pero
   específico: qué hace ON, qué pasa OFF).
2. `Stacky Agents/backend/services/harness_flags_help.py` — 5 entradas `PlainHelp`
   nuevas, copiando el formato de la de `STACKY_RUN_PREFLIGHT_GATE_ENABLED` (`:492`).
3. `Stacky Agents/backend/config.py` — 5 atributos nuevos junto al bloque donde vive
   `STACKY_RUN_PREFLIGHT_GATE_ENABLED`, leyendo env con default `"true"`, mismo parseo
   booleano que las flags vecinas (copiar el patrón literal de la línea vecina).
4. `Stacky Agents/backend/tests/test_harness_flags.py` — agregar los 5 nombres al set
   `_CURATED_DEFAULTS_ON` (`:465`).

**Tests (TDD — escribirlos primero, verlos fallar, implementar):**

- Archivo nuevo: `Stacky Agents/backend/tests/test_context_contract_flags.py`
  - `test_las_cinco_flags_existen_en_registry_con_default_true`
  - `test_las_cinco_flags_tienen_config_attr_default_true` (monkeypatch env vacío →
    `config.STACKY_..._ENABLED is True`)
  - `test_flag_off_por_env` (env `"false"` → atributo False)
- Registrar el archivo en `HARNESS_TEST_FILES` (.sh y .ps1, §3.9).

**Criterio de aceptación (binario):**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_context_contract_flags.py tests\test_harness_flags.py tests\test_harness_flags_help.py -q
```
→ 0 failed. Las 5 flags aparecen en `HarnessFlagsPanel` (verificación visual: sub-tab
Arnés muestra las 5 con toggle ON).

**Runtimes:** N/A (solo registro). **Trabajo del operador: ninguno.**

---

### F1 — Refresh just-in-time del ticket (cierra causa raíz 3)

**Objetivo:** re-sincronizar `work_item_type`/`ado_state`/título/descripción del ticket
desde el tracker al inicio del `/run`, integrado con el caché TTL I3.2, para que
preflight (F2) e inyección (F4/`_inject_epic_structured`) decidan sobre datos frescos.

**Archivo nuevo:** `Stacky Agents/backend/services/run_ticket_refresh.py`

```python
"""Plan 133 F1 — Refresh just-in-time del snapshot local del ticket antes del run."""
from __future__ import annotations
import logging
logger = logging.getLogger("stacky.services.run_ticket_refresh")

def refresh_ticket_snapshot(ticket_id: int) -> dict:
    """Re-sincroniza el work item del ticket desde el tracker.

    Retorna {"refreshed": bool, "reason": str}. NUNCA levanta excepción
    (fail-open ante red, §3.3). Con flag OFF o ticket sin ado_id positivo:
    no-op {"refreshed": False, "reason": "..."}.
    """
    from config import config
    if not getattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", False):
        return {"refreshed": False, "reason": "flag_off"}
    # 1. Cargar Ticket local (session_scope, patrón de enrich_blocks
    #    context_enrichment.py:85-91). Sin ticket o ado_id None/<=0 →
    #    {"refreshed": False, "reason": "no_ado_id"}  (sentinels negativos
    #    -1..-8 NUNCA se refrescan).
    # 2. Solo tracker ADO en v1: si el provider del proyecto no es ADO →
    #    {"refreshed": False, "reason": "non_ado_tracker"}.
    # 3. Construir AdoClient como lo hace services/ado_sync.py (mismo helper
    #    de credenciales/proyecto que usa sync_tickets, ado_sync.py:102).
    # 4. Llamar vía caché I3.2 para no duplicar llamadas dentro del mismo run:
    #    from services import ado_read_cache
    #    from services.ado_sync import upsert_single_work_item
    #    ttl = int(getattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 0) or 0)
    #    ado_read_cache.get_or_fetch(
    #        ("run_refresh", ado_id),
    #        lambda: upsert_single_work_item(client, ado_id),
    #        ttl_sec=ttl,
    #    )   # ttl 0 = siempre fetch (byte-idéntico al contrato del caché,
    #        # ado_read_cache.py:6-7,95)
    # 5. Éxito → {"refreshed": True, "reason": "ok"}.
    #    Cualquier excepción → logger.warning + {"refreshed": False,
    #    "reason": f"tracker_error: {exc}"}.
```

`upsert_single_work_item(client, ado_id)` (`ado_sync.py:235`) ya persiste el work item
en el Ticket local — no duplicar esa lógica, solo invocarla.

**Hook (1 solo call site):** `Stacky Agents/backend/api/agents.py`, dentro del handler
de `POST /api/agents/run` (`:339`), INMEDIATAMENTE después de resolver el ticket y ANTES
de cualquier validación/lanzamiento:

```python
from services.run_ticket_refresh import refresh_ticket_snapshot
_refresh = refresh_ticket_snapshot(ticket_id)  # best-effort, nunca levanta
```

El resultado `_refresh` se pasa luego al preflight F2 (para el campo `snapshot_fresh`).

**Tests primero:** `Stacky Agents/backend/tests/test_run_ticket_refresh.py`
1. `test_flag_off_es_noop` — monkeypatch config OFF → `{"refreshed": False, "reason": "flag_off"}`, y NO se llama a `upsert_single_work_item` (mock).
2. `test_refresh_pisa_snapshot_stale` — Ticket local con `ado_state="To Do"`; mock de `upsert_single_work_item` que actualiza a `"Doing"` → tras la llamada el Ticket local relee `"Doing"` y retorno `{"refreshed": True, ...}`.
3. `test_error_de_red_es_fail_open` — mock que levanta `Exception("timeout")` → retorno `{"refreshed": False, "reason": "tracker_error: timeout"}`, sin excepción propagada.
4. `test_ado_id_negativo_o_none_es_noop` — sentinel `-6` y `None` → `"no_ado_id"`.
5. `test_usa_cache_ttl` — con TTL>0 (monkeypatch), dos llamadas seguidas → `upsert_single_work_item` invocado 1 sola vez (mock con contador).

Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación:** `pytest tests\test_run_ticket_refresh.py -q` → 5 passed.
**Runtimes:** paridad automática (el hook está en `/run`, antes de bifurcar por runtime).
Fallback: flag OFF o tracker no-ADO → comportamiento actual byte-idéntico.
**Trabajo del operador: ninguno.**

---

### F2 — Preflight de negocio en `/run` (cierra causa raíz 1)

**Objetivo:** rechazar con 400 accionable el lanzamiento de un agente cuyo ticket no
cumple los prerequisitos deterministas del contrato del agente, ANTES de gastar el run.

**Archivo nuevo:** `Stacky Agents/backend/services/business_preflight.py`

```python
"""Plan 133 F2 — Predicados de negocio por agent_type antes de lanzar el run.

Complementa (NO reemplaza) el gate de infraestructura G0.1
(services/run_preflight.py). Fail-closed ante hechos deterministas del
snapshot local (tipo/estado), fail-open ante errores de red (comentarios)."""
from __future__ import annotations
from dataclasses import dataclass, field

BLOCKER_MARKER = "🚫 BLOQUEANTE TÉCNICO"  # espejo de FunctionalAnalyst.agent.md:50

@dataclass
class BusinessPreflightResult:
    ok: bool
    mode: str | None = None            # "A" | "B" | None
    reason: str = ""                   # legible, en español, accionable
    check: str | None = None           # id máquina del predicado fallido
    epic_ado_id: int | None = None     # Modo A: ado_id de la épica
    validated_state: str | None = None # estado del ticket validado
    blocker: dict | None = None        # Modo B: {author, date, excerpt}
    warnings: list[str] = field(default_factory=list)

def evaluate(*, ticket_id: int, agent_type: str) -> BusinessPreflightResult:
    """Evalúa predicados para agent_type. Sin predicados registrados para ese
    agent_type, o flag OFF → ok=True (identidad). NUNCA levanta excepción."""
```

**Reglas exactas de `evaluate` (v1 solo registra predicados para
`agent_type == "functional"`; el registro es un dict módulo-nivel
`_PREDICATES: dict[str, callable]` para extender después sin tocar el core):**

0. Flag `STACKY_BUSINESS_PREFLIGHT_ENABLED` OFF, o `agent_type not in _PREDICATES`, o
   ticket inexistente, o `ado_id` None/negativo (sentinels -1..-8) → `ok=True`.
1. Cargar snapshot local del Ticket (post-refresh F1): `work_item_type`, `ado_state`.
2. Cargar client-profile con el MISMO loader que usa `_inject_client_profile_block`
   (`context_enrichment.py:110`; leer esa función y reusar su import — prohibido crear
   otro loader). `input_states = profile["tracker_state_machine"]["functional"]["input_states"]`
   (defensivo: ausente → lista vacía; el validador del profile ya la tipa como lista,
   `services/client_profile.py:158-160`).
3. **Modo A:** `work_item_type == "Epic"` Y (`input_states` vacía O `ado_state in
   input_states`) → `ok=True, mode="A", epic_ado_id=ticket.ado_id,
   validated_state=ado_state`.
4. **Modo B:** si no aplica Modo A, buscar el marcador `BLOCKER_MARKER` en los
   comentarios del work item: reusar el MISMO fetch de comentarios que usa
   `ado_context.enrich` (`services/ado_context.py:305`; leer y reusar su helper de
   comentarios, límite 30, más reciente primero). Si el comentario MÁS RECIENTE que
   contiene el marcador existe → `ok=True, mode="B",
   blocker={"author":..., "date":..., "excerpt": primeras 500 chars}`.
   Además: si `profile["tracker_state_machine"]["functional"]` define la clave
   `blocked_states` (lista no vacía), exigir también `ado_state in blocked_states`;
   si la clave NO existe en el profile → no exigir estado (solo marcador).
5. **Fail-open de red (§3.3):** si el fetch de comentarios levanta excepción →
   `ok=True, mode=None, warnings=["comentarios inaccesibles: <exc> — el agente hará el
   cross-check"]` (NO bloquear por timeout).
6. **Fail-closed determinista:** si no aplicó Modo A, los comentarios SÍ se leyeron y
   ninguno tiene el marcador → `ok=False, check="functional_prereqs_unmet",
   reason=` (texto EXACTO, con interpolación):
   `"FunctionalAnalyst requiere: (Modo A) una Épica en estado {input_states}, o (Modo B) un work item con comentario '🚫 BLOQUEANTE TÉCNICO'. El ticket ADO-{ado_id} es {work_item_type} en estado '{ado_state}' y no tiene comentario bloqueante. Cambiá el estado/tipo del ticket o agregá el comentario bloqueante en ADO y relanzá."`

**Hook en el endpoint:** `Stacky Agents/backend/api/agents.py` handler de
`POST /api/agents/run` (`:339`), después del refresh F1 y antes de crear la ejecución:

```python
from services.business_preflight import evaluate as business_preflight
_bp = business_preflight(ticket_id=ticket_id, agent_type=agent_type)
if not _bp.ok:
    return jsonify({
        "error": "business_preflight_failed",
        "check": _bp.check,
        "detail": _bp.reason,
        "agent_type": agent_type,
        "ticket_id": ticket_id,
    }), 400
```

(Adaptar `jsonify`/estilo de retorno al patrón EXACTO de los demás 400 del mismo
handler — leerlo primero; no inventar otro shape de error.)

**Frontend (mostrar el 400, mínimo):** los lanzadores existentes ya muestran el error
del launch en su catch (`frontend/src/hooks/useAgentRun.ts` y
`frontend/src/components/AgentLaunchModal.tsx`). Cambio único y acotado: en el catch de
CADA UNO de esos dos archivos, si el body del error tiene `error ===
"business_preflight_failed"`, mostrar `detail` (el texto accionable) en lugar del
mensaje genérico. Localizar el catch por grep de `run` + `catch` en esos 2 archivos;
NO tocar ningún otro componente.

**Tests primero:** `Stacky Agents/backend/tests/test_business_preflight.py`
1. `test_flag_off_ok_true` (identidad).
2. `test_agent_type_sin_predicados_ok_true` (`developer` → ok).
3. `test_task_doing_sin_bloqueante_rechaza` — **caso ADO-331**: Task, "Doing",
   comentarios sin marcador → `ok=False`, `check=="functional_prereqs_unmet"`, reason
   contiene `"ADO-"` y `"BLOQUEANTE TÉCNICO"`.
4. `test_epic_en_input_state_modo_a` — Epic + estado en input_states → `mode=="A"`,
   `epic_ado_id` seteado.
5. `test_epic_fuera_de_input_state_sin_bloqueante_rechaza`.
6. `test_task_con_comentario_bloqueante_modo_b` — marcador presente → `mode=="B"`,
   `blocker["excerpt"]` no vacío.
7. `test_blocked_states_definidos_exige_estado` — profile con `blocked_states=["Blocked"]`
   y ticket en "Doing" con marcador → `ok=False`.
8. `test_error_red_comentarios_fail_open` — fetch levanta → `ok=True`, warning presente.
9. `test_sentinel_negativo_ok_true` (`ado_id=-6`).
10. `test_endpoint_run_devuelve_400` — vía test client Flask sobre `/api/agents/run`
    con mock de `evaluate` → status 400 y body con `error/check/detail` (patrón de test
    de endpoint: copiar setup de un test existente de `api/agents.py`, p.ej. los de
    run_brief).

Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación:** `pytest tests\test_business_preflight.py -q` → 10 passed.
**Runtimes:** paridad automática (endpoint común). Fallback: flag OFF → `/run`
byte-idéntico. **Trabajo del operador: ninguno** (el 400 le AHORRA el run quemado y le
dice qué tocar).

---

### F3 — Bloque `ado-blocker` server-side (cierra causa raíz 4)

**Objetivo:** que el backend detecte y marque el comentario bloqueante como bloque de
contexto de primera clase, en vez de esperar que el agente lo pesque entre 30
comentarios crudos.

**Archivo:** `Stacky Agents/backend/services/ado_context.py` — dentro de `enrich`
(`:305`), después de construir el bloque `ado-comments`:

- Si `config.STACKY_ADO_BLOCKER_BLOCK_ENABLED` es True Y algún comentario contiene
  `business_preflight.BLOCKER_MARKER` (importar la constante — fuente única, prohibido
  duplicar el string): agregar un bloque ADICIONAL:

```python
{
    "id": "ado-blocker",
    "title": "🚫 Bloqueante técnico detectado (server-side)",
    "content": (
        f"Autor: {author}\nFecha: {date}\n\n{texto_completo_del_comentario_mas_reciente_con_marcador}"
    ),
    "priority": "high",
}
```

- El bloque va ANTES de `ado-comments` en la lista (orden de presentación).
- Con Modo A conocido NO se recortan comentarios en esta fase (el recorte opcional de
  ruido queda fuera de scope §6 — decisión: riesgo de perder contexto > ahorro).
- Sin marcador o flag OFF → ni una línea distinta en la salida actual (identidad).

**Tests primero:** `Stacky Agents/backend/tests/test_ado_blocker_block.py`
1. `test_sin_marcador_identidad` — bloques idénticos al comportamiento actual.
2. `test_con_marcador_agrega_bloque` — `id=="ado-blocker"`, content contiene autor y
   texto, y aparece antes de `ado-comments`.
3. `test_flag_off_identidad` aun con marcador presente.
4. `test_toma_el_mas_reciente` — 2 comentarios con marcador → gana el más nuevo.

Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación:** `pytest tests\test_ado_blocker_block.py -q` → 4 passed.
**Runtimes:** paridad automática (ado_context corre dentro de `enrich_blocks`).
Fallback: GitLab/tracker sin comentarios ADO → el enrich actual ya no produce
`ado-comments`; el bloque simplemente no aparece. **Trabajo del operador: ninguno.**

---

### F4 — Bloque `run-directive` server-side (cierra causas raíz 2 y 4)

**Objetivo:** inyectar la decisión de modo (A/B) calculada por el backend como bloque de
máxima prioridad, degradando el paso de auto-validación del agente a cross-check.

**Archivo:** `Stacky Agents/backend/services/context_enrichment.py`

1. Función nueva `_inject_run_directive(ticket_id, agent_type, blocks, log)` —
   insertarla en el pipeline de `enrich_blocks` INMEDIATAMENTE DESPUÉS de la llamada a
   `_inject_epic_structured` (`:121`):
   - Flag `STACKY_RUN_DIRECTIVE_ENABLED` OFF, o `agent_type != "functional"`, o
     ticket sin ado_id positivo → retorna `blocks` sin tocar.
   - Llama `business_preflight.evaluate(ticket_id=ticket_id, agent_type=agent_type)`
     (F2; gracias al caché TTL de F1 y al fail-open, esta segunda evaluación es barata
     y segura). Nota: si F2 rechazó, el run ni llegó acá; si `evaluate` da `ok=True`
     con `mode=None` (fail-open de red o preflight OFF), el bloque lo dice.
   - PREPEND del bloque (primero de la lista, patrón de `_inject_stacky_memory_block`):

```python
{
    "id": "run-directive",
    "title": "Directiva de ejecución (validada por Stacky server-side)",
    "content": (
        "modo: A|B|indeterminado\n"
        "razon: <BusinessPreflightResult.reason o 'prerequisitos validados'>\n"
        "epic_ado_id: <int o n/a>\n"
        "estado_validado: <validated_state o n/a>\n"
        "Instrucción: Stacky YA validó los prerequisitos de tu contrato. Tu paso de\n"
        "validación de modo es un CROSS-CHECK: si tu lectura contradice esta\n"
        "directiva, reportá la discrepancia en el output y continuá según TU contrato."
    ),
}
```

2. `Stacky Agents/backend/Stacky/agents/FunctionalAnalyst.agent.md` — actualizar la
   sección de detección de modo (`:50` y `:118-119`): agregar (SIN borrar el flujo
   actual) el párrafo: *"Si el contexto incluye un bloque `run-directive`, tomalo como
   validación previa de Stacky: usá su `modo` como hipótesis principal y tu detección
   propia como cross-check; ante discrepancia, reportala y priorizá la evidencia de los
   bloques (`ado-epic-structured` / `ado-blocker`). Si NO hay bloque `run-directive`,
   aplicá tu flujo de detección actual sin cambios."* (backward compatible: el agente
   funciona igual sin el bloque). Recordatorio de rutas: el runtime lee
   `backend/Stacky/agents/` — editar AHÍ (no DeployStackyAgents).

**Tests primero:** `Stacky Agents/backend/tests/test_run_directive_block.py`
1. `test_flag_off_identidad`.
2. `test_agent_no_functional_identidad` (`developer`).
3. `test_modo_a_prepend_primero` — mock de `evaluate` → bloque `run-directive` en
   índice 0 con `modo: A` y `epic_ado_id`.
4. `test_modo_b_incluye_razon`.
5. `test_fail_open_modo_indeterminado` — `evaluate` ok con mode None → content contiene
   `indeterminado`.
6. `test_agent_md_consume_directiva` — el texto de
   `backend/Stacky/agents/FunctionalAnalyst.agent.md` contiene `run-directive` y
   `cross-check` (test de sincronía prompt↔contrato, patrón
   `test_business_agent_bundled.py`).

Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación:** `pytest tests\test_run_directive_block.py -q` → 6 passed.
**Runtimes:** paridad automática (`enrich_blocks` común, causa 7). Fallback: flag OFF o
bloque ausente → el agente usa su flujo actual (explícito en el .agent.md).
**Trabajo del operador: ninguno.**

---

### F5 — Contrato declarativo `stacky_required_blocks` (garantía pre-spawn)

**Objetivo:** que cada `.agent.md` pueda declarar qué bloques de contexto necesita, y
que los 3 runtimes fallen pre-spawn (sin gastar tokens) con error accionable si el
enriquecimiento no los produjo.

**Sintaxis (frontmatter del `.agent.md`):**

```yaml
stacky_required_blocks: "ado-epic-structured|ado-blocker, client-profile"
```

Semántica: lista separada por comas = AND; dentro de cada término, `|` = OR de
alternativas. El ejemplo exige (`ado-epic-structured` O `ado-blocker`) Y
(`client-profile`).

**Archivo nuevo:** `Stacky Agents/backend/services/agent_contract.py`

```python
"""Plan 133 F5 — Contrato declarativo de bloques requeridos por agente."""
from __future__ import annotations
from pathlib import Path

class AgentContractError(RuntimeError):
    """Bloques requeridos ausentes tras el enriquecimiento (pre-spawn)."""

def parse_required_blocks(agent_md_text: str) -> list[list[str]]:
    """Extrae stacky_required_blocks del frontmatter YAML-lite (parser k:v línea
    a línea entre los dos '---', MISMO enfoque que
    tests/test_business_agent_bundled.py:16 _parse_frontmatter — sin dependencia
    yaml). Sin frontmatter o sin la clave → []. "a|b, c" → [["a","b"],["c"]].
    Espacios y comillas se strippean; términos vacíos se ignoran."""

def resolve_agent_md_text(vscode_agent_filename: str) -> str | None:
    """Lee el .agent.md con la MISMA resolución de ruta que el runner de Claude
    (claude_code_cli_runner.py:551-558): Path(config.VSCODE_PROMPTS_DIR)/filename,
    fallback services.stacky_agents.stacky_agents_dir(). No existe → None."""

def enforce(*, vscode_agent_filename: str, blocks: list[dict]) -> None:
    """Valida post-enrichment. Flag STACKY_REQUIRED_BLOCKS_ENABLED OFF, archivo
    ausente, o required vacío → no-op. Si falta un grupo (ningún id del OR está
    en {b.get("id") for b in blocks}) → raise AgentContractError con mensaje:
    'El agente <filename> requiere el bloque <a|b> en el contexto y el
    enriquecimiento no lo produjo. Causas típicas: ticket sin épica/bloqueante
    (corré el preflight), client-profile no configurado, o tracker inaccesible.'
    Errores propios inesperados (no AgentContractError) → no-op con log.warning
    (best-effort en el parseo, fail-closed SOLO en la ausencia determinista)."""
```

**Hooks (los 3 call sites de `enrich_blocks`, mismo patrón en cada uno):**
`agent_runner.py:695`, `codex_cli_runner.py:329`, `claude_code_cli_runner.py:581` —
inmediatamente después de recibir `(blocks, ado_stats)`:

```python
from services import agent_contract
agent_contract.enforce(vscode_agent_filename=vscode_agent_filename, blocks=blocks)
```

y en cada runner, capturar `AgentContractError` en el MISMO except/flujo donde ese
runner ya marca runs fallidos pre-spawn (leer cada runner y reusar su camino de fallo
existente), registrando `metadata["context_contract_failure"] = {"agent":
vscode_agent_filename, "detail": str(exc)}` — patrón espejo de
`metadata["precondition_failure"]` (`run_preflight.py:50`). El run queda `failed` SIN
spawnear el CLI.

**Datos:** agregar al frontmatter de
`backend/Stacky/agents/FunctionalAnalyst.agent.md` (línea nueva bajo la `:7`):

```yaml
stacky_required_blocks: "ado-epic-structured|ado-blocker|run-directive, client-profile"
```

(Se incluye `run-directive` como tercera alternativa para el fail-open de red: si ADO
está caído, F4 igual inyecta el bloque con modo `indeterminado` y el run procede — el
contrato no bloquea por un timeout, §3.3.) NO tocar otros `.agent.md` en este plan.

**Tests primero:** `Stacky Agents/backend/tests/test_agent_contract.py`
1. `test_parse_vacio_y_ausente` — texto sin frontmatter / sin clave → `[]`.
2. `test_parse_and_or` — `"a|b, c"` → `[["a","b"],["c"]]`; espacios/comillas toleradas.
3. `test_enforce_flag_off_noop` — falta todo pero flag OFF → no levanta.
4. `test_enforce_ok_con_alternativa` — blocks con `ado-blocker` y `client-profile`
   satisfacen `"ado-epic-structured|ado-blocker, client-profile"`.
5. `test_enforce_falta_grupo_levanta` — sin ninguno del primer grupo →
   `AgentContractError` cuyo mensaje contiene el nombre del grupo.
6. `test_archivo_ausente_noop`.
7. `test_functional_agent_md_declara_contrato` — el frontmatter real de
   `backend/Stacky/agents/FunctionalAnalyst.agent.md` parsea a
   `[["ado-epic-structured","ado-blocker","run-directive"],["client-profile"]]`.

Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación:** `pytest tests\test_agent_contract.py -q` → 7 passed.
**Runtimes:** paridad por construcción (mismo helper en los 3 call sites; test 4/5 son
del helper, agnósticos del runner). Fallback: flag OFF o clave ausente → cero cambio.
**Trabajo del operador: ninguno.**

---

### F6 — Prioridades de bloques honestas (cierra causa raíz 5)

**Objetivo:** que los bloques que los prompts declaran obligatorios dejen de ser
podables por el budget F2.4, y que el campo `priority: "high"` de bloques ad-hoc se
respete.

**Archivo:** `Stacky Agents/backend/services/context_enrichment.py`

1. Agregar a `_BLOCK_PRIORITY` (`:360`) las entradas exactas (todas ≥
   `_HIGH_PRIORITY_THRESHOLD = 75` → nunca se podan, y el dedup I0.1 las trata como
   fuente de verdad):

```python
    "run-directive": 105,        # Plan 133 — directiva server-side, manda casi sobre todo
    "ado-blocker": 90,           # Plan 133 — bloqueante técnico detectado server-side
    "process-catalog": 78,       # Plan 133 — el prompt lo declara lectura OBLIGATORIA
    "process-discipline": 77,    # Plan 133 — decisión REUSE vs CREATE, no podable
    "acceptance-contract": 76,   # Plan 133 — se autodeclaraba high y era podable
```

   (Verificar por grep que los `id` literales de los bloques inyectados son EXACTAMENTE
   `process-catalog`, `process-discipline` y `acceptance-contract` en sus injectors —
   `_inject_process_catalog_block`, `_inject_process_discipline_block` y el bloque de
   `:1406` — y usar el string que el código emite, no el de este doc, si difiere.)

2. Modificar `_block_priority` (`:383`) para respetar el campo ad-hoc:

```python
def _block_priority(block: dict) -> int:
    mapped = _BLOCK_PRIORITY.get(block.get("id") or "")
    if mapped is not None:
        return mapped
    if str(block.get("priority") or "").lower() == "high":
        return _HIGH_PRIORITY_THRESHOLD  # 75 — nunca podable
    return _DEFAULT_PRIORITY
```

**Sin flag** (justificación explícita §3.6: es la corrección de un bug de omisión — el
mapa contradecía el contrato declarado por los prompts; solo cambia el comportamiento
cuando budget/dedup están activos, y siempre en la dirección de NO perder bloques
obligatorios. Una flag acá sería una flag para "mantener el bug").

**Tests primero:** `Stacky Agents/backend/tests/test_block_priorities_contract.py`
1. `test_bloques_obligatorios_sobre_umbral` — para cada id nuevo:
   `_block_priority({"id": id}) >= _HIGH_PRIORITY_THRESHOLD`.
2. `test_priority_high_adhoc_respetada` — `{"id": "cualquier-cosa", "priority": "high"}`
   → 75; `priority: "HIGH"` → 75 (case-insensitive).
3. `test_default_sin_cambios` — `{"id": "desconocido"}` → 50.
4. `test_budget_no_poda_process_catalog` — con budget chico (monkeypatch
   `STACKY_CONTEXT_BUDGET_TOKENS` + `cli_feature_flags.context_budget_enabled` True),
   `_apply_context_budget` conserva íntegro un bloque `process-catalog` y trunca uno
   `ado-comments`.

Registrar en `HARNESS_TEST_FILES`. Correr TAMBIÉN los tests existentes del budget/dedup
(localizarlos: `grep -l "_apply_context_budget\|_dedup_blocks" tests/`) — si alguno
asertaba la prioridad vieja de estos ids, actualizarlo citando este plan.

**Criterio de aceptación:** `pytest tests\test_block_priorities_contract.py -q` → 4
passed + los archivos de tests existentes de budget/dedup en verde.
**Runtimes:** paridad automática. **Trabajo del operador: ninguno.**

---

### F7 — Promoción a default ON de las flags existentes (directiva del operador)

**Objetivo:** encender por defecto la maquinaria ya construida, testeada e inofensiva
que este plan toca.

**Promociones (patrón triple del Plan 127 en cada una: FlagSpec `default=True` en
`services/harness_flags.py` + alta en `_CURATED_DEFAULTS_ON`
`tests/test_harness_flags.py:465` + default `"true"` en `config.py`):**

1. **`STACKY_CONTEXT_DEDUP_ENABLED` → ON.** Ahorra tokens (poda líneas duplicadas entre
   bloques), nunca gasta; conservador por diseño (nunca poda bloques ≥75; best-effort
   con identidad ante excepción, `context_enrichment.py:252-350`). Inofensiva por
   construcción. `STACKY_CONTEXT_DEDUP_PROJECTS` (allowlist) queda como está (vacía =
   todos los proyectos).
2. **`STACKY_RUN_PREFLIGHT_GATE_ENABLED` → ON.** Con F2 el preflight deja de ser solo
   infra: ahora es la primera línea que evita runs quemados. Sus 4 predicados duros
   (`run_preflight.py:87-156`) son deterministas y locales (disco/PATH/env), no
   dependen de red, y cada fallo produce mensaje accionable
   (`metadata["precondition_failure"]`). Riesgo residual: el predicado 3 bloquea si
   falta `ADO_PAT` con auto-create ON — correcto: ese run iba a fallar al crear tasks;
   el mensaje dice exactamente qué setear.

**Decisión sobre `STACKY_CONTEXT_BUDGET` (F2.4): QUEDA OPT-IN (justificación explícita
requerida por la directiva):** el budget poda/trunca contexto en función de
`STACKY_CONTEXT_BUDGET_TOKENS`, un número que el operador debe calibrar por proyecto;
mal configurado (bajo), trunca bloques útiles de prioridad <75 (p.ej. `ado-comments`,
`few-shot-approved`) — es decir, PUEDE ser nocivo con un valor arbitrario, y apagado no
gasta nada. F6 baja el riesgo (los obligatorios ya no son podables) pero no elimina la
dependencia del valor calibrado. Cumple exactamente la excepción de la directiva
("salvo que sean nocivas"): se queda OFF por default.

**Tests:** agregar a `tests/test_context_contract_flags.py` (F0):
- `test_dedup_flag_default_on`
- `test_run_preflight_gate_default_on`
y verificar centinelas: `tests/test_harness_flags.py` + `tests/test_harness_flags_help.py`.
PROHIBIDO (§3.6): tocar `harness_defaults.env`; agregar asserts `=false` sobre estas
flags; si algún test legacy asertaba default OFF de estas dos flags, actualizarlo a ON
citando este plan (localizarlos: `grep -rl "STACKY_CONTEXT_DEDUP_ENABLED\|STACKY_RUN_PREFLIGHT_GATE_ENABLED" tests/`).

**Criterio de aceptación:**
```powershell
.venv\Scripts\python.exe -m pytest tests\test_context_contract_flags.py tests\test_harness_flags.py tests\test_harness_flags_help.py -q
```
→ 0 failed.
**Runtimes:** dedup corre en `enrich_blocks` (paridad automática); el gate G0.1 corre en
`agent_runner.py:106-134` (verificar en la implementación que ese camino es común a los
3 runtimes; si algún runner CLI no pasa por ahí, documentarlo en el commit — NO
extenderlo en este plan). **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El 400 de F2 bloquea un lanzamiento legítimo no contemplado (falso positivo). | Predicados SOLO para `functional` en v1; Modo B sin exigencia de estado salvo `blocked_states` explícito en el profile; fail-open total ante red; kill-switch `STACKY_BUSINESS_PREFLIGHT_ENABLED` en la UI. |
| R2 | El refresh F1 agrega latencia al `/run`. | 1 llamada ADO cacheada por TTL I3.2; fail-open con timeout implícito del client; flag OFF = 0 ms. |
| R3 | Doble evaluación de `evaluate` (F2 en `/run`, F4 en enrich) duplica fetch de comentarios. | El fetch va por el mismo caché TTL I3.2 cuando `STACKY_ADO_READ_CACHE_TTL_SEC > 0`; con TTL 0 son 2 llamadas livianas — aceptado y documentado. |
| R4 | `AgentContractError` (F5) deja runs en `failed` por un gap de enriquecimiento transitorio. | La alternativa `run-directive` en el contrato del functional garantiza que F4 (que no depende de red para emitir el bloque) siempre satisface el grupo; `enforce` es no-op ante errores de parseo propios. |
| R5 | F6 cambia qué se poda con budget/dedup activos y algún test legacy asertaba lo viejo. | Grep dirigido de tests de budget/dedup en F6 + actualización citando el plan; el cambio solo protege MÁS bloques, nunca poda más. |
| R6 | Gate G0.1 ON (F7) bloquea en entornos sin ADO_PAT. | El fallo es pre-run, determinista y con mensaje exacto de qué setear; kill-switch en UI; es el comportamiento correcto (ese run iba a fallar después, más caro). |
| R7 | Colisión de numeración con la sesión Fable en loop. | `docs/` re-listado inmediatamente antes de crear este archivo (133 libre); si al commitear existe otro 133, renumerar ANTES del commit (precedente planes 119/128/129). |
| R8 | WIP ajeno en `api/agents.py`/`config.py`. | Staging quirúrgico §3.8 (`git commit -- <paths>`); prohibido stash/reset. |

## 6. Fuera de scope (explícito)

- Predicados de negocio para `technical`/`developer`/`business` (el registro
  `_PREDICATES` queda listo para extender; el schema de cada contrato merece su plan).
- Recorte de comentarios ruidosos con Modo A conocido (mencionado en F3; riesgo de
  pérdida de contexto > ahorro — se decide con datos de KPI-4).
- Refresh just-in-time para GitLab (F1 es ADO-only en v1; GitLab degrada a no-op
  explícito `non_ado_tracker`).
- El camino interactivo `open_chat` (`api/agents.py:991`) — solo re-inyecta
  client-profile hoy; extenderle el contrato es otro plan.
- Promover `STACKY_CONTEXT_BUDGET`/`STACKY_CONTEXT_RERANK_ENABLED` a ON (justificado en F7).
- `stacky_required_blocks` en otros `.agent.md` distintos de FunctionalAnalyst.
- Cambios al Protocol del puerto tracker, a `PORT_METHODS`, o al contrato de
  `enrich_blocks` (firma intacta: `(blocks, ado_stats)`).

## 7. Glosario, Orden de implementación y DoD

**Glosario (dominio Stacky):**
- **Bloque de contexto:** dict `{id, title, content, ...}` que el pipeline de
  `enrich_blocks` arma y el prompt_builder serializa al prompt del agente.
- **Modo A / Modo B:** los dos modos del contrato del FunctionalAnalyst — A: desglosar
  una Épica; B: resolver un bloqueante técnico reportado en comentarios.
- **Runtime:** motor de ejecución del agente — `codex_cli`, `claude_code_cli`,
  `github_copilot`.
- **G0.1:** gate de preflight de infraestructura (`services/run_preflight.py`).
- **I0.1 / F2.4 / I2.1 / I3.2:** dedup léxico de bloques / presupuesto de tokens /
  rerank TF-IDF / caché TTL de lecturas ADO (todos preexistentes).
- **Sentinels:** `ado_id` negativos -1..-8 reservados para agentes internos (doctor,
  documentador, etc.) — nunca sincronizan con el tracker.
- **Patrón triple (Plan 127):** FlagSpec `default=True` + `_CURATED_DEFAULTS_ON` +
  default `"true"` en `config.py`.

**Orden de implementación (estricto, cada fase cierra verde antes de la siguiente):**
1. **F0** — flags + help + config + curated (fundación).
2. **F1** — refresh just-in-time (insumo de F2/F4).
3. **F2** — preflight de negocio + 400 accionable + frontend mínimo.
4. **F3** — bloque `ado-blocker` (insumo de F4/F5).
5. **F4** — bloque `run-directive` + actualización del `.agent.md`.
6. **F5** — `stacky_required_blocks` + enforce en los 3 runners.
7. **F6** — prioridades honestas.
8. **F7** — promociones default ON (dedup + preflight gate).

**Definición de Hecho (DoD) global:**
- [ ] Los 7 archivos de test nuevos en verde, corridos por archivo con
  `.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`, output real leído (cero
  falsos verdes).
- [ ] Centinelas en verde: `tests/test_harness_flags.py`,
  `tests/test_harness_flags_help.py`, meta-test de `HARNESS_TEST_FILES`.
- [ ] Las 5 flags nuevas + 2 promovidas visibles y toggleables en `HarnessFlagsPanel`.
- [ ] Caso ADO-331 reproducido: `functional` sobre Task "Doing" sin bloqueante → 400
  con el texto de F2 (test 3 + verificación manual de 1 minuto).
- [ ] Con todas las flags del plan en OFF vía env: `/run` y `enrich_blocks`
  byte-idénticos al comportamiento actual (tests de identidad de cada fase), salvo F6
  (sin flag, justificado).
- [ ] `harness_defaults.env` NO tocado; ningún assert nuevo `=false` sobre flags
  promovidas.
- [ ] Commits con pathspec explícito, WIP ajeno intacto, push manual del operador.
- [ ] Encabezado de estado de este doc actualizado al cerrar
  (PROPUESTO → CRITICADO → IMPLEMENTADO).

**Trabajo del operador: ninguno.**
