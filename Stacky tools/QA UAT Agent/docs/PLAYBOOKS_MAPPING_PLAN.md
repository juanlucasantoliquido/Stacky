# Plan de mapeo de Playbooks de Navegación — QA UAT Agent

**Estado:** COMPLETADO (P1)  
**Última actualización:** 2026-05-26 (sesión cont 3 — FrmGestionFlujos + FrmJDemanda + FrmAdministrador DONE; popups P1 documentados como artefacto de Materialize (no existen en trunk); generator extendido para consumir navigation_steps tipados)  
**Autor inicial:** Claude (sesión de Juan Luca)  
**Objetivo del documento:** Handover para que otro agente pueda continuar el mapeo sin re-investigar contexto.

---

## 1. Problema que esto resuelve

El agente QA UAT de GitHub Copilot Pro genera rutas de navegación incorrectas y saltea pasos cuando tiene que llegar a pantallas session-dependent. La causa raíz: el LLM intenta improvisar la navegación en vez de seguir un contrato declarativo.

**Solución adoptada:** poblar `cache/playbooks/*.json` con playbooks fase-por-fase para cada pantalla y sub-flujo crítico. El generator (`playwright_test_generator.py`) ya consume estos playbooks vía `_resolve_entry_screen` (ver `project_qa_uat_navigation_fix` en memoria del proyecto). Lo que faltaba era **cobertura**.

**Decisión arquitectural confirmada con el usuario** (2026-05-26):
- LLM no decide navegación. Sólo selecciona el playbook destino por `confidence_keywords` del índice.
- Mapeo incremental on-demand (no upfront exhaustivo).
- Granularidad por tab + por modal (no por acción individual).

---

## 2. Estado por pantalla — P1 (Prioritario)

### ✅ FrmDetalleClie.aspx — COMPLETADO (sesión 2026-05-26)

Audit hecho contra `trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx` (1400 líneas).

**Hallazgos críticos durante el audit (importantes para próximo agente):**
- Branch canónico = `trunk/`, NO `branches/NetCore/`. El user confirmó esto explícitamente.
- ADO-119 (2026-05-06 RF-008): nuevos campos `abfCorredorPrincipal`, `abfRiesgoCliente`
- ADO-146 (2026-05-14 RF-011): `btnConvenios.OnClick` ELIMINADO → redirige a portal externo vía `OnClientClick` inyectado. Modal `dlgConvenios` queda huérfano en el DOM.
- ADO-148 (2026-05-18 RF-013): nuevo modal `dlgMedioContacto` para gestiones tel/mail/dom.
- ADO-162 (2026-05-20 RF-015): nuevos campos asegurador (`lblPrimaNeta`, `lblIntereses`, `lblMontoCubierto`).

**Archivos producidos** (todos en `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/`):

| Archivo | Tipo | Notas |
|---|---|---|
| `frm_detalle_clie_actions.json` | mapa estático | Corregido: deprecación ADO-146 + nuevos campos ADO-119/162 |
| `open_detalle_clie_tab_relaciones.json` | playbook tab | **Exemplar** validado por el user — usar como referencia de estilo |
| `open_detalle_clie_tab_contactos.json` | playbook tab | Sub-grids con casing minúscula (`gridTelefonosContactos`, `gridMailsContactos`) |
| `open_detalle_clie_tab_pagos.json` | playbook tab | Read-only |
| `open_detalle_clie_tab_garantias.json` | playbook tab | CRUD garantías |
| `open_detalle_clie_tab_scorings.json` | playbook tab | ⚠ `GridPersonas` colisiona con FrmBusqueda — usar `[id*='tabScorings'] [id$='GridPersonas']` |
| `open_detalle_clie_tab_historicos.json` | playbook tab | Read-only, 3 grids |
| `open_detalle_clie_modal_compromisos.json` | playbook modal top-bar | `btnGuardarModalCompromisos` = mutates_data |
| `open_detalle_clie_modal_convenios_DEPRECATED.json` | stub | NO ejecutar — ADO-146 deprecó el botón |
| `open_detalle_clie_modal_estados.json` | playbook modal top-bar | Read-only |
| `open_detalle_clie_modal_cheques.json` | playbook modal top-bar | Read-only |
| `open_detalle_clie_modal_pasaje_judicial.json` | playbook modal top-bar | `btnAceptarCliente` = judicializar (mutates_data + OnClientClick JS confirm) |
| `open_detalle_clie_modal_notas.json` | playbook modal top-bar | `btnGuardarNota` = mutates_data |
| `open_detalle_clie_modal_documento.json` | playbook modal top-bar | Selectores internos vienen de `GestionDocumentosUpload.ascx` — discovery dinámico requerido |
| `open_detalle_clie_modal_medio_contacto.json` | playbook indirecto | Disparado por flujo de gestión, no botón |
| `open_detalle_clie_modal_prestamos.json` | playbook row-triggered | Trigger condicional: fila tipo Préstamo |
| `open_detalle_clie_modal_tarjetas.json` | playbook row-triggered | Casing `dlgtarjetas` (lowercase) |
| `open_detalle_clie_modal_cuentas.json` | playbook row-triggered | Bug semántico ASPX: Titulo='Tarjetas' (no fixear desde QA) |
| `open_detalle_clie_modal_gestiones.json` | playbook row-triggered | Disparado desde GridGestiones row |

