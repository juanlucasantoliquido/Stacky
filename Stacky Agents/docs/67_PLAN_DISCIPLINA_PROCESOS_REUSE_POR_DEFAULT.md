# Plan 67 — Disciplina de procesos: reutilizar por default, crear solo con instrucción explícita

> Versión: **v1** | Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 66 → este plan = **67**.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Hoy los agentes de Stacky (Business, Functional, Technical) pueden crear nuevos procesos o tareas sin una disciplina clara que distinga entre REUTILIZAR un proceso existente del catálogo (`process_catalog`) vs CREAR uno nuevo. Esto genera ambigüedad en la generación de código Batch: el agente puede inventar procesos duplicados, crear "fantasmas" que no existen en la arquitectura real, o malinterpretar cuándo usar Mul2Bane/IncHost/RSCore/RsExtrae vs cuándo proponer algo nuevo. Este plan introduce una **disciplina explícita de procesos** con dos reglas duras: (1) REUTILIZAR por default un proceso del catálogo si el ticket NO pide explícitamente crear uno nuevo; (2) CREAR solo cuando el ticket contiene una instrucción explícita del operador ("crear nuevo proceso", "nuevo batch", etc.) o cuando NO existe ningún proceso en el catálogo que cubra la necesidad. La disciplina se codifica en un módulo `process_discipline.py` con funciones PURAS que el agente consulta antes de proponer código, y se inyecta como bloque de contexto en el prompt del agente.

**KPI / impacto esperado:**
- **Reducción de procesos fantasmas:** el agente deja de inventar procesos que no existen en la arquitectura real.
- **Claridad en tareas/épicas:** el output del agente distingue explícitamente "REUTILIZO <proceso>" vs "CREO nuevo proceso <nombre>".
- **Tokens de contexto:** el bloque de disciplina es compacto (~300 tokens) y solo se inyecta cuando `process_catalog` existe en el profile.
- **Trabajo del operador:** ninguno. La disciplina se aplica automáticamente cuando el flag está ON (default OFF para opt-in).
- **Paridad 3 runtimes:** el módulo corre en el backend antes de cualquier runtime → idéntico para Codex, Claude Code y GitHub Copilot Pro.

---

## 2. Por qué ahora / gap que cierra

- **Plan 42** introdujo `process_catalog` en `client_profile` y el grounding de épicas.
- **Plan 45** agregó el catálogo de procesos editable por UI (`ClientProfileEditor`).
- **Planes 49/50** endurecieron el arnés con blindaje determinista y saneamiento de épica.
- **Gap verificado:** los agentes NO tienen hoy una regla explícita que diga "reutiliza por default". Un agente puede leer `process_catalog` y aún así inventar un nuevo proceso sin justificación, o malinterpretar un requerimiento y crear un duplicado.
- **Evidencia real:** el ejemplo del prompt del operador menciona "Estructurar un poco más las tareas para que quede claro cuándo se debe crear un nuevo proceso y cuándo reutilizar uno" y "Nunca debe de crear un proceso sin una instrucción explícita". Esto es exactamente lo que el plan codifica.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** la disciplina corre en el backend (Python puro) antes de cualquier llamada al runtime. Idéntico para Codex CLI, Claude Code CLI y GitHub Copilot Pro. No hay rama por runtime.
- **Cero trabajo extra al operador:** flag `STACKY_PROCESS_DISCIPLINE_ENABLED` default OFF. OFF → byte-idéntico al actual (sin bloque de disciplina). Opt-in desde UI.
- **Human-in-the-loop intacto:** la disciplina guía al agente, pero el operador sigue aprobando el resultado. No hay autonomía nueva.
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** cero nuevas dependencias (stdlib `re`, `dataclasses`). Sin llamadas a red. Fallback: si el módulo falla → no inyecta bloque (degradación controlada).
- **Reuso obligatorio:** reutiliza `client_profile.process_catalog` ya cargado, el bloque `"process-catalog"` existente, el sistema de flags de `harness_flags.FLAG_REGISTRY`.
- **Regla dura config-por-UI:** el flag se registra en `FLAG_REGISTRY` → aparece en el panel de flags sin tocar el frontend.

---

## 4. Fases

> **Orden de dependencia:** F0 → F1 → F2.
> F0 = módulo disciplina puro; F1 = wiring en context_enrichment; F2 = tests + ratchet.

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


