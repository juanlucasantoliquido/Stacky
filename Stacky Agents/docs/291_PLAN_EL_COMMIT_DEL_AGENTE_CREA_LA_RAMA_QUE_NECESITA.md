# Plan 291 — El commit del agente crea la rama que necesita

**Estado:** MEJORADO (v1 → v2) — sin implementar
**Fecha:** 2026-08-02
**Rama de trabajo:** `docs/plan-279`
**Alcance:** backend (`services/gitlab_provider.py`, `services/incident_dev_autocommit.py`), registro de **3** flags, tests. **Cero frontend.**
**Veredicto de la crítica v1:** 🔴 **RECHAZADO — 6 bloqueantes.** Todos corregidos en esta v2 (ver CHANGELOG §8).
**Sello:** `Juez v2: subagente independiente, misma corrida, contexto limpio`

> **Lo que la crítica confirmó ejecutando (para que nadie lo vuelva a medir):** los **13 baselines** de F0 son exactos, uno por uno; el registry da **490 flags** con `STACKY_GITLAB_ENABLED` **NO registrada** y `STACKY_INCIDENT_DEV_PR_ENABLED` con `requires='STACKY_INCIDENT_DEV_RESOLVER_ENABLED'`; `start_branch` da **0** ocurrencias; ADO **sí** crea la rama en `ado_provider.py:183-190`; `_build_pr_body` **sí** se llama en `:73` antes del bucle de `:83`; `redact_secrets` **sí** enmascara emails; y `test_plan218_tracker_contract[gitlab]` **sí** emite un request HTTPS real.
>
> **Y lo que la crítica ROMPIÓ:** cuatro cosas que el v1 daba por ciertas y no lo son. Están en el CHANGELOG y cada una tiene su fase corregida. La lección de la serie 284-287 se repite acá: **los anclajes estaban casi todos bien y el plan igual era inimplementable**. Lo que falla no es dónde mira el plan, sino **qué da por existente y cuál cree que es el radio de alcance de su propia flag**.

---

## 1. Título, objetivo y KPI

### Objetivo en una frase

Que `commit_file` de GitLab pueda **crear la rama destino cuando no existe** (como el adaptador de Azure DevOps ya hace desde el plan 95), y que el diagnóstico deje de confundir *"la rama no existe"* con *"el archivo no existe"* — **sin que Stacky empiece a escribir en el GitLab real del operador hasta que él lo decida**.

### KPI

| # | KPI | Valor hoy | Meta | Cómo se mide |
|---|---|---|---|---|
| **K1** | Merge Requests abiertos por Stacky en el GitLab del operador con estado `opened` | **0** | ≥ 1 tras la activación | **NO MEDIBLE** hasta que el operador encienda la flag y corra el humo de §4.9. Ver §1.1. |
| **K2** | Commits del **auto-PR de incidencias** fuera de una rama con prefijo `stacky/` | **0** | **0** (invariante **del auto-PR**, NO de `commit_file`) | Test **F4.7**, que ejercita `maybe_open_pr_for_incident_dev` y lee la rama que **el producto** construyó. Ver §1.2. |
| **K3** | Llamadas a `commit_file` de GitLab que fallan por *"You can only create or edit files when you are on a branch"* con la flag ON | n/a (hoy la flag no existe) | **0** | Test F4.1/F4.2 contra el doble. |
| **K4** | Archivos del auto-PR commiteados sin pasar por el detector de secretos | **todos** (hoy no se inspecciona nada) | **0** | Test F5.2 sobre el consumidor final. **Detectar va ON; enmascarar va OFF** (§3.2). |

#### 1.2 — Sobre K2: el invariante es del auto-PR, NO de la flag

> **CORRECCIÓN DE LA v1, y es la corrección más importante del documento.**
> El v1 escribía K2 como *"Commits de Stacky fuera de una rama `stacky/` = 0 (invariante)"* y lo daba por probado con un test que asertaba `posts[i][1]["branch"].startswith("stacky/")` sobre **ramas que el propio test pasaba como argumento**. Eso es un gate que no puede fallar: comprueba su propio input.
>
> Y el invariante, escrito así, es **falso**. `commit_file` de GitLab tiene **TRES** consumidores, medidos el 2026-08-02:
>
> | Consumidor | Archivo:línea | De dónde sale la rama | ¿Empieza con `stacky/`? |
> |---|---|---|---|
> | Auto-PR del Dev Resolutor | `services/incident_dev_autocommit.py:88` | `_BRANCH_PREFIX` (`:22`) + ticket + exec | **SÍ, siempre** |
> | Editor de pipelines | `api/pipeline_editor.py:285` | la rama que **tipea el operador** en el body (obligatoria, `:218-220`; rechazada si coincide con la default, `:227-229`) | **NO necesariamente** |
> | Generador de pipelines | `api/pipeline_generator.py:122` | `body.get("branch") or f"feature/pipeline-{_slug(spec.name)}"` (`:97`) | **NO** — autogenera `feature/pipeline-…` |
>
> **Consecuencia dura, que el v1 no declaraba en ningún lado:** encender `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` no habilita solo al auto-PR. Habilita a los **tres**, porque la perilla vive en `commit_file`. Con la flag ON, el generador de pipelines puede crear en el GitLab del operador una rama `feature/pipeline-<slug>` que hoy no crea.
>
> Eso **no es un motivo para no hacerlo** — es coherente con el objetivo (`commit_file` debe poder crear la rama destino, venga de donde venga el llamado) —, pero **sí obliga a tres cosas**: (i) K2 se acota al auto-PR, que es lo único que este plan gobierna; (ii) el radio real se declara en §3.6 y en el texto de la flag que lee el operador; (iii) el gate de K2 pasa a ejercitar el producto, no su propio argumento (**F4.7 reescrito**).

#### 1.1 — Sobre K1: honestidad obligatoria del reporte

> **REGLA DURA PARA QUIEN IMPLEMENTE ESTE PLAN.**
> K1 **no se reporta como 0 %, ni como éxito, ni como fracaso**. Se reporta con estas palabras exactas en el resumen final:
>
> `K1: NO MEDIBLE — requiere que el operador encienda STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED y ejecute el humo de la sección 4.9 contra su GitLab. Ninguna fase de este plan lo mide.`
>
> Escribir "K1 = 0, meta no alcanzada" es **falso**: 0 es el valor esperado y correcto mientras la flag esté apagada. Escribir "K1 cumplido" es **falso** porque nada de este plan toca la red.

---

## 2. Por qué ahora / el gap

### 2.1 El defecto, con la evidencia

`services/gitlab_provider.py:785` — `commit_file` postea a `/projects/:id/repository/commits` con este body (líneas **798-807**):

```python
body, _ = self._client._request(
    "POST",
    f"/projects/{proj_path}/repository/commits",
    json_body={
        "branch": branch,
        "commit_message": message,
        "actions": [{"action": action, "file_path": path, "content": content}],
    },
)
```

**No hay `start_branch`.** Medido el 2026-08-02:

```
grep -rn "start_branch" --include=*.py "Stacky Agents/backend"   →   0 resultados
```

La API v4 de GitLab, en `POST /projects/:id/repository/commits`, **rechaza un commit sobre una rama que no existe** salvo que el body incluya `start_branch` con el nombre de la rama base desde la cual crearla. Sin `start_branch`, la respuesta documentada es `400 Bad Request` con el mensaje `"You can only create or edit files when you are on a branch"`.

### 2.2 El agravante: el diagnóstico apunta al lugar equivocado

`services/gitlab_provider.py:765` — `_detect_commit_action`:

```python
try:
    body, _ = self._client._request(
        "GET",
        f"/projects/{proj_path}/repository/files/{encoded_path}",
        params={"ref": branch},
    )
    return "update", self._decode_file_content(body)
except TrackerApiError as e:
    if e.status == 404:
        return "create", None
    raise
```

Cuando la rama **no existe**, ese `GET` devuelve **404** — porque no hay rama, no porque no haya archivo. El código lo interpreta como `"create"` y **sigue avanzando hacia el POST que va a fallar**, en vez de detenerse con un diagnóstico correcto. El operador termina viendo el 400 críptico de GitLab, que no menciona la rama que falta.

### 2.3 El comentario que miente

`services/incident_dev_autocommit.py:88`:

```python
writer.commit_file(rel, content, branch, commit_msg)   # crea la rama en el 1er call
```

Ese comentario es **verdadero para Azure DevOps y falso para GitLab**:

- **ADO** (`services/ado_provider.py:146-192`) resuelve el ref del branch; si `refs_list` viene vacío, lee el default branch y hace `POST .../refs` con `"oldObjectId": "0" * 40` (líneas **183-190**) para **crear la rama**. Después pushea.
- **GitLab** (`services/gitlab_provider.py:785`) no hace nada equivalente.

**Esto es un bug de PARIDAD entre proveedores, no una capacidad nueva.** El plan lleva GitLab al comportamiento que ADO ya tiene entregado desde el plan 95 F1.a.

### 2.4 ⚠️ Naturaleza de este diagnóstico

> **DIAGNÓSTICO POR CÓDIGO Y POR CONTRATO DE LA API. NO FUE VERIFICADO EN VIVO CONTRA EL GITLAB DEL OPERADOR.**
>
> Nadie corrió este flujo contra `srvcgit01.imsolutions.local`. Lo que está probado es: (i) que `start_branch` no aparece en ninguna línea del backend, (ii) que ADO sí crea la rama y GitLab no, y (iii) qué dice la documentación de la API v4 de GitLab sobre commits en ramas inexistentes.
>
> **Quien implemente este plan NO debe asumir que el ciclo issue → commit → MR se probó de punta a punta.** No se probó. La única prueba end-to-end posible es el humo manual de §4.9, que **es del operador y está fuera del alcance de este plan**.

### 2.5 Por qué esto importa hoy

El proyecto **RIPLEY** del operador tiene `issue_tracker.type = "gitlab"` con `base_url = https://srvcgit01.imsolutions.local` (medido en `backend/projects/RIPLEY/config.json` el 2026-08-02). Los otros dos proyectos con tracker (`RSPACIFICO`, `RSSICREA`) son `azure_devops` — o sea que **el auto-PR funciona para dos de tres proyectos y muere en el tercero**, en silencio, con un 400 que no explica nada.

---

## 3. Principios y guardarraíles

### 3.1 La decisión central del plan: **(a) — el fix nace detrás de una flag en OFF citando (B)**

El prompt de este plan exige elegir explícitamente entre:

- **(a)** el fix nace detrás de una flag nueva en OFF citando la excepción **(B)**; o
- **(b)** el fix es puro, porque se demuestra con evidencia de código que el camino del post-hook **hoy no alcanza GitLab por otro motivo**.

**Se elige (a). La opción (b) es FALSA.** Evidencia, cadena completa, abierta archivo por archivo:

| Compuerta | Archivo:línea | Estado medido | ¿Detiene el camino? |
|---|---|---|---|
| El post-hook está registrado | `backend/app.py:1036` → `incident_dev_autocommit.register(ticket_status.register_post_hook)` | **registrado** | ❌ no detiene |
| `STACKY_INCIDENT_DEV_RESOLVER_ENABLED` (el master de la de abajo) | `backend/config.py:1212-1213`, `os.getenv(..., "true")` | **ON por default** | ❌ no detiene |
| `STACKY_INCIDENT_DEV_PR_ENABLED` | `backend/config.py:1220-1221`, `os.getenv(..., "true")` | **ON por default** | ❌ no detiene |
| El checkbox "Abrir PR" de la UI | `frontend/src/incidents/incidentDevPrModel.ts:8` → `export const DEFAULT_OPEN_PR = true; // premarcado` | **premarcado** | ❌ no detiene |
| El intent se registra | `backend/api/agents.py:1330-1336` | se registra si hay repo git | ❌ no detiene |
| La fábrica devuelve el writer de GitLab | `services/repo_writer.py:33` → `services/tracker_provider.py:130-156` | devuelve `GitLabTrackerProvider` cuando `tracker_type == "gitlab"` | ❌ no detiene |
| `STACKY_GITLAB_ENABLED` | `backend/config.py:1297-1298`, default `"false"` — **pero `backend/.env:7` dice `STACKY_GITLAB_ENABLED=true`** | **ENCENDIDA en la máquina del operador** | ⚠️ **es una decisión del operador, no del código** |

> **La crítica v2 recorrió esta cadena compuerta por compuerta, abriendo cada archivo, y la confirma entera.** Los siete anclajes son exactos y la conclusión se sostiene: **la opción (b) es FALSA**. No hay ninguna compuerta de código que detenga el camino hacia GitLab. La única que existe está **encendida en el `.env` del operador**, medido.

La única compuerta que hoy corta el camino es `STACKY_GITLAB_ENABLED`, y **no sirve como argumento para (b)** por dos razones medidas:

1. **Es exactamente la flag que el operador enciende para usar GitLab.** Sin ella no funciona ni el listado de tickets de RIPLEY (`tracker_provider.py:133-136` lanza `TrackerConfigError`). Si el operador usa GitLab para algo, esa flag está ON. Un plan que se apoye en ella para prometer "esto no escribe nada" está apoyándose en que el operador **no use el producto**.
2. **El plan 290 F5 la llevó a la interfaz**, así que es un interruptor de un click, no una constante de compilación.

**Conclusión: arreglar `commit_file` convertiría un camino que hoy FALLA en un camino que ESCRIBE en el GitLab real del operador — creando ramas y Merge Requests que nadie vio funcionar nunca.** Eso es de lleno la excepción **(B)**: *escribe en un sistema real del operador*.

Que ADO ya lo haga es **precedente, no autorización**. El operador nunca vio a Stacky crear una rama en su GitLab.

### 3.2 El eje se parte en dos: lo que lee y lo que escribe

El riel de la casa dice: *"Si una capacidad mezcla parte inocua y parte que escribe, partila en dos flags: ver/diffear ON, la que escribe OFF citando (B)."* Acá el corte es limpio:

| Mitad | Qué hace | Escribe en GitLab | Decisión |
|---|---|---|---|
| **Sonda de rama** (`branch_exists`) + diagnóstico correcto en `_detect_commit_action` | Un `GET` de solo lectura y un mensaje de error preciso donde antes había un 400 críptico | **NO** | **Sin flag** (ver §3.3) |
| **Creación de la rama** (`start_branch` en el body del POST) | Hace que GitLab **cree una rama** en el repo del operador | **SÍ** | **`STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`, nace OFF, cita (B)** |
| **Detección de secretos** (inspeccionar y **reportar**, sin tocar el archivo) | Marca qué archivos tienen pinta de traer un secreto y lo lista en la descripción del MR | **NO** — el archivo se commitea byte-idéntico | **`STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED`, nace ON** |
| **Enmascarado del contenido** (reemplazar el texto **antes** de commitear) | **Cambia los bytes** que se escriben en el repo real del operador | **SÍ** (ADO **hoy mismo**; GitLab cuando se encienda la otra) | **`STACKY_AUTOCOMMIT_REDACT_ENABLED`, nace OFF, cita (B)** |

#### 3.2.1 — Por qué el v1 se equivocaba acá, con la prueba ejecutada

> **CORRECCIÓN DE LA v1. Es el segundo bloqueante de la crítica y el más peligroso de los dos.**
>
> El v1 ponía **una sola** flag de redacción, **ON por default**, clasificada como *"no abre camino nuevo; endurece uno existente"*. Las dos mitades de esa frase son falsas.
>
> **(1) `redact_secrets` DESTRUYE código fuente legítimo.** No es una hipótesis: se ejecutó contra `services/pr_review_sanitize.py` el 2026-08-02.
>
> ```
> ENTRADA                                  SALIDA de redact_secrets()
> password = cfg.get("db_password")   →    password = ***REDACTED***
> api_key  = os.getenv("X")           →    api_key = ***REDACTED***
> secret   = None                     →    secret = ***REDACTED***
> # autor: juan.santoliquido@gmail.com →   # autor: ***REDACTED***
> ```
>
> Los patrones responsables son `(?i)(password\s*[=:]\s*)\S+`, `(?i)(secret\s*[=:]\s*)\S+` y `(?i)(api[_-]?key\s*[=:]\s*)\S+` (`pr_review_sanitize.py:16-18`). **Cualquier archivo de Python, C#, TypeScript o JSON que asigne una variable llamada `password`, `secret` o `api_key` sale roto del filtro.** Un fixture de test con `password = "x"` sale roto. Ese archivo roto es exactamente el que se commitea y se propone en el MR.
>
> **(2) `redact_secrets` no fue escrito para esto.** Su propio docstring (`pr_review_sanitize.py:1-3`) dice: *"Saneo de diffs antes de mandarlos a un modelo"*. Es una sanitización **con pérdida sobre un camino de LECTURA**, donde perder información es gratis. Reusarla sobre un camino de **ESCRITURA** es un error de categoría: acá la pérdida se persiste en el repositorio del operador.
>
> **(3) Y sale ON sobre un camino que YA está vivo.** `RSPACIFICO` y `RSSICREA` son `azure_devops`, `ado_provider.commit_file` está implementado desde el plan 95, y las dos flags del Dev Resolutor están ON por default. O sea: **el enmascarado ON por default cambia hoy, sin que el operador decida nada, los bytes que Stacky escribe en el Azure DevOps de la empresa.** Eso es de lleno la excepción **(B)**, y el v1 la clasificaba como kill-switch.
>
> **La corrección respeta el riel que el propio plan cita en §3.2:** *"si una capacidad mezcla parte inocua y parte que escribe, partila en dos flags: ver/diffear ON, la que escribe OFF"*. El v1 enunciaba ese riel y después **no lo aplicaba a su propia F5**. La v2 lo aplica: **detectar y reportar va ON; mutar el archivo va OFF**.
>
> **Además, cuando el enmascarado se encienda, NO usa `redact_secrets` entero.** Usa `_PATRONES_ALTA_CONFIANZA`, un subconjunto propio del plan (F5) con **solo** los patrones que no pueden confundirse con código: AWS `AKIA…`, GitHub `ghp_…`, GitLab `glpat-…`, Slack `xox…`, `Authorization: Bearer …` y bloques `-----BEGIN … PRIVATE KEY-----`. **Quedan FUERA** los tres de `password|secret|api_key` y **el de email**: enmascarar el mail de una cabecera de licencia no protege nada y rompe la atribución.

### 3.3 Por qué la sonda de rama NO lleva flag (decisión justificada, no omisión)

Un plan de esta casa debe justificar por escrito cada flag que **no** crea. La sonda no lleva flag porque:

