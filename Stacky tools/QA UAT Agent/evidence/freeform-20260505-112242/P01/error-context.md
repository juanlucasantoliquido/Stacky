# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: freeform-20260505-112242\tests\P01_verificar_que_se_puede_agregar_un_nuevo_usuario_de.spec.ts >> ADO--1 | P01 — Verificar que se puede agregar un nuevo usuario desde el administrador >> p01 verificar_que_se_puede_agregar_un_nuevo_usuario_desde_el_adm
- Location: evidence\freeform-20260505-112242\tests\P01_verificar_que_se_puede_agregar_un_nuevo_usuario_de.spec.ts:72:7

# Error details

```
Error: P01: página debe contener "USQA01"

expect(locator).toContainText(expected) failed

Locator: locator('body')
Timeout: 5000ms
- Expected substring  -    1
+ Received string     + 1494

- USQA01
+
+     
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+
+ 	
+
+ 		
+ 	
+         
+
+         
+                 
+             
+         
+ 	
+                 
+
+ 	
+             
+
+         menulogoutSalirSeguridad PrejudicialUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:1Realizado Hoy:1Total en Agenda:2Barrido Realizado:50%Clientes Asignados:10430    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion Manualformat_list_bulletedReportes OperativosleaderboardInformesleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estados EspecialesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
+         
+             
+ 	
+                     
+                         
+                             chevron_leftadministrador
+                         
+                         
+                             
+                             
+                             
+                             
+                             
+                         
+                     
+                 
+
+             
+     
+ 	
+             
+ 		RolesUsuarios
+
+
+
+ 			
+                     
+                             
+                                 
+                                     
+ 	
+                                             
+                                                 
+ 		Roles
+ 	
+                                                 filter_altBuscar Roles 
+                                                 
+                                                     addAgregar Rol
+                                                     Jerarquía
+                                                     grid_onExportar
+                                                 
+                                             
+                                             
+                                                 
+                                                     
+ 		
+ 			
+ 				
+ 					 RolDescripción% Asignación
+ 				
+ 			
+ 				
+ 					radio_button_checkedBOTCBackoffice Tarjetas de Credito100
+ 				
+ 					radio_button_uncheckedINUBICBolson de Clientes Inubicables1100
+ 				
+ 					radio_button_uncheckedCCEXTCall Center Externo100
+ 				
+ 					radio_button_uncheckedCOBSRCobrador Senior100
+ 				
+ 					radio_button_uncheckedCOMJUDComite Judicial100
+ 				
+ 					radio_button_uncheckedTOTALControl Total 
+ 				
+ 					radio_button_uncheckedCONVEJConvenios Extrajudiciales95
+ 				
+ 					radio_button_uncheckedEJCOMEjecutivo Comercial 
+ 				
+ 					radio_button_uncheckedEMPEXTEmpresas Externas de Cobranzas25
+ 				
+ 					radio_button_uncheckedGCCENGerente Casa Central 
+ 				
+ 					radio_button_uncheckedGCGerente de Cobranzas 
+ 				
+ 					radio_button_uncheckedGERSUCGerente de Sucursal105
+ 				
+ 					radio_button_uncheckedATMSGestion ATM (Cajero Automatico)100
+ 				
+ 					radio_button_uncheckedAUTOPAGestion Autopago2
+ 				
+ 					radio_button_uncheckedCARTASGestion Cartas 
+ 				
+ 					radio_button_uncheckedEMAILGestion Email 
+ 				
+ 					radio_button_uncheckedNOMORAGestion No Mora1
+ 				
+ 					radio_button_uncheckedSMSGestion SMS 
+ 				
+ 					radio_button_uncheckedGRAGestor de Recuperacion de Activos 
+ 				
+ 					radio_button_uncheckedJOPSUCJefe Operativo de Sucursal 
+ 				
+ 					radio_button_uncheckedJJudicial 
+ 				
+ 					radio_button_uncheckedMBOTMiembro Backoffice Tarjetas 
+ 				
+ 					radio_button_uncheckedMCONEJMiembro Conv Extrajudicial 
+ 				
+ 					radio_button_uncheckedMICJMiembro de Comite Judicial 
+ 				
+ 					radio_button_uncheckedMSINMiembro Gestion Siniestro 
+ 				
+ 					radio_button_uncheckedNUCLEONucleo Estrategico 
+ 				
+ 					radio_button_uncheckedOPCCOperador de Call Center 
+ 				
+ 					radio_button_uncheckedGESSINPool de Siniestros 
+ 				
+ 					radio_button_uncheckedPROGRAMADORPROGRAMADOR 
+ 				
+ 					radio_button_uncheckedRACRecurso de Apoyo a Cobranzas 
+ 				
+ 					radio_button_uncheckedRTESTRol de Test 
+ 				
+ 					radio_button_uncheckedSEGURSeguros 
+ 				
+ 					radio_button_uncheckedSKIPTSkip Trace 
+ 				
+ 					radio_button_uncheckedAISSoporte AIS149
+ 				
+ 					radio_button_uncheckedSUPCCSupervisor Call Center 
+ 				
+ 			
+
+ 			
+ 		
+ 	
+                                                     
+                                                 
+                                             
+                                         
+
+                                     
+ 	
+                                             
+                                                 
+ 		Usuarios
+ 	
+                                                 
+                                                     visibilityConsultar
+                                                     createModificar
+                                                     deleteEliminar
+                                                 
+                                             
+                                             
+                                                 
+                                                     
+ 		
+ 			
+ 				
+ 					 CódigoDescripción
+ 				
+ 			
+ 				
+ 					radio_button_checked122
+ 				
+ 					radio_button_uncheckedAAAEAAAE
+ 				
+ 					radio_button_uncheckedddggddg
+ 				
+ 					radio_button_uncheckedJAYJAY
+ 				
+ 					radio_button_uncheckedPABLOUSUARIO TEST
+ 				
+ 					radio_button_uncheckedPABLO4PABLO44
+ 				
+ 					radio_button_uncheckedSUPERMANSUPERMAN
+ 				
+ 					radio_button_uncheckedVARELACVARELA CARLOS  ESTUDIO VARELA
+ 				
+ 					radio_button_uncheckedVILLARVILLAR JUAN PABLO
+ 				
+ 					radio_button_uncheckedWILLIMANWILLIMAN JOSE
+ 				
+ 					radio_button_uncheckedYANEZYA?`EZ RODOLFO
+ 				
+ 					radio_button_uncheckedYANEZAYAÑEZ ALVARO
+ 				
+ 			
+
+ 			
+ 		
+ 	
+                                                     
+                                                 
+                                             
+                                         
+
+                                 
+                                 
+                                     
+ 	
+                                         
+ 		
+                                                 
+                                                     
+                                                         
+                                                             
+ 			Modulos Disponibles
+ 		
+                                                         
+                                                         
+                                                             Seleccionar Todos
+                                                             
+                                                                 addAñadir Permiso
+                                                                 grid_onExportar
+                                                             
+                                                         
+                                                         
+                                                             
+                                                                 
+ 			
+                                                                         
+ 				
+ 					
+ 						10 - Cobranza Prejudicial
+ 					
+ 				
+ 					
+ 						
+ 							11 - Agenda Personal
+ 						
+ 					
+ 						
+ 							12 - Busqueda de Clientes
+ 						
+ 					
+ 						
+ 							
+ 								265 - Ver Solo Casos del Mismo Empleador
+ 							
+ 						
+ 							
+ 								267 - Ver Todos Los Casos
+ 							
+ 						
+ 					
+ 						
+ 							120 - Detalle de Cliente
+ 						
+ 					
+ 						
+ 							
+ 								122 - Ver Compromisos
+ 							
+ 						
+ 							
+ 								123 - Generar Compromisoso
+ 							
+ 						
+ 							
+ 								124 - Generar Convenio
+ 							
+ 						
+ 							
+ 								125 - Ver caso judicial
+ 							
+ 						
+ 							
+ 								126 - Ver Ficha
+ 							
+ 						
+ 							
+ 								25 - Convenios
+ 							
+ 						
+ 							
+ 								26 - Pasaje a Judicial
+ 							
+ 						
+ 							
+ 								366 - Gestionar Casos No Asignados
+ 							
+ 						
+ 					
+ 						
+ 							13 - Supervision
+ 						
+ 					
+ 						
+ 							
+ 								14 - Reasignacion Manual
+ 							
+ 						
+ 					
+ 						
+ 							15 - Reportes Operativos
+ 						
+ 					
+ 						
+ 							
+ 								17 - Distribución por Tipologia de Clientes
+ 							
+ 						
+ 							
+ 								18 - Distribución por Estrategia
+ 							
+ 						
+ 							
+ 								19 - Call Center
+ 							
+ 						
+ 							
+ 								22 - Distribución por Estados Especiales
+ 							
+ 						
+ 							
+ 								23 - Distribución por Rol y Nivel de Mora
+ 							
+ 						
+ 							
+ 								27 - otros Reportes
+ 							
+ 						
+ 							
+ 								74 - Informes
+ 							
+ 						
+ 					
+ 						
+ 							20 - Agenda de Grupo
+ 						
+ 					
+ 						
+ 							24 - Pooles de Trabajo
+ 						
+ 					
+ 						
+ 							320 - Reportes OBI
+ 						
+ 					
+ 						
+ 							
+ 								321 - Resumen Agenda
+ 							
+ 						
+ 							
+ 								322 - Gestión Rol y N.Mora
+ 							
+ 						
+ 							
+ 								323 - Gest. Tipo Cliente y N.Mora
+ 							
+ 						
+ 							
+ 								324 - Gest. Estrategia y N.Mora
+ 							
+ 						
+ 							
+ 								325 - Promeas de Pago
+ 							
+ 						
+ 							
+ 								326 - Risk Management
+ 							
+ 						
+ 					
+ 				
+ 					
+ 						200 - Administrador
+ 					
+ 				
+ 					
+ 						
+ 							201 - Administración
+ 						
+ 					
+ 						
+ 							
+ 								202 - Oficinas
+ 							
+ 						
+ 							
+ 								203 - Productos
+ 							
+ 						
+ 							
+ 								204 - Festivos
+ 							
+ 						
+ 							
+ 								205 - Tablas Generales
+ 							
+ 						
+ 							
+ 								
+ 									362 - Crear y Modificar Roles
+ 								
+ 							
+ 						
+ 							
+ 								206 - Conversión Monetaria
+ 							
+ 						
+ 							
+ 								207 - Multi-Mandante
+ 							
+ 						
+ 							
+ 								
+ 									208 - Mandantes
+ 								
+ 							
+ 								
+ 									209 - Tablas Generales Multi-Mandante
+ 								
+ 							
+ 						
+ 							
+ 								211 - Comisiones y Honorarios
+ 							
+ 						
+ 							
+ 								276 - Variables de Priorización de Agenda
+ 							
+ 						
+ 							
+ 								277 - Parámetros
+ 							
+ 						
+ 					
+ 						
+ 							250 - Seguridad
+ 						
+ 					
+ 						
+ 							
+ 								251 - Administración de Usuarios
+ 							
+ 						
+ 							
+ 								
+ 									358 - Edición de Usuarios
+ 								
+ 							
+ 								
+ 									360 - Gestionar Permisos Roles
+ 								
+ 							
+ 						
+ 							
+ 								252 - Parametría de Seguridad
+ 							
+ 						
+ 							
+ 								275 - Administración de Usuarios Judicial
+ 							
+ 						
+ 							
+ 								285 - Administración de Comisionistas
+ 							
+ 						
+ 					
+ 						
+ 							263 - Estrategia
+ 						
+ 					
+ 						
+ 							
+ 								260 - Judicial
+ 							
+ 						
+ 							
+ 								
+ 									274 - Edición de TARs
+ 								
+ 							
+ 								
+ 									287 - Vinculación de Variables a GMR
+ 								
+ 							
+ 								
+ 									344 - Diseñador de procedimientos judiciales
+ 								
+ 							
+ 						
+ 							
+ 								272 - Prejudicial
+ 							
+ 						
+ 							
+ 								
+ 									262 - Edición de TARs
+ 								
+ 							
+ 								
+ 									
+ 										359 - Asignar Permisos uso TARs
+ 									
+ 								
+ 							
+ 								
+ 									264 - Diseñador de Flujos
+ 								
+ 							
+ 								
+ 									273 - Edición de Estrategias
+ 								
+ 							
+ 								
+ 									286 - Vinculación de Variables a GMR
+ 								
+ 							
+ 								
+ 									290 - Generar Archivo GMR Plus
+ 								
+ 							
+ 								
+ 									310 - Simulador de Estrategias
+ 								
+ 							
+ 								
+ 									311 - Diagnóstico de Evaluación
+ 								
+ 							
+ 								
+ 									341 - Simulador
+ 								
+ 							
+ 								
+ 									
+ 										340 - Simulaciones unitarias
+ 									
+ 								
+ 									
+ 										342 - Simulaciones masivas
+ 									
+ 								
+ 							
+ 						
+ 					
+ 						
+ 							300 - Herramientas
+ 						
+ 					
+ 						
+ 							
+ 								301 - Generar Cartas...
+ 							
+ 						
+ 							
+ 								302 - Generar Fichas de Cobranzaa?|
+ 							
+ 						
+ 							
+ 								303 - Gestión de Nuevos Campos
+ 							
+ 						
+ 					
+ 				
+ 					
+ 						52 - Otras Funcionalidades
+ 					
+ 				
+ 					
+ 						
+ 							108 - Añadir ficheros a Gestión
+ 						
+ 					
+ 				
+ 			
+                                                                     
+ 		
+                                                             
+                                                         
+                                                     
+                                                     
+                                                         
+                                                             
+ 			Modulos Otorgados
+ 		
+                                                         
+                                                         
+                                                             Seleccionar Todos
+                                                             
+                                                                 deleteQuitar Permiso
+                                                             
+                                                         
+                                                         
+                                                             
+                                                                 
+ 			
+                                                                         
+ 				
+ 					
+ 						10 - Cobranza Prejudicial
+ 					
+ 				
+ 					
+ 						
+ 							11 - Agenda Personal
+ 						
+ 					
+ 						
+ 							12 - Busqueda de Clientes
+ 						
+ 					
+ 						
+ 							
+ 								265 - Ver Solo Casos del Mismo Empleador
+ 							
+ 						
+ 							
+ 								267 - Ver Todos Los Casos
+ 							
+ 						
+ 					
+ 						
+ 							120 - Detalle de Cliente
+ 						
+ 					
+ 						
+ 							
+ 								122 - Ver Compromisos
+ 							
+ 						
+ 							
+ 								123 - Generar Compromisoso
+ 							
+ 						
+ 							
+ 								124 - Generar Convenio
+ 							
+ 						
+ 							
+ 								125 - Ver caso judicial
+ 							
+ 						
+ 							
+ 								126 - Ver Ficha
+ 							
+ 						
+ 							
+ 								25 - Convenios
+ 							
+ 						
+ 							
+ 								26 - Pasaje a Judicial
+ 							
+ 						
+ 							
+ 								366 - Gestionar Casos No Asignados
+ 							
+ 						
+ 					
+ 						
+ 							13 - Supervision
+ 						
+ 					
+ 						
+ 							
+ 								14 - Reasignacion Manual
+ 							
+ 						
+ 					
+ 						
+ 							15 - Reportes Operativos
+ 						
+ 					
+ 						
+ 							
+ 								17 - Distribución por Tipologia de Clientes
+ 							
+ 						
+ 							
+ 								18 - Distribución por Estrategia
+ 							
+ 						
+ 							
+ 								19 - Call Center
+ 							
+ 						
+ 							
+ 								22 - Distribución por Estados Especiales
+ 							
+ 						
+ 							
+ 								23 - Distribución por Rol y Nivel de Mora
+ 							
+ 						
+ 							
+ 								27 - otros Reportes
+ 							
+ 						
+ 							
+ 								74 - Informes
+ 							
+ 						
+ 					
+ 						
+ 							20 - Agenda de Grupo
+ 						
+ 					
+ 						
+ 							24 - Pooles de Trabajo
+ 						
+ 					
+ 				
+ 					
+ 						200 - Administrador
+ 					
+ 				
+ 					
+ 						
+ 							201 - Administración
+ 						
+ 					
+ 						
+ 							
+ 								202 - Oficinas
+ 							
+ 						
+ 							
+ 								203 - Productos
+ 							
+ 						
+ 							
+ 								204 - Festivos
+ 							
+ 						
+ 							
+ 								205 - Tablas Generales
+ 							
+ 						
+ 							
+ 								
+ 									362 - Crear y Modificar Roles
+ 								
+ 							
+ 						
+ 							
+ 								206 - Conversión Monetaria
+ 							
+ 						
+ 							
+ 								207 - Multi-Mandante
+ 							
+ 						
+ 							
+ 								
+ 									208 - Mandantes
+ 								
+ 							
+ 								
+ 									209 - Tablas Generales Multi-Mandante
+ 								
+ 							
+ 						
+ 							
+ 								211 - Comisiones y Honorarios
+ 							
+ 						
+ 							
+ 								276 - Variables de Priorización de Agenda
+ 							
+ 						
+ 							
+ 								277 - Parámetros
+ 							
+ 						
+ 					
+ 						
+ 							250 - Seguridad
+ 						
+ 					
+ 						
+ 							
+ 								251 - Administración de Usuarios
+ 							
+ 						
+ 							
+ 								
+ 									358 - Edición de Usuarios
+ 								
+ 							
+ 								
+ 									360 - Gestionar Permisos Roles
+ 								
+ 							
+ 						
+ 							
+ 								252 - Parametría de Seguridad
+ 							
+ 						
+ 							
+ 								275 - Administración de Usuarios Judicial
+ 							
+ 						
+ 							
+ 								285 - Administración de Comisionistas
+ 							
+ 						
+ 					
+ 						
+ 							263 - Estrategia
+ 						
+ 					
+ 						
+ 							
+ 								260 - Judicial
+ 							
+ 						
+ 							
+ 								
+ 									274 - Edición de TARs
+ 								
+ 							
+ 								
+ 									287 - Vinculación de Variables a GMR
+ 								
+ 							
+ 								
+ 									344 - Diseñador de procedimientos judiciales
+ 								
+ 							
+ 						
+ 							
+ 								272 - Prejudicial
+ 							
+ 						
+ 							
+ 								
+ 									262 - Edición de TARs
+ 								
+ 							
+ 								
+ 									
+ 										359 - Asignar Permisos uso TARs
+ 									
+ 								
+ 							
+ 								
+ 									264 - Diseñador de Flujos
+ 								
+ 							
+ 								
+ 									273 - Edición de Estrategias
+ 								
+ 							
+ 								
+ 									286 - Vinculación de Variables a GMR
+ 								
+ 							
+ 								
+ 									290 - Generar Archivo GMR Plus
+ 								
+ 							
+ 						
+ 					
+ 						
+ 							300 - Herramientas
+ 						
+ 					
+ 						
+ 							
+ 								301 - Generar Cartas...
+ 							
+ 						
+ 							
+ 								302 - Generar Fichas de Cobranzaa?|
+ 							
+ 						
+ 							
+ 								303 - Gestión de Nuevos Campos
+ 							
+ 						
+ 					
+ 				
+ 					
+ 						343 - SEPARADOR
+ 					
+ 				
+ 					
+ 						52 - Otras Funcionalidades
+ 					
+ 				
+ 					
+ 						
+ 							108 - Añadir ficheros a Gestión
+ 						
+ 					
+ 				
+ 			
+                                                                     
+ 		
+                                                             
+                                                         
+                                                     
+                                                 
+                                             
+ 	
+                                     
+
+                                 
+                             
+                         
+                 
+ 		
+ 			
+                     
+                             
+                                 
+                                     
+ 	
+                                         
+                                             Ver Usuarios dados de Baja
+                                             filter_altBuscar Usuarios 
+                                             
+                                                 grid_onUsuarios
+                                             
+                                         
+                                         
+                                             
+                                                 
+ 		
+                                                         
+ 			
+ 				
+ 					
+ 						 CódigoDescripción
+ 					
+ 				
+ 					
+ 						radio_button_checked122
+ 					
+ 						radio_button_unchecked1011
+ 					
+ 						radio_button_unchecked233
+ 					
+ 						radio_button_unchecked344
+ 					
+ 						radio_button_unchecked444
+ 					
+ 						radio_button_unchecked566
+ 					
+ 						radio_button_unchecked5001
+ 					
+ 						radio_button_unchecked501501
+ 					
+ 						radio_button_unchecked600AIS PROGRAMADOR 1
+ 					
+ 						radio_button_unchecked899
+ 					
+ 						radio_button_unchecked800Jefe de proyecto 1
+ 					
+ 						radio_button_uncheckedA100A 100
+ 					
+ 						radio_button_uncheckedaaaatest
+ 					
+ 						radio_button_uncheckedAAAEAAAE
+ 					
+ 						radio_button_uncheckedAAAFAAAF
+ 					
+ 						radio_button_uncheckedAAAGAAAG
+ 					
+ 						radio_button_uncheckedAAARAAAR
+ 					
+ 						radio_button_uncheckedAABAAABA
+ 					
+ 						radio_button_uncheckedAABBAABB
+ 					
+ 						radio_button_uncheckedAABCAABC
+ 					
+ 						radio_button_uncheckedAACCaaa
+ 					
+ 						radio_button_uncheckedAISMMMireia (AIS)
+ 					
+ 						radio_button_uncheckedANDAN22
+ 					
+ 						radio_button_uncheckedARRIETAARRIETA PABLO
+ 					
+ 						radio_button_uncheckedASDASD
+ 					
+ 						radio_button_uncheckedBACHECHIBACHECHI, GONZALO  ESTUDIO BACHECHI441
+ 					
+ 						radio_button_uncheckedBANYASZBANYASZ FLORENCIA1
+ 					
+ 						radio_button_uncheckedBARCIALBARCIA, Lucía
+ 					
+ 						radio_button_uncheckedBARQUINBARQUIN VALIENTE, ALFONSO 
+ 					
+ 						radio_button_uncheckedBELENBELEN MANUEL
+ 					
+ 						radio_button_uncheckedBELLAGAMBABELLAGAMBA FABRICIO1
+ 					
+ 						radio_button_uncheckedBERRIELBERRIEL FIORELLA11123123
+ 					
+ 						radio_button_uncheckedBOCCARDIBOCCARDI DIEGO
+ 					
+ 						radio_button_uncheckedBOLSASUSUARIO TEST 2
+ 					
+ 						radio_button_uncheckedC}
+ 					
+ 						radio_button_uncheckedCALLORDACALLORDA PEREZ, Eliana Paula
+ 					
+ 						radio_button_uncheckedCASAGRANDECASAGRANDE MAURICIO
+ 					
+ 						radio_button_uncheckedCASTROMCASTRO MARTIN
+ 					
+ 						radio_button_uncheckedCAVIGLIACAVIGLIA OSCAR
+ 					
+ 						radio_button_uncheckedCGMYACGMyA
+ 					
+ 						radio_button_uncheckedCHARBONNIECHARBONNIER LISSETTE
+ 					
+ 						radio_button_uncheckedcjzouCaijie
+ 					
+ 						radio_button_uncheckedCOLLCOLL GONZALO2
+ 					
+ 						radio_button_uncheckedCOLOMBICOLOMBI MARCELO
+ 					
+ 						radio_button_uncheckedCOLOMBODCOLOMBO DANIEL
+ 					
+ 						radio_button_uncheckedCRESPICRESPI GONZALO
+ 					
+ 						radio_button_uncheckedCUADROCUADRO OVIEDO, Andrea Antonella
+ 					
+ 						radio_button_uncheckedddggddg
+ 					
+ 						radio_button_uncheckedDELEONLDE LEON LEONARDO
+ 					
+ 						radio_button_uncheckedDIAZSADÍAZ VARELA, Stefani Anabella
+ 					
+ 						radio_button_uncheckedESPESP
+ 					
+ 						radio_button_uncheckedESTIGARRIBESTIGARRIBIA SCALVINO, Victoria
+ 					
+ 						radio_button_uncheckedESTRELLADE MAR
+ 					
+ 						radio_button_uncheckedFERNANDEZMFERNANDEZ MARIA PIA
+ 					
+ 						radio_button_uncheckedFERNANDEZPFERNANDEZ PISCIOTTANO, Ana Camila
+ 					
+ 						radio_button_uncheckedFERREREFERRERE
+ 					
+ 						radio_button_uncheckedFERREYRAFERREYRA MASDEU, María Matilde
+ 					
+ 						radio_button_uncheckedFILLATFILLAT SOFIA
+ 					
+ 						radio_button_uncheckedFONTOURAFONTOURA MELLO, Maira Natalie
+ 					
+ 						radio_button_uncheckedFRECHOUFRECHOU FLORENCIA
+ 					
+ 						radio_button_uncheckedFUSTERFUSTER ALVARO
+ 					
+ 						radio_button_uncheckedGADEAGADEA MARIA NOEL
+ 					
+ 						radio_button_uncheckedGOMEZGOMEZ ANDRES
+ 					
+ 						radio_button_uncheckedGOMEZSGOMEZ PLATERO SOFIA
+ 					
+ 						radio_button_uncheckedGUSTAVOGUSTAVO
+ 					
+ 						radio_button_uncheckedGUTIERREZNGutierrez Bas, Natalia Vanessa
+ 					
+ 						radio_button_uncheckedHUERTASHUERTAS LAURA
+ 					
+ 						radio_button_uncheckedHUGOHUGO FERNANDEZ, JUAN PABLO 
+ 					
+ 						radio_button_uncheckedIZETTAIZETTA MAURICIO
+ 					
+ 						radio_button_uncheckedJAYJAY
+ 					
+ 						radio_button_uncheckedKEVINKEVIN
+ 					
+ 						radio_button_uncheckedLAGOSLAGOS MEDEIROS, Camila Yamisel
+ 					
+ 						radio_button_uncheckedLAPILAPI MARIA JOSE
+ 					
+ 						radio_button_uncheckedLOPEZCLOPEZ CAROLINA
+ 					
+ 						radio_button_uncheckedLoremLorem
+ 					
+ 						radio_button_uncheckedMANASMAÑAS ALEXIS
+ 					
+ 						radio_button_uncheckedMARINOMARIÑO IGNACIO
+ 					
+ 						radio_button_uncheckedMASSATMASSAT AGUSTINA
+ 					
+ 						radio_button_uncheckedMAYAMAYA AGUSTINA
+ 					
+ 						radio_button_uncheckedMIHALIKMIHALIK FERNANDO
+ 					
+ 						radio_button_uncheckedMIRANDAMIRANDA CARLOS
+ 					
+ 						radio_button_uncheckedMONTOSSIMONTOSSI RAUL
+ 					
+ 						radio_button_uncheckedMOREIRAMMOREIRA MARIA NOEL
+ 					
+ 						radio_button_uncheckedMOYPCMOyPC
+ 					
+ 						radio_button_uncheckedNBK1C2RMILES PAMELA
+ 					
+ 						radio_button_uncheckedNBK1O9HLIZARRAGA GONZALO
+ 					
+ 						radio_button_uncheckedNBK2PTMMOLINARI MARTIN
+ 					
+ 						radio_button_uncheckedNBK31EVTORNQUIST JORGE
+ 					
+ 						radio_button_uncheckedNBK34HLCORREA JORGE
+ 					
+ 						radio_button_uncheckedNBK54NSHERNANDEZ GUSTAVO
+ 					
+ 						radio_button_uncheckedNBK5TAQMASSEILOT JOAQUIN
+ 					
+ 						radio_button_uncheckedNBK68OWBARRIOS VERONICA112119
+ 					
+ 						radio_button_uncheckedNBK7IBISAPIURKA FABIAN222
+ 					
+ 						radio_button_uncheckedNBK8S7JANTUNEZ JULIO
+ 					
+ 						radio_button_uncheckedNBK95LKARECHAVALETA IGNACIO
+ 					
+ 						radio_button_uncheckedNBK9UJRRADO MARCELLO
+ 					
+ 						radio_button_uncheckedNBKDWWUMUTIO JUAN MANUEL
+ 					
+ 						radio_button_uncheckedNBKE27XGROSSO MARY
+ 					
+ 						radio_button_uncheckedNBKE72HPONTE ENRIQUE
+ 					
+ 						radio_button_uncheckedNBKFE5TREY OMAR
+ 					
+ 						radio_button_uncheckedNBKG3KCQUEIROLO JAIME
+ 					
+ 						radio_button_uncheckedNBKI19GBALADAN SANTIAGO
+ 					
+ 						radio_button_uncheckedNBKK3CEOTEGUI ANDRES
+ 					
+ 						radio_button_uncheckedNBKKP3ESANTAMARINA CARLOS
+ 					
+ 						radio_button_uncheckedNBKKU8IMOREIRA PEDRO
+ 					
+ 						radio_button_uncheckedNBKM3ACBONDONI EDUARDO
+ 					
+ 						radio_button_uncheckedNBKOF8FPONASSO VIRGINIA
+ 					
+ 						radio_button_uncheckedNBKP41XMANTA DANIEL
+ 					
+ 						radio_button_uncheckedNBKQ7SWGROLLA ALVARO
+ 					
+ 						radio_button_uncheckedNBKSJ2YREY SANTIAGO
+ 					
+ 						radio_button_uncheckedNBKV2UPMEZZERA FEDERICO
+ 					
+ 						radio_button_uncheckedNBKWC9EDELFINO ALVARO
+ 					
+ 						radio_button_uncheckedNBKYUGRMILAN PATRICIA
+ 					
+ 						radio_button_uncheckedNBKZ25CBRUN JULIO
+ 					
+ 						radio_button_uncheckedNBKZE2WCARLUCCIO PATRICIA
+ 					
+ 						radio_button_uncheckedNOTTENOTTE MARCELO
+ 					
+ 						radio_button_uncheckedOTEGUIMOTEGUI MARIA ELENA
+ 					
+ 						radio_button_uncheckedPABLOUSUARIO TEST
+ 					
+ 						radio_button_uncheckedPABLO2PABLO22
+ 					
+ 						radio_button_uncheckedPABLO3PABLO3
+ 					
+ 						radio_button_uncheckedPABLO4PABLO44
+ 					
+ 						radio_button_uncheckedPABLO5PÀBLO5
+ 					
+ 						radio_button_uncheckedPABLO6PABLO6
+ 					
+ 						radio_button_uncheckedPACIFICOPACIFICO
+ 					
+ 						radio_button_uncheckedPALMEROPALMERO
+ 					
+ 						radio_button_uncheckedPEPITOA
+ 					
+ 						radio_button_uncheckedPEREIRAIPEREIRA ISABEL
+ 					
+ 						radio_button_uncheckedPIASTRILUCIANA PIASTRI 22222
+ 					
+ 						radio_button_uncheckedPIZZORNOFPIZZORNO FERNANDA
+ 					
+ 						radio_button_uncheckedQQW11
+ 					
+ 						radio_button_uncheckedqwqw
+ 					
+ 						radio_button_uncheckedRAMISRAMIS FEDERICO
+ 					
+ 						radio_button_uncheckedRASNERRASNER NICOLAS
+ 					
+ 						radio_button_uncheckedRDRD
+ 					
+ 						radio_button_uncheckedROCCASROCCA STEFANIA
+ 					
+ 						radio_button_uncheckedRODRIGUEZMRODRIGUEZ BORGES, Marcelo
+ 					
+ 						radio_button_uncheckedROTONDOROTONDO MAGELA
+ 					
+ 						radio_button_uncheckedSANCHEZALBSANCHEZ ALBERTO
+ 					
+ 						radio_button_uncheckedSANCHEZROSANCHEZ RODRIGO
+ 					
+ 						radio_button_uncheckedSANZSANZ ALEJANDRA1
+ 					
+ 						radio_button_uncheckedSBROCCASBROCCA PABLO
+ 					
+ 						radio_button_uncheckedSELHAYSELHAY CAROLINA
+ 					
+ 						radio_button_uncheckedSICARDISICARDI JUAN CARLOS
+ 					
+ 						radio_button_uncheckedSOLAROSOLARO ROSARIO
+ 					
+ 						radio_button_uncheckedSOSAJJSOSA JUAN JOSE
+ 					
+ 						radio_button_uncheckedSOUZASOUZA BARRETO, Juliana
+ 					
+ 						radio_button_uncheckedSTAZIONESTAZIONE FERNANDEZ, Paola Antonella
+ 					
+ 						radio_button_uncheckedSUPERMANSUPERMAN
+ 					
+ 						radio_button_uncheckedTESTtest
+ 					
+ 						radio_button_uncheckedTEST1TEST1
+ 					
+ 						radio_button_uncheckedTEST2ASD
+ 					
+ 						radio_button_uncheckedTEST3TEST3
+ 					
+ 						radio_button_uncheckedtesterUserTester
+ 					
+ 						radio_button_uncheckedTOBLERTOBLER ELIZABETH
+ 					
+ 						radio_button_uncheckedUSER1TEST USER
+ 					
+ 						radio_button_uncheckedusernuevoprueba1user nuevo pruba 2
+ 					
+ 						radio_button_uncheckedusertest2usuario test 2
+ 					
+ 						radio_button_uncheckedUSITAUsuario ITALIA
+ 					
+ 						radio_button_uncheckedUSUPRUEBAUSUARIO DE PRUEBA
+ 					
+ 						radio_button_uncheckedVARELACVARELA CARLOS  ESTUDIO VARELA
+ 					
+ 						radio_button_uncheckedVGGAIS VICTOR
+ 					
+ 						radio_button_uncheckedVILLALBAVILLALBA GUZMAN
+ 					
+ 						radio_button_uncheckedVILLARVILLAR JUAN PABLO
+ 					
+ 						radio_button_uncheckedWILLIMANWILLIMAN JOSE
+ 					
+ 						radio_button_uncheckedYANEZYA?`EZ RODOLFO
+ 					
+ 						radio_button_uncheckedYANEZAYAÑEZ ALVARO
+ 					
+ 				
+
+ 				
+ 			
+ 		
+                                                     
+ 	
+                                             
+                                         
+                                     
+
+                                 
+                                 
+                                     
+                                             
+ 	Usuario
+                                                 
+                                                     Código 
+                                                     Nombre 
+                                                     Fecha Baja 
+                                                 
+                                                 
+                                                     Estado 
+                                                     Idioma 
+                                                     Empleador 
+                                                     Sucursal 
+                                                 
+                                                 
+                                                     Teléfono 
+                                                     Interno 
+                                                     Max Lotes 
+                                                     Número Documento 
+                                                 
+                                                 
+                                                     Superior 
+                                                     Email 
+                                                 
+                                                 
+                                                     
+                                                         addAgregar
+                                                         createModificar
+                                                         lock_openDesbloquear
+                                                         passwordCambio Password
+                                                     
+                                                 
+                                             
+
+                                             
+ 	Perfil
+                                                 
+                                                     
+                                                         
+                                                             filter_altBuscador Perfil 
+                                                         
+                                                     
+                                                     
+                                                         addAgregar Perfil
+                                                         visibilityConsultar Perfil
+                                                         createModificar Perfil
+                                                         content_copyCopiar Perfiles a...
+                                                         deleteEliminar Perfil
+                                                     
+                                                 
+                                                 
+                                                     
+                                                         
+ 		
+ 			
+ 				
+ 					 CódigoDescripciónFecha AltaFecha Baja
+ 				
+ 			
+ 				
+ 					radio_button_checkedBOTCBackoffice Tarjetas de Credito19/07/2024 
+ 				
+ 			
+
+ 			
+ 		
+ 	
+                                                     
+                                                 
+                                             
+
+                                         
+                                 
+                             
+                         
+                 
+ 		
+             
+                     
+ 	
+ 		
+ 	Usuario
+                             
+                                 Código * Código obligatorio 
+                                 Nombre * 
+                                 Fecha Baja 
+                             
+                             
+                                 Estado Seleccione un valorActivoInactivoPeriodo de VacacionesActivo  
+                                 Idioma Seleccione un valorEspanolInglésItaliaNativoSeleccione un valor  
+                                 Empleador * Seleccione un valor0001 - Empresa 1001 - Call Valparaiso0010 - Empleador Seguros0011 - Agencia Externa 1002 - UCE003 - Terreno004 - Terreno Asistido12 - Agencia Externa 213 - Agencia Externa 30011 - Agencia Externa 1  
+                                 Sucursal Seleccione un valorSeleccione un valor  
+                             
+                             
+                                 Teléfono 
+                                 Interno 
+                                 Máx Lotes * 
+                                 Número Documento 
+                             
+                             
+                                 Superior Seleccione1 - 2210 - 112 - 333 - 444 - 445 - 66500 - 1501 - 501600 - AIS PROGRAMADOR 18 - 99800 - Jefe de proyecto 1A100 - A 100aaaa - testAAAE - AAAEAAAF - AAAFAAAG - AAAGAAAR - AAARAABA - AABAAABB - AABBAABC - AABCAACC - aaaAISMM - Mireia (AIS)ANDAN - 22ARRIETA - ARRIETA PABLOASD - ASDBACHECHI - BACHECHI, GONZALO  ESTUDIO BACHECHI441BANYASZ - BANYASZ FLORENCIA1BARCIAL - BARCIA, LucíaBARQUIN - BARQUIN VALIENTE, ALFONSO BELEN - BELEN MANUELBELLAGAMBA - BELLAGAMBA FABRICIO1BERRIEL - BERRIEL FIORELLA11123123BOCCARDI - BOCCARDI DIEGOBOLSAS - USUARIO TEST 2C - }CALLORDA - CALLORDA PEREZ, Eliana PaulaCASAGRANDE - CASAGRANDE MAURICIOCASTROM - CASTRO MARTINCAVIGLIA - CAVIGLIA OSCARCGMYA - CGMyACHARBONNIE - CHARBONNIER LISSETTEcjzou - CaijieCOLL - COLL GONZALO2COLOMBI - COLOMBI MARCELOCOLOMBOD - COLOMBO DANIELCRESPI - CRESPI GONZALOCUADRO - CUADRO OVIEDO, Andrea Antonelladdgg - ddgDELEONL - DE LEON LEONARDODIAZSA - DÍAZ VARELA, Stefani AnabellaESP - ESPESTIGARRIB - ESTIGARRIBIA SCALVINO, VictoriaESTRELLA - DE MARFERNANDEZM - FERNANDEZ MARIA PIAFERNANDEZP - FERNANDEZ PISCIOTTANO, Ana CamilaFERRERE - FERREREFERREYRA - FERREYRA MASDEU, María MatildeFILLAT - FILLAT SOFIAFONTOURA - FONTOURA MELLO, Maira NatalieFRECHOU - FRECHOU FLORENCIAFUSTER - FUSTER ALVAROGADEA - GADEA MARIA NOELGOMEZ - GOMEZ ANDRESGOMEZS - GOMEZ PLATERO SOFIAGUSTAVO - GUSTAVOGUTIERREZN - Gutierrez Bas, Natalia VanessaHUERTAS - HUERTAS LAURAHUGO - HUGO FERNANDEZ, JUAN PABLO IZETTA - IZETTA MAURICIOJAY - JAYKEVIN - KEVINLAGOS - LAGOS MEDEIROS, Camila YamiselLAPI - LAPI MARIA JOSELOPEZC - LOPEZ CAROLINALorem - LoremMANAS - MAÑAS ALEXISMARINO - MARIÑO IGNACIOMASSAT - MASSAT AGUSTINAMAYA - MAYA AGUSTINAMIHALIK - MIHALIK FERNANDOMIRANDA - MIRANDA CARLOSMONTOSSI - MONTOSSI RAULMOREIRAM - MOREIRA MARIA NOELMOYPC - MOyPCNBK1C2R - MILES PAMELANBK1O9H - LIZARRAGA GONZALONBK2PTM - MOLINARI MARTINNBK31EV - TORNQUIST JORGENBK34HL - CORREA JORGENBK54NS - HERNANDEZ GUSTAVONBK5TAQ - MASSEILOT JOAQUINNBK68OW - BARRIOS VERONICA112119NBK7IBI - SAPIURKA FABIAN222NBK8S7J - ANTUNEZ JULIONBK95LK - ARECHAVALETA IGNACIONBK9UJR - RADO MARCELLONBKDWWU - MUTIO JUAN MANUELNBKE27X - GROSSO MARYNBKE72H - PONTE ENRIQUENBKFE5T - REY OMARNBKG3KC - QUEIROLO JAIMENBKI19G - BALADAN SANTIAGONBKK3CE - OTEGUI ANDRESNBKKP3E - SANTAMARINA CARLOSNBKKU8I - MOREIRA PEDRONBKM3AC - BONDONI EDUARDONBKOF8F - PONASSO VIRGINIANBKP41X - MANTA DANIELNBKQ7SW - GROLLA ALVARONBKSJ2Y - REY SANTIAGONBKV2UP - MEZZERA FEDERICONBKWC9E - DELFINO ALVARONBKYUGR - MILAN PATRICIANBKZ25C - BRUN JULIONBKZE2W - CARLUCCIO PATRICIANOTTE - NOTTE MARCELOOTEGUIM - OTEGUI MARIA ELENAPABLO - USUARIO TESTPABLO2 - PABLO22PABLO3 - PABLO3PABLO4 - PABLO44PABLO5 - PÀBLO5PABLO6 - PABLO6PACIFICO - PACIFICOPALMERO - PALMEROPEPITO - APEREIRAI - PEREIRA ISABELPIASTRI - LUCIANA PIASTRI 22222PIZZORNOF - PIZZORNO FERNANDAQQW - 11qw - qwRAMIS - RAMIS FEDERICORASNER - RASNER NICOLASRD - RDROCCAS - ROCCA STEFANIARODRIGUEZM - RODRIGUEZ BORGES, MarceloROTONDO - ROTONDO MAGELASANCHEZALB - SANCHEZ ALBERTOSANCHEZRO - SANCHEZ RODRIGOSANZ - SANZ ALEJANDRA1SBROCCA - SBROCCA PABLOSELHAY - SELHAY CAROLINASICARDI - SICARDI JUAN CARLOSSOLARO - SOLARO ROSARIOSOSAJJ - SOSA JUAN JOSESOUZA - SOUZA BARRETO, JulianaSTAZIONE - STAZIONE FERNANDEZ, Paola AntonellaSUPERMAN - SUPERMANTEST - testTEST1 - TEST1TEST2 - ASDTEST3 - TEST3testerUser - TesterTOBLER - TOBLER ELIZABETHUSER1 - TEST USERusernuevoprueba1 - user nuevo pruba 2usertest2 - usuario test 2USITA - Usuario ITALIAUSUPRUEBA - USUARIO DE PRUEBAVARELAC - VARELA CARLOS  ESTUDIO VARELAVGG - AIS VICTORVILLALBA - VILLALBA GUZMANVILLAR - VILLAR JUAN PABLOWILLIMAN - WILLIMAN JOSEYANEZ - YA?`EZ RODOLFOYANEZA - YAÑEZ ALVAROSeleccione  
+                                 Email 
+                             
+                         
+
+ 	
+                             Guardar
+                             Cerrar
+                         
+
+ 	
+
+                 
+             
+ 			
+                     
+
+ 			
+                 
+ 		
+             
+ 			
+                     
+
+ 			
+                 
+ 		
+             
+ 			
+                     
+
+ 			
+                 
+ 		
+             
+ 			
+                     
+
+ 			
+                 
+ 		
+         
+ 	
+
+         
+         
+     
+
+
+ 	
+
+
+     
+         
+         
+             
+                 
+                     
+                 
+                 
+                     
+                 
+                 
+                     
+                 
+             
+         
+     
+
+
+ Guardar

