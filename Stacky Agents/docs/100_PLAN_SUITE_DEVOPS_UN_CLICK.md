# Plan 100 — Suite DevOps en un click: activar el paquete completo de flags DevOps desde un modal HITL

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** infraestructura transversal del panel DevOps (87-91, 97, 98, 99). NO pertenece
a la serie E2E 93-96 y NO depende de ninguno de esos planes pendientes; tampoco ninguno
de ellos depende de este. Puede implementarse en paralelo.
**Frontera con los planes de flags (33, 63, 82, 86):** este plan NO cambia el subsistema
de flags del arnés (registro, categorías, defaults curados, ayuda llana, perfiles). Es
**azúcar de UI ENCIMA** de ese subsistema: reusa `HarnessFlags.list()` y
`HarnessFlags.update()` tal cual existen. No crea ninguna `FlagSpec` nueva, no toca
`_CURATED_DEFAULTS_ON`, no toca `_CATEGORY_KEYS`, no toca `harness_defaults.env` ni
`config.py`. Por eso NO cruza el gotcha de `FlagSpec` (default OFF) — no hay flag nueva.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| `HarnessFlags.list()` — devuelve todas las flags con `label`, `description`, `value`, `category`, `plain_help`, `requires` | `frontend/src/api/endpoints.ts:859-860` |
| `HarnessFlags.update(updates)` — PUT multi-flag; body `{updates:{KEY:val}}`; devuelve `{ok, applied, restart_required_keys}` | `frontend/src/api/endpoints.ts:865-874` |
| `PUT /api/harness-flags` valida TODO o nada (`apply_updates`, `ValueError → 400 sin escribir`) y hace hot-apply | `backend/api/harness_flags.py:117-174` (validación atómica en `:139-142`) |
| Tipo `HarnessFlagView` (incluye `value`, `category`, `plain_help?`) | `frontend/src/api/endpoints.ts:653-682` |
| `FlagGateBanner` — precedente de activación de UNA flag con `HarnessFlags.update({[k]:true})`, sin flag propia, HITL | `frontend/src/components/devops/FlagGateBanner.tsx:34` |
| Categoría `devops` del registry (6 flags) | `backend/services/harness_flags.py:177-184` |
| Flags de pipeline que el panel consume (`generator_enabled`/`trigger_enabled` del health) | `backend/services/harness_flags.py:167-168` (`STACKY_PIPELINE_GENERATOR_ENABLED`, `STACKY_PIPELINE_TRIGGER_ENABLED`) |
| Shell del panel con react-query (`useQuery` de health y servers) | `frontend/src/pages/DevOpsPage.tsx:113-117`, `:124-129` |
| Registro declarativo `DEVOPS_SECTIONS` + gate por sección | `frontend/src/pages/DevOpsPage.tsx:68-110`, `:208-234` |
| Carpeta de modelos puros del panel (destino del helper nuevo) | `frontend/src/devops/` (`specBuilder.ts`, `presetsModel.ts`, `pipelinePresets.ts`) |
| Patrón de test vitest TS-puro (estilo de la casa) | `frontend/src/devops/pipelinePresets.test.ts`, `frontend/src/pages/__tests__/DevOpsPage.test.ts` |
| Estilos del panel (clases reusables) | `frontend/src/components/devops/devops.module.css` (`alertWarning`, `btnSuccess`, `textDanger`) |

**GAP VERIFICADO (no existe hoy, búsqueda dirigida):** activar la suite DevOps completa
exige activar 8 flags **una por una**. Hoy cada sección gated muestra su propio
`FlagGateBanner` con un botón "Activar ahora" que activa SOLO su flag
(`FlagGateBanner.tsx:34`, `HarnessFlags.update({[flagKey]:true})`), y el panel base
(`STACKY_DEVOPS_PANEL_ENABLED`) + las 2 flags de pipeline (generator/trigger) se activan
aparte en Configuración → Arnés. No existe ningún componente que ofrezca activar el
paquete coherente de una sola vez. El endpoint `PUT /api/harness-flags` **ya soporta
multi-flag atómico** (`harness_flags.py:117-174`) — la capacidad backend está; falta el
gesto de UI que la use. Conclusión: el gap es puramente de frontend y se cierra reusando
endpoints existentes, sin backend nuevo.

