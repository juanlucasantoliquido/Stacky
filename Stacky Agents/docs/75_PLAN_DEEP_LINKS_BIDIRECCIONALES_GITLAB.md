# Plan 75 — Deep links bidireccionales GitLab

> **Estado:** PROPUESTO v1.
> **Pre-requisito:** Plan 70 (puerto `TrackerProvider` con `item_url`) — COMPLETO. Indirecto: este plan extiende para GitLab los deep links que el Plan 70 ya estandarizó para ADO vía `provider.item_url(item_id)`.
> **Roadmap:** Sexto eslabón del bloque GitLab-Main 70-76 (desacople → pipeline infer agnóstico → trigger CI → creador pipelines → migrador ADO→GitLab → **deep links** → eval codebase-memory-mcp).
> **Versión doc:** v1 (2026-06-27). Reemplaza al boceto v0.

> **CHANGELOG boceto v0 → v1:**
> - Supuesto crítico del boceto (`project_path` URL-encoded canónico) **RESUELTO**: `_project_path()` YA existe en `gitlab_client.py:98` y URL-encodea `grp/sub/proj` → `grp%2Fsub%2Fproj`. El plan lo reusa vía el puerto; NO recalcula en la UI.
> - Hallazgo de auditoría: `gitlab_provider.item_url` (`:164-167`) NO URL-encodea `self._project` (gap real para sub-groups). F1 lo corrige.
> - Hallazgo de auditoría: `frontend/src/components/StructuredOutput.tsx:83` hardcodea `dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/...`. F4 lo reemplaza por el helper provider-agnóstico.
> - Patrón existente confirmado: el frontend NO compone URLs ADO; renderiza strings que el backend ya arma. Este plan extiende ese patrón a GitLab (composiciones PURAS en backend, render en frontend).
> - Fallback Free para épicas documentado y operacionalizado (F3).

---

## 1. Objetivo y KPI

Componer **URLs profundas (deep links) GitLab** deterministas — issue, MR, pipeline, commit, epic — consumiéndolas desde la UI de Stacky en cualquier card/relación de un ítem, reutilizando el patrón de deep links ADO ya existente (`work_item_url` ADO / `item_url` puerto) y la composición nativa del provider GitLab.

**KPI global (DoD):** en la UI de un proyecto con `issue_tracker.type=gitlab` (y `STACKY_GITLAB_ENABLED=true`), toda card/relación de un ítem (épica, issue, task, ejecución con pipeline, MR) muestra el deep link clickeable al recurso correcto en GitLab, construido **sin lógica de URL en el frontend** (el frontend sólo renderiza strings que el backend le pasa por el puerto). Las composiciones son funciones PURAS testeadas con input→URL exacta.

---

## 2. Por qué ahora / gap que cierra

- Hoy los deep links en la UI son ADO-only: `StructuredOutput.tsx:83` hardcodea `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`; el backend expone `work_item_url` (`ado_client.py:344`) y `item_url` puerto (`ado_provider.py:69`).
- El provider GitLab ya compone `item_url` para issues (`gitlab_provider.py:164-167`) y devuelve `web_url` armado por el API para pipelines (`gitlab_provider.py:449`), PERO:
  - `item_url` **no URL-encodea** `self._project` (gap para sub-groups como `rs/pacifico/strategist`).
  - No hay compositores para MRs, commits ni épicas nativas.
  - El frontend no renderiza links GitLab porque el backend no los provee de forma provider-agnóstica fuera de `item_url`.
- Sin deep links, el operador copia-pega IDs entre Stacky y GitLab: fricción alta, rompe el flujo centauro.
- Es un **Boost** (poco código, mucho valor de UX), pero requiere corrección del gap de encoding para no romper sub-groups.

