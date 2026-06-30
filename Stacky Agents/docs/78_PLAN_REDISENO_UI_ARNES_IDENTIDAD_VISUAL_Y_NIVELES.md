# Plan 78 — Rediseño UI del Arnés: identidad visual, dashboard de salud y niveles Simple/Experto

> **Versión:** v1 (propuesta inicial — pendiente de 2 pasadas del juez `criticar-y-mejorar-plan`).
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
- **Estética:** identidad visual consistente (12+ colores/iconos de categoría) y hero con barra de salud, sin sumar dependencias (usa `lucide-react`, ya instalado, `package.json:14`).
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
6. **Reusar lo existente.** Se reusa el endpoint `GET /api/harness-flags`, React Query (`queryKey: ["harness-flags"]`), los perfiles off/safe/full (`POST /api/harness-flags/profile`), todas las clases CSS del Plan 63 (`HarnessFlagsPanel.module.css`) y los sub-componentes `FlagRow`/`JsonInput`. Solo se agregan clases/elementos nuevos sin romper los que usa `SettingsPage.harness.test.tsx`.
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

2. Anotar las 14 entradas de `FLAG_CATEGORIES` con `tier` e `intent`. **Mapa exacto a usar** (decisión cerrada — el implementador NO elige):

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

**Criterio de aceptación BINARIO:** los 3 tests nuevos + los existentes de `test_harness_flags.py` pasan (verde). Comando: el de arriba; salida esperada `passed`, 0 `failed`.
**Configuración que la protege:** ninguna flag/env nueva. Es metadata de presentación, siempre activa, sin riesgo (default `advanced` es seguro).
**Impacto por runtime:** NINGUNO. No toca el pipeline de ejecución; solo el endpoint de lectura de flags. Fallback: si el deploy no se actualiza, el front degrada (F1) — nada se rompe.
**Trabajo del operador:** ninguno.

---

### F1 — Frontend: tipos del contrato + mapa de identidad visual por categoría

**Objetivo (1 frase):** Reflejar `tier`/`intent` en los tipos TS (opcionales, backward-compatible) y declarar el mapa estático slug→{color, icono} que da identidad visual a cada categoría.
**Valor:** Habilita F3..F6 sin lógica todavía; aislado y verificable por `tsc`.

**Archivos exactos:**
- `Stacky Agents/frontend/src/api/endpoints.ts` (extender `HarnessFlagCategory`).
- `Stacky Agents/frontend/src/components/harnessVisuals.ts` (**NUEVO** — mapa de identidad visual).

**Implementación:**

1. En `endpoints.ts`, extender el tipo (campos **opcionales** → no rompe el mock de `SettingsPage.harness.test.tsx` que no los envía):
```ts
export interface HarnessFlagCategory {
  id: string;
  label: string;
  description: string;
  tier?: "simple" | "advanced";   // Plan 78 — nivel de profundidad (default tratado como "advanced")
  intent?: string;                 // Plan 78 — frase humana de intención
}
```

2. Crear `harnessVisuals.ts` (mapa estático; slugs estables del backend). Iconos de `lucide-react` (ya instalado). **Mapa exacto a usar:**
```ts
import {
  Terminal, Brain, CheckCircle2, ShieldCheck, BookOpen, ListChecks,
  Coins, Activity, GraduationCap, Compass, Database, FlaskConical,
  GitMerge, HelpCircle, type LucideIcon,
} from "lucide-react";

export interface CategoryVisual { color: string; icon: LucideIcon; }

// slug (HarnessFlagCategory.id) → identidad visual. Slugs estables (backend FLAG_CATEGORIES).
export const CATEGORY_VISUALS: Record<string, CategoryVisual> = {
  runtimes_cli:          { color: "#6366f1", icon: Terminal },
  contexto_memoria:      { color: "#0ea5e9", icon: Brain },
  calidad_verificacion:  { color: "#22c55e", icon: CheckCircle2 },
  integridad_grounding:  { color: "#14b8a6", icon: ShieldCheck },
  epicas_ado:            { color: "#a855f7", icon: BookOpen },
  flujo_funcional:       { color: "#8b5cf6", icon: ListChecks },
  routing_costo:         { color: "#f59e0b", icon: Coins },
  fiabilidad_ciclo_vida: { color: "#ef4444", icon: Activity },
  observabilidad_notif:  { color: "#3b82f6", icon: Activity },
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
```

