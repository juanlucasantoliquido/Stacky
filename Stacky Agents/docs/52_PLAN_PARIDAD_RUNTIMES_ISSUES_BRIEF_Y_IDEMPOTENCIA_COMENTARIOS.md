# Plan 52 — Paridad de runtimes en autopublish (Epic/Issue) e idempotencia robusta de comentarios

> Estado: IMPLEMENTADO 2026-06-19.
>
> Evidencia: F0 guard 400 `autopublish_requires_claude_cli` en `api/agents.py` (tras la validación de Issue, antes de leer `model`). F1 `services/ado_client.py`: `fetch_all_comments` (pagina por continuationToken con tope `_COMMENT_PAGE_CAP`=40 + short-circuit en marker) + `comment_exists` reescrito (escaneo total, gateado por `STACKY_COMMENT_FULL_SCAN_ENABLED` default ON, rollback legacy a 1 página); `fetch_comments` intacto. F3 tests de persistencia real del Issue. F4 `api/tickets.py`: `_compute_epic_observability` (reusa helpers de la épica) cableado en `publish_issue_from_run` → `_AutopublishResult` con grounding_warnings/epic_summary; comentario obsoleto en `claude_code_cli_runner.py:1218` actualizado. Flag en `harness_flags.py` + `.env.example`. Tests verdes (por archivo, .venv): test_run_brief_autopublish_parity.py 4, test_ado_comment_idempotency.py 4, test_persist_issue_ticket.py 5, test_issue_observability.py 4; no-regresión test_epic_autopublish_backend.py + test_issue_from_brief_contract.py 10, test_harness_flags.py 23.
>
> Estado original: PROPUESTO (no implementado). Autor: StackyArchitectaUltraEficientCode. Fecha: 2026-06-19.
> Origen: revisión adversarial de la generación de Issues desde brief (Plan 45, IMPLEMENTADO).
> Implementable por modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) SIN inferir nada.

---

## 1. Título, objetivo y KPI/impacto

**Objetivo (1 frase):** Cerrar la **falla silenciosa de paridad de runtimes** del autopublish (Epic/Issue) convirtiéndola en un **error explícito y temprano** (HTTP 400) cuando el runtime no puede autopublicar, y **endurecer la idempotencia** del comentario de fase del Issue para que NUNCA se duplique aunque el work item tenga más de 50 comentarios.

**KPI / impacto medible:**
- **K1** — 0 runs de `run_brief` con `work_item_type ∈ {Epic, Issue}` que terminen `completed`/`needs_review` SIN crear el work item por usar un runtime que no autopublica. Hoy ese caso es invisible; tras el plan devuelve 400 antes de gastar tokens.
- **K2** — 0 comentarios de fase duplicados en Issues con >50 comentarios. Hoy `comment_exists` solo mira los 50 más recientes (`ado_client.py:764`, `fetch_comments` default `top=20` en `ado_client.py:399`).
- **K3** — Observabilidad del path Issue al nivel del path Epic: `epic_summary` y `grounding_warnings` presentes en `metadata` también para Issues (hoy ausentes a propósito, `claude_code_cli_runner.py:1219`).

**Costo de tokens del plan:** marginal. No agrega generación LLM nueva. F0 es una guarda barata; F1 es paginación HTTP; F4 es propagación de campos ya calculados.

---

## 2. Por qué ahora / gap que cierra

Tres hallazgos verificados en código real (rutas archivo:línea reales):

**(G1) ALTO — Falla silenciosa de paridad.** El despachador `_maybe_autopublish_epic` (que bifurca Epic vs Issue) está definido como closure SOLO dentro del finalizador del runner de Claude CLI: `Stacky Agents/backend/services/claude_code_cli_runner.py:1163`, invocado únicamente en las líneas `:1233` (rama runaway) y `:1380` (rama normal). **No existe ningún call-site equivalente en los finalizadores de Codex CLI ni de GitHub Copilot.** Confirmado por memoria del proyecto [[stacky-autopublish-only-claude-cli]]. Consecuencia: si el operador lanza `run_brief` con `runtime="codex_cli"` o `"github_copilot"` y `work_item_type ∈ {Epic, Issue}`, el run corre, gasta tokens, termina `completed`/`needs_review`, y **el work item nunca se crea en ADO, sin error visible**. Falsa sensación de éxito.

**(G2) MEDIO — Idempotencia frágil del comentario de fase.** `_post_phase_comment` (`Stacky Agents/backend/api/tickets.py:6029`) consulta `client.comment_exists(ado_id, marker)` (`Stacky Agents/backend/services/ado_client.py:764`) antes de postear. `comment_exists` llama `fetch_comments(ado_id, top=top)` con `top` por defecto **50** (firma `comment_exists(..., top: int = 50)`), y `fetch_comments` (`ado_client.py:399`) pide a la API `?$top={top}&order=desc` — es decir, **solo los 50 comentarios más recientes**. Si un Issue acumuló >50 comentarios, el marker idempotente viejo puede caer fuera de la ventana → `comment_exists` devuelve `None` → **comentario duplicado**. La API REST de comments de ADO es paginada vía `continuationToken`; hoy no se sigue.