---

## 1. Objetivo + KPI

Dar al operador **un solo botón + un solo confirm** para activar todo el paquete de flags
que el panel DevOps necesita (`STACKY_DEVOPS_PANEL_ENABLED` + las 4 secciones + detección
de stack + generador y trigger de pipeline = 8 flags), en **un único request atómico**
(`PUT /api/harness-flags` con las 8 keys), en vez de 8 activaciones sueltas repartidas
entre el panel y Configuración → Arnés. Human-in-the-loop total: un modal lista
exactamente qué se va a activar (label + ayuda llana) y nada se aplica sin el click de
confirmación. Idempotente: solo se ofrecen las flags que están OFF.

**KPI (medibles; los criterios binarios están en cada fase):**

| Métrica | Hoy | Con este plan | Cómo se mide |
|---|---|---|---|
| Clicks para dejar la suite DevOps completa operativa (desde 0 flags) | 8 botones "Activar ahora" en ≥2 pantallas | **1 botón + 1 confirm** | contar clicks en la UI |
| Requests HTTP para activar las 8 flags | 8× `PUT /api/harness-flags` (uno por banner) | **1× `PUT /api/harness-flags`** (8 keys) | pestaña Network |
| Pantallas que el operador debe visitar | panel DevOps (5 banners) + Configuración → Arnés (3 flags) | **0 cambios de pantalla** (todo en el shell del panel) | navegación manual |
| Riesgo de dejar la suite a medias (olvidar una flag) | alto (activación manual pieza por pieza) | **nulo** (paquete atómico: todo o nada) | inspección del payload en Network |
| Visibilidad de qué se activa antes de aplicar | ninguna (cada banner activa a ciegas) | **total** (modal lista label + ayuda llana + estado de cada flag) | inspección visual del modal |

## 2. Por qué ahora / gap que cierra (evidencia)

1. **8 activaciones sueltas.** El operador que abre el panel DevOps por primera vez ve
   las sub-tabs deshabilitadas (`DevOpsPage.tsx:177`, `disabled={!ctx.health.flag_enabled}`)
   y, al entrar a cada sección gated, un `FlagGateBanner` que activa **solo esa** flag
   (`FlagGateBanner.tsx:34`). Publicaciones, Ambientes, Agente y Servidores son 4 banners
   distintos (`DevOpsPage.tsx:74-109`); el panel base y generator/trigger van por
   Configuración → Arnés. Son 8 gestos en ≥2 pantallas para el mismo objetivo obvio:
   "quiero DevOps completo".
2. **La capacidad atómica ya existe, sin usar.** `PUT /api/harness-flags` acepta
   `{updates:{K1:true, K2:true, ...}}`, valida TODO junto (`apply_updates`, y si algo
   falla es `400` **sin escribir nada** — `harness_flags.py:139-142`), persiste y hace
   hot-apply. Es exactamente el primitivo que un "activar suite" necesita, pero ningún
   componente lo llama con más de una key (todos los usos hoy son de a una).
3. **El drift de flags de hoy es la prueba del dolor.** El working tree de 2026-07-06
   muestra las flags DevOps activadas pieza por pieza con tests centinela desincronizados
   (`test_plan87_devops_flag.py` ya espera default ON; `config.py`/`harness_defaults.env`
   sin commitear). Ese desorden nace justamente de activar flags de a una a mano. Un
   activador de paquete no arregla el drift (es de defaults versionados, fuera de scope)
   pero **elimina la causa raíz de futuros drifts**: una activación coherente y visible.
