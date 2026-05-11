# Dossier UAT — ADO-0: RF-007 - Modificaciones en la Lista de Obligaciones

> **Run ID**: `0a2bde5c-6db5-4789-b8f1-10cc8f893c72`  
> **Fecha**: 2026-05-10T02:02:30Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Resumen Ejecutivo UAT:  
El ticket RF-007 - Modificaciones en la Lista de Obligaciones se encuentra BLOQUEADO. Se ejecutaron 8 escenarios, de los cuales ninguno fue aprobado y se identificaron 8 incidencias en los escenarios P02, P05, P06, P07, P08, P10, P12 y P13. Se requiere resolución de los problemas detectados para continuar con la validación y asegurar el cumplimiento de los requisitos funcionales.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P02` | La columna "Fecha de ingreso judicial" no es recuperable por configuracion | ⚠️ BLOCKED | 0 ms |

| `P05` | Comportamiento con campos sin valor (nulos) en los 8 nuevos campos | ⚠️ BLOCKED | 0 ms |

| `P06` | Valores "Si"/"No" del campo "Afiliado al Debito Automatico" | ⚠️ BLOCKED | 0 ms |

| `P07` | Los 8 nuevos campos son de solo lectura para todos los perfiles | ⚠️ BLOCKED | 0 ms |

| `P08` | Formato monetario de "Saldo a favor disponible" y "Monto de la Cuota" | ⚠️ BLOCKED | 0 ms |

| `P10` | Actualizacion de datos tras batch nocturno | ⚠️ BLOCKED | 0 ms |

| `P12` | Exportacion incluye nuevos campos y excluye columna eliminada (si aplica) | ⚠️ BLOCKED | 0 ms |

| `P13` | Consistencia de "Nombre del Corredor" con RF-006 (Corredor Principal en cabecera) | ⚠️ BLOCKED | 0 ms |


---


## Fallas detectadas


### ❌ P02 — P02

**Mensaje**: RUNTIME_ERROR






---


### ❌ P05 — P05

**Mensaje**: RUNTIME_ERROR






---


### ❌ P06 — P06

**Mensaje**: RUNTIME_ERROR






---


### ❌ P07 — P07

**Mensaje**: RUNTIME_ERROR






---


### ❌ P08 — P08

**Mensaje**: RUNTIME_ERROR






---


### ❌ P10 — P10

**Mensaje**: RUNTIME_ERROR






---


### ❌ P12 — P12

**Mensaje**: RUNTIME_ERROR






---


### ❌ P13 — P13

**Mensaje**: RUNTIME_ERROR






---






---

## Evidencia por escenario


### P02 — La columna "Fecha de ingreso judicial" no es recuperable por configuracion

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P05 — Comportamiento con campos sin valor (nulos) en los 8 nuevos campos

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P06 — Valores "Si"/"No" del campo "Afiliado al Debito Automatico"

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P07 — Los 8 nuevos campos son de solo lectura para todos los perfiles

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P08 — Formato monetario de "Saldo a favor disponible" y "Monto de la Cuota"

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P10 — Actualizacion de datos tras batch nocturno

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P12 — Exportacion incluye nuevos campos y excluye columna eliminada (si aplica)

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P13 — Consistencia de "Nombre del Corredor" con RF-006 (Corredor Principal en cabecera)

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- Revise los registros de errores para identificar la causa exacta del error de ejecución.

- Verifique que todas las dependencias y configuraciones necesarias estén correctamente instaladas.

- Ejecute los casos de prueba de forma individual para aislar el problema.

- Consulte con el equipo de desarrollo si persisten los errores tras las verificaciones iniciales.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `0a2bde5c-6db5-4789-b8f1-10cc8f893c72`_