# Plan 192 — Resiliencia de conexión dashboard-backend: monitor pasivo, probe con backoff, banner global y re-hidratación sin F5

**Estado:** CRITICADO v2 (v1 → v2 aplicada; veredicto v1: APROBADO-CON-CAMBIOS)
**Fecha:** 2026-07-18 (v1 y crítica v2 el mismo día)
**Crítico v2:** StackyArchitectaUltraEficientCode (juez adversarial, pipeline criticar-y-mejorar-plan)
**Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
**Tema:** UX/UI — valor perceptible inmediato, onboarding cero, sin configuración.
**Audiencia:** un modelo menor (Haiku / Codex / Copilot) debe poder implementarlo SIN inferir nada. Todo símbolo citado fue verificado contra el repo con `archivo:línea` el 2026-07-18.
**Coexistencias declaradas:** plan 156 (latido único, CRITICADO v2, NO implementado) — ver §3 D11; `HealthBanner.tsx` existente — ver §3 D10 y F5.

---

## CHANGELOG v1 → v2 (crítica adversarial 2026-07-18)

Veredicto v1: **APROBADO-CON-CAMBIOS**. Muestreo de anclas: TODAS las citas archivo:línea verificadas exactas (cero anclas falsas). Hallazgos: 4 IMPORTANTES + 8 MENORES + 1 adición. Cambios aplicados:

- **C1 (IMPORTANTE, venv equivocado):** todos los comandos backend decían `venv\Scripts\python.exe`; verificado en vivo 2026-07-18: `venv` = Python 3.11.9 (WIP ajeno, untracked hoy) y `.venv` = Python 3.13.5 (canónico, corre el arnés). v2 usa `.venv\Scripts\python.exe` en F0 y §9 + advertencia §10.9.
- **C2 (IMPORTANTE, gate insatisfacible):** `tests/test_harness_ratchet_meta.py` está ROJO en HEAD por drift AJENO (corrido 2026-07-18: `1 failed, 2 passed`; `test_ratchet_clasifica_todos_los_tests` lista tests de los planes 98/122/126/139 y otros nunca registrados). El criterio v1 "verde" era imposible sin scope creep. v2 fija el criterio honesto (lista de no-clasificados idéntica a HEAD, sin el archivo nuevo) en F0.
- **C3 (IMPORTANTE, F6 mentiría):** `reportSuccess()` en `healthy` no regenera el snapshot (a propósito, para no re-renderizar por request) ⇒ `snapshot.lastOkAt` queda CONGELADO desde la última transición y el `title` del dot F6 mostraría "hace 3600s" con backend sano. v2 agrega `getLastOkAt()` (lectura VIVA de la variable interna), F6 lo usa, test t19 lo fija.
- **C4 (IMPORTANTE, inventario incompleto):** D1 v1 presentaba los 7 `fetch` de `endpoints.ts` como inventario completo fuera del choke-point. Verificado: hay al menos 6 call-sites más (`App.tsx:154`, `services/preferences.ts:40`/`:69`, `hooks/useTicketSync.ts:89`, `components/AssignmentRecommendationPanel.tsx:58`, `components/HarnessFlagsPanel.tsx:405`, `utils/flagHealth.ts:39`) + 1 `EventSource` (`hooks/useExecutionStream.ts:135`). v2 los declara todos con la regla: NINGUNO se instrumenta.
- **C5 (MENOR, K1 sobre-prometía):** "CERO requests" literal era falso: `connectionFlags` hace UNA lectura de flag por sesión al montar el host. v2 precisa "cero requests recurrentes" en K1/§2.6/D11.
- **C6 (MENOR):** F0 decía "patrón EXACTO de `STACKY_COST_CENTER_ENABLED`" pero el código v1 usaba `.lower() in ("true","1","yes")`; el patrón real (`config.py:543-545`) es `.strip().lower() == "true"`. v2 alinea el código al patrón citado.
- **C7 (MENOR):** el comentario del contrato §4 decía `"sin datos aún"`; el string fijado por tests F3 es `"Sin respuesta del backend aún"`. v2 alinea §4.
- **C8 (MENOR, duplicación):** v1 exportaba `GATEWAY_DOWN_STATUSES` del monitor Y hacía que `client.ts` declarara su copia local `GATEWAY_DOWN`. v2: `client.ts` IMPORTA `GATEWAY_DOWN_STATUSES` (fuente única; la arista client→monitor ya existía en D7).
- **C9 (MENOR, gotcha 6×):** los gates grep del §9 se rompen si un comentario del código contiene el token gateado (gotcha recurrido 6 veces en este repo). v2 agrega la advertencia §10.10.
- **C10 (MENOR):** vitest node env NO tiene `localStorage`; los casos de cache de `connectionFlags.test.ts` necesitan `vi.stubGlobal`. v2 lo especifica en F2.
- **C11 (MENOR, punto ciego):** `request()` no tiene timeout (verificado `client.ts:67-81`) ⇒ un backend COLGADO (proceso vivo que no responde) no genera señal pasiva hasta el timeout del propio navegador. v2 lo declara en R4 con por qué se acepta.
- **C12 (MENOR, a11y):** una live region que se INSERTA ya con contenido no siempre se anuncia (SR/navegador dependiente). v2 usa patrón announcer: `role="status"` PERSISTENTE (sr-only) mientras la flag está ON + mensaje visual `aria-hidden` (el gate `aria-hidden` de F3 pasa de 1 a 2).
- **[ADICIÓN ARQUITECTO] (D13, K11, t20/t21):** eventos `online`/`offline` del navegador como señal pasiva gratuita: `offline` ⇒ fallo inmediato (suspect+probe); `online` en `suspect`/`down` ⇒ probe inmediato (recovery instantáneo al volver la red, sin esperar el backoff). Cero timers/requests en sano; el caso localhost se auto-corrige (el probe confirma).

---

## 0. Contexto y gap real (evidencia verificada)

El backend Flask local se reinicia seguido (deploys frecuentes vía `START.bat`). Cuando eso pasa, hoy la SPA queda viva pero ciega, y cada página degrada por su lado:

1. `react-query` está configurado con `staleTime: 30_000, retry: 1` (`frontend/src/main.tsx:9-11`): cada query que falla durante la caída queda en estado de error o con datos viejos, sin ninguna señal global ni re-intento coordinado.
2. El único aviso existente es `HealthBanner` (`frontend/src/components/HealthBanner.tsx`, montado en `App.tsx:260`): polea `GET /api/diag/local` cada 30 s (`HealthBanner.tsx:22` `POLL_MS = 30_000`, loop `:67-94`) y solo en su `catch` (`:80-88`) muestra "El backend no responde". Problemas concretos:
   - Ventana ciega de hasta 30 s para detectar la caída (y otros 30 s para notar la recuperación).
   - El dismiss "ocultar por 30 minutos" (`:141-151` + `persistDismissed :45-48`) puede suprimir el aviso de backend caído durante media hora.
   - Usa `role="alert"` (`:116`) — grita, no informa.
   - Al volver el backend, el banner desaparece en silencio y **nada re-hidrata las páginas**: los datos viejos y los errores quedan hasta que el operador aprieta F5.
3. No existe probe de recuperación con backoff, ni contador de intentos, ni un "momento mágico" de vuelta.
4. `Toast.tsx` (`frontend/src/components/Toast.tsx`) es efímero por diseño: no sirve como superficie persistente de estado de conexión.

**Qué instala este plan:** (a) monitor de conexión 100% pasivo derivado de las requests YA existentes (interceptor en el choke-point del api-client); (b) probe de recuperación con backoff exponencial SOLO mientras está caído; (c) banner global accesible y no intrusivo con contador de intentos y botón "Reintentar ahora"; (d) al recuperar, UNA invalidación global de react-query que re-hidrata todas las páginas sin F5 (el momento mágico); (e) opcional acotado: punto de frescura en la TopBar. Cero trabajo del operador; flag default ON.

---

## 1. KPIs binarios (verificables al cierre)

| # | KPI | Verificación binaria |
|---|-----|----------------------|
| K1 | En estado `healthy` el plan agrega CERO requests RECURRENTES y CERO timers (única request nueva: 1 lectura de flag por sesión al montar el host, F2/D9 — C5) | Test F1 t1 (con señales de éxito, `deps.schedule` jamás se llama) + gate `grep -c 'setInterval' src/services/connectionMonitor.ts` = 0 |
| K2 | Primera señal de fallo de red dispara 1 probe de confirmación inmediato (sin banner todavía) | Test F1 t2/t3 |
| K3 | En `down`, los delays del probe son exactamente 1000, 2000, 4000, 8000, 16000, 30000, 30000, ... ms | Test F1 t6 |
| K4 | El probe se detiene al recuperar y se pausa con la pestaña oculta | Tests F1 t7/t10 |
| K5 | Por ciclo caída→recuperación se dispara EXACTAMENTE 1 `invalidateQueries()` global | Test F1 t7 (onRecovered una vez) + test F4 + gate `grep -c 'invalidateQueries' src/services/connectionRecovery.ts` = 1 |
| K6 | Ninguna mutación (POST/PUT/DELETE) se reintenta automáticamente | Test F2 (semántica de `request()` intacta: sigue lanzando el mismo Error) + §3 D6 |
| K7 | Flag OFF ⇒ cero timers, cero probes, cero banner, comportamiento actual intacto | Test F1 t12 (disabled ⇒ máquina inerte) + F3 (host devuelve null) |
| K8 | Banner accesible: live region `role="status"` + `aria-live="polite"` PERSISTENTE (announcer sr-only, C12); mensaje visual y contador con `aria-hidden` (no re-anuncian) | Gates grep de F3 (= 1, = 1, `aria-hidden` = 2) |
| K9 | `HealthBanner` no duplica el aviso de backend caído con el monitor activo | Diff F5 + `tsc --noEmit` verde |
| K10 | Todo verde: pytest por archivo (F0), vitest por archivo (F1-F4/F6), `tsc --noEmit`, gates grep | Comandos exactos en §9 DoD |
| K11 | [ADICIÓN ARQUITECTO] evento `offline` ⇒ fallo pasivo inmediato; evento `online` en `suspect`/`down` ⇒ probe inmediato | Tests F1 t20/t21 |

---

## 2. Principios no negociables (codificados)

