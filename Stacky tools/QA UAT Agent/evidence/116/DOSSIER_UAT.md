# Dossier UAT — ADO-116: RF-004 - Indicador de Promesas de Pago Vigentes con Vencimiento en los Proximos 7 Dias

> **Run ID**: `0f1ba0bd-e487-4410-a50d-2629f73fafa6`  
> **Fecha**: 2026-05-07T02:41:58Z  
> **Agente**: 1.2.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**🔶 MIXED** — Hay escenarios FAIL y BLOCKED simultáneos. Revisión humana requerida.


---

## Resumen ejecutivo

Resumen Ejecutivo UAT:  
La validación del ticket RF-004 arrojó un resultado mixto. Se ejecutaron 3 escenarios, de los cuales ninguno fue aprobado. Se identificaron 3 incidencias en los escenarios P02, P03 y P04, relacionadas con el indicador de promesas de pago vigentes con vencimiento en los próximos 7 días. Se recomienda revisar y corregir los hallazgos antes de avanzar a producción.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P02` | Unidad promesa (no lote) | ⚠️ BLOCKED | 52173 ms |

| `P03` | Aislamiento por usuario | ⚠️ BLOCKED | 37562 ms |

| `P04` | Visibilidad Pacifico | ❌ FAIL | 44116 ms |


---


## Fallas detectadas


### ❌ P02 — P02

**Mensaje**: RUNTIME_ERROR




**Trace Playwright**: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P02\trace.zip`



---


### ❌ P03 — P03

**Mensaje**: evaluator_inconclusive




**Trace Playwright**: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\step_00_setup.png`


---


### ❌ P04 — P04

**Mensaje**: Error: P04: panel_timer debe ser visible

    [2mexpect([22m[31mlocator[39m[2m).[22mtoBeVisible[2m([22m[2m)[22m failed

    Locator:  locator('#updTimer')
    Expected: visible
    Received: hidden
    Timeout:  5000ms

    Call log:
    [2m  - P04: panel_timer debe ser visible with timeo


| | Valor |
|---|---|
| **Esperado** | `visible` |
| **Actual** | `hidden
    Timeout:  5000ms

    Call log:
    [2m  - P04: panel_timer debe ser visible with timeou` |



**Trace Playwright**: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\step_00_setup.png`


---




---

## Evidencia por escenario


### P02 — Unidad promesa (no lote)

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P02\trace.zip`
- Video: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P02\video.webm`







---


### P03 — Aislamiento por usuario

**Estado**: ⚠️ BLOCKED (evaluator_inconclusive)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\trace.zip`


- Screenshots:

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\step_00_setup.png`

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\step_01_after.png`

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\step_final_state.png`

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P03\test_failure.png`








---


### P04 — Visibilidad Pacifico

**Estado**: ❌ FAIL


**Artefactos**:
- Trace: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\trace.zip`
- Video: `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\step_00_setup.png`

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\step_final_state.png`

  - `N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent\evidence\116\P04\test_failure.png`







**Assertions fallidas**:

- `Error: P04: panel_timer debe ser visible

    [2mexpect([22m[31mlocator[39m[2m).[22mtoBeVisible[2m([22m[2m)[22m failed

    Locator:  locator('#updTimer')
    Expected: visible
    Received: hidden
    Timeout:  5000ms

    Call log:
    [2m  - P04: panel_timer debe ser visible with timeo` — Esperado: `visible` | Actual: `hidden
    Timeout:  5000ms

    Call log:
    [2m  - P04: panel_timer debe ser visible with timeou`



---



## Recomendaciones para el QA humano



- Verifica que el elemento con el selector '#updTimer' esté correctamente renderizado y no oculto por estilos CSS.

- Revisa si existen condiciones en el código que puedan estar ocultando el panel_timer durante la ejecución de la prueba.

- Consulta los registros de errores y el flujo de la prueba para identificar posibles causas del error de visibilidad.

- Asegúrate de que no haya dependencias o datos faltantes que bloqueen la ejecución de los casos P02 y P03.



---

## Próximos pasos



- Separar fallos de bloqueos para tratamiento diferencial.

- Resolver bloqueos de entorno.

- Crear bugs para los escenarios fallidos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.2.0 — Run `0f1ba0bd-e487-4410-a50d-2629f73fafa6`_