Call log:
  - P01: página debe contener "USQA01" with timeout 5000ms
  - waiting for locator('body')
    4 × locator resolved to <body id="bodyTag">…</body>
      - unexpected value "
    




































	

		
	
        

        
                
            
        
	
                

	
            

        menulogoutSalirSeguridad PrejudicialUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:1Realizado Hoy:1Total en Agenda:2Barrido Realizado:50%Clientes Asignados:10430    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion Manualformat_list_bulletedReportes OperativosleaderboardInformesleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estados EspecialesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
        
            
	
                    
                        
                            chevron_leftadministrador
                        
                        
                            
                            
                            
                            
                            
                        
                    
                

            
    
	
            
		RolesUsuarios



			
                    
                            
                                
                                    
	
                                            
                                                
		Roles
	
                                                filter_altBuscar Roles 
                                                
                                                    addAgregar Rol
                                                    Jerarquía
                                                    grid_onExportar
                                                
                                            
                                            
                                                
                                                    
		
			
				
					 RolDescripción% Asignación
				
			
				
					radio_button_checkedBOTCBackoffice Tarjetas de Credito100
				
					radio_button_uncheckedINUBICBolson de Clientes Inubicables1100
				
					radio_button_uncheckedCCEXTCall Center Externo100
				
					radio_button_uncheckedCOBSRCobrador Senior100
				
					radio_button_uncheckedCOMJUDComite Judicial100
				
					radio_button_uncheckedTOTALControl Total 
				
					radio_button_uncheckedCONVEJConvenios Extrajudiciales95
				
					radio_button_uncheckedEJCOMEjecutivo Comercial 
				
					radio_button_uncheckedEMPEXTEmpresas Externas de Cobranzas25
				
					radio_button_uncheckedGCCENGerente Casa Central 
				
					radio_button_uncheckedGCGerente de Cobranzas 
				
					radio_button_uncheckedGERSUCGerente de Sucursal105
				
					radio_button_uncheckedATMSGestion ATM (Cajero Automatico)100
				
					radio_button_uncheckedAUTOPAGestion Autopago2
				
					radio_button_uncheckedCARTASGestion Cartas 
				
					radio_button_uncheckedEMAILGestion Email 
				
					radio_button_uncheckedNOMORAGestion No Mora1
				
					radio_button_uncheckedSMSGestion SMS 
				
					radio_button_uncheckedGRAGestor de Recuperacion de Activos 
				
					radio_button_uncheckedJOPSUCJefe Operativo de Sucursal 
				
					radio_button_uncheckedJJudicial 
				
					radio_button_uncheckedMBOTMiembro Backoffice Tarjetas 
				
					radio_button_uncheckedMCONEJMiembro Conv Extrajudicial 
				
					radio_button_uncheckedMICJMiembro de Comite Judicial 
				
					radio_button_uncheckedMSINMiembro Gestion Siniestro 
				
					radio_button_uncheckedNUCLEONucleo Estrategico 
				
					radio_button_uncheckedOPCCOperador de Call Center 
				
					radio_button_uncheckedGESSINPool de Siniestros 
				
					radio_button_uncheckedPROGRAMADORPROGRAMADOR 
				
					radio_button_uncheckedRACRecurso de Apoyo a Cobranzas 
				
					radio_button_uncheckedRTESTRol de Test 
				
					radio_button_uncheckedSEGURSeguros 
				
					radio_button_uncheckedSKIPTSkip Trace 
				
					radio_button_uncheckedAISSoporte AIS149
				
					radio_button_uncheckedSUPCCSupervisor Call Center 
				
			

			
		
	
                                                    
                                                
                                            
                                        

                                    
	
                                            
                                                
		Usuarios
	
                                                
                                                    visibilityConsultar
                                                    createModificar
                                                    deleteEliminar
                                                
                                            
                                            
                                                
                                                    
		
			
				
					 CódigoDescripción
				
			
				
					radio_button_checked122
				
					radio_button_uncheckedAAAEAAAE
				
					radio_button_uncheckedddggddg
				
					radio_button_uncheckedJAYJAY
				
					radio_button_uncheckedPABLOUSUARIO TEST
				
					radio_button_uncheckedPABLO4PABLO44
				
					radio_button_uncheckedSUPERMANSUPERMAN
				
					radio_button_uncheckedVARELACVARELA CARLOS  ESTUDIO VARELA
				
					radio_button_uncheckedVILLARVILLAR JUAN PABLO
				
					radio_button_uncheckedWILLIMANWILLIMAN JOSE
				
					radio_button_uncheckedYANEZYA?`EZ RODOLFO
				
					radio_button_uncheckedYANEZAYAÑEZ ALVARO
				
			

			
		
	
                                                    
                                                
                                            
                                        

                                
                                
                                    
	
                                        
		
                                                
                                                    
                                                        
                                                            
			Modulos Disponibles
		
                                                        
                                                        
                                                            Seleccionar Todos
                                                            
                                                                addAñadir Permiso
                                                                grid_onExportar
                                                            
                                                        
                                                        
                                                            
                                                                
			
                                                                        
				
					
						10 - Cobranza Prejudicial
					
				
					
						
							11 - Agenda Personal
						
					
						
							12 - Busqueda de Clientes
						
					
						
							
								265 - Ver Solo Casos del Mismo Empleador
							
						
							
								267 - Ver Todos Los Casos
							
						
					
						
							120 - Detalle de Cliente
						
					
						
							
								122 - Ver Compromisos
							
						
							
								123 - Generar Compromisoso
							
						
							
								124 - Generar Convenio
							
						
							
								125 - Ver caso judicial
							
						
							
								126 - Ver Ficha
							
						
							
								25 - Convenios
							
						
							
								26 - Pasaje a Judicial
							
						
							
								366 - Gestionar Casos No Asignados
							
						
					
						
							13 - Supervision
						
					
						
							
								14 - Reasignacion Manual
							
						
					
						
							15 - Reportes Operativos
						
					
						
							
								17 - Distribución por Tipologia de Clientes
							
						
							
								18 - Distribución por Estrategia
							
						
							
								19 - Call Center
							
						
							
								22 - Distribución por Estados Especiales
							
						
							
								23 - Distribución por Rol y Nivel de Mora
							
						
							
								27 - otros Reportes
							
						
							
								74 - Informes
							
						
					
						
							20 - Agenda de Grupo
						
					
						
							24 - Pooles de Trabajo
						
					
						
							320 - Reportes OBI
						
					
						
							
								321 - Resumen Agenda
							
						
							
								322 - Gestión Rol y N.Mora
							
						
							
								323 - Gest. Tipo Cliente y N.Mora
							
						
							
								324 - Gest. Estrategia y N.Mora
							
						
							
								325 - Promeas de Pago
							
						
							
								326 - Risk Management
							
						
					
				
					
						200 - Administrador
					
				
					
						
							201 - Administración
						
					
						
							
								202 - Oficinas
							
						
							
								203 - Productos
							
						
							
								204 - Festivos
							
						
							
								205 - Tablas Generales
							
						
							
								
									362 - Crear y Modificar Roles
								
							
						
							
								206 - Conversión Monetaria
							
						
							
								207 - Multi-Mandante
							
						
							
								
									208 - Mandantes
								
							
								
									209 - Tablas Generales Multi-Mandante
								
							
						
							
								211 - Comisiones y Honorarios
							
						
							
								276 - Variables de Priorización de Agenda
							
						
							
								277 - Parámetros
							
						
					
						
							250 - Seguridad
						
					
						
							
								251 - Administración de Usuarios
							
						
							
								
									358 - Edición de Usuarios
								
							
								
									360 - Gestionar Permisos Roles
								
							
						
							
								252 - Parametría de Seguridad
							
						
							
								275 - Administración de Usuarios Judicial
							
						
							
								285 - Administración de Comisionistas
							
						
					
						
							263 - Estrategia
						
					
						
							
								260 - Judicial
							
						
							
								
									274 - Edición de TARs
								
							
								
									287 - Vinculación de Variables a GMR
								
							
								
									344 - Diseñador de procedimientos judiciales
								
							
						
							
								272 - Prejudicial
							
						
							
								
									262 - Edición de TARs
								
							
								
									
										359 - Asignar Permisos uso TARs
									
								
							
								
									264 - Diseñador de Flujos
								
							
								
									273 - Edición de Estrategias
								
							
								
									286 - Vinculación de Variables a GMR
								
							
								
									290 - Generar Archivo GMR Plus
								
							
								
									310 - Simulador de Estrategias
								
							
								
									311 - Diagnóstico de Evaluación
								
							
								
									341 - Simulador
								
							
								
									
										340 - Simulaciones unitarias
									
								
									
										342 - Simulaciones masivas
									
								
							
						
					
						
							300 - Herramientas
						
					
						
							
								301 - Generar Cartas...
							
						
							
								302 - Generar Fichas de Cobranzaa?|
							
						
							
								303 - Gestión de Nuevos Campos
							
						
					
				
					
						52 - Otras Funcionalidades
					
				
					
						
							108 - Añadir ficheros a Gestión
						
					
				
			
                                                                    
		
                                                            
                                                        
                                                    
                                                    
                                                        
                                                            
			Modulos Otorgados
		
                                                        
                                                        
                                                            Seleccionar Todos
                                                            
                                                                deleteQuitar Permiso
                                                            
                                                        
                                                        
                                                            
                                                                
			
                                                                        
				
					
						10 - Cobranza Prejudicial
					
				
					
						
							11 - Agenda Personal
						
					
						
							12 - Busqueda de Clientes
						
					
						
							
								265 - Ver Solo Casos del Mismo Empleador
							
						
							
								267 - Ver Todos Los Casos
							
						
					
						
							120 - Detalle de Cliente
						
					
						
							
								122 - Ver Compromisos
							
						
							
								123 - Generar Compromisoso
							
						
							
								124 - Generar Convenio
							
						
							
								125 - Ver caso judicial
							
						
							
								126 - Ver Ficha
							
						
							
								25 - Convenios
							
						
							
								26 - Pasaje a Judicial
							
						
							
								366 - Gestionar Casos No Asignados
							
						
					
						
							13 - Supervision
						
					
						
							
								14 - Reasignacion Manual
							
						
					
						
							15 - Reportes Operativos
						
					
						
							
								17 - Distribución por Tipologia de Clientes
							
						
							
								18 - Distribución por Estrategia
							
						
							
								19 - Call Center
							
						
							
								22 - Distribución por Estados Especiales
							
						
							
								23 - Distribución por Rol y Nivel de Mora
							
						
							
								27 - otros Reportes
							
						
							
								74 - Informes
							
						
					
						
							20 - Agenda de Grupo
						
					
						
							24 - Pooles de Trabajo
						
					
				
					
						200 - Administrador
					
				
					
						
							201 - Administración
						
					
						
							
								202 - Oficinas
							
						
							
								203 - Productos
							
						
							
								204 - Festivos
							
						
							
								205 - Tablas Generales
							
						
							
								
									362 - Crear y Modificar Roles
								
							
						
							
								206 - Conversión Monetaria
							
						
							
								207 - Multi-Mandante
							
						
							
								
									208 - Mandantes
								
							
								
									209 - Tablas Generales Multi-Mandante
								
							
						
							
								211 - Comisiones y Honorarios
							
						
							
								276 - Variables de Priorización de Agenda
							
						
							
								277 - Parámetros
							
						
					
						
							250 - Seguridad
						
					
						
							
								251 - Administración de Usuarios
							
						
							
								
									358 - Edición de Usuarios
								
							
								
									360 - Gestionar Permisos Roles
								
							
						
							
								252 - Parametría de Seguridad
							
						
							
								275 - Administración de Usuarios Judicial
							
						
							
								285 - Administración de Comisionistas
							
						
					
						
							263 - Estrategia
						
					
						
							
								260 - Judicial
							
						
							
								
									274 - Edición de TARs
								
							
								
									287 - Vinculación de Variables a GMR
								
							
								
									344 - Diseñador de procedimientos judiciales
								
							
						
							
								272 - Prejudicial
							
						
							
								
									262 - Edición de TARs
								
							
								
									
										359 - Asignar Permisos uso TARs
									
								
							
								
									264 - Diseñador de Flujos
								
							
								
									273 - Edición de Estrategias
								
							
								
									286 - Vinculación de Variables a GMR
								
							
								
									290 - Generar Archivo GMR Plus
								
							
						
					
						
							300 - Herramientas
						
					
						
							
								301 - Generar Cartas...
							
						
							
								302 - Generar Fichas de Cobranzaa?|
							
						
							
								303 - Gestión de Nuevos Campos
							
						
					
				
					
						343 - SEPARADOR
					
				
					
						52 - Otras Funcionalidades
					
				
					
						
							108 - Añadir ficheros a Gestión
						
					
				
			
                                                                    
		
                                                            
                                                        
                                                    
                                                
                                            
	
                                    

                                
                            
                        
                
		
			
                    
                            
                                
                                    
	
                                        
                                            Ver Usuarios dados de Baja
                                            filter_altBuscar Usuarios 
                                            
                                                grid_onUsuarios
                                            
                                        
                                        
                                            
                                                
		
                                                        
			
				
					
						 CódigoDescripción
					
				
					
						radio_button_checked122
					
						radio_button_unchecked1011
					
						radio_button_unchecked233
					
						radio_button_unchecked344
					
						radio_button_unchecked444
					
						radio_button_unchecked566
					
						radio_button_unchecked5001
					
						radio_button_unchecked501501
					
						radio_button_unchecked600AIS PROGRAMADOR 1
					
						radio_button_unchecked899
					
						radio_button_unchecked800Jefe de proyecto 1
					
						radio_button_uncheckedA100A 100
					
						radio_button_uncheckedaaaatest
					
						radio_button_uncheckedAAAEAAAE
					
						radio_button_uncheckedAAAFAAAF
					
						radio_button_uncheckedAAAGAAAG
					
						radio_button_uncheckedAAARAAAR
					
						radio_button_uncheckedAABAAABA
					
						radio_button_uncheckedAABBAABB
					
						radio_button_uncheckedAABCAABC
					
						radio_button_uncheckedAACCaaa
					
						radio_button_uncheckedAISMMMireia (AIS)
					
						radio_button_uncheckedANDAN22
					
						radio_button_uncheckedARRIETAARRIETA PABLO
					
						radio_button_uncheckedASDASD
					
						radio_button_uncheckedBACHECHIBACHECHI, GONZALO  ESTUDIO BACHECHI441
					
						radio_button_uncheckedBANYASZBANYASZ FLORENCIA1
					
						radio_button_uncheckedBARCIALBARCIA, Lucía
					
						radio_button_uncheckedBARQUINBARQUIN VALIENTE, ALFONSO 
					
						radio_button_uncheckedBELENBELEN MANUEL
					
						radio_button_uncheckedBELLAGAMBABELLAGAMBA FABRICIO1
					
						radio_button_uncheckedBERRIELBERRIEL FIORELLA11123123
					
						radio_button_uncheckedBOCCARDIBOCCARDI DIEGO
					
						radio_button_uncheckedBOLSASUSUARIO TEST 2
					
						radio_button_uncheckedC}
					
						radio_button_uncheckedCALLORDACALLORDA PEREZ, Eliana Paula
					
						radio_button_uncheckedCASAGRANDECASAGRANDE MAURICIO
					
						radio_button_uncheckedCASTROMCASTRO MARTIN
					
						radio_button_uncheckedCAVIGLIACAVIGLIA OSCAR
					
						radio_button_uncheckedCGMYACGMyA
					
						radio_button_uncheckedCHARBONNIECHARBONNIER LISSETTE
					
						radio_button_uncheckedcjzouCaijie
					
						radio_button_uncheckedCOLLCOLL GONZALO2
					
						radio_button_uncheckedCOLOMBICOLOMBI MARCELO
					
						radio_button_uncheckedCOLOMBODCOLOMBO DANIEL
					
						radio_button_uncheckedCRESPICRESPI GONZALO
					
						radio_button_uncheckedCUADROCUADRO OVIEDO, Andrea Antonella
					
						radio_button_uncheckedddggddg
					
						radio_button_uncheckedDELEONLDE LEON LEONARDO
					
						radio_button_uncheckedDIAZSADÍAZ VARELA, Stefani Anabella
					
						radio_button_uncheckedESPESP
					
						radio_button_uncheckedESTIGARRIBESTIGARRIBIA SCALVINO, Victoria
					
						radio_button_uncheckedESTRELLADE MAR
					
						radio_button_uncheckedFERNANDEZMFERNANDEZ MARIA PIA
					
						radio_button_uncheckedFERNANDEZPFERNANDEZ PISCIOTTANO, Ana Camila
					
						radio_button_uncheckedFERREREFERRERE
					
						radio_button_uncheckedFERREYRAFERREYRA MASDEU, María Matilde
					
						radio_button_uncheckedFILLATFILLAT SOFIA
					
						radio_button_uncheckedFONTOURAFONTOURA MELLO, Maira Natalie
					
						radio_button_uncheckedFRECHOUFRECHOU FLORENCIA
					
						radio_button_uncheckedFUSTERFUSTER ALVARO
					
						radio_button_uncheckedGADEAGADEA MARIA NOEL
					
						radio_button_uncheckedGOMEZGOMEZ ANDRES
					
						radio_button_uncheckedGOMEZSGOMEZ PLATERO SOFIA
					
						radio_button_uncheckedGUSTAVOGUSTAVO
					
						radio_button_uncheckedGUTIERREZNGutierrez Bas, Natalia Vanessa
					
						radio_button_uncheckedHUERTASHUERTAS LAURA
					
						radio_button_uncheckedHUGOHUGO FERNANDEZ, JUAN PABLO 
					
						radio_button_uncheckedIZETTAIZETTA MAURICIO
					
						radio_button_uncheckedJAYJAY
					
						radio_button_uncheckedKEVINKEVIN
					
						radio_button_uncheckedLAGOSLAGOS MEDEIROS, Camila Yamisel
					
						radio_button_uncheckedLAPILAPI MARIA JOSE
					
						radio_button_uncheckedLOPEZCLOPEZ CAROLINA
					
						radio_button_uncheckedLoremLorem
					
						radio_button_uncheckedMANASMAÑAS ALEXIS
					
						radio_button_uncheckedMARINOMARIÑO IGNACIO
					
						radio_button_uncheckedMASSATMASSAT AGUSTINA
					
						radio_button_uncheckedMAYAMAYA AGUSTINA
					
						radio_button_uncheckedMIHALIKMIHALIK FERNANDO
					
						radio_button_uncheckedMIRANDAMIRANDA CARLOS
					
						radio_button_uncheckedMONTOSSIMONTOSSI RAUL
					
						radio_button_uncheckedMOREIRAMMOREIRA MARIA NOEL
					
						radio_button_uncheckedMOYPCMOyPC
					
						radio_button_uncheckedNBK1C2RMILES PAMELA
					
						radio_button_uncheckedNBK1O9HLIZARRAGA GONZALO
					
						radio_button_uncheckedNBK2PTMMOLINARI MARTIN
					
						radio_button_uncheckedNBK31EVTORNQUIST JORGE
					
						radio_button_uncheckedNBK34HLCORREA JORGE
					
						radio_button_uncheckedNBK54NSHERNANDEZ GUSTAVO
					
						radio_button_uncheckedNBK5TAQMASSEILOT JOAQUIN
					
						radio_button_uncheckedNBK68OWBARRIOS VERONICA112119
					
						radio_button_uncheckedNBK7IBISAPIURKA FABIAN222
					
						radio_button_uncheckedNBK8S7JANTUNEZ JULIO
					
						radio_button_uncheckedNBK95LKARECHAVALETA IGNACIO
					
						radio_button_uncheckedNBK9UJRRADO MARCELLO
					
						radio_button_uncheckedNBKDWWUMUTIO JUAN MANUEL
					
						radio_button_uncheckedNBKE27XGROSSO MARY
					
						radio_button_uncheckedNBKE72HPONTE ENRIQUE
					
						radio_button_uncheckedNBKFE5TREY OMAR
					
						radio_button_uncheckedNBKG3KCQUEIROLO JAIME
					
						radio_button_uncheckedNBKI19GBALADAN SANTIAGO
					
						radio_button_uncheckedNBKK3CEOTEGUI ANDRES
					
						radio_button_uncheckedNBKKP3ESANTAMARINA CARLOS
					
						radio_button_uncheckedNBKKU8IMOREIRA PEDRO
					
						radio_button_uncheckedNBKM3ACBONDONI EDUARDO
					
						radio_button_uncheckedNBKOF8FPONASSO VIRGINIA
					
						radio_button_uncheckedNBKP41XMANTA DANIEL
					
						radio_button_uncheckedNBKQ7SWGROLLA ALVARO
					
						radio_button_uncheckedNBKSJ2YREY SANTIAGO
					
						radio_button_uncheckedNBKV2UPMEZZERA FEDERICO
					
						radio_button_uncheckedNBKWC9EDELFINO ALVARO
					
						radio_button_uncheckedNBKYUGRMILAN PATRICIA
					
						radio_button_uncheckedNBKZ25CBRUN JULIO
					
						radio_button_uncheckedNBKZE2WCARLUCCIO PATRICIA
					
						radio_button_uncheckedNOTTENOTTE MARCELO
					
						radio_button_uncheckedOTEGUIMOTEGUI MARIA ELENA
					
						radio_button_uncheckedPABLOUSUARIO TEST
					
						radio_button_uncheckedPABLO2PABLO22
					
						radio_button_uncheckedPABLO3PABLO3
					
						radio_button_uncheckedPABLO4PABLO44
					
						radio_button_uncheckedPABLO5PÀBLO5
					
						radio_button_uncheckedPABLO6PABLO6
					
						radio_button_uncheckedPACIFICOPACIFICO
					
						radio_button_uncheckedPALMEROPALMERO
					
						radio_button_uncheckedPEPITOA
					
						radio_button_uncheckedPEREIRAIPEREIRA ISABEL
					
						radio_button_uncheckedPIASTRILUCIANA PIASTRI 22222
					
						radio_button_uncheckedPIZZORNOFPIZZORNO FERNANDA
					
						radio_button_uncheckedQQW11
					
						radio_button_uncheckedqwqw
					
						radio_button_uncheckedRAMISRAMIS FEDERICO
					
						radio_button_uncheckedRASNERRASNER NICOLAS
					
						radio_button_uncheckedRDRD
					
						radio_button_uncheckedROCCASROCCA STEFANIA
					
						radio_button_uncheckedRODRIGUEZMRODRIGUEZ BORGES, Marcelo
					
						radio_button_uncheckedROTONDOROTONDO MAGELA
					
						radio_button_uncheckedSANCHEZALBSANCHEZ ALBERTO
					
						radio_button_uncheckedSANCHEZROSANCHEZ RODRIGO
					
						radio_button_uncheckedSANZSANZ ALEJANDRA1
					
						radio_button_uncheckedSBROCCASBROCCA PABLO
					
						radio_button_uncheckedSELHAYSELHAY CAROLINA
					
						radio_button_uncheckedSICARDISICARDI JUAN CARLOS
					
						radio_button_uncheckedSOLAROSOLARO ROSARIO
					
						radio_button_uncheckedSOSAJJSOSA JUAN JOSE
					
						radio_button_uncheckedSOUZASOUZA BARRETO, Juliana
					
						radio_button_uncheckedSTAZIONESTAZIONE FERNANDEZ, Paola Antonella
					
						radio_button_uncheckedSUPERMANSUPERMAN
					
						radio_button_uncheckedTESTtest
					
						radio_button_uncheckedTEST1TEST1
					
						radio_button_uncheckedTEST2ASD
					
						radio_button_uncheckedTEST3TEST3
					
						radio_button_uncheckedtesterUserTester
					
						radio_button_uncheckedTOBLERTOBLER ELIZABETH
					
						radio_button_uncheckedUSER1TEST USER
					
						radio_button_uncheckedusernuevoprueba1user nuevo pruba 2
					
						radio_button_uncheckedusertest2usuario test 2
					
						radio_button_uncheckedUSITAUsuario ITALIA
					
						radio_button_uncheckedUSUPRUEBAUSUARIO DE PRUEBA
					
						radio_button_uncheckedVARELACVARELA CARLOS  ESTUDIO VARELA
					
						radio_button_uncheckedVGGAIS VICTOR
					
						radio_button_uncheckedVILLALBAVILLALBA GUZMAN
					
						radio_button_uncheckedVILLARVILLAR JUAN PABLO
					
						radio_button_uncheckedWILLIMANWILLIMAN JOSE
					
						radio_button_uncheckedYANEZYA?`EZ RODOLFO
					
						radio_button_uncheckedYANEZAYAÑEZ ALVARO
					
				

				
			
		
                                                    
	
                                            
                                        
                                    

                                
                                
                                    
                                            
	Usuario
                                                
                                                    Código 
                                                    Nombre 
                                                    Fecha Baja 
                                                
                                                
                                                    Estado 
                                                    Idioma 
                                                    Empleador 
                                                    Sucursal 
                                                
                                                
                                                    Teléfono 
                                                    Interno 
                                                    Max Lotes 
                                                    Número Documento 
                                                
                                                
                                                    Superior 
                                                    Email 
                                                
                                                
                                                    
                                                        addAgregar
                                                        createModificar
                                                        lock_openDesbloquear
                                                        passwordCambio Password
                                                    
                                                
                                            

                                            
	Perfil
                                                
                                                    
                                                        
                                                            filter_altBuscador Perfil 
                                                        
                                                    
                                                    
                                                        addAgregar Perfil
                                                        visibilityConsultar Perfil
                                                        createModificar Perfil
                                                        content_copyCopiar Perfiles a...
                                                        deleteEliminar Perfil
                                                    
                                                
                                                
                                                    
                                                        
		
			
				
					 CódigoDescripciónFecha AltaFecha Baja
				
			
				
					radio_button_checkedBOTCBackoffice Tarjetas de Credito19/07/2024 
				
			

			
		
	
                                                    
                                                
                                            

                                        
                                
                            
                        
                
		
            
                    
	
		
	Usuario
                            
                                Código * 
                                Nombre * 
                                Fecha Baja 
                            
                            
                                Estado Seleccione un valorActivoInactivoPeriodo de VacacionesActivo  
                                Idioma Seleccione un valorEspanolInglésItaliaNativoSeleccione un valor  
                                Empleador * Seleccione un valor0001 - Empresa 1001 - Call Valparaiso0010 - Empleador Seguros0011 - Agencia Externa 1002 - UCE003 - Terreno004 - Terreno Asistido12 - Agencia Externa 213 - Agencia Externa 30011 - Agencia Externa 1  
                                Sucursal Seleccione un valorSeleccione un valor  
                            
                            
                                Teléfono 
                                Interno 
                                Máx Lotes * 
                                Número Documento 
                            
                            
                                Superior Seleccione1 - 2210 - 112 - 333 - 444 - 445 - 66500 - 1501 - 501600 - AIS PROGRAMADOR 18 - 99800 - Jefe de proyecto 1A100 - A 100aaaa - testAAAE - AAAEAAAF - AAAFAAAG - AAAGAAAR - AAARAABA - AABAAABB - AABBAABC - AABCAACC - aaaAISMM - Mireia (AIS)ANDAN - 22ARRIETA - ARRIETA PABLOASD - ASDBACHECHI - BACHECHI, GONZALO  ESTUDIO BACHECHI441BANYASZ - BANYASZ FLORENCIA1BARCIAL - BARCIA, LucíaBARQUIN - BARQUIN VALIENTE, ALFONSO BELEN - BELEN MANUELBELLAGAMBA - BELLAGAMBA FABRICIO1BERRIEL - BERRIEL FIORELLA11123123BOCCARDI - BOCCARDI DIEGOBOLSAS - USUARIO TEST 2C - }CALLORDA - CALLORDA PEREZ, Eliana PaulaCASAGRANDE - CASAGRANDE MAURICIOCASTROM - CASTRO MARTINCAVIGLIA - CAVIGLIA OSCARCGMYA - CGMyACHARBONNIE - CHARBONNIER LISSETTEcjzou - CaijieCOLL - COLL GONZALO2COLOMBI - COLOMBI MARCELOCOLOMBOD - COLOMBO DANIELCRESPI - CRESPI GONZALOCUADRO - CUADRO OVIEDO, Andrea Antonelladdgg - ddgDELEONL - DE LEON LEONARDODIAZSA - DÍAZ VARELA, Stefani AnabellaESP - ESPESTIGARRIB - ESTIGARRIBIA SCALVINO, VictoriaESTRELLA - DE MARFERNANDEZM - FERNANDEZ MARIA PIAFERNANDEZP - FERNANDEZ PISCIOTTANO, Ana CamilaFERRERE - FERREREFERREYRA - FERREYRA MASDEU, María MatildeFILLAT - FILLAT SOFIAFONTOURA - FONTOURA MELLO, Maira NatalieFRECHOU - FRECHOU FLORENCIAFUSTER - FUSTER ALVAROGADEA - GADEA MARIA NOELGOMEZ - GOMEZ ANDRESGOMEZS - GOMEZ PLATERO SOFIAGUSTAVO - GUSTAVOGUTIERREZN - Gutierrez Bas, Natalia VanessaHUERTAS - HUERTAS LAURAHUGO - HUGO FERNANDEZ, JUAN PABLO IZETTA - IZETTA MAURICIOJAY - JAYKEVIN - KEVINLAGOS - LAGOS MEDEIROS, Camila YamiselLAPI - LAPI MARIA JOSELOPEZC - LOPEZ CAROLINALorem - LoremMANAS - MAÑAS ALEXISMARINO - MARIÑO IGNACIOMASSAT - MASSAT AGUSTINAMAYA - MAYA AGUSTINAMIHALIK - MIHALIK FERNANDOMIRANDA - MIRANDA CARLOSMONTOSSI - MONTOSSI RAULMOREIRAM - MOREIRA MARIA NOELMOYPC - MOyPCNBK1C2R - MILES PAMELANBK1O9H - LIZARRAGA GONZALONBK2PTM - MOLINARI MARTINNBK31EV - TORNQUIST JORGENBK34HL - CORREA JORGENBK54NS - HERNANDEZ GUSTAVONBK5TAQ - MASSEILOT JOAQUINNBK68OW - BARRIOS VERONICA112119NBK7IBI - SAPIURKA FABIAN222NBK8S7J - ANTUNEZ JULIONBK95LK - ARECHAVALETA IGNACIONBK9UJR - RADO MARCELLONBKDWWU - MUTIO JUAN MANUELNBKE27X - GROSSO MARYNBKE72H - PONTE ENRIQUENBKFE5T - REY OMARNBKG3KC - QUEIROLO JAIMENBKI19G - BALADAN SANTIAGONBKK3CE - OTEGUI ANDRESNBKKP3E - SANTAMARINA CARLOSNBKKU8I - MOREIRA PEDRONBKM3AC - BONDONI EDUARDONBKOF8F - PONASSO VIRGINIANBKP41X - MANTA DANIELNBKQ7SW - GROLLA ALVARONBKSJ2Y - REY SANTIAGONBKV2UP - MEZZERA FEDERICONBKWC9E - DELFINO ALVARONBKYUGR - MILAN PATRICIANBKZ25C - BRUN JULIONBKZE2W - CARLUCCIO PATRICIANOTTE - NOTTE MARCELOOTEGUIM - OTEGUI MARIA ELENAPABLO - USUARIO TESTPABLO2 - PABLO22PABLO3 - PABLO3PABLO4 - PABLO44PABLO5 - PÀBLO5PABLO6 - PABLO6PACIFICO - PACIFICOPALMERO - PALMEROPEPITO - APEREIRAI - PEREIRA ISABELPIASTRI - LUCIANA PIASTRI 22222PIZZORNOF - PIZZORNO FERNANDAQQW - 11qw - qwRAMIS - RAMIS FEDERICORASNER - RASNER NICOLASRD - RDROCCAS - ROCCA STEFANIARODRIGUEZM - RODRIGUEZ BORGES, MarceloROTONDO - ROTONDO MAGELASANCHEZALB - SANCHEZ ALBERTOSANCHEZRO - SANCHEZ RODRIGOSANZ - SANZ ALEJANDRA1SBROCCA - SBROCCA PABLOSELHAY - SELHAY CAROLINASICARDI - SICARDI JUAN CARLOSSOLARO - SOLARO ROSARIOSOSAJJ - SOSA JUAN JOSESOUZA - SOUZA BARRETO, JulianaSTAZIONE - STAZIONE FERNANDEZ, Paola AntonellaSUPERMAN - SUPERMANTEST - testTEST1 - TEST1TEST2 - ASDTEST3 - TEST3testerUser - TesterTOBLER - TOBLER ELIZABETHUSER1 - TEST USERusernuevoprueba1 - user nuevo pruba 2usertest2 - usuario test 2USITA - Usuario ITALIAUSUPRUEBA - USUARIO DE PRUEBAVARELAC - VARELA CARLOS  ESTUDIO VARELAVGG - AIS VICTORVILLALBA - VILLALBA GUZMANVILLAR - VILLAR JUAN PABLOWILLIMAN - WILLIMAN JOSEYANEZ - YA?`EZ RODOLFOYANEZA - YAÑEZ ALVAROSeleccione  
                                Email 
                            
                        

	
                            Guardar
                            Cerrar
                        

	

                
            
			
                    

			
                
		
            
			
                    

			
                
		
            
			
                    

			
                
		
            
			
                    

			
                
		
        
	

        
        
    


	


    
        
        
            
                
                    
                
                
                    
                
                
                    
                
            
        
    


GuardarCerrar"
    4 × locator resolved to <body id="bodyTag">…</body>
      - unexpected value "
    




































	

		
	
        

        
                
            
        
	
                

	
            

        menulogoutSalirSeguridad PrejudicialUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:1Realizado Hoy:1Total en Agenda:2Barrido Realizado:50%Clientes Asignados:10430    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion Manualformat_list_bulletedReportes OperativosleaderboardInformesleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estados EspecialesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
        
            
	
                    
                        
                            chevron_leftadministrador
                        
                        
                            
                            
                            
                            
                            
                        
                    
                

            
    
	
            
		RolesUsuarios



			
                    
                            
                                
                                    
	
                                            
                                                
		Roles
	
                                                filter_altBuscar Roles 
                                                
                                                    addAgregar Rol
                                                    Jerarquía
                                                    grid_onExportar
                                                
                                            
                                            
                                                
                                                    
		
			
				
					 RolDescripción% Asignación
				
			
				
					radio_button_checkedBOTCBackoffice Tarjetas de Credito100
				
					radio_button_uncheckedINUBICBolson de Clientes Inubicables1100
				
					radio_button_uncheckedCCEXTCall Center Externo100
				
					radio_button_uncheckedCOBSRCobrador Senior100
				
					radio_button_uncheckedCOMJUDComite Judicial100
				
					radio_button_uncheckedTOTALControl Total 
				
					radio_button_uncheckedCONVEJConvenios Extrajudiciales95
				
					radio_button_uncheckedEJCOMEjecutivo Comercial 
				
					radio_button_uncheckedEMPEXTEmpresas Externas de Cobranzas25
				
					radio_button_uncheckedGCCENGerente Casa Central 
				
					radio_button_uncheckedGCGerente de Cobranzas 
				
					radio_button_uncheckedGERSUCGerente de Sucursal105
				
					radio_button_uncheckedATMSGestion ATM (Cajero Automatico)100
				
					radio_button_uncheckedAUTOPAGestion Autopago2
				
					radio_button_uncheckedCARTASGestion Cartas 
				
					radio_button_uncheckedEMAILGestion Email 
				
					radio_button_uncheckedNOMORAGestion No Mora1
				
					radio_button_uncheckedSMSGestion SMS 
				
					radio_button_uncheckedGRAGestor de Recuperacion de Activos 
				
					radio_button_uncheckedJOPSUCJefe Operativo de Sucursal 
				
					radio_button_uncheckedJJudicial 
				
					radio_button_uncheckedMBOTMiembro Backoffice Tarjetas 
				
					radio_button_uncheckedMCONEJMiembro Conv Extrajudicial 
				
					radio_button_uncheckedMICJMiembro de Comite Judicial 
				
					radio_button_uncheckedMSINMiembro Gestion Siniestro 
				
					radio_button_uncheckedNUCLEONucleo Estrategico 
				
					radio_button_uncheckedOPCCOperador de Call Center 
				
					radio_button_uncheckedGESSINPool de Siniestros 
				
					radio_button_uncheckedPROGRAMADORPROGRAMADOR 
				
					radio_button_uncheckedRACRecurso de Apoyo a Cobranzas 
				
					radio_button_uncheckedRTESTRol de Test 
				
					radio_button_uncheckedSEGURSeguros 
				
					radio_button_uncheckedSKIPTSkip Trace 
				
					radio_button_uncheckedAISSoporte AIS149
				
					radio_button_uncheckedSUPCCSupervisor Call Center 
				
			

			
		
	
                                                    
                                                
                                            
                                        

                                    
	
                                            
                                                
		Usuarios
	
                                                
                                                    visibilityConsultar
                                                    createModificar
                                                    deleteEliminar
                                                
                                            
                                            
                                                
                                                    
		
			
				
					 CódigoDescripción
				
			
				
					radio_button_checked122
				
					radio_button_uncheckedAAAEAAAE
				
					radio_button_uncheckedddggddg
				
					radio_button_uncheckedJAYJAY
				
					radio_button_uncheckedPABLOUSUARIO TEST
				
					radio_button_uncheckedPABLO4PABLO44
				
					radio_button_uncheckedSUPERMANSUPERMAN
				
					radio_button_uncheckedVARELACVARELA CARLOS  ESTUDIO VARELA
				
					radio_button_uncheckedVILLARVILLAR JUAN PABLO
				
					radio_button_uncheckedWILLIMANWILLIMAN JOSE
				
					radio_button_uncheckedYANEZYA?`EZ RODOLFO
				
					radio_button_uncheckedYANEZAYAÑEZ ALVARO
				
			

			
		
	
                                                    
                                                
                                            
                                        

                                
                                
                                    
	
                                        
		
                                                
                                                    
                                                        
                                                            
			Modulos Disponibles
		
                                                        
                                                        
                                                            Seleccionar Todos
                                                            
                                                                addAñadir Permiso
                                                                grid_onExportar
                                                            
                                                        
                                                        
                                                            
                                                                
			
                                                                        
				
					
						10 - Cobranza Prejudicial
					
				
					
						
							11 - Agenda Personal
						
					
						
							12 - Busqueda de Clientes
						
					
						
							
								265 - Ver Solo Casos del Mismo Empleador
							
						
							
								267 - Ver Todos Los Casos
							
						
					
						
							120 - Detalle de Cliente
						
					
						
							
								122 - Ver Compromisos
							
						
							
								123 - Generar Compromisoso
							
						
							
								124 - Generar Convenio
							
						
							
								125 - Ver caso judicial
							
						
							
								126 - Ver Ficha
							
						
							
								25 - Convenios
							
						
							
								26 - Pasaje a Judicial
							
						
							
								366 - Gestionar Casos No Asignados
							
						
					
						
							13 - Supervision
						
					
						
							
								14 - Reasignacion Manual
							
						
					
						
							15 - Reportes Operativos
						
					
						
							
								17 - Distribución por Tipologia de Clientes
							
						
							
								18 - Distribución por Estrategia
							
						
							
								19 - Call Center
							
						
							
								22 - Distribución por Estados Especiales
							
						
							
								23 - Distribución por Rol y Nivel de Mora
							
						
							
								27 - otros Reportes
							
						
							
								74 - Informes
							
						
					
						
							20 - Agenda de Grupo
						
					
						
							24 - Pooles de Trabajo
						
					
						
							320 - Reportes OBI
						
					
						
							
								321 - Resumen Agenda
							
						
							
								322 - Gestión Rol y N.Mora
							
						
							
								323 - Gest. Tipo Cliente y N.Mora
							
						
							
								324 - Gest. Estrategia y N.Mora
							
						
							
								325 - Promeas de Pago
							
						
							
								326 - Risk Management
							
						
					
				
					
						200 - Administrador
					
				
					
						
							201 - Administración
						
					
						
							
								202 - Oficinas
							
						
							
								203 - Productos
							
						
							
								204 - Festivos
							
						
							
								205 - Tablas Generales
							
						
							
								
									362 - Crear y Modificar Roles
								
							
						
							
								206 - Conversión Monetaria
							
						
							
								207 - Multi-Mandante
							
						
							
								
									208 - Mandantes
								
							
								
									209 - Tablas Generales Multi-Mandante
								
							
						
							
								211 - Comisiones y Honorarios
							
						
							
								276 - Variables de Priorización de Agenda
							
						
							
								277 - Parámetros
							
						
					
						
							250 - Seguridad
						
					
						
							
								251 - Administración de Usuarios
							
						
							
								
									358 - Edición de Usuarios
								
							
								
									360 - Gestionar Permisos Roles
								
							
						
							
								252 - Parametría de Seguridad
							
						
							
								275 - Administración de Usuarios Judicial
							
						
							
								285 - Administración de Comisionistas
							
						
					
						
							263 - Estrategia
						
					
						
							
								260 - Judicial
							
						
							
								
									274 - Edición de TARs
								
							
								
									287 - Vinculación de Variables a GMR
								
							
								
									344 - Diseñador de procedimientos judiciales
								
							
						
							
								272 - Prejudicial
							
						
							
								
									262 - Edición de TARs
								
							
								
									
										359 - Asignar Permisos uso TARs
									
								
							
								
									264 - Diseñador de Flujos
								
							
								
									273 - Edición de Estrategias
								
							
								
									286 - Vinculación de Variables a GMR
								
							
								
									290 - Generar Archivo GMR Plus
								
							
								
									310 - Simulador de Estrategias
								
							
								
									311 - Diagnóstico de Evaluación
								
							
								
									341 - Simulador
								
							
								
									
										340 - Simulaciones unitarias
									
								
									
										342 - Simulaciones masivas
									
								
							
						
					
						
							300 - Herramientas
						
					
						
							
								301 - Generar Cartas...
							
						
							
								302 - Generar Fichas de Cobranzaa?|
							
						
							
								303 - Gestión de Nuevos Campos
							
						
					
				
					
						52 - Otras Funcionalidades
					
				
					
						
							108 - Añadir ficheros a Gestión
						
					
				
			
                                                                    
		
                                                            
                                                        
                                                    
                                                    
                                                        
                                                            
			Modulos Otorgados
		
                                                        
                                                        
                                                            Seleccionar Todos
                                                            
                                                                deleteQuitar Permiso
                                                            
                                                        
                                                        
                                                            
                                                                
			
                                                                        
				
					
						10 - Cobranza Prejudicial
					
				
					
						
							11 - Agenda Personal
						
					
						
							12 - Busqueda de Clientes
						
					
						
							
								265 - Ver Solo Casos del Mismo Empleador
							
						
							
								267 - Ver Todos Los Casos
							
						
					
						
							120 - Detalle de Cliente
						
					
						
							
								122 - Ver Compromisos
							
						
							
								123 - Generar Compromisoso
							
						
							
								124 - Generar Convenio
							
						
							
								125 - Ver caso judicial
							
						
							
								126 - Ver Ficha
							
						
							
								25 - Convenios
							
						
							
								26 - Pasaje a Judicial
							
						
							
								366 - Gestionar Casos No Asignados
							
						
					
						
							13 - Supervision
						
					
						
							
								14 - Reasignacion Manual
							
						
					
						
							15 - Reportes Operativos
						
					
						
							
								17 - Distribución por Tipologia de Clientes
							
						
							
								18 - Distribución por Estrategia
							
						
							
								19 - Call Center
							
						
							
								22 - Distribución por Estados Especiales
							
						
							
								23 - Distribución por Rol y Nivel de Mora
							
						
							
								27 - otros Reportes
							
						
							
								74 - Informes
							
						
					
						
							20 - Agenda de Grupo
						
					
						
							24 - Pooles de Trabajo
						
					
				
					
						200 - Administrador
					
				
					
						
							201 - Administración
						
					
						
							
								202 - Oficinas
							
						
							
								203 - Productos
							
						
							
								204 - Festivos
							
						
							
								205 - Tablas Generales
							
						
							
								
									362 - Crear y Modificar Roles
								
							
						
							
								206 - Conversión Monetaria
							
						
							
								207 - Multi-Mandante
							
						
							
								
									208 - Mandantes
								
							
								
									209 - Tablas Generales Multi-Mandante
								
							
						
							
								211 - Comisiones y Honorarios
							
						
							
								276 - Variables de Priorización de Agenda
							
						
							
								277 - Parámetros
							
						
					
						
							250 - Seguridad
						
					
						
							
								251 - Administración de Usuarios
							
						
							
								
									358 - Edición de Usuarios
								
							
								
									360 - Gestionar Permisos Roles
								
							
						
							
								252 - Parametría de Seguridad
							
						
							
								275 - Administración de Usuarios Judicial
							
						
							
								285 - Administración de Comisionistas
							
						
					
						
							263 - Estrategia
						
					
						
							
								260 - Judicial
							
						
							
								
									274 - Edición de TARs
								
							
								
									287 - Vinculación de Variables a GMR
								
							
								
									344 - Diseñador de procedimientos judiciales
								
							
						
							
								272 - Prejudicial
							
						
							
								
									262 - Edición de TARs
								
							
								
									
										359 - Asignar Permisos uso TARs
									
								
							
								
									264 - Diseñador de Flujos
								
							
								
									273 - Edición de Estrategias
								
							
								
									286 - Vinculación de Variables a GMR
								
							
								
									290 - Generar Archivo GMR Plus
								
							
						
					
						
							300 - Herramientas
						
					
						
							
								301 - Generar Cartas...
							
						
							
								302 - Generar Fichas de Cobranzaa?|
							
						
							
								303 - Gestión de Nuevos Campos
							
						
					
				
					
						343 - SEPARADOR
					
				
					
						52 - Otras Funcionalidades
					
				
					
						
							108 - Añadir ficheros a Gestión
						
					
				
			
                                                                    
		
                                                            
                                                        
                                                    
                                                
                                            
	
                                    

                                
                            
                        
                
		
			
                    
                            
                                
                                    
	
                                        
                                            Ver Usuarios dados de Baja
                                            filter_altBuscar Usuarios 
                                            
                                                grid_onUsuarios
                                            
                                        
                                        
                                            
                                                
		
                                                        
			
				
					
						 CódigoDescripción
					
				
					
						radio_button_checked122
					
						radio_button_unchecked1011
					
						radio_button_unchecked233
					
						radio_button_unchecked344
					
						radio_button_unchecked444
					
						radio_button_unchecked566
					
						radio_button_unchecked5001
					
						radio_button_unchecked501501
					
						radio_button_unchecked600AIS PROGRAMADOR 1
					
						radio_button_unchecked899
					
						radio_button_unchecked800Jefe de proyecto 1
					
						radio_button_uncheckedA100A 100
					
						radio_button_uncheckedaaaatest
					
						radio_button_uncheckedAAAEAAAE
					
						radio_button_uncheckedAAAFAAAF
					
						radio_button_uncheckedAAAGAAAG
					
						radio_button_uncheckedAAARAAAR
					
						radio_button_uncheckedAABAAABA
					
						radio_button_uncheckedAABBAABB
					
						radio_button_uncheckedAABCAABC
					
						radio_button_uncheckedAACCaaa
					
						radio_button_uncheckedAISMMMireia (AIS)
					
						radio_button_uncheckedANDAN22
					
						radio_button_uncheckedARRIETAARRIETA PABLO
					
						radio_button_uncheckedASDASD
					
						radio_button_uncheckedBACHECHIBACHECHI, GONZALO  ESTUDIO BACHECHI441
					
						radio_button_uncheckedBANYASZBANYASZ FLORENCIA1
					
						radio_button_uncheckedBARCIALBARCIA, Lucía
					
						radio_button_uncheckedBARQUINBARQUIN VALIENTE, ALFONSO 
					
						radio_button_uncheckedBELENBELEN MANUEL
					
						radio_button_uncheckedBELLAGAMBABELLAGAMBA FABRICIO1
					
						radio_button_uncheckedBERRIELBERRIEL FIORELLA11123123
					
						radio_button_uncheckedBOCCARDIBOCCARDI DIEGO
					
						radio_button_uncheckedBOLSASUSUARIO TEST 2
					
						radio_button_uncheckedC}
					
						radio_button_uncheckedCALLORDACALLORDA PEREZ, Eliana Paula
					
						radio_button_uncheckedCASAGRANDECASAGRANDE MAURICIO
					
						radio_button_uncheckedCASTROMCASTRO MARTIN
					
						radio_button_uncheckedCAVIGLIACAVIGLIA OSCAR
					
						radio_button_uncheckedCGMYACGMyA
					
						radio_button_uncheckedCHARBONNIECHARBONNIER LISSETTE
					
						radio_button_uncheckedcjzouCaijie
					
						radio_button_uncheckedCOLLCOLL GONZALO2
					
						radio_button_uncheckedCOLOMBICOLOMBI MARCELO
					
						radio_button_uncheckedCOLOMBODCOLOMBO DANIEL
					
						radio_button_uncheckedCRESPICRESPI GONZALO
					
						radio_button_uncheckedCUADROCUADRO OVIEDO, Andrea Antonella
					
						radio_button_uncheckedddggddg
					
						radio_button_uncheckedDELEONLDE LEON LEONARDO
					
						radio_button_uncheckedDIAZSADÍAZ VARELA, Stefani Anabella
					
						radio_button_uncheckedESPESP
					
						radio_button_uncheckedESTIGARRIBESTIGARRIBIA SCALVINO, Victoria
					
						radio_button_uncheckedESTRELLADE MAR
					
						radio_button_uncheckedFERNANDEZMFERNANDEZ MARIA PIA
					
						radio_button_uncheckedFERNANDEZPFERNANDEZ PISCIOTTANO, Ana Camila
					
						radio_button_uncheckedFERREREFERRERE
					
						radio_button_uncheckedFERREYRAFERREYRA MASDEU, María Matilde
					
						radio_button_uncheckedFILLATFILLAT SOFIA
					
						radio_button_uncheckedFONTOURAFONTOURA MELLO, Maira Natalie
					
						radio_button_uncheckedFRECHOUFRECHOU FLORENCIA
					
						radio_button_uncheckedFUSTERFUSTER ALVARO
					
						radio_button_uncheckedGADEAGADEA MARIA NOEL
					
						radio_button_uncheckedGOMEZGOMEZ ANDRES
					
						radio_button_uncheckedGOMEZSGOMEZ PLATERO SOFIA
					
						radio_button_uncheckedGUSTAVOGUSTAVO
					
						radio_button_uncheckedGUTIERREZNGutierrez Bas, Natalia Vanessa
					
						radio_button_uncheckedHUERTASHUERTAS LAURA
					
						radio_button_uncheckedHUGOHUGO FERNANDEZ, JUAN PABLO 
					
						radio_button_uncheckedIZETTAIZETTA MAURICIO
					
						radio_button_uncheckedJAYJAY
					
						radio_button_uncheckedKEVINKEVIN
					
						radio_button_uncheckedLAGOSLAGOS MEDEIROS, Camila Yamisel
					
						radio_button_uncheckedLAPILAPI MARIA JOSE
					
						radio_button_uncheckedLOPEZCLOPEZ CAROLINA
					
						radio_button_uncheckedLoremLorem
					
						radio_button_uncheckedMANASMAÑAS ALEXIS
					
						radio_button_uncheckedMARINOMARIÑO IGNACIO
					
						radio_button_uncheckedMASSATMASSAT AGUSTINA
					
						radio_button_uncheckedMAYAMAYA AGUSTINA
					
						radio_button_uncheckedMIHALIKMIHALIK FERNANDO
					
						radio_button_uncheckedMIRANDAMIRANDA CARLOS
					
						radio_button_uncheckedMONTOSSIMONTOSSI RAUL
					
						radio_button_uncheckedMOREIRAMMOREIRA MARIA NOEL
					
						radio_button_uncheckedMOYPCMOyPC
					
						radio_button_uncheckedNBK1C2RMILES PAMELA
					
						radio_button_uncheckedNBK1O9HLIZARRAGA GONZALO
					
						radio_button_uncheckedNBK2PTMMOLINARI MARTIN
					
						radio_button_uncheckedNBK31EVTORNQUIST JORGE
					
						radio_button_uncheckedNBK34HLCORREA JORGE
					
						radio_button_uncheckedNBK54NSHERNANDEZ GUSTAVO
					
						radio_button_uncheckedNBK5TAQMASSEILOT JOAQUIN
					
						radio_button_uncheckedNBK68OWBARRIOS VERONICA112119
					
						radio_button_uncheckedNBK7IBISAPIURKA FABIAN222
					
						radio_button_uncheckedNBK8S7JANTUNEZ JULIO
					
						radio_button_uncheckedNBK95LKARECHAVALETA IGNACIO
					
						radio_button_uncheckedNBK9UJRRADO MARCELLO
					
						radio_button_uncheckedNBKDWWUMUTIO JUAN MANUEL
					
						radio_button_uncheckedNBKE27XGROSSO MARY
					
						radio_button_uncheckedNBKE72HPONTE ENRIQUE
					
						radio_button_uncheckedNBKFE5TREY OMAR
					
						radio_button_uncheckedNBKG3KCQUEIROLO JAIME
					
						radio_button_uncheckedNBKI19GBALADAN SANTIAGO
					
						radio_button_uncheckedNBKK3CEOTEGUI ANDRES
					
						radio_button_uncheckedNBKKP3ESANTAMARINA CARLOS
					
						radio_button_uncheckedNBKKU8IMOREIRA PEDRO
					
						radio_button_uncheckedNBKM3ACBONDONI EDUARDO
					
						radio_button_uncheckedNBKOF8FPONASSO VIRGINIA
					
						radio_button_uncheckedNBKP41XMANTA DANIEL
					
						radio_button_uncheckedNBKQ7SWGROLLA ALVARO
					
						radio_button_uncheckedNBKSJ2YREY SANTIAGO
					
						radio_button_uncheckedNBKV2UPMEZZERA FEDERICO
					
						radio_button_uncheckedNBKWC9EDELFINO ALVARO
					
						radio_button_uncheckedNBKYUGRMILAN PATRICIA
					
						radio_button_uncheckedNBKZ25CBRUN JULIO
					
						radio_button_uncheckedNBKZE2WCARLUCCIO PATRICIA
					
						radio_button_uncheckedNOTTENOTTE MARCELO
					
						radio_button_uncheckedOTEGUIMOTEGUI MARIA ELENA
					
						radio_button_uncheckedPABLOUSUARIO TEST
					
						radio_button_uncheckedPABLO2PABLO22
					
						radio_button_uncheckedPABLO3PABLO3
					
						radio_button_uncheckedPABLO4PABLO44
					
						radio_button_uncheckedPABLO5PÀBLO5
					
						radio_button_uncheckedPABLO6PABLO6
					
						radio_button_uncheckedPACIFICOPACIFICO
					
						radio_button_uncheckedPALMEROPALMERO
					
						radio_button_uncheckedPEPITOA
					
						radio_button_uncheckedPEREIRAIPEREIRA ISABEL
					
						radio_button_uncheckedPIASTRILUCIANA PIASTRI 22222
					
						radio_button_uncheckedPIZZORNOFPIZZORNO FERNANDA
					
						radio_button_uncheckedQQW11
					
						radio_button_uncheckedqwqw
					
						radio_button_uncheckedRAMISRAMIS FEDERICO
					
						radio_button_uncheckedRASNERRASNER NICOLAS
					
						radio_button_uncheckedRDRD
					
						radio_button_uncheckedROCCASROCCA STEFANIA
					
						radio_button_uncheckedRODRIGUEZMRODRIGUEZ BORGES, Marcelo
					
						radio_button_uncheckedROTONDOROTONDO MAGELA
					
						radio_button_uncheckedSANCHEZALBSANCHEZ ALBERTO
					
						radio_button_uncheckedSANCHEZROSANCHEZ RODRIGO
					
						radio_button_uncheckedSANZSANZ ALEJANDRA1
					
						radio_button_uncheckedSBROCCASBROCCA PABLO
					
						radio_button_uncheckedSELHAYSELHAY CAROLINA
					
						radio_button_uncheckedSICARDISICARDI JUAN CARLOS
					
						radio_button_uncheckedSOLAROSOLARO ROSARIO
					
						radio_button_uncheckedSOSAJJSOSA JUAN JOSE
					
						radio_button_uncheckedSOUZASOUZA BARRETO, Juliana
					
						radio_button_uncheckedSTAZIONESTAZIONE FERNANDEZ, Paola Antonella
					
						radio_button_uncheckedSUPERMANSUPERMAN
					
						radio_button_uncheckedTESTtest
					
						radio_button_uncheckedTEST1TEST1
					
						radio_button_uncheckedTEST2ASD
					
						radio_button_uncheckedTEST3TEST3
					
						radio_button_uncheckedtesterUserTester
					
						radio_button_uncheckedTOBLERTOBLER ELIZABETH
					
						radio_button_uncheckedUSER1TEST USER
					
						radio_button_uncheckedusernuevoprueba1user nuevo pruba 2
					
						radio_button_uncheckedusertest2usuario test 2
					
						radio_button_uncheckedUSITAUsuario ITALIA
					
						radio_button_uncheckedUSUPRUEBAUSUARIO DE PRUEBA
					
						radio_button_uncheckedVARELACVARELA CARLOS  ESTUDIO VARELA
					
						radio_button_uncheckedVGGAIS VICTOR
					
						radio_button_uncheckedVILLALBAVILLALBA GUZMAN
					
						radio_button_uncheckedVILLARVILLAR JUAN PABLO
					
						radio_button_uncheckedWILLIMANWILLIMAN JOSE
					
						radio_button_uncheckedYANEZYA?`EZ RODOLFO
					
						radio_button_uncheckedYANEZAYAÑEZ ALVARO
					
				

				
			
		
                                                    
	
                                            
                                        
                                    

                                
                                
                                    
                                            
	Usuario
                                                
                                                    Código 
                                                    Nombre 
                                                    Fecha Baja 
                                                
                                                
                                                    Estado 
                                                    Idioma 
                                                    Empleador 
                                                    Sucursal 
                                                
                                                
                                                    Teléfono 
                                                    Interno 
                                                    Max Lotes 
                                                    Número Documento 
                                                
                                                
                                                    Superior 
                                                    Email 
                                                
                                                
                                                    
                                                        addAgregar
                                                        createModificar
                                                        lock_openDesbloquear
                                                        passwordCambio Password
                                                    
                                                
                                            

                                            
	Perfil
                                                
                                                    
                                                        
                                                            filter_altBuscador Perfil 
                                                        
                                                    
                                                    
                                                        addAgregar Perfil
                                                        visibilityConsultar Perfil
                                                        createModificar Perfil
                                                        content_copyCopiar Perfiles a...
                                                        deleteEliminar Perfil
                                                    
                                                
                                                
                                                    
                                                        
		
			
				
					 CódigoDescripciónFecha AltaFecha Baja
				
			
				
					radio_button_checkedBOTCBackoffice Tarjetas de Credito19/07/2024 
				
			

			
		
	
                                                    
                                                
                                            

                                        
                                
                            
                        
                
		
            
                    
	
		
	Usuario
                            
                                Código * Código obligatorio 
                                Nombre * 
                                Fecha Baja 
                            
                            
                                Estado Seleccione un valorActivoInactivoPeriodo de VacacionesActivo  
                                Idioma Seleccione un valorEspanolInglésItaliaNativoSeleccione un valor  
                                Empleador * Seleccione un valor0001 - Empresa 1001 - Call Valparaiso0010 - Empleador Seguros0011 - Agencia Externa 1002 - UCE003 - Terreno004 - Terreno Asistido12 - Agencia Externa 213 - Agencia Externa 30011 - Agencia Externa 1  
                                Sucursal Seleccione un valorSeleccione un valor  
                            
                            
                                Teléfono 
                                Interno 
                                Máx Lotes * 
                                Número Documento 
                            
                            
                                Superior Seleccione1 - 2210 - 112 - 333 - 444 - 445 - 66500 - 1501 - 501600 - AIS PROGRAMADOR 18 - 99800 - Jefe de proyecto 1A100 - A 100aaaa - testAAAE - AAAEAAAF - AAAFAAAG - AAAGAAAR - AAARAABA - AABAAABB - AABBAABC - AABCAACC - aaaAISMM - Mireia (AIS)ANDAN - 22ARRIETA - ARRIETA PABLOASD - ASDBACHECHI - BACHECHI, GONZALO  ESTUDIO BACHECHI441BANYASZ - BANYASZ FLORENCIA1BARCIAL - BARCIA, LucíaBARQUIN - BARQUIN VALIENTE, ALFONSO BELEN - BELEN MANUELBELLAGAMBA - BELLAGAMBA FABRICIO1BERRIEL - BERRIEL FIORELLA11123123BOCCARDI - BOCCARDI DIEGOBOLSAS - USUARIO TEST 2C - }CALLORDA - CALLORDA PEREZ, Eliana PaulaCASAGRANDE - CASAGRANDE MAURICIOCASTROM - CASTRO MARTINCAVIGLIA - CAVIGLIA OSCARCGMYA - CGMyACHARBONNIE - CHARBONNIER LISSETTEcjzou - CaijieCOLL - COLL GONZALO2COLOMBI - COLOMBI MARCELOCOLOMBOD - COLOMBO DANIELCRESPI - CRESPI GONZALOCUADRO - CUADRO OVIEDO, Andrea Antonelladdgg - ddgDELEONL - DE LEON LEONARDODIAZSA - DÍAZ VARELA, Stefani AnabellaESP - ESPESTIGARRIB - ESTIGARRIBIA SCALVINO, VictoriaESTRELLA - DE MARFERNANDEZM - FERNANDEZ MARIA PIAFERNANDEZP - FERNANDEZ PISCIOTTANO, Ana CamilaFERRERE - FERREREFERREYRA - FERREYRA MASDEU, María MatildeFILLAT - FILLAT SOFIAFONTOURA - FONTOURA MELLO, Maira NatalieFRECHOU - FRECHOU FLORENCIAFUSTER - FUSTER ALVAROGADEA - GADEA MARIA NOELGOMEZ - GOMEZ ANDRESGOMEZS - GOMEZ PLATERO SOFIAGUSTAVO - GUSTAVOGUTIERREZN - Gutierrez Bas, Natalia VanessaHUERTAS - HUERTAS LAURAHUGO - HUGO FERNANDEZ, JUAN PABLO IZETTA - IZETTA MAURICIOJAY - JAYKEVIN - KEVINLAGOS - LAGOS MEDEIROS, Camila YamiselLAPI - LAPI MARIA JOSELOPEZC - LOPEZ CAROLINALorem - LoremMANAS - MAÑAS ALEXISMARINO - MARIÑO IGNACIOMASSAT - MASSAT AGUSTINAMAYA - MAYA AGUSTINAMIHALIK - MIHALIK FERNANDOMIRANDA - MIRANDA CARLOSMONTOSSI - MONTOSSI RAULMOREIRAM - MOREIRA MARIA NOELMOYPC - MOyPCNBK1C2R - MILES PAMELANBK1O9H - LIZARRAGA GONZALONBK2PTM - MOLINARI MARTINNBK31EV - TORNQUIST JORGENBK34HL - CORREA JORGENBK54NS - HERNANDEZ GUSTAVONBK5TAQ - MASSEILOT JOAQUINNBK68OW - BARRIOS VERONICA112119NBK7IBI - SAPIURKA FABIAN222NBK8S7J - ANTUNEZ JULIONBK95LK - ARECHAVALETA IGNACIONBK9UJR - RADO MARCELLONBKDWWU - MUTIO JUAN MANUELNBKE27X - GROSSO MARYNBKE72H - PONTE ENRIQUENBKFE5T - REY OMARNBKG3KC - QUEIROLO JAIMENBKI19G - BALADAN SANTIAGONBKK3CE - OTEGUI ANDRESNBKKP3E - SANTAMARINA CARLOSNBKKU8I - MOREIRA PEDRONBKM3AC - BONDONI EDUARDONBKOF8F - PONASSO VIRGINIANBKP41X - MANTA DANIELNBKQ7SW - GROLLA ALVARONBKSJ2Y - REY SANTIAGONBKV2UP - MEZZERA FEDERICONBKWC9E - DELFINO ALVARONBKYUGR - MILAN PATRICIANBKZ25C - BRUN JULIONBKZE2W - CARLUCCIO PATRICIANOTTE - NOTTE MARCELOOTEGUIM - OTEGUI MARIA ELENAPABLO - USUARIO TESTPABLO2 - PABLO22PABLO3 - PABLO3PABLO4 - PABLO44PABLO5 - PÀBLO5PABLO6 - PABLO6PACIFICO - PACIFICOPALMERO - PALMEROPEPITO - APEREIRAI - PEREIRA ISABELPIASTRI - LUCIANA PIASTRI 22222PIZZORNOF - PIZZORNO FERNANDAQQW - 11qw - qwRAMIS - RAMIS FEDERICORASNER - RASNER NICOLASRD - RDROCCAS - ROCCA STEFANIARODRIGUEZM - RODRIGUEZ BORGES, MarceloROTONDO - ROTONDO MAGELASANCHEZALB - SANCHEZ ALBERTOSANCHEZRO - SANCHEZ RODRIGOSANZ - SANZ ALEJANDRA1SBROCCA - SBROCCA PABLOSELHAY - SELHAY CAROLINASICARDI - SICARDI JUAN CARLOSSOLARO - SOLARO ROSARIOSOSAJJ - SOSA JUAN JOSESOUZA - SOUZA BARRETO, JulianaSTAZIONE - STAZIONE FERNANDEZ, Paola AntonellaSUPERMAN - SUPERMANTEST - testTEST1 - TEST1TEST2 - ASDTEST3 - TEST3testerUser - TesterTOBLER - TOBLER ELIZABETHUSER1 - TEST USERusernuevoprueba1 - user nuevo pruba 2usertest2 - usuario test 2USITA - Usuario ITALIAUSUPRUEBA - USUARIO DE PRUEBAVARELAC - VARELA CARLOS  ESTUDIO VARELAVGG - AIS VICTORVILLALBA - VILLALBA GUZMANVILLAR - VILLAR JUAN PABLOWILLIMAN - WILLIMAN JOSEYANEZ - YA?`EZ RODOLFOYANEZA - YAÑEZ ALVAROSeleccione  
                                Email 
                            
                        

	
                            Guardar
                            Cerrar
                        

	

                
            
			
                    

			
                
		
            
			
                    

			
                
		
            
			
                    

			
                
		
            
			
                    

			
                
		
        
	

        
        
    


	


    
        
        
            
                
                    
                
                
                    
                
                
                    
                
            
        
    


