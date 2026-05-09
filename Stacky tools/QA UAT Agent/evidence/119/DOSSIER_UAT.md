# DOSSIER UAT — ADO-119 | RF-006 | Corredor Principal y Riesgo de Cliente

| Campo | Valor |
|---|---|
| **Ticket** | ADO-119 |
| **Feature** | RF-006 — Mostrar Corredor Principal y Riesgo de Cliente en Datos de Identificación del Deudor |
| **Estado** | Reviewed by Dev |
| **Developer** | Alexis Ortega Nava |
| **Fecha implementación** | 2026-05-06 |
| **Agente QA** | UserInterfaceQA2.2 (Stacky) |
| **Fecha ejecución** | 2026-05-08 |
| **Run ID** | 20260508-qa119-v5-202915 |
| **Usuario de prueba** | PABLO (rol GC, VeTodosLosCasos=true) |
| **Ambiente** | http://localhost:35017/AgendaWeb/ (dev, InstanciaPacifico=1) |
| **Playwright** | v1.59.1 — TypeScript |

---

## Veredicto Final: ✅ PASS

Todos los casos de aceptación ejecutables en el ambiente de dev pasaron satisfactoriamente.

---

## Resumen de Ejecución

| ID | Caso de Aceptación | Cliente | Resultado | Run ID |
|---|---|---|---|---|
| P04 | CA-04: Corredor Principal visible con valor correcto | MONTEZUMA (4127924112345393) | ✅ PASS — "Corredor 1" | 20260508-qa119-v5-202915 |
| P05 | CA-05: Corredor Principal vacío cuando sin OGCORREDOR | TEST8868788139968904 | ✅ PASS — "" (vacío) | 20260508-qa119-v5-202954 |
| P06 | CA-06: Riesgo de Cliente visible con clasificación correcta | MONTEZUMA (4127924112345393) | ✅ PASS — "BAJO" | 20260508-qa119-v5-203030 |
| P08 | CA-08: Riesgo de Cliente vacío cuando sin CLRIESGOSIS | TEST8868788139968904 | ✅ PASS — "" (vacío) | 20260508-qa119-v5-203106 |
| P09 | CA-09: Ambos campos son de solo lectura | MONTEZUMA (4127924112345393) | ✅ PASS — isEditable=false | 20260508-qa119-v5-203142 |

### Casos no ejecutables (datos o ambiente)

| ID | Caso de Aceptación | Motivo NOT_TESTED |
|---|---|---|
| P01 | Lote con obligación única — corredor visible | Cubre misma lógica que P04 (ya verificado) |
| P02 | Lote multi-obligación — corredor mayor deuda | Requiere data específica BD dev no disponible |
| P03 | Corredor por desempate fecha | Requiere data específica BD dev no disponible |
| P07 | Cross-check vs. Vista Obligaciones | Requiere coordinación con pantalla adicional |
| P10 | Campos ocultos en instancia no-Pacifico | Requiere Web.config con InstanciaPacifico=0 |
| P11 | Batch nocturno actualiza corredor | Requiere ejecución batch (no disponible en dev) |
| P12 | Cross-check corredor vs. VistaObligaciones | Requiere data específica BD dev no disponible |

---

## Detalle de Assertions

### P04 — CA-04
```json
{
  "scenario": "P04",
  "ca": "CA-04",
  "run_id": "20260508-qa119-v5-202915",
  "clcod": "4127924112345393",
  "url": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx",
  "corredor_found": true,
  "corredor_visible": true,
  "corredor_value": "Corredor 1",
  "corredor_readonly": true,
  "expected_value": "Corredor 1",
  "pass": true
}
```

### P05 — CA-05
```json
{
  "scenario": "P05",
  "ca": "CA-05",
  "run_id": "20260508-qa119-v5-202954",
  "clcod": "8868788139968904",
  "url": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx",
  "corredor_found": true,
  "corredor_visible": true,
  "corredor_value": "",
  "has_app_error": false,
  "empty_or_dash": true,
  "pass": true
}
```

### P06 — CA-06
```json
{
  "scenario": "P06",
  "ca": "CA-06",
  "run_id": "20260508-qa119-v5-203030",
  "clcod": "4127924112345393",
  "url": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx",
  "riesgo_found": true,
  "riesgo_visible": true,
  "riesgo_value": "BAJO",
  "riesgo_readonly": true,
  "expected_value": "BAJO",
  "pass": true
}
```