**Índices actualizados:**
- `cache/playbooks/index.json` — 25 entradas (5 originales + 2 que faltaban indexar + 18 nuevas)
- `navigation_contracts.yml` — sección `FrmDetalleClie` extendida con `related_playbooks` agrupados + `trunk_change_log`

**Convenciones aplicadas** (mantener estas para próximos playbooks):
- `method: "button_click"` para tabs (NO inventar `tab_click`)
- Sin `approval_required` (decisión del user — el ambiente UAT maneja el resto)
- `stable_selectors` flat (un nivel)
- Doble fallback selector: `"#c_xxx, [id$='xxx']"` por cada control
- `category_on_fail`: NAV / DATA / ENV / APP
- `severity`: hard / soft (soft para sub-paneles que pueden no estar visibles)
- Steps 1-6 idénticos para todo playbook que parta de FrmBusqueda → FrmDetalleClie (no factorizar, mantener self-contained)

---

### ✅ FrmDetalleObligacion.aspx — DESCARTADO (sesión cont. 2026-05-26)

Audit determinó que `FrmDetalleObligacion.aspx` **no existe** en `trunk/OnLine/AgendaWeb/` ni en ninguna otra carpeta del repo. El contrato declarado en `navigation_contracts.yml` era un fantasma. El detalle por tipo de obligación se renderiza **in-page** dentro de `FrmDetalleClie.aspx` vía tres modales row-triggered:

- `dlgPrestamos` → `open_detalle_clie_modal_prestamos` (ya existe)
- `dlgtarjetas` → `open_detalle_clie_modal_tarjetas` (ya existe)
- `dlgCuentas` → `open_detalle_clie_modal_cuentas` (ya existe)

El row-click in-page (`seleccionar_obligacion` en `frm_detalle_clie_actions.json`) sólo actualiza el panel de deuda y togglea `btnJudicial`; no navega a otra pantalla.

**Acción tomada:** sección `FrmDetalleObligacion.aspx` removida de `navigation_contracts.yml` y reemplazada por un comentario explicativo. Si en el futuro se crea una pantalla dedicada, reincorporar el contrato.

---

### ✅ FrmLogin.aspx — COMPLETADO (sesión cont. 2026-05-26)

Audit hecho contra `trunk/OnLine/AgendaWeb/FrmLogin.aspx` + `FrmLogin.aspx.cs`.

**Hallazgos relevantes:**
- DOM mínimo: `abfUsuario` + `abfContrasena` (TextMode=Password) + `ddlDominio` (AISCatalogo) + `btnOk` + `divError`/`lblError`. AISPanel con `DefaultButton="btnOk"` (Enter dispara submit).
- `btnOk_Click` normaliza usuario a UPPERCASE, valida vacíos (`coerr.e1065`), AD (`autentificacion.Errores`), o NATIVO (`coerr.e1224`).
- Post-login: `RedireccionarUsuario` redirige a `FrmAgenda.aspx` / `FrmAgenda.aspx?pool=Si` / `FrmBusqueda.aspx` / `FrmAdministrador.aspx` según perfil → aserción `post_login_home_loaded` marcada **soft** (admite varios destinos).
- **Riesgo crítico documentado en `login_fail`:** `IncrementarNumAccesos` puede bloquear cuentas reales. El playbook explicita que `USR_BAD_USERNAME` debe ser un usuario fantasma, nunca real.

**Archivos producidos:**
- `cache/playbooks/login_explicit.json` — happy path con `USR_USERNAME`/`USR_PASSWORD`/`USR_DOMINIO` (último opcional)
- `cache/playbooks/login_fail.json` — negative path con `USR_BAD_USERNAME`/`USR_BAD_PASSWORD` (defaults seguros: `TESTNOEXISTE` / `invalid_pwd_for_qa_only`)

**Índices actualizados:**
- `cache/playbooks/index.json` — +2 entradas (`login_explicit`, `login_fail`)
- `navigation_contracts.yml` — `FrmLogin.aspx` extendido con `human_paths.open_direct`, `assertions` y `related_playbooks` (happy_path + negative_path)

---

### ✅ FrmBusqueda.aspx variantes — COMPLETADO (sesión cont. 2026-05-26)

