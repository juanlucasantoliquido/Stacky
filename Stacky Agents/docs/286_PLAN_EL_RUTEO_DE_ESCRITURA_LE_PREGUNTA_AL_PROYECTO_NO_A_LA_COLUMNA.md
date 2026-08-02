# Plan 286 — El ruteo de escritura deja de preguntarle a la columna y le pregunta al proyecto

**Estado:** PROPUESTO (v1)
**Eje:** corrección de ruteo por tracker — continuación directa del Plan 281
**Fecha:** 2026-08-01
**Rama al escribir:** `docs/plan-279`
**Alcance:** backend. Cero frontend. Cero flags nuevas. Cero migraciones de datos.

---

## 1. Objetivo

Hoy quedan **cuatro escritores** del backend que deciden a qué tracker le escriben leyendo
`ticket.tracker_type`, una columna cuyo default de ORM es `"azure_devops"`
(`backend/models.py:49`) y que por lo tanto **miente** para cualquier fila creada sin ese
campo en un proyecto que no es Azure DevOps. Este plan introduce **un único helper de
"tracker efectivo"** con precedencia declarada — *columna explícita > config del proyecto >
default* — y reemplaza con él los cuatro sitios. Nada más.

El Plan 281 F6 ya hizo exactamente esto en `services/run_ticket_refresh.py:46-58`, pero
solo ahí. El 286 extiende **ese mismo patrón** a los escritores que quedaron, y de paso
destapa dos falsos verdes que hacían invisible el problema.

**KPI / impacto esperado (todos medidos el 2026-08-01 contra la BD viva
`backend/data/stacky_agents.db`):**

| KPI | Hoy | Meta |
|---|---|---|
| Tickets de un proyecto GitLab que la columna manda a Azure DevOps | **2** (`ado_id=-7` "[Documentador] RIPLEY", `ado_id=-1` "[Stacky] Brief Pool") | **0** |
| Sitios de escritura que rutean por la columna cruda | **4** | **0** |
| Filas `agent_html_publish` con `status='failed'` y la firma `no usa Azure DevOps` | **2** (ids 56 y 57) | **no crece** (ver §5.F6: el 2 es histórico, no se borra) |
| K1 del gate `backend/scripts/gate_plan282.py` | **NO MEDIBLE por un bug de columna** | **medible, devuelve 2** |
| Centinela "ningún escritor lee la columna" | **no existe** | existe y está verde |

**Radio de impacto medido, exacto: 2 tickets de 228.** Se midió proyecto por proyecto
contra la BD viva:

| `stacky_project_name` | tickets | `issue_tracker.type` del config | ¿cambia el destino? |
|---|---|---|---|
| RIPLEY | 63 con `tracker_type='gitlab'` | `gitlab` | no (la columna ya coincide) |
| **RIPLEY** | **2 con `tracker_type='azure_devops'`** | **`gitlab`** | **SÍ — es todo el cambio** |
| RSPACIFICO | 57 | `azure_devops` | no |
| `p` | 49 | (sin config resoluble) | no — fail-closed a ADO |
| `P` | 44 | (sin config resoluble) | no — fail-closed a ADO |
| ONP | 6 | (sin config resoluble) | no — fail-closed a ADO |
| RSSICREA | 3 | `azure_devops` | no |
| `__demo__` | 3 con `tracker_type='demo'` | (sin config resoluble) | no — la columna no vale el default, gana ella |
| `test` | 1 | (sin config resoluble) | no — fail-closed a ADO |

---

## 2. Por qué ahora / el gap que cierra

### 2.1 Lo que el Plan 281 dejó cerrado (no lo repitas)

`docs/281_PLAN_EL_RUTEO_POR_TRACKER_DEJA_DE_MENTIR.md` cerró:

- **F3/F4/F5/F7** — ocho sitios ADO-only que ahora preguntan `tracker_is_azure_devops(project)`
  antes de construir el cliente. Vivos y verificables: `api/agents.py:1920`,
  `api/tickets.py:4944`, `api/tickets.py:7595`, `services/acceptance_criteria.py:44`,
  `services/business_preflight.py:94`, `services/self_review.py:58`,
  `services/similar_tickets.py:122`, `services/ticket_assigner.py:396`.
- **F6** — `services/run_ticket_refresh.py:46-58`, el primer sitio que dejó de leer la
  columna y pasó a preguntarle al config del proyecto. **Es el patrón que este plan
  generaliza.**
- **F7/F9** — el kill-switch `ruteo_estricto_por_tracker()` en
  `services/project_context.py:78-99`, default `True`.
- **F8** — el ratchet AST `scan_tracker_type_routing()` en
  `services/provider_coupling_audit.py:344`, con su test
  `tests/test_plan281_ratchet_ado_only.py:150-168`.

### 2.2 Lo que el Plan 282 dejó cerrado (no lo repitas)

`docs/282_PLAN_GITLAB_DEJA_DE_SER_UN_ADO_DISFRAZADO_PARIDAD_Y_FLUIDEZ.md` construyó
`services/comment_publish_router.py`, un adaptador **client-shaped** que envuelve al
provider de GitLab con la forma del cliente ADO, y lo cableó en
`services/ado_publisher.py:426-440`. Ese cableado **está bien** y no se toca. Lo que el
282 no arregló es **cómo ese router decide cuál es el tracker**: sigue leyendo la columna
cruda (`services/comment_publish_router.py:118-122`, decisión en `:142`).

### 2.3 El gap, con la evidencia abierta y verificada

**(a) La columna miente y no puede no mentir.** `backend/models.py:49`:

```python
tracker_type: Mapped[str | None] = mapped_column(String(40), default="azure_devops")
```

El valor `"azure_devops"` en esa columna es **indistinguible** de "nadie la seteó". En la
BD viva hay 0 filas con `tracker_type IS NULL` y 162 con `"azure_devops"` — de las cuales
2 pertenecen a RIPLEY, que es GitLab. Esto no es un dato sucio que se limpia: es una
propiedad del esquema. **Cualquier regla de precedencia que haga ganar a la columna
cuando dice `"azure_devops"` es un no-op que no arregla nada.** Ver §3, regla P2.

**(b) Los cuatro sitios que quedan.** Todos verificados abriendo el archivo el 2026-08-01:

| # | Sitio | Línea que lee la columna | Línea donde decide |
|---|---|---|---|
| 1 | `backend/services/tracker_write_router.py::_norm_tracker_type` | `:49` (`getattr`), def en `:48` | `:74` (`if ttype in _ADO_TRACKER_TYPES`) y `:86` (`if ttype == "gitlab"`); el `build_ado_client` está en `:79` |
| 2 | `backend/services/comment_publish_router.py::_norm_tracker_type` | `:119` (`getattr`), def en `:118` | `:142` y `:155` |
| 3 | `backend/services/completion_sync.py::_resolve_sync_and_project` | `:47` | `:49-54` |
| 4 | `backend/api/tickets.py::_tracker_type_for` | `:463`, def en `:461` | consumido por `_item_ref_for_ticket` en `:471-472` |

**(c) El resolvedor correcto ya existe y está bendecido.**
`backend/services/project_context.py:46-75`, `tracker_is_azure_devops(project_name)`, con
17 consumidores. Su docstring ya explica por qué **deliberadamente** no mira la columna.
Verificado en vivo: `tracker_is_azure_devops("RIPLEY")` → `False`,
`tracker_is_azure_devops("RSPACIFICO")` → `True`, `tracker_is_azure_devops(None)` → `True`.

**(d) El daño medido no es el que parece — leelo con cuidado.** Las 2 filas fallidas de
`agent_html_publish` (ids 56 y 57) son de los tickets `ado_id=1116` y `ado_id=1120`, y esos
dos tickets tienen `tracker_type='gitlab'`, **correcto**. O sea: **esas dos filas NO las
causó la columna mentirosa.** Las causó el publicador corriendo sin el ruteo del 282
(`triggered_by='output_watcher_mode_b'`, `published_at` `2026-08-01 16:16:42` y
`2026-08-01 20:24:43`; el fix del 282 se commiteó en `3461d0ce` a las `19:56:02`, así que
la segunda es de un proceso backend arrancado antes del fix y nunca reiniciado). El
mensaje se emite en `backend/services/ado_publisher.py:459`.

