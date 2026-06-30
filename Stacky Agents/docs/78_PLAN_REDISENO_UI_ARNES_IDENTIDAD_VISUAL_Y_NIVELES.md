# Plan 78 — Rediseño UI del Arnés: identidad visual, dashboard de salud y niveles Simple/Experto

> **Versión:** v2 → v3 (segunda pasada adversarial — juez `criticar-y-mejorar-plan`).
>
> **CHANGELOG v3:**
> - **C7 (IMPORTANTE) — F3+F7: test `HarnessFlagsPanel.test.tsx` rompe con la eliminación del profileBar.**
>   El test existente (línea 172) aserta `screen.getByText(/Perfil activo/i)`. F3 elimina el
>   `<div className={styles.profileBar}>` que contiene ese texto y lo reemplaza por el hero
>   ("Estado del Arnés", "Perfil:"). El plan también nombraba mal el archivo en todo su cuerpo
>   (apuntaba a un `SettingsPage.harness.test.tsx` inexistente; archivo real: `HarnessFlagsPanel.test.tsx`). F7 ahora
>   exige actualizar esa aserción y el nombre del archivo fue corregido en todo el plan.
> - **C8 (IMPORTANTE) — F3: barra llamada "de salud" premia encender flags → ENGAÑOSA.**
>   `totalActive / totalFlags` crece al activar flags experimentales, que son default OFF a
>   propósito. Llamarla "salud" contradice el KPI de claridad. Renombrada a "% de flags activas"
>   en el hero; comentario explícito en código; riesgo R6 extendido; título del hero cambiado a
>   "Arnés — Configuración activa" para no confundir con salud operativa real (Plan 46).
> - **C9 (IMPORTANTE) — [ADICIÓN ARQUITECTO] `intent` incluida en el predicado de búsqueda.**
>   Sin este cambio, buscar "publicar épica" o "elegir modelo" no matchea la `intent` de la
>   categoría → "navegación por intención" queda como decoración visual. Fix quirúrgico: 1 línea
>   en el filtro de `orderedSections`. Hace REAL la promesa del objetivo sin dependencias nuevas.
> - **C10 (MENOR) — Nombre de archivo corregido en todo el plan.**
>   `HarnessFlagsPanel.test.tsx` → `HarnessFlagsPanel.test.tsx` (verificado en el repo).
> - **C11 (MENOR) — Honestidad del gate pytest de partición aclarada.**
>   El pytest valida la consistencia de datos del backend, no la función TS que shipea. Aclarado
>   en el comentario del test y en F7/DoD para no sobrevender.
> - **C12 (MENOR) — a11y del toggle: `role="group"` + `aria-label` añadidos en F4.**
>   Sin `role="group"`, los dos botones no comunican selección mutuamente excluyente a lectores
>   de pantalla.
> - **C13 (MENOR) — F7 ahora incluye criterio de aceptación para búsqueda + catch-all.**
>   El claim "búsqueda activa abre el catch-all" queda con gate explícito en DoD.
>
> **CHANGELOG v2:**
> - **C1 (IMPORTANTE) — F3: instrucción "se absorben" era ambigua para modelos menores.**
>   V1 no aclaraba si `<div className={styles.profileBar}>` y `<div className={styles.summary}>`
>   se eliminaban o convivían con el hero nuevo (riesgo de duplicación de UI). V2 lo hace
>   EXPLÍCITO: ambos `<div>` se **eliminan** del JSX; sus datos y su lógica se conservan en
>   el hero. También reemplaza referencias por número de línea (que driftean) por anclas
>   simbólicas.
> - **C2 (IMPORTANTE) — invariante de partición F4: cerrado con test ejecutable real.**
>   V1 dejaba el invariante más crítico del plan solo como "convención no bloqueante" con
>   vitest ausente. **[ADICIÓN ARQUITECTO]:** extraer la lógica de partición a una función
>   PURA `partitionSectionsByTier` en `harnessVisuals.ts` (frontend) y agregar un test
>   ejecutable en `test_harness_flags.py` (backend) que valide la semántica del predicado
>   `simple`/`advanced`. Cierra el agujero: el corazón del plan tiene al menos un gate real.
> - **C3 (IMPORTANTE) — bug icono duplicado en `CATEGORY_VISUALS`.**
>   V1 asignaba `Activity` tanto a `fiabilidad_ciclo_vida` como a `observabilidad_notif`,
>   rompiendo la premisa de reconocimiento visual por icono. Corregido: `observabilidad_notif`
>   usa `Monitor`.
> - **C4 (MENOR) — mock de SettingsPage sin `tier` puede fallar el test en F7.**
>   Si `tier` llega `undefined`, el flag cae al catch-all colapsado → `getByText` puede no
>   encontrarlo. V2 lo documenta en F7 y exige agregar `tier: "simple"` al mock.
> - **C5 (MENOR) — F6: tokens visuales concretos añadidos.**
>   V1 dejaba todos los valores CSS "a criterio estético del implementador", insuficiente
>   para evitar un resultado banal. V2 provee anclas mínimas (padding, gradiente, sombra,
>   radio, acento del toggle).
> - **C6 (MENOR) — referencias por número de línea reemplazadas por símbolos** en F3/F4/F5
>   para que no driftéen entre fases.
>
> **Predecesor directo:** Plan 63 (`63_PLAN_REDISENO_UI_CONFIG_ARNES_CLARIDAD.md`), que ya entregó categorías colapsables, descripción inline, badge `def:`, búsqueda, resalte `activeRow` y métricas separadas. **Este plan NO re-hace nada de eso**: es la capa de ESTÉTICA + INTUICIÓN + SEGMENTACIÓN POR NIVEL encima de esa base.
> **Tipo de cambio:** UI pura del frontend + UN campo aditivo y opcional en el contrato del backend (metadata de categoría). **Cero cambio de semántica de cualquier flag.**

---

## 1. Objetivo y KPI

### Objetivo (1 párrafo)
Transformar `HarnessFlagsPanel` de una lista funcional-pero-densa (~142 flags en 14 categorías colapsables) en un **panel con identidad visual y dos niveles de profundidad**: (a) un **hero/dashboard de Estado del Arnés** arriba (perfil activo + cuántas flags activas + salud visual), (b) **color + icono por categoría** para que el ojo navegue por reconocimiento y no por lectura, y (c) un **toggle Simple ↔ Experto** (persistido en `localStorage`) que muestra primero lo que la mayoría necesita y esconde —sin eliminar— lo avanzado. El criterio de qué es "Simple" NO vive en una lista manual del frontend: se sirve desde el backend como metadata aditiva de cada categoría (`tier` + `intent`), fuente única de verdad blindada por un test bidireccional (igual que el Plan 63 blindó `_CATEGORY_KEYS`). **Toda flag sigue 100% accesible y editable por UI**: el modo Simple jamás oculta una flag sin ofrecer una sección catch-all "Todo lo demás" que la contiene.

