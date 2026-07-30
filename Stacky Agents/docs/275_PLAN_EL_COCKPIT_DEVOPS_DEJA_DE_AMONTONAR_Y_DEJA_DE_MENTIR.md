**Estado:** PROPUESTO v1 (2026-07-30) · **Autor:** pipeline proponer-plan-stacky (StackyArchitectaUltraEficientCode) · **Fuente:** auditoría UX/UI 2026-07-29 (`fd4e45d3`) + código verificado 2026-07-30

# Plan 275 — El cockpit DevOps deja de amontonar y deja de mentir

## 1. Objetivo

Tres correcciones acotadas y de bajo riesgo al panel/cockpit de DevOps (`frontend/src/pages/DevOpsPage.tsx`, `devopsCockpitShell.ts`, `frontend/src/components/devops/*`), las tres con evidencia `archivo:línea` de la auditoría 2026-07-29 y las tres verificadas contra el código real el 2026-07-30:

1. **La navegación deja de amontonar.** El grupo `construir` del cockpit tiene 7 secciones heterogéneas (autoría de pipelines y auditoría/inventario/reporting conviven en el mismo cajón). Se separan en dos grupos coherentes: `construir` (autoría: 3 secciones) y `gobernar` (solo-lectura/gobierno: 4 secciones).
2. **La previsualización de YAML deja de mentir.** `PublicationsSection.tsx:539-543` le pasa a `PipelineYamlPreview` un objeto `ctx.health` **inventado en el sitio de llamada** (todo `true` salvo `trigger_enabled`), en vez del `ctx` real que ya está disponible y que se usa seis líneas más abajo. Es el hallazgo H-11 (= B-08) de la auditoría, explícitamente dejado fuera del plan 273 por no ser su zona.
3. **Empieza el pago de la deuda visual concentrada en DevOps.** El literal `style={{ padding: '10px 20px' }}` se repite, byte a byte, 7 veces en los dos archivos de `components/devops/` con más deuda de estilos inline del repo (`PipelineBuilderSection.tsx`, 53 inline; `PublicationsSection.tsx`, 34 inline — H-15). Se extrae a una única clase compartida. No es una migración masiva — H-15 la prohíbe explícitamente — es el primer corte, mecánico y sin cambio visual, por concentración.

**KPI / impacto esperado** (medible sin telemetría nueva, con los comandos de cada fase):

| Métrica | Hoy (verificado 2026-07-30) | Objetivo |
|---|---|---|
| Máx. secciones en un solo grupo del cockpit DevOps | **7** (`construir`) | **≤ 5** en todos los grupos |
| Archivos de producción de `components/devops/` con un `ctx.health` fabricado en vez del real | **1** (`PublicationsSection.tsx:541`) | **0** |
| Ocurrencias del literal `style={{ padding: '10px 20px' }}` en `PipelineBuilderSection.tsx` + `PublicationsSection.tsx` | **7** (4 + 3) | **0** (extraídas a `.btnLg` en `devops.module.css`) |
| Conteo `inlineStyleByFile` del ratchet para esos 2 archivos (`uiDebtBaseline.json`) | `PipelineBuilderSection.tsx`: 53 · `PublicationsSection.tsx`: 34 | **49** · **31** (delta, nunca sube) |

**Flags nuevas: CERO.** Los tres cambios son correcciones de defecto (IA de navegación, contrato de datos mentiroso, deuda de estilo) sobre funcionalidad **ya construida y ya en `default=True`**, no una capacidad opcional nueva. No hay nada que un operador deba decidir activar u omitir.

---

## 2. Por qué ahora / gap que cierra

El panel DevOps es, por conteo propio verificado hoy, el área con más superficie del cockpit (17 secciones en `DEVOPS_SECTIONS`, `frontend/src/pages/DevOpsPage.tsx:145-330`) y la auditoría UX/UI 2026-07-29 (883 líneas, `docs/reportes/2026-07-29_AUDITORIA_UX_UI_PRODUCCION.md`, commit `fd4e45d3`) documenta ahí, con evidencia, tres tipos de deuda que ningún plan en vuelo cierra:

1. **Sobrecarga de información architecture, concentrada en un grupo.** `frontend/src/pages/devopsCockpitShell.ts:20-25` define 4 grupos (`resumen`, `operar`, `construir`, `diagnosticar`). Verificado hoy por conteo real de `group:` en `DevOpsPage.tsx:145-330`: `resumen` 1 · `operar` 6 · `construir` **7** · `diagnosticar` 3. El grupo `construir` mezcla dos intenciones muy distintas del operador: **autoría** (`pipelines` línea 161, `variables` línea 208, `editar-pipeline` línea 298 — el operador escribe/cambia algo) y **gobierno de solo lectura** (`inventario-pipelines` línea 274, `pipeline-audit` línea 286, `matriz-entornos` línea 310, `paquete-entrega` línea 322 — el operador audita/consulta). El síntoma de sobrecarga que la auditoría documenta para la nav global (H-05, `App.module.css:7-16`, 18 tabs sin `flex-wrap` ni `overflow-x`) **no reaparece técnicamente en el cockpit** — verificado hoy: `DevOpsCockpit.module.css:10-11` ya tiene `overflow-x: auto` en `.navPrimary` y `.navSecondary` — pero el problema de IA (un cajón con 7 acciones de naturaleza distinta) sigue siendo real y es lo que este plan corrige, no un bug de layout sino de agrupación semántica.
2. **H-11 (`docs/reportes/2026-07-29_AUDITORIA_UX_UI_PRODUCCION.md:380-403`), B-08 del censo de planes:** *"el componente de previsualización recibe un objeto de 'health' inventado en el sitio de llamada... mientras el `ctx` real está disponible y se usa seis líneas más abajo"*. Confirmado byte a byte hoy en `PublicationsSection.tsx:539-543`. El propio plan 273 lo lista como P1 fuera de su alcance (`docs/273_PLAN_EL_DEEP_LINK_ATERRIZA_Y_EL_ERROR_SE_ENTIENDE_LOS_7_BLOQUEANTES_DE_PRODUCCION.md:1099`, nota: *"P1, 1 línea, zona del plan 265/267"*) — queda libre, y es zona DevOps.
3. **H-15 (`docs/reportes/2026-07-29_AUDITORIA_UX_UI_PRODUCCION.md:459-483`):** *"la deuda de estilos inline está fuertemente concentrada en DevOps (6 de los 10 primeros archivos están bajo `components/devops/`)"* — con conteo exacto por archivo. La propia auditoría prescribe **no** migrar en masa y atacar **por concentración**. Los dos archivos de mayor deuda con superficie DevOps activa hoy (`BlockProperties.tsx` con 58 es el #1 pero es un editor de bloques de bajo tráfico; `PipelineBuilderSection.tsx` 53 y `PublicationsSection.tsx` 34 son, en cambio, las dos pantallas de mayor uso — autoría y publicación de pipelines) comparten, verificado hoy, **el mismo literal exacto** repetido 7 veces. Es la definición operacional de "atacar por concentración": mismo texto, mismo arreglo, en los dos archivos de más tráfico.

**Por qué un plan chico y no una reescritura:** los tres ejes son correcciones locales sobre construcción ya existente (cockpit v3 del plan 239, catálogo de acciones del plan 267) — ninguno pide diseño nuevo. Es exactamente el patrón "no falta construir, falta terminar de conectar/corregir lo construido" que la propia auditoría usa como diagnóstico general (§1).

**Frontera con el plan 273** (`PROPUESTO v1 SIN CRITICAR`, commit `8a6a7123`, sin commit de crítica verificado hoy con `git log --all --grep="plan-273"`): su §4 declara **"Prohibido tocar `pages/DevOpsPage.tsx` o `components/devops/` salvo la lectura de F4.5"** (`docs/273_PLAN_...:154`). Su F4 (B-02, contrato de error) **lee** tres archivos de `components/devops/` (`ProductionFlow.tsx:32`, `SectionDoctorButton.tsx:29`, `VariablesSection.tsx:34,43`) solo para verificar que su cambio en `api/client.ts` no les rompe el parseo — **no los edita**. Ninguno de esos tres archivos aparece en este plan. Los dos planes son disjuntos en archivos de escritura y pueden implementarse en paralelo sin coordinación.

---

## 3. Principios y guardarraíles

### 3.1 Rieles del producto (no negociables)
- **Human-in-the-loop.** Ningún cambio decide nada por el operador: F1 reordena tabs ya visibles, F2 corrige qué datos ve una previsualización (la hace más honesta, no la oculta ni la reemplaza por una decisión automática), F3 es un refactor invisible de CSS.
- **Mono-operador sin auth real.** No aplica: no se toca identidad, sesión ni permisos.
- **Toda config del operador va por UI.** Este plan no agrega ninguna configuración nueva; no hay flag que activar.

### 3.2 Cero trabajo extra para el operador
Los tres cambios son invisibles o mejoran lo que ya se ve sin pedir ninguna acción: la reagrupación de tabs es automática en el próximo build, la previsualización empieza a reflejar el estado real sin que el operador haga nada, y el refactor de CSS no cambia un solo píxel. **Ninguna de las dos categorías de excepción (A: quema tokens en reposo / B: escribe en sistema real, destruye datos, saca la decisión) aplica** — no hay loop, no hay llamada a modelo, no hay escritura a ADO/GitLab/BD/servidores. No se declara ninguna flag OFF.

### 3.3 Testing (rieles duros del repo, verificados en esta corrida)
- **RTL/jsdom NO están instalados en `frontend/`** (confirmado por el estado del repo). Prohibido cualquier test que monte un componente React. Todos los tests de este plan son `.ts` puros: leen archivos fuente como texto (gates de grep/ratchet, igual que `uiDebtRatchet.test.ts`) o importan solo los helpers/datos exportados de `devopsCockpitShell.ts`/`DevOpsPage.tsx` sin renderizar JSX — el mismo patrón que ya usan `frontend/src/pages/__tests__/devopsCockpitShell.test.ts` y `DevOpsCockpitClosure.test.ts`.
- **Vitest se corre por archivo**, nunca la suite completa (contaminación cross-file conocida): `npx vitest run <ruta-exacta>`, siempre desde `Stacky Agents/frontend`.
- **Gates compartidos son DELTA, nunca "todo verde".** `uiDebtRatchet.test.ts` compara contra `uiDebtBaseline.json` archivo por archivo; el criterio de F3 es que los dos archivos tocados **bajen** su conteo (nunca que el repo entero esté en cero).
- **El gate se corre CONTRA el defecto.** Cada fase declara el resultado ROJO esperado del test ANTES del fix, y se verifica que el fix lo pone VERDE.

### 3.4 Reusar, no reinventar
- La reagrupación (F1) usa exclusivamente los helpers puros ya existentes de `devopsCockpitShell.ts` (`groupOf`, `sectionsOfGroup`, `partitionForBar`, `DEVOPS_SECTION_GROUPS`, `DEVOPS_SECTION_GROUPS`) del plan 239 — no se crea ninguna primitiva de navegación nueva.
- El catálogo único de acciones DevOps del plan 267 (`DevOpsActionConsole.tsx`, IMPLEMENTADO 9/9) no se toca ni se duplica: este plan es sobre la navegación por tabs del cockpit, un eje distinto y complementario.
- F3 reusa la clase de botón ya existente en `devops.module.css` (`.btnPrimary`, `.btnSuccess`) como base y solo agrega el modificador de tamaño que falta, con el mismo patrón de composición de clases que ya usan 10+ archivos del propio directorio (`className={\`${styles.X} ${styles.Y}\`}`, verificado en `ConnectionHealthStrip.tsx:59`, `FlagGateBanner.tsx:56`, `PipelineAuditPanel.tsx:110`, entre otros).

### 3.5 Paridad de runtimes
Los tres cambios son 100% frontend (`.tsx`/`.css`/`.ts` de test), sin ninguna pieza de backend, prompt, agente ni tool. **Impacto neutro/idéntico en Codex CLI, Claude Code CLI y GitHub Copilot Pro**: el diff se aplica igual, los tests son `npx vitest run` igual, no hay ninguna superficie que dependa del runtime que ejecuta el cambio. No se declara fallback por runtime porque no hay divergencia posible (mismo patrón que usó el plan 274 para sus fases de frontend puro).

### 3.6 Sin flags nuevas
Confirmado en 3.2: no se introduce ninguna `FlagSpec`, ninguna variable de entorno, ninguna entrada en `_CURATED_DEFAULTS_ON` ni en `PLAIN_HELP`. Los tres cambios corrigen comportamiento de secciones que ya están, verificado hoy, con sus 40 flags de la categoría `devops` en `default=True`.

---

## 4. Fases

### F0 — Línea base: confirmar el ROJO de las tres fases y la frontera con el plan 273

**Objetivo:** dejar registrado, con comandos reales, el estado ANTES de tocar nada, para que F1-F3 midan delta real y no una foto inventada. **Valor:** evita que una fase se marque VERDE por casualidad (código ya arreglado por otro plan) o que el criterio de "no rompí nada" quede sin ancla.

**No se crean ni editan archivos en esta fase** — solo comandos de verificación, ejecutados desde `Stacky Agents/frontend` salvo que se indique lo contrario.

1. Confirmar que el plan 273 no ha sido implementado ni ha tocado `components/devops/` desde que se escribió este plan:
   ```
   git log --all --oneline --grep="plan-273"
   ```
   Resultado esperado hoy: una sola línea, `8a6a7123 docs(plan-273): cierre de los 7 bloqueantes UX/UI para produccion` (solo el commit del documento, ningún commit de implementación). Si aparece un commit de implementación adicional, releer su diff antes de continuar (podría haber tocado por error un archivo de este plan pese a su frontera declarada).

2. Confirmar el conteo actual de secciones por grupo (debe imprimir `construir: 7`):
   ```
   grep -c "group: 'construir'" ../"Stacky Agents"/frontend/src/pages/DevOpsPage.tsx
   ```
   (Si se corre desde `Stacky Agents/frontend`, usar `grep -c "group: 'construir'" src/pages/DevOpsPage.tsx`.)

3. Confirmar el literal fabricado de F2 (debe imprimir 1 coincidencia, la de `PublicationsSection.tsx:541`):
   ```
   grep -rn "ctx={{ health: {" src/components/devops --include=*.tsx
   ```

4. Confirmar el conteo del literal de padding de F3 (debe imprimir `4` y `3`):
   ```
   grep -c "style={{ padding: '10px 20px' }}" src/components/devops/PipelineBuilderSection.tsx
   grep -c "style={{ padding: '10px 20px' }}" src/components/devops/PublicationsSection.tsx
   ```

5. Confirmar el baseline actual del ratchet de deuda visual para ambos archivos:
   ```
   grep -A1 '"components/devops/PipelineBuilderSection.tsx"' src/__tests__/uiDebtBaseline.json
   grep -A1 '"components/devops/PublicationsSection.tsx"' src/__tests__/uiDebtBaseline.json
   ```
   Resultado esperado hoy: `53` y `34` respectivamente (bajo `inlineStyleByFile`).

**Criterio de aceptación:** los 5 comandos devuelven exactamente los valores citados arriba. Si alguno difiere, detenerse y re-anclar esa fase específica contra el valor real antes de seguir — no asumir que el plan sigue vigente tal cual.

**Flag:** ninguna. **Impacto por runtime:** ninguno (solo lectura). **Trabajo del operador:** ninguno.

---

### F1 — El grupo `construir` deja de amontonar: autoría separada de gobierno

**Objetivo:** dividir el grupo `construir` (7 secciones: 3 de autoría + 4 de solo-lectura/gobierno) en dos grupos coherentes, `construir` (3) y `gobernar` (4), sin tocar ninguna otra sección ni cambiar ninguna flag. **Valor:** el operador que quiere auditar o revisar el estado de sus pipelines (inventario, auditoría de seguridad, matriz de entornos, paquete de entrega) ya no tiene que escanear un cajón de 7 ítems mezclado con las herramientas de edición activa.

**Archivos a editar:**
- `frontend/src/pages/devopsCockpitShell.ts`
- `frontend/src/pages/DevOpsPage.tsx`
- `frontend/src/pages/__tests__/devopsCockpitShell.test.ts` (test existente que hardcodea "4 grupos" — se actualiza a 5, ver más abajo)

**Archivos a crear:**
- `frontend/src/pages/__tests__/plan275DevOpsGroupBalance.test.ts`

**1. Diseño exacto del nuevo grupo.** Cuatro secciones cambian de `group: 'construir'` a `group: 'gobernar'` — son las de solo-lectura/gobierno de pipelines ya construidas (planes 246/248/251/252, todas con `default=True`):

| id | label actual | línea de `group:` verificada hoy (buscar por el `id:` de la tabla, NO confiar en el número si el archivo se movió) |
|---|---|---|
| `inventario-pipelines` | Inventario | `DevOpsPage.tsx:274` |
| `pipeline-audit` | Auditoría | `DevOpsPage.tsx:286` |
| `matriz-entornos` | Matriz de entornos | `DevOpsPage.tsx:310` |
| `paquete-entrega` | Paquete de entrega | `DevOpsPage.tsx:322` |

Quedan en `construir` (sin tocar): `pipelines` (línea 161), `variables` (línea 208), `editar-pipeline` (línea 298) — las tres son de autoría/edición activa.

**2. Tests PRIMERO — `frontend/src/pages/__tests__/plan275DevOpsGroupBalance.test.ts` (archivo nuevo):**

```ts
/**
 * plan275DevOpsGroupBalance.test.ts — Plan 275 F1.
 * Ningún grupo del cockpit DevOps debe amontonar más de 5 secciones (IA de
 * navegación, ver docs/275_PLAN_...md §2). El gate se corre CONTRA el
 * defecto: HOY 'construir' tiene 7 y este test da ROJO.
 */
import { describe, it, expect } from 'vitest';
import { DEVOPS_SECTIONS } from '../DevOpsPage';
import { DEVOPS_SECTION_GROUPS, sectionsOfGroup, groupOf } from '../devopsCockpitShell';

const MAX_SECCIONES_POR_GRUPO = 5;

describe('plan 275 F1 — balance de grupos del cockpit DevOps', () => {
  it(`ningún grupo visible tiene más de ${MAX_SECCIONES_POR_GRUPO} secciones`, () => {
    const porGrupo = new Map<string, number>();
    DEVOPS_SECTIONS.forEach((s) => {
      const g = groupOf(s);
      porGrupo.set(g, (porGrupo.get(g) ?? 0) + 1);
    });
    const infractores = [...porGrupo.entries()].filter(([, n]) => n > MAX_SECCIONES_POR_GRUPO);
    expect(infractores, `Grupos sobrecargados: ${JSON.stringify(infractores)}`).toEqual([]);
  });

  it('el grupo "gobernar" existe en el catálogo de grupos', () => {
    expect(DEVOPS_SECTION_GROUPS.map((g) => g.id)).toContain('gobernar');
  });

  it('"gobernar" agrupa exactamente las 4 secciones de solo-lectura de pipelines', () => {
    const ids = sectionsOfGroup(DEVOPS_SECTIONS, 'gobernar' as any).map((s) => s.id).sort();
    expect(ids).toEqual(['inventario-pipelines', 'matriz-entornos', 'paquete-entrega', 'pipeline-audit']);
  });

  it('"construir" baja de 7 a 3: pipelines, variables, editar-pipeline', () => {
    const ids = sectionsOfGroup(DEVOPS_SECTIONS, 'construir').map((s) => s.id).sort();
    expect(ids).toEqual(['editar-pipeline', 'pipelines', 'variables']);
  });
});
```

**Comando y ROJO esperado ANTES del fix:**
```
cd "Stacky Agents\frontend"; npx vitest run src/pages/__tests__/plan275DevOpsGroupBalance.test.ts
```
Falla en 3 de los 4 `it`: el primero (`construir` tiene 7 > 5), el tercero (`sectionsOfGroup(..., 'gobernar')` da `[]` porque ninguna sección usa ese id todavía) y el cuarto (`construir` tiene 7 ids, no 3). El segundo (`DEVOPS_SECTION_GROUPS` no contiene `'gobernar'`) también falla.

**3. Diff de `frontend/src/pages/devopsCockpitShell.ts`:**

a) Línea 9 — ampliar el tipo:
```diff
-export type DevOpsGroupId = 'resumen' | 'operar' | 'construir' | 'diagnosticar';
+export type DevOpsGroupId = 'resumen' | 'operar' | 'construir' | 'gobernar' | 'diagnosticar';
```

