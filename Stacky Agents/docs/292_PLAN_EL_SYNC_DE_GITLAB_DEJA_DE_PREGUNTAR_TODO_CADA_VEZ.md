# Plan 292 — El sync de GitLab deja de preguntar todo cada vez

**Estado:** **v2 — IMPLEMENTADO (F0..F6, todas las fases IMPLEMENTADA).** 2026-08-02, rama `docs/plan-279`, sin push.

## Estado de implementación por fase

| Fase | Estado | Commit | Evidencia |
|---|---|---|---|
| **F0** — baselines y ratchets | **IMPLEMENTADA** | (verificación, sin commit propio) | los **21** baselines de §4 re-corridos y **coincidentes uno por uno**; brecha 831 − 767 = **64**; `FLAG_REGISTRY` = **493**; el array del `.ps1` **cargado** (no grepeado) = 767 |
| **F1** — `TrackerQuery.updated_after` | **IMPLEMENTADA** | `7db4b8d3` | 3 passed (rojo previo: `TypeError` por el kwarg inexistente) |
| **F2** — el store de la marca | **IMPLEMENTADA** | `5314f5c3` | **17** passed (rojo previo: `ModuleNotFoundError`). Mitad de contraste de la marca monótona **ejecutada y fallando** |
| **F3+F4** — las opciones y su consumidor | **IMPLEMENTADA** | `50496f73` | flags 12 passed (rojo previo 11F/1P); `FLAG_REGISTRY` 493 → **495**; grep de las 2 keys en `app.py` = **0** |
| **F5** — el gate de correctitud | **IMPLEMENTADA** | `94a6245d` | **22** passed. **Las CINCO mitades de contraste ejecutadas y fallando**, parches revertidos (`git diff` vacío) |
| **F6** — paridad, docs y no-regresión | **IMPLEMENTADA** | `e3dab299` | 6 passed + **5 mitades de contraste propias**; delta cero en los 14 baselines verdes y los 7 rojos de fábrica medibles |

**Desvíos respecto del plan, medidos al implementar (ninguno cambia el alcance):**

1. **`bytes_recibidos` con la tanda vacía daba 2, no 0.** `json.dumps([])` son los dos bytes de `"[]"`, que son **envoltorio y no carga**: el criterio `== 0` de §F5 caso 20 era **insatisfacible** tal como estaba escrito el snippet de §F4.6. Se cuenta 0 cuando no hay ítems, y queda documentado en el código.
2. **La barrera pagaba un `SELECT` por ítem también en modo COMPLETO** (63 por sync en RIPLEY) para una respuesta que `admitir_del_delta` no mira. El propio plan declaraba el costo como *"sólo en modo parcial"*; el código quedó gateado para que eso sea cierto.
3. **Contaminación de `backend/data/` NO prevista por el plan.** `tests/test_plan276_gitlab_sync.py` ejercita el sync entero y aísla la BD por `DATABASE_URL`, pero **no** aísla `data_dir()`: apenas el sync empezó a guardar la marca, esa suite **ajena** dejó un `gitlab_sync_watermark.json` **real** en la carpeta del operador (medido). No alcanzaba con *"es gitignored y degrada a completo"*: una marca escrita por un test podía quedar lo bastante **fresca** como para que la primera corrida real del operador saliera **parcial** apoyada en un reloj inventado — eso es correctitud, no higiene. Se agregó un guard de modo test (idioma de `services/error_fingerprints.py:95-100`) y su caso ⇒ F2 pasa de **16** a **17** casos.
4. **F5 da 22 passed, no 21.** La tabla de casos de §F5 lista **22 tests nombrados** (numera 1..21 con un `4b` intercalado). No falta ni sobra ningún caso; el número de la DoD estaba corrido en uno.
5. **F6 sumó 5 mitades de contraste que el plan no pedía.** Los 6 casos de paridad pasaron **en verde a la primera** —el molde clásico del falso verde—, así que se corrió cada invariante contra su defecto: un runner nombrando `gitlab`, el arranque sin forzar, el pedido manual sin forzar, el poll forzando, y un **cuarto llamador por alias**. Los cinco fallaron como debían.

**Pendiente del operador: ninguno.**

---

**Versión:** v1 → v2 (2026-08-02). Ver el **CHANGELOG v1→v2** al final (§11).
**Fecha:** 2026-08-02
**Rama en la que se escribió:** `docs/plan-279`

> **Sello de revisión:** `Juez v2: subagente independiente, misma corrida, contexto limpio`.
> La v1 fue rechazada con **101 de 104 anclajes correctos**. El defecto no estaba en dónde miraba, sino en **qué escenario eligió como representativo**: al probar el modo parcial con una tanda **vacía**, su gate central quedó satisfecho por un `if` que ya existía antes del plan, y su mitad de contraste dejó de poder fallar. Los cuatro bloqueantes se verificaron **ejecutando** `sync_gitlab_tickets` contra el código de hoy (§0).
**Alcance:** backend. **Cero frontend. Cero migraciones de esquema. Cero escritura en la base del operador.**
**Depende de:** Plan 276 F5 (`services/gitlab_sync.py`, el sync entero), Plan 277 F2/F4/F6 (`_upsert_ticket_gitlab`, la clasificación local, el traído de padres), Plan 281 F4 (el ruteo de arranque), Plan 286 (`tracker_efectivo_de_ticket`), Plan 253 F5 (`services/maintenance.py`, el punto de extensión periódico)
**Frontera con planes hermanos en vuelo:** sesión paralela VIVA sobre los planes 287/288 (34 archivos sucios al escribir esto). Ninguno de los archivos que este plan toca está en esa lista. Ver §3.7.

> Todo número, ruta y línea de este documento se midió **abriendo el archivo o ejecutando el comando** el 2026-08-02 sobre `docs/plan-279`. Las mediciones que **no** pudieron hacerse sin tocar el GitLab del operador están marcadas **NO VERIFICABLE DESDE EL REPO** y no se usan como criterio.

---

## 0. Lo que se EJECUTÓ contra el código de hoy (v2)

Antes de corregir nada, se corrió `sync_gitlab_tickets` **sin ninguna modificación del plan**, con un proveedor doble y una base SQLite en un temporal aislado. Tres escenarios, salida literal:

```
== A) el "caso central" de la v1: corrida 2 con TANDA VACIA ==
   corrida1 created=3  corrida2 removed=0  filas=[(1,'opened'),(2,'opened'),(3,'opened')]

== B) el escenario REAL de R1: corrida 2 con TANDA PARCIAL (1 de 3) ==
   corrida2 removed=2  filas=[(1,'opened'),(2,'closed'),(3,'closed')]

== C) state='all': un CERRADO desconocido en el delta ==
   corrida2 created=1 removed=0  filas=[(1,'opened'),(77,'closed')]
```

Qué prueba cada uno, y qué se corrigió por eso:

| | Lo que se midió | Consecuencia |
|---|---|---|
| **A** | Con la tanda vacía, el código de **hoy** —con la regla de ausencia SIN gatear— ya devuelve `removed=0` y deja las 3 filas en `opened` | El caso 4 de la v1 y su mitad de contraste **no podían fallar**. Corregido en §F5: el caso central usa ahora una tanda **parcial no vacía** |
| **B** | Un delta de 1 ítem sobre 3 filas **cierra 2** | Es R1 materializado, y la v1 **no tenía ningún caso** que lo cubriera. Corregido: §F5 caso 5 |
| **C** | Un cerrado desconocido en el delta **crea una fila nueva** (`created=1`) | `state="all"` no sólo *lee* distinto: **escribe filas que hoy no existen**. Corregido con la barrera de admisión de §3.1-bis |

> El código de la sonda vivió en el scratchpad de la sesión, nunca en el repo, y la base del operador se leyó **sólo** por una copia `VACUUM INTO` en modo `ro`.

---

## 1. Objetivo, y el KPI honesto

**Objetivo:** que el sync de GitLab deje de pedir el listado completo de issues abiertos en cada corrida, y pida **sólo lo que cambió desde la última vez**, sin perder ni una sola de las garantías de correctitud que tiene hoy.

### 1.1. El KPI, corregido contra la medición

El enunciado de trabajo de este plan proponía *"hoy ~90 requests por sync, meta <10"*. **Se midió y ese número es falso para el estado actual de RIPLEY.** Queda corregido acá, porque un plan que arranca con un KPI inalcanzable o ya cumplido se cae solo en la implementación:

| # | Indicador | Hoy (**medido** 2026-08-02) | Meta | Cómo se mide |
|---|---|---|---|---|
| **K1** | **Bytes** que GitLab serializa y manda en un sync **en estado estable** (nada cambió) sobre RIPLEY | **~205 KB** (medido, ver abajo) | **~0** | **PROYECCIÓN.** El doble de §F5 sólo prueba el *mecanismo* (`fetched == 0`); el byte real depende del servidor y **no se puede medir sin consultarlo**. Ver K6 |
| **K2** | Filas marcadas `ado_state="closed"` por un sync **incremental** con un delta **parcial no vacío** | **2 de 3 en la sonda §0-B** (o sea: la regla de hoy SÍ cierra) | **0, siempre** | §F5 caso 4 — criterio de **correctitud**, y el único que decide el plan |
| **K2b** | Filas **creadas** por un sync incremental a partir de un ítem que ya venía `closed` y **no existe** localmente | **1 en la sonda §0-C** | **0, siempre** | §F5 caso 6 — el segundo criterio de correctitud (§3.1-bis) |
| **K3** | Requests HTTP de listado por sync sobre RIPLEY | **1** (63 abiertos < `per_page=100` ⇒ una sola página) | **1** (sin cambio) | §F5, contador de llamadas |
| **K4** | Requests HTTP de listado por sync sobre un proyecto de 4.000 issues abiertos | 40 (el techo de `_DEFAULT_PAGE_CAP`) | **1** en estado estable | **PROYECCIÓN, no medición.** No hay ningún proyecto así en la base; **no** es criterio de aceptación |
| **K5** | `secondsSince(last_synced_at)` medio sin intervención | ~45 s con el tablero abierto; **sin cota** con el tablero cerrado | — | **NO MEDIBLE en este plan.** El disparador periódico que lo mejoraría queda **fuera de scope** (§6.1) |
| **K6** | `bytes_recibidos` que el propio sync reporta en su dict de retorno y en su log | no existe | existe, y en estado estable baja a **0** | **[ADICIÓN ARQUITECTO]** §F4.6 — convierte K1 de proyección en algo que el operador mide **en su propia corrida**, sin que nadie consulte GitLab |

**K1 es el KPI del plan, y la unidad correcta es BYTES, no issues ni requests.** Medido sobre la copia `VACUUM INTO` de la base viva:

| Métrica de carga | Valor medido 2026-08-02 |
|---|---|
| `description` de los 63 issues de RIPLEY | **111.685 bytes** (promedio **1.773 B**, máximo **14.800 B**, **0** vacías) |
| `title` de los 63 | 3.340 bytes |
| Payload estimado por sync (los dos anteriores + ~1,5 KB de metadata por issue) | **~205 KB** |
| Con el tablero abierto: 80 corridas/hora | **~16 MB/hora** contra el GitLab de la empresa |

El navegador dispara un sync cada **45 s** (`frontend/src/hooks/useTicketSync.ts:40`, `DEFAULT_INTERVAL_MS = 45_000`, importado con alias en `frontend/src/pages/TicketBoard.tsx:12` y consumido en `:1030`). Cada corrida hace que GitLab **renderice y serialice los 63 issues completos** aunque el delta sea cero.

> ⚠️ **Corrección de la v1.** La v1 decía *"K1 es 63 issues → 0"*. Contar issues esconde el número que importa: **el 54 % del payload son descripciones en markdown**, y una sola llega a 14,8 KB. Y el plan **no baja requests** (K3 es 1 hoy y 1 después): baja **bytes**. Decirlo en la unidad equivocada es lo que hizo que el enunciado original creyera que había 90 requests que ahorrar.

### 1.2. La alternativa de una línea, y por qué igual conviene este plan

Un plan que agrega un store en disco, dos opciones con ocho guardianes cada una y una **inversión semántica de la query** debe compararse contra la alternativa barata, o el operador no puede decidir. Se compara:

| Opción | Cambio | Ahorro sobre los ~16 MB/h | Superficie de riesgo |
|---|---|---|---|
| **Subir el intervalo del poll** de 45 s a 180 s (`useTicketSync.ts:40`) | **una línea** | **75 %** (~4 MB/h) | **cero**: no toca la semántica del sync | 
| **Este plan** | 4 archivos nuevos + 6 tocados, 2 opciones, 8 guardianes ×2 | **~100 %** en estado estable | apagar la regla de ausencia + `state="all"` (§3.1 y §3.1-bis) |
| Las dos juntas | | ~100 %, y además baja la frescura pedida | |

**El plan sigue valiendo la pena, con dos condiciones que la v1 no cumplía:** (1) que el ahorro se mida en bytes y no en requests —hecho arriba—, y (2) que la inversión semántica venga con **las dos** barreras de correctitud probadas ejecutando (§3.1 y §3.1-bis), no una. Sin (2), el plan cambia ~16 MB/h de ancho de banda interno por corrupción del tablero: un mal negocio.

**Subir el intervalo NO es alcance de este plan** (§6.2 mantiene el frontend intacto y `endpoints.ts` está sucio por la sesión paralela), pero queda **anotado como recomendación independiente para el operador**, porque es más barato que todo esto junto.

---

## 2. Por qué ahora — el gap, con evidencia abierta

### 2.1. La query es completa, siempre, y `updated_after` no existe en el repo

```
services/gitlab_sync.py:257    items = provider.fetch_open_items(TrackerQuery(state="open"))
```

`TrackerQuery` es un `@dataclass(frozen=True)` declarado en `services/tracker_provider.py:21-28` con exactamente seis campos: `state`, `labels`, `milestone`, `assignee`, `search`, `parent_id`. **No hay ningún campo de fecha.** Y su traductor a parámetros de GitLab, `_query_to_gitlab_params` (`services/gitlab_provider.py:122-136`), sólo mapea esos seis.

Verificado por búsqueda: **`updated_after` tiene 0 hits en todo `backend/` y todo `frontend/src/`.**

### 2.2. El dato para hacerlo incremental YA llega, y se tira a la basura

`_normalize_issue` emite el `updated_at` del issue:

```
services/gitlab_provider.py:162        "updated_at": body.get("updated_at") or "",
```

Ese dict es el que consume `sync_gitlab_tickets`… y `_upsert_ticket_gitlab` **nunca lo lee**. Verificado: en `services/gitlab_sync.py` hay **cero** referencias a `updated_at`; sólo a `last_synced_at`, escrito con `datetime.utcnow()` **local** en `:212`, `:231` y `:325`.

O sea: **el reloj del servidor de GitLab llega hasta el sync y se descarta, y en su lugar se guarda el reloj de la máquina del operador.** Ese es el gap exacto que este plan cierra.

### 2.3. La tabla no tiene dónde guardarlo

Columnas reales de `tickets` (`PRAGMA table_info` sobre una copia `VACUUM INTO` de la base viva, 2026-08-02):

```
id, ado_id, external_id, project, stacky_project_name, tracker_type, title,
description, ado_state, ado_url, priority, work_item_type, parent_ado_id,
last_synced_at, created_at, stacky_status, assigned_to_ado,
local_work_item_type, local_parent_iid
```

**No existe ninguna columna con el `updated_at` del tracker.** `last_synced_at` (`models.py:63`) es el reloj de Stacky, no el de GitLab.

### 2.4. El costo real, medido

Copia read-only de la base viva (`backend/data/stacky_agents.db`, **194.109.440 bytes**) obtenida con `VACUUM INTO` al scratchpad — **la base del operador no se tocó**:

| Métrica | Valor medido |
|---|---|
| Filas en `tickets` | **232** |
| `tracker_type='gitlab'` (todas de `stacky_project_name='RIPLEY'`) | **63** — abiertas: **63**, cerradas: **0** |
| Tipos en RIPLEY | `Issue` 53, `Task` 8, `Epic` 2 |
| Filas GitLab con `parent_ado_id` no nulo | 8, apuntando a **2** padres distintos |
| Padres referenciados **ausentes** de la tabla (los GET uno a uno de `_TOPE_PADRES`) | **0** |

⇒ **El costo real de un sync de RIPLEY hoy es 1 request de listado y 0 requests de padres.** El "≈90 requests" es el **techo del diseño** (`_DEFAULT_PAGE_CAP = 40` en `services/gitlab_client.py:32`, usado como default de `_request_paginated` en `:355`, más `_TOPE_PADRES = 50` en `services/gitlab_sync.py:47`), y se alcanza recién a partir de ~3.901 issues abiertos. Este plan **no** promete bajar un número que hoy ya es 1.

> **NO VERIFICABLE DESDE EL REPO:** el enunciado menciona "1009 issues totales en RIPLEY". La base local sólo tiene los abiertos que el sync trajo (63); el total del servidor sólo se sabría preguntándole a GitLab, y este plan tiene prohibido hacerlo. No se usa como criterio.

### 2.5. Los disparadores del sync — el censo completo, corregido

`sync_gitlab_tickets` tiene exactamente **tres** llamadores de producción:

| Disparador | Anclaje **real** | Naturaleza |
|---|---|---|
| Arranque del proceso | `app.py:183` (import) → `app.py:186` (`_r = sync_gitlab_tickets(active, provider=_prov)`), dentro de `_startup_sync` (def en `app.py:99`) | una vez por arranque |
| Endpoints HTTP | `api/tickets.py:1209` (import) → `:1210` (`return sync_gitlab_tickets(project_name, provider=provider)`), dentro de `_sync_via_provider_or_ado` (def en `api/tickets.py:1144`) | por request |
| Post-completación de una ejecución | `services/completion_sync.py:134` (import) → `:136` (`result = sync_gitlab_tickets(project) or {}`), dentro de `_do_project_sync` (def en `:99`) | reactivo |

**Corrección importante al enunciado de trabajo.** Es cierto que **ninguno de los daemons de `app.py` sincroniza tickets** (los ocho son: `plan199-harvest` `:309`, `stacky-maintenance` `:671`, `stacky-digest-daemon` `:708`, `stacky-memory-review-daemon` `:728`, `stacky-local-insights-daemon` `:758`, `stacky-egress-sentinel-daemon` `:787`, `stacky-ado-edit-daemon` `:820`, `stacky-dbcompare-watch-daemon` `:848`). **Pero no es cierto que no haya disparador periódico.** Lo hay, y vive en el navegador:

```
frontend/src/hooks/useTicketSync.ts:252-277   // polling con backoff exponencial
frontend/src/hooks/useTicketSync.ts:269           requestSync("auto_poll", false);
frontend/src/hooks/useTicketSync.ts:40        export const DEFAULT_INTERVAL_MS = 45_000;
```

Ese poll pega contra `POST /api/tickets/sync-v2` (`useTicketSync.ts:146`), que rate-limitea a un mínimo de **15 s** (`api/tickets.py:6601`, `_SYNC_MIN_INTERVAL_SEC = 15`) — es decir, **el poll de 45 s pasa siempre**. Salta la corrida si la pestaña está oculta (`useTicketSync.ts:265`).

**Consecuencia directa sobre el alcance:** el disparador periódico **ya existe**, así que agregar un daemon de backend no cierra ningún hueco de frescura mientras el operador trabaja; sólo agrega polling **en reposo**, que es la excepción (A). Por eso el daemon **queda fuera de scope** (§6.1) y todo el plan se concentra en hacer barato el poll que ya está corriendo.

### 2.6. El riesgo central, escrito por el propio código

`services/gitlab_sync.py:310-326` cierra por **ausencia**:

```
310    # Lo que dejó de venir en el listado de ABIERTOS se marca cerrado. NO se
311    # borra: el operador conserva su historial y el grafo sigue mostrando el ítem.
312    if vistos_external:
313        pendientes = (
314            session.query(Ticket)
315            .filter(
316                Ticket.stacky_project_name == stacky_name,
317                Ticket.tracker_type == _TRACKER,
318                Ticket.ado_state != "closed",
319                ~Ticket.external_id.in_(vistos_external),
320            )
321            .all()
322        )
323        for fila in pendientes:
324            fila.ado_state = "closed"
325            fila.last_synced_at = datetime.utcnow()
326            cerrados += 1
```

