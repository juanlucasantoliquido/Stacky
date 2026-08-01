# Plan 278 — La épica se publica en los 3 runtimes, con UN SOLO publicador

**Estado:** v2 (MEJORADO tras crítica adversarial)
**Versión:** v1 -> v2
**Rama:** `docs/plan-278`
**Origen:** defecto reportado en vivo por el operador (2026-08-01).
**Juez v2: subagente independiente, misma corrida, contexto limpio**

---

## 0. CHANGELOG v1 -> v2

Veredicto de la crítica sobre v1: **RECHAZADO** (9 BLOQUEANTES). Todos resueltos acá.

| C# | Sev | Qué estaba mal en v1 | Cómo se resolvió en v2 |
|----|-----|----------------------|------------------------|
| C1 | BLOQ | F3 mandaba borrar `claude_code_cli_runner.py:1675-1751`. El closure **termina en `:1746`**; `:1749` es `if _runaway_triggered:`. Borrar hasta `:1751` **elimina el `if`** y deja huérfano el bloque `1753-1787` → `IndentationError` o camino runaway ejecutándose incondicionalmente. | F3 reescrita con los **3 rangos exactos y disjuntos**, con el texto literal de la primera y última línea de cada uno + un gate de sintaxis (`compileall`). |
| C2 | BLOQ | El censo AST contaba *"llamadas a `autopublish_epic_from_run`"*. La invocación real es por **alias** (`_publish` en `:1703`/`:1715`), y el pseudocódigo de F1 repetía el alias ⇒ el censo daba **conjunto vacío antes y después**: F0 caso 1 y F3 fallaban ambos. | Censo por **REFERENCIA** (`ast.Name` / `ast.ImportFrom` / `ast.Attribute`), con el código completo, el scope exacto y las exclusiones (`api.tickets` es el módulo que los DEFINE). Verificado contra el repo: hoy da exactamente `{"services.claude_code_cli_runner"}`. |
| C3 | BLOQ | La degradación por `set_status` toca el **ticket**, no la fila. Hoy la degradación entra por `_mark_terminal` (`:1936`→`:1967`) y arrastra `AgentExecution.status`, `failure_kind`, manifest, evento en disco, `_notify_outcome` y el gate de `post_run_memory`. v1 prometía "byte-idéntico" y no lo era. | F2 ahora degrada **las dos capas** (fila + ticket) con `_degrade_execution_row`, replicando `failure_kind`; §3 corregido y test 13 congela la fila. |
| C4 | BLOQ | Ventana real de **doble publicación**: `on_execution_end` puede dispararse ≥2 veces para la misma ejecución desde hilos distintos (gateway `agent_completion.py:1230` + runner `:2002`). El sello `md.get(seal_key)` es read-modify-write sin atomicidad. | **`[ADICIÓN ARQUITECTO] A1`** — nueva fase **F2-bis**: claim atómico de una sola sentencia SQL con `rowcount`, que convierte "como mucho una publicación" en invariante demostrable. |
| C5 | BLOQ | `set_status(ticket_id, "needs_review", ...)`: los puntos suspensivos ocultaban `changed_by`, que es **keyword-only obligatorio** (`ticket_status.py:147`). `TypeError` garantizado en un modelo menor. | Firma literal completa en F2, incluido `guard_downgrade=False` explícito con la razón. |
| C6 | IMPO | El discriminador se declaraba "equivalente" al `_one_shot and business` sin prueba. | §F1 declara la **diferencia medida** (sub-disparo en `ado_id ∈ {-7,-8,-9}`), la justifica y la congela con el test 2-bis. |
| C7 | BLOQ | El contrato de F2 omitía `epic_baseline_html` / `epic_baseline_rev` (`:1740-1745`, Plan 60 F1) ⇒ regresión silenciosa del aprendizaje bidireccional. | Tabla de contrato ampliada a 9 filas + test 11-bis. |
| C8 | BLOQ | `run_started_at` pasaba de `spawn_epoch` (`:1032`) a `started_at` de la fila: **amplía hacia atrás** la ventana anti-stale del rescate desde disco (`api/tickets.py:7300`) y, con `datetime.utcnow()` naive, `.timestamp()` lo interpreta como hora **local** (desfase de horas en Windows). | F1 fija `spawn_epoch_from_metadata` con fallback UTC-explícito, y F1-bis obliga al runner a sellar `spawn_epoch` en metadata. Test 7 reescrito. |
| C9 | BLOQ | Orden de registro del post-hook sin especificar; los hooks posteriores (`completion_dispatcher`, `qa_uat_enqueue`) reciben el `final_status` **pre-degradación** y ya sincronizaron el tracker. | F4 fija la línea exacta (`app.py:993`, **antes** de `incident_autopublish`) y F2 degrada la fila **antes** de que corran los demás; documentado como limitación conocida en R9. |
| C10 | IMPO | `mock_run_agent.assert_called_once()` en F4 sin evidencia de que el happy path sobreviva a los mocks. | F4 da el procedimiento exacto (extender `_patch_deps`, **nunca** debilitar el assert) y el assert mínimo irrenunciable. |
| C11 | IMPO | `test_speculative_parity.py:93-111` desfasado (es `:92-111`) y la "actualización" sin literales. | Corregido, con los literales exactos, y se suma `test_speculative_claim_flow.py:180` que v1 ignoraba. |
| C12 | IMPO | F6 no tocaba el mapa de categorías de `harness_flags.py` (`:400-420`). | F6 nombra la categoría destino y la línea exacta. |
| C13 | IMPO | F6 sin archivo de test ni comando. | Archivo + comando exactos. |
| C14 | IMPO | F0 caso 2 leía `_POST_HOOKS` sin `create_app()` ⇒ lista vacía ⇒ la propia guarda anti-falso-verde lo hacía fallar. | F0 exige `create_app()` primero, con el patrón ya usado en `test_run_brief_autopublish_parity.py:20-24`. |
| C15 | IMPO | F5 no fijaba `DATABASE_URL` ⇒ un pytest suelto escribe en la **base viva del operador**. | Cabecera obligatoria `sqlite:///:memory:` en los 2 tests nuevos. |
| C16 | IMPO | 8 frases vagas inventariadas ("aprox., re-verificar al implementar", "mismo bloque", "el meta-test que ya existe", "espejo exacto", "el resto no se toca"…). | Todas reemplazadas por literales. |
| C17 | BLOQ | **Contradicción entre criterios**: F4 obliga a escribir `"autopublish_requires_claude_cli"` en los asserts invertidos, y el DoD exige `grep ... = 0` en `backend/`. Mutuamente insatisfacibles ⇒ un modelo menor borra el assert. | El criterio pasa a ser: **0 ocurrencias fuera de `backend/tests/`**, con el comando exacto. |
| C18 | IMPO | R8 afirmaba "sin cambio de perfil". Falso para el camino gateway: ahí el hook corre **dentro de un request HTTP de Flask**. | R8 reescrito y acotado. |
| C19 | IMPO | Sin rollback operativo: con la flag OFF y el gate 400 borrado, un `run_brief` con Copilot termina `completed` **sin épica y sin error** — el falso verde que el Plan 52 F0 quería evitar, ahora en los 3 runtimes. | **`[ADICIÓN ARQUITECTO] A2`** — F4-bis: el 400 no desaparece, se **reemplaza** por `autopublish_disabled` cuando la flag está OFF. |
| C20 | IMPO | F7 no decía **cómo** se registra un test en cada ratchet (sintaxis distinta) y su lista de no-regresión omitía 2 archivos. | Líneas literales para `.sh` y `.ps1` + lista ampliada a 12 archivos. |
| C21 | MENOR | "Paridad de mecanismo, no de calidad" no era medible. | **`[ADICIÓN ARQUITECTO] A3`** — F6-bis: sello `epic_publish` con runtime/intento/desenlace, visible en la UI. |
| C22 | BLOQ | **Anclaje INEXISTENTE**: el KPI K4 y F6 citaban `test_harness_flags_registry.py`. Ese archivo **no existe** en `backend/tests/` (los que existen son `test_harness_flags.py`, `_bounds`, `_endpoint_restart`, `_help`, `_op_health`, `_requires`, `_restart_required`, `_undo`). El KPI K4 no se podía verificar. | K4 y F6 apuntan a `tests/test_harness_flags.py::test_every_registry_flag_is_categorized` (`:988`), que es el gate real declarado en `services/harness_flags.py:551-552`. |

---

## 1. Objetivo y KPI

Hoy **solo `claude_code_cli` puede crear una épica desde un brief**. Con GitHub Copilot Pro o Codex CLI
el backend responde 400 antes de arrancar:

```
400 BAD REQUEST
{"detail":"work_item_type='Epic' requiere runtime 'claude_code_cli'; recibido 'github_copilot'",
 "error":"autopublish_requires_claude_cli","ok":false}
```

Este plan mueve la autopublicación de Epic/Issue desde el finalizador del runner de Claude al
**chokepoint runtime-agnóstico que ya existe y ya está vivo en los 3 runtimes**
(`ticket_status.on_execution_end` → post-hooks), dejando **un solo publicador** en todo el backend, y
reemplaza el gate que rechazaba.

**KPI binarios:**

| # | KPI | Cómo se mide |
|---|-----|--------------|
| K1 | `POST /api/agents/run-brief` con `work_item_type=Epic` y runtime `github_copilot` o `codex_cli` **no devuelve `autopublish_requires_claude_cli`** | `test_run_brief_autopublish_parity.py` invertido (F4) |
| K2 | **Exactamente 1** módulo de producción REFERENCIA `autopublish_epic_from_run` / `publish_issue_from_run` en todo `backend/`, sin contar el módulo que los define | censo por **AST de referencias** (F0/F3), no por grep ni por `ast.Call` |
| K3 | Los 3 runtimes publican por el **mismo** camino de código | `test_epic_autopublish_runtime_parity.py` parametrizado por runtime (F5) |
| K4 | La flag que gobierna el autopublish es **visible, categorizada y configurable desde la UI** | `tests/test_harness_flags.py::test_every_registry_flag_is_categorized` (`:988`) (F6) |
| K5 | **A lo sumo UNA** publicación por ejecución, aun con dos `on_execution_end` concurrentes | claim atómico con `rowcount` (F2-bis) |

