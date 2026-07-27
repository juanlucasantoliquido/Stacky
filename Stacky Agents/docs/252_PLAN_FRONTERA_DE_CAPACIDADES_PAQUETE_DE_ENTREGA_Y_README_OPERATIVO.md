# Plan 252 — La frontera de capacidades: qué hace Stacky, qué te toca a vos, y el paquete de entrega que lo cierra

> ## ESTADO REAL AL 2026-07-26: **IMPLEMENTADO — F0..F5 COMPLETAS**
>
> Implementado y commiteado en `feat/plan-217-migrador-mantis-gitlab`. **Backend 64 tests
> verdes corridos por archivo con `backend/.venv` (py3.13.5); frontend 8 verdes +
> `npx tsc --noEmit` en 0 errores.**
>
> | Fase | Estado | Archivo de test | Resultado real |
> |---|---|---|---|
> | F0 catálogo + resolución pura + flag | IMPLEMENTADA | `test_plan252_capability_frontier.py` | **18 passed** (F0+F1) |
> | F1 sondas del estado real | IMPLEMENTADA | (mismo archivo) | incluidas arriba |
> | F2 manifest + README por plantilla | IMPLEMENTADA | `test_plan252_handoff_bundle.py` | **18 passed** |
> | F3 zip determinista + gate anti-secreto | IMPLEMENTADA | `test_plan252_zip_determinismo.py` | **14 passed** |
> | F4 blueprint preview/build/download | IMPLEMENTADA | `test_plan252_handoff_api.py` | **14 passed** |
> | F5 modelo puro + panel | IMPLEMENTADA | `pipelineHandoffModel.test.ts` | **8 passed**, `tsc` 0 errores |
>
> ### El peligro nº1 de este plan: ¿falla abierto o cerrado? — **CERRADO, y está probado**
>
> - **Orden del gate:** `build_files → assert_no_secrets(CRUDO) → scrub_files → ¿el scrub
>   cambió algo? → abortar → zip`. `test_el_gate_corre_sobre_el_texto_crudo_no_sobre_el_enmascarado`
>   congela justamente eso: demuestra que sobre el texto YA enmascarado el gate **no
>   encuentra nada**, que es exactamente por qué el orden invertido del v1 dejaba salir el
>   paquete para los 7 formatos que el enmascarador sí reconoce.
> - **El scrub es TESTIGO, no filtro:** `test_masking_que_cambia_algo_tambien_aborta` usa
>   `ghp_` + 20 chars — que `mask_token_values` reconoce y `egress_policies` **no** (pide
>   36) — y verifica que el bundle se cae igual, nombrando el archivo culpable.
> - **`probes={}` (nada evaluable) ⇒ ninguna acción `DEPENDS` queda en `CAN`**: todas caen
>   en `UNKNOWN`, y `UNKNOWN` **cuenta como trabajo manual** (`test_probes_vacio_resuelve_unknown_nunca_can`).
>   Lo mismo en la UI: `manualActions` incluye `UNKNOWN`.
> - **Una acción `CANNOT` no la promueve ninguna sonda**, ni con las 3 en `True`.
> - **`bundle_path` valida `^[0-9a-f]{16}$` ANTES de tocar el disco**, y el endpoint suma
>   `commonpath` como defensa en profundidad: traversal ⇒ 404/400, nunca 500.
> - **Un secreto sembrado ⇒ 409 y CERO archivos en disco** (`test_build_con_secreto_devuelve_409`).
>
> ### Los 3 bugs del PROPIO PLAN que aparecieron al construirlo
>
> 1. **El catálogo del §5 promete de más, y su propio §5.1 lo prohíbe.** La regla dice que
>    una fila solo puede ser `CAN`/`DEPENDS` si nombra un ejecutor **real e importable**, y
>    que si no existe **hay que bajarla a `CANNOT`**. Greppeado: en este árbol NO hay ningún
>    símbolo que cree un variable group, un environment con approvals ni un agent pool. Por
>    lo tanto `create_variable_group`, `create_environment_and_approvals` y
>    `create_agent_pool` **bajaron de `DEPENDS` a `CANNOT`** con el `reason` honesto
>    *"Stacky todavía no tiene un ejecutor para esto"*. El conteo de 14 no se movió (los
>    tests cuentan filas, no veredictos), y `test_toda_accion_ejecutable_cita_un_simbolo_que_existe`
>    lo congela: el día que alguien implemente el ejecutor, o se sube la fila o el test se
>    pone rojo.
>    *También:* `commit_yaml_to_repo` figuraba **`CAN`** en la tabla y **`repo_writer`** en
>    su columna de sonda — las dos cosas a la vez es imposible (§F0: `CAN` ⟹ `probes == ()`,
>    congelado por `test_can_y_cannot_no_declaran_sondas`). Se resolvió como `DEPENDS`, que
>    es lo honesto: sin provider con puerto de escritura, Stacky no commitea.
> 2. **`from services import X` no se puede desactivar sólo con `sys.modules`.** El test
>    obligatorio de KPI-5 manda `monkeypatch.setitem(sys.modules, "services.X", None)`. Eso
>    funciona **sólo si nadie importó `services.X` antes**: `from package import item` usa
>    primero el **atributo del paquete** y recién cae a `sys.modules` si no existe. Como
>    `test_bundle_con_251_presente_no_degrada` importa los módulos de verdad, los tests
>    posteriores del mismo archivo pasaban a probar **la rama equivocada** — y uno de ellos
>    fallaba. Corregido con `_forzar_ausencia()`, que parchea las **dos** cosas.
> 3. **`collect_inputs` degradaba SIEMPRE por diseño accidental.** El plan lo escribió
>    asumiendo que 246/247/251 no existen ("HOY NO EXISTE") — hoy **sí** existen, así que la
>    rama sana nunca se había ejercitado. Se implementó `_variables_from_env_matrix` contra
>    la API real del 251 (`extract_requirements`), con
>    `test_bundle_con_251_presente_no_degrada` probando esa rama.
>
> ### Lo que queda pendiente (declarado)
>
> - **Smoke visual del operador** (no automatizable: sin `jsdom`): DevOps → *Paquete de
>   entrega*, ver las dos listas, armar el paquete y bajarlo.
> - **Rojo ajeno conocido:** `test_harness_flags_help.py` sigue con sus **4 fallos
>   preexistentes**. Verificado que **ninguna** de las 4 flags de esta corrida (250 x2, 251,
>   252) figura entre las ofensoras, y que las 4 entradas de `PLAIN_HELP` cumplen las 4
>   restricciones (longitudes, prefijo `"Si "`, jerga).
>
> ---
>
> ### Encabezado original (antes de implementar)
>
> ## ESTADO PREVIO: **NO IMPLEMENTADO**
>
> La corrida que implementó la serie "Mago de las Pipelines" llegó hasta el **249** y **se detuvo
> acá por presupuesto de contexto, a propósito**: el operador pidió explícitamente "prefiero 'el
> 250 quedó a medias por X' que un verde inventado". **No hay una sola línea de código de este
> plan en el árbol.** Verificable: ninguno de los archivos que este plan manda CREAR existe.
>
> Implementados y commiteados en esta misma rama, en orden: **246** (`f2e63e77`), **247**
> (`d006e406`), **248** (`ed9a1942`), **249** (`7fc345d8`). Los cuatro tienen su estado real
> escrito en su propio encabezado, con los números de tests y los bugs de plan que aparecieron.
>
> **Antes de implementar este plan, leé el encabezado del 246, 247, 248 y 249**: los cuatro
> descubrieron contradicciones internas de sus propios documentos (una flag con 5 patas que en
> realidad son 6, un `LLMCallSpec` sin sus campos obligatorios, un `RULES_VERSION` que no se puede
> subir sin romper el gate que el mismo plan exige). Este plan no fue revisado con ese ojo todavía.

