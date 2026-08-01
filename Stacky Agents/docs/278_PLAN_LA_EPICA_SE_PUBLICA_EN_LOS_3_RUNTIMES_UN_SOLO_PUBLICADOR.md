# Plan 278 — La épica se publica en los 3 runtimes, con UN SOLO publicador

**Estado:** v1 (propuesta)
**Rama:** `docs/plan-278`
**Origen:** defecto reportado en vivo por el operador (2026-08-01).

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
borra el gate que rechazaba.

**KPI binarios:**

| # | KPI | Cómo se mide |
|---|-----|--------------|
| K1 | `POST /api/agents/run-brief` con `work_item_type=Epic` y runtime `github_copilot` o `codex_cli` **no devuelve 400** | `test_run_brief_autopublish_parity.py` invertido (F4) |
| K2 | **Exactamente 1** llamador de producción de `autopublish_epic_from_run` / `publish_issue_from_run` en todo `backend/` | gate por **AST** (F3), no por grep |
| K3 | Los 3 runtimes publican por el **mismo** camino de código | `test_epic_autopublish_runtime_parity.py` parametrizado por runtime (F5) |
| K4 | La flag que gobierna el autopublish es **visible y configurable desde la UI** | `test_harness_flags_registry.py` (F6) |

**Paridad declarada honestamente:** este plan entrega **paridad de MECANISMO**, no de calidad. Si el
modelo de Copilot o Codex devuelve narración en vez del HTML de la épica, el publicador ya falla
RUIDOSO con `epic_not_in_output` → `needs_review` (`api/tickets.py:7310-7318`). Eso es correcto y
estrictamente mejor que el 400 de hoy, pero **el plan no promete que los 3 modelos produzcan épicas de
la misma calidad**. Prohibido escribir en el doc o en un test que la calidad es equivalente.

---

## 2. Por qué ahora / gap que cierra

El gate **no es un bug ni un residuo**: hoy es fácticamente correcto. Verificado abriendo los archivos:

- `autopublish_epic_from_run` (`backend/api/tickets.py:7248`) y `publish_issue_from_run`
  (`backend/api/tickets.py:7695`) tienen **un solo llamador de producción en todo el backend**:
  `backend/services/claude_code_cli_runner.py:1690-1703`, dentro del closure `_maybe_autopublish_epic`
  (definido en `:1675`; invocado en `:1752` y `:1936`).
- Con Copilot o Codex el run correría, gastaría tokens y **no crearía la épica**. El gate cambia ese
  falso verde por un 400 legible antes de gastar. Fue una decisión deliberada del Plan 52 F0.

Lo que cambió es que **el operador exige la paridad real**, y el sustrato para darla ya está construido:

1. **El publicador ya es runtime-agnóstico.** `autopublish_epic_from_run` recibe
   `output / brief / project_name / already_published_id / run_started_at` y parsea con
   `_extract_epic_html` + `_looks_like_epic`. Nada adentro depende del runtime.
2. **El chokepoint ya existe y ya está vivo en los 3.** `ticket_status.on_execution_end`
   (`backend/services/ticket_status.py:293`) corre `_run_post_hooks` (`:349`, definido `:395-400`);
   el registro es `register_post_hook` (`:377`). Lo llaman Claude
   (`claude_code_cli_runner.py:2002`), Codex (`codex_cli_runner.py:1130-1133`) y Copilot in-proc
   (`agent_runner.py:1037-1043`).
3. **Existe el precedente exacto a copiar.** `backend/services/incident_autopublish.py` (53 líneas) es
   un autopublish agnóstico de runtime implementado como post-hook, registrado en `app.py:994`.
4. **El hueco está admitido por escrito en el código.** `backend/agent_runner.py:176-180`:
   *"La autopublicación de Issue vive en el finalizador del runner CLI; este path (github_copilot) no
   autopublica, pero igual deja la trazabilidad"*.

