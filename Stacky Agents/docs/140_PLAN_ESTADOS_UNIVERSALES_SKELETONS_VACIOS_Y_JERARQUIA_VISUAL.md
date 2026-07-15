# Plan 140 — Estados universales: skeletons de carga, vacíos accionables y jerarquía visual de datos

**Estado:** CRITICADO v1→v2 · **VEREDICTO: APROBADO-CON-CAMBIOS** (2026-07-15) — v1 propuesto 2026-07-15
**Autor:** StackyArchitectaUltraEficientCode (perfil normal)
**Depende de:** Plan 138 (tokens semánticos + primitivas `ui/`) IMPLEMENTADO y mergeado; Plan 139 (siguiente en la serie) aterriza antes.
**Se implementa DESPUÉS de:** 138 y 139.
**Aterrizan ANTES (orden congelado por 134 v2 §3.3):** 132 → 134 → 135 → 136.
**Deslinde duro:** el canal de ERROR (LoadErrorState, error≠vacío, ErrorBoundary, Toast, retry) es 100% del Plan 135. Este plan NO toca errores.

> Este documento está escrito para que un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) lo
> implemente **sin inferir nada**. Cada fase trae archivos exactos, símbolos exactos, copys literales,
> tests primero con comando exacto y criterio de aceptación binario. Si algo no está escrito acá,
> **NO lo inventes**: parás y preguntás al operador.

---

## § 0. Changelog de crítica v1 → v2 (juez adversarial, 2026-07-15)

Veredicto: **APROBADO-CON-CAMBIOS** (0 bloqueantes; 1 IMPORTANTE; 2 MENORES). Plan sólido:
helpers puros con casos frontera exactos, gate STOP droppable en F8, deslinde 135 claro.

- **C1 (IMPORTANTE) — resuelto in place [ADICIÓN ARQUITECTO].** *Trampa vacío-vs-error.* El
  branch de VACÍO (`items.length === 0`) TAMBIÉN captura el caso de ERROR (una query que falla
  suele devolver 0 elementos). El v1 mapeaba `length===0 → <EmptyState "no hay datos">`, así
  que **un fetch fallido renderiza un falso vacío** ("Sin historial todavía", con copy que
  AFIRMA que no hay datos) — engañando al operador y siendo, encima, MÁS engañoso que el texto
  plano que reemplaza. Fix (respeta el deslinde con 135, NO implementa UI de error): el
  `EmptyState` de vacío se renderiza **sólo** cuando la query resolvió OK con 0 elementos —
  `!<query>.isError && length===0`. En estado de error NO se muestra EmptyState; ese canal es
  del Plan 135. Aplicado a F4/F5/F6/F8 (regla global en §10.7) + añadido a los tests de adopción.
- **C2 (MENOR) — documentado.** F3 reemplaza el botón crudo de `EmptyState` (que hoy renderiza
  `▶ {finalAction}` vía `.action`) por la primitiva `Button` primaria: se pierde el glifo `▶` y
  cambia el estilo de acción de las variantes existentes (`executions/packs/tickets`).
  Verificado: **0 importadores actuales del compartido** (§3.1) ⇒ nada en producción se rompe;
  es una mejora de jerarquía, intencional y reversible por revert.
- **C3 (MENOR) — mitigado.** Los tests fs+regex de adopción no observan el render (no hay
  RTL/jsdom); combinados con C1 pasarían aun con el falso-vacío. Se agrega a los tests de F4/F5
  la verificación de que el branch de vacío referencia el guard `isError` (patrón textual).

139/138/141 sin cambios por esta crítica.

---

## § 1. Glosario

| Término | Significado exacto en este plan |
|---|---|
| **Estado no-feliz de presentación** | Cualquier estado de una superficie que NO es "datos cargados y visibles": (a) CARGA, (b) VACÍO real, (c) el chip/timestamp con que se presentan los datos. NO incluye ERROR (eso es 135). |
| **CARGA** | La query aún no resolvió (`isLoading === true`). Hoy se muestra texto plano tipo "Cargando…" o pantalla en blanco. Objetivo: skeleton. |
| **VACÍO real** | La query resolvió OK y devolvió 0 elementos (no es error). Objetivo: `EmptyState` compartido con copy accionable. |
| **Skeleton** | Primitiva `Skeleton` del Plan 138 (`components/ui/Skeleton.tsx`). Bloque gris animado que ocupa el lugar del contenido mientras carga. |
| **StatusChip** | Primitiva `StatusChip` del Plan 138 (`components/ui/StatusChip.tsx`). Chip de estado con `tone` ∈ {success, warning, danger, info, neutral}. |
| **EmptyState (compartido)** | `frontend/src/components/EmptyState.tsx` — YA EXISTE con presets; hoy tiene **cero importadores reales** (ver §3.1). Este plan lo adopta y extiende. |
| **SkeletonList** | Componente nuevo que crea este plan: composición fina sobre `Skeleton` para renderizar N barras apiladas (lista/tabla cargando). |
| **Superficie** | Una página o sección concreta que muestra una lista/tabla de datos. |
| **Tono (tone)** | Uno de los 5 valores de `StatusChip.tone`. Ver tabla congelada §6. |
| **Helper puro** | Función sin efectos, sin React, testeable con vitest sin DOM. |
| **fs+regex test** | Test que lee el archivo fuente con `fs.readFileSync(...)` y verifica su contenido con regex. Es el único modo de "test de adopción" disponible (no hay `@testing-library/react` ni `jsdom`, ver §2). |

---

## § 2. Restricciones NO negociables (aplican a TODAS las fases)

1. **3 runtimes con paridad total.** Todo lo de este plan es **presentación frontend pura, runtime-agnóstica**. No hay ramas por runtime, no hay backend, no hay cambio de contrato de datos. Los estados (`running/completed/error/needs_review/…`) y los timestamps ISO llegan idénticos desde el backend para Codex, Claude Code y GitHub Copilot Pro. **Impacto por runtime = ninguno; fallback = N/A** (se declara igual en cada fase).
2. **Cero trabajo del operador.** No se agrega ninguna flag de harness (justificación en §8). No hay nada que configurar. Reversible con `git revert` de los commits de la fase.
3. **Human-in-the-loop; mono-operador sin auth.** No se agregan permisos, roles ni gates. No se toca nada de autenticación.
4. **No degradar performance.** Los skeletons **no agregan requests, ni timers, ni intervalos, ni polling**. `Skeleton` (138) anima por CSS. `SkeletonList` renderiza un número fijo y pequeño de `<div>` estáticos. `formatRelativeTime` y `runStatus*` son O(1) puros llamados en render (igual que los helpers ad-hoc que reemplazan). Se declara por fase.
5. **No degradar DX.** No se agregan dependencias: **`package.json` NO se toca** (queda `git status -- "Stacky Agents/frontend/package.json"` limpio).
6. **Backward-compatible.** Todas las firmas nuevas son aditivas. `EmptyState` conserva sus props actuales; sólo se agregan variantes y se cambia el render interno del botón de acción por la primitiva `Button`.
7. **Sin @testing-library/react ni jsdom** (confirmado: no están en `frontend/package.json`). Los tests son (a) funciones puras con vitest, o (b) fs+regex calcando el precedente `frontend/src/pages/__tests__/DevOpsPage.test.ts:42-51`. **PROHIBIDO** escribir tests con RTL/`render()`.
8. **Sólo consumir el contrato del 138 por nombre exacto.** PROHIBIDO redefinir tokens o primitivas. Ver §5.
9. **PROHIBIDO** crear Toast, LoadErrorState o ErrorBoundary (dominio 135). PROHIBIDO agregar hex nuevos en `.module.css` o `style={{ }}` inline en `.tsx` (rompería el ratchet del 138, §5.3). Todo color va por token `--status-*`/`--space-*`/etc.

---

## § 3. Contexto y evidencia (estado actual, archivo:línea real)

### 3.1 `EmptyState` compartido: existe pero NADIE lo importa

- `frontend/src/components/EmptyState.tsx:1-90` — componente con presets `executions | packs | tickets | agents | history | generic` (`EmptyState.tsx:4-10`, `21-61`), props `variant/title/message/actionLabel/onAction/icon` (`:12-19`), y botón de acción crudo `<button className={styles.action}>` (`:84`).
- **Grep de importadores del compartido** (`import ... from ".../components/EmptyState"`): **0 resultados**. Su adopción real es cero.
- El único archivo que "usa" el nombre `EmptyState` es `frontend/src/pages/TeamScreen.tsx:205`, pero es una **función LOCAL homónima** (`function EmptyState({ onAdd })`) que **duplica** el patrón con su propio CSS `styles.empty` — NO importa el compartido. TeamScreen además tiene `NoProjectState` (`TeamScreen.tsx:193-203`), otra duplicación de vacío.

