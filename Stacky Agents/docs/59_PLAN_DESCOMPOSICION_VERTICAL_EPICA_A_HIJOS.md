# Plan 59 — Descomposición vertical épica → hijos (1 Epic → Features/Tasks)

> Estado: PROPUESTO (2026-06-20). NO implementado.
> Tipo: molécula VERTICAL (complementa, NO duplica, el plan 55 que es molécula HORIZONTAL brief→N épicas hermanas).
> Origen: finalista #2 del roadmap `Stacky Agents/docs/_roadmap/TOP5_2026-06-20_POST57_LOOP_MOLECULA_BIDIRECCIONAL.md`.
> Audiencia de implementación: modelo MENOR (Haiku/Codex/Copilot). Todo está dado: rutas exactas, nombres exactos, casos borde, tests primero, comandos exactos. NO inferir nada.

---

## 1. Título, objetivo y KPI

**Título:** Descomposición vertical de una épica aprobada en su jerarquía de hijos (Features/Tasks) en ADO, con PREVIEW solo-lectura que el operador aprueba ANTES de crear nada.

**Objetivo:** Hoy `autopublish_epic_from_run` (backend/api/tickets.py:5926) publica UN SOLO work item Epic. No existe desglose hijo automático: el operador desgaja Features/Tasks a mano en ADO. Este plan agrega una descomposición DETERMINÍSTICA: parsear el HTML de la épica (función pura) → lista de hijos propuestos (Features → Tasks) → mostrarlos en un PREVIEW → el operador aprueba → crear esos hijos colgando del Epic, idempotentemente, reusando la primitiva `ado.create_work_item(..., parent_ado_id=...)` ya existente.

**KPI binario:** Dado un brief que produjo un Epic con N bloques `<h2>RF-…` en su HTML, con la flag `STACKY_EPIC_DECOMPOSITION_ENABLED=true` y aprobación del operador, ADO termina con: 1 Epic (ya existente) + sus hijos colgados (1 Feature por sección/RF según contrato §4.F1) sin trabajo manual de desglose; un segundo POST idéntico NO crea duplicados (idempotente); con la flag OFF el comportamiento es exactamente el actual (solo Epic, 0 hijos).

---

## 2. Por qué ahora / gap

- **Gap:** brief→épica entrega un Epic suelto. El backlog jerárquico (Epic→Features→Tasks) que ADO espera lo arma el humano a mano. Es el cuello de botella post-épica.
- **Por qué ahora:** el plan 55 introdujo `build_epic_payload_preview` (tickets.py:5835, función PURA + NamedTuple `EpicPayloadPreview` en :5822) y el patrón de preview solo-lectura. La maquinaria de creación de hijos con parent link ya existe y está endurecida: `ado.create_work_item(work_item_type, fields, parent_ado_id=...)` (services/ado_client.py:565) + `_ensure_task_creation_parent` (tickets.py:3059) que resuelve jerarquía intermedia y reusa nodos vía `hierarchy_bridge`. Solo falta el parser épica→hijos y el wiring del preview+publicación. Cero reinvención.
- **Complementariedad:** 55 = horizontal (un brief → N épicas hermanas). 59 = vertical (una épica → sus hijos). No se pisan: 59 opera sobre UNA épica ya derivada/publicada.

---

## 3. Principios y guardarraíles (codificados en las fases)

1. **Parseo PURO = paridad 3 runtimes.** La función que convierte el HTML de la épica en lista de hijos es pura sobre texto: idéntica en Codex / Claude Code / GitHub Copilot. No depende del runtime.
2. **Publicación CLI-only (hereda degradación existente).** La creación real de hijos en ADO hereda la MISMA restricción que `autopublish_epic_from_run`: solo se dispara desde el flujo claude-CLI (agents.py:600-605, claude_code_cli_runner.py:1212 `_maybe_autopublish_epic`). Codex/Copilot NO autopublican hijos (igual que hoy no autopublican el Epic). Documentado en cada fase.
3. **Fallback duro:** si el HTML no tiene estructura de hijos parseable (0 bloques RF) → 0 hijos, solo el Epic. Comportamiento idéntico al actual. NUNCA falla por falta de hijos.
4. **Human-in-the-loop REFORZADO:** nada se crea en ADO sin que el operador apruebe la jerarquía propuesta en el preview. Prohibida la creación automática de hijos sin confirmación explícita. (El Epic padre conserva su comportamiento actual; los HIJOS exigen aprobación.)
5. **Cero trabajo extra:** opt-in, flag default OFF. Con OFF nadie ve preview ni hijos. Con ON, el operador VE el preview y decide.
6. **Mono-operador sin auth:** sin RBAC. Idempotencia para no duplicar hijos en reintentos (no asumir que un 403 protege nada — no hay 403 real).
7. **Config por UI (REGLA DURA, INNEGOCIABLE):** la flag `STACKY_EPIC_DECOMPOSITION_ENABLED` se registra en `backend/services/harness_flags.py` (FLAG_REGISTRY, que la UI ya consume — plan 33) + `backend/.env.example`. Queda editable por UI, default OFF.
8. **Reuso:** `build_epic_payload_preview` (preview), `ado.create_work_item(..., parent_ado_id=...)` + `_ensure_task_creation_parent` (creación + jerarquía), patrón `EpicPayloadPreview`. Cero primitivas nuevas de ADO.

