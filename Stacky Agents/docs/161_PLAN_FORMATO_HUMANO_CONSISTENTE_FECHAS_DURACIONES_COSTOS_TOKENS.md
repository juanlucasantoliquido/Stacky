# Plan 161 — Formato humano consistente: fechas, duraciones, costos USD, tokens y tamaños

**Estado: PROPUESTO v1 — 2026-07-17**

## 1. Objetivo

Crear el módulo canónico ÚNICO de formateo de presentación del frontend (`src/services/format.ts`): funciones puras y deterministas para fechas/horas, duraciones, costos USD, tokens, enteros con separador de miles, tamaños en bytes y porcentajes — con reglas CONGELADAS en este documento — y migrar 3 superficies ejemplares de alto tráfico (Ejecuciones/Logs, PM Command Center, Centro de Costos) a esas funciones, protegido por un ratchet anti-regresión (`formatDebtRatchet.test.ts`, espejo exacto de `uiDebtRatchet.test.ts` del plan 138 y `motionDebtRatchet.test.ts` del plan 143) que congela por archivo la cantidad de formatters crudos y solo permite que BAJE. Hoy el mismo dato (un costo, una duración, un timestamp) se ve distinto según la pantalla; después de este plan cada tipo de dato tiene UNA representación y ningún archivo nuevo puede volver a inventar la suya.

### KPIs binarios

| # | KPI | Verificación |
|---|-----|--------------|
| K1 | `src/services/format.ts` exporta EXACTAMENTE las 10 funciones del catálogo (§4.F0) y su test pasa | `npx vitest run src/services/format.test.ts` exit 0 |
| K2 | Ratchet activo con baseline commiteado y regla solo-baja | `npx vitest run src/__tests__/formatDebtRatchet.test.ts` exit 0 y existe `src/__tests__/formatDebtBaseline.json` |
| K3 | En el baseline final NO figuran (0 matches): `pages/ExecutionHistoryPage.tsx`, `components/ExecutionDetailDrawer.tsx`, `pages/SystemLogsPage.tsx`, `lib/costCenter.logic.ts`, `components/CostPreview.tsx`, `components/CostCapIndicator.tsx`; y `pages/PMCommandCenter.tsx` figura con ≤ 4 | inspección de `formatDebtBaseline.json` |
| K4 | Compila sin errores | `npx tsc --noEmit` exit 0 desde `Stacky Agents/frontend` |
| K5 | Contratos preexistentes intactos | `npx vitest run src/lib/__tests__/costCenter.logic.test.ts`, `npx vitest run src/utils/__tests__/formatRelativeTime.test.ts`, `npx vitest run src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts` — los 3 exit 0 |

## 2. Por qué ahora / gap que cierra

Evidencia re-verificada hoy 2026-07-17 con `grep -rEn "toLocaleString\(|toLocaleTimeString\(|toLocaleDateString\(|toFixed\("` sobre `frontend/src`: **94 ocurrencias en 39 archivos**, cada superficie con su propia regla:

- **Costos USD, 4 reglas distintas para el mismo dato:**
  - `src/lib/costCenter.logic.ts:11` → `$` + 2 decimales siempre (Centro de Costos, plan 142).
  - `src/pages/ExecutionHistoryPage.tsx:38`, `src/components/ExecutionDetailDrawer.tsx:30`, `src/components/HarnessHealthCard.tsx:96`, `src/components/OperationalHealthCard.tsx:27`, `src/components/ProvenanceDrawer.tsx:78`, `src/components/CodexConsoleDock.tsx:196` → `$` + 4 decimales siempre.
  - `src/pages/PMCommandCenter.tsx:241-243` y `src/components/WeeklyDigestCard.tsx:19-21` → escalonado 4/3/2 decimales.
  - `src/components/ModelDecisionChip.tsx:34`, `src/components/CostPreview.tsx:72`, `src/components/CostCapIndicator.tsx:53` → 2 decimales.
  El MISMO costo de $0.42 se ve "$0.42", "$0.4200" o "$0.420" según la pantalla.
- **Tokens, 3 notaciones:** compacta `12.3k` (`src/lib/costCenter.logic.ts:17-18`, `src/components/TokenCounter.tsx:28`, `src/components/CostPreview.tsx:80`), compacta con M a 2 decimales (`src/pages/PMCommandCenter.tsx:234`), y entero con separador dependiente del locale del navegador (`src/components/ExecutionDetailDrawer.tsx:37`, `src/components/CodexConsoleDock.tsx:192`, `src/pages/SystemLogsPage.tsx:205,370`).
- **Duraciones, 5 reglas:** `ms → Xm Ys` (`src/pages/ExecutionHistoryPage.tsx:26-34`), `segundos → X.Xm` decimal (`src/components/ExecutionDetailDrawer.tsx:20-25`), solo segundos sin rama de minutos (`src/pages/SystemLogsPage.tsx:30-34`, `src/components/ProvenanceDrawer.tsx:90`, `src/components/CostPreview.tsx:75`, `src/pages/PMCommandCenter.tsx:323`), segundos como número plano (`src/components/DossierPanel.tsx:144`, `src/diagnostics/codeIntegrityModel.ts:27`).
- **Fechas/horas, lo peor:** locale explícito `es-AR` (`src/pages/PMCommandCenter.tsx:26,39`, `src/pages/SystemLogsPage.tsx:24`, `src/pages/SprintBoardPage.tsx:71`), `es-ES` (`src/components/AgentHistoryPage.tsx:69-70`, `src/components/ChatDrawer.tsx:378`) y **sin locale = depende del navegador del operador** (`src/components/AgentHistoryModal.tsx:152`, `src/pages/DiagnosticsPage.tsx:40`, `src/pages/FlowConfigPage.tsx:241,280`, `src/components/HarnessHealthCard.tsx:377`, `src/components/devops/ServersSection.tsx:376`, `src/components/LogsPanel.tsx:30`, `src/components/ActiveRunsPanel.tsx:170`, entre otros). Un mismo `updated_at` puede renderizar "7/16/2026" o "16/7/2026" según la máquina.
- **Bytes, con y sin espacio:** `1.5 KB` (`src/pages/DiagnosticsPage.tsx:32-33`, `src/components/FileManagerModal.tsx:15-16`) vs `1.5KB` (`src/components/AgentHistoryPage.tsx:335`).

