# `services/ado_context.py` — enriquecimiento de contexto ADO

## Qué hace

Antes de invocar al chat de Copilot (vía `agent_runner.py`), inyecta al
contexto del agente **comentarios** y **adjuntos** del work item de Azure
DevOps asociado al ticket. El objetivo es que el contexto que llega al chat
sea **completo**: información principal del ticket + conversación posterior +
material de referencia adjunto.

Sin este enriquecimiento, el LLM solo ve los `context_blocks` que el operador
seleccionó manualmente en la UI (que típicamente son la descripción y unos
pocos blocks), y se pierde:

- Correcciones, aclaraciones y decisiones que quedaron en los comentarios.
- Capturas, documentos, logs y archivos de referencia adjuntos al ticket.

## Política de agentes

Por defecto **todos los agentes registrados** reciben el enriquecimiento:

```
business, functional, technical, developer, qa, debug, pr-review, custom
```

Esto se puede sobreescribir vía variable de entorno:

| `ADO_CONTEXT_ENRICH_AGENTS` | Comportamiento                                   |
| --------------------------- | ------------------------------------------------ |
| no seteada / `""`           | default: todos los agentes registrados           |
| `all` / `*`                 | todos los agentes (incluye custom no registrado) |
| `none` / `off` / `false`    | desactivado                                      |
| `qa,developer,technical`    | CSV de agent.type permitidos                     |

## Variables de entorno relevantes

| Var                                  | Default | Descripción                                                |
| ------------------------------------ | ------- | ---------------------------------------------------------- |
| `ADO_CONTEXT_ENRICH_AGENTS`          | (todos) | ver tabla anterior                                         |
| `ADO_CONTEXT_ATTACH_MAX_TEXT_FILES`  | `5`     | tope de adjuntos cuyo texto se inlinea al prompt           |

Las variables de credencial ADO (`ADO_PAT`, etc.) son resueltas por
`services/ado_client.py`. Si no hay PAT, el enriquecimiento devuelve `[]`
silenciosamente y la ejecución del agente continúa con el contexto original.

## Bloques que produce

| `id`                          | Cuándo aparece                                           |
| ----------------------------- | -------------------------------------------------------- |
| `ado-comments`                | el ticket tiene comentarios no vacíos                    |
| `ado-attachments-index`       | el ticket tiene adjuntos                                 |
| `ado-attachment-<filename>`   | adjunto de texto pequeño (≤ 64 KB) inlineado en el prompt |

Schema (compatible con `prompt_builder.render_blocks`):

```json
{
  "kind": "text",
  "id": "ado-comments",
  "title": "Comentarios ADO del ticket",
  "content": "**Alice** (2026-05-01):\nTexto…\n\n---\n\n**Bob** (2026-05-02):\n…"
}
```

El bloque `ado-attachments-index` lista cada adjunto como Markdown:

```
- **captura.png**  ·  2.0 KB  ·  `image/png`
  https://dev.azure.com/<org>/_apis/wit/attachments/<guid>
```

## Trazabilidad

El runner persiste en `AgentExecution.metadata_dict["ado_context"]`:

```json
{
  "comments_count": 3,
  "attachments_count": 2,
  "attachments_text_inlined": 1,
  "skipped": false,
  "skipped_reason": null,
  "errors": []
}
```

Esto permite a la UI / dashboards mostrar cuánto contexto extra se inyectó
para cada ejecución, y debuggear por qué un agente "no vio" un comentario.

## Idempotencia

Si el `existing_blocks` ya trae un block con `id` `ado-comments` o
`ado-attachments-index`, `enrich()` no hace nada (no duplica ni vuelve a
llamar a la API). Esto permite re-ejecuciones desde caché o desde history sin
duplicar contexto.

## Compatibilidad con QA UAT y otros consumidores

El schema de los bloques es exactamente el de los demás `ContextBlock` que
maneja `prompt_builder.render_blocks`: `kind`, `id`, `title`, `content`. No
hay nuevos campos requeridos en los blocks → cualquier consumidor downstream
(QA UAT, embeddings, contract validator) los procesa transparentemente.

## Cómo testear

```powershell
cd "N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky Agents\backend"
python -m pytest tests/test_ado_context.py -v
```

17 tests cubren: política de agentes, env vars, comments-only, attachments
con/sin texto inline, mime detection por extensión, hint explícito,
idempotencia, errores no fatales y compatibilidad de signatura legacy
(`return_stats=False` sigue devolviendo `list`).

## Rollback

Para desactivar completamente el enriquecimiento sin tocar código:

```powershell
$env:ADO_CONTEXT_ENRICH_AGENTS = "off"
# Reiniciar el backend de Stacky Agents.
```

Para revertir solo un agente (ej. el agente debug ruidoso):

```powershell
$env:ADO_CONTEXT_ENRICH_AGENTS = "business,functional,technical,developer,qa,pr-review,custom"
```

Para revertir el cambio entero, hacer `git revert` del commit que extiende
`_DEFAULT_ENRICHED_AGENTS` y la firma de `enrich()` (`return_stats`).
