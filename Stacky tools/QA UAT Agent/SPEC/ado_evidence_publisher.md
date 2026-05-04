---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `ado_evidence_publisher.py`

## 1. Propósito

Publica el dossier UAT como **un único comentario, idempotente y auditado** en el ticket de Azure DevOps via ADO Manager. Es la **única superficie de escritura del agente QA UAT hacia ADO**. Nunca cambia el estado del ticket; solo agrega o actualiza el comentario de evidencia.

## 2. Alcance

**Hace:**
- Lee los comentarios existentes del ticket via `python ado.py comments <id>` (solo-lectura)
- Detecta si ya existe un comentario del agente (por el marker `<!-- stacky-qa-uat:run`)
- En `--mode dry-run`: escribe un preview en `evidence/<ticket>/preview/` sin tocar ADO
- En `--mode publish`: crea o actualiza el comentario de evidencia en ADO (idempotente)
- Registra cada invocación en el audit log `audit/<YYYY-MM-DD>.jsonl` (incluso dry-run y fallos)

**NO hace:**
- Cambia el estado del ticket en ADO — está explícitamente prohibido y testeado en suite
- Crea más de un comentario por run
- Mezcla evidencia de runs distintos en un comentario
- Acepta credenciales como argumentos CLI

## 3. Inputs

### CLI

```bash
python ado_evidence_publisher.py \
  --ticket 70 \
  [--dossier-dir evidence/70/] \
  [--mode dry-run|publish] \
  [--update-existing true|false] \
  [--run-id <uuid>] \
  [--verbose]
```

| Arg | Tipo | Default | Descripción |
|---|---|---|---|
| `--ticket <id>` | int | — (✅ requerido) | ID del work item en ADO |
| `--dossier-dir <path>` | str | `evidence/<ticket>/` | Carpeta con `ado_comment.html` |
| `--mode <mode>` | str | `dry-run` | `dry-run` = solo preview; `publish` = escribe en ADO |
| `--update-existing` | bool | `true` | Si existe comentario previo del agente, reemplazarlo |
| `--run-id <uuid>` | str | auto-generado | UUID del run (para el marker de idempotencia) |
| `--verbose` | flag | — | Logs detallados a stderr |

### Env vars

| Var | Descripción |
|---|---|
| `STACKY_OPERATOR` | Email del operador para el audit log; si no está, usa `git config user.email` |

Las credenciales de ADO las gestiona ADO Manager via su `ado-config.json`. Esta tool no las necesita directamente.

### Archivo de entrada requerido

`evidence/<ticket>/ado_comment.html` — producido por `uat_dossier_builder.py`. Debe contener el marker `<!-- stacky-qa-uat:run id="..." hash="..." -->`.

## 4. Outputs

### JSON a stdout

```json
{
  "ok": true,
  "action": "created",
  "ticket_id": 70,
  "comment_id": 12345,
  "comment_hash": "sha256:abc...",
  "mode": "publish",
  "audit_log_path": "audit/2026-05-02.jsonl",
  "ado_response_status": 200,
  "meta": {"tool": "ado_evidence_publisher", "version": "1.0.0", "duration_ms": 840}
}
```

**Valores posibles de `action`:**

| Valor | Descripción |
|---|---|
| `dry-run` | Preview generado, ADO no tocado |
| `created` | Primer comentario del agente en el ticket, recién creado |
| `updated` | Comentario existente del agente, reemplazado con el nuevo hash |
| `skipped_unchanged` | El comentario existente tiene el mismo hash → no se tocó ADO |
| `failed` | ADO Manager retornó error |

### Artefactos de dry-run

`evidence/<ticket>/preview/comment_payload.html` — el HTML que se publicaría  
`evidence/<ticket>/preview/intent.json` — el plan exacto:

```json
{
  "would_action": "create|update|skip",
  "existing_comment_id": null,
  "comment_hash": "sha256:...",
  "reason": "No existe comentario previo del agente en ADO-70"
}
```

### Audit log (append-only)

`audit/<YYYY-MM-DD>.jsonl` — una línea por invocación:

```json
{"ts": "2026-05-02T14:32:00Z", "ticket_id": 70, "run_id": "uuid-...", "mode": "publish", "action": "created", "user": "juan@empresa.com", "comment_hash": "sha256:...", "ado_response_status": 200}
```

## 5. Contrato de uso

**Precondiciones:**
- `evidence/<ticket>/ado_comment.html` existe y contiene el marker de idempotencia
- ADO Manager configurado con `ado-config.json` válido
- (Solo para `--mode publish`) conectividad a `dev.azure.com`

**Postcondiciones:**
- En `dry-run`: ADO no fue modificado; artefactos de preview existen en `evidence/<ticket>/preview/`
- En `publish create`: existe exactamente UN comentario nuevo del agente en el ticket
- En `publish update`: el comentario existente fue reemplazado (el comment_id es el mismo u otro, según soporte de ADO Manager)
- En `skipped_unchanged`: ADO no fue modificado; el comentario existente sigue intacto
- El audit log tiene una nueva línea independientemente del modo y del resultado

**Idempotencia:**
- `dry-run`: idempotente
- `publish` con mismo hash: `skipped_unchanged` → idempotente
- `publish` con hash distinto: `updated` → sobreescribe

## 6. Validaciones internas