**Consecuencia para el implementador: este plan NO baja ese contador a 0.** Baja a 0 los
*sitios* que rutean por la columna, y deja el contador **congelado en 2 y medible**. Ver
§5.F6 y §6, riesgo R4.

**(e) Los dos falsos verdes que hacían todo esto invisible.** Este es el hallazgo más
importante del relevamiento y está **medido**, no inferido:

1. `tests/test_plan281_ratchet_ado_only.py:152-153` asserta
   `scan_tracker_type_routing() == []` y **pasa**. Se corrió: devuelve `[]`.
2. El detector es **ciego al idioma `getattr`**. Se comprobó con una sonda sintética: un
   módulo con dos funciones, una que rutea con `ticket.tracker_type` y otra que rutea con
   `getattr(ticket, "tracker_type", None) or "azure_devops"`. El detector marcó **solo la
   primera**. Los cuatro sitios de la tabla (b) usan **exactamente** el idioma que no ve.
3. Hay una **tercera** capa: aunque el detector viera `getattr`, su regla es
   *intra-función* (lee la columna y compara contra un literal **en la misma función**).
   Tres de los cuatro sitios parten eso en dos funciones (`_norm_tracker_type` lee,
   `resolve_*` compara), así que seguirían invisibles. Medido: con la regla extendida a
   `getattr`, el censo pasa de 0 a 8 sitios y **ninguno** de esos 8 es
   `_norm_tracker_type` ni `_tracker_type_for`.
4. Encima, `services/provider_coupling_audit.py:178-181` excluye
   `services/tracker_write_router.py` del censo por diseño.

**Por eso el gate de este plan NO es "arreglar `scan_tracker_type_routing`".** Ampliar esa
regla abre 8 hallazgos ajenos (fábricas de providers de CI, mayormente legítimas) y rompe
el contrato del Plan 281. El gate del 286 es un **centinela dirigido a los cuatro sitios
nombrados** (§5.F0), que es inmune a las tres capas de ceguera porque no infiere: mira
esos cuatro sitios y punto.

**(f) El gate que había que reusar está roto.** `backend/scripts/gate_plan282.py:202-203`
(dentro de `k1_publicaciones_fallidas`, def en `:184`) consulta:

```sql
SELECT COUNT(*) FROM agent_html_publish
WHERE status = 'failed' AND reason LIKE '%no usa Azure DevOps%'
```

La columna `reason` **no existe** en esa tabla. Las columnas reales son
`['id','execution_id','ticket_id','ado_id','html_path','html_sha256','status','ado_response','error_message','triggered_by','published_at','comment_id','marker']`.
Ejecutado contra la BD viva: `OperationalError: no such column: reason`. Ese error lo
traga el `except Exception` de `:207` y K1 devuelve `NO_MEDIBLE` **siempre**. El nombre
`reason` viene del campo del dataclass `PublishResult` (`ado_publisher.py:459`), que se
persiste en la columna `error_message`. Con `error_message`, la misma query devuelve **2**.

---

## 3. Principios y guardarraíles

- **P1 — Un solo helper, cuatro consumidores.** La precedencia se escribe **una vez**, en
  `services/project_context.py`, al lado del resolvedor canónico. Cuatro copias de un
  `if` son cuatro oportunidades de equivocarse (es el mismo argumento textual con el que
  el Plan 281 justificó centralizar `ruteo_estricto_por_tracker`, `project_context.py:88-90`).
- **P2 — "Columna explícita" tiene una definición dura, y es la clave del plan.**
  *Explícita* significa: **valor no vacío Y distinto de `_DEFAULT_TRACKER_TYPE`
  (`"azure_devops"`, `project_context.py:30`)**. Motivo en §2.3(a): el default del ORM hace
  que `"azure_devops"` sea ruido, no señal. Implementar `if columna: return columna` es un
  no-op que deja los 2 tickets rotos y **todos los tests que escribas van a pasar igual**.
- **P3 — El fail-closed a ADO se conserva tal cual.** `tracker_is_azure_devops` devuelve
  `True` sin nombre de proyecto o sin config resoluble (`project_context.py:63-65, 74-75`).
  Un ticket sin `stacky_project_name` sigue yendo a Azure DevOps. **Eso es el
  comportamiento de hoy, no una regresión, y no se "arregla" en este plan.** 100 de las
  162 filas `azure_devops` de la BD viva pertenecen a proyectos sin config resoluble
  (`p`=49, `P`=44, ONP=6, `test`=1) y dependen de ese fail-closed para no cambiar de
  destino.
- **P4 — Sin flags nuevas.** Ver §4.0.
- **P5 — No se escribe en la BD del operador.** Prohibido `UPDATE tickets SET tracker_type`,
  prohibido `DELETE FROM agent_html_publish`. Los 2 tickets sintéticos y las 2 filas
  fallidas son datos vivos. Un `UPDATE` además taparía el defecto en vez de arreglarlo: el
  próximo ticket sintético nacería igual de mentiroso.
- **P6 — `services/` nunca importa de `api/`.** Regla del repo, escrita en
  `services/completion_sync.py:93-95` y en el docstring de
  `services/tracker_write_router.py:7-11`. El helper vive en `services/`, así que
  `api/tickets.py` lo importa (esa dirección sí vale, y ya lo hace en `api/tickets.py:32-38`).
- **P7 — Backward-compatible por construcción.** Con el kill-switch apagado, los cuatro
  sitios se comportan byte-idéntico a hoy (§5.F1, caso borde 5).
- **P8 — Human-in-the-loop y mono-operador.** El plan no agrega decisiones al operador, no
  agrega pantallas, no agrega auth ni roles.

---

## 4. Decisiones transversales que valen para TODAS las fases

### 4.0 Flags: **ninguna nueva.** Se reusa `ruteo_estricto_por_tracker()`, default ON

No se registra ninguna flag. El kill-switch es el que **ya existe**:
`services/project_context.py:78-99`, `STACKY_TRACKER_ROUTING_STRICT_ENABLED`, **default
`True`** (fail-open a `True` si `config` no importa, `:98-99`), ya consumido por 8 sitios
del Plan 281 F7.

**Por qué alcanza y por qué es mejor que inventar una:**

- Su propósito documentado (`:81-84`) es literalmente *"apagada la flag, los sitios vuelven
  a construir el cliente de Azure DevOps como hoy"*. Es la misma semántica que necesita el 286.
- Se lee **una sola vez, adentro del helper**, así que los cuatro sitios quedan cubiertos
  por una sola palanca de rollback.
- Una flag nueva nacería ON (es solo lectura: resolver un string no escribe en ningún
  sistema real ni quema tokens en reposo), o sea que sería una flag ON redundante con otra
  flag ON que ya hace exactamente esto. Registrarla cuesta **siete patas**
  (`config.py`, `services/harness_flags.py`, sus dos tests de registro, el panel del
  frontend, `harness_defaults.env`, `_CURATED_DEFAULTS_ON`) a cambio de cero capacidad nueva.

**Instrucción dura:** si al implementar te dan ganas de agregar
`STACKY_TRACKER_EFECTIVO_ENABLED` o similar, **no lo hagas**. Está fuera de scope (§7).

### 4.1 Entorno y comandos exactos

Ambos venvs del backend tienen pytest 8.3.3 (verificado): `backend/.venv` = Python 3.13.5,
`backend/venv` = Python 3.11.9. **Usá `venv`**, que es el que usan los planes 281 y 282 en
sus comandos (`282_PLAN_...md:414, 632, 709, 795`).