### KPI / impacto esperado (medible)
- **Descubribilidad:** 100% de las flags del registry siguen alcanzables desde la UI en cualquier modo. **Verificable** por `test_every_category_has_tier_and_intent` (toda categoría tiene `tier`/`intent`) + el catch-all garantizado por diseño (criterio de aceptación binario en F4).
- **Carga cognitiva inicial:** en modo Simple, el operador ve solo las categorías `tier=="simple"` + 1 sección catch-all colapsada, en vez de las 14 abiertas según actividad. Reducción medible de secciones expandidas por defecto (de "todas las que tienen flag activa" a "solo las simple + catch-all colapsado").
- **Cero drift front↔backend:** ninguna flag nueva queda invisible; al agregarse al registry queda en una categoría, y la categoría ya tiene `tier`/`intent` → aparece automáticamente. **Verificable** por los tests de F0.
- **Estética:** identidad visual consistente (15 colores/iconos de categoría, todos distintos) y hero con barra de salud, sin sumar dependencias (usa `lucide-react`, ya instalado, `package.json:14`).
- **Gate binario del frontend:** `npm run build` (que ejecuta `tsc --noEmit`) con **0 errores**.

---

## 2. Por qué ahora / gap que cierra

El Plan 63 resolvió la **claridad estructural** (agrupar, describir, buscar). Quedó pendiente la **capa humana**: el panel sigue siendo una grilla monocroma de 14 `<details>` que se abren según actividad; un operador poco técnico no sabe por dónde empezar, y todo "pesa" visualmente igual. El pedido textual del operador es: (1) **más intuitivo para más gente** (incluida gente poco técnica), (2) **más dividido/segmentado por intención**, (3) y **sobre todo más estético y llamativo**. El Plan 63 es la base de datos visual correcta (categorías servidas por el backend); el Plan 78 le pone **piel** (color/icono/hero) y **profundidad progresiva** (Simple/Experto) sin tocar el pipeline ni la semántica de ninguna flag.

### Resultado del debate (Brainstormer ⇄ UltraEficientCode)
- **ENTRA — #4 Identidad visual + dashboard de salud (el ORO):** color + icono por categoría y un hero "Estado del Arnés". Es máximo impacto estético con costo mínimo porque el mapa es por las **14 categorías ya fijas** en `FLAG_CATEGORIES`. Se implementa como un mapa estático `CATEGORY_VISUALS` en el frontend (slug→{color,icon}) — los slugs (`runtimes_cli`, etc.) son **estables** y ya viajan en el contrato (`HarnessFlagCategory.id`). Si llega una categoría sin entrada, fallback gris + icono genérico (nunca rompe).
- **ENTRA TRANSFORMADO — #1 Navegación por intención + #3 Modo Simple/Experto:** el Brainstormer marcó como **supuesto frágil** que las listas curadas de "intención" y "Simple" vivieran en el frontend (riesgo de drift → flag nueva invisible). **Lo transformo**: la intención (`intent`, frase humana) y el nivel (`tier`, `"simple"|"advanced"`) se declaran **en el backend, como metadata aditiva de cada `CategorySpec`** (no por flag — más barato, no toca las ~142 entradas de `_CATEGORY_KEYS`), se sirven por el endpoint que ya existe, y se blindan con `test_every_category_has_tier_and_intent`. Así "Simple" es **derivable de datos del backend**, fuente única de verdad, exactamente como pidió el blindaje. El toggle Simple/Experto es solo presentación, persistido en `localStorage`.
- **CIERRE DEL SUPUESTO FRÁGIL (red de seguridad doble):** (a) el modo Experto muestra TODAS las categorías (es el panel del Plan 63 intacto); (b) el modo Simple muestra las `tier=="simple"` **más** una sección catch-all **"Todo lo demás"** que contiene el 100% del resto de categorías (colapsada). Ergo ninguna flag queda jamás oculta en ningún modo. Esto es invariante de diseño, verificado en F4.
- **DESCARTADO — nada.** Las tres ideas sobreviven (una transformada). No se agregó librería de animación (CSS puro) ni de iconos (lucide-react ya está). Se descarta explícitamente cualquier "intención" como lista manual en el front (anti-patrón de drift).

---

## 3. Principios y guardarraíles (codificados por fase)

1. **3 runtimes con paridad — impacto NINGUNO.** Es UI pura del frontend + metadata de presentación en el backend. **No toca** `agent_runner.py`, `agents/base.py`, ningún `*_runner.py`, ni el evaluador `cli_feature_flags.py`. Las flags conservan idéntico nombre, tipo, default y efecto en Codex / Claude Code / GitHub Copilot Pro. Cada fase lo declara explícito.
2. **Cero trabajo extra al operador.** La preferencia de modo (Simple/Experto) y de tema se guarda en `localStorage` del navegador — **no** es config del operador, **no** es flag del pipeline, **no** se persiste en `.env` ni en la BD. Default seguro: arranca en **Simple** (lo menos abrumador). Backward-compatible: si el backend aún no envía `tier`/`intent` (deploy viejo), el front degrada a tratar todo como `advanced` y el modo Simple muestra solo el catch-all (nada se rompe, nada se oculta).
3. **Regla dura config-por-UI / descubribilidad total.** Ninguna flag se saca del panel. El modo Simple OCULTA visualmente categorías `advanced`, pero el catch-all "Todo lo demás" (modo Simple) y el listado completo (modo Experto) garantizan que TODA flag siga accesible y editable. El supuesto frágil del Brainstormer se cierra acá.
4. **Aditivo y blindado en el backend.** El campo nuevo (`tier`, `intent`) se agrega a `CategorySpec` con **default seguro** (`tier="advanced"`, `intent=""`) para no romper construcciones existentes, se expone en `list_categories()` de forma aditiva al JSON, y se blinda con test bidireccional. **No cambia** la semántica de ninguna flag ni el `_CATEGORY_KEYS`.
5. **Sin libs pesadas nuevas.** Animaciones con CSS (`transition`, `@keyframes`). Iconos con `lucide-react` (ya en `package.json`). Nada de framer-motion, nada de icon-packs nuevos.
6. **Reusar lo existente.** Se reusa el endpoint `GET /api/harness-flags`, React Query (`queryKey: ["harness-flags"]`), los perfiles off/safe/full (`POST /api/harness-flags/profile`), todas las clases CSS del Plan 63 (`HarnessFlagsPanel.module.css`) y los sub-componentes `FlagRow`/`JsonInput`. Solo se agregan clases/elementos nuevos sin romper los que usa `HarnessFlagsPanel.test.tsx`.
7. **Mono-operador sin auth / human-in-the-loop / no degradar.** No introduce autonomía, roles ni decisiones automáticas; es presentación. No degrada ninguna ruta ni endpoint.

---

## 4. Fases

> **Orden de dependencia:** F0 (contrato backend + blindaje) → F1 (tipos + visuals frontend) → F2 (hook de preferencia localStorage) → F3 (hero/dashboard) → F4 (modo Simple/Experto + catch-all) → F5 (identidad visual por categoría) → F6 (pulido estético/animación) → F7 (no-regresión y DoD).
> Cada fase es autocontenida y verificable sola. F1..F7 son frontend; F0 es backend. F3..F6 dependen de F1 y F2.

---

### F0 — Backend: metadata aditiva `tier` + `intent` por categoría (fuente única de verdad)

**Objetivo (1 frase):** Que cada categoría declare en el backend su nivel (`tier`: `"simple"` o `"advanced"`) y su intención humana (`intent`: frase tipo "¿qué querés lograr?"), servida por el endpoint existente, sin tocar ninguna flag ni `_CATEGORY_KEYS`.
**Valor:** Es el cimiento que vuelve "Simple" e "intención" **derivables de datos**, cerrando el supuesto frágil del debate.

**Archivos exactos:**
- `Stacky Agents/backend/services/harness_flags.py` (modificar `CategorySpec`, `FLAG_CATEGORIES`, `list_categories`).
- `Stacky Agents/backend/tests/test_harness_flags.py` (agregar tests — TESTS PRIMERO).

