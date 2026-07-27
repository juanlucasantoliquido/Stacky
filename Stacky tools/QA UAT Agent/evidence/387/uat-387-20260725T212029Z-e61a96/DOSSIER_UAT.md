# Dossier UAT — ADO-387: [INC] Columna duplicada "Medio de Contacto" en grid Gestiones de Detalle de Cliente

> **Run ID**: `12be76d2-cdd1-4f7e-a4af-e5241af79438`  
> **Fecha**: 2026-07-25T21:21:00Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Se ejecutaron 2 escenarios UAT para '[INC] Columna duplicada "Medio de Contacto" en grid Gestiones de Detalle de Cliente'. Resultado: BLOCKED. Escenarios con problemas: P02, P04. Se requiere revisión humana de los ítems marcados.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P02` | La columna que exponía el tipo/clasificación del medio ya no se renderiza en pantalla. | ⚠️ BLOCKED | 0 ms |

| `P04` | No se introducen errores ni columnas vacías/rotas en el grid tras el cambio (paginación y ordenamiento existentes siguen funcionando). | ⚠️ BLOCKED | 0 ms |


---


## Fallas detectadas


### ❌ P02 — P02

**Mensaje**: missing_selectors






---


### ❌ P04 — P04

**Mensaje**: missing_selectors






---






---

## Evidencia por escenario


### P02 — La columna que exponía el tipo/clasificación del medio ya no se renderiza en pantalla.

**Estado**: ⚠️ BLOCKED (missing_selectors)





---


### P04 — No se introducen errores ni columnas vacías/rotas en el grid tras el cambio (paginación y ordenamiento existentes siguen funcionando).

**Estado**: ⚠️ BLOCKED (missing_selectors)





---



## Recomendaciones para el QA humano



- [P02] Revisar manualmente — status: blocked

- [P04] Revisar manualmente — status: blocked



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `12be76d2-cdd1-4f7e-a4af-e5241af79438`_