b) Líneas 20-25 — agregar la entrada al catálogo de grupos, entre `construir` y `diagnosticar`:
```diff
 export const DEVOPS_SECTION_GROUPS: GroupDef[] = [
   { id: 'resumen', label: 'Resumen', hint: 'Estado general y avisos' },
   { id: 'operar', label: 'Operar', hint: 'Desplegar, ambientes, publicaciones y servidores' },
-  { id: 'construir', label: 'Construir', hint: 'Pipelines y variables' },
+  { id: 'construir', label: 'Construir', hint: 'Pipelines y variables' },
+  { id: 'gobernar', label: 'Gobernar', hint: 'Inventario, auditoría, matriz de entornos y paquete de entrega' },
   { id: 'diagnosticar', label: 'Diagnosticar', hint: 'PRs, consola remota y agente DevOps' },
 ];
```

c) Líneas 54-59 (dentro de `partitionForBar`) — agregar la clave nueva al objeto hardcodeado; **si se omite este paso, `visibleByGroup[groupOf(s)].push(s)` lanza `TypeError: Cannot read properties of undefined` para toda sección con `group: 'gobernar'`**:
```diff
   const visibleByGroup = {
     resumen: [] as DevOpsSection[],
     operar: [] as DevOpsSection[],
     construir: [] as DevOpsSection[],
+    gobernar: [] as DevOpsSection[],
     diagnosticar: [] as DevOpsSection[],
   } as Record<DevOpsGroupId, DevOpsSection[]>;
```

