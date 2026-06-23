# Plan 67 — Disciplina de procesos: reutilizar por default, crear solo con instrucción explícita

> Versión: **v2 (PROPUESTA) — 1ra pasada del juez** | Estado: PROPUESTA | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 66 → este plan = **67**.

### CHANGELOG v1 → v2

- **C1 (BLOQUEANTE)**: `enrich_blocks` no recibe `title`/`description`/`process_catalog`. Se reescribió el Cambio 1.3 para usar `ticket_title`/`ticket_description` (capturados localmente líneas 87-88) y obtener el catálogo vía `load_client_profile(project_name)` (mismo seam que usa `_inject_process_catalog_block:716`), no vía `project_ctx.process_catalog` (no existe en scope).
- **C2 (BLOQUEANTE)**: La variable `enriched_blocks` no existe en `enrich_blocks`; la local es `blocks`. Se corrigió el wiring a `blocks = _inject_process_discipline_block(blocks, ...)`.
- **C3 (IMPORTANTE)**: La flag `STACKY_PROCESS_DISCIPLINE_ENABLED` no estaba en `FLAG_REGISTRY` (`harness_flags.py:174`). Se añadió la **F1b** con el FlagSpec literal (archivo + ancla exacta), categoría `contexto_memoria` ya existente (`harness_flags.py:40`), `env_only=False`, default `false`.
- **C4 (IMPORTANTE)**: Se alineó `_inject_process_discipline_block` al patrón idiomático del módulo (retorno `list[dict]`, `return blocks` en todos los fallbacks, dedup por `id`, carga del profile propia).
- **C5 (MENOR)**: Negación expandida a `nunca|prohibido|no vuelvas` + stopword filtering en Jaccard. Documentada la relación con el RAG TF-IDF del Plan 64 (no se duplica: 64=truncar ranking, 67=gate binario).
- **[ADICIÓN ARQUITECTO] PD-07**: Test de integración del wiring (flag ON + catálogo → bloque `process-discipline` presente; flag OFF → ausente; sin catálogo → ausente). Cubre la rama F1 que F0 no ejercitaba.
- **[ADICIÓN ARQUITECTO] Telemetría decision.action**: emite `decision.action`/`confidence`/`process_name` vía el `meta` del bloque para que el observatorio de grounding (Plan 44) pueda exponer cuándo el agente fue guiado a REUSE vs CREATE.
- **C6 (BLOQUEANTE) — corrección de cierre v2.1**: la F1b de v2 registraba la flag en `FLAG_REGISTRY` pero **NO** la agregaba a `_CATEGORY_KEYS`. Verificado contra `harness_flags.py:172-173` ("toda flag nueva debe agregarse también a `_CATEGORY_KEYS` o el test `test_every_registry_flag_is_categorized` rompe CI") y contra `_CATEGORY_KEYS["contexto_memoria"]` (`harness_flags.py:79-91`, donde ya vive `STACKY_RAG_CATALOG_TOP_K`). Sin este alta, CI se rompe. Agregado el **Cambio F1b.2** literal.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Hoy los agentes de Stacky (Business, Functional, Technical) pueden crear nuevos procesos o tareas sin una disciplina clara que distinga entre REUTILIZAR un proceso existente del catálogo (`process_catalog`) vs CREAR uno nuevo. Esto genera ambigüedad en la generación de código Batch: el agente puede inventar procesos duplicados, crear "fantasmas" que no existen en la arquitectura real, o malinterpretar cuándo usar Mul2Bane/IncHost/RSCore/RsExtrae vs cuándo proponer algo nuevo. Este plan introduce una **disciplina explícita de procesos** con dos reglas duras: (1) REUTILIZAR por default un proceso del catálogo si el ticket NO pide explícitamente crear uno nuevo; (2) CREAR solo cuando el ticket contiene una instrucción explícita del operador ("crear nuevo proceso", "nuevo batch", "nunca crees", etc.) o cuando NO existe ningún proceso en el catálogo que cubra la necesidad. La disciplina se codifica en un módulo `process_discipline.py` con funciones PURAS que el agente consulta antes de proponer código, y se inyecta como bloque de contexto en el prompt del agente.

**KPI / impacto esperado:**
- **Reducción de procesos fantasmas:** el agente deja de inventar procesos que no existen en la arquitectura real.
- **Claridad en tareas/épicas:** el output del agente distingue explícitamente "REUTILIZO <proceso>" vs "CREO nuevo proceso <nombre>".
- **Tokens de contexto:** el bloque de disciplina es compacto (~300 tokens) y solo se inyecta cuando `process_catalog` existe en el profile.
- **Trabajo del operador:** ninguno. La disciplina se aplica automáticamente cuando el flag está ON (default OFF para opt-in).
- **Paridad 3 runtimes:** el módulo corre en el backend antes de cualquier runtime → idéntico para Codex, Claude Code y GitHub Copilot Pro.
- **Observabilidad (v2):** el `decision.action` queda en `meta` del bloque para telemetría/observatorio.

