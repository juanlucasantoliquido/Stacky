# Plan 48 — Memoria que Empuja: rechazos previos como anti-patrones inyectados (cerrar el loop del veredicto humano)

> **Estado: IMPLEMENTADO 2026-06-19.** Evidencia:
> - F0/F1 módulo: `backend/services/rejection_lessons.py` (`build_items`, `build_prefix`, `load_for_run` reusa `memory_store.list_observations`).
> - F2 inyección CLI: `backend/services/context_enrichment.py` (`_inject_rejection_lessons` + encadenado tras `_inject_cli_fewshot`; prioridad `rejection-lessons`=82 en `_BLOCK_PRIORITY`).
> - F3 paridad Copilot: `backend/agents/base.py:97-119` (dentro de `use_anti_patterns`, mismo flag, dedupe vs FA-11).
> - F4 telemetría: bloque CLI lleva `metadata["rejection_lessons_count"]`; base.py setea `meta["rejection_lessons_count"]`.
> - F5 flag: `backend/services/harness_flags.py` (FlagSpec `STACKY_PUSH_REJECTIONS_ENABLED`, env_only) + `.env.example`.
> - Tests verdes: `test_rejection_lessons.py` 12, `test_inject_rejection_lessons.py` 7, `test_base_rejection_lessons.py` 4, `test_harness_flags.py` (caso nuevo); regresión `test_capture_operator_note.py`+`test_skills_injection.py` 14, `test_context_enrichment.py` 8. 0 fallos.
> - Ajuste vs plan: el ORM `StackyMemoryObservation` vive en `services/memory_store.py` (no `models.py`); `load_for_run` reusa `list_observations` (filtra type/status/project, ordena updated_at DESC) en vez del query crudo.

> **Estado original: PROPUESTO (no implementado).**
> Convergencia del debate con StackyArquitectoBrainstormer. Núcleo elegido: **idea 2 (Memoria que Empuja)** con un componente acotado de **idea 4 (pre-vuelo barato sin LLM)** fusionado como guardarraíl. Descartadas/diferidas: 1, 3, 5, 6 (ver §0).

---

## 0. Debate y veredicto de diseño

El Brainstormer propuso fusionar idea 2 (mejorar el INPUT con memoria de rechazos) + idea 1 (doble-pase para mejorar el OUTPUT). **Rechazo el doble-pase silencioso (idea 1) como núcleo**: duplica tokens en CADA run sobre rieles UltraCode, y el sistema YA tiene pases correctivos dirigidos y baratos (Q1.1 corrección de criterios, `epic_repair`, A1.1 gate de aceptación) que se disparan SOLO cuando algo falla, no siempre. Pagar x2 incondicional para a veces mejorar es mala relación valor/costo. Lo dejo fuera de scope.

**Acepto idea 2 como núcleo, pero el código me obliga a precisar el gap real** (verificado, no asumido):
- `post_run_memory.capture_operator_note` (`post_run_memory.py:199`) YA promueve la nota humana de un rechazo a memoria `operator_note`, con tags `rejected_reason`/`approval_condition` (`:237-241`). El loop de CAPTURA del viejo plan 47 está **implementado**, contradiciendo el supuesto del Brainstormer de que "casi nadie consume". El gap no es capturar.
- El gap es el **CONSUMO**: esas memorias `operator_note` solo pueden volver al próximo run por el bloque `stacky-memory` (`context_enrichment.py:667`), que las rankea por **TF-IDF coseno contra el título/descripción del ticket** (`memory_store.py:1012-1036`), sin ningún boost por ser una lección de rechazo, compitiendo de igual a igual con resúmenes de sesión, y todo gateado por `STACKY_MEMORY_INJECTION_ENABLED` (default OFF). Una lección "no inventes procesos batch" casi nunca gana relevancia coseno contra el texto de un brief nuevo. **El conocimiento se guarda pero no empuja.**
- Existe `anti_patterns.py` (FA-11) con `relevant()`/`build_prefix()` que inyecta anti-patrones de forma **imperativa** ("Evitá X porque Y", como restricción dura), pero (a) se alimenta de una tabla `anti_patterns` **separada** que el operador llena a mano, NO de los rechazos capturados; y (b) su inyección vive en `agents/base.py:90-104`, que es el path del runtime **github_copilot** — los runtimes **Codex CLI y Claude Code CLI** (que pasan por `context_enrichment.py`) **NO reciben anti-patrones**. Asimetría de runtime real.

**Veredicto.** El máximo valor/costo/reuso es un **puente determinístico** que toma las memorias `operator_note` de veredictos `rejected`/`approved_with_notes` (ya capturadas, gratis) y las inyecta como **anti-patrones imperativos** (canal que ya existe y es más fuerte que el pool TF-IDF), **con paridad en los 3 runtimes** (cerrando de paso la asimetría Copilot-vs-CLI de FA-11). Cero tokens nuevos de generación (no hay doble-pase), cero trabajo del operador (la nota ya la escribió al rechazar), default OFF.

