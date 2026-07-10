# Plan 119 — Rediseño visual minimalista y profesional del dashboard DevOps

> **Estado:** PROPUESTO v1 — 2026-07-10
> **Autor:** StackyArchitectaUltraEficientCode
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Serie:** pulido profesional del dashboard DevOps. COMPLEMENTA al plan 116 (que ya proponía
> "pulido profesional del panel DevOps": facelift del `FlagGateBanner`, estado vacío en Servidores,
> accesibilidad de la barra de sub-tabs). Este plan lleva ese pulido a su conclusión natural:
> **reemplaza el shell inline por un shell que usa el design system** (tokens `theme.css`), sin tocar
> comportamiento. NO duplica 116 (que agrega el *doctor de conexiones* determinista): 119 es
> **100% presentación**.
> **Depende de:** nada pendiente. Usa sustrato YA implementado: plan 87 (shell DevOps + `/api/devops/health`),
> plan 91 (registro de servidores + selector), flags del arnés (planes 33/63/82/86), y los tokens de
> `theme.css`. La dependencia `lucide-react` **ya está en `frontend/package.json:15`** (no se agrega nada).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El panel DevOps (`frontend/src/pages/DevOpsPage.tsx`) es hoy el **único** módulo
del app que abandona el design system: su shell está construido con **estilos inline crudos** y colores
Bootstrap hardcodeados (`<div style={{padding:'20px'…}}>` en la línea 210, botones de sub-tab con
`backgroundColor: activeId===s.id ? '#007bff' : '#6c757d'` y `borderRadius:'4px'` en las líneas 214-233,
y un `<select style={{ marginLeft:'auto' }}>` suelto a la derecha en las líneas 235-247). Esto choca visualmente
con el resto de la aplicación, que ya usa los tokens oscuros de `theme.css` y el patrón de tabs *underline*
de `App.module.css`. Este plan **reemplaza ese shell por uno minimalista y profesional** (estética
near-monochrome tipo Linear/Vercel/Tailscale): header con título + subtítulo + una línea de *situational
awareness* + selector de "Servidor activo" **promovido**; sub-tabs *underline*; y la sección de Servidores
migrada de grilla de cards a **tabla** con íconos de línea. **Todo es puro cambio de presentación**: el
registro `DEVOPS_SECTIONS`, el montaje persistente C10, el gate declarativo vía `FlagGateBanner`, el estado
de selección de servidor y toda la lógica de `ServersSection` quedan **intactos**. El shell nuevo va detrás
de una flag del arnés **default OFF** (`STACKY_DEVOPS_UI_V2_ENABLED`): con la flag apagada la UI es
**byte-idéntica** a hoy (rollback y A/B triviales).

**KPI / impacto esperado (todos binarios y verificables).**
- **0 estilos inline en el shell v2 (binario):** con la flag ON, `DevOpsPage.tsx` no renderiza ningún atributo
  `style={{…}}` en el shell nuevo (header/tabs/picker); todo el estilo sale de `DevOpsPage.module.css` +
  tokens `theme.css`. (El outlet C10 y el path v1 conservan su `style` inline — intocables.)
- **100% tokens theme.css (binario):** el CSS nuevo (`DevOpsPage.module.css`, `ServersTable.module.css`) usa
  **solo** `var(--…)` de `theme.css`; **cero** hex de color nuevos (grep del diff sobre `#[0-9a-fA-F]{3,6}`
  en los `.module.css` nuevos ⇒ solo `#fff` permitido para texto sobre `--accent`, ver F1).
- **Paridad visual con el resto del app (binario):** las sub-tabs v2 replican el patrón *underline* de
  `App.module.css` (`.nav`/`.navTab`, líneas 7-39) usando `--accent` como color de 2º nivel.
- **Regresión 0 con flag OFF (binario):** con `STACKY_DEVOPS_UI_V2_ENABLED` OFF, el payload de
  `GET /api/devops/health` gana solo un campo aditivo (`ui_v2_enabled: false`), `DevOpsPage` renderiza
  exactamente lo de hoy, y todas las suites vitest + `tsc --noEmit` quedan verdes.
- **Contrato §3.12 C20 preservado (binario):** "sumar una sección futura = 1 entrada en `DEVOPS_SECTIONS`
  + 1 componente, CERO cambios en `DevOpsPage`" sigue siendo cierto tras el rediseño (el outlet y las tabs
  iteran `DEVOPS_SECTIONS` sin cambios de contrato).

---

## 2. Por qué ahora / gap que cierra

1. **El shell DevOps es el último rincón fuera del design system.** El resto del app ya migró a los tokens
   oscuros de `theme.css` y al patrón de tabs *underline* de `App.module.css:7-39`. El panel DevOps quedó
   con estilos inline y colores Bootstrap (`#007bff`, `#6c757d`) que en tema oscuro se ven "de juguete".
2. **La serie DevOps 87-116 construyó mucha superficie sin pulir el marco.** Se agregaron 15+ secciones
   (`DEVOPS_SECTIONS`, `DevOpsPage.tsx:80-152`), servidores (plan 91), consola remota (105), agente (90),
   revisor de PRs (110)… pero el *chrome* (header, tabs, selector) nunca se profesionalizó. El plan 116 ya
   detectó esta deuda ("pulido profesional del panel DevOps") pero la acotó a componentes puntuales; 119 la
   cierra en el shell.
3. **Ya existe todo lo necesario, no hay que inventar paleta.** Tokens en `theme.css`, patrón de tabs en
   `App.module.css`, patrones profesionales probados en `HarnessFlagsPanel.module.css` (`.groupTitle`,
   toggles, chips) y `PrReviewerSection.module.css` (`.privacy`, el callout de datos sensibles), y clases
   semánticas compartidas en `components/devops/devops.module.css`. `lucide-react` ya está instalado.
4. **Riesgo cero por diseño:** es 100% frontend, ortogonal al runtime, detrás de una flag default OFF. Con la
   flag apagada nada cambia; con ella prendida, el operador estrena un panel a la altura del resto del app.

---

## 3. Principios y guardarraíles (no negociables)

- **Cambio SOLO de presentación.** CERO cambios de comportamiento, contratos, endpoints, datos o API.
  Se conservan **intactos** (verificado por tests de no-regresión, F5):
  - el registro `DEVOPS_SECTIONS` (`DevOpsPage.tsx:80-152`) y su contrato `id/label/icon?/healthKey?/gateFlagKey?/gateMessage?/render(ctx)`;
  - el montaje persistente **C10** (`mountedIds`, `DevOpsPage.tsx:163, 192-195`): las secciones no se desmontan (`display:none`);
  - el **outlet + gate declarativo** (`DevOpsPage.tsx:250-276`): `isGated = s.healthKey && ctx.health[s.healthKey] !== true` → `<FlagGateBanner/>`;
  - el estado de selección de servidor (`selectedAlias`/`onSelectServer`/`localStorage 'stacky.devops.selectedServer'`, `DevOpsPage.tsx:172-179`);
  - toda la lógica de `ServersSection` (CRUD, test de conectividad `testResults`, RDP, password **write-only**).
- **Flag opt-in default OFF.** El shell v2 se protege con `STACKY_DEVOPS_UI_V2_ENABLED` (categoría `devops`,
  default OFF). Flag OFF ⇒ shell v1 (inline) intacto; flag ON ⇒ shell v2 (`.module.css`). Gotchas obligatorios
  (heredados de planes 63/104): la `FlagSpec` nueva va **SIN `default=`** (solo `_CURATED_DEFAULTS_ON` puede
  declarar default; ponerlo rompe `test_default_known_only_for_curated`); el default **efectivo** vive en
  `config.py` (fallback `"false"`); `requires` con **profundidad 1** apuntando al master del panel
  (`STACKY_DEVOPS_PANEL_ENABLED`, **no** a una flag hija), y esa arista se registra en `_REQUIRES_MAP_FROZEN`
  (`backend/tests/test_harness_flags_requires.py`).
