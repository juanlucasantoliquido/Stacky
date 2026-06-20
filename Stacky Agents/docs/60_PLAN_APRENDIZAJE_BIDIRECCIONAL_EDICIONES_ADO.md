# Plan 60 — Aprendizaje bidireccional: las ediciones del operador en ADO vuelven como lección/golden

> **Estado:** PROPUESTO 2026-06-20 · v1 (sin juez) · NO implementado.
> **Autor:** StackyArchitectaUltraEficientCode.
> **Origen:** finalista #3 del roadmap `docs/_roadmap/TOP5_2026-06-20_POST57_LOOP_MOLECULA_BIDIRECCIONAL.md`.
> **Sustrato verificado firsthand 2026-06-20:** `ado_client.fetch_work_item_updates` (ado_client.py:930, código muerto, cero callers), `get_work_item` (ado_client.py:836), wiring autopublish `_maybe_autopublish_epic` (claude_code_cli_runner.py:1212) que sella `metadata["epic_ado_id"]`, corpus de lecciones plan 54 (`rejection_lessons.py`), golden gate plan 56 (`harness/epic_gate.py:72`, NO implementado), patrón de loop de fondo (`app.py:389 _memory_review_sweep_loop`).

---

## 1. Título, objetivo y KPI

**Título.** Aprendizaje bidireccional de ediciones humanas en ADO.

**Objetivo en una frase.** Cuando el operador corrige a mano una épica/issue YA publicada por Stacky directamente en Azure DevOps, Stacky LEE DE VUELTA la revisión del work item, DIFFEA lo que publicó (baseline) contra la versión que dejó el humano, y materializa ese delta como **lección determinista** en el corpus del plan 54 (y opcionalmente como **golden positivo** del plan 56) — sin ningún trabajo extra del operador y sin nunca re-publicar ni auto-aplicar nada.

**Gap que cierra.** Hoy la publicación es *write-only / fire-and-forget*: `_maybe_autopublish_epic` crea el WI, sella `epic_ado_id` y termina. La corrección humana en ADO —la señal de entrenamiento más rica que existe, la versión REAL aprobada por el humano— se pierde por completo. Pasamos de **observar** (planes 44/46 son pasivos read-only de runs locales) a **APRENDER cerrado contra ground-truth real**.

**KPI binario.** Cada corrección humana detectable en ADO sobre un WI publicado por Stacky se convierte, en el siguiente sweep, en **≥1 lección determinista** en el corpus del plan 54 (y un golden positivo si el plan 56 está presente y su flag ON), **idempotente** (una revisión nunca produce dos lecciones), **sin trabajo del operador**. Con el flag `STACKY_ADO_EDIT_LEARNING_ENABLED=false` (default), el comportamiento del sistema es **byte-idéntico** al actual (cero threads nuevos, cero llamadas a ADO).

---

## 2. Por qué ahora / diferenciación

- **Por qué ahora.** Los planes 40-52 cerraron el lado de *publicación* (épicas grounded, autopublish backend, gate de calidad). El plan 54 cerró el lado de *memoria que empuja* (rechazos internos → anti-patrones). Falta el lazo que une ambos: la edición humana real. El read-back ya existe como código muerto (`fetch_work_item_updates`) — no hay que inventar transporte.
- **Distinto del plan 54.** El 54 aprende de una **nota de rechazo escrita DENTRO de Stacky** (veredicto humano en `OutputPanel`). El 60 aprende del **artefacto editado por el humano EN ADO** — señal distinta, más rica y sin pedirle al operador que escriba nada.
- **Distinto del plan 56.** El 56 materializa un golden de **aprobar/rechazar**. El 60 materializa la **versión corregida** como baseline positivo. El 60 *consume* el 56 si está presente; degrada limpio si no.
- **Distinto del plan 57 (RECHAZADO).** El 57 murió porque la especulación FA-36 vía runner CLI **auto-publicaba** épicas → rompía human-in-the-loop. El 60 es lo opuesto: NUNCA publica, NUNCA actúa solo; solo lee y materializa lecciones deterministas de lo que el humano YA hizo.

---

## 3. Principios y guardarraíles (codificados en el diseño)

