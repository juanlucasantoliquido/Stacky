# Plan 239 — Cockpit DevOps: rediseño integral de UX/UI y arquitectura de la información

> **Estado:** MEJORADO (**v1 → v2**) — criticado 2026-07-25 · **Veredicto: RECHAZADO (v1) → corregido en v2**
> **Autor v1:** StackyArchitectaUltraEficientCode · **Juez/arquitecto v2:** `criticar-y-mejorar-plan` (perfil heredado del modelo activo)
> **Pipeline:** `proponer-plan-stacky` (v1) → `criticar-y-mejorar-plan` (v2, este documento) → sigue `implementar-plan-stacky` → `supervisar-implementaciones-planes`.

---

## CHANGELOG v1 → v2 (qué cambió y por qué)

Toda afirmación del v1 fue verificada contra el código el 2026-07-25. **La mayoría resistió**
(los 461/804 de `uiDebtBaseline.json`, los 75 de F7b, los 14 tokens de `theme.css`, las firmas de
`deploy_store`/`ci_run_ledger`/`server_registry`, las primitivas `Tabs`/`Card`/`StatusChip`/`Select`,
y los 15 archivos de test preexistentes que el plan nombra: **todos existen**). Lo que **no** resistió:

- **C1 (BLOQUEANTE) — pantalla en blanco.** El v1 arreglaba `activeId` (`DevOpsPage.tsx:188`) pero
  **no** `mountedIds` (`:190`), que se siembra con `DEVOPS_SECTIONS[0].id` mientras el outlet hace
  `if (!mountedIds.has(s.id)) return null` (`:324`). Con deep-link, con `pinned` o con el cockpit OFF el
  aterrizaje resuelve a una sección **no montada** ⇒ **panel vacío**. Mataba KPI-5 y KPI-9.
  Corregido en **F3.4** (un único inicializador perezoso compartido) + R16.
- **C2 (BLOQUEANTE) — F1 era inimplementable como estaba escrita.** `deploy_planner.dora_metrics`
  **no devuelve conteos** (`:341-347` solo trae el *ratio*), pero el v1 exigía CFR "sobre el TOTAL, no
  promedio de promedios" y una alerta con `(fails+successes) >= 3` — dos datos que la API no da — y
  además **prohibía** reimplementar DORA. Y citaba `_FAILED_STATUSES` (privado, `deploy_planner.py:25`)
  sin decir de dónde sale. Corregido con la nueva **F1.0** (extensión aditiva de `dora_metrics`) y la
  especificación exacta de la doble llamada en **F1.3**.
- **C3 (IMPORTANTE) — KPI-4 era un falso verde.** `TriggerPipelineSection.tsx:207` y `:293` sondean con
  `setInterval` (10 s y 3 s) y **siguen corriendo con la sección oculta**; el ratchet del v1 solo grepeaba
  `refetchInterval:`. Corregido en **F6** (ratchet ampliado a `setInterval`/`setTimeout` + gateo de los
  dos efectos, que ya reciben `ctx`) y KPI-4 reescrito.
- **C4 (IMPORTANTE) — F0.2 rompía 2 asertos más** de `test_plan119_devops_ui_v2_flag.py` que el v1 no
  nombraba (`_spec(_KEY).default is None` y `_KEY not in _CURATED_DEFAULTS_ON`). Corregido en **F0.2**.
- **C5 (IMPORTANTE) — flag inexistente.** El checklist de F8 decía `STACKY_DEVOPS_CI_RUN_LEDGER_ENABLED`;
  la real es **`STACKY_CI_RUN_LEDGER_ENABLED`** (`config.py:1427`, `harness_flags.py:193`). Corregido.
- **C6 (IMPORTANTE) — `deploy_last_failed` podía dispararse con un deploy EN CURSO** o con un `rollback`
  (`read_ledger` devuelve todos los `action`, y los entries vivos tienen `finished_at: null`). Regla
  reescrita a "último entry **terminado** con `action == "deploy"`" en **F1.2**.
- **C7..C11 (MENORES)** — referencias de línea corregidas (`_CATEGORY_KEYS` :120 no :21; `_SNAPSHOT` :20
  no :22; `App.tsx` :307/:301 no :298/:292; `endpoints.ts` :3721-3747 / :3748-3750 / :3873);
  comando del KPI-8 pasado de `python -c` a `node -e` (funciona igual en PowerShell, el shell del
  operador); el hex huérfano de `PrReviewerSection.module.css` incorporado a F7a (8 → **9** hex a matar);
  huella de regresión registrada en `error_fingerprints.json` (**F8.2**); y `test_bootstrap_health_paridad`
  con sus precondiciones declaradas.
- **[ADICIÓN ARQUITECTO] — F3.5 "Copiar resumen".** Un botón que pone el estado del cockpit en el
  portapapeles como texto llano (estado, KPIs, alertas, fuentes sin datos, alcance aplicado), para pegarlo
  en un ticket, un chat o el standup. Reusa **íntegro** el plan 194 (`CopyAsButton` + `copyService`, con
  su flag, su toast y su fallback ya probados) y un builder **puro** testeable sin jsdom. Es el paso que
  faltaba entre "veo el problema" y "lo reporto": hoy el operador transcribe a mano. HITL puro (copia
  solo si el operador hace clic), cero dependencias nuevas, cero red. Nuevo **KPI-12**.

Todo lo demás del v1 se conserva **textualmente**: mismo alcance, mismas 4 clusters, mismos umbrales,
mismos guardarraíles, misma lista de fuera-de-scope.

---
> **Serie:** cierre de la serie DevOps 87→120 (que construyó 9 secciones de superficie) y del rediseño
> parcial del plan 119 (que arregló solo el *chrome* y dejó explícitamente fuera el contenido y el
> retiro del shell v1, ver 119 §6). Este plan es el que el 119 nombró como "otro plan".
> **Depende de:** NADA pendiente. Todo el sustrato está implementado y verificado en código
> (2026-07-25): plan 87 (registro `DEVOPS_SECTIONS` + `/api/devops/health`), plan 91 (registro de
> servidores), plan 116 (doctor de conexiones), plan 119 (shell v2 + `DevOpsPage.module.css`),
> plan 120 (Centro de Despliegues + `dora_metrics`), plan 138 (tokens semánticos + 13 primitivas
> `components/ui/`), plan 141 (tema claro), plan 143 (motion), plan 150 (densidad `data-density`),
> plan 165 (contrato de URL `services/routes.ts`), plan 191 (bitácora CI `ci_run_ledger`),
> plan 193 (triage de fallos CI).
> **NO depende de** los planes 172-175 (cockpit UX global: teclado, vistas guardadas, rendimiento,
> peek) que siguen sin implementar; este plan **no invade** su alcance (ver §6 Fuera de scope).

---

## 1. Título, objetivo y KPI

### Objetivo (1 párrafo)

El panel DevOps es hoy el módulo con más superficie funcional de Stacky (9 secciones, 5 blueprints de
API, ~40 endpoints) y a la vez el **menos utilizable como herramienta de decisión**: al abrir `/devops`
el operador aterriza en un **constructor de pipelines** (`DEVOPS_SECTIONS[0].id === 'pipelines'`,
`frontend/src/pages/DevOpsPage.tsx:99-102` + `:188`) —es decir, en una *herramienta de autoría*, no en
el *estado del mundo*—, con **9 pestañas hermanas planas** sin jerarquía, una línea de contexto que
informa `"N / 10 capacidades activas"` (un dato sobre la *configuración de Stacky*, no sobre la *salud
de la operación*: `frontend/src/pages/devopsShell.ts:32`), **cero KPIs**, cero tendencias, cero alertas,
y con el agravante de que **la presentación profesional del plan 119 está apagada de fábrica**
(`STACKY_DEVOPS_UI_V2_ENABLED` default `"false"` en `backend/config.py:1361-1363`), por lo que la UI que
el operador ve por default es el shell legacy con botones Bootstrap `#007bff`/`#6c757d`
(`DevOpsPage.tsx:281-318`). Este plan lo convierte en un **cockpit**: agrega una sección **Resumen**
como aterrizaje (KPIs DORA + CI + conexiones, alertas determinísticas con salto a la sección que las
resuelve, actividad reciente unificada, tendencia de 7/14/30 días y filtros de alcance por aplicación y
por proyecto de CI), reagrupa las 9 secciones en **4 clusters
de navegación de dos niveles** (Resumen · Operar · Construir · Diagnosticar) usando la primitiva
`components/ui/Tabs` en vez de una barra artesanal, hace cada sección **direccionable por URL**
(`/devops/<id>`, reusando el contrato del plan 165 **sin tocarlo**), **frena el sondeo de las secciones
invisibles** (hoy `DeploymentsSection.tsx:50` sondea cada 4 s **para siempre** una vez visitada, porque
las secciones nunca se desmontan: `DevOpsPage.tsx:190`, `:229`, `:344`), y **converge el panel al sistema
de diseño** (el panel DevOps concentra **461 de los 804** `style={{` inline de todo el frontend —el 57%—
según `frontend/src/__tests__/uiDebtBaseline.json`). Todo el dato nuevo se **agrega server-side a partir
de fuentes que YA existen** (`deploy_planner.dora_metrics`, `ci_run_ledger.list_runs`, snapshot del doctor
de conexiones, `server_registry`): **cero credenciales nuevas, cero red, cero ejecución remota, cero LLM.**

### KPI / impacto esperado (todos binarios y verificables por comando)