**Paridad declarada honestamente:** este plan entrega **paridad de MECANISMO**, no de calidad. Si el
modelo de Copilot o Codex devuelve narración en vez del HTML de la épica, el publicador ya falla
RUIDOSO con `epic_not_in_output` → `needs_review` (`api/tickets.py:7310-7318`, verificado). Eso es
correcto y estrictamente mejor que el 400 de hoy, pero **el plan no promete que los 3 modelos
produzcan épicas de la misma calidad**. Prohibido escribir en el doc o en un test que la calidad es
equivalente. La **medición** de esa diferencia es lo que agrega F6-bis.

---

## 2. Por qué ahora / gap que cierra

El gate **no es un bug ni un residuo**: hoy es fácticamente correcto. Verificado abriendo los archivos:

- `autopublish_epic_from_run` (`backend/api/tickets.py:7248`) y `publish_issue_from_run`
  (`backend/api/tickets.py:7695`) tienen **un solo módulo de producción que los referencia en todo el
  backend**: `backend/services/claude_code_cli_runner.py`, dentro del closure `_maybe_autopublish_epic`.
  - **Definición del closure:** `:1675` (`def _maybe_autopublish_epic(current_status: str) -> str:`)
    hasta `:1746` (`return current_status`). `:1747` está en blanco.
  - **Import de los símbolos:** `:1689-1692`. **Alias:** `:1703`
    (`_publish = publish_issue_from_run if _is_issue else autopublish_epic_from_run`).
    **Invocación real:** `:1715` (`_res = _publish(**_publish_kwargs)`).
    > Consecuencia dura: **no existe ninguna `ast.Call` cuyo `func` se llame `autopublish_epic_from_run`.**
    > Cualquier censo por llamada devuelve vacío. Por eso el censo de este plan es por **referencia**.
  - **Invocaciones del closure:** `:1752` (dentro de `if _runaway_triggered:` en `:1749`) y `:1936`.
- Con Copilot o Codex el run correría, gastaría tokens y **no crearía la épica**. El gate cambia ese
  falso verde por un 400 legible antes de gastar. Fue una decisión deliberada del Plan 52 F0.

Lo que cambió es que **el operador exige la paridad real**, y el sustrato para darla ya está construido:

1. **El publicador ya es runtime-agnóstico.** `autopublish_epic_from_run` recibe
   `output / brief / project_name / already_published_id / run_started_at` (firma en
   `api/tickets.py:7248-7254`) y parsea con `_extract_epic_html` + `_looks_like_epic`. Nada adentro
   depende del runtime.
2. **El chokepoint ya existe y ya está vivo en los 3.** `ticket_status.on_execution_end`
   (`backend/services/ticket_status.py:293`) corre `_run_post_hooks` (llamado en `:349`, definido en
   `:395-400`); el registro es `register_post_hook` (`:377`). Lo llaman Claude
   (`claude_code_cli_runner.py:2002`), Codex (`codex_cli_runner.py:1130-1133`) y Copilot in-proc
   (`agent_runner.py:1037-1043`). **Los 3 anclajes verificados.**
3. **Existe el precedente exacto a copiar.** `backend/services/incident_autopublish.py` (53 líneas,
   verificado) es un autopublish agnóstico de runtime implementado como post-hook, registrado en
   `app.py:994`.
4. **El hueco está admitido por escrito en el código.** `backend/agent_runner.py:176-180`:
   *"La autopublicación de Issue vive en el finalizador del runner CLI; este path (github_copilot) no
   autopublica, pero igual deja la trazabilidad"*.

Además, hoy **la combinación por default está rechazada de fábrica**: el runtime default de `run_brief`
es `github_copilot` (`api/agents.py:640`) y `work_item_type` normaliza a `Epic`, así que el operador
que no toca nada choca contra el 400 (`api/agents.py:654-667`). El propio test lo congela
(`test_run_brief_epic_default_runtime_copilot_returns_400`, `tests/test_run_brief_autopublish_parity.py:88`).

### 2.1 Lo que el post-hook NO cubre (hueco investigado, no supuesto)

Se auditaron **todos** los caminos de cierre de run del backend. Resultado:

| Camino | ¿Llama `on_execution_end`? | ¿Publicaba hoy? | Efecto del cambio |
|---|---|---|---|
| Claude, éxito (`:1936` → `:2002`) | Sí, `:2002` | Sí | Igual (ver F2 por el orden) |
| Claude, runaway (`:1752` → `:1782`) | **Sí, `:1782`**, con `final_status="needs_review"` | Sí | **Cubierto** — R3 de v1 queda RESUELTO, no pendiente |
| Claude, stall (`:1892`) | Sí, `final_status="error"` | No | Igual (el hook corta en no-terminal-bueno) |
| Claude, exit≠0 (`:2071`) / excepción (`:2128`) | Sí, `"error"` | No | Igual |
| Codex (`:1130`, `:1182`, `:871`, `:964`, `:363`) | Sí | No (nunca publicó) | Ahora publica: es el objetivo |
| Copilot in-proc (`agent_runner.py:1037/1063/1090`) | Sí | No | Ahora publica: es el objetivo |
| Cancelación manual (`api/executions.py:746`) | Sí, `"cancelled"` | No | Igual (el hook corta) |
| Gateway de completion (`agent_completion.py:1230`) | Sí, **si no `idempotent_replay`** (`:1184-1188`) | No | **Riesgo de 2º disparo → ver F2-bis** |
| `close_execution_with_publish` (`agent_completion_internal.py:183`) | Sólo **si `not already_terminal`** | No | Igual |
| `output_watcher` modo A/B | Vía `close_execution_with_publish` | No | Igual |
| `recover_stale_running_tickets` (`ticket_status.py:406-470`) | **NO** — escribe `Ticket.stacky_status` y un `TicketStatusEvent` a mano | No | **NO publicará.** Aceptado: ese camino sólo corrige tickets colgados cuya ejecución **ya** estaba terminal; si la ejecución terminó bien, ya pasó por `on_execution_end`. Se documenta como límite conocido (R10). |
| `scripts/rescue_execution.py:497` | Sí (script manual del operador) | No | **Ahora podría publicar** — deseable, y protegido por el claim de F2-bis |
| `services/speculative.py` | **NO** — usa su propia tabla `SpeculativeRun` y `_mark()` (`:182-186`) | No | **No publicará nunca.** Es lo que de verdad blinda el riel del Plan 53; `test_speculative_parity` sigue siendo el centinela de source-text. |

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad.** El publicador único corre en el post-hook, que los 3 disparan. Sin ramas
  `if runtime == ...` en el camino de publicación. Fallback: si el output no es una épica, falla
  ruidoso a `needs_review` — igual en los 3.
- **Cero trabajo extra al operador.** No hay pasos manuales nuevos, ni config nueva obligatoria. Para
  Copilot/Codex, lo que antes era un 400 ahora publica.
- **Equivalencia declarada con precisión (corrige C3 de la crítica).** Para `claude_code_cli` el plan
  garantiza **el mismo estado final observable y la misma metadata sellada**, pero **no** el mismo
  *orden* de escrituras: hoy la degradación por fallo de publicación ocurre **antes** de
  `_mark_terminal` (`claude_code_cli_runner.py:1936` → `:1967`); mañana ocurre **después**, dentro del
  post-hook. Consecuencias que el plan asume y prueba explícitamente:
  - `AgentExecution.status` se degrada igual, pero en una **segunda escritura** (F2 `_degrade_execution_row`).
  - El **manifest en disco** (`_safe_write_manifest`, `:1975`) y el evento (`append_event`, `:1984`)
    quedarán escritos con el estado **pre-degradación**. Se acepta y se declara: son artefactos de
    traza, no la fuente de verdad; la fuente de verdad (fila + ticket) sí queda coherente.
  - `post_run_memory.capture_on_completion` (`:1993`) podrá capturar un draft de una run cuya épica
    falló. Se acepta y se declara (R11).
  Prohibido escribir "byte-idéntico" en el doc o en un test.
- **Human-in-the-loop.** No se agrega autonomía nueva: el autopublish desde brief **ya existía y ya era
  automático** para Claude (excepción dura #1, aceptada por directiva del operador — mismo precedente
  citado en `services/incident_autopublish.py:1-4`). Este plan **no amplía la autonomía**, la vuelve
  uniforme entre runtimes. La decisión de generar la épica la sigue tomando el operador al mandar el
  brief.
- **Mono-operador, sin auth real.** Nada de RBAC.
- **Reusar, no reinventar.** Se reusa `autopublish_epic_from_run` / `publish_issue_from_run` tal cual
  (no se tocan), el patrón de `incident_autopublish`, y la flag existente
  `STACKY_EPIC_AUTOPUBLISH_BACKEND`.
- **Sin falsos verdes.** Cada fase trae un gate que se corre **contra el defecto**. El censo de
  publicadores se hace por **AST de referencias**, nunca por `grep` (que contaría los 3 *strings*
  de `services/harness_flags.py:2783/2797/2906`) ni por `ast.Call` (que devuelve vacío por el alias).

### Flags

| Flag | Default | Nueva | Justificación |
|------|---------|-------|---------------|
| `STACKY_EPIC_AUTOPUBLISH_BACKEND` | **ON** (ya es `true`, `config.py:1054-1055`, verificado) | NO — ya existe | Se **reusa**. No cambia de default. F6 solo la **registra** en el arnés para que sea visible/configurable desde la UI (verificado: **0 ocurrencias** en `services/harness_flags.py`). |
| `STACKY_ISSUE_FROM_BRIEF_ENABLED` | sin cambios | NO | Se reusa tal cual; sigue gobernando la bifurcación Issue. |