Todos los comandos de este plan se corren **parado en `Stacky Agents/backend`**:

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_<archivo>.py -v
```

**Correr SIEMPRE por archivo, nunca `pytest tests` entero** (la suite completa tiene
contaminación cruzada conocida y no es un veredicto).

**Guard anti-falso-verde obligatorio en cada fase** — un archivo de test que no colecta
nada sale con exit 0 y parece verde:

```bash
./venv/Scripts/python.exe -m pytest tests/test_plan286_<archivo>.py --collect-only -q | tail -3
```

Tiene que imprimir un número de tests **mayor que cero** y coincidente con lo que la fase
declara.

### 4.2 Los tests nuevos NO tocan la BD ni la red

`backend/tests/conftest.py` **no aísla la base**: solo setea `STACKY_TEST_MODE`, bloquea el
egress de red no-loopback (`:30-53`) y protege los handlers de logging. Un test que importe
`db`, `app` o `models` escribe en la BD **real** del operador.

**Regla dura para los 3 archivos de test de este plan: no importan `db`, ni `app`, ni
`models`.** El ticket se representa con `types.SimpleNamespace` y el config del proyecto se
inyecta con `monkeypatch.setattr("project_manager.get_project_config", ...)` — que funciona
porque `tracker_is_azure_devops` resuelve `get_project_config` **por referencia en cada
llamada** (importe local, `project_context.py:57-61, 67`).

### 4.3 Ratchets: los 3 archivos nuevos se registran en LOS DOS

Los ratchets son `backend/scripts/run_harness_tests.ps1` y
`backend/scripts/run_harness_tests.sh`. Ambos hacen `cd` a `backend/` antes de correr, así
que las rutas se registran como `tests/...` — **sin espacios, sin prefijo `Stacky Agents/`**
(los ratchets no admiten rutas con espacios). Sintaxis distinta en cada uno: `.ps1` usa
comillas y coma final, `.sh` va pelado.

Se agregan **inmediatamente después del bloque del Plan 282**, que hoy ocupa
`run_harness_tests.ps1:906-909` y `run_harness_tests.sh:1012-1015` (ambos terminan en
`test_plan282_assignee_no_borra.py`). Diff exacto en §5.F0.

### 4.4 Impacto por runtime (Codex CLI / Claude Code CLI / GitHub Copilot Pro)

**Idéntico en los tres, en todas las fases, y no hace falta fallback.** Justificación
concreta, no genérica: los cuatro sitios corregidos viven en `services/` y `api/`, por
**debajo** de la bifurcación de runtime. Se los alcanza por caminos que no tienen código
por runtime: el post-hook común (`services/ticket_status.register_post_hook`), el
`output_watcher` y los endpoints HTTP. Se verificó en la BD viva que los `triggered_by` de
`agent_html_publish` son `legacy_auto_publish`, `output_watcher_mode_b`,
`output_watcher_mode_b_late` y `finish_work` — ninguno nombra un runtime.

Cada fase repite esta línea porque el criterio es por fase, pero el motivo es este y es el
mismo. **No hay que escribir ni un `if runtime == ...` en todo el plan.**

### 4.5 Trabajo del operador

**Ninguno, en todas las fases.** Sin migración, sin re-configurar proyectos, sin tocar
flags, sin pantallas nuevas, sin reinicio obligatorio (el cambio toma efecto en el próximo
arranque del backend, como cualquier cambio de código).

---

## 5. Fases

Orden por dependencia estricta: **F0 → F1 → F2 → F3 → F4 → F5 → F6**.
F0 nace ROJO a propósito y recién vuelve a verde en F5.

---

### F0 — El centinela que hoy está ROJO: los cuatro sitios leen la columna

**Objetivo (1 frase):** dejar escrito, como test, que los cuatro escritores nombrados leen
`ticket.tracker_type`, para que el resto del plan tenga un rojo real que apagar y para que
nadie pueda volver a meter esa lectura sin que un test lo grite.

**Valor:** convierte "hay 4 sitios malos" en un booleano ejecutable. Sin esto, las fases
F2-F4 son verdes por construcción y no prueban nada (§2.3(e): el ratchet existente ya es un
falso verde).

**Archivos:**
- crea `Stacky Agents/backend/tests/test_plan286_columna_no_rutea.py`
- modifica `Stacky Agents/backend/scripts/run_harness_tests.ps1`
- modifica `Stacky Agents/backend/scripts/run_harness_tests.sh`

**Nombres exactos:**
- función del censo: `lectores_de_la_columna(rutas: list[str]) -> list[str]`
- constante congelada: `SITIOS_VIGILADOS: tuple[tuple[str, str], ...]`
- tests: `test_ningun_sitio_vigilado_lee_la_columna`,
  `test_el_detector_ve_los_dos_idiomas` (calibración)

**Pseudocódigo (el archivo completo, salvo detalles de estilo):**

```python
"""Plan 286 F0 — Centinela DIRIGIDO: los cuatro escritores no leen la columna.

Por qué un centinela propio y no `scan_tracker_type_routing` (Plan 281 F8):
ese detector (a) es ciego al idioma `getattr(x, "tracker_type", ...)`, que es
justo el que usan los cuatro sitios, y (b) es intra-funcion, asi que no ve el
idioma "una funcion lee y otra compara". Medido el 2026-08-01: devuelve [] con
los cuatro sitios vivos. Ampliarlo abre 8 hallazgos ajenos y rompe el contrato
del Plan 281, asi que este centinela mira EXACTAMENTE los cuatro sitios.
"""
import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]

# (ruta relativa a backend/, nombre de la funcion). Lista CONGELADA: agregar un
# sitio nuevo es una decision del plan, no un efecto colateral.
SITIOS_VIGILADOS = (
    ("services/tracker_write_router.py",  "_norm_tracker_type"),
    ("services/comment_publish_router.py", "_norm_tracker_type"),
    ("services/completion_sync.py",        "_resolve_sync_and_project"),
    ("api/tickets.py",                     "_tracker_type_for"),
)


def _lee_la_columna(nodo) -> bool:
    """Los DOS idiomas: `x.tracker_type` y `getattr(x, "tracker_type", ...)`."""
    if isinstance(nodo, ast.Attribute) and nodo.attr == "tracker_type":
        return True
    if isinstance(nodo, ast.Call):
        fn = nodo.func
        if isinstance(fn, ast.Name) and fn.id == "getattr" and len(nodo.args) >= 2:
            a = nodo.args[1]
            return isinstance(a, ast.Constant) and a.value == "tracker_type"
    return False


def lectores_de_la_columna(rutas):
    """['<ruta>::<funcion>'] por cada sitio vigilado que lee la columna."""
    hallados = []
    for rel, nombre in rutas:
        path = _BACKEND / rel
        arbol = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if n.name != nombre:
                continue
            if any(_lee_la_columna(h) for h in ast.walk(n)):
                hallados.append(f"{rel}::{nombre}")
    return sorted(set(hallados))


def test_ningun_sitio_vigilado_lee_la_columna():
    vivos = lectores_de_la_columna(SITIOS_VIGILADOS)
    assert vivos == [], (
        f"estos escritores siguen ruteando por la columna que MIENTE: {vivos}. "
        f"Tienen que llamar a services.project_context.tracker_efectivo_de_ticket."
    )


def test_el_detector_ve_los_dos_idiomas(tmp_path):
    """El gate se corre CONTRA el defecto: si el detector no ve el idioma
    `getattr`, el test de arriba es un falso verde (le paso al Plan 281)."""
    (tmp_path / "sonda.py").write_text(
        "def por_atributo(t):\n"
        "    return t.tracker_type\n"
        "def por_getattr(t):\n"
        '    return getattr(t, "tracker_type", None)\n'
        "def limpia(t):\n"
        "    return t.stacky_project_name\n",
        encoding="utf-8",
    )
    global _BACKEND
    original, _BACKEND = _BACKEND, tmp_path
    try:
        marcadas = lectores_de_la_columna(
            (("sonda.py", "por_atributo"), ("sonda.py", "por_getattr"),
             ("sonda.py", "limpia"))
        )
    finally:
        _BACKEND = original
    assert marcadas == ["sonda.py::por_atributo", "sonda.py::por_getattr"]
```

> Nota de implementación: si te resulta más limpio, pasá `_BACKEND` como parámetro con
> default en vez de usar `global`. Lo innegociable es que la calibración corra como
> **assert**, no como paso manual, y que verifique **los dos** idiomas.

**Registro en los ratchets (diff exacto).** En
`Stacky Agents/backend/scripts/run_harness_tests.ps1`, después de la línea
`"tests/test_plan282_assignee_no_borra.py",`:

```powershell
  # Plan 286 - El ruteo de escritura le pregunta al proyecto, no a la columna.
  "tests/test_plan286_columna_no_rutea.py",
  "tests/test_plan286_tracker_efectivo.py",
  "tests/test_plan286_ruteo_de_escritura.py",