Audit hecho contra `trunk/OnLine/AgendaWeb/FrmBusqueda.aspx` (64 líneas, formulario lineal).

**Campos disponibles en FrmBusqueda detectados:**
- Documento: `ddlTipoDocumento` + `abfDocumento` (MaxLength=14)
- Cliente: `abfCodCliente` (CLCOD, MaxLength=20)
- Obligación: `abfCodObligacion` (MaxLength=20)
- Tarjeta: `abfTarjeta` (MaxLength=30)
- Identidad: `abfApellido1`, `abfApellido2`, `abfNombre` (todos MaxLength=30)
- Teléfono: `ddlTipoTelefono` + `abfTelefono`
- Customer: `abfCustomer` (MaxLength=7)
- Rol/Perfil: `ddlRol` (⚠ AutoPostBack=true) + `ddlPerfil`
- Límite: `abfResultados` (default 20, FieldDataType=Entero)
- Acciones: `btnOk` (Buscar), `btnLimpiar`
- Grids: `GridPersonas` (coincidencias) + `GridObligaciones` (obligaciones de la persona seleccionada)

**Archivos producidos:**
- `cache/playbooks/busqueda_por_apellido.json` — fill `abfApellido1` (req) + `abfApellido2`/`abfNombre` (opt) → `btnOk` → `GridPersonas`
- `cache/playbooks/busqueda_por_dni.json` — `ddlTipoDocumento` (opt) + `abfDocumento` (req) → `btnOk`
- `cache/playbooks/busqueda_judicial.json` — pantalla SEPARADA `FrmBusquedaJudicial.aspx`; todos los filtros opcionales (apellido, documento, causa, tipo demanda, fechas, etc.)

**Decisión arquitectural confirmada en sesión:**
- `busqueda_judicial` apunta a `FrmBusquedaJudicial.aspx` (pantalla independiente con sus propios filtros judiciales: `abfCausa`, `ddlTipoDeDemanda`, `abfDesde`/`abfHasta`, `ddlJuzgado`, etc.), **no** es una variante de `FrmBusqueda.aspx`.
- Los IDs de control coinciden parcialmente entre ambas pantallas (`abfApellido1`, `abfDocumento`, etc.) — el dispatcher debe diferenciar por URL (`wait_url_contains`) antes de hacer assertions DOM.

**Índices actualizados:**
- `cache/playbooks/index.json` — +3 entradas (`busqueda_por_apellido`, `busqueda_por_dni`, `busqueda_judicial`)
- `navigation_contracts.yml` — `FrmBusqueda.aspx` extendido con `related_playbooks` (smoke, by_filter, chained); **nuevo contrato `FrmBusquedaJudicial.aspx`** con `human_paths.open_direct` + `related_playbooks.by_filter`

**Convención adicional aplicada (mantener):**
- Steps con `skip_if_empty_data: true` para campos opcionales — el ejecutor de Playwright debe omitir el step si el binding está vacío en lugar de fallar.
- Bloques `optional_data` separados de `required_data` en el JSON del playbook (no soportado por el schema oficial todavía — flagged para evolución del schema en `schemas/ui_map.schema.json`).

---

### ✅ FrmAgendaEquipo.aspx — COMPLETADO (sesión cont 2 — 2026-05-26)

Audit contra `FrmAgendaEquipo.aspx` + `.aspx.cs`. Playbook `open_agenda_equipo`.
- Grillas `GridAgendaUsu` (Agendados por Usuarios) + `GridAgendaAut` (Motor Experto) se pueblan en `Page_Load` (`CargoControles`) con la agenda del equipo completo → **smoke no requiere búsqueda**.
- Filtro en `AISCollapsibleSection lblBusqueda` Active='false' (COLAPSADO). Hay que clickear `.collapsible-header` para revelar `ddlUsuarios`/`ddlRoles`.
- `ddlUsuarios` AutoPostBack → repuebla y habilita `ddlRoles` (que arranca disabled). Orden: usuario → wait postback → rol → `btnOk`.
- Row-click en cualquiera de las 2 grillas → redirige a `FrmDetalleClie.aspx` (Session 'lote' + 'PadreDetalleCliente'). Chain target.

### ✅ FrmAgendaJudicial.aspx — COMPLETADO (sesión cont 2 — 2026-05-26)