1. **Human-in-the-loop INNEGOCIABLE.** El plan APRENDE de lo que el humano hizo en ADO; NUNCA re-publica, NUNCA auto-aplica cambios al WI, NUNCA actúa solo. Solo escribe lecciones/goldens locales. (No reintroducir la autonomía proactiva que mató al plan 57.)
2. **Cero trabajo del operador.** El operador edita en ADO como ya lo haría. Stacky lee PASIVAMENTE en un sweep de fondo periódico (patrón `_memory_review_sweep_loop`), nunca bloqueante de ningún run.
3. **Default OFF.** Flag `STACKY_ADO_EDIT_LEARNING_ENABLED` default `false`. OFF ⇒ el thread NO se arma, cero llamadas a ADO, byte-idéntico al actual.
4. **Config por UI.** El flag se registra en `harness_flags.FLAG_REGISTRY` (group `global`, `env_only=True`) para que aparezca en el panel de flags (plan 33) sin tocar frontend; además en `backend/.env.example`.
5. **Paridad 3 runtimes con fallback.** El read-back es vía ADO REST API (runtime-agnóstico) y el diff es **función PURA de texto** → idéntico en Codex, Claude Code y GitHub Copilot. **Fallback:** si `fetch_work_item_updates` falla, ADO no responde, o no hay edición humana detectable ⇒ **no-op** (sin lección), nunca rompe nada.
6. **Mono-operador sin auth.** No hay roles; no degradar. Solo lecturas sobre ADO + rate-limit del sweep + idempotencia (no duplicar lecciones por la misma revisión, ledger persistente).
7. **Reuso, cero reinvención.** Reusa `fetch_work_item_updates` (dead code), `get_work_item`, el corpus del plan 54, el golden del plan 56, el patrón de loop. No se inventa transporte ni almacenamiento nuevo salvo un ledger mínimo de idempotencia.
8. **Determinismo total.** El diff y la derivación de lección son funciones puras de texto; sin LLM, sin tokens, sin no-determinismo.

### Cómo se distingue una edición HUMANA de la publicación original de Stacky (criterio SIN ambigüedad)

Una revisión `r` de `fetch_work_item_updates(ado_id)` cuenta como **edición humana aprendible** si y solo si TODAS estas condiciones se cumplen (función pura `is_human_edit`):

1. `r["rev"] > baseline_rev`, donde `baseline_rev` es la revisión sellada al publicar (ver F1). Descarta la revisión 1 que es la creación por Stacky.
2. La revisión modificó el campo de contenido relevante: `r["fields"]` contiene `"System.Description"` (épica) **o** `"Microsoft.VSTS.TCM.ReproSteps"`/el campo de cuerpo usado por Issue — usamos el set `_BODY_FIELDS = {"System.Description"}` (Issue publica también en `System.Description`; verificar en F1 contra `publish_issue_from_run`).
3. El **autor** de la revisión NO es la identidad de servicio de Stacky. Identidad de servicio = `STACKY_ADO_SERVICE_IDENTITY` (env/UI, CSV de `uniqueName`/`displayName`, default vacío). Si está vacío ⇒ se usa el heurístico: el autor de la revisión `r` es distinto del autor de la revisión `baseline_rev` (Stacky publicó la baseline). Autor en `r["revisedBy"]["uniqueName"]` (fallback `displayName`).
4. El texto del cuerpo en `r` (`r["fields"]["System.Description"]["newValue"]`) **difiere materialmente** del baseline HTML guardado (`diff_is_material`, ver F2): tras normalizar (strip HTML tags → texto, colapsar whitespace), la distancia es > umbral (`_MIN_EDIT_CHARS = 12` chars de diff neto). Cambios cosméticos (whitespace, re-encoding) ⇒ no material ⇒ no-op.

Casos borde resueltos por construcción:
- **Sin ediciones humanas:** ninguna revisión pasa `is_human_edit` ⇒ no-op.
- **Edición de otro autor que no es el operador:** mono-operador ⇒ cualquier autor ≠ Stacky es "el humano". No discriminamos entre humanos (no hay auth). Aprendible.
- **Revisión ya procesada:** ledger de idempotencia `(ado_id, rev)` (ver F3) ⇒ se saltea.
- **ADO no responde / endpoint no soportado:** `fetch_work_item_updates` ya devuelve `[]` silencioso ⇒ no-op.

---

## 4. Fases F0..F6

> **Orden estricto por dependencia.** TDD: el archivo de test se escribe y corre ANTES de la implementación. Comando base de test (Windows, venv del repo):
> `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/<archivo>" -q`
> Todo test nuevo se REGISTRA en `backend/scripts/run_harness_tests.sh` y `.ps1` (regla dura plan 49 F4 — el meta-test falla si no).

---

### F0 — Diff puro de ediciones (núcleo determinista, sin red)

**Objetivo.** Función pura que, dado el HTML baseline y el HTML editado por el humano, decide si el cambio es material y devuelve un delta estructurado. **Valor:** es el corazón determinista y testeable en aislamiento total; idéntico en los 3 runtimes.

**Archivo nuevo:** `Stacky Agents/backend/harness/ado_edit_diff.py`
(en `harness/` porque es función pura de calidad, junto a `epic_gate.py`).