**TESTS PRIMERO** — agregar en `test_harness_flags.py`:

```python
def test_every_category_has_tier_and_intent():
    """Bidireccional: toda CategorySpec declara tier válido e intent no vacío.
    Impide drift — una categoría nueva sin tier/intent rompe CI a propósito."""
    from services.harness_flags import FLAG_CATEGORIES
    valid_tiers = {"simple", "advanced"}
    for c in FLAG_CATEGORIES:
        assert c.tier in valid_tiers, f"Categoría '{c.id}' tiene tier inválido: {c.tier!r}"
        assert isinstance(c.intent, str) and c.intent.strip(), \
            f"Categoría '{c.id}' tiene intent vacío"

def test_list_categories_exposes_tier_and_intent():
    """list_categories() expone tier e intent de forma ADITIVA (sin romper id/label/description)."""
    from services.harness_flags import list_categories
    for c in list_categories():
        assert {"id", "label", "description", "tier", "intent"} <= set(c.keys())
        assert c["tier"] in {"simple", "advanced"}

def test_at_least_one_simple_and_one_advanced_category():
    """Garantiza que el modo Simple no quede vacío ni absorba todo (sanidad del diseño de niveles)."""
    from services.harness_flags import FLAG_CATEGORIES
    tiers = {c.tier for c in FLAG_CATEGORIES}
    assert "simple" in tiers, "Ninguna categoría es 'simple' → modo Simple quedaría vacío"
    assert "advanced" in tiers, "Ninguna categoría es 'advanced' → no hay catch-all que poblar"

def test_partition_semantics_simple_vs_advanced():
    """[ADICIÓN ARQUITECTO — C2] Valida que el predicado tier=='simple' y su complemento
    tier!='simple' particionan el total sin solape ni pérdida.
    Es el equivalente ejecutable del invariante de partición de F4 (frontend),
    corriendo en pytest donde vitest no está disponible."""
    from services.harness_flags import FLAG_CATEGORIES
    all_ids = [c.id for c in FLAG_CATEGORIES]
    simple_ids = [c.id for c in FLAG_CATEGORIES if c.tier == "simple"]
    rest_ids   = [c.id for c in FLAG_CATEGORIES if c.tier != "simple"]
    # Sin solape
    assert len(set(simple_ids) & set(rest_ids)) == 0, "Solapamiento entre simple y rest — imposible por definición"
    # Sin pérdida
    assert sorted(simple_ids + rest_ids) == sorted(all_ids), \
        "La unión simple+rest != FLAG_CATEGORIES — se perdió una categoría"
```

**Comando exacto de test (desde `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend`):**
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_harness_flags.py -q
```

**Implementación (diff ilustrativo, `harness_flags.py`):**

1. Extender el dataclass (campos nuevos con default seguro → aditivo, no rompe llamadas posicionales existentes porque van al final):
```python
@dataclass(frozen=True)
class CategorySpec:
    id: str
    label: str
    description: str
    tier: str = "advanced"   # "simple" | "advanced" — nivel de profundidad para la UI (Plan 78)
    intent: str = ""         # frase humana "¿qué querés lograr?" para navegación por intención (Plan 78)
```

2. Anotar las 15 entradas de `FLAG_CATEGORIES` con `tier` e `intent`. **Mapa exacto a usar** (decisión cerrada — el implementador NO elige):

| id | tier | intent (frase humana exacta) |
|----|------|------------------------------|
| `runtimes_cli` | `simple` | "Elegir cómo y con qué modelo corren los agentes" |
| `contexto_memoria` | `advanced` | "Qué información y memoria recibe el agente" |
| `calidad_verificacion` | `simple` | "Asegurar que el entregable cumpla y esté verificado" |
| `integridad_grounding` | `advanced` | "Verificar que lo que el agente afirma sea real" |
| `epicas_ado` | `simple` | "Generar y publicar épicas e issues en ADO" |
| `flujo_funcional` | `advanced` | "Crear Tasks funcionales en ADO" |
| `routing_costo` | `simple` | "Controlar el costo y a qué modelo va cada ticket" |
| `fiabilidad_ciclo_vida` | `advanced` | "Mantener sanos los procesos y reintentos" |
| `observabilidad_notif` | `simple` | "Ver salud, KPIs y recibir notificaciones" |
| `aprendizaje` | `advanced` | "Que Stacky aprenda de rechazos y ediciones" |
| `preflight_intencion` | `advanced` | "Aprobar la intención antes de que el agente corra" |
| `base_datos` | `advanced` | "Acceso read-only y caché de la base ADO" |
| `avanzado` | `advanced` | "Kill-switches internos y features beta" |
| `migrador_ado_gitlab` | `advanced` | "Migrar work items de ADO a GitLab" |
| `otros` | `advanced` | "Flags sin categorizar (no debería haber ninguna)" |

   Ejemplo de una entrada anotada (las demás idénticas en forma):
```python
    CategorySpec("runtimes_cli", "Runtimes CLI (Claude / Codex)",
        "Comportamiento de los agentes que corren como CLI: ...",
        tier="simple", intent="Elegir cómo y con qué modelo corren los agentes"),
```

3. Exponer en `list_categories()` (aditivo):
```python
def list_categories() -> list[dict]:
    return [{"id": c.id, "label": c.label, "description": c.description,
             "tier": c.tier, "intent": c.intent}
            for c in FLAG_CATEGORIES]
```

**Casos borde:** categoría sin `tier` explícito → default `"advanced"` (seguro: cae al catch-all, no se pierde). `intent` vacío en una categoría → `test_every_category_has_tier_and_intent` falla a propósito (obliga a curarla).

**Criterio de aceptación BINARIO:** los 4 tests nuevos + los existentes de `test_harness_flags.py` pasan (verde). Comando: el de arriba; salida esperada `passed`, 0 `failed`.
**Configuración que la protege:** ninguna flag/env nueva. Es metadata de presentación, siempre activa, sin riesgo (default `advanced` es seguro).
**Impacto por runtime:** NINGUNO. No toca el pipeline de ejecución; solo el endpoint de lectura de flags. Fallback: si el deploy no se actualiza, el front degrada (F1) — nada se rompe.
**Trabajo del operador:** ninguno.

---

### F1 — Frontend: tipos del contrato + mapa de identidad visual por categoría

**Objetivo (1 frase):** Reflejar `tier`/`intent` en los tipos TS (opcionales, backward-compatible), declarar el mapa estático slug→{color, icono} y **[ADICIÓN ARQUITECTO] exponer la función pura `partitionSectionsByTier` que cierra el invariante de partición con un test ejecutable**.
**Valor:** Habilita F3..F6 sin lógica todavía; el invariante central es testeable desde este módulo.

**Archivos exactos:**
- `Stacky Agents/frontend/src/api/endpoints.ts` (extender `HarnessFlagCategory`).
- `Stacky Agents/frontend/src/components/harnessVisuals.ts` (**NUEVO** — mapa de identidad visual + función pura de partición).

**Implementación:**

1. En `endpoints.ts`, extender el tipo (campos **opcionales** → no rompe el mock de `HarnessFlagsPanel.test.tsx` que no los envía):
```ts
export interface HarnessFlagCategory {
  id: string;
  label: string;
  description: string;
  tier?: "simple" | "advanced";   // Plan 78 — nivel de profundidad (default tratado como "advanced")
  intent?: string;                 // Plan 78 — frase humana de intención
}
```

2. Crear `harnessVisuals.ts`. Incluye:
   - El mapa `CATEGORY_VISUALS` (slug→{color,icon}).
   - La función pura `partitionSectionsByTier` **[ADICIÓN ARQUITECTO — C2]** que encapsula el predicado de partición, haciéndolo importable y testeable de forma aislada.

```ts
import {
  Terminal, Brain, CheckCircle2, ShieldCheck, BookOpen, ListChecks,
  Coins, Activity, GraduationCap, Compass, Database, FlaskConical,
  GitMerge, HelpCircle, Monitor, type LucideIcon,
} from "lucide-react";

