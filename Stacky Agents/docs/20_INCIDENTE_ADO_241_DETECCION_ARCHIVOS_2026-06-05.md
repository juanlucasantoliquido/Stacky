# SSD - Incidente ADO-241: deteccion automatica de pending-task.json

## Situacion

En RSPACIFICO, el agente FunctionalAnalyst genero archivos para el Epic ADO-241
(`EP-26 - Busqueda de Cliente - Simplificacion de Filtros y Nomenclatura`), pero
Stacky Agents no creo la Task automaticamente. Al arrastrar manualmente los
mismos archivos desde el desatascador, la Task se creo correctamente.

## Senales observadas

- Log del deploy, `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-06-05.log`:
  - `20:39:47`: Stacky abre el agente para `ado_id=241`.
  - `20:43:36`: el watcher llama `create_child_task` con `ado_id=26` y path
    `Agentes/outputs/epic-26/.../pending-task.json`.
  - `20:43:37`: ADO responde `ADO_PARENT_NOT_FOUND` para work item 26.
  - `20:44:48`: el flujo manual llama `create_child_task` con `ado_id=241` y path
    `Agentes/outputs/epic-241/.../pending-task.json`.
  - `20:44:55`: se confirma `task_ado_id=246`.
- Archivo automatico real:
  - `C:/desarrollo/GIT/RS/RSPACIFICO/Agentes/outputs/epic-26/.../pending-task.json`
  - contiene `epic_id: "26"` y no contiene `parent_id`.
- Archivo manual re-stageado por el desatascador:
  - `C:/desarrollo/GIT/RS/RSPACIFICO/Agentes/outputs/epic-241/.../pending-task.json`
  - contiene `epic_id: "241"`, `parent_id: 241`, `status: "consumed"` y
    `task_ado_id: 246`.

## Diagnostico

La causa raiz no fue ADO ni el endpoint de creacion manual. El agente confundio
la etiqueta humana del titulo (`EP-26`) con el `System.Id` real de ADO (`241`) y
genero el contrato bajo `epic-26` con `epic_id="26"`.

El flujo automatico usaba el sufijo de la carpeta `epic-*` como fuente del ADO
padre. Por eso intento crear la Task bajo ADO-26, que no existe. El flujo manual
funciono porque `rescue-artifact` normalizo el mismo payload a `epic_id=241` y
`parent_id=241` antes de llamar a `create-child-task`.

## Solucion aplicada

- `services/output_watcher.py`
  - Resuelve un `effective_epic_ado_id` antes del auto-create.
  - Corrige carpetas mal nombradas usando, en orden:
    1. `parent_id` / `epic_ado_id` / `parent_ado_id` si el JSON lo declara.
    2. Titulo local del ticket: `EP-26...` puede mapear a ADO-241 si no existe
       un ticket ADO-26.
    3. Ventana temporal de ejecucion funcional asociada al Epic.
  - Si corrige `epic-26 -> ADO-241`, llama el endpoint con
    `source_epic_ado_id` y `allow_epic_id_mismatch=true`.
- `api/tickets.py`
  - `/pending-tasks` y el desatascador ahora pueden mostrar archivos `epic-26`
    para ADO-241 por match de titulo `EP-26`, aunque el JSON no tenga `parent_id`.
  - `create-child-task` acepta mismatch de `epic_id` solo cuando viene del
    watcher con autorizacion explicita y normaliza el JSON a `epic_id=<ADO real>`
    y `parent_id=<ADO real>` antes de crear.
  - Antes de tocar ADO, detecta si ya existe otro `pending-task.json` equivalente
    del mismo ADO/RF con `status=consumed` y `task_ado_id`; en ese caso marca el
    archivo original como idempotente para evitar duplicar la Task.
- `FunctionalAnalyst.agent.md`
  - Version `2.0.3`.
  - El prompt exige usar `epic_ado_id` / `System.Id` real como `{ADO_EPIC_ID}` y
    escribir `parent_id`.

## Validacion

- `pytest Stacky Agents/backend/tests/test_create_child_task_endpoint.py`: 25 passed.
- `pytest Stacky Agents/backend/tests/test_output_watcher.py`: 30 passed.
- `pytest Stacky Agents/backend/tests/test_unblocker_board.py`: 10 passed.
- `pytest Stacky Agents/backend/tests/test_context_enrichment.py Stacky Agents/backend/tests/test_functional_epic_context_injection.py`: 15 passed.
- `pytest Stacky Agents/backend/tests/test_functional_analyst_extraction_rules.py`: 7 passed.
- Corrida combinada de modulos tocados: 88 passed.
- Verificacion read-only contra artifacts reales de Pacífico:
  - `_scan_pending_tasks_for_epic(..., 241)` devuelve el pendiente original en
    `Agentes/outputs/epic-26/.../pending-task.json`.
  - `_resolve_effective_epic_ado_id(source_epic_ado_id=26, ...)` devuelve
    `(241, reason='ticket_title_ep_label')`.
  - `_find_equivalent_consumed_pending_task(..., ado_id=241, current=epic-26...)`
    devuelve el archivo consumido en `epic-241` con `task_ado_id=246`.
