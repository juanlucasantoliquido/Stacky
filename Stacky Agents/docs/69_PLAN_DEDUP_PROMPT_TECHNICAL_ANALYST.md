# Plan 69 — Eliminar redundancia en prompts de agente: deduplicar identidad/regla en los 3 runtimes (Copilot = origen reportado)

> Versión: **v3** (endurecido por el juez adversarial `criticar-y-mejorar-plan`)
> Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 68 → este plan = **69**.

---

## 0. CHANGELOG (v1 → v2 → v3)

> **Por qué v3:** el operador aclaró que la redundancia **fue reportada en GitHub Copilot Pro**. El v1 (sólo Codex) y la v2 (Codex + Claude rollback) **excluyeron Copilot** — el runtime donde el operador la observó. La verificación contra código confirmó que los 3 runtimes tienen redundancia de identidad/regla. La v3 corrige el scope poniendo a Copilot como objetivo **primario** y conservando los fixes de la v2 para Codex/Claude.

- **[C7 — BLOQUEANTE, nuevo en v3] El runtime reportado (Copilot) estaba excluido del scope.**
  v1 y v2 ponían a GitHub Copilot Pro fuera de scope ("puente propio"). FALSO y verificado: el path de Copilot es el endpoint `POST /api/agents/open-chat` (`agents.py:open_chat`, mensaje en líneas 1154-1165). Ese mensaje pega `invocation` ("## Agente Stacky seleccionado" + `Regla: usá únicamente ese archivo`) y luego una sección "## Agente Stacky" que **repite** "Usá únicamente el archivo indicado arriba como fuente de rol, criterio, tono, restricciones y forma de trabajo". Es exactamente el "repite identidad y rutas 2-3 veces" que reportó el operador. **Corregido:** v3 convierte a Copilot en F1 (objetivo primario) y lo deduplica.

- **[C1 — BLOQUEANTE, heredado v2] Claude rollback también duplica.** `claude_code_cli_runner.py:_build_claude_code_prompt` (2147-2170) tiene el bloque "## Agente seleccionado" duplicado. v3 lo mantiene en scope (F3).

- **[C2 — BLOQUEANTE, heredado v2] No eliminar la directiva read-from-disk.** Condensar, no borrar (regresión conductual). v3 la conserva en los 3 runtimes.

- **[C3 — IMPORTANTE, heredado v2] `description` falta en `invocation_block`.** v3 lo añade (F0) → fuente única de verdad real. `AgentEntry` la tiene (`stacky_agents.py:51`).

- **[C4/C5/C6 — IMPORTANTE/MENOR, heredados v2]** DP-01 tautológico (aserta sobre delta), tests con `Path` no `str`, inexactitud de nº de línea. Resueltos en F4.

