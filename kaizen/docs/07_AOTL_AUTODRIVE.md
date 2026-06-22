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

## Guardarraíles (no negociables)
1. **Rutas acotadas:** el auto-apply sólo toca archivos dentro de `kaizen/` y **nunca** los datos
   de sesión ni la maquinaria del propio loop (denylist en `scripts/aotl_state.py`). Empieza
   acotado al sandbox `playground/` vía `observe.focus` del adapter.
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

### 3. Ver todo en vivo
```sh
python kaizen.py dashboard            # http://127.0.0.1:8765
```
El dashboard se auto-refresca y muestra: la **fase actual** del ciclo, métricas, y cada **plan
con su estado** (verde = implementado · azul = sólo plan sin implementar · rojo = rechazado ·
violeta = iterando · naranja = escalado a vos). Click en una fila para ver propuesta, evaluación,
decisión y los archivos cambiados. El botón **STOP** pide la parada cooperativa.

## Costo
Un loop `--forever` con Opus puede gastar bastante. Para iterar seguido conviene `sonnet` (default)
o el driver `mock` (gratis, offline) para ensayar el flujo. Todo es configurable en el adapter.

## Ampliar el alcance
El loop empieza acotado al sandbox `playground/`. Cuando confíes, ampliá `observe.focus` en el
adapter a más carpetas de `kaizen/` (sin incluir nunca las rutas protegidas). Una mejora a la vez,
medible y reversible: es el mismo contrato que en HITL.
