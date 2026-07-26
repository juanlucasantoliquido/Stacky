# Plan 176 — Smoke manual (F9 paso 4)

Checklist HITL. **No bloquea el merge** y **no está automatizado**: el repo no
tiene RTL/jsdom ni Playwright para el frontend (ver
`gotcha-rtl-jsdom-structural-gap`), así que nada de lo visual de este plan se
renderizó nunca en una corrida de tests. Todo lo de acá es riesgo abierto hasta
que alguien lo haga a mano.

**Estado: PENDIENTE.** Nadie lo corrió todavía. Cuando lo corras, poné el
resultado y la fecha en cada línea.

## Preparación (sin setup manual)

El Plan 183 dejó un sandbox demo en `main`: un click en el panel de demo siembra
el par sqlite `test-*` con drift RS-like. No hace falta ninguna BD real.

Flags necesarias (las 4 están **ON** por default):

| Flag | Qué habilita |
|---|---|
| `STACKY_DB_COMPARE_TRIAGE_ENABLED` | curación por ítem + cierre |
| `STACKY_DB_COMPARE_GATES_ENABLED` | precondiciones read-only |
| `STACKY_DB_COMPARE_TABLE_PREFS_ENABLED` | tabla de parámetro + clave natural |
| `STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED` | multi-filtro, export, line diff, histórico |

## Con las 4 flags ON

- [ ] **(i) Triage → scripts.** Correr un compare sobre el par sembrado. Excluir
      1 ítem **con nota**. Regenerar scripts. Verificar que el bundle **no**
      contiene ese ítem y que `TRIAGE_EXCLUSIONS.md` **sí** lo lista con la nota.
- [ ] **(ii) Precondiciones.** Sobre un diff con un `NOT NULL` endurecido, sembrar
      NULLs en destino y apretar "Verificar ahora": la precondición tiene que
      pintar **fail**. Sin NULLs, **pass**. (Si pinta igual en los dos casos, el
      gate no está midiendo nada.)
- [ ] **(iii) Tablas de parámetro y clave natural.** Marcar una tabla con la
      estrella, recargar candidatas y verla **preseleccionada**. Definir una clave
      natural en una tabla **sin PK** y comprobar que pasa a comparable y que el
      diff de datos devuelve filas.
- [ ] **(iv) Cierre.** Ejecutar (a mano) parte de los scripts, apretar "Verificar
      migración" y comprobar que el reporte muestra `ok` en lo que se aplicó y
      **`violado`** en lo que no. Prueba clave: tocar a propósito algo **excluido**
      y verificar que el panel lo marca como violado — si no lo marca, el cierre
      no sirve para nada.
- [ ] **(v) UX v2 del diff.** Export CSV y JSON descargan **exactamente** lo
      filtrado (filtrar por severidad primero y contar las filas del archivo
      contra las de la pantalla). El diff por líneas marca las líneas cambiadas en
      una vista. El modo **Histórico** compara 2 snapshots viejos y **no** toma
      snapshots nuevos.

## Con las 4 flags OFF

- [ ] La página se ve **idéntica** a `main`: sin celdas de triage, sin panel de
      precondiciones, sin panel de cierre, sin estrellas en el picker, sin botones
      CSV/JSON, sin modo Histórico, y el select de tipo vuelve a ser de un tipo.
- [ ] Los endpoints nuevos responden **403** (triage, gates, table-prefs).

## Lo que sí quedó verificado por tests

No repitas a mano lo que ya corre en CI:

- 12 archivos `test_plan176_*.py`, 153 tests, corridos por archivo con el venv.
- 7 targets de vitest (triageLogic, gatesLogic, tablePrefsLogic, closureLogic,
  lineDiff, diffExport, filterLogic) + `tsc --noEmit` en 0.
- Que el modo histórico **no toma snapshots nuevos** está probado con un
  `take_snapshot` que revienta si alguien lo llama.
- Que la clave natural **llega** al diff de datos está probado de punta a punta
  (preferencia → candidata → filas), no solo en el almacén.