- `--ticket` debe ser entero positivo → `invalid_id`
- `ado_comment.html` debe contener el marker → `marker_not_found_in_dossier`
- El marker debe estar al inicio del archivo (primeros 200 chars) → `marker_misplaced`
- Antes de crear/actualizar, lee `python ado.py comments <id>` y busca el marker en comentarios existentes
- Si `--update-existing false` y existe comentario previo → retorna `skipped_existing_comment` sin escribir
- Si ADO Manager retorna `ok:false` → `ado_publish_failed`; el dossier queda en disco para reintento manual

### Prohibición de cambio de estado

**NUNCA** se invoca `python ado.py state ...`. Hay un test estático que escanea el código fuente de esta tool (y de todas las `uat_*`) y rechaza cualquier substring `ado.py state` o `update_state`. Este test es parte de la CI obligatoria.

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `invalid_id` | `--ticket` no es entero positivo |
| `dossier_not_found` | `ado_comment.html` no existe en `--dossier-dir` |
| `marker_not_found_in_dossier` | El HTML no contiene `<!-- stacky-qa-uat:run` |
| `marker_misplaced` | El marker no está al inicio del archivo |
| `ado_credentials_missing` | `ado-config.json` no configurado |
| `ado_unreachable` | Sin conectividad a `dev.azure.com` |
| `ado_publish_failed` | ADO Manager retornó `ok:false` al intentar crear/actualizar el comentario |
| `skipped_existing_comment` | `--update-existing false` y ya existe comentario previo |

## 8. Dependencias

- ADO Manager (`ado.py`) — invocado via subprocess para `comments <id>` (lectura) y `comment <id>` (escritura)
- `ado_html_postprocessor.py` — el dossier builder ya procesó el HTML; esta tool no lo reprocesa
- Python 3.8+ stdlib + `hashlib`, `uuid`, `subprocess`, `json`
- Sin LLM

## 9. Ejemplos de uso

```bash
# Dry-run: previsualizar sin tocar ADO
python ado_evidence_publisher.py --ticket 70 --mode dry-run

# Ver el plan del dry-run
cat evidence/70/preview/intent.json

# Publicar en ADO
python ado_evidence_publisher.py --ticket 70 --mode publish

# Re-publicar (si el hash no cambió → skipped_unchanged)
python ado_evidence_publisher.py --ticket 70 --mode publish

# Revisar el audit log
cat audit/2026-05-02.jsonl | python -m json.tool
```

## 10. Criterios de aceptación

- [ ] `--mode dry-run` con dossier real → genera `preview/comment_payload.html` e `intent.json` sin tocar ADO
- [ ] `--mode publish` por primera vez → crea comentario en ADO y retorna `action: "created"` con `comment_id`
- [ ] `--mode publish` con el mismo hash → retorna `action: "skipped_unchanged"` sin llamar a ADO
- [ ] `--mode publish` con hash distinto → retorna `action: "updated"` con nuevo contenido
- [ ] Si ADO Manager falla → `{"ok": false, "error": "ado_publish_failed"}`; dossier sigue en disco
- [ ] El audit log tiene una línea por cada invocación (incluso dry-run y fallos)
- [ ] **Test estático**: escanear todos los archivos `uat_*.py` y `ado_evidence_publisher.py` — ninguno contiene la cadena `ado.py state` o `update_state`
- [ ] Sin `ado_comment.html` → `{"ok": false, "error": "dossier_not_found"}`

## 11. Embedding de evidencia visual (v1.1)

A partir de v1.1 el publisher embebe las screenshots como attachments del work
item, en lugar de dejarlas como paths locales en el comentario.

**Flujo en `--mode publish`:**

1. El HTML producido por `uat_dossier_builder` lleva tokens
   `{{ATTACH:<scenario_id>:<filename>}}` en cada `<img src>`/`<a href>`.
2. El publisher recorre los tokens, sube cada screenshot via
   `python ado.py attach <ticket> <file> --name <upload_name>` y obtiene la URL
   real del attachment.
3. Reemplaza cada token por la URL retornada y luego postea el comentario.

**Flags nuevos:**

| Flag | Descripción |
|---|---|
| `--no-attach` | Desactiva el embedding (legacy text-only) |
| `--replace-previous` | Si detecta un comentario previo de Stacky por marker, lo elimina via `ado.py delete-comment` antes de crear el nuevo |

**Errores nuevos:**

| Código | Cuándo |
|---|---|
| `attachment_upload_failed` | Todos los uploads fallaron (sin URLs válidas para reemplazar tokens) |

**Descripciones por step:**

`uat_dossier_builder` invoca `step_descriptor.build_step_descriptions(...)` que
genera, para cada screenshot, un texto en español que explica qué se intentó
en ese paso. Por defecto usa `gpt-5-mini` vía `llm_client` (VS Code bridge) y
hace fallback determinístico cuando el LLM no está disponible.

## 12. Tests requeridos

```
tests/unit/test_ado_evidence_publisher.py

test_dry_run_generates_preview_without_touching_ado
test_first_publish_creates_comment
test_second_publish_same_hash_skipped_unchanged
test_second_publish_different_hash_updated
test_ado_manager_failure_returns_error_dossier_stays
test_audit_log_written_on_every_invocation
test_missing_dossier_returns_error
test_marker_not_found_returns_error
test_no_state_subcommand_in_codebase  ← test estático de seguridad

# v1.1
test_publish_uploads_attachments_and_replaces_tokens
test_publish_aborts_when_all_uploads_fail
test_no_attach_flag_preserves_legacy_behavior
test_replace_previous_deletes_old_comment
```