---

## 4. Fases F0..F6

> Orden por dependencia. Cada fase es autocontenida: objetivo, valor, archivos exactos, nombres exactos, pseudocódigo con casos borde, TEST PRIMERO con comando exacto, criterio binario, flag, impacto por runtime + fallback, y línea de trabajo del operador.

> Intérprete del repo (usar SIEMPRE este, no `python` global): `.venv\Scripts\python.exe`. Comando base de test: `.venv\Scripts\python.exe -m pytest "<ruta>" -q`.

---

### F0 — Flag de configuración por UI (default OFF)

**Objetivo (1 frase):** registrar `STACKY_EPIC_DECOMPOSITION_ENABLED` en el FLAG_REGISTRY y en `.env.example`, default OFF, para que la descomposición sea opt-in y editable por UI.

**Valor:** habilita/inhabilita todo el plan desde la UI sin tocar código; cumple la regla dura de config-por-UI.

**Archivos exactos:**
- `Stacky Agents/backend/services/harness_flags.py` — agregar entrada en `FLAG_REGISTRY`.
- `Stacky Agents/backend/.env.example` — agregar línea documentada.

**Contrato exacto:**
- Key env: `STACKY_EPIC_DECOMPOSITION_ENABLED`
- Tipo: bool. Default: `false` (OFF).
- Lectura canónica (helper a crear en F1): `os.getenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "false").strip().lower() in ("1", "true", "on", "yes")`. (Mismo patrón que `STACKY_ARTIFACT_RESCUE_ENABLED`, tickets.py:5966-5968.)

**Pseudocódigo (entrada en FLAG_REGISTRY — copiar la forma de las entradas vecinas existentes, p.ej. `STACKY_EPIC_GATE_ENABLED`):**
```python
"STACKY_EPIC_DECOMPOSITION_ENABLED": {
    "type": "bool",
    "default": False,
    "label": "Descomposición vertical épica→hijos",
    "description": "Si está ON, tras aprobar una épica el operador puede previsualizar y crear los hijos (Features/Tasks) colgando del Epic. Default OFF = solo el Epic.",
    "group": "epic",   # usar el group que usen las flags STACKY_EPIC_* vecinas
},
```
> Caso borde: si la forma exacta de las entradas vecinas difiere (claves distintas), REPLICAR la forma de `STACKY_EPIC_GATE_ENABLED` byte a byte, cambiando solo name/label/description/default. No inventar campos nuevos del registry.

**Línea en `.env.example`:**
```
# Plan 59 — Descomposición vertical épica→hijos (opt-in, editable por UI). Default OFF.
STACKY_EPIC_DECOMPOSITION_ENABLED=false
```

**TEST PRIMERO:**
- Archivo: `Stacky Agents/backend/tests/test_harness_flags.py` (ya existe; agregar caso).
- Caso: `test_epic_decomposition_flag_registered` — assert que `"STACKY_EPIC_DECOMPOSITION_ENABLED"` está en `FLAG_REGISTRY` y su default es `False`.
- Comando: `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q`

**Criterio de aceptación binario:** el test pasa Y `grep STACKY_EPIC_DECOMPOSITION_ENABLED ".env.example"` devuelve la línea.

**Impacto por runtime + fallback:** ninguno aún (solo registro). Igual en los 3 runtimes.

**Trabajo del operador:** ninguno / opt-in default off.

---

### F1 — Parser PURO épica → árbol de hijos (`build_epic_children_plan`)

**Objetivo (1 frase):** función PURA que toma el HTML limpio de una épica y devuelve la jerarquía de hijos propuesta (lista de Features, cada una con sus Tasks), sin tocar ADO/BD/disco.

**Valor:** corazón del plan; determinístico e idéntico en los 3 runtimes; testeable aisladamente.

**Archivo exacto:** `Stacky Agents/backend/api/tickets.py` (junto a `build_epic_payload_preview`, ~después de :5907).

**Contrato de parseo HTML→hijos (SIN AMBIGÜEDAD):**

El HTML de la épica ya viene saneado por `_extract_epic_html` y validado por `_looks_like_epic` (requiere ≥1 heading + ≥1 bloque `<h2>RF-N`). Reglas deterministas:

1. **Cada bloque `<h2 ...>RF-N …</h2>` define UNA Feature.** Regex de delimitación (idéntica al split ya usado en `_dedup_identical_rf_blocks`, tickets.py:5481): `re.split(r"(?=<h2[^>]*>\s*RF-\d)", html, flags=re.IGNORECASE)`. El preámbulo antes del primer RF se descarta (no es Feature).
2. **Título de la Feature** = texto plano del heading `<h2>` de ese bloque, sin tags, colapsando espacios, truncado a 250 chars (reusar `_strip_tags`/lógica de `_derive_epic_title` si existe; si no, regex `re.sub(r"<[^>]+>", "", heading)`).
3. **Descripción HTML de la Feature** = el bloque RF completo (heading + cuerpo hasta el próximo `<h2>RF-` o fin).
4. **Tasks dentro de una Feature (nivel opcional, determinístico):** cada `<li>` directo dentro del PRIMER `<ul>`/`<ol>` del bloque RF que tenga marca de tarea se vuelve una Task. Marca de tarea = el `<li>` cuyo texto plano empieza (tras trim, case-insensitive) con `T-`, `Task:`, `Tarea:` o `TODO:`. Título de la Task = texto plano del `<li>` sin el prefijo, truncado a 250. Descripción HTML de la Task = el `<li>` completo. Si ningún `<li>` cumple → la Feature no tiene Tasks (lista vacía). **No inferir Tasks de prosa libre.**
5. **Tipos ADO:** Feature → `work_item_type="Feature"`; Task → `work_item_type="Task"`. (La resolución de jerarquía intermedia Epic→Feature→Task la hace `_ensure_task_creation_parent` en F4; el parser NO decide jerarquía ADO, solo estructura lógica.)

**Estructuras de datos (NamedTuples, junto a `EpicPayloadPreview`):**
```python
class ChildNodePreview(NamedTuple):
    work_item_type: str        # "Feature" | "Task"
    title: str                 # texto plano, ≤250
    html: str                  # descripción HTML del nodo
    children: list = []        # type: ignore[assignment]  # Tasks bajo una Feature

class EpicChildrenPlan(NamedTuple):
    ok: bool
    features: list = []        # type: ignore[assignment]  # list[ChildNodePreview]
    total_children: int = 0    # features + tasks
    error: str | None = None   # "empty_html" | "no_children_parseable" | None
```

**Pseudocódigo:**
```python
def build_epic_children_plan(*, epic_html: str | None) -> EpicChildrenPlan:
    """Plan 59 F1 — PURA. HTML de épica → jerarquía lógica de hijos.
    NO toca ADO/BD/disco. NUNCA lanza."""
    try:
        if not epic_html or not str(epic_html).strip():
            return EpicChildrenPlan(ok=False, features=[], total_children=0, error="empty_html")
        text = str(epic_html)
        parts = re.split(r"(?=<h2[^>]*>\s*RF-\d)", text, flags=re.IGNORECASE)
        rf_blocks = [p for p in parts if re.match(r"<h2[^>]*>\s*RF-\d", p, re.IGNORECASE)]
        if not rf_blocks:
            # Fallback duro: épica sin estructura hija → 0 hijos.
            return EpicChildrenPlan(ok=False, features=[], total_children=0, error="no_children_parseable")
        features = []
        total = 0
        for block in rf_blocks:
            heading = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.IGNORECASE | re.DOTALL)
            f_title = _plain_text(heading.group(1))[:250] if heading else "Feature"
            tasks = _parse_tasks_from_block(block)  # ver regla §4 punto 4
            total += 1 + len(tasks)
            features.append(ChildNodePreview(
                work_item_type="Feature", title=f_title, html=block.strip(), children=tasks,
            ))
        return EpicChildrenPlan(ok=True, features=features, total_children=total, error=None)
    except Exception:  # noqa: BLE001 — pura, nunca lanza
        return EpicChildrenPlan(ok=False, features=[], total_children=0, error="parse_error")
```
Helpers auxiliares (puros, mismo módulo):
- `_plain_text(html_fragment: str) -> str`: `re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html_fragment)).strip()`.
- `_parse_tasks_from_block(block: str) -> list[ChildNodePreview]`: extrae `<li>` del primer `<ul>|<ol>` con prefijo de tarea (`T-`/`Task:`/`Tarea:`/`TODO:`, case-insensitive). Devuelve `list[ChildNodePreview]` con `work_item_type="Task"`, `children=[]`.

**Casos borde explícitos:**
- HTML vacío/None → `ok=False, error="empty_html", total_children=0`.
- HTML válido como épica pero sin bloques RF parseables (no debería pasar tras `_looks_like_epic`, pero por defensa) → `ok=False, error="no_children_parseable"`. **Esto es el fallback duro:** el llamante NO crea hijos.
- Bloque RF sin lista de tareas → Feature con `children=[]` (válido).
- Bloques RF duplicados ya vienen deduplicados por `_extract_epic_html` (sanitize ON); si vinieran repetidos, cada uno genera una Feature (idempotencia real se garantiza en F4 por título+parent, no acá).