1. Es un `GET` de solo lectura contra `/repository/branches/:branch`. No escribe, no dispara loop, no llama a ningún modelo, no gasta tokens en reposo. **No cae en (A) ni en (B).**
2. **No puede cambiar ningún resultado exitoso.** Si la rama existe, `_detect_commit_action` se comporta byte por byte como hoy (mismo `GET` de archivos, mismo `("update", contenido)` o `("create", None)`).
3. Su único efecto observable es reemplazar un `400` incomprensible por un error preciso **en un camino que ya fallaba**. Eso es corrección de clasificación de errores, no una capacidad que el operador tenga que decidir.
4. Precedente propio de la serie: el **plan 286** entregó un cambio de ruteo de escritura con **cero flags nuevas** por el mismo razonamiento.

Costo: **una llamada HTTP `GET` extra por cada `commit_file` de GitLab**. Se declara explícitamente acá porque no es cero (ver Riesgo R7).

### 3.4 Rieles innegociables que este plan respeta

| Riel | Cómo se respeta acá |
|---|---|
| **Human-in-the-loop** | Es el riel más cargado de este plan. Nada se mergea solo: `approve` y `merge` viven detrás del botón del operador en `api/pr_review.py:387-411`, y `merge` además exige `confirm_merge is True` (`:391-393`) o devuelve `400 confirm_merge_required`. **Este plan no toca ese endpoint.** Además, la creación de la rama misma queda detrás de una flag que solo el operador enciende. |
| **Mono-operador sin auth real** | No se agrega ningún control de permisos. `current_user()` sigue siendo un header sin validar; el gate real es la flag. |
| **Cero trabajo extra al operador** | Con las **tres** flags en su default (start_branch **OFF**, scan **ON**, redact **OFF**) el operador **no tiene que hacer nada** y **ningún byte escrito cambia respecto de hoy**. Lo único que cambia es (i) el mensaje de error del auto-PR de GitLab, que pasa a ser útil, y (ii) que la descripción del MR puede listar archivos sospechosos. |
| **Backward-compatible** | Ninguna firma pública cambia de forma incompatible: `_detect_commit_action` gana un parámetro **keyword-only con default `None` = comportamiento de hoy**; `_build_pr_body` gana un keyword con default `None`. ⚠️ **Pero el comportamiento OBSERVABLE de `commit_file` sí cambia** (una llamada HTTP más), y eso **rompe dos tests existentes**: ver F4 y el bloqueante C2. |
| **Reusar lo existente** | `create_merge_request` (`gitlab_provider.py:819`) **se reusa tal cual, NO se reescribe**. `_MAX_FILES = 60` (`incident_dev_autocommit.py:23`) **se queda intacto**. `_BRANCH_PREFIX = "stacky/incidencia-"` (`:22`) **se queda intacto**. ⚠️ **`redact_secrets` YA NO se reusa entero** (§3.2.1). Y **`_default_branch_name` NO se inventa de cero**: hay una implementación previa idéntica en `api/devops_production.py:48-51` — ver F1 y el hallazgo C7. |
| **Sin degradar** | Cada fase declara qué pasa con su flag en OFF, y **con los tres defaults de la v2 el sistema escribe exactamente los mismos bytes que hoy**. (El v1 fallaba este riel: su `STACKY_AUTOCOMMIT_REDACT_ENABLED=ON` cambiaba el contenido commiteado en el ADO del operador desde el día 1.) |

### 3.5 Hallazgo de plomería que ahorra un rojo garantizado

> **NINGUNA de las tres flags nuevas puede declarar `requires=`.** Verificado ejecutando contra el registry real el 2026-08-02 (y **re-ejecutado por la crítica v2, mismo resultado**):
>
> ```
> STACKY_GITLAB_ENABLED             -> NO REGISTRADA
> STACKY_INCIDENT_DEV_PR_ENABLED    -> REGISTRADA type=bool requires='STACKY_INCIDENT_DEV_RESOLVER_ENABLED'
> total flags: 490
> ```
>
> - Apuntar `requires="STACKY_GITLAB_ENABLED"` **rompe la regla R1** de `validate_requires_graph` (`services/harness_flags.py:7343`): *"requires debe ser la key de un FlagSpec existente"*. Esa key **no está en `FLAG_REGISTRY`** — vive solo en `config.py:1297`.
> - Apuntar `requires="STACKY_INCIDENT_DEV_PR_ENABLED"` **rompe la regla R4** (`:7346-7347`): *"profundidad máxima 1 — un master apuntado NO puede tener a su vez requires"*. Y esa flag **ya tiene** `requires='STACKY_INCIDENT_DEV_RESOLVER_ENABLED'`.
>
> **Consecuencia práctica: las tres flags llevan `requires=None` (o sea, se omite el parámetro) y `tests/test_harness_flags_requires.py::_REQUIRES_MAP_FROZEN` (línea 120) NO se toca.** Verificado leyendo el test: `test_requires_map_is_frozen` construye `{s.key: s.requires for s in FLAG_REGISTRY if s.requires}` — una flag **sin** `requires` sencillamente no entra en el mapa. La dependencia real se explica en la `description` en prosa, que es donde el operador la lee.

### 3.6 — Radio de alcance REAL de `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`

> **La perilla vive en `commit_file`, no en el auto-PR.** Por lo tanto, encenderla habilita la creación de ramas para los **tres** consumidores de la tabla de §1.2, no solo para el Dev Resolutor.
>
> **Se elige deliberadamente NO acotarla al auto-PR**, por tres razones:
>
> 1. **El defecto es del proveedor, no del caso de uso.** `commit_file` de GitLab está roto contra cualquier rama inexistente, venga el llamado de donde venga. Un parche que arregle solo un caller deja los otros dos rotos y crea dos comportamientos distintos para la misma función pública — exactamente la asimetría que este plan viene a cerrar entre ADO y GitLab.
> 2. **Los otros dos consumidores ya son human-in-the-loop duro.** `pipeline_editor` y `pipeline_generator` solo commitean con `confirm=True` explícito del operador (gate verificado en `tests/test_plan73_generator_endpoint.py:86` — *"/commit sin confirm → 400; commit_file NUNCA se llama"*). Nadie llega ahí sin apretar un botón.
> 3. **Meter un parámetro `permitir_crear_rama=` en `commit_file` para acotarlo rompería el puerto `RepoWriter`** (`services/repo_writer.py:18`), cuya firma es idéntica en ADO y GitLab. Y ADO **ya crea la rama sin preguntarle a nadie**: acotar solo a GitLab dejaría los dos proveedores más desparejos, no menos.
>
> **Pero se declara, y se declara en el texto que el operador lee.** La `description` de la flag (F3) y la ayuda llana (F3, punto 4) dicen explícitamente que también aplica al armado de pipelines. Un operador que enciende esto tiene que saber que la rama `feature/pipeline-…` que hoy le falla, mañana se crea.

### 3.7 — Lo que este plan NO puede garantizar, dicho antes de las fases

| Afirmación tentadora | Por qué es falsa |
|---|---|
| *"Con la flag OFF, cero escritura en GitLab"* | **Falso a nivel sistema.** Con la flag OFF, `commit_file` lanza `TrackerApiError`, el `except` de `incident_dev_autocommit.py:106` lo captura y `_comment_issue_safe` (`:110`) **postea un comentario en la Issue de GitLab**. Cero escritura **en el repositorio**; el tracker sí recibe un comentario. Eso ya pasa hoy y el plan no lo cambia — pero no se puede escribir *"cero escritura"* sin la aclaración. |
| *"Los tests no tocan la red"* | Solo si el comando **exporta `STACKY_TEST_MODE`**. Ver la convención de §4 y el bloqueante C4. |
| *"Delta cero en todas las suites vecinas"* | **Falso en F4.** `tests/test_plan73_repo_writer.py` se rompe a propósito. Ver C2. |

---

## 4. Fases

> **Convención para todas las fases.** El comando de test es siempre, literal, **por archivo**, con **las dos variables de entorno obligatorias**, desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:
>
> ```bash
> STACKY_TEST_MODE=1 \
> DATABASE_URL="sqlite:///<scratchpad>/db_<nombre_del_archivo>.db" \
>   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q
> ```
>
> Se usa **`.venv`** (py3.13.5), **no** `venv` (py3.11.9, sin las dependencias).
> **Nunca** se corre `pytest tests` entero: la suite completa da miles de errores de contaminación cruzada y **no es un veredicto**.
>
> ⚠️ **`STACKY_TEST_MODE=1` NO ES OPCIONAL, y esto es una corrección de la v1 (bloqueante C4).**
> El v1 escribía el comando **sin** esa variable, y al mismo tiempo su DoD #18 prometía *"cero llamadas de red: el guard de egress de `conftest.py` bloquea `connect()` bajo `STACKY_TEST_MODE`"*. Abriendo `tests/conftest.py:35`:
>
> ```python
> if os.environ.get("STACKY_TEST_MODE", "").strip().lower() not in ("1", "true", "yes"):
>     yield
>     return          # ← el guard NO se instala
> ```
>
> **Sin la variable, el guard se desinstala solo.** El plan prometía una garantía que sus propios comandos apagaban. En un plan cuyo riesgo #1 es tocar el GitLab real de la empresa, eso no es un detalle de forma.
>
> ⚠️ **Y el guard tiene un límite que hay que conocer: engancha `socket.connect`, no la resolución DNS.** Medido el 2026-08-02: `tests/test_plan218_tracker_contract.py::test_contrato_del_puerto_tracker[gitlab]` emite un `requests` real y muere en `getaddrinfo` contra `gl.test` — **antes** de llegar a `connect()`, así que el guard nunca se entera. Si ese host algún día resolviera, el guard lo atajaría; hasta entonces, la única defensa real es **no apuntar ningún test a un host que exista**.
>
> ⚠️ **`DATABASE_URL` a scratchpad tampoco es opcional.** Sin él, un pytest suelto escribe en la base viva del operador (`backend/data`). Ver también F6/F7, que además necesitan `STACKY_DATA_DIR`.

---

### F0 — Congelar la línea base (sin tocar código de producto)

**Objetivo:** dejar por escrito, medido, el estado de cada suite que este plan puede mover, para que el criterio de cada fase sea **delta cero** y no "todo verde".

**Archivos:** ninguno de producto. Solo se registra el resultado en el mensaje de commit de F1.

**Baselines MEDIDOS el 2026-08-02** (con `DATABASE_URL` apuntando a una base de scratchpad, nunca la del operador, **y con `STACKY_TEST_MODE=1`**):

> ✅ **RE-MEDIDOS UNO POR UNO POR LA CRÍTICA v2 el 2026-08-02. Los 13 números coinciden EXACTO**, incluidos los cinco rojos de fábrica y el `10 passed` de `test_plan73_generator_endpoint.py` sobre el árbol sucio. **No hace falta volver a medirlos**: si al implementar dan otro número, cambió el árbol, no la medición.

| Archivo de test | Resultado base | ¿Rojo de fábrica? |
|---|---|---|
| `tests/test_gitlab_provider.py` | **26 passed** | verde |
| `tests/test_plan73_repo_writer.py` | **6 passed** | verde |
| `tests/test_plan70_gitlab_provider_complete.py` | **19 passed** | verde |
| `tests/test_incident_dev_autocommit.py` | **11 passed** | verde |
| `tests/test_plan73_generator_endpoint.py` | **10 passed** | verde ⚠️ (ver nota) |
| `tests/test_harness_flags.py` | **59 passed** | verde |
| `tests/test_harness_flags_requires.py` | **9 passed** | verde |
| `tests/test_flag_wiring.py` | **5 passed** | verde |
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** | 🔴 **ROJO DE FÁBRICA** |
| `tests/test_flags_env_read_meta.py` | **1 failed, 1 passed** | 🔴 **ROJO DE FÁBRICA** |
| `tests/test_plan218_coupling_ratchet.py` | **3 failed, 7 passed** | 🔴 **ROJO DE FÁBRICA** |
| `tests/test_plan218_capability_matrix.py` | **2 failed, 8 passed** | 🔴 **ROJO DE FÁBRICA** |
| `tests/test_plan218_tracker_contract.py` | **1 failed, 9 passed** | 🔴 **ROJO VIVO** — `test_contrato_del_puerto_tracker[gitlab]` sale a la red |

> 🔴 **Sobre `test_plan218_tracker_contract.py`: la afirmación del v1 es CIERTA y la crítica la reprodujo.** El error exacto, con `STACKY_TEST_MODE=1` puesto:
>
> ```
> ContractViolation: [gitlab] escenario 'create_item' (tracker.items.create):
>   Red contra https://gl.test: HTTPSConnectionPool(host='gl.test', port=443):
>   Max retries exceeded ... NameResolutionError ... getaddrinfo failed
> ```
>
> O sea: **un test del repo emite un request HTTPS real** en cada corrida. Hoy es inofensivo porque `gl.test` no resuelve y porque el host es de fantasía (`_make_gitlab_provider` lo fija en `tests/test_plan218_tracker_contract.py:97`), pero es un riesgo **del arnés**, no de este plan: el día que alguien apunte ese fixture a un host real, el arnés le pega.
>
> **Decisión de alcance: NO se arregla acá.** Es deuda ajena del plan 218 y tocarla movería un archivo que este plan no gobierna. **Se anota como acción para el operador en §6** y se declara que ninguna fase de este plan lo empeora ni lo mejora (criterio delta cero: `1 failed, 9 passed`).
>
> **Prohibido correrlo durante la implementación** salvo con `STACKY_TEST_MODE=1`, y aun así sabiendo que el guard no ataja el fallo de DNS.

> ⚠️ **`tests/test_plan73_generator_endpoint.py` está MODIFICADO por una sesión paralela viva.** Su baseline de 10 passed se midió sobre el árbol sucio. Si al implementar da otro número, **volver a medirlo antes de culpar a este plan**, con `git stash list` prohibido: simplemente re-medir y anotar.

**Rojos de fábrica del backend: 5 archivos / 11 tests fallando** (los 4 que el enunciado del plan anticipaba, **más** `test_plan218_tracker_contract.py`, que sale a la red y por eso no es determinista).

**Rojos de fábrica del frontend: 5 ratchets** (`uiDebt`, `formDebt`, `motionDebt`, `formatDebt`, `adhocModal`). **Este plan no toca frontend**, así que no los mueve.

**Criterio binario de F0:** los 13 números de la tabla están transcriptos en el cuerpo del commit de F1. Sin comando propio.

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F1 — `branch_exists`: preguntar si la rama existe, en vez de deducirlo de un 404 ajeno

**Objetivo:** dar al proveedor de GitLab una forma explícita y de solo lectura de saber si una rama existe.

**Archivos:**
- `Stacky Agents/backend/services/gitlab_provider.py` (se agregan los dos métodos)
- `Stacky Agents/backend/api/devops_production.py` (**F1.b**: 3 líneas → 1, para no duplicar)

**Símbolos EXACTOS:**
- **Se agrega:** el método `branch_exists(self, branch: str) -> bool` en la clase `GitLabTrackerProvider`.
- **Se agrega:** el método privado `_default_branch_name(self) -> str` en la misma clase.
- **Ubicación (anclada por SÍMBOLO, no por línea):** inmediatamente **antes** de `def _decode_file_content`, dentro del bloque comentado `# ── Plan 73 F4 — RepoWriter (sub-puerto separado de CIProvider) ──`.

**Pseudocódigo:**

```python
def branch_exists(self, branch: str) -> bool:
    """GET /projects/:id/repository/branches/:branch — ¿existe la rama?

    SOLO LECTURA. 200 → True; 404 → False; cualquier otro TrackerApiError se
    PROPAGA (un 401/403/500 NO es "no existe": tratarlo como False haría que
    commit_file intentara crear una rama que quizás ya está, C1 del plan 73).

    El nombre de rama del auto-PR lleva una BARRA ('stacky/incidencia-12-exec-34'),
    así que va URL-encodeado con safe="" o GitLab lo lee como dos segmentos de path.
    """
    from services.tracker_provider import TrackerApiError   # lazy import — patrón del repo
    proj_path = self._client._project_path()
    encoded_branch = urllib.parse.quote(branch, safe="")
    try:
        self._client._request(
            "GET",
            f"/projects/{proj_path}/repository/branches/{encoded_branch}",
        )
        return True
    except TrackerApiError as e:
        if e.status == 404:
            return False
        raise


def _default_branch_name(self) -> str:
    """GET /projects/:id → campo 'default_branch'. Cadena vacía si el repo no tiene
    rama default (repo recién creado y VACÍO).

    NO adivina 'main': si el repo usa 'master' o 'develop', devuelve eso.
    NO importa nada de `api/` — `services/` NUNCA importa `api/` (riel duro del repo).

    ⚠️ ESTA ES LA IMPLEMENTACIÓN CANÓNICA a partir de este plan. La rama GitLab de
    `api/devops_production._default_branch` (:48-51) hacía EXACTAMENTE este GET y
    pasa a delegar acá (F1.b). Ver el hallazgo C7 del plan 291.
    """
    proj_path = self._client._project_path()
    body, _ = self._client._request("GET", f"/projects/{proj_path}")
    return str((body or {}).get("default_branch") or "")
```

#### F1.b — No duplicar: `api/devops_production._default_branch` delega en el provider

> **CORRECCIÓN DE LA v1 (hallazgo C7).** El v1 presentaba `_default_branch_name` como código nuevo y justificaba no reusar nada con *"`services/` nunca importa `api/`"*. La restricción es cierta, pero **la conclusión estaba invertida**: no hay que escribir una segunda implementación, hay que **mover la única que existe al lugar correcto y que la vieja delegue**.
>
> Porque ya existe, y es idéntica — `api/devops_production.py:37-51`:
>
> ```python
> def _default_branch(provider, project):
>     if provider.name == "azure_devops":
>         from services.ado_pipeline_definitions import _default_branch as _ado_default_branch
>         return _ado_default_branch(provider, project)
>     # GitLab
>     proj_path = provider._client._project_path()
>     body, _ = provider._client._request("GET", f"/projects/{proj_path}")
>     return body.get("default_branch") or "main"
> ```
>
> Mismo endpoint, mismo campo. **Dejarlas conviviendo crea dos contratos distintos para la misma llamada**: una devuelve `""` para el repo vacío y la otra `"main"`. Y esa divergencia no es teórica: `incident_dev_autocommit._default_branch_for` (`:157-164`) usa la de `api/` para calcular el `target_branch` del MR, mientras `commit_file` usaría la del provider para el `start_branch`. Dos funciones decidiendo la misma rama base **en el mismo flujo**.
>
> **Cambio EXACTO, mínimo y retro-compatible** — en `api/devops_production.py`, reemplazar las tres líneas del bloque `# GitLab` por:
>
> ```python
>     # GitLab — Plan 291 F1.b: implementación única en el provider.
>     # El fallback "main" se PRESERVA acá (contrato histórico de este helper);
>     # el provider devuelve "" para el repo vacío y commit_file lo traduce a
>     # TrackerApiError(kind="repo_empty"). Los dos contratos quedan explícitos.
>     return provider._default_branch_name() or "main"
> ```
>
> **Es `api/` importando de `services/`, que es la dirección PERMITIDA.** El riel prohíbe lo contrario.
>
> **Caso borde declarado:** si `provider` no es GitLab ni ADO, `_default_branch_name` no existe y hoy tampoco andaría (`provider._client._project_path()` fallaría igual). Comportamiento sin cambios.
>
> **Test F1.6 (nuevo):** con un doble de provider cuyo `_default_branch_name()` devuelve `"develop"`, `api.devops_production._default_branch(doble, "P")` devuelve `"develop"`; con `""`, devuelve `"main"`. **Guarda la PRESENCIA del fallback histórico**, que es lo que un refactor descuidado rompería.