- **3 runtimes con paridad total.** Es un cambio **100% frontend**, **ortogonal** al runtime. Codex CLI,
  Claude Code CLI y GitHub Copilot Pro se comportan **idéntico** (ninguna lógica se ata al runtime). Fallback
  universal: flag OFF ⇒ UI actual; deploy viejo sin la key en health ⇒ `ui_v2_enabled` ausente ⇒ tratado como
  `false` ⇒ shell v1 (comportamiento correcto).
- **Cero trabajo extra al operador.** Opt-in, default OFF, backward-compatible. Sin pasos manuales nuevos.
  La flag se activa desde el panel Arnés existente (`HarnessFlagsPanel`, plan 33/86) — la vía estándar.
- **Human-in-the-loop / mono-operador sin auth.** No se toca. No se introduce RBAC ni multiusuario.
- **No degradar performance/seguridad/estabilidad/DX.** Se reusan `theme.css` y `devops.module.css`; no se
  reinventa paleta; no se agregan dependencias (lucide ya está). Accesibilidad: foco visible por teclado
  (`:focus-visible`), `prefers-reduced-motion` respetado, contraste AA, `aria-current` en la tab activa,
  labels en los controles.
- **Datos personales / sensibles (obligación de reporte de riesgo).** La sección de Servidores muestra
  **usuarios** (p. ej. `PACIFICO\deploy`) y **hosts/IPs** — datos infra-sensibles — y gestiona **credenciales**.
  La migración a tabla los hace más visibles ⇒ ver Riesgo R5 y el callout de F4. El cambio es
  **solo de presentación**: no agrega logging, ni persistencia, ni exposición nueva de esos campos.

---

## 4. Fases (F0 → F5)

> **Anclajes de tokens (usar EXACTAMENTE estos `var(--…)` de `theme.css`, no inventar colores):**
> superficies `--bg-base #0d1117` / `--bg-panel #161b22` / `--bg-elev #21262d`; bordes `--border #30363d` /
> `--border-muted #21262d`; texto `--text-primary #e6edf3` / `--text-muted #8b949e` / `--text-faint #6e7681`;
> acento `--accent #388bfd` / `--accent-hot #58a6ff`; estado `--success #3fb950` / `--warn #d29922` /
> `--danger #f85149`; tipografía `--font-sans` (Inter) / `--font-mono` (JetBrains Mono); radios
> `--radius 6px` / `--radius-sm 4px`.
> **Referencia visual completa** (CSS 1:1 con tokens, ya iterada y validada con el operador):
> `C:\Users\juanluca\AppData\Local\Temp\claude\N--GIT-RS-STACKY-Stacky\92c9ab6c-2d7c-4a40-8a9b-d7c192aa532e\scratchpad\devops-console-redesign.html`.

---

### F0 — Flag del arnés + tipos + CSS module + helpers puros (sin cambio visual)

**Objetivo (1 frase).** Plumbear la flag `STACKY_DEVOPS_UI_V2_ENABLED` end-to-end (backend → health → tipos
frontend), crear el CSS module del shell y los **helpers puros** con sus tests, **sin tocar todavía el JSX**
(OFF y ON renderizan idéntico a hoy). **Valor:** deja la infraestructura y la lógica testeada lista para que
F1-F4 solo conecten presentación.

**Archivos EXACTOS a editar/crear:**

1. `backend/config.py` — agregar el default **efectivo** (OFF) tras el bloque del Plan 110 (después de la
   línea 98). Diff ilustrativo:
   ```python
   # ── Plan 119 — Rediseño minimalista del shell DevOps (default OFF) ──
   STACKY_DEVOPS_UI_V2_ENABLED = os.getenv("STACKY_DEVOPS_UI_V2_ENABLED", "false").lower() in (
       "1", "true", "yes", "on"
   )
   ```

2. `backend/services/harness_flags.py` — dos ediciones:
   - **(a)** agregar la key a la tupla de la categoría `"devops"` (que hoy va de la línea 184 a la 206),
     inmediatamente después de `"STACKY_PR_REVIEW_TIMEOUT_SEC",` (línea 205), **antes** del `),` de cierre
     (línea 206). Esto satisface `test_every_registry_flag_is_categorized`:
     ```python
         "STACKY_DEVOPS_UI_V2_ENABLED",  # Plan 119 — rediseño minimalista del shell DevOps
     ```
   - **(b)** agregar una `FlagSpec` (junto a las FlagSpec DevOps; p. ej. tras el bloque del Plan 110 que
     termina en la línea 2564). **SIN `default=`** (gotcha Plan 63) y con `requires` de profundidad 1 al
     master del panel:
     ```python
     # ── Plan 119 — Rediseño minimalista del shell DevOps ──────────────────────
     FlagSpec(
         key="STACKY_DEVOPS_UI_V2_ENABLED",
         type="bool",
         label="Shell DevOps minimalista (Plan 119)",
         description=(
             "Plan 119 — Reemplaza el shell del panel DevOps (header, sub-tabs y "
             "selector de servidor) por un diseño minimalista que usa los tokens de "
             "theme.css, y la sección Servidores por una tabla. Solo presentación: "
             "cero cambios de comportamiento. Default OFF: con la flag apagada la UI "
             "es idéntica a la actual."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # profundidad 1 (master del panel, no una flag hija)
         # SIN default= (solo _CURATED_DEFAULTS_ON puede; default OFF vive en config.py).
     ),
     ```

3. `backend/services/harness_flags_help.py` — agregar una entrada `PlainHelp` para la key, replicando el
   patrón de `"STACKY_PR_REVIEWER_ENABLED"` (línea 1166). Diff ilustrativo:
   ```python
   "STACKY_DEVOPS_UI_V2_ENABLED": PlainHelp(
       what="Enciende el rediseño minimalista del panel DevOps (header, tabs, servidores).",
       why="Alinea el panel DevOps con el resto del app (tokens theme.css). Solo apariencia.",
       default_hint="OFF — con la flag apagada la UI es idéntica a la actual.",
   ),
   ```
   > Usar los MISMOS nombres de campos de `PlainHelp` que la entrada vecina de la línea 1166 (copiar su
   > forma exacta; si algún campo difiere, respetar el de esa entrada).

4. `backend/api/devops.py` — en `_health_payload()`, agregar la key al dict, inmediatamente después de
   `"pr_reviewer_enabled": …` (línea 62), antes del `}` de cierre (línea 63):
   ```python
       "ui_v2_enabled": bool(getattr(cfg, "STACKY_DEVOPS_UI_V2_ENABLED", False)),  # Plan 119
   ```

5. `backend/tests/test_harness_flags_requires.py` — en `_REQUIRES_MAP_FROZEN`, agregar la arista antes del
   `}` de cierre (línea 176), replicando el patrón de la línea 171:
   ```python
       "STACKY_DEVOPS_UI_V2_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 119
   ```

6. **NO** agregar la key a `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py`, el set que termina
   en la línea 534): la flag es **OFF**. Tocarlo la promovería a ON.

7. `frontend/src/pages/DevOpsPage.tsx` — en la interface `DevOpsHealth` (líneas 22-38), agregar el campo
   aditivo opcional junto a `pr_reviewer_enabled?` (línea 36):
   ```ts
     ui_v2_enabled?: boolean; // Plan 119 — shell minimalista
   ```

8. `frontend/src/api/endpoints.ts` — en el tipo de retorno de `DevOps.health` (donde está `pr_reviewer_enabled?`,
   línea 3158), agregar:
   ```ts
     ui_v2_enabled?: boolean; // Plan 119
   ```