---

## 2. Por qué ahora / gap que cierra

- **Plan 42** introdujo `process_catalog` en `client_profile` y el grounding de épicas.
- **Plan 45** agregó el catálogo de procesos editable por UI (`ClientProfileEditor`).
- **Plan 64** introdujo RAG TF-IDF para *truncar* el catálogo a top-K relevante (ranking), NO para decidir REUSE vs CREATE.
- **Planes 49/50** endurecieron el arnés con blindaje determinista y saneamiento de épica.
- **Gap verificado:** los agentes NO tienen hoy una regla explícita que diga "reutiliza por default". Un agente puede leer `process_catalog` y aún así inventar un nuevo proceso sin justificación.
- **Evidencia real:** el operador pidió "Estructurar un poco más las tareas para que quede claro cuándo se debe crear un nuevo proceso y cuándo reutilizar uno" y "Nunca debe de crear un proceso sin una instrucción explícita". Esto es exactamente lo que el plan codifica.
- **No duplica el Plan 64:** el 64 decide *cuántos* procesos mostrar (truncamiento por relevancia TF-IDF); el 67 decide una *acción binaria* REUSE/CREATE con un gate de similitud. Coexisten: el 64 filtra el catálogo y el 67 emite la directiva sobre el resultado.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** la disciplina corre en el backend (Python puro) antes de cualquier llamada al runtime. Idéntico para Codex CLI, Claude Code CLI y GitHub Copilot Pro. No hay rama por runtime.
- **Cero trabajo extra al operador:** flag `STACKY_PROCESS_DISCIPLINE_ENABLED` default OFF. OFF → byte-idéntico al actual (sin bloque de disciplina). Opt-in desde UI.
- **Human-in-the-loop intacto:** la disciplina guía al agente, pero el operador sigue aprobando el resultado. No hay autonomía nueva.
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** cero nuevas dependencias (stdlib `re`, `dataclasses`). Sin llamadas a red. Fallback: si el módulo falla → no inyecta bloque (degradación controlada, `return blocks`).
- **Reuso obligatorio:** reutiliza `load_client_profile` (seam del Plan 42/64), el bloque `"process-catalog"` existente, y `harness_flags.FLAG_REGISTRY` (registración explícita en `harness_flags.py:174`).
- **Regla dura config-por-UI:** el flag se registra en `FLAG_REGISTRY` con `env_only=False` → aparece en el panel de flags (Plan 62) sin tocar el frontend.

---

## 4. Fases

> **Orden de dependencia:** F0 → F1 → F1b → F2.
> F0 = módulo disciplina puro; F1 = wiring en context_enrichment; F1b = registro de flag en FLAG_REGISTRY; F2 = tests + ratchet (incluye PD-07 de integración).

> **Intérprete de tests (usar en todos los comandos pytest):**
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest <archivo> -q`
> ejecutado desde `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend`.

---

### F0 — Módulo disciplina puro: funciones PURAS que deciden reutilizar vs crear

**Objetivo (1 frase).** Crear `services/process_discipline.py` con funciones PURAS que, dado un ticket (título + descripción) y un catálogo de procesos, deciden si REUTILIZAR un proceso existente o se justifica CREAR uno nuevo, basándose en (1) instrucción explícita del operador, (2) coincidencia por similitud de texto con el catálogo, y (3) fallback cuando no hay coincidencia.

**Archivo a crear:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/process_discipline.py`

**Implementación exacta (copiá esto tal cual):**

