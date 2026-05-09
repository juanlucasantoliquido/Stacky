# DOSSIER_UAT — ADO-116 (Run 002: P08 / CA-08)

**Run ID:** uat-116-20260508-002
**Fecha:** 2026-05-08
**Veredicto global:** FAIL
**Alcance:** P08 (CA-08) — Visibilidad contador para usuario no-Pacifico
**Usuario primario:** PABLO (PEEMPRESA=0001 — NO es instancia Pacifico)
**Login attempts:** 1 | **Browser launches:** 1 | **Modo:** dry-run

---

## Resumen ejecutivo

Se detecta un **defecto real en CA-08**. El contador "Promesas a Vencer en 7 dias"
es visible para el usuario PABLO, quien NO pertenece a la instancia Pacifico
(PEEMPRESA=0001, sin vinculo a 0010).

El run anterior (uat-116-20260508-001) con PACIFICO mostro P05 y P09 como PASS.

---

## Hallazgos de datos (pre-ejecucion)

| Item | Estado | Detalle |
|---|---|---|
| Agenda Web | RUNNING | HTTP 200 en FrmLogin.aspx |
| PABLO es Pacifico | NO | PEEMPRESA: 0001,0002,0003,0004,0005,0006,9999 — no incluye 0010 |
| RIDIOMA 9302 | PRESENT | ESP+ENG+POR |
| Promesas ventana [20260508,20260514] | 0 | Sin datos insertados |
| Playwright | v1.59.1 | Instalado |

---

## P08 — CA-08 — FAIL

- **Oracle esperado:** counter_visible === false
- **Oracle real:** counter_visible === **true** (FALLA)
- **Duracion:** 13.4s
- **URL real:** http://localhost:35017/AgendaWeb/FrmAgenda.aspx

### Root cause

En AISMenu.cs, el bloque de render usa condicion if (!EsJudicial).
No hay llamada a EsInstanciaPacifico() en el render. El metodo no existe
en AISMenu.cs. El contador se muestra para TODOS los usuarios no-judiciales.

### barraResumen HTML de PABLO (evidencia)

`html
... <div class="etiqueta">Promesas a Vencer en 7 dias:</div><div class="valor">0</div> ...
`

### Fix recomendado para Developer

Cambiar en AISMenu.cs, seccion render (~L593):

`csharp
// ANTES (buggy):
if (!EsJudicial)
{
    // render Promesas a Vencer 7

// DESPUES (correcto):
if (!EsJudicial && EsInstanciaPacifico(usuario.CodUsuario))
{
    // render Promesas a Vencer 7
`

E implementar EsInstanciaPacifico():
`csharp
private bool EsInstanciaPacifico(string codUsuario)
{
    // SELECT con JOIN RUSUPERF + RPERFEMP WHERE PEEMPRESA='0010'
}
`

---

## Estado completo de escenarios

| ID | CA | Run | Resultado | Motivo |
|---|---|---|---|---|
| P01 | CA-01 | 001 | BLOCKED | TEST_DATA_EXPIRED |
| P02 | CA-02 | 001 | BLOCKED | TEST_DATA_MISSING |
| P03 | CA-03 | 001 | BLOCKED | TEST_DATA_MISSING |
| P04 | CA-04 | 001 | BLOCKED | TEST_DATA_MISSING |
| P05 | CA-05 | 001 | **PASS** | Counter=0 visible para PACIFICO |
| P06 | CA-06 | 001 | BLOCKED | TEST_DATA_MISSING |
| P07 | CA-07 | 001 | BLOCKED | TEST_DATA_AMBIGUOUS |
| P08 | CA-08 | **002** | **FAIL** | Counter visible para PABLO (no-Pacifico) |
| P09 | CA-09 | 001 | **PASS** | Recalculo consistente |
| P10 | CA-10 | 001 | BLOCKED | TEST_DATA_INSUFFICIENT |

---

## Archivos de evidencia

`
evidence/116/
├── effective_config.json
├── ado_comment.html       <- HTML con screenshots embebidos (162 KB)
├── DOSSIER_UAT.md
├── build_html.py
└── P08/
    ├── assertions_P08.json
    ├── barraResumen.html
    ├── P08-01-initial.png
    ├── P08-02-counter-check.png
    ├── runner_raw.txt
    └── test-failed-1.png
`

---

## Proximo paso humano

1. **Developer:** Corregir AISMenu.cs — agregar EsInstanciaPacifico() en el render del contador.
2. **Admin BD:** Insertar RCPAGO con CPFECVEN en [2026-05-08, 2026-05-14] para PACIFICO/PABLO6.
3. **QA:** Re-ejecutar P08 post-fix + P01-P04, P06, P07, P10 post-datos.
4. **NO** mover estado ADO — el humano decide.