**TEST PRIMERO:**
- Archivo: `Stacky Agents/backend/tests/test_epic_decomposition.py` (NUEVO).
- Casos:
  1. `test_children_plan_empty_html_returns_error` → `build_epic_children_plan(epic_html=None).error == "empty_html"`.
  2. `test_children_plan_two_rf_blocks_two_features` → HTML con 2 `<h2>RF-1</h2>...<h2>RF-2</h2>` → `len(features)==2`, `total_children>=2`.
  3. `test_children_plan_parses_tasks_with_prefix` → un bloque RF con `<ul><li>T- hacer X</li><li>nota suelta</li></ul>` → la Feature tiene exactamente 1 Task con title "hacer X".
  4. `test_children_plan_feature_without_tasks` → bloque RF sin `<li>` de tarea → `features[0].children == []`.
  5. `test_children_plan_no_rf_blocks_fallback` → HTML `<h1>Épica</h1><p>prosa</p>` → `ok is False`, `error=="no_children_parseable"`, `total_children==0`.
  6. `test_children_plan_pure_never_raises` → input basura (`"<h2>RF-1<<<"`) → no lanza, devuelve EpicChildrenPlan.
- Comando: `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/test_epic_decomposition.py" -q`

**Criterio binario:** los 6 casos pasan.

**Impacto por runtime + fallback:** PURO → idéntico en los 3 runtimes. Fallback = `ok=False` → llamante no crea hijos.

**Trabajo del operador:** ninguno / opt-in default off.

---

### F2 — Endpoint de PREVIEW solo-lectura (`GET/POST /api/tickets/epic-children-preview`)

**Objetivo (1 frase):** endpoint que, dado el `output` de una run (o un epic ya publicado), devuelve la jerarquía de hijos propuesta SIN crear nada en ADO.

**Valor:** materializa el human-in-the-loop: el operador VE qué se va a crear antes de aprobar.

**Archivo exacto:** `Stacky Agents/backend/api/tickets.py` (registrar ruta en el blueprint `bp`, url_prefix `/tickets`).

**Contrato del endpoint:**
- Método: `POST` (recibe el output crudo; evita límites de querystring).
- Ruta: `/epic-children-preview` (→ `/api/tickets/epic-children-preview`).
- Body JSON: `{ "output": str|null, "brief": str (opcional), "project_name": str|null (opcional) }`.
- Guard de flag: si `STACKY_EPIC_DECOMPOSITION_ENABLED` OFF → `200 {"enabled": false, "features": [], "total_children": 0}` (NO 403; mono-operador, devolvemos estado, no error).
- Lógica:
  1. `preview = build_epic_payload_preview(output=output, brief=brief, project_name=project_name)` (reuso plan 55).
  2. Si `not preview.ok` → `200 {"enabled": true, "epic_ok": false, "epic_error": preview.error, "features": [], "total_children": 0}`.
  3. `plan = build_epic_children_plan(epic_html=preview.html)`.
  4. `200 {"enabled": true, "epic_ok": true, "epic_title": preview.title, "features": [<serializado>], "total_children": plan.total_children, "children_error": plan.error}`.
- Serialización de cada Feature: `{"work_item_type","title","html","children":[{"work_item_type","title","html"}]}`.
- NUNCA toca ADO/BD/disco. Solo-lectura puro.

**Casos borde:**
- `output` None/vacío → `epic_ok=false`, `epic_error="empty_output"`.
- épica sin hijos → `epic_ok=true`, `total_children=0`, `children_error="no_children_parseable"`. (Preview legítimo: "esta épica no tiene hijos parseables; con aprobar no se crea nada".)

**TEST PRIMERO:**
- Archivo: `Stacky Agents/backend/tests/test_epic_decomposition.py` (mismo de F1).
- Casos (usando el test client Flask, ver patrón en `test_epic_autopublish_backend.py`):
  1. `test_preview_endpoint_flag_off_returns_disabled` → monkeypatch flag OFF → POST → `200`, `json["enabled"] is False`.
  2. `test_preview_endpoint_returns_features` → flag ON + output con 2 RF → `json["total_children"]>=2`, `len(json["features"])==2`.
  3. `test_preview_endpoint_empty_output` → flag ON + output `""` → `json["epic_ok"] is False`.
  4. `test_preview_endpoint_does_not_touch_ado` → assert que NO se instancia/llama AdoClient (monkeypatch `build_ado_client` para que lance si se llama).
- Comando: `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/test_epic_decomposition.py" -q`

**Criterio binario:** los 4 casos pasan; el caso 4 garantiza solo-lectura.

**Impacto por runtime + fallback:** el preview es PURO → igual en los 3 runtimes (cualquiera puede previsualizar). Fallback: hijos no parseables → `total_children=0`.