**Este plan no crea ninguna flag nueva.** No hay, por lo tanto, ninguna flag que deba nacer OFF ni
excepción (A)/(B) que citar. La capacidad que escribe en el sistema real del operador —el autopublish—
**ya estaba encendida por default antes de este plan**; el plan no la enciende, la unifica.

**Semántica de la flag OFF (corrige C19).** Antes de este plan, con la flag OFF el gate 400 seguía
rechazando Copilot/Codex, así que nunca había una run que terminara `completed` sin épica por culpa de
la flag. Al borrar el gate, la flag OFF crearía exactamente ese falso verde en los 3 runtimes. Por eso
F4-bis reemplaza el 400 en vez de borrarlo: con la flag OFF, `run_brief` con `work_item_type ∈
{Epic, Issue}` devuelve `autopublish_disabled` (400). El rollback por flag sigue siendo real y sigue
siendo ruidoso.

---

## 4. Fases

### F0 — Gate contra el defecto: probar que HOY Copilot y Codex no publican

**Objetivo:** dejar tomada, antes de tocar nada, la foto del estado actual.

**Archivo a crear:** `Stacky Agents/backend/tests/test_epic_autopublish_runtime_parity.py`

**Cabecera obligatoria del archivo** (corrige C15 — sin esto un pytest suelto escribe en la base viva
del operador):

```python
"""Plan 278 F0/F3/F5 — un solo publicador, tres runtimes."""
from __future__ import annotations

import ast
import os
import pathlib
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BACKEND = pathlib.Path(__file__).resolve().parents[1]
TARGETS = {"autopublish_epic_from_run", "publish_issue_from_run"}
# Directorios excluidos del censo: no son codigo de produccion del backend.
SKIP_PARTS = {"tests", "venv", ".venv", "__pycache__", "evals", "harness", "scripts", "node_modules"}
# api.tickets DEFINE los simbolos: no es un llamador.
SKIP_MODULES = {"api.tickets"}
```

**Helper del censo (código completo, no pseudocódigo) — corrige C2:**

```python
def publishing_modules() -> set[str]:
    """Modulos de PRODUCCION que REFERENCIAN el publicador.

    Se cuenta por REFERENCIA (ast.ImportFrom + ast.Name + ast.Attribute), NO por
    ast.Call: hoy la invocacion real pasa por un ALIAS
    (claude_code_cli_runner.py:1703 `_publish = publish_issue_from_run if ...`,
    llamado en :1715), y el servicio nuevo hace lo mismo. Un censo por ast.Call
    devuelve el conjunto VACIO en los DOS lados del cambio y no prueba nada.
    Tampoco sirve grep: services/harness_flags.py:2783/2797/2906 nombran los
    simbolos dentro de STRINGS de documentacion.
    """
    found: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND)
        if SKIP_PARTS & set(rel.parts):
            continue
        module = ".".join(rel.with_suffix("").parts)
        if module in SKIP_MODULES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            hit = (
                (isinstance(node, ast.ImportFrom)
                 and any(alias.name in TARGETS for alias in node.names))
                or (isinstance(node, ast.Name) and node.id in TARGETS)
                or (isinstance(node, ast.Attribute) and node.attr in TARGETS)
            )
            if hit:
                found.add(module)
                break
    return found
```

**Casos:**

1. `test_hoy_solo_claude_tiene_publicador`
   ```python
   def test_hoy_solo_claude_tiene_publicador():
       assert publishing_modules() == {"services.claude_code_cli_runner"}
   ```
   **Verificado contra el repo al escribir este plan**: ese es el resultado exacto hoy.
   Este caso **se reemplaza en F3** por `test_un_solo_publicador_por_ast` (no se deja convivir con su
   inverso: ver la nota de inversión más abajo). Es el KPI K2.

2. `test_post_hook_de_epica_no_esta_registrado` — assert de AUSENCIA **con guarda**:
   ```python
   def test_post_hook_de_epica_no_esta_registrado():
       from app import create_app          # OBLIGATORIO: _POST_HOOKS se puebla en create_app
       create_app()                        # (app.py:993-1011). Sin esto la lista esta VACIA
       from services import ticket_status  # y el assert de ausencia pasa por accidente.
       assert ticket_status._POST_HOOKS, "guarda anti-falso-verde: la lista no puede estar vacia"
       nombres = {getattr(h, "__name__", "") for h in ticket_status._POST_HOOKS}
       assert "maybe_autopublish_epic" not in nombres
   ```

> **Nota anti-falso-verde (gotcha de la casa):** un assert de ausencia no distingue *"no está porque lo
> sacamos bien"* de *"nunca estuvo / el registro no corrió"*. Por eso el caso 2 exige primero que la
> lista tenga contenido, y por eso llama `create_app()`.

> **Regla de inversión (corrige la ambigüedad de v1 señalada en el cruce de criterios):** el caso 1 de
> F0 **no se conserva** después de F3. En F3 se **renombra y se reescribe** la misma función; queda
> **una sola** aserción de censo viva en el archivo. Está **prohibido** dejar los dos asserts
> coexistiendo, y está prohibido "resolver" la contradicción con `pytest.mark.skip`. Gate de que se
> hizo bien: `grep -c "services.claude_code_cli_runner" tests/test_epic_autopublish_runtime_parity.py`
> debe pasar de `1` (tras F0) a `0` (tras F3), salvo dentro de comentarios.

**Comando (venv verificado: `backend\venv\Scripts\python.exe` existe; también existe `backend\.venv`,
NO usar ese):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m pytest tests/test_epic_autopublish_runtime_parity.py -v
```

**Criterio binario:** salida `2 passed` **contra el código actual, sin ningún cambio de producción**.
Exit 0 no alcanza: hay que ver el conteo (gotcha de la casa: una selección vacía da exit 0).

**Flag:** ninguna. **Runtimes:** N/A (test estructural). **Trabajo del operador:** ninguno.

---

### F1 — Extraer el publicador único a un servicio runtime-agnóstico

**Objetivo:** un módulo nuevo que publique la épica/issue sin saber qué runtime corrió, espejo de
`incident_autopublish` (mismo esqueleto: función `maybe_*` + `register`).

**Archivo a crear:** `Stacky Agents/backend/services/epic_autopublish.py`

**Símbolos exactos a crear:**
- `maybe_autopublish_epic(*, ticket_id, execution_id, final_status, agent_type, error=None, **_) -> None`
- `register(register_post_hook) -> None`
- `_load_run(execution_id) -> dict | None`
- `_claim(execution_id) -> bool` (F2-bis)
- `_apply_result(...)`, `_seal_and_degrade(...)`, `_degrade_execution_row(...)` (F2)

**Discriminador de "esto es un run brief→épica"** (reemplaza al `_one_shot` del runner, que hoy es
`_is_one_shot(t_ado_id)` → `t_ado_id in _ONE_SHOT_ADO_IDS`, `claude_code_cli_runner.py:220-225`,
`_ONE_SHOT_ADO_IDS = frozenset({-1, -7, -8, -9})` en `:220`):

> `agent_type == "business"` **Y** el `input_context` de la ejecución contiene un bloque con
> `id == "brief"`.

**Diferencia MEDIDA respecto de hoy (corrige C6 — no es "equivalente", es *más estrecho*):**

- **Sobre-disparo: NINGUNO.** Verificado con `grep -rn '"id": "brief"' --include=*.py` sobre
  `backend/` excluyendo `tests/`: el **único** sitio de producción que inyecta ese bloque es
  `api/agents.py:792`, dentro de `run_brief`, que siempre usa el Brief Pool `ado_id=-1`
  (`api/agents.py:778-788`). No hay ningún otro endpoint que pueda hacer publicar al hook por error.
- **Sub-disparo: SÍ, y es deliberado.** Hoy una run con `agent_type=="business"` sobre
  `ado_id ∈ {-7, -8, -9}` (Documentador `services/doc_documenter.py:304`; Incident Pool
  `api/agents.py:991`; variantes `services/variant_generator.py:115`) **entra igual** al closure y
  llama al publicador con `brief=""`. Mañana no publica. Es una mejora (publicar una épica sin brief
  es basura), pero **se declara** en vez de esconderse, y se congela con el test 2-bis.

`run_brief` **siempre** inyecta el bloque `brief` (`api/agents.py:790-798`, verificado) y ese bloque es
además el que provee el argumento `brief=` del publicador (hoy el runner lo extrae igual,
`claude_code_cli_runner.py:1696-1700`). Un chat interactivo del BusinessAgent no tiene bloque `brief`
⇒ **no publica**.

**Ventana temporal del rescate (`run_started_at`) — corrige C8. LEER ANTES DE IMPLEMENTAR.**

Hoy el runner pasa `run_started_at=spawn_epoch` (`claude_code_cli_runner.py:1714`), y
`spawn_epoch = time.time()` se toma en `:1032`, **justo antes de lanzar el proceso**. Ese valor es el
`min_mtime` del rescate desde disco (`api/tickets.py:7300`, comentario literal: *"C4/R-STALE: solo
artefactos de ESTA run"*). Derivarlo de `AgentExecution.started_at` (`models.py:278`,
`default=datetime.utcnow`, que se escribe al **crear** la fila, mucho antes) **amplía la ventana hacia
atrás** y habilita rescatar y publicar un artefacto que NO es de esta run. Además `datetime.utcnow()`
es **naive**: `.timestamp()` lo interpreta como hora **local**, con desfase de horas en Windows.

Solución en dos pasos:

- **F1-bis (cambio mínimo en el runner, 1 línea):** en `claude_code_cli_runner.py`, inmediatamente
  después de `spawn_epoch = time.time()` (`:1032`), sellar el valor en la fila para que el hook lo
  pueda leer. Usar el helper de metadata ya existente del módulo; si no hay uno a mano, escribirlo con
  `session_scope()` + merge sobre `metadata_dict` (mismo patrón que `_mark_terminal`,
  `claude_code_cli_runner.py:3166-3184`). Clave: `metadata["spawn_epoch"] = spawn_epoch`.
- **En el servicio:**
  ```python
  def _run_started_at(md: dict, started_at) -> float | None:
      v = md.get("spawn_epoch")
      if isinstance(v, (int, float)):
          return float(v)                      # camino normal: identico a hoy
      if started_at is None:
          return None
      # Fallback SOLO para runs viejas o runtimes que no sellan spawn_epoch.
      # utcnow() es naive: hay que declarar UTC o el epoch sale desplazado.
      from datetime import timezone
      return started_at.replace(tzinfo=timezone.utc).timestamp()
  ```

**Pseudocódigo del hook (v2):**

```python
def maybe_autopublish_epic(*, ticket_id, execution_id, final_status, agent_type, error=None, **_):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_EPIC_AUTOPUBLISH_BACKEND", True):
        return
    if (agent_type or "").lower() != "business":
        return
    if final_status not in ("completed", "needs_review"):
        return            # error / cancelled / no terminal: nada que publicar

    run = _load_run(execution_id)   # output, metadata, input_context, started_at, project_name
    if run is None:
        return
    brief_text = next((str(b.get("content") or "")
                       for b in run["input_context"]
                       if isinstance(b, dict) and b.get("id") == "brief"), None)
    if brief_text is None:
        return            # no es un run brief->epica (chat interactivo): NO publicar

    md = dict(run["metadata"] or {})
    is_issue = (str(md.get("work_item_type") or "Epic") == "Issue"
                and getattr(_cfg, "STACKY_ISSUE_FROM_BRIEF_ENABLED", False))
    seal_key = "issue_ado_id" if is_issue else "epic_ado_id"
    if md.get(seal_key):
        return            # ya publicada: idempotente (2a linea de defensa)

    if not _claim(execution_id):   # F2-bis: 1a linea, ATOMICA
        return

    from api.tickets import autopublish_epic_from_run, publish_issue_from_run
    publish = publish_issue_from_run if is_issue else autopublish_epic_from_run
    kwargs = dict(output=run["output"], brief=brief_text,
                  project_name=run["project_name"], already_published_id=md.get(seal_key))
    if not is_issue:
        # publish_issue_from_run NO acepta run_started_at (verificado, api/tickets.py:7695).
        kwargs["run_started_at"] = _run_started_at(md, run["started_at"])

    try:
        res = publish(**kwargs)
    except Exception as exc:                      # noqa: BLE001 — nunca tumbar el chokepoint
        _seal_and_degrade(execution_id, ticket_id, agent_type, error=str(exc))
        return
    _apply_result(execution_id, ticket_id, agent_type, res, seal_key, is_issue)