- **Idea 3 (termómetro de confianza):** ya existe `confidence.overall` capturado (`post_run_memory.py:73`) y rescatado por planes previos; un score nuevo es redundante. Diferida.
- **Idea 5 (adversario interno / peer-review):** moonshot caro (segundo agente = segundo run completo). Viola el riel de costo. Fuera.
- **Idea 6 (few-shot vivo):** **ya implementada** — Q1.2 `_inject_cli_fewshot` (`context_enrichment.py:1189`) recicla outputs aprobados como ejemplos. Solapamiento total. Fuera.
- **Idea 4 (pre-vuelo barato):** la fusiono como guardarraíl mínimo, NO como núcleo: un check de tamaño/cantidad sin LLM que evita que el bloque de anti-patrones de rechazos crezca sin techo (poda determinística). Sin gasto.

Honestidad de costo (rieles UltraCode): este plan **NO agrega un solo token de generación de LLM**. Solo agrega texto al system prompt (acotado por caps existentes) a partir de datos ya almacenados. El riesgo de costo es marginal (más prompt) y está topado por `_MAX_*` y por el cap de presupuesto de contexto que ya existe.

---

## 1. Título, objetivo y KPI

**Título.** Memoria que Empuja — rechazos previos del operador inyectados como anti-patrones imperativos, con paridad en los 3 runtimes.

**Objetivo (1 párrafo).** Cerrar el loop abierto entre la CAPTURA del veredicto humano (ya implementada en `capture_operator_note`) y su CONSUMO en el próximo run. Hoy las lecciones de rechazo quedan en memoria `operator_note` pero solo reingresan por relevancia TF-IDF débil y gateada. Este plan agrega un puente determinístico que, ante un nuevo run del mismo proyecto+tipo de agente, recupera las memorias `operator_note` de veredictos `rejected`/`approved_with_notes` y las inyecta como **anti-patrones imperativos** ("Evitá X porque el operador rechazó esto antes"), reusando el canal FA-11 existente y extendiéndolo a los runtimes CLI que hoy no lo reciben. El operador no hace nada nuevo: la nota ya la escribió al rechazar.

**KPI/impacto.**
- Primario: **tasa de re-rechazo por el MISMO motivo** baja (un motivo ya rechazado en el proyecto+agente reaparece como restricción dura en el siguiente run). Medible vía telemetría `metadata["pushed_antipatterns"]` (cuántas lecciones de rechazo se inyectaron) cruzado con el bucket `needs_review` del panel de salud (plan 46).
- Secundario: **paridad de anti-patrones entre runtimes** = 1.0 (los 3 runtimes reciben anti-patrones; hoy solo github_copilot).
- Con flag OFF: comportamiento byte-idéntico al actual.

---

## 2. Por qué ahora / gap (apoyado en 41-47 y código)

- **Plan 47 (vigente, "auto-recuperación del entregable")** rescata el artefacto del disco: resuelve el bug del entregado perdido, pero NO mejora la CALIDAD del contenido generado. Es ortogonal y complementario a este plan.
- **Plan 47 anterior ("veredicto→memoria"), RECHAZADO** por incremental: capturaba notas que "casi nunca existen" y agregaba botones. Pero la pieza de captura **terminó implementándose igual** (`capture_operator_note` existe). Este plan NO agrega captura ni botones: solo **consume** lo que ya se captura, de forma invisible. Respeta la lección del plan 41 (cero pasos nuevos).
- **Gap verificado en código:**
  - `capture_operator_note` escribe `operator_note` con tags `rejected_reason`/`approval_condition` (`post_run_memory.py:237-241`). ✅ captura.
  - `get_context_for_run` rankea por coseno TF-IDF (`memory_store.py:1012-1036`); `operator_note` no tiene boost ni canal imperativo. ❌ consumo débil.
  - `anti_patterns.relevant`/`build_prefix` inyectan imperativo (`anti_patterns.py:64-93`) pero desde tabla manual y SOLO en `agents/base.py:90-104` (runtime github_copilot). ❌ no se alimenta de rechazos; ❌ no llega a Codex/Claude CLI.
- **Oportunidad:** unir las dos piezas que ya existen (captura `operator_note` + canal anti-patrón imperativo) y darles paridad de runtime. Trabajo de plomería determinística, no de IA.

---

## 3. Principios y guardarraíles

1. **Invisible / opt-in default OFF.** Todo detrás de `STACKY_PUSH_REJECTIONS_ENABLED` (bool, default `false`). OFF → cero cambios.
2. **Cero tokens de generación.** No hay doble-pase ni segundo agente. Solo se agrega texto (acotado) al system prompt desde datos ya almacenados.
3. **Human-in-the-loop intacto.** El plan no decide ni aprueba; consume lo que el humano ya decidió (su rechazo + nota). No genera contenido nuevo.
4. **Determinístico, implementable por modelo menor.** "Buscá memorias `operator_note` con tag `rejected_reason`/`approval_condition` del proyecto+agente, ordená por recencia, tomá las primeras N, formateálas como anti-patrón imperativo." Sin IA, sin ambigüedad.
5. **Paridad 3 runtimes.** El puente vive en `context_enrichment.py` (path de Codex CLI y Claude Code CLI) Y se reusa en `agents/base.py` (path github_copilot). Fallback explícito por fase.
6. **Mono-operador sin auth.** No toca usuarios ni RBAC.
7. **No degradar.** try/except best-effort en cada inyección; ante cualquier fallo se omite el bloque y el run continúa idéntico. Poda determinística de tamaño (idea 4 fusionada) evita inflar el prompt.
8. **No duplicar conocimiento.** Si una lección de rechazo YA existe como anti-patrón manual (FA-11 tabla), no se inyecta dos veces el mismo texto (dedupe por `pattern` normalizado).