### 3.2 CARGA: hoy texto plano o blanco (no skeleton), superficie por superficie

| Superficie | Archivo:línea | Cómo carga HOY |
|---|---|---|
| Historial de ejecuciones | `pages/ExecutionHistoryPage.tsx:178-179` | `<div className={styles.empty}>Cargando historial…</div>` |
| Bandeja de revisión | `pages/ReviewInboxPage.tsx:98` | `<div className={styles.empty}>Cargando ejecuciones…</div>` |
| Documentación | `pages/DocsPage.tsx:265` | `<p>Cargando documentación...</p>` |
| Tablero de tickets (lista) | `pages/TicketBoard.tsx:1010` | `<div className={styles.loading}>Cargando jerarquía…</div>` |
| Mi Equipo | `pages/TeamScreen.tsx:139-144` | Ya hay un skeleton **hand-rolled**: 4 `<div className={styles.skeletonCard} aria-hidden />`. Se migrará a la primitiva `Skeleton`. |

### 3.3 VACÍO: cada superficie inventa su propio "no hay datos" (ninguna usa el compartido)

| Superficie | Archivo:línea | Vacío HOY |
|---|---|---|
| Historial | `ExecutionHistoryPage.tsx:180-181` | `<div className={styles.empty}>Sin ejecuciones</div>` |
| Revisión | `ReviewInboxPage.tsx:99-101` | `<div className={styles.empty}>No hay ejecuciones pendientes de revisión.</div>` |
| Docs | `DocsPage.tsx:331` | `<div className={styles.emptyState}>…</div>` (local) |
| Tickets | `TicketBoard.tsx:1011-1013` | `<div className={styles.empty}>No hay tickets. Hacé clic en «Sincronizar ADO».</div>` |
| Equipo (vacío) | `TeamScreen.tsx:205-218` | `EmptyState` LOCAL |
| Equipo (sin proyecto) | `TeamScreen.tsx:193-203` | `NoProjectState` LOCAL |

### 3.4 DATOS — chips de estado: 3+ implementaciones con hex propios e inconsistentes

- `ExecutionHistoryPage.tsx:41-47` `statusClass()` → clases CSS `statusCompleted/statusError/statusReview/statusRunning`.
- `ExecutionHistoryPage.module.css:125-143` — esas clases usan **hex de tema CLARO** (`#d1fae5`/`#065f46`, `#fee2e2`/`#991b1b`, `#fef3c7`/`#92400e`, `#dbeafe`/`#1e40af`) — visualmente **inconsistentes con el dark theme** de la app.
- `ReviewInboxPage.tsx:121-123` — otro badge con clases locales `styles.error`/`styles.review`.
- (Zona 134, NO se toca) `components/ActiveRunsPanel.tsx` y `pages/TicketBoard.tsx:359` (`style={{ background: "rgba(245,158,11,0.18)", … }}`) renderizan "running" con su propio color inline.

### 3.5 DATOS — timestamps: 3 implementaciones distintas y crudas

| Impl | Archivo:línea | Reglas |
|---|---|---|
| `fmtDate` (absoluto) | `ExecutionHistoryPage.tsx:35-39` | `new Date(iso).toLocaleString()` — locale/timezone no determinista. |
| `timeAgo` (relativo) | `ReviewInboxPage.tsx:21-32` | "ahora" / "hace Nm" / "hace Nh" / "hace Nd". |
| `relativeTimeEs` (relativo) | `components/dbcompare/relativeTime.ts:4-19` (Plan 124 F6) | "hace segundos" / "hace N min" / "hace N h" / "hace N d". **Nunca** cae a fecha absoluta. |
| ad hoc | `DocsPage.tsx:347` | `new Date(indexData.indexed_at).toLocaleTimeString()`. |

`dbcompare/relativeTime.ts` queda **fuera de scope** (código mergeado de 124; ver §12). Este plan crea el helper canónico y lo adopta en superficies limpias.

### 3.6 Infra de tests disponible

- No hay RTL/jsdom (§2.7). Precedente fs+regex real: `frontend/src/pages/__tests__/DevOpsPage.test.ts:42-51` usa `fs.readFileSync('N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DevOpsPage.tsx','utf-8')` + `regex.test(content)`. **Calcá ese patrón.**
- Helpers puros viven en `frontend/src/utils/` (ya existen `agentCompletionErrors.ts`, `trackerUrls.ts`, `resolveSuggestedAgent.ts`, `inconsistencyDetector.ts`, `workItemTypeColor.ts`).
- Tests de utils: convención `frontend/src/utils/__tests__/<name>.test.ts` (ver `utils/__tests__/inconsistencyDetector.test.ts`).

---

## § 4. Objetivo y KPIs

**Objetivo:** estandarizar los 3 estados no-felices de presentación de datos (CARGA, VACÍO, DATOS) en las superficies principales, consumiendo las primitivas del 138, sin tocar el canal de error (135) ni agregar trabajo al operador.

**KPIs binarios (se verifican en F9):**
- KPI-1: **≥ 4** superficies principales muestran skeleton (primitiva `Skeleton` vía `SkeletonList` o `Skeleton` directo) en CARGA, en vez de texto plano / blanco.
- KPI-2: **0** vacíos ad-hoc en las superficies tocadas: todas usan el `EmptyState` compartido (grep de importadores del compartido pasa de 0 a **≥ 4**).
- KPI-3: **1** helper canónico de estado (`runStatus.ts`) adoptado en **≥ 2** superficies; **0** `statusClass`/badge-hex propios en las superficies tocadas.
- KPI-4: **1** helper canónico de tiempo (`formatRelativeTime.ts`) adoptado en **≥ 2** superficies; **0** `toLocaleString`/`toLocaleTimeString`/`timeAgo` local en las superficies tocadas.
- KPI-5: `npx tsc --noEmit` = 0 errores; todos los tests nuevos verdes; ratchet del 138 sin regresión.

---

## § 5. Contrato del Plan 138 que este plan CONSUME (solo por nombre exacto)

### 5.1 Primitivas (todas en `frontend/src/components/ui/`, re-exportadas por `ui/index.ts`)

| Primitiva | Import | Firma relevante (138 §10.2) |
|---|---|---|
| `Skeleton` | `from "../components/ui"` (desde pages) / `from "./ui"` (desde components) | `{ width?: number\|string; height?: number\|string; radius?: number\|string; lines?: number; className?: string }`. Defaults `width="100%"`, `height=14`, `radius="var(--radius-sm)"`, `lines=1`. Internamente usa `style={skeletonStyle(...)}` (una llave → **no** cuenta para el ratchet inline). |
| `StatusChip` | idem | `{ tone: "success"\|"warning"\|"danger"\|"info"\|"neutral"; children: ReactNode; icon?: ReactNode; size?: "sm"\|"md"; title?: string }`. Default `size="sm"`. |
| `Button` | idem | `{ variant?: "primary"\|"secondary"\|"ghost"\|"danger"; size?: "sm"\|"md"; loading?: boolean; iconLeft?; iconRight? } & ButtonHTMLAttributes`. Default `variant="secondary"`, `size="md"`, `type="button"`. |

### 5.2 Tokens (consumir por nombre, NO redefinir) — 138 §10.1

Usados por este plan: `--status-{success,warning,danger,info,neutral}-*` (los aplica `StatusChip` internamente, este plan **no** los toca), `--space-1..9`, `--radius-{xs,sm,md,lg,full}`, `--duration-{fast,base,slow}`. En CSS nuevo de este plan **solo** se referencian por `var(--…)`.

### 5.3 Ratchet del 138 (no regresar) — 138 §10.3

- Test `frontend/src/__tests__/uiDebtRatchet.test.ts` con baseline `uiDebtBaseline.json`.
- Regex: hex `/#[0-9a-fA-F]{3,8}\b/g` sobre `*.module.css`; inline `/style=\{\{/g` sobre `*.tsx`. Contador por archivo **≤ baseline**. `components/ui/**` siempre 0.
- **Regla de oro de este plan:** no introducir NI un hex nuevo en `.module.css` NI un `style={{` nuevo en `.tsx`. Al reemplazar chips propios por `StatusChip`, se **borran** las clases hex muertas (baja el contador ⇒ el ratchet sigue verde sin regenerar baseline).

---

