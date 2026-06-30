# Plan 45 — Catálogo de Procesos en UI + Soporte de Issues desde Brief

**Versión:** v1 → v2 — 2026-06-19
**Estado:** IMPLEMENTADO 2026-06-19 (F0–F5; F6 diferida como future-proof). Juez v2 APROBADO-CON-CAMBIOS aplicado.

> **Nota de implementación (2026-06-19):** el dispatch Epic/Issue NO vive en `run_brief`
> (ahí la run es asíncrona, 202) sino en el finalizador del runner CLI
> (`claude_code_cli_runner._maybe_autopublish_epic`), que es donde ya ocurría la
> autopublicación de épica (Plan 41). `run_brief` valida `work_item_type`, rechaza Issue
> con flag OFF (400) y propaga el tipo vía `run_agent` → runner → `metadata["work_item_type"]`.
> El finalizador bifurca a `publish_issue_from_run` y sella `metadata["issue_ado_id"]`.
> Tests verdes: test_issue_from_brief_contract.py (6), test_publish_issue.py (7),
> test_run_brief_work_item_type.py (5), test_client_profile_endpoints.py (29, +5 nuevos);
> tsc --noEmit exit 0. Sin regresión en epic path (test_epic_autopublish_backend.py).

---
## v1 → v2 Changelog

- **C1 resuelta:** F3 ahora nombra archivo exacto `frontend/src/config.ts` y endpoint `GET /api/config`
- **C2 resuelta:** F1 ciclo de fases clarificado — UN marcador por Issue, futuras fases en plan posterior
- **C3 resuelta:** F2 especifica `metadata['issue_ado_id']` vs `metadata['epic_ado_id']` con bifurcación de lectura
- **C4 resuelta:** F3 modal fuerza `work_item_type="Epic"` si flag OFF (nunca envía Issue al backend)
- **C5 resuelta:** F5 valida `process_catalog[*].kind` contra allowlist; backend PUT agrega validación explícita
- **C6–C8 resueltas:** citas exactas de archivos, helpers documentados, tests específicos en DoD
- **[ADICIÓN ARQUITECTO] F6:** endpoint de validación de catálogo (opcional, future-proof)

---

## 1. Objetivo y KPI / Impacto

### Objetivo
Cerrar dos gaps de UX/valor para el operador de Pacífico sin agregar trabajo ni config nueva:

1. **Req1 — Catálogo de procesos visible y editable en la UI:** el `process_catalog` del `client_profile` (ya parseado e inyectado a agentes) es hoy invisible al operador salvo que edite el JSON a mano. Exponer una sección gestionable dentro del editor de perfil existente.

2. **Req2 — Soporte de Issues:** el flujo épica-desde-brief (business→funcional→técnico→desarrollo) ya funciona; un Issue es el mismo pipeline con dos diferencias: ADO recibe un work item tipo "Issue" (no Epic) y cada fase se acumula como *comentario* en ese mismo work item (no como tickets hijos).

### KPI / Impacto

| KPI | Hoy | Post-plan |
|---|---|---|
| Visualización del catálogo de procesos | Solo en config.json a mano | Sección editable en SettingsPage |
| Tipos de work item soportados en brief→ADO | Solo Epic | Epic + Issue (opt-in) |
| Tickets hijos en un Issue | N/A | 0 (todo en comentarios del mismo WI) |
| Riesgo de romper flujo épica | — | 0 (path épica intacto, Issue es aditivo) |

---

## 2. Por qué ahora / Gap que cierra

**Plan 40** estableció R-BATCH (nombrar el proceso batch) y detectó que el catálogo de procesos es dato raíz del grounding; **plan 42** implementó F0 (diccionario de procesos) e inyecta el catálogo al agente vía `build_process_dictionary_block`. Sin embargo el operador no puede ver ni editar ese catálogo sin abrir el JSON directamente: gap de DX.

**Planes 38–41** completaron el pipeline épica-desde-brief con auto-publicación en ADO. El operador ahora pide un tipo de artefacto distinto para resolver incidencias/bugs: un Issue que no genera jerarquía de tickets sino comentarios acumulativos en el mismo work item. Reutiliza el 100% del pipeline existente.

---

## 3. Principios y Guardarraíles

