# Playground — sandbox del loop de automejora

Esta carpeta es el **foco por defecto** del modo AI-driven (AOTL). El loop empieza acotado acá
para que sus primeras vueltas sean seguras y baratas: puede crear/editar archivos en
`playground/` pero **no** la maquinaria del propio loop ni los datos de sesión
(ver el guardarraíl en [`../scripts/aotl_state.py`](../scripts/aotl_state.py)).

Cuando confíes en el loop, ampliá `observe.focus` en el adapter activo
([`../adapters/claude/adapter.yaml`](../adapters/claude/adapter.yaml)) a más carpetas de `kaizen/`.

- [`JOURNAL.md`](JOURNAL.md) — bitácora donde el driver `mock` anota cada latido (demo reproducible).