**Anclajes verificados con evidencia de hoy:**
- `_project_path()` URL-encodea: `services/gitlab_client.py:98-103` → `'grp%2Fsub%2Fproj'`.
- `_base_url` ya está rstrip-`/`: `services/gitlab_client.py:56`.
- `item_url` issue GitLab: `services/gitlab_provider.py:164-167` → `{base}/{proj}/-/issues/{iid}` (sin encodear → gap F1).
- `web_url` pipeline viene del API: `services/gitlab_provider.py:449`.
- `_epics_native` flag (Premium/Free): `services/gitlab_provider.py:36`.
- Marker idempotencia: `gitlab_provider.py:262`, `ado_provider.py:95`.

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): este plan NO toca el runtime del agente ni los prompts; el cambio vive en servicios/UI. Los 3 runtimes siguen operativos.
- **Cero trabajo extra al operador**: deep links GitLab son **default ON** cuando el proyecto ya es gitlab (no requieren opt-in extra); el feature completo está gateado por `STACKY_GITLAB_DEEP_LINKS_ENABLED` default **OFF** sólo para permitir kill-switch, `env_only=False`. Con flag OFF, el backend no compone URLs GitLab y el frontend no renderiza el componente (caen los links ADO si el proyecto fuera ADO).
- **Human-in-the-loop innegociable**: deep links son sólo clicks externos (abren tab nueva con `rel="noopener noreferrer"`); no modifican recursos.
- **Mono-operador sin auth**: el `project_path` se lee del `client_profile`/config del proyecto; sin RBAC, sin login.
- **No degradar / backward-compatible**: los deep links ADO existentes se preservan; `_project_path()` se reusa (no se recalcula); `StructuredOutput.tsx:83` se reemplaza por un helper que delega al backend.
- **TDD + funciones puras + ratchet + no falsos verdes**: cada compositor es una función PURA testada con input→URL exacta (sin I/O, sin red).
- **Seguridad anti-injection:** todo input externo (`project_path`, `iid`, `sha`) se URL-encodea antes de componer; tests de boundary (path traversal, caracteres raros).
- **Prohibido lo vago:** todo call site, archivo y símbolo citado con `archivo:línea`.

---

## 4. Fases

### F0 — Inventario (entregable: tabla entidad × compositor de URL × origen del project_path)

**Tabla F0 — Entidades a linkear (5 filas):**

| # | Entidad GitLab | URL canónica | Compositora PURA (F1) | Origen `project_path` | Notas |
|---|----------------|--------------|------------------------|-----------------------|-------|
| 1 | `issue` | `https://gitlab.example.com/{project_path}/-/issues/{iid}` | `compose_issue_url(base_url, project_path, iid)` | `_project_path()` (`gitlab_client.py:98`) | Reemplaza `item_url` actual (`gitlab_provider.py:164`) que no encodea |
| 2 | `epic` (Premium) | `https://gitlab.example.com/groups/{group}/-/epics/{iid}` | `compose_epic_url(base_url, group, iid)` | `STACKY_GITLAB_GROUP` (config) | Fallback Free → `compose_issue_url` del issue degradado |
| 3 | `merge_request` | `https://gitlab.example.com/{project_path}/-/merge_requests/{iid}` | `compose_mr_url(base_url, project_path, iid)` | `_project_path()` | Análogo a issue |
| 4 | `pipeline` | `web_url` del API (`gitlab_provider.py:449`) | `pipeline_web_url(pipeline_dict)` (selector) | N/A (lo da el API) | Preferir `web_url` del API; fallback a composición |
| 5 | `commit` | `https://gitlab.example.com/{project_path}/-/commit/{sha}` | `compose_commit_url(base_url, project_path, sha)` | `_project_path()` | `sha` URL-safe pero se valida longitud |

**Criterio binario F0:** la tabla está completa (5 filas) y cada fila cita el origen del `project_path`. **Cumplido en este doc.**

**Trabajo del operador F0:** ninguno.

---

### F1 — Compositoras PURAS de URL (backend)

**Objetivo:** 5 funciones PURAS en un módulo nuevo, sin I/O, que componen URLs deterministas URL-encoding todos los inputs. Corrigen el gap de `gitlab_provider.item_url` (que no encodea).

**Trabajo:**