**API exacta:**
```python
from __future__ import annotations
from dataclasses import dataclass

_MIN_EDIT_CHARS = 12  # diff neto mínimo (chars) para considerar material

@dataclass(frozen=True)
class EditDelta:
    is_material: bool
    baseline_text: str        # baseline normalizado a texto plano
    edited_text: str          # edición normalizada a texto plano
    added_snippets: list[str] # líneas/frases presentes en edited y NO en baseline
    removed_snippets: list[str]
    net_char_delta: int       # len(edited_text) - len(baseline_text)

def strip_html_to_text(html: str) -> str:
    """PURA. Quita tags HTML, decodifica entidades básicas (&amp;&lt;&gt;&nbsp;),
    colapsa whitespace a un espacio, trim. Sin dependencias externas (regex stdlib)."""

def diff_edit(baseline_html: str, edited_html: str) -> EditDelta:
    """PURA. Normaliza ambos con strip_html_to_text, compara por líneas/frases
    (split en '. ' y '\\n'), arma added/removed con difflib.SequenceMatcher o
    comparación de sets ordenados. is_material = suma de chars en added+removed
    > _MIN_EDIT_CHARS. baseline vacío + edited no vacío => material."""
```

**Pseudocódigo de `diff_edit` (casos borde inline):**
```
b = strip_html_to_text(baseline_html or "")
e = strip_html_to_text(edited_html or "")
if b == e: return EditDelta(is_material=False, ... , added=[], removed=[], net=0)
b_units = _split_units(b)   # frases por '. ' y saltos
e_units = _split_units(e)
added   = [u for u in e_units if u not in b_units]
removed = [u for u in b_units if u not in e_units]
net_chars = sum(len(u) for u in added) + sum(len(u) for u in removed)
is_material = net_chars > _MIN_EDIT_CHARS
return EditDelta(is_material, b, e, added, removed, len(e)-len(b))
```

**Test primero:** `Stacky Agents/backend/tests/test_ado_edit_diff.py`
Casos:
1. `diff_edit(html, html)` idéntico ⇒ `is_material=False`, added/removed vacíos.
2. baseline con un párrafo, edited con ese párrafo + una frase nueva ⇒ `is_material=True`, frase en `added_snippets`.
3. Solo cambio de whitespace/`&nbsp;` vs espacio ⇒ `is_material=False`.
4. baseline `""`, edited con contenido ⇒ `is_material=True`.
5. Eliminación de una frase ⇒ aparece en `removed_snippets`.
6. `strip_html_to_text("<h1>A</h1><p>b&amp;c</p>")` ⇒ `"A b&c"`.

**Aceptación binaria:** `... -m pytest "Stacky Agents/backend/tests/test_ado_edit_diff.py" -q` ⇒ 6 passed, 0 failed.
**Flag:** ninguno (función pura siempre disponible, sin efectos).
**Runtime/fallback:** idéntico 3 runtimes (puro). Sin fallback necesario.
**Trabajo del operador:** ninguno.

---

### F1 — Sellar baseline al publicar (HTML + rev + autor)

**Objetivo.** Que la publicación registre lo necesario para diffear después: el `ado_id` (ya se sella), el HTML publicado (baseline), la revisión inicial y el autor. **Valor:** sin baseline no hay diff confiable.

**Archivos:**
- `Stacky Agents/backend/api/tickets.py` — en `autopublish_epic_from_run` (y `publish_issue_from_run`), extender `_AutopublishResult` con dos campos nuevos: `published_html: str | None` y `baseline_rev: int | None`.
- `Stacky Agents/backend/services/claude_code_cli_runner.py` — en `_maybe_autopublish_epic` (línea ~1262), tras sellar `metadata[_seal_key]`, sellar también:
  ```python
  if _res.published_html is not None:
      metadata["epic_baseline_html"] = _res.published_html
  if _res.baseline_rev is not None:
      metadata["epic_baseline_rev"] = _res.baseline_rev
  ```
  (Para Issue usar prefijo `issue_baseline_html`/`issue_baseline_rev` consistente con `_seal_key`.)

**Cómo obtener `baseline_rev`:** tras el PATCH/create del WI, `autopublish_epic_from_run` ya tiene el `ado_id`. Llamar `ado_client.get_work_item(ado_id, fields=["System.Rev"])` y leer `fields["System.Rev"]` (int). Si falla ⇒ `baseline_rev=None` (el sweep usará fallback de autor, ver F4).
**`published_html`:** es el HTML que `autopublish_epic_from_run` ya construye/envía como `System.Description` (reusar la variable existente; CONFIRMAR su nombre al implementar leyendo el cuerpo de la función). Si no se puede capturar ⇒ `None` (F4 degrada).

