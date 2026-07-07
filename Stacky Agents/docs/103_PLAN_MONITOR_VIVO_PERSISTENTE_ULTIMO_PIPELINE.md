# Plan 103 — Monitor vivo y persistente: badge del último pipeline en el shell DevOps, con backoff y estado legible

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** infraestructura transversal del panel DevOps (87-91, 97-102). NO pertenece a la
serie E2E 93-96 y NO depende de ninguno de esos planes; es el candidato 6 (último) del
portafolio de mejoras del dashboard. Complementa al Plan 102 ("Publicar en un paso"): el
102 dispara el pipeline en un click y deja el monitoreo continuo EXPLÍCITAMENTE fuera de
scope; este plan cubre ese monitoreo.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| `CIPipeline.monitor(project, pipelineId)` → `CIMonitorResponse` (`status`, `ref`, `web_url`, `tracker_type`, `source`) | `frontend/src/api/endpoints.ts:2934-2942`, `:2967-2970` |
| `CIPipeline.trigger(...)` → `CITriggerResponse` (`pipeline_id?`, `status`, `ref`, `web_url`) | `frontend/src/api/endpoints.ts:2916-2924`, `:2952-2965` |
| Polling fijo de 3s SIN backoff (el que este plan mejora) | `frontend/src/components/devops/TriggerPipelineSection.tsx:97-104` |
| `JSON.stringify(monitorStatus, null, 2)` crudo en pantalla (lo que este plan reemplaza) | `frontend/src/components/devops/TriggerPipelineSection.tsx:163-165` |
| Estado del monitor EFÍMERO (useState local; se pierde al recargar; invisible fuera de la sección) | `frontend/src/components/devops/TriggerPipelineSection.tsx:20-22` |
| Patrón de persistencia con `localStorage` directo (el que este plan copia) | `frontend/src/pages/DevOpsPage.tsx:131-136` (`selectedServer`) |
| Store zustand con `create` plano (estilo de la casa; NO usa middleware `persist`) | `frontend/src/store/uiSectionsStore.ts:25-31` |
| Health SIEMPRE-200 con booleans aditivos por plan | `backend/api/devops.py:26-40` |
| `DevOpsHealth` con index signature para keys aditivas | `frontend/src/pages/DevOpsPage.tsx:22-32` |
| Patrón flag 5 patas + gotchas (`_CATEGORY_KEYS["devops"]`, `_REQUIRES_MAP_FROZEN`, ratchet sh+ps1) | `backend/services/harness_flags.py:177-184`, `backend/tests/test_harness_flags_requires.py` |
| Patrón de test vitest TS-puro (estilo de la casa) | `frontend/src/devops/pipelinePresets.test.ts`, `frontend/src/pages/__tests__/DevOpsPage.test.ts` |
| Estilos del panel (clases de tono) | `frontend/src/components/devops/devops.module.css` (`alertSuccess`, `alertWarning`, `alertError`) |

**GAP VERIFICADO (no existe hoy, búsqueda dirigida):** el monitoreo del pipeline vive
dentro de `TriggerPipelineSection` con `useState` local (`TriggerPipelineSection.tsx:20-22`)
y un `setInterval` fijo de 3000ms (`:99-101`). El estado se pierde si el operador recarga
la página, y no es visible desde otras sub-secciones del panel (Pipelines, Ambientes,
Servidores). El resultado se muestra como `JSON.stringify` crudo (`:163-165`). No existe
ningún store DevOps de "último pipeline" (`grep -r "lastPipeline\|pipelineMonitor" frontend/src` = 0),
ni backoff (el intervalo es constante), ni badge en el shell. Conclusión: el gap es real;
se cierra reusando el endpoint `monitor` existente + el patrón `localStorage` ya usado en
el mismo shell.

---

## 1. Objetivo + KPI

Sacar el estado del último pipeline disparado de la sub-sección efímera y llevarlo a un
**badge persistente en el shell del panel DevOps**, que: (a) sobrevive al cambio de
sub-sección y a la recarga de la página (persistido en `localStorage`), (b) sondea con
**backoff progresivo** (3s → 5s → 10s → 30s tope) en vez de un fijo de 3s, (c) muestra el
estado en **lenguaje legible** (estado + ref + link al pipeline) en vez de JSON crudo, y
(d) cambia de color al terminar aunque el operador esté en otra sección. Todo detrás de
una flag nueva default OFF: con la flag apagada, el comportamiento es byte-idéntico al
actual (polling 3s local + JSON en la sección).

**KPI (medibles; los criterios binarios están en cada fase):**

