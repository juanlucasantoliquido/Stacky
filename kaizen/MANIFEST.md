# MANIFEST — Qué hace cada archivo y carpeta

> Inventario autoritativo de `kaizen/`. Si agregás un archivo, agregalo acá.
> Todas las rutas son **relativas a la raíz `kaizen/`**.

## Raíz

| Ruta | Tipo | Propósito |
|---|---|---|
| `README.md` | doc | Punto de entrada: qué es, mapa, quickstart, modos del ciclo. |
| `MANIFEST.md` | doc | Este archivo. Inventario de propósito por archivo/carpeta. |
| `PORTABILITY.md` | doc | Manifiesto de portabilidad: cómo mover/extraer la carpeta sin romper nada. |
| `ASSUMPTIONS.md` | doc | Supuestos, límites y no-objetivos del sistema. |
| `VERSION` | meta | Versión semántica de la base (independiente del repo padre). |
| `.gitignore` | meta | Ignora datos volátiles de sesiones/artefactos locales. |
| `kaizen.py` | cli | **Punto de entrada único.** Despacha a `scripts/`: new, run, list, show, validate, spawn-child, promote, view, metrics, selfcheck, doctor, adapter, check, archive, **apply, loop, dashboard**. |
| `start_kaizen.bat` | launcher | **Doble clic (Windows):** levanta el dashboard, abre el navegador y corre el loop AI-driven constante. |

## `config/` — Capa de configuración (genérico; valores por proyecto)

| Ruta | Tipo | Propósito |
|---|---|---|
| `config/kaizen.config.yaml` | config | Config activa: modo (HITL/AOTL), adapter seleccionado, política de evaluación. |
| `config/kaizen.config.example.yaml` | config | Ejemplo comentado para copiar y adaptar. |
| `config/profiles/default.yaml` | config | Perfil por defecto (umbrales, presupuesto, gates). |

## `docs/` — Documentación (genérico)

| Ruta | Tipo | Propósito |
|---|---|---|
| `docs/00_CONCEPT.md` | doc | Base conceptual del sistema (problema, ciclo, invariantes). |
| `docs/01_ARCHITECTURE.md` | doc | Componentes, flujo de datos, fronteras de aislamiento. |
| `docs/02_USAGE.md` | doc | Uso mínimo: correr una sesión en HITL paso a paso. |
| `docs/03_SESSIONS.md` | doc | Modelo de sesiones separadas; transición HITL → AOTL. |
| `docs/04_HUMAN_REVIEW.md` | doc | Base de evaluación humana: rúbrica, veredictos, gates. |
| `docs/05_MIGRATION.md` | doc | Esqueleto para extraer esto como herramienta independiente. |
| `docs/06_RUNBOOK_AGENTE.md` | doc | **Instructivo paso a paso** para que cualquier agente lance una sesión completa. |
| `docs/07_AOTL_AUTODRIVE.md` | doc | **Modo AI-driven:** loop de automejora + dashboard; reparto de responsabilidades y guardarraíles. |

## `contracts/` — Contratos de E/S (genérico, JSON Schema draft 2020-12)

| Ruta | Tipo | Propósito |
|---|---|---|
| `contracts/README.md` | doc | Cómo se usan los contratos y su versionado. |
| `contracts/session.input.schema.json` | contrato | Entrada de una sesión (objetivo, contexto, adapter). |
| `contracts/session.output.schema.json` | contrato | Salida de una sesión (propuesta + evaluación + decisión + refs). |
| `contracts/proposal.schema.json` | contrato | Una propuesta de mejora. |
| `contracts/evaluation.schema.json` | contrato | Una evaluación (humana o agéntica) de una propuesta. |
| `contracts/decision.schema.json` | contrato | Decisión final y su justificación. |
| `contracts/artifact.schema.json` | contrato | Metadatos de un artefacto producido. |
| `contracts/change_set.schema.json` | contrato | Cambios declarativos que el improver propone y `apply.py` aplica reversible (AOTL). |

## `prompts/` — Prompts (genérico, afinables)

| Ruta | Tipo | Propósito |
|---|---|---|
| `prompts/system/improver.system.md` | prompt | Rol/sistema del proponedor de mejoras. |
| `prompts/system/evaluator.system.md` | prompt | Rol/sistema del evaluador. |
| `prompts/templates/propose.prompt.md` | prompt | Plantilla para pedir una propuesta. |
| `prompts/templates/critique.prompt.md` | prompt | Plantilla para pedir una evaluación/crítica. |

## `agents/` — Roles agénticos (genérico)

| Ruta | Tipo | Propósito |
|---|---|---|
| `agents/README.md` | doc | Qué es un agente acá y cómo se vincula a prompts/contratos. |
| `agents/improver.agent.md` | agente | Definición del agente proponedor. |
| `agents/evaluator.agent.md` | agente | Definición del agente evaluador. |

## `skills/` — Procedimientos invocables (genérico)

| Ruta | Tipo | Propósito |
|---|---|---|
| `skills/README.md` | doc | Qué es una skill acá y cómo se invoca. |
| `skills/run-session/SKILL.md` | skill | Procedimiento determinístico para correr una sesión. |

## `templates/` — Plantillas de artefacto (genérico)