Además, hoy **la combinación por default está rechazada de fábrica**: el runtime default de `run_brief`
es `github_copilot` (`api/agents.py:640`) y `work_item_type` normaliza a `Epic`, así que el operador
que no toca nada choca contra el 400. El propio test lo congela
(`test_run_brief_epic_default_runtime_copilot_returns_400`).

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad.** El publicador único corre en el post-hook, que los 3 disparan. Sin ramas
  `if runtime == ...` en el camino de publicación. Fallback: si el output no es una épica, falla
  ruidoso a `needs_review` — igual en los 3.
- **Cero trabajo extra al operador.** No hay pasos manuales nuevos, ni config nueva obligatoria. El
  comportamiento para `claude_code_cli` queda **byte-idéntico** (mismo publicador, mismo sellado de
  metadata, mismo status final). Para Copilot/Codex, lo que antes era un 400 ahora publica.
- **Human-in-the-loop.** No se agrega autonomía nueva: el autopublish desde brief **ya existía y ya era
  automático** para Claude (excepción dura #1, aceptada por directiva del operador — mismo precedente
  citado en `services/incident_autopublish.py:1-4`). Este plan **no amplía la autonomía**, la vuelve
  uniforme entre runtimes. La decisión de generar la épica la sigue tomando el operador al mandar el
  brief.
- **Mono-operador, sin auth real.** Nada de RBAC.
- **Reusar, no reinventar.** Se reusa `autopublish_epic_from_run` / `publish_issue_from_run` tal cual
  (no se tocan), el patrón de `incident_autopublish`, y la flag existente
  `STACKY_EPIC_AUTOPUBLISH_BACKEND`.
- **Sin falsos verdes.** Cada fase trae un gate que se corre **contra el defecto** (rojo antes del fix,
  verde después). El conteo de publicadores se hace por **AST**, nunca por `grep` sobre un closure.

### Flags

| Flag | Default | Nueva | Justificación |
|------|---------|-------|---------------|
| `STACKY_EPIC_AUTOPUBLISH_BACKEND` | **ON** (ya es `true`, `config.py:1054-1055`) | NO — ya existe | Se **reusa**. No cambia de default. F6 solo la **registra** en el arnés para que sea visible/configurable desde la UI (hoy no lo es). |
| `STACKY_ISSUE_FROM_BRIEF_ENABLED` | sin cambios | NO | Se reusa tal cual; sigue gobernando la bifurcación Issue. |

**Este plan no crea ninguna flag nueva.** No hay, por lo tanto, ninguna flag que deba nacer OFF ni
excepción (A)/(B) que citar. La capacidad que escribe en el sistema real del operador —el autopublish—
**ya estaba encendida por default antes de este plan**; el plan no la enciende, la unifica.

---

## 4. Fases

### F0 — Gate contra el defecto: probar que HOY Copilot y Codex no publican

**Objetivo:** dejar en rojo, antes de tocar nada, la afirmación "los 3 runtimes publican".

**Archivo a crear:** `Stacky Agents/backend/tests/test_epic_autopublish_runtime_parity.py`

**Casos:**

1. `test_hoy_solo_claude_tiene_publicador` — **censo por AST** (no grep): parsear con `ast` los módulos
   de `backend/services/` y `backend/` y contar los módulos que contienen una llamada a
   `autopublish_epic_from_run` o `publish_issue_from_run`. Assert: el conjunto de módulos publicadores
   es **exactamente** `{"services.claude_code_cli_runner"}`.
   Este caso **se invierte en F3** (pasa a `{"services.epic_autopublish"}`). Es el KPI K2.
2. `test_post_hook_de_epica_no_esta_registrado` — assert de AUSENCIA **con guarda**: primero verificar
   que `ticket_status._POST_HOOKS` **no está vacío** (si estuviera vacío, el assert de ausencia pasaría
   por accidente y sería un falso verde), y recién entonces assert de que ningún hook registrado se
   llama `maybe_autopublish_epic`.

> **Nota anti-falso-verde (gotcha de la casa):** un assert de ausencia no distingue *"no está porque lo
> sacamos bien"* de *"nunca estuvo / el registro no corrió"*. Por eso el caso 2 exige primero que la
> lista tenga contenido.

**Comando:**
```
"N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest ^
  "Stacky Agents/backend/tests/test_epic_autopublish_runtime_parity.py" -v
```