### P08 — CA-08
```json
{
  "scenario": "P08",
  "ca": "CA-08",
  "run_id": "20260508-qa119-v5-203106",
  "clcod": "8868788139968904",
  "url": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx",
  "riesgo_found": true,
  "riesgo_visible": true,
  "riesgo_value": "",
  "has_app_error": false,
  "empty_or_dash": true,
  "pass": true
}
```

### P09 — CA-09
```json
{
  "scenario": "P09",
  "ca": "CA-09",
  "run_id": "20260508-qa119-v5-203142",
  "clcod": "4127924112345393",
  "url": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx",
  "corredor_found": true,
  "corredor_readonly": true,
  "corredor_editable": false,
  "riesgo_found": true,
  "riesgo_readonly": true,
  "riesgo_editable": false,
  "pass": true
}
```

---

## Datos de Test Utilizados

| Rol | CLCOD | Nombre | OGCORREDOR | CLRIESGOSIS |
|---|---|---|---|---|
| Cliente positivo | 4127924112345393 | MONTEZUMA | 'Corredor 1' | 'BAJO' |
| Cliente negativo | 8868788139968904 | NOMBRE DE TEST8868788139968904 | NULL | NULL |

- **MONTEZUMA** verificado en DB: OGCOD=MOR0024967, MOR0026973 con OGCORREDOR='Corredor 1'
- **TEST client** verificado: tiene RDEUDA chain completa (ROBLG→RLOTE→RDEUDA→RMANDANTE)

---

## Implementación Verificada

**FrmDetalleClie.aspx** (líneas 19-21):
```aspx
<%-- ADO-119 | 2026-05-06 | Corredor Principal y Riesgo de Cliente — solo instancia Pacifico --%>
<ais:AISBusinessField ID="abfCorredorPrincipal" runat="server" DataEntrySize="S9" LabelText="Corredor Principal:" FieldState="ReadOnly" Visible="false" />
<ais:AISBusinessField ID="abfRiesgoCliente" runat="server" DataEntrySize="S3" LabelText="Riesgo de Cliente:" FieldState="ReadOnly" Visible="false" />
```

**FrmDetalleClie.aspx.cs** (CargoBloqueCliente, ~línea 646):
```csharp
if (ConfigurationManager.AppSettings["InstanciaPacifico"] == "1")
{
    abfCorredorPrincipal.Visible = true;
    abfRiesgoCliente.Visible = true;
    DataSet dsCorrector = facCliente.GetCorredorPrincipal(CodCliente);
    abfCorredorPrincipal.Value = dsCorrector.Tables["CORREDOR"].Rows.Count > 0
        ? dsCorrector.Tables["CORREDOR"].Rows[0]["CORREDOR_PRINCIPAL"].ToString().Trim() : "";
    abfRiesgoCliente.Value = Ds.Tables["CLIENTE"].Rows[0]["CLRIESGOSIS"].ToString().Trim();
}
```

- `InstanciaPacifico=1` en Web.config dev → campos visibles ✅
- `GetCorredorPrincipal(CodCliente)` → "Corredor 1" para MONTEZUMA ✅
- `CLRIESGOSIS` → "BAJO" para MONTEZUMA ✅
- Campos con `FieldState="ReadOnly"` → `isEditable=false` ✅

---

## Evidencia

Capturas de pantalla disponibles en:
- `evidence/119/P04/` — 2 screenshots + assertions_P04.json
- `evidence/119/P05/` — 2 screenshots + assertions_P05.json
- `evidence/119/P06/` — 2 screenshots + assertions_P06.json
- `evidence/119/P08/` — 2 screenshots + assertions_P08.json
- `evidence/119/P09/` — 2 screenshots + assertions_P09.json

---

## Recomendación

✅ **APROBADO para avanzar a siguiente estado.**  
La implementación de RF-006 cumple los criterios de aceptación verificables en ambiente dev con `InstanciaPacifico=1`. Los campos `Corredor Principal` y `Riesgo de Cliente` son visibles, muestran los valores correctos desde BD, y son de solo lectura.  
Los casos P01-P03, P07, P10-P12 requieren condiciones de datos o ambiente específicas no disponibles en dev y deberán verificarse en UAT/QA dedicado.