**Casos borde cubiertos:**

| Caso | Comportamiento |
|---|---|
| Rama con barra (`stacky/incidencia-12-exec-34`) | `quote(branch, safe="")` → `stacky%2Fincidencia-12-exec-34` |
| Rama existe | `True` |
| Rama no existe (404) | `False` |
| 401 / 403 / 500 | **propaga** `TrackerApiError` — no miente diciendo `False` |
| Repo vacío sin rama default | `_default_branch_name()` devuelve `""` (F4 lo traduce a error claro) |
| Rama default llamada `master` / `develop` | se **lee**, no se adivina |

**Tests PRIMERO.** Archivo NUEVO: `Stacky Agents/backend/tests/test_plan291_start_branch.py`

Doble del cliente — se reusa el idioma exacto que ya usa `tests/test_plan73_repo_writer.py:11-21`:

```python
def _provider_con_doble():
    from services.gitlab_provider import GitLabTrackerProvider
    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)   # sin __init__: cero red, cero TLS
    p._client = MagicMock()
    p._client._project_path.return_value = "grp%2Fproj"
    p._project = "proj"; p._group = ""; p._epics_native = False
    return p, p._client
```

Casos de F1:

| id | Caso | Aserción |
|---|---|---|
| F1.1 | `branch_exists("stacky/incidencia-12-exec-34")` con el doble devolviendo `({}, {})` | devuelve `True` **y** la URL del `GET` contiene `stacky%2Fincidencia-12-exec-34` (no `stacky/incidencia`) |
| F1.2 | el doble lanza `TrackerApiError(404, "not found", kind="not_found")` | devuelve `False` |
| F1.3 | el doble lanza `TrackerApiError(403, "forbidden", kind="auth")` | **lanza** `TrackerApiError` (usar `pytest.raises`) |
| F1.4 | `_default_branch_name()` con body `{"default_branch": "master"}` | devuelve `"master"` — **no** `"main"` |
| F1.5 | `_default_branch_name()` con body `{}` (repo vacío) | devuelve `""` |
| **F1.6** | **F1.b** — `api.devops_production._default_branch(doble, "P")` con `doble.name = "gitlab"` y `doble._default_branch_name() -> "develop"` | devuelve `"develop"` |
| **F1.7** | **F1.b** — mismo doble, `_default_branch_name() -> ""` | devuelve `"main"` — **el fallback histórico se PRESERVA** (guarda la presencia, no la ausencia) |

**Cómo se comprueba el ROJO:** antes de escribir el código, correr el archivo de tests. F1.1-F1.5 fallan con `AttributeError: 'GitLabTrackerProvider' object has no attribute 'branch_exists'` (y `_default_branch_name`). F1.6/F1.7 fallan con `AttributeError` sobre el doble (hoy `_default_branch` va por `provider._client._request`, que el doble no expone). Ese `AttributeError` **es** el rojo, y es rojo por la razón correcta: el símbolo no existe.

**Comando:** el de la convención de §4, sobre `tests/test_plan291_start_branch.py`.

**Criterio BINARIO:** `7 passed` en ese archivo, y **delta cero** en:
```
tests/test_gitlab_provider.py             →  26 passed
tests/test_plan73_repo_writer.py          →   6 passed   ⚠️ delta cero SOLO hasta F3; F4 lo rompe a propósito (C2)
tests/test_plan218_capability_matrix.py   →   2 failed, 8 passed  (delta cero sobre el rojo de fábrica)
tests/test_plan95_production_endpoints.py →  (medir el baseline ANTES de F1.b y reproducirlo)
tests/test_plan250_api.py                 →  (idem)
tests/test_plan95_ado_parity.py           →  (idem)
tests/test_plan177_ado_commit_web_url.py  →  (idem)
```

> **Por qué esas cuatro suites nuevas:** son las que mencionan `_default_branch` y F1.b lo toca. Verificado que **la de plan 95 lo parchea entero** (`mock.patch("api.devops_production._default_branch", ...)` en `tests/test_plan95_production_endpoints.py:104`), así que F1.b le es invisible — **pero eso hay que reproducirlo midiendo, no creyéndole a este párrafo**. Verificado también que `api/pipeline_editor.py:223` importa `_default_branch` de **`services.ado_pipeline_definitions`**, NO de `devops_production`: F1.b no lo alcanza.

**Registro en los ratchets — EN EL MISMO COMMIT que crea el archivo:**

1. `Stacky Agents/backend/scripts/run_harness_tests.sh` — dentro del array `HARNESS_TEST_FILES=(` (declarado en la **línea 20**; **828** entradas medidas el 2026-08-02). Agregar, sin comillas, sin coma:
   ```
     tests/test_plan291_start_branch.py
   ```
2. `Stacky Agents/backend/scripts/run_harness_tests.ps1` — dentro del array `$HarnessTestFiles = @(` (declarado en la **línea 13**; **764** entradas medidas). Agregar **con comillas y con coma**:
   ```
     "tests/test_plan291_start_branch.py",
   ```
   ⚠️ **Trampa conocida: la ÚLTIMA entrada del `.ps1` no lleva coma.** Si se agrega al final, hay que ponerle coma a la que era última y dejar la nueva sin coma. Lo más seguro es **insertar en el medio**, junto a `"tests/test_plan73_repo_writer.py",`, y no tocar la cola.
3. ⚠️ **Los ratchets NO admiten rutas con espacios.** Por eso las entradas son relativas a `backend/` (`tests/...`), nunca absolutas.
4. Verificar que el archivo **no** quede en `tests/harness_ratchet_allowlist.txt` (207 líneas): registrar un test obliga a sacarlo del allowlist. Medido: **ningún** archivo de este eje está hoy en el allowlist, así que no hay nada que sacar — pero hay que confirmarlo con `grep -n "plan291" "Stacky Agents/backend/tests/harness_ratchet_allowlist.txt"` → 0 resultados.

> **Dato medido, fuera de scope:** `tests/test_gitlab_provider.py` está en el `.sh` pero **NO en el `.ps1`** (una de las 64 divergencias conocidas). **No la arregles en este plan**: cambiaría el conteo del `.ps1` y es deuda ajena. Solo se anota para que nadie se sorprenda.

**Flag:** ninguna (justificación completa en §3.3). **Default:** n/a.
**Impacto por runtime:** ninguno — `gitlab_provider` no conoce runtimes. **Fallback:** n/a.
**Trabajo del operador:** ninguno.

---

### F2 — `_detect_commit_action` deja de confundir "no hay rama" con "no hay archivo"

**Objetivo:** que un 404 de rama **no** se traduzca a `"create"`, porque no prueba nada sobre el archivo.

**Archivo:** `Stacky Agents/backend/services/gitlab_provider.py`

**Símbolos EXACTOS:**
- **Se agrega** una constante a nivel de módulo, junto a los demás módulos-nivel del archivo:
  ```python
  _ACCION_RAMA_NUEVA = "create_new_branch"   # SENTINELA INTERNO. NO es una acción de la API de GitLab.
  ```
- **Se modifica** la firma de `GitLabTrackerProvider._detect_commit_action` (hoy en `:765`), agregando un parámetro **keyword-only con default `None`**.

**Diff conceptual:**

```python
-    def _detect_commit_action(self, path: str, branch: str) -> tuple[str, str | None]:
+    def _detect_commit_action(
+        self, path: str, branch: str, *, rama_existe: bool | None = None,
+    ) -> tuple[str, str | None]:
         """...
+        rama_existe=False → devuelve (_ACCION_RAMA_NUEVA, None) SIN hacer el GET de
+          archivos: si la rama no existe, ningún archivo puede existir en ella, y un
+          404 de ese endpoint NO probaría nada sobre el archivo. Ese sentinela es
+          INTERNO: commit_file lo traduce a la acción real "create" de la API.
+        rama_existe=None (default) → comportamiento IDÉNTICO al de hoy. Retro-
+          compatible: cualquier caller viejo se comporta igual.
+        rama_existe=True → comportamiento IDÉNTICO al de hoy.
         """
         from services.tracker_provider import TrackerApiError
+        if rama_existe is False:
+            return _ACCION_RAMA_NUEVA, None
         proj_path = self._client._project_path()
         ...  # resto SIN CAMBIOS
```

**Casos borde:**

| Caso | Comportamiento |
|---|---|
| `rama_existe=False` | `(_ACCION_RAMA_NUEVA, None)` **y cero llamadas a `_request`** |
| `rama_existe=True` | idéntico a hoy |
| `rama_existe=None` (caller viejo) | idéntico a hoy — retro-compatible |
| archivo existe en rama existente | `("update", contenido)` — sin cambios |
| archivo no existe en rama existente | `("create", None)` — sin cambios |
| 500 del endpoint de archivos | propaga — sin cambios |

**Tests PRIMERO.** Mismo archivo `tests/test_plan291_start_branch.py`:

| id | Caso | Aserción |
|---|---|---|
| F2.1 | `_detect_commit_action("a.py", "stacky/x", rama_existe=False)` | devuelve `("create_new_branch", None)` — **explícitamente NO `"create"`** |
| F2.2 | mismo caso | `cliente._request.call_count == 0` — **no se hace el GET inútil** |
| F2.3 | `rama_existe=True`, el doble lanza `TrackerApiError(404)` | devuelve `("create", None)` (comportamiento de hoy preservado) |
| F2.4 | **sin** pasar `rama_existe` (caller viejo), el doble devuelve un body con contenido base64 de `"hola"` | devuelve `("update", "hola")` — retro-compatibilidad probada |

**Cómo se comprueba el ROJO:** F2.1 y F2.2 fallan hoy con `TypeError: _detect_commit_action() got an unexpected keyword argument 'rama_existe'`. F2.3 y F2.4 **pasan hoy** — están a propósito: son el guardián de no-regresión (guardan la **PRESENCIA** del comportamiento viejo, no su ausencia).

**Comando:** el de la convención de §4, sobre `tests/test_plan291_start_branch.py`.

**Criterio BINARIO:** `11 passed` (7 de F1 + 4 de F2). Delta cero en `test_plan73_repo_writer.py` (6 passed) y `test_gitlab_provider.py` (26 passed).

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F3 — Registrar las **TRES** flags (dos OFF por (B), una ON)

**Objetivo:** que existan las perillas que el operador va a mover, en su estado correcto, antes de que exista el código que las lee.

| Key | Default | Por qué |
|---|---|---|
| `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` | **OFF** | (B) — hace que GitLab **cree una rama** en el repositorio real |
| `STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED` | **ON** | Solo lee y reporta. No cambia un byte de lo que se escribe |
| `STACKY_AUTOCOMMIT_REDACT_ENABLED` | **OFF** | (B) — **cambia los bytes** que se escriben en el repo real (§3.2.1) |

⚠️ **Mecánica no negociable, y se equivoca fácil:** una flag **OFF NO declara `default=`** en su `FlagSpec` (ni siquiera `default=False`), porque `default_is_known(spec)` es literalmente `spec.default is not None` (`services/harness_flags.py:7299`) y `test_default_known_only_for_curated` (`tests/test_harness_flags.py:1187`) exige que el conjunto de keys con default conocido sea **EXACTAMENTE** `_CURATED_DEFAULTS_ON`. Una flag **ON** sí declara `default=True` **y** entra en `_CURATED_DEFAULTS_ON`. Verificado leyendo los dos tests.

> **Una flag nueva tiene OCHO guardianes.** Los siete que hay que editar (o confirmar que no hace falta) están abajo; el octavo es el par de ratchets, ya cubierto en F1. Cada punto está anclado **por símbolo**, porque las líneas se mueven en horas.

**Archivos y símbolos EXACTOS:**

**(1) `Stacky Agents/backend/services/harness_flags.py` — `_CATEGORY_KEYS`**
Agregar la key dentro de la **misma tupla de categoría que ya contiene `"STACKY_INCIDENT_DEV_PR_ENABLED"`**, que es `"capacidades_optin"`. Anclaje: buscar la línea `"STACKY_INCIDENT_DEV_PR_ENABLED",          # Plan 177 — auto-PR del Dev Resolutor` y agregar debajo:
```python
        # Plan 291 — el commit del agente crea la rama que necesita (GitLab)
        "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED",   # Plan 291 — crea la rama destino (OFF)
        "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED",       # Plan 291 — detecta y reporta secretos (ON)
        "STACKY_AUTOCOMMIT_REDACT_ENABLED",            # Plan 291 — enmascara antes de commitear (OFF)
```
⚠️ **La categorización NO se deriva del prefijo de la key.** Si no se declara acá, `test_every_registry_flag_is_categorized` se pone rojo a propósito (nota en `harness_flags.py:615-616`).
✅ **Verificado por la crítica:** `"STACKY_INCIDENT_DEV_PR_ENABLED",          # Plan 177 — auto-PR del Dev Resolutor` está en `harness_flags.py:511`, y la categoría que lo contiene arranca en `:464` y es efectivamente `"capacidades_optin"` (etiqueta visible: **"Capacidades opt-in"**, `CategorySpec` en `:103`).

**(2) `Stacky Agents/backend/services/harness_flags.py` — `FLAG_REGISTRY`**
Agregar al final de la tupla, **después** del bloque `# ── Plan 289 —` y **antes** del `)` de cierre:

```python
    # ── Plan 291 — el commit del agente crea la rama que necesita ─────────────
    FlagSpec(
        key="STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED",
        # SIN default= A PROPOSITO (regla dura): una flag default OFF NO declara
        # default=False, porque `default_is_known(spec)` es literalmente
        # `spec.default is not None` (harness_flags.py:7299) y eso la metería en el
        # conjunto que test_default_known_only_for_curated exige que sea EXACTAMENTE
        # _CURATED_DEFAULTS_ON. El OFF vive SOLO en config.py.
        #
        # Nace OFF por EXCEPCION (B): es lo único de este plan que hace que Stacky
        # ESCRIBA en un sistema real del operador — con esto encendido, GitLab CREA
        # una rama en el repositorio del operador. Mismo precedente que
        # STACKY_MEETINGS_PUBLISH_ENABLED (plan 283) y
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED: ver y diagnosticar va ON,
        # escribir de verdad va OFF.
        #
        # SIN requires= A PROPOSITO: STACKY_GITLAB_ENABLED NO está en FLAG_REGISTRY
        # (rompería R1 de validate_requires_graph) y STACKY_INCIDENT_DEV_PR_ENABLED
        # ya tiene requires propio (rompería R4, profundidad máxima 1). Ver plan 291
        # sección 3.5.
        type="bool",
        label="Crear la rama del fix cuando no existe (GitLab)",
        description=(
            "Plan 291 — Cuando Stacky va a commitear en una rama de GitLab que "
            "todavía no existe, le pide a GitLab que la cree a partir de la rama "
            "principal del repositorio. Nace APAGADA porque es lo único que hace "
            "que Stacky escriba de verdad en el GitLab de la empresa. Con OFF, ese "
            "commit no se intenta y Stacky avisa con un mensaje claro cuál es la "
            "rama que falta. Azure DevOps ya crea la rama desde siempre; esto "
            "empareja GitLab. Requiere que GitLab esté habilitado. IMPORTANTE: "
            "aplica a TODO commit de Stacky a GitLab, no solo al arreglo de una "
            "incidencia — también al armado de pipelines, que usa nombres de rama "
            "propios. Ver plan 291 sección 3.6."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED",
        type="bool",
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        # Nace ON: SOLO LEE. No cambia un byte de lo que se commitea; agrega una
        # advertencia a la descripción del MR. No cae en (A) ni en (B).
        default=True,
        label="Avisar si el arreglo del agente trae algo que parece un secreto",
        description=(
            "Plan 291 — Antes de subir un archivo que escribió el agente, Stacky "
            "lo revisa buscando claves de acceso conocidas (Amazon, GitHub, GitLab, "
            "Slack) y bloques de clave privada. Si encuentra algo, NO toca el "
            "archivo: lo sube igual y agrega una advertencia con la lista de "
            "archivos sospechosos en la descripción de la propuesta de cambio, "
            "para que vos decidas antes de integrarla. Nace ENCENDIDA porque solo "
            "mira y avisa."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_AUTOCOMMIT_REDACT_ENABLED",
        # SIN default= A PROPOSITO: misma regla dura que la de start_branch.
        #
        # Nace OFF por EXCEPCION (B). El v1 de este plan la ponía ON y estaba MAL:
        # enmascarar reemplaza texto DENTRO del archivo que se sube al repositorio
        # real del operador — y el camino de Azure DevOps ya está vivo hoy, así que
        # habría cambiado los bytes escritos en el ADO de la empresa sin que nadie
        # lo decidiera. Además, medido: aplicar el saneador de diffs completo a
        # codigo fuente rompe codigo legitimo (`password = cfg.get(...)` ->
        # `password = ***REDACTED***`). Por eso acá se usa SOLO el subconjunto de
        # patrones de alta confianza (plan 291 F5), nunca redact_secrets entero.
        type="bool",
        label="Tapar el secreto dentro del archivo antes de subirlo",
        description=(
            "Plan 291 — Va de la mano de la opción de aviso. Con esta ENCENDIDA, "
            "Stacky ya no se limita a avisar: reemplaza el valor sospechoso por una "
            "marca dentro del archivo antes de subirlo, y lo aclara en la propuesta "
            "de cambio. Nace APAGADA porque modifica el contenido que se guarda en "
            "el repositorio de la empresa, y esa es una decisión tuya. Con OFF, el "
            "archivo se sube tal cual lo escribió el agente y solo recibís el aviso."
        ),
        group="global",
        env_only=False,
    ),
```