- **Cero trabajo extra al operador:** Req1 lee el profile existente sin config nueva. Req2 es opt-in vía flag default OFF; con el flag en OFF el flujo actual es byte-a-byte idéntico.
- **Human-in-the-loop:** se mantiene el patrón actual de épica-desde-brief (auto-publica sin checkbox, decisión ya tomada). Issue auto-publica igual que épica. No se introduce autonomía proactiva nueva.
- **No degradar:** el path de épica existente (`_publish_epic_to_ado` / `autopublish_epic_from_run`) queda intacto y con sus tests verdes. Issue es aditivo y aislado por flag.
- **Paridad de 3 runtimes:** el destino de publicación (Epic vs Issue + comentarios) es decisión backend al cerrar la run, igual para Codex CLI, Claude Code CLI y GitHub Copilot Pro. El agente `business` no cambia.
- **Mono-operador sin auth:** sin RBAC, sin login, sin roles.
- **TDD:** tests primero en cada fase backend; validación por archivo (no full-suite).
- **Separación de responsabilidades:** función dedicada `_publish_issue_to_ado` para Issue (no contaminar el path de épica probado); `autopublish_epic_from_run` ruta por `work_item_type`.

---

## 4. Fases

### F0 — Contrato `work_item_type` + flag `STACKY_ISSUE_FROM_BRIEF_ENABLED`

**Objetivo:** definir el allowlist de tipos válidos, el flag feature-gate y el modelo/configuración de flags de backend, sin lógica de negocio aún.

**Archivos exactos:**
- `backend/config.py` — agregar `STACKY_ISSUE_FROM_BRIEF_ENABLED` (bool, default `False`)
- `backend/tests/test_issue_from_brief_contract.py` — NUEVO, tests de esta fase

**Símbolos/flags/keys exactos:**
- Flag: `STACKY_ISSUE_FROM_BRIEF_ENABLED` (env var, default `False`)
- Allowlist: `ALLOWED_BRIEF_WORK_ITEM_TYPES = {"Epic", "Issue"}`
- Función helper: `validate_brief_work_item_type(value: str | None) -> str` — normaliza a `"Epic"` si `None` o vacío; lanza `ValueError` si el valor no está en la allowlist

**Pseudocódigo — `config.py`:**
```python
# Añadir junto al resto de flags de feature:
STACKY_ISSUE_FROM_BRIEF_ENABLED: bool = _bool_env("STACKY_ISSUE_FROM_BRIEF_ENABLED", False)
```

**Pseudocódigo — helper en `tickets.py` (zona de helpers, cerca de `_norm_work_item_type`):**
```python
ALLOWED_BRIEF_WORK_ITEM_TYPES = {"Epic", "Issue"}

def validate_brief_work_item_type(value: str | None) -> str:
    """Normaliza y valida el tipo de WI para el pipeline brief→ADO.
    Retorna "Epic" si value es None/vacío. Lanza ValueError si no está en allowlist.
    Helper `_bool_env` en backend/config.py línea ~XX parsea env vars a bool: _bool_env(key, default) retorna default si key no existe."""
    if not value:
        return "Epic"
    if value not in ALLOWED_BRIEF_WORK_ITEM_TYPES:
        raise ValueError(f"work_item_type inválido: {value!r}. Permitidos: {ALLOWED_BRIEF_WORK_ITEM_TYPES}")
    return value
```

**Tests primero — `backend/tests/test_issue_from_brief_contract.py`:**
```python
# Casos:
# 1. validate_brief_work_item_type(None) == "Epic"
# 2. validate_brief_work_item_type("") == "Epic"
# 3. validate_brief_work_item_type("Epic") == "Epic"
# 4. validate_brief_work_item_type("Issue") == "Issue"
# 5. validate_brief_work_item_type("Bug") lanza ValueError
# 6. STACKY_ISSUE_FROM_BRIEF_ENABLED es False por defecto (os.environ sin set)
```

