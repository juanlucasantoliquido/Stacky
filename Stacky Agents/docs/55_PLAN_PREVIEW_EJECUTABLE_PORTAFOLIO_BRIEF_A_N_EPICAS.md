# Plan 55 — Preview Ejecutable de Publicación + Portafolio brief→N épicas

> Versión: v1 → v2 (propuesto 2026-06-20). Top-5 debate adversarial, ítem 3/5. Depende del Plan 53 solo en orden.
>
> ## v1 → v2 CHANGELOG (juicio adversarial 2026-06-20)
>
> - **C5 (IMPORTANTE, resuelto):** F0 "Refactor de `autopublish_epic_from_run`" sin especificar si el cambio es observable. Reescrita F0 para claridad: refactor pura extracción; `autopublish_epic_from_run` llama al helper nuevoo; tests de regresión obligatorios.
> - **C6 (IMPORTANTE, resuelto):** Contrato UX endpoint F1 vago: ¿deshabilita frontend el botón por `publishable_runtime` o espera 400? Clarificada expectativa: frontend deshabilita ANTES (más UX responsivo).
> - **C7 (MENOR, documentado):** Partición portafolio F3 por H1 es determinista pero frágil si output heterogéneo. Documentado: si output sin H1s, `_split_epics_html` devuelve [output] (una épica); riesgo de false-positives si agente genera H1s para encabezados, no épicas (mitigable por instrucción de agente).
> - **[ADICIÓN ARQUITECTO]:** Endpoint de fallback `/api/tickets/epic-preview?execution_id=<id>&work_item_type=Issue`: mismo preview para Issue (reusa `build_epic_payload_preview` con type="Issue", sin cambios de lógica; solo inyección de parámetro). Fallback: Issue sin output → `epic_not_in_output` (mismo que Epic).

## Resumen (3 líneas)
- **Qué propone:** (a) antes de auto-publicar, el operador ve EXACTAMENTE el payload/HTML que Stacky mandaría a ADO — render PURO del payload que `autopublish_epic_from_run` construiría, solo-lectura, sin llamar a ADO; (b) salto átomo→molécula: un brief puede producir un PORTAFOLIO de N épicas relacionadas en preview, no una sola.
- **Valor:** fidelidad por construcción (el preview reusa el mismo constructor que publica → cero divergencia preview/realidad); refuerza human-in-the-loop (ver antes de tocar la realidad) sin agregar trabajo (inspeccionar es opcional).
- **3 runtimes:** el preview se computa desde el `output` del run en los 3 runtimes (función pura sobre texto); el BOTÓN publicar mantiene la degradación Claude-CLI-only ya existente (`autopublish_requires_claude_cli`, agents.py:603). Fallback: si el output no es épica válida, el preview muestra el mismo `epic_not_in_output` que produciría la publicación.

---

## Glosario corto
- **Preview ejecutable:** render solo-lectura del payload exacto que se enviaría a ADO, producido por el MISMO código que publica (no una re-derivación paralela).
- **Constructor de payload:** la cadena `_extract_epic_html` → `_looks_like_epic` → `_derive_epic_title` → (lo que arma el cuerpo HTML del WI) dentro de `autopublish_epic_from_run` (tickets.py:5823).
- **Portafolio (molécula):** lista de N épicas derivadas de un mismo brief, cada una con su preview, mostradas juntas. Detrás de flag propio.
- **Degradación Claude-CLI-only:** publicar Epic/Issue exige `runtime == claude_code_cli` (agents.py:600-605). El PREVIEW no exige eso (es solo-lectura).

## Sustrato verificado (archivo:línea — 2026-06-20)
- `backend/api/tickets.py:5823 autopublish_epic_from_run(*, output, brief, project_name, already_published_id, run_started_at=None) -> _AutopublishResult` — construye y publica. Armado: `_extract_epic_html(output)` (5854), `_looks_like_epic(clean_html)` (5859), `_derive_epic_title(raw, ...)` (~5688). Envío: `_publish_epic_to_ado(...)` (~5860-5900, incluyendo rescate de disco). Return: `_AutopublishResult` (~5999).
- `backend/api/tickets.py:5406 _extract_epic_html(raw)`, `:5518 _looks_like_epic(html)`, `:5688 _derive_epic_title(raw, *, fallback, max_len=250)`, `:5806 class _AutopublishResult(NamedTuple)`.
- `backend/api/tickets.py:6173 publish_issue_from_run(...)` — análogo para Issue (rescata cuerpo con `_sanitize_epic_html`, publica vía ADO).
- `backend/api/agents.py:565 run_brief()`; `:600-605` rechaza Epic/Issue si `runtime != _AUTOPUBLISH_RUNTIME` (Plan 52).
- `backend/services/claude_code_cli_runner.py:1191 _maybe_autopublish_epic` — **único call-site que autopublica** en cualquier runner (Plan 52 verificado).

