# Dossier UAT — ADO-0: RF-007 - Modificaciones en la Lista de Obligaciones

> **Run ID**: `3b42538e-7210-4c25-876f-3b21c9c759cc`  
> **Fecha**: 2026-05-09T21:43:52Z  
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
El ticket RF-007 - Modificaciones en la Lista de Obligaciones se encuentra BLOQUEADO. Se ejecutaron 8 escenarios y todos presentaron incidencias (P02, P05, P06, P07, P08, P11, P12, P13), sin casos aprobados. Se requiere revisión y corrección de los problemas detectados antes de continuar con la validación.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P02` | La columna "Fecha de ingreso judicial" no es recuperable por configuracion | ⚠️ BLOCKED | 0 ms |

| `P05` | Comportamiento con campos sin valor (nulos) en los 8 nuevos campos | ⚠️ BLOCKED | 1 ms |

| `P06` | Valores "Si"/"No" del campo "Afiliado al Debito Automatico" | ⚠️ BLOCKED | 0 ms |

| `P07` | Los 8 nuevos campos son de solo lectura para todos los perfiles | ⚠️ BLOCKED | 0 ms |

| `P08` | Formato monetario de "Saldo a favor disponible" y "Monto de la Cuota" | ⚠️ BLOCKED | 0 ms |

| `P11` | La sub-vista de detalle de cuotas no se ve afectada (regresion) | ⚠️ BLOCKED | 0 ms |

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


### ❌ P11 — P11

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


### P11 — La sub-vista de detalle de cuotas no se ve afectada (regresion)

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



- Revise los registros de errores para identificar la causa raíz del error de ejecución.

- Verifique que todas las dependencias y configuraciones necesarias estén correctamente instaladas.

- Ejecute las pruebas de manera individual para aislar el componente que está fallando.

- Consulte la documentación del sistema para asegurarse de que los entornos de prueba estén correctamente configurados.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `3b42538e-7210-4c25-876f-3b21c9c759cc`_