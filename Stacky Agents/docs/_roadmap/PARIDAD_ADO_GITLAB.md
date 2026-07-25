# Paridad Azure DevOps ↔ GitLab

> **ARCHIVO GENERADO — no editar a mano.** Lo produce
> `services.provider_capabilities.render_markdown_matrix()` y
> `tests/test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado`
> queda ROJO si diverge. Fuente de verdad: `CAPABILITY_MATRIX` (Plan 218 F2).

## Resumen

| Proveedor | completa | parcial | ausente | no aplica |
|---|---|---|---|---|
| azure_devops | 38 | 8 | 25 | 0 |
| gitlab | 33 | 14 | 22 | 2 |

Total de capacidades declaradas: **71**.

## Matriz por capacidad

Una fila por capacidad: estado en cada proveedor, pérdida declarada cuando el
estado es parcial, y la evidencia `archivo:línea` que lo respalda.

| Capacidad | Azure DevOps | GitLab | Pérdida declarada | Evidencia ADO | Evidencia GitLab |
|---|---|---|---|---|---|
| **tracker.\*** | | | | | |
| `tracker.items.list` | completa | completa | — | `services/ado_client.py:319` | `services/gitlab_provider.py:155` |
| `tracker.items.get` | parcial | completa | **ADO:** propaga AdoApiError crudo en vez de TrackerApiError(kind='not_found'): el consumidor no puede distinguir 'no existe' de 'se cayó la API' | `services/ado_provider.py:66` | `services/gitlab_provider.py:164` |
| `tracker.items.create` | completa | completa | — | `services/ado_provider.py:101` | `services/gitlab_provider.py:252` |
| `tracker.items.update_state` | completa | completa | — | `services/ado_provider.py:81` | `services/gitlab_provider.py:218` |
| `tracker.items.update_assignee` | completa | parcial | **GitLab:** si el usuario no resuelve, silencia el error y BORRA el asignado en vez de levantar un error tipado | `services/ado_provider.py:120` | `services/gitlab_provider.py:363` |
| `tracker.items.url` | completa | parcial | **GitLab:** devuelve None con los deep links apagados, violando la firma '-> str' del puerto | `services/ado_provider.py:69` | `services/gitlab_provider.py:169` |
| `tracker.states.list` | completa | parcial | **GitLab:** devuelve 4 claves lógicas hardcodeadas, no los estados reales del tracker ni los del perfil del cliente | `services/ado_client.py:393` | `services/gitlab_provider.py:84` |
| `tracker.types.list` | completa | ausente | — | `services/ado_client.py:416` | `services/gitlab_provider.py:45` |
| `tracker.query.search` | completa | completa | — | `services/ado_client.py:325` | `services/gitlab_provider.py:48` |
| `tracker.comments.list` | completa | completa | — | `services/ado_client.py:431` | `services/gitlab_provider.py:289` |
| `tracker.comments.list_all` | completa | parcial | **GitLab:** es idéntico a fetch_comments: no pagina el histórico completo ni acepta marker | `services/ado_client.py:796` | `services/gitlab_provider.py:293` |
| `tracker.comments.post` | completa | completa | — | `services/ado_client.py:768` | `services/gitlab_provider.py:297` |
| `tracker.comments.idempotent` | completa | completa | — | `services/ado_provider.py:95` | `services/gitlab_provider.py:307` |
| `tracker.attachments.list` | completa | parcial | **GitLab:** GitLab no tiene modelo de relaciones: los adjuntos se extraen por regex sobre la descripción del issue | `services/ado_client.py:458` | `services/gitlab_provider.py:343` |
| `tracker.attachments.upload` | completa | completa | — | `services/ado_client.py:687` | `services/gitlab_provider.py:313` |
| `tracker.attachments.link` | completa | completa | — | `services/ado_client.py:736` | `services/gitlab_provider.py:325` |
| `tracker.hierarchy.link_parent` | completa | parcial | **GitLab:** sin licencia Premium no hay épicas nativas: cae a issue-links, que no son jerarquía real (no hay padre único) | `services/ado_provider.py:101` | `services/gitlab_provider.py:104` |
| `tracker.hierarchy.find_child` | completa | parcial | **GitLab:** devuelve el PADRE como proxy del hijo cuando no hay épica nativa | `services/ado_provider.py:115` | `services/gitlab_provider.py:381` |
| `tracker.updates.history` | completa | parcial | **GitLab:** las sub-consultas de resource_state_events / resource_label_events están silenciadas: sin historial de estado ni de etiquetas | `services/ado_provider.py:137` | `services/gitlab_provider.py:413` |
| `tracker.sync.full` | completa | ausente | — | `services/ado_sync.py:102` | `api/tickets.py:692` |
| `tracker.sync.incremental` | parcial | ausente | **ADO:** upsert_single_work_item procesa de a un ítem: no hay ventana incremental por fecha ni cursor persistido | `services/ado_sync.py:235` | — |
| `tracker.epics.list` | completa | ausente | — | `services/ado_provider.py:487` | — |
| `tracker.epics.create_native` | completa | parcial | **GitLab:** requiere licencia GitLab Premium; sin ella cae al fallback de issue-links | `services/ado_provider.py:101` | `services/gitlab_provider.py:104` |
| `tracker.iterations.list` | completa | ausente | — | `services/pm/ado_pm_collector.py:36` | — |
| `tracker.milestones.list` | ausente | parcial | **GitLab:** solo se puede FILTRAR por milestone; no hay listado ni CRUD por el puerto | — | `services/gitlab_provider.py:48` |
| `tracker.labels.ensure` | ausente | parcial | **GitLab:** las etiquetas type::* se envían al crear el ítem, pero no se garantiza que existan en el proyecto (GitLab las crea implícitas, sin color ni descripción) | — | `services/gitlab_provider.py:45` |
| `tracker.rate_limit.clamp` | completa | parcial | **GitLab:** no clampea Retry-After: un valor hostil bloquea el hilo (ADO lo clampea a 30 s) | `services/ado_client.py:49` | `services/gitlab_client.py:146` |
| `tracker.auth.html_redirect` | completa | parcial | **GitLab:** ante el HTML de login devuelve el texto crudo en vez de un error tipado de auth | `services/ado_client.py:88` | `services/gitlab_client.py:164` |
| **repo.\*** | | | | | |
| `repo.file.read` | ausente | ausente | — | — | `services/gitlab_provider.py:564` |
| `repo.file.commit` | completa | completa | — | `services/ado_provider.py:146` | `services/gitlab_provider.py:592` |
| `repo.branch.list` | ausente | ausente | — | — | — |
| `repo.branch.create` | ausente | ausente | — | — | — |
| `repo.commit.list` | ausente | ausente | — | — | — |
| `repo.tag.create` | ausente | ausente | — | — | — |
| **mr.\*** | | | | | |
| `mr.create` | completa | completa | — | `services/ado_provider.py:265` | `services/gitlab_provider.py:626` |
| `mr.get` | completa | completa | — | `services/ado_provider.py:301` | `services/gitlab_provider.py:651` |
| `mr.list` | completa | completa | — | `services/ado_provider.py:405` | `services/gitlab_provider.py:705` |
| `mr.diff` | parcial | completa | **ADO:** devuelve diff_available=False y diff_text vacío: el operador abre la PR en el navegador para ver el diff | `services/ado_provider.py:429` | `services/gitlab_provider.py:735` |
| `mr.comment` | completa | completa | — | `services/ado_provider.py:460` | `services/gitlab_provider.py:764` |
| `mr.close` | completa | completa | — | `services/ado_provider.py:469` | `services/gitlab_provider.py:772` |
| `mr.merge` | completa | completa | — | `services/ado_provider.py:362` | `services/gitlab_provider.py:692` |
| `mr.approve` | ausente | completa | — | `services/ado_provider.py:476` | `services/gitlab_provider.py:779` |
| `mr.reviewers` | ausente | ausente | — | — | — |
| `mr.policies` | ausente | ausente | — | — | — |
| **ci.\*** | | | | | |
| `ci.pipeline.infer` | parcial | completa | **ADO:** la inferencia es por LLM (ado_pipeline_inference), no lee pipelines reales: misma firma, semántica distinta a la de GitLab | `services/ado_ci_provider.py:20` | `services/gitlab_ci_provider.py:32` |
| `ci.pipeline.trigger` | completa | completa | — | `services/ado_ci_provider.py:54` | `services/gitlab_provider.py:524` |
| `ci.pipeline.monitor` | completa | completa | — | `services/ado_ci_provider.py:25` | `services/gitlab_provider.py:547` |
| `ci.pipeline.definition.find` | completa | no aplica | — | `services/ado_pipeline_definitions.py:82` | `services/gitlab_provider.py:592` |
| `ci.pipeline.definition.ensure` | completa | no aplica | — | `services/ado_pipeline_definitions.py:125` | `services/gitlab_provider.py:592` |
| `ci.jobs.failed` | completa | completa | — | `services/ado_ci_logs.py:25` | `services/gitlab_ci_logs.py:14` |
| `ci.job.log` | completa | completa | — | `services/ado_ci_logs.py:49` | `services/gitlab_ci_logs.py:27` |
| `ci.variables.list` | parcial | completa | **ADO:** defecto abierto: AdoClient._request se liga SIN bind (ado_variables.py:14) y además exige una pipeline definition preexistente | `services/ado_variables.py:25` | `services/gitlab_variables.py:21` |
| `ci.variables.set` | parcial | completa | **ADO:** defecto abierto: AdoClient._request se liga SIN bind (ado_variables.py:14) | `services/ado_variables.py:47` | `services/gitlab_variables.py:46` |
| `ci.variables.delete` | parcial | completa | **ADO:** defecto abierto: AdoClient._request se liga SIN bind (ado_variables.py:14) | `services/ado_variables.py:88` | `services/gitlab_variables.py:112` |
| `ci.variables.masked` | ausente | completa | — | `services/ado_variables.py:44` | `services/gitlab_variables.py:46` |
| `ci.artifacts.list` | ausente | ausente | — | — | — |
| `ci.artifacts.download` | ausente | ausente | — | — | — |
| `ci.environments.list` | ausente | ausente | — | — | — |
| `ci.approvals` | ausente | ausente | — | — | — |
| **identity.\*** | | | | | |
| `identity.me` | completa | parcial | **GitLab:** sin caché ni mapa de identidad por proyecto (ADO cachea en ado_user_map.json) | `services/ado_identity.py:126` | `services/gitlab_provider.py:146` |
| `identity.user.find` | ausente | ausente | — | — | `services/gitlab_provider.py:94` |
| `identity.members.list` | ausente | ausente | — | — | — |
| `identity.groups.list` | ausente | ausente | — | — | — |
| `identity.token.scopes` | ausente | ausente | — | — | — |
| **events.\*** | | | | | |
| `events.webhook.inbound` | ausente | ausente | — | `services/webhooks.py:123` | `services/webhooks.py:123` |
| `events.webhook.verify` | ausente | ausente | — | `services/webhooks.py:70` | `services/webhooks.py:70` |
| **links.\*** | | | | | |
| `links.item` | parcial | completa | **ADO:** ADO no tiene módulo de deep links: solo la URL del work item, compuesta a mano | `services/ado_provider.py:69` | `services/gitlab_deep_links.py:38` |
| `links.mr` | ausente | completa | — | — | `services/gitlab_deep_links.py:47` |
| `links.commit` | ausente | completa | — | — | `services/gitlab_deep_links.py:56` |
| `links.pipeline` | ausente | completa | — | — | `services/gitlab_deep_links.py:74` |
| `links.epic` | ausente | completa | — | — | `services/gitlab_deep_links.py:65` |