9. `frontend/src/pages/DevOpsPage.module.css` — **crear** el archivo con TODO el CSS del shell v2 (se aplica
   recién en F1/F2, acá solo se crea). Contenido EXACTO (traducción 1:1 del mockup a tokens):
   ```css
   .page { max-width: 1120px; margin: 0 auto; padding: 40px 40px 64px; height: 100%; display: flex; flex-direction: column; }

   /* header */
   .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 6px; }
   .title { font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; margin: 0; color: var(--text-primary); }
   .subtitle { color: var(--text-muted); font-size: 0.85rem; margin: 4px 0 0; }
   .meta { color: var(--text-faint); font-size: 0.8rem; margin: 10px 0 0; display: flex; gap: 14px; flex-wrap: wrap; align-items: center; }
   .sep { color: var(--border); }
   .mk { display: inline-flex; align-items: center; gap: 6px; }

   /* picker de servidor promovido */
   .picker { display: flex; flex-direction: column; gap: 6px; flex: 0 0 auto; }
   .pickerLabel { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--text-faint); }
   .ctl { display: flex; align-items: center; gap: 8px; padding: 7px 11px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-base); min-width: 220px; transition: border-color 0.12s; }
   .ctl:hover { border-color: var(--text-faint); }
   .ctl:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
   .select { flex: 1; background: transparent; border: none; color: var(--text-primary); font: inherit; font-family: var(--font-mono); font-size: 0.82rem; cursor: pointer; }
   .select:focus { outline: none; }

   .dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; background: var(--text-faint); }
   .dotOk { background: var(--success); }
   .dotWarn { background: var(--warn); }
   .dotBad { background: var(--danger); }

   /* sub-tabs underline (patrón App.module.css .nav/.navTab) */
   .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin: 28px 0 0; overflow-x: auto; }
   .tab { padding: 10px 14px; background: transparent; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; color: var(--text-muted); font: inherit; font-size: 0.85rem; font-weight: 500; cursor: pointer; white-space: nowrap; transition: color 0.12s, border-color 0.12s; }
   .tab:hover { color: var(--text-primary); }
   .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
   .tabActive { color: var(--text-primary); border-bottom-color: var(--accent); }
   .tabOff { color: var(--text-faint); opacity: 0.5; }  /* atenuada; SIGUE clickable (abre el banner) */
   .tabDisabled { opacity: 0.5; cursor: not-allowed; }  /* solo si el panel entero está off */

   /* cabecera de sección + botones */
   .section { margin-top: 32px; }
   .sechead { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; margin-bottom: 4px; }
   .sechead h2 { font-size: 1.05rem; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
   .actions { display: flex; gap: 14px; align-items: center; flex: 0 0 auto; }
   .secdesc { color: var(--text-muted); font-size: 0.82rem; margin: 0 0 20px; }

   .link { display: inline-flex; align-items: center; gap: 6px; background: none; border: none; padding: 0; color: var(--text-muted); font: inherit; font-size: 0.82rem; cursor: pointer; transition: color 0.12s; }
   .link:hover { color: var(--text-primary); }
   .link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
   .btn { display: inline-flex; align-items: center; gap: 7px; font: inherit; font-size: 0.82rem; cursor: pointer; padding: 6px 13px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg-base); color: var(--text-primary); transition: border-color 0.12s, background 0.12s; }
   .btn:hover { border-color: var(--text-faint); background: var(--bg-elev); }
   .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
   .btnPrimary { background: var(--accent); border-color: var(--accent); color: #fff; }  /* único acento sólido */
   .btnPrimary:hover { background: var(--accent-hot); border-color: var(--accent-hot); }

   .ico { width: 14px; height: 14px; flex: 0 0 auto; }

   /* callout de datos sensibles (patrón PrReviewerSection.module.css .privacy) */
   .note { font-size: 0.8rem; color: var(--text-muted); border-left: 2px solid color-mix(in srgb, var(--warn) 60%, transparent); padding: 2px 0 2px 12px; margin: 0 0 22px; max-width: 78ch; }
   .note strong { color: var(--text-primary); font-weight: 600; }

   @media (prefers-reduced-motion: reduce) {
     .ctl, .tab, .link, .btn { transition: none; }
   }
   ```
   > `#fff` en `.btnPrimary` es la ÚNICA excepción hex permitida (texto blanco sobre `--accent`, contraste AA).
   > Todo el resto es `var(--…)`.

10. `frontend/src/pages/devopsShell.ts` — **crear** con los helpers PUROS (sin JSX, testeables sin DOM):
    ```ts
    // Plan 119 — helpers puros del shell DevOps v2 (sin dependencia de DOM/render).
    export const CAPABILITY_KEYS = [
      'flag_enabled', 'servers_enabled', 'agent_enabled', 'rdp_available',
      'publications_enabled', 'environments_enabled', 'preflight_enabled',
      'variables_enabled', 'production_enabled', 'doctor_enabled',
    ] as const;

    export function countCapabilities(health: Record<string, unknown>): { active: number; total: number } {
      const total = CAPABILITY_KEYS.length;
      const active = CAPABILITY_KEYS.reduce((n, k) => n + (health[k] === true ? 1 : 0), 0);
      return { active, total };
    }

    export type Tone = 'ok' | 'warn' | 'faint';
    export interface AwarenessSegment { text: string; tone: Tone; }

    export function buildAwareness(
      health: Record<string, unknown>,
      selectedAlias: string | null,
    ): AwarenessSegment[] {
      const { active, total } = countCapabilities(health);
      return [
        selectedAlias
          ? { text: `${selectedAlias} activo`, tone: 'ok' }
          : { text: 'sin servidor activo', tone: 'faint' },
        health.agent_enabled === true
          ? { text: 'agente disponible', tone: 'ok' }
          : { text: 'agente en espera', tone: 'faint' },
        health.rdp_available === true
          ? { text: 'RDP listo', tone: 'ok' }
          : { text: 'RDP no disponible', tone: 'faint' },
        { text: `${active} / ${total} capacidades activas`, tone: 'faint' },
      ];
    }

    export interface TabState { active: boolean; gated: boolean; }
    // Debe coincidir EXACTAMENTE con el gate del outlet (DevOpsPage.tsx:256).
    export function classifyTab(
      section: { id: string; healthKey?: string },
      health: Record<string, unknown>,
      activeId: string,
    ): TabState {
      return {
        active: section.id === activeId,
        gated: !!section.healthKey && health[section.healthKey] !== true,
      };
    }
    ```

11. `frontend/src/pages/devopsShell.test.ts` — **crear** los tests PUROS (vitest, sin render):
    ```ts
    import { describe, it, expect } from 'vitest';
    import { countCapabilities, buildAwareness, classifyTab, CAPABILITY_KEYS } from './devopsShell';

    describe('countCapabilities', () => {
      it('cuenta solo los true de CAPABILITY_KEYS', () => {
        const h = { flag_enabled: true, servers_enabled: true, agent_enabled: false, ado_commit_supported: true };
        expect(countCapabilities(h)).toEqual({ active: 2, total: CAPABILITY_KEYS.length });
      });
      it('health vacío ⇒ 0 activas', () => {
        expect(countCapabilities({}).active).toBe(0);
      });
    });

    describe('buildAwareness', () => {
      it('sin servidor seleccionado ⇒ "sin servidor activo" tono faint', () => {
        const segs = buildAwareness({}, null);
        expect(segs[0]).toEqual({ text: 'sin servidor activo', tone: 'faint' });
      });
      it('con alias ⇒ "<alias> activo" tono ok', () => {
        expect(buildAwareness({}, 'pf-pacifico')[0]).toEqual({ text: 'pf-pacifico activo', tone: 'ok' });
      });
      it('rdp_available true ⇒ segmento "RDP listo"', () => {
        expect(buildAwareness({ rdp_available: true }, null)[2].text).toBe('RDP listo');
      });
    });

    describe('classifyTab', () => {
      it('id igual a activeId ⇒ active', () => {
        expect(classifyTab({ id: 'a' }, {}, 'a').active).toBe(true);
      });
      it('healthKey ausente ⇒ nunca gated', () => {
        expect(classifyTab({ id: 'a' }, {}, 'x').gated).toBe(false);
      });
      it('healthKey en false ⇒ gated', () => {
        expect(classifyTab({ id: 'a', healthKey: 'k' }, { k: false }, 'x').gated).toBe(true);
      });
      it('healthKey en true ⇒ no gated', () => {
        expect(classifyTab({ id: 'a', healthKey: 'k' }, { k: true }, 'x').gated).toBe(false);
      });
    });
    ```

