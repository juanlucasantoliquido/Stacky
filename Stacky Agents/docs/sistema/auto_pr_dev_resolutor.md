# Auto-PR del Dev Resolutor — activación y humo (plan 291)

← [INDEX](INDEX.md) · hermanos: [08-configuracion-flags](08-configuracion-flags.md) · [09-integraciones](09-integraciones.md) · [12-devops](12-devops.md)

## Qué es

Cuando el **Dev Resolutor de Incidencias** termina una ejecución en `completed` y el
operador dejó marcado *"Abrir PR"*, Stacky enumera el delta del working tree, commitea
los archivos a una rama nueva vía el proveedor del tracker (REST, sin `git push` local)
y abre la propuesta de cambio, comentando el link en la Issue.
[V: `services/incident_dev_autocommit.py:maybe_open_pr_for_incident_dev`; registrado como post-hook en `app.py:1036`]

**Nunca mergea, nunca aprueba, nunca cierra la Issue.** El MR/PR es una propuesta que
revisa el operador: `approve` y `merge` viven detrás de su botón, y `merge` además exige
la casilla de confirmación fuerte. [V: `api/pr_review.py:387-411`]

## Qué cambió con el plan 291

Hasta el plan 291, `commit_file` de GitLab **no podía crear la rama destino**: posteaba a
`/projects/:id/repository/commits` sin `start_branch`, y la API v4 de GitLab rechaza un
commit sobre una rama que no existe. Azure DevOps sí la crea desde el plan 95.
[V: `services/gitlab_provider.py:commit_file`; `services/ado_provider.py:183-190`]

Era un bug de **paridad entre proveedores**: el auto-PR funcionaba para los proyectos con
Azure DevOps y moría en los de GitLab con un `400` que no mencionaba la rama faltante.

El plan 291 agrega:

1. Una sonda de solo lectura (`branch_exists`) y un diagnóstico correcto: un `404` de rama
   ya no se traduce a *"el archivo no existe"*. **Sin opción que activar**: no escribe nada.
2. `start_branch` en el primer commit —y **solo** en el primero—, detrás de una opción que
   **nace APAGADA**.
3. Un aviso de secretos en la descripción de la propuesta de cambio (**nace ENCENDIDO**,
   solo mira) y un tapado del contenido (**nace APAGADO**, cambia lo que se guarda).

## 1 — Pasos EXACTOS para activar

> ⚠️ Con los tres valores de fábrica —crear rama **apagada**, aviso **encendido**, tapado
> **apagado**— no tenés que hacer nada y **ningún byte escrito cambia respecto de antes**.
> Lo único que cambia es que el mensaje de error del auto-PR de GitLab pasa a ser útil.

1. **Primero, el motor de GitLab.** Andá a **Diagnósticos** y confirmá que el interruptor
   **"Sistema de tickets GitLab"** (`STACKY_GITLAB_ENABLED`) está **encendido**. Sin eso no
   hay camino a GitLab: no se lista ni un ticket.
   ⚠️ **Ese interruptor NO está en el panel de opciones.** No figura en el registro de
   opciones del arnés: vive en la pantalla de Diagnósticos, en el componente
   `GitlabEngineSwitch`. [V: `frontend/src/pages/DiagnosticsPage.tsx:334`; `services/tracker_provider.py:133-136` lanza `TrackerConfigError`]
2. **Después, el panel de opciones.** Abrilo y andá a la categoría **"Capacidades opt-in"**.
   [V: `services/harness_flags.py:103` — `CategorySpec("capacidades_optin", "Capacidades opt-in", ...)`]
3. Confirmá que **"Abrir PR al resolver incidencias"** (`STACKY_INCIDENT_DEV_PR_ENABLED`)
   está **encendido** (viene encendido de fábrica), y también su master
   `STACKY_INCIDENT_DEV_RESOLVER_ENABLED`, que también nace encendido.
   [V: `config.py:1212-1213` y `config.py:1220-1221`, los dos con default `"true"`]
4. Encendé **"Crear la rama del fix cuando no existe (GitLab)"**
   (`STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`).
   **Este es el paso que autoriza a Stacky a escribir en tu GitLab.**
   ⚠️ **Y alcanza a más que a las incidencias.** La opción vive dentro de `commit_file`, que
   tiene **tres** consumidores: el auto-PR, el editor de pipelines y el generador de
   pipelines. Con esto encendido, el armado de pipelines también puede crear su propia rama
   `feature/pipeline-<nombre>`, que hoy le falla.
   [V: `services/incident_dev_autocommit.py:88`, `api/pipeline_editor.py:285`, `api/pipeline_generator.py:97,122`]
