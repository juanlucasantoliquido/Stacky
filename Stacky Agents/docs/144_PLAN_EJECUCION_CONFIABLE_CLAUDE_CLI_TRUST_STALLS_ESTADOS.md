# Plan 144 — Ejecución confiable de Claude CLI en deploy: trust de workspace + cierre rápido de stalls/timeouts + contrato de estados terminales

- **Estado:** CRITICADO v1→v2 · VEREDICTO: **APROBADO-CON-CAMBIOS**
- **Fecha:** 2026-07-15
- **Autor:** StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8)
- **Crítica/mejora v2:** StackyArchitectaUltraEficientCode (juez adversarial, perfil normal)
- **Serie:** 144–149 (derivada de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`)
- **Cubre hallazgos:** **D1** (trust de workspace), **D2** (stall watchdog opaco), **D3** (ticket colgado 120 min), **D4** (vocabulario de estados divergente).
- **Cross-refs:** 145 (higiene/observabilidad de logs), 146 (quick-wins verificados: V1/V4/V5), 147 (rutas de proyecto V2/D8). Este plan **no** toca esos alcances; solo declara dependencias.

---

## 0. Changelog v1 → v2 (crítica adversarial)

Todas las citas `[V]` del v1 fueron re-verificadas contra el código real (repo root `N:\GIT\RS\STACKY\Stacky\Stacky Agents`). Núcleo confirmado: `ticket_status.py:35` (`VALID_STATUSES` **sin** `needs_review`), `ticket_status.py:110-111` (`raise ValueError`), `agent_completion.py:44` (`TERMINAL_STATUSES` **con** `needs_review`), codex degrada a `needs_review` (`codex_cli_runner.py:761`, `:851`), `_run_pre_run_checks` (`claude_code_cli_runner.py:2689-2731`, con `log`/`_mark_terminal`/`ticket_status`/`config` en scope), `on_execution_end` (`ticket_status.py:214-266`), `STACKY_STALL_WATCHDOG_SECONDS` default 600 (`config.py:688-689`), `_CATEGORY_KEYS`/`runtimes_cli` (`harness_flags.py:114-124`), `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`), tests preexistentes existen. **La FOCO-crítica #1 (auto-set opt-in default OFF, nunca automático) quedó confirmada correcta** — no es bloqueante.

Cambios aplicados (detalle inline en cada fase afectada):

- **C0 (F2, ROMPE TEST — bloqueante de implementación):** el v1 declara `requires="CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED"` en la FlagSpec de AUTOSET pero NO agrega la arista al mapa congelado `_REQUIRES_MAP_FROZEN` de `tests/test_harness_flags_requires.py:120`, ni corre ese archivo. `test_requires_map_is_frozen:187` asevera `actual == _REQUIRES_MAP_FROZEN` → **falla** al implementar. Corregido: F2 agrega la arista al mapa y corre `test_harness_flags_requires.py` en F2/F5. (R4/profundidad-1 y R1 verificados OK: `PREFLIGHT` está registrada y NO declara `requires` propio → cadena de profundidad 1, válida.)
- **C1 (F4, coupling real):** `trust_ok` del `stall_meta` NO se poblaba: el builder del stall lee el `metadata` local del streaming (`:1350`), que nunca recibe la key `"trust"` (el preflight la escribe en `row.metadata_dict`, otra función/scope). Corregido: el stall builder lee el trust **persistido** desde `row.metadata_dict`; se documenta que `trust_ok` solo aporta señal con preflight OFF; test nuevo.
- **C2 (§2/F1, atribución causal):** los paths de *stall* (`claude:1629`, `codex:726`) llaman `on_execution_end(final_status="error")` — `"error"` **siempre** fue válido, nunca estallaron por D4. Los verdaderos afectados por D4 son los paths `needs_review` (codex runaway `:761`, autocorrect `:851`, y el path dinámico de calidad claude `:1732`). Narrativa corregida (el fix F0/F1 sigue siendo correcto).
- **C3 (F4, ambigüedad para modelos menores):** se fija el mapeo EXACTO del `stall_meta` de codex (6 keys idénticas a claude, `trust_ok=True` n/a documentado) y se limpia el ternario muerto `if False` de `codex_cli_runner.py:715`.
- **C4 (F4, contrato UI):** se agrega verificación de que el endpoint GET de ejecución serializa `metadata.stall` (si no, el drawer no muestra nada) + test backend.
- **C5 (cross-plan 147):** el keying de trust debe usar el `cwd` resuelto (`_resolve_cwd`), no el `workspace_root` crudo, para no driftear cuando 147 estandarice la resolución de raíz.
- **C6 (citas):** refs de línea de codex corregidas a los `on_execution_end` reales (`:761`, `:851`).
- **C7 (F1 test):** `test_no_ticket_is_noop` se hace hermético (patch de `_POST_HOOKS`).
- **C8 (backward-compat UI):** grep del enum de `stacky_status` en frontend para garantizar que `needs_review` renderiza (label/color).
- **[ADICIÓN ARQUITECTO]:** test de contrato que **escanea el fuente** de los 3 runners y asevera que todo literal `final_status="..."` ∈ `VALID_TICKET_STATUSES` (guarda proactiva del bug D4, complementa al `_coerce_terminal_status` defensivo).

---

## 1. Título, objetivo e impacto esperado

**Objetivo.** Hacer que un run de Claude Code CLI en producción **nunca muera en silencio ni deje un ticket colgado 2 horas**. Se ataca la cadena causal completa observada en el DEPLOY v1.0.76: (1) el workspace no está confiado y el CLI sale con `code 1` sin diagnóstico accionable (**D1**); (2) los runs degradados se cuelgan hasta que el stall watchdog los mata a ~600 s sin explicar por qué (**D2**); (3) el ticket asociado queda en `running` hasta el reaper de 120 min (**D3**); y (4) cuando la capa de completion intenta degradar a `needs_review`, el validador de estados del ticket lo **rechaza** y lanza `ValueError`, lo que estranca el ticket en `running` (**D4** — causa raíz real de D3). El plan cierra los cuatro con un preflight de confianza determinista, una transición terminal **garantizada e inmediata**, y una **única fuente de verdad** de estados con test de contrato.

**KPI / impacto esperado (medible contra los logs del reporte):**

| Métrica | Antes (DEPLOY v1.0.76) | Meta post-plan |
|---|---|---|
| Runs muertos por `exited with code 1: ... workspace has not been trusted` (D1) | 8 ERROR + 15 WARNING | 0 (preflight detecta y o bien auto-confía [opt-in] o falla temprano con remedio en el run record) |
| Tickets recuperados por el reaper de 120 min (D3) | 2 tickets (120, 121) | 0 en el caso `needs_review`; reaper queda solo como red de seguridad |
| `Estado inválido: 'needs_review'` (D4) | ≥1 ERROR/run degradado | 0 (test de contrato lo prohíbe) |
| Eventos de stall sin diagnóstico (D2) | 7 runs "605s sin eventos" sin última señal | 100% de stalls con `last_signal` + correlación de trust en metadata y UI |

**Naturaleza del cambio:** aditivo y backward-compatible. Dos flags nuevas (una kill-switch default ON, una opt-in default OFF con excepción dura citada), un módulo de vocabulario compartido, un módulo de trust, y endurecimiento de una transición existente. Sin pasos manuales nuevos para el operador en el camino default.

---

## 2. Por qué ahora / gap que se cierra

- **Es el bloqueo #1 de producción.** El reporte lo marca Crítico: *"los runs mueren o cuelgan 2h. Sin esto, el deploy no ejecuta agentes"* (§7, candidato #1). No es cosmético: la instancia desplegada no puede ejecutar agentes contra RSPACIFICO.
- **La causa raíz de D3 es D4, y está viva en el working tree, no solo en el deploy.** Verificado [V]: `services/agent_completion.py:44` define `TERMINAL_STATUSES` **con** `needs_review`, pero `services/ticket_status.py:35` define `VALID_STATUSES` **sin** `needs_review`, y `set_status` (`ticket_status.py:110-111`) hace `raise ValueError(f"Estado inválido: '{new_status}'. Válidos: {sorted(VALID_STATUSES)}")`. Cualquier `on_execution_end(final_status="needs_review")` estalla. Esto ocurre HOY en ambos runners: el runner de Codex degrada a `needs_review` en runaway (`codex_cli_runner.py:761`, `on_execution_end(final_status="needs_review")`) y en autocorrect (`:851`); en Claude el path dinámico de calidad/contrato pasa un `final_status` variable a `on_execution_end` (`claude_code_cli_runner.py:1732`) que puede ser `needs_review`. Por eso D3 tiene **dependencia dura** de D4.
- **Precisión causal (corregida en v2, C2).** Los paths de **stall** NO son los que estrancaban el ticket: tanto Claude (`claude_code_cli_runner.py:1629-1635`) como Codex (`codex_cli_runner.py:726-728`) llaman `on_execution_end(final_status="error")`, y `"error"` **siempre** estuvo en `VALID_STATUSES` → nunca dispararon el `ValueError` de D4 ni dejaron el ticket en `running`. Los tickets 120/121 recuperados por el reaper (D3) provinieron de los paths `needs_review` (codex `:761`/`:851`, claude dinámico `:1732`), que sí estallaban. El fix F0/F1 es correcto; esta nota solo afina la atribución.
- **El watchdog ya existe y funciona, pero es opaco.** `claude_code_cli_runner.py:1300-1323` mata el run a `STACKY_STALL_WATCHDOG_SECONDS` (default 600, `config.py:688-689`) y guarda `metadata["stall"] = {detected_at, last_event_at}` (`:1617-1621`). Falta la **última señal conocida** (qué estaba haciendo el run) y la correlación con el estado de trust, que es justo lo que un operador necesita para no repetir el run a ciegas.
- **No hay ningún preflight de trust.** Verificado [V]: grep de `hasTrustDialogAccepted` / `has not been trusted` / `trust` en `claude_code_cli_runner.py` → **0 coincidencias**. Stacky lanza el CLI y recibe el `code 1` sin haberlo anticipado.

---

## 3. Principios y guardarrailes (codificados por fase)

1. **Paridad de 3 runtimes con degradación explícita.**
   - **D4 (vocabulario)** y **D3 (transición robusta)** son **runtime-agnósticos**: viven en `services/status_vocabulary.py` (nuevo) y `services/ticket_status.on_execution_end`, que **los 3 runtimes ya invocan**. El fix aplica idéntico a Claude, Codex y Copilot sin código duplicado.
   - **D1 (trust de workspace)** es **específico del binario `claude`**: el concepto `hasTrustDialogAccepted` vive en `~/.claude.json`. **Codex CLI no tiene ese concepto** (verificado [V]: grep de `trust`/`.claude.json` en `codex_cli_runner.py` → 0; usa `workspace_root` solo como `cwd` en `_resolve_cwd`, `:1322`). **Copilot corre in-process** (sin CLI, sin `.claude.json`). Degradación: el preflight de trust es **no-op silencioso** para Codex y Copilot (skip, log `debug`). Se declara explícito en F2/F5.
   - **D2 (enriquecimiento del stall)** aplica a Claude y Codex (ambos tienen watchdog: `claude:1300-1323`, `codex_cli_runner.py:632-648`); Copilot no tiene watchdog de stream de subproceso (no aplica; sin regresión).
2. **Cero trabajo extra al operador (con una excepción dura citada).** El camino default (preflight ON + autoset OFF) **no agrega ningún paso manual**: detecta el problema y lo reporta accionable en el run record. El **auto-set** de `hasTrustDialogAccepted` es opt-in default OFF porque **dispara la excepción dura (d) "reduce seguridad por default"** (escribe un setting de seguridad de `~/.claude.json`). Se activa solo por decisión explícita del operador desde la UI. Ninguna otra fase agrega trabajo.
3. **Human-in-the-loop.** El preflight **amplifica** al operador (le dice exactamente qué pasa y cómo arreglarlo); no decide por él. El auto-set nunca se activa solo.
4. **Mono-operador sin auth.** Ningún cambio toca identidad/roles.
5. **No degradar performance/seguridad/estabilidad/DX; reutilizar.** El preflight es una lectura de un JSON pequeño (`~/.claude.json`) una vez por run, antes del spawn (costo despreciable). El reaper de 120 min **se conserva intacto** como red de seguridad (no se acorta ni se elimina). Se reutiliza `ticket_status`, `TERMINAL_STATUSES`, el `metadata["stall"]` existente y el patrón de flags del arnés.

**Patrón triple de flags (regla dura del repo).** Una flag nueva **default ON** exige: (i) `FlagSpec(..., default=True)` en `services/harness_flags.py`; (ii) su key en `_CURATED_DEFAULTS_ON` de `tests/test_harness_flags.py:467`; (iii) default `"true"` en `config.py`. Una flag **default OFF** **no** lleva `default=` en su `FlagSpec` (si lo lleva, `default_is_known` se vuelve True y rompe `test_default_known_only_for_curated`, `test_harness_flags.py:700`); su default OFF vive solo en `config.py` (`"false"`). **Toda** flag nueva debe además agregarse a `_CATEGORY_KEYS` (`harness_flags.py:114`) o rompe `test_every_registry_flag_is_categorized`. **Y toda flag con `requires=X` (regla dura Plan 82, C0):** (i) `X` debe estar registrada en `FLAG_REGISTRY` y **no** declarar `requires` propio (R1/R4 profundidad-1, validado en runtime por `validate_requires_graph()`, `harness_flags.py:2924`); (ii) la arista debe agregarse a `_REQUIRES_MAP_FROZEN` de `tests/test_harness_flags_requires.py:120` o rompe `test_requires_map_is_frozen:187`; (iii) ese archivo debe correrse en los comandos de cierre.

---

## 4. Fases

> Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5**. F0 (vocabulario) es prerequisito de F1 (D3). F3 (auto-set) depende de F2 (detección). F4/F5 son aditivos.

Comando base de tests backend (venv real verificado): `backend/.venv/Scripts/python.exe -m pytest <archivo> -q` corrido **por archivo** (correr la suite completa contamina cross-file — gotcha del repo). Frontend: `frontend/node_modules/.bin/vitest run <archivo>` por archivo + `frontend/node_modules/.bin/tsc --noEmit`.

---

### F0 — Fuente única de verdad de estados terminales (cierra D4)

**Objetivo (1 frase).** Unificar el vocabulario de estados en un solo módulo importado por completion y por el validador del ticket, de modo que todo estado que completion produce sea aceptado por `set_status`.

**Valor.** Elimina la contradicción `TERMINAL_STATUSES` (con `needs_review`) vs `VALID_STATUSES` (sin `needs_review`) que hoy lanza `ValueError` y estranca el ticket en `running` (raíz de D3).

**Archivos EXACTOS:**
- **CREAR** `backend/services/status_vocabulary.py`.
- **EDITAR** `backend/services/ticket_status.py` (línea 35).
- **EDITAR** `backend/services/agent_completion.py` (línea 44).
- **CREAR** `backend/tests/test_status_vocabulary_contract.py`.

**Contenido de `status_vocabulary.py` (nombres EXACTOS):**
```python
"""Fuente ÚNICA de verdad del vocabulario de estados de Stacky (Plan 144 F0).

Antes existían dos definiciones divergentes:
  - agent_completion.TERMINAL_STATUSES  (con needs_review)
  - ticket_status.VALID_STATUSES        (sin needs_review)  → set_status rechazaba needs_review.

Este módulo las reconcilia. NO depende de db/models (import barato, sin ciclos)."""
from __future__ import annotations

# Estados terminales que la capa de completion puede producir para un run.
TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "needs_review"})

