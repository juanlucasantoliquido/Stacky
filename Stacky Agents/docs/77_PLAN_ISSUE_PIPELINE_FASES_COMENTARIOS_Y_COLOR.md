# Plan 77 — Issue como épica de un solo ticket: fases (funcional → técnico → implementación) como comentarios idempotentes + color propio

> Estado: PROPUESTO (no implementado). Autor: StackyArchitectaUltraEficientCode. Fecha: 2026-06-29.
> **Versión: v3** (v3 2026-06-30: pre-flight resuelve ambigüedades de F3 y F6 — ubicaciones
> archivo:línea exactas de los 3 finalizadores y ruta correcta del ratchet, antes de implementar).
> Origen: pedido del operador — "Stacky debe admitir Issues tratados como una épica, pero con dos
> diferencias: (1) color distinto al de las épicas en la UI, y (2) todo ocurre en el MISMO ticket:
> el análisis funcional, el técnico y la implementación se publican como COMENTARIOS en el work item
> del Issue, NO como tickets hijos."
> Implementable por un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) SIN inferir nada.

---

## Changelog v2 → v3 (pre-flight implementador — 2026-06-30)

> **VEREDICTO v2: APROBADO-CON-CAMBIOS** (v3 cierra las ambigüedades pre-flight).

- **F3 — Ubicaciones exactas de los 3 finalizadores** (v2 decía "localizar con grep"):
  - **Copilot** (`agent_runner.py`): insertar ANTES de la apertura del `with session_scope()` en
    línea ~860 (después de `result.output = pii_masker.unmask(...)` en línea 841), guardar
    `_issue_phase` en variable local, y dentro del bloque de sesión (antes de
    `row.metadata_dict = md` en línea 895) hacer `if _issue_phase: md["issue_phase"] = _issue_phase`.
    Locales: `result.output`, `agent_type`, `ticket_id`,
    `project_ctx.stacky_project_name if project_ctx else None`.
  - **Claude CLI** (`services/claude_code_cli_runner.py`): insertar ANTES de `_mark_terminal`
    en línea ~1521, dentro del bloque `elif _outcome_kind == "success":` (~1482). Locales:
    `output`, `agent_type`, `ticket_id`, `project_name` (ya computado en línea 475 como
    `project_ctx.stacky_project_name if project_ctx else None`). Usar `metadata` (dict local).
  - **Codex CLI** (`services/codex_cli_runner.py`): insertar ANTES de `_mark_terminal` en
    línea ~937, dentro del bloque `if return_code == 0:` (~749). Locales: `output`, `agent_type`,
    `ticket_id`, `metadata`. Para `project_name` usar `_codex_project_name` (ya computado en
    línea 338 como `project_ctx.stacky_project_name if project_ctx else None`) — NO `None`.
  - El directorio `tests/conformance/` NO existe: usar la opción del archivo nuevo
    `tests/test_issue_phase_runtime_parity.py`.
- **F6 — Ruta correcta del ratchet**: el archivo es `scripts/run_harness_tests.sh` (bajo
  `backend/scripts/`, NO `backend/tests/`). Los archivos `.ps1` no existen — solo editar el `.sh`.
  El meta-test a correr es `tests/test_harness_ratchet_meta.py`.

---

## Changelog v1 → v2 (crítica del juez aplicada)

> **VEREDICTO v1: RECHAZADO** (3 hallazgos BLOQUEANTES verificados contra el código real). v2 los resuelve.

- **C1 (BLOQUEANTE) — Reader de flag inexistente.** F1/F2 v1 leían el flag con
  `harness_flags.is_enabled(...)`, función que **no existe** en `services/harness_flags.py`, y citaban un
  ancla falsa ("Plan 52 usó `harness_flags.is_enabled`"): `STACKY_COMMENT_FULL_SCAN_ENABLED` se lee con
  `os.getenv` (`harness_flags.py:1492`). Los flags **UI-editables** (`env_only=False`) se leen como
  **atributos de `Config`** (`config.<FLAG>`), p. ej. `tickets.py:6829` (`_cfg.STACKY_EPIC_FROM_BRIEF_ENABLED`)
  y `claude_code_cli_runner.py:1291` (`config.STACKY_ISSUE_FROM_BRIEF_ENABLED`). **v2:** el reader es
  `from config import config; return bool(config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED)`. Barrido de todo
  el doc para erradicar `is_enabled`.
- **C2 (BLOQUEANTE) — Falta el registro en `_CATEGORY_KEYS` (rompe CI).** `harness_flags.py:184-185`
  exige: *toda flag nueva debe agregarse también a `_CATEGORY_KEYS` o el test
  `test_every_registry_flag_is_categorized` rompe CI a propósito (Plan 63)*. v1 trataba la categoría como
  opcional y perseguía una key inexistente (`STACKY_ISSUE_FROM_BRIEF_ENABLED`; la real es
  `STACKY_EPIC_FROM_BRIEF_ENABLED`, en la tupla `epicas_ado`). **v2:** F1 agrega
  `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` a la tupla `epicas_ado` de `_CATEGORY_KEYS` (paso obligatorio) y
  el test afirma la categorización.
- **C3 (BLOQUEANTE) — Guard F4 sobre variable fantasma.** `create_child_task(ado_id: int)`
  (`tickets.py:3819`) trabaja con `ado_id` (int) + `pending-task.json`; **no** tiene ninguna variable
  `parent_ticket`. El diff v1 (`parent_ticket.work_item_type`) es inimplementable. **v2:** el guard usa un
  lookup real del `Ticket` por `ado_id` (o el preflight de tipo de padre que ya existe en
  `tickets.py:3072/3359`), y se elimina el segundo sitio vago ("grep del endpoint del Plan 59"):
  `create_child_task` es el ÚNICO creador de hijos ADO (único `create_work_item` de Task con
  Hierarchy-Reverse).
- **C4 (IMPORTANTE) — Cableado F3 con shapes equivocados por runner + sitio Copilot incorrecto.** El diff
  único de v1 (`ticket_id`, `agent_type`, `output`, `project_ctx`) **solo** existe tal cual en
  `claude_code_cli_runner.py`. `codex_cli_runner.py` tiene `output`/`agent_type`/`ticket_id` pero **no**
  `project_ctx`. `agents/base.py` es la **clase del agente** (`run()` devuelve
  `AgentResult(output=response.text)` con `self.type`/`ctx.stacky_project_name`): **no** es el finalizador,
  no tiene `_mark_terminal` ni esos locales. **v2:** tabla de mapeo por runner con locales verificados,
  `project_name=None` donde no hay `project_ctx` (el helper lo recupera del ticket), y el sitio Copilot
  correcto (el **llamador** de `base.Agent.run`, no `base.py`).
- **C5 (IMPORTANTE) — Contradicción interna en el conformance F3.** v1 exigía "falla si se quita el
  cableado de cualquiera de los 3" **y** a la vez permitía a Copilot "degradar y documentar". **v2:** se
  fija UNA regla — los 3 deben cablear (verificando el contrato compartido del helper por runner); se
  elimina la cláusula de degradación.
- **C6 (IMPORTANTE) → [ADICIÓN ARQUITECTO] — Pérdida silenciosa por colisión del marker `funcional`.** v1
  "aceptaba" que el `business` de brief→Issue ocupe el marker `funcional` y que un `functional` posterior
  quede idempotente-skipped **sin señal visible** (el operador corre el agente y no ve nada). **v2:**
  `publish_issue_phase_from_run` distingue `posted=True` de `reason="phase_already_present"` (pre-chequeo
  de `comment_exists`) y lo sella en `metadata["issue_phase"]`, dándole al operador una señal perceptible
  ("la fase X ya estaba publicada — no se duplicó") en vez de silencio. Reusa el canal de metadata y
  `comment_exists` existentes; cero trabajo del operador; sin autonomía nueva.