Guardar"

```

# Page snapshot

```yaml
- generic [ref=e1]:
  - generic [ref=e2]:
    - navigation [ref=e3]:
      - generic [ref=e4]:
        - list [ref=e5]:
          - listitem [ref=e6]:
            - link "menu" [ref=e7] [cursor=pointer]:
              - /url: "#"
              - generic: menu
        - generic [ref=e8]:
          - img [ref=e9]
          - img [ref=e10]
        - generic [ref=e11]:
          - generic [ref=e13] [cursor=pointer]:
            - generic: logout
            - text: Salir
          - img [ref=e14]
        - generic [ref=e15]: Seguridad Prejudicial
        - generic [ref=e17]:
          - generic [ref=e18]:
            - generic [ref=e19]: "Usuario:"
            - generic [ref=e20]: USUARIO TEST
          - generic [ref=e22]:
            - generic [ref=e23]: "Pendiente de Hoy:"
            - generic [ref=e24]: "0"
          - generic [ref=e26]:
            - generic [ref=e27]: "Pendiente de otros Días:"
            - generic [ref=e28]: "1"
          - generic [ref=e30]:
            - generic [ref=e31]: "Realizado Hoy:"
            - generic [ref=e32]: "1"
          - generic [ref=e34]:
            - generic [ref=e35]: "Total en Agenda:"
            - generic [ref=e36]: "2"
          - generic [ref=e38]:
            - generic [ref=e39]: "Barrido Realizado:"
            - generic [ref=e40]: 50%
          - generic [ref=e42]:
            - generic [ref=e43]: "Clientes Asignados:"
            - generic [ref=e44]: "10430"
    - list [ref=e45]:
      - listitem [ref=e46]:
        - generic [ref=e47]:
          - generic: format_list_bulleted
          - text: Cobranza Prejudicial
        - list [ref=e49]:
          - listitem [ref=e50]:
            - link "event Agenda Personal" [ref=e51] [cursor=pointer]:
              - /url: /AgendaWeb/FrmAgenda.aspx
              - generic: event
              - text: Agenda Personal
          - listitem [ref=e52]:
            - link "event_note Pooles de Trabajo" [ref=e53] [cursor=pointer]:
              - /url: /AgendaWeb/FrmAgenda.aspx?q=rh3wPkybH+atHWY9zjvV4w==
              - generic: event_note
              - text: Pooles de Trabajo
          - listitem [ref=e54]:
            - link "search Busqueda de Clientes" [ref=e55] [cursor=pointer]:
              - /url: /AgendaWeb/FrmBusqueda.aspx
              - generic: search
              - text: Busqueda de Clientes
          - listitem [ref=e56]:
            - link "date_range Agenda de Grupo" [ref=e57] [cursor=pointer]:
              - /url: /AgendaWeb/FrmAgendaEquipo.aspx
              - generic: date_range
              - text: Agenda de Grupo
          - listitem [ref=e58]:
            - list [ref=e59]:
              - listitem [ref=e60]:
                - generic [ref=e61] [cursor=pointer]:
                  - generic: format_list_bulleted
                  - text: Supervision
              - listitem [ref=e62]:
                - list [ref=e63]:
                  - listitem [ref=e64]:
                    - generic [ref=e65] [cursor=pointer]:
                      - generic: format_list_bulleted
                      - text: Reportes Operativos
      - listitem [ref=e66]:
        - generic [ref=e67]:
          - generic: format_list_bulleted
          - text: Cobranza Judicial
        - list [ref=e69]:
          - listitem [ref=e70]:
            - link "event Agenda De Demandas" [ref=e71] [cursor=pointer]:
              - /url: /AgendaWeb/FrmAgendaJudicial.aspx
              - generic: event
              - text: Agenda De Demandas
          - listitem [ref=e72]:
            - link "search Buscar Demandas" [ref=e73] [cursor=pointer]:
              - /url: /AgendaWeb/FrmBusquedaJudicial.aspx
              - generic: search
              - text: Buscar Demandas
          - listitem [ref=e74]:
            - link "rule Validar Gastos" [ref=e75] [cursor=pointer]:
              - /url: /AgendaWeb/FrmValidacionGastosJudicial.aspx
              - generic: rule
              - text: Validar Gastos
          - listitem [ref=e76]:
            - link "confirmation_number Liquidar Gastos" [ref=e77] [cursor=pointer]:
              - /url: /AgendaWeb/FrmLiquidarGastos.aspx
              - generic: confirmation_number
              - text: Liquidar Gastos
          - listitem [ref=e78]:
            - link "switch_account Reasignar Abogado" [ref=e79] [cursor=pointer]:
              - /url: /AgendaWeb/FrmJReasignarAbogado.aspx
              - generic: switch_account
              - text: Reasignar Abogado
          - listitem [ref=e80]:
            - list [ref=e81]:
              - listitem [ref=e82]:
                - generic [ref=e83] [cursor=pointer]:
                  - generic: format_list_bulleted
                  - text: Reportes Operativos
              - listitem [ref=e84]:
                - list [ref=e85]:
                  - listitem [ref=e86]:
                    - generic [ref=e87] [cursor=pointer]:
                      - generic: format_list_bulleted
                      - text: Reportes OBI
      - listitem [ref=e88]:
        - generic [ref=e89]:
          - generic: format_list_bulleted
          - text: Facturación y Gastos
        - list [ref=e91]:
          - listitem [ref=e92]:
            - link "rule Validar Facturas" [ref=e93] [cursor=pointer]:
              - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FiScu1K/9opoNFBT3rUlgpvM=
              - generic: rule
              - text: Validar Facturas
          - listitem [ref=e94]:
            - link "rule Validar Notas de Gastos" [ref=e95] [cursor=pointer]:
              - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FieWKk8YQotwBcHU/2DP3KIw=
              - generic: rule
              - text: Validar Notas de Gastos
          - listitem [ref=e96]:
            - link "receipt Facturas" [ref=e97] [cursor=pointer]:
              - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiHOOp6prF5Vq+94RnI70taQ=
              - generic: receipt
              - text: Facturas
          - listitem [ref=e98]:
            - link "confirmation_number Notas de Gastos" [ref=e99] [cursor=pointer]:
              - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiEmPUsCvT75NbJGKOtz0/0Y=
              - generic: confirmation_number
              - text: Notas de Gastos
      - listitem [ref=e100]:
        - separator [ref=e101]
      - listitem [ref=e102]:
        - link "settings Administrador" [ref=e103] [cursor=pointer]:
          - /url: /AgendaWeb/FrmAdministrador.aspx
          - generic: settings
          - text: Administrador
      - listitem [ref=e104]
      - listitem [ref=e105]
    - generic [ref=e106]:
      - link "chevron_left administrador" [ref=e110] [cursor=pointer]:
        - /url: javascript:__doPostBack('ctl00$btnBack','')
        - generic: chevron_left
        - text: administrador
      - generic [ref=e112]:
        - list [ref=e114]:
          - listitem [ref=e115]:
            - link "Roles" [ref=e116] [cursor=pointer]:
              - /url: "#c_tabRol"
          - listitem [ref=e117]:
            - link "Usuarios" [ref=e118] [cursor=pointer]:
              - /url: "#c_tabUsuario"
          - listitem [ref=e119]
        - generic [ref=e122]:
          - generic [ref=e124]:
            - generic [ref=e125]:
              - generic [ref=e126]:
                - checkbox "Ver Usuarios dados de Baja"
                - generic [ref=e127] [cursor=pointer]: Ver Usuarios dados de Baja
              - generic [ref=e128]:
                - textbox "Buscar Usuarios" [ref=e129]
                - generic [ref=e130] [cursor=pointer]:
                  - generic: filter_alt
                - generic [ref=e131]: Buscar Usuarios
              - link "grid_on Usuarios" [ref=e133] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$btnExportExcelUsuarios','')
                - generic: grid_on
                - text: Usuarios
            - table [ref=e138]:
              - rowgroup [ref=e139]:
                - row "Código Descripción" [ref=e140]:
                  - columnheader [ref=e141]
                  - columnheader "Código" [ref=e142]:
                    - link "Código" [ref=e143] [cursor=pointer]:
                      - /url: javascript:__doPostBack('ctl00$c$GridUsuario','Sort$CODIGO')
                  - columnheader "Descripción" [ref=e144]:
                    - link "Descripción" [ref=e145] [cursor=pointer]:
                      - /url: javascript:__doPostBack('ctl00$c$GridUsuario','Sort$DESCRIPCION')
              - rowgroup [ref=e146]:
                - row "radio_button_checked 1 22" [ref=e147]:
                  - cell "radio_button_checked" [ref=e148] [cursor=pointer]:
                    - generic [ref=e149]: radio_button_checked
                  - cell "1" [ref=e150] [cursor=pointer]
                  - cell "22" [ref=e151] [cursor=pointer]
                - row "radio_button_unchecked 10 11" [ref=e152]:
                  - cell "radio_button_unchecked" [ref=e153] [cursor=pointer]:
                    - generic [ref=e154]: radio_button_unchecked
                  - cell "10" [ref=e155] [cursor=pointer]
                  - cell "11" [ref=e156] [cursor=pointer]
                - row "radio_button_unchecked 2 33" [ref=e157]:
                  - cell "radio_button_unchecked" [ref=e158] [cursor=pointer]:
                    - generic [ref=e159]: radio_button_unchecked
                  - cell "2" [ref=e160] [cursor=pointer]
                  - cell "33" [ref=e161] [cursor=pointer]
                - row "radio_button_unchecked 3 44" [ref=e162]:
                  - cell "radio_button_unchecked" [ref=e163] [cursor=pointer]:
                    - generic [ref=e164]: radio_button_unchecked
                  - cell "3" [ref=e165] [cursor=pointer]
                  - cell "44" [ref=e166] [cursor=pointer]
                - row "radio_button_unchecked 4 44" [ref=e167]:
                  - cell "radio_button_unchecked" [ref=e168] [cursor=pointer]:
                    - generic [ref=e169]: radio_button_unchecked
                  - cell "4" [ref=e170] [cursor=pointer]
                  - cell "44" [ref=e171] [cursor=pointer]
                - row "radio_button_unchecked 5 66" [ref=e172]:
                  - cell "radio_button_unchecked" [ref=e173] [cursor=pointer]:
                    - generic [ref=e174]: radio_button_unchecked
                  - cell "5" [ref=e175] [cursor=pointer]
                  - cell "66" [ref=e176] [cursor=pointer]
                - row "radio_button_unchecked 500 1" [ref=e177]:
                  - cell "radio_button_unchecked" [ref=e178] [cursor=pointer]:
                    - generic [ref=e179]: radio_button_unchecked
                  - cell "500" [ref=e180] [cursor=pointer]
                  - cell "1" [ref=e181] [cursor=pointer]
                - row "radio_button_unchecked 501 501" [ref=e182]:
                  - cell "radio_button_unchecked" [ref=e183] [cursor=pointer]:
                    - generic [ref=e184]: radio_button_unchecked
                  - cell "501" [ref=e185] [cursor=pointer]
                  - cell "501" [ref=e186] [cursor=pointer]
                - row "radio_button_unchecked 600 AIS PROGRAMADOR 1" [ref=e187]:
                  - cell "radio_button_unchecked" [ref=e188] [cursor=pointer]:
                    - generic [ref=e189]: radio_button_unchecked
                  - cell "600" [ref=e190] [cursor=pointer]
                  - cell "AIS PROGRAMADOR 1" [ref=e191] [cursor=pointer]
                - row "radio_button_unchecked 8 99" [ref=e192]:
                  - cell "radio_button_unchecked" [ref=e193] [cursor=pointer]:
                    - generic [ref=e194]: radio_button_unchecked
                  - cell "8" [ref=e195] [cursor=pointer]
                  - cell "99" [ref=e196] [cursor=pointer]
                - row "radio_button_unchecked 800 Jefe de proyecto 1" [ref=e197]:
                  - cell "radio_button_unchecked" [ref=e198] [cursor=pointer]:
                    - generic [ref=e199]: radio_button_unchecked
                  - cell "800" [ref=e200] [cursor=pointer]
                  - cell "Jefe de proyecto 1" [ref=e201] [cursor=pointer]
                - row "radio_button_unchecked A100 A 100" [ref=e202]:
                  - cell "radio_button_unchecked" [ref=e203] [cursor=pointer]:
                    - generic [ref=e204]: radio_button_unchecked
                  - cell "A100" [ref=e205] [cursor=pointer]
                  - cell "A 100" [ref=e206] [cursor=pointer]
                - row "radio_button_unchecked aaaa test" [ref=e207]:
                  - cell "radio_button_unchecked" [ref=e208] [cursor=pointer]:
                    - generic [ref=e209]: radio_button_unchecked
                  - cell "aaaa" [ref=e210] [cursor=pointer]
                  - cell "test" [ref=e211] [cursor=pointer]
                - row "radio_button_unchecked AAAE AAAE" [ref=e212]:
                  - cell "radio_button_unchecked" [ref=e213] [cursor=pointer]:
                    - generic [ref=e214]: radio_button_unchecked
                  - cell "AAAE" [ref=e215] [cursor=pointer]
                  - cell "AAAE" [ref=e216] [cursor=pointer]
                - row "radio_button_unchecked AAAF AAAF" [ref=e217]:
                  - cell "radio_button_unchecked" [ref=e218] [cursor=pointer]:
                    - generic [ref=e219]: radio_button_unchecked
                  - cell "AAAF" [ref=e220] [cursor=pointer]
                  - cell "AAAF" [ref=e221] [cursor=pointer]
                - row "radio_button_unchecked AAAG AAAG" [ref=e222]:
                  - cell "radio_button_unchecked" [ref=e223] [cursor=pointer]:
                    - generic [ref=e224]: radio_button_unchecked
                  - cell "AAAG" [ref=e225] [cursor=pointer]
                  - cell "AAAG" [ref=e226] [cursor=pointer]
                - row "radio_button_unchecked AAAR AAAR" [ref=e227]:
                  - cell "radio_button_unchecked" [ref=e228] [cursor=pointer]:
                    - generic [ref=e229]: radio_button_unchecked
                  - cell "AAAR" [ref=e230] [cursor=pointer]
                  - cell "AAAR" [ref=e231] [cursor=pointer]
                - row "radio_button_unchecked AABA AABA" [ref=e232]:
                  - cell "radio_button_unchecked" [ref=e233] [cursor=pointer]:
                    - generic [ref=e234]: radio_button_unchecked
                  - cell "AABA" [ref=e235] [cursor=pointer]
                  - cell "AABA" [ref=e236] [cursor=pointer]
                - row "radio_button_unchecked AABB AABB" [ref=e237]:
                  - cell "radio_button_unchecked" [ref=e238] [cursor=pointer]:
                    - generic [ref=e239]: radio_button_unchecked
                  - cell "AABB" [ref=e240] [cursor=pointer]
                  - cell "AABB" [ref=e241] [cursor=pointer]
                - row "radio_button_unchecked AABC AABC" [ref=e242]:
                  - cell "radio_button_unchecked" [ref=e243] [cursor=pointer]:
                    - generic [ref=e244]: radio_button_unchecked
                  - cell "AABC" [ref=e245] [cursor=pointer]
                  - cell "AABC" [ref=e246] [cursor=pointer]
                - row "radio_button_unchecked AACC aaa" [ref=e247]:
                  - cell "radio_button_unchecked" [ref=e248] [cursor=pointer]:
                    - generic [ref=e249]: radio_button_unchecked
                  - cell "AACC" [ref=e250] [cursor=pointer]
                  - cell "aaa" [ref=e251] [cursor=pointer]
                - row "radio_button_unchecked AISMM Mireia (AIS)" [ref=e252]:
                  - cell "radio_button_unchecked" [ref=e253] [cursor=pointer]:
                    - generic [ref=e254]: radio_button_unchecked
                  - cell "AISMM" [ref=e255] [cursor=pointer]
                  - cell "Mireia (AIS)" [ref=e256] [cursor=pointer]
                - row "radio_button_unchecked ANDAN 22" [ref=e257]:
                  - cell "radio_button_unchecked" [ref=e258] [cursor=pointer]:
                    - generic [ref=e259]: radio_button_unchecked
                  - cell "ANDAN" [ref=e260] [cursor=pointer]
                  - cell "22" [ref=e261] [cursor=pointer]
                - row "radio_button_unchecked ARRIETA ARRIETA PABLO" [ref=e262]:
                  - cell "radio_button_unchecked" [ref=e263] [cursor=pointer]:
                    - generic [ref=e264]: radio_button_unchecked
                  - cell "ARRIETA" [ref=e265] [cursor=pointer]
                  - cell "ARRIETA PABLO" [ref=e266] [cursor=pointer]
                - row "radio_button_unchecked ASD ASD" [ref=e267]:
                  - cell "radio_button_unchecked" [ref=e268] [cursor=pointer]:
                    - generic [ref=e269]: radio_button_unchecked
                  - cell "ASD" [ref=e270] [cursor=pointer]
                  - cell "ASD" [ref=e271] [cursor=pointer]
                - row "radio_button_unchecked BACHECHI BACHECHI, GONZALO ESTUDIO BACHECHI441" [ref=e272]:
                  - cell "radio_button_unchecked" [ref=e273] [cursor=pointer]:
                    - generic [ref=e274]: radio_button_unchecked
                  - cell "BACHECHI" [ref=e275] [cursor=pointer]
                  - cell "BACHECHI, GONZALO ESTUDIO BACHECHI441" [ref=e276] [cursor=pointer]
                - row "radio_button_unchecked BANYASZ BANYASZ FLORENCIA1" [ref=e277]:
                  - cell "radio_button_unchecked" [ref=e278] [cursor=pointer]:
                    - generic [ref=e279]: radio_button_unchecked
                  - cell "BANYASZ" [ref=e280] [cursor=pointer]
                  - cell "BANYASZ FLORENCIA1" [ref=e281] [cursor=pointer]
                - row "radio_button_unchecked BARCIAL BARCIA, Lucía" [ref=e282]:
                  - cell "radio_button_unchecked" [ref=e283] [cursor=pointer]:
                    - generic [ref=e284]: radio_button_unchecked
                  - cell "BARCIAL" [ref=e285] [cursor=pointer]
                  - cell "BARCIA, Lucía" [ref=e286] [cursor=pointer]
                - row "radio_button_unchecked BARQUIN BARQUIN VALIENTE, ALFONSO" [ref=e287]:
                  - cell "radio_button_unchecked" [ref=e288] [cursor=pointer]:
                    - generic [ref=e289]: radio_button_unchecked
                  - cell "BARQUIN" [ref=e290] [cursor=pointer]
                  - cell "BARQUIN VALIENTE, ALFONSO" [ref=e291] [cursor=pointer]
                - row "radio_button_unchecked BELEN BELEN MANUEL" [ref=e292]:
                  - cell "radio_button_unchecked" [ref=e293] [cursor=pointer]:
                    - generic [ref=e294]: radio_button_unchecked
                  - cell "BELEN" [ref=e295] [cursor=pointer]
                  - cell "BELEN MANUEL" [ref=e296] [cursor=pointer]
                - row "radio_button_unchecked BELLAGAMBA BELLAGAMBA FABRICIO1" [ref=e297]:
                  - cell "radio_button_unchecked" [ref=e298] [cursor=pointer]:
                    - generic [ref=e299]: radio_button_unchecked
                  - cell "BELLAGAMBA" [ref=e300] [cursor=pointer]
                  - cell "BELLAGAMBA FABRICIO1" [ref=e301] [cursor=pointer]
                - row "radio_button_unchecked BERRIEL BERRIEL FIORELLA11123123" [ref=e302]:
                  - cell "radio_button_unchecked" [ref=e303] [cursor=pointer]:
                    - generic [ref=e304]: radio_button_unchecked
                  - cell "BERRIEL" [ref=e305] [cursor=pointer]
                  - cell "BERRIEL FIORELLA11123123" [ref=e306] [cursor=pointer]
                - row "radio_button_unchecked BOCCARDI BOCCARDI DIEGO" [ref=e307]:
                  - cell "radio_button_unchecked" [ref=e308] [cursor=pointer]:
                    - generic [ref=e309]: radio_button_unchecked
                  - cell "BOCCARDI" [ref=e310] [cursor=pointer]
                  - cell "BOCCARDI DIEGO" [ref=e311] [cursor=pointer]
                - row "radio_button_unchecked BOLSAS USUARIO TEST 2" [ref=e312]:
                  - cell "radio_button_unchecked" [ref=e313] [cursor=pointer]:
                    - generic [ref=e314]: radio_button_unchecked
                  - cell "BOLSAS" [ref=e315] [cursor=pointer]
                  - cell "USUARIO TEST 2" [ref=e316] [cursor=pointer]
                - 'row "radio_button_unchecked C }" [ref=e317]':
                  - cell "radio_button_unchecked" [ref=e318] [cursor=pointer]:
                    - generic [ref=e319]: radio_button_unchecked
                  - cell "C" [ref=e320] [cursor=pointer]
                  - 'cell "}" [ref=e321] [cursor=pointer]'
                - row "radio_button_unchecked CALLORDA CALLORDA PEREZ, Eliana Paula" [ref=e322]:
                  - cell "radio_button_unchecked" [ref=e323] [cursor=pointer]:
                    - generic [ref=e324]: radio_button_unchecked
                  - cell "CALLORDA" [ref=e325] [cursor=pointer]
                  - cell "CALLORDA PEREZ, Eliana Paula" [ref=e326] [cursor=pointer]
                - row "radio_button_unchecked CASAGRANDE CASAGRANDE MAURICIO" [ref=e327]:
                  - cell "radio_button_unchecked" [ref=e328] [cursor=pointer]:
                    - generic [ref=e329]: radio_button_unchecked
                  - cell "CASAGRANDE" [ref=e330] [cursor=pointer]
                  - cell "CASAGRANDE MAURICIO" [ref=e331] [cursor=pointer]
                - row "radio_button_unchecked CASTROM CASTRO MARTIN" [ref=e332]:
                  - cell "radio_button_unchecked" [ref=e333] [cursor=pointer]:
                    - generic [ref=e334]: radio_button_unchecked
                  - cell "CASTROM" [ref=e335] [cursor=pointer]
                  - cell "CASTRO MARTIN" [ref=e336] [cursor=pointer]
                - row "radio_button_unchecked CAVIGLIA CAVIGLIA OSCAR" [ref=e337]:
                  - cell "radio_button_unchecked" [ref=e338] [cursor=pointer]:
                    - generic [ref=e339]: radio_button_unchecked
                  - cell "CAVIGLIA" [ref=e340] [cursor=pointer]
                  - cell "CAVIGLIA OSCAR" [ref=e341] [cursor=pointer]
                - row "radio_button_unchecked CGMYA CGMyA" [ref=e342]:
                  - cell "radio_button_unchecked" [ref=e343] [cursor=pointer]:
                    - generic [ref=e344]: radio_button_unchecked
                  - cell "CGMYA" [ref=e345] [cursor=pointer]
                  - cell "CGMyA" [ref=e346] [cursor=pointer]
                - row "radio_button_unchecked CHARBONNIE CHARBONNIER LISSETTE" [ref=e347]:
                  - cell "radio_button_unchecked" [ref=e348] [cursor=pointer]:
                    - generic [ref=e349]: radio_button_unchecked
                  - cell "CHARBONNIE" [ref=e350] [cursor=pointer]
                  - cell "CHARBONNIER LISSETTE" [ref=e351] [cursor=pointer]
                - row "radio_button_unchecked cjzou Caijie" [ref=e352]:
                  - cell "radio_button_unchecked" [ref=e353] [cursor=pointer]:
                    - generic [ref=e354]: radio_button_unchecked
                  - cell "cjzou" [ref=e355] [cursor=pointer]
                  - cell "Caijie" [ref=e356] [cursor=pointer]
                - row "radio_button_unchecked COLL COLL GONZALO2" [ref=e357]:
                  - cell "radio_button_unchecked" [ref=e358] [cursor=pointer]:
                    - generic [ref=e359]: radio_button_unchecked
                  - cell "COLL" [ref=e360] [cursor=pointer]
                  - cell "COLL GONZALO2" [ref=e361] [cursor=pointer]
                - row "radio_button_unchecked COLOMBI COLOMBI MARCELO" [ref=e362]:
                  - cell "radio_button_unchecked" [ref=e363] [cursor=pointer]:
                    - generic [ref=e364]: radio_button_unchecked
                  - cell "COLOMBI" [ref=e365] [cursor=pointer]
                  - cell "COLOMBI MARCELO" [ref=e366] [cursor=pointer]
                - row "radio_button_unchecked COLOMBOD COLOMBO DANIEL" [ref=e367]:
                  - cell "radio_button_unchecked" [ref=e368] [cursor=pointer]:
                    - generic [ref=e369]: radio_button_unchecked
                  - cell "COLOMBOD" [ref=e370] [cursor=pointer]
                  - cell "COLOMBO DANIEL" [ref=e371] [cursor=pointer]
                - row "radio_button_unchecked CRESPI CRESPI GONZALO" [ref=e372]:
                  - cell "radio_button_unchecked" [ref=e373] [cursor=pointer]:
                    - generic [ref=e374]: radio_button_unchecked
                  - cell "CRESPI" [ref=e375] [cursor=pointer]
                  - cell "CRESPI GONZALO" [ref=e376] [cursor=pointer]
                - row "radio_button_unchecked CUADRO CUADRO OVIEDO, Andrea Antonella" [ref=e377]:
                  - cell "radio_button_unchecked" [ref=e378] [cursor=pointer]:
                    - generic [ref=e379]: radio_button_unchecked
                  - cell "CUADRO" [ref=e380] [cursor=pointer]
                  - cell "CUADRO OVIEDO, Andrea Antonella" [ref=e381] [cursor=pointer]
                - row "radio_button_unchecked ddgg ddg" [ref=e382]:
                  - cell "radio_button_unchecked" [ref=e383] [cursor=pointer]:
                    - generic [ref=e384]: radio_button_unchecked
                  - cell "ddgg" [ref=e385] [cursor=pointer]
                  - cell "ddg" [ref=e386] [cursor=pointer]
                - row "radio_button_unchecked DELEONL DE LEON LEONARDO" [ref=e387]:
                  - cell "radio_button_unchecked" [ref=e388] [cursor=pointer]:
                    - generic [ref=e389]: radio_button_unchecked
                  - cell "DELEONL" [ref=e390] [cursor=pointer]
                  - cell "DE LEON LEONARDO" [ref=e391] [cursor=pointer]
                - row "radio_button_unchecked DIAZSA DÍAZ VARELA, Stefani Anabella" [ref=e392]:
                  - cell "radio_button_unchecked" [ref=e393] [cursor=pointer]:
                    - generic [ref=e394]: radio_button_unchecked
                  - cell "DIAZSA" [ref=e395] [cursor=pointer]
                  - cell "DÍAZ VARELA, Stefani Anabella" [ref=e396] [cursor=pointer]
                - row "radio_button_unchecked ESP ESP" [ref=e397]:
                  - cell "radio_button_unchecked" [ref=e398] [cursor=pointer]:
                    - generic [ref=e399]: radio_button_unchecked
                  - cell "ESP" [ref=e400] [cursor=pointer]
                  - cell "ESP" [ref=e401] [cursor=pointer]
                - row "radio_button_unchecked ESTIGARRIB ESTIGARRIBIA SCALVINO, Victoria" [ref=e402]:
                  - cell "radio_button_unchecked" [ref=e403] [cursor=pointer]:
                    - generic [ref=e404]: radio_button_unchecked
                  - cell "ESTIGARRIB" [ref=e405] [cursor=pointer]
                  - cell "ESTIGARRIBIA SCALVINO, Victoria" [ref=e406] [cursor=pointer]
                - row "radio_button_unchecked ESTRELLA DE MAR" [ref=e407]:
                  - cell "radio_button_unchecked" [ref=e408] [cursor=pointer]:
                    - generic [ref=e409]: radio_button_unchecked
                  - cell "ESTRELLA" [ref=e410] [cursor=pointer]
                  - cell "DE MAR" [ref=e411] [cursor=pointer]
                - row "radio_button_unchecked FERNANDEZM FERNANDEZ MARIA PIA" [ref=e412]:
                  - cell "radio_button_unchecked" [ref=e413] [cursor=pointer]:
                    - generic [ref=e414]: radio_button_unchecked
                  - cell "FERNANDEZM" [ref=e415] [cursor=pointer]
                  - cell "FERNANDEZ MARIA PIA" [ref=e416] [cursor=pointer]
                - row "radio_button_unchecked FERNANDEZP FERNANDEZ PISCIOTTANO, Ana Camila" [ref=e417]:
                  - cell "radio_button_unchecked" [ref=e418] [cursor=pointer]:
                    - generic [ref=e419]: radio_button_unchecked
                  - cell "FERNANDEZP" [ref=e420] [cursor=pointer]
                  - cell "FERNANDEZ PISCIOTTANO, Ana Camila" [ref=e421] [cursor=pointer]
                - row "radio_button_unchecked FERRERE FERRERE" [ref=e422]:
                  - cell "radio_button_unchecked" [ref=e423] [cursor=pointer]:
                    - generic [ref=e424]: radio_button_unchecked
                  - cell "FERRERE" [ref=e425] [cursor=pointer]
                  - cell "FERRERE" [ref=e426] [cursor=pointer]
                - row "radio_button_unchecked FERREYRA FERREYRA MASDEU, María Matilde" [ref=e427]:
                  - cell "radio_button_unchecked" [ref=e428] [cursor=pointer]:
                    - generic [ref=e429]: radio_button_unchecked
                  - cell "FERREYRA" [ref=e430] [cursor=pointer]
                  - cell "FERREYRA MASDEU, María Matilde" [ref=e431] [cursor=pointer]
                - row "radio_button_unchecked FILLAT FILLAT SOFIA" [ref=e432]:
                  - cell "radio_button_unchecked" [ref=e433] [cursor=pointer]:
                    - generic [ref=e434]: radio_button_unchecked
                  - cell "FILLAT" [ref=e435] [cursor=pointer]
                  - cell "FILLAT SOFIA" [ref=e436] [cursor=pointer]
                - row "radio_button_unchecked FONTOURA FONTOURA MELLO, Maira Natalie" [ref=e437]:
                  - cell "radio_button_unchecked" [ref=e438] [cursor=pointer]:
                    - generic [ref=e439]: radio_button_unchecked
                  - cell "FONTOURA" [ref=e440] [cursor=pointer]
                  - cell "FONTOURA MELLO, Maira Natalie" [ref=e441] [cursor=pointer]
                - row "radio_button_unchecked FRECHOU FRECHOU FLORENCIA" [ref=e442]:
                  - cell "radio_button_unchecked" [ref=e443] [cursor=pointer]:
                    - generic [ref=e444]: radio_button_unchecked
                  - cell "FRECHOU" [ref=e445] [cursor=pointer]
                  - cell "FRECHOU FLORENCIA" [ref=e446] [cursor=pointer]
                - row "radio_button_unchecked FUSTER FUSTER ALVARO" [ref=e447]:
                  - cell "radio_button_unchecked" [ref=e448] [cursor=pointer]:
                    - generic [ref=e449]: radio_button_unchecked
                  - cell "FUSTER" [ref=e450] [cursor=pointer]
                  - cell "FUSTER ALVARO" [ref=e451] [cursor=pointer]
                - row "radio_button_unchecked GADEA GADEA MARIA NOEL" [ref=e452]:
                  - cell "radio_button_unchecked" [ref=e453] [cursor=pointer]:
                    - generic [ref=e454]: radio_button_unchecked
                  - cell "GADEA" [ref=e455] [cursor=pointer]
                  - cell "GADEA MARIA NOEL" [ref=e456] [cursor=pointer]
                - row "radio_button_unchecked GOMEZ GOMEZ ANDRES" [ref=e457]:
                  - cell "radio_button_unchecked" [ref=e458] [cursor=pointer]:
                    - generic [ref=e459]: radio_button_unchecked
                  - cell "GOMEZ" [ref=e460] [cursor=pointer]
                  - cell "GOMEZ ANDRES" [ref=e461] [cursor=pointer]
                - row "radio_button_unchecked GOMEZS GOMEZ PLATERO SOFIA" [ref=e462]:
                  - cell "radio_button_unchecked" [ref=e463] [cursor=pointer]:
                    - generic [ref=e464]: radio_button_unchecked
                  - cell "GOMEZS" [ref=e465] [cursor=pointer]
                  - cell "GOMEZ PLATERO SOFIA" [ref=e466] [cursor=pointer]
                - row "radio_button_unchecked GUSTAVO GUSTAVO" [ref=e467]:
                  - cell "radio_button_unchecked" [ref=e468] [cursor=pointer]:
                    - generic [ref=e469]: radio_button_unchecked
                  - cell "GUSTAVO" [ref=e470] [cursor=pointer]
                  - cell "GUSTAVO" [ref=e471] [cursor=pointer]
                - row "radio_button_unchecked GUTIERREZN Gutierrez Bas, Natalia Vanessa" [ref=e472]:
                  - cell "radio_button_unchecked" [ref=e473] [cursor=pointer]:
                    - generic [ref=e474]: radio_button_unchecked
                  - cell "GUTIERREZN" [ref=e475] [cursor=pointer]
                  - cell "Gutierrez Bas, Natalia Vanessa" [ref=e476] [cursor=pointer]
                - row "radio_button_unchecked HUERTAS HUERTAS LAURA" [ref=e477]:
                  - cell "radio_button_unchecked" [ref=e478] [cursor=pointer]:
                    - generic [ref=e479]: radio_button_unchecked
                  - cell "HUERTAS" [ref=e480] [cursor=pointer]
                  - cell "HUERTAS LAURA" [ref=e481] [cursor=pointer]
                - row "radio_button_unchecked HUGO HUGO FERNANDEZ, JUAN PABLO" [ref=e482]:
                  - cell "radio_button_unchecked" [ref=e483] [cursor=pointer]:
                    - generic [ref=e484]: radio_button_unchecked
                  - cell "HUGO" [ref=e485] [cursor=pointer]
                  - cell "HUGO FERNANDEZ, JUAN PABLO" [ref=e486] [cursor=pointer]
                - row "radio_button_unchecked IZETTA IZETTA MAURICIO" [ref=e487]:
                  - cell "radio_button_unchecked" [ref=e488] [cursor=pointer]:
                    - generic [ref=e489]: radio_button_unchecked
                  - cell "IZETTA" [ref=e490] [cursor=pointer]
                  - cell "IZETTA MAURICIO" [ref=e491] [cursor=pointer]
                - row "radio_button_unchecked JAY JAY" [ref=e492]:
                  - cell "radio_button_unchecked" [ref=e493] [cursor=pointer]:
                    - generic [ref=e494]: radio_button_unchecked
                  - cell "JAY" [ref=e495] [cursor=pointer]
                  - cell "JAY" [ref=e496] [cursor=pointer]
                - row "radio_button_unchecked KEVIN KEVIN" [ref=e497]:
                  - cell "radio_button_unchecked" [ref=e498] [cursor=pointer]:
                    - generic [ref=e499]: radio_button_unchecked
                  - cell "KEVIN" [ref=e500] [cursor=pointer]
                  - cell "KEVIN" [ref=e501] [cursor=pointer]
                - row "radio_button_unchecked LAGOS LAGOS MEDEIROS, Camila Yamisel" [ref=e502]:
                  - cell "radio_button_unchecked" [ref=e503] [cursor=pointer]:
                    - generic [ref=e504]: radio_button_unchecked
                  - cell "LAGOS" [ref=e505] [cursor=pointer]
                  - cell "LAGOS MEDEIROS, Camila Yamisel" [ref=e506] [cursor=pointer]
                - row "radio_button_unchecked LAPI LAPI MARIA JOSE" [ref=e507]:
                  - cell "radio_button_unchecked" [ref=e508] [cursor=pointer]:
                    - generic [ref=e509]: radio_button_unchecked
                  - cell "LAPI" [ref=e510] [cursor=pointer]
                  - cell "LAPI MARIA JOSE" [ref=e511] [cursor=pointer]
                - row "radio_button_unchecked LOPEZC LOPEZ CAROLINA" [ref=e512]:
                  - cell "radio_button_unchecked" [ref=e513] [cursor=pointer]:
                    - generic [ref=e514]: radio_button_unchecked
                  - cell "LOPEZC" [ref=e515] [cursor=pointer]
                  - cell "LOPEZ CAROLINA" [ref=e516] [cursor=pointer]
                - row "radio_button_unchecked Lorem Lorem" [ref=e517]:
                  - cell "radio_button_unchecked" [ref=e518] [cursor=pointer]:
                    - generic [ref=e519]: radio_button_unchecked
                  - cell "Lorem" [ref=e520] [cursor=pointer]
                  - cell "Lorem" [ref=e521] [cursor=pointer]
                - row "radio_button_unchecked MANAS MAÑAS ALEXIS" [ref=e522]:
                  - cell "radio_button_unchecked" [ref=e523] [cursor=pointer]:
                    - generic [ref=e524]: radio_button_unchecked
                  - cell "MANAS" [ref=e525] [cursor=pointer]
                  - cell "MAÑAS ALEXIS" [ref=e526] [cursor=pointer]
                - row "radio_button_unchecked MARINO MARIÑO IGNACIO" [ref=e527]:
                  - cell "radio_button_unchecked" [ref=e528] [cursor=pointer]:
                    - generic [ref=e529]: radio_button_unchecked
                  - cell "MARINO" [ref=e530] [cursor=pointer]
                  - cell "MARIÑO IGNACIO" [ref=e531] [cursor=pointer]
                - row "radio_button_unchecked MASSAT MASSAT AGUSTINA" [ref=e532]:
                  - cell "radio_button_unchecked" [ref=e533] [cursor=pointer]:
                    - generic [ref=e534]: radio_button_unchecked
                  - cell "MASSAT" [ref=e535] [cursor=pointer]
                  - cell "MASSAT AGUSTINA" [ref=e536] [cursor=pointer]
                - row "radio_button_unchecked MAYA MAYA AGUSTINA" [ref=e537]:
                  - cell "radio_button_unchecked" [ref=e538] [cursor=pointer]:
                    - generic [ref=e539]: radio_button_unchecked
                  - cell "MAYA" [ref=e540] [cursor=pointer]
                  - cell "MAYA AGUSTINA" [ref=e541] [cursor=pointer]
                - row "radio_button_unchecked MIHALIK MIHALIK FERNANDO" [ref=e542]:
                  - cell "radio_button_unchecked" [ref=e543] [cursor=pointer]:
                    - generic [ref=e544]: radio_button_unchecked
                  - cell "MIHALIK" [ref=e545] [cursor=pointer]
                  - cell "MIHALIK FERNANDO" [ref=e546] [cursor=pointer]
                - row "radio_button_unchecked MIRANDA MIRANDA CARLOS" [ref=e547]:
                  - cell "radio_button_unchecked" [ref=e548] [cursor=pointer]:
                    - generic [ref=e549]: radio_button_unchecked
                  - cell "MIRANDA" [ref=e550] [cursor=pointer]
                  - cell "MIRANDA CARLOS" [ref=e551] [cursor=pointer]
                - row "radio_button_unchecked MONTOSSI MONTOSSI RAUL" [ref=e552]:
                  - cell "radio_button_unchecked" [ref=e553] [cursor=pointer]:
                    - generic [ref=e554]: radio_button_unchecked
                  - cell "MONTOSSI" [ref=e555] [cursor=pointer]
                  - cell "MONTOSSI RAUL" [ref=e556] [cursor=pointer]
                - row "radio_button_unchecked MOREIRAM MOREIRA MARIA NOEL" [ref=e557]:
                  - cell "radio_button_unchecked" [ref=e558] [cursor=pointer]:
                    - generic [ref=e559]: radio_button_unchecked
                  - cell "MOREIRAM" [ref=e560] [cursor=pointer]
                  - cell "MOREIRA MARIA NOEL" [ref=e561] [cursor=pointer]
                - row "radio_button_unchecked MOYPC MOyPC" [ref=e562]:
                  - cell "radio_button_unchecked" [ref=e563] [cursor=pointer]:
                    - generic [ref=e564]: radio_button_unchecked
                  - cell "MOYPC" [ref=e565] [cursor=pointer]
                  - cell "MOyPC" [ref=e566] [cursor=pointer]
                - row "radio_button_unchecked NBK1C2R MILES PAMELA" [ref=e567]:
                  - cell "radio_button_unchecked" [ref=e568] [cursor=pointer]:
                    - generic [ref=e569]: radio_button_unchecked
                  - cell "NBK1C2R" [ref=e570] [cursor=pointer]
                  - cell "MILES PAMELA" [ref=e571] [cursor=pointer]
                - row "radio_button_unchecked NBK1O9H LIZARRAGA GONZALO" [ref=e572]:
                  - cell "radio_button_unchecked" [ref=e573] [cursor=pointer]:
                    - generic [ref=e574]: radio_button_unchecked
                  - cell "NBK1O9H" [ref=e575] [cursor=pointer]
                  - cell "LIZARRAGA GONZALO" [ref=e576] [cursor=pointer]
                - row "radio_button_unchecked NBK2PTM MOLINARI MARTIN" [ref=e577]:
                  - cell "radio_button_unchecked" [ref=e578] [cursor=pointer]:
                    - generic [ref=e579]: radio_button_unchecked
                  - cell "NBK2PTM" [ref=e580] [cursor=pointer]
                  - cell "MOLINARI MARTIN" [ref=e581] [cursor=pointer]
                - row "radio_button_unchecked NBK31EV TORNQUIST JORGE" [ref=e582]:
                  - cell "radio_button_unchecked" [ref=e583] [cursor=pointer]:
                    - generic [ref=e584]: radio_button_unchecked
                  - cell "NBK31EV" [ref=e585] [cursor=pointer]
                  - cell "TORNQUIST JORGE" [ref=e586] [cursor=pointer]
                - row "radio_button_unchecked NBK34HL CORREA JORGE" [ref=e587]:
                  - cell "radio_button_unchecked" [ref=e588] [cursor=pointer]:
                    - generic [ref=e589]: radio_button_unchecked
                  - cell "NBK34HL" [ref=e590] [cursor=pointer]
                  - cell "CORREA JORGE" [ref=e591] [cursor=pointer]
                - row "radio_button_unchecked NBK54NS HERNANDEZ GUSTAVO" [ref=e592]:
                  - cell "radio_button_unchecked" [ref=e593] [cursor=pointer]:
                    - generic [ref=e594]: radio_button_unchecked
                  - cell "NBK54NS" [ref=e595] [cursor=pointer]
                  - cell "HERNANDEZ GUSTAVO" [ref=e596] [cursor=pointer]
                - row "radio_button_unchecked NBK5TAQ MASSEILOT JOAQUIN" [ref=e597]:
                  - cell "radio_button_unchecked" [ref=e598] [cursor=pointer]:
                    - generic [ref=e599]: radio_button_unchecked
                  - cell "NBK5TAQ" [ref=e600] [cursor=pointer]
                  - cell "MASSEILOT JOAQUIN" [ref=e601] [cursor=pointer]
                - row "radio_button_unchecked NBK68OW BARRIOS VERONICA112119" [ref=e602]:
                  - cell "radio_button_unchecked" [ref=e603] [cursor=pointer]:
                    - generic [ref=e604]: radio_button_unchecked
                  - cell "NBK68OW" [ref=e605] [cursor=pointer]
                  - cell "BARRIOS VERONICA112119" [ref=e606] [cursor=pointer]
                - row "radio_button_unchecked NBK7IBI SAPIURKA FABIAN222" [ref=e607]:
                  - cell "radio_button_unchecked" [ref=e608] [cursor=pointer]:
                    - generic [ref=e609]: radio_button_unchecked
                  - cell "NBK7IBI" [ref=e610] [cursor=pointer]
                  - cell "SAPIURKA FABIAN222" [ref=e611] [cursor=pointer]
                - row "radio_button_unchecked NBK8S7J ANTUNEZ JULIO" [ref=e612]:
                  - cell "radio_button_unchecked" [ref=e613] [cursor=pointer]:
                    - generic [ref=e614]: radio_button_unchecked
                  - cell "NBK8S7J" [ref=e615] [cursor=pointer]
                  - cell "ANTUNEZ JULIO" [ref=e616] [cursor=pointer]
                - row "radio_button_unchecked NBK95LK ARECHAVALETA IGNACIO" [ref=e617]:
                  - cell "radio_button_unchecked" [ref=e618] [cursor=pointer]:
                    - generic [ref=e619]: radio_button_unchecked
                  - cell "NBK95LK" [ref=e620] [cursor=pointer]
                  - cell "ARECHAVALETA IGNACIO" [ref=e621] [cursor=pointer]
                - row "radio_button_unchecked NBK9UJR RADO MARCELLO" [ref=e622]:
                  - cell "radio_button_unchecked" [ref=e623] [cursor=pointer]:
                    - generic [ref=e624]: radio_button_unchecked
                  - cell "NBK9UJR" [ref=e625] [cursor=pointer]
                  - cell "RADO MARCELLO" [ref=e626] [cursor=pointer]
                - row "radio_button_unchecked NBKDWWU MUTIO JUAN MANUEL" [ref=e627]:
                  - cell "radio_button_unchecked" [ref=e628] [cursor=pointer]:
                    - generic [ref=e629]: radio_button_unchecked
                  - cell "NBKDWWU" [ref=e630] [cursor=pointer]
                  - cell "MUTIO JUAN MANUEL" [ref=e631] [cursor=pointer]
                - row "radio_button_unchecked NBKE27X GROSSO MARY" [ref=e632]:
                  - cell "radio_button_unchecked" [ref=e633] [cursor=pointer]:
                    - generic [ref=e634]: radio_button_unchecked
                  - cell "NBKE27X" [ref=e635] [cursor=pointer]
                  - cell "GROSSO MARY" [ref=e636] [cursor=pointer]
                - row "radio_button_unchecked NBKE72H PONTE ENRIQUE" [ref=e637]:
                  - cell "radio_button_unchecked" [ref=e638] [cursor=pointer]:
                    - generic [ref=e639]: radio_button_unchecked
                  - cell "NBKE72H" [ref=e640] [cursor=pointer]
                  - cell "PONTE ENRIQUE" [ref=e641] [cursor=pointer]
                - row "radio_button_unchecked NBKFE5T REY OMAR" [ref=e642]:
                  - cell "radio_button_unchecked" [ref=e643] [cursor=pointer]:
                    - generic [ref=e644]: radio_button_unchecked
                  - cell "NBKFE5T" [ref=e645] [cursor=pointer]
                  - cell "REY OMAR" [ref=e646] [cursor=pointer]
                - row "radio_button_unchecked NBKG3KC QUEIROLO JAIME" [ref=e647]:
                  - cell "radio_button_unchecked" [ref=e648] [cursor=pointer]:
                    - generic [ref=e649]: radio_button_unchecked
                  - cell "NBKG3KC" [ref=e650] [cursor=pointer]
                  - cell "QUEIROLO JAIME" [ref=e651] [cursor=pointer]
                - row "radio_button_unchecked NBKI19G BALADAN SANTIAGO" [ref=e652]:
                  - cell "radio_button_unchecked" [ref=e653] [cursor=pointer]:
                    - generic [ref=e654]: radio_button_unchecked
                  - cell "NBKI19G" [ref=e655] [cursor=pointer]
                  - cell "BALADAN SANTIAGO" [ref=e656] [cursor=pointer]
                - row "radio_button_unchecked NBKK3CE OTEGUI ANDRES" [ref=e657]:
                  - cell "radio_button_unchecked" [ref=e658] [cursor=pointer]:
                    - generic [ref=e659]: radio_button_unchecked
                  - cell "NBKK3CE" [ref=e660] [cursor=pointer]
                  - cell "OTEGUI ANDRES" [ref=e661] [cursor=pointer]
                - row "radio_button_unchecked NBKKP3E SANTAMARINA CARLOS" [ref=e662]:
                  - cell "radio_button_unchecked" [ref=e663] [cursor=pointer]:
                    - generic [ref=e664]: radio_button_unchecked
                  - cell "NBKKP3E" [ref=e665] [cursor=pointer]
                  - cell "SANTAMARINA CARLOS" [ref=e666] [cursor=pointer]
                - row "radio_button_unchecked NBKKU8I MOREIRA PEDRO" [ref=e667]:
                  - cell "radio_button_unchecked" [ref=e668] [cursor=pointer]:
                    - generic [ref=e669]: radio_button_unchecked
                  - cell "NBKKU8I" [ref=e670] [cursor=pointer]
                  - cell "MOREIRA PEDRO" [ref=e671] [cursor=pointer]
                - row "radio_button_unchecked NBKM3AC BONDONI EDUARDO" [ref=e672]:
                  - cell "radio_button_unchecked" [ref=e673] [cursor=pointer]:
                    - generic [ref=e674]: radio_button_unchecked
                  - cell "NBKM3AC" [ref=e675] [cursor=pointer]
                  - cell "BONDONI EDUARDO" [ref=e676] [cursor=pointer]
                - row "radio_button_unchecked NBKOF8F PONASSO VIRGINIA" [ref=e677]:
                  - cell "radio_button_unchecked" [ref=e678] [cursor=pointer]:
                    - generic [ref=e679]: radio_button_unchecked
                  - cell "NBKOF8F" [ref=e680] [cursor=pointer]
                  - cell "PONASSO VIRGINIA" [ref=e681] [cursor=pointer]
                - row "radio_button_unchecked NBKP41X MANTA DANIEL" [ref=e682]:
                  - cell "radio_button_unchecked" [ref=e683] [cursor=pointer]:
                    - generic [ref=e684]: radio_button_unchecked
                  - cell "NBKP41X" [ref=e685] [cursor=pointer]
                  - cell "MANTA DANIEL" [ref=e686] [cursor=pointer]
                - row "radio_button_unchecked NBKQ7SW GROLLA ALVARO" [ref=e687]:
                  - cell "radio_button_unchecked" [ref=e688] [cursor=pointer]:
                    - generic [ref=e689]: radio_button_unchecked
                  - cell "NBKQ7SW" [ref=e690] [cursor=pointer]
                  - cell "GROLLA ALVARO" [ref=e691] [cursor=pointer]
                - row "radio_button_unchecked NBKSJ2Y REY SANTIAGO" [ref=e692]:
                  - cell "radio_button_unchecked" [ref=e693] [cursor=pointer]:
                    - generic [ref=e694]: radio_button_unchecked
                  - cell "NBKSJ2Y" [ref=e695] [cursor=pointer]
                  - cell "REY SANTIAGO" [ref=e696] [cursor=pointer]
                - row "radio_button_unchecked NBKV2UP MEZZERA FEDERICO" [ref=e697]:
                  - cell "radio_button_unchecked" [ref=e698] [cursor=pointer]:
                    - generic [ref=e699]: radio_button_unchecked
                  - cell "NBKV2UP" [ref=e700] [cursor=pointer]
                  - cell "MEZZERA FEDERICO" [ref=e701] [cursor=pointer]
                - row "radio_button_unchecked NBKWC9E DELFINO ALVARO" [ref=e702]:
                  - cell "radio_button_unchecked" [ref=e703] [cursor=pointer]:
                    - generic [ref=e704]: radio_button_unchecked
                  - cell "NBKWC9E" [ref=e705] [cursor=pointer]
                  - cell "DELFINO ALVARO" [ref=e706] [cursor=pointer]
                - row "radio_button_unchecked NBKYUGR MILAN PATRICIA" [ref=e707]:
                  - cell "radio_button_unchecked" [ref=e708] [cursor=pointer]:
                    - generic [ref=e709]: radio_button_unchecked
                  - cell "NBKYUGR" [ref=e710] [cursor=pointer]
                  - cell "MILAN PATRICIA" [ref=e711] [cursor=pointer]
                - row "radio_button_unchecked NBKZ25C BRUN JULIO" [ref=e712]:
                  - cell "radio_button_unchecked" [ref=e713] [cursor=pointer]:
                    - generic [ref=e714]: radio_button_unchecked
                  - cell "NBKZ25C" [ref=e715] [cursor=pointer]
                  - cell "BRUN JULIO" [ref=e716] [cursor=pointer]
                - row "radio_button_unchecked NBKZE2W CARLUCCIO PATRICIA" [ref=e717]:
                  - cell "radio_button_unchecked" [ref=e718] [cursor=pointer]:
                    - generic [ref=e719]: radio_button_unchecked
                  - cell "NBKZE2W" [ref=e720] [cursor=pointer]
                  - cell "CARLUCCIO PATRICIA" [ref=e721] [cursor=pointer]
                - row "radio_button_unchecked NOTTE NOTTE MARCELO" [ref=e722]:
                  - cell "radio_button_unchecked" [ref=e723] [cursor=pointer]:
                    - generic [ref=e724]: radio_button_unchecked
                  - cell "NOTTE" [ref=e725] [cursor=pointer]
                  - cell "NOTTE MARCELO" [ref=e726] [cursor=pointer]
                - row "radio_button_unchecked OTEGUIM OTEGUI MARIA ELENA" [ref=e727]:
                  - cell "radio_button_unchecked" [ref=e728] [cursor=pointer]:
                    - generic [ref=e729]: radio_button_unchecked
                  - cell "OTEGUIM" [ref=e730] [cursor=pointer]
                  - cell "OTEGUI MARIA ELENA" [ref=e731] [cursor=pointer]
                - row "radio_button_unchecked PABLO USUARIO TEST" [ref=e732]:
                  - cell "radio_button_unchecked" [ref=e733] [cursor=pointer]:
                    - generic [ref=e734]: radio_button_unchecked
                  - cell "PABLO" [ref=e735] [cursor=pointer]
                  - cell "USUARIO TEST" [ref=e736] [cursor=pointer]
                - row "radio_button_unchecked PABLO2 PABLO22" [ref=e737]:
                  - cell "radio_button_unchecked" [ref=e738] [cursor=pointer]:
                    - generic [ref=e739]: radio_button_unchecked
                  - cell "PABLO2" [ref=e740] [cursor=pointer]
                  - cell "PABLO22" [ref=e741] [cursor=pointer]
                - row "radio_button_unchecked PABLO3 PABLO3" [ref=e742]:
                  - cell "radio_button_unchecked" [ref=e743] [cursor=pointer]:
                    - generic [ref=e744]: radio_button_unchecked
                  - cell "PABLO3" [ref=e745] [cursor=pointer]
                  - cell "PABLO3" [ref=e746] [cursor=pointer]
                - row "radio_button_unchecked PABLO4 PABLO44" [ref=e747]:
                  - cell "radio_button_unchecked" [ref=e748] [cursor=pointer]:
                    - generic [ref=e749]: radio_button_unchecked
                  - cell "PABLO4" [ref=e750] [cursor=pointer]
                  - cell "PABLO44" [ref=e751] [cursor=pointer]
                - row "radio_button_unchecked PABLO5 PÀBLO5" [ref=e752]:
                  - cell "radio_button_unchecked" [ref=e753] [cursor=pointer]:
                    - generic [ref=e754]: radio_button_unchecked
                  - cell "PABLO5" [ref=e755] [cursor=pointer]
                  - cell "PÀBLO5" [ref=e756] [cursor=pointer]
                - row "radio_button_unchecked PABLO6 PABLO6" [ref=e757]:
                  - cell "radio_button_unchecked" [ref=e758] [cursor=pointer]:
                    - generic [ref=e759]: radio_button_unchecked
                  - cell "PABLO6" [ref=e760] [cursor=pointer]
                  - cell "PABLO6" [ref=e761] [cursor=pointer]
                - row "radio_button_unchecked PACIFICO PACIFICO" [ref=e762]:
                  - cell "radio_button_unchecked" [ref=e763] [cursor=pointer]:
                    - generic [ref=e764]: radio_button_unchecked
                  - cell "PACIFICO" [ref=e765] [cursor=pointer]
                  - cell "PACIFICO" [ref=e766] [cursor=pointer]
                - row "radio_button_unchecked PALMERO PALMERO" [ref=e767]:
                  - cell "radio_button_unchecked" [ref=e768] [cursor=pointer]:
                    - generic [ref=e769]: radio_button_unchecked
                  - cell "PALMERO" [ref=e770] [cursor=pointer]
                  - cell "PALMERO" [ref=e771] [cursor=pointer]
                - row "radio_button_unchecked PEPITO A" [ref=e772]:
                  - cell "radio_button_unchecked" [ref=e773] [cursor=pointer]:
                    - generic [ref=e774]: radio_button_unchecked
                  - cell "PEPITO" [ref=e775] [cursor=pointer]
                  - cell "A" [ref=e776] [cursor=pointer]
                - row "radio_button_unchecked PEREIRAI PEREIRA ISABEL" [ref=e777]:
                  - cell "radio_button_unchecked" [ref=e778] [cursor=pointer]:
                    - generic [ref=e779]: radio_button_unchecked
                  - cell "PEREIRAI" [ref=e780] [cursor=pointer]
                  - cell "PEREIRA ISABEL" [ref=e781] [cursor=pointer]
                - row "radio_button_unchecked PIASTRI LUCIANA PIASTRI 22222" [ref=e782]:
                  - cell "radio_button_unchecked" [ref=e783] [cursor=pointer]:
                    - generic [ref=e784]: radio_button_unchecked
                  - cell "PIASTRI" [ref=e785] [cursor=pointer]
                  - cell "LUCIANA PIASTRI 22222" [ref=e786] [cursor=pointer]
                - row "radio_button_unchecked PIZZORNOF PIZZORNO FERNANDA" [ref=e787]:
                  - cell "radio_button_unchecked" [ref=e788] [cursor=pointer]:
                    - generic [ref=e789]: radio_button_unchecked
                  - cell "PIZZORNOF" [ref=e790] [cursor=pointer]
                  - cell "PIZZORNO FERNANDA" [ref=e791] [cursor=pointer]
                - row "radio_button_unchecked QQW 11" [ref=e792]:
                  - cell "radio_button_unchecked" [ref=e793] [cursor=pointer]:
                    - generic [ref=e794]: radio_button_unchecked
                  - cell "QQW" [ref=e795] [cursor=pointer]
                  - cell "11" [ref=e796] [cursor=pointer]
                - row "radio_button_unchecked qw qw" [ref=e797]:
                  - cell "radio_button_unchecked" [ref=e798] [cursor=pointer]:
                    - generic [ref=e799]: radio_button_unchecked
                  - cell "qw" [ref=e800] [cursor=pointer]
                  - cell "qw" [ref=e801] [cursor=pointer]
                - row "radio_button_unchecked RAMIS RAMIS FEDERICO" [ref=e802]:
                  - cell "radio_button_unchecked" [ref=e803] [cursor=pointer]:
                    - generic [ref=e804]: radio_button_unchecked
                  - cell "RAMIS" [ref=e805] [cursor=pointer]
                  - cell "RAMIS FEDERICO" [ref=e806] [cursor=pointer]
                - row "radio_button_unchecked RASNER RASNER NICOLAS" [ref=e807]:
                  - cell "radio_button_unchecked" [ref=e808] [cursor=pointer]:
                    - generic [ref=e809]: radio_button_unchecked
                  - cell "RASNER" [ref=e810] [cursor=pointer]
                  - cell "RASNER NICOLAS" [ref=e811] [cursor=pointer]
                - row "radio_button_unchecked RD RD" [ref=e812]:
                  - cell "radio_button_unchecked" [ref=e813] [cursor=pointer]:
                    - generic [ref=e814]: radio_button_unchecked
                  - cell "RD" [ref=e815] [cursor=pointer]
                  - cell "RD" [ref=e816] [cursor=pointer]
                - row "radio_button_unchecked ROCCAS ROCCA STEFANIA" [ref=e817]:
                  - cell "radio_button_unchecked" [ref=e818] [cursor=pointer]:
                    - generic [ref=e819]: radio_button_unchecked
                  - cell "ROCCAS" [ref=e820] [cursor=pointer]
                  - cell "ROCCA STEFANIA" [ref=e821] [cursor=pointer]
                - row "radio_button_unchecked RODRIGUEZM RODRIGUEZ BORGES, Marcelo" [ref=e822]:
                  - cell "radio_button_unchecked" [ref=e823] [cursor=pointer]:
                    - generic [ref=e824]: radio_button_unchecked
                  - cell "RODRIGUEZM" [ref=e825] [cursor=pointer]
                  - cell "RODRIGUEZ BORGES, Marcelo" [ref=e826] [cursor=pointer]
                - row "radio_button_unchecked ROTONDO ROTONDO MAGELA" [ref=e827]:
                  - cell "radio_button_unchecked" [ref=e828] [cursor=pointer]:
                    - generic [ref=e829]: radio_button_unchecked
                  - cell "ROTONDO" [ref=e830] [cursor=pointer]
                  - cell "ROTONDO MAGELA" [ref=e831] [cursor=pointer]
                - row "radio_button_unchecked SANCHEZALB SANCHEZ ALBERTO" [ref=e832]:
                  - cell "radio_button_unchecked" [ref=e833] [cursor=pointer]:
                    - generic [ref=e834]: radio_button_unchecked
                  - cell "SANCHEZALB" [ref=e835] [cursor=pointer]
                  - cell "SANCHEZ ALBERTO" [ref=e836] [cursor=pointer]
                - row "radio_button_unchecked SANCHEZRO SANCHEZ RODRIGO" [ref=e837]:
                  - cell "radio_button_unchecked" [ref=e838] [cursor=pointer]:
                    - generic [ref=e839]: radio_button_unchecked
                  - cell "SANCHEZRO" [ref=e840] [cursor=pointer]
                  - cell "SANCHEZ RODRIGO" [ref=e841] [cursor=pointer]
                - row "radio_button_unchecked SANZ SANZ ALEJANDRA1" [ref=e842]:
                  - cell "radio_button_unchecked" [ref=e843] [cursor=pointer]:
                    - generic [ref=e844]: radio_button_unchecked
                  - cell "SANZ" [ref=e845] [cursor=pointer]
                  - cell "SANZ ALEJANDRA1" [ref=e846] [cursor=pointer]
                - row "radio_button_unchecked SBROCCA SBROCCA PABLO" [ref=e847]:
                  - cell "radio_button_unchecked" [ref=e848] [cursor=pointer]:
                    - generic [ref=e849]: radio_button_unchecked
                  - cell "SBROCCA" [ref=e850] [cursor=pointer]
                  - cell "SBROCCA PABLO" [ref=e851] [cursor=pointer]
                - row "radio_button_unchecked SELHAY SELHAY CAROLINA" [ref=e852]:
                  - cell "radio_button_unchecked" [ref=e853] [cursor=pointer]:
                    - generic [ref=e854]: radio_button_unchecked
                  - cell "SELHAY" [ref=e855] [cursor=pointer]
                  - cell "SELHAY CAROLINA" [ref=e856] [cursor=pointer]
                - row "radio_button_unchecked SICARDI SICARDI JUAN CARLOS" [ref=e857]:
                  - cell "radio_button_unchecked" [ref=e858] [cursor=pointer]:
                    - generic [ref=e859]: radio_button_unchecked
                  - cell "SICARDI" [ref=e860] [cursor=pointer]
                  - cell "SICARDI JUAN CARLOS" [ref=e861] [cursor=pointer]
                - row "radio_button_unchecked SOLARO SOLARO ROSARIO" [ref=e862]:
                  - cell "radio_button_unchecked" [ref=e863] [cursor=pointer]:
                    - generic [ref=e864]: radio_button_unchecked
                  - cell "SOLARO" [ref=e865] [cursor=pointer]
                  - cell "SOLARO ROSARIO" [ref=e866] [cursor=pointer]
                - row "radio_button_unchecked SOSAJJ SOSA JUAN JOSE" [ref=e867]:
                  - cell "radio_button_unchecked" [ref=e868] [cursor=pointer]:
                    - generic [ref=e869]: radio_button_unchecked
                  - cell "SOSAJJ" [ref=e870] [cursor=pointer]
                  - cell "SOSA JUAN JOSE" [ref=e871] [cursor=pointer]
                - row "radio_button_unchecked SOUZA SOUZA BARRETO, Juliana" [ref=e872]:
                  - cell "radio_button_unchecked" [ref=e873] [cursor=pointer]:
                    - generic [ref=e874]: radio_button_unchecked
                  - cell "SOUZA" [ref=e875] [cursor=pointer]
                  - cell "SOUZA BARRETO, Juliana" [ref=e876] [cursor=pointer]
                - row "radio_button_unchecked STAZIONE STAZIONE FERNANDEZ, Paola Antonella" [ref=e877]:
                  - cell "radio_button_unchecked" [ref=e878] [cursor=pointer]:
                    - generic [ref=e879]: radio_button_unchecked
                  - cell "STAZIONE" [ref=e880] [cursor=pointer]
                  - cell "STAZIONE FERNANDEZ, Paola Antonella" [ref=e881] [cursor=pointer]
                - row "radio_button_unchecked SUPERMAN SUPERMAN" [ref=e882]:
                  - cell "radio_button_unchecked" [ref=e883] [cursor=pointer]:
                    - generic [ref=e884]: radio_button_unchecked
                  - cell "SUPERMAN" [ref=e885] [cursor=pointer]
                  - cell "SUPERMAN" [ref=e886] [cursor=pointer]
                - row "radio_button_unchecked TEST test" [ref=e887]:
                  - cell "radio_button_unchecked" [ref=e888] [cursor=pointer]:
                    - generic [ref=e889]: radio_button_unchecked
                  - cell "TEST" [ref=e890] [cursor=pointer]
                  - cell "test" [ref=e891] [cursor=pointer]
                - row "radio_button_unchecked TEST1 TEST1" [ref=e892]:
                  - cell "radio_button_unchecked" [ref=e893] [cursor=pointer]:
                    - generic [ref=e894]: radio_button_unchecked
                  - cell "TEST1" [ref=e895] [cursor=pointer]
                  - cell "TEST1" [ref=e896] [cursor=pointer]
                - row "radio_button_unchecked TEST2 ASD" [ref=e897]:
                  - cell "radio_button_unchecked" [ref=e898] [cursor=pointer]:
                    - generic [ref=e899]: radio_button_unchecked
                  - cell "TEST2" [ref=e900] [cursor=pointer]
                  - cell "ASD" [ref=e901] [cursor=pointer]
                - row "radio_button_unchecked TEST3 TEST3" [ref=e902]:
                  - cell "radio_button_unchecked" [ref=e903] [cursor=pointer]:
                    - generic [ref=e904]: radio_button_unchecked
                  - cell "TEST3" [ref=e905] [cursor=pointer]
                  - cell "TEST3" [ref=e906] [cursor=pointer]
                - row "radio_button_unchecked testerUser Tester" [ref=e907]:
                  - cell "radio_button_unchecked" [ref=e908] [cursor=pointer]:
                    - generic [ref=e909]: radio_button_unchecked
                  - cell "testerUser" [ref=e910] [cursor=pointer]
                  - cell "Tester" [ref=e911] [cursor=pointer]
                - row "radio_button_unchecked TOBLER TOBLER ELIZABETH" [ref=e912]:
                  - cell "radio_button_unchecked" [ref=e913] [cursor=pointer]:
                    - generic [ref=e914]: radio_button_unchecked
                  - cell "TOBLER" [ref=e915] [cursor=pointer]
                  - cell "TOBLER ELIZABETH" [ref=e916] [cursor=pointer]
                - row "radio_button_unchecked USER1 TEST USER" [ref=e917]:
                  - cell "radio_button_unchecked" [ref=e918] [cursor=pointer]:
                    - generic [ref=e919]: radio_button_unchecked
                  - cell "USER1" [ref=e920] [cursor=pointer]
                  - cell "TEST USER" [ref=e921] [cursor=pointer]
                - row "radio_button_unchecked usernuevoprueba1 user nuevo pruba 2" [ref=e922]:
                  - cell "radio_button_unchecked" [ref=e923] [cursor=pointer]:
                    - generic [ref=e924]: radio_button_unchecked
                  - cell "usernuevoprueba1" [ref=e925] [cursor=pointer]
                  - cell "user nuevo pruba 2" [ref=e926] [cursor=pointer]
                - row "radio_button_unchecked usertest2 usuario test 2" [ref=e927]:
                  - cell "radio_button_unchecked" [ref=e928] [cursor=pointer]:
                    - generic [ref=e929]: radio_button_unchecked
                  - cell "usertest2" [ref=e930] [cursor=pointer]
                  - cell "usuario test 2" [ref=e931] [cursor=pointer]
                - row "radio_button_unchecked USITA Usuario ITALIA" [ref=e932]:
                  - cell "radio_button_unchecked" [ref=e933] [cursor=pointer]:
                    - generic [ref=e934]: radio_button_unchecked
                  - cell "USITA" [ref=e935] [cursor=pointer]
                  - cell "Usuario ITALIA" [ref=e936] [cursor=pointer]
                - row "radio_button_unchecked USUPRUEBA USUARIO DE PRUEBA" [ref=e937]:
                  - cell "radio_button_unchecked" [ref=e938] [cursor=pointer]:
                    - generic [ref=e939]: radio_button_unchecked
                  - cell "USUPRUEBA" [ref=e940] [cursor=pointer]
                  - cell "USUARIO DE PRUEBA" [ref=e941] [cursor=pointer]
                - row "radio_button_unchecked VARELAC VARELA CARLOS ESTUDIO VARELA" [ref=e942]:
                  - cell "radio_button_unchecked" [ref=e943] [cursor=pointer]:
                    - generic [ref=e944]: radio_button_unchecked
                  - cell "VARELAC" [ref=e945] [cursor=pointer]
                  - cell "VARELA CARLOS ESTUDIO VARELA" [ref=e946] [cursor=pointer]
                - row "radio_button_unchecked VGG AIS VICTOR" [ref=e947]:
                  - cell "radio_button_unchecked" [ref=e948] [cursor=pointer]:
                    - generic [ref=e949]: radio_button_unchecked
                  - cell "VGG" [ref=e950] [cursor=pointer]
                  - cell "AIS VICTOR" [ref=e951] [cursor=pointer]
                - row "radio_button_unchecked VILLALBA VILLALBA GUZMAN" [ref=e952]:
                  - cell "radio_button_unchecked" [ref=e953] [cursor=pointer]:
                    - generic [ref=e954]: radio_button_unchecked
                  - cell "VILLALBA" [ref=e955] [cursor=pointer]
                  - cell "VILLALBA GUZMAN" [ref=e956] [cursor=pointer]
                - row "radio_button_unchecked VILLAR VILLAR JUAN PABLO" [ref=e957]:
                  - cell "radio_button_unchecked" [ref=e958] [cursor=pointer]:
                    - generic [ref=e959]: radio_button_unchecked
                  - cell "VILLAR" [ref=e960] [cursor=pointer]
                  - cell "VILLAR JUAN PABLO" [ref=e961] [cursor=pointer]
                - row "radio_button_unchecked WILLIMAN WILLIMAN JOSE" [ref=e962]:
                  - cell "radio_button_unchecked" [ref=e963] [cursor=pointer]:
                    - generic [ref=e964]: radio_button_unchecked
                  - cell "WILLIMAN" [ref=e965] [cursor=pointer]
                  - cell "WILLIMAN JOSE" [ref=e966] [cursor=pointer]
                - 'row "radio_button_unchecked YANEZ YA?`EZ RODOLFO" [ref=e967]':
                  - cell "radio_button_unchecked" [ref=e968] [cursor=pointer]:
                    - generic [ref=e969]: radio_button_unchecked
                  - cell "YANEZ" [ref=e970] [cursor=pointer]
                  - 'cell "YA?`EZ RODOLFO" [ref=e971] [cursor=pointer]'
                - row "radio_button_unchecked YANEZA YAÑEZ ALVARO" [ref=e972]:
                  - cell "radio_button_unchecked" [ref=e973] [cursor=pointer]:
                    - generic [ref=e974]: radio_button_unchecked
                  - cell "YANEZA" [ref=e975] [cursor=pointer]
                  - cell "YAÑEZ ALVARO" [ref=e976] [cursor=pointer]
              - rowgroup
          - generic [ref=e978]:
            - generic [ref=e979]:
              - generic [ref=e980]: Usuario
              - generic [ref=e981]:
                - generic [ref=e982]:
                  - textbox "Código" [ref=e983]: "1"
                  - generic [ref=e984]: Código
                - generic [ref=e985]:
                  - textbox "Nombre" [ref=e986]: "22"
                  - generic [ref=e987]: Nombre
                - generic [ref=e988]:
                  - textbox "Fecha Baja" [ref=e989]
                  - generic [ref=e990]: Fecha Baja
              - generic [ref=e991]:
                - generic [ref=e992]:
                  - textbox "Estado" [ref=e993]: Periodo de Vacaciones
                  - generic [ref=e994]: Estado
                - generic [ref=e995]:
                  - textbox "Idioma" [ref=e996]: Espanol
                  - generic [ref=e997]: Idioma
                - generic [ref=e998]:
                  - textbox "Empleador" [ref=e999]: Agencia Externa 1
                  - generic [ref=e1000]: Empleador
                - generic [ref=e1001]:
                  - textbox "Sucursal" [ref=e1002]
                  - generic [ref=e1003]: Sucursal
              - generic [ref=e1004]:
                - generic [ref=e1005]:
                  - textbox "Teléfono" [ref=e1006]: "66"
                  - generic [ref=e1007]: Teléfono
                - generic [ref=e1008]:
                  - textbox "Interno" [ref=e1009]: "77"
                  - generic [ref=e1010]: Interno
                - generic [ref=e1011]:
                  - textbox "Max Lotes" [ref=e1012]: "88"
                  - generic [ref=e1013]: Max Lotes
                - generic [ref=e1014]:
                  - textbox "Número Documento" [ref=e1015]: "99123123123123123123"
                  - generic [ref=e1016]: Número Documento
              - generic [ref=e1017]:
                - generic [ref=e1018]:
                  - textbox "Superior" [ref=e1019]: 501 - 501
                  - generic [ref=e1020]: Superior
                - generic [ref=e1021]:
                  - textbox "Email" [ref=e1022]: "1010"
                  - generic [ref=e1023]: Email
              - generic [ref=e1025]:
                - link "add Agregar" [ref=e1026] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$btnAgregarUsuario','')
                  - generic: add
                  - text: Agregar
                - link "create Modificar" [ref=e1027] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$btnModificarUsuario','')
                  - generic: create
                  - text: Modificar
                - link "lock_open Desbloquear" [ref=e1028] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$btnDesbloquear','')
                  - generic: lock_open
                  - text: Desbloquear
                - link "password Cambio Password" [ref=e1029] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$btnCambioPassword','')
                  - generic: password
                  - text: Cambio Password
            - generic [ref=e1030]:
              - generic [ref=e1031]: Perfil
              - generic [ref=e1032]:
                - generic [ref=e1035]:
                  - textbox "Buscador Perfil" [ref=e1036]
                  - generic [ref=e1037] [cursor=pointer]:
                    - generic: filter_alt
                  - generic [ref=e1038]: Buscador Perfil
                - generic [ref=e1039]:
                  - link "add Agregar Perfil" [ref=e1040] [cursor=pointer]:
                    - /url: javascript:__doPostBack('ctl00$c$btnAgregarPerfil','')
                    - generic: add
                    - text: Agregar Perfil
                  - link "visibility Consultar Perfil" [ref=e1041] [cursor=pointer]:
                    - /url: javascript:__doPostBack('ctl00$c$btnConsultarPerfil','')
                    - generic: visibility
                    - text: Consultar Perfil
                  - link "create Modificar Perfil" [ref=e1042] [cursor=pointer]:
                    - /url: javascript:__doPostBack('ctl00$c$btnModificarPerfil','')
                    - generic: create
                    - text: Modificar Perfil
                  - link "content_copy Copiar Perfiles a..." [ref=e1043] [cursor=pointer]:
                    - /url: javascript:__doPostBack('ctl00$c$btnCopiarPerfiles','')
                    - generic: content_copy
                    - text: Copiar Perfiles a...
                  - link "delete Eliminar Perfil" [ref=e1044] [cursor=pointer]:
                    - /url: javascript:__doPostBack('ctl00$c$btnEliminarPerfil','')
                    - generic: delete
                    - text: Eliminar Perfil
              - table [ref=e1048]:
                - rowgroup [ref=e1049]:
                  - row "Código Descripción Fecha Alta Fecha Baja" [ref=e1050]:
                    - columnheader [ref=e1051]
                    - columnheader "Código" [ref=e1052]:
                      - link "Código" [ref=e1053] [cursor=pointer]:
                        - /url: javascript:__doPostBack('ctl00$c$GridPerfiles','Sort$UPROL')
                    - columnheader "Descripción" [ref=e1054]:
                      - link "Descripción" [ref=e1055] [cursor=pointer]:
                        - /url: javascript:__doPostBack('ctl00$c$GridPerfiles','Sort$TBTEXT')
                    - columnheader "Fecha Alta" [ref=e1056]:
                      - link "Fecha Alta" [ref=e1057] [cursor=pointer]:
                        - /url: javascript:__doPostBack('ctl00$c$GridPerfiles','Sort$UPFECALTA')
                    - columnheader "Fecha Baja" [ref=e1058]:
                      - link "Fecha Baja" [ref=e1059] [cursor=pointer]:
                        - /url: javascript:__doPostBack('ctl00$c$GridPerfiles','Sort$UPFECBAJA')
                - rowgroup [ref=e1060]:
                  - row "radio_button_checked BOTC Backoffice Tarjetas de Credito 19/07/2024" [ref=e1061]:
                    - cell "radio_button_checked" [ref=e1062] [cursor=pointer]:
                      - generic [ref=e1063]: radio_button_checked
                    - cell "BOTC" [ref=e1064] [cursor=pointer]
                    - cell "Backoffice Tarjetas de Credito" [ref=e1065] [cursor=pointer]
                    - cell "19/07/2024" [ref=e1066] [cursor=pointer]
                    - cell [ref=e1067] [cursor=pointer]
                - rowgroup
        - generic [ref=e1070]:
          - generic [ref=e1071]:
            - heading "Usuario" [level=5] [ref=e1072]
            - generic [ref=e1073]:
              - generic [ref=e1074]:
                - textbox "Código *" [ref=e1075]
                - generic [ref=e1076]: Código *
                - generic [ref=e1077]: Código obligatorio
              - generic [ref=e1078]:
                - textbox "Nombre *" [ref=e1079]: QA Test User 01
                - generic [ref=e1080]: Nombre *
              - generic [ref=e1081]:
                - textbox "Fecha Baja" [ref=e1082]
                - generic [ref=e1083]: Fecha Baja
            - generic [ref=e1084]:
              - generic [ref=e1085]:
                - generic [ref=e1086]: Estado
                - combobox "Activo" [ref=e1089] [cursor=pointer]:
                  - generic "Activo" [ref=e1090]
              - generic [ref=e1092]:
                - generic [ref=e1093]: Idioma
                - combobox "Seleccione un valor" [ref=e1096] [cursor=pointer]:
                  - generic "Seleccione un valor" [ref=e1097]
              - generic [ref=e1099]:
                - generic [ref=e1100]: Empleador *
                - combobox "0011 - Agencia Externa 1" [ref=e1103] [cursor=pointer]:
                  - generic "0011 - Agencia Externa 1" [ref=e1104]
              - generic [ref=e1106]:
                - generic [ref=e1107]: Sucursal
                - combobox "Seleccione un valor" [ref=e1110] [cursor=pointer]:
                  - generic "Seleccione un valor" [ref=e1111]
            - generic [ref=e1113]:
              - generic [ref=e1114]:
                - textbox "Teléfono" [ref=e1115]
                - generic [ref=e1116]: Teléfono
              - generic [ref=e1117]:
                - textbox "Interno" [ref=e1118]
                - generic [ref=e1119]: Interno
              - generic [ref=e1120]:
                - textbox "Máx Lotes *" [ref=e1121]: "5"
                - generic [ref=e1122]: Máx Lotes *
              - generic [ref=e1123]:
                - textbox "Número Documento" [ref=e1124]
                - generic [ref=e1125]: Número Documento
            - generic [ref=e1126]:
              - generic [ref=e1127]:
                - generic [ref=e1128]: Superior
                - combobox "Seleccione" [ref=e1131] [cursor=pointer]:
                  - generic "Seleccione" [ref=e1132]
              - generic [ref=e1134]:
                - textbox "Email" [ref=e1135]
                - generic [ref=e1136]: Email
          - generic [ref=e1137]:
            - link "Guardar" [active] [ref=e1138] [cursor=pointer]:
              - /url: javascript:__doPostBack('ctl00$c$btnGuardarUsuario','')
            - link "Cerrar" [ref=e1139] [cursor=pointer]:
              - /url: javascript:__doPostBack('ctl00$c$btnCancelarUsuario','')
  - generic:
    - generic: Guardar
