# Plan: Data Gate Pre-Playwright para QA UAT Ticket 120

## Resumen

Crear un documento Markdown para guiar a cualquier desarrollador agentico, sin contexto previo, en la implementación de un gate de datos obligatorio antes de ejecutar Playwright en el Stacky QA UAT Agent.

Archivo sugerido:

`Tools/Stacky/Stacky tools/QA UAT Agent/PLAN_pre_playwright_data_gate_ticket_120.md`

El objetivo es que el pipeline verifique la data necesaria para el ticket 120 antes de abrir el navegador. Si faltan datos, debe generar artifacts accionables para el humano, incluyendo scripts SQL seguros de seed cuando aplique, detenerse con `BLOCKED DATA`, y permitir que el humano continúe el test luego de preparar la data.

## Contenido Del Markdown

El archivo debe incluir estas secciones:

- **Contexto funcional**
  - Ticket 120 valida RF-007 en `FrmDetalleClie.aspx`, grilla de obligaciones.
  - El último run logró `PASS_STRUCTURAL`, pero no `PASS_VALUE_ASSERTIONS`.
  - La evidencia muestra que faltan datos batch para validar valores reales en columnas como `OGCANAL`, `OGMEDIOPAGO`, `OGTIENEDEBITOAUTO`, `DESALDOFAVOR`, `OGCUOTA`, `OGMONTOCUOTA`.
  - Playwright no debe ejecutarse si esos datos no están listos.

- **Estado actual del agente**
  - `qa_uat_pipeline.py` ya tiene etapas de `data_contract_compile`, `data_readiness_v2`, `data_resolution_broker` y `sql_seed_proposal`.
  - El problema actual es de orquestación: el pipeline puede bloquear demasiado temprano o continuar sin garantizar data lista.
  - El gate debe quedar antes de `playwright_test_generator` y `uat_test_runner`.

- **Diseño propuesto**
  - Agregar una decisión explícita `pre_playwright_data_gate`.
  - Orden requerido:
    `scenario_compiler -> data_contract_compile -> data_readiness_v2 -> data_resolution_broker -> sql_seed_proposal -> pre_playwright_data_gate -> playwright_generator -> runner`.
  - Playwright solo arranca si `pre_playwright_data_gate.decision == READY`.
  - Si falta data:
    - generar `data_readiness_v2_*.json`;
    - generar `data_resolution_request*.json`;
    - generar `seed_proposal_*.sql` y `cleanup_proposal_*.sql` cuando sea seedable;
    - devolver `BLOCKED DATA`;
    - incluir `playwright_started=false`.

- **Contrato de datos específico para ticket 120**
  - El contrato debe validar:
    - cliente navegable desde `FrmBusqueda.aspx`;
    - obligación visible en `GridObligaciones`;
    - headers `RIDIOMA/RCONTROLES` `9305..9312`;
    - valores no vacíos o coherentes para las columnas RF-007;
    - vínculo suficiente entre `ROBLG`, `RDEUDA` y `RCUOTAS` para validar cuotas, saldo y monto.
  - El contrato no debe conformarse con “hay una obligación”; debe distinguir `PASS_STRUCTURAL` de `PASS_VALUE_ASSERTIONS`.

- **Flujo humano**
  - Si el gate bloquea, el humano revisa los artifacts.
  - Si hay SQL seed, el humano revisa el script, valida el hash y decide si ejecutarlo en QA.
  - El script debe venir con `ROLLBACK TRANSACTION` activo y `-- COMMIT TRANSACTION` comentado.
  - Luego el humano relanza el pipeline completo o usa un futuro flag `--continue-after-data`.
  - Antes de Playwright, el gate debe consultar nuevamente la DB en modo read-only.

## Cambios De Implementación

- En `qa_uat_pipeline.py`, mover el bloqueo definitivo a una nueva etapa `pre_playwright_data_gate`.
- No retornar inmediatamente desde `data_readiness_v2` si hay missing data; primero permitir broker y seed proposal.
- Enriquecer `uat_data_contract_compiler.py` para RF-007/ticket 120 con requisitos de valores reales.
- Enriquecer `data_readiness_checker.py` para producir un candidato usable o una lista precisa de faltantes.
- Mantener `sql_seed_generator.py` y `sql_safety_validator.py` como fuente de scripts seguros, sin ejecución automática.
- Registrar artifacts y eventos con nombres claros para que otro agente pueda continuar sin leer prompts previos.

## Criterios De Aceptación

- Si falta data RF-007, Playwright no arranca.
- El resultado incluye `verdict=BLOCKED`, `category=DATA`, `failed_stage=pre_playwright_data_gate`.
- El resultado incluye `playwright_started=false`.
- Si la data faltante es seedable, se generan scripts SQL seguros.
- Si la data ya existe, el gate pasa a `READY` y Playwright ejecuta normalmente.
- El dossier final no publica `PASS` completo si solo hubo validación estructural.
- Los tests cubren:
  - data lista;
  - data faltante seedable;
  - data faltante no seedable;
  - DB no disponible;
  - SQL safety failed;
  - relanzamiento después de seed humano.

## Supuestos

- Ambiente objetivo por defecto: `QA`.
- No se ejecutará DML automáticamente desde el agente.
- Todo seed requiere revisión humana.
- El plan debe escribirse como documentación implementable, no como cambios de código todavía.
- El archivo Markdown será creado cuando se salga de Plan Mode y se habilite ejecución/mutación.