**Criterio binario:** los 2 casos pasan **contra el código actual, sin ningún cambio de producción**.
Si alguno falla acá, la foto del defecto está mal tomada y hay que corregir el test antes de seguir.

**Flag:** ninguna. **Runtimes:** N/A (test estructural). **Trabajo del operador:** ninguno.

---

### F1 — Extraer el publicador único a un servicio runtime-agnóstico

**Objetivo:** un módulo nuevo que publique la épica/issue sin saber qué runtime corrió, espejo exacto
de `incident_autopublish`.

**Archivo a crear:** `Stacky Agents/backend/services/epic_autopublish.py`

**Símbolos exactos a crear:**
- `maybe_autopublish_epic(*, ticket_id, execution_id, final_status, agent_type, error=None, **_) -> None`
- `register(register_post_hook) -> None`
- `_load_run(execution_id) -> dict | None` (helper interno, testeable solo)

**Discriminador de "esto es un run brief→épica"** (reemplaza al `_one_shot` del runner, que hoy es
`_is_one_shot(t_ado_id)` → `t_ado_id in _ONE_SHOT_ADO_IDS`, `claude_code_cli_runner.py:220-225`):

> `agent_type == "business"` **Y** el `input_context` de la ejecución contiene un bloque con
> `id == "brief"`.

Es equivalente y más preciso: `run_brief` **siempre** inyecta ese bloque
(`api/agents.py:790-798`), y el bloque es además el que provee el argumento `brief=` del publicador
(hoy el runner lo extrae igual, `claude_code_cli_runner.py:1696-1700`). Un chat interactivo del
BusinessAgent no tiene bloque `brief` ⇒ **no publica**. F1 debe traer un test para justamente eso.

**Pseudocódigo:**

```python
def maybe_autopublish_epic(*, ticket_id, execution_id, final_status, agent_type, error=None, **_):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_EPIC_AUTOPUBLISH_BACKEND", True):
        return
    if (agent_type or "").lower() != "business":
        return
    if final_status not in ("completed", "needs_review"):
        return            # estados no terminales o cancelados: nada que publicar

    run = _load_run(execution_id)          # output, metadata, input_context, started_at
    if run is None:
        return
    brief_text = next((str(b.get("content") or "")
                       for b in run["input_context"]
                       if isinstance(b, dict) and b.get("id") == "brief"), None)
    if brief_text is None:
        return            # no es un run brief->épica (chat interactivo): NO publicar

    md = dict(run["metadata"] or {})
    is_issue = (str(md.get("work_item_type") or "Epic") == "Issue"
                and _cfg.STACKY_ISSUE_FROM_BRIEF_ENABLED)
    seal_key = "issue_ado_id" if is_issue else "epic_ado_id"
    if md.get(seal_key):
        return            # ya publicada: idempotente (2a línea de defensa)

    from api.tickets import autopublish_epic_from_run, publish_issue_from_run
    publish = publish_issue_from_run if is_issue else autopublish_epic_from_run
    kwargs = dict(output=run["output"], brief=brief_text,
                  project_name=run["project_name"], already_published_id=md.get(seal_key))
    if not is_issue:
        # Plan 47 F2-bis: ventana temporal del rescate desde disco. Antes salia de
        # `spawn_epoch` del runner; acá se deriva de la fila (models.py:278).
        kwargs["run_started_at"] = run["started_at_epoch"]

    try:
        res = publish(**kwargs)
    except Exception as exc:
        _seal_and_degrade(execution_id, ticket_id, agent_type,
                          error=str(exc), final_status=final_status)
        return
    _apply_result(execution_id, ticket_id, agent_type, res, seal_key, final_status)
```

`_load_run` lee de la fila `AgentExecution` (campos verificados en `backend/models.py`):
`output` (`:272`), `metadata_dict` (property, `:315`), `input_context` (property, `:299`),
`started_at` (`:278`, `datetime` → convertir a epoch float con `.timestamp()`).
`project_name` sale del `Ticket` asociado (`Ticket.stacky_project_name`), igual que hoy hace el runner
vía `project_ctx.stacky_project_name` (`claude_code_cli_runner.py:1701`).