1. **Human-in-the-loop.** Nada se auto-ejecuta salvo re-FETCHES de lectura. La invalidación de queries de react-query es un refresh de datos (GET), NO una acción de negocio: no crea, no muta, no publica. **PROHIBIDO reintentar automáticamente requests de mutación (POST/PUT/DELETE):** fallan y se reportan exactamente como hoy (`client.ts:76-79` sigue lanzando); el monitor solo OBSERVA el resultado.
2. **Cero trabajo del operador.** Flag `STACKY_CONNECTION_RESILIENCE_ENABLED` bool default **ON**, editable por UI (HarnessFlagsPanel). **Ninguna de las 4 excepciones duras aplica**, revisadas una por una: (1) *bypass de revisión humana* — NO: el plan solo observa requests y re-fetchea lecturas; ninguna decisión del operador se saltea; (2) *destructiva/irreversible* — NO: cero escrituras, cero borrados; el probe es un GET read-only a `/api/diag/health` (docstring "Solo lectura: no muta nada", `backend/api/diag.py:322`); (3) *prerequisito no garantizado* — NO: solo usa el api-client, react-query y un endpoint que existen en toda instalación; (4) *reduce seguridad* — NO: no toca auth ni secretos; OFF ⇒ idéntico a hoy.
3. **Paridad de 3 runtimes: N/A-por-diseño, declarada por fase.** Feature 100% frontend + 1 flag de arnés backend + LECTURA de un endpoint backend existente. No toca el camino de ejecución/publicación de Codex, Claude Code ni Copilot. Cada fase lo declara en 1 línea.
4. **Mono-operador sin auth.** Sin RBAC ni `user_id`: `current_user` es un header sin validar y acá ni se usa.
5. **Reuso.** api-client central (`client.ts`), react-query ya instalado (`@tanstack/react-query ^5.59.0`, `frontend/package.json:13`), tokens de `theme.css`, patrón de flag triple del repo, patrón de lógica pura + cáscara fina (`integrationHealth.logic.ts:1-10` lo documenta explícitamente), `Button` del barrel `ui/` (`frontend/src/components/ui/index.ts:7`).
6. **No degradar performance.** El interceptor es O(1) por request (dos llamadas a funciones síncronas). En estado sano NO hay timers ni requests recurrentes nuevas (los listeners de `visibilitychange`/`online`/`offline` son eventos, no timers; la única request nueva es la lectura de flag 1 vez por sesión — C5). El probe usa `setTimeout` encadenado (nunca `setInterval`) y solo corre en `suspect`/`down`.
7. **Backward-compatible.** Ningún caller de `api.*`/`rawPost` cambia de semántica: mismos throws, mismos tipos de retorno. Flag OFF ⇒ UI y red idénticas a hoy.
8. **Ratchets del repo.** (a) uiDebtRatchet: `.tsx` nuevos con CERO `style={{}}` — todo en `*.module.css`; valores dinámicos por clase condicional (este plan no necesita `ref`+`setProperty`). (b) formDebtRatchet: cero tags crudos de form en `.tsx` nuevos — el único control es el botón "Reintentar ahora" con `Button` del barrel (`div`/`span` contenedores están permitidos). (c) Test backend nuevo registrado en `HARNESS_TEST_FILES` (sh Y ps1). (d) Colores SOLO con tokens `var(--...)` de `theme.css`; cero hex.
9. **Tests sin DOM.** `@testing-library/react` y `jsdom` NO están en `frontend/package.json` (gap estructural conocido; hay `.test.tsx` legacy que los importan y NO corren — no imitarlos). TODA la lógica vive en módulos `.ts` PUROS con vitest (`vitest ^4.1.9`, `package.json:30`) corrido POR ARCHIVO; los `.tsx` son cáscaras finas verificadas con `tsc --noEmit` + smoke manual documentado (F7). Precedentes reales: `src/services/briefDraft.test.ts`, `src/services/format.test.ts`, `src/components/integrationHealth.logic.ts`, `src/utils/__tests__/agentCompletionRecovery.integration.test.ts` (core de react-query sin DOM).
10. **Coexistencia con el plan 156 (no implementado).** El 156 impone KPI ≤2 requests/tick e idle backoff para el polling sano. Este plan NO agrega polling en estado sano (detección 100% pasiva por interceptor) y el probe corre SOLO durante la caída (cuando no hay tick que proteger) y se detiene al recuperar. Ver §3 D11.

---

## 3. Decisiones de diseño (D1..D13, con evidencia)

### D1 — Punto único de intercepción: `client.ts`

El api-client central es `frontend/src/api/client.ts`. `endpoints.ts:1` importa `{ api, apiBase, rawPost, ... }` de `./client`. Los dos caminos de red del client son:

- `request<T>()` (`client.ts:67-81`): envuelve `fetch` y es el ÚNICO camino de `api.get/post/put/patch/delete/postWithHeaders` (`client.ts:83-100`). **Choke-point principal.**
- `rawPost<T>()` (`client.ts:28-63`): fetch propio para respuestas estructuradas. **Segundo punto, en el MISMO archivo.**

Ambos se instrumentan en F2. **Inventario COMPLETO del tráfico fuera del choke-point (verificado 2026-07-18; C4):**

- (a) 7 `fetch` directos en `endpoints.ts`: `:166` (sync-v2), `:916` (harness-flags PUT — comentario `:911-914` explica por qué es fetch directo), `:2682` (code-integrity), `:3539` (download-setup), `:4033`/`:4038` (DbCompare files), `:4171` (incidents multipart).
- (b) 6 call-sites más FUERA de `endpoints.ts`: `App.tsx:154` (lee `shell_v2_enabled` de `/api/diag/health` con fetch crudo — el MISMO endpoint del probe), `services/preferences.ts:40` (GET) y `:69` (PUT), `hooks/useTicketSync.ts:89`, `components/AssignmentRecommendationPanel.tsx:58`, `components/HarnessFlagsPanel.tsx:405` (profile PUT), `utils/flagHealth.ts:39` (default de un `fetchImpl` inyectable).
- (c) 1 `EventSource` (`hooks/useExecutionStream.ts:135`, SSE de logs — no es request/response; irrelevante para la señal).

**Regla dura: NINGUNO de estos sitios se instrumenta** (fuera de scope §7): son minoritarios, el tráfico dominante pasa por `request()`, y el estado `down` lo confirma el probe igual. Un modelo menor NO debe "completar" la cobertura instrumentándolos.

### D2 — Semántica de la señal (qué cuenta como fallo de conexión)

- **Fallo de conexión** = (a) el `fetch` RECHAZA (típicamente `TypeError: Failed to fetch`) EXCLUYENDO `AbortError` (cancelación del caller, no es caída), o (b) respuesta HTTP con status ∈ {502, 503, 504} (statuses de gateway que el Flask local nunca emite legítimamente).
- **Éxito de conexión** = cualquier otra respuesta HTTP, incluidos 4xx/5xx restantes: un 500 del backend significa backend VIVO con un bug — eso ya tiene sus superficies de error propias y NO debe encender este banner.
- Detección de abort: `e instanceof DOMException && e.name === "AbortError"`.
- Limitación conocida en dev: ver §6 R7 (proxy de Vite, `vite.config.ts:13-15`).

### D3 — Máquina de estados

```
healthy --fallo--> suspect --probe falla--> down --probe/éxito pasivo ok--> recovering --linger 4000ms--> healthy
   ^                  |                      ^                                   |
   |                  +--probe ok / éxito ---+----(fallo durante recovering)-----+--> suspect (probe inmediato)
   |                      pasivo (falsa alarma, sin ceremonia)
   +--éxito pasivo en cualquier estado no-down (suspect) ⇒ healthy directo
```

- `healthy` + fallo → `suspect` + **1 probe inmediato de confirmación** (disparado por el fallo, NO es polling sano). Sin banner en `suspect` (anti falso-positivo por UNA request fallida).
- `suspect` + probe ok o éxito pasivo → `healthy` (falsa alarma; SIN `onRecovered`, SIN invalidación).
- `suspect` + probe falla → `down`: banner visible, arranca el loop de backoff.
- `down` + probe ok **o éxito pasivo** → `recovering`: dispara `onRecovered` (exactamente una vez por ciclo), banner "Backend de vuelta — actualizando…", y a los `RECOVERY_LINGER_MS` (timer propio de la máquina) → `healthy`.
- `recovering` + fallo → `suspect` + probe inmediato (nuevo ciclo).
- **Regla determinista:** la invalidación global se dispara SOLO en la transición que SALE de `down`.
- **Generación (`gen`):** contador entero incrementado en cada transición; los callbacks de probe capturan `gen` y se ignoran si al resolver la máquina ya transicionó (resultados stale de probes en vuelo).

### D4 — Probe de recuperación

- `fetch` CRUDO (NO `api.get`: `request()` no tiene timeout y lanzaría en !ok) a `probeUrl` = `` `${apiBase}/api/diag/health` `` con `AbortController` y timeout `PROBE_TIMEOUT_MS` (5000 ms). Éxito = `res.ok === true`; fallo = rechazo, timeout o `!res.ok`. Así "backend lento" (> 5 s el probe) no se confunde con sano, y en dev el 500 del proxy de Vite cuenta como fallo del probe (recovery correcto también en dev).
- El probe corre SOLO en `suspect` (1 disparo) y `down` (loop con backoff). `setTimeout` encadenado, jamás `setInterval`.
- **Pestaña oculta:** si `isHidden()` al momento de programar o disparar, no se hace la request; se marca `pendingWhileHidden = true` y al `visibilitychange` a visible (estando en `suspect`/`down`) se dispara probe inmediato.
- La ruta HTTP verificada: blueprint `api` con `url_prefix="/api"` (`backend/api/__init__.py:63`) + blueprint `diag` con `url_prefix="/diag"` (`backend/api/diag.py:40`) + `@bp.get("/health")` (`diag.py:311`) ⇒ **`GET /api/diag/health`**, sin flag, read-only (`diag.py:322`). El frontend ya la consume (`endpoints.ts:2689-2691`, `App.tsx:156`).

### D5 — Backoff exponencial

Delays entre probes tras entrar a `down` (k = probes ya disparados en este ciclo `down`): `min(1000 * 2^k, 30000)` ⇒ 1000, 2000, 4000, 8000, 16000, 30000, 30000, ... `attempt` (mostrado en el banner) = probes disparados en el ciclo `down` actual; el probe de confirmación de `suspect` NO cuenta. `probeNow()` ("Reintentar ahora"): cancela el timer pendiente y dispara probe inmediato (`attempt++` si está en `down`); si falla, se reprograma con el delay que corresponde al nuevo k (el backoff NO se resetea por el click). Todo se resetea al salir de `down`.

### D6 — Re-hidratación global (el momento mágico)

Al salir de `down`: UNA llamada `queryClient.invalidateQueries()` sin filtro (react-query v5): marca TODAS las queries stale y re-fetchea SOLO las activas (con observers montados — `refetchType: 'active'` es el default de v5). Eso acota el thundering herd por diseño: se re-fetchea la página visible (típicamente 2-6 requests contra el Flask local), y las inactivas se re-hidratan al montar. No hace falta escalonado. Las mutaciones NUNCA se re-disparan: `invalidateQueries` no toca mutations.