---

> Estado: **v2 · CRITICADO** — juez independiente (`criticar-y-mejorar-plan`, 2026-07-26).
> Veredicto sobre el v1: **RECHAZADO** — 3 bloqueantes. Esta v2 los corrige. Ver §0.0.
> Autor del v1: StackyArchitectaUltraEficientCode (Claude Opus 5, 1M context).
> Crítica y reescritura a v2: juez independiente (NO el autor del v1).
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

## 0.0 Changelog v1 → v2 (qué corrigió el juez)

Veredicto del v1: **RECHAZADO**. Tres bloqueantes, los tres verificados contra el código real,
los tres dentro de los propios bloques de código del plan. La v2 los resuelve.

| # | Sev | Hallazgo | Dónde se corrigió |
|---|-----|----------|-------------------|
| **C1** | **BLOQ** | **El gate anti-secreto NO fallaba cerrado: `scrub_files` se comía el secreto antes de que `assert_no_secrets` lo viera.** `secret_masking.TOKEN_VALUE_PREFIXES` (`secret_masking.py:11`) incluye `glpat-` y `_TOKEN_RE` (`:15-17`) lo reemplaza por `MASK_PLACEHOLDER`; después `detect_classes` no encuentra nada y el bundle **se produce**. Los dos tests de KPI-2 fallaban por construcción, y §4.5 ("no enmascara y sigue") quedaba contradicha por el propio código: enmascaraba y seguía para **todo formato conocido**, y solo fallaba cerrado para los **desconocidos** — exactamente al revés | §4.5, F3 `build_bundle`, KPI-2 |
| **C2** | **BLOQ** | **Dos gates del plan eran imposibles de pasar el día 1, por la misma causa: la prosa choca con su propio grep.** (a) `test_modulos_sin_ejecucion_remota` asertaba que el **texto fuente** no contiene `subprocess`/`paramiko`/`winrm`/`socket`/`requests`, y el plan mandaba escribir esas 5 palabras en el docstring de **ambos** módulos. (b) El criterio binario de F3 exige `grep -c "zf.write(" … → 0`, y el docstring de `zip_bytes` que el plan mandaba escribir contenía esa llamada **literal** para prohibirla. Gotcha recurrente de la casa | (a) F0 y F2 docstrings + test migrado a **AST**; (b) docstring de `zip_bytes` reescrito en prosa (F3) |
| **C3** | **BLOQ** | **F5 mandaba editar `backend/api/diag.py`, fuera de la superficie reservada al 252**, y ese mismo dict lo reclaman el 246 (`pipeline_inventory_enabled`) y el 251 (`env_matrix_enabled`) → merge silencioso entre hermanos. Además contradecía §4.7 | F5 (se elimina `healthKey`), §4.7, R10 |
| C4 | IMP | `bundle_id` era la huella del contenido **pre-scrub**, no del que va al zip; el README afirmaba lo contrario | §2.3, F3 (resuelto por C1) |
| C5 | IMP | El orden de `degraded` que produce `collect_inputs` contradecía el orden que exigía su propio test | F2 |
| C6 | IMP | `test_bundle_sin_246_247_251_igual_se_arma` pasaba trivialmente hoy (los módulos ya no existen) y **se volvía mudo** el día que aterrice el 246 | F2 |
| C7 | IMP | `except ImportError` era muy angosto: un módulo hermano que rompa al importarse tumbaba el bundle en vez de degradarlo | F2 |
| C8 | IMP | Falso positivo NO contemplado: la clase `secrets` incluye `password\s*[=:]` (`egress_policies.py:89-90`); un `format_hint` con forma de connection string dejaba el bundle **inconstruible** con un 409 confuso | F2 (`__post_init__`), F3, R2 |
| C9 | MEN | 3 anclajes desviados de 66 verificados (ver §2.5) | §2.1, R2 |
| C10 | MEN | `test_zip_es_byte_identico_en_dos_corridas` no podía fallar (el `os.utime` era decorativo: `zip_bytes` no toca el disco) | F3 |
| C11 | MEN | `test_readme_no_tiene_placeholders_sin_sustituir` era frágil ante cualquier `{` legítimo | F2 |
| **C12** | **IMP** | **Faltaba el 5º lugar del cableado de la flag: `services/harness_flags_help.py`.** `test_harness_flags_help.py:32-35` exige `REGISTRY_KEYS - set(PLAIN_HELP) == []`. El v1 mencionaba el rojo preexistente de ese archivo pero nunca mandaba agregar la entrada, así que iba a sumar su propio fallo y confundirlo con deuda ajena. Se agrega la entrada **literal** ya validada contra la `JARGON_DENYLIST` congelada | F0 GOTCHA DURA 4, §4.7, §12 |

**[ADICIÓN ARQUITECTO] — `evidence`: la frontera deja de ser una lista de afirmaciones tipeadas
a mano.** Ver §5.1 y los 2 tests nuevos de F0. Es la corrección de fondo del plan: el v1 denunciaba
que la frontera escrita a mano en `bootstrap-server-environment.yml:28-32` "no es verificable" — y
después proponía una tabla de 14 filas escrita a mano, igual de no verificable, solo que mudada de
un comentario YAML a un `tuple` de Python.

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
| **KPI-2** | Cero secretos | Con un token sembrado en cualquier archivo de entrada, `build_bundle` **lanza `HandoffSecretError` y NO produce zip** (falla cerrado, no enmascara y sigue). **El gate corre sobre el texto CRUDO, ANTES del masking (C1)**; el masking queda como red de seguridad que, si llega a cambiar algo, **también aborta**. `test_secreto_sembrado_aborta_el_bundle` + `test_masking_que_cambia_algo_tambien_aborta` |
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
| **Bundle a disco + manifest + README** | `backend/services/dbcompare_scripts.py:1234` (`bundle_zip_bytes`), `:1180-1195` (arma `MANIFEST.json` con `json.dumps(..., sort_keys=True)` y `files["README.md"] = _render_readme(manifest, warnings)`), `_render_readme` (**`:950`** — el v1 decía `:1155`, FALSO, corregido C9), `_write_bundle_atomic` (**`:975`** — el v1 decía `:1207`, FALSO, corregido C9; escribe a `<run_id>.tmp` en `:982` y en `:992` usa el alias `_os_replace`, importado como `from os import replace as _os_replace` en `:14` — **no** el literal `os.replace`) | El patrón `dict[str, str]` → archivos → zip, con **README por plantilla determinista** y escritura atómica. Lo copio tal cual |
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

> **Corrección C4 (juez).** El v1 calculaba el `bundle_id` en `build_files` y **después** pasaba
> todo por `scrub_files`. Resultado: el id era la huella del contenido **pre-scrub**, mientras que
> el zip llevaba el contenido **post-scrub** — y el README afirmaba, literalmente, que el id es
> *"la huella SHA-256 del contenido de este paquete"*. Con el orden nuevo de F3 (gate sobre el
> texto crudo, y el masking obligado a ser un **no-op**), el contenido hasheado y el contenido
> empaquetado son el mismo por construcción, y la frase del README vuelve a ser cierta.
> Congelado por `test_bundle_id_es_hash_del_contenido_del_zip`.

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

### 2.5 Verificación independiente de anclajes (juez, 2026-07-26)

Se abrieron y verificaron **66 anclajes** citados por el v1. **63 correctos, 3 desviados.** Los
desviados están corregidos arriba; se listan acá para que nadie los reintroduzca:

| Anclaje del v1 | Realidad | Dónde estaba |
|---|---|---|
| `dbcompare_scripts._render_readme:1155` | **`:950`** | §2.1 |
| `dbcompare_scripts._write_bundle_atomic:1207` | **`:975`** (y usa el alias `_os_replace` de `:14`, no `os.replace`) | §2.1 |
| `egress_policies` `\b\d{7,8}\b` en `:67` | **`:66`** (la clase `"pii"` abre en `:65`) | R2 |