**Tests (TDD, primero):** `Stacky Agents/backend/tests/test_epic_autopublish_service.py`
1. `test_publica_cuando_hay_bloque_brief` (mock de `autopublish_epic_from_run`, assert llamado 1 vez).
2. `test_no_publica_sin_bloque_brief` — chat interactivo del BusinessAgent ⇒ 0 llamadas.
3. `test_no_publica_si_ya_esta_sellado` — `metadata["epic_ado_id"]` presente ⇒ 0 llamadas (idempotencia).
4. `test_no_publica_con_flag_off` — `STACKY_EPIC_AUTOPUBLISH_BACKEND=False` ⇒ 0 llamadas.
5. `test_no_publica_en_estado_no_terminal` — `final_status="running"` / `"cancelled"` ⇒ 0 llamadas.
6. `test_bifurca_a_issue_con_flag_on` — `work_item_type="Issue"` + `STACKY_ISSUE_FROM_BRIEF_ENABLED=True`
   ⇒ llama `publish_issue_from_run`, no `autopublish_epic_from_run`.
7. `test_run_started_at_sale_de_started_at_de_la_fila` — assert del valor exacto pasado.
8. `test_una_excepcion_del_publicador_no_propaga` — el hook nunca puede tumbar `on_execution_end`.

**Comando:**
```
"N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest ^
  "Stacky Agents/backend/tests/test_epic_autopublish_service.py" -v
```

**Criterio binario:** 8/8 verdes. **Flag:** reusa `STACKY_EPIC_AUTOPUBLISH_BACKEND` (ON).
**Runtimes:** el módulo no menciona ningún runtime; se prueba parametrizado en F5.
**Trabajo del operador:** ninguno.

---

### F2 — Sellado de metadata y degradación de estado desde el post-hook

**Objetivo:** que el hook reproduzca **exactamente** los efectos laterales que hoy tiene el finalizador
del runner. **Ésta es la fase donde se esconde el falso verde**, y va sola por eso.

**El problema exacto:** hoy `_maybe_autopublish_epic` corre **ANTES** de `on_execution_end`
(publicación en `claude_code_cli_runner.py:1936`, `on_execution_end` en `:2002`). Por eso puede:
(a) **devolver** un `final_status` degradado a `needs_review`, que el runner después usa; y
(b) mutar el dict `metadata` local, que viaja en `metadata_override`.

Un post-hook corre **DESPUÉS** de `set_status` (`ticket_status.py:332-355`). No puede devolver nada ni
mutar un dict local. Tiene que **escribir él mismo**.

**Archivo a editar:** `Stacky Agents/backend/services/epic_autopublish.py` (helpers `_apply_result`,
`_seal_and_degrade`).

**Contrato exacto a reproducir** (leído de `claude_code_cli_runner.py:1716-1745`):

| Situación | metadata a sellar | Estado del ticket |
|---|---|---|
| Excepción inesperada | `epic_publish_error = str(exc)` | → `needs_review` |
| `res.error is not None` | `epic_publish_error = res.error` | → `needs_review` |
| Éxito (`ado_id`, no skipped) | `epic_ado_id` / `issue_ado_id` = `res.ado_id` | sin cambio |
| Ya publicada (skipped) | re-afirmar el sello | sin cambio |
| `res.grounding_warnings` | `grounding_warnings` | sin cambio |
| `res.epic_summary` | `epic_summary` | sin cambio |
| `res.recovery_method` | `epic_recovery` | sin cambio |

**Escritura del metadata:** leer-modificar-escribir sobre `AgentExecution.metadata_dict` dentro de un
`session_scope()`, **mergeando** (nunca reemplazando el dict entero: el runner ya escribió ahí
`runtime`, `work_item_type`, `one_shot`, `epic_convergence`, etc.).

**Degradación de estado:** llamar `ticket_status.set_status(ticket_id, "needs_review", ...)`.

> **Riesgo a probar explícitamente (C-recursión):** el hook corre *dentro* de `_run_post_hooks`, que
> corre dentro de `on_execution_end`. Si el hook llamara `on_execution_end` de nuevo para degradar,
> **se re-dispararían todos los post-hooks**, incluido él mismo ⇒ recursión / doble publicación. Por eso
> el contrato dice `set_status`, **no** `on_execution_end`. F2 debe traer un test que lo congele.