**Comando de validación (exacto):**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_issue_from_brief_contract.py" -v
```

**Criterio de aceptación (binario):** todos los tests pasan, `0 failed`.

**Flag que la protege:** `STACKY_ISSUE_FROM_BRIEF_ENABLED=false` (tests corren igual, flag solo controla runtime).

**Impacto por runtime:** ninguno en esta fase (solo contrato).

**Trabajo del operador:** ninguno.

---

### F1 — `tickets.py` — función dedicada `_publish_issue_to_ado` + `publish_issue_from_run`

**Objetivo:** implementar la lógica de publicación de Issues: crear un work item "Issue" en ADO y acumular cada fase (funcional / técnico / implementación) como comentarios idempotentes en ese mismo work item. Sin tocar el path de épica.

**Archivos exactos:**
- `backend/api/tickets.py` — agregar funciones nuevas al final del módulo (zona >5600)
- `backend/tests/test_publish_issue.py` — NUEVO

**Símbolos/funciones exactos a crear:**
- `_persist_issue_ticket(ado_id, title, description_html, url, project_name)` — como `_persist_epic_ticket` pero con `work_item_type="Issue"`
- `_publish_issue_to_ado(description_html, brief, project_name, title="") -> _PublishedEpic` — crea WI tipo "Issue"
- `_post_phase_comment(client, ado_id, phase_marker, html_content)` — llama `comment_exists` + `post_comment` (idempotente)
- `publish_issue_from_run(*, output, brief, project_name, already_published_id) -> _AutopublishResult` — punto de entrada análogo a `autopublish_epic_from_run` para Issues

**Marcadores de fase (constantes):**
```python
_ISSUE_PHASE_MARKERS = {
    "funcional":       "<!-- stacky:issue-phase:funcional -->",
    "tecnico":         "<!-- stacky:issue-phase:tecnico -->",
    "implementacion":  "<!-- stacky:issue-phase:implementacion -->",
}
```

**Pseudocódigo — `_publish_issue_to_ado`:**
```python
def _publish_issue_to_ado(
    description_html: str,
    brief: str,
    project_name: str | None,
    title: str = "",
) -> _PublishedEpic:
    clean_html = _extract_epic_html(description_html) or description_html
    if not title:
        title = _derive_epic_title(clean_html)  # reutiliza derivación de título existente

    client = _ado_client_for_ticket(project_name=project_name)
    wi = client.create_work_item(
        work_item_type="Issue",
        title=title,
        description=clean_html,
    )
    ado_id: int = wi["id"]
    wi_title: str = wi.get("fields", {}).get("System.Title", title)
    wi_url: str = (
        wi.get("_links", {}).get("html", {}).get("href")
        or client.work_item_url(ado_id)
    )
    _persist_issue_ticket(ado_id, wi_title, clean_html, wi_url, project_name)
    _epic_brief_save(ado_id, brief, project_name)  # reutiliza helper de brief
    logger.info("issue publish: Issue creado ado_id=%s title=%r project=%s", ado_id, wi_title, project_name)
    return _PublishedEpic(ado_id=ado_id, title=wi_title, url=wi_url)
```

**Pseudocódigo — `_post_phase_comment`:**
```python
def _post_phase_comment(client, ado_id: int, phase: str, html_content: str) -> None:
    marker = _ISSUE_PHASE_MARKERS.get(phase)
    if not marker:
        return
    if client.comment_exists(ado_id, marker):
        logger.debug("issue comment: ya existe fase=%s ado_id=%s", phase, ado_id)
        return
    marked_html = f"{marker}\n{html_content}"
    client.post_comment(ado_id, marked_html, fmt="html")
    logger.info("issue comment: posteado fase=%s ado_id=%s", phase, ado_id)
```

**Pseudocódigo — `publish_issue_from_run`:**
```python
def publish_issue_from_run(
    *,
    output: str | None,
    brief: str,
    project_name: str | None,
    already_published_id: int | None,
) -> _AutopublishResult:
    if already_published_id is not None:
        return _AutopublishResult(ado_id=int(already_published_id), error=None, skipped=True)
    if not output or not str(output).strip():
        return _AutopublishResult(ado_id=None, error=None, skipped=True)
    if not _looks_like_epic(output):  # reutiliza validador existente
        return _AutopublishResult(ado_id=None, error="epic_not_in_output", skipped=False)
    try:
        published = _publish_issue_to_ado(output, brief, project_name)
        # Comentarios por fase: actualmente el output es un bloque único.
        # La fase se infiere por presencia de marcadores HTML en el output.
        # Si el output tiene secciones diferenciables, postear cada una.
        # Por defecto, postear el output completo como comentario de fase "funcional"
        # si no hay marcadores de fase explícitos.
        client = _ado_client_for_ticket(project_name=project_name)
        _post_phase_comment(client, published.ado_id, "funcional", output)
        return _AutopublishResult(ado_id=published.ado_id, error=None, skipped=False)
    except Exception as exc:
        logger.error("issue publish: fallo ado err=%s", exc, exc_info=True)
        return _AutopublishResult(ado_id=None, error=str(exc), skipped=False)