**Test primero:** `Stacky Agents/backend/tests/test_epic_autopublish_backend.py` (extender, no nuevo archivo):
- Caso: con `FakeAdoClient` que crea WI y `get_work_item` devuelve `{"fields":{"System.Rev":1}}`, `autopublish_epic_from_run` retorna `_AutopublishResult` con `published_html` no vacío y `baseline_rev=1`.
- Caso: `get_work_item` lanza ⇒ `baseline_rev=None`, no rompe (sigue `ado_id` sellado).

**Aceptación binaria:** los tests existentes de ese archivo siguen verdes + 2 casos nuevos passed.
**Flag:** sin flag propio; el sellado de baseline es inocuo y sin costo (1 GET extra solo en autopublish, ya online). Si se prefiere gatearlo, reusar `STACKY_ADO_EDIT_LEARNING_ENABLED` para saltear el GET cuando OFF (recomendado: evita el GET extra con flag OFF → byte-idéntico). **Decisión: gatear el GET extra con el flag** para garantizar byte-identidad con flag OFF.
**Runtime/fallback:** autopublish solo lo invoca claude_code_cli (memoria `autopublish-only-claude-cli`); el baseline solo se sella ahí. Los otros runtimes no autopublican ⇒ no tienen baseline ⇒ el sweep los saltea (no-op). Aceptable: la señal viene de épicas autopublicadas. **Documentar esta asimetría como esperada.**
**Trabajo del operador:** ninguno.

---

### F2 — Detector de edición humana (función pura sobre revisiones)

**Objetivo.** Funciones puras que, dada la lista de revisiones de ADO + baseline sellado, deciden cuál revisión es una edición humana aprendible. **Valor:** aísla la lógica de "qué cuenta como edición humana" sin red, testeable con fixtures.

**Archivo nuevo:** `Stacky Agents/backend/harness/ado_edit_detect.py` (puro).

**API exacta:**
```python
from __future__ import annotations
from dataclasses import dataclass

_BODY_FIELDS = ("System.Description",)  # confirmar en F1 contra el campo real publicado

@dataclass(frozen=True)
class HumanEdit:
    ado_id: int
    rev: int
    author: str               # uniqueName o displayName
    edited_html: str          # newValue del body field

def _service_identities(csv: str) -> set[str]:
    """PURA. Parsea STACKY_ADO_SERVICE_IDENTITY (CSV) a set normalizado lower()."""

def is_human_edit(
    revision: dict,
    *,
    baseline_rev: int | None,
    baseline_author: str | None,
    service_identities: set[str],
) -> HumanEdit | None:
    """PURA. Aplica las 4 condiciones del §3. Devuelve HumanEdit o None.
    - rev <= baseline_rev (o ==1 si baseline_rev None) -> None
    - no toca _BODY_FIELDS -> None
    - autor in service_identities -> None
    - si service_identities vacío y baseline_author set: autor==baseline_author -> None
    - extrae edited_html del newValue del body field; si vacío -> None
    """

def select_latest_human_edit(
    revisions: list[dict],
    *,
    baseline_rev: int | None,
    baseline_author: str | None,
    service_identities: set[str],
    already_processed_revs: set[int],
) -> HumanEdit | None:
    """PURA. Recorre revisiones DESC por rev, devuelve la primera que pasa
    is_human_edit y cuyo rev NO esté en already_processed_revs. Else None.
    (Solo la MÁS RECIENTE no procesada: la versión humana vigente.)"""
```

**Test primero:** `Stacky Agents/backend/tests/test_ado_edit_detect.py`
Casos (fixtures = dicts con shape de ADO `updates`):
1. Solo revisión 1 (creación por Stacky) ⇒ `None` (sin edición humana).
2. Revisión 2 que toca `System.Description`, autor `operador@x` ≠ baseline_author `stacky-svc` ⇒ `HumanEdit(rev=2, ...)`.
3. Revisión 2 cuyo autor está en `service_identities` ⇒ `None`.
4. Revisión 2 que NO toca el body field (solo cambió `System.State`) ⇒ `None`.
5. Revisión 2 ya en `already_processed_revs` ⇒ `None` (idempotencia).
6. Revisiones 2 y 3 humanas, ninguna procesada ⇒ `select_latest_human_edit` devuelve rev=3.
7. `service_identities` vacío + `baseline_author=None` + rev>baseline_rev ⇒ se acepta como humana (heurístico mínimo: rev posterior con body cambiado).

**Aceptación binaria:** 7 passed, 0 failed.
**Flag:** ninguno (puro).
**Runtime/fallback:** idéntico 3 runtimes (puro).
**Trabajo del operador:** ninguno.

---

### F3 — Ledger de idempotencia de revisiones procesadas

**Objetivo.** Persistir `(ado_id, rev)` ya convertidas en lección para no duplicar. **Valor:** garantiza el KPI de idempotencia entre sweeps y reinicios.

