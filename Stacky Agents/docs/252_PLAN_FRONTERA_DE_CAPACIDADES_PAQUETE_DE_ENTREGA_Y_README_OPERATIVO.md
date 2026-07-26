# Plan 252 — La frontera de capacidades: qué hace Stacky, qué te toca a vos, y el paquete de entrega que lo cierra

> Estado: **v1 · PROPUESTO** — pendiente de `criticar-y-mejorar-plan` (juez independiente).
> Autor: StackyArchitectaUltraEficientCode (Claude Opus 5, 1M context).
> Serie: **"Mago de las Pipelines" (246–252)**. Este es el **7º y último**: cierra el círculo.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro. **Este plan no usa LLM en
> ningún camino**: la frontera es un catálogo de datos y el README sale de una plantilla. La
> paridad de los 3 runtimes es trivial **por construcción**, no por esfuerzo.
> Origen: **pedido textual del operador, en 5 puntos numerados** — *"(1) generar automáticamente
> todos los archivos necesarios; (2) habilitar una opción para descargarlos en un único paquete;
> (3) incluir un README claro y detallado con los pasos a realizar en el servidor; (4) especificar
> requisitos previos, comandos, variables y validaciones; (5) limitar la intervención manual
> exclusivamente a lo que el agente no pueda hacer por sí mismo."*

---

## 0. La tesis del plan (leer esto antes que nada)

El punto (5) del pedido — *"limitar la intervención manual exclusivamente a lo que el agente no
pueda hacer por sí mismo"* — es el único de los cinco que **no se puede implementar como una
feature**. Los otros cuatro son un `.zip` y un archivo de texto. El (5) es una **afirmación sobre
el sistema**: para "limitar la intervención manual a lo que Stacky no puede hacer", primero hay
que **saber, y poder demostrar, qué es exactamente lo que Stacky no puede hacer**.

Hoy esa información no existe como dato en ningún lado. Existe como prosa, dispersa, y en el
mejor de los casos escrita a mano por un humano en un comentario. La prueba está en el propio
corpus dorado de esta serie, en la cabecera de
`backend/tests/fixtures/cicd_nl/golden/bootstrap-server-environment.yml:28-32`:

> ```
> # QUE NO HACE (ver Initialize-ServerEnvironment.ps1 seccion .NOTES):
> #   No instala el agente ADO, no habilita WinRM, no instala RecBatchSvc, no
> #   siembra el almacen de claves DPAPI real, no completa ningun placeholder
> #   de credencial/connection string. Todo eso queda explicito en el log de
> #   salida del script bajo "ACCIONES PENDIENTES / DECISIONES REQUERIDAS".
> ```

Y en `:19-26` del mismo archivo, el requisito previo que ningún YAML puede resolverse a sí mismo:

> ```
> # REQUISITO PREVIO (fuera del alcance de este YAML y del script que invoca):
> #   El pool de agente self-hosted del servidor destino (parametro 'agentPool')
> #   YA debe existir y tener un agente registrado y online en ADO ANTES de
> #   correr esta pipeline.
> ```

**Eso es una frontera de capacidades escrita a mano, en comentarios, por un humano, una sola vez,
para un solo pipeline.** Funciona porque alguien se tomó el trabajo. No es verificable, no es
consultable por la UI, no se actualiza cuando cambia el entorno, y no existe para los otros
8 pipelines del corpus.

> **La tesis:** un paquete de entrega sin frontera de capacidades es un `.zip` con buenas
> intenciones — nadie puede auditar si lo que quedó adentro es "lo que Stacky no podía hacer" o
> "lo que Stacky no se molestó en hacer". Por eso **A (la frontera) va antes que B (el zip)**, y
> por eso A tiene valor entregable **por sí sola**: convierte el punto (5) del operador de promesa
> en aserción testeable.

La segunda mitad de la tesis es sobre el README. El pedido (4) dice *"requisitos previos,
comandos, variables y validaciones"*. **La validación es la parte que casi todos los generadores
de READMEs omiten**, y es la única que le sirve al operador parado frente al servidor a las
23:40. Un README que dice *"instalá el agente self-hosted"* y no dice **cómo saber que quedó
instalado** es exactamente el artefacto que este plan existe para no producir. Por eso el
contrato de datos de un paso manual en este plan **no puede construirse sin su validación**: es
un campo obligatorio, no un campo opcional bien intencionado (F2).

---

## 1. Objetivo y valor

Que cuando Stacky termine de generar un pipeline, el operador vea un botón **"Descargar paquete
de entrega"**, obtenga **un solo `.zip`**, lo abra, lea el `README.md`, y en ~10 minutos haga —
sin adivinar nada y sin preguntarle a nadie — **exactamente las tareas que Stacky no podía
ejecutar por sí mismo, y ninguna más**.

Dos piezas, y la primera le da sentido a la segunda:

- **A) `pipeline_capability_frontier.py` — la frontera como DATO.** Catálogo cerrado y versionado
  de acciones del dominio (crear el YAML, registrar la definición, crear un service connection,
  instalar un agente self-hosted, abrir un puerto…), cada una con un veredicto
  `CAN | DEPENDS | CANNOT`, **un motivo obligatorio**, y — para las `DEPENDS` — la sonda concreta
  que la resuelve contra el **estado real** del entorno (¿hay PAT?, ¿hay token de GitLab?, ¿hay
  repo escribible?). No es una lista de deseos: se evalúa en cada corrida.
- **B) `pipeline_handoff_bundle.py` — el paquete.** Un `.zip` **único, determinista y sin un solo
  secreto adentro**, con los YAML generados, los scripts auxiliares, un `MANIFEST.json` y un
  `README.md` operativo generado **por plantilla** (nunca por LLM) donde **cada paso manual trae
  su comando, su validación y qué hacer si falla**.

**KPI / impacto esperado (binarios, verificados por los tests nombrados en cada fase):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| **KPI-1** | Reproducibilidad | `zip_bytes(files)` llamado dos veces, con archivos cuyo mtime en disco difiere, devuelve **bytes idénticos**; `sha256` estable. `test_zip_es_byte_identico_en_dos_corridas` |
| **KPI-2** | Cero secretos | Con un token sembrado en cualquier archivo de entrada, `build_bundle` **lanza `HandoffSecretError` y NO produce zip** (falla cerrado, no enmascara y sigue). `test_secreto_sembrado_aborta_el_bundle` |
| **KPI-3** | Frontera verificable (punto 5 del operador) | Las **14** acciones del catálogo tienen veredicto ∈ `{CAN, DEPENDS, CANNOT}` y `reason` no vacío; y **ninguna acción resuelta `CAN` aparece en la lista de pasos manuales del README**. `test_toda_accion_tiene_veredicto_y_motivo` + `test_ninguna_accion_can_es_paso_manual` |
| **KPI-4** | README accionable (punto 4 del operador) | **Todo** `HandoffStep` del manifest tiene `command`, `expected_result` y `on_failure` no vacíos — imposible construir uno sin ellos. `test_paso_sin_validacion_es_rechazado` |
| **KPI-5** | Degradación honesta | Sin los módulos de los planes 246/247/251 instalados, `build_bundle` produce un zip **válido** y `manifest["degraded"]` lista **exactamente** los módulos ausentes. `test_bundle_sin_246_247_251_igual_se_arma` |
| **KPI-6** | Descarga segura | `bundle_id` desconocido → `404`; ruta resuelta fuera de la raíz de bundles → `400`; zip por encima del tope → `413`. `test_download_*` (3 casos) |

**Ganancia robusta:** el handoff Stacky→operador deja de ser un chat ("che, ¿y ahora qué hago?")
y pasa a ser un artefacto versionado, auditable y con huella de contenido.

**Onboarding casi nulo:** un botón nuevo en la sección Pipelines del panel DevOps que ya existe.
Nada que configurar.

---

## 2. Evidencia (todo verificado abriendo los archivos el 2026-07-26)

### 2.1 Prior art de empaquetado — lo que esta casa YA resolvió (reusar, no reinventar)

| Pieza | Anclaje (símbolo verificado) | Qué me aporta |
|---|---|---|
| **Zip en memoria + `send_file`** | `backend/api/devops_servers.py:181` (`download_setup_route`), `:212-216` (`io.BytesIO()` + `zipfile.ZipFile(..., "w", ZIP_DEFLATED)` + `zf.write(..., arcname=...)`), `:218-223` (`send_file(..., as_attachment=True, download_name=...)`) | **El precedente exacto de mi endpoint.** Y su docstring `:183-187` ya escribe un mini-README de 3 pasos: es literalmente la versión artesanal de este plan |
| **Bundle a disco + manifest + README** | `backend/services/dbcompare_scripts.py:1234` (`bundle_zip_bytes`), `:1180-1195` (arma `MANIFEST.json` con `json.dumps(..., sort_keys=True)` y `files["README.md"] = _render_readme(manifest, warnings)`), `_render_readme` (`:1155`, verificado por lectura), `_write_bundle_atomic` (`:1207`+, escribe a `<id>.tmp/` y recién ahí `os.replace`) | El patrón `dict[str, str]` → archivos → zip, con **README por plantilla determinista** y escritura atómica. Lo copio tal cual |
| **Zip ordenado** | `dbcompare_scripts.py:1238` — `for path in sorted(base.rglob("*"))` y `arcname=...replace("\\", "/")` | Orden estable de entradas + separador POSIX. **Falta el `date_time`** (ver §2.3) |
| **Descarga con guard anti path-traversal** | `docs/201_PLAN_...ARTEFACTOS_DESCARGABLES.md:806-819` (F7) — `commonpath` + *"`build_id` NUNCA se interpola en una ruta de filesystem; solo se usa como **clave**"*; implementado en `backend/services/solution_builder.py:410` (`artifact_zip_path`, docstring literal: *"`build_id` es una CLAVE, jamás parte de una ruta"*) y `backend/api/devops_build_workshop.py:175` (`send_file`) | **El guard exacto que copio en F4.** No lo reinvento: lo espejo |
| **Zip como respuesta sin archivo temporal** | `backend/api/db_compare.py:871` (`get_scripts_zip_route`), `:883-885` (`current_app.response_class(zip_bytes, mimetype="application/zip")` + `Content-Disposition`) | Alternativa a `send_file` cuando los bytes ya están en memoria |
| **Descarga desde el frontend** | `frontend/src/api/endpoints.ts:4016` (`DevOpsServers`), `:4037` (`downloadSetupScripts`), `:4039-4048` (`fetch` → `blob()` → `URL.createObjectURL` → `<a download>` → `revokeObjectURL`) | **El patrón de descarga del frontend, ya escrito.** F5 lo reusa literal |
| **Export portable con "cero secretos" y checklist HITL** | `docs/190_PLAN_...EQUIPAJE_PORTABLE...md` — KPI-1 (*"Cero secretos en el bundle"*, `:54`), regla de oro `:114-115`, `credentials_manifest` = **lista de aliases, nunca valores** (`:28-31`) | **Mi pariente más cercano.** Mismo principio: lo que viaja es el *nombre* de lo que falta, jamás su valor |
| **Masking canónico** | `backend/services/secret_masking.py:1` (docstring: *"Plan 195 … Masking canónico … PURO: sin red, sin config"*), `:11` (`TOKEN_VALUE_PREFIXES`), `:12` (`MASK_PLACEHOLDER`), `:20` (`mask_token_values`), `:25` (`strip_secret_keys`) | **El módulo del Plan 195 que el pedido me obliga a reusar. Verificado: vive acá, no en otro lado.** Consumidores actuales: `ci_log_view.py:9`, `config_transfer.py:67`, `devops_evidence.py:18`, `pipeline_lint.py:14` |
| **Guardia de red / clases de dato** | `backend/services/egress_policies.py:64` (`_DETECTORS`), `:81-92` (clase `"secrets"`: `ghp_`, `github_pat_`, `glpat-`, `AKIA`, PEM, `xox[baprs]-`, JWT, `password=…`, `;password=…`, `Authorization: bearer`), `:96` (`detect_classes(text) -> set[str]`) | Segunda capa del gate anti-secreto. **`detect_classes` es la API pública; `_DETECTORS` es privada** |
| **Vocabulario "cómo validar"** | `backend/services/validation_playbook.py:30` (`SECTION_TITLE`), `:32` (`DEGRADED_MESSAGE`), `:121` (`class ValidationStep` con campos **`n`, `action`, `expected_result`, `source`**) | **El dialecto ya existe (Plan 209). Mi `HandoffStep` lo espeja campo por campo** en vez de inventar uno nuevo (F2 + test que lo congela) |