## § 6. Tabla congelada: estado de run/ticket → `StatusChip.tone` + etiqueta

`StatusChip.tone` solo acepta 5 valores. Mapeo canónico (implementado en F1, `utils/runStatus.ts`). La clave se normaliza con `String(status).trim().toLowerCase()` antes de buscar.

| status (normalizado) | tone | label (ES) |
|---|---|---|
| `completed` | `success` | Completado |
| `success` | `success` | Completado |
| `done` | `success` | Completado |
| `running` | `info` | En ejecución |
| `in_progress` | `info` | En ejecución |
| `pending` | `neutral` | Pendiente |
| `queued` | `neutral` | En cola |
| `needs_review` | `warning` | Requiere revisión |
| `review` | `warning` | Requiere revisión |
| `error` | `danger` | Error |
| `failed` | `danger` | Error |
| `cancelled` | `neutral` | Cancelado |
| `canceled` | `neutral` | Cancelado |
| *(cualquier otro / vacío)* | `neutral` | *(el status crudo tal cual llegó; si viene vacío → "—")* |

> Nota: aunque exista un status de "error", este chip es sólo **presentación de color**. El manejo de error como estado de página (mensaje, retry) es 135. Un chip `danger` no es un LoadErrorState.

---

## § 7. Lista congelada: superficie → skeleton (forma exacta)

| # | Superficie | Archivo | Forma de skeleton | Reemplaza |
|---|---|---|---|---|
| S1 | Historial de ejecuciones (tabla) | `pages/ExecutionHistoryPage.tsx` | `<SkeletonList rows={8} rowHeight={28} />` dentro de `styles.tableWrapper` | `Cargando historial…` (`:178-179`) |
| S2 | Bandeja de revisión (tabla) | `pages/ReviewInboxPage.tsx` | `<SkeletonList rows={6} rowHeight={28} />` | `Cargando ejecuciones…` (`:98`) |
| S3 | Documentación (panel de contenido) | `pages/DocsPage.tsx` | `<SkeletonList rows={6} rowHeight={20} />` en el bloque de carga de contenido | `Cargando documentación...` (`:265`) |
| S4 | Tablero de tickets (lista jerárquica) | `pages/TicketBoard.tsx` | `<SkeletonList rows={6} rowHeight={44} />` **solo** en la carga de la lista (`:1010`) | `Cargando jerarquía…` (`:1010`) — **zona-gated, ver §9** |
| S5 | Mi Equipo (grid de tarjetas) | `pages/TeamScreen.tsx` | 4 × `<Skeleton height={120} radius="var(--radius-lg)" />` dentro de `styles.loadingGrid` | 4 × `div.skeletonCard` hand-rolled (`:141-143`) |

> S1..S4 usan el componente compuesto `SkeletonList` (F2). S5 usa la primitiva `Skeleton` directa (es un grid, no una lista vertical).

---

## § 8. Tabla congelada: superficie → `EmptyState` (variante + copy LITERAL)

Los copys van **literales** en el doc; el implementador los pega tal cual. Variantes nuevas (`review`, `docs`, `no_project`) se agregan en F3; el resto ya existe.

| Superficie | variant | title (literal) | message (literal) | actionLabel / onAction |
|---|---|---|---|---|
| Historial (S1) | `history` *(existente)* | Sin historial todavía | Cuando corras agentes, el historial va a aparecer acá. | — (sin acción) |
| Revisión (S2) | `review` *(NUEVA)* | Bandeja al día | No hay ejecuciones que requieran tu revisión. Cuando un agente termine con dudas o error, va a aparecer acá. | — (sin acción) |
| Docs (S3) | `docs` *(NUEVA)* | Sin documentación indexada | Todavía no hay documentos para explorar. Indexá el proyecto para ver el grafo y buscar contenido. | actionLabel `Indexar ahora` **solo si** DocsPage ya tiene un handler de reindex accesible en ese scope; si no, omitir `onAction` (queda sin botón). |
| Tickets (S4) | `tickets` *(existente, con overrides)* | *(preset)* Sin tickets visibles | **override:** No hay tickets para este proyecto. Sincronizá con ADO para traerlos. | actionLabel `Sincronizar ADO` **solo si** el handler de sync es accesible en ese scope; si no, omitir. — **zona-gated §9** |
| Equipo vacío (S5) | `agents` *(existente)* | Tu equipo está vacío | Agregá tu primer agente para empezar a asignar tickets. | actionLabel `Agregar agente`, `onAction = () => setManageOpen(true)` (reusa el handler local existente de TeamScreen) |
| Equipo sin proyecto (S5) | `no_project` *(NUEVA)* | Ningún proyecto activo | Seleccioná un proyecto desde la barra superior para ver su equipo. | — (sin acción) |

**Copys literales de las variantes NUEVAS (para pegar en `VARIANT_PRESETS`, F3):**

```ts
review: {
  icon: "✅",
  title: "Bandeja al día",
  message: "No hay ejecuciones que requieran tu revisión. Cuando un agente termine con dudas o error, va a aparecer acá.",
},
docs: {
  icon: "📚",
  title: "Sin documentación indexada",
  message: "Todavía no hay documentos para explorar. Indexá el proyecto para ver el grafo y buscar contenido.",
  actionLabel: "Indexar ahora",
},
no_project: {
  icon: "📂",
  title: "Ningún proyecto activo",
  message: "Seleccioná un proyecto desde la barra superior para ver su equipo.",
},
```

---

## § 9. Tabla de zonas de conflicto con la serie 132/134/135/136

La serie 132→134→135→136 aterriza ANTES. Archivos que ellos editan fuerte: `ActiveRunsPanel.tsx`, `TicketBoard.tsx`, `App.tsx`, `TopBar.tsx`, `SettingsPage.tsx`, `EpicFromBriefModal.tsx`, `CodexConsoleDock.tsx`.

| Archivo | ¿Lo toca este plan? | Zona que toca ESTE plan | Zona que tocan 134/135/136 | Resolución |
|---|---|---|---|---|
| `ExecutionHistoryPage.tsx` | Sí (F4) | tabla: carga/vacío/status/fecha | — (limpio) | Sin conflicto. |
| `ReviewInboxPage.tsx` | Sí (F5) | tabla: carga/vacío/status/fecha | — (limpio) | Sin conflicto. |
| `DocsPage.tsx` | Sí (F6) | carga contenido / vacío índice / fecha "Indexado" | — (limpio) | Sin conflicto. El texto de error del grafo (`DocsPage.tsx:409` "No se pudo cargar el grafo.") **NO se toca** (dominio 135). |
| `TeamScreen.tsx` | Sí (F7) | `EmptyState`/`NoProjectState` locales + `skeletonCard` grid | — (limpio) | Sin conflicto. |
| `TicketBoard.tsx` | Sí, **acotado** (F8) | **solo** la carga de la lista (`:1010`) y el vacío de la lista (`:1011-1013`) | 134 toca banners "running" (`:359`, `:961-970`, `:638-641`), conteos "corriendo" (`:860-863`) y grafo | **Gate duro:** pre-flight `git status` antes de editar; si hay WIP de 134 sin commitear en `TicketBoard.tsx` → **STOP** y avisar al operador. F8 es **droppable**: si el conflicto existe, se omite F8 sin afectar F0-F7. |
| `ActiveRunsPanel.tsx` | **No** | — | 134 (dueño total) | Este plan NO adopta StatusChip ahí; es zona 134. |
| `App.tsx`, `TopBar.tsx`, `SettingsPage.tsx`, `EpicFromBriefModal.tsx`, `CodexConsoleDock.tsx` | **No** | — | 132/134/135/136 | No se tocan. |

---

## § 10. Reglas de proceso (aplican a CADA fase)

1. **Pre-flight por archivo (regla 135 v2 §3.2):** antes de editar CADA archivo, correr `git status -- "<ruta exacta>"`. Si el archivo aparece modificado (WIP ajeno sin commitear) → **STOP**, no editar, avisar al operador.
2. **Staging quirúrgico:** `git add -- "<ruta1>" "<ruta2>"` con paths explícitos. **NUNCA** `git add -A` ni `git add .`.
3. **Anclas por texto normativo:** los `:NN` son orientativos (el archivo puede haberse corrido por 134/135). Localizá por el **texto** citado (ej. el string `"Cargando historial…"`), no por número de línea.
4. **TDD:** en cada fase, primero el test (o se ajusta), se corre y **se ve fallar** por la razón correcta, luego se implementa, luego se corre y **se ve pasar**. Pegar el output real.
5. **Commit por fase** con mensaje `feat(plan-140): <fase> <resumen>` (sin comillas dobles embebidas — gotcha PS 5.1). **Push siempre manual** (no lo hace este plan).
6. **Comandos (cwd = `Stacky Agents/frontend`):**
   - Test de un archivo: `npx vitest run <ruta-relativa-al-frontend>`
   - Typecheck global: `npx tsc --noEmit`
   - Ratchet 138: `npx vitest run src/__tests__/uiDebtRatchet.test.ts`