**(3) `Stacky Agents/backend/config.py` — los defaults EFECTIVOS**
⚠️ **El default efectivo es este, no el de la `FlagSpec`.** Sin atributo acá, el `getattr` del consumidor cae siempre al default hardcodeado y el panel del operador no apaga nada. Agregar **inmediatamente antes de la línea `config = Config()`** (hoy la última del archivo), dentro de la clase:

```python
    # ── Plan 291 — El commit del agente crea la rama que necesita ─────────────
    # Nace OFF por EXCEPCION (B): encenderla hace que GitLab CREE una rama en el
    # repositorio real del operador. Ninguna otra cosa de este plan escribe.
    STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED: bool = os.getenv(
        "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", "false"
    ).strip().lower() in ("1", "true", "yes")

    # Nace ON: SOLO LEE y reporta. No cambia ni un byte de lo que se commitea.
    STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED: bool = os.getenv(
        "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")

    # Nace OFF por EXCEPCION (B): enmascarar CAMBIA el contenido del archivo que se
    # escribe en el repositorio real del operador (y el camino ADO ya está vivo).
    STACKY_AUTOCOMMIT_REDACT_ENABLED: bool = os.getenv(
        "STACKY_AUTOCOMMIT_REDACT_ENABLED", "false"
    ).strip().lower() in ("1", "true", "yes")
```

✅ **Verificado por la crítica:** `config = Config()` es literalmente **la última línea del archivo** (`config.py:2714`), y `test_registry_all_non_env_only_keys_exist_in_config` (`tests/test_harness_flags.py:30`) exige que **toda** key con `env_only=False` exista como atributo de `Config`. Sin este paso (3), F3 sale rojo.
✅ **Y NO rompe `test_flags_env_read_meta.py`:** ese meta-test escanea **solo** `backend/api/` y `backend/services/` (`_SCAN_DIRS = ("api", "services")`, `tests/test_flags_env_read_meta.py:17`). `config.py` no entra en su corpus. Los consumidores de F4/F5 leen por `getattr(config.config, ...)`, que es el patrón correcto.

**(4) `Stacky Agents/backend/services/harness_flags_help.py` — `PLAIN_HELP` (línea 25)**
⚠️ **`PLAIN_HELP` NO se deriva de `description`.** Es un diccionario aparte y hay que escribirlo a mano. Agregar dos entradas con el dataclass `PlainHelp(what=, on_effect=, off_effect=, example=)`:

```python
    # ── Plan 291 — el commit del agente crea la rama que necesita ──────────
    "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED": PlainHelp(
        what="Deja que Stacky cree en GitLab la rama nueva donde va a dejar el arreglo que preparó el agente.",
        on_effect="Si la activás: cuando el agente termina un arreglo, Stacky crea la rama en GitLab, sube los archivos y abre la propuesta de cambio. Vos seguís siendo quien la aprueba y la integra.",
        off_effect="Si la apagás: Stacky no crea ninguna rama en GitLab y te avisa en el ticket cuál era la rama que faltaba, sin tocar nada de tu repositorio.",
        example="Como pedirle al archivo que abra una carpeta nueva antes de guardar el borrador, en vez de que el guardado falle porque la carpeta no estaba.",
    ),
    "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED": PlainHelp(
        what="Revisa los archivos que escribió el agente buscando claves de acceso conocidas o bloques de clave privada.",
        on_effect="Si la activás: los archivos se suben igual, pero la propuesta de cambio te lista arriba cuáles traen algo que parece una clave, para que lo mires antes de integrarla.",
        off_effect="Si la apagás: nadie revisa nada y la propuesta de cambio no te avisa si quedó una clave adentro de algún archivo.",
        example="Como el aviso del corrector antes de mandar el mail: te marca lo dudoso y vos decidís.",
    ),
    "STACKY_AUTOCOMMIT_REDACT_ENABLED": PlainHelp(
        what="Además de avisarte, reemplaza el valor sospechoso por una marca dentro del archivo antes de subirlo.",
        on_effect="Si la activás: el valor que parecía una clave se reemplaza por una marca dentro del archivo que se guarda en el repositorio de la empresa, y queda anotado en la propuesta de cambio.",
        off_effect="Si la apagás: el archivo se sube tal cual lo escribió el agente y solo recibís el aviso, sin que nadie le cambie el contenido.",
        example="Como pasar un marcador negro por un dato de una fotocopia antes de archivarla: protege, pero el original ya no vuelve.",
    ),
```

⚠️ **`tests/test_harness_flags_help.py` está ROJO DE FÁBRICA (4 failed / 4 passed).** Dos de sus fallos son `test_plain_help_on_off_start_with_si` y `test_plain_help_avoids_jargon_denylist`. El criterio de esta fase es **delta cero: sigue en `4 failed, 4 passed`**, no "verde".

🔴 **Y acá hay una trampa que el v1 no vio (hallazgo C8): un criterio de conteo sobre un archivo YA ROJO no discrimina.** Si las tres entradas nuevas violaran el denylist o el `"Si "`, esos dos tests **seguirían fallando igual** y el conteo seguiría siendo `4 failed, 4 passed`. El propio v1 escribía *"si pasa a 5 failed, la entrada está mal escrita"* — **eso no puede pasar**: un test que ya falla no falla más fuerte.

**Por eso la validación de las entradas nuevas se hace en el test PROPIO de este plan (F3.6 y F3.7), asertando sobre las tres keys concretas.** El denylist real, leído de `tests/test_harness_flags_help.py:17-20`, es:

```
"MCP", "TF-IDF", "LLM", "stdin", "stdout", "endpoint", "frontmatter",
"prompt", "token", "regex", "backend", "frontend", "gate", "hook", "runtime"
```

…comparado **por palabra completa, case-insensitive y con plural opcional** (`\btokens?\b`), más `\b[A-Z]+_[A-Z0-9_]+\b` (nada de keys en mayúsculas) y `\bF\d` (nada de "F1", "F2"). Los textos de arriba están escritos contra esa lista: por eso dicen **"clave de acceso"** y nunca la palabra prohibida que empieza con t. También respetan los topes de `test_plain_help_fields_non_empty_and_bounded`: `what` ≤ 200, `on_effect`/`off_effect` ≤ 240, `example` ≤ 300.

**(5) `tests/test_harness_flags.py::_CURATED_DEFAULTS_ON` (línea 467)**
Agregar **SOLO** `"STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED"` (es la única de las tres que declara `default=True`). **NO** agregar las otras dos: no declaran `default=`, así que `default_is_known()` es `False` para ellas y meterlas en el set haría fallar `test_default_known_only_for_curated` por "faltante".
✅ **Ese mismo set lo consumen DOS tests, no uno** — `test_declared_default_true_set` (`:1176`) y `test_default_known_only_for_curated` (`:1187`), ambos iterando `_CURATED_DEFAULTS_ON`. Con el paso (5) hecho, los dos quedan verdes; sin él, los dos rojos. No hay un tercer lugar que tocar.

**(6) `tests/test_harness_flags_requires.py::_REQUIRES_MAP_FROZEN` (línea 120)**
**NO SE TOCA.** Ninguna de las **tres** flags declara `requires=` (§3.5). Verificado leyendo el test: solo entran al mapa las specs con `requires` truthy.

**(7) `tests/test_flag_wiring.py::test_every_non_reserved_flag_is_wired`**
**No requiere edición**, pero **impone un orden**: el corpus que escanea son todos los `.py` de `backend/` **excepto** `tests/`, `services/harness_flags.py` y `services/harness_flags_help.py`, más los `.ts/.tsx` de `frontend/src` fuera de `__tests__` (`tests/test_flag_wiring.py:29-51`).
👉 **Consecuencia dura: `config.py` SÍ cuenta como consumo** — nota explícita en `tests/test_flag_wiring.py:**36-37**` (el v1 decía `:37-38`; drift de una línea, corregido): *"NOTA: harness_profiles.py y config.py SÍ cuentan (baseline de la auditoría 2026-07-02; endurecerlo es fuera de scope, sección 6)"*. Así que con el paso (3) hecho, este test pasa desde F3. Aun así, F4 y F5 agregan el consumidor **lógico** real, que es lo que le da sentido.
**NO** marcar las flags como `reserved=True`: tienen consumidor dentro de este mismo plan.

**(8) `Stacky Agents/deployment/harness_defaults.env`**
**No se regenera.** Medido el 2026-08-02: ese archivo **no contiene** `STACKY_TRACKER_CONTEXT_ENABLED` (la flag del plan 289), o sea que ya es **parcial por diseño** y ningún test exige que esté completo. Tocarlo es fuera de scope.

**Tests PRIMERO.** Mismo archivo `tests/test_plan291_start_branch.py`:

| id | Caso | Aserción |
|---|---|---|
| F3.1 | **las tres** keys están en `FLAG_REGISTRY` | `_REGISTRY_INDEX[k]` no es `None` y `.type == "bool"` para las tres |
| F3.2 | start_branch **nace OFF** en el default efectivo | `getattr(config.config, "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED") is False` (con el entorno limpio de esa env var) |
| F3.3 | scan **nace ON** y redact **nace OFF** | `getattr(config.config, "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED") is True` **y** `getattr(config.config, "STACKY_AUTOCOMMIT_REDACT_ENABLED") is False`. ⚠️ **Este es el guardián del bloqueante C1: si alguien vuelve a poner el enmascarado en ON, este test se pone rojo.** |
| F3.4 | las **dos OFF** no declaran default; la **ON** sí | `.default is None` y `default_is_known(spec) is False` para start_branch y redact; `.default is True` y `default_is_known(spec) is True` para scan |
| F3.5 | **ninguna declara `requires`** | `spec.requires is None` para las tres, **y** `validate_requires_graph() == []` |
| F3.6 | las tres tienen entrada en `PLAIN_HELP` con el formato exigido | `PLAIN_HELP[k]` existe para las tres; `on_effect` **y** `off_effect` empiezan con `"Si "` (sin tilde); los 4 campos no vacíos y dentro de los topes 200/240/240/300 |
| **F3.7** | **las entradas nuevas no violan el denylist de jerga** | para las tres keys, ninguno de los 4 campos matchea `\b<term>s?\b` (case-insensitive) para ningún `term` de `JARGON_DENYLIST` importado **del propio** `tests/test_harness_flags_help.py`, ni `\b[A-Z]+_[A-Z0-9_]+\b`, ni `\bF\d`. ⚠️ **Este test existe porque el archivo que lo vigilaría de verdad ya está rojo y su conteo no discrimina (C8).** |

**Cómo se comprueba el ROJO:** los 7 fallan hoy con `KeyError` / `AssertionError` porque las keys no existen en ningún registro.

**Comando:** el de la convención de §4, sobre `tests/test_plan291_start_branch.py`.

**Criterio BINARIO de F3 — los seis comandos, con su número exacto:**
```
tests/test_plan291_start_branch.py      →  18 passed          (7 de F1 + 4 de F2 + 7 de F3)
tests/test_harness_flags.py             →  59 passed          (delta cero)
tests/test_harness_flags_requires.py    →   9 passed          (delta cero)
tests/test_flag_wiring.py               →   5 passed          (delta cero)
tests/test_harness_flags_help.py        →   4 failed, 4 passed (DELTA CERO sobre el rojo de fábrica)
tests/test_flags_env_read_meta.py       →   1 failed, 1 passed (DELTA CERO sobre el rojo de fábrica)
```
> **Aritmética explícita del archivo `test_plan291_start_branch.py`, para que nadie tenga que sumar de memoria:** F1 aporta **7** (F1.1-F1.7), F2 aporta **4** (F2.1-F2.4), F3 aporta **7** (F3.1-F3.7) ⇒ **18 passed al cerrar F3**. F4 agrega **7** (F4.1-F4.7) ⇒ **25 passed al cerrar F4**, que es el número del DoD.

**Flags:** las **tres** que se crean. **Defaults:** start_branch **OFF**, scan **ON**, redact **OFF**.
**Impacto por runtime:** ninguno — el registro de flags es compartido por los 3. **Fallback:** n/a.
**Trabajo del operador:** ninguno todavía (las flags aparecen en el panel; la de start_branch aparece apagada).

---

### F4 — `start_branch` en el body, detrás de la flag

**Objetivo:** que el **primer** POST a `/repository/commits` sobre una rama inexistente lleve `start_branch`, y que el **segundo no**.

**Archivo:** `Stacky Agents/backend/services/gitlab_provider.py`

**Símbolo EXACTO:** `GitLabTrackerProvider.commit_file` (hoy `:785`).

**Diff conceptual:**

```python
     def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
         from services.tracker_provider import TrackerApiError    # lazy import
         proj_path = self._client._project_path()
-        action, current = self._detect_commit_action(path, branch)
+        rama_existe = self.branch_exists(branch)                          # F1
+        action, current = self._detect_commit_action(
+            path, branch, rama_existe=rama_existe,                        # F2
+        )
         if action == "update" and current == content:
             return { ... "status": "unchanged" }                          # FIX C7 — SIN CAMBIOS
+
+        crear_rama = (action == _ACCION_RAMA_NUEVA)
+        if crear_rama:
+            action = "create"        # traducir el sentinela INTERNO a la acción de la API
+
+        cuerpo = {
+            "branch": branch,
+            "commit_message": message,
+            "actions": [{"action": action, "file_path": path, "content": content}],
+        }
+        if crear_rama:
+            from config import config as _cfg
+            if not bool(getattr(_cfg, "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", False)):
+                raise TrackerApiError(
+                    400,
+                    f"La rama '{branch}' no existe en GitLab y la creación automática de "
+                    f"ramas está apagada. Encendé "
+                    f"'Crear la rama del fix cuando no existe (GitLab)' en el panel de "
+                    f"opciones para que Stacky la cree, o creá la rama a mano.",
+                    kind="branch_missing",
+                )
+            base = self._default_branch_name()
+            if not base:
+                raise TrackerApiError(
+                    400,
+                    f"El repositorio de GitLab no tiene rama principal (¿está vacío?), "
+                    f"así que no hay desde dónde crear '{branch}'. Hacé el primer commit "
+                    f"del repositorio a mano y volvé a intentar.",
+                    kind="repo_empty",
+                )
+            cuerpo["start_branch"] = base
+
         body, _ = self._client._request(
-            "POST", f"/projects/{proj_path}/repository/commits", json_body={...},
+            "POST", f"/projects/{proj_path}/repository/commits", json_body=cuerpo,
         )
         return { "sha": ..., "branch": branch, "path": path,
                  "web_url": body.get("web_url", ""), "status": action }
```

> **Firma confirmada abriendo el archivo, no asumida:** `GitLabClient._request` está declarada en `services/gitlab_client.py:265-274` como
> `_request(self, method, path, *, params=None, json_body=None, files=None, _retry=0) -> tuple[object, dict]`
> — devuelve **`(body, headers)`** y **ya lanza `TrackerApiError(status, msg, kind=...)`** ante cualquier no-2xx. **PROHIBIDO comparar el segundo valor de retorno con un status** (fue el defecto C1 del plan 73).
> `TrackerApiError.__init__` está en `services/tracker_provider.py:48-52`: `(status: int, message: str, *, kind: str = "unknown")` — **`message` es POSICIONAL**, y `kind` es keyword-only.

**Casos borde — la tabla completa:**

| # | Caso | Comportamiento |
|---|---|---|
| 1 | **Primer commit**, rama no existe, flag **ON** | `branch_exists` → `False`; body lleva `start_branch=<default_branch real>`; `action="create"` |
| 2 | **Segundo commit** sobre la misma rama (ya creada por el primero) | `branch_exists` → `True`; **body NO lleva `start_branch`**; `action` sale del GET de archivos |
| 3 | Rama **ya existe** de antes | igual que hoy, sin `start_branch` |
| 4 | Rama no existe, flag **OFF** | `TrackerApiError(400, kind="branch_missing")` con mensaje accionable. **Cero POST. Cero escritura.** |
| 5 | Rama default llamada `master` / `develop` | `start_branch="master"` / `"develop"` — se **lee** de `/projects/:id`, no se adivina `"main"` |
| 6 | **Repo vacío** sin rama default | `TrackerApiError(400, kind="repo_empty")`. Cero POST |
| 7 | Contenido idéntico al actual (rama existente) | `status="unchanged"` **sin POST** — el corto de FIX C7 se preserva intacto |
| 8 | `branch_exists` devuelve 403 | propaga desde F1; `commit_file` no lo traga |

⚠️ **Por qué el caso 2 importa:** mandar `start_branch` en el segundo commit contra una rama que ya existe puede hacer que GitLab rechace la operación o cree un commit huérfano. **El `start_branch` no es idempotente: se manda una sola vez.**

#### F4.a — 🔴 OBLIGATORIO: F4 ROMPE `tests/test_plan73_repo_writer.py`, y hay que arreglarlo acá