Lo que SÍ existe y este plan reusa (no reinventa):
- `src/utils/formatRelativeTime.ts:15` — tiempo relativo en español con reglas YA CONGELADAS y `nowMs` inyectable; test en `src/utils/__tests__/formatRelativeTime.test.ts`. Se re-exporta desde el módulo canónico, NO se duplica ni se mueve.
- `src/lib/costCenter.logic.ts:9-25` — `formatUsd`/`formatTokens`/`formatPct` del plan 142, con contrato testeado en `src/lib/__tests__/costCenter.logic.test.ts:33-47`. Se migran a delegación preservando su contrato (`"n/d"` como marcador nulo).
- Patrón de ratchet probado 2 veces: `src/__tests__/uiDebtRatchet.test.ts` (plan 138) y `src/__tests__/motionDebtRatchet.test.ts` (plan 143). Este plan copia ese patrón EXACTO (baseline JSON por archivo, solo-baja, regen por env var con guard anti-suba, forced-zero para `components/ui/` y `components/shell/`).
- NO existe ningún `src/services/format*.ts` ni `src/lib/format*.ts` (verificado por Glob hoy; lo único es `src/utils/formatRelativeTime.ts`).

## 3. Principios y guardarraíles

1. **Reglas congeladas, cero criterio del implementador.** Cada función tiene tabla de casos con output EXACTO (§4.F0). El implementador copia; no elige.
2. **Canónico = mayoría actual.** Cada regla canónica se eligió mirando qué usa hoy la mayoría de las superficies, para minimizar el cambio visual percibido (justificación por regla en §4.F0.d).
3. **Determinismo total.** Nada de `toLocaleString`-y-familia dentro del módulo canónico: fecha/hora se construyen a mano desde getters de `Date` (independiente del navegador y del locale del SO). "Ahora" y la zona horaria son inyectables para tests (mismo patrón que `formatRelativeTime.ts:15`).
4. **Solo presentación.** El módulo recibe números/ISO strings y devuelve strings. No fetch, no React, no estado, no side-effects. Igual precedente que `src/services/uiGuards.ts` (lógica pura + test colocalizado `uiGuards.test.ts`).
5. **Ratchet, no big-bang.** Las ~32 superficies no migradas quedan congeladas en baseline; la deuda solo puede bajar. Nadie está obligado a migrar todo hoy.
6. **Sin flag de harness.** Presentación pura aditiva, mismo precedente que los planes 138/140/141/143 (todos sin flag). No aplica ninguna de las 4 excepciones duras: no bypasea revisión humana, no es destructivo/irreversible, no depende de prerequisito no garantizado, no reduce seguridad.
7. **Paridad de runtimes por construcción.** 100% frontend web: idéntico bajo Codex CLI, Claude Code CLI y GitHub Copilot Pro. Fallback: N/A en todas las fases.
8. **Gotcha prosa-vs-gate (6+ ocurrencias en la casa):** los comentarios de los archivos MIGRADOS o NUEVOS (salvo los 3 del allowlist del ratchet, §4.F1) NO deben nombrar los métodos crudos gateados; referirse a ellos como "formatter crudo" o "método nativo de formateo". Los únicos archivos autorizados a contener esos literales son `src/services/format.ts`, `src/services/format.test.ts` y `src/__tests__/formatDebtRatchet.test.ts`.
9. **Pre-flight por fase:** antes de editar cada archivo, correr `git status --porcelain -- "<ruta>"` desde la raíz del repo. Si el archivo aparece modificado (WIP ajeno sin commitear) ⇒ STOP, avisar al orquestador, no editar. El implementador NO commitea.
10. **Contratos ajenos intactos:** NO tocar los imports existentes de `formatRelativeTime` (los consumen 3 tests de adopción: `src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts`, `DocsPage.adoption.test.ts`, `ReviewInboxPage.adoption.test.ts`). NO tocar `formatPct` ni el CSV de `costCenter.logic.ts`.

## 4. Fases

Convención de comandos: todos los comandos vitest/tsc se corren desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`. Los `:NN` de línea citados son orientativos; el ancla normativa es el TEXTO citado (regla de la casa). Tests SIEMPRE por archivo (test-order pollution conocida de vitest en este repo).

---

### F0 — Módulo canónico `format.ts` (TDD)

**Objetivo:** crear el catálogo único de funciones de formateo puro, test-first, con las reglas congeladas de esta sección. Valor: una sola fuente de verdad de presentación.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/services/format.test.ts` (PRIMERO)
- CREAR `Stacky Agents/frontend/src/services/format.ts` (después, hasta poner verde el test)
- EDITAR `Stacky Agents/frontend/src/utils/formatRelativeTime.ts` (1 línea: exportar la constante de meses)

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/services" "Stacky Agents/frontend/src/utils/formatRelativeTime.ts"` → si hay salida con `M`, STOP.

#### F0.a — Cambio mínimo en `formatRelativeTime.ts`

En `src/utils/formatRelativeTime.ts:1`, la línea que hoy es:

```ts
const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
```

pasa a:

```ts
export const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
```

Nada más cambia en ese archivo. (Aditivo: su test existente no importa `MESES_ABREV`, sigue verde.)

#### F0.b — Catálogo congelado (10 exports de `src/services/format.ts`)

