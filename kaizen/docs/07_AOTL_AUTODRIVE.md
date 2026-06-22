# 07 — Modo AI-driven (AOTL): loop de automejora + dashboard

> Cómo Kaizen pasa de **HITL** (vos manejás) a **AOTL** (la IA maneja, vos supervisás por
> excepción) **sin cambiar la arquitectura**: mismos contratos, mismo gate, mismas invariantes.
> El acoplamiento a la IA vive sólo en `scripts/engine.py` y en el adapter activo.

## Qué hace, en una frase
Un loop que, vuelta tras vuelta, **observa** el estado de `kaizen/`, **propone** una mejora con
un modelo, la **aplica** de forma reversible, la **mide** contra una métrica objetiva, la
**evalúa**, y un **gate determinista decide**. Solo lo que el gate **acepta** se conserva (y se
commitea); todo lo demás se **revierte**. Lo ves todo en vivo en un **dashboard HTML**.

## El reparto de responsabilidades (clave de seguridad)
| Pieza | Quién | Toca el filesystem |
|---|---|---|
| Proponer / Evaluar | **modelo IA** (`engine.py`, driver `claude`) | ❌ sólo emite JSON (modo `claude -p`, read-only) |
| Aplicar / Revertir | **Python determinista** (`apply.py`) | ✅ con pre-imagen de respaldo (rollback sin git) |
| Medir | la métrica del adapter (`selfcheck`) | sólo lee |
| Decidir | **gate determinista** (`run_session.py`) | escribe decisión/forense |
| Orquestar | `autoloop.py` | coordina y commitea lo aceptado (scopeado a `kaizen/`) |

El modelo **nunca** ejecuta cambios: describe un `change_set` (ver
[`../contracts/change_set.schema.json`](../contracts/change_set.schema.json)) y Python lo aplica.

## El ciclo (mapeado a PDCA)
```
OBSERVAR → PROPONER → APLICAR → MEDIR → EVALUAR → DECIDIR → RESOLVER
└─ PLAN ──────────┘   └─ DO ─┘  └──── CHECK ────┘ └───── ACT ─────┘
```
- **accept** → se conserva → `impl_status: implemented` (+ commit scopeado).
- **reject** → se revierte → `impl_status: rejected`.
- **iterate** (no escalado) → se revierte, engendra sesión hija → `impl_status: iterating`.
- **iterate + escalado** (baja confianza / irreversible) → se revierte y **el loop se detiene**:
  decide un humano (`impl_status: escalated`). Es la regla 6 de [`06_RUNBOOK_AGENTE.md`](06_RUNBOOK_AGENTE.md).

Cuando el gate dispara un **bloqueante** (B1..B4), el `decision.json` incluye el campo
`blocking_details` con la descripción humana de cada bloqueante (no solo el código B1/B2…).

## Guardarraíles (no negociables)
1. **Rutas acotadas:** el auto-apply sólo toca archivos dentro de `kaizen/` y **nunca** los datos
   de sesión ni la maquinaria del propio loop (`PROTECTED_FILES` en `scripts/aotl_state.py`).
   Archivos protegidos: `kaizen.py`, `config/kaizen.config.yaml`, y los scripts del arnés
   (`aotl_state.py`, `apply.py`, `autoloop.py`, `engine.py`, `dashboard.py`, `run_session.py`,
   `validate.py`, `forensic.py`, `new_session.py`, `selfcheck.py`, `spawn_child.py`,
   `promote_decision.py`). Scripts de visualización y tests **sí** pueden ser editados por el loop.
   Empieza acotado al sandbox `playground/` vía `observe.focus` del adapter.
2. **Reversibilidad siempre:** cada aplicación guarda pre-imagen; el rollback no depende de git.
3. **Commit scopeado:** al aceptar, se commitea **sólo** las rutas tocadas (jamás `git add -A`),
   así el loop nunca arrastra cambios ajenos del repo.
4. **Frenos:** tope de iteraciones (`--max-iterations`), flag de parada cooperativa (botón STOP
   del dashboard), y **escalado a humano** que detiene el loop.
5. **Sin falsos verdes:** la evaluación se basa en una **medición real** (la métrica corre de verdad).

## Cómo se usa
### 1. Activar el modo AI-driven
```sh
cp config/kaizen.config.example.yaml config/kaizen.config.yaml   # una vez
# en kaizen.config.yaml:  mode: aotl   y   adapter: claude
```
El adapter [`../adapters/claude/adapter.yaml`](../adapters/claude/adapter.yaml) fija modelo
(`claude-sonnet-4-6` por defecto; subí a Opus si querés), timeout y el **foco** editable.

### 2. Lanzar el loop
```sh
python kaizen.py loop --engine claude --forever      # automejora constante
python kaizen.py loop --engine claude --max-iterations 5
python kaizen.py loop --engine mock  --max-iterations 3   # demo determinista, sin red
```
Flags: `--interval S` (espera entre vueltas), `--objective "..."` (semilla), `--no-commit`,
`--adapter NAME`.

### 3. Ver el dashboard
```sh
python kaizen.py dashboard            # genera dashboard/index.html (file://), sin servidor
python kaizen.py dashboard --port 8765  # servidor HTTP en vivo (auto-refresca)
```
El dashboard **estático** (`dashboard/index.html`) se genera automáticamente al cerrar cada sesión
(`run_session.py` lo regenera como best-effort). Abrilo con la URL `file://` que imprime el comando.
El header del HTML muestra la propia URL clickeable.

El dashboard incluye:
- La **fase actual** del ciclo (la etapa resaltada en azul).
- **Métricas** (total, aceptadas, rechazadas, iterando, AOTL, tasa %).
- Sección **"Pendiente de revisión humana"** (naranja): sesiones con `verdict=iterate` o escaladas;
  el loop se detuvo ahí y necesita tu decisión.
- **Historial** de sesiones con estado de implementación e indicadores de color.

La variante HTTP (`--port`) sigue disponible para visualización en vivo con auto-refresco.
El botón **STOP** en la variante HTTP pide la parada cooperativa.

## Costo
Un loop `--forever` con Opus puede gastar bastante. Para iterar seguido conviene `sonnet` (default)
o el driver `mock` (gratis, offline) para ensayar el flujo. Todo es configurable en el adapter.

## Ampliar el alcance
El loop empieza acotado al sandbox `playground/`. Cuando confíes, ampliá `observe.focus` en el
adapter a más carpetas de `kaizen/` (sin incluir nunca las rutas protegidas). Una mejora a la vez,
medible y reversible: es el mismo contrato que en HITL.