**Confirmado, no desmentido** (los dos puntos que el juez recibió como "posiblemente stale"):

1. **`zf.write()` toma el `mtime` del disco ⇒ el zip no es reproducible.** Verificado en el prior
   art: `dbcompare_scripts.py:1234-1241` es literalmente
   `zf.write(path, arcname=str(path.relative_to(base)).replace("\\", "/"))` dentro de un
   `for path in sorted(base.rglob("*"))` — ordena las entradas pero **no fija la fecha**. El
   diagnóstico de §2.3 y la solución `ZipInfo(date_time=_ZIP_EPOCH)` son correctos.
2. **`detect_classes` dispara con `"produccion"` y con 8 dígitos** —
   `egress_policies.py:75` (`\b(producci[oó]n|PROD|data\s+real|prod-db)\b`, IGNORECASE) y `:66`
   (`\b\d{7,8}\b`). **Matiz importante:** esos patrones **no pertenecen a la clase `secrets`** sino
   a `"production"` y `"pii"`. `detect_classes` **detecta**, no bloquea: quien bloquea es el
   llamador. Por eso la mitigación del plan (mirar **solo** la clase `secrets`) es correcta. Las 5
   clases son `pii`, `financial`, `production`, `regulatory`, `secrets` (`_DETECTORS:64-93`).
   Lo que el v1 **no** vio es que la clase `secrets` **sí** trae dos patrones que un README de
   deploy puede disparar legítimamente (`:89` `password\s*[=:]\s*\S{4,}` y `:90` `;password=…`):
   ver C8.

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
5. **Falla cerrado en secretos — y el ORDEN es la mitad de la regla (C1).** Si el gate detecta un
   secreto, **el bundle no se produce**. No se enmascara-y-sigue: enmascarar y seguir enseñaría al
   operador que el paquete "limpia solo", y la primera vez que el masking no cubra un formato
   nuevo, el secreto viaja.
   **El v1 escribía esta regla y después hacía lo contrario**: su `build_bundle` corría
   `scrub_files` **antes** de `assert_no_secrets`, así que el masking canónico (que conoce
   `ghp_`, `github_pat_`, `glpat-`, `xoxb-`, `xoxp-`, `AKIA`, `eyJhbGciOi` —
   `secret_masking.py:11`) borraba el secreto y el gate no encontraba nada: el paquete **salía**.
   La consecuencia es perversa: fallaba cerrado **solo** para los formatos que el masking
   desconoce, y fallaba abierto justo para los que sabe reconocer.
   **Orden obligatorio, no negociable:**
   `build_files` → `assert_no_secrets(crudo)` → `scrub_files` → **si el scrub cambió un solo byte,
   también aborta** → `zip_bytes`. El masking pasa de ser un filtro a ser un **testigo**: si tuvo
   algo que hacer, es que el gate se le escapó algo, y eso es un fallo, no una limpieza.
6. **Determinismo o no es un artefacto.** Mismas entradas → mismos bytes. Sin esto, no se puede
   comparar dos paquetes, ni cachear, ni auditar qué se le entregó a quién.
7. **No degradar / backward-compatible — y la lista EXACTA de archivos ajenos que se tocan (C3).**
   Todo lo nuevo es aditivo. El v1 afirmaba "cero ediciones a módulos existentes fuera de 3
   lugares" y después editaba 8, incluido uno **fuera de la superficie reservada al 252**. Lista
   cerrada y auditable de **todo** lo que este plan edita de archivos que ya existen:

   | Archivo existente | Qué se le agrega | Superficie |
   |---|---|---|
   | `backend/services/harness_flags.py` | 1 `FlagSpec` + 1 key en `_CATEGORY_KEYS["devops"]` | universal |
   | `backend/config.py` | 1 constante espejo | universal |
   | `backend/tests/test_harness_flags.py` | 1 key en `_CURATED_DEFAULTS_ON` (`:467`) | universal |
   | `backend/services/harness_flags_help.py` | 1 entrada en `PLAIN_HELP` (**C12** — el v1 lo olvidaba) | universal |
   | `backend/scripts/run_harness_tests.sh` (`:20`) | 4 archivos de test | universal |
   | `backend/scripts/run_harness_tests.ps1` (`:13`) | 4 archivos de test | universal |
   | `backend/api/__init__.py` | 1 `import` + 1 `register_blueprint` | blueprint |
   | `frontend/src/api/endpoints.ts` | 1 objeto `PipelineHandoff` | panel |
   | `frontend/src/pages/DevOpsPage.tsx` | 1 objeto en el array de secciones | panel |

   **`backend/api/diag.py` NO se toca** (era la 9ª edición del v1, y está fuera de la frontera
   del 252): ver F5. **Cero archivos fuera de esta tabla.** Con la flag OFF, todo queda
   **exactamente** como hoy.
   *Nota de merge (R9):* `harness_flags.py`, `endpoints.ts` y `DevOpsPage.tsx` los tocan también
   los planes hermanos de la serie. Git **no marca conflicto** cuando dos ramas agregan
   independientemente la misma línea de cierre a un objeto ya existente: tras cada merge, correr
   `python -m compileall backend`, `npx tsc --noEmit` y un `grep -c` de la key nueva (debe dar
   exactamente 1 por archivo).
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

### 5.1 [ADICIÓN ARQUITECTO] — `evidence`: la frontera tiene que poder mentir en rojo

**El problema que el v1 no vio en sí mismo.** §0 abre denunciando que la frontera escrita a mano en
`bootstrap-server-environment.yml:28-32` *"no es verificable, no es consultable, no se actualiza
cuando cambia el entorno"*. Y a continuación propone… una tabla de 14 filas escrita a mano. Mudarla
de un comentario YAML a un `tuple` de Python la hace **consultable**, sí — pero **no** verificable
y **no** auto-actualizable. Un catálogo que afirma `CAN` sobre algo que Stacky no sabe hacer es
peor que no tener catálogo: el README le promete al operador que ya está resuelto, el operador no
lo hace, y el pipeline no anda. **Una frontera que promete de más es un bug de producto disfrazado
de documentación.**

**La corrección: cada acción que se declara ejecutable debe nombrar el símbolo que la ejecuta, y
ese símbolo tiene que existir.**

`CapabilityAction` suma **un campo obligatorio**:

```python
    evidence: str = ""   # "modulo.simbolo" del ejecutor real; "" SOLO si verdict == CANNOT
```

**Regla binaria (congelada por test, no por buena voluntad):**

- `verdict in (CAN, DEPENDS)` ⟹ `evidence != ""` **y** `importlib.import_module(mod)` +
  `getattr(mod, simbolo)` **resuelven**. Si no resuelve, el test es rojo.
- `verdict == CANNOT` ⟹ `evidence == ""`. Y el test verifica la recíproca: **ninguna** acción
  `CANNOT` tiene un ejecutor importable. El día que alguien implemente ejecución remota, el
  catálogo se pone **rojo** en vez de seguir mintiendo en silencio.
- **Corolario duro, y es el punto entero:** si al implementar no existe ningún símbolo que haga la
  acción, **la fila no puede quedar `CAN` ni `DEPENDS`**. Se baja a `CANNOT` con el `reason`
  honesto *"Stacky todavía no tiene un ejecutor para esto"*. Prohibido inventar un símbolo para
  que el test pase: eso es exactamente el fraude que este campo existe para impedir.

**Semilla verificada por el juez** (estos 5 símbolos se abrieron y existen; el resto los resuelve el
implementador con `grep -rn "def <lo-que-busque>" backend/services/` **antes** de elegir el
veredicto):