### D7 — Grafo de imports acíclico

- `client.ts` importa SOLO `{ reportConnectionSuccess, reportConnectionFailure }` de `services/connectionMonitor.ts`.
- `connectionMonitor.ts` NO importa NADA de `api/` (ni `apiBase` ni `endpoints`): el `probeUrl` llega por `enable({ probeUrl })` desde el host `ConnectionBanner.tsx`, que sí puede importar ambos sin ciclo.
- `connectionFlags.ts` importa `endpoints.ts` (no al revés). `connectionRecovery.ts` importa solo `@tanstack/react-query` (tipos).

### D8 — Singleton + StrictMode + useSyncExternalStore

- El monitor es un singleton a nivel módulo (creado al importar, no en un componente). `main.tsx:18` monta bajo `React.StrictMode` (double-mount de effects en dev): por eso `enable()`/`disable()` son idempotentes (boolean interno) y `setOnRecovered` es un SLOT ÚNICO reemplazable (nunca un array acumulativo).
- La UI se suscribe con `useSyncExternalStore(subscribe, getSnapshot)` (React 18). `getSnapshot()` devuelve LA MISMA referencia de objeto si no hubo cambios (requisito de estabilidad del hook): el snapshot se recalcula solo dentro de `_transition()`/`_notify()`.
- Mientras `enabled === false`, los reportes pasivos actualizan SOLO `lastOkAt`/`lastFailureAt` (sin transiciones, sin timers). Al hacer `enable()`, si el último fallo registrado es más reciente que el último éxito Y tiene menos de `STARTUP_SIGNAL_WINDOW_MS` (10000 ms), la máquina entra directo a `suspect` + probe inmediato (cubre el arranque en frío con backend ya caído, donde las queries iniciales fallaron ANTES de que el host montara). Si no, arranca `healthy` sin ninguna request.

### D9 — Flag triple + lectura frontend fail-open

- Backend: patrón triple verificado — `FlagSpec` en `FLAG_REGISTRY` (`backend/services/harness_flags.py`), key agregada a `_CATEGORY_KEYS["interfaz_ui"]` (`harness_flags.py:117` dict, tupla `interfaz_ui` en `:326-328`, hoy contiene solo `STACKY_UI_SHELL_V2_ENABLED`), default efectivo en `backend/config.py` (patrón exacto de `STACKY_COST_CENTER_ENABLED`, `config.py:543-545`), y alta en `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`).
- Frontend: `connectionFlags.ts` replica el patrón del plan 187 F0 (`bulkFlags.ts`) de forma AUTOCONTENIDA (los planes 185/187 NO están implementados: PROHIBIDO importar código de ellos; se duplica el patrón): lookup literal de key/value en `HarnessFlags.list()` (`endpoints.ts:909-910`; `HarnessFlagView.value: boolean | number | string`, `endpoints.ts:711`), promesa cacheada a nivel módulo (1 request por sesión), cache `localStorage` anti-flash.
- **Fail-open deliberado:** si la lectura de la flag falla (backend caído al arrancar — EXACTAMENTE el escenario para el que existe la feature), se usa el cache y en su defecto `true`. Un modelo menor NO debe "resolver" esto al revés: fail-closed dejaría la feature muerta en su escenario principal.
- OFF ⇒ el host no monta contenido, `enable()` nunca corre, cero timers, cero probes (K7).

### D10 — Coexistencia con `HealthBanner` (existente)

`HealthBanner` NO se reemplaza (sus checks propios — tracker, database, watchers y el resto de los que enumera `HealthBanner.tsx` — siguen siendo suyos). Dos puntos:
1. Su poll de 30 s usa `api.get` (`HealthBanner.tsx:69`) ⇒ pasa por `request()` ⇒ **alimenta la detección pasiva**: incluso con el dashboard idle hay una señal cada ≤30 s sin que este plan agregue nada.
2. Su branch `catch` (`HealthBanner.tsx:80-88`) muestra "El backend no responde" — con el monitor activo serían DOS banners para lo mismo. F5 hace que `HealthBanner` CEDA esa superficie cuando el monitor está habilitado (diff mínimo de 6 líneas). Con la flag OFF, `HealthBanner` se comporta exactamente como hoy.

Nota de desambiguación: `components/devops/ConnectionHealthStrip.tsx` es OTRO dominio (conexiones a servidores remotos DevOps, plan 116) — solo homónimo; no se toca. `IntegrationHealthBanner.tsx` (plan 148) es salud de integraciones externas (ADO/GitLab) — tampoco se toca.

### D11 — Coexistencia con el plan 156 (latido único, NO implementado)

El monitor es agnóstico a las FUENTES de tráfico: solo observa lo que pasa por `client.ts`. Hoy el piso pasivo lo dan el poll de `HealthBanner` (≤30 s) y el tráfico de las páginas. Cuando el 156 aterrice, su latido único pasará por el MISMO `request()` y se volverá la señal pasiva dominante; si el 156 consolida o elimina pollers (incluido el de `HealthBanner`), este monitor NO cambia. Este plan no agrega ni una request RECURRENTE en estado sano (la única request nueva es la lectura de flag, 1 vez por sesión al montar el host — no toca ningún tick; C5) ⇒ no viola el KPI ≤2 requests/tick del 156; el probe corre SOLO caído (no hay tick sano que proteger) y se detiene al recuperar.

### D12 — Accesibilidad del banner (announcer persistente, C12)

- **Announcer persistente (C12):** una live region que se INSERTA en el DOM ya con contenido no siempre se anuncia (comportamiento inconsistente entre lectores/navegadores). Por eso el `span` con `role="status"` + `aria-live="polite"` está SIEMPRE montado mientras la flag está ON (clase `.srOnly`, visualmente invisible) y lo que cambia es su TEXTO: `""` ↔ mensaje de estado. La reconexión no debe gritar (`aria-live="assertive"`/`role="alert"` PROHIBIDOS acá).
- El mensaje VISUAL del banner es una copia con `aria-hidden="true"` (evita el doble anuncio); el contador "(intento N)" vive en un `span` con `aria-hidden="true"`: el tick del contador NO re-anuncia en cada probe. El texto del live region cambia SOLO en transiciones de estado (2 mensajes posibles + vacío).
- Decisión documentada: el lector de pantalla no oye el número de intento (es información visual secundaria); oye "Sin conexión con el backend — reintentando…" una vez y "Backend de vuelta — actualizando…" una vez.

### D13 — [ADICIÓN ARQUITECTO] Eventos `online`/`offline` del navegador como señal gratuita

- Evento `window "offline"` ⇒ se trata como fallo pasivo (mismo camino que `reportFailure()`): `healthy → suspect` + probe inmediato. Evento `window "online"` estando en `suspect`/`down` ⇒ cancelar el timer pendiente y probe inmediato (recovery instantáneo al volver la red, sin esperar el backoff vigente); en `healthy`/`recovering` el evento `online` NO hace nada.
- **Caso localhost (mono-operador):** perder la red NO rompe necesariamente `localhost` (loopback sigue vivo). No importa: el probe CONFIRMA — si el backend local responde, `suspect → healthy` sin banner ni ceremonia (falsa alarma auto-corregida por la máquina existente, D3). Donde sí brilla: dashboard accedido desde otra máquina (VPN/red local), donde el `offline`/`online` del cliente es señal real.
- Cero costo en sano: son LISTENERS (eventos), no timers ni requests; se registran en `enable()` y se remueven en `disable()` (simetría total con `visibilitychange`).
- Un modelo menor NO debe "optimizar" esto gateando probes con `navigator.onLine` (es notoriamente poco fiable como ESTADO): solo se usan los EVENTOS, y siempre confirmando con probe. Tests t20/t21; KPI K11.

---

## 4. Contratos y constantes (código exacto)

Archivo nuevo `frontend/src/services/connectionMonitor.ts` exporta:

```ts
export type ConnectionStatus = "healthy" | "suspect" | "down" | "recovering";

export interface ConnectionSnapshot {
  status: ConnectionStatus;
  /** Probes disparados en el ciclo down actual (0 fuera de down). */
  attempt: number;
  /** Epoch ms de entrada al estado down del ciclo actual (null fuera de down). */
  downSince: number | null;
  /** Última señal de éxito de conexión (pasiva o probe), epoch ms. */
  lastOkAt: number | null;
  /** Última transición down→recovering, epoch ms. */
  lastRecoveredAt: number | null;
  enabled: boolean;
}

export const PROBE_TIMEOUT_MS = 5000;
export const BACKOFF_BASE_MS = 1000;
export const BACKOFF_FACTOR = 2;
export const BACKOFF_CAP_MS = 30000;
export const RECOVERY_LINGER_MS = 4000;
export const STARTUP_SIGNAL_WINDOW_MS = 10000;
/** Fuente ÚNICA de los statuses de gateway (C8): client.ts la IMPORTA; PROHIBIDO duplicar el Set. */
export const GATEWAY_DOWN_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

export interface MachineDeps {
  now(): number;
  schedule(fn: () => void, ms: number): unknown;   // handle opaco
  cancel(handle: unknown): void;
  probe(url: string, timeoutMs: number): Promise<boolean>; // true = res.ok
  isHidden(): boolean;
  /** Registra cb de visibilidad; devuelve unsubscribe. */
  onVisibilityChange(cb: () => void): () => void;
  /** [ADICIÓN ARQUITECTO] D13 — eventos de red del navegador; devuelven unsubscribe. */
  onOnline(cb: () => void): () => void;
  onOffline(cb: () => void): () => void;
}

export interface ConnectionMachine {
  reportSuccess(): void;
  reportFailure(): void;
  enable(opts: { probeUrl: string }): void;
  disable(): void;
  setOnRecovered(fn: (() => void) | null): void;
  probeNow(): void;
  subscribe(listener: () => void): () => void;
  getSnapshot(): ConnectionSnapshot;
  /** C3: lectura VIVA de lastOkAt (NO la copia del snapshot, que solo se regenera al transicionar). F6 la usa. */
  getLastOkAt(): number | null;
}

/** Factory PURA (testeable con deps fake). */
export function _createConnectionMachine(deps: MachineDeps): ConnectionMachine;

/** Singleton cableado con deps reales (window.setTimeout, document.hidden, fetch+AbortController). */
export const connectionMonitor: ConnectionMachine;

/** Atajos que usa client.ts (delegan en el singleton). */
export function reportConnectionSuccess(): void;
export function reportConnectionFailure(): void;

/** F5: true si el monitor está habilitado (ConnectionBanner es dueño de la superficie "backend caído"). */
export function connectionMonitorOwnsBackendSurface(): boolean;
```