```ts
export type FormatTz = "local" | "utc";

export { formatRelativeTime } from "../utils/formatRelativeTime";   // 1 (re-export, reglas ya congeladas allá)
export function formatDate(iso: string | null | undefined, tz: FormatTz = "local"): string;      // 2
export function formatTime(iso: string | null | undefined, tz: FormatTz = "local"): string;      // 3
export function formatDateTime(iso: string | null | undefined, tz: FormatTz = "local"): string;  // 4
export function formatDuration(ms: number | null | undefined): string;                           // 5
export function formatCostUsd(n: number | null | undefined): string;                             // 6
export function formatTokens(n: number | null | undefined): string;                              // 7
export function formatInt(n: number | null | undefined): string;                                 // 8
export function formatBytes(n: number | null | undefined): string;                               // 9
export function formatPercent(pct: number | null | undefined, decimals: number = 0): string;     // 10
```

Cabecera obligatoria del archivo (copiar tal cual):

```ts
/**
 * Plan 161 F0 — Módulo canónico ÚNICO de formateo humano del frontend.
 * Funciones PURAS y deterministas (sin React, sin fetch, sin Date.now implícito
 * en firmas testeables, sin APIs de locale del navegador). Este archivo y su
 * test son los ÚNICOS autorizados por formatDebtRatchet a usar métodos
 * nativos de formateo; el resto del código importa de acá.
 * Reglas congeladas en docs/161_PLAN_FORMATO_HUMANO_CONSISTENTE_*.md §4.F0.
 */
```

#### F0.c — Reglas y pseudocódigo por función (NORMATIVO)

Helper interno (no exportado):

```ts
const pad2 = (n: number) => String(n).padStart(2, "0");

function dateParts(iso: string | null | undefined, tz: FormatTz):
  { y: number; mo: number; day: number; h: number; mi: number; s: number } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return tz === "utc"
    ? { y: d.getUTCFullYear(), mo: d.getUTCMonth(), day: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes(), s: d.getUTCSeconds() }
    : { y: d.getFullYear(), mo: d.getMonth(), day: d.getDate(), h: d.getHours(), mi: d.getMinutes(), s: d.getSeconds() };
}
```

**2) `formatDate(iso, tz)`** → `"{D} {mes} {YYYY}"` con `mes` de `MESES_ABREV` (importada de `../utils/formatRelativeTime`), día SIN cero a la izquierda (coherente con el corte absoluto de `formatRelativeTime.ts:33`).
- `dateParts` null → `"—"`. Si no: `` `${p.day} ${MESES_ABREV[p.mo]} ${p.y}` ``.

**3) `formatTime(iso, tz)`** → `"{HH}:{mm}:{ss}"` 24h, todo con `pad2`.
- `dateParts` null → `"—"`. Si no: `` `${pad2(p.h)}:${pad2(p.mi)}:${pad2(p.s)}` ``.

**4) `formatDateTime(iso, tz)`** → `"{D} {mes} {YYYY} {HH}:{mm}"` (sin segundos; quien necesite segundos compone `formatDate(x) + " " + formatTime(x)`).
- `dateParts` null → `"—"`. Si no: `` `${p.day} ${MESES_ABREV[p.mo]} ${p.y} ${pad2(p.h)}:${pad2(p.mi)}` ``.

**5) `formatDuration(ms)`**:
```ts
if (ms === null || ms === undefined || Number.isNaN(ms) || ms < 0) return "—";
if (ms < 1000) return `${Math.round(ms)}ms`;
const sec = ms / 1000;
if (Math.round(sec * 10) / 10 < 60) return `${(Math.round(sec * 10) / 10).toFixed(1)}s`;
const secR = Math.round(sec);
if (secR < 3600) return `${Math.floor(secR / 60)}m ${secR % 60}s`;
return `${Math.floor(secR / 3600)}h ${Math.floor((secR % 3600) / 60)}m`;
```
(Sin tier de días: las horas crecen sin tope. Regla base = `ExecutionHistoryPage.tsx:26-34`, la más completa de la casa, extendida con rama de horas.)

**6) `formatCostUsd(n)`** — escalonado de DOS niveles (no tres):
```ts
if (n === null || n === undefined || Number.isNaN(n)) return "—";
const sign = n < 0 ? "-" : "";
const abs = Math.abs(n);
if (abs !== 0 && abs < 0.01) return `${sign}$${abs.toFixed(4)}`;
return `${sign}$${abs.toFixed(2)}`;
```
Sin separador de miles (hoy ninguna superficie agrupa miles en USD).

**7) `formatTokens(n)`** — compacta, IDÉNTICA a `costCenter.logic.ts:14-20` (contrato del plan 142; la delegación de F4 depende de esta igualdad):
```ts
if (n === null || n === undefined || Number.isNaN(n)) return "—";
const r = Math.round(n);
const abs = Math.abs(r);
if (abs >= 1_000_000) return `${(r / 1_000_000).toFixed(1)}M`;
if (abs >= 1_000) return `${(r / 1_000).toFixed(1)}k`;
return String(r);
```

**8) `formatInt(n)`** — entero exacto con separador de miles `.` (estilo es-AR), independiente del navegador:
```ts
if (n === null || n === undefined || Number.isNaN(n)) return "—";
const t = Math.trunc(n);
const sign = t < 0 ? "-" : "";
return sign + String(Math.abs(t)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
```

**9) `formatBytes(n)`** — base 1024, 1 decimal, CON espacio antes de la unidad (regla mayoritaria: `DiagnosticsPage.tsx:32-33`, `FileManagerModal.tsx:15-16`, `FileSelectorModal.tsx:73-74`, `DocViewer.tsx:152`):
```ts
if (n === null || n === undefined || Number.isNaN(n) || n < 0) return "—";
if (n < 1024) return `${Math.round(n)} B`;
if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
return `${(n / 1024 ** 3).toFixed(1)} GB`;
```

**10) `formatPercent(pct, decimals = 0)`** — recibe escala 0–100 (los campos `*_pct` del backend ya vienen 0–100; los ratios 0–1 se multiplican por 100 EN el call-site, como hoy):
```ts
if (pct === null || pct === undefined || Number.isNaN(pct)) return "—";
return `${pct.toFixed(decimals)}%`;
```

#### F0.d — Justificación de cada regla canónica (por qué minimiza el cambio visual)