**Tests:** ampliar `test_epic_autopublish_service.py`
9.  `test_error_del_publicador_degrada_a_needs_review` + sella `epic_publish_error`.
10. `test_exito_sella_epic_ado_id_sin_pisar_metadata_previa` — metadata preexistente (`runtime`,
    `work_item_type`) sigue intacta después del sellado.
11. `test_sella_grounding_warnings_epic_summary_y_epic_recovery`.
12. `test_el_hook_no_llama_on_execution_end` — gate por **AST** sobre `epic_autopublish.py`: cero
    llamadas a `on_execution_end`. Congela la no-recursión.

**Criterio binario:** 12/12 verdes. **Flag:** la misma. **Trabajo del operador:** ninguno.

---

### F3 — UN solo publicador: sacar el closure del runner de Claude

**Objetivo:** eliminar el segundo motor **antes** de que exista, para no repetir el anti-patrón de los
2 motores CI/CD del plan 260 y los 2 motores de probe de tracker.

**Archivo a editar:** `Stacky Agents/backend/services/claude_code_cli_runner.py`

**Cambios exactos:**
1. Borrar el closure `_maybe_autopublish_epic` (`:1675-1751` aprox., re-verificar el rango al
   implementar).
2. Borrar su invocación en `:1752` (`_maybe_autopublish_epic("needs_review")`).
3. Reemplazar `:1936` (`final_status = _maybe_autopublish_epic(final_status)`) por nada: el
   `final_status` viaja sin modificar y el post-hook, disparado por `on_execution_end` en `:2002`,
   hace la publicación y la eventual degradación.

> **Ojo con el rango:** el bloque a borrar está pegado al de `epic_convergence`
> (`claude_code_cli_runner.py:1660-1669`), que **NO se toca**. Borrar de más rompe el plan 58.

**Cuidado con `:1752`.** Hoy hay una invocación temprana con `"needs_review"` hardcodeado, en un camino
distinto del `:1936`. Al implementar, **leer ese camino** y confirmar que también termina llamando
`on_execution_end` (si no, ese camino perdería la publicación y sería una regresión silenciosa). Si no
la llama, el fix es hacer que la llame — **no** reintroducir el publicador.

**Tests:** invertir el caso 1 de F0 en `test_epic_autopublish_runtime_parity.py`:

```python
def test_un_solo_publicador_por_ast():
    # K2: el censo se hace por AST porque el publicador vivia dentro de un CLOSURE,
    # y un `grep -c` sobre un closure premia al bug (gotcha de la casa).
    assert publishing_modules() == {"services.epic_autopublish"}
```

Y verificar que **no se rompe** `backend/tests/test_speculative_parity.py:93-111`, que assertea que
`speculative.py` nunca llama `_maybe_autopublish_epic` ni `publish_issue_from_run`. Al desaparecer el
símbolo `_maybe_autopublish_epic`, ese test puede volverse vacuo: **actualizarlo** para que apunte al
nuevo símbolo (`maybe_autopublish_epic` del servicio) en vez de dejarlo assertando la ausencia de un
símbolo que ya no existe en ningún lado — eso sería un assert de ausencia que pasa por accidente.

**Comando:**
```
"N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest ^
  "Stacky Agents/backend/tests/test_epic_autopublish_runtime_parity.py" ^
  "Stacky Agents/backend/tests/test_speculative_parity.py" -v
```

**Criterio binario:** censo por AST devuelve exactamente `{"services.epic_autopublish"}` y
`test_speculative_parity.py` verde. **Flag:** la misma. **Trabajo del operador:** ninguno.

---

### F4 — Registrar el hook y borrar el gate 400

**Objetivo:** encender la paridad de punta a punta.

**Archivos a editar:**

1. `Stacky Agents/backend/app.py` — junto a los registros existentes (`:993-1011`), agregar:
   ```python
   from services import epic_autopublish
   epic_autopublish.register(ticket_status.register_post_hook)
   ```
   Colocarlo **junto a `incident_autopublish.register(...)` (`app.py:994`)**, mismo bloque.