| `id` | `evidence` | Verificado en |
|---|---|---|
| `generate_yaml` | `services.pipeline_renderers.to_ado_yaml` | `pipeline_renderers.py:79` (y `:277` para GitLab) |
| `generate_helper_scripts` | `services.pipeline_handoff_bundle.build_files` | módulo propio de este plan (F2) |
| `commit_yaml_to_repo` | `services.repo_writer.get_repo_writer` | `repo_writer.py:30` |
| `register_pipeline_definition` | `services.ado_pipeline_definitions.ensure_yaml_definition` | `ado_pipeline_definitions.py:125` |
| `set_pipeline_variables` | `services.ci_variables.get_variables_provider` | `ci_variables.py:66` |

**Los 7 restantes (`open_pull_request`, `create_variable_group`,
`create_environment_and_approvals`, `create_agent_pool`, `run_pipeline_first_time`, y las 2 filas
`CANNOT` de infraestructura) NO fueron verificados por el juez.** El implementador **debe**
grepear el ejecutor de cada uno y, si no aparece, **bajar la fila a `CANNOT`** y ajustar el
`reason`. Es un cambio de dato en el catálogo, no un cambio de diseño: el conteo de 14 no se toca,
solo puede moverse la columna *Veredicto declarado*. Los tests que dependen del reparto
(`test_frontier_devuelve_14_acciones`, `test_frontier_sin_deploys_devuelve_12`) cuentan filas, no
veredictos, así que siguen valiendo.

**Por qué esta adición respeta todos los rieles:** cero LLM (es `importlib`, stdlib), idéntica en
los 3 runtimes, cero trabajo del operador, cero config nueva, no toca ningún archivo fuera de la
frontera del 252, y no saca al humano de ningún lazo — **al contrario: impide que el README le
prometa al humano trabajo ya hecho que no está hecho.**

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
- EDITAR `Stacky Agents/backend/services/harness_flags_help.py` (agregar la entrada a `PLAIN_HELP` — **C12**, obligatorio, ver GOTCHA DURA 4)
- CREAR `Stacky Agents/backend/tests/test_plan252_capability_frontier.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (**:20**, `HARNESS_TEST_FILES=(`)
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.ps1` (**:13**, `$HarnessTestFiles = @(`)

**Símbolos EXACTOS a crear en `pipeline_capability_frontier.py`:**

```python
"""services/pipeline_capability_frontier.py — Plan 252 F0/F1. Frontera de capacidades.

Declara, COMO DATO, qué acciones del dominio de pipelines puede ejecutar Stacky por sí
mismo y cuáles no, con el motivo. PURO en F0 (cero I/O, cero red, cero config): las
sondas de estado real viven en F1 y se inyectan.

Este módulo describe la frontera; jamás la cruza: no importa ningún módulo de ejecución
remota ni de red. La lista negra vive en UN solo lugar — _MODULOS_PROHIBIDOS en
tests/test_plan252_capability_frontier.py — y se verifica por AST, no por texto (C2).
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
    evidence: str = ""             # §5.1 — "modulo.simbolo" del ejecutor REAL.
                                   # OBLIGATORIO si verdict in (CAN, DEPENDS); "" si CANNOT.


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
> **GOTCHA DURA 4 (C12) — el v1 olvidó el 5º lugar: `services/harness_flags_help.py`.**
> `tests/test_harness_flags_help.py:32-35` exige `REGISTRY_KEYS - set(PLAIN_HELP) == []`. Una
> `FlagSpec` nueva **sin** entrada en `PLAIN_HELP` deja ese test rojo con tu key en la lista de
> faltantes. El v1 mencionaba el rojo preexistente de ese archivo pero **nunca mandaba agregar la
> entrada**, así que iba a sumar un 5º fallo y atribuirlo a deuda ajena.
>
> **Entrada literal a agregar** (ya validada contra las 4 restricciones del test — copiala tal
> cual, no la reescribas "mejorándola"):
>
> ```python
> "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED": PlainHelp(
>     what="Arma un paquete descargable con los archivos del pipeline y una guia de pasos para dejarlo funcionando en el servidor.",
>     on_effect="Si esta activada, aparece el boton Descargar paquete de entrega en la seccion Pipelines: junta los archivos generados, agrega una guia con los pasos manuales y su verificacion, y baja todo en un solo archivo comprimido.",
>     off_effect="Si esta apagada, el boton no aparece y el resto del panel queda igual que antes; podes seguir copiando los archivos a mano.",
>     example="Generaste el pipeline y ahora hay que registrarlo y preparar el servidor. Con esto activado bajas un solo archivo con todo adentro y una guia que dice, paso a paso, que hacer, con que comando y como darte cuenta de que salio bien.",
> ),
> ```
>
> **Las 4 restricciones que ese texto respeta** (`test_harness_flags_help.py:17-23,44-73`):
> `what` entre 10 y 200 chars · `on_effect`/`off_effect` **empiezan literalmente con `"Si "`** y
> ≤240 · `example` ≤300 · **prohibida** la `JARGON_DENYLIST` congelada
> (`MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend,
> frontend, gate, hook, runtime` — case-insensitive, palabra completa **y su plural**) · prohibido
> citar keys `SCREAMING_SNAKE` y referencias de fase tipo `F1`. Por eso el texto dice *"archivo
> comprimido"* y no *"zip con el endpoint"*, y *"clave"* y nunca *"token"*.
>
> **VERIFICADO POR EL JUEZ — `_REQUIRES_MAP_FROZEN` NO es uno de los lugares, para esta flag.**
> El test construye `actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}`
> (`tests/test_harness_flags_requires.py:287`): una `FlagSpec` **sin** `requires` no entra en el
> mapa. Como esta flag es deliberadamente SIN `requires`, agregarla ahí **pondría en rojo**
> `test_requires_map_is_frozen` (aparecería como "Faltantes"). No la agregues.
>
> **Los 5 lugares, entonces:** `FlagSpec` · `_CATEGORY_KEYS["devops"]` · `config.py` ·
> `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`) · `PLAIN_HELP`
> (`services/harness_flags_help.py`).

**Tests PRIMERO — `tests/test_plan252_capability_frontier.py` (12 casos):**

> **Por qué el test de la lista negra es por AST y no por `in` sobre el texto (C2).** El v1
> asertaba que *"el texto fuente no contiene `subprocess`, `paramiko`, `winrm`, `socket` ni
> `requests`"* — y al mismo tiempo mandaba escribir, en el docstring de los **dos** módulos, la
> línea *"PROHIBIDO … subprocess, paramiko, winrm, requests, socket"*. El test se detectaba a sí
> mismo: **rojo el día 1, sin una sola línea de código malo**. Es el gotcha recurrente de esta casa
> (la prosa del plan choca con su propio grep-gate) y ya mordió antes con el centinela textual de
> flags, que hubo que migrar a AST por lo mismo. Regla general: **una lista negra de imports se
> verifica sobre el árbol sintáctico, jamás sobre la cadena de caracteres.**

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
| `test_modulos_sin_ejecucion_remota` (**§3, fuera de scope duro**) | **por AST, NO por texto (C2).** `ast.parse(fuente)` de `pipeline_capability_frontier.py` **y** de `pipeline_handoff_bundle.py`; se recorren los nodos `ast.Import` / `ast.ImportFrom` y se toma la **raíz** de cada módulo importado (`nombre.split(".")[0]`); ninguna puede estar en `_MODULOS_PROHIBIDOS = {"subprocess", "paramiko", "winrm", "pywinrm", "socket", "requests", "httpx", "urllib", "urllib3", "telnetlib", "ftplib", "asyncssh"}`. Además: **cero nodos `ast.Call` a `__import__` o `importlib.import_module`** en ambos módulos (los imports dinámicos quedan prohibidos justamente para que este test sea decidible — ver F2) |
| `test_toda_accion_ejecutable_cita_un_simbolo_que_existe` (**§5.1, [ADICIÓN ARQUITECTO]**) | para toda acción con `verdict in (CAN, DEPENDS)`: `a.evidence != ""`, tiene exactamente un `.` separando módulo y símbolo, y `getattr(importlib.import_module(mod), sym)` **no lanza**. Mensaje de fallo: el `id` de la acción y el `evidence` que no resolvió |
| `test_cannot_no_tiene_ejecutor` (**§5.1**) | para toda acción con `verdict == CANNOT`: `a.evidence == ""`. Recíproca: el día que aparezca un ejecutor, la fila deja de ser `CANNOT` **o el test se pone rojo** |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan252_capability_frontier.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q   # C12
```