def _contains_create_instruction(text: str) -> bool:
    """Detecta si el texto contiene una instrucción EXPLÍCITA de crear algo nuevo."""
    text_lower = text.lower()
    for keyword in _CREATE_KEYWORDS:
        if keyword in text_lower:
            # Verificar que no esté negado
            pattern = rf"no\s+{re.escape(keyword)}|sin\s+{re.escape(keyword)}|evitar\s+{re.escape(keyword)}"
            if not re.search(pattern, text_lower):
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
    """Encuentra el proceso del catálogo más similar al query.

    Returns:
        (process_name, similarity_score) donde similarity_score está en 0..1
    """
    if not process_catalog:
        return None, 0.0

    query_lower = query.lower()
    query_words = set(re.findall(r"\b\w+\b", query_lower))

    best_name = None
    best_score = 0.0

    for proc in process_catalog:
        name = proc.get("name", "")
        purpose = proc.get("purpose", "")
        kind = proc.get("kind", "")

        # Texto completo del proceso para comparar
        proc_text = f"{name} {purpose} {kind}".lower()
        proc_words = set(re.findall(r"\b\w+\b", proc_text))

        # Similitud Jaccard: intersección / unión
        if not query_words or not proc_words:
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

    Args:
        title: título del ticket
        description: descripción del ticket
        process_catalog: lista de dicts con {name, purpose, kind} desde client_profile

    Returns:
        DisciplineDecision con action, process_name, reason, confidence, instruction_present
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

    # Umbral de similitud: 0.4 significa "bastante superposición de vocabulario"
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
    if process_catalog and len(process_catalog) > 0:
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

**Archivo a modificar:** `N:/GIT/RS/STACKY\Stacky\Stacky Agents\backend\services\context_enrichment.py`

**Test primero:** `N:/GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_process_discipline.py` (crear en F2 antes de este cambio).

#### Cambio 1.1 — Importar el módulo (al principio del archivo, después de imports existentes)

```python
# Plan 67 — disciplina de procesos
from services import process_discipline
```

#### Cambio 1.2 — Función `_inject_process_discipline_block` (nueva, agregar cerca de `_inject_process_catalog_block`)

```python
# Plan 67 | 2026-06-23 | Inyecta bloque de disciplina de procesos si el flag está ON
def _inject_process_discipline_block(
    blocks: list[dict],
    title: str,
    description: str,
    process_catalog: list[dict] | None,
) -> None:
    """Si STACKY_PROCESS_DISCIPLINE_ENABLED=true y hay catálogo, decide REUSE vs CREATE y agrega bloque."""
    if not process_catalog:
        return
    try:
        from services.harness_flags import get_flag
        if not get_flag("STACKY_PROCESS_DISCIPLINE_ENABLED"):
            return
    except Exception:
        return

    decision = process_discipline.decide_process_action(
        title=title,
        description=description,
        process_catalog=process_catalog,
    )

    discipline_text = process_discipline.build_discipline_block(decision)

    blocks.append({
        "type": "process-discipline",
        "title": "Disciplina de Procesos",
        "content": discipline_text,
        # Metadatos para telemetría (opcional)
        "meta": {
            "action": decision.action,
            "process_name": decision.process_name,
            "confidence": decision.confidence,
            "instruction_present": decision.instruction_present,
        },
    })
```

#### Cambio 1.3 — Llamar a `_inject_process_discipline_block` en `enrich_blocks` (después de `_inject_process_catalog_block`)

Buscar la función `enrich_blocks` (cerca de línea 150-250) y agregar, inmediatamente después de la llamada a `_inject_process_catalog_block`:

```python
    # Plan 67 | 2026-06-23 | Disciplina de procesos: decidir REUSE vs CREATE
    _inject_process_discipline_block(
        enriched_blocks,
        title=title,
        description=description,
        process_catalog=project_ctx.process_catalog if project_ctx else None,
    )
```

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_process_discipline.py" -q
```
Esperado: 5 tests verdes (PD-01 a PD-05).

#### Flag que protege esta fase

- `STACKY_PROCESS_DISCIPLINE_ENABLED` (bool) — default `false` — opt-in desde UI (categoría `contexto_memoria`).

#### Impacto por runtime

- **Codex CLI:** idéntico (la disciplina se inyecta en el prompt antes de enviar al CLI).
- **Claude Code CLI:** idéntico.
- **GitHub Copilot Pro:** idéntico.
- **Fallback:** si el flag está OFF o `process_catalog` no existe, el comportamiento es byte-idéntico al actual (no se inyecta nada).

#### Trabajo del operador

Ninguno. El flag default OFF → comportamiento byte-idéntico. Opt-in desde UI sin pasos manuales.

---

### F2 — Tests TDD + ratchet de cobertura

**Objetivo (1 frase).** Crear `tests/test_process_discipline.py` con 5 tests que cubran (1) instrucción explícita de crear → CREATE, (2) prefijo de no-crear → REUSE, (3) coincidencia por similitud → REUSE, (4) sin coincidencia y sin instrucción → CREATE con baja confianza, (5) sin catálogo → CREATE con confianza 0.

**Archivo a crear:** `N:/GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_process_discipline.py`

**Tests exactos (copiar tal cual):**

```python
"""Tests de disciplina de procesos (Plan 67)."""
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
    # No tiene instrucción de crear porque empieza con "modificar"
    assert decision.instruction_present is False
    # Coincide con Mul2Bane → REUSE
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
    # "cargar", "base de datos" coincide con propósito de Mul2Bane
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
    # RsExtrae es reporte, no scoring → no coincide suficiente
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
```

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_process_discipline.py" -q
```
Esperado: 6 tests verdes (PD-01 a PD-06).

#### Flag que protege esta fase

- `STACKY_PROCESS_DISCIPLINE_ENABLED` (bool) — default `false` — opt-in desde UI.

#### Impacto por runtime

- **Codex CLI:** idéntico.
- **Claude Code CLI:** idéntico.
- **GitHub Copilot Pro:** idéntico.
- **Fallback:** idéntico.

#### Trabajo del operador

Ninguno. Tests TDD primero, luego implementación.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| El agente ignora el bloque de disciplina | La disciplina es INSTRUCTIVA ("Debes usar..."). Si el agente la ignora, el output del agente puede ser capturado por el arnés de post-run (plan 49/50) y marcado como needs_review si crea un proceso sin justificación. |
| Falsos positivos en similitud (Jaccard ingenuo) | El umbral 0.4 es conservador. Falso positivo → el agente recibe "REUSE" pero podría ser CREATE → el operador puede corregir. No hay daño. |
| Falsos negativos (debería REUSE pero dice CREATE) | Si similitud < 0.4, el bloque advierte "solo crea si estás seguro". El agente puede evaluar. No es bloqueo, es guía. |
| Catálogo vacío o mal configurado | Fallback a "CREATE con confianza 0" + mensaje "no hay catálogo". El operador ve el bloque y puede configurar el catálogo si lo desea. |

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
- **Jaccard:** métrica de similitud entre conjuntos = intersección / unión. Aplicada a vocabulario del ticket vs proceso.
- **Instrucción explícita:** el ticket contiene palabras como "crear nuevo proceso", "nuevo batch", etc., sin negación.
- **REUSE vs CREATE:** las dos acciones posibles. REUSE indica un proceso existente del catálogo; CREATE indica que se justifica crear algo nuevo.

---

## 8. Orden de implementación

1. **F0** — Crear `services/process_discipline.py` (módulo puro).
2. **F2** — Crear `tests/test_process_discipline.py` (tests TDD).
3. **F1** — Modificar `services/context_enrichment.py` (wiring).
4. Verificar tests verdes.
5. Commitear y push manual.

---

## 9. Definición de Hecho (DoD)

- [ ] `services/process_discipline.py` existe con todas las funciones.
- [ ] `tests/test_process_discipline.py` pasa con 6 tests verdes.
- [ ] `services/context_enrichment.py` llama a `_inject_process_discipline_block`.
- [ ] Flag `STACKY_PROCESS_DISCIPLINE_ENABLED` registrada en `FLAG_REGISTRY`.
- [ ] `npx tsc --noEmit` en `frontend/` = 0 errores (no se toca frontend, pero se verifica).
- [ ] Commit con mensaje `docs(plan-67): disciplina de procesos reusar-por-default` + trailer de co-autoría.
- [ ] Memoria actualizada (opcional, pero recomendado para rastreo).

---

**Resumen de 5 líneas:**

Este plan introduce una disciplina de procesos que guía al agente: REUTILIZAR un proceso existente del catálogo por default, CREAR solo cuando hay instrucción explícita o no hay coincidencia. KPI: reducción de procesos fantasmas y claridad en tareas. Cero trabajo del operador: flag default OFF, opt-in desde UI. Paridad 3 runtimes: el módulo corre en backend antes de cualquier runtime. Implementación F0→F2: módulo puro + wiring + tests TDD.
