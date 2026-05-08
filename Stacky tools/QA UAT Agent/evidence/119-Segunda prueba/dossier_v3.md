## 🔴 Dossier UAT Final — ADO-119 (v3)

**Veredicto: BLOCKED** | 0/5 OK, 0 KO, 5 BLOCKED

### Parámetros de ejecución

| Parámetro | Valor |
|-----------|-------|
| Fecha/Hora | 2026-05-08 05:35:14 UTC |
| Usuario UAT | PABLO |
| URL Agenda Web | http://localhost:35017/AgendaWeb/ |
| Run ID | 20260508-qa119-v3-053352 |
| Dato de prueba | MONTEZUMA (CLCOD=4127924112345393) |
| OGCORREDOR esperado | 'Corredor 1' |
| CLRIESGOSIS esperado | 'BAJO' |

### Resultados por escenario

| Escenario | CA-REF | Veredicto | Detalle |
|-----------|--------|-----------|---------|
| P04 | CA-04 | 🔴 BLOCKED | FrmBusqueda sin resultados para MONTEZUMA |
| P05 | CA-05 | 🔴 BLOCKED | FrmBusqueda sin resultados para búsqueda genérica |
| P06 | CA-06 | 🔴 BLOCKED | FrmBusqueda sin resultados para MONTEZUMA |
| P08 | CA-08 | 🔴 BLOCKED | FrmBusqueda sin resultados para búsqueda genérica |
| P09 | CA-09 | 🔴 BLOCKED | FrmBusqueda sin resultados para MONTEZUMA |

### Escenarios no ejecutados en esta suite

| Escenario | CA-REF | Motivo |
|-----------|--------|--------|
| P01 | CA-01 | Requiere múltiples obligaciones con distinto OGCORREDOR (datos de batch) |
| P02 | CA-02 | Requiere lote con 3 obligaciones y distintos importes (datos de batch) |
| P03 | CA-03 | Requiere empate de deuda con distintas fechas mora (datos de batch) |
| P07 | CA-07 | Requiere Vista Obligaciones con datos post-batch |
| P10 | CA-10 | Requiere instancia no-Pacifico (Web.config distinto) |
| P11 | CA-11 | Requiere ciclo de batch nocturno |
| P12 | CA-12 | Requiere Vista Obligaciones con datos post-batch |

### Artefactos capturados

- `evidence/119/P04_P06_P09_montezuma.png` — FrmDetalleClie MONTEZUMA
- `evidence/119/P05_P08_empty_client.png` — FrmDetalleClie cliente sin datos

### Análisis del bloqueo anterior (2026-05-08)

El run anterior fue BLOCKED porque el agente QA navegó a **FrmAgenda.aspx** para obtener el lote. El usuario PABLO no tenía lotes asignados en la agenda, por lo que la tabla no renderizó filas. **Fix aplicado en v3**: navegación vía **FrmBusqueda.aspx** (búsqueda por apellido 'MONTEZUMA') — independiente de la agenda asignada al usuario.

---
*Dossier generado por QA UAT Agent v3 | Run ID: 20260508-qa119-v3-053352*