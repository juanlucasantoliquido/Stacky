# Dossier UAT — ADO-0: [INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)

> **Run ID**: `6fa93908-2823-4199-aafa-8076333e7d7f`  
> **Fecha**: 2026-07-26T00:28:10Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Se ejecutaron 3 escenarios UAT para '[INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)'. Resultado: BLOCKED. Escenarios con problemas: P01. Se requiere revisión humana de los ítems marcados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos. | ⚠️ BLOCKED | 0 ms |

| `P02` | Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado. | ✅ PASS | 0 ms |

| `P03` | Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol). | ✅ PASS | 0 ms |


---


## Fallas detectadas


### ❌ P01 — P01

**Mensaje**: evaluator_inconclusive






---






---

## Evidencia por escenario


### P01 — El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos.

**Estado**: ⚠️ BLOCKED (evaluator_inconclusive)


**Artefactos**:









---


### P02 — Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado.

**Estado**: ✅ PASS


**Artefactos**:









---


### P03 — Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol).

**Estado**: ✅ PASS


**Artefactos**:









---



## Recomendaciones para el QA humano



- [P01] Revisar manualmente — status: blocked



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `6fa93908-2823-4199-aafa-8076333e7d7f`_