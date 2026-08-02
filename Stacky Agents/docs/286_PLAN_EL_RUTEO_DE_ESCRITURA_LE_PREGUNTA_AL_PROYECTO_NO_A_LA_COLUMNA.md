# Plan 286 — El ruteo de escritura deja de preguntarle a la columna y le pregunta al proyecto

**Estado:** MEJORADO — **v1 -> v2** (veredicto de la v1: **RECHAZADO**, 5 bloqueantes)
**Eje:** corrección de ruteo por tracker — continuación directa del Plan 281
**Fecha:** 2026-08-01 (v1) / 2026-08-02 (v2)
**Rama al escribir:** `docs/plan-279`
**Alcance:** backend. Cero frontend. Cero flags nuevas. Cero migraciones de datos.

`Juez v2: subagente independiente, misma corrida, contexto limpio`

---

## ESTADO DE IMPLEMENTACIÓN (v2, rama `docs/plan-279`, 2026-08-02)

| Fase | Estado | Evidencia real (output pegado) |
|---|---|---|
| F0 | **IMPLEMENTADA** | `test_plan286_columna_no_rutea.py` nace **`2 failed, 2 passed`** (4 collected), y las dos patas listan **exactamente** los 4 sitios. Ratchets: parity **12 passed**, meta **4 passed** |
| F1 | **IMPLEMENTADA** | Rojo previo real: `ImportError: cannot import name '_reset_memo_tracker_declarado'`. Después: **`14 passed`** (14 collected). En vivo: RIPLEY→`gitlab`, RSPACIFICO→`azure_devops`. Perf **`108 us/llamada`** (bar < 400, línea base sin memo 1.057) |
| F2 | **IMPLEMENTADA** | Rojo previo real, los 2 predichos: `#1 assert 'ado_client' == 'provider'`, `#5 assert 'azure_devops' == 'gitlab'`. Después **`6 passed`** (6 collected). No-regresión exacta: 270→**14**, 271→**13**, ratchet 270→**6**, 281 sitios→**18**. Ratchets: parity **12**, meta **4 passed** |
| F3 | **IMPLEMENTADA, con UN rojo ajeno declarado (ver C12)** | Rojo previo real: `#7 assert 'ado_client' == 'gitlab_adapter'`. Después **`9 passed`** (9 collected). **PERO** `test_plan282_publicacion_comentario.py` pasa de **`7 passed`** a **`1 failed, 6 passed`** — y el que falla estaba **congelando el defecto**. No se tocó. Ver C12 |
| F4 | **IMPLEMENTADA — hito del eje** | Rojo previo real: `#10` y `#12`, los dos `assert 'azure_devops' == 'gitlab'`. Después **`13 passed`**. **F0 pasa a `4 passed`: las DOS patas verdes.** 281 sitios sigue en **18**. Censo `getattr`-extendido **8 → 7**, sin `completion_sync::_resolve_sync_and_project`. El import de `api.tickets` NO creó la base (verificado: el archivo no existe) |
| F5 | **IMPLEMENTADA** | `test_plan281_ratchet_ado_only.py` **`11 passed`**, `test_plan281_sitios_ado_only.py` **`18 passed`**, y el snippet imprime **`F5 OK`** (`scan_tracker_type_routing() == []` con la exclusión reducida a `project_context.py`). Efecto medido: cero, como predijo el plan |
| F6 | pendiente | |
| F7 | pendiente | |

> **Corrección de baseline medida al implementar (§4.6).** `test_harness_ratchet_meta.py`
> ya **no** está `1 failed, 3 passed`: da **`4 passed`**. El rojo de fábrica ajeno
> (`test_allowlist_no_se_solapa_con_ratchet`, `tests/test_docs_api.py` duplicado) lo saldó
> el Plan 285 en `91e461fa` *("saldo del 4to rojo de fabrica")*, **posterior** a la medición
> de la v2. El criterio de este eje sobre esa suite pasa a ser **`4 passed`** — más
> estricto, no más laxo. §7.12 sigue valiendo: no se tocó nada de eso acá.
>
> **Baseline extra medido:** `test_error_fingerprints_catalog.py` = **`3 failed, 5 passed`**
> de fábrica (`test_campos_obligatorios` y `test_self_test_coherente` por
> `PLAN239-OUTLET-EN-BLANCO` sin `self_test`; `test_status_enum` porque `guarded` **no está**
> en el enum del test aunque sí esté en uso en el catálogo). F7 debe conservar ese número.

### C12 — BLOQUEANTE NUEVO, encontrado al implementar F3. El juez v2 no lo vio.

**`tests/test_plan282_publicacion_comentario.py::test_ado_sigue_publicando_igual_que_hoy`
estaba CONGELANDO el defecto que este plan mata, y contradice frontalmente al test F3#7
del propio plan.** No es una regresión de F3: es una contradicción que el plan no detectó.

La evidencia, ejecutada:

```
FAILED tests/test_plan282_publicacion_comentario.py::test_ado_sigue_publicando_igual_que_hoy
E       AssertionError: assert 'gitlab_adapter' == 'ado_client'
```

El mecanismo, verificado abriendo el archivo:

- `_TicketFalso.__init__` declara **`stacky_project_name="RIPLEY"` como default**
  (`tests/test_plan282_publicacion_comentario.py:22-23`).
- `_preparar` (`:97-127`) monkeypatchea `session_scope`, `_emit_and_persist`,
  `read_and_validate` y demás — pero **NO** `project_manager.get_project_config`.
- Por lo tanto el helper de F1 lee el **config REAL de disco**,
  `backend/projects/RIPLEY/config.json`, que declara **`"type": "gitlab"`** (Anexo A, punto 5).
- O sea: ese test asserta que un ticket de **RIPLEY** (proyecto GitLab) con la columna en
  el default mentiroso `azure_devops` (`models.py:49`) publica su comentario en **Azure
  DevOps**. **Eso es exactamente el defecto de §1**, escrito como aserción verde.

**Es irreconciliable con el plan, no con mi implementación.** El test F3#7 de este documento
(`test_comentario_de_ripley_con_columna_mentirosa_va_a_gitlab`) es **el mismo input**
—RIPLEY + columna `azure_devops`— con el resultado **opuesto**. Los dos no pueden estar
verdes a la vez. El baseline `7 passed` de §4.6 se midió **antes** del cambio y nunca se
cruzó contra la semántica que el propio plan introduce.

**Qué hice: NADA sobre el test ajeno.** §4.6 dice *"no edites el test ajeno"* y §7 no
autoriza tocarlo. Queda **rojo y declarado**, no tapado, no `skip`, no `xfail`.

**Decisión que le queda al operador (human-in-the-loop), con el fix de una línea:** la
intención de ese test la declara su propio nombre y su comentario interno
(*"El router clasifica ADO como ADO y devuelve el cliente de siempre"*): valida el **camino
ADO**, no a RIPLEY. Su dependencia de RIPLEY es un accidente del default de `_TicketFalso`.
El arreglo que **preserva la intención** es apuntar ese caso a un proyecto que de verdad sea
ADO:

```python
    ticket = _TicketFalso(tracker_type="azure_devops", stacky_project_name="RSPACIFICO")
```

Con eso el caso vuelve a probar lo que dice probar y deja de depender del bug. **No lo
apliqué**: cambia un archivo de otro eje y esa es una decisión de alcance del operador.

---

## CHANGELOG v1 -> v2

Las cinco afirmaciones medibles de la v1 se **reprodujeron ejecutando**, y las cinco
resultaron **CONFIRMADAS** (§Anexo B). El plan fue rechazado igual: los bloqueantes no
estaban en la evidencia, estaban en los **mecanismos** que la evidencia sostenía.

| # | Severidad | Qué estaba mal | Dónde se corrige |
|---|---|---|---|
| **C1** | BLOQUEANTE | El centinela de F0 vigila `(archivo, función)` y F2/F3 **borran** las dos funciones vigiladas ⇒ desde F4 queda verde **por ausencia de la función**, no por ausencia del defecto. Es el mismo falso verde que el plan le imputa al ratchet del 281. | §5.F0 reescrita: ausencia **+ presencia** + calibración del rename |
| **C2** | BLOQUEANTE | F0 registraba en los dos ratchets **3** archivos, 2 inexistentes hasta F1/F2. Medido: eso pone **rojas dos suites ajenas hoy verdes** (`test_harness_ratchet_meta::test_ratchet_no_referencia_archivos_inexistentes`, `test_plan259_ratchet_script_parity::test_ninguna_ruta_apunta_a_un_archivo_inexistente`). | §4.3 y §5.F0/F1/F2: **registro por fase**, en el commit que crea el archivo |
| **C3** | BLOQUEANTE | F6 dejaba K1 en **2** contra una meta **0 hardcodeada** en `gate_plan282.py` (`v != 0`, y el rótulo `(meta 0)`) ⇒ el gate del 282 pasaba de `exit 5` a **`exit 2` para siempre**, sin salida legal (borrar filas está prohibido). | §5.F6: la línea base se congela **dentro del gate** con un corte histórico |
| **C4** | BLOQUEANTE | El test de F6 era **estático** y con un `assert` de ausencia suelto: no puede detectar el defecto real, que era que **la query no corría**. | §5.F6: el test **ejecuta** el SQL del gate contra un SQLite en memoria |
| **C5** | BLOQUEANTE | Regresión de performance **medida y no declarada**: `get_project_config` no cachea (**858-1074 µs/llamada**) y F4 la mete en `_tracker_type_for`, que corre **2 veces por ticket** dentro de un loop por ticket (`api/tickets.py:1499`). | §5.F1: memo revalidado por `mtime` (medido: `os.stat` = **132 µs**) |
| **C6** | IMPORTANTE | "el mismo número de passed que antes" no es binario para quien implementa: el "antes" ya pasó. | §4.6: **los 8 baselines medidos y hardcodeados**, incluido un rojo de fábrica ajeno |
| **C7** | IMPORTANTE | F1#7 (`get_project_config` explota) pasaba **por la razón equivocada** si el ticket no tenía proyecto: el `except` nunca se ejercía. | §5.F1, caso 7 reescrito con contador de llamadas |
| **C8** | IMPORTANTE | F4 delegaba al implementador una decisión que el plan podía medir ("si el import es pesado, no lo importes"). | §5.F4: **medido y resuelto** — se importa (3,77 s, no crea la base) |
| **C9** | IMPORTANTE | La justificación de F4 sobre `completion_sync` era correcta pero por el motivo que no dice; sin el motivo real, un implementador prudente "arregla" lo que el plan prohíbe. | §5.F4: la evidencia es `completion_sync.py:165`, que **descarta el callable** |
| **C10** | IMPORTANTE | La huella `plan282-comentario-no-llega-al-tracker-gitlab` dice `resolved` y la BD viva la desmiente (fila 57, 28 min **después** del fix). Una huella que miente es peor que una que falta. | §5.F7 |
| **C11** | MENOR | `services/completion_sync.py:93-95` → la regla está en `:94-96`. Dos formas alternativas de inyectar `_BACKEND` en F0. `TRACKER_GUARDS` contiene `"_tracker_type_for"` **por nombre**. | §5.F0, §5.F4, Anexo A |