**Archivo nuevo:** `Stacky Agents/backend/services/ado_edit_ledger.py`.
**Almacenamiento:** reusar la DB viva (sqlite, `DeployStackyAgents\data`). Tabla nueva `ado_edit_learned(ado_id INTEGER, rev INTEGER, run_id TEXT, learned_at TEXT, PRIMARY KEY(ado_id, rev))`. Crear con `CREATE TABLE IF NOT EXISTS` al primer uso (patrón existente del repo — CONFIRMAR helper de conexión, p.ej. `models.py`/`db`).

**API exacta:**
```python
def already_learned(ado_id: int, rev: int) -> bool: ...
def mark_learned(ado_id: int, rev: int, run_id: str | None) -> None: ...
def processed_revs_for(ado_id: int) -> set[int]: ...  # alimenta select_latest_human_edit
```
Manejo de error: cualquier excepción de DB ⇒ log warning + `already_learned` devuelve `False` defensivo NO (sería duplicar); **decisión: si la DB falla, `already_learned` devuelve `True`** (mejor perder una lección que duplicarla) y `mark_learned` traga la excepción con log.

**Test primero:** `Stacky Agents/backend/tests/test_ado_edit_ledger.py` (usar DB temporal / monkeypatch de la ruta de DB, patrón existente en tests del repo):
1. `already_learned(10, 2)` antes de marcar ⇒ `False`.
2. tras `mark_learned(10, 2, "run-x")` ⇒ `already_learned(10, 2)` `True`.
3. `processed_revs_for(10)` ⇒ `{2}`.
4. `mark_learned` dos veces misma PK ⇒ no rompe (INSERT OR IGNORE).

**Aceptación binaria:** 4 passed.
**Flag:** ninguno (solo se invoca dentro del sweep gateado).
**Runtime/fallback:** agnóstico.
**Trabajo del operador:** ninguno.

---

### F4 — Materializador: edición humana → lección (plan 54) + golden opcional (plan 56)

**Objetivo.** Función que toma un `HumanEdit` + `EditDelta` y escribe la lección en el corpus del plan 54; si el plan 56 está presente y su flag ON, además registra golden positivo. **Valor:** convierte la señal en mejora real del próximo run.

**Archivo nuevo:** `Stacky Agents/backend/services/ado_edit_learning.py`.

**API exacta:**
```python
@dataclass(frozen=True)
class LearnResult:
    learned: bool
    lesson_written: bool
    golden_written: bool
    rev: int | None
    reason: str   # "ok" | "not_material" | "no_baseline" | "no_human_edit" | "already_learned" | "ado_unavailable"

def edit_to_lesson_content(delta: EditDelta, *, ado_id: int) -> str:
    """PURA. Construye el texto de lección determinista a partir del delta.
    Forma: 'El operador corrigió a mano la épica/issue (WI {ado_id}). Incorporá:'
    + bullets de added_snippets (techo 6) + '. Evitá:' + removed_snippets (techo 6).
    Truncado por _MAX chars. SIN LLM."""

def learn_from_work_item(
    *,
    ado_id: int,
    baseline_html: str | None,
    baseline_rev: int | None,
    baseline_author: str | None,
    run_id: str | None,
    project_name: str | None,
    ado_client,            # inyectable para test (FakeAdoClient)
    service_identities: set[str],
) -> LearnResult:
    """IMPURA (red+DB) pero orquesta puras. Pasos:
    1. revisions = ado_client.fetch_work_item_updates(ado_id)  -> [] si falla
       (si [] -> LearnResult(learned=False, reason='ado_unavailable' o 'no_human_edit'))
    2. processed = ado_edit_ledger.processed_revs_for(ado_id)
    3. he = select_latest_human_edit(revisions, baseline_rev=..., baseline_author=...,
            service_identities=..., already_processed_revs=processed)
       -> None: reason='no_human_edit'
    4. if baseline_html is None: usar como baseline el newValue de la revisión
       anterior (oldValue del body en he), o '' -> reason puede ser 'no_baseline' si
       ni eso existe (degradar: aún se puede aprender de added si edited no vacío).
    5. delta = diff_edit(baseline_html or oldValue or '', he.edited_html)
       -> not delta.is_material: reason='not_material', NO marca ledger.
    6. content = edit_to_lesson_content(delta, ado_id=ado_id)
       -> escribir en corpus plan 54 (ver más abajo). lesson_written=True
    7. golden opcional (plan 56): if _golden_available() and flag ON:
          registrar golden positivo (baseline = he.edited_html). golden_written=True
    8. ado_edit_ledger.mark_learned(ado_id, he.rev, run_id)
    9. return LearnResult(learned=True, lesson_written, golden_written, he.rev, 'ok')
    """
```

