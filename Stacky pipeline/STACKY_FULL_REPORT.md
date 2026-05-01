STACKY — Informe completo
=========================

**Resumen ejecutivo**
- **Qué es:** Stacky es un pipeline de automatización para tickets que orquesta 3 etapas principales (PM → Dev → QA) integrando un panel web, agentes LLM (invocados por `copilot_bridge`), integración con Mantis (vía Playwright), operación sobre SVN (status/diff/export), y generación automática de paquetes de despliegue (ZIP) y notas.
- **Objetivo:** acelerar el ciclo de análisis → implementación → validación, reducir errores manuales (commits, snapshot, notas en Mantis) y facilitar trazabilidad (archivos en la carpeta del ticket, snapshots, logs).

**Dónde está el código (archivos clave)**
- **UI / API / Orquestador:** [tools/mantis_scraper/dashboard_server.py](tools/mantis_scraper/dashboard_server.py)
- **Generación de prompts / plantillas:** [tools/mantis_scraper/prompt_builder.py](tools/mantis_scraper/prompt_builder.py)
- **Estados del pipeline:** [tools/mantis_scraper/pipeline_state.py](tools/mantis_scraper/pipeline_state.py)
- **Integración Mantis (Playwright):** [tools/mantis_scraper/mantis_updater.py](tools/mantis_scraper/mantis_updater.py)
- **Generador de paquetes de deploy:** [tools/mantis_scraper/deploy_packager.py](tools/mantis_scraper/deploy_packager.py)
- **Operaciones SVN (wrappers):** [tools/mantis_scraper/svn_ops.py](tools/mantis_scraper/svn_ops.py)  (utilizado por `deploy_packager`)
- **Bridge hacia LLM / agents:** [tools/mantis_scraper/copilot_bridge.py](tools/mantis_scraper/copilot_bridge.py)
- **Gestión de proyectos y configuración:** [tools/mantis_scraper/project_manager.py](tools/mantis_scraper/project_manager.py)
- **Historial de deploys:** [tools/mantis_scraper/deploy_history.py](tools/mantis_scraper/deploy_history.py)

**Estructura de carpetas y archivos por ticket**
Cada ticket tiene su carpeta con la siguiente convención mínima:
- `INC-{id}.md` o `INCIDENTE.md` — información original del ticket
- `ANALISIS_TECNICO.md` — salida del PM (causa raíz)
- `ARQUITECTURA_SOLUCION.md` — diseño técnico sugerido
- `TAREAS_DESARROLLO.md` — tareas/desglose para el dev
- `DEV_COMPLETADO.md` — resultado del Developer (archivos, resumen, SQL ejecutado)
- `SVN_CHANGES.md` — snapshot svn (estado + diff) capturado post-dev
- `TESTER_COMPLETADO.md` — resultados de QA
- `snapshots/` — contiene `{stage}_diff.patch` y `{stage}_files.txt`
- Otros artefactos: `COMMIT_MESSAGE.txt`, `MANTIS_UPDATE.json`, `*_ERROR.flag` (por fallo)

**Flujo general (lógica de negocio)**
1. El PM es invocado (vía UI ó watcher) → genera `ANALISIS_TECNICO.md`, `ARQUITECTURA_SOLUCION.md`, `TAREAS_DESARROLLO.md` y marca `pm_completado`.
2. El Developer es invocado con el prompt de Dev → modifica workspace local (SVN), genera `DEV_COMPLETADO.md` y, cuando finaliza, el watcher guarda snapshot `{dev}_diff.patch` y `{dev}_files.txt` en la carpeta del ticket.
3. El QA es invocado y realiza tests; si aprueba, se llama a `update_ticket_on_mantis()` para publicar nota y opcionalmente cerrar el ticket.
4. `DeployPackager` recopila archivos modificados (prioridad: `svn diff --summarize` → `SVN_CHANGES.md` → parse `DEV_COMPLETADO.md`), resuelve binarios (.dll/.exe) y crea ZIP de deploy + rollback.