Audit contra `FrmAgendaJudicial.aspx` + `.aspx.cs`. Playbook `open_agenda_judicial`.
- `Page_Load` (`CargoControles`) llama `btnBuscar_Click` con filtros default (`abfHasta`=hoy) → grillas `GridAgendaUsu` (Agendas Pendientes) + `GridAgendaWorkFlow` (Agenda Por Etapas) auto-pobladas → **smoke no requiere búsqueda**.
- Filtro en `AISCollapsibleSection acsAgendaJudicial` Active='false' (COLAPSADO).
- `ddlTipoDeDemanda` AutoPostBack → repuebla y habilita `ddlEtapaActual` (cascading, arranca disabled). Orden: tipo juicio → wait postback → etapa.
- Botón de búsqueda es **`btnBuscar`** (no `btnOk`).
- Row-click en cualquiera de las 2 grillas → redirige a `FrmJDemanda.aspx?NumeroDeDemanda=<demanda>` (Session 'PadreDemanda'). **Este es el entry path de FrmJDemanda** mencionado en §7.3 — encadenar desde acá.
- ⚠ IDs colisionan con `FrmBusquedaJudicial.aspx` (GridAgendaUsu, abfApellido1/2, abfDocumento, ddlTipoDocumento, ddlTipoDeDemanda, ddlEtapaActual, ddlRegion, ddlJuzgado) — dispatcher debe filtrar por `wait_url_contains='FrmAgendaJudicial'`.

**Nota de schema (deuda pendiente):** ambos playbooks introducen un campo nuevo `skip_if_empty_data_keys` (array) en navigation_steps — gatea el skip de un step según si CUALQUIERA de varias claves opcionales está vacía (usado en el expand-colapsable y en el click de búsqueda). También usan `wait_after_ms` para esperar el postback de los AutoPostBack. **NINGUNO está en `schemas/ui_map.schema.json`** (ver §7.2 punto 1, misma deuda que `optional_data`/`skip_if_empty_data`). El generator debe ser actualizado para respetarlos o el ejecutor los ignora.

### ✅ FrmGestionFlujos.aspx — COMPLETADO (sesión cont 3 — 2026-05-26)

Audit contra `FrmGestionFlujos.aspx` + `.aspx.cs`. Playbook `open_gestion_flujos`.
- Hub direct-entry del editor de Workflow judicial. Page_Load (!IsPostBack) → `LlenarDDL()` + `CargarDatos()` puebla el árbol `treeviewWF` (AISTreeView, `GetFlujoList()`) y **auto-selecciona el primer nodo** (CargarDetalle). **NO depende de Session para entrar** (no redirige a Login). Smoke = goto + assert árbol.
- Filtros: 2 checkboxes AutoPostBack (`checkHistoricos`, `checkObsoletos`) que reincorporan flujos estado 4/5.
- `btnEditor` → navega a `FrmEditorWorkflow.aspx` (Session IdModelo/IdVersion/AccessMode; puede mostrar `dlgBloqueo`). Chain target.
- Botones que MUTAN: `btnGuardar` (alta/mod modelo), `btnNewVersion`, `btnCopiarVesion`, `btnGuardarVersion`, `btnProduccion`, `btnEliminar` (destructivo). Sólo UAT con flujos de prueba.
- Habilitación de botones depende del estado del nodo seleccionado (`HabilitarBotones`).

### ✅ FrmJDemanda.aspx — COMPLETADO (sesión cont 3 — 2026-05-26)

Audit dirigido contra `FrmJDemanda.aspx` (731) + `.aspx.cs` (3466). Playbook `open_jdemanda`.
- **PARAM-DEPENDENT crítico:** Page_Load (línea 62) hace `Request.QueryString["NumeroDeDemanda"].ToString()` **SIN null-check** → entrar sin el query param = **YSOD** (NullReferenceException). También usa `Session['logUsuario']` y `Session['lote']`.
- **Entry canónico:** chain desde `open_agenda_judicial` (row-click en grillas → `FrmJDemanda.aspx?NumeroDeDemanda=<demanda>`, Session 'PadreDemanda'). Entry alternativo: btnJudicial/pasaje judicial desde FrmDetalleClie. `direct_entry_allowed: false` en el contrato.
- Pantalla tabbed (`AISTabControl 'TabControl'`, AutoPostBack) con 8 tabs: General (etapas/workflow), Demandados, Contactos, Deuda, Gestiones, Embargos, Gastos, Pagos. Header read-only. Footer colapsable 'Acción / Agendar' (`acsEjecutar`) con `gbEjecutar`/`gbAgendar` + `btnEjecutar`.
- Chain targets: `btnCasoPrejudicial` → FrmDetalleClie.aspx; `btnConvenio` → FrmJConvenio.aspx.
- Acciones que MUTAN: btnDesestimarDemanda (finaliza), btnCerrarEtapayAvanzar (avanza workflow), btnBloquearEtapa, btnEjecutar, btnReactivarDemanda, CRUD de tabs. Visibilidad por permisos.

### ✅ FrmAdministrador.aspx — COMPLETADO (sesión cont 3 — 2026-05-26)

