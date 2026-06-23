# Plan 69 — Eliminar redundancia en prompt de Technical Analyst: deduplicar bloques de agente seleccionado

> Versión: **v1** | Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 68 → este plan = **69**.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Hoy el prompt que se arma para el Technical/Developer/Functional Analyst contiene **información redundante**: el bloque `invocation_block` (generado por `build_invocation_block` en `stacky_agents.py`) ya incluye "## Agente Stacky seleccionado" con todos los datos (mention, nombre, archivo, ruta, carpeta, STACKY_HOME, workspace) y la regla "usá únicamente el archivo X", pero luego `_build_codex_prompt` agrega **otro** bloque "## Agente seleccionado" que repite nombre, archivo, path y descripción. Esto genera confusión y consume tokens innecesarios. Este plan elimina la redundancia: manteniendo `invocation_block` como única fuente de verdad y removiendo el bloque duplicado, además de simplificar la intro que refuerza la regla.

**KPI / impacto esperado:**
- **Tokens de prompt:** reducción estimada de ~150-200 tokens por run (eliminación de bloque duplicado).
- **Claridad:** el prompt tiene una única sección "## Agente Stacky seleccionado" en lugar de dos.
- **Cero regresiones:** la información del agente sigue presente (en `invocation_block`), solo que no duplicada.
- **Trabajo del operador:** ninguno. Cambio automático en el backend.
- **Paridad 3 runtimes:** Codex CLI, Claude Code CLI y GitHub Copilot Pro se benefician de la deduplicación (todos usan `invocation_block`).

---

## 2. Por qué ahora / gap que cierra

- **Evidencia en código:**
  - `stacky_agents.py:429-443` — `build_invocation_block` genera "## Agente Stacky seleccionado" con mention, nombre, archivo, ruta, carpeta, STACKY_HOME, workspace + regla "usá únicamente el archivo X".
  - `codex_cli_runner.py:1315-1330` — `_build_codex_prompt` incluye `{invocation_block}` (línea 1317) Y luego agrega "## Agente seleccionado" (línea 1325) con nombre, archivo, path, descripción.
  - La línea 1323 dice "debes leerlo desde la ruta indicada en el bloque 'Agente Stacky seleccionado'" — refuerzo redundante.
- **Gap reportado:** el operador muestra un ejemplo donde el mensaje repite la identidad del agente y las rutas 2-3 veces. La pregunta es "¿es por algo en especial o es un error?". La respuesta: **es redundancia** (no intencional) que este plan elimina.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI y GitHub Copilot Pro usan `invocation_block` como única fuente de verdad.
- **Cero trabajo extra al operador:** cambio automático, sin config nueva.
- **Human-in-the-loop intacto:** el operador sigue viendo qué agente se seleccionó (en `invocation_block`).
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** solo se elimina redundancia; la información del agente sigue presente.
- **Reuso obligatorio:** mantener `build_invocation_block` como contrato canónico.

---

## 4. Fases

> **Orden de dependencia:** F0 → F1.
> F0 = deduplicar en Codex CLI; F1 = tests de verificación.

> **Intérprete de tests (usar en todos los comandos pytest):**
> `& "N:/GIT/RS/STACKY/Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest <archivo> -q`

---

### F0 — Deduplicar bloque de agente seleccionado en Codex CLI

**Objetivo (1 frase).** Modificar `codex_cli_runner.py:_build_codex_prompt` para eliminar el bloque redundante "## Agente seleccionado" y simplificar la intro, manteniendo `invocation_block` como única fuente de verdad.

**Archivo a modificar:** `N:/GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\codex_cli_runner.py`

#### Cambio 0.1 — Eliminar bloque duplicado "## Agente seleccionado" (líneas 1325-1330)

**Código actual (líneas 1315-1343):**
```python
    return f"""# Stacky Agents Codex CLI runtime

{invocation_block}

Stacky te esta lanzando desde Codex CLI para trabajar sobre el ticket y mantener
trazabilidad en los logs del workbench. No se inyecta el contenido del
`.agent.md` seleccionado en este mensaje: debes leerlo desde la ruta indicada en
el bloque "Agente Stacky seleccionado" y usar ese archivo como fuente de rol,
criterio, tono, restricciones y forma de trabajo.

## Agente seleccionado

- Nombre: {selected_agent.name}
- Archivo: {selected_agent.filename}
- Path: {selected_path}
- Descripcion: {selected_agent.description or "(sin descripcion)"}

## Catalogo de agentes Stacky disponibles

Stacky copio todos los `.agent.md` conocidos a esta ejecucion para que Codex
CLI pueda consultar cualquier agente GitHub Copilot Pro aunque el operador haya
elegido solo uno.

- Carpeta local: {agent_bundle_dir}
- Manifest JSON: {agent_manifest_file}

{inventory}

## Ticket y contexto
```