**4. Diff de `frontend/src/pages/DevOpsPage.tsx`.** Para cada uno de los 4 `id` de la tabla del punto 1: localizar el bloque `{ id: '<ese id>', ... }` y cambiar SU línea `group: 'construir',` (la única línea `group:` dentro de ese bloque específico) a `group: 'gobernar',`. Ejemplo del primero (`inventario-pipelines`):
```diff
   {
     id: 'inventario-pipelines',
     label: 'Inventario',
     ...
-    group: 'construir',
+    group: 'gobernar',
     healthKey: 'pipeline_inventory_enabled',
     gateFlagKey: 'STACKY_PIPELINE_INVENTORY_ENABLED',
     ...
   },
```
Repetir el mismo cambio (`'construir'` → `'gobernar'`) exclusivamente dentro de los bloques `pipeline-audit`, `matriz-entornos` y `paquete-entrega`. **No tocar** ninguna otra línea de esos bloques (`healthKey`, `gateFlagKey`, `gateMessage`, `render`) ni los bloques de `pipelines`, `variables`, `editar-pipeline`.

**5. Actualizar el test existente que hardcodea "4 grupos"** — `frontend/src/pages/__tests__/devopsCockpitShell.test.ts` (este test YA EXISTE y, si no se actualiza, queda ROJO después del fix por una razón ajena a un bug real — es el patrón "el ratchet de un plan hermano vigila tu función"):

```diff
-  it('DEVOPS_SECTION_GROUPS tiene exactamente 4 grupos (KPI-2)', () => {
-    expect(DEVOPS_SECTION_GROUPS).toHaveLength(4);
+  it('DEVOPS_SECTION_GROUPS tiene exactamente 5 grupos (KPI-2 ampliado por plan 275: separa autoría de gobierno)', () => {
+    expect(DEVOPS_SECTION_GROUPS).toHaveLength(5);
   });
```
```diff
   it('grupo con TODAS gateadas ⇒ el grupo sigue existiendo (no se oculta)', () => {
     const { visibleByGroup } = partitionForBar(SECTIONS, {});
     expect(Object.keys(visibleByGroup).sort()).toEqual(
-      ['construir', 'diagnosticar', 'operar', 'resumen'],
+      ['construir', 'diagnosticar', 'gobernar', 'operar', 'resumen'],
     );
     expect(visibleByGroup.diagnosticar).toEqual([]);
-    expect(buildGroupTabs(DEVOPS_SECTION_GROUPS)).toHaveLength(4);
+    expect(buildGroupTabs(DEVOPS_SECTION_GROUPS)).toHaveLength(5);
   });
```
```diff
   it('buildGroupTabs devuelve 4 items con id/label', () => {
     const tabs = buildGroupTabs(DEVOPS_SECTION_GROUPS);
-    expect(tabs).toHaveLength(4);
+    expect(tabs).toHaveLength(5);
```
(Renombrar también el texto del `it` de "4 items" a "5 items" para que no quede desincronizado con su propio aserto — mismo patrón que el gotcha "el comentario choca con su gate".)

**Nota informativa (no requiere editar ningún doc):** esto revisa hacia arriba el KPI-2 original del plan 239 (`docs/239_PLAN_COCKPIT_DEVOPS_REDISENO_INTEGRAL_UX_UI_E_INFORMACION.md:115`, *"9 → 4 opciones visibles de primer nivel"*). Pasar de 4 a 5 grupos de primer nivel sigue siendo una mejora neta de IA: la alternativa —dejar 7 secciones heterogéneas amontonadas en 1 grupo— es peor que 5 grupos de ≤6 secciones cada uno. `docs/239_...md` no se edita porque no es la fuente de verdad operativa (los tests sí lo son) y no fue pedido re-anclarlo en este plan.