**Escritura de la lección (reuso plan 54).** El corpus del 54 (`rejection_lessons.py`) lee de `memory_store` memorias con tags en `REJECTION_TAGS`. **Decisión:** escribir la lección como memoria en `memory_store` con un tag NUEVO `"ado_human_edit"` y EXTENDER `rejection_lessons.REJECTION_TAGS` para incluirlo:
- En `rejection_lessons.py`: `REJECTION_TAGS = ("rejected_reason", "approval_condition", "ado_human_edit")`.
- En `ado_edit_learning.py`: `memory_store.add(...)` con `content` = `edit_to_lesson_content(...)` , `tags=["ado_human_edit"]`, `title=f"Edición humana WI {ado_id}"`, `project=project_name`.
  (CONFIRMAR la firma exacta de `memory_store.add` leyendo `services/memory_store.py` al implementar; si no existe `add`, usar el writer que ya use `capture_operator_note`.)
Así la lección entra automáticamente al prefix que ya se inyecta en los 3 runtimes (plan 54 cerró la paridad FA-11). **Cero código de inyección nuevo.**

**Golden opcional (plan 56).** El plan 56 NO está implementado. `_golden_available()` hace `try: from harness import epic_gate; return hasattr(epic_gate, "register_positive_golden") except Exception: return False`. Si no existe ⇒ `golden_written=False`, `lesson_written=True` (degradación limpia: solo lección). **Documentar el prerequisito 56 y el modo degradado.** Flag del golden: `STACKY_EPIC_CATALOG_GATE_ENABLED` (ya existe en memoria plan 51) o el que el 56 defina; si no está, irrelevante.

**Test primero:** `Stacky Agents/backend/tests/test_ado_edit_learning.py` con `FakeAdoClient` (mock de `fetch_work_item_updates`) y `memory_store` monkeypatcheado a un stub que captura `add`:
1. `fetch_work_item_updates` ⇒ `[]` ⇒ `LearnResult(learned=False, reason ∈ {ado_unavailable,no_human_edit})`, NO escribe memoria, NO marca ledger.
2. Una revisión humana material ⇒ `learned=True, lesson_written=True`, memoria escrita con tag `ado_human_edit`, ledger marcado con su rev.
3. Llamar dos veces seguidas (segunda con ledger ya marcado) ⇒ segunda `learned=False, reason='already_learned'`, NO escribe segunda memoria. **(idempotencia, KPI clave.)**
4. Edición no material (solo whitespace) ⇒ `not_material`, NO escribe, NO marca ledger.
5. `_golden_available()` falso ⇒ `golden_written=False` pero `lesson_written=True`.
6. `edit_to_lesson_content` produce texto determinista con bullets de added/removed.

**Aceptación binaria:** 6 passed.
**Flag:** la orquestación se invoca solo desde F5 (sweep gateado); la función en sí no checkea flag (testeable directo).
**Runtime/fallback:** la lección se inyecta vía corpus 54 que ya es paritario en 3 runtimes. Si `fetch_work_item_updates` falla ⇒ no-op.
**Trabajo del operador:** ninguno.

---

### F5 — Sweep de fondo pasivo (wiring, gateado por flag)

**Objetivo.** Un daemon periódico que recorre runs recientes con `epic_ado_id` sellado y llama `learn_from_work_item` para cada uno. **Valor:** cierra el lazo automáticamente sin tocar el path del run.

**Archivos:**
- `Stacky Agents/backend/app.py` — agregar bloque tras `_memory_review_sweep_loop` (línea ~406), patrón idéntico:
  ```python
  # Plan 60 — Aprendizaje bidireccional de ediciones humanas en ADO (opcional).
  # STACKY_ADO_EDIT_LEARNING_ENABLED=false => apagado (default, byte-idéntico).
  if _flag_on("STACKY_ADO_EDIT_LEARNING_ENABLED"):
      _ado_edit_seconds = int(os.environ.get("STACKY_ADO_EDIT_SWEEP_HOURS", "6")) * 3600

      def _ado_edit_sweep_loop() -> None:
          from services.ado_edit_learning import sweep_recent_runs
          while True:
              try:
                  n = sweep_recent_runs()
                  if n:
                      logger.info("ado edit learning sweep: %d lecciones nuevas", n)
              except Exception:
                  logger.exception("ado edit learning daemon falló")
              time.sleep(_ado_edit_seconds)

      threading.Thread(target=_ado_edit_sweep_loop,
                       name="stacky-ado-edit-daemon", daemon=True).start()
      logger.info("ado edit learning daemon armed (interval=%ds)", _ado_edit_seconds)
  ```
  (Usar el mismo lector de flag que el resto; como `STACKY_ADO_EDIT_LEARNING_ENABLED` es `env_only`, leer `os.environ.get(...) in ("1","true","True")`. CONFIRMAR el helper existente.)