7. **Regla vacío-vs-error (C1, OBLIGATORIA en F4-F8):** el `EmptyState` de VACÍO se renderiza
   SÓLO cuando la query resolvió OK con 0 elementos. La condición de vacío SIEMPRE lleva el
   guard `!<query>.isError` además de `<longitud> === 0` (ej.: `!historyQ.isError &&
   items.length === 0`). En estado de ERROR **NUNCA** se muestra `EmptyState` (sería un falso
   vacío). Este plan **NO** implementa UI de error (dominio 135): en error simplemente NO se
   entra al branch de vacío; se deja el render por defecto de la superficie. Usá el nombre real
   de la query de cada archivo (localizá `isLoading` para hallarla).

---

## § 11. Fases

### F0 — Helper canónico de tiempo relativo (`formatRelativeTime`)

**Objetivo (1 frase):** una única función pura ES para timestamps relativos con corte a fecha absoluta, determinista y testeable.
**Valor:** elimina 3 implementaciones divergentes (§3.5) y da corte a fecha absoluta que hoy nadie tiene.

**Archivos:**
- Crear `frontend/src/utils/formatRelativeTime.ts`
- Crear `frontend/src/utils/__tests__/formatRelativeTime.test.ts`

**Contrato exacto:**
```ts
// frontend/src/utils/formatRelativeTime.ts
const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/**
 * Tiempo relativo en español con corte a fecha absoluta.
 * Reglas de corte (congeladas):
 *   - iso vacío/inválido            -> "—"
 *   - futuro (t > now) o diff < 60s -> "recién"
 *   - diff < 60 min                 -> "hace N min"   (N = floor(seg/60), N>=1)
 *   - diff < 24 h                   -> "hace N h"     (N = floor(seg/3600))
 *   - diff < 7 días                 -> "hace N d"     (N = floor(seg/86400))
 *   - diff >= 7 días                -> "D MES YYYY"   (UTC, ej "3 jul 2026")
 * @param iso   timestamp ISO (o null/undefined)
 * @param nowMs epoch ms de "ahora" (default Date.now()); explícito en tests para determinismo.
 */
export function formatRelativeTime(iso: string | null | undefined, nowMs: number = Date.now()): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";

  const diffSec = Math.floor((nowMs - t) / 1000);
  if (diffSec < 60) return "recién"; // cubre futuro (diffSec negativo) y < 60s

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} min`;

  const diffH = Math.floor(diffSec / 3600);
  if (diffH < 24) return `hace ${diffH} h`;

  const diffD = Math.floor(diffSec / 86400);
  if (diffD < 7) return `hace ${diffD} d`;

  const d = new Date(t);
  return `${d.getUTCDate()} ${MESES_ABREV[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
```

**Test primero (`formatRelativeTime.test.ts`) — casos exactos:**
```ts
import { describe, it, expect } from "vitest";
import { formatRelativeTime } from "../formatRelativeTime";

const NOW = Date.parse("2026-07-15T12:00:00.000Z");
const before = (sec: number) => new Date(NOW - sec * 1000).toISOString();

describe("Plan 140 F0 — formatRelativeTime (puro)", () => {
  it("iso vacío/null/undefined -> —", () => {
    expect(formatRelativeTime("", NOW)).toBe("—");
    expect(formatRelativeTime(null, NOW)).toBe("—");
    expect(formatRelativeTime(undefined, NOW)).toBe("—");
  });
  it("iso inválido -> —", () => {
    expect(formatRelativeTime("no-es-fecha", NOW)).toBe("—");
  });
  it("futuro -> recién", () => {
    expect(formatRelativeTime(before(-120), NOW)).toBe("recién");
  });
  it("< 60s -> recién", () => {
    expect(formatRelativeTime(before(59), NOW)).toBe("recién");
  });
  it("frontera 60s -> hace 1 min", () => {
    expect(formatRelativeTime(before(60), NOW)).toBe("hace 1 min");
  });
  it("< 60min -> hace 59 min", () => {
    expect(formatRelativeTime(before(59 * 60), NOW)).toBe("hace 59 min");
  });
  it("frontera 60min -> hace 1 h", () => {
    expect(formatRelativeTime(before(3600), NOW)).toBe("hace 1 h");
  });
  it("< 24h -> hace 23 h", () => {
    expect(formatRelativeTime(before(23 * 3600), NOW)).toBe("hace 23 h");
  });
  it("frontera 24h -> hace 1 d", () => {
    expect(formatRelativeTime(before(86400), NOW)).toBe("hace 1 d");
  });
  it("< 7d -> hace 6 d", () => {
    expect(formatRelativeTime(before(6 * 86400), NOW)).toBe("hace 6 d");
  });
  it("frontera 7d -> fecha absoluta UTC", () => {
    expect(formatRelativeTime(before(7 * 86400), NOW)).toBe("8 jul 2026");
  });
  it("mucho tiempo atrás -> fecha absoluta UTC", () => {
    expect(formatRelativeTime("2026-01-03T00:00:00.000Z", NOW)).toBe("3 ene 2026");
  });
});
```

**Comando:** `npx vitest run src/utils/__tests__/formatRelativeTime.test.ts`
**Criterio de aceptación (binario):** los 13 `it` verdes. `npx tsc --noEmit` = 0.
**Flag:** ninguna (helper puro, sin UI). **Runtime:** N/A (no wiring). **Trabajo del operador:** ninguno.

---

### F1 — Helper canónico de estado (`runStatus`: tone + label)

**Objetivo (1 frase):** una única función pura que mapea cualquier status de run/ticket a `{tone,label}` según la tabla §6.
**Valor:** centraliza el mapeo estado→color y elimina `statusClass`/badges hex divergentes.

**Archivos:**
- Crear `frontend/src/utils/runStatus.ts`
- Crear `frontend/src/utils/__tests__/runStatus.test.ts`

**Contrato exacto:**
```ts
// frontend/src/utils/runStatus.ts
export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";
// Debe coincidir con StatusChipProps["tone"] (138 §10.2). NO importar desde ui/ para no acoplar utils->ui.

interface StatusView { tone: StatusTone; label: string; }

const MAP: Record<string, StatusView> = {
  completed:    { tone: "success", label: "Completado" },
  success:      { tone: "success", label: "Completado" },
  done:         { tone: "success", label: "Completado" },
  running:      { tone: "info",    label: "En ejecución" },
  in_progress:  { tone: "info",    label: "En ejecución" },
  pending:      { tone: "neutral", label: "Pendiente" },
  queued:       { tone: "neutral", label: "En cola" },
  needs_review: { tone: "warning", label: "Requiere revisión" },
  review:       { tone: "warning", label: "Requiere revisión" },
  error:        { tone: "danger",  label: "Error" },
  failed:       { tone: "danger",  label: "Error" },
  cancelled:    { tone: "neutral", label: "Cancelado" },
  canceled:     { tone: "neutral", label: "Cancelado" },
};

function normalize(status: string | null | undefined): string {
  return String(status ?? "").trim().toLowerCase();
}

export function runStatusTone(status: string | null | undefined): StatusTone {
  return MAP[normalize(status)]?.tone ?? "neutral";
}

/** Etiqueta ES; si el status es desconocido devuelve el crudo; si viene vacío "—". */
export function runStatusLabel(status: string | null | undefined): string {
  const key = normalize(status);
  if (!key) return "—";
  return MAP[key]?.label ?? String(status);
}
```