export interface CategoryVisual { color: string; icon: LucideIcon; }

// slug (HarnessFlagCategory.id) → identidad visual. Slugs estables (backend FLAG_CATEGORIES).
// REGLA: cada slug debe tener un icono DISTINTO para permitir reconocimiento por icono.
export const CATEGORY_VISUALS: Record<string, CategoryVisual> = {
  runtimes_cli:          { color: "#6366f1", icon: Terminal },
  contexto_memoria:      { color: "#0ea5e9", icon: Brain },
  calidad_verificacion:  { color: "#22c55e", icon: CheckCircle2 },
  integridad_grounding:  { color: "#14b8a6", icon: ShieldCheck },
  epicas_ado:            { color: "#a855f7", icon: BookOpen },
  flujo_funcional:       { color: "#8b5cf6", icon: ListChecks },
  routing_costo:         { color: "#f59e0b", icon: Coins },
  fiabilidad_ciclo_vida: { color: "#ef4444", icon: Activity },
  observabilidad_notif:  { color: "#3b82f6", icon: Monitor },   // [C3 fix: era Activity, duplicado]
  aprendizaje:           { color: "#ec4899", icon: GraduationCap },
  preflight_intencion:   { color: "#06b6d4", icon: Compass },
  base_datos:            { color: "#64748b", icon: Database },
  avanzado:              { color: "#71717a", icon: FlaskConical },
  migrador_ado_gitlab:   { color: "#fb923c", icon: GitMerge },
  otros:                 { color: "#9ca3af", icon: HelpCircle },
};

// Fallback determinista: categoría sin entrada → gris + icono genérico. NUNCA rompe.
export const FALLBACK_VISUAL: CategoryVisual = { color: "#9ca3af", icon: HelpCircle };

export function visualFor(catId: string): CategoryVisual {
  return CATEGORY_VISUALS[catId] ?? FALLBACK_VISUAL;
}

/**
 * [ADICIÓN ARQUITECTO — C2] Función PURA que particiona secciones por tier.
 * Encapsula el predicado de F4 para que sea importable y testeable de forma aislada.
 *
 * INVARIANTE garantizado: simpleSections ∪ restSections === allSections (sin solape, sin pérdida).
 * Un filtro por `=== "simple"` y su complemento `!== "simple"` lo garantiza por construcción.
 * tier=undefined (deploy viejo / mock sin tier) cae en restSections → degradación segura.
 *
 * @param allSections Lista completa de secciones (orderedSections de HarnessFlagsPanel).
 * @returns { simpleSections, restSections } — partición exhaustiva y disjunta.
 */
export function partitionSectionsByTier<T extends { cat: { tier?: string } }>(
  allSections: T[]
): { simpleSections: T[]; restSections: T[] } {
  const simpleSections = allSections.filter(s => s.cat.tier === "simple");
  const restSections   = allSections.filter(s => s.cat.tier !== "simple");
  return { simpleSections, restSections };
}
```

**Casos borde:** categoría servida por el backend sin entrada en el mapa → `visualFor` devuelve `FALLBACK_VISUAL` (gris + `HelpCircle`). Nombre de icono inexistente en lucide → error de `tsc` en build (gate lo atrapa antes de mergear).
**Verificación de nombres de icono:** todos los iconos listados existen en `lucide-react@0.453`. Si el implementador duda de uno, sustituir por `Settings` (existe siempre) — NO inventar nombres.

**TESTS de `partitionSectionsByTier` (convención — no bloqueante, ejecutar cuando vitest esté):**
Agregar `Stacky Agents/frontend/src/components/__tests__/harnessVisuals.test.ts`:
```ts
import { partitionSectionsByTier, visualFor, FALLBACK_VISUAL } from "../harnessVisuals";

const sec = (tier?: string) => ({ cat: { id: "x", label: "", description: "", tier } });

it("particion exhaustiva: simple + rest == total, sin solape", () => {
  const all = [sec("simple"), sec("advanced"), sec(undefined), sec("simple")];
  const { simpleSections, restSections } = partitionSectionsByTier(all);
  expect(simpleSections.length + restSections.length).toBe(all.length);
  const simpleSet = new Set(simpleSections);
  for (const s of restSections) expect(simpleSet.has(s)).toBe(false);
});

it("tier undefined cae en restSections (degradacion segura)", () => {
  const { restSections } = partitionSectionsByTier([sec(undefined)]);
  expect(restSections.length).toBe(1);
});

it("visualFor sin entrada devuelve FALLBACK_VISUAL", () => {
  expect(visualFor("inexistente")).toBe(FALLBACK_VISUAL);
});
```

**Criterio de aceptación BINARIO:** `npm run build` (incluye `tsc --noEmit`) desde `Stacky Agents/frontend` → **0 errores**. Comando: `cd "Stacky Agents/frontend"; npm run build` (PowerShell: usar `;`).
**Configuración que la protege:** ninguna; es código de presentación inerte hasta que F3..F5 lo consumen.
**Impacto por runtime:** NINGUNO (frontend).
**Trabajo del operador:** ninguno.

---

### F2 — Frontend: hook de preferencia de UI persistida en `localStorage`

**Objetivo (1 frase):** Un hook `useHarnessUiPrefs()` que lee/escribe el modo (`"simple"|"experto"`) en `localStorage`, default `"simple"`, sin tocar backend ni store del operador.
**Valor:** Aísla la persistencia local; reusable y testeable por inspección; no contamina la config del pipeline.

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/useHarnessUiPrefs.ts` (**NUEVO**).

**Especificación EXACTA:**
- **Key de localStorage:** `"stacky.harness.uiMode"` (string literal, sin variantes).
- **Valores válidos:** `"simple"` | `"experto"`. Cualquier otro valor leído → se trata como default.
- **Default:** `"simple"` (lo menos abrumador, según riel 2).
- **Dónde se lee:** al inicializar el `useState` (lazy initializer que lee `localStorage.getItem("stacky.harness.uiMode")`).
- **Dónde se escribe:** en el setter expuesto (`setMode`), que hace `localStorage.setItem("stacky.harness.uiMode", value)` y actualiza el state.

**Implementación (diff ilustrativo):**
```ts
import { useState, useCallback } from "react";

export type HarnessUiMode = "simple" | "experto";
const STORAGE_KEY = "stacky.harness.uiMode";

function readMode(): HarnessUiMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "experto" ? "experto" : "simple"; // default seguro
  } catch { return "simple"; }  // SSR / storage bloqueado → default
}

export function useHarnessUiPrefs() {
  const [mode, setModeState] = useState<HarnessUiMode>(readMode);
  const setMode = useCallback((m: HarnessUiMode) => {
    try { localStorage.setItem(STORAGE_KEY, m); } catch { /* no-op */ }
    setModeState(m);
  }, []);
  return { mode, setMode };
}
```