Audit contra `FrmAdministrador.aspx` (10 líneas, body vacío) + `.aspx.cs` (182). Playbook `open_administrador`.
- Hub administrativo post-login. El `.aspx` sólo tiene un UpdatePanel vacío `PanelCards`; **todo el menú se genera en code-behind** (`RenderMenuAdministrador` → `GetArbolAdministrador(CodUsuario)`): una card (`div.rs-card-admin`) por nodo raíz, con `AISHyperLink` hijos (`a.rs-btn-action-admin`, `NavigateUrl`=columna Redirect; los HTTP abren _blank).
- **Menú data-driven + permisado:** opciones dependen de los permisos del usuario. IDs de links data-driven (ej. `#c_251`='Administracion de Usuarios') **NO estables** → matchear por CLASE + texto.
- **Try/catch silencioso:** si `Session['logUsuario']` es null, el menú renderiza vacío sin YSOD (por eso la aserción de cards es soft).
- El click en una opción es un anchor (href), no postback. Se modela como `action_step` de catálogo (el destino es scenario-specific), no como navigation_step auto-ejecutado. El flujo existente `agregar_usuario_nuevo` parte de aquí.

### ✅ Popups P1 — DOCUMENTADOS COMO FANTASMA (sesión cont 3 — 2026-05-26)

Los 7 popups P1 (`PopUpAgendar`, `PopUpCompromisos`, `PopUpConvenios`, `PopUpDomicilios`, `PopUpContactos`, `PopUpGastosJudicial`, `PopUpNotasGestiones`) **NO existen en `trunk/`** (rama canónica) — sólo en `branches/Materialize/`. trunk no los referencia (sin window.open/Redireccionar). En trunk esa funcionalidad vive como **modales in-page (AISDialog) y user-controls `.ascx`**, en su mayoría ya cubiertos por playbooks existentes. Mismo patrón que el contrato fantasma `FrmDetalleObligacion`.

**Decisión (confirmada con el user 2026-05-26):** NO mapear contra `branches/Materialize` (sus selectores no matchean el runtime de trunk). Documentados en `agenda_screens.py` (comentario en la sección PopUps) con su cobertura real:

| Popup (sólo Materialize) | Cobertura en trunk |
|---|---|
| PopUpAgendar | footer `gbAgendar`/`btnEjecutar` (`open_jdemanda`) + modal compromisos |
| PopUpCompromisos | `open_detalle_clie_modal_compromisos` |
| PopUpConvenios | DEPRECATED ADO-146 (`open_detalle_clie_modal_convenios_DEPRECATED`) |
| PopUpDomicilios | `MantenedorDirecciones.ascx` (`frm_detalle_clie_domicilios`) |
| PopUpContactos | `open_detalle_clie_tab_contactos` / `ModalMantenedorContactos` |
| PopUpGastosJudicial | `ModalGestionGastosJudiciales` (tab Gastos de `open_jdemanda`) |
| PopUpNotasGestiones | `dlgGestionesJudicial` (`open_jdemanda`) / `open_detalle_clie_modal_gestiones` |

> Nota: `FrmGestion.aspx` y `FrmDetalleLote.aspx` se removieron del listado tras verificar que NO existen en `trunk/OnLine/AgendaWeb/`.
>
> Nota 2: `FrmBusquedaJudicial.aspx` quedó completado vía `busqueda_judicial.json`.

**Catálogo completo de pantallas:** `Tools/Stacky/Stacky tools/QA UAT Agent/agenda_screens.py` (≈100 pantallas + popups).

---

## 3. Estado P2 — Secundario (mapeo on-demand)

No mapear preventivamente. Se mapean cuando aparezca un ticket QA que las toque. Agrupado por dominio para referencia:

- **Administración/config** (10): FrmAdministrador, FrmParametros, FrmFeriados, FrmMonedas, FrmOficinas, FrmProductos, FrmTablasGenerales, FrmTablasGeneralesMandante, FrmMandantes, FrmSegmentacion
- **Asignación/estrategias** (7): FrmAsignarEstudio, FrmAsignarLote, FrmAsignarTipoDeJuicio, FrmEstrategia, FrmAdminEstrategias, FrmEdicionTars, FrmVinculVariablesGMR
- **Judicial** (10): FrmBusquedaJudicial, FrmJDemanda, FrmJEmbargo, FrmJModificarDemanda, FrmJReasignarAbogado, FrmJConvenio, FrmJConveniosAnulados, FrmJElaborarDemanda, FrmRadicarDemanda, FrmValidacionGastosJudicial
- **Liquidaciones/comisiones** (9): FrmLiquidaciones, FrmLiquidarGastos, FrmDetalleLiquidacion, FrmLiquidComisiones, FrmLiquidComisionesDet, FrmLiquidComisionesProg, FrmComisionistas, FrmConfigComisiones, FrmAgenteComisiones
- **Simulación/reportes/envíos/impresión** (10): FrmSimulacionUnitaria, FrmSimulMasiva, FrmReportes, FrmReporteOperativo, FrmInformes, FrmEnviarDocumentacion, FrmMensajes, FrmImpConvenioJudicial, FrmImpFichaClienteJudi, FrmImpFichaClientePre
- **Workflow** (5): WorkflowFrame, FrmEditorWorkflow, FrmIframeWorkflow, FrmEtapaVacia, FrmAvanzarFlow
- **PopUps secundarios** (~25): ver `agenda_screens.py` líneas 137-170