> **CORRECCIÓN DE LA v1 (bloqueante C2).** El v1 repetía en F1, F2, F4 y en el DoD #14 que `tests/test_plan73_repo_writer.py` queda en **`6 passed` (delta cero)**. **Es falso, y es falso de forma determinista.**
>
> `commit_file` pasa a hacer **una llamada `_request` más** (la de `branch_exists`) **antes** que todo lo demás. Dos de los seis tests de ese archivo están escritos contra el número y el orden exactos de esas llamadas:
>
> **(1) `test_f4_commit_file_create` (`tests/test_plan73_repo_writer.py:50-62`)** — el doble usa una **lista** de `side_effect` de dos elementos:
> ```python
> mock_client._request.side_effect = [
>     TrackerApiError(404, "not found", kind="not_found"),          # ← GET del archivo
>     ({"id": "abc123", "web_url": "..."}, {}),                     # ← POST del commit
> ]
> ```
> Con F4, el **primer** elemento lo consume `branch_exists`, que ve el 404 y devuelve `False` ⇒ `rama_existe=False` ⇒ `_ACCION_RAMA_NUEVA` ⇒ con la flag OFF (que es el default en tests) `commit_file` **lanza `TrackerApiError(kind="branch_missing")`**. El test muere.
>
> **(2) `test_f4_c7_idempotence_unchanged` (`:75-89`)** — `side_effect` de **un** elemento, y la última línea es literalmente:
> ```python
> assert mock_client._request.call_count == 1
> ```
> Con F4 son **2** llamadas, y además la lista se agota ⇒ `StopIteration` antes de llegar al assert.
>
> **(3) `test_f4_c1_tracker_api_error_propagated` (`:65-72`)** sobrevive por casualidad (su `side_effect` es una excepción única que se aplica a toda llamada, y `branch_exists` propaga el 403 igual). **Se deja como está y se documenta que sobrevive por qué razón**, para que nadie lo "arregle" de más.
>
> **Cambio EXACTO en `tests/test_plan73_repo_writer.py` — mínimo, dos tests, sin tocar los otros cuatro:**
>
> ```python
> # test_f4_commit_file_create — la rama YA EXISTE en este escenario (es lo que el
> # test siempre quiso probar: create de ARCHIVO, no de rama). Plan 291 F4.
> mock_client._request.side_effect = [
>     ({"name": "main"}, {}),                                  # ← NUEVO: GET branch_exists → existe
>     TrackerApiError(404, "not found", kind="not_found"),     # GET del archivo → no existe
>     ({"id": "abc123", "web_url": "https://gitlab.com/commit/abc"}, {}),
> ]
> ```
>
> ```python
> # test_f4_c7_idempotence_unchanged — idem: la rama existe.
> mock_client._request.side_effect = [
>     ({"name": "main"}, {}),                                  # ← NUEVO: GET branch_exists
>     ({"content": encoded}, {}),                              # GET del archivo → mismo contenido
> ]
> ...
> assert mock_client._request.call_count == 2   # ← era 1: ahora hay un GET de rama previo
> ```
>
> **Esto NO es "silenciar un test ajeno".** Es lo contrario: el test estaba congelando un contrato (`commit_file` hace exactamente 1 GET) que este plan cambia **a propósito y de forma declarada** (§3.3, Riesgo R7). Se actualiza el contrato en el test, se deja el comentario que dice por qué, y **el assert de conteo se mantiene** — no se borra. Borrarlo sería el falso verde.
>
> **Y hay que agregar un test nuevo en ESE archivo**, porque si no, nada vigila que el GET extra siga siendo exactamente uno:
>
> | id | Caso | Aserción |
> |---|---|---|
> | **F4.a.1** | `commit_file` sobre rama existente con contenido nuevo | `mock_client._request.call_count == 3` y la **primera** llamada es un `GET` a `/repository/branches/` |
>
> **Criterio de F4.a:** `tests/test_plan73_repo_writer.py` → **`7 passed`** (6 actualizados + 1 nuevo). **NO `6 passed`.** Ese cambio de número va escrito en el commit de F4 con el rojo previo pegado.

**Tests PRIMERO — con un doble del cliente CON ESTADO (no un `MagicMock` ingenuo).**

> ⚠️ **Este es el punto donde el test se puede volver un falso verde.** Un `MagicMock` que devuelva 404 siempre haría que el segundo commit **también** mandara `start_branch` y el test pasaría igual. El doble tiene que **modelar que la rama existe después del primer POST exitoso**.

```python
class ClienteFalso:
    """Doble del cliente GitLab CON ESTADO. Cero red.
    Modela: la rama NO existe hasta que un POST a /repository/commits la crea."""
    def __init__(self, ramas=(), archivos=None, default_branch="main"):
        self.ramas = set(ramas)
        self.archivos = dict(archivos or {})       # (rama, path) -> contenido
        self.default_branch = default_branch
        self.posts = []                            # [(path_url, json_body)] — LO QUE SE ASERTA
    def _project_path(self):
        return "grp%2Fproj"
    def _request(self, method, path, *, params=None, json_body=None, files=None, _retry=0):
        from services.tracker_provider import TrackerApiError
        if method == "GET" and "/repository/branches/" in path:
            rama = urllib.parse.unquote(path.rsplit("/", 1)[1])
            if rama in self.ramas:
                return {"name": rama}, {}
            raise TrackerApiError(404, "branch not found", kind="not_found")
        if method == "GET" and path.endswith(f"/projects/{self._project_path()}"):
            return {"default_branch": self.default_branch}, {}
        if method == "GET" and "/repository/files/" in path:
            ...  # 404 si no está; si está, {"content": base64(contenido)}
        if method == "POST" and path.endswith("/repository/commits"):
            self.posts.append((path, json_body))
            self.ramas.add(json_body["branch"])      # ← EL PUNTO: la rama pasa a EXISTIR
            for a in json_body["actions"]:
                self.archivos[(json_body["branch"], a["file_path"])] = a["content"]
            return {"id": "deadbeef", "web_url": "http://x/commit/deadbeef"}, {}
        raise AssertionError(f"llamada inesperada: {method} {path}")
```

Casos:

| id | Caso | Aserción — **sobre el consumidor final: `cliente.posts`** |
|---|---|---|
| **F4.1** | flag **ON**, rama no existe, se llama `commit_file` **dos veces** con paths distintos | `len(cliente.posts) == 2`; **`"start_branch" in cliente.posts[0][1]`** y **`"start_branch" not in cliente.posts[1][1]`** |
| **F4.2** | flag ON, `default_branch="develop"` | `cliente.posts[0][1]["start_branch"] == "develop"` — nunca `"main"` |
| **F4.3** | flag **OFF**, rama no existe | `pytest.raises(TrackerApiError)` con `.kind == "branch_missing"`, **y `cliente.posts == []`** (cero escritura) |
| **F4.4** | flag ON, rama existe de antes (`ramas={"stacky/x"}`) | `"start_branch" not in cliente.posts[0][1]` |
| **F4.5** | flag ON, repo vacío (`default_branch=""`) | `TrackerApiError` con `.kind == "repo_empty"` **y `cliente.posts == []`** |
| **F4.6** | flag ON, rama existe y el contenido es idéntico | devuelve `status == "unchanged"` **y `cliente.posts == []`** (FIX C7 preservado) |
| **F4.7** | **Radio de alcance declarado (§3.6), probado.** Reemplaza al F4.7 del v1 | flag ON, `commit_file(path, content, "feature/pipeline-x", msg)` con rama inexistente ⇒ `cliente.posts[0][1]["start_branch"]` existe y `["branch"] == "feature/pipeline-x"`. **El test NO afirma que eso esté mal: afirma que PASA**, para que quede escrito en el arnés que la flag alcanza a los tres consumidores de `commit_file`, no solo al auto-PR |

> 🔴 **Por qué el F4.7 del v1 desapareció (bloqueante C3).** Era `cliente.posts[i][1]["branch"].startswith("stacky/")` sobre POSTs generados por llamadas que **el propio test hacía con `branch="stacky/x"`**. Un gate que asserta su propio argumento **no puede ponerse rojo nunca**: si mañana alguien cambia `_BRANCH_PREFIX` a `"tmp/"`, el test sigue verde y K2 sigue "cumplido". Molde (c) de gate muerto — y encima el DoD #10 lo citaba como prueba del invariante.
>
> **El gate REAL de K2 se mudó a F6.8**, donde hay un doble del writer y se puede ejecutar `maybe_open_pr_for_incident_dev` para leer **la rama que construyó el producto**. Mudarlo no es cosmético: es lo que respeta la regla de que **ningún criterio de Fk puede depender de algo que se construye en Fk+1** — en F4 todavía no existe el doble del writer, así que un K2 real no era escribible acá.

**Cómo se comprueba el ROJO (esto es lo que hay que hacer, en este orden):**

1. Escribir el archivo de tests **antes** de tocar `commit_file`.
2. Correr el comando. **F4.1 falla** con `AssertionError: 'start_branch' not in {...}` — porque hoy `commit_file` nunca lo agrega. **F4.3 falla** con `Failed: DID NOT RAISE TrackerApiError`. **F4.5 falla** igual.
3. Pegar ese output en el commit. **Un rojo que no se leyó no cuenta.**

⚠️ Con el código de HOY, el `ClienteFalso` recibiría un `GET /repository/files/...` que devuelve 404, `_detect_commit_action` devolvería `("create", None)` y el POST se haría **sin `start_branch`** — o sea, el doble reproduce exactamente el bug. **Ese es el rojo por la razón correcta.**

**Cómo se manipula la flag en el test:** con `monkeypatch.setattr(config.config, "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", True/False, raising=False)`. **No** se toca `os.environ`: `config = Config()` se instancia en el import y `os.getenv` ya corrió.

**Comando:** el de la convención de §4.

**Criterio BINARIO:**
```
tests/test_plan291_start_branch.py       →  25 passed  (7 F1 + 4 F2 + 7 F3 + 7 F4)
tests/test_plan73_repo_writer.py         →   7 passed  🔴 NO delta cero — F4.a lo actualiza a propósito
tests/test_gitlab_provider.py            →  26 passed  (delta cero)
tests/test_plan70_gitlab_provider_complete.py →  19 passed  (delta cero)
tests/test_plan73_generator_endpoint.py  →  10 passed  (delta cero — parchea el WRITER, no el cliente HTTP, así que F4 no lo alcanza; re-medir igual, archivo sucio por sesión paralela)
```
> ✅ **`tests/test_plan73_repo_writer.py` ya está registrado en LOS DOS ratchets y NO está en el allowlist** (medido: `.sh` 1 hit, `.ps1` 1 hit, allowlist 0 hits). Agregarle el test F4.a.1 **no requiere registro nuevo** ni sacar nada del allowlist.

**Flag:** `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`. **Default: OFF, excepción (B).**
**Impacto por runtime:** ninguno — `gitlab_provider` es agnóstico de runtime. **Fallback:** con la flag OFF, comportamiento de hoy salvo el mensaje de error, que mejora.
**Trabajo del operador:** ninguno. La perilla queda disponible, apagada.

---

### F5 — El auto-PR AVISA si el arreglo trae un secreto (y solo lo tapa si el operador lo pide)

**Objetivo:** que el operador **vea, antes de integrar**, en qué archivos del arreglo hay algo que parece un secreto — y que **enmascararlo sea una decisión suya**, no un default.

> 🔴 **Esta fase se rediseñó por completo respecto del v1 (bloqueante C1).** El v1 pasaba **todo** el contenido por `redact_secrets` con una flag **ON por default**. Medido: eso **rompe código fuente legítimo** y **cambia los bytes que Stacky ya escribe hoy en el Azure DevOps del operador**. La evidencia ejecutada está en §3.2.1. La v2 parte la fase en dos mitades con la doctrina que el propio plan enuncia en §3.2: **detectar y reportar va ON; mutar el archivo va OFF citando (B)**.

**Archivo:** `Stacky Agents/backend/services/incident_dev_autocommit.py`

**Símbolos EXACTOS:**
- **Se agrega** la constante de módulo `_PATRONES_ALTA_CONFIANZA` (ver abajo).
- **Se agrega** el helper de módulo `_inspeccionar(texto: str) -> tuple[str, bool]`.
- **Se modifica** el bucle `for rel in changed:` (hoy `:83-89`) dentro de `maybe_open_pr_for_incident_dev`.
- **Se modifica** la firma de `_build_pr_body` (hoy `:208`) agregando **un keyword con default**.
- **Se modifica** la llamada a `mark_intent(... status="opened" ...)` (hoy `:103-104`).

**Diff conceptual:**

```python
+# Plan 291 F5 — SOLO patrones que no pueden confundirse con codigo fuente.
+# DELIBERADAMENTE NO se usa services.pr_review_sanitize.redact_secrets entero:
+# ese modulo sanea DIFFS QUE VAN A UN MODELO (docstring :1-3), donde perder
+# informacion es gratis. Aca el texto se ESCRIBE en el repositorio del operador.
+# Medido 2026-08-02: sus patrones `password|secret|api_key\s*[=:]` (:16-18)
+# convierten `password = cfg.get("db_password")` en `password = ***REDACTED***`,
+# o sea rompen codigo valido; y su patron de email (:28) tapa la atribucion de
+# una cabecera de licencia. Los seis de abajo no tienen ese modo de fallo.
+_PATRONES_ALTA_CONFIANZA = (
+    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                  # AWS access key id
+    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),              # GitHub PAT
+    re.compile(r"\bglpat-[A-Za-z0-9\-_]{20,}\b"),         # GitLab PAT
+    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),     # Slack
+    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._\-]+"),
+    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
+)
+_MARCA = "***REDACTED***"
+
+
+def _inspeccionar(texto):
+    """(texto_a_commitear, hubo_hallazgo).
+
+    DOS flags, dos mitades, y el orden importa:
+      - STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED (ON):  solo MIRA. Devuelve el texto
+        INTACTO y True si encontro algo. El archivo se commitea byte-identico.
+      - STACKY_AUTOCOMMIT_REDACT_ENABLED (OFF):      ademas REEMPLAZA. Solo con
+        esta encendida el texto devuelto difiere del original.
+    Con las dos apagadas: (texto, False) — camino byte-identico a hoy.
+    """
+    from config import config as _cfg
+    if not bool(getattr(_cfg, "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED", True)):
+        return texto, False
+    hallazgo = any(p.search(texto) for p in _PATRONES_ALTA_CONFIANZA)
+    if not hallazgo:
+        return texto, False
+    if not bool(getattr(_cfg, "STACKY_AUTOCOMMIT_REDACT_ENABLED", False)):
+        return texto, True          # ← avisa, NO toca el archivo
+    saneado = texto
+    for p in _PATRONES_ALTA_CONFIANZA:
+        saneado = p.sub(lambda m: (m.group(1) + _MARCA) if p.groups >= 1 else _MARCA, saneado)
+    return saneado, True

     committed: list[str] = []
     skipped_binary: list[str] = []
+    sospechosos: list[str] = []
     commit_msg = f"fix(incidencia #{...}): resolución del Dev Resolutor + tests"
     for rel in changed:
         content = _read_text_or_none(repo_root, rel)
         if content is None:
             skipped_binary.append(rel)
             continue
-        writer.commit_file(rel, content, branch, commit_msg)   # crea la rama en el 1er call
+        content, hubo_hallazgo = _inspeccionar(content)
+        if hubo_hallazgo:
+            sospechosos.append(rel)
+        # Azure DevOps crea la rama solo (ado_provider.py:183-190). GitLab la crea
+        # solo desde el plan 291 y SOLO con STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED
+        # encendida; con la flag apagada esto lanza TrackerApiError(kind="branch_missing")
+        # y el except de abajo lo comenta en la Issue. El comentario viejo
+        # ("crea la rama en el 1er call") era falso para GitLab.
+        writer.commit_file(rel, content, branch, commit_msg)
         committed.append(rel)
...
-    title, description = _build_pr_body(ado_id, classify, deleted, origin)
+    # (se mueve DESPUÉS del bucle: la lista de sospechosos no existe hasta que
+    #  el bucle terminó. Hoy _build_pr_body se llama ANTES, en :73.)
+    title, description = _build_pr_body(ado_id, classify, deleted, origin,
+                                        sospechosos=sospechosos)
...
     incident_dev_pr.mark_intent(execution_id, status="opened", pr_id=pr.get("id"),
                                 pr_url=pr_url, branch=branch,
-                                files_committed=committed, origin=origin)
+                                files_committed=committed, origin=origin,
+                                secret_scan_files=sospechosos)
```

✅ **`mark_intent` acepta el kwarg nuevo sin tocarla.** Verificado abriendo la firma: `def mark_intent(execution_id: int, **fields) -> None` (`services/incident_dev_pr.py:223`), que hace `cur.update(fields)`. **No hay supuesto de capacidad acá.**

Y en `_build_pr_body`:
```python
-def _build_pr_body(ado_id, classify, deleted, origin):
+def _build_pr_body(ado_id, classify, deleted, origin, *, sospechosos=None):
     ...
+    if sospechosos:
+        lines += ["", "**⚠️ Revisá estos archivos antes de integrar**",
+                  "Parecen traer una clave de acceso o una clave privada. "
+                  "Se subieron TAL CUAL los escribió el agente salvo que hayas "
+                  "encendido el tapado automático.",
+                  *[f"- `{p}`" for p in sospechosos]]
     return title, "\n".join(lines)
```

> ⚠️ **Reordenamiento obligatorio y fácil de olvidar:** hoy `_build_pr_body` se llama en la **línea 73**, **antes** del bucle de commits (`:83`). La lista `sospechosos` **no existe todavía** en ese punto. **Hay que mover la llamada a después del bucle**, justo antes de `target = _default_branch_for(...)` (`:99`). Si no se mueve, `sospechosos` siempre llega vacío y el gate F5.3 sale verde con el defecto vivo.
> ✅ **Verificado que el reordenamiento es seguro:** `classify` se calcula en `:71` y `origin` en `:64`, los dos **antes** del bucle; y entre el bucle y `:99` solo hay el corte `if not committed: … return` (`:91-95`), que no usa `title`/`description`. Mover la llamada a `:99` no rompe ninguna dependencia.
>
> ⚠️ **`import re` hay que agregarlo al encabezado del módulo.** Hoy `incident_dev_autocommit.py:16-18` importa solo `logging`, `pathlib.Path` y `urllib.parse.urlparse`. Sin ese import, `_PATRONES_ALTA_CONFIANZA` explota en tiempo de import y **el post-hook deja de registrarse entero**.

**Casos borde:**

| # | Caso | Comportamiento |
|---|---|---|
| 1 | Archivo con `ghp_xxxxxxxxxxxxxxxxxxxxx`, **defaults de fábrica** (scan ON, redact OFF) | **se sube TAL CUAL**; el archivo entra en `sospechosos` y aparece en la descripción del MR |
| 2 | Mismo archivo, redact **ON** (el operador la encendió) | se reemplaza por `***REDACTED***`; entra en `sospechosos` igual |
| 3 | Archivo sin nada sensible | pasa **idéntico**; NO entra en `sospechosos` |
| 4 | **Código legítimo: `password = cfg.get("db_password")`, `secret = None`, `api_key = os.getenv("X")`** | **NO se toca, ni siquiera con redact ON, ni entra en `sospechosos`.** Es el caso que hundía al v1: `redact_secrets` lo destruía. `_PATRONES_ALTA_CONFIANZA` no lo mira |
| 5 | **Email legítimo en una cabecera (`# autor: juan@empresa.com`)** | **NO se toca.** El v1 lo enmascaraba (`pr_review_sanitize.py:28`) y lo llamaba "esperado"; la v2 lo saca del conjunto: tapar un mail de atribución no protege nada y rompe la autoría |
| 6 | Las dos flags **OFF** | camino byte-idéntico a hoy y `sospechosos` vacío |
| 7 | Archivo binario / no-utf8 | ya lo filtra `_read_text_or_none` **antes**; nunca llega a `_inspeccionar` |
| 8 | Más de `_MAX_FILES` (60) archivos | **el tope existente se queda tal cual** (`:23` y `:57`); corta antes del bucle |
| 9 | Clave privada partida en varias líneas | el patrón `BEGIN…END PRIVATE KEY` es multilínea (`[\s\S]*?`); se detecta entera |

**Tests PRIMERO.** Archivo NUEVO: `Stacky Agents/backend/tests/test_plan291_autocommit_redaccion.py`