12. `backend/tests/test_plan119_devops_ui_v2_flag.py` — **crear** el test de la flag (replicar el molde de
    `backend/tests/test_plan110_pr_review_flags.py`). Casos:
    - la key `STACKY_DEVOPS_UI_V2_ENABLED` está en `FLAG_REGISTRY`;
    - su `requires == "STACKY_DEVOPS_PANEL_ENABLED"`;
    - la key está en la categoría `"devops"` de `_CATEGORY_KEYS`;
    - default **OFF**: sin env var, `config.config.STACKY_DEVOPS_UI_V2_ENABLED is False`;
    - `_health_payload()` (importado de `api.devops`) incluye `ui_v2_enabled` y es `False` por default y
      `True` cuando se fuerza `config.config.STACKY_DEVOPS_UI_V2_ENABLED = True`.

13. `backend/scripts/run_harness_tests.sh` **y** `backend/scripts/run_harness_tests.ps1` — registrar el nuevo
    archivo de test en `HARNESS_TEST_FILES` (sh) y en `$HarnessTestFiles` (ps1). Obligatorio: si no, el
    meta-test `tests/test_harness_ratchet_meta.py` falla.

**Tests PRIMERO (TDD) + comandos exactos:**
- Backend (desde `Stacky Agents/backend`, venv real = `backend/.venv`):
  ```
  .venv\Scripts\python -m pytest tests/test_plan119_devops_ui_v2_flag.py -q
  .venv\Scripts\python -m pytest tests/test_harness_flags_requires.py -q
  .venv\Scripts\python -m pytest tests/test_harness_flags.py -q
  ```
- Frontend (desde `Stacky Agents/frontend`):
  ```
  npx vitest run src/pages/devopsShell.test.ts
  npx tsc --noEmit
  ```

**Criterio de aceptación (binario):** los 3 pytest verdes + `devopsShell.test.ts` verde + `tsc --noEmit` 0
errores. **Y** `DevOpsPage` renderiza **idéntico** a antes (aún no hay branch de JSX) — verificable porque el
diff de `DevOpsPage.tsx` en F0 solo agrega 1 línea a la interface (paso 7) y ningún cambio de render.

**Flag:** `STACKY_DEVOPS_UI_V2_ENABLED` (default **OFF**).
**Impacto por runtime:** ninguno (backend registra la flag; frontend crea artefactos no montados). Codex /
Claude Code / Copilot: idéntico. **Fallback:** N/A (sin cambio observable).
**Trabajo del operador:** ninguno (opt-in, default off).

---

### F1 — Header v2 + selector de servidor promovido (conmutado por flag)

**Objetivo (1 frase).** Reemplazar, **solo cuando la flag está ON**, el `<h2>DevOps</h2>` inline por un header
profesional (`<DevOpsHeaderV2>`) con título, subtítulo, línea de *situational awareness* y el selector de
"Servidor activo" promovido, moviendo ese selector fuera de la barra de sub-tabs. **Valor:** primer golpe
visual del rediseño; el picker deja de estar suelto a la derecha.

**Archivos EXACTOS a crear/editar:**

1. `frontend/src/pages/DevOpsHeaderV2.tsx` — **crear**. Props e implementación ilustrativa:
   ```tsx
   import { ChevronDown } from 'lucide-react';
   import styles from './DevOpsPage.module.css';
   import { buildAwareness } from './devopsShell';

   interface ServerOption { alias: string; host: string; }
   interface Props {
     health: Record<string, unknown>;
     servers: ServerOption[];
     serversEnabled: boolean;
     selectedAlias: string | null;
     onSelectServer: (alias: string | null) => void;
   }

   export function DevOpsHeaderV2({ health, servers, serversEnabled, selectedAlias, onSelectServer }: Props) {
     const segs = buildAwareness(health, selectedAlias);
     const showPicker = serversEnabled && servers.length >= 1;
     return (
       <div className={styles.head}>
         <div>
           <h1 className={styles.title}>DevOps</h1>
           <p className={styles.subtitle}>Operación de pipelines, servidores y despliegues.</p>
           <div className={styles.meta}>
             {segs.map((s, i) => (
               <span key={i} className={styles.mk}>
                 {i === 0 && (
                   <span className={`${styles.dot} ${s.tone === 'ok' ? styles.dotOk : ''}`} />
                 )}
                 {i > 0 && <span className={styles.sep} aria-hidden>·</span>}
                 {s.text}
               </span>
             ))}
           </div>
         </div>
         {showPicker && (
           <div className={styles.picker}>
             <label className={styles.pickerLabel} htmlFor="devops-server-picker">Servidor activo</label>
             <div className={styles.ctl}>
               <span className={`${styles.dot} ${selectedAlias ? styles.dotOk : ''}`} />
               <select
                 id="devops-server-picker"
                 className={styles.select}
                 value={selectedAlias ?? ''}
                 onChange={(e) => onSelectServer(e.target.value || null)}
                 aria-label="Servidor activo para las secciones que lo usen"
               >
                 <option value="">— ninguno —</option>
                 {servers.map((s) => (
                   <option key={s.alias} value={s.alias}>{s.alias} · {s.host}</option>
                 ))}
               </select>
               <ChevronDown size={14} className={styles.ico} aria-hidden />
             </div>
           </div>
         )}
       </div>
     );
   }
   ```
   > La fuente de datos del picker es **la misma** que hoy alimenta el `<select>` legacy: `ctx.servers`
   > (`DevOpsPage.tsx:243`) y la condición `ctx.health.servers_enabled === true && ctx.servers.length >= 1`
   > (`DevOpsPage.tsx:235`). No se cambia el origen de datos, solo el markup.

2. `frontend/src/pages/DevOpsPage.tsx` — 3 ediciones quirúrgicas:
   - **(a)** imports nuevos al tope:
     ```ts
     import styles from './DevOpsPage.module.css';
     import { DevOpsHeaderV2 } from './DevOpsHeaderV2';
     ```
   - **(b)** antes del `return` (después de la línea 195, junto a `handleTabClick`), calcular la flag:
     ```ts
     const uiV2 = ctx.health.ui_v2_enabled === true;
     ```
   - **(c)** en el `return` (líneas 209-248): (i) el `<div>` contenedor (línea 210) usa `.page` cuando `uiV2`;
     (ii) el `<h2>` (línea 211) se conmuta por el header v2; (iii) el `<select>` standalone (líneas 235-247)
     se rinde **solo** en v1 (`!uiV2`). Diff ilustrativo:
     ```tsx
     return (
       <div
         className={uiV2 ? styles.page : undefined}
         style={uiV2 ? undefined : { padding: '20px', height: '100%', display: 'flex', flexDirection: 'column' }}
       >
         {uiV2 ? (
           <DevOpsHeaderV2
             health={ctx.health}
             servers={ctx.servers ?? []}
             serversEnabled={ctx.health.servers_enabled === true}
             selectedAlias={selectedAlias}
             onSelectServer={onSelectServer}
           />
         ) : (
           <h2 style={{ marginTop: 0 }}>DevOps</h2>
         )}

         {/* Barra de sub-tabs — legacy por ahora (F2 la conmuta). */}
         <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
           {DEVOPS_SECTIONS.map((s) => ( /* …botones legacy sin cambios… */ ))}
           {/* selector legacy: SOLO en v1 (en v2 vive en el header) */}
           {!uiV2 && ctx.health.servers_enabled === true && (ctx.servers?.length ?? 0) >= 1 && (
             <select /* …sin cambios… */ />
           )}
         </div>

         {/* OUTLET C10 + gate — INTOCABLE (líneas 250-276) */}
         {DEVOPS_SECTIONS.map((s) => { /* …sin cambios… */ })}
       </div>
     );
     ```
   > **Único cambio al path v1:** anteponer `!uiV2 &&` a la condición del `<select>` legacy (para que no se
   > duplique con el picker del header cuando `uiV2`). Con `uiV2` OFF esa condición es idéntica a hoy.

