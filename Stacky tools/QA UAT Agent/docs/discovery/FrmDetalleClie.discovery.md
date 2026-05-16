# Discovery de FrmDetalleClie

Fecha: 2026-05-13
Origen: discovery estatico sobre `trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx*`.
Estado: aplicado como baseline QAUAT, pendiente de validacion runtime con Playwright/browser.

## Resumen

`FrmDetalleClie.aspx` es la pantalla principal de detalle/ficha de cliente en AgendaWeb. Carga el cliente desde `Session["lote"]`, muestra datos generales, obligaciones, deuda, gestiones, relaciones, contactos, pagos, garantias, scoring e historicos. Tambien concentra acciones operativas: ejecutar TAR, agendar, gestionar compromisos de pago, convenios, pasaje judicial, documentos, notas, ficha, cheques y exportaciones.

Existe una variante reducida en `trunk/OnLine/AutoGestion/FrmDetalleClie.aspx`; este baseline QAUAT cubre la version `AgendaWeb`.

## Fuentes Analizadas

- `trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx`
- `trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx.cs`
- `trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx.designer.cs`
- `trunk/OnLine/Negocio/RSFac/Cliente.cs`
- `trunk/OnLine/Negocio/RSFac/Obligaciones.cs`
- `trunk/OnLine/Negocio/RSFac/Convenio.cs`
- `trunk/OnLine/Negocio/RSFac/Promesa.cs`
- `trunk/OnLine/Negocio/RSFac/Ejecutar.cs`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_detalle_cliente_from_busqueda.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/flows/cliente_flow.ts`

## Navegacion

Entradas detectadas:

- `FrmBusqueda.aspx` selecciona cliente/obligacion y redirige a `FrmDetalleClie.aspx`.
- `FrmAgenda.aspx` redirige con filtros de agenda en query string.
- `FrmAgendaEquipo.aspx`, `FrmJDemanda.aspx` y `FrmSimulacionUnitaria.aspx` tambien redirigen a detalle.
- `AutoGestion/FrmLogin.aspx` redirige a su propia version `AutoGestion/FrmDetalleClie.aspx`.

Precondicion principal: `Session["lote"]` debe contener el codigo de cliente. El deeplink por `clcod` debe validarse antes de usarse como ruta UAT confiable.

## Campos y Controles Principales

- Header cliente: `abfApellidoNombre`, `abfUsuario`, `abfDocumento`, `abfPerfil`, `abfNumCliente`, `abfNivelMora`, `abfCategoriaCliente`, `abfTipoCliente`, `abfCorredorPrincipal`, `abfRiesgoCliente`, `abfAtrasoTotal`.
- Acciones superiores: `btnCompromisos`, `btnConvenios`, `btnEstado`, `btnChequesProtestados`, `btnPasajeJudicial`, `btnJudicial`, `btnDocumento`, `btnFicha`, `btnNotas`.
- Tabs: `tabGenerales`, `tabRelaciones`, `tabContactos`, `tabPagos`, `tabGarantias`, `tabScorings`, `tabHistoricos`.
- Footer Accion/Agendar: `ddlAccionEjecutar`, `ddlFigura`, `ddlObligacion`, `btnNotaEjecutar`, `ddlAccionAgendar`, `abfFecha`, `abfHora`, `ddlDestino`, `ddlUsuarios`, `ddlFiguraAgendar`, `btnNotaAgendar`, `btnEjecutar`.

## Acciones Detectadas

Acciones read-only o de apertura:

- Abrir detalle cliente: carga `CargoDatosPagina`, `CargoBloqueAgendar`, `OcultarOtros`.
- Cambiar tab: `TabControl_SelectedIndexChanged`.
- Seleccionar obligacion: `GridObligaciones_SelectedIndexChanged`.
- Abrir compromisos: `btnCompromisos_Click`.
- Abrir convenios: `btnConvenios_Click`.
- Abrir estados especiales: `btnEstado_Click`.
- Abrir cheques: `btnChequesProtestados_Click`.
- Abrir pasaje judicial: `btnPasajeJudicial_Click`.
- Ver judicial/demanda: `btnJudicial_Click`, `btnVerDemanda_Click`.
- Abrir documentos: `btnDocumento_Click`, `btnDocumentacion_Click`.
- Abrir notas/comentarios: `btnNotas_Click`, `btnVerComentariosGestion_Click`.
- Ver producto analitico desde obligaciones: `GridObligaciones_RowCommand`.
- Exportar grillas: multiples `btnExport..._Click`.

Acciones que mutan datos y requieren dataset/cleanup aprobados:

- Ejecutar accion/agendar: `btnEjecutar_Click` usa `RSFac.Ejecutar.EjecutarAccion`.
- Guardar compromisos: `btnGuardarModalCompromisos_Click` usa `RSFac.Ejecutar.GuardarCompromisos`.
- Guardar/anular convenio: `btnGuardarCuotas_Click`, `btnAnularConvenio_Click`.
- Judicializar: `btnAceptarCliente_Click` / `Generar`.
- CRUD contactos, telefonos, emails, domicilios y garantias.
- Guardar comentarios/notas de gestion.

## Servicios y Datos

- `RSFac.Cliente`: cliente, lote, alertas, relaciones, contactos, telefonos, emails, domicilios, garantias, cheques, estados, ficha, corredor principal.
- `RSFac.Obligaciones`: obligaciones, deuda, gestiones, pagos, historicos, demanda por obligacion, datos de producto.
- `RSFac.Promesa`: promesas, obligaciones/cuotas para promesa.
- `RSFac.Convenio`: obligaciones para convenio, cuotas, grabacion y anulacion.
- `RSFac.Ejecutar`: ejecucion de accion, agenda y guardado de compromisos.
- `RSFac.Usuario`: permisos funcionales.

## Permisos y Condiciones

- `btnPasajeJudicial`: `Permisos.Pasaje_Judicial`.
- `btnJudicial`: `Permisos.Ver_Caso_Judicial` y tambien se oculta si falta `Pasaje_Judicial`.
- `btnFicha`: `Permisos.Generar_Ficha_Cliente`.
- `btnConvenios`: `Permisos.Ver_Convenio` o `Permisos.Generar_Convenio`.
- `btnGuardarCuotas` y `btnAnularConvenio`: requieren generar convenio y gestionar caso asignado/no asignado.
- `btnCompromisos` y promesas: dependen de permisos de compromisos y gestion del caso.
- `colAccionEjecutar`: depende de usuario gestor o permiso para gestionar casos no asignados.
- `btnEstado`: visible solo si `Cliente.TieneEstadosEspeciales`.
- `btnChequesProtestados`: visible solo si `Cliente.TieneCheques`.

## Artefactos QAUAT Aplicados

- UIMap baseline: `cache/ui_maps/FrmDetalleClie.aspx.json`.
- Playbook de navegacion actualizado: `cache/playbooks/open_detalle_cliente_from_busqueda.json`.
- Playbook de acciones nuevo: `cache/playbooks/frm_detalle_clie_actions.json`.
- Flow/Page Object extendido: `playwright/flows/cliente_flow.ts`.
- Spec read-only nuevo: `playwright/uat/frm_detalle_clie.spec.ts`.

## Validaciones Pendientes

- Captura runtime del UIMap para confirmar IDs y visibilidad real de controles AIS.
- Confirmar cliente QA con datos suficientes para obligaciones, compromisos, convenios, notas, cheques, garantias y judicial.
- Confirmar usuarios QA por matriz de permisos.
- Confirmar politica para tests que mutan datos y cleanup asociado.
- Confirmar si se requiere baseline separado para `AutoGestion/FrmDetalleClie.aspx`.