| Métrica | Hoy (flag OFF / preexistente) | Con flag ON | Cómo se mide |
|---|---|---|---|
| Requests de monitoreo en 2 min de pipeline corriendo | 1 cada 3s = **~40** | 3s,5s,10s luego 30s ⇒ **~7** (−82%) | pestaña Network durante 2 min |
| Estado del pipeline tras recargar la página | **se pierde** (useState local) | **se restaura** desde `localStorage` y el polling se reanuda | recargar con un pipeline corriendo |
| Visibilidad del estado desde otra sub-sección | **nula** (solo en Trigger CI) | **badge en el shell**, visible en todas las sub-secciones | cambiar de sub-tab |
| Legibilidad del resultado | `JSON.stringify` crudo | estado + ref + link, con color por tono | inspección visual |
| Aviso de fin de pipeline en otra sección | **ninguno** | el badge cambia a verde/rojo al terminar | disparar y cambiar de sección |

## 2. Por qué ahora / gap que cierra (evidencia)

1. **El monitoreo es efímero y local.** `TriggerPipelineSection` guarda `pipelineId`,
   `polling` y `monitorStatus` en `useState` (`:20-22`). Al recargar la página se pierde
   todo; el operador que disparó un pipeline y refrescó no tiene forma de recuperar el
   hilo salvo re-disparar (con la idempotencia de 60s ya vencida).
2. **El polling es un fijo de 3s.** El `setInterval(..., 3000)` (`:99-101`) no tiene
   backoff: un pipeline de 10 min son ~200 requests de monitoreo, casi todas idénticas.
3. **El resultado es ilegible.** `JSON.stringify(monitorStatus, null, 2)` (`:163-165`)
   vuelca el objeto crudo (`id`, `tracker_type`, `source`...) en un `<pre>`; el operador
   tiene que leer JSON para saber si su pipeline pasó.
4. **El estado no viaja con el operador.** El montaje persistente del shell
   (`DevOpsPage.tsx`, `display:none`) mantiene el componente vivo, pero su estado no es
   visible desde otra sub-sección: no hay indicador en el shell.
5. **La infraestructura para arreglarlo YA está:** el endpoint `monitor`
   (`endpoints.ts:2967-2970`) devuelve todo lo necesario (`status`, `ref`, `web_url`); el
   mismo shell ya persiste `selectedServer` en `localStorage` (`DevOpsPage.tsx:131-136`);
   el proyecto ya usa stores zustand con `create` plano (`uiSectionsStore.ts:25-31`).

El Plan 102 ("Publicar en un paso") dispara el pipeline en un click y deja
EXPLÍCITAMENTE el monitoreo continuo fuera de su scope (§6 del 102). Este plan es la pieza
que lo complementa: una vez disparado (por el flujo del 102 o por Trigger CI), el badge
persistente sigue el pipeline hasta el final.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **Flag default OFF + byte-idéntico con OFF.** Todo lo nuevo vive detrás de
   `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` (default OFF). Con OFF:
   `TriggerPipelineSection` corre EXACTO como hoy (polling 3s local, JSON en pantalla), el
   badge del shell no se renderiza, el store no se alimenta. Criterio binario por test.
2. **Cero trabajo extra del operador.** Opt-in de 1 click en Configuración → Arnés
   (categoría DevOps), como toda la serie 87-102. Sin pasos manuales nuevos, sin config
   nueva, sin datos persistidos server-side (el estado del badge vive en `localStorage`
   del navegador, no toca la DB ni el client-profile).
3. **Human-in-the-loop intacto.** El monitor solo LEE estado (`CIPipeline.monitor`, un
   GET); NO dispara, cancela ni reintenta pipelines. El badge tiene un botón "×" para que
   el operador lo descarte cuando quiera. Ninguna acción autónoma sobre el pipeline.
4. **Solo lectura, sin nuevos side effects.** El plan no agrega ningún endpoint de
   escritura ni dispara nada; reusa el GET `monitor` existente. El backoff REDUCE la
   carga; nunca la aumenta respecto al fijo de 3s.
5. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** este plan es UI del
   panel + 1 flag; NINGÚN runner ni prompt de agente consume el store, el hook ni el
   badge (los consumidores son componentes React). Impacto runtime: **NINGUNO**,
   declarado por fase (precedente: Plan 78). Fallback: N/A.
6. **Mono-operador sin auth.** Un solo navegador, un solo `localStorage`; nada de estado
   compartido multiusuario ni RBAC.
7. **No degradar.** Cero dependencias nuevas (zustand ya está;
   `localStorage` es del navegador). El shell `DevOpsPage.tsx` recibe SOLO cambios
   aditivos (un hook + un badge por encima de las sub-tabs). `TriggerPipelineSection`
   gana una prop OPCIONAL (`monitorEnabled?`, default false ⇒ comportamiento actual).