5. *(Opcional)* Si querés que además **tape** lo que parezca una clave dentro de los
   archivos, encendé **"Tapar el secreto dentro del archivo antes de subirlo"**
   (`STACKY_AUTOCOMMIT_REDACT_ENABLED`). **Nace apagada a propósito**: el aviso viene
   encendido, el reemplazo del contenido lo decidís vos, porque modifica lo que queda
   guardado en el repositorio de la empresa.
6. El cambio **aplica en caliente**: el endpoint escribe el valor sobre la configuración
   viva además de persistirlo. **No hace falta reiniciar.** [V: `api/harness_flags.py:150-153`]

## 2 — El humo, paso a paso, y qué mirar

> ⚠️ **Este humo es TRABAJO TUYO y está FUERA DEL ALCANCE del plan 291.** Ninguna fase lo
> automatiza ni lo verifica: requiere credenciales reales y toca el GitLab de la empresa.
> El diagnóstico del plan es **por código y por contrato de la API**; el ciclo completo
> issue → commit → MR **no se probó nunca de punta a punta**.

1. Elegí un ticket de un proyecto cuyo `issue_tracker.type` sea `gitlab` (hoy, **RIPLEY**).
2. Tocá **"Resolver con agente"** dejando el checkbox **"Abrir PR"** marcado (viene premarcado).
   [V: `frontend/src/incidents/incidentDevPrModel.ts:8`]
3. Esperá a que la ejecución termine en `completed`.
4. Qué mirar, en orden:

| Dónde | Qué tiene que aparecer | Si NO aparece |
|---|---|---|
| El comentario en la Issue de GitLab | `🚀 PR abierto automáticamente con el fix y los tests: <url>` | Si dice `⚠️ No se pudo abrir el PR automático: ...`, **el mensaje trae la causa**. Si dice que la rama no existe y la creación está apagada → volvé al paso 4 de la sección 1 |
| GitLab → Repositorio → Ramas | una rama llamada `stacky/incidencia-<ticket>-exec-<ejecución>` | Sin rama, el commit no llegó |
| GitLab → Merge Requests | un MR en estado `opened` desde esa rama hacia la rama principal | — |
| La descripción del MR | **Cambios de código**, **Tests incluidos**, **Origen del working tree**, y —si hubo— la sección **⚠️ Revisá estos archivos antes de integrar** | Si aparece esa sección, **los archivos se subieron TAL CUAL** salvo que hayas encendido el tapado del paso 5. Miralos antes de integrar |
| El MR | **NO** debe estar mergeado ni aprobado | Si lo está, es un bug grave: reportalo |

5. **Recién después de ver ese MR `opened`, el KPI K1 del plan 291 pasa a ser medible.**

### Sobre el KPI K1

`K1: NO MEDIBLE — requiere que el operador encienda STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED
y ejecute el humo de esta sección contra su GitLab. Ninguna fase del plan 291 lo mide.`

Escribir *"K1 = 0, meta no alcanzada"* sería falso: **0 es el valor esperado y correcto**
mientras la opción esté apagada.

## 3 — Cómo apagarlo

Apagá **"Crear la rama del fix cuando no existe (GitLab)"**. Vuelve el comportamiento previo
al plan: Stacky no crea ninguna rama en GitLab y avisa en la Issue cuál era la rama que
faltaba. **Las ramas y MRs ya creados NO se borran** — eso es decisión tuya, a mano.

## 4 — Lo que NO se puede prometer

| Afirmación tentadora | Por qué es falsa |
|---|---|
| *"Con la opción apagada, cero escritura en GitLab"* | **Falso a nivel sistema.** Con la opción apagada `commit_file` lanza un error, el camino de error lo captura y **postea un comentario en la Issue de GitLab**. Cero escritura **en el repositorio**; el tracker sí recibe un comentario. Eso ya pasaba antes del plan 291. [V: `services/incident_dev_autocommit.py:106-112`] |
| *"El aviso de secretos detecta todo"* | **Falso, y es deliberado.** Solo se buscan seis formas que **no pueden confundirse con código**: `AKIA…`, `ghp_…`, `glpat-…`, `xox…`, `Authorization: Bearer …` y bloques `BEGIN…END PRIVATE KEY`. Una contraseña en texto plano o la clave de un proveedor no listado **no se detecta ni se avisa**. Entre avisar de menos y romper el arreglo, se eligió avisar de menos: un detector agresivo destruía código legítimo (`password = cfg.get("db_password")` salía como `password = ***REDACTED***`). |
| *"El ciclo está probado de punta a punta"* | **Falso.** Todas las pruebas del plan 291 corren contra dobles, sin una sola llamada de red. La única validación end-to-end posible es el humo de la sección 2, y es tuya. |