- **C7/C8/C9 (MENORES) —** F5: `TicketBoard.tsx:447` usa `isEpic` para *render* (no solo color) y
  `SprintBoardPage.tsx:84` hoy **no** tiene elemento de color (hay que envolver el tipo en un `<span>`, no
  "reemplazar un inline inexistente"); barrido de `is_enabled` residual; y el test de F2 afirma el
  fallback a `output` crudo cuando `_extract_epic_html` no encuentra bloque épica (salida `technical`).

---

## 1. Título, objetivo y KPI / impacto

**Objetivo (1 frase):** Completar el soporte de Issues para que un Issue acumule sus tres fases de
trabajo —**funcional → técnico → implementación**— como **comentarios idempotentes en el MISMO work
item** (sin tickets hijos), reutilizando el pipeline de agentes existente (`functional`, `technical`,
`developer`), con **paridad real en los 3 runtimes** y en **ADO + GitLab**, y dándole al Issue un
**color propio** perceptible en toda la UI.

**Por qué es valioso:** Hoy el soporte de Issues está a medio camino. El substrato ya existe (Plan 45
creó la creación del WI Issue y el comentario idempotente; Plan 52 endureció idempotencia y
observabilidad; Plan 70 lo hizo provider-agnóstico), **pero solo se postea UN comentario de fase
"funcional"** con la salida del `business` agent (`tickets.py:6789-6794`). Las fases técnica e
implementación —que el operador pide explícitamente— **nunca se publican**. Y el color del Issue solo
existe en una pantalla (`UnblockerPage.tsx:240`), invisible en el resto.

**KPI / impacto medible:**

| KPI | Hoy | Post-plan |
|---|---|---|
| **K1** — Fases publicables como comentario en un Issue | 1 (`funcional`) | 3 (`funcional`, `tecnico`, `implementacion`) |
| **K2** — Tickets hijos creados por un Issue | indefinido (sin guard) | **0** (guard explícito) |
| **K3** — Runtimes que publican comentarios de fase del Issue | 1 (Claude CLI, vía one-shot) | **3** (Codex, Claude, Copilot) con conformance test |
| **K4** — Providers de tracker soportados para fases del Issue | ADO + GitLab (ya provider-aware) | ADO + GitLab (con test que lo fija) |
| **K5** — Pantallas de la UI donde el Issue tiene color propio | 1 | ≥4 (helper compartido) |
| **K6** — Comentarios de fase duplicados al re-correr un agente | (no aplicaba) | **0** (idempotencia por marker, ya existente) |

**Costo de tokens del plan:** marginal. No agrega generación LLM nueva: reusa los agentes que el
operador ya corre. El plan agrega una función pura (mapper), un helper de publicación que reusa
`_post_phase_comment` (ya escrito), 3 cableados de una línea, un guard, un flag y un helper de color de
frontend.

---

## 2. Por qué ahora / gap que cierra (anclado en código real)

Hallazgos verificados (rutas `archivo:línea` reales del repo):

**(G1) ALTO — Solo se publica la fase "funcional".** `publish_issue_from_run`
(`Stacky Agents/backend/api/tickets.py:6742`) crea el WI Issue y, en `:6789-6794`, postea **un único**
comentario de fase `"funcional"` con la salida del `business` agent. El diccionario de marcadores
`_ISSUE_PHASE_MARKERS` (`tickets.py:6568`) **ya define las 3 fases** (`funcional`, `tecnico`,
`implementacion`) y `_post_phase_comment` (`tickets.py:6655`) **ya escala** a cualquiera de ellas — pero
nadie llama a las fases `tecnico` ni `implementacion`. El comentario del propio Plan 45
(`tickets.py:6564-6567`) lo dice textual: "Si en el futuro se encadenan fases
(funcional→técnico→implementación como runs separadas), cada una usa su marker y `_post_phase_comment`
escala sin cambios." **Este plan implementa ese futuro.**

**(G2) ALTO — La cadena de fases corre, pero su salida NO va al Issue.** El operador ya dispone de los
agentes `functional`, `technical` y `developer` (registrados en
`Stacky Agents/backend/agents/__init__.py:10-22`, con `type` exacto en
`agents/functional.py:5`, `agents/technical.py:5`, `agents/developer.py:5`). Hoy, cuando el operador
corre esos agentes sobre un ticket, su salida **no se publica como comentario de fase del Issue**: no
hay ningún hook que, al cerrar la run de un agente sobre un ticket cuyo `work_item_type == "Issue"`,
postee el output como su comentario de fase. La publicación automática (`_maybe_autopublish_epic`,
`claude_code_cli_runner.py:1281`) solo dispara para el one-shot `business` (`:1284`), no para
`functional`/`technical`/`developer`.

**(G3) MEDIO — Sin garantía de "no hijos".** El operador exige que un Issue **no** genere tickets hijos.
Hoy nada impide que el operador descomponga un Issue en hijos vía el flujo épica→hijos (Plan 59) o
`create_child_task`. Falta un guard explícito.

**(G4) MEDIO — Color del Issue solo en una pantalla.** El color ámbar `#F59E0B` para Issue está
hardcodeado inline **solo** en `Stacky Agents/frontend/src/pages/UnblockerPage.tsx:240`.
`TicketBoard.tsx:253` distingue `isEpic` pero **no** Issue; `SprintBoardPage.tsx:84` muestra el tipo sin
color. No hay un helper compartido → el Issue es visualmente indistinguible de una épica en las vistas
principales.

**(G5) BAJO — Paridad de runtimes no fijada por test para fases.** El posteo de comentarios de fase debe
funcionar en los 3 runtimes (a diferencia de la *creación* del WI Issue, que sigue siendo Claude-only
por la guarda del Plan 52, `agents.py:600`). Postear un comentario es operación liviana y tolerante
(no exige el contrato HTML-solo que bloqueó la Opción B del Plan 52), así que **sí** puede tener
paridad real; falta un conformance test que lo garantice.

---

## 3. Principios y guardarraíles (codificados en el plan)

- **P1 — Reusar, no reinventar.** Todo el plan se apoya en piezas ya escritas: `_ISSUE_PHASE_MARKERS`
  (`tickets.py:6568`), `_post_phase_comment` (`tickets.py:6655`, idempotente + provider-aware),
  `_provider_for_ticket`, `_extract_epic_html`. La lógica nueva es un mapper puro + un helper delgado +
  cableado.
- **P2 — Paridad de 3 runtimes (real, con conformance).** El helper de publicación de fase se cablea en
  los finalizadores de los 3 runtimes (`agents/base.py` = Copilot, `services/claude_code_cli_runner.py`,
  `services/codex_cli_runner.py`). Un conformance test lo fija. Provider-agnóstico (ADO + GitLab).
- **P3 — Cero trabajo extra al operador.** El operador ya corre `functional`/`technical`/`developer`
  sobre el ticket; el plan hace que esas salidas aterricen solas como comentarios de fase. No agrega
  pasos. Opt-in vía flag **default OFF**: con el flag OFF, el comportamiento es **byte-idéntico** al
  actual.
- **P4 — Human-in-the-loop intacto.** No hay auto-encadenamiento de agentes ni autonomía nueva: **el
  operador dispara cada fase** (corre funcional, luego técnico, luego desarrollo). El plan solo enruta
  la salida que el operador ya genera. [[human-in-the-loop-fundamental]]
- **P5 — Mono-operador sin auth.** Sin RBAC, sin roles, sin login. [[stacky-no-auth-substrate]]
- **P6 — No degradar.** El path de épica y el de creación del WI Issue quedan intactos. Toda la lógica
  nueva está aislada por flag y por el chequeo `work_item_type == "Issue"`. Backward-compatible.