---

## 4. Fases

> Entorno de tests (TODAS las fases backend):
> Intérprete: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe`
> cwd: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> Correr **por archivo** (full-suite contaminada): `.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`
> Frontend: este plan NO toca frontend (el toggle del flag ya lo expone el panel de flags del plan 33).

---

### F0 — Módulo puro: lecciones de rechazo → ítems de anti-patrón (sin Flask, sin red)

**Objetivo (1 frase).** Crear un módulo que tome filas de memoria `operator_note` (dicts) y devuelva una lista de ítems `_Loaded` compatibles con `anti_patterns.build_prefix`, deduplicados y podados.

**Valor.** Núcleo determinístico, testeable en memoria; agnóstico al runtime y a la fuente (recibe dicts).

**Archivo a CREAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\rejection_lessons.py`

**Contenido EXACTO:**
```python
"""F0 (plan 48) — Memoria que Empuja: convierte memorias `operator_note` de
veredictos rechazados/condicionados en ítems de anti-patrón imperativos.

PURO respecto de red/DB/Flask: recibe dicts (forma de memory_store.to_dict) y
devuelve ítems listos para anti_patterns.build_prefix. La carga desde DB y la
inyección viven en F1/F2.
"""
from __future__ import annotations

from dataclasses import dataclass

# Reusa la forma de item que anti_patterns.build_prefix ya sabe renderizar.
# (anti_patterns._Loaded tiene .pattern, .reason, .example). Replicamos el shape
# para no importar la dataclass interna y evitar acoplamiento.
@dataclass
class RejectionItem:
    pattern: str
    reason: str
    example: str | None = None


# Tags que marcan una memoria como lección de rechazo (los setea capture_operator_note).
REJECTION_TAGS = ("rejected_reason", "approval_condition")
_MAX_ITEMS = 6          # techo de lecciones inyectadas (poda; idea 4 fusionada)
_MAX_PATTERN_CHARS = 280
_MAX_REASON_CHARS = 280


def _norm(text: str) -> str:
    """Normaliza para dedupe: minúsculas, espacios colapsados."""
    return " ".join((text or "").lower().split())


def build_items(
    memories: list[dict],
    *,
    existing_patterns: set[str] | None = None,
    max_items: int = _MAX_ITEMS,
) -> list[RejectionItem]:
    """Convierte memorias operator_note en ítems de anti-patrón.

    - `memories`: dicts con al menos {'content', 'tags', 'title'} (memory_store.to_dict).
      Se asume YA ordenadas por recencia DESC por el caller (F1).
    - Solo procesa memorias cuyo `tags` intersecta REJECTION_TAGS.
    - `existing_patterns`: set de patrones normalizados ya inyectados por FA-11
      (dedupe cruzado, principio 8). Se saltean coincidencias.
    - Trunca pattern/reason; descarta vacíos; corta en max_items.
    - El `content` de operator_note tiene forma "Veredicto: X\\n\\n<nota>".
      El pattern es la primera línea no vacía de la nota; el reason es el contexto.
    """
    seen = set(existing_patterns or set())
    out: list[RejectionItem] = []
    for m in memories:
        if len(out) >= max_items:
            break
        tags = m.get("tags") or []
        if not any(t in REJECTION_TAGS for t in tags):
            continue
        content = (m.get("content") or "").strip()
        if not content:
            continue
        # Separar "Veredicto: X" del cuerpo de la nota.
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        note_lines = [ln for ln in lines if not ln.lower().startswith("veredicto:")]
        if not note_lines:
            continue
        pattern = note_lines[0][:_MAX_PATTERN_CHARS]
        key = _norm(pattern)
        if not key or key in seen:
            continue
        seen.add(key)
        # reason: resto de la nota o un default explicativo.
        rest = " ".join(note_lines[1:]).strip()
        reason = (rest or "El operador rechazó/condicionó un output por este motivo en este proyecto.")[:_MAX_REASON_CHARS]
        out.append(RejectionItem(pattern=pattern, reason=reason, example=None))
    return out


def build_prefix(items: list[RejectionItem]) -> str:
    """Render imperativo, mismo formato que anti_patterns.build_prefix pero con
    encabezado que aclara el origen (rechazos del operador)."""
    if not items:
        return ""
    body_lines = []
    for i, it in enumerate(items, 1):
        body_lines.append(f"{i}. **Evitá**: {it.pattern}\n   **Por qué**: {it.reason}")
    return (
        "## Lecciones de rechazos previos (el operador YA rechazó esto en este proyecto)\n"
        "Estos motivos causaron rechazo o aprobación condicionada en runs anteriores. "
        "Tratalos como restricciones duras: NO repitas estos errores.\n\n"
        + "\n\n".join(body_lines)
        + "\n"
    )
```