Archivo nuevo `frontend/src/services/connectionBanner.logic.ts` exporta:

```ts
import type { ConnectionSnapshot } from "./connectionMonitor";

export interface BannerView {
  visible: boolean;
  kind: "down" | "recovering" | null;
  message: string;        // string exacto, ver F3
  attemptText: string | null; // "(intento N)" o null
  showRetry: boolean;
}
export function computeBannerView(s: ConnectionSnapshot): BannerView;

/** F6: "Última respuesta del backend hace Xs" (o "Sin respuesta del backend aún" si lastOkAt es null — string EXACTO fijado por los tests F3; C7). */
export function freshnessLabel(lastOkAt: number | null, now: number): string;
```

Archivo nuevo `frontend/src/services/connectionRecovery.ts` exporta:

```ts
import type { QueryClient } from "@tanstack/react-query";
/** Handler de recuperación: UNA invalidación global (refetch de lecturas activas). */
export function makeRecoveryHandler(qc: QueryClient): () => void {
  return () => { void qc.invalidateQueries(); };
}
```

Archivo nuevo `frontend/src/services/connectionFlags.ts`: ver F2 (código completo).

---

## 5. Fases

### F0 — Flag backend triple + test registrado (sh y ps1)

**Objetivo (1 frase):** dar de alta `STACKY_CONNECTION_RESILIENCE_ENABLED` (bool, default ON) por la vía canónica triple, con test propio registrado en ambos runners.

**TESTS PRIMERO** — archivo nuevo `backend/tests/test_connection_resilience_flag.py`:

```python
"""Plan 192 F0 — flag STACKY_CONNECTION_RESILIENCE_ENABLED (registro triple).

G5: este archivo hace importlib.reload(config) y contamina tests flag-off de la
misma sesión pytest. Correr SIEMPRE por archivo (como todo el arnés).
"""
import importlib

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

KEY = "STACKY_CONNECTION_RESILIENCE_ENABLED"


def test_flag_registrada_bool_default_on():
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    assert KEY in _CATEGORY_KEYS["interfaz_ui"]


def test_config_default_efectivo_on(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is True
```

**Implementación (4 archivos, anclas exactas):**

1. `backend/services/harness_flags.py` — agregar al FINAL de la tupla `FLAG_REGISTRY` (inmediatamente antes de su `)` de cierre; si otra sesión agregó specs nuevas, agregar después de la última):

```python
    FlagSpec(
        key="STACKY_CONNECTION_RESILIENCE_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Resiliencia de conexion del dashboard",
        description=(
            "Plan 192 - Monitor pasivo de conexion dashboard-backend: banner global "
            "con reintento exponencial durante caidas y re-hidratacion automatica "
            "(refetch de lecturas) al recuperar. Solo observa; nunca reintenta mutaciones."
        ),
        group="global",
    ),
```

2. `backend/services/harness_flags.py` — en `_CATEGORY_KEYS` (dict en `:117`), agregar `"STACKY_CONNECTION_RESILIENCE_ENABLED",` a la tupla `"interfaz_ui"` (ancla por texto: la tupla que hoy contiene `"STACKY_UI_SHELL_V2_ENABLED"`, `:326-328`). NO crear categoría nueva. Nota de coexistencia: los planes 172/173/175/187 (no implementados) planean sumar keys a la MISMA tupla; si ya están, agregar la nuestra al final.

3. `backend/config.py` — inmediatamente DESPUÉS del bloque de asignación de `STACKY_UI_SHELL_V2_ENABLED` (buscar ese texto; hoy `:1308`), patrón EXACTO de `STACKY_COST_CENTER_ENABLED` (`config.py:543-545`):

```python
    # -- Plan 192 - Resiliencia de conexion dashboard-backend (UI) -------------
    # Monitor pasivo + banner global + re-hidratacion al recuperar. Default ON;
    # editable por UI (HarnessFlagsPanel). OFF => comportamiento actual intacto.
    STACKY_CONNECTION_RESILIENCE_ENABLED: bool = os.getenv(
        "STACKY_CONNECTION_RESILIENCE_ENABLED", "true"
    ).strip().lower() == "true"
```

4. `backend/tests/test_harness_flags.py` — agregar `"STACKY_CONNECTION_RESILIENCE_ENABLED",` al set `_CURATED_DEFAULTS_ON` (`:467`).

5. Registro del test en AMBOS runners: `backend/scripts/run_harness_tests.sh` — agregar `"tests/test_connection_resilience_flag.py"` a la lista `HARNESS_TEST_FILES` (`:20`); `backend/scripts/run_harness_tests.ps1` — agregar la misma ruta a `$HarnessTestFiles` (`:13`).

**PROHIBIDO** tocar `backend/harness_defaults.env` a mano (drift preexistente conocido; el default efectivo vive en `config.py` y la ausencia de la key en ese env ⇒ ON por el `os.getenv(..., "true")`).

**Criterio binario + comandos (PowerShell, desde `Stacky Agents/backend`, POR ARCHIVO):**

```
.venv\Scripts\python.exe -m pytest tests/test_connection_resilience_flag.py -q  # 3 passed
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q               # verde (54 passed en HEAD 2026-07-18; curado + categorizado)
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q        # criterio C2 abajo (NO exigir "verde" a secas)
```

**Nota C2 — gate honesto del meta-ratchet:** `tests/test_harness_ratchet_meta.py` está ROJO en HEAD por drift AJENO (verificado 2026-07-18 con `.venv`: `1 failed, 2 passed` — `test_ratchet_clasifica_todos_los_tests` lista tests de los planes 98/122/126/139 y otros nunca registrados). Criterio binario REAL de esta fase: (a) los 2 subtests que hoy pasan siguen pasando; (b) la lista de archivos sin clasificar que imprime el fallo preexistente queda IDÉNTICA a la de HEAD — en particular NO contiene `tests/test_connection_resilience_flag.py`. Correr el meta-test una vez ANTES de tocar nada y guardar esa lista como base de comparación. PROHIBIDO "sanear" el drift ajeno registrando tests de otros planes (scope creep). Si otra sesión ya lo saneó y en HEAD está verde, entonces sí exigir verde total.

**Flag:** `STACKY_CONNECTION_RESILIENCE_ENABLED` bool default ON.
**Runtimes:** N/A-por-diseño — flag de arnés backend leída por la UI; no toca ejecución de ningún runtime.
**Trabajo del operador:** ninguno.

---

### F1 — `connectionMonitor.ts`: máquina de estados pura (factory + singleton)

**Objetivo (1 frase):** implementar la máquina de estados de D3-D5-D8 como factory pura con deps inyectadas, más el singleton cableado a browser APIs, sin ninguna dependencia de `api/`.

**TESTS PRIMERO** — archivo nuevo `frontend/src/services/connectionMonitor.test.ts` (vitest, node env, deps fake con scheduler manual: `schedule` guarda `{fn, ms}` en un array y un helper `fire(i)` los ejecuta; `probe` devuelve promesas controladas por el test). Casos OBLIGATORIOS:

| # | Caso | Aserción |
|---|------|----------|
| t1 | enabled + solo `reportSuccess()` repetidos | status `healthy`; `deps.schedule` JAMÁS llamado; `deps.probe` JAMÁS llamado (K1) |
| t2 | `healthy` + 1 `reportFailure()` | status `suspect`; exactamente 1 probe disparado de inmediato |
| t3 | `suspect` + probe resuelve `true` | status `healthy`; `onRecovered` NO llamado |
| t4 | `suspect` + `reportSuccess()` antes de que el probe resuelva | status `healthy`; el resultado tardío del probe se IGNORA (gen stale, t18 lo cubre aparte) |
| t5 | `suspect` + probe resuelve `false` | status `down`; `attempt` pasa a 1 recién al disparar el siguiente probe; próximo probe programado a 1000 ms |
| t6 | `down` con probes que siempre fallan | delays programados exactamente 1000, 2000, 4000, 8000, 16000, 30000, 30000 (K3) |
| t7 | `down` + probe resuelve `true` | status `recovering`; `onRecovered` llamado EXACTAMENTE 1 vez; timer de `RECOVERY_LINGER_MS` programado; al dispararlo → `healthy`; `attempt` vuelve a 0 (K4/K5) |
| t8 | `down` + `reportSuccess()` pasivo | mismo camino que t7 (recovering + onRecovered 1 vez); probe pendiente cancelado (`deps.cancel` llamado) |
| t9 | `recovering` + `reportFailure()` | cancela el linger; status `suspect`; probe inmediato |
| t10 | `down` con `isHidden() === true` al programar/disparar | NO se llama `deps.probe`; al simular visibilitychange a visible → probe inmediato (K4) |
| t11 | `probeNow()` en `down` | cancela el timer pendiente; probe inmediato; `attempt` incrementa; si falla, reprograma con el delay del k actual (backoff NO se resetea) |
| t12 | sin `enable()` (o tras `disable()`) | `reportFailure()`/`reportSuccess()` NO transicionan ni programan timers; snapshot.enabled === false; `disable()` en `down` cancela todos los timers (K7) |
| t13 | dos `getSnapshot()` consecutivos sin cambios | MISMA referencia (`a === b`); tras una transición, referencia nueva |
| t14 | `setOnRecovered` | slot único: el segundo set reemplaza al primero; `setOnRecovered(null)` limpia; nunca se acumulan |
| t15 | `enable()` idempotente | dos `enable()` seguidos no duplican listeners ni timers; `disable()` + `enable()` funciona |
| t16 | `reportFailure()` con máquina disabled, luego `enable()` dentro de `STARTUP_SIGNAL_WINDOW_MS` | entra directo a `suspect` + probe inmediato (arranque en frío con backend caído, D8) |
| t17 | `enable()` sin señal previa de fallo reciente | status `healthy`; CERO probes (no hay request de arranque) |
| t18 | probe en vuelo resuelve DESPUÉS de una transición (gen distinto) | el resultado se ignora (sin transición doble, sin onRecovered duplicado) |
| t19 | `healthy` enabled + `reportSuccess()` (C3) | `getSnapshot()` devuelve la MISMA referencia (sin notify) PERO `getLastOkAt()` devuelve el `now()` nuevo (lectura viva, no la copia del snapshot) |
| t20 | [ADICIÓN D13] `healthy` + evento offline (disparar el cb capturado de `deps.onOffline`) | mismo camino que `reportFailure()`: `suspect` + 1 probe inmediato |
| t21 | [ADICIÓN D13] `down` con probe programado + evento online (cb de `deps.onOnline`) | `deps.cancel` llamado (timer viejo) + probe inmediato con `attempt++`; el mismo evento en `healthy` NO hace nada |