```

# Test source

```ts
  173 |     
  174 |     
  175 |     
  176 |     // [STEP 08] fill pb_step_7 with "QA Test User 01"
  177 |     console.log('[STEP 08] fill pb_step_7');
  178 |     await page.locator("#c_abfNombre").fill('QA Test User 01', { force: true });;
  179 |     await page.screenshot({ path: 'evidence/-1/P01/step_08_after.png' });
  180 |     STEP_BBOXES.push({ step_index: 8, screenshot_path: 'evidence/-1/P01/step_08_after.png', target: "pb_step_7", bbox: await page.locator("#c_abfNombre").boundingBox().catch(() => null) });
  181 |     
  182 |     
  183 |     
  184 |     
  185 |     // [STEP 09] fill pb_step_8 with "5"
  186 |     console.log('[STEP 09] fill pb_step_8');
  187 |     await page.locator("#c_abfMaxLotes").fill('5', { force: true });;
  188 |     await page.screenshot({ path: 'evidence/-1/P01/step_09_after.png' });
  189 |     STEP_BBOXES.push({ step_index: 9, screenshot_path: 'evidence/-1/P01/step_09_after.png', target: "pb_step_8", bbox: await page.locator("#c_abfMaxLotes").boundingBox().catch(() => null) });
  190 |     
  191 |     
  192 |     
  193 |     
  194 |     // [STEP 10] click pb_step_9
  195 |     console.log('[STEP 10] click pb_step_9');
  196 |     await page.locator("#c_btnAgregarUsuario").click({ force: true });
  197 |     await page.waitForLoadState('load');
  198 |     await page.screenshot({ path: 'evidence/-1/P01/step_10_after.png' });
  199 |     STEP_BBOXES.push({ step_index: 10, screenshot_path: 'evidence/-1/P01/step_10_after.png', target: "pb_step_9", bbox: await page.locator("#c_btnAgregarUsuario").boundingBox().catch(() => null) });
  200 |     
  201 |     
  202 |     
  203 |     
  204 |     // [STEP 11] wait visible pb_step_10
  205 |     await expect(page.locator('#c_abfMdCodigo')).toBeVisible({ timeout: 30000 });
  206 |     
  207 |     
  208 |     
  209 |     // [STEP 12] select 0011 in pb_step_11
  210 |     console.log('[STEP 12] select pb_step_11');
  211 |     await page.locator("#c_ddlMdEmpleador").selectOption('0011', { force: true });;
  212 |     await page.screenshot({ path: 'evidence/-1/P01/step_12_after.png' });
  213 |     STEP_BBOXES.push({ step_index: 12, screenshot_path: 'evidence/-1/P01/step_12_after.png', target: "pb_step_11", bbox: await page.locator("#c_ddlMdEmpleador").boundingBox().catch(() => null) });
  214 |     
  215 |     
  216 |     
  217 |     
  218 |     // [STEP 13] wait networkidle
  219 |     await page.waitForLoadState('networkidle');
  220 |     
  221 |     
  222 |     
  223 |     // [STEP 14] wait visible pb_step_13
  224 |     await expect(page.locator('#c_abfMdCodigo')).toBeVisible({ timeout: 30000 });
  225 |     
  226 |     
  227 |     
  228 |     // [STEP 15] fill pb_step_14 with "USQA01"
  229 |     console.log('[STEP 15] fill pb_step_14');
  230 |     await page.locator("#c_abfMdCodigo").fill('USQA01', { force: true });;
  231 |     await page.screenshot({ path: 'evidence/-1/P01/step_15_after.png' });
  232 |     STEP_BBOXES.push({ step_index: 15, screenshot_path: 'evidence/-1/P01/step_15_after.png', target: "pb_step_14", bbox: await page.locator("#c_abfMdCodigo").boundingBox().catch(() => null) });
  233 |     
  234 |     
  235 |     
  236 |     
  237 |     // [STEP 16] fill pb_step_15 with "QA Test User 01"
  238 |     console.log('[STEP 16] fill pb_step_15');
  239 |     await page.locator("#c_abfMdNombre").fill('QA Test User 01', { force: true });;
  240 |     await page.screenshot({ path: 'evidence/-1/P01/step_16_after.png' });
  241 |     STEP_BBOXES.push({ step_index: 16, screenshot_path: 'evidence/-1/P01/step_16_after.png', target: "pb_step_15", bbox: await page.locator("#c_abfMdNombre").boundingBox().catch(() => null) });
  242 |     
  243 |     
  244 |     
  245 |     
  246 |     // [STEP 17] fill pb_step_16 with "5"
  247 |     console.log('[STEP 17] fill pb_step_16');
  248 |     await page.locator("#c_abfMdMaxLotes").fill('5', { force: true });;
  249 |     await page.screenshot({ path: 'evidence/-1/P01/step_17_after.png' });
  250 |     STEP_BBOXES.push({ step_index: 17, screenshot_path: 'evidence/-1/P01/step_17_after.png', target: "pb_step_16", bbox: await page.locator("#c_abfMdMaxLotes").boundingBox().catch(() => null) });
  251 |     
  252 |     
  253 |     
  254 |     
  255 |     // [STEP 18] click pb_step_17
  256 |     console.log('[STEP 18] click pb_step_17');
  257 |     await page.locator("#c_btnGuardarUsuario").click({ force: true });
  258 |     await page.waitForLoadState('load');
  259 |     await page.screenshot({ path: 'evidence/-1/P01/step_18_after.png' });
  260 |     STEP_BBOXES.push({ step_index: 18, screenshot_path: 'evidence/-1/P01/step_18_after.png', target: "pb_step_17", bbox: await page.locator("#c_btnGuardarUsuario").boundingBox().catch(() => null) });
  261 |     
  262 |     
  263 |     
  264 |     
  265 |     // [STEP 19] wait networkidle
  266 |     await page.waitForLoadState('networkidle');
  267 |     
  268 |     
  269 | 
  270 |     // ASSERTIONS
  271 |     
  272 |     
