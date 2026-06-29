# Plan 77 — Issue como épica de un solo ticket: fases (funcional → técnico → implementación) como comentarios idempotentes + color propio

> Estado: PROPUESTO (no implementado). Autor: StackyArchitectaUltraEficientCode. Fecha: 2026-06-29.
> Origen: pedido del operador — "Stacky debe admitir Issues tratados como una épica, pero con dos
> diferencias: (1) color distinto al de las épicas en la UI, y (2) todo ocurre en el MISMO ticket:
> el análisis funcional, el técnico y la implementación se publican como COMENTARIOS en el work item
> del Issue, NO como tickets hijos."
> Implementable por un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) SIN inferir nada.

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

1. Abrir `services/harness_flags.py` y **leer** cómo está declarado un flag bool existente con
   `env_only=False` (por ejemplo el patrón usado por `STACKY_COMMENT_FULL_SCAN_ENABLED`, Plan 52, o
   cualquier `FlagSpec` con `env_only=False`). **Copiar exactamente ese patrón.**
2. Agregar la entrada nueva con:
   - **nombre exacto:** `STACKY_ISSUE_PHASE_COMMENTS_ENABLED`
   - **tipo:** bool
   - **default:** `False`
   - **env_only:** `False` (visible/editable en UI)
   - **categoría:** la misma categoría/keys donde viven los flags de Issues/épica (buscar dónde está
     `STACKY_ISSUE_FROM_BRIEF_ENABLED` si está registrado; si no, usar la categoría "avanzado"/Arnés que
     ya use el panel, confirmando con `_CATEGORY_KEYS` o equivalente).
   - **descripción (string, en español):** "Postea el análisis funcional/técnico/implementación de un
     Issue como comentarios idempotentes en el mismo work item (no crea hijos). Default OFF."
3. Confirmar el **nombre exacto de la función lectora** del módulo (p. ej. `is_enabled(name, default)` o
   `get_bool(name)`); se reusará en F2. Plan 52 usó `harness_flags.is_enabled("...", default=...)`.
4. Agregar en `.env.example`, junto al bloque del Plan 45 (`.env.example:193-194`):
   ```
   # Plan 77 — Comentarios de fase de Issue (funcional/tecnico/implementacion) en el mismo WI. Default OFF.
   # STACKY_ISSUE_PHASE_COMMENTS_ENABLED=false
   ```

#### Test PRIMERO — caso nuevo en `tests/test_harness_flags.py`

`test_issue_phase_comments_flag_registered_default_false`:
- El flag `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` está en el registro.
- Su default es `False`.
- `env_only` es `False` (aparece en la vista de UI; usar la misma aserción que los otros tests del panel
  que verifican visibilidad).

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
```

#### Criterio de aceptación BINARIO
`tests\test_harness_flags.py` pasa 100% (los 23 casos previos + el nuevo).

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
    """Lee el flag STACKY_ISSUE_PHASE_COMMENTS_ENABLED vía harness_flags (default False).
    Usar la función lectora real confirmada en F1 (p. ej. is_enabled)."""
    from services import harness_flags
    return harness_flags.is_enabled("STACKY_ISSUE_PHASE_COMMENTS_ENABLED", default=False)


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
      5. Extrae el HTML (reusa _extract_epic_html; si no hay, usa output crudo) y
         postea vía _post_phase_comment usando _provider_for_ticket (ADO o GitLab).
         Idempotente por marker (si ya existe, _post_phase_comment no re-postea).
      6. Devuelve telemetría: {"phase": fase, "posted": True, "ado_id": ado_id}.

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
        _post_phase_comment(tracker, int(ado_id), phase, clean_html)
        return {"phase": phase, "posted": True, "ado_id": int(ado_id)}
    except Exception as exc:  # noqa: BLE001 — fase nunca tumba el finalizador
        logger.warning("publish_issue_phase_from_run: no fatal err=%s", exc)
        return {"phase": phase, "posted": False, "reason": f"error:{exc}"}
```