```

`_load_run` lee de la fila `AgentExecution` (campos verificados en `backend/models.py`, tabla
`agent_executions`, `:263`): `output` (`:272`), `metadata_dict` (property, `:315`), `input_context`
(property, `:299`), `started_at` (`:278`). `project_name` sale del `Ticket` asociado
(`Ticket.stacky_project_name`), igual que hoy hace el runner vía `project_ctx.stacky_project_name`
(`claude_code_cli_runner.py:1701`).

**Tests (TDD, primero):** `Stacky Agents/backend/tests/test_epic_autopublish_service.py`
(misma cabecera obligatoria de `DATABASE_URL` que F0).

1. `test_publica_cuando_hay_bloque_brief` — mock de `api.tickets.autopublish_epic_from_run`,
   `assert_called_once()`.
2. `test_no_publica_sin_bloque_brief` — chat interactivo del BusinessAgent ⇒ 0 llamadas.
2-bis. `test_no_publica_para_business_en_pool_sin_brief` — ticket `ado_id=-8`, `agent_type="business"`,
   `input_context` **sin** bloque `brief` ⇒ 0 llamadas. **Congela el sub-disparo declarado** (C6).
3. `test_no_publica_si_ya_esta_sellado` — `metadata["epic_ado_id"]` presente ⇒ 0 llamadas.
4. `test_no_publica_con_flag_off` — `STACKY_EPIC_AUTOPUBLISH_BACKEND=False` ⇒ 0 llamadas.
5. `test_no_publica_en_estado_no_terminal` — parametrizado sobre `["running","error","cancelled"]`
   ⇒ 0 llamadas en los 3. Criterio: `3 passed` en ese parámetro.
6. `test_bifurca_a_issue_con_flag_on` — `work_item_type="Issue"` + `STACKY_ISSUE_FROM_BRIEF_ENABLED=True`
   ⇒ llama `publish_issue_from_run`, **y** `autopublish_epic_from_run` recibe 0 llamadas.
7. `test_run_started_at_sale_de_spawn_epoch_sellado` — metadata con `spawn_epoch=1234567890.5`
   ⇒ el kwarg `run_started_at` vale **exactamente** `1234567890.5`.
7-bis. `test_run_started_at_fallback_es_utc` — sin `spawn_epoch`, con
   `started_at=datetime(2026,1,1,0,0,0)` ⇒ el kwarg vale `1767225600.0` (epoch UTC de esa fecha),
   **independiente de la TZ de la máquina**. Congela el bug de naive datetime.
8. `test_una_excepcion_del_publicador_no_propaga` — el hook nunca puede tumbar `on_execution_end`.

**Comando:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m pytest tests/test_epic_autopublish_service.py -v
```

**Criterio binario:** salida `10 passed` (8 casos + 2-bis + 7-bis; el caso 5 parametrizado cuenta 3, así
que el total esperado es `12 passed` — verificar el número exacto en la salida, no el exit code).
**Flag:** reusa `STACKY_EPIC_AUTOPUBLISH_BACKEND` (ON). **Trabajo del operador:** ninguno.

---

### F2 — Sellado de metadata y degradación de estado desde el post-hook

**Objetivo:** que el hook reproduzca los efectos laterales que hoy tiene el finalizador del runner.
**Ésta es la fase donde se esconde el falso verde**, y va sola por eso.

**El problema exacto:** hoy `_maybe_autopublish_epic` corre **ANTES** de `_mark_terminal`
(publicación en `claude_code_cli_runner.py:1936`, `_mark_terminal` en `:1967`, `on_execution_end` en
`:2002`). Por eso puede (a) **devolver** un `final_status` degradado a `needs_review` que el runner
después usa, y (b) mutar el dict `metadata` local, que viaja a `_mark_terminal`.

Un post-hook corre **DESPUÉS** de `set_status` (`ticket_status.py:332` → hooks en `:349-355`). No puede
devolver nada ni mutar un dict local. Tiene que **escribir él mismo, en las DOS capas**.

**Archivo a editar:** `Stacky Agents/backend/services/epic_autopublish.py`

**Contrato exacto a reproducir** (leído de `claude_code_cli_runner.py:1716-1745` — **9 filas**, v1
tenía 7 y perdía las 2 últimas; C7):

| Situación (línea del runner) | metadata a sellar | Estado |
|---|---|---|
| Excepción inesperada (`:1716-1719`) | `epic_publish_error = str(exc)` | → `needs_review` |
| `res.error is not None` (`:1720-1724`) | `epic_publish_error = res.error` | → `needs_review` |
| Éxito, `ado_id` y no skipped (`:1725-1727`) | `epic_ado_id` / `issue_ado_id` = `res.ado_id` | sin cambio |
| Ya publicada, skipped (`:1728-1729`) | re-afirmar el sello | sin cambio |
| `res.grounding_warnings` (`:1733-1734`) | `grounding_warnings` | sin cambio |
| `res.epic_summary` (`:1735-1736`) | `epic_summary` | sin cambio |
| `res.recovery_method` (`:1737-1739`) | `epic_recovery` | sin cambio |
| **Épica, no skipped, `res.published_html` (`:1741-1743`)** | **`epic_baseline_html`** (Plan 60 F1) | sin cambio |
| **Épica, no skipped, `res.baseline_rev` (`:1744-1745`)** | **`epic_baseline_rev`** (Plan 60 F1) | sin cambio |

> Las 2 últimas van bajo la condición literal del runner: `if not _is_issue and not _res.skipped:`.
> Sin ellas el aprendizaje bidireccional del Plan 60 se queda sin baseline y el diff de ediciones del
> operador deja de funcionar — regresión silenciosa.

**Escritura del metadata:** leer-modificar-escribir sobre `AgentExecution.metadata_dict` dentro de un
`session_scope()`, **mergeando** (nunca reemplazando el dict entero: el runner ya escribió ahí
`runtime`, `work_item_type`, `spawn_epoch`, `epic_convergence`, `confidence`, `contract_score`, etc.).

**Degradación de estado — LAS DOS CAPAS (corrige C3). Firmas literales:**

```python
def _degrade_execution_row(execution_id: int, error_text: str) -> None:
    """Capa 1: la FILA. Hoy esto lo hace _mark_terminal(status='needs_review')
    (claude_code_cli_runner.py:1967 -> :3161-3184). Sin esto, la fila queda
    'completed' mientras el ticket dice 'needs_review': incoherencia observable
    en /api/executions, en el output_watcher y en recover_stale_running_tickets."""
    from db import session_scope
    from models import AgentExecution
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None or row.status not in ("completed",):
            return                       # no pisar error/cancelled ya escritos
        row.status = "needs_review"
        md = dict(row.metadata_dict or {})
        try:
            from harness.failure import classify      # paridad con _mark_terminal
            kind = classify(return_code=md.get("return_code"),
                            error_message=error_text,
                            metadata={**md, "status": "needs_review"})
            if kind is not None:
                md["failure_kind"] = kind
        except Exception:                              # noqa: BLE001
            pass
        row.metadata_dict = md


def _degrade_ticket(ticket_id: int, execution_id: int, agent_type, error_text: str) -> None:
    """Capa 2: el TICKET."""
    from services import ticket_status
    ticket_status.set_status(
        ticket_id,
        "needs_review",
        changed_by="system:epic_autopublish",   # OBLIGATORIO: keyword-only sin default
        execution_id=execution_id,              # (ticket_status.py:147)
        agent_type=agent_type,
        reason=f"autopublish de la epica fallo: {error_text}"[:500],
        guard_downgrade=False,                  # EXPLICITO. El guard del Plan 254 F1
    )                                           # solo bloquea completed->error
```                                             # (_would_degrade, ticket_status.py:58-67);
                                                # no bloquearia esto, pero se declara.

