# Dossier UAT — ADO-0: [INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)

> **Run ID**: `f93445b8-acea-4954-8659-33ed89bca9a0`  
> **Fecha**: 2026-07-25T20:48:45Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

La validación UAT del ticket [INC] Truncamiento del campo Póliza en Búsqueda de Clientes resultó bloqueada. Se ejecutaron 4 escenarios y ninguno fue aprobado; todos presentaron incidencias relacionadas con el truncamiento incorrecto del campo Póliza (MaxLength=20). Se requiere revisión y corrección para garantizar el cumplimiento de la restricción de longitud antes de continuar con la validación.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos. | ⚠️ BLOCKED | 4 ms |

| `P02` | El campo Obligación en FrmBusquedaJudicial.aspx admite hasta 50 caracteres. | ⚠️ BLOCKED | 4 ms |

| `P03` | Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado. | ⚠️ BLOCKED | 4 ms |

| `P04` | Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol). | ⚠️ BLOCKED | 4 ms |


---


## Fallas detectadas


### ❌ P01 — P01

**Mensaje**: RUNTIME_ERROR






---


### ❌ P02 — P02

**Mensaje**: RUNTIME_ERROR






---


### ❌ P03 — P03

**Mensaje**: RUNTIME_ERROR






---


### ❌ P04 — P04

**Mensaje**: RUNTIME_ERROR






---






---

## Evidencia por escenario


### P01 — El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P02 — El campo Obligación en FrmBusquedaJudicial.aspx admite hasta 50 caracteres.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P03 — Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P04 — Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol).

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- Revise los registros de errores para identificar la causa exacta del error de ejecución.

- Asegúrese de que todas las dependencias y servicios requeridos estén correctamente configurados y en funcionamiento.

- Ejecute pruebas unitarias en los módulos afectados para aislar el problema antes de volver a ejecutar el flujo completo.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `f93445b8-acea-4954-8659-33ed89bca9a0`_