**Tests PRIMERO.** Archivo a CREAR: `backend\tests\test_rejection_lessons.py`
> Sin DB. Construir dicts a mano con la forma de `memory_store.to_dict`.
Casos:
- `test_no_memories_returns_empty` → `build_items([])` → `[]`; `build_prefix([])` → `""`.
- `test_ignores_non_rejection_tags` → memoria con `tags=["agent","session"]` (sin REJECTION_TAGS) → ignorada → `[]`.
- `test_extracts_pattern_from_rejected_note` → `{"content":"Veredicto: rejected\n\nNo inventes procesos batch\nUsar solo el catálogo", "tags":["functional","operator_note","rejected","rejected_reason"]}` → 1 ítem con `pattern=="No inventes procesos batch"` y `reason` que contiene "Usar solo el catálogo".
- `test_dedupes_against_existing` → memoria con pattern "No inventes procesos batch" + `existing_patterns={"no inventes procesos batch"}` → `[]` (ya cubierto por FA-11).
- `test_dedupes_internal` → dos memorias con la misma primera línea → 1 ítem.
- `test_respects_max_items` → 10 memorias de rechazo distintas, `max_items=6` → `len==6`.
- `test_truncates_long_pattern` → primera línea de 500 chars → `len(pattern)==280`.
- `test_build_prefix_imperative_format` → 2 ítems → string contiene "Lecciones de rechazos previos", "**Evitá**", ambos patterns.
- `test_approval_condition_tag_also_included` → memoria con tag `approval_condition` (sin `rejected_reason`) → se incluye.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_rejection_lessons.py -q`
**Criterio de aceptación BINARIO.** 9 passed, 0 failed.
**Flag que la protege.** Ninguno (módulo inerte hasta F1/F2).
**Impacto por runtime.** Ninguno (puro). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F1 — Cargar las lecciones de rechazo desde memory_store (consulta acotada por proyecto+agente)

**Objetivo (1 frase).** Exponer una función que devuelva los `RejectionItem` del proyecto+agente, leyendo memorias `operator_note` activas con tags de rechazo, ordenadas por recencia.

**Valor.** Conecta F0 a la fuente real (memorias capturadas) sin que F0 conozca la DB.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\rejection_lessons.py` (agregar a F0).

**Verificación previa OBLIGATORIA (citar en el PR).** Confirmar la firma exacta del query de memorias por tipo en `memory_store.py:840-841` (`q.filter(StackyMemoryObservation.type == type)`) y si existe un helper público de listado por tipo+proyecto. Si existe `list_by_type(project, type, status, limit)` o similar, reusarlo; si NO, usar el patrón de query directo mostrado abajo.

**Agregar:**
```python
def load_for_run(
    *,
    project: str | None,
    agent_type: str | None,
    existing_patterns: set[str] | None = None,
    max_items: int = _MAX_ITEMS,
) -> list[RejectionItem]:
    """Carga memorias operator_note del proyecto y construye RejectionItems.

    - project None → [] (no hay contexto de proyecto).
    - Filtra: type == 'operator_note', status == 'active', scope == 'project',
      project == <project>. Ordena por updated_at DESC (recencia).
    - agent_type: se PREFIERE el mismo agent_type pero NO se exige (una lección de
      rechazo funcional puede aplicar a otro agente del mismo proyecto). El filtro
      por tags REJECTION_TAGS en build_items hace el corte fino.
    - Best-effort: cualquier excepción → [].
    """
    if not project:
        return []
    try:
        from db import session_scope
        from models import StackyMemoryObservation  # confirmar nombre real en F1 verif.
        with session_scope() as session:
            q = (
                session.query(StackyMemoryObservation)
                .filter(StackyMemoryObservation.type == "operator_note")
                .filter(StackyMemoryObservation.status == "active")
                .filter(StackyMemoryObservation.project == project)
                .order_by(StackyMemoryObservation.updated_at.desc())
                .limit(50)
            )
            memories = [r.to_dict() for r in q.all()]
    except Exception:  # noqa: BLE001
        return []
    return build_items(
        memories, existing_patterns=existing_patterns, max_items=max_items
    )
```
> Nota de implementación: el nombre real del modelo ORM (`StackyMemoryObservation`) y de su `to_dict()` deben confirmarse con grep en `models.py`/`memory_store.py` antes de escribir (la verificación previa lo exige). Si `to_dict()` no incluye `tags` como lista, ajustar el mapeo en `load_for_run` para poblar `tags` desde la relación correspondiente.

**Casos borde.**
- `project=None` → `[]`.
- Proyecto sin memorias `operator_note` → query vacía → `[]`.
- Modelo/columna inexistente o sesión rota → except → `[]` (no propaga).