```python
"""Disciplina de procesos: reutilizar por default, crear solo con instrucción explícita.

Funciones puras: sin estado global, sin red, sin LLM. Compatible con Python 3.10+ stdlib.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


# Palabras clave que indican INTENCIÓN EXPLÍCITA de crear algo nuevo
_CREATE_KEYWORDS = [
    "crear nuevo proceso",
    "crear nuevo batch",
    "nuevo proceso",
    "nuevo batch",
    "crear proceso",
    "proceso nuevo",
    "batch nuevo",
    "nueva interfaz",
    "nuevo modulo",
    "nuevo subproceso",
    "crear subproceso",
]

# Prefijos que NUNCA indican creación (son modificaciones o consultas)
_NO_CREATE_PREFIXES = [
    "modificar",
    "actualizar",
    "corregir",
    "fix",
    "agregar campo",
    "incorporar",
    "incorporación",
    "mejorar",
    "optimizar",
    "revisar",
    "analizar",
    "informe",
    "reporte",
]

# Stopwords para limpiar vocabulario antes de Jaccard (C5 — reduce ruido)
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y",
    "o", "en", "para", "por", "con", "que", "se", "a", "al", "lo", "le",
    "es", "son", "como", "the", "a", "an", "of", "to", "in", "for", "and",
    "or", "que", "este", "esta", "esto", "su", "sus", "this", "is",
}


@dataclass(frozen=True)
class DisciplineDecision:
    """Resultado de analizar un ticket contra el catálogo de procesos.

    - action: "REUSE" o "CREATE"
    - process_name: nombre del proceso a reutilizar (si action=REUSE) o sugerido para crear (si action=CREATE)
    - reason: explicación breve para inyectar en el prompt
    - confidence: 0..1, cuán seguro estamos (para telemetría)
    - instruction_present: True si el ticket contiene instrucción explícita de crear
    """
    action: Literal["REUSE", "CREATE"]
    process_name: str | None
    reason: str
    confidence: float
    instruction_present: bool


def _tokenize(text: str) -> set[str]:
    """Tokeniza + lower + filtra stopwords (C5)."""
    words = re.findall(r"\b\w+\b", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _contains_create_instruction(text: str) -> bool:
    """Detecta si el texto contiene una instrucción EXPLÍCITA de crear algo nuevo.

    Niega ante 'no', 'nunca', 'sin', 'evitar', 'prohibido', 'no vuelvas' (C5).
    """
    text_lower = text.lower()
    # Patrones de negación que invalidan la keyword de creación (C5 — expansión)
    _NEGATIONS = (
        r"no\s+{kw}", r"nunca\s+{kw}", r"sin\s+{kw}",
        r"evitar\s+{kw}", r"prohibido\s+{kw}", r"no\s+vuelvas\s+a\s+{kw}",
    )
    for keyword in _CREATE_KEYWORDS:
        if keyword not in text_lower:
            continue
        negated = any(
            re.search(pat.format(kw=re.escape(keyword)), text_lower)
            for pat in _NEGATIONS
        )
        if not negated:
            return True
    return False


def _contains_no_create_prefix(text: str) -> bool:
    """Detecta si el texto empieza con prefijos que claramente NO son creación."""
    text_lower = text.lower().strip()
    for prefix in _NO_CREATE_PREFIXES:
        if text_lower.startswith(prefix):
            return True
    return False


def _find_best_match(
    query: str, process_catalog: list[dict]
) -> tuple[str | None, float]:
    """Encuentra el proceso del catálogo más similar al query (Jaccard sobre tokens limpios).

    Returns:
        (process_name, similarity_score) donde similarity_score está en 0..1
    """
    if not process_catalog:
        return None, 0.0

    query_lower = query.lower()
    query_words = _tokenize(query_lower)
    if not query_words:
        return None, 0.0

    best_name = None
    best_score = 0.0

    for proc in process_catalog:
        name = proc.get("name", "")
        purpose = proc.get("purpose", "")
        kind = proc.get("kind", "")

        proc_text = f"{name} {purpose} {kind}".lower()
        proc_words = _tokenize(proc_text)
        if not proc_words:
            continue

        intersection = query_words & proc_words
        union = query_words | proc_words
        score = len(intersection) / len(union) if union else 0.0

        # Boost si el nombre aparece literalmente
        if name.lower() in query_lower:
            score = max(score, 0.8)

        if score > best_score:
            best_score = score
            best_name = name

    return best_name, best_score


def decide_process_action(
    title: str,
    description: str,
    process_catalog: list[dict] | None,
) -> DisciplineDecision:
    """Decide si REUTILIZAR un proceso existente o CREAR uno nuevo.

    Reglas:
    1. Si el ticket contiene instrucción EXPLÍCITA de crear ("crear nuevo proceso", etc.)
       Y NO empieza con prefijos de no-creación → CREATE.
    2. Si NO hay instrucción explícita Y hay un proceso con similitud >= 0.4 → REUSE ese proceso.
    3. Si NO hay instrucción explícita Y NO hay coincidencia → CREATE (porque no sabemos qué usar).
    4. Sin catálogo → CREATE con confianza 0 (fallback).
    """
    combined = f"{title} {description}"
    instruction_present = _contains_create_instruction(combined)
    no_create_prefix = _contains_no_create_prefix(combined)

    # Si empieza con "modificar", "fix", etc., no es creación aunque diga "proceso"
    if no_create_prefix:
        instruction_present = False

    # Caso 1: instrucción explícita de crear
    if instruction_present:
        return DisciplineDecision(
            action="CREATE",
            process_name=None,
            reason="El ticket contiene una instrucción explícita de crear un nuevo proceso o batch.",
            confidence=0.95,
            instruction_present=True,
        )

    # Caso 2: buscar mejor coincidencia en catálogo
    best_match, similarity = _find_best_match(combined, process_catalog or [])

    SIMILARITY_THRESHOLD = 0.4

    if best_match and similarity >= SIMILARITY_THRESHOLD:
        return DisciplineDecision(
            action="REUSE",
            process_name=best_match,
            reason=f"El catálogo ya contiene el proceso '{best_match}' que cubre la necesidad (similitud {similarity:.2f}).",
            confidence=similarity,
            instruction_present=False,
        )

    # Caso 3: no hay coincidencia clara y no hay instrucción explícita
    if process_catalog:
        return DisciplineDecision(
            action="CREATE",
            process_name=None,
            reason=f"No se encontró un proceso en el catálogo que coincida suficientemente (mejor similitud {similarity:.2f}). Solo crea un nuevo proceso si estás seguro de que no existe uno equivalente.",
            confidence=0.3,
            instruction_present=False,
        )

    # Caso 4: no hay catálogo (fallback)
    return DisciplineDecision(
        action="CREATE",
        process_name=None,
        reason="No hay catálogo de procesos configurado para este proyecto. Procede con tu criterio.",
        confidence=0.0,
        instruction_present=False,
    )


def build_discipline_block(decision: DisciplineDecision) -> str:
    """Construye el bloque de texto para inyectar en el prompt del agente."""
    if decision.action == "REUSE":
        return f"""## Disciplina de Procesos — Stacky

**ACCIÓN RECOMENDADA: REUTILIZAR proceso existente**

- Proceso a reutilizar: **{decision.process_name}**
- Razón: {decision.reason}
- Confianza: {decision.confidence:.0%}

**Instrucción para el agente:** Debes usar el proceso **{decision.process_name}** existente en la arquitectura. NO inventes un nuevo proceso. Si el ticket requiere modificaciones, explica cómo se ajustan en el proceso existente.

"""
    else:  # CREATE
        instruction = "**SÍ** crear un nuevo proceso" if decision.instruction_present else "Evaluar si es necesario crear"
        return f"""## Disciplina de Procesos — Stacky

**ACCIÓN RECOMENDADA: {instruction}**

- Razón: {decision.reason}
- Confianza: {decision.confidence:.0%}

**Instrucción para el agente:** Solo crea un nuevo proceso si (1) el ticket lo pide explícitamente O (2) estás seguro de que no existe un proceso equivalente en el catálogo. Si existe algo cercano, REUTILIZA antes de inventar.

"""
```