- **P7 — Toda config por UI.** El flag nuevo se registra en `services/harness_flags.py` con
  `env_only=False` para que aparezca y se edite en el `HarnessFlagsPanel` (regla de operador),
  default OFF. [[operator-config-always-via-ui]]
- **P8 — TDD: tests PRIMERO en cada fase.** Correr **por archivo** con el python del `.venv`
  (la suite completa tiene contaminación conocida). [[stacky-backend-test-suite-pollution]]

### Decisión de diseño central (anti-ambigüedad para el implementador)

El operador describe el flujo del Issue como **secuencial**: "arrancará el análisis funcional, luego el
técnico, luego el desarrollo". En Stacky eso son **tres agentes distintos** (`functional`, `technical`,
`developer`), no un único `business` produciendo todo. Por lo tanto:

- **NO** se modifica el agente `business` para que emita 3 secciones (rompería la reutilización y bajaría
  la calidad).
- **NO** se auto-encadenan los 3 agentes (violaría human-in-the-loop).
- **SÍ** se agrega un hook en el finalizador per-ticket: cuando un agente `functional`/`technical`/
  `developer` cierra su run sobre un ticket `Issue`, su salida se postea como el comentario de fase
  correspondiente (`funcional`/`tecnico`/`implementacion`), idempotente, en el mismo WI.
- El path **brief→Issue** existente (`publish_issue_from_run`, one-shot `business`, Claude-only) **no se
  toca**: sigue creando el WI Issue con el cuerpo de negocio y su comentario `funcional`. Si el operador
  luego corre el agente `functional`, el marker `funcional` ya existe → idempotente (no duplica). Las
  fases `tecnico` e `implementacion` son las que aportan los nuevos comentarios.

---

## 4. Fases F0..F6

> CWD asumido para los comandos: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`.
> **Python del .venv (comando base, reusado en todas las fases backend):**
> ```
> .venv\Scripts\python.exe -m pytest <archivo_de_test> -q
> ```
> Si `.venv` no existiera, usar el intérprete del proyecto; NO instalar pins rotos
> (pywin32==306 falla en py3.13). Correr SIEMPRE por archivo, nunca `pytest` a secas.
> [[stacky-backend-dev-test-env]]

---

### F0 — Mapper puro `agent_type_to_issue_phase` (cierra parte de G1/G2)

**Objetivo (1 frase):** Una función pura que traduce el `agent_type` de Stacky a la fase del Issue
(`funcional`/`tecnico`/`implementacion`) o `None` si el agente no participa del pipeline del Issue.

**Valor:** Contrato determinista y testeable que desacopla "qué agente corrió" de "qué comentario de
fase postear". Sin efectos secundarios.

#### Archivos exactos

- Implementación: `Stacky Agents/backend/api/tickets.py` — agregar, **junto a** `_ISSUE_PHASE_MARKERS`
  (`tickets.py:6568`), el dict de mapeo y la función pura.
- Test: `Stacky Agents/backend/tests/test_issue_phase_mapper.py` (**archivo nuevo**).

#### Test PRIMERO — `tests/test_issue_phase_mapper.py`

Casos exactos:
1. `test_functional_maps_to_funcional` — `agent_type_to_issue_phase("functional") == "funcional"`.
2. `test_technical_maps_to_tecnico` — `agent_type_to_issue_phase("technical") == "tecnico"`.
3. `test_developer_maps_to_implementacion` — `agent_type_to_issue_phase("developer") == "implementacion"`.
4. `test_business_maps_to_none` — `agent_type_to_issue_phase("business") is None` (el one-shot crea el WI,
   no es una fase de comentario).
5. `test_unknown_maps_to_none` — `agent_type_to_issue_phase("qa") is None` y
   `agent_type_to_issue_phase("debug") is None` y `agent_type_to_issue_phase("") is None` y
   `agent_type_to_issue_phase(None) is None`.
6. `test_case_insensitive` — `agent_type_to_issue_phase("FUNCTIONAL") == "funcional"`.
7. `test_every_phase_value_has_a_marker` — para cada valor devuelto por el mapper (los 3), ese valor es
   una key de `_ISSUE_PHASE_MARKERS` (garantiza que el mapper nunca produzca una fase sin marker).

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_issue_phase_mapper.py -q
```
Confirmar que TODOS fallan antes de implementar (la función no existe).

#### Implementación (diff ilustrativo, junto a `_ISSUE_PHASE_MARKERS` en `tickets.py`)

```python
# Plan 77 F0 — mapeo agent_type → fase del Issue. business NO es una fase de
# comentario (es el one-shot que crea el WI). Agentes fuera del pipeline → None.
_AGENT_TYPE_TO_ISSUE_PHASE: dict[str, str] = {
    "functional": "funcional",
    "technical": "tecnico",
    "developer": "implementacion",
}


def agent_type_to_issue_phase(agent_type: str | None) -> str | None:
    """Traduce el agent_type de Stacky a la fase del Issue, o None si no aplica.

    Plan 77: las tres fases (funcional/tecnico/implementacion) tienen marker en
    _ISSUE_PHASE_MARKERS. business y el resto de agentes → None (no postean fase).
    """
    if not agent_type:
        return None
    return _AGENT_TYPE_TO_ISSUE_PHASE.get(str(agent_type).strip().lower())
```

#### Criterio de aceptación BINARIO
`tests\test_issue_phase_mapper.py` pasa 100% (7 casos verdes).

#### Flag que la protege + default seguro
Ninguno (función pura, sin efectos; no se invoca aún).

#### Impacto por runtime + fallback
Ninguno en esta fase (no cableada).

#### Trabajo del operador: ninguno.

---

### F1 — Flag `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` (registro + UI)

**Objetivo (1 frase):** Registrar el feature-gate que protege todo el comportamiento nuevo, **editable
desde la UI** (HarnessFlagsPanel), default **OFF**.

**Valor:** Backward-compatibility garantizada (OFF = comportamiento idéntico) y control del operador sin
redeploy.

#### Archivos exactos

- Implementación: `Stacky Agents/backend/services/harness_flags.py` — registrar el flag en el
  `FLAG_REGISTRY` (o la estructura que use el módulo) como **bool, default `False`, `env_only=False`**
  (para que aparezca en el panel de flags del arnés).
- Documentación: `Stacky Agents/backend/.env.example` — agregar la entrada comentada (default false).
- Test: extender `Stacky Agents/backend/tests/test_harness_flags.py` (**archivo existente**) con un caso
  que afirme el registro y el default.

#### Procedimiento determinista (sin ambigüedad)

> **[C1/C2 v2] Dos pasos OBLIGATORIOS y verificados contra el código:** (a) el flag se registra en
> `FLAG_REGISTRY` **y** (b) se agrega su key a `_CATEGORY_KEYS`, o el meta-test
> `test_every_registry_flag_is_categorized` **rompe CI a propósito** (`harness_flags.py:184-185`, Plan 63).
> El reader del flag **NO** es `harness_flags.is_enabled` (esa función no existe): un flag con
> `env_only=False` es atributo de `Config` y se lee como `config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED`
> (patrón real: `tickets.py:6829`, `claude_code_cli_runner.py:1291`).

1. Abrir `services/harness_flags.py` y **leer** cómo está declarado un `FlagSpec` bool con
   `env_only=False` (patrón real verificado: el bloque que define `STACKY_EPIC_FROM_BRIEF_ENABLED` y demás
   flags de la categoría `epicas_ado`; ver también el `FlagSpec` con `env_only=False` del Plan 62/63).
   **Copiar exactamente ese patrón.**
2. Agregar la entrada nueva al `FLAG_REGISTRY` con:
   - **nombre exacto:** `STACKY_ISSUE_PHASE_COMMENTS_ENABLED`
   - **tipo:** bool
   - **default:** `False`
   - **env_only:** `False` (visible/editable en UI; lo lee `Config` como atributo)
   - **descripción (string, en español):** "Postea el análisis funcional/técnico/implementación de un
     Issue como comentarios idempotentes en el mismo work item (no crea hijos). Default OFF."