**Implementación** — `frontend/src/services/connectionMonitor.ts` (pseudocódigo completo; el implementador lo traduce literal):

```ts
export function _createConnectionMachine(deps: MachineDeps): ConnectionMachine {
  let status: ConnectionStatus = "healthy";
  let enabled = false;
  let probeUrl = "";
  let attempt = 0;
  let downSince: number | null = null;
  let lastOkAt: number | null = null;
  let lastFailureAt: number | null = null;   // interno, no va al snapshot
  let lastRecoveredAt: number | null = null;
  let gen = 0;                                // generación anti-stale (D3)
  let timerHandle: unknown = null;            // probe programado o linger
  let pendingWhileHidden = false;
  let onRecovered: (() => void) | null = null;
  let visibilityUnsub: (() => void) | null = null;
  let onlineUnsub: (() => void) | null = null;    // D13
  let offlineUnsub: (() => void) | null = null;   // D13
  const listeners = new Set<() => void>();
  let snapshot: ConnectionSnapshot = makeSnapshot();

  function makeSnapshot(): ConnectionSnapshot {
    return { status, attempt, downSince, lastOkAt, lastRecoveredAt, enabled };
  }
  function notify() { snapshot = makeSnapshot(); listeners.forEach((l) => l()); }
  function clearTimer() { if (timerHandle !== null) { deps.cancel(timerHandle); timerHandle = null; } }
  function transition(next: ConnectionStatus) { gen += 1; clearTimer(); status = next; notify(); }

  function delayForNextProbe(): number {
    // attempt = probes YA disparados en este ciclo down (k de D5)
    return Math.min(BACKOFF_BASE_MS * Math.pow(BACKOFF_FACTOR, attempt), BACKOFF_CAP_MS);
  }

  function fireProbe(countsAsAttempt: boolean) {
    if (deps.isHidden()) { pendingWhileHidden = true; return; }
    pendingWhileHidden = false;
    if (countsAsAttempt) { attempt += 1; notify(); }
    const myGen = gen;
    deps.probe(probeUrl, PROBE_TIMEOUT_MS).then(
      (ok) => { if (gen !== myGen) return; ok ? onProbeOk() : onProbeFail(); },
      () => { if (gen !== myGen) return; onProbeFail(); },
    );
  }

  function scheduleProbe(ms: number) {
    clearTimer();
    if (deps.isHidden()) { pendingWhileHidden = true; return; }
    timerHandle = deps.schedule(() => { timerHandle = null; fireProbe(true); }, ms);
  }

  function onProbeOk() {
    lastOkAt = deps.now();
    if (status === "suspect") { transition("healthy"); attempt = 0; notify(); return; }
    if (status === "down") { enterRecovering(); }
  }
  function onProbeFail() {
    lastFailureAt = deps.now();
    if (status === "suspect") { downSince = deps.now(); attempt = 0; transition("down"); scheduleProbe(delayForNextProbe()); return; }
    if (status === "down") { scheduleProbe(delayForNextProbe()); notify(); }
  }
  function enterRecovering() {
    lastRecoveredAt = deps.now();
    attempt = 0; downSince = null;
    transition("recovering");
    const fn = onRecovered; if (fn) fn();          // EXACTAMENTE 1 vez por ciclo (gen ya avanzó)
    timerHandle = deps.schedule(() => { timerHandle = null; transition("healthy"); }, RECOVERY_LINGER_MS);
  }

  function reportSuccess() {
    lastOkAt = deps.now();
    if (!enabled) return;                          // t12: inerte
    if (status === "suspect") { transition("healthy"); return; }
    if (status === "down") { enterRecovering(); return; }
    // healthy / recovering: sin transición; snapshot.lastOkAt se refresca en el próximo notify
  }
  function reportFailure() {
    lastFailureAt = deps.now();
    if (!enabled) return;                          // t12: inerte (solo registra lastFailureAt)
    if (status === "healthy") { transition("suspect"); fireProbe(false); return; }
    if (status === "recovering") { transition("suspect"); fireProbe(false); return; }
    // suspect / down: el probe en curso ya decide; no reprogramar acá
  }

  function enable(opts: { probeUrl: string }) {
    if (enabled) return;                           // t15 idempotente
    enabled = true; probeUrl = opts.probeUrl;
    visibilityUnsub = deps.onVisibilityChange(() => {
      if (!deps.isHidden() && pendingWhileHidden && (status === "down" || status === "suspect")) {
        fireProbe(status === "down");
      }
    });
    // [ADICIÓN ARQUITECTO] D13 — señal de red del navegador (t20/t21):
    offlineUnsub = deps.onOffline(() => { reportFailure(); });
    onlineUnsub = deps.onOnline(() => {
      if (status === "down" || status === "suspect") { clearTimer(); fireProbe(status === "down"); }
    });
    const failedRecently = lastFailureAt !== null
      && (lastOkAt === null || lastFailureAt > lastOkAt)
      && deps.now() - lastFailureAt <= STARTUP_SIGNAL_WINDOW_MS;
    if (failedRecently) { transition("suspect"); fireProbe(false); }   // t16
    else { notify(); }                                                  // t17: healthy, cero probes
  }
  function disable() {
    if (!enabled) return;
    enabled = false; gen += 1; clearTimer();
    if (visibilityUnsub) { visibilityUnsub(); visibilityUnsub = null; }
    if (onlineUnsub) { onlineUnsub(); onlineUnsub = null; }       // D13
    if (offlineUnsub) { offlineUnsub(); offlineUnsub = null; }    // D13
    status = "healthy"; attempt = 0; downSince = null; pendingWhileHidden = false;
    notify();
  }
  function probeNow() {
    if (!enabled || (status !== "down" && status !== "suspect")) return;
    clearTimer(); fireProbe(status === "down");     // t11
  }

  return {
    reportSuccess, reportFailure, enable, disable, probeNow,
    setOnRecovered: (fn) => { onRecovered = fn; },  // t14 slot único
    subscribe: (l) => { listeners.add(l); return () => listeners.delete(l); },
    getSnapshot: () => snapshot,                    // t13 referencia estable
    getLastOkAt: () => lastOkAt,                    // t19 lectura VIVA (C3); NO pasa por el snapshot
  };
}
```

Singleton (mismo archivo):

```ts
function realProbe(url: string, timeoutMs: number): Promise<boolean> {
  const ctrl = new AbortController();
  const t = window.setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(url, { signal: ctrl.signal, cache: "no-store" })
    .then((res) => res.ok)
    .finally(() => window.clearTimeout(t));
}

export const connectionMonitor: ConnectionMachine = _createConnectionMachine({
  now: () => Date.now(),
  schedule: (fn, ms) => window.setTimeout(fn, ms),
  cancel: (h) => window.clearTimeout(h as number),
  probe: realProbe,
  isHidden: () => typeof document !== "undefined" && document.hidden === true,
  onVisibilityChange: (cb) => {
    if (typeof document === "undefined") return () => {};
    document.addEventListener("visibilitychange", cb);
    return () => document.removeEventListener("visibilitychange", cb);
  },
  onOnline: (cb) => {                               // D13
    if (typeof window === "undefined") return () => {};
    window.addEventListener("online", cb);
    return () => window.removeEventListener("online", cb);
  },
  onOffline: (cb) => {                              // D13
    if (typeof window === "undefined") return () => {};
    window.addEventListener("offline", cb);
    return () => window.removeEventListener("offline", cb);
  },
});

export function reportConnectionSuccess(): void { connectionMonitor.reportSuccess(); }
export function reportConnectionFailure(): void { connectionMonitor.reportFailure(); }
export function connectionMonitorOwnsBackendSurface(): boolean {
  return connectionMonitor.getSnapshot().enabled;
}
```

**Criterio binario + comandos (Git Bash, desde `Stacky Agents/frontend`):**

```
npx vitest run src/services/connectionMonitor.test.ts    # t1..t21 verdes
npx tsc --noEmit                                          # verde
grep -c 'setInterval' src/services/connectionMonitor.ts   # 0
```

**Flag:** la máquina nace inerte (`enabled=false`); el gating real es F3.
**Runtimes:** N/A-por-diseño — módulo TS puro sin red propia salvo el probe (GET read-only), sin tocar ejecución de runtimes.
**Trabajo del operador:** ninguno.

---

### F2 — Interceptor en `client.ts` + `connectionFlags.ts`

**Objetivo (1 frase):** instrumentar los DOS caminos de red de `client.ts` con reportes O(1) al monitor (sin cambiar ninguna semántica) y crear el lector de flag fail-open.

**TESTS PRIMERO** —

Archivo nuevo `frontend/src/api/client.connection.test.ts` (vitest node; `vi.mock("../services/connectionMonitor")` para espiar los reportes; `vi.stubGlobal("fetch", ...)` para controlar respuestas). Casos:

| # | Caso | Aserción |
|---|------|----------|
| c1 | `api.get` con fetch → 200 JSON | `reportConnectionSuccess` 1 vez; devuelve el JSON (semántica intacta) |
| c2 | `api.get` con fetch que rechaza `TypeError` | `reportConnectionFailure` 1 vez; el MISMO error se relanza |
| c3 | `api.get` con rechazo `DOMException("...", "AbortError")` | NINGÚN reporte de fallo; el error se relanza (abort ≠ caída) |
| c4 | `api.get` con respuesta 503 | `reportConnectionFailure` 1 vez; `request()` lanza el mismo `Error("503 ...")` de hoy |
| c5 | `api.get` con respuesta 500 | `reportConnectionSuccess` 1 vez (backend vivo); `request()` lanza como hoy (K6: sin retry) |
| c6 | `api.post` (mutación) con fetch que rechaza | `reportConnectionFailure` 1 vez; el error se relanza; `fetch` llamado EXACTAMENTE 1 vez (cero reintentos, K6) |
| c7 | `rawPost` con 200 / con rechazo TypeError | success/failure reportados; `RawResponse` intacto |

Archivo nuevo `frontend/src/services/connectionFlags.test.ts` (`vi.mock("../api/endpoints")`): flag presente `value:false` → false; presente `value:true` → true; `list()` rechaza → true (fail-open) y usa cache `localStorage` si existe; promesa cacheada (2 llamadas ⇒ 1 sola request); `_resetForTests()` limpia. **C10:** vitest corre en node env SIN `localStorage`: para los casos de cache, stubear con `vi.stubGlobal("localStorage", fake)` (fake con `getItem`/`setItem`/`removeItem` sobre un `Map`); agregar además un caso SIN stub (localStorage inexistente ⇒ el try/catch del código cae al default `true` sin lanzar).

**Implementación:**

1. `frontend/src/api/client.ts` — import nuevo en la cabecera:

```ts
import {
  GATEWAY_DOWN_STATUSES,
  reportConnectionSuccess,
  reportConnectionFailure,
} from "../services/connectionMonitor";

// C8: GATEWAY_DOWN_STATUSES se IMPORTA del monitor (fuente única; prohibido duplicar el Set acá).
function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}
function reportOutcome(res: Response): void {
  if (GATEWAY_DOWN_STATUSES.has(res.status)) reportConnectionFailure();
  else reportConnectionSuccess();
}
```

2. `request<T>()` (`client.ts:67-81`) — diff exacto (solo se envuelve el fetch; el throw en `!ok` NO cambia):

```ts
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...(init.headers ?? {}),
      },
    });
  } catch (e) {
    if (!isAbortError(e)) reportConnectionFailure();
    throw e;                       // semántica intacta: el caller ve el mismo error
  }
  reportOutcome(res);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}
```

3. `rawPost<T>()` (`client.ts:28-63`) — mismo patrón: `try/catch` alrededor del `await fetch(...)` con `isAbortError` + `reportConnectionFailure` + rethrow; tras obtener `res`, llamar `reportOutcome(res)` antes del parseo. El resto del cuerpo NO cambia.

4. Archivo nuevo `frontend/src/services/connectionFlags.ts` (patrón 187 F0 autocontenido, D9):

```ts
import { HarnessFlags } from "../api/endpoints";

const KEY = "STACKY_CONNECTION_RESILIENCE_ENABLED";
const CACHE_KEY = "stacky.connectionResilience.last";
let _promise: Promise<boolean> | null = null;

/** Lectura síncrona anti-flash. Fail-open: sin cache => true (D9). */
export function readCachedConnectionFlag(): boolean {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw === "false") return false;
    if (raw === "true") return true;
  } catch { /* localStorage inaccesible: seguir al default */ }
  return true;
}

export function isConnectionResilienceEnabled(): Promise<boolean> {
  if (_promise) return _promise;
  _promise = HarnessFlags.list()
    .then((res) => {
      const flag = res.flags.find((f) => f.key === KEY);
      const value = flag ? flag.value === true : true;
      try { localStorage.setItem(CACHE_KEY, String(value)); } catch { /* ignorar */ }
      return value;
    })
    .catch(() => readCachedConnectionFlag()); // fail-open: backend caido => la feature debe vivir
  return _promise;
}

export function _resetForTests(): void { _promise = null; }
```

**Criterio binario + comandos:**

```
npx vitest run src/api/client.connection.test.ts     # c1..c7 verdes
npx vitest run src/services/connectionFlags.test.ts  # verde
npx tsc --noEmit                                      # verde
```

**Flag:** el interceptor reporta SIEMPRE (O(1), inofensivo con máquina inerte); el gating de comportamiento visible es F3 (OFF ⇒ máquina nunca habilitada ⇒ reportes no-op).
**Runtimes:** N/A-por-diseño — cambia solo el envoltorio de fetch del frontend; cero cambios de backend.
**Trabajo del operador:** ninguno.

---

### F3 — `ConnectionBanner.tsx` + lógica pura + montaje en `App.tsx`

**Objetivo (1 frase):** banner global accesible (down/recovering), con contador de intentos y "Reintentar ahora", montado una sola vez sobre ambas ramas del shell, gateado por la flag.

**TESTS PRIMERO** — archivo nuevo `frontend/src/services/connectionBanner.logic.test.ts`:

- `computeBannerView({status:"healthy", ...})` → `{visible:false}`.
- `computeBannerView({status:"suspect", ...})` → `{visible:false}` (anti falso-positivo: sin banner en suspect).
- `computeBannerView({status:"down", attempt:0, ...})` → visible, kind "down", message EXACTO `"Sin conexión con el backend — reintentando…"`, attemptText `null`, showRetry `true`.
- `computeBannerView({status:"down", attempt:3, ...})` → attemptText EXACTO `"(intento 3)"`.
- `computeBannerView({status:"recovering", ...})` → visible, kind "recovering", message EXACTO `"Backend de vuelta — actualizando…"`, attemptText `null`, showRetry `false`.
- `computeBannerView({enabled:false, status:"down", ...})` → `{visible:false}` (defensa en profundidad).
- `freshnessLabel(null, ahora)` → `"Sin respuesta del backend aún"`; `freshnessLabel(ahora-7000, ahora)` → `"Última respuesta del backend hace 7s"`; redondeo a segundos enteros con `Math.round`.

**Implementación:**

1. `frontend/src/services/connectionBanner.logic.ts` — funciones puras del contrato §4 (strings exactos de arriba; sin imports de React).

2. Archivo nuevo `frontend/src/components/ConnectionBanner.tsx` (cáscara fina):

```tsx
import { useEffect, useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "./ui";
import { apiBase } from "../api/client";
import { connectionMonitor } from "../services/connectionMonitor";
import { makeRecoveryHandler } from "../services/connectionRecovery";
import { isConnectionResilienceEnabled, readCachedConnectionFlag } from "../services/connectionFlags";
import { computeBannerView } from "../services/connectionBanner.logic";
import styles from "./ConnectionBanner.module.css";

export default function ConnectionBanner() {
  const queryClient = useQueryClient();
  const [flagOn, setFlagOn] = useState<boolean>(() => readCachedConnectionFlag());

  useEffect(() => {
    let alive = true;
    isConnectionResilienceEnabled().then((v) => { if (alive) setFlagOn(v); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!flagOn) return;
    connectionMonitor.setOnRecovered(makeRecoveryHandler(queryClient));
    connectionMonitor.enable({ probeUrl: `${apiBase}/api/diag/health` });
    return () => {
      connectionMonitor.disable();
      connectionMonitor.setOnRecovered(null);
    };
  }, [flagOn, queryClient]);

  const snapshot = useSyncExternalStore(connectionMonitor.subscribe, connectionMonitor.getSnapshot);
  const view = computeBannerView(snapshot);
  if (!flagOn) return null;

  return (
    <>
      {/* C12: live region PERSISTENTE (announcer). Cambia su TEXTO, nunca se monta y
          desmonta con el banner: una region insertada ya con contenido puede no anunciarse. */}
      <span role="status" aria-live="polite" className={styles.srOnly}>
        {view.visible ? view.message : ""}
      </span>
      {view.visible ? (
        <div className={view.kind === "recovering" ? `${styles.banner} ${styles.recovering}` : `${styles.banner} ${styles.down}`}>
          <span aria-hidden="true" className={styles.msg}>{view.message}</span>
          {view.attemptText ? (
            <span aria-hidden="true" className={styles.attempt}>{view.attemptText}</span>
          ) : null}
          {view.showRetry ? (
            <Button onClick={() => connectionMonitor.probeNow()}>Reintentar ahora</Button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
```

Notas duras para el implementador: los hooks van SIEMPRE antes del early-return (orden de hooks estable). `Button` viene del barrel (`components/ui/index.ts:7`); usar props existentes de `ButtonProps` (verificar variantes en `components/ui/Button.tsx`; si no hay certeza, solo `onClick` + children). PROHIBIDO `<button>` crudo y `style={{}}`. El StrictMode double-mount está cubierto por t15/t14 (enable/disable + slot único).

3. Archivo nuevo `frontend/src/components/ConnectionBanner.module.css` — clases `.banner`, `.down`, `.recovering`, `.msg`, `.attempt`, `.srOnly`. `.srOnly` (announcer C12, SIN colores): `position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); white-space:nowrap;`. Colores y fondos EXCLUSIVAMENTE con tokens `var(--...)` existentes: leer `HealthBanner.module.css` y `Toast.module.css` y reusar los MISMOS tokens que esos archivos usan para error/éxito (no inventar nombres de token; no hex). Layout: banda horizontal full-width, padding compacto, `display:flex; align-items:center; gap`.

4. `frontend/src/App.tsx` — montaje ÚNICO: insertar `<ConnectionBanner />` en la línea inmediatamente ANTERIOR a `<HealthBanner />` (`App.tsx:260`), que ya está FUERA del ternario `shellV2Enabled` (`:262`) ⇒ cubre ambas ramas del shell con un solo mount. Import correspondiente junto a los demás imports de componentes.

**Criterio binario + comandos:**

```
npx vitest run src/services/connectionBanner.logic.test.ts   # verde
npx tsc --noEmit                                              # verde
grep -c 'style={{' src/components/ConnectionBanner.tsx        # 0
grep -c '<button' src/components/ConnectionBanner.tsx         # 0
grep -c 'role="status"' src/components/ConnectionBanner.tsx   # 1
grep -c 'aria-live="polite"' src/components/ConnectionBanner.tsx  # 1
grep -c 'aria-hidden' src/components/ConnectionBanner.tsx     # 2 (mensaje visual + contador; el anuncio sale de la live region persistente, C12)
grep -cE '#[0-9a-fA-F]{3,6}' src/components/ConnectionBanner.module.css  # 0
grep -c 'ConnectionBanner' src/App.tsx                        # 2 (import + JSX)
```

**Flag:** OFF ⇒ `flagOn=false` desde el primer resolve (y cache en mounts posteriores) ⇒ `enable()` jamás corre, render null.
**Runtimes:** N/A-por-diseño — componente de UI puro; el probe es un GET read-only al health existente.
**Trabajo del operador:** ninguno.

---

### F4 — Re-hidratación al recuperar (invalidación global única)

**Objetivo (1 frase):** cablear `onRecovered` → `queryClient.invalidateQueries()` global (una sola vez por ciclo) y probarlo con el core de react-query sin DOM.

**TESTS PRIMERO** — archivo nuevo `frontend/src/services/connectionRecovery.integration.test.ts` (precedentes: `utils/__tests__/agentCompletionRecovery.integration.test.ts` y la regla del 156 `:666` "core de react-query sin DOM"):

```ts
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { makeRecoveryHandler } from "./connectionRecovery";

describe("makeRecoveryHandler", () => {
  it("re-fetchea las queries ACTIVAS y marca stale las inactivas con UNA invalidacion", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
    let activeCalls = 0;
    let inactiveCalls = 0;
    const observer = new QueryObserver(qc, {
      queryKey: ["activa"],
      queryFn: () => { activeCalls += 1; return Promise.resolve(activeCalls); },
    });
    const unsub = observer.subscribe(() => {});
    await vi.waitFor(() => expect(activeCalls).toBe(1));
    await qc.prefetchQuery({
      queryKey: ["inactiva"],
      queryFn: () => { inactiveCalls += 1; return Promise.resolve(inactiveCalls); },
    });
    expect(inactiveCalls).toBe(1);

    makeRecoveryHandler(qc)();   // el momento magico

    await vi.waitFor(() => expect(activeCalls).toBe(2));          // activa: re-fetch
    expect(inactiveCalls).toBe(1);                                 // inactiva: NO re-fetch (thundering herd acotado)
    expect(qc.getQueryState(["inactiva"])?.isInvalidated).toBe(true); // pero queda stale para su proximo mount
    unsub();
    qc.clear();
  });
});
```