# Estados NO terminales válidos a nivel ticket (stacky_status).
NON_TERMINAL_TICKET_STATUSES = frozenset({"idle", "running"})

# Vocabulario válido COMPLETO de stacky_status (lo que set_status acepta).
# Invariante garantizado por test de contrato: TERMINAL_STATUSES ⊆ VALID_TICKET_STATUSES.
VALID_TICKET_STATUSES = NON_TERMINAL_TICKET_STATUSES | TERMINAL_STATUSES
```

**Edición en `ticket_status.py:35`** — reemplazar la definición literal por el import (se **conserva el nombre `VALID_STATUSES`** para no romper callers ni el mensaje de error):
```python
# ANTES:
# VALID_STATUSES = frozenset({"idle", "running", "completed", "error", "cancelled"})
# DESPUÉS:
from services.status_vocabulary import VALID_TICKET_STATUSES
VALID_STATUSES = VALID_TICKET_STATUSES
```
(El `raise ValueError(...)` de `set_status:110-111` queda igual; ahora `needs_review` ∈ `VALID_STATUSES` y no dispara.)

**Edición en `agent_completion.py:44`** — reemplazar la definición literal por el import (se **conserva el nombre `TERMINAL_STATUSES`**):
```python
# ANTES:
# TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "needs_review"})
# DESPUÉS:
from services.status_vocabulary import TERMINAL_STATUSES
```
(No se toca `ACTIVE_STATUSES` en `agent_completion.py:43` — es vocabulario de *ejecución* `preparing|running|queued`, ortogonal al de ticket. Fuera de scope de F0.)

**Tests PRIMERO (`backend/tests/test_status_vocabulary_contract.py`), casos EXACTOS:**
1. `test_terminal_subset_of_valid_ticket` — `assert TERMINAL_STATUSES <= VALID_TICKET_STATUSES` (invariante central). **Falla antes** del import unificado (needs_review ∉ VALID_STATUSES viejo).
2. `test_ticket_status_valid_is_shared` — `from services import ticket_status; from services.status_vocabulary import VALID_TICKET_STATUSES; assert ticket_status.VALID_STATUSES == VALID_TICKET_STATUSES`.
3. `test_completion_terminal_is_shared` — `from services.agent_completion import TERMINAL_STATUSES as A; from services.status_vocabulary import TERMINAL_STATUSES as B; assert A is B` (misma referencia, no copia).
4. `test_set_status_accepts_needs_review` — sembrar un `Ticket` en DB de test, llamar `ticket_status.set_status(tid, "needs_review", changed_by="test")` y aseverar que **no** lanza y que `get_current_status(tid) == "needs_review"`. (Reproduce D4 end-to-end.)
5. `test_set_status_rejects_garbage` — `set_status(tid, "banana", ...)` sigue lanzando `ValueError` (no aflojamos la validación).
6. **[ADICIÓN ARQUITECTO] `test_all_runner_final_status_literals_subset`** — escanear el **fuente** de los 3 runners y asegurar que TODO literal `final_status="..."` que se pasa a `on_execution_end` pertenece a `VALID_TICKET_STATUSES`. Implementación EXACTA:
   ```python
   import re, inspect
   from services import claude_code_cli_runner, codex_cli_runner
   from services.status_vocabulary import VALID_TICKET_STATUSES

   def _literals(mod):
       src = inspect.getsource(mod)
       return set(re.findall(r'final_status\s*=\s*"([a-z_]+)"', src))

   def test_all_runner_final_status_literals_subset():
       found = _literals(claude_code_cli_runner) | _literals(codex_cli_runner)
       assert found, "esperaba al menos un literal final_status en los runners"
       assert found <= VALID_TICKET_STATUSES, (
           f"literales fuera del vocabulario: {sorted(found - VALID_TICKET_STATUSES)}")
   ```
   **Por qué (evidencia):** hoy los literales reales son `{completed, error, needs_review}` más paths **dinámicos** `final_status=final_status` (`claude:1732`, `codex:1017`) — los dinámicos los cubre el `_coerce_terminal_status` de F1; este test pinza los **literales** para que, el día que un runtime nuevo introduzca un terminal nuevo fuera del vocabulario unificado, falle en test en vez de estrancar un ticket en producción (clase de bug de D4, de forma proactiva no solo defensiva). Falla si alguien agrega, p.ej., `final_status="failed"` sin sumarlo a `status_vocabulary`.

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_status_vocabulary_contract.py -q`