```python
# backend/services/gitlab_deep_links.py (NUEVO)
import urllib.parse

def _norm_base(base_url: str) -> str:
    """rstrip '/' del base_url (defensivo)."""
    return (base_url or "").rstrip("/")

def _enc(value: str) -> str:
    """URL-encode un segmento de path de forma segura."""
    return urllib.parse.quote(str(value), safe="")

def compose_issue_url(base_url: str, project_path: str, iid: str) -> str:
    return f"{_norm_base(base_url)}/{_enc(project_path)}/-/issues/{_enc(iid)}"

def compose_mr_url(base_url: str, project_path: str, iid: str) -> str:
    return f"{_norm_base(base_url)}/{_enc(project_path)}/-/merge_requests/{_enc(iid)}"

def compose_commit_url(base_url: str, project_path: str, sha: str) -> str:
    return f"{_norm_base(base_url)}/{_enc(project_path)}/-/commit/{_enc(sha)}"

def compose_epic_url(base_url: str, group: str, iid: str) -> str:
    return f"{_norm_base(base_url)}/groups/{_enc(group)}/-/epics/{_enc(iid)}"

def pipeline_web_url(pipeline: dict) -> str | None:
    """Selector puro: retorna pipeline['web_url'] si viene del API, sino None."""
    return (pipeline or {}).get("web_url") or None
```

**Archivos exactos F1:**
- `backend/services/gitlab_deep_links.py` (NUEVO) — las 5 funciones + helpers `_norm_base`, `_enc`.

**Tests F1 (TDD primero):**
- Archivo: `backend/tests/test_plan75_deep_links_compose.py`.
- Casos:
  1. `compose_issue_url("https://gl.example.com/", "rs/pacifico/strat", "42")` → `"https://gl.example.com/rs%2Fpacifico%2Fstrat/-/issues/42"`.
  2. `compose_mr_url` con mismo input → análogo con `/merge_requests/42`.
  3. `compose_commit_url("https://gl.example.com", "rs/pacifico/strat", "abc123def")` → `/rs%2Fpacifico%2Fstrat/-/commit/abc123def`.
  4. `compose_epic_url("https://gl.example.com", "my-group", "7")` → `https://gl.example.com/groups/my-group/-/epics/7`.
  5. `_norm_base` rstrip: base con trailing `/` vs sin → misma URL final.
  6. **Boundary anti-injection:** `project_path="../../../etc"` → encodeado como `%2E%2E%2F%2E%2E%2E%2Fetc` (no escapa del path).
  7. `pipeline_web_url({"web_url": "https://gl/x"})` → `"https://gl/x"`; `pipeline_web_url({})` → `None`.
  8. **Pureza:** 2 llamadas con mismo input → mismo output (no I/O).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan75_deep_links_compose.py -q`.

**Criterio binario F1:** los 8 casos pasan; URL exacta afirmada string-compare; boundary anti-injection verde.

**Impacto por runtime:** ninguno (capa de servicios).

**Flag F1:** ninguna (módulo inerte hasta F2).

**Trabajo del operador F1:** ninguno.

---

### F2 — Wiring de las compositoras en `gitlab_provider`

**Objetivo:** que `gitlab_provider.item_url` use `compose_issue_url` (corrige gap de encoding) y añadir métodos públicos `epic_url`, `mr_url`, `commit_url` al provider GitLab (NO al puerto, para no romper ADO). El puerto `TrackerProvider` queda intacto (sólo exige `item_url`).

**Trabajo:**

```python
# services/gitlab_provider.py — patches puntuales
# item_url reescrito a:
def item_url(self, item_id: str) -> str:
    from services.gitlab_deep_links import compose_issue_url
    return compose_issue_url(self._client._base_url, self._client._project_path(), item_id)

# Métodos NUEVOS (no del puerto, sólo del provider GitLab):
def mr_url(self, mr_iid: str) -> str:
    from services.gitlab_deep_links import compose_mr_url
    return compose_mr_url(self._client._base_url, self._client._project_path(), mr_iid)

def commit_url(self, sha: str) -> str:
    from services.gitlab_deep_links import compose_commit_url
    return compose_commit_url(self._client._base_url, self._client._project_path(), sha)

def epic_url(self, epic_iid: str) -> str:
    from services.gitlab_deep_links import compose_epic_url
    if not self._group:
        # Free tier: no hay épicas nativas; devolver URL del issue degradado si se conoce.
        raise TrackerConfigError("GitLab Free: épicas no nativas; usar fallback Free (F3)")
    return compose_epic_url(self._client._base_url, self._group, epic_iid)