**Conclusión de sustrato:** construcción y publicación están entrelazadas en `autopublish_epic_from_run`. **F0 debe extraer solo la construcción** (sin tocar BD/ADO) en una función pura. Luego `autopublish_epic_from_run` llama al helper antes de publicar (refactor no-observable si se resguardan los tests).

## Rieles no negociables (codificados aquí)
- **Paridad 3 runtimes con fallback:** el preview se computa desde `output` (texto), igual en los 3 runtimes. Fallback explícito: output no-épica → preview muestra el motivo `epic_not_in_output` (mismo que publicación).
- **Cero trabajo extra:** preview es opcional inspeccionarlo; default ON aceptable por ser solo-lectura. Portafolio detrás de flag propio default OFF.
- **Human-in-the-loop:** el preview REFUERZA al operador (ve antes de publicar). No publica nada solo. El botón publicar sigue siendo acción humana con la degradación CLI-only.
- **No degradar:** preview no toca ADO ni la DB de tickets. Solo lee `output`.
- **Backward-compatible:** flag OFF de portafolio = comportamiento actual (1 épica). Preview ON no cambia el flujo de publicación.
- **Reusar lo existente:** el preview NO re-deriva el HTML; reusa el constructor extraído de `autopublish_epic_from_run`.

---

## Fases

### F0 — Extraer y consolidar la construcción de payload (refactor puro)
**Objetivo:** función pura `build_epic_payload_preview` que reproduce el armado que `autopublish_epic_from_run` hace ANTES de `_publish_epic_to_ado`. Luego refactor `autopublish_epic_from_run` para llamarlo (cambio no-observable con resguardo de regresión).

- **Archivo nuevo:** `backend/api/tickets.py` (agregar símbolos aquí; no es archivo separado)
- **Símbolos nuevos (función + dataclass):**
  ```python
  class EpicPayloadPreview(NamedTuple):
      ok: bool
      title: str | None
      html: str | None
      work_item_type: str          # "Epic" | "Issue"
      error: str | None            # "epic_not_in_output" | "empty_output" etc.
      grounding_warnings: list = []

  def build_epic_payload_preview(
      *,
      output: str | None,
      brief: str,
      project_name: str | None,
      work_item_type: str = "Epic",
  ) -> EpicPayloadPreview:
      """PURA. NO publica ni toca BD/ADO. Reproduce exactamente el armado que
      autopublish_epic_from_run/publish_issue_from_run hacen ANTES de _publish_*_to_ado.

      Orden lógico (mismo que el publicador):
        1. output vacío → ok=False, error="empty_output".
        2. clean_html = _extract_epic_html(output).
        3. not _looks_like_epic(clean_html) → ok=False, error="epic_not_in_output".
        4. title = _derive_epic_title(output, fallback=...).
        5. si work_item_type=="Issue": aplica path Issue (rescate disco, sanitiza).
        6. ok=True.
      NUNCA lanza.
      """
  ```
- **Refactor de `autopublish_epic_from_run`:** líneas ~5850-5900 (antes de `_publish_epic_to_ado`)
  - Cambiar: `payload = build_epic_payload_preview(...); if not payload.ok: return _AutopublishResult(...)`
  - Luego: `_publish_epic_to_ado(payload.title, payload.html, ...)` (se simplifica la lógica inline).
  - **Resultado:** `autopublish_epic_from_run` sigue publicando idéntico; ahora delega extracción al helper.
  
- **Caso borde — Rescate del disco:** vive en `publish_issue_from_run` (~línea 5961, `_persist_issue_ticket`). El preview NO rescata (preview es sobre output, no artefactos). Documentar: si el agente narró, preview dice "epic_not_in_output" aunque luego se rescate. OK, y documentado.

- **Tests PRIMERO (refactor-safe):** `backend/tests/test_epic_payload_preview.py`
  - `test_empty_output_returns_error` → output=None → ok=False, error="empty_output".
  - `test_narration_not_html_returns_error` → output prosa sin HTML → ok=False, error="epic_not_in_output".
  - `test_valid_epic_html_returns_ok` → output con HTML válido → ok=True, title no vacío.
  - `test_epic_and_issue_paths_differ` — work_item_type="Issue" vs "Epic" → paths internos distintos (si aplica).
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_payload_preview.py" -q`
- **Regresión:** suite existente de `autopublish_epic_from_run` (localizar: `grep -rn "test_autopublish" backend/tests/`) debe pasar sin cambios.
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_autopublish_backend.py" -q` (ajustar nombre si es distinto).
- **Aceptación binaria:** 4 tests nuevos verdes + suite existente sin regresión. **Comando:** arriba, exit 0 en ambos.
- **Flag:** ninguno (puro).
- **Impacto por runtime:** ninguno (refactor no-observable).
- **Trabajo del operador:** ninguno.