| # | KPI | Verificación binaria |
|---|-----|----------------------|
| **KPI-1** | **Aterrizaje informativo:** con `STACKY_DEVOPS_COCKPIT_ENABLED=ON` (default), la sección inicial de `/devops` es `resumen` y no `pipelines`. | `npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts` — caso `resolveLandingSection` devuelve `"resumen"` sin URL ni pin. |
| **KPI-2** | **9 → 4 opciones visibles de primer nivel:** la fila primaria muestra exactamente 4 grupos. | Mismo test: `buildGroupTabs(DEVOPS_SECTION_GROUPS).length === 4`. |
| **KPI-3** | **Presentación profesional de fábrica:** `STACKY_DEVOPS_UI_V2_ENABLED` pasa a default ON. | `.venv/Scripts/python.exe -m pytest tests/test_plan239_cockpit_flag.py -q` — caso `test_ui_v2_default_on`. |
| **KPI-4** | **Sondeo cero en secciones invisibles:** ningún sondeo periódico de `components/devops/*.tsx` corre con la sección oculta — ni `refetchInterval` (1 sitio: `DeploymentsSection.tsx:50`) **ni `setInterval`** (2 sitios: `TriggerPipelineSection.tsx:207` y `:293`). **v2 (C3):** el v1 solo cubría `refetchInterval` y dejaba vivos los dos `setInterval`. | `npx vitest run src/__tests__/devopsPollingRatchet.test.ts` — 0 `refetchInterval` **y** 0 `setInterval` sin guarda de visibilidad, con `ALLOWLIST` vacía. |
| **KPI-5** | **Direccionable y compartible:** `/devops/despliegues` abre Despliegues; un click en una sección reescribe el path. | `npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts` — casos `resolveLandingSection` con `subTab`. |
| **KPI-6** | **Overview honesto (nunca ceguera silenciosa):** si una fuente está apagada, el payload lo declara y la UI lo muestra; jamás reporta 0 como si fuera un dato. | `.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_service.py -q` — casos `test_blocks_declare_flag_off` y `test_status_unknown_sin_datos`. |
| **KPI-7** | **Overview inocuo:** `GET /api/devops/overview` no abre red, no ejecuta comandos remotos y no invoca LLM. | `.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_endpoint.py -q` — caso `test_overview_no_ejecuta_remoto` (monkeypatch que revienta si se llama `remote_exec`/`requests`). |
| **KPI-8** | **Deuda visual DevOps a la baja:** los `style={{` del panel bajan de **461 → ≤ 386** (8 archivos migrados, desglose exacto en F7b) y los hex de `devops.module.css` + `DevOpsPage.module.css` + `PrReviewerSection.module.css` bajan de **9 → 0** (**v2, C9:** el v1 decía 8 y se olvidaba el hex de `PrReviewerSection.module.css`, verificado en `hexByFile`). | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` verde **sin** `UI_DEBT_REGEN`, más el conteo del baseline regenerado (comando `node -e` exacto al final de F7b). |
| **KPI-9** | **Regresión 0 con flag OFF:** con `STACKY_DEVOPS_COCKPIT_ENABLED=OFF` el panel es el del plan 119, con las 9 secciones y `ConnectionHealthStrip` intactos. | `npx vitest run src/pages/__tests__/DevOpsShellV2Regression.test.ts src/pages/__tests__/DevOpsCockpitRegression.test.ts` |
| **KPI-10** | **Contrato §3.12 C20 preservado:** sumar una sección futura sigue siendo *1 entrada + 1 componente* sin tocar `DevOpsPage.tsx`. | `DevOpsCockpitRegression.test.ts` — caso `test_seccion_sin_group_cae_en_grupo_default`. |
| **KPI-11** | **Filtros con alcance real y honesto:** aplicación, proyecto de CI y ventana (7/14/30 d) recortan KPIs, series, alertas y actividad; un filtro inválido no rompe la pantalla y el selector muestra lo **aplicado**, no lo pedido. | `.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_service.py -q` (bloque "Filtros") + `npx vitest run src/pages/__tests__/DevOpsPage.test.ts` (caso `test_filtros_usan_el_eco_del_backend`). |
| **KPI-12** *(v2)* | **[ADICIÓN ARQUITECTO] El resumen es reportable en 1 clic:** el cockpit ofrece "Copiar resumen" y produce un texto llano con estado, KPIs, alertas, fuentes sin datos y alcance aplicado — sin `0` disfrazados de dato (los `null` salen como `n/d`, igual que en pantalla). | `npx vitest run src/components/devops/overviewModel.test.ts` — casos `buildOverviewClipboardText_*` (bloque F3.5), incluido `test_clipboard_no_miente_con_datos_ausentes`. |

---

## 2. Por qué ahora / gap que cierra

Diagnóstico del dashboard actual, **cada punto verificado en el código el 2026-07-25** (nada de esto es
opinión estética):

### 2.1 Usabilidad y arquitectura de la información

1. **Aterrizaje equivocado.** `DevOpsPage.tsx:188` arranca en `DEVOPS_SECTIONS[0].id`, que es `pipelines`
   (`:99`): el constructor gráfico. El operador que entra a "ver cómo está DevOps" recibe un editor.
   No existe ninguna pantalla que responda *"¿está todo bien?"*.
2. **9 hermanas planas sin jerarquía.** `DEVOPS_SECTIONS` (`:97-179`) mezcla en un mismo nivel tres modos
   mentales distintos: **estado** (Despliegues, Servidores), **autoría** (Pipelines, Publicaciones,
   Variables, Ambientes) y **diagnóstico** (Consola, Revisor de PRs, Agente DevOps). La ley de Miller no
   es una opinión: 9 destinos equiprobables en una fila obligan a leer las 9 etiquetas cada vez.
3. **Contexto que no informa.** `devopsShell.ts:17-34` construye la línea de awareness con
   `"N / 10 capacidades activas"` (`:32`) — mide cuántas *flags* están prendidas, no si hay un despliegue
   roto. Es ruido con forma de dato.
4. **Pestañas fantasma en el espacio noble.** `DevOpsTabsV2.tsx:29` renderiza las secciones con la flag
   apagada como `"<Label> · flag off"` en la fila primaria. En una instalación con pocas flags DevOps
   encendidas, la mayoría de la barra es peso muerto.
5. **No direccionable, no persistente.** La sección activa vive en `useState` (`DevOpsPage.tsx:188`) y no
   se refleja en la URL ni se persiste. `services/routes.ts:58` y `:92-93` **ya soportan** `/devops/<sub>`
   de forma genérica (hoy lo usa solo Settings: `App.tsx:292`), pero `App.tsx:298` monta
   `<DevOpsPage />` **sin props**. Consecuencia: no se puede compartir ni marcar "DevOps → Despliegues",
   y cada F5 devuelve al constructor de pipelines. Es la única página con 9 sub-tabs que incumple el
   contrato de URL del plan 165.

### 2.2 Rendimiento

6. **Sondeo perpetuo de secciones invisibles.** `mountedIds` **solo crece** (`DevOpsPage.tsx:190` y
   `:229`) y el outlet oculta con `display:'none'` (`:344`) sin desmontar (contrato C10, deliberado, para
   no perder autoría a medio hacer). Pero `DeploymentsSection.tsx:50` declara `refetchInterval: 4000`:
   **basta visitar Despliegues una vez** para que `/api/devops/deployments/overview` se pida cada 4 s
   —15 req/min, indefinidamente— mientras el operador trabaja en Variables. Cada `useQuery` de cada
   sección montada (hay ~20 `queryKey` distintos en `components/devops/*.tsx`) queda vivo igual.
6b. **Y el sondeo no es solo `refetchInterval` (hallazgo v2, C3).** `TriggerPipelineSection.tsx:207`
   corre un `setInterval(POLL_INTERVAL_MS)` que pide `CIPipeline.monitor(project, id)` por cada corrida
   no-final, y `:293` corre otro `setInterval(…, 3000)` mientras `polling` esté activo. Los dos viven en
   `useEffect` cuyas dependencias **no incluyen la visibilidad**, así que sobreviven al `display:none`
   exactamente igual que el `refetchInterval`. Un ratchet que solo mire `refetchInterval` (como proponía
   el v1) declara victoria dejando la fuga más agresiva de las tres viva: **censo verificado
   2026-07-25** = 1 `refetchInterval` + 2 `setInterval` en `components/devops/`.

### 2.3 Diseño y consistencia visual

7. **La versión linda está apagada de fábrica.** `STACKY_DEVOPS_UI_V2_ENABLED` = `"false"`
   (`config.py:1361-1363`), mientras el shell global de la app **sí** fue promovido a ON el 2026-07-18
   (`STACKY_UI_SHELL_V2_ENABLED`, ver el comentario de promoción en `config.py:1503-1508`). Resultado
   de fábrica: sidebar v2 moderna en toda la app **y adentro** el panel DevOps con píldoras Bootstrap
   `#007bff`/`#6c757d` y `borderRadius:'4px'` (`DevOpsPage.tsx:290-298`). El plan 119 se implementó y
   quedó a oscuras.
8. **El panel DevOps es el epicentro de la deuda visual.** `uiDebtBaseline.json`: **461** ocurrencias de
   `style={{` en `components/devops/*` + `Pipeline*` + `pages/DevOpsPage.tsx`, sobre **804** en todo
   `src/` ⇒ **57%**. Peores: `BlockProperties.tsx` 58, `PipelineBuilderSection.tsx` 53,
   `PublicationsSection.tsx` 34, `ServersSection.tsx` 33, `RemoteConsoleSection.tsx` 33. Más **8** hex
   hardcodeados (`devops.module.css` 7, `DevOpsPage.module.css` 1).
9. **Divergencia con el sistema de diseño del plan 138.** `DevOpsPage.module.css` usa medidas crudas
   (`padding: 40px 40px 64px`, `font-size: 0.85rem`, `margin: 28px 0 0`) en vez de la escala semántica
   (`--space-*`, `--text-*`), por lo que **no hereda la densidad compacta del plan 150**
   (`[data-density="compacto"]` re-apunta los 9 `--space-*`: si no los usás, el panel ignora la
   preferencia del operador). Y `DevOpsTabsV2.tsx` reimplementa a mano una barra de tabs que
   `components/ui/Tabs.tsx` ya provee (con `role="tablist"`, `aria-selected` y tokens).

### 2.4 Funcionalidad ausente pese a tener el dato

10. **Los datos para decidir existen y nadie los muestra arriba.** `deploy_planner.dora_metrics`
    (`services/deploy_planner.py:311-349`) ya computa `deploys_7d`, `deploys_30d`,
    `change_failure_rate_30d`, `mttr_minutes_30d`, `last_deploy_at` — y solo se ven enterrados dentro de
    la pestaña Despliegues (`api/devops_deployments.py:92`). `GET /api/ci/runs` (`api/ci.py:233-249`)
    expone la bitácora local de corridas CI del plan 191 y **ningún consumidor la agrega**.
    `GET /api/devops/connections/health` (`api/devops_connections.py:39-47`) tiene el último snapshot
    del doctor. **No hay KPIs, ni ventana temporal, ni tendencia, ni alertas, ni actividad reciente
    unificada** en ninguna parte del panel.

### 2.5 El gap que este plan cierra

> El panel DevOps tiene **superficie de sobra y síntesis cero**. Este plan no agrega capacidades nuevas
> de operación: agrega **la capa de decisión que falta** (resumen + alertas + tendencia), **ordena** los
> 9 destinos existentes en 4 clusters navegables y direccionables, **frena** el costo de sondeo que ya
> se está pagando, y **converge** el módulo al sistema de diseño que el resto de la app ya usa. Trabajo
> del operador: **ninguno** — todo se activa solo (flags default ON) y con las flags apagadas la UI es
> exactamente la de hoy.

---

## 3. Principios y guardarraíles (no negociables)

1. **Paridad de 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro).** Todo lo de este plan es
   **UI + agregación read-only de archivos locales**: no hay una sola línea que dependa del runtime.
   El overview lee la bitácora de despliegues (`services/deploy_store`) y la de CI
   (`services/ci_run_ledger`), que registran eventos de **CI/despliegue**, no de agentes ⇒ el mismo
   payload sale idéntico bajo los 3 runtimes. **Declaración honesta y explícita:** la sección
   *Agente DevOps* hoy solo acepta `runtime: "claude_code_cli" | "codex_cli"`
   (`frontend/src/api/endpoints.ts:3868`) — **no** tiene camino Copilot. Eso es **preexistente**, este
   plan **no lo empeora ni lo arregla** (no está en su alcance) y **no** introduce ninguna dependencia
   nueva de runtime. Fallback por runtime en cada fase: el mismo, porque el código no bifurca por runtime.
2. **Cero trabajo extra para el operador.** Dos flags nuevas/promovidas, ambas **default ON**, editables
   por UI (`Configuración → Arnés`, categoría `devops`). No hay credenciales nuevas, ni catálogo a armar,
   ni paso manual, ni migración de datos. **Ninguna de las 4 excepciones duras aplica** y el plan lo
   justifica flag por flag en F0 §"Justificación del default ON".
3. **Human-in-the-loop innegociable.** El cockpit **muestra y navega**; no ejecuta nada. Prohibido en
   este plan: disparar el chequeo de conexiones automáticamente (sigue siendo POST explícito, ver
   `api/devops_connections.py` docstring), consultar drift (¡ejecuta un comando remoto!, ver
   `api/devops_deployments.py:373-395`), disparar pipelines, desplegar, hacer rollback, crear tickets o
   mandar notificaciones. Las alertas son **texto + un botón "Ir a …"** que navega a la sección donde el
   operador decide.
4. **Mono-operador sin auth real.** Nada de RBAC, usuarios, roles ni permisos.
5. **No degradar performance / seguridad / estabilidad / DX.** El overview es **una** request que lee
   archivos JSON locales ya cacheados por el SO (topes duros: 500 entradas de ledger por app, 200
   corridas CI) y **baja** el tráfico neto del panel al frenar el sondeo invisible. No agrega
   dependencias npm ni pip (verificado: `lucide-react` ya está; las sparklines son SVG a mano).
6. **Honestidad de datos por sobre la estética (anti "ceguera silenciosa").** Lección directa de la
   crítica del plan 238 (bloqueante: *"ceguera silenciosa con tracker gitlab"*) y del censo honesto del
   plan 237: si una fuente está apagada o vacía, el payload lo **declara** (`blocks[x].available=false` +
   `reason`) y la UI lo **muestra** ("CI: bitácora apagada"), y el estado global es `unknown`, **jamás**
   un `0` disfrazado de "todo bien".
7. **Reusar, no reinventar.** Primitivas `components/ui/` (plan 138: `Card`, `StatusChip`,
   `SectionHeader`, `Tabs`, `Skeleton`), tokens `theme.css` (planes 138/141/143/150), contrato de URL
   `services/routes.ts` (plan 165, **sin modificarlo**), `hooks/useLocalStorageState.ts`, ratchet
   `uiDebtRatchet` (plan 138 F0), flags del arnés, y el patrón de KPIs de
   `components/costcenter/CostKpiCards.tsx` (plan 142 F6).
8. **Backward-compatible y reversible.** Flag OFF ⇒ el panel del plan 119, sin quitar nada. **No se
   borra el shell v1** (ver R3): el 119 lo dejó como DoD futuro y retirarlo exige cirugía sobre el mapa
   congelado `test_harness_flags_requires.py` — fuera de alcance, declarado en §6.
9. **TDD.** Cada fase escribe primero su test con nombre exacto y comando exacto; el criterio de
   aceptación es un comando que devuelve verde/rojo.
10. **Prohibido el ruido nuevo.** Ninguna alerta nueva va al centro de notificaciones (plan 152) ni al
    digest: eso sería autonomía proactiva. Las alertas viven **solo** en la pantalla que el operador abre.

---

## 4. Fases

**Mapa de dependencias.** F0 → **F1.0** → F1 → F2 → F3 (cadena dura). F4 → F5 → F6 (cadena del shell,
requiere F0). F7a/F7b y F8 al final. F3 requiere F2, que requiere F1, que requiere **F1.0**.

```
F0 (flags+tipos+CSS)
 ├─► F1.0 (dora_metrics +cfr_sample_30d) ─► F1 (backend service) ─► F2 (modelo puro front) ─► F3 (Resumen + F3.4 aterrizaje + F3.5 copiar)
 └─► F4 (shell agrupado) ─► F5 (deep-link + pin) ─► F6 (visibilidad/sondeo: refetchInterval Y setInterval)
                                                      └─► F7a (tokens/responsive) ─► F7b (barrido inline) ─► F8 (gate + huellas)
```

> **v2 — dos aristas nuevas, no negociables:** (1) **F1.0 antes que F1**, porque F1 usa una clave que
> hoy `dora_metrics` no devuelve; (2) **F3.4 dentro de F3**, no en F5: sin el fix del aterrizaje, F3 deja
> el panel en blanco en cuanto la sección activa no es la primera del array. F5 solo le pasa dos valores
> (`subTab`, `pinned`) al efecto que F3.4 ya dejó puesto.

---

### F0 — Flags, tipos, health y CSS base (sin ningún cambio visible)

**Objetivo (1 frase).** Registrar la flag maestra del cockpit con sus 7 patas (las 6 del riel de la casa
+ el alta en `_CURATED_DEFAULTS_ON` que exige todo `default=True`), promover la flag del plan 119 a
default ON, y crear los tipos + el CSS module que consumirán F3/F4 — sin alterar un pixel todavía.
**Valor.** Deja el terreno preparado y ya entrega el KPI-3 (la presentación profesional del 119 pasa a
ser la de fábrica) con un cambio de 1 palabra por archivo.

#### F0.1 — Flag nueva `STACKY_DEVOPS_COCKPIT_ENABLED` (7 patas, default ON)

**Pata 1 — `backend/config.py`.** Insertar **inmediatamente después** del bloque de
`STACKY_DEVOPS_UI_V2_ENABLED` (hoy en `config.py:1361-1363`):

```python
    # ── Plan 239 — Cockpit DevOps (Resumen + navegación agrupada + deep-link) ──
    # Default ON: solo agrega una vista de LECTURA y reordena la navegación del
    # panel. Ninguna de las 4 excepciones duras aplica (ver plan 239 F0):
    # no bypassea revisión humana (no ejecuta nada), no es destructiva ni
    # irreversible (OFF ⇒ panel del plan 119 idéntico), no tiene prerequisitos
    # (lee ledgers locales; si no existen, estado vacío honesto) y no reduce
    # seguridad (no expone dato nuevo: agrega lo que ya se ve en cada sección).
    STACKY_DEVOPS_COCKPIT_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_COCKPIT_ENABLED", "true"
    ).strip().lower() == "true"
```

**Pata 2 — `backend/services/harness_flags.py`, categoría `devops`.** Agregar la clave al final de la
tupla de la categoría `"devops"` del dict `_CATEGORY_KEYS` (**el dict se declara en
`harness_flags.py:120`** — v2, C7: el v1 decía `:21`, que es un import; la categoría `"devops"` abre en
`:205` y su última entrada actual es `"STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED"` en `:239`):

```python
        "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED",  # Plan 198 — bitácora de applies de ambientes
+       "STACKY_DEVOPS_COCKPIT_ENABLED",  # Plan 239 — cockpit DevOps (Resumen + nav agrupada)
```

**Pata 3 — `FlagSpec` en el mismo archivo.** Insertar **después** del `FlagSpec` de
`STACKY_DEVOPS_UI_V2_ENABLED` (hoy `harness_flags.py:3285-3299`):

```python
    # ── Plan 239 — Cockpit DevOps ─────────────────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_COCKPIT_ENABLED",
        type="bool",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_harness_flags.py:467)
        label="Cockpit DevOps (Plan 239)",
        description=(
            "Plan 239 — Agrega la sección Resumen del panel DevOps (KPIs de despliegue "
            "y CI, alertas determinísticas, actividad reciente y tendencia de 14 días), "
            "agrupa las secciones en 4 clusters navegables y hace cada sección "
            "direccionable por URL (/devops/<seccion>). Solo lectura: no ejecuta "
            "despliegues, pipelines ni comandos remotos. OFF = panel del plan 119."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # profundidad 1 (master del panel)
    ),
```

> **Regla dura del arnés (gotcha conocido):** un `FlagSpec` con `default=True` **obliga** a dar de alta
> la clave en `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`), o
> `test_default_known_only_for_curated` (`:827`) queda rojo. Ver Pata 6.

**Pata 4 — `backend/services/harness_flags_help.py`.** Insertar después de la entrada
`"STACKY_DEVOPS_UI_V2_ENABLED"` (hoy `:1342`). Los **4 campos son obligatorios** y son exactamente
`what` / `on_effect` / `off_effect` / `example` (el dataclass `PlainHelp` no tiene `why` ni
`default_hint` — error real detectado en la crítica del plan 119, C8):

```python
    "STACKY_DEVOPS_COCKPIT_ENABLED": PlainHelp(
        what="Le agrega al panel DevOps una pantalla de Resumen y agrupa las pestañas.",
        on_effect="Al entrar a DevOps ves primero un Resumen con los números clave "
                  "(despliegues, fallos, tiempo de recuperacion, corridas de CI, "
                  "conexiones), los avisos de lo que necesita atencion y la actividad "
                  "reciente. Las pestañas quedan ordenadas en 4 grupos y cada seccion "
                  "tiene su propia direccion web para guardar en favoritos.",
        off_effect="El panel DevOps queda como antes: sin Resumen y con las 9 pestañas "
                   "en una sola fila.",
        example="Entras a DevOps y ves 'Ultimo despliegue: hace 2 dias' y un aviso "
                "'2 corridas de CI fallaron esta semana' con un boton para ir a verlas.",
    ),
```

**Pata 5 — `backend/api/devops.py`, `_health_payload()`.** Agregar la key aditiva al final del dict
(hoy termina en `:68-72` con `local_doctor_enabled`):

```python
        "cockpit_enabled": bool(getattr(cfg, "STACKY_DEVOPS_COCKPIT_ENABLED", False)),  # Plan 239
```

> `getattr(cfg, ...)` con `cfg = _config.config` (la **instancia**, `api/devops.py:38`) es lo correcto
> acá — gotcha conocido: `getattr` sobre el **módulo** `config` devuelve el default y mata la rama OFF.

**Pata 6 — `backend/tests/test_harness_flags.py`.** Agregar la clave al set `_CURATED_DEFAULTS_ON`
(empieza en `:467`), en una línea nueva al final del bloque de promociones, con comentario
`# Plan 239 — cockpit DevOps (solo lectura)`.

**Pata 7 (mapa congelado) — `backend/tests/test_harness_flags_requires.py`.** Agregar junto a la entrada
del plan 119 (hoy `:203`):

```python
    "STACKY_DEVOPS_COCKPIT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 239
```

#### F0.2 — Promoción de `STACKY_DEVOPS_UI_V2_ENABLED` a default ON

Tres ediciones quirúrgicas, calcadas de la promoción ya aprobada por el operador para
`STACKY_UI_SHELL_V2_ENABLED` (`config.py:1503-1508`):

1. `backend/config.py:1362`: `os.getenv("STACKY_DEVOPS_UI_V2_ENABLED", "false")` → `"true"`, y agregar
   arriba el comentario:
   ```python
   # PROMOVIDA a default ON (plan 239 F0): el shell v2 del plan 119 es ahora la
   # presentación de fábrica del panel DevOps — hasta hoy quedaba a oscuras
   # mientras el shell global de la app ya iba en v2 (STACKY_UI_SHELL_V2_ENABLED,
   # promovida 2026-07-18), dejando el panel con píldoras Bootstrap por default.
   # Curada en _CURATED_DEFAULTS_ON y espejada con default=True en la FlagSpec.
   ```
2. `backend/services/harness_flags.py`, `FlagSpec` de `STACKY_DEVOPS_UI_V2_ENABLED` (`:3285-3299`):
   agregar `default=True,` y **borrar** el comentario `# SIN default= (solo _CURATED_DEFAULTS_ON…)`
   que hoy está en `:3298`.
3. `backend/tests/test_harness_flags.py`: alta de `"STACKY_DEVOPS_UI_V2_ENABLED"` en
   `_CURATED_DEFAULTS_ON`.
4. `backend/tests/test_plan119_devops_ui_v2_flag.py` — **son TRES asertos, no uno** (v2, C4: el v1 solo
   nombraba el tercero y el implementador se encontraba con 2 rojos "sorpresa" que puede arreglar mal,
   p.ej. sacando la clave del set curado y rompiendo `test_harness_flags`). Los tres, en orden de
   aparición, **hay que actualizarlos en la misma edición**:
   1. `assert _spec(_KEY).default is None` → `assert _spec(_KEY).default is True`
      *(lo rompe el punto 2 de esta misma fase, que agrega `default=True` a la `FlagSpec`)*.
   2. `assert _KEY not in _CURATED_DEFAULTS_ON` → `assert _KEY in _CURATED_DEFAULTS_ON`
      *(lo rompe el punto 3, que da de alta la clave en el set curado)*.
   3. En `test_flag_default_off_in_config`:
      `assert config_module.config.STACKY_DEVOPS_UI_V2_ENABLED is False` → `is True`, y renombrar el caso
      a `test_default_on_tras_promocion_plan239`.

   Los tres con el comentario `# Plan 239 F0 — promovida a ON; el default OFF original era del plan 119.`
   **Regla de honestidad:** actualizar el aserto porque el default cambió a propósito es legítimo;
   **borrar** el caso o aflojarlo a `is not None` sería falsear el arnés — prohibido.

#### F0.3 — Tipos y CSS base (frontend)

**Editar `frontend/src/pages/DevOpsPage.tsx`:**

a) En `interface DevOpsHealth` (`:27-49`), agregar antes del index signature:
```ts
  cockpit_enabled?: boolean; // Plan 239 — cockpit DevOps
```

b) En `interface DevOpsSection` (`:65-73`), agregar **opcional** (mantiene el contrato C20: una sección
futura sin `group` sigue funcionando con 1 entrada):
```ts
  group?: DevOpsGroupId; // Plan 239 — cluster de navegación. Ausente ⇒ DEFAULT_GROUP.
  summary?: string;      // Plan 239 — 1 línea para el header de sección (opcional).
```

c) En `interface DevOpsSectionContext` (`:52-62`), agregar **opcional** (precedente: `selectedServer`
del plan 91 y `setActiveSection` del plan 120):
```ts
  /** Plan 239 F6 — true si esta sección es la visible. Las secciones que sondean
   *  DEBEN gatear su refetchInterval con esto. Ausente ⇒ tratar como true
   *  (shells que no lo propaguen degradan al comportamiento de hoy). */
  visible?: boolean;
```

**Editar `frontend/src/api/endpoints.ts`:** en el tipo de retorno de `DevOps.health()` (`:3718-3741`),
agregar `cockpit_enabled?: boolean; // Plan 239`.

**Crear `frontend/src/pages/DevOpsCockpit.module.css`** con el esqueleto (todo con tokens del plan 138 —
así hereda automáticamente densidad del 150 y tema claro del 141; **cero hex**, `#fff` prohibido: usar
`--text-on-solid`):

```css
/* Plan 239 — CSS del cockpit DevOps. SOLO tokens de theme.css (planes 138/141/143/150).
   Prohibido: hex de color y px crudos donde exista token. */
.page { max-width: 1280px; margin: 0 auto; padding: var(--space-8) var(--space-8) var(--space-9);
        height: 100%; display: flex; flex-direction: column; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-7); }
.titleRow { display: flex; align-items: center; gap: var(--space-5); }
.title { font-size: var(--text-2xl); font-weight: var(--weight-semibold); letter-spacing: -0.02em;
         margin: 0; color: var(--text-primary); }
.subtitle { color: var(--text-muted); font-size: var(--text-sm); margin: var(--space-2) 0 0; }
.navPrimary { display: flex; gap: var(--space-2); border-bottom: var(--border-width) solid var(--border);
              margin: var(--space-7) 0 0; overflow-x: auto; }
.navSecondary { display: flex; gap: var(--space-2); margin: var(--space-5) 0 0; overflow-x: auto; }
.disabledDisclosure { margin-left: auto; font-size: var(--text-xs); color: var(--text-faint); }
.kpiGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
           gap: var(--space-5); margin: var(--space-7) 0 0; }
.kpiLabel { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.07em;
            color: var(--text-faint); }
.kpiValue { font-size: var(--text-xl); font-weight: var(--weight-semibold); color: var(--text-primary);
            font-family: var(--font-mono); margin-top: var(--space-3); }
.kpiHint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--space-2); }
.alerts { display: flex; flex-direction: column; gap: var(--space-4); margin: var(--space-7) 0 0; }
.alertRow { display: flex; align-items: flex-start; gap: var(--space-5); padding: var(--space-5);
            border: var(--border-width) solid var(--border); border-radius: var(--radius-md);
            background: var(--bg-panel); }
.alertBody { flex: 1; min-width: 0; }
.alertTitle { font-size: var(--text-md); font-weight: var(--weight-medium); color: var(--text-primary); }
.alertDetail { font-size: var(--text-sm); color: var(--text-muted); margin-top: var(--space-2); }
.timeline { display: flex; flex-direction: column; gap: var(--space-3); margin: var(--space-6) 0 0; }
.eventRow { display: grid; grid-template-columns: 96px 1fr auto; gap: var(--space-5);
            align-items: center; font-size: var(--text-sm); }
.eventWhen { color: var(--text-faint); font-family: var(--font-mono); font-size: var(--text-xs); }
.spark { display: block; width: 100%; height: 40px; }
.sparkLine { fill: none; stroke: var(--accent); stroke-width: 1.5; }
.sparkFail { fill: none; stroke: var(--danger); stroke-width: 1.5; }
.blocksNote { font-size: var(--text-xs); color: var(--text-faint); margin: var(--space-6) 0 0; }
.empty { color: var(--text-muted); font-size: var(--text-sm); padding: var(--space-7) 0; }

/* Responsive: ventana angosta ⇒ respiración mínima y filas de nav deslizables. */
@media (max-width: 900px) {
  .page { padding: var(--space-6) var(--space-5) var(--space-8); }
  .head { flex-direction: column; gap: var(--space-5); }
  .eventRow { grid-template-columns: 1fr; gap: var(--space-2); }
}
@media (prefers-reduced-motion: reduce) { .alertRow { transition: none; } }
```

**Tests PRIMERO.** Crear `backend/tests/test_plan239_cockpit_flag.py`:

```python
"""Plan 239 F0 — las 6+1 patas de STACKY_DEVOPS_COCKPIT_ENABLED y la promoción del 119."""
# Casos exactos a cubrir:
# 1. test_cockpit_flag_en_categoria_devops       -> la clave está en la tupla "devops" de
#                                                   harness_flags._CATEGORY_KEYS (nombre real del dict,
#                                                   declarado en services/harness_flags.py:120)
# 2. test_cockpit_flag_tiene_flagspec            -> existe FlagSpec con type="bool" y default=True
# 3. test_cockpit_flag_tiene_help_llano          -> harness_flags_help tiene los 4 campos no vacíos
# 4. test_cockpit_flag_requires_panel            -> requires == "STACKY_DEVOPS_PANEL_ENABLED"
# 5. test_cockpit_default_on                     -> config.config.STACKY_DEVOPS_COCKPIT_ENABLED is True
# 6. test_health_expone_cockpit_enabled          -> GET /api/devops/health trae la key (bool)
# 7. test_health_cockpit_off                     -> monkeypatch False ⇒ health la reporta False y sigue 200
# 8. test_ui_v2_default_on                       -> config.config.STACKY_DEVOPS_UI_V2_ENABLED is True (KPI-3)
# 9. test_bootstrap_health_paridad               -> /api/devops/bootstrap y /health traen las MISMAS keys.
#    v2 (C11) PRECONDICIONES del caso, o da un rojo por motivos ajenos al plan:
#      - bootstrap es 404 si STACKY_DEVOPS_BOOTSTRAP_ENABLED está OFF ⇒ monkeypatch a True;
#      - bootstrap es 400 sin ?project= ⇒ pedir "/api/devops/bootstrap?project=<el activo>";
#      - comparar payload["health"].keys() contra _health_payload().keys() (bootstrap EMBEBE
#        _health_payload en api/devops.py, así que la paridad es estructural: el test la CONGELA).
```