4. **Los planes 98 y 99 ya abaratan el transporte y el preview**; falta abaratar el
   ONBOARDING. Este plan cierra la última fricción de arranque del panel: pasar de "panel
   apagado" a "panel operativo" en un gesto.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **Sin flag nueva — UI aditiva de conveniencia.** El activador NO crea ninguna
   `FlagSpec`, NO cambia el registry, NO toca `_CURATED_DEFAULTS_ON`. Es un componente
   que reusa `HarnessFlags.list()`/`update()`. Precedente directo: `FlagGateBanner`
   (Plan 87) tampoco tiene flag propia y activa flags con el mismo endpoint. Por
   construcción **no cruza el gotcha de `FlagSpec` con `default=False`** (Plan 63): no
   hay flag que registrar.
2. **Human-in-the-loop innegociable.** El botón NUNCA activa nada solo. Abre un modal
   que lista las flags a activar (label + ayuda llana + estado); la activación ocurre
   únicamente tras el click "Activar N flags". El operador puede destildar cualquier flag
   antes de confirmar. Nada autónomo, nada proactivo.
3. **Idempotente y no destructivo.** El modal solo ofrece (con checkbox) las flags que
   están **OFF**; las que ya están ON se muestran como "ya activas" sin checkbox y no se
   re-envían. El activador **nunca apaga** una flag (no hay path de desactivación en este
   plan). Backward-compatible: si el operador no usa el botón, el panel funciona
   idéntico a hoy (los `FlagGateBanner` por sección siguen intactos).
4. **Atomicidad heredada del backend.** Se envían todas las keys seleccionadas en UN
   `PUT /api/harness-flags`. Si el backend rechaza el lote (400), no se activa ninguna
   (garantía de `apply_updates`) y el modal muestra el error sin dejar estado a medias.
   Como el modal solo manda keys que vinieron de `HarnessFlags.list()` (keys reales del
   registry con su tipo bool), un 400 por key desconocida es imposible en la práctica.
5. **No toca el drift de defaults.** El activador usa el mismo `_write_env` del endpoint
   (`harness_flags.py:32-68`), que escribe al `.env` de runtime (`backend_root()/.env`),
   NO a `harness_defaults.env` ni a `config.py`. No introduce ni empeora el drift
   documentado de defaults versionados: es ortogonal a él.
6. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** este plan es UI del
   panel DevOps; NINGÚN runner ni prompt de agente consume el activador ni las flags por
   esta vía (los consumidores son componentes React). Impacto runtime: **NINGUNO**,
   declarado por fase (precedente: Plan 78, rediseño UI con impacto runtime nulo). Las
   flags que activa ya existían y ya las leía el sistema; su semántica no cambia.
7. **Cero trabajo extra del operador.** El activador es **opt-in por naturaleza**: es un
   botón que aparece solo cuando faltan flags y que el operador decide usar. No agrega
   configuración nueva, no exige pasos, no cambia datos persistidos.
8. **No degradar.** Cero dependencias nuevas (npm/py). Cero endpoints nuevos. El shell
   `DevOpsPage.tsx` recibe SOLO cambios aditivos (una query nueva + un banner nuevo por
   encima de las sub-tabs), sin tocar el registro `DEVOPS_SECTIONS` ni el gate por
   sección.

---

## F0 — Helper puro `devopsSuite.ts` (toda la lógica testeable de la suite)

**Objetivo:** concentrar en un módulo TS puro (sin React) la definición del paquete de
flags de la suite y las funciones que el modal y el shell consumen, para que TODO lo
testeable viva acá (estilo de la casa: componentes delgados, lógica pura testeada).
**Valor:** el modal (F1) y el shell (F2) quedan triviales; los tests son deterministas
sin render.

**Archivo a crear (exacto):** `Stacky Agents/frontend/src/devops/devopsSuite.ts`

**Símbolos exactos:**