```

**Nota de diseño — comentarios por fase (C2 resuelta):**
El agente `business` hoy produce UN bloque de output (la épica/issue completa). Para Issues, el pipeline es idéntico (el mismo agente corre), de modo que el output es un bloque único. **En esta versión (v2), un Issue SIEMPRE postea el output como comentario `"funcional"` en la primera ejecución; el marker `<!-- stacky:issue-phase:funcional -->` es ÚNICO y garantiza idempotencia si corre nuevamente.**

**Futura extensión (plan posterior):** Si se implementan fases separadas (funcional → técnico → implementación como 3 runs distintas), cada run llamará a `publish_issue_from_run` con su output parcial y fase específica, y `_post_phase_comment` escalará para múltiples markers. Hoy: UN marcador por Issue, idempotente. El agente `business` no cambia.

**Casos borde cubiertos por tests:**
1. `already_published_id` != None → `skipped=True`, sin llamadas ADO
2. output vacío → `skipped=True`
3. output que no es épica (narración) → `error="epic_not_in_output"`, sin llamadas ADO
4. ADO falla en `create_work_item` → `error` no vacío, `ado_id=None`
5. ADO falla en `post_comment` → WI ya creado, pero comentario no posteado; función registra warning, no falla fatal (decisión: Issue existe aunque sin comentario)
6. `comment_exists` retorna dict (ya existe) → `post_comment` no se llama (idempotencia)
7. `_persist_issue_ticket`: si ya existe el ado_id en DB, no duplica (igual que épica)

**Tests primero — `backend/tests/test_publish_issue.py`:**
```python
# Mocks: ado_client.create_work_item, post_comment, comment_exists
# (parchear el módulo origen: backend.api.tickets._ado_client_for_ticket)
# Casos: los 7 listados arriba.
# No usar full-suite; no importar tickets completo si genera side effects — usar lazy import.
```

**Comando de validación:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_publish_issue.py" -v
```

**Criterio de aceptación (binario):** todos los tests pasan, `0 failed`.

**Flag que la protege:** las funciones existen pero `publish_issue_from_run` solo es invocada por F2 (que está gated por `STACKY_ISSUE_FROM_BRIEF_ENABLED`).

**Impacto por runtime:** ninguno aún (funciones no invocadas hasta F2).

**Trabajo del operador:** ninguno.

---

### F2 — `run_brief` / `agents.py` — aceptar `work_item_type` y rutear autopublish

**Objetivo:** el endpoint `POST /api/agents/stacky/run-brief` acepta el param opcional `work_item_type` ("Epic" | "Issue", default "Epic") y al cerrar la run ruta a `autopublish_epic_from_run` o `publish_issue_from_run` según el tipo. El flag `STACKY_ISSUE_FROM_BRIEF_ENABLED` protege la nueva rama.

**Archivos exactos:**
- `backend/api/agents.py` — función `run_brief` (línea ~565); lectura del body y dispatch al cerrar
- `backend/tests/test_run_brief_work_item_type.py` — NUEVO

**Símbolos exactos a modificar en `agents.py`:**
- `run_brief` (línea ~565): leer `work_item_type = validate_brief_work_item_type(body.get("work_item_type"))` del request body; validar allowlist; si `work_item_type == "Issue"` y `STACKY_ISSUE_FROM_BRIEF_ENABLED` es False, retornar HTTP 400 con `{"error": "issue_from_brief_disabled"}`.
- La lógica de autopublicación al cerrar la run (llamada a `autopublish_epic_from_run`) debe ramificarse: si `work_item_type == "Issue"` → llamar a `publish_issue_from_run`; si `work_item_type == "Epic"` → comportamiento actual intacto.
- El `work_item_type` debe persistirse en `metadata` de la run (igual que `epic_ado_id`), para que el frontend pueda mostrar el tipo correcto.

**Pseudocódigo — fragmento de `run_brief` (C3 resuelta):**
```python
# Al inicio del handler, en la lectura del body:
work_item_type_raw = body.get("work_item_type")
try:
    work_item_type = validate_brief_work_item_type(work_item_type_raw)
except ValueError:
    return jsonify({"error": "invalid_work_item_type"}), 400

if work_item_type == "Issue" and not config.STACKY_ISSUE_FROM_BRIEF_ENABLED:
    return jsonify({"error": "issue_from_brief_disabled"}), 400

# ... resto del handler (sin cambios) ...

# Al cerrar la run (donde hoy se llama autopublish_epic_from_run):
# LECTURA DE already_published_id DIFERENCIADA POR work_item_type (C3):
if work_item_type == "Issue":
    already_published_issue_id = metadata.get("issue_ado_id")  # separado de epic_ado_id
    result = publish_issue_from_run(
        output=run_output,
        brief=brief,
        project_name=project_name,
        already_published_id=already_published_issue_id,
    )
    if result.ado_id:
        metadata["issue_ado_id"] = result.ado_id  # guardar en key separada
else:
    already_published_epic_id = metadata.get("epic_ado_id")
    result = autopublish_epic_from_run(
        output=run_output,
        brief=brief,
        project_name=project_name,
        already_published_id=already_published_epic_id,
    )
    if result.ado_id:
        metadata["epic_ado_id"] = result.ado_id

# El resto del manejo de result (needs_review) queda igual.
metadata["work_item_type"] = work_item_type
```