3. **[C2 — OBLIGATORIO] Agregar la key a `_CATEGORY_KEYS`.** Insertar el string
   `"STACKY_ISSUE_PHASE_COMMENTS_ENABLED"` en la tupla `"epicas_ado"` de `_CATEGORY_KEYS`
   (`harness_flags.py:116-130`), junto a `STACKY_EPIC_FROM_BRIEF_ENABLED` / `STACKY_COMMENT_FULL_SCAN_ENABLED`
   (es de la familia Issues/épica). Sin este paso, `test_every_registry_flag_is_categorized` queda ROJO.
4. **[C1] Reader del flag** (se reusará en F2): **NO** usar `harness_flags.is_enabled`. El patrón correcto:
   ```python
   from config import config
   config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED  # bool; env_only=False → atributo de Config
   ```
   Verificá que `Config` expone el atributo nuevo automáticamente (es el mecanismo de `FlagSpec`
   `env_only=False`); si el repo requiere declararlo también en `config.py`, seguí el mismo patrón que
   `STACKY_EPIC_FROM_BRIEF_ENABLED` (buscar con `grep -n "STACKY_EPIC_FROM_BRIEF_ENABLED" config.py`).
5. Agregar en `.env.example`, junto al bloque del Plan 45 (`.env.example:193-194`):
   ```
   # Plan 77 — Comentarios de fase de Issue (funcional/tecnico/implementacion) en el mismo WI. Default OFF.
   # STACKY_ISSUE_PHASE_COMMENTS_ENABLED=false
   ```

#### Test PRIMERO — casos nuevos en `tests/test_harness_flags.py`

`test_issue_phase_comments_flag_registered_default_false`:
- El flag `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` está en `FLAG_REGISTRY`.
- Su default es `False`.
- `env_only` es `False` (visible en UI; usar la misma aserción que los otros tests del panel).
- **[C2] El flag está categorizado:** su key pertenece a alguna tupla de `_CATEGORY_KEYS` (idealmente
  `"epicas_ado"`). Reusar el helper de categorización (`categorize(...)`) o afirmar pertenencia a la tupla.

> No hace falta un caso nuevo dedicado al meta-test: `test_every_registry_flag_is_categorized` (ya
> existente) cubre la garantía global y debe seguir verde tras el paso 3.

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
```

#### Criterio de aceptación BINARIO
`tests\test_harness_flags.py` pasa 100% (todos los casos previos + el nuevo), **incluyendo**
`test_every_registry_flag_is_categorized` verde (prueba el paso 3).

#### Flag que la protege + default seguro
Este ES el flag. Default `False`.

#### Impacto por runtime + fallback
Ninguno (solo registro). Los 3 runtimes lo leerán igual en F2.

#### Trabajo del operador
**Opt-in:** activar `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` desde el HarnessFlagsPanel (o `.env`) para
habilitar las fases del Issue. Sin eso, todo idéntico a hoy.

---

### F2 — Helper `publish_issue_phase_from_run` (provider-agnóstico, idempotente, gated)

**Objetivo (1 frase):** Una función que, dado un ticket Issue y el agente que corrió, postea la salida
como el comentario de fase correspondiente en el MISMO WI, idempotente, en ADO o GitLab, sin crear hijos.

**Valor:** El núcleo de G1/G2. Concentra toda la lógica nueva en una función testeable que los 3
finalizadores invocan con una línea (F3).

#### Archivos exactos

- Implementación: `Stacky Agents/backend/api/tickets.py` — agregar la función **después de**
  `publish_issue_from_run` (`tickets.py:6742-6814`).
- Test: `Stacky Agents/backend/tests/test_issue_phase_publisher.py` (**archivo nuevo**).

#### Contrato exacto

```python
def _issue_phase_comments_enabled() -> bool:
    """[C1 v2] Lee el flag STACKY_ISSUE_PHASE_COMMENTS_ENABLED como atributo de Config
    (env_only=False → atributo de Config; NO existe harness_flags.is_enabled)."""
    from config import config
    return bool(getattr(config, "STACKY_ISSUE_PHASE_COMMENTS_ENABLED", False))


def _marker_already_present(tracker, ado_id: int, phase: str) -> bool:
    """[ADICIÓN ARQUITECTO / C6] ¿Ya existe el comentario de esta fase?

    Pre-chequeo para distinguir 'posteado ahora' de 'ya estaba' y darle al
    operador una señal visible (en vez del skip silencioso de _post_phase_comment).
    Reusa el marker y la firma provider-vs-AdoClient del módulo. No-fatal.
    """
    marker = _ISSUE_PHASE_MARKERS.get(phase)
    if not marker:
        return False
    is_provider = isinstance(getattr(tracker, "name", None), str)
    try:
        return bool(tracker.comment_exists(str(ado_id) if is_provider else ado_id, marker))
    except Exception:  # noqa: BLE001 — pre-chequeo nunca rompe
        return False


def publish_issue_phase_from_run(
    *,
    ticket_id: int,
    agent_type: str | None,
    output: str | None,
    project_name: str | None,
) -> dict | None:
    """Plan 77 F2 — Postea la salida de un agente de fase como comentario del Issue.

    Reglas (en orden, short-circuit):
      1. Si el flag STACKY_ISSUE_PHASE_COMMENTS_ENABLED está OFF → None (no-op).
      2. Si agent_type no mapea a una fase (business/qa/...) → None (no-op).
      3. Carga el Ticket por ticket_id; si no existe o work_item_type != "Issue"
         o no tiene ado_id válido (>0) → None (no-op).
      4. Si output vacío → {"phase": fase, "posted": False, "reason": "empty_output"}.
      5. Extrae el HTML (reusa _extract_epic_html; si no hay, usa output crudo).
         [ADICIÓN ARQUITECTO/C6] Pre-chequea el marker: si ya existe →
         {"phase": fase, "posted": False, "reason": "phase_already_present"}
         (señal visible para el operador, sin duplicar).
      6. Postea vía _post_phase_comment usando _provider_for_ticket (ADO o GitLab),
         idempotente por marker; devuelve {"phase": fase, "posted": True, "ado_id": ado_id}.

    NUNCA lanza: cualquier excepción se captura y se devuelve telemetría con error.
    No crea tickets hijos (solo comentarios en el WI del Issue).
    """
    if not _issue_phase_comments_enabled():
        return None
    phase = agent_type_to_issue_phase(agent_type)
    if phase is None:
        return None
    try:
        from db import session_scope
        from models import Ticket
        with session_scope() as session:
            t = session.query(Ticket).filter(Ticket.id == ticket_id).first()
            if t is None:
                return None
            wi_type = (t.work_item_type or "").strip()
            ado_id = t.ado_id
            proj = project_name or t.stacky_project_name or t.project or None
        if wi_type != "Issue" or not ado_id or int(ado_id) <= 0:
            return None
        if not output or not str(output).strip():
            return {"phase": phase, "posted": False, "reason": "empty_output"}
        clean_html = _extract_epic_html(output) or output
        tracker = _provider_for_ticket(project_name=proj) or _ado_client_for_ticket(project_name=proj)
        # [ADICIÓN ARQUITECTO/C6] señal explícita de idempotencia (no silenciosa).
        if _marker_already_present(tracker, int(ado_id), phase):
            return {"phase": phase, "posted": False, "reason": "phase_already_present",
                    "ado_id": int(ado_id)}
        _post_phase_comment(tracker, int(ado_id), phase, clean_html)
        return {"phase": phase, "posted": True, "ado_id": int(ado_id)}
    except Exception as exc:  # noqa: BLE001 — fase nunca tumba el finalizador
        logger.warning("publish_issue_phase_from_run: no fatal err=%s", exc)
        return {"phase": phase, "posted": False, "reason": f"error:{exc}"}
