---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-23
---

# SPEC - `ado_evidence_publisher.py`

## 1. Proposito

`ado_evidence_publisher.py` queda como herramienta legacy de preview/auditoria para dossiers UAT. QA UAT no publica, no adjunta y no borra comentarios en Azure DevOps de forma directa.

La publicacion formal de comentarios y screenshots la hace exclusivamente Stacky Agents backend mediante `services.ado_publisher`, leyendo los artefactos que el agente deja en el contrato central:

```text
Agentes/outputs/<ADO_ID>/comment.html
Agentes/outputs/<ADO_ID>/comment.meta.json
Agentes/outputs/<ADO_ID>/attachments.json
Agentes/outputs/<ADO_ID>/attachments/<files>
```

## 2. Alcance

**Hace:**

- Lee `dossier.json` y `ado_comment.html` locales para validar que existen.
- En `--mode dry-run`, devuelve preview/auditoria sin tocar ADO.
- En `--mode publish`, rechaza la operacion con `direct_publish_forbidden`.
- Escribe audit log local por invocacion.

**No hace:**

- No llama `ado.py comment`.
- No llama `ado.py attach`.
- No llama `ado.py delete-comment`.
- No cambia estado del ticket en ADO.
- No publica ni actualiza comentarios en ADO.

## 3. Handoff Correcto

El flujo QA UAT debe usar `stacky_handoff.export_stacky_handoff(...)` o el pipeline principal, que genera:

```json
{
  "ok": true,
  "publish_state": "stacky_handoff_ready",
  "html_output_path": "Agentes/outputs/120/comment.html",
  "attachments_count": 4
}
```

Stacky backend toma ese `html_output_path`, sube los archivos declarados en `attachments.json`, reemplaza tokens `{{ATTACH:<scenario>:<filename>}}` por URLs reales de ADO y recien entonces publica el comentario.

## 4. CLI

```bash
python ado_evidence_publisher.py --ticket-id 120 --dossier evidence/120/dossier.json --mode dry-run
python ado_evidence_publisher.py --ticket-id 120 --dossier evidence/120/dossier.json --mode publish
```

`--mode publish` existe solo por compatibilidad y siempre devuelve `direct_publish_forbidden`.

## 5. Salidas Esperadas

### Dry Run

```json
{
  "ok": true,
  "mode": "dry-run",
  "action": "preview_only",
  "ticket_id": 120
}
```

### Publish Bloqueado

```json
{
  "ok": false,
  "error": "direct_publish_forbidden",
  "action": "delegated_to_stacky",
  "ticket_id": 120
}
```

## 6. Evidencia Visual

El HTML puede contener:

```html
<img src="{{ATTACH:QA-UAT-001:step_final.png}}" />
```

QA UAT debe dejar un `attachments.json` junto a `comment.html`:

```json
{
  "schema_version": "stacky.agent_attachments.v1",
  "attachments": [
    {
      "token": "{{ATTACH:QA-UAT-001:step_final.png}}",
      "path": "attachments/step_final.png",
      "upload_name": "ADO-120_step_final.png",
      "comment": "QA UAT QA-UAT-001: evidencia final"
    }
  ]
}
```

Solo Stacky backend sube esos archivos a ADO y reemplaza los tokens.

## 7. Criterios De Aceptacion

- `--mode dry-run` no toca ADO.
- `--mode publish` no toca ADO y devuelve `direct_publish_forbidden`.
- QA UAT pipeline genera `Agentes/outputs/<ADO_ID>/comment.html`.
- Si hay screenshots, QA UAT pipeline genera `attachments.json` y copia los archivos bajo `attachments/`.
- `services.ado_publisher` sube los adjuntos, linkea el work item y publica el HTML final.
- El hash de deduplicacion de Stacky incluye `comment.html`, `attachments.json` y bytes de los adjuntos.