**Implementación:** archivo nuevo `frontend/src/services/connectionRecovery.ts` con el contrato exacto de §4 (3 líneas). El cableado en el componente ya quedó hecho en F3 (`setOnRecovered(makeRecoveryHandler(queryClient))`); esta fase lo valida. La garantía "exactamente 1 vez por ciclo down→recovered" es de la máquina (F1 t7/t18).

**Criterio binario + comandos:**

```
npx vitest run src/services/connectionRecovery.integration.test.ts  # verde
grep -c 'invalidateQueries' src/services/connectionRecovery.ts       # 1
```

**Flag:** hereda el gating de F3 (sin enable no hay onRecovered).
**Runtimes:** N/A-por-diseño — invalidación de cache de lecturas del frontend; cero requests de mutación.
**Trabajo del operador:** ninguno.

---

### F5 — Coexistencia: `HealthBanner` cede la superficie "backend caído"

**Objetivo (1 frase):** evitar el doble banner haciendo que el branch `catch` de `HealthBanner` no pinte su aviso de backend cuando el monitor está habilitado, sin tocar ningún otro check.

**Implementación** — `frontend/src/components/HealthBanner.tsx`, diff mínimo:

1. Import nuevo: `import { connectionMonitorOwnsBackendSurface } from "../services/connectionMonitor";`
2. Reemplazar el cuerpo del `catch` (`HealthBanner.tsx:80-88`) por:

```ts
      } catch {
        if (!cancelled) {
          if (connectionMonitorOwnsBackendSurface()) {
            // Plan 192 F5: con el monitor de conexion activo, ConnectionBanner es
            // el dueño del aviso "backend caido"; HealthBanner no lo duplica.
            setWorst((prev) => (prev && prev.id === "backend" ? null : prev));
          } else {
            setWorst({
              id: "backend",
              label: "Backend",
              status: "error",
              message: "El backend no responde — revisá que esté corriendo.",
            });
          }
        }
      }
```

Reglas: NO tocar el `POLL_MS`, ni el dismiss, ni ningún otro check (tracker/database/watchers siguen siendo de `HealthBanner`). Con la flag OFF el monitor nunca se habilita ⇒ `connectionMonitorOwnsBackendSurface()` es `false` ⇒ comportamiento EXACTAMENTE igual a hoy. Bonus implícito: con la flag ON, el problema del dismiss de 30 min suprimiento la alerta de caída desaparece para la superficie de conexión (el ConnectionBanner no tiene dismiss).

**Tests:** la función `connectionMonitorOwnsBackendSurface` queda cubierta en F1 (false por default, true tras `enable()`, false tras `disable()` — está implícita en t12/t15; agregar una aserción explícita en t12 si no quedó). El diff del componente se verifica con `tsc --noEmit` + gate grep.

**Criterio binario + comandos:**

```
npx tsc --noEmit                                                     # verde
grep -c 'connectionMonitorOwnsBackendSurface' src/components/HealthBanner.tsx  # 2 (import + uso)
```

**Flag:** OFF ⇒ rama nueva inerte (comportamiento actual intacto).
**Runtimes:** N/A-por-diseño — cambio de render condicional en un componente existente.
**Trabajo del operador:** ninguno.

---

### F6 — Punto de frescura en TopBar (opcional acotado, mismo flag)

**Objetivo (1 frase):** un punto de estado decorativo en la TopBar con `title` "Última respuesta del backend hace Xs", sin timers en estado sano.

**TESTS PRIMERO:** los casos de `freshnessLabel` ya están en F3 (connectionBanner.logic.test.ts). No hay lógica nueva.

**Implementación:**

1. Archivo nuevo `frontend/src/components/ConnectionFreshnessDot.tsx`:

```tsx
import { useEffect, useState, useSyncExternalStore } from "react";
import { connectionMonitor } from "../services/connectionMonitor";
import { isConnectionResilienceEnabled, readCachedConnectionFlag } from "../services/connectionFlags";
import { freshnessLabel } from "../services/connectionBanner.logic";
import styles from "./ConnectionFreshnessDot.module.css";

export default function ConnectionFreshnessDot() {
  const [flagOn, setFlagOn] = useState<boolean>(() => readCachedConnectionFlag());
  const [, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    isConnectionResilienceEnabled().then((v) => { if (alive) setFlagOn(v); });
    return () => { alive = false; };
  }, []);
  const snapshot = useSyncExternalStore(connectionMonitor.subscribe, connectionMonitor.getSnapshot);
  if (!flagOn || !snapshot.enabled) return null;
  const cls =
    snapshot.status === "healthy" ? styles.ok :
    snapshot.status === "recovering" ? styles.warn : styles.bad;
  return (
    <span
      className={`${styles.dot} ${cls}`}
      title={freshnessLabel(connectionMonitor.getLastOkAt(), Date.now())}
      aria-hidden="true"
      onMouseEnter={() => setTick((t) => t + 1)}
    />
  );
}
```

Decisión codificada: el `title` se recalcula en cada render; entre renders puede quedar viejo, y el `onMouseEnter` fuerza un re-render al pasar el mouse (evento del usuario, cero timers — K1 se mantiene). **C3 (obligatorio):** el `title` usa `connectionMonitor.getLastOkAt()` (lectura VIVA) y NO `snapshot.lastOkAt`: el snapshot solo se regenera al transicionar (t13), así que en `healthy` sostenido quedaría congelado y el dot mentiría ("hace 3600s" con backend sano). `aria-hidden="true"`: el punto es decorativo; la superficie accesible es el banner (D12).

2. Archivo nuevo `frontend/src/components/ConnectionFreshnessDot.module.css` — `.dot` (8px, `border-radius:50%`, `display:inline-block`), `.ok`/`.warn`/`.bad` con tokens `var(--...)` existentes de `theme.css` (mismos tokens semánticos de éxito/alerta/error que ya usan `HealthBanner.module.css`/`Toast.module.css`; cero hex).

3. `frontend/src/components/TopBar.tsx` — import del componente y montarlo como PRIMER hijo del contenedor `<div className={styles.actions}>` (`TopBar.tsx:202`).

**Criterio binario + comandos:**

```
npx tsc --noEmit                                                         # verde
grep -c 'style={{' src/components/ConnectionFreshnessDot.tsx             # 0
grep -cE '#[0-9a-fA-F]{3,6}' src/components/ConnectionFreshnessDot.module.css  # 0
grep -c 'ConnectionFreshnessDot' src/components/TopBar.tsx               # 2 (import + JSX)
```

**Flag:** mismo gating que F3 (OFF o monitor no habilitado ⇒ null).
**Runtimes:** N/A-por-diseño — indicador visual read-only.
**Trabajo del operador:** ninguno.

---

### F7 — DoD global + smoke manual documentado

**Objetivo (1 frase):** correr TODO el gate por archivo y validar el ciclo completo contra un backend real matándolo y reviviéndolo.

**Smoke manual (documentar el resultado en el commit/PR; sin RTL/jsdom este es el gate de UI real):**

1. Levantar el deploy (o `npm run dev` + backend): dashboard abierto en una página con datos (p.ej. board de tickets).
2. Matar el proceso Flask. Esperado: banner "Sin conexión con el backend — reintentando… (intento N)" en ≤ ~7 s (primera request fallida o poll de HealthBanner + probe de confirmación), contador subiendo con cadencia 1, 2, 4, 8... s. UN solo banner (no el de HealthBanner). NOTA dev: bajo `npm run dev` el proxy de Vite puede responder 500 en vez de rechazar (R7) — la validación de ENTRADA a down hacerla en deploy real; "Reintentar ahora"/recovery funcionan en ambos.
3. Revivir el Flask. Esperado: en ≤ backoff vigente (máx 30 s; o instantáneo con "Reintentar ahora") el banner pasa a "Backend de vuelta — actualizando…" ~4 s y la página se re-hidrata SOLA (datos frescos, sin F5).
4. Con la pestaña oculta durante la caída: sin requests de probe (verificar en la pestaña Network); al volver a la pestaña, probe inmediato.
5. Apagar la flag desde la UI (Settings → HarnessFlagsPanel → "Resiliencia de conexión del dashboard") + reload: comportamiento actual (HealthBanner vuelve a ser el único aviso).
6. (D13) Con la flag ON y backend vivo: DevTools → Network → "Offline": el banner aparece tras el probe fallido (sin esperar tráfico pasivo); volver a "No throttling": recuperación inmediata al evento `online` (sin esperar el backoff vigente).