**Trabajo del operador:** ninguno / opt-in default off.

> **Dependencia con plan 55:** este endpoint reusa `build_epic_payload_preview` (ya en código, tickets.py:5835). Si por algún motivo no existiera, degradar a preview mínimo propio: `clean = _extract_epic_html(output); if not _looks_like_epic(clean): epic_ok=False`. Documentado para que el implementador no se bloquee.

---

### F3 — Publicador idempotente de hijos (`publish_epic_children`)

**Objetivo (1 frase):** función que, dado un Epic ya publicado (`epic_ado_id`) y un `EpicChildrenPlan`, crea los hijos en ADO colgando del Epic, idempotentemente, reusando `ado.create_work_item(..., parent_ado_id=...)`.

**Valor:** el efecto real (backlog jerárquico en ADO) con cero duplicación en reintentos.

**Archivo exacto:** `Stacky Agents/backend/api/tickets.py`.

**Firma exacta:**
```python
class _ChildrenPublishResult(NamedTuple):
    created_ids: list = []        # type: ignore[assignment]  # ids creados ESTA corrida
    reused_ids: list = []         # type: ignore[assignment]  # ids ya existentes (idempotencia)
    error: str | None = None
    skipped: bool = False         # flag OFF o plan sin hijos

def publish_epic_children(
    *,
    epic_ado_id: int,
    children_plan: "EpicChildrenPlan",
    project_name: str | None,
    ado=None,                      # inyectable para tests; si None, build_ado_client(project_name)
) -> _ChildrenPublishResult:
    ...
```

**Idempotencia (SIN BD nueva):** antes de crear una Feature, listar los hijos directos actuales del Epic en ADO y comparar por `(work_item_type, title)` normalizado (trim + colapso espacios + lower). Si ya existe un hijo con mismo tipo+título → REUSAR su id (no crear). Para listar hijos: usar la primitiva de lectura de relaciones que ya use el código (grep `get_work_item` con `relations`, ado_client.py; si no hay un helper de "listar hijos", usar `ado.get_work_item(epic_ado_id, expand="relations")` y filtrar links `System.LinkTypes.Hierarchy-Forward`). Misma estrategia para Tasks bajo cada Feature.

**Pseudocódigo:**
```python
def publish_epic_children(*, epic_ado_id, children_plan, project_name, ado=None):
    if not _epic_decomposition_enabled():        # helper F0 (lee la flag)
        return _ChildrenPublishResult(skipped=True)
    if not children_plan.ok or not children_plan.features:
        return _ChildrenPublishResult(skipped=True)   # fallback duro: 0 hijos
    if ado is None:
        ado = build_ado_client(project_name)          # patrón existente
    created, reused = [], []
    try:
        existing_children = _list_child_titles(ado, epic_ado_id)  # {(type_norm, title_norm): id}
        for feature in children_plan.features:
            key = ("feature", _norm_title(feature.title))
            if key in existing_children:
                feature_id = existing_children[key]
                reused.append(feature_id)
            else:
                # _ensure_task_creation_parent NO aplica a Feature directa de Epic
                # (Epic acepta Feature en Agile). Para Task usar la jerarquía.
                res = ado.create_work_item(
                    work_item_type="Feature",
                    fields={"System.Title": feature.title, "System.Description": feature.html},
                    parent_ado_id=epic_ado_id,
                )
                feature_id = int(res["id"]); created.append(feature_id)
            # Tasks bajo la feature
            existing_tasks = _list_child_titles(ado, feature_id)
            for task in feature.children:
                tkey = ("task", _norm_title(task.title))
                if tkey in existing_tasks:
                    reused.append(existing_tasks[tkey]); continue
                # Epic→Feature→Task: Feature acepta Task directo en Agile; si el
                # template no lo permite, _ensure_task_creation_parent resuelve puente.
                res = ado.create_work_item(
                    work_item_type="Task",
                    fields={"System.Title": task.title, "System.Description": task.html},
                    parent_ado_id=feature_id,
                )
                created.append(int(res["id"]))
        return _ChildrenPublishResult(created_ids=created, reused_ids=reused, error=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_epic_children falló: %s", str(exc)[:200], exc_info=True)
        return _ChildrenPublishResult(created_ids=created, reused_ids=reused, error=str(exc)[:200])
```
Helpers:
- `_epic_decomposition_enabled() -> bool` (F0).
- `_norm_title(t: str) -> str`: `re.sub(r"\s+", " ", t).strip().lower()`.
- `_list_child_titles(ado, parent_id) -> dict[tuple[str,str], int]`: lee hijos directos del WI vía relations Hierarchy-Forward y devuelve mapa `{(type_norm, title_norm): child_id}`. Si la lectura falla → `{}` (degradar a "crear", aceptando que un reintento tras fallo de lectura podría duplicar — mitigado porque el flujo normal lee bien; documentar en Riesgos).