Con `updated_after`, la respuesta ya **no contiene todo lo abierto**. Si esa lógica quedara viva, el primer sync incremental marcaría `closed` **todo el backlog que no cambió**. Es una corrupción masiva y silenciosa del tablero del operador.

> ⚠️ **Corrección de la v1: el daño NO es "61 de 63", y decirlo así fue lo que rompió el gate.** El número real depende del tamaño del delta y **no se puede medir desde el repo**. Lo que sí se midió, ejecutando (§0):
>
> | Delta que devuelve GitLab | Filas mal cerradas (de 63) | Por qué |
> |---|---|---|
> | **vacío** (nada cambió) | **0** | `if vistos_external:` (`gitlab_sync.py:312`) ya corta: el conjunto queda vacío y el bloque **no entra** |
> | 1 ítem ya conocido | **62** | entra al bloque y las otras 62 quedan fuera del `IN` |
> | k ítems ya conocidos | **63 − k** | idem |
> | sólo ítems **nuevos** (ninguno conocido) | **63** — el peor caso | ningún `external_id` de las filas viejas está en `vistos_external` |
>
> O sea: la v1 **sobreestimó el caso benigno y subestimó el peor caso**. Y el error de encuadre tuvo una consecuencia directa: al tomar el delta vacío como escenario representativo, su caso de prueba central quedó cubierto por un `if` preexistente y **dejó de poder fallar**. El caso de §F5 usa ahora un delta **parcial no vacío** (§0-B), que es donde el daño existe.

El módulo lo anticipó por escrito, tres años de código antes que este plan, en su propio docstring:

```
services/gitlab_sync.py:21-25
LA QUERY ES DE ABIERTOS Y ESO NO ES UN DETALLE. Se pide
`TrackerQuery(state="open")` explícito, y la semántica de `removed` de arriba
—"lo que no vino en el listado pasa a closed"— SOLO es correcta con esa query. Si
alguna vez alguien la cambia a `state="all"`, la regla de `removed` deja de tener
sentido y hay que revisarla: van juntas, y por eso están documentadas juntas acá.
```

**Este plan es exactamente ese "alguna vez".** La revisión que el docstring pide es §3.1 **y §3.1-bis**: son **dos** consecuencias, no una, y la v1 sólo vio la primera.

### 2.7. La segunda consecuencia de `state="all"`: no sólo lee distinto, ESCRIBE filas nuevas

`_upsert_ticket_gitlab` inserta **sin mirar el estado** (`services/gitlab_sync.py`, rama `if fila is None:`):

```
    if fila is None:
        session.add(
            Ticket(
                ...
                ado_state=estado,      # <-- "closed" entra igual que "opened"
                ...
            )
        )
        return "created"
```

Hoy eso es inofensivo porque la query es de **abiertos**: un issue cerrado nunca llega. Con `state="all"&updated_after=W`, **sí llega** — GitLab devuelve todo lo modificado después de `W`, y un issue cerrado hace meses al que alguien le puso un comentario o una etiqueta **entra en el delta**. Medido ejecutando (§0-C): `created=1`, fila `(77, 'closed')` **creada de la nada**.

Por qué importa, con los números de la base real:

| Hecho | Medido |
|---|---|
| Filas GitLab hoy | **63**, todas `RIPLEY`, **todas `opened`, 0 cerradas** |
| Qué las saca | **nada**: el modo COMPLETO marca `closed` por ausencia, **nunca borra** (riel del producto, `gitlab_sync.py:17-19`) |
| Quién las muestra | `GET /api/tickets` → `list_tickets` (`api/tickets.py:1104`), que **no filtra por `ado_state`** … |
| … y con qué orden y tope | `.order_by(Ticket.last_synced_at.desc()...).limit(500)` (`api/tickets.py:1126`) |

⇒ Cada cerrado que entra por el delta es una fila **permanente**, aparece **arriba de todo** en el tablero (su `last_synced_at` es el más fresco) y consume una de las **500** posiciones de la lista. Con el tiempo, los abiertos reales quedan fuera de la ventana.

**La v1 declaraba en su §2.4 el invariante *"la base local sólo tiene los abiertos que el sync trajo (63)"* y lo rompía en su F4 sin decirlo.** La barrera de §3.1-bis lo restituye.

---

## 3. Principios y guardarraíles

### 3.1. La regla de correctitud — dos modos, nunca mezclados

El sync pasa a tener **dos modos**, y el que decide es una función pura y testeable:

| Modo | Query emitida | Regla de ausencia (`removed`) | Cuándo |
|---|---|---|---|
| **COMPLETO** | `TrackerQuery(state="open")` — **byte-idéntico a hoy** | **ACTIVA**, sin un cambio | Según §3.2 |
| **INCREMENTAL** | `TrackerQuery(state="all", updated_after=W)` | **APAGADA POR COMPLETO** | Sólo si ninguna condición de §3.2 se cumple |

**Por qué `state="all"` y no `state="open"` en el incremental.** Con `state="open"&updated_after=W`, un issue que se **cerró** después de `W` **no viene en la respuesta** (GitLab lo filtra por estado), así que el incremental sería incapaz de enterarse de un cierre — ni por presencia ni por ausencia. Con `state="all"`, el issue cerrado **sí viene**, con `"state": "closed"`, y `_upsert_ticket_gitlab` lo refleja solo, porque ya escribe `fila.ado_state = estado` (`gitlab_sync.py:227`) a partir de `estado = item.get("state") or "opened"` (`:148`). **El cierre del delta se captura por el estado propio del issue, no por su ausencia.** Por eso, y sólo por eso, la regla de ausencia puede apagarse sin perder la detección de cierres recientes.

Dos verificaciones que sostienen esto y que se hicieron abriendo el código:

1. `_query_to_gitlab_params` (`gitlab_provider.py:122-136`) mapea `"open"→"opened"` y `"closed"→"closed"`, y **para cualquier otro valor no emite el parámetro `state`**. GitLab sin `state` devuelve todos. ⇒ `state="all"` funciona **sin tocar esa función**.
2. `TrackerQuery(state="all")` **ya se usa en producción hoy**: `backend/tools/migrar_mantis_gitlab/destination_writer.py:574`. No es una invención de este plan.

**Lo único que el incremental NO puede detectar** es un issue **borrado** de GitLab (delete real) o movido de proyecto: no viene en el delta ni deja rastro. Eso lo cubre el modo COMPLETO periódico. Está declarado en §5, riesgo R2.

### 3.1-bis. La SEGUNDA regla de correctitud — la barrera de admisión del delta

Apagar la regla de ausencia arregla el lado de la **lectura**. Falta el de la **escritura**, que la v1 no vio (§2.7). Regla:

> **En modo INCREMENTAL, un ítem del delta puede ACTUALIZAR una fila existente, pero sólo puede CREAR una fila si viene `opened`.**

| Situación en el delta parcial | Fila local | Qué hace | Por qué |
|---|---|---|---|
| ítem `opened` | existe | **actualiza** | es el caso normal |
| ítem `opened` | **no existe** | **crea** | es un issue nuevo del proyecto: tiene que entrar |
| ítem `closed` | existe | **actualiza** ⇒ la fila pasa a `closed` | es la detección de cierre de §3.1, y **no se toca** |
| ítem `closed` | **no existe** | **se SALTEA** (cuenta en `omitidos_cerrados_desconocidos`) | hoy esa fila no existe; crearla es inventar historial que el operador nunca tuvo |

En modo **COMPLETO** la barrera **no se aplica**: ahí la query es de abiertos y ningún `closed` llega, así que el camino es byte-idéntico al de hoy. La barrera vive **sólo** en la rama parcial, igual que el apagado de la regla de ausencia — **las dos van juntas con `state="all"`, exactamente como el docstring de `:21-25` avisa que van juntas la query y la regla de `removed`.**

**No se cuela por el traído de padres.** Ese bloque (`gitlab_sync.py:343-389`) pide por `get_item` los padres **referenciados y ausentes**, y un padre cerrado **sí debe entrar** (es la deuda que el Plan 277 F6 vino a saldar: una épica cerrada cuyos hijos quedarían huérfanos). La barrera se aplica **sólo al bucle del listado**, nunca al de padres. Está probado por separado en §F5 caso 7.

### 3.1-ter. Por qué la barrera es una función pura y no un `if` suelto

Se implementa como `admitir_del_delta(item, fila_existe, modo) -> bool` en `services/gitlab_sync_watermark.py`, no como una condición inline, por tres razones:

1. **Se puede probar sin base de datos ni proveedor** — es el gate más barato de todo el plan.
2. **Es el punto de extensión del próximo tracker.** Cuando Jira o Mantis quieran su incremental (§6.2), la barrera ya existe y la regla es la misma; lo que cambia es el nombre del estado, que entra por parámetro.
3. **Deja el `if` de producción con un solo símbolo grepeable**, que es lo que el gate estático de §F6 puede vigilar sin depender de la forma del `if`.

### 3.2. La regla exacta de cuándo se hace COMPLETO

Función pura `decidir_modo_de_sync(...)` en `services/gitlab_sync_watermark.py`. Devuelve `("completo", motivo)` si **cualquiera** de estas es cierta, y `("incremental", "")` si ninguna lo es:

| # | Condición | Motivo devuelto |
|---|---|---|
| 1 | `forzar_full=True` lo pidió el llamador | `"pedido_explicito"` |
| 2 | La opción de sincronización parcial está apagada | `"opcion_apagada"` |
| 3 | No hay entrada de marca para este proyecto (primera corrida de siempre) | `"sin_marca"` |
| 4 | La entrada existe pero es ilegible: el archivo no es JSON válido, no es un objeto, falta la clave `marca`, la marca no parsea como fecha ISO-8601, o el contador no es un entero ≥ 0 | `"marca_ilegible"` |
| 5 | La marca es más vieja que `_EDAD_MAX_MARCA_H` (24 h) respecto de `datetime.utcnow()` | `"marca_vencida"` |
| 6 | El contador de corridas parciales consecutivas alcanzó `STACKY_GITLAB_SYNC_FULL_CADA_N` (default **10**) | `"cuota_cumplida"` |

**El orden es de evaluación, no de prioridad**: se devuelve el primer motivo que aplica. Los seis se prueban uno por uno en §F5.

**Consecuencia de diseño, deliberada:** el modo COMPLETO es el **default de todos los caminos de error**. Perder el archivo, corromperlo, borrarlo a mano, un disco lleno, una excepción al leerlo — todo termina en COMPLETO, que es el comportamiento de hoy. **Nunca en "no sincronizar".** Ninguna condición puede llevar a un estado donde el sync haga menos de lo que hace hoy sin haber hecho antes un COMPLETO.

### 3.3. El reloj: se usa la hora de GitLab, nunca la de Stacky

La marca de agua es el **máximo `updated_at` de los ítems que GitLab devolvió**, no `datetime.utcnow()`. Motivo: si el reloj de la máquina del operador adelanta respecto del servidor de GitLab, una marca local dejaría fuera del siguiente delta todo lo modificado en la ventana de desfase, **en silencio y para siempre**. Usando la hora que el propio servidor puso en el issue, el desfase de relojes **no puede producir un hueco**.

Dos refuerzos, los dos obligatorios:

- **Solapamiento.** Se guarda `max(updated_at) - _SOLAPAMIENTO_SEG`, con `_SOLAPAMIENTO_SEG = 120`. Cubre (a) la ventana de carrera —un issue modificado *durante* el sync, entre la página 1 y la página N—, y (b) la duda sobre si `updated_after` de GitLab es inclusivo o exclusivo, que **no se puede resolver sin consultar la API del operador**: con 120 s de solapamiento el diseño es correcto en los dos casos. El precio es traer de nuevo los issues tocados en los últimos 2 minutos, que es exactamente lo que se quiere.
- **Si la respuesta viene vacía, la marca NO se toca.** Un delta vacío significa "no cambió nada", no "avanzá el reloj". Avanzarla con un `utcnow()` local reintroduciría el problema de relojes por la puerta de atrás.
- **La marca es MONÓTONA: nunca retrocede.** `escribir_marca` guarda `max(marca_anterior, nueva)`, nunca `nueva` a secas.

> ⚠️ **Corrección de la v1 — la marca podía retroceder y nadie lo notaba.** En modo **COMPLETO** la query es de **abiertos**, así que `items` NO incluye los cerrados. Si el cambio más reciente del proyecto fue sobre un issue **cerrado**, el `max(updated_at)` de esa tanda es **más viejo** que la marca que dejó el último incremental, y la v1 lo escribía igual (su guard con `None` sólo cubría la tanda vacía, no la tanda "vieja").
>
> El efecto es doble y silencioso: **(a)** el incremental siguiente pide una ventana enorme y el ahorro de K1 desaparece justo después de cada corrida de cuota; **(b)** combinado con §2.7, esa ventana enorme arrastra una tanda grande de **cerrados** y dispara la inserción masiva de filas.
>
> Con `max(marca_anterior, nueva)` el problema desaparece y **no se pierde nada**: la marca sólo puede quedar más atrás de lo real, nunca más adelante, y quedarse atrás sólo cuesta traer de más — que es el lado seguro. Es la misma asimetría que gobierna todo el módulo.

Formato en disco: el string ISO-8601 **crudo, tal como lo emitió GitLab** (`"2026-08-02T14:33:21.000Z"`), después de restar el solapamiento y re-serializar. El parseo usa la receta que ya está en el repo para el equivalente de Azure DevOps, `services/ado_sync.py:57`:

```python
datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
```

⚠️ **NO copiar** `datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")` (el patrón de `services/dbcompare_watch.py:340`): **revienta con los milisegundos** que manda GitLab (`.000Z`). Tampoco `.rstrip("Z")` (`heartbeat_monitor.py:133`), que descarta la zona en vez de convertirla.

### 3.4. Dónde vive la marca: JSON en `data_dir()`, no la base

Se descartan las dos alternativas, con motivo:

- **Columna nueva en `tickets`: DESCARTADA, y es la decisión más importante de este plan.** `db.py:270-325` hace migraciones a mano con `ALTER TABLE`, pero `_rebuild_tickets_table_if_needed` (llamada en `db.py:323`) tiene **la lista de columnas hardcodeada**, y el propio código avisa en `db.py:283-287` que si se agrega una columna sólo en la lista de migraciones *"el ALTER la crea y el rebuild la borra en silencio junto con el dato del operador"*. Además la granularidad sería equivocada: la marca es **por proyecto**, no por ticket.
- **Tabla key-value existente: NO EXISTE.** Los diez modelos de `models.py` son `Ticket`, `User`, `TicketStateHistory`, `PackRun`, `AgentExecution`, `PipelineRun`, `ExecutionLog`, `SystemLog`, `AgentPromptVersion`, `EvalRun`. Ninguno es un store de estado por clave. `SystemLog` es append-only sin unicidad: usarlo obligaría a un `MAX(timestamp) WHERE action=…` por cada sync.

**Se usa el patrón consolidado del repo:** un JSON bajo `runtime_paths.data_dir()` (definida en `runtime_paths.py:48-54`), con el molde exacto de `services/integration_breaker.py` — que además es el precedente semánticamente más cercano, porque también guarda estado de degradación **por integración y por proyecto**:

| Pieza | En `integration_breaker.py` | En el módulo nuevo |
|---|---|---|
| ruta | `:55` `_path()` → `data_dir() / _FILENAME` | igual, `gitlab_sync_watermark.json` |
| lectura tolerante | `:56-61` `_load()` → `{}` si falta o si el JSON está roto | igual — **es la condición 4 de §3.2** |
| escritura best-effort | `:62-67` `_save()` con `mkdir(parents=True, exist_ok=True)` | igual |
| clave compuesta | `:37-38` `integration_key()` → `f"{integration}::{project.upper()}"` | `stacky_project_name` a secas |

⚠️ **`data_dir()` es `backend/data/`, la misma carpeta donde vive la base de 194 MB del operador.** Todo test que ejercite el store **tiene que** monkeypatchear la ruta a `tmp_path`, o contamina la instalación real. Es un requisito explícito de §F2.3 y §F5.

### 3.5. Flags: una ON, una numérica, y por qué no hay más

| Key | Tipo | Default | Categoría | Excepción |
|---|---|---|---|---|
| `STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED` | `bool` | **`true` (ON)** | `paridad_proveedores` | **Ninguna.** Ver abajo |
| `STACKY_GITLAB_SYNC_FULL_CADA_N` | `int` | `10` (min 1, max 1000) | `paridad_proveedores` | n/a (numérica) |

**Por qué la booleana nace ON.** No cae en (A): **no enciende ningún loop, daemon, barrido ni llamada a modelo — no gasta absolutamente nada en reposo.** Al contrario: reduce el gasto de un poll que ya está corriendo cada 45 s desde antes de este plan. No cae en (B): es camino de **lectura**, no publica, no commitea, no escribe en el tracker del operador, no le saca ninguna decisión, y **no borra ni cierra nada** — de hecho apaga la única regla del sync que marca filas como cerradas. Con la flag OFF el sync vuelve **byte-idéntico al de hoy**: es la palanca de rollback documentada.

**Por qué la flag ON es una sola y qué NO es flag:**

- `_SOLAPAMIENTO_SEG = 120` y `_EDAD_MAX_MARCA_H = 24` son **constantes de módulo, no flags**. Precedente exacto, en el mismo archivo que este plan modifica: `_TOPE_PADRES = 50` (`services/gitlab_sync.py:47`), una cota de costo contra el sistema del operador que el Plan 277 dejó como constante y nadie pidió por interfaz. Son parámetros de correctitud interna, no decisiones de operación. Exponerlos sumaría dos flags con sus ocho guardianes cada una a cambio de nada.
- **No se declara `requires=` en ninguna de las dos.** Motivo doble: (1) `STACKY_GITLAB_ENABLED` **no está en `FLAG_REGISTRY`** y usarlo como madre rompería la regla R1 de `validate_requires_graph` (`harness_flags.py:7425`); (2) `STACKY_GITLAB_SYNC_ENABLED` sí está, pero la dependencia ya está resuelta **en código** —si el sync entero está apagado, el modo parcial es inalcanzable por construcción—. Precedente escrito y aceptado: `tests/test_harness_flags_requires.py:351-352` dice que el Plan 269 *"no declara ninguna (…) de forma deliberada: resuelve la dependencia EN CODIGO, no en el registro"*.
  **Consecuencia medida:** `test_requires_map_is_frozen` (`tests/test_harness_flags_requires.py:397`) construye `actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}` — el `if s.requires` **filtra**. Sin `requires=`, las flags de este plan **no entran al mapa y el archivo `_REQUIRES_MAP_FROZEN` no se toca**. Un guardián menos, sin trampa.

**Mecánica exacta (regla dura, verificada en `harness_flags.py:7383-7385`: `default_is_known(spec)` es literalmente `return spec.default is not None`):**

- **ON** ⇒ en `config.py` el `os.getenv(..., "true")`, en el `FlagSpec` **`default=True`**, y la key **agregada a `_CURATED_DEFAULTS_ON`** (`tests/test_harness_flags.py:467-1121`).
- **numérica (`int`)** ⇒ en `config.py` el `os.getenv(..., "10")` convertido a int, y en el `FlagSpec` **NO se declara `default=`** — declararlo la metería en el conjunto que `test_default_known_only_for_curated` (`:1196`) exige que sea **exactamente** `_CURATED_DEFAULTS_ON`. Sí lleva `min_value=1, max_value=1000`, que la mete en `_FROZEN_BOUNDS` (`tests/test_harness_flags_bounds.py`, cierra en `:227`, congelado por `test_bounds_map_is_frozen` en `:230`).

### 3.6. Los tres runtimes: la paridad sale gratis, y está verificada

Los tres son `services/codex_cli_runner.py`, `services/claude_code_cli_runner.py`, y GitHub Copilot, que **no tiene runner propio**: corre en el runner estándar de `agent_runner.py` apoyado en `copilot_bridge.py` (despacho en `agent_runner.py:228`, `:311-313`, `:319`, `:398`, `:507-569`).