### 2.2 Sustrato de pipelines de la serie (lo que consumo, no lo que construyo)

| Pieza | Anclaje (símbolo verificado) | Rol en este plan |
|---|---|---|
| Blueprint patrón | `backend/api/pipeline_generator.py:24` (`bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")`), `:1-10` (docstring con la regla `url_prefix` sin `/api`), `:36-37` (guard **per-request** `abort(404)`) | Molde EXACTO de `api/pipeline_handoff.py` (F4) |
| Preview / commit HITL | `frontend/src/api/endpoints.ts:4426` (`PipelineGenerator`), `:4429` (`preview`), `:4434` (`commit`, comentario *"commit HITL con confirm"*) | El paso `commit_yaml_to_repo` de la frontera resuelve a `CAN` **gracias a esto** |
| Renderer y parser | `backend/services/pipeline_renderers.py:79` (`to_ado_yaml`), `:277` (`to_gitlab_yaml`), `:453` (`parse_ado_yaml`), `:51` (`scan_unsupported`) | El YAML que va al zip sale de acá; no lo re-renderizo |
| Catálogo de tareas | `backend/services/cicd_task_catalog.py:28` (`CATALOG_VERSION = "243.1"`), `:62` (`DEPLOY_TASK_REFS`), `:244` (`is_deploy_step`), `:261` (`is_machine_group_task`), `:287` (`extract_task_refs`) | Detecta si el pipeline **despliega** → activa las acciones de frontera de infraestructura |
| Alta de definición ADO | `backend/services/ado_pipeline_definitions.py:120` (`class DefinitionConfirmRequired`), `:125` (`ensure_yaml_definition`), `:5` (`_MAX_DEFINITIONS = 50`) | Prueba de que `register_pipeline_definition` es `DEPENDS` **y HITL**, no `CAN` automático |
| Sonda de credencial ADO | `backend/services/ado_client.py:203` (`ado_pat_present(auth_path=None) -> bool`) | **Sonda real** de la frontera (no una env var leída a mano) |
| Sonda de credencial GitLab | `backend/services/gitlab_client.py:5` (docstring: *"Auth por token (env `GITLAB_TOKEN` > archivo `auth/gitlab_auth.json` > campo token)"*), `:62` (`os.getenv("GITLAB_TOKEN")`), `:68` (mensaje de error cuando no hay ninguno) | **No existe un `gitlab_token_present()`**: F1 declara su propia sonda espejando esta precedencia (§2.4) |
| Placeholders sin resolver | `backend/services/pipeline_preflight.py:13` (`PLACEHOLDER_LITERALS`), `:37` (`check_placeholders`), `:102` (`check_undefined_variables`), `:79` (`referenced_variables`) | Fuente **determinista y ya implementada** de la sección "Variables a completar" cuando el Plan 251 no está |
| Caja fuerte de variables | `backend/services/ci_variables.py:13` (`validate_variable_key`), `:31` (`looks_secret`), `:40` (`VariablesUnavailableError`), `:66` (`get_variables_provider`) | `looks_secret(key)` decide qué variable se nombra **sin valor** en el README |
| Flags | `backend/services/harness_flags.py:20` (`@dataclass(frozen=True) class FlagSpec`), `:120` (`_CATEGORY_KEYS`), `:217` (categoría `"devops"`), `backend/tests/test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON`) | Cableado exacto de la flag (F0) |
| Ratchet de tests | **DOS listas:** `backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`) **y** `backend/scripts/run_harness_tests.ps1:13` (`$HarnessTestFiles = @(`) | Todo `test_*.py` nuevo va **en las dos** |
| Panel DevOps | `frontend/src/pages/DevOpsPage.tsx:75` (`interface DevOpsSection` — campos `id, label, icon?, healthKey?, gateFlagKey?, gateMessage?, group?, summary?, render`), `:126-131` (la sección `id: 'pipelines'`, `group: 'construir'`) | Dónde se monta el panel (F5) |
| Contrato UX de IA del panel | `frontend/src/components/devops/PipelineBuilderSection.tsx:382-383` — *"pide sugerencias al modelo local y PRE-RELLENA solo lo que está vacío (KPI-5, HITL): nunca pisa lo que el operador ya escribió"* | El paquete **nunca** se genera solo: es un click explícito (F4/F5) |
| Ruta de datos | `backend/runtime_paths.py:48` (`data_dir()`) | Raíz de `data_dir()/pipeline_handoff/bundles/` |

### 2.3 La trampa de la reproducibilidad (fundamento de F3)

`zipfile.ZipFile.write(path, arcname=...)` **toma el `mtime` del archivo en disco** y lo escribe en
el encabezado local de cada entrada. Consecuencia: el precedente de
`dbcompare_scripts.py:1234-1241` — que ordena las entradas correctamente — **igual produce bytes
distintos en cada corrida**, porque los archivos del bundle se acaban de escribir a disco y su
`mtime` cambió. Lo mismo pasa con `zf.writestr(nombre, contenido)`: sin `ZipInfo` explícito, usa
`time.localtime()`.

**Resolución explícita (F3):** el zip se arma **solo con `ZipInfo` construidos a mano**, con
`date_time = _ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)` (el mínimo que admite el formato ZIP),
`compress_type = ZIP_DEFLATED`, `external_attr` fijo y entradas ordenadas por `arcname`. Nunca se
usa `zf.write(ruta)`: el contenido viaja siempre desde el `dict[str, str]` en memoria.

**Corolario incómodo, y su resolución:** si el zip debe ser byte-idéntico, **no puede contener un
timestamp de generación**. Por lo tanto `MANIFEST.json` **no lleva `generated_at`** (a diferencia
de `dbcompare_scripts.py:1183`, que sí lo lleva y por eso no es reproducible). La identidad del
paquete es su **huella de contenido**: `bundle_id = sha256(json canónico del mapa de archivos)[:16]`.
El "cuándo" vive **fuera** del zip: en el nombre del archivo descargado y en el ledger JSONL. El
README dice `id: <bundle_id>` y explica en una línea que es la huella del contenido, no una fecha.
Ese es el trade-off, es deliberado, y está congelado por `test_manifest_no_tiene_timestamp`.

### 2.4 Lo NO verificado (declarado)

- **`services/devops_variables.py` NO EXISTE.** El dossier de la serie lo lista en su §2.1 junto a
  `ci_variables.py`/`ado_variables.py`/`gitlab_variables.py`. Verificado con `ls`: en
  `backend/services/` **no está** (sí existe `backend/api/devops_variables.py`, que es el
  blueprint). **Ningún archivo de este plan lo importa.** Si un implementador lo ve citado en el
  dossier, es un error del dossier, no una dependencia faltante.
- **No existe un `gitlab_token_present()`** análogo a `ado_client.ado_pat_present` (`:203`).
  Verificado con `grep -rn "def .*token.*present\|def has_token"` sobre `services/` → 0 hits. F1
  declara `_probe_gitlab_token()` **dentro de `pipeline_capability_frontier.py`**, espejando la
  precedencia documentada en `gitlab_client.py:5` (env `GITLAB_TOKEN` > `auth/gitlab_auth.json`).
  Es una sonda **de solo lectura**: nunca abre una conexión de red.
- **Los módulos de los planes 246 (`pipeline_inventory.py`), 247 (`pipeline_profiler.py`) y 251
  (`pipeline_environments.py`) NO EXISTEN todavía.** Verificado con `ls backend/services/ | grep -E
  "pipeline_(environments|inventory|profiler|handoff|capability)"` → **salida vacía**. Este plan es
  implementable **hoy, solo**, y así lo prueba KPI-5.
- **No se verificó** si ADO expone un endpoint de validación server-side de YAML (el Plan 243 §2.4
  lo declara igualmente como no verificado). Este plan **no lo necesita**: no valida contra ADO.
- Este plan **no toca ninguna tabla**: la persistencia nueva es un directorio de bundles + un
  JSONL, ambos bajo `data_dir()`.

---

## 3. Alcance / Fuera de alcance / Corte declarado

**En alcance:** el catálogo de frontera de capacidades y su evaluación contra el estado real; el
armado determinista del paquete; el README operativo por plantilla; el gate anti-secreto; el
endpoint de descarga con sus tres guardas; el panel en la sección Pipelines.

**Corte de alcance declarado (§7 del dossier: máximo 6 fases).** Entra F0..F5 y nada más. Lo que
se cortó a propósito, con su motivo:

| Cortado | Motivo |
|---|---|
| Pulido del README por LLM | Rompería la paridad trivial de los 3 runtimes y metería no determinismo en el artefacto que este plan promete reproducible (KPI-1). El README **sale 100% de plantilla**. Si algún día se quiere pulir, va en un plan aparte con su propia flag |
| Ledger con UI (historial de paquetes emitidos) | El JSONL se escribe en F4 (auditoría), pero **no se le construye pantalla**. Un plan futuro puede leerlo |
| Firma / checksum externo del zip (GPG, sigstore) | El `bundle_id` ya es la huella `sha256` del contenido. Firmar cambia el modelo de confianza y necesita gestión de claves: fuera |
| Envío del paquete por mail / Slack / a un share | Es un mensaje externo → **excepción dura (1)** del dossier. Prohibido |

**Fuera de scope duro y no negociable:**

- **Ejecutar cualquier cosa en el servidor del operador.** Ni WinRM, ni SSH, ni `Invoke-Command`,
  ni un `subprocess` contra una máquina remota. **Eso es precisamente lo que este plan declara
  como fuera de la frontera**; implementarlo lo vaciaría de sentido. Congelado por
  `test_modulos_sin_ejecucion_remota` (F0).

---

## 4. Principios y guardarraíles (codificados en cada fase)

1. **Paridad 3 runtimes por construcción.** Cero LLM en todo el plan. Backend Python puro + un
   modelo puro de frontend. Idéntico en Codex CLI / Claude Code CLI / GitHub Copilot Pro, **y sin
   ningún runtime instalado**. El fallback de cada fase es, literalmente, "no hay nada que
   degradar".
2. **Cero trabajo extra para el operador.** Flag `STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED` default
   **ON**. Justificación explícita de por qué **ninguna** de las 4 excepciones duras aplica:
   (1) *no bypasea revisión humana* — al contrario, **existe para que un humano revise y ejecute**,
   y no publica, ni crea tickets, ni ejecuta remoto, ni manda mensajes externos;
   (2) *no es destructiva ni irreversible* — solo escribe archivos nuevos bajo `data_dir()`;
   (3) *no tiene prerequisitos fuera de la instalación default* — `zipfile`, `hashlib` y `json` son
   stdlib; **no agrega ni una dependencia**;
   (4) *no reduce la seguridad por default* — la **sube**: el gate anti-secreto de F3 falla cerrado.
   Además **no quema tokens ociosos**: nada se pre-genera; el bundle se arma **solo** cuando el
   operador clickea.
3. **Human-in-the-loop innegociable.** El paquete se genera con un click explícito y **su único
   efecto es producir un archivo descargable**. El README **instruye**, nunca ejecuta. Ningún
   endpoint de este plan muta el repo, el tracker, un servidor ni una pipeline.
4. **Mono-operador sin auth.** Cero RBAC, cero roles, cero `403`. El `bundle_id` no es un secreto
   ni un token de autorización: es una clave de búsqueda local.
5. **Falla cerrado en secretos.** Si el gate detecta un secreto, **el bundle no se produce**. No se
   enmascara-y-sigue: enmascarar y seguir enseñaría al operador que el paquete "limpia solo", y la
   primera vez que el masking no cubra un formato nuevo, el secreto viaja.
6. **Determinismo o no es un artefacto.** Mismas entradas → mismos bytes. Sin esto, no se puede
   comparar dos paquetes, ni cachear, ni auditar qué se le entregó a quién.