> Notas de reuso (verificar antes de codear, ya existen en el mismo módulo):
> `_post_phase_comment` (`tickets.py:6655`) ya distingue provider del puerto vs `AdoClient` legacy y ya
> es idempotente y no-fatal. `_provider_for_ticket` y `_ado_client_for_ticket` ya se usan en
> `publish_issue_from_run` (`tickets.py:6791`). `_extract_epic_html` ya se usa en `_publish_issue_to_ado`
> (`tickets.py:6617`). **No** duplicar ninguna.

#### Test PRIMERO — `tests/test_issue_phase_publisher.py`

Patrón de DB en tests: usar el patrón del repo (db importado a nivel de módulo, sesión real sobre SQLite
de test, lazy imports parcheados en el módulo de origen). Leer un test existente que ya cree `Ticket`
(p. ej. `tests/test_persist_issue_ticket.py`) y copiar su fixture. Mockear el tracker
(`_provider_for_ticket` y/o `_ado_client_for_ticket`) con un fake que registre llamadas a
`post_comment`/`comment_exists`.

Casos exactos:
1. `test_noop_when_flag_off` — flag OFF (monkeypatch `harness_flags.is_enabled` → False); llamar con un
   Issue válido y `agent_type="technical"` → devuelve `None`, **sin** llamar a `post_comment`.
2. `test_noop_when_agent_not_a_phase` — flag ON, `agent_type="business"` → `None`, sin `post_comment`.
3. `test_noop_when_ticket_not_issue` — flag ON, ticket con `work_item_type="Epic"`,
   `agent_type="technical"` → `None`, sin `post_comment`.
4. `test_posts_tecnico_comment_for_technical_agent` — flag ON, ticket Issue (ado_id=9100),
   `agent_type="technical"`, output con HTML → `post_comment` se llamó **una vez** con un texto que
   **contiene** el marker `_ISSUE_PHASE_MARKERS["tecnico"]`; retorno `{"phase":"tecnico","posted":True,...}`.
5. `test_posts_implementacion_for_developer_agent` — igual con `agent_type="developer"` → marker
   `implementacion`.
6. `test_idempotent_when_marker_exists` — fake `comment_exists` devuelve verdadero (ya existe) →
   `post_comment` **NO** se llama; función no rompe.
7. `test_empty_output_returns_not_posted` — output `""` → `{"phase":...,"posted":False,"reason":"empty_output"}`,
   sin `post_comment`.
8. `test_gitlab_provider_path` — fake provider con atributo `name` (rama provider del puerto): se llama
   `post_comment(str(ado_id), marked_html)` (firma del puerto, sin `fmt`), confirmando paridad GitLab.