8. **Gotchas de flags (obligatorios):** la `FlagSpec` nueva NO lleva kwarg `default`
   (default OFF implícito; `default=False` explícito rompe
   `test_default_known_only_for_curated` — Plan 63). La arista
   `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` se agrega a
   `_REQUIRES_MAP_FROZEN` (R4, profundidad 1). Todo archivo de test backend nuevo se
   registra en `HARNESS_TEST_FILES` de `run_harness_tests.sh` Y `.ps1` (ratchet Plan 49).
9. **Evitar doble polling.** Con la flag ON, `TriggerPipelineSection` DELEGA el polling al
   shell (no corre su `setInterval` local): un único poller por pipeline. Con OFF, la
   sección conserva su poller. Criterio binario por test de la condición.

---

## F0 — Flag `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` (5 patas) + key de health

**Objetivo:** dar de alta la flag que protege TODO el plan, default OFF, activable por UI,
y exponerla al frontend con la key aditiva `pipeline_monitor_enabled` del health.
**Valor:** el guard existe antes que cualquier consumidor.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/config.py` — inmediatamente después del bloque de
   `STACKY_DEVOPS_STACK_DETECT_ENABLED`:

```python
# Plan 103 — Monitor vivo y persistente del ultimo pipeline. Default OFF.
STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED: bool = os.getenv(
    "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED", "false"
).lower() in ("1", "true", "yes")
```

2. `Stacky Agents/backend/services/harness_flags.py`:
   - Agregar `"STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED",  # Plan 103 — badge persistente del ultimo pipeline` como última entrada de `_CATEGORY_KEYS["devops"]` (hoy `:177-184`).
   - Agregar al `FLAG_REGISTRY`, después de la `FlagSpec` de `STACKY_DEVOPS_STACK_DETECT_ENABLED`:

```python
    # ── Plan 103 — Monitor vivo y persistente del ultimo pipeline ────────────────
    FlagSpec(
        key="STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED",
        type="bool",
        label="Monitor persistente de pipelines (Plan 103)",
        description=(
            "Plan 103 — Muestra un badge del ultimo pipeline en el panel DevOps que "
            "sobrevive al cambio de seccion y a la recarga, sondea con backoff "
            "(3s->30s) y muestra el estado legible en vez de JSON. Con OFF todo "
            "funciona igual que antes (monitoreo dentro de Trigger CI, 3s fijo)."
        ),
        group="global",
        env_only=False,  # editable por UI (categoria 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",
    ),
```

   **PROHIBIDO** pasar `default=False` (gotcha Plan 63) y **PROHIBIDO** `requires`
   apuntando a otra flag que no sea `STACKY_DEVOPS_PANEL_ENABLED` (R4).

3. `Stacky Agents/backend/services/harness_flags_help.py` — nueva entrada en el dict de
   ayudas, junto a las devops (patrón de las flags 97/98):

```python
    "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED": PlainHelp(
        what="Un cartelito en el panel DevOps que sigue tu ultimo pipeline y no se pierde si cambias de pestania o recargas.",
        on_effect="Si la activás: ves el estado del ultimo pipeline (corriendo/ok/fallo) con un link, en cualquier seccion del panel, y el sistema consulta cada vez menos seguido para no saturar.",
        off_effect="Si la apagás: el monitoreo sigue como antes, solo dentro de Trigger CI, se pierde al recargar y consulta cada 3 segundos fijos.",
        example="Como el globito de 'tu pedido va en camino' que te sigue en toda la app, no solo en la pantalla donde lo pediste.",
    ),
```

4. `Stacky Agents/backend/harness_defaults.env` — agregar
   `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED=false` junto al bloque DEVOPS.

5. `Stacky Agents/backend/api/devops.py` — en el route de health (`:26-40`), agregar la
   key aditiva:

```python
        "pipeline_monitor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED", False)),  # Plan 103
```

6. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar al mapa
   `_REQUIRES_MAP_FROZEN`:
   `"STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",`.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan103_pipeline_monitor_flag.py`, 5 casos (espejo de
`test_plan87_devops_flag.py`):

1. `test_flag_registered_bool` — existe `FlagSpec` con
   `key == "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED"`, `type == "bool"`, `env_only is False`.
2. `test_flag_categorized_devops` — la key está en `_CATEGORY_KEYS["devops"]`.
3. `test_flag_requires_panel` — `spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
4. `test_default_off_effective` — con env limpio, recargar `config` ⇒
   `config.STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED is False`.
5. `test_health_exposes_pipeline_monitor_enabled_false_by_default` —
   `GET /api/devops/health` responde 200 con `"pipeline_monitor_enabled": False`.