**Criterio binario:** la lista COMPLETA de comandos del §9 verde + los 5 pasos del smoke documentados con resultado.
**Runtimes:** N/A-por-diseño — validación de UI/red local.
**Trabajo del operador:** ninguno (el smoke lo hace el implementador).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación (codificada en el plan) |
|---|--------|-------------------------------------|
| R1 | Falso positivo por UNA request fallida suelta | Estado `suspect` SIN banner + probe de confirmación inmediato; solo `down` (probe fallido) pinta banner (D3). Umbral efectivo: 2 fallos consecutivos (1 pasivo + 1 probe). `AbortError` excluido (D2) |
| R2 | Thundering herd al recuperar | UNA `invalidateQueries()` global; react-query v5 re-fetchea SOLO queries activas (default `refetchType:'active'`); inactivas quedan stale para su próximo mount (D6, test F4) |
| R3 | Mutaciones en vuelo durante la caída | Fallan y se reportan EXACTAMENTE como hoy (`request()` relanza el mismo error, test c6); el monitor solo observa; PROHIBIDO retry de POST/PUT/DELETE (§2.1) |
| R4 | Backend lento ≠ caído / backend COLGADO no detectado (C11) | La detección pasiva NO usa timeouts sobre requests de negocio (solo rechazos y 502/503/504); el timeout de 5 s aplica SOLO al probe (D4). **Punto ciego declarado (C11):** `request()` no tiene timeout (`client.ts:67-81`) ⇒ un backend colgado (proceso vivo que no responde) no genera señal pasiva hasta el timeout del propio navegador (minutos). Se acepta: el modo de fallo real del Flask local (deploy/`START.bat`) es proceso muerto ⇒ rechazo inmediato del fetch; agregar timeouts a las requests de negocio cambiaría la semántica de TODOS los callers (fuera de scope §7) |
| R5 | StrictMode double-mount (`main.tsx:18`) | Singleton a nivel módulo + `enable()/disable()` idempotentes + `setOnRecovered` slot único (D8, tests t14/t15) |
| R6 | Pestaña oculta quemando requests | Probe pausado con `document.hidden`; reanuda con `visibilitychange` (D4, test t10) |
| R7 | Dev bajo Vite: proxy (`vite.config.ts:13-15` → `http://localhost:5050`) puede responder 500 con Flask caído (no rechaza) | 500 excluido A PROPÓSITO de la señal pasiva (un 500 real del backend no debe encender el banner). Limitación SOLO en `npm run dev`; en deploy real Flask sirve la SPA y su caída rechaza el fetch. El probe valida `res.ok`, así que recovery y "Reintentar ahora" funcionan también en dev (D2/D4) |
| R8 | Doble banner (HealthBanner + ConnectionBanner) | F5: HealthBanner cede la superficie "backend" cuando el monitor está habilitado; resto de sus checks intactos (D10) |
| R9 | Ciclo de imports client ↔ monitor | El monitor NO importa nada de `api/`; `probeUrl` llega por `enable()` desde el host (D7) |
| R10 | Flag ilegible con backend caído al arrancar | Fail-open a ON + cache `localStorage` anti-flash (D9); fallos previos al `enable()` se recuperan con la ventana de arranque (D8, t16) |
| R11 | Sesión paralela MUY activa (robó números 2 veces hoy; toca archivos compartidos) | Antes de implementar: re-listar `docs/` (si 192 está tomado, renumerar al primer libre y actualizar título + este registro); commits SIEMPRE con pathspec explícito de los archivos propios; releer `git status` en frío |
| R12 | Resultado stale de un probe en vuelo tras cambiar de estado | Contador de generación `gen`; callbacks con gen viejo se ignoran (D3, t18) |
| R13 | Probe recibe 500 del health en `suspect` con backend VIVO (bug puntual del endpoint) ⇒ `down` falso | Mitigado por diseño: cualquier éxito pasivo saca de `down` (D3) — la próxima request exitosa (p.ej. el poll de HealthBanner ≤30 s) transiciona a `recovering`. Además `health()` responde SIEMPRE 200 aunque haya warnings (`diag.py:397-412`; `healthy:false` viaja en el body), así que el 500 requiere una excepción no capturada, improbable con sus try/except defensivos |

---

## 7. Fuera de scope (explícito)

- **Service Worker / offline real / cola offline.** Nada de cachear mutaciones ni reintentarlas después.
- **Retry automático de mutaciones.** Prohibido por §2.1; queda como está hoy para siempre dentro de este plan.
- **WebSocket / SSE para presencia del backend.** El 156 ya lo recortó para el summary (`156:660`); acá tampoco.
- **Migrar o eliminar el poller de `HealthBanner`** (`POLL_MS 30s`): es trabajo del latido único (plan 156). Este plan solo hace que CEDA la superficie de backend caído (F5).
- **Instrumentar los caminos fuera del choke-point** (inventario COMPLETO en D1 — C4: 7 `fetch` en `endpoints.ts`, 6 call-sites más en `App.tsx`/`preferences.ts`/`useTicketSync.ts`/`AssignmentRecommendationPanel.tsx`/`HarnessFlagsPanel.tsx`/`flagHealth.ts`, y el `EventSource` de `useExecutionStream.ts:135`): el choke-point cubre el tráfico dominante; el probe confirma el resto.
- **`ConnectionHealthStrip` (devops)** e **`IntegrationHealthBanner`** (plan 148): otros dominios, solo homónimos; no se tocan.
- **Tocar `vite.config.ts`** (hacer que el proxy emita 502 en dev): fuera de scope; R7 documenta la limitación.
- **Tocar `Toast.tsx`**: el banner es persistente; Toast es efímero por diseño.
- **Indicadores por página / spinners nuevos**: la re-hidratación usa los estados de loading que cada página ya tiene.
- **Tests de render (`render()`/RTL)**: imposibles en este repo (§2.9).

---

## 8. Glosario

- **Señal pasiva:** resultado (éxito/fallo de conexión) de una request que la app YA hacía por sus propias razones; el monitor la observa gratis en el choke-point.
- **Choke-point:** punto único del código por donde pasa el tráfico a instrumentar (`client.ts request()` + `rawPost()`).
- **Probe:** GET read-only a `/api/diag/health` disparado SOLO en `suspect`/`down` para confirmar caída o detectar recuperación.
- **Suspect:** estado intermedio sin banner tras el primer fallo; evita falsos positivos con un probe de confirmación.
- **Backoff exponencial:** espera creciente entre probes (1, 2, 4, ... cap 30 s) para no martillar un backend caído.
- **Linger:** los 4 s en que el banner muestra "Backend de vuelta — actualizando…" antes de ocultarse (`RECOVERY_LINGER_MS`).
- **Fail-open:** ante la imposibilidad de leer la flag, la feature queda ON (su escenario principal ES el backend caído).
- **Invalidación global:** `queryClient.invalidateQueries()` sin filtro; marca todo stale y re-fetchea solo lo activo.
- **Observador activo:** query de react-query con un componente montado mirándola; es lo único que re-fetchea al invalidar.
- **Gen (generación):** contador que invalida callbacks de probes viejos tras una transición de estado.
- **Announcer persistente:** live region `role="status"` sr-only SIEMPRE montada mientras la flag está ON, cuyo TEXTO cambia; evita el caso "región insertada ya con contenido no se anuncia" (D12/C12).
- **Señal de red del navegador:** eventos `window online`/`offline` (D13): `offline` cuenta como fallo pasivo; `online` dispara probe inmediato en `suspect`/`down`. Solo eventos — `navigator.onLine` como estado NO se consulta.

---

## 9. Orden de implementación y DoD

**Orden estricto:** F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7. (F5 y F6 requieren F3; F4 valida el cableado hecho en F3.)

**DoD — todos los comandos, en orden, todos verdes:**

Backend (PowerShell, desde `Stacky Agents/backend`, POR ARCHIVO — G5):

```
.venv\Scripts\python.exe -m pytest tests/test_connection_resilience_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

(El tercero con el criterio C2 de F0: rojo preexistente AJENO permitido, lista de no-clasificados idéntica a HEAD y sin el archivo nuevo. C1: `.venv` = py3.13.5 canónico; `venv/` = py3.11.9 WIP ajeno, NO usarlo.)

Frontend (Git Bash, desde `Stacky Agents/frontend`, POR ARCHIVO):

```
npx vitest run src/services/connectionMonitor.test.ts
npx vitest run src/api/client.connection.test.ts
npx vitest run src/services/connectionFlags.test.ts
npx vitest run src/services/connectionBanner.logic.test.ts
npx vitest run src/services/connectionRecovery.integration.test.ts
npx tsc --noEmit
```

Gates grep (Git Bash, desde `Stacky Agents/frontend`; valores esperados al lado):

```
grep -c 'setInterval' src/services/connectionMonitor.ts                          # 0
grep -c 'style={{' src/components/ConnectionBanner.tsx                           # 0
grep -c 'style={{' src/components/ConnectionFreshnessDot.tsx                     # 0
grep -c '<button' src/components/ConnectionBanner.tsx                            # 0
grep -c 'role="status"' src/components/ConnectionBanner.tsx                      # 1
grep -c 'aria-live="polite"' src/components/ConnectionBanner.tsx                 # 1
grep -cE '#[0-9a-fA-F]{3,6}' src/components/ConnectionBanner.module.css         # 0
grep -cE '#[0-9a-fA-F]{3,6}' src/components/ConnectionFreshnessDot.module.css   # 0
grep -c 'invalidateQueries' src/services/connectionRecovery.ts                   # 1
grep -c 'connectionMonitorOwnsBackendSurface' src/components/HealthBanner.tsx    # 2
grep -c 'ConnectionBanner' src/App.tsx                                           # 2
grep -c 'ConnectionFreshnessDot' src/components/TopBar.tsx                       # 2
```

Más el smoke manual de F7 (5 pasos) documentado.

---

## 10. Advertencias para el implementador (leer antes de tocar nada)

1. **Sesión paralela activa HOY** en el mismo repo/rama: re-listar `Stacky Agents/docs/` antes de empezar (si el 192 fue tomado, renumerar); `git status` en frío; commitear SIEMPRE con pathspec explícito (`git commit -- <paths propios>`); NUNCA amend/reset/rebase/checkout.
2. **G5:** `tests/test_harness_flags.py` (y el test nuevo de F0) hacen `importlib.reload(config)` y contaminan la sesión pytest — TODOS los pytest de este plan van POR ARCHIVO, con `.venv\Scripts\python.exe` desde `backend` (C1: `.venv`, no `venv/`).
3. **NO importar código de los planes 185/187** (no implementados): `connectionFlags.ts` duplica el patrón de forma autocontenida (D9).
4. **NO tocar `backend/harness_defaults.env` a mano** (drift preexistente conocido; el default efectivo vive en `config.py`).
5. **NO imitar los `.test.tsx` legacy** que importan `@testing-library/react` (no corre en este repo): imitar `services/briefDraft.test.ts` / `components/integrationHealth.logic.ts` / `utils/__tests__/agentCompletionRecovery.integration.test.ts`.
6. Los mensajes del banner son STRINGS EXACTOS (F3, con tilde y puntos suspensivos como están escritos); los tests los fijan.
7. Si `vitest` pide config para resolver TS, correr igualmente por archivo; NO agregar dependencias nuevas a `package.json` (este plan no suma ninguna).
8. La numeración de líneas citada (`App.tsx:260`, `client.ts:67` y todas las demás anclas archivo:línea de este doc) es del 2026-07-18; si la sesión paralela movió líneas, anclar por TEXTO (los símbolos citados) antes de editar.
9. **Venv canónico (C1):** el backend se corre con `.venv\Scripts\python.exe` (Python 3.13.5, verificado 2026-07-18). El directorio `venv/` (Python 3.11.9) es un WIP ajeno untracked de otra sesión: NO usarlo ni tocarlo. Si `.venv` no existiera en tu checkout, verificar con `--version` cuál intérprete tiene las deps del backend antes de correr nada.
10. **Gates grep vs comentarios (C9 — gotcha recurrido 6× en el repo):** los gates del §9 cuentan tokens EN EL FUENTE. PROHIBIDO escribir comentarios/JSDoc que contengan los tokens gateados (`setInterval`, `invalidateQueries`, `<button`, `style={{`, `aria-hidden`, `connectionMonitorOwnsBackendSurface`, `ConnectionBanner`, `ConnectionFreshnessDot`) en los archivos gateados fuera de los usos exactos esperados. Si una explicación necesita nombrar el token, parafrasear ("timer encadenado", "la invalidación global", "el botón del barrel").