---

## 4. Cómo agregar un nuevo playbook (procedimiento)

### Paso 1 — Audit del .aspx contra `trunk/`

```bash
# Localizar la pantalla en trunk (no en branches/)
ls trunk/OnLine/AgendaWeb/<NombrePantalla>.aspx

# Si la pantalla es grande (>800 líneas) NO leer entera con Read.
# Hacer grep dirigido a estructura:
```

Patrón de grep recomendado para mapear estructura (probado en FrmDetalleClie):
```
AISTabPage|AISDialog|AISButton.*ID=|AISGridView.*ID=|<%--
```

### Paso 2 — Detectar cambios recientes ADO

Buscar en el .aspx comentarios `<%-- ADO-XXX | YYYY-MM-DD | ... --%>` — son señales de cambios recientes que pueden invalidar selectores cacheados.

### Paso 3 — Generar el .json

Copiar la estructura del exemplar `open_detalle_clie_tab_relaciones.json`. Adaptar:
- `playbook_id`, `target_screen`, `entry_screen`, `goal_slug`, `goal_label`, `description`
- `tags`, `confidence_keywords` (críticos — son los que el dispatcher usa para matchear scenarios)
- `navigation_steps` — para playbooks que parten de FrmBusqueda, copiar steps 1-6 del exemplar y customizar step 7+
- `arrival_assertions` — incluir siempre `no_aspnet_error`, `no_login_redirect`, `url_contains_<screen>` + aserciones DOM específicas
- `action_steps` — uno por cada acción discreta del modal/tab. Marcar `mutates_data: true` para writes.
- `static_discovery.stable_selectors` — flat dict, doble fallback `"#c_xxx, [id$='xxx']"`

### Paso 4 — Registrar en índices

1. Agregar entrada en `cache/playbooks/index.json` con `file`, `screen`, `entry_screen`, `tags`, `required_data`, `confidence_keywords`, `goal_label`.
2. Agregar el playbook al bloque `related_playbooks` de la pantalla correspondiente en `navigation_contracts.yml`.

### Paso 5 — Cuando dudas, preguntar al user

El user explicitó (2026-05-26): "que lo que tengas dudas me preguntes". No inventar selectores ni handlers. Si un control no es claro en el .aspx (ej. user-controls externos `.ascx`), marcarlo en `warnings` y preguntar antes de seguir.

**Para aprobar flujos:** presentar en `mermaid` (no listas) — preferencia del usuario guardada en `memory/feedback_approval_flows_mermaid.md`.

---

## 5. Referencias rápidas

- **Generator que consume estos playbooks:** `Tools/Stacky/Stacky tools/QA UAT Agent/playwright_test_generator.py` (función `_resolve_entry_screen`)
- **Template Playwright:** `Tools/Stacky/Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2`
- **Catálogo de pantallas:** `Tools/Stacky/Stacky tools/QA UAT Agent/agenda_screens.py`
- **Contratos de navegación:** `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_contracts.yml`
- **Schema de UI map:** `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/ui_map.schema.json`
- **Memoria relacionada del proyecto:**
  - `project_qa_uat_navigation_fix.md` — fix entry vs target screen
  - `project_stacky_bridge_ports.md` — puerto del bridge (5061 para RSPACIFICO)
  - `feedback_approval_flows_mermaid.md` — preferencia de formato para aprobaciones

---

## 6. Próximo paso recomendado

**TODA la cobertura P1 quedó COMPLETADA (sesión cont 3).** El plan P1 está cerrado:
1. ~~FrmAgendaEquipo.aspx~~ ✅ `open_agenda_equipo`.
2. ~~FrmAgendaJudicial.aspx~~ ✅ `open_agenda_judicial`.
3. ~~FrmGestionFlujos.aspx~~ ✅ `open_gestion_flujos`.
4. ~~FrmJDemanda.aspx~~ ✅ `open_jdemanda` (param-dependent, chained desde agenda judicial).
5. ~~FrmAdministrador.aspx~~ ✅ `open_administrador` (hub menú data-driven).
6. ~~Popups P1~~ ✅ documentados como artefacto de Materilize (no existen en trunk).

