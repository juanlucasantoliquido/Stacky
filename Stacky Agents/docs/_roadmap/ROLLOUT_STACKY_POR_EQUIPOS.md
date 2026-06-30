# Rollout de Stacky Agents por equipos — Plan de adopción organizacional

> Documento de propuesta organizacional. **No** introduce features nuevas: todo lo que
> sigue está anclado en lo que el código de Stacky Agents hace **hoy** (con
> `archivo:línea`). Donde el modelo organizacional choca con una limitación real del
> código, se dice explícitamente y se propone el work-around con lo que ya existe.

## Resumen (TL;DR)

Stacky se despliega como un **build congelado por máquina** y es **mono-operador sin
identidad real** (no hay login/roles; `current_user` es un header sin validar). Por eso
el modelo "un equipo por vez, con un Referente local responsable" se implementa
físicamente: **1 equipo = 1 deploy = 1 máquina = 1 Referente**, no como roles dentro de
una instancia compartida. El Equipo de Expertos entrega capacidades nuevas por el
pipeline interno de planes (proponer → criticar → implementar → supervisar), siempre con
**flags default-OFF** y **conformance de 3 runtimes**, y esas capacidades llegan a cada
equipo como una **nueva versión del build** (redeploy que preserva datos y config). El
flujo estrella brief → épica → publicación autónoma en el tracker **solo funciona con el
runtime `claude_code_cli`**.

---

## Capacidades REALES hoy (evidencia que habilita o limita el modelo)

| # | Capacidad / límite real | Evidencia (`archivo:línea`) | Impacto en el modelo |
|---|---|---|---|
| 1 | **Sin auth / sin roles**: `current_user` es el header `X-User-Email` o `dev@local`, sin validar | `backend/api/_helpers.py:4-5` | "Referente responsable" NO es enforceable por la app: es convención humana. Aislamiento = por máquina, no por rol |
| 2 | **3 runtimes** soportados: `github_copilot`, `codex_cli`, `claude_code_cli` | `backend/api/agents.py:336`; `frontend/src/types.ts:10` | El Referente elige runtime por UI; cada uno tiene prerequisitos de credenciales propios en la máquina |
| 3 | **Default de runtime**: frontend persiste `claude_code_cli`; el backend, si no llega runtime, cae a `github_copilot` (con warning) | `frontend/src/store/workbench.ts:79`; `backend/api/agents.py:351-359` | El default operativo es Claude CLI; el fallback del backend es defensivo, no la ruta normal |
| 4 | **Autopublicación Epic/Issue SOLO con `claude_code_cli`**: rechazo 400 explícito para los otros | `backend/api/agents.py:599-608`; `backend/services/claude_code_cli_runner.py:1281-1505` | El flujo brief→épica→tracker autónomo exige Claude CLI en la máquina del Referente |
| 5 | **Multi-proyecto, pero un solo activo a la vez** (`active_project.json`) | `backend/project_manager.py:39-100` | Un deploy puede tener varios proyectos del mismo equipo, pero está diseñado alrededor de un proyecto activo |
| 6 | **Config por proyecto** en `projects/{NOMBRE}/config.json` + `auth/*.json` (incluye `client_profile`, `workspace_root`, `issue_tracker`, `docs_paths`) | `backend/project_manager.py:105-181` | Cada equipo se modela como un "proyecto" con su tracker, repo y catálogo |
| 7 | **Credenciales cifradas con DPAPI**, ligadas al usuario/máquina local de Windows | `backend/project_manager.py:451-504` (`set_encrypted_secret`, `_DPAPI_B64_PREFIX`) | Las credenciales NO son portables entre máquinas; cada Referente las re-ingresa por UI |
| 8 | **Config global** (defaults para nuevos proyectos) se escribe en `backend/.env` | `backend/api/global_config.py:1-39` | El `.env` es por máquina/deploy; no hay separación de config por usuario |
| 9 | **Harness flags configurables por UI** (no solo env var) | `backend/api/harness_flags.py`; `backend/services/harness_flags.py` (`FLAG_REGISTRY`) | El Referente ajusta el comportamiento sin tocar archivos ni redeployar |
| 10 | **Deploy congelado** (`is_frozen`) con datos fuera del binario | `backend/runtime_paths.py:26-63` (`data_dir`, `projects_dir`, `app_root`) | Los fixes NO se hot-reload: llegan como build nuevo. Datos/config sobreviven al redeploy |
| 11 | **El build hornea el arnés** (`.env.example` + `harness_defaults.env`) en `backend/.env` en CADA deploy | `deployment/build_release.ps1:574-590`; `deployment/export_harness_defaults.py:33-67` | El Equipo de Expertos fija defaults seguros del arnés que viajan con cada versión |
| 12 | **Outputs del agente** van al `workspace_root` del proyecto activo (repo del cliente), no al deploy | `backend/runtime_paths.py:99-136` (`repo_root`) | Los artefactos quedan en la máquina/repo del equipo; refuerza "1 máquina por equipo" |
| 13 | **Trackers soportados** vía factory: Azure DevOps, GitLab, Jira, Mantis | `backend/services/tracker_provider.py`; `ado_provider.py`; `gitlab_provider.py`; `backend/project_manager.py:270-368,541-577` | Cada equipo se conecta a su tracker real; no hay que cambiar de herramienta |
| 14 | **Pipeline de planes** del Equipo de Expertos: proponer → criticar → implementar → supervisar | skills en `.claude/skills/` + agentes Stacky | Forma reproducible de sumar capacidades sin improvisar |
| 15 | **Conformance de 3 runtimes** y golden gates protegen contra regresiones | `backend/tests/conformance/test_runtime_conformance.py`; `test_tracker_provider_conformance.py` | Garantía de que una feature nueva no rompe a los equipos en producción |
| 16 | **Human-in-the-loop**: `needs_review`, cancelación de runs, veredicto humano | `backend/services/claude_code_cli_runner.py:1358`; panel de salud operativa (plan 46) | El Referente siempre tiene la última palabra; no hay autonomía que lo reemplace |