**Código corregido:**
```python
    return f"""# Stacky Agents Codex CLI runtime

{invocation_block}

## Catalogo de agentes Stacky disponibles

Stacky copio todos los `.agent.md` conocidos a esta ejecucion para que Codex
CLI pueda consultar cualquier agente GitHub Copilot Pro aunque el operador haya
elegido solo uno.

- Carpeta local: {agent_bundle_dir}
- Manifest JSON: {agent_manifest_file}

{inventory}

## Ticket y contexto
```

**Qué se eliminó:**
- El párrafo introductorio (líneas 1319-1323) que reforzaba la regla de leer el archivo (redundante con `invocation_block`).
- El bloque "## Agente seleccionado" (líneas 1325-1330) que duplicaba info.

**Qué se mantiene:**
- `invocation_block` — tiene toda la info del agente seleccionado + la regla de usar únicamente ese archivo.
- "## Catalogo de agentes Stacky disponibles" — info sobre el bundle y manifest.
- `{inventory}` — lista de todos los agentes disponibles.
- "## Ticket y contexto" — resto del prompt.

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_codex_prompt_dedup.py" -q
```
Esperado: 2 tests verdes (DP-01, DP-02).

#### Flag que protege esta fase

Ninguna. Este cambio es de deduplicación, no requiere opt-in.

#### Impacto por runtime

- **Codex CLI:** prompt más corto, misma info.
- **Claude Code CLI:** idéntico (no se toca, ya usa `invocation_block` correctamente).
- **GitHub Copilot Pro:** idéntico.
- **Fallback:** ninguno, cambio es directo.

#### Trabajo del operador

Ninguno. Cambio automático.

---

### F1 — Tests de verificación: prompt sin duplicación

**Objetivo (1 frase).** Crear `tests/test_codex_prompt_dedup.py` que verifique que el prompt de Codex no contiene bloques duplicados y que `invocation_block` está presente.

**Archivo a crear:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_codex_prompt_dedup.py`

**Tests exactos (copiar tal cual):**