**Casos borde:** `localStorage` no disponible (modo privado / test) → `try/catch` devuelve default y no lanza. Valor corrupto en storage → tratado como `"simple"`.
**TESTS:** convención (no bloqueante) en `__tests__/useHarnessUiPrefs.test.ts`. Gate real = `tsc`.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores.
**Configuración que la protege:** ninguna flag; preferencia 100% local del navegador (no es config del operador ni del pipeline).
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno (opt-in implícito: si nunca toca el toggle, queda en Simple).

---

### F3 — Frontend: Hero / dashboard "Arnés — Configuración activa"

**Objetivo (1 frase):** Un encabezado visual (hero) arriba del panel que muestra perfil activo, total de flags activas vs totales, y una barra de actividad (NO de salud — ver C8), reusando las stats que el panel ya calcula y **reemplazando** el `profileBar` y el `summary` actuales.
**Valor:** Da el golpe estético y de orientación inmediata pedido por el operador, sin introducir un KPI engañoso.

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` (insertar `<HarnessHero>` como sub-componente local o bloque; **ELIMINAR** los dos bloques existentes descritos abajo).
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (clases NUEVAS: `hero`, `heroTitle`, `heroStats`, `heroStat`, `heroStatValue`, `heroStatLabel`, `heroHealthBar`, `heroHealthFill`).

**Datos a usar (ya existen en el componente, NO recalcular contratos):** `totalFlags`, `totalActive`, `totalKnown` (~líneas 257-259), `activeProfile` (~línea 223), `PROFILE_LABELS` (línea 14), `applyProfile` (~línea 201). Anclar por SÍMBOLO, no por número de línea.

**Barra de actividad [C8 fix — NO llamarla "salud"]:** porcentaje = `totalActive / totalFlags` → ancho de `heroHealthFill`. Color: verde si `totalActive > 0`, gris si `totalActive === 0`. **IMPORTANTE:** esta barra NO indica salud operativa — solo muestra el % de flags que el operador activó. Activar más flags no es necesariamente "más sano" (muchas son default OFF por diseño: experimentales, betas, kill-switches). Declarar en comentario de código: `// % de flags activas — NO es indicador de salud. Ver Plan 46 (OperationalHealthCard) para salud real.` Para salud de runs (failed, zombies, needs_review), ver Plan 46. Renombrar la clase CSS `heroHealthBar`/`heroHealthFill` a `heroActivityBar`/`heroActivityFill` para evitar la confusión semántica en futuros lectores del código.

**[C1 FIX — EXPLÍCITO] Qué se ELIMINA del JSX (anclas simbólicas):**
- Eliminar el bloque `<div className={styles.profileBar}>...</div>` completo (identificado por `className={styles.profileBar}` en el JSX actual). Su lógica (`applyProfile.mutate`, `PROFILE_LABELS`, `activeProfile`) se conserva intacta; solo cambia el contenedor visual.
- Eliminar el bloque `<div className={styles.summary}>...</div>` completo (identificado por `className={styles.summary}` en el JSX actual). Los datos (`totalFlags`, `totalActive`, `totalKnown`) se conservan intactos y se usan en el hero.
- Las clases CSS `.profileBar` y `.summary` pueden eliminarse del `.module.css` o dejarse como dead-code si no se usan en el nuevo JSX; NO duplicar los contenedores.

**Implementación (diff ilustrativo, dentro de `HarnessFlagsPanel`):**
```tsx
{/* Plan 78 F3 — Hero "Arnés — Configuración activa".
    REEMPLAZA los bloques <div className={styles.profileBar}> y <div className={styles.summary}>
    que se eliminan del JSX. Reutiliza los mismos datos y la misma lógica.
    [C8] El título y la barra son presentación, NO indicadores de salud operativa.
    Ver Plan 46 (OperationalHealthCard) para salud real de runs. */}
<div className={styles.hero}>
  <div className={styles.heroTitle}>
    Arnés — Configuración activa
    <span className={styles.heroProfile}>Perfil: <strong>{activeProfile ?? "personalizado"}</strong></span>
  </div>
  <div className={styles.heroStats}>
    <div className={styles.heroStat}>
      <span className={styles.heroStatValue}>{totalActive}</span>
      <span className={styles.heroStatLabel}>flags activas</span>
    </div>
    <div className={styles.heroStat}>
      <span className={styles.heroStatValue}>{totalFlags}</span>
      <span className={styles.heroStatLabel}>flags totales</span>
    </div>
    <div className={styles.heroStat}>
      <span className={styles.heroStatValue}>{totalKnown}</span>
      <span className={styles.heroStatLabel}>con default</span>
    </div>
  </div>
  {/* % de flags activas — NO es indicador de salud. Ver Plan 46 para salud real. */}
  <div className={styles.heroActivityBar}>
    <div
      className={styles.heroActivityFill}
      style={{ width: `${totalFlags ? Math.round((totalActive / totalFlags) * 100) : 0}%` }}
    />
  </div>
  {/* Los botones de perfil off/safe/full — misma lógica que el profileBar eliminado. */}
  <div className={styles.profileButtons}>
    {Object.entries(PROFILE_LABELS).map(([name, label]) => (
      <button key={name}
        className={`${styles.profileBtn} ${activeProfile === name ? styles.profileBtnActive : ""}`}
        disabled={saving} onClick={() => applyProfile.mutate(name)}>{label}</button>
    ))}
  </div>
</div>
```

**Casos borde:** `totalFlags === 0` (carga vacía) → barra a 0%, sin división por cero (guardado con `totalFlags ?`). `activeProfile` null → muestra "personalizado".
**TESTS:** no aplica unit ejecutable; gate `tsc`. El test de `HarnessFlagsPanel.test.tsx` busca el texto del flag (label del flag, no del hero) → no se rompe por este cambio.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores; al render, el hero muestra los 3 números y la barra (verificación visual manual del operador, no bloqueante para el gate).
**Configuración que la protege:** ninguna.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno.

---

### F4 — Frontend: toggle Simple ↔ Experto + sección catch-all "Todo lo demás" (cierre del supuesto frágil)

**Objetivo (1 frase):** Un toggle visible (Simple/Experto) que, en Simple, renderiza solo categorías `tier==="simple"` más una sección catch-all colapsada "Todo lo demás" con TODAS las restantes; en Experto, renderiza todas (comportamiento Plan 63).
**Valor:** Reduce carga cognitiva sin sacrificar descubribilidad — el invariante que cierra el supuesto frágil del debate.

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` (consumir `useHarnessUiPrefs`, consumir `partitionSectionsByTier` de `harnessVisuals.ts`, dividir `orderedSections`).
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (clases NUEVAS: `modeToggle`, `modeBtn`, `modeBtnActive`, `catchAll`).

**Lógica EXACTA (sin ambigüedad):**
- Tomar `mode` de `useHarnessUiPrefs()`.
- Importar `partitionSectionsByTier` de `./harnessVisuals` [ADICIÓN ARQUITECTO].
- Llamar `const { simpleSections, restSections } = partitionSectionsByTier(orderedSections)` — la función ya encapsula el predicado, sin repetirlo inline.
- **Si `mode === "experto"`:** renderizar `orderedSections` completas, EXACTAMENTE como hoy (Plan 63). El catch-all NO se muestra (sería redundante).
- **Si `mode === "simple"`:** renderizar `simpleSections` con el render normal, y DESPUÉS un `<details className={styles.catchAll}>` (cerrado por default salvo que haya búsqueda/onlyActive) cuyo cuerpo renderiza `restSections` (cada una con su propio `<details>` de categoría intacto). El summary del catch-all dice "Todo lo demás · {N} categorías · {M} flags".
- **Búsqueda/onlyActive activos:** si `qLower` u `onlyActive`, forzar `mode`-independiente la apertura (igual que hoy las secciones se abren con `open={!!qLower || onlyActive || sectionActive}`), y abrir el catch-all (`open` cuando `qLower || onlyActive`), para que buscar nunca esconda resultados.
- **Extraer `renderSection`:** el bloque `<details>` de categoría (anclado por `className={styles.section}` en el JSX actual) se extrae a una función local `renderSection(cat, catFlags)` para no duplicarlo en los 3 puntos de uso (simple-directas, rest-dentro-del-catch-all, experto). La función NO cambia la lógica interna del bloque.

**Implementación (diff ilustrativo):**
```tsx
import { useHarnessUiPrefs } from "./useHarnessUiPrefs";
import { partitionSectionsByTier } from "./harnessVisuals";