**Se abrieron los tres y se grepearon.** Resultado: `gitlab` = **0 hits** en `codex_cli_runner.py`, **0** en `claude_code_cli_runner.py`, **0** en `copilot_bridge.py`; `sync_` y `completion_dispatcher` = **0 hits** en los tres.

⇒ **El sync es transversal y vive fuera de los runtimes.** Sus tres disparadores (§2.5) son agnósticos al runner: el arranque del proceso, el endpoint HTTP y el daemon de completación. **Poner el cambio en `services/gitlab_sync.py` da paridad de los tres runtimes sin tocar ni un runner.** No hace falta fallback, porque no hay ninguna asimetría que cubrir. Esto **no se afirma: se prueba**, con un test que ejecuta los tres caminos (§F6.2).

### 3.7. Guardarraíles innegociables

1. **Human-in-the-loop.** El plan no agrega ninguna decisión automática nueva. El único comportamiento nuevo es *pedir menos datos*.
2. **Cero trabajo extra al operador.** No hay que encender nada, configurar nada ni migrar nada.
3. **No se escribe en la base del operador.** Cero `DELETE`, cero `UPDATE` de saneado, cero `ALTER TABLE`. La única escritura nueva es un JSON de ~200 bytes en `data_dir()`.
4. **Backward-compatible.** El campo nuevo de `TrackerQuery` es el **último** y tiene default `None`, así que ningún llamador de hoy cambia. Censo medido: **6** llamadas de producción le pasan un `TrackerQuery` — `services/gitlab_sync.py:257`, `services/incident_context.py:230`, `services/migrator_core.py:151`, `services/migrator_executor.py:172`, `services/migrator_verify.py:37` y `backend/tools/migrar_mantis_gitlab/destination_writer.py:574` (esta última **ya con `state="all"`**). Las de `migrar_mantis_gitlab/migrator_mg_*.py` llaman al **wrapper** `writer.fetch_open_items()`, cuya firma es `(self)` sin argumentos (`destination_writer.py:173` y `:563`): no lo tocan ni se ven afectadas. `sync_gitlab_tickets` y `_sync_via_provider_or_ado` reciben un kwarg **keyword-only con default seguro**.
5. **No degradar.** Con la flag OFF, o con cualquier fallo del store, el comportamiento es el de hoy, byte a byte.
6. **Sesión paralela viva.** Cada fase commitea con `git commit -F <archivo> -- <rutas exactas>`, y **el `-F` va antes del `--`**. Cero `add -A`, cero `amend`/`reset`/`rebase`/`stash`/`checkout`, cero push. Se corre `git status --short` **antes de cada commit**. Ninguno de los archivos de este plan aparece en la lista de 34 sucios medida el 2026-08-02.

---

## 4. Baselines — medidos, no copiados

Medidos el **2026-08-02** sobre `docs/plan-279`, con `"Stacky Agents/backend/.venv/Scripts/python.exe"` (Python **3.13.5**), `STACKY_TEST_MODE=1`, `LLM_BACKEND=mock`, `DATABASE_URL` al scratchpad y **una base SQLite fresca por archivo** (reusar una sola base entre archivos hace que la migración de arranque choque contra el índice único de `tickets` y devuelva `errors` en vez de `passed` — regla descubierta al implementar el Plan 290).

Comando exacto, por archivo:

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
rm -f "$SCRATCH/bl.db" "$SCRATCH/bl.db-wal" "$SCRATCH/bl.db-shm"
STACKY_TEST_MODE=1 LLM_BACKEND=mock DATABASE_URL="sqlite:///$SCRATCH/bl.db" \
  ./.venv/Scripts/python.exe -m pytest "tests/<ARCHIVO>" -q
```

| Archivo | Baseline **medido** | Nota |
|---|---|---|
| `tests/test_plan276_gitlab_sync.py` | **21 passed** | el archivo que este plan más mueve |
| `tests/test_gitlab_provider.py` | **26 passed** | `_query_to_gitlab_params` |
| `tests/test_gitlab_client.py` | **6 passed** | paginación |
| `tests/test_tracker_provider_conformance.py` | **13 passed** | `TrackerQuery` |
| `tests/test_plan277_read_path.py` | **15 passed** | camino de lectura |
| `tests/test_plan277_un_solo_motor.py` | **4 passed** | gate del motor único |
| `tests/test_plan208_auto_sync.py` | **10 passed** | `completion_sync` |
| `tests/test_harness_flags.py` | **59 passed** | 6 de los 8 guardianes viven acá |
| `tests/test_harness_flags_bounds.py` | 🔴 **1 failed, 17 passed** | **ROJO DE FÁBRICA — la v1 lo daba por verde.** Ver §4.1 y §4.1-bis |
| `tests/test_flag_wiring.py` | **5 passed** | `test_every_non_reserved_flag_is_wired` |
| `tests/test_harness_flags_requires.py` | **9 passed** | debe quedar **intacto**: no se declara `requires=` |
| `tests/test_harness_ratchet_meta.py` | **4 passed** | clasificación de los tests nuevos |
| `tests/test_plan259_ratchet_script_parity.py` | **12 passed** | **la brecha está en el límite, ver §4.2** |
| `tests/test_plan276_capability_envelope.py` | **6 passed** | parchea `_sync_via_provider_or_ado` |
| `tests/test_plan148_ado_sync_breaker.py` | **6 passed** | idem |

> **Los cinco baselines que la v1 dejaba *(medir en F0)* ya están medidos, arriba.** F0 deja de ser una fase de medición y pasa a ser una fase de **verificación**: se re-corren y se confirma que dan el mismo número. Si alguno difiere, manda la medición del día y se anota — pero el plan ya no arranca con huecos.

### 4.1. Rojos de fábrica — **OCHO**, medidos uno por uno

**Criterio para todos ellos: delta cero, NO verde.** Un conteo sobre un archivo ya rojo **no discrimina**: si la fase rompiera algo ahí, el total no se movería. Por eso, donde el plan agrega contenido vigilado por uno de estos archivos, la validación real se hace **importando la regla desde el archivo rojo hacia el test propio del plan** (patrón ya usado en `tests/test_plan257_flags.py:99-110`).

| Archivo | Baseline medido 2026-08-02 |
|---|---|
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** |
| `tests/test_flags_env_read_meta.py` | **1 failed, 1 passed** |
| `tests/test_plan218_coupling_ratchet.py` | **3 failed, 7 passed** |
| `tests/test_plan218_capability_matrix.py` | **2 failed, 8 passed** |
| `tests/test_plan76_codebase_memory_mcp.py` | **1 failed, 9 passed** |
| `tests/test_plan74_migrator_wiring.py` | **1 failed, 3 passed** |
| `tests/test_plan218_tracker_contract.py` | **1 failed, 9 passed — NO MEDIDO ACÁ: SALE A LA RED.** No correr sin aislar. Valor tomado de la corrida anterior de la serie |
| 🔴 **`tests/test_harness_flags_bounds.py`** | **1 failed, 17 passed** — **el que la v1 no vio, y es el que más importa acá** |

#### 4.1-bis. El octavo rojo es el ÚNICO guardián de la flag numérica

`test_bounds_map_is_frozen` (`tests/test_harness_flags_bounds.py:230`) **ya falla hoy**, y la salida dice exactamente por qué:

```
    actual = {s.key: (s.min_value, s.max_value)
              for s in FLAG_REGISTRY
              if s.min_value is not None or s.max_value is not None}
>   assert actual == _FROZEN_BOUNDS
E   Left contains 6 more items:
E   {'STACKY_DOCS_CITATION_GATE_MIN_RATIO': (0.0, 1.0),
E    'STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS': (0, 100000),
E    'STACKY_DOCS_PIPELINE_MAX_LLM_CALLS': (1, 200),
E    'STACKY_DOCS_RIGOR_MIN_CITATIONS': (0, 50), ...}
```

El mapa congelado le debe **seis entradas** a un plan anterior. Consecuencia para éste, que es un **gate que no puede fallar** de manual:

| Qué hace el implementador con el paso 6 de §4.3 (`_FROZEN_BOUNDS`) | Resultado del archivo |
|---|---|
| lo hace bien (entrada en `_FROZEN_BOUNDS` **y** en el `FlagSpec`) | 1 failed, 17 passed |
| **se lo olvida** (bounds sólo en el `FlagSpec`) | 1 failed, 17 passed |
| lo hace al revés (sólo en `_FROZEN_BOUNDS`) | 1 failed, 17 passed |

**Los tres casos dan el mismo número.** ⇒ el criterio de la v1 (*"`test_harness_flags_bounds.py` — el baseline de F0, delta cero"*) **no discrimina**, y §F3 caso 4 sólo miraba `spec.min_value`/`spec.max_value`, nunca la pertenencia al mapa. La v1 aplicó su propia regla de §4.1 —*"importar la regla desde el archivo rojo hacia el test propio"*— al archivo de ayuda llana y **se olvidó de aplicarla acá**, que es donde hacía falta.

⇒ **§F3 gana el caso 11**, que importa `_FROZEN_BOUNDS` desde el archivo rojo y asserta la pertenencia de la key en el archivo verde de este plan. Ver §F3.

### 4.2. Ratchets — el colchón está en CERO

Medido el 2026-08-02:

| Script | Array | Entradas |
|---|---|---|
| `backend/scripts/run_harness_tests.sh` | `HARNESS_TEST_FILES=(` **línea 20**, cierra `)` en **:1086** | **831** |
| `backend/scripts/run_harness_tests.ps1` | `$HarnessTestFiles = @(` **línea 13**, cierra `)` en **:1002** | **767** |

🔴 **`_PS1_LAG_MAX = 64` (`tests/test_plan259_ratchet_script_parity.py:46`) y la brecha de hoy es exactamente 831 − 767 = 64.** El margen es **cero**. ⇒ **Todo archivo de test nuevo va en LOS DOS scripts, en el mismo commit, sin excepción.** Agregarlo sólo al `.sh` pone `test_el_ps1_no_pierde_terreno` (`:85`) en rojo de inmediato.

**Anclajes de inserción, por SÍMBOLO (no por línea — las líneas se mueven entre fases):** insertar inmediatamente **después** de la entrada `tests/test_plan291_guardia_repo.py`, que en ambos archivos cierra el bloque comentado del Plan 291. Contexto literal verificado:

`run_harness_tests.sh` — **rutas peladas, sin comillas, sin comas**:
```
  # — Plan 177 — Auto-PR del Dev Resolutor de incidencias —
  tests/test_plan177_ado_commit_web_url.py
  tests/test_incident_dev_diff.py
  tests/test_incident_dev_autocommit.py
  # — Plan 291 — el auto-PR avisa si el arreglo trae un secreto —
  tests/test_plan291_autocommit_redaccion.py
  tests/test_plan291_guardia_repo.py
```

`run_harness_tests.ps1` — **rutas ENTRE COMILLAS DOBLES; en esta región NO se usan comas**:
```
  # Plan 177 - Auto-PR del Dev Resolutor de incidencias
  "tests/test_plan177_ado_commit_web_url.py"
  "tests/test_incident_dev_diff.py"
  "tests/test_incident_dev_autocommit.py"
  # Plan 291 - el auto-PR avisa si el arreglo trae un secreto
  "tests/test_plan291_autocommit_redaccion.py"
  "tests/test_plan291_guardia_repo.py"
```

Lo **innegociable** en el `.ps1` es la **comilla**, no la coma: `test_el_ps1_no_tiene_rutas_sin_comillas` (`test_plan259_ratchet_script_parity.py:76`) falla si se pega la ruta pelada, porque PowerShell la leería como un comando y el array la perdería **muda**. Sin rutas con espacios.

⚠️ **Tres precisiones medidas que la v1 no daba, y que juntas son una trampa:**

1. **El anclaje NO está al final del array.** `tests/test_plan291_guardia_repo.py` vive en **`.sh:519`** y **`.ps1:466`**, dentro del bloque temático *"Plan 177 — Auto-PR del Dev Resolutor de incidencias"*, a ~570 líneas del cierre (`.sh:1086`, `.ps1:1002`). El Plan 291 lo puso ahí porque **su tema era ese**. El tema de este plan no lo es.
2. **La convención de los cuatro planes anteriores es APPEND AL FINAL.** Los planes 287, 288, 289 y 290 agregaron sus entradas en la **cola** (`.sh:1071-1085`, `.ps1:995-1001`). Este plan **hace lo mismo**: se inserta **antes del `)` de cierre**, no en el bloque del 291.
3. 🔴 **Y por eso la coma cambia.** Las dos regiones NO usan la misma forma. Medido sobre `run_harness_tests.ps1`: **557** entradas **con** coma y **210** **sin** coma — conviven. La región del 291 (`.ps1:464-466`) no lleva coma; **la cola sí** (`.ps1:998-1000` llevan coma y sólo la última, `:1001`, no). ⇒ al insertar en la cola hay que **poner coma en todas las entradas nuevas menos la última del array**, y **agregarle coma a la que hoy es última** (`"tests/test_plan290_defaults_no_mienten.py"` en `.ps1:1001`).

**Anclaje corregido, por SÍMBOLO:** insertar **inmediatamente antes del `)` de cierre** del array, es decir después de `tests/test_plan290_defaults_no_mienten.py` en ambos scripts. Contexto literal verificado hoy:

`run_harness_tests.sh` (`:1077-1086`) — **rutas peladas, sin comillas, sin comas**:
```
  # Plan 290 - La degradacion deja de ser muda
  tests/test_plan290_degradacion_declarada.py
  ...
  tests/test_plan290_defaults_no_mienten.py
)
```

`run_harness_tests.ps1` (`:995-1002`) — **entre comillas dobles y CON COMA salvo el último elemento**:
```
  "tests/test_plan290_sitios_clasificados.py",
  "tests/test_plan290_gitlab_switch_ui.py",
  "tests/test_plan290_base_url_normalizada.py",
  "tests/test_plan290_defaults_no_mienten.py"
)
```

⚠️ **Una entrada `.ps1` sin la coma que su región exige NO rompe ningún test del ratchet** (`test_el_ps1_no_tiene_rutas_sin_comillas` sólo mira la comilla): PowerShell simplemente evalúa dos strings seguidos y el array **puede quedar mal armado en silencio**. Por eso la verificación de F0 incluye un `pwsh`/`powershell` que **carga el array y cuenta**, no sólo un grep. Ver §F0.

**Registrar obliga a sacar del allowlist.** `tests/harness_ratchet_allowlist.txt` tiene hoy **207 líneas / 194 entradas**, con tope congelado `_ALLOWLIST_MAX = 197` (`tests/test_harness_ratchet_meta.py:66`) y la regla de que **sólo baja**. Los cuatro archivos nuevos de este plan **no** van al allowlist: van al ratchet.

### 4.3. Los ocho guardianes de una flag nueva — verificados uno por uno

| # | Archivo:línea | Función | Lo toca este plan |
|---|---|---|---|
| 1 | `tests/test_harness_flags.py:1124` | `test_every_registry_flag_is_categorized` | **SÍ** — las 2 keys van a `_CATEGORY_KEYS` |
| 2 | `tests/test_harness_flags.py:30` | `test_registry_all_non_env_only_keys_exist_in_config` | **SÍ** — las 2 van a `config.py` |
| 3 | `tests/test_harness_flags.py:1196` | `test_default_known_only_for_curated` | **SÍ** — sólo la booleana entra a `_CURATED_DEFAULTS_ON` |
| 3b | `tests/test_harness_flags.py:1185` | `test_declared_default_true_set` | **SÍ** — mismo set |
| 4 | `tests/test_harness_flags_requires.py:397` | `test_requires_map_is_frozen` | **NO** — no se declara `requires=` (§3.5) |
| 5 | `tests/test_harness_flags_help.py:32` y `:38` | `test_plain_help_covers_all_registry_keys` / `..._no_orphan_keys` | **SÍ** — las 2 van a `PLAIN_HELP` |
| 6 | `tests/test_flag_wiring.py:57` | `test_every_non_reserved_flag_is_wired` | **SÍ, pero NO prueba lo que la v1 creía.** Ver §4.3-bis |
| 7 | `tests/test_harness_flags.py:42` | `test_registry_no_duplicates` | **SÍ** — trivial |
| 8 | `tests/test_harness_ratchet_meta.py:43` + `test_plan259_ratchet_script_parity.py` | los dos ratchets | **SÍ** — 4 archivos nuevos × 2 scripts |
| **9** | `tests/test_harness_flags_bounds.py:230` | `test_bounds_map_is_frozen` | **SÍ — y está ROJO DE FÁBRICA.** La v1 lo contaba dentro del #3 y lo daba por verde. Ver §4.1-bis |

### 4.3-bis. El guardián 6 no prueba que la flag tenga consumidor — y eso cambia una decisión de alcance

`test_every_non_reserved_flag_is_wired` (`tests/test_flag_wiring.py:57-66`) es, literal:

```python
    dead = [spec.key for spec in FLAG_REGISTRY
            if not spec.reserved and spec.key not in corpus]
```

Una **subcadena** sobre `corpus`. Y `_production_corpus()` (`:29-52`) recorre `BACKEND_ROOT.rglob("*.py")` excluyendo **sólo** `tests/`, `services/harness_flags.py` y `services/harness_flags_help.py`. Su docstring lo dice textual:

```
    NOTA: harness_profiles.py y config.py SÍ cuentan (baseline de la
    auditoría 2026-07-02; endurecerlo es fuera de scope, sección 6).