**Tests PRIMERO (TDD):** la lógica testeable (`buildAwareness`) ya está cubierta por `devopsShell.test.ts`
(F0). Para el componente NO se escriben tests de render (el frontend **no** tiene `@testing-library/react`
ni `jsdom` — verificado en `frontend/package.json`; ver §5). La verificación de F1 es `tsc` + checklist
visual (F5).

**Comando de aceptación:**
```
cd Stacky Agents/frontend && npx tsc --noEmit && npx vitest run src/pages/devopsShell.test.ts
```
**Criterio de aceptación (binario):** `tsc --noEmit` 0 errores; `devopsShell.test.ts` verde; con la flag OFF
el header es el `<h2>` de siempre y hay exactamente 1 selector (el legacy); con la flag ON el header muestra
título/subtítulo/awareness y el picker aparece 1 sola vez (en el header), no en las tabs.

**Flag:** `STACKY_DEVOPS_UI_V2_ENABLED`. **Impacto por runtime:** ninguno (UI). Codex/Claude/Copilot idéntico.
**Fallback:** flag OFF ⇒ `<h2>` + selector legacy. **Trabajo del operador:** ninguno (opt-in, default off).

---

### F2 — Sub-tabs underline + estado gateado (conmutado por flag)

**Objetivo (1 frase).** Reemplazar, **solo cuando la flag está ON**, la barra de botones Bootstrap por sub-tabs
*underline* minimalistas (`<DevOpsTabsV2>`) que recorren `DEVOPS_SECTIONS`, con `aria-current` en la activa y
atenuación en las gateadas. **Valor:** paridad visual con el patrón de tabs del resto del app.

**Archivos EXACTOS a crear/editar:**

1. `frontend/src/pages/DevOpsTabsV2.tsx` — **crear**. Implementación ilustrativa:
   ```tsx
   import styles from './DevOpsPage.module.css';
   import { classifyTab } from './devopsShell';

   interface SectionLite { id: string; label: string; healthKey?: string; }
   interface Props {
     sections: SectionLite[];
     activeId: string;
     onSelect: (id: string) => void;
     health: Record<string, unknown>;
   }

   export function DevOpsTabsV2({ sections, activeId, onSelect, health }: Props) {
     const panelOff = health.flag_enabled !== true;  // paridad con disabled={!ctx.health.flag_enabled}
     return (
       <nav className={styles.tabs} aria-label="Secciones DevOps">
         {sections.map((s) => {
           const { active, gated } = classifyTab(s, health, activeId);
           const cls = [styles.tab, active ? styles.tabActive : '', gated ? styles.tabOff : '',
                        panelOff ? styles.tabDisabled : ''].filter(Boolean).join(' ');
           return (
             <button
               key={s.id}
               className={cls}
               onClick={() => onSelect(s.id)}   // gated SIGUE clickable (abre el FlagGateBanner en el outlet)
               disabled={panelOff}
               aria-current={active ? 'page' : undefined}
               title={gated ? 'flag off — clic para ver cómo activarla' : undefined}
             >
               {s.label}{gated ? ' · flag off' : ''}
             </button>
           );
         })}
       </nav>
     );
   }
   ```
   > **NO** renderizar `s.icon` (los emojis del registro): el operador rechazó emojis. El label va limpio.
   > **NO** poner `cursor:default` ni `disabled` en la tab gateada: debe seguir abriendo el banner (comportamiento
   > v1 intacto). El único `disabled` es cuando el panel entero está off (`flag_enabled !== true`), igual que hoy
   > (`DevOpsPage.tsx:219`).

2. `frontend/src/pages/DevOpsPage.tsx` — conmutar la barra de tabs. La barra legacy (el `<div>` de las líneas
   214-248) queda en el path `!uiV2`; el path `uiV2` usa `<DevOpsTabsV2>`. El selector legacy (ya guardado con
   `!uiV2 &&` en F1) queda dentro del `<div>` legacy. Diff ilustrativo:
   ```tsx
   import { DevOpsTabsV2 } from './DevOpsTabsV2';
   // …
   {uiV2 ? (
     <DevOpsTabsV2 sections={DEVOPS_SECTIONS} activeId={activeId} onSelect={handleTabClick} health={ctx.health} />
   ) : (
     <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
       {DEVOPS_SECTIONS.map((s) => ( /* …botones legacy… */ ))}
       {!uiV2 && /* …selector legacy… */ }
     </div>
   )}
   ```
   > El outlet C10 + gate (líneas 250-276) permanece **intacto**: sigue mostrando `<FlagGateBanner/>` cuando la
   > sección activa está gateada. La atenuación de la tab (F2) y el banner del outlet (existente) son consistentes.

**Tests PRIMERO (TDD):** `classifyTab` ya está cubierto por `devopsShell.test.ts` (F0), que garantiza la lógica
active/gated. Sin tests de render (ver §5). Verificación por `tsc` + checklist visual (F5).

**Comando de aceptación:**
```
cd Stacky Agents/frontend && npx tsc --noEmit && npx vitest run src/pages/devopsShell.test.ts
```
**Criterio de aceptación (binario):** `tsc` 0 err; `devopsShell.test.ts` verde; con flag ON la tab activa tiene
`aria-current="page"` y borde inferior `--accent`, la tab gateada muestra "· flag off" con `opacity .5` y **sigue
abriendo** el `FlagGateBanner` al clic; con flag OFF la barra es la de botones Bootstrap de siempre.

**Flag:** `STACKY_DEVOPS_UI_V2_ENABLED`. **Impacto por runtime:** ninguno (UI). **Fallback:** flag OFF ⇒ barra
legacy. **Trabajo del operador:** ninguno (opt-in, default off).

---

### F3 — ServersSection: grilla de cards → tabla minimalista (conmutado por flag)

**Objetivo (1 frase).** En `ServersSection.tsx`, renderizar **solo cuando la flag está ON** una **tabla**
minimalista en lugar de la grilla de cards, con íconos de línea (lucide), acciones que aparecen en hover/foco y
el servidor activo marcado con texto en `--accent-hot`. **Valor:** idioma de consola de infraestructura,
denso y legible. **Cero cambios de lógica** (mismo CRUD, mismo `testResults`, mismo RDP, password write-only).

**Archivos EXACTOS a crear/editar:**

1. `frontend/src/components/devops/serversTable.ts` — **crear** el mapeo PURO del resultado de conectividad a
   la celda de Estado (testeable sin DOM):
   ```ts
   // Plan 119 — mapea el testResult existente de ServersSection a la celda "Estado".
   export type StateTone = 'ok' | 'warn' | 'none';
   export interface StateCell { tone: StateTone; label: string; latency?: string; }

   // `result` es la MISMA forma que ServersSection ya maneja hoy en `testResults`
   // (no se cambia su producción). Se leen: ok/success (bool) y detail/message + latency si existen.
   export function mapTestResultToState(result: { ok?: boolean; detail?: string; latencyMs?: number } | undefined): StateCell {
     if (!result) return { tone: 'none', label: 'sin probar' };
     if (result.ok) {
       return { tone: 'ok', label: 'Alcanzable', latency: result.latencyMs != null ? `${result.latencyMs} ms` : undefined };
     }
     return { tone: 'warn', label: result.detail?.trim() || 'No alcanzable' };
   }
   ```
   > **Ajuste de contrato:** usar los nombres de campo REALES del `testResults` que hoy existe en
   > `ServersSection.tsx` (el que hoy pinta el `detail` crudo del test — ver plan 116, `ServersSection.tsx:284-286`).
   > Si los campos difieren de `ok/detail/latencyMs`, adaptar SOLO las lecturas dentro de esta función (la firma
   > pública y el `StateCell` no cambian). No cambiar cómo se produce `testResults`.