```

> Notas de reuso (verificar antes de codear, ya existen en el mismo módulo):
> `_post_phase_comment` (`tickets.py:6655`) ya distingue provider del puerto vs `AdoClient` legacy y ya
> es idempotente y no-fatal. `_provider_for_ticket` (`:394`) y `_ado_client_for_ticket` (`:343`) ya se usan
> en `publish_issue_from_run` (`tickets.py:6791`). `_extract_epic_html` (`:5781`) ya se usa en
> `_publish_issue_to_ado` (`tickets.py:6617`). El marker y la firma `comment_exists(str(id))` (provider) vs
> `comment_exists(id, marker)` (AdoClient) son los mismos de `_post_phase_comment`. **No** duplicar ninguna,
> ni cambiar la firma de `_post_phase_comment` (el pre-chequeo es aditivo).

#### Test PRIMERO — `tests/test_issue_phase_publisher.py`

Patrón de DB en tests: usar el patrón del repo (db importado a nivel de módulo, sesión real sobre SQLite
de test, lazy imports parcheados en el módulo de origen). Leer un test existente que ya cree `Ticket`
(p. ej. `tests/test_persist_issue_ticket.py`) y copiar su fixture. Mockear el tracker
(`_provider_for_ticket` y/o `_ado_client_for_ticket`) con un fake que registre llamadas a
`post_comment`/`comment_exists`.

Casos exactos:
1. `test_noop_when_flag_off` — flag OFF (**[C1]** monkeypatch `api.tickets._issue_phase_comments_enabled`
   → `False`, o `config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED = False`; NO existe `harness_flags.is_enabled`);
   llamar con un Issue válido y `agent_type="technical"` → devuelve `None`, **sin** llamar a `post_comment`.
2. `test_noop_when_agent_not_a_phase` — flag ON, `agent_type="business"` → `None`, sin `post_comment`.
3. `test_noop_when_ticket_not_issue` — flag ON, ticket con `work_item_type="Epic"`,
   `agent_type="technical"` → `None`, sin `post_comment`.
4. `test_posts_tecnico_comment_for_technical_agent` — flag ON, ticket Issue (ado_id=9100),
   `agent_type="technical"`, output con HTML, `comment_exists` → False → `post_comment` se llamó **una vez**
   con un texto que **contiene** el marker `_ISSUE_PHASE_MARKERS["tecnico"]`; retorno
   `{"phase":"tecnico","posted":True,...}`.
5. `test_posts_implementacion_for_developer_agent` — igual con `agent_type="developer"` → marker
   `implementacion`.
6. `test_phase_already_present_returns_not_posted` — **[ADICIÓN ARQUITECTO/C6]** fake `comment_exists`
   devuelve True (el marker ya existe) → `post_comment` **NO** se llama; retorno
   `{"phase":...,"posted":False,"reason":"phase_already_present","ado_id":...}` (señal visible, no silencio).
7. `test_empty_output_returns_not_posted` — output `""` → `{"phase":...,"posted":False,"reason":"empty_output"}`,
   sin `post_comment`.
8. `test_gitlab_provider_path` — fake provider con atributo `name` (rama provider del puerto): `comment_exists`
   se llama con `str(ado_id)` y, si False, `post_comment(str(ado_id), marked_html)` (firma del puerto, sin
   `fmt`), confirmando paridad GitLab.
9. `test_never_raises_on_provider_error` — fake `post_comment` lanza → la función captura, devuelve
   `posted=False` con `reason` `error:...`, **no** propaga.
10. `test_raw_output_fallback_when_not_epic_shaped` — **[C9]** `agent_type="technical"`, output que NO es
    HTML de épica (p. ej. `"<p>análisis técnico</p>"` sin estructura de épica) → `_extract_epic_html`
    devuelve `""` y se postea el `output` crudo: `post_comment` recibe un texto que **contiene** el `output`
    original; `posted=True`. (Garantiza que las fases técnica/implementación no se pierden por no ser
    "épica-shaped".)

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_issue_phase_publisher.py -q
```
Confirmar que 4, 5, 6, 8 y 10 FALLAN antes (la función no existe).

#### Criterio de aceptación BINARIO
`tests\test_issue_phase_publisher.py` pasa 100% (10 casos verdes, incluyendo `phase_already_present`,
rama GitLab, no-fatal y fallback de output crudo).

#### Flag que la protege + default seguro
`STACKY_ISSUE_PHASE_COMMENTS_ENABLED` (F1), default OFF → la función es no-op total.

#### Impacto por runtime + fallback
La función es runtime-agnóstica. Provider-agnóstica: ADO (`AdoClient`) y GitLab (`gitlab_provider`, cuyo
`post_comment`/`comment_exists` existen en `gitlab_provider.py:255` y `:265`). Fallback: si el provider
falla, `posted=False` sin romper.

#### Trabajo del operador: ninguno (la función no se invoca hasta F3).

---

### F3 — Cableado en los 3 finalizadores + conformance de paridad (cierra G2/G5)

**Objetivo (1 frase):** Invocar `publish_issue_phase_from_run` al cerrar la run de un agente en cada uno
de los 3 runtimes, y fijar la paridad con un conformance test.

**Valor:** Hace que la salida de `functional`/`technical`/`developer` aterrice como comentario de fase
**en cualquier runtime** que el operador elija.

#### Archivos exactos

- Implementación (3 puntos de cableado, una llamada cada uno). **[C4 v2] Los locales NO son iguales en los
  3 runners — usar la tabla de mapeo verificada de abajo, no un diff único:**
  - `Stacky Agents/backend/services/claude_code_cli_runner.py` — en la ruta de cierre **normal** del runner
    (la que aplica a cualquier `agent_type`, no solo `business`), **antes** del `_mark_terminal(...)` de
    éxito. Locales verificados disponibles: `output`, `agent_type`, `ticket_id`, `project_ctx`, `metadata`
    (mismo patrón que `_proj = project_ctx.stacky_project_name if project_ctx else None`, `:1307`). **No**
    cablear dentro de `_maybe_autopublish_epic` (`:1281`, solo `business` one-shot).
  - `Stacky Agents/backend/services/codex_cli_runner.py` — ruta de cierre normal (éxito, `return_code == 0`).
    Locales verificados: `output`, `agent_type`, `ticket_id`, `metadata`. **No hay `project_ctx`** → pasar
    `project_name=None` (el helper recupera el proyecto del propio Ticket en F2 paso 3).
  - **[C4 — sitio Copilot corregido]** `agents/base.py` **NO** es el finalizador: `Agent.run()` (`base.py:205`)
    devuelve `AgentResult(output=response.text, ...)` usando `self.type` y `ctx.stacky_project_name` — no
    tiene `_mark_terminal` ni los locales `agent_type`/`ticket_id`/`output`. El finalizador del runtime
    `github_copilot` es el **llamador** de `Agent.run` (el runner/orquestador que consume el `AgentResult`
    y llama a `_mark_terminal`/`on_execution_end`). **Localizarlo** con
    `grep -rn "\.run(" backend/agent_runner.py backend/services` y `grep -rn "_mark_terminal" backend`
    filtrando el path de `github_copilot`; cablear allí, donde están `execution_id`/`ticket_id`/`agent_type`
    y el `output` del `AgentResult`. Mapear los nombres reales según la tabla.
- Test: `Stacky Agents/backend/tests/conformance/test_runtime_conformance.py` (**archivo existente**;
  agregar casos) — o, si el patrón de conformance no admite el caso, crear
  `Stacky Agents/backend/tests/test_issue_phase_runtime_parity.py` (**archivo nuevo**).