**Casos borde:** categoría servida por el backend sin entrada en el mapa → `visualFor` devuelve `FALLBACK_VISUAL` (gris + `HelpCircle`). Nombre de icono inexistente en lucide → error de `tsc` en build (gate lo atrapa antes de mergear).
**Verificación de nombres de icono:** todos los iconos listados existen en `lucide-react@0.453`. Si el implementador duda de uno, sustituir por `Settings` (existe siempre) — NO inventar nombres.

**TESTS:** No hay test unitario de frontend ejecutable (vitest no instalado en el entorno — gate real es `tsc`). Se agrega por convención `Stacky Agents/frontend/src/components/__tests__/harnessVisuals.test.ts` con un caso (`visualFor("inexistente") === FALLBACK_VISUAL`) que NO bloquea.
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

### F3 — Frontend: Hero / dashboard "Estado del Arnés"

**Objetivo (1 frase):** Un encabezado visual (hero) arriba del panel que muestra perfil activo, total de flags activas vs totales, y una barra/indicador de salud, reusando las stats que el panel ya calcula.
**Valor:** Da el golpe estético y de orientación inmediata ("¿en qué estado está mi arnés?") pedido por el operador.

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` (insertar `<HarnessHero>` como sub-componente local o bloque).
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (clases NUEVAS: `hero`, `heroTitle`, `heroStats`, `heroStat`, `heroStatValue`, `heroStatLabel`, `heroHealthBar`, `heroHealthFill`).

**Datos a usar (ya existen en el componente, NO recalcular contratos):** `totalFlags`, `totalActive`, `totalKnown` (líneas 257-259 del actual), `activeProfile` (línea 223).
**Salud (definición determinista, sin backend nuevo):** porcentaje = `totalActive / totalFlags` → ancho de `heroHealthFill`. Color del fill por umbral: `>0` verde si hay perfil `safe`/`full` activo; si `activeProfile === "off"` o `totalActive === 0` → gris. Esto es presentación, no un juicio de "salud real" (declararlo en comentario).

**Implementación (diff ilustrativo, dentro de `HarnessFlagsPanel`):**
```tsx
{/* Plan 78 F3 — Hero Estado del Arnés (sustituye visualmente al profileBar+summary del Plan 63;
    reusa los mismos datos y el mismo applyProfile.mutate). */}
<div className={styles.hero}>
  <div className={styles.heroTitle}>
    Estado del Arnés
    <span className={styles.heroProfile}>Perfil: <strong>{activeProfile ?? "personalizado"}</strong></span>
  </div>
  <div className={styles.heroStats}>
    <div className={styles.heroStat}>
      <span className={styles.heroStatValue}>{totalActive}</span>
      <span className={styles.heroStatLabel}>activas</span>
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
  <div className={styles.heroHealthBar}>
    <div
      className={styles.heroHealthFill}
      style={{ width: `${totalFlags ? Math.round((totalActive / totalFlags) * 100) : 0}%` }}
    />
  </div>
  {/* Los botones de perfil off/safe/full siguen acá, reusando el bloque profileButtons del Plan 63. */}
  <div className={styles.profileButtons}>
    {Object.entries(PROFILE_LABELS).map(([name, label]) => (
      <button key={name}
        className={`${styles.profileBtn} ${activeProfile === name ? styles.profileBtnActive : ""}`}
        disabled={saving} onClick={() => applyProfile.mutate(name)}>{label}</button>
    ))}
  </div>