```

⇒ **`backend/config.py` está DENTRO del corpus.** Apenas F3 escriba las dos keys ahí, `spec.key in corpus` es verdadero y el guardián **pasa con F3 sola**.

> ⚠️ **Corrección de la v1.** Decía: *"En F3 las dos flags todavía no tienen consumidor ⇒ correr `tests/test_flag_wiring.py` al cierre de F3 dará rojo, y eso es esperado"*, y sobre esa frase construía la decisión *(a) F3 y F4 van en el mismo commit*. **La premisa es falsa** (baseline hoy: **5 passed**, y seguirá en 5). Consecuencias:
>
> 1. **No hay estado rojo intermedio que evitar.** La opción **(b)** —`reserved=True` en F3— tampoco hace falta: sería *peor*, porque `test_reserved_flags_are_actually_dead` (`:73`) exige que una key reservada **no** aparezca en el corpus, y la key ya estaría en `config.py`.
> 2. **F3 y F4 siguen yendo en el mismo commit**, pero por el motivo correcto: *una opción sin consumidor es una promesa que el operador ve en la interfaz y que no hace nada*. Es una decisión de producto, no una imposición de un guardián.
> 3. **Lo importante:** este guardián **no puede** verificar que F4 exista. Una key declarada sólo en `config.py`, jamás leída, lo pasa. **La única prueba real de que la flag numérica está cableada es §F5 caso 10**, que la ejercita **ejecutando** con la cuota en 3. Queda dicho acá para que nadie vuelva a confiar en el guardián equivocado.

**Guardián extra que este plan NO dispara:** `test_app_startup_flag_reads_are_all_declared` (`tests/test_harness_flags_restart_required.py:233`) exige que todo token `STACKY_*` que aparezca en `app.py` y sea key del registry esté en `_EXPECTED_RESTART_REQUIRED`. **Este plan no toca `app.py`** (el daemon está fuera de scope, §6.1), así que no aplica. Si una fase futura lo tocara, ese guardián se activa.

**Sitios de declaración, con la línea real de hoy:**

| # | Archivo | Símbolo | Dónde |
|---|---|---|---|
| 1 | `backend/services/harness_flags.py` | `_CATEGORY_KEYS` → categoría `"paridad_proveedores"` (tupla abre en **:587**, cierra `),` en **:615**) | antes del `),` de **:615**, después de `STACKY_TRACKER_CONTEXT_ENABLED` (**:614**, del Plan 289) — el orden de la tupla es **cronológico por plan**, no alfabético. Ojo: `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED` (**:607**) **no** es la última entrada; después vienen las de los planes 281, 287 y 289 |
| 2 | `backend/services/harness_flags.py` | `FLAG_REGISTRY` (abre **:621**) | antes del `)` de cierre, hoy **:7353** (la última `FlagSpec` cierra con `),` en **:7352**) |
| 3 | `backend/config.py` | `class Config:` (abre **:60**) | antes de `config = Config()`, hoy **:2732** |
| 4 | `backend/services/harness_flags_help.py` | `PLAIN_HELP` (abre **:25**, cierra `}` en **:2505**) | antes de **:2505** |
| 5 | `backend/tests/test_harness_flags.py` | `_CURATED_DEFAULTS_ON` (abre **:467**, cierra `}` en **:1121**) | antes de **:1121**, **sólo la booleana** |
| 6 | `backend/tests/test_harness_flags_bounds.py` | `_FROZEN_BOUNDS` (cierra **:227**) | **sólo la numérica** |

**El generador de `harness_defaults.env` NO se toca:** `deployment/export_harness_defaults.py:36` construye `HARNESS_KEYS` desde `FLAG_REGISTRY`, sin lista propia; una flag nueva entra sola. Y no existe ningún test que compare el `.env` versionado contra el registry — es un snapshot **parcial por diseño** (declarado en `tests/test_plan128_plans_board_flag.py:56-57`).

### 4.4. Reglas duras de la ayuda llana (`PLAIN_HELP`)

`tests/test_harness_flags_help.py` está **rojo de fábrica**, así que su conteo no valida nada. La entrada nueva se valida en `test_plan292_flags.py` importando las reglas desde ahí. Las reglas, verificadas:

- Los cuatro campos son obligatorios y no vacíos: `what` (≥10, ≤200), `on_effect` (≤240), `off_effect` (≤240), `example` (≤300) — `test_plain_help_fields_non_empty_and_bounded:44`.
- `on_effect` y `off_effect` **empiezan con `"Si "`, SIN TILDE** — `test_plain_help_on_off_start_with_si:56`.
- **Denylist de jerga** (`:17-20`, por palabra completa, case-insensitive, con plural opcional): `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime`. Además está prohibido cualquier `\b[A-Z]+_[A-Z0-9_]+\b` (nombres de variables en mayúsculas) y cualquier `\bF\d` (referencias a fases).

⇒ **Las descripciones de este plan no pueden decir "endpoint", "backend", "gate", "runtime", ni nombrar `STACKY_...`, ni decir "F4".** El texto exacto propuesto está en §F3.2.

### 4.5. Otras dos trampas medidas

- **`tests/flags_env_read_allowlist.txt` (42 líneas).** `test_flags_env_read_meta.py:52` escanea `backend/api/` y `backend/services/` buscando `os.getenv("STACKY_...", <default>)` y exige que toda flag **registrada** se lea desde `config.config`. ⇒ **En `services/gitlab_sync.py` y en `services/gitlab_sync_watermark.py` las dos flags se leen con `getattr(config.config, "...", <default>)`, nunca con `os.getenv`.** El módulo `gitlab_sync.py` ya usa ese patrón (`:79-81`, `:90`, `:101`) y el docstring de `:75-77` explica por qué: ahí `config` es el **módulo**, y la instancia de flags es `config.config`. **`config.py` no entra en el corpus escaneado**, así que declarar el atributo en `Config` no rompe nada.
- **`_ProviderFalso` de `tests/test_plan276_gitlab_sync.py:105-114` no implementa `get_item`.** Tiene sólo `name`, `__init__`, `fetch_open_items` y la lista `self.queries` (que es justo lo que hace falta para asertar la query emitida). El doble de §F5 **debe** agregar `get_item` si algún caso ejercita el traído de padres, o el sync lo cuenta como `padres_fallidos` por el `except Exception` de `gitlab_sync.py:376`. *(La v1 decía `:105-118`; `:117` ya es `def _issue`.)*
- **`_rebuild_tickets_table_if_needed` está DEFINIDA en `db.py:390`**, no dentro de `db.py:270-325`. Lo que sí está en `:323` es su **llamada**, dentro de `_migrate_add_columns` (def en `:270`), y el aviso sobre la lista hardcodeada está en `:284-287`. La conclusión de §3.4 y §6.2 no cambia; el anclaje sí. *(Corregido de la v1, que citaba `:323` como si fuera la definición.)*

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación | Dónde se prueba |
|---|---|---|---|
| **R1** | El incremental cierra en falso el backlog que no cambió — **hasta 63 de 63 filas** de RIPLEY (§2.6), medido en **2 de 3** en la sonda §0-B | La regla de ausencia se **apaga por completo** en modo incremental, y el modo se decide en una función pura | §F5 **caso 4**, con delta **parcial no vacío** — **el criterio de aceptación central** |
| **R1b** | El incremental **crea** filas cerradas que hoy no existen, se muestran arriba del tablero y comen la ventana de 500 (§2.7). Medido en la sonda §0-C | Barrera de admisión `admitir_del_delta` (§3.1-bis): en modo parcial, un ítem `closed` sin fila local **se saltea** | §F5 **caso 6** — el **segundo** criterio de correctitud |
| **R2** | Un issue **borrado** de GitLab (o movido de proyecto) nunca se detecta: no viene en el delta ni deja rastro | El modo COMPLETO periódico (condiciones 5 y 6 de §3.2) lo captura, a lo sumo 10 corridas o 24 h después | §F5 caso 6 |
| **R3** | Reloj de Stacky desfasado del de GitLab ⇒ hueco silencioso de issues nunca vistos | La marca es la hora **del servidor** (`item["updated_at"]`), nunca `utcnow()`; más 120 s de solapamiento | §F5 caso 7 |
| **R4** | Issue modificado **durante** el sync (entre la página 1 y la N) | Los mismos 120 s de solapamiento: la corrida siguiente lo vuelve a traer | §F5 caso 8 |
| **R5** | `updated_after` de GitLab podría ser exclusivo en vez de inclusivo — **no se puede verificar sin consultar el servidor del operador** | El solapamiento hace el diseño correcto en **ambos** casos. Declarado como supuesto, no como hecho | §F5 caso 8 |
| **R6** | Zona horaria: GitLab manda `...Z`, el repo vive en naive UTC (~402 usos de `utcnow()`) | Receta única y compartida, copiada de `ado_sync.py:57`; comparar aware con naive lanza `TypeError`, así que **todo** se normaliza a naive UTC en el borde del store | §F2.3 caso 4 |
| **R7** | El archivo de marca se corrompe, se borra o no se puede escribir | Toda condición de error degrada a **COMPLETO** (§3.2, condiciones 3 y 4), nunca a "no sincronizar" | §F5 casos 4 y 5 |
| **R8** | Un test escribe en `data_dir()` real y contamina `backend/data/` | La ruta del store se monkeypatchea a `tmp_path` en **todos** los tests que lo tocan | §F2.3, §F5 |
| **R9** | La brecha de los ratchets está en 64/64 y un archivo nuevo la rompe | Los 4 archivos van a **los dos** scripts, en el commit de la fase que los crea | §F0 y cada fase |
| **R10** | La sesión paralela pisa archivos | Ninguno de los 34 sucios coincide. `git status --short` antes de cada commit, y pathspec acotado siempre | §3.7 |
| **R11** | La marca **retrocede** tras una corrida COMPLETA (el `max(updated_at)` de los abiertos puede ser más viejo que la marca previa) ⇒ el incremental siguiente pide una ventana enorme, mata el ahorro y arrastra una tanda grande de cerrados | `escribir_marca` guarda **`max(marca_anterior, nueva)`**: la marca es monótona (§3.3) | §F2.3 caso 12 |
| **R12** | Un gate del plan **no puede fallar** y da falso verde: el archivo que lo vigila ya está rojo, o el escenario elegido está cubierto por un `if` preexistente | Toda afirmación lleva **mitad de contraste ejecutada** (§F5), y donde el vigilante está rojo se **importa la regla** al archivo verde del plan (§4.1-bis, §F3 caso 11) | §F5 y §F3 |

---

## 6. Fuera de scope

### 6.1. El daemon periódico de backend — FUERA, con motivo medido

El enunciado de este plan contemplaba *"un daemon opcional con el patrón de los 8 existentes de `app.py`, que nace OFF"*. **Se descarta, por tres razones, y las tres son medidas:**

1. **El disparador periódico ya existe.** `useTicketSync.ts:252-277` pollea cada **45 s** (`:40`) mientras el tablero está abierto. Un daemon de backend no mejora la frescura durante el trabajo del operador; sólo agrega corridas cuando **nadie está mirando**. Eso es exactamente la excepción (A): polling que gasta en reposo sin que el operador haya pedido nada.
2. **El código prohíbe explícitamente el patrón que el enunciado pedía.** `app.py:635-636` dice, textual: *"Punto de extensión compartido: las tareas se registran con `services.maintenance.register_maintenance_task()`. **NO agregar threads nuevos**."* Un daemon nuevo estilo "los 8 existentes" contradice una instrucción escrita en el propio archivo. La forma correcta —si algún día se hiciera— es registrar un `MaintenanceTask` (`services/maintenance.py:17-22`: `name`, `interval_s`, `enabled`, `run`, los tres últimos **callables lazy**) en el loop único del Plan 253 F5, junto a `register_syslog_purge_task` (`services/db_maintenance.py:59-74`, el molde exacto).
3. **Su KPI sería inmedible en este plan.** K5 (`secondsSince` medio) sólo tiene sentido con el daemon adentro; sin él, se declara **NO MEDIBLE** y no se usa como criterio (§1.1).

**Si en el futuro se decide hacerlo**, la ruta está escrita arriba y es una fase de un plan futuro, no un pedazo de este: `MaintenanceTask` + una flag `bool` que nace **OFF citando la excepción (A)** por escrito en su línea, más la entrada en `_EXPECTED_RESTART_REQUIRED` si la flag se lee en `create_app()`.

### 6.2. También fuera

- **Columna `tracker_updated_at` en `tickets`.** Motivo en §3.4: `_rebuild_tickets_table_if_needed` (`db.py:323`) tiene la lista hardcodeada y el propio código advierte (`db.py:283-287`) que la borraría en silencio **junto con el dato del operador**. Además la granularidad es equivocada.
- **Cualquier cambio de frontend.** El indicador de frescura (`frontend/src/components/syncStatus.ts:8`, `secondsSince`) y el `timeoutMs: 0` del sync manual (`frontend/src/api/endpoints.ts:239`) se dejan **exactamente como están**. `endpoints.ts` está sucio por la sesión paralela y tocarlo barrería trabajo ajeno.
- **El sync incremental de Azure DevOps, Jira o Mantis.** `ado_sync.sync_tickets` usa un camino distinto (`client.fetch_open_work_items()`, `services/ado_sync.py:113`) y `ado_provider.fetch_open_items` (`:53-64`) es un stub que ignora todo salvo `state` y `assignee` y cae a `[]`. El campo nuevo de `TrackerQuery` **no los afecta**, y extender el patrón a ellos es otro plan.
- **Subir `_DEFAULT_PAGE_CAP` o `_TOPE_PADRES`.** Son cotas de protección del sistema del operador. No se tocan.
- **Purgar, sanear o borrar filas.** Cero escritura correctiva en la base del operador.

---

## 7. Fases

> **Orden:** F0 → F1 → F2 → F3 → F4 → F5 → F6. F1, F2 y F3 son independientes entre sí y podrían hacerse en cualquier orden; F4 depende de las tres; F5 depende de F4; F6 depende de F5.
> **Un commit por fase.** Comando: `git commit -F <archivo_de_mensaje> -- "<ruta1>" "<ruta2>"`. **El `-F` va ANTES del `--`.**
> **Comando de test, siempre por archivo:**
> ```bash
> cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
> rm -f "$SCRATCH/t.db" "$SCRATCH/t.db-wal" "$SCRATCH/t.db-shm"
> STACKY_TEST_MODE=1 LLM_BACKEND=mock DATABASE_URL="sqlite:///$SCRATCH/t.db" \
>   ./.venv/Scripts/python.exe -m pytest "tests/<ARCHIVO>" -q
> ```
> donde `$SCRATCH` es el directorio de scratchpad de la sesión. **Base fresca por archivo, siempre.**
> **Trampa: `pytest -k` sin match sale con código 0, y un archivo inexistente sale con 4.** Nunca usar `-k` como criterio; siempre la ruta del archivo y leer el conteo.

---

### F0 — Baselines completos y las cuatro entradas de ratchet

**Objetivo (1 frase):** verificar los baselines ya medidos en §4 y dejar escrito **dónde** van los cuatro archivos de test nuevos en los dos ratchets, antes de que exista una sola línea de código de producto.

**Archivos:**
- `backend/scripts/run_harness_tests.sh` (símbolo `HARNESS_TEST_FILES`)
- `backend/scripts/run_harness_tests.ps1` (símbolo `$HarnessTestFiles`)

**Trabajo:**

1. **Re-correr** los baselines de §4 —**ya están los 17 medidos, ninguno queda abierto**— y confirmar que dan el mismo número. Si alguno difiere, manda la medición del día y se anota. *(En la v1 este paso era "medir los cinco que faltan"; la v2 los trae medidos, así que F0 pasa de medir a **verificar**.)*
2. **Registrar** en **ambos** scripts, **al final del array**, inmediatamente **antes del `)` de cierre** — es decir después de `tests/test_plan290_defaults_no_mienten.py` (anclaje por símbolo, §4.2). **NO en el bloque del Plan 291**: ése es el bloque temático del auto-PR de incidencias, y la convención de los planes 287-290 es apendear en la cola.

   En `run_harness_tests.sh` (rutas peladas, sin comillas, **sin comas**):
   ```
     # Plan 292 - el sync de GitLab deja de preguntar todo cada vez
     tests/test_plan292_watermark_store.py
     tests/test_plan292_sync_incremental.py
     tests/test_plan292_flags.py
     tests/test_plan292_paridad_runtimes.py
   ```
   En `run_harness_tests.ps1` (**entre comillas dobles y CON COMA**, como toda la cola — y hay que **agregarle la coma** a `"tests/test_plan290_defaults_no_mienten.py"`, que hoy es la última y por eso no la tiene):
   ```
     # Plan 292 - el sync de GitLab deja de preguntar todo cada vez
     "tests/test_plan292_watermark_store.py",
     "tests/test_plan292_sync_incremental.py",
     "tests/test_plan292_flags.py",
     "tests/test_plan292_paridad_runtimes.py"
   ```
   ⚠️ **La última entrada del array va SIN coma** — y la que hoy ocupa ese lugar deja de ser la última. Una coma faltante en medio del array no rompe ningún test del ratchet, pero PowerShell arma el array mal **en silencio**: por eso el criterio de F0 lo verifica **cargando el array**, no grepeando.
3. **No** agregar nada a `tests/harness_ratchet_allowlist.txt`.

**Caso borde:** los cuatro archivos **todavía no existen** cuando se hace este registro. `test_ratchet_no_referencia_archivos_inexistentes` (`tests/test_harness_ratchet_meta.py:79`) y `test_ninguna_ruta_apunta_a_un_archivo_inexistente` (`tests/test_plan259_ratchet_script_parity.py:101`) **fallarían**. ⇒ **El registro de cada archivo se hace en el commit de la fase que lo crea, no acá.** F0 sólo verifica los baselines y deja escrito **dónde** va cada uno. Esta es la razón exacta por la que el registro está distribuido por fase.

**Criterio BINARIO:**
```bash
# los baselines de §4 se RE-CORREN y deben coincidir; ya no hay ninguno sin medir
./.venv/Scripts/python.exe -m pytest "tests/test_harness_ratchet_meta.py" -q            # 4 passed
./.venv/Scripts/python.exe -m pytest "tests/test_plan259_ratchet_script_parity.py" -q   # 12 passed
./.venv/Scripts/python.exe -m pytest "tests/test_harness_flags_bounds.py" -q            # 1 failed, 17 passed (ROJO DE FABRICA)
./.venv/Scripts/python.exe -m pytest "tests/test_flag_wiring.py" -q                     # 5 passed
./.venv/Scripts/python.exe -m pytest "tests/test_harness_flags_requires.py" -q          # 9 passed
# la brecha de los ratchets, que arranca en 64/64
grep -cE '^\s*tests/[A-Za-z0-9_./-]+\.py\s*$' scripts/run_harness_tests.sh              # 831
grep -cE '^\s*"tests/[A-Za-z0-9_./-]+\.py",?\s*$' scripts/run_harness_tests.ps1         # 767
```
Todos deben dar **exactamente el número de la tabla de §4** (delta cero: F0 no toca los scripts todavía).

**Verificación EXTRA del `.ps1`, obligatoria en cada fase que lo toque (§4.2, punto 3):** un grep no detecta una coma faltante, pero PowerShell sí arma mal el array. Se comprueba **cargando el array**:
```powershell
powershell -NoProfile -Command "& { . { $HarnessTestFiles = @() }; $c = (Select-String -Path 'backend/scripts/run_harness_tests.ps1' -Pattern '^\s*\"tests/.*\.py\",?\s*$').Count; Write-Output $c }"
```
y comparando ese número con el conteo de rutas del `.sh` menos la brecha. Si el array quedara mal armado por una coma faltante, el `.ps1` **corre menos tests de los que declara** y ningún test del ratchet lo dice.

**Flag y default:** ninguna.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F1 — El carril: `TrackerQuery.updated_after`

**Objetivo (1 frase):** que la consulta al tracker pueda expresar "sólo lo que cambió después de esta fecha", sin que ningún llamador de hoy cambie de comportamiento.

**Tests PRIMERO** — archivo `backend/tests/test_plan292_sync_incremental.py` (se crea acá, se completa en F5):

| # | Caso | Qué asserta |
|---|---|---|
| 1 | `test_trackerquery_acepta_updated_after_y_su_default_es_none` | `TrackerQuery().updated_after is None` y `TrackerQuery(updated_after="2026-01-01T00:00:00Z").updated_after == "2026-01-01T00:00:00Z"` |
| 2 | `test_query_sin_updated_after_no_emite_el_parametro` | `_query_to_gitlab_params(TrackerQuery(state="open"))` devuelve **exactamente** `{"state": "opened"}` — la clave `updated_after` **no está** (`"updated_after" not in params`) |
| 3 | `test_query_con_updated_after_lo_emite_tal_cual` | `_query_to_gitlab_params(TrackerQuery(state="all", updated_after="2026-08-01T10:00:00Z"))` devuelve `{"updated_after": "2026-08-01T10:00:00Z"}` **y** `"state" not in params` |

**Cómo se comprueba el ROJO:** el caso 1 falla hoy con `TypeError: TrackerQuery.__init__() got an unexpected keyword argument 'updated_after'`; el caso 3 falla con `AssertionError` porque el dict sale vacío de `state`. Se corre el archivo **antes** de tocar el código de producto y se pega el output.

**Archivos y símbolos EXACTOS:**

1. `backend/services/tracker_provider.py` — dataclass `TrackerQuery` (`@dataclass(frozen=True)`, `:21-28`). Agregar como **último campo**:
   ```python
       updated_after: Optional[str] = None   # Plan 292 — ISO-8601 del tracker; None = sin filtro
   ```
   `Optional` ya está importado (`:18`). Al ser el último campo y tener default, **los llamadores posicionales siguen andando**.

2. `backend/services/gitlab_provider.py` — método `_query_to_gitlab_params` (`:122-136`). Agregar **al final**, antes del `return params`:
   ```python
       # Plan 292 — sólo lo que cambió. Se emite CRUDO, tal como lo guardó el store:
       # el valor sale del propio `updated_at` que devolvió GitLab, así que no hay
       # nada que reformatear y cualquier reformateo sería una oportunidad de perder
       # precisión.
       if q.updated_after:
           params["updated_after"] = q.updated_after
   ```

**Casos borde:**
- `updated_after=""` (string vacío) ⇒ el `if` es falsy ⇒ **no se emite**. Deliberado: un vacío es "no sé", y "no sé" nunca puede producir un filtro.
- `state="all"` ⇒ `_query_to_gitlab_params` **no emite `state`** (ya verificado: sólo mapea `"open"` y `"closed"`). GitLab sin `state` devuelve todos. **No se toca esa rama.**
- `ado_provider.fetch_open_items` (`:53-64`) ignora el campo nuevo. Correcto y deliberado: ADO no entra en este plan (§6.2).

**Criterio BINARIO:**
```bash
./.venv/Scripts/python.exe -m pytest "tests/test_plan292_sync_incremental.py" -q   # 3 passed
./.venv/Scripts/python.exe -m pytest "tests/test_gitlab_provider.py" -q            # 26 passed (delta cero)
./.venv/Scripts/python.exe -m pytest "tests/test_tracker_provider_conformance.py" -q  # 13 passed (delta cero)
./.venv/Scripts/python.exe -m pytest "tests/test_plan276_gitlab_sync.py" -q        # 21 passed (delta cero)
```

**Registro de ratchet:** en este commit se agregan al `.sh` **y** al `.ps1` la entrada `tests/test_plan292_sync_incremental.py` (§F0) — el archivo ya existe.

**Flag y default:** ninguna. **Es un carril sin consumidor**, y a propósito: el campo no cambia el comportamiento de nadie hasta F4.
**Impacto por runtime:** ninguno — `TrackerQuery` no se usa en ninguno de los tres runners (§3.6).
**Trabajo del operador:** ninguno.

---

### F2 — El store de la marca de agua

**Objetivo (1 frase):** un módulo nuevo que guarde, por proyecto, hasta qué momento se sincronizó, y que **degrade a "no sé" ante cualquier anomalía**.

**Tests PRIMERO** — archivo NUEVO `backend/tests/test_plan292_watermark_store.py`:

| # | Caso | Qué asserta |
|---|---|---|
| 1 | `test_sin_archivo_devuelve_none_y_contador_cero` | Con el archivo inexistente, `leer_marca("RIPLEY") == (None, 0)` |
| 2 | `test_escribir_y_leer_ida_y_vuelta` | Tras `escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 3)`, `leer_marca("RIPLEY") == ("2026-08-01T10:00:00Z", 3)` |
| 3 | `test_json_corrupto_degrada_a_none_sin_lanzar` | Con el archivo conteniendo `"{no es json"`, `leer_marca(...) == (None, 0)` y **no se lanza** |
| 4 | `test_marca_que_no_parsea_como_fecha_degrada_a_none` | Con `{"RIPLEY": {"marca": "ayer", "contador": 1}}`, `leer_marca(...) == (None, 0)` |
| 5 | `test_contador_no_entero_degrada_a_none` | Con `{"RIPLEY": {"marca": "2026-08-01T10:00:00Z", "contador": "tres"}}`, `leer_marca(...) == (None, 0)` |
| 6 | `test_json_que_no_es_objeto_degrada_a_none` | Con el archivo conteniendo `[1,2,3]`, `leer_marca(...) == (None, 0)` |
| 7 | `test_dos_proyectos_no_se_pisan` | Escribir "RIPLEY" y "RSPACIFICO"; leer cada uno devuelve **lo suyo** |
| 8 | `test_escribir_no_lanza_si_el_directorio_no_existe` | Con `data_dir()` apuntando a un subdirectorio inexistente, `escribir_marca` **crea el árbol** y no lanza |
| 9 | `test_marca_maxima_normaliza_z_y_milisegundos` | `marca_maxima(["2026-08-01T10:00:00.000Z", "2026-08-02T09:00:00.500Z"])` devuelve la segunda, y parsea con milisegundos |
| 10 | `test_marca_maxima_ignora_vacios_y_basura` | `marca_maxima(["", None, "ayer", "2026-08-01T10:00:00Z"])` devuelve la única válida; con la lista **toda** inválida devuelve `None` |
| 11 | `test_marca_maxima_de_lista_vacia_es_none` | `marca_maxima([]) is None` |
| **12** | **`test_la_marca_nunca_retrocede`** | **NUEVO en v2 (R11).** Tras `escribir_marca("RIPLEY", "2026-08-02T10:00:00Z", 1)`, un `escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 0)` deja la marca en **la del 02**, no la del 01. **Mitad de contraste:** con `escribir_marca` guardando `nueva` a secas, este caso debe **fallar** |
| **13** | **`test_la_marca_avanza_si_la_nueva_es_mas_nueva`** | El complemento del 12: del 01 al 02 **sí** avanza. Sin este caso, el 12 se podría satisfacer con un `escribir_marca` que **nunca** escriba nada |
| **14** | **`test_admitir_del_delta_solo_bloquea_al_cerrado_desconocido`** | **NUEVO en v2 (§3.1-bis).** Los cuatro cuadrantes de la tabla de §3.1-bis, en modo `"incremental"`: `(opened, existe)→True`, `(opened, no existe)→True`, `(closed, existe)→True`, `(closed, no existe)→**False**` |
| **15** | **`test_admitir_del_delta_no_bloquea_nada_en_modo_completo`** | Los mismos cuatro cuadrantes con `modo="completo"` ⇒ **los cuatro `True`**. Es la garantía de que el modo de hoy queda byte-idéntico |
| **16** | **`test_admitir_del_delta_trata_el_estado_ausente_como_abierto`** | Un ítem sin clave `state` (o con `""`) se admite: `_upsert_ticket_gitlab` ya cae a `"opened"` (`gitlab_sync.py:148`), y la barrera **no puede ser más estricta que el upsert** o saltearía ítems válidos |

**Cómo se comprueba el ROJO:** el archivo entero falla hoy con `ModuleNotFoundError: No module named 'services.gitlab_sync_watermark'`. Se corre y se pega el output.

**Archivo NUEVO:** `backend/services/gitlab_sync_watermark.py`

```python
"""services/gitlab_sync_watermark.py — Plan 292.

Hasta qué momento se sincronizó cada proyecto de GitLab. Molde EXACTO de
`services/integration_breaker.py` (:55-67): un JSON en data_dir(), lectura
tolerante que degrada a vacío, escritura best-effort.

POR QUÉ TOLERA TODO. Este store existe para AHORRAR trabajo, nunca para
habilitarlo. Cada camino de error devuelve "no sé", y "no sé" significa
sincronización COMPLETA — o sea, exactamente lo que el sync hacía antes de que
este módulo existiera. NINGÚN fallo de acá puede hacer que el sync traiga MENOS
de lo que traería sin este módulo.

LA HORA ES LA DE GITLAB, NUNCA LA DE LA MÁQUINA. La marca sale de
`item["updated_at"]`, que lo puso el servidor. Con `datetime.utcnow()`, un reloj
local adelantado dejaría fuera del delta siguiente todo lo modificado en la
ventana de desfase, en silencio y para siempre.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import config  # el MÓDULO: la instancia de opciones es `config.config`
from runtime_paths import data_dir

logger = logging.getLogger(__name__)

_FILENAME = "gitlab_sync_watermark.json"
_LOCK = threading.Lock()

# Cota de seguridad, NO opción de operador. Mismo criterio que `_TOPE_PADRES = 50`
# de gitlab_sync.py:47. 120 s cubren dos cosas a la vez: el issue modificado
# DURANTE el sync (entre la primera página y la última) y la duda sobre si
# `updated_after` de GitLab es inclusivo o exclusivo — con este solapamiento el
# diseño es correcto en los dos casos.
_SOLAPAMIENTO_SEG = 120

# Si la marca quedó más vieja que esto, se hace una corrida COMPLETA aunque el
# contador no haya llegado a su cuota. Red de seguridad para el backend apagado
# varios días.
_EDAD_MAX_MARCA_H = 24


def _path():
    return data_dir() / _FILENAME


def _load() -> dict:
    """Todo el archivo, o {} ante CUALQUIER anomalía. Nunca lanza."""
    try:
        p = _path()
        if not p.exists():
            return {}
        datos = json.loads(p.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except Exception:   # noqa: BLE001 — degradar a COMPLETO es siempre correcto
        logger.warning("Plan 292: marca de sincronización ilegible; se hará completa", exc_info=True)
        return {}


def _save(datos: dict) -> None:
    """Best-effort. Si no se puede escribir, la próxima corrida es completa."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(datos, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:   # noqa: BLE001
        logger.warning("Plan 292: no se pudo guardar la marca de sincronización", exc_info=True)