### F1 — Endpoint de preview (solo-lectura, paridad 3 runtimes)
**Objetivo:** exponer el preview por HTTP. Paridad: los 3 runtimes generan preview; publicar sigue Claude-CLI-only.

- **Archivo:** `backend/api/tickets.py` (ahí vive `build_epic_payload_preview`).
- **Ruta:** `GET /api/tickets/epic-preview?execution_id=<id>&work_item_type=Epic|Issue`
  - Lee `output`, `brief`, `project_name` del run `execution_id`.
  - Llama `build_epic_payload_preview(...)`.
  - Responde HTTP 200:
    ```json
    {
      "ok": bool,
      "title": str | null,
      "html": str | null,
      "work_item_type": "Epic" | "Issue",
      "error": str | null,
      "grounding_warnings": list,
      "publishable_runtime": bool
    }
    ```
    donde `publishable_runtime = (run.runtime == "claude_code_cli")` (informa al frontend; Plan 52 ya valida en run_brief).
    
- **Casos borde:**
  - execution_id inexistente → 404 `{"ok":false,"error":"run_not_found"}`.
  - output=None/vacío → 200 `ok=false, error="empty_output"` (no es error HTTP; esperable si run aún corre).
  - flag `STACKY_ADO_PREVIEW_ENABLED` OFF → 404 (endpoint deshabilitado).
- **Tests:** `backend/tests/test_epic_preview_endpoint.py`
  - `test_preview_returns_html_for_epic`
  - `test_preview_returns_false_for_codex_publishable` — runtime=codex_cli → `publishable_runtime=false`.
  - `test_preview_returns_false_for_copilot_publishable` — runtime=github_copilot → `publishable_runtime=false`.
  - `test_preview_returns_true_for_claude_cli` — runtime=claude_code_cli → `publishable_runtime=true`.
  - `test_preview_404_when_flag_off`
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_preview_endpoint.py" -q`
- **Aceptación binaria:** 5 tests verdes. **Comando:** arriba, exit 0.
- **Flag:** `STACKY_ADO_PREVIEW_ENABLED` default **ON** (solo-lectura, no degrada). env_only.
- **Impacto por runtime:** los 3 runtimes generan preview (pura construcción, sin publicar). Publicar sigue Claude-CLI-only (error 400 en run_brief, Plan 52).
- **Trabajo del operador:** ninguno (opt-in inspeccionable).

### F2 — UI del preview (muestra payload antes de publicar)
**Objetivo:** mostrar el HTML/título que se publicaría, con control UX sobre el botón publicar.

- **Archivo:** componente en `frontend/src/components/` que dispara publicación (localizar: `grep -rn "publishEpic\|run_brief\|dispatch.*Epic\|autopublish" frontend/src/components`).
- **Cambio (UX decisión):** 
  - Sección "Vista previa de publicación" que consulta `GET /api/tickets/epic-preview?execution_id=<id>&work_item_type=Epic`.
  - Si `ok===true`: renderiza `<div dangerouslySetInnerHTML={{ __html: sanitize(html) }} />` + `title` (solo-lectura).
  - Si `ok===false`: muestra el `error` legible (p.ej. "El agente narró en vez de devolver épica").
  - **Botón publicar:** si `publishable_runtime===false` → deshabilita botón y muestra tooltip "Este runtime no auto-publica; selecciona Claude Code CLI" (anticipatorio, antes de HTTP 400).
- **Casos borde:**
  - Endpoint no disponible (flag OFF) → oculta sección preview.
  - Output aún corriendo → preview muestra `ok=false, error="empty_output"` (transparente).
- **Tests:** `tsc --noEmit` sin errores (Vitest no necesario para type-check). **Comando:** `cd frontend && npx tsc --noEmit`.
- **Aceptación binaria:** 0 errores TS. **Comando:** arriba, exit 0.
- **Flag:** UI graceful si endpoint 404 (oculta sección).
- **Impacto por runtime:** UI idéntica para los 3. Botón publicar controlado por `publishable_runtime` antes de intentar.
- **Trabajo del operador:** opcional leer el preview; ningún trabajo nuevo obligatorio.