- `Stacky Agents/backend/services/ado_edit_learning.py` — agregar:
  ```python
  _SWEEP_RUN_LIMIT = 50           # techo de runs por sweep (rate-limit)
  def sweep_recent_runs() -> int:
      """Lee los últimos _SWEEP_RUN_LIMIT runs con metadata['epic_ado_id']
      (o issue_ado_id) NO marcados completamente en ledger; para cada uno llama
      learn_from_work_item con el baseline sellado. Devuelve nº de lecciones nuevas.
      Construye ado_client vía el factory existente (CONFIRMAR: project_manager /
      ado_client constructor). service_identities de STACKY_ADO_SERVICE_IDENTITY."""
  ```

**Rate-limit / no degradar:** `_SWEEP_RUN_LIMIT=50` runs por pasada; intervalo default 6 h; cada run hace a lo sumo 1 `fetch_work_item_updates` (+ 0 si ya todo en ledger). Sin paralelismo. Daemon `daemon=True` (no bloquea shutdown).

**Test primero:** `Stacky Agents/backend/tests/test_ado_edit_sweep.py`:
1. `sweep_recent_runs` con 0 runs con `epic_ado_id` ⇒ devuelve 0, no llama ADO.
2. 1 run con `epic_ado_id` + `FakeAdoClient` con revisión humana ⇒ devuelve 1, lección escrita.
3. Segundo sweep inmediato (ledger ya marcado) ⇒ devuelve 0 (idempotencia entre sweeps).
4. `FakeAdoClient.fetch_work_item_updates` lanza ⇒ `sweep_recent_runs` no propaga, devuelve 0.

> Nota TDD: como `app.py` arma el thread, NO se testea el thread en sí (no-determinista); se testea `sweep_recent_runs` directo. El thread es wiring trivial verificado por inspección + el centinela de paridad. (Justificación de no-TDD del thread: 1 línea — los daemons no son unit-testeables de forma determinista; se cubre la función que invocan.)

**Aceptación binaria:** 4 passed; y con `STACKY_ADO_EDIT_LEARNING_ENABLED` ausente, un test de humo (en `test_ado_edit_sweep.py`) que importa `app` y verifica que NO existe thread `stacky-ado-edit-daemon` (o que `sweep_recent_runs` no se invocó) ⇒ byte-identidad con flag OFF.
**Flag:** `STACKY_ADO_EDIT_LEARNING_ENABLED` (bool, default false) + `STACKY_ADO_EDIT_SWEEP_HOURS` (int, default 6) + `STACKY_ADO_SERVICE_IDENTITY` (csv, default "").
**Runtime/fallback:** el sweep es runtime-agnóstico (lee runs y ADO). Si ADO no responde ⇒ no-op.
**Trabajo del operador:** ninguno (opt-in, default off).

---

### F6 — Flags en UI + .env.example + registro de tests

**Objetivo.** Exponer los 3 flags en el panel de flags (plan 33) y documentarlos; registrar los tests nuevos. **Valor:** regla dura de config-por-UI + regla dura del ratchet (plan 49 F4).

**Archivos:**
- `Stacky Agents/backend/services/harness_flags.py` — agregar a `FLAG_REGISTRY`:
  ```python
  FlagSpec(key="STACKY_ADO_EDIT_LEARNING_ENABLED", type="bool",
           label="Aprender de ediciones en ADO (plan 60)",
           description="Lee de vuelta las correcciones humanas del WI publicado y las materializa como lección/golden. Pasivo, default OFF.",
           group="global", env_only=True),
  FlagSpec(key="STACKY_ADO_EDIT_SWEEP_HOURS", type="int",
           label="Intervalo del sweep ADO (horas)",
           description="Cada cuántas horas relee los WI publicados. Default 6.",
           group="global", env_only=True),
  FlagSpec(key="STACKY_ADO_SERVICE_IDENTITY", type="csv",
           label="Identidad(es) de servicio Stacky en ADO",
           description="CSV de uniqueName/displayName con que Stacky publica; sus revisiones se ignoran como 'no humanas'. Vacío = heurístico por autor.",
           group="global", env_only=True),
  ```
- `Stacky Agents/backend/.env.example` — agregar las 3 keys con default y comentario (1 línea c/u).
- `Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1` — agregar a `HARNESS_TEST_FILES`: `test_ado_edit_diff.py`, `test_ado_edit_detect.py`, `test_ado_edit_ledger.py`, `test_ado_edit_learning.py`, `test_ado_edit_sweep.py`.