**(G3) BAJO — Pérdida de observabilidad en path Issue.** En `claude_code_cli_runner.py:1218-1223` el sellado de `grounding_warnings` y `epic_summary` aplica a ambos paths porque lee del `_AutopublishResult` devuelto, PERO `publish_issue_from_run` (`tickets.py:6053`) construye su `_AutopublishResult` **sin** `grounding_warnings` ni `epic_summary` (devuelve `_AutopublishResult(ado_id=..., error=None, skipped=False)` en `:6107`, usando los defaults `grounding_warnings=[]`, `epic_summary=None` de la NamedTuple en `tickets.py:5782-5795`). Resultado: los Issues no llevan warnings de grounding ni resumen → menos triage en el Panel de Salud Operativa (Plan 46).

Además, gaps de test (G4, BAJO): `_persist_issue_ticket` (`tickets.py:5961`) siempre se mockea en los tests existentes → no hay test que fije persistencia REAL con `work_item_type="Issue"` ni idempotencia por `ado_id`; y no hay test de HTML estructuralmente roto que pase `_looks_like_epic` pero genere cuerpo malformado.

---

## 3. Principios y guardarraíles (codificados en el plan)

- **P1 — 3 runtimes con paridad o degradación controlada explícita.** Codex CLI, Claude Code CLI, GitHub Copilot Pro. En este plan, la "degradación controlada" del autopublish para Codex/Copilot ES un **error 400 claro** (no cableado nuevo en cada runtime).
- **P2 — Cero trabajo extra para el operador.** No se agregan pasos manuales. El flag de Issue desde brief sigue default OFF. El nuevo comportamiento (400 temprano) reemplaza una falla silenciosa por un error legible: es estrictamente mejor para el operador, sin acción nueva de su parte.
- **P3 — Human-in-the-loop intacto.** No se cambia ninguna decisión del operador. Mono-operador, sin auth real: no se introduce RBAC. [[stacky-no-auth-substrate]]
- **P4 — Backward-compatible.** `runtime="claude_code_cli"` (default actual del selector, Plan 37) sigue funcionando idéntico. Solo cambia el comportamiento de combos que HOY ya están rotos en silencio.
- **P5 — TDD: tests PRIMERO en cada fase.** Comando exacto con el python del .venv del repo (ver [[stacky-backend-dev-test-env]]): se corre **por archivo**, nunca la suite completa.
- **P6 — No degradar performance/seguridad/estabilidad/DX.** Reusar flags del arnés, telemetría y memoria existentes. La paginación de comentarios acota el costo (tope duro de páginas).

### Decisión de diseño G1: Opción A (rechazo temprano 400) — recomendada y adoptada

Se evaluaron dos opciones:

- **Opción A (ADOPTADA): rechazo explícito y temprano en `run_brief`.** Antes de lanzar el agente (junto al chequeo de flag en `agents.py:593`), si `work_item_type ∈ {Epic, Issue}` y `runtime ≠ claude_code_cli`, devolver `400 {"ok": false, "error": "autopublish_requires_claude_cli"}`. El operador recibe un error legible ANTES de gastar tokens.
- **Opción B (FUERA DE SCOPE): cablear `publish_epic`/`publish_issue` en los finalizadores de Codex y Copilot.** Rechazada porque: (1) mayor superficie de código en 2 runtimes más; (2) el contrato de salida que exige `autopublish_epic_from_run`/`publish_issue_from_run` es **HTML-solo** validado por `_looks_like_epic` (`tickets.py:6077`), y NO hay garantía de que los runtimes Codex/Copilot produzcan ese HTML-solo (su contrato de salida no lo asegura) → cablearlos probablemente caería en `epic_not_in_output` igual, sumando complejidad sin valor; (3) el valor real que se busca es "el operador deja de tener falsa sensación de éxito", y eso lo entrega A con una fracción del costo.

**Conclusión:** A entrega el mismo valor de negocio (no más falsos éxitos) con menor superficie y riesgo. B queda documentada como alternativa futura **solo si** en el futuro se garantiza por contrato que Codex/Copilot emiten el HTML-solo requerido.

---

## 4. Fases F0..F4

> Cada fase es autocontenida y verificable sola. Tests PRIMERO. Cada comando de test usa el python del .venv del repo. Asumir CWD = `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`.
>
> **Python del .venv (comando base, reusado en todas las fases):**
> ```
> .venv\Scripts\python.exe -m pytest <archivo_de_test> -q
> ```
> Si `.venv` no existiera en el entorno del implementador, usar el intérprete del proyecto; NO instalar pins rotos (pywin32==306 falla en py3.13, ver [[stacky-backend-dev-test-env]]). Correr SIEMPRE por archivo, nunca `pytest` a secas (la suite completa tiene contaminación conocida).

---

### F0 — Rechazo temprano 400 cuando autopublish requiere Claude CLI (cierra G1, ALTO)