- **[ADICIÓN ARQUITECTO #1] DP-04 test de longitud** (prueba el KPI binariamente).
- **[ADICIÓN ARQUITECTO #2] DP-05 guard repo-wide anti-duplicación** (los 3 runners).
- **[ADICIÓN ARQUITECTO #3, nuevo v3] DP-08 test de no-repetición de la regla en el mensaje de Copilot** — falla si "fuente de rol, criterio, tono" aparece más de una vez (sellando la redundancia exacta que reportó el operador).

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Los prompts/mensajes que Stacky arma para el agente seleccionado repiten la **identidad del agente y la regla "usá únicamente ese archivo"** 2-3 veces en los **3 runtimes**. El bloque `invocation_block` (`build_invocation_block`, `stacky_agents.py:413`) ya incluye "## Agente Stacky seleccionado" (mention/nombre/archivo/ruta/carpeta/STACKY_HOME/workspace) + la regla "usá únicamente ese archivo"; pero: (a) **Copilot** (`agents.py:open_chat`) le añade una sección "## Agente Stacky" que re-explica la regla; (b) **Codex CLI** (`_build_codex_prompt`) y **Claude rollback** (`_build_claude_code_prompt`) añaden un bloque "## Agente seleccionado" que duplica nombre/archivo/path/descripción. Este plan elimina la redundancia en los 3 runtimes, conserva la directiva conductual "leé el `.agent.md` desde disco" (condensada), y convierte a `invocation_block` en fuente única de verdad añadiéndole `description`.

**KPI / impacto esperado (binarios):**
- **Redundancia eliminada en los 3 runtimes:** test DP-08 (Copilot), DP-01/02 (Codex), DP-06 (Claude) verde.
- **Tokens:** reducción verificable por DP-04 (longitud estrictamente menor con idéntico input).
- **Cero regresión de información:** `description` pasa a `invocation_block` (F0); directiva read-from-disk condensada (no borrada).
- **Trabajo del operador:** ninguno. Cambio automático en el backend.
- **Paridad 3 runtimes REAL:** Copilot + Codex + Claude (rollback) deduplicados; el default de Claude (`_build_system_prompt`) ya estaba limpio.

---

## 2. Por qué ahora / gap que cierra (VERIFICADO contra código)

**Evidencia (citada con `archivo:línea`):**

| Runtime | Símbolo | Redundancia |
|---------|---------|-------------|
| **GitHub Copilot Pro** (reportado) | `api/agents.py:open_chat` mensaje (1154-1165) | `invocation` ("## Agente Stacky seleccionado" + `Regla: usá únicamente ese archivo`) seguido de "## Agente Stacky" que **repite** "Usá únicamente el archivo indicado arriba como fuente de rol, criterio, tono, restricciones y forma de trabajo" |
| Codex CLI | `codex_cli_runner.py:_build_codex_prompt` (1315-1348) | `{invocation_block}` + intro read-from-disk + bloque "## Agente seleccionado" duplicado (Nombre/Archivo/Path/Descripcion) |
| Claude rollback | `claude_code_cli_runner.py:_build_claude_code_prompt` (2147-2170) | `{invocation_section}` + intro + bloque "## Agente seleccionado" duplicado |
| *(limpio, no se toca)* | `claude_code_cli_runner.py:_build_system_prompt` (2077) y `_build_user_message` (2110) | sin duplicación |

- `stacky_agents.py:413-443` — `build_invocation_block`: NO incluye `description` (deuda de F0).
- **`copilot_bridge.py` NO es el runtime del agente:** es el LLM_BACKEND interno de Stacky (ver memoria `stacky-llm-backend-vs-runtime`). El runtime GitHub Copilot Pro = el endpoint `/open-chat` que abre VS Code Copilot Chat con el `.agent.md` resuelto.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad explícita:** Copilot + Codex + Claude (rollback) se deduplican. Cada cambio declara impacto por runtime.
- **Cero trabajo extra al operador:** automático, sin config/flag nueva.
- **Human-in-the-loop intacto:** el operador sigue viendo qué agente se seleccionó (en `invocation_block`, ahora con `description`).
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** no se elimina información (description → invocation_block; directiva read-from-disk condensada).
- **Reuso obligatorio:** `build_invocation_block` = contrato canónico.

---

## 4. Fases

> **Orden:** F0 (contrato) → F1 (Copilot, primario) → F2 (Codex) → F3 (Claude rollback) → F4 (tests).
> F1/F2/F3 dependen de F0. Cada fase verde de forma aislada.
> **Tests por archivo, desde `backend/`:** `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/<archivo> -q` (pin pywin32 roto en 3.13 → no correr suite completa).

---

### F0 — Contrato canónico: añadir `description` a `build_invocation_block`

**Objetivo.** Hacer que `invocation_block` sea fuente única de verdad REAL (incluye `description`). **Valor:** permite eliminar los bloques duplicados en F1/F2/F3 sin perder info.

**Archivo:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/stacky_agents.py`

**Cambio 0.1 — Agregar `- Descripcion` al return de `build_invocation_block` (línea ~437)**

Localizar con `grep -n "Workspace de trabajo:" stacky_agents.py`. Insertar la línea **justo después** de `- Workspace de trabajo:` y antes del `"\n"` que precede a `Regla:`:

```python
        f"- Workspace de trabajo: {ws or '(no resuelto)'}\n"
        f"- Descripcion: {entry.description or '(sin descripcion)'}\n"   # ← AGREGAR
        "\n"
        f"Regla: usá el agente `{entry.mention}` y tomá como prompt/persona\n"
```

**No-rotura de tests:** `test_stacky_agents.py:265` usa `assert "## Agente Stacky seleccionado" in block` (substring) → no rompe. Confirmar en §8.

**Criterio binario F0:** `pytest tests/test_stacky_agents.py -q` verde.
**Flag:** ninguna. **Impacto runtime:** los 3 runtimes reciben `description` en `invocation_block` (aditivo, benigno). **Trabajo del operador:** ninguno.

---

### F1 — [PRIMARIO] Deduplicar el mensaje de GitHub Copilot Pro (`open_chat`)

**Objetivo.** Eliminar la repetición de la regla "usá únicamente ese archivo" en el mensaje que se envía a VS Code Copilot Chat. **Es el runtime donde el operador reportó la redundancia.**

**Archivo:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/api/agents.py`

**Cambio 1.1 — Condensar la sección "## Agente Stacky" (líneas 1154-1165)**

Localizar con `grep -n '## Agente Stacky\\n' agents.py` (aprox. 1154-1165). La regla "usá únicamente ese archivo como fuente de rol/criterio/tono" YA está en el `Regla:` del `invocation` — la sección "## Agente Stacky" la repite. Conservar SOLO la directiva read-from-disk (no redundante con `invocation`):

```python
# ANTES (1154-1165):
        message = (
            f"{invocation}\n"
            "## Agente Stacky\n"
            "\n"
            "No se incluye el contenido del `.agent.md` en este mensaje. "
            "Usá únicamente el archivo indicado arriba como fuente de rol, "
            "criterio, tono, restricciones y forma de trabajo.\n"
            "\n"
            "## Tarea\n"
            "\n"
            f"{message}"
        )

# DESPUÉS: condensar a una línea read-from-disk (la regla "usá únicamente ese
# archivo" ya vive en el 'Regla:' del invocation; no re-explicarla):
        message = (
            f"{invocation}\n"
            "No se incluye el contenido del `.agent.md` en este mensaje: "
            "leé el archivo indicado arriba antes de empezar.\n"
            "\n"
            "## Tarea\n"
            "\n"
            f"{message}"
        )
```

**Qué se eliminó:** la repetición "Usá únicamente el archivo indicado arriba como fuente de rol, criterio, tono, restricciones y forma de trabajo" (ya en `invocation`).
**Qué se conserva (C2):** la directiva read-from-disk ("No se incluye el contenido... leé el archivo indicado arriba").
**No-rotura de tests:** `test_open_chat_ado_enrichment.py:307` aserta `"## Agente Stacky" in msg` — substring satisfecho por "## Agente Stacky **seleccionado**" del `invocation`. `"Ruta agent.md"` (línea 309 del test) viene de `invocation`. Confirmar en §8.

**Criterio binario F1:** `pytest tests/test_open_chat_ado_enrichment.py -q` verde + DP-08 (F4) verde.
**Flag:** ninguna. **Impacto runtime:** GitHub Copilot Pro → mensaje sin regla duplicada. Codex/Claude → sin cambios. **Trabajo del operador:** ninguno.

---

### F2 — Deduplicar Codex CLI (`_build_codex_prompt`)

**Objetivo.** Eliminar el bloque duplicado "## Agente seleccionado" y condensar la intro read-from-disk.

**Archivo:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/codex_cli_runner.py`

**Cambio 2.1 — Reemplazar el cuerpo del f-string de `_build_codex_prompt` (def en 1294, return 1315-1348)**

Localizar con `grep -n "def _build_codex_prompt"`. Reemplazar desde `return f"""# Stacky Agents Codex CLI runtime` hasta `"""`:

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

**Eliminado:** bloque "## Agente seleccionado" (su info → `invocation_block` tras F0). **Conservado:** directiva read-from-disk condensada.

**Criterio binario F2:** `pytest tests/test_codex_prompt_dedup.py -q` verde (DP-01..DP-05).
**Flag:** ninguna. **Impacto runtime:** Codex → deduplicado. **Trabajo del operador:** ninguno.

---

### F3 — Deduplicar Claude rollback (`_build_claude_code_prompt`)

**Objetivo.** Mismo tratamiento sobre la función de rollback de Claude (la única con el bloque duplicado).

**Archivo:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/claude_code_cli_runner.py`

**Cambio 3.1 — Reemplazar el cuerpo del f-string de `_build_claude_code_prompt` (def en 2133, return 2147-2170)**

Localizar con `grep -n "def _build_claude_code_prompt"`. Reemplazar el `return f"""# Stacky Agents Claude Code CLI runtime` ... `"""`:

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

**Eliminado:** bloque "## Agente seleccionado" + intro larga. **Conservado:** directiva condensada. **No se toca:** `_build_system_prompt` (2077) ni `_build_user_message` (2110).

**Criterio binario F3:** `pytest tests/test_claude_code_cli_prompt.py -q` verde (DP-06/DP-07 agregados en F4).
**Flag:** ninguna. **Impacto runtime:** Claude rollback → deduplicado. **Trabajo del operador:** ninguno.

---

### F4 — Tests de verificación (corregidos + adiciones)

**Crear `tests/test_codex_prompt_dedup.py`:**

```python
"""Tests de deduplicación de prompts (Plan 69 v3). Codex + guards repo-wide."""
from pathlib import Path
from unittest.mock import MagicMock


def _make_selected(name="TestAgent", filename="TestAgent.agent.md", description="Agente de prueba"):
    sel = MagicMock()
    sel.name = name
    sel.filename = filename
    sel.description = description
    return sel


_INVOC = (
    "## Agente Stacky seleccionado\n\n- Mention: @TestAgent\n- Nombre: TestAgent\n"
    "- Archivo agent.md: TestAgent.agent.md\n- Descripcion: Agente de prueba\n"
)


# DP-01 (CORREGIDO, ex-tautología): la función NO emite su propio header fuera del invocation_block.
def test_dp01_codex_no_own_agent_stacky_header_outside_invocation():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected()
    prompt = _build_codex_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"), agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    delta = prompt.replace(_INVOC, "")
    assert "## Agente Stacky seleccionado" not in delta
    assert prompt.count("## Agente Stacky seleccionado") == 1


# DP-02: sin bloque duplicado "## Agente seleccionado"
def test_dp02_codex_no_duplicate_agent_block():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected()
    prompt = _build_codex_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"), agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    assert "## Agente seleccionado\n" not in prompt


# DP-03: la info del agente sigue presente (incluida description vía invocation_block)
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
    assert "Análisis funcional" in prompt


# DP-04 [ADICIÓN ARQUITECTO #1]: el prompt deduplicado es ESTRICTAMENTE más corto que la baseline.
def test_dp04_codex_prompt_is_shorter_than_baseline():
    from services.codex_cli_runner import _build_codex_prompt
    sel = _make_selected()
    prompt_after = _build_codex_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"), agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    baseline = _INVOC + (
        f"## Agente seleccionado\n\n- Nombre: {sel.name}\n"
        f"- Archivo: {sel.filename}\n- Descripcion: {sel.description}\n"
    )
    assert len(prompt_after) < len(baseline) + len(_INVOC)
```

**Crear `tests/test_prompt_dedup_guard.py` [ADICIÓN ARQUITECTO #2]:**

```python
"""Guard repo-wide (Plan 69 v3): ningún _build_*_prompt ni el mensaje de Copilot duplican identidad/regla."""
from pathlib import Path

_TARGETS = [
    Path("services/codex_cli_runner.py"),
    Path("services/claude_code_cli_runner.py"),
]


def test_dp05_no_duplicated_agent_block_anywhere():
    """El header canónico vive sólo en invocation_block; ningún runner lo duplica."""
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for rel in _TARGETS:
        text = (root / rel).read_text(encoding="utf-8")
        if "## Agente seleccionado\n" in text:
            offenders.append(rel.as_posix())
    assert not offenders, (
        f"Bloque '## Agente seleccionado' duplicado en: {offenders}. "
        "La identidad debe vivir sólo en invocation_block."
    )
```

**Agregar a `tests/test_open_chat_ado_enrichment.py` [ADICIÓN ARQUITECTO #3 — sella el reporte del operador]:**

```python
# DP-08: el mensaje de Copilot NO repite la regla "fuente de rol, criterio, tono..."
# más de una vez (reproducer exacto de la redundancia reportada por el operador).
def test_dp08_open_chat_rule_not_duplicated(client, monkeypatch):
    """La frase 'fuente de rol, criterio, tono' debe aparecer a lo sumo 1 vez en el mensaje."""
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket(ado_id=70001, project="RSPacifico", title="dp08", ado_state="Active",
                   description="d")
        session.add(t); session.flush()
        ticket_id = t.id
    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): return None

    def _fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    with patch("services.ado_client.AdoClient", side_effect=RuntimeError("off")), \
         patch("api.agents.ensure_project_vscode", return_value=_fake_project_context()), \
         patch("requests.post", side_effect=_fake_post):
        r = client.post("/api/agents/open-chat",
                        json={"ticket_id": ticket_id, "context_blocks": [],
                              "vscode_agent_filename": "X.agent.md"})
    assert r.status_code == 200
    msg = captured["json"]["message"]
    assert msg.count("fuente de rol, criterio, tono") <= 1, (
        "La regla se repite en el mensaje de Copilot — redundancia que reportó el operador"
    )
    # La directiva read-from-disk se conserva (C2):
    assert "no se incluye el contenido" in msg.lower() or "leé el archivo" in msg.lower()
```

> Nota: reusar los fixtures `_fake_project_context()` ya existentes en ese archivo de test.

**Agregar a `tests/test_claude_code_cli_prompt.py` (F3):**

```python
def test_dp06_claude_rollback_no_duplicate_agent_block():
    from services.claude_code_cli_runner import _build_claude_code_prompt
    from unittest.mock import MagicMock
    sel = MagicMock(); sel.name = "X"; sel.filename = "X.agent.md"; sel.description = "d"
    prompt = _build_claude_code_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        invocation_block="## Agente Stacky seleccionado\n- Mention: @X\n",
    )
    assert "## Agente seleccionado\n" not in prompt

def test_dp07_claude_rollback_keeps_read_from_disk_directive():
    from services.claude_code_cli_runner import _build_claude_code_prompt
    from unittest.mock import MagicMock
    sel = MagicMock(); sel.name = "X"; sel.filename = "X.agent.md"; sel.description = "d"
    prompt = _build_claude_code_prompt(
        selected_agent=sel, all_agents=[], ticket_message="t",
        invocation_block="## Agente Stacky seleccionado\n- Mention: @X\n",
    )
    assert "no está en este mensaje" in prompt or "leé el archivo" in prompt
```

**Comando (por archivo, desde `backend/`):**
```powershell
& ".venv/Scripts/python.exe" -m pytest tests/test_codex_prompt_dedup.py tests/test_claude_code_cli_prompt.py tests/test_prompt_dedup_guard.py tests/test_open_chat_ado_enrichment.py tests/test_stacky_agents.py -q
```
**Criterio binario F4:** todos los DP verdes + suite existente sin regresión.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Un LLM deja de leer el `.agent.md` al condensar | C2: la directiva read-from-disk se **conserva** (condensada) en los 3 runtimes. DP-07/DP-08 la bloquean. |
| Se pierde `description` | C3: pasa a `invocation_block` (F0). DP-03 verifica presencia. |
| Test de `open_chat` se rompe al tocar el mensaje | `test_open_chat_ado_enrichment.py:307` usa substring `"## Agente Stacky"` (satisfecho por "## Agente Stacky **seleccionado**") y `"Ruta agent.md"` (de invocation). Verificado §8. |
| Queda duplicación en otro runner | ADICIÓN #2 (`test_dp05`) escanea Codex+Claude; ADICIÓN #3 (`test_dp08`) sella Copilot. |
| `invocation_block` afecta a los 3 runtimes | Aditivo/benigno: añade `- Descripcion:`. |

---

## 6. Fuera de scope

- `copilot_bridge.py` (LLM_BACKEND interno, NO runtime del agente).
- `_build_system_prompt` (default Claude Fase C) y `_build_user_message`: limpios, no se tocan.
- Reescribir `build_invocation_block` más allá de añadir `description`.

---

## 7. Glosario

- **invocation_block:** contrato canónico (`build_invocation_block`). Tras F0 incluye `description`. Única fuente de verdad de la identidad del agente.
- **runtime GitHub Copilot Pro:** el endpoint `/api/agents/open-chat` (`agents.py`) que abre VS Code Copilot Chat con el `.agent.md` resuelto. NO es `copilot_bridge.py`.
- **directiva read-from-disk:** "el `.agent.md` no está inline; leélo desde la ruta". Se conserva condensada (C2).
- **rollback (`_build_claude_code_prompt`):** modo `user_message` de Claude, alternativa al default `_build_system_prompt`.

---

## 8. Orden de implementación y DoD

**Orden (TDD):**
1. **F0** — Añadir `- Descripcion:` a `build_invocation_block` → `pytest tests/test_stacky_agents.py -q` verde.
2. **F4 (tests)** — Crear `test_codex_prompt_dedup.py`, `test_prompt_dedup_guard.py`; agregar DP-08 a `test_open_chat_ado_enrichment.py`; DP-06/07 a `test_claude_code_cli_prompt.py` → ROJO.
3. **F1 (Copilot, PRIMARIO)** — Condensar mensaje `open_chat` → DP-08 verde + `test_open_chat_ado_enrichment.py` sin regresión.
4. **F2 (Codex)** — Dedup `_build_codex_prompt` → DP-01..05 verde.
5. **F3 (Claude rollback)** — Dedup `_build_claude_code_prompt` → DP-06/07 verde.

**Definition of Done (binaria):**
- [ ] `build_invocation_block` incluye `- Descripcion:`; `tests/test_stacky_agents.py` verde.
- [ ] **Copilot:** `open_chat` sin repetición de "fuente de rol, criterio, tono" (DP-08 ≤1) y con directiva read-from-disk condensada; `tests/test_open_chat_ado_enrichment.py` sin regresión.
- [ ] Codex `_build_codex_prompt` sin bloque duplicado; directiva condensada.
- [ ] Claude `_build_claude_code_prompt` (rollback) sin bloque duplicado; directiva condensada.
- [ ] `_build_system_prompt` y `_build_user_message` NO modificados.
- [ ] `test_codex_prompt_dedup.py` (DP-01..05), `test_prompt_dedup_guard.py` (DP-05), DP-06/07, DP-08 verde.
- [ ] `tests/test_stacky_agents.py` y `tests/test_claude_code_cli_prompt.py` sin regresión.
- [ ] Sin flag nueva; sin trabajo del operador; sin cambio en `copilot_bridge.py`.
- [ ] Commit `docs(plan-69): dedup prompt 3 runtimes v3` + trailer de co-autoría.