2. `frontend/src/components/devops/serversTable.test.ts` — **crear** los tests puros:
   ```ts
   import { describe, it, expect } from 'vitest';
   import { mapTestResultToState } from './serversTable';

   describe('mapTestResultToState', () => {
     it('undefined ⇒ sin probar (none)', () => {
       expect(mapTestResultToState(undefined)).toEqual({ tone: 'none', label: 'sin probar' });
     });
     it('ok con latencia ⇒ Alcanzable + ms', () => {
       expect(mapTestResultToState({ ok: true, latencyMs: 12 })).toEqual({ tone: 'ok', label: 'Alcanzable', latency: '12 ms' });
     });
     it('falla ⇒ warn con el detail', () => {
       expect(mapTestResultToState({ ok: false, detail: 'WinRM 5985 cerrado' })).toEqual({ tone: 'warn', label: 'WinRM 5985 cerrado' });
     });
   });
   ```

3. `frontend/src/components/devops/ServersTable.module.css` — **crear** (estilos de la tabla; solo tokens):
   ```css
   .tbl { width: 100%; border-collapse: collapse; }
   .tbl thead th { text-align: left; font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); padding: 0 14px 10px; border-bottom: 1px solid var(--border); }
   .right { text-align: right; }
   .tbl tbody td { padding: 13px 14px; border-bottom: 1px solid var(--border-muted); vertical-align: middle; }
   .tbl tbody tr { transition: background 0.1s; }
   .tbl tbody tr:hover { background: var(--bg-panel); }
   .tbl tbody tr:hover .rowActions, .tbl tbody tr:focus-within .rowActions { opacity: 1; }  /* revelar también por teclado */
   .name { display: flex; align-items: center; gap: 10px; }
   .n { font-family: var(--font-mono); font-size: 0.9rem; font-weight: 500; color: var(--text-primary); }
   .active { font-size: 0.68rem; color: var(--accent-hot); letter-spacing: 0.03em; }
   .host, .user { font-family: var(--font-mono); font-size: 0.82rem; color: var(--text-muted); }
   .state { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; }
   .txtOk { color: var(--text-muted); }
   .txtWarn { color: var(--warn); }
   .lat { color: var(--text-faint); font-family: var(--font-mono); font-size: 0.75rem; margin-left: 4px; }
   .rowActions { display: flex; gap: 16px; justify-content: flex-end; opacity: 0.35; transition: opacity 0.12s; }
   .actionsCell { text-align: right; white-space: nowrap; }
   .footnote { margin-top: 28px; color: var(--text-faint); font-size: 0.75rem; }
   .ico { width: 14px; height: 14px; flex: 0 0 auto; }
   .icoOk { color: var(--success); }
   .icoWarn { color: var(--warn); }
   @media (prefers-reduced-motion: reduce) {
     .tbl tbody tr, .rowActions { transition: none; }
     .rowActions { opacity: 1; }  /* sin reveal por hover si el usuario evita animaciones */
   }
   ```

4. `frontend/src/components/devops/ServersSection.tsx` — **editar** el markup del listado para conmutar por flag.
   Leer la flag desde el contexto de sección: `const uiV2 = ctx.health?.ui_v2_enabled === true;` (la sección
   recibe `ctx`; `ctx.health` ya trae `ui_v2_enabled` tras F0). Envolver:
   ```tsx
   {uiV2 ? renderServersTable() : renderServersCards()/* markup actual, SIN cambios */}
   ```
   `renderServersTable()` (nuevo) usa `ServersTable.module.css` + lucide (`Search`, `Plus`, `Activity`,
   `Monitor`, `Crosshair`, `Check`, `AlertTriangle`) + `mapTestResultToState`. Estructura ilustrativa:
   ```tsx
   import { Search, Plus, Activity, Monitor, Crosshair, Check, AlertTriangle } from 'lucide-react';
   import t from './ServersTable.module.css';
   import s from './devops.module.css';  // reusar .btnPrimary/.link ya existentes si aplica
   import { mapTestResultToState } from './serversTable';

   // cabecera de sección (reusa clases del shell si se importan, o devops.module.css)
   // <button className="link"><Search size={14}/> Diagnosticar</button>
   // <button className="btnPrimary"><Plus size={14}/> Nuevo servidor</button>  // ÚNICO botón sólido

   <table className={t.tbl}>
     <thead>
       <tr>
         <th>Alias</th><th>Host</th><th>Usuario</th><th>Estado</th>
         <th className={t.right}>Acciones</th>
       </tr>
     </thead>
     <tbody>
       {servers.map((srv) => {
         const isActive = srv.alias === selectedAlias;
         const st = mapTestResultToState(testResults[srv.alias]);  // MISMO testResults de hoy
         return (
           <tr key={srv.alias}>
             <td><div className={t.name}><span className={t.n}>{srv.alias}</span>
               {isActive && <span className={t.active}>activo</span>}</div></td>
             <td><span className={t.host}>{srv.host}</span></td>
             <td><span className={t.user}>{srv.username}</span></td>
             <td><div className={t.state}>
               {st.tone === 'ok' && <Check size={14} className={t.icoOk} aria-hidden />}
               {st.tone === 'warn' && <AlertTriangle size={14} className={t.icoWarn} aria-hidden />}
               <span className={st.tone === 'warn' ? t.txtWarn : t.txtOk}>{st.label}</span>
               {st.latency && <span className={t.lat}>{st.latency}</span>}
             </div></td>
             <td className={t.actionsCell}><div className={t.rowActions}>
               {!isActive && <button className="link" onClick={() => onSelectServer(srv.alias)}><Crosshair size={14}/> Fijar activo</button>}
               <button className="link" onClick={() => handleTest(srv.alias)}><Activity size={14}/> Probar</button>
               {rdpAvailable && <button className="link" onClick={() => handleRdp(srv.alias)}><Monitor size={14}/> RDP</button>}
               {/* Editar / Quitar contraseña / Eliminar: mismos handlers existentes (handleEdit/handleRemovePassword/handleDelete) */}
             </div></td>
           </tr>
         );
       })}
     </tbody>
   </table>
   ```
   > **Reglas duras de F3:** (a) NO cambiar handlers ni endpoints; reutilizar los existentes
   > (`handleEdit`/`handleSubmit`/`handleRemovePassword`/`handleDelete`, el test de conectividad y su
   > `testResults`, `rdpAvailable = ctx.health.rdp_available === true`). (b) El servidor activo se marca con el
   > texto "activo" en `--accent-hot` (clase `.active`), **sin** barra ni dot de color. (c) Un **único** botón
   > sólido con acento: "Nuevo servidor" (`.btnPrimary`). Todo lo demás es `.link` gris. (d) Password sigue
   > write-only (Credential Manager); el markup no muestra contraseñas.

**Tests PRIMERO (TDD) + comando:**
```
cd Stacky Agents/frontend && npx vitest run src/components/devops/serversTable.test.ts && npx tsc --noEmit
```
Registrar `serversTable.test.ts` NO requiere ratchet (el ratchet es solo backend).

**Criterio de aceptación (binario):** `serversTable.test.ts` verde + `tsc` 0 err; con flag ON, Servidores
lista N filas (una por servidor) con alias/host/usuario en mono, la columna Estado con ícono de línea + texto +
latencia, y las acciones reveladas por hover/foco; con flag OFF, Servidores renderiza la grilla de cards de hoy
sin cambios.

**Flag:** `STACKY_DEVOPS_UI_V2_ENABLED`. **Impacto por runtime:** ninguno (UI). **Fallback:** flag OFF ⇒ cards
legacy. **Trabajo del operador:** ninguno (opt-in, default off).