**Tests PRIMERO.** Archivo a EDITAR: `backend\tests\test_rejection_lessons.py` (agregar casos).
> Estrategia: parchear `rejection_lessons.session_scope`/el query NO; en su lugar parchear `build_items` NO. Mejor: monkeypatch del método de carga a nivel de un fake que devuelve dicts, O usar la DB de test in-memory si el conftest la provee. Patrón mínimo sin DB: parchear `rejection_lessons.load_for_run` no aplica (es la SUT). Entonces: parchear el query mediante un fake `session_scope` que devuelve filas con `.to_dict()`.
Casos:
- `test_load_none_project_returns_empty` → `load_for_run(project=None, agent_type="functional")` → `[]`.
- `test_load_filters_and_builds` → fake session que devuelve 2 filas operator_note (una con tag de rechazo, una sin) → 1 RejectionItem (la de rechazo).
- `test_load_db_error_returns_empty` → fake `session_scope` que lanza → `[]` (no propaga).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_rejection_lessons.py -q`
**Criterio de aceptación BINARIO.** 12 passed, 0 failed (9 de F0 + 3 de F1).
**Flag que la protege.** Ninguno (función inerte hasta F2).
**Impacto por runtime.** Ninguno (solo lee DB local, igual en los 3). Fallback: query vacía → `[]`.
**Trabajo del operador:** ninguno.

---

### F2 — Inyección en runtimes CLI (Codex / Claude Code) vía context_enrichment (flag OFF)

**Objetivo (1 frase).** Agregar un bloque `rejection-lessons` al system prompt en el path de los runtimes CLI, detrás del flag, deduplicando contra los anti-patrones manuales ya presentes.

**Valor.** Cierra el consumo para los 2 runtimes que HOY no reciben ni anti-patrones ni lecciones imperativas.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\context_enrichment.py`

**Diff ilustrativo.** Agregar la prioridad del bloque junto a las existentes (cerca de `:325`, donde está `"operator_note": 76`):
```python
# Plan 48 — lecciones de rechazo como anti-patrón imperativo (CLI). Prioridad
# ALTA (cerca de directivas): es una restricción dura, no un nice-to-have.
"rejection-lessons": 82,
```
Agregar el helper de inyección (junto a los otros `_inject_*`, p.ej. tras `_inject_cli_fewshot`):
```python
def _push_rejections_enabled(project_name: str | None) -> bool:
    import os
    if os.getenv("STACKY_PUSH_REJECTIONS_ENABLED", "false").lower() not in {"1","true","on","yes"}:
        return False
    # Reusa el mismo allowlist por proyecto que la memoria (si existe), para no
    # encender en proyectos sin curaduría. Si no querés acoplar, omitir esta línea.
    return True


def _inject_rejection_lessons(
    *, blocks: list[dict], project_name: str | None, agent_type: str, log: LogFn
) -> list[dict]:
    """Plan 48 — inyecta lecciones de rechazo (operator_note) como anti-patrón."""
    if not _push_rejections_enabled(project_name):
        return blocks
    if not project_name:
        return blocks
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "rejection-lessons" in existing_ids:
        return blocks
    try:
        from services import rejection_lessons
        # Dedupe cruzado con anti-patrones manuales FA-11 ya relevantes.
        existing_patterns = set()
        try:
            from services import anti_patterns
            for ap in anti_patterns.relevant(agent_type=agent_type, project=project_name):
                existing_patterns.add(" ".join((ap.pattern or "").lower().split()))
        except Exception:  # noqa: BLE001
            pass
        items = rejection_lessons.load_for_run(
            project=project_name, agent_type=agent_type,
            existing_patterns=existing_patterns,
        )
        if not items:
            return blocks
        prefix = rejection_lessons.build_prefix(items)
        block = {
            "kind": "text",
            "id": "rejection-lessons",
            "title": f"Lecciones de rechazos previos ({len(items)})",
            "content": prefix,
        }
        log("info", f"rejection-lessons inyectado (n={len(items)})")
        return [block] + list(blocks)
    except Exception as exc:  # noqa: BLE001
        log("warn", f"rejection-lessons no se pudo inyectar (continuando): {exc}")
        return blocks
```
Cablear la llamada en el cuerpo principal del enricher (junto a las otras `blocks = _inject_*`, p.ej. tras `_inject_cli_fewshot` en `:180`):
```python
blocks = _inject_rejection_lessons(
    blocks=blocks, project_name=project_name, agent_type=agent_type, log=log
)
```
> **Verificación previa OBLIGATORIA (citar archivo:línea en el PR).** Leer el bloque `:60-205` de `context_enrichment.py` para confirmar el nombre EXACTO de los parámetros disponibles en scope (`project_name`, `agent_type`, `log`, `blocks`) y el punto exacto de encadenado. NO inventar nombres.

**Casos borde.**
- Flag OFF → retorna `blocks` sin tocar → comportamiento actual.
- Sin project / sin memorias → `blocks` sin tocar.
- Lección ya presente como anti-patrón manual → dedupe la salta (no duplica).
- `rejection_lessons` lanza → log + `blocks` sin tocar.