> **PROHIBIDO** copiar el call-site de `on_execution_end` (`ticket_status.py:332-343`) y pasar
> `guard_downgrade=True` por mimetismo.

> **Riesgo a probar explícitamente (C-recursión):** el hook corre *dentro* de `_run_post_hooks`
> (`ticket_status.py:395-400`), que corre dentro de `on_execution_end`. Si el hook llamara
> `on_execution_end` de nuevo para degradar, **se re-dispararían todos los post-hooks**, incluido él
> mismo ⇒ recursión / doble publicación. Por eso el contrato dice `set_status`, **no**
> `on_execution_end`. F2 trae el test 12 que lo congela por AST.

**Tests:** ampliar `test_epic_autopublish_service.py`
9.  `test_error_del_publicador_degrada_a_needs_review` — el ticket queda `needs_review` y se sella
    `epic_publish_error`.
10. `test_exito_sella_epic_ado_id_sin_pisar_metadata_previa` — metadata preexistente (`runtime`,
    `work_item_type`, `spawn_epoch`) sigue **intacta** después del sellado.
11. `test_sella_grounding_warnings_epic_summary_y_epic_recovery`.
11-bis. `test_sella_epic_baseline_html_y_rev_solo_en_epica_no_skipped` — y **0 sellos** cuando
    `is_issue=True` o `skipped=True`.
12. `test_el_hook_no_llama_on_execution_end` — gate por **AST** sobre `services/epic_autopublish.py`:
    cero `ast.Attribute` con `attr == "on_execution_end"` y cero `ast.Name` con
    `id == "on_execution_end"`. Congela la no-recursión.
13. `test_fallo_de_publicacion_degrada_TAMBIEN_la_fila` — tras el hook,
    `AgentExecution.status == "needs_review"` **y** `metadata["failure_kind"]` presente. **Este es el
    test que hace imposible el falso verde de C3.**

**Comando:** el mismo de F1.
**Criterio binario:** el conteo del archivo sube de `12 passed` a `18 passed` (5 casos nuevos, ninguno
parametrizado). Verificar el número, no el exit code. **Trabajo del operador:** ninguno.

---

### F2-bis — `[ADICIÓN ARQUITECTO] A1` — Claim atómico: a lo sumo UNA publicación por ejecución

**Por qué existe esta fase (hallazgo de la crítica, no del v1).** Al mover el publicador al post-hook,
la cantidad de intentos de publicación por ejecución deja de ser 1 y pasa a ser *"uno por cada
`on_execution_end` que reciba esa ejecución"*. Verificado que existen al menos **tres** disparadores
posibles para la misma fila, y **dos de ellos corren en hilos distintos**:

- el runner, en su hilo de fondo (`claude_code_cli_runner.py:2002`);
- el **gateway de completion**, dentro del request HTTP de Flask del PATCH del agente
  (`services/agent_completion.py:1230`), cuya guarda `idempotent_replay` sólo se activa si la ejecución
  **ya** estaba terminal (`:1184-1188`) — es decir, **no** protege el caso en que el agente PATCHea
  antes de que el runner cierre;
- `scripts/rescue_execution.py:497`, rescate manual del operador.

El sello `md.get(seal_key)` del F1 es un read-modify-write **sin atomicidad**: dos hilos leen el sello
vacío, los dos llaman `autopublish_epic_from_run` con `already_published_id=None` (que en
`api/tickets.py:7272-7273` sólo cortocircuita cuando **no** es `None`) ⇒ **dos épicas en el GitLab/ADO
real del operador**. Ese es el riesgo de mayor consecuencia de todo el plan y v1 no lo cerraba.

**Contrato:** antes de llamar al publicador, la ejecución debe **ganar un claim**, con una **única
sentencia SQL** cuyo `rowcount` decide. Una sola sentencia es atómica también en SQLite.

```python
_CLAIM_KEY = "epic_publish_claim"

def _claim(execution_id: int) -> bool:
    """True solo para el PRIMER llamador. Atomico: UN solo UPDATE condicional.

    No usa read-modify-write: dos on_execution_end concurrentes sobre la misma
    fila leerian los dos el sello vacio y publicarian los dos.
    """
    import json
    from datetime import datetime
    from sqlalchemy import text
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return False
        md = dict(row.metadata_dict or {})
        if md.get(_CLAIM_KEY):
            return False                      # ya reclamado (chequeo barato previo)
        md[_CLAIM_KEY] = {"at": datetime.utcnow().isoformat(), "by": "epic_autopublish"}
        payload = json.dumps(md, ensure_ascii=False)
        res = session.execute(
            text(
                "UPDATE agent_executions SET metadata_json = :md "
                "WHERE id = :eid "
                "AND (metadata_json IS NULL OR metadata_json NOT LIKE :probe)"
            ),
            {"md": payload, "eid": execution_id, "probe": f'%"{_CLAIM_KEY}"%'},
        )
        return res.rowcount == 1              # el perdedor ve 0 y se va en silencio
```

Nombre de tabla verificado: `agent_executions` (`models.py:263`). Columna verificada:
`metadata_json` (`models.py:274`).

**Tests:** ampliar `test_epic_autopublish_service.py`
14. `test_claim_lo_gana_uno_solo` — dos llamadas seguidas a `_claim(exec_id)` ⇒ `True`, luego `False`.
15. `test_dos_on_execution_end_publican_una_sola_vez` — invocar `maybe_autopublish_epic` **dos veces**
    con el mismo `execution_id` y `epic_ado_id` **sin** sellar (simula el fallo de la 1ª y el reintento
    de la 2ª) ⇒ `autopublish_epic_from_run.call_count == 1`.
16. `test_claim_concurrente_desde_dos_hilos` — `threading.Thread` x2 sobre `maybe_autopublish_epic`
    con `threading.Barrier(2)` para forzar el solape ⇒ `call_count == 1`. Si el entorno da
    `SQLITE_LOCKED` (gotcha de la casa: todo test de DB concurrente es flaky), envolver con
    `@pytest.mark.flaky`-equivalente **NO**: reintentar la sentencia dentro de `_claim` con
    `run_with_retry` si ya existe en el módulo, o marcar el test con un `xfail` **estricto y
    justificado por escrito**. Prohibido borrarlo.

**Criterio binario:** `21 passed` en el archivo (18 + 3). **KPI K5.**
**Trabajo del operador:** ninguno.

---

### F3 — UN solo publicador: sacar el closure del runner de Claude

**Objetivo:** eliminar el segundo motor **antes** de que exista, para no repetir el anti-patrón de los
2 motores CI/CD del plan 260 y los 2 motores de probe de tracker.

**Archivo a editar:** `Stacky Agents/backend/services/claude_code_cli_runner.py`

**LOS 3 RANGOS EXACTOS (corrige C1 — el rango de v1 borraba el `if _runaway_triggered:`).**
Borrar **de abajo hacia arriba** para que los números no se corran:

| # | Rango | Primera línea (literal) | Última línea (literal) |
|---|-------|-------------------------|------------------------|
| 3 | `1934-1936` | `            # Plan 41 — autopublicar la épica antes de marcar terminal. Puede` | `            final_status = _maybe_autopublish_epic(final_status)` |
| 2 | `1750-1752` | `            # Incluso en runaway intentamos publicar la épica si el agente alcanzó` | `            _maybe_autopublish_epic("needs_review")` |
| 1 | `1670-1747` | `        # Plan 41 — Autopublicación backend de la épica brief→épica.` | *(línea 1746)* `            return current_status` **+ la 1747 en blanco** |

**Lo que NO se toca, verificado:**
- `:1749` **`if _runaway_triggered:`** — **queda**. Su cuerpo pasa a empezar en la actual `:1753`
  (`metadata["runaway"] = {`). Si esta línea desaparece, el bloque `1753-1787` se ejecuta
  incondicionalmente o el archivo no compila.
- `:1748` `# H5 — trazabilidad del runaway guard.` — queda.
- `:1660-1669` bloque `epic_convergence` (Plan 58) — **no se toca**. Está pegado arriba del rango 1.
- `:1937+` bloque `# Plan 38 C1 — Trazabilidad` — no se toca. Está pegado abajo del rango 3.

**Gate de sintaxis obligatorio inmediatamente después del borrado:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m compileall -q services/claude_code_cli_runner.py
```
Debe salir sin output y exit 0. Un `IndentationError` acá significa que se comió el `if` de `:1749`.

**Camino `:1752` — RESUELTO, no pendiente (corrige el R3 abierto de v1).** Verificado abriendo el
archivo: ese camino es el `if _runaway_triggered:` de `:1749`, y **sí** termina llamando
`ticket_status.on_execution_end(...)` en **`:1782-1787`**, con `final_status="needs_review"` — que es
uno de los dos estados que el hook acepta (F1). Además `_mark_terminal(status="needs_review", ...)` ya
corrió en `:1760-1765`, así que el `output` está persistido cuando el hook lo lee. **Ese camino no
pierde la publicación.** No hace falta ningún fix extra.

**Tests:** reemplazar el caso 1 de F0 en `test_epic_autopublish_runtime_parity.py` (renombrar la
función, no agregar una segunda):

```python
def test_un_solo_publicador_por_ast():
    # K2: el censo se hace por AST de REFERENCIAS porque el publicador vivia
    # dentro de un CLOSURE y se invoca por ALIAS; un grep -c premia al bug y un
    # censo por ast.Call devuelve vacio en los dos lados del cambio.
    assert publishing_modules() == {"services.epic_autopublish"}