**Adición del arquitecto:** §5.**F7** — `[ADICIÓN ARQUITECTO]` la contradicción columna↔proyecto
deja **rastro** en el log y **huella nueva** en el catálogo, en vez de corregirse en silencio.

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
| K1 del gate `backend/scripts/gate_plan282.py` | **NO MEDIBLE por un bug de columna** (`exit 5`) | **medible, `0` sobre el corte histórico** (§5.F6) — **NO "devuelve 2"**: la meta del gate es `0` y está hardcodeada (`gate_plan282.py`, `v != 0` + el rótulo `(meta 0)`), así que dejar K1 en 2 convierte el `exit 5` en un **`exit 2` permanente** |
| Centinela "ningún escritor lee la columna" | **no existe** | existe, verde, y **con pata de presencia** (§5.F0): verde por ausencia de la función vigilada NO cuenta |
| Costo de resolver el tracker efectivo de un ticket de proyecto ADO | (no existía) | **≤ 200 µs**, no ~1 ms (§5.F1, memo por `mtime`) |

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
nombrados** (§5.F0), que no infiere: mira esos cuatro sitios y punto.

> **Corrección v2 (C1), y es la más importante del documento.** La v1 afirmaba que ese
> centinela era *"inmune a las tres capas de ceguera"*. **Es falso a partir de F2.** El
> centinela vigila pares `(archivo, función)` y **F2 punto 1 y F3 punto 1 ordenan BORRAR**
> `_norm_tracker_type` de los dos routers. Con la función borrada, el recorrido
> `if n.name != nombre: continue` no encuentra nada, no agrega nada, devuelve `[]` y el
> centinela queda **verde por ausencia de la función**, no porque el sitio dejó de leer la
> columna. Desde F4 en adelante esos dos archivos son **invisibles para siempre**: una
> reincidencia futura, o un simple rename, no lo despiertan. Es exactamente el patrón
> *"un assert de ausencia pasa por accidente"* y es **la misma clase de defecto** que este
> plan le imputa al ratchet del Plan 281 tres párrafos más arriba. Por eso el centinela de
> §5.F0 tiene ahora **dos patas obligatorias — ausencia Y PRESENCIA —** y una calibración
> que prueba que el centinela **grita cuando la función desaparece**.

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

**(g) Corrección v2 (C3): arreglar el nombre de la columna A SECAS rompe el gate del 282.**
La v1 no miró qué hace `main()` con el número. Lo hace:

```python
fuera = [(n, d, v, det) for n, d, v, det in kpis if v is not NO_MEDIBLE and v != 0]
...
print(f"{nombre}  {estado:<14} {desc}: {... valor} (meta 0)")
if fuera:
    print("\nRESULTADO: exit 2 — hay KPI fuera de meta.")
    return 2
```

La meta de **los seis** KPI es `0`, hardcodeada en dos lugares (el filtro `v != 0` y el
rótulo literal `(meta 0)`). Con `error_message` K1 pasa a valer **2**, y esas 2 filas son
históricas y **este plan prohíbe borrarlas** (§5.F6, §7.2). Resultado: el gate del 282 pasa
de `exit 5` ("no medible", que no reporta verde pero tampoco acusa a nadie) a **`exit 2`
permanente**, y el implementador queda sin salida legal: borrar filas está prohibido,
revertir el fix también, y commitear un gate rojo de por vida es peor que el bug original.
Reproducido ejecutando el gate real contra una **copia read-only** de la base:

```
K1  NO MEDIBLE     publicaciones fallidas con la firma 'no usa Azure DevOps': - (meta 0)
      la base no respondio: OperationalError
RESULTADO: exit 5 — K1 no se pudieron medir. Un gate que no puede medir NO reporta verde.
```

**Consecuencia:** F6 no es "un fix de una palabra". Son dos: la **columna** y el **corte
histórico** que devuelve el KPI a su meta `0` sin tocar un dato. Ver §5.F6.

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

`backend/.venv` = Python 3.13.5, `backend/venv` = Python 3.11.9. **Usá `venv`.** La
justificación de la v1 ("es el que usan los planes 281 y 282") no alcanza: tener `pytest`
instalado no es tener las dependencias del backend. **Justificación v2, medida el
2026-08-02:** con `./venv/Scripts/python.exe` corrieron **de verdad** las ocho suites de
§4.6 (`test_plan270_write_router`, `test_plan271_writer_routed`,
`test_plan270_state_write_ratchet`, `test_plan282_publicacion_comentario`,
`test_plan281_ratchet_ado_only`, `test_plan281_sitios_ado_only`,
`test_harness_ratchet_meta`, `test_plan259_ratchet_script_parity`), más
`import api.tickets` y `import services.provider_coupling_audit`. Ese venv tiene las deps.

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

### 4.3 Ratchets: los 3 archivos se registran en LOS DOS, **cada uno en la fase que lo crea**

Los ratchets son `backend/scripts/run_harness_tests.ps1` y
`backend/scripts/run_harness_tests.sh`. Ambos hacen `cd` a `backend/` antes de correr, así
que las rutas se registran como `tests/...` — **sin espacios, sin prefijo `Stacky Agents/`**
(los ratchets no admiten rutas con espacios). Sintaxis distinta en cada uno: `.ps1` usa
comillas y coma final, `.sh` va pelado.

**Corrección v2 (C2) — la v1 registraba los tres archivos juntos en F0 y llamaba a eso
"un rojo esperado y acotado al eje". No está acotado.** Hay **cuatro** gates ajenos que
gobiernan esto, y están **todos verdes hoy** salvo uno; el registro en lote rompe dos:

| Gate | Qué exige | Estado hoy (medido) | Qué le hace el registro en lote de la v1 |
|---|---|---|---|
| `tests/test_harness_ratchet_meta.py::test_ratchet_no_referencia_archivos_inexistentes` (`:79-80`) | ninguna ruta registrada puede faltar en disco | **PASSED** | lo pone **ROJO** de F0 a F2 |
| `tests/test_plan259_ratchet_script_parity.py::test_ninguna_ruta_apunta_a_un_archivo_inexistente` (`:101-103`) | lo mismo, sobre la unión `.sh ∪ .ps1` | **12 passed** en la suite | la pone **11 passed 1 failed** de F0 a F2 |
| `tests/test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` (`:43`) | todo `tests/test_*.py` está en el ratchet **o** en `tests/harness_ratchet_allowlist.txt` | **PASSED** | (lo satisface, y es la razón por la que NO se puede diferir el registro a una fase posterior) |
| `tests/test_plan259_ratchet_script_parity.py::test_los_8_de_este_plan_estan_en_las_dos_listas` | paridad `.sh` ↔ `.ps1` | verde | exige registrar en **los dos** o en ninguno |

Los dos primeros y el tercero se contradicen si el registro no es simultáneo con la
creación. **La única secuencia que deja los cuatro verdes en cada frontera de commit es:
cada fase registra, en los DOS ratchets, sólo el archivo que esa misma fase crea.**

- **F0** registra `tests/test_plan286_columna_no_rutea.py`.
- **F1** registra `tests/test_plan286_tracker_efectivo.py`.
- **F2** registra `tests/test_plan286_ruteo_de_escritura.py`.

**Anclaje por SÍMBOLO, no por línea** (F0 desplaza las líneas de F1 y F1 las de F2): la
primera inserción va inmediatamente después de la línea `test_plan282_assignee_no_borra.py`
— hoy `run_harness_tests.ps1:909` y `run_harness_tests.sh:1015`, **verificado el
2026-08-02** —, y las siguientes van al final del bloque `# Plan 286` que la fase anterior
dejó. Diff exacto en §5.F0.

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

### 4.6 Baselines de no-regresión: **medidos y congelados** (C6)

La v1 pedía "el mismo número de passed que antes del cambio (medilo antes)". Eso **no es un
criterio binario** para quien implementa: cuando llega a F3, el "antes" ya pasó. Acá están
medidos, el **2026-08-02**, en `docs/plan-279`, con
`./venv/Scripts/python.exe -m pytest tests/<archivo> -q`, un archivo por corrida:

| Suite | Baseline | Fases que la pueden mover |
|---|---|---|
| `tests/test_plan270_write_router.py` | **14 passed** | F2 |
| `tests/test_plan271_writer_routed.py` | **13 passed** | F2 |
| `tests/test_plan270_state_write_ratchet.py` | **6 passed** | F2 |
| `tests/test_plan282_publicacion_comentario.py` | **7 passed** | F3 |
| `tests/test_plan281_ratchet_ado_only.py` | **11 passed** | F5 |
| `tests/test_plan281_sitios_ado_only.py` | **18 passed** | **F2/F4** — la v1 no la listaba, y **sí** la puede mover: `TRACKER_GUARDS` (`services/provider_coupling_audit.py:142`) contiene `"_tracker_type_for"` **por nombre**, así que ese censo depende del nombre de una función que F4 toca |
| `tests/test_plan259_ratchet_script_parity.py` | **12 passed** | F0/F1/F2 |
| `tests/test_harness_ratchet_meta.py` | **1 failed, 3 passed** | F0/F1/F2 |

> **`test_harness_ratchet_meta.py` está ROJO DE FÁBRICA y no lo rompiste vos.** El que falla
> es `test_allowlist_no_se_solapa_con_ratchet`:
> `AssertionError: Archivos en ratchet Y allowlist (redundante): ['tests/test_docs_api.py']`.
> Es deuda ajena, anterior a este eje. **No la arregles acá** (tocar
> `tests/harness_ratchet_allowlist.txt` o el ratchet por ese motivo es scope creep y pisa
> terreno de otro plan). El criterio de este eje sobre esa suite es **exactamente
> `1 failed, 3 passed`**, ni mejor ni peor.

**Cómo se usa:** antes de cada fase que toca una de esas suites, corrés la suite y verificás
que da el baseline de la tabla. Después del cambio, tiene que dar **el mismo número**. Si da
otro, el cambio rompió algo — **no edites el test ajeno**.

---

## 5. Fases

Orden por dependencia estricta: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7**.
F0 nace ROJO a propósito y vuelve a verde en **F4** (no en F5: la v1 decía F5 y su propia
tabla de §9 decía F4).

---

### F0 — El centinela que hoy está ROJO: los cuatro sitios leen la columna

**Objetivo (1 frase):** dejar escrito, como test, que los cuatro escritores nombrados leen
`ticket.tracker_type`, para que el resto del plan tenga un rojo real que apagar y para que
nadie pueda volver a meter esa lectura sin que un test lo grite.

**Valor:** convierte "hay 4 sitios malos" en un booleano ejecutable. Sin esto, las fases
F2-F4 son verdes por construcción y no prueban nada (§2.3(e): el ratchet existente ya es un
falso verde). **Y sin la segunda pata (C1), este centinela sería el tercer falso verde del
eje** — el más caro, porque nace con el cartel de "el gate real del 286".

**Archivos:**
- crea `Stacky Agents/backend/tests/test_plan286_columna_no_rutea.py`
- modifica `Stacky Agents/backend/scripts/run_harness_tests.ps1` (**sólo este archivo**, §4.3)
- modifica `Stacky Agents/backend/scripts/run_harness_tests.sh` (**sólo este archivo**, §4.3)

**Las DOS patas del centinela (C1). Esto es lo que separa este gate de un falso verde:**

1. **AUSENCIA** — ninguna de las funciones vigiladas **que exista** lee la columna.
2. **PRESENCIA** — los cuatro archivos **llaman** a `tracker_efectivo_de_ticket`, y en los
   dos sitios donde la función vigilada **sobrevive** al eje (`_resolve_sync_and_project`,
   `_tracker_type_for`) la llamada tiene que estar **dentro de esa función**.

Sin la pata 2, borrar o renombrar la función vigilada deja el centinela verde para siempre:
`_norm_tracker_type` **se borra** en F2 y F3 (§5.F2 punto 1, §5.F3 punto 1), así que sin
esto el centinela llegaría a F4 verde sin haber verificado nada de esos dos archivos.