```typescript
import type { HarnessFlagView } from '../api/endpoints';

// Flags DevOps que NO están en la categoría 'devops' del registry pero que el panel
// necesita (viven en 'epicas_ado'): generador y trigger de pipeline.
// Ver backend/services/harness_flags.py:167-168.
export const DEVOPS_SUITE_EXTRA_KEYS: readonly string[] = [
  'STACKY_PIPELINE_GENERATOR_ENABLED',
  'STACKY_PIPELINE_TRIGGER_ENABLED',
];

// La flag base va SIEMPRE primero en el listado (es el panel maestro).
export const DEVOPS_SUITE_BASE_KEY = 'STACKY_DEVOPS_PANEL_ENABLED';

export interface SuiteFlag {
  key: string;
  label: string;
  description: string;
  plainWhat: string | null; // plain_help.what si existe, si no null
  isOn: boolean;            // value === true
}

export interface SuitePlan {
  all: SuiteFlag[];      // todas las flags de la suite, base primero
  missing: SuiteFlag[];  // las que están OFF (a ofrecer)
  present: SuiteFlag[];  // las que ya están ON (informativas)
}

// Dada la lista cruda de HarnessFlags.list().flags, arma el plan de la suite.
export function computeSuitePlan(flags: HarnessFlagView[]): SuitePlan {
  const inSuite = (f: HarnessFlagView) =>
    f.category === 'devops' || DEVOPS_SUITE_EXTRA_KEYS.includes(f.key);
  const mapped: SuiteFlag[] = flags.filter(inSuite).map((f) => ({
    key: f.key,
    label: f.label,
    description: f.description,
    plainWhat: f.plain_help?.what ?? null,
    isOn: f.value === true,
  }));
  // Ordenar: la base primero, el resto por key ascendente (determinista).
  mapped.sort((a, b) => {
    if (a.key === DEVOPS_SUITE_BASE_KEY) return -1;
    if (b.key === DEVOPS_SUITE_BASE_KEY) return 1;
    return a.key.localeCompare(b.key);
  });
  return {
    all: mapped,
    missing: mapped.filter((f) => !f.isOn),
    present: mapped.filter((f) => f.isOn),
  };
}

// {key: true} para cada key seleccionada (payload del PUT multi-flag).
export function buildSuiteUpdatePayload(selectedKeys: string[]): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const k of selectedKeys) out[k] = true;
  return out;
}

// Toggle inmutable de una key en la lista de seleccionadas (para el modal).
export function toggleKey(selected: string[], key: string): string[] {
  return selected.includes(key)
    ? selected.filter((k) => k !== key)
    : [...selected, key];
}

// Etiqueta del botón, o null si no falta ninguna flag (no mostrar botón).
export function suiteButtonLabel(plan: SuitePlan): string | null {
  if (plan.missing.length === 0) return null;
  return `Activar suite DevOps (${plan.missing.length} pendientes)`;
}
```

**Casos borde cubiertos:** lista vacía ⇒ `all/missing/present` vacíos, `suiteButtonLabel`
null; flag de otra categoría (p.ej. `STACKY_TASK_GATE_ENABLED`) ⇒ NO entra;
`plain_help` ausente o null ⇒ `plainWhat = null`; base presente ⇒ primera en `all`.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/devops/devopsSuite.test.ts`, 9 casos:

1. `computeSuitePlan incluye las 6 flags de categoría devops` — dado un fixture con las 6
   keys `category:'devops'`, `all.length === 6`.
2. `computeSuitePlan suma las 2 extras de pipeline` — fixture con generator/trigger en
   `category:'epicas_ado'` ⇒ ambas en `all` (total 8).
3. `computeSuitePlan excluye otras categorías` — una flag `category:'flujo_funcional'` NO
   aparece en `all`.
4. `la base va primera` — `all[0].key === 'STACKY_DEVOPS_PANEL_ENABLED'`.
5. `missing solo contiene las OFF` — flags con `value:false` van a `missing`, las
   `value:true` no.
6. `present solo contiene las ON` — simétrico.
7. `plainWhat cae a null sin plain_help` — flag sin `plain_help` ⇒ `plainWhat === null`;
   con `plain_help.what` ⇒ ese string.
8. `buildSuiteUpdatePayload arma {key:true} solo para seleccionadas` — entrada `['A','B']`
   ⇒ `{A:true, B:true}`; entrada `[]` ⇒ `{}`.
9. `toggleKey agrega/quita inmutablemente` y `suiteButtonLabel` es null con `missing=[]` y
   `"Activar suite DevOps (3 pendientes)"` con 3 faltantes.

**Comando (desde el directorio frontend):**

```
cd "Stacky Agents/frontend" && npx vitest run src/devops/devopsSuite.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** 9 tests verdes + `tsc --noEmit` 0 errores.
**Flag:** ninguna (helper puro; no gated). **Default seguro:** N/A.
**Impacto por runtime:** NINGUNO (TS puro; ningún runner lo importa; verificable por grep
de `devopsSuite` fuera de `frontend/`). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F1 — Modal HITL `DevOpsSuiteModal.tsx` (delgado, sin lógica no testeada)