def parsear(valor) -> Optional[datetime]:
    """ISO-8601 de GitLab -> datetime naive UTC. None si no parsea.

    Receta idéntica a services/ado_sync.py:57. NO usar strptime con "%SZ": los
    milisegundos de GitLab (".000Z") lo rompen.
    """
    if not valor or not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def marca_maxima(valores) -> Optional[str]:
    """El `updated_at` más nuevo de la tanda, MENOS el solapamiento, en ISO con Z.

    Devuelve None si la tanda está vacía o si ninguno parsea — y ese None hace
    que el llamador NO toque la marca guardada, que es lo correcto: un delta
    vacío significa "no cambió nada", no "avanzá el reloj".
    """
    fechas = [d for d in (parsear(v) for v in (valores or [])) if d is not None]
    if not fechas:
        return None
    tope = max(fechas) - timedelta(seconds=_SOLAPAMIENTO_SEG)
    return tope.isoformat(timespec="seconds") + "Z"


def leer_marca(proyecto: str) -> tuple[Optional[str], int]:
    """(marca_iso, contador_de_parciales) o (None, 0) ante cualquier anomalía."""
    with _LOCK:
        entrada = _load().get(proyecto)
    if not isinstance(entrada, dict):
        return (None, 0)
    marca = entrada.get("marca")
    contador = entrada.get("contador")
    # `isinstance(True, int)` es True en Python: el `is True` descarta booleanos,
    # que en un JSON escrito a mano son un error de tipo, no un contador.
    if parsear(marca) is None or not isinstance(contador, int) or contador is True or contador < 0:
        return (None, 0)
    return (marca, contador)


def escribir_marca(proyecto: str, marca: Optional[str], contador: int) -> None:
    """Guarda la marca del proyecto. MONOTONA: la marca nunca retrocede.

    Si `marca` es None (delta vacío o toda la tanda ilegible) NO la toca.
    Si `marca` es MAS VIEJA que la guardada, tampoco: se conserva la vieja.

    POR QUE NUNCA RETROCEDE (plan 292 v2, R11). En modo COMPLETO la query es de
    ABIERTOS, así que `items` no incluye los cerrados. Si el cambio más reciente
    del proyecto fue sobre un issue cerrado, el max(updated_at) de esa tanda es
    MAS VIEJO que la marca que dejó el último incremental. Escribirlo haría que
    la corrida siguiente pidiera una ventana enorme — matando el ahorro y
    arrastrando una tanda grande de cerrados.

    Quedarse ATRAS sólo cuesta traer de más, que es el lado seguro; adelantarse
    pierde ítems en silencio. La asimetría es la misma que gobierna todo el
    módulo, y por eso acá se resuelve con un max() y no con una condición.
    """
    with _LOCK:
        datos = _load()
        actual = datos.get(proyecto) if isinstance(datos.get(proyecto), dict) else {}
        previa = actual.get("marca")
        elegida = previa
        if marca is not None:
            d_nueva, d_previa = parsear(marca), parsear(previa)
            if d_previa is None or (d_nueva is not None and d_nueva > d_previa):
                elegida = marca
        datos[proyecto] = {
            "marca": elegida,
            "contador": max(0, int(contador)),
        }
        _save(datos)


# ── Plan 292 v2 §3.1-bis — la barrera de admisión del delta ────────────────────
# Estados que GitLab reporta como "no cerrado". `_upsert_ticket_gitlab` cae a
# "opened" cuando el campo falta (gitlab_sync.py:148), así que la barrera NO
# puede ser más estricta que él: un ítem sin estado se admite.
_ESTADOS_ABIERTOS = ("opened", "reopened", "")


def admitir_del_delta(item: dict, *, fila_existe: bool, modo: str) -> bool:
    """¿Este ítem del listado puede llegar al upsert?

    En modo COMPLETO devuelve SIEMPRE True: la query es de abiertos, ningún
    cerrado llega, y el camino queda byte-idéntico al de antes de este plan.

    En modo INCREMENTAL la query es `state="all"`, así que SI llegan cerrados.
    Un cerrado que YA tiene fila local se admite —es la detección de cierre de
    §3.1—, pero un cerrado que NO tiene fila local se SALTEA: hoy esa fila no
    existe, `list_tickets` (api/tickets.py:1104) no filtra por estado y ordena
    por last_synced_at con tope 500, así que crearla la pondría arriba del
    tablero del operador y le comería una posición a un abierto real. Nadie la
    saca nunca: el modo COMPLETO marca cerrado por ausencia, jamás borra.
    """
    if modo != "incremental":
        return True
    if fila_existe:
        return True
    estado = (item.get("state") or "").strip().lower()
    return estado in _ESTADOS_ABIERTOS
```

**Casos borde declarados en el código:**
- `isinstance(True, int)` es `True` en Python ⇒ el guard `contador is True` es **necesario**, no defensivo de más.
- `escribir_marca(proyecto, None, n)` conserva la marca anterior y sólo actualiza el contador — es el camino del delta vacío.
- `_LOCK` serializa lectura-modificación-escritura, igual que `services/server_registry.py:34`.

**⚠️ Requisito de test innegociable (R8):** `data_dir()` es `backend/data/`, la carpeta de la base de 194 MB del operador. Los **dieciséis** casos **deben** monkeypatchear la ruta:
```python
monkeypatch.setattr("services.gitlab_sync_watermark.data_dir", lambda: tmp_path)
```
y el primer caso del archivo **debe** asertar `tmp_path.name in str(store._path())` antes de escribir nada — el mismo cinturón que `tests/test_plan276_gitlab_sync.py:53` usa para la base.

**Criterio BINARIO:**
```bash
./.venv/Scripts/python.exe -m pytest "tests/test_plan292_watermark_store.py" -q   # 16 passed
ls "backend/data/gitlab_sync_watermark.json"   # NO debe existir tras correr los tests
```

**Mitad de contraste de F2** (obligatoria, §8): con `escribir_marca` guardando `marca` a secas en vez de `max(...)`, el caso 12 **debe fallar** y el 13 debe seguir pasando. Si el 12 pasara con el parche puesto, el gate es vacuo y hay que rehacerlo.

**Registro de ratchet:** en este commit, `tests/test_plan292_watermark_store.py` en los **dos** scripts.

**Flag y default:** ninguna todavía — el módulo no tiene consumidor hasta F4.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F3 — Las dos opciones

**Objetivo (1 frase):** registrar la opción de sincronización parcial (encendida) y la cuota de corridas completas, cumpliendo los ocho guardianes.

**Tests PRIMERO** — archivo NUEVO `backend/tests/test_plan292_flags.py`:

| # | Caso | Qué asserta |
|---|---|---|
| 1 | `test_las_dos_keys_estan_en_el_registro` | Las 2 keys están en `FLAG_REGISTRY`, sin duplicados |
| 2 | `test_la_booleana_nace_encendida` | `declared_default(spec) is True` y `default_is_known(spec) is True`, y la key está en `_CURATED_DEFAULTS_ON` |
| 3 | `test_la_numerica_no_declara_default` | `spec.default is None` y `default_is_known(spec) is False` |
| 4 | `test_la_numerica_declara_cotas` | `min_value == 1` y `max_value == 1000` |
| 5 | `test_ninguna_declara_requires` | `spec.requires is None` en las dos — protege la decisión de §3.5 |
| 6 | `test_las_dos_existen_en_config` | `hasattr(config.config, key)` para las 2; la booleana vale `True` y la numérica `10` con el entorno limpio |
| 7 | `test_las_dos_estan_categorizadas_en_paridad_proveedores` | `_KEY_CATEGORY[key] == "paridad_proveedores"` para las 2 |
| 8 | `test_las_dos_tienen_ayuda_llana` | Las 2 están en `PLAIN_HELP`, con los 4 campos no vacíos y dentro de sus topes |
| 9 | `test_la_ayuda_llana_respeta_la_denylist` | **Importa `JARGON_DENYLIST` de `tests/test_harness_flags_help.py`** y la aplica a las 2 entradas nuevas, más las prohibiciones de `[A-Z]+_[A-Z0-9_]+` y `F\d` |
| 10 | `test_la_ayuda_llana_empieza_con_si_sin_tilde` | `on_effect` y `off_effect` de las 2 empiezan con `"Si "` |
| **11** | **`test_la_numerica_esta_en_el_mapa_congelado_de_cotas`** | **NUEVO en v2 (§4.1-bis).** Importa `_FROZEN_BOUNDS` de `tests/test_harness_flags_bounds.py` y asserta `_FROZEN_BOUNDS["STACKY_GITLAB_SYNC_FULL_CADA_N"] == (1, 1000)`. **Sin este caso, olvidarse del paso 6 de §4.3 es indetectable**: el archivo ajeno queda en 1F/17P en los tres escenarios posibles |
| **12** | **`test_la_booleana_no_esta_en_el_mapa_de_cotas`** | `"STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED" not in _FROZEN_BOUNDS` — una `bool` no declara cotas. Es la **mitad de contraste** del caso 11: guarda la PRESENCIA de una y la AUSENCIA de la otra en el mismo archivo, para que ninguna de las dos pase por accidente |

**Por qué el caso 9 importa la regla en vez de correr el archivo ajeno:** `tests/test_harness_flags_help.py` está **rojo de fábrica (4F/4P)**, así que su conteo no discrimina — si la entrada nueva violara el denylist, el total seguiría en 4F/4P. Importar `JARGON_DENYLIST` trae la regla al archivo verde de este plan. Patrón ya usado en `tests/test_plan257_flags.py:99-110`.

**Cómo se comprueba el ROJO:** el archivo entero falla hoy; los casos 1 y 6 con `KeyError`/`AssertionError` porque las keys no existen. Se corre antes de declarar nada y se pega el output.

**Los seis sitios de declaración (§4.3), texto exacto:**

**1. `backend/config.py`** — antes de `config = Config()` (hoy `:2732`):
```python
    # ── Plan 292 — El sync de GitLab deja de preguntar todo cada vez ──────────
    # Nace ON. No cae en (A): no enciende ningún loop, daemon ni barrido — al
    # contrario, ABARATA un poll que ya corre cada 45 s desde el tablero. No cae
    # en (B): es camino de LECTURA, y de hecho APAGA la única regla del sync que
    # marca filas como cerradas. Curada en _CURATED_DEFAULTS_ON.
    STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED: bool = os.getenv(
        "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")

    # Cada cuántas corridas parciales consecutivas se fuerza una completa. Es la
    # red que detecta lo que el delta NO puede ver: un issue BORRADO de GitLab.
    STACKY_GITLAB_SYNC_FULL_CADA_N: int = int(
        os.getenv("STACKY_GITLAB_SYNC_FULL_CADA_N", "10")
    )
```

**2. `backend/services/harness_flags.py`, `_CATEGORY_KEYS`** — dentro de la tupla de `"paridad_proveedores"` (abre `:587`, cierra `),` en `:615`), **al final**, después de `STACKY_TRACKER_CONTEXT_ENABLED` (`:614`) y antes del `),` — la tupla está ordenada **cronológicamente por plan**:
```python
        # Plan 292 — el sync de GitLab pide sólo lo que cambió
        "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED",
        "STACKY_GITLAB_SYNC_FULL_CADA_N",