**Test primero (`runStatus.test.ts`) — casos exactos:**
```ts
import { describe, it, expect } from "vitest";
import { runStatusTone, runStatusLabel } from "../runStatus";

describe("Plan 140 F1 — runStatus (puro)", () => {
  it("completed/success/done -> success + Completado", () => {
    for (const s of ["completed", "success", "done", "COMPLETED", " Done "]) {
      expect(runStatusTone(s)).toBe("success");
      expect(runStatusLabel(s)).toBe("Completado");
    }
  });
  it("running/in_progress -> info + En ejecución", () => {
    expect(runStatusTone("running")).toBe("info");
    expect(runStatusLabel("in_progress")).toBe("En ejecución");
  });
  it("needs_review/review -> warning + Requiere revisión", () => {
    expect(runStatusTone("needs_review")).toBe("warning");
    expect(runStatusLabel("review")).toBe("Requiere revisión");
  });
  it("error/failed -> danger + Error", () => {
    expect(runStatusTone("error")).toBe("danger");
    expect(runStatusTone("failed")).toBe("danger");
    expect(runStatusLabel("error")).toBe("Error");
  });
  it("cancelled/canceled/pending/queued -> neutral", () => {
    for (const s of ["cancelled", "canceled", "pending", "queued"]) {
      expect(runStatusTone(s)).toBe("neutral");
    }
  });
  it("desconocido -> neutral + crudo", () => {
    expect(runStatusTone("banana")).toBe("neutral");
    expect(runStatusLabel("banana")).toBe("banana");
  });
  it("vacío/null -> neutral + —", () => {
    expect(runStatusTone("")).toBe("neutral");
    expect(runStatusLabel(null)).toBe("—");
  });
});
```

**Comando:** `npx vitest run src/utils/__tests__/runStatus.test.ts`
**Criterio (binario):** 7 `it` verdes; `npx tsc --noEmit` = 0.
**Flag:** ninguna. **Runtime:** N/A. **Trabajo del operador:** ninguno.

---

### F2 — Componente `SkeletonList` (composición sobre `Skeleton`)

**Objetivo (1 frase):** un componente reutilizable que renderiza N barras skeleton apiladas para listas/tablas en carga, sin inline styles ni hex.
**Valor:** una sola forma de skeleton de lista para S1..S4; DRY y ratchet-safe.

**Archivos:**
- Crear `frontend/src/components/SkeletonList.tsx`
- Crear `frontend/src/components/SkeletonList.module.css`
- Crear `frontend/src/components/__tests__/SkeletonList.test.ts`

**Contrato exacto:**
```ts
// frontend/src/components/SkeletonList.tsx
import { Skeleton } from "./ui";
import styles from "./SkeletonList.module.css";

/** Clamp defensivo: 1..24 filas. Pura y exportada para test. */
export function clampRows(rows: number): number {
  if (!Number.isFinite(rows)) return 1;
  return Math.max(1, Math.min(24, Math.floor(rows)));
}

interface SkeletonListProps {
  rows?: number;       // default 6
  rowHeight?: number;  // px, default 28
  gap?: "sm" | "md";   // default "sm"
  ariaLabel?: string;  // default "Cargando"
}

export default function SkeletonList({ rows = 6, rowHeight = 28, gap = "sm", ariaLabel = "Cargando" }: SkeletonListProps) {
  const n = clampRows(rows);
  return (
    <div
      className={gap === "md" ? `${styles.list} ${styles.gapMd}` : styles.list}
      role="status"
      aria-busy="true"
      aria-label={ariaLabel}
    >
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} height={rowHeight} radius="var(--radius-md)" />
      ))}
    </div>
  );
}
```
```css
/* frontend/src/components/SkeletonList.module.css */
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.gapMd {
  gap: var(--space-5);
}
```

> **Ratchet-safe:** `SkeletonList.tsx` **no** contiene `style={{`. La `Skeleton` interna usa `style={skeletonStyle(...)}` (una llave, no cuenta). `SkeletonList.module.css` **no** tiene hex (solo tokens). Cae en baseline 0 para ambos contadores.

**Test primero (`SkeletonList.test.ts`) — puro + fs+regex (calca `DevOpsPage.test.ts:42-51`):**
```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { clampRows } from "../SkeletonList";

const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/SkeletonList.tsx";
const CSS = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/SkeletonList.module.css";

describe("Plan 140 F2 — SkeletonList", () => {
  it("clampRows fija 1..24", () => {
    expect(clampRows(0)).toBe(1);
    expect(clampRows(-3)).toBe(1);
    expect(clampRows(6)).toBe(6);
    expect(clampRows(999)).toBe(24);
    expect(clampRows(NaN)).toBe(1);
    expect(clampRows(3.9)).toBe(3);
  });
  it("consume la primitiva Skeleton de ui (no reinventa)", () => {
    const src = readFileSync(SRC, "utf-8");
    expect(/from ["']\.\/ui["']/.test(src)).toBe(true);
    expect(/<Skeleton\b/.test(src)).toBe(true);
  });
  it("es ratchet-safe: sin style-doble-llave ni hex", () => {
    const src = readFileSync(SRC, "utf-8");
    const css = readFileSync(CSS, "utf-8");
    expect(/style=\{\{/.test(src)).toBe(false);
    expect(/#[0-9a-fA-F]{3,8}\b/.test(css)).toBe(false);
  });
  it("anuncia carga accesible", () => {
    const src = readFileSync(SRC, "utf-8");
    expect(/role="status"/.test(src)).toBe(true);
    expect(/aria-busy="true"/.test(src)).toBe(true);
  });
});
```

**Comando:** `npx vitest run src/components/__tests__/SkeletonList.test.ts`
**Criterio (binario):** 4 `it` verdes; `npx tsc --noEmit` = 0.
**Flag:** ninguna. **Runtime:** N/A (presentación pura; misma UI en los 3). **Performance:** 0 requests/timers; N ≤ 24 divs estáticos. **Trabajo del operador:** ninguno.

---

### F3 — Extender `EmptyState` (3 variantes nuevas + accessor puro + acción por `Button`)

**Objetivo (1 frase):** que el `EmptyState` compartido cubra todas las superficies del plan y exponga sus presets de forma testeable, alineando el botón con la primitiva `Button`.
**Valor:** habilita KPI-2; retira el `#fff` inline del botón crudo (baja el ratchet).

**Archivos:**
- Editar `frontend/src/components/EmptyState.tsx`
- Editar `frontend/src/components/EmptyState.module.css`
- Crear `frontend/src/components/__tests__/EmptyState.presets.test.ts`

**Cambios exactos en `EmptyState.tsx`:**
1. Ampliar el union `EmptyVariant` (`:4-10`) agregando `"review" | "docs" | "no_project"`.
2. Agregar al `VARIANT_PRESETS` (`:21-61`) las 3 entradas literales de §8 (bloque copy-pasteable).
3. Exportar un accessor puro (para tests): agregar al final del archivo
   ```ts
   export function emptyStatePreset(variant: EmptyVariant) {
     return VARIANT_PRESETS[variant];
   }
   ```
4. Reemplazar el botón crudo de acción (`:83-87`) por la primitiva `Button`:
   ```tsx
   {finalAction && onAction ? (
     <Button variant="primary" size="md" onClick={onAction}>{finalAction}</Button>
   ) : null}
   ```
   y agregar `import { Button } from "./ui";` arriba. **Borrar** la clase `.action` y `.action:hover` de `EmptyState.module.css` (`:35-47`, contiene `#fff`). No tocar el resto del CSS.

> Backward-compat: las props no cambian; variantes viejas siguen igual. El único cambio visible es el estilo del botón (ahora `Button` primario del 138) — mejora de jerarquía, reversible por revert.

**Test primero (`EmptyState.presets.test.ts`):**
```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { emptyStatePreset } from "../EmptyState";

const CSS = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/EmptyState.module.css";

describe("Plan 140 F3 — EmptyState presets", () => {
  it("variante review con copy exacto", () => {
    const p = emptyStatePreset("review");
    expect(p.title).toBe("Bandeja al día");
    expect(p.message).toContain("No hay ejecuciones que requieran tu revisión");
  });
  it("variante docs con copy exacto y acción", () => {
    const p = emptyStatePreset("docs");
    expect(p.title).toBe("Sin documentación indexada");
    expect(p.actionLabel).toBe("Indexar ahora");
  });
  it("variante no_project con copy exacto", () => {
    const p = emptyStatePreset("no_project");
    expect(p.title).toBe("Ningún proyecto activo");
  });
  it("conserva variantes previas (agents/history)", () => {
    expect(emptyStatePreset("agents").title).toBe("Tu equipo está vacío");
    expect(emptyStatePreset("history").title).toBe("Sin historial todavía");
  });
  it("el CSS ya no tiene el #fff del botón crudo", () => {
    const css = readFileSync(CSS, "utf-8");
    expect(/#fff\b/i.test(css)).toBe(false);
  });
});
```

**Comando:** `npx vitest run src/components/__tests__/EmptyState.presets.test.ts`
**Criterio (binario):** 5 `it` verdes; `npx tsc --noEmit` = 0; ratchet 138 verde (el contador de `EmptyState.module.css` **baja**, nunca sube).
**Flag:** ninguna. **Runtime:** N/A. **Trabajo del operador:** ninguno.