```python
"""Tests de deduplicación de prompt Codex CLI (Plan 69)."""
import pytest


# DP-01: el prompt contiene invocation_block una sola vez
def test_dp01_prompt_contains_invocation_block_once():
    """Verificar que invocation_block aparece exactamente una vez en el prompt."""
    from unittest.mock import MagicMock
    from services.codex_cli_runner import _build_codex_prompt

    # Mock de agentes
    selected = MagicMock()
    selected.name = "TestAgent"
    selected.filename = "TestAgent.agent.md"
    selected.description = "Agente de prueba"

    invocation_block = (
        "## Agente Stacky seleccionado\n"
        "\n"
        "- Mention: @TestAgent\n"
        "- Nombre: TestAgent\n"
        # ... resto del bloque
    )

    prompt = _build_codex_prompt(
        selected_agent=selected,
        all_agents=[],
        ticket_message="Test ticket",
        agent_bundle_dir="/tmp/bundle",
        agent_manifest_file="/tmp/manifest.json",
        invocation_block=invocation_block,
    )

    # Contar cuántas veces aparece el header del invocation_block
    count = prompt.count("## Agente Stacky seleccionado")
    assert count == 1, f"Expected 1 occurrence of '## Agente Stacky seleccionado', got {count}"


# DP-02: el prompt NO contiene el bloque duplicado "## Agente seleccionado"
def test_dp02_prompt_does_not_contain_duplicate_agent_block():
    """Verificar que el bloque '## Agente seleccionado' (sin 'Stacky') NO existe."""
    from unittest.mock import MagicMock
    from services.codex_cli_runner import _build_codex_prompt

    selected = MagicMock()
    selected.name = "TestAgent"
    selected.filename = "TestAgent.agent.md"
    selected.description = "Agente de prueba"

    invocation_block = (
        "## Agente Stacky seleccionado\n"
        "- Mention: @TestAgent\n"
    )

    prompt = _build_codex_prompt(
        selected_agent=selected,
        all_agents=[],
        ticket_message="Test ticket",
        agent_bundle_dir="/tmp/bundle",
        agent_manifest_file="/tmp/manifest.json",
        invocation_block=invocation_block,
    )

    # El bloque duplicado era "## Agente seleccionado" (sin "Stacky")
    assert "## Agente seleccionado\n" not in prompt, "Found duplicate '## Agente seleccionado' block"


# DP-03: el prompt sigue conteniendo info del agente (en invocation_block)
def test_dp03_prompt_still_contains_agent_info():
    """Verificar que la info del agente sigue presente en invocation_block."""
    from unittest.mock import MagicMock
    from services.codex_cli_runner import _build_codex_prompt

    selected = MagicMock()
    selected.name = "FunctionalAnalyst"
    selected.filename = "FunctionalAnalyst.agent.md"
    selected.description = "Análisis funcional"

    invocation_block = (
        "## Agente Stacky seleccionado\n"
        "- Mention: @FunctionalAnalyst\n"
        "- Nombre: FunctionalAnalyst\n"
        f"- Archivo agent.md: {selected.filename}\n"
    )

    prompt = _build_codex_prompt(
        selected_agent=selected,
        all_agents=[],
        ticket_message="Test ticket",
        agent_bundle_dir="/tmp/bundle",
        agent_manifest_file="/tmp/manifest.json",
        invocation_block=invocation_block,
    )

    # Verificar que la info del agente está presente
    assert "@FunctionalAnalyst" in prompt
    assert "FunctionalAnalyst" in prompt
    assert selected.filename in prompt
```

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_codex_prompt_dedup.py" -q
```
Esperado: 3 tests verdes (DP-01 a DP-03).

#### Flag que protege esta fase

Ninguna.

#### Impacto por runtime

- **Codex CLI:** prompt más corto, misma info.
- **Claude Code CLI:** idéntico.
- **GitHub Copilot Pro:** idéntico.
- **Fallback:** ninguno.

#### Trabajo del operador

Ninguno. Tests de verificación.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| La info del agente ya no está visible | Falso. `invocation_block` tiene toda la info y sigue presente. |
| El prompt queda muy corto | Falso. Solo se eliminaron ~150-200 tokens redundantes; el resto del prompt sigue intacto. |
| Claude Code CLI también tenía redundancia | Verificado: Claude Code CLI usa `invocation_block` correctamente, no tiene bloque duplicado. |
| Copilot también tenía redundancia | Copilot usa su propio puente; fuera de scope de este plan (plan separado si aplica). |

---

## 6. Fuera de scope

- Modificar el prompt de Claude Code CLI (ya está correcto).
- Modificar el prompt de GitHub Copilot Pro (fuera de scope).
- Modificar `build_invocation_block` (es el contrato canónico, no se toca).

---

## 7. Glosario

- **invocation_block:** bloque generado por `build_invocation_block` que contiene toda la info del agente seleccionado + la regla de usar únicamente ese archivo.
- **bloque duplicado:** el bloque "## Agente seleccionado" que aparecía en `_build_codex_prompt` y repetía info ya presente en `invocation_block`.
- **deduplicación:** eliminar redundancia manteniendo una única fuente de verdad.

---

## 8. Orden de implementación

1. **F1** — Crear `tests/test_codex_prompt_dedup.py` (tests TDD).
2. **F0** — Modificar `codex_cli_runner.py:_build_codex_prompt` (eliminar bloque duplicado).
3. Verificar tests verdes.
4. Commitear y push manual.

---

## 9. Definición de Hecho (DoD)

- [ ] `tests/test_codex_prompt_dedup.py` existe con 3 tests (DP-01 a DP-03).
- [ ] Todos los tests pasan.
- [ ] `codex_cli_runner.py:_build_codex_prompt` no contiene bloque duplicado.
- [ ] El prompt generado contiene `invocation_block` con toda la info del agente.
- [ ] `npx tsc --noEmit` en `frontend/` = 0 errores (no se toca frontend).
- [ ] Commit con mensaje `docs(plan-69): dedup prompt technical analyst` + trailer de co-autoría.
- [ ] Memoria actualizada (opcional).

---

**Resumen de 5 líneas:**

Este plan elimina la redundancia en el prompt del Technical Analyst: el bloque `invocation_block` ya tiene toda la info del agente seleccionado, y `_build_codex_prompt` tenía un bloque duplicado "## Agente seleccionado". KPI: reducción de ~150-200 tokens por run y prompt más claro. Cero trabajo del operador: cambio automático. Paridad 3 runtimes: Codex CLI mejora, Claude Code CLI ya estaba correcto. Implementación F0→F1: eliminar bloque duplicado + tests de verificación.