---

### F1 — Wiring en context_enrichment: inyectar bloque de disciplina

**Objetivo (1 frase).** Modificar `services/context_enrichment.py` para que, cuando `STACKY_PROCESS_DISCIPLINE_ENABLED=true` y el proyecto tiene `process_catalog`, llame a `decide_process_action` y agregue el bloque `process-discipline` al contexto enriquecido.

**Archivo a modificar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/context_enrichment.py`

> **Hechos del código (verificados, NO asumidos):**
> - `enrich_blocks` está en `context_enrichment.py:57` con firma `(*, ticket_id, agent_type, raw_blocks, project_ctx, log)`. **NO** recibe `title`/`description`/`process_catalog`.
> - Título/descripción se capturan localmente como `ticket_title`/`ticket_description` (`context_enrichment.py:87-88`).
> - El catálogo se obtiene vía `load_client_profile(project_name)` (`context_enrichment.py:716`, seam del Plan 42/64).
> - Las funciones `_inject_*` retornan `list[dict]`; el caller hace `blocks = _inject...(blocks, ...)`.

**Test primero:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_process_discipline.py` (crear en F2, **incluye PD-07 de integración**).

#### Cambio 1.1 — Importar el módulo (al principio del archivo, después de imports existentes)

```python
# Plan 67 — disciplina de procesos
from services import process_discipline
```

#### Cambio 1.2 — Función `_inject_process_discipline_block` (nueva, agregar cerca de `_inject_process_catalog_block`, ~línea 694)