</div>
```

**Nota de no-regresión:** el `profileBar` y el `summary` del Plan 63 se **absorben** en el hero (mismos datos, misma acción `applyProfile.mutate`). NO se elimina la funcionalidad, solo su contenedor visual. Mantener `PROFILE_LABELS` y `applyProfile` intactos.

**Casos borde:** `totalFlags === 0` (carga vacía) → barra a 0%, sin división por cero (guardado con `totalFlags ?`). `activeProfile` null → muestra "personalizado".
**TESTS:** no aplica unit ejecutable; gate `tsc`. El test de `SettingsPage.harness.test.tsx` busca el texto del flag, no el del hero → no se rompe.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores; al render, el hero muestra los 3 números y la barra (verificación visual manual del operador, no bloqueante para el gate).
**Configuración que la protege:** ninguna.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno.

---

### F4 — Frontend: toggle Simple ↔ Experto + sección catch-all "Todo lo demás" (cierre del supuesto frágil)

**Objetivo (1 frase):** Un toggle visible (Simple/Experto) que, en Simple, renderiza solo categorías `tier==="simple"` más una sección catch-all colapsada "Todo lo demás" con TODAS las restantes; en Experto, renderiza todas (comportamiento Plan 63).
**Valor:** Reduce carga cognitiva sin sacrificar descubribilidad — el invariante que cierra el supuesto frágil del debate.

**Archivos exactos:**
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` (consumir `useHarnessUiPrefs`, dividir `orderedSections`).
- `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (clases NUEVAS: `modeToggle`, `modeBtn`, `modeBtnActive`, `catchAll`).

**Lógica EXACTA (sin ambigüedad):**
- Tomar `mode` de `useHarnessUiPrefs()`.
- `orderedSections` (ya existe, línea 250) se parte en dos: `simpleSections = orderedSections.filter(s => s.cat.tier === "simple")` y `restSections = orderedSections.filter(s => s.cat.tier !== "simple")`. **Nota:** `tier` puede venir `undefined` (deploy backend viejo / mock) → `!== "simple"` lo manda al catch-all (degradación segura: nada se oculta).
- **Si `mode === "experto"`:** renderizar `orderedSections` completas, EXACTAMENTE como hoy (Plan 63). El catch-all NO se muestra (sería redundante).
- **Si `mode === "simple"`:** renderizar `simpleSections` con el render normal, y DESPUÉS un `<details className={styles.catchAll}>` (cerrado por default salvo que haya búsqueda/onlyActive) cuyo cuerpo renderiza `restSections` (cada una con su propio `<details>` de categoría intacto). El summary del catch-all dice "Todo lo demás · {N} categorías · {M} flags".
- **Búsqueda/onlyActive activos:** si `qLower` u `onlyActive`, forzar `mode`-independiente la apertura (igual que hoy las secciones se abren con `open={!!qLower || onlyActive || sectionActive}`), y abrir el catch-all (`open` cuando `qLower || onlyActive`), para que buscar nunca esconda resultados.

**Implementación (diff ilustrativo):**
```tsx
const { mode, setMode } = useHarnessUiPrefs();

const simpleSections = orderedSections.filter(s => s.cat.tier === "simple");
const restSections   = orderedSections.filter(s => s.cat.tier !== "simple");

// ... en el render, arriba de las secciones:
<div className={styles.modeToggle}>
  <button className={`${styles.modeBtn} ${mode === "simple" ? styles.modeBtnActive : ""}`}
          onClick={() => setMode("simple")}>Simple</button>
  <button className={`${styles.modeBtn} ${mode === "experto" ? styles.modeBtnActive : ""}`}
          onClick={() => setMode("experto")}>Experto</button>
</div>

{/* Render de secciones: extraer a una función renderSection(cat, catFlags) que es
    EXACTAMENTE el <details> del Plan 63 (líneas 324-349 actuales), sin cambios de lógica. */}
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

**INVARIANTE CRÍTICO (verificar en review):** la unión `{categorías visibles directas} ∪ {categorías dentro del catch-all}` == `orderedSections` completo, en AMBOS modos. En Experto se muestran todas directas; en Simple, simple-directas + resto-en-catch-all. **Ninguna categoría se filtra fuera de ambos conjuntos.** Esto es lo que garantiza descubribilidad total. El implementador debe asegurar que `simpleSections` y `restSections` particionan `orderedSections` sin solापe ni pérdida (un `filter` por `=== "simple"` y su complemento `!== "simple"` lo garantizan por construcción).

**Casos borde:** ninguna categoría `tier==="simple"` (no debería pasar — F0 lo testea) → `simpleSections` vacío, todo cae en el catch-all (sigue siendo accesible). `restSections` vacío → no se renderiza el catch-all (no hay nada que esconder). Deploy backend viejo (sin `tier`) → todas caen al catch-all en Simple; el operador puede pasar a Experto; nada se pierde.
**TESTS:** no ejecutable (vitest ausente). Convención: agregar a `HarnessFlagsPanel.test.tsx` un caso documentando el invariante de partición (no bloqueante). Gate real `tsc`.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores. + Verificación manual: en Simple, contar categorías visibles directas + dentro del catch-all == total; en Experto, todas visibles. (El invariante de partición es matemáticamente garantizado por el filtro complementario; el gate de build asegura compilación.)
**Configuración que la protege:** preferencia local `stacky.harness.uiMode` (F2), default Simple. Sin flag de pipeline.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno (toggle opt-in; default Simple es seguro).

---

### F5 — Frontend: identidad visual por categoría (color + icono en cada sección)