2. `Stacky Agents/backend/api/agents.py` — **borrar** el gate `:654-667` completo (comentario del
   Plan 52 F0 + `_AUTOPUBLISH_RUNTIME` + el `if` + el `return jsonify(...400)`).
   El resto de `run_brief` no se toca.

3. `Stacky Agents/backend/tests/test_run_brief_autopublish_parity.py` — **invertir los 4 casos**:
   - `test_run_brief_epic_codex_returns_400` → `test_run_brief_epic_codex_no_es_rechazado`
   - `test_run_brief_issue_copilot_returns_400` → `..._issue_copilot_no_es_rechazado`
   - `test_run_brief_epic_default_runtime_copilot_returns_400` → `..._default_copilot_no_es_rechazado`
   - `test_run_brief_epic_claude_cli_not_rejected_by_parity_guard` → se **conserva** (no-regresión).

   En los invertidos, el assert correcto es
   `assert resp.get_json().get("error") != "autopublish_requires_claude_cli"`
   **y** `mock_run_agent.assert_called_once()` — porque "no da 400" solo no prueba que arrancó.
   Reescribir el docstring del módulo (`:1-6`), que hoy describe el comportamiento contrario.

**Criterio binario:**
```
"...\venv\Scripts\python.exe" -m pytest ^
  "Stacky Agents/backend/tests/test_run_brief_autopublish_parity.py" -v
```
4/4 verdes, y `grep -c "autopublish_requires_claude_cli" backend/` = **0** fuera de docs.

**Runtimes:** Codex ✅ / Claude ✅ (byte-idéntico) / Copilot ✅. **Trabajo del operador:** ninguno.

---

### F5 — Prueba de paridad real, parametrizada por runtime

**Objetivo:** probar K3 — que los 3 runtimes publican por el mismo camino.

**Archivo a editar:** `Stacky Agents/backend/tests/test_epic_autopublish_runtime_parity.py`

**Caso nuevo:**
```python
@pytest.mark.parametrize("runtime", ["claude_code_cli", "codex_cli", "github_copilot"])
def test_los_tres_runtimes_publican_por_el_mismo_camino(runtime, ...):
    # Simular una ejecucion terminada con output de epica valido y metadata
    # {"runtime": runtime, "work_item_type": "Epic"}, disparar
    # ticket_status.on_execution_end(...) y assertar que autopublish_epic_from_run
    # fue llamado exactamente 1 vez, con el MISMO brief y el MISMO project_name,
    # para los 3 valores de runtime.
```

**Criterio binario:** los 3 parámetros verdes, y el conteo de llamadas es **1** en cada uno (no 0, no 2).
El `assert_called_once` es el que detecta la doble publicación.

> **Anti-falso-verde:** exigir además que el test **seleccione 3 casos**
> (`-k` sin match da exit 0 — gotcha de la casa). Verificar en la salida
> `3 passed`, no solo exit 0.

**Trabajo del operador:** ninguno.

---

### F6 — [ADICIÓN ARQUITECTO] La flag del autopublish se vuelve visible en la UI

**Hallazgo no pedido, encontrado al verificar el sustrato:** `STACKY_EPIC_AUTOPUBLISH_BACKEND` está
**viva** en `config.py:1054-1055` con default `true`, pero **no está registrada en
`backend/services/harness_flags.py`**. Consecuencia: gobierna una acción que **escribe en el GitLab/ADO
real del operador** y el operador **no puede verla ni apagarla desde la UI** — solo editando `.env`.
Eso viola el riel de la casa "toda flag/config del operador va por UI; solo los kill-switches son
env-only", y este no es un kill-switch.

Después de este plan la flag pasa a gobernar el autopublish de **los 3 runtimes** en vez de uno, así
que su invisibilidad deja de ser menor.

**Archivo a editar:** `Stacky Agents/backend/services/harness_flags.py`