**Criterio de aceptación BINARIO:** los 6 tests pasan (5 de contrato de vocabulario + el escaneo de fuente de la ADICIÓN ARQUITECTO). Verificación adicional: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_status_vocabulary_contract.py backend/tests/test_stale_recovery_guardian.py backend/tests/test_cutover_p5.py -q` (por archivo cada uno; ninguno regresa rojo).

**Flag:** ninguna. Es un **fix de bug verificado** (reconcilia dos vocabularios divergentes; solo *agrega* `needs_review` a lo aceptado por el ticket). No introduce comportamiento opt-in. **Justificación de no-flag:** un bug así, protegido por flag, dejaría el bug vivo con la flag OFF; el test de contrato es la protección correcta.

**Impacto por runtime + fallback:**
- **Claude Code CLI:** su path de completion (`_maybe_autopublish_epic`, gate de contrato `:1658-1665`) que fuerza `needs_review` ahora transiciona el ticket sin estallar.
- **Codex CLI:** su runaway (`codex_cli_runner.py:761`) y autocorrect (`:851`) que llaman `on_execution_end(final_status="needs_review")` ahora transicionan sin estallar. **Fallback:** ninguno necesario (el fix es automático vía el módulo compartido).
- **GitHub Copilot:** su completion pasa por el mismo `agent_completion`/`ticket_status`; hereda el fix. **Fallback:** ninguno.

**Trabajo del operador:** ninguno.

---

### F1 — Transición terminal garantizada e inmediata al matar un run (cierra D3)

**Objetivo (1 frase).** Garantizar que cuando el watchdog (D2) o el preflight de trust (D1) matan un run, el ticket asociado sale de `running` **inmediatamente** hacia un estado terminal, y que **ningún** valor de estado inesperado pueda volver a estrancar el ticket (defensa en profundidad contra futuros drifts de vocabulario).

**Valor.** Con F0, la transición a `needs_review` ya no estalla; F1 agrega el cinturón de seguridad: `on_execution_end` **nunca** deja el ticket en `running`, aunque llegue un estado desconocido. Así el reaper de 120 min pasa a ser red de seguridad, no el camino primario (cierra D3).

**Archivos EXACTOS:**
- **EDITAR** `backend/services/ticket_status.py` (función `on_execution_end`, `:214-266`).
- **CREAR** `backend/tests/test_ticket_status_robust_transition.py`.

**Cambio en `ticket_status.py` — helper defensivo + uso en `on_execution_end`:**
```python
# Nuevo helper de módulo (junto a set_status). NO relaja set_status:
# solo protege la transición terminal de fin de run.
def _coerce_terminal_status(requested: str) -> str:
    """Devuelve `requested` si es un estado válido; si no, cae a 'error' con log.

    Blindaje D3: un fin de run SIEMPRE debe sacar al ticket de 'running'. Un
    estado no reconocido nunca debe propagar una excepción que lo estranque."""
    if requested in VALID_STATUSES:
        return requested
    logger.warning(
        "on_execution_end: estado terminal desconocido '%s' → coercionado a 'error'",
        requested,
    )
    return "error"
```
Dentro de `on_execution_end`, antes de `set_status(ticket_id, final_status, ...)`, insertar:
```python
    final_status = _coerce_terminal_status(final_status)