> Se crea archivo aparte del de F1-F4 porque el doble es distinto (acá se falsea el `writer` y el `mrp`, no el cliente HTTP), y porque así cada archivo sigue pasando **en aislamiento**, que es lo que el ratchet exige.

> ⚠️ **Los seis puntos de patch que este archivo necesita, enumerados (bloqueante C5).** El v1 decía *"con un `writer` falso y un `mrp` falso"* y nada más. `maybe_open_pr_for_incident_dev` toca disco, base y red por seis lados distintos; sin patchearlos **el test escribe en los datos vivos del operador o se cuelga contra git**. Fixture obligatorio, idéntico para F5, F6 y F7:
>
> ```python
> @pytest.fixture
> def entorno(monkeypatch, tmp_path):
>     # (0) el intent store escribe en runtime_paths.data_dir() => backend/data.
>     #     SIN esto, el test contamina la carpeta VIVA del operador.
>     monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path / "data"))
>     from services import incident_dev_pr, incident_dev_autocommit as ida
>     # (1) el intent
>     monkeypatch.setattr(incident_dev_pr, "get_intent",
>                         lambda eid: {"open_pr": True, "repo_root": str(tmp_path), "baseline": {}})
>     monkeypatch.setattr(incident_dev_pr, "mark_intent", lambda eid, **kw: marcas.append(kw))
>     # (2) el snapshot de git (si no, corre `git status` de verdad)
>     monkeypatch.setattr(incident_dev_pr, "snapshot_worktree", lambda root: {"entries": {}})
>     monkeypatch.setattr(incident_dev_pr, "compute_changed_files",
>                         lambda b, c: {"added_or_modified": ["src/a.py"], "deleted": []})
>     monkeypatch.setattr(incident_dev_pr, "remote_origin_url", lambda root: ORIGIN)
>     # (3) el Ticket en la base (si no, abre session_scope contra la DB)
>     monkeypatch.setattr(ida, "_ticket_ado_id_and_project", lambda tid: (99, "RIPLEY"))
>     # (4) el contenido del archivo
>     monkeypatch.setattr(ida, "_read_text_or_none", lambda root, rel: CONTENIDO)
>     # (5) el writer y el proveedor de MR — OJO: se importan LAZY dentro de la
>     #     función (`:75-76`), así que hay que parchear el MÓDULO de origen.
>     import services.repo_writer, services.merge_request_provider
>     monkeypatch.setattr(services.repo_writer, "get_repo_writer", lambda p: writer)
>     monkeypatch.setattr(services.merge_request_provider, "get_merge_request_provider", lambda p: mrp)
>     # (6) el comentario en la Issue (si no, sale a la red del tracker)
>     monkeypatch.setattr(ida, "_comment_issue_safe", lambda *a, **k: comentarios.append(a))
> ```
>
> **`_provider_host` NO hace falta patchearlo en F5** (con `origin=None`, `_worktree_maps_to_wrong_repo` devuelve `False` en la primera línea). **Sí en F6.**

| id | Caso | Aserción — **sobre el consumidor final** |
|---|---|---|
| F5.1 | `_inspeccionar("clave: ghp_" + "a"*22)` con defaults (scan ON, redact OFF) | devuelve el texto **IDÉNTICO** y el bool `True` |
| F5.2 | **end-to-end con defaults de fábrica**, archivo con `ghp_…` | **el `content` que recibió `writer.commit_file`** (`writer.llamadas[0][1]`) es **byte-idéntico** al original. ⚠️ **La aserción va sobre el argumento que llegó a `commit_file`**, no sobre el retorno de `_inspeccionar` |
| F5.3 | mismo caso | **el `description` que recibió `mrp.create_merge_request`** contiene `src/a.py`. ⚠️ **Sobre el kwarg real de `create_merge_request` (`:100-101` lo llama con keywords), no sobre el retorno de `_build_pr_body`** |
| F5.4 | end-to-end con **redact ON** (`monkeypatch.setattr(config.config, ...)`), mismo archivo | `writer.llamadas[0][1]` **no** contiene el `ghp_…`, contiene `***REDACTED***`, **y** `src/a.py` sigue en el `description` |
| **F5.5** | 🔴 **EL GATE DEL BLOQUEANTE C1.** `redact ON` y contenido `'password = cfg.get("db_password")\nsecret = None\napi_key = os.getenv("X")\n# autor: juan@empresa.com\n'` | `writer.llamadas[0][1]` **es exactamente igual al original** y `sospechosos` está **vacío**. **Si alguien vuelve a meter `redact_secrets` entero, este test se pone rojo.** Este es el escenario que existe después de la última fase y que puede romper el gate |
| F5.6 | archivo limpio (`"def f():\n    return 1\n"`), defaults | `writer.llamadas[0][1] == "def f():\n    return 1\n"` **exactamente**, y el `description` **no** contiene la sección de revisión |
| F5.7 | **scan OFF y redact OFF** | camino byte-idéntico y `description` sin la sección — el apagado total es el de hoy |
| F5.8 | **el intent recibe la lista** | la llamada a `mark_intent` con `status="opened"` trae `secret_scan_files == ["src/a.py"]` |

**Cómo se comprueba el ROJO:** F5.3, F5.4 y F5.8 fallan hoy con `AssertionError` — nadie inspecciona, el `description` no menciona nada y el intent no lleva la lista. **F5.2, F5.6 y F5.7 pasan hoy a propósito: guardan la PRESENCIA del contenido intacto**, que es exactamente lo que el v1 iba a romper. **F5.5 también pasa hoy** — y ese es el punto: es el centinela que impide reintroducir el defecto.

**Comando:** el de la convención de §4, sobre `tests/test_plan291_autocommit_redaccion.py`.

**Registro en los ratchets — MISMO COMMIT que crea el archivo.** Idéntico al procedimiento de F1 (`.sh` sin comillas / `.ps1` con comillas y coma, insertando en el medio para no tocar la cola sin coma).

**Criterio BINARIO:**
```
tests/test_plan291_autocommit_redaccion.py →   8 passed
tests/test_incident_dev_autocommit.py      →  11 passed  (DELTA CERO — el keyword con default y el reordenamiento NO deben romper ninguno)
```
> ✅ **`tests/test_incident_dev_autocommit.py` está en los DOS ratchets y no en el allowlist** (medido). Si hiciera falta agregarle un test, no requiere registro nuevo.

**Flags:** `STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED` (**ON** — solo lee) y `STACKY_AUTOCOMMIT_REDACT_ENABLED` (**OFF, excepción (B)** — cambia bytes escritos en un sistema real).
**Impacto por runtime:** ninguno — corre en el post-hook agnóstico. **Fallback:** las dos OFF = comportamiento de hoy, byte por byte.
**Trabajo del operador:** ninguno.

---

### F6 — El guardia de "repo equivocado", ejercitado contra un `origin` de GitLab

**Objetivo:** probar que `_worktree_maps_to_wrong_repo` **detiene** un commit cuando el working tree local apunta a un GitLab distinto del que el tracker tiene configurado.

> **Por qué esta fase existe:** `_worktree_maps_to_wrong_repo` está construido (`services/incident_dev_autocommit.py:198-205`) y llamado (`:63-69`), pero **nunca se ejercitó contra un `origin` de GitLab**. Es el guardia contra el peor fallo posible de este eje: **commitear en el repositorio equivocado**. Antes de encender la creación de ramas, este guardia tiene que estar probado.

**Archivos:** ninguno de producto **si el guardia funciona**. Solo tests.
👉 Si algún caso de abajo falla, **se corrige `_host_of` o `_provider_host` en `services/incident_dev_autocommit.py`** (símbolos `:167-179` y `:182-195`) con el cambio mínimo, y se documenta en el commit qué se corrigió y por qué.

**Contrato real, leído (no asumido):**
- `_host_of(url)` (`:167`) soporta `http(s)://host/...` **y** SSH scp-like `git@host:org/repo`. Devuelve el host en minúsculas o `None`.
- `_provider_host(project)` (`:182`) resuelve el host base del tracker probando, **en este orden**: `client._base_proj`, `prov.base_url`, `client.base_url`. Cualquier excepción → `None`.
- `_worktree_maps_to_wrong_repo(origin, project)` (`:198`) devuelve `True` **SOLO** cuando ambos hosts se resolvieron y son distintos. **Ante cualquier duda → `False`** (nunca degrada por debajo de v1).

**Tests PRIMERO.** Archivo NUEVO: `Stacky Agents/backend/tests/test_plan291_guardia_repo.py`

| id | Caso | Aserción |
|---|---|---|
| F6.1 | `origin = "https://srvcgit01.imsolutions.local/grp/proj.git"`, `_provider_host` parcheado a `"srvcgit01.imsolutions.local"` | `_worktree_maps_to_wrong_repo(...) is False` — mismo host, se permite |
| F6.2 | `origin = "https://gitlab.com/otro/repo.git"`, `_provider_host` → `"srvcgit01.imsolutions.local"` | `is True` — **hosts distintos, se detiene** |
| F6.3 | `origin = "git@srvcgit01.imsolutions.local:grp/proj.git"` (SSH), provider host igual | `is False` — la forma SSH se parsea bien |
| F6.4 | `origin = "git@gitlab.com:otro/repo.git"` (SSH), provider host `srvcgit01...` | `is True` |
| F6.5 | mayúsculas: `origin = "https://SRVCGIT01.ImSolutions.LOCAL/g/p.git"` | `is False` — la comparación es case-insensitive |
| F6.6 | `_provider_host` devuelve `None` (no se pudo resolver) | `is False` — ante la duda, **no** bloquea |
| **F6.7** | **INTEGRACIÓN — el que de verdad importa.** `maybe_open_pr_for_incident_dev` completa con `origin` de otro GitLab | **`writer.llamadas == []`** (cero `commit_file`), **`mrp.llamadas == []`** (cero MR), y `mark_intent` recibió `status="skipped"` con un `error` que contiene el origin |
| **F6.8** | 🔴 **K2, el gate REAL (viene de F4.7 del v1, bloqueante C3).** `maybe_open_pr_for_incident_dev` con `ticket_id=12`, `execution_id=34` y `origin` correcto | **`writer.llamadas[0][2] == "stacky/incidencia-12-exec-34"`** — la rama la construyó **el producto** (`_BRANCH_PREFIX` + ids), no el test. **Mitad de contraste obligatoria:** con `monkeypatch.setattr(ida, "_BRANCH_PREFIX", "suelto/")` la misma aserción **debe fallar**, y eso se prueba con `pytest.raises(AssertionError)` alrededor del helper. **Sin esa segunda mitad el gate no demuestra que puede ponerse rojo** |

> **Fixture:** F6 reusa **tal cual** el `entorno` de F5 (los seis puntos de patch), cambiando solo `ORIGIN` y agregando `monkeypatch.setattr(ida, "_provider_host", lambda p: "srvcgit01.imsolutions.local")`. **Se declara acá dónde vive:** el fixture se escribe **duplicado en cada archivo de test**, NO en un `conftest.py` compartido ni importándolo del otro archivo — porque el ratchet corre cada archivo **en aislamiento** y una dependencia cruzada entre archivos de test rompe esa garantía. Son ~20 líneas; la duplicación es deliberada y va comentada.

⚠️ **F6.7 es el gate real de esta fase.** F6.1-F6.6 prueban la función; **F6.7 prueba que la función DETIENE el commit**. Un gate que solo mira el booleano de `_worktree_maps_to_wrong_repo` sería un test estático sobre un defecto de ejecución: tiene que **ejecutar** el post-hook y verificar que el writer **no fue llamado**.

