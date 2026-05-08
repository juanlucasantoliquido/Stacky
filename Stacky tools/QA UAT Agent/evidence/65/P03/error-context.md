# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 65\tests\P03_corredor_valor_parcial.spec.ts >> ADO-65 | P03 — Corredor = valor parcial >> p03 corredor_=_valor_parcial
- Location: evidence\65\tests\P03_corredor_valor_parcial.spec.ts:58:7

# Error details

```
Error: P03: página debe contener "valor parcial"

expect(locator).toContainText(expected) failed

Locator: locator('body')
Timeout: 5000ms
- Expected substring  -   1
+ Received string     + 168

- valor parcial
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
+         menulogoutSalirAgenda PersonalUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:2Realizado Hoy:0Total en Agenda:2Barrido Realizado:0%Clientes Asignados:10430    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion Manualformat_list_bulletedReportes OperativosleaderboardInformesleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estados EspecialesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
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
+                             AccionesExportar AgendasClientes Asignados
+                             chevron_rightAvanzar
+                         
+                     
+                 
+
+             
+     
+ 	
+ 		search
+ 			Búsqueda Avanzada
+ 		
+ 	
+ 		
+                 
+                         
+ 	
+                             
+                                 Desde 
+                                 Hasta 
+                                 Empresa TodasBBB_test2Carteras PrópiasEmpresa 1Empresa 2Empresa 3Empresa 4Empresa 6Empresa 9999PacíficoTodas  
+                                 Perfil Todos1 - Gerente de Cobranzas150 - Gestion Autopago155 - Soporte AIS156 - Operador de Call Center167 - Backoffice Tarjetas de Credito279 - Nucleo EstrategicoTodos  
+                             
+                             
+                                 Región TodasREGIÓN 00REGIÓN 01REGIÓN 02REGIÓN 03REGIÓN 04REGIÓN 05REGIÓN 06REGIÓN 07REGIÓN 08REGIÓN 09REGIÓN 10REGIÓN 11REGIÓN 12REGIÓN 13REGIÓN 14REGIÓN 15REGIÓN 16REGIÓN 17REGIÓN 18REGIÓN 19REGIÓN 20REGIÓN 21REGIÓN 22REGIÓN 23REGIÓN 24REGIÓN 25REGIÓN 26REGIÓN 27Todas  
+                                 Recomendación TodasOECA - Cerrar Cuenta y Enviar Carpeta Recup ActTRT4 - Propuesta refin. y adver. incl ClearingTRT6 - Llamada advertencia pase a judicialTodas  
+                                 Nivel de Mora TodosCiclo 1Ciclo 2Ciclo 3Ciclo 4Ciclo 5Ciclo 6Ciclo 7Ciclo 8Ciclo 9Cobranza JudicialCobranza preventivaNo MoraPeriodo de autopagoTodos  
+                                 Tipo de Cliente TodosCliente JudicialCliente MixtoCliente VigenteTodos  
+                             
+                             
+                             
+                                 lblDebitoAuto TodosNoSíTodos  
+                                 Corredor: 
+                                 Nombre de Cliente: 
+                                 RUC: 
+                             
+                             
+                                 
+                                     
+                                     searchFiltrar
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
+ 	Agendados por Usuario
+
+                 
+                     
+                 
+             
+             
+ 	
+ 		
+ 			
+ 				ClienteLoteFechaHoraRecomendaciónNivel MoraPrimaMoneda
+ 			
+ 		
+ 	
+
+             
+                 
+ 	Agendados por Motor Experto
+
+                 
+                     
+                 
+             
+             
+ 	
+ 		
+ 			
+ 				ClienteLoteFechaHoraRecomendaciónNivel MoraPrimaMoneda
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
+ InformaciónNo hay lotes agendados que cumplan los criterios seleccionadosCerrar

Call log:
  - P03: página debe contener "valor parcial" with timeout 5000ms
  - waiting for locator('body')
    4 × locator resolved to <body id="bodyTag">…</body>
      - unexpected value "
    






























	

        

        
	
                
            

        
	
                

	
            

        menulogoutSalirAgenda PersonalUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:2Realizado Hoy:0Total en Agenda:2Barrido Realizado:0%Clientes Asignados:10430    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion Manualformat_list_bulletedReportes OperativosleaderboardInformesleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estados EspecialesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
        
            
	
                    
                        
                            
                        
                        
                            
                            
                            
                            AccionesExportar AgendasClientes Asignados
                            chevron_rightAvanzar
                        
                    
                

            
    
	
		search
			Búsqueda Avanzada
		
	
		
                
			
                        
				
                            
                                Desde 
                                Hasta 
                                Empresa TodasBBB_test2Carteras PrópiasEmpresa 1Empresa 2Empresa 3Empresa 4Empresa 6Empresa 9999PacíficoTodas  
                                Perfil Todos1 - Gerente de Cobranzas150 - Gestion Autopago155 - Soporte AIS156 - Operador de Call Center167 - Backoffice Tarjetas de Credito279 - Nucleo EstrategicoTodos  
                            
                            
                                Región TodasREGIÓN 00REGIÓN 01REGIÓN 02REGIÓN 03REGIÓN 04REGIÓN 05REGIÓN 06REGIÓN 07REGIÓN 08REGIÓN 09REGIÓN 10REGIÓN 11REGIÓN 12REGIÓN 13REGIÓN 14REGIÓN 15REGIÓN 16REGIÓN 17REGIÓN 18REGIÓN 19REGIÓN 20REGIÓN 21REGIÓN 22REGIÓN 23REGIÓN 24REGIÓN 25REGIÓN 26REGIÓN 27Todas  
                                Recomendación TodasOECA - Cerrar Cuenta y Enviar Carpeta Recup ActTRT4 - Propuesta refin. y adver. incl ClearingTRT6 - Llamada advertencia pase a judicialTodas  
                                Nivel de Mora TodosCiclo 1Ciclo 2Ciclo 3Ciclo 4Ciclo 5Ciclo 6Ciclo 7Ciclo 8Ciclo 9Cobranza JudicialCobranza preventivaNo MoraPeriodo de autopagoTodos  
                                Tipo de Cliente TodosCliente JudicialCliente MixtoCliente VigenteTodos  
                            
                            
                            
                                lblDebitoAuto TodosNoSíTodos  
                                Corredor: 
                                Nombre de Cliente: 
                                RUC: 
                            
                            
                                
                                    
                                    searchFiltrar
                                
                            
                        
			
                    
		
            
	

    
	
            
                
		Agendados por Usuario
	
                
                    grid_onAgendados por Usuario
                
            
            
		
			
				
					ClienteLoteFechaHoraRecomendaciónNivel MoraPrimaMoneda
				
			
				
					MONTEZUMA GARRIDO NATALIA412792411234539320/03/202610:00:00OECA - Cerrar Cuenta y Enviar Carpeta Recup ActCiclo 948882,83US.D
				
			

			
		
	
            
                
		Agendados por Motor Experto
	
                
                    
                
            
            
		
			
				
					ClienteLoteFechaHoraRecomendaciónNivel MoraPrimaMoneda
				
			
		
	
        


        
        
    



    
        
        
            
                
                    
                
                
                    
                
                
                    
                
            
        
    


Filtrar"
    5 × locator resolved to <body id="bodyTag">…</body>
      - unexpected value "
    






























	

        

        
                
            
        
	
                

	
            

        menulogoutSalirAgenda PersonalUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:2Realizado Hoy:0Total en Agenda:2Barrido Realizado:0%Clientes Asignados:10430    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion Manualformat_list_bulletedReportes OperativosleaderboardInformesleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estados EspecialesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
        
            
	
                    
                        
                            
                        
                        
                            
                            
                            
                            AccionesExportar AgendasClientes Asignados
                            chevron_rightAvanzar
                        
                    
                

            
    
	
		search
			Búsqueda Avanzada
		
	
		
                
                        
	
                            
                                Desde 
                                Hasta 
                                Empresa TodasBBB_test2Carteras PrópiasEmpresa 1Empresa 2Empresa 3Empresa 4Empresa 6Empresa 9999PacíficoTodas  
                                Perfil Todos1 - Gerente de Cobranzas150 - Gestion Autopago155 - Soporte AIS156 - Operador de Call Center167 - Backoffice Tarjetas de Credito279 - Nucleo EstrategicoTodos  
                            
                            
                                Región TodasREGIÓN 00REGIÓN 01REGIÓN 02REGIÓN 03REGIÓN 04REGIÓN 05REGIÓN 06REGIÓN 07REGIÓN 08REGIÓN 09REGIÓN 10REGIÓN 11REGIÓN 12REGIÓN 13REGIÓN 14REGIÓN 15REGIÓN 16REGIÓN 17REGIÓN 18REGIÓN 19REGIÓN 20REGIÓN 21REGIÓN 22REGIÓN 23REGIÓN 24REGIÓN 25REGIÓN 26REGIÓN 27Todas  
                                Recomendación TodasOECA - Cerrar Cuenta y Enviar Carpeta Recup ActTRT4 - Propuesta refin. y adver. incl ClearingTRT6 - Llamada advertencia pase a judicialTodas  
                                Nivel de Mora TodosCiclo 1Ciclo 2Ciclo 3Ciclo 4Ciclo 5Ciclo 6Ciclo 7Ciclo 8Ciclo 9Cobranza JudicialCobranza preventivaNo MoraPeriodo de autopagoTodos  
                                Tipo de Cliente TodosCliente JudicialCliente MixtoCliente VigenteTodos  
                            
                            
                            
                                lblDebitoAuto TodosNoSíTodos  
                                Corredor: 
                                Nombre de Cliente: 
                                RUC: 
                            
                            
                                
                                    
                                    searchFiltrar
                                
                            
                        

                    
            
	

    
            
                
	Agendados por Usuario

                
                    
                
            
            
	
		
			
				ClienteLoteFechaHoraRecomendaciónNivel MoraPrimaMoneda
			
		
	

            
                
	Agendados por Motor Experto

                
                    
                
            
            
	
		
			
				ClienteLoteFechaHoraRecomendaciónNivel MoraPrimaMoneda
			
		
	

        

        
        
    



    
        
        
            
                
                    
                
                
                    
                
                
                    
                
            
        
    


InformaciónNo hay lotes agendados que cumplan los criterios seleccionadosCerrar"

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
        - generic [ref=e15]: Agenda Personal
        - generic [ref=e17]:
          - generic [ref=e18]:
            - generic [ref=e19]: "Usuario:"
            - generic [ref=e20]: USUARIO TEST
          - generic [ref=e22]:
            - generic [ref=e23]: "Pendiente de Hoy:"
            - generic [ref=e24]: "0"
          - generic [ref=e26]:
            - generic [ref=e27]: "Pendiente de otros Días:"
            - generic [ref=e28]: "2"
          - generic [ref=e30]:
            - generic [ref=e31]: "Realizado Hoy:"
            - generic [ref=e32]: "0"
          - generic [ref=e34]:
            - generic [ref=e35]: "Total en Agenda:"
            - generic [ref=e36]: "2"
          - generic [ref=e38]:
            - generic [ref=e39]: "Barrido Realizado:"
            - generic [ref=e40]: 0%
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
      - generic [ref=e110]:
        - link "Acciones" [ref=e111] [cursor=pointer]:
          - /url: "#!"
        - link "chevron_right Avanzar" [ref=e112] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$btnNext','')
          - generic: chevron_right
          - text: Avanzar
      - list [ref=e113]:
        - listitem [ref=e114]:
          - generic [ref=e115] [cursor=pointer]:
            - generic [ref=e116]: search
            - generic [ref=e117]: Búsqueda Avanzada
          - generic [ref=e120]:
            - generic [ref=e121]:
              - generic [ref=e122]:
                - textbox "Desde" [ref=e123]
                - generic [ref=e124]: Desde
              - generic [ref=e125]:
                - textbox "Hasta" [ref=e126]
                - generic [ref=e127]: Hasta
              - generic [ref=e128]:
                - generic [ref=e129]: Empresa
                - combobox "Todas" [ref=e132] [cursor=pointer]:
                  - generic "Todas" [ref=e133]
              - generic [ref=e135]:
                - generic [ref=e136]: Perfil
                - combobox "Todos" [ref=e139] [cursor=pointer]:
                  - generic "Todos" [ref=e140]
            - generic [ref=e142]:
              - generic [ref=e143]:
                - generic [ref=e144]: Región
                - combobox "Todas" [ref=e147] [cursor=pointer]:
                  - generic "Todas" [ref=e148]
              - generic [ref=e150]:
                - generic [ref=e151]: Recomendación
                - combobox "Todas" [ref=e154] [cursor=pointer]:
                  - generic "Todas" [ref=e155]
              - generic [ref=e157]:
                - generic [ref=e158]: Nivel de Mora
                - combobox "Todos" [ref=e161] [cursor=pointer]:
                  - generic "Todos" [ref=e162]
              - generic [ref=e164]:
                - generic [ref=e165]: Tipo de Cliente
                - combobox "Todos" [ref=e168] [cursor=pointer]:
                  - generic "Todos" [ref=e169]
            - generic [ref=e171]:
              - generic [ref=e172]:
                - generic [ref=e173]: lblDebitoAuto
                - combobox "Todos" [ref=e176] [cursor=pointer]:
                  - generic "Todos" [ref=e177]
              - generic [ref=e179]:
                - textbox "Corredor:" [ref=e180]: valor parcial
                - generic [ref=e181]: "Corredor:"
              - generic [ref=e182]:
                - textbox "Nombre de Cliente:" [ref=e183]
                - generic [ref=e184]: "Nombre de Cliente:"
              - generic [ref=e185]:
                - textbox "RUC:" [ref=e186]
                - generic [ref=e187]: "RUC:"
            - link "search Filtrar" [ref=e190] [cursor=pointer]:
              - /url: javascript:__doPostBack('ctl00$c$btnOk','')
              - generic: search
              - text: Filtrar
      - generic [ref=e191]:
        - generic [ref=e193]: Agendados por Usuario
        - table [ref=e196]:
          - rowgroup [ref=e197]:
            - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda" [ref=e198]:
              - columnheader "Cliente" [ref=e199]:
                - link "Cliente" [ref=e200] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
              - columnheader "Lote" [ref=e201]:
                - link "Lote" [ref=e202] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
              - columnheader "Fecha" [ref=e203]:
                - link "Fecha" [ref=e204] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
              - columnheader "Hora" [ref=e205]:
                - link "Hora" [ref=e206] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
              - columnheader "Recomendación" [ref=e207]:
                - link "Recomendación" [ref=e208] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
              - columnheader "Nivel Mora" [ref=e209]:
                - link "Nivel Mora" [ref=e210] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
              - columnheader "Prima" [ref=e211]:
                - link "Prima" [ref=e212] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LODEUDA')
              - columnheader "Moneda" [ref=e213]:
                - link "Moneda" [ref=e214] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGMONEDA')
        - generic [ref=e216]: Agendados por Motor Experto
        - table [ref=e219]:
          - rowgroup [ref=e220]:
            - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda" [ref=e221]:
              - columnheader "Cliente" [ref=e222]:
                - link "Cliente" [ref=e223] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
              - columnheader "Lote" [ref=e224]:
                - link "Lote" [ref=e225] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
              - columnheader "Fecha" [ref=e226]:
                - link "Fecha" [ref=e227] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
              - columnheader "Hora" [ref=e228]:
                - link "Hora" [ref=e229] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
              - columnheader "Recomendación" [ref=e230]:
                - link "Recomendación" [ref=e231] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
              - columnheader "Nivel Mora" [ref=e232]:
                - link "Nivel Mora" [ref=e233] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
              - columnheader "Prima" [ref=e234]:
                - link "Prima" [ref=e235] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LODEUDA')
              - columnheader "Moneda" [ref=e236]:
                - link "Moneda" [ref=e237] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGMONEDA')
  - generic [ref=e239]:
    - generic [ref=e241]: Información
    - list [ref=e242]:
      - listitem [ref=e243]: No hay lotes agendados que cumplan los criterios seleccionados
    - link "Cerrar" [active] [ref=e245] [cursor=pointer]:
      - /url: "#!"
      - text: Cerrar
```