```
(La firma pública de `on_execution_end` no cambia; el blindaje es interno.)

**Nota sobre el reaper (D3):** **no se modifica** `recover_stale_running_tickets` ni `EXECUTION_TIMEOUT_MINUTES` (120, `ticket_status.py:40`). El reaper queda como backstop. El acortamiento del lazo se logra porque F0 hace que los paths que sí estallaban (`needs_review`: codex `:761`/`:851`, claude dinámico `:1732`) ahora **completen** la transición inmediata, y F1 blinda cualquier valor futuro inesperado del `final_status` variable (`claude:1732`, `codex:1017`) para que nunca deje el ticket en `running`. **Precisión (C2):** los paths de *stall* (`claude:1629-1635`, `codex:726-728`) ya transicionaban bien porque usan `final_status="error"` (siempre válido); no eran los afectados por D4, pero heredan el blindaje de F1 sin cambio de comportamiento.

**Tests PRIMERO (`test_ticket_status_robust_transition.py`), casos EXACTOS:**
1. `test_needs_review_end_transitions_immediately` — sembrar ticket `running`; `on_execution_end(ticket_id=..., execution_id=..., final_status="needs_review", agent_type="developer")`; aseverar `get_current_status == "needs_review"` y **no** excepción. (Regresión directa de D3 pre-F0/F1: antes estallaba y dejaba `running`.)
2. `test_unknown_status_coerces_to_error` — `on_execution_end(..., final_status="weird_state")`; aseverar `get_current_status == "error"` (no `running`, no excepción).
3. `test_error_end_unchanged` — `final_status="error"` sigue funcionando igual (no regresión).
4. `test_no_ticket_is_noop` — `on_execution_end` sobre `ticket_id` inexistente no lanza. **Hermético (C2 crítica):** `on_execution_end` NO solo llama `set_status` (noop en ticket ausente, `ticket_status.py:115-117`); también corre `_run_post_hooks` (`:260`). Para que el test no dependa de hooks registrados por otros módulos al importar, parchear la lista de hooks: `monkeypatch.setattr(ticket_status, "_POST_HOOKS", [])` (y `_PRE_HOOKS` si aplica) antes de invocar. Aserción: no excepción.

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_status_robust_transition.py -q`

**Criterio de aceptación BINARIO:** los 4 tests pasan; además `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_b6_cancel_sync.py -q` sigue verde (no regresión de la transición de cancelación).

**Flag:** ninguna. **Justificación:** endurecimiento de un invariante de fiabilidad (un fin de run debe sacar el ticket de `running`); protegerlo con flag reintroduciría el modo colgado. El test es la protección.

**Impacto por runtime + fallback:** `on_execution_end` es el **único** punto por el que los 3 runtimes transicionan el ticket al terminar → paridad automática. **Fallback:** el reaper de 120 min sigue disponible si un runtime muriera sin llegar a `on_execution_end` (p.ej. kill -9 del proceso backend).

**Trabajo del operador:** ninguno.

---

### F2 — Preflight de confianza de workspace: detectar + fallar temprano accionable (cierra D1, default ON)

**Objetivo (1 frase).** Antes de spawnear `claude`, detectar si el `workspace_root` activo tiene `hasTrustDialogAccepted: true` en `~/.claude.json`; si no, **fallar temprano** marcando el run `error` con un mensaje accionable en el run record, en vez de dejar que el CLI salga con `code 1` mudo.

**Valor.** Convierte el bloqueo #1 de producción (8 ERROR + 15 WARNING mudos) en un fallo diagnosticado con remedio exacto, y prepara el auto-set opt-in de F3.

**Archivos EXACTOS:**
- **CREAR** `backend/services/claude_workspace_trust.py`.
- **EDITAR** `backend/services/claude_code_cli_runner.py` (función `_run_pre_run_checks`, `:2689-2731`).
- **EDITAR** `backend/config.py` (bloque Claude CLI, junto a `:246`).
- **EDITAR** `backend/services/harness_flags.py` (`FLAG_REGISTRY` y `_CATEGORY_KEYS`).
- **EDITAR** `backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`, `:467`).
- **EDITAR** `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`, `:120-184`) — **obligatorio por C0** (la AUTOSET declara `requires`).
- **CREAR** `backend/tests/test_claude_workspace_trust.py`.
- **CREAR** `backend/tests/test_claude_trust_preflight.py`.

**Contenido de `claude_workspace_trust.py` (nombres EXACTOS):**
```python
"""Preflight de confianza de workspace para el binario `claude` (Plan 144 F2/F3).

El CLI de Claude Code ignora permisos y sale con code 1 si el workspace no está
en projects[<key>].hasTrustDialogAccepted:true dentro de ~/.claude.json.
Este módulo lee/normaliza/escribe ese estado. Específico de Claude CLI:
Codex/Copilot NO lo usan (ver Plan 144 §3)."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("stacky_agents.claude_workspace_trust")


@dataclass(frozen=True)
class WorkspaceTrust:
    trusted: bool          # projects[key].hasTrustDialogAccepted is True
    present: bool          # el key del proyecto existe en projects
    config_path: str       # ruta absoluta a ~/.claude.json
    project_key: str       # key normalizado que se buscó/escribiría
    error: str | None = None  # None si la lectura fue OK


def _claude_json_path(home: str | None = None) -> Path:
    base = Path(home) if home else Path(os.path.expanduser("~"))
    return base / ".claude.json"


def _normalize_project_key(workspace_root: str) -> str:
    """El CLI keyea projects con la ruta absoluta en barras '/'.
    Evidencia [V] del log: projects["C:/desarrollo/GIT/RS/RSPACIFICO"]."""
    return str(Path(workspace_root).resolve()).replace("\\", "/")


def read_workspace_trust(workspace_root: str, *, home: str | None = None) -> WorkspaceTrust:
    key = _normalize_project_key(workspace_root)
    path = _claude_json_path(home)
    if not path.exists():
        return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                              project_key=key, error="~/.claude.json no existe")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                              project_key=key, error=f"~/.claude.json ilegible: {exc}")
    projects = data.get("projects") or {}
    entry = projects.get(key)
    if entry is None:
        return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                              project_key=key, error=None)
    return WorkspaceTrust(trusted=bool(entry.get("hasTrustDialogAccepted")),
                          present=True, config_path=str(path), project_key=key, error=None)


def set_workspace_trusted(workspace_root: str, *, home: str | None = None) -> WorkspaceTrust:
    """Escribe projects[key].hasTrustDialogAccepted = True. Hace backup previo
    (~/.claude.json.stacky.bak) y crea el archivo/estructura si falta. SOLO se
    invoca cuando el operador activó el auto-set (Plan 144 F3, excepción dura d)."""
    key = _normalize_project_key(workspace_root)
    path = _claude_json_path(home)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — no pisar un JSON que no entendemos
            return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                                  project_key=key, error="no se sobreescribe un ~/.claude.json ilegible")
        try:
            (path.parent / ".claude.json.stacky.bak").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:  # noqa: BLE001 — backup best-effort
            pass
    projects = data.setdefault("projects", {})
    entry = projects.setdefault(key, {})
    entry["hasTrustDialogAccepted"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.warning("trust auto-set aplicado a projects[%s].hasTrustDialogAccepted=true", key)
    return WorkspaceTrust(trusted=True, present=True, config_path=str(path),
                          project_key=key, error=None)
```

**Wiring en `claude_code_cli_runner.py._run_pre_run_checks` (`:2689`).** Después del `run_pull_check` y antes del `return True` (`:2731`), insertar el bloque de trust (Claude-específico):
```python
    # Plan 144 F2/F3 — preflight de confianza de workspace (solo Claude CLI).
    if config.CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED and workspace_root:
        from services import claude_workspace_trust as _cwt
        trust = _cwt.read_workspace_trust(workspace_root)
        if not trust.trusted:
            if config.CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED:
                # F3 — comportamiento explícito opt-in (excepción dura d).
                trust = _cwt.set_workspace_trusted(workspace_root)
                log("warn",
                    f"trust auto-set: workspace confiado automáticamente "
                    f"(projects[{trust.project_key}].hasTrustDialogAccepted=true)")
            else:
                remedio = (
                    f"El workspace no está confiado por Claude Code CLI. "
                    f"Abrí `claude` una vez en {trust.project_key} y aceptá el diálogo de confianza, "
                    f"o activá 'Auto-confiar workspace (claude)' en Config → Runtimes CLI, "
                    f"o seteá projects[\"{trust.project_key}\"].hasTrustDialogAccepted=true en {trust.config_path}."
                )
                log("error", f"pre-run bloqueado (trust): {remedio}")
                _mark_terminal(execution_id, status="error", error=remedio,
                               metadata={"trust": {"trusted": False, "project_key": trust.project_key}})
                if ticket_id is not None:
                    ticket_status.on_execution_end(
                        ticket_id=ticket_id, execution_id=execution_id,
                        final_status="error", agent_type=agent_type, error=remedio)
                return False
    # (fin bloque trust)
```
Guardar además `metadata["trust"]` en el path OK para que F4 lo correlacione (aditivo; si `trust.trusted`, `metadata["trust"] = {"trusted": True, "project_key": ...}`).