**Objetivo:** un modal que lista las flags faltantes con checkbox (default todas
marcadas), muestra las ya activas como informativas, y en el confirm dispara UN
`HarnessFlags.update` con las seleccionadas.
**Valor:** el gesto "activar todo" con visibilidad y control totales (HITL).

**Archivo a crear (exacto):**
`Stacky Agents/frontend/src/components/devops/DevOpsSuiteModal.tsx`

**Props exactas:**

```typescript
import type { SuitePlan } from '../../devops/devopsSuite';

export interface DevOpsSuiteModalProps {
  plan: SuitePlan;
  onClose: () => void;
  onActivated: () => void; // el shell hace refetch de health + flags
}
```

**Comportamiento (pseudocódigo):**

```tsx
import React, { useState } from 'react';
import { HarnessFlags } from '../../api/endpoints';
import { buildSuiteUpdatePayload, toggleKey } from '../../devops/devopsSuite';
import styles from './devops.module.css';

export const DevOpsSuiteModal: React.FC<DevOpsSuiteModalProps> = ({ plan, onClose, onActivated }) => {
  // Default: todas las faltantes seleccionadas.
  const [selected, setSelected] = useState<string[]>(plan.missing.map((f) => f.key));
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restartMsg, setRestartMsg] = useState<string | null>(null);

  const handleActivate = async () => {
    if (selected.length === 0) return;
    setActivating(true); setError(null); setRestartMsg(null);
    try {
      const res = await HarnessFlags.update(buildSuiteUpdatePayload(selected));
      if (res.restart_required_keys && res.restart_required_keys.length > 0) {
        setRestartMsg('Algunas flags quedaron guardadas pero requieren reiniciar el backend.');
      }
      onActivated();      // el shell refetchea health+flags
      if (!res.restart_required_keys?.length) onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al activar la suite');
    } finally {
      setActivating(false);
    }
  };

  // Render: overlay + tarjeta.
  // - plan.missing: cada una con <input type=checkbox checked={selected.includes(key)}
  //   onChange={() => setSelected(toggleKey(selected, key))} /> + <strong>{label}</strong>
  //   + (plainWhat ?? description).
  // - plan.present: lista gris "Ya activas: label1, label2..." SIN checkbox.
  // - Botón "Activar {selected.length} flags" disabled={activating || selected.length===0}.
  // - Botón "Cancelar" → onClose.
  // - error → styles.textDanger ; restartMsg → styles.alertWarning.
};
```

**Casos borde:** `selected` vacío ⇒ botón deshabilitado (no se puede mandar `{}`);
`restart_required_keys` no vacío ⇒ se muestra aviso y el modal NO se autocierra (para que
el operador lea); error de red ⇒ inline, sin cerrar, estado consistente (no se activó
nada por la atomicidad del backend).

**Tests PRIMERO (TDD)** — la lógica testeable ya vive en F0; este archivo agrega los casos
de armado de payload desde una selección parcial, en
`Stacky Agents/frontend/src/devops/devopsSuite.test.ts` (mismo archivo, bloque nuevo):

1. `payload de selección parcial` — de `plan.missing` con 3 keys, destildar 1 ⇒
   `buildSuiteUpdatePayload(restantes)` tiene 2 keys, la destildada ausente.
2. `selección vacía ⇒ payload vacío` — `buildSuiteUpdatePayload([]) === {}` (el modal usa
   esto para deshabilitar el botón).

**Comando:**