#### Procedimiento determinista de cableado (tabla de mapeo por runner) — [C4]

| Runner / archivo | `ticket_id` | `agent_type` | `output` | `project_name` | log |
|---|---|---|---|---|---|
| `claude_code_cli_runner.py` (cierre normal) | `ticket_id` | `agent_type` | `output` | `project_ctx.stacky_project_name if project_ctx else None` | `log("warn", ...)` |
| `codex_cli_runner.py` (cierre normal, rc==0) | `ticket_id` | `agent_type` | `output` | `None` (no hay `project_ctx`) | `log("warn", ...)` |
| Copilot finalizer (**llamador** de `Agent.run`) | nombre real local (`ticket_id`/`row.ticket_id`) | `self.type`/`agent_type` según scope | `result.output` del `AgentResult` | `ctx.stacky_project_name` o `None` | `log`/`logger.warning` |

En cada finalizador, localizar el bloque que arma `metadata` y llama a `_mark_terminal`/`on_execution_end`
(`grep -n "_mark_terminal" <archivo>`). Insertar, gated y no-fatal, **sustituyendo cada celda por el local
real de la tabla** (no copiar `project_ctx` donde no existe):

```python
# Plan 77 F3 — Si la run fue de un agente de fase (functional/technical/developer)
# sobre un ticket Issue, postear su salida como comentario de fase en el mismo WI.
# No-op total si el flag está OFF o el ticket no es Issue. Nunca tumba el finalizador.
try:
    from api.tickets import publish_issue_phase_from_run
    _issue_phase = publish_issue_phase_from_run(
        ticket_id=<TICKET_ID>,          # ver tabla
        agent_type=<AGENT_TYPE>,        # ver tabla
        output=<OUTPUT>,                # ver tabla
        project_name=<PROJECT_NAME>,    # ver tabla; None si el runner no tiene project_ctx
    )
    if _issue_phase is not None:
        metadata["issue_phase"] = _issue_phase
except Exception as _ip_exc:  # noqa: BLE001
    log("warn", f"issue phase publish (no fatal): {_ip_exc}")
```

> **No** cambiar la firma del finalizador. El sello `metadata["issue_phase"]` es aditivo (no pisa nada) y
> transporta `posted`/`reason` (incluido `phase_already_present`, C6) hasta la UI del run.

#### Test PRIMERO — conformance de paridad

Si se usa `test_runtime_conformance.py`, agregar un caso parametrizado por runtime que verifique el
**contrato compartido**: "al cerrar una run de `agent_type='technical'` sobre un ticket `Issue` con el
flag ON, se invoca `publish_issue_phase_from_run` y se sella `metadata['issue_phase']['phase']=='tecnico'`".
Estrategia (sin lanzar procesos reales): parchear `publish_issue_phase_from_run` con un espía y verificar
que **los 3** finalizadores lo invocan con los kwargs correctos (`ticket_id`, `agent_type`, `output`,
`project_name`). Casos:
1. `test_claude_runner_invokes_issue_phase_publisher`
2. `test_codex_runner_invokes_issue_phase_publisher`
3. `test_copilot_runner_invokes_issue_phase_publisher`
4. `test_phase_publisher_not_invoked_when_flag_off` — con flag OFF, los 3 finalizadores **igualmente**
   invocan `publish_issue_phase_from_run` (que es no-op interno y devuelve `None`); el espía confirma
   retorno `None` y que **no** se sella `metadata["issue_phase"]`. (Contrato elegido y fijo: el gating vive
   en el helper, no en el call site — un solo punto de verdad.)

> **[C5 v2] Regla única (sin degradación):** los **3** runners DEBEN cablear. El conformance verifica, por
> runner, que el finalizador invoca `publish_issue_phase_from_run` con los kwargs correctos (espía sobre la
> función; sin lanzar procesos reales). Si aislar el finalizador real de un runner es caro, el test de ese
> runner puede ser de **humo** (confirma import + llamada presente en el path de cierre), pero **debe
> existir para los 3** y **fallar** si a cualquiera le falta el cableado. Queda **eliminada** la cláusula v1
> de "Copilot degrada y se documenta": si el sitio Copilot no se puede cablear correctamente (C4), el plan
> **no** alcanza DoD — no se cierra a medias.

Comando:
```
.venv\Scripts\python.exe -m pytest tests\conformance\test_runtime_conformance.py -q
```
(o `tests\test_issue_phase_runtime_parity.py` si se creó aparte).

#### Criterio de aceptación BINARIO
El archivo de conformance/paridad pasa 100%; falla si se quita el cableado de cualquiera de los 3
runners. No-regresión: correr `tests\test_epic_autopublish_backend.py` y confirmarlo verde.

#### Flag que la protege + default seguro
`STACKY_ISSUE_PHASE_COMMENTS_ENABLED`, default OFF → cableado presente pero no-op.

#### Impacto por runtime + fallback

| Runtime | Antes | Después |
|---|---|---|
| `claude_code_cli` | fases no se publican | publica comentario de fase (flag ON, ticket Issue) |
| `codex_cli` | fases no se publican | **idem** (paridad real) |
| `github_copilot` | fases no se publican | **idem** (paridad real) |

Fallback: cualquier error → `log warn` + run continúa; con flag OFF, no-op.

#### Trabajo del operador: ninguno (corre los agentes que ya corría).

---

### F4 — Guard "un Issue NO crea hijos" (cierra G3)

**Objetivo (1 frase):** Impedir explícitamente que un work item `Issue` se descomponga en tickets hijos
(ni vía `create_child_task` ni vía el flujo épica→hijos del Plan 59).

**Valor:** Encoda el requisito duro del operador ("todo en el mismo ticket, sin hijos") y previene que
coexistan dos mecanismos (comentarios vs hijos) sobre el mismo Issue.

#### Archivos exactos

- Implementación: `Stacky Agents/backend/api/tickets.py` — en `create_child_task(ado_id: int)`
  (`tickets.py:3819`). **[C3 v2]** Esta función trabaja con `ado_id` (int) + `pending-task.json`: **NO
  existe** ninguna variable `parent_ticket`. El guard se agrega temprano (tras parsear el body, antes de
  crear el WI) cargando el padre por `ado_id`.
- **[C3] Sitio único — sin segundo guard vago.** `create_child_task` es el **único** creador de hijos ADO
  (único `create_work_item` de Task con `Hierarchy-Reverse`, `tickets.py:3471`/`:3824`). El flujo épica→hijos
  (Plan 59) **produce un plan**, no crea WIs por su cuenta. Verificación obligatoria (una vez, no editar):
  `grep -rn "create_work_item" backend/api/tickets.py` debe confirmar que toda creación de Task pasa por
  `create_child_task`. Se elimina la instrucción v1 de "agregar el mismo guard en el endpoint del Plan 59".
- Test: `Stacky Agents/backend/tests/test_issue_no_children_guard.py` (**archivo nuevo**).

#### Implementación (diff ilustrativo) — [C3]

```python
# Plan 77 F4 — Un Issue NO genera tickets hijos: todo su trabajo vive como
# comentarios de fase en el mismo WI. Guard explícito y temprano.
# create_child_task recibe `ado_id` (id ADO del padre) — NO un objeto ticket;
# se carga el padre local para leer su work_item_type.
from db import session_scope          # ya importado a nivel de módulo en tickets.py
from models import Ticket             # idem
with session_scope() as _guard_sess:
    _parent = _guard_sess.query(Ticket).filter(Ticket.ado_id == ado_id).first()
    _parent_type = (_parent.work_item_type or "").strip() if _parent is not None else ""
if _parent_type == "Issue":
    return jsonify({
        "ok": False,
        "error": "issue_has_no_children",
        "detail": "Un Issue acumula su trabajo como comentarios de fase, no como tickets hijos.",
    }), 400
```