**Trabajo P2 / pendiente real (on-demand, no preventivo):**
- Las pantallas P2 (§3) se mapean cuando aparezca un ticket QA que las toque.
- **Validación end-to-end en runtime** (§7.2 punto 2): ninguno de los playbooks nuevos se corrió contra UAT en vivo. Validar selectores marcados "SELECTOR A VERIFICAR EN RUNTIME" (AISTreeView de gestión de flujos, row-click de agenda/jdemanda, clases rs-card-admin del administrador) en la primera corrida real.
- **Honrar `wait_after_ms`** en el ejecutor/template para los AutoPostBack (hoy es metadata inerte en el generator).

### Tickets activos (status 2026-05-26)

Los tickets 120 y 122 mencionados en versiones anteriores del plan apuntaban a `FrmDetalleObligacion.aspx` (fantasma). Antes de bloquear esos tickets en el resolutor, revisar si el agente QA puede satisfacerlos con los playbooks de modales `prestamos/tarjetas/cuentas` que ya existen — si no es suficiente, los tickets necesitan re-clarificación de scope con el dueño funcional.

---

## 7. Handover — Estado preciso para el próximo agente (2026-05-26)

### 7.1 Playbooks completados en esta sesión

| Playbook | Pantalla | Tipo | Notas críticas |
|---|---|---|---|
| `login_explicit` | FrmLogin.aspx | happy path | Aserción `post_login_home_loaded` es **soft** (3 destinos posibles según perfil). USR_DOMINIO es opcional. |
| `login_fail` | FrmLogin.aspx | negative path | ⚠ NUNCA usar `USR_BAD_USERNAME` real (riesgo de bloqueo por `IncrementarNumAccesos`). Defaults seguros embebidos. |
| `busqueda_por_apellido` | FrmBusqueda.aspx | filtro | Aserción de resultados es **soft** (apellido inexistente = grid vacío válido). |
| `busqueda_por_dni` | FrmBusqueda.aspx | filtro | `BUSQ_TIPO_DOC` es la etiqueta exacta del catálogo (case-sensitive). |
| `busqueda_judicial` | FrmBusquedaJudicial.aspx | filtro | Pantalla SEPARADA. IDs colisionan con FrmBusqueda — el dispatcher debe filtrar por URL primero. `ddlEtapaActual` depende de `ddlTipoDeDemanda` (cascading). |

### 7.2 Trabajos NO hechos en esta sesión que el próximo agente debe considerar

1. **Schema evolution — RESUELTO (sesión cont 3, 2026-05-26):** La nota original apuntaba al schema EQUIVOCADO. `schemas/ui_map.schema.json` es el output de `ui_map_builder.py` (mapas de DOM), NO el de playbooks. El schema de playbooks es **`schemas/Playbook.schema.json`** → sus `navigation_steps` referencian `NavigationPlan/1.0#/$defs/NavigationStep` y `arrival_assertions` referencian `AssertionSpec`. **Ambos defs son `additionalProperties: true`** y el enum de `method` ya incluye `goto_direct/button_click/row_click/fill/select/check/wait/...`. Conclusión: `optional_data` (top-level, Playbook es `additionalProperties: true`), `skip_if_empty_data`, `skip_if_empty_data_keys` y `wait_after_ms` **ya son válidos contra el schema — NO hubo que evolucionarlo**.

   **Gap real encontrado y CORREGIDO en el generator:** `playwright_test_generator.py::_playbook_steps_to_pasos` sólo entendía el shape legacy basado en recording (`action: goto/click/fill/...`) e **ignoraba el campo `method`** de los NavigationStep tipados. Eso hacía que los navigation_steps tipados de TODO el corpus moderno (login_explicit, busqueda_*, open_agenda_*, y los 3 nuevos) se descartaran silenciosamente → el spec sólo navegaba al entry_screen sin ejecutar los pasos. **Fix aplicado:**
   - `_playbook_steps_to_pasos` ahora maneja ambos shapes: legacy `action` (sin cambios) + tipado `method` (goto_direct/goto_deeplink→navigate, button_click/link_click/menu_click/row_click/tab_click/form_submit/dopostback→click, fill/select con `data_bindings.value`, check→check_checkbox, wait→wait_networkidle).
   - Nuevo helper `_playbook_step_should_skip` respeta `skip_if_empty_data` (+ `skip_if_empty_data_keys`): omite el step cuando TODAS las claves relevantes resuelven vacías (smoke omite filtros opcionales; con datos los incluye).
   - **Salvaguarda:** los `action_steps` de catálogo tipados (con `action_id`/`trigger`, sin `action` ni `method`) NO se auto-ejecutan — muchos son mutantes/destructivos (btnEliminar, btnProduccion, etc.). Verificado: 0 acciones mutantes filtradas a los pasos generados.
   - Tests: baseline de `tests/unit/test_playwright_test_generator.py` sin cambios (6 fallas pre-existentes ajenas, 5 pasan). Verificación funcional inline: open_agenda_judicial smoke=1 navigate / full=14 pasos; open_jdemanda=navigate+row_click; open_gestion_flujos smoke=1 / full=3.
   - `wait_after_ms` y `text_match` siguen siendo metadata inerte en el generator (no afectan validación). El ejecutor/template los puede honrar a futuro; por ahora `open_administrador` evita selectores ambiguos modelando el click de opción como `action_step` (no navigation_step).

