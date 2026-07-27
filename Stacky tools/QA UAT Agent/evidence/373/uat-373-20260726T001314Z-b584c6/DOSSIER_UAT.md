# Dossier UAT — ADO-0: [INC] Domicilios en pestaña Contactos desaparecen al cambiar de pestaña

> **Run ID**: `b9acf40d-a527-475f-a3b6-d241ab243504`  
> **Fecha**: 2026-07-26T00:25:28Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**❌ FAIL** — Al menos un escenario falló.


---

## Resumen ejecutivo

Resumen Ejecutivo UAT: La validación del ticket [INC] Domicilios en pestaña Contactos desaparecen al cambiar de pestaña resultó en un FAIL. De 7 escenarios ejecutados, 6 fueron exitosos y 1 presentó problemas (P04). El escenario fallido evidencia que los domicilios no se mantienen visibles al alternar entre pestañas, afectando la experiencia del usuario. Se recomienda revisar y corregir la funcionalidad antes de avanzar a producción.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | Al seleccionar un contacto CORREDOR en la pestaña Contactos, la grilla Domicilios carga correctamente los domicilios existentes de ese contacto. | ✅ PASS | 0 ms |

| `P02` | Al agregar un domicilio nuevo al contacto y guardar, el registro aparece en la grilla sin necesidad de refrescar la página completa. | ✅ PASS | 0 ms |

| `P03` | Al modificar un domicilio existente del contacto, el cambio se refleja en la grilla. | ✅ PASS | 0 ms |

| `P04` | Al eliminar un domicilio, desaparece de la grilla. | ❌ FAIL | 0 ms |

| `P05` | La grilla de Domicilios del cliente principal (sin selección de contacto) no regresa errores. | ✅ PASS | 0 ms |

| `P06` | La funcionalidad de Teléfonos y eMails en la misma pestaña no presenta regresiones. | ✅ PASS | 0 ms |

| `P07` | La migración de columnas DTDISTRIT / DTURBAN / DTDIRECCION en RDIRE está confirmada en el entorno de pruebas y producción. | ✅ PASS | 0 ms |


---


## Fallas detectadas


### ❌ P04 — P04

**Mensaje**: Oracle 'grid_c_griddomicilios' (tipo=count_eq) expected='0' actual='1'


| | Valor |
|---|---|
| **Esperado** | `0` |
| **Actual** | `1` |





---






---

## Evidencia por escenario


### P01 — Al seleccionar un contacto CORREDOR en la pestaña Contactos, la grilla Domicilios carga correctamente los domicilios existentes de ese contacto.

**Estado**: ✅ PASS


**Artefactos**:









---


### P02 — Al agregar un domicilio nuevo al contacto y guardar, el registro aparece en la grilla sin necesidad de refrescar la página completa.

**Estado**: ✅ PASS


**Artefactos**:









---


### P03 — Al modificar un domicilio existente del contacto, el cambio se refleja en la grilla.

**Estado**: ✅ PASS


**Artefactos**:









---


### P04 — Al eliminar un domicilio, desaparece de la grilla.

**Estado**: ❌ FAIL


**Artefactos**:








**Assertions fallidas**:

- `Oracle 'grid_c_griddomicilios' (tipo=count_eq) expected='0' actual='1'` — Esperado: `0` | Actual: `1`



---


### P05 — La grilla de Domicilios del cliente principal (sin selección de contacto) no regresa errores.

**Estado**: ✅ PASS


**Artefactos**:









---


### P06 — La funcionalidad de Teléfonos y eMails en la misma pestaña no presenta regresiones.

**Estado**: ✅ PASS


**Artefactos**:









---


### P07 — La migración de columnas DTDISTRIT / DTURBAN / DTDIRECCION en RDIRE está confirmada en el entorno de pruebas y producción.

**Estado**: ✅ PASS


**Artefactos**:









---



## Recomendaciones para el QA humano



- Verifica si existe un domicilio adicional en el sistema que no debería estar registrado.

- Revisa la configuración y los datos de entrada para asegurarte de que no se esté generando un domicilio extra por error.

- Consulta con el equipo de desarrollo si hubo cambios recientes en la lógica de creación de domicilios.

- Realiza una prueba manual para confirmar si el resultado es consistente y documenta los pasos para identificar la causa.



---

## Próximos pasos



- Revisar los escenarios fallidos con el desarrollador.

- Crear bug tickets para cada fallo confirmado.

- Planificar re-ejecución tras correcciones.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `b9acf40d-a527-475f-a3b6-d241ab243504`_