---

### F4 — Callout de datos sensibles + accesibilidad + pulido

**Objetivo (1 frase).** Añadir (en el path v2 de `ServersSection`) el callout de datos sensibles y cerrar la
accesibilidad del shell nuevo (foco por teclado, `prefers-reduced-motion`, contraste, labels). **Valor:**
profesionalismo y cumplimiento de accesibilidad + reporte de riesgo de datos personales.

**Archivos EXACTOS a editar:**

1. `frontend/src/components/devops/ServersSection.tsx` (path v2) — agregar, encima de la tabla, el callout con
   la clase `.note` de `DevOpsPage.module.css` (patrón `.privacy` de `PrReviewerSection.module.css:12-18`):
   ```tsx
   import shell from '../../pages/DevOpsPage.module.css';
   // …
   <p className={shell.note}>
     <strong>Datos sensibles.</strong> Las credenciales se guardan write-only en el Credential Manager de
     Windows; nunca vuelven al navegador. Usuarios y hosts no se registran en logs.
   </p>
   ```
   > Sin emoji, sin relleno de color fuerte (solo borde-izquierdo ámbar), tal como el patrón `.privacy`.

2. **Accesibilidad (verificar en los componentes ya creados, ajustar si falta):**
   - `aria-current="page"` en la tab activa (ya en F2).
   - `:focus-visible` con `outline` visible en `.tab`, `.link`, `.btn`, y `:focus-within` en `.ctl` (ya en el
     CSS de F0). Confirmar que ningún `outline: none` global los pise.
   - `prefers-reduced-motion: reduce` desactiva transiciones y revela acciones sin depender de hover (ya en el
     CSS de F0 y F3).
   - `<label>`/`aria-label` en el selector de servidor (ya en F1: `htmlFor="devops-server-picker"`).
   - Contraste AA: todos los textos usan `--text-primary`/`--text-muted`/`--text-faint` sobre superficies
     oscuras (ratios ya validados en el resto del app). El texto blanco (`#fff`) va solo sobre `--accent`.

**Tests PRIMERO (TDD):** sin lógica pura nueva ⇒ sin test unitario nuevo. La accesibilidad se valida en el
checklist visual de F5 (no hay entorno de render para tests automáticos de a11y; ver §5).

**Comando de aceptación:**
```
cd Stacky Agents/frontend && npx tsc --noEmit
```
**Criterio de aceptación (binario):** `tsc` 0 err; el callout aparece en Servidores v2; navegación por teclado
(Tab) muestra foco visible en tabs/links/botones/picker; con `prefers-reduced-motion` no hay transiciones y las
acciones de fila están visibles sin hover.

**Flag:** `STACKY_DEVOPS_UI_V2_ENABLED`. **Impacto por runtime:** ninguno. **Fallback:** flag OFF ⇒ nada de esto
se monta. **Trabajo del operador:** ninguno (opt-in, default off).

---

### F5 — No-regresión + checklist visual (gate de cierre)

**Objetivo (1 frase).** Probar que con la flag OFF todo es byte-idéntico y que con la flag ON el shell v2 funciona,
sin romper ninguna suite existente. **Valor:** garantía de "regresión 0".

**Acciones:**

1. Correr las suites vitest existentes de DevOps + las nuevas puras, por archivo (desde `Stacky Agents/frontend`):
   ```
   npx vitest run src/pages/devopsShell.test.ts
   npx vitest run src/components/devops/serversTable.test.ts
   npx vitest run src/components/devops/RemoteConsoleSection.test.tsx
   npx vitest run src/components/devops/PipelineBuilderSection.test.ts
   npx vitest run src/components/devops/agentServerBinding.test.ts
   npx vitest run src/components/devops/DirTreePreview.test.tsx
   npx vitest run src/components/devops/__tests__/PrReviewerSection.test.ts
   npx tsc --noEmit
   ```
   > Antes de correr, hacer `npx vitest list` (o glob `src/**/DevOpsPage.test.*` y `src/**/ServersSection.test.*`)
   > para detectar si existe algún test de `DevOpsPage`/`ServersSection` no listado arriba; si existe, correrlo y
   > dejarlo verde.

2. Correr los tests de flags backend (desde `Stacky Agents/backend`):
   ```
   .venv\Scripts\python -m pytest tests/test_plan119_devops_ui_v2_flag.py -q
   .venv\Scripts\python -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
   .venv\Scripts\python -m pytest tests/test_harness_ratchet_meta.py -q
   ```

3. **Checklist visual manual** (queda para el operador/implementador; el entorno no tiene render automatizado):
   - Flag OFF ⇒ el panel DevOps se ve exactamente como hoy (h2, botones azules/grises, selector a la derecha,
     cards de servidores).
   - Flag ON ⇒ header con título/subtítulo/awareness + picker "Servidor activo"; sub-tabs underline con activa
     en `--accent`; tab gateada atenuada con "· flag off" que igual abre el banner; Servidores en tabla con
     íconos de línea, acciones en hover, servidor activo con texto "activo"; callout de datos sensibles visible.

**Criterio de aceptación (binario):** todas las suites del punto 1 y 2 verdes + `tsc --noEmit` 0 err + checklist
del punto 3 OK.

**Flag:** `STACKY_DEVOPS_UI_V2_ENABLED`. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno para
implementar; el checklist visual es una verificación, no una tarea recurrente.

---

## 5. Riesgos y mitigaciones

- **R1 — No hay entorno de tests de render (RTL/jsdom).** `frontend/package.json` NO incluye
  `@testing-library/react` ni `jsdom` (solo `vitest`), confirmando el gap ya visto en el plan 107.
  **Mitigación:** toda la lógica de riesgo se extrae a **helpers puros** (`devopsShell.ts`, `serversTable.ts`)
  con tests vitest puros (gate binario real); el DOM se valida por `tsc --noEmit` + checklist visual. **No** se
  agregan dependencias de testing (evita degradar DX / build).
- **R2 — Dual-maintenance del shell (v1 inline + v2 module.css).** Mantener dos shells indefinidamente es deuda.
  **Mitigación:** la flag es un puente temporal. **DoD futuro (fuera de scope de este plan):** una vez validado
  el v2 en producción, un plan posterior retira el path v1 y la flag (borra el JSX legacy y `STACKY_DEVOPS_UI_V2_ENABLED`
  siguiendo el patrón inverso de F0). Hasta entonces, el path v1 no se toca (menos riesgo).
- **R3 — Divergencia del gate entre tabs y outlet.** `classifyTab` (tabs) y el gate inline del outlet
  (`DevOpsPage.tsx:256`) usan la MISMA fórmula. **Mitigación:** `classifyTab` está testeado con los 4 casos y su
  fórmula es idéntica al outlet (documentado en el código); el outlet no se modifica.
- **R4 — Regresión en `ServersSection`.** Es el único componente de sección que se toca. **Mitigación:** el
  cambio es puramente de markup detrás de `uiV2`; los handlers, endpoints y `testResults` se reutilizan sin
  cambios; el path v1 (cards) queda intacto; `serversTable.ts` aísla y testea el único mapeo con lógica.
- **R5 — Datos personales / sensibles más visibles (obligación de reporte).** La tabla expone usuarios
  (`PACIFICO\deploy`) y hosts/IPs de forma más prominente que las cards ⇒ mayor riesgo de *shoulder-surfing* o
  captura de pantalla. **Mitigación:** (a) el cambio es solo presentación — **no** agrega logging, persistencia
  ni endpoints que expongan esos datos; (b) las credenciales siguen **write-only** en Credential Manager y el
  markup nunca las muestra; (c) el callout de F4 lo reafirma explícitamente; (d) Stacky es mono-operador local,
  lo que acota la superficie. Se recomienda al operador no compartir capturas del panel con la tabla poblada.
