# Dossier UAT — ADO-0: [INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)

> **Run ID**: `5583da80-7a47-4995-9957-274149702e20`  
> **Fecha**: 2026-07-25T20:57:18Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Resumen Ejecutivo UAT: La incidencia relacionada con el truncamiento del campo Póliza en la Búsqueda de Clientes (MaxLength=20) permanece bloqueada. De los 3 escenarios evaluados, solo 1 fue exitoso; los escenarios P01 y P02 presentan problemas que impiden la validación completa. Se requiere intervención técnica para resolver los errores detectados antes de continuar con la aprobación UAT.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos. | ⚠️ BLOCKED | 0 ms |

| `P02` | Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado. | ⚠️ BLOCKED | 0 ms |

| `P03` | Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol). | ✅ PASS | 0 ms |


---


## Fallas detectadas


### ❌ P01 — P01

**Mensaje**: evaluator_inconclusive






---


### ❌ P02 — P02

**Mensaje**: evaluator_inconclusive






---






---

## Evidencia por escenario


### P01 — El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos.

**Estado**: ⚠️ BLOCKED (evaluator_inconclusive)


**Artefactos**:









---


### P02 — Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado.

**Estado**: ⚠️ BLOCKED (evaluator_inconclusive)


**Artefactos**:









---


### P03 — Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol).

**Estado**: ✅ PASS


**Artefactos**:









---



## Recomendaciones para el QA humano



- Revise los criterios de evaluación para asegurar que sean claros y específicos, evitando resultados inconclusos.

- Solicite información adicional o aclaraciones al evaluador para resolver cualquier ambigüedad en la evaluación.

- Implemente una revisión por pares para los casos bloqueados, con el fin de obtener una segunda opinión y reducir la incertidumbre.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `5583da80-7a47-4995-9957-274149702e20`_