**Cambio:** agregar el `FlagSpec` (espejo del de `INTENT_PREFLIGHT_ENABLED`, `:2863-2873`):
```python
FlagSpec(
    key="STACKY_EPIC_AUTOPUBLISH_BACKEND",
    type="bool",
    default=True,          # ya era true en config.py:1054; NO se cambia el default
    label="Autopublicar la épica del brief (41)",
    description=(
        "Plan 41 / Plan 278 — Si ON, al cerrar una run brief→épica el backend publica "
        "la Épica/Issue en el tracker del proyecto, en los 3 runtimes. OFF = la run "
        "termina igual pero no se crea el work item."
    ),
    group="global",
),
```

**No se cambia el default** (sigue ON): la capacidad ya estaba encendida antes de este plan, así que
apagarla sería una regresión de comportamiento, no una mejora de seguridad.

**Tests:** el meta-test del registro que ya existe. Verificar además que el conteo de flags del arnés
sube en exactamente 1 (el ratchet de flags es por conteo).

**Criterio binario:** la flag aparece en `GET /api/harness/flags` y el meta-test del registro pasa.
**Trabajo del operador:** ninguno (gana una perilla que antes no tenía).

---

### F7 — Gate de cierre

**Objetivo:** un solo comando que prueba los 4 KPI.

**Archivos:** registrar los 2 tests nuevos en **AMBOS** ratchets
(`backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1` — la sintaxis difiere y el
meta-test parsea solo el `.sh`; van en los dos igual).

**Criterio binario de cierre (DoD):**

| KPI | Verificación |
|-----|--------------|
| K1 | `test_run_brief_autopublish_parity.py` → 4/4, ningún 400 de paridad |
| K2 | censo AST → `{"services.epic_autopublish"}` exactamente |
| K3 | `test_los_tres_runtimes_publican_por_el_mismo_camino` → `3 passed` |
| K4 | `STACKY_EPIC_AUTOPUBLISH_BACKEND` en el registro del arnés |

**No-regresión obligatoria** (correr **por archivo**, nunca `pytest tests` entero — 2260 errores de
contaminación, gotcha de la casa):
`test_epic_autopublish_backend.py`, `test_epic_grounding.py`, `test_epic_narration_guard.py`,
`test_publish_issue.py`, `test_issue_observability.py`, `test_persist_issue_ticket.py`,
`test_autopublish_rescue.py`, `test_autopublish_rev_from_response.py`, `test_speculative_parity.py`,
`test_epic_payload_preview.py`.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación |
|---|--------|-----------|------------|
| R1 | **Doble publicación** (hook + closure vivos a la vez) ⇒ 2 épicas en el tracker real del operador | ALTA | F3 borra el closure **antes** de F4 registrar el hook. K2 por AST lo congela. `assert_called_once` en F5. |
| R2 | **Recursión de post-hooks**: el hook llama `on_execution_end` para degradar ⇒ se re-dispara a sí mismo | ALTA | Contrato F2: usar `set_status`, nunca `on_execution_end`. Gate por AST (caso 12). |
| R3 | El camino temprano `:1752` pierde la publicación al borrar el closure | MEDIA | F3 obliga a leer ese camino y confirmar que llama `on_execution_end`. |
| R4 | Copilot/Codex devuelven narración ⇒ épicas basura | MEDIA | Ya cubierto: `_looks_like_epic` falla ruidoso con `epic_not_in_output` → `needs_review` (`tickets.py:7284-7318`). Se declara como paridad de MECANISMO, §1. |
| R5 | El hook publica en un chat interactivo del BusinessAgent | MEDIA | Discriminador por bloque `brief` (F1) + test 2. |
| R6 | `test_speculative_parity.py` queda vacuo al desaparecer el símbolo | MEDIA | F3 lo actualiza al símbolo nuevo. |
| R7 | Orden de sellado: el hook escribe metadata después de que el runner ya la escribió ⇒ pisa | MEDIA | F2 exige merge leer-modificar-escribir, con test 10. |
| R8 | El post-hook corre **sincrónico** dentro de `on_execution_end` ⇒ una publicación lenta demora el cierre | BAJA | Igual que hoy (el closure también era sincrónico). Sin cambio de perfil. Si molestara, la salida es encolar como `completion_dispatcher`, **fuera de scope**. |