### F3 — Portafolio brief→N épicas (preview de molécula) [flag propio OFF]
**Objetivo:** un brief puede previsualizar N épicas relacionadas, no solo una (separando por estructura HTML determinista).

- **Archivo:** `backend/api/tickets.py`
- **Símbolo nuevo (función pura):**
  ```python
  def build_epic_portfolio_preview(
      *,
      output: str | None,
      brief: str,
      project_name: str | None,
  ) -> list[EpicPayloadPreview]:
      """PURA. Particiona output en bloques-épica por separador estructural (H1 headings).
      Aplica build_epic_payload_preview a cada bloque.
      
      Partición determinista vía _split_epics_html:
        - Si 0 H1s: devuelve [output] (una épica).
        - Si 1+ H1s: devuelve [bloque1, bloque2, ...].
      Sin LLM, sin generación.
      Resultado: list[EpicPayloadPreview]. NUNCA lanza.
      """
  def _split_epics_html(html: str) -> list[str]:
      """PURA. Divide por <h1>...</h1> como separador de épicas.
      Si no hay H1s → [html] (una épica).
      Determinista: mismo input → mismo output (mismo orden)."""
  ```
- **Riel duro:** partición DETERMINISTA (estructura HTML), **NO LLM**. NO genera nuevas épicas: solo particiona lo que el agente YA produjo. Si operador quiere N épicas distintas, el agente debe generarlas.
  
- **Endpoint:** `GET /api/tickets/epic-portfolio-preview?execution_id=<id>` (mismo patrón F1) bajo flag `STACKY_EPIC_PORTFOLIO_ENABLED` default OFF.
- **Tests:** `backend/tests/test_epic_portfolio_preview.py`
  - `test_no_h1_returns_single_item` — output sin H1s → [output] (una épica).
  - `test_three_h1_returns_three_items` — output con 3 H1s → 3 épicas.
  - `test_split_is_deterministic` — mismo HTML → misma partición (order stable).
  - `test_endpoint_404_when_flag_off`
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_portfolio_preview.py" -q`
- **Aceptación binaria:** 4 tests verdes. **Comando:** arriba, exit 0.
- **Flag:** `STACKY_EPIC_PORTFOLIO_ENABLED` default OFF (superficie nueva; opt-in).
- **Impacto por runtime:** preview en los 3. **Publicar N épicas está FUERA de scope** (solo preview).
- **Trabajo del operador:** ninguno (opt-in).

### F4 — Registrar tests en el ratchet + [ADICIÓN ARQUITECTO] Issue preview
- **Archivos:** `backend/scripts/run_harness_tests.ps1` y `.sh` — añadir `test_epic_payload_preview.py`, `test_epic_preview_endpoint.py`, `test_epic_portfolio_preview.py`.
- **Aceptación:** meta-test del ratchet (plan 49 F4) verde. **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_harness_ratchet_meta.py" -q` exit 0.
- **[ADICIÓN ARQUITECTO] Issue preview fallback:** El endpoint `GET /api/tickets/epic-preview?work_item_type=Issue` reusa `build_epic_payload_preview(work_item_type="Issue")`. No duplica lógica; UI muestra el preview igual que Epic. Comando test: `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_preview_endpoint.py" -q` (incluye casos Issue).

---

## Orden de implementación
F0 (refactor + regresión) → F1 (endpoint) → F2 (UI) → F3 (portafolio, opcional) → F4 (ratchet).

## Fuera de scope (dependencias con el top-5)
- **Publicar N épicas del portafolio:** este plan solo previsualiza. La publicación de molécula sería un plan futuro.
- **Plan 56 (gate de regresión):** el gate corre sobre el output; el preview es ortogonal. No se acoplan.
- **Plan 54:** independiente (memoria de rechazos no afecta el preview).
- El rescate del disco (Plan 47) NO se reproduce en el preview (divergencia documentada en F0).

## DoD
1. `test_epic_payload_preview.py` (incl. `test_preview_html_matches_publisher`), `test_epic_preview_endpoint.py`, `test_epic_portfolio_preview.py` verdes.
2. `GET /api/tickets/epic-preview` devuelve el MISMO `html` que `autopublish_epic_from_run` enviaría (fidelidad por construcción demostrada por test).
3. Preview disponible en los 3 runtimes; botón publicar gobernado por `publishable_runtime`/degradación CLI-only existente.
4. `STACKY_ADO_PREVIEW_ENABLED` default ON; `STACKY_EPIC_PORTFOLIO_ENABLED` default OFF.
5. `tsc --noEmit` 0 errores.
6. Tests en el ratchet y meta-test verde.