---

### F4 — Adopción en Historial de ejecuciones (`ExecutionHistoryPage`)

**Objetivo (1 frase):** que Historial muestre skeleton en carga, `EmptyState` en vacío, `StatusChip` en la columna Estado y `formatRelativeTime` en la columna Inicio.
**Valor:** superficie completa cubierta con las 4 estandarizaciones; retira 4 helpers/clases ad-hoc.

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx" "Stacky Agents/frontend/src/pages/ExecutionHistoryPage.module.css"` → si WIP ajeno, STOP.

**Cambios exactos en `ExecutionHistoryPage.tsx`:**
1. Imports nuevos:
   ```ts
   import EmptyState from "../components/EmptyState";
   import SkeletonList from "../components/SkeletonList";
   import { StatusChip } from "../components/ui";
   import { runStatusTone, runStatusLabel } from "../utils/runStatus";
   import { formatRelativeTime } from "../utils/formatRelativeTime";
   ```
2. **Borrar** `fmtDate` (`:35-39`) y `statusClass` (`:41-47`). Conservar `fmtDuration` y `fmtCost` (numéricos, no fecha).
3. CARGA: reemplazar el bloque `isLoading ? (<div className={styles.empty}>Cargando historial…</div>)` (`:178-179`) por:
   ```tsx
   {isLoading ? (
     <div className={styles.tableWrapper}><SkeletonList rows={8} rowHeight={28} ariaLabel="Cargando historial" /></div>
   ) : (!historyQ.isError && items.length === 0) ? (   // C1: guard vacío-vs-error (§10.7)
     <EmptyState variant="history" />
   ) : ( … tabla sin cambios … )}
   ```
   (el `Sin ejecuciones` de `:180-181` pasa a `<EmptyState variant="history" />`). **En error
   (`historyQ.isError`) NO se muestra EmptyState** (falso vacío): cae al branch de tabla, sin
   copy engañoso; el canal de error es 135.
4. Columna Inicio (`:207`): `{fmtDate(item.started_at)}` → `{formatRelativeTime(item.started_at)}`.
5. Columna Estado (`:211-215`): reemplazar el `<span className={statusBadge…}>` por
   ```tsx
   <td><StatusChip tone={runStatusTone(item.status)} size="sm">{runStatusLabel(item.status)}</StatusChip></td>
   ```
6. En `ExecutionHistoryPage.module.css`: **borrar** las clases muertas `.statusCompleted/.statusError/.statusReview/.statusRunning` (`:125-143`) y, si `.statusBadge` (`:115-123`) ya no se referencia, borrarla también (verificar con grep antes). **No** tocar `.riskLow/.riskMedium/.riskHigh` (siguen usadas por `local_insight`, `:231-242`).

**Test primero (`frontend/src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts`):**
```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx";
describe("Plan 140 F4 — adopción Historial", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("importa y usa SkeletonList", () => { expect(/import SkeletonList/.test(src())).toBe(true); expect(/<SkeletonList\b/.test(src())).toBe(true); });
  it("usa EmptyState compartido", () => { expect(/from ["']\.\.\/components\/EmptyState["']/.test(src())).toBe(true); expect(/<EmptyState\b/.test(src())).toBe(true); });
  it("guarda el vacío contra error (C1, §10.7): usa isError en la condición", () => { expect(/isError/.test(src())).toBe(true); });
  it("usa StatusChip + runStatus", () => { expect(/<StatusChip\b/.test(src())).toBe(true); expect(/runStatusTone\(/.test(src())).toBe(true); });
  it("usa formatRelativeTime y ya no toLocaleString ni statusClass", () => {
    expect(/formatRelativeTime\(/.test(src())).toBe(true);
    expect(/toLocaleString/.test(src())).toBe(false);
    expect(/function statusClass/.test(src())).toBe(false);
  });
});
```

**Comando:** `npx vitest run src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts && npx tsc --noEmit`
**Criterio (binario):** 4 `it` verdes; `tsc` 0; ratchet 138 verde (baja o igual).
**Flag:** ninguna (justificación §8). **Runtime:** misma tabla para los 3; sin ramas por runtime; fallback N/A. **Performance:** skeleton sin requests/timers. **Trabajo del operador:** ninguno.

---

### F5 — Adopción en Bandeja de revisión (`ReviewInboxPage`)

**Objetivo (1 frase):** skeleton en carga, `EmptyState` (variante `review`) en vacío, `StatusChip` en Status y `formatRelativeTime` en Terminado.
**Valor:** retira el `timeAgo` local y el badge hex propio.

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/pages/ReviewInboxPage.tsx" "Stacky Agents/frontend/src/pages/ReviewInboxPage.module.css"`.

**Cambios exactos en `ReviewInboxPage.tsx`:**
1. Imports nuevos: `EmptyState`, `SkeletonList`, `{ StatusChip }` de `../components/ui`, `{ runStatusTone, runStatusLabel }`, `{ formatRelativeTime }`.
2. **Borrar** la función `timeAgo` (`:21-32`). Conservar `summarizeCause`.
3. CARGA (`:98`): `{executionsQ.isLoading && <div className={styles.empty}>Cargando ejecuciones…</div>}` → `{executionsQ.isLoading && <SkeletonList rows={6} rowHeight={28} ariaLabel="Cargando ejecuciones" />}`.
4. VACÍO (`:99-101`, guard C1 §10.7): reemplazar por `{!executionsQ.isLoading && !executionsQ.isError && sortedRows.length === 0 && <EmptyState variant="review" />}`. En error NO se muestra EmptyState (dominio 135).
5. Status (`:120-124`): reemplazar el `<span className={badge…}>` por `<td><StatusChip tone={runStatusTone(row.status)} size="sm">{runStatusLabel(row.status)}</StatusChip></td>`.
6. Terminado (`:126`): `{timeAgo(row.completed_at || row.started_at)}` → `{formatRelativeTime(row.completed_at || row.started_at)}`.
7. En `ReviewInboxPage.module.css`: **borrar** las clases muertas `.badge/.error/.review` si dejan de referenciarse (grep antes). No tocar el resto.

**Test primero (`frontend/src/pages/__tests__/ReviewInboxPage.adoption.test.ts`):** calca F4 con `SRC` = `.../ReviewInboxPage.tsx`, mismos `it` adaptados (`<SkeletonList>`, `<EmptyState variant="review"`, `<StatusChip>` + `runStatusTone`, `formatRelativeTime` presente y `function timeAgo` ausente y `toLocale` ausente, **y el guard `isError` de C1 presente en la condición del vacío**).

**Comando:** `npx vitest run src/pages/__tests__/ReviewInboxPage.adoption.test.ts && npx tsc --noEmit`
**Criterio (binario):** 4 `it` verdes; `tsc` 0; ratchet verde.
**Flag:** ninguna. **Runtime:** N/A (idéntico en los 3). **Trabajo del operador:** ninguno.

---

### F6 — Adopción en Documentación (`DocsPage`)

**Objetivo (1 frase):** skeleton en la carga del panel de contenido, `EmptyState` (variante `docs`) en índice vacío, `formatRelativeTime` en el sello "Indexado".
**Valor:** cierra el timestamp ad-hoc (`toLocaleTimeString`) y estandariza carga/vacío. **NO** toca el texto de error del grafo (dominio 135).

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/pages/DocsPage.tsx"`.

**Cambios exactos en `DocsPage.tsx`:**
1. Imports: `EmptyState`, `SkeletonList`, `{ formatRelativeTime }`. (Acá **no** hay StatusChip: Docs no muestra estados de run.)
2. CARGA de contenido (`:265`): `<p>Cargando documentación...</p>` → `<SkeletonList rows={6} rowHeight={20} ariaLabel="Cargando documentación" />`.
3. VACÍO de índice (`:331` `<div className={styles.emptyState}>…</div>`): reemplazar el contenido del vacío por `<EmptyState variant="docs" />`. **Guard C1 (§10.7):** mostrar el `EmptyState` de índice vacío SÓLO si la query del índice NO está en error (`!<indexQuery>.isError`); en error NO mostrarlo (dominio 135). Si en ese scope existe un handler de reindex, pasarlo como `onAction={<handler>}`; si no, omitir (queda sin botón). **Confirmar por lectura** si el handler es accesible; si no lo es, NO inventarlo.
4. Sello "Indexado" (`:347`): `Indexado: {new Date(indexData.indexed_at).toLocaleTimeString()}` → `Indexado: {formatRelativeTime(indexData.indexed_at)}`.
5. **NO tocar** `:409` (`"No se pudo cargar el grafo." : "Cargando grafo..."`): el ternario mezcla error+carga y el error es dominio 135. Dejar como está; documentar en §12 que 135/141 lo unifican.