**Casos borde:**
- Flag OFF → `skipped=True`, 0 llamadas a ADO.
- `children_plan.ok is False` o sin features → `skipped=True` (fallback duro, solo Epic).
- Reintento idéntico → todas las features/tasks caen en `reused_ids`, `created_ids=[]` (idempotente).
- Template ADO que no permite Task directo bajo Feature → reusar `_ensure_task_creation_parent` (tickets.py:3059) en vez de `create_work_item` plano para las Tasks. **Nota implementación:** envolver la creación de Task con la misma resolución de jerarquía que usa `create_child_task`; si el template estándar (Agile) permite Task bajo Feature, el camino directo basta. Probar con mock que simula ambos.
- Fallo a media corrida → devolver lo creado en `created_ids` + `error` (no rollback; ADO no es transaccional; el reintento idempotente completa el resto).

**TEST PRIMERO:**
- Archivo: `Stacky Agents/backend/tests/test_epic_decomposition.py`.
- Usar un `FakeAdo` (clase de test, igual patrón que mocks en `test_epic_autopublish_backend.py`) que registra `create_work_item` calls y simula `get_work_item(expand="relations")`.
- Casos:
  1. `test_publish_children_flag_off_skips` → flag OFF → `skipped is True`, `FakeAdo.create_calls == []`.
  2. `test_publish_children_creates_features_and_tasks` → plan con 1 Feature + 1 Task → `created_ids` tiene 2 ids; parent de la Feature == epic_ado_id; parent de la Task == feature_id.
  3. `test_publish_children_idempotent_reuses` → FakeAdo precargado con la Feature ya existente → segunda llamada → `created_ids==[]`, `reused_ids` no vacío.
  4. `test_publish_children_empty_plan_skips` → `EpicChildrenPlan(ok=False)` → `skipped is True`.
  5. `test_publish_children_ado_failure_returns_error_no_raise` → FakeAdo lanza en la 2ª creación → resultado tiene `error` y `created_ids` con la 1ª; no propaga excepción.
- Comando: `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/test_epic_decomposition.py" -q`

**Criterio binario:** los 5 casos pasan; el caso 3 prueba idempotencia, el caso 2 prueba el parent link correcto.

**Impacto por runtime + fallback:** la FUNCIÓN es runtime-agnóstica, pero solo el flujo claude-CLI la INVOCA (F4). Fallback: plan vacío/flag OFF → 0 hijos, solo Epic.

**Trabajo del operador:** ninguno (la aprobación se da vía endpoint F5; esta función solo ejecuta tras aprobación).

---

### F4 — Endpoint de CREACIÓN tras aprobación (`POST /api/tickets/epic-children`)

**Objetivo (1 frase):** endpoint que el frontend llama cuando el operador APRUEBA el preview, ejecutando `publish_epic_children` sobre un Epic ya publicado.

**Valor:** el handshake de aprobación humana → efecto en ADO. Es el ÚNICO camino que crea hijos.

**Archivo exacto:** `Stacky Agents/backend/api/tickets.py` (blueprint `bp`).

**Contrato:**
- Método `POST`, ruta `/epic-children` (→ `/api/tickets/epic-children`).
- Body JSON: `{ "epic_ado_id": int, "output": str (de la run, para re-derivar el plan server-side), "project_name": str|null }`.
- **Seguridad anti-tamper:** el backend NO confía en una lista de hijos enviada por el cliente; RE-DERIVA el plan server-side desde `output` (preview F1) y crea EXACTAMENTE eso. (Evita que un body manipulado cree WIs arbitrarios. Coherente con mono-operador: aunque no hay auth, no se ejecuta input no validado.)
- Guard flag OFF → `200 {"enabled": false, "created_ids": [], "reused_ids": []}`.
- Guard `epic_ado_id` ausente/no-int → `400 {"error": "epic_ado_id_required"}`.
- Lógica:
  1. `preview = build_epic_payload_preview(output=output, brief="", project_name=project_name)`.
  2. Si `not preview.ok` → `409 {"error": "epic_not_in_output"}` (no hay épica de la cual derivar hijos).
  3. `plan = build_epic_children_plan(epic_html=preview.html)`.
  4. `result = publish_epic_children(epic_ado_id=epic_ado_id, children_plan=plan, project_name=project_name)`.
  5. `200 {"enabled": true, "created_ids": result.created_ids, "reused_ids": result.reused_ids, "error": result.error, "skipped": result.skipped}`.

**Casos borde:** flag OFF (200 disabled); épica no parseable (409); plan sin hijos (200, created=[], skipped=true); reintento (200, reused poblado).