```

**3. `backend/services/harness_flags.py`, `FLAG_REGISTRY`** — antes del `)` de cierre (hoy `:7353`):
```python
    # ── Plan 292 — el sync de GitLab deja de preguntar todo cada vez ──────────
    FlagSpec(
        key="STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED",
        type="bool",
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        # Nace ON: no cae en (A) —no enciende loop, daemon, barrido ni llamada a
        # modelo; abarata un poll que YA existe— ni en (B) —es lectura pura, no
        # publica, no commitea, no escribe en el tracker y APAGA la única regla
        # del sync que marca filas como cerradas—. Con OFF el sync vuelve
        # byte-idéntico al de hoy: es la palanca de rollback.
        #
        # SIN requires= A PROPOSITO: STACKY_GITLAB_ENABLED no está en
        # FLAG_REGISTRY (rompería R1 de validate_requires_graph) y la dependencia
        # con STACKY_GITLAB_SYNC_ENABLED ya está resuelta EN CODIGO (si el sync
        # está apagado, esto es inalcanzable). Mismo criterio deliberado que el
        # plan 269, ver tests/test_harness_flags_requires.py:351-352.
        default=True,
        label="Traer de GitLab sólo lo que cambió",
        description=(
            "Plan 292 — Stacky le pide a GitLab únicamente los ítems modificados "
            "desde la última vez que miró, en vez de pedir la lista entera cada "
            "45 segundos. Cada tanto igual pide todo, para no perderse un ítem "
            "borrado en el servidor. Nace ENCENDIDA porque sólo lee y le saca "
            "trabajo al GitLab de la empresa. Con esto apagado, Stacky vuelve a "
            "pedir la lista completa en cada consulta, como antes."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_GITLAB_SYNC_FULL_CADA_N",
        # SIN default= A PROPOSITO (regla dura): `default_is_known(spec)` es
        # literalmente `spec.default is not None`, y declararlo metería esta key
        # en el conjunto que test_default_known_only_for_curated exige que sea
        # EXACTAMENTE _CURATED_DEFAULTS_ON — que es sólo para booleanas ON. El
        # valor 10 vive SOLO en config.py.
        type="int",
        min_value=1,
        max_value=1000,
        label="Cada cuántas consultas se pide la lista completa",
        description=(
            "Plan 292 — Va de la mano de la opción anterior. Aunque Stacky pida "
            "sólo los cambios, cada tanto necesita pedir la lista completa para "
            "descubrir ítems que desaparecieron del servidor, porque un ítem "
            "borrado no aparece en la lista de cambios. Con 10, una de cada diez "
            "consultas es completa. Bajarlo la hace más segura y más cara; "
            "subirlo, al revés. Además se pide todo si pasaron más de 24 horas."
        ),
        group="global",
        env_only=False,
    ),
```

**4. `backend/services/harness_flags_help.py`, `PLAIN_HELP`** — antes del `}` de cierre (hoy `:2505`). **Redactado contra la denylist de §4.4: no dice "endpoint", "backend", "gate", "runtime", "token", "prompt"; no nombra ninguna variable en mayúsculas; no dice "F" seguido de número; y los dos efectos empiezan con `"Si "` sin tilde:**
```python
    "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED": PlainHelp(
        what="Hace que Stacky le pida a GitLab sólo los ítems que cambiaron desde la última consulta, en vez de la lista completa cada vez.",
        on_effect="Si la activás: cada consulta trae únicamente lo que se modificó, y cada tanto se pide la lista entera para no perderse un ítem borrado en el servidor.",
        off_effect="Si la apagás: cada consulta vuelve a traer la lista completa de ítems abiertos, exactamente como se hacía antes. Sirve para volver atrás si algo no cierra.",
        example="Con 63 ítems abiertos y ningún cambio, la consulta pasa de traer los 63 enteros a no traer ninguno. Como pedir sólo las cartas nuevas del buzón en vez de vaciarlo entero cada vez.",
    ),
    "STACKY_GITLAB_SYNC_FULL_CADA_N": PlainHelp(
        what="Cada cuántas consultas parciales seguidas Stacky vuelve a pedirle a GitLab la lista completa de ítems.",
        on_effect="Si subís el número: se pide la lista completa menos seguido, así que se gasta menos y se tarda más en notar que un ítem desapareció del servidor.",
        off_effect="Si bajás el número: se pide la lista completa más seguido, así que se nota antes un ítem borrado pero se le da más trabajo al servidor de la empresa.",
        example="Con 10, una de cada diez consultas trae la lista entera y las otras nueve traen sólo lo que cambió. Además se pide todo si pasaron más de 24 horas desde la última vez.",
    ),
```

> **Estilo verificado sobre el archivo real, no inventado.** Las entradas existentes usan `"Si la activás: …"` / `"Si la apagás: …"` para las booleanas y `"Si subís el número: …"` / `"Si bajás el número: …"` para las numéricas (ver `harness_flags_help.py:20-21`, que lo documenta en el propio `dataclass`, y `:2499-2504` como ejemplo vivo). Las cuatro entradas de arriba respetan ese estilo **y** las tres prohibiciones de §4.4: ninguna contiene un término de la lista de jerga, ninguna nombra una variable en mayúsculas con guión bajo, ninguna dice "F" seguido de número, y las cuatro líneas de efecto empiezan con `"Si "` sin tilde. Longitudes dentro de los topes (`what` ≤200, efectos ≤240, `example` ≤300) — **verificar con `len()` al implementar, no confiar en el ojo**.

**5. `backend/tests/test_harness_flags.py`, `_CURATED_DEFAULTS_ON`** — antes del `}` de cierre (hoy `:1121`), **sólo la booleana**:
```python
    # ── Plan 292 — el sync de GitLab pide sólo lo que cambió ─────────────────
    # Nace ON. No cae en (A): no enciende loop, daemon, barrido ni llamada a
    # modelo — abarata un poll que ya corría cada 45 s desde el tablero, así que
    # el gasto en reposo BAJA, no sube. No cae en (B): es camino de lectura, no
    # publica, no commitea, no escribe en el tracker del operador ni le saca
    # ninguna decisión; al contrario, APAGA la única regla del sync que marca
    # filas como cerradas. Con OFF el comportamiento vuelve byte-idéntico al de
    # hoy: existe sólo como palanca de rollback.
    "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED",
```

**6. `backend/tests/test_harness_flags_bounds.py`, `_FROZEN_BOUNDS`** — antes del `}` de cierre (hoy `:227`), **sólo la numérica**:
```python
    "STACKY_GITLAB_SYNC_FULL_CADA_N": (1, 1000),   # Plan 292
```

**Casos borde:**
- `STACKY_GITLAB_SYNC_FULL_CADA_N` con un valor no numérico en el entorno haría reventar `int()` **al importar `config`**. Es el mismo patrón que ya usan las demás numéricas del archivo, y el consumidor de F4 igual acota con `max(1, ...)`. **No se cambia el patrón del archivo** por una flag.
- La lectura en `services/` va **siempre** por `getattr(config.config, ...)`, nunca por `os.getenv` (§4.5).

**Criterio BINARIO:**
```bash
./.venv/Scripts/python.exe -m pytest "tests/test_plan292_flags.py" -q                    # 12 passed
./.venv/Scripts/python.exe -m pytest "tests/test_harness_flags.py" -q                    # 59 passed (delta cero)
./.venv/Scripts/python.exe -m pytest "tests/test_harness_flags_bounds.py" -q             # 1 failed, 17 passed — ROJO DE FABRICA, delta cero. NO discrimina: quien valida es el caso 11
./.venv/Scripts/python.exe -m pytest "tests/test_harness_flags_requires.py" -q           # 9 passed (delta cero: NO se declaró requires)
./.venv/Scripts/python.exe -m pytest "tests/test_flag_wiring.py" -q                      # 5 passed — VERDE, no rojo. Ver §4.3-bis
./.venv/Scripts/python.exe -m pytest "tests/test_harness_flags_help.py" -q               # 4 failed, 4 passed (delta cero)
./.venv/Scripts/python.exe -m pytest "tests/test_flags_env_read_meta.py" -q              # 1 failed, 1 passed (delta cero)
./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from services.harness_flags import FLAG_REGISTRY; print(len(FLAG_REGISTRY))"   # 495 (493 medido + 2)
```

**F3 y F4 van en el MISMO commit.** *(La v1 llegaba a la misma decisión con un argumento falso; queda corregido, porque el argumento falso sobrevive a la decisión y confunde a quien lo lea después.)*

- **Lo que la v1 decía y NO es cierto:** que `test_flag_wiring.py` daría rojo al cierre de F3. **No lo da.** `_production_corpus()` **incluye `backend/config.py`** por decisión explícita y documentada (`tests/test_flag_wiring.py:29-38`), así que declarar las keys en `config.py` ya las hace "cableadas" para ese guardián. Baseline hoy y después: **5 passed**. Ver §4.3-bis.
- **El motivo real de juntarlas:** una opción visible en Configuración global que no hace nada es una promesa rota para el operador. Es un riel de producto, no una imposición del arnés.
- **La opción (b) —`reserved=True` en F3— queda DESCARTADA con evidencia**, no por preferencia: `test_reserved_flags_are_actually_dead` (`tests/test_flag_wiring.py:73`) exige que una key reservada **no** aparezca en el corpus, y en F3 ya estaría en `config.py`. Declararla reservada pondría ese test en rojo. La v1 la ofrecía como alternativa válida; **no lo es**.

**Registro de ratchet:** en este commit, `tests/test_plan292_flags.py` en los **dos** scripts.

**Flag y default:** las dos de arriba.
**Impacto por runtime:** ninguno — son opciones globales, leídas en un servicio transversal (§3.6).
**Trabajo del operador:** ninguno. Las dos quedan visibles y ajustables desde Configuración global.

---

### F4 — El sync elige su modo (fase hito)

**Objetivo (1 frase):** que `sync_gitlab_tickets` decida entre completo y parcial, apague la regla de ausencia cuando corresponda, y guarde la marca.

> **Va en el MISMO commit que F3** (decisión (a) de arriba).

**Tests PRIMERO:** todos los casos de F5. Esta fase se implementa **contra** ese archivo, que se escribe **antes**.

**Archivos y símbolos EXACTOS:**

**1. `backend/services/gitlab_sync_watermark.py`** — agregar la función pura de decisión:

```python
def decidir_modo_de_sync(proyecto: str, *, forzar_full: bool = False,
                         ahora: Optional[datetime] = None) -> tuple[str, str, Optional[str], int]:
    """(modo, motivo, marca, contador). modo es "completo" o "incremental".

    Función PURA salvo por la lectura del archivo y de las opciones: no escribe,
    no llama a la red, y `ahora` es inyectable para poder probar el vencimiento
    sin dormir. El orden de las condiciones es de EVALUACIÓN, no de prioridad:
    se devuelve el primer motivo que aplica (ver plan 292 §3.2).
    """
    ahora = ahora or datetime.utcnow()
    if forzar_full:
        return ("completo", "pedido_explicito", None, 0)
    if not bool(getattr(config.config, "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED", True)):
        return ("completo", "opcion_apagada", None, 0)
    marca, contador = leer_marca(proyecto)
    if marca is None:
        # Cubre a la vez "primera corrida" y "archivo ilegible": leer_marca ya
        # colapsó los dos en (None, 0). El motivo se distingue por la existencia
        # del archivo, que es lo único que los separa para el operador.
        return ("completo", "sin_marca" if not _path().exists() else "marca_ilegible", None, 0)
    momento = parsear(marca)
    if momento is None or (ahora - momento) > timedelta(hours=_EDAD_MAX_MARCA_H):
        return ("completo", "marca_vencida", None, 0)
    # La marca del FUTURO también vence: si el reloj de GitLab (o una edición a
    # mano del archivo) dejó una marca posterior a `ahora`, el delta siguiente
    # vendría vacío para siempre y el tablero se congelaría en silencio. Se
    # degrada a COMPLETO, que es el default de todo camino anómalo (§3.2).
    if momento > ahora + timedelta(hours=1):
        return ("completo", "marca_vencida", None, 0)
    try:
        cuota = max(1, int(getattr(config.config, "STACKY_GITLAB_SYNC_FULL_CADA_N", 10)))
    except (TypeError, ValueError):
        cuota = 10
    if contador >= cuota:
        return ("completo", "cuota_cumplida", None, 0)
    return ("incremental", "", marca, contador)
```

**2. `backend/services/gitlab_sync.py`, función `sync_gitlab_tickets` (def en `:235`)** — cambiar la firma y el cuerpo:

```python
def sync_gitlab_tickets(project_name: str, *, provider=None, forzar_full: bool = False) -> dict:
```

Reemplazar la línea `:257` por:

```python
    # ── Plan 292 — el modo se decide ANTES de armar la query ────────────────
    # El docstring de este módulo (:21-25) anticipó exactamente este cambio: la
    # query de abiertos y la regla de `removed` "van juntas". Acá se cumple esa
    # advertencia — cuando la query deja de ser de abiertos, la regla se APAGA.
    from services import gitlab_sync_watermark as _wm

    modo, motivo, marca, contador_previo = _wm.decidir_modo_de_sync(
        ctx.stacky_project_name, forzar_full=forzar_full
    )
    if modo == "incremental":
        # `state="all"` a propósito: con `state="open"` un issue CERRADO después
        # de la marca no vendría en la respuesta y el cierre sería INDETECTABLE
        # (ni por presencia ni por ausencia, que está apagada). Con "all" viene
        # con state="closed" y `_upsert_ticket_gitlab` lo refleja solo (:227).
        # `_query_to_gitlab_params` no emite `state` para "all" (gitlab_provider
        # .py:124-127) y GitLab sin `state` devuelve todos.
        consulta = TrackerQuery(state="all", updated_after=marca)
    else:
        # BYTE-IDÉNTICO a lo que había antes de este plan.
        consulta = TrackerQuery(state="open")
    items = provider.fetch_open_items(consulta)
```

**2-bis. `backend/services/gitlab_sync.py`, dentro del bucle `for item in items:`** — la barrera de admisión (§3.1-bis). Va **después** de `vistos_external.add(external_id)` y **antes** de la llamada a `_upsert_ticket_gitlab`, porque necesita saber si la fila existe:

```python
            # ── Plan 292 v2 §3.1-bis — la barrera de admisión ────────────────
            # `state="all"` no sólo LEE distinto: haría que un issue CERRADO y
            # desconocido localmente se INSERTE como fila nueva (la rama
            # `if fila is None` del upsert no mira el estado). Hoy esa fila no
            # existe, nadie la borra nunca, y `list_tickets` la mostraría arriba
            # del tablero comiéndose una de las 500 posiciones. Ver §2.7.
            _existe = (
                session.query(Ticket.id)
                .filter(
                    Ticket.stacky_project_name == stacky_name,
                    Ticket.tracker_type == _TRACKER,
                    Ticket.external_id == external_id,
                )
                .first()
                is not None
            )
            if not _wm.admitir_del_delta(item, fila_existe=_existe, modo=modo):
                omitidos_cerrados_desconocidos += 1
                # SALE de `vistos_external`: no vino a decir que sigue abierto.
                vistos_external.discard(external_id)
                continue
```

⚠️ **`vistos_external.discard(...)` es obligatorio y no es cosmético.** Si el `external_id` quedara en el conjunto, en una corrida COMPLETA posterior el `IN` lo trataría como "visto" — pero el bloque de ausencia sólo corre en modo completo, donde la barrera nunca saltea nada, así que hoy no hay camino que lo use. **Se hace igual**, porque el conjunto tiene que significar exactamente una cosa —"GitLab lo listó como parte del universo consultado"— y un ítem salteado no lo es. Un conjunto con dos significados es cómo nace el próximo bug de esta familia.

> **Costo:** un `SELECT id` extra por ítem del delta, sólo en modo parcial, sobre el índice único `ux_tickets_stacky_tracker_external` (`models.py:77-83`) — la misma terna que el upsert ya usa dos líneas más abajo. En estado estable el delta es de 0 ítems, así que el costo real es **cero**. No se optimiza a un `IN` masivo por adelantado: sería una abstracción prematura sobre un camino que casi siempre está vacío.

Envolver el bloque de ausencia (`:312-326`) con el guard del modo:

```python
        # Plan 292 — LA REGLA DE AUSENCIA SOLO ES VALIDA EN MODO COMPLETO.
        # En modo parcial la respuesta NO contiene todo lo abierto, así que este
        # bloque marcaría `closed` todo lo que no cambió: hoy serían 61 de las 63
        # filas de RIPLEY. La condición NO es "hay flag": es "la query fue de
        # abiertos". Van juntas, tal como avisa el docstring de :21-25.
        if modo == "completo" and vistos_external:
            ...   # el cuerpo de hoy, sin tocar una línea
```

Al final, antes de armar `resultado`, dentro del `with session_scope()` **no** — **después** de cerrarlo, para no atar la escritura del JSON a la transacción:

```python
    # ── Plan 292 — avanzar la marca ────────────────────────────────────────
    # Se hace DESPUÉS de cerrar la sesión: si la transacción falla, `session_scope`
    # levanta y no se llega acá, así que la marca NUNCA avanza sobre datos que no
    # se guardaron. El orden importa y es deliberado.
    nueva = _wm.marca_maxima([i.get("updated_at") for i in items])
    # `marca_maxima` devuelve None con la tanda vacía o toda inválida, y
    # `escribir_marca` con None CONSERVA la marca anterior: un delta vacío
    # significa "no cambió nada", nunca "avanzá el reloj".
    _wm.escribir_marca(
        stacky_name, nueva, 0 if modo == "completo" else contador_previo + 1
    )
```

Y agregar al dict `resultado` (aditivo, las 5 claves de siempre no cambian):
```python
        # Plan 292 — ADITIVO. El consumidor (api/tickets.py:6703, :6713) lee
        # created/updated/removed y sigue andando sin tocar una línea.
        "modo_sync": modo,
        "motivo_modo": motivo,
        "omitidos_cerrados_desconocidos": omitidos_cerrados_desconocidos,
        "bytes_recibidos": bytes_recibidos,
```

**6. [ADICIÓN ARQUITECTO] — `bytes_recibidos`: el KPI deja de ser una promesa y pasa a medirse solo**

El problema que resuelve: **K1 no se puede medir**. El doble de test devuelve lo que el test le puso, así que `fetched == 0` prueba el mecanismo y nada más — es tautológico. Y medirlo de verdad exigiría consultar el GitLab del operador, que este plan tiene **prohibido**. Queda un hueco: el plan promete un ahorro que nadie va a confirmar nunca.

La salida es medir el ahorro **donde ya está el dato**: el sync ya tiene los ítems en la mano. Dos líneas, junto a `resultado`:

```python
    # ── Plan 292 v2 [ADICIÓN ARQUITECTO] — el ahorro se mide solo ───────────
    # El tamaño serializado de lo que GitLab mandó. NO es el byte exacto del
    # cable (falta compresión y cabeceras) y por eso el nombre dice "recibidos"
    # y no "transferidos": lo que interesa es la SERIE, no el valor absoluto.
    # En estado estable esta clave cae a 0 y el operador lo ve en su propio log,
    # sin que nadie le pregunte nada a GitLab. Best-effort: un ítem no
    # serializable NO puede tumbar un sync que ya terminó bien.
    try:
        import json as _json
        bytes_recibidos = len(_json.dumps(items, default=str).encode("utf-8"))
    except Exception:  # noqa: BLE001
        bytes_recibidos = -1
```

Por qué vale la pena, y por qué es barato:

| | |
|---|---|
| **Qué habilita** | El log del sync ya existe (`gitlab_sync.py:406`, `logger.info("Plan 276 sync GitLab '%s': %s", ...)` imprime el dict entero). Con la clave adentro, el operador tiene la **serie temporal** del ahorro sin instrumentar nada |
| **Qué cuesta** | un `json.dumps` sobre una lista que en estado estable está **vacía**. Con los 63 issues de RIPLEY (~205 KB) es del orden de un milisegundo, y sólo en las corridas completas |
| **Qué NO es** | no es una flag, no es un endpoint, no es UI, no es una tabla. Es una clave más en un dict que ya es aditivo por diseño (§F4, punto 5) |
| **Cómo se prueba** | §F5 caso 18, **ejecutando**: corrida completa ⇒ `bytes_recibidos > 0`; corrida parcial en estado estable ⇒ `bytes_recibidos == 0` |

**El límite, dicho:** no mide bytes de red (gzip, cabeceras, TLS). Mide **carga serializada**, que es la magnitud que el plan efectivamente baja y la única honesta sin tocar el servidor. K6 de §1.1 lo declara así.

**3. `backend/api/tickets.py`, `_sync_via_provider_or_ado` (def en `:1144`)** — firma y propagación:

```python
def _sync_via_provider_or_ado(project_name: str | None, *, forzar_full: bool = False) -> dict:
```
y en `:1210`:
```python
            return sync_gitlab_tickets(project_name, provider=provider, forzar_full=forzar_full)
```
En el llamador de **`:1227`** (dentro de `sync_from_ado`, el endpoint `POST /sync`):
```python
        # Plan 292 — este camino lo dispara el operador a mano desde el selector
        # de tickets (frontend/src/components/TicketSelector.tsx:29). Un pedido
        # explícito trae TODO: es la forma que ya tiene el operador de forzar una
        # corrida completa, sin agregar ni un control nuevo a la interfaz.
        result = _sync_via_provider_or_ado(project_name=project_name, forzar_full=True)