```

En `Stacky Agents/backend/scripts/run_harness_tests.sh`, después de
`tests/test_plan282_assignee_no_borra.py`:

```bash
  # Plan 286 - El ruteo de escritura le pregunta al proyecto, no a la columna.
  tests/test_plan286_columna_no_rutea.py
  tests/test_plan286_tracker_efectivo.py
  tests/test_plan286_ruteo_de_escritura.py
```

Los tres archivos se registran **acá, en F0**, aunque dos se creen en F1 y F2: así el
registro es un solo cambio y no se olvida. Los dos archivos que todavía no existen hacen
fallar al ratchet con "falta" hasta F2 — es esperado y está acotado al eje.

**Criterio de aceptación BINARIO:**

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -v
```

- `test_el_detector_ve_los_dos_idiomas` → **PASA** (el detector sirve).
- `test_ningun_sitio_vigilado_lee_la_columna` → **FALLA**, y el mensaje lista **exactamente
  estos 4**:
  `api/tickets.py::_tracker_type_for`, `services/comment_publish_router.py::_norm_tracker_type`,
  `services/completion_sync.py::_resolve_sync_and_project`,
  `services/tracker_write_router.py::_norm_tracker_type`.
- Resultado esperado: **1 failed, 1 passed**.

Si el segundo test pasa en F0, **el centinela está mal escrito** — no bajes la expectativa,
arreglá el detector.

Y el guard de colección:

```bash
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py --collect-only -q | tail -3
```
→ tiene que decir **2 tests**.

**Flag:** ninguna. Un test no se gatea.
**Impacto por runtime:** ninguno (es un test estático). Idéntico en los 3. Sin fallback.
**Trabajo del operador: ninguno.**

---

### F1 — El helper de tracker efectivo (sin consumidores todavía)

**Objetivo:** que exista **una** función que responda "a qué tracker le corresponde escribir
este ticket", con la precedencia escrita y testeada, antes de tocar ningún escritor.

**Valor:** separa la decisión difícil (la precedencia, §3.P2) de los cuatro reemplazos
mecánicos. Si esta fase está bien, F2-F4 son copy-paste.

**Archivos:**
- modifica `Stacky Agents/backend/services/project_context.py` (agrega dos funciones
  **inmediatamente después** de `ruteo_estricto_por_tracker`, que termina en `:99`)
- crea `Stacky Agents/backend/tests/test_plan286_tracker_efectivo.py`

**Nombres exactos:**
- `tracker_declarado_del_proyecto(project_name: str | None) -> str | None`
- `tracker_efectivo_de_ticket(ticket) -> str`

**No tocar `__all__`** (`project_context.py:440-447`): ni `tracker_is_azure_devops` ni
`ruteo_estricto_por_tracker` están ahí, y los imports de este plan son explícitos.

**Diff ilustrativo:**

```python
def tracker_declarado_del_proyecto(project_name: str | None) -> str | None:
    """Plan 286 — Tipo de tracker DECLARADO por el config del proyecto, o None.

    Hermano en minúscula de `tracker_is_azure_devops`: mismo origen de verdad
    (`issue_tracker.type`, lo que el operador setea por UI), mismo idioma de
    import local para seguir siendo interceptable con monkeypatch, misma
    defensa a prueba de todo. La diferencia es el retorno: acá hace falta el
    NOMBRE del tracker, no un booleano, porque el llamador tiene que rutear a
    GitLab, no solo descartar ADO.

    Devuelve None (no "azure_devops") cuando no se puede resolver: quien decide
    qué hacer con la ausencia es `tracker_efectivo_de_ticket`, en un solo lugar.
    """
    raw = (project_name or "").strip()
    if not raw:
        return None
    try:
        from project_manager import get_project_config as _get_cfg
        cfg = _get_cfg(raw) or {}
        tracker = cfg.get("issue_tracker") or {}
        declarado = (tracker.get("type") or "").strip().lower()
        return declarado or None
    except Exception:  # noqa: BLE001
        return None


def tracker_efectivo_de_ticket(ticket) -> str:
    """Plan 286 — A qué tracker le corresponde ESCRIBIR este ticket.

    PRECEDENCIA (este orden y no otro):

      1. La columna, SOLO si es EXPLÍCITA. Explícita = valor no vacío Y
         DISTINTO de `_DEFAULT_TRACKER_TYPE`. Motivo, y es el corazón del plan:
         `models.py:49` declara `default="azure_devops"`, así que ese valor en
         la columna es indistinguible de "nadie la seteó". Un valor como
         "gitlab", "jira", "mantis" o "demo" solo pudo escribirlo un sync a
         propósito: ese SÍ manda, y por eso gana incluso sobre el config (un
         ticket importado de Jira dentro de un proyecto ADO sigue siendo de
         Jira).
      2. El config del proyecto (`issue_tracker.type`). Es la fuente que el
         operador controla por UI y la que ya usan los 17 consumidores de
         `tracker_is_azure_devops`.
      3. `_DEFAULT_TRACKER_TYPE`. Fail-closed a Azure DevOps, IGUAL que hoy:
         un ticket sin `stacky_project_name` o de un proyecto sin config
         resoluble se comporta exactamente como antes de este plan. NO es una
         regresión y NO se "arregla" acá.

    Kill-switch: apagado `ruteo_estricto_por_tracker()` (Plan 281 F7), devuelve
    la columna cruda con el default de siempre — camino byte-idéntico al previo
    a este plan para los cuatro consumidores. No se registra flag nueva.

    NUNCA levanta y NUNCA devuelve cadena vacía.
    """
    bruto = getattr(ticket, "tracker_type", None)
    columna = bruto.strip().lower() if isinstance(bruto, str) else ""

    if not ruteo_estricto_por_tracker():
        return columna or _DEFAULT_TRACKER_TYPE

    if columna and columna != _DEFAULT_TRACKER_TYPE:
        return columna

    declarado = tracker_declarado_del_proyecto(
        getattr(ticket, "stacky_project_name", None)
    )
    if declarado:
        return declarado

    return _DEFAULT_TRACKER_TYPE
```

**Tests PRIMERO.** Archivo: `Stacky Agents/backend/tests/test_plan286_tracker_efectivo.py`.
Sin importar `db`/`app`/`models` (§4.2). Helper local:

```python
from types import SimpleNamespace

def _ticket(tracker_type=None, proyecto=None):
    return SimpleNamespace(tracker_type=tracker_type, stacky_project_name=proyecto)

def _con_config(monkeypatch, mapa):
    """mapa: {"RIPLEY": "gitlab", "RSPACIFICO": "azure_devops"}; ausente => None."""
    def _fake(nombre):
        tipo = mapa.get((nombre or "").strip().upper())
        return {"issue_tracker": {"type": tipo}} if tipo else None
    monkeypatch.setattr("project_manager.get_project_config", _fake)
```

Casos, **exactamente estos 11**:

| # | test | entrada | esperado | qué protege |
|---|---|---|---|---|
| 1 | `test_columna_mentirosa_pierde_contra_el_proyecto` | `tracker_type="azure_devops"`, proyecto `RIPLEY`(gitlab) | `"gitlab"` | **el caso de los 2 tickets. Si falla, el plan no sirve.** |
| 2 | `test_columna_vacia_cae_al_proyecto` | `tracker_type=None`, `RIPLEY` | `"gitlab"` | ausencia |
| 3 | `test_columna_explicita_no_default_gana_al_proyecto` | `tracker_type="jira"`, `RSPACIFICO`(ado) | `"jira"` | P2, rama 1 |
| 4 | `test_proyecto_ado_sigue_siendo_ado` | `tracker_type="azure_devops"`, `RSPACIFICO` | `"azure_devops"` | **no-regresión ADO** |
| 5 | `test_sin_proyecto_es_fail_closed_a_ado` | `tracker_type="azure_devops"`, `None` | `"azure_devops"` | P3 |
| 6 | `test_proyecto_sin_config_es_fail_closed_a_ado` | `tracker_type="azure_devops"`, `"p"` (sin config) | `"azure_devops"` | P3, las 100 filas |
| 7 | `test_get_project_config_que_explota_es_fail_closed` | `get_project_config` lanza `RuntimeError` | `"azure_devops"` | nunca levanta |
| 8 | `test_columna_con_espacios_y_mayusculas_se_normaliza` | `tracker_type="  GitLab  "`, proyecto ADO | `"gitlab"` | normalización |
| 9 | `test_columna_no_string_se_ignora` | `tracker_type=123`, `RIPLEY` | `"gitlab"` | el `isinstance` |
| 10 | `test_kill_switch_apagado_devuelve_la_columna_cruda` | flag OFF, `tracker_type="azure_devops"`, `RIPLEY` | `"azure_devops"` | P7 / rollback |
| 11 | `test_kill_switch_apagado_sin_columna_da_el_default` | flag OFF, `tracker_type=None`, `RIPLEY` | `"azure_devops"` | P7, rama vacía |