---

## 6. Fuera de scope

- El **timeout de 20 s** del frontend en `/api/agents/run-brief` — **ya arreglado aparte**
  (`frontend/src/api/endpoints.ts:1308` + ratchet `plan273RequestTimeout.test.ts`, 13/13 vitest, `tsc` 0).
- Mejorar la **calidad** del HTML de épica que produce Copilot o Codex (prompt engineering del
  BusinessAgent). Este plan da paridad de mecanismo, no de calidad.
- Mover el autopublish a un daemon asíncrono (ver R8).
- Cualquier cambio a `autopublish_epic_from_run` / `publish_issue_from_run`: **no se tocan**.
- El pre-vuelo de intención (`intent_preflight`) y su flag.

---

## 7. Glosario

| Término | Significado |
|---------|-------------|
| **Autopublish** | Crear el work item (Épica/Issue) en el tracker real del operador automáticamente al cerrar la run, sin que el navegador tenga que completar un handshake. |
| **Brief → épica** | Flujo donde el operador escribe un brief en lenguaje natural y el BusinessAgent produce el HTML de una Épica. Entra por `POST /api/agents/run-brief`. |
| **Chokepoint** | Punto único por el que pasan los 3 runtimes. Acá: `ticket_status.on_execution_end` → `_run_post_hooks`. |
| **Post-hook** | Callable registrado con `ticket_status.register_post_hook`, ejecutado al terminar cualquier run, en cualquier runtime. |
| **Brief Pool Ticket** | Ticket local sintético (`ado_id=-1`) que ancla las runs de brief (no existe en el tracker). |
| **One-shot** | Run que cierra al primer resultado (`_ONE_SHOT_ADO_IDS = {-1,-7,-8,-9}`), en vez de sesión interactiva. |
| **Sellar (metadata)** | Escribir una clave en `AgentExecution.metadata_dict` como registro idempotente (p. ej. `epic_ado_id`). |
| **Falla ruidosa** | El fallo degrada el estado a `needs_review` y queda visible, en vez de terminar `completed` sin haber hecho nada. |
| **Censo por AST** | Contar llamadas parseando el árbol sintáctico. Obligatorio acá porque el publicador vivía en un **closure**, donde un `grep -c` premia al bug. |

---

## 8. Orden de implementación

1. **F0** — tests del defecto, verdes contra el código actual (foto del estado roto).
2. **F1** — `services/epic_autopublish.py` + sus 8 tests (TDD).
3. **F2** — sellado y degradación + tests 9-12. **No saltear: acá está el falso verde.**
4. **F3** — borrar el closure del runner de Claude + invertir el censo AST. **Antes de F4.**
5. **F4** — registrar el hook en `app.py` + borrar el gate 400 + invertir los 4 tests de paridad.
6. **F5** — test parametrizado por los 3 runtimes.
7. **F6** — registrar la flag en el arnés.
8. **F7** — ratchets (los DOS) + no-regresión por archivo.

> El orden **F3 antes de F4** no es cosmético: invertirlo deja una ventana en la que el closure y el
> hook están vivos a la vez ⇒ **doble publicación en el tracker real del operador** (R1).

## 9. Definición de Hecho (DoD)

- [ ] Los 4 KPI (K1-K4) verdes con sus comandos exactos.
- [ ] Censo por AST: **exactamente un** módulo publicador.
- [ ] Los 3 runtimes probados por el mismo camino, `3 passed` (no exit 0 sin selección).
- [ ] `grep` de `autopublish_requires_claude_cli` en `backend/` = 0 (fuera de docs).
- [ ] 10 archivos de no-regresión verdes, corridos **por archivo**.
- [ ] Tests nuevos registrados en los **DOS** ratchets (`.sh` y `.ps1`).
- [ ] Comportamiento de `claude_code_cli` **sin cambios observables** (mismo status, misma metadata).
- [ ] Ninguna flag nueva; `STACKY_EPIC_AUTOPUBLISH_BACKEND` sigue en default ON y ahora es visible en la UI.
- [ ] Sin `push`. Sin `--no-verify`.