**Comando y VERDE esperado DESPUÉS del fix (correr los dos archivos, uno por vez):**
```
cd "Stacky Agents\frontend"; npx vitest run src/pages/__tests__/plan275DevOpsGroupBalance.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts
```

**Criterio de aceptación (binario):** los dos comandos en 0 fallas. Además, sanity check de que ningún otro test quedó afectado (ninguno de estos dos archivos hardcodea la cuenta de grupos, verificado en F0-equivalente de esta fase):
```
cd "Stacky Agents\frontend"; npx vitest run src/pages/__tests__/DevOpsCockpitClosure.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/pages/__tests__/DevOpsCockpitRegression.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/pages/__tests__/DevOpsPage.test.ts
```
Estos 3 deben seguir en 0 fallas (ya usan lookups dinámicos por `id`/`group`, no cuentas fijas — verificado en la redacción de este plan).

**Flag:** ninguna — es una reorganización de secciones ya `default=True`, no una capacidad nueva.

**Impacto por runtime:** ninguno / idéntico en los tres (TSX + CSS + test `.ts` puro). Fallback: no aplica.

**Trabajo del operador:** ninguno. El próximo build ya muestra los 5 grupos; ningún dato ni preferencia guardada (`pinned` en `localStorage`, ver `useLocalStorageState` en `DevOpsPage.tsx:28`) se pierde porque los `id` de sección no cambian, solo su `group`.

---

### F2 — `PipelineYamlPreview` recibe el `ctx` real (cierra H-11 / B-08)

**Objetivo:** que la previsualización de YAML en Publicaciones refleje el estado real de las flags (`flag_enabled`, `generator_enabled`, `trigger_enabled`, `publications_enabled`) en vez de un objeto inventado que siempre miente en la misma dirección. **Valor:** el operador que usa la previsualización como paso previo a publicar un pipeline deja de ver una vista que promete capacidades que el backend puede rechazar.

**Archivos a editar:**
- `frontend/src/components/devops/PublicationsSection.tsx` — **solo** la línea 541 (la prop `ctx=` de la llamada a `PipelineYamlPreview` en las líneas 539-543).

**Archivos a crear:**
- `frontend/src/components/devops/__tests__/plan275PipelineYamlPreviewCtx.test.ts`

**Test PRIMERO:**

```ts
/**
 * plan275PipelineYamlPreviewCtx.test.ts — Plan 275 F2 (cierra H-11/B-08 de la
 * auditoría 2026-07-29: PublicationsSection.tsx:539-543 pasaba un ctx.health
 * INVENTADO a PipelineYamlPreview en vez del ctx real ya disponible en scope,
 * usado 6 líneas más abajo en PreflightPanel). Gate de grep sobre el FUENTE
 * (no hay RTL/jsdom en este repo): ningún archivo de producción bajo
 * components/devops/ puede pasar un objeto `health` literal dentro de una
 * prop `ctx=`. Se corre CONTRA el defecto: HOY da ROJO con 1 ofensor.
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const DEVOPS_DIR = path.join(process.cwd(), 'src', 'components', 'devops');
const CTX_LITERAL_RE = /ctx=\{\{\s*health:\s*\{/;

function listProdTsxFiles(dir: string): string[] {
  return (fs.readdirSync(dir, { recursive: true } as any) as string[])
    .filter((p) => p.endsWith('.tsx') && !p.includes('__tests__') && !p.includes('.test.'))
    .map((p) => path.join(dir, p));
}

describe('plan 275 F2 — ctx real en PipelineYamlPreview', () => {
  it('ningún archivo de producción de components/devops/ pasa un ctx.health inventado', () => {
    const ofensores: string[] = [];
    for (const file of listProdTsxFiles(DEVOPS_DIR)) {
      const content = fs.readFileSync(file, 'utf-8');
      if (CTX_LITERAL_RE.test(content)) ofensores.push(path.relative(DEVOPS_DIR, file));
    }
    expect(ofensores, `Objetos ctx.health literales (fabricados) en: ${ofensores.join(', ')}`).toEqual([]);
  });
});
```

**Comando y ROJO esperado ANTES del fix:**
```
cd "Stacky Agents\frontend"; npx vitest run src/components/devops/__tests__/plan275PipelineYamlPreviewCtx.test.ts
```
Falla con `ofensores = ['PublicationsSection.tsx']`.

**Diff exacto (`PublicationsSection.tsx:539-543`, verificado hoy):**
```diff
             <PipelineYamlPreview
               spec={materializedDraft}
-              ctx={{ health: { flag_enabled: true, generator_enabled: true, trigger_enabled: false, publications_enabled: true }, refetchHealth: () => {} }}
+              ctx={ctx}
               localErrors={[]}
             />
```
`ctx` ya es un identificador en scope en este componente (usado sin modificación en las líneas 527, 547, 566 y 570 del mismo archivo — `PreflightPanel ctx={ctx}`, `TriggerPipelineSection ctx={ctx}`, `ProductionFlow ctx={ctx}`). No se crea ninguna variable nueva.

**Comando y VERDE esperado DESPUÉS del fix:**
```
cd "Stacky Agents\frontend"; npx vitest run src/components/devops/__tests__/plan275PipelineYamlPreviewCtx.test.ts
```

**Criterio de aceptación (binario):** 0 fallas; `ofensores` es `[]`.

**Flag:** ninguna — es un fix de defecto (el dato mostrado no correspondía al estado real), no hay comportamiento alternativo que preservar.

**Impacto por runtime:** ninguno / idéntico en los tres. Fallback: no aplica.

**Trabajo del operador:** ninguno. La previsualización simplemente empieza a reflejar el estado real de sus propias flags — si las tiene todas en `True` (el default hoy), el cambio es imperceptible; si alguna está en `False`, ahora lo verá reflejado ahí en vez de en el momento de publicar.

---

### F3 — Primer pago de la deuda visual concentrada: dedup del literal de padding de botón

**Objetivo:** extraer el literal `style={{ padding: '10px 20px' }}`, repetido 7 veces idéntico en los dos archivos de `components/devops/` con más tráfico y más deuda de estilos inline (H-15), a una única clase CSS compartida, sin cambiar un solo píxel del resultado visual. **Valor:** primer corte real, mecánico y verificable de la deuda que la auditoría documentó como "fuertemente concentrada en DevOps" — hecho **por concentración** como la propia auditoría prescribe, no como migración masiva.