**`config.py` (junto a `:246`, patrón bool EXACTO del repo `.lower() in ("1","true","yes")`):**
```python
    CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
```

**`harness_flags.py` — dos `FlagSpec` nuevos en `FLAG_REGISTRY` (grupo `claude_code_cli`):**
```python
    FlagSpec(
        key="CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED",
        type="bool",
        default=True,  # Plan 144 F2 — kill-switch default ON (detecta+falla temprano; no reduce seguridad).
        label="Preflight de confianza de workspace (claude)",
        description="Antes de lanzar claude, verifica hasTrustDialogAccepted del workspace; si no, falla temprano con remedio en vez de code 1 mudo.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED",
        type="bool",
        # SIN default= → default_is_known False → NO va en _CURATED_DEFAULTS_ON (default OFF via config.py).
        label="Auto-confiar workspace (claude)",
        description="OPT-IN. Si el workspace no está confiado, escribe hasTrustDialogAccepted=true en ~/.claude.json (setting de seguridad). OFF por defecto.",
        group="claude_code_cli",
        requires="CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED",
    ),
```
**`harness_flags.py` — `_CATEGORY_KEYS["runtimes_cli"]` (`:115-124`):** agregar ambas keys `"CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED"` y `"CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED"` a la tupla.

**`test_harness_flags.py._CURATED_DEFAULTS_ON` (`:467`):** agregar **solo** `"CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED"` (la default-ON). **NO** agregar la AUTOSET.

**`test_harness_flags_requires.py._REQUIRES_MAP_FROZEN` (`:120-184`) — OBLIGATORIO (C0):** como la AUTOSET declara `requires="CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED"`, hay que agregar la arista al mapa congelado o `test_requires_map_is_frozen` (`:187`) falla:
```python
    "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED": "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED",  # Plan 144 F3
```
Verificado que NO viola R4 (profundidad 1): `CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED` NO declara `requires` propio, y está registrada en `FLAG_REGISTRY` (R1 OK). `validate_requires_graph()` (`harness_flags.py:2924`) sigue devolviendo `[]`.

**Tests PRIMERO:**

`backend/tests/test_claude_workspace_trust.py` (usa `tmp_path` como `home`):
1. `test_missing_claude_json_untrusted` — sin `~/.claude.json` → `trusted False, present False, error != None`.
2. `test_project_absent_untrusted` — `.claude.json` con `{"projects":{}}` → `trusted False, present False, error None`.
3. `test_project_present_true` — `{"projects":{"<key>":{"hasTrustDialogAccepted":true}}}` (key = `_normalize_project_key(tmp)`) → `trusted True, present True`.
4. `test_project_present_false` — `hasTrustDialogAccepted:false` → `trusted False, present True`.
5. `test_normalize_uses_forward_slashes` — `_normalize_project_key(r"C:\a\b")` no contiene `\\`.
6. `test_set_workspace_trusted_writes_and_backups` — sobre un `.claude.json` existente, `set_workspace_trusted` deja `hasTrustDialogAccepted True`, crea `.claude.json.stacky.bak`, y `read_workspace_trust` posterior devuelve `trusted True`.
7. `test_set_refuses_unreadable_json` — `.claude.json` con basura no-JSON → `set_workspace_trusted` no lo pisa (`error != None`, archivo intacto).

`backend/tests/test_claude_trust_preflight.py` (monkeypatch de `config` y de `claude_workspace_trust`):
8. `test_preflight_off_skips` — `CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED=False` → `_run_pre_run_checks` no llama a trust (patch de `read_workspace_trust` que aseveraría no-llamada) y retorna True.
9. `test_untrusted_autoset_off_fails_early` — trust `trusted=False`, autoset OFF → `_run_pre_run_checks` retorna **False**, el run queda `error`, el `error_message` contiene "no está confiado" y "hasTrustDialogAccepted".
10. `test_untrusted_autoset_on_proceeds` — trust `trusted=False`, autoset ON → se llama `set_workspace_trusted` (patch) y `_run_pre_run_checks` retorna **True**.
11. `test_trusted_proceeds` — trust `trusted=True` → retorna True sin auto-set.

`backend/tests/test_harness_flags.py` (ya existente; los tests curados deben seguir verdes tras editar `_CURATED_DEFAULTS_ON` y `_CATEGORY_KEYS`):
12. correr `test_default_known_only_for_curated`, `test_declared_default_true_set`, `test_every_registry_flag_is_categorized`.

**Comandos:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_workspace_trust.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_trust_preflight.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_harness_flags.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_harness_flags_requires.py -q
```

**Criterio de aceptación BINARIO:** los 4 comandos verdes. En particular `test_harness_flags.py` no debe reportar drift del patrón triple/OFF, y `test_harness_flags_requires.py` no debe reportar drift del mapa `requires` (prueba de que la arista AUTOSET→PREFLIGHT quedó registrada — C0).

**Flag(s):** `CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED` (default **ON**, kill-switch; **sin excepción dura** — solo detecta y falla accionable, no reduce seguridad). Configurable desde UI (aparece en Runtimes CLI vía `FLAG_REGISTRY`).

**Impacto por runtime + fallback:**
- **Claude Code CLI:** preflight activo. **Fallback:** si `~/.claude.json` es ilegible o el read falla, `read_workspace_trust` devuelve `trusted=False` → con autoset OFF falla temprano accionable (nunca peor que el `code 1` actual).
- **Codex CLI:** **no-op** (el bloque está en `claude_code_cli_runner._run_pre_run_checks`, no en el de Codex `codex_cli_runner.py:1763`). Degradación: Codex usa su propio modelo de sandbox/aprobación; no hay `hasTrustDialogAccepted`. Se documenta y no se toca su `_run_pre_run_checks`.
- **GitHub Copilot:** **no-op** (corre in-process, sin CLI ni `.claude.json`).

**Trabajo del operador:** ninguno en el camino default (preflight solo diagnostica). El remedio manual (aceptar el diálogo de trust) ya era necesario antes; ahora es visible y accionable.

---

### F3 — Auto-set opt-in de `hasTrustDialogAccepted` (cierra D1 opción a; excepción dura (d))

**Objetivo (1 frase).** Permitir que, **por decisión explícita del operador**, el preflight escriba `hasTrustDialogAccepted:true` para el workspace activo, eliminando el bloqueo de trust sin intervención manual en cada instalación nueva.

**Valor.** Cierra D1 de raíz para el operador que lo elija: los runs dejan de morir por trust sin que tenga que abrir `claude` a mano.

**Nota de diseño (excepción dura citada).** El auto-set **modifica un setting de seguridad** de `~/.claude.json` (`hasTrustDialogAccepted`). Eso cae en la **excepción dura (d) "reduce seguridad por default"**. Por eso **NO** es default ON: es opt-in con **default OFF**, activable solo desde la UI. El comportamiento default seguro (F2) es únicamente detectar+fallar-temprano.

**Archivos EXACTOS:** ya cubiertos por F2 (la flag `CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED`, la función `set_workspace_trusted`, y la rama `if config.CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED:` del wiring). F3 **no crea archivos nuevos**; formaliza el comportamiento y su test dedicado de escritura.

**Comportamiento EXACTO cuando AUTOSET=ON y el workspace no está confiado:**
1. `set_workspace_trusted(workspace_root)` hace backup `~/.claude.json.stacky.bak`, crea estructura si falta, setea `projects[key].hasTrustDialogAccepted=true`, persiste con `indent=2`.
2. Loguea `warn` visible en el run (`trust auto-set: workspace confiado automáticamente ...`) — el operador ve que se aplicó.
3. `_run_pre_run_checks` retorna True → el run procede.
4. Si el `~/.claude.json` es ilegible, `set_workspace_trusted` **no lo pisa** (devuelve `error`); el wiring trata `trust.trusted==False` posterior como fallo accionable (no procede a ciegas).

**Tests PRIMERO:** cubiertos por `test_claude_workspace_trust.py::test_set_workspace_trusted_writes_and_backups`, `::test_set_refuses_unreadable_json`, y `test_claude_trust_preflight.py::test_untrusted_autoset_on_proceeds`. Test adicional de idempotencia:
- `test_autoset_idempotent` (en `test_claude_workspace_trust.py`) — llamar `set_workspace_trusted` dos veces deja un solo entry con `hasTrustDialogAccepted True` y no corrompe otros keys de `projects`.

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_workspace_trust.py backend/tests/test_claude_trust_preflight.py -q` (por archivo).

