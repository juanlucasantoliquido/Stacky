# Dossier UAT — ADO-0: RF-008 — Incorporación de Campos Provincia y Departamento Territorial en el Mantenedor de Domicilios

> **Run ID**: `uat-122-20260513T151246Z-ef5a1b`  
> **Fecha**: 2026-05-13T15:13:46Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Se ejecutaron 4 escenarios UAT para 'RF-008 — Incorporación de Campos Provincia y Departamento Territorial en el Mantenedor de Domicilios'. Resultado: BLOCKED. Escenarios con problemas: P03, P05, P06, P09. Se requiere revisión humana de los ítems marcados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P03` | Abrir domicilio existente en Modificación | ⚠️ BLOCKED | 0 ms |

| `P05` | Guardar con Provincia seleccionada y reabrir | ⚠️ BLOCKED | 2 ms |

| `P06` | Guardar sin informar Provincia | ⚠️ BLOCKED | 0 ms |

| `P09` | Borrado lógico de domicilio con Provincia | ⚠️ BLOCKED | 0 ms |


---


## Fallas detectadas


### ❌ P03 — P03

**Mensaje**: RUNTIME_ERROR






---


### ❌ P05 — P05

**Mensaje**: RUNTIME_ERROR






---


### ❌ P06 — P06

**Mensaje**: RUNTIME_ERROR






---


### ❌ P09 — P09

**Mensaje**: RUNTIME_ERROR






---






---

## Evidencia por escenario


### P03 — Abrir domicilio existente en Modificación

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P05 — Guardar con Provincia seleccionada y reabrir

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P06 — Guardar sin informar Provincia

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P09 — Borrado lógico de domicilio con Provincia

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- [P03] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P05] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P06] Error de ejecución — verificar entorno (Node, Playwright, env vars).

- [P09] Error de ejecución — verificar entorno (Node, Playwright, env vars).



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `uat-122-20260513T151246Z-ef5a1b`_