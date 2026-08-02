# 15 — Degradación declarada (`metadata["capability_degraded"]`)

← [INDEX](INDEX.md) · hermanos: [03-modelo-datos](03-modelo-datos.md) · [06-servicios-daemons](06-servicios-daemons.md) · [09-integraciones](09-integraciones.md)

Plan 290. Cuando Stacky corre sobre un tracker que **no** es Azure DevOps y decide **a propósito** no
ejecutar una capacidad, devuelve un valor neutro. Hasta el Plan 290 esa decisión no dejaba rastro: el
operador leía "preflight OK" o "score 1.0" sin forma de saber que no se validó ni se revisó nada.

> **Una degradación NO es un error.** `Microsoft.VSTS.Common.AcceptanceCriteria` no existe en GitLab,
> WIQL no existe en GitLab, `System.Rev` no existe en GitLab. Devolver el valor neutro es la conducta
> **correcta** y se conserva byte a byte. Lo único que el Plan 290 agrega es una **declaración antes del
> `return`**. Ningún `return` cambió de valor, de tipo ni de posición.

## Forma canónica de una entrada

Contrato **congelado**: cinco claves y ninguna más. El consumidor de la interfaz depende de ellas.
[V: services/capability_degradation.py:79 `construir_entrada`]

```json
{
  "capability": "tracker.comments.list",
  "reason": "tracker no-ADO: sin cross-check de comentarios",
  "provider": "gitlab",
  "site": "business_preflight._evaluate_functional",
  "at": "2026-08-02T14:05:00+00:00"
}
```

`metadata["capability_degraded"]` es una **lista** de estas entradas.

- `site` es un **símbolo**, nunca `archivo:línea`: las líneas caducan y mandarían a leer el lugar equivocado.
- `capability` es una key de `CAPABILITY_MATRIX` **o** una clave lógica propia. `tracker.comments.list` **sí**
  está en `CAPABILITY_KEYS`; `tracker.acceptance_criteria` **no**, y es deliberado (ver "Fuera de alcance").
- La **ausencia** de la clave es el estado válido de toda ejecución histórica y de toda corrida que no degradó.

## El único escritor

`services/capability_degradation.py`. Mismo idioma que `context_enrichment.persistir_stats_de_contexto`.
[V: services/capability_degradation.py:29 `CLAVE_METADATA`, :98 `declarar`]

| Invariante | Cómo se sostiene |
|---|---|
| **Nunca levanta** | `try/except` total, y `log = log or _noop_log` como **primera** línea. Sin eso, con el default `log=None` el propio `except` llamaría `None("warn", ...)` y lanzaría `TypeError` **desde el manejador**. [V: tests/test_plan290_registro_degradacion.py::test_declarar_sin_log_y_con_sesion_rota_no_levanta] |
| **Idempotente** | Dedup por `(capability, site)`. Un backlog de 200 tickets anota una vez. |
| **No pisa nada** | Reasignación **completa** de `metadata_dict`; mutar el dict del getter no marca la fila sucia en SQLAlchemy y el cambio se pierde en silencio. |
| **Sin destino, no-op** | `execution_id=None` devuelve `False` sin tocar la base. Es el caso de `api/agents.py:542`, que evalúa antes de que exista la fila. |

## Los dos sitios instrumentados

| Sitio | Símbolo | Capacidad | Qué devolvía en silencio |
|---|---|---|---|
| 5 | `business_preflight._evaluate_functional` | `tracker.comments.list` | `ok=True, mode=None` — el operador lee **"preflight OK"** y no se validó nada. [V: services/business_preflight.py:112] |
| 6 | `self_review.review_artifact` | `tracker.acceptance_criteria` | `score=1.0` — o sea **"perfecto"** — sobre un artefacto que nadie revisó. [V: services/self_review.py:118] |

### La cadena del `execution_id` (los 3 runtimes)

El guard del sitio 5 vive en `_evaluate_functional`, que recibía cinco escalares y ningún `execution_id`.
La cadena se construyó entera; **no** hay atajo con `execution_id=None`, que dejaría el mecanismo
construido, verde y muerto.

```
agent_runner.py:817  ─┐
claude_..._runner:677 ├─► enrich_blocks ─► _inject_run_directive ─► business_preflight.evaluate
codex_..._runner:334 ─┘   [V: ce.py:60]     [V: ce.py:1263]          [V: ce.py:1295]
                                                    │
                                                    ▼
                                        _PREDICATES[agent_type] ─► _evaluate_functional ─► declarar()
```

Todos los eslabones son keyword-only con default `None`: **backward-compatible** en cada uno, y los 11
call sites de `enrich_blocks` en `tests/` quedaron idénticos.

El sitio 6 no necesitó plomería: `review_artifact(*, execution_id, artifact_text)` ya recibía el dato.
[V: services/self_review.py:76] Es el **único** de los ocho sitios donde el destino estaba en el scope
inmediato. Los 3 runtimes llegan ahí por `apply_to_execution`, así que se instrumenta el punto único y
no los tres call sites.

> **Gate de paridad:** `tests/test_plan290_preflight_no_regresion.py::test_los_tres_runtimes_pasan_el_execution_id`
> parsea por AST los 3 runtimes y exige el kwarg en las 3 llamadas **y** que el parser haya visto
> exactamente 3. El Plan 289 cableó 2 de 3 y el tercero tiró el dato en silencio; acá está congelado.

