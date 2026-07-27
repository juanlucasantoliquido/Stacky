# Dossier UAT — ADO-0: [INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)

> **Run ID**: `f418d29d-346b-4b18-8102-667326239068`  
> **Fecha**: 2026-07-25T20:27:30Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Se ejecutaron 4 escenarios UAT para '[INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)'. Resultado: BLOCKED. Escenarios con problemas: P01, P02, P03, P04. Se requiere revisión humana de los ítems marcados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos. | ⚠️ BLOCKED | 0 ms |

| `P02` | El campo Obligación en FrmBusquedaJudicial.aspx admite hasta 50 caracteres. | ⚠️ BLOCKED | 0 ms |

| `P03` | Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado. | ⚠️ BLOCKED | 0 ms |

| `P04` | Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol). | ⚠️ BLOCKED | 0 ms |


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



- [P01] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P02] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P03] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P04] Error de ejecución — verificar entorno (Node, Playwright, env vars).



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `f418d29d-346b-4b18-8102-667326239068`_