**Tests PRIMERO.** Archivo a CREAR: `backend\tests\test_inject_rejection_lessons.py`
> Parchear en su módulo origen: `services.rejection_lessons.load_for_run` y `services.anti_patterns.relevant`. Llamar a `_inject_rejection_lessons` directamente (función interna) o al enricher público con monkeypatch del flag.
Casos:
- `test_disabled_does_not_inject` → flag unset → bloque `rejection-lessons` ausente; `load_for_run` NO invocado (assert_not_called).
- `test_enabled_injects_block` → `setenv("STACKY_PUSH_REJECTIONS_ENABLED","true")`, `load_for_run` mock devuelve 2 RejectionItems → bloque `rejection-lessons` presente con su content imperativo al FRENTE de blocks.
- `test_enabled_no_items_no_block` → flag ON, `load_for_run` devuelve `[]` → sin bloque.
- `test_dedupe_passes_existing_patterns` → flag ON, `anti_patterns.relevant` mock devuelve un patrón → `load_for_run` recibe `existing_patterns` con ese patrón normalizado (assert sobre kwargs).
- `test_exception_is_swallowed` → flag ON, `load_for_run` lanza → blocks sin tocar, sin propagar.
- `test_no_project_no_block` → flag ON, `project_name=None` → sin bloque.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_inject_rejection_lessons.py -q`
**Criterio de aceptación BINARIO.** 6 passed, 0 failed.
**Flag que la protege.** `STACKY_PUSH_REJECTIONS_ENABLED` (bool, default `false`).
**Impacto por runtime.**
- **Codex CLI / Claude Code CLI:** RECIBEN el bloque nuevo (hoy no tenían anti-patrones). Mejora directa.
- **GitHub Copilot Pro:** este path (`context_enrichment`) puede o no aplicarse según cómo arme su prompt; F3 cubre su paridad explícitamente. Fallback: si Copilot no pasa por `context_enrichment`, F3 lo cubre por `agents/base.py`; si pasara por ambos, el guard `if "rejection-lessons" in existing_ids` evita doble inyección.
**Trabajo del operador:** ninguno (opt-in default off).

---

### F3 — Paridad en github_copilot: alimentar FA-11 con lecciones de rechazo (mismo flag)

**Objetivo (1 frase).** En el path `agents/base.py` (runtime github_copilot), cuando el flag está ON, agregar los `RejectionItem` al prefijo de anti-patrones que YA se inyecta, sin duplicar con la tabla manual.

**Valor.** Garantiza que los 3 runtimes reciban las lecciones de rechazo (cierra la asimetría FA-11 que hoy solo cubre Copilot con anti-patrones manuales).

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\agents\base.py`

**Diff ilustrativo (dentro del bloque `if run_ctx.use_anti_patterns:` en `:90-104`, DESPUÉS de armar `patterns` y su prefix):**
```python
        if run_ctx.use_anti_patterns:
            try:
                from services import anti_patterns
                patterns = anti_patterns.relevant(
                    agent_type=self.type, project=run_ctx.project
                )
                if patterns:
                    prefix_parts.append(anti_patterns.build_prefix(patterns))
                    meta["anti_patterns_count"] = len(patterns)
                else:
                    meta["anti_patterns_count"] = 0
                # Plan 48 — lecciones de rechazo (mismo flag que los runtimes CLI).
                import os as _os
                if _os.getenv("STACKY_PUSH_REJECTIONS_ENABLED", "false").lower() in {"1","true","on","yes"}:
                    from services import rejection_lessons
                    existing = {" ".join((p.pattern or "").lower().split()) for p in patterns}
                    rej = rejection_lessons.load_for_run(
                        project=run_ctx.project, agent_type=self.type,
                        existing_patterns=existing,
                    )
                    if rej:
                        prefix_parts.append(rejection_lessons.build_prefix(rej))
                        meta["rejection_lessons_count"] = len(rej)
            except Exception as exc:  # noqa: BLE001
                meta["anti_patterns_error"] = str(exc)
                meta["anti_patterns_count"] = 0
```
> **Verificación previa OBLIGATORIA.** Confirmar en `agents/base.py:28,90` que `run_ctx.project`, `self.type`, `prefix_parts` y `meta` existen con esos nombres en el scope (ya verificado: `:90-104`). Confirmar que `anti_patterns.relevant` devuelve objetos con `.pattern` (sí, `_Loaded`, `anti_patterns.py:75`).

**Casos borde.**
- Flag OFF → solo se agregan los anti-patrones manuales de siempre (comportamiento actual exacto).
- Sin lecciones → no se agrega nada extra.
- Dedupe con la tabla manual vía `existing`.
- `use_anti_patterns=False` (run_ctx) → todo el bloque se saltea, igual que hoy.