**API pública (endpoints principales)**
(implementados en `dashboard_server.py`)
- `POST /api/mantis_confirm/<ticket_id>` — publica nota en Mantis (PM/QA) (ahora activo)
- `POST /api/reinvoke/<ticket_id>` — reintenta invocar el agente para el estado actual
- `POST /api/send_correction` — guarda `CORRECCION_DEV.md` y reinvoca Dev
- `GET /api/projects`, `GET|POST /api/active_project` — gestión de proyectos
- `GET /api/stages` — retorna definición de etapas
- `GET /api/prompts/<role>` / `POST /api/prompts/<role>` — leer/guardar prompts por rol
- `GET /api/gen_prompts/<ticket_id>` — genera prompts compactos para Dev/QA desde el contexto
- `GET /api/diff/<ticket_id>/<stage>` — entrega diff (snapshot → SVN_CHANGES.md → live SVN)
- `POST /api/capture_snapshot/<ticket_id>/<stage>` — fuerza captura y guardado del diff
- `GET|POST /api/pipeline_note/<ticket_id>` — nota pre-pipeline (NOTA_PM.md)
- `POST /api/capture_snapshot/<ticket_id>/<stage>` — comando para capturar snapshot manualmente

Referencias directas a funciones y comportamiento (ver code):
- `api_diff` normaliza sub-stages (por ejemplo `dev_impl`, `dev_doc`) al padre para buscar snapshot.
- `api_capture_snapshot` llama `_save_svn_snapshot(folder, stage, workspace)` — guarda `snapshots/{stage}_diff.patch`.

**Prompting y agentes**
- `prompt_builder.py` construye prompts para roles `pm`, `dev`, `tester`.
- Cada prompt contiene 3 fases internas (no se invocan como sub-agentes por defecto):
  - PM: INVESTIGAR → DISEÑAR → PLANIFICAR
  - DEV: LOCALIZAR → IMPLEMENTAR → DOCUMENTAR
  - QA: CODE REVIEW → PRUEBAS FUNCIONALES → VEREDICTO
- También existen funciones preparadas para sub-agentes (`pm_inv`, `pm_arq`, `pm_plan`, `dev_loc`, `dev_impl`, `dev_doc`, `qa_rev`, `qa_exec`, `qa_arb`) si se desea invocarlos separadamente.
- `copilot_bridge.invoke_agent(prompt, agent_name, project_name)` centraliza la invocación (mantiene abstracción del proveedor LLM/agent).

**Detalles técnicos importantes**
- `DeployPackager._get_modified_files()` prioridad: `svn diff --summarize` → `SVN_CHANGES.md` → parse `DEV_COMPLETADO.md` (regex mejorada para detectar rutas en listas y backticks).
- Resolución de binarios: `_resolve_dlls()` busca `.csproj` ascendiendo hasta 6 niveles y luego intenta ubicar binarios en `bin/`, `bin/Release`, `bin/Debug`, y rutas típicas `net48`, `net472`, `net6.0`, `net8.0`.
- Rollback: `_build_rollback_zip()` usa `svn_ops.export_prev_revision()` para exportar binarios previos y empaquetarlos.
- Mantis: `mantis_updater.py` usa Playwright y `auth.json` (cookies SSO) para publicar notas y cambiar estado. Funciones relevantes: `_build_pm_note()`, `_build_note()` y `_post_note()`.

**Dependencias y requisitos de ejecución**
- Python 3.8+ (revisar `python` del entorno).
- Paquetes Python: `flask`, `playwright` (y sus navegadores), plus utilidades (requests, etc.).
- Herramientas del sistema: `svn` en PATH, y para builds C# el MSBuild/Visual Studio instalado si se quiere compilar proyectos.
- Credenciales Mantis: `auth/auth.json` con cookies guardadas (Playwright session).