Para 10 y 11, apagar la flag con
`monkeypatch.setattr("config.config.STACKY_TRACKER_ROUTING_STRICT_ENABLED", False, raising=False)`
(se lee del **objeto** `config.config`, `project_context.py:95-97`, nunca con `os.getenv`).

**Cómo se comprueba que el rojo es rojo por la razón correcta:** escribí los 11 tests
**antes** de tocar `project_context.py` y corrélos: tienen que fallar todos con
`ImportError` / `AttributeError: tracker_efectivo_de_ticket`. Recién ahí implementá.

**Criterio de aceptación BINARIO:**

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_tracker_efectivo.py -v
```
→ **11 passed**. Y `--collect-only -q | tail -3` → **11 tests**.

Además, comprobación en vivo de que el helper contradice a la columna donde tiene que
contradecirla (read-only, no escribe nada):

```bash
./venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from types import SimpleNamespace
from services.project_context import tracker_efectivo_de_ticket as f
print(f(SimpleNamespace(tracker_type='azure_devops', stacky_project_name='RIPLEY')))
print(f(SimpleNamespace(tracker_type='azure_devops', stacky_project_name='RSPACIFICO')))
"
```
→ tiene que imprimir `gitlab` y después `azure_devops`.

**Flag:** ninguna nueva; el helper **lee** `ruteo_estricto_por_tracker()` (default ON).
**Impacto por runtime:** ninguno todavía (nadie lo llama). Idéntico en los 3. Sin fallback.
**Trabajo del operador: ninguno.**

---

### F2 — `tracker_write_router` deja de leer la columna

**Objetivo:** que el escritor de **estado** de tickets resuelva el destino con el helper.

**Valor:** es el sitio que el prompt del eje señala como el peor
(`tracker_write_router.py:74` → `:79` → `build_ado_client`), y el que termina en el
`AdoConfigError` de `project_context.py:365-367`.

**Archivos:**
- modifica `Stacky Agents/backend/services/tracker_write_router.py`
- crea `Stacky Agents/backend/tests/test_plan286_ruteo_de_escritura.py`

**Cambios exactos:**

1. **Borrar** `_norm_tracker_type` (`:48-52`) completo.
2. En `resolve_state_writer` (`:55`), reemplazar `ttype = _norm_tracker_type(ticket)`
   (`:72`) por:
   ```python
   from services.project_context import tracker_efectivo_de_ticket
   ttype = tracker_efectivo_de_ticket(ticket)
   ```
   El import va **adentro de la función**, siguiendo el idioma del archivo (`:70`, `:78`,
   `:87`) y para no ligar la referencia al importar el módulo.
3. En `preview_state_write` (`:166`), reemplazar
   `ttype = _norm_tracker_type(ticket) or "azure_devops"` (`:182`) por
   `ttype = tracker_efectivo_de_ticket(ticket)` (con el mismo import local).
   Beneficio lateral real: hoy el dry-run le reporta al operador `"azure_devops"` para un
   ticket de RIPLEY; pasa a reportar `"gitlab"`.
4. **No tocar** `_ADO_TRACKER_TYPES` (`:32`). El helper ya no devuelve `""`, pero dejar el
   `""` en el conjunto no cuesta nada y evita un cambio de contrato innecesario.
5. **Actualizar el docstring** de `resolve_state_writer` (`:56-69`): donde dice
   *"tracker_type ausente / azure_devops"* tiene que decir que el tracker sale de
   `tracker_efectivo_de_ticket`. Un docstring que describe el comportamiento viejo es una
   mina para el próximo lector.

**Equivalencia que hay que verificar y no dar por obvia:** hoy, un ticket sin la columna
produce `ttype == ""`, que cae en `_ADO_TRACKER_TYPES` y va a ADO. Con el helper produce
`"azure_devops"`, que cae en el **mismo** conjunto y va al **mismo** lugar. El
`StateWriter` resultante ya declaraba `tracker_type="azure_devops"` hardcodeado (`:84`).
Byte-idéntico.

**Tests PRIMERO** en `tests/test_plan286_ruteo_de_escritura.py` (mismos helpers de §F1;
`resolve_state_writer` se ejercita monkeypatcheando
`services.project_context.build_ado_client` y `services.tracker_provider.get_tracker_provider`
para que devuelvan centinelas, **sin construir clientes reales** — el conftest bloquea la
red igual):

| # | test | esperado |
|---|---|---|
| 1 | `test_ticket_de_ripley_con_columna_mentirosa_resuelve_gitlab` | `writer.kind == "provider"` y `writer.tracker_type == "gitlab"`; **`build_ado_client` NO se llamó** |
| 2 | `test_ticket_de_rspacifico_sigue_resolviendo_ado` | `writer.kind == "ado_client"`, `tracker_type == "azure_devops"` |
| 3 | `test_ticket_sin_proyecto_sigue_resolviendo_ado` | `kind == "ado_client"` (P3) |
| 4 | `test_ticket_sin_columna_en_proyecto_ado_resuelve_ado` | `kind == "ado_client"` |
| 5 | `test_preview_reporta_el_tracker_efectivo` | `preview_state_write(...)["tracker_type"] == "gitlab"` para el ticket de RIPLEY |
| 6 | `test_kill_switch_apagado_manda_el_ticket_mentiroso_a_ado` | flag OFF → `kind == "ado_client"` (rollback demostrado) |

El test 1 es el **rojo primero de todo el eje**: escribilo y corrélo **antes** de tocar
`tracker_write_router.py`. Con el código actual tiene que fallar mostrando
`kind == "ado_client"`. Si pasa antes del cambio, el test está mal armado (lo más probable:
el fake de `get_project_config` no se está aplicando).

Verificación explícita de "el rojo es por la razón correcta":

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py::test_ticket_de_ripley_con_columna_mentirosa_resuelve_gitlab -v
```
→ **1 failed** antes del cambio, **1 passed** después.

**Criterio de aceptación BINARIO:**
```bash
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -v
./venv/Scripts/python.exe -m pytest tests/test_plan270_write_router.py -v
./venv/Scripts/python.exe -m pytest tests/test_plan271_writer_routed.py tests/test_plan270_state_write_ratchet.py -v
```
→ el primero **6 passed**; los otros dos, **el mismo número de passed que antes del
cambio** (medilo antes: son los tests del Plan 270/271 sobre este mismo archivo y son la
red de no-regresión de esta fase). Si alguno se pone rojo, **no lo edites**: significa que
la equivalencia del punto 4 no se cumplió.

**Flag:** ninguna nueva; cubierto por `ruteo_estricto_por_tracker()` adentro del helper
(default ON). El flag propio del archivo, `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED`
(`:42-45`), **no se toca**: gobierna si el ruteo existe, no cómo se resuelve el tipo.
**Impacto por runtime:** idéntico en los 3 (§4.4). Sin fallback.
**Trabajo del operador: ninguno.**

---

### F3 — `comment_publish_router` deja de leer la columna

**Objetivo:** que el publicador de **comentarios** (el adaptador client-shaped del Plan 282)
resuelva el tracker con el helper.

**Valor:** es el camino de `ado_publisher.publish` → el que emite el
`"ADO client build failed: ... no usa Azure DevOps"` de `ado_publisher.py:459`. Con la
columna mentirosa, un ticket sintético de RIPLEY publica su HTML en Azure DevOps o falla.

**Archivos:** modifica `Stacky Agents/backend/services/comment_publish_router.py`; agrega
tests al archivo creado en F2.

**Cambios exactos:**
1. **Borrar** `_norm_tracker_type` (`:118-122`).
2. En `resolve_comment_publisher` (`:125`), reemplazar `ttype = _norm_tracker_type(ticket)`
   (`:140`) por el import local + `ttype = tracker_efectivo_de_ticket(ticket)`.