9. `test_never_raises_on_provider_error` — fake `post_comment` lanza → la función captura, devuelve
   `posted=False`, **no** propaga.

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_issue_phase_publisher.py -q
```
Confirmar que 4, 5 y 8 FALLAN antes (la función no existe).

#### Criterio de aceptación BINARIO
`tests\test_issue_phase_publisher.py` pasa 100% (9 casos verdes).

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

- Implementación (3 puntos de cableado, una llamada cada uno):
  - `Stacky Agents/backend/services/claude_code_cli_runner.py` — en el finalizador, junto al sellado de
    `metadata`, **después** de tener `output` final y **antes** de `_mark_terminal(...)`. (El finalizador
    de épica/issue one-shot vive en `:1281`; el cableado de fase va en la ruta de cierre **normal** del
    runner, que aplica a cualquier `agent_type`, no solo `business`.)
  - `Stacky Agents/backend/services/codex_cli_runner.py` — punto equivalente de cierre normal.
  - `Stacky Agents/backend/agents/base.py` — finalizador del runtime `github_copilot` (la run vía VS
    Code/bridge); punto donde se dispone del `output` final del agente y del `ticket_id`.
- Test: `Stacky Agents/backend/tests/conformance/test_runtime_conformance.py` (**archivo existente**;
  agregar casos) — o, si el patrón de conformance no admite el caso, crear
  `Stacky Agents/backend/tests/test_issue_phase_runtime_parity.py` (**archivo nuevo**).

#### Procedimiento determinista de cableado

En cada finalizador, localizar el bloque que ya arma `metadata` y llama a `_mark_terminal`/equivalente
(grep sugerido por runner: `grep -n "_mark_terminal\|on_execution_end\|def .*final" <archivo>`). Insertar,
gated y no-fatal:

```python
# Plan 77 F3 — Si la run fue de un agente de fase (functional/technical/developer)
# sobre un ticket Issue, postear su salida como comentario de fase en el mismo WI.
# No-op total si el flag está OFF o el ticket no es Issue. Nunca tumba el finalizador.
try:
    from api.tickets import publish_issue_phase_from_run
    _issue_phase = publish_issue_phase_from_run(
        ticket_id=ticket_id,
        agent_type=agent_type,
        output=output,
        project_name=(project_ctx.stacky_project_name if project_ctx else None),
    )
    if _issue_phase is not None:
        metadata["issue_phase"] = _issue_phase
except Exception as _ip_exc:  # noqa: BLE001
    log("warn", f"issue phase publish (no fatal): {_ip_exc}")
```

> Ajustar los nombres locales reales de cada runner: `output`, `ticket_id`, `agent_type`, el objeto de
> proyecto (`project_ctx` o equivalente) y la función de log (`log(...)`/`logger.warning(...)`). **No**
> cambiar la firma del finalizador. El sello `metadata["issue_phase"]` es aditivo (no pisa nada).

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
4. `test_phase_publisher_not_invoked_when_flag_off` — los 3 igualmente llaman a la función (que es no-op
   interno), **o** el espía confirma `None`/no-sello; fijar el contrato elegido en el test.

> Si aislar los finalizadores reales es caro, el conformance puede verificar el **contrato del helper**
> (un solo punto de verdad) + un test de humo por runner que confirme la presencia del cableado
> (importable y llamado). Lo esencial: que el test **falle** si alguno de los 3 runners NO cablea.

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

- Implementación: `Stacky Agents/backend/api/tickets.py` — en el punto de entrada de creación de hijos
  (`create_child_task`; localizar con `grep -n "def create_child_task" tickets.py`). Agregar el guard al
  inicio, **después** de resolver el ticket padre y **antes** de crear nada.
- (Si el flujo épica→hijos del Plan 59 tiene su propio endpoint de publicación de hijos, agregar el mismo
  guard allí; localizar con `grep -rn "children" backend/api/tickets.py` y revisar el publicador de
  `build_epic_children_plan`.)
- Test: `Stacky Agents/backend/tests/test_issue_no_children_guard.py` (**archivo nuevo**).

#### Implementación (diff ilustrativo)

```python
# Plan 77 F4 — Un Issue NO genera tickets hijos: todo su trabajo vive como
# comentarios de fase en el mismo WI. Guard explícito y temprano.
_parent_type = (parent_ticket.work_item_type or "").strip()
if _parent_type == "Issue":
    return jsonify({
        "ok": False,
        "error": "issue_has_no_children",
        "detail": "Un Issue acumula su trabajo como comentarios de fase, no como tickets hijos.",
    }), 400
```

> Usar el nombre real de la variable del ticket padre tal como exista en `create_child_task`. El guard es
> incondicional (no requiere flag): un Issue nunca debe tener hijos, independientemente del flag de fases.

#### Test PRIMERO — `tests/test_issue_no_children_guard.py`

Casos:
1. `test_create_child_task_rejected_for_issue_parent` — padre con `work_item_type="Issue"` → HTTP 400,
   `error == "issue_has_no_children"`, y **no** se llama al creador de WI hijo (mock).
2. `test_create_child_task_allowed_for_epic_parent` — padre `Epic` → el guard NO se dispara (puede fallar
   por otras validaciones; afirmar solo que el error **no** es `issue_has_no_children`).
3. `test_create_child_task_allowed_for_feature_parent` — padre `Feature`/`User Story` → idem (guard no
   dispara).

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_issue_no_children_guard.py -q
```