```

**`test_speculative_parity.py` (corrige C11 — el anclaje de v1 estaba desfasado).** El test real es
`test_spec_never_calls_autopublish`, **`tests/test_speculative_parity.py:92-111`** (la línea `def` es
la **92**, no la 93). Sus 4 asserts:
- `:101-102` `not hasattr(spec_module, "_maybe_autopublish_epic")`
- `:103-104` `not hasattr(spec_module, "publish_issue_from_run")`
- `:108-109` `"_maybe_autopublish_epic" not in src`
- `:110-111` `"publish_issue_from_run" not in src`

Al desaparecer el símbolo `_maybe_autopublish_epic` del backend, los asserts 1 y 3 quedan vacuos.
**Acción exacta:** reemplazar el literal `"_maybe_autopublish_epic"` por `"maybe_autopublish_epic"` en
los 4 sitios (nombre del símbolo nuevo del servicio) y **agregar** un 5º assert que es el que de verdad
blinda el riel:
```python
    assert "on_execution_end" not in src, \
        "speculative.py no debe llamar on_execution_end: eso disparia el post-hook publicador"
```
Verificado que hoy pasa: `services/speculative.py` usa su propia tabla `SpeculativeRun` y su propio
`_mark()` (`:182-186`) y **no** llama `on_execution_end`.
Actualizar también el docstring del módulo (`tests/test_speculative_parity.py:1-10`), que hoy dice
*"el autopublish ocurre en el runner confirmado"* — pasa a ocurrir en el post-hook.

**Archivo hermano que v1 no mencionaba:** `tests/test_speculative_claim_flow.py:180` tiene el mismo
assert de source-text (`"publish_issue_from_run" not in src`). No requiere cambio, pero **entra en la
lista de no-regresión de F7**.

**Comando:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m compileall -q services/claude_code_cli_runner.py
.\venv\Scripts\python.exe -m pytest tests/test_epic_autopublish_runtime_parity.py tests/test_speculative_parity.py tests/test_speculative_claim_flow.py -v
```

**Criterio binario:** `compileall` exit 0 **y** censo por AST devuelve exactamente
`{"services.epic_autopublish"}` **y** los 3 archivos de test verdes con el conteo esperado
(`2 passed` en el de paridad — el caso 1 renombrado + el caso 2 de F0 sigue vivo).
**Trabajo del operador:** ninguno.

---

### F4 — Registrar el hook y reemplazar el gate 400

**Objetivo:** encender la paridad de punta a punta sin abrir un falso verde nuevo.

**Archivos a editar:**

1. `Stacky Agents/backend/app.py` — **antes** de la línea `:994`
   (`incident_autopublish.register(ticket_status.register_post_hook)`), es decir insertando entre la
   `:993` y la `:994`, agregar:
   ```python
   # Plan 278 F4 — publicador unico de la epica/issue del brief, agnostico de
   # runtime. Va PRIMERO en la lista de post-hooks: degrada la fila y el ticket
   # antes de que completion_dispatcher (app.py:999) sincronice el tracker y de
   # que qa_uat_enqueue (app.py:1011) encole una validacion E2E.
   from services import epic_autopublish
   epic_autopublish.register(ticket_status.register_post_hook)
   ```
   > **Orden, no cosmética (C9).** `_run_post_hooks` (`ticket_status.py:395-400`) le pasa a **todos**
   > los hooks el **mismo** `final_status`, calculado en `:347` **antes** de correr ninguno. Aunque
   > `epic_autopublish` vaya primero y degrade, los hooks siguientes van a recibir el `final_status`
   > **pre-degradación**. Registrarlo primero es lo mejor que se puede hacer sin rediseñar el
   > chokepoint; la limitación se documenta en R9 y queda **fuera de scope** corregirla.

2. `Stacky Agents/backend/api/agents.py` — **reemplazar** el bloque `:654-667` (comentario del Plan 52
   F0 + `_AUTOPUBLISH_RUNTIME` + el `if` + el `return jsonify(...400)`) por el bloque de F4-bis
   (abajo). El resto de `run_brief` no cambia: se conservan intactos el gate de `work_item_type`
   (`:647-651`), el de `issue_from_brief_disabled` (`:652-653`) y todo lo que sigue desde `:668`.

3. `Stacky Agents/backend/tests/test_run_brief_autopublish_parity.py` — **invertir 3 casos y conservar
   1** (nombres reales verificados, `:52`, `:62`, `:74`, `:88`):
   - `test_run_brief_epic_codex_returns_400` (`:52`) → `test_run_brief_epic_codex_no_es_rechazado`
   - `test_run_brief_issue_copilot_returns_400` (`:62`) → `test_run_brief_issue_copilot_no_es_rechazado`
   - `test_run_brief_epic_default_runtime_copilot_returns_400` (`:88`) → `..._default_copilot_no_es_rechazado`
   - `test_run_brief_epic_claude_cli_not_rejected_by_parity_guard` (`:74`) → se **conserva** sin cambios
     (no-regresión).

   En los 3 invertidos, los asserts son:
   ```python
   assert resp.get_json().get("error") != "autopublish_requires_claude_cli"
   mock_run_agent.assert_called_once()   # "no da 400" solo NO prueba que arranco
   ```

   > **Procedimiento obligatorio si `assert_called_once()` falla (corrige C10).** Al caer el gate, el
   > request recorre el resto de `run_brief`. Verificado que **no** hay riesgo de red: el pre-vuelo
   > sólo corre si `payload["preflight"]` es truthy (`api/agents.py:736`) y los tests no lo mandan, y
   > `services/adaptive_selector.py:4` declara *"NO hace I/O"*. Lo que **no** está verificado es que el
   > resto del path sobreviva a la `session` MagicMock de `_patch_deps`
   > (`tests/test_run_brief_autopublish_parity.py:27-41`), donde `pool_ticket.id` es un `MagicMock` y
   > no un `int`. Si el test falla, el fix correcto es **extender `_patch_deps`** con los mocks que
   > falten. **PROHIBIDO** debilitar o borrar `assert_called_once()`: sin él, el test pasaría con un
   > `run_brief` que devuelve 500 y el KPI K1 sería falso.

   Reescribir el docstring del módulo (`:1-6`), que hoy describe el comportamiento contrario.

**Criterio binario:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m pytest tests/test_run_brief_autopublish_parity.py -v
```
Salida `4 passed`.

**Y el gate de residuo (corrige C17 — v1 pedía `= 0` en `backend/` mientras F4 obliga a escribir el
literal en los asserts: mutuamente insatisfacible):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
grep -rn "autopublish_requires_claude_cli" --include=*.py . | grep -v "^./tests/" | grep -v "/venv/" | grep -v "/.venv/"
```
Debe devolver **0 líneas**. Dentro de `backend/tests/` el literal **sigue existiendo** y es correcto que
siga: es lo que asserta que el error ya no se emite.

**Runtimes:** Codex ✅ / Claude ✅ / Copilot ✅. **Trabajo del operador:** ninguno.

---

### F4-bis — `[ADICIÓN ARQUITECTO] A2` — El 400 no se borra: se reemplaza

**Por qué existe esta fase (hallazgo de la crítica).** El gate del Plan 52 F0 hacía dos cosas: (a)
rechazaba runtimes sin publicador, y (b) **de rebote** garantizaba que, con
`STACKY_EPIC_AUTOPUBLISH_BACKEND=false`, ningún `run_brief` de Epic/Issue terminara `completed` sin
épica. Borrar el gate sin más deja el rollback por flag convertido en un **falso verde en los 3
runtimes**: el operador apaga la flag para frenar la escritura en su tracker y recibe runs verdes sin
work item y sin error. Eso es exactamente el defecto que el Plan 41 vino a cerrar.

**Cambio exacto** (es el bloque que reemplaza a `api/agents.py:654-667`):

```python
    # Plan 278 F4-bis — el publicador ya es agnostico de runtime (post-hook en
    # ticket_status.on_execution_end), asi que el rechazo por RUNTIME desaparece.
    # Lo que NO desaparece es el rechazo cuando el autopublish esta APAGADO: sin
    # el, un run_brief de Epic/Issue con la flag OFF terminaria 'completed' sin
    # work item y sin error — el falso verde que el Plan 41 vino a cerrar.
    if work_item_type in ("Epic", "Issue") and not config.STACKY_EPIC_AUTOPUBLISH_BACKEND:
        return jsonify({
            "ok": False,
            "error": "autopublish_disabled",
            "detail": (
                f"work_item_type={work_item_type!r} requiere STACKY_EPIC_AUTOPUBLISH_BACKEND=ON; "
                "la flag esta apagada y el work item no se crearia."
            ),
        }), 400
```

**Tests:** agregar a `test_run_brief_autopublish_parity.py`
5. `test_run_brief_epic_copilot_rechazado_con_flag_off` — `patch.object(config,
   "STACKY_EPIC_AUTOPUBLISH_BACKEND", False)` ⇒ 400 con `error == "autopublish_disabled"` y
   `mock_run_agent.assert_not_called()`.
6. `test_run_brief_epic_copilot_aceptado_con_flag_on` — el default ⇒ `error != "autopublish_disabled"`.

**Criterio binario:** el archivo pasa de `4 passed` a `6 passed`.
**Flag:** no crea ninguna; le da semántica de rollback real a la existente.
**Trabajo del operador:** ninguno (gana un error legible donde antes había silencio).

---

### F5 — Prueba de paridad real, parametrizada por runtime

**Objetivo:** probar K3 — que los 3 runtimes publican por el mismo camino.

**Archivo a editar:** `Stacky Agents/backend/tests/test_epic_autopublish_runtime_parity.py`
(la cabecera con `DATABASE_URL=sqlite:///:memory:` de F0 ya está; **no** correr este test sin ella).

**Caso nuevo:**
```python
@pytest.mark.parametrize("runtime", ["claude_code_cli", "codex_cli", "github_copilot"])
def test_los_tres_runtimes_publican_por_el_mismo_camino(runtime, monkeypatch):
    # 1. Crear Ticket + AgentExecution reales en la sqlite en memoria, con
    #    input_context = [{"id": "brief", "content": "BRIEF X"}],
    #    metadata_dict = {"runtime": runtime, "work_item_type": "Epic"},
    #    output = <HTML de epica valido>, agent_type = "business".
    # 2. Mockear api.tickets.autopublish_epic_from_run (NUNCA se toca el tracker real).
    # 3. create_app() para poblar _POST_HOOKS, y disparar
    #    ticket_status.on_execution_end(ticket_id=..., execution_id=...,
    #                                   final_status="completed", agent_type="business").
    # 4. Assert: call_count == 1 (no 0, no 2) y el kwarg brief == "BRIEF X"
    #    y project_name == el del Ticket, IGUALES para los 3 runtimes.
```