**Nombres exactos:**
- censo de lectura: `lectores_de_la_columna(sitios) -> list[str]`
- censo de anclaje: `archivos_sin_anclaje(anclas) -> list[str]`
- constantes congeladas: `SITIOS_VIGILADOS: tuple[tuple[str, str], ...]`,
  `ANCLAS_HELPER: tuple[tuple[str, str | None], ...]`
- tests (**4**): `test_ningun_sitio_vigilado_lee_la_columna`,
  `test_los_cuatro_archivos_anclan_en_el_helper`,
  `test_el_detector_ve_los_dos_idiomas` (calibración),
  `test_el_centinela_no_se_calla_si_la_funcion_desaparece` (calibración del rename)

**Pseudocódigo (el archivo completo, salvo detalles de estilo). `_BACKEND` va como
parámetro con default — NO uses `global`: la v1 ofrecía las dos formas y eso es una
bifurcación gratuita para un modelo menor (C11):**

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
_HELPER = "tracker_efectivo_de_ticket"

# (ruta relativa a backend/, nombre de la funcion que NO puede leer la columna).
# Lista CONGELADA: agregar un sitio nuevo es una decision del plan, no un efecto
# colateral.
SITIOS_VIGILADOS = (
    ("services/tracker_write_router.py",   "_norm_tracker_type"),
    ("services/comment_publish_router.py", "_norm_tracker_type"),
    ("services/completion_sync.py",        "_resolve_sync_and_project"),
    ("api/tickets.py",                     "_tracker_type_for"),
)

# PATA 2 (C1). (ruta, funcion|None). None => basta con que el ARCHIVO llame al
# helper, porque el eje BORRA la funcion vigilada de ese archivo (F2/F3). Con un
# nombre de funcion => la llamada tiene que estar DENTRO de esa funcion, porque
# esa funcion SOBREVIVE al eje (F4).
# Sin esta constante, borrar o renombrar la funcion vigilada deja el censo de
# ausencia verde para siempre: verde por ausencia de la funcion, no por ausencia
# del defecto. Es el falso verde que este centinela existe para no repetir.
ANCLAS_HELPER = (
    ("services/tracker_write_router.py",   None),
    ("services/comment_publish_router.py", None),
    ("services/completion_sync.py",        "_resolve_sync_and_project"),
    ("api/tickets.py",                     "_tracker_type_for"),
)


def _funcs(arbol, nombre):
    return [n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == nombre]


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


def _llama_al_helper(nodo) -> bool:
    """`tracker_efectivo_de_ticket(...)` o `<mod>.tracker_efectivo_de_ticket(...)`."""
    if not isinstance(nodo, ast.Call):
        return False
    fn = nodo.func
    if isinstance(fn, ast.Name):
        return fn.id == _HELPER
    if isinstance(fn, ast.Attribute):
        return fn.attr == _HELPER
    return False


def lectores_de_la_columna(sitios, backend=None):
    """['<ruta>::<funcion>'] por cada sitio vigilado que lee la columna."""
    raiz = backend or _BACKEND
    hallados = []
    for rel, nombre in sitios:
        arbol = ast.parse((raiz / rel).read_text(encoding="utf-8"))
        for n in _funcs(arbol, nombre):
            if any(_lee_la_columna(h) for h in ast.walk(n)):
                hallados.append(f"{rel}::{nombre}")
    return sorted(set(hallados))


def archivos_sin_anclaje(anclas, backend=None):
    """['<ruta>' | '<ruta>::<funcion>'] por cada ancla que NO llama al helper."""
    raiz = backend or _BACKEND
    faltan = []
    for rel, nombre in anclas:
        arbol = ast.parse((raiz / rel).read_text(encoding="utf-8"))
        if nombre is None:
            if not any(_llama_al_helper(n) for n in ast.walk(arbol)):
                faltan.append(rel)
            continue
        objetivo = _funcs(arbol, nombre)
        if not objetivo:
            faltan.append(f"{rel}::{nombre} (LA FUNCION NO EXISTE)")
            continue
        if not any(_llama_al_helper(h) for f in objetivo for h in ast.walk(f)):
            faltan.append(f"{rel}::{nombre}")
    return sorted(set(faltan))


def test_ningun_sitio_vigilado_lee_la_columna():
    """PATA 1 — ausencia."""
    vivos = lectores_de_la_columna(SITIOS_VIGILADOS)
    assert vivos == [], (
        f"estos escritores siguen ruteando por la columna que MIENTE: {vivos}. "
        f"Tienen que llamar a services.project_context.{_HELPER}."
    )


def test_los_cuatro_archivos_anclan_en_el_helper():
    """PATA 2 — PRESENCIA. Un assert de ausencia solo pasa por accidente: este
    guarda la presencia del anclaje EN EL MISMO eje, asi que borrar o renombrar
    la funcion vigilada NO puede apagar el centinela."""
    faltan = archivos_sin_anclaje(ANCLAS_HELPER)
    assert faltan == [], (
        f"estos sitios ya no leen la columna PERO tampoco resuelven con el "
        f"helper: {faltan}. Un centinela verde por ausencia de la funcion es un "
        f"falso verde (Plan 286 C1)."
    )


def test_el_detector_ve_los_dos_idiomas(tmp_path):
    """Calibracion 1 — el gate se corre CONTRA el defecto: si el detector no ve
    el idioma `getattr`, la pata 1 es un falso verde (le paso al Plan 281)."""
    (tmp_path / "sonda.py").write_text(
        "def por_atributo(t):\n"
        "    return t.tracker_type\n"
        "def por_getattr(t):\n"
        '    return getattr(t, "tracker_type", None)\n'
        "def limpia(t):\n"
        "    return t.stacky_project_name\n",
        encoding="utf-8",
    )
    marcadas = lectores_de_la_columna(
        (("sonda.py", "por_atributo"), ("sonda.py", "por_getattr"),
         ("sonda.py", "limpia")),
        backend=tmp_path,
    )
    assert marcadas == ["sonda.py::por_atributo", "sonda.py::por_getattr"]


def test_el_centinela_no_se_calla_si_la_funcion_desaparece(tmp_path):
    """Calibracion 2 (C1) — el modo de falla que mato a la v1: si la funcion
    vigilada se BORRA o se RENOMBRA, la pata 1 devuelve [] (nada que mirar) y la
    pata 2 tiene que GRITAR. Se prueban los dos lados en el mismo test."""
    (tmp_path / "limpio.py").write_text(
        "from services.project_context import tracker_efectivo_de_ticket\n"
        "def resolver(t):\n"
        "    return tracker_efectivo_de_ticket(t)\n",
        encoding="utf-8",
    )
    (tmp_path / "renombrado.py").write_text(
        "def otro_nombre(t):\n"
        '    return getattr(t, "tracker_type", None)\n',
        encoding="utf-8",
    )
    # (a) La pata 1 se calla cuando la funcion no existe: por eso no alcanza sola.
    assert lectores_de_la_columna(
        (("renombrado.py", "_norm_tracker_type"),), backend=tmp_path) == []
    # (b) La pata 2 lo agarra igual, por archivo...
    assert archivos_sin_anclaje(
        (("renombrado.py", None),), backend=tmp_path) == ["renombrado.py"]
    # (c) ...y por funcion inexistente, con el motivo escrito.
    assert archivos_sin_anclaje(
        (("renombrado.py", "_norm_tracker_type"),), backend=tmp_path
    ) == ["renombrado.py::_norm_tracker_type (LA FUNCION NO EXISTE)"]
    # (d) Y NO grita sobre un archivo que si ancla: la pata 2 no es un assert
    #     que siempre falla.
    assert archivos_sin_anclaje((("limpio.py", None),), backend=tmp_path) == []
    assert archivos_sin_anclaje(
        (("limpio.py", "resolver"),), backend=tmp_path) == []
```

**Registro en los ratchets (diff exacto). SÓLO EL ARCHIVO DE ESTA FASE (§4.3, C2).** En
`Stacky Agents/backend/scripts/run_harness_tests.ps1`, después de la línea
`"tests/test_plan282_assignee_no_borra.py",` (hoy `:909`):

```powershell

  # Plan 286 - El ruteo de escritura le pregunta al proyecto, no a la columna.
  "tests/test_plan286_columna_no_rutea.py",
```

En `Stacky Agents/backend/scripts/run_harness_tests.sh`, después de
`tests/test_plan282_assignee_no_borra.py` (hoy `:1015`):

```bash

  # Plan 286 - El ruteo de escritura le pregunta al proyecto, no a la columna.
  tests/test_plan286_columna_no_rutea.py
```

**Los otros dos archivos NO se registran acá.** `test_plan286_tracker_efectivo.py` se
registra en F1 y `test_plan286_ruteo_de_escritura.py` en F2, cada uno en el commit que lo
crea. Motivo medido en §4.3: registrar una ruta inexistente pone rojas dos suites ajenas
que hoy están verdes, y no registrarla al crearla pone roja una tercera. **No hay orden
alternativo.**

**Criterio de aceptación BINARIO:**

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -v
```

- `test_el_detector_ve_los_dos_idiomas` → **PASA** (el detector sirve).
- `test_el_centinela_no_se_calla_si_la_funcion_desaparece` → **PASA** (la pata 2 sirve).
- `test_ningun_sitio_vigilado_lee_la_columna` → **FALLA**, y el mensaje lista **exactamente
  estos 4**:
  `api/tickets.py::_tracker_type_for`, `services/comment_publish_router.py::_norm_tracker_type`,
  `services/completion_sync.py::_resolve_sync_and_project`,
  `services/tracker_write_router.py::_norm_tracker_type`.
- `test_los_cuatro_archivos_anclan_en_el_helper` → **FALLA**, y el mensaje lista
  **exactamente estos 4**: `api/tickets.py::_tracker_type_for`,
  `services/comment_publish_router.py`, `services/completion_sync.py::_resolve_sync_and_project`,
  `services/tracker_write_router.py`.
- Resultado esperado: **2 failed, 2 passed**.

Si alguno de los dos primeros **falla** en F0, el detector está mal escrito. Si alguno de
los dos últimos **pasa** en F0, el centinela está mal apuntado — en los dos casos **no
bajes la expectativa, arreglá el centinela**.

Y las suites ajenas de §4.6 que este commit toca, **con su baseline exacto**:

```bash
./venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -q   # 12 passed
./venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q            # 1 failed, 3 passed
```

Y el guard de colección:

```bash
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py --collect-only -q | tail -3
```
→ tiene que decir **4 tests**.

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
- modifica `run_harness_tests.ps1` y `run_harness_tests.sh` — **registra acá**
  `tests/test_plan286_tracker_efectivo.py`, al final del bloque `# Plan 286` que dejó F0
  (§4.3, C2). Después: `test_plan259_ratchet_script_parity.py` → **12 passed**,
  `test_harness_ratchet_meta.py` → **1 failed, 3 passed**.

**Nombres exactos:**
- `tracker_declarado_del_proyecto(project_name: str | None) -> str | None`
- `tracker_efectivo_de_ticket(ticket) -> str`
- privados del memo (C5): `_TRACKER_DECLARADO_MEMO: dict[str, tuple[int, int, str | None]]`,
  `_reset_memo_tracker_declarado() -> None`

**Corrección v2 (C5) — el memo NO es opcional, y no es una optimización prematura: es la
reparación de una degradación medida.** `project_manager.get_project_config`
(`project_manager.py:55-62`) **no cachea**: hace `exists()` + `read_text()` + `json.loads()`
del config entero en **cada** llamada. Medido el 2026-08-02 en este árbol:

| Operación | Costo medido |
|---|---|
| `get_project_config("RIPLEY")` (config de 3.969 b) | **858 µs** |
| `get_project_config("RSPACIFICO")` (7.278 b) | **1.057 µs** |
| `get_project_config("RSSICREA")` (6.667 b) | **1.074 µs** |
| `get_project_config("p")` (no existe el dir) | 71 µs |
| `os.stat(<config.json>)` | **132 µs** |