7. **No degradar / backward-compatible.** Todo lo nuevo es aditivo: 2 módulos de servicio, 1
   blueprint, 1 modelo puro, 1 componente, 1 entrada en `DevOpsPage.tsx`. **Cero ediciones a
   módulos existentes** fuera del registro de la flag, el registro del blueprint y el array de
   secciones. Con la flag OFF, todo queda **exactamente** como hoy.
8. **Reusar, no reinventar.** `secret_masking` (195), `egress_policies.detect_classes` (154), el
   guard `commonpath` (201 F7), el patrón de blueprint (`pipeline_generator.py:24`), el patrón de
   descarga del frontend (`endpoints.ts:4039-4048`), el vocabulario de validación (209).

---

## 5. La frontera de capacidades — tabla COMPLETA (contrato de F0)

Esta tabla **es el catálogo**: se transcribe a `ACTION_CATALOG` en
`services/pipeline_capability_frontier.py` sin agregar ni quitar filas. `CATALOG_VERSION = "252.1"`.

Leyenda de veredicto **declarado** (el del catálogo, antes de sondear):
- **`CAN`** — Stacky lo ejecuta por sí mismo en el entorno default (con HITL si escribe algo).
- **`DEPENDS`** — puede o no, según el estado real; se resuelve con la sonda de la columna *Sonda*.
- **`CANNOT`** — Stacky **no puede**, en ningún entorno, por diseño. Es trabajo del operador.

| # | `id` | Acción | Veredicto declarado | Sonda (`probe_id`) que lo resuelve | Motivo (`reason`, texto del catálogo) | Qué queda manual si no se resuelve a `CAN` |
|---|------|--------|---------------------|------------------------------------|----------------------------------------|--------------------------------------------|
| 1 | `generate_yaml` | Generar el YAML del pipeline | **CAN** | — | El renderer es determinista y local (`pipeline_renderers.to_ado_yaml`) | — |
| 2 | `generate_helper_scripts` | Generar los scripts auxiliares que el pipeline invoca | **CAN** | — | Son texto; se emiten junto al YAML | — |
| 3 | `commit_yaml_to_repo` | Escribir el YAML en el repo (rama + commit) | **CAN** | `repo_writer` | Ya existe y es HITL con confirm (`PipelineGenerator.commit`) | Copiar el `.yml` del paquete al repo y commitearlo |
| 4 | `open_pull_request` | Abrir el PR/MR con el YAML | **DEPENDS** | `ado_pat` \| `gitlab_token` | Requiere credencial del proveedor con permiso de escritura de PR | Abrir el PR a mano desde la web del proveedor |
| 5 | `register_pipeline_definition` | Dar de alta la definición de pipeline en ADO/GitLab | **DEPENDS** | `ado_pat` | Requiere PAT con scope de Build y **confirmación humana** (`DefinitionConfirmRequired`) | `Pipelines → New pipeline → Existing Azure Pipelines YAML file` y elegir la ruta del `.yml` |
| 6 | `set_pipeline_variables` | Cargar variables no secretas de la pipeline | **DEPENDS** | `ado_pat` \| `gitlab_token` | Requiere credencial y permiso sobre variables | Cargar las variables listadas en el README, una por una |
| 7 | `set_pipeline_secrets` | Cargar los **valores secretos** de las variables | **CANNOT** | — | **Por diseño:** Stacky nunca transporta valores secretos (regla de oro del Plan 190) | Cargar cada secreto marcado en el README, en la UI del proveedor |
| 8 | `create_variable_group` | Crear un grupo de variables / Library | **DEPENDS** | `ado_pat` | Requiere permiso sobre Library, que un PAT de build no siempre trae | `Pipelines → Library → + Variable group` |
| 9 | `create_service_connection` | Crear un service connection | **CANNOT** | — | Exige consentimiento de una identidad (service principal / OAuth) y rol de administrador del proyecto: no es una llamada de API que un PAT pueda hacer sin más | `Project settings → Service connections → New` |
| 10 | `create_environment_and_approvals` | Crear el `environment` y su approval gate | **DEPENDS** | `ado_pat` | Requiere permiso de Environments; el approval además define **quién** aprueba (decisión humana) | `Pipelines → Environments → New environment` + agregar aprobadores |
| 11 | `create_agent_pool` | Crear el agent pool | **DEPENDS** | `ado_pat` | Requiere rol de administrador de pools a nivel organización | `Project settings → Agent pools → Add pool` |
| 12 | `install_selfhosted_agent` | Instalar y registrar el agente self-hosted en el servidor destino | **CANNOT** | — | **Stacky no ejecuta nada en el servidor destino.** El agente se instala corriendo un instalador *en esa máquina*, con una cuenta de esa máquina | Descargar el agente, `config.cmd`, registrarlo en el pool y dejarlo como servicio |
| 13 | `install_server_prerequisites` | Instalar IIS / roles de Windows / build tooling / abrir puertos en el servidor | **CANNOT** | — | Misma razón que 12: es administración del sistema operativo del servidor destino | Ejecutar los pasos del README como administrador en el servidor |
| 14 | `run_pipeline_first_time` | Disparar la primera corrida | **DEPENDS** | `ado_pat` | Requiere definición registrada **y** un agente online; y es **HITL**: la primera corrida la autoriza el operador | `Run pipeline` desde la web, con los parámetros que indica el README |

**Sondas (`PROBE_CATALOG`), 3 en total:**

| `probe_id` | Cómo se resuelve | Nunca hace |
|---|---|---|
| `ado_pat` | `services.ado_client.ado_pat_present()` (`ado_client.py:203`) | Red |
| `gitlab_token` | `_probe_gitlab_token()`: `os.getenv("GITLAB_TOKEN")` no vacío **o** existe el archivo `auth/gitlab_auth.json` — espejando la precedencia de `gitlab_client.py:5,62` | Red |
| `repo_writer` | `services.repo_writer.get_repo_writer()` devuelve algo distinto de `None` sin lanzar | Escribir |

**Regla de resolución (pura, F0):** una acción `DEPENDS` cuya expresión de sondas evalúa `True`
resuelve a `CAN`; si evalúa `False` resuelve a `CANNOT_NOW` (distinto de `CANNOT`: es circunstancial,
y el README lo dice con otras palabras). Una sonda que **no se pudo evaluar** (excepción,
módulo ausente) resuelve a `UNKNOWN`, y `UNKNOWN` **se trata como `CANNOT_NOW`** — nunca como
`CAN`. Falla cerrado también acá.

---

## 6. La plantilla LITERAL del README operativo (contrato de F2)

`render_readme(manifest: dict) -> str` produce **exactamente** esta estructura. Los `{…}` son
sustituciones; todo lo demás es literal. Las secciones vacías **se omiten enteras** (encabezado
incluido) salvo `## Validación final`, que siempre está.

```markdown
# Paquete de entrega — {pipeline_name}

Generado por Stacky Agents · id `{bundle_id}` · proveedor `{provider}`
El `id` es la huella SHA-256 del contenido de este paquete, no una fecha: dos paquetes con el
mismo id son byte a byte el mismo paquete.

---

## 1. Qué hizo Stacky por vos

{por cada accion con verdict_efectivo == "CAN": "- {label}. {reason}"}

## 2. Qué te toca a vos, y por qué

Estas son las únicas tareas que Stacky no puede ejecutar por sí mismo. No hay ninguna otra.

{por cada accion con verdict_efectivo in ("CANNOT","CANNOT_NOW"): }
- **{label}** — {reason}{si CANNOT_NOW: " (hoy no se pudo: {probe_id} no está disponible; si lo
  configurás en Stacky, la próxima vez esto lo hace solo)"}

{si degraded no está vacío:}
> Nota honesta: este paquete se armó sin {lista legible de módulos ausentes}. Eso significa que
> {consecuencia concreta por módulo, del mapa DEGRADED_CONSEQUENCE}.

## 3. Prerequisitos

Verificá los tres antes de empezar. Si alguno falla, frená: los pasos siguientes no van a andar.

| # | Prerequisito | Cómo verificarlo | Qué tenés que ver |
|---|--------------|------------------|-------------------|
{por cada prerequisito: "| {n} | {label} | `{command}` | {expected_result} |"}

## 4. Variables a completar

Stacky **no incluye ni un solo valor secreto en este paquete**, a propósito. Acá está la lista de
qué completar y dónde; los valores los ponés vos.

| Variable | Dónde se carga | Formato / ejemplo | ¿Es secreta? |
|----------|----------------|-------------------|--------------|
{por cada variable: "| `{name}` | {where} | {format_hint} | {"SÍ — cargala marcada como secreta" si secret else "no"} |"}

## 5. Pasos

{por cada paso n, en orden:}
### Paso {n} — {action}

- **Dónde:** {where}
- **Comando:**
  ```{lang}
  {command}
  ```
- **Cómo sabés que salió bien:** {expected_result}
- **Si falla:** {on_failure}
- **Fuente:** {source}

## 6. Validación final

Cuando termines todos los pasos, esto tiene que ser cierto:

{por cada item de final_checks: "- [ ] {check} — verificalo con: `{command}`"}

Si algún ítem no se cumple, **no des el pipeline por operativo**.

## 7. Si algo sale mal

{rollback_note}

Nada de lo que hiciste con este paquete borra datos: si un paso falló a la mitad, se puede repetir.
Los pasos marcados como `no repetible` en la sección 5 son la excepción y lo dicen ahí mismo.

## 8. Anexo — contenido del paquete

{por cada archivo del manifest, ordenado: "- `{path}` — {kind} · {bytes} bytes"}
```

**Por qué esta plantilla y no otra:** las columnas *Cómo verificarlo / Qué tenés que ver* de la
sección 3 y los campos *Cómo sabés que salió bien / Si falla* de la sección 5 son el par
`action` + `expected_result` que el Plan 209 ya estableció como el dialecto de esta casa
(`validation_playbook.py:121`, `class ValidationStep`). **No se inventa un dialecto nuevo.**

---

## 7. Fases

