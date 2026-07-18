# Plan 194 — Portapapeles y exportación universal: "Copiar como…" (servicio central, formateadores puros y ratchet)

**Estado:** CRITICADO v2 (v1 → v2 aplicada; veredicto v1: APROBADO-CON-CAMBIOS)
**Autor:** StackyArchitectaUltraEficientCode (v1 propuesta; v2 por juez adversarial, perfil normal, heredado de Fable 5)
**Tema:** UX/UI — brief del operador: innovador, eficiente, extrema calidad, usable al instante, onboarding casi nulo, ganancia robusta.
**Audiencia:** implementador con modelo menor (Haiku / Codex / Copilot). Este documento NO deja nada a inferir: rutas, símbolos, strings, regex, baseline y comandos son EXACTOS. Toda ancla `archivo:línea` fue verificada contra el checkout el 2026-07-18 (y re-verificada por el juez v2 el mismo día: grep del ratchet reproducido = 14 matches / 13 archivos); si la sesión paralela corrió las líneas, mandan las anclas POR TEXTO que acompañan a cada `:línea`.

---

## CHANGELOG v1 → v2 (crítica adversarial aplicada)

| C# | Sev. | Qué estaba mal en v1 | Fix integrado en v2 |
|----|------|----------------------|---------------------|
| C1 | IMPORTANTE | El fallback textarea+`execCommand` roba el foco (`ta.select()`) y destruye la selección del usuario — y en el deploy LAN típico de Stacky (`http://IP:puerto`, contexto NO seguro, `navigator.clipboard` undefined) el fallback es el camino PRINCIPAL, no un edge case | §4.9 nueva (decisión fijada) + pseudocódigo F1 guarda/restaura `activeElement` y los ranges de `getSelection()` de forma defensiva + caso de test 11 + R1 ampliado |
| C2 | IMPORTANTE | F0 decía "importarlos como ya lo hace el propio archivo de tests para `_CURATED_DEFAULTS_ON`" — FALSO: `_CURATED_DEFAULTS_ON` se DEFINE en `test_harness_flags.py:467`, no se importa; y el snippet del test no mostraba imports (un modelo menor escribiría `from services.harness_flags import _CURATED_DEFAULTS_ON` → ImportError) | Test F0 reescrito COMPLETO como espejo textual del patrón real `test_cost_center_flag_registered_default_on` (`test_harness_flags.py:944-952`): imports dentro de la función, `categorize()` + `by_key`, y prosa corregida |
| C3 | IMPORTANTE | Truncado a 1000 filas potencialmente silencioso: `Math.min(items.length, 1000)` en el toast diría "1000 filas" sin declarar que faltan (mentira de datos si un plan futuro — p. ej. 173 — sube el límite de la tabla) | Nuevo export puro `copiedRowsLabel(total)` con strings fijados: `"N filas"` o `"1000 de N filas; límite de copia"` + test F2 caso 20 + §4.3/§4.7 actualizadas + F4.b lo usa |
| C4 | IMPORTANTE | "headers espejo de las 10 columnas visibles" era FALSO: la tabla visible (`ExecutionHistoryPage.tsx:170-179`) tiene columna **Prompt** (renderiza `prompt_sha.slice(0,7)`, `:197-201`) y NO tiene columna id; el export mete `id` y omite `prompt` | Justificación reescrita como DECISIÓN deliberada (id = trazabilidad; prompt_sha = hash sin valor en export), con cita a `:197-201`. La palabra "espejo" eliminada |
| C5 | MENOR | Fechas ISO crudas en plantillas/mdRows mientras duración/costo van formateados — decisión no declarada (un modelo menor podría "arreglarla" con formatDate) | §4.10 nueva: fechas SIEMPRE ISO crudo en exports, deliberado (sin pérdida, ordenable, universal); `formatDate*` de la casa es para UI, PROHIBIDO en copyFormats |
| C6 | MENOR | Posición del `CopyAsButton` en el header del drawer ambigua ("después del subtitle y ANTES del closeButton" cruza niveles de anidado: subtitle está DENTRO del `<div>`, closeButton FUERA) | F4.a fija: ÚLTIMO hijo del `<div>` que envuelve `<h3>` + subtitle (`ExecutionDetailDrawer.tsx:70-77`) |
| C7 | MENOR | `t.ado_url ?? adoUrl(...)` puede fabricar una URL ADO falsa para un ticket de un proyecto con tracker GitLab sin `ado_url` sincronizada | §4.6 declara el riesgo y la razón de mantener el fallback (coherencia exacta con `linkifyCitations`, que ya hace esto hoy — `trackerUrls.ts:1-8`) |
| C8 | MENOR | K3 contaba hits crudos de grep (imports + usos + definición ≈ 6-7 hits) — binariedad floja | K3 reformulado: la salida del grep debe listar los 3 archivos nombrados |
| C9 | MENOR | El mensaje del ratchet en F5 estaba escrito con comillas tipográficas (“ ”) — un copy-paste literal mete comillas curvas en el código | Mensaje reescrito con comillas rectas en bloque de código |
| [ADICIÓN ARQUITECTO] | ALTO VALOR | — | `copyRichText(html, plain)` + `rowsToHtmlTable`/`htmlEscapeCell` + opción **"Tabla (ADO)"** en el piloto de historial: al pegar en un comentario/descripción de work item ADO (o Word/Outlook/Teams) aparece una TABLA REAL renderizada, no pipes Markdown. Degradación honesta a texto plano cuando `ClipboardItem` no está (contexto no-seguro), con toast que lo declara. Se descartó la alternativa "atajo de teclado directo": agregaría una 4ª fuente de atajos divergente que el plan 172 (teclado primero, NO implementado) tendría que desmontar — anti-arquitectura. Ver §4.11, F1 casos 12-14, F2 casos 17-19, F4.b, smoke §10.3.7, R10 |

Verificación de anclas por el juez v2 (muestreo completo): regex del ratchet reproducida → **14 matches / 13 archivos** hoy (incluye las 2 llamadas partidas: la línea de continuación `.writeText(x)` matchea sola, sin multiline); baseline post-F4 = 12/11 correcto. `costCenter.logic.ts:60-82`, `trackerUrls.ts:10`, `types.ts:87-110/:121-145`, `incidentModel.ts:34-47`, `endpoints.ts:703-715/:909-910/:1212-1233/:1267`, `Toast.tsx:9-17`, `ui/Button.tsx:5-6`, `ui/index.ts:7-8`, `harness_flags.py:117/:326-333/:334/:1615-1624/:3378/:3380-3382`, `config.py:543-553`, `test_harness_flags.py:467/:744-759/:944-952`, `formatDebtRatchet.test.ts:6-124`, `run_harness_tests.ps1:15`, los 4 usos de `queryKey: ["harness-flags"]`, `services/__tests__/` (existe con activeRuns/notifierCore/reviewInbox/theme + density): TODAS verificadas OK.

---

## 0. Resumen ejecutivo

Hoy el frontend tiene **14 llamadas directas a `navigator.clipboard.writeText` repartidas en 13 archivos**, cada una con su propio try/catch y su propio feedback (o ninguno). El único CSV del sistema vive encerrado en el Centro de Costos (`lib/costCenter.logic.ts:72 toCsv(rows: TopRun[])`, específico de `TopRun` y usado para DESCARGA por Blob, no para portapapeles). No existe "copiar entidad como Markdown" ni "tabla → CSV/Markdown" genérico.

Este plan instala:

1. **`frontend/src/services/copyService.ts`** — `copyText(text): Promise<CopyResult>` con fallback documentado (`navigator.clipboard` → textarea+`execCommand` con preservación de foco y selección, §4.9) + `copyRichText(html, plain)` para copia enriquecida `text/html` (§4.11) y contrato de feedback ÚNICO (strings exactos fijados en §4.3).
2. **`frontend/src/services/copyFormats.ts`** — formateadores 100 % PUROS: `ticketToMarkdown`, `executionToMarkdown`, `executionToPlainText`, `incidentToMarkdown`, `rowsToCsv`, `rowsToMarkdownTable`, `rowsToHtmlTable`, `csvEscapeCell`, `mdEscapeCell`, `htmlEscapeCell`, `executionHistoryToRows`, `copiedRowsLabel` (escapado CSV correcto: comillas, comas, saltos de línea; CRLF; sin BOM — decisiones fijadas en §4.1).
3. **`frontend/src/components/CopyAsButton.tsx`** — grupo de botones inline (SIN popover, SIN dropdown) "Copiar: Markdown | CSV | …" con primitivas del barrel `ui/` y el Toast de la casa.
4. **Adopción piloto en 3 superficies reales:** ExecutionDetailDrawer (entidad → Markdown/Texto), ExecutionHistoryPage (tabla → CSV/Markdown/Tabla-ADO) y migración del `writeText` de mayor uso (StructuredOutput.tsx, el botón de copiar presente en cada sección de cada output estructurado).
5. **Ratchet suave `copyDebtRatchet`** (patrón `formatDebtRatchet.test.ts`): congela los `.writeText(` directos fuera de `copyService.ts` — el número solo puede bajar. Baseline post-plan: **12 sitios en 11 archivos** (§8 F5, tabla exacta; conteo pre-plan re-verificado: 14/13).

Flag: `STACKY_COPY_EXPORT_ENABLED`, bool, **default ON**, patrón triple verificado (§6 F0). Copiar es read-only: jamás muta datos, jamás llama a un runtime, jamás toca el backend (salvo el registro de la flag).

---

## 1. KPIs binarios