**Test primero (`frontend/src/pages/__tests__/DocsPage.adoption.test.ts`):**
```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DocsPage.tsx";
describe("Plan 140 F6 — adopción Docs", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("usa SkeletonList y EmptyState docs", () => {
    expect(/<SkeletonList\b/.test(src())).toBe(true);
    expect(/variant="docs"/.test(src())).toBe(true);
  });
  it("usa formatRelativeTime en Indexado y ya no toLocaleTimeString", () => {
    expect(/formatRelativeTime\(/.test(src())).toBe(true);
    expect(/toLocaleTimeString/.test(src())).toBe(false);
  });
  it("NO reemplaza el texto de error del grafo (dominio 135)", () => {
    expect(/No se pudo cargar el grafo\./.test(src())).toBe(true);
  });
});
```

**Comando:** `npx vitest run src/pages/__tests__/DocsPage.adoption.test.ts && npx tsc --noEmit`
**Criterio (binario):** 3 `it` verdes; `tsc` 0; ratchet verde.
**Flag:** ninguna. **Runtime:** N/A. **Trabajo del operador:** ninguno.

---

### F7 — Adopción en Mi Equipo (`TeamScreen`)

**Objetivo (1 frase):** reemplazar los dos vacíos LOCALES por el `EmptyState` compartido y migrar el skeleton hand-rolled a la primitiva `Skeleton`.
**Valor:** elimina 2 duplicaciones de vacío y unifica el skeleton; sube el grep de importadores del compartido.

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/pages/TeamScreen.tsx" "Stacky Agents/frontend/src/pages/TeamScreen.module.css"`.

**Cambios exactos en `TeamScreen.tsx`:**
1. Import: `import SharedEmptyState from "../components/EmptyState";` y `import { Skeleton } from "../components/ui";`. (Se importa con alias `SharedEmptyState` para no chocar con la función local mientras se migra; al terminar, la local se borra.)
2. CARGA (`:139-144`): dentro de `styles.loadingGrid`, reemplazar los 4 `<div className={styles.skeletonCard} aria-hidden />` por:
   ```tsx
   {[...Array(4)].map((_, i) => (
     <Skeleton key={i} height={120} radius="var(--radius-lg)" />
   ))}
   ```
3. Vacío sin proyecto (`:145-146`): `<NoProjectState />` → `<SharedEmptyState variant="no_project" />`.
4. Vacío de equipo (`:147-148`): `<EmptyState onAdd={() => setManageOpen(true)} />` → `<SharedEmptyState variant="agents" actionLabel="Agregar agente" onAction={() => setManageOpen(true)} />`.
5. **Borrar** las funciones locales `NoProjectState` (`:193-203`) y `EmptyState` (`:205-218`).
6. En `TeamScreen.module.css`: `.skeletonCard` puede quedar sin uso → borrar si grep confirma 0 referencias. `.empty/.emptyIcon/.emptyTitle/.emptyText/.emptyBtn`: borrar **solo** las que queden sin referencia (grep antes); si alguna se usa en otro lado del archivo, dejarla.

**Test primero (`frontend/src/pages/__tests__/TeamScreen.adoption.test.ts`):**
```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/TeamScreen.tsx";
describe("Plan 140 F7 — adopción Equipo", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("importa el EmptyState compartido", () => {
    expect(/import\s+SharedEmptyState\s+from\s+["']\.\.\/components\/EmptyState["']/.test(src())).toBe(true);
  });
  it("usa variantes agents y no_project", () => {
    expect(/variant="agents"/.test(src())).toBe(true);
    expect(/variant="no_project"/.test(src())).toBe(true);
  });
  it("ya no define EmptyState/NoProjectState locales", () => {
    expect(/function EmptyState\(/.test(src())).toBe(false);
    expect(/function NoProjectState\(/.test(src())).toBe(false);
  });
  it("skeleton migrado a la primitiva Skeleton", () => {
    expect(/<Skeleton\b/.test(src())).toBe(true);
    expect(/className=\{styles\.skeletonCard\}/.test(src())).toBe(false);
  });
});
```

**Comando:** `npx vitest run src/pages/__tests__/TeamScreen.adoption.test.ts && npx tsc --noEmit`
**Criterio (binario):** 4 `it` verdes; `tsc` 0; ratchet verde.
**Flag:** ninguna. **Runtime:** N/A. **Trabajo del operador:** ninguno.

---

### F8 — Adopción ACOTADA en Tablero de tickets (`TicketBoard`) — **zona-gated, droppable**

**Objetivo (1 frase):** solo la carga y el vacío de la **lista** de tickets pasan a `SkeletonList` y `EmptyState`, sin tocar ninguna zona de "running" (dominio 134).
**Valor:** cubre la superficie más visible sin invadir 134.

**Gate duro (obligatorio):** `git status -- "Stacky Agents/frontend/src/pages/TicketBoard.tsx"`. Si aparece modificado (WIP de 134 sin commitear) → **STOP, NO implementar F8, avisar al operador.** F8 es **opcional**: su omisión no rompe F0-F7 ni el DoD (KPI-1..4 se cumplen con S1-S3/S5).

**Cambios exactos (SOLO estos, nada de running):**
1. Import: `EmptyState`, `SkeletonList`.
2. CARGA de la lista (localizar por el texto `"Cargando jerarquía…"`, hoy `:1010`): `<div className={styles.loading}>Cargando jerarquía…</div>` → `<SkeletonList rows={6} rowHeight={44} ariaLabel="Cargando tickets" />`.
3. VACÍO de la lista (texto `"No hay tickets. Hacé clic en «Sincronizar ADO»."`, hoy `:1011-1013`): reemplazar por
   ```tsx
   <EmptyState variant="tickets"
     message="No hay tickets para este proyecto. Sincronizá con ADO para traerlos."
     actionLabel={/* pasar "Sincronizar ADO" + onAction SOLO si el handler de sync es accesible en este scope; si no, omitir ambos */}
   />
   ```
   Confirmar por lectura si el handler de sync está en scope; si no, dejar sin `actionLabel/onAction`.
   **Guard C1 (§10.7):** renderizar este vacío SÓLO cuando la lista NO esté en error
   (`!<query>.isError && <lista vacía>`); en error NO mostrar EmptyState (dominio 135).
4. **PROHIBIDO** tocar: banners running (`:359`, `:366`, `:638-641`), conteo "corriendo" (`:860-863`), `EpicGroup` running, modo grafo (`:1054`) y cualquier `runningExecution/runningByTicket`.

**Test primero (`frontend/src/pages/__tests__/TicketBoard.adoption.test.ts`):**
```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/TicketBoard.tsx";
describe("Plan 140 F8 — adopción acotada Tickets", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("carga de lista usa SkeletonList y ya no el texto plano", () => {
    expect(/<SkeletonList\b/.test(src())).toBe(true);
    expect(/Cargando jerarquía…/.test(src())).toBe(false);
  });
  it("vacío de lista usa EmptyState tickets", () => {
    expect(/variant="tickets"/.test(src())).toBe(true);
  });
  it("NO tocó zonas de running (siguen presentes)", () => {
    expect(/runningByTicket/.test(src())).toBe(true);
    expect(/runningPulse/.test(src())).toBe(true);
  });
});
```

**Comando:** `npx vitest run src/pages/__tests__/TicketBoard.adoption.test.ts && npx tsc --noEmit`
**Criterio (binario):** 3 `it` verdes; `tsc` 0; ratchet verde. **Si el gate STOP se activó, F8 se marca OMITIDA y el DoD se evalúa sin ella.**
**Flag:** ninguna. **Runtime:** N/A. **Trabajo del operador:** ninguno.

---

### F9 — Verificación global, ratchet y DoD

**Objetivo (1 frase):** confirmar que todo el plan quedó verde, sin regresión de ratchet, sin tocar `package.json`, y sin invadir dominios ajenos.