- **R6 — Flag mal registrada (rompe ratchet/known-flags).** **Mitigación:** F0 registra la flag por el patrón
  exacto del sibling `STACKY_PR_REVIEWER_ENABLED` (categoría, FlagSpec sin `default=`, requires frozen), NO la
  agrega a `_CURATED_DEFAULTS_ON`, y corre `test_harness_flags*.py` + `test_harness_ratchet_meta.py` como gate.
- **R7 — Overlap con `feat(plan-118)` (WinRM 1-click) YA en la rama.** El commit `dcfdac40`
  (`feat(plan-118): Enable-WinRM 1-click`, implementado pero sin doc de plan; este plan de rediseño es el 119)
  agregó a `ServersSection.tsx` un botón **"⬇️ Descargar scripts"** (setup de WinRM) y sumó campos a
  `frontend/src/api/endpoints.ts`. El **F3** de este plan re-maqueta el listado de servidores a tabla y el
  **F0** edita `endpoints.ts`. **Mitigación:** (a) F3 debe **conservar** ese botón de descarga en el path v2
  (reubicado en la cabecera de sección junto a "Nuevo servidor"/"Diagnosticar", con su handler/endpoint
  intactos); (b) F0 debe agregar `ui_v2_enabled?` **sin pisar** los campos que `dcfdac40` ya añadió al tipo de
  retorno de `DevOps.health`; (c) el `criticar-y-mejorar-plan` debe **re-anclar las líneas** de
  `ServersSection.tsx`/`endpoints.ts` porque `dcfdac40` (+ WIP) las corrió respecto de los números citados aquí.

---

## 6. Fuera de scope

- **No** se rediseña cada sección interna del panel (Pipelines, Agente, Consola, Ambientes, Variables,
  Publicaciones, Revisor de PRs, etc.). La única sección cuyo contenido se re-maqueta es **Servidores**
  (cards → tabla). El resto solo hereda el nuevo *chrome* (header/tabs) y su contenido queda igual.
- **No** se toca backend salvo **registrar la flag** (config + FlagSpec + help + health + requires frozen).
- **No** se agregan dependencias frontend (lucide ya está; no se agrega RTL/jsdom).
- **No** se retira el shell v1 ni la flag en este plan (ver R2: es un DoD futuro, otro plan).
- **No** se cambia ningún comportamiento, endpoint, contrato de datos, ni el runtime.
- **No** se agrega densidad configurable de tabla (la tabla es "cómoda" ~44px por default; compactar queda como
  mejora futura opcional).

---

## 7. Glosario, Orden de implementación y DoD

### Glosario (términos del dominio Stacky para un modelo menor)
- **`DEVOPS_SECTIONS`** — array declarativo en `DevOpsPage.tsx:80-152`; cada entrada es una sección del panel con
  `id/label/icon?/healthKey?/gateFlagKey?/gateMessage?/render(ctx)`. Las tabs y el outlet lo recorren. Su
  estructura y contrato NO se tocan.
- **C10 (montaje persistente)** — patrón por el que las secciones ya visitadas NO se desmontan; se ocultan con
  `display:none` (`mountedIds`, `DevOpsPage.tsx:163, 192-195`). Preserva estado interno de cada sección al
  cambiar de tab. Intocable.
- **Outlet** — el bloque que renderiza el contenido de las secciones montadas (`DevOpsPage.tsx:250-276`). Intocable.
- **Gate declarativo / `FlagGateBanner`** — cuando `s.healthKey` no está `true` en `ctx.health`, el outlet muestra
  `<FlagGateBanner/>` (un aviso "qué pasó + cómo activarlo") en vez del contenido. Intocable.
- **`healthKey`** — clave de `ctx.health` (payload de `GET /api/devops/health`, construido en
  `api/devops.py:_health_payload`) que decide si una sección está habilitada.
- **`ctx` / `DevOpsSectionContext`** — objeto que cada sección recibe en `render(ctx)`: `{ health, refetchHealth,
  selectedServer, servers }` (`DevOpsPage.tsx:184-189`). `ctx.health` tiene index signature (acepta keys nuevas).
- **write-only Credential Manager** — las contraseñas de servidores se guardan en el Windows Credential Manager y
  nunca se leen de vuelta al frontend; solo se pueden escribir/borrar (plan 91).
- **token de `theme.css`** — variable CSS (`var(--…)`) con la paleta/tipografía del app. Fuente única de color;
  prohibido inventar hex.
- **flag del arnés / `HarnessFlagsPanel`** — el sistema de feature-flags de Stacky; se registran en
  `harness_flags.py` (metadata), `config.py` (default efectivo) y se activan desde la UI del panel Arnés.
- **`_CURATED_DEFAULTS_ON`** — set (en `tests/test_harness_flags.py`) de las únicas flags autorizadas a declarar
  default ON. Una flag OFF NO va acá.
- **`_REQUIRES_MAP_FROZEN`** — mapa congelado (en `tests/test_harness_flags_requires.py`) de aristas
  `flag → flag_de_la_que_depende`; toda flag con `requires` debe estar acá.
- **ratchet de tests** — `backend/scripts/run_harness_tests.{sh,ps1}` listan los archivos de test backend; el
  meta-test `test_harness_ratchet_meta.py` falla si un test nuevo no está listado.

### Orden de implementación (numerado)
1. **F0** — backend flag (config + FlagSpec + help + health + requires frozen + ratchet) + tipos frontend +
   `DevOpsPage.module.css` + `devopsShell.ts` + `devopsShell.test.ts` + `test_plan119_devops_ui_v2_flag.py`.
2. **F1** — `DevOpsHeaderV2.tsx` + conmutación del header y del contenedor `.page` + guard `!uiV2` del selector legacy.
3. **F2** — `DevOpsTabsV2.tsx` + conmutación de la barra de sub-tabs.
4. **F3** — `serversTable.ts` (+ test) + `ServersTable.module.css` + tabla en `ServersSection.tsx` (path v2).
5. **F4** — callout `.note` + cierre de accesibilidad.
6. **F5** — no-regresión (vitest por archivo + pytest de flags + ratchet) + `tsc --noEmit` + checklist visual.

### Definición de Hecho (DoD) global
- [ ] `STACKY_DEVOPS_UI_V2_ENABLED` registrada correctamente (categoría `devops`, FlagSpec sin `default=`,
      `requires=STACKY_DEVOPS_PANEL_ENABLED` en `_REQUIRES_MAP_FROZEN`, default OFF en `config.py`, help, y
      surface en `/api/devops/health` como `ui_v2_enabled`).
- [ ] `test_plan119_devops_ui_v2_flag.py` + `test_harness_flags.py` + `test_harness_flags_requires.py` +
      `test_harness_ratchet_meta.py` verdes.
- [ ] `devopsShell.test.ts` + `serversTable.test.ts` verdes; `tsc --noEmit` 0 errores.
- [ ] Suites vitest DevOps existentes verdes (F5 punto 1).
- [ ] Flag OFF ⇒ `DevOpsPage` byte-idéntico a hoy (header `<h2>`, botones Bootstrap, selector a la derecha,
      cards de servidores); `/api/devops/health` solo gana `ui_v2_enabled:false`.
- [ ] Flag ON ⇒ header v2 + picker promovido, sub-tabs underline (`aria-current` en activa, gateada atenuada que
      igual abre el banner), Servidores en tabla con íconos de línea, callout de datos sensibles.
- [ ] 0 estilos inline en el shell v2; 100% tokens theme.css (grep sin hex nuevos salvo `#fff` sobre `--accent`).
- [ ] Contrato §3.12 C20 intacto (sumar sección futura = 1 entrada + 1 componente, 0 cambios en `DevOpsPage`).
- [ ] Paridad total en los 3 runtimes (cambio 100% frontend, ortogonal al runtime); fallback = flag OFF.
- [ ] Cero trabajo nuevo para el operador (opt-in, default off).