**TEST PRIMERO:**
- Archivo: `Stacky Agents/backend/tests/test_epic_decomposition.py`.
- Casos:
  1. `test_children_endpoint_flag_off` → 200, enabled false.
  2. `test_children_endpoint_missing_epic_id_400` → body sin epic_ado_id → 400.
  3. `test_children_endpoint_creates_via_fake_ado` → flag ON + monkeypatch `build_ado_client`→FakeAdo + output con 1 RF → 200, `created_ids` no vacío.
  4. `test_children_endpoint_rederives_server_side` → body trae `output` real + un campo espurio `"children":[...]` → assert que los hijos creados salen del parse del output, NO del campo espurio.
- Comando: `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/test_epic_decomposition.py" -q`

**Criterio binario:** los 4 casos pasan; el caso 4 prueba la re-derivación anti-tamper.

**Impacto por runtime + fallback:** este endpoint puede invocarse desde cualquier runtime (es HTTP), pero crea hijos solo si la flag está ON y hay ADO configurado; la PUBLICACIÓN comparte la naturaleza CLI-only del flujo épica (un Codex/Copilot que no llegó a publicar el Epic no tendrá `epic_ado_id` para descomponer). Fallback: plan vacío → 0 hijos.

**Trabajo del operador:** APROBAR el preview (un clic). Sin la flag ON, este endpoint ni se expone en UI.

---

### F5 — UI: preview de jerarquía + botón "Crear hijos en ADO"

**Objetivo (1 frase):** mostrar, tras una épica publicada, la jerarquía de hijos propuesta (Features→Tasks) con un botón que el operador pulsa para crearlos, solo si la flag está ON.

**Valor:** cierra el human-in-the-loop visualmente; cero trabajo de desglose manual.

**Archivos exactos:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — agregar `epicChildrenPreview(body)` (POST `/tickets/epic-children-preview`) y `createEpicChildren(body)` (POST `/tickets/epic-children`).
- `Stacky Agents/frontend/src/components/OutputPanel.tsx` — donde hoy se muestra el resultado de la épica autopublicada, agregar (condicional a flag ON, leída del estado de harness flags que la UI ya consume — plan 33) un sub-panel `EpicChildrenPanel`.
- Componente nuevo: `Stacky Agents/frontend/src/components/EpicChildrenPanel.tsx`.

**Contrato UI:**
- Al montar (solo si flag ON y hay `epic_ado_id` + `output` de la run), llama `epicChildrenPreview({output, project_name})`.
- Renderiza árbol: por cada Feature, su título + lista de Tasks. Muestra `total_children`.
- Si `total_children===0` → muestra "Esta épica no tiene hijos descomponibles" (NO botón de crear).
- Botón "Crear N hijos en ADO" → confirma (dialog) → `createEpicChildren({epic_ado_id, output, project_name})` → muestra `created_ids`/`reused_ids` y deshabilita el botón tras éxito.
- Estados: loading, error (muestra `error` del backend), éxito.

**Casos borde:** flag OFF → panel no se renderiza; preview con `epic_ok=false` → mensaje "no hay épica que descomponer"; reintento → muestra "ya existían M, creados K".

**TEST PRIMERO (frontend):**
- Vitest no está instalado (memoria `stacky-backend-dev-test-env`). Por tanto la verificación frontend es: `npx tsc --noEmit` desde `Stacky Agents/frontend` → 0 errores TS. (TDD frontend no viable sin runner; se documenta la razón en 1 línea — regla de la guía.)
- Comando: (desde `Stacky Agents/frontend`) `npx tsc --noEmit`

**Criterio binario:** `npx tsc --noEmit` devuelve 0 errores Y el panel solo se renderiza con flag ON (revisión visual del condicional).

**Impacto por runtime + fallback:** UI única; muestra hijos solo si el backend (CLI-only para publicación del Epic) dio un `epic_ado_id`. Fallback: sin hijos → mensaje, sin botón.

**Trabajo del operador:** un clic de aprobación. Opt-in default off.

---

### F6 — Registro de tests en el ratchet (obligatorio)

**Objetivo (1 frase):** registrar `test_epic_decomposition.py` en las listas del runner de tests del arnés para que el meta-test del plan 49 F4 no falle.

**Valor:** cumple la regla dura del ratchet (memoria `stacky-ratchet-obliga-registrar-tests`): todo test nuevo del backend va en `HARNESS_TEST_FILES`.

**Archivos exactos:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar `"tests/test_epic_decomposition.py"` a la lista `HARNESS_TEST_FILES`.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — agregar la misma entrada a su lista equivalente.

**TEST PRIMERO:** el meta-test existente (plan 49 F4) que verifica que todo archivo `tests/test_*.py` está registrado. Tras agregar el nuevo test sin registrarlo, ese meta-test FALLA; tras registrarlo, PASA.
- Comando: correr la suite del ratchet (el meta-test del plan 49). Buscar el archivo con `grep -rl "HARNESS_TEST_FILES" "Stacky Agents/backend/tests"` y correr ese archivo:
  `.venv\Scripts\python.exe -m pytest "<archivo_meta_test>" -q`