2. **Validación end-to-end pendiente:** ninguno de los 5 playbooks nuevos se ha ejecutado en runtime contra ambiente UAT. Antes de marcarlos como `verified_runtime`, el próximo agente debe:
   - Correr `busqueda_por_apellido` con un apellido de QA conocido y validar selectores en vivo.
   - Correr `login_explicit` con `USR_USERNAME=JAY` (usuario de prueba documentado en `FrmLogin.aspx.cs:44`) y verificar el destino post-redirect.
   - Correr `login_fail` con los defaults y confirmar que el `IncrementarNumAccesos` NO bloquea al usuario fantasma.
   - Actualizar `created_from_recording` o agregar campo `verified_at` cuando pasen las corridas.

3. **Variantes de FrmBusqueda no cubiertas (decisión: NO hacer salvo demanda real):**
   - `busqueda_por_cod_cliente` — ya cubierto por `busqueda_detalle_cliente` existente.
   - `busqueda_por_cod_obligacion` — sin demanda actual, esperar a ticket que lo requiera.
   - `busqueda_por_tarjeta` / `busqueda_por_customer` / `busqueda_por_telefono` — idem, on-demand.
   - `busqueda_por_perfil_rol` — `ddlRol` tiene `AutoPostBack=true` y dispara `ddlRol_SelectedIndexChanged` que repuebla `ddlPerfil`. Si se mapea, el playbook DEBE esperar el postback async entre los dos selects.

4. **Contrato fantasma documentado pero no totalmente limpiado:** el comentario en `navigation_contracts.yml:293` deja la nota explicativa. Si en el futuro alguien busca `FrmDetalleObligacion` por grep esperando un contrato real, no lo encontrará — eso es correcto. No re-introducir el contrato salvo que aparezca un `.aspx` físico.

### 7.3 Próximas pantallas — preparación recomendada

Para **FrmAgendaEquipo.aspx** y **FrmAgendaJudicial.aspx** (los 2 próximos):
- Leer primero los `.aspx` (son cortos, similares a FrmAgenda y FrmBusqueda).
- Verificar si comparten la convención `AISPanel DefaultButton="btnOk"` o si son scaffolding distinto.
- El playbook existente `open_agenda_personal` sirve como template — copiar y adaptar.

Para **FrmGestionFlujos.aspx**:
- Es **judicial workflow**. Hay que leer `FrmGestionFlujos.aspx.cs` Page_Load para entender si redirige a Login cuando falta `Session['demanda']` o equivalente.
- Si es session-dependent: el playbook debe arrancar desde otra pantalla (probablemente `FrmBusquedaJudicial` → seleccionar demanda → ir a flujos).

Para **FrmJDemanda.aspx**:
- Es la pantalla destino de `btnJudicial` en FrmDetalleClie (ya documentado en `frm_detalle_clie_actions.json` action `ver_judicial`).
- Encadenar desde `open_detalle_cliente_from_busqueda` + click en `btnJudicial` (necesita CLCOD + obligación con demanda).
- Convención steps 1-6 idénticos del exemplar de FrmDetalleClie.

### 7.4 Reglas anti-deriva (no romper convenciones)

- **NO inventar selectores.** Si un control no se ve claro en el `.aspx`, dejarlo en `warnings` y preguntar al user. El user explicitó esta regla.
- **NO inventar `tab_click` / métodos no estándar.** Métodos válidos por convención: `goto_direct`, `fill`, `button_click`, `row_click`, `select`, `wait`. Si se necesita uno nuevo, validar primero contra el generator.
- **Mantener steps 1-6 del exemplar self-contained** (no factorizar) para playbooks que partan de FrmBusqueda → FrmDetalleClie.
- **Doble fallback selector** siempre: `"#c_xxx, [id$='xxx']"`. NO usar `[id*=...]` salvo colisiones documentadas (ej. `GridPersonas` entre FrmBusqueda y FrmBusquedaJudicial / tab Scorings).
- **Aprobaciones de flujos al user en formato `mermaid`** (no listas) — preferencia guardada en `memory/feedback_approval_flows_mermaid.md`.