**Objetivo (1 frase):** Que `run_brief` rechace con 400 legible el combo `work_item_type ∈ {Epic, Issue}` + `runtime ≠ claude_code_cli`, antes de lanzar el agente.

**Valor:** Elimina la falla silenciosa: el operador ve el error en vez de un run que "anduvo" pero no creó nada.

#### Archivos exactos

- Implementación: `Stacky Agents/backend/api/agents.py` (función `run_brief`, dentro del bloque de validación en `:588-594`).
- Test: `Stacky Agents/backend/tests/test_run_brief_autopublish_parity.py` (**archivo nuevo**).

#### Test PRIMERO

Crear `Stacky Agents/backend/tests/test_run_brief_autopublish_parity.py` con estos casos (usar el patrón de cliente Flask de tests existentes de `agents.py`; si no hay fixture compartida, instanciar `create_app()` y `app.test_client()`):

Casos exactos:
1. `test_run_brief_epic_codex_returns_400` — POST a la ruta de `run_brief` con body `{"brief": "x", "runtime": "codex_cli", "work_item_type": "Epic"}` → status `400`, JSON `{"ok": false, "error": "autopublish_requires_claude_cli"}`.
2. `test_run_brief_issue_copilot_returns_400` — con flag `STACKY_ISSUE_FROM_BRIEF_ENABLED=true` (monkeypatch `config.STACKY_ISSUE_FROM_BRIEF_ENABLED = True`), body `{"brief":"x","runtime":"github_copilot","work_item_type":"Issue"}` → `400`, error `"autopublish_requires_claude_cli"`.
3. `test_run_brief_epic_claude_cli_not_rejected_by_parity_guard` — body `{"brief":"x","runtime":"claude_code_cli","work_item_type":"Epic", ...}` → NO devuelve `400` con error `"autopublish_requires_claude_cli"` (puede fallar por otras validaciones posteriores como `vscode_agent_filename` faltante; el test debe afirmar SOLO que el error NO es `autopublish_requires_claude_cli`). Para aislar: mockear `run_agent`/lo que lanza el agente, o afirmar `resp.get_json().get("error") != "autopublish_requires_claude_cli"`.
4. `test_run_brief_task_codex_not_rejected` — body `{"brief":"x","runtime":"codex_cli","work_item_type":"Task"}` (o sin `work_item_type`, que normaliza a "Epic" → ESTE caso sí cae en el guard; usar explícitamente un tipo que NO sea Epic/Issue para verificar que el guard NO se dispara). NOTA: `Task` debe estar en `ALLOWED_BRIEF_WORK_ITEM_TYPES`; si no lo está, este caso se omite y se documenta en el test con un comentario. Afirma que NO se devuelve `autopublish_requires_claude_cli`.

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_run_brief_autopublish_parity.py -q
```
Antes de implementar: confirmar que los casos 1 y 2 FALLAN (porque hoy no existe el guard).

#### Implementación (diff ilustrativo)

En `agents.py`, **inmediatamente después** del bloque que valida el flag de Issue (después de `agents.py:594`, antes de la lectura de `model` en `:595`), insertar:

```python
# Plan 52 F0 — Paridad de runtimes: el autopublish (Epic/Issue) SOLO lo ejecuta
# el finalizador de claude_code_cli_runner (_maybe_autopublish_epic). Codex CLI y
# GitHub Copilot NO autopublican → degradación controlada: rechazo explícito y
# temprano (antes de gastar tokens) para no dar falsa sensación de éxito.
_AUTOPUBLISH_RUNTIME = "claude_code_cli"
if work_item_type in ("Epic", "Issue") and runtime_raw != _AUTOPUBLISH_RUNTIME:
    return jsonify({
        "ok": False,
        "error": "autopublish_requires_claude_cli",
        "detail": (
            f"work_item_type={work_item_type!r} requiere runtime "
            f"{_AUTOPUBLISH_RUNTIME!r}; recibido {runtime_raw!r}."
        ),
    }), 400