> **Cómo leer `test_harness_flags_help.py` (C12).** Ese archivo arrastra **4 fallos ajenos
> preexistentes**. Procedimiento obligatorio, para no confundir tu fallo con la deuda de otro:
> correlo **ANTES** de tocar nada y guardar la salida; correrlo **DESPUÉS**; y verificar que tu key
> **no** aparezca en la lista de "Flags sin ayuda llana" de
> `test_plain_help_covers_all_registry_keys`. Prohibido "arreglar" los 4 ajenos.

**Criterio de aceptación BINARIO:** los 12 tests pasan **y** `test_harness_flags.py` y
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

**Criterio BINARIO:** los 17 tests del archivo (12 de F0 + 5 de F1) pasan.

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

Este módulo no cruza la frontera: no importa nada de ejecución remota ni de red, y no
usa imports dinamicos. La lista negra y su verificacion por AST viven en
tests/test_plan252_capability_frontier.py::test_modulos_sin_ejecucion_remota (C2).
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

    def __post_init__(self):
        _assert_campo_limpio(self, "format_hint")   # C8


def _assert_campo_limpio(obj, campo: str) -> None:
    """C8 — falso positivo del gate, atajado EN EL ORIGEN.

    La clase `secrets` de egress_policies incluye dos patrones que un texto
    INSTRUCTIVO legitimo dispara sin tener un secreto adentro:
        egress_policies.py:89  (?i)\\b(password|passwd|pwd|contrase[nñ]a)\\s*[=:]\\s*\\S{4,}
        egress_policies.py:90  (?i);\\s*password\\s*=\\s*[^;\\s]{4,}
    Un `format_hint` con forma de connection string
    ("Server=...;Database=...;Password=<tu-clave>") los dispara. El v1 solo habia
    previsto los falsos positivos de las clases `pii` y `production`, que no bloquean.

    Consecuencia si no se ataja aca: `assert_no_secrets` (F3) aborta el bundle entero con
    un 409 que le dice al operador "hay material sensible en README.md" — cuando el
    problema es UN campo de UNA variable, y el operador no tiene forma de saber cual.

    Regla: el campo se valida en su constructor y el error NOMBRA el campo y la variable.
    Fallar temprano y preciso, no tarde y generico. Sigue siendo falla cerrado.
    """
    from services.egress_policies import detect_classes
    texto = str(getattr(obj, campo) or "")
    if "secrets" in detect_classes(texto):
        raise HandoffSecretError(
            f"{type(obj).__name__}.{campo} parece contener un valor sensible "
            f"(o una plantilla con forma de credencial): {getattr(obj, 'name', '?')!r}. "
            f"Describi el FORMATO sin escribir un valor de ejemplo con forma de clave "
            f"(ej.: 'connection string de SQL Server, sin la clave' en vez de "
            f"'Server=..;Password=..')."
        )


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
    """Degradacion honesta. Tres correcciones del juez respecto del v1:
      C5 — `degraded` se devuelve SIEMPRE ordenado alfabeticamente. El v1 lo armaba en
           orden de aparicion (environments primero) pero su test exigia otro orden:
           se contradecian entre si.
      C6 — el test que prueba esto NO puede depender de que los modulos no existan hoy:
           debe forzar la ausencia (ver la tabla de tests).
      C7 — `except Exception`, no `except ImportError`. Un modulo hermano que exista pero
           reviente al importarse (SyntaxError, dependencia rota, side effect) tiene que
           DEGRADAR el paquete, no tumbarlo. Degradar es el trabajo de esta funcion.
    Sin imports dinamicos (`__import__` / `importlib`): tres bloques explicitos, para que
    test_modulos_sin_ejecucion_remota pueda decidir por AST (C2).
    """
    degraded: list[str] = []

    # 251 — matriz de entornos. Si no esta, se degrada al preflight que YA existe.
    try:
        from services import pipeline_environments          # plan 251 — HOY NO EXISTE (§2.4)
        variables = _variables_from_env_matrix(pipeline_environments, spec_dict)
    except Exception:                                       # noqa: BLE001 — C7
        degraded.append("pipeline_environments")
        variables = _variables_from_preflight(spec_dict)    # fallback determinista

    try:
        from services import pipeline_inventory             # plan 246 — HOY NO EXISTE
        _ = pipeline_inventory
    except Exception:                                       # noqa: BLE001
        degraded.append("pipeline_inventory")

    try:
        from services import pipeline_profiler              # plan 247 — HOY NO EXISTE
        _ = pipeline_profiler
    except Exception:                                       # noqa: BLE001
        degraded.append("pipeline_profiler")

    degraded_t = tuple(sorted(set(degraded)))               # C5 — orden canonico y estable
    ...
