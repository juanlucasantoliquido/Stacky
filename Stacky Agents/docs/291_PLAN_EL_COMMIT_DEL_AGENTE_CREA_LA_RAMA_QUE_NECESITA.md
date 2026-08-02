# Plan 291 — El commit del agente crea la rama que necesita

**Estado:** PROPUESTO (v1) — sin implementar
**Fecha:** 2026-08-02
**Rama de trabajo:** `docs/plan-279`
**Alcance:** backend (`services/gitlab_provider.py`, `services/incident_dev_autocommit.py`), registro de 2 flags, tests. **Cero frontend.**

---

## 1. Título, objetivo y KPI

### Objetivo en una frase

Que `commit_file` de GitLab pueda **crear la rama destino cuando no existe** (como el adaptador de Azure DevOps ya hace desde el plan 95), y que el diagnóstico deje de confundir *"la rama no existe"* con *"el archivo no existe"* — **sin que Stacky empiece a escribir en el GitLab real del operador hasta que él lo decida**.

### KPI

| # | KPI | Valor hoy | Meta | Cómo se mide |
|---|---|---|---|---|
| **K1** | Merge Requests abiertos por Stacky en el GitLab del operador con estado `opened` | **0** | ≥ 1 tras la activación | **NO MEDIBLE** hasta que el operador encienda la flag y corra el humo de §4.9. Ver §1.1. |
| **K2** | Commits de Stacky fuera de una rama con prefijo `stacky/` | **0** | **0** (invariante) | Test F4.4 + revisión del operador en el humo. |
| **K3** | Llamadas a `commit_file` de GitLab que fallan por *"You can only create or edit files when you are on a branch"* con la flag ON | n/a (hoy la flag no existe) | **0** | Test F4.1/F4.2 contra el doble. |
| **K4** | Archivos commiteados por el auto-PR sin pasar por `redact_secrets` | **todos** (hoy no se redacta) | **0** | Test F5.2 sobre el consumidor final. |

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
| `STACKY_INCIDENT_DEV_PR_ENABLED` | `backend/config.py:1220-1221`, `os.getenv(..., "true")` | **ON por default** | ❌ no detiene |
| El checkbox "Abrir PR" de la UI | `frontend/src/incidents/incidentDevPrModel.ts:8` → `export const DEFAULT_OPEN_PR = true; // premarcado` | **premarcado** | ❌ no detiene |
| El intent se registra | `backend/api/agents.py:1330-1336` | se registra si hay repo git | ❌ no detiene |
| La fábrica devuelve el writer de GitLab | `services/repo_writer.py:33` → `services/tracker_provider.py:130-156` | devuelve `GitLabTrackerProvider` cuando `tracker_type == "gitlab"` | ❌ no detiene |
| `STACKY_GITLAB_ENABLED` | `backend/config.py:1297-1298`, default `"false"` | **OFF en el código** | ⚠️ **es una decisión del operador, no del código** |

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
| **Redacción del contenido** (`redact_secrets` antes de commitear) | Filtra secretos del texto que salió de un LLM antes de que se commitee | No abre camino nuevo; endurece uno existente | **`STACKY_AUTOCOMMIT_REDACT_ENABLED`, nace ON** (kill-switch) |

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
| **Cero trabajo extra al operador** | Con las flags en su default (start_branch OFF, redact ON) el operador **no tiene que hacer nada** y el sistema se comporta exactamente como hoy, salvo que el mensaje de error del auto-PR de GitLab pasa a ser útil. |
| **Backward-compatible** | Ninguna firma pública cambia de forma incompatible: `_detect_commit_action` gana un parámetro **keyword-only con default `None` = comportamiento de hoy**; `_build_pr_body` gana un keyword con default `None`. |
| **Reusar lo existente** | `create_merge_request` (`gitlab_provider.py:819`) **se reusa tal cual, NO se reescribe**. `redact_secrets` (`pr_review_sanitize.py:33`) se reusa. `_MAX_FILES = 60` (`incident_dev_autocommit.py:23`) **se queda intacto**. `_BRANCH_PREFIX = "stacky/incidencia-"` (`:22`) **se queda intacto**. |
| **Sin degradar** | Cada fase declara qué pasa con su flag en OFF, y en todos los casos el OFF es el comportamiento de hoy. |

### 3.5 Hallazgo de plomería que ahorra un rojo garantizado

> **NINGUNA de las dos flags nuevas puede declarar `requires=`.** Verificado ejecutando contra el registry real el 2026-08-02:
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
> **Consecuencia práctica: ambas flags llevan `requires=None` (o sea, se omite el parámetro) y `tests/test_harness_flags_requires.py::_REQUIRES_MAP_FROZEN` (línea 120) NO se toca.** La dependencia real se explica en la `description` en prosa, que es donde el operador la lee.

---

## 4. Fases

> **Convención para todas las fases.** El comando de test es siempre, literal, **por archivo**, desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:
>
> ```
> "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q
> ```
>
> Se usa **`.venv`** (py3.13.5), **no** `venv` (py3.11.9, sin las dependencias).
> **Nunca** se corre `pytest tests` entero: la suite completa da miles de errores de contaminación cruzada y **no es un veredicto**.

---

### F0 — Congelar la línea base (sin tocar código de producto)

**Objetivo:** dejar por escrito, medido, el estado de cada suite que este plan puede mover, para que el criterio de cada fase sea **delta cero** y no "todo verde".