**Criterio de aceptación BINARIO:** tests de escritura/idempotencia verdes; `CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED` aparece en la UI (Runtimes CLI) como toggle OFF por default; con la flag OFF, `set_workspace_trusted` **nunca** se invoca (aseverado por `test_untrusted_autoset_off_fails_early`).

**Flag:** `CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED` (default **OFF**, opt-in). **Excepción dura citada: (d) reduce seguridad por default.** `requires=CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED` (si el preflight está OFF, el auto-set no tiene efecto — solo informativo en la UI). Configurable desde UI (regla dura: valor que el operador configura va por UI, no solo env).

**Impacto por runtime + fallback:** idéntico a F2 (Claude-específico; no-op para Codex/Copilot). **Fallback:** con AUTOSET OFF (default), el sistema se comporta exactamente como F2 (detecta+falla accionable).

**Trabajo del operador:** opt-in (default OFF). Si lo activa, cero trabajo recurrente; si no, ninguno (el default es seguro).

---

### F4 — Enriquecer el evento de stall + superficie UI (cierra D2)

**Objetivo (1 frase).** Que un run terminado por inactividad reporte **la última señal conocida** (último tipo de evento del stream / tool_use) y su correlación con el estado de trust, tanto en el log/metadata como en la UI del detalle de ejecución.

**Valor.** El operador deja de ver "605s sin eventos — terminando" sin contexto; ve "terminado por inactividad (600s) — última señal: tool_use(Read)". Diagnóstico sin repetir el run a ciegas.

**Archivos EXACTOS:**
- **EDITAR** `backend/services/claude_code_cli_runner.py` (tracking de última señal en `_on_stream_event` `:1002-1011`; enriquecer `stall_meta` en `:1617-1621`).
- **EDITAR** `backend/services/codex_cli_runner.py` (enriquecer `stall_meta` en `:710-718`, limpiar ternario muerto `if False` de `:715` — paridad, C3).
- **CREAR** `frontend/src/utils/stallReason.ts`.
- **CREAR** `frontend/src/utils/__tests__/stallReason.test.ts`.
- **EDITAR** `frontend/src/components/ExecutionDetailDrawer.tsx` (mostrar la razón de stall si `metadata.stall` presente).
- **EDITAR (condicional, C4)** `backend/api/executions.py` (serializer de `get_execution`) **solo si** no expone ya `metadata` con el sub-dict `stall` (verificar con grep antes).
- **CREAR** `backend/tests/test_claude_stall_signal.py`.
- **CREAR** `backend/tests/test_execution_metadata_serialization.py`.

**Backend — tracking de última señal en Claude (`_on_stream_event`, `:1002`):** agregar una lista mutable junto a `_last_event_wall`/`_last_event_mono` (`:991-993`):
```python
        _last_event_kind: list[str] = ["none"]  # último tipo de señal del stream
```
Dentro de `_on_stream_event`, tras actualizar los timestamps:
```python
        etype = event.get("type") or "unknown"
        if etype == "assistant":
            _last_event_kind[0] = "assistant_text"
        elif etype == "tool_use" or event.get("name"):
            _last_event_kind[0] = f"tool_use:{event.get('name') or '?'}"
        else:
            _last_event_kind[0] = etype
```
En el bloque `failed_stall` (`:1617-1621`), enriquecer `stall_meta`. **C1 (fix de coupling):** el `trust_ok` NO puede leerse de `metadata.get("trust")` — el `metadata` local del streaming (`:1350`) nunca recibe la key `"trust"` (el preflight F2 la escribe en `row.metadata_dict`, otra función/scope, vía `_run_pre_run_checks`). Hay que leer el trust **persistido** desde la fila, con fallback a una lectura on-demand (que es donde el dato tiene valor diagnóstico real: el caso preflight OFF en el que el CLI cuelga en el diálogo de trust en vez de salir `code 1`):
```python
            # C1 — trust persistido por el preflight (F2) o lectura on-demand si preflight estaba OFF.
            trust_ok: bool | None = None
            try:
                with session_scope() as _s:
                    _row = _s.get(AgentExecution, execution_id)
                    _persisted = (_row.metadata_dict.get("trust") if _row else None) or {}
                if "trusted" in _persisted:
                    trust_ok = bool(_persisted["trusted"])
                elif workspace_root:  # preflight OFF: diagnosticar el cuelgue de trust ahora
                    from services import claude_workspace_trust as _cwt
                    trust_ok = _cwt.read_workspace_trust(str(cwd)).trusted
            except Exception:  # noqa: BLE001 — diagnóstico best-effort, nunca romper el cierre del run
                trust_ok = None
            stall_meta = {
                "detected_at": datetime.utcnow().isoformat(),
                "last_event_at": _last_event_wall[0].isoformat(),
                "last_signal": _last_event_kind[0],
                "seconds_idle": round(time.monotonic() - _last_event_mono[0]),
                "watchdog_seconds": stall_watchdog_sec,
                "trust_ok": trust_ok,  # True/False si se conoce; None si indeterminado.
            }
            metadata["stall"] = stall_meta
```
(Nota semántica: con preflight ON, todo run que llega al watchdog **ya pasó** el trust — el preflight bloquea los no-confiados antes del streaming (`_run_pre_run_checks` retorna False en `:545`) — así que `trust_ok` será `True`. El campo solo agrega señal cuando el preflight está OFF; por eso la lectura on-demand. `None` = indeterminado, no "no confiado".)

Y el `log("error", ...)` del stall (`:1628`) pasa a incluir la señal:
```python
            log("error", f"run terminado por inactividad ({stall_watchdog_sec}s) — última señal: {_last_event_kind[0]}")
```
**Codex (paridad, `:710-718`) — mapeo EXACTO (C3), para no dejar ambigüedad a modelos menores.** El `stall_meta` de codex hoy tiene solo `{detected_at, last_event_at}` y arrastra un ternario muerto `... if False else ...` en `:715` (limpiarlo al tocar el bloque). Codex NO tipa eventos (solo `_codex_last_event_mono`, un timestamp) ni tiene concepto de trust. Escribir las **mismas 6 keys** con estos valores exactos:
```python
            stall_meta = {
                "detected_at": datetime.utcnow().isoformat(),
                "last_event_at": datetime.utcnow().isoformat(),
                "last_signal": "stream_line" if _codex_last_event_mono[0] != _codex_started_mono else "none",
                "seconds_idle": round(_time.monotonic() - _codex_last_event_mono[0]),
                "watchdog_seconds": _codex_stall_watchdog_sec,
                "trust_ok": True,  # n/a en Codex (sin ~/.claude.json); True fijo documentado para paridad de esquema.
            }
            metadata["stall"] = stall_meta
```
(Si `_codex_started_mono` no existe como símbolo, usar el `_time.monotonic()` capturado al inicio del run; el objetivo es solo distinguir "hubo alguna señal" de "ninguna". El objetivo global es que ambos runners escriban el **mismo conjunto de keys** `metadata["stall"]` — verificado por `test_stall_schema_parity` en F5.)

