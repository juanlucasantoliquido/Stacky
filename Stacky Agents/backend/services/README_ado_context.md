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
| `ado-comments`                | el ticket tiene comentarios no vacíos (**Azure DevOps o GitLab**, ver abajo) |
| `ado-attachments-index`       | el ticket tiene adjuntos (**sólo Azure DevOps**)          |
| `ado-attachment-<filename>`   | adjunto de texto pequeño (≤ 64 KB) inlineado en el prompt (**sólo Azure DevOps**) |

Schema (compatible con `prompt_builder.render_blocks`):

```json
{
  "kind": "text",
  "id": "ado-comments",
  "title": "Comentarios ADO del ticket",
  "content": "**Alice** (2026-05-01):\nTexto…\n\n---\n\n**Bob** (2026-05-02):\n…"
}
```

## Plan 289 — el módulo dejó de ser ADO-only

Desde el Plan 289, `build_ado_context_blocks` **despacha por tracker** antes de
construir el cliente de Azure DevOps. Lo que sigue es lo que hay que saber para
no romperlo.

### El dispatcher

Vive en `build_ado_context_blocks`, **después** de inicializar `stats` y **antes**
del `try` que construye el `AdoClient`. Decide así:

- con `ticket` → `project_context.tracker_efectivo_de_ticket(ticket)` (Plan 286);
- sin `ticket` (flujo *epic-from-brief* y los tests) →
  `project_context.tracker_is_azure_devops(project_name)`, que es **fail-closed a
  ADO** (Plan 281): sin dato, se comporta como hoy.

**Nunca decide leyendo la columna del ticket**: esa columna nace con
`default="azure_devops"` y miente (Planes 281/286). Si el proyecto no es ADO, se
delega en `_bloques_por_proveedor` → `services/tracker_context.py`, que lee por
la **fábrica única** `get_tracker_provider` (Plan 282: construir
`GitLabTrackerProvider(...)` a mano pierde el `ca_bundle`).

La flag `STACKY_TRACKER_CONTEXT_ENABLED` (**ON**) apaga el dispatcher entero: con
ella en `false` el módulo vuelve byte-idéntico a antes del plan.

### Mismo `id`, distinto título — y por qué

El bloque de GitLab conserva **`id: "ado-comments"`**. No es pereza de naming:

1. `context_enrichment._BLOCK_PRIORITY` mapea `ado-comments` a **30**; un id nuevo
   caería en `_DEFAULT_PRIORITY = 50`, o sea **más alto** que `harness-patterns`
   (45) y `ado-similar-tickets` (40), y bajo presión de presupuesto se podarían
   otros bloques en vez de éste. Sería un cambio de comportamiento silencioso.
2. El guard de idempotencia de `enrich()` (ver más abajo) depende del `id`.
3. Tres `.agent.md` en dos árboles y cuatro suites de test lo nombran.

Lo que sí cambia es el **título**: `"Comentarios ADO del ticket"` para Azure
DevOps (literal, hay un test que lo asserta) y
`"Comentarios del ticket (GitLab)"` para GitLab.

### Enmascarado de secretos — en los DOS caminos

Todo el texto de un comentario pasa por `secret_masking.mask_token_values` antes
de entrar al bloque. Es un endurecimiento **deliberado** que también alcanza a
Azure DevOps: los comentarios los escriben personas y llegan enteros al prompt
del LLM. **No tiene flag a propósito** — una flag cuya posición OFF filtra
credenciales a un modelo no debería existir. El rollback es revertir el commit.

### Markdown vs HTML

La forma canónica de un comentario es `{author, date, text[, is_html]}`.
**`is_html` ausente significa `True`** (camino ADO, byte-idéntico). GitLab emite
`is_html=False` porque sus notas son Markdown, y pasarlas por `_html_to_text`
(que usa `HTMLParser`) **borra** fragmentos como `List<int>` o `<NombreDelCampo>`:
una pérdida silenciosa de contexto técnico.

### Tope de comentarios

`GitLabTrackerProvider.fetch_comments` **no acepta `top`**. El tope lo pone
Stacky: `tracker_context.max_comments()`, **30** por defecto — exactamente el
`top=30` que usa el camino ADO — bajable con `TRACKER_CONTEXT_MAX_COMMENTS`.
Se conservan las **más recientes**. Ojo: el tope limita los ítems **entregados al
prompt**, no las páginas que el provider ya le pidió al servidor.

### El orden diverge entre trackers, y el bloque lo dice