**Registrar los tests en el ratchet** (obligatorio; si no, `tests/test_harness_ratchet_meta.py` queda
rojo): agregar en `backend/scripts/run_harness_tests.sh`, dentro del array `HARNESS_TEST_FILES`, en el
bloque DevOps:

```
  tests/test_plan239_cockpit_flag.py
  tests/test_plan239_devops_overview_service.py
  tests/test_plan239_devops_overview_endpoint.py
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan239_cockpit_flag.py -q
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py tests/test_harness_ratchet_meta.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan119_devops_ui_v2_flag.py -q
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx tsc --noEmit
```
> **Gotcha obligatorio:** correr `test_harness_flags.py` **solo, por archivo**. Hace
> `importlib.reload(config)` y contamina a los tests flag-off de la misma corrida.

**Criterio de aceptación (binario).** Los 4 comandos de pytest y `tsc --noEmit` en verde, y
`GET /api/devops/health` devuelve `cockpit_enabled: true` y `ui_v2_enabled: true` sin variables de entorno.

**Flag que protege.** `STACKY_DEVOPS_COCKPIT_ENABLED`, **default ON**.

**Justificación del default ON (obligatoria, sin genéricos).** Ninguna de las 4 excepciones duras aplica:
(1) **no bypasea revisión humana** — no publica, no crea tickets, no ejecuta remoto, no manda mensajes:
es una vista de lectura y botones de navegación; (2) **no es destructiva ni irreversible** — con OFF el
panel vuelve byte a byte al del plan 119, y no escribe ningún dato nuevo; (3) **no tiene prerequisito no
garantizado** — lee ledgers JSON locales del propio Stacky y, si no existen, el overview devuelve estado
`unknown` con los bloques declarados como vacíos (nunca error); (4) **no reduce la seguridad** — agrega
datos que el operador **ya ve** dentro de cada sección, al mismo mono-operador, sin exponer secretos
(el masking de `services/devops_evidence.py` sigue rigiendo en su camino y este payload no incluye logs).
La promoción de `STACKY_DEVOPS_UI_V2_ENABLED` es 100% presentación y sigue el precedente explícito y ya
aprobado por el operador de `STACKY_UI_SHELL_V2_ENABLED` (`config.py:1503-1508`).

**Impacto por runtime.** Ninguno: son flags, tipos y CSS. **Codex CLI / Claude Code CLI / Copilot Pro:
comportamiento idéntico**; no hay fallback porque no hay bifurcación por runtime.

**Trabajo del operador: ninguno.**

---

### F1 — Backend: `services/devops_overview.py` + `GET /api/devops/overview`

**Objetivo (1 frase).** Un servicio puro que agrega lo que ya existe (bitácora de despliegues, bitácora
CI, snapshot de conexiones, registro de servidores) en KPIs + series + alertas determinísticas + filtros
por aplicación/proyecto/ventana, y un endpoint **siempre 200** que degrada por bloque en vez de romperse.
**Valor.** Fuente única de verdad para el Resumen, testeable en Python sin UI, reutilizable después por
el digest sin duplicar umbrales.

#### F1.0 — Prerrequisito: extensión ADITIVA de `deploy_planner` (v2, C2 — hacerla PRIMERO)

> **Por qué existe esta sub-fase.** El v1 mandaba "reusar `dora_metrics`, **no** reimplementar DORA" y a
> la vez pedía dos datos que `dora_metrics` **no devuelve**: (a) el CFR consolidado *sobre el total* de
> todas las apps, y (b) el **tamaño de muestra** `fails+successes` que exige la alerta
> `deploy_failure_rate` (`CFR_MIN_SAMPLE = 3`). Verificado en `services/deploy_planner.py:341-347`: el
> retorno tiene exactamente 5 claves y **ninguna** es un conteo de fallos/éxitos. Con el v1 en la mano, un
> modelo menor solo podía inventar una API inexistente o hacer el "promedio de promedios" que el propio
> plan prohíbe. Se arregla con **dos ediciones aditivas de 1 línea cada una**, backward-compatible
> (nadie pierde claves; los consumidores actuales — `api/devops_deployments.py:92` — siguen igual).

**Edición 1 — `backend/services/deploy_planner.py:25`.** Publicar el set de estados fallidos, que hoy es
privado y este plan necesita citar por nombre en la tabla F1.2:

```python
-_FAILED_STATUSES = ("failed", "failed_smoke")
+FAILED_STATUSES = ("failed", "failed_smoke")   # Plan 239 — público: lo consume services/devops_overview
+_FAILED_STATUSES = FAILED_STATUSES             # alias retro-compatible (usos internos :322)
```

**Edición 2 — `backend/services/deploy_planner.py`, dict de retorno de `dora_metrics` (`:341-347`).**
Agregar **una** clave al final, sin tocar las 5 existentes:

```python
         "last_deploy_at": last_deploy_at,
+        # Plan 239 — tamaño de muestra del CFR: cuántos deploys de la ventana de 30 d
+        # terminaron en éxito o en fallo (los "running" no cuentan). Sin esto no se
+        # puede aplicar el umbral CFR_MIN_SAMPLE ni consolidar el CFR entre apps.
+        "cfr_sample_30d": total_30,
```

**Test PRIMERO — agregar a `backend/tests/test_plan120_planner.py`** (archivo existente, ya registrado en
el ratchet):

```
test_dora_expone_cfr_sample_30d        -> 2 éxitos + 1 fallo ⇒ cfr_sample_30d == 3
test_dora_cfr_sample_ignora_running    -> un entry status "running" NO suma a cfr_sample_30d
test_dora_claves_previas_intactas      -> las 5 claves del plan 120 siguen presentes (backward-compat)
test_failed_statuses_publico           -> deploy_planner.FAILED_STATUSES == deploy_planner._FAILED_STATUSES
```