**Casos borde:**
- `work_item_type` ausente o `null` → default `"Epic"`, flujo actual intacto
- `work_item_type = "Issue"` con flag OFF → HTTP 400 (no llega al agente)
- `work_item_type = "Bug"` → HTTP 400 (allowlist)
- `work_item_type = "Issue"` con flag ON → ruta nueva; épica queda intacta

**Tests primero — `backend/tests/test_run_brief_work_item_type.py`:**
```python
# Casos:
# 1. body sin work_item_type → se procesa como Epic (no 400)
# 2. body con work_item_type="Epic" → se procesa como Epic
# 3. body con work_item_type="Issue" + flag OFF → HTTP 400
# 4. body con work_item_type="Issue" + flag ON → llama publish_issue_from_run (mock)
# 5. body con work_item_type="Bug" → HTTP 400
# Mocks: publish_issue_from_run, autopublish_epic_from_run, agent_runner.run_agent
```

**Comando de validación:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_run_brief_work_item_type.py" -v
```

**Criterio de aceptación (binario):** todos los tests pasan, `0 failed`.

**Flag que la protege:** `STACKY_ISSUE_FROM_BRIEF_ENABLED=false` — Issue retorna 400 aunque el frontend lo envíe.

**Impacto por runtime:** backend-side, igual para los 3 runtimes. El agente `business` no cambia; la bifurcación ocurre tras cerrar la run.

**Trabajo del operador:** opt-in: agregar `STACKY_ISSUE_FROM_BRIEF_ENABLED=true` al `.env` del deploy para activar Issues. Sin eso, todo idéntico a hoy.

---

### F3 — Frontend `EpicFromBriefModal` — selector de tipo gated por flag

**Objetivo:** el modal `EpicFromBriefModal.tsx` muestra un selector "Epic / Issue" solo si `STACKY_ISSUE_FROM_BRIEF_ENABLED` está activo (expuesto vía config endpoint). Por defecto selecciona "Epic". Envía `work_item_type` al backend. Si el flag está OFF, el modal es byte-a-byte idéntico al de hoy.

**Archivos exactos:**
- `frontend/src/components/EpicFromBriefModal.tsx` — agregar selector `workItemType` state + UI condicional
- `frontend/src/api/endpoints.ts` — verificar que `runBrief` ya acepta `work_item_type` en el body (ya tiene `model` y `effort`; agregar `work_item_type?: string`)
- `frontend/src/config.ts` (o el archivo que expone flags de feature al frontend) — exponer `STACKY_ISSUE_FROM_BRIEF_ENABLED`

**Símbolos exactos:**
- En `EpicFromBriefModal.tsx`: nuevo state `const [workItemType, setWorkItemType] = useState<"Epic" | "Issue">("Epic")`
- En el body del submit: incluir `work_item_type: workItemType`
- UI del selector: renderizar solo si `featureFlags.issueFromBriefEnabled === true` (o el nombre que use el frontend para este flag)
- Si el flag está OFF: no renderizar el selector, `workItemType` queda siempre `"Epic"`

**Pseudocódigo — fragmento de EpicFromBriefModal:**
```tsx
// State:
const [workItemType, setWorkItemType] = useState<"Epic" | "Issue">("Epic");

// En el submit handler (junto a model, effort):
const body = {
  brief,
  runtime,
  project,
  model,
  effort,
  work_item_type: workItemType,  // siempre "Epic" si el flag está OFF
};

// UI (condicional, C4 resuelta):
{featureFlags?.issueFromBriefEnabled && (
  <Select
    label="Tipo de work item"
    value={workItemType}
    onChange={(v) => setWorkItemType(v as "Epic" | "Issue")}
    options={[
      { value: "Epic", label: "Épica" },
      { value: "Issue", label: "Issue" },
    ]}
  />
)}