**Tests PRIMERO.** Archivo a CREAR: `backend\tests\test_base_rejection_lessons.py`
> Construir/instanciar el agente mínimo o parchear el método que arma el system prompt. Parchear `services.rejection_lessons.load_for_run` y `services.anti_patterns.relevant`.
Casos:
- `test_copilot_disabled_only_manual_antipatterns` → flag unset → `meta` SIN `rejection_lessons_count`; `load_for_run` no invocado.
- `test_copilot_enabled_appends_rejections` → flag ON, `load_for_run` mock 2 ítems → `meta["rejection_lessons_count"]==2`, prefix contiene el encabezado de lecciones.
- `test_copilot_dedupe_against_manual` → flag ON, `relevant` devuelve patrón P, `load_for_run` recibe `existing_patterns` con P normalizado.
- `test_copilot_use_anti_patterns_false_skips_all` → `run_ctx.use_anti_patterns=False` → ni anti-patrones ni lecciones.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_base_rejection_lessons.py -q`
**Criterio de aceptación BINARIO.** 4 passed, 0 failed.
**Flag que la protege.** `STACKY_PUSH_REJECTIONS_ENABLED` (mismo flag que F2, default `false`).
**Impacto por runtime.** github_copilot recibe lecciones por este path; CLI por F2. Fallback: si un runtime no entra a `base.py`, lo cubre F2. Ninguno queda peor que hoy.
**Trabajo del operador:** ninguno.

---

### F4 — Telemetría: sellar cuántas lecciones de rechazo se empujaron

**Objetivo (1 frase).** Exponer en metadata del run `pushed_antipatterns` (conteo) para que el panel de salud (plan 46) y el operador vean el efecto, sin trabajo nuevo.

**Valor.** Visibilidad del KPI primario (cuántas lecciones empujaron) y secundario (paridad de runtime) sin UI nueva.

**Archivos a EDITAR:**
- `context_enrichment.py`: el bloque `rejection-lessons` ya lleva `len(items)` en su título; agregar al `metadata` del bloque `{"rejection_lessons_count": len(items)}` (espejo del patrón `metadata` de `stacky-memory`, `:721-730`).
- `agents/base.py`: ya setea `meta["rejection_lessons_count"]` en F3.

> **Verificación previa.** Confirmar que el `metadata` del bloque de `context_enrichment` se propaga al metadata del run consultable (mismo camino que `stacky-memory` usa para `memory_ids`). Si el path es distinto, sellar el conteo donde hoy se persiste `few_shot_count`/`anti_patterns_count` (grep `few_shot_count` en backend para ubicar el sink).

**Tests PRIMERO.** Reusar los archivos de F2/F3:
- En `test_inject_rejection_lessons.py`: `test_block_metadata_has_count` → bloque inyectado tiene `metadata["rejection_lessons_count"]==2`.
- En `test_base_rejection_lessons.py`: ya cubierto por `test_copilot_enabled_appends_rejections` (assert sobre `meta`).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_inject_rejection_lessons.py tests\test_base_rejection_lessons.py -q`
**Criterio de aceptación BINARIO.** Todos los tests de F2+F3+F4 pasan, 0 failed.
**Flag que la protege.** Mismo flag (con OFF el conteo nunca aparece).
**Impacto por runtime.** Ninguno (informativo). Fallback: si el sink de metadata difiere, el conteo simplemente no aparece.
**Trabajo del operador:** ninguno.

---

### F5 — Registrar el flag en el arnés (toggle en UI existente)

**Objetivo (1 frase).** Declarar `STACKY_PUSH_REJECTIONS_ENABLED` en `FLAG_REGISTRY` (plan 33) y documentarlo en `.env.example`.

**Valor.** Gobernanza consistente; el operador ve/togglea desde el panel de flags existente, sin frontend nuevo.

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\harness_flags.py`
**Agregar a `FLAG_REGISTRY` (tras el último FlagSpec):**
```python
FlagSpec(
    key="STACKY_PUSH_REJECTIONS_ENABLED",
    type="bool",
    label="Memoria que empuja: rechazos como anti-patrones",
    description=("Plan 48 — Si ON, las notas de rechazo del operador (memoria "
                 "operator_note) se inyectan como anti-patrones imperativos en el "
                 "próximo run del mismo proyecto, en los 3 runtimes. Default OFF."),
    group="global",
    env_only=True,  # se lee con os.getenv en F2/F3 (igual criterio que otros flags os.getenv)
),
```

**Archivo a EDITAR:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.env.example`
```
# Plan 48 — inyectar notas de rechazo del operador como anti-patrones imperativos en el próximo run. Default OFF.
STACKY_PUSH_REJECTIONS_ENABLED=false
```