**Archivos:** ninguno de producto. Solo se registra el resultado en el mensaje de commit de F1.

**Baselines MEDIDOS el 2026-08-02** (con `DATABASE_URL` apuntando a una base de scratchpad, nunca la del operador):

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

> ⚠️ **`tests/test_plan73_generator_endpoint.py` está MODIFICADO por una sesión paralela viva.** Su baseline de 10 passed se midió sobre el árbol sucio. Si al implementar da otro número, **volver a medirlo antes de culpar a este plan**, con `git stash list` prohibido: simplemente re-medir y anotar.

**Rojos de fábrica del backend: 5 archivos / 11 tests fallando** (los 4 que el enunciado del plan anticipaba, **más** `test_plan218_tracker_contract.py`, que sale a la red y por eso no es determinista).

**Rojos de fábrica del frontend: 5 ratchets** (`uiDebt`, `formDebt`, `motionDebt`, `formatDebt`, `adhocModal`). **Este plan no toca frontend**, así que no los mueve.

**Criterio binario de F0:** los 13 números de la tabla están transcriptos en el cuerpo del commit de F1. Sin comando propio.

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F1 — `branch_exists`: preguntar si la rama existe, en vez de deducirlo de un 404 ajeno

**Objetivo:** dar al proveedor de GitLab una forma explícita y de solo lectura de saber si una rama existe.