// IMPORTANTE (C4): Si featureFlags.issueFromBriefEnabled === false, NO renderizar el selector.
// Además, en el handler de submit, ASEGURAR que si el flag está OFF, nunca se envía "Issue":
const bodyWorkItemType = featureFlags?.issueFromBriefEnabled ? workItemType : "Epic";
const body = {
  brief,
  runtime,
  project,
  model,
  effort,
  work_item_type: bodyWorkItemType,  // Siempre "Epic" si flag OFF
};
```

**Exponer flag al frontend (C1 resuelta):**
El endpoint `GET /api/config` devuelve flags al frontend (verificar en `backend/api/global_config.py` o similar). Agregar en la respuesta una key `issueFromBriefEnabled` mapeada a `config.STACKY_ISSUE_FROM_BRIEF_ENABLED` (booleano). En el frontend (`frontend/src/config.ts`), leer `issueFromBriefEnabled` del response de `GET /api/config` y exponerlo en `featureFlags.issueFromBriefEnabled` para que EpicFromBriefModal pueda condicionar el selector de tipo.

**Validación frontend:** tsc limpio (sin errores de compilación).

**Comando de validación:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio de aceptación (binario):** `tsc --noEmit` sin errores + checklist manual mínimo:
- [ ] Con flag OFF: modal se ve idéntico a hoy, sin selector de tipo.
- [ ] Con flag ON: aparece selector "Épica / Issue", default "Épica".
- [ ] Al enviar con Issue: body incluye `work_item_type: "Issue"`.

**Flag que la protege:** `STACKY_ISSUE_FROM_BRIEF_ENABLED` (expuesto al frontend como feature flag).

**Impacto por runtime:** solo UI; los 3 runtimes usan el mismo modal.

**Trabajo del operador:** ninguno (la UI aparece sola al activar el flag).

---

### F4 — Frontend — color/badge para work item type "Issue"

**Objetivo:** en la lista de tickets/work items y en badges, el tipo "Issue" recibe un color distintivo (no el mismo que "Epic").

**Archivos exactos:**
El implementador debe localizar el componente que colorea badges por `work_item_type`. Estrategia de búsqueda:
```bash
grep -rn "work_item_type\|workItemType\|Epic\|badge" \
  "Stacky Agents/frontend/src/components" \
  --include="*.tsx" -l
```
El componente que ya mapea `"Epic"` → color X es el target. Agregar el caso `"Issue"` con color naranja (`#F59E0B` o equivalente Tailwind `amber-500`) para diferenciarlo visualmente de Epic (típicamente violeta/púrpura) y de Bug/Task.

**Pseudocódigo — en el mapa de colores existente:**
```typescript
// Ejemplo (adaptar al patrón real del componente):
const WORK_ITEM_TYPE_COLORS: Record<string, string> = {
  "Epic":       "#7C3AED",  // violeta (ya existe)
  "User Story": "#2563EB",  // ya existe
  "Task":       "#059669",  // ya existe
  "Bug":        "#DC2626",  // ya existe
  "Issue":      "#F59E0B",  // NUEVO — ámbar/naranja
};
```

**Validación frontend:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio de aceptación (binario):** tsc limpio + checklist manual:
- [ ] Un ticket con `work_item_type="Issue"` muestra badge en color ámbar.
- [ ] Tickets Epic, Bug, Task no cambian de color.

**Flag que la protege:** ninguno necesario (el color es display-only, no altera lógica).

**Impacto por runtime:** solo UI; sin impacto en runtimes de agente.

**Trabajo del operador:** ninguno.

---

### F5 — Frontend `ClientProfileEditor` — sección "Catálogo de procesos" (Req1)

**Objetivo:** agregar una sección "Catálogo de procesos" en `ClientProfileEditor.tsx` que renderice y permita editar el array `process_catalog` del `client_profile`. Sin endpoints nuevos; reutiliza el PUT existente. Backward-compatible: si `process_catalog` es `undefined` o vacío, muestra lista vacía con botón "Agregar".

**Archivos exactos:**
- `frontend/src/components/ClientProfileEditor.tsx` — agregar sección 10 "Catálogo de procesos"

**Estructura de datos del catálogo (C5 resuelta):**
```typescript
// Tipo del item (inferido de config.json líneas 67-88):
interface ProcessCatalogItem {
  name: string;      // ej: "Mul2Bane"
  kind: string;      // ej: "entry" — VALIDADO contra allowlist {"entry", "processing", "output"}
  purpose: string;   // ej: "Convierte lotes crudos al formato IN_"
}

// ALLOWLIST en backend/api/client_profile.py (para PUT validation):
ALLOWED_PROCESS_KINDS = {"entry", "processing", "output"}
// En PUT /api/projects/<name>/client-profile, validar: 
// for item in body.get("process_catalog", []):
//     if item.get("kind") not in ALLOWED_PROCESS_KINDS:
//         return jsonify({"error": "invalid_process_kind", "value": item.get("kind")}), 400
```

**Patrón de implementación (seguir el patrón del editor existente):**
El `ClientProfileEditor.tsx` ya tiene helpers `getPath` / `setPath` para mutar el profile de forma inmutable, y helpers de sección como `StringArrayField` y `KeyValueField`. La sección de `process_catalog` debe implementarse como una lista editable de filas (name / kind / purpose), con botones "Agregar fila" y "Eliminar fila", enganchada a `setPath(["process_catalog"], updatedArray)`.