```

**Archivos exactos F2:**
- `services/gitlab_provider.py` (edits puntuales en `item_url` `:164-167` + 3 métodos nuevos después de `item_url`).
- NO toca `services/tracker_provider.py` (el puerto no cambia).
- NO toca `services/ado_provider.py` (ADO sigue usando su `item_url`).

**Tests F2 (TDD primero):**
- Archivo: `backend/tests/test_plan75_gitlab_provider_urls.py`.
- Casos (con `GitLabTrackerProvider` instanciado con config mock):
  1. `item_url("42")` con `project="rs/pacifico/strat"` → URL encodeada (usa `compose_issue_url`).
  2. `mr_url("7")` → URL MR correcta encodeada.
  3. `commit_url("abc123")` → URL commit correcta.
  4. `epic_url("3")` con `STACKY_GITLAB_GROUP="grp"` → URL epic correcta.
  5. `epic_url("3")` sin `_group` → levanta `TrackerConfigError` (Free fallback en F3).
  6. **No regresión ADO:** `AdoTrackerProvider.item_url("42")` sigue devolviendo la URL ADO intacta (`assert_equal` con valor conocido).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan75_gitlab_provider_urls.py -q`.

**Criterio binario F2:** los 6 casos pasan; no regresión ADO (caso 6).

**Impacto por runtime:** ninguno.

**Flag F2:** ninguna.

**Trabajo del operador F2:** ninguno.

---

### F3 — Fallback Free para épicas + helper provider-agnóstico

**Objetivo:** resolver el caso "GitLab Free no tiene épicas". Cuando un ítem viene de migrar una épica ADO y el destino es Free, el deep link apunta al issue degradado (label `type::epic`), no a una epic inexistente.

**Trabajo:**

```python
# services/gitlab_deep_links.py (extiende F1)
def resolve_epic_deep_link(
    *, dest_provider, epic_strategy: str, gitlab_iid: str, fallback_issue_iid: str | None
) -> str:
    """Estrategia de fallback Free para deep links de épicas.
    - epic_strategy == 'premium_native' y provider tiene _group → epic_url(group, iid).
    - epic_strategy == 'free_degrade' o sin _group → compose_issue_url(project_path, fallback_issue_iid).
    - Sin fallback_issue_iid → compose_search_url(base_url, project_path, 'label:type::epic').
    Nunca escribe; sólo compone."""
```

**Archivos exactos F3:**
- `backend/services/gitlab_deep_links.py` — añade `resolve_epic_deep_link` + `compose_search_url(base_url, project_path, query)` helper.

**Tests F3 (TDD primero):**
- Archivo: `backend/tests/test_plan75_deep_links_epic_fallback.py`.
- Casos:
  1. `premium_native` + provider con `_group` → URL epic nativa.
  2. `free_degrade` + `fallback_issue_iid` → URL issue del issue degradado.
  3. `free_degrade` sin `fallback_issue_iid` → URL search con `label:type::epic`.
  4. `auto` detecta `_epics_native=False` → cae a `free_degrade`.
  5. `compose_search_url` produce `.../issues?search=...&label_name=type::epic` encodeado.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan75_deep_links_epic_fallback.py -q`.

**Criterio binario F3:** los 5 casos pasan; ninguna función escribe.

**Impacto por runtime:** ninguno.

**Flag F3:** ninguna.

**Trabajo del operador F3:** ninguno.

---

### F4 — UI: componente `TrackerDeepLink` provider-agnóstico + reemplazo de hardcoded ADO

**Objetivo:** un componente React reutilizable que reciba una URL (string) + label y la renderice como link externo (`target="_blank"`, `rel="noopener noreferrer"`), reemplazando el hardcodeo de `StructuredOutput.tsx:83`.

**Trabajo:**

```tsx
// frontend/src/components/TrackerDeepLink.tsx (NUEVO)
type Props = { url: string | null | undefined; label: React.ReactNode; className?: string };
export function TrackerDeepLink({ url, label, className }: Props) {
  if (!url) return <span className={className}>{label}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={className}>
      {label}
    </a>
  );
}
```

**Reemplazo del hardcodeo:** `StructuredOutput.tsx:83` (construcción `https://dev.azure.com/UbimiaPacifico/...`) se elimina; el componente consume la URL que el backend ya pasa en el payload (vía `item_url` del puerto). Si el proyecto es gitlab, el backend pasa la URL GitLab; si ADO, la ADO.