| Regla | Elegida por | Superficies que ya la usan | Cambian |
|---|---|---|---|
| Fecha `3 jul 2026` | coherencia con el corte absoluto YA congelado de `formatRelativeTime.ts:33` y con `PMCommandCenter.tsx:26` (month short) | relativo en 3 páginas, PMCC, SprintBoard | las que hoy dependen del locale del navegador (eso es un FIX, no una regresión) |
| Hora 24h `14:03` | `hour12: false` es la opción explícita mayoritaria (`PMCommandCenter.tsx:39`, `SystemLogsPage.tsx:24`, `PMCommandCenter.tsx:380`) | es-AR explícitos | los sin-locale |
| USD 2 dec / 4 dec sub-centavo | 2 dec = Centro de Costos (`costCenter.logic.ts:11`, contrato 142 testeado en `costCenter.logic.test.ts:35`); 4 dec sub-centavo = todos los `$` de telemetría por ejecución | Centro de Costos intacto; micro-costos intactos | tier intermedio de 3 dec de `PMCommandCenter.tsx:242` y `WeeklyDigestCard.tsx:20` ($0.420 → $0.42) |
| Tokens `12.3k`/`1.2M` | idéntica a `costCenter.logic.ts:14-20` (142) y `TokenCounter.tsx:28` | Centro de Costos, TokenCounter, CostPreview | `PMCommandCenter.tsx:234` (M a 2 dec → 1 dec) |
| Duración `Xm Ys` | `ExecutionHistoryPage.tsx:26-34` (la más completa) | historial | `ExecutionDetailDrawer.tsx:24` (`2.5m` → `2m 30s`, mejora legibilidad) |
| Bytes `1.5 KB` con espacio | 4 archivos vs 1 sin espacio | Diagnostics, FileManager, FileSelector, DocViewer | `AgentHistoryPage.tsx:335` (cuando se migre; NO está en las fases ejemplares) |
| Marcador vacío `"—"` | mayoritario (`ExecutionHistoryPage.tsx:27`, `SystemLogsPage.tsx:31`, `PMCommandCenter.tsx:24`, y estándar del plan 140 de estados universales) | casi todas | `ExecutionDetailDrawer` usa `"-"` (se unifica a `"—"` al migrar) |

#### F0.e — Test `src/services/format.test.ts` (escribir PRIMERO)

Import: `import { describe, it, expect } from "vitest";` y todas las funciones desde `./format`. Los asserts exactos de fecha/hora usan `tz = "utc"`; para `tz = "local"` solo se testea shape por regex (la zona local de la máquina de CI/dev no es determinista). Tabla de casos NORMATIVA (un `it` por bloque, nombres literales):

| Función | Input | Output EXACTO |
|---|---|---|
| formatDate | `null`, `undefined`, `""`, `"no-es-fecha"` (tz utc) | `"—"` (los 4) |
| formatDate | `"2026-07-03T14:03:27Z"`, utc | `"3 jul 2026"` |
| formatDate | `"2026-12-31T23:59:59Z"`, utc | `"31 dic 2026"` |
| formatTime | `null`, `"x"` | `"—"` |
| formatTime | `"2026-07-03T09:05:07Z"`, utc | `"09:05:07"` |
| formatDateTime | `null`, `"x"` | `"—"` |
| formatDateTime | `"2026-07-03T14:03:27Z"`, utc | `"3 jul 2026 14:03"` |
| formatDateTime | `"2026-01-09T05:07:00Z"`, utc | `"9 ene 2026 05:07"` |
| formatDateTime | `"2026-07-03T14:03:27Z"`, local (default) | matchea `/^\d{1,2} [a-z]{3} \d{4} \d{2}:\d{2}$/` |
| formatDuration | `null`, `undefined`, `NaN`, `-1` | `"—"` (los 4) |
| formatDuration | `0` | `"0ms"` |
| formatDuration | `850` | `"850ms"` |
| formatDuration | `1000` | `"1.0s"` |
| formatDuration | `59_940` | `"59.9s"` |
| formatDuration | `59_960` | `"1m 0s"` |
| formatDuration | `61_000` | `"1m 1s"` |
| formatDuration | `245_000` | `"4m 5s"` |
| formatDuration | `3_600_000` | `"1h 0m"` |
| formatDuration | `5_430_000` | `"1h 30m"` |
| formatDuration | `90_000_000` | `"25h 0m"` |
| formatCostUsd | `null`, `undefined`, `NaN` | `"—"` (los 3) |
| formatCostUsd | `0` | `"$0.00"` |
| formatCostUsd | `0.0042` | `"$0.0042"` |
| formatCostUsd | `0.42` | `"$0.42"` |
| formatCostUsd | `12.5` | `"$12.50"` |
| formatCostUsd | `1234.567` | `"$1234.57"` |
| formatCostUsd | `-0.5` | `"-$0.50"` |
| formatCostUsd | `-0.005` | `"-$0.0050"` |
| formatTokens | `null`, `NaN` | `"—"` |
| formatTokens | `0` | `"0"` |
| formatTokens | `500` | `"500"` |
| formatTokens | `999` | `"999"` |
| formatTokens | `12_345` | `"12.3k"` |
| formatTokens | `1_234_567` | `"1.2M"` |
| formatTokens | `-2500` | `"-2.5k"` |
| formatInt | `null`, `NaN` | `"—"` |
| formatInt | `0` | `"0"` |
| formatInt | `999` | `"999"` |
| formatInt | `12_345` | `"12.345"` |
| formatInt | `1_234_567` | `"1.234.567"` |
| formatInt | `-12_345` | `"-12.345"` |
| formatInt | `1234.9` | `"1.234"` |
| formatBytes | `null`, `NaN`, `-1` | `"—"` (los 3) |
| formatBytes | `0` | `"0 B"` |
| formatBytes | `512` | `"512 B"` |
| formatBytes | `1536` | `"1.5 KB"` |
| formatBytes | `1_048_576` | `"1.0 MB"` |
| formatBytes | `3_221_225_472` | `"3.0 GB"` |
| formatPercent | `null`, `NaN` | `"—"` |
| formatPercent | `85` | `"85%"` |
| formatPercent | `85.34`, decimals `1` | `"85.3%"` |
| formatPercent | `0` | `"0%"` |
| formatPercent | `-5` | `"-5%"` |
| formatRelativeTime (re-export) | `formatRelativeTime("2026-07-17T11:59:30Z", Date.parse("2026-07-17T12:00:00Z"))` | `"recién"` (prueba que el re-export resuelve) |