**Archivos a editar:**
- `frontend/src/components/devops/devops.module.css` — agregar la clase `.btnLg`.
- `frontend/src/components/devops/PipelineBuilderSection.tsx` — 4 sitios (líneas 576, 584, 592, 729, verificadas hoy).
- `frontend/src/components/devops/PublicationsSection.tsx` — 3 sitios (líneas 362, 556, 560, verificadas hoy).
- `frontend/src/__tests__/uiDebtBaseline.json` — regenerado con `UI_DEBT_REGEN=1` (nunca a mano).

**Archivos a crear:**
- `frontend/src/components/devops/__tests__/plan275ButtonPaddingRatchet.test.ts`

**Por qué SOLO este literal y no los otros 27+31 `style={{}}` de esos archivos:** son objetos distintos entre sí (paddings de 8px, `flex`, `marginBottom`, `fontSize`, etc.), y decidir su clase de reemplazo es una decisión de diseño que un modelo menor no puede tomar sin inferir — exactamente lo que H-15 prohíbe hacer en masa. Este literal es el único que se repite **byte a byte** en ambos archivos, así que extraerlo no es una decisión de diseño: es deduplicación mecánica de un string ya idéntico.

**Test PRIMERO:**

```ts
/**
 * plan275ButtonPaddingRatchet.test.ts — Plan 275 F3 (paga deuda de H-15 POR
 * CONCENTRACIÓN: el literal `style={{ padding: '10px 20px' }}` se repite 7
 * veces IDÉNTICO en los dos archivos más deudores con tráfico real de
 * components/devops/ — PipelineBuilderSection.tsx (H-15, 53 inline) y
 * PublicationsSection.tsx (H-15, 34 inline). Se extrae a `.btnLg` en
 * devops.module.css. NO es una migración masiva (H-15 la prohíbe
 * explícitamente): solo el duplicado EXACTO, mecánico, sin cambio visual.
 * Se corre CONTRA el defecto: HOY da ROJO (4 y 3 ocurrencias).
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const DEVOPS_DIR = path.join(process.cwd(), 'src', 'components', 'devops');
const LITERAL_RE = /style=\{\{ padding: '10px 20px' \}\}/g;

function count(file: string): number {
  const p = path.join(DEVOPS_DIR, file);
  const m = fs.readFileSync(p, 'utf-8').match(LITERAL_RE);
  return m ? m.length : 0;
}

describe('plan 275 F3 — dedup del literal de padding de botón', () => {
  it('PipelineBuilderSection.tsx y PublicationsSection.tsx no contienen el literal (extraído a .btnLg)', () => {
    expect(count('PipelineBuilderSection.tsx')).toBe(0);
    expect(count('PublicationsSection.tsx')).toBe(0);
  });

  it('devops.module.css declara .btnLg con el mismo padding que reemplaza', () => {
    const css = fs.readFileSync(path.join(DEVOPS_DIR, 'devops.module.css'), 'utf-8');
    expect(css).toMatch(/\.btnLg\s*\{[^}]*padding:\s*10px 20px/);
  });
});
```

**Comando y ROJO esperado ANTES del fix:**
```
cd "Stacky Agents\frontend"; npx vitest run src/components/devops/__tests__/plan275ButtonPaddingRatchet.test.ts
```
Falla: `count('PipelineBuilderSection.tsx')` da `4` (no `0`), `count('PublicationsSection.tsx')` da `3` (no `0`), y `.btnLg` no existe en `devops.module.css`.

**1. Diff de `frontend/src/components/devops/devops.module.css`** — agregar después de la regla `.btnSuccess:disabled` (líneas 98-102 verificadas hoy), antes del comentario `/* ── Texto semántico ── */` (línea 104):
```diff
 .btnSuccess:disabled {
   background: var(--text-faint);
   color: var(--bg-base);
   cursor: not-allowed;
 }
 
+/* Plan 275 F3 — modificador de tamaño, se compone con .btnPrimary/.btnSuccess
+   o solo. Declarado DESPUÉS de .btnPrimary/.btnSuccess para ganar el cascade
+   en `padding` cuando se combinan (misma especificidad, orden de fuente). */
+.btnLg {
+  padding: 10px 20px;
+}
+
 /* ── Texto semántico ──────────────────────────────────────────────────── */
```

**2. Diff de `frontend/src/components/devops/PipelineBuilderSection.tsx`** (4 sitios). El patrón es siempre `className={styles.btnXxx}` seguido de `style={{ padding: '10px 20px' }}` en la línea siguiente — se combina en una sola línea `className` y se borra la línea `style`:

- Líneas 574-577 (`Empezar con ejemplo`):
```diff
             <button
               onClick={() => setSpec(starterSpec())}
-              className={styles.btnSuccess}
-              style={{ padding: '10px 20px' }}
+              className={`${styles.btnSuccess} ${styles.btnLg}`}
             >
```
- Líneas 581-585 (`+ stage`):
```diff
             <button
               onClick={() => setSpec(addStage(spec))}
-              className={styles.btnPrimary}
-              style={{ padding: '10px 20px' }}
+              className={`${styles.btnPrimary} ${styles.btnLg}`}
             >
```
- Líneas 589-593 (`Insertá acciones sueltas`):
```diff
             <button
               onClick={handleStartEmptyJob}
-              className={styles.btnPrimary}
-              style={{ padding: '10px 20px' }}
+              className={`${styles.btnPrimary} ${styles.btnLg}`}
               title="Crea un stage y un job vacíos y los selecciona, para insertar acciones prehechas sueltas"
             >
```
- Líneas 724-730 (`Commit al repo…`):
```diff
           <button
             onClick={() => setShowCommitModal(true)}
             disabled={localErrors.length > 0}
             title={localErrors.length > 0 ? 'Resolvé los avisos primero' : undefined}
-            className={styles.btnSuccess}
-            style={{ padding: '10px 20px' }}
+            className={`${styles.btnSuccess} ${styles.btnLg}`}
           >
```

**3. Diff de `frontend/src/components/devops/PublicationsSection.tsx`** (3 sitios):