`tracker_efectivo_de_ticket` corta antes de tocar el disco cuando la columna es explícita
(los 63 de RIPLEY con `'gitlab'` y los 3 de `__demo__`), pero **pega al disco para las 162
filas `azure_devops`**, que son la mayoría. Y F4 mete ese costo en
`api/tickets.py::_tracker_type_for`, que se invoca **dos veces por ticket** dentro de
`_resolve_ci_result` (`:471` vía `_item_ref_for_ticket` y `:509`) — y `_resolve_ci_result`
corre **en un loop por ticket** en el batch de pipelines (`api/tickets.py:1499`, sobre
`ticket_ids`). Son **~2,1 ms por ticket** de puro `json.loads`. La v1 afirmaba "sin impacto"
sin haberlo medido.

*Atenuante, y hay que escribirlo para no exagerar el riesgo:* ese camino está detrás de
`STACKY_PIPELINE_PROVIDER_ENABLED`, que hoy resuelve a **False** (`api/tickets.py:480`,
`getattr(..., False)`), así que la degradación está **dormida**. Se arregla igual, porque el
plan no puede dejar una bomba armada detrás de una flag que otro plan puede encender.

**Por qué `mtime` y no un TTL, ni un `lru_cache`.** El operador cambia
`issue_tracker.type` **por UI** (§8, glosario). Un `lru_cache` o un TTL dejarían a Stacky
escribiendo en el tracker viejo hasta que el proceso reinicie o venza la ventana — un
falso destino, que es exactamente el defecto que este plan mata. Revalidar con un solo
`os.stat` cuesta **132 µs en vez de 1.057 µs (8x)** y **no puede quedar stale**: si el
archivo cambia, cambia `st_mtime_ns` o `st_size` y el memo se descarta en la llamada
siguiente. *Instrucción dura: si te tienta cambiar el `os.stat` por un TTL o un
`functools.lru_cache`, **no lo hagas** — está en §7.10.*

**No tocar `__all__`** (`project_context.py:440-447`): ni `tracker_is_azure_devops` ni
`ruteo_estricto_por_tracker` están ahí, y los imports de este plan son explícitos.

**Diff ilustrativo:**

```python
# Plan 286 F1 (C5) — memo {proyecto: (st_mtime_ns, st_size, tipo|None)}.
# Modulo-level a proposito: el ciclo de vida es el del proceso, igual que el del
# resto del modulo. `_reset_memo_tracker_declarado()` existe SOLO para los tests
# (un memo que los tests no pueden vaciar produce falsos verdes por orden).
_TRACKER_DECLARADO_MEMO: dict[str, tuple[int, int, str | None]] = {}


def _reset_memo_tracker_declarado() -> None:
    """Plan 286 F1 — vacia el memo. Uso: tests. NUNCA en camino de produccion."""
    _TRACKER_DECLARADO_MEMO.clear()


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
        import os
        from project_manager import PROJECTS_DIR, get_project_config as _get_cfg

        # Plan 286 F1 (C5) — memo revalidado por mtime. `get_project_config`
        # relee y reparsea el JSON entero en cada llamada (medido: 858-1074 us,
        # project_manager.py:55-62) y este helper corre POR TICKET dentro de un
        # loop (api/tickets.py:1499). Un `os.stat` cuesta 132 us y NO puede
        # quedar stale: el operador cambia el tracker por UI, y cualquier
        # escritura del archivo mueve st_mtime_ns/st_size. NO cambiar por TTL ni
        # por lru_cache: eso rutearia al tracker viejo, que es el defecto que
        # este plan mata.
        try:
            st = os.stat(PROJECTS_DIR / raw / "config.json")
            firma = (st.st_mtime_ns, st.st_size)
        except OSError:
            firma = None  # sin archivo (o sin permiso) -> camino sin memo

        if firma is not None:
            cacheado = _TRACKER_DECLARADO_MEMO.get(raw)
            if cacheado is not None and cacheado[:2] == firma:
                return cacheado[2]

        cfg = _get_cfg(raw) or {}
        tracker = cfg.get("issue_tracker") or {}
        declarado = (tracker.get("type") or "").strip().lower() or None

        if firma is not None:
            _TRACKER_DECLARADO_MEMO[raw] = (firma[0], firma[1], declarado)
        return declarado
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
import pytest
from services.project_context import _reset_memo_tracker_declarado

@pytest.fixture(autouse=True)
def _memo_limpio():
    """El memo de F1 es modulo-level: sin esto, el orden de los tests decide el
    resultado y aparecen verdes que no significan nada."""
    _reset_memo_tracker_declarado()
    yield
    _reset_memo_tracker_declarado()

def _ticket(tracker_type=None, proyecto=None):
    return SimpleNamespace(tracker_type=tracker_type, stacky_project_name=proyecto)

def _con_config(monkeypatch, mapa):
    """mapa: {"RIPLEY": "gitlab", "RSPACIFICO": "azure_devops"}; ausente => None.
    Devuelve la lista de nombres consultados: varios casos NO prueban nada si no
    se comprueba que el fake fue LLAMADO (C7)."""
    llamadas = []
    def _fake(nombre):
        llamadas.append(nombre)
        tipo = mapa.get((nombre or "").strip().upper())
        return {"issue_tracker": {"type": tipo}} if tipo else None
    monkeypatch.setattr("project_manager.get_project_config", _fake)
    return llamadas
```

> **Ojo con el memo en los tests (C5).** El memo se revalida contra el `os.stat` del
> **config real en disco**, no contra el fake. Para `RIPLEY` / `RSPACIFICO` esos archivos
> **existen** en este árbol, así que la primera llamada cachea el valor **del fake** bajo la
> firma del archivo real y la segunda no vuelve a llamarlo. Por eso el fixture `autouse` de
> arriba es obligatorio, y por eso los asserts de "el fake fue llamado" (C7) van sobre la
> **primera** llamada de cada test.

Casos, **exactamente estos 14** (11 de la v1, con el 7 reescrito, más 3 del memo):

| # | test | entrada | esperado | qué protege |
|---|---|---|---|---|
| 1 | `test_columna_mentirosa_pierde_contra_el_proyecto` | `tracker_type="azure_devops"`, proyecto `RIPLEY`(gitlab) | `"gitlab"` | **el caso de los 2 tickets. Si falla, el plan no sirve.** |
| 2 | `test_columna_vacia_cae_al_proyecto` | `tracker_type=None`, `RIPLEY` | `"gitlab"` | ausencia |
| 3 | `test_columna_explicita_no_default_gana_al_proyecto` | `tracker_type="jira"`, `RSPACIFICO`(ado) | `"jira"` | P2, rama 1 |
| 4 | `test_proyecto_ado_sigue_siendo_ado` | `tracker_type="azure_devops"`, `RSPACIFICO` | `"azure_devops"` | **no-regresión ADO** |
| 5 | `test_sin_proyecto_es_fail_closed_a_ado` | `tracker_type="azure_devops"`, `None` | `"azure_devops"` | P3 |
| 6 | `test_proyecto_sin_config_es_fail_closed_a_ado` | `tracker_type="azure_devops"`, `"p"` (sin config) | `"azure_devops"` | P3, las 100 filas |
| 7 | `test_get_project_config_que_explota_es_fail_closed` | `tracker_type="azure_devops"`, proyecto **`"RIPLEY"`** (obligatorio) y un `get_project_config` que **lanza `RuntimeError` y cuenta sus llamadas** | `"azure_devops"` **y `len(llamadas) == 1`** | nunca levanta. **C7: con un ticket SIN proyecto este test pasa sin ejercer el `except`** — `tracker_declarado_del_proyecto` corta en `if not raw: return None` antes de llamar a nada. El assert del contador es lo único que hace que el verde signifique algo |
| 8 | `test_columna_con_espacios_y_mayusculas_se_normaliza` | `tracker_type="  GitLab  "`, proyecto ADO | `"gitlab"` | normalización |
| 9 | `test_columna_no_string_se_ignora` | `tracker_type=123`, `RIPLEY` | `"gitlab"` | el `isinstance` |
| 10 | `test_kill_switch_apagado_devuelve_la_columna_cruda` | flag OFF, `tracker_type="azure_devops"`, `RIPLEY` | `"azure_devops"` | P7 / rollback |
| 11 | `test_kill_switch_apagado_sin_columna_da_el_default` | flag OFF, `tracker_type=None`, `RIPLEY` | `"azure_devops"` | P7, rama vacía |
| 12 | `test_el_memo_no_relee_el_config_dos_veces` | dos llamadas seguidas con `tracker_type=None`, `RIPLEY` | `"gitlab"` las dos veces **y `len(llamadas) == 1`** | **C5** — sin esto el memo puede no existir y nadie se entera |
| 13 | `test_tocar_el_config_invalida_el_memo` | `monkeypatch.setattr("os.stat", <doble>)`: el doble devuelve un objeto con `st_mtime_ns`/`st_size` **fijos** en la 1ª llamada y **distintos** en la 2ª; el fake de config devuelve `gitlab` y después `jira` | 1ª llamada `"gitlab"`, 2ª `"jira"`, **`len(llamadas) == 2`** | el memo **no puede quedar stale** cuando el operador edita el tracker por UI |
| 14 | `test_un_stat_que_explota_cae_al_camino_sin_memo` | `os.stat` lanza `OSError`, dos llamadas seguidas | devuelve igual el valor del config las dos veces **y `len(llamadas) == 2`** | degradación: sin firma no hay memo, pero **nunca** rompe |

Para 10 y 11, apagar la flag con
`monkeypatch.setattr("config.config.STACKY_TRACKER_ROUTING_STRICT_ENABLED", False, raising=False)`
(se lee del **objeto** `config.config`, `project_context.py:95-97`, nunca con `os.getenv`).

**Cómo se comprueba que el rojo es rojo por la razón correcta:** escribí los 14 tests
**antes** de tocar `project_context.py` y corrélos: tienen que fallar todos con
`ImportError` sobre `tracker_efectivo_de_ticket` **o** `_reset_memo_tracker_declarado`.
Verificado el 2026-08-02: hoy `from services.project_context import tracker_efectivo_de_ticket`
da `ImportError: cannot import name 'tracker_efectivo_de_ticket'`. Recién ahí implementá.

**Criterio de aceptación BINARIO:**

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_tracker_efectivo.py -v
```
→ **14 passed**. Y `--collect-only -q | tail -3` → **14 tests**.

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

Y el **criterio de performance (C5), binario y medido**:

```bash
./venv/Scripts/python.exe -c "
import sys, time; sys.path.insert(0,'.')
from types import SimpleNamespace
from services.project_context import tracker_efectivo_de_ticket as f
t = SimpleNamespace(tracker_type='azure_devops', stacky_project_name='RSPACIFICO')
f(t)                                   # calienta el memo
ini = time.perf_counter()
for _ in range(2000): f(t)
us = (time.perf_counter() - ini) * 1e6 / 2000
print('%.0f us/llamada' % us)
assert us < 400, 'el memo no esta funcionando: %.0f us' % us
"
```
→ imprime un número **< 400 µs** y no revienta. **Línea base sin memo, medida el
2026-08-02: 1.057 µs.** Si te da > 400, el memo no se está usando (lo más probable: la
firma del `os.stat` se recalcula sobre un path distinto del que lee `get_project_config`).

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
- modifica `run_harness_tests.ps1` y `run_harness_tests.sh` — **registra acá**
  `tests/test_plan286_ruteo_de_escritura.py`, al final del bloque `# Plan 286` (§4.3, C2).
  Es el último de los tres; después de F2 el bloque tiene las 3 rutas y no se toca más.

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