```

> **Nota de determinismo (C5):** `degraded` entra al `MANIFEST.json` y al README. Si su orden
> dependiera del orden de los `try`, dos corridas equivalentes podrían diferir tras cualquier
> refactor de este bloque, y el `bundle_id` con ellas. `sorted(set(...))` lo vuelve una propiedad
> del **conjunto de módulos ausentes**, no del orden en que se los preguntó.

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

**Tests PRIMERO — `tests/test_plan252_handoff_bundle.py` (17 casos):**

| Test | Qué congela |
|---|---|
| `test_paso_sin_validacion_es_rechazado` (**KPI-4**) | `HandoffStep(..., expected_result="")` lanza `HandoffError`; idem con `command=""` y `on_failure=""` |
| `test_variable_no_modela_valor` | `HandoffVariable` **no tiene** campo `value` (`dataclasses.fields` → nombres exactos) |
| `test_ninguna_accion_can_es_paso_manual` (**KPI-3**) | con `probes` todo `True`, `build_steps` no emite ningún paso cuyo `source` apunte a una acción `CAN` |
| `test_todo_id_manual_tiene_plantilla` | para cada acción del catálogo que pueda quedar manual, `_STEP_TEMPLATES` la cubre; si no, `HandoffError` con el id |
| `test_pasos_numerados_sin_huecos` | `[s.n for s in steps] == list(range(1, len(steps)+1))` |
| `test_bundle_sin_246_247_251_igual_se_arma` (**KPI-5**) | **La ausencia se FUERZA, no se asume (C6).** Los 3 módulos no existen hoy, así que el test del v1 pasaba trivialmente **y se volvía mudo el día que aterrice el 246** sin que nadie se entere. Obligatorio: `for m in ("pipeline_environments","pipeline_inventory","pipeline_profiler"): monkeypatch.setitem(sys.modules, f"services.{m}", None)` — poner `None` en `sys.modules` hace que el `import` lance `ImportError`, así que el test prueba **la rama de degradación** hoy y dentro de un año igual. Assert: `build_files` devuelve un dict con `README.md` y `MANIFEST.json`, y `manifest["degraded"] == ["pipeline_environments","pipeline_inventory","pipeline_profiler"]` — **orden alfabético (C5)**, que es el que produce `tuple(sorted(set(...)))`. El v1 exigía `["pipeline_inventory","pipeline_profiler","pipeline_environments"]`, que su propio código no podía producir |
| `test_bundle_con_251_presente_no_degrada` (**C6, la mitad que faltaba**) | con un módulo stub inyectado en `sys.modules["services.pipeline_environments"]`, `manifest["degraded"]` **no** contiene `"pipeline_environments"`. Sin este test, KPI-5 solo prueba una de las dos ramas |
| `test_modulo_que_revienta_al_importar_degrada_no_tumba` (**C7**) | un stub cuyo import lanza `RuntimeError` (no `ImportError`) → el bundle **se arma igual** y el módulo aparece en `degraded`. Con el `except ImportError` del v1, esto tumbaba `build_bundle` entero |
| `test_format_hint_con_connection_string_falla_temprano_y_preciso` (**C8**) | `HandoffVariable(name="DB_CONN", ..., format_hint="Server=x;Database=y;Password=abcd")` lanza `HandoffSecretError` **en el constructor**, y el mensaje contiene `"format_hint"` y `"DB_CONN"`. Congela que el fallo es del CAMPO, no un 409 genérico sobre `README.md` |
| `test_degraded_aparece_en_el_readme` | el README contiene el texto de `DEGRADED_CONSEQUENCE["pipeline_environments"]` |
| `test_readme_tiene_las_8_secciones` | los 8 encabezados `## N.` de §6, en orden |
| `test_readme_no_tiene_placeholders_sin_sustituir` | **C11 — se asserta sobre los placeholders de ESTA plantilla, no sobre cualquier `{`.** El check del v1 (`"{" not in readme.replace("${{", "")`) reventaba ante cualquier llave legítima venida del operador — un `format_hint` de GitLab como `${CI_COMMIT_SHA}`, un bloque `@{...}` de PowerShell, un JSON de ejemplo. Correcto: `re.findall(r"\{[a-z_]+\}", readme) == []`, que solo caza los nombres de sustitución de §6 (`{bundle_id}`, `{pipeline_name}`, `{reason}`, …) |
| `test_manifest_no_tiene_timestamp` (**§2.3**) | `"generated_at" not in manifest` y ninguna clave del manifest matchea `r"(_at|timestamp|date)$"` |
| `test_bundle_id_estable` (**KPI-1, mitad pura**) | `compute_bundle_id(files) == compute_bundle_id(dict(reversed(list(files.items()))))` — el orden de inserción **no** afecta |
| `test_bundle_id_no_es_circular` | `build_files` no lanza `RecursionError` y `manifest["bundle_id"]` tiene 16 chars hex |
| `test_vocabulario_espeja_al_209` | los campos `n`, `action`, `expected_result`, `source` de `HandoffStep` existen con esos nombres exactos, comparados contra `[f.name for f in dataclasses.fields(validation_playbook.ValidationStep)]` (`validation_playbook.py:121`) |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan252_handoff_bundle.py -q`
Y re-correr `tests/test_plan252_capability_frontier.py` (el `skip` de
`test_modulos_sin_ejecucion_remota` ahora **debe dejar de saltear** y pasar).

**Criterio BINARIO:** los 17 tests pasan **y** `test_modulos_sin_ejecucion_remota` deja de estar
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
    """Capa 2 (TESTIGO, ya no filtro): masking canónico del Plan 195 sobre TODO texto.
    Reusa services.secret_masking.mask_token_values (secret_masking.py:20).

    C1 — En el v1 esta funcion corria ANTES del gate y lo desarmaba. Ahora corre DESPUES,
    y su unico proposito es delatar lo que el gate no vio: si cambia un solo byte,
    `build_bundle` aborta. No limpia: acusa."""
    from services.secret_masking import mask_token_values
    return {path: mask_token_values(text) for path, text in files.items()}


def assert_no_secrets(files: dict) -> None:
    """Capa 1 (gate): corre sobre el texto CRUDO. Si detecta un secreto, LANZA
    HandoffSecretError. Falla cerrado (§4.5): no enmascara y sigue.

    Usa egress_policies.detect_classes (egress_policies.py:96) pero SOLO mira la
    clase "secrets" (:81-92). TRAMPA VERIFICADA POR EL JUEZ: detect_classes devuelve
    5 clases (pii/financial/production/regulatory/secrets) y dos de ellas se disparan
    con texto perfectamente legitimo de un README de deploy:
        :66  \\b\\d{7,8}\\b      -> clase "pii"        (un build number 20260726 la dispara)
        :75  producci[oó]n|PROD -> clase "production" (un README de deploy la tiene si o si)
    Bloquear por el set completo dejaria el bundle inconstruible. Por eso: SOLO "secrets".

    CONTRACARA (C8), que el v1 no vio: la clase "secrets" TAMBIEN tiene dos patrones
    que texto instructivo legitimo dispara -- :89 password[=:]valor y :90 ;password=valor.
    Esos NO se relajan aca (son justamente lo que hay que bloquear): se atajan en el
    origen, validando HandoffVariable.format_hint en su constructor (F2), para que el
    error nombre el campo culpable en vez de abortar todo el paquete sin decir cual."""
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
    """Zip REPRODUCIBLE (§2.3). Mismas entradas -> mismos bytes, siempre.

    Regla: una entrada NUNCA se escribe desde una ruta del filesystem (tomaria el mtime
    del disco), ni pasando un str desnudo como nombre (usaria time.localtime()). Siempre
    ZipInfo explicito con _ZIP_EPOCH.

    OJO AL REDACTAR (C2): este docstring NO puede contener la llamada literal que el
    criterio binario de F3 prohibe -- el grep de 0 hits se detectaria a si mismo. En el
    v1 la prohibicion estaba escrita con la sintaxis exacta y ponia el gate en rojo el
    dia 1. Se describe la regla en prosa; el codigo de abajo es la unica fuente."""
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
    """Camino UNICO de generacion. Devuelve (bundle_id, zip_bytes_, manifest).

    ORDEN NO NEGOCIABLE (C1 — el v1 lo tenia INVERTIDO y por eso su KPI-2 era falso):
        build_files -> assert_no_secrets(CRUDO) -> scrub_files -> scrub fue no-op? -> zip

    Por que este orden y no el otro: `mask_token_values` conoce ghp_/github_pat_/glpat-/
    xoxb-/xoxp-/AKIA/eyJhbGciOi (secret_masking.py:11). Si corre primero, BORRA el secreto
    y el gate no encuentra nada -> el paquete SALE. Es decir: el v1 fallaba abierto
    justo para los formatos que sabe reconocer, y cerrado solo para los que no conoce.

    El scrub queda como segunda capa con semantica invertida: si TUVO algo que hacer,
    es que el gate se le escapo un formato, y eso es un fallo -> tambien aborta.
    """
    files = build_files(inputs, resolved_frontier)
    assert_no_secrets(files)                    # ← C1: gate sobre el texto CRUDO
    scrubbed = scrub_files(files)
    if scrubbed != files:                       # ← C1: el masking debe ser un NO-OP
        culpables = sorted(p for p in files if scrubbed[p] != files[p])
        raise HandoffSecretError(
            "El paquete NO se genero: el masking canonico encontro material sensible que "
            "el gate no reconocio, en " + ", ".join(culpables) + ". Es un formato de "
            "credencial nuevo: quitalo del origen y reportalo para sumarlo al detector."
        )
    data = zip_bytes(files)                     # ← se empaqueta el MISMO texto que se hasheo (C4)
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

**Tests PRIMERO — `tests/test_plan252_zip_determinismo.py` (11 casos):**

| Test | Qué congela |
|---|---|
| `test_zip_es_byte_identico_en_dos_corridas` (**KPI-1**) | **C10 — sin el teatro del `os.utime`.** `zip_bytes(files: dict)` **no toca el disco**, así que tocarle el mtime a un archivo homónimo en `tmp_path` no podía hacer fallar el test: era una aserción que no podía fallar. Assert real: `zip_bytes(f) == zip_bytes(f)`, `sha256` iguales, **y** para **todas** las entradas de `infolist()`: `date_time == (1980,1,1,0,0,0)`, `external_attr == 0o644 << 16`, `create_system == 0` y `compress_type == ZIP_DEFLATED`. Esos 4 campos son los únicos que un refactor puede volver dependientes del entorno; el guard contra la regresión a `zf.write(ruta)` es el `grep` del criterio binario |
| `test_masking_que_cambia_algo_tambien_aborta` (**C1, KPI-2**) | con un archivo cuyo texto el gate no reconoce pero `mask_token_values` sí (formato conocido por `secret_masking` y no por `egress_policies`), `build_bundle` lanza `HandoffSecretError` y el mensaje **nombra el archivo culpable**. Congela que el scrub es testigo y no filtro |
| `test_bundle_id_es_hash_del_contenido_del_zip` (**C4**) | `manifest["bundle_id"]` recomputado desde los archivos **efectivamente empaquetados** (leídos del zip, sin `MANIFEST.json` ni `README.md`) coincide con el del manifest. Congela que el README no miente al decir *"el id es la huella del contenido de este paquete"* |
| `test_zip_ignora_el_orden_de_insercion` | `zip_bytes(f) == zip_bytes(dict(reversed(list(f.items()))))` |
| `test_zip_usa_epoch_fijo` | `zipfile.ZipFile(BytesIO(data)).infolist()[0].date_time == (1980, 1, 1, 0, 0, 0)` para **todas** las entradas |
| `test_zip_arcnames_con_barra_posix` | ninguna entrada de `namelist()` contiene `\\` |
| `test_secreto_sembrado_aborta_el_bundle` (**KPI-2**) | con `"glpat-" + "x"*20` (**literal PARTIDO** — gotcha de push-protection de GitHub) dentro de un `.ps1` de entrada, `build_bundle` lanza `HandoffSecretError` y **no** deja archivo en `data_dir()` |
| `test_secreto_en_el_readme_tambien_aborta` | ídem sembrando en un `format_hint` de `HandoffVariable` |
| `test_build_number_de_8_digitos_no_bloquea` (**la trampa de §F3**) | un README con `20260726` **sí** se empaqueta (la clase `pii` no bloquea) |
| `test_palabra_produccion_no_bloquea` | un README que contiene `"producción"` **sí** se empaqueta (la clase `production` no bloquea) |
| `test_bundle_path_rechaza_traversal` | `bundle_path("../../etc/passwd")`, `bundle_path("ABCD")`, `bundle_path("")` → `None`, y `tmp_path` queda sin cambios |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan252_zip_determinismo.py -q`