**Criterio binario:** los 3 parámetros verdes y `call_count == 1` en cada uno. El `assert_called_once`
es el que detecta la doble publicación.

> **Anti-falso-verde:** exigir que la salida diga **`3 passed`** para este test
> (`-k test_los_tres_runtimes` ⇒ `3 passed`). Un `-k` sin match da exit 0 — gotcha de la casa.
> Verificar el conteo, no el exit code.

**Comando:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m pytest tests/test_epic_autopublish_runtime_parity.py -v -k test_los_tres_runtimes
```

**Trabajo del operador:** ninguno.

---

### F6 — La flag del autopublish se vuelve visible en la UI

**Hallazgo del v1, confirmado por la crítica:** `STACKY_EPIC_AUTOPUBLISH_BACKEND` está **viva** en
`config.py:1054-1055` con default `true`, pero **no está registrada en
`backend/services/harness_flags.py`** (verificado: `grep -n "EPIC_AUTOPUBLISH" services/harness_flags.py`
devuelve **0 líneas**). Consecuencia: gobierna una acción que **escribe en el GitLab/ADO real del
operador** y el operador **no puede verla ni apagarla desde la UI** — sólo editando `.env`. Eso viola
el riel de la casa "toda flag/config del operador va por UI; sólo los kill-switches son env-only", y
este no es un kill-switch. Después de este plan la flag pasa a gobernar el autopublish de **los 3
runtimes** en vez de uno, así que su invisibilidad deja de ser menor. Con F4-bis, además, es la palanca
de rollback documentada.

**Archivo a editar:** `Stacky Agents/backend/services/harness_flags.py`

**Cambio 1 — el `FlagSpec`** (espejo del de `INTENT_PREFLIGHT_ENABLED`, `:2863-2873`, verificado;
todos los campos son keyword, el orden del dataclass `:21-42` no obliga):
```python
    FlagSpec(
        key="STACKY_EPIC_AUTOPUBLISH_BACKEND",
        type="bool",
        default=True,          # ya era true en config.py:1054; NO se cambia el default
        label="Autopublicar la épica del brief (41)",
        description=(
            "Plan 41 / Plan 278 — Si ON, al cerrar una run brief→épica el backend publica "
            "la Épica/Issue en el tracker del proyecto, en los 3 runtimes. OFF = run_brief "
            "rechaza Epic/Issue con 'autopublish_disabled' en vez de terminar en falso verde."
        ),
        group="global",
    ),
```

**Cambio 2 — la categorización (corrige C12; v1 lo omitía por completo).** El propio archivo lo declara
obligatorio en `services/harness_flags.py:551-552`:
*"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` (arriba) o el test
`test_every_registry_flag_is_categorized` rompe CI a propósito (Plan 63)"*.

El mapa es `_CATEGORY_KEYS` (`:120`). **La categoría destino es `"epicas_ado"` (`:200`)**, que ya
agrupa `STACKY_EPIC_FROM_BRIEF_ENABLED` (`:201`), `STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED` y
`STACKY_EPIC_SUMMARY_ENABLED` (`:202`), `STACKY_EPIC_GATE_ENABLED` (`:205`), etc.
**Acción exacta:** agregar `"STACKY_EPIC_AUTOPUBLISH_BACKEND",` dentro de esa tupla, en la línea
siguiente a la `:201`. No crear categorías nuevas.

**Cambio 3 — los tests (corrige C13 y C22; v1 citaba `test_harness_flags_registry.py`, que
**NO EXISTE** en `backend/tests/`):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v -k "categoriz or registry"
.\venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.\venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -v
```
El meta-test que importa es `tests/test_harness_flags.py::test_every_registry_flag_is_categorized`
(`:988`). Verificar que el `-k` **seleccione al menos 1** caso: un `-k` sin match da exit 0.

> **Rojo AJENO conocido (gotcha de la casa):** `test_harness_flags_help.py` tiene fallos
> **preexistentes** que no son de este plan. Criterio **delta**: el número de fallos de ese archivo
> debe ser **el mismo antes y después** del cambio. Correrlo ANTES de tocar nada y anotar el número en
> el commit.

**No se cambia el default** (sigue ON): la capacidad ya estaba encendida antes de este plan, así que
apagarla sería una regresión de comportamiento, no una mejora de seguridad.

**Criterio binario:** `test_harness_flags.py` verde (incluido
`test_every_registry_flag_is_categorized`), `test_harness_flags_help.py` con el **mismo** número de
fallos que antes del cambio, y la flag aparece en `GET /api/harness/flags`.
**Trabajo del operador:** ninguno (gana una perilla que antes no tenía).

---

### F6-bis — `[ADICIÓN ARQUITECTO] A3` — La paridad de mecanismo se vuelve MEDIBLE

**Por qué existe.** El plan declara honestamente que entrega paridad de **mecanismo**, no de calidad.
Pero después de F4 el operador va a poder mandar briefs con los 3 runtimes y **no va a tener forma de
saber cuál de los 3 le produce épicas publicables**: el único rastro será `epic_publish_error` cuando
falla. Sin medición, la decisión de "con qué runtime mando el brief" queda a intuición, y el propio
KPI K3 sólo prueba que el *camino* es el mismo.

**Cambio:** en `_apply_result` / `_seal_and_degrade` de `services/epic_autopublish.py`, sellar además
un bloque compacto (aditivo, no pisa nada):
```python
    md["epic_publish"] = {
        "runtime": md.get("runtime"),          # ya lo sella el runner (agent_runner.py:175)
        "work_item_type": md.get("work_item_type") or "Epic",
        "outcome": "published" | "skipped" | "failed",
        "error_kind": "epic_not_in_output" | "ado_error" | "exception" | None,
        "recovery_method": getattr(res, "recovery_method", None),
        "at": datetime.utcnow().isoformat(),
    }
```
`error_kind` se deriva del prefijo de `res.error` (`api/tickets.py:7313` emite
`"epic_not_in_output: ..."`), sin parsear el texto completo.

**Por qué es cero trabajo para el operador:** es una clave más en `metadata_dict`, que la UI de la run
ya renderiza. No hay flag nueva, no hay endpoint nuevo, no hay pantalla nueva.

**Tests:** ampliar `test_epic_autopublish_service.py`
17. `test_sella_epic_publish_con_outcome_published`.
18. `test_sella_epic_publish_con_outcome_failed_y_error_kind` — para un `res.error` que empieza con
    `"epic_not_in_output"` ⇒ `error_kind == "epic_not_in_output"`.

**Criterio binario:** el archivo pasa de `21 passed` a `23 passed`.
**Trabajo del operador:** ninguno.

---

### F7 — Gate de cierre

**Objetivo:** un solo comando que prueba los 5 KPI.

**Ratchets — cómo se registra un test (corrige C20; la sintaxis difiere y el meta-test parsea sólo el
`.sh`).** Agregar los 2 archivos nuevos en **AMBOS**, imitando la línea de un vecino verificado:

- `backend/scripts/run_harness_tests.sh` — junto a la `:94` (`  tests/test_speculative_parity.py`),
  formato **sin comillas y sin coma**:
  ```
    tests/test_epic_autopublish_service.py
    tests/test_epic_autopublish_runtime_parity.py
  ```
- `backend/scripts/run_harness_tests.ps1` — junto a la `:87`
  (`  "tests/test_speculative_parity.py",`), formato **con comillas y con coma**:
  ```
    "tests/test_epic_autopublish_service.py",
    "tests/test_epic_autopublish_runtime_parity.py",
  ```

> Gotcha de la casa: el ratchet **no admite rutas con espacios**; estas no los tienen. Y los dos
> archivos ya divergen en ~64 entradas: eso es deuda ajena, no se toca.

**Criterio binario de cierre (DoD):**

| KPI | Verificación |
|-----|--------------|
| K1 | `test_run_brief_autopublish_parity.py` → `6 passed`, ningún `autopublish_requires_claude_cli` |
| K2 | censo AST → `{"services.epic_autopublish"}` exactamente |
| K3 | `test_los_tres_runtimes_publican_por_el_mismo_camino` → `3 passed` |
| K4 | `STACKY_EPIC_AUTOPUBLISH_BACKEND` en `FLAG_REGISTRY` **y** en `_CATEGORY_KEYS["epicas_ado"]`; `tests/test_harness_flags.py::test_every_registry_flag_is_categorized` verde |
| K5 | `test_dos_on_execution_end_publican_una_sola_vez` y `test_claim_lo_gana_uno_solo` verdes |

**No-regresión obligatoria** (correr **por archivo**, nunca `pytest tests` entero — 2260 errores de
contaminación, gotcha de la casa). **12 archivos** (v1 listaba 10; se suman los 2 que la crítica
encontró):
`test_epic_autopublish_backend.py`, `test_epic_grounding.py`, `test_epic_narration_guard.py`,
`test_publish_issue.py`, `test_issue_observability.py`, `test_persist_issue_ticket.py`,
`test_autopublish_rescue.py`, `test_autopublish_rev_from_response.py`, `test_speculative_parity.py`,
`test_epic_payload_preview.py`, **`test_speculative_claim_flow.py`**,
**`test_epic_confidence_extraction.py`**.

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
foreach ($f in @("test_epic_autopublish_backend","test_epic_grounding","test_epic_narration_guard","test_publish_issue","test_issue_observability","test_persist_issue_ticket","test_autopublish_rescue","test_autopublish_rev_from_response","test_speculative_parity","test_epic_payload_preview","test_speculative_claim_flow","test_epic_confidence_extraction")) { .\venv\Scripts\python.exe -m pytest "tests/$f.py" -q }
```

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación |
|---|--------|-----------|------------|
| R1 | **Doble publicación por convivencia** (hook + closure vivos a la vez) ⇒ 2 épicas en el tracker real | ALTA | F3 borra el closure **antes** de F4 registrar el hook. K2 por AST lo congela. `assert_called_once` en F5. |
| R2 | **Recursión de post-hooks**: el hook llama `on_execution_end` para degradar ⇒ se re-dispara a sí mismo | ALTA | Contrato F2: `set_status`, nunca `on_execution_end`. Gate por AST (test 12). |
| R3 | ~~El camino temprano `:1752` pierde la publicación~~ | **CERRADO** | Verificado: ese camino es `if _runaway_triggered:` (`:1749`) y **sí** llama `on_execution_end` en `:1782-1787` con `needs_review`. No requiere acción. |
| R4 | Copilot/Codex devuelven narración ⇒ épicas basura | MEDIA | Ya cubierto: `_looks_like_epic` falla ruidoso con `epic_not_in_output` → `needs_review` (`api/tickets.py:7284-7318`). Declarado como paridad de MECANISMO (§1) y **medido** por F6-bis. |
| R5 | El hook publica en un chat interactivo del BusinessAgent | MEDIA | Discriminador por bloque `brief` (F1) + tests 2 y 2-bis. Verificado que `api/agents.py:792` es el único inyector. |
| R6 | `test_speculative_parity.py` queda vacuo al desaparecer el símbolo | MEDIA | F3 lo actualiza con literales exactos y **agrega** el assert de `on_execution_end`, que es el que de verdad blinda el riel. |
| R7 | Orden de sellado: el hook escribe metadata después de que el runner ya la escribió ⇒ pisa | MEDIA | F2 exige merge leer-modificar-escribir, con test 10 sobre `runtime`/`work_item_type`/`spawn_epoch`. |
| R8 | El post-hook corre **sincrónico**. En el camino del runner es un hilo de fondo (igual que hoy), pero en el camino del **gateway** (`agent_completion.py:1230`) corre **dentro del request HTTP de Flask** del PATCH del agente ⇒ una publicación lenta bloquea una respuesta HTTP que hoy no bloqueaba | MEDIA | Se declara. El claim de F2-bis acota el peor caso a **una** publicación por ejecución. Encolar como `completion_dispatcher` queda **fuera de scope**. |
| R9 | Los post-hooks posteriores (`completion_dispatcher` `app.py:999`, `qa_uat_enqueue` `:1011`) reciben el `final_status` **pre-degradación** (`ticket_status.py:347`) ⇒ pueden sincronizar el tracker como `completed` y encolar una validación E2E de una run cuya épica falló | MEDIA | F4 registra `epic_autopublish` **primero** y F2 degrada la **fila** de inmediato. La limitación del `final_status` congelado se declara y queda fuera de scope. |
| R10 | `recover_stale_running_tickets` (`ticket_status.py:406-470`) **no** llama `on_execution_end` ⇒ no publica | BAJA | Ese camino sólo corrige tickets colgados cuya ejecución **ya** era terminal; si terminó bien, ya pasó por el chokepoint. Se declara como límite conocido. |
| R11 | `post_run_memory.capture_on_completion` (`claude_code_cli_runner.py:1993`) puede capturar un draft de una run cuya épica falló, porque la degradación llega después | BAJA | Se declara en §3. Corregirlo exigiría mover el gate de captura al post-hook: fuera de scope. |
| R12 | El manifest en disco y el evento (`:1975`, `:1984`) quedan con el estado pre-degradación | BAJA | Se declara en §3. Son traza, no fuente de verdad. |