// ...dentro del componente:
const { mode, setMode } = useHarnessUiPrefs();
const { simpleSections, restSections } = partitionSectionsByTier(orderedSections);

// ... en el render, arriba de las secciones:
{/* [C12] role="group" + aria-label comunican selección mutuamente excluyente a lectores de pantalla */}
<div role="group" aria-label="Nivel de configuración" className={styles.modeToggle}>
  <button className={`${styles.modeBtn} ${mode === "simple" ? styles.modeBtnActive : ""}`}
          aria-pressed={mode === "simple"}
          onClick={() => setMode("simple")}>Simple</button>
  <button className={`${styles.modeBtn} ${mode === "experto" ? styles.modeBtnActive : ""}`}
          aria-pressed={mode === "experto"}
          onClick={() => setMode("experto")}>Experto</button>
</div>

{mode === "experto"
  ? orderedSections.map(({ cat, catFlags }) => renderSection(cat, catFlags))
  : <>
      {simpleSections.map(({ cat, catFlags }) => renderSection(cat, catFlags))}
      {restSections.length > 0 && (
        <details className={styles.catchAll} open={!!qLower || onlyActive}>
          <summary className={styles.sectionSummary}>
            <span className={styles.sectionLabel}>Todo lo demás</span>
            <span className={styles.sectionMeta}>
              {restSections.length} categorías · {restSections.reduce((n, s) => n + s.catFlags.length, 0)} flags
            </span>
          </summary>
          {restSections.map(({ cat, catFlags }) => renderSection(cat, catFlags))}
        </details>
      )}
    </>}
```

**[ADICIÓN ARQUITECTO — C9] Incluir `intent` en el predicado de búsqueda:**
En el cálculo de `orderedSections` (el filtro que aplica `qLower` a cada categoría), agregar `cat.intent` al predicado de búsqueda de sección. Ejemplo: donde el código hace algo como:
```ts
const sectionMatch = cat.label.toLowerCase().includes(qLower) ||
                     cat.description.toLowerCase().includes(qLower);
```
Extenderlo a:
```ts
const sectionMatch = cat.label.toLowerCase().includes(qLower) ||
                     cat.description.toLowerCase().includes(qLower) ||
                     (cat.intent ?? "").toLowerCase().includes(qLower);  // [C9] navegación por intención real
```
Este cambio tiene 1 línea de código, cero dependencias nuevas, y hace REAL la promesa del objetivo de "navegación por intención": escribir "publicar épica" en el buscador matchea la categoría `epicas_ado` cuyo `intent` es "Generar y publicar épicas e issues en ADO". Sin esto, la `intent` es decoración visual pura. El implementador DEBE ubicar el predicado de búsqueda actual y extenderlo; no hardcodear un bloque nuevo.

**INVARIANTE CRÍTICO:** la unión `{categorías visibles directas} ∪ {categorías dentro del catch-all}` == `orderedSections` completo. Garantizado por `partitionSectionsByTier` (función pura cuyo invariante está cubierto en F0 + convención de test en F1). El implementador NO debe reescribir el predicado inline — usar la función importada.

**Accesibilidad del toggle [C12]:** los botones `Simple` / `Experto` son elementos `<button>` nativos (teclado-accesibles por defecto). Agregar `aria-pressed={mode === "simple"}` al primer botón y `aria-pressed={mode === "experto"}` al segundo para comunicar el estado al lector de pantalla. **Además**, el contenedor `<div className={styles.modeToggle}>` debe declarar `role="group"` y `aria-label="Nivel de configuración"` para que el lector de pantalla comunique que los botones forman una selección mutuamente excluyente.

**Casos borde:** ninguna categoría `tier==="simple"` (no debería pasar — F0 lo testea) → `simpleSections` vacío, todo cae en el catch-all (sigue siendo accesible). `restSections` vacío → no se renderiza el catch-all (no hay nada que esconder). Deploy backend viejo (sin `tier`) → todas caen al catch-all en Simple; el operador puede pasar a Experto; nada se pierde.
**TESTS:** convención en `HarnessFlagsPanel.test.tsx`; el invariante de partición tiene gate ejecutable en F0 (backend) y convención TS en F1. Gate real `tsc`.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores. + Verificación manual: en Simple, contar categorías visibles directas + dentro del catch-all == total; en Experto, todas visibles.
**Configuración que la protege:** preferencia local `stacky.harness.uiMode` (F2), default Simple. Sin flag de pipeline.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno (toggle opt-in; default Simple es seguro).

---

### F5 — Frontend: identidad visual por categoría (color + icono en cada sección)

**Objetivo (1 frase):** Pintar cada `<summary>` de categoría con su color/icono de `CATEGORY_VISUALS` (borde izquierdo de color, icono junto al label) y mostrar la `intent` como subtítulo humano.
**Valor:** El reconocimiento visual por color/icono es el corazón del pedido "más estético y llamativo" y de "navegación por intención". Cada categoría tiene un icono único (mapa corregido en F1/C3).

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` (en `renderSection`, consumir `visualFor(cat.id)` y `cat.intent`).
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (clases NUEVAS: `sectionIcon`, `sectionIntent`, y modificador inline `borderLeft` por color).

**Implementación (diff ilustrativo, dentro de `renderSection`):**
```tsx
import { visualFor } from "./harnessVisuals";
// ...
const { color, icon: Icon } = visualFor(cat.id);
return (
  <details key={cat.id} className={styles.section}
           style={{ borderLeft: `4px solid ${color}` }}
           open={!!qLower || onlyActive || sectionActive}>
    <summary className={styles.sectionSummary}>
      <span className={styles.sectionLabel}>
        <Icon size={16} color={color} className={styles.sectionIcon} aria-hidden="true" />
        {cat.label}
      </span>
      <span className={styles.sectionMeta}>{visibleFlags.length} flags · {visibleActive} activas</span>
    </summary>
    {cat.intent && <p className={styles.sectionIntent}>{cat.intent}</p>}
    {cat.description && <p className={styles.sectionDesc}>{cat.description}</p>}
    {visibleFlags.map((flag) => (
      <FlagRow key={flag.key} flag={flag} allFlags={flags} onUpdate={handleUpdate} saving={saving} />
    ))}
  </details>
);
```