## Cómo llega a la interfaz

No hubo que construir nada en el medio: `models.py:345` serializa `"metadata": self.metadata_dict`
**entero, sin whitelist**, y el drawer ya lee `metadata` completo. [V: models.py:345]

- Modelo puro: `frontend/src/services/capabilityDegradedModel.ts` (lectura defensiva, etiquetas legibles,
  agrupación por proveedor). Lógica en `.ts` porque **RTL/jsdom no están instalados**: un `.test.tsx` con
  RTL reporta *"no tests"* y sale con exit 0.
- Componente: `frontend/src/components/AvisoDegradacionPanel.tsx`. Sin degradaciones devuelve `null`.
- Montado en `ExecutionDetailDrawer.tsx`, junto a los otros paneles alimentados por `metadata`.

## Los seis sitios que NO declaran, y por qué

**La deuda es ejecutable, no prosa.** Vive en `SITIOS_SIN_DECLARAR`
[V: services/capability_degradation.py:40] y la vigila `tests/test_plan290_sitios_clasificados.py`:
todo sitio del censo `Plan 281 F7 sitio` está instrumentado **o** está ahí con su motivo. Agregar un
guard nuevo sin clasificarlo pone el arnés en rojo; sacar uno de ahí obliga a instrumentarlo.

| Archivo | Motivo de la exclusión |
|---|---|
| `api/agents.py` (sitio 1) | Sin `execution_id` en el scope ni en su llamador (`:1687`). Requeriría plomería nueva por varias capas. |
| `api/tickets.py` (sitios 2 y 3) | `:5111` es un closure sin `execution_id` y su propio comentario lo declara *guard cosmético*. `:7762` degrada un sellado de aprendizaje bidireccional (Plan 60 F1), no una capacidad que el operador espere. Bajo daño los dos. |
| `services/acceptance_criteria.py` (sitio 4) | Gemelo funcional de `self_review`, pero **ninguno** de sus llamadores tiene `execution_id`. El sitio 6 ya cubre el mismo hecho de negocio desde donde el dato existe; instrumentar los dos duplicaría la entrada. |
| `services/similar_tickets.py` (sitio 7) | Devuelve `[]`, indistinguible de "no hubo coincidencias", que es un resultado legítimo y frecuente: sería ruido de alta frecuencia y bajo valor. |
| `services/ticket_assigner.py` (sitio 8) | Devuelve `None` y ya loguea en `debug`; el ticket sin asignar se ve en el propio tracker. |

## Kill-switch y flags

**Cero flags nuevas.** Los ocho guards están, sin excepción, dentro de `... and ruteo_estricto_por_tracker()`,
y la declaración va **dentro de ese mismo `if`**. Apagar `STACKY_TRACKER_ROUTING_STRICT_ENABLED`
(`config.py`, default **ON**; se lee en `services/project_context.py:97` con fail-open `True`) apaga el guard
**y** su declaración de un solo movimiento, y el rollback es byte-idéntico al estado previo al Plan 281 F7.
Una flag nueva sería un segundo interruptor para la misma luz.

## Fuera de alcance (decidido, no olvidado)

- **`tracker.acceptance_criteria` NO se agrega a `CAPABILITY_MATRIX`.** Agregar una key mueve
  `len(CAPABILITY_KEYS)` de 71 a 72, y `render_markdown_matrix()` genera el documento de paridad a partir
  de esa lista, que `test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado` exige idéntico
  al `.md` versionado. Habría que regenerar el documento de paridad dentro de un plan que no es sobre
  paridad, y declarar `evidence` para la key nueva en los dos proveedores.
- **No se muestra `metadata["ado_context"]`** (el stat del Plan 289) en la interfaz, pese a tener cero
  consumidores en `frontend/src/`. Es alcance del 289.

## KPI K1 y cómo medirlo

```
K1 = (ejecuciones con capability_degraded no vacío)
   / (ejecuciones de proyectos NO-ADO, con ado_context presente, posteriores al despliegue)
```

Meta **≥ 95 %**, no 100 %: una corrida que muere entre el enriquecimiento y el commit de la fila es un
hueco real y honesto. El `ado_context` del Plan 289 es la prueba de que esa corrida pasó por
`enrich_blocks`, que es el camino que se instrumentó; sin ese filtro el denominador incluye corridas que
nunca podían declarar y el KPI baja por construcción.

```
python scripts/medir_degradacion_declarada.py [--desde 2026-08-02]
```

> ⚠️ **El script abre la base en modo `ro` y saca la foto con `VACUUM INTO`.** El motor corre en **WAL**
> [V: db.py:42-49], así que las escrituras recientes viven en el sidecar `-wal` y **no** en el `.db`: copiar
> sólo el `.db` da una foto inconsistente cuyo arranque falla con
> `IntegrityError: UNIQUE constraint failed: tickets.stacky_project_name, tickets.tracker_type, tickets.external_id`.
> Una métrica sacada de ahí no es "aproximada": es **falsa**. Nunca un `cp` pelado, nunca apuntar
> `DATABASE_URL` a la base viva.

Medido el 2026-08-02, recién desplegado F2: **223 ejecuciones leídas, 0 candidatas** ⇒ K1 **no es 0 %, es
NO MEDIBLE todavía**. El script lo dice explícitamente en vez de reportar un falso 0 %.