```python
# Plan 67 | 2026-06-23 | Inyecta bloque de disciplina de procesos si el flag está ON.
# Patrón idiomático del módulo: retorna list[dict]; `return blocks` en todos los fallbacks.
def _inject_process_discipline_block(
    blocks: list[dict],
    project_name: str | None,
    title: str | None,
    description: str | None,
    log: LogFn,
) -> list[dict]:
    """Si STACKY_PROCESS_DISCIPLINE_ENABLED=true y hay catálogo, decide REUSE vs CREATE y agrega bloque."""
    if not project_name or not (title or description):
        return blocks
    try:
        from services.harness_flags import get_flag
        if not get_flag("STACKY_PROCESS_DISCIPLINE_ENABLED"):
            return blocks
    except Exception:
        return blocks

    # Reusar el seam de carga de profile (Plan 42/64) — NO asumir project_ctx.process_catalog.
    try:
        from services.client_profile import load_client_profile
        profile = load_client_profile(project_name)
        if not isinstance(profile, dict):
            return blocks
        process_catalog = profile.get("process_catalog") or []
        if not process_catalog:
            return blocks
    except Exception as exc:  # noqa: BLE001
        log("warn", f"process-discipline no pudo cargar el catálogo (continuando): {exc}")
        return blocks

    try:
        decision = process_discipline.decide_process_action(
            title=title or "",
            description=description or "",
            process_catalog=process_catalog,
        )
    except Exception as exc:  # noqa: BLE001
        log("warn", f"process-discipline falló al decidir (continuando): {exc}")
        return blocks

    # [ADICIÓN ARQUITECTO] Telemetría decision.action en meta del bloque (Plan 44 observatorio).
    block = {
        "id": "process-discipline",
        "type": "process-discipline",
        "title": "Disciplina de Procesos",
        "content": process_discipline.build_discipline_block(decision),
        "meta": {
            "action": decision.action,
            "process_name": decision.process_name,
            "confidence": decision.confidence,
            "instruction_present": decision.instruction_present,
        },
    }
    log("info", f"process-discipline inyectado: action={decision.action} project={project_name}")
    return list(blocks) + [block]
```

#### Cambio 1.3 — Llamar a `_inject_process_discipline_block` en `enrich_blocks` (después de `_inject_process_catalog_block`, ~línea 109)

Buscar en `enrich_blocks` (`context_enrichment.py:109`) la línea:

```python
    blocks = _inject_process_catalog_block(blocks, project_name, log, query=_rag_query)
```

Agregar **inmediatamente después**:

```python
    # Plan 67 | 2026-06-23 | Disciplina de procesos: decidir REUSE vs CREATE
    blocks = _inject_process_discipline_block(
        blocks=blocks,
        project_name=project_name,
        title=ticket_title,
        description=ticket_description,
        log=log,
    )
```

> **Notas de corrección v2 (C1+C2+C4):** se usa `blocks` (no `enriched_blocks`), se asigna el retorno, y se pasan `ticket_title`/`ticket_description` (locales de `enrich_blocks:87-88`), NO parámetros inexistentes. El catálogo se carga dentro de la función vía `load_client_profile`, igual que `_inject_process_catalog_block`.

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_process_discipline.py" -q
```
Esperado: 7 tests verdes (PD-01 a PD-07).

#### Flag que protege esta fase

- `STACKY_PROCESS_DISCIPLINE_ENABLED` (bool) — default `false` — opt-in desde UI (categoría `contexto_memoria`). **Ver F1b para registro obligatorio.**

#### Impacto por runtime

- **Codex CLI / Claude Code CLI / GitHub Copilot Pro:** idéntico (la disciplina se inyecta en el prompt antes de enviar al runtime).
- **Fallback:** si el flag está OFF, `get_flag` falla, o `process_catalog` no existe → `return blocks` (byte-idéntico al actual).

#### Trabajo del operador

Ninguno. El flag default OFF → comportamiento byte-idéntico. Opt-in desde UI sin pasos manuales.

---

### F1b — Registro de la flag en FLAG_REGISTRY (OBLIGATORIO)

**Objetivo (1 frase).** Registrar `STACKY_PROCESS_DISCIPLINE_ENABLED` en `FLAG_REGISTRY` para que `get_flag` la conozca y aparezca en el panel de flags (Plan 62).

**Archivo a modificar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/harness_flags.py`

**Ancla exacta:** dentro de `FLAG_REGISTRY` (`harness_flags.py:174`), insertar este `FlagSpec` **inmediatamente después** del `STACKY_RAG_CATALOG_TOP_K` (`harness_flags.py:1259-1269`):

```python
    FlagSpec(
        key="STACKY_PROCESS_DISCIPLINE_ENABLED",
        type="bool",
        label="Disciplina de procesos: reusar por default (Plan 67)",
        description=(
            "Plan 67 — Si ON, inyecta un bloque 'process-discipline' que decide "
            "REUTILIZAR un proceso existente del catálogo vs CREAR uno nuevo, según "
            "instrucción explícita del ticket y similitud con el catálogo. "
            "Default OFF = enrich_blocks byte-idéntico al Plan 64."
        ),
        group="contexto_memoria",
        env_only=False,  # editable por UI (Plan 62); NO es kill-switch interno
    ),
```

> **Notas (C3):** `group="contexto_memoria"` ya existe (`harness_flags.py:40` y bucket `:79`). `env_only=False` cumple la regla config-por-UI. Sin este paso, `get_flag("STACKY_PROCESS_DISCIPLINE_ENABLED")` devuelve el default `false` siempre y la flag **no aparece** en el panel → el operador no puede activarla.

#### Cambio F1b.2 — Agregar la key a `_CATEGORY_KEYS["contexto_memoria"]` (C6, OBLIGATORIO)