```
cd "Stacky Agents/frontend" && npx vitest run src/devops/devopsSuite.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 2 tests nuevos verdes (11 en total en el
archivo) + `tsc --noEmit` 0 errores + el modal importa `HarnessFlags`,
`buildSuiteUpdatePayload`, `toggleKey` y compila.
**Flag:** ninguna. **Impacto por runtime:** NINGUNO (componente React). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F2 — Integración en el shell `DevOpsPage.tsx` (banner "Activar suite" + refetch)

**Objetivo:** mostrar arriba de las sub-tabs un banner con el botón de suite cuando falte
≥1 flag, abrir el modal, y refrescar health + flags al activar.
**Valor:** el gesto "un click" queda a la vista apenas se abre el panel, incluso con el
panel base apagado (el activador incluye `STACKY_DEVOPS_PANEL_ENABLED`).

**Archivo a editar (exacto):** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx`

**Cambios (aditivos, sin tocar `DEVOPS_SECTIONS` ni el gate por sección):**

1. Imports nuevos (junto a los existentes):

```tsx
import { HarnessFlags } from '../api/endpoints';
import { computeSuitePlan, suiteButtonLabel } from '../devops/devopsSuite';
import { DevOpsSuiteModal } from '../components/devops/DevOpsSuiteModal';
```

2. Dentro de `DevOpsPage`, después de `healthQuery` (`DevOpsPage.tsx:113-117`):

```tsx
  const flagsQuery = useQuery({
    queryKey: ['harness-flags'],
    queryFn: () => HarnessFlags.list(),
    retry: false,
  });
  const suitePlan = computeSuitePlan(flagsQuery.data?.flags ?? []);
  const suiteLabel = suiteButtonLabel(suitePlan);
  const [showSuiteModal, setShowSuiteModal] = useState(false);

  const onSuiteActivated = () => {
    healthQuery.refetch();
    flagsQuery.refetch();
  };
```

3. En el JSX, INMEDIATAMENTE antes de la barra de sub-tabs (`DevOpsPage.tsx:171`,
   `{/* Barra de sub-tabs ... */}`):

```tsx
      {suiteLabel && (
        <div className={styles.alertWarning} style={{ marginBottom: '12px' }}>
          <span style={{ marginRight: '12px' }}>
            Activá todo el panel DevOps de una vez ({suitePlan.missing.length} flags pendientes).
          </span>
          <button className={styles.btnSuccess} onClick={() => setShowSuiteModal(true)}>
            {suiteLabel}
          </button>
        </div>
      )}
      {showSuiteModal && (
        <DevOpsSuiteModal
          plan={suitePlan}
          onClose={() => setShowSuiteModal(false)}
          onActivated={onSuiteActivated}
        />
      )}
```

   (Requiere `import styles from '../components/devops/devops.module.css';` si no está ya;
   verificar el import de `useState` — ya presente en `DevOpsPage.tsx:16`.)

**Casos borde:** `flagsQuery` cargando ⇒ `suitePlan` de lista vacía ⇒ `suiteLabel` null ⇒
banner no aparece (no parpadea un botón vacío); todas ON ⇒ banner ausente; `flagsQuery`
error ⇒ `?? []` ⇒ banner ausente (el panel sigue usable con los `FlagGateBanner` por
sección como fallback).

**Tests PRIMERO (TDD)** — extender `Stacky Agents/frontend/src/pages/__tests__/DevOpsPage.test.ts`
(existe) con 3 casos que importan las funciones puras usadas por el shell:

1. `banner visible con ≥1 faltante` — `suiteButtonLabel(computeSuitePlan(fixtureConOFF))`
   !== null.
2. `banner oculto con todas ON` — `suiteButtonLabel(computeSuitePlan(fixtureTodasON))`
   === null.
3. `el conteo del banner coincide con missing` — el número en la etiqueta ===
   `computeSuitePlan(...).missing.length`.

**Comando:**