#### Criterio de aceptación BINARIO
`tests\test_issue_no_children_guard.py` pasa 100% (3 casos). No-regresión:
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
  - `Stacky Agents/frontend/src/pages/TicketBoard.tsx` — donde hoy distingue `isEpic` (`:253`), usar el
    helper para el color del badge/tipo (sin romper la lógica `isEpic` existente).
  - `Stacky Agents/frontend/src/pages/SprintBoardPage.tsx` — `:84` muestra `item.work_item_type`; aplicar
    color con el helper.
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
| R1 | Colisión del marker `funcional`: brief→Issue ya postea `funcional` (business); luego el agente `functional` queda idempotente-skipped y su análisis no aparece | Media | **Documentado y aceptado:** para Issues brief-originados el output de `business` ES la fase funcional. Para Issues creados manualmente, el operador corre los 3 agentes y obtiene las 3 fases. Si en el futuro se quiere separar, se agrega un 4º marker; fuera de scope. |
| R2 | El hook de fase dispara para tickets que no deberían (p. ej. una épica con `work_item_type` raro) | Baja | Guard estricto `work_item_type == "Issue"` + `agent_type` mapeado + flag OFF por default. Tests F2 casos 2/3. |
| R3 | Cablear 3 finalizadores introduce divergencia entre runtimes | Media | Toda la lógica vive en UNA función (`publish_issue_phase_from_run`); los runners solo la invocan. Conformance test F3 falla si algún runner no cablea. |
| R4 | El finalizador de Copilot (`base.py`) no tiene `ticket_id`/`output` en el mismo shape | Media | F3 instruye localizar los nombres reales por runner; el helper recibe primitivos (`ticket_id:int`, `output:str`), agnóstico del shape interno. Si Copilot no expone `output` en el finalizador, degradar: cablear donde sí esté disponible y documentarlo (el conformance test marca el faltante). |
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
- [ ] `STACKY_ISSUE_PHASE_COMMENTS_ENABLED` registrado bool default False `env_only=False`; entrada en
      `.env.example`; `tests\test_harness_flags.py` verde con el caso nuevo (F1).
- [ ] `tests\test_issue_phase_publisher.py` — 9 verdes, incluyendo rama GitLab y no-fatal (F2).
- [ ] Los 3 finalizadores (`claude_code_cli_runner.py`, `codex_cli_runner.py`, `agents/base.py`) invocan
      `publish_issue_phase_from_run`; conformance/paridad verde y falla si se quita un cableado (F3).
- [ ] `tests\test_issue_no_children_guard.py` — 3 verdes; `create_child_task` rechaza padres Issue (F4).
- [ ] `frontend/src/utils/workItemTypeColor.ts` creado y aplicado en TicketBoard/SprintBoard/Unblocker
      (+ ExecutionHistory si aplica); `tsc --noEmit` limpio (F5).
- [ ] Tests nuevos registrados en `HARNESS_TEST_FILES` (sh + ps1); meta-test de cobertura verde (F6).
- [ ] No-regresión: `tests\test_epic_autopublish_backend.py`, `tests\test_publish_issue.py`,
      `tests\test_issue_from_brief_contract.py` verdes.
- [ ] Con `STACKY_ISSUE_PHASE_COMMENTS_ENABLED=false` (default), el comportamiento es **byte-idéntico** al
      actual en los 3 runtimes.
- [ ] Trabajo del operador: ninguno (opt-in vía flag por UI; default OFF).