3. Actualizar el docstring (`:126-137`), primer bullet.
4. **No tocar** la rama ADO (`:142-153`): sigue llamando a
   `ado_publisher._client_for_ticket_project(...)` con su fallback, byte-idéntico.
5. **No tocar** `ado_publisher.py`. El cableado del Plan 282 (`:426-440`) está bien.

**Tests (se suman a `test_plan286_ruteo_de_escritura.py`), exactamente 3:**

| # | test | esperado |
|---|---|---|
| 7 | `test_comentario_de_ripley_con_columna_mentirosa_va_a_gitlab` | `publisher.kind == "gitlab_adapter"`; `ado_publisher._client_for_ticket_project` **no se llamó** |
| 8 | `test_comentario_de_rspacifico_sigue_yendo_a_ado` | `kind == "ado_client"` |
| 9 | `test_comentario_sin_proyecto_sigue_yendo_a_ado` | `kind == "ado_client"` |

El 7 también es rojo-primero: corrélo antes del cambio y confirmá que da `"ado_client"`.

**Criterio de aceptación BINARIO:**
```bash
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -v
./venv/Scripts/python.exe -m pytest tests/test_plan282_publicacion_comentario.py -v
```
→ **9 passed** en el primero; el segundo, **igual número de passed que antes** (es la
suite del Plan 282 sobre este mismo router).

**Flag:** ninguna nueva. `STACKY_COMMENT_PUBLISH_ROUTED_ENABLED` (`:108-115`) no se toca.
**Impacto por runtime:** idéntico en los 3 (§4.4). Sin fallback.
**Trabajo del operador: ninguno.**

---

### F4 — `completion_sync` y `api/tickets._tracker_type_for` dejan de leer la columna

**Objetivo:** cerrar los dos sitios que quedan, que son los más simples.

**Valor:** completa el barrido. Sin estos dos, el centinela de F0 sigue rojo y el eje no
cierra. `completion_sync` decide **qué sync corre** después de una completación
(`:49-54`); `_tracker_type_for` decide **qué `tracker_type` lleva el `ItemRef`** que se le
pasa al provider de CI (`api/tickets.py:471-472`).

**Archivos:**
- modifica `Stacky Agents/backend/services/completion_sync.py`
- modifica `Stacky Agents/backend/api/tickets.py`
- agrega tests al archivo de F2

**Cambio en `completion_sync.py::_resolve_sync_and_project` (`:40-55`):** reemplazar la
línea `:47` por

```python
    from services.project_context import tracker_efectivo_de_ticket
    tracker_type = tracker_efectivo_de_ticket(ticket)
```

Import **local** (el archivo ya usa ese idioma en `:50`, `:54`, `:61`, `:72`) y sobre todo
porque **`services/completion_sync.py` no puede importar de `api/`** y un import de módulo
al tope aumenta el riesgo de ciclo al arrancar el daemon (la regla está escrita en ese
mismo archivo, `:93-95`). El resto de la función queda igual: el `if tracker_type == "jira"`
/ `elif "mantis"` / `else` sigue tal cual, y **no hay que agregar una rama `gitlab`** acá —
la rama GitLab del sync ya existe más abajo, en `_do_project_sync` (`:116-119`, Plan 281 F5).

**Cambio en `api/tickets.py::_tracker_type_for` (`:461-463`):** reemplazar el cuerpo por
`return tracker_efectivo_de_ticket(ticket)` y agregar `tracker_efectivo_de_ticket,` al
bloque de import que **ya existe** en `api/tickets.py:32-38` (junto a
`ruteo_estricto_por_tracker` y `tracker_is_azure_devops`), respetando el orden alfabético
que el bloque ya trae. Actualizar el docstring de una línea (`:462`).

**Tests (se suman al archivo de F2), exactamente 4:**

| # | test | esperado |
|---|---|---|
| 10 | `test_completion_sync_de_ripley_no_elige_el_sync_de_ado` | `_resolve_sync_and_project(ticket_ripley_mentiroso)[2] == "gitlab"` |
| 11 | `test_completion_sync_de_rspacifico_elige_ado` | `[2] == "azure_devops"` y la callable es `services.ado_sync.sync_tickets` |
| 12 | `test_item_ref_de_ripley_declara_gitlab` | `_tracker_type_for(ticket_ripley_mentiroso) == "gitlab"` |
| 13 | `test_item_ref_de_rspacifico_declara_ado` | `== "azure_devops"` |

**Cuidado con el import de `api/tickets.py`:** importar ese módulo arrastra medio backend.
Si el import resulta pesado o toca la BD, **no lo importes**: reemplazá los tests 12 y 13
por una verificación AST equivalente (que `_tracker_type_for` no lea la columna y sí llame
a `tracker_efectivo_de_ticket`) — el centinela de F0 ya cubre la mitad. Decidilo midiendo,
no adivinando:
`./venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); import api.tickets"`
tiene que terminar sin error y sin escribir en `backend/data/`.

**Criterio de aceptación BINARIO:**
```bash
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -v
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -v
```
→ **13 passed** en el primero. En el segundo, **2 passed**: el centinela de F0 pasa a
**VERDE** acá. Ese es el hito real del eje.

**Flag:** ninguna nueva.
**Impacto por runtime:** idéntico en los 3 (§4.4). Sin fallback.
**Trabajo del operador: ninguno.**

---

### F5 — El ratchet del Plan 281 deja de mirar el lugar equivocado

**Objetivo:** sacar `services/tracker_write_router.py` de la lista de exclusión del censo
de acoplamiento, ahora que ese archivo ya no tiene nada que esconder.

**Valor:** cierra el riesgo R2 (§6). Mientras ese archivo esté excluido, cualquier
reincidencia futura ahí es invisible para el ratchet: falso verde permanente.

**Archivos:** modifica `Stacky Agents/backend/services/provider_coupling_audit.py`.

**Cambio exacto** (`:177-181`):

```python
# Archivos donde `<algo>.tracker_type` ES la verdad resuelta, no la columna.
# Plan 286 F5 — `services/tracker_write_router.py` SALE de esta lista: desde el
# Plan 286 ese archivo no lee la columna (resuelve con
# `project_context.tracker_efectivo_de_ticket`), así que la exención sobraba y
# solo servía para que una reincidencia futura pasara sin ser vista.
# `services/project_context.py` SE QUEDA: ahí la columna se lee A PROPÓSITO, es
# el lugar donde vive el resolvedor.
_ROUTING_EXCLUDED_FILES: frozenset[str] = frozenset({
    "services/project_context.py",
})
```

También actualizar el párrafo "EXCLUYE POR ARCHIVO" del docstring de
`scan_tracker_type_routing` (`:369-371`), que hoy nombra los dos archivos.

**Efecto medido antes de hacerlo (para que no haya sorpresa): CERO.** Se corrió
`scan_tracker_type_routing()` con la exclusión ya quitada y la regla actual del detector:
devuelve `[]`. O sea, esta fase **no puede** poner rojo el ratchet del 281. Es una
limpieza de cobertura sin riesgo.

**Criterio de aceptación BINARIO:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan281_ratchet_ado_only.py -v
./venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from services.provider_coupling_audit import _ROUTING_EXCLUDED_FILES, scan_tracker_type_routing
assert 'services/tracker_write_router.py' not in _ROUTING_EXCLUDED_FILES
assert scan_tracker_type_routing() == []
print('F5 OK')
"
```
→ el pytest, **mismo número de passed que antes** (todos verdes); el snippet imprime
`F5 OK`.

**Flag:** ninguna. Un ratchet no se gatea.
**Impacto por runtime:** ninguno (análisis estático). Idéntico en los 3. Sin fallback.
**Trabajo del operador: ninguno.**

---

### F6 — El KPI se vuelve medible: el gate del 282 consulta la columna que existe

**Objetivo:** que `k1_publicaciones_fallidas` deje de devolver `NO_MEDIBLE` por un nombre de
columna equivocado, y congelar la línea base **2** sin tocar un solo dato.

**Valor:** sin esto, el KPI principal del eje no se puede leer y "0 fallas" es
indistinguible de "el gate está roto". Es un fix de una palabra con un test que lo protege.

**Archivos:**
- modifica `Stacky Agents/backend/scripts/gate_plan282.py`
- agrega **1** test al archivo `tests/test_plan286_columna_no_rutea.py`

**Cambio exacto** (`gate_plan282.py:200-204`): `reason` → `error_message`.

```python
            filas = s.execute(
                text(
                    "SELECT COUNT(*) FROM agent_html_publish "
                    # Plan 286 F6 — la columna es `error_message`. `reason` es el
                    # campo del dataclass PublishResult (ado_publisher.py:459), NO
                    # la columna: con `reason` esto tiraba
                    # `OperationalError: no such column` y K1 devolvía NO MEDIBLE
                    # SIEMPRE, tapado por el `except Exception` de abajo.
                    "WHERE status = 'failed' AND error_message LIKE '%no usa Azure DevOps%'"
                )
            ).scalar()
