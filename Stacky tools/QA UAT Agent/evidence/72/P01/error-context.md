# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 72\tests\P01_busqueda_sin_filtros_validacion_de_nuevas_columnas.spec.ts >> ADO-72 | P01 — Búsqueda sin filtros + validación de nuevas columnas >> p01 búsqueda_sin_filtros_+_validación_de_nuevas_columnas
- Location: evidence\72\tests\P01_busqueda_sin_filtros_validacion_de_nuevas_columnas.spec.ts:104:7

# Error details

```
Error: P01: página debe contener "RUC"

expect(locator).toContainText(expected) failed

Locator: locator('body')
Timeout: 5000ms
- Expected substring  -   1
+ Received string     + 203

- RUC
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
+         menulogoutSalirAgenda PersonalUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:17Realizado Hoy:2Total en Agenda:19Barrido Realizado:11%Clientes Asignados:0    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion ManualsearchBúsqueda de InhibicionessearchExcepciones de Conveniosformat_list_bulletedReportes OperativosleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedReportes OBIleaderboardResumen AgendaleaderboardGestión Rol y N.MoraleaderboardGest. Tipo Cliente y N.MoraleaderboardGest. Estrategia y N.MoraleaderboardPromeas de PagoleaderboardRisk Managementformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
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
+                                 Empresa TodasRIPLEYTodas  
+                                 Perfil Todos1 - Soporte AIS155 - Gerente de Cobranzas (Ripley)1660 - Administrador363 - Supervisor de Cobranzas (Ripley)Todos  
+                             
+                             
+                                 Región TodasAISEN DEL GENERAL CARLOS IBAÑEZ DEL CAMPOANTOFAGASTAARAUCANIAARICA Y PARINACOTAATACAMABIO-BIOCOQUIMBOLIBERTADOR GENERAL BERNARDO O HIGGINSLOS LAGOSMAGALLANESMAULEREGION DE LOS RIOSREGION METROPOLITANATARAPACAVALPARAISOTodas  
+                                 Recomendación TodasBAJO -  PILOTO MK BAJOCTEL -  Compra de FonosEMCF -  Empex Con FonoGANC - Terreno Asistido - Clien. con contacto sin CPRCC5 -  Clientes Vigentes entre 121 y 150 d as moraTodas  
+                                 Nivel de Mora TodosCastigoCiclo 1Ciclo 2Ciclo 3Ciclo 4Ciclo 5Ciclo 6Ciclo 7Ciclo 8Ciclo 9Cobranza JudicialCobranza preventivaFlujoJudicialNo MoraPeriodo de autopagoSin AsignarVigenteSin Asignar  
+                                 Tipo de Cliente TodosCliente CastigoCliente JudicialCliente MixtoCliente VigenteTodos  
+                             
+                             
+                                 Ventil 
+                                 Campaña TodasA rellenarTodas  
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
+ 				ClienteLoteFechaHoraRecomendaciónNivel Mora
+ 			
+ 		
+ 	
+
+             
+                 
+ 	Agendados por Motor Experto
+
+                 
+                     grid_onAgendados por Motor Experto
+                 
+             
+             
+ 	
+ 		
+ 			
+ 				ClienteLoteFechaHoraRecomendaciónNivel Mora
+ 			
+ 		
+ 			
+ 				6499714 6499714 6499714649971403/12/202514:53:44EDPP - Compromiso de pago 
+ 			
+ 				12406972 12406972 124069721240697203/12/202514:53:45EDPP - Compromiso de pago 
+ 			
+ 				12266465 12266465 122664651226646503/12/202514:53:45EDPP - Compromiso de pago 
+ 			
+ 				19559074 19559074 195590741955907403/12/202514:53:45EDPP - Compromiso de pago 
+ 			
+ 				12272340 12272340 122723401227234003/12/202514:53:44EDPP - Compromiso de pago 
+ 			
+ 				12261570 12261570 122615701226157003/12/202514:53:44EDPP - Compromiso de pago 
+ 			
+ 				12285038 12285038 122850381228503803/12/202514:53:44EDPP - Compromiso de pago 
+ 			
+ 				10396023 10396023 103960231039602303/12/202514:53:43EDPP - Compromiso de pago 
+ 			
+ 				15471591 15471591 154715911547159103/12/202514:53:43EDPP - Compromiso de pago 
+ 			
+ 				12256873 12256873 122568731225687303/12/202514:53:43EDPP - Compromiso de pago 
+ 			
+ 				12242167 12242167 122421671224216703/12/202514:53:43EDPP - Compromiso de pago 
+ 			
+ 				12326138 12326138 123261381232613803/12/202514:53:42EDPP - Compromiso de pago 
+ 			
+ 				12271212 12271212 122712121227121203/12/202514:53:42EDPP - Compromiso de pago 
+ 			
+ 				16417065 16417065 164170651641706503/12/202514:53:42EDPP - Compromiso de pago 
+ 			
+ 				12405368 12405368 124053681240536803/12/202514:53:42EDPP - Compromiso de pago 
+ 			
+ 				15317201 15317201 153172011531720103/12/202514:53:41EDPP - Compromiso de pago 
+ 			
+ 				12355359 12355359 123553591235535903/12/202514:53:40EDPP - Compromiso de pago 
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
+ Filtrar

Call log:
  - P01: página debe contener "RUC" with timeout 5000ms
  - waiting for locator('body')
    4 × locator resolved to <body id="bodyTag">…</body>
      - unexpected value "
    






























	

        

        
	
                
            

        
	
                

	
            

        menulogoutSalirAgenda PersonalUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:17Realizado Hoy:2Total en Agenda:19Barrido Realizado:11%Clientes Asignados:0    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion ManualsearchBúsqueda de InhibicionessearchExcepciones de Conveniosformat_list_bulletedReportes OperativosleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedReportes OBIleaderboardResumen AgendaleaderboardGestión Rol y N.MoraleaderboardGest. Tipo Cliente y N.MoraleaderboardGest. Estrategia y N.MoraleaderboardPromeas de PagoleaderboardRisk Managementformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
        
            
	
                    
                        
                            
                        
                        
                            
                            
                            
                            AccionesExportar AgendasClientes Asignados
                            chevron_rightAvanzar
                        
                    
                

            
    
	
		search
			Búsqueda Avanzada
		
	
		
                
			
                        
				
                            
                                Desde 
                                Hasta 
                                Empresa TodasRIPLEYTodas  
                                Perfil Todos1 - Soporte AIS155 - Gerente de Cobranzas (Ripley)1660 - Administrador363 - Supervisor de Cobranzas (Ripley)Todos  
                            
                            
                                Región TodasAISEN DEL GENERAL CARLOS IBAÑEZ DEL CAMPOANTOFAGASTAARAUCANIAARICA Y PARINACOTAATACAMABIO-BIOCOQUIMBOLIBERTADOR GENERAL BERNARDO O HIGGINSLOS LAGOSMAGALLANESMAULEREGION DE LOS RIOSREGION METROPOLITANATARAPACAVALPARAISOTodas  
                                Recomendación TodasBAJO -  PILOTO MK BAJOCTEL -  Compra de FonosEMCF -  Empex Con FonoGANC - Terreno Asistido - Clien. con contacto sin CPRCC5 -  Clientes Vigentes entre 121 y 150 d as moraTodas  
                                Nivel de Mora TodosCastigoCiclo 1Ciclo 2Ciclo 3Ciclo 4Ciclo 5Ciclo 6Ciclo 7Ciclo 8Ciclo 9Cobranza JudicialCobranza preventivaFlujoJudicialNo MoraPeriodo de autopagoSin AsignarVigenteSin Asignar  
                                Tipo de Cliente TodosCliente CastigoCliente JudicialCliente MixtoCliente VigenteTodos  
                            
                            
                                Ventil 
                                Campaña TodasA rellenarTodas  
                            
                            
                                
                                    
                                    searchFiltrar
                                
                            
                        
			
                    
		
            
	

    
	
            
                
		Agendados por Usuario
	
                
                    
                
            
            
		
			
				
					ClienteLoteFechaHoraRecomendaciónNivel Mora
				
			
		
	
            
                
		Agendados por Motor Experto
	
                
                    grid_onAgendados por Motor Experto
                
            
            
		
			
				
					ClienteLoteFechaHoraRecomendaciónNivel Mora
				
			
				
					6499714 6499714 6499714649971403/12/202514:53:44EDPP - Compromiso de pago 
				
					12406972 12406972 124069721240697203/12/202514:53:45EDPP - Compromiso de pago 
				
					12266465 12266465 122664651226646503/12/202514:53:45EDPP - Compromiso de pago 
				
					19559074 19559074 195590741955907403/12/202514:53:45EDPP - Compromiso de pago 
				
					12272340 12272340 122723401227234003/12/202514:53:44EDPP - Compromiso de pago 
				
					12261570 12261570 122615701226157003/12/202514:53:44EDPP - Compromiso de pago 
				
					12285038 12285038 122850381228503803/12/202514:53:44EDPP - Compromiso de pago 
				
					10396023 10396023 103960231039602303/12/202514:53:43EDPP - Compromiso de pago 
				
					15471591 15471591 154715911547159103/12/202514:53:43EDPP - Compromiso de pago 
				
					12256873 12256873 122568731225687303/12/202514:53:43EDPP - Compromiso de pago 
				
					12242167 12242167 122421671224216703/12/202514:53:43EDPP - Compromiso de pago 
				
					12326138 12326138 123261381232613803/12/202514:53:42EDPP - Compromiso de pago 
				
					12271212 12271212 122712121227121203/12/202514:53:42EDPP - Compromiso de pago 
				
					16417065 16417065 164170651641706503/12/202514:53:42EDPP - Compromiso de pago 
				
					12405368 12405368 124053681240536803/12/202514:53:42EDPP - Compromiso de pago 
				
					15317201 15317201 153172011531720103/12/202514:53:41EDPP - Compromiso de pago 
				
					12355359 12355359 123553591235535903/12/202514:53:40EDPP - Compromiso de pago 
				
			

			
		
	
        


        
        
    



    
        
        
            
                
                    
                
                
                    
                
                
                    
                
            
        
    


Filtrar"
    5 × locator resolved to <body id="bodyTag">…</body>
      - unexpected value "
    






























	

        

        
                
            
        
	
                

	
            

        menulogoutSalirAgenda PersonalUsuario:USUARIO TESTPendiente de Hoy:0Pendiente de otros Días:17Realizado Hoy:2Total en Agenda:19Barrido Realizado:11%Clientes Asignados:0    format_list_bulletedCobranza PrejudicialeventAgenda Personalevent_notePooles de TrabajosearchBusqueda de Clientesdate_rangeAgenda de Grupoformat_list_bulletedSupervisionswitch_accountReasignacion ManualsearchBúsqueda de InhibicionessearchExcepciones de Conveniosformat_list_bulletedReportes OperativosleaderboardCall CenterleaderboardDistribución por Rol y Nivel de MoraleaderboardDistribución por Tipologia de ClientesleaderboardDistribución por Estrategialeaderboardotros Reportesformat_list_bulletedReportes OBIleaderboardResumen AgendaleaderboardGestión Rol y N.MoraleaderboardGest. Tipo Cliente y N.MoraleaderboardGest. Estrategia y N.MoraleaderboardPromeas de PagoleaderboardRisk Managementformat_list_bulletedCobranza JudicialeventAgenda De DemandassearchBuscar DemandasruleValidar Gastosconfirmation_numberLiquidar Gastosswitch_accountReasignar Abogadoformat_list_bulletedReportes OperativosleaderboardInformacion de DemandasleaderboardInformesformat_list_bulletedReportes OBIleaderboardInformación de Demandasformat_list_bulletedFacturación y GastosruleValidar FacturasruleValidar Notas de GastosreceiptFacturasconfirmation_numberNotas de GastossettingsAdministrador 
        
            
	
                    
                        
                            
                        
                        
                            
                            
                            
                            AccionesExportar AgendasClientes Asignados
                            chevron_rightAvanzar
                        
                    
                

            
    
	
		search
			Búsqueda Avanzada
		
	
		
                
                        
	
                            
                                Desde 
                                Hasta 
                                Empresa TodasRIPLEYTodas  
                                Perfil Todos1 - Soporte AIS155 - Gerente de Cobranzas (Ripley)1660 - Administrador363 - Supervisor de Cobranzas (Ripley)Todos  
                            
                            
                                Región TodasAISEN DEL GENERAL CARLOS IBAÑEZ DEL CAMPOANTOFAGASTAARAUCANIAARICA Y PARINACOTAATACAMABIO-BIOCOQUIMBOLIBERTADOR GENERAL BERNARDO O HIGGINSLOS LAGOSMAGALLANESMAULEREGION DE LOS RIOSREGION METROPOLITANATARAPACAVALPARAISOTodas  
                                Recomendación TodasBAJO -  PILOTO MK BAJOCTEL -  Compra de FonosEMCF -  Empex Con FonoGANC - Terreno Asistido - Clien. con contacto sin CPRCC5 -  Clientes Vigentes entre 121 y 150 d as moraTodas  
                                Nivel de Mora TodosCastigoCiclo 1Ciclo 2Ciclo 3Ciclo 4Ciclo 5Ciclo 6Ciclo 7Ciclo 8Ciclo 9Cobranza JudicialCobranza preventivaFlujoJudicialNo MoraPeriodo de autopagoSin AsignarVigenteSin Asignar  
                                Tipo de Cliente TodosCliente CastigoCliente JudicialCliente MixtoCliente VigenteTodos  
                            
                            
                                Ventil 
                                Campaña TodasA rellenarTodas  
                            
                            
                                
                                    
                                    searchFiltrar
                                
                            
                        

                    
            
	

    
            
                
	Agendados por Usuario

                
                    
                
            
            
	
		
			
				ClienteLoteFechaHoraRecomendaciónNivel Mora
			
		
	

            
                
	Agendados por Motor Experto

                
                    grid_onAgendados por Motor Experto
                
            
            
	
		
			
				ClienteLoteFechaHoraRecomendaciónNivel Mora
			
		
			
				6499714 6499714 6499714649971403/12/202514:53:44EDPP - Compromiso de pago 
			
				12406972 12406972 124069721240697203/12/202514:53:45EDPP - Compromiso de pago 
			
				12266465 12266465 122664651226646503/12/202514:53:45EDPP - Compromiso de pago 
			
				19559074 19559074 195590741955907403/12/202514:53:45EDPP - Compromiso de pago 
			
				12272340 12272340 122723401227234003/12/202514:53:44EDPP - Compromiso de pago 
			
				12261570 12261570 122615701226157003/12/202514:53:44EDPP - Compromiso de pago 
			
				12285038 12285038 122850381228503803/12/202514:53:44EDPP - Compromiso de pago 
			
				10396023 10396023 103960231039602303/12/202514:53:43EDPP - Compromiso de pago 
			
				15471591 15471591 154715911547159103/12/202514:53:43EDPP - Compromiso de pago 
			
				12256873 12256873 122568731225687303/12/202514:53:43EDPP - Compromiso de pago 
			
				12242167 12242167 122421671224216703/12/202514:53:43EDPP - Compromiso de pago 
			
				12326138 12326138 123261381232613803/12/202514:53:42EDPP - Compromiso de pago 
			
				12271212 12271212 122712121227121203/12/202514:53:42EDPP - Compromiso de pago 
			
				16417065 16417065 164170651641706503/12/202514:53:42EDPP - Compromiso de pago 
			
				12405368 12405368 124053681240536803/12/202514:53:42EDPP - Compromiso de pago 
			
				15317201 15317201 153172011531720103/12/202514:53:41EDPP - Compromiso de pago 
			
				12355359 12355359 123553591235535903/12/202514:53:40EDPP - Compromiso de pago 
			
		

		
	

        

        
        
    



    
        
        
            
                
                    
                
                
                    
                
                
                    
                
            
        
    


Filtrar"

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
            - link "USUARIO TEST" [ref=e21] [cursor=pointer]:
              - /url: FrmCambioPass.aspx
          - generic [ref=e23]:
            - generic [ref=e24]: "Pendiente de Hoy:"
            - generic [ref=e25]: "0"
          - generic [ref=e27]:
            - generic [ref=e28]: "Pendiente de otros Días:"
            - generic [ref=e29]: "17"
          - generic [ref=e31]:
            - generic [ref=e32]: "Realizado Hoy:"
            - generic [ref=e33]: "2"
          - generic [ref=e35]:
            - generic [ref=e36]: "Total en Agenda:"
            - generic [ref=e37]: "19"
          - generic [ref=e39]:
            - generic [ref=e40]: "Barrido Realizado:"
            - generic [ref=e41]: 11%
          - generic [ref=e43]:
            - generic [ref=e44]: "Clientes Asignados:"
            - generic [ref=e45]: "0"
    - list [ref=e46]:
      - listitem [ref=e47]:
        - generic [ref=e48]:
          - generic: format_list_bulleted
          - text: Cobranza Prejudicial
        - list [ref=e50]:
          - listitem [ref=e51]:
            - link "event Agenda Personal" [ref=e52] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmAgenda.aspx
              - generic: event
              - text: Agenda Personal
          - listitem [ref=e53]:
            - link "event_note Pooles de Trabajo" [ref=e54] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmAgenda.aspx?q=rh3wPkybH+atHWY9zjvV4w==
              - generic: event_note
              - text: Pooles de Trabajo
          - listitem [ref=e55]:
            - link "search Busqueda de Clientes" [ref=e56] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmBusqueda.aspx
              - generic: search
              - text: Busqueda de Clientes
          - listitem [ref=e57]:
            - link "date_range Agenda de Grupo" [ref=e58] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmAgendaEquipo.aspx
              - generic: date_range
              - text: Agenda de Grupo
          - listitem [ref=e59]:
            - list [ref=e60]:
              - listitem [ref=e61]:
                - generic [ref=e62] [cursor=pointer]:
                  - generic: format_list_bulleted
                  - text: Supervision
              - listitem [ref=e63]:
                - list [ref=e64]:
                  - listitem [ref=e65]:
                    - generic [ref=e66] [cursor=pointer]:
                      - generic: format_list_bulleted
                      - text: Reportes Operativos
                  - listitem [ref=e67]:
                    - list [ref=e68]:
                      - listitem [ref=e69]:
                        - generic [ref=e70] [cursor=pointer]:
                          - generic: format_list_bulleted
                          - text: Reportes OBI
      - listitem [ref=e71]:
        - generic [ref=e72]:
          - generic: format_list_bulleted
          - text: Cobranza Judicial
        - list [ref=e74]:
          - listitem [ref=e75]:
            - link "event Agenda De Demandas" [ref=e76] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmAgendaJudicial.aspx
              - generic: event
              - text: Agenda De Demandas
          - listitem [ref=e77]:
            - link "search Buscar Demandas" [ref=e78] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmBusquedaJudicial.aspx
              - generic: search
              - text: Buscar Demandas
          - listitem [ref=e79]:
            - link "rule Validar Gastos" [ref=e80] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmValidacionGastosJudicial.aspx
              - generic: rule
              - text: Validar Gastos
          - listitem [ref=e81]:
            - link "confirmation_number Liquidar Gastos" [ref=e82] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmLiquidarGastos.aspx
              - generic: confirmation_number
              - text: Liquidar Gastos
          - listitem [ref=e83]:
            - link "switch_account Reasignar Abogado" [ref=e84] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmJReasignarAbogado.aspx
              - generic: switch_account
              - text: Reasignar Abogado
          - listitem [ref=e85]:
            - list [ref=e86]:
              - listitem [ref=e87]:
                - generic [ref=e88] [cursor=pointer]:
                  - generic: format_list_bulleted
                  - text: Reportes Operativos
              - listitem [ref=e89]:
                - list [ref=e90]:
                  - listitem [ref=e91]:
                    - generic [ref=e92] [cursor=pointer]:
                      - generic: format_list_bulleted
                      - text: Reportes OBI
      - listitem [ref=e93]:
        - generic [ref=e94]:
          - generic: format_list_bulleted
          - text: Facturación y Gastos
        - list [ref=e96]:
          - listitem [ref=e97]:
            - link "rule Validar Facturas" [ref=e98] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FiScu1K/9opoNFBT3rUlgpvM=
              - generic: rule
              - text: Validar Facturas
          - listitem [ref=e99]:
            - link "rule Validar Notas de Gastos" [ref=e100] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FieWKk8YQotwBcHU/2DP3KIw=
              - generic: rule
              - text: Validar Notas de Gastos
          - listitem [ref=e101]:
            - link "receipt Facturas" [ref=e102] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiHOOp6prF5Vq+94RnI70taQ=
              - generic: receipt
              - text: Facturas
          - listitem [ref=e103]:
            - link "confirmation_number Notas de Gastos" [ref=e104] [cursor=pointer]:
              - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiEmPUsCvT75NbJGKOtz0/0Y=
              - generic: confirmation_number
              - text: Notas de Gastos
      - listitem [ref=e105]:
        - separator [ref=e106]
      - listitem [ref=e107]:
        - link "settings Administrador" [ref=e108] [cursor=pointer]:
          - /url: /AgendaWebRipleyCHI/FrmAdministrador.aspx
          - generic: settings
          - text: Administrador
      - listitem [ref=e109]
      - listitem [ref=e110]
    - generic [ref=e111]:
      - generic [ref=e115]:
        - link "Acciones" [ref=e116] [cursor=pointer]:
          - /url: "#!"
        - link "chevron_right Avanzar" [ref=e117] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$btnNext','')
          - generic: chevron_right
          - text: Avanzar
      - list [ref=e118]:
        - listitem [ref=e119]:
          - generic [ref=e120] [cursor=pointer]:
            - generic [ref=e121]: search
            - generic [ref=e122]: Búsqueda Avanzada
          - generic [ref=e125]:
            - generic [ref=e126]:
              - generic [ref=e127]:
                - textbox "Desde" [ref=e128]
                - generic [ref=e129]: Desde
              - generic [ref=e130]:
                - textbox "Hasta" [ref=e131]
                - generic [ref=e132]: Hasta
              - generic [ref=e133]:
                - generic [ref=e134]: Empresa
                - combobox "Todas" [ref=e137] [cursor=pointer]:
                  - generic "Todas" [ref=e138]
              - generic [ref=e140]:
                - generic [ref=e141]: Perfil
                - combobox "Todos" [ref=e144] [cursor=pointer]:
                  - generic "Todos" [ref=e145]
            - generic [ref=e147]:
              - generic [ref=e148]:
                - generic [ref=e149]: Región
                - combobox "Todas" [ref=e152] [cursor=pointer]:
                  - generic "Todas" [ref=e153]
              - generic [ref=e155]:
                - generic [ref=e156]: Recomendación
                - combobox "Todas" [ref=e159] [cursor=pointer]:
                  - generic "Todas" [ref=e160]
              - generic [ref=e162]:
                - generic [ref=e163]: Nivel de Mora
                - combobox "Sin Asignar" [ref=e166] [cursor=pointer]:
                  - generic "Sin Asignar" [ref=e167]
              - generic [ref=e169]:
                - generic [ref=e170]: Tipo de Cliente
                - combobox "Todos" [ref=e173] [cursor=pointer]:
                  - generic "Todos" [ref=e174]
            - generic [ref=e176]:
              - generic [ref=e177]:
                - textbox "Ventil" [ref=e178]
                - generic [ref=e179]: Ventil
              - generic [ref=e180]:
                - generic [ref=e181]: Campaña
                - combobox "Todas" [ref=e184] [cursor=pointer]:
                  - generic "Todas" [ref=e185]
            - link "search Filtrar" [active] [ref=e189] [cursor=pointer]:
              - /url: javascript:__doPostBack('ctl00$c$btnOk','')
              - generic: search
              - text: Filtrar
      - generic [ref=e190]:
        - generic [ref=e192]: Agendados por Usuario
        - table [ref=e195]:
          - rowgroup [ref=e196]:
            - row "Cliente Lote Fecha Hora Recomendación Nivel Mora" [ref=e197]:
              - columnheader "Cliente" [ref=e198]:
                - link "Cliente" [ref=e199] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
              - columnheader "Lote" [ref=e200]:
                - link "Lote" [ref=e201] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
              - columnheader "Fecha" [ref=e202]:
                - link "Fecha" [ref=e203] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
              - columnheader "Hora" [ref=e204]:
                - link "Hora" [ref=e205] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
              - columnheader "Recomendación" [ref=e206]:
                - link "Recomendación" [ref=e207] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
              - columnheader "Nivel Mora" [ref=e208]:
                - link "Nivel Mora" [ref=e209] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
        - generic [ref=e210]:
          - generic [ref=e211]: Agendados por Motor Experto
          - link "grid_on Agendados por Motor Experto" [ref=e213] [cursor=pointer]:
            - /url: javascript:__doPostBack('ctl00$c$btnExportExcelAg','')
            - generic: grid_on
            - text: Agendados por Motor Experto
        - table [ref=e215]:
          - rowgroup [ref=e216]:
            - row "Cliente Lote Fecha Hora Recomendación Nivel Mora" [ref=e217]:
              - columnheader "Cliente" [ref=e218]:
                - link "Cliente" [ref=e219] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
              - columnheader "Lote" [ref=e220]:
                - link "Lote" [ref=e221] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
              - columnheader "Fecha" [ref=e222]:
                - link "Fecha" [ref=e223] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
              - columnheader "Hora" [ref=e224]:
                - link "Hora" [ref=e225] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
              - columnheader "Recomendación" [ref=e226]:
                - link "Recomendación" [ref=e227] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
              - columnheader "Nivel Mora" [ref=e228]:
                - link "Nivel Mora" [ref=e229] [cursor=pointer]:
                  - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
          - rowgroup [ref=e230]:
            - row "6499714 6499714 6499714 6499714 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e231]:
              - cell "6499714 6499714 6499714" [ref=e232] [cursor=pointer]
              - cell "6499714" [ref=e233] [cursor=pointer]
              - cell "03/12/2025" [ref=e234] [cursor=pointer]
              - cell "14:53:44" [ref=e235] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e236] [cursor=pointer]
              - cell [ref=e237] [cursor=pointer]
            - row "12406972 12406972 12406972 12406972 03/12/2025 14:53:45 EDPP - Compromiso de pago" [ref=e238]:
              - cell "12406972 12406972 12406972" [ref=e239] [cursor=pointer]
              - cell "12406972" [ref=e240] [cursor=pointer]
              - cell "03/12/2025" [ref=e241] [cursor=pointer]
              - cell "14:53:45" [ref=e242] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e243] [cursor=pointer]
              - cell [ref=e244] [cursor=pointer]
            - row "12266465 12266465 12266465 12266465 03/12/2025 14:53:45 EDPP - Compromiso de pago" [ref=e245]:
              - cell "12266465 12266465 12266465" [ref=e246] [cursor=pointer]
              - cell "12266465" [ref=e247] [cursor=pointer]
              - cell "03/12/2025" [ref=e248] [cursor=pointer]
              - cell "14:53:45" [ref=e249] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e250] [cursor=pointer]
              - cell [ref=e251] [cursor=pointer]
            - row "19559074 19559074 19559074 19559074 03/12/2025 14:53:45 EDPP - Compromiso de pago" [ref=e252]:
              - cell "19559074 19559074 19559074" [ref=e253] [cursor=pointer]
              - cell "19559074" [ref=e254] [cursor=pointer]
              - cell "03/12/2025" [ref=e255] [cursor=pointer]
              - cell "14:53:45" [ref=e256] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e257] [cursor=pointer]
              - cell [ref=e258] [cursor=pointer]
            - row "12272340 12272340 12272340 12272340 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e259]:
              - cell "12272340 12272340 12272340" [ref=e260] [cursor=pointer]
              - cell "12272340" [ref=e261] [cursor=pointer]
              - cell "03/12/2025" [ref=e262] [cursor=pointer]
              - cell "14:53:44" [ref=e263] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e264] [cursor=pointer]
              - cell [ref=e265] [cursor=pointer]
            - row "12261570 12261570 12261570 12261570 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e266]:
              - cell "12261570 12261570 12261570" [ref=e267] [cursor=pointer]
              - cell "12261570" [ref=e268] [cursor=pointer]
              - cell "03/12/2025" [ref=e269] [cursor=pointer]
              - cell "14:53:44" [ref=e270] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e271] [cursor=pointer]
              - cell [ref=e272] [cursor=pointer]
            - row "12285038 12285038 12285038 12285038 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e273]:
              - cell "12285038 12285038 12285038" [ref=e274] [cursor=pointer]
              - cell "12285038" [ref=e275] [cursor=pointer]
              - cell "03/12/2025" [ref=e276] [cursor=pointer]
              - cell "14:53:44" [ref=e277] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e278] [cursor=pointer]
              - cell [ref=e279] [cursor=pointer]
            - row "10396023 10396023 10396023 10396023 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e280]:
              - cell "10396023 10396023 10396023" [ref=e281] [cursor=pointer]
              - cell "10396023" [ref=e282] [cursor=pointer]
              - cell "03/12/2025" [ref=e283] [cursor=pointer]
              - cell "14:53:43" [ref=e284] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e285] [cursor=pointer]
              - cell [ref=e286] [cursor=pointer]
            - row "15471591 15471591 15471591 15471591 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e287]:
              - cell "15471591 15471591 15471591" [ref=e288] [cursor=pointer]
              - cell "15471591" [ref=e289] [cursor=pointer]
              - cell "03/12/2025" [ref=e290] [cursor=pointer]
              - cell "14:53:43" [ref=e291] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e292] [cursor=pointer]
              - cell [ref=e293] [cursor=pointer]
            - row "12256873 12256873 12256873 12256873 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e294]:
              - cell "12256873 12256873 12256873" [ref=e295] [cursor=pointer]
              - cell "12256873" [ref=e296] [cursor=pointer]
              - cell "03/12/2025" [ref=e297] [cursor=pointer]
              - cell "14:53:43" [ref=e298] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e299] [cursor=pointer]
              - cell [ref=e300] [cursor=pointer]
            - row "12242167 12242167 12242167 12242167 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e301]:
              - cell "12242167 12242167 12242167" [ref=e302] [cursor=pointer]
              - cell "12242167" [ref=e303] [cursor=pointer]
              - cell "03/12/2025" [ref=e304] [cursor=pointer]
              - cell "14:53:43" [ref=e305] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e306] [cursor=pointer]
              - cell [ref=e307] [cursor=pointer]
            - row "12326138 12326138 12326138 12326138 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e308]:
              - cell "12326138 12326138 12326138" [ref=e309] [cursor=pointer]
              - cell "12326138" [ref=e310] [cursor=pointer]
              - cell "03/12/2025" [ref=e311] [cursor=pointer]
              - cell "14:53:42" [ref=e312] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e313] [cursor=pointer]
              - cell [ref=e314] [cursor=pointer]
            - row "12271212 12271212 12271212 12271212 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e315]:
              - cell "12271212 12271212 12271212" [ref=e316] [cursor=pointer]
              - cell "12271212" [ref=e317] [cursor=pointer]
              - cell "03/12/2025" [ref=e318] [cursor=pointer]
              - cell "14:53:42" [ref=e319] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e320] [cursor=pointer]
              - cell [ref=e321] [cursor=pointer]
            - row "16417065 16417065 16417065 16417065 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e322]:
              - cell "16417065 16417065 16417065" [ref=e323] [cursor=pointer]
              - cell "16417065" [ref=e324] [cursor=pointer]
              - cell "03/12/2025" [ref=e325] [cursor=pointer]
              - cell "14:53:42" [ref=e326] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e327] [cursor=pointer]
              - cell [ref=e328] [cursor=pointer]
            - row "12405368 12405368 12405368 12405368 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e329]:
              - cell "12405368 12405368 12405368" [ref=e330] [cursor=pointer]
              - cell "12405368" [ref=e331] [cursor=pointer]
              - cell "03/12/2025" [ref=e332] [cursor=pointer]
              - cell "14:53:42" [ref=e333] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e334] [cursor=pointer]
              - cell [ref=e335] [cursor=pointer]
            - row "15317201 15317201 15317201 15317201 03/12/2025 14:53:41 EDPP - Compromiso de pago" [ref=e336]:
              - cell "15317201 15317201 15317201" [ref=e337] [cursor=pointer]
              - cell "15317201" [ref=e338] [cursor=pointer]
              - cell "03/12/2025" [ref=e339] [cursor=pointer]
              - cell "14:53:41" [ref=e340] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e341] [cursor=pointer]
              - cell [ref=e342] [cursor=pointer]
            - row "12355359 12355359 12355359 12355359 03/12/2025 14:53:40 EDPP - Compromiso de pago" [ref=e343]:
              - cell "12355359 12355359 12355359" [ref=e344] [cursor=pointer]
              - cell "12355359" [ref=e345] [cursor=pointer]
              - cell "03/12/2025" [ref=e346] [cursor=pointer]
              - cell "14:53:40" [ref=e347] [cursor=pointer]
              - cell "EDPP - Compromiso de pago" [ref=e348] [cursor=pointer]
              - cell [ref=e349] [cursor=pointer]
          - rowgroup
  - generic:
    - generic: Filtrar
```

