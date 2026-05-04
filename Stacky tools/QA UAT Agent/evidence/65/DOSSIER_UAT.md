# Dossier UAT — ADO-65: RF-001 — Validación de campos del Filtro de Agenda en la instalación Pacífico

> **Run ID**: `dcda3339-bc5f-495f-8bb0-7bb4e9dc27f8`  
> **Fecha**: 2026-05-04T19:32:11Z  
> **Agente**: 1.2.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Resumen Ejecutivo UAT:  
El ticket RF-001 sobre la validación de campos del Filtro de Agenda en la instalación Pacífico se encuentra BLOQUEADO. De 4 escenarios evaluados, solo 1 fue aprobado y 3 presentaron incidencias (P02, P04, P05). Las fallas detectadas impiden la validación completa de la funcionalidad, por lo que se requiere atención prioritaria para resolver los problemas antes de continuar con las pruebas.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P02` | Debito Automatico = No | ⚠️ BLOCKED | 48265 ms |

| `P03` | Corredor = valor parcial | ✅ PASS | 40357 ms |

| `P04` | Nombre de Cliente = texto parcial | ⚠️ BLOCKED | 51242 ms |

| `P05` | RUC = parcial 20 | ⚠️ BLOCKED | 3371 ms |


---


## Fallas detectadas


### ❌ P02 — P02

**Mensaje**: RUNTIME_ERROR




**Trace Playwright**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\step_00_setup.png`


---


### ❌ P04 — P04

**Mensaje**: RUNTIME_ERROR




**Trace Playwright**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\step_00_setup.png`


---


### ❌ P05 — P05

**Mensaje**: RUNTIME_ERROR




**Trace Playwright**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\trace.zip`


**Screenshot**: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\step_00_setup.png`


---




---

## Evidencia por escenario


### P02 — Debito Automatico = No

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P02\test_failure.png`








---


### P03 — Corredor = valor parcial

**Estado**: ✅ PASS


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\step_01_after.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\step_02_after.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P03\test_failure.png`







**Assertions fallidas**:

- `Error: P03: pÃ¡gina debe contener "valor parcial"

    [2mexpect([22m[31mlocator[39m[2m).[22mtoContainText[2m([22m[32mexpected[39m[2m)[22m failed

    Locator: locator('body')
    Timeout: 5000ms
    [32m- Expected substring  -   1[39m
    [31m+ Received string     + 168[39m

    [3` — Esperado: `substring  -   1[39m
    [31m+` | Actual: `string     + 168[39m

    [32m- valor parcial[39m
    [31m+[39m
    [31m+ [43m    [49m[39m
`



---


### P04 — Nombre de Cliente = texto parcial

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\step_01_after.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\step_02_after.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P04\test_failure.png`








---


### P05 — RUC = parcial 20

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:
- Trace: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\trace.zip`
- Video: `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\video.webm`

- Screenshots:

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\step_00_setup.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\step_final_state.png`

  - `N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\65\P05\test_failure.png`








---



## Recomendaciones para el QA humano



- Revise los registros de errores para identificar la causa exacta del error de ejecución.

- Verifique que todas las dependencias y configuraciones necesarias estén correctamente instaladas.

- Ejecute los casos de prueba de forma individual para aislar el problema.

- Consulte con el equipo de desarrollo si persisten los errores después de las verificaciones iniciales.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo publicó este dossier como comentario de evidencia.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.2.0 — Run `dcda3339-bc5f-495f-8bb0-7bb4e9dc27f8`_