```

**Test que lo protege** (`test_el_gate_282_consulta_una_columna_que_existe`): estático, no
toca la BD. Lee `scripts/gate_plan282.py` como texto y asserta que en el SQL de
`agent_html_publish` aparece `error_message` y **no** aparece `reason`. Motivo de que sea
estático: un test que abriera `session_scope` escribiría en la base del operador (§4.2).

**Qué NO hay que hacer, y es la trampa de esta fase.** El contador da **2** y esas 2 filas
son **históricas** (§2.3(d)): son de antes de que el fix del Plan 282 estuviera corriendo, y
sus tickets tienen la columna **correcta**. Este plan **no las hace desaparecer**.

- **PROHIBIDO** `DELETE FROM agent_html_publish ...` para "llegar a 0".
- **PROHIBIDO** `UPDATE tickets SET tracker_type='gitlab' WHERE ado_id IN (-7,-1)`.
- La meta del KPI es **"no crece"**: la línea base queda documentada en **2** y cualquier
  fila nueva con esa firma es una regresión del eje.

**Criterio de aceptación BINARIO:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -v
./venv/Scripts/python.exe -c "
import sqlite3
c = sqlite3.connect('file:data/stacky_agents.db?mode=ro', uri=True)
print(c.execute(
  \"SELECT COUNT(*) FROM agent_html_publish WHERE status='failed' \"
  \"AND error_message LIKE '%no usa Azure DevOps%'\").fetchone()[0])
"
```
→ el pytest, **3 passed** (los 2 de F0 más este); el snippet imprime **2** sin excepción.
Fijate en el `mode=ro`: la verificación es **read-only por construcción**, no por promesa.

Opcionalmente, el gate completo: `./venv/Scripts/python.exe scripts/gate_plan282.py --json`
→ K1 tiene que salir **2**, no `NO MEDIBLE`. Ojo: ese script importa `db`, así que **puede
inicializar la base real**; si no querés ese riesgo, alcanza con el snippet `mode=ro`.

**Flag:** ninguna. Un script de gate no se gatea.
**Impacto por runtime:** ninguno (herramienta de medición). Idéntico en los 3. Sin fallback.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

**R1 — El fail-closed a `True` deja tickets sin proyecto yendo a ADO.**
`tracker_is_azure_devops` y `tracker_efectivo_de_ticket` devuelven Azure DevOps cuando no
hay `stacky_project_name` o el config no resuelve (`project_context.py:63-65, 74-75`).
*Es el comportamiento de HOY, medido: 100 de las 162 filas `azure_devops` de la BD viva son
de proyectos sin config resoluble.* **Mitigación: ninguna, es deliberado.** Cambiarlo
movería 100 tickets de destino en un plan que declara un radio de 2. Está en §7.
*Instrucción al implementador: si te tienta "arreglarlo", no. Rompés el plan.*

**R2 — Cambiar el ruteo sin actualizar la exclusión del censo deja un falso verde.**
`provider_coupling_audit.py:178-181` excluye `tracker_write_router.py`. **Mitigación: F5**,
con efecto medido = 0 y criterio binario. *Adicional, y es peor que R2: el detector del
Plan 281 ya era un falso verde antes de este plan por ser ciego a `getattr` (§2.3(e)). Por
eso el gate real del eje es el centinela dirigido de F0, no ese ratchet.*