# Test source

```ts
  12  | const PASS = process.env.AGENDA_WEB_PASS!;
  13  | 
  14  | if (!BASE_URL) throw new Error('AGENDA_WEB_BASE_URL env var is required');
  15  | if (!USER) throw new Error('AGENDA_WEB_USER env var is required');
  16  | if (!PASS) throw new Error('AGENDA_WEB_PASS env var is required');
  17  | 
  18  | // ORACLE_PROBES — generated from scenario.oraculos × ui_map.
  19  | // Consumed by the test.afterEach hook to write
  20  | // evidence/<ticket>/<sid>/assertions_<sid>.json with the actual values
  21  | // captured from the live DOM, regardless of whether the test passed,
  22  | // failed, or threw. uat_assertion_evaluator.py reads this file as the
  23  | // primary source of truth for expected/actual reconciliation; without
  24  | // it every oracle would default to status=review.
  25  | type OracleProbe = {
  26  |   oracle_id: number;
  27  |   target: string;
  28  |   tipo: string;
  29  |   expected: string | number | null;
  30  |   selector: string | null;  // CSS-ish; null for whole-page oracles
  31  | };
  32  | const ORACLE_PROBES: OracleProbe[] = [
  33  | 
  34  |   {
  35  |     oracle_id: 0,
  36  |     target: "table_agenda_usu",
  37  |     tipo: "count_gt",
  38  |     expected: 0,
  39  |     selector: "#c_GridAgendaUsu"
  40  |   },
  41  | 
  42  | ];
  43  | const ASSERTIONS_OUT_PATH = 'evidence/65/P03/assertions_P03.json';
  44  | 
  45  | test.describe('ADO-65 | P03 — Corredor = valor parcial', () => {
  46  | 
  47  |   test.beforeEach(async ({ page }) => {
  48  |     // SETUP: login via FrmLogin.aspx (AIS rendered controls)
  49  |     // Use noWaitAfter + waitForURL to avoid actionTimeout race on ASP.NET PostBack navigation
  50  |     await page.goto(`${BASE_URL}FrmLogin.aspx`, { waitUntil: 'load' });
  51  |     await page.fill('#c_abfUsuario', USER);
  52  |     await page.fill('#c_abfContrasena', PASS);
  53  |     await page.locator('#c_btnOk').click({ noWaitAfter: true });
  54  |     await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
  55  |     await page.waitForLoadState('load', { timeout: 20000 });
  56  |   });
  57  | 
  58  |   test('p03 corredor_=_valor_parcial', async ({ page }) => {
  59  |     // DATA: OGCORREDOR IS NOT NULL
  60  | 
  61  |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  62  |     
  63  | 
  64  |     // SETUP
  65  |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  66  |     await page.screenshot({ path: 'evidence/65/P03/step_00_setup.png' });
  67  | 
  68  |     // Expand "Búsqueda Avanzada" panel only when needed.
  69  |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  70  |     const advancedPanel = page.locator('#c_pnlBusqueda');
  71  |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  72  |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  73  |     if (!filtersReady) {
  74  |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  75  |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  76  | 
  77  |       if (await toggleByData.count()) {
  78  |         await toggleByData.click({ timeout: 5000 });
  79  |       } else if (await toggleByText.count()) {
  80  |         await toggleByText.click({ timeout: 5000 });
  81  |       }
  82  | 
  83  |       if (await advancedPanel.count()) {
  84  |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  85  |       }
  86  |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  87  |     }
  88  |     console.log('Advanced filters ready:', filtersReady);
  89  |     await page.screenshot({ path: 'screenshots/P03_panel_expanded.png' });
  90  | 
  91  |     // ACTION
  92  |     
  93  |     
  94  |     // [STEP 01] fill input_corredor with "valor parcial"
  95  |     console.log('[STEP 01] fill input_corredor');
  96  |     await page.locator("#c_abfCorredor").fill('valor parcial');;
  97  |     await page.screenshot({ path: 'evidence/65/P03/step_01_after.png' });
  98  |     
  99  |     
  100 |     
  101 |     // [STEP 02] click link_c_btnok
  102 |     console.log('[STEP 02] click link_c_btnok');
  103 |     await page.locator("#c_btnOk").click();
  104 |     await page.waitForLoadState('load');
  105 |     await page.screenshot({ path: 'evidence/65/P03/step_02_after.png' });
  106 |     
  107 |     
  108 | 
  109 |     // ASSERTIONS
  110 |     
  111 |     
> 112 |     await expect(page.locator('#c_GridAgendaUsu')).toHaveCount({ min: 1 });
      |                                                                                     ^ Error: P03: página debe contener "valor parcial"
  113 |     
  114 |     
  115 | 
  116 |     // CLEANUP
  117 |     await page.context().clearCookies();
  118 |   });
  119 | 
  120 |   test.afterEach(async ({ page }) => {
  121 |     // Capture final state screenshot first — fail-safe even if the page is
  122 |     // mid-PostBack.
  123 |     try {
  124 |       await page.screenshot({
  125 |         path: 'evidence/65/P03/step_final_state.png',
  126 |       });
  127 |     } catch (_e) {
  128 |       // ignore — page may be closed or navigating
  129 |     }
  130 | 
  131 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  132 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  133 |     // relying on Playwright's pass/fail (which conflates product defects
  134 |     // with pipeline defects).
  135 |     const captured: any[] = [];
  136 |     for (const probe of ORACLE_PROBES) {
  137 |       const entry: any = {
  138 |         oracle_id: probe.oracle_id,
  139 |         target: probe.target,
  140 |         tipo: probe.tipo,
  141 |         expected: probe.expected,
  142 |       };
  143 |       try {
  144 |         if (probe.selector === null) {
  145 |           // Whole-page oracle: capture the body text once (truncated).
  146 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  147 |           entry.actual_text = bodyText.slice(0, 4000);
  148 |           entry.visible = true;
  149 |         } else {
  150 |           const loc = page.locator(probe.selector);
  151 |           // count
  152 |           const count = await loc.count();
  153 |           entry.count = count;
  154 |           if (count === 0) {
  155 |             entry.visible = false;
  156 |             entry.actual_text = null;
  157 |           } else {
  158 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  159 |             // value (form controls)
  160 |             try {
  161 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  162 |             } catch (_e) { /* not a form control */ }
  163 |             // textContent
  164 |             try {
  165 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  166 |               entry.actual_text = txt.slice(0, 1000);
  167 |             } catch (_e) {
  168 |               entry.actual_text = null;
  169 |             }
  170 |             // disabled / state
  171 |             try {
  172 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  173 |             } catch (_e) { /* ignore */ }
  174 |           }
  175 |         }
  176 |       } catch (e: any) {
  177 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  178 |       }
  179 |       captured.push(entry);
  180 |     }
  181 | 
  182 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
  183 |     // must not break the test runner.
  184 |     try {
  185 |       const outPath = path.resolve(process.cwd(), ASSERTIONS_OUT_PATH);
  186 |       fs.mkdirSync(path.dirname(outPath), { recursive: true });
  187 |       fs.writeFileSync(
  188 |         outPath,
  189 |         JSON.stringify(
  190 |           { scenario_id: 'P03', assertions: captured },
  191 |           null, 2,
  192 |         ),
  193 |         'utf-8',
  194 |       );
  195 |     } catch (e) {
  196 |       console.error('[afterEach] could not persist assertions json:', e);
  197 |     }
  198 | 
  199 |     await page.context().clearCookies();
  200 |   });
  201 | });
```