**Sites de UI a migrar a `TrackerDeepLink` (buscá el patrón existente):**
- `frontend/src/components/StructuredOutput.tsx:83` — reemplazar construcción hardcoded por `TrackerDeepLink url={payload.task_url}`.
- Cards de épica/issue/task donde aparezca `task_url`/`epic_url`/`issue_url` (revisar `frontend/src/components/` y `frontend/src/pages/` buscando `_links.html.href` o `_workitems`).
- Drawer de ejecución donde aparezca `pipeline.web_url` (si existe).

**Archivos exactos F4:**
- `frontend/src/components/TrackerDeepLink.tsx` (NUEVO).
- `frontend/src/components/StructuredOutput.tsx` (eliminar línea 83 hardcode, usar `TrackerDeepLink`).
- Otros sites confirmados por grep (mismo commit).

**Tests F4 (TDD primero, componentes):**
- Archivo: `frontend/src/components/__tests__/TrackerDeepLink.test.tsx` (NUEVO) o test de lógica en `TrackerDeepLink.logic.ts` si vitest no está.
- Casos:
  1. `url == null` → renderiza `<span>` sin `<a>`.
  2. `url == "https://gl/x/-/issues/1"` → renderiza `<a href=... target="_blank" rel="noopener noreferrer">`.
  3. `url` vacío → `<span>`.
  4. `label` se renderiza dentro del link.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/components/__tests__/TrackerDeepLink.test.tsx` (si vitest); sino `npx tsc --noEmit`.

**Criterio binario F4:** los 4 casos pasan; `tsc` 0 errores; `StructuredOutput.tsx:83` ya no contiene `dev.azure.com` literal.

**Impacto por runtime:** ninguno (UI).

**Trabajo del operador F4:** ninguno.

---

### F5 — Composición bidireccional (épica ↔ MRs/pipelines relacionados; pipeline ↔ issue que lo disparó)

**Objetivo:** desde una épica, coleccionar links a sus MRs/pipelines relacionados; desde un pipeline, link al issue que lo disparó (si está en el payload). Reusa las compositoras F1.

**Trabajo:** helpers PUROS de agrupación en backend (no en UI).

```python
# services/gitlab_deep_links.py (extiende)
def epic_related_links(
    *, dest_provider, epic_iid: str, child_issues: list[dict], mrs: list[dict], pipelines: list[dict]
) -> dict:
    """Compone URLs para los recursos relacionados a una épica.
    Retorna {issue_urls: [...], mr_urls: [...], pipeline_urls: [...]}.
    No escribe; sólo compone a partir de los IDs que el caller ya recolectó."""

def pipeline_trigger_issue_link(pipeline: dict, *, dest_provider) -> str | None:
    """Si el pipeline tiene variables/refs que apuntan a un issue (ej. branch 'issue-42'),
    intenta componer el link al issue. Heurística determinista documentada."""
```

**Archivos exactos F5:**
- `backend/services/gitlab_deep_links.py` — añade `epic_related_links`, `pipeline_trigger_issue_link`.

**Tests F5 (TDD primero):**
- Archivo: `backend/tests/test_plan75_deep_links_bidirectional.py`.
- Casos:
  1. `epic_related_links` con 2 child issues + 1 MR + 1 pipeline → 3 listas con URLs correctas.
  2. `pipeline_trigger_issue_link` con `ref="issue-42"` → URL issue 42 (heurística documentada).
  3. `pipeline_trigger_issue_link` con `ref="main"` → `None` (no disparado por issue).
  4. Inputs vacíos → listas vacías (no errores).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan75_deep_links_bidirectional.py -q`.

**Criterio binario F5:** los 4 casos pasan; funciones puras.

**Impacto por runtime:** ninguno.

**Trabajo del operador F5:** ninguno.

---

### F6 — Wiring del flag + ratchet + integración UI final

**Trabajo:**
- `backend/config.py` — `STACKY_GITLAB_DEEP_LINKS_ENABLED: bool = False` default OFF, `env_only=False`.
- `backend/harness_defaults.env` — `STACKY_GITLAB_DEEP_LINKS_ENABLED=false`.
- `frontend/src/components/HarnessFlagsPanel.tsx` — toggle en categoría "GitLab / Deep Links".
- El backend, cuando compone URLs para el frontend, chequea el flag: si OFF y proyecto gitlab, devuelve `null` en los campos URL (el frontend cae a `<span>`).
- Registrar TODOS los archivos `test_plan75_*.py` en el ratchet del Plan 49.