> **C6 (v2.1) — VERIFICADO.** `harness_flags.py:172-173` exige que toda flag nueva esté **también** en `_CATEGORY_KEYS`, o `test_every_registry_flag_is_categorized` rompe CI. La v2 lo omitía.

Localizar `_CATEGORY_KEYS["contexto_memoria"]` (`harness_flags.py:79-91`) y agregar la key dentro de la tupla, junto a `"STACKY_RAG_CATALOG_TOP_K",`:

```python
    "contexto_memoria": (
        # ... flags existentes ...
        "STACKY_RAG_CATALOG_ENABLED", "STACKY_RAG_CATALOG_TOP_K",
        "STACKY_PROCESS_DISCIPLINE_ENABLED",   # ← AGREGAR (Plan 67, C6 v2.1)
    ),
```

#### Criterio de aceptación binario

```bash
# (1) Flag registrada en FLAG_REGISTRY:
& ".venv/Scripts/python.exe" -c "from services.harness_flags import get_flag; assert get_flag('STACKY_PROCESS_DISCIPLINE_ENABLED') is False; print('OK')"
# (2) Flag categorizada (CI no rompe) — C6 v2.1:
& ".venv/Scripts/python.exe" -m pytest "tests/test_harness_flags.py" -q -k "categor"
```
Esperado: (1) imprime `OK`; (2) verde.

---

### F2 — Tests TDD + ratchet de cobertura

**Objetivo (1 frase).** Crear `tests/test_process_discipline.py` con 8 tests: PD-01..PD-06 cubren el módulo puro (F0), **PD-07 cubre la integración del wiring** (F1, flag ON/OFF gobierna la aparición del bloque `process-discipline`) y PD-08 cubre la negación ampliada (C5).

**Archivo a crear:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_process_discipline.py`

**Tests exactos (copiar tal cual):**

```python
"""Tests de disciplina de procesos (Plan 67)."""
import os
from unittest import mock

import pytest
from services.process_discipline import (
    decide_process_action,
    DisciplineDecision,
    _contains_create_instruction,
    _contains_no_create_prefix,
)


# PD-01: instrucción explícita "crear nuevo proceso" → CREATE
def test_pd01_explicit_create_instruction():
    """Instrucción explícita de crear nuevo proceso → action=CREATE."""
    catalog = [
        {"name": "Mul2Bane", "purpose": "Punto de entrada de la carga", "kind": "carga"},
    ]
    decision = decide_process_action(
        title="Nuevo requerimiento",
        description="Se debe crear un nuevo proceso de carga que procesar archivo X",
        process_catalog=catalog,
    )
    assert decision.action == "CREATE"
    assert decision.instruction_present is True
    assert decision.confidence >= 0.9
    assert "explícita" in decision.reason.lower()


# PD-02: prefijo "modificar" + "proceso" → REUSE (no es creación)
def test_pd02_modify_prefix_is_not_create():
    """Prefijo 'modificar proceso' NO debe interpretarse como creación."""
    catalog = [
        {"name": "Mul2Bane", "purpose": "Punto de entrada de la carga", "kind": "carga"},
    ]
    decision = decide_process_action(
        title="Ajuste Mul2Bane",
        description="Modificar proceso Mul2Bane para agregar campo CLESPECIAL",
        process_catalog=catalog,
    )
    assert decision.instruction_present is False
    assert decision.action == "REUSE"
    assert decision.process_name == "Mul2Bane"


# PD-03: similitud con proceso existente → REUSE
def test_pd03_similarity_triggers_reuse():
    """Coincidencia por similitud de vocabulario → REUSE."""
    catalog = [
        {"name": "Mul2Bane", "purpose": "Lee interfaces de entrada y las carga en tablas IN_", "kind": "carga"},
        {"name": "RsExtrae", "purpose": "Genera interfaces de salida", "kind": "reporte"},
    ]
    decision = decide_process_action(
        title="Carga de clientes",
        description="Procesar archivo de clientes y cargarlo en base de datos",
        process_catalog=catalog,
    )
    assert decision.action == "REUSE"
    assert decision.process_name == "Mul2Bane"
    assert decision.confidence >= 0.4


# PD-04: sin coincidencia clara y sin instrucción → CREATE con baja confianza
def test_pd04_no_match_no_instruction():
    """Sin coincidencia y sin instrucción explícita → CREATE pero con baja confianza."""
    catalog = [
        {"name": "RsExtrae", "purpose": "Genera interfaces de salida", "kind": "reporte"},
    ]
    decision = decide_process_action(
        title="Algoritmo de scoring",
        description="Implementar lógica de scoring de riesgo",
        process_catalog=catalog,
    )
    assert decision.action == "CREATE"
    assert decision.confidence < 0.5
    assert "similitud" in decision.reason.lower() or "no se encontró" in decision.reason.lower()