**Criterio de aceptación (binario):** `npx vitest run src/services/format.test.ts` exit 0 y `npx tsc --noEmit` exit 0. TDD: correr el test ANTES de crear `format.ts` y verificar que falla por módulo inexistente; recién ahí implementar.

**Flag:** sin flag (guardarraíl §3.6). **Impacto por runtime:** idéntico en Codex CLI / Claude Code CLI / GitHub Copilot Pro (presentación web, no toca runtimes). Fallback: N/A. **Trabajo del operador: ninguno.**

---

### F1 — Ratchet `formatDebtRatchet.test.ts` + baseline inicial

**Objetivo:** congelar POR ARCHIVO la cantidad actual de formatters crudos en `src/**` y prohibir que suba. Valor: ningún archivo nuevo o editado puede volver a formatear a mano.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/__tests__/formatDebtRatchet.test.ts`
- GENERAR `Stacky Agents/frontend/src/__tests__/formatDebtBaseline.json` (vía env var, ver abajo)

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/__tests__"` → si hay `M` en archivos que esta fase no crea, STOP.

**Especificación (copiar el patrón EXACTO de `src/__tests__/uiDebtRatchet.test.ts`, incluidas las funciones `countMatches`, `listFiles`, `sortKeys`, `readBaseline`, `assertNoIncrease` y el guard de regen de `uiDebtRatchet.test.ts:104-111`), con estos parámetros:**

- `BASELINE_PATH` = `src/__tests__/formatDebtBaseline.json`; shape `{ "formatByFile": Record<string, number> }`.
- Regex única: `const FORMAT_RE = /\.(toLocaleString|toLocaleDateString|toLocaleTimeString|toFixed)\s*\(/g;`
- Alcance del scan: archivos bajo `src/` cuyo path termina en `.ts` o `.tsx` (rutas normalizadas a `/` como en `uiDebtRatchet.test.ts:37`).
- **Allowlist (excluidos del conteo, único lugar legítimo de esos métodos):** exactamente estos 3 rel-paths: `services/format.ts`, `services/format.test.ts`, `__tests__/formatDebtRatchet.test.ts`. (El tercero es el propio ratchet: se auto-excluye porque su fuente contiene la regex — exclusión explícita, NO ofuscar la regex.)
- Forced-zero (invariante mecánico, igual que `uiDebtRatchet.test.ts:80-82`): archivos bajo `components/ui/` y `components/shell/` tienen permitido 0 SIEMPRE.
- Env var de regen: `FORMAT_DEBT_REGEN` (valor `"1"`), con el mismo guard que rechaza regenerar si algún archivo AUMENTÓ.
- Cabecera del archivo: misma estructura de comentario que `uiDebtRatchet.test.ts:1-12` con los comandos de regen:
  - PowerShell: `$env:FORMAT_DEBT_REGEN='1'; npx vitest run src/__tests__/formatDebtRatchet.test.ts; Remove-Item Env:\FORMAT_DEBT_REGEN`
  - bash: `FORMAT_DEBT_REGEN=1 npx vitest run src/__tests__/formatDebtRatchet.test.ts`
- Mensaje de error de regresión (texto normativo): `format REGRESION en ${file}: ${count} > ${allowed} permitido. La deuda de formato solo puede bajar (plan 161). Importá formatDate/formatDateTime/formatDuration/formatCostUsd/formatTokens/formatInt/formatBytes/formatPercent de services/format en vez de formatear a mano.`
- Tres `it` (mismos títulos adaptados que `uiDebtRatchet.test.ts:98,102,119`): (1) `src/` existe; (2) la deuda por archivo no aumenta respecto del baseline; (3) `components/ui/` y `components/shell/` se mantienen con deuda CERO.

**Generación del baseline inicial:** correr el comando PowerShell de regen de arriba. El JSON resultante se inspecciona: debe contener ≥ 30 entradas (sanity: la evidencia de §2 encontró 39 archivos) y NO contener ninguna clave del allowlist.

**Criterio de aceptación (binario):** (a) `npx vitest run src/__tests__/formatDebtRatchet.test.ts` exit 0 SIN env var; (b) existe `formatDebtBaseline.json` con ≥ 30 claves; (c) ninguna clave del baseline empieza con `services/format` ni es `__tests__/formatDebtRatchet.test.ts`.

**Flag:** sin flag. **Runtimes:** idéntico los 3; fallback N/A. **Trabajo del operador: ninguno.**

---

### F2 — Migración ejemplar 1: Ejecuciones y Logs

**Objetivo:** las 3 superficies donde el operador mira duraciones/costos/timestamps de runs todos los días pasan al canónico. Valor: el mismo run se lee igual en historial, detalle y logs.

**Archivos:** `src/pages/ExecutionHistoryPage.tsx`, `src/components/ExecutionDetailDrawer.tsx`, `src/pages/SystemLogsPage.tsx`.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx" "Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx" "Stacky Agents/frontend/src/pages/SystemLogsPage.tsx"` → si hay `M`, STOP.

**Tabla de reemplazo determinista** (ancla = texto normativo citado; NO dejar funciones locales muertas: se BORRAN):

`ExecutionHistoryPage.tsx`:
1. Agregar al import block: `import { formatDuration, formatCostUsd } from "../services/format";`
2. BORRAR la función local `fmtDuration` (ancla: `function fmtDuration(ms: number | null): string`, hoy :26-34) y reemplazar TODOS sus call-sites por `formatDuration(...)` con el mismo argumento.
3. BORRAR la función local `fmtCost` (ancla: `function fmtCost(cost: number | null): string`, hoy :36-39) y reemplazar sus call-sites por `formatCostUsd(...)`.
4. NO tocar el import existente de `formatRelativeTime` (guardarraíl §3.10).