---

## 6. Fuera de scope

- El **timeout de 20 s** del frontend en `/api/agents/run-brief` — **ya arreglado aparte**
  (`frontend/src/api/endpoints.ts:1302-1310`, `{ timeoutMs: 0 }`, + ratchet `plan273RequestTimeout.test.ts`).
- Mejorar la **calidad** del HTML de épica que produce Copilot o Codex (prompt engineering del
  BusinessAgent). Este plan da paridad de mecanismo, no de calidad; F6-bis sólo la **mide**.
- Mover el autopublish a un daemon asíncrono (ver R8).
- Hacer que `_run_post_hooks` recalcule el `final_status` entre hooks (ver R9).
- Hacer que `recover_stale_running_tickets` dispare post-hooks (ver R10).
- Cualquier cambio a `autopublish_epic_from_run` / `publish_issue_from_run`: **no se tocan**.
- El pre-vuelo de intención (`intent_preflight`) y su flag.

---

## 7. Glosario

| Término | Significado |
|---------|-------------|
| **Autopublish** | Crear el work item (Épica/Issue) en el tracker real del operador automáticamente al cerrar la run, sin que el navegador tenga que completar un handshake. |
| **Brief → épica** | Flujo donde el operador escribe un brief en lenguaje natural y el BusinessAgent produce el HTML de una Épica. Entra por `POST /api/agents/run-brief`. |
| **Chokepoint** | Punto único por el que pasan los 3 runtimes. Acá: `ticket_status.on_execution_end` → `_run_post_hooks`. |
| **Post-hook** | Callable registrado con `ticket_status.register_post_hook` (`ticket_status.py:377`), ejecutado al terminar cualquier run, en cualquier runtime. |
| **Brief Pool Ticket** | Ticket local sintético (`ado_id=-1`) que ancla las runs de brief (no existe en el tracker). Se crea en `api/agents.py:778-788`. |
| **One-shot** | Run que cierra al primer resultado (`_ONE_SHOT_ADO_IDS = {-1,-7,-8,-9}`, `claude_code_cli_runner.py:220`), en vez de sesión interactiva. |
| **Sellar (metadata)** | Escribir una clave en `AgentExecution.metadata_dict` (`models.py:315`) como registro idempotente (p. ej. `epic_ado_id`). |
| **Claim** | Reserva **atómica** del derecho a publicar, ganada por un solo `UPDATE ... WHERE ... NOT LIKE` cuyo `rowcount` decide (F2-bis). Distinto del sello: el sello registra el resultado, el claim evita la carrera. |
| **Falla ruidosa** | El fallo degrada la fila **y** el ticket a `needs_review` y queda visible, en vez de terminar `completed` sin haber hecho nada. |
| **Censo por AST de referencias** | Contar módulos que **nombran** el símbolo (`ast.Name` / `ast.ImportFrom` / `ast.Attribute`), no que lo *llamen*. Obligatorio acá: el publicador se invoca por **alias**, así que un censo por `ast.Call` devuelve vacío, y un `grep` cuenta los strings de documentación de `harness_flags.py`. |

---

## 8. Orden de implementación

1. **F0** — tests del defecto, verdes contra el código actual (`2 passed`).
2. **F1** + **F1-bis** — `services/epic_autopublish.py` + el sello de `spawn_epoch` en el runner + los
   12 casos (TDD).
3. **F2** — sellado (9 filas) y degradación en **las 2 capas** + tests 9-13. **No saltear: acá está el
   falso verde.**
4. **F2-bis** — claim atómico + tests 14-16. **Antes de F4**: sin claim, registrar el hook abre la
   ventana de doble publicación en el tracker real.
5. **F3** — borrar el closure del runner (3 rangos, de abajo hacia arriba) + `compileall` + reemplazar
   el censo AST + actualizar `test_speculative_parity.py`. **Antes de F4.**
6. **F4** + **F4-bis** — registrar el hook **primero** en `app.py` + reemplazar el gate 400 + invertir 3
   de los 4 tests de paridad + los 2 casos de la flag OFF.
7. **F5** — test parametrizado por los 3 runtimes (`3 passed`).
8. **F6** + **F6-bis** — registrar y categorizar la flag + telemetría `epic_publish`.
9. **F7** — ratchets (los DOS) + no-regresión de los 12 archivos, por archivo.

> El orden **F3 antes de F4** no es cosmético: invertirlo deja una ventana en la que el closure y el
> hook están vivos a la vez ⇒ **doble publicación en el tracker real del operador** (R1).
> El orden **F2-bis antes de F4** tampoco: sin el claim, dos `on_execution_end` concurrentes sobre la
> misma ejecución publican dos veces (K5).

## 9. Definición de Hecho (DoD)

- [ ] Los 5 KPI (K1-K5) verdes con sus comandos exactos y sus **conteos** (no exit codes).
- [ ] Censo por AST de referencias: **exactamente un** módulo publicador (`services.epic_autopublish`).
- [ ] Los 3 runtimes probados por el mismo camino, `3 passed`.
- [ ] `compileall` de `services/claude_code_cli_runner.py` exit 0 (el `if _runaway_triggered:` sigue vivo).
- [ ] `grep -rn "autopublish_requires_claude_cli" --include=*.py .` (excluyendo `./tests/`, `/venv/`,
      `/.venv/`) = **0 líneas**. Dentro de `backend/tests/` el literal **debe** seguir existiendo.
- [ ] 12 archivos de no-regresión verdes, corridos **por archivo**.
- [ ] Tests nuevos registrados en los **DOS** ratchets, con la sintaxis propia de cada uno.
- [ ] `claude_code_cli`: mismo **estado final observable** (fila + ticket) y misma **metadata sellada**
      (9 claves del contrato de F2, incluidas `epic_baseline_html` / `epic_baseline_rev`).
      **NO** se afirma "byte-idéntico": el manifest y el evento en disco quedan con el estado
      pre-degradación (declarado en §3 y R12).
- [ ] Con `STACKY_EPIC_AUTOPUBLISH_BACKEND=false`, `run_brief` de Epic/Issue devuelve
      `autopublish_disabled` (400) en los 3 runtimes — el rollback por flag sigue siendo ruidoso.
- [ ] Ninguna flag nueva; `STACKY_EPIC_AUTOPUBLISH_BACKEND` sigue en default ON, ahora visible **y
      categorizada** en la UI.
- [ ] Sin `push`. Sin `--no-verify`.