**Criterio de aceptación BINARIO** (números de §4.6, **medidos el 2026-08-02**, no "los
mismos que antes" — C6). Un archivo por corrida:
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -q   # 6 passed
./venv/Scripts/python.exe -m pytest tests/test_plan270_write_router.py -q         # 14 passed
./venv/Scripts/python.exe -m pytest tests/test_plan271_writer_routed.py -q        # 13 passed
./venv/Scripts/python.exe -m pytest tests/test_plan270_state_write_ratchet.py -q  # 6 passed
./venv/Scripts/python.exe -m pytest tests/test_plan281_sitios_ado_only.py -q      # 18 passed
./venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -q # 12 passed
./venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q          # 1 failed, 3 passed (rojo de fabrica ajeno, §4.6)
```
Si alguno da otro número, **no lo edites**: significa que la equivalencia del punto 4 no se
cumplió. `test_plan281_sitios_ado_only.py` está en la lista porque `TRACKER_GUARDS`
(`provider_coupling_audit.py:142`) discrimina **por nombre de función** y esta fase toca el
cuerpo de funciones que ese censo mira.

Y `--collect-only -q | tail -3` de `test_plan286_ruteo_de_escritura.py` → **6 tests**.

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

**Criterio de aceptación BINARIO** (números de §4.6, medidos — C6):
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -q      # 9 passed
./venv/Scripts/python.exe -m pytest tests/test_plan282_publicacion_comentario.py -q  # 7 passed
```
Y `--collect-only -q | tail -3` del primero → **9 tests**.

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
mismo archivo, `:94-96` — la v1 decía `:93-95`, C11). El resto de la función queda igual: el
`if tracker_type == "jira"` / `elif "mantis"` / `else` sigue tal cual, y **no hay que agregar
una rama `gitlab`** acá.

> **Corrección v2 (C9) — la razón real, porque sin ella el implementador va a "arreglar"
> lo que el plan prohíbe.** Después de este cambio, para un ticket de RIPLEY la función pasa
> a devolver el par **incoherente** `(services.ado_sync.sync_tickets, "RIPLEY", "gitlab")`:
> el callable es el de Azure DevOps y el tracker dice GitLab. Eso **parece** un bug y
> cualquiera con criterio le agrega la rama que el plan prohíbe. Lo que lo hace seguro no es
> que "la rama GitLab exista más abajo en `_do_project_sync` (`:116-119`, Plan 281 F5)" —
> eso es cierto pero no es el argumento. **El argumento es que el callable está muerto: el
> único consumidor lo descarta.** `services/completion_sync.py:165`:
>
> ```python
>             _, project, tracker_type = _resolve_sync_and_project(t)
> ```
>
> Censo completo, verificado el 2026-08-02: `_resolve_sync_and_project` se define en `:40` y
> se llama en **un solo lugar**, `:165`, dentro de `maybe_coalesced_sync`, que se queda con
> `project` y `tracker_type` y se los pasa a `_do_project_sync(project, tracker_type, ado_id)`
> — que **sí** discrimina GitLab en `:116-119`. El primer elemento de la tupla no lo consume
> nadie. *Instrucción dura: no agregues la rama `gitlab` al `if/elif/else`. Está en §7.11.*

**Cambio en `api/tickets.py::_tracker_type_for` (`:461-463`):** reemplazar el cuerpo por
`return tracker_efectivo_de_ticket(ticket)` y agregar `tracker_efectivo_de_ticket,` al
bloque de import que **ya existe** en `api/tickets.py:32-38` (junto a
`ruteo_estricto_por_tracker` y `tracker_is_azure_devops`), respetando el orden alfabético
que el bloque ya trae — va **antes** de `tracker_is_azure_devops`. Actualizar el docstring
de una línea (`:462`).

> **NO renombres `_tracker_type_for` (C11).** `services/provider_coupling_audit.py:142`
> tiene ese nombre **literal** dentro de `TRACKER_GUARDS`, el conjunto que decide si una
> función que construye un cliente ADO cae en `gateados` o en `ado_only` (`:316`). Un rename
> mueve el censo del Plan 218/281 sin que este plan lo pida. Cambia el **cuerpo**, dejá el
> **nombre**. Ojo también con el homónimo `api/client_profile.py:85::_tracker_type_for`, que
> es **otra función** (recibe `project_name: str`, no un ticket) y **no se toca**.

**Tests (se suman al archivo de F2), exactamente 4:**

| # | test | esperado |
|---|---|---|
| 10 | `test_completion_sync_de_ripley_no_elige_el_sync_de_ado` | `_resolve_sync_and_project(ticket_ripley_mentiroso)[2] == "gitlab"` |
| 11 | `test_completion_sync_de_rspacifico_elige_ado` | `[2] == "azure_devops"`. **NO assertes el callable** (C9): es código muerto, congelarlo como contrato documenta una mentira. Asserta en cambio `[1] == "RSPACIFICO"` |
| 12 | `test_item_ref_de_ripley_declara_gitlab` | `_tracker_type_for(ticket_ripley_mentiroso) == "gitlab"` |
| 13 | `test_item_ref_de_rspacifico_declara_ado` | `== "azure_devops"` |

**El import de `api/tickets.py`: MEDIDO Y RESUELTO — se importa (C8).** La v1 delegaba la
decisión ("si resulta pesado o toca la BD, no lo importes"), lo cual es exactamente la
ambigüedad que un modelo menor resuelve mal. Medido el 2026-08-02, con `DATABASE_URL`
apuntado a un archivo SQLite **inexistente**:

```
import api.tickets  ->  OK en 3.77 s   (y el archivo de base NO se creó)
```

O sea: importar el módulo **funciona**, tarda ~3,8 s (aceptable en un test) y **no abre ni
crea la base** — SQLAlchemy no conecta al importar `db`. **Los tests 12 y 13 importan
`api.tickets` directamente.** No hay fork, no hay fallback AST, no hay decisión que tomar.

**Criterio de aceptación BINARIO:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -q  # 13 passed
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -q    # 4 passed
./venv/Scripts/python.exe -m pytest tests/test_plan281_sitios_ado_only.py -q     # 18 passed
```
→ **13 passed** en el primero. En el segundo, **4 passed**: las **dos** patas del centinela
de F0 pasan a VERDE acá — la de ausencia *y la de presencia*. Ese es el hito real del eje, y
sólo cuenta con las dos: la de ausencia sola quedaría verde igual aunque F2/F3 hubieran
borrado las funciones sin poner el helper (C1).

**Verificación extra, y es la más barata del eje** — el censo `getattr`-extendido de §7.4
baja de **8 a 7** porque `services/completion_sync.py::_resolve_sync_and_project` sale de la
lista. Es un binario independiente del centinela y de sus puntos ciegos:

```bash
./venv/Scripts/python.exe - <<'PY'
import sys, ast; sys.path.insert(0,'.')
import services.provider_coupling_audit as pca
from pathlib import Path
def es_col(n):
    if isinstance(n, ast.Attribute) and n.attr == "tracker_type":
        v = n.value
        return not (isinstance(v, ast.Call) and pca._nombre_llamado(v) in pca._ORIGENES_RESUELTOS)
    if isinstance(n, ast.Call):
        f = n.func
        if isinstance(f, ast.Name) and f.id == "getattr" and len(n.args) >= 2:
            a = n.args[1]
            return isinstance(a, ast.Constant) and a.value == "tracker_type"
    return False
def subn(n):
    out=[]; p=[n]
    while p:
        x=p.pop(); out.append(x); p.extend(ast.iter_child_nodes(x))
    return out
base = Path('.').resolve(); marcadas=set()
for path in pca._archivos_censables(base):
    rel = path.relative_to(base).as_posix()
    if rel == "services/project_context.py": continue
    try: tree = ast.parse(path.read_text(encoding='utf-8'))
    except Exception: continue
    for nombre, propios in pca._funciones_con_cuerpo_propio(tree):
        leidos=set()
        for nodo in propios:
            val = getattr(nodo,'value',None)
            if val is None or not isinstance(nodo,(ast.Assign,ast.AnnAssign,ast.AugAssign)): continue
            if not any(es_col(s) for s in subn(val)): continue
            for d in (nodo.targets if isinstance(nodo,ast.Assign) else [nodo.target]):
                for s in subn(d):
                    if isinstance(s,ast.Name): leidos.add(s.id)
        for nodo in propios:
            if not isinstance(nodo,ast.Compare): continue
            planos=[s for o in [nodo.left]+list(nodo.comparators) for s in subn(o)]
            if not any(isinstance(s,ast.Constant) and isinstance(s.value,str) and s.value in pca.TRACKER_LITERALS for s in planos): continue
            if any(es_col(s) or (isinstance(s,ast.Name) and s.id in leidos) for s in planos):
                marcadas.add(f"{rel}::{nombre}"); break
print(len(marcadas)); [print(" -", m) for m in sorted(marcadas)]
assert "services/completion_sync.py::_resolve_sync_and_project" not in marcadas
assert len(marcadas) == 7, marcadas
PY
```
→ imprime **7** y no revienta. **Antes del eje imprime 8** (medido el 2026-08-02; la lista
exacta está en §7.4). Este snippet es una **verificación**, no un test: no se agrega al
ratchet ni se amplía `scan_tracker_type_routing` (§7.4).

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

**Efecto medido antes de hacerlo (para que no haya sorpresa): CERO.** Reproducido el
2026-08-02 sobre el árbol **sin ningún cambio del 286**: con
`_ROUTING_EXCLUDED_FILES = frozenset({"services/project_context.py"})` y la regla actual del
detector, `scan_tracker_type_routing()` devuelve `[]`. O sea, esta fase **no puede** poner
rojo el ratchet del 281, **ni antes ni después de F2** (después de F2 el archivo tampoco
califica: la única `ast.Compare` con literal de tracker es `if ttype == "gitlab"`, y `ttype`
pasa a venir de `tracker_efectivo_de_ticket(...)`, que no es una lectura de la columna, así
que el paso 1 del detector no lo registra en `leidos`). Es una limpieza de cobertura sin
riesgo y **es independiente del orden** respecto de F2.

**Criterio de aceptación BINARIO** (números de §4.6, medidos — C6):
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan281_ratchet_ado_only.py -q   # 11 passed
./venv/Scripts/python.exe -m pytest tests/test_plan281_sitios_ado_only.py -q    # 18 passed
./venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from services.provider_coupling_audit import _ROUTING_EXCLUDED_FILES, scan_tracker_type_routing
assert 'services/tracker_write_router.py' not in _ROUTING_EXCLUDED_FILES
assert _ROUTING_EXCLUDED_FILES == frozenset({'services/project_context.py'})
assert scan_tracker_type_routing() == []
print('F5 OK')
"
```
→ los pytest, **11 passed** y **18 passed**; el snippet imprime `F5 OK`.

**Flag:** ninguna. Un ratchet no se gatea.
**Impacto por runtime:** ninguno (análisis estático). Idéntico en los 3. Sin fallback.
**Trabajo del operador: ninguno.**

---

### F6 — El KPI se vuelve medible **y vuelve a su meta**: columna real + corte histórico

**Objetivo:** que `k1_publicaciones_fallidas` deje de devolver `NO_MEDIBLE` por un nombre de
columna equivocado, **y** que el número resultante vuelva a la meta `0` del gate congelando
la línea base **dentro del gate**, sin tocar un solo dato.