**Test primero:** `Stacky Agents/backend/tests/test_harness_flags.py` (extender): aserción de que las 3 keys nuevas están en `FLAG_REGISTRY` con `group="global"` y `env_only=True`. El meta-test del plan 49 F4 valida que los 5 archivos nuevos estén registrados (correrlo).
**Aceptación binaria:** `test_harness_flags.py` verde + meta-test del ratchet verde + el panel de flags muestra las 3 (verificación visual o assert del endpoint que serializa FLAG_REGISTRY).
**Flag:** N/A.
**Runtime/fallback:** N/A (config).
**Trabajo del operador:** opt-in vía UI; default off.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | Falso positivo: tratar una revisión de Stacky como humana ⇒ lección circular | `is_human_edit` exige autor ≠ servicio + rev > baseline_rev + diff material; `STACKY_ADO_SERVICE_IDENTITY` configurable cierra el caso exacto |
| R2 | Duplicar lecciones por la misma edición | Ledger `(ado_id, rev)` persistente; si DB falla, `already_learned=True` (no duplica) |
| R3 | Costo/carga sobre ADO | Sweep cada 6 h, ≤50 runs, 1 GET por run, sin paralelismo; ledger evita re-leer lo ya aprendido |
| R4 | Romper byte-identidad con flag OFF | Thread NO se arma con flag OFF; GET de baseline (F1) gateado por el mismo flag; test de humo lo verifica |
| R5 | Reintroducir autonomía (matar como plan 57) | El plan NUNCA publica/re-aplica; solo escribe memoria local. Guardarraíl §3.1 explícito |
| R6 | Baseline HTML no capturable en F1 | Degradar a `oldValue` del body en la revisión, o `''`; aún se aprende de `added_snippets` |
| R7 | Plan 56 ausente | `_golden_available()` degrada a solo-lección; documentado |
| R8 | Lección ruidosa por edición trivial | `_MIN_EDIT_CHARS` + `diff_is_material` filtran cosméticos |
| R9 | Asimetría: solo épicas autopublicadas por claude_code_cli tienen baseline | Documentado como esperado; los otros runtimes no autopublican (memoria `autopublish-only-claude-cli`). El sweep los saltea sin error |

---

## 6. Fuera de scope

- Re-publicar o auto-aplicar cambios al WI en ADO (PROHIBIDO — human-in-the-loop).
- Diff semántico vía LLM (el diff es puro/determinista; cero tokens).
- Discriminar entre múltiples humanos editores (mono-operador, sin auth).
- Aprender de ediciones a WI NO publicados por Stacky (sin baseline ⇒ fuera).
- Implementar el plan 56 (golden gate) — solo se consume si está presente.
- UI dedicada para visualizar las lecciones derivadas (reusa el panel de memoria existente; opcional futuro).
- Webhooks/push de ADO (event-driven) — el sweep pasivo es suficiente; event-driven es mejora futura.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario
- **Baseline.** HTML + revisión + autor que Stacky publicó originalmente (sellado en metadata del run, F1).
- **Edición humana aprendible.** Revisión posterior del WI, de autor ≠ servicio, que cambia el body de forma material (§3).
- **Lección.** Memoria determinista en el corpus del plan 54 (tag `ado_human_edit`) inyectada en el prefix de los 3 runtimes.
- **Golden positivo.** Baseline de calidad = versión humana, registrado en el gate del plan 56 (si presente).
- **Ledger.** Tabla `ado_edit_learned(ado_id, rev)` que garantiza idempotencia.
- **Sweep.** Daemon periódico pasivo que dispara el read-back (no bloquea runs).

### Orden de implementación (estricto)
F0 (diff puro) → F1 (sellar baseline) → F2 (detector puro) → F3 (ledger) → F4 (materializador) → F5 (sweep wiring) → F6 (flags UI + .env + registro tests). Cada fase verde antes de la siguiente.

### Definition of Done (binario)
1. Los 5 archivos de test nuevos + extensiones verdes con el comando exacto del §4 (intérprete `.venv\Scripts\python.exe`).
2. `STACKY_ADO_EDIT_LEARNING_ENABLED` ausente ⇒ no existe thread `stacky-ado-edit-daemon`, cero llamadas a ADO (test de humo F5).
3. Una edición humana material sobre un WI publicado ⇒ exactamente 1 lección nueva en `memory_store` (tag `ado_human_edit`) y, si plan 56 presente + flag ON, 1 golden positivo; reejecutar el sweep ⇒ 0 lecciones nuevas (idempotencia).
4. Las 3 flags aparecen en el endpoint de FLAG_REGISTRY (panel plan 33) y en `.env.example`.
5. Meta-test del ratchet (plan 49 F4) verde con los 5 archivos registrados.
6. Suite de conformance/paridad sin regresiones nuevas (comparar baseline por archivo, memoria `backend-test-suite-pollution`).

**Trabajo del operador: ninguno / opt-in default off.**