Azure DevOps pide `order=desc`, así que su lista llega **del más nuevo al más
viejo**. GitLab devuelve **del más viejo al más nuevo** y el plan **no invierte
ninguno de los dos** (invertir ADO cambiaría el prompt de todos los agentes que
hoy funcionan). En cambio, el bloque de GitLab lleva un **sello de procedencia**
como primera línea del contenido:

```
_(GitLab · 30 de 200 comentarios (los mas recientes), del mas antiguo al mas reciente)_
```

El sello dice tres cosas que el agente necesita: **de dónde vienen**, **si están
completos** y **en qué sentido se leen**. Va en el `content` y no sólo en la
metadata **a propósito**: la metadata es un canal frágil (ver la sección
siguiente) y el agente nunca la ve. En el camino ADO el sello está **ausente**,
así que el contenido queda byte-idéntico.

### Adjuntos: hueco declarado, no un cero mudo

En GitLab **no hay adjuntos en el contexto**. `fetch_attachments` del provider
saca links por regex de la descripción del issue y **no descarga el contenido**,
mientras que el camino ADO consume `text_content` ya descargado. Traer paridad es
un plan aparte. Lo que sí se hace es **declarar el hueco**:
`stats["attachments_skipped_reason"] = "provider_sin_descarga_de_adjuntos"`, para
que un `attachments_count: 0` no se confunda con un fallo.

### La whitelist de `enrich()` — la trampa que hay que conocer

**`enrich()` NO devuelve el `stats` que arma `build_ado_context_blocks`.** Arma
uno propio y lo actualiza **clave por clave**. Durante años eso fue inocuo porque
las claves eran las mismas cuatro. Hoy no lo es:

> **Toda clave nueva que `build_ado_context_blocks` ponga en `stats` se pierde en
> silencio si no se agrega también a `enrich()`.**

El modo de fallo es **invisible**: la fase que agrega el contador escribe el dato,
su test unitario pasa (porque asserta una capa más abajo) y el operador ve un `0`
sin explicación. El Plan 289 agregó un bucle que propaga
`comments_truncated`, `comments_total_disponibles` y `attachments_skipped_reason`
**sólo si el productor las puso** (así el camino ADO queda byte-idéntico), y lo
congeló con un test de contrato:

`tests/test_plan289_contexto_por_tracker.py::test_enrich_propaga_TODAS_las_claves_que_produce_el_armador`

Ese test parchea el productor con una **clave centinela inventada** y verifica
**primero** que la centinela sí se pierde — si dejara de perderse, el detector
estaría roto y el test no probaría nada — y **después** que las reales sí llegan.
Mata la **clase** de bug, no la instancia. **Si agregás una clave a `stats`,
agregala al bucle en el mismo commit.**

### El contador sobrevive en los 3 runtimes

`context_enrichment.persistir_stats_de_contexto()` es la **única** función que
escribe `metadata["ado_context"]`, y la llaman los tres runtimes justo después de
enriquecer. Antes del Plan 289, `claude_code_cli_runner` y `codex_cli_runner`
asignaban el segundo valor de `enrich_blocks` a `_ado_stats` y **lo tiraban**: el
73 % de las ejecuciones de la base no tenía el dato, así que cualquier métrica
sobre él era inmedible. Es best-effort y **nunca levanta**: persistir un contador
no puede tumbar una corrida.

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

En el camino GitLab (Plan 289) se suman, **sólo si el productor las emitió**:

```json
{
  "comments_truncated": true,
  "attachments_skipped_reason": "provider_sin_descarga_de_adjuntos"
}
```

Esto permite a la UI / dashboards mostrar cuánto contexto extra se inyectó
para cada ejecución, y debuggear por qué un agente "no vio" un comentario.

Los modos de fallo del camino por proveedor se declaran en `errors` con un
prefijo estable: `tracker_provider_unavailable:` (incluye
`STACKY_GITLAB_ENABLED=false`, que **nunca** se reporta como un error de Azure
DevOps), `capability_missing:`, `fetch_comments_failed:` y
`tracker_dispatch_failed:`.

## Idempotencia

Si el `existing_blocks` ya trae un block con `id` `ado-comments` o
`ado-attachments-index`, `enrich()` no hace nada (no duplica ni vuelve a
llamar a la API). Esto permite re-ejecuciones desde caché o desde history sin
duplicar contexto.

**Éste es uno de los tres motivos por los que el bloque de GitLab conserva el id
`ado-comments`** en vez de estrenar uno propio: un id nuevo se escaparía de este
guard y se podría inyectar dos veces. Ver la sección del Plan 289 más arriba.

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