**Criterio binario:** el meta-test del ratchet pasa con el nuevo archivo presente.

**Impacto por runtime + fallback:** N/A (infra de test).

**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | Duplicación de hijos en reintento tras fallo de lectura de relaciones (`_list_child_titles` devuelve `{}`) | Idempotencia por (tipo,título) cubre el caso normal. Documentado que un fallo de LECTURA seguido de reintento podría duplicar; aceptable mono-operador (operador ve el preview y los ids creados). No introducir BD nueva para esto. |
| R2 | Template ADO no permite Task bajo Feature | Reusar `_ensure_task_creation_parent` (tickets.py:3059) para Tasks; probar con mock de template restrictivo. |
| R3 | Parser malinterpreta prosa como Task | Contrato §4.F1 punto 4 exige prefijo explícito (`T-`/`Task:`/`Tarea:`/`TODO:`); sin prefijo → no es Task. Determinístico. |
| R4 | Operador crea hijos sin querer | Flag default OFF + preview + botón con confirmación. Nada automático. |
| R5 | Plan 55 (`build_epic_payload_preview`) ausente | Verificado presente (tickets.py:5835). Fallback documentado en F2 (preview mínimo propio). |
| R6 | Body manipulado en F4 crea WIs arbitrarios | F4 RE-DERIVA el plan server-side desde `output`; ignora cualquier lista de hijos del cliente. |
| R7 | Falso "completado" si crea unos hijos y falla otros | `_ChildrenPublishResult` devuelve `created_ids` + `error`; UI muestra parcial; reintento idempotente completa. |

---

## 6. Fuera de scope

- Generación de NUEVAS épicas o variación del contenido del Epic (eso es plan 55 horizontal).
- Edición del HTML de la épica desde la UI antes de descomponer.
- Estimaciones, asignación de responsables, sprints o iteration paths en los hijos.
- Autopublicación de hijos SIN aprobación humana (prohibido por guardarraíl #4).
- Descomposición en runtimes no-CLI más allá del preview (la publicación hereda CLI-only; no se "arregla" acá).
- Persistencia en BD local de la jerarquía de hijos (idempotencia se resuelve leyendo ADO).
- Soporte de tipos de WI distintos a Feature/Task (p.ej. User Story, PBI) — extensible luego.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario
- **Descomposición vertical:** una épica → sus hijos en el eje Epic→Feature→Task. (Vs. horizontal del plan 55: brief→N épicas hermanas.)
- **Bloque RF:** segmento del HTML de la épica que empieza en `<h2>RF-N…</h2>` y va hasta el próximo `<h2>RF-` o fin. Define una Feature.
- **Marca de tarea:** prefijo (`T-`/`Task:`/`Tarea:`/`TODO:`) en el texto de un `<li>` que lo convierte en Task.
- **Idempotencia por (tipo,título):** no se crea un hijo si ya existe uno con mismo tipo y título normalizado bajo el mismo parent.
- **CLI-only (publicación):** la creación real de WIs hereda la restricción de `autopublish_epic_from_run` (solo flujo claude-CLI). El PREVIEW es runtime-agnóstico.
- **Fallback duro:** épica sin bloques RF parseables → 0 hijos, solo el Epic = comportamiento actual.

### Orden de implementación (estricto)
F0 (flag) → F1 (parser puro + tests) → F2 (endpoint preview + tests) → F3 (publicador idempotente + tests) → F4 (endpoint creación + tests) → F5 (UI) → F6 (ratchet). Cada fase se cierra con su comando de test en verde antes de la siguiente.

### Definition of Done (binario)
1. F0–F4 y F6: `.venv\Scripts\python.exe -m pytest "Stacky Agents/backend/tests/test_epic_decomposition.py" "Stacky Agents/backend/tests/test_harness_flags.py" -q` → todo verde.
2. F5: `npx tsc --noEmit` (en `Stacky Agents/frontend`) → 0 errores.
3. Meta-test del ratchet (plan 49 F4) → verde con el nuevo archivo registrado.
4. Con `STACKY_EPIC_DECOMPOSITION_ENABLED=false`: el flujo brief→épica produce SOLO el Epic (0 hijos, 0 preview) — comportamiento idéntico al actual (verificable por test F1 caso fallback + F3 caso skip).
5. Con la flag ON + aprobación: una épica con N bloques RF produce N Features (+ Tasks por marca) colgando del Epic; un segundo POST idéntico no crea duplicados (test F3 idempotencia).
6. Cero primitivas ADO nuevas: solo `ado.create_work_item(..., parent_ado_id=...)` y lectura de relaciones existente.

---

**Trabajo del operador (global): ninguno por defecto / opt-in default OFF. Con la flag ON, el único trabajo es aprobar el preview con un clic.**