**Casos borde:** `cat.intent` undefined (deploy viejo) → no renderiza el `<p>` (guardado con `&&`). `aria-hidden` en el icono para accesibilidad (el label textual queda como fuente de verdad para lectores de pantalla). El color del borde es refuerzo visual, no único canal de información.
**TESTS:** gate `tsc`. El test del SettingsPage busca el texto del label/flag, que sigue presente → no se rompe. El mock no tiene `tier`, lo que el flag de la categoría `runtimes_cli` lo maneja F7.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores; visualmente cada sección tiene borde de color + icono + intent.
**Configuración que la protege:** ninguna.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno.

---

### F6 — Frontend: pulido estético y animación CSS (sin libs)

**Objetivo (1 frase):** Aplicar la capa "llamativa" final con CSS puro: transiciones suaves de hover/expand, sombra/elevación en hero y secciones, y estética de los toggles, todo en el `.module.css`.
**Valor:** Cierra el pedido "mucho más estético y llamativo" sin sumar dependencias.

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (estilos de las clases nuevas de F3/F4/F5 + transiciones).

**Especificación con anclas mínimas [C5 FIX] (el implementador puede ajustar, pero DEBE respetar estos tokens como base):**

```css
/* Hero */
.hero {
  background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3e 100%); /* fondo elevado oscuro-azul */
  border-radius: 12px;
  padding: 20px 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Barra de actividad — % de flags activas (NO salud; ver Plan 46 para salud real) */
.heroActivityBar {
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}
.heroActivityFill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #4ade80);
  border-radius: 3px;
  transition: width 0.4s ease;
}

/* Toggle Simple/Experto — pill group */
.modeToggle {
  display: inline-flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.15);
  margin-bottom: 12px;
}
.modeBtn {
  padding: 6px 16px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  color: inherit;
  transition: background 0.15s ease, color 0.15s ease;
}
.modeBtnActive {
  background: #6366f1; /* acento índigo, coherente con runtimes_cli */
  color: #fff;
}

/* Secciones — elevación suave en hover */
@media (prefers-reduced-motion: no-preference) {
  .section {
    transition: box-shadow 0.2s ease;
  }
  .section:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  }
}

/* Catch-all — apariencia secundaria */
.catchAll {
  border: 1px dashed rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  padding: 4px 0;
  opacity: 0.85;
}

/* Icono de sección */
.sectionIcon {
  vertical-align: middle;
  margin-right: 6px;
  flex-shrink: 0;
}

/* Subtítulo de intención */
.sectionIntent {
  font-size: 0.8rem;
  opacity: 0.7;
  margin: 2px 0 6px 0;
  font-style: italic;
}
```

**Notas de tema:** si el proyecto tiene variables CSS globales (`--bg-panel`, `--color-accent`, etc.) verificarlas en los estilos globales antes de hardcodear los colores de fondo; usar las variables si existen. Los colores de categoría de F1 son acentos, nunca fondos. Los colores del hero son neutros oscuros que funcionan sobre el fondo actual del panel.

**Casos borde:** `prefers-reduced-motion` cubierto (envuelto en la media query de arriba). Tema claro/oscuro: los valores base funcionan sobre fondo oscuro (el panel actual lo es); ajustar si el panel tiene fondo claro.
**TESTS:** no aplica (CSS). Gate efectivo: `npm run build` sin error de CSS + verificación visual manual.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores (incluye bundling de CSS). Verificación visual manual del operador.
**Configuración que la protege:** ninguna.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno.

---

### F7 — No-regresión y cierre (DoD)

**Objetivo (1 frase):** Confirmar que el contrato del backend sigue verde, el frontend compila, y el test de integración del SettingsPage no se rompió.
**Valor:** Gate final honesto, sin falsos verdes.

**Acciones:**
1. Correr el backend: `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_harness_flags.py -q` desde `Stacky Agents/backend` → todos verdes (incluye los 4 nuevos de F0, entre ellos `test_partition_semantics_simple_vs_advanced`). **Nota sobre el gate [C11]:** `test_partition_semantics_simple_vs_advanced` valida que los DATOS del backend (FLAG_CATEGORIES) sean consistentes con el predicado; es un gate de consistencia de datos, no de la función TS `partitionSectionsByTier`. La función TS se verifica por inspección directa + `tsc`.
2. **[C4+C7+C10 FIX — EXPLÍCITO]** Actualizar el test `Stacky Agents/frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx` (**nombre de archivo correcto — no `HarnessFlagsPanel.test.tsx`**):
   - **[C7]** En el test "botón de perfil 'safe' llama al endpoint de perfiles" (línea ~172 del archivo actual), la aserción `await waitFor(() => screen.getByText(/Perfil activo/i))` **ROMPE** porque F3 elimina el `<div className={styles.profileBar}>` que contiene el texto "Perfil activo:". Reemplazar esa línea por:
     ```ts
     await waitFor(() => screen.getByText(/Perfil:/i));
     ```
     El nuevo hero muestra `"Perfil:"` (sin "activo") dentro del bloque `<span className={styles.heroProfile}>`.
   - **[C4]** En el mock `MOCK_RESPONSE` (o en el array de `categories` si existe), agregar `tier: "simple"` al flag o categoría de `runtimes_cli`. Si el mock no expone `categories` (el mock actual solo tiene `flags` + `active_profile`), verificar que el test no monte `HarnessFlagsPanel` en modo que el catch-all colapse los flags del mock. Si la categoría de `BOOL_FLAG` (`group: "claude_code_cli"`) cae en el catch-all colapsado → `getByText("Gate de contrato (claude)")` puede fallar en JSDOM. Si el componente requiere `categories` del endpoint, mockar `HarnessFlags.list` devolviendo también `categories` con `tier: "simple"` para `claude_code_cli`.
   - El campo `tier` es opcional en el tipo TS — este cambio es backward-compatible.
3. `npm run build` desde `Stacky Agents/frontend` → 0 errores TS.

**Criterio de aceptación BINARIO (DoD):**
- `pytest tests/test_harness_flags.py -q` → 0 failed.
- `npm run build` → exit 0, 0 errores TS.
- `HarnessFlagsPanel.test.tsx` actualizado: aserción `/Perfil activo/i` → `/Perfil:/i` (C7) + `tier: "simple"` en el mock de la categoría de `runtimes_cli` (C4).
- El invariante de partición de F4 está cubierto por `partitionSectionsByTier` (test ejecutable de datos en F0/backend + función pura verificable en F1/frontend).
- **[C13]** Criterio de búsqueda + catch-all: con `qLower` no vacío en modo Simple, el `<details className={styles.catchAll}>` se abre (`open={!!qLower || onlyActive}`). Verificar en inspección manual: buscar cualquier término que matchee una categoría `advanced` → el catch-all se expande y la sección aparece.