- Líneas 359-363 (`Crear preset TODO`):
```diff
             <button
               onClick={() => void handleCreateTodoPreset()}
-              className={styles.btnSuccess}
-              style={{ padding: '10px 20px' }}
+              className={`${styles.btnSuccess} ${styles.btnLg}`}
             >
```
- Líneas 553-557 (`Commit al repo…`, el mismo bloque que toca F2):
```diff
               <button
                 onClick={() => setShowCommitModal(true)}
-                className={styles.btnSuccess}
-                style={{ padding: '10px 20px' }}
+                className={`${styles.btnSuccess} ${styles.btnLg}`}
               >
```
- Línea 560 (`Guardar como borrador` — **sin** `className` previo, hay que agregarlo):
```diff
-              <button onClick={() => void handleSaveAsDraft()} style={{ padding: '10px 20px' }}>
+              <button onClick={() => void handleSaveAsDraft()} className={styles.btnLg}>
```

**4. Regenerar el baseline del ratchet (solo porque la deuda BAJÓ, nunca a mano):**
```
cd "Stacky Agents\frontend"
$env:UI_DEBT_REGEN='1'; npx vitest run src/__tests__/uiDebtRatchet.test.ts; Remove-Item Env:\UI_DEBT_REGEN
```
Verificar el diff de `src/__tests__/uiDebtBaseline.json`: **solo** deben cambiar dos números, `components/devops/PipelineBuilderSection.tsx` de `53` a `49` y `components/devops/PublicationsSection.tsx` de `34` a `31`, ambos bajo `inlineStyleByFile`. Si cambia cualquier otro archivo o cualquier número de `hexByFile`, **no commitear** — significa que hay deuda ajena mezclada en el working tree y hay que aislarla primero (mismo gotcha que el plan 273 §F3: *"Regenerar con `UI_DEBT_REGEN=1` está prohibido si arrastra deuda ajena"*).

**Comando y VERDE esperado DESPUÉS del fix (los tres, en este orden):**
```
cd "Stacky Agents\frontend"; npx vitest run src/components/devops/__tests__/plan275ButtonPaddingRatchet.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeContrast.test.ts
```
El tercero se corre porque `.btnLg` es una regla nueva de `devops.module.css` — no toca ningún color ni contraste (solo `padding`), pero confirma que el archivo sigue en el mismo estado de gates de tema que tenía en F0 (delta cero, no "todo verde": los fallos preexistentes de `themeContrast.test.ts` que no son de este archivo, si los hay, no son responsabilidad de este plan).

**Criterio de aceptación (binario):** los 3 comandos en 0 fallas nuevas; el diff de `uiDebtBaseline.json` toca únicamente las 2 líneas citadas.

**Flag:** ninguna — refactor de CSS sin cambio de comportamiento ni de capacidad.

**Impacto por runtime:** ninguno / idéntico en los tres. Fallback: no aplica.

**Trabajo del operador:** ninguno. El resultado renderizado es idéntico píxel a píxel (`padding: 10px 20px` sigue aplicándose exactamente donde se aplicaba).

---

### F4 — Verificación integradora y cierre de frontera

**Objetivo:** confirmar que las tres fases conviven sin regresión cruzada y que el plan no tocó ningún archivo fuera de su frontera declarada con el plan 273. **Valor:** cierre auditable — el mismo patrón de verificación final que exige el propio riel de "sin falsos verdes".

**No se crean archivos nuevos.** Solo comandos, corridos desde `Stacky Agents/frontend` salvo que se indique lo contrario.

1. Correr, uno por uno, TODOS los tests nuevos y editados de F1-F3:
```
npx vitest run src/pages/__tests__/plan275DevOpsGroupBalance.test.ts
npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts
npx vitest run src/components/devops/__tests__/plan275PipelineYamlPreviewCtx.test.ts
npx vitest run src/components/devops/__tests__/plan275ButtonPaddingRatchet.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/themeContrast.test.ts
npx vitest run src/pages/__tests__/DevOpsCockpitClosure.test.ts
npx vitest run src/pages/__tests__/DevOpsCockpitRegression.test.ts
npx vitest run src/pages/__tests__/DevOpsPage.test.ts
```
Los 9 comandos en 0 fallas.

2. Confirmar que el diff completo del plan no toca ningún archivo de la frontera del plan 273 (`App.tsx`, `api/client.ts`, `flagHealth.ts`, `services/routes.ts`, `PageErrorBoundary.tsx`, `theme.css`):
```
git diff --stat -- "Stacky Agents/frontend/src/App.tsx" "Stacky Agents/frontend/src/api/client.ts" "Stacky Agents/frontend/src/flagHealth.ts" "Stacky Agents/frontend/src/services/routes.ts" "Stacky Agents/frontend/src/components/PageErrorBoundary.tsx" "Stacky Agents/frontend/src/theme.css"
```
Resultado esperado: salida **vacía** (ningún archivo de esa lista en el diff).

3. Confirmar que el diff completo toca exactamente los 7 archivos declarados en F1-F3 (más el baseline regenerado) y ninguno más:
```
git diff --stat -- "Stacky Agents/frontend/src/pages/devopsCockpitShell.ts" "Stacky Agents/frontend/src/pages/DevOpsPage.tsx" "Stacky Agents/frontend/src/pages/__tests__/devopsCockpitShell.test.ts" "Stacky Agents/frontend/src/components/devops/PublicationsSection.tsx" "Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx" "Stacky Agents/frontend/src/components/devops/devops.module.css" "Stacky Agents/frontend/src/__tests__/uiDebtBaseline.json"
```
Más los 3 archivos de test nuevos (`git status` debe listarlos como `??` o `A`).

**Criterio de aceptación (binario):** los 9 tests en verde, el comando 2 sin salida, el comando 3 solo con los 7 archivos esperados.

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Olvidar el paso 3.c de F1 (agregar `gobernar` al objeto hardcodeado de `partitionForBar`) y que `TypeError` rompa el render del cockpit en runtime. | El test `plan275DevOpsGroupBalance.test.ts` no lo detecta directamente (usa `sectionsOfGroup`, no `partitionForBar`), por eso F1 exige correr también `devopsCockpitShell.test.ts` completo, que sí ejercita `partitionForBar` con datos reales y hubiera lanzado la excepción en el test `'grupo con TODAS gateadas...'`. |
| Un tercer plan en vuelo toca `DevOpsPage.tsx` en paralelo (los únicos verificados en F0 son 273, que declara frontera explícita, y 267/268/239, ya IMPLEMENTADOS). | F0 exige re-correr `git log --all --grep="plan-273"` antes de empezar; si aparece cualquier otra rama activa tocando `pages/DevOpsPage.tsx`, coordinar antes de F1 (no hay forma automática de detectarlo, es responsabilidad de quien ejecuta el plan). |
| Regenerar `uiDebtBaseline.json` con `UI_DEBT_REGEN=1` arrastra deuda ajena si el working tree tiene otros cambios sin commitear al momento de F3. | F3 exige revisar el diff del JSON línea por línea antes de commitear; el propio `assertNoIncrease` del ratchet ya rechaza el regen si algún archivo subió, pero no evita que el regen "adopte" una baja ajena como si fuera de este plan — de ahí la instrucción explícita de revisar el diff. |
| El nombre de clase `.btnLg` colisiona con una clase ya existente en otro `.module.css` importado en el mismo archivo. | No aplica: CSS Modules hashea la clase POR ARCHIVO (gotcha conocido), así que `styles.btnLg` de `devops.module.css` nunca colisiona con una clase de otro módulo — cada `import styles from './archivo.module.css'` es un namespace propio. |