**Archivos exactos F6:**
- `backend/config.py`, `backend/harness_defaults.env`, `frontend/src/components/HarnessFlagsPanel.tsx`.
- `tests/conformance/test_harness_ratchet.py` (o el artefacto ratchet vigente) — añadir los 5 archivos `test_plan75_*`.

**Tests F6:**
- Archivo: `backend/tests/test_plan75_deep_links_wiring.py`.
- Casos:
  1. Flag OFF + proyecto gitlab → endpoint que devuelve URLs retorna `null` en el campo URL.
  2. Flag ON + proyecto gitlab → endpoint devuelve URL GitLab compuesta.
  3. `harness_defaults.env` contiene la línea `STACKY_GITLAB_DEEP_LINKS_ENABLED=false`.
  4. Ratchet verde con los 5 archivos nuevos registrados.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan75_deep_links_wiring.py tests/conformance/test_harness_ratchet.py -q`.
- Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` (0 errores).

**Criterio binario F6:** los 4 casos pasan; tsc 0 errores; ratchet verde.

**Trabajo del operador F6:** ninguno (default OFF es kill-switch; los links se activan prendiendo el flag, que vive en UI).

---

## 5. Riesgos y mitigaciones

1. **URLs rotas en self-hosted con subpath.** Mitigación: F1 prefiere `web_url` del API cuando existe (caso pipeline); para issues/MRs/commits compone con `_base_url` + `_project_path()` que ya maneja el base rstrip-`/`. No se recorta a mano.
2. **Link a épica en GitLab Free.** Mitigación: F3 `resolve_epic_deep_link` detecta tier y provee fallback (issue degradado o search por label).
3. **Injection por `project_path` malicioso.** Mitigación: `_enc()` URL-encodea todos los inputs; F1 caso 6 (boundary anti-injection) es el gate de significancia.
4. **No regresión ADO.** Mitigación: F2 caso 6 afirma URL ADO intacta; `ado_provider.item_url` no se toca.
5. **3 runtimes.** Mitigación: el plan NO toca prompts ni runtime; los 3 runtimes siguen operativos.
6. **Falsos verdes.** Mitigación: F1 tests son string-compare exacto (no "contiene"); F4 caso 1/3 afirman que `null`/vacío no renderiza `<a>`.
7. **`StructuredOutput.tsx:83` hardcodeo residual.** Mitigación: F4 elimina la línea literal; grep post-F4 confirma `dev.azure.com` no aparece más en `StructuredOutput.tsx`.

---

## 6. Fuera de scope

- **NO** embeber el contenido del recurso en Stacky (sólo linkeamos).
- **NO** notificaciones push al recurso externo.
- **NO** links a MR diffs o comentarios puntuales (se agrega después si hay demanda).
- **NO** modificar el puerto `TrackerProvider` (`item_url` ya existe; los métodos `mr_url`/`commit_url`/`epic_url` son del provider GitLab, no del puerto).
- **NO** auth/RBAC (mono-operador, sin login).
- **NO** cambiar `ado_provider` ni los deep links ADO existentes.

---

## 7. Glosario

- **Deep link:** URL profunda a un recurso específico (issue/MR/pipeline/commit/epic) en GitLab o ADO.
- **`project_path`:** segmento URL-encoded `namespace/project` que identifica un proyecto GitLab. Generado por `_project_path()` (`services/gitlab_client.py:98`).
- **`_base_url`:** base del GitLab self-hosted/SaaS (`services/gitlab_client.py:56`), ya rstrip-`/`.
- **`item_url(item_id)`:** método del puerto (`tracker_provider.py:63`) que devuelve la URL profunda de un ítem.
- **`web_url` pipeline:** URL armada por el API GitLab, devuelta en `fetch_pipelines` (`gitlab_provider.py:449`).
- **Fallback Free:** degradación de épicas a issues + label `type::epic` cuando el destino es GitLab Free.
- **`TrackerDeepLink`:** componente React nuevo (F4) que renderiza un link externo con `target="_blank" rel="noopener noreferrer"`.
- **`STACKY_GITLAB_DEEP_LINKS_ENABLED`:** flag kill-switch (default OFF, editable por UI) que gatea la composición de URLs GitLab en el backend.
- **Ratchet:** mecanismo del Plan 49 que obliga a registrar todo test nuevo en `HARNESS_TEST_FILES`.