**Comandos (venv real del repo — es `.venv`, no `venv`):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan103_pipeline_monitor_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" "Stacky Agents/backend/tests/test_harness_flags_requires.py" "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
```

**Criterio de aceptación (binario):** 5 tests nuevos verdes + los 3 meta-tests del arnés
verdes.
**Flag:** `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED`, default OFF.
**Impacto por runtime:** NINGUNO (flag de UI/panel; ningún runner la lee). Fallback: N/A.
**Trabajo del operador:** ninguno (opt-in default off).

---

## F1 — Módulo puro `pipelineMonitor.ts` (backoff + estado legible + store persistente)

**Objetivo:** concentrar en un módulo TS puro el backoff, la detección de estado terminal,
el formateo legible y el store persistente del último pipeline, para que el hook (F2) y el
badge (F3) queden triviales y todo lo testeable viva acá.
**Valor:** tests deterministas sin timers reales ni render.

**Archivo a crear (exacto):** `Stacky Agents/frontend/src/devops/pipelineMonitor.ts`

**Símbolos exactos:**

```typescript
import { create } from 'zustand';
import type { CIMonitorResponse } from '../api/endpoints';

// Backoff progresivo: 3s, 5s, 10s, 30s (tope). attempt 0 → 3s.
export const BACKOFF_STEPS_MS: readonly number[] = [3000, 5000, 10000, 30000];
export function computeBackoffMs(attempt: number): number {
  const i = Math.min(Math.max(attempt, 0), BACKOFF_STEPS_MS.length - 1);
  return BACKOFF_STEPS_MS[i];
}

const TERMINAL = new Set(['success', 'failed', 'canceled']);
export function isTerminalStatus(status: string): boolean {
  return TERMINAL.has((status ?? '').toLowerCase());
}

export type MonitorTone = 'running' | 'success' | 'failed' | 'unknown';
export interface MonitorView {
  label: string;       // texto legible ("Pipeline OK", "Falló", "Corriendo"...)
  tone: MonitorTone;
  ref: string;
  webUrl: string;
  tracker: string;
}
export function toneForStatus(status: string): MonitorTone {
  const s = (status ?? '').toLowerCase();
  if (s === 'success') return 'success';
  if (s === 'failed' || s === 'canceled') return 'failed';
  if (['running', 'pending', 'created', 'preparing', 'waiting_for_resource', 'scheduled'].includes(s)) return 'running';
  return 'unknown';
}
export function formatMonitorStatus(res: CIMonitorResponse): MonitorView {
  const tone = toneForStatus(res.status);
  const label =
    tone === 'success' ? 'Pipeline OK'
    : tone === 'failed' ? `Pipeline ${res.status}`
    : tone === 'running' ? `Corriendo (${res.status})`
    : `Estado: ${res.status}`;
  return { label, tone, ref: res.ref, webUrl: res.web_url, tracker: res.tracker_type };
}

// ── Store persistente del último pipeline (localStorage, patrón selectedServer) ──
const STORAGE_KEY = 'stacky.devops.lastPipeline';

export interface MonitoredPipeline {
  project: string;
  pipelineId: string;
  ref: string;
  status: string;   // último status conocido
  webUrl: string;
  tracker: string;
  startedAt: number; // Date.now() al registrar
  attempt: number;   // nº de poll (para el backoff)
}

export function loadPersistedPipeline(): MonitoredPipeline | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as MonitoredPipeline) : null;
  } catch {
    return null;
  }
}
function persist(p: MonitoredPipeline | null): void {
  try {
    if (p) localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
    else localStorage.removeItem(STORAGE_KEY);
  } catch { /* storage lleno/denegado: el badge sigue en memoria */ }
}

interface DevopsMonitorState {
  last: MonitoredPipeline | null;
  setLast: (p: MonitoredPipeline) => void;
  applyStatus: (status: string, webUrl?: string) => void; // update de status + bump attempt
  clear: () => void;
}
export const useDevopsMonitorStore = create<DevopsMonitorState>((set) => ({
  last: loadPersistedPipeline(),
  setLast: (p) => { persist(p); set({ last: p }); },
  applyStatus: (status, webUrl) => set((s) => {
    if (!s.last) return s;
    const next: MonitoredPipeline = {
      ...s.last,
      status,
      webUrl: webUrl ?? s.last.webUrl,
      attempt: s.last.attempt + 1,
    };
    persist(next);
    return { last: next };
  }),
  clear: () => { persist(null); set({ last: null }); },
}));
```

**Casos borde cubiertos:** `attempt` negativo o mayor al tope ⇒ `computeBackoffMs` clampa;
status con mayúsculas/espacios ⇒ `isTerminalStatus`/`toneForStatus` normalizan;
`localStorage` inaccesible ⇒ `load` devuelve null y `persist` no rompe; status desconocido
⇒ tono `unknown` (no `running`, para no mentir "corriendo").

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/devops/pipelineMonitor.test.ts`, 10 casos:

1. `computeBackoffMs 0→3000, 1→5000, 2→10000, 3→30000`.
2. `computeBackoffMs clampa` — `computeBackoffMs(9) === 30000`, `computeBackoffMs(-1) === 3000`.
3. `isTerminalStatus true` para `success`/`failed`/`canceled` (y `SUCCESS` mayúscula).
4. `isTerminalStatus false` para `running`/`pending`/`''`.
5. `toneForStatus` mapea success→success, failed/canceled→failed, running/pending→running,
   raro→unknown.
6. `formatMonitorStatus` arma `label`/`tone`/`ref`/`webUrl`/`tracker` desde un
   `CIMonitorResponse` fixture.
7. `setLast persiste` — tras `setLast(p)`, `localStorage.getItem(STORAGE_KEY)` parsea a `p`
   (usar un mock/polyfill de `localStorage` en el test).
8. `applyStatus actualiza status y bumpea attempt` — de `attempt:0` a `attempt:1`, status
   nuevo; persistido.
9. `applyStatus sin last es no-op`.
10. `clear borra memoria y storage` — `last === null` y `localStorage.getItem` null.

**Comando:**

```
cd "Stacky Agents/frontend" && npx vitest run src/devops/pipelineMonitor.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** 10 tests verdes + `tsc --noEmit` 0 errores.
**Flag:** consumido aguas arriba (F2/F3); el módulo es librería pura.
**Impacto por runtime:** NINGUNO (TS puro). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F2 — Hook `useDevopsPipelineMonitor` (poller con backoff, vive en el shell)

**Objetivo:** un hook que, si la flag está ON y hay un pipeline no-terminal en el store,
sondea con backoff y actualiza el store hasta el estado terminal; corre en el shell para
sobrevivir al cambio de sub-sección.
**Valor:** un único poller persistente que reduce requests y no muere al navegar.

**Archivo a crear (exacto):**
`Stacky Agents/frontend/src/components/devops/useDevopsPipelineMonitor.ts`

**Símbolo exacto y pseudocódigo:**

```typescript
import { useEffect } from 'react';
import { CIPipeline } from '../../api/endpoints';
import { useDevopsMonitorStore, computeBackoffMs, isTerminalStatus } from '../../devops/pipelineMonitor';

// enabled = ctx.health.pipeline_monitor_enabled === true (lo pasa el shell)
export function useDevopsPipelineMonitor(enabled: boolean): void {
  const last = useDevopsMonitorStore((s) => s.last);
  const applyStatus = useDevopsMonitorStore((s) => s.applyStatus);

  useEffect(() => {
    if (!enabled || !last || isTerminalStatus(last.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const res = await CIPipeline.monitor(last.project, last.pipelineId);
        if (cancelled) return;
        applyStatus(res.status, res.web_url); // bumpea attempt y persiste
        // el re-render por el store re-dispara este effect con el nuevo attempt/status;
        // si el nuevo status es terminal, el guard de arriba corta el próximo ciclo.
      } catch {
        // corte silencioso: el badge conserva el último estado conocido; reintenta al
        // próximo ciclo del effect (no rompe la UI).
      }
    };

    timer = setTimeout(() => { void tick(); }, computeBackoffMs(last.attempt));
    return () => { cancelled = true; clearTimeout(timer); };
  }, [enabled, last?.project, last?.pipelineId, last?.status, last?.attempt, applyStatus]);
}
```

**Casos borde:** flag OFF ⇒ el effect retorna sin agendar timer (cero polling); pipeline ya
terminal en el store (p. ej. restaurado de `localStorage` tras recarga) ⇒ no se sondea;
error de red ⇒ no rompe, reintenta; desmontaje del shell ⇒ `clearTimeout` (sin fugas).

**Tests PRIMERO (TDD)** — la lógica pura (backoff, terminal) ya está cubierta en F1. Este
hook es delgado; se testea su CONDICIÓN de arranque con una función auxiliar pura que se
agrega a `pipelineMonitor.ts` y se testea en `pipelineMonitor.test.ts` (2 casos nuevos):

```typescript
// en pipelineMonitor.ts
export function shouldPoll(enabled: boolean, last: MonitoredPipeline | null): boolean {
  return enabled && last !== null && !isTerminalStatus(last.status);
}
```

11. `shouldPoll` true solo con `enabled && last && !terminal`.
12. `shouldPoll` false si `enabled` false, o `last` null, o `last.status` terminal.

**Comando:**

```
cd "Stacky Agents/frontend" && npx vitest run src/devops/pipelineMonitor.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** 12 tests verdes (10 de F1 + 2 de `shouldPoll`) +
`tsc` 0 errores + el hook usa `shouldPoll`/`computeBackoffMs` y compila.
**Flag:** `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` (vía `enabled`).
**Impacto por runtime:** NINGUNO (hook React). Fallback: si la flag está OFF, el hook no
sondea (cero cambios).
**Trabajo del operador:** ninguno.