**Cómo se comprueba el ROJO:** F6.1-F6.7 **deberían pasar hoy** — el guardia existe. Ese es el punto: **esta fase es una red de seguridad que se instala antes de encender la escritura**. Si alguno falla, se encontró un bug vivo y **se arregla acá**. Para probar que el test no es vacuo (no es un `assert` de ausencia que pasa por accidente), **F6.7 se corre dos veces**: una con el origin ajeno (esperando `writer.llamadas == []`) y otra con el origin correcto (esperando `len(writer.llamadas) == 1`). **La segunda mitad guarda la PRESENCIA** y es lo que impide que el test pase porque el writer nunca se llama por otro motivo.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_guardia_repo.py" -q
```

**Registro en los ratchets:** mismo procedimiento de F1, en el mismo commit.

**Criterio BINARIO:** `10 passed` (F6.1-F6.6 = 6, F6.7 con sus dos mitades como dos casos = 2, F6.8 con sus dos mitades = 2). Delta cero en `tests/test_incident_dev_autocommit.py` → `11 passed`.

**Flag:** ninguna — es cobertura de un guardia existente. **Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F7 — Paridad de los 3 runtimes, probada ejecutando

**Objetivo:** demostrar —ejecutando, no leyendo— que este eje entra por una costura que los 3 runtimes comparten, y por lo tanto no hay ni puede haber divergencia por runtime.

**Archivos:** ninguno de producto. Solo tests y documentación.

**Evidencia estructural MEDIDA el 2026-08-02.** El post-hook está registrado en `app.py:1036` sobre `ticket_status.register_post_hook`, y `ticket_status.on_execution_end` (`services/ticket_status.py:293`) dispara `_POST_HOOKS` (`:364`, recorridos en `:396`). Llamadas a `on_execution_end` por runtime:

| Runtime | Archivo | Call sites | Líneas |
|---|---|---|---|
| **Codex CLI** | `services/codex_cli_runner.py` | **8** | 369, 843, 877, 970, 1136, 1188, 1244, 1918 |
| **Claude Code CLI** | `services/claude_code_cli_runner.py` | **8** | 712, 1766, 1895, 2029, 2098, 2155, 3099, 3133 |
| **In-proc / GitHub Copilot** | `agent_runner.py` | **4** | 848, 1161, 1187, 1226 |

> ✅ **Los 20 call sites RE-VERIFICADOS por la crítica, uno por uno: 8/8, 8/8 y 4/4, en las líneas exactas.** Dato fino que el v1 no decía y conviene saber: en `agent_runner.py` las cuatro llamadas van por el **alias `_ts.on_execution_end(`**, no por `ticket_status.on_execution_end(`. Un censo por la cadena larga daría **cero** para ese runtime y haría creer que Copilot no llama al chokepoint. **Censar por símbolo, no por la cadena completa.**

**Conclusión de paridad, escrita explícitamente:** este plan **no agrega ni una sola rama condicional por runtime**. `gitlab_provider` no sabe qué runtime corrió, y `incident_dev_autocommit` corre después del chokepoint compartido. **No hace falta fallback por runtime**, porque no hay comportamiento por runtime. Si algún día un runtime dejara de llamar `on_execution_end`, el auto-PR **ya estaría roto hoy** para ese runtime, independientemente de este plan — sería un defecto del plan 177, no de este.

**Test PRIMERO.** Se agrega a `Stacky Agents/backend/tests/test_plan291_guardia_repo.py` (archivo ya registrado en los ratchets por F6, así que **no hay registro nuevo**):

| id | Caso | Aserción |
|---|---|---|
| **F7.1** | `maybe_open_pr_for_incident_dev` está en `ticket_status._POST_HOOKS` después de importar y registrar | la función aparece en la lista. ⚠️ **Este caso es casi vacuo por construcción** (asserta que el fixture hizo lo que hizo). Se conserva solo como diagnóstico: si F7.2 falla, F7.1 dice si el problema es el registro o el disparo. **El gate real es F7.2** |
| **F7.2** | **EJECUTANDO**: se llama `ticket_status.on_execution_end(...)` con `agent_type="incident_dev"`, `final_status="completed"` y un intent con `open_pr=True`, con el writer y el mrp falseados | **`writer.llamadas` tiene 1 entrada** — o sea, el hook **se disparó desde el chokepoint compartido**, no desde una llamada directa al hook |
| **F7.3** | mismo, pero con `agent_type="incident"` (otro agente) | `writer.llamadas == []` — el hook filtra bien y no se dispara de más |

⚠️ **F7.2 es el gate que no puede ser estático.** Un test que solo grepeara los 3 runners buscando `"on_execution_end"` sería un test estático sobre un defecto de ejecución (molde de gate muerto (b)). **Tiene que llamar a `on_execution_end` de verdad** y comprobar que el efecto llegó al final de la cadena.
⚠️ **F7.3 guarda la PRESENCIA del filtro** para que F7.2 no pase por accidente.

**Cómo se comprueba el ROJO:** F7.2 falla si el hook no está registrado o si el chokepoint no lo dispara. Con `app.py` sin importar, `_POST_HOOKS` está vacío, así que el test **debe** registrar el hook explícitamente (`incident_dev_autocommit.register(ticket_status.register_post_hook)`) en un fixture y limpiarlo al final, **sin** llamar `create_app()`.

> ⚠️ **PROHIBIDO llamar `create_app()` en estos tests.** Con `pytest` en `sys.modules` y `STACKY_TEST_MODE=1` **igual arranca los watchers** y hace efectos reales.
> ✅ **`on_execution_end` es keyword-only** — firma real, abierta: `on_execution_end(*, ticket_id, execution_id, final_status, agent_type=None, error=None, reason_override=None, ...)` (`services/ticket_status.py:293-300`). F7.2 **debe** llamarla con keywords o da `TypeError`.
> ✅ **`register_post_hook` existe en `:377` y hace `_POST_HOOKS.append(fn)` en `:383`.** El fixture tiene que **vaciar `_POST_HOOKS` al terminar** (`monkeypatch.setattr(ticket_status, "_POST_HOOKS", [])` antes de registrar es lo más limpio: monkeypatch lo restaura solo).

**Comando:** el de la convención de §4, sobre `tests/test_plan291_guardia_repo.py`.

**Criterio BINARIO:** `13 passed` (10 de F6 + 3 de F7).

**Flag:** ninguna. **Impacto por runtime:** los 3, idéntico, probado por F7.2. **Fallback:** no aplica (no hay rama por runtime).
**Trabajo del operador:** ninguno.

---

### F8 — La activación queda como decisión explícita y documentada del operador

**Objetivo:** dejar por escrito, en la documentación del sistema, **qué tiene que hacer el operador exactamente** para encender esto y **qué tiene que mirar** para saber si funcionó — y que nadie confunda "el plan está implementado" con "el ciclo funciona".

**Archivos:**
- `Stacky Agents/docs/sistema/` — el archivo que documenta el Dev Resolutor / auto-PR. **Localizarlo con** `grep -rln "auto-PR\|Dev Resolutor" "Stacky Agents/docs/sistema/"` y editar el que salga. Si no sale ninguno, crear `Stacky Agents/docs/sistema/auto_pr_dev_resolutor.md`.
- ⚠️ **`docs/sistema/` es la fuente única.** No duplicar en otro lado.
- ⚠️ **Un `.md` nuevo en `docs/` contamina el DocTree y el corpus RAG.** Si se crea archivo nuevo, va en `docs/sistema/`, que es la ubicación canónica ya indexada.

**Contenido obligatorio de la sección (literal, para que el operador lo pueda seguir sin ayuda):**

#### 8.1 — Pasos EXACTOS para activar

> 🔴 **Corrección de la v1 (bloqueante C6): los dos primeros pasos del v1 mandaban al operador a la pantalla equivocada.** Decía *"categoría **Capacidades opcionales**"* — la categoría se llama **"Capacidades opt-in"** (`harness_flags.py:103`) — y decía que `STACKY_GITLAB_ENABLED` se confirma en ese mismo panel, cuando **esa clave NO está en `FLAG_REGISTRY`** (verificado ejecutando: `NO REGISTRADA`) y por lo tanto **no aparece ahí**. El plan 290 F5 la llevó a la interfaz, sí, pero a **otra pantalla**: el componente `GitlabEngineSwitch` montado en **`frontend/src/pages/DiagnosticsPage.tsx:334`**. El único humo real de este plan arrancaba con dos instrucciones falsas.

1. **Primero, el motor de GitLab.** Andá a **Diagnósticos** y confirmá que el interruptor **"Sistema de tickets GitLab"** (`STACKY_GITLAB_ENABLED`) está **encendido**. Sin eso no hay camino a GitLab: `services/tracker_provider.py:133-136` lanza `TrackerConfigError` y no se lista ni un ticket. *(No está en el panel de opciones: vive en Diagnósticos, `DiagnosticsPage.tsx:334`.)*
2. **Después, el panel de opciones.** Abrilo y andá a la categoría **"Capacidades opt-in"**.
3. Confirmá que **"Abrir PR al resolver incidencias"** (`STACKY_INCIDENT_DEV_PR_ENABLED`) está **encendido** (viene encendido de fábrica), y también su master **`STACKY_INCIDENT_DEV_RESOLVER_ENABLED`**, que también nace encendido.
4. Encendé **"Crear la rama del fix cuando no existe (GitLab)"** (`STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`). **Este es el paso que autoriza a Stacky a escribir en tu GitLab.**
   ⚠️ **Y alcanza a más que a las incidencias:** también habilita a que el armado de pipelines cree su propia rama (`feature/pipeline-…`). Ver §3.6.
5. *(Opcional)* Si querés que además **tape** lo que parezca una clave dentro de los archivos, encendé **"Tapar el secreto dentro del archivo antes de subirlo"** (`STACKY_AUTOCOMMIT_REDACT_ENABLED`). **Nace apagada a propósito**: el aviso viene encendido, el reemplazo del contenido lo decidís vos.
6. El cambio **aplica en caliente**: el endpoint hace `setattr(config, key, val)` sobre la instancia viva (`api/harness_flags.py:153`, dentro del bucle de hot-apply de `:150` y solo si `env_only` es falso) además de persistirlo. **No hace falta reiniciar** (la `FlagSpec` no declara `restart_required`).

#### 8.2 — El humo, paso a paso, y qué mirar

> ⚠️ **Este humo es TRABAJO DEL OPERADOR y está FUERA DEL ALCANCE de este plan.** Ninguna fase lo automatiza, ninguna fase lo verifica. Requiere credenciales reales y toca el GitLab de la empresa.

1. Elegí un ticket del proyecto **RIPLEY** (el único con `issue_tracker.type = "gitlab"`).
2. Tocá **"Resolver con agente"** dejando el checkbox **"Abrir PR"** marcado (viene premarcado).
3. Esperá a que la ejecución termine en `completed`.
4. **Qué mirar, en orden:**

| Dónde | Qué tiene que aparecer | Si NO aparece |
|---|---|---|
| El comentario en la Issue de GitLab | `🚀 PR abierto automáticamente con el fix y los tests: <url>` | Si dice `⚠️ No se pudo abrir el PR automático: ...`, **el mensaje trae la causa**. Si dice que la rama no existe y la creación está apagada → volvé al paso 4 de §8.1 |
| GitLab → Repositorio → Ramas | una rama llamada `stacky/incidencia-<ticket>-exec-<ejecución>` | Sin rama, el commit no llegó |
| GitLab → Merge Requests | un MR en estado **`opened`** desde esa rama hacia la rama principal | — |
| La descripción del MR | las listas de **Cambios de código**, **Tests incluidos**, el **Origen del working tree**, y —si hubo— la sección **⚠️ Revisá estos archivos antes de integrar** | Si aparece esa sección, **los archivos se subieron TAL CUAL** salvo que hayas encendido el tapado del paso 5. Miralos antes de integrar |
| El MR | **NO** debe estar mergeado ni aprobado | Si lo está, es un bug grave: reportalo. `approve`/`merge` viven detrás de tu botón (`api/pr_review.py:387-411`) y `merge` además exige la casilla de confirmación fuerte |

5. **Recién después de ver ese MR `opened`, K1 pasa a ser medible.**

#### 8.3 — Cómo apagarlo

Apagá **"Crear la rama del fix cuando no existe (GitLab)"**. Vuelve el comportamiento previo al plan: Stacky no crea ninguna rama en GitLab y avisa en la Issue cuál era la rama que faltaba. **Las ramas y MRs ya creados NO se borran** — eso es decisión tuya, a mano.

**Criterio BINARIO de F8** — el archivo destino se **fija en el commit de F8**, no queda como `<archivo>`. Los greps se corren sobre **toda la carpeta**, que es lo único binario si el nombre todavía no está decidido:
```
grep -rc "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED" "Stacky Agents/docs/sistema/" | grep -v ":0$" | wc -l  →  >= 1
grep -rc "STACKY_AUTOCOMMIT_REDACT_ENABLED"          "Stacky Agents/docs/sistema/" | grep -v ":0$" | wc -l  →  >= 1
grep -rc "NO MEDIBLE"                                "Stacky Agents/docs/sistema/" | grep -v ":0$" | wc -l  →  >= 1
grep -rc "stacky/incidencia-"                        "Stacky Agents/docs/sistema/" | grep -v ":0$" | wc -l  →  >= 1
grep -rc "DiagnosticsPage"                           "Stacky Agents/docs/sistema/" | grep -v ":0$" | wc -l  →  >= 1
```
> **La quinta línea existe por el bloqueante C6:** la documentación tiene que decir **dónde** está el interruptor de GitLab, porque no está donde el operador buscaría.

Y en este mismo documento, la sección §1.1 dice literalmente `NO MEDIBLE`.

**Flag:** ninguna. **Impacto por runtime:** ninguno.
**Trabajo del operador:** **TODO §8.1 y §8.2.** Es la única fase con trabajo del operador, y es a propósito: es la decisión que este plan **no** le saca.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación en este plan |
|---|---|---|---|---|
| **R1** | **Commitear en el repositorio equivocado.** El working tree local apunta a otro remoto y Stacky sube el fix ahí. **Es el peor fallo posible de este eje.** | Baja | **Crítico** | `_worktree_maps_to_wrong_repo` ya corta (`:63-69`), y **F6 lo ejercita por primera vez contra un `origin` de GitLab**, incluida la forma SSH y el caso de integración F6.7 que verifica que el writer **no se llama**. |
| **R2** | ~~`redact_secrets` enmascara EMAILS~~ → **REEMPLAZADO. El riesgo real era mucho peor y el v1 no lo veía: `redact_secrets` DESTRUYE código fuente legítimo** (`password = cfg.get(...)` → `password = ***REDACTED***`, medido), y el v1 lo activaba **ON por default sobre el camino de ADO que ya está vivo**. | ~~Alta~~ **Cierta** | ~~Medio~~ **Crítico** | **Rediseñado en F5 (§3.2.1).** (i) No se usa `redact_secrets`: se usa `_PATRONES_ALTA_CONFIANZA`, seis patrones que no pueden confundirse con código; (ii) el email **sale** del conjunto; (iii) la mitad que **muta** el archivo nace **OFF** citando (B), y solo la que **avisa** nace ON; (iv) **F5.5 es el centinela**: pasa código con `password`/`secret`/`api_key`/email por el camino con redact ON y exige que salga **byte-idéntico**. |
| **R2.b** | **Falsos negativos del detector.** Al acotar los patrones, un secreto con formato raro (contraseña en texto plano, clave de un proveedor no listado) **no se detecta ni se avisa**. | Media | Medio | **Se acepta explícitamente y se declara.** El detector es una **ayuda**, no una garantía; el MR sigue siendo una propuesta que el operador revisa (HITL). La alternativa —el detector agresivo del v1— tenía un modo de fallo peor: falsos positivos que **rompen el código commiteado**. Entre avisar de menos y romper el arreglo, se elige avisar de menos. |
| **R3** | **`start_branch` mandado dos veces.** GitLab podría rechazar el segundo commit o crear un commit huérfano. | Media si el doble es ingenuo | Alto | El doble de F4 **tiene estado**: la rama pasa a existir tras el primer POST. **F4.1 asserta explícitamente que el segundo POST NO lo lleva.** Un `MagicMock` plano habría dado falso verde. |
| **R4** | **Adivinar `"main"`** cuando el repo usa `master` o `develop`: se crearía la rama desde una base equivocada. | Media | Alto | `_default_branch_name()` **lee** `/projects/:id → default_branch`. F4.2 lo prueba con `"develop"`. Nunca hay literal `"main"` en el camino de `start_branch`. |
| **R5** | **Repo vacío** sin rama default: `start_branch=""` produciría un error críptico. | Baja | Bajo | `TrackerApiError(400, kind="repo_empty")` con mensaje accionable, **antes** del POST. F4.5. |
| **R6** | **Deuda ajena vecina:** `_default_branch_for` (`incident_dev_autocommit.py:157-164`) **importa de `api.devops_production`** — un servicio importando de `api/`, que viola el riel del repo — y hace `fallback DURO 'main'` ante cualquier excepción. Si el repo usa `master`, el MR podría apuntar a un `target_branch` inexistente. | Baja | Medio | **Fuera de scope, declarado.** Este plan **no agrega** ningún import de `api/` (por eso `_default_branch_name` vive en el provider). Se anota para un plan futuro. |
| **R7** | **Una llamada `GET` extra por cada `commit_file` de GitLab.** Afecta también a `api/pipeline_editor.py:285` y `api/pipeline_generator.py:122`. | Cierta | Bajo | Se declara explícitamente (§3.3). Es un `GET` a `/repository/branches/:branch`, no una lista paginada. A cambio, elimina un `GET` inútil de archivos cuando la rama no existe (F2.2), o sea que en el camino roto el neto es **cero llamadas extra**. |
| **R8** | **Sesión paralela VIVA** editando los mismos archivos. Al momento de escribir este plan hay **34 archivos sucios**, incluido `tests/test_plan73_generator_endpoint.py`, que este plan mide como baseline. | **Cierta** | Medio | Antes de cada commit: `git status --short`. Commitear **solo** las rutas propias con `git commit -- "<ruta>"`. **PROHIBIDO** `amend`, `reset`, `rebase`, `stash`, `checkout`. Si un baseline no coincide, **re-medir**, no culpar. |
| **R9** | **El ratchet es una trampa de COMMIT, no solo de edición.** Crear un test nuevo sin registrarlo en **ambos** scripts bloquea el commit. | Media | Bajo | F1, F5 y F6 registran su archivo **en el mismo commit que lo crea**. La trampa de la coma final del `.ps1` está documentada con el remedio (insertar en el medio). |
| **R10** | ~~Un test ajeno *podría* estar congelando el comportamiento viejo (Baja)~~ → **NO es un riesgo: es un HECHO MEDIDO.** `tests/test_plan73_repo_writer.py` tiene **dos** tests escritos contra el número y el orden exactos de llamadas a `_request` (`:54-59` con una lista de 2 y `:89` con `call_count == 1`). El GET de `branch_exists` los rompe a los dos. | ~~Baja~~ **Cierta** | Bajo | **F4.a lo resuelve de frente**: actualiza los dos tests con el comentario que dice por qué, **mantiene el assert de conteo** (no lo borra) y agrega F4.a.1 para vigilar que el GET extra siga siendo exactamente uno. El criterio de esa suite pasa de `6 passed` a **`7 passed`**, declarado. |
| **R12** | **El auto-PR con la flag OFF sigue escribiendo un comentario en la Issue de GitLab.** El camino de error (`incident_dev_autocommit.py:106-112`) llama a `_comment_issue_safe`, que hace `post_comment` contra el tracker real. | Cierta | Bajo | **Se declara en §3.7**, porque "cero escritura" a secas es falso. Es comportamiento **de hoy**, no nuevo: el 400 críptico también se comenta. Lo que este plan cambia es que el comentario pase a ser útil. Ninguna fase lo toca. |
| **R13** | **Los tests de este plan pueden escribir en los datos vivos del operador.** `incident_dev_pr.get_intent/record_intent` resuelven su carpeta con `runtime_paths.data_dir()`, que sin `STACKY_DATA_DIR` es **`backend/data`** (`runtime_paths.py:48-54`). | **Cierta si no se mitiga** | Alto | El fixture obligatorio de F5/F6/F7 hace `monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path / "data"))` **y** parchea `get_intent`/`mark_intent`. Además la convención de §4 fija `DATABASE_URL` a scratchpad. **Son tres capas, no una.** |
| **R14** | **El propio arnés emite un request HTTPS real** en `test_plan218_tracker_contract.py::[gitlab]`, y el guard de egress **no se instala** si `STACKY_TEST_MODE` no está en el entorno (`conftest.py:35`). | Cierta | Medio | La convención de §4 exporta `STACKY_TEST_MODE=1` en **todos** los comandos. El test ajeno queda como **acción para el operador** (§6), no se arregla acá: es deuda del plan 218. |
| **R11** | **El diagnóstico de §2 nunca se validó en vivo.** Puede que la instancia del operador se comporte distinto. | Media | Medio | Está declarado en §2.4 con esas palabras. **La única validación real es el humo de §8.2, que es del operador.** Ninguna fase pretende sustituirlo. |

---

## 6. Fuera de scope (explícito)

Nada de lo siguiente entra en este plan. Enumerarlo es parte del plan.

1. **🔴 ACTIVAR el post-hook o cambiar el default de `STACKY_INCIDENT_DEV_PR_ENABLED`.** Esa flag **ya está ON** (`config.py:1220-1221`) y **este plan no la toca**.
2. **🔴 Encender `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`.** Nace OFF y **se queda OFF al terminar el plan**. Encenderla es una decisión del operador, documentada en §8.1.
3. **🔴 Ejercitar el ciclo end-to-end contra GitLab.** Ninguna fase hace una sola llamada de red. Todo va contra dobles. El humo de §8.2 es del operador.
4. **🔴 Tocar el GitLab del operador** (`srvcgit01.imsolutions.local`) de cualquier forma.
5. **Mergear o aprobar nada.** `approve`/`merge` siguen exactamente donde están (`api/pr_review.py:387-411`), detrás del botón del operador y de la casilla `confirm_merge`. **Este plan no toca ese archivo.**
6. **Reescribir `create_merge_request`** (`gitlab_provider.py:819`). Ya es agnóstico y se reusa tal cual.
7. **Cambiar `_MAX_FILES = 60`** (`incident_dev_autocommit.py:23`) ni el tope `_MAX_TEXT_BYTES` (`:24`).
8. **Cambiar `_BRANCH_PREFIX`** (`:22`). La rama sigue siendo `stacky/incidencia-<ticket>-exec-<exec>`.
9. **Arreglar `_default_branch_for`** y su import de `api/` (Riesgo R6). Deuda ajena declarada.
10. **Agregar `tests/test_gitlab_provider.py` al ratchet `.ps1`** (hoy está solo en el `.sh`). Es una de las 64 divergencias conocidas; arreglarla movería el conteo del `.ps1`.
11. **Regenerar `deployment/harness_defaults.env`.** Es parcial por diseño (medido: no contiene la flag del plan 289).
12. **Frontend.** Este plan no toca ni un `.ts`/`.tsx`. Las flags `group="global"` de tipo `bool` se renderizan solas desde `read_current()` — verificado: la flag del plan 289 tiene **cero** referencias en `frontend/src/`.
13. **Los 5 rojos de fábrica del backend y los 5 ratchets rojos del frontend.** Deuda ajena; criterio delta cero.
14. **Borrar ramas o MRs** que el operador ya haya creado.
15. **Aislar `tests/test_plan218_tracker_contract.py::[gitlab]` de la red.** Deuda del plan 218. **Acción sugerida para el operador**, fuera de este plan: instalar el doble HTTP también en el escenario `create_item` o mover el guard de egress a `getaddrinfo` además de `connect`.
16. **Acotar `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` a un solo consumidor de `commit_file`.** Se decidió que no (§3.6), con las tres razones escritas.
17. **Detectar secretos con más patrones** que los seis de alta confianza. Riesgo R2.b, aceptado y declarado.

> ### 6.1 — Acciones que quedan para el operador (ninguna la hace este plan)
> 1. **El humo de §8.2 contra su GitLab.** Es la única validación end-to-end posible y es suya.
> 2. **Decidir si enciende `STACKY_AUTOCOMMIT_REDACT_ENABLED`.** Nace apagada. Con ella apagada recibe el aviso; con ella encendida, Stacky modifica el contenido de los archivos que sube.
> 3. **Decidir qué hacer con `test_plan218_tracker_contract[gitlab]`**, que emite un request real en cada corrida del arnés (punto 15).

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado exacto en este plan |
|---|---|
| **`start_branch`** | Campo del body de `POST /projects/:id/repository/commits` de la API v4 de GitLab. Nombre de la rama **base** desde la cual crear la rama destino si no existe. **Se manda una sola vez, en el primer commit.** |
| **`branch_exists`** | Método nuevo, de **solo lectura**, en `GitLabTrackerProvider`. `GET /repository/branches/:branch`; `True`/`False`/propaga. |
| **Alta confianza (patrón de)** | Expresión que **no puede confundirse con código fuente**: `AKIA…`, `ghp_…`, `glpat-…`, `xox…`, `Authorization: Bearer …`, bloque `BEGIN…END PRIVATE KEY`. Es el conjunto que usa F5. **`password=`, `secret=`, `api_key=` y el email NO son de alta confianza**: matchean código válido. |
| **Gate vacuo** | Test que no puede ponerse rojo porque asserta su propio input, o porque el escenario que lo rompería no existe. Tres moldes: (a) centinela sobre un símbolo que una fase posterior borra; (b) test estático sobre un defecto de ejecución; (c) `assert` de ausencia suelto. El F4.7 del v1 era el molde (c). |
| **`_ACCION_RAMA_NUEVA`** | Constante de módulo con valor `"create_new_branch"`. **Sentinela INTERNO**, no es una acción válida de la API de GitLab. `commit_file` lo traduce a `"create"`. |
| **Excepción (B)** | Regla de la casa: una flag nueva nace **OFF** si **escribe en un sistema real del operador**, destruye datos, o le saca una decisión. |
| **Rojo de fábrica** | Test que ya falla **antes** de tocar nada. Su criterio es **delta cero**, no "verde". |
| **Delta cero** | El conteo `N failed, M passed` de una suite es **idéntico** antes y después. |
| **Doble del cliente** | Objeto de test que reemplaza `GitLabClient` y **no hace red**. Acá tiene **estado**: la rama pasa a existir tras un POST exitoso. |
| **Chokepoint** | `ticket_status.on_execution_end` (`services/ticket_status.py:293`), el único punto que los 3 runtimes llaman al terminar. |
| **HITL** | Human-in-the-loop. Acá: el MR es una **propuesta**; aprobar y mergear son botones del operador. |

### 7.2 Orden de implementación (dependencias duras)

```
F0  medir baselines                 (sin dependencias)
 └─ F1  branch_exists + F1.b        ← necesita F0 para el criterio delta cero
     └─ F2  _detect_commit_action    ← usa el sentinela; independiente de F1 en código,
     │                                 pero F4 necesita las DOS
     └─ F3  registrar las 3 flags    ← puede ir en paralelo con F1/F2
         └─ F4  start_branch + F4.a  ← NECESITA F1 + F2 + F3 (las tres)
             └─ F5  detección/tapado ← necesita F3 (las dos flags de secretos)
                                       y DEFINE el fixture `entorno` de 6 patches
                 └─ F6  guardia de repo + K2  ← reusa (duplicado) el fixture de F5
                     └─ F7  paridad 3 runtimes  ← reusa los dobles de F6
                         └─ F8  documentación + activación del operador  ← última