```
El llamador de **`:6674`** (dentro de `sync_from_ado_v2`, el endpoint `POST /sync-v2`) **queda exactamente como está**: es el poll automático del tablero, y es justo el que tiene que ir parcial.

**4. `backend/app.py:186`** — el arranque fuerza completo:
```python
                    _r = sync_gitlab_tickets(active, provider=_prov, forzar_full=True)
```
Motivo: el arranque ocurre una vez por proceso, no es polling, y es el momento donde más conviene una foto completa —el proceso pudo haber estado apagado días—. La condición de vencimiento (24 h) lo cubriría igual, pero depender de ella dejaría el arranque a merced del reloj; esto lo hace explícito.

> ⚠️ **`app.py` NO recibe ninguna key `STACKY_*` nueva en este cambio** — sólo un kwarg literal. Por eso `test_app_startup_flag_reads_are_all_declared` (`tests/test_harness_flags_restart_required.py:233`) **no se activa**. Verificar con `grep -n "STACKY_GITLAB_SYNC_INCREMENTAL\|STACKY_GITLAB_SYNC_FULL_CADA_N" backend/app.py` ⇒ debe dar **0 líneas**.

**5. `backend/services/completion_sync.py:136`** — **no se toca**. El default `forzar_full=False` es correcto: es un sync reactivo y frecuente, exactamente el caso del modo parcial.

**Casos borde:**
- **`items` vacío en modo parcial** ⇒ `marca_maxima` devuelve `None` ⇒ la marca **no** avanza y el contador **sí** ⇒ eventualmente se cumple la cuota y se hace completo. Correcto.
- **`vistos_external` vacío en modo completo** ⇒ el `if` de `:312` ya lo cubría; sigue igual.
- **El traído de padres (`:343-389`) no se toca.** En modo parcial es igual de válido: un padre referenciado y ausente hay que traerlo, cambió o no.
- **Los cuatro contadores de clasificación local (`_CONTADORES_LOCAL`) no se tocan.**
- **Fallo de `_wm.escribir_marca`** ⇒ es best-effort y no lanza ⇒ la próxima corrida lee `(None, 0)` ⇒ completo. Degradación correcta.

**Criterio BINARIO:** todos los de §F5, más delta cero en:
```bash
./.venv/Scripts/python.exe -m pytest "tests/test_plan276_gitlab_sync.py" -q          # 21 passed
./.venv/Scripts/python.exe -m pytest "tests/test_plan277_read_path.py" -q            # 15 passed
./.venv/Scripts/python.exe -m pytest "tests/test_plan277_un_solo_motor.py" -q        # 4 passed
./.venv/Scripts/python.exe -m pytest "tests/test_plan208_auto_sync.py" -q            # 10 passed
./.venv/Scripts/python.exe -m pytest "tests/test_plan276_capability_envelope.py" -q  # el baseline de F0
./.venv/Scripts/python.exe -m pytest "tests/test_plan148_ado_sync_breaker.py" -q     # el baseline de F0
grep -c "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED\|STACKY_GITLAB_SYNC_FULL_CADA_N" backend/app.py   # 0
```

⚠️ **Tests ajenos que monkeypatchean `_sync_via_provider_or_ado` por nombre y hay que correr antes de tocarlo:** `tests/test_plan148_ado_sync_breaker.py:126`, `tests/test_plan276_capability_envelope.py:71,91,104,131,150`, `tests/test_plan276_gitlab_sync.py:261,367`. **Los siete lo reemplazan por completo o lo llaman con un solo argumento posicional** ⇒ un kwarg keyword-only con default no los rompe. **Igual se miden antes y después: la predicción se verifica, no se afirma.**

**Flag y default:** las dos de F3.
**Impacto por runtime:** ninguno, verificado en §3.6 y probado en §F6.2.
**Trabajo del operador:** ninguno.

---

### F5 — El gate de correctitud, con las dos mitades

**Objetivo (1 frase):** probar que un sync parcial **no cierra nada**, que el completo **sí** detecta el cierre por ausencia, y que las seis condiciones de §3.2 hacen lo que dicen.

**Archivo:** `backend/tests/test_plan292_sync_incremental.py` (creado en F1, se completa acá).

**Infraestructura del archivo** — reusa `tests/test_plan276_gitlab_sync.py` como molde exacto:
- La fixture `bd` de `:24-95` (base SQLite en `tmp_path`, `session_scope` re-apuntado porque `gitlab_sync.py` lo importó **por valor**, y el assert `tmp_path.name in str(motor.url)`).
- `CTX` (`:98-102`) y el helper `_issue(...)` (`:116-133`), que **ya emite `updated_at`**.
- **`_ProviderFalso` se EXTIENDE**, porque el de `:105-118` **no tiene `get_item`** (§4.5) y no cuenta llamadas:
  ```python
  class _ProviderConCuenta:
      name = "gitlab"
      def __init__(self, tandas):
          self._tandas = list(tandas)   # una lista de items por corrida
          self.queries = []             # las TrackerQuery emitidas, en orden
          self.gets = []                # los iid pedidos uno a uno
      def fetch_open_items(self, query):
          self.queries.append(query)
          return list(self._tandas.pop(0)) if self._tandas else []
      def get_item(self, item_id):
          self.gets.append(item_id)
          raise LookupError("no debería pedirse en estos casos")
  ```
- **La ruta del store se monkeypatchea a `tmp_path` en TODOS los casos** (R8).

**Los casos:**

| # | Nombre | Qué asserta |
|---|---|---|
| 1 | `test_trackerquery_acepta_updated_after_y_su_default_es_none` | (de F1) |
| 2 | `test_query_sin_updated_after_no_emite_el_parametro` | (de F1) |
| 3 | `test_query_con_updated_after_lo_emite_tal_cual` | (de F1) |
| **4** | 🔴 **`test_el_delta_PARCIAL_no_cierra_a_los_ausentes`** | **EL CASO CENTRAL — REESCRITO EN v2.** Corrida 1: 3 issues ⇒ `created == 3`, `queries[0].updated_after is None`, `queries[0].state == "open"`. Corrida 2 **parcial** con **UN SOLO issue de los tres** (el que cambió) ⇒ `queries[1].updated_after is not None`, `queries[1].state == "all"`, **`res["removed"] == 0`** y **las 3 filas siguen `opened`**. ⚠️ **La tanda tiene que ser NO VACÍA**: ver el recuadro de abajo |
| **4b** | **`test_el_delta_vacio_tampoco_cierra_nada`** | El caso 4 de la v1, degradado a **complementario**: corrida 2 con tanda vacía ⇒ `removed == 0`. Se conserva porque cubre la ruta del delta vacío, pero **no vale como gate**: pasa también sin el plan (§0-A) |
| 5 | `test_el_sync_completo_sigue_cerrando_por_ausencia` | Corrida 1: 3 issues. Corrida 2 con `forzar_full=True` y sólo 2 de los 3 ⇒ `res["removed"] == 1` y la fila faltante queda `closed`. **Es la mitad de contraste del caso 4** |
| **6** | 🔴 **`test_un_cerrado_DESCONOCIDO_del_delta_no_crea_fila`** | **NUEVO en v2 — el segundo criterio de correctitud (§3.1-bis, R1b).** Corrida 1: 1 issue abierto. Corrida 2 **parcial** con ese issue **más** un `iid=77` con `"state": "closed"` que **no existe localmente** ⇒ **`res["created"] == 0`**, `res["omitidos_cerrados_desconocidos"] == 1`, y `session.query(Ticket).count() == 1`: la fila 77 **NO se creó**. Sin este caso, el comportamiento medido en §0-C entra en producción |
| **7** | **`test_un_padre_cerrado_SI_se_trae_aunque_este_la_barrera`** | La barrera vive en el bucle del listado, **no** en el traído de padres. Corrida parcial donde un hijo referencia un padre ausente y `get_item` devuelve ese padre **cerrado** ⇒ la fila del padre **SÍ se crea** y `padres_traidos == 1`. Protege la deuda que saldó el Plan 277 F6 |
| 8 | `test_sin_marca_el_primer_sync_es_completo` | Archivo inexistente ⇒ `modo_sync == "completo"`, `motivo_modo == "sin_marca"`, `queries[0].updated_after is None` |
| 9 | `test_marca_corrupta_degrada_a_completo` | Escribir `"{no es json"` en la ruta ⇒ `completo` / `marca_ilegible`, y **la regla de ausencia vuelve a estar activa** (se comprueba cerrando uno) |
| 10 | `test_marca_vencida_degrada_a_completo` | Marca de hace 25 h ⇒ `motivo_modo == "marca_vencida"`. **Y la del futuro también:** marca de dentro de 2 h ⇒ mismo motivo (§F4, punto 1) |
| 11 | `test_la_cuota_fuerza_una_corrida_completa` | Con la cuota en 3 (monkeypatch de `config.config`), las corridas 1..3 son parciales y la **4.ª** es `completo` / `cuota_cumplida`, y el contador vuelve a **0**. **Es la única prueba real de que la flag numérica está cableada** (§4.3-bis) |
| 12 | `test_la_opcion_apagada_deja_el_sync_identico_al_de_hoy` | Con la opción en `False`, **todas** las corridas son `completo` / `opcion_apagada`, `updated_after is None` siempre y la regla de ausencia cierra igual que antes del plan |
| 13 | `test_el_pedido_explicito_gana_sobre_una_marca_fresca` | Marca fresca y válida, pero `forzar_full=True` ⇒ `completo` / `pedido_explicito` |
| 14 | `test_un_issue_cerrado_CONOCIDO_en_el_delta_marca_la_fila_cerrada` | Corrida 1: issue abierto. Corrida 2 **parcial** con ese issue traído con `"state": "closed"` ⇒ la fila queda `closed` **por su propio estado**, con `removed == 0`. Prueba §3.1 **y** que la barrera de §3.1-bis **no** bloquea este caso |
| 15 | `test_un_issue_reabierto_vuelve_a_opened` | Corrida 1 con `closed`, corrida 2 parcial con el mismo issue en `opened` ⇒ la fila vuelve a `opened` |
| 16 | `test_la_marca_usa_la_hora_de_gitlab_no_la_local` | Los issues traen `updated_at = "2026-08-01T10:00:00Z"`; tras el sync, la marca guardada es **`2026-08-01T09:58:00Z`** (el máximo menos los 120 s de solapamiento) y **no** se parece a `utcnow()`. Cubre R3 y R4 |
| 17 | `test_un_delta_vacio_no_mueve_la_marca_pero_si_el_contador` | Tras una corrida parcial con 0 ítems, la marca es **idéntica** a la anterior y el contador subió 1 |
| **18** | **`test_un_completo_posterior_no_hace_retroceder_la_marca`** | **NUEVO en v2 (R11).** Corrida parcial que deja la marca en el 02; corrida `forzar_full=True` cuyos ítems traen `updated_at` del **01** ⇒ la marca guardada sigue siendo la del **02** |
| 19 | `test_el_delta_no_dispara_pedidos_de_padres_uno_a_uno` | En la corrida parcial sin padres ausentes, `prov.gets == []` |
| **20** | **`test_bytes_recibidos_baja_a_cero_en_estado_estable`** | **NUEVO en v2 (K6, [ADICIÓN ARQUITECTO]).** Corrida 1 completa ⇒ `res["bytes_recibidos"] > 0`; corrida 2 parcial con tanda vacía ⇒ `res["bytes_recibidos"] == 0` |
| 21 | `test_k1_en_estado_estable_el_delta_trae_cero_items` | Corrida 1 con 63 issues, corrida 2 parcial con tanda vacía ⇒ `res["fetched"] == 0`. ⚠️ **Este caso prueba el MECANISMO, no el KPI**: el `0` lo decide el doble, no GitLab. Ver §1.1, K1 marcado como PROYECCIÓN |

> 🔴 **Por qué el caso 4 cambió, y es la corrección más importante de la v2.**
> La v1 hacía la corrida 2 con una **tanda vacía**. Se ejecutó contra el código de hoy (§0-A) y el resultado es `removed=0` con las 3 filas en `opened` — **sin ninguna modificación del plan**. Motivo: con `items == []`, `vistos_external` queda vacío y el `if vistos_external:` de `gitlab_sync.py:312` **ya corta**. ⇒ los dos asserts centrales del caso 4 se cumplían **antes** de F4, y su mitad de contraste (*"quitar `modo == "completo" and` del guard"*) **restauraba exactamente ese código**, así que no podía fallar.
> La v1 hasta razonó sobre este hecho —*"hoy la segunda corrida con tanda vacía no entra al bloque porque `vistos_external` queda vacío"*— y sacó la conclusión opuesta: lo usó para **justificar** la tanda vacía en vez de para descartarla.
> **Con una tanda parcial no vacía el daño existe y está medido: 2 de 3 filas cerradas (§0-B).** Ahí el gate discrimina.

**Cómo se comprueba el ROJO de los casos 4..21:** **antes de F4** el archivo falla con `TypeError: sync_gitlab_tickets() got an unexpected keyword argument 'forzar_full'` en los casos que lo usan, y con `AssertionError` en `queries[1].updated_after is not None` (hoy siempre `None`: la línea `:257` está hardcodeada). Se corre el archivo antes de F4 y se pega el output **completo, caso por caso** — no el resumen.

⚠️ **Un rojo por `TypeError` NO alcanza como prueba de que el caso discrimina.** Un `TypeError` en la firma se arregla agregando el kwarg, y el caso pasaría a verde **sin que la lógica de correctitud se haya probado nunca**. Por eso cada uno de los tres invariantes lleva su mitad de contraste **después** de F4, con el producto ya construido y luego parcheado a mano.

**Gate con mitad de contraste — obligatorio, y ahora son CINCO.** Cada invariante lleva **dos** corridas: una que pasa y una que, con el producto parcheado, **debe fallar**. Si la mitad que falla no se puede construir, el gate es vacuo y hay que rehacerlo (§8):

| # | Invariante | Mitad que PASA | Mitad que DEBE FALLAR (parche temporal, se revierte) | Verificado que puede fallar |
|---|---|---|---|---|
| 1 | El parcial no cierra a los ausentes (**caso 4**) | como está | **quitar `modo == "completo" and`** del guard de `:312` | ✅ **sí** — medido en §0-B: con el guard fuera y una tanda parcial, `removed=2`. *(Con la tanda VACÍA de la v1 esta mitad daba `removed=0` y NO fallaba)* |
| 2 | El completo sí cierra (**caso 5**) | como está | dejar el guard como `if False and vistos_external:` | ✅ sí — el caso 5 pasaría a `removed == 0` |
| 3 | El parcial no crea cerrados desconocidos (**caso 6**) | como está | **hacer que `admitir_del_delta` devuelva siempre `True`** | ✅ **sí** — medido en §0-C: `created=1` y la fila `(77,'closed')` aparece |
| 4 | La marca es la de GitLab (**caso 16**) | como está | cambiar `marca_maxima` para devolver `utcnow()` | ✅ sí — la fecha guardada deja de ser `2026-08-01T09:58:00Z` |
| 5 | La marca no retrocede (**caso 18**) | como está | **quitar el `max(...)` de `escribir_marca`** y guardar `marca` a secas | ✅ sí — la marca pasaría a la del 01 |

**Criterio BINARIO:**
```bash
./.venv/Scripts/python.exe -m pytest "tests/test_plan292_sync_incremental.py" -q   # 21 passed
```
más **las cinco** mitades de contraste ejecutadas y su salida pegada (cada una debe mostrar el caso correspondiente en `FAILED`), más `ls "backend/data/gitlab_sync_watermark.json"` ⇒ **no debe existir**.

**Flag y default:** las de F3, ejercitadas en los dos estados.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F6 — Paridad de los tres runtimes, documentación y no-regresión

**Objetivo (1 frase):** probar ejecutando que los tres caminos que disparan el sync se comportan igual, y dejar la decisión escrita en la documentación del sistema.

**Tests PRIMERO** — archivo NUEVO `backend/tests/test_plan292_paridad_runtimes.py`:

| # | Caso | Qué asserta |
|---|---|---|
| 1 | `test_los_tres_disparadores_llaman_al_mismo_sync` | **REESCRITO EN v2.** Censo por **AST**, no por grep: se recorre `backend/**/*.py` (excluyendo `tests/`) y se cuentan los nodos `ast.Call` cuyo `func` resuelve a `sync_gitlab_tickets`. Deben ser **exactamente 3**, en `app.py`, `api/tickets.py` y `services/completion_sync.py`. Ver el recuadro |
| 2 | `test_ningun_runner_conoce_el_sync_de_gitlab` | `gitlab`, `sync_gitlab_tickets` y `completion_sync` tienen **0 hits** en `services/codex_cli_runner.py`, `services/claude_code_cli_runner.py` y `copilot_bridge.py`. **Es el gate de paridad: si un runner empezara a hablar de GitLab, la paridad dejaría de ser gratis y este test lo diría** |
| 3 | `test_el_arranque_fuerza_completo` | **EJECUTANDO**, no leyendo: se parchea `sync_gitlab_tickets` por un espía y se llama `_startup_sync` con un contexto GitLab ⇒ el espía recibió `forzar_full=True` |
| 4 | `test_el_pedido_manual_fuerza_completo` | **EJECUTANDO**: espía sobre `sync_gitlab_tickets`, se llama al camino de `POST /sync` ⇒ `forzar_full=True` |
| 5 | `test_el_poll_automatico_no_fuerza_completo` | **EJECUTANDO**: mismo espía por el camino de `POST /sync-v2` ⇒ `forzar_full` ausente o `False` |
| 6 | `test_la_completacion_no_fuerza_completo` | **EJECUTANDO**: espía, se llama `completion_sync._do_project_sync("RIPLEY", "gitlab")` ⇒ `forzar_full` ausente o `False` |

> 🔴 **El caso 1 de la v1 no podía pasar, y hay que decir por qué.** Decía *"…y **no hay un cuarto** fuera de `backend/tests/`"*. Medido con `grep -rn "sync_gitlab_tickets" backend/ --include=*.py`, fuera de `backend/tests/` el símbolo aparece en **6 archivos / 12 líneas**:
>
> | Archivo:línea | Qué es | ¿Es una llamada? |
> |---|---|---|
> | `api/tickets.py:1209` / `:1210` | import / **llamada** | 1 de 3 |
> | `app.py:183` / `:186` | import / **llamada** | 2 de 3 |
> | `services/completion_sync.py:134` / `:136` | import / **llamada** | 3 de 3 |
> | `services/completion_sync.py:127` | comentario | no |
> | `services/gitlab_sync.py:118` | comentario | no |
> | `services/gitlab_sync.py:235` | la **definición** | no |
> | `services/gitlab_sync.py:410` | `__all__ = ["sync_gitlab_tickets"]` | no |
> | `services/gitlab_hierarchy_backfill.py:181` | comentario | no |
> | `services/provider_capabilities.py:258` | **string** `"services/gitlab_sync.py:sync_gitlab_tickets"` | no |
>
> Un censo por grep da **6 archivos** y falla el día uno; un censo por subcadena sobre el módulo propio se cuenta a sí mismo (la definición y el `__all__`). Por eso el caso 1 cuenta **nodos `ast.Call`**, que es lo único que distingue una llamada de un comentario, de un `__all__` y de una cadena de capacidad.
>
> ⚠️ **Y el AST tiene su propia trampa: cuenta CERO si la llamada va por alias.** Las tres son `from services.gitlab_sync import sync_gitlab_tickets` seguidas de `sync_gitlab_tickets(...)`, o sea `ast.Name`. El test **debe** aceptar también `ast.Attribute` (`gs.sync_gitlab_tickets(...)`) y **debe** asertar que el censo reproduce los **3 archivos esperados por nombre**, no sólo el número — un conteo de 3 que cayera en tres archivos equivocados pasaría igual.

**Por qué los casos 3..6 EJECUTAN y no grepean:** un test estático sobre un defecto de ejecución es uno de los tres moldes de gate muerto. Que la línea `forzar_full=True` esté escrita en `app.py` no prueba que llegue: podría estar en una rama muerta. Los cuatro llaman a la función real con un espía y miran el kwarg **recibido**.

**Cómo se comprueba el ROJO:** antes de F4, los casos 3 y 4 fallan porque el kwarg no existe (`TypeError`), y el caso 2 debe pasar **desde ya** — es un invariante preexistente que este plan **conserva**, y su mitad de contraste es agregar temporalmente una línea `# gitlab` a uno de los tres runners y verificar que el test se ponga rojo.