| Ruta | Tipo | Propósito |
|---|---|---|
| `templates/session.template.md` | plantilla | Esqueleto de la bitácora de una sesión. |
| `templates/proposal.template.md` | plantilla | Esqueleto de una propuesta. |
| `templates/evaluation.template.md` | plantilla | Esqueleto de una evaluación. |
| `templates/decision.template.md` | plantilla | Esqueleto de una decisión (ADR-lite). |

## `adapters/` — Único punto de acoplamiento (REEMPLAZABLE por proyecto)

| Ruta | Tipo | Propósito |
|---|---|---|
| `adapters/README.md` | doc | Qué es un adapter y la frontera genérico/específico. |
| `adapters/adapter.contract.md` | contrato | Qué debe proveer cualquier adapter. |
| `adapters/generic/adapter.yaml` | adapter | Adapter genérico HITL, sin dependencias del padre (por defecto). |
| `adapters/example-project/adapter.yaml` | adapter | Ejemplo que muestra qué se reemplaza al acoplar a un proyecto. |
| `adapters/claude/adapter.yaml` | adapter | **AOTL AI-driven:** improver/evaluator vía Claude Code CLI (`claude -p`). |
| `adapters/mock/adapter.yaml` | adapter | **AOTL determinista** sin red: demo/test reproducible del loop. |

## `playground/` — Sandbox del loop AI-driven (foco por defecto)

| Ruta | Tipo | Propósito |
|---|---|---|
| `playground/README.md` | doc | Qué es el sandbox y cómo ampliar el foco editable del loop. |
| `playground/JOURNAL.md` | dato | Bitácora donde el loop anota cada mejora aceptada (demo reproducible). |

## `sessions/`, `artifacts/`, `decisions/` — Datos (generados)

| Ruta | Tipo | Propósito |
|---|---|---|
| `sessions/README.md` | doc | Convención de nombrado y contenido de cada sesión. |
| `sessions/_index.json` | dato | Índice de sesiones (append-only); incluye `impl_status` en AOTL. |
| `sessions/_forensic.jsonl` | dato | Traza forense global (append-only) de todos los runs. |
| `sessions/_loop.status.json` | dato | Estado vivo del loop AOTL (lo lee el dashboard). Transitorio. |
| `sessions/_loop.stop` | dato | Flag de parada cooperativa del loop (lo crea el botón STOP). Transitorio. |
| `artifacts/README.md` | doc | Cómo se guardan los artefactos. |
| `decisions/README.md` | doc | Registro de decisiones (ADR-lite) acumulado. |

## `scripts/` — Utilidades portables (genérico)

| Ruta | Tipo | Propósito |
|---|---|---|
| `scripts/README.md` | doc | Qué hace cada script y sus garantías de portabilidad. |
| `scripts/new_session.py` | script | Crea una sesión nueva desde plantillas (stdlib pura, sin red). |
| `scripts/run_session.py` | script | Motor: gate determinista + escritura de decisión/output + índice + forense. |
| `scripts/validate.py` | script | Valida los artefactos de una sesión contra los contratos. |
| `scripts/spawn_child.py` | script | Crea la sesión hija de una sesión 'iterate' (enlace madre↔hija). |
| `scripts/promote_decision.py` | script | Promueve una decisión 'accept' a un ADR-lite en `decisions/`. |
| `scripts/forensic_view.py` | script | Visor de la traza forense (timeline legible) de una sesión. |
| `scripts/metrics.py` | script | Reporte forense de eficiencia agregado (texto/`--json`, media/mediana/min/max). |
| `scripts/selfcheck.py` | script | Guard de consistencia/regresión de las sesiones cerradas (exige traza con `run.end`). |
| `scripts/list_sessions.py` | script | Lista las sesiones del índice con estado/veredicto y filtros. |
| `scripts/show_session.py` | script | Resumen legible de una sesión (objetivo/propuesta/evaluación/decisión). |
| `scripts/doctor.py` | script | Diagnóstico de salud estructural (config/perfil/adapter/contratos/scripts/índice). |
| `scripts/adapter_info.py` | script | Resuelve y describe el adapter activo; valida sus campos de contrato. |
| `scripts/check.py` | script | Chequeo agregado para CI (doctor + selfcheck + validate). |
| `scripts/archive.py` | script | Archiva una sesión cerrada (housekeeping no destructivo). |
| `scripts/forensic.py` | módulo | Logger forense JSONL append-only (sha256 + tiempos). |
| `scripts/_config.py` | módulo | Lector YAML mínimo (stdlib pura, sin PyYAML). |
| `scripts/_console.py` | módulo | Helper de salida UTF-8 tolerante (portabilidad consolas cp1252). |
| `scripts/autoloop.py` | script | **Loop de automejora AI-driven (AOTL):** orquesta observar→proponer→aplicar→medir→evaluar→gate→resolver. |
| `scripts/dashboard.py` | script | **Dashboard HTML en vivo** del loop (stdlib `http.server`, offline-first). |
| `scripts/apply.py` | script | Aplica/revierte el `change_set` de forma determinista y reversible (pre-imagen); commit scopeado. |
| `scripts/engine.py` | módulo | Motor improver/evaluator: drivers `mock` (offline) y `claude` (CLI `claude -p`). |
| `scripts/aotl_state.py` | módulo | Estado compartido AOTL: `impl_status`, estado del loop, flag de parada, guardarraíl de rutas. |
| `scripts/test_aotl.py` | test | Tests del modo AOTL (guardarraíl, apply/rollback, motor mock, gate, dashboard). |