```

Casos borde:
- `work_item_type` ya está normalizado por `validate_brief_work_item_type` (`tickets.py:2878`): None/"" → "Epic". Por lo tanto un brief sin `work_item_type` y runtime no-Claude **también** se rechaza (correcto: hoy también falla en silencio para Epic).
- `runtime_raw` se lee en `agents.py:581` con default `"github_copilot"`. Si el operador no manda runtime y pide Epic → se rechaza con 400. Esto es deseable: el default histórico del selector es Claude CLI (Plan 37) pero el default del endpoint sigue siendo copilot; el guard fuerza coherencia.

#### Flag que lo protege + default seguro

No requiere flag nuevo. El comportamiento es una **validación de entrada** (como `invalid_work_item_type` y `issue_from_brief_disabled` ya existentes). Backward-compatible: el path feliz (Claude CLI + Epic) no cambia.

#### Impacto por runtime + fallback

| Runtime | Antes | Después (fallback explícito) |
|---|---|---|
| `claude_code_cli` | autopublica | igual (sin cambio) |
| `codex_cli` | run "ok" sin WI (silencioso) | 400 `autopublish_requires_claude_cli` (degradación controlada) |
| `github_copilot` | run "ok" sin WI (silencioso) | 400 `autopublish_requires_claude_cli` (degradación controlada) |

#### Criterio de aceptación BINARIO

`test_run_brief_autopublish_parity.py` pasa al 100% con el comando de arriba (4 casos verdes, o 3 si Task no está en la allowlist y se omite el caso 4 documentadamente).

#### Trabajo del operador: ninguno.

---

### F1 — Idempotencia robusta de comentarios: paginar TODOS los comentarios (cierra G2, MEDIO)

**Objetivo (1 frase):** Que `comment_exists` recorra TODAS las páginas de comentarios del work item (no solo las 50 más recientes), para que el marker idempotente viejo siempre se encuentre.

**Valor:** Cero comentarios de fase duplicados en Issues longevos (>50 comentarios).

#### Contrato exacto de la API REST de comments de Azure DevOps

Endpoint GET (el mismo que ya usa `fetch_comments`, `ado_client.py:405-408`):
```
GET {org}/{project}/_apis/wit/workItems/{id}/comments?api-version=7.1-preview.3&$top={N}&order=asc
```
Respuesta JSON relevante (campos reales de ADO):
```json
{
  "totalCount": 137,
  "count": 50,
  "comments": [ { "id": 1, "text": "...", "createdBy": {...}, "createdDate": "...", "revisedBy": {...}, "revisedDate": "..." }, ... ],
  "continuationToken": "eyJ..."   // presente SOLO si hay más páginas; ausente/null en la última
}
```
Paginación: para traer la siguiente página, repetir el GET agregando `&continuationToken={token}`. Cuando la respuesta NO trae `continuationToken` (o viene `null`/vacío), se llegó a la última página. (Algunos despliegues exponen `nextLink` en `_links`; el contrato canónico de la API de comments es `continuationToken`, que es el que se sigue aquí.)

#### Archivos exactos

- Implementación: `Stacky Agents/backend/services/ado_client.py` — agregar método nuevo `fetch_all_comments` y modificar `comment_exists` (`:764`). NO modificar `fetch_comments` (`:399`) para no alterar su contrato actual usado por otros callers (diagnóstico, digest).
- Test: `Stacky Agents/backend/tests/test_ado_comment_idempotency.py` (**archivo nuevo**).

#### Test PRIMERO

Crear `Stacky Agents/backend/tests/test_ado_comment_idempotency.py`. Estrategia: instanciar el cliente ADO real pero mockear su método interno de request HTTP (`_request`) para simular paginación. Identificar el método de bajo nivel usando el patrón de los tests existentes de `ado_client` (buscar en `tests/` los que ya mockean `_request`). Casos:

1. `test_comment_exists_finds_marker_on_second_page` — mock de `_request` que devuelve:
   - 1ra llamada: `{"comments": [{"text": "ruido", ...} x50], "continuationToken": "tok1"}` (sin marker)
   - 2da llamada (con `continuationToken=tok1`): `{"comments": [{"text": "<!-- stacky:issue-phase:funcional --> cuerpo"}], }` (con marker, SIN continuationToken)
   - `comment_exists(ado_id=1, marker="<!-- stacky:issue-phase:funcional -->")` → devuelve un dict no-None (el comentario que contiene el marker).
2. `test_comment_exists_returns_none_when_marker_absent_across_all_pages` — 2 páginas, ninguna con el marker → `None`.
3. `test_comment_exists_stops_at_page_cap` — mock que SIEMPRE devuelve `continuationToken` (paginación infinita simulada); afirmar que `_request` se llamó **a lo sumo `_COMMENT_PAGE_CAP` veces** (tope duro de seguridad, ver implementación) y devuelve `None` sin colgarse.
4. `test_comment_exists_empty_marker_returns_none_without_http` — `comment_exists(1, "")` → `None` y `_request` NO se llamó (guard de marker vacío ya existe en `:771`).

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_ado_comment_idempotency.py -q
```
Confirmar que los casos 1 y 3 FALLAN antes de implementar (hoy solo mira una página de 50).

#### Implementación (diff ilustrativo)

En `ado_client.py`, agregar constante de módulo (cerca de `_API_VERSION`):
```python
# Plan 52 F1 — tope duro de páginas para la búsqueda idempotente de comentarios.
# Evita loops si ADO devolviera continuationToken indefinidamente.
_COMMENT_PAGE_CAP = 40          # 40 páginas * 200 = 8000 comentarios máximos inspeccionados
_COMMENT_PAGE_SIZE = 200        # $top por página (200 es el máximo práctico de la API)
```