`ExecutionDetailDrawer.tsx`:
1. Agregar: `import { formatDuration as formatDurationCanonical, formatCostUsd, formatInt } from "../services/format";` — el alias evita colisión mientras se edita; al final la local se borra y el alias se puede simplificar a import directo `formatDuration` (elegir UNA de las dos formas y compilar).
2. BORRAR la local `formatDuration` (ancla: `function formatDuration(durationMs?: number | null): string`, hoy :20-25); call-sites → canónica. Cambio visual congelado: `"2.5m"` → `"2m 30s"`; marcador `"-"` → `"—"`.
3. En `formatMaybeCurrency` (ancla: `function formatMaybeCurrency(value: unknown): string`, hoy :27-32): conservar la función (su guard de `unknown` es dominio del drawer) pero el cuerpo pasa a: `if (value == null) return "—"; const n = Number(value); if (Number.isFinite(n)) return formatCostUsd(n); return String(value);`
4. En la local `formatTokens` (ancla: `function formatTokens(value: unknown): string`, hoy :34-39): conservar guard, cuerpo numérico → `return formatInt(n);` y marcador `"—"`. Cambio visual congelado: separador de miles ya no depende del navegador.

`SystemLogsPage.tsx`:
1. Agregar: `import { formatDate, formatTime, formatDuration, formatInt } from "../services/format";`
2. `fmtTs` (ancla: `function fmtTs(ts: string): string`, hoy :21-28): cuerpo pasa a componer fecha+hora CON segundos (los segundos importan en logs): `const d = formatDate(ts); return d === "—" ? "—" : `${d} ${formatTime(ts)}`;`
3. BORRAR `fmtMs` (ancla: `function fmtMs(ms: number | null): string`, hoy :30-34); call-sites → `formatDuration(...)`.
4. Ancla `Total {stats.total.toLocaleString()}` (hoy :205) → `Total {formatInt(stats.total)}`.
5. Ancla `{total.toLocaleString()} total events` (hoy :370) → `{formatInt(total)} total events`.

**Criterio de aceptación (binario):** (a) `npx tsc --noEmit` exit 0; (b) `npx vitest run src/__tests__/formatDebtRatchet.test.ts` exit 0; (c) `npx vitest run src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts` exit 0; (d) el conteo de `FORMAT_RE` en los 3 archivos es 0 — verificable porque el ratchet en modo normal pasa y, tras el regen de F5, esos archivos desaparecen del baseline.

**Flag:** sin flag. **Runtimes:** idéntico los 3; fallback N/A. **Trabajo del operador: ninguno.** Smoke manual documentado (no bloqueante): abrir Historial de Ejecuciones y Logs del Sistema, confirmar que duraciones se ven `4m 5s` y costos `$0.0042`/`$1.23`.

---

### F3 — Migración ejemplar 2: PM Command Center

**Objetivo:** la superficie con MÁS formatters crudos del repo (19 matches, `src/pages/PMCommandCenter.tsx`) pasa al canónico. Valor: KPIs, timestamps y costos del tablero PM coherentes con el resto de la app.

**Archivo:** `src/pages/PMCommandCenter.tsx`. **Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/PMCommandCenter.tsx"` → si hay `M`, STOP.

Import a agregar: `import { formatDate, formatTime, formatDateTime, formatDuration, formatCostUsd, formatTokens, formatPercent } from "../services/format";`

**Tabla de reemplazo determinista:**

| # | Ancla normativa (hoy :NN) | Reemplazo |
|---|---|---|
| 1 | `function fmtDate(iso: string | null | undefined): string` (:23-34) | BORRAR la local; call-sites → `formatDate(iso)`. Cambio congelado: iso inválido → `"—"` (antes devolvía el iso crudo) |
| 2 | `function fmtDateTime(iso: string | null | undefined): string` (:36-43) | BORRAR la local; call-sites → `formatDateTime(iso)` |
| 3 | `` `${kpis.completion_rate_pct.toFixed(0)}%` `` (:114) | `formatPercent(kpis.completion_rate_pct)` |
| 4 | `` `${kpis.bug_rate_pct.toFixed(1)}% del sprint` `` (:135) | `` `${formatPercent(kpis.bug_rate_pct, 1)} del sprint` `` |
| 5 | función local de tokens compactos (ancla `if (n >= 1_000_000) return`, :234-235) | BORRAR la local; call-sites → `formatTokens(n)`. Cambio congelado: M pasa de 2 a 1 decimal |
| 6 | función local de USD escalonado (ancla `if (usd < 0.01) return`, :241-243) | BORRAR la local; call-sites → `formatCostUsd(usd)`. Cambio congelado: desaparece el tier de 3 decimales |
| 7 | `` `${((data.success / data.calls) * 100).toFixed(0)}%` `` (:267) | `formatPercent((data.success / data.calls) * 100)` |
| 8 | `new Date(report.window_start).toLocaleString("es-AR")` (:279) | `formatDateTime(report.window_start)` |
| 9 | `` `${totals.success_rate_pct.toFixed(0)}%` `` (:314) | `formatPercent(totals.success_rate_pct)` |
| 10 | `` `${(totals.latency_ms_avg / 1000).toFixed(1)}s` `` (:323) | `formatDuration(totals.latency_ms_avg)` |
| 11 | `new Date(r.timestamp).toLocaleTimeString("es-AR", { hour12: false })` (:380) | `formatTime(r.timestamp)` |
| 12 | `(r.confidence * 100).toFixed(0)` en `conf ...%` (:614) | `` `conf ${formatPercent(r.confidence * 100)}` `` (quitando el `%` literal que quedaba afuera) |
| 13 | `(c.sentiment_score * 100).toFixed(0)` en sentimiento (:782) | `formatPercent(c.sentiment_score * 100)` (quitando el `%` literal externo) |