```

> ⚠️ **Chequeo de la regla "ningún criterio de Fk depende de algo que se construye en Fk+1", hecho fase por fase:**
>
> | Fase | ¿Su criterio depende de una fase posterior? |
> |---|---|
> | F0 | No — solo transcribe números. |
> | F1 | No — `branch_exists`/`_default_branch_name` no tienen caller hasta F4, y `test_plan73_repo_writer` sigue en 6 hasta F4. |
> | F2 | No — el sentinela solo aparece si un caller pasa `rama_existe=False`, y no hay ninguno hasta F4. |
> | F3 | No — `test_flag_wiring` ya se satisface con `config.py` (paso 3), sin esperar a los consumidores lógicos de F4/F5. |
> | F4 | **Corregido en v2.** El F4.7 del v1 (K2) necesitaba el doble del writer, que recién existe en F5/F6 ⇒ **se mudó a F6.8**. Lo que quedó en F4 se prueba con el `ClienteFalso`, que F4 mismo define. |
> | F5 | No — define su propio fixture. |
> | F6 | No — el fixture se duplica, no se importa. |
> | F7 | No — se apoya en F6, que es anterior. |
> | F8 | No — solo documenta lo ya construido. |

**Regla de commits:** **un commit por fase**, mensaje `feat(plan-291): F<n> - <qué hace>`. Los archivos de test nuevos se registran en **ambos** ratchets **en el mismo commit que los crea**. Antes de cada commit: `git status --short`, y commitear **solo** las rutas propias con `git commit -- "<ruta1>" "<ruta2>"`.

### 7.3 Definition of Done

| # | Criterio | Comando / verificación |
|---|---|---|
| 1 | `branch_exists` y `_default_branch_name` existen, están probados, y `api/devops_production._default_branch` **delega** en el segundo | `pytest tests/test_plan291_start_branch.py -q` → **25 passed**; F1.6/F1.7 verdes |
| 2 | `_detect_commit_action` **no** devuelve `"create"` por un 404 de rama | caso F2.1 verde |
| 3 | El **primer** POST lleva `start_branch` y el **segundo no** | caso F4.1 verde, y su rojo previo pegado en el commit de F4 |
| 4 | Con la flag OFF, cero POST **al endpoint de commits** y error accionable | caso F4.3 verde (`cliente.posts == []`). ⚠️ **No es "cero escritura": el camino de error igual comenta en la Issue** (§3.7, R12) |
| 5 | La rama base se **lee**, no se adivina | caso F4.2 verde con `"develop"` |
| 6 | 🔴 **El contenido commiteado es byte-idéntico con los defaults de fábrica**, y **código legítimo con `password=`/`secret=`/`api_key=`/email NO se toca ni con el tapado encendido** | `pytest tests/test_plan291_autocommit_redaccion.py -q` → **8 passed**; **F5.5 verde** (el centinela del bloqueante C1); F5.2 asserta sobre el argumento real de `commit_file` |
| 7 | Los archivos sospechosos llegan a la descripción del MR **y** al intent | F5.3 sobre el kwarg real de `create_merge_request`; F5.8 sobre `mark_intent(secret_scan_files=…)` |
| 8 | El guardia de repo detiene el commit con un `origin` de GitLab ajeno | `pytest tests/test_plan291_guardia_repo.py -q` → **13 passed**; F6.7 con sus dos mitades |
| 9 | La paridad de los 3 runtimes está probada **ejecutando** | caso F7.2 verde |
| 10 | **Cero commits del auto-PR fuera de una rama `stacky/`** (K2, acotado en §1.2) | **caso F6.8 verde, con su mitad de contraste** (`_BRANCH_PREFIX` parcheado ⇒ el gate falla). El F4.7 del v1 **no vale**: asertaba su propio input |
| 11 | `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` sigue **OFF** al terminar, y `STACKY_AUTOCOMMIT_REDACT_ENABLED` **también** | `grep -c 'STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", "false"' config.py` → 1; `grep -c 'STACKY_AUTOCOMMIT_REDACT_ENABLED", "false"' config.py` → 1; **y F3.3 verde**, que es el gate ejecutable |
| 12 | Los dos ratchets tienen los 3 archivos nuevos | `grep -c "test_plan291" scripts/run_harness_tests.sh` → **3**; ídem en `.ps1` → **3**. Total esperado: `.sh` **831**, `.ps1` **767** |
| 13 | Ninguno de los 3 archivos nuevos está en el allowlist | `grep -c "plan291" tests/harness_ratchet_allowlist.txt` → **0** |
| 14 | **Delta cero en 7 de las 8 suites vecinas — y `test_plan73_repo_writer.py` pasa de 6 a 7 A PROPÓSITO** | los conteos de F0 se reproducen exactos **salvo** `test_plan73_repo_writer.py` → **7 passed** (F4.a). Cualquier otro movimiento es regresión |
| 15 | Los rojos de fábrica siguen igual | `test_harness_flags_help.py` → 4F/4P; `test_flags_env_read_meta.py` → 1F/1P; `test_plan218_coupling_ratchet.py` → 3F/7P; `test_plan218_capability_matrix.py` → 2F/8P; `test_plan218_tracker_contract.py` → 1F/9P |
| 16 | La documentación de activación existe **y dice dónde está el interruptor de GitLab** | los **5** `grep` de F8 dan ≥ 1 |
| 17 | **K1 se reporta como NO MEDIBLE**, con las palabras de §1.1 | revisión del resumen final |
| 18 | Cero llamadas de red en toda la implementación | **todos** los comandos corridos con `STACKY_TEST_MODE=1` — sin esa variable el guard de `conftest.py:35` **no se instala** — y con `DATABASE_URL` + `STACKY_DATA_DIR` a scratchpad. Ningún test nuevo importa `requests` sin doble |
| **19** | **Los tests del plan no dejaron rastro en los datos del operador** | `git status --short` no muestra nada bajo `backend/data/`; y `ls "Stacky Agents/backend/data/incident_dev_pr"` no ganó archivos nuevos |

**El plan está DONE cuando los 19 criterios se cumplen Y las dos flags de excepción (B) siguen apagadas.** Un plan 291 que termina con `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` encendida **no está done: está mal implementado.** Lo mismo vale para `STACKY_AUTOCOMMIT_REDACT_ENABLED`.

---

## 8. CHANGELOG v1 → v2

**Veredicto de la crítica sobre el v1: 🔴 RECHAZADO — 6 bloqueantes, 6 importantes, 3 menores.** Todos resueltos abajo. Método: se abrieron **34 archivos** y se **ejecutaron** el registry de flags, los 13 baselines, `redact_secrets` sobre código real y el test que sale a la red.

### Bloqueantes

| # | Defecto del v1 | Cómo se resolvió |
|---|---|---|
| **C1** | **F5 pasaba TODO el contenido por `redact_secrets` con la flag ON por default.** Medido: eso convierte `password = cfg.get("db_password")` en `password = ***REDACTED***`, o sea **rompe código válido**, y lo hace sobre el camino de **Azure DevOps que ya está vivo hoy**, sin que el operador decida nada. El v1 lo clasificaba como *"no abre camino nuevo; endurece uno existente"* y como kill-switch. | **F5 rediseñada (§3.2.1).** Se parte en **detectar (ON, no toca el archivo)** y **enmascarar (OFF, excepción (B))**, que es el riel que el propio plan enunciaba en §3.2 y no se aplicaba a sí mismo. No se usa `redact_secrets`: se usa `_PATRONES_ALTA_CONFIANZA` (6 patrones). El email sale del conjunto. **F5.5 es el centinela ejecutable** y F3.3 vigila el default. |
| **C2** | **Criterio insatisfacible.** F1, F2, F4 y DoD #14 exigían `tests/test_plan73_repo_writer.py` → `6 passed` delta cero. El GET de `branch_exists` **rompe dos de esos seis tests** de forma determinista (`:54-59` lista de `side_effect` de 2 elementos; `:89` `assert call_count == 1`). | **F4.a**, nueva: actualiza los dos tests con el diff exacto, **conserva** el assert de conteo (`== 2`), agrega F4.a.1 para vigilar que el GET extra sea uno solo, y el criterio pasa a **`7 passed`** declarado. DoD #14 reescrito. |
| **C3** | **Gate vacuo + invariante falso.** F4.7 "probaba" K2 asertando `branch.startswith("stacky/")` sobre ramas **que el propio test pasaba**; y K2 era falso porque `commit_file` tiene **tres** consumidores, uno de los cuales (`api/pipeline_generator.py:97`) arma ramas `feature/pipeline-…`. El v1 no nombraba ese radio en ningún lado. | **§1.2** acota K2 al auto-PR y publica la tabla de los tres consumidores. **§3.6** declara el radio real y por qué se elige no acotar la flag. El gate real se muda a **F6.8**, que ejecuta el producto y trae **mitad de contraste**. El F4.7 nuevo prueba —y documenta— que la flag también alcanza a `feature/pipeline-x`. La `description` de la flag lo dice en el texto que lee el operador. |
| **C4** | **DoD #18 prometía "cero red" apoyándose en un guard que los comandos del propio plan apagaban.** `conftest.py:35` desinstala el guard si `STACKY_TEST_MODE` no está en el entorno, y ningún comando del v1 la exportaba. | La convención de **§4** exporta `STACKY_TEST_MODE=1` y `DATABASE_URL` en **todos** los comandos, con la explicación y el límite del guard (engancha `connect`, no `getaddrinfo`). DoD #18 reescrito. R14 nuevo. |
| **C5** | **F6.7 y F7.2 eran inimplementables.** `maybe_open_pr_for_incident_dev` toca disco, base, git y red por **seis** lados; el v1 decía "con un writer falso y un mrp falso". Y `incident_dev_pr.get_intent` resuelve su carpeta con `runtime_paths.data_dir()` = **`backend/data`**, la carpeta viva del operador. | **Fixture `entorno` completo en F5**, con los 6 puntos de patch escritos, `STACKY_DATA_DIR` a `tmp_path`, y la nota de que los imports de `:75-76` son **lazy** (hay que parchear el módulo de origen). R13 nuevo. DoD #19 nuevo. |
| **C6** | **§8.1 mandaba al operador a la pantalla equivocada** en sus dos primeros pasos: la categoría se llama **"Capacidades opt-in"**, y `STACKY_GITLAB_ENABLED` **no está en el panel de flags** (no está en `FLAG_REGISTRY`) — el plan 290 la puso en `GitlabEngineSwitch`, montado en `DiagnosticsPage.tsx:334`. El único humo real del plan arrancaba con dos instrucciones falsas. | **§8.1 reescrito** con la pantalla correcta y el paso 5 nuevo (el tapado, opcional). **F8 gana un quinto grep** que exige que la documentación diga dónde está el interruptor. |

### Importantes

| # | Defecto | Resolución |
|---|---|---|
| **C7** | `_default_branch_name` **duplicaba** `api/devops_production._default_branch:48-51` (mismo GET, mismo campo), con contratos divergentes (`""` vs `"main"`) y las dos decidiendo la rama base **en el mismo flujo**. | **F1.b**: implementación única en el provider; `api/` **delega** (dirección permitida). F1.6/F1.7 guardan el fallback histórico. Cuatro suites nuevas a medir. |
| **C8** | **Criterios de conteo sobre archivos ROJOS que no discriminan.** El v1 decía *"si `test_harness_flags_help` pasa a 5 failed, la entrada está mal escrita"* — **no puede pasar**: un test que ya falla no falla más fuerte. Lo mismo con `test_flags_env_read_meta`. | **F3.6 ampliado y F3.7 nuevo**, asertando el formato **y** el denylist real sobre las tres keys concretas, importando `JARGON_DENYLIST` del propio test. Se transcribe el denylist verificado. |
| **C9** | *"Cero POST. Cero escritura."* es falso a nivel sistema: con la flag OFF el camino de error **igual comenta en la Issue de GitLab**. | **§3.7** publica la tabla de "afirmaciones tentadoras que son falsas". R12 nuevo. DoD #4 matizado. |
| **C10** | Anclajes desfasados: el patrón PII de email está en `pr_review_sanitize.py:**28**` (el v1 decía 29); la nota de que `config.py` cuenta como consumo está en `test_flag_wiring.py:**36-37**` (el v1 decía 37-38). | Corregidos in situ. **Los otros 101 anclajes del v1 se verificaron abriendo el archivo y están OK**, incluidas las cuatro correcciones de drift que el propio v1 ya traía (`config.py:1220-1221`, `:63-69`, `commit_file:785/798-807`, `pr_review.py:387-411`). |
| **C11** | El orden de fases decía *"F6 se apoya en el doble del writer de F5"*, pero son **archivos distintos** y el ratchet exige aislamiento por archivo. | Se declara explícitamente que el fixture **se duplica**, no se importa ni se sube a un `conftest.py`, y por qué. |
| **C12** | F0 no fijaba entorno en el comando canónico ⇒ baselines no reproducibles ni seguros. | Cubierto por C4 (convención de §4). Los 13 baselines quedan **re-medidos y confirmados** para que nadie los vuelva a correr. |

### Menores

| # | Defecto | Resolución |
|---|---|---|
| **C13** | La cadena de compuertas de §3.1 se presentaba como exhaustiva y omitía `STACKY_INCIDENT_DEV_RESOLVER_ENABLED` (`config.py:1212-1213`, `"true"`), el master de la flag de PR. | Fila agregada. No cambia la conclusión: también está ON. |
| **C14** | F7.1 es un caso vacuo (asserta que el fixture registró el hook). | Se conserva, marcado como diagnóstico, con el gate real señalado (F7.2). |
| **C15** | El v1 no advertía que las 4 llamadas de `agent_runner.py` van por el **alias `_ts.`**: un censo por la cadena larga daría cero para ese runtime. | Nota agregada en F7. |

### Lo que se verificó y quedó IGUAL porque estaba bien

La decisión central **(a) contra (b)** —la cadena de 7 compuertas hacia GitLab, con `.env:7` en `true`—; los **13 baselines**; los **490 flags** y las tres razones por las que ninguna puede declarar `requires=` (R1/R4 leídas en `harness_flags.py:7343` y `:7346-7347`); `default_is_known` en `:7299`; los **20 call sites** de los tres runners; `828`/`764` en los ratchets y la trampa de la coma final del `.ps1`; el allowlist de **207** líneas; `mark_intent(**fields)` aceptando kwargs nuevos; `create_merge_request` llamada con keywords en `:100-101`; `_request` en `gitlab_client.py:265-274`; `TrackerApiError` en `tracker_provider.py:48-52` con `message` posicional; `_MAX_FILES`/`_BRANCH_PREFIX` intactos; **el HITL de `api/pr_review.py`** (`confirm` en `:389-390`, `confirm_merge` en `:391-393`, `merge` en `:404-405`, `approve` en `:408-411`) **que este plan efectivamente no toca**; y **§1.1 con `NO MEDIBLE` escrito literal**, que era uno de los aciertos del v1.

### `[ADICIÓN ARQUITECTO]`

**1 — `_inspeccionar` en dos mitades es una pieza reusable, no un parche del auto-PR.** El defecto que hundió a F5 —usar un saneador de *lectura* en un camino de *escritura*— no es exclusivo de este eje: cualquier futuro camino que escriba texto generado por un modelo en un sistema del operador (pipelines, documentación, scripts) tiene el mismo agujero. Por eso `_PATRONES_ALTA_CONFIANZA` + `_inspeccionar` se escriben **con contrato explícito `(texto, hubo_hallazgo)` y sin dependencias de `incident_dev_autocommit`**, para que el próximo plan los pueda mover a `services/` sin reescribirlos. **No se mueven ahora**: mover sin un segundo consumidor sería abstracción prematura.

**2 — `F6.8` introduce el patrón "gate con mitad de contraste", y debería volverse idioma de la casa.** Todo gate que asserte un invariante del producto lleva **dos** corridas: una que pasa y una que, con el símbolo del producto parcheado, **debe fallar**. Es la única forma barata de demostrar que el gate puede ponerse rojo. Los tres moldes de gate muerto del glosario se detectan solos con esta técnica: si no se puede construir la mitad que falla, el gate es vacuo. **En este plan se aplica a F6.8** (el que sostiene un KPI) y se recomienda como criterio de aceptación para los planes de la serie.

**3 — El arnés tiene un test que sale a la red y nadie lo vigila.** Se descubrió midiendo, no leyendo, y no es de este eje. Queda como acción del operador (§6.1.3) con el remedio concreto: mover el guard de `conftest.py` de `socket.connect` a `socket.getaddrinfo` lo atraparía **antes** del DNS, que es donde hoy se escapa.