---

# Parte 1 — Plan de rollout paso a paso

Modelo físico (consecuencia directa de las capacidades #1, #5, #7, #8, #10):
**cada equipo recibe su propio deploy de Stacky en la máquina de su Referente.** No se
comparte una instancia entre equipos, porque no hay identidad para separar quién es
quién dentro de la app, y la config sensible (flags, `.env`, proyecto activo, DB) es por
máquina.

Notación de cada paso: **Responsable** · **Precondición** · **Pasos** · **Hecho cuando**.

> **Contexto de partida:** hoy la organización usa **SVN** como repositorio y **Mantis**
> como gestión de proyectos/tickets (el propio Stacky vive en SVN:
> `https://dev.ais-int.net/svn/rs/Agentes/Stacky Agents`). El destino es **GitLab** como
> repositorio **y** gestión de proyectos, que Stacky ya soporta como TrackerProvider
> (`backend/services/gitlab_provider.py`). Por eso el rollout arranca con una fase de
> migración previa a cualquier despliegue por equipo. El detalle de endpoints/API de la
> migración está en `API_ENDPOINTS_MANTIS_GITLAB.md` (mismo directorio).

---

### Fase -1 — Migración SVN + Mantis → GitLab (previa a todo el rollout)

- **Responsable:** Equipo de Expertos (diseña y corre el migrador) + Referente de cada equipo (valida sus datos).
- **Precondición:** instancia GitLab disponible (self-managed o SaaS) con acceso por token; acceso de lectura a SVN y a la API REST de Mantis.
- **Pasos (resumen accionable; el detalle fino va en `API_ENDPOINTS_MANTIS_GITLAB.md`):**
  1. **Migrar el repositorio (SVN → Git/GitLab):** con `git svn clone` / `svn2git`,
     preservando historia y autores (tabla `authors.txt`: usuario SVN → nombre+email
     GitLab). Aplica tanto al **repo del propio Stacky** como a los **repos de cada
     equipo**. Verificación: revisiones SVN vs commits Git y un `git log` de control.
  2. **Migrar la gestión de proyectos (Mantis → GitLab Issues/Epics):** mediante un
     **proceso automatizado** que lee de la API de Mantis y crea en la API de GitLab
     (ver detalle abajo).
  3. **Repuntar la config de Stacky:** cada proyecto pasa su `issue_tracker.type` de
     `mantis` a `gitlab` por UI y carga el token GitLab; a partir de ahí el flujo normal
     (brief→épica→tracker) corre contra GitLab **sin cambios de código**.

#### Proceso automatizado de migración de tickets Mantis → GitLab (lo más importante)

Un job de migración del Equipo de Expertos que **reutiliza los patrones de auth y cliente
HTTP que Stacky ya tiene**, con estas piezas:

- **Lado CREAR (GitLab): se reutiliza el TrackerProvider real de Stacky.**
  `GitLabTrackerProvider` (`gitlab_provider.py`) ya expone todo lo necesario:
  `create_item` (issue + labels `type::`), `post_comment` (notas), `upload_attachment` +
  `link_attachment` (adjuntos), y `_link_parent` (jerarquía: epics nativos GitLab si hay
  licencia, con **fallback automático a issue-links** si no — `gitlab_provider.py:99-125`).
- **Lado LEER (Mantis): NO hay un TrackerProvider de Mantis** — el factory lo rechaza a
  propósito (`tracker_provider.py:122-124`). Se reutiliza el cliente legacy
  `MantisClient` (`mantis_client.py`) para auth + HTTP, pero **con una salvedad dura**:
  su `fetch_open_issues()` **descarta los tickets resueltos/cerrados** (status 80/90,
  `mantis_client.py:269-297`). Para una migración **completa** el migrador debe llamar al
  endpoint REST `GET /api/rest/issues` **sin** ese filtro (paginando todas las páginas,
  incluidos cerrados). Lo mismo para relaciones/jerarquía y adjuntos binarios, que el
  cliente de Stacky hoy no extrae (ver gaps abajo).
- **Mapeo de campos:** estado (Mantis status → GitLab `open/closed` + label;
  `_STANDARD_STATUS_IDS` y `_RESOLVED_STATUS_IDS` de `mantis_client.py` son la base),
  prioridad (Mantis priority → label; `_PRIORITY_MAP` `mantis_client.py:57-64`), asignado
  (Mantis handler → username GitLab vía **tabla de mapeo de usuarios** que el migrador
  debe proveer, porque los nombres no coinciden), comentarios (notes → notes), adjuntos
  (descarga binaria desde Mantis `/files/{id}` → subida a GitLab `/uploads`), relaciones
  y jerarquía (Mantis `relationships` → epic/issue-links de GitLab).
- **Idempotencia (re-correr sin duplicar):** el migrador incrusta un **marcador de
  procedencia** `[[mantis:#<id>]]` en la descripción del issue GitLab; antes de crear,
  busca ese marcador (`fetch_open_items` con `search`, o el patrón `comment_exists` /
  `find_child_by_marker` ya existente) y **omite** los que ya existen.
- **Procedencia (limitación de API, no de Stacky):** GitLab fija autor=token y fecha=now
  al crear; el autor/fecha originales de Mantis **no son seteables por API**, así que se
  preservan como cabecera de procedencia en el cuerpo ("Creado originalmente por X el
  FECHA en Mantis #N").
- **Verificación post-migración:** contar tickets origen (Mantis, todos los estados) vs
  issues creados en GitLab; reconciliar por marcador `[[mantis:#<id>]]` y reportar
  faltantes/duplicados.

- **Hecho cuando:** los repos están en GitLab con historia/autores preservados; el conteo
  Mantis-total ↔ GitLab-creados cuadra por marcador; y un proyecto de prueba ya tiene su
  `issue_tracker.type=gitlab` y corre un brief→épica end-to-end contra GitLab.

---

### Fase 0 — Estandarización (una sola vez, antes del primer equipo)

- **Responsable:** Equipo de Expertos.
- **Precondición:** repo de Stacky Agents con el pipeline de planes operativo y el build reproducible.
- **Pasos:**
  1. Congelar una **versión base estable** del build (`deployment/build_release.ps1`), que ya hornea el arnés por defecto en `backend/.env` (#11).
  2. Definir el **paquete de despliegue estándar**: el deploy frozen + un checklist de alta de proyecto + plantillas de `client_profile` por tracker (`backend/services/client_profile_default_templates.py`).
  3. Fijar el **runtime estándar para equipos que autopublican** = `claude_code_cli` (única ruta de autopublicación, #4).
  4. Definir los **defaults de arnés** que viajan con el build: todo lo riesgoso queda default-OFF (#9, #11).
- **Hecho cuando:** existe un build versionado + checklist de despliegue + plantilla de `client_profile` por tipo de tracker, y está documentado qué runtime usa cada tipo de equipo.

---

### Fase 1 — Selección del equipo y designación del Referente

- **Responsable:** Equipo de Expertos + liderazgo de la organización.
- **Precondición:** Fase 0 cerrada.
- **Pasos:**
  1. Elegir **un (1) equipo** para esta iteración (rollout secuencial, no masivo).
  2. Designar **un (1) Referente** local: será el dueño humano del Stacky de su equipo (la app no puede enforzar esto, #1; es una decisión organizacional).
  3. Relevar la "ficha del equipo": tracker real (ADO/GitLab/Jira/Mantis, #13), `workspace_root` (repo del equipo), `docs_paths` (técnica/funcional), y el catálogo de procesos del producto.
- **Hecho cuando:** existe la ficha del equipo con tracker, `workspace_root`, `docs_paths` y runtime elegido; el Referente está nombrado y disponible.

---

### Fase 2 — Despliegue en la máquina del Referente

- **Responsable:** Equipo de Expertos (instala) + Referente (aporta su máquina y credenciales).
- **Precondición:** máquina Windows del Referente con (a) credenciales del runtime elegido (suscripción/login de Claude para `claude_code_cli`; o Codex/Copilot según el caso) y (b) acceso al tracker del equipo.
- **Pasos:**
  1. Instalar el **deploy frozen** estándar en la máquina del Referente y arrancar el backend (carga `backend/.env` horneado, #11).
  2. Dar de alta el **proyecto del equipo por UI** → crea `projects/{NOMBRE}/config.json` (`initialize_*_project`, `project_manager.py:270-368,541-577`), que ya siembra el `client_profile` default del tracker (`project_manager.py:161-169`).
  3. Cargar las **credenciales del tracker por UI** (quedan cifradas con DPAPI, ligadas a esta máquina, #7) y correr el **test-connection** (`api/global_config.py`).
  4. Setear `workspace_root` y `docs_paths` del equipo (#6); marcarlo como **proyecto activo** (`active_project.json`, #5).
  5. Cargar/ajustar el **process_catalog y el client_profile** del equipo por UI (editor de perfil de cliente).
- **Hecho cuando:** el proyecto del equipo está activo, el test-connection del tracker pasa, y un **run de prueba brief → épica publica realmente** en el tracker del equipo (valida #4 end-to-end).

> **Por qué una máquina por equipo:** la config sensible (proyecto activo, flags, `.env`,
> DB SQLite, credenciales DPAPI) es por máquina/deploy (#1, #5, #7, #8, #10). Compartir
> un deploy entre equipos haría que se pisen el proyecto activo, las flags y las
> credenciales.

---

### Fase 3 — Capacitación del Referente

- **Responsable:** Equipo de Expertos (capacita) → Referente (aprende).
- **Precondición:** Fase 2 cerrada (deploy operativo con un run real exitoso).
- **Pasos:**
  1. Enseñar el **flujo end-to-end**: brief → épica grounded (process_catalog + technical_master) → autopublicación en el tracker; descomposición épica → hijos; historial de ejecuciones; panel de salud operativa.
  2. Enseñar la **configuración por UI**: `client_profile`, `process_catalog`, harness flags (#9), y el selector de modelo/effort por run.
  3. Enseñar el **human-in-the-loop**: leer `needs_review`, cancelar runs colgados, y el veredicto humano (#16).
  4. Enseñar el **mantra mono-operador** (#1): quien tenga acceso a la UI de ese deploy es, de hecho, el operador. La responsabilidad del Referente es organizacional, no técnica → cuidar el acceso a la máquina.
- **Hecho cuando:** el Referente ejecuta el flujo completo **sin asistencia**, sabe interpretar `needs_review`, y ajusta al menos una flag por UI por su cuenta.

---

### Fase 4 — Operación asistida (acompañamiento)

- **Responsable:** Referente (opera) + Equipo de Expertos (soporte cercano, on-call).
- **Precondición:** Fase 3 cerrada.
- **Pasos:**
  1. El Referente **opera de verdad** durante un período acordado (p. ej. 2-4 semanas) sobre el trabajo real del equipo.
  2. Registra fricciones y pedidos; el Equipo de Expertos los convierte en **planes** (pipeline #14) o en **flags** ya existentes (#9), sin parches ad-hoc.
- **Hecho cuando:** el equipo usa Stacky en su trabajo cotidiano y hay un backlog de mejoras registrado y triado.

---

### Fase 5 — Traspaso de responsabilidad

- **Responsable:** Equipo de Expertos → Referente.
- **Precondición:** Fase 4 estable (el Referente opera sin intervención frecuente).
- **Pasos:**
  1. El Referente queda como **dueño del Stacky de su equipo**: config, credenciales, operación diaria y **primer nivel de soporte**.
  2. El Equipo de Expertos pasa a **segundo nivel** (incidencias que escalan) + entrega de **versiones nuevas** del build.
  3. Documentar el traspaso: quién mantiene qué, cómo se reportan incidencias, cómo se reciben versiones nuevas.
- **Hecho cuando:** el traspaso está firmado/documentado y el Referente sostiene la operación con soporte solo de segundo nivel.

---

### Fase 6 — Iterar con el siguiente equipo

- **Responsable:** Equipo de Expertos + liderazgo.
- **Pasos:** repetir **Fase 1 → Fase 5** con el siguiente equipo. Cada equipo = su propio deploy/máquina/Referente. El rollout es secuencial por diseño (control de calidad y soporte acotado por iteración).
- **Hecho cuando:** el nuevo equipo llega a su Fase 5; el anterior sigue autónomo.

---

### Track paralelo (continuo) — Equipo de Expertos construye capacidades nuevas

Corre **en paralelo** a las fases 1-6, sin bloquearlas.

- **Responsable:** Equipo de Expertos.
- **Pasos:**
  1. Diseñar cada capacidad nueva (tool, agente, arnés) con el **pipeline de planes** (#14): proponer → criticar (juez adversarial) → implementar (TDD) → supervisar.
  2. Toda config nueva del operador queda **activable por UI** y la flag nace **default-OFF** (#9, #11): un redeploy nunca cambia el comportamiento en silencio.
  3. Pasar **conformance de 3 runtimes** y los golden gates antes de liberar (#15): garantiza paridad y no-regresión para los equipos en producción.
  4. Liberar como **versión nueva del build** y notificar a los Referentes.
- **Cómo llega a cada equipo:** el Referente (o el Equipo de Expertos) **redeploya** en la máquina del equipo. Como los datos y la config viven fuera del binario (`projects/`, `data/`, `.env`), **sobreviven al redeploy** (#10); las flags nuevas llegan OFF (#11) y el Referente decide cuándo activarlas por UI.
- **Hecho cuando:** la versión nueva está liberada con conformance verde y los Referentes saben cómo y cuándo adoptarla.

---

# Parte 2 — Transición operativa (estado de régimen)

Una vez que el Equipo de Expertos terminó de pasar el conocimiento a los Referentes, el
día a día queda así:

- **Cada equipo** corre su propio Stacky en la máquina de su Referente. El **Referente
  opera**: lanza agentes, revisa `needs_review`, publica al tracker, ajusta
  `client_profile` / `process_catalog` / flags por UI, y es el **primer soporte** de su
  equipo. La "propiedad" es por persona/máquina, no por rol en la app (#1).
- **El Equipo de Expertos ya no opera el día a día**: se dedica a **construir
  capacidades nuevas** por el pipeline (#14), a **liberar versiones** del build con
  conformance/golden gates verdes (#15), y a dar **soporte de segundo nivel** cuando un
  Referente escala una incidencia.
- **Cómo se sostiene la evolución:** las versiones nuevas llegan por **redeploy** en la
  máquina de cada equipo; la config y los datos se preservan (#10) y las flags nuevas
  llegan OFF (#11), así cada equipo adopta mejoras **a su ritmo**, activándolas por UI.
- **Flujo de incidencias:** Referente (1er nivel, su deploy) → Equipo de Expertos (2do
  nivel, plan/fix → versión nueva). Nada se parchea a mano en producción: entra por el
  pipeline.
- **Garantía de no-romper:** ningún cambio del Equipo de Expertos rompe a un equipo en
  producción "por sorpresa", porque (a) las flags nacen OFF, (b) la conformance de 3
  runtimes y los golden gates corren antes de liberar, y (c) el redeploy no cambia
  comportamiento salvo que el Referente active algo.

---

## Limitaciones reales y cómo las sorteamos hoy

| Choque (modelo deseado ↔ realidad del código) | Realidad (evidencia) | Work-around realista con lo que existe |
|---|---|---|
| **A. "Un Referente responsable por equipo"** sugiere control de acceso por rol | No hay auth/roles; `current_user` es un header sin validar (#1, `_helpers.py:4-5`) | La responsabilidad es **organizacional**, no técnica. Aislamiento por **máquina/OS**: el deploy del equipo vive en la máquina del Referente y se protege con el control de acceso del SO. No construir RBAC: sería teatro |
| **B. "Implementar de a un equipo"** en una instancia compartida | Un solo proyecto activo, flags y `.env` por máquina, DB SQLite única por deploy (#5, #8, #10) | **1 equipo = 1 deploy = 1 máquina.** No compartir instancia entre equipos. Si un equipo maneja varios productos, se modelan como proyectos del mismo deploy y se conmuta el activo |
| **C. El flujo estrella (brief→épica→tracker autónomo)** se espera en cualquier runtime | La autopublicación Epic/Issue **solo** la hace `claude_code_cli`; los demás reciben 400 (#4, `agents.py:599-608`) | Estandarizar `claude_code_cli` como runtime de los equipos que autopublican (requiere login de Claude en esa máquina). Con Codex/Copilot el agente igual trabaja, pero la publicación al tracker queda **manual** |
| **D. "Las mejoras del Equipo de Expertos llegan solas"** | Deploy **congelado**: no hay hot-reload; los fixes viajan en un build nuevo (#10, #11) | Entregar **versiones del build**; el Referente **redeploya**. Datos/config se preservan (viven fuera del binario) y las flags nuevas llegan OFF, así el redeploy es seguro |
| **E. Config "lista para copiar"** entre máquinas/equipos | Credenciales cifradas con **DPAPI**, ligadas al usuario/máquina local (#7) | Las credenciales se **re-ingresan por UI** en cada máquina. La config NO sensible (defaults de tracker, plantillas de `client_profile`) sí se estandariza vía `global_config` / plantillas. (Existe `services/config_transfer.py` como vía de transferencia de config, pero los secretos quedan excluidos por diseño) |
| **F. "Dashboard único de toda la organización"** | Cada deploy es una isla con su propia DB SQLite (#5, #10); no hay agregación central en el código | Cada Referente exporta KPIs de su deploy (`backend/services/exporter.py`, métricas de arnés) y **alguien agrega manualmente**. La consolidación cross-equipo en tiempo real **no existe hoy** y no debe prometerse |

---

## Notas de cierre

- Este plan respeta los **rieles duros** de Stacky: human-in-the-loop (#16),
  mono-operador (#1), 3 runtimes con conformance (#2, #15), y todo lo configurable por
  el operador queda **por UI** (#9).
- El único punto donde el modelo organizacional pide más de lo que el código garantiza
  es la **identidad/propiedad** (choque A): se resuelve por convención + aislamiento por
  máquina, **no** agregando un RBAC que no protegería nada.
- La pieza que hay que comunicar sí o sí a cada Referente: **para el flujo autónomo de
  publicación al tracker, el runtime debe ser `claude_code_cli`** (choque C).
