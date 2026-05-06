# Dossier UAT — ADO-72: RF-005 — Alineación de campos de las listas de agenda con nuevos campos solicitados

> **Run ID**: `6b87d1e1-49e0-43b8-900b-69e4e5ae769d`  
> **Fecha**: 2026-05-06T14:35:33Z  
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
El ticket RF-005 presentó un veredicto MIXTO. De los 4 escenarios evaluados, ninguno fue aprobado y se identificaron 4 incidencias en los escenarios P01, P03, P04 y P05. Las fallas están relacionadas con la alineación de campos en las listas de agenda y la incorporación de los nuevos campos solicitados. Se recomienda revisar y corregir los puntos observados antes de proceder con la siguiente fase.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | Búsqueda sin filtros + validación de nuevas columnas | ⚠️ BLOCKED | 37450 ms |

| `P03` | Filtro Débito Auto = No | ⚠️ BLOCKED | 41150 ms |

| `P04` | Filtro Débito Auto = Sí | ⚠️ BLOCKED | 40959 ms |

| `P05` | Filtro Corredor | ❌ FAIL | 29993 ms |


---


## Fallas detectadas


### ❌ P01 — P01

**Mensaje**: Error: P01: página debe contener "RUC"

    [2mexpect([22m[31mlocator[39m[2m).[22mtoContainText[2m([22m[32mexpected[39m[2m)[22m failed

    Locator: locator('body')
    Timeout: 5000ms
    [32m- Expected substring  -   1[39m
    [31m+ Received string     + 203[39m

    [32m- RUC[39


| | Valor |
|---|---|
| **Esperado** | `substring  -   1[39m
    [31m+` |
| **Actual** | `string     + 203[39m

    [32m- RUC[39m
    [31m+[39m
    [31m+ [43m    [49m[39m
    [31m+` |



**Trace Playwright**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\step_00_setup.png`


---


### ❌ P03 — P03

**Mensaje**: RUNTIME_ERROR




**Trace Playwright**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\step_00_setup.png`


---


### ❌ P04 — P04

**Mensaje**: RUNTIME_ERROR




**Trace Playwright**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\step_00_setup.png`


---


### ❌ P05 — P05

**Mensaje**: Oracle 'table_agenda_usu' (tipo=count_eq) expected='0' actual='1'


| | Valor |
|---|---|
| **Esperado** | `0` |
| **Actual** | `1` |




**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P05\step_00_setup.png`


---




---

## Evidencia por escenario


### P01 — Búsqueda sin filtros + validación de nuevas columnas

**Estado**: ⚠️ BLOCKED (evaluator_inconclusive)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\step_01_after.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P01\test_failure.png`







**Assertions fallidas**:

- `Error: P01: página debe contener "RUC"

    [2mexpect([22m[31mlocator[39m[2m).[22mtoContainText[2m([22m[32mexpected[39m[2m)[22m failed

    Locator: locator('body')
    Timeout: 5000ms
    [32m- Expected substring  -   1[39m
    [31m+ Received string     + 203[39m

    [32m- RUC[39` — Esperado: `substring  -   1[39m
    [31m+` | Actual: `string     + 203[39m

    [32m- RUC[39m
    [31m+[39m
    [31m+ [43m    [49m[39m
    [31m+`



---


### P03 — Filtro Débito Auto = No

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P03\test_failure.png`








---


### P04 — Filtro Débito Auto = Sí

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P04\test_failure.png`








---


### P05 — Filtro Corredor

**Estado**: ❌ FAIL


**Artefactos**:



- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P05\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P05\step_01_after.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P05\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\72\P05\test_failure.png`







**Assertions fallidas**:

- `Oracle 'table_agenda_usu' (tipo=count_eq) expected='0' actual='1'` — Esperado: `0` | Actual: `1`



---



## Recomendaciones para el QA humano



- Verifica que la página muestre correctamente el texto 'RUC' según los requisitos.

- Revisa los errores de tiempo de ejecución (RUNTIME_ERROR) en los casos P03 y P04 para identificar posibles problemas de código o configuración.

- Asegúrate de que la tabla 'table_agenda_usu' esté vacía cuando se espera, revisando los datos de prueba y el proceso de limpieza antes de ejecutar los tests.



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

_Generado por Stacky Agents — QA UAT Pipeline v1.2.0 — Run `6b87d1e1-49e0-43b8-900b-69e4e5ae769d`_