**Objetivo (1 frase):** Pintar cada `<summary>` de categoría con su color/icono de `CATEGORY_VISUALS` (borde izquierdo de color, icono junto al label) y mostrar la `intent` como subtítulo humano.
**Valor:** El reconocimiento visual por color/icono es el corazón del pedido "más estético y llamativo" y de "navegación por intención".

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
           open={mode === "experto" ? (!!qLower || onlyActive || sectionActive)
                                     : (!!qLower || onlyActive || sectionActive)}>
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

**Casos borde:** `cat.intent` undefined (deploy viejo) → no renderiza el `<p>` (guardado con `&&`). Color del borde con icono del mismo color → contraste cubierto por el fondo de la sección (CSS). `aria-hidden` en el icono para accesibilidad (el label textual queda como fuente de verdad para lectores de pantalla).
**TESTS:** gate `tsc`. El test del SettingsPage busca el texto del label/flag, que sigue presente → no se rompe.
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

**Especificación (sin ambigüedad sobre QUÉ estilar; valores a criterio estético del implementador respetando estos límites):**
- `.hero`: fondo con gradiente sutil o color de panel elevado, `border-radius`, `padding`, sombra suave (`box-shadow`). `.heroHealthFill`: `transition: width .4s ease`.
- `.modeToggle`: pill group (dos botones segmentados); `.modeBtnActive` con fondo de acento.
- `.section`: `transition: box-shadow .2s, transform .2s` en hover (elevación leve). El `borderLeft` de color (F5) ya va inline.
- `.sectionIcon`: alineación vertical con el label (`vertical-align: middle`, `margin-right`).
- `.catchAll`: estilo más tenue/secundario (borde punteado o fondo más apagado) para señalar "esto es lo avanzado/secundario".
- Animaciones SOLO con `transition`/`@keyframes`. **Prohibido** importar librerías.
- **Respetar `prefers-reduced-motion`:** envolver transiciones no esenciales en `@media (prefers-reduced-motion: no-preference)` o anularlas en `reduce` (accesibilidad).

**Casos borde:** tema oscuro/claro — reusar variables CSS existentes del proyecto si las hay (verificar en el `.module.css` y en estilos globales antes de hardcodear colores de fondo; los colores de categoría de F1 son acentos, no fondos). Si no hay variables de tema, usar colores neutros que funcionen sobre el fondo actual del panel.
**TESTS:** no aplica (CSS). Gate `tsc` no cubre CSS; el gate efectivo es que `npm run build` (vite) compile sin error de CSS y la verificación visual manual.
**Criterio de aceptación BINARIO:** `npm run build` → 0 errores (incluye bundling de CSS). Verificación visual manual del operador.
**Configuración que la protege:** ninguna.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno.

---

### F7 — No-regresión y cierre (DoD)

**Objetivo (1 frase):** Confirmar que el contrato del backend sigue verde, el frontend compila, y el test de integración del SettingsPage no se rompió.
**Valor:** Gate final honesto, sin falsos verdes.

**Acciones:**
1. Correr el backend: `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_harness_flags.py -q` desde `Stacky Agents/backend` → todos verdes (incluye los 3 nuevos de F0).
2. Actualizar el mock de `SettingsPage.harness.test.tsx` SOLO si se decide enviar `tier`/`intent` en el mock (opcional — como son campos opcionales en el tipo, NO es obligatorio; si se agregan, agregarlos a la entrada de `categories` del mock para fidelidad). No cambiar la aserción (sigue buscando "Gate de contrato (claude)").
3. `npm run build` desde `Stacky Agents/frontend` → 0 errores TS.

**Criterio de aceptación BINARIO (DoD):**
- `pytest tests/test_harness_flags.py -q` → 0 failed.
- `npm run build` → exit 0, 0 errores TS.
- El invariante de partición de F4 se cumple por construcción (filtro complementario).