**R3 — Romper Azure DevOps.** RSPACIFICO (57 tickets) y RSSICREA (3) son proyectos ADO
reales. **Mitigación:** tests de no-regresión explícitos en cada fase que toca ruteo (F1#4,
F2#2, F3#8, F4#11/#13), más correr las suites de origen (`test_plan270_write_router.py`,
`test_plan271_writer_routed.py`, `test_plan282_publicacion_comentario.py`) y exigir el
**mismo número de passed que antes**. Más el kill-switch `ruteo_estricto_por_tracker()`
como rollback de una sola palanca, con su propio test (F1#10, F2#6).

**R4 — Creer que el eje baja el contador de fallas a 0.** No lo baja: las 2 filas son
históricas y de tickets con la columna correcta (§2.3(d)). **Mitigación:** el KPI está
declarado como **"no crece"**, F6 prohíbe explícitamente el `DELETE`/`UPDATE`, y la causa
real de esas 2 (proceso backend viejo sin el fix del 282) queda escrita acá para que nadie
la re-descubra.

**R5 — Implementar `if columna: return columna` y creer que está hecho.** Es el error más
probable del eje, y es silencioso: los tests que uno escribiría "naturalmente" pasan igual.
**Mitigación:** §3.P2 con la evidencia de `models.py:49`, el test F1#1 nombrado como *"si
falla, el plan no sirve"*, y el centinela F0 que igual quedaría rojo... **no**: F0 quedaría
**verde** con esa implementación (el sitio ya no lee la columna). *El único que atrapa este
error es F1#1 y F2#1.* No los saltees ni los debilites.

**R6 — Un ticket importado de otro tracker dentro de un proyecto ADO.** La precedencia hace
ganar a la columna cuando dice `"jira"` o `"mantis"` aunque el proyecto declare
`azure_devops` (F1#3). Es **intencional**: ese valor solo pudo escribirlo un sync a
propósito. *Si en el futuro se decide que el proyecto gana siempre, es otro plan y hay que
medir el radio de nuevo.*

**R7 — Una sesión paralela tiene tomado el árbol.** Al escribir este plan había 8 archivos
sucios sin commitear de otra sesión (entre ellos `services/epic_autopublish.py` y
`frontend/src/api/endpoints.ts`). **Mitigación:** ninguno de los archivos de este plan está
en esa lista; commitear **siempre con pathspec explícito**
(`git commit -- "Stacky Agents/backend/services/project_context.py" ...`), nunca
`git commit -a`. Prohibido `stash`, `reset`, `rebase`, `amend`.

**R8 — El ratchet queda rojo entre F0 y F4.** F0 registra tres archivos de test, dos de los
cuales no existen hasta F1/F2, y su propio test nace rojo a propósito. **Mitigación:** es
un rojo **acotado al eje y esperado**; el DoD (§9) exige verde. No commitees F0 solo como
si fuera un entregable cerrado: F0 sin F4 es deuda.

---

## 7. Fuera de scope (explícito)

1. **Cambiar el fail-closed a ADO.** Ver R1.
2. **Cualquier `UPDATE`/`DELETE`/migración sobre la BD del operador**, incluidos los 2
   tickets sintéticos y las 2 filas fallidas.
3. **Cambiar el default de `Ticket.tracker_type` en `models.py:49`.** Sería la solución de
   raíz, pero toca el esquema, exige backfill y su radio no está medido. Candidato a un
   plan futuro.
4. **Ampliar `scan_tracker_type_routing` para que vea `getattr`.** Medido: abre 8 hallazgos
   ajenos (`api/devops_production.py::_do_ensure`, `api/tickets.py::_sync_via_provider_or_ado`,
   `services/ci_logs_provider.py::get_ci_logs_provider`,
   `services/ci_preflight.py::get_preflight_provider`, `services/ci_provider.py::get_ci_provider`,
   `services/ci_variables.py::get_variables_provider`,
   `services/completion_sync.py::_resolve_sync_and_project`,
   `services/tracker_provider.py::get_tracker_provider`) que son mayormente fábricas
   legítimas, y ni siquiera atrapa 3 de los 4 sitios de este eje por ser una regla
   intra-función. Es un plan propio.
5. **Agregar `tracker_efectivo_de_ticket` a `_ORIGENES_RESUELTOS`**
   (`provider_coupling_audit.py:173-176`). Se evaluó: es innecesario, porque esa lista solo
   aplica a `<llamada>().tracker_type` y el helper no devuelve un objeto con ese atributo.
   No lo agregues.
6. **Paridad GitLab en general** (tableros, estados, épicas, adjuntos): planes 276-282.
7. **Frontend.** Ni un `.tsx`, ni un `.ts`. El helper es backend puro.
8. **Flags nuevas de cualquier tipo.** Ver §4.0.
9. **Los otros 36 lectores de la columna** del backend (censo medido: 40 funciones leen
   `tracker_type`). La enorme mayoría son legítimos: serializar (`models.py::to_dict`),
   armar claves de identidad (`api/tickets.py::_clave`), o **escribir** la columna en el
   sync (`services/gitlab_sync.py::_upsert_ticket_gitlab`). Este plan toca **4**.

---

## 8. Glosario

- **La columna** — `tickets.tracker_type`, `backend/models.py:49`, `default="azure_devops"`.
  Miente por diseño, no por dato sucio.
- **El config del proyecto** — `issue_tracker.type` en
  `backend/projects/<NOMBRE>/config.json`. Lo setea el operador por UI. Es la fuente de
  verdad. Verificado: `backend/projects/RIPLEY/config.json` declara `"type": "gitlab"`.
- **Tracker efectivo** — lo que devuelve `tracker_efectivo_de_ticket`: el resultado de
  aplicar la precedencia de §3.P2.
- **Columna explícita** — valor no vacío **y distinto de `"azure_devops"`**. Nada más
  cuenta como explícito.
- **Fail-closed a ADO** — sin proyecto o sin config resoluble, se asume Azure DevOps.
  Comportamiento previo, conservado.
- **Centinela dirigido** — el gate de F0: mira 4 sitios nombrados en vez de inferir sobre
  todo el backend. Inmune a las 3 capas de ceguera del detector del Plan 281.
- **`NO MEDIBLE`** — sentinela de `gate_plan282.py:30`. **No es un 0.** Un gate que devuelve
  `NO MEDIBLE` no falla, y por eso puede tapar un bug durante semanas (§2.3(f)).
- **Client-shaped** — un adaptador que expone la forma del cliente ADO envolviendo otro
  provider. Es lo que construyó el Plan 282 en `comment_publish_router.py`.

---

## 9. Orden de implementación y Definición de Hecho

### Orden (estricto)

| Fase | Qué entrega | Rojo→Verde |
|---|---|---|
| F0 | Centinela dirigido + registro en los 2 ratchets | nace **ROJO** (1 failed, 1 passed) |
| F1 | `tracker_declarado_del_proyecto` + `tracker_efectivo_de_ticket` | 11 passed |
| F2 | `tracker_write_router` usa el helper | 6 passed + suites 270/271 sin cambio |
| F3 | `comment_publish_router` usa el helper | 9 passed + suite 282 sin cambio |
| F4 | `completion_sync` + `api/tickets._tracker_type_for` usan el helper | 13 passed y **F0 pasa a VERDE** |
| F5 | Sale la exclusión de `tracker_write_router` del censo | ratchet 281 sin cambio |
| F6 | `gate_plan282` K1 medible (`error_message`) | 3 passed y K1 = 2 |

Commit por fase, con pathspec explícito. Mensaje sugerido:
`feat(plan-286): F<N> — <qué hace>`.

### Definición de Hecho

- [ ] `tests/test_plan286_columna_no_rutea.py` → **3 passed** (F0 verde + el test de F6).
- [ ] `tests/test_plan286_tracker_efectivo.py` → **11 passed**.
- [ ] `tests/test_plan286_ruteo_de_escritura.py` → **13 passed**.
- [ ] Los 3 archivos figuran en `run_harness_tests.ps1` **y** en `run_harness_tests.sh`,
      como `tests/...` sin espacios.
- [ ] `--collect-only -q` de cada archivo imprime el número declarado (**nunca 0**).
- [ ] Suites de no-regresión con **el mismo número de passed que antes del eje**:
      `test_plan270_write_router.py`, `test_plan270_state_write_ratchet.py`,
      `test_plan271_writer_routed.py`, `test_plan282_publicacion_comentario.py`,
      `test_plan281_ratchet_ado_only.py`.
- [ ] `scan_tracker_type_routing()` sigue devolviendo `[]` y
      `'services/tracker_write_router.py' not in _ROUTING_EXCLUDED_FILES`.
- [ ] En vivo: `tracker_efectivo_de_ticket(SimpleNamespace(tracker_type='azure_devops',
      stacky_project_name='RIPLEY'))` → `'gitlab'`; con `'RSPACIFICO'` → `'azure_devops'`.
- [ ] El contador `error_message LIKE '%no usa Azure DevOps%'` medido con `mode=ro` sigue
      en **2** (no bajó porque no se borró nada, no subió porque no hay regresión).
- [ ] **Cero flags nuevas** registradas: `git diff` no toca `config.py` ni
      `services/harness_flags.py`.
- [ ] **Cero escrituras en la BD**: `git status` no muestra `backend/data/` modificado y no
      se ejecutó ningún `UPDATE`/`DELETE`.
- [ ] **Cero archivos de la sesión paralela tocados** (§6.R7).
- [ ] Los docstrings de `resolve_state_writer`, `resolve_comment_publisher` y
      `scan_tracker_type_routing` describen el comportamiento **nuevo**.

---

## Anexo — Anclajes verificados el 2026-08-01

Todos abiertos y confirmados contra el árbol en `docs/plan-279`. Los anclajes de línea
caducan: **anclá por símbolo** y confirmá antes de editar.

| Anclaje | Estado |
|---|---|
| `services/tracker_write_router.py:32` `_ADO_TRACKER_TYPES` | OK exacto |
| `services/tracker_write_router.py:48-52` `_norm_tracker_type` | OK (def en `:48`) |
| `services/tracker_write_router.py:74` / `:79` | OK exactos |
| `services/comment_publish_router.py:119` | OK — es el `getattr`; def en `:118`, decisión en `:142` |
| `services/completion_sync.py:47` | OK exacto |
| `api/tickets.py:463` | OK exacto (def `_tracker_type_for` en `:461`) |
| `services/project_context.py:46` `tracker_is_azure_devops` | OK exacto |
| `services/project_context.py:78` `ruteo_estricto_por_tracker` | OK exacto |
| `services/provider_coupling_audit.py:178-181` `_ROUTING_EXCLUDED_FILES` | OK exacto (el archivo a sacar, en `:180`) |
| `backend/scripts/gate_plan282.py:202` | OK — es la línea del `SELECT`; la función es `k1_publicaciones_fallidas`, def en `:184`. **Pero la query está ROTA** (§2.3(f)) |
| `backend/models.py:49` `default="azure_devops"` | OK exacto |
| `services/run_ticket_refresh.py:46-58` (patrón del Plan 281 F6) | OK exacto |
| `services/ado_publisher.py:459` (emisor del mensaje) | OK exacto |
| `services/ado_publisher.py:426-440` (cableado del Plan 282) | OK exacto |
| `api/tickets.py:32-38` (bloque de import de `project_context`) | OK exacto |
| `run_harness_tests.ps1:906-909` / `.sh:1012-1015` (bloque del Plan 282) | OK exactos |

**Correcciones a la evidencia de partida del eje** (todas medidas, no inferidas):

1. Las 2 filas fallidas de `agent_html_publish` son de `ado_id` **1116 y 1120**, cuyos
   tickets tienen `tracker_type='gitlab'` **correcto** — no son los sintéticos `-7`/`-1`.
2. La columna del KPI es **`error_message`**, no `reason`; el gate del 282 usa `reason` y
   por eso está roto.
3. El detector `scan_tracker_type_routing` es **ciego a `getattr`** e **intra-función**:
   devuelve `[]` con los 4 sitios vivos. Comprobado con sonda sintética.
4. Sacar la exclusión de `tracker_write_router.py` tiene efecto **cero** hoy (medido).
5. `backend/projects/RIPLEY/config.json` **existe** y declara `gitlab` — el helper tiene de
   dónde resolver. (`PROJECTS_DIR` resuelve a
   `Stacky Agents/backend/projects`, y `N:` / `C:\desarrollo` son el mismo directorio.)