## 6. Fuera de scope

- **Migración masiva de los 723 `style={{}}` / 1314 hex literales del repo (H-15).** Explícitamente prohibida por la propia auditoría. Este plan solo paga el duplicado exacto de 7 ocurrencias como primer corte demostrativo.
- **`BlockProperties.tsx` (58 inline, #1 del top-10 de H-15).** Es un editor de bloques de bajo tráfico comparado con `PipelineBuilderSection.tsx`/`PublicationsSection.tsx`; sus 58 literales no comparten un duplicado exacto entre sí verificado en esta corrida — pagarlos requiere decisiones de diseño por objeto, fuera del criterio mecánico de este plan. Candidato para un plan futuro dedicado.
- **Los 27 `style={{}}` restantes de `PipelineBuilderSection.tsx` y los 31 restantes de `PublicationsSection.tsx`.** Mismo motivo: no son duplicados exactos, requieren juicio de diseño.
- **H-10 (breakpoints ad hoc, `DevOpsCockpit.module.css:39` y `DevOpsPage.module.css:70`).** Verificado en esta corrida: **ambos archivos YA tienen** `@media (max-width: 900px)` con reglas de adaptación (plan 239 F7a) — no es un defecto de DevOps específico, es una decisión de arquitectura repo-wide (12 archivos, 6 breakpoints ad hoc sin token compartido) que la auditoría deja explícitamente pendiente de decisión (Opción A vs B, §H-10). Tokenizar solo para DevOps fragmentaría más la decisión.
- **H-05 (nav v1 global sin `flex-wrap`/`overflow-x`, `App.module.css:7-16`).** No es del cockpit DevOps — es la navegación de primer nivel de toda la app (18 tabs). El cockpit DevOps YA tiene `overflow-x: auto` en su propia barra (`DevOpsCockpit.module.css:10-11`), verificado en esta corrida.
- **H-06 / H-07 / H-08 / H-09 / H-12 / H-13 / H-14 / H-16 / H-17 de la auditoría.** Ninguno es específico del panel DevOps (son transversales al frontend o de backend); quedan para los planes que ya los tienen asignados (273 cubre H-01 a H-04 y B-06; el resto queda en el backlog general de la auditoría).
- **Catálogo de acciones DevOps (plan 267).** Ya implementado 9/9; este plan no lo toca ni lo extiende.
- **Cualquier flag nueva.** Los tres cambios corrigen defectos sobre funcionalidad `default=True` existente.

## 7. Glosario

- **Cockpit DevOps / shell v3:** el layout de dos niveles (grupos → secciones) del panel DevOps, introducido en el plan 239. `DEVOPS_SECTION_GROUPS` son los 5 grupos de primer nivel (tras este plan); cada sección de `DEVOPS_SECTIONS` pertenece a uno.
- **`healthKey` / `gateFlagKey`:** por cada sección, la clave de `DevOpsHealth` que determina si está habilitada y la flag que el `FlagGateBanner` ofrece prender si no lo está. Ninguno de los dos se toca en este plan.
- **Ratchet de deuda visual (`uiDebtRatchet.test.ts`):** test que congela, archivo por archivo, la cantidad de `style={{` y de colores hex; solo puede bajar, nunca subir, respecto de `uiDebtBaseline.json`.
- **`ctx` (DevOpsSectionContext):** el objeto que cada sección DevOps recibe con `health`, `refetchHealth`, `selectedServer`, etc. — el estado real de las flags y del servidor activo.
- **B-08 / H-11:** identificadores de hallazgo de la auditoría UX/UI 2026-07-29 para el mismo defecto (ctx.health fabricado en `PublicationsSection.tsx`).

## 8. Orden de implementación

1. F0 — línea base (solo verificación, sin código).
2. F1 — rebalance de grupos de navegación (`devopsCockpitShell.ts` + `DevOpsPage.tsx` + su test hermano).
3. F2 — ctx real en `PipelineYamlPreview` (independiente de F1, puede ir antes o después, se numera F2 por prioridad de impacto en confianza del operador).
4. F3 — dedup del literal de padding (toca el mismo archivo que F2, `PublicationsSection.tsx`, en un bloque adyacente — hacerlo DESPUÉS de F2 para evitar un diff simultáneo confuso sobre las mismas líneas).
5. F4 — verificación integradora y cierre de frontera.

## 9. Definición de Hecho (DoD)

- Los 4 archivos de test nuevos existen y están en verde: `plan275DevOpsGroupBalance.test.ts`, `plan275PipelineYamlPreviewCtx.test.ts`, `plan275ButtonPaddingRatchet.test.ts`, y `devopsCockpitShell.test.ts` actualizado.
- `DEVOPS_SECTION_GROUPS` tiene 5 grupos; ningún grupo tiene más de 5 secciones.
- `PublicationsSection.tsx` no contiene ningún `ctx={{ health: {` literal.
- `PipelineBuilderSection.tsx` y `PublicationsSection.tsx` no contienen `style={{ padding: '10px 20px' }}`; `devops.module.css` declara `.btnLg`.
- `uiDebtBaseline.json` refleja la baja (53→49, 34→31) y ningún otro número cambió.
- `uiDebtRatchet.test.ts` y `themeContrast.test.ts` en el mismo estado de F0 (delta cero, no regresión).
- Ningún archivo de la frontera del plan 273 (`App.tsx`, `api/client.ts`, `flagHealth.ts`, `routes.ts`, `PageErrorBoundary.tsx`, `theme.css`) aparece en el diff.
- Cero flags nuevas. Cero trabajo nuevo para el operador.