> `session_scope` y `Ticket` ya se usan en todo `tickets.py` (no agregar imports nuevos si ya están a nivel
> de módulo). Alternativa equivalente: reusar el **preflight de tipo de padre** que ya lee el WI del padre
> desde ADO (`tickets.py:3072`/`:3359`, "no pudo leer tipo del padre ADO-…") y rechazar si es "Issue"; si se
> elige esta vía, ubicar el guard **después** de ese preflight. El guard es incondicional (no requiere
> flag): un Issue nunca tiene hijos, independientemente del flag de fases.

#### Test PRIMERO — `tests/test_issue_no_children_guard.py`

> **[C3] Setup:** el guard lee el padre de la BD local por `ado_id`. Cada caso **persiste** un `Ticket`
> (mismo fixture de `tests/test_persist_issue_ticket.py`) con `ado_id=<N>` y el `work_item_type` del caso,
> luego hace `POST /tickets/<N>/child-task` (usar la ruta real; confirmar con
> `grep -n "child-task\|create_child_task" backend/api/tickets.py`). Mockear el creador de WI hijo
> (`AdoClient.create_work_item`) para afirmar que **no** se invoca cuando el guard dispara.

Casos:
1. `test_create_child_task_rejected_for_issue_parent` — `Ticket(ado_id=N, work_item_type="Issue")`
   persistido → HTTP 400, `error == "issue_has_no_children"`, y `create_work_item` **no** se llamó.
2. `test_create_child_task_allowed_for_epic_parent` — `Ticket(ado_id=N, work_item_type="Epic")` → el guard
   NO dispara (puede fallar por otras validaciones; afirmar solo que el error **no** es
   `issue_has_no_children`).
3. `test_create_child_task_allowed_for_feature_parent` — `work_item_type="Feature"`/`"User Story"` → idem
   (guard no dispara).
4. `test_create_child_task_no_local_parent_does_not_block` — sin `Ticket` local para ese `ado_id`
   (`_parent is None` → `_parent_type == ""`) → el guard NO dispara (no rechaza por ausencia de padre
   local; deja que las validaciones existentes sigan su curso). Evita falsos 400.

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_issue_no_children_guard.py -q
```

#### Criterio de aceptación BINARIO
`tests\test_issue_no_children_guard.py` pasa 100% (4 casos, incl. padre local ausente). No-regresión:
`tests\test_create_child_task_endpoint.py` y `tests\test_create_child_task_gate.py` siguen verdes.

#### Flag que la protege + default seguro
Ninguno (invariante de dominio, siempre activo). Backward-compatible: hoy nadie crea hijos de un Issue a
propósito.

#### Impacto por runtime + fallback
Independiente del runtime (validación de API). Sin fallback: es un rechazo determinista.

#### Trabajo del operador: ninguno.

---

### F5 — Frontend: helper compartido `workItemTypeColor` y color del Issue en toda la UI (cierra G4)

**Objetivo (1 frase):** Un único helper de color por `work_item_type` (Issue ≠ Epic) aplicado en las
vistas principales, eliminando el color inline disperso.

**Valor:** El Issue es perceptiblemente distinto de la épica en todas las pantallas, no solo en
UnblockerPage.

#### Archivos exactos

- Crear: `Stacky Agents/frontend/src/utils/workItemTypeColor.ts` (**archivo nuevo**).
- Editar (aplicar el helper):
  - `Stacky Agents/frontend/src/pages/UnblockerPage.tsx` — reemplazar el inline `#F59E0B` de `:240` por
    `workItemTypeColor(item.work_item_type)`.
  - `Stacky Agents/frontend/src/pages/TicketBoard.tsx` — `isEpic` (`:253`) además dispara **render**
    condicional en `:447`; **[C7]** NO tocar esa rama. Aplicar el helper SOLO al color del badge/tipo
    (localizar el elemento del badge de tipo y setear su `color`/`style` con `workItemTypeColor(...)`).
  - `Stacky Agents/frontend/src/pages/SprintBoardPage.tsx` — `:84` renderiza `{item.work_item_type}` **sin
    color** hoy; **[C7]** no hay inline que "reemplazar": envolver el tipo en
    `<span style={{ color: workItemTypeColor(item.work_item_type) }}>…</span>`.
  - `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx` — si muestra `work_item_type`, aplicar el
    helper (si no lo muestra, omitir y documentarlo en el PR).

#### Implementación — `frontend/src/utils/workItemTypeColor.ts`

```ts
// Plan 77 F5 — color único por tipo de work item. Issue (ámbar) ≠ Epic (violeta).
export function workItemTypeColor(type: string | null | undefined): string {
  const t = (type ?? "").trim().toLowerCase();
  switch (t) {
    case "epic": return "#7C3AED";        // violeta
    case "issue": return "#F59E0B";       // ámbar — distinto de la épica
    case "bug": return "#DC2626";         // rojo
    case "user story": return "#2563EB";  // azul
    case "feature": return "#9333EA";     // púrpura
    case "task": return "#059669";        // verde
    default: return "#6B7280";            // gris neutro
  }
}
```

> No instalar vitest (no está en el repo); la validación frontend es `tsc --noEmit` + checklist manual,
> como hizo Plan 45 F4. [[stacky-backend-dev-test-env]]