**Cómo levantar el stack localmente (quick-start)**
1. Instalar dependencias Python: `pip install -r requirements.txt` (si no existe, instalar `flask playwright` manualmente).
2. Instalar navegadores Playwright: `playwright install`.
3. Configurar proyecto activo con `api/init_project` o editar fichero de configuracion del proyecto.
4. Ejecutar: `python tools/mantis_scraper/dashboard_server.py` y abrir `http://localhost:5050`.

**Formato esperado de artefactos creados por agentes**
- `DEV_COMPLETADO.md`: debe incluir 'Archivos modificados' en formato de lista (preferible backticks o rutas en líneas) y un breve `Resumen` con lo realizado. Esto alimenta `DeployPackager`.
- `TAREAS_DESARROLLO.md`: contiene criterios de aceptación, pasos y `TXXX` headings para tareas.
- `TESTER_COMPLETADO.md`: debe incluir `APROBADO`/`RECHAZADO` y secciones con `Veredicto` / `Resultado`.

**Estado actual y correcciones recientes (importante para la IA que herede el proyecto)**
- Se corrigió condición de carrera PM→DEV (watcher / locks).
- `api_mantis_confirm` reactivado y `mantis_updater._build_note()` ampliado para incluir problema, solución, archivos y commit.
- `deploy_packager._parse_dev_completado()` mejorado para capturar rutas en listas (`- ruta/archivo.cs`) y backticks.
- `api_diff` ahora acepta sub-stages y busca `SVN_CHANGES.md` antes del diff live.
- Proyecto RecBatchSvc: `TargetFrameworkVersion` actualizado a `v4.7.2` para resolver dependencias y permitir generar `RecBatchSvc.exe`.

**Peticiones útiles para la otra IA (prompt sugerido)**
- "Lee los archivos listados y genera:
  1) Diagrama de arquitectura (componentes + flujos de datos). 
  2) Lista de endpoints con inputs/outputs y ejemplos. 
  3) Diagrama de estados del pipeline y transiciones automáticas. 
  4) Un README operativo con comandos para ejecutar localmente."

Comandos útiles para inspección rápida del repo (copiar/pegar):

```powershell
# listar endpoints en dashboard_server
Select-String -Path tools/mantis_scraper/dashboard_server.py -Pattern "@app.route" -SimpleMatch

# ver funciones prompt
Select-String -Path tools/mantis_scraper/prompt_builder.py -Pattern "def build_" -SimpleMatch

# buscar referencias a SVN/Deploy
Select-String -Path tools/mantis_scraper/*.py -Pattern "svn\_|DeployPackager|update_ticket_on_mantis" -SimpleMatch
```

**Sugerencia: diseño de un "Game-Changer Agent" (CommitAgent)**
- Auto-commit y push seguro al completar QA: lee `DEV_COMPLETADO.md`, valida `SVN_CHANGES.md`, arma `COMMIT_MESSAGE.txt`, ejecuta `svn add` para archivos nuevos, `svn commit` y actualiza `COMMIT_MESSAGE.txt` con número de revisión. Opcional: correr `DeployPackager.build()` y subir ZIP al storage.
- Beneficio: elimina pasos manuales y errores humanos al publicar cambios.

**Tareas recomendadas para entregar a otra IA**
- Generar `README.md` completo con el contenido de este informe (incluyendo pasos reproducibles).
- Generar diagramas (PlantUML o Mermaid) de la pipeline y de la arquitectura.
- Revisar prompts en `tools/mantis_scraper/prompt_builder.py` y proponer mejoras (prompts más cortos/resumidos y templates para sub-fases).

---

Archivo generado: `tools/mantis_scraper/STACKY_FULL_REPORT.md`

Si querés, puedo:
- 1) Comitear y pushear este informe (lo hago ahora),
- 2) Implementar el `CommitAgent` (prototipo), o
- 3) Generar un `README.md` más resumido y diagramas para pasar a la otra IA.

Decime qué querés que haga a continuación.