# Test source

```ts
  78  | // STEP_BBOXES — accumulates bounding boxes of interacted elements per step.
  79  | // Written by test.afterEach to evidence/<ticket>/<sid>/step_bboxes.json and
  80  | // consumed by screenshot_annotator.py (Fase 2) to draw red boxes on screenshots.
  81  | type StepBboxEntry = {
  82  |   step_index: number;
  83  |   screenshot_path: string;
  84  |   target: string;
  85  |   bbox: { x: number; y: number; width: number; height: number } | null;
  86  | };
  87  | const STEP_BBOXES: StepBboxEntry[] = [];
  88  | const STEP_BBOXES_OUT_PATH = 'evidence/72/P01/step_bboxes.json';
  89  | 
  90  | 
  91  | test.describe('ADO-72 | P01 — Búsqueda sin filtros + validación de nuevas columnas', () => {
  92  | 
  93  |   test.beforeEach(async ({ page }) => {
  94  |     // SETUP: login via FrmLogin.aspx (AIS rendered controls)
  95  |     // Use noWaitAfter + waitForURL to avoid actionTimeout race on ASP.NET PostBack navigation
  96  |     await page.goto(`${BASE_URL}FrmLogin.aspx`, { waitUntil: 'load' });
  97  |     await page.fill('#c_abfUsuario', USER);
  98  |     await page.fill('#c_abfContrasena', PASS);
  99  |     await page.locator('#c_btnOk').click({ noWaitAfter: true });
  100 |     await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
  101 |     await page.waitForLoadState('load', { timeout: 20000 });
  102 |   });
  103 | 
  104 |   test('p01 búsqueda_sin_filtros_+_validación_de_nuevas_columnas', async ({ page }) => {
  105 |     // DATA: AGLOTE='4127924112345393' OR AGLOTE='1011240108601559' AND AGHECHO='P'
  106 | 
  107 |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  108 |     
  109 | 
  110 |     // SETUP
  111 |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  112 |     await page.screenshot({ path: 'evidence/72/P01/step_00_setup.png' });
  113 | 
  114 |     // Expand "Búsqueda Avanzada" panel only when needed.
  115 |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  116 |     const advancedPanel = page.locator('#c_pnlBusqueda');
  117 |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  118 |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  119 |     if (!filtersReady) {
  120 |       const toggleByHeader = page.locator('.collapsible-header:has-text("Búsqueda Avanzada"), li:has-text("Búsqueda Avanzada") .collapsible-header').first();
  121 |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  122 |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  123 | 
  124 |       if (await toggleByHeader.count()) {
  125 |         await toggleByHeader.scrollIntoViewIfNeeded();
  126 |         await toggleByHeader.click({ timeout: 5000, force: true });
  127 |       } else if (await toggleByData.count()) {
  128 |         await toggleByData.click({ timeout: 5000, force: true });
  129 |       } else if (await toggleByText.count()) {
  130 |         await toggleByText.click({ timeout: 5000, force: true });
  131 |       }
  132 | 
  133 |       if (await advancedPanel.count()) {
  134 |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  135 |       }
  136 |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  137 | 
  138 |       // Last-resort fallback for legacy WebForms layouts where the toggle
  139 |       // exists but does not update aria/visibility attributes consistently.
  140 |       if (!filtersReady && await advancedPanel.count()) {
  141 |         await page.evaluate(() => {
  142 |           const pnl = document.querySelector('#c_pnlBusqueda') as HTMLElement | null;
  143 |           if (pnl) {
  144 |             pnl.style.display = 'block';
  145 |             pnl.classList.add('active');
  146 |           }
  147 |         });
  148 |         filtersReady = await firstFilter.first().isVisible().catch(() => false);
  149 |       }
  150 |     }
  151 |     console.log('Advanced filters ready:', filtersReady);
  152 |     await page.screenshot({ path: 'screenshots/P01_panel_expanded.png' });
  153 | 
  154 |     // ACTION
  155 |     
  156 |     
  157 |     // [STEP 01] click link_c_btnok
  158 |     console.log('[STEP 01] click link_c_btnok');
  159 |     await page.locator("#c_btnOk").click({ force: true });
  160 |     await page.waitForLoadState('load');
  161 |     await page.screenshot({ path: 'evidence/72/P01/step_01_after.png' });
  162 |     STEP_BBOXES.push({ step_index: 1, screenshot_path: 'evidence/72/P01/step_01_after.png', target: "link_c_btnok", bbox: await page.locator("#c_btnOk").boundingBox().catch(() => null) });
  163 |     
  164 |     
  165 |     
  166 | 
  167 |     // ASSERTIONS
  168 |     
  169 |     
  170 |     await expect(page.locator('#c_GridAgendaUsu'), 'P01: table_agenda_usu debe ser visible').toBeVisible();
  171 |     
  172 |     
  173 |     
  174 |     await expect(page.locator('#c_GridAgendaAut'), 'P01: table_agenda_aut debe ser visible').toBeVisible();
  175 |     
  176 |     
  177 |     
> 178 |     await expect(page.locator('body'), 'P01: página debe contener "RUC"').toContainText('RUC');
      |                                                                           ^ Error: P01: página debe contener "RUC"
  179 |     
  180 |     
  181 |     
  182 |     await expect(page.locator('body'), 'P01: página debe contener "Corredor"').toContainText('Corredor');
  183 |     
  184 |     
  185 |     
  186 |     await expect(page.locator('body'), 'P01: página debe contener "Débito Auto"').toContainText('Débito Auto');
  187 |     
  188 |     
  189 | 
  190 |     // CLEANUP
  191 |     await page.context().clearCookies();
  192 |   });
  193 | 
  194 |   test.afterEach(async ({ page }) => {
  195 |     // Capture final state screenshot first — fail-safe even if the page is
  196 |     // mid-PostBack.
  197 |     try {
  198 |       await page.screenshot({
  199 |         path: 'evidence/72/P01/step_final_state.png',
  200 |       });
  201 |     } catch (_e) {
  202 |       // ignore — page may be closed or navigating
  203 |     }
  204 | 
  205 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  206 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  207 |     // relying on Playwright's pass/fail (which conflates product defects
  208 |     // with pipeline defects).
  209 |     const captured: any[] = [];
  210 |     for (const probe of ORACLE_PROBES) {
  211 |       const entry: any = {
  212 |         oracle_id: probe.oracle_id,
  213 |         target: probe.target,
  214 |         tipo: probe.tipo,
  215 |         expected: probe.expected,
  216 |       };
  217 |       try {
  218 |         if (probe.selector === null) {
  219 |           // Whole-page oracle: capture the body text once (truncated).
  220 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  221 |           entry.actual_text = bodyText.slice(0, 4000);
  222 |           entry.visible = true;
  223 |         } else {
  224 |           const loc = page.locator(probe.selector);
  225 |           // count
  226 |           const count = await loc.count();
  227 |           entry.count = count;
  228 |           if (count === 0) {
  229 |             entry.visible = false;
  230 |             entry.actual_text = null;
  231 |           } else {
  232 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  233 |             // value (form controls)
  234 |             try {
  235 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  236 |             } catch (_e) { /* not a form control */ }
  237 |             // textContent
  238 |             try {
  239 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  240 |               entry.actual_text = txt.slice(0, 1000);
  241 |             } catch (_e) {
  242 |               entry.actual_text = null;
  243 |             }
  244 |             // disabled / state
  245 |             try {
  246 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  247 |             } catch (_e) { /* ignore */ }
  248 |           }
  249 |         }
  250 |       } catch (e: any) {
  251 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  252 |       }
  253 |       captured.push(entry);
  254 |     }
  255 | 
  256 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
  257 |     // must not break the test runner.
  258 |     try {
  259 |       const outPath = path.resolve(process.cwd(), ASSERTIONS_OUT_PATH);
  260 |       fs.mkdirSync(path.dirname(outPath), { recursive: true });
  261 |       fs.writeFileSync(
  262 |         outPath,
  263 |         JSON.stringify(
  264 |           { scenario_id: 'P01', assertions: captured },
  265 |           null, 2,
  266 |         ),
  267 |         'utf-8',
  268 |       );
  269 |     } catch (e) {
  270 |       console.error('[afterEach] could not persist assertions json:', e);
  271 |     }
  272 | 
  273 |     // Persist step_bboxes.json for screenshot_annotator.py (Fase 2).
  274 |     // Non-fatal: if this fails the pipeline continues without annotations.
  275 |     if (STEP_BBOXES.length > 0) {
  276 |       try {
  277 |         const bboxOutPath = path.resolve(process.cwd(), STEP_BBOXES_OUT_PATH);
  278 |         fs.mkdirSync(path.dirname(bboxOutPath), { recursive: true });
```