#### Validación

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit
```

#### Criterio de aceptación BINARIO
`tsc --noEmit` sin errores + checklist manual:
- [ ] Un ticket `Issue` muestra color ámbar (#F59E0B) en TicketBoard, SprintBoard y UnblockerPage.
- [ ] Un ticket `Epic` muestra violeta; `Bug` rojo; `Task` verde — sin cambios respecto de hoy.
- [ ] No quedan colores de tipo hardcodeados inline en los archivos editados (todos via helper).

#### Flag que la protege + default seguro
Ninguno (display-only, no altera lógica). Siempre visible.

#### Impacto por runtime + fallback
Solo UI; los 3 runtimes comparten la misma UI.

#### Trabajo del operador: ninguno.

---

### F6 — Ratchet: registrar los tests nuevos en el arnés

**Objetivo (1 frase):** Que los archivos de test nuevos queden registrados en la lista del arnés para que
el meta-test de cobertura (Plan 49 F4) no falle y los tests corran en CI local.

**Valor:** Cumple la regla dura del repo: todo test nuevo del backend va en `HARNESS_TEST_FILES`.
[[stacky-ratchet-obliga-registrar-tests]]

#### Archivos exactos

- `Stacky Agents/backend/tests/run_harness_tests.sh` — agregar a `HARNESS_TEST_FILES` los nuevos:
  `test_issue_phase_mapper.py`, `test_issue_phase_publisher.py`, `test_issue_no_children_guard.py`, y
  (si se creó aparte) `test_issue_phase_runtime_parity.py`.
- `Stacky Agents/backend/tests/run_harness_tests.ps1` — la lista paralela (mismo set).
- (No agregar `test_harness_flags.py` ni `test_runtime_conformance.py`: ya están registrados.)

> Confirmar el nombre real del archivo/lista del arnés con
> `grep -rn "HARNESS_TEST_FILES" backend/tests` antes de editar (puede vivir en
> `tests/harness_ratchet_allowlist.txt` u otro; usar la fuente real).

#### Test / criterio de aceptación BINARIO

Correr el meta-test de cobertura del arnés (Plan 49 F4) y confirmarlo verde:
```
.venv\Scripts\python.exe -m pytest tests\test_harness_test_coverage.py -q
```
(usar el nombre real del meta-test; localizar con `grep -rn "HARNESS_TEST_FILES" backend/tests`).

#### Flag / runtime / operador
N/A. Ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| R1 | Colisión del marker `funcional`: brief→Issue ya postea `funcional` (business); luego el agente `functional` queda idempotente-skipped y su análisis no aparece | Media | **[C6/ADICIÓN]** Ya no es silencioso: `publish_issue_phase_from_run` devuelve `reason="phase_already_present"` y lo sella en `metadata["issue_phase"]`, así el operador VE en el run que la fase ya estaba (no se "perdió" en silencio). Semántica: para Issues brief-originados el `business` ES la fase funcional; para Issues manuales el operador corre los 3 agentes. Separar negocio/funcional técnico = 4º marker, fuera de scope. |
| R2 | El hook de fase dispara para tickets que no deberían (p. ej. una épica con `work_item_type` raro) | Baja | Guard estricto `work_item_type == "Issue"` + `agent_type` mapeado + flag OFF por default. Tests F2 casos 2/3. |
| R3 | Cablear 3 finalizadores introduce divergencia entre runtimes | Media | Toda la lógica vive en UNA función (`publish_issue_phase_from_run`); los runners solo la invocan. Conformance test F3 falla si algún runner no cablea. |
| R4 | El finalizador de Copilot NO es `agents/base.py` (esa es la clase del agente, `run()` devuelve `AgentResult`); el verdadero finalizador es el **llamador** de `Agent.run` y tiene otro shape de locales | Media | **[C4 v2]** F3 corrige el sitio: cablear en el llamador de `Agent.run` (el runner/orquestador `github_copilot` que llama a `_mark_terminal`), no en `base.py`. El helper recibe primitivos (`ticket_id:int`, `output:str`, `project_name:str|None`) → agnóstico del shape. Tabla de mapeo por runner en F3. **Sin degradación** (C5): los 3 deben cablear o no hay DoD. |
| R5 | Comentarios de fase crecen sin límite en Issues longevos | Baja | Idempotencia por marker (`_post_phase_comment` + `comment_exists` paginado, Plan 52 F1): cada fase se postea una sola vez. |
| R6 | GitLab no soporta tipo "Issue" igual que ADO | Baja | `_publish_issue_to_ado` y `_post_phase_comment` ya son provider-aware (Plan 70 F3/F8); `gitlab_provider.post_comment`/`comment_exists` existen. F2 caso 8 fija la rama GitLab. |
| R7 | Suite completa enmascara verdes/rojos | Media | Correr SIEMPRE por archivo con el .venv (P8). [[stacky-backend-test-suite-pollution]] |
| R8 | El flag no aparece en el panel de UI (env_only mal puesto) | Baja | F1 exige `env_only=False` + test que lo afirma; copiar el patrón de un flag ya visible. |

---

## 6. Fuera de scope

- **Modificar el agente `business`** para que emita 3 secciones. Las fases vienen de los agentes
  `functional`/`technical`/`developer` (decisión de diseño §3).
- **Auto-encadenar** los 3 agentes sin intervención del operador (violaría human-in-the-loop). El
  operador dispara cada fase.
- **Crear el WI Issue desde Codex/Copilot.** La *creación* del Issue sigue siendo Claude-only por la
  guarda del Plan 52 (`agents.py:600`); este plan solo da paridad a los *comentarios de fase*.
- **Cuarto marker** para separar el "funcional de negocio" (business) del "funcional técnico"
  (functional). Documentado como extensión futura (R1).
- **Dashboard de Issues** separado del de épicas (el color en las vistas actuales alcanza).
- **Migración de Issues existentes** o reconciliación de comentarios históricos.
- **Tema/configurabilidad del color** por el operador (color fijo por tipo; un selector de colores es UX
  futura).

---

## 7. Glosario, Orden de implementación y DoD

### Glosario de dominio Stacky

- **Issue:** work item ADO/GitLab tipo "Issue". Pipeline idéntico al de la épica (funcional→técnico→
  desarrollo) pero su salida vive como **comentarios en el mismo WI**, sin tickets hijos.
- **fase del Issue:** uno de `funcional` / `tecnico` / `implementacion`. Cada una tiene un marker HTML
  invisible en `_ISSUE_PHASE_MARKERS` (`tickets.py:6568`) que garantiza idempotencia.
- **agent_type:** identificador del agente (`agents/__init__.py:10`): `business`, `functional`,
  `technical`, `developer`, `qa`, `debug`, `pr_review`, `custom`. Solo los 3 del medio mapean a fase.
- **marker idempotente:** comentario HTML (`<!-- stacky:issue-phase:tecnico -->`) que `comment_exists`
  busca para no duplicar (paginado completo, Plan 52 F1).
- **`_post_phase_comment`:** helper provider-aware e idempotente que postea un comentario de fase
  (`tickets.py:6655`).
- **`_provider_for_ticket`:** resuelve el `TrackerProvider` (ADO o GitLab) del proyecto (Plan 70). Si es
  `None`, se cae a `_ado_client_for_ticket` (legacy ADO).
- **autopublish:** publicación autónoma del WI al cerrar el one-shot `business` brief→épica/issue
  (`claude_code_cli_runner.py:1281`, Claude-only). **Distinto** del hook de fases de este plan.
- **harness_flags / FLAG_REGISTRY:** sistema de flags del arnés, editables por UI
  (`services/harness_flags.py`, `HarnessFlagsPanel`). [[operator-config-always-via-ui]]

### Orden de implementación (por dependencia)

1. **F0** — mapper puro (sin dependencias).
2. **F1** — flag en harness_flags + UI + `.env.example`.
3. **F2** — helper `publish_issue_phase_from_run` (usa F0 + F1).
4. **F3** — cableado en 3 finalizadores + conformance (usa F2).
5. **F4** — guard no-hijos (independiente; puede ir en cualquier momento).
6. **F5** — color frontend (independiente del backend; puede ir en paralelo).
7. **F6** — ratchet (al final, tras crear todos los tests).

### Definición de Hecho (DoD) global

- [ ] `tests\test_issue_phase_mapper.py` — 7 verdes (F0).
- [ ] `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` en `FLAG_REGISTRY` (bool, default False, `env_only=False`) **y**
      en la tupla `epicas_ado` de `_CATEGORY_KEYS` (C2); reader vía `config.<FLAG>` (C1, NO `is_enabled`);
      entrada en `.env.example`; `tests\test_harness_flags.py` verde, incl. `test_every_registry_flag_is_categorized` (F1).
- [ ] `tests\test_issue_phase_publisher.py` — 10 verdes, incluyendo `phase_already_present` (C6), rama
      GitLab, no-fatal y fallback de output crudo (C9) (F2).
- [ ] Los 3 finalizadores invocan `publish_issue_phase_from_run`: `claude_code_cli_runner.py` (cierre
      normal), `codex_cli_runner.py` (cierre normal, `project_name=None`), y el **llamador de `Agent.run`**
      del runtime `github_copilot` (NO `agents/base.py`, C4); conformance/paridad verde y falla si se quita
      un cableado, sin cláusula de degradación (C5) (F3).
- [ ] `tests\test_issue_no_children_guard.py` — 4 verdes (incl. padre local ausente); `create_child_task`
      rechaza padres Issue vía lookup por `ado_id`, sin variable `parent_ticket` (C3) (F4).
- [ ] `frontend/src/utils/workItemTypeColor.ts` creado y aplicado en TicketBoard/SprintBoard/Unblocker
      (+ ExecutionHistory si aplica); `tsc --noEmit` limpio (F5).
- [ ] Tests nuevos registrados en `HARNESS_TEST_FILES` (sh + ps1); meta-test de cobertura verde (F6).
- [ ] No-regresión: `tests\test_epic_autopublish_backend.py`, `tests\test_publish_issue.py`,
      `tests\test_issue_from_brief_contract.py` verdes.
- [ ] Con `STACKY_ISSUE_PHASE_COMMENTS_ENABLED=false` (default), el comportamiento es **byte-idéntico** al
      actual en los 3 runtimes.
- [ ] Trabajo del operador: ninguno (opt-in vía flag por UI; default OFF).