Agregar método nuevo:
```python
def fetch_all_comments(self, ado_id: int, marker: str | None = None) -> list[dict]:
    """Recorre TODAS las páginas de comentarios del work item (Plan 52 F1).

    Sigue `continuationToken` de la API de comments de ADO hasta agotar páginas
    o alcanzar `_COMMENT_PAGE_CAP`. Si se pasa `marker`, hace short-circuit:
    devuelve apenas encuentra una página que contenga el marker (no sigue paginando).
    Tolerante a fallos: ante cualquier AdoApiError devuelve lo acumulado hasta ahí.
    Devuelve dicts con la MISMA forma que fetch_comments: {author, date, text}.
    """
    out: list[dict] = []
    token: str | None = None
    for _page in range(_COMMENT_PAGE_CAP):
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}/comments"
            f"?api-version=7.1-preview.3&$top={_COMMENT_PAGE_SIZE}&order=asc"
        )
        if token:
            url += f"&continuationToken={urllib.parse.quote(str(token))}"
        try:
            data = self._request("GET", url)
        except AdoApiError as e:
            logger.warning("fetch_all_comments(%s) falló en página %s: %s", ado_id, _page, e)
            return out
        for c in (data.get("comments") or []):
            text_html = (c.get("text") or "").strip()
            if not text_html:
                continue
            revised_by = c.get("revisedBy") or c.get("createdBy") or {}
            author = revised_by.get("displayName") or revised_by.get("uniqueName") or "?"
            date = (c.get("revisedDate") or c.get("createdDate") or "")[:10]
            entry = {"author": author, "date": date, "text": text_html}
            out.append(entry)
            if marker and marker in text_html:
                return out  # short-circuit: ya basta para idempotencia
        token = data.get("continuationToken")
        if not token:
            break
    return out
```

Modificar `comment_exists` (`:764`) para usar el recorrido completo con short-circuit:
```python
def comment_exists(self, ado_id: int, marker: str, top: int = 50) -> dict | None:
    """Busca un comentario que contenga el marcador Stacky en TODAS las páginas.

    Plan 52 F1: antes solo miraba los `top` más recientes (riesgo de duplicado en
    work items con >50 comentarios). Ahora recorre todas las páginas vía
    fetch_all_comments con short-circuit en el marker. `top` se conserva en la
    firma por compatibilidad pero ya no limita la búsqueda.
    """
    if not marker:
        return None
    comments = self.fetch_all_comments(ado_id, marker=marker)
    for c in comments:
        if marker in (c.get("text") or ""):
            return c
    return None
```

Casos borde:
- `marker` vacío → `None` sin HTTP (guard existente preservado).
- ADO sin soporte de la API preview → `fetch_all_comments` devuelve `[]` → `comment_exists` devuelve `None`. **Importante:** esto significa "no encontrado" → `_post_phase_comment` POSTEARÁ. Es el mismo comportamiento conservador que hoy (degradación: preferir postear a perder el artefacto). Documentar en el docstring.
- Paginación infinita defectuosa de ADO → cortada por `_COMMENT_PAGE_CAP`.

#### Flag que lo protege + default seguro

No requiere flag nuevo: es un endurecimiento de un método interno, sin cambio de contrato observable salvo "ahora encuentra el marker viejo". Si se quiere reversibilidad operativa, gatear bajo un flag de arnés `STACKY_COMMENT_FULL_SCAN_ENABLED` (env_only, default **true**) que, si `false`, restaura el comportamiento de una sola página. **Decisión: agregar el flag con default true** (defensa en profundidad + rollback barato sin redeploy de código). Registrar en `services/harness_flags.py` siguiendo el patrón de los flags existentes (tipo bool).

Diff de `comment_exists` con flag:
```python
if not marker:
    return None
from services import harness_flags
if harness_flags.is_enabled("STACKY_COMMENT_FULL_SCAN_ENABLED", default=True):
    comments = self.fetch_all_comments(ado_id, marker=marker)
else:
    comments = self.fetch_comments(ado_id, top=top)   # comportamiento legacy (1 página)
for c in comments:
    if marker in (c.get("text") or ""):
        return c
return None
```
(Usar la API real de `harness_flags`; confirmar el nombre exacto de la función de lectura — `is_enabled` o equivalente — leyendo `services/harness_flags.py` antes de codear. Si el patrón de flags requiere alta en `FLAG_REGISTRY`, registrarlo allí como bool default true.)

#### Impacto por runtime + fallback

Independiente del runtime: `comment_exists` solo se invoca desde `_post_phase_comment` en el path Issue, que (tras F0) solo corre bajo `claude_code_cli`. Fallback: con flag off → comportamiento legacy de 1 página.

#### Criterio de aceptación BINARIO

`test_ado_comment_idempotency.py` pasa 100% (4 casos verdes) con el comando de arriba.

#### Trabajo del operador: ninguno.

---

### F2 — (incluida en F0) Test de paridad

> **Nota:** El hallazgo (3) del brief ("test que fije el comportamiento de paridad") ya está cubierto por el archivo de test de F0 (`test_run_brief_autopublish_parity.py`). No se crea fase separada para evitar duplicación. Esta sección existe solo para trazar el hallazgo → F0.

---

### F3 — Tests de respaldo: persistencia real del Issue e HTML roto (cierra G4, BAJO)

**Objetivo (1 frase):** Fijar con tests la persistencia REAL del ticket Issue (`work_item_type="Issue"` + idempotencia por `ado_id`) y el manejo de HTML que pasa `_looks_like_epic` pero está estructuralmente malformado.