**Documentación:** `Stacky Agents/docs/sistema/` — un archivo nuevo con: los dos modos, la tabla de las seis condiciones de §3.2, por qué la hora es la del servidor, y por qué el daemon quedó fuera de scope. Más su entrada en el `INDEX.md` de esa carpeta.

**Barrido de no-regresión** (delta cero contra §4, **por archivo**, base fresca), con el número exacto medido el 2026-08-02:

| Archivo | Debe dar |
|---|---|
| `test_plan276_gitlab_sync.py` | 21 passed |
| `test_gitlab_provider.py` | 26 passed |
| `test_gitlab_client.py` | 6 passed |
| `test_tracker_provider_conformance.py` | 13 passed |
| `test_plan277_read_path.py` | 15 passed |
| `test_plan277_un_solo_motor.py` | 4 passed |
| `test_plan208_auto_sync.py` | 10 passed |
| `test_harness_flags.py` | 59 passed |
| `test_harness_flags_requires.py` | 9 passed |
| `test_flag_wiring.py` | 5 passed |
| `test_harness_ratchet_meta.py` | 4 passed |
| `test_plan259_ratchet_script_parity.py` | 12 passed |
| `test_plan276_capability_envelope.py` | 6 passed |
| `test_plan148_ado_sync_breaker.py` | 6 passed |
| 🔴 `test_harness_flags_bounds.py` | **1 failed, 17 passed** |
| 🔴 `test_harness_flags_help.py` | 4 failed, 4 passed |
| 🔴 `test_flags_env_read_meta.py` | 1 failed, 1 passed |
| 🔴 `test_plan218_coupling_ratchet.py` | 3 failed, 7 passed |
| 🔴 `test_plan218_capability_matrix.py` | 2 failed, 8 passed |
| 🔴 `test_plan76_codebase_memory_mcp.py` | 1 failed, 9 passed |
| 🔴 `test_plan74_migrator_wiring.py` | 1 failed, 3 passed |

**`test_plan218_tracker_contract.py` NO se corre**: sale a la red del operador.

**Criterio BINARIO:**
```bash
./.venv/Scripts/python.exe -m pytest "tests/test_plan292_paridad_runtimes.py" -q   # 6 passed
# + los 14 baselines verdes y los 7 rojos de fábrica medibles, cada uno en su número EXACTO de la tabla
bash backend/scripts/run_harness_tests.sh 2>&1 | tail -5    # el ratchet, sin MISSING
```

**Flag y default:** ninguna nueva.
**Impacto por runtime:** es **la fase que lo prueba**. Los tres quedan idénticos porque ninguno toca el sync (§3.6).
**Trabajo del operador:** ninguno.

---

## 8. Glosario

| Término | Qué es acá |
|---|---|
| **Marca de agua** | El momento, según el reloj **del servidor de GitLab**, hasta el que se sabe que se sincronizó un proyecto. Guardada por proyecto en un JSON de `data_dir()`. Nunca sale de `datetime.utcnow()` |
| **Modo COMPLETO** | El sync de hoy, byte a byte: `TrackerQuery(state="open")` y la regla de ausencia activa |
| **Modo PARCIAL / incremental** | `TrackerQuery(state="all", updated_after=marca)` con la regla de ausencia **apagada** |
| **Regla de ausencia** | `gitlab_sync.py:310-326`: lo que no vino en el listado pasa a `ado_state="closed"`. **Sólo es correcta si la query trajo todo lo abierto** |
| **Solapamiento** | Los 120 s que se restan a la marca antes de guardarla. Cubre la carrera del sync y la duda inclusivo/exclusivo |
| **Cuota** | Cada cuántas corridas parciales seguidas se fuerza una completa. `STACKY_GITLAB_SYNC_FULL_CADA_N`, default 10 |
| **Excepción (A)** | Una opción nace apagada si gasta en reposo: enciende un loop, daemon, barrido o llamada a modelo sin que el operador pida nada |
| **Excepción (B)** | Una opción nace apagada si escribe en un sistema real, destruye datos o le saca una decisión al operador |
| **Delta cero** | Criterio sobre una suite roja de fábrica: no se exige verde, se exige **el mismo conteo de antes** |
| **Mitad de contraste** | Toda afirmación de un gate se corre dos veces: una que pasa, y una con el producto parcheado que **debe fallar**. Si la segunda no se puede construir, el gate es vacuo |

---

## 9. Orden de implementación

1. **F0** — **verificar** los baselines de §4 (ya están todos medidos, ninguno queda abierto) y comprobar la brecha 831/767 **cargando el array del `.ps1`**, no sólo grepeando. Commit: sólo este documento.
2. **F1** — el campo de `TrackerQuery` y su traducción. Commit: `tracker_provider.py`, `gitlab_provider.py`, `test_plan292_sync_incremental.py`, los **dos** ratchets.
3. **F2** — el store **con la marca monótona y la barrera de admisión** (§3.1-bis). Commit: `gitlab_sync_watermark.py`, `test_plan292_watermark_store.py`, los **dos** ratchets. **Correr la mitad de contraste de la marca monótona antes de cerrar.**
4. **F3 + F4 juntos** — las dos opciones **y** su consumidor. Commit: `config.py`, `harness_flags.py`, `harness_flags_help.py`, `test_harness_flags.py`, `test_harness_flags_bounds.py`, `gitlab_sync.py`, `gitlab_sync_watermark.py`, `api/tickets.py`, `app.py`, `test_plan292_flags.py`, los **dos** ratchets.
5. **F5** — completar el gate y correr **las cinco** mitades de contraste, pegando la salida de cada una. Commit: `test_plan292_sync_incremental.py`.
6. **F6** — paridad (censo por **AST**), documentación y barrido. Commit: `test_plan292_paridad_runtimes.py`, `docs/sistema/`, los **dos** ratchets.

⚠️ **En cada fase que toque los ratchets:** las entradas van **al final del array** (no en el bloque del Plan 291), y en el `.ps1` **con la coma que la cola exige** — incluida la coma que hay que agregarle a la que hoy es última entrada (`.ps1:1001`). Ver §4.2.

**Antes de cada commit:** `git status --short`, y pathspec acotado a las rutas de la fase. **`git commit -F <archivo> -- "<rutas>"`**, el `-F` **antes** del `--`. Un archivo sin seguimiento necesita `git add -- "<ruta>"` primero. Cero push.

---

## 10. Definición de Terminado

| # | Condición | Cómo se verifica |
|---|---|---|
| 1 | `tests/test_plan292_watermark_store.py` = **16 passed** | comando de §F2 |
| 2 | `tests/test_plan292_sync_incremental.py` = **21 passed** | comando de §F5 |
| 3 | `tests/test_plan292_flags.py` = **12 passed** | comando de §F3 |
| 4 | `tests/test_plan292_paridad_runtimes.py` = **6 passed** | comando de §F6 |
| 5 | **Las CINCO mitades de contraste de §F5 se ejecutaron y fallaron**, con la salida de cada una pegada mostrando el caso en `FAILED`, y el parche revertido | §F5 |
| 5b | **La mitad de contraste de §F2 (marca monótona) se ejecutó y falló** | §F2 |
| **6** | 🔴 **K2 = 0**: un sync parcial con delta **PARCIAL NO VACÍO** no marca ninguna fila como cerrada | §F5 **caso 4** — *(la v1 lo verificaba con un delta vacío, donde el `if` preexistente ya daba 0; ver §0-A)* |
| **6b** | 🔴 **K2b = 0**: un sync parcial no **crea** ninguna fila a partir de un ítem `closed` desconocido | §F5 **caso 6** |
| 7 | El delta en estado estable trae **0** ítems (**mecanismo**, no KPI) y `bytes_recibidos == 0` | §F5 casos 20 y 21 |
| 7b | **K1 queda declarado como PROYECCIÓN** en §1.1 y **no** se usa como criterio de aceptación | §1.1 |
| 8 | Delta cero en los **14** baselines verdes y en los **7** rojos de fábrica medibles, cada uno en su número exacto de la tabla de §F6 | §F6 |
| 9 | `len(FLAG_REGISTRY) == 495` (493 medido + 2) | snippet de §F3 |
| 10 | `tests/test_harness_flags_requires.py` = **9 passed**, intacto (no se declaró `requires=`) | §F3 |
| **10b** | **`_FROZEN_BOUNDS["STACKY_GITLAB_SYNC_FULL_CADA_N"] == (1, 1000)`**, asertado desde el archivo **verde** de este plan | §F3 caso 11 — *(el archivo ajeno está rojo de fábrica y no discrimina: §4.1-bis)* |
| 11 | Los 4 archivos de test están en el `.sh` **y** en el `.ps1`, **insertados al final del array**, con la coma que su región exige; la brecha sigue en **64** | `test_plan259_ratchet_script_parity.py` = 12 passed + el conteo cargando el array (§F0) |
| 12 | **`backend/data/gitlab_sync_watermark.json` NO existe** tras correr toda la suite | `ls` |
| 13 | **La base del operador no cambió**: `md5` de `backend/data/stacky_agents.db` idéntico al de antes | `md5sum` antes y después |
| 14 | `grep` de las 2 keys nuevas en `app.py` = **0 líneas** | §F4 |
| 15 | Documento de `docs/sistema/` escrito y en su `INDEX.md` (la carpeta ya tiene 18 archivos e `INDEX.md`) | §F6 |
| 16 | **Cero requests reales contra el GitLab del operador** en toda la implementación | todos los tests usan dobles |
| **17** | **`res["omitidos_cerrados_desconocidos"]` existe en el dict de retorno y se loguea** — si el número crece sin parar, el operador tiene la señal de que el proyecto mueve mucho cerrado | §F4 punto 2-bis |

**Pendiente del operador tras la implementación: ninguno.** Las dos opciones nacen con el valor correcto y no hay nada que encender, configurar ni migrar. Si el operador quisiera forzar una sincronización completa, ya tiene el botón que existe hoy en el selector de tickets.

**Recomendación independiente, fuera de este plan (§1.2):** subir `DEFAULT_INTERVAL_MS` (`frontend/src/hooks/useTicketSync.ts:40`) de 45 s a 180 s baja el **75 %** de los ~16 MB/h con **una línea** y cero riesgo de correctitud. No entra acá porque este plan no toca frontend y `endpoints.ts` está sucio por la sesión paralela — pero es más barato que todo esto junto y el operador merece saberlo.

---

## 11. CHANGELOG v1 → v2

**Veredicto de la v1: RECHAZADO — 4 bloqueantes, 6 importantes, 4 menores.** Anclajes verificados abriendo el archivo: **101 de 104 correctos**. El defecto no estaba en dónde miraba.

**Cómo se criticó:** ejecutando. Se corrió `sync_gitlab_tickets` contra el código de hoy con un proveedor doble (§0), se corrieron los **17** archivos de baseline con base SQLite fresca por archivo, y se midió la base viva por una copia `VACUUM INTO` en modo `ro`. La base del operador no se tocó y no salió un solo request a GitLab.

### Bloqueantes resueltos

| # | Defecto de la v1 | Evidencia | Resuelto en |
|---|---|---|---|
| **C1** | **El "caso central" (§F5 caso 4) era vacuo: su mitad de contraste no podía fallar.** Usaba un delta **vacío**, donde el `if vistos_external:` de `gitlab_sync.py:312` ya corta. Quitar el guard del modo —la mitad que "debía fallar"— restaura exactamente ese código | **§0-A ejecutado:** con el código de hoy, `removed=0` y las 3 filas en `opened` | §F5 caso 4 reescrito con delta **parcial no vacío**; el viejo baja a caso 4b como complementario; tabla de contraste ampliada a **5** filas con la columna *"verificado que puede fallar"* |
| **C2** | **El escenario real de R1 no tenía ningún caso.** El único con delta parcial era el caso 5, y corría con `forzar_full=True` — o sea, en el modo donde cerrar es **correcto** | **§0-B ejecutado:** delta de 1 sobre 3 filas ⇒ **`removed=2`** | mismo caso 4 |
| **C3** | **`state="all"` INSERTA filas cerradas que hoy no existen.** `_upsert_ticket_gitlab` crea sin mirar el estado; nadie borra nunca; `list_tickets` (`api/tickets.py:1104`) no filtra por `ado_state`, ordena por `last_synced_at DESC` y topea en **500** ⇒ los fantasmas van arriba del tablero y desalojan abiertos reales. La v1 declaraba el invariante *"la base sólo tiene los abiertos"* en §2.4 y lo rompía en F4 sin decirlo | **§0-C ejecutado:** `created=1`, fila `(77,'closed')` creada de la nada | **§2.7** (el gap), **§3.1-bis** (la barrera `admitir_del_delta`), **§3.1-ter** (por qué es función pura), F2 casos 14-16, F4 punto 2-bis, F5 casos 6 y 7, R1b |
| **C4** | **`test_harness_flags_bounds.py` es un OCTAVO rojo de fábrica y es el único guardián de la flag numérica.** La v1 lo listaba como *"(medir en F0)"* y usaba *"delta cero"* como criterio — pero el archivo da 1F/17P **haga lo que haga** el implementador con `_FROZEN_BOUNDS` | **medido:** `1 failed, 17 passed`; `test_bounds_map_is_frozen` falla con **6 extras** que le debe un plan anterior | **§4.1** SIETE→**OCHO**, **§4.1-bis** con la tabla de los tres escenarios indistinguibles, **§4.3** guardián **#9**, **§F3 casos 11 y 12** que importan `_FROZEN_BOUNDS` al archivo verde |

### Importantes resueltos

| # | Defecto | Resuelto en |
|---|---|---|
| **C5** | **La premisa que justificaba fusionar F3+F4 era falsa.** `_production_corpus()` **incluye `backend/config.py`** por decisión documentada (`test_flag_wiring.py:29-38`), así que el guardián pasa con F3 sola. Baseline medido: **5 passed**, no rojo. Segundo orden: ese guardián **no puede** probar que F4 exista | **§4.3-bis** entera + §F3. La fusión se mantiene, con el motivo correcto; la opción (b) queda **descartada con evidencia** (`test_reserved_flags_are_actually_dead:73`) |
| **C6** | **La marca podía RETROCEDER.** En COMPLETO `items` son sólo abiertos: si el cambio más reciente fue sobre un cerrado, el `max` es más viejo que la marca previa y la v1 lo escribía igual. Efecto: el ahorro muere después de cada corrida de cuota, y la ventana enorme arrastra cerrados (compone con C3) | **§3.3** marca monótona, `escribir_marca` con `max(...)`, **R11**, F2 casos 12-13 con su mitad de contraste, F5 caso 18 |
| **C7** | **§F6 caso 1 no podía pasar.** Decía *"no hay un cuarto"*; medido, fuera de `tests/` el símbolo está en **6 archivos / 12 líneas** (3 llamadas + 3 comentarios + la `def` + `__all__` + una cadena en `provider_capabilities.py:258`) | **§F6** censo por **`ast.Call`** con la tabla de los 12 hits, más el aviso de que el AST **cuenta cero si la llamada va por alias** y la exigencia de reproducir los 3 archivos **por nombre** |
| **C8** | **K1 y su criterio eran tautológicos.** `fetched = len(items)` y el doble recibe `[]`: el test decide la respuesta. La DoD lo usaba como *"K1 medido"* | **§1.1** K1 marcado **PROYECCIÓN** (como ya estaba K4), nuevo **K6**, DoD 7/7b, y la **[ADICIÓN ARQUITECTO]** `bytes_recibidos` de §F4.6 |
| **C9** | **"61 de 63" no era una medición** y erraba en las dos direcciones: 0 con delta vacío, **63** en el peor caso. El mal encuadre es la causa directa de C1 | **§2.6** con la tabla del daño por tamaño de delta, **R1** reescrito |
| **C10** | **El KPI estaba en la unidad equivocada** (issues/requests en vez de bytes) y **nunca se comparaba contra la alternativa de una línea** | **§1.1** con la carga real medida (**111.685 B** de descripciones, ~**205 KB**/sync, ~**16 MB/h**) y **§1.2** con la tabla de alternativas |

### Menores resueltos

| # | Defecto | Resuelto en |
|---|---|---|
| **C11** | El anclaje del ratchet caía en el bloque temático del Plan 177 (`.sh:519`, `.ps1:466`), no al final; y las dos regiones **no son paralelas** (`.sh:521` tiene una entrada que el `.ps1` no tiene). **Trampa medida:** el `.ps1` tiene **557** entradas con coma y **210** sin — la cola **sí** lleva coma, y una coma faltante rompe el array **en silencio** sin que ningún test lo diga | **§4.2** con las tres precisiones, anclaje movido al final del array, y **verificación extra en §F0 cargando el array** |
| **C12** | `motivo_modo` decía `marca_ilegible` cuando el archivo existe pero no tiene entrada para ese proyecto | queda documentado; ambos caminos van a COMPLETO, que es lo correcto |
| **C13** | `_ProviderFalso` va de `:105` a **`:114`**, no a `:118` (`:117` ya es `def _issue`) | §4.5 |
| **C14** | `_rebuild_tickets_table_if_needed` está definida en **`db.py:390`**; `:323` es su **llamada** y el aviso está en `:284-287` | §4.5 |

### Lo que la v1 tenía bien y se conserva sin tocar

Verificado abriendo el archivo o ejecutando: **todos los anclajes de flags** (`harness_flags.py:587/607/614/615/621/7352/7353/7383-7385/7425`, `config.py:60/2732`, `harness_flags_help.py:25/2505`, `test_harness_flags.py:30/42/467/1121/1124/1185/1196`, `test_harness_flags_bounds.py:227/230`, `test_harness_flags_requires.py:351-352/397`, `test_flag_wiring.py:17-27/57`, los dos ratchets `:46/76/85/101` y `:43/66/79`) · **las seis correcciones de anclaje que la v1 le hizo al enunciado** (`gitlab_client.py:32`+`:355`, `gitlab_provider.py:122-136`, `gitlab_sync.py:310-326`, `app.py:183`+`:186`, `api/tickets.py:1202` comentario +`:1209`/`:1210`, `completion_sync.py:117` es `build_ado_client` y la llamada está en `:136`) — **las seis eran correctas** · las **cinco mediciones de la base** (232 filas, 63 GitLab todas RIPLEY y `opened`, Epic 2 / Issue 53 / Task 8, 8 con padre → 2 padres, **0** padres ausentes) · los **ocho baselines** que declaraba con número (21/26/6/13/15/4/10/59) · `FLAG_REGISTRY` = **493** · la brecha de ratchets **831 − 767 = 64 = `_PS1_LAG_MAX`** · `updated_after` = **0 hits** en todo el repo · los **tres runtimes con 0 hits** de `gitlab`/`sync_gitlab_tickets`/`completion_sync` · `app.py:635-636` textual *"NO agregar threads nuevos"* y `MaintenanceTask` en `maintenance.py:17-22` · el poll de **45 s** (`useTicketSync.ts:40`, alias en `TicketBoard.tsx:12`, consumido en `:1030`) contra el rate-limit de 15 s (`api/tickets.py:6601`) · `_ProviderFalso` **sin `get_item`** · `per_page=100` (`gitlab_client.py:363`) ⇒ **1 request** real hoy · `TrackerQuery` en `tracker_provider.py:21-28` con `Optional` ya importado en `:18` · `docs/sistema/INDEX.md` existe.

**Las dos decisiones de alcance de la v1 se confirman:** no declarar `requires=` (verificado: `test_requires_map_is_frozen` filtra con `if s.requires`, así que el mapa congelado no se toca) y dejar el daemon **fuera de scope** (verificado: el disparador periódico ya existe en el navegador, y `app.py:635-636` prohíbe por escrito el patrón que el enunciado pedía).

### Sello

```
Juez v2: subagente independiente, misma corrida, contexto limpio
```