**NO migrar (deuda residual congelada, ≤ 4 matches):** `avg_aging_days`/`avg_cycle_time_days` con sufijo `d` (:143, :147 — unidad de dominio en días, no es duración en ms) y la notación de pricing `($X.XX/X.XX per 1M)` (:435 — tabla de precios por millón, notación de dominio). Los comentarios que se escriban en este archivo NO deben nombrar los métodos crudos (guardarraíl §3.8).

**Criterio de aceptación (binario):** (a) `npx tsc --noEmit` exit 0; (b) `npx vitest run src/__tests__/formatDebtRatchet.test.ts` exit 0; (c) tras el regen de F5, `pages/PMCommandCenter.tsx` figura en el baseline con ≤ 4.

**Flag:** sin flag. **Runtimes:** idéntico los 3; fallback N/A. **Trabajo del operador: ninguno.** Smoke manual documentado: abrir PM Command Center, verificar KPIs con `%` y fechas `16 jul 2026 14:03`.

---

### F4 — Migración ejemplar 3: Centro de Costos (delegación, contrato 142 intacto)

**Objetivo:** el Centro de Costos (plan 142) delega su formateo al canónico SIN romper su contrato público (`"n/d"` y reglas testeadas en `src/lib/__tests__/costCenter.logic.test.ts:33-47`). Valor: la superficie insignia de costos y el resto de la app quedan garantizados-idénticos por construcción.

**Archivos:** `src/lib/costCenter.logic.ts`, `src/components/CostPreview.tsx`, `src/components/CostCapIndicator.tsx`.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/lib/costCenter.logic.ts" "Stacky Agents/frontend/src/components/CostPreview.tsx" "Stacky Agents/frontend/src/components/CostCapIndicator.tsx"` → si hay `M`, STOP.

`costCenter.logic.ts`:
1. Agregar import (con alias obligatorio, hay colisión de nombre): `import { formatCostUsd, formatTokens as formatTokensCanonical } from "../services/format";`
2. Cuerpo de `formatUsd` (ancla `export function formatUsd(n: number | null): string`, hoy :9-12) → `if (n === null || n === undefined || Number.isNaN(n)) return "n/d"; return formatCostUsd(n);` — el test existente `formatUsd(0.42) === "$0.42"` (`costCenter.logic.test.ts:35`) sigue verde porque el canónico da 2 decimales para ≥ $0.01.
3. Cuerpo de `formatTokens` (ancla `export function formatTokens(n: number | null): string`, hoy :14-20) → `if (n === null || n === undefined || Number.isNaN(n)) return "n/d"; return formatTokensCanonical(n);` — reglas idénticas por §4.F0.c.7, tests :38-42 siguen verdes.
4. `formatPct` (:22-25) NO se toca (ratio 0–1, contrato propio del 142, sin literales gateados).

`CostPreview.tsx`:
1. Import: `import { formatCostUsd, formatDuration, formatTokens } from "../services/format";`
2. Ancla `` `$${estimate.cost_usd_total.toFixed(2)}` `` (:72) → `formatCostUsd(estimate.cost_usd_total)`.
3. Ancla `` `${(estimate.latency_ms / 1000).toFixed(1)}s` `` (:75) → `formatDuration(estimate.latency_ms)`.
4. Ancla `{(estimate.tokens_in / 1000).toFixed(1)}k → {(estimate.tokens_out / 1000).toFixed(1)}k tok` (:80) → `{formatTokens(estimate.tokens_in)} → {formatTokens(estimate.tokens_out)} tok`. Cambio congelado: valores < 1000 se ven `500` en vez de `0.5k`.

`CostCapIndicator.tsx`:
1. Import: `import { formatCostUsd, formatPercent } from "../services/format";`
2. Ancla del title (hoy :53) → `` const title = `Costo mensual: ${formatCostUsd(data.spent_usd)} / ${formatCostUsd(data.monthly_cap_usd)} (${formatPercent(data.spent_pct)})`; ``
3. Ancla del badge compacto (hoy :58) → `{formatCostUsd(data.spent_usd)}/{Math.round(data.monthly_cap_usd)}` (el cap del badge queda entero adrede para no ensanchar el chip).

**Criterio de aceptación (binario):** (a) `npx vitest run src/lib/__tests__/costCenter.logic.test.ts` exit 0 SIN modificar ese test; (b) `npx tsc --noEmit` exit 0; (c) `npx vitest run src/__tests__/formatDebtRatchet.test.ts` exit 0.

**Flag:** sin flag. **Runtimes:** idéntico los 3; fallback N/A. **Trabajo del operador: ninguno.** Smoke manual documentado: abrir Centro de Costos y comparar un mismo run contra el Historial — el costo debe verse IDÉNTICO.

---

### F5 — Regeneración del baseline (lock de la deuda bajada) + verificación global

**Objetivo:** congelar la deuda REDUCIDA por F2-F4 para que no pueda volver a subir, y correr la batería completa. Valor: cierre verificable del plan.

**Pasos:**
1. Regenerar baseline: `$env:FORMAT_DEBT_REGEN='1'; npx vitest run src/__tests__/formatDebtRatchet.test.ts; Remove-Item Env:\FORMAT_DEBT_REGEN` (el guard interno rechaza si algo subió).
2. Verificar en `src/__tests__/formatDebtBaseline.json`: ausentes `pages/ExecutionHistoryPage.tsx`, `components/ExecutionDetailDrawer.tsx`, `pages/SystemLogsPage.tsx`, `lib/costCenter.logic.ts`, `components/CostPreview.tsx`, `components/CostCapIndicator.tsx`; presente `pages/PMCommandCenter.tsx` con valor ≤ 4.
3. Batería completa, POR ARCHIVO, en este orden:
   - `npx vitest run src/services/format.test.ts`
   - `npx vitest run src/__tests__/formatDebtRatchet.test.ts`
   - `npx vitest run src/lib/__tests__/costCenter.logic.test.ts`
   - `npx vitest run src/utils/__tests__/formatRelativeTime.test.ts`
   - `npx vitest run src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts`
   - `npx vitest run src/pages/__tests__/DocsPage.adoption.test.ts`
   - `npx vitest run src/pages/__tests__/ReviewInboxPage.adoption.test.ts`
   - `npx vitest run src/__tests__/uiDebtRatchet.test.ts`
   - `npx vitest run src/__tests__/motionDebtRatchet.test.ts`
   - `npx tsc --noEmit`