# PD-05: sin catálogo → CREATE con confianza 0
def test_pd05_no_catalog():
    """Sin catálogo de procesos → CREATE con confianza 0 (fallback)."""
    decision = decide_process_action(
        title="Cualquier tarea",
        description="Descripción cualquiera",
        process_catalog=None,
    )
    assert decision.action == "CREATE"
    assert decision.confidence == 0.0
    assert "no hay catálogo" in decision.reason.lower()


# PD-06: build_discipline_block genera texto no vacío
def test_pd06_build_discipline_block_non_empty():
    """El bloque de disciplina siempre genera texto."""
    from services.process_discipline import build_discipline_block

    decision_reuse = DisciplineDecision(
        action="REUSE",
        process_name="Mul2Bane",
        reason="Coincide con catálogo",
        confidence=0.8,
        instruction_present=False,
    )
    block_reuse = build_discipline_block(decision_reuse)
    assert block_reuse.strip()
    assert "REUTILIZAR" in block_reuse
    assert "Mul2Bane" in block_reuse

    decision_create = DisciplineDecision(
        action="CREATE",
        process_name=None,
        reason="Instrucción explícita",
        confidence=0.95,
        instruction_present=True,
    )
    block_create = build_discipline_block(decision_create)
    assert block_create.strip()
    assert "CREAR" in block_create or "crear" in block_create.lower()


# PD-07: [ADICIÓN ARQUITECTO] integración del wiring — flag ON/OFF gobierna el bloque
def test_pd07_wiring_flag_governs_block(monkeypatch):
    """Con flag ON + catálogo → bloque 'process-discipline' presente y meta.action seteado.
    Con flag OFF → ausente (byte-idéntico). Sin catálogo → ausente."""
    from services.context_enrichment import _inject_process_discipline_block

    fake_profile = {"process_catalog": [
        {"name": "Mul2Bane", "purpose": "carga de interfaces de entrada", "kind": "carga"},
    ]}

    def _noop(level, msg=""):
        return None

    base_blocks: list[dict] = []

    # ON + catálogo → bloque presente
    with mock.patch("services.client_profile.load_client_profile", return_value=fake_profile):
        with mock.patch("services.harness_flags.get_flag", return_value=True):
            result_on = _inject_process_discipline_block(
                blocks=list(base_blocks),
                project_name="PACIFICO",
                title="Carga de clientes",
                description="Procesar archivo de clientes",
                log=_noop,
            )
    ids_on = {b.get("id") for b in result_on}
    assert "process-discipline" in ids_on
    disc = next(b for b in result_on if b.get("id") == "process-discipline")
    assert disc["meta"]["action"] in {"REUSE", "CREATE"}
    assert "content" in disc and disc["content"].strip()

    # OFF → ausente (byte-idéntico)
    with mock.patch("services.harness_flags.get_flag", return_value=False):
        result_off = _inject_process_discipline_block(
            blocks=list(base_blocks),
            project_name="PACIFICO",
            title="Carga de clientes",
            description="Procesar archivo de clientes",
            log=_noop,
        )
    ids_off = {b.get("id") for b in result_off}
    assert "process-discipline" not in ids_off

    # Sin catálogo → ausente
    with mock.patch("services.client_profile.load_client_profile", return_value={"process_catalog": []}):
        with mock.patch("services.harness_flags.get_flag", return_value=True):
            result_nocat = _inject_process_discipline_block(
                blocks=list(base_blocks),
                project_name="PACIFICO",
                title="x",
                description="y",
                log=_noop,
            )
    ids_nocat = {b.get("id") for b in result_nocat}
    assert "process-discipline" not in ids_nocat


# PD-08 (C5): negación ampliada — "nunca crees" no debe contar como instrucción de crear
def test_pd08_negation_never_create():
    """'nunca crees un proceso' NO debe disparar CREATE por instrucción explícita."""
    catalog = [{"name": "Mul2Bane", "purpose": "carga", "kind": "carga"}]
    decision = decide_process_action(
        title="Recordatorio",
        description="Nunca crees un nuevo proceso sin autorización",
        process_catalog=catalog,
    )
    assert decision.instruction_present is False
```

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_process_discipline.py" -q
```
Esperado: 8 tests verdes (PD-01 a PD-08).

#### Ratchet (Plan 49 F4)

Agregar `tests/test_process_discipline.py` a `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh` y `scripts/run_harness_tests.ps1` (si existe). Verificado: el meta-test del Plan 49 F4 exige que todo test nuevo del backend figure en la lista sh+ps1.

#### Flag que protege esta fase

- `STACKY_PROCESS_DISCIPLINE_ENABLED` (bool) — default `false` — opt-in desde UI.

#### Impacto por runtime