**Valor:** Blinda contra regresiones en `_persist_issue_ticket` (hoy siempre mockeado) y documenta el comportamiento ante HTML degenerado.

#### Archivos exactos

- Solo tests (NO cambia producción salvo que un test revele un bug — en ese caso, fix mínimo en `tickets.py`):
  - `Stacky Agents/backend/tests/test_persist_issue_ticket.py` (**archivo nuevo**).
- Implementación bajo prueba: `_persist_issue_ticket` (`tickets.py:5961`), `_publish_issue_to_ado` (`tickets.py:5991`), `_looks_like_epic` (referenciado en `tickets.py:6077`), `_extract_epic_html`.

#### Test PRIMERO

Patrón de DB en tests: usar el patrón conocido del repo — `db` importado a nivel de módulo, lazy imports parcheados en el módulo de origen, sesión real sobre SQLite de test (ver [[stacky-plan28-lifecycle]] sobre el patrón de mock). Leer un test existente que ya ejercite `Ticket` + `session_scope` para copiar la fixture exacta antes de escribir.

Casos en `test_persist_issue_ticket.py`:
1. `test_persist_issue_ticket_creates_with_work_item_type_issue` — llamar `_persist_issue_ticket(ado_id=9001, title="T", description_html="<h1>x</h1>", url="http://ado/9001", project_name="Pacifico")` con DB real; luego `session.query(Ticket).filter(Ticket.ado_id==9001).first()` → existe y `ticket.work_item_type == "Issue"`.
2. `test_persist_issue_ticket_idempotent_by_ado_id` — llamar DOS veces con el mismo `ado_id=9002` (segunda con título distinto) → solo existe 1 fila para `ado_id=9002`, y NO lanza.
3. `test_publish_issue_to_ado_uses_extracted_html` — mockear `_ado_client_for_ticket` para devolver un fake client cuyo `create_work_item` capture el `description` recibido; pasar `description_html` con narración + HTML embebido; afirmar que el `description` pasado a `create_work_item` es el HTML extraído (`_extract_epic_html`), no la narración cruda.
4. `test_looks_like_epic_rejects_malformed_html` — alimentar a `publish_issue_from_run` un `output` que NO pasa `_looks_like_epic` (narración pura) → `_AutopublishResult.error` contiene `"epic_not_in_output"`, `ado_id is None`.
5. `test_publish_issue_structurally_broken_html` — `output` que SÍ pasa `_looks_like_epic` (tiene `<h1>`/`<h2>` y palabras clave) pero con cuerpo malformado (tags sin cerrar). Afirmar el comportamiento ACTUAL observado: el Issue se crea igual (el contrato no valida well-formedness más allá de `_looks_like_epic`). **Si** el test revela que esto rompe ADO, documentarlo como hallazgo y abrir nota para un futuro plan (NO arreglar aquí salvo crash en el código Python). El test fija el contrato actual: "HTML que pasa `_looks_like_epic` se publica tal cual".

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_persist_issue_ticket.py -q
```

#### Implementación

Ninguna en producción por defecto (fase de tests). Excepción: si el caso 2 revelara que `_persist_issue_ticket` NO es idempotente (hoy filtra por `ado_id` en `:5971` y solo agrega si `existing is None`, `:5973` → ya parece idempotente), el test simplemente confirma el comportamiento existente. Si el caso 5 produce una excepción no manejada en Python (no en ADO), envolver con manejo defensivo mínimo en `_publish_issue_to_ado`.

#### Flag / runtime / fallback

N/A (tests). El path Issue real solo corre bajo `claude_code_cli` (post F0).

#### Criterio de aceptación BINARIO

`test_persist_issue_ticket.py` pasa 100% (5 casos verdes).

#### Trabajo del operador: ninguno.

---

### F4 — Propagar `epic_summary` y `grounding_warnings` al path Issue (cierra G3, BAJO)

**Objetivo (1 frase):** Que `publish_issue_from_run` devuelva `grounding_warnings` y `epic_summary` poblados (cuando aplique), para que el finalizador los selle en `metadata` también para Issues.

**Valor:** Paridad de observabilidad Issue ≈ Epic en el Panel de Salud Operativa (Plan 46) y telemetría de grounding (Plan 44).

#### Archivos exactos

- Implementación: `Stacky Agents/backend/api/tickets.py` — función `publish_issue_from_run` (`:6053`).
- Test: `Stacky Agents/backend/tests/test_issue_observability.py` (**archivo nuevo**).
- (Verificar, sin cambiar) `claude_code_cli_runner.py:1218-1226` ya sella `grounding_warnings`/`epic_summary`/`recovery_method` desde el `_AutopublishResult` para AMBOS paths — no requiere cambio. El comentario en `:1219-1223` ("solo aplica al path de épica; el Issue no produce summary") quedará **obsoleto** y debe **actualizarse** en F4 (ver abajo).

#### Test PRIMERO

Crear `Stacky Agents/backend/tests/test_issue_observability.py`. Mockear `_publish_issue_to_ado` (para no tocar ADO) y `_post_phase_comment`. Casos:

1. `test_publish_issue_from_run_emits_grounding_warnings` — `output` con HTML que pasa `_looks_like_epic` pero dispara warnings de grounding (HTML sin las secciones esperadas; reusar el mismo generador de warnings que la épica: `_epic_grounding_warnings`, `tickets.py:5529`). Afirmar que el `_AutopublishResult` devuelto tiene `grounding_warnings` no vacío.
2. `test_publish_issue_from_run_emits_epic_summary_when_enabled` — con el flag de epic_summary ON (el mismo que controla la épica; confirmar nombre leyendo el bloque `tickets.py:5915-5926`), afirmar `_AutopublishResult.epic_summary is not None`.
3. `test_publish_issue_from_run_no_summary_when_disabled` — flag OFF → `epic_summary is None` (sin romper).
4. `test_publish_issue_from_run_skipped_keeps_defaults` — `already_published_id=123` → `skipped=True`, sin calcular warnings (short-circuit en `:6070-6071`), sin tocar ADO.

Comando:
```
.venv\Scripts\python.exe -m pytest tests\test_issue_observability.py -q
```
Confirmar que 1 y 2 FALLAN antes (hoy `publish_issue_from_run` no puebla esos campos).

#### Implementación (diff ilustrativo)

En `publish_issue_from_run` (`:6087-6107`), tras publicar el Issue y postear el comentario, computar warnings y summary REUSANDO las helpers de la épica (NO duplicar lógica):

```python
# Plan 52 F4 — paridad de observabilidad con la épica: calcular grounding_warnings
# y epic_summary REUSANDO las helpers existentes, para sellarlos en metadata.
_grounding_enabled = _grounding_warnings_enabled()      # misma helper que usa autopublish_epic_from_run
grounding_warnings: list[str] = (
    _epic_grounding_warnings(clean_html) if _grounding_enabled else []
)
if _catalog_grounding_warnings_enabled():
    catalog = _load_process_catalog(project_name)       # misma fuente que la épica
    grounding_warnings = grounding_warnings + _catalog_grounding_warnings(clean_html, catalog)