**Criterio de aceptación (binario):** los 10 comandos exit 0 y el punto 2 se cumple literal. **Flag:** sin flag. **Runtimes:** idéntico los 3; fallback N/A. **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Cambio visual percibido al converger formatos (ej. `$0.420`→`$0.42`, `2.5m`→`2m 30s`) | Canónico elegido por regla mayoritaria (§4.F0.d); cada cambio visual está CONGELADO y listado en su fase; smokes manuales documentados por fase (no bloqueantes) |
| R2 | El ratchet bloquea un PR futuro legítimo | El mensaje de error nombra las funciones canónicas a usar; regen documentado en la cabecera del test (solo cuando la deuda BAJÓ, guard automático anti-suba) |
| R3 | Colisión con planes CRITICADOS pendientes (150/151/152/157) que tocan los mismos archivos | Pre-flight `git status --porcelain` por archivo en CADA fase (STOP si hay WIP ajeno); el ratchet es solo-baja: si esos planes usan el canónico no los afecta, y si agregan formatter crudo el ratchet los detecta — comportamiento deseado |
| R4 | Gotcha prosa-vs-gate (6+ ocurrencias en la casa) | Allowlist explícito de 3 archivos; prohibición §3.8 de nombrar los métodos crudos en comentarios de archivos migrados; el ratchet solo escanea `frontend/src`, nunca `docs/` |
| R5 | Romper el contrato del plan 142 (`costCenter.logic`) | Delegación con wrappers que preservan `"n/d"`; reglas de tokens copiadas idénticas (§4.F0.c.7); criterio F4.a exige el test de 142 verde SIN modificarlo |
| R6 | Tests de fecha no deterministas por zona horaria de la máquina | Parámetro `tz: "local" | "utc"` (default local en runtime); asserts exactos solo con `"utc"`; `"local"` se testea por shape/regex — mismo patrón de inyección que `formatRelativeTime.ts:15` con `nowMs` |
| R7 | Test-order pollution de vitest (gotcha conocido del repo) | Todos los comandos son POR ARCHIVO; nunca `npx vitest run` completo |
| R8 | Edge cosmético heredado: `formatTokens(999_999)` → `"1000.0k"` | Heredado tal cual del contrato 142 (`costCenter.logic.ts:17-18`) a propósito: la igualdad de reglas es prerequisito de la delegación de F4; queda documentado como edge conocido, no corregirlo en este plan |

## 6. Fuera de scope

- **Semántica de datos del backend.** Este plan es SOLO capa de presentación frontend. En particular NO corrige el gotcha conocido de telemetría legacy donde `cost_estimated` (bool) se serializó como float — eso fue el plan 158 (fix de telemetría de costos `claude_code_cli`) de esta misma rama. Si un número llega mal del backend, acá se formatea bonito un número que sigue mal.
- Migración de las ~32 superficies restantes con formatters crudos (quedan congeladas en baseline; migran oportunistamente bajo presión del ratchet).
- i18n/l10n real (multi-idioma/multi-locale). Stacky es mono-operador; el canónico es español rioplatense fijo.
- El CSV de exportación del Centro de Costos (`costCenter.logic.ts`, funciones de CSV) — es formato de DATOS, no de presentación.
- La precisión de 2 decimales del timeline de `ReplayPlayer.tsx:145` (dominio del player, queda en baseline).
- Instalar RTL/jsdom (gap estructural conocido); lo visual se cubre con tsc + smokes manuales documentados, como en 138-143.
- Cualquier flag/config nueva de operador (no hay ninguna).

## 7. Glosario, orden de implementación y DoD

**Glosario:**
- **Formatter crudo:** llamada directa a un método nativo de formateo numérico/fecha en código de UI, fuera del módulo canónico.
- **Módulo canónico:** `src/services/format.ts`, único origen autorizado de strings de presentación para fechas, duraciones, costos, tokens, enteros, bytes y porcentajes.
- **Ratchet:** test vitest fs+regex que congela un conteo por archivo en un baseline JSON y solo permite que baje (patrón planes 138/143).
- **Baseline:** `src/__tests__/formatDebtBaseline.json`, snapshot commiteado de la deuda por archivo.
- **Marcador vacío:** string para dato ausente/ inválido; canónico `"—"` (em dash); `costCenter.logic` conserva `"n/d"` por contrato del plan 142.
- **Superficie:** página o componente visible del frontend (ej. Centro de Costos, Historial de Ejecuciones).
- **Runtime:** motor de ejecución de agentes de Stacky (Codex CLI, Claude Code CLI, GitHub Copilot Pro); este plan no los toca.
- **Match:** ocurrencia individual de la regex del ratchet dentro de un archivo (`countMatches` cuenta matches, no líneas).

**Orden de implementación:** F0 → F1 → F2 → F3 → F4 → F5 (estricto; F1 requiere el allowlist de F0 ya existente; F5 requiere las migraciones hechas). El implementador NO commitea: eso lo hace el orquestador al cierre.

**Definición de Hecho (DoD) global:**
1. K1–K5 de §1 verdes con output real pegado (cero falsos verdes: el verificador corre los comandos y LEE el output).
2. Los 10 comandos de F5.3 exit 0.
3. `formatDebtBaseline.json` commiteado cumpliendo F5.2 literal.
4. Ningún archivo fuera del allowlist ganó matches de la regex del ratchet respecto del baseline inicial de F1.
5. `git status` final sin tocar archivos fuera de los listados en las fases.
6. Smokes manuales de F2/F3/F4 documentados como pendientes para el operador solo a título informativo (no bloquean el cierre; precedente 134-136).