- **Codex CLI / Claude Code CLI / GitHub Copilot Pro:** idéntico.

#### Trabajo del operador

Ninguno. Tests TDD primero, luego implementación.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| El agente ignora el bloque de disciplina | La disciplina es INSTRUCTIVA ("Debes usar..."). Si el agente la ignora, el output puede ser capturado por el arnés de post-run (Plan 49/50) y marcado `needs_review`. |
| Falsos positivos en similitud (Jaccard) | Umbral 0.4 conservador + stopword filtering (C5). Falso positivo → "REUSE" pero el operador corrige. No hay daño (es guía). |
| Falsos negativos (debería REUSE pero dice CREATE) | Si similitud < 0.4, el bloque advierte "solo crea si estás seguro". No es bloqueo. |
| Catálogo vacío o mal configurado | Fallback a "CREATE con confianza 0" + "no hay catálogo". `return blocks` (no inyecta). |
| Flag no registrada → operador no puede activar | **F1b obligatorio** registra la flag en `FLAG_REGISTRY` con `env_only=False`. PD-07 + smoke `-c` lo verifican. |
| Duplicación con Plan 64 (RAG TF-IDF) | No duplica: 64 = truncar catálogo a top-K; 67 = gate binario REUSE/CREATE. Coexisten (ver §2). |

---

## 6. Fuera de scope

- Modificar el comportamiento de los agentes (esto es SOLO inyección de contexto).
- Validar en tiempo de ejecución si el proceso creado realmente existe (futuro plan de verificación).
- Modificar el catálogo de procesos automatizadamente (el catálogo se edita por UI).
- Prohibir la creación de procesos (la disciplina es RECOMENDACIÓN, no bloqueo duro).

---

## 7. Glosario

- **process_catalog:** lista de procesos del cliente en `client_profile`, con `{name, purpose, kind}`.
- **Disciplina de procesos:** regla que decide REUTILIZAR vs CREAR basándose en instrucción explícita y similitud.
- **Jaccard:** métrica de similitud = intersección / unión sobre tokens limpios (sin stopwords).
- **Instrucción explícita:** el ticket contiene palabras como "crear nuevo proceso", "nuevo batch", etc., sin negación (`no`/`nunca`/`sin`/`evitar`/`prohibido`/`no vuelvas`).
- **REUSE vs CREATE:** las dos acciones posibles. REUSE indica un proceso existente del catálogo; CREATE indica que se justifica crear algo nuevo.

---

## 8. Orden de implementación

1. **F0** — Crear `services/process_discipline.py` (módulo puro).
2. **F2** — Crear `tests/test_process_discipline.py` (tests TDD PD-01..PD-06 puros).
3. **F1b** — Registrar flag en `FLAG_REGISTRY` (`harness_flags.py`).
4. **F1** — Modificar `services/context_enrichment.py` (wiring: Cambio 1.1, 1.2, 1.3).
5. **F2 (PD-07, PD-08)** — Tests de integración del wiring + negación ampliada.
6. Verificar 8 tests verdes + smoke de flag.
7. Commitear y push manual.

---

## 9. Definición de Hecho (DoD)

- [ ] `services/process_discipline.py` existe con todas las funciones.
- [ ] `tests/test_process_discipline.py` pasa con **8 tests verdes** (PD-01 a PD-08, incluye PD-07 de integración).
- [ ] `services/context_enrichment.py` llama a `_inject_process_discipline_block` con `ticket_title`/`ticket_description`/`project_name` (NO `title`/`description`/`enriched_blocks` inexistentes).
- [ ] Flag `STACKY_PROCESS_DISCIPLINE_ENABLED` registrada en `FLAG_REGISTRY` (`harness_flags.py`, `env_only=False`, `group="contexto_memoria"`).
- [ ] `tests/test_process_discipline.py` agregado a `HARNESS_TEST_FILES` (sh + ps1).
- [ ] `npx tsc --noEmit` en `frontend/` = 0 errores (no se toca frontend, pero se verifica).
- [ ] Commit con mensaje `docs(plan-67): disciplina de procesos reusar-por-default` + trailer de co-autoría.
- [ ] Memoria actualizada (opcional, para rastreo).

---

**Resumen de 5 líneas:**

Este plan introduce una disciplina de procesos que guía al agente: REUTILIZAR un proceso existente del catálogo por default, CREAR solo cuando hay instrucción explícita (con negación ampliada) o no hay coincidencia. KPI: reducción de procesos fantasmas y claridad en tareas. Cero trabajo del operador: flag default OFF registrada en `FLAG_REGISTRY` (F1b), opt-in desde UI. Paridad 3 runtimes: el módulo corre en backend antes de cualquier runtime. Implementación F0→F1b→F1→F2 con 8 tests (PD-07 de integración + telemetría decision.action como adiciones del arquitecto).