**Pasos (comando exacto, cwd = `Stacky Agents/frontend`):**
1. `npx tsc --noEmit` → **0 errores**.
2. Correr TODOS los tests nuevos:
   ```
   npx vitest run src/utils/__tests__/formatRelativeTime.test.ts src/utils/__tests__/runStatus.test.ts src/components/__tests__/SkeletonList.test.ts src/components/__tests__/EmptyState.presets.test.ts src/pages/__tests__/ExecutionHistoryPage.adoption.test.ts src/pages/__tests__/ReviewInboxPage.adoption.test.ts src/pages/__tests__/DocsPage.adoption.test.ts src/pages/__tests__/TeamScreen.adoption.test.ts src/pages/__tests__/TicketBoard.adoption.test.ts
   ```
   → todos verdes (si F8 fue OMITIDA, excluir su archivo).
3. Ratchet 138: `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → **verde sin regenerar baseline** (los contadores solo bajan).
4. `git status -- "Stacky Agents/frontend/package.json"` → **limpio**.
5. Grep de importadores del `EmptyState` compartido → **≥ 4** archivos (era 0).
6. Grep en las superficies tocadas: `toLocaleString|toLocaleTimeString|function timeAgo|function statusClass` → **0** en F4-F7 (S1-S3,S5).

**DoD global (todo debe cumplirse):**
- [ ] F0-F7 implementadas y verdes; F8 implementada verde **o** OMITIDA por gate (documentado).
- [ ] KPI-1..KPI-5 (§4) satisfechos.
- [ ] `tsc --noEmit` = 0; ratchet 138 verde; `package.json` intacto.
- [ ] Cero flags nuevas; cero backend; cero cambios en runtimes; cero trabajo del operador.
- [ ] Ningún archivo de dominio 134/135/136 tocado fuera de la zona acotada de F8 (§9).
- [ ] `dbcompare/relativeTime.ts` NO modificado (§12).

---

## § 12. Fuera de scope

1. **Canal de error** (LoadErrorState, error≠vacío, ErrorBoundary, Toast, retry): 100% Plan 135. Este plan referencia, no implementa. En particular `DocsPage.tsx:409` (error del grafo) queda intacto.
2. **`components/dbcompare/relativeTime.ts`** (`relativeTimeEs`, Plan 124 F6, mergeado): NO se migra ni se borra. Es un duplicado conocido; su unificación con `formatRelativeTime` es una tarea futura separada (tocar código de 124 excede este plan).
3. **Zonas "running"** de `TicketBoard.tsx` y `ActiveRunsPanel.tsx`: dominio 134. Este plan NO adopta StatusChip ahí.
4. **Tema claro** (`data-theme="light"`): Plan 141. Este plan solo consume tokens `--status-*` existentes (dark).
5. **Superficies secundarias** no listadas (DevOps sections, PMCommandCenter, SprintBoard, SystemLogs, Diagnostics, etc.): fuera de las 5 principales; se abordan en un plan posterior si aportan valor. Los helpers de F0-F3 quedan disponibles para ellas.
6. Cualquier cambio en `package.json`, dependencias o backend.

---

## § 13. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | 138 no está implementado cuando se corre este plan (primitivas `ui/` inexistentes). | Pre-condición dura: F2/F3/F4-F8 dependen de `components/ui/{Skeleton,StatusChip,Button}`. Si `import` falla en `tsc`, STOP: 138 debe estar mergeado primero. |
| R2 | 134/135 corrieron y movieron líneas en `TicketBoard.tsx`/otros → anclas `:NN` desfasadas. | Anclar por **texto** normativo, no por línea (§10.3). Pre-flight `git status` por archivo. |
| R3 | F8 pisa WIP de 134 en `TicketBoard.tsx`. | Gate STOP en F8; F8 es droppable sin romper DoD. |
| R4 | Borrar clases CSS "muertas" que en realidad seguían usadas. | Grep de la clase en TODO el archivo antes de borrar; si hay ≥1 uso, no borrar. |
| R5 | El corte a fecha absoluta de `formatRelativeTime` usa UTC → puede diferir del día local del operador en timestamps viejos. | Aceptado y documentado: para ≥7 días el día exacto importa poco; UTC garantiza tests deterministas (mono-operador). Si el operador pide local, es un cambio trivial posterior. |
| R6 | La variante `docs`/`tickets` deja botón sin handler → click muerto. | Regla explícita F6/F8: pasar `onAction` **solo** si el handler es accesible; si no, omitir (sin botón). Nunca inventar handler. |
| R7 | Cambio de copy en timestamps (ReviewInbox "hace 5m" → "hace 5 min") percibido como regresión. | Es mejora aditiva, reversible por revert; no cambia comportamiento. Justificado en §8. |
| R8 | El chip `StatusChip danger` se confunde con "página en error". | Aclaración en §6: es solo color de dato; el estado de error de página es 135. |

---

## § 14. Justificación de "sin flag" (por qué NO agrega trabajo al operador)

Precedente 132 §3.1 / 135 §3.1: se omite flag cuando el cambio es **aditivo/correctivo + reversible con `git revert` + cero backend**. Este plan cumple los 3 en todas las fases:
- **F0-F3** son infra (helpers puros + 1 componente + variantes): invisibles hasta que se adoptan; nada que activar.
- **F4-F8** reemplazan **blanco/texto-plano por skeleton** y **vacío ad-hoc por EmptyState** (mejora de presentación de flujo feliz, no cambio de flujo). Los dos cambios "perceptibles" son (a) colores de estado ahora coherentes con el dark theme (corrección, no comportamiento) y (b) formato de timestamp unificado (textual). Ninguno altera datos, endpoints ni decisiones del operador.
- Todo es **frontend puro, idéntico en los 3 runtimes**, revertible por commit. Por eso: **sin flag**, cero configuración, cero trabajo del operador. Ninguna fase cambia un flujo feliz de forma que amerite flag OFF.

---

## § 15. Orden de implementación (numerado)

1. **F0** `formatRelativeTime` (util + test).
2. **F1** `runStatus` (util + test).
3. **F2** `SkeletonList` (componente + test). *(requiere `ui/Skeleton` del 138)*
4. **F3** `EmptyState` extendido (variantes + accessor + Button). *(requiere `ui/Button` del 138)*
5. **F4** Historial. **F5** Revisión. **F6** Docs. **F7** Equipo. *(F4-F7 independientes entre sí; orden libre)*
6. **F8** Tickets (acotado, gate STOP). *(droppable)*
7. **F9** Verificación global + DoD.

Cada fase: pre-flight → test primero (ver fallar) → implementar → test (ver pasar) → `tsc --noEmit` → ratchet → commit quirúrgico `feat(plan-140): Fn …`. Push manual al final.

---

## § 16. Smoke manual final (pasos numerados)

Con el frontend corriendo (`npm run dev` en `Stacky Agents/frontend`) y un proyecto activo:

1. **Historial** (`/executions/history` o su ruta): recargar con red lenta (DevTools → Network → Slow 3G). Confirmar: aparecen **barras skeleton** (no "Cargando historial…"), luego la tabla. Columna Estado con **StatusChip** (running=azul/info, completed=verde/success, error=rojo/danger, needs_review=amarillo/warning). Columna Inicio en **relativo** ("hace N min" / fecha para viejos).
2. Filtrar por un estado inexistente combinado hasta 0 resultados → aparece **EmptyState** "Sin historial todavía" (sin botón).
3. **Revisión** (`/review`): con red lenta, skeleton; con 0 pendientes, **EmptyState** "Bandeja al día" (icono ✅). Chips de Status y "Terminado" en relativo.
4. **Docs** (`/docs`): con red lenta, skeleton en el panel de contenido. Con proyecto sin indexar, **EmptyState** "Sin documentación indexada". Sello "Indexado: hace N …". Verificar que el error del grafo (si se fuerza) **sigue** mostrando "No se pudo cargar el grafo." (no lo tocamos).
5. **Equipo** (`/team`): con red lenta, 4 **Skeleton** de tarjeta (no los divs viejos). Sin proyecto activo → **EmptyState** "Ningún proyecto activo". Con equipo vacío → **EmptyState** "Tu equipo está vacío" con botón **Agregar agente** (abre el drawer).
6. **Tickets** (`/tickets`) *(si F8 se implementó)*: con red lenta, skeleton de lista; proyecto sin tickets → **EmptyState** "No hay tickets…". Confirmar que los banners "EN EJECUCIÓN" y el conteo "N corriendo" **siguen intactos** (zona 134).
7. Alternar tema si el 141 ya está: los chips deben seguir legibles (tokens `--status-*`).
8. Confirmar en consola: **0 warnings nuevos** de React y **0 requests extra** por los skeletons (Network no muestra llamadas nuevas al pintar skeletons).

---

**FIN DEL PLAN 140 (v1 PROPUESTO).** Próximo paso del pipeline: criticar con `criticar-y-mejorar-plan` antes de implementar.
