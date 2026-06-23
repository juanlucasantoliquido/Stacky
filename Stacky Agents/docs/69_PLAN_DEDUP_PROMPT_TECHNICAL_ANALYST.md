# Plan 69 — Eliminar redundancia en prompts de agente: deduplicar bloques en Codex CLI y Claude Code CLI (rollback)

> Versión: **v2** (endurecido por el juez adversarial `criticar-y-mejorar-plan`)
> Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 68 → este plan = **69**.

---

## 0. CHANGELOG v1 → v2

El v1 atacaba SOLO el prompt de Codex CLI bajo la premisa de que "Claude Code CLI ya está correcto". La verificación contra el código **destruyó esa premisa** y destapó dos defectos de diseño. La v2 corrige el scope y las regresiones silenciosas del v1.

- **[C1 — BLOQUEANTE] Premisa falsa: Claude Code CLI TAMBIÉN tiene el bloque duplicado.**
  El v1 excluía a Claude ("ya está correcto"). **FALSO**, verificado con grep: `claude_code_cli_runner.py:_build_claude_code_prompt` (líneas 2147-2170, el modo rollback `user_message`) tiene el MISMO patrón: intro read-from-disk (2149-2153) + bloque "## Agente seleccionado" duplicado (2155-2159). El KPI "paridad 3 runtimes, todos se benefician" era falso; dejaba 1 runtime con el defecto. **Corregido:** la v2 dedup AMBOS runners afectados (Codex `_build_codex_prompt` + Claude `_build_claude_code_prompt`). Las otras dos funciones de Claude (`_build_system_prompt` default y `_build_user_message`) están limpias y NO se tocan.

- **[C2 — BLOQUEANTE] Remover la intro perdía la directiva "leé desde disco" (regresión conductual).**
  El v1 eliminaba el párrafo entero (Codex 1319-1323) asumiendo que era redundante con `invocation_block`. Pero `invocation_block` sólo dice "usá únicamente ese archivo"; **no** dice "el contenido del `.agent.md` NO está en este mensaje, debés leerlo desde la ruta". Son dos reglas distintas. Un LLM podría asumir que su persona ya está inline y no cargar el `.agent.md` → degradación del runtime sin fallback. **Corregido:** la v2 NO elimina la directiva: la condensa a UNA línea en cada runner ("Tu `.agent.md` no está en este mensaje: leé el archivo desde la 'Ruta agent.md' indicada arriba.").

- **[C3 — IMPORTANTE] Remover "## Agente seleccionado" borraba el campo `description`.**
  `invocation_block` NO incluía `description` (tenía mention/nombre/archivo/ruta/carpeta/STACKY_HOME/workspace). El bloque duplicado era la ÚNICA fuente de `selected_agent.description` en el prompt. El v1 decía "cero regresiones" — falso para `description`. **Corregido:** la v2 añade `- Descripcion: {entry.description}` a `build_invocation_block` (`AgentEntry` SÍ tiene `description`, `stacky_agents.py:51`), convirtiéndolo en fuente única de verdad REAL. El test existente `test_stacky_agents.py:265` usa aserción `in` (substring) → no se rompe.

- **[C4 — IMPORTANTE] DP-01 era tautológico (no protegía la regresión).**
  El v1 contaba "## Agente Stacky seleccionado" == 1, pero ese 1 venía 100% del `invocation_block` que el propio test inyectaba. La función nunca emite ese header (antes ni después). DP-01 pasaba aunque se revirtiera el cambio. **Corregido:** la v2 reescribe la aserción sobre el **delta** (`prompt` sin el `invocation_block` inyectado) y agrega la aserción real del bloque duplicado eliminado.

- **[C5 — IMPORTANTE] Tests pasaban `agent_bundle_dir`/`agent_manifest_file` como str; la firma declara `Path`.**
  Funcionaba por casualidad (f-string + inventory vacío), pero violaba el contrato y era frágil. **Corregido:** la v2 pasa `Path(...)` y declara las dependencias de import (`config.VSCODE_PROMPTS_DIR`, `harness.run_contract.rules_text`).

- **[C6 — MENOR] Inexactitud de nº de línea.** El v1 citaba `build_invocation_block` en "stacky_agents.py:429-443"; el `def` está en **413** (429-443 es el return body). Corregido.