---

## F3 — Badge en el shell + registro en el store + estado legible en la sección

**Objetivo:** renderizar el badge persistente en el shell (solo flag ON + hay pipeline),
registrar el pipeline en el store al dispararlo, y reemplazar el JSON crudo por el estado
legible cuando la flag está ON.
**Valor:** el KPI end-to-end (persistencia + legibilidad + visibilidad cross-sección).

**Archivos a crear/editar (exactos):**

1. **Crear** `Stacky Agents/frontend/src/components/devops/LastPipelineBadge.tsx`:

```tsx
import React from 'react';
import { useDevopsMonitorStore, toneForStatus, type MonitorTone } from '../../devops/pipelineMonitor';
import styles from './devops.module.css';

const TONE_CLASS: Record<MonitorTone, string> = {
  running: styles.alertWarning,
  success: styles.alertSuccess,
  failed: styles.alertError,
  unknown: styles.alertInfo,
};

export const LastPipelineBadge: React.FC = () => {
  const last = useDevopsMonitorStore((s) => s.last);
  const clear = useDevopsMonitorStore((s) => s.clear);
  if (!last) return null;
  const tone = toneForStatus(last.status);
  return (
    <div className={TONE_CLASS[tone]} style={{ marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
      <span><strong>Último pipeline</strong> ({last.ref}): {last.status}</span>
      {last.webUrl && <a href={last.webUrl} target="_blank" rel="noreferrer">ver</a>}
      <button onClick={() => clear()} title="Descartar" style={{ marginLeft: 'auto' }}>×</button>
    </div>
  );
};
```

2. **Editar** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx`:
   - Imports: `import { useDevopsPipelineMonitor } from '../components/devops/useDevopsPipelineMonitor';`
     y `import { LastPipelineBadge } from '../components/devops/LastPipelineBadge';`.
   - Dentro de `DevOpsPage`, tras construir `ctx` (`:142-147`):
     `useDevopsPipelineMonitor(ctx.health.pipeline_monitor_enabled === true);`
   - En el JSX, antes de la barra de sub-tabs (`:171`):
     `{ctx.health.pipeline_monitor_enabled === true && <LastPipelineBadge />}`
   - En la interfaz `DevOpsHealth` (`:22-32`), agregar
     `pipeline_monitor_enabled?: boolean; // Plan 103`.

3. **Editar** `Stacky Agents/frontend/src/components/devops/TriggerPipelineSection.tsx`:
   - Agregar prop OPCIONAL: `monitorEnabled?: boolean;` en `TriggerPipelineSectionProps`
     (default undefined ⇒ false ⇒ comportamiento actual).
   - En `handleTrigger`, tras `setPipelineId(result.pipeline_id)` (`:71`), si
     `monitorEnabled`: registrar en el store en vez de arrancar el poller local:

```tsx
      if (result.pipeline_id) {
        setPipelineId(result.pipeline_id);
        if (monitorEnabled) {
          useDevopsMonitorStore.getState().setLast({
            project, pipelineId: result.pipeline_id, ref,
            status: result.status, webUrl: result.web_url ?? '',
            tracker: '', startedAt: Date.now(), attempt: 0,
          });
        } else {
          setPolling(true); // camino actual
        }
      }
```

   - En el `useEffect` de polling (`:97-104`), condicionar el arranque a `!monitorEnabled`
     (con la flag ON, el shell es el único poller — evita doble polling, §3.9):
     `if (polling && pipelineId && !monitorEnabled) { ... }`.
   - En el bloque de monitoreo (`:160-167`), cuando `monitorEnabled` y hay estado en el
     store, mostrar el estado legible (reusar `formatMonitorStatus` del store) en vez del
     `JSON.stringify`; cuando OFF, dejar el `<pre>` actual intacto.
   - `import { useDevopsMonitorStore, formatMonitorStatus } from '../../devops/pipelineMonitor';`

4. **Editar** el punto donde `PublicationsSection` renderiza `<TriggerPipelineSection ...>`
   (importado en `PublicationsSection.tsx:29`): pasarle
   `monitorEnabled={ctx.health.pipeline_monitor_enabled === true}` (la sección ya recibe
   `ctx`). Cambio aditivo de 1 prop.

**Tests PRIMERO (TDD)** — extender
`Stacky Agents/frontend/src/pages/__tests__/DevOpsPage.test.ts` con 3 casos (TS-puro,
sobre las funciones/estado del store, sin render):