**Frontend — helper puro (`frontend/src/utils/stallReason.ts`):**
```ts
export interface StallMeta {
  detected_at?: string;
  last_event_at?: string;
  last_signal?: string;
  seconds_idle?: number;
  watchdog_seconds?: number;
  trust_ok?: boolean;
}

export function formatStallReason(stall: StallMeta | null | undefined): string | null {
  if (!stall) return null;
  const secs = stall.watchdog_seconds ?? stall.seconds_idle;
  const base = secs != null
    ? `Run terminado por inactividad (${secs}s sin eventos del stream).`
    : "Run terminado por inactividad del stream.";
  const signal = stall.last_signal && stall.last_signal !== "none"
    ? ` Última señal: ${stall.last_signal}.`
    : " Sin señales previas del agente.";
  const trust = stall.trust_ok === false
    ? " Posible causa: workspace no confiado (ver preflight de trust)."
    : "";
  return base + signal + trust;
}
```
**Wiring en `ExecutionDetailDrawer.tsx`:** leer `execution.metadata?.stall` (tipo `Record<string, unknown>`, ya existe `metadata?` en el tipo de ejecución, `endpoints.ts:2032`), pasar a `formatStallReason`, y si devuelve string, renderizar un bloque de aviso (reusar el estilo de error existente del drawer). Cambio mínimo, sin lógica nueva de red.

**C4 — verificar el contrato de serialización ANTES de cablear la UI (paso obligatorio).** El drawer asume `execution.metadata.stall`, pero el backend persiste el stall en `AgentExecution.metadata_dict` (columna `metadata_json`). Hay que confirmar que el endpoint GET de ejecución expone ese campo como `metadata` (no como `metadata_json` u omitido). Verificación literal: `grep -nE '"metadata"|metadata_dict|metadata_json' backend/api/executions.py` y localizar el serializer de `get_execution`. Si el serializer NO incluye `metadata` (o el sub-dict `stall`), **agregarlo** (aditivo) — sin eso, el drawer nunca vería la razón del stall. **Test backend obligatorio:** `backend/tests/test_execution_metadata_serialization.py::test_get_execution_exposes_stall` — sembrar un `AgentExecution` con `metadata_dict={"stall": {...6 keys...}}`, pegarle al endpoint (o al serializer) y aseverar que la respuesta contiene `metadata["stall"]` con las 6 keys. Binario: pasa/falla.

**Tests PRIMERO:**

`frontend/src/utils/__tests__/stallReason.test.ts` (vitest puro, sin RTL — respeta el gap estructural jsdom/RTL del repo):
1. `null/undefined → null`.
2. stall con `watchdog_seconds:600, last_signal:"tool_use:Read"` → contiene "600s" y "tool_use:Read".
3. stall con `last_signal:"none"` → contiene "Sin señales previas".
4. stall con `trust_ok:false` → contiene "workspace no confiado".

`backend/tests/test_claude_stall_signal.py` (unit del esquema + correlación de trust, sin spawnear el CLI):
5. `test_stall_meta_has_six_keys` — construir un `stall_meta` como en el runner y aseverar las claves exactas `{detected_at,last_event_at,last_signal,seconds_idle,watchdog_seconds,trust_ok}`.
6. **C1 `test_trust_ok_from_persisted_untrusted`** — sembrar un `AgentExecution` con `metadata_dict={"trust":{"trusted":False,...}}`, ejecutar la lógica de derivación de `trust_ok` (extraerla a un helper puro `_derive_stall_trust_ok(execution_id, cwd)` en el runner para poder testearla sin stream) y aseverar `trust_ok is False`.
7. **C1 `test_trust_ok_indeterminate_is_none`** — sin key `trust` persistida y sin `workspace_root` → `trust_ok is None` (indeterminado, NO `False`).

`backend/tests/test_execution_metadata_serialization.py` (C4): `test_get_execution_exposes_stall` — descrito arriba en el wiring UI.

**Comandos:**
```
frontend/node_modules/.bin/vitest run frontend/src/utils/__tests__/stallReason.test.ts
frontend/node_modules/.bin/tsc --noEmit
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_stall_signal.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_execution_metadata_serialization.py -q
```

**Criterio de aceptación BINARIO:** vitest del helper verde, `tsc --noEmit` sin errores nuevos, pytest del esquema/correlación verde, y el test de serialización confirma `metadata.stall` en la respuesta del endpoint.

**Flag:** ninguna. **Justificación:** enriquecimiento aditivo de un `metadata`/log ya existente y de un render condicional; no cambia comportamiento de ejecución, es backward-compatible (si `metadata.stall` no tiene los campos nuevos, el helper degrada).

**Impacto por runtime + fallback:** Claude y Codex escriben el mismo esquema `metadata["stall"]`. Copilot no tiene watchdog de stream → no produce `metadata.stall` → el drawer no muestra el bloque (sin regresión). **Fallback:** si faltan campos, `formatStallReason` usa los que haya.

**Trabajo del operador:** ninguno.

---

### F5 — Paridad de runtimes + verificación integral

**Objetivo (1 frase).** Dejar constancia ejecutable de que D3/D4 aplican idénticos a los 3 runtimes y que D1/D2 (Claude-específicos) degradan de forma controlada en Codex/Copilot, y correr la verificación final.

**Valor.** Evita regresiones de paridad y cumple el riel duro #1.

**Archivos EXACTOS:**
- **CREAR** `backend/tests/test_plan144_parity.py`.
- (Revisión, sin editar salvo que falle) `backend/services/codex_cli_runner.py` — confirmar que su stall (`:726-728`) y runaway (`:759-761`) transicionan vía `ticket_status.on_execution_end` (ya lo hacen; heredan F0+F1).

**Tests (`test_plan144_parity.py`), casos EXACTOS:**
1. `test_codex_runaway_needs_review_transitions` — sembrar ticket `running`, simular `on_execution_end(final_status="needs_review", agent_type="developer")` (la ruta que Codex usa en runaway) → `get_current_status == "needs_review"`, sin excepción. (Prueba que el fix D4 cubre Codex.)
2. `test_trust_preflight_is_claude_only` — aseverar que `codex_cli_runner` **no** importa ni referencia `claude_workspace_trust` (grep en el fuente del módulo: `assert "claude_workspace_trust" not in inspect.getsource(codex_cli_runner)`), documentando el no-op de trust en Codex.
3. `test_stall_schema_parity` — construir `stall_meta` con las claves del esquema para Claude y Codex y aseverar el **mismo** conjunto de claves.

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan144_parity.py -q`

**Verificación final integral (la corre el implementador y pega el output real — cero falsos verdes):**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_status_vocabulary_contract.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_status_robust_transition.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_workspace_trust.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_trust_preflight.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_claude_stall_signal.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_execution_metadata_serialization.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan144_parity.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_harness_flags.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_harness_flags_requires.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_stale_recovery_guardian.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_cutover_p5.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_b6_cancel_sync.py -q
frontend/node_modules/.bin/vitest run frontend/src/utils/__tests__/stallReason.test.ts
frontend/node_modules/.bin/tsc --noEmit
```

**Criterio de aceptación BINARIO:** todos verdes, corridos **por archivo**. Ningún test preexistente citado (harness_flags, harness_flags_requires, stale_recovery, cutover_p5, b6_cancel) regresa rojo.

**Flag:** ninguna (fase de verificación).