**Criterio BINARIO:** los 11 tests pasan **y**
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
    // SIN healthKey / gateFlagKey / gateMessage — a proposito (C3). Ver abajo.
    render: (ctx) => <PipelineHandoffPanel ctx={ctx} />,
  },
```

> **C3 — Por qué esta sección NO lleva `healthKey` (cambio del juez).**
> El v1 traía una *"instrucción ejecutable"* para agregar `pipeline_handoff_bundle_enabled` al
> payload de `/api/diag/health`, es decir **editar `backend/api/diag.py`**. Eso está **fuera de la
> superficie reservada al plan 252**, y no es un tecnicismo: ese mismo dict
> (`diag.py:411-423`) lo reclaman al menos dos planes hermanos de la serie — el **246**
> (`healthKey: 'pipeline_inventory_enabled'`) y el **251** (`healthKey: 'env_matrix_enabled'`) —
> más varios de la serie 253-257. Tres ramas agregando una línea al final del mismo `dict` es el
> escenario exacto del merge silencioso: git no marca conflicto y quedan claves duplicadas o
> perdidas.
>
> **`healthKey` es opcional.** `DevOpsPage.tsx:79` lo declara `healthKey?: string` y el gate es
> `const isGated = s.healthKey && ctx.health[s.healthKey] !== true` (`:463`): **sin `healthKey`,
> la sección simplemente no se gatea por health**. Precedente en el mismo archivo: la sección
> `id: 'pipelines'` (`:126-131`), que es justo donde vive esta serie, **tampoco lo tiene**.
>
> **Y la UX con la flag OFF no se pierde** — se resuelve dentro de la frontera del 252:
> `PipelineHandoffPanel.tsx` ya envuelve la llamada a `frontier` en `try/catch` (gotcha del Plan
> 196: `api.get` lanza en non-2xx). Con la flag OFF el endpoint responde `404`, el `catch` lo
> distingue por status y renderiza **inline** el texto de
> `blockedReason({ flagOn: false, yamlCount })`, que ya está en el modelo puro y ya está testeado.
> Resultado: mismo mensaje para el operador, **cero archivos tocados fuera de la frontera**, y el
> riesgo R10 deja de existir.
>
> **Si el dueño de la serie decide igual centralizar los `healthKey` en `diag.py`**, es una tarea
> de la serie (246 o un plan de cierre), no de este plan: una sola rama agrega las N claves de una
> vez. Este plan no la asume.

**Tests PRIMERO — `src/devops/__tests__/pipelineHandoffModel.test.ts` (7 casos, vitest;
**sin** `@testing-library/react` — no está instalado, gap conocido):**

| Test | Qué congela |
|---|---|
| `automaticActions y manualActions son partición` | unión == total, intersección == ∅ |
| `manualActions incluye UNKNOWN` | una acción `UNKNOWN` cae del lado manual, **nunca** del automático |
| `frontierSummary cuenta bien` | 9 `CAN` de 14 → texto con `"9"` y `"14"` |
| `verdictLabel cubre los 4 veredictos` | los 4 textos exactos; ningún `undefined` |
| `blockedReason sin yaml` | `{flagOn: true, yamlCount: 0}` → string no vacío |
| `blockedReason feliz` | `{flagOn: true, yamlCount: 1}` → `null` |
| `blockedReason con la flag OFF` (**C3**) | `{flagOn: false, yamlCount: 3}` → string no vacío que menciona la flag. Es el texto que el panel renderiza **inline** cuando el endpoint contesta `404`, ahora que la sección no usa `FlagGateBanner` |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineHandoffModel.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** los 7 tests pasan **y** `npx tsc --noEmit` sin errores nuevos **y**
`grep -c "style={{" "Stacky Agents/frontend/src/components/devops/PipelineHandoffPanel.tsx"` → **0**.

**Smoke manual (1 paso, no automatizable — gap RTL/jsdom conocido):** panel DevOps → Construir →
Paquete de entrega → el botón baja un `.zip`; abrirlo y confirmar que el `README.md` tiene sus 8
secciones y que **ninguna** contiene un valor secreto.

**Flag:** la de F0. OFF → el endpoint responde `404` y el panel renderiza **inline** el texto de
`blockedReason({flagOn:false, …})` (C3: sin `FlagGateBanner`, para no tocar `api/diag.py`).
**Impacto por runtime:** ninguno (UI pura). **Fallback:** no aplica.
**Trabajo del operador: ninguno** (un click opcional, default ON).

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación (verificable) |
|---|--------|-----------|--------------------------|
| R1 | **Un secreto viaja en el `.zip`** | Crítica | Cuatro capas: (a) `HandoffVariable` **no modela** un campo `value` — no se puede filtrar lo que no existe; (b) `scrub_files` con el masking canónico del 195; (c) `assert_no_secrets` que **lanza** (falla cerrado); (d) `test_secreto_sembrado_aborta_el_bundle` con literal partido. Además el `POST /build` responde `409`, no `200` con un zip "limpio" |
| R2 | El gate anti-secreto bloquea paquetes legítimos (falso positivo) | Alta | **Solo se mira la clase `secrets`**, jamás el set completo de `detect_classes`. Congelado por `test_build_number_de_8_digitos_no_bloquea` y `test_palabra_produccion_no_bloquea`, que existen precisamente porque `\b\d{7,8}\b` (`egress_policies.py:`**`66`** — el v1 decía `:67`, C9) cae en la clase `pii` y `producci[oó]n` (`:75`) en la clase `production`. **C8:** el falso positivo que el v1 NO previó vive dentro de la clase `secrets` (`:89` `password[=:]valor`, `:90` `;password=valor`): un `format_hint` con forma de connection string. Se ataja en el constructor de `HandoffVariable` (F2), con error que nombra el campo |
| R3 | El zip no es reproducible por el `mtime` (el bug silencioso del prior art) | Alta | `ZipInfo(date_time=_ZIP_EPOCH)` en **todas** las entradas; prohibido `zf.write(ruta)` (verificado por `grep` en el criterio binario de F3); `MANIFEST.json` sin `generated_at` |
| R4 | El endpoint de descarga se vuelve una lectura arbitraria del disco | Crítica | `bundle_id` validado contra `^[0-9a-f]{16}$` **antes** de tocar el filesystem + `commonpath` como defensa en profundidad + tope de tamaño. 4 tests de descarga (KPI-6) |
| R5 | El README miente: dice que Stacky no puede algo que sí puede (o al revés) | Alta | El README **no se escribe**: se **deriva** de `resolve_frontier`. `test_ninguna_accion_can_es_paso_manual` hace imposible que una acción resuelta `CAN` aparezca como trabajo del operador |
| R6 | Los planes 246/247/251 nunca se implementan y este queda inerte | Media | KPI-5: `build_bundle` funciona con los 3 ausentes; el fallback de variables usa `pipeline_preflight.referenced_variables`/`check_placeholders`, que **ya existen y están probados** |
| R7 | Los comandos del README están mal para el entorno del cliente | Media | Todos los comandos son PowerShell/Windows, que es el entorno real del corpus (`cd-deploy-test.yml:120-121` usa `pool: name: 'TEST-Server'` self-hosted Windows). Cada paso trae `on_failure`. **Ningún comando del README lo ejecuta Stacky**: los ejecuta un humano que puede frenar |
| R8 | Los bundles llenan el disco | Baja | `prune_bundles(max_age_hours=72, keep_last=20)` tras cada `build`; best-effort, nunca lanza |
| R9 | Sesión paralela viva toca `harness_flags.py` / `DevOpsPage.tsx` | Media | Los cambios son **aditivos** (1 `FlagSpec`, 1 entrada en `_CATEGORY_KEYS`, 1 objeto en el array de secciones). Tras el merge: `python -m compileall backend` + `npx tsc --noEmit` + `grep` de la key duplicada (gotcha del merge silencioso: git no marca conflicto si dos ramas agregan la misma línea de cierre) |
| R10 | ~~El `healthKey` no existe en `/api/diag/health` y el gate queda pegado~~ | — | **ELIMINADO (C3).** La sección ya no usa `healthKey`, así que no hay nada que sincronizar con `api/diag.py` ni riesgo de gate pegado. Ver F5 |
| R11 | **El catálogo promete de más: una fila dice `CAN` sobre algo que Stacky no sabe hacer** | **Alta** | Riesgo NUEVO, identificado por el juez. Es el fallo de producto más grave posible en este plan: el README le dice al operador *"esto ya está hecho"*, el operador no lo hace, y el pipeline no anda — y el artefacto que existía para eliminar la ambigüedad la multiplica. Mitigación: el campo obligatorio `evidence` de §5.1 + `test_toda_accion_ejecutable_cita_un_simbolo_que_existe` + `test_cannot_no_tiene_ejecutor`. Una fila sin ejecutor importable **no puede** quedar `CAN`/`DEPENDS` |

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

1. **F0** — catálogo de 14 acciones (con `evidence`, §5.1) + `resolve_frontier` puro + flag en los
   4 lugares + 12 tests.
2. **F1** — 3 sondas + `probe_environment` + `evaluate_frontier` + 5 tests.
3. **F2** — `HandoffStep`/`HandoffVariable`/`BundleInputs` + `collect_inputs` degradado +
   `build_steps` + `build_manifest` + `render_readme` (plantilla de §6) + 17 tests.
4. **F3** — `assert_no_secrets` (gate, **primero**) + `scrub_files` (testigo, **después**) +
   `zip_bytes` determinista + `build_bundle` + `persist_bundle` atómico + `bundle_path` +
   `prune_bundles` + `append_ledger` + 11 tests.
5. **F4** — blueprint con 3 endpoints + guard de flag per-request + guard `commonpath` + 10 tests.
6. **F5** — modelo puro + panel + `endpoints.ts` + sección **sin `healthKey`** en `DevOpsPage.tsx`
   + 7 tests + `tsc`.

Cada fase se commitea sola, con **sus tests verdes corridos de verdad** (output pegado) **antes**
de la siguiente. TDD estricto, cero falsos verdes.

---

## 12. Definición de Hecho (DoD) — binaria

- [ ] Los **5** archivos de test nuevos pasan **por archivo** con `backend\.venv\Scripts\python.exe`
      (no `venv`): `test_plan252_capability_frontier.py` (**17**), `test_plan252_handoff_bundle.py` (**17**),
      `test_plan252_zip_determinismo.py` (**11**), `test_plan252_handoff_api.py` (10),
      `pipelineHandoffModel.test.ts` (**7**). **Total: 62 casos** (v1: 53; +9 de la crítica).
- [ ] **C1 (bloqueante del v1):** en `services/pipeline_handoff_bundle.py`, `assert_no_secrets`
      aparece **antes** que `scrub_files` dentro de `build_bundle`, y existe la comparación
      `scrubbed != files` que aborta. `test_masking_que_cambia_algo_tambien_aborta` verde.
- [ ] **C2 (bloqueante del v1):** `test_modulos_sin_ejecucion_remota` usa `ast.parse` y **no**
      contiene ningún `in` / `assert ... not in <fuente>` sobre el texto del módulo.
- [ ] **C3 (bloqueante del v1):** `git diff --name-only` de la rama **no** incluye
      `backend/api/diag.py` ni ningún archivo fuera de la tabla de §4.7.
- [ ] **[ADICIÓN ARQUITECTO] §5.1:** `test_toda_accion_ejecutable_cita_un_simbolo_que_existe` y
      `test_cannot_no_tiene_ejecutor` verdes; toda fila `CAN`/`DEPENDS` del catálogo resuelve su
      `evidence` con `importlib`, y ninguna fila quedó `CAN`/`DEPENDS` "de palabra".
- [ ] Los **4** archivos de test backend están registrados en **las dos** listas del ratchet
      (`run_harness_tests.sh:20` y `run_harness_tests.ps1:13`) y `test_harness_ratchet_meta.py` queda verde.
- [ ] `test_harness_flags.py` verde con la key nueva en `_CURATED_DEFAULTS_ON` (**:467**) y en
      `_CATEGORY_KEYS["devops"]` (`harness_flags.py:217`).
- [ ] **C12:** la key tiene entrada en `PLAIN_HELP` (`services/harness_flags_help.py`) y **no**
      aparece en la lista de faltantes de `test_plain_help_covers_all_registry_keys`. Los 4 fallos
      ajenos preexistentes de ese archivo siguen igual que antes del cambio (salida guardada).
- [ ] **NO** se agregó la key a `_REQUIRES_MAP_FROZEN` (la flag no declara `requires`; agregarla
      pondría rojo `test_requires_map_is_frozen`). `tests/test_harness_flags_requires.py` verde.
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