| # | KPI | Medición (comando exacto) | Criterio binario |
|---|-----|---------------------------|------------------|
| K1 | Flag registrada por patrón triple | `& "N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe" -m pytest tests/test_harness_flags.py -q` desde `Stacky Agents/backend` | Verde (relativo a HEAD, §5.G3) |
| K2 | Sitios directos de `.writeText(` en `frontend/src` (excl. allowlist §8 F5) | `npx vitest run src/__tests__/copyDebtRatchet.test.ts` desde `Stacky Agents/frontend` | Baseline = **12** sitios / **11** archivos (era 14/13); test verde |
| K3 | Superficies con "Copiar como…" | `grep -rln "CopyAsButton" "Stacky Agents/frontend/src" --include=*.tsx` | La salida lista, como mínimo, estos 3 archivos: `components/CopyAsButton.tsx`, `components/ExecutionDetailDrawer.tsx`, `pages/ExecutionHistoryPage.tsx` |
| K4 | Formateadores puros testeados | `npx vitest run src/services/__tests__/copyFormats.test.ts` | Verde; los **12** exports públicos de §6 F2 cubiertos |
| K5 | Servicio con fallback + rich testeado | `npx vitest run src/services/__tests__/copyService.test.ts` | Verde; **14/14** casos de §6 F1 |
| K6 | Cero deuda nueva de estilo/formato/formulario | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` + `formatDebtRatchet` + `formDebtRatchet` | Sin entradas NUEVAS atribuibles a archivos de este plan (criterio relativo a HEAD, §5.G3) |
| K7 | TypeScript limpio | `npx tsc --noEmit` desde `Stacky Agents/frontend` | Exit 0 |
| K8 | Flag OFF oculta superficies nuevas | Smoke manual §10.3 | Documentado en el PR (gap RTL/jsdom, §5.G4) |

---

## 2. Evidencia del gap (inventario verificado 2026-07-18; re-verificado por el juez v2 el mismo día)

### 2.1 Los 14 sitios ad-hoc de `navigator.clipboard.writeText` (13 archivos)

Grep ejecutado: patrón `\.writeText\s*\(` sobre `frontend/src` → 14 matches / 13 archivos (se listan SOLO archivos de producción; `RemediationCard.test.tsx` mockea `writeText` — 3 hits del patrón pelado `writeText` sin punto+paréntesis: `writeText = vi.fn()`, `{ writeText }`, `expect(writeText)` — y queda fuera del conteo del ratchet; `incidents/incidentModel.ts` es paste de imágenes del plan 160 — clipboard de LECTURA — y NO forma parte de este inventario).

| # | Archivo | Línea | Forma |
|---|---------|-------|-------|
| 1 | `components/ChatDrawer.tsx` | 361 | `try { await navigator.clipboard.writeText(text); } catch { /* noop */ }` |
| 2 | `components/ChatDrawer.tsx` | 401 | `.then()` con feedback propio |
| 3 | `components/CodeIntegrityCard.tsx` | 53-54 | `navigator.clipboard` y `.writeText(copyText)` PARTIDOS en 2 líneas |
| 4 | `pages/PlansBoardPage.tsx` | 88-89 | ídem, partido en 2 líneas |
| 5 | `components/DailyStandupModal.tsx` | 59 | `await` + estado local |
| 6 | `components/ExecutionDetailDrawer.tsx` | 143 | `void navigator.clipboard.writeText(absolutePath)` sin feedback |
| 7 | `components/devops/DirTreePreview.tsx` | 136 | `void` + guard `canCopy` propio (:123) |
| 8 | `components/HarnessFlagsPanel.tsx` | 273 | `navigator.clipboard?.writeText(flag.key)` optional-chain |
| 9 | `components/dbcompare/SqlViewer.tsx` | 50 | `?.writeText(text).catch(() => {})` |
| 10 | `components/dbcompare/SummaryHero.tsx` | 57 | `void navigator.clipboard?.writeText(...)` |
| 11 | `components/devops/RemediationCard.tsx` | 26 | `void navigator.clipboard?.writeText(action.command ?? '')` |
| 12 | `components/MermaidDiagram.tsx` | 81 | inline en onClick |
| 13 | `components/QaBrowserRunModal.tsx` | 50 | `await` + estado local |
| 14 | `components/StructuredOutput.tsx` | 231 | `CopyButton` local (:226-244) con estado `copied` 1500 ms |

**Nota sobre las llamadas partidas (verificado por el juez):** en los sitios 3 y 4 la línea de continuación (`.writeText(copyText)` / `.writeText(text)`) contiene punto + `writeText` + paréntesis en la MISMA línea, así que la regex del ratchet las captura SIN flag multiline. No hay hoy ningún `.writeText(` que no sea de clipboard (streams, etc.) en `frontend/src`.

**Consecuencia:** 14 contratos de error distintos (noop silencioso, catch vacío, optional-chain, estado local) y CERO feedback consistente. El sitio 6 ni siquiera avisa que copió.

### 2.2 El CSV existente está encerrado

- `lib/costCenter.logic.ts:60-82` — `CSV_HEADER` hardcodeado de `TopRun`, `csvEscape` privado (cita `/["\n,]/`, sin `\r`), `toCsv(rows: TopRun[])` específico de esa entidad, filas unidas con `\n` (LF).
- `components/costcenter/CostTable.tsx:18-21` — usa `toCsv` para DESCARGA vía Blob ("Export CSV 100% client-side"), no portapapeles. **Este plan NO toca ninguno de los dos archivos** (§9): reusa el PATRÓN de escapado (comillas dobladas, quote-si-matchea) generalizándolo en `copyFormats.ts`.

### 2.3 Lo que no existe

- Ningún `copyService`/`clipboard` service en `frontend/src/services/` (verificado por listado: `avatarGallery, preferences, uiSections, activeRuns, notifierCore, tabTitle, reviewInbox, executionNotifier, uiGuards, briefDraft, theme, themeController, agentLaunch, format` — ninguno de portapapeles).
- Ningún "copiar entidad como Markdown": `ticketToMarkdown`/`executionToMarkdown`/`incidentToMarkdown` dan 0 hits en `frontend/src`.
- Ningún "tabla → CSV/Markdown" genérico (`rowsToCsv`/`rowsToMarkdownTable` dan 0 hits).

---

## 3. Principios y guardarraíles (NO negociables, codificados acá)

1. **Human-in-the-loop intacto.** Copiar es una acción explícita del operador (click), 100 % read-only: no muta tickets, ejecuciones, incidencias ni config; no dispara agentes; no publica nada. No hay auto-copia ni copia proactiva.
2. **Cero trabajo extra para el operador.** Flag default ON; la feature es invisible hasta que el operador clickea; no usarla deja todo como hoy. Sin migraciones, sin config nueva, sin pasos manuales. **Ninguna de las 4 excepciones duras aplica, revisadas 1×1** (mismas 4 del plan 187 §3.2): (1) *bypass de revisión humana* — NO: copiar no ejecuta ni aprueba nada; (2) *destructiva/irreversible* — NO: solo escribe en el portapapeles del SO, que el operador pisa con su próximo Ctrl+C; (3) *prerequisito no garantizado* — NO: `navigator.clipboard` existe en todo Chromium/Firefox moderno y el fallback `execCommand` cubre contextos no-seguros; no requiere binarios, red ni servicios; (4) *reduce seguridad* — NO: no expone datos nuevos (copia lo que la pantalla ya muestra) y OFF ⇒ idéntico a hoy.
3. **Paridad de 3 runtimes: N/A-por-diseño.** Feature 100 % frontend (+1 flag backend de arnés). No toca el camino de ejecución/publicación de ningún runtime (claude_code_cli / codex_cli / github_copilot). Cada fase lo declara con 1 línea.
4. **Mono-operador sin auth.** Sin RBAC, sin `user_id`, sin permisos: `current_user` es un header sin validar y acá ni se lee.
5. **Backward-compatible.** Los 12 `writeText` NO migrados siguen funcionando byte-idéntico; el ratchet solo CONGELA (prohíbe crecer), no obliga a migrar. Las 2 migraciones de F4 conservan el feedback visible preexistente de cada superficie (§4.4).
6. **La flag gobierna SOLO las superficies nuevas.** `STACKY_COPY_EXPORT_ENABLED` controla el render de `CopyAsButton` (las superficies que este plan AGREGA). Las migraciones internas de mecanismo (F4.a parcial y F4.c) NO se gatean: con flag OFF el operador ve EXACTAMENTE los mismos botones que hoy, funcionando igual. `copyService.ts`/`copyFormats.ts` son infraestructura sin flag, como `services/format.ts`.
7. **Gotcha prosa-vs-gate (declarado).** El ratchet de F5 cuenta `.writeText(` SOLO bajo `frontend/src` (`SRC = path.join(process.cwd(), "src")`, patrón `formatDebtRatchet.test.ts:17-18`); este documento vive en `docs/`, fuera del scanner, y el propio test se auto-excluye por ALLOWLIST (§8 F5). Los mensajes de error del ratchet NO deben contener la secuencia punto+writeText+paréntesis (usar la frase "usa copyText de services/copyService" — sin paréntesis tras writeText).

---

## 4. Decisiones de diseño FIJADAS (el implementador no decide nada)

### 4.1 CSV (fijado)

- **Separador:** coma (`,`).
- **Fin de fila:** **CRLF** (`\r\n`). Razón: pegado en Excel/Windows (el operador es Windows-only; LF a secas confunde a Excel viejo al pegar multilínea). El `toCsv` legado del Centro de Costos usa LF y NO se toca (contrato aparte, descarga).
- **BOM UTF-8: NO.** Razón: el BOM sirve para ARCHIVOS que Excel abre desde disco (ahí sí corrige acentos); en el portapapeles el SO transporta texto Unicode nativo (`CF_UNICODETEXT` en Windows) y un BOM pegado aparece como carácter basura en editores. El caso de uso de este plan es PEGAR, no abrir archivos. Decisión CERRADA y cableada por test (F2 caso 10): `rowsToCsv` NUNCA antepone `﻿`. **Nota al implementador con modelo menor: NO "arreglar" esto agregando BOM aunque otra fuente lo sugiera — el test lo prohíbe a propósito.**
- **Escapado (superset del patrón `costCenter.logic.ts:64-70`):** una celda se encierra en comillas dobles si matchea `/["\r\n,]/` (nota: agrega `\r` que el legado no contempla); las comillas internas se duplican (`"` → `""`). `null`/`undefined` → celda vacía. Números y booleanos → `String(v)`.
- **Sin trailing newline** al final del string (última fila sin `\r\n` final).

### 4.2 Tabla Markdown (fijado)

- Fila de encabezado + fila separadora `| --- |` (un `---` por columna, exacto, sin alineación `:`).
- `mdEscapeCell`: `null`/`undefined` → `""`; pipes escapados (`|` → `\|`); TODO salto de línea (`\r\n`, `\r` o `\n`) → un espacio simple; sin trim adicional.
- Filas unidas con `\n` (LF: es Markdown para pegar en ADO/GitLab/editores, no CSV).

### 4.3 Contrato de feedback ÚNICO (strings EXACTOS, congelados como constantes exportadas)

- `COPY_TOAST_SUCCESS = "Copiado al portapapeles."` → `ToastState { variant: "success", body: COPY_TOAST_SUCCESS }` (sin `title`).
- `COPY_TOAST_ERROR = "No se pudo copiar al portapapeles."` → `ToastState { variant: "error", body: COPY_TOAST_ERROR }` (sin `title`).
- Tablas (éxito, body override por opción), usando `copiedRowsLabel` (§6 F2, anti-truncado-silencioso C3):
  - CSV: `` `Tabla copiada como CSV (${copiedRowsLabel(items.length)}).` ``
  - Markdown: `` `Tabla copiada como Markdown (${copiedRowsLabel(items.length)}).` ``
  - Tabla (ADO), copia enriquecida OK: `` `Tabla copiada para ADO (${copiedRowsLabel(items.length)}).` ``
  - Tabla (ADO), degradada a texto: `` `Tabla copiada como Markdown (${copiedRowsLabel(items.length)}; sin copia enriquecida en este contexto).` ``
- `copiedRowsLabel(total)` devuelve `"N filas"` si `total <= 1000`, y `"1000 de N filas; límite de copia"` si `total > 1000` (con N = total). Así, si algún plan futuro sube el límite de la tabla, el truncado JAMÁS es silencioso.
- **Texto vacío ⇒ no-op declarado:** `copyText("")` devuelve `{ ok: false, reason: "empty" }` y el caller NO muestra toast (ni éxito ni error).
- El Toast es el de la casa: `components/Toast.tsx` (plan 135 F5; contrato `ToastState` en `Toast.tsx:11-17`, variantes `Toast.tsx:9`). Auto-cierre del éxito a los 4000 ms (timer limpiado al desmontar); el error persiste hasta el cierre manual (`onClose`).

### 4.4 Anti doble-feedback (fijado)

`CopyAsButton` es el ÚNICO dueño del Toast en las superficies nuevas. El servicio (`copyService.ts`) JAMÁS muestra toasts ni toca el DOM visible: devuelve `CopyResult` y el caller decide el feedback — por eso las superficies migradas pueden conservar el suyo sin doble canal. Las superficies MIGRADAS conservan su feedback preexistente y NO agregan Toast: StructuredOutput conserva su `✓` inline de 1500 ms (F4.c); el botón "Copiar ruta" del drawer hoy no da feedback y sigue sin darlo (F4.a, diff mínimo). Regla para futuras migraciones (fuera de scope): una superficie muestra UN solo canal de feedback.

### 4.5 Menú "Copiar como…" (fijado: botones inline, SIN popover)

El barrel `components/ui/index.ts` NO exporta Popover/Menu/Dialog (verificado; el diálogo canónico es plan 164, NO implementado — no depender). Decisión: `CopyAsButton` renderiza un **grupo inline**: prefijo de texto `Copiar:` + un `Button` del barrel por opción (`variant="ghost"`, `size="sm"` — valores válidos verificados en `ui/Button.tsx:5-6`: `"primary" | "secondary" | "ghost" | "danger"` y `"sm" | "md"`). Cero dropdown, cero estado de apertura, cero focus-trap.

### 4.6 Opción "Enlace" (fijado: solo entidades con URL real)

- **Ticket:** enlace = `t.ado_url ?? adoUrl(String(t.ado_id))` (`utils/trackerUrls.ts:10` exporta SOLO `adoUrl(adoId: string): string`; `Ticket.ado_url` existe en `types.ts:94`). `ticketToMarkdown` lo incluye (§6 F2).
  **Riesgo declarado (C7):** `adoUrl()` hardcodea la org/proyecto ADO (`trackerUrls.ts:11`); para un ticket de un proyecto con tracker GitLab SIN `ado_url` sincronizada, el fallback fabricaría una URL ADO inválida. Se ACEPTA porque (a) `ado_url` del backend SIEMPRE gana cuando existe, y (b) es EXACTAMENTE el mismo comportamiento que la linkificación de la casa (`linkifyCitations`, razón de ser de `trackerUrls.ts:1-8`) — coherencia > sofisticación. Unificarlo es problema del que unifique `trackerUrls`, no de este plan.
- **Ejecución: SIN opción Enlace en este plan.** No existe URL canónica por ejecución (el contrato URL/deep-links es el plan 165, CRITICADO v2, NO implementado). Nota de coexistencia §7.3.

### 4.7 Límite de filas (fijado)

Se copia SOLO lo que la tabla muestra (los `items` ya paginados; en ExecutionHistoryPage `filters.limit = 50` fijo, sin selector de límite en la UI — verificado `ExecutionHistoryPage.tsx:36-43` y :112-158). Guard defensivo adicional: `executionHistoryToRows` corta en **1000 filas** (`items.slice(0, 1000)`), con test. Con el límite estructural de 50 el truncado es inalcanzable HOY, pero si un plan futuro lo vuelve alcanzable, el aviso ya está cableado: TODO body de éxito de tabla usa `copiedRowsLabel` (§4.3), que declara "1000 de N filas; límite de copia" — el truncado silencioso queda PROHIBIDO por diseño (C3).

### 4.8 Dónde vive cada cosa (fijado)

- Servicio y formateadores: `frontend/src/services/` (convención existente: `format.ts`, `notifierCore.ts`). Tests en `frontend/src/services/__tests__/` (convención existente, verificada: `activeRuns.test.ts`, `density.test.ts`, `notifierCore.test.ts`, `reviewInbox.test.ts`, `theme.test.ts`).
- Componente: `frontend/src/components/CopyAsButton.tsx` + `CopyAsButton.module.css` (tokens `var(--…)` de theme.css; PROHIBIDO hex y `style={{}}` — uiDebtRatchet).
- Ratchet: `frontend/src/__tests__/copyDebtRatchet.test.ts` + `copyDebtBaseline.json` (convención existente: `formatDebtRatchet.test.ts` + `formatDebtBaseline.json`).

### 4.9 Foco y selección durante el fallback (fijado — C1)

**Contexto real de Stacky:** el deploy típico se sirve por `http://IP:puerto` en LAN — contexto NO seguro, donde `navigator.clipboard` es `undefined`. Ahí el fallback textarea+`execCommand` NO es un edge case: es el camino PRINCIPAL de copiado. Por eso sus efectos colaterales importan:

- `ta.select()` mueve el foco al textarea invisible; tras `removeChild`, el foco caería a `document.body` (el operador pierde dónde estaba — a11y rota).
- `ta.select()` además DESTRUYE la selección de texto que el operador tuviera en pantalla.

**Decisión fijada:** `copyText` guarda `document.activeElement` y los ranges de `getSelection()` ANTES de tocar el DOM, y los restaura DESPUÉS (foco con `.focus()`, selección con `removeAllRanges()` + `addRange()`), todo con guards defensivos (`typeof x === "function"`) para que:
1. jamás lance en navegadores raros, y
2. los stubs planos de los tests en node (G4) sigan funcionando sin definir `getSelection`/`activeElement`.

El pseudocódigo de F1 lo implementa tal cual; el caso de test 11 lo cubre.

### 4.10 Fechas en exports: SIEMPRE ISO crudo (fijado — C5)

En `copyFormats.ts` las fechas (`started_at`, `completed_at`, `created_at`) van SIEMPRE tal cual llegan del backend (ISO 8601), tanto en `csvRows` como en `mdRows` y plantillas. Razón deliberada: un export debe ser sin pérdida, ordenable lexicográficamente y universal (pegable en tickets, hojas de cálculo y scripts); los formateadores humanos de fecha de la casa (`formatDate*` de `services/format.ts`, `formatRelativeTime`) son para UI en vivo y quedan PROHIBIDOS dentro de `copyFormats.ts`. Duración y costo SÍ se formatean en los `mdRows`/plantillas (`formatDuration`/`formatCostUsd`) porque sus valores crudos (ms, floats) no son legibles y su formato es estable y sin locale. **Nota al implementador con modelo menor: NO "mejorar" las fechas con formatDate — es a propósito.**

### 4.11 Copia enriquecida "Tabla (ADO)" (fijado — [ADICIÓN ARQUITECTO])

Pegar Markdown en la descripción o comentarios de un work item de ADO muestra pipes crudos (el editor de ADO es HTML). La opción **"Tabla (ADO)"** copia el DOBLE formato al portapapeles vía `navigator.clipboard.write([ClipboardItem])`:
- `text/html`: `<table>` generada por `rowsToHtmlTable` (F2) — ADO/Word/Outlook/Teams pegan una tabla REAL renderizada.
- `text/plain`: la tabla Markdown (F2) — editores de texto plano pegan algo legible.

**Degradación fijada:** si `clipboard.write` o `ClipboardItem` no existen (contexto no-seguro LAN, browsers viejos) o la escritura falla, `copyRichText` degrada a `copyText(plain)` (Markdown), y el toast lo DECLARA con el string de §4.3 ("…sin copia enriquecida en este contexto"). Nunca miente sobre lo que quedó en el portapapeles. Target: Chromium en Windows (el navegador del operador); no se hace nada especial para Safari.

**Alternativa evaluada y DESCARTADA:** atajo de teclado de copiar contextual con listener directo. Razón del descarte: ya existen 3 fuentes de atajos divergentes en el frontend y el plan 172 (teclado primero, NO implementado) existe precisamente para unificarlas; agregar un 4º listener suelto sería anti-arquitectura y trabajo que el 172 tendría que desmontar. El copiado por atajo queda diferido al 172 (§9).

---

## 5. Gotchas del repo codificados (leer ANTES de implementar)

- **G1 — Intérprete backend:** el canónico es el `.venv` de la RAÍZ del repo (py3.13.5): `& "N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe" -m pytest tests/test_harness_flags.py -q` desde `Stacky Agents/backend`. **NO usar `backend/venv/`** (WIP ajeno py3.11, verificado 2026-07-18).
- **G2 — pytest SIEMPRE por archivo:** `test_harness_flags.py` hace `importlib.reload(config)` y contamina la suite completa.
- **G3 — Criterio RELATIVO a HEAD:** `test_harness_ratchet_meta.py` está ROJO preexistente en HEAD por drift ajeno; los ratchets frontend pueden tener rojos ajenos. El gate de este plan es: NINGÚN test que estaba verde en HEAD se pone rojo, y TODOS los tests nuevos de este plan quedan verdes. No se exige verde absoluto de archivos ajenos.
- **G4 — Frontend sin RTL/jsdom** (`@testing-library/react` y `jsdom` NO están en `package.json`): TODA la lógica (escapado, formateadores, resolución de flag, fallback de clipboard, copia rica) vive en módulos `.ts` PUROS con vitest POR ARCHIVO (`npx vitest run src/services/__tests__/<archivo>.test.ts` desde `Stacky Agents/frontend`); los `.tsx` son cáscaras finas verificadas con `npx tsc --noEmit` + smoke manual documentado. Vitest corre en node: los tests de `copyService` stubbean `navigator`, `document` y `ClipboardItem` con `vi.stubGlobal` (§6 F1) — jamás asumen DOM real.
- **G5 — Registro de tests backend:** este plan NO crea archivos de test backend nuevos (solo agrega un test al FINAL de `tests/test_harness_flags.py`, ya registrado en `backend/scripts/run_harness_tests.ps1:15` y su gemelo `run_harness_tests.sh`), por lo tanto NO toca `run_harness_tests.sh` ni `run_harness_tests.ps1`. El archivo acepta tests planos al final sin fixtures (patrón verificado: `test_cost_center_flag_registered_default_on`, `:944-952`).
- **G6 — `harness_defaults.env`:** PROHIBIDO editarlo a mano (lo genera `backend/scripts/export_harness_defaults.py`) y además está `M` (modificado) por la sesión paralela activa. Este plan NO lo toca; regenerarlo queda FUERA del DoD (drift preexistente documentado).
- **G7 — uiDebtRatchet:** los `.tsx` nuevos nacen con CERO `style={{}}` (todo por `CopyAsButton.module.css`; si hiciera falta un valor dinámico, `ref` + `element.style.setProperty` — en este plan NO hace falta). El `ta.style.cssText` del fallback vive en un `.ts` sin JSX: fuera del alcance del ratchet (que escanea atributos JSX `style={{`), declarado.
- **G8 — formDebtRatchet:** `CopyAsButton` usa `Button` del barrel `components/ui` (verificado `ui/index.ts:7-8`), cero `<button>` crudo nuevo.
- **G9 — formatDebtRatchet:** `copyFormats.ts` formatea duración/costo vía `formatDuration`/`formatCostUsd` de `services/format.ts` (importados hoy por el drawer en `ExecutionDetailDrawer.tsx:13`) — jamás `toFixed`/`toLocaleString` a mano. Fechas: ISO crudo (§4.10), sin formatter alguno.
- **G10 — Sesión paralela viva:** `IncidentResolverModal.tsx`, `harness_defaults.env` y otros están `M` en el working tree. Este plan no toca ninguno de esos archivos. Ante cualquier `:línea` corrida, mandan las anclas por texto.

---

## 6. Fases

### F0 — Flag `STACKY_COPY_EXPORT_ENABLED` (patrón triple + curado)

**Objetivo (1 frase):** registrar la flag bool default ON en las 4 patas verificadas del patrón, sin efecto funcional todavía.

**Runtimes:** N/A-por-diseño — flag de arnés leída solo por el frontend; ningún runner la evalúa.
**Trabajo del operador:** ninguno.

**Tests PRIMERO** — en `backend/tests/test_harness_flags.py` (archivo EXISTENTE, ya registrado — G5), agregar al final este test COMPLETO (espejo textual del patrón real `test_cost_center_flag_registered_default_on`, `test_harness_flags.py:944-952`: imports DENTRO de la función; `_CURATED_DEFAULTS_ON` es el set definido en el PROPIO archivo de tests en `:467` — NO se importa de ningún módulo):

```python
def test_copy_export_flag_registered():
    """Plan 194 F0 — STACKY_COPY_EXPORT_ENABLED: registrada, categorizada, default ON curado."""
    from services.harness_flags import FLAG_REGISTRY, categorize

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_COPY_EXPORT_ENABLED" in by_key
    assert by_key["STACKY_COPY_EXPORT_ENABLED"].type == "bool"
    assert by_key["STACKY_COPY_EXPORT_ENABLED"].default is True
    assert categorize("STACKY_COPY_EXPORT_ENABLED") == "interfaz_ui"
    assert "STACKY_COPY_EXPORT_ENABLED" in _CURATED_DEFAULTS_ON
```

(`categorize` existe en `harness_flags.py:3385-3387` y resuelve contra `_KEY_CATEGORY`, `:3380-3382`, construido desde `_CATEGORY_KEYS`; no hace falta importar símbolos privados.) Correr y ver ROJO (`assert "STACKY_COPY_EXPORT_ENABLED" in by_key` falla primero).

**Implementación (4 patas):**

1. `backend/services/harness_flags.py` — agregar al FINAL de la tupla `FLAG_REGISTRY` (abre en `:334`; insertar antes del `)` de cierre que precede a `_REGISTRY_INDEX`, `:3378`), copiando el patrón del entry de `STACKY_COST_CENTER_ENABLED` (`:1615-1624`):

```python
    FlagSpec(
        key="STACKY_COPY_EXPORT_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica: copiar es read-only; curada en _CURATED_DEFAULTS_ON)
        label="Copiar como… (portapapeles universal)",
        description=(
            "Plan 194 — Botones 'Copiar como' (Markdown/CSV/Texto/Tabla ADO) en drawers y tablas. "
            "Solo lectura: copiar nunca muta datos. Default ON; desactivable desde la UI."
        ),
        group="global",
    ),
```

2. `backend/services/harness_flags.py` — en `_CATEGORY_KEYS` (`:117`), agregar `"STACKY_COPY_EXPORT_ENABLED",  # Plan 194` a la tupla `"interfaz_ui"` (ancla por texto: la tupla que hoy contiene `"STACKY_UI_SHELL_V2_ENABLED"`, `:326-328`). NO crear categoría nueva. Nota: los planes 187/173/175 (no implementados) planean sumar sus keys a la MISMA tupla; si ya están, agregar la nuestra al final. (La nota de `:332-333` lo exige: flag sin categoría rompe `test_every_registry_flag_is_categorized`.)

3. `backend/config.py` — atributo en la clase Config, inmediatamente después del atributo `STACKY_COST_CODEBURN_IMPORT_PATH` (ancla por texto; hoy `:551-553`), patrón EXACTO de `STACKY_COST_CENTER_ENABLED` (`config.py:543-545`):

```python
    # ── Plan 194 — Portapapeles universal ("Copiar como…") ────────────────────
    # Read-only puro; default ON (ninguna de las 4 excepciones duras aplica).
    STACKY_COPY_EXPORT_ENABLED: bool = os.getenv(
        "STACKY_COPY_EXPORT_ENABLED", "true"
    ).strip().lower() == "true"
```

4. `backend/tests/test_harness_flags.py` — agregar `"STACKY_COPY_EXPORT_ENABLED",` al set `_CURATED_DEFAULTS_ON` (`:467`; el meta-assert `test_default_known_only_for_curated`, `:750-759`, exige igualdad exacta entre curadas y `default_known` — sin esta pata, ROJO).

**Criterio binario + comando:** desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:
`& "N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe" -m pytest tests/test_harness_flags.py -q` → verde (relativo a HEAD, G3).

---

### F1 — `copyService.ts`: copiar con fallback, foco preservado y copia rica (TDD)

**Objetivo (1 frase):** un único punto de escritura al portapapeles con resultado tipado, fallback para contextos no-seguros que NO rompe foco ni selección, copia enriquecida opcional y resolución pura de la flag.

**Runtimes:** N/A-por-diseño — módulo TypeScript de navegador, sin backend.
**Trabajo del operador:** ninguno.

**Archivos:** `frontend/src/services/copyService.ts` (nuevo), `frontend/src/services/__tests__/copyService.test.ts` (nuevo).

**Símbolos EXACTOS:**

```ts
export type CopySuccessMethod = "clipboard" | "execCommand" | "richClipboard";

export type CopyResult =
  | { ok: true; method: CopySuccessMethod }
  | { ok: false; reason: "empty" | "denied" | "unavailable" };

export const COPY_TOAST_SUCCESS = "Copiado al portapapeles.";
export const COPY_TOAST_ERROR = "No se pudo copiar al portapapeles.";

export async function copyText(text: string): Promise<CopyResult>;

/** §4.11 — doble formato text/html + text/plain; degrada a copyText(plain). */
export async function copyRichText(html: string, plain: string): Promise<CopyResult>;

export function resolveCopyExportEnabled(
  flags: ReadonlyArray<{ key: string; value: unknown }> | undefined,
): boolean;
```

**Semántica de `reason` (determinista, sin ambigüedad):**
- `"empty"`: el texto plano es `""` (no se toca ningún mecanismo; en `copyRichText` manda el `plain`).
- `"unavailable"`: no existe `navigator.clipboard.writeText` NI un `document.execCommand` utilizable (p. ej. entorno node de tests sin stubs).
- `"denied"`: existía al menos un mecanismo pero todos fallaron (writeText rechazó y/o execCommand devolvió false o lanzó).

**Pseudocódigo de `copyText` (implementar tal cual; incluye §4.9):**

```ts
export async function copyText(text: string): Promise<CopyResult> {
  if (text === "") return { ok: false, reason: "empty" };
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  const hasAsync = typeof nav?.clipboard?.writeText === "function";
  if (hasAsync) {
    try {
      await nav!.clipboard.writeText(text);
      return { ok: true, method: "clipboard" };
    } catch {
      /* permiso denegado o contexto no-seguro: cae al fallback */
    }
  }
  const doc = typeof document !== "undefined" ? document : undefined;
  if (!doc || typeof doc.execCommand !== "function") {
    return { ok: false, reason: hasAsync ? "denied" : "unavailable" };
  }
  try {
    // §4.9 — foto del foco y la selección ANTES de tocar el DOM (guards defensivos: los
    // stubs planos de los tests no definen activeElement/getSelection y NO deben romper).
    const prevActive = (doc.activeElement ?? null) as { focus?: () => void } | null;
    const sel = typeof doc.getSelection === "function" ? doc.getSelection() : null;
    const prevRanges: Range[] = [];
    if (sel && typeof sel.rangeCount === "number" && typeof sel.getRangeAt === "function") {
      for (let i = 0; i < sel.rangeCount; i++) prevRanges.push(sel.getRangeAt(i));
    }

    const ta = doc.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.setAttribute("aria-hidden", "true");
    ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0;"; // .ts imperativo, no JSX (G7)
    doc.body.appendChild(ta);
    ta.select();
    const ok = doc.execCommand("copy");
    doc.body.removeChild(ta);

    // §4.9 — restaurar selección y foco (mismo orden: primero ranges, después foco).
    if (sel && typeof sel.removeAllRanges === "function" && prevRanges.length > 0) {
      sel.removeAllRanges();
      for (const r of prevRanges) sel.addRange(r);
    }
    if (prevActive && typeof prevActive.focus === "function") prevActive.focus();

    return ok ? { ok: true, method: "execCommand" } : { ok: false, reason: "denied" };
  } catch {
    return { ok: false, reason: "denied" };
  }
}
```

(`document.execCommand` está deprecado pero es EXACTAMENTE el fallback documentado para contextos no-seguros — `http://IP:puerto` en LAN, el deploy típico de Stacky, donde `navigator.clipboard` NO existe y este camino es el PRINCIPAL (§4.9) — envuelto en try/catch, solo se ejecuta si el camino moderno no está o falló.)

**Pseudocódigo de `copyRichText` (implementar tal cual; §4.11):**

```ts
export async function copyRichText(html: string, plain: string): Promise<CopyResult> {
  if (plain === "") return { ok: false, reason: "empty" };
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  const canRich =
    typeof nav?.clipboard?.write === "function" && typeof ClipboardItem !== "undefined";
  if (canRich) {
    try {
      const item = new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      });
      await nav!.clipboard.write([item]);
      return { ok: true, method: "richClipboard" };
    } catch {
      /* degrada a texto plano */
    }
  }
  return copyText(plain);
}
```

**Pseudocódigo de `resolveCopyExportEnabled` (implementar tal cual):**

```ts
export function resolveCopyExportEnabled(
  flags: ReadonlyArray<{ key: string; value: unknown }> | undefined,
): boolean {
  if (!flags) return true;                                        // fail-open: sin datos aún ⇒ ON (anti-flash)
  const f = flags.find((x) => x.key === "STACKY_COPY_EXPORT_ENABLED");
  if (!f) return true;                                            // flag desconocida por el backend ⇒ ON
  return f.value === true;                                        // SOLO false explícito apaga
}
```

(Compatible estructuralmente con `HarnessFlagView` — `endpoints.ts:703-715`: `key: string; value: boolean | number | string`.)

**Tests PRIMERO** (`src/services/__tests__/copyService.test.ts`) — casos enumerados; stubs con `vi.stubGlobal` (G4, sin jsdom):

1. `copyText("")` → `{ ok: false, reason: "empty" }` y el stub de `writeText` NO fue llamado.
2. `writeText` resuelve → `{ ok: true, method: "clipboard" }` con el texto exacto pasado.
3. `writeText` rechaza + `document.execCommand` stub devuelve `true` → `{ ok: true, method: "execCommand" }` y el textarea fue agregado y removido del `body` (asserts sobre los stubs `appendChild`/`removeChild`).
4. `writeText` rechaza + `execCommand` devuelve `false` → `{ ok: false, reason: "denied" }`.
5. Sin `navigator` NI `document` (stubs a `undefined`) → `{ ok: false, reason: "unavailable" }`.
6. `resolveCopyExportEnabled(undefined)` → `true`.
7. `resolveCopyExportEnabled([])` (flag ausente) → `true`.
8. `resolveCopyExportEnabled([{ key: "STACKY_COPY_EXPORT_ENABLED", value: false }])` → `false`.
9. `resolveCopyExportEnabled([{ key: "STACKY_COPY_EXPORT_ENABLED", value: true }])` → `true`.
10. `resolveCopyExportEnabled([{ key: "STACKY_COPY_EXPORT_ENABLED", value: "true" }])` → `false` (solo boolean true enciende; el backend entrega bool para type="bool").
11. **(C1)** fallback exitoso con `document.activeElement = { focus: vi.fn() }` y sin `getSelection` en el stub → `focus` fue llamado exactamente 1 vez tras el copy (restauración de foco) y nada lanzó pese a faltar `getSelection` (guard defensivo).
12. **(§4.11)** stubs `navigator.clipboard.write` que resuelve + `ClipboardItem` clase stub → `copyRichText("<b>x</b>", "x")` → `{ ok: true, method: "richClipboard" }` y el constructor del stub recibió un objeto con claves `"text/html"` y `"text/plain"`.
13. **(§4.11)** sin `clipboard.write` (solo `writeText` que resuelve) → `copyRichText("<b>x</b>", "x")` → `{ ok: true, method: "clipboard" }` y `writeText` recibió `"x"` (el PLAIN, no el html).
14. **(§4.11)** `copyRichText("<b>x</b>", "")` → `{ ok: false, reason: "empty" }` (manda el plain).

Stub mínimo de `document` para los casos 3-4 (objeto plano): `createElement` devuelve `{ value: "", setAttribute: vi.fn(), select: vi.fn(), style: {} }`; `body: { appendChild: vi.fn(), removeChild: vi.fn() }`; `execCommand: vi.fn(() => true/false)`. Para el caso 11 se agrega `activeElement: { focus: vi.fn() }` al mismo stub. Para 12-14, `vi.stubGlobal("ClipboardItem", class { constructor(public parts: Record<string, unknown>) { spy(parts); } })` (o equivalente con `vi.fn()`); `Blob` existe nativo en node ≥ 18, no se stubbea. Restaurar stubs en `afterEach` con `vi.unstubAllGlobals()`.

**Criterio binario + comando:** `npx vitest run src/services/__tests__/copyService.test.ts` desde `Stacky Agents/frontend` → verde (14/14).

---

### F2 — `copyFormats.ts`: formateadores puros (TDD)

**Objetivo (1 frase):** funciones puras y testeadas que convierten entidades reales y tablas a Markdown/CSV/HTML/Texto con escapado correcto.

**Runtimes:** N/A-por-diseño — funciones puras de presentación en el navegador.
**Trabajo del operador:** ninguno.

**Archivos:** `frontend/src/services/copyFormats.ts` (nuevo), `frontend/src/services/__tests__/copyFormats.test.ts` (nuevo).

**Imports permitidos (todos verificados):** `type Ticket` y `type AgentExecution` de `../types` (`types.ts:87-110` y `:121-145`), `type IncidentDTO` de `../incidents/incidentModel` (`incidentModel.ts:34-47`), `type ExecutionHistoryItem` de `../api/endpoints` (`endpoints.ts:1212-1233`), `adoUrl` de `../utils/trackerUrls` (`trackerUrls.ts:10` — ÚNICO export), `formatDuration, formatCostUsd` de `./format` (G9).

**Símbolos EXACTOS (12 exports):**

```ts
export type CellValue = string | number | boolean | null | undefined;

export function csvEscapeCell(v: CellValue): string;
export function rowsToCsv(headers: string[], rows: CellValue[][]): string;        // §4.1: coma, CRLF, sin BOM
export function mdEscapeCell(v: CellValue): string;                               // §4.2
export function rowsToMarkdownTable(headers: string[], rows: CellValue[][]): string;
export function htmlEscapeCell(v: CellValue): string;                             // §4.11
export function rowsToHtmlTable(headers: string[], rows: CellValue[][]): string;  // §4.11
export function copiedRowsLabel(total: number): string;                           // §4.3 (C3)
export function ticketToMarkdown(t: Ticket): string;
export function executionToMarkdown(e: AgentExecution): string;
export function executionToPlainText(e: AgentExecution): string;
export function incidentToMarkdown(i: IncidentDTO): string;
export function executionHistoryToRows(items: ExecutionHistoryItem[]): {
  headers: string[];
  csvRows: CellValue[][];   // valores crudos máquina (ISO, números)
  mdRows: CellValue[][];    // valores formateados humanos (formatDuration/formatCostUsd; fechas ISO §4.10)
};
```

**Reglas exactas:**

- `csvEscapeCell`: `null | undefined` → `""`; si `String(v)` matchea `/["\r\n,]/` → envolver en `"` con `"` internas duplicadas; si no, `String(v)` tal cual.
- `rowsToCsv`: `[headers.map(csvEscapeCell).join(",")]` + una línea por fila; unir TODO con `"\r\n"`; sin `\r\n` final.
- `mdEscapeCell`: `null | undefined` → `""`; `String(v).replace(/\r\n|\r|\n/g, " ").replace(/\|/g, "\\|")`.
- `rowsToMarkdownTable`: `| h1 | h2 |` + `| --- | --- |` (tantos `---` como headers) + filas; celdas con `mdEscapeCell`; unir con `"\n"`.
- `htmlEscapeCell` (§4.11): `null | undefined` → `""`; sobre `String(v)`, en ESTE orden: `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`, `"` → `&quot;`. Sin tocar saltos de línea (el HTML los colapsa solo).
- `rowsToHtmlTable` (§4.11): UNA sola línea, sin estilos ni atributos (el destino — ADO/Word — aplica los suyos): `<table><thead><tr><th>…</th>…</tr></thead><tbody><tr><td>…</td>…</tr>…</tbody></table>`; celdas con `htmlEscapeCell`.
- `copiedRowsLabel(total)` (C3): `total <= 1000` → `` `${total} filas` `` (con `total === 1` → `"1 fila"`); `total > 1000` → `` `1000 de ${total} filas; límite de copia` ``.

**Plantillas EXACTAS (golden; `n/d` literal para ausentes; fechas ISO crudas §4.10):**

`ticketToMarkdown(t)`:

```
## [{t.work_item_type ?? "Ticket"} {t.ado_id}] {t.title}

- Estado ADO: {t.ado_state ?? "n/d"}
- Estado Stacky: {t.stacky_status ?? "n/d"}
- Prioridad: {t.priority ?? "n/d"}
- Asignado: {t.assigned_to_ado ?? "n/d"}
- Enlace: {t.ado_url ?? adoUrl(String(t.ado_id))}

{t.description ?? ""}
```

(Si `description` es undefined, el string termina tras la línea en blanco final del bloque de bullets, con `trimEnd()` aplicado al resultado completo. Riesgo del fallback `adoUrl` declarado en §4.6.)

`executionToMarkdown(e)` — tabla Markdown de 2 columnas construida con `rowsToMarkdownTable(["Campo", "Valor"], …)` precedida por el título:

```
## Ejecución #{e.id} — {e.agent_type}

| Campo | Valor |
| --- | --- |
| Estado | {e.status} |
| Ticket | #{e.ticket_id}{e.ticket_title ? " — " + e.ticket_title : ""} |
| Proyecto | {e.project ?? "n/d"} |
| Agente | {e.agent_filename ?? "n/d"} |
| Inicio | {e.started_at} |
| Fin | {e.completed_at ?? "n/d"} |
| Duración | {formatDuration(e.duration_ms ?? null)} |
| Veredicto | {e.verdict ?? "n/d"} |
| Error | {e.error_message ?? "—"} |
```

(Las celdas pasan por `mdEscapeCell` vía `rowsToMarkdownTable`; los campos citados existen en `types.ts:121-145`. La celda Error usa `—` y no `n/d` a propósito: "sin error" no es un dato faltante.)

`executionToPlainText(e)` — una sola línea:
`Ejecución #{e.id} · {e.agent_type} · {e.status} · ticket #{e.ticket_id}{e.ticket_title ? " (" + e.ticket_title + ")" : ""} · {formatDuration(e.duration_ms ?? null)}`

`incidentToMarkdown(i)`:

```
## Incidencia {i.id}{i.title ? " — " + i.title : ""}

- Creada: {i.created_at}
- Estado: {i.status}
- Ejecución: {i.execution_id != null ? "#" + i.execution_id : "n/d"}
- Ticket: {i.tracker_id ?? "n/d"}{i.tracker_url ? " (" + i.tracker_url + ")" : ""}
- Adjuntos: {i.files.length}

{i.text}
```

(Campos verificados en `incidentModel.ts:34-47`; si `i.error != null`, agregar bullet `- Error: {i.error}` al final de la lista.)

`executionHistoryToRows(items)`:
- `headers` EXACTOS: `["id", "inicio", "agente", "runtime", "modelo", "estado", "duracion_ms", "costo_usd", "archivos", "ticket"]`.
  **Decisión deliberada (C4 — NO es espejo 1:1 de la tabla visible `ExecutionHistoryPage.tsx:170-179`):** se AGREGA `id` (no es columna visible, pero es la clave de trazabilidad al pegar en tickets/planillas y lo que abre el drawer) y se EXCLUYE la columna visible "Prompt" (en la UI renderiza `prompt_sha.slice(0, 7)` — verificado `:197-201` — un hash truncado sin valor alguno en un export). Las otras 8 columnas sí se corresponden 1:1 con las visibles.
- Por cada item de `items.slice(0, 1000)` (§4.7):
  - `csvRows`: `[it.id, it.started_at ?? "", it.agent_type, it.runtime ?? "", it.model ?? "", it.status, it.duration_ms, it.cost_usd, it.produced_files_count, it.ticket_title ?? String(it.ticket_id)]`
  - `mdRows`: igual pero `it.started_at ?? "n/d"` (ISO crudo, §4.10), `it.runtime ?? "n/d"`, `it.model ?? "n/d"`, `formatDuration(it.duration_ms)`, `it.cost_usd == null ? "n/d" : formatCostUsd(it.cost_usd)` (campos verificados en `endpoints.ts:1212-1233`).

**Tests PRIMERO** (`src/services/__tests__/copyFormats.test.ts`) — casos enumerados (mínimo 20):

1. `csvEscapeCell("simple")` → `simple` (sin comillas).
2. `csvEscapeCell("a,b")` → `"a,b"`.
3. `csvEscapeCell('di"jo')` → `"di""jo"`.
4. `csvEscapeCell("l1\nl2")` → `"l1\nl2"` (envuelto en comillas, salto intacto).
5. `csvEscapeCell("l1\r\nl2")` → envuelto (cubre `\r`).
6. `csvEscapeCell(null)` y `csvEscapeCell(undefined)` → `""`.
7. `csvEscapeCell(0)` → `0`; `csvEscapeCell(false)` → `false`.
8. `rowsToCsv(["a","b"], [["1","x,y"],[null,'q"q']])` → string EXACTO `a,b\r\n1,"x,y"\r\n,"q""q"` (golden literal).
9. `rowsToCsv(["a"], [])` → `a` (solo header, sin CRLF final).
10. `rowsToCsv` NO empieza con `﻿` (sin BOM, §4.1).
11. `mdEscapeCell("a|b")` → `a\|b`; `mdEscapeCell("l1\nl2")` → `l1 l2`; `mdEscapeCell(null)` → `""`.
12. `rowsToMarkdownTable(["h1","h2"], [["a","b"]])` → golden EXACTO `| h1 | h2 |\n| --- | --- |\n| a | b |`.
13. `ticketToMarkdown` con `ado_url` presente usa `ado_url`; sin `ado_url` usa `adoUrl(String(ado_id))` (assert contiene `dev.azure.com`); sin `description` no agrega cuerpo.
14. `executionToMarkdown` golden completo con todos los campos seteados; y con opcionales en null → celdas `n/d`/`—`.
15. `incidentToMarkdown` golden; con `tracker_url` null omite el paréntesis; con `error` agrega el bullet.
16. `executionHistoryToRows`: 1 item completo → `headers` exactos, `csvRows[0]` crudo (números como números, ISO tal cual) y `mdRows[0]` formateado; 1001 items → devuelve 1000 filas (guard §4.7).
17. **(§4.11)** `htmlEscapeCell('<b>&"x"</b>')` → `&lt;b&gt;&amp;&quot;x&quot;&lt;/b&gt;`; `htmlEscapeCell(null)` → `""`.
18. **(§4.11)** `rowsToHtmlTable(["h1","h2"], [["a","b"]])` → golden EXACTO `<table><thead><tr><th>h1</th><th>h2</th></tr></thead><tbody><tr><td>a</td><td>b</td></tr></tbody></table>`.
19. **(§4.11)** `rowsToHtmlTable` escapa contenido: celda `"<img>"` produce `&lt;img&gt;` y NO `<img>` (anti-inyección al pegar).
20. **(C3)** `copiedRowsLabel(1)` → `1 fila`; `copiedRowsLabel(50)` → `50 filas`; `copiedRowsLabel(1500)` → `1000 de 1500 filas; límite de copia`.

**Criterio binario + comando:** `npx vitest run src/services/__tests__/copyFormats.test.ts` → verde.

---

### F3 — `CopyAsButton.tsx`: el grupo "Copiar como…" reutilizable

**Objetivo (1 frase):** componente chico y tonto que renderiza los botones inline, llama a los builders puros, muestra el Toast de la casa y respeta la flag.

**Runtimes:** N/A-por-diseño — componente React sin backend.
**Trabajo del operador:** ninguno.

**Archivos:** `frontend/src/components/CopyAsButton.tsx` (nuevo), `frontend/src/components/CopyAsButton.module.css` (nuevo).

**Contrato EXACTO:**

```ts
import type { CopySuccessMethod } from "../services/copyService";

export interface CopyAsOption {
  label: string;              // texto EXACTO del botón: "Markdown" | "CSV" | "Texto" | "Tabla (ADO)" (o "Enlace" en superficies futuras)
  build: () => string;        // formateador puro de copyFormats; SIEMPRE el text/plain; se evalúa recién al click
  buildHtml?: () => string;   // §4.11: presente ⇒ se intenta copia enriquecida vía copyRichText(buildHtml(), build())
  successBody?: (method: CopySuccessMethod) => string; // override del body del toast de éxito (§4.3); ausente ⇒ COPY_TOAST_SUCCESS. Las opciones que no distinguen método simplemente ignoran el argumento.
}

export default function CopyAsButton({ options }: { options: CopyAsOption[] }): JSX.Element | null;
```

**Comportamiento EXACTO (implementar tal cual):**

1. `const flagsQ = useQuery({ queryKey: ["harness-flags"], queryFn: () => HarnessFlags.list(), staleTime: 60_000 });` — MISMO `queryKey` que el resto de la casa (verificado en `MemoryConfigPanel.tsx:26`, `DbCompareSettingsSection.tsx:80`, `HarnessFlagsPanel.tsx:359`, `PipelineTriggerCard.tsx:46`): comparte cache, cero request extra si ya está caliente. (`HarnessFlags.list` — `endpoints.ts:909-910` — devuelve `{ ok, flags, … }`; de ahí el `.flags` del paso 2.)
2. `if (!resolveCopyExportEnabled(flagsQ.data?.flags)) return null;` — fail-open: mientras no hay data renderiza (anti-flash, mismo trade-off aceptado por el plan 187 C2: el primer paint de la primerísima carga puede mostrar los botones un instante si la flag está OFF).
3. Render: `<span className={styles.group} role="group" aria-label="Copiar como">` + `<span className={styles.prefix}>Copiar:</span>` + un `<Button key={o.label} variant="ghost" size="sm" disabled={busy} onClick={() => void handleCopy(o)}>{o.label}</Button>` por opción (barrel `ui/`, G8) + `{toast && <Toast toast={toast} onClose={() => setToast(null)} />}`.
4. `handleCopy(o)`: `setBusy(true)`; `const r = o.buildHtml ? await copyRichText(o.buildHtml(), o.build()) : await copyText(o.build());`; si `r.ok` → `setToast({ variant: "success", body: o.successBody ? o.successBody(r.method) : COPY_TOAST_SUCCESS })` y armar timer de auto-cierre 4000 ms; si `!r.ok && r.reason !== "empty"` → `setToast({ variant: "error", body: COPY_TOAST_ERROR })` sin timer; si `r.reason === "empty"` → nada (§4.3); `finally setBusy(false)`.
5. Timer: guardarlo en `useRef<number | null>`, limpiarlo antes de armar uno nuevo y en un `useEffect` de cleanup al desmontar.
6. Estado: `useState<ToastState | null>` + `useState<boolean>` (busy). Nada más. Imports de Toast: `import Toast, { type ToastState } from "./Toast";` (contrato `Toast.tsx:9-17`).

**CSS (`CopyAsButton.module.css`):** `.group { display: inline-flex; align-items: center; gap: var(--space-1, 4px); }` `.prefix { color: var(--color-text-secondary); font-size: var(--font-size-sm, 12px); }` — SOLO tokens `var(--…)`, cero hex, cero `style={{}}` (G7). Si algún token no existe en `theme.css`, usar el fallback de `var()` mostrado (no inventar tokens nuevos).

**Tests:** la lógica de este componente ya está cubierta por F1 (resolver + copyText + copyRichText) y F2 (builders); el `.tsx` es cáscara fina (G4) → gate: `npx tsc --noEmit` exit 0 + smoke manual §10.3.

**Criterio binario + comando:** `npx tsc --noEmit` exit 0 **y** `grep -c "style={{" "Stacky Agents/frontend/src/components/CopyAsButton.tsx"` = 0.

---

### F4 — Adopción piloto en 3 superficies reales

**Objetivo (1 frase):** hacer visible el valor en un drawer de entidad, una tabla y una migración del sitio ad-hoc de mayor uso, con diff mínimo.

**Runtimes:** N/A-por-diseño — cambios de presentación en 3 componentes React.
**Trabajo del operador:** ninguno.

**F4.a — `components/ExecutionDetailDrawer.tsx` (drawer de entidad).**
- Posición EXACTA (C6): dentro del `<header className={styles.header}>` (`:69-81`) hay un `<div>` que envuelve `<h3 className={styles.title}>` y el bloque condicional del subtitle (`:70-77`), y como hermano de ese div está el `closeButton` (`:78-80`). Insertar el `CopyAsButton` como **ÚLTIMO hijo de ese `<div>` interior** (después del bloque `{content && (<div className={styles.subtitle}>…)}`, ANTES del `</div>` que cierra el div interior — NUNCA entre el div y el botón cerrar):
  `{content && <CopyAsButton options={drawerCopyOptions(content)} />}`
  con el helper local (misma unidad de archivo, arriba del componente):
  ```ts
  function drawerCopyOptions(e: AgentExecution): CopyAsOption[] {
    return [
      { label: "Markdown", build: () => executionToMarkdown(e) },
      { label: "Texto", build: () => executionToPlainText(e) },
    ];
  }
  ```
  (SIN opción "Enlace": §4.6. `AgentExecution` es exactamente lo que devuelve `Executions.byId` — `endpoints.ts:1267`.)
- Migración incidental del sitio 6 del inventario: en `:140-146` (ancla por texto: botón con `title="Copiar ruta"`), reemplazar `onClick={() => void navigator.clipboard.writeText(absolutePath)}` por `onClick={() => void copyText(absolutePath)}` e importar `copyText` de `../services/copyService`. El botón NO gana toast (hoy no da feedback; diff mínimo, §4.4).
- Imports nuevos: `CopyAsButton` + `type CopyAsOption` de `./CopyAsButton`; `executionToMarkdown, executionToPlainText` de `../services/copyFormats`; `copyText` de `../services/copyService`; `type AgentExecution` de `../types` (si no estaba importado).

**F4.b — `pages/ExecutionHistoryPage.tsx` (tabla).**
- Entre el cierre del bloque de filtros (`</div>` en `:158`; ancla por texto: el div `className={styles.filters}`) y el comentario `{/* Tabla */}` (`:160`), insertar:
  ```tsx
  {items.length > 0 && (
    <CopyAsButton
      options={[
        {
          label: "CSV",
          build: () => { const r = executionHistoryToRows(items); return rowsToCsv(r.headers, r.csvRows); },
          successBody: () => `Tabla copiada como CSV (${copiedRowsLabel(items.length)}).`,
        },
        {
          label: "Markdown",
          build: () => { const r = executionHistoryToRows(items); return rowsToMarkdownTable(r.headers, r.mdRows); },
          successBody: () => `Tabla copiada como Markdown (${copiedRowsLabel(items.length)}).`,
        },
        {
          label: "Tabla (ADO)",
          build: () => { const r = executionHistoryToRows(items); return rowsToMarkdownTable(r.headers, r.mdRows); },
          buildHtml: () => { const r = executionHistoryToRows(items); return rowsToHtmlTable(r.headers, r.mdRows); },
          successBody: (m) =>
            m === "richClipboard"
              ? `Tabla copiada para ADO (${copiedRowsLabel(items.length)}).`
              : `Tabla copiada como Markdown (${copiedRowsLabel(items.length)}; sin copia enriquecida en este contexto).`,
        },
      ]}
    />
  )}
  ```
- Imports nuevos: `CopyAsButton` de `../components/CopyAsButton`; `executionHistoryToRows, rowsToCsv, rowsToMarkdownTable, rowsToHtmlTable, copiedRowsLabel` de `../services/copyFormats`.
- NO se toca `CostTable.tsx` ni `costCenter.logic.ts` (§2.2, §9).

**F4.c — `components/StructuredOutput.tsx` (migración del writeText de mayor uso).**
- Elegido por uso: su `CopyButton` local (`:226-244`) aparece en CADA sección de CADA output estructurado (tablero de tickets + drawer + revisión) — es el sitio con más instancias renderizadas del inventario.
- Diff mínimo dentro de `handleCopy` (`:229-237`): reemplazar el bloque `try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(...) } catch {...}` por:
  ```ts
  const r = await copyText(text);
  if (r.ok) {
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  ```
  e importar `copyText` de `../services/copyService`. Conserva el `✓` inline de 1500 ms como ÚNICO feedback (§4.4); NO se agrega Toast; NO se gatea por flag (§3.6). (`copyText` jamás lanza — devuelve `CopyResult` — así que el try/catch se elimina sin cambiar semántica: hoy el catch era un noop.)

**Tests:** builders y servicio ya cubiertos (F1/F2). Gate de la fase:
1. `npx tsc --noEmit` exit 0.
2. `grep -c "writeText" "Stacky Agents/frontend/src/components/StructuredOutput.tsx"` = 0 y `grep -c "writeText" "Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx"` = 0 (ambos migrados; `copyText` no matchea).
3. Re-correr `npx vitest run src/services/__tests__/copyService.test.ts` y `.../copyFormats.test.ts` → siguen verdes.

**Criterio binario:** los 3 comandos de arriba en verde/0-hits.

---

### F5 — Ratchet `copyDebtRatchet`: la deuda solo baja

**Objetivo (1 frase):** congelar los `.writeText(` directos fuera del servicio para que ningún PR futuro agregue el patrón ad-hoc.

**Runtimes:** N/A-por-diseño — test de repositorio frontend.
**Trabajo del operador:** ninguno.

**Archivos:** `frontend/src/__tests__/copyDebtRatchet.test.ts` (nuevo), `frontend/src/__tests__/copyDebtBaseline.json` (nuevo, generado).

**Mecánica:** copiar EXACTAMENTE la de `formatDebtRatchet.test.ts` (`:13-124`: `listFiles` recursivo sobre `SRC`, conteo por archivo, baseline JSON ordenado, modo regen por env var, `assertNoIncrease` con forced-zero) con estos reemplazos:

- Regex (array de 1): `const COPY_RES: RegExp[] = [/\.writeText\s*\(/g];` — atrapa `navigator.clipboard.writeText(`, `clipboard?.writeText(` y los casos PARTIDOS en 2 líneas (`CodeIntegrityCard.tsx:53-54`, `PlansBoardPage.tsx:88-89`: la línea `.writeText(copyText)` matchea sola, SIN flag multiline — re-verificado por el juez v2 reproduciendo el grep: 14 matches / 13 archivos hoy). NO atrapa los usos del mock en `RemediationCard.test.tsx` (`writeText = vi.fn()`, `{ writeText }`, `expect(writeText)` — ninguno tiene punto antes y paréntesis después; verificado). NO se ratchetea `clipboard.write(` a secas (§4.11): `write(` es demasiado genérico (streams, sockets) y hoy su único caller legítimo es el propio `copyService.ts`.
- `ALLOWLIST = new Set(["services/copyService.ts", "services/__tests__/copyService.test.ts", "__tests__/copyDebtRatchet.test.ts"])` (auto-exclusión del propio ratchet, patrón `formatDebtRatchet.test.ts:29`).
- Forced-zero: `components/ui/` y `components/shell/` (mismas carpetas que `formatDebtRatchet.test.ts:81`).
- Env de regeneración: `COPY_DEBT_REGEN=1`. Cabecera del test con los DOS comandos (PowerShell y bash), espejo de `formatDebtRatchet.test.ts:6-8`.
- Clave del JSON: `copyByFile` (espejo de `formatByFile`).
- Mensaje de error SIN la secuencia punto+writeText+paréntesis (gotcha §3.7), con comillas RECTAS (C9), texto fijo:

```ts
`REGRESION de portapapeles en ${file}: ${count} > ${allowed}. La deuda solo puede bajar (plan 194). Usa copyText de services/copyService.`
```

**Baseline esperado (foto verificada 2026-07-18, post-migraciones F4 — 12 sitios / 11 archivos):**

```json
{
  "copyByFile": {
    "components/ChatDrawer.tsx": 2,
    "components/CodeIntegrityCard.tsx": 1,
    "components/DailyStandupModal.tsx": 1,
    "components/HarnessFlagsPanel.tsx": 1,
    "components/MermaidDiagram.tsx": 1,
    "components/QaBrowserRunModal.tsx": 1,
    "components/dbcompare/SqlViewer.tsx": 1,
    "components/dbcompare/SummaryHero.tsx": 1,
    "components/devops/DirTreePreview.tsx": 1,
    "components/devops/RemediationCard.tsx": 1,
    "pages/PlansBoardPage.tsx": 1
  }
}
```

El baseline CANÓNICO es el que emita `COPY_DEBT_REGEN=1` en el checkout del implementador (la sesión paralela puede haber agregado sitios); si difiere de la tabla, commitear el generado y anotar la diferencia en el PR. `ExecutionDetailDrawer.tsx` y `StructuredOutput.tsx` NO deben aparecer (migrados en F4; si aparecen, F4 quedó incompleta — corregir F4, no el baseline).

**Tests PRIMERO:** escribir el test, correrlo SIN baseline → debe fallar con el mensaje "Falta …copyDebtBaseline.json" (espejo `formatDebtRatchet.test.ts:112`); generar baseline con regen; re-correr normal → verde.

**Criterio binario + comando:**
- PowerShell: `$env:COPY_DEBT_REGEN='1'; npx vitest run src/__tests__/copyDebtRatchet.test.ts; Remove-Item Env:\COPY_DEBT_REGEN` (una vez), luego `npx vitest run src/__tests__/copyDebtRatchet.test.ts` → verde y el JSON committeado coincide con lo listado (± drift de sesión paralela documentado en el PR).

---

### F6 — Cierre: verificación integral y smoke manual

**Objetivo (1 frase):** correr TODOS los gates del plan y documentar el smoke de flag y pegado real.

**Runtimes:** N/A-por-diseño — solo verificación.
**Trabajo del operador:** ninguno (el smoke lo hace el implementador).

Ver §10 (DoD). Sin código nuevo en esta fase.

---

## 7. Coexistencias obligatorias (declaradas; NO bloquear, NO importar código ajeno)

1. **Plan 175 (peek + menú contextual, NO implementado)** planea un `services/clipboard.ts` local para sus quick-actions. **Nota para su implementador:** NO crear `services/clipboard.ts`; consumir `services/copyService.ts` (`copyText`) de ESTE plan. Este plan no bloquea al 175 ni depende de él.
2. **Plan 187 v2 (selección múltiple, NO implementado)** incluye "Copiar N links" inline. **Nota para su implementador:** rutear el copiado por `copyText` y, si copia tablas/listas, usar `rowsToCsv`/`rowsToMarkdownTable`. Este plan no bloquea al 187.
3. **Plan 165 (contrato URL/deep-links, NO implementado):** cuando exista URL canónica por ejecución, agregar la opción `{ label: "Enlace", build: () => <url> }` a `drawerCopyOptions` (F4.a). Hasta entonces, sin opción Enlace (§4.6).
4. **Planes 173/175/187 y la tupla `interfaz_ui`:** pueden agregar keys a la misma tupla de `_CATEGORY_KEYS`; orden irrelevante, solo sumar la nuestra (F0.2).
5. **Plan 172 (teclado primero, NO implementado):** el copiado por atajo de teclado se difiere al 172 (§4.11 documenta el descarte deliberado del listener directo). Cuando el 172 exista, sus atajos deben invocar `copyText`/`copyRichText`, nunca `writeText` directo (el ratchet F5 lo garantiza mecánicamente).
6. **Centro de Costos:** `toCsv`/`CostTable` quedan intactos (descarga Blob, contrato del plan 142). Unificarlos con `rowsToCsv` es una migración futura FUERA de scope.
7. Todo lo anterior es **autocontenido**: este plan no importa ni asume código de ningún plan no implementado.

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Mitigación (codificada) |
|---|--------|--------------------------|
| R1 | Clipboard denegado o contexto no-seguro (`http://IP:puerto` en LAN — ahí el fallback es el camino PRINCIPAL, §4.9) | Fallback textarea+execCommand (F1) con foco y selección preservados (§4.9, test caso 11); si también falla, UN toast de error con string fijo (§4.3); nunca excepción sin capturar |
| R2 | Doble feedback en superficies que ya tenían el suyo | §4.4: el servicio JAMÁS muestra toasts; migraciones conservan su feedback y no suman Toast; CopyAsButton es dueño único del Toast en superficies nuevas |
| R3 | Tabla enorme cuelga el hilo al serializar | Paginación existente (límite estructural 50 en ExecutionHistoryPage) + guard `slice(0, 1000)` testeado (§4.7, F2 caso 16) |
| R4 | CRLF/BOM rompen el pegado en Excel o ensucian editores | CRLF fijado, BOM prohibido, ambos cableados por tests golden (F2 casos 8-10) |
| R5 | Sesión paralela corre líneas o agrega writeText nuevos | Anclas por texto en cada edición; baseline canónico = regen en el checkout del implementador (F5); archivos `M` ajenos NO se tocan (G10) |
| R6 | `execCommand` deprecado desaparece de algún browser | Es SOLO fallback tras fallo del camino moderno, envuelto en try/catch; su ausencia degrada a toast de error, jamás a crash |
| R7 | Flash de botones con flag OFF en el primer paint | Fail-open declarado (§6 F3.2), mismo trade-off aceptado por 187 C2; mounts posteriores usan el cache compartido `["harness-flags"]` |
| R8 | El propio ratchet o este doc disparan un gate | §3.7: ALLOWLIST auto-excluye el test; el doc vive en docs/ fuera de todo scanner frontend; mensajes de error sin la secuencia prohibida |
| R9 | Ratchets/meta-tests ajenos rojos en HEAD confunden el veredicto | Criterio RELATIVO a HEAD (G3): comparar contra el estado pre-plan, exigir cero regresiones propias |
| R10 | `ClipboardItem`/`clipboard.write` ausentes (contexto no-seguro, browser viejo) rompen "Tabla (ADO)" | `copyRichText` degrada a `copyText(plain)` (Markdown) y el toast lo DECLARA (§4.3, §4.11, F1 caso 13); truncados nunca silenciosos (`copiedRowsLabel`, C3) |
| R11 | Truncado del guard de 1000 filas se vuelve alcanzable por un plan futuro y miente | `copiedRowsLabel` cablea el aviso "1000 de N filas; límite de copia" en TODOS los bodies de tabla (§4.3/§4.7, F2 caso 20) |

---

## 9. Fuera de scope (explícito)

- Exportar a ARCHIVO descargable (.csv/.md): solo portapapeles. La descarga Blob del Centro de Costos queda como está.
- Imágenes y binarios en el portapapeles: fuera. `text/html` entra SOLO vía `copyRichText` para la opción "Tabla (ADO)" (§4.11); cualquier otra superficie enriquecida es futura.
- Cualquier endpoint o cambio backend más allá del registro de la flag (F0).
- Migrar los 12 sitios restantes del inventario: el ratchet los congela; migraciones oportunistas en PRs futuros (cada una BAJA el baseline con regen).
- Opción "Enlace" para ejecuciones (espera plan 165) y menús contextuales (plan 175).
- Unificar `toCsv` del Centro de Costos con `rowsToCsv`.
- Copiado por atajo de teclado: diferido al plan 172 (decisión razonada en §4.11 — NO agregar un listener directo que el 172 tendría que desmontar).

---

## 10. Orden, DoD y glosario

### 10.1 Orden de implementación (estricto)

F0 → F1 → F2 → F3 → F4 → F5 → F6. (F1 y F2 no dependen entre sí pero el orden fija el contrato de feedback antes de los builders; F3 requiere F1; F4 requiere F1+F2+F3; F5 requiere F4 terminada — el baseline no debe contener los archivos migrados.)

### 10.2 Definition of Done (comandos EXACTOS)

Backend (desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`, intérprete G1):

```powershell
& "N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe" -m pytest tests/test_harness_flags.py -q
```

Frontend (desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`, POR ARCHIVO — G4):

```powershell
npx vitest run src/services/__tests__/copyService.test.ts
npx vitest run src/services/__tests__/copyFormats.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
npx vitest run src/__tests__/formatDebtRatchet.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/formDebtRatchet.test.ts
npx tsc --noEmit
```

Veredicto: K1-K7 de §1 en verde/0-hits con criterio relativo a HEAD (G3) + smoke §10.3 documentado (K8).

### 10.3 Smoke manual documentado (gap RTL/jsdom, G4 — pegar el resultado en el PR)

1. Abrir Historial de ejecuciones con datos → click `Copiar: CSV` → toast "Tabla copiada como CSV (N filas)." → pegar en un editor: header + N filas, comas y CRLF.
2. Mismo lugar → `Markdown` → pegar: tabla con `| --- |`.
3. Abrir el detalle de una ejecución → `Copiar: Markdown` → pegar: título `## Ejecución #…` + tabla de campos. → `Texto` → una línea.
4. En el mismo drawer, botón "Copiar ruta" de un artefacto → pegar: la ruta absoluta (migración F4.a) → verificar además que el FOCO no saltó a body (§4.9; en https/localhost usa el camino moderno — el chequeo de foco aplica sobre todo al probar por `http://IP:puerto`).
5. En un output estructurado, botón de copiar sección → `✓` 1500 ms (migración F4.c).
6. Settings → Flags del arnés → apagar `Copiar como… (portapapeles universal)` → los grupos "Copiar:" desaparecen del historial y del drawer; los botones preexistentes (ruta, sección) siguen funcionando. Reencender → vuelven.
7. **(§4.11)** Historial → `Tabla (ADO)` → pegar en la descripción o un comentario de un work item ADO: tabla REAL renderizada (sin pipes); pegar en Notepad: tabla Markdown. Si el toast dijo "sin copia enriquecida en este contexto", documentar que el deploy corre en contexto no-seguro (esperado en LAN http) y que el pegado fue Markdown.

### 10.4 Glosario

- **Ratchet suave:** test que congela un conteo de deuda por archivo; solo acepta que baje (regen manual documentado). Patrón de la casa: `formatDebtRatchet.test.ts`.
- **Baseline:** JSON committeado con la foto de deuda aceptada (`copyDebtBaseline.json`).
- **Fail-open:** ante ausencia de datos de la flag, comportarse como ON (default de la flag) para no ocultar UI por una carga lenta.
- **CRLF:** `\r\n`, fin de línea Windows; fijado para el CSV del portapapeles (§4.1).
- **BOM:** marca `﻿` inicial de archivos UTF-8; prohibida acá (§4.1).
- **execCommand:** API legada `document.execCommand("copy")`, usada SOLO como fallback (§6 F1) con foco/selección preservados (§4.9).
- **ClipboardItem / copia enriquecida:** API `navigator.clipboard.write` con múltiples MIME types (`text/html` + `text/plain`); usada SOLO por `copyRichText` para "Tabla (ADO)" (§4.11), con degradación declarada.
- **Curated defaults:** set `_CURATED_DEFAULTS_ON` en `test_harness_flags.py:467` — única vía canónica para que una flag bool nazca con default ON conocido. Se DEFINE en el archivo de tests; NO se importa de ningún módulo (C2).
- **HITL:** human-in-the-loop; acá trivial: copiar es read-only y siempre iniciado por click del operador.
- **Superficie:** lugar concreto de la UI donde se ofrece la acción (drawer, tabla, sección).