epic_summary: dict | None = None
if _epic_summary_enabled():                              # misma helper/flag que la épica
    epic_summary = build_epic_summary(
        html=clean_html,
        warnings=grounding_warnings,
        # mismos kwargs que el call-site de la épica en tickets.py:5922-5926
    )

return _AutopublishResult(
    ado_id=published.ado_id,
    error=None,
    skipped=False,
    grounding_warnings=grounding_warnings,
    epic_summary=epic_summary,
)
```

**IMPORTANTE — antes de codear:** leer el bloque `tickets.py:5877-5937` (cuerpo de `autopublish_epic_from_run`) para copiar EXACTAMENTE los nombres reales de las helpers/flags (`_grounding_warnings_enabled`, `_epic_summary_enabled`, `_load_process_catalog`, kwargs de `build_epic_summary`). Usar los nombres reales, no los ilustrativos de arriba. NO duplicar las funciones; importarlas/llamarlas (ya están en el mismo módulo `tickets.py`).

Actualizar el comentario obsoleto en `claude_code_cli_runner.py:1218-1223`: cambiar "(solo aplica al path de épica; el Issue no produce summary)" por "(Plan 52 F4: el path Issue también produce grounding_warnings y epic_summary)".

Casos borde:
- `already_published_id` no-None → return temprano en `:6070-6071` con defaults (`grounding_warnings=[]`, `epic_summary=None`). Correcto: idempotente, no recomputa.
- Flags OFF → `grounding_warnings=[]`, `epic_summary=None` (igual que hoy). Sin regresión.

#### Flag que lo protege + default seguro

Reusa los flags YA existentes de grounding/summary de la épica (sin flags nuevos). Si ambos están OFF, el comportamiento es idéntico al actual (campos vacíos).

#### Impacto por runtime + fallback

Solo afecta el path Issue, que post-F0 corre exclusivamente bajo `claude_code_cli`. El finalizador (`:1220-1223`) ya sabe sellar los campos. Fallback: campos vacíos si flags OFF.

#### Criterio de aceptación BINARIO

`test_issue_observability.py` pasa 100% (4 casos verdes).

#### Trabajo del operador: ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| R1 | F0 rompe un flujo legítimo donde alguien lanzaba Epic con Copilot esperando algo | Baja | Hoy ese flujo NO crea el WI (falla silenciosa); el 400 es estrictamente mejor. El path feliz (Claude CLI) no cambia. Tests F0 caso 3 lo fijan. |
| R2 | F1 dispara muchas llamadas HTTP en Issues con miles de comentarios | Media | Short-circuit en el marker + `_COMMENT_PAGE_CAP=40`. En la práctica el marker está entre los primeros comentarios (se postea al crear el Issue). Flag de rollback `STACKY_COMMENT_FULL_SCAN_ENABLED`. |
| R3 | F1 cambia el contrato de `comment_exists` y rompe otros callers | Baja | `comment_exists` solo lo usa `_post_phase_comment` (verificar con grep antes de implementar). Firma preservada (`top` sigue en la firma). `fetch_comments` NO se toca. |
| R4 | F4 duplica lógica de grounding entre épica e Issue | Media | Prohibido duplicar: REUSAR las helpers existentes de `tickets.py` (mismo módulo). El test exige que los warnings salgan de `_epic_grounding_warnings`. |
| R5 | Contaminación de la suite completa enmascara verdes/rojos | Media | Correr SIEMPRE por archivo con el .venv (P5). [[stacky-backend-test-suite-pollution]] |
| R6 | ADO no expone `continuationToken` en algún despliegue | Baja | `fetch_all_comments` corta al no recibir token (1 página) → degradación a comportamiento legacy. Sin crash. |

---

## 6. Fuera de scope

- **Opción B (cablear autopublish en Codex/Copilot).** Documentada en §3 como alternativa futura; NO se implementa. Solo se consideraría si en el futuro se garantiza por contrato que esos runtimes emiten HTML-solo.
- **Cambiar el default del endpoint `run_brief` de `github_copilot` a `claude_code_cli`.** El selector del frontend ya defaultea a Claude CLI (Plan 37); el default del endpoint es defensa separada y cambiarlo excede este plan.
- **UI nueva** para el error `autopublish_requires_claude_cli`. El frontend ya renderiza errores de `run_brief` genéricamente; no se agrega componente.
- **Idempotencia del work item Issue en sí** (no del comentario). `_persist_issue_ticket` ya es idempotente por `ado_id` y `publish_issue_from_run` por `already_published_id`; F3 solo lo fija con tests.
- **Validación de well-formedness del HTML** más allá de `_looks_like_epic`. F3 caso 5 documenta el comportamiento actual; un endurecimiento real sería otro plan.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario de dominio Stacky

- **runtime:** motor que ejecuta el agente. Tres valores válidos (`agents.py:336`): `github_copilot`, `codex_cli`, `claude_code_cli`. Paridad obligatoria (o degradación controlada explícita).
- **autopublish:** publicación autónoma del work item en ADO al cerrar la run, sin aprobación (excepción human-in-the-loop pedida explícitamente para brief→épica). Hoy solo en `claude_code_cli_runner._maybe_autopublish_epic` (`claude_code_cli_runner.py:1163`). [[stacky-autopublish-only-claude-cli]]
- **work_item_type:** tipo destino en ADO. Normalizado por `validate_brief_work_item_type` (`tickets.py:2878`): None/"" → "Epic". Issue es opt-in (flag).
- **marker idempotente:** comentario HTML invisible (`_ISSUE_PHASE_MARKERS`, `tickets.py:5954`, p.ej. `<!-- stacky:issue-phase:funcional -->`) que `comment_exists` busca para no duplicar.
- **`_AutopublishResult`:** NamedTuple (`tickets.py:5782`) devuelto por `autopublish_epic_from_run`/`publish_issue_from_run`: `ado_id`, `error`, `skipped`, `grounding_warnings`, `epic_summary`, `recovery_method`.
- **grounding_warnings / epic_summary:** telemetría de calidad de la épica (Planes 42/44). Sellados en `metadata` por el finalizador.
- **arnés / harness_flags:** sistema de flags configurables del runtime (`services/harness_flags.py`).

### Orden de implementación (por dependencia)

1. **F0** (independiente, ALTO valor): guard 400. Tests + impl.
2. **F1** (independiente, MEDIO): paginación de comentarios. Tests + impl.
3. **F3** (independiente, tests): persistencia real del Issue. Solo tests.
4. **F4** (depende conceptualmente de entender el path Issue; tras F0/F1/F3): observabilidad. Tests + impl.

(F2 está fusionada en F0.)

### Definición de Hecho (DoD) global

- [ ] Los 4 archivos de test nuevos pasan al 100%, cada uno corrido por separado con `.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`.
- [ ] `agents.py` rechaza con 400 `autopublish_requires_claude_cli` el combo Epic/Issue + runtime≠claude_code_cli (F0).
- [ ] `comment_exists` recorre todas las páginas vía `fetch_all_comments` con short-circuit y tope `_COMMENT_PAGE_CAP` (F1).
- [ ] Flag `STACKY_COMMENT_FULL_SCAN_ENABLED` registrado (bool, default true) en `harness_flags.py` y documentado en `.env.example`.
- [ ] `publish_issue_from_run` devuelve `grounding_warnings` y `epic_summary` poblados reusando las helpers de la épica (F4); comentario obsoleto en `claude_code_cli_runner.py:1219` actualizado.
- [ ] Path feliz (Claude CLI + Epic) sin regresión: correr el/los archivo(s) de test existentes que cubren `autopublish_epic_from_run` y confirmarlos verdes.
- [ ] Trabajo del operador: ninguno en ninguna fase. Backward-compatible. Flags de Issue siguen default OFF.
- [ ] `grep` confirma que `comment_exists` no tiene callers fuera de `_post_phase_comment` antes de cambiar su contrato (R3).
