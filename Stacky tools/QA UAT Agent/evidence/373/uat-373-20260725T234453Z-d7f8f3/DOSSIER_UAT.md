# Dossier UAT — ADO-0: [INC] Domicilios en pestaña Contactos desaparecen al cambiar de pestaña

> **Run ID**: `471987ae-0f09-422e-9265-8fd078ebfc37`  
> **Fecha**: 2026-07-25T23:55:40Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Se ejecutaron 6 escenarios UAT para '[INC] Domicilios en pestaña Contactos desaparecen al cambiar de pestaña'. Resultado: BLOCKED. Escenarios con problemas: P01, P02, P03, P04, P05, P07. Se requiere revisión humana de los ítems marcados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | Al seleccionar un contacto CORREDOR en la pestaña Contactos, la grilla Domicilios carga correctamente los domicilios existentes de ese contacto. | ⚠️ BLOCKED | 7 ms |

| `P02` | Al agregar un domicilio nuevo al contacto y guardar, el registro aparece en la grilla sin necesidad de refrescar la página completa. | ⚠️ BLOCKED | 8 ms |

| `P03` | Al modificar un domicilio existente del contacto, el cambio se refleja en la grilla. | ⚠️ BLOCKED | 7 ms |

| `P04` | Al eliminar un domicilio, desaparece de la grilla. | ⚠️ BLOCKED | 7 ms |

| `P05` | La grilla de Domicilios del cliente principal (sin selección de contacto) no regresa errores. | ⚠️ BLOCKED | 7 ms |

| `P07` | La migración de columnas DTDISTRIT / DTURBAN / DTDIRECCION en RDIRE está confirmada en el entorno de pruebas y producción. | ⚠️ BLOCKED | 10 ms |


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


### ❌ P05 — P05

**Mensaje**: RUNTIME_ERROR






---


### ❌ P07 — P07

**Mensaje**: RUNTIME_ERROR






---






---

## Evidencia por escenario


### P01 — Al seleccionar un contacto CORREDOR en la pestaña Contactos, la grilla Domicilios carga correctamente los domicilios existentes de ese contacto.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P02 — Al agregar un domicilio nuevo al contacto y guardar, el registro aparece en la grilla sin necesidad de refrescar la página completa.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P03 — Al modificar un domicilio existente del contacto, el cambio se refleja en la grilla.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P04 — Al eliminar un domicilio, desaparece de la grilla.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P05 — La grilla de Domicilios del cliente principal (sin selección de contacto) no regresa errores.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P07 — La migración de columnas DTDISTRIT / DTURBAN / DTDIRECCION en RDIRE está confirmada en el entorno de pruebas y producción.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- [P01] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P02] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P03] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P04] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P05] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P07] Error de ejecución — verificar entorno (Node, Playwright, env vars).



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `471987ae-0f09-422e-9265-8fd078ebfc37`_