**Valor:** sin esto, el KPI principal del eje no se puede leer y "0 fallas" es
indistinguible de "el gate está roto". **Corrección v2 (C3): no es "un fix de una palabra"**
— con una sola palabra el gate pasa de `exit 5` a `exit 2` **permanente**, porque su meta es
`0` y las 2 filas que quedarían contando son históricas y no se pueden borrar (§2.3(g)).

**Archivos:**
- modifica `Stacky Agents/backend/scripts/gate_plan282.py`
- agrega **1** test al archivo `tests/test_plan286_columna_no_rutea.py`

**Cambio exacto (`gate_plan282.py`): son DOS, no uno (C3).** Arreglar sólo el nombre de la
columna deja K1 en **2** contra una meta **0 hardcodeada** y convierte el `exit 5` del gate
en un **`exit 2` permanente** (§2.3(g)). El segundo cambio congela la línea base **dentro
del gate**, que es donde el gate la lee — escribirla sólo en este documento no la aplica.

Al lado de `NO_MEDIBLE` (`:30`), una constante y el SQL **como constante de módulo** (esto
último no es estético: es lo que permite que el test de abajo ejecute **la query del gate**
y no una copia suya):

```python
# Plan 286 F6 — Corte historico de K1. Las dos publicaciones fallidas que hay en
# la base del operador (ids 56 y 57, ado_id 1116 y 1120) son ANTERIORES a que el
# fix del Plan 282 estuviera CORRIENDO: la 57 es de un backend arrancado antes
# del commit 3461d0ce y nunca reiniciado (Plan 286 §2.3(d)). Sus tickets tienen
# la columna CORRECTA, asi que no las causo el defecto del Plan 286 y el Plan 286
# PROHIBE borrarlas (§7.2). Sin este corte, arreglar el nombre de la columna
# dejaria K1 en 2 contra la meta 0 de `main()` y este gate quedaria en exit 2
# para siempre. El corte es POSTERIOR a la ultima falla historica conocida
# (2026-08-01 20:24:43): toda fila con esta firma despues de este instante es una
# regresion real del eje y TIENE que contar.
K1_CORTE_HISTORICO = "2026-08-01 21:00:00"

# La query VIVE aca, como constante, para que el test la EJECUTE en vez de
# copiarla: un test que copia el SQL queda verde con el gate roto.
K1_SQL = (
    "SELECT COUNT(*) FROM agent_html_publish "
    # `error_message` es la columna real. `reason` es el campo del dataclass
    # PublishResult (ado_publisher.py:459), NO la columna: con `reason` esto
    # tiraba `OperationalError: no such column` y K1 devolvia NO MEDIBLE SIEMPRE,
    # tapado por el `except Exception` de mas abajo.
    "WHERE status = 'failed' AND error_message LIKE '%no usa Azure DevOps%' "
    "AND published_at > :corte"
)
```

y en `k1_publicaciones_fallidas` (def en `:184`), reemplazar el bloque `:199-205` por:

```python
            filas = s.execute(text(K1_SQL), {"corte": K1_CORTE_HISTORICO}).scalar()
        return int(filas or 0), [
            f"corte historico {K1_CORTE_HISTORICO}: las 2 fallas previas "
            f"(Plan 286 §2.3(d)) no cuentan y NO se borran"
        ]
```

La nota sale impresa por `main()` (imprime `detalle` debajo de cada KPI), así que el corte
**no queda invisible**: quien lea el gate ve el número y de dónde sale.

**Test que lo protege** (`test_el_gate_282_mide_de_verdad_y_respeta_el_corte`).
**Corrección v2 (C4): el de la v1 era estático y no podía detectar el defecto.** El bug no
era el texto — era que **la query no corría**. Un test que sólo lee el archivo queda verde
si el SQL se rompe por cualquier otro motivo, y además su `assert "reason" not in ...` es un
assert de ausencia suelto, de los que pasan por accidente. Este **ejecuta** el SQL del gate:

```python
def test_el_gate_282_mide_de_verdad_y_respeta_el_corte():
    """El defecto no era el TEXTO, era que la query no CORRIA. Asi que se corre.
    Contra SQLite en memoria: no importa `db`, no toca la base del operador."""
    import importlib.util, sqlite3
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "scripts" / "gate_plan282.py"
    spec = importlib.util.spec_from_file_location("gate_plan282_bajo_test", ruta)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    # PRESENCIA (lo que TIENE que estar), guardada junto a la ausencia: un assert
    # de ausencia solo pasaria igual si la query se borrara entera.
    assert "error_message LIKE" in gate.K1_SQL
    assert "published_at > :corte" in gate.K1_SQL
    assert "reason LIKE" not in gate.K1_SQL

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE agent_html_publish "
              "(id INTEGER, status TEXT, error_message TEXT, published_at TEXT)")
    firma = ("ADO client build failed: AdoConfigError: El proyecto 'RIPLEY' "
             "no usa Azure DevOps (tracker_type=gitlab).")
    c.executemany("INSERT INTO agent_html_publish VALUES (?,?,?,?)", [
        (56, "failed", firma, "2026-08-01 16:16:42.530521"),   # historica
        (57, "failed", firma, "2026-08-01 20:24:43.801697"),   # historica
        (58, "failed", "otro error cualquiera", "2026-09-01 00:00:00"),
        (59, "ok",     firma,                    "2026-09-01 00:00:00"),
    ])
    sql = gate.K1_SQL.replace(":corte", "?")
    assert c.execute(sql, (gate.K1_CORTE_HISTORICO,)).fetchone()[0] == 0

    # Y ahora la mitad que de verdad importa: una REGRESION tiene que contar.
    c.execute("INSERT INTO agent_html_publish VALUES (60,'failed',?, '2026-09-02 00:00:00')",
              (firma,))
    assert c.execute(sql, (gate.K1_CORTE_HISTORICO,)).fetchone()[0] == 1
```