**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | El key real que usa el CLI en `projects` no coincide con `_normalize_project_key` (mayúsculas de unidad, ruta UNC, symlink). [INF] sobre el keying exacto del CLI. | Media | Preflight marca "no confiado" un workspace que sí lo está → falla temprano de más. | El fallo es **accionable, no mudo** (mejor que el `code 1` actual). `read_workspace_trust` es puro y testeable; si aparece un caso real distinto, se ajusta la normalización con un test. AUTOSET (opt-in) resuelve el caso escribiendo el key normalizado que sí usará el preflight. |
| R2 | `set_workspace_trusted` corrompe un `~/.claude.json` grande/compartido con otras herramientas. | Baja | Config de Claude del operador dañada. | Backup previo `~/.claude.json.stacky.bak`; **no** se pisa un JSON ilegible (se aborta con `error`); `indent=2` preserva legibilidad; solo se toca `projects[key].hasTrustDialogAccepted` (merge, no reemplazo). Opt-in default OFF. |
| R3 | Coerción defensiva `_coerce_terminal_status` enmascara un bug real (estado válido nuevo tratado como error). | Baja | Un estado terminal legítimo futuro caería a `error`. | Logea `warning` explícito con el estado desconocido; el vocabulario canónico vive en un solo módulo (F0), así que agregar un estado nuevo es un cambio de una línea + test. |
| R4 | El preflight agrega latencia al arranque del run. | Muy baja | +ms por run. | Es una lectura de un JSON local pequeño, una vez, antes del spawn. Despreciable frente al costo del turno. Kill-switch `CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED=false` disponible. |
| R5 | Sesión concurrente en el árbol movió `ticket_status.py`/`agent_completion.py` mientras se implementa (hay actividad multiagente confirmada en esta rama). | Media | Merge/anchors desalineados. | Los cambios son quirúrgicos y por símbolo (no por línea). Re-verificar `VALID_STATUSES`/`TERMINAL_STATUSES` con grep antes de editar. `git add` con paths explícitos. |
| R6 | Trust no persistido/indeterminado al construir `stall_meta` (run sin `workspace_root`, o preflight OFF). | Baja | `trust_ok` no concluyente. | **Corregido en v2 (C1):** `trust_ok` se deriva del trust **persistido** (`row.metadata_dict`), con fallback a lectura on-demand cuando el preflight estaba OFF; si sigue indeterminado → `None` (NO `False`, no marca falsamente "no confiado"). Con preflight ON, todo stall que llega al watchdog ya está confiado → `True`. |
| R7 | **Cross-plan 147 (V2 repo_root/workspace_root):** si 147 cambia la resolución de raíz/cwd después de este plan, el key de trust puede driftear y reintroducir falsos "no confiado". | Media | Preflight marca no-confiado un workspace que sí lo está. | El keying de trust normaliza vía `Path(...).resolve()` sobre el mismo `workspace_root`/`cwd` que `_resolve_cwd` (`claude_code_cli_runner.py:2627`) produce. **Regla de orden:** si 147 aterriza, re-verificar que `_normalize_project_key` y `_resolve_cwd` sigan resolviendo el mismo path. AUTOSET (opt-in) escribe exactamente el key que el preflight leerá, cerrando el drift para quien lo active. |
| R8 | **Backward-compat UI (C8):** agregar `needs_review` al vocabulario de `stacky_status` podría sorprender a un `switch`/enum del frontend que renderiza el estado (sin label/color → estado en blanco). | Baja | Celda de estado sin etiqueta para `needs_review`. | Antes de cerrar F0, `grep -rnE "stacky_status|needs_review" frontend/src` para ubicar el enum/labels; garantizar que `needs_review` tenga label y color. La columna DB es `String` libre (`models.py`), sin constraint que rompa. Cambio de UI mínimo si falta. |

---

## 6. Fuera de scope (explícito)

- **404 masivo de `/api/v1/pipeline/status`, strip ANSI, aislar logging de pytest, dedup de warnings de preflight** → **Plan 145**. (Este plan no toca el FileHandler ni el logging de tests.)
- **Fix de import `Execution`→`AgentExecution` (V1), `mkdir` del SQLite ledger (V5), re-deploy con `CLAUDE_CODE_CLI_MODEL_FALLBACK` (V4)** → **Plan 146**. (V4 ya está en el working tree, `config.py:216-217`; su re-publicación es de 146.)
- **Resolución robusta de `outputs_dir`/`repo_root` (V2) y estado UI de watchers inactivos (D8)** → **Plan 147**.
- **Degradación de PAT ADO/Jira/LLM local + 502 (V3/V8/D6/D9)** → **Plan 148**.
- **`pending-task.json` inválido (D5) + excepciones tipadas en endpoints (V6)** → **Plan 149**.
- **Acortar el timeout del reaper (120 min):** se **conserva** como red de seguridad; no se modifica en este plan (F0+F1 evitan que sea el camino primario).
- **Cambiar el vocabulario de `AgentExecution.status`** (columna libre `String`, `models.py:60`) o `ACTIVE_STATUSES`: fuera de scope; F0 solo unifica el vocabulario **de ticket** y el **terminal de completion**.

---

## 7. Glosario, orden de implementación y DoD

### Glosario (términos Stacky usados)
- **Trust de workspace:** flag `hasTrustDialogAccepted` en `~/.claude.json` que el binario `claude` exige por proyecto; sin ella el CLI ignora permisos y sale `code 1`. Concepto exclusivo de Claude CLI.
- **Stall watchdog:** lazo en el runner que mata el subproceso del CLI si no hay eventos del stream por `STACKY_STALL_WATCHDOG_SECONDS` (default 600). Existe en Claude (`:1300-1323`) y Codex (`:632-648`).
- **Reaper / stale-recovery:** daemon (`ticket_status.recover_stale_running_tickets` / `schedule_stale_recovery`) que fuerza a `error` ejecuciones colgadas > `EXECUTION_TIMEOUT_MINUTES` (120). Red de seguridad, no camino primario.
- **`on_execution_end`:** hook único (`ticket_status.py:214`) por el que **los 3 runtimes** transicionan el `stacky_status` del ticket al terminar. Punto de paridad.
- **`stacky_status`:** estado interno del ticket (`idle|running|completed|error|cancelled|needs_review` tras F0), distinto de `ado_state`.
- **`needs_review`:** estado terminal que produce el gate de contrato/runaway; hoy rechazado por `set_status` (D4).
- **Patrón triple de flags:** `FlagSpec(default=True)` + key en `_CURATED_DEFAULTS_ON` + `config.py "true"`. Obligatorio para default ON.

### Orden de implementación (numerado)
1. **F0** — `status_vocabulary.py` + rewire `ticket_status`/`agent_completion` + `test_status_vocabulary_contract.py`. (Desbloquea D3.)
2. **F1** — `_coerce_terminal_status` + uso en `on_execution_end` + `test_ticket_status_robust_transition.py`.
3. **F2** — `claude_workspace_trust.py` + wiring preflight + flags (patrón triple para PREFLIGHT, OFF para AUTOSET) + `config.py` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` + **`_REQUIRES_MAP_FROZEN` (arista AUTOSET→PREFLIGHT, C0)** + `test_claude_workspace_trust.py` + `test_claude_trust_preflight.py`.
4. **F3** — formalizar auto-set (ya cableado en F2) + tests de escritura/idempotencia. Excepción dura (d) citada.
5. **F4** — enriquecer `stall_meta` (Claude + Codex) + `stallReason.ts` + wiring en `ExecutionDetailDrawer.tsx` + tests (vitest + tsc + pytest esquema).
6. **F5** — `test_plan144_parity.py` + verificación integral (correr TODOS los comandos por archivo, pegar output real).

### Definición de Hecho (DoD) global
- [ ] `TERMINAL_STATUSES ⊆ VALID_TICKET_STATUSES` garantizado por test; `set_status(tid,"needs_review")` no lanza. (D4)
- [ ] Un fin de run con `needs_review` transiciona el ticket inmediatamente; un estado desconocido cae a `error`, nunca deja `running`. (D3)
- [ ] Un run sobre workspace no confiado, con AUTOSET OFF, **no** muere con `code 1` mudo: queda `error` con remedio exacto en `error_message`. (D1)
- [ ] Con AUTOSET ON (opt-in), el workspace se confía automáticamente (con backup) y el run procede. Excepción dura (d) citada. (D1)
- [ ] `CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED` (ON) y `CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED` (OFF) aparecen en la UI (Runtimes CLI); `test_harness_flags.py` no reporta drift del patrón triple **y** `test_harness_flags_requires.py` no reporta drift del mapa `requires` (arista AUTOSET→PREFLIGHT registrada, C0).
- [ ] Todo stall reporta `last_signal` + `trust_ok` en `metadata["stall"]` y en el log; el drawer muestra la razón humana. Claude y Codex comparten esquema. (D2)
- [ ] Paridad documentada y testeada: D3/D4 aplican a los 3 runtimes; trust es no-op en Codex/Copilot.
- [ ] Todos los comandos de la verificación integral (§F5) verdes, corridos por archivo, con output real pegado.
- [ ] Cero pasos manuales nuevos en el camino default; auto-set opt-in default OFF; backward-compatible.