```
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/DevOpsPage.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/devops/devopsSuite.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 3 tests de `DevOpsPage.test.ts` verdes + F0/F1
verdes + `tsc --noEmit` 0 errores.
**Flag:** ninguna. **Impacto por runtime:** NINGUNO (shell React). Fallback: si
`flagsQuery` falla, el banner no aparece y el panel funciona como hoy.
**Trabajo del operador:** ninguno (opt-in: el botón está, se usa si se quiere).

---

## F3 — Cierre: verificación manual HITL + checklist binario

**Objetivo:** confirmar en la app real que el gesto de un click activa el paquete en un
solo request, con HITL, sin romper el flujo por-sección existente.
**Valor:** evidencia de que el KPI (1 click / 1 request) se cumple end-to-end.

**Sin archivos nuevos.** Guion de verificación manual (el operador o el implementador lo
corre una vez; NADA se automatiza que saque al operador del lazo):

1. Con las 8 flags OFF (env limpio), abrir el panel DevOps → aparece el banner "Activar
   suite DevOps (8 pendientes)". **Binario:** el banner se ve; las sub-tabs están grises.
2. Click en el botón → abre el modal con 8 flags tildadas + su ayuda llana. **Binario:**
   se listan 8, ninguna activada aún (verificar en otra pestaña que las flags siguen OFF).
3. Destildar 1 flag (p.ej. Servidores) → el botón dice "Activar 7 flags". Confirmar →
   **una** request `PUT /api/harness-flags` en Network con 7 keys. **Binario:** 1 sola
   request; body con 7 keys `:true`; la destildada ausente.
4. Tras el confirm, el panel refresca: 7 sub-tabs habilitadas, Servidores sigue gated con
   su `FlagGateBanner` (fallback por-sección intacto). El banner de suite ahora dice
   "Activar suite DevOps (1 pendientes)". **Binario:** conteo = 1.
5. Activar la última desde su `FlagGateBanner` (camino viejo) → el banner de suite
   desaparece. **Binario:** sin banner cuando `missing = 0`.

**Comando de regresión (no-romper) — todos deben seguir verdes:**

```
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/DevOpsPage.test.ts src/devops/devopsSuite.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 5 pasos manuales cumplen su condición + `tsc` 0
errores + suite de tests verde. Sin cambios en backend ⇒ sin tests backend nuevos ⇒ sin
ratchet nuevo (declarado: este plan no agrega archivos de test Python).
**Flag:** ninguna. **Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno (la verificación es del implementador, una sola vez).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Alguna flag de la suite fuera `restart_required` y no aplique en caliente | El endpoint ya devuelve `restart_required_keys` (`harness_flags.py:170-172`); el modal lo muestra y NO se autocierra. Las flags DevOps son `env_only=False` / hot-apply (verificado en `test_plan87`); en la práctica no habrá restart. |
| El lote sea rechazado (400) y quede estado a medias | Imposible por diseño: `apply_updates` valida TODO o nada **sin escribir** (`harness_flags.py:139-142`). El modal muestra el error y no hay activación parcial. |
| Doble activación / re-activar una flag ya ON | El modal solo ofrece las OFF; las ON van sin checkbox. Reactivar sería no-op igual. |
| El paquete "extra" (generator/trigger) cambie de nombre o categoría | `DEVOPS_SUITE_EXTRA_KEYS` es una constante única y testeada (F0 test 2). Si el registry cambia esas keys, el test 2 falla y avisa. Las 6 de categoría `devops` se derivan solas (robustas a altas futuras). |
| Empeorar el drift de `harness_defaults.env` | No lo toca: el activador escribe al `.env` de runtime vía el endpoint existente, igual que el `FlagGateBanner` de a una. Ortogonal al drift de defaults versionados (§3.5). |
| El banner tape contenido o parpadee mientras carga `flagsQuery` | Con lista vacía `suiteButtonLabel` es null ⇒ el banner no se renderiza hasta tener datos; es aditivo arriba de las sub-tabs, no reemplaza nada. |

## 6. Fuera de scope (v1)

- **Editor de catálogo de procesos inline.** Cargar el `process_catalog` sin salir de
  Publicaciones (hoy `PublicationsSection.tsx:224-228` manda a Configuración → Perfil del
  cliente) requiere reusar o duplicar el editor de catálogo, que vive en otra pantalla y
  cuyo mecanismo de navegación no se toca en este plan. Amerita su propio plan.