*Por qué no se abre `session_scope`: un test que lo hiciera escribiría en la base del
operador (§4.2). Por qué se ejecuta el módulo del gate con `importlib` en vez de copiar la
query: si el test copia el SQL, el test queda verde y el gate sigue roto — que es
literalmente el bug que estamos arreglando, un nivel más arriba.*

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
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -q   # 5 passed
./venv/Scripts/python.exe -c "
import sqlite3
c = sqlite3.connect('file:data/stacky_agents.db?mode=ro', uri=True)
q = (\"SELECT COUNT(*) FROM agent_html_publish WHERE status='failed' \"
     \"AND error_message LIKE '%no usa Azure DevOps%'\")
print('total historico:', c.execute(q).fetchone()[0])
print('sobre el corte :', c.execute(q + \" AND published_at > '2026-08-01 21:00:00'\").fetchone()[0])
"
```
→ el pytest, **5 passed** (los 4 de F0 más este); el snippet imprime
`total historico: 2` y `sobre el corte : 0`, sin excepción. Fijate en el `mode=ro`: la
verificación es **read-only por construcción**, no por promesa.

**El gate completo, y esta vez no es opcional** — es la única forma de probar que C3 quedó
cerrado. Corrélo **contra una copia** de la base, nunca contra la del operador:

```bash
cp data/stacky_agents.db "$TMPDIR/copia_286.db"
DATABASE_URL="sqlite:///$TMPDIR/copia_286.db" ./venv/Scripts/python.exe scripts/gate_plan282.py --json
echo "EXIT=$?"
```
→ `"K1": 0`, la nota del corte impresa debajo, `RESULTADO: exit 0` y **`EXIT=0`**.
**Antes de F6 eso mismo da** (reproducido el 2026-08-02):
```
"K1": "no_medible"   ...   la base no respondio: OperationalError   ...   exit 5
```
Y si te da `"K1": 2` con `exit 2`, hiciste **la mitad** del cambio: pusiste la columna y te
olvidaste el corte. **No lo "arregles" borrando filas** (§7.2) ni tocando `main()`.

**Flag:** ninguna. Un script de gate no se gatea.
**Impacto por runtime:** ninguno (herramienta de medición). Idéntico en los 3. Sin fallback.
**Trabajo del operador: ninguno.**

---

### F7 — `[ADICIÓN ARQUITECTO]` La contradicción deja rastro, en vez de corregirse en silencio

**Objetivo (1 frase):** que la próxima vez que un ticket tenga la columna en contra del
config de su proyecto, **el sistema lo diga** — en el log y en el catálogo de huellas — en
vez de que haga falta que alguien vuelva a abrir la BD viva a mano.

**Por qué esto y no otra cosa.** Todo el eje se apoya en una medición **manual** contra
`backend/data/stacky_agents.db` que nadie va a repetir: *"2 tickets de 228"*. Después de F4
esos 2 se rutean bien, pero **la contradicción sigue existiendo en la base** y el sitio que
la produce (los tickets sintéticos que nacen sin `tracker_type`) no se toca en este plan
(§7.9). Si mañana aparece un tercero, **no hay ninguna señal**: el ruteo lo corrige, el
operador nunca se entera y el próximo plan tiene que volver a medir a mano. Peor: la huella
que debería avisar **miente hoy** (C10). Esta fase cierra las dos puntas y es la única del
eje que agrega capacidad en vez de mover código de lugar.

**Archivos:**
- modifica `Stacky Agents/backend/services/project_context.py` (dentro de
  `tracker_efectivo_de_ticket`, la rama donde el config le gana a la columna)
- modifica `Stacky Agents/docs/sistema/error_fingerprints.json`
- agrega **2** tests a `tests/test_plan286_tracker_efectivo.py` y **1** a
  `tests/test_plan286_columna_no_rutea.py`

**(a) El rastro, deduplicado.** En la rama `if declarado:` de `tracker_efectivo_de_ticket`,
justo antes del `return declarado`:

```python
    if declarado:
        # Plan 286 F7 — la columna decia una cosa y el proyecto otra. Se rutea
        # bien (arriba) y ademas se DECLARA: una vez por (proyecto, columna,
        # declarado) por proceso, para que un backlog de 200 tickets no vomite
        # 200 lineas iguales. INFO, no WARNING: no es un error, es un dato que
        # hoy solo se consigue abriendo la base a mano.
        if columna and columna != declarado:
            clave = (raw_proyecto, columna, declarado)
            if clave not in _DIVERGENCIAS_VISTAS:
                _DIVERGENCIAS_VISTAS.add(clave)
                logger.info(
                    "tracker efectivo: proyecto=%s columna=%s efectivo=%s "
                    "(la columna no manda, Plan 286)",
                    raw_proyecto, columna, declarado,
                )
        return declarado
```

con `_DIVERGENCIAS_VISTAS: set[tuple[str, str, str]] = set()` y
`_reset_divergencias_vistas() -> None` a nivel de módulo, al lado del memo de F1, y
`raw_proyecto = (getattr(ticket, "stacky_project_name", None) or "").strip()`.

**Costos, uno por uno, para que nadie tenga que suponerlos:** cero I/O extra (el `declarado`
ya está resuelto en ese punto), cero llamadas de red, cero flags (un `logger.info` no es una
capacidad que se gatee — §4.0), cero trabajo del operador, y el `set` está acotado por
`|proyectos| × |valores de tracker|`, que en esta base es **3 × 3**.

**(b) La huella que hoy miente (C10).** En `docs/sistema/error_fingerprints.json`, la
entrada `plan282-comentario-no-llega-al-tracker-gitlab` dice `"status": "resolved"`,
`"date_resolved": "2026-08-01"` y `"killed_commit": null`. **La BD viva la desmiente:** la
fila 57 de `agent_html_publish` tiene esa firma exacta a las `2026-08-01 20:24:43`, **28
minutos después** del commit del fix (`3461d0ce`, `19:56:02`). Quien vea esa fila va a
reabrir un bug cerrado. Dos ediciones, **sin tocar `status`** (queda `resolved`, que es
correcto: el defecto de código está muerto):

- `"killed_commit": "3461d0ce"` — hoy `null`.
- agregar el campo `note` (ya existe en el esquema del catálogo, junto con `evidence`):
  `"Plan 286 §2.3(d): la fila 57 de agent_html_publish (2026-08-01 20:24:43) es POSTERIOR al fix — la emitio un backend arrancado antes de 3461d0ce y nunca reiniciado. NO es una reaparicion. La linea base del KPI queda congelada en gate_plan282.K1_CORTE_HISTORICO."`

**Y la huella nueva del 286**, que es la que va a agarrar al tercer ticket mentiroso:

```json
{
  "id": "plan286-columna-tracker-contradice-al-proyecto",
  "title": "Un ticket declara un tracker distinto del que declara su proyecto",
  "class": "silent-wrong-destination",
  "status": "guarded",
  "log_pattern": "tracker efectivo: proyecto=\\S+ columna=\\S+ efectivo=\\S+",
  "log_guarded": true,
  "killed_by": "plan 286 F1-F4",
  "killed_commit": null,
  "date_resolved": null,
  "guard_test": "tests/test_plan286_tracker_efectivo.py",
  "note": "No es un error: el ruteo YA lo corrige (tracker_efectivo_de_ticket). Es la senal de que la columna `tickets.tracker_type` sigue naciendo con el default 'azure_devops' en proyectos que no son ADO (models.py:49). Si aparece seguido, el plan que corresponde es el de §7.3 (cambiar el default del esquema), no volver a parchear el ruteo.",
  "self_test": {
    "matches": ["INFO stacky_agents.project_context tracker efectivo: proyecto=RIPLEY columna=azure_devops efectivo=gitlab (la columna no manda, Plan 286)"],
    "clean": ["INFO stacky_agents.project_context tracker efectivo: proyecto=RIPLEY columna=gitlab efectivo=gitlab"]
  }
}
```

> `"guarded"` **sí** es un valor legítimo de este catálogo: medido el 2026-08-02, los
> `status` en uso son `by_design`, `guarded`, `open`, `resolved` (61 huellas). Aun así,
> **antes y después de tocar el JSON corré `tests/test_error_fingerprints_catalog.py` y
> exigí el mismo número de passed/failed**: si esa suite tiene rojos de fábrica, no son
> tuyos y no se arreglan acá.

**Tests (exactamente 3):**

| # | archivo | test | esperado |
|---|---|---|---|
| 15 | `test_plan286_tracker_efectivo.py` | `test_la_divergencia_se_loguea_una_sola_vez` | con `caplog` en INFO, **10** llamadas con el mismo ticket de RIPLEY mentiroso ⇒ **1** sola línea con `"la columna no manda"` |
| 16 | `test_plan286_tracker_efectivo.py` | `test_sin_divergencia_no_se_loguea_nada` | ticket de RIPLEY con `tracker_type='gitlab'`, y ticket de RSPACIFICO con `'azure_devops'` ⇒ **0** líneas. *Guarda la PRESENCIA del 15: un assert de "no loguea" solo pasaría igual si el log no existiera* |
| 17 | `test_plan286_columna_no_rutea.py` | `test_la_huella_del_286_esta_en_el_catalogo` | el JSON parsea; existe `plan286-columna-tracker-contradice-al-proyecto`; su `log_pattern` **matchea** el `self_test.matches[0]` y **no** matchea el `clean[0]` (con `re.search`); y `plan282-...` tiene `killed_commit == "3461d0ce"` |

**Criterio de aceptación BINARIO:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan286_tracker_efectivo.py -q   # 16 passed
./venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -q   # 6 passed
./venv/Scripts/python.exe -m pytest tests/test_error_fingerprints_catalog.py -q # mismo resultado que antes de tocar el JSON
```

**Flag:** ninguna. Es un `logger.info` y una entrada de catálogo: solo lectura, no publica,
no escribe en ningún sistema del operador, no le saca ninguna decisión. Nace **ON** porque
no cae en (A) ni en (B).
**Impacto por runtime:** idéntico en los 3 (§4.4). Sin fallback.
**Trabajo del operador: ninguno.** No hay pantalla, no hay alerta, no hay que hacer nada
con la línea de log: está ahí para cuando alguien pregunte.

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
F2#2, F3#8, F4#11/#13), más correr las suites de origen (`test_plan270_write_router.py`
**14**, `test_plan271_writer_routed.py` **13**, `test_plan282_publicacion_comentario.py`
**7**, `test_plan281_sitios_ado_only.py` **18**) y exigir **exactamente esos números**, que
están medidos en §4.6 y no "los mismos que antes" (C6). Más el kill-switch
`ruteo_estricto_por_tracker()` como rollback de una sola palanca, con su propio test
(F1#10, F2#6). *Y el radio está acotado por dato: no existe ningún proyecto que declare
`jira` ni `mantis`, así que ninguna fila cambia de "iba a ADO" a "levanta
`CapabilityUnavailable`" — Anexo B.*

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

**R8 — El registro en lote de F0 pone rojas dos suites AJENAS (C2). CORREGIDO en v2.**
La v1 registraba los tres archivos en F0 y llamaba a eso *"un rojo esperado y acotado al
eje"*. Medido: no es acotado — rompe
`test_harness_ratchet_meta::test_ratchet_no_referencia_archivos_inexistentes` (hoy PASSED) y
`test_plan259_ratchet_script_parity::test_ninguna_ruta_apunta_a_un_archivo_inexistente` (hoy
dentro de un `12 passed`), que son gates compartidos de todo el repo y que una sesión
paralela puede correr. **Mitigación: §4.3 — registro por fase**, en el mismo commit que crea
el archivo. Lo único que queda rojo entre F0 y F4 es el propio
`test_plan286_columna_no_rutea.py`, que nace rojo **a propósito** y sólo dentro del eje.
*Sigue valiendo: F0 sin F4 es deuda, no un entregable cerrado.*

**R9 — El helper mete un `json.loads` por ticket en un loop por ticket (C5).** Medido:
`get_project_config` cuesta **858-1074 µs** y no cachea; `_tracker_type_for` se llama **2
veces por ticket** dentro de `_resolve_ci_result`, que corre en un loop en
`api/tickets.py:1499`. **Mitigación:** el memo revalidado por `mtime` de §5.F1, con criterio
binario propio (**< 400 µs/llamada**, línea base 1.057 µs) y tres tests (12, 13, 14).
*Atenuante medido: el camino está detrás de `STACKY_PIPELINE_PROVIDER_ENABLED`, hoy `False`
(`api/tickets.py:480`) — está dormido, pero no se deja armado.*
*Riesgo del propio memo: quedar stale y rutear al tracker viejo. Por eso se revalida con
`os.stat` (132 µs) y **no** con TTL ni `lru_cache` — §7.10.*

**R10 — F6 arregla la columna y deja el gate del 282 rojo para siempre (C3).** Ver §2.3(g):
`main()` compara contra `0` hardcodeado. **Mitigación:** el corte histórico vive **dentro**
del gate (`K1_CORTE_HISTORICO`), la nota se imprime debajo del KPI, y el criterio de §5.F6
exige correr el gate completo contra **una copia** y ver `exit 0`. *Si alguien "resuelve"
esto borrando filas o tocando `main()`, rompió §7.2 y el propósito del gate.*

**R11 — El centinela de F0 verde por ausencia de la función (C1).** Ver el recuadro de
§2.3(e). **Mitigación:** las dos patas de §5.F0 y la calibración
`test_el_centinela_no_se_calla_si_la_funcion_desaparece`, que prueba **los dos** lados: que
la pata 1 se calla y que la pata 2 grita. *Es la mitigación más importante del plan: sin
ella, F4 declara el hito del eje sobre un gate que ya no puede fallar.*

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
10. **Cambiar el memo de F1 por un TTL, un `lru_cache` o una caché global de configs.** El
    memo se revalida con `os.stat` **a propósito**: el operador cambia `issue_tracker.type`
    por UI y cualquier caché que no mire el archivo dejaría a Stacky escribiendo en el
    tracker viejo — el mismo defecto que este plan mata, con otra causa. Tampoco se toca
    `project_manager.get_project_config` (17 consumidores ajenos, radio no medido): el memo
    vive **sólo** dentro de `tracker_declarado_del_proyecto`.
11. **Agregar una rama `gitlab` al `if/elif/else` de `_resolve_sync_and_project`.** Ver C9:
    el callable que devuelve esa función **no lo consume nadie** (`completion_sync.py:165`
    lo descarta) y la rama GitLab del sync ya vive en `_do_project_sync:116-119`.
12. **Arreglar el rojo de fábrica de `test_harness_ratchet_meta.py`**
    (`test_allowlist_no_se_solapa_con_ratchet`, `tests/test_docs_api.py` duplicado en el
    ratchet y en la allowlist). Es deuda ajena y anterior; tocarla acá es scope creep sobre
    terreno de otro plan. Ver §4.6.

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
  todo el backend. No sufre las 3 capas de ceguera del detector del Plan 281. **Tiene DOS
  patas** (ausencia + presencia): con una sola quedaría verde por haber borrado la función
  vigilada, que es el modo de falla que mató a la v1 (C1).
- **Pata de presencia** — la mitad del centinela que exige que el archivo **llame** a
  `tracker_efectivo_de_ticket`. Existe porque *un `assert` de ausencia pasa por accidente*:
  la única forma de que un "no lee la columna" signifique algo es guardar, en el mismo test,
  qué **sí** tiene que estar.
- **Corte histórico (`K1_CORTE_HISTORICO`)** — `"2026-08-01 21:00:00"`, en
  `gate_plan282.py`. Instante posterior a la última publicación fallida conocida (fila 57,
  `2026-08-01 20:24:43`). K1 sólo cuenta lo que pasó **después**: así el KPI vuelve a su
  meta `0` sin borrar nada, y cualquier falla nueva sí cuenta. **No es un `!= 0` disfrazado:
  es una línea base declarada, con fecha y motivo.**
- **Memo por `mtime`** — la caché de `tracker_declarado_del_proyecto`, revalidada con un
  `os.stat` (132 µs) en vez de releer el JSON (858-1.074 µs). **No es un TTL:** un TTL
  dejaría a Stacky escribiendo en el tracker viejo después de que el operador lo cambia
  por UI.
- **`NO MEDIBLE`** — sentinela de `gate_plan282.py:30`. **No es un 0.** Un gate que devuelve
  `NO MEDIBLE` no falla, y por eso puede tapar un bug durante semanas (§2.3(f)).
- **Client-shaped** — un adaptador que expone la forma del cliente ADO envolviendo otro
  provider. Es lo que construyó el Plan 282 en `comment_publish_router.py`.

---

## 9. Orden de implementación y Definición de Hecho

### Orden (estricto)

| Fase | Qué entrega | Rojo→Verde | Registro en ratchets |
|---|---|---|---|
| F0 | Centinela dirigido de **dos patas** (ausencia + presencia) | nace **ROJO**: **2 failed, 2 passed** | `test_plan286_columna_no_rutea.py` |
| F1 | `tracker_declarado_del_proyecto` + `tracker_efectivo_de_ticket` + memo por `mtime` | **14 passed** y **< 400 µs/llamada** | `test_plan286_tracker_efectivo.py` |
| F2 | `tracker_write_router` usa el helper | **6 passed**; 270→14, 271→13, ratchet 270→6, 281 sitios→18 | `test_plan286_ruteo_de_escritura.py` |
| F3 | `comment_publish_router` usa el helper | **9 passed**; 282 publicación→7 | — |
| F4 | `completion_sync` + `api/tickets._tracker_type_for` usan el helper | **13 passed**, **F0 pasa a 4 passed** y el censo `getattr` baja **8 → 7** | — |
| F5 | Sale la exclusión de `tracker_write_router` del censo | 281 ratchet→11, 281 sitios→18 | — |
| F6 | `gate_plan282`: columna **y** corte histórico | **5 passed** y el gate completo en **`exit 0`** con `K1 = 0` | — |
| F7 | `[ADICIÓN ARQUITECTO]` rastro deduplicado + huellas del catálogo | **16 passed** / **6 passed** | — |

Commit por fase, con pathspec explícito. Mensaje sugerido:
`feat(plan-286): F<N> — <qué hace>`.

### Definición de Hecho

- [ ] `tests/test_plan286_columna_no_rutea.py` → **6 passed** (4 de F0 + 1 de F6 + 1 de F7).
- [ ] `tests/test_plan286_tracker_efectivo.py` → **16 passed** (14 de F1 + 2 de F7).
- [ ] `tests/test_plan286_ruteo_de_escritura.py` → **13 passed**.
- [ ] Los 3 archivos figuran en `run_harness_tests.ps1` **y** en `run_harness_tests.sh`,
      como `tests/...` sin espacios, **y ninguna fase intermedia dejó registrada una ruta
      inexistente** (§4.3).
- [ ] `--collect-only -q` de cada archivo imprime el número declarado (**nunca 0**).
- [ ] Suites de no-regresión, **con los números medidos de §4.6** (no "los mismos que
      antes"): `test_plan270_write_router.py` **14**, `test_plan270_state_write_ratchet.py`
      **6**, `test_plan271_writer_routed.py` **13**,
      `test_plan282_publicacion_comentario.py` **7**, `test_plan281_ratchet_ado_only.py`
      **11**, `test_plan281_sitios_ado_only.py` **18**,
      `test_plan259_ratchet_script_parity.py` **12**, `test_harness_ratchet_meta.py`
      **1 failed / 3 passed** (rojo de fábrica ajeno, §4.6 y §7.12).
- [ ] `scan_tracker_type_routing()` sigue devolviendo `[]` y
      `_ROUTING_EXCLUDED_FILES == frozenset({'services/project_context.py'})`.
- [ ] El censo `getattr`-extendido de §5.F4 imprime **7** (antes del eje: **8**) y
      `services/completion_sync.py::_resolve_sync_and_project` ya no aparece.
- [ ] En vivo: `tracker_efectivo_de_ticket(SimpleNamespace(tracker_type='azure_devops',
      stacky_project_name='RIPLEY'))` → `'gitlab'`; con `'RSPACIFICO'` → `'azure_devops'`.
- [ ] **Performance (C5):** el bucle de §5.F1 imprime **< 400 µs/llamada** (línea base sin
      memo: 1.057 µs).
- [ ] `scripts/gate_plan282.py --json` **contra una copia** de la base: `"K1": 0`,
      `RESULTADO: exit 0`. Ni `no_medible` (era el bug) ni `2` (sería el fix a medias).
- [ ] El contador `error_message LIKE '%no usa Azure DevOps%'` medido con `mode=ro` sigue
      en **2** en total y en **0** sobre el corte (no bajó porque no se borró nada, no subió
      porque no hay regresión).
- [ ] `docs/sistema/error_fingerprints.json` parsea, tiene la huella
      `plan286-columna-tracker-contradice-al-proyecto` y `plan282-...` ya no dice
      `killed_commit: null`; `tests/test_error_fingerprints_catalog.py` da el mismo
      resultado que antes de tocar el JSON.
- [ ] **Cero flags nuevas** registradas: `git diff` no toca `config.py` ni
      `services/harness_flags.py`.
- [ ] **Cero escrituras en la BD**: `git status` no muestra `backend/data/` modificado y no
      se ejecutó ningún `UPDATE`/`DELETE`. Toda consulta a la base viva fue con
      `?mode=ro` o contra una **copia**.
- [ ] **Cero archivos de la sesión paralela tocados** (§6.R7).
- [ ] Los docstrings de `resolve_state_writer`, `resolve_comment_publisher` y
      `scan_tracker_type_routing` describen el comportamiento **nuevo**.

---

## Anexo A — Anclajes: **re-verificados por el juez el 2026-08-02**

Todos abiertos y confirmados contra el árbol en `docs/plan-279`. Los anclajes de línea
caducan: **anclá por símbolo** y confirmá antes de editar.

**Resultado de la re-verificación: 16/16 anclajes de la v1 OK, salvo uno DESFASADO por 1
línea** (`completion_sync.py:93-95` → **`:94-96`**, corregido en §5.F4). *Y eso es
exactamente lo que hace instructiva a esta crítica: los cinco bloqueantes no vinieron de un
anclaje mal puesto. Vinieron de **mecanismos que la evidencia correcta no cubría** — qué
hace `main()` con el número, qué pasa con la función vigilada cuando la borrás, cuánto
cuesta la llamada que agregás. Verificar dónde mirás no prueba que hayas mirado lo
suficiente.*

**Anclajes NUEVOS de la v2** (todos abiertos y confirmados el 2026-08-02):

| Anclaje nuevo | Para qué |
|---|---|
| `scripts/gate_plan282.py::main`, `fuera = [... if v is not NO_MEDIBLE and v != 0]` y el rótulo `(meta 0)` | C3 — la meta hardcodeada que convierte el fix en `exit 2` |
| `tests/test_harness_ratchet_meta.py:79-80` `test_ratchet_no_referencia_archivos_inexistentes` | C2 |
| `tests/test_harness_ratchet_meta.py:43` `test_ratchet_clasifica_todos_los_tests` | C2 — la otra mitad de la pinza |
| `tests/test_plan259_ratchet_script_parity.py:101-103` `test_ninguna_ruta_apunta_a_un_archivo_inexistente` | C2 |
| `project_manager.py:55-62` `get_project_config` (sin caché) | C5 |
| `api/tickets.py:1499` (`_resolve_ci_result` en loop por ticket) y `:480` (`STACKY_PIPELINE_PROVIDER_ENABLED`, default `False`) | C5 y su atenuante |
| `services/completion_sync.py:165` (`_, project, tracker_type = ...`) | C9 — el callable está muerto |
| `services/provider_coupling_audit.py:142` `TRACKER_GUARDS` contiene `"_tracker_type_for"` | C11 — no renombrar |
| `api/client_profile.py:85` `_tracker_type_for` (homónimo, **otra** función) | C11 — no confundir |
| `services/provider_coupling_audit.py:201-217` `_archivos_censables` = `backend/*.py` + `api/*.py` + `services/*.py` | acota el censo de §7.4 |
| `config.py:1419-1421` `STACKY_TRACKER_ROUTING_STRICT_ENABLED` = `os.getenv(..., "true") in ("1","true","yes")` y `services/harness_flags.py:5871` `default=True` | §4.0 — el kill-switch reusado **es** default ON, leído del `os.getenv`, no del comentario |
| `services/project_context.py:440-447` `__all__` (6 entradas, sin los dos helpers) | §5.F1 — no tocarlo |
| `docs/sistema/error_fingerprints.json` — 61 huellas; `status` en uso: `by_design`, `guarded`, `open`, `resolved` | §5.F7 |

| Anclaje de la v1 | Estado |
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

---

## Anexo B — Las cinco afirmaciones medibles de la v1, **reproducidas ejecutando** (2026-08-02)

El juez no le creyó al plan: corrió las cinco. **Las cinco dieron CONFIRMADA.** Se dejan
acá con la evidencia para que nadie las tenga que volver a medir.

| # | Afirmación de la v1 | Veredicto | Evidencia ejecutada |
|---|---|---|---|
| 1 | Las 2 filas `failed` son `ado_id` 1116 y 1120, con `tracker_type='gitlab'` **correcto**; no las causa la columna sino el publicador sin el fix del 282 | **CONFIRMADA** | Copia read-only de `backend/data/stacky_agents.db`: filas `id=56` (`ticket_id=1171`, `ado_id=1116`, `output_watcher_mode_b`, `2026-08-01 16:16:42`) e `id=57` (`ticket_id=1373`, `ado_id=1120`, `2026-08-01 20:24:43`), ambas con `"ADO client build failed: AdoConfigError: El proyecto 'RIPLEY' no usa Azure DevOps"`. Los tickets 1171 y 1373 tienen `tracker_type='gitlab'`. Y son **las únicas 2** filas `failed` de la tabla |
| 2 | `gate_plan282.py:202` consulta `reason`, que no existe; el `except` se lo traga y K1 da `NO MEDIBLE` siempre | **CONFIRMADA** | `PRAGMA table_info` no lista `reason`; la query cruda da `OperationalError: no such column: reason`; con `error_message` da **2**. Y el **gate real**, corrido contra la copia: `"K1": "no_medible"` / `la base no respondio: OperationalError` / `RESULTADO: exit 5` |
| 3 | `scan_tracker_type_routing()` devuelve `[]` con los 4 sitios vivos; ampliarlo a `getattr` abre **8** hallazgos ajenos | **CONFIRMADA, y el 8 es exacto** | El scan real devuelve `[]`. Con la regla extendida a `getattr` devuelve **8**, y la lista coincide **verbatim** con la de §7.4 (`api/devops_production.py::_do_ensure`, `api/tickets.py::_sync_via_provider_or_ado`, los 4 `ci_*`, `services/completion_sync.py::_resolve_sync_and_project`, `services/tracker_provider.py::get_tracker_provider`). Sólo **1 de los 4** sitios del eje está ahí — los otros 3 son intra-función, como dice el plan |
| 4 | `models.py:49` declara `default="azure_devops"`, y por eso la precedencia tiene que ser *no vacía Y distinta del default*; los tests rojo-primero fallan hoy | **CONFIRMADA** | `models.py:49` textual. Y el rojo, **ejecutado** contra el código actual: F2#1 → `kind='ado_client'` (se esperaba `provider`), F2#5 preview → `'azure_devops'` (se esperaba `'gitlab'`), F3#7 → `'ado_client'`, F4#10 → `'azure_devops'`, F1 → `ImportError: cannot import name 'tracker_efectivo_de_ticket'`. **Ninguno pasa hoy**. Y en vivo `tracker_is_azure_devops`: RIPLEY `False`, RSPACIFICO `True`, `None` `True` |
| 5 | Sacar la exclusión de `tracker_write_router.py` tiene efecto **cero** | **CONFIRMADA** | `scan_tracker_type_routing()` con `_ROUTING_EXCLUDED_FILES = {'services/project_context.py'}` → `[]` |

**Radio de impacto de §1, re-medido y exacto** (228 tickets, coincide con la tabla del
plan): RIPLEY 63 `gitlab` + **2 `azure_devops`** (ids 1167 `ado_id=-1` "[Stacky] Brief Pool"
y 1378 `ado_id=-7` "[Documentador] RIPLEY"), RSPACIFICO 57, `p` 49, `P` 44, ONP 6, RSSICREA
3, `__demo__` 3 `demo`, `test` 1. Distintos valores de la columna: `azure_devops` **162**,
`gitlab` 63, `demo` 3, **`NULL` 0**. Configs de proyecto que existen: **sólo 3** — RIPLEY
`gitlab`, RSPACIFICO `azure_devops`, RSSICREA `azure_devops`. *Consecuencia que la v1 no
hacía explícita y conviene dejar escrita: **no hay ningún proyecto que declare `jira` o
`mantis`**, así que no existe el caso "la columna dice ADO, el config dice mantis y el
`resolve_state_writer` pasa a levantar `CapabilityUnavailable` donde antes iba a ADO". El
radio es 2 y no hay cola oculta.*