---

## 8. Orden de implementación

1. **F0** — Inventario (cumplido en este doc, 5 filas).
2. **F1** — Compositoras PURAS `gitlab_deep_links.py` (5 funciones).
3. **F2** — Wiring en `gitlab_provider` (fix `item_url` encoding + 3 métodos nuevos) — **sin tocar el puerto**.
4. **F3** — Fallback Free épicas + `resolve_epic_deep_link`.
5. **F4** — UI `TrackerDeepLink` + reemplazo de `StructuredOutput.tsx:83` hardcode.
6. **F5** — Composición bidireccional (épica ↔ relacionados; pipeline ↔ issue trigger).
7. **F6** — Flag + harness_defaults.env + HarnessFlagsPanel + ratchet.

Cada fase es auto-contenida y se puede implementar/commitear de forma independiente.

> **Dependencia Plan 70 (indirecta):** el Plan 70 estandarizó `item_url` en el puerto; este plan extiende el provider GitLab sin tocar el puerto. Si el Plan 70 aún introdujo `_provider_for_ticket` (F2 del 70), los sitios de UI consumen URLs vía el payload del backend (que ya viene provider-agnóstico); este plan NO depende de que 70 haya migrado todos los consumers, sólo de que `item_url` exista en el puerto (ya existe, `tracker_provider.py:63`). `[a verificar tras implementar Plan 70]` los sites exactos de UI donde aparecen `task_url`/`epic_url` (pueden moverse si 70 reestructura tickets.py). Los contratos de compositoras, marker, flags y fases están **fijados con evidencia de hoy**.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Tabla F0 completa y verificada (5 filas, cada fila cita origen del `project_path`). — **Cumplido en este doc.**
- [ ] **(b)** 5 compositoras PURAS en `gitlab_deep_links.py` con tests string-compare exactos (F1 casos 1-8).
- [ ] **(c)** `gitlab_provider.item_url` corrige encoding usando `compose_issue_url` (F2 caso 1); no regresión ADO (F2 caso 6).
- [ ] **(d)** Fallback Free operacional (F3 casos 1-5).
- [ ] **(e)** `StructuredOutput.tsx:83` ya no contiene `dev.azure.com` literal; usa `TrackerDeepLink` (F4).
- [ ] **(f)** Composición bidireccional (F5 casos 1-4) verde.
- [ ] **(g)** Flag `STACKY_GITLAB_DEEP_LINKS_ENABLED` default OFF, en UI; con flag ON, proyecto gitlab muestra deep links.
- [ ] **(h)** Ratchet verde con los 5 archivos `test_plan75_*` registrados.
- [ ] **(i)** `tsc` 0 errores.
- [ ] **(j)** Los 3 runtimes (Codex, Claude Code, GitHub Copilot Pro) operativos sin cambios.

---

## 10. Notas de implementación (para el modelo menor que ejecute esto)

- **Venv del repo:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`. El venv es py3.13 (ver memoria `stacky-backend-dev-test-env`); correr tests por archivo.
- **Patrón mock (TDD):** los tests de compositoras son string-compare exacto (no mock de red). Los tests de provider (F2) mockean `_client._base_url`/`_project_path()` con valores fijos.
- **Cada commit deja el sistema verde y backward-compatible.**
- **`_project_path()` YA URL-encodea** (`gitlab_client.py:98`); no reimplementarlo en `gitlab_deep_links.py` — las compositoras toman `project_path` ya resuelto y lo re-encodean (defensivo, idempotente).
- **No tocar el puerto `TrackerProvider`.** Los métodos `mr_url`/`commit_url`/`epic_url` son del provider GitLab, no del puerto. ADO no los necesita.
- **Anti-injection:** todo input externo se URL-encodea con `_enc()` antes de componer. F1 caso 6 es el gate de significancia.
- **Frontend:** el frontend NO compone URLs; renderiza strings que el backend pasa. `TrackerDeepLink` es un thin wrapper sobre `<a target="_blank" rel="noopener noreferrer">`.
- **Si una fase revela un GAP no listado en F0**, detener y actualizar este doc antes de seguir.