> **Comandos (§4 del dossier, verificados el 2026-07-26).** Trampa: en `backend/` conviven
> `backend/.venv` (Python **3.13.5**) y `backend/venv` (3.11.9). **Usá `.venv`.** El frontend
> **no tiene script `test`**: `npm test` falla; se usa `npx vitest`.
>
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> .venv\Scripts\python.exe -m pytest tests/<archivo>.py -q     # SIEMPRE por archivo
> .venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q   # tras crear cualquier test nuevo
> .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q          # tras tocar harness_flags.py
>
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
> npx vitest run src/devops/__tests__/<archivo>.test.ts
> npx tsc --noEmit
> ```
>
> **Rojo preexistente ajeno:** `test_harness_flags_help` arrastra 4 fallos que **no son de este
> plan**. Validá tu entrada de forma aislada; no los "arregles".

---

### F0 — La frontera como DATO: catálogo cerrado + resolución pura + flag

**Objetivo (1 frase):** que "qué puede y qué no puede Stacky" deje de ser prosa y pase a ser una
estructura consultable y testeable.
**Valor:** convierte el punto (5) del operador en una aserción verificable. **Entrega valor solo**,
sin F1..F5.

**Archivos:**
- CREAR `Stacky Agents/backend/services/pipeline_capability_frontier.py`
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- EDITAR `Stacky Agents/backend/config.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags.py` (agregar la key a `_CURATED_DEFAULTS_ON`, **línea 467**)
- CREAR `Stacky Agents/backend/tests/test_plan252_capability_frontier.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (**:20**, `HARNESS_TEST_FILES=(`)
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.ps1` (**:13**, `$HarnessTestFiles = @(`)

**Símbolos EXACTOS a crear en `pipeline_capability_frontier.py`:**

```python
"""services/pipeline_capability_frontier.py — Plan 252 F0/F1. Frontera de capacidades.

Declara, COMO DATO, qué acciones del dominio de pipelines puede ejecutar Stacky por sí
mismo y cuáles no, con el motivo. PURO en F0 (cero I/O, cero red, cero config): las
sondas de estado real viven en F1 y se inyectan.

PROHIBIDO en este módulo (y congelado por test): subprocess, paramiko, winrm, requests,
socket. Este módulo describe la frontera; jamás la cruza.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CATALOG_VERSION = "252.1"

# Veredictos declarados (los del catálogo)
CAN = "CAN"
DEPENDS = "DEPENDS"
CANNOT = "CANNOT"
# Veredictos efectivos adicionales (los que sale de resolver DEPENDS contra el entorno)
CANNOT_NOW = "CANNOT_NOW"   # podría, pero hoy le falta la sonda
UNKNOWN = "UNKNOWN"          # no se pudo evaluar la sonda → se trata como CANNOT_NOW

_DECLARED_VERDICTS = frozenset({CAN, DEPENDS, CANNOT})
_EFFECTIVE_VERDICTS = frozenset({CAN, CANNOT, CANNOT_NOW, UNKNOWN})


@dataclass(frozen=True)
class CapabilityAction:
    id: str                    # snake_case, único
    label: str                 # texto para el operador (español)
    verdict: str               # ∈ _DECLARED_VERDICTS
    reason: str                # OBLIGATORIO no vacío — el "por qué"
    probes: tuple = ()         # tuple[str, ...] de probe_id; OR entre ellas. Solo si DEPENDS
    manual_instruction: str = ""   # qué hace el operador si no resuelve a CAN
    needs_deploy: bool = False     # True = solo aplica si el pipeline despliega


@dataclass(frozen=True)
class ResolvedAction:
    action: CapabilityAction
    effective: str             # ∈ _EFFECTIVE_VERDICTS
    probe_detail: str          # qué sonda decidió, o "" si el veredicto era declarado


ACTION_CATALOG: tuple = ( ... )   # las 14 filas de §5, en ese orden
PROBE_IDS: tuple = ("ado_pat", "gitlab_token", "repo_writer")


def get_action(action_id: str) -> Optional[CapabilityAction]: ...
def resolve_frontier(probes: dict, *, pipeline_deploys: bool = False) -> list: ...
def manual_actions(resolved: list) -> list: ...
def automatic_actions(resolved: list) -> list: ...
```

**Contrato de `resolve_frontier(probes, *, pipeline_deploys=False) -> list[ResolvedAction]` (PURO):**
- `probes` es un `dict[str, bool | None]`: `True` = disponible, `False` = ausente, `None` /
  clave faltante = **no evaluable** → `UNKNOWN`.
- Acción `CAN` declarada → `effective = CAN`, `probe_detail = ""`.
- Acción `CANNOT` declarada → `effective = CANNOT`, `probe_detail = ""`. **Ninguna sonda la puede
  promover.** (`create_service_connection` y `install_selfhosted_agent` no se vuelven `CAN` porque
  aparezca un PAT.)
- Acción `DEPENDS`:
  - si **alguna** de sus `probes` es `True` → `CAN`, `probe_detail = f"{probe_id} disponible"`;
  - si **todas** son `False` → `CANNOT_NOW`, `probe_detail = f"falta: {', '.join(probes)}"`;
  - si ninguna es `True` y **alguna** es `None`/ausente → `UNKNOWN`,
    `probe_detail = f"no evaluable: {probe_id}"`.
- Si `pipeline_deploys is False`, las acciones con `needs_deploy=True` **no aparecen** en el
  resultado (un pipeline que solo compila no necesita que nadie instale IIS).
- Orden de salida = orden de `ACTION_CATALOG`. **Determinista.**
- `manual_actions(resolved)` = los `effective ∈ {CANNOT, CANNOT_NOW, UNKNOWN}`.
  `automatic_actions(resolved)` = los `effective == CAN`. Los dos conjuntos son **disjuntos y su
  unión es el total** (invariante congelada por test).

**Casos borde:** `probes={}` → todas las `DEPENDS` caen en `UNKNOWN` (nunca en `CAN`).
`probes={"ado_pat": True}` con `pipeline_deploys=False` → 12 acciones (se van las 2 con
`needs_deploy=True`: `install_selfhosted_agent`, `install_server_prerequisites`).

**Diff en `harness_flags.py`** — `FlagSpec` al final del bloque DEVOPS (el registro es el tuple
`FLAG_REGISTRY`; el patrón de `@dataclass(frozen=True) class FlagSpec` está en `:20`):

```python
FlagSpec(
    key="STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED",
    type="bool",
    label="Paquete de entrega de pipelines",
    description=(
        "Plan 252 - genera un .zip unico con los YAML, los scripts y un README operativo "
        "para lo que Stacky no puede hacer solo. OFF: desaparece el boton y el endpoint "
        "responde 404; todo lo demas del panel queda identico."
    ),
    group="global",
    default=True,  # default ON: ninguna de las 4 excepciones duras aplica (§4.2). Curada en _CURATED_DEFAULTS_ON.
    # SIN requires: el paquete se puede armar aunque el generador NL este OFF (los YAML pueden venir del repo).
),
```

Y agregar `"STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED",  # Plan 252 — paquete de entrega + frontera de capacidades`
a `_CATEGORY_KEYS["devops"]` (`harness_flags.py:217`, al final del bloque, después de
`"STACKY_DEVOPS_COCKPIT_ENABLED"`).

**Diff en `config.py`** (espejo del default; patrón idéntico al del Plan 209):

```python
# ── Plan 252 — Paquete de entrega de pipelines ────────────────────────────
# Genera un .zip determinista con YAML + scripts + README operativo. No ejecuta
# nada: solo produce un archivo descargable. Default ON (espejo del default=True
# de la FlagSpec homonima; curada en _CURATED_DEFAULTS_ON). Editable por UI.
STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED: bool = os.getenv(
    "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED", "true"
).strip().lower() in ("1", "true", "yes")
```

> **GOTCHA DURA 1:** un `default=True` que **no** esté en `_CURATED_DEFAULTS_ON`
> (`tests/test_harness_flags.py:467`) rompe `test_default_known_only_for_curated`. Agregala ahí.
> **GOTCHA DURA 2:** el consumidor lee **la instancia**: `getattr(_config.config, "STACKY_…", False)`.
> `getattr` del **módulo** devuelve el default y mata el branch OFF (el test flag-off pasa en falso).
> **GOTCHA DURA 3:** una flag nueva sin entrada en `_CATEGORY_KEYS` rompe el meta-test de categorías.

**Tests PRIMERO — `tests/test_plan252_capability_frontier.py` (10 casos):**

| Test | Qué congela |
|---|---|
| `test_catalogo_tiene_14_acciones_con_ids_unicos` | `len(ACTION_CATALOG) == 14` y los `id` no se repiten |
| `test_toda_accion_tiene_veredicto_y_motivo` (**KPI-3**) | `a.verdict in _DECLARED_VERDICTS` y `a.reason.strip() != ""` para las 14 |
| `test_depends_declara_al_menos_una_sonda` | `verdict == DEPENDS` ⟹ `len(a.probes) >= 1` y toda sonda ∈ `PROBE_IDS` |
| `test_can_y_cannot_no_declaran_sondas` | `verdict in (CAN, CANNOT)` ⟹ `a.probes == ()` |
| `test_cannot_declarado_no_lo_promueve_ninguna_sonda` | con `probes={p: True for p in PROBE_IDS}`, `create_service_connection` y `install_selfhosted_agent` siguen `CANNOT` |
| `test_probes_vacio_resuelve_unknown_nunca_can` | `resolve_frontier({})` → ninguna `DEPENDS` queda en `CAN` |
| `test_depends_con_una_sonda_true_resuelve_can` | `resolve_frontier({"ado_pat": True, "gitlab_token": False, "repo_writer": True})` → `register_pipeline_definition` es `CAN` |
| `test_needs_deploy_filtra_acciones` | `pipeline_deploys=False` → 12 acciones; `True` → 14 |
| `test_manual_y_automatic_son_particion` | `set(manual) ∩ set(automatic) == ∅` y `len(manual) + len(automatic) == len(resolved)` |
| `test_modulos_sin_ejecucion_remota` (**§3, fuera de scope duro**) | el **texto fuente** de `pipeline_capability_frontier.py` **y** de `pipeline_handoff_bundle.py` no contiene `subprocess`, `paramiko`, `winrm`, `socket` ni `requests` |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan252_capability_frontier.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio de aceptación BINARIO:** los 10 tests pasan **y** `test_harness_flags.py` y
`test_harness_ratchet_meta.py` quedan verdes.
*(Nota: `test_modulos_sin_ejecucion_remota` referencia `pipeline_handoff_bundle.py`, que nace en
F2. En F0 el test debe **saltear** el archivo que aún no existe con `pytest.skip` explícito por
archivo faltante — NUNCA con un `try/except` mudo — y en F2 deja de saltear. El skip se declara
acá para que no sea una sorpresa.)*

**Flag:** `STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED`, default **ON**. En F0 el módulo es puro y **no
lee la flag**: la flag gatea el endpoint (F4) y el panel (F5).

**Impacto por runtime:** ninguno — módulo puro sin LLM. **Fallback:** no aplica (no hay nada que
degradar). Idéntico en Codex CLI / Claude Code CLI / Copilot Pro / sin runtime.

**Trabajo del operador: ninguno.**

---

### F1 — Sondas del estado real: la frontera deja de ser teórica

**Objetivo (1 frase):** resolver la frontera contra **el entorno de esta máquina, ahora**, sin red
y sin lanzar nunca.
**Valor:** el veredicto de cada acción refleja si el operador **hoy** tiene PAT/token/repo, no un
supuesto.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/pipeline_capability_frontier.py` (solo se **agrega** la capa de sondas al final)
- EDITAR `Stacky Agents/backend/tests/test_plan252_capability_frontier.py` (5 casos nuevos)

**Símbolos EXACTOS a agregar:**

```python
def _probe_ado_pat() -> Optional[bool]:
    """True/False si se pudo evaluar; None si el módulo no está disponible."""
    try:
        from services.ado_client import ado_pat_present   # ado_client.py:203
        return bool(ado_pat_present())
    except Exception:      # noqa: BLE001 — una sonda NUNCA tumba el bundle
        return None


def _probe_gitlab_token() -> Optional[bool]:
    """Espeja la precedencia documentada en gitlab_client.py:5 (env > archivo).
    NO existe un gitlab_token_present() al que delegar (§2.4, verificado)."""
    try:
        import os
        from runtime_paths import backend_root
        if (os.getenv("GITLAB_TOKEN") or "").strip():
            return True
        return (backend_root() / "auth" / "gitlab_auth.json").is_file()
    except Exception:      # noqa: BLE001
        return None


def _probe_repo_writer() -> Optional[bool]:
    try:
        from services.repo_writer import get_repo_writer
        return get_repo_writer() is not None
    except Exception:      # noqa: BLE001
        return None


_PROBE_FUNCS = {
    "ado_pat": _probe_ado_pat,
    "gitlab_token": _probe_gitlab_token,
    "repo_writer": _probe_repo_writer,
}


def probe_environment() -> dict:
    """Ejecuta las 3 sondas. NUNCA lanza. Devuelve dict[probe_id, bool | None]."""
    return {pid: fn() for pid, fn in _PROBE_FUNCS.items()}


def evaluate_frontier(*, pipeline_deploys: bool = False) -> list:
    """Azúcar: probe_environment() + resolve_frontier(). La ÚNICA función del
    módulo con I/O. Todo lo demás sigue siendo puro y testeable sin monkeypatch."""
    return resolve_frontier(probe_environment(), pipeline_deploys=pipeline_deploys)
```

**Casos borde:** `ado_client` no importable (deploy recortado) → `None` → `UNKNOWN` →
tratado como `CANNOT_NOW` → el README **suma** un paso manual en vez de omitirlo. **Falla
cerrado.** `GITLAB_TOKEN=""` (string vacío) → `False`, no `True`. Excepción dentro de
`get_repo_writer()` → `None`, sin traceback al operador.

**Tests PRIMERO — 5 casos nuevos en `test_plan252_capability_frontier.py`:**

| Test | Qué congela |
|---|---|
| `test_probe_environment_devuelve_las_3_sondas` | claves == `set(PROBE_IDS)`; cada valor ∈ `{True, False, None}` |
| `test_probe_nunca_lanza` | monkeypatch de `services.ado_client.ado_pat_present` para que lance `RuntimeError` → `probe_environment()["ado_pat"] is None` (no propaga) |
| `test_probe_gitlab_env_vacia_es_false` | `monkeypatch.setenv("GITLAB_TOKEN", "")` + `backend_root` a un `tmp_path` sin `auth/` → `False` |
| `test_probe_gitlab_env_con_valor_es_true` | `monkeypatch.setenv("GITLAB_TOKEN", "x")` → `True` |
| `test_evaluate_frontier_no_lanza_y_es_deterministico` | dos llamadas seguidas devuelven la **misma** lista de `(id, effective)` |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan252_capability_frontier.py -q`

**Criterio BINARIO:** los 15 tests del archivo (10 de F0 + 5 de F1) pasan.

**Flag:** la de F0 (el módulo sigue sin leerla).
**Impacto por runtime:** ninguno; cero LLM, cero red. **Fallback:** sonda no evaluable → `UNKNOWN`
→ paso manual. **Trabajo del operador: ninguno.**

---

### F2 — El núcleo del paquete: manifest + README por plantilla + degradación honesta

**Objetivo (1 frase):** construir, de forma **pura y determinista**, el `dict[str, str]` con todos
los archivos del paquete, incluido el `README.md` renderizado por plantilla.
**Valor:** los 5 puntos del operador, ya resueltos como dato; F3 solo los comprime.

**Archivos:**
- CREAR `Stacky Agents/backend/services/pipeline_handoff_bundle.py`
- CREAR `Stacky Agents/backend/tests/test_plan252_handoff_bundle.py`
- EDITAR `run_harness_tests.sh` (**:20**) y `run_harness_tests.ps1` (**:13**)

**Símbolos EXACTOS:**

```python
"""services/pipeline_handoff_bundle.py — Plan 252 F2/F3. Paquete de entrega.

PURO salvo `persist_bundle` (F3). El README sale de PLANTILLA, jamás de un LLM:
por eso la paridad de los 3 runtimes es trivial.

PROHIBIDO (congelado por test_modulos_sin_ejecucion_remota): subprocess, paramiko,
winrm, socket, requests.
"""
MANIFEST_VERSION = 1
BUNDLE_ID_LEN = 16
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)     # F3 — reproducibilidad (§2.3)
MAX_BUNDLE_BYTES = 20 * 1024 * 1024    # 20 MB; por encima → error explícito
_BUNDLES_DIRNAME = "pipeline_handoff/bundles"   # data_dir()/pipeline_handoff/bundles/<bundle_id>/


class HandoffError(RuntimeError): ...
class HandoffSecretError(HandoffError): ...      # F3 — gate anti-secreto
class HandoffTooLargeError(HandoffError): ...


@dataclass(frozen=True)
class HandoffStep:
    """Espeja campo por campo a validation_playbook.ValidationStep (:121) —
    n / action / expected_result / source — y AGREGA lo que un paso de servidor
    necesita: dónde, con qué comando, y qué hacer si falla."""
    n: int
    action: str
    expected_result: str      # OBLIGATORIO no vacío
    source: str               # OBLIGATORIO no vacío ("frontier:install_selfhosted_agent")
    where: str                # "servidor destino" | "web de Azure DevOps" | "tu máquina"
    command: str              # OBLIGATORIO no vacío; "-" si de verdad no hay comando
    on_failure: str           # OBLIGATORIO no vacío
    lang: str = "powershell"  # para el fence del markdown
    repeatable: bool = True

    def __post_init__(self):
        for campo in ("action", "expected_result", "source", "where", "command", "on_failure"):
            if not str(getattr(self, campo)).strip():
                raise HandoffError(f"HandoffStep.{campo} no puede estar vacío (KPI-4)")


@dataclass(frozen=True)
class HandoffVariable:
    name: str
    where: str
    format_hint: str
    secret: bool          # de services.ci_variables.looks_secret(name) (:31)
    # INVARIANTE: NO existe un campo `value`. No se puede filtrar lo que no se modela.


@dataclass(frozen=True)
class BundleInputs:
    pipeline_name: str
    provider: str                       # "ado" | "gitlab"
    yaml_files: dict                    # {"pipelines/ci.yml": "<texto>"}
    script_files: dict = field(default_factory=dict)   # {"scripts/Deploy-Local.ps1": "<texto>"}
    variables: tuple = ()               # tuple[HandoffVariable, ...]
    pipeline_deploys: bool = False
    degraded: tuple = ()                # ids de módulos ausentes (ver DEGRADED_CONSEQUENCE)


DEGRADED_CONSEQUENCE = {
    "pipeline_inventory":   "no se pudo cruzar con las pipelines ya existentes: revisá a mano que el nombre no choque con una definición registrada (plan 246)",
    "pipeline_profiler":    "el propósito y el stack del pipeline no están descritos en este README (plan 247)",
    "pipeline_environments": "las variables por entorno se dedujeron de los placeholders del YAML en vez de la matriz de entornos, así que la lista puede estar incompleta (plan 251)",
}

PREREQUISITES = ( ... )   # tuple[HandoffStep, ...] — ver abajo
FINAL_CHECKS = ( ... )    # tuple[dict, ...] con claves {"check", "command"}


def collect_inputs(spec_dict, *, pipeline_name, provider, yaml_files, script_files=None) -> BundleInputs: ...
def build_steps(resolved_frontier: list) -> tuple: ...
def build_manifest(inputs: BundleInputs, resolved_frontier: list) -> dict: ...
def render_readme(manifest: dict) -> str: ...
def build_files(inputs: BundleInputs, resolved_frontier: list) -> dict: ...
def compute_bundle_id(files: dict) -> str: ...
```

**`collect_inputs` — degradación honesta (KPI-5), la parte que hace este plan implementable hoy:**

```python
def collect_inputs(spec_dict, *, pipeline_name, provider, yaml_files, script_files=None):
    degraded = []
    variables = []
    # 251 — matriz de entornos. Si no está, se degrada al preflight que YA existe.
    try:
        from services import pipeline_environments          # plan 251 — HOY NO EXISTE (§2.4)
        variables = _variables_from_env_matrix(pipeline_environments, spec_dict)
    except ImportError:
        degraded.append("pipeline_environments")
        variables = _variables_from_preflight(spec_dict)    # fallback determinista
    for mod, key in (("pipeline_inventory", "pipeline_inventory"),
                     ("pipeline_profiler", "pipeline_profiler")):
        try:
            __import__(f"services.{mod}")
        except ImportError:
            degraded.append(key)
    ...
```

`_variables_from_preflight(spec_dict)` **no inventa nada**: usa
`pipeline_preflight.referenced_variables(spec_dict, target)` (`:79`) para las variables
referenciadas y `pipeline_preflight.check_placeholders(spec_dict)` (`:37`) para los pasos que
todavía tienen el comando de ejemplo, y marca `secret=ci_variables.looks_secret(name)` (`:31`).
`where` = `"Pipelines → Library / variables de la pipeline"` para ADO,
`"Settings → CI/CD → Variables"` para GitLab.

**`build_steps(resolved_frontier) -> tuple[HandoffStep, ...]` — el corazón del punto (5):**
- Recorre `frontier.manual_actions(resolved_frontier)` **en orden de catálogo** y emite **un
  `HandoffStep` por acción manual**, tomando `action` de `action.label`, `source` de
  `f"frontier:{action.id}"` y `on_failure`/`command`/`expected_result`/`where` de
  `_STEP_TEMPLATES[action.id]` — un `dict` literal, cerrado, en el módulo.
- **Ninguna acción `CAN` produce un paso** (KPI-3, `test_ninguna_accion_can_es_paso_manual`).
- Numeración `n` = 1..N consecutiva **después** del filtrado, para que el README no salte números.
- `_STEP_TEMPLATES` cubre **las 5 acciones que pueden quedar manuales sin sonda**
  (`set_pipeline_secrets`, `create_service_connection`, `install_selfhosted_agent`,
  `install_server_prerequisites`, y las `DEPENDS` que caen a `CANNOT_NOW`). Si un `action.id`
  llegara sin plantilla, **lanza `HandoffError`** con el id: preferimos romper en un test a emitir
  un README con un paso vacío.

Ejemplo del contenido literal de `_STEP_TEMPLATES["install_selfhosted_agent"]` (los otros siguen
el mismo molde y salen de la columna *Qué queda manual* de §5):

```python
"install_selfhosted_agent": dict(
    where="servidor destino (sesión de administrador)",
    lang="powershell",
    command=(
        "# 1) En ADO: Project settings -> Agent pools -> <pool> -> New agent -> Windows x64 -> Download\n"
        "# 2) En el SERVIDOR, en una consola como administrador:\n"
        "mkdir C:\\agent; cd C:\\agent\n"
        "Add-Type -AssemblyName System.IO.Compression.FileSystem\n"
        "[System.IO.Compression.ZipFile]::ExtractToDirectory(\"$HOME\\Downloads\\vsts-agent-win-x64.zip\", \"C:\\agent\")\n"
        ".\\config.cmd --unattended --url <URL_DE_TU_ORGANIZACION> --auth pat --pool <NOMBRE_DEL_POOL> --runAsService\n"
        "# El PAT te lo pide de forma interactiva: NO lo pegues en este archivo."
    ),
    expected_result=(
        "En ADO, Project settings -> Agent pools -> <pool> muestra el agente con el punto VERDE "
        "y estado 'Online'. En el servidor, `Get-Service vstsagent*` devuelve Status=Running."
    ),
    on_failure=(
        "Si el agente queda 'Offline': revisá que el servicio esté corriendo y que el servidor "
        "salga a internet por HTTPS hacia dev.azure.com. El log vive en C:\\agent\\_diag\\."
    ),
    repeatable=False,
),
```

**`PREREQUISITES` (3, literales — sección 3 del README):**
1. *"Tenés acceso de administrador al servidor destino"* — comando
   `whoami /groups | findstr /i "S-1-5-32-544"` — esperado: *"aparece al menos una línea (grupo
   Administradores)"*.
2. *"El servidor sale a internet por HTTPS"* — comando
   `Test-NetConnection dev.azure.com -Port 443` — esperado: *"`TcpTestSucceeded : True`"*.
3. *"Tenés permiso de escritura en la carpeta de destino del deploy"* — comando
   `New-Item -ItemType File -Path "<RUTA_DESTINO>\stacky.probe" -Force; Remove-Item "<RUTA_DESTINO>\stacky.probe"`
   — esperado: *"ninguno de los dos comandos imprime un error"*.

**`FINAL_CHECKS` (3, literales — sección 6 del README):**
1. *"La pipeline aparece listada en el proveedor"* — `# Pipelines -> buscar por nombre: {pipeline_name}`.
2. *"La primera corrida terminó en verde"* — `# Pipelines -> {pipeline_name} -> última corrida -> estado 'Succeeded'"`.
3. *"El artefacto/deploy llegó al destino"* — `Get-ChildItem "<RUTA_DESTINO>" | Select-Object -First 5`.

**`build_manifest` — shape EXACTO (sin `generated_at`, §2.3):**

```json
{
  "manifest_version": 1,
  "catalog_version": "252.1",
  "bundle_id": "<sha256 del mapa de archivos, 16 hex>",
  "pipeline_name": "...",
  "provider": "ado",
  "degraded": ["pipeline_environments"],
  "frontier": [{"id": "...", "label": "...", "effective": "CAN|CANNOT|CANNOT_NOW|UNKNOWN",
                "reason": "...", "probe_detail": "..."}],
  "steps": [{"n": 1, "action": "...", "where": "...", "command": "...",
             "expected_result": "...", "on_failure": "...", "source": "...",
             "lang": "powershell", "repeatable": false}],
  "prerequisites": [ ... ],
  "variables": [{"name": "ADO_PAT", "where": "...", "format_hint": "...", "secret": true}],
  "final_checks": [ ... ],
  "files": [{"path": "pipelines/ci.yml", "kind": "yaml", "bytes": 1234}]
}
```

Se serializa con `json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True)` — **igual que
`dbcompare_scripts.py:1194`** — para que el texto sea estable.

**`build_files(inputs, resolved) -> dict[str, str]`**: `{**yaml_files, **script_files,
"MANIFEST.json": <json>, "README.md": render_readme(manifest)}`. **El `bundle_id` se calcula sobre
el mapa SIN `MANIFEST.json` ni `README.md`** (que lo contienen) y recién después se inyecta: si no,
es una referencia circular. Congelado por `test_bundle_id_no_es_circular`.

**Tests PRIMERO — `tests/test_plan252_handoff_bundle.py` (13 casos):**

| Test | Qué congela |
|---|---|
| `test_paso_sin_validacion_es_rechazado` (**KPI-4**) | `HandoffStep(..., expected_result="")` lanza `HandoffError`; idem con `command=""` y `on_failure=""` |
| `test_variable_no_modela_valor` | `HandoffVariable` **no tiene** campo `value` (`dataclasses.fields` → nombres exactos) |
| `test_ninguna_accion_can_es_paso_manual` (**KPI-3**) | con `probes` todo `True`, `build_steps` no emite ningún paso cuyo `source` apunte a una acción `CAN` |
| `test_todo_id_manual_tiene_plantilla` | para cada acción del catálogo que pueda quedar manual, `_STEP_TEMPLATES` la cubre; si no, `HandoffError` con el id |
| `test_pasos_numerados_sin_huecos` | `[s.n for s in steps] == list(range(1, len(steps)+1))` |
| `test_bundle_sin_246_247_251_igual_se_arma` (**KPI-5**) | con los 3 módulos ausentes, `build_files` devuelve un dict con `README.md` y `MANIFEST.json`, y `manifest["degraded"] == ["pipeline_inventory","pipeline_profiler","pipeline_environments"]` (ordenado) |
| `test_degraded_aparece_en_el_readme` | el README contiene el texto de `DEGRADED_CONSEQUENCE["pipeline_environments"]` |
| `test_readme_tiene_las_8_secciones` | los 8 encabezados `## N.` de §6, en orden |
| `test_readme_no_tiene_placeholders_sin_sustituir` | `"{" not in readme.replace("${{", "")` (las expresiones ADO del YAML no cuentan; el README no las lleva) |
| `test_manifest_no_tiene_timestamp` (**§2.3**) | `"generated_at" not in manifest` y ninguna clave del manifest matchea `r"(_at|timestamp|date)$"` |
| `test_bundle_id_estable` (**KPI-1, mitad pura**) | `compute_bundle_id(files) == compute_bundle_id(dict(reversed(list(files.items()))))` — el orden de inserción **no** afecta |
| `test_bundle_id_no_es_circular` | `build_files` no lanza `RecursionError` y `manifest["bundle_id"]` tiene 16 chars hex |
| `test_vocabulario_espeja_al_209` | los campos `n`, `action`, `expected_result`, `source` de `HandoffStep` existen con esos nombres exactos, comparados contra `[f.name for f in dataclasses.fields(validation_playbook.ValidationStep)]` (`validation_playbook.py:121`) |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan252_handoff_bundle.py -q`
Y re-correr `tests/test_plan252_capability_frontier.py` (el `skip` de
`test_modulos_sin_ejecucion_remota` ahora **debe dejar de saltear** y pasar).

**Criterio BINARIO:** los 13 tests pasan **y** `test_modulos_sin_ejecucion_remota` deja de estar
en `skipped` y queda `passed`.

**Flag:** la de F0 (el módulo no la lee; la gatea el endpoint).
**Impacto por runtime:** ninguno. **README por plantilla ⇒ el texto es idéntico bit a bit en
Codex, Claude Code y Copilot.** Ese es el punto. **Fallback:** no aplica.
**Trabajo del operador: ninguno.**

---

### F3 — Zip determinista + gate anti-secreto que falla cerrado + persistencia atómica

**Objetivo (1 frase):** convertir el `dict[str, str]` en un `.zip` **byte-idéntico entre corridas**
y **sin un solo secreto adentro**, o no producirlo en absoluto.
**Valor:** KPI-1 y KPI-2, los dos requisitos duros del pedido.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/pipeline_handoff_bundle.py` (se **agrega** al final)
- CREAR `Stacky Agents/backend/tests/test_plan252_zip_determinismo.py`
- EDITAR `run_harness_tests.sh` (**:20**) y `run_harness_tests.ps1` (**:13**)

**Símbolos EXACTOS:**

```python
_SECRET_CLASS = "secrets"


def scrub_files(files: dict) -> dict:
    """Capa 1 (preventiva): masking canónico del Plan 195 sobre TODO texto.
    Reusa services.secret_masking.mask_token_values (secret_masking.py:20)."""
    from services.secret_masking import mask_token_values
    return {path: mask_token_values(text) for path, text in files.items()}


def assert_no_secrets(files: dict) -> None:
    """Capa 2 (gate): si QUEDA un secreto tras el scrub, LANZA HandoffSecretError.
    Falla cerrado (§4.5): no enmascara y sigue.

    Usa egress_policies.detect_classes (egress_policies.py:96) pero SOLO mira la
    clase "secrets" (:81-92). TRAMPA VERIFICADA: detect_classes también devuelve
    "pii" ante \\b\\d{7,8}\\b — un build number como 20260726 la dispara — y
    "production" ante la palabra "produccion", que un README de deploy va a tener
    sí o sí. Bloquear por el set completo dejaría el bundle inconstruible."""
    from services.secret_masking import MASK_PLACEHOLDER
    from services.egress_policies import detect_classes
    ofensores = []
    for path, text in sorted(files.items()):
        if _SECRET_CLASS in detect_classes(text):
            ofensores.append(path)
    if ofensores:
        raise HandoffSecretError(
            "El paquete NO se generó: se detectó material sensible en "
            + ", ".join(ofensores)
            + ". Quitá el valor del origen (el paquete solo debe nombrar variables, nunca sus "
              "valores) y volvé a intentar. Marcador de masking: " + MASK_PLACEHOLDER
        )


def zip_bytes(files: dict) -> bytes:
    """Zip REPRODUCIBLE (§2.3). Mismas entradas → mismos bytes, siempre.
    NUNCA usa zf.write(ruta) (tomaría el mtime del disco) ni zf.writestr(str, ...)
    (usaría time.localtime()): siempre ZipInfo explícito con _ZIP_EPOCH."""
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname in sorted(files):                    # orden estable
            info = zipfile.ZipInfo(arcname.replace("\\", "/"), date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16             # permisos fijos
            info.create_system = 0                       # 0 = FAT/Windows, fijo
            zf.writestr(info, files[arcname].encode("utf-8"))
    return buf.getvalue()


def build_bundle(inputs: BundleInputs, resolved_frontier: list) -> tuple:
    """Camino ÚNICO de generación. Devuelve (bundle_id, zip_bytes_, manifest).
    Orden NO negociable: build_files → scrub → assert_no_secrets → tope → zip."""
    files = build_files(inputs, resolved_frontier)
    files = scrub_files(files)
    assert_no_secrets(files)                    # ← si hay secreto, NO hay zip
    data = zip_bytes(files)
    if len(data) > MAX_BUNDLE_BYTES:
        raise HandoffTooLargeError(f"el paquete pesa {len(data)} bytes (tope {MAX_BUNDLE_BYTES})")
    return json.loads(files["MANIFEST.json"])["bundle_id"], data, json.loads(files["MANIFEST.json"])


def persist_bundle(bundle_id: str, data: bytes) -> Path:
    """Escritura ATÓMICA, espejando dbcompare_scripts._write_bundle_atomic (:1207):
    escribe a <id>.zip.tmp y recién ahí os.replace. Un lector nunca ve un zip parcial."""


def bundle_path(bundle_id: str) -> Optional[Path]:
    """bundle_id es una CLAVE, jamás parte de una ruta construida a ciegas
    (docstring literal de solution_builder.artifact_zip_path, :410-411).
    Valida ^[0-9a-f]{16}$ ANTES de tocar el filesystem; si no matchea → None."""


def prune_bundles(max_age_hours: int = 72, keep_last: int = 20) -> int:
    """Vida útil del artefacto. Best-effort, nunca lanza. Devuelve cuántos borró."""


def append_ledger(bundle_id: str, manifest: dict) -> None:
    """JSONL en data_dir()/pipeline_handoff/bundles.jsonl. ACÁ SÍ va el timestamp
    (fuera del zip, §2.3). Best-effort: un fallo de ledger nunca tumba la descarga."""
```

**Casos borde:** `files` vacío → `HandoffError` (un paquete sin archivos no es un paquete).
Un archivo con `\r\n` → se escribe tal cual (el contenido es responsabilidad de F2; el zip no
normaliza, porque normalizar rompería un `.ps1` que necesita CRLF). `bundle_id` con `../` o
mayúsculas → no matchea `^[0-9a-f]{16}$` → `bundle_path` devuelve `None` **sin tocar el disco**.

**Tests PRIMERO — `tests/test_plan252_zip_determinismo.py` (9 casos):**

| Test | Qué congela |
|---|---|
| `test_zip_es_byte_identico_en_dos_corridas` (**KPI-1**) | `zip_bytes(f) == zip_bytes(f)` y ambos `sha256` iguales, con un `os.utime` de por medio sobre un archivo homónimo en `tmp_path` (prueba que el mtime del disco es irrelevante) |
| `test_zip_ignora_el_orden_de_insercion` | `zip_bytes(f) == zip_bytes(dict(reversed(list(f.items()))))` |
| `test_zip_usa_epoch_fijo` | `zipfile.ZipFile(BytesIO(data)).infolist()[0].date_time == (1980, 1, 1, 0, 0, 0)` para **todas** las entradas |
| `test_zip_arcnames_con_barra_posix` | ninguna entrada de `namelist()` contiene `\\` |
| `test_secreto_sembrado_aborta_el_bundle` (**KPI-2**) | con `"glpat-" + "x"*20` (**literal PARTIDO** — gotcha de push-protection de GitHub) dentro de un `.ps1` de entrada, `build_bundle` lanza `HandoffSecretError` y **no** deja archivo en `data_dir()` |
| `test_secreto_en_el_readme_tambien_aborta` | ídem sembrando en un `format_hint` de `HandoffVariable` |
| `test_build_number_de_8_digitos_no_bloquea` (**la trampa de §F3**) | un README con `20260726` **sí** se empaqueta (la clase `pii` no bloquea) |
| `test_palabra_produccion_no_bloquea` | un README que contiene `"producción"` **sí** se empaqueta (la clase `production` no bloquea) |
| `test_bundle_path_rechaza_traversal` | `bundle_path("../../etc/passwd")`, `bundle_path("ABCD")`, `bundle_path("")` → `None`, y `tmp_path` queda sin cambios |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan252_zip_determinismo.py -q`

**Criterio BINARIO:** los 9 tests pasan **y**
`grep -n "date_time=_ZIP_EPOCH" "Stacky Agents/backend/services/pipeline_handoff_bundle.py"` → ≥1 match
**y** `grep -cn "zf.write(" "Stacky Agents/backend/services/pipeline_handoff_bundle.py"` → **0**.

**Flag:** la de F0. **Impacto por runtime:** ninguno; `zipfile`/`hashlib` son stdlib.
**Fallback:** no aplica. **Trabajo del operador: ninguno.**

---

### F4 — El blueprint: preview, build y descarga con las tres guardas

**Objetivo (1 frase):** exponer la frontera y el paquete por HTTP, con el guard de flag
per-request y el guard anti path-traversal del Plan 201 F7.
**Valor:** el punto (2) del operador — *"una opción para descargarlos en un único paquete"*.

**Archivos:**
- CREAR `Stacky Agents/backend/api/pipeline_handoff.py`
- EDITAR `Stacky Agents/backend/api/__init__.py` (registrar el blueprint sobre `api_bp`)
- CREAR `Stacky Agents/backend/tests/test_plan252_handoff_api.py`
- EDITAR `run_harness_tests.sh` (**:20**) y `run_harness_tests.ps1` (**:13**)

**Molde EXACTO** (copiado de `api/pipeline_generator.py:1-24,36-37`):

```python
"""api/pipeline_handoff.py — Blueprint del paquete de entrega. Plan 252 F4.

url_prefix="/pipeline-handoff" → ruta final /api/pipeline-handoff/...
NO poner url_prefix="/api/pipeline-handoff" (daría /api/api/...) y NO registrar en app.py.
Guard de la flag PER-REQUEST (abort(404)) — nunca gateado en el registro del blueprint.

Este blueprint NO ejecuta nada fuera del proceso de Stacky. Solo arma y sirve archivos.
"""
import config as _config
from flask import Blueprint, abort, jsonify, request, current_app

bp = Blueprint("pipeline_handoff", __name__, url_prefix="/pipeline-handoff")


def _guard():
    if not getattr(_config.config, "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED", False):
        abort(404)   # per-request
```

**Endpoints (3):**

| Método | Ruta final | Body / params | Respuesta |
|---|---|---|---|
| `GET` | `/api/pipeline-handoff/frontier` | `?deploys=true|false` | `200 {"catalog_version": "252.1", "actions": [{id, label, effective, reason, probe_detail}]}` |
| `POST` | `/api/pipeline-handoff/build` | `{pipeline_name, provider, spec, yaml_files, script_files?}` | `200 {"bundle_id", "bytes", "manifest"}` · `400` body inválido · `409 {"error": "<mensaje de HandoffSecretError>"}` · `413` sobre el tope |
| `GET` | `/api/pipeline-handoff/<bundle_id>/download` | — | `200` `application/zip` · `400` fuera de la raíz · `404` desconocido |

**Guard de descarga (obligatorio, espejo literal del 201 F7 `:806-819`):**

```python
@bp.get("/<bundle_id>/download")
def download_route(bundle_id):
    _guard()
    path = pipeline_handoff_bundle.bundle_path(bundle_id)   # valida ^[0-9a-f]{16}$ adentro
    if path is None:
        abort(404)
    root = (data_dir() / "pipeline_handoff" / "bundles").resolve()
    target = Path(path).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        abort(400)                       # defensa en profundidad
    if not target.exists():
        abort(404)
    if target.stat().st_size > pipeline_handoff_bundle.MAX_BUNDLE_BYTES:
        abort(413)
    return send_file(str(target), mimetype="application/zip", as_attachment=True,
                     download_name=f"stacky-handoff-{bundle_id}.zip")
```

- `bundle_id` **NUNCA se interpola en una ruta**: es una **clave** que `bundle_path` valida contra
  `^[0-9a-f]{16}$` antes de tocar el filesystem, exactamente como `artifact_zip_path`
  (`solution_builder.py:410-411`).
- El nombre de descarga lleva el `bundle_id`, no una fecha: dos descargas del mismo paquete dan el
  mismo nombre **y el mismo archivo**.
- `POST /build` llama `prune_bundles()` **después** de persistir (vida útil: 72 h o 20 paquetes,
  lo que ocurra primero) y `append_ledger()`. Ningún fallo de prune/ledger aborta la respuesta.

**`POST /build` es HITL por construcción:** solo corre cuando el operador clickea; **no hay ningún
scheduler, watcher ni hook que lo dispare**. Congelado por
`test_ningun_hook_dispara_build` (grep sobre `backend/` de `pipeline_handoff_bundle.build_bundle`
→ los únicos call-sites son `api/pipeline_handoff.py` y los tests).

**Tests PRIMERO — `tests/test_plan252_handoff_api.py` (10 casos, Flask test client + `monkeypatch`
de `runtime_paths.data_dir` a `tmp_path`):**

| Test | Qué congela |
|---|---|
| `test_flag_off_404_en_los_3_endpoints` | con la flag OFF, los 3 devuelven `404` |
| `test_frontier_devuelve_14_acciones` | `GET /frontier?deploys=true` → `len(actions) == 14`, todas con `reason` no vacío |
| `test_frontier_sin_deploys_devuelve_12` | `?deploys=false` → 12 |
| `test_build_devuelve_bundle_id_y_persiste` | `POST /build` → `200`, y existe `tmp_path/pipeline_handoff/bundles/<id>.zip` |
| `test_build_es_idempotente` (**KPI-1 end-to-end**) | dos `POST /build` con el **mismo** body → el **mismo** `bundle_id` y el mismo `sha256` del archivo |
| `test_build_con_secreto_devuelve_409` (**KPI-2**) | body con `"glpat-" + "y"*20` (literal PARTIDO) → `409` y **cero archivos** en el directorio de bundles |
| `test_download_ok` (**KPI-6**) | `GET /<id>/download` → `200`, `Content-Type: application/zip`, y `zipfile.ZipFile(BytesIO(r.data)).namelist()` contiene `README.md` y `MANIFEST.json` |
| `test_download_desconocido_404` (**KPI-6**) | id válido en formato pero inexistente → `404` |
| `test_download_traversal_404` (**KPI-6**) | `GET /..%2f..%2fetc%2fpasswd/download` → `404` (no `500`) |
| `test_download_fuera_de_raiz_400` (**KPI-6**) | `monkeypatch` de `bundle_path` a una ruta fuera de la raíz → `400` |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan252_handoff_api.py -q`

**Criterio BINARIO:** los 10 tests pasan **y**
`grep -n "commonpath" "Stacky Agents/backend/api/pipeline_handoff.py"` → ≥1 match.

**Flag:** `STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED`, default **ON**. OFF → los 3 endpoints `404`,
idéntico a como si el blueprint no existiera.
**Impacto por runtime:** ninguno; HTTP + stdlib. **Fallback:** no aplica.
**Trabajo del operador: ninguno.**

---

### F5 — El panel: un botón, una tabla de frontera y una descarga

**Objetivo (1 frase):** que el operador vea, dentro de la sección Pipelines que ya usa, qué hace
Stacky, qué le toca a él, y un botón para bajarse el paquete.
**Valor:** cierra los 5 puntos del pedido en la UI.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/devops/pipelineHandoffModel.ts` (**modelo PURO** — toda la lógica va acá)
- CREAR `Stacky Agents/frontend/src/devops/__tests__/pipelineHandoffModel.test.ts`
- CREAR `Stacky Agents/frontend/src/components/devops/PipelineHandoffPanel.tsx`
- CREAR `Stacky Agents/frontend/src/components/devops/PipelineHandoffPanel.module.css`
- EDITAR `Stacky Agents/frontend/src/api/endpoints.ts` (agregar `PipelineHandoff`, junto a `PipelineGenerator` **:4426**)
- EDITAR `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` (una entrada nueva en el array de secciones, molde `:126-131`)

**`pipelineHandoffModel.ts` — símbolos EXACTOS (puro, sin `fetch`, sin React):**

```typescript
export type FrontierVerdict = 'CAN' | 'CANNOT' | 'CANNOT_NOW' | 'UNKNOWN';

export interface FrontierAction {
  id: string; label: string; effective: FrontierVerdict; reason: string; probe_detail: string;
}

/** Lo que hizo Stacky (verde). */
export function automaticActions(actions: FrontierAction[]): FrontierAction[];
/** Lo que le toca al operador (ámbar/gris). Partición exacta con la anterior. */
export function manualActions(actions: FrontierAction[]): FrontierAction[];
/** Texto de una línea para el encabezado: "Stacky resuelve 9 de 14; 5 quedan para vos". */
export function frontierSummary(actions: FrontierAction[]): string;
/** UNKNOWN y CANNOT_NOW se explican distinto que CANNOT: uno es "hoy no", el otro "nunca". */
export function verdictLabel(v: FrontierVerdict): string;
/** null si el paquete se puede pedir; string con el motivo si no. */
export function blockedReason(args: { flagOn: boolean; yamlCount: number }): string | null;
```

`verdictLabel` devuelve **exactamente**: `CAN` → `"Lo hace Stacky"`; `CANNOT` → `"Lo hacés vos"`;
`CANNOT_NOW` → `"Lo hacés vos por ahora"`; `UNKNOWN` → `"Lo hacés vos (Stacky no pudo verificarlo)"`.

**`endpoints.ts` — agregar después de `PipelineGenerator` (`:4426-4435`), reusando el patrón de
descarga de `DevOpsServers.downloadSetupScripts` (`:4037-4049`) LITERAL:**

```typescript
/** Plan 252 — frontera de capacidades + paquete de entrega. */
export const PipelineHandoff = {
  frontier: (deploys: boolean) =>
    api.get<{ catalog_version: string; actions: FrontierAction[] }>(
      `/api/pipeline-handoff/frontier?deploys=${deploys ? 'true' : 'false'}`),
  build: (body: object) =>
    api.post<{ bundle_id: string; bytes: number; manifest: object }>(
      '/api/pipeline-handoff/build', body),
  download: async (bundleId: string) => {
    const response = await fetch(`/api/pipeline-handoff/${encodeURIComponent(bundleId)}/download`);
    if (!response.ok) throw new Error(`Descarga falló: ${response.statusText}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `stacky-handoff-${bundleId}.zip`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
};
```

> **GOTCHA (Plan 196):** `api.post`/`api.get` **lanzan** ante un status non-2xx. El `409` del gate
> anti-secreto **es un caso esperado**, no un crash: `PipelineHandoffPanel.tsx` envuelve el
> `build` en `try/catch` y muestra el mensaje del error en un banner, sin romper el panel.

**`PipelineHandoffPanel.tsx` — comportamiento EXACTO:**
1. Al montar: `PipelineHandoff.frontier(deploys)` y renderiza **dos listas** — *"Lo hace Stacky"* y
   *"Lo hacés vos"* — con `verdictLabel` y el `reason` de cada acción. Encabezado =
   `frontierSummary(actions)`.
2. Botón **"Descargar paquete de entrega"**, deshabilitado si `blockedReason(...) !== null`, con el
   motivo como `title`.
3. Al clickear: `build` → si `200`, `download(bundle_id)`; si lanza, banner con el mensaje.
4. **Nada se dispara solo.** Sin `useEffect` que buildee, sin polling, sin autodescarga. Espeja el
   contrato UX del panel (`PipelineBuilderSection.tsx:382-383`): la IA/el sistema propone, el
   operador decide.

> **GOTCHA (ratchet UI):** `uiDebtRatchet` exige **cero `style={{}}`** en archivos `.tsx` nuevos.
> Todo estilo va en `PipelineHandoffPanel.module.css`, con `var(--token)` y **sin literales HEX**.

**`DevOpsPage.tsx` — entrada nueva** (molde exacto de `:126-131` + el patrón de gate de `:132-140`):

```tsx
  {
    id: 'paquete-entrega',
    label: 'Paquete de entrega',
    group: 'construir',
    summary: 'Qué hace Stacky, qué te toca a vos, y el .zip con el README',
    healthKey: 'pipeline_handoff_bundle_enabled',
    gateFlagKey: 'STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED',
    gateMessage: 'La sección Paquete de entrega necesita la flag STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <PipelineHandoffPanel ctx={ctx} />,
  },
```

> **Instrucción ejecutable (no inferir):** `healthKey` debe existir en el payload de
> `/api/diag/health`. Correr
> `grep -n "publications_enabled\|environments_enabled" "Stacky Agents/backend/api/diag.py"`,
> leer cómo se arma ese dict, y agregar `"pipeline_handoff_bundle_enabled"` **de la misma forma**.
> Si el health no expone la flag, el `FlagGateBanner` mostraría el gate **siempre**.

**Tests PRIMERO — `src/devops/__tests__/pipelineHandoffModel.test.ts` (6 casos, vitest;
**sin** `@testing-library/react` — no está instalado, gap conocido):**

| Test | Qué congela |
|---|---|
| `automaticActions y manualActions son partición` | unión == total, intersección == ∅ |
| `manualActions incluye UNKNOWN` | una acción `UNKNOWN` cae del lado manual, **nunca** del automático |
| `frontierSummary cuenta bien` | 9 `CAN` de 14 → texto con `"9"` y `"14"` |
| `verdictLabel cubre los 4 veredictos` | los 4 textos exactos; ningún `undefined` |
| `blockedReason sin yaml` | `{flagOn: true, yamlCount: 0}` → string no vacío |
| `blockedReason feliz` | `{flagOn: true, yamlCount: 1}` → `null` |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineHandoffModel.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** los 6 tests pasan **y** `npx tsc --noEmit` sin errores nuevos **y**
`grep -c "style={{" "Stacky Agents/frontend/src/components/devops/PipelineHandoffPanel.tsx"` → **0**.

**Smoke manual (1 paso, no automatizable — gap RTL/jsdom conocido):** panel DevOps → Construir →
Paquete de entrega → el botón baja un `.zip`; abrirlo y confirmar que el `README.md` tiene sus 8
secciones y que **ninguna** contiene un valor secreto.

**Flag:** la de F0. OFF → la sección muestra el `FlagGateBanner` y el endpoint responde `404`.
**Impacto por runtime:** ninguno (UI pura). **Fallback:** no aplica.
**Trabajo del operador: ninguno** (un click opcional, default ON).

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación (verificable) |
|---|--------|-----------|--------------------------|
| R1 | **Un secreto viaja en el `.zip`** | Crítica | Cuatro capas: (a) `HandoffVariable` **no modela** un campo `value` — no se puede filtrar lo que no existe; (b) `scrub_files` con el masking canónico del 195; (c) `assert_no_secrets` que **lanza** (falla cerrado); (d) `test_secreto_sembrado_aborta_el_bundle` con literal partido. Además el `POST /build` responde `409`, no `200` con un zip "limpio" |
| R2 | El gate anti-secreto bloquea paquetes legítimos (falso positivo) | Alta | **Solo se mira la clase `secrets`**, jamás el set completo de `detect_classes`. Congelado por `test_build_number_de_8_digitos_no_bloquea` y `test_palabra_produccion_no_bloquea`, que existen precisamente porque `\b\d{7,8}\b` (`egress_policies.py:67`) y `producci[oó]n` (`:75`) están en el detector |
| R3 | El zip no es reproducible por el `mtime` (el bug silencioso del prior art) | Alta | `ZipInfo(date_time=_ZIP_EPOCH)` en **todas** las entradas; prohibido `zf.write(ruta)` (verificado por `grep` en el criterio binario de F3); `MANIFEST.json` sin `generated_at` |
| R4 | El endpoint de descarga se vuelve una lectura arbitraria del disco | Crítica | `bundle_id` validado contra `^[0-9a-f]{16}$` **antes** de tocar el filesystem + `commonpath` como defensa en profundidad + tope de tamaño. 4 tests de descarga (KPI-6) |
| R5 | El README miente: dice que Stacky no puede algo que sí puede (o al revés) | Alta | El README **no se escribe**: se **deriva** de `resolve_frontier`. `test_ninguna_accion_can_es_paso_manual` hace imposible que una acción resuelta `CAN` aparezca como trabajo del operador |
| R6 | Los planes 246/247/251 nunca se implementan y este queda inerte | Media | KPI-5: `build_bundle` funciona con los 3 ausentes; el fallback de variables usa `pipeline_preflight.referenced_variables`/`check_placeholders`, que **ya existen y están probados** |
| R7 | Los comandos del README están mal para el entorno del cliente | Media | Todos los comandos son PowerShell/Windows, que es el entorno real del corpus (`cd-deploy-test.yml:120-121` usa `pool: name: 'TEST-Server'` self-hosted Windows). Cada paso trae `on_failure`. **Ningún comando del README lo ejecuta Stacky**: los ejecuta un humano que puede frenar |
| R8 | Los bundles llenan el disco | Baja | `prune_bundles(max_age_hours=72, keep_last=20)` tras cada `build`; best-effort, nunca lanza |
| R9 | Sesión paralela viva toca `harness_flags.py` / `DevOpsPage.tsx` | Media | Los cambios son **aditivos** (1 `FlagSpec`, 1 entrada en `_CATEGORY_KEYS`, 1 objeto en el array de secciones). Tras el merge: `python -m compileall backend` + `npx tsc --noEmit` + `grep` de la key duplicada (gotcha del merge silencioso: git no marca conflicto si dos ramas agregan la misma línea de cierre) |
| R10 | El `healthKey` no existe en `/api/diag/health` y el gate queda pegado | Media | F5 lleva una **instrucción ejecutable** (grep + leer + espejar), no una suposición |

---

## 9. Fuera de scope (explícito, nombrando los planes de la serie)

| Fuera de este plan | Dueño |
|---|---|
| Descubrir las pipelines existentes (ADO + GitLab + repo) y su última corrida | **Plan 246** — `pipeline_inventory.py`. Yo **consumo** su registro si está; si no, degrado (KPI-5) |
| Perfilar un YAML: stack, fases, artefactos, propósito | **Plan 247** — `pipeline_profiler.py`. Idem |
| Auditar seguridad y malas prácticas (`SEC001..SECnn`) y recomendaciones de optimización | **Plan 248** — `cicd_security_rules.py`. Este paquete **no audita** el YAML que empaqueta |
| Catálogo y reglas semánticas de GitLab (`GL001..GLnn`) | **Plan 249** |
| Editar/optimizar una pipeline existente por lenguaje natural (patch quirúrgico) | **Plan 250** |
| **Detectar y resolver los valores por entorno** (formulario por entorno, qué falta, caja fuerte del Plan 94) | **Plan 251** — `pipeline_environments.py`. Yo los **CONSUMO** para la sección 4 del README; **nunca los resuelvo yo** |
| Generar el pipeline desde lenguaje natural | **Planes 243 / 244** |
| **Ejecutar cualquier cosa en el servidor o la infraestructura del operador** (WinRM, SSH, `Invoke-Command`, instalar un agente, abrir un puerto) | **Nadie. Es la frontera.** Fuera de scope duro y no negociable (§3), congelado por `test_modulos_sin_ejecucion_remota` |
| Pulido del README por LLM, ledger con UI, firma criptográfica del zip, envío por mail/Slack | Cortados en §3 con su motivo |

---

## 10. Glosario (para modelos menores)

- **Frontera de capacidades:** el catálogo de §5. Dice, **como dato**, qué acciones puede ejecutar
  Stacky por sí mismo y cuáles no, **con el motivo**. Vive en `pipeline_capability_frontier.py`.
- **Veredicto declarado** (`CAN` / `DEPENDS` / `CANNOT`): el del catálogo, antes de mirar el
  entorno. **Veredicto efectivo** (`CAN` / `CANNOT` / `CANNOT_NOW` / `UNKNOWN`): el resultado de
  resolver `DEPENDS` contra las sondas. `UNKNOWN` **siempre** se trata como trabajo del operador.
- **Sonda (`probe`):** una función de solo lectura, sin red, que responde `True`/`False`/`None`
  sobre el estado real (¿hay PAT?, ¿hay token?, ¿hay repo escribible?). `None` = no se pudo saber.
- **Paquete de entrega (bundle):** el `.zip` único con YAML + scripts + `README.md` +
  `MANIFEST.json`. Su identidad es el `bundle_id` = huella `sha256` de su contenido.
- **Determinista / reproducible:** mismas entradas → **mismos bytes**. Requiere `ZipInfo` con
  `date_time` fijo y **cero timestamps dentro del zip** (§2.3).
- **Falla cerrado:** ante la duda, se bloquea. Si el gate detecta un secreto, **no hay paquete**.
- **Degradación honesta:** si falta un módulo de la serie, el paquete **igual se arma** y el README
  **dice qué falta y qué consecuencia tiene** (`DEGRADED_CONSEQUENCE`).
- **HITL (human-in-the-loop):** el operador decide. Acá: el paquete se genera con un click y su
  único efecto es un archivo descargable.
- **`_CURATED_DEFAULTS_ON` / `HARNESS_TEST_FILES` / ratchet UI:** convenciones de la casa — lista de
  flags con default ON curadas (`tests/test_harness_flags.py:467`), registro obligatorio de tests
  nuevos (**dos** listas: `run_harness_tests.sh:20` y `run_harness_tests.ps1:13`), y la prohibición
  de `style={{}}` en `.tsx`.

---

## 11. Orden de implementación

1. **F0** — catálogo de 14 acciones + `resolve_frontier` puro + flag en los 4 lugares + 10 tests.
2. **F1** — 3 sondas + `probe_environment` + `evaluate_frontier` + 5 tests.
3. **F2** — `HandoffStep`/`HandoffVariable`/`BundleInputs` + `collect_inputs` degradado +
   `build_steps` + `build_manifest` + `render_readme` (plantilla de §6) + 13 tests.
4. **F3** — `scrub_files` + `assert_no_secrets` + `zip_bytes` determinista + `build_bundle` +
   `persist_bundle` atómico + `bundle_path` + `prune_bundles` + `append_ledger` + 9 tests.
5. **F4** — blueprint con 3 endpoints + guard de flag per-request + guard `commonpath` + 10 tests.
6. **F5** — modelo puro + panel + `endpoints.ts` + sección en `DevOpsPage.tsx` + 6 tests + `tsc`.

Cada fase se commitea sola, con **sus tests verdes corridos de verdad** (output pegado) **antes**
de la siguiente. TDD estricto, cero falsos verdes.

---

## 12. Definición de Hecho (DoD) — binaria

- [ ] Los **5** archivos de test nuevos pasan **por archivo** con `backend\.venv\Scripts\python.exe`
      (no `venv`): `test_plan252_capability_frontier.py` (15), `test_plan252_handoff_bundle.py` (13),
      `test_plan252_zip_determinismo.py` (9), `test_plan252_handoff_api.py` (10),
      `pipelineHandoffModel.test.ts` (6). **Total: 53 casos.**
- [ ] Los **4** archivos de test backend están registrados en **las dos** listas del ratchet
      (`run_harness_tests.sh:20` y `run_harness_tests.ps1:13`) y `test_harness_ratchet_meta.py` queda verde.
- [ ] `test_harness_flags.py` verde con la key nueva en `_CURATED_DEFAULTS_ON` (**:467**) y en
      `_CATEGORY_KEYS["devops"]` (`harness_flags.py:217`).
- [ ] **KPI-1:** `test_zip_es_byte_identico_en_dos_corridas` + `test_build_es_idempotente` verdes; y
      `grep -c "zf.write(" services/pipeline_handoff_bundle.py` → **0**.
- [ ] **KPI-2:** `test_secreto_sembrado_aborta_el_bundle` + `test_build_con_secreto_devuelve_409`
      verdes, **y** el directorio de bundles queda vacío tras el intento.
- [ ] **KPI-3:** `test_toda_accion_tiene_veredicto_y_motivo` + `test_ninguna_accion_can_es_paso_manual`
      verdes; `len(ACTION_CATALOG) == 14`.
- [ ] **KPI-4:** `test_paso_sin_validacion_es_rechazado` verde — **imposible** construir un
      `HandoffStep` sin `command`, `expected_result` y `on_failure`.
- [ ] **KPI-5:** `test_bundle_sin_246_247_251_igual_se_arma` verde con los 3 módulos ausentes.
- [ ] **KPI-6:** los 4 tests de descarga verdes; `grep -n "commonpath" api/pipeline_handoff.py` → ≥1.
- [ ] `python -m compileall backend` limpio · `npx tsc --noEmit` sin errores nuevos ·
      `grep -c "style={{" .../PipelineHandoffPanel.tsx` → **0**.
- [ ] `test_modulos_sin_ejecucion_remota` **passed** (no `skipped`): ni
      `pipeline_capability_frontier.py` ni `pipeline_handoff_bundle.py` mencionan `subprocess`,
      `paramiko`, `winrm`, `socket` ni `requests`.
- [ ] Flag `STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED` **visible y toggleable desde la UI**
      (Configuración → Arnés → categoría DevOps), default ON.
- [ ] Con la flag **OFF**: los 3 endpoints devuelven `404`, la sección muestra el `FlagGateBanner`, y
      **todo lo demás del panel DevOps queda exactamente como hoy**.
- [ ] **Smoke manual (obligatorio, 1 vez):** descargar un paquete real, abrir el `README.md`,
      verificar sus 8 secciones, y confirmar a ojo que **ninguna** contiene un valor secreto.