**Comando exacto.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan120_planner.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan120_flags.py -q
```

**Criterio de aceptación (binario).** Ambos verdes, **sin haber modificado ningún test preexistente del
plan 120** (prueba de que la extensión es puramente aditiva).

#### F1.1 — Contrato del payload (EXACTO — el frontend depende de estas claves)

```jsonc
{
  "generated_at": "2026-07-25T14:02:11Z",   // ISO-8601 UTC con Z
  "status": "ok",                            // "ok" | "warning" | "danger" | "unknown"
  "filters": {                               // eco de los filtros APLICADOS (nunca de los pedidos)
    "app_id": null,                          // null = todas las aplicaciones
    "project": null,                         // null = todos los proyectos de CI
    "window_days": 14                        // 7 | 14 | 30 — largo de las series
  },
  "options": {                               // para poblar los selectores, sin una 2ª request
    "apps": [{ "id": "agendaweb", "name": "AgendaWeb" }],
    "projects": ["RSPACIFICO"]               // proyectos presentes en la bitácora de CI
  },
  "kpis": {
    "deploys_7d": 4,                         // int
    "deploys_30d": 11,                       // int
    "change_failure_rate_30d": 0.18,         // float 0..1 | null (sin datos)
    "cfr_sample_30d": 11,                    // int — v2 (C2): sobre cuántos deploys TERMINADOS se
                                             //   calculó el CFR. Sin esto, "100% de fallos" sobre
                                             //   1 muestra se lee igual que sobre 40 (deshonesto).
                                             //   La UI lo muestra como hint del KPI de CFR.
    "mttr_minutes_30d": 37.5,                // float | null
    "last_deploy_at": "2026-07-24T18:03:00Z",// ISO | null
    "ci_runs_7d": 9,                         // int
    "ci_failures_7d": 2,                     // int
    "ci_running_now": 1,                     // int
    "connections_ok": 3,                     // int | null (nunca chequeado)
    "connections_total": 4,                  // int | null
    "servers_total": 2,                      // int
    "apps_total": 2,                         // int
    "targets_configured": 3,                 // int
    "targets_locked": 0                      // int
  },
  "series": {
    "days": ["2026-07-12", "...", "2026-07-25"],  // EXACTAMENTE `filters.window_days` strings YYYY-MM-DD, viejo→nuevo
    "deploys_by_day":      [0,1,0,0,2,0,1,0,0,0,1,0,0,0],  // 14 ints
    "deploy_failures_by_day":[0,0,0,0,1,0,0,0,0,0,0,0,0,0],// 14 ints
    "ci_runs_by_day":      [1,0,2,0,0,3,0,1,0,0,2,0,0,0],  // 14 ints
    "ci_failures_by_day":  [0,0,1,0,0,1,0,0,0,0,0,0,0,0]   // 14 ints
  },
  "alerts": [
    { "id": "ci_failures", "tone": "warning",
      "title": "2 corridas de CI fallaron en los últimos 7 días",
      "detail": "La más reciente: proyecto RSPACIFICO, pipeline 8123.",
      "section": "pipelines" }                // id de DEVOPS_SECTIONS al que salta
  ],
  "recent": [
    { "at": "2026-07-24T18:03:00Z", "kind": "deploy", "tone": "success",
      "title": "Deploy AgendaWeb → PROD-01", "status": "success", "section": "despliegues",
      "app_id": "agendaweb", "project": null }   // app_id en deploys, project en CI; el otro va null
  ],                                          // máx 12, orden descendente por "at"
  "blocks": {
    "deployments": { "available": true,  "reason": null },
    "ci":          { "available": false, "reason": "flag_off" },
    "connections": { "available": true,  "reason": null },
    "servers":     { "available": true,  "reason": null }
  }
}
```
`reason` ∈ `null | "flag_off" | "sin_datos" | "error_lectura"`. **Nunca** se omite un bloque: si está
apagado, `available:false` + `reason` y sus KPIs quedan en `null`/`0` **declarados**, no inventados.

#### F1.2 — Reglas de alerta (tabla congelada, umbrales constantes, cero configuración)

| `id` | Condición exacta | `tone` | `section` |
|------|------------------|--------|-----------|
| `deploy_last_failed` | **(v2, C6)** para algún `(app,target)`: el último entry **terminado** —el más reciente con `action == "deploy"` **y** `finished_at` no nulo— tiene `status` en `deploy_planner.FAILED_STATUSES` (público desde F1.0). Los entries en curso (`finished_at: null`) y los `action` distintos de `deploy` (p. ej. `rollback`) **se ignoran para esta regla**: avisar "el último deploy falló" porque hay uno corriendo sería mentir. | `danger` | `despliegues` |
| `deploy_failure_rate` | `change_failure_rate_30d >= 0.30` **y** `cfr_sample_30d >= 3` (la clave que agrega F1.0; **v2, C2:** el v1 pedía `fails+successes`, un dato que la API no devolvía) | `danger` | `despliegues` |
| `deploy_locked` | algún destino con `locked == true` | `warning` | `despliegues` |
| `mttr_high` | `mttr_minutes_30d >= 240` | `warning` | `despliegues` |
| `deploy_stale` | `apps_total >= 1` y `last_deploy_at` con antigüedad `> 21` días | `warning` | `despliegues` |
| `deploy_never` | `targets_configured >= 1` y bitácora de despliegues vacía | `info` | `despliegues` |
| `ci_failures` | `ci_failures_7d >= 2` | `warning` | `pipelines` |
| `ci_stuck` | alguna corrida en estado `running`/`inProgress` con `started_at` de más de `120` min | `warning` | `pipelines` |
| `connections_down` | snapshot con `>= 1` chequeo cuyo estado no es OK | `danger` | `servidores` |
| `connections_never` | `status == "never_run"` (nunca se corrió el doctor) | `info` | `servidores` |
| `connections_stale` | `stale == true` | `info` | `servidores` |
| `no_servers` | bloque `servers` disponible y `servers_total == 0` | `info` | `servidores` |

Constantes al tope del módulo, en MAYÚSCULAS, una por umbral:
`CFR_DANGER = 0.30`, `CFR_MIN_SAMPLE = 3`, `MTTR_WARN_MINUTES = 240`, `DEPLOY_STALE_DAYS = 21`,
`CI_FAILURES_WARN = 2`, `CI_STUCK_MINUTES = 120`, `SERIES_DAYS = 14`, `RECENT_LIMIT = 12`,
`CI_READ_LIMIT = 200`, `LEDGER_READ_LIMIT = 500`.

**Estado global** (`status`): `danger` si hay ≥1 alerta `danger`; si no, `warning` si hay ≥1 `warning`;
si no, `ok` **solo si al menos un bloque está `available` con datos**; en cualquier otro caso `unknown`.
**Prohibido devolver `ok` sin datos** (guardarraíl 6).

#### F1.2b — Filtros (los 3 únicos que existen, sin más)

| filtro | query param | valores válidos | qué recorta | inválido ⇒ |
|--------|-------------|-----------------|-------------|------------|
| Aplicación | `app_id` | un `id` presente en `options.apps` | bitácora de despliegues (KPIs DORA, series de deploy, alertas de deploy, `recent` de deploy) | se descarta a `None` (= todas) |
| Proyecto de CI | `project` | un valor presente en `options.projects` | bitácora CI (KPIs CI, series CI, alertas CI, `recent` de CI) | se descarta a `None` (= todos) |
| Ventana | `window_days` | `7`, `14`, `30` | **solo** el largo de `series` (los KPIs siguen siendo 7d/30d fijos, que es la definición DORA) | se descarta a `14` |

Reglas duras del filtrado:
1. **Un filtro inválido NUNCA es un error 400.** La pantalla tiene que abrirse siempre, incluso con un
   link viejo cuyo `app_id` ya no existe.
2. **`filters` es el eco de lo APLICADO**, no de lo pedido. La UI pinta los selectores desde ese eco, así
   que el operador siempre ve la verdad de lo que está mirando.
3. **`options` se computa sobre el universo SIN filtrar.** Si se recortara, al filtrar por una app el
   selector quedaría con una sola opción y no habría forma de volver a "todas".
4. **El filtro se aplica ANTES** de derivar KPIs, series, alertas y `recent`: no se puede mostrar una
   alerta de una app que el operador filtró fuera.
5. Los filtros **no** afectan las conexiones ni los servidores (son globales de la máquina, no de una app).

#### F1.3 — Archivo a crear: `backend/services/devops_overview.py`

Firmas EXACTAS (funciones puras + un único orquestador que hace la lectura):

```python
"""Plan 239 F1 — agregación read-only del panel DevOps.

REGLA DURA: este módulo NO abre red, NO ejecuta comandos remotos y NO invoca LLM.
Lee únicamente: services.deploy_store (bitácora local), services.ci_run_ledger
(bitácora local), el snapshot en memoria del doctor de conexiones y
services.server_registry. El drift (api/devops_deployments.py:373) queda EXCLUIDO
a propósito: ejecuta un comando en el servidor remoto y sería una acción, no una lectura.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

CFR_DANGER = 0.30
CFR_MIN_SAMPLE = 3
MTTR_WARN_MINUTES = 240
DEPLOY_STALE_DAYS = 21
CI_FAILURES_WARN = 2
CI_STUCK_MINUTES = 120
SERIES_DAYS = 14
RECENT_LIMIT = 12
CI_READ_LIMIT = 200
LEDGER_READ_LIMIT = 500

_CI_FAILED = {"failed", "failure", "canceled", "cancelled", "error"}
_CI_RUNNING = {"running", "inprogress", "in_progress", "pending", "queued"}

def parse_iso(value) -> datetime | None: ...
    # tolerante: None/""/basura ⇒ None. Sufijo "Z" ⇒ UTC. Naive ⇒ se asume UTC
    # (mismo criterio que services/harness/telemetry.py: timestamps naive-UTC).

def day_key(dt: datetime) -> str: ...          # "YYYY-MM-DD" en UTC

def build_day_axis(now_utc: datetime, days: int = SERIES_DAYS) -> list[str]: ...
    # exactamente `days` claves, viejo→nuevo, terminando en day_key(now_utc)

def bucket_by_day(timestamps: list[str], axis: list[str]) -> list[int]: ...
    # cuenta por día; lo que cae fuera del eje se descarta

def aggregate_deploy_metrics(entries_by_app: dict[str, list[dict]], now_utc) -> dict: ...
    # v2 (C2) — ALGORITMO EXACTO, sin reimplementar DORA y sin inventar API.
    # Son DOS llamadas a services.deploy_planner.dora_metrics, cada una con un
    # propósito, y NINGÚN cálculo DORA propio:
    #
    #  (A) UNA llamada sobre la CONCATENACIÓN de los entries de todas las apps
    #      (`dora_metrics([e for lst in entries_by_app.values() for e in lst], now_utc)`).
    #      De ahí y SOLO de ahí salen:  deploys_7d, deploys_30d,
    #      change_failure_rate_30d y cfr_sample_30d.
    #      Por qué: sobre el total, el CFR ya es fallos/(fallos+éxitos) global — que es
    #      justo lo que se pide — sin promediar promedios y sin contar nada a mano.
    #
    #  (B) UNA llamada POR APP para los dos valores que la concatenación falsearía:
    #      - mttr_minutes_30d: promedio simple de los valores no-None de cada app
    #        (None si NINGUNA app tiene valor). NO se toma el de (A): en la
    #        concatenación, un fallo de la app X se "recuperaría" con un éxito de la
    #        app Y (dora_metrics busca el siguiente success del array ordenado por
    #        fecha, sin distinguir app: deploy_planner.py:328-339) ⇒ MTTR inventado.
    #      - last_deploy_at: MÁXIMO de los last_deploy_at por app (str ISO comparable).
    #
    # Devuelve además `locked_targets: list[tuple[str,str]]` (de deploy_store.is_locked)
    # y `last_failed_by_target: dict[tuple[str,str], dict]` para alimentar F1.2.

def aggregate_ci(runs: list[dict], now_utc) -> dict: ...
    # ci_runs_7d, ci_failures_7d, ci_running_now, y el detalle de la más reciente fallida

def derive_alerts(kpis: dict, ctx: dict, now_utc) -> list[dict]: ...
    # aplica la tabla F1.2 en el ORDEN de la tabla (danger primero); cada alerta
    # es {"id","tone","title","detail","section"}; textos en español llano.

def derive_status(alerts: list[dict], blocks: dict) -> str: ...

def build_recent(deploy_entries: list[dict], ci_runs: list[dict], limit=RECENT_LIMIT) -> list[dict]: ...

ALLOWED_WINDOW_DAYS = (7, 14, 30)   # cualquier otro valor ⇒ SERIES_DAYS (14)

def normalize_filters(app_id, project, window_days) -> dict: ...
    # Saneamiento ESTRICTO (nunca confía en el query string):
    #   app_id/project: str no vacío recortado, máx 200 chars, o None. Si no está en
    #     options.apps/options.projects ⇒ se DESCARTA a None (no se filtra por un valor
    #     inexistente y el eco `filters` dice None: el operador ve qué se aplicó de verdad).
    #   window_days: int en ALLOWED_WINDOW_DAYS, o SERIES_DAYS.

def build_overview(now_utc: datetime | None = None, app_id: str | None = None,
                   project: str | None = None, window_days: int = SERIES_DAYS) -> dict: ...
    # ÚNICO punto con efectos de lectura. Cada fuente va en su propio try/except:
    #   - flag apagada  ⇒ blocks[x] = {"available": False, "reason": "flag_off"}
    #   - lista vacía   ⇒ {"available": True,  "reason": "sin_datos"}
    #   - excepción     ⇒ {"available": False, "reason": "error_lectura"} y SIGUE
    # Nunca propaga la excepción: el endpoint es siempre 200.
    # `options` se computa SIEMPRE sobre el universo SIN filtrar (si no, al filtrar por
    # una app el selector se quedaría con una sola opción y no se podría volver).
    # El filtro se aplica ANTES de derivar KPIs, series, alertas y `recent`, para que
    # todo lo que se muestra corresponda al alcance elegido.
```

Lecturas exactas por bloque (no inventar APIs):

| bloque | flag que lo habilita | llamadas |
|--------|---------------------|----------|
| `deployments` | `STACKY_DEPLOYMENTS_ENABLED` | `deploy_store.list_apps()`; por app `deploy_store.read_ledger(app_id=..., limit=LEDGER_READ_LIMIT)`; `deploy_store.is_locked(app_id, target)`; `deploy_planner.dora_metrics(entries, now)` |
| `ci` | `STACKY_CI_RUN_LEDGER_ENABLED` | `ci_run_ledger.list_runs(project=None, limit=CI_READ_LIMIT)` |
| `connections` | `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` | **solo lectura del snapshot** vía `api.devops_connections.get_snapshot()` (ver F1.4) — **prohibido** llamar `connection_doctor.run_connection_check()` |
| `servers` | `STACKY_DEVOPS_SERVERS_ENABLED` | `server_registry.list_servers()` |

#### F1.4 — Exponer el snapshot de conexiones sin dispararlo

`api/devops_connections.py` guarda el snapshot en el módulo (`_SNAPSHOT`, **`:20`**, con
`_SNAPSHOT_LOCK` en `:21` — v2, C7: el v1 decía `:22`). Agregar allí una función de lectura pura
(aditiva, no cambia rutas ni toca `_guard()`, así que **no** hereda el 404 del doctor: el bloque
`connections` decide su disponibilidad leyendo la flag, como dice la tabla de F1.3):

```python
def get_snapshot() -> dict | None:
    """Plan 239 — lectura del último snapshot SIN correr el chequeo (HITL intacto)."""
    with _SNAPSHOT_LOCK:
        return _SNAPSHOT
```

#### F1.5 — Ruta: `backend/api/devops.py`

Agregar **después** de `devops_bootstrap_route()` (`:81-120`):

```python
@bp.get("/overview")
def devops_overview_route():
    """Plan 239 — Resumen del panel (read-only). 404 si el cockpit está OFF.
    SIEMPRE 200 cuando está ON: la degradación es POR BLOQUE, nunca por error.

    Filtros opcionales (query string): ?app_id= &project= &window_days=7|14|30.
    Un valor inválido NO es un 400: se descarta y el payload lo declara en `filters`
    (la pantalla debe poder abrirse siempre, aunque el link venga con basura)."""
    if not bool(getattr(_config.config, "STACKY_DEVOPS_COCKPIT_ENABLED", False)):
        abort(404)
    from services.devops_overview import build_overview  # import perezoso (patrón de la casa)
    try:
        window_days = int(request.args.get("window_days", "14"))
    except ValueError:
        window_days = 14
    return jsonify(build_overview(
        app_id=request.args.get("app_id") or None,
        project=request.args.get("project") or None,
        window_days=window_days,
    ))
```

#### F1.6 — Tests PRIMERO

**Crear `backend/tests/test_plan239_devops_overview_service.py`** (fixtures inline, sin tocar disco real
—monkeypatch de `deploy_store.read_ledger`/`list_apps`, `ci_run_ledger.list_runs`,
`devops_connections.get_snapshot`, `server_registry.list_servers`—, `now_utc` **inyectado**, jamás
`datetime.now()` real):

```
test_parse_iso_tolerante                   -> None/""/"basura"/naive/Z ⇒ resultado esperado
test_build_day_axis_14_dias                -> len==14, orden viejo→nuevo, último == hoy
test_bucket_by_day_descarta_fuera_de_eje   -> un timestamp de hace 40 días no suma
test_aggregate_deploy_consolidado          -> 2 apps: deploys_7d suma; CFR sobre el TOTAL, no promedio.
                                              Caso testigo (v2, C2): app A 1 fallo/1 deploy (CFR 1.0) y
                                              app B 0 fallos/3 deploys (CFR 0.0) ⇒ el consolidado es
                                              0.25, NO 0.5 (que es el promedio de promedios prohibido)
test_aggregate_mttr_no_cruza_apps          -> v2 (C2): fallo en app A y éxito posterior en app B ⇒ el
                                              MTTR de A sigue None; NO se "recupera" con el de B
test_aggregate_last_deploy_at_es_el_maximo -> 2 apps con fechas distintas ⇒ gana la más nueva
test_aggregate_cfr_sample_se_propaga       -> cfr_sample_30d del payload == el de la llamada (A)
test_aggregate_deploy_sin_datos            -> CFR y MTTR son None (NUNCA 0.0) y cfr_sample_30d == 0
test_aggregate_ci_cuenta_7d_y_fallos       -> runs_7d/failures_7d/running_now correctos
test_alert_deploy_last_failed              -> último entry failed ⇒ alerta danger, section "despliegues"
test_alert_deploy_last_failed_ignora_running -> v2 (C6): último entry con finished_at None (deploy en
                                              curso) sobre un fallo previo ⇒ la alerta SIGUE mirando el
                                              último TERMINADO; y un `action: "rollback"` exitoso
                                              posterior a un deploy fallido NO apaga la alerta
test_alert_deploy_failure_rate_umbral      -> CFR 0.30 con cfr_sample_30d 3 dispara; 0.29 no; 0.5 con
                                              cfr_sample_30d 2 no (muestra insuficiente)
test_alert_mttr_high                       -> 240 dispara, 239 no
test_alert_deploy_stale_21_dias            -> 22 días dispara, 20 no
test_alert_ci_failures_dos                 -> 2 dispara, 1 no
test_alert_ci_stuck_120_min                -> running de 121 min dispara, 119 no
test_alert_connections_down                -> 1 chequeo no-OK ⇒ danger
test_alert_connections_never_run           -> snapshot None ⇒ info "connections_never"
test_alert_no_servers                      -> servers_total 0 ⇒ info
test_alerts_orden_danger_primero           -> el primer elemento es tone danger si existe
test_status_danger_gana_a_warning
test_status_ok_solo_con_datos
test_status_unknown_sin_datos              -> todos los bloques apagados ⇒ "unknown" (KPI-6)
test_blocks_declare_flag_off               -> flag CI off ⇒ blocks.ci.available False + reason flag_off (KPI-6)
test_block_error_lectura_no_propaga        -> read_ledger que lanza ⇒ reason "error_lectura" y el resto vive
test_recent_orden_desc_y_tope_12           -> 20 eventos ⇒ 12, del más nuevo al más viejo
test_recent_mezcla_deploy_y_ci             -> ambas kinds presentes con su section correcta
test_series_cuatro_arrays_de_14            -> las 4 series tienen exactamente 14 enteros
# ── Filtros (F1.2b) ──
test_normalize_window_days_permitidos      -> 7/14/30 pasan; 1, 999, "abc", None, -7 ⇒ 14
test_normalize_app_id_inexistente_se_descarta -> app_id "no-existe" ⇒ filters.app_id None
test_normalize_recorta_y_topea             -> " app " ⇒ "app"; 300 chars ⇒ None
test_filtro_app_id_recorta_kpis            -> 2 apps, filtro por 1 ⇒ deploys_7d solo de esa
test_filtro_project_recorta_ci             -> 2 proyectos, filtro por 1 ⇒ ci_runs_7d solo de ese
test_filtro_recorta_recent_y_alertas       -> `recent` y `alerts` solo del alcance elegido
test_options_no_se_recorta_con_el_filtro   -> filtrando por 1 app, options.apps sigue con las 2
test_window_days_30_da_series_de_30        -> len(days)==30 y las 4 series también
test_filters_es_eco_de_lo_APLICADO         -> pedir app_id inválido ⇒ filters.app_id None (no el pedido)
```

**Crear `backend/tests/test_plan239_devops_overview_endpoint.py`**:

```
test_overview_404_si_cockpit_off           -> flag OFF ⇒ 404
test_overview_200_con_todo_apagado         -> cockpit ON, resto OFF ⇒ 200, status "unknown", 4 blocks
test_overview_contrato_de_claves           -> el payload trae generated_at/status/kpis/series/alerts/recent/blocks
test_overview_no_ejecuta_remoto            -> monkeypatch de services.remote_exec.run_deploy_step y de
                                              services.connection_doctor.run_connection_check que lanzan
                                              AssertionError si alguien los llama ⇒ el endpoint responde 200 (KPI-7)
test_overview_no_abre_red                  -> monkeypatch de requests.request que lanza ⇒ 200 (KPI-7)
test_overview_no_invoca_llm                -> monkeypatch del invocador local que lanza ⇒ 200 (KPI-7)
test_overview_acepta_filtros               -> ?app_id=x&project=y&window_days=30 ⇒ 200 y filters lo refleja
test_overview_window_days_basura_no_es_400 -> ?window_days=abc ⇒ 200 con filters.window_days == 14
test_overview_app_id_inexistente_no_es_400 -> ?app_id=zzz ⇒ 200 con filters.app_id null
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_service.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_endpoint.py -q
```

**Criterio de aceptación (binario).** Ambos comandos verdes. `curl -s localhost:5000/api/devops/overview`
devuelve 200 con las 7 claves de primer nivel incluso en una instalación virgen (sin apps, sin CI, sin
servidores) y con `"status": "unknown"`.

**Flag.** `STACKY_DEVOPS_COCKPIT_ENABLED` (default ON). El endpoint es 404 con la flag OFF.

**Impacto por runtime.** Ninguno: agrega ledgers locales que son runtime-agnósticos (registran CI y
despliegues, no corridas de agente). **Codex / Claude Code / Copilot: payload idéntico.** Fallback: no
aplica (no hay rama por runtime).

**Trabajo del operador: ninguno.**

---

### F2 — Frontend: modelo puro `overviewModel.ts`

**Objetivo (1 frase).** Convertir el payload de F1 en filas de KPI, tonos y etiquetas listas para
pintar, con funciones puras testeables sin jsdom.
**Valor.** Cero lógica en el JSX, tests baratos, y el "n/d" honesto centralizado en un solo lugar.

> **Gotcha estructural obligatorio:** `@testing-library/react` y `jsdom` **NO están** en
> `frontend/package.json`. Prohibido escribir tests que rendericen componentes. Todos los tests de este
> plan son sobre funciones puras (`*.ts`) o inspección de archivos con `fs`+regex (el idioma que ya usa
> `pages/__tests__/DevOpsPage.test.ts`).

**Crear `frontend/src/components/devops/overviewModel.ts`:**

```ts
/** Plan 239 F2 — modelo puro del Resumen DevOps. Sin React, sin fetch, sin DOM. */
export type OverviewTone = "success" | "warning" | "danger" | "info" | "neutral";
export type OverviewStatus = "ok" | "warning" | "danger" | "unknown";

export interface OverviewPayload { /* espejo EXACTO del contrato F1.1 */ }
export interface KpiRow { key: string; label: string; value: string; hint?: string; tone?: OverviewTone; }

/** null/undefined ⇒ "n/d" SIEMPRE (precedente formatUsd de CostKpiCards, plan 142 F6).
 *  Prohibido devolver "0" para un dato ausente. */
export function fmtInt(n: number | null | undefined): string;
export function fmtPct(v: number | null | undefined): string;          // 0.183 ⇒ "18%"
export function fmtMinutes(v: number | null | undefined): string;       // 90 ⇒ "1 h 30 min"; 37.5 ⇒ "38 min"
export function fmtWhen(iso: string | null | undefined, nowMs: number): string;  // ⇒ "hace 2 días" | "n/d"

/** 8 KPIs en ORDEN FIJO: deploys_7d, change_failure_rate_30d, mttr_minutes_30d,
 *  last_deploy_at, ci_runs_7d, ci_failures_7d, connections, servers_total. */
export function buildKpiRows(p: OverviewPayload, nowMs: number): KpiRow[];

export function statusLabel(s: OverviewStatus): { text: string; tone: OverviewTone };
  // ok      ⇒ { "Sin novedades",              "success" }
  // warning ⇒ { "Requiere atención",          "warning" }
  // danger  ⇒ { "Hay algo roto",              "danger"  }
  // unknown ⇒ { "Sin datos suficientes",      "neutral" }   <- NUNCA "todo bien"

/** Texto de los bloques apagados: "CI: bitácora apagada · Conexiones: sin chequear".
 *  Devuelve "" si los 4 bloques están disponibles con datos. */
export function blocksNote(p: OverviewPayload): string;

/** Polyline SVG normalizada a un viewBox 100x30. Serie vacía o toda en cero ⇒ "" (no dibuja). */
export function sparkPoints(series: number[], width = 100, height = 30): string;

/** Resumen textual de la serie para lectores de pantalla (la sparkline va aria-hidden). */
export function sparkAltText(label: string, series: number[], days: string[]): string;

/** [ADICIÓN ARQUITECTO] (v2) — El resumen del cockpit como texto llano, para pegarlo en
 *  un ticket, un chat o el standup. Función PURA: recibe el payload, devuelve un string.
 *  Formato EXACTO (líneas separadas por "\n", sin markdown, sin emojis, ancho libre):
 *
 *    DevOps — <statusLabel().text> · <generated_at en ISO>
 *    Alcance: <app o "todas las aplicaciones"> · <proyecto o "todos los proyectos de CI"> · <N> días
 *    KPIs: <label>: <value> (una por línea, las MISMAS 8 filas y los MISMOS textos de buildKpiRows,
 *          "n/d" incluido — el texto copiado y la pantalla NUNCA pueden discrepar)
 *    Avisos: <N>
 *      - [Crítico|Atención|Info] <title> — <detail>          (o "  (ninguno)")
 *    Fuentes sin datos: <blocksNote(p) o "ninguna">
 *
 *  Reglas duras: (1) reusa buildKpiRows/statusLabel/blocksNote — prohibido reformatear
 *  a mano, o el texto miente cuando la pantalla dice otra cosa; (2) jamás imprime "0"
 *  por un dato ausente; (3) no incluye logs, rutas ni nombres de host: el payload no
 *  los trae y esto NO los va a buscar. */
export function buildOverviewClipboardText(p: OverviewPayload, nowMs: number): string;
```

**Test PRIMERO — crear `frontend/src/components/devops/overviewModel.test.ts`:**

```
fmtInt/fmtPct/fmtMinutes: null y undefined ⇒ "n/d"; 0 ⇒ "0" (0 SÍ es un dato)
fmtPct redondea a entero: 0.183 ⇒ "18%"
fmtMinutes: 37.5 ⇒ "38 min"; 90 ⇒ "1 h 30 min"; 0 ⇒ "0 min"
fmtWhen: mismo día ⇒ "hoy"; 1 día ⇒ "ayer"; 2 ⇒ "hace 2 días"; null ⇒ "n/d"
buildKpiRows devuelve 8 filas en el orden fijo declarado
buildKpiRows con payload vacío ⇒ 8 filas y ninguna dice "0" para un dato null
buildKpiRows: change_failure_rate_30d >= 0.30 ⇒ tone "danger"; < 0.10 ⇒ "success"
statusLabel("unknown") NO contiene "bien" ni "OK"        <- guardarraíl anti-falso-verde
blocksNote lista solo los bloques no disponibles y "" cuando están todos
sparkPoints([]) === "" ; sparkPoints([0,0,0]) === "" ; sparkPoints([1,2]) tiene 2 pares "x,y"
sparkPoints es monótona en x y respeta el viewBox (0<=x<=100, 0<=y<=30)
sparkAltText menciona el total y el máximo
# ── [ADICIÓN ARQUITECTO] buildOverviewClipboardText (v2, KPI-12) ──
buildOverviewClipboardText_incluye_estado_y_fecha    -> 1ª línea trae statusLabel().text y generated_at
buildOverviewClipboardText_incluye_las_8_filas       -> las 8 filas de buildKpiRows aparecen con su label
buildOverviewClipboardText_declara_el_alcance        -> con filters {app_id:null,project:null,window_days:14}
                                                        dice "todas las aplicaciones" y "14 días"
buildOverviewClipboardText_lista_las_alertas         -> 2 alertas ⇒ 2 viñetas con su tono en español
buildOverviewClipboardText_sin_alertas               -> imprime "(ninguno)", no una lista vacía
test_clipboard_no_miente_con_datos_ausentes          -> payload con CFR/MTTR null ⇒ el texto dice "n/d"
                                                        y NO contiene " 0" para esos KPIs (KPI-12)
test_clipboard_status_unknown_no_dice_bien           -> status "unknown" ⇒ el texto no contiene
                                                        "bien" ni "OK" (mismo guardarraíl que statusLabel)
```

**Comando exacto.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/components/devops/overviewModel.test.ts
```
> **Gotcha:** correr vitest **por archivo**. La corrida completa tiene contaminación cross-file conocida.

**Criterio de aceptación (binario).** El comando verde con **todos** los casos listados, y
`npx tsc --noEmit` verde.

**Flag.** `STACKY_DEVOPS_COCKPIT_ENABLED` (el módulo solo lo consume la sección nueva).

**Impacto por runtime.** Ninguno (TypeScript puro). Los 3 runtimes: idéntico. Sin fallback necesario.

**Trabajo del operador: ninguno.**

---

### F3 — Sección Resumen (`DevOpsOverviewSection.tsx`)

**Objetivo (1 frase).** La pantalla de decisión: estado global, 8 KPIs, alertas con salto a la sección
que las resuelve, tendencia, actividad reciente unificada y los 3 filtros de alcance (aplicación,
proyecto de CI, ventana).
**Valor.** Responde *"¿está todo bien?"* en un vistazo, que hoy no se puede responder sin abrir 4 pestañas.

**Cliente de API — editar `frontend/src/api/endpoints.ts`**, dentro del objeto `DevOps` (después de
`connectionsHealth`, `:3742-3744`):

```ts
  /** Plan 239 — Resumen agregado del panel (read-only). 404 si el cockpit está OFF.
   *  Filtros opcionales; un valor inválido no falla (el backend lo descarta y lo declara). */
  overview: (f?: { appId?: string | null; project?: string | null; windowDays?: number }) => {
    const sp = new URLSearchParams();
    if (f?.appId) sp.set("app_id", f.appId);
    if (f?.project) sp.set("project", f.project);
    if (f?.windowDays) sp.set("window_days", String(f.windowDays));
    const qs = sp.toString();
    return api.get<OverviewPayload>(`/api/devops/overview${qs ? `?${qs}` : ""}`);
  },
```
> **Gotcha `api.get` (memoria):** `api.get` **lanza** en cualquier non-2xx (incluido 404). Por eso la
> sección envuelve la query con `retry: false` y muestra el estado vacío si falla — nunca deja la
> pantalla en blanco ni intenta leer el body del error desde `.then()`.

**Crear `frontend/src/components/devops/DevOpsOverviewSection.tsx`** — **CERO `style={{`** (el ratchet lo
exige: archivo nuevo con deuda 0) y cero hex:

```tsx
/** Plan 239 F3 — Sección Resumen del cockpit DevOps. SOLO LECTURA:
 *  ningún botón de esta pantalla ejecuta nada; los de las alertas NAVEGAN. */
import { useQuery } from "@tanstack/react-query";
import { Card, StatusChip, SectionHeader, Skeleton, Button, Select } from "../ui";
import { DevOps } from "../../api/endpoints";
import { useLocalStorageState } from "../../hooks/useLocalStorageState";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { buildKpiRows, statusLabel, blocksNote, sparkPoints, sparkAltText, fmtWhen } from "./overviewModel";
import styles from "../../pages/DevOpsCockpit.module.css";

export function DevOpsOverviewSection({ ctx }: { ctx: DevOpsSectionContext }) {
  // Filtros persistidos (sobreviven a la sesión, sin backend ni config: hook de la casa).
  const [appId, setAppId] = useLocalStorageState<string | null>("stacky.devops.overview.appId", null);
  const [project, setProject] = useLocalStorageState<string | null>("stacky.devops.overview.project", null);
  const [windowDays, setWindowDays] = useLocalStorageState<number>("stacky.devops.overview.windowDays", 14);

  const q = useQuery({
    // Los filtros van en la queryKey: react-query cachea por alcance y no mezcla resultados.
    queryKey: ["devops-overview", appId, project, windowDays],
    queryFn: () => DevOps.overview({ appId, project, windowDays }),
    retry: false,
    // F6: la sección solo sondea cuando es la visible; 60 s (dato de minutos, no de segundos).
    refetchInterval: ctx.visible === false ? false : 60_000,
  });

  if (q.isLoading) return <div className={styles.kpiGrid}>{/* 8 <Skeleton /> */}</div>;
  if (q.isError || !q.data) return <p className={styles.empty}>No se pudo leer el resumen. …</p>;

  const p = q.data;
  const st = statusLabel(p.status);
  const nowMs = Date.parse(p.generated_at);   // reloj del SERVIDOR (no del navegador)
  const kpis = buildKpiRows(p, nowMs);
  const note = blocksNote(p);

  return (
    <section>
      <SectionHeader
        title={<span className={styles.titleRow}>Resumen <StatusChip tone={st.tone}>{st.text}</StatusChip></span>}
        subtitle={`Datos al ${fmtWhen(p.generated_at, Date.now())}. Solo lectura.`}
        actions={
          <>
            {/* Filtros: 3 Select de la primitiva del plan 162. `value` sale del ECO
                del backend (p.filters), no del estado local: si el backend descartó
                un filtro inválido, el selector muestra la verdad, no la intención. */}
            <Select aria-label="Aplicación" value={p.filters.app_id ?? ""}
                    onChange={(e) => setAppId(e.target.value || null)}>
              <option value="">Todas las aplicaciones</option>
              {p.options.apps.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
            <Select aria-label="Proyecto de CI" value={p.filters.project ?? ""}
                    onChange={(e) => setProject(e.target.value || null)}>
              <option value="">Todos los proyectos</option>
              {p.options.projects.map((pr) => <option key={pr} value={pr}>{pr}</option>)}
            </Select>
            <Select aria-label="Ventana de la tendencia" value={String(p.filters.window_days)}
                    onChange={(e) => setWindowDays(Number(e.target.value))}>
              <option value="7">7 días</option>
              <option value="14">14 días</option>
              <option value="30">30 días</option>
            </Select>
            <Button variant="secondary" size="sm" onClick={() => q.refetch()}>Actualizar</Button>
          </>
        }
      />

      {/* KPIs */}
      <div className={styles.kpiGrid}>
        {kpis.map((k) => (
          <Card key={k.key} padding="sm">
            <div className={styles.kpiLabel}>{k.label}</div>
            <div className={styles.kpiValue}>{k.value}</div>
            {k.hint && <div className={styles.kpiHint}>{k.hint}</div>}
          </Card>
        ))}
      </div>

      {/* Alertas: cada una NAVEGA, ninguna EJECUTA */}
      {p.alerts.length > 0 && (
        <div className={styles.alerts}>
          {p.alerts.map((a) => (
            <div key={a.id} className={styles.alertRow}>
              <StatusChip tone={a.tone}>{a.tone === "danger" ? "Crítico" : a.tone === "warning" ? "Atención" : "Info"}</StatusChip>
              <div className={styles.alertBody}>
                <div className={styles.alertTitle}>{a.title}</div>
                <div className={styles.alertDetail}>{a.detail}</div>
              </div>
              {ctx.setActiveSection && (
                <Button variant="secondary" size="sm" onClick={() => ctx.setActiveSection!(a.section)}>
                  Ir a la sección
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tendencia: SVG puro, sin dependencias nuevas. El título usa la ventana APLICADA. */}
      <SectionHeader title={`Tendencia (${p.filters.window_days} días)`} />
      <svg className={styles.spark} viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
        <polyline className={styles.sparkLine} points={sparkPoints(p.series.deploys_by_day)} />
        <polyline className={styles.sparkFail} points={sparkPoints(p.series.ci_failures_by_day)} />
      </svg>
      <p className={styles.kpiHint}>
        {sparkAltText("Despliegues", p.series.deploys_by_day, p.series.days)}{" · "}
        {sparkAltText("Fallos de CI", p.series.ci_failures_by_day, p.series.days)}
      </p>

      {/* Actividad reciente unificada */}
      <SectionHeader title="Actividad reciente" />
      {p.recent.length === 0
        ? <p className={styles.empty}>Todavía no hay despliegues ni corridas de CI registradas.</p>
        : <div className={styles.timeline}>
            {p.recent.map((e, i) => (
              <div key={`${e.at}-${i}`} className={styles.eventRow}>
                <span className={styles.eventWhen}>{fmtWhen(e.at, nowMs)}</span>
                <span>{e.title}</span>
                <StatusChip tone={e.tone}>{e.status}</StatusChip>
              </div>
            ))}
          </div>}

      {note && <p className={styles.blocksNote}>Fuentes sin datos: {note}</p>}
    </section>
  );
}
```

**Registrar la sección — editar `frontend/src/pages/DevOpsPage.tsx`.** Import junto a los otros
(después de `:93`) y **primera** entrada de `DEVOPS_SECTIONS` (antes de `pipelines`, `:98`):

```tsx
  // Plan 239 — Resumen: aterrizaje del cockpit. healthKey cockpit_enabled ⇒ con la
  // flag OFF la pestaña se atenúa y el shell v2/v1 sigue aterrizando en Pipelines.
  {
    id: 'resumen',
    label: 'Resumen',
    group: 'resumen',
    summary: 'Estado de despliegues, CI y conexiones en una pantalla.',
    healthKey: 'cockpit_enabled',
    gateFlagKey: 'STACKY_DEVOPS_COCKPIT_ENABLED',
    gateMessage: 'El Resumen del panel DevOps necesita la flag STACKY_DEVOPS_COCKPIT_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <DevOpsOverviewSection ctx={ctx} />,
  },
```

#### F3.4 — Aterrizaje correcto (v2, C1 — **BLOQUEANTE del v1: sin esto el panel queda EN BLANCO**)

El v1 decía "reemplazar `useState(DEVOPS_SECTIONS[0].id)` por `useState(() => resolveLandingSection(…))`".
**Eso no alcanza y además no funciona.** Dos defectos verificados en el código el 2026-07-25:

1. **`mountedIds` no sigue al aterrizaje.** `DevOpsPage.tsx:190` siembra
   `useState<Set<string>>(new Set([DEVOPS_SECTIONS[0].id]))` y el outlet corta con
   `if (!mountedIds.has(s.id)) return null;` (`:324`). Si `activeId` resuelve a **cualquier** id distinto
   del primero del array —deep-link `/devops/despliegues`, `pinned`, o cockpit OFF que cae a
   `pipelines`— la sección activa **no está montada** y la única montada está oculta con
   `display:none` ⇒ **el panel se ve vacío** hasta que el operador hace clic en una pestaña.
   El v1 no tocaba `:190` en ninguna fase.
2. **El inicializador perezoso corre demasiado temprano.** `useState(() => …)` se evalúa en el **primer
   render**, y en ese momento `healthQuery.data` todavía es `undefined` (el early-return de `:243`
   muestra "Cargando salud DevOps..."); el inicializador **no vuelve a correr** cuando la salud llega.
   Resultado: `cockpitOn` sería `false` siempre y el panel aterrizaría en `pipelines` **incluso con el
   cockpit ON** ⇒ **KPI-1 falla**, que es el KPI insignia del plan.

**Fix (dos ediciones, ambas obligatorias en esta fase):**

**(a) Guardarraíl mecánico en el outlet — 1 línea, mata la clase de error para siempre.**
En `DevOpsPage.tsx:324`:

```diff
-        if (!mountedIds.has(s.id)) return null;
+        // Plan 239 F3.4 — invariante: la sección ACTIVA siempre se renderiza, la
+        // monte quien la monte. Sin esto, cualquier camino que fije activeId sin
+        // pasar por handleTabClick (deep-link, pin, aterrizaje) deja el panel en blanco.
+        if (!mountedIds.has(s.id) && s.id !== activeId) return null;
```

**(b) Aterrizaje aplicado UNA vez, cuando la salud ya llegó.** Insertar **después** de `handleTabClick`
(`:227-230`, para que la const ya esté definida) — **no** cambiar el `useState` de `:188` ni el de `:190`,
que quedan como están:

```tsx
  // Plan 239 F3.4 — aterrizaje resuelto una sola vez, con la salud REAL en la mano.
  // Usa handleTabClick (no setActiveId) a propósito: es el único lugar que mantiene
  // la invariante C10 "activeId ∈ mountedIds".
  const landingApplied = useRef(false);
  useEffect(() => {
    if (landingApplied.current) return;
    if (!healthQuery.data) return;            // esperar la salud; jamás adivinarla
    landingApplied.current = true;
    handleTabClick(resolveLandingSection({
      sections: DEVOPS_SECTIONS,
      health: healthQuery.data as Record<string, unknown>,
      subTab,                                  // F5: null hasta que F5.2 cablee la prop
      pinned,                                  // F5: null hasta que F5.3 agregue el pin
      cockpitOn: healthQuery.data.cockpit_enabled === true,
    }));
  }, [healthQuery.data]);
```

> **Orden entre F3 y F5.** `resolveLandingSection` se especifica en F5.1. En F3 se implementa **ya** con
> su firma final; `subTab` y `pinned` entran como `null` hasta que F5 los cablee. Así F3 queda verde sola
> y F5 no reescribe nada, solo pasa dos valores que hoy son `null`.

**Casos de test que este fix agrega.** Van en **`pages/__tests__/DevOpsPage.test.ts`** (que **ya existe**),
no en `DevOpsCockpitRegression.test.ts` — ese archivo lo crea F4, que corre **después**, y un plan no
puede pedir tests en un archivo que todavía no existe. Están listados abajo, junto con el resto de los
casos de F3. F8 los vuelve a verificar en `DevOpsCockpitClosure.test.ts` a propósito (redundancia
barata: el cierre de un bloqueante no debería depender de un solo archivo de test).

#### F3.5 — [ADICIÓN ARQUITECTO] (v2) "Copiar resumen": del vistazo al reporte, en 1 clic

**El hueco que cierra.** El cockpit responde *"¿está todo bien?"*, pero en cuanto la respuesta es "no",
el operador tiene que **transcribir a mano** los números a un ticket de ADO, a un chat o al standup —
que es exactamente el trabajo manual que este plan dice eliminar. Un botón de copiar convierte la
pantalla de decisión en una pantalla **reportable**, sin sacar al humano del lazo: **copia solo si él
hace clic**, y no publica, no crea tickets ni manda mensajes (guardarraíles 3 y 10 intactos).

**Reuso total, código nuevo mínimo.** No se escribe ni un servicio de portapapeles: el plan 194 ya dejó
`components/CopyAsButton.tsx` (props `{ options: CopyAsOption[] }`, con `label` + `build: () => string`),
que ya resuelve la flag `STACKY_COPY_EXPORT_ENABLED`, el toast de la casa, el fallback a `execCommand` y
el ratchet `copyDebtRatchet` que prohíbe tocar `navigator.clipboard` a mano. Precedente **dentro de este
mismo panel**: `components/devops/DeploymentsSection.tsx:22,234` ya usa `copyService`. Lo único nuevo es
el builder **puro** `buildOverviewClipboardText` (declarado en F2, testeado en F2 sin jsdom).

**Cableado — en `DevOpsOverviewSection.tsx`, dentro de `actions` del `SectionHeader`**, antes del botón
"Actualizar":

```tsx
import CopyAsButton from "../CopyAsButton";           // Plan 194 F3
// …
<CopyAsButton options={[{ label: "Texto", build: () => buildOverviewClipboardText(p, nowMs) }]} />
```

- `build` es perezoso (se evalúa recién al click), así que copia **lo que está en pantalla en ese
  momento**, con el alcance de filtros aplicado.
- Si `STACKY_COPY_EXPORT_ENABLED` está OFF, `CopyAsButton` **se auto-oculta** (devuelve `null`): no hay
  que gatearlo a mano ni agregar una flag nueva.

**Test.** Los casos de `buildOverviewClipboardText_*` de F2 (función pura) **más** dos casos fs+regex en
`DevOpsPage.test.ts`:
```
test_overview_usa_CopyAsButton            -> DevOpsOverviewSection.tsx importa CopyAsButton (plan 194)
test_overview_no_toca_el_portapapeles_a_mano -> el archivo NO contiene "navigator.clipboard"
```

**Restricciones (verificadas una por una).** 3 runtimes: es TypeScript puro sobre un payload
runtime-agnóstico ⇒ idéntico en Codex / Claude Code / Copilot, sin fallback necesario. Trabajo del
operador: **ninguno** (aparece solo, sin configurar nada; la flag del 194 ya existe y ya está ON).
HITL: copia **solo** por clic explícito; no envía nada a ningún lado. No degrada: cero dependencias
nuevas, cero red, cero `style={{`. Reuso: 100% plan 194 + plan 138.

**Test PRIMERO — extender `frontend/src/pages/__tests__/DevOpsPage.test.ts`** (existe; mismo idioma
fs+regex) con estos casos:

```
test_resumen_es_la_primera_seccion         -> el orden textual de DEVOPS_SECTIONS empieza en id 'resumen'
test_resumen_tiene_gate_completo           -> healthKey + gateFlagKey + gateMessage presentes
test_overview_section_sin_estilos_inline   -> DevOpsOverviewSection.tsx no contiene "style={{"
test_overview_section_no_ejecuta            -> el archivo NO menciona execute/rollback/trigger/deploy(
test_aterrizaje_no_queda_gateado           -> DevOpsPage.tsx ya no usa DEVOPS_SECTIONS[0].id crudo
test_filtros_usan_el_eco_del_backend       -> los 3 Select leen p.filters.*, NO el estado local (KPI-11)
test_filtros_en_la_querykey                -> la queryKey incluye appId, project y windowDays
test_filtros_persisten                     -> usa useLocalStorageState con las 3 keys stacky.devops.overview.*
# ── F3.4 — aterrizaje (v2, C1: BLOQUEANTE) ──
test_outlet_renderiza_siempre_la_activa    -> DevOpsPage.tsx tiene el guard `s.id !== activeId` en el
                                              return null del outlet (sin esto: pantalla en blanco)
test_aterrizaje_no_va_en_useState          -> grep NEGATIVO: resolveLandingSection NO aparece dentro de
                                              useState( (el inicializador corre antes de la salud)
test_aterrizaje_espera_la_salud            -> existe el useEffect con landingApplied y con la guarda
                                              `if (!healthQuery.data) return`
test_aterrizaje_usa_handleTabClick         -> el efecto llama handleTabClick, NO setActiveId (invariante C10)
# ── F3.5 — [ADICIÓN ARQUITECTO] copiar resumen (v2, KPI-12) ──
test_overview_usa_CopyAsButton             -> DevOpsOverviewSection.tsx importa CopyAsButton (plan 194)
test_overview_no_toca_el_portapapeles_a_mano -> el archivo NO contiene "navigator.clipboard"
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/pages/__tests__/DevOpsPage.test.ts
npx vitest run src/components/devops/overviewModel.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts    # v2 (F3.5) — la copia va por copyService
npx tsc --noEmit
```

**Criterio de aceptación (binario).** Los 5 comandos verdes. En particular `uiDebtRatchet` **sin**
`UI_DEBT_REGEN`: prueba que los archivos nuevos nacen con deuda 0 (KPI-8 parcial); y `copyDebtRatchet`
verde prueba que F3.5 no tocó `navigator.clipboard` a mano.

**Flag.** `STACKY_DEVOPS_COCKPIT_ENABLED` (default ON) — vía `healthKey: 'cockpit_enabled'`, así que con
la flag OFF la pestaña muestra el `FlagGateBanner` estándar en vez de la sección.

**Impacto por runtime.** Ninguno; la sección pinta datos runtime-agnósticos.
**Codex / Claude Code / Copilot: idéntico.** Fallback: si el endpoint no está (deploy viejo, 404), la
query falla con `retry:false` y se muestra el estado vacío — nunca pantalla en blanco.

**Trabajo del operador: ninguno.**

---

### F4 — Shell v3: navegación agrupada de dos niveles

**Objetivo (1 frase).** Reemplazar la fila plana de 9 pestañas por 4 grupos (fila primaria) + las
secciones del grupo activo (fila secundaria), con las secciones gateadas recogidas en un desplegable.
**Valor.** Baja de 9 a ≤4 decisiones visibles simultáneas y libera el espacio noble que hoy ocupan las
pestañas con flag apagada.

#### F4.1 — Helpers puros: `frontend/src/pages/devopsCockpitShell.ts` (archivo NUEVO)

```ts
/** Plan 239 F4 — helpers puros del shell v3. Sin DOM, sin React. */
import type { DevOpsSection } from "./DevOpsPage";

export type DevOpsGroupId = "resumen" | "operar" | "construir" | "diagnosticar";
export const DEFAULT_GROUP: DevOpsGroupId = "operar";   // sección sin `group` ⇒ acá (contrato C20)

export interface GroupDef { id: DevOpsGroupId; label: string; hint: string; }
export const DEVOPS_SECTION_GROUPS: GroupDef[] = [
  { id: "resumen",      label: "Resumen",      hint: "Estado general y avisos" },
  { id: "operar",       label: "Operar",       hint: "Desplegar, ambientes, publicaciones y servidores" },
  { id: "construir",    label: "Construir",    hint: "Pipelines y variables" },
  { id: "diagnosticar", label: "Diagnosticar", hint: "PRs, consola remota y agente DevOps" },
];

export function groupOf(s: Pick<DevOpsSection, "group">): DevOpsGroupId;   // s.group ?? DEFAULT_GROUP

/** Secciones del grupo, en el orden de DEVOPS_SECTIONS. */
export function sectionsOfGroup(sections: DevOpsSection[], g: DevOpsGroupId): DevOpsSection[];

/** true si health[section.healthKey] !== true (idéntico al gate del outlet, DevOpsPage.tsx:327). */
export function isGated(s: Pick<DevOpsSection,"healthKey">, health: Record<string, unknown>): boolean;

/** Partición para la barra: las gateadas salen de la fila primaria y van al desplegable.
 *  Regla: si TODAS las secciones de un grupo están gateadas, el grupo NO se oculta —
 *  se muestra atenuado (descubribilidad: el operador tiene que poder llegar al banner). */
export function partitionForBar(sections: DevOpsSection[], health: Record<string, unknown>):
  { visibleByGroup: Record<DevOpsGroupId, DevOpsSection[]>; gated: DevOpsSection[] };

/** Grupos para la primitiva Tabs (siempre los 4, con badge de cantidad si >1 sección visible). */
export function buildGroupTabs(groups: GroupDef[]): { id: string; label: string }[];

/** Grupo que contiene a la sección activa (para que la fila primaria marque el correcto). */
export function activeGroupOf(sections: DevOpsSection[], activeId: string): DevOpsGroupId;

/** Línea de estado OPERACIONAL del header (reemplaza a buildAwareness del plan 119, que
 *  contaba flags). Ahora: servidor activo + estado del overview + fecha del último deploy.
 *  `overviewStatus` null ⇒ no se inventa nada: se omite el segmento. */
export function buildOperationalMeta(args: {
  selectedAlias: string | null;
  overviewStatus: "ok" | "warning" | "danger" | "unknown" | null;
  lastDeployAt: string | null;
  nowMs: number;
}): { text: string; tone: "ok" | "warn" | "bad" | "faint" }[];
```

#### F4.2 — Asignación de grupos en `DEVOPS_SECTIONS` (editar `DevOpsPage.tsx`)

Agregar `group:` a las 10 entradas (1 nueva + 9 existentes). **Es lo único que cambia de cada entrada.**

| `id` | `group` |
|------|---------|
| `resumen` | `resumen` |
| `despliegues` | `operar` |
| `ambientes` | `operar` |
| `publicaciones` | `operar` |
| `servidores` | `operar` |
| `pipelines` | `construir` |
| `variables` | `construir` |
| `pr-review` | `diagnosticar` |
| `remote-console` | `diagnosticar` |
| `agente` | `diagnosticar` |

> **No reordenar el array** más allá de poner `resumen` primero (F3): el orden dentro de cada grupo lo
> deriva `sectionsOfGroup` del orden del array, y `DevOpsShellV2Regression.test.ts` verifica presencia.

#### F4.3 — Componente: `frontend/src/pages/DevOpsCockpitNav.tsx` (archivo NUEVO, deuda 0)

Usa la primitiva `Tabs` **dos veces** (dos conjuntos de pestañas independientes, cada uno con su
`role="tablist"` propio, que es lo que la primitiva ya emite — `components/ui/Tabs.tsx:30`):

```tsx
/** Plan 239 F4 — navegación de dos niveles del cockpit. Presentación pura. */
import Tabs from "../components/ui/Tabs";
import styles from "./DevOpsCockpit.module.css";
import { DEVOPS_SECTION_GROUPS, sectionsOfGroup, partitionForBar, activeGroupOf } from "./devopsCockpitShell";

export function DevOpsCockpitNav({ sections, activeId, onSelect, health }: Props) {
  const activeGroup = activeGroupOf(sections, activeId);
  const { visibleByGroup, gated } = partitionForBar(sections, health);
  const inGroup = visibleByGroup[activeGroup];
  return (
    <>
      <div className={styles.navPrimary}>
        <Tabs aria-label="Grupos del panel DevOps" size="md"
              items={DEVOPS_SECTION_GROUPS.map(g => ({ id: g.id, label: g.label }))}
              activeId={activeGroup}
              onChange={(gid) => {
                // Al cambiar de grupo se abre su PRIMERA sección visible; si el grupo
                // no tiene ninguna visible, se abre la primera gateada (para que el
                // operador llegue al FlagGateBanner y sepa cómo prenderla).
                const first = visibleByGroup[gid]?.[0] ?? sectionsOfGroup(sections, gid)[0];
                if (first) onSelect(first.id);
              }} />
        {gated.length > 0 && (
          <details className={styles.disabledDisclosure}>
            <summary>{`Deshabilitadas (${gated.length})`}</summary>
            {gated.map(s => (
              <button key={s.id} type="button" onClick={() => onSelect(s.id)}
                      title="Flag apagada — clic para ver cómo activarla">{s.label}</button>
            ))}
          </details>
        )}
      </div>
      {inGroup.length > 1 && (
        <div className={styles.navSecondary}>
          <Tabs aria-label={`Secciones de ${activeGroup}`} size="sm"
                items={inGroup.map(s => ({ id: s.id, label: s.label }))}
                activeId={activeId} onChange={onSelect} />
        </div>
      )}
    </>
  );
}
```

#### F4.4 — Cableado en `DevOpsPage.tsx` (3 niveles de degradación, sin borrar nada)

```tsx
const cockpit = ctx.health.cockpit_enabled === true;   // Plan 239
const uiV2 = ctx.health.ui_v2_enabled === true;        // Plan 119 (ahora default ON)

// Header: cockpit ⇒ header v3 (meta operacional); si no, el v2 del 119; si no, el <h2> v1.
// Barra:  cockpit ⇒ <DevOpsCockpitNav/>; si no, <DevOpsTabsV2/>; si no, la barra inline v1.
// El outlet (C10) y <ConnectionHealthStrip/> NO se tocan en ninguna rama.
```

**INTOCABLES (verificados como regresiones reales de la crítica del plan 119, C1/C2):**
- `<ConnectionHealthStrip onGotoSection={handleTabClick} />` sigue condicionado **solo** a
  `connection_doctor_enabled` (`DevOpsPage.tsx:273-275`), **nunca** a `cockpit`/`uiV2`.
- El botón "⬇️ Descargar scripts" (WinRM) de `ServersSection` sigue presente.
- El registro `DEVOPS_SECTIONS`, el gate declarativo con `FlagGateBanner` y el montaje persistente C10
  quedan iguales.

**Test PRIMERO — crear `frontend/src/pages/__tests__/devopsCockpitShell.test.ts`:**

```
groupOf: sección sin group ⇒ DEFAULT_GROUP "operar"        <- contrato C20 (KPI-10)
DEVOPS_SECTION_GROUPS tiene exactamente 4 grupos            <- KPI-2
sectionsOfGroup respeta el orden de DEVOPS_SECTIONS
isGated replica el gate del outlet (healthKey ausente ⇒ false)
partitionForBar saca las gateadas de visibleByGroup y las pone en gated
partitionForBar: grupo con TODAS gateadas ⇒ el grupo sigue existiendo (no se oculta)
buildGroupTabs devuelve 4 items con id/label
activeGroupOf('despliegues') ⇒ 'operar'; id inexistente ⇒ 'resumen'
buildOperationalMeta con overviewStatus null omite el segmento de estado (no inventa)
buildOperationalMeta NO menciona "capacidades"              <- el ruido del 119 se fue
```

**Y crear `frontend/src/pages/__tests__/DevOpsCockpitRegression.test.ts`** (fs+regex, calcado de
`DevOpsShellV2Regression.test.ts`):

```
las 10 secciones siguen registradas en DEVOPS_SECTIONS (por id)
cada sección (salvo 'resumen') conserva su healthKey/gateFlagKey/gateMessage originales
ConnectionHealthStrip aparece en DevOpsPage.tsx sin estar condicionado a cockpit ni uiV2
DevOpsCockpitNav.tsx y DevOpsOverviewSection.tsx no contienen "style={{"
DevOpsCockpitNav.tsx importa Tabs de components/ui (no reimplementa la barra)
DevOpsPage.tsx conserva la rama v1 (grep '#007bff') -> no se borró el rollback
test_seccion_sin_group_cae_en_grupo_default (KPI-10)
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts
npx vitest run src/pages/__tests__/DevOpsCockpitRegression.test.ts
npx vitest run src/pages/__tests__/DevOpsShellV2Regression.test.ts
npx vitest run src/pages/devopsShell.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario).** Los 5 comandos verdes. `buildGroupTabs(...).length === 4` (KPI-2)
y `DevOpsShellV2Regression.test.ts` sigue verde sin modificarlo (KPI-9).

**Flag.** `STACKY_DEVOPS_COCKPIT_ENABLED` (default ON). OFF ⇒ `DevOpsTabsV2` del plan 119, intacto.

**Impacto por runtime.** Ninguno (presentación). Los 3 runtimes: idéntico. Fallback: la escalera
`cockpit → v2 → v1` es la degradación explícita, controlada por 2 flags independientes.

**Trabajo del operador: ninguno.**

**Accesibilidad de esta fase (declaración honesta).** Se hereda de la primitiva `Tabs`:
`role="tablist"`, `role="tab"`, `aria-selected` y `aria-label` por fila; el foco se ve con
`--focus-ring`; el orden de tabulación es el del DOM y **todos** los destinos son alcanzables con
Tab/Shift+Tab. **Lo que este plan NO resuelve:** la primitiva `Tabs` **no** implementa navegación con
flechas ←/→ (roving tabindex) — es un hueco **preexistente** de `components/ui/Tabs.tsx` (no tiene
`onKeyDown`), y arreglarlo exige tocar el contrato congelado del plan 138 §10.2. Queda declarado en §6
como trabajo de un plan del sistema de diseño; este plan no lo empeora.

---

### F5 — Deep-link `/devops/<seccion>` + sección de inicio fijable

**Objetivo (1 frase).** Que cada sección tenga URL propia (compartible y marcable) y que el operador
pueda fijar cuál es su pantalla de aterrizaje.
**Valor.** Cierra el incumplimiento del contrato de URL del plan 165 en la única página con 9 sub-tabs y
elimina el "cada F5 me devuelve al constructor de pipelines".

> **Reuso total:** `services/routes.ts` **no se toca**. Ya parsea `/devops/<sub>` de forma genérica
> (`:58`) y lo serializa (`:92-93`). El patrón receptor es el de `SettingsPage` (`App.tsx:292` +
> `SettingsPage.tsx:146-183`), que se replica literalmente.

#### F5.1 — Helper puro (agregar a `frontend/src/pages/devopsCockpitShell.ts`)

```ts
/** Precedencia EXACTA (y en este orden):
 *  1. `subTab` de la URL, si es un id conocido y NO está gateado.
 *  2. `pinned` (localStorage), si es conocido y NO está gateado.
 *  3. 'resumen' si el cockpit está ON.
 *  4. primera sección NO gateada del array.
 *  5. 'pipelines' (último recurso, comportamiento histórico).
 *  Nunca devuelve un id gateado: aterrizar en un FlagGateBanner sería un aterrizaje roto. */
export function resolveLandingSection(args: {
  sections: DevOpsSection[];
  health: Record<string, unknown>;
  subTab: string | null;
  pinned: string | null;
  cockpitOn: boolean;
}): string;
```

#### F5.2 — `App.tsx`: pasar el subtab (1 línea)

> v2 (C7): la línea a editar es **`App.tsx:307`** (el v1 decía `:298`); el precedente de `SettingsPage`
> está en **`:301`** (el v1 decía `:292`). El texto del diff de abajo coincide **literalmente** con el
> archivo actual, así que se aplica por búsqueda de texto, no por número de línea.

```diff
-      {tab === "devops"      && devopsEnabled && <DevOpsPage />} {/* Plan 87 */}
+      {tab === "devops"      && devopsEnabled && <DevOpsPage subTab={route.subtab ?? null} />} {/* Plan 87 + 239 */}
```

#### F5.3 — `DevOpsPage.tsx`: recibir, sincronizar y escribir la URL

Calcado de `SettingsPage.tsx:146-183` (mismo patrón `lastApplied` + `replaceState` con guard):

```tsx
export const DevOpsPage: React.FC<{ subTab?: string | null }> = ({ subTab = null }) => {
  // ...healthQuery y serversQuery como hoy...
  const [pinned, setPinned] = useLocalStorageState<string | null>("stacky.devops.pinnedSection", null);

  // NOTA v2 (C1): `activeId` NO se inicializa con resolveLandingSection — el aterrizaje
  // lo aplica el efecto `landingApplied` de F3.4, que espera a que healthQuery.data
  // exista. Acá F5 solo aporta los dos valores que en F3 entraban como null:
  // `subTab` (prop, F5.2) y `pinned` (localStorage). El efecto de F3.4 no se duplica.

  // (a) prop VIVA: popstate / navegación in-app cambian subTab ⇒ seguirlo, sin pisar el click local.
  const lastAppliedSub = useRef(subTab);
  useEffect(() => {
    if (subTab !== lastAppliedSub.current) {
      lastAppliedSub.current = subTab;
      if (subTab && DEVOPS_SECTIONS.some(s => s.id === subTab)) handleTabClick(subTab);
    }
  }, [subTab]);

  // (b) write-back: la sección elegida por click se refleja en el path con replaceState
  //     (no pushState: no ensucia el historial, mismo criterio del plan 165 F3 [A2]).
  //     GUARD obligatorio: solo si la ruta actual es /devops (si el operador ya navegó
  //     a otra tab, esta página puede estar desmontándose y reescribiría una URL ajena).
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    if (current.tab !== "devops") return;
    const next = serializeRoute({ ...current, subtab: activeId });
    const target = window.location.pathname + window.location.search;
    if (next !== target) window.history.replaceState({}, "", next);
  }, [activeId]);
```

**Control de "fijar inicio"** en el header v3 (solo con `cockpit` ON): un `Button` `size="sm"` que dice
`Fijar como inicio` / `Inicio fijado` y hace `setPinned(activeId === pinned ? null : activeId)`.
Un solo `localStorage` key, sin backend, sin config. **No es un sistema de vistas guardadas** (eso es
del plan 173, ver §6).

**Test PRIMERO — agregar a `devopsCockpitShell.test.ts`:**

```
resolveLandingSection sin nada + cockpitOn ⇒ 'resumen'                       <- KPI-1
resolveLandingSection con subTab 'despliegues' ⇒ 'despliegues'               <- KPI-5
resolveLandingSection con subTab desconocido ⇒ cae a 'resumen'
resolveLandingSection con subTab GATEADO ⇒ NO lo devuelve (cae al siguiente)
resolveLandingSection con pinned 'variables' y sin subTab ⇒ 'variables'
resolveLandingSection: subTab GANA a pinned
resolveLandingSection con cockpitOff y sin nada ⇒ primera NO gateada (nunca 'resumen')  <- KPI-9
resolveLandingSection con todo gateado ⇒ 'pipelines'
```

**Y agregar a `DevOpsCockpitRegression.test.ts`:**
```
App.tsx pasa subTab a DevOpsPage
DevOpsPage.tsx usa replaceState (no pushState) y tiene el guard current.tab !== "devops"
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts
npx vitest run src/pages/__tests__/DevOpsCockpitRegression.test.ts
npx vitest run src/services/__tests__/routes.test.ts src/services/__tests__/routesDeepLink.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario).** Los 4 comandos verdes; los tests de `routes.ts` verdes **sin
haber modificado** `routes.ts` (prueba de reuso puro).

**Flag.** El aterrizaje en `resumen` y el control de fijar dependen de
`STACKY_DEVOPS_COCKPIT_ENABLED`; el deep-link `/devops/<id>` funciona en **las 3 ramas** (es
comportamiento estrictamente aditivo y deseable también en v2/v1).

**Impacto por runtime.** Ninguno. Los 3 runtimes: idéntico. Fallback: sin `subTab` (deploy viejo de
`App.tsx`) el default de la prop es `null` y el aterrizaje resuelve por pin/cockpit ⇒ no rompe.

**Trabajo del operador: ninguno** (fijar el inicio es opcional y el default ya es el mejor).

---

### F6 — Fin del sondeo perpetuo: `visible` en el contexto + ratchet

**Objetivo (1 frase).** Que ninguna sección oculta siga pidiendo datos al backend, sin perder el
montaje persistente que protege la autoría a medio hacer.
**Valor.** Elimina las ~15 req/min permanentes que hoy genera Despliegues tras una única visita **y los
dos `setInterval` de `TriggerPipelineSection` (10 s y 3 s) que el v1 dejaba vivos** (v2, C3), y
**mecaniza** la regla —en sus dos formas— para que una sección futura no pueda reintroducir la fuga.

**Por qué `visible` y NO desmontar (decisión explícita, no la tomes de nuevo):** el contrato C10
(`DevOpsPage.tsx:189-190`) existe para que cambiar de pestaña **no** pierda el YAML a medio escribir del
constructor de pipelines ni el formulario de un ambiente. Desmontar (o una política LRU) resolvería el
sondeo **destruyendo trabajo del operador** — inaceptable. Gatear el sondeo por visibilidad da el mismo
ahorro con riesgo cero.

**Editar `DevOpsPage.tsx`** — el outlet ya sabe cuál está activa (`:344`); propagarlo por sección:

```diff
-      {DEVOPS_SECTIONS.map((s) => {
-        if (!mountedIds.has(s.id)) return null;
-        const isGated = s.healthKey && ctx.health[s.healthKey] !== true;
-        const content = isGated ? (<FlagGateBanner … />) : s.render(ctx);
+      {DEVOPS_SECTIONS.map((s) => {
+        if (!mountedIds.has(s.id)) return null;
+        const isGated = s.healthKey && ctx.health[s.healthKey] !== true;
+        // Plan 239 F6 — ctx POR SECCIÓN: `visible` es true solo para la activa.
+        const sectionCtx: DevOpsSectionContext = { ...ctx, visible: activeId === s.id };
+        const content = isGated ? (<FlagGateBanner … />) : s.render(sectionCtx);
```

**Editar `frontend/src/components/devops/DeploymentsSection.tsx:50`** (primer consumidor):

```diff
-    refetchInterval: 4000,
+    // Plan 239 F6 — solo sondea cuando la sección es la visible. `visible` ausente
+    // (shells que no lo propaguen) ⇒ se trata como visible: comportamiento de hoy.
+    refetchInterval: ctx.visible === false ? false : 4000,
```

**Editar `frontend/src/components/devops/TriggerPipelineSection.tsx` (v2, C3 — el v1 lo omitía).**
Censo verificado 2026-07-25: `components/devops/` tiene **1** `refetchInterval` y **2** `setInterval`.
Los dos `setInterval` sondean el backend y sobreviven al `display:none` igual que el `refetchInterval`;
el ratchet del v1, que solo miraba `refetchInterval`, los habría dejado vivos declarando KPI-4 cumplido.
El componente **ya recibe `ctx`** (`:135` en `TriggerPipelineSectionProps`, `:140` en la firma) y sus
tres padres lo pasan verbatim (`PipelineBuilderSection.tsx:753`, `EnvironmentsSection.tsx:568`,
`ProductionFlow.tsx`), así que `ctx.visible` llega solo: el fix son **2 líneas**.

```diff
   // Poll de estado acotado (KPI-4): solo los ids no-finales, cap 5, cada 10 s
   React.useEffect(() => {
     if (!ledgerAvailable) return;
+    if (ctx.visible === false) return;   // Plan 239 F6 — no sondear con la sección oculta
     const targets = pollTargets(runs, statusById);
```
```diff
   // Auto-polling si está activo
   React.useEffect(() => {
-    if (polling && pipelineId) {
+    if (polling && pipelineId && ctx.visible !== false) {   // Plan 239 F6
       const interval = setInterval(() => {
```
> **Agregar `ctx.visible` al array de dependencias de ambos efectos** (`[runs, statusById,
> ledgerAvailable, project, ctx.visible]` y `[polling, pipelineId, ctx.visible]`). Sin eso, el efecto no
> se re-evalúa al volver a la sección y el sondeo **no se reanuda**: pasaríamos de "sondea de más" a
> "no sondea nunca", que es peor. El `return () => clearInterval(interval)` que ya existe hace la
> limpieza al ocultarse.

**Test PRIMERO — crear `frontend/src/__tests__/devopsPollingRatchet.test.ts`** (ratchet mecánico, mismo
idioma que `uiDebtRatchet`):

```ts
/** Plan 239 F6 — ningún sondeo periódico de components/devops/ puede correr oculto.
 *  v2 (C3): cubre DOS formas, no una. Para cada archivo .tsx de components/devops/:
 *    - cada línea con `refetchInterval:`  ⇒ en esa línea o en las 2 siguientes debe
 *      aparecer `visible`;
 *    - cada línea con `setInterval(`      ⇒ en las 12 líneas ANTERIORES del mismo
 *      useEffect debe aparecer `visible` (el guard va antes del setInterval).
 *  Un archivo solo queda exento si está en la ALLOWLIST, que hoy está vacía. */
const ALLOWLIST: string[] = [];  // vacía a propósito: hoy no hay excepción legítima
```
Casos:
```
todo refetchInterval en components/devops/*.tsx está gateado por `visible`          <- KPI-4
todo setInterval( en components/devops/*.tsx está gateado por `visible`             <- KPI-4 (v2, C3)
el censo detecta exactamente 1 refetchInterval y 2 setInterval (si aparece uno nuevo
  sin guarda, este test lo caza: es un ratchet, no una foto)
DeploymentsSection.tsx usa ctx.visible en su refetchInterval
TriggerPipelineSection.tsx gatea sus DOS setInterval con ctx.visible
TriggerPipelineSection.tsx incluye ctx.visible en las deps de ambos efectos          <- anti "no reanuda"
la ALLOWLIST está vacía (si alguien la llena, tiene que justificarlo en el diff)
el helper detecta el caso negativo (fixture string con refetchInterval sin visible ⇒ error)
el helper detecta el caso negativo de setInterval (fixture sin visible ⇒ error)
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/__tests__/devopsPollingRatchet.test.ts
npx vitest run src/components/devops/deploymentsModel.test.ts
npx vitest run src/components/devops/__tests__/PipelineBuilderSection.test.ts   # v2 — padre de Trigger*
npx tsc --noEmit
```

**Criterio de aceptación (binario).** Los 4 comandos verdes. Verificación manual complementaria (2 min,
opcional pero recomendada): abrir DevTools → Network, entrar a Despliegues, cambiar a Variables y
confirmar que `deployments/overview` **deja** de aparecer; después entrar a Pipelines con una corrida en
curso, cambiar de sección y confirmar que `/pipeline/<id>` **también** deja de aparecer (v2, C3), y que
al volver a Pipelines **se reanuda** (prueba de que las deps del efecto quedaron bien).

**Flag.** Ninguna nueva. El cambio es intrínsecamente seguro: `visible === false` solo puede ocurrir en
el shell que lo propaga; cualquier otro camino lo deja `undefined` ⇒ comportamiento de hoy.

**Impacto por runtime.** Ninguno. Los 3 runtimes: idéntico. Fallback: `visible` es opcional; su ausencia
significa "visible".

**Trabajo del operador: ninguno.**

---

### F7a — Convergencia al sistema de diseño: tokens, hex 0 y responsive

**Objetivo (1 frase).** Que el CSS del panel DevOps use la escala semántica del plan 138 (y por lo tanto
herede densidad del 150 y tema claro del 141) y que no quede ni un hex de color.
**Valor.** El panel deja de ser el único módulo que ignora la preferencia de densidad del operador, y el
tema claro deja de tener colores que no se re-apuntan.

**Editar `frontend/src/pages/DevOpsPage.module.css`** (58 líneas, plan 119): reemplazo 1:1, **sin tocar
ningún selector ni la estructura** (para no romper el v2):

| Hoy | Pasa a |
|-----|--------|
| `padding: 40px 40px 64px` | `padding: var(--space-9) var(--space-8) var(--space-9)` |
| `gap: 24px` / `gap: 14px` / `gap: 8px` / `gap: 6px` / `gap: 2px` | `var(--space-7)` / `var(--space-6)` / `var(--space-4)` / `var(--space-3)` / `var(--space-1)` |
| `margin: 28px 0 0` | `margin: var(--space-8) 0 0` |
| `font-size: 1.5rem` / `0.85rem` / `0.8rem` / `0.82rem` / `0.68rem` | `var(--text-2xl)` / `var(--text-sm)` / `var(--text-sm)` / `var(--text-sm)` / `var(--text-xs)` |
| `font-weight: 600` / `500` | `var(--weight-semibold)` / `var(--weight-medium)` |
| `border-radius: var(--radius)` | `var(--radius-md)` |
| `transition: color 0.12s, border-color 0.12s` | `var(--transition-colors)` |
| `1px solid var(--border)` | `var(--border-width) solid var(--border)` |
| **`color: #fff`** (en `.btnPrimary`, el único hex del archivo) | **`color: var(--text-on-solid)`** |

**Editar `frontend/src/components/devops/devops.module.css`** (428 líneas): reemplazar los **7** hex por
tokens. **Y `frontend/src/components/devops/PrReviewerSection.module.css`: su **1** hex (v2, C9 — el v1
lo pasaba por alto; está en `hexByFile` del baseline y vive en `components/devops/`, así que sin él la
frase "0 hex en el panel DevOps" sería falsa). Total del barrido: **7 + 1 + 1 = 9 hex → 0**.
Mapeo obligatorio (si un hex no cae en la tabla, usar el token semántico de estado más cercano
del plan 138 y dejar comentario `/* plan 239: <hex original> */`):

| hex | token |
|-----|-------|
| blancos (`#fff`, `#ffffff`) | `var(--text-on-solid)` |
| azules Bootstrap (`#007bff`, `#0d6efd`) | `var(--accent)` |
| grises (`#6c757d`, `#888`, `#ccc`) | `var(--text-muted)` |
| verdes | `var(--status-success-text)` |
| rojos | `var(--status-danger-text)` |
| amarillos | `var(--status-warning-text)` |

**Responsive.** Agregar al final de `DevOpsPage.module.css`:
```css
/* Plan 239 F7a — ventana angosta: respiración mínima y nav deslizable. */
@media (max-width: 900px) {
  .page { padding: var(--space-6) var(--space-5) var(--space-8); }
  .head { flex-direction: column; }
  .picker .ctl { min-width: 0; width: 100%; }
}
```

**Test PRIMERO — crear `frontend/src/__tests__/devopsDesignTokens.test.ts`:**
```
DevOpsPage.module.css y DevOpsCockpit.module.css tienen 0 hex de color
devops.module.css tiene 0 hex de color
PrReviewerSection.module.css tiene 0 hex de color                     <- v2 (C9)
ningún .module.css bajo components/devops/ tiene hex (barrido por carpeta, no por lista:
  así un archivo nuevo con hex también lo caza)
DevOpsCockpit.module.css no usa px crudos en padding/margin/gap (solo var(--space-*))
DevOpsPage.module.css declara al menos un @media (max-width: 900px)
ningún .module.css de devops usa `transition:` con duración literal (usa --transition-*/--duration-*)
```

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/__tests__/devopsDesignTokens.test.ts
npx vitest run src/__tests__/themeTokens.test.ts src/__tests__/themeLightTokens.test.ts
npx vitest run src/__tests__/densityTokens.test.ts src/__tests__/a11yCss.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```

**Criterio de aceptación (binario).** Los 4 comandos verdes. `uiDebtRatchet` verde **sin**
`UI_DEBT_REGEN` (los hex bajaron, y el ratchet solo se queja si suben). Después de esta fase, regenerar
el baseline **una vez** y verificar que `hexByFile` ya no tiene entradas de devops:
```bash
UI_DEBT_REGEN=1 npx vitest run src/__tests__/uiDebtRatchet.test.ts   # bash
# PowerShell: $env:UI_DEBT_REGEN='1'; npx vitest run src/__tests__/uiDebtRatchet.test.ts; Remove-Item Env:\UI_DEBT_REGEN
npx vitest run src/__tests__/uiDebtRatchet.test.ts                    # y de nuevo SIN la env: debe quedar verde
```

**Flag.** Ninguna: es CSS de archivos existentes, sin cambio de comportamiento. El riesgo se controla
con los tests de tokens/contraste/densidad ya existentes.

**Impacto por runtime.** Ninguno. Los 3 runtimes: idéntico.

**Trabajo del operador: ninguno.**

---

### F7b — Barrido de estilos inline (8 archivos acotados, mecánico)

**Objetivo (1 frase).** Bajar la deuda de `style={{` del panel DevOps migrando los 8 archivos de menor
volumen y mayor visibilidad a clases de `devops.module.css`.
**Valor.** KPI-8 medible, y cada archivo migrado deja de re-pintar estilos en cada render.

**Alcance EXACTO (8 archivos, 75 ocurrencias a eliminar):**

| # | archivo | `style={{` hoy | destino |
|---|---|---|---|
| 1 | `components/devops/FlagGateBanner.tsx` | 5 | 0 |
| 2 | `components/devops/SectionDoctorButton.tsx` | 7 | 0 |
| 3 | `components/devops/DeploymentsSection.tsx` | 8 | 0 |
| 4 | `components/devops/BlockTree.tsx` | 8 | 0 |
| 5 | `components/devops/PreflightPanel.tsx` | 10 | 0 |
| 6 | `components/devops/DirTreePreview.tsx` | 12 | 0 |
| 7 | `components/devops/ProductionFlow.tsx` | 12 | 0 |
| 8 | `components/devops/TriggerPipelineSection.tsx` | 13 | 0 |
| — | `pages/DevOpsPage.tsx` | 8 | **8 — NO se toca** (es la rama v1 de rollback, ver R3) |

Aritmética del KPI-8: **461 − 75 = 386**, y los 3 archivos nuevos de F3/F4 nacen en **0** ⇒ el panel
queda en **≤ 386**, que es exactamente el techo declarado en §1.

> **NOTA DE ALCANCE, SIN CAPS SILENCIOSOS (obligatorio leerla).** Estos 8 archivos son los de chrome y
> controles chicos. **NO se migran en este plan** (y queda dicho explícitamente, no escondido):
> `BlockProperties.tsx` (58), `PipelineBuilderSection.tsx` (53), `PublicationsSection.tsx` (34),
> `ServersSection.tsx` (33), `RemoteConsoleSection.tsx` (33), `EnvironmentsSection.tsx` (28),
> `PipelineDoctorPanel.tsx` (27), `CommitPipelineModal.tsx` (21), `DevOpsAgentSection.tsx` (20),
> `VariablesSection.tsx` (17), `PipelineYamlPreview.tsx` (14), `PipelineGeneratorPanel.tsx` (25),
> `PipelineTriggerCard.tsx` (14). Son **387** ocurrencias de re-maquetado de contenido, no de chrome:
> requieren rediseñar cada formulario y exceden lo que una fase mecánica puede garantizar sin
> regresiones. Se dejan como **plan siguiente nombrado** en §6.

**Procedimiento mecánico por archivo (idéntico para los 8, sin ambigüedad):**
1. Para cada `style={{ a: 1, b: 2 }}` crear una clase en `devops.module.css` con nombre
   `<archivoCamel>__<rol>` (ej.: `flagGateBanner__row`), con **las mismas propiedades**, usando tokens
   (`--space-*`, `--text-*`, `--status-*`).
2. Reemplazar por `className={styles.flagGateBanner__row}`.
3. **Valores dinámicos** (ej. `style={{ width: pct + '%' }}`): NO se pueden mover a CSS. Usar el patrón
   de la casa (gotcha del ratchet): `ref` + `useEffect` que setea `el.style.setProperty('--w', pct+'%')`
   y la clase consume `width: var(--w)`. **Prohibido** dejar `style={{}}` en archivos nuevos; en archivos
   existentes, dejarlo solo si el valor es realmente dinámico y **documentarlo** en el diff.
4. Verificar en cada paso: `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (debe seguir verde: la
   deuda baja, nunca sube).

**Test.** No hace falta test nuevo: el gate es el ratchet + el conteo del baseline.

**Comandos exactos.**
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
npx vitest run src/components/devops/deploymentsModel.test.ts src/components/devops/deployEvidence.test.ts
npx vitest run src/components/devops/__tests__/PipelineBuilderSection.test.ts
```

**Criterio de aceptación (binario).** Los 4 comandos verdes y, tras regenerar el baseline, el conteo.
**v2 (C8):** el comando pasa de `python -c` a `node -e` — `node` está garantizado (todo este plan usa
`npx`), mientras que `python` pelado puede no resolver desde `frontend/`, y las comillas del one-liner
de Python se rompen en PowerShell, que es el shell del operador. Este funciona **igual en bash y en
PowerShell**, desde `Stacky Agents/frontend`:
```bash
node -e "const d=require('./src/__tests__/uiDebtBaseline.json');console.log(Object.entries(d.inlineStyleByFile).filter(([k])=>/devops|DevOps|Pipeline/.test(k)).reduce((a,[,v])=>a+v,0))"
# DEBE imprimir un número <= 386
```

**Flag.** Ninguna (refactor de presentación sin cambio de comportamiento).

**Impacto por runtime.** Ninguno. Los 3 runtimes: idéntico.

**Trabajo del operador: ninguno.**

---

### F8 — Gate de cierre: no-regresión, accesibilidad y documentación del DoD

**Objetivo (1 frase).** Un único comando que prueba que nada se rompió y que los 10 KPIs se cumplen.
**Valor.** Convierte el cierre del plan en algo verificable por el supervisor sin inspección visual.

**Crear `frontend/src/pages/__tests__/DevOpsCockpitClosure.test.ts`** (fs+regex; agrega lo que las fases
anteriores no cubren):
```
las 10 secciones de DEVOPS_SECTIONS tienen `group` asignado
ninguna sección perdió su render(ctx)
DevOpsOverviewSection no importa nada de deploy/execute/rollback/trigger      <- solo lectura
DevOpsCockpit.module.css no tiene hex ni px crudos en spacing
la sección Resumen es la primera del array                                    <- KPI-1
no hay dos secciones con el mismo id
todo `group` usado existe en DEVOPS_SECTION_GROUPS
# ── v2: cierres de los bloqueantes C1/C3 ──
DevOpsPage.tsx tiene el guard `s.id !== activeId` en el outlet                <- C1 (a): nunca en blanco
DevOpsPage.tsx aplica el aterrizaje en useEffect con landingApplied           <- C1 (b): health primero
DevOpsPage.tsx NO llama resolveLandingSection dentro de useState(             <- C1 (b): grep negativo
ningún .tsx de components/devops tiene setInterval( sin `visible` cerca       <- C3 (redundante con el
                                                                                ratchet, a propósito:
                                                                                el cierre no depende de
                                                                                un solo archivo de test)
```

#### F8.2 — Huellas de regresión (v2, C10 — convención de la casa que el v1 omitía)

Este plan **mata dos clases de error**, no una. Registrarlas en
`Stacky Agents/docs/sistema/error_fingerprints.json` (schema v1, 13 entradas hoy; precedente exacto:
las dos del plan 238, con `log_guarded: false` y `killed_commit: null`). Agregar al final del array
`fingerprints`, completando `killed_commit` con el hash real al commitear:

```jsonc
{
  "id": "PLAN239-OUTLET-EN-BLANCO",
  "title": "La sección activa no está en mountedIds y el panel DevOps se ve vacío",
  "class": "shell-navigation",
  "status": "resolved",
  "log_pattern": "",
  "log_guarded": false,
  "killed_by": "plan 239 F3.4 (guard `s.id !== activeId` en el outlet + aterrizaje por useEffect)",
  "killed_commit": null,
  "date_resolved": "2026-07-25",
  "guard_test": "src/pages/__tests__/DevOpsCockpitRegression.test.ts",
  "evidence": "frontend/src/pages/DevOpsPage.tsx:190 sembraba mountedIds con DEVOPS_SECTIONS[0].id mientras :324 cortaba con !mountedIds.has(s.id); cualquier deep-link/pin/flag-off dejaba la pantalla vacía",
  "note": "Clase general: estado de montaje derivado de una constante en vez de derivado del estado activo. Regla: si un render depende de un Set de ids, la invariante 'lo activo siempre se renderiza' va en el render, no en quien setea. Hermana de la trampa del inicializador perezoso de useState, que evalúa antes de que llegue la data async."
},
{
  "id": "PLAN239-SONDEO-OCULTO-SETINTERVAL",
  "title": "Un setInterval sigue sondeando el backend con la sección oculta (display:none, sin desmontar)",
  "class": "polling-leak",
  "status": "resolved",
  "log_pattern": "",
  "log_guarded": false,
  "killed_by": "plan 239 F6 (ctx.visible + ratchet que cubre refetchInterval Y setInterval)",
  "killed_commit": null,
  "date_resolved": "2026-07-25",
  "guard_test": "src/__tests__/devopsPollingRatchet.test.ts",
  "evidence": "frontend/src/components/devops/TriggerPipelineSection.tsx:207 y :293 (setInterval) + DeploymentsSection.tsx:50 (refetchInterval), bajo el montaje persistente C10 de DevOpsPage.tsx:190",
  "note": "Un ratchet que solo mira refetchInterval declara victoria y deja viva la fuga de setInterval. Regla: el ratchet de sondeo se define por EFECTO (pedir datos periódicamente), no por API."
}
```

**Verificación (binaria).** El archivo sigue siendo JSON válido y ganó exactamente 2 entradas:
```bash
# desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents"
node -e "const d=require('./docs/sistema/error_fingerprints.json');console.log(d.fingerprints.length, d.fingerprints.slice(-2).map(f=>f.id).join(','))"
# DEBE imprimir: 15 PLAN239-OUTLET-EN-BLANCO,PLAN239-SONDEO-OCULTO-SETINTERVAL
```

**Suite completa de cierre (correr en este orden, todos DEBEN quedar verdes):**
```bash
# ── Backend ── desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan239_cockpit_flag.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_service.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan239_devops_overview_endpoint.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan120_planner.py tests/test_plan120_flags.py -q  # v2 — F1.0 aditiva
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q          # SOLO, por el reload de config
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py -q
./.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan119_devops_ui_v2_flag.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_plan87_devops_flag.py -q
./.venv/Scripts/python.exe -m pytest tests/test_plan116_connections_endpoints.py -q   # HITL del doctor intacto
./.venv/Scripts/python.exe -m pytest tests/test_plan116_connection_doctor_core.py -q
./.venv/Scripts/python.exe -m compileall -q services/devops_overview.py services/deploy_planner.py api/devops.py api/devops_connections.py

# ── Frontend ── desde "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx tsc --noEmit
npx vitest run src/components/devops/overviewModel.test.ts
npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts
npx vitest run src/pages/__tests__/DevOpsCockpitRegression.test.ts
npx vitest run src/pages/__tests__/DevOpsCockpitClosure.test.ts
npx vitest run src/pages/__tests__/DevOpsPage.test.ts
npx vitest run src/pages/__tests__/DevOpsShellV2Regression.test.ts
npx vitest run src/pages/devopsShell.test.ts
npx vitest run src/__tests__/devopsPollingRatchet.test.ts
npx vitest run src/__tests__/devopsDesignTokens.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts       # v2 — F3.5 usa copyService, no clipboard crudo
npx vitest run src/__tests__/themeContrast.test.ts src/__tests__/a11yCss.test.ts src/__tests__/motionA11yGuard.test.ts
npx vitest run src/services/__tests__/routes.test.ts src/services/__tests__/routesDeepLink.test.ts
```

**Checklist visual (2 minutos, complementario — NO reemplaza los tests):**
1. `/devops` aterriza en **Resumen** con 8 KPIs y la fila primaria de 4 grupos.
2. Apagar **`STACKY_CI_RUN_LEDGER_ENABLED`** por UI (v2, C5: el v1 escribía
   `STACKY_DEVOPS_CI_RUN_LEDGER_ENABLED`, que **no existe**; la real está en `config.py:1427` y
   `harness_flags.py:193`, y es la misma que nombra la tabla de F1.3). **Dónde encontrarla en la UI:**
   NO está en la categoría *DevOps* — vive en **`epicas_ado`** (`harness_flags.py:179-196`), junto al
   resto de las flags de CI heredadas de los planes 71-73. → el pie dice "Fuentes sin datos: CI:
   bitácora apagada" y **ningún KPI de CI muestra 0 como si fuera un dato**.
3. Instalación virgen (sin apps ni servidores) → estado "Sin datos suficientes", **no** "Sin novedades".
4. Click en "Ir a la sección" de una alerta → abre la sección correcta y la URL pasa a `/devops/<id>`.
5. Recargar en `/devops/despliegues` → sigue en Despliegues.
5b. Elegir una aplicación en el filtro → KPIs, tendencia, alertas y actividad se recortan a esa app, el
    selector de aplicaciones **sigue** listando todas, y al recargar la selección se mantiene.
5c. Abrir `/devops/resumen` con `?app_id=inexistente` a mano → la pantalla abre igual, con el selector en
    "Todas las aplicaciones" (nunca un 400 ni una pantalla en blanco).
6. Apagar `STACKY_DEVOPS_COCKPIT_ENABLED` por UI → panel del plan 119 con sus 9 pestañas y la tira de
   conexiones intacta.
7. `Configuración → Apariencia → densidad compacta` → el panel DevOps se compacta (antes no lo hacía).
8. Tema claro → ningún texto ilegible en el Resumen.
9. *(v2, F3.5)* Click en "Copiar: Texto" → pegar en un editor: el texto trae el mismo estado, los mismos
   8 KPIs con los mismos valores que la pantalla (incluidos los `n/d`), los avisos y el alcance aplicado.
10. *(v2, C1)* Con una corrida de CI en curso: entrar a Pipelines, cambiar a Variables, mirar Network →
   `/pipeline/<id>` **deja** de pedirse; volver a Pipelines → **vuelve** a pedirse.

**Criterio de aceptación (binario).** Todos los comandos verdes. Si alguno de los archivos de test
preexistentes nombrados no existe, el implementador **lo dice explícitamente en el reporte** en vez de
inventar que pasó.

**Flag.** N/A (fase de verificación).

**Impacto por runtime.** Ninguno.

**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad / Impacto | Mitigación (concreta) |
|---|--------|------------------------|------------------------|
| **R1** | Promover `STACKY_DEVOPS_UI_V2_ENABLED` a ON rompe `test_plan119_devops_ui_v2_flag.py:45` (asevera `is False`). | Alta / Bajo | F0.2 punto 4 lo actualiza explícitamente y renombra el caso. Está en la suite de cierre. |
| **R2** | Poner `resumen` primero en `DEVOPS_SECTIONS` hace que, con el cockpit OFF, `DevOpsPage.tsx:188` aterrice en una pestaña gateada (pantalla de banner). | Alta / Alto | `resolveLandingSection` **nunca** devuelve un id gateado (F5.1) y se usa ya en F3. Test `resolveLandingSection con cockpitOff` (KPI-9). |
| **R3** | Tentación de "limpiar" borrando el shell v1 y su flag. | Media / Alto | **PROHIBIDO en este plan.** El plan 119 §6 lo dejó como DoD futuro y retirarlo obliga a tocar el mapa congelado `test_harness_flags_requires.py:203` y el set curado. `DevOpsCockpitRegression.test.ts` verifica que la rama v1 (`#007bff`) **siga existiendo**. Ver §6. |
| **R4** | El overview termina ejecutando algo remoto (drift) por "completitud" y la carga de página abre WinRM contra un servidor. | Media / **Crítico** | Excluido por contrato en el docstring de `services/devops_overview.py`, más `test_overview_no_ejecuta_remoto` / `test_overview_no_abre_red` / `test_overview_no_invoca_llm` con monkeypatch que revienta si se llama (KPI-7). |
| **R5** | El overview dispara el chequeo de conexiones y viola el HITL del plan 116. | Media / Alto | Solo se lee `get_snapshot()` (F1.4). `run_connection_check` monkeypatcheado a explotar en el test del endpoint. |
| **R6** | Umbrales de alerta mal calibrados ⇒ ruido y el operador aprende a ignorar el Resumen. | Media / Medio | Tabla F1.2 congelada con constantes nombradas y tests de borde en ambos lados de **cada** umbral (0.29/0.30, 239/240, 20/22 días, 1/2 fallos, 119/121 min). Todo ajuste futuro es un cambio de constante con su test. |
| **R7** | Alerta que reporta "todo bien" cuando en realidad no hay datos (ceguera silenciosa, bloqueante del plan 238). | Media / Alto | `status` nunca es `ok` sin bloques disponibles con datos; `statusLabel("unknown")` no puede contener "bien"/"OK" (test explícito); `blocks` viaja siempre en el payload y la UI lo muestra. |
| **R8** | `api.get` lanza en 404 (deploy viejo sin `/api/devops/overview`) y la sección deja la pantalla en blanco. | Media / Medio | `retry: false` + rama `isError` con estado vacío legible (F3). Gotcha documentado en el propio código. |
| **R9** | Gatear el sondeo con `visible` rompe una sección que dependía de refrescar en segundo plano. | Baja / Medio | Solo se cambia `DeploymentsSection` (F6), cuyo dato se refresca al volver a la pestaña (react-query re-fetchea al reactivar el intervalo). El resto de las secciones no declara `refetchInterval`. |
| **R10** | Alguien "arregla" el sondeo desmontando secciones y el operador pierde el YAML a medio escribir. | Media / Alto | F6 lo prohíbe por escrito con la razón. El contrato C10 sigue documentado en la cabecera de `DevOpsPage.tsx`. |
| **R11** | El write-back de URL pelea con el router y genera un bucle de `replaceState`. | Media / Medio | Guard `if (next !== target) return` + guard `current.tab !== "devops"`, calcado de `SettingsPage.tsx:180-184` (ya probado en producción) y **fuera** de todo updater de `setState` (regla §3.4 del plan 165). |
| **R12** | Regenerar el baseline del ratchet enmascara una **subida** de deuda. | Media / Medio | El propio ratchet rechaza el REGEN si algún archivo aumentó (`uiDebtRatchet.test.ts:142-145`). Además F7b exige correr el test **sin** la env después de regenerar. |
| **R13** | Los 3 tests nuevos de backend no se registran en `HARNESS_TEST_FILES` y el meta-test queda rojo. | Alta / Bajo | F0 lo incluye como paso explícito con las 3 rutas exactas. |
| **R14** | `test_harness_flags.py` se corre junto a otros y contamina la corrida (reload de `config`). | Alta / Bajo | Todos los comandos de este plan lo corren **solo**, y así está escrito en cada fase. |
| **R15** | Sesión paralela sobre el mismo árbol de trabajo: un `git commit` sin pathspec se lleva cambios ajenos. | Media / Alto | Commitear **siempre** con pathspec explícito (`git commit -- "<ruta>"`). Prohibido `reset`, `amend` y `rebase`. Correr `git worktree list` antes. |
| **R16** *(v2, C1)* | El aterrizaje fija una sección que no está en `mountedIds` y el panel se ve **vacío** (deep-link, pin, o cockpit OFF). **No es hipotético: era el comportamiento del v1.** | **Alta / Crítico** | F3.4 (a): el outlet renderiza siempre la activa (`s.id !== activeId`), así que la invariante deja de depender de quién setea `activeId`. F3.4 (b): el aterrizaje pasa por `handleTabClick`, único lugar que mantiene C10. Tres casos en `DevOpsCockpitRegression.test.ts` + huella `PLAN239-OUTLET-EN-BLANCO`. |
| **R17** *(v2, C1)* | El aterrizaje se resuelve con `healthQuery.data` todavía `undefined` (inicializador perezoso de `useState`) y el cockpit ON aterriza igual en `pipelines` ⇒ **KPI-1 falla en silencio** (los tests de la función pura pasan; falla el cableado). | **Alta / Alto** | F3.4 (b) resuelve el aterrizaje en un `useEffect` con guard `landingApplied`, que espera a que la salud exista. Test negativo por grep: `DevOpsPage.tsx` **no** puede llamar `resolveLandingSection` dentro de `useState(`. |
| **R18** *(v2, C3)* | El ratchet de sondeo cubre solo `refetchInterval` y deja viva la fuga de `setInterval` ⇒ KPI-4 verde con la fuga puesta (falso verde). | Alta / Medio | El ratchet de F6 cubre **las dos formas** y el censo (1 + 2) es parte del test; huella `PLAN239-SONDEO-OCULTO-SETINTERVAL` para que la clase no vuelva por otra sección. |
| **R19** *(v2, C3)* | Gatear los `setInterval` sin agregar `ctx.visible` a las deps del efecto ⇒ el sondeo **no se reanuda** al volver a la sección (pasamos de sondear de más a no sondear nunca). | Media / Alto | F6 lo exige por escrito con los arrays de deps completos, más el caso de test `TriggerPipelineSection.tsx incluye ctx.visible en las deps` y el paso 2 del checklist manual (volver a Pipelines y ver que se reanuda). |
| **R20** *(v2, C2)* | Nadie nota que `dora_metrics` no devuelve conteos y el implementador consolida el CFR como promedio de promedios (o inventa una clave que no existe). | Alta / Alto | F1.0 agrega `cfr_sample_30d` de forma aditiva **antes** de F1, F1.3 fija el algoritmo de dos llamadas, y `test_aggregate_deploy_consolidado` usa un caso testigo donde el promedio de promedios (0.5) y el valor correcto (0.25) **difieren**: si alguien lo implementa mal, el test lo caza. |

---

## 6. Fuera de scope (declarado, no escondido)

1. **Retirar el shell v1 y su flag.** Sigue siendo DoD futuro (plan 119 §6, R2 de ese plan). Este plan
   lo **conserva** como tercer escalón de rollback y lo verifica por test.
2. **Migrar los 13 archivos de mayor deuda inline** (`BlockProperties` 58, `PipelineBuilderSection` 53,
   `PublicationsSection` 34, `ServersSection` 33, `RemoteConsoleSection` 33, `EnvironmentsSection` 28,
   `PipelineDoctorPanel` 27, `PipelineGeneratorPanel` 25, `CommitPipelineModal` 21,
   `DevOpsAgentSection` 20, `VariablesSection` 17, `PipelineYamlPreview` 14, `PipelineTriggerCard` 14 =
   **387** ocurrencias). Es re-maquetado de **contenido** (formularios, árboles, editores), no de chrome.
   **Plan siguiente nombrado:** *"Rediseño de los formularios del panel DevOps sobre las primitivas del
   plan 162"*.
3. **Navegación con flechas ←/→ dentro de las filas de pestañas (roving tabindex).** Exige tocar
   `components/ui/Tabs.tsx`, cuyo contrato está congelado (plan 138 §10.2). Es un hueco preexistente de
   la primitiva; corresponde a un plan del sistema de diseño, no a este.
4. **Vistas guardadas con nombre (múltiples combinaciones de filtros nombradas y compartibles).** Es el
   alcance del **plan 173** (sin implementar) y este plan **no** lo invade. **Sí se entrega** (F1.2b + F3):
   filtro por aplicación, por proyecto de CI y ventana de tendencia 7/14/30 días, con persistencia de
   **la última** selección (3 keys `stacky.devops.overview.*`) y de la sección de inicio
   (`stacky.devops.pinnedSection`). Lo que queda para el 173 es el catálogo de vistas guardadas
   —N combinaciones con nombre, ordenables y compartibles por URL—, no el filtrado en sí.
5. **Atajos de teclado nuevos.** Alcance del **plan 172**. Este plan **no** registra ni un atajo global.
6. **Llevar las alertas al centro de notificaciones (plan 152) o al digest.** Sería autonomía proactiva:
   las alertas viven solo en la pantalla que el operador abre (guardarraíl 3 y 10).
7. **Drift, chequeo de conexiones, deploy, rollback, disparo de pipelines o cualquier acción** desde el
   Resumen. El cockpit **navega**, no ejecuta.
8. **Métricas históricas de largo plazo, comparativas entre proyectos y persistencia de series.** La
   tendencia se computa **al vuelo** sobre las bitácoras existentes (14 días, topes 500/200). Un almacén
   de series temporales es alcance de los planes 171/199 (telemetría).
9. **IA / LLM en el Resumen** (resumen narrado, diagnóstico automático). El diagnóstico IA de deploys ya
   existe y es opt-in dentro de Despliegues (`STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED`); acá no se toca.
10. **Nuevas dependencias npm/pip** (librerías de gráficos incluidas). Las sparklines son SVG a mano.
11. **Backend nuevo de datos.** No se crea ninguna tabla, ninguna migración ni ningún archivo de estado:
    el overview **solo lee** lo que otros planes ya escriben.

---

## 7. Glosario, orden de implementación y DoD

### Glosario (para un modelo menor)

| Término | Significado en Stacky |
|---|---|
| **Panel DevOps** | La pestaña `/devops` de la app. Su shell vive en `frontend/src/pages/DevOpsPage.tsx`. |
| **Sección / sub-tab** | Una entrada del array `DEVOPS_SECTIONS`. Cada una tiene `id`, `label`, `render(ctx)` y opcionalmente un `healthKey` que la gatea. |
| **Contrato §3.12 C20** | "Sumar una sección DevOps futura = 1 entrada en `DEVOPS_SECTIONS` + 1 componente, CERO cambios en `DevOpsPage`". Este plan lo preserva haciendo `group` **opcional**. |
| **C10 / montaje persistente** | Las secciones visitadas nunca se desmontan (se ocultan con `display:none`) para no perder trabajo a medio hacer. |
| **Flag del arnés** | Interruptor `STACKY_*` con 6 patas: `config.py`, categoría en `harness_flags.py`, `FlagSpec`, ayuda llana en `harness_flags_help.py`, key en `/api/devops/health`, y mapa `requires`. Si además lleva `default=True`, suma una **7ª pata**: el alta en `_CURATED_DEFAULTS_ON`. Editable por UI en `Configuración → Arnés`. |
| **`_CURATED_DEFAULTS_ON`** | Set en `backend/tests/test_harness_flags.py:467`. Toda flag con `default=True` en su `FlagSpec` **debe** estar acá o el test del arnés falla. |
| **`FlagGateBanner`** | Banner que reemplaza a una sección cuya flag está apagada y ofrece prenderla desde ahí. |
| **`healthKey`** | Nombre de la key booleana de `GET /api/devops/health` que decide si la sección está habilitada. |
| **DORA** | Cuatro métricas de entrega: frecuencia de despliegue, tasa de fallo del cambio, tiempo de restauración (MTTR) y lead time. Stacky ya calcula las 3 primeras en `services/deploy_planner.py:311`. |
| **CFR** | *Change Failure Rate*: fallos / (fallos + éxitos) en la ventana de 30 días. |
| **MTTR** | Minutos promedio entre un despliegue fallido y el siguiente exitoso. |
| **Bitácora / ledger** | Archivo JSON local append-only. Dos relevantes: despliegues (`services/deploy_store`) y corridas CI (`services/ci_run_ledger`, tope 500 filas). |
| **Drift** | Diferencia entre la versión que Stacky cree desplegada y la que hay en el servidor. **Consultarlo ejecuta un comando remoto** ⇒ excluido del overview. |
| **Snapshot del doctor de conexiones** | Último resultado del chequeo del plan 116, guardado en memoria. Se **lee**; correrlo es un POST explícito del operador. |
| **Ratchet** | Test que congela una métrica de deuda por archivo y solo permite que baje (`uiDebtRatchet`, `HARNESS_TEST_FILES`). |
| **HITL** | *Human in the loop*: el operador decide y confirma; el sistema nunca actúa por su cuenta. |
| **Runtime** | Motor que ejecuta a los agentes: Codex CLI, Claude Code CLI o GitHub Copilot Pro. Nada de este plan depende de cuál esté activo. |
| **Tokens del plan 138** | Variables CSS semánticas de `theme.css`: `--space-*`, `--text-*`, `--radius-*`, `--status-*`, `--transition-*`. Usarlas hace que el módulo herede densidad (plan 150) y tema claro (plan 141) gratis. |
| **`n/d`** | Literal que se muestra cuando un dato es `null`. **Nunca** mostrar `0` por un dato ausente. |
| **`cfr_sample_30d`** *(v2)* | Cuántos despliegues **terminados** (éxito o fallo) entraron en el cálculo del CFR de 30 días. Lo agrega F1.0 a `dora_metrics`. Sin él, "100% de fallos" sobre 1 despliegue se lee igual que sobre 40, y no se puede aplicar el umbral `CFR_MIN_SAMPLE`. |
| **Huella de regresión** *(v2)* | Entrada en `docs/sistema/error_fingerprints.json` que describe una **clase** de error ya muerta, con el test que la vigila (`guard_test`). Convención de la casa para planes tipo-fix: si matás una clase de error, la registrás para que no vuelva por otra puerta. |
| **`ctx.visible`** *(v2)* | Campo opcional del `DevOpsSectionContext` que vale `true` solo para la sección activa. **Ausente ⇒ tratar como visible** (los shells que no lo propaguen degradan al comportamiento de hoy). Toda forma de sondeo periódico —`refetchInterval` y `setInterval`— debe gatearse con él **y** listarlo en las deps de su efecto. |

### Orden de implementación (numerado, no reordenar)

1. **F0** — Flag `STACKY_DEVOPS_COCKPIT_ENABLED` (7 patas) + promoción de `STACKY_DEVOPS_UI_V2_ENABLED`
   a ON + tipos (`cockpit_enabled`, `group`, `summary`, `visible`) + `DevOpsCockpit.module.css` +
   `test_plan239_cockpit_flag.py` + registro de los 3 tests en `HARNESS_TEST_FILES`.
2. **F1.0** *(v2)* — casos nuevos en `test_plan120_planner.py` primero; después las **dos ediciones
   aditivas** de `services/deploy_planner.py` (`FAILED_STATUSES` público + `cfr_sample_30d` en el
   retorno de `dora_metrics`). **Va antes que F1: F1 no se puede escribir sin esto.**
3. **F1** — `test_plan239_devops_overview_service.py` y `test_plan239_devops_overview_endpoint.py`
   **primero** (incluyendo los bloques "Filtros" y los casos de consolidación de F1.3); después
   `services/devops_overview.py` (agregación de **dos llamadas** a `dora_metrics` + tabla de alertas
   F1.2 + `normalize_filters` F1.2b), `get_snapshot()` en `api/devops_connections.py` y
   `GET /api/devops/overview` con sus 3 query params.
4. **F2** — `overviewModel.test.ts` primero (incluido el bloque `buildOverviewClipboardText_*`);
   después `overviewModel.ts`.
5. **F3** — casos nuevos en `DevOpsPage.test.ts` primero; después `DevOps.overview()` en `endpoints.ts`,
   `DevOpsOverviewSection.tsx`, el alta de la sección `resumen`, **F3.4 (el fix del aterrizaje: guard del
   outlet + efecto `landingApplied`, ambos obligatorios)** y **F3.5 (`CopyAsButton`)**.
6. **F4** — `devopsCockpitShell.test.ts` y `DevOpsCockpitRegression.test.ts` primero; después
   `devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, los 10 `group:` y el cableado de 3 ramas.
7. **F5** — casos de `resolveLandingSection` primero; después `App.tsx:307` (1 línea), la prop `subTab`, el
   `lastApplied`, el write-back con `replaceState` y el control "Fijar como inicio". **No re-implementa el
   aterrizaje: solo alimenta con `subTab`/`pinned` el efecto que ya dejó F3.4.**
8. **F6** — `devopsPollingRatchet.test.ts` primero (las **dos** formas: `refetchInterval` y
   `setInterval`); después el `sectionCtx` con `visible`, el gateo de `DeploymentsSection.tsx:50` y el de
   los **dos** `setInterval` de `TriggerPipelineSection.tsx` (`:207`, `:293`) **con `ctx.visible` en las
   deps de ambos efectos**.
9. **F7a** — `devopsDesignTokens.test.ts` primero; después las sustituciones de tokens, los **9** hex → 0
   (incluido `PrReviewerSection.module.css`) y el bloque responsive.
10. **F7b** — barrido de los 8 archivos acotados, verificando el ratchet después de cada uno; regenerar el
    baseline **una vez** al final y re-correrlo sin la env.
11. **F8** — `DevOpsCockpitClosure.test.ts` + **F8.2 (las 2 huellas en `error_fingerprints.json`)** + la
    suite completa + el checklist visual de 8 puntos.
12. **Commit** con pathspec explícito por archivo (riesgo R15). **Sin `git push`** salvo pedido del
    operador. **Sin `--no-verify`.** Al commitear, completar `killed_commit` de las 2 huellas de F8.2 con
    el hash real (segundo commit chico, o `git commit` del JSON después del principal).

### Definición de Hecho (DoD) global

- [ ] Los **12 KPIs** de §1 verificados con su comando (KPI-8 con el techo declarado en §F7b: **≤ 386**).
- [ ] **(v2, C1)** El panel **nunca** queda en blanco: `/devops/despliegues` en frío, un `pinned` guardado
      y el cockpit OFF renderizan su sección — verificado por los 3 casos de F3.4 en
      `DevOpsCockpitRegression.test.ts` **y** por los pasos 4-6 del checklist visual.
- [ ] **(v2, C1)** El aterrizaje se decide con la salud ya cargada (nada de `useState(() => resolve…)`):
      con el cockpit ON, `/devops` en frío abre **Resumen**, no `pipelines`.
- [ ] **(v2, C2)** `dora_metrics` ganó `cfr_sample_30d` sin perder ninguna de sus 5 claves, y el CFR
      consolidado es sobre el total (caso testigo 0.25 vs. el 0.5 del promedio de promedios).
- [ ] **(v2, C3)** Censo de sondeo de `components/devops/`: **0** `refetchInterval` y **0** `setInterval`
      sin guarda de visibilidad; el sondeo **se reanuda** al volver a la sección.
- [ ] **(v2, C10)** Las 2 huellas de F8.2 están en `docs/sistema/error_fingerprints.json` (15 entradas)
      con su `guard_test` apuntando a un test que existe y pasa.
- [ ] Los 3 filtros (aplicación / proyecto de CI / ventana 7-14-30 d) recortan KPIs, series, alertas y
      actividad; un valor inválido no devuelve 400 y el selector refleja lo **aplicado** (KPI-11).
- [ ] `GET /api/devops/overview` responde **200** en una instalación virgen, con `status: "unknown"`, los
      4 bloques declarados y **sin** abrir red, ejecutar comandos remotos ni invocar LLM.
- [ ] `/devops` aterriza en **Resumen**; la fila primaria tiene **4** grupos; las secciones con flag
      apagada están en el desplegable "Deshabilitadas (N)" y siguen siendo alcanzables.
- [ ] `/devops/<seccion>` funciona en los dos sentidos (URL → sección y click → URL con `replaceState`),
      **sin** haber modificado `services/routes.ts`.
- [ ] Ninguna sección oculta sondea: `devopsPollingRatchet.test.ts` verde con la allowlist **vacía**.
- [ ] Con `STACKY_DEVOPS_COCKPIT_ENABLED=OFF`: panel del plan 119 con sus 9 secciones,
      `ConnectionHealthStrip` presente y `DevOpsShellV2Regression.test.ts` verde **sin modificarlo**.
- [ ] Con `STACKY_DEVOPS_UI_V2_ENABLED=OFF` (además del cockpit OFF): shell v1 legacy intacto.
- [ ] `0` hex de color en **todos** los `.module.css` de `components/devops/` (incluido
      `PrReviewerSection.module.css`, v2 C9), en `DevOpsPage.module.css` y en `DevOpsCockpit.module.css`;
      este último sin px crudos en spacing.
- [ ] Densidad compacta (plan 150) y tema claro (plan 141) se aplican al panel DevOps.
- [ ] `npx tsc --noEmit` verde y **todos** los comandos de la suite de F8 verdes.
- [ ] Los 3 tests nuevos de backend están en `HARNESS_TEST_FILES` y `test_harness_ratchet_meta.py` verde.
- [ ] `test_harness_flags.py`, `test_harness_flags_requires.py` y `test_plan119_devops_ui_v2_flag.py`
      verdes (el último, con su aserto actualizado a `is True`).
- [ ] Paridad de runtimes declarada y cierta: no existe **ninguna** bifurcación por runtime en el código
      agregado (verificable con `grep -rn "codex_cli\|claude_code_cli\|copilot" ` sobre los archivos
      nuevos de este plan ⇒ **0 hits**).
- [ ] **Trabajo del operador: ninguno.** Dos flags default ON, sin credenciales, sin config, sin pasos
      manuales, backward-compatible.
- [ ] Ninguna acción automática nueva: el cockpit no despliega, no dispara, no ejecuta, no notifica.
      La única acción que agrega la v2 —"Copiar resumen" (F3.5)— es **local y por clic explícito**: no
      envía nada a ningún lado, y si `STACKY_COPY_EXPORT_ENABLED` está OFF el botón ni aparece.
- [ ] Lo que quedó afuera está **declarado** en §6 (13 archivos de deuda inline, roving tabindex, vistas
      guardadas, atajos, notificaciones) — sin caps silenciosos.