**Impacto por runtime:** NINGUNO en las tres. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación (en este plan) |
|---|--------|---------------------------|
| R1 | **Drift front↔backend (el supuesto frágil del Brainstormer):** una flag/categoría nueva queda invisible en modo Simple. | `tier`/`intent` viven en el backend (F0), fuente única de verdad, blindados por `test_every_category_has_tier_and_intent`. El catch-all "Todo lo demás" (F4) contiene SIEMPRE toda categoría `!= simple` (incluida `undefined`). Invariante de partición verificado. **Cerrado.** |
| R2 | Deploy backend desactualizado no envía `tier`/`intent`. | Campos opcionales en TS (F1); `!== "simple"` manda todo al catch-all (F4) → en Simple todo accesible vía catch-all, y el operador puede ir a Experto. Degradación segura, nada se pierde. |
| R3 | Romper `SettingsPage.harness.test.tsx` (monta el panel). | Campos nuevos opcionales → el mock actual (sin `tier`/`intent`) sigue válido. La aserción busca el label del flag, que no cambia. F7 lo verifica. |
| R4 | Cambio posicional en `CategorySpec` rompe construcciones existentes. | Los campos nuevos van **al final con default** (`tier="advanced"`, `intent=""`) → llamadas posicionales existentes siguen válidas (aditivo). |
| R5 | Nombre de icono inexistente en `lucide-react`. | F1 lista solo iconos verificados de `lucide-react@0.453`; fallback a `Settings` si hay duda; `tsc` atrapa cualquier símbolo inexistente en el gate de build. |
| R6 | El hero "salud" se malinterprete como diagnóstico real. | F3 define la salud como % `activas/totales` (presentación), documentado en comentario; no pretende ser un juicio de salud operativa (eso es el Plan 46, otro panel). |
| R7 | Accesibilidad (color como único canal de información). | El label textual y la `intent` siempre presentes; icono `aria-hidden`; `prefers-reduced-motion` respetado (F6). El color es refuerzo, no único portador. |

---

## 6. Fuera de scope

- **Reasignar flags a categorías** o cambiar `_CATEGORY_KEYS` (eso es semántica del Plan 63; acá NO se toca).
- **Nuevas flags o cambios de comportamiento del pipeline** (este plan es presentación + metadata).
- **Tema oscuro/claro nuevo** o sistema de theming global (se reusa lo existente; no se introduce).
- **Persistencia de la preferencia de modo en BD/servidor** (es `localStorage` por diseño — no es config del operador).
- **"Salud operativa real" de runs** (eso es el Plan 46 `OperationalHealthCard`; el hero de F3 es solo % de flags activas).
- **Tests ejecutables de frontend** (vitest no está instalado; el gate real es `tsc`/`npm run build`).
- **Editor de `tier`/`intent` por UI** (son metadata de diseño del sistema, no config del operador; se cambian en código + test).

---

## 7. Glosario, orden de implementación y DoD global

### Glosario
- **`tier`** (`"simple"|"advanced"`): nivel de profundidad de una categoría, declarado en `CategorySpec`. Determina si aparece en modo Simple directamente o cae en el catch-all.
- **`intent`**: frase humana ("¿qué querés lograr?") asociada a una categoría, para navegación por intención. Vive en `CategorySpec`.
- **Catch-all "Todo lo demás"**: sección colapsable en modo Simple que contiene TODAS las categorías `tier != "simple"`. Garantiza descubribilidad total.
- **Hero / Estado del Arnés**: encabezado visual con perfil activo, stats (activas/totales/con-default) y barra de salud (% activas).
- **`CATEGORY_VISUALS`**: mapa estático slug→{color, icono} en el frontend (`harnessVisuals.ts`).
- **Modo Simple/Experto**: preferencia de presentación persistida en `localStorage` (`stacky.harness.uiMode`), default Simple.

### Orden de implementación
**F0** (backend: `tier`/`intent` + tests) → **F1** (tipos TS + `harnessVisuals.ts`) → **F2** (`useHarnessUiPrefs`) → **F3** (hero) → **F4** (toggle + catch-all) → **F5** (color/icono/intent por sección) → **F6** (pulido CSS) → **F7** (no-regresión + DoD).
F0 y F1 pueden hacerse en paralelo (F1 declara campos opcionales que no dependen del valor real de F0). F3..F6 dependen de F1+F2.

### DoD global (binario)
1. `pytest tests/test_harness_flags.py -q` (desde `Stacky Agents/backend`, con el `.venv`) → **0 failed**, incluyendo `test_every_category_has_tier_and_intent`, `test_list_categories_exposes_tier_and_intent`, `test_at_least_one_simple_and_one_advanced_category`.
2. `npm run build` (desde `Stacky Agents/frontend`) → **exit 0, 0 errores TS**.
3. `SettingsPage.harness.test.tsx` sin cambios de aserción (campos nuevos opcionales).
4. Invariante de partición F4 garantizado por construcción (filtro `=== "simple"` y su complemento).
5. Impacto por runtime declarado NINGUNO en F0..F7; ninguna flag cambia de nombre/tipo/default/efecto.
6. Trabajo del operador: **ninguno** (preferencia de modo opt-in, default Simple; sin nueva config de pipeline).