- **Auto-creación del preset TODO de pipeline.** El preset TODO de **publicaciones** ya
  existe como botón (`PublicationsSection.tsx:234-244`); un preset TODO del **builder de
  pipeline** dependería de la galería del Plan 97 y es una feature aparte.
- **Desactivar la suite de un click (simétrico).** Este plan solo activa (nunca apaga),
  por seguridad. La desactivación en lote queda para v2.
- **Perfiles del arnés.** Ya existe `POST /api/harness-flags/profile` (off/safe/full,
  `harness_flags.py:87-114`); la suite DevOps es un subconjunto granular y NO reemplaza
  ni modifica ese mecanismo.

## 7. Glosario

- **Suite DevOps:** el paquete de 8 flags que deja el panel DevOps completamente operativo
  — `STACKY_DEVOPS_PANEL_ENABLED` (base) + `PUBLICATIONS`/`ENVIRONMENTS`/`AGENT`/`SERVERS`
  + `STACKY_DEVOPS_STACK_DETECT_ENABLED` + `STACKY_PIPELINE_GENERATOR_ENABLED` +
  `STACKY_PIPELINE_TRIGGER_ENABLED`.
- **Flag del arnés:** interruptor de feature del sistema, registrado en `FLAG_REGISTRY`,
  editable por UI (Configuración → Arnés) y persistido en el `.env` de runtime.
- **`FlagGateBanner`:** aviso por-sección que activa UNA flag con un click (Plan 87). El
  activador de suite es su hermano de "activar todas".
- **Health del panel:** `GET /api/devops/health`, agregador de booleans que dice qué
  secciones están habilitadas; el shell lo usa para el gate por sección.
- **Hot-apply:** aplicación en caliente de una flag (sin reiniciar el backend) que hace el
  endpoint `PUT /api/harness-flags` para las flags `env_only=False`.
- **HITL (human-in-the-loop):** ninguna acción se ejecuta sin confirmación explícita del
  operador; acá, el modal + el botón "Activar N flags".
- **Ayuda llana (`plain_help`):** explicación en lenguaje sencillo de una flag (Plan 86),
  expuesta en `HarnessFlagView.plain_help`.

## 8. Orden de implementación

1. **F0** — `devopsSuite.ts` + `devopsSuite.test.ts` (9 tests). Verde antes de seguir.
2. **F1** — `DevOpsSuiteModal.tsx` + los 2 tests de payload parcial en `devopsSuite.test.ts`.
3. **F2** — editar `DevOpsPage.tsx` (query + banner + modal) + 3 tests en `DevOpsPage.test.ts`.
4. **F3** — verificación manual HITL (5 pasos) + regresión (`tsc` + vitest de los 2 archivos).

## 9. Definición de Hecho (DoD) global

- [ ] `devopsSuite.test.ts` verde (11 casos) y `DevOpsPage.test.ts` verde (3 casos nuevos).
- [ ] `npx tsc --noEmit` 0 errores en `frontend/`.
- [ ] El banner "Activar suite DevOps (N pendientes)" aparece solo cuando `missing ≥ 1` y
      desaparece con `missing = 0`.
- [ ] Confirmar el modal dispara **1** `PUT /api/harness-flags` con todas las keys
      seleccionadas (verificado en Network).
- [ ] HITL: ninguna flag se activa sin el click "Activar N flags"; las flags ON no se
      re-envían; el operador puede destildar antes de confirmar.
- [ ] NO se creó ninguna `FlagSpec` nueva; NO se tocó `harness_flags.py` (registry),
      `config.py`, `harness_defaults.env` ni `_CURATED_DEFAULTS_ON`.
- [ ] Backward-compatible: con el botón sin usar, el panel funciona idéntico a hoy; los
      `FlagGateBanner` por sección siguen operativos como fallback.
- [ ] Impacto runtime NINGUNO (verificable por grep: `devopsSuite`/`DevOpsSuiteModal` no
      aparecen fuera de `frontend/`).
- [ ] Trabajo del operador: ninguno (opt-in de conveniencia).