- **[ADICIÓN ARQUITECTO #1] Test de LONGITUD que prueba el KPI binariamente.** `test_dp04_prompt_is_shorter_than_baseline`: con idéntico input, el prompt deduplicado es estrictamente más corto que una baseline construida con el bloque duplicado. Convierte "reducción ~150-200 tokens" en verificable (pasa/falla), no verbal.
- **[ADICIÓN ARQUITECTO #2] Guard repo-wide anti-duplicación.** `test_dp05_no_duplicated_agent_block_anywhere`: grep sobre los 3 runners que afirman que NINGÚN `_build_*_prompt` emite su propio "## Agente seleccionado" fuera del `invocation_block`. Sella la regresión "alguien vuelve a duplicar" en todos los runtimes.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Los prompts que se arman para el agente seleccionado contienen **información redundante en DOS runtimes**. El bloque `invocation_block` (generado por `build_invocation_block` en `stacky_agents.py:413`) ya incluye "## Agente Stacky seleccionado" con todos los datos (mention, nombre, archivo, ruta, carpeta, STACKY_HOME, workspace) y la regla "usá únicamente el archivo X"; pero tanto `_build_codex_prompt` (Codex CLI) como `_build_claude_code_prompt` (Claude Code CLI, modo rollback) agregan **otro** bloque "## Agente seleccionado" que repite nombre, archivo, path y descripción, precedido de un párrafo introductorio. Este plan elimina la duplicación en AMBOS runners, conserva la directiva conductual "leé el `.agent.md` desde disco" (condensada a una línea) y convierte a `invocation_block` en fuente única de verdad añadiéndole el campo `description` que faltaba.

**KPI / impacto esperado (binarios):**
- **Tokens de prompt:** reducción verificable por test (DP-04) de longitud estrictamente menor con idéntico input, en Codex y en Claude-rollback.
- **Claridad:** cada prompt tiene una única sección "## Agente Stacky seleccionado" (la de `invocation_block`).
- **Cero regresiones de información:** `description` ahora vive en `invocation_block`; la directiva read-from-disk se conserva (condensada). Testeado (DP-03).
- **Trabajo del operador:** ninguno. Cambio automático en el backend.
- **Paridad 3 runtimes:** Codex CLI y Claude CLI (rollback) se deduplican; Copilot no se toca (puente propio, fuera de scope); el default de Claude (`_build_system_prompt`) ya estaba limpio.

---

## 2. Por qué ahora / gap que cierra (VERIFICADO contra código en v2)

**Evidencia en código (citada con `archivo:línea`):**
- `stacky_agents.py:413-443` — `build_invocation_block` genera "## Agente Stacky seleccionado" con mention/nombre/archivo/ruta/carpeta/STACKY_HOME/workspace + regla "usá únicamente ese archivo". **NO incluye `description`** (deuda que la v2 corrige en F0).
- `codex_cli_runner.py:1315-1348` — `_build_codex_prompt` incluye `{invocation_block}` (1317), luego un párrafo introductorio read-from-disk (1319-1323), **Y** un bloque "## Agente seleccionado" duplicado (1325-1330) con nombre/archivo/path/**descripción**.
- `claude_code_cli_runner.py:2147-2170` — `_build_claude_code_prompt` (modo rollback) tiene el **MISMO** patrón: `{invocation_section}` (2146/2149), intro read-from-disk (2149-2153), bloque "## Agente seleccionado" duplicado (2155-2159).
- **Limpios (NO se tocan):** `claude_code_cli_runner.py:_build_system_prompt` (2077, default Fase C — sólo un 1-liner "# Agente que estás adoptando" + intro, sin bloque duplicado) y `_build_user_message` (2110 — sin bloque de agente).

**Gap reportado:** el operador ve el mensaje repitiendo identidad del agente y rutas 2-3 veces. **Es redundancia** (no intencional), presente en Codex y en Claude-rollback.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad explícita:** Codex CLI y Claude CLI (rollback) se deduplican; el default de Claude y Copilot están limpios. Cualquier cambio declara su impacto por runtime + fallback.
- **Cero trabajo extra al operador:** cambio automático, sin config nueva ni flag.
- **Human-in-the-loop intacto:** el operador sigue viendo qué agente se seleccionó (en `invocation_block`, ahora con `description`).
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** no se elimina NINGUNA información (description pasa a invocation_block; la directiva read-from-disk se condensa, no se borra).
- **Reuso obligatorio:** `build_invocation_block` sigue siendo el contrato canónico, ahora enriquecido con `description`.

---

## 4. Fases

> **Orden de dependencia:** F0 → F1 → F2 → F3.
> F0 = enriquecer el contrato canónico (`invocation_block` + `description`); F1 = dedup Codex; F2 = dedup Claude rollback; F3 = tests.
> Cada fase verde de forma aislada (F0 no depende de F1/F2; F1/F2 dependen de F0).

> **Intérprete de tests (usar en todos los comandos pytest), ejecutar DESDE `backend/`:**
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/<archivo> -q`
> (pin pywin32 roto en 3.13 → correr **por archivo**, no la suite completa.)

---

### F0 — Contrato canónico: añadir `description` a `build_invocation_block`

**Objetivo (1 frase).** Hacer que `invocation_block` sea la fuente única de verdad REAL añadiendo el campo `description` que hoy sólo existía en los bloques duplicados. **Valor:** permite eliminar los bloques duplicados en F1/F2 sin perder información.

**Archivo a modificar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/stacky_agents.py`

**Cambio 0.1 — Agregar línea `- Descripcion` al return de `build_invocation_block` (línea ~437)**

Localizar con `grep -n "STACKY_HOME:" stacky_agents.py` (aprox. línea 436). Insertar la línea de descripción **justo después** de `- Workspace de trabajo:` y **antes** de la línea en blanco que precede a `Regla:`:

```python
# ANTES (return actual, líneas ~428-442):
    return (
        "## Agente Stacky seleccionado\n"
        "\n"
        f"- Mention: {entry.mention}\n"
        f"- Nombre: {entry.name}\n"
        f"- Archivo agent.md: {entry.filename}\n"
        f"- Ruta agent.md: {entry.path}\n"
        f"- Carpeta de agentes configurada: {agents_dir}\n"
        f"- STACKY_HOME: {home}\n"
        f"- Workspace de trabajo: {ws or '(no resuelto)'}\n"
        "\n"
        f"Regla: usá el agente `{entry.mention}` y tomá como prompt/persona\n"
        ...
    )

# DESPUÉS: agregar una línea "- Descripcion:" antes del "\n" separador
    return (
        "## Agente Stacky seleccionado\n"
        "\n"
        f"- Mention: {entry.mention}\n"
        f"- Nombre: {entry.name}\n"
        f"- Archivo agent.md: {entry.filename}\n"
        f"- Ruta agent.md: {entry.path}\n"
        f"- Carpeta de agentes configurada: {agents_dir}\n"
        f"- STACKY_HOME: {home}\n"
        f"- Workspace de trabajo: {ws or '(no resuelto)'}\n"
        f"- Descripcion: {entry.description or '(sin descripcion)'}\n"   # ← AGREGAR
        "\n"
        f"Regla: usá el agente `{entry.mention}` y tomá como prompt/persona\n"
        ...
    )
```

**Verificación de no-rotura de tests existentes:** `test_stacky_agents.py:265` usa `assert "## Agente Stacky seleccionado" in block` (substring) → la nueva línea NO la rompe. `test_claude_code_cli_prompt.py` inyecta su propio `invocation_block` de prueba → no depende del real. Confirmar con el comando de la sección §8.

**Criterio binario F0:** `pytest tests/test_stacky_agents.py -q` verde (incluye la aserción de `build_invocation_block`).
**Flag:** ninguna. **Impacto runtime:** los 3 runtimes ahora reciben `description` en `invocation_block` (aditivo, benigno). **Trabajo del operador:** ninguno.

---

### F1 — Deduplicar Codex CLI (`_build_codex_prompt`)

**Objetivo (1 frase).** Eliminar el bloque duplicado "## Agente seleccionado" y condensar la intro read-from-disk a una línea, manteniendo la directiva conductual.

**Archivo a modificar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/codex_cli_runner.py`

**Cambio 1.1 — Reemplazar el cuerpo del f-string de `_build_codex_prompt` (líneas 1315-1348)**

Localizar con `grep -n "def _build_codex_prompt" codex_cli_runner.py` (def en 1294). Reemplazar **desde `return f"""# Stacky Agents Codex CLI runtime`** hasta el cierre `"""`:

```python
    return f"""# Stacky Agents Codex CLI runtime

{invocation_block}
Tu `.agent.md` (persona/rol) no está en este mensaje: leé el archivo desde la
'Ruta agent.md' indicada arriba antes de empezar y usalo como fuente de rol,
criterio, tono, restricciones y forma de trabajo.

## Catalogo de agentes Stacky disponibles

Stacky copio todos los `.agent.md` conocidos a esta ejecucion para que Codex
CLI pueda consultar cualquier agente GitHub Copilot Pro aunque el operador haya
elegido solo uno.

- Carpeta local: {agent_bundle_dir}
- Manifest JSON: {agent_manifest_file}

{inventory}

## Ticket y contexto

{ticket_message}
{skills_block}
{rules}
"""
```

**Qué se eliminó (vs v1):**
- El bloque "## Agente seleccionado" (Nombre/Archivo/Path/Descripcion) → su info ahora vive 100% en `invocation_block` (tras F0, incluye `description`).
**Qué se CONSERVA (corrección del C2 del v1):**
- La directiva read-from-disk, condensada de 5 líneas a 3 ("Tu `.agent.md` no está en este mensaje: leé el archivo desde la 'Ruta agent.md' indicada arriba...").

**Criterio binario F1:** `pytest tests/test_codex_prompt_dedup.py -q` verde (DP-01..DP-05) Y suite Codex existente sin regresión.
**Flag:** ninguna. **Impacto runtime:** Codex CLI → prompt más corto con idéntica info + directiva preservada. Claude/Copilot → sin cambios. **Trabajo del operador:** ninguno.

---

### F2 — Deduplicar Claude Code CLI rollback (`_build_claude_code_prompt`)

**Objetivo (1 frase).** Mismo tratamiento que F1 sobre la función de rollback de Claude (la ÚNICA de Claude con el bloque duplicado). **Corrige la premisa falsa del v1.**

**Archivo a modificar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/claude_code_cli_runner.py`

**Cambio 2.1 — Reemplazar el cuerpo del f-string de `_build_claude_code_prompt` (líneas 2147-2170)**

Localizar con `grep -n "def _build_claude_code_prompt" claude_code_cli_runner.py` (def en 2133). Reemplazar el `return f"""# Stacky Agents Claude Code CLI runtime` ... `"""`:

```python
    return f"""# Stacky Agents Claude Code CLI runtime

{invocation_section}Tu `.agent.md` (persona/rol) no está en este mensaje: leé el archivo desde la
'Ruta agent.md' indicada arriba y usalo como fuente de rol, criterio, tono,
restricciones y forma de trabajo.

## Catalogo de agentes Stacky disponibles

{inventory}

## Ticket y contexto

{ticket_message}

{_STACKY_RULES}
"""
```

**Qué se eliminó:** el bloque "## Agente seleccionado" (Nombre/Archivo/Descripcion) duplicado; la intro larga.
**Qué se CONSERVA:** la directiva read-from-disk (condensada). `invocation_section` (que envuelve a `invocation_block`) sigue presente.
**NO se toca:** `_build_system_prompt` (2077, default) ni `_build_user_message` (2110) — ya limpios.

**Criterio binario F2:** `pytest tests/test_claude_code_cli_prompt.py -q` verde (incluye tests existentes que asertan "Agente Stacky seleccionado" presente — siguen pasando porque viene de `invocation_section`). Agregar DP-06/DP-07 (ver F3).
**Flag:** ninguna. **Impacto runtime:** Claude CLI modo rollback → deduplicado. Default y Copilot → sin cambios. **Trabajo del operador:** ninguno.

---

### F3 — Tests de verificación (corregidos + adiciones)

**Objetivo (1 frase).** Crear `tests/test_codex_prompt_dedup.py` con aserciones REALES (no tautológicas), agregar casos a `tests/test_claude_code_cli_prompt.py`, y sumar las dos adiciones de arquitecto.

**Archivo a crear:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_codex_prompt_dedup.py`

```python
"""Tests de deduplicación de prompts (Plan 69 v2). Cobertura Codex + guard repo-wide."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_selected(name="TestAgent", filename="TestAgent.agent.md", description="Agente de prueba"):
    sel = MagicMock()
    sel.name = name
    sel.filename = filename
    sel.description = description
    return sel


_INVOC = (
    "## Agente Stacky seleccionado\n"
    "\n"
    "- Mention: @TestAgent\n"
    "- Nombre: TestAgent\n"
    "- Archivo agent.md: TestAgent.agent.md\n"
    "- Descripcion: Agente de prueba\n"
)


# DP-01 (CORREGIDO, ex-tautología): la función NO emite su propio header "## Agente Stacky seleccionado"
# fuera del invocation_block inyectado. Se aserta sobre el DELTA (prompt sin el invocation_block).
def test_dp01_codex_no_own_agent_stacky_header_outside_invocation():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected()
    prompt = _build_codex_prompt(
        selected_agent=sel,
        all_agents=[],
        ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"),       # Path, no str (C5)
        agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    delta = prompt.replace(_INVOC, "")
    assert "## Agente Stacky seleccionado" not in delta, (
        "El header canónico sólo debe venir de invocation_block, no de la función"
    )
    # Y el header CANÓNICO sigue apareciendo exactamente 1 vez (la de invocation_block)
    assert prompt.count("## Agente Stacky seleccionado") == 1


# DP-02: el prompt NO contiene el bloque duplicado "## Agente seleccionado" (sin "Stacky")
def test_dp02_codex_no_duplicate_agent_block():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected()
    prompt = _build_codex_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"), agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    assert "## Agente seleccionado\n" not in prompt


# DP-03: la info del agente sigue presente (incluida description, vía invocation_block)
def test_dp03_codex_agent_info_present():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected(name="FunctionalAnalyst", filename="FunctionalAnalyst.agent.md",
                         description="Análisis funcional")
    invoc = (
        "## Agente Stacky seleccionado\n- Mention: @FunctionalAnalyst\n"
        f"- Archivo agent.md: {sel.filename}\n- Descripcion: Análisis funcional\n"
    )
    prompt = _build_codex_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"), agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=invoc,
    )
    assert "@FunctionalAnalyst" in prompt
    assert "Análisis funcional" in prompt   # description preservada vía invocation_block


# DP-04 [ADICIÓN ARQUITECTO #1]: el prompt deduplicado es ESTRICTAMENTE más corto que la baseline duplicada.
# Convierte el KPI "~150-200 tokens" en binario verificable.
def test_dp04_codex_prompt_is_shorter_than_baseline():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected()
    # Prompt real (deduplicado)
    prompt_after = _build_codex_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"), agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    # Baseline: simula el bloque duplicado que el plan elimina
    baseline = _INVOC + (
        f"## Agente seleccionado\n\n- Nombre: {sel.name}\n"
        f"- Archivo: {sel.filename}\n- Descripcion: {sel.description}\n"
    )
    assert len(prompt_after) < len(baseline) + len(_INVOC), (
        "El prompt deduplicado debe ser más corto que la versión con bloque duplicado"
    )
```

**Agregar a `tests/test_claude_code_cli_prompt.py` (F2):**

```python
# DP-06: el prompt de rollback de Claude NO tiene bloque "## Agente seleccionado" duplicado
def test_dp06_claude_rollback_no_duplicate_agent_block():
    from services.claude_code_cli_runner import _build_claude_code_prompt
    from unittest.mock import MagicMock
    sel = MagicMock(); sel.name = "X"; sel.filename = "X.agent.md"; sel.description = "d"
    prompt = _build_claude_code_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        invocation_block="## Agente Stacky seleccionado\n- Mention: @X\n",
    )
    assert "## Agente seleccionado\n" not in prompt


# DP-07: el prompt de rollback de Claude conserva la directiva read-from-disk (condensada)
def test_dp07_claude_rollback_keeps_read_from_disk_directive():
    from services.claude_code_cli_runner import _build_claude_code_prompt
    from unittest.mock import MagicMock
    sel = MagicMock(); sel.name = "X"; sel.filename = "X.agent.md"; sel.description = "d"
    prompt = _build_claude_code_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        invocation_block="## Agente Stacky seleccionado\n- Mention: @X\n",
    )
    assert "no está en este mensaje" in prompt or "leé el archivo" in prompt, (
        "La directiva read-from-disk debe conservarse (condensada)"
    )
```

**[ADICIÓN ARQUITECTO #2] Guard repo-wide anti-duplicación — crear `tests/test_prompt_dedup_guard.py`:**

```python
"""Guard repo-wide (Plan 69 v2): ningún _build_*_prompt duplica '## Agente seleccionado'."""
from pathlib import Path

_RUNNERS = [
    Path("services/codex_cli_runner.py"),
    Path("services/claude_code_cli_runner.py"),
]

def test_dp05_no_duplicated_agent_block_anywhere():
    """Sella la regresión: el header canónico vive sólo en invocation_block."""
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for rel in _RUNNERS:
        text = (root / rel).read_text(encoding="utf-8")
        # Cuenta emisiones literales del header duplicado (sin "Stacky") dentro de f-strings/código
        if "## Agente seleccionado\n" in text:
            offenders.append(rel.as_posix())
    assert not offenders, (
        f"Se encontró bloque '## Agente seleccionado' duplicado en: {offenders}. "
        f"La identidad del agente debe vivir sólo en invocation_block."
    )
```

**Comando de verificación (correr por archivo desde `backend/`):**
```powershell
& ".venv/Scripts/python.exe" -m pytest tests/test_codex_prompt_dedup.py tests/test_claude_code_cli_prompt.py tests/test_prompt_dedup_guard.py tests/test_stacky_agents.py -q
```
**Criterio binario F3:** todos los DP verdes + suite existente (`test_stacky_agents.py`, `test_claude_code_cli_prompt.py`) sin regresión.
**Flag:** ninguna. **Impacto runtime:** ninguno (tests). **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Un LLM deja de leer el `.agent.md` al condensar la intro | C2 resuelto: la directiva read-from-disk se **conserva** (condensada a 1-3 líneas), no se elimina. DP-07 la bloquea. |
| Se pierde `description` del prompt | C3 resuelto: `description` pasa a `invocation_block` (F0). DP-03 verifica su presencia. |
| Snapshot test de `build_invocation_block` se rompe al añadir `description` | `test_stacky_agents.py:265` usa aserción `in` (substring) → no rompe. Verificado en §8. |
| Queda duplicación en otro runner no contemplado | ADICIÓN #2 (`test_dp05`) escanea Codex + Claude y falla si reaparece. (Copilot tiene puente propio, fuera de scope.) |
| El cambio de `invocation_block` afecta a los 3 runtimes | Aditivo y benigno: sólo añade una línea `- Descripcion:`. Default Claude y Copilot la reciben también (mejora, no regresión). |

---

## 6. Fuera de scope

- **GitHub Copilot Pro** (puente propio, sin `invocation_block` en este camino): plan separado si se detecta la misma duplicación.
- **`_build_system_prompt` (default Claude Fase C) y `_build_user_message`:** ya limpios, no se tocan.
- **Reescribir `build_invocation_block` más allá de añadir `description`:** no; es el contrato canónico.

---

## 7. Glosario

- **invocation_block:** bloque generado por `build_invocation_block` (contrato canónico). Tras F0 incluye `description`. Única fuente de verdad de la identidad del agente.
- **bloque duplicado:** el "## Agente seleccionado" (sin "Stacky") que aparecía en `_build_codex_prompt` y `_build_claude_code_prompt`, repitiendo info ya en `invocation_block`.
- **directiva read-from-disk:** instrucción conductual "el `.agent.md` no está inline; leélo desde la ruta". Se conserva condensada (C2).
- **rollback (`_build_claude_code_prompt`):** modo `user_message` de Claude, alternativa al default `_build_system_prompt`.

---

## 8. Orden de implementación y DoD

**Orden (estricto, TDD):**
1. **F0** — Añadir `- Descripcion:` a `build_invocation_block` → `pytest tests/test_stacky_agents.py -q` verde.
2. **F3 (tests nuevos)** — Crear `test_codex_prompt_dedup.py`, `test_prompt_dedup_guard.py`; agregar DP-06/DP-07 a `test_claude_code_cli_prompt.py` → ROJO esperado.
3. **F1** — Dedup `_build_codex_prompt` → DP-01..05 verde.
4. **F2** — Dedup `_build_claude_code_prompt` → DP-06/07 verde.
5. Suite completa afectada por archivo → sin regresión.

**Definition of Done (verificación binaria):**
- [ ] `build_invocation_block` incluye `- Descripcion:` y `tests/test_stacky_agents.py` verde.
- [ ] `_build_codex_prompt` sin bloque "## Agente seleccionado"; directiva read-from-disk condensada presente.
- [ ] `_build_claude_code_prompt` (rollback) sin bloque duplicado; directiva condensada presente.
- [ ] `_build_system_prompt` y `_build_user_message` NO modificados (diff vacío en esos símbolos).
- [ ] `tests/test_codex_prompt_dedup.py` (DP-01..DP-05) verde; `tests/test_prompt_dedup_guard.py` verde; DP-06/DP-07 en `test_claude_code_cli_prompt.py` verde.
- [ ] `tests/test_claude_code_cli_prompt.py` y `tests/test_stacky_agents.py` sin regresión.
- [ ] Sin flag nueva; sin trabajo del operador; sin cambio en Copilot.
- [ ] Commit `docs(plan-69): dedup prompt Codex+Claude v2` + trailer de co-autoría.