**Pseudocódigo — estructura de la sección:**
```tsx
// Dentro de <ClientProfileEditor>, tras la última sección existente:

<Section title="Catálogo de procesos" description="Procesos batch inyectados como contexto a los agentes.">
  {(getPath(["process_catalog"]) as ProcessCatalogItem[] || []).map((item, idx) => (
    <div key={idx} className="flex gap-2 items-start mb-2">
      <input
        placeholder="Nombre"
        value={item.name}
        onChange={(e) => {
          const arr = [...(getPath(["process_catalog"]) as ProcessCatalogItem[] || [])];
          arr[idx] = { ...arr[idx], name: e.target.value };
          setPath(["process_catalog"], arr);
        }}
      />
      <input placeholder="Tipo" value={item.kind} onChange={...} />
      <input placeholder="Propósito" value={item.purpose} onChange={...} />
      <button onClick={() => {
        const arr = [...(getPath(["process_catalog"]) as ProcessCatalogItem[] || [])];
        arr.splice(idx, 1);
        setPath(["process_catalog"], arr);
      }}>✕</button>
    </div>
  ))}
  <button onClick={() => {
    const arr = [...(getPath(["process_catalog"]) as ProcessCatalogItem[] || [])];
    arr.push({ name: "", kind: "", purpose: "" });
    setPath(["process_catalog"], arr);
  }}>+ Agregar proceso</button>
</Section>
```

**Integración con el guardado:** el botón "Guardar" del editor ya llama al PUT de `client-profile` con el profile completo (incluyendo `process_catalog`). No se requiere lógica adicional.

**Backward-compatibility:** `getPath(["process_catalog"]) ?? []` — si la key no existe, muestra lista vacía y el operador puede agregar desde cero.

**Validación frontend:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio de aceptación (binario):** tsc limpio + checklist manual:
- [ ] SettingsPage → tab "client-profile" → sección "Catálogo de procesos" visible.
- [ ] Con `process_catalog` existente en el profile: las filas se cargan (name/kind/purpose).
- [ ] Con `process_catalog` ausente: sección vacía con botón "Agregar proceso".
- [ ] Agregar/editar/eliminar fila + "Guardar": el PUT devuelve 200 y la sección recarga con los datos guardados.
- [ ] El resto del editor (otras secciones) no cambia.

**Flag que la protege:** ninguno (siempre visible; leer el profile es zero-config).

**Impacto por runtime:** solo UI.

**Trabajo del operador:** ninguno para Req1 — el catálogo ya existe en el config; ahora es visible. Editar es opcional.

---

### F6 [ADICIÓN ARQUITECTO] — Endpoint de validación de catálogo (opcional, future-proof)

**Objetivo:** agregar `POST /api/projects/<name>/client-profile/validate-catalog` para que el frontend valide el catálogo ANTES de enviar PUT, mejorando UX y alineando con patrón client-side + server-side. No es bloqueante; puede postergar a plan futuro.

**Archivos:**
- `backend/api/client_profile.py` — agregar ruta nueva

**Pseudocódigo:**
```python
@bp.route("/projects/<project_name>/client-profile/validate-catalog", methods=["POST"])
def validate_catalog_endpoint(project_name: str):
    """Valida un catálogo de procesos sin persistir.
    Request body: {process_catalog: [...]} 
    Response: {valid: bool, errors: [string]}"""
    data = request.get_json() or {}
    catalog = data.get("process_catalog", [])
    errors = []
    for idx, item in enumerate(catalog):
        if not item.get("name"):
            errors.append(f"Item {idx}: name requerido")
        if item.get("kind") not in ALLOWED_PROCESS_KINDS:
            errors.append(f"Item {idx}: kind inválido '{item.get('kind')}'")
        if not item.get("purpose"):
            errors.append(f"Item {idx}: purpose requerido")
    return jsonify({"valid": len(errors) == 0, "errors": errors}), 200
```

**Frontend (opcional):** antes de cliquear "Guardar" en ClientProfileEditor, invocar este endpoint. Si errors != [], mostrar toast/banner rojo. Sino, enviar PUT. Requiere formulario con `onBlur` o botón "Validar ahora".

**Criterio:** no es obligatorio para v2; implementar en F5 si hay tiempo, sino postergar.

---