13. `badge oculto sin pipeline` — con `useDevopsMonitorStore` en `last:null`, la condición
    de render (`last !== null`) es false.
14. `setLast alimenta el badge y toneForStatus da el color` — tras `setLast(fixtureRunning)`,
    `store.last.ref` correcto y `toneForStatus(store.last.status) === 'running'`.
15. `clear apaga el badge` — tras `clear()`, `last === null`.

(La visibilidad por flag —`pipeline_monitor_enabled === true`— se testea con la función
`shouldPoll`/lectura del health en F2; el render condicional del shell es una guarda de una
línea sin lógica testeable extra.)

**Comando:**

```
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/DevOpsPage.test.ts src/devops/pipelineMonitor.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** 3 tests nuevos verdes + F1/F2 verdes + `tsc` 0
errores + los vitest preexistentes del panel (`PipelineBuilderSection.test.ts`,
`ServersSection.test.ts`) verdes sin modificarse.
**Flag:** `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` vía health (OFF ⇒ badge ausente,
sección con polling 3s + JSON como hoy).
**Impacto por runtime:** NINGUNO (UI). Fallback: con la flag OFF, byte-idéntico al actual.
**Trabajo del operador:** ninguno (opt-in default off).

---

## F4 — Cierre: ratchet, verificación manual HITL y checklist binario

**Objetivo:** registrar el test backend en el ratchet y confirmar en la app real la
persistencia, el backoff y la legibilidad.
**Valor:** evidencia de que los KPI se cumplen end-to-end.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar
   `test_plan103_pipeline_monitor_flag.py` a `HARNESS_TEST_FILES`.
2. `Stacky Agents/backend/scripts/run_harness_tests.ps1` — misma alta en la lista `.ps1`
   (ratchet Plan 49; ambos deben listar el archivo o el meta-test de cobertura falla).

**Verificación manual (HITL; el implementador la corre una vez, nada se automatiza que
saque al operador del lazo):**

1. Flag OFF (default): abrir Trigger CI, disparar → polling 3s + JSON como hoy; sin badge
   en el shell. **Binario:** comportamiento idéntico al actual.
2. Activar `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` (Configuración → Arnés) → disparar un
   pipeline. **Binario:** aparece el badge "Último pipeline (ref): running" en el shell.
3. Cambiar a otra sub-sección (Pipelines/Servidores) → el badge sigue visible. **Binario:**
   el badge persiste cross-sección.
4. Recargar la página con el pipeline aún corriendo → el badge se restaura y el polling se
   reanuda. **Binario:** badge presente tras F5/reload; en Network, las consultas se
   espacian (3s→5s→10s→30s), no un fijo de 3s.
5. Esperar al final → el badge cambia a verde ("Pipeline OK") o rojo ("Pipeline failed")
   aunque el operador esté en otra sección. **Binario:** color/tono correcto al terminar;
   el polling se detiene (sin más requests en Network).
6. Click en "×" → el badge desaparece y no reaparece al recargar. **Binario:**
   `localStorage['stacky.devops.lastPipeline']` ausente.

**Comando de regresión (no-romper):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan103_pipeline_monitor_flag.py" -q
cd "Stacky Agents/frontend" && npx vitest run src/devops/pipelineMonitor.test.ts src/pages/__tests__/DevOpsPage.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 6 pasos manuales cumplen + regresión verde +
test backend en ambos ratchets.
**Flag:** `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED`, default OFF.
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno (opt-in default off).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Doble polling (sección local + shell) con la flag ON | §3.9: con `monitorEnabled`, la sección NO arranca su `setInterval` (guard `!monitorEnabled` en el effect); un único poller en el shell. Test 6 de F1 + verificación manual paso 4 (Network). |
| El badge quede "pegado" en un estado no-terminal (pipeline borrado en el server) | El poller reintenta; si el server devuelve error persistente, el badge conserva el último estado y el operador puede descartarlo con "×" (`clear`). No hay bloqueo. |
| `localStorage` lleno o deshabilitado (modo privado) | `loadPersistedPipeline`/`persist` envueltos en `try/catch`: el badge funciona en memoria durante la sesión; no rompe. |
| El estado terminal restaurado de `localStorage` re-dispare polling tras recargar | El guard `isTerminalStatus(last.status)` en el hook (F2) evita sondear pipelines ya terminados; solo se reanuda para no-terminales. |
| Colisión con el Plan 102 (que también registra el pipeline disparado) | Ambos usan el MISMO store (`useDevopsMonitorStore.setLast`); si el 102 se implementa, su modal llama `setLast` al terminar la cadena y el badge lo toma sin cambios. Punto de integración declarado, no un conflicto. |
| `tracker` vacío al registrar desde el trigger (`CITriggerResponse` no trae `tracker_type`) | Se registra `tracker:''` al disparar y el primer `applyStatus` NO lo actualiza (el monitor sí trae `tracker_type` pero el store solo guarda status/webUrl). El badge no depende del tracker para funcionar; es informativo. Si se quiere, el implementador puede extender `applyStatus` para tomar `tracker_type` — declarado como mejora menor, no requerida. |

## 6. Fuera de scope (v1)

- **Notificación de escritorio al terminar.** Ya existe `STACKY_DESKTOP_NOTIFY_ENABLED`
  (categoría observabilidad); integrar el badge con notificaciones nativas es un enganche
  futuro, no parte de v1 (el aviso v1 es el cambio de color del badge).
- **Historial de pipelines.** El badge sigue UN pipeline (el último). Una lista de los N
  últimos es otro plan.
- **Monitoreo de múltiples pipelines simultáneos.** v1 sigue el último disparado
  (mono-operador, un pipeline a la vez es el caso real).
- **Cancelar/re-disparar desde el badge.** Solo lectura + descartar; cualquier acción
  mutante sobre el pipeline queda en Trigger CI (HITL explícito).
- **Persistir el estado server-side (DB/client-profile).** v1 usa `localStorage` del
  navegador; no toca la DB.
- **Reemplazar el poller local de la sección cuando la flag está OFF.** Con OFF todo queda
  como hoy; no se refactoriza el camino viejo.

## 7. Glosario

- **Badge del último pipeline:** indicador en el shell del panel DevOps que muestra el
  estado del pipeline más recientemente disparado, persistente entre sub-secciones y
  recargas.
- **Backoff progresivo:** aumentar el intervalo entre consultas (3s→5s→10s→30s) para no
  saturar el server con un pipeline largo.
- **Estado terminal:** `success`/`failed`/`canceled` — el pipeline terminó y el polling se
  detiene.
- **`CIMonitorResponse`:** respuesta del GET `monitor` (`status`, `ref`, `web_url`,
  `tracker_type`, `source`).
- **Store persistente:** store zustand cuyo estado se guarda en `localStorage` (patrón ya
  usado en el shell para `selectedServer`).
- **Poller:** el `setTimeout`/`setInterval` que consulta el estado del pipeline; con la
  flag ON, único y en el shell.
- **Tono (`MonitorTone`):** `running`/`success`/`failed`/`unknown`, mapeado a un color del
  badge.

## 8. Orden de implementación

1. **F0** — flag 5 patas + health key + arista R4 + 5 tests backend. Verde antes de seguir.
2. **F1** — `pipelineMonitor.ts` (backoff + terminal + format + store) + 10 tests.
3. **F2** — `useDevopsPipelineMonitor.ts` + `shouldPoll` + 2 tests (necesita F1).
4. **F3** — `LastPipelineBadge.tsx` + edición de `DevOpsPage`/`TriggerPipelineSection`/
   `PublicationsSection` + 3 tests (necesita F1/F2).
5. **F4** — ratchet (sh+ps1) + verificación manual HITL (6 pasos) + regresión.

## 9. Definición de Hecho (DoD) global

- [ ] `test_plan103_pipeline_monitor_flag.py` verde (5 casos) + 3 meta-tests del arnés
      verdes; flag visible en Configuración → Arnés (categoría DevOps), default OFF.
- [ ] `pipelineMonitor.test.ts` verde (12 casos) y `DevOpsPage.test.ts` verde (3 casos
      nuevos); `npx tsc --noEmit` 0 errores.
- [ ] Con flag ON: el badge aparece al disparar, persiste al cambiar de sub-sección y al
      recargar, muestra estado legible + link, y cambia de color al terminar.
- [ ] Con flag ON: el polling usa backoff (3s→5s→10s→30s), verificado en Network (−82%
      requests vs el fijo de 3s); un único poller (sin doble polling).
- [ ] Con flag OFF: comportamiento byte-idéntico al actual (polling 3s local + JSON en la
      sección; sin badge; store sin alimentar).
- [ ] Solo lectura: ningún endpoint de escritura nuevo; el monitor no dispara/cancela/
      reintenta pipelines; botón "×" descarta el badge (HITL).
- [ ] Backward-compatible: `TriggerPipelineSection` gana una prop OPCIONAL; sin ella,
      comportamiento actual. Cero dependencias nuevas.
- [ ] Test backend registrado en ambos ratchets (`run_harness_tests.sh` y `.ps1`).
- [ ] Impacto runtime NINGUNO (verificable por grep: `pipelineMonitor`/`LastPipelineBadge`/
      `useDevopsPipelineMonitor` no aparecen fuera de `frontend/`).
- [ ] Trabajo del operador: ninguno (opt-in default off).