> 273 |     await expect(page.locator('body'), 'P01: página debe contener "USQA01"').toContainText('USQA01');
      |                                                                              ^ Error: P01: página debe contener "USQA01"
  274 |     
  275 |     
  276 | 
  277 |     // CLEANUP
  278 |     await page.context().clearCookies();
  279 |   });
  280 | 
  281 |   test.afterEach(async ({ page }) => {
  282 |     // Capture final state screenshot first — fail-safe even if the page is
  283 |     // mid-PostBack.
  284 |     try {
  285 |       await page.screenshot({
  286 |         path: 'evidence/-1/P01/step_final_state.png',
  287 |       });
  288 |     } catch (_e) {
  289 |       // ignore — page may be closed or navigating
  290 |     }
  291 | 
  292 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  293 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  294 |     // relying on Playwright's pass/fail (which conflates product defects
  295 |     // with pipeline defects).
  296 |     const captured: any[] = [];
  297 |     for (const probe of ORACLE_PROBES) {
  298 |       const entry: any = {
  299 |         oracle_id: probe.oracle_id,
  300 |         target: probe.target,
  301 |         tipo: probe.tipo,
  302 |         expected: probe.expected,
  303 |       };
  304 |       try {
  305 |         if (probe.selector === null) {
  306 |           // Whole-page oracle: capture the body text once (truncated).
  307 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  308 |           entry.actual_text = bodyText.slice(0, 4000);
  309 |           entry.visible = true;
  310 |         } else {
  311 |           const loc = page.locator(probe.selector);
  312 |           // count
  313 |           const count = await loc.count();
  314 |           entry.count = count;
  315 |           if (count === 0) {
  316 |             entry.visible = false;
  317 |             entry.actual_text = null;
  318 |           } else {
  319 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  320 |             // value (form controls)
  321 |             try {
  322 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  323 |             } catch (_e) { /* not a form control */ }
  324 |             // textContent
  325 |             try {
  326 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  327 |               entry.actual_text = txt.slice(0, 1000);
  328 |             } catch (_e) {
  329 |               entry.actual_text = null;
  330 |             }
  331 |             // disabled / state
  332 |             try {
  333 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  334 |             } catch (_e) { /* ignore */ }
  335 |           }
  336 |         }
  337 |       } catch (e: any) {
  338 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  339 |       }
  340 |       captured.push(entry);
  341 |     }
  342 | 
  343 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
  344 |     // must not break the test runner.
  345 |     try {
  346 |       const outPath = path.resolve(process.cwd(), ASSERTIONS_OUT_PATH);
  347 |       fs.mkdirSync(path.dirname(outPath), { recursive: true });
  348 |       fs.writeFileSync(
  349 |         outPath,
  350 |         JSON.stringify(
  351 |           { scenario_id: 'P01', assertions: captured },
  352 |           null, 2,
  353 |         ),
  354 |         'utf-8',
  355 |       );
  356 |     } catch (e) {
  357 |       console.error('[afterEach] could not persist assertions json:', e);
  358 |     }
  359 | 
  360 |     // Persist step_bboxes.json for screenshot_annotator.py (Fase 2).
  361 |     // Non-fatal: if this fails the pipeline continues without annotations.
  362 |     if (STEP_BBOXES.length > 0) {
  363 |       try {
  364 |         const bboxOutPath = path.resolve(process.cwd(), STEP_BBOXES_OUT_PATH);
  365 |         fs.mkdirSync(path.dirname(bboxOutPath), { recursive: true });
  366 |         fs.writeFileSync(bboxOutPath, JSON.stringify(STEP_BBOXES, null, 2), 'utf-8');
  367 |       } catch (e) {
  368 |         console.error('[afterEach] could not persist step_bboxes json:', e);
  369 |       }
  370 |     }
  371 | 
  372 | 
  373 |     await page.context().clearCookies();
```