**Tests PRIMERO.** Archivo a EDITAR: `backend\tests\test_harness_flags.py`
- `test_push_rejections_flag_registered` → existe FlagSpec con `key=="STACKY_PUSH_REJECTIONS_ENABLED"`, `type=="bool"`, `group=="global"`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q`
**Criterio de aceptación BINARIO.** El archivo pasa con el caso nuevo, 0 failed.
**Flag que la protege.** Se declara aquí. Default `false`.
**Impacto por runtime.** Ninguno (declarativo). Fallback: N/A.
**Trabajo del operador:** ninguno (solo expone el toggle).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **R-RUIDO**: una nota de rechazo mal escrita inyecta una "restricción" confusa. | Tope `_MAX_ITEMS=6`, truncado de pattern/reason, primera línea como pattern (lo más conciso). El operador puede desactivar el flag. No genera contenido nuevo, solo reusa su propia nota. |
| **R-STALE**: lección vieja ya resuelta sigue empujando. | Orden por `updated_at DESC` + tope 6 → priman las recientes. Mitigación futura (fuera de MVP): expirar `operator_note` por antigüedad. Documentado para el juez. |
| **R-DUP**: misma lección como anti-patrón manual (FA-11) y como rechazo. | Dedupe cruzado por `pattern` normalizado en F2/F3 (`existing_patterns`). |
| **R-PROMPT-BLOAT**: más texto en el system prompt. | Acotado por `_MAX_ITEMS`×(`_MAX_PATTERN_CHARS`+`_MAX_REASON_CHARS`) ≈ 3.4 KB techo; sujeto a los caps de presupuesto de contexto existentes. Cero tokens de generación. |
| **R-PARIDAD**: un runtime no recibe el bloque. | F2 cubre CLI, F3 cubre Copilot, guard `existing_ids` evita doble inyección si un runtime pasa por ambos. Fallback explícito por fase. |
| **R-REGRESIÓN**: rompe la inyección existente. | Cada `_inject_*` envuelto en try/except best-effort → ante fallo devuelve `blocks` intactos. Flag default OFF = byte-idéntico. |
| **R-MODELO-ORM**: nombre real del modelo/columna difiere. | Verificación previa OBLIGATORIA en F1 (grep `models.py`/`memory_store.py`) antes de escribir el query. |

---

## 6. Fuera de scope (NO hacer)

- NO doble-pase / self-critique (idea 1): paga x2 tokens siempre. Rechazado.
- NO segundo agente adversario (idea 5): moonshot caro. Rechazado.
- NO nuevo score de confianza (idea 3): ya existe `confidence.overall`. Diferido.
- NO few-shot (idea 6): ya implementado en Q1.2 `_inject_cli_fewshot`.
- NO nuevos botones/pasos para el operador (lección plan 41). La nota ya se captura.
- NO migración de schema: se reusan `operator_note` (memoria), `anti_patterns` (tabla existente) y metadata del run.
- NO expirar/curar memorias `operator_note` (posible plan futuro).
- NO tocar el rescate de disco (plan 47), el modal/selector (42/43), el observatorio (44), el catálogo (45) ni el panel (46): este plan ALIMENTA el panel vía `pushed_antipatterns`.

---

## 7. Glosario, orden de implementación, DoD

**Glosario (dominio Stacky).**
- **`operator_note`**: tipo de memoria colaborativa que `capture_operator_note` (`post_run_memory.py:199`) crea desde la nota humana de un veredicto; tags `rejected_reason`/`approval_condition`.
- **Anti-patrón (FA-11)**: restricción imperativa "Evitá X porque Y" inyectada al system prompt (`anti_patterns.py`); hoy desde tabla manual, solo en runtime github_copilot.
- **`get_context_for_run`**: armador del bloque de memoria por relevancia TF-IDF (`memory_store.py:1294`); canal débil para lecciones de rechazo.
- **`context_enrichment._inject_*`**: cadena de inyección de bloques al system prompt para runtimes CLI (Codex/Claude Code).
- **`agents/base.py`**: path de prompt del runtime github_copilot, único que hoy inyecta anti-patrones.
- **3 runtimes**: Codex CLI, Claude Code CLI (vía `context_enrichment`, F2), GitHub Copilot Pro (vía `base.py`, F3).
- **`STACKY_PUSH_REJECTIONS_ENABLED`**: flag maestro de este plan, default OFF.

**Orden de implementación (por dependencia).**
1. **F0** — `rejection_lessons.build_items`/`build_prefix` + tests (sin dependencias).
2. **F1** — `rejection_lessons.load_for_run` (lee memory_store) + tests (depende de F0; requiere verif. ORM).
3. **F2** — inyección CLI en `context_enrichment` + tests (depende de F0/F1).
4. **F3** — paridad Copilot en `agents/base.py` + tests (depende de F0/F1).
5. **F4** — telemetría `rejection_lessons_count`/`pushed_antipatterns` (depende de F2/F3).
6. **F5** — registrar flag + `.env.example` + test (independiente; habilita F2/F3 en UI).

**Definición de Hecho (DoD) global — binaria.**
- [ ] `test_rejection_lessons.py` → 12 passed, 0 failed (F0 9 + F1 3).
- [ ] `test_inject_rejection_lessons.py` → 6 passed (+ caso metadata F4), 0 failed.
- [ ] `test_base_rejection_lessons.py` → 4 passed, 0 failed.
- [ ] `test_harness_flags.py` → pasa con el caso nuevo, 0 failed.
- [ ] Con `STACKY_PUSH_REJECTIONS_ENABLED` unset (default), `context_enrichment` y `agents/base.py` producen el system prompt byte-idéntico al actual (verificado por `test_*_disabled_*`).
- [ ] Con flag ON y memorias `operator_note` de rechazo en el proyecto, el bloque `rejection-lessons` (CLI) y el prefijo (Copilot) aparecen con formato imperativo, deduplicados contra FA-11.
- [ ] Cualquier excepción del puente cae al comportamiento actual sin propagar (verificado).
- [ ] Cero tokens de generación nuevos (no hay llamada a LLM en ninguna fase).
- [ ] Paridad 3 runtimes verificada: F2 (CLI) + F3 (Copilot), sin doble inyección.
- [ ] Sin migración de schema; sin cambios de frontend.
- [ ] Tests existentes sin regresión: `test_capture_operator_note.py`, `test_harness_flags.py`, `test_skills_injection.py` → 0 failed.