## 5. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| `_publish_issue_to_ado` rompe el path de épica por import / efecto lateral | Baja | Funciones nuevas en zona isolada; el path de épica no las importa; tests de épica no cambian |
| `run_brief` falla al parsear `work_item_type` si el campo no existe | Baja | `validate_brief_work_item_type(None)` devuelve `"Epic"` — backward-compatible |
| ADO no admite `work_item_type="Issue"` en el proyecto Pacífico | Media | En F1 mockear ADO; verificar en entorno real antes de desplegar; si ADO rechaza, `publish_issue_from_run` devuelve error y la run queda `needs_review` (no crash) |
| `ClientProfileEditor.tsx` tiene >770 líneas; agregar la sección puede introducir error de tipado | Baja | tsc --noEmit como gate; no refactorizar el archivo, solo agregar la sección nueva |
| Comentarios acumulativos (F1) crecen sin límite en un Issue | Baja-Media | Idempotencia por marker: cada fase solo se postea una vez; el operador puede abrir el Issue en ADO para ver el historial |
| Flag OFF mal configurado en el deploy congelado | Baja | Default `False` hardcodeado en `config.py`; requiere SET explícito para activar Issues |

---

## 6. Fuera de Scope

- Encadenar el agente `business` en fases separadas (funcional → técnico → implementación como 3 runs distintas): el agente hoy produce un bloque único; si en el futuro se encadenan fases, `_post_phase_comment` ya soporta múltiples marcadores.
- Soporte de tipo "Bug" u otros tipos ADO distintos de Epic e Issue.
- Dashboard de Issues separado del de Épicas.
- Filtros/búsqueda en el catálogo de procesos (Req1 es solo lista editable).
- Validación de unicidad de `name` en el catálogo de procesos (UX futura).
- RBAC por tipo de work item.
- Comentarios de revisión humana sobre Issues desde la UI de Stacky (el operador usa ADO directamente para eso).

---

## 7. Glosario

| Término | Significado en este plan |
|---|---|
| **Issue** | Work item ADO tipo "Issue"; pipeline idéntico a Epic pero destino = comentarios en WI único, sin tickets hijos |
| **Epic** | Work item ADO tipo "Epic"; flujo actual intacto |
| **process_catalog** | Array de `{name, kind, purpose}` dentro del `client_profile`; inyectado al agente como diccionario de procesos |
| **fase** | Bloque de output del agente (funcional / técnico / implementación); en la implementación actual es un bloque único |
| **marker** | Comentario HTML `<!-- stacky:issue-phase:X -->` que garantiza idempotencia al postear fases |
| **autopublish** | Publicación automática en ADO al cerrar la run (sin checkbox, sin intervención del operador) |

---

## 8. Orden de Implementación

```
F0 → F1 → F2 → F3 → F4 → F5 → [F6 opcional, futuro]
```

F0–F2 son backend puro y deben completarse antes de tocar el frontend.
F3 depende de F2 (el endpoint ya acepta `work_item_type`).
F4 es independiente de F3 (puede hacerse en paralelo con F3).
F5 (Req1) es completamente independiente; puede implementarse en cualquier momento, incluso antes de F0 si se prefiere.
**[ADICIÓN ARQUITECTO] F6 (opcional):** endpoint POST `/api/projects/<name>/client-profile/validate-catalog` para validación frontend anticipada. Posterga a plan futuro si no es crítico hoy.

---

## 9. DoD (Definition of Done)

- [ ] F0: `backend/tests/test_issue_from_brief_contract.py` — 0 failed
- [ ] F1: `backend/tests/test_publish_issue.py` — 0 failed; tests en `backend/tests/test_publish_epic.py` (path de épica) no regresionan
- [ ] F2: `backend/tests/test_run_brief_work_item_type.py` — 0 failed; tests en `backend/tests/test_run_brief_efforts.py` y `backend/tests/test_llm_router_opus_flag.py` pasan sin cambios (flag OFF = comportamiento idéntico a v1)
- [ ] F3: `tsc --noEmit` limpio en `frontend/`; flag OFF = modal idéntico al actual; flag ON = selector visible; body envía `work_item_type` correcto
- [ ] F4: `tsc --noEmit` limpio; un Issue con `work_item_type="Issue"` muestra badge en color ámbar (#F59E0B); Epic/Bug/Task no cambian
- [ ] F5: `tsc --noEmit` limpio; sección "Catálogo de procesos" visible en SettingsPage → ClientProfileEditor; agregar/editar/eliminar filas funciona; PUT retorna 200 y datos persisten
- [ ] Validación de `process_catalog[*].kind` contra allowlist {"entry", "processing", "output"} en backend PUT client-profile — rechaza 400 si kind inválido
- [ ] Deploy: `harness_defaults.env` actualizado con `STACKY_ISSUE_FROM_BRIEF_ENABLED=false` (default seguro)