**Impacto por runtime:** NINGUNO en las tres. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación (en este plan) |
|---|--------|---------------------------|
| R1 | **Drift front↔backend (el supuesto frágil del Brainstormer):** una flag/categoría nueva queda invisible en modo Simple. | `tier`/`intent` viven en el backend (F0), fuente única de verdad, blindados por `test_every_category_has_tier_and_intent`. El catch-all "Todo lo demás" (F4) contiene SIEMPRE toda categoría `!= simple` (incluida `undefined`). Invariante de partición verificado por `test_partition_semantics_simple_vs_advanced` (F0) y `partitionSectionsByTier` (F1). **Cerrado.** |
| R2 | Deploy backend desactualizado no envía `tier`/`intent`. | Campos opcionales en TS (F1); `!== "simple"` manda todo al catch-all (F4) → en Simple todo accesible vía catch-all, y el operador puede ir a Experto. Degradación segura, nada se pierde. |
| R3 | Romper `HarnessFlagsPanel.test.tsx` (monta el panel). | F7 exige agregar `tier: "simple"` al mock de `runtimes_cli` para evitar que el flag caiga al catch-all colapsado. La aserción busca el label del flag, que no cambia de texto. |
| R4 | Cambio posicional en `CategorySpec` rompe construcciones existentes. | Los campos nuevos van **al final con default** (`tier="advanced"`, `intent=""`) → llamadas posicionales existentes siguen válidas (aditivo). |
| R5 | Nombre de icono inexistente en `lucide-react`. | F1 lista solo iconos verificados de `lucide-react@0.453`, todos distintos entre sí; fallback a `Settings` si hay duda; `tsc` atrapa cualquier símbolo inexistente en el gate de build. |
| R6 | ~~El hero "salud" se malinterprete como diagnóstico real.~~ [C8 cerrado] La barra se llamaba "de salud" pero `totalActive/totalFlags` crece al encender features experimentales (default OFF). | Renombrada a "% de flags activas" / barra de actividad (no de salud). Título del hero: "Arnés — Configuración activa". Comentario en código. **Cerrado (C8).** |
| R7 | Accesibilidad (color como único canal de información). | El label textual y la `intent` siempre presentes; icono `aria-hidden`; toggle con `aria-pressed` + `role="group"` + `aria-label` (C12); `prefers-reduced-motion` respetado (F6). El color es refuerzo, no único portador. |
| R8 | Duplicación de UI (profileBar + hero coexisten). | F3 especifica EXPLÍCITAMENTE qué elementos JSX se eliminan (ancla simbólica `className={styles.profileBar}` y `className={styles.summary}`). No hay ambigüedad. **Cerrado (C1).** |
| R9 | Icono duplicado rompe reconocimiento por icono. | `observabilidad_notif` usa `Monitor` (no `Activity` como en v1). Mapa con 15 iconos todos distintos. **Cerrado (C3).** |
| R10 | Test `HarnessFlagsPanel.test.tsx` rompe por eliminación del profileBar. | F7 exige actualizar la aserción `/Perfil activo/i` → `/Perfil:/i` y el mock de categoría. **Cerrado (C7).** |
| R11 | "Navegación por intención" es decorativa si `intent` no está en el predicado de búsqueda. | [ADICIÓN ARQUITECTO C9] F4 exige extender el filtro de `orderedSections` con `cat.intent` en el predicado de búsqueda. **Cerrado (C9).** |

---

## 6. Fuera de scope

- **Reasignar flags a categorías** o cambiar `_CATEGORY_KEYS` (eso es semántica del Plan 63; acá NO se toca).
- **Nuevas flags o cambios de comportamiento del pipeline** (este plan es presentación + metadata).
- **Tema oscuro/claro nuevo** o sistema de theming global (se reusa lo existente; no se introduce).
- **Persistencia de la preferencia de modo en BD/servidor** (es `localStorage` por diseño — no es config del operador).
- **"Salud operativa real" de runs** (eso es el Plan 46 `OperationalHealthCard`; el hero de F3 es solo % de flags activas).
- **Tests ejecutables de frontend vía vitest** (no está instalado; el gate real es `tsc`/`npm run build`). Los tests de F1 son convención ejecutable cuando el toolchain esté.
- **Editor de `tier`/`intent` por UI** (son metadata de diseño del sistema, no config del operador; se cambian en código + test).

---

## 7. Glosario, orden de implementación y DoD global

### Glosario
- **`tier`** (`"simple"|"advanced"`): nivel de profundidad de una categoría, declarado en `CategorySpec`. Determina si aparece en modo Simple directamente o cae en el catch-all.
- **`intent`**: frase humana ("¿qué querés lograr?") asociada a una categoría, para navegación por intención. Vive en `CategorySpec`.
- **Catch-all "Todo lo demás"**: sección colapsable en modo Simple que contiene TODAS las categorías `tier != "simple"`. Garantiza descubribilidad total.
- **Hero / "Arnés — Configuración activa"**: encabezado visual con perfil activo, stats (activas/totales/con-default) y barra de actividad (% de flags activas — NO indicador de salud). **Reemplaza** el `profileBar` y el `summary` del Plan 63. Ver Plan 46 para salud operativa real (runs failed/zombies/needs_review).
- **`CATEGORY_VISUALS`**: mapa estático slug→{color, icono} en el frontend (`harnessVisuals.ts`). 15 entradas con 15 iconos distintos.
- **Modo Simple/Experto**: preferencia de presentación persistida en `localStorage` (`stacky.harness.uiMode`), default Simple.
- **`partitionSectionsByTier`**: función pura en `harnessVisuals.ts` que encapsula el predicado de partición Simple/resto, testeable de forma aislada. [ADICIÓN ARQUITECTO]

### Orden de implementación
**F0** (backend: `tier`/`intent` + 4 tests, incluyendo `test_partition_semantics_simple_vs_advanced`) → **F1** (tipos TS + `harnessVisuals.ts` con `partitionSectionsByTier`) → **F2** (`useHarnessUiPrefs`) → **F3** (hero — ELIMINAR profileBar+summary) → **F4** (toggle + catch-all, usar `partitionSectionsByTier`) → **F5** (color/icono/intent por sección) → **F6** (pulido CSS con anclas) → **F7** (no-regresión + DoD: actualizar mock + correr tests).
F0 y F1 pueden hacerse en paralelo (F1 declara campos opcionales que no dependen del valor real de F0). F3..F6 dependen de F1+F2.

### DoD global (binario)
1. `pytest tests/test_harness_flags.py -q` (desde `Stacky Agents/backend`, con el `.venv`) → **0 failed**, incluyendo `test_every_category_has_tier_and_intent`, `test_list_categories_exposes_tier_and_intent`, `test_at_least_one_simple_and_one_advanced_category`, **`test_partition_semantics_simple_vs_advanced`**. (El pytest valida consistencia de datos del backend, no la función TS.)
2. `npm run build` (desde `Stacky Agents/frontend`) → **exit 0, 0 errores TS**.
3. `HarnessFlagsPanel.test.tsx` actualizado [C7+C4]: (a) aserción `/Perfil activo/i` → `/Perfil:/i`; (b) mock de categoría `claude_code_cli`/`runtimes_cli` incluye `tier: "simple"`.
4. Invariante de partición F4 cubierto por `partitionSectionsByTier` (función pura verificable + gate `tsc`) y test de consistencia de datos en F0/backend.
5. Impacto por runtime declarado NINGUNO en F0..F7; ninguna flag cambia de nombre/tipo/default/efecto.
6. Trabajo del operador: **ninguno** (preferencia de modo opt-in, default Simple; sin nueva config de pipeline).
7. `<div className={styles.profileBar}>` y `<div className={styles.summary}>` eliminados del JSX (no duplicados con el hero).
8. Mapa `CATEGORY_VISUALS`: 15 iconos distintos (sin duplicados); `observabilidad_notif` usa `Monitor`.
9. **[C8]** Hero titulado "Arnés — Configuración activa"; barra = `heroActivityBar`/`heroActivityFill` con comentario explícito "NO es indicador de salud".
10. **[C9 ADICIÓN ARQUITECTO]** Predicado de búsqueda de `orderedSections` incluye `cat.intent` → buscar "publicar épica" matchea la categoría correcta.
11. **[C12]** Toggle `<div role="group" aria-label="Nivel de configuración">` con `aria-pressed` en ambos botones.