**Archivo:** `Stacky Agents/backend/services/gitlab_provider.py`

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
    """
    proj_path = self._client._project_path()
    body, _ = self._client._request("GET", f"/projects/{proj_path}")
    return str((body or {}).get("default_branch") or "")
```

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

**Cómo se comprueba el ROJO:** antes de escribir el código, correr el archivo de tests. Los 5 casos fallan con `AttributeError: 'GitLabTrackerProvider' object has no attribute 'branch_exists'` (y `_default_branch_name`). Ese `AttributeError` **es** el rojo, y es rojo por la razón correcta: el símbolo no existe.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_start_branch.py" -q
```

**Criterio BINARIO:** `5 passed` en ese archivo, y **delta cero** en:
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_gitlab_provider.py" -q        → 26 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan73_repo_writer.py" -q      → 6 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q → 2 failed, 8 passed  (delta cero sobre el rojo de fábrica)
```

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

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_start_branch.py" -q
```

**Criterio BINARIO:** `9 passed` (5 de F1 + 4 de F2). Delta cero en `test_plan73_repo_writer.py` (6 passed) y `test_gitlab_provider.py` (26 passed).

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F3 — Registrar `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` (nace **OFF**, excepción **(B)**)

**Objetivo:** que exista la perilla que el operador va a encender, **apagada**, antes de que exista el código que la lee.

> **Una flag nueva tiene OCHO guardianes.** Los siete que hay que editar (o confirmar que no hace falta) están abajo; el octavo es el par de ratchets, ya cubierto en F1. Cada punto está anclado **por símbolo**, porque las líneas se mueven en horas.

**Archivos y símbolos EXACTOS:**

**(1) `Stacky Agents/backend/services/harness_flags.py` — `_CATEGORY_KEYS`**
Agregar la key dentro de la **misma tupla de categoría que ya contiene `"STACKY_INCIDENT_DEV_PR_ENABLED"`**, que es `"capacidades_optin"`. Anclaje: buscar la línea `"STACKY_INCIDENT_DEV_PR_ENABLED",          # Plan 177 — auto-PR del Dev Resolutor` y agregar debajo:
```python
        # Plan 291 — el commit del agente crea la rama que necesita (GitLab)
        "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED",   # Plan 291 — crea la rama destino (OFF)
        "STACKY_AUTOCOMMIT_REDACT_ENABLED",            # Plan 291 — redacta secretos antes de commitear
```
⚠️ **La categorización NO se deriva del prefijo de la key.** Si no se declara acá, `test_every_registry_flag_is_categorized` se pone rojo a propósito (nota en `harness_flags.py:615-616`).

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
            "empareja GitLab. Requiere que GitLab esté habilitado."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_AUTOCOMMIT_REDACT_ENABLED",
        type="bool",
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
        label="Filtrar secretos antes de commitear el fix del agente",
        description=(
            "Plan 291 — Antes de commitear un archivo que escribió el agente, "
            "Stacky enmascara lo que parezca una contraseña, un token, una clave "
            "privada o una dirección de correo. Los archivos en los que enmascaró "
            "algo quedan listados en la descripción del Pull Request para que los "
            "revises. Nace ENCENDIDA: es una red de seguridad, no una capacidad. "
            "Con OFF, el archivo se commitea tal cual salió del agente."
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

    # Nace ON: redactar secretos del texto que salió de un LLM es una red de
    # seguridad, no una capacidad nueva. No cae en (A) ni en (B). Es kill-switch.
    STACKY_AUTOCOMMIT_REDACT_ENABLED: bool = os.getenv(
        "STACKY_AUTOCOMMIT_REDACT_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
```

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
    "STACKY_AUTOCOMMIT_REDACT_ENABLED": PlainHelp(
        what="Revisa los archivos que escribió el agente y tapa lo que parezca una contraseña, una clave o un correo antes de subirlos.",
        on_effect="Si la activás: lo que parezca un dato sensible se reemplaza por una marca, y la propuesta de cambio lista en qué archivos pasó para que los mires.",
        off_effect="Si la apagás: los archivos se suben tal cual los escribió el agente, incluida cualquier contraseña o clave que haya quedado adentro.",
        example="Como pasar un marcador negro por los datos personales de una fotocopia antes de mandarla.",
    ),
```

⚠️ **`tests/test_harness_flags_help.py` está ROJO DE FÁBRICA (4 failed / 4 passed).** Dos de sus fallos son `test_plain_help_on_off_start_with_si` y `test_plain_help_avoids_jargon_denylist`. El criterio de esta fase es **delta cero: sigue en `4 failed, 4 passed`**, no "verde". Para no empeorarlo: los `on_effect`/`off_effect` de arriba **empiezan con `"Si "` SIN TILDE** (es exactamente lo que ese gate pide) y evitan jerga (`flag`, `endpoint`, `commit`, `branch`, `merge`, `PR`).

**(5) `tests/test_harness_flags.py::_CURATED_DEFAULTS_ON` (línea 467)**
Agregar **SOLO** `"STACKY_AUTOCOMMIT_REDACT_ENABLED"` (es la única que declara `default=True`). **NO** agregar la de start_branch: no declara `default=`, así que `default_is_known()` es `False` para ella y meterla en el set haría fallar `test_default_known_only_for_curated` por "faltante".

**(6) `tests/test_harness_flags_requires.py::_REQUIRES_MAP_FROZEN` (línea 120)**
**NO SE TOCA.** Ninguna de las dos flags declara `requires=` (§3.5).

**(7) `tests/test_flag_wiring.py::test_every_non_reserved_flag_is_wired`**
**No requiere edición**, pero **impone un orden**: el corpus que escanea son todos los `.py` de `backend/` **excepto** `tests/`, `services/harness_flags.py` y `services/harness_flags_help.py`, más los `.ts/.tsx` de `frontend/src` fuera de `__tests__` (`tests/test_flag_wiring.py:29-51`).
👉 **Consecuencia dura: `config.py` SÍ cuenta como consumo** (nota explícita en `:37-38`). Así que con el paso (3) hecho, este test pasa desde F3. Aun así, F4 y F5 agregan el consumidor **lógico** real, que es lo que le da sentido.
**NO** marcar las flags como `reserved=True`: tienen consumidor dentro de este mismo plan.

**(8) `Stacky Agents/deployment/harness_defaults.env`**
**No se regenera.** Medido el 2026-08-02: ese archivo **no contiene** `STACKY_TRACKER_CONTEXT_ENABLED` (la flag del plan 289), o sea que ya es **parcial por diseño** y ningún test exige que esté completo. Tocarlo es fuera de scope.

**Tests PRIMERO.** Mismo archivo `tests/test_plan291_start_branch.py`:

| id | Caso | Aserción |
|---|---|---|
| F3.1 | ambas keys están en `FLAG_REGISTRY` | `_REGISTRY_INDEX["STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED"]` y `..._AUTOCOMMIT_REDACT_ENABLED` no son `None`, y ambos `.type == "bool"` |
| F3.2 | la de start_branch **nace OFF** en el default efectivo | `getattr(config.config, "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED") is False` (con el entorno limpio de esa env var) |
| F3.3 | la de redact **nace ON** | `getattr(config.config, "STACKY_AUTOCOMMIT_REDACT_ENABLED") is True` |
| F3.4 | la de start_branch **NO declara default** | `_REGISTRY_INDEX["STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED"].default is None` y `default_is_known(spec) is False` |
| F3.5 | **ninguna declara `requires`** | `spec.requires is None` para las dos, **y** `validate_requires_graph() == []` |
| F3.6 | ambas tienen entrada en `PLAIN_HELP` | `PLAIN_HELP["<key>"]` existe para las dos y su `on_effect` empieza con `"Si "` |

**Cómo se comprueba el ROJO:** los 6 fallan hoy con `KeyError` / `AssertionError` porque las keys no existen en ningún registro.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_start_branch.py" -q
```

**Criterio BINARIO de F3 — los cinco comandos, con su número exacto:**
```
pytest tests/test_plan291_start_branch.py      -q  →  15 passed          (5+4+6)
pytest tests/test_harness_flags.py             -q  →  59 passed          (delta cero)
pytest tests/test_harness_flags_requires.py    -q  →   9 passed          (delta cero)
pytest tests/test_flag_wiring.py               -q  →   5 passed          (delta cero)
pytest tests/test_harness_flags_help.py        -q  →   4 failed, 4 passed (DELTA CERO sobre el rojo de fábrica)
pytest tests/test_flags_env_read_meta.py       -q  →   1 failed, 1 passed (DELTA CERO sobre el rojo de fábrica)
```
> Si `test_harness_flags_help.py` pasa a **5 failed**, la entrada de `PLAIN_HELP` está mal escrita — **es regresión de este plan**, no el rojo de fábrica.

**Flag:** las dos que se crean. **Defaults:** start_branch **OFF**, redact **ON**.
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
| **F4.7** | **K2 — invariante de prefijo**: todos los POST de F4.1 y F4.4 | `cliente.posts[i][1]["branch"].startswith("stacky/")` para todos |

**Cómo se comprueba el ROJO (esto es lo que hay que hacer, en este orden):**

1. Escribir el archivo de tests **antes** de tocar `commit_file`.
2. Correr el comando. **F4.1 falla** con `AssertionError: 'start_branch' not in {...}` — porque hoy `commit_file` nunca lo agrega. **F4.3 falla** con `Failed: DID NOT RAISE TrackerApiError`. **F4.5 falla** igual.
3. Pegar ese output en el commit. **Un rojo que no se leyó no cuenta.**

⚠️ Con el código de HOY, el `ClienteFalso` recibiría un `GET /repository/files/...` que devuelve 404, `_detect_commit_action` devolvería `("create", None)` y el POST se haría **sin `start_branch`** — o sea, el doble reproduce exactamente el bug. **Ese es el rojo por la razón correcta.**

**Cómo se manipula la flag en el test:** con `monkeypatch.setattr(config.config, "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", True/False, raising=False)`. **No** se toca `os.environ`: `config = Config()` se instancia en el import y `os.getenv` ya corrió.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_start_branch.py" -q
```

**Criterio BINARIO:**
```
pytest tests/test_plan291_start_branch.py           -q  →  22 passed  (5+4+6+7)
pytest tests/test_plan73_repo_writer.py             -q  →   6 passed  (delta cero)
pytest tests/test_gitlab_provider.py                -q  →  26 passed  (delta cero)
pytest tests/test_plan70_gitlab_provider_complete.py -q →  19 passed  (delta cero)
pytest tests/test_plan73_generator_endpoint.py      -q  →  10 passed  (delta cero — re-medir, archivo sucio por sesión paralela)
```

**Flag:** `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`. **Default: OFF, excepción (B).**
**Impacto por runtime:** ninguno — `gitlab_provider` es agnóstico de runtime. **Fallback:** con la flag OFF, comportamiento de hoy salvo el mensaje de error, que mejora.
**Trabajo del operador:** ninguno. La perilla queda disponible, apagada.

---

### F5 — El contenido que sale de un LLM pasa por `redact_secrets` antes de commitear

**Objetivo:** que nunca se commitee un secreto que el agente dejó en un archivo, y que **el operador vea en qué archivos se enmascaró algo**.

**Archivo:** `Stacky Agents/backend/services/incident_dev_autocommit.py`

**Símbolos EXACTOS:**
- **Se agrega** el helper de módulo `_redactar(texto: str) -> tuple[str, bool]`.
- **Se modifica** el bucle `for rel in changed:` (hoy `:83-89`) dentro de `maybe_open_pr_for_incident_dev`.
- **Se modifica** la firma de `_build_pr_body` (hoy `:208`) agregando **un keyword con default**.
- **Se modifica** la llamada a `mark_intent(... status="opened" ...)` (hoy `:103-104`).

**Diff conceptual:**

```python
+def _redactar(texto):
+    """(texto_saneado, hubo_cambio). Reusa services.pr_review_sanitize.redact_secrets:33.
+    Con la flag OFF devuelve el texto TAL CUAL y False (camino byte-idéntico a hoy)."""
+    from config import config as _cfg
+    if not bool(getattr(_cfg, "STACKY_AUTOCOMMIT_REDACT_ENABLED", True)):
+        return texto, False
+    from services.pr_review_sanitize import redact_secrets
+    saneado = redact_secrets(texto)
+    return saneado, (saneado != texto)

     committed: list[str] = []
     skipped_binary: list[str] = []
+    redactados: list[str] = []
     commit_msg = f"fix(incidencia #{...}): resolución del Dev Resolutor + tests"
     for rel in changed:
         content = _read_text_or_none(repo_root, rel)
         if content is None:
             skipped_binary.append(rel)
             continue
-        writer.commit_file(rel, content, branch, commit_msg)   # crea la rama en el 1er call
+        content, hubo_redaccion = _redactar(content)
+        if hubo_redaccion:
+            redactados.append(rel)
+        # Azure DevOps crea la rama solo (ado_provider.py:183-190). GitLab la crea
+        # solo desde el plan 291 y SOLO con STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED
+        # encendida; con la flag apagada esto lanza TrackerApiError(kind="branch_missing")
+        # y el except de abajo lo comenta en la Issue. El comentario viejo
+        # ("crea la rama en el 1er call") era falso para GitLab.
+        writer.commit_file(rel, content, branch, commit_msg)
         committed.append(rel)
...
-    title, description = _build_pr_body(ado_id, classify, deleted, origin)
+    # (se mueve DESPUÉS del bucle: la lista de redactados no existe hasta que
+    #  el bucle terminó. Hoy _build_pr_body se llama ANTES, en :73.)
+    title, description = _build_pr_body(ado_id, classify, deleted, origin,
+                                        redactados=redactados)
...
     incident_dev_pr.mark_intent(execution_id, status="opened", pr_id=pr.get("id"),
                                 pr_url=pr_url, branch=branch,
-                                files_committed=committed, origin=origin)
+                                files_committed=committed, origin=origin,
+                                redacted_files=redactados)
```

Y en `_build_pr_body`:
```python
-def _build_pr_body(ado_id, classify, deleted, origin):
+def _build_pr_body(ado_id, classify, deleted, origin, *, redactados=None):
     ...
+    if redactados:
+        lines += ["", "**⚠️ Archivos con datos enmascarados antes de subir**",
+                  "Revisá estos archivos: se reemplazó algo que parecía una clave, "
+                  "un token o un correo por una marca.",
+                  *[f"- `{p}`" for p in redactados]]
     return title, "\n".join(lines)
```

> ⚠️ **Reordenamiento obligatorio y fácil de olvidar:** hoy `_build_pr_body` se llama en la **línea 73**, **antes** del bucle de commits (`:83`). La lista `redactados` **no existe todavía** en ese punto. **Hay que mover la llamada a después del bucle**, justo antes de `target = _default_branch_for(...)` (`:99`). Si no se mueve, `redactados` siempre llega vacío y el gate F5.3 sale verde con el defecto vivo.

**Casos borde:**

| # | Caso | Comportamiento |
|---|---|---|
| 1 | Archivo con un token tipo `ghp_xxxx` | se enmascara; el archivo entra en `redactados` |
| 2 | Archivo sin nada sensible | pasa **idéntico**; NO entra en `redactados` |
| 3 | **Archivo con un email legítimo en el código** | ⚠️ `redact_secrets` **también enmascara emails** (patrón PII en `pr_review_sanitize.py:29`). El email se reemplaza. **Es esperado, está testeado y se REPORTA** — ver Riesgo R2 |
| 4 | Flag `STACKY_AUTOCOMMIT_REDACT_ENABLED` **OFF** | `_redactar` devuelve el texto tal cual; `redactados` queda vacío; camino byte-idéntico a hoy |
| 5 | Archivo binario / no-utf8 | ya lo filtra `_read_text_or_none` **antes**; nunca llega a `_redactar` |
| 6 | Más de `_MAX_FILES` (60) archivos | **el tope existente se queda tal cual** (`:23` y `:57`); corta antes del bucle |

**Tests PRIMERO.** Archivo NUEVO: `Stacky Agents/backend/tests/test_plan291_autocommit_redaccion.py`

> Se crea archivo aparte del de F1-F4 porque el doble es distinto (acá se falsea el `writer` y el `mrp`, no el cliente HTTP), y porque así cada archivo sigue pasando **en aislamiento**, que es lo que el ratchet exige.

| id | Caso | Aserción — **sobre el consumidor final** |
|---|---|---|
| F5.1 | `_redactar("password=hunter2secreto")` con flag ON | el resultado **no contiene** `hunter2secreto`, y el bool es `True` |
| F5.2 | `maybe_open_pr_for_incident_dev` end-to-end con un `writer` falso y un archivo con un token | **el `content` que recibió `writer.commit_file`** (`writer.llamadas[0][1]`) no contiene el token. ⚠️ **La aserción va sobre el argumento que llegó a `commit_file`, NO sobre el retorno de `_redactar`** |
| F5.3 | mismo caso | **el `description` que recibió `mrp.create_merge_request`** contiene la ruta del archivo redactado. ⚠️ **Sobre el kwarg real de `create_merge_request`, no sobre el retorno de `_build_pr_body`** |
| F5.4 | archivo limpio (`"def f():\n    return 1\n"`) | `writer.llamadas[0][1] == "def f():\n    return 1\n"` **exactamente**, y el `description` **no** contiene la sección "datos enmascarados" |
| F5.5 | flag **OFF**, archivo con token | `writer.llamadas[0][1]` contiene el token **tal cual** (el OFF es byte-idéntico a hoy) |
| F5.6 | archivo con un email (`autor = "juan@empresa.com"`) | el `content` que llegó a `commit_file` **no** contiene `juan@empresa.com`, **y** el archivo aparece en el `description`. **Este test congela la conducta de PII como conocida y reportada, no como sorpresa** |

**Cómo se comprueba el ROJO:** F5.2 falla hoy con `AssertionError` — el token llega intacto a `commit_file` porque nadie redacta. F5.3 falla con `AssertionError` — el `description` no menciona nada. F5.4 y F5.5 **pasan hoy** a propósito: guardan la **PRESENCIA** del comportamiento correcto (contenido intacto cuando no hay nada que redactar), no la ausencia de algo.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_autocommit_redaccion.py" -q
```

**Registro en los ratchets — MISMO COMMIT que crea el archivo.** Idéntico al procedimiento de F1 (`.sh` sin comillas / `.ps1` con comillas y coma, insertando en el medio para no tocar la cola sin coma).

**Criterio BINARIO:**
```
pytest tests/test_plan291_autocommit_redaccion.py -q  →   6 passed
pytest tests/test_incident_dev_autocommit.py      -q  →  11 passed  (DELTA CERO — el keyword con default y el reordenamiento NO deben romper ninguno)
```

**Flag:** `STACKY_AUTOCOMMIT_REDACT_ENABLED`. **Default: ON** (no cae en (A) ni en (B): no gasta tokens en reposo, no abre camino de escritura nuevo, no le saca ninguna decisión al operador — el MR sigue siendo una propuesta que él revisa).
**Impacto por runtime:** ninguno — corre en el post-hook agnóstico. **Fallback:** OFF = comportamiento de hoy.
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

⚠️ **F6.7 es el gate real de esta fase.** F6.1-F6.6 prueban la función; **F6.7 prueba que la función DETIENE el commit**. Un gate que solo mira el booleano de `_worktree_maps_to_wrong_repo` sería un test estático sobre un defecto de ejecución: tiene que **ejecutar** el post-hook y verificar que el writer **no fue llamado**.

**Cómo se comprueba el ROJO:** F6.1-F6.7 **deberían pasar hoy** — el guardia existe. Ese es el punto: **esta fase es una red de seguridad que se instala antes de encender la escritura**. Si alguno falla, se encontró un bug vivo y **se arregla acá**. Para probar que el test no es vacuo (no es un `assert` de ausencia que pasa por accidente), **F6.7 se corre dos veces**: una con el origin ajeno (esperando `writer.llamadas == []`) y otra con el origin correcto (esperando `len(writer.llamadas) == 1`). **La segunda mitad guarda la PRESENCIA** y es lo que impide que el test pase porque el writer nunca se llama por otro motivo.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_guardia_repo.py" -q
```

**Registro en los ratchets:** mismo procedimiento de F1, en el mismo commit.

**Criterio BINARIO:** `8 passed` (7 casos + la mitad positiva de F6.7 como caso propio). Delta cero en `tests/test_incident_dev_autocommit.py` → `11 passed`.

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

**Conclusión de paridad, escrita explícitamente:** este plan **no agrega ni una sola rama condicional por runtime**. `gitlab_provider` no sabe qué runtime corrió, y `incident_dev_autocommit` corre después del chokepoint compartido. **No hace falta fallback por runtime**, porque no hay comportamiento por runtime. Si algún día un runtime dejara de llamar `on_execution_end`, el auto-PR **ya estaría roto hoy** para ese runtime, independientemente de este plan — sería un defecto del plan 177, no de este.

**Test PRIMERO.** Se agrega a `Stacky Agents/backend/tests/test_plan291_guardia_repo.py` (archivo ya registrado en los ratchets por F6, así que **no hay registro nuevo**):

| id | Caso | Aserción |
|---|---|---|
| **F7.1** | `maybe_open_pr_for_incident_dev` está en `ticket_status._POST_HOOKS` después de importar y registrar | la función aparece en la lista |
| **F7.2** | **EJECUTANDO**: se llama `ticket_status.on_execution_end(...)` con `agent_type="incident_dev"`, `final_status="completed"` y un intent con `open_pr=True`, con el writer y el mrp falseados | **`writer.llamadas` tiene 1 entrada** — o sea, el hook **se disparó desde el chokepoint compartido**, no desde una llamada directa al hook |
| **F7.3** | mismo, pero con `agent_type="incident"` (otro agente) | `writer.llamadas == []` — el hook filtra bien y no se dispara de más |

⚠️ **F7.2 es el gate que no puede ser estático.** Un test que solo grepeara los 3 runners buscando `"on_execution_end"` sería un test estático sobre un defecto de ejecución (molde de gate muerto (b)). **Tiene que llamar a `on_execution_end` de verdad** y comprobar que el efecto llegó al final de la cadena.
⚠️ **F7.3 guarda la PRESENCIA del filtro** para que F7.2 no pase por accidente.

**Cómo se comprueba el ROJO:** F7.2 falla si el hook no está registrado o si el chokepoint no lo dispara. Con `app.py` sin importar, `_POST_HOOKS` está vacío, así que el test **debe** registrar el hook explícitamente (`incident_dev_autocommit.register(ticket_status.register_post_hook)`) en un fixture y limpiarlo al final, **sin** llamar `create_app()`.

> ⚠️ **PROHIBIDO llamar `create_app()` en estos tests.** Con `pytest` en `sys.modules` y `STACKY_TEST_MODE=1` **igual arranca los watchers** y hace efectos reales.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan291_guardia_repo.py" -q
```

**Criterio BINARIO:** `11 passed` (8 de F6 + 3 de F7).

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

1. Abrí el panel de opciones de Stacky (**Configuración → Opciones avanzadas**), categoría **"Capacidades opcionales"**.
2. Confirmá que **"Sistema de tickets GitLab"** (`STACKY_GITLAB_ENABLED`) está **encendido** — sin eso no hay camino a GitLab.
3. Confirmá que **"Abrir PR al resolver incidencias"** (`STACKY_INCIDENT_DEV_PR_ENABLED`) está **encendido** (viene encendido de fábrica).
4. Encendé **"Crear la rama del fix cuando no existe (GitLab)"** (`STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`). **Este es el paso que autoriza a Stacky a escribir en tu GitLab.**
5. El cambio **aplica en caliente**: el endpoint hace `setattr(config, key, val)` sobre la instancia viva (`api/harness_flags.py:153`) además de persistirlo. **No hace falta reiniciar** (la `FlagSpec` no declara `restart_required`).

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
| La descripción del MR | las listas de **Cambios de código**, **Tests incluidos**, el **Origen del working tree**, y —si hubo— la sección **⚠️ Archivos con datos enmascarados** | — |
| El MR | **NO** debe estar mergeado ni aprobado | Si lo está, es un bug grave: reportalo. `approve`/`merge` viven detrás de tu botón (`api/pr_review.py:387-411`) y `merge` además exige la casilla de confirmación fuerte |

5. **Recién después de ver ese MR `opened`, K1 pasa a ser medible.**

#### 8.3 — Cómo apagarlo

Apagá **"Crear la rama del fix cuando no existe (GitLab)"**. Vuelve el comportamiento previo al plan: Stacky no crea ninguna rama en GitLab y avisa en la Issue cuál era la rama que faltaba. **Las ramas y MRs ya creados NO se borran** — eso es decisión tuya, a mano.

**Criterio BINARIO de F8:**
```
grep -c "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED" "Stacky Agents/docs/sistema/<archivo>"   →  >= 1
grep -c "NO MEDIBLE"                                "Stacky Agents/docs/sistema/<archivo>"   →  >= 1
grep -c "stacky/incidencia-"                        "Stacky Agents/docs/sistema/<archivo>"   →  >= 1
```
Y en este mismo documento, la sección §1.1 dice literalmente `NO MEDIBLE`.

**Flag:** ninguna. **Impacto por runtime:** ninguno.
**Trabajo del operador:** **TODO §8.1 y §8.2.** Es la única fase con trabajo del operador, y es a propósito: es la decisión que este plan **no** le saca.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación en este plan |
|---|---|---|---|---|
| **R1** | **Commitear en el repositorio equivocado.** El working tree local apunta a otro remoto y Stacky sube el fix ahí. **Es el peor fallo posible de este eje.** | Baja | **Crítico** | `_worktree_maps_to_wrong_repo` ya corta (`:63-69`), y **F6 lo ejercita por primera vez contra un `origin` de GitLab**, incluida la forma SSH y el caso de integración F6.7 que verifica que el writer **no se llama**. |
| **R2** | **`redact_secrets` enmascara EMAILS** (patrón PII, `pr_review_sanitize.py:29`). Un email legítimo en el código (cabecera de licencia, `@author`, fixture de test) se reemplaza por `***REDACTED***` en el archivo commiteado. | **Alta** | Medio | **No se oculta: se prueba y se reporta.** F5.6 congela la conducta como conocida. Los archivos afectados van listados en la descripción del MR (F5.3) y en el intent (`redacted_files`). El operador los ve **antes** de mergear — el MR es una propuesta, no un merge. Si molesta, `STACKY_AUTOCOMMIT_REDACT_ENABLED` es el kill-switch. |
| **R3** | **`start_branch` mandado dos veces.** GitLab podría rechazar el segundo commit o crear un commit huérfano. | Media si el doble es ingenuo | Alto | El doble de F4 **tiene estado**: la rama pasa a existir tras el primer POST. **F4.1 asserta explícitamente que el segundo POST NO lo lleva.** Un `MagicMock` plano habría dado falso verde. |
| **R4** | **Adivinar `"main"`** cuando el repo usa `master` o `develop`: se crearía la rama desde una base equivocada. | Media | Alto | `_default_branch_name()` **lee** `/projects/:id → default_branch`. F4.2 lo prueba con `"develop"`. Nunca hay literal `"main"` en el camino de `start_branch`. |
| **R5** | **Repo vacío** sin rama default: `start_branch=""` produciría un error críptico. | Baja | Bajo | `TrackerApiError(400, kind="repo_empty")` con mensaje accionable, **antes** del POST. F4.5. |
| **R6** | **Deuda ajena vecina:** `_default_branch_for` (`incident_dev_autocommit.py:157-164`) **importa de `api.devops_production`** — un servicio importando de `api/`, que viola el riel del repo — y hace `fallback DURO 'main'` ante cualquier excepción. Si el repo usa `master`, el MR podría apuntar a un `target_branch` inexistente. | Baja | Medio | **Fuera de scope, declarado.** Este plan **no agrega** ningún import de `api/` (por eso `_default_branch_name` vive en el provider). Se anota para un plan futuro. |
| **R7** | **Una llamada `GET` extra por cada `commit_file` de GitLab.** Afecta también a `api/pipeline_editor.py:285` y `api/pipeline_generator.py:122`. | Cierta | Bajo | Se declara explícitamente (§3.3). Es un `GET` a `/repository/branches/:branch`, no una lista paginada. A cambio, elimina un `GET` inútil de archivos cuando la rama no existe (F2.2), o sea que en el camino roto el neto es **cero llamadas extra**. |
| **R8** | **Sesión paralela VIVA** editando los mismos archivos. Al momento de escribir este plan hay **34 archivos sucios**, incluido `tests/test_plan73_generator_endpoint.py`, que este plan mide como baseline. | **Cierta** | Medio | Antes de cada commit: `git status --short`. Commitear **solo** las rutas propias con `git commit -- "<ruta>"`. **PROHIBIDO** `amend`, `reset`, `rebase`, `stash`, `checkout`. Si un baseline no coincide, **re-medir**, no culpar. |
| **R9** | **El ratchet es una trampa de COMMIT, no solo de edición.** Crear un test nuevo sin registrarlo en **ambos** scripts bloquea el commit. | Media | Bajo | F1, F5 y F6 registran su archivo **en el mismo commit que lo crea**. La trampa de la coma final del `.ps1` está documentada con el remedio (insertar en el medio). |
| **R10** | **El plan cambia el mensaje de error del auto-PR de GitLab** aun con la flag OFF. Un test ajeno podría estar congelando el mensaje viejo. | Baja | Bajo | Criterio delta cero sobre `test_incident_dev_autocommit.py` (11 passed) y `test_gitlab_provider.py` (26 passed) en F2 y F4. Si alguno se rompe, **es un test ajeno congelando el bug** y hay que decidirlo a conciencia, no silenciarlo. |
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

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado exacto en este plan |
|---|---|
| **`start_branch`** | Campo del body de `POST /projects/:id/repository/commits` de la API v4 de GitLab. Nombre de la rama **base** desde la cual crear la rama destino si no existe. **Se manda una sola vez, en el primer commit.** |
| **`branch_exists`** | Método nuevo, de **solo lectura**, en `GitLabTrackerProvider`. `GET /repository/branches/:branch`; `True`/`False`/propaga. |
| **`_ACCION_RAMA_NUEVA`** | Constante de módulo con valor `"create_new_branch"`. **Sentinela INTERNO**, no es una acción válida de la API de GitLab. `commit_file` lo traduce a `"create"`. |
| **Excepción (B)** | Regla de la casa: una flag nueva nace **OFF** si **escribe en un sistema real del operador**, destruye datos, o le saca una decisión. |
| **Rojo de fábrica** | Test que ya falla **antes** de tocar nada. Su criterio es **delta cero**, no "verde". |
| **Delta cero** | El conteo `N failed, M passed` de una suite es **idéntico** antes y después. |
| **Doble del cliente** | Objeto de test que reemplaza `GitLabClient` y **no hace red**. Acá tiene **estado**: la rama pasa a existir tras un POST exitoso. |
| **Chokepoint** | `ticket_status.on_execution_end` (`services/ticket_status.py:293`), el único punto que los 3 runtimes llaman al terminar. |
| **HITL** | Human-in-the-loop. Acá: el MR es una **propuesta**; aprobar y mergear son botones del operador. |

### 7.2 Orden de implementación (dependencias duras)

```
F0  medir baselines           (sin dependencias)
 └─ F1  branch_exists          ← necesita F0 para el criterio delta cero
     └─ F2  _detect_commit_action  ← usa el sentinela; independiente de F1 en código,
     │                              pero F4 necesita las DOS
     └─ F3  registrar las 2 flags   ← puede ir en paralelo con F1/F2
         └─ F4  start_branch en el body   ← NECESITA F1 + F2 + F3 (las tres)
             └─ F5  redact_secrets        ← necesita F3 (la flag de redacción)
                 └─ F6  guardia de repo   ← se apoya en el doble del writer de F5
                     └─ F7  paridad 3 runtimes  ← se apoya en los dobles de F6
                         └─ F8  documentación + activación del operador  ← última
```

**Regla de commits:** **un commit por fase**, mensaje `feat(plan-291): F<n> - <qué hace>`. Los archivos de test nuevos se registran en **ambos** ratchets **en el mismo commit que los crea**. Antes de cada commit: `git status --short`, y commitear **solo** las rutas propias con `git commit -- "<ruta1>" "<ruta2>"`.

### 7.3 Definition of Done

| # | Criterio | Comando / verificación |
|---|---|---|
| 1 | `branch_exists` y `_default_branch_name` existen y están probados | `pytest tests/test_plan291_start_branch.py -q` → **22 passed** |
| 2 | `_detect_commit_action` **no** devuelve `"create"` por un 404 de rama | caso F2.1 verde |
| 3 | El **primer** POST lleva `start_branch` y el **segundo no** | caso F4.1 verde, y su rojo previo pegado en el commit de F4 |
| 4 | Con la flag OFF, cero POST y error accionable | caso F4.3 verde (`cliente.posts == []`) |
| 5 | La rama base se **lee**, no se adivina | caso F4.2 verde con `"develop"` |
| 6 | Todo lo commiteado pasa por `redact_secrets` | `pytest tests/test_plan291_autocommit_redaccion.py -q` → **6 passed**; F5.2 asserta sobre el argumento real de `commit_file` |
| 7 | Los archivos redactados llegan a la descripción del MR | F5.3 asserta sobre el kwarg real de `create_merge_request` |
| 8 | El guardia de repo detiene el commit con un `origin` de GitLab ajeno | `pytest tests/test_plan291_guardia_repo.py -q` → **11 passed**; F6.7 con sus dos mitades |
| 9 | La paridad de los 3 runtimes está probada **ejecutando** | caso F7.2 verde |
| 10 | **Cero commits fuera de una rama `stacky/`** (K2) | caso F4.7 verde |
| 11 | `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` sigue **OFF** al terminar | `grep -n 'STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", "false"' "Stacky Agents/backend/config.py"` → 1 resultado |
| 12 | Los dos ratchets tienen los 3 archivos nuevos | `grep -c "test_plan291" scripts/run_harness_tests.sh` → **3**; ídem en `.ps1` → **3** |
| 13 | Ninguno de los 3 archivos nuevos está en el allowlist | `grep -c "plan291" tests/harness_ratchet_allowlist.txt` → **0** |
| 14 | **Delta cero** en las 8 suites vecinas | los 8 conteos de F0 se reproducen exactos |
| 15 | Los rojos de fábrica siguen igual | `test_harness_flags_help.py` → 4F/4P; `test_flags_env_read_meta.py` → 1F/1P; `test_plan218_coupling_ratchet.py` → 3F/7P; `test_plan218_capability_matrix.py` → 2F/8P; `test_plan218_tracker_contract.py` → 1F/9P |
| 16 | La documentación de activación existe | los 3 `grep` de F8 dan ≥ 1 |
| 17 | **K1 se reporta como NO MEDIBLE**, con las palabras de §1.1 | revisión del resumen final |
| 18 | Cero llamadas de red en toda la implementación | ningún test importa `requests` sin doble; el guard de egress de `conftest.py:31-52` bloquea `connect()` bajo `STACKY_TEST_MODE` |

**El plan está DONE cuando los 18 criterios se cumplen Y `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` sigue apagada.** Un plan 291 que termina con esa flag encendida **no está done: está mal implementado.**
