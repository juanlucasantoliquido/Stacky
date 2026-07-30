**Estado:** MEJORADO v2 (2026-07-30) · **Autor:** pipeline proponer-plan-stacky · **Crítica:** skill `criticar-y-mejorar-plan` (juez adversarial, subagente con contexto limpio) · **Fuente:** auditoría 2026-07-29 (fd4e45d3)

# Plan 273 — El deep link aterriza y el error se entiende: los 7 bloqueantes de producción

## 0. Versión v1 → v2 · Veredicto y changelog

**Veredicto sobre el v1: RECHAZADO** — **5 BLOQUEANTES, 8 IMPORTANTES, 7 MENORES** (20 hallazgos). El v1 tiene una calidad de anclaje excepcional: se verificaron ~40 anclas contra el código real y coincidieron casi todas, incluidos conteos finos como `PAIRS`=24 con el texto literal del `it`, `.toBe(53)`, `.toBe(69)`, baseline `App.module.css`=4 con exactamente esos 4 hex, B-06=24/13 con los 13 nombres 1:1, el lag de ratchet 719/655/64 con holgura CERO, y la aritmética WCAG (6.47 / 3.76 / 4.88 recalculados de forma independiente). **Los cinco bloqueantes no son de anclaje.** Cuatro son de **alcance dimensionado por el tamaño del defecto en vez de por el tamaño de la superficie que lo muestra**, y uno es autoinfligido: el diff que F3 dicta rompe el gate que F3 crea. Este v2 los cierra.

La crítica se hizo en dos pasadas independientes (el juez en subagente con contexto limpio + verificación directa del invocador) y **todo número de esta tabla fue medido corriendo el comando, no leído del plan**.

| # | Sev | Hallazgo | Dónde se corrige en v2 |
|---|---|---|---|
| **C1** | **BLOQ** | **C3 era insatisfacible.** F4 cableaba `userFacingMessage()` **solo** en `PageErrorBoundary.tsx`, que es un boundary de errores de **render** (`getDerivedStateFromError`/`componentDidCatch`, verificado `PageErrorBoundary.tsx:26-30`): los rechazos de `api.*` **nunca llegan ahí**. Los errores de API los pinta cada componente con el modismo de la casa `err instanceof Error ? err.message : String(err)` — **42 ocurrencias en 26 archivos**, p. ej. `CompareWizard.tsx:94-99` → banner en `:108`. ⇒ tras F4+F5 el smoke 5 seguiría mostrando `403 FORBIDDEN: {"ok":false,"error":"feature_disabled",...,"detail":{"flag":"STACKY_DB_COMPARE_ENABLED"}}`: las **cuatro** cosas que el smoke prohíbe. Peor: F5 **reubica** el nombre de la flag de `error` a `detail.flag` **dentro del mismo string crudo**, así que sin migrar consumidores la exposición de `STACKY_*` no baja de 24 a 0: **queda en 24** | **F4.6 nueva** (14 sitios en las 10 superficies gateadas) + KPI corregido + **[ADICIÓN ARQUITECTO] F4.7** (ratchet de superficie cruda 42→28, solo baja) |
| **C2** | **BLOQ** | **El override de F6 era inalcanzable justo donde hace falta.** Verificado `client.ts:213-235`: **solo `api.get` acepta `init`**; `post`/`put`/`patch`/`delete` construyen el `RequestInit` adentro y `postAbortable` recibe un `AbortSignal`, no opciones. Y F4 prohibía explícitamente tocar los verbos. ⇒ un deadline de 20 s duro sobre **todo** `api.post`, sin escape, sobre operaciones de minutos verificadas: `/api/tickets/sync` (`endpoints.ts:237`), `/api/agents/run` (`:1153`, `:1229`), `/api/packs/start` (`:1495`), `/api/config/import` (`:2199`), `/api/executions/{id}/publish-to-ado` (`:1411`), `/api/drift/run` (`:1834`), `/api/glossary/scan` (`:1856`), `/api/qa-uat/run` (`:2649`), `/api/qa-browser/runs` (`:2839`), `/api/diag/backup/run` (`:2884`). Además `request()` **no está exportado**, así que el test de F6 no tenía por dónde inyectar el `fetchImpl` | **F6 rediseñada**: `opts?: RequestOptions` **aditivo** en los 4 verbos + tabla de los 10 endpoints con `timeoutMs: 0` + gate que la verifica + `export` de `request` para test |
| **C3** | **BLOQ** | **F7 exigía dos artefactos que ninguna fase construía, uno sobre premisa falsa.** (a) La tabla de decisión dice `"unknown"` ⇒ *"Esqueleto de carga en la pantalla pedida. **Este es el fix**"* y el smoke 1 lo espera, pero F7 no daba archivo, símbolo, diff ni caso de test para el esqueleto. (b) El microcopy del caso `"off"` decía *"reusar el mecanismo de avisos que ya existe en el shell; no construir un componente nuevo"* — **no existe tal mecanismo**: `App.tsx:516` monta `UndoToastHost` (undo, no avisos), `components/Toast.tsx` es un componente con estado propio por página, y `publishActivity` (`services/activityCenter.ts:89`) escribe en el Centro de Actividad, que es un log consultable, no un aviso visible. La instrucción era insatisfacible **y prohibía la única salida** | **F7 reescrita**: símbolos exactos (`Skeleton` de `components/ui`, `Toast`+`ToastState` montado en el shell, `publishActivity` para el rastro), diff completo y 3 casos de test nuevos |
| **C13** | **BLOQ** | **El diff que F3 dicta pone ROJO el gate que F3 crea.** F3 define el caso `cero_hex_en_App_module_css` (*"no matchea `/#[0-9a-fA-F]{3,8}\b/`"*) y afirma que *"hoy es satisfacible"* y que el archivo *"pasa de 4 hex a 0"*. Pero los comentarios que sus propios diffs prescriben escriben **cuatro literales hex dentro del mismo archivo**: `#a5b4fc` y `#6366f1` en el comentario de `.navTab.active`, `#b91c1c` y `#ef4444` en el de `.navBadge`. Verificado que el conteo es sobre contenido **crudo, sin strip de comentarios**: `uiDebtRatchet.test.ts:21` `HEX_RE = /#[0-9a-fA-F]{3,8}\b/g` aplicado en `:58` sobre `content`. ⇒ (a) el gate nuevo nace **rojo después del fix**, con la implementación que el plan dicta; (b) el delta declarado "4 → 0" es **falso**: queda en 4 (y `4 > 4` es falso, así que `uiDebtRatchet` sigue verde y la bitácora registra un número inventado). Es la **8ª recurrencia** del patrón "el comentario choca con su propio gate" en este repo. (`cero_rgba_de_blanco…` sobrevive **por casualidad**: el comentario escribe `rgba(255,255,255,0.45)` sin espacios y el gate busca `rgba(255, 255, 255` con espacios) | F3: los 4 comentarios **reescritos sin literales** + paso de verificación obligatorio de correr el gate **después** del fix |
| **C14** | **BLOQ** | **La única edición de UI de F4 introduce una regresión activa.** `PageErrorBoundary` es lo único que F4 cablea, y lo que ese boundary **sí** recibe son crashes de **render** — el propio plan cita el crash vivo del 266 en `dbcompare/radarLogic.ts:60`. Con el algoritmo de `userFacingMessage` tal como lo define F4, un `TypeError: Cannot read properties of undefined` es un `Error` común ⇒ cae en el **paso 4** y se muestra como **"No se pudo conectar con el servidor."** Hoy se muestra el `TypeError` real. Cambiar un diagnóstico correcto por uno falso, en el único archivo que F4 toca, es estrictamente **peor que el estado actual** | F4: **paso 0** en el algoritmo (un `Error` que no es `GatewayError`/`TimeoutError` y cuyo `message` no matchea `/^\d{3}\s/` devuelve su `message` tal cual) + caso de test `ufm_un_typeerror_de_render_no_se_disfraza_de_error_de_red` |
| **C4** | IMP | `§10.2` dice *"6 de 9 deben FALLAR"* pre-plan y F8 nombra 1,2,3,5,6,8 — pero los **9** smokes de §10 llevan escrito *"Antes del plan: FALLA"*. Un criterio de cierre binario que se contradice consigo mismo | §10.2 y F8: **9 de 9** |
| **C15** | IMP | **F0 no mide la línea base de `tsc --noEmit`**, pero F4, F6 y §10.1 exigen *"sin errores nuevos respecto de F0"*. Criterio delta contra una base que nunca se midió ⇒ **no verificable**. Y es justamente el criterio que atraparía el error de tipos del override de F6 | F0: comando + 7ª fila en la tabla de mediciones |
| **C16** | IMP | **F6 manda "copiar" un patrón de inyección que no compila para `request()`.** Verificado `flagHealth.ts:26`: `fetchImpl?: (path: string) => Promise<{ json(): Promise<unknown> }>` — ese tipo **no expone** `ok`, `status`, `statusText` ni `text()`, que es exactamente lo que `request()` usa en `:205-210`. Un modelo menor que obedezca al pie se atasca o degrada `request()` | F6: el tipo concreto escrito (`(input: string, init?: RequestInit) => Promise<Response>`) y aclarado que se copia **el patrón**, no la firma |
| **C17** | IMP | **La regla 5 de F5 no aplica al caso que F5 nombra como especial.** Regla 5: *"No cambiar la clave `ok`. Sigue siendo `False`"*. Verificado: `migrator.py:101` es `return jsonify({"error": "Migrador no habilitado (…)"}), 503` — **no tiene clave `ok`**. Ambigüedad binaria sin respuesta: ¿se agrega o no? Un modelo menor decide al azar y puede romper consumidores del 503 | F5 regla 5 reescrita con el caso "no la tiene" explícito |
| **C5** | IMP | F8 exigía correr los smokes *"sobre el commit anterior a F1"* mientras §9 **prohíbe `checkout`** (8 worktrees vivos). Contradicción interna con riesgo real de pisar trabajo ajeno | F8: los pre-smokes se corren **en F0** (antes de tocar nada) o en un worktree dedicado; `checkout` sigue prohibido |
| **C6** | IMP | Aritmética del DoD: *"los **6** archivos de test nuevos (**43** casos: 3+6+14+3+8+7+5)"*. Son **7** archivos y la suma da **46** | §10.1 recontado sobre el v2 |
| **C7** | IMP | KPI *"Requests HTTP sin deadline: todos → **0**"* lo contradice F6 misma, que declara los tres `raw*` como gap conocido; y C2 lo rompe del otro lado | KPI honesto: `api.*` con override; `raw*` gap declarado |
| **C8** | IMP | F1 dejaba abierto el agujero que su propio KPI cierra: `App.tsx:173` usa `d.shell_v2_enabled === true`, así que un 200 sin la clave **vuelve a cambiar la nav después del primer paint**. El precedente correcto está **dos líneas abajo**, en el mismo `.then`: `App.tsx:177` hace `d.ui_shortcuts_enabled !== false` (plan 172 F2) por exactamente esta razón | F1: `!== false` + 4º caso de test + se cita el precedente |
| **C9** | MEN | El diff ilustrativo de F5 inventa la forma del caso que usa de ejemplo: `docs.py:222` es `"message"` con **404**, no `"error"` con 403. Desglose real verificado: **14** con clave `error`, **10** con clave `message` | F5: las **dos** formas, con el desglose |
| **C10** | MEN | F3 bumpea `.toBe(53)`→`54` pero no el nombre del `it` `"re-apunta los **53** tokens de color con valor exacto"` (`themeLightTokens.test.ts:86`): es el patrón "el comentario choca con su gate" que este repo ya repitió 7 veces | F3: paso 3b |
| **C11** | MEN | No registra la huella de regresión. `docs/sistema/error_fingerprints.json` existe con **45** entradas y esquema `{id,title,class,status,log_pattern,log_guarded,killed_by,killed_commit,date_resolved,guard_test,evidence,note}`. Este plan mata 7 clases de error **con test guardián** y no registra ninguna | **F9 nueva** |
| **C12** | MEN | KPI *"18 de 18"*: tras F7 un deep link a una sección genuinamente apagada **sigue** redirigiendo (correctamente). El número es condicional | KPI: "18 de 18 **con la sección habilitada**" |
| **C18** | MEN | **Cuatro anclajes desviados** (el símbolo manda por §3.5, así que no cambian el diseño, pero el plan los declara *"verificado hoy"*): el bloque claro de `theme.css` abre en **:172**, no en :166 (el `:root` base es **:3-164**); `computeVisibleTabs` es **:68-83** — :51-60 es `VisibilityInput`; el default de `STACKY_UI_SHELL_V2_ENABLED` es una sentencia de **:1811-1813** (`.strip().lower() == "true"`), con el literal `"true"` en :1812; y el efecto de redirección tiene **11 `else if` (:266-276) + 1 `if` (:265)** = 12 ramas, no "doce ramas `else if`" | Los cuatro corregidos in situ |
| **C19** | MEN | **Riesgo de implementación silencioso en F3, derivado de C18.** `themeContrast.test.ts:16-17` extrae los bloques con un regex no-greedy `([\s\S]*?)\n\}`: captura **solo hasta el primer `\n}`**. Un token agregado fuera de `:3-164` (p. ej. después del cierre, o en el bloque `[data-density]` de :250) es **invisible** para el anti-drift y para `themeLightTokens`: todo pasa verde y el token queda sin re-apuntar en claro — exactamente el drift que esos gates existen para atrapar | F3 paso 1: `--nav-badge-bg` va **dentro** de `:3-164`, con verificación |
| **C20** | MEN | **Los archivos nuevos bajo `components/ui/` y `components/shell/` tienen presupuesto CERO ABSOLUTO**, no baseline: `uiDebtRatchet.test.ts:109-112` ⇒ `forcedZero = kind === "nativeDialogByFile" \|\| file.startsWith("components/ui/") \|\| file.startsWith("components/shell/")`, y ni un `UI_DEBT_REGEN` futuro puede resubirlo. Afecta a F1 (agrega `SHELL_V2_DEFAULT` en `components/shell/shellNav.ts`) y a cualquier primitiva nueva | Anotado en F1 y en §3.4 |

**Verificaciones que el v1 pasó y que este v2 conserva sin tocar** (medidas en esta corrida, no heredadas): los 9 `useState(false)` en `76/78/80/83/85/97/99/100/102`; las **12** ramas del efecto de redirección en `265-276`; los **8** `probeFlagHealth` en `143-165`; las **3** ocurrencias de `setShellV2Enabled` (`85`/`173`/`179`); `throw new Error(...)` en `client.ts:208`; los 4 hex de `App.module.css` son exactamente `#6366f1 #a5b4fc #b91c1c #ffffff`; `PAIRS` tiene **24** entradas y el `it` dice literal *"los 24 pares…"*; `initUiSections` **sí** es `async (): Promise<void>` (`services/uiSections.ts:20`), así que el `.finally()` de F7 es válido; `FlagHealthVerdict` está exportado (`flagHealth.ts:7`); `ProbeOptions.fetchImpl`/`sleepImpl` existen (`flagHealth.ts:25-32`), así que "copiarlo, no inventar otro" es correcto; los 9 nombres de archivo reservados están **libres**; `devDependencies` son exactamente las 6 y **no hay script `test`**. Y dos verificaciones nuevas que **refuerzan** la frontera de §4: B-06 vale **24/13 idéntico en los 8 worktrees vivos** (ningún plan en vuelo agrega ocurrencias que rompan el gate de F5 al mergear), y la región de gates/redirección de `App.tsx` es **byte-idéntica** en `wt-plan-263`, `wt-plan-265` y `wt-plan-266`.

**Flags nuevas en v2: sigue siendo CERO.** Ninguna corrección de este v2 introduce flag; F6 refuerza por qué (§3.6 fila F6).

---

## 1. Objetivo

Cerrar los **7 condicionantes P0** (B-01…B-07) que la auditoría UX/UI del 2026-07-29 dejó como bloqueantes del veredicto `GO CONDICIONADO`, y dejar verificados los 6 gates de salida C1–C6. Ninguno de los siete es un rediseño: son cuatro correcciones de arranque de aplicación, dos de contrato de error y una de tokens de color, todas localizadas, todas con `archivo:línea` abierto. Al terminar este plan, un deep link a `/devops` sobrevive un F5, la navegación no cambia de forma después del primer paint, un backend colgado produce un error accionable en vez de un spinner eterno, la nav v1 no esconde tabs ni se vuelve ilegible en tema claro, y el operador lee la frase que el backend redactó en lugar de `403 FORBIDDEN: {"ok":false,...STACKY_DB_COMPARE_ENABLED...}`.

**KPI / impacto esperado** (medibles sin telemetría nueva, por smoke manual enumerado en §10):

| Métrica | Hoy (verificado) | Objetivo |
|---|---|---|
| Pantallas donde F5 / deep link aterriza en la pantalla pedida, **con la sección habilitada** (C12) | 10 de 18 | **18 de 18** |
| Ventana de rebote tras el montaje | ~1.2 s (`flagHealth.ts:40-41`, 2 reintentos 400→800 ms) | **0 ms** (no se redirige con gate sin resolver) |
| Cambios de arquitectura de navegación por carga | 1 (v1 → v2), **y un 2º si el health responde 200 sin la clave** (C8) | **0** en los dos casos |
| Cadenas de error del backend que nombran `STACKY_*` en texto para el operador | 24 (13 archivos: 14 con clave `error`, 10 con clave `message`) | **0** (el nombre se mueve a `detail.flag`) |
| **Sitios del frontend que aplanan la excepción y la pintan cruda al operador** (C1: el modismo `X instanceof Error ? X.message : String(X)`) | **42 en 26 archivos** | **28** — los **14** de las 10 superficies gateadas van a `userFacingMessage()`; el resto queda **congelado por ratchet que solo baja** (F4.7) |
| `STACKY_*` visible en pantalla ante una feature apagada | sí (dentro del string crudo) | **0** — y es F4.6, **no** F5, quien lo logra: F5 solo mueve el nombre de `error` a `detail.flag`, **dentro del mismo string crudo** |
| Contraste del texto de tab en reposo, tema claro | **1.03:1** | **≥ 4.5:1** (6.00:1 con el token propuesto) |
| Contraste del texto de tab en reposo, tema oscuro | **4.48:1** (falla AA por 0.02) | **≥ 4.5:1** (5.62:1) |
| Tabs inalcanzables por desborde horizontal de la nav v1 | sin mecanismo de recuperación | **0** (scroll disponible) |
| Requests `api.*` sin deadline | todos (`request()` no pasa `signal` propio) | **0 en `api.*`**, con override `timeoutMs` por llamador y **10 endpoints largos declarados en `timeoutMs: 0`** (F6). **Gap declarado (C7):** `rawGet`/`rawPost`/`rawPut` siguen **sin** deadline — frontera con el plan 263 |

**Flags nuevas: CERO.** La justificación está en cada fase y consolidada en §3.6, incluido el caso tentador (el timeout de F6) y por qué convertirlo en flag sería un error de diseño, no una precaución.

**Nota de honestidad sobre el KPI de errores (C1).** El v1 medía el defecto en el lado equivocado del cable: contaba las 24 cadenas del backend. El daño que ve el operador se mide en el frontend, y son **42 sitios en 26 archivos** los que aplanan la excepción. Reescribir el backend sin migrar consumidores no baja ese número de 42: lo deja igual y **reubica** el nombre de la flag dentro del mismo string. Por eso el v2 agrega F4.6 (migración de las 10 superficies gateadas) y F4.7 (ratchet).

---

## 2. Por qué ahora / gap que cierra

La auditoría (`docs/reportes/2026-07-29_AUDITORIA_UX_UI_PRODUCCION.md`, 883 líneas, commit `fd4e45d3`) es explícita en su §1: *"no falta construir, falta terminar de conectar lo construido"*. Los dos ejes que concentran el daño son de arranque, no de arquitectura:

1. **El arranque decide la navegación con 10 llamadas de red y decide mal cuando la red tarda.** Verificado en esta corrida: `frontend/src/App.tsx` inicializa **nueve** gates en `false` (líneas `:76` migrador, `:78` devops, `:80` dbcompare, `:83` costcenter, `:85` shellV2, `:97` planes, `:99` evolution, `:100` incidencias, `:102` deepSearch) y el efecto de `App.tsx:264-277` redirige a `tickets` en **doce ramas** — **1 `if` (`:265`) + 11 `else if` (`:266-276`)**, no doce `else if` (C18) — cuando ve el gate en falso. El gate solo se resuelve por red, después del montaje (`App.tsx:143-167`, ocho `probeFlagHealth`).
2. **El cliente HTTP destruye el mensaje que el backend redacta.** Verificado: `frontend/src/api/client.ts:208` — `throw new Error(\`${res.status} ${res.statusText}: ${text}\`)`, y el contrato rico `GatewayErrorBody { error, message, correlation_id, detail }` ya existe tipado en el mismo archivo (`:36-41`) y ya se devuelve por `rawPost`/`rawGet`/`rawPut`. La pieza está construida; falta que `request()` la use.

**El comentario que parecía proteger el caso 1 es falso, y está confirmado.** `flagHealth.ts:19-23` implementa `nextEnabledState(prev, verdict)` devolviendo `prev` cuando el veredicto es `"unknown"`; su docstring dice *"unknown conserva el último estado conocido (sticky)"*. Pero `prev` al montar **ya es `false`** (`useState(false)`), así que "conservar el último estado conocido" conserva exactamente el estado que dispara el rebote. El mecanismo es correcto y el valor inicial lo anula. Ese es el hallazgo H-01 y es la razón por la que B-01 no se arregla tocando `flagHealth.ts`: se arregla introduciendo un tercer estado.

**Por qué ahora y no después:** los cuatro planes recientes que tocan estos mismos dos archivos (263, 265, 266, 267) van a seguir llegando. Cada plan que aterriza sobre `App.tsx` y `api/client.ts` sin que estos defectos estén cerrados hereda el rebote y el error crudo, y además mueve las líneas que la auditoría ancló. La frontera de §4 existe justamente porque este plan tiene que poder implementarse **en paralelo** a esos cuatro sin pisarlos.

**Gap frente a la auditoría:** la auditoría diagnostica y recomienda; no implementa, y en dos puntos su recomendación literal es insuficiente o incorrecta. Este plan corrige ambos con evidencia (§3.7): el conteo de archivos de B-06 y —más grave— la recomendación de tokenizar el badge de la nav con `var(--status-danger-solid)`, que **degradaría** el contraste de 6.47:1 a 3.76:1 en tema oscuro, sobre un token que el propio repo ya congeló como falla AA conocida en `frontend/src/__tests__/themeContrast.test.ts:71`.

---

## 3. Principios y guardarraíles

### 3.1 Rieles del producto (no negociables)

- **Human-in-the-loop.** Ningún cambio de este plan decide por el operador. La corrección de B-01 hace que la app **espere** a saber si una sección está activa en lugar de asumir que no lo está; cuando de verdad está apagada, redirige **y avisa**, no rebota mudo.
- **Mono-operador sin auth real.** `backend/api/_helpers.py` resuelve identidad con un header sin validar. **Prohibido** en este plan: RBAC, roles, login, multiusuario. H-08 (identidad de reserva) es B-12, P1, y queda fuera (§7).
- **Toda config del operador va por UI.** Este plan **no agrega** ninguna config del operador, así que el riel no se ejerce. Los kill-switches env-only tampoco aplican: no hay flag nueva (§3.6).

### 3.2 Testing (rieles duros del repo, verificados en esta corrida)

- **RTL y jsdom NO están instalados.** `frontend/package.json` declara en devDependencies exactamente: `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite`, `vitest`. No hay `@testing-library/*`, no hay `jsdom`. ⇒ **Prohibido especificar un solo test de componente en este plan.** Todo criterio es (a) test `.ts` **puro**, (b) gate de grep/ratchet sobre archivos, o (c) smoke manual con pasos enumerados.
- **No hay script `test` en `package.json`.** El binario existe en `frontend/node_modules/.bin/vitest`. El comando canónico del repo, y el único que este plan usa, es:
  ```
  cd "Stacky Agents\frontend"; npx vitest run <ruta relativa a frontend/>
  ```
- **Tests por archivo, siempre.** Hay contaminación cross-file conocida en la corrida completa de vitest. **Prohibido** `npx vitest run` sin ruta. **Prohibido** `grep -c` sobre la salida de vitest: duplica los conteos.
- **Backend: intérprete por ruta absoluta.** El venv que anda es `backend/venv` (existe también `.venv`, que no). Un worktree no tiene ninguno. Comando canónico de este plan:
  ```
  cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/<archivo>.py -q
  ```
  Un archivo por invocación. **Prohibido** `pytest -k <patrón>` como criterio: `N deselected` termina con **exit 0** y produce un falso verde perfecto.

### 3.3 El gate se corre CONTRA el defecto

Un test que nunca se vio rojo no prueba nada. **Cada fase de este plan declara su estado ROTO ESPERADO**: qué test falla, con qué mensaje, antes de escribir el fix. La secuencia obligatoria por fase es:

1. Escribir el test. Correrlo. **Ver el rojo y leer el mensaje**: tiene que fallar por la razón que la fase dice atrapar, no por un import roto ni por un archivo que no existe.
2. Recién entonces aplicar el cambio de producción.
3. Correr el test. Ver el verde.
4. Correr los gates compartidos que la fase nombra y comparar contra la **línea base medida en F0**.

Si el test pasa antes del fix, el test está mal: no mide lo que dice medir. Volver al paso 1.

### 3.4 Gates compartidos: criterios DELTA, nunca "todo verde"

Hay gates rojos por deuda ajena a este plan. **Prohibido** escribir un DoD que exija una suite compartida en verde: es insatisfacible y obliga a arreglar rojo ajeno. Todos los criterios sobre gates compartidos de este plan son **delta**: *mi cambio no empeora el número que F0 midió*. Los tres gates compartidos que este plan roza, con su mecánica ya verificada:

| Gate | Archivo | Mecánica verificada | Efecto de este plan |
|---|---|---|---|
| Deuda visual por archivo | `frontend/src/__tests__/uiDebtRatchet.test.ts:97-131` | `count > allowed` ⇒ una **BAJA nunca falla**; solo cuenta hex en `*.module.css`; baseline de `App.module.css` = **4** | F3 lleva 4 → 0. `0 > 4` es falso ⇒ pasa **sin regenerar el baseline** |
| Anti-drift color base↔claro | `frontend/src/__tests__/themeContrast.test.ts:100-116` | todo token de color nuevo en `:root` **debe** re-apuntarse en el bloque claro o el gate se pone rojo | F3 agrega **un** token ⇒ reconciliación de 3 pasos obligatoria, escrita en F3 |
| Ratchet de tests del arnés | `backend/tests/test_harness_ratchet_meta.py:43-53` + `backend/tests/test_plan259_ratchet_script_parity.py:46` | todo `tests/test_*.py` nuevo va a `HARNESS_TEST_FILES` **o** a `tests/harness_ratchet_allowlist.txt`; el test compara **conjuntos** (`solo_en_sh`), no tamaños, y hoy vale **64 con límite 64: holgura CERO** (medido: `.sh`=719, `.ps1`=655, `solo_en_ps1`=0) | F5 agrega **1** test backend ⇒ **hay que registrarlo en los DOS scripts**. Registrarlo solo en el `.sh` sube `solo_en_sh` a 65 y pone rojo el gate de paridad. **v2:** F9 NO agrega un segundo archivo (su caso va en el de F5) precisamente para no repetir esta operación con holgura cero |
| **[v2, C20] Presupuesto CERO ABSOLUTO por carpeta** | `frontend/src/__tests__/uiDebtRatchet.test.ts:109-112` | `forcedZero = kind === "nativeDialogByFile" \|\| file.startsWith("components/ui/") \|\| file.startsWith("components/shell/")` ⇒ para esas dos carpetas el techo es **0**, no un baseline, y **ni un `UI_DEBT_REGEN` futuro puede resubirlo** | F1 agrega `SHELL_V2_DEFAULT` en `components/shell/shellNav.ts`: es un `.ts` con un booleano, sin hex ni inline style ⇒ **sin efecto**. Pero cualquier `.tsx`/`.module.css` que este plan agregara bajo esas dos carpetas arrancaría con techo 0. Vale para el aviso de F7 (§F7, punto 3) |

### 3.5 Regla de anclaje de este plan (obligatoria para el implementador)

**Todo anclaje de este plan es por SÍMBOLO, nunca por número de línea de `App.tsx` ni de `api/client.ts`.** Símbolo = nombre de función, de constante, de estado de React, de selector CSS, de clave de objeto, o una cadena literal única y buscable.

Los números de línea que aparecen en este documento son **contexto de lectura verificado el 2026-07-30**, no instrucciones de edición. Se citan para que el implementador confirme que está mirando el código correcto; si no coinciden, **el símbolo manda y la línea se descarta**. Esta regla no es celo: cuatro planes en vuelo tocan estos dos archivos (§4), y ya caducó un anclaje de `docs/sistema/07-frontend.md:14` por exactamente esta causa.

Forma de localizar, siempre:
```
cd "Stacky Agents\frontend"; Select-String -Path src\App.tsx -Pattern "setShellV2Enabled"
```
y editar la ocurrencia que el símbolo devuelve. **Prohibido** `sed -n '85p'` o cualquier edición posicional.

### 3.6 Flags: cero nuevas, con justificación por fase

La regla del repo es que toda flag nueva nace **default ON** salvo que (A) queme tokens en reposo o (B) escriba en un sistema real del operador. Ninguna de las siete correcciones cae en (A) ni en (B) — pero eso no significa que necesiten flag. Son **correcciones de defecto**: el estado actual no es una alternativa que valga la pena preservar detrás de un toggle. Justificación por fase:

| Fase | ¿Flag? | Por qué |
|---|---|---|
| F1 (B-03) | No | La flag ya existe: `STACKY_UI_SHELL_V2_ENABLED` (`backend/config.py:1811-1813` — es una sentencia de 3 líneas `os.getenv(...).strip().lower() == "true"`, con el literal `"true"` en `:1812`; C18. Expuesta en `backend/api/diag.py:634`). F1 **alinea el frontend con esa flag**. Agregar una segunda flag para decidir si respetar la primera es incoherente |
| F2 (B-05) | No | Una línea de CSS (`overflow-x: auto`). Una flag que decida si la nav puede scrollear no tiene un caso de uso concebible; el gate de grep de F2 la protege mejor que un toggle |
| F3 (B-07) | No | Tokenizar colores. El estado actual (1.03:1 en tema claro) no es una opción que alguien quiera elegir. Protegido por gate de contraste, no por flag |
| F4 (B-02) | No | El diseño de F4 es **estrictamente aditivo** y retrocompatible byte a byte en `Error.message` (§3.7 y F4). No hay comportamiento viejo que preservar porque no se rompe ninguno |
| F5 (B-06) | No | Reescritura de 24 cadenas de error en 13 archivos. Una flag "¿filtrar nombres de variables de entorno al operador?" cuyo lado OFF es la filtración no debería existir |
| F6 (B-04) | **No — y este es el caso interesante** | Un `STACKY_UI_HTTP_TIMEOUT_MS` por UI parece correcto y es **circular**: el frontend leería el valor del deadline con una llamada HTTP que es exactamente la que el deadline protege. Si el backend está colgado —el escenario de H-04— la lectura de la flag cuelga y el timeout nunca se configura. El deadline vive como **constante del frontend** más **override por llamador** (parámetro de función, no config), que es lo que cubre la varianza real (ejecuciones de agente, publicaciones) |
| F7 (B-01) | No | Eliminar un defecto de estado inicial. El lado OFF de una flag sería "seguir rebotando", que es el bug |

Consecuencia operativa: **este plan NO toca `backend/services/harness_flags.py`, NO toca `_CURATED_DEFAULTS_ON`, NO toca `_FROZEN_BOUNDS`, NO toca `_REQUIRES_MAP_FROZEN` ni `_CATEGORY_KEYS`, y NO agrega nada a `harness_defaults.env`.** No hay que registrar nada en las 6 estructuras / 5 archivos del cableado de flags. Si el implementador se encuentra editando `harness_flags.py`, se salió del plan.

### 3.7 Dos correcciones a la fuente

La auditoría es evidencia de primera calidad y este plan la reusa sin re-derivarla. Dos puntos, sin embargo, no sobreviven a la verificación y este plan se desvía de ellos **a propósito**:

**(a) B-06 son 13 archivos, no 16.** La auditoría cierra H-06 con *"Archivos a modificar: los 16 archivos de `backend/api/` listados arriba"*. Su comando, corrido de nuevo hoy, da 24 ocurrencias en **13** archivos:
```
grep -rlE '"(error|message)":\s*"[^"]*STACKY_[A-Z_]+' backend/api --include=*.py
```
→ `db_compare.py`, `db_compare_demo.py`, `db_compare_masking.py`, `db_compare_repo.py`, `db_compare_watch.py`, `diag.py`, `docs.py`, `evolution.py`, `evolution_fitness.py`, `evolution_knowledge.py`, `evolution_optimizer.py`, `migrator.py`, `plans_board.py`.

El "16" de la auditoría es el conteo de sus propios **ejemplos** (16 pares `archivo:línea`), no de archivos distintos. Y su lista de ejemplos **omite dos archivos que su propio grep sí encuentra**: `db_compare_demo.py` y `evolution_optimizer.py`. Un implementador que trabajara sobre la lista de ejemplos dejaría esos dos afuera y el gate de F5 se lo diría, pero después de escribir el fix. F5 usa el grep, no la lista.

**(b) El badge de la nav NO se tokeniza con `var(--status-danger-solid)`.** La auditoría recomienda, para H-07: *"`var(--status-danger-solid)` (badge)"* con criterio de aceptación *"ningún literal de color en `App.module.css`; contraste medido ≥ 4.5:1 en ambos temas"*. Esas dos cosas **son incompatibles entre sí**, y el propio repo lo tiene documentado:

- Hoy: `.navBadge { background: #b91c1c; color: #ffffff; }` (`App.module.css:49-50`). Blanco sobre `#b91c1c` = **6.47:1**. Cumple AA. El comentario de la regla (`App.module.css:41-42`, plan 134 F5) dice *"Rojo fijo con texto blanco: contraste garantizado en tema claro y oscuro"* — y es cierto.
- Con `var(--status-danger-solid)`: en oscuro el token vale `#ef4444` (`theme.css:74`) y blanco sobre `#ef4444` = **3.76:1**. **Falla AA.**
- Corroboración independiente en el repo: `frontend/src/__tests__/themeContrast.test.ts:69-73` congela `DARK_SHORTFALLS = { ..., "--text-on-solid|--status-danger-solid": 3.76, ... }` como **falla AA conocida y documentada** del tema oscuro, con un tripwire anti-drift. El valor que este plan calculó de forma independiente (3.76) coincide al centésimo con el que el repo ya tenía congelado.

Seguir la recomendación literal movería el badge desde un valor que cumple AA hacia un token que el repo ya declaró que no cumple. F3 tokeniza el badge con **un token nuevo, `--nav-badge-bg: #b91c1c`**, que preserva los 6.47:1, y usa el token invariante existente `--text-on-solid` (`theme.css:89` = `#ffffff`) para el texto. Resultado: `App.module.css` queda con **cero** literales de color y el contraste **sube o se mantiene** en los cinco casos. Los dos objetivos se cumplen; la recomendación intermedia se descarta.

---

## 4. Frontera con los planes 263, 265, 266 y 267

Cuatro planes recientes tocan `frontend/src/App.tsx` y/o `frontend/src/api/client.ts`, los dos archivos centrales de este plan. Esta sección es de cumplimiento obligatorio: define qué toca este plan, qué no, y cómo se ancla para no pisarse.

| Plan | Estado | Zona que toca | Colisión con este plan | Regla |
|---|---|---|---|---|
| **267** — catálogo único de acciones DevOps | IMPLEMENTADO 9/9 | `api/client.ts:206-209` — **exactamente** el bloque que F4 reemplaza | **DIRECTA** | Ya está en el árbol. F4 **parte del estado post-267**, verificado hoy: `request()` vive en `:190-211`, hace `reportOutcome(res)` antes del `if (!res.ok)`, y usa `isAbortError(e)` / `reportConnectionFailure()` en el `catch` del `fetch`. **F4 conserva esas tres llamadas intactas** y solo cambia la expresión del `throw`. Ver el diff literal en F4. **v2 (C2):** F6 además agrega un parámetro **opcional al final** a `post`/`put`/`patch`/`delete` y exporta `request`; el 267 no depende de esas firmas (depende de `reportOutcome`/`isAbortError`, que no se tocan) y todos los llamadores existentes compilan igual |
| **266** — cero pantalla rota en el Comparador de BD | SIN implementar (3 rechazos; crash vivo en `dbcompare/radarLogic.ts:60`) | `App.tsx:33`, `:346`, `:495` — `:346` y `:495` **encierran el JSX de la nav v1**, donde caen F2 y F3 | **ADYACENTE** | F2 y F3 **no tocan `App.tsx`**: operan sobre `App.module.css` y `theme.css`, que el 266 no toca. La nav v1 se corrige por CSS, sin abrir el JSX. Colisión eliminada por construcción |
| **265** — consola DevOps pantalla completa | IMPL en su worktree, sin merge | `App.tsx:252`, `:254`, `:520` | **ADYACENTE** | `:252-254` es el bloque `CORE_SHORTCUT_DEFS.forEach(...)` (verificado hoy). F1 y F7 tocan `useState`/`useEffect` de gates y el efecto de redirección, no los atajos. Anclar por `setShellV2Enabled`, `probeFlagHealth`, `selectTab("tickets")` |
| **263** — tablero de planes denso | SIN implementar | `App.tsx:211` y `api/client.ts:96-99` | **ADYACENTE** | `client.ts:96-99` es la firma de `rawGet` (verificado). **F4 y F6 no cambian la firma de `rawGet`.** F6 agrega el deadline **dentro** del cuerpo de `request()` y deja `rawGet`/`rawPost`/`rawPut` sin tocar (ver "Alcance explícito" en F6) |

### Regla de anclaje que rige esta frontera

Ver §3.5. Concretamente, para cada archivo compartido, los símbolos que este plan usa como ancla y que **ningún** plan de la tabla renombra:

- `frontend/src/App.tsx`: `setShellV2Enabled`, `probeFlagHealth`, `nextEnabledState`, `selectTab("tickets")`, `initUiSections`, `computeVisibleTabs`, `shellV2Enabled ?`.
- `frontend/src/api/client.ts`: `async function request<T>`, `reportOutcome`, `isAbortError`, `GatewayErrorBody`, `postAbortable`.
- `frontend/src/App.module.css`: selectores `.nav`, `.navTab`, `.navTab:hover`, `.navTab.active`, `.navBadge`.
- `frontend/src/theme.css`: bloques `:root {` y `:root[data-theme="light"] {`.

**Prohibido** en este plan, por frontera: tocar `dbcompare/radarLogic.ts` (es del 266), tocar `plansBoard/` (263), tocar `pages/DevOpsPage.tsx` o `components/devops/` salvo la lectura de F4.5 (265/267), y renombrar cualquiera de los símbolos de la lista anterior.

### Archivos nuevos: nombres reservados

Verificado hoy que **no existen** y que ningún plan de la tabla los declara:

- `frontend/src/api/gatewayError.ts`
- `frontend/src/services/gateState.ts`
- `frontend/src/api/__tests__/plan273GatewayError.test.ts`
- `frontend/src/api/__tests__/plan273RequestTimeout.test.ts`
- `frontend/src/services/__tests__/plan273GateState.test.ts`
- `frontend/src/__tests__/plan273ShellV2Default.test.ts`
- `frontend/src/__tests__/plan273NavCss.test.ts`
- `frontend/src/__tests__/plan273LegacyErrorParsers.test.ts`
- `frontend/src/__tests__/plan273ErrorSurface.test.ts` **(v2, F4.6)**
- `frontend/src/__tests__/plan273RawErrorSurfaceRatchet.test.ts` **(v2, F4.7)**
- `backend/tests/test_plan273_error_message_sin_flags.py`

**Archivos existentes que el v2 SÍ edita y el v1 no listaba** (por C1 y C2, con su justificación de frontera):
- Los **10** de F4.6 (6 en `components/dbcompare/`, 3 en `evolution/`, `pages/EvolutionCenterPage.tsx`). **Ninguno** de los 4 planes de la tabla de §4 los toca: el 266 vive en `dbcompare/radarLogic.ts` (que F4.6 **no** toca) y el 263 en `plansBoard/`.
- `frontend/src/api/client.ts` — **también** las firmas de los 4 verbos (C2). Sigue **sin** tocar `rawGet`/`rawPost`/`rawPut`, que es donde está la frontera con el 263.
- `Stacky Agents/docs/sistema/error_fingerprints.json` (F9).

(Existe `frontend/src/services/flagGate.ts` — es la lectura de flags de la UI, **concepto distinto** de `gateState.ts`, que es la máquina de tres estados del gate de tab. No unificarlos en este plan.)

---

## 5. Fases

Orden por dependencias reales, **actualizado en v2**: **F0 → F1 → F2 → F3 → F4 → F4.5 → F4.6 → F4.7 → F5 → F6 → F7 → F9 → F8**. Cada fase es autocontenida y verificable sola.

- **F4.5** es un gate de protección que debe existir **antes** de F5 y F6.
- **F4.6 y F4.7 son nuevas (v2)** y van **entre F4.5 y F5**, no después: F5 depende de que el `message` humano **llegue a la pantalla**, y eso lo hace F4.6, no F4. Correr F5 antes de F4.6 abre una ventana en la que el operador lee `feature_disabled` en pantalla.
- **F9 (nueva, v2)** va después de F5 porque necesita su hash de commit.
- **F8 va última** y su **pre-pasada de smokes se corre en F0** (C5).

---

### F0 — Congelar la línea base de los gates compartidos y la regla de anclaje

**Objetivo:** medir, antes de tocar una sola línea de producción, los números contra los que las fases posteriores se compararán en delta. **Valor:** sin esta foto, los criterios delta de §3.4 no son verificables y el implementador termina persiguiendo rojo ajeno.

**Archivos a crear/editar:** ninguno de producción. Esta fase **solo mide y anota**.

**Procedimiento exacto.** Correr los cinco comandos y anotar la salida en el propio doc del plan (sección de bitácora al final, o en el mensaje de commit de F0):

```powershell
# (1) Deuda visual: baseline de hex de App.module.css. Esperado hoy: 4
cd "Stacky Agents\frontend"; Select-String -Path src\__tests__\uiDebtBaseline.json -Pattern "App.module.css"

# (2) Ratchet de deuda visual: estado ACTUAL (puede tener rojo ajeno)
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts

# (3) Gates de tema: estado ACTUAL de los tres
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeContrast.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeTokens.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeLightTokens.test.ts

# (4) Ratchet del arnés: lag .sh vs .ps1. Esperado hoy: sh=719 ps1=655 lag=64 (limite 64)
cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_plan259_ratchet_script_parity.py -q
cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_harness_ratchet_meta.py -q

# (5) B-06: conteo y archivos. Esperado hoy: 24 ocurrencias / 13 archivos
cd "Stacky Agents\backend"; (Select-String -Path api\*.py -Pattern '"(error|message)":\s*"[^"]*STACKY_[A-Z_]+').Count
cd "Stacky Agents\backend"; (Select-String -Path api\*.py -Pattern '"(error|message)":\s*"[^"]*STACKY_[A-Z_]+' | Select-Object -ExpandProperty Filename -Unique).Count

# (6) [v2, C15] LINEA BASE DE tsc. F4, F6 y §10.1 exigen "sin errores nuevos
# respecto de F0": sin este numero el criterio delta NO es verificable.
cd "Stacky Agents\frontend"; npx tsc --noEmit
# anotar el CONTEO de errores (0 si sale limpio) y, si hay, los archivos.

# (7) [v2, C1] Superficie de error cruda: sitios que aplanan la excepcion y la
# pintan al operador. Es el numerador real del KPI de C3.
cd "Stacky Agents\frontend"; (Select-String -Path src\*.ts,src\*.tsx,src\**\*.ts,src\**\*.tsx -Pattern 'instanceof Error' | Where-Object { $_.Path -notmatch '__tests__|\.test\.' }).Count
```

**Valores medidos el 2026-07-30** (si difieren, gana la medición del implementador y se anota la diferencia):

| Medición | Valor |
|---|---|
| `uiDebtBaseline.json` → `App.module.css` | **4** |
| Lag ratchet `.sh` − `.ps1` | **64** (`.sh`=719, `.ps1`=655; el test compara **conjuntos**: `solo_en_sh` = 64, `solo_en_ps1` = 0), límite `_PS1_LAG_MAX = 64` ⇒ **holgura CERO** |
| Entradas en `tests/harness_ratchet_allowlist.txt` | **196** |
| `themeLightTokens.test.ts` → `REQUIRED.length` | **53** |
| `themeTokens.test.ts` → `FROZEN_TOKENS.length` | **69** |
| B-06 ocurrencias / archivos | **24 / 13** (desglose: **14** con clave `error`, **10** con clave `message`; conjuntos de archivos **disjuntos** ⇒ 24 ocurrencias = 24 cuerpos distintos) |
| **[v2, C15] `tsc --noEmit`** → errores | **a medir** (anotar el conteo; el criterio de F4/F6/§10.1 es delta contra este número) |
| **[v2, C1] Modismo `X instanceof Error ? X.message : String(X)`** | **42 ocurrencias en 26 archivos** (0 en tests) |

**Tests:** ninguno nuevo. F0 no escribe código.

**Estado ROTO esperado:** no aplica (fase de medición). **Pero sí hay una observación obligatoria:** si alguno de los comandos (2) o (3) ya sale **rojo** antes de tocar nada, ese rojo es **ajeno** y queda anotado como tal. Las fases siguientes lo comparan en delta y **no lo arreglan**.

**Criterio de aceptación (binario):** las **ocho** mediciones de la tabla (v2: seis del v1 + `tsc` por C15 + superficie cruda por C1) están anotadas con su valor real y, para cada gate compartido, está anotado si hoy sale verde o rojo. Verificación: la bitácora contiene las ocho filas.

**Flag:** ninguna. F0 no cambia comportamiento.

**Impacto por runtime:** ninguno — F0 no modifica código. Los comandos son PowerShell y `pytest`/`npx`, disponibles en los tres runtimes. Fallback: si `Select-String` no está (runtime no-Windows), usar `grep -c` / `grep -l` sobre los mismos patrones; el número es el mismo.

**Trabajo del operador: ninguno.**

---

### F1 — B-03: el shell v2 arranca alineado con el backend y un fallo de health no lo degrada

**Objetivo:** eliminar el cambio de arquitectura de navegación en cada carga y la degradación permanente a la nav vieja cuando `/api/diag/health` falla. **Valor:** un solo modelo mental del producto por sesión; captura de pantalla y documentación dejan de ser ambiguas. Es la fase más barata y determina cuánto vale invertir en la nav v1.

**Archivos a editar:**
- `frontend/src/App.tsx` — **tres** ediciones (v2: la tercera es C8), todas ancladas por símbolo.

**Archivos a crear:**
- `frontend/src/__tests__/plan273ShellV2Default.test.ts`

**Símbolos exactos que se tocan:** el estado `shellV2Enabled` / setter `setShellV2Enabled` (declaración con `useState`), y el `.catch` de la cadena `fetch("/api/diag/health")`.

**Diff ilustrativo** (localizar por `Select-String -Pattern "setShellV2Enabled"`; hay exactamente 3 ocurrencias: la declaración y dos usos):

```diff
  // Plan 139: App Shell v2 (sidebar agrupada) — flag leída una sola vez al montar.
- const [shellV2Enabled, setShellV2Enabled] = useState(false);
+ // Plan 273 F1 (B-03): el default del frontend ESPEJA el del backend
+ // (STACKY_UI_SHELL_V2_ENABLED = "true", backend/config.py). Arrancar en false
+ // pintaba la nav v1 en el primer paint de TODA carga y saltaba a v2 al resolver
+ // el health: cambio de arquitectura de informacion visible, 100% de las cargas.
+ const [shellV2Enabled, setShellV2Enabled] = useState(SHELL_V2_DEFAULT);
```

```diff
      .catch(() => {
-       if (alive) setShellV2Enabled(false);
+       // Plan 273 F1 (B-03): un fallo de red NO cambia la arquitectura de
+       // navegacion. Antes, un solo health fallido dejaba la nav v1 para toda la
+       // sesion, sin ninguna senal al operador. Ahora se CONSERVA el optimista.
      });
```

Si al conservar el optimista el `.catch` queda vacío, **dejarlo vacío con el comentario** (no borrar el `.catch`: sin él, la promesa rechazada se vuelve un unhandled rejection en consola).

**Donde vive `SHELL_V2_DEFAULT`:** exportarlo desde `frontend/src/components/shell/shellNav.ts` (archivo puro, sin React, ya importado por `App.tsx` para `computeVisibleTabs`), al final del archivo:

```ts
/**
 * Plan 273 F1 (B-03) — ESPEJO del default del backend:
 * backend/config.py -> STACKY_UI_SHELL_V2_ENABLED = os.getenv(..., "true")
 * expuesto en backend/api/diag.py -> "shell_v2_enabled".
 * Si el default del backend cambia, este literal cambia en el MISMO commit;
 * plan273ShellV2Default.test.ts lo verifica leyendo config.py.
 */
export const SHELL_V2_DEFAULT = true;
```

**TERCERA edición, y es la que el v1 se perdió (C8).** El v1 declaraba el caso `{}` sin la clave como "límite conocido, fuera de scope", pero ese límite **contradice el KPI de §1** (*"cambios de arquitectura de navegación por carga: 0"*): un 200 con un cuerpo que no trae `shell_v2_enabled` vuelve a producir el salto v2 → v1 después del primer paint. Y el fix correcto **ya está escrito dos líneas más abajo, en el mismo `.then`**:

```diff
        if (alive) setShellV2Enabled(d.shell_v2_enabled === true);
        // Plan 172 F2 — default ON: una falla de red NO puede degradar el
        // teclado, así que la flag solo se toca cuando el health respondió.
        if (alive) setUiShortcutsEnabled(d.ui_shortcuts_enabled !== false);
```

`App.tsx:177` (plan 172 F2) resolvió **este mismo problema** para los atajos con `!== false`. F1 lo aplica al shell, que es el precedente de la casa, no una invención:

```diff
-       if (alive) setShellV2Enabled(d.shell_v2_enabled === true);
+       // Plan 273 F1 (B-03, C8): `=== true` trataba "clave ausente" como
+       // "apagado" y reintroducia el cambio de nav despues del primer paint con
+       // un health 200 incompleto. `!== false` es el patron que el plan 172 F2 ya
+       // uso para ui_shortcuts_enabled DOS LINEAS ABAJO, por la misma razon.
+       if (alive) setShellV2Enabled(d.shell_v2_enabled !== false);
```

**Casos borde, todos cubiertos por el test:**
- `/api/diag/health` responde `{ shell_v2_enabled: false }` ⇒ la nav **sí** pasa a v1. La flag apagada de verdad sigue funcionando; eso no es el bug.
- `/api/diag/health` responde 500 o no responde ⇒ se conserva `true`. **Este es el cambio.**
- `/api/diag/health` responde `{}` sin la clave ⇒ con `!== false` **se conserva `true`**. Cerrado en esta fase (C8), ya no es límite conocido.
- `/api/diag/health` responde `{ shell_v2_enabled: null }` ⇒ `null !== false` es `true` ⇒ se conserva v2. Correcto: `null` es "no sé", no "apagado". Mismo criterio que la línea de atajos.

**Tests PRIMERO.** Archivo: `frontend/src/__tests__/plan273ShellV2Default.test.ts`. Es un test **puro de archivos** (lee `config.py` y `shellNav.ts` con `fs`), sin React, sin DOM:

| Caso | Afirma |
|---|---|
| `paridad_default_backend_frontend` | El literal de `SHELL_V2_DEFAULT` en `shellNav.ts` coincide con el default del `os.getenv("STACKY_UI_SHELL_V2_ENABLED", "<valor>")` leído de `backend/config.py`. Regex sobre el fuente de `config.py`: `STACKY_UI_SHELL_V2_ENABLED"\s*,\s*"(true|false)"` |
| `app_no_inicializa_shellv2_en_false_literal` | `App.tsx` **no** contiene `useState(false)` en la misma línea que `shellV2Enabled`. Grep sobre el fuente |
| `el_catch_del_health_no_apaga_el_shell` | El fuente de `App.tsx` **no** contiene `setShellV2Enabled(false)`. Este es el gate contra el defecto exacto de H-02 |
| `una_clave_ausente_no_degrada_la_nav` (C8) | El fuente de `App.tsx` **no** contiene `shell_v2_enabled === true` y **sí** contiene `shell_v2_enabled !== false`. Gate contra el defecto de C8. **Verificación de que discrimina:** hoy `=== true` está en `App.tsx:173` y el caso tiene que verse rojo por ese match |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273ShellV2Default.test.ts
```

**Estado ROTO esperado (correr el test ANTES del fix):** **4 de 4 fallan.**
- `paridad_default_backend_frontend` falla al importar/leer `SHELL_V2_DEFAULT`: la constante no existe todavía.
- `app_no_inicializa_shellv2_en_false_literal` falla con el match de `const [shellV2Enabled, setShellV2Enabled] = useState(false);` (hoy en `:85`).
- `el_catch_del_health_no_apaga_el_shell` falla con el match de `setShellV2Enabled(false)` (hoy en `:179`).
- `una_clave_ausente_no_degrada_la_nav` falla con el match de `shell_v2_enabled === true` (hoy en `:173`).

Si el tercero o el cuarto pasan antes del fix, el grep está mal escrito: las dos cadenas están hoy en `App.tsx` y hay que verlas.

**Criterio de aceptación (binario):** los 4 casos verdes, con el comando de arriba. Y en delta: `npx vitest run src/components/shell/__tests__/shellNav.test.ts` mantiene el mismo resultado que en F0 (agregar una constante exportada no puede cambiarlo).

**Flag:** ninguna. Ver §3.6 — la flag ya existe en el backend y esta fase la respeta.

**Impacto por runtime:** **ninguno / idéntico en los tres.** Es un valor inicial de estado de React y un `.catch` vacío en el bundle del frontend; no hay una sola rama que dependa de Codex CLI, Claude Code CLI o GitHub Copilot Pro. **Fallback:** no aplica, no hay capacidad de runtime involucrada. (Esta observación vale para F1–F4, F6 y F7; F5 la repite por ser backend.)

**Trabajo del operador: ninguno.**

---

### F2 — B-05: la nav v1 no deja tabs inalcanzables

**Objetivo:** que ningún tab quede fuera de alcance por desborde horizontal de la nav v1. **Valor:** los módulos más caros de construir (Migrador, DevOps, Comparador BD, Centro de Costos, Planes, Evolución) son los últimos del orden de v1 y son los que caen fuera; funcionalidad invisible es funcionalidad con cero adopción.

**Archivos a editar:**
- `frontend/src/App.module.css` — regla `.nav`, **una** propiedad agregada (más `scrollbar-width`).

**Archivos a crear:** ninguno propio (el gate va en el archivo de F3, `plan273NavCss.test.ts`, porque las dos fases verifican el mismo archivo; el caso de F2 se escribe en F2).

**Diff exacto** (anclar por el selector `.nav {`; verificado hoy en `App.module.css:7-16`, sin `flex-wrap`, sin `overflow-x`, y el archivo **no tiene ninguna `@media`**):

```diff
  .nav {
    display: flex;
    gap: 0;
    background: var(--bg-panel);
    border-bottom: 2px solid var(--border);
    padding: 0 16px;
    position: sticky;
    top: 0;
    z-index: 30;
+   /* Plan 273 F2 (B-05): sin esto, con las 18 secciones habilitadas los ultimos
+      tabs quedan FUERA del viewport y no hay forma de llegar: los items son
+      white-space: nowrap y el contenedor no envuelve ni scrollea. */
+   overflow-x: auto;
+   scrollbar-width: thin;
  }
```

**Por qué `overflow-x: auto` y no `flex-wrap: wrap`:** `wrap` cambia el **alto** de una barra `position: sticky` con `z-index: 30`, y ese alto lo asume el layout de las 18 pantallas. `overflow-x: auto` no cambia el box model cuando no hay desborde: es un no-op visual en el caso normal y una vía de recuperación en el caso de desborde. Riesgo de layout: nulo.

**Casos borde:**
- Sin desborde (viewport ancho): `overflow-x: auto` no pinta scrollbar ni cambia el alto. Verificado por construcción de la propiedad CSS.
- La barra es `position: sticky` + `overflow-x: auto`: la combinación es válida; `sticky` opera sobre el ancestro de scroll **vertical**, que sigue siendo el documento.
- **Interacción con F3:** las dos fases editan `App.module.css`. F2 toca la regla `.nav`; F3 toca `.navTab`, `.navTab:hover`, `.navTab.active`, `.navBadge`. **Reglas disjuntas** — pero editar el mismo archivo en dos pasos con otra sesión activa en el árbol es riesgo real. Mitigación: hacer F2 y F3 en **el mismo commit** (ver §9, paso 3).

**Tests PRIMERO.** Caso a agregar en `frontend/src/__tests__/plan273NavCss.test.ts`:

| Caso | Afirma |
|---|---|
| `la_regla_nav_tiene_mecanismo_de_recuperacion_ante_desborde` | El bloque de la regla `.nav` de `App.module.css` contiene `overflow-x` **o** `flex-wrap`. Implementación: leer el archivo, extraer el bloque entre `.nav {` y el `}` siguiente, y afirmar sobre **ese bloque** (no sobre el archivo entero: `.shellContent` ya tiene `overflow: auto` y un grep de archivo completo pasaría **en falso**) |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273NavCss.test.ts
```

**Estado ROTO esperado:** el caso falla con `la regla .nav no declara overflow-x ni flex-wrap`. **Verificación obligatoria de que el gate discrimina:** antes de aplicar el fix, comprobar que el test falla **incluso** existiendo `overflow: auto` en `.shellContent` (línea 68 hoy). Si pasa, la extracción del bloque está mal y el gate no sirve — es exactamente el modo de falla "grep de archivo entero no discrimina".

**Criterio de aceptación (binario):** el caso verde. Y en delta: `npx vitest run src/__tests__/uiDebtRatchet.test.ts` da el **mismo** resultado que F0 (`overflow-x` y `scrollbar-width` no son hex ni inline style ⇒ ninguna dimensión del baseline se mueve).

**Flag:** ninguna. Ver §3.6.

**Impacto por runtime:** ninguno / idéntico en los tres — es una propiedad CSS en el bundle. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F3 — B-07: la nav v1 se lee en los dos temas y sale del literal de color

**Objetivo:** que las etiquetas de la nav v1 sean legibles en tema claro y oscuro, tokenizando los 5 literales de color, sin degradar el contraste de ningún elemento. **Valor:** el tema claro es una funcionalidad completa y construida (`theme.css:166-244`) que hoy queda inutilizable por tres literales; y v1 es el primer paint de toda carga mientras F1 no esté desplegado.

**Archivos a editar:**
- `frontend/src/App.module.css` — reglas `.navTab`, `.navTab:hover`, `.navTab.active`, `.navBadge`.
- `frontend/src/theme.css` — bloque `:root {` y bloque `:root[data-theme="light"] {`: **un** token nuevo en cada uno.
- `frontend/src/__tests__/themeLightTokens.test.ts` — agregar el token a `REQUIRED` y **bumpear** el literal `.toBe(53)` a `54`.
- `frontend/src/__tests__/themeContrast.test.ts` — agregar **un** par a `PAIRS` y actualizar el texto del nombre del `it` (de "los 24 pares" a "los 25 pares").

**Archivos a crear:**
- `frontend/src/__tests__/plan273NavCss.test.ts` (compartido con F2).

**Los 5 literales, verificados hoy en `App.module.css`, con el contraste real medido:**

| Selector | Literal actual | Contraste hoy (oscuro) | Contraste hoy (claro) | Token propuesto | Contraste con el token (oscuro / claro) |
|---|---|---|---|---|---|
| `.navTab` `color` | `rgba(255, 255, 255, 0.45)` | **4.48:1** (falla AA por 0.02) | **1.03:1** | `var(--text-muted)` | **5.62:1** / **6.00:1** |
| `.navTab:hover` `color` | `rgba(255, 255, 255, 0.8)` | 11.32:1 | **1.05:1** | `var(--text-primary)` | **14.64:1** / **14.84:1** |
| `.navTab.active` `color` | `#a5b4fc` | 8.68:1 | **1.87:1** | `var(--accent)` | **5.17:1** / **4.88:1** |
| `.navTab.active` `border-bottom-color` | `#6366f1` | (borde, no texto) | (borde, no texto) | `var(--accent)` | n/a (no es texto) |
| `.navBadge` `background` | `#b91c1c` | **6.47:1** (blanco encima) | 6.47:1 | `var(--nav-badge-bg)` (**token nuevo**, `#b91c1c`) | **6.47:1** / **6.47:1** |
| `.navBadge` `color` | `#ffffff` | — | — | `var(--text-on-solid)` (ya existe, `theme.css:89`) | — |

Los seis valores de la columna "con el token" se calcularon con la fórmula de luminancia relativa WCAG sobre `--bg-panel` (`#161b22` oscuro / `#f6f8fa` claro). **Los seis superan 4.5:1 en ambos temas** ⇒ el criterio de aceptación de esta fase es satisfacible. `#a5b4fc` y `#6366f1` no existen en `theme.css`: son índigos ajenos al design system, cuyo acento real es `--accent` (`theme.css:17` = `#388bfd` oscuro, `:187` = `#0969da` claro).

**Por qué el badge lleva token nuevo y NO `var(--status-danger-solid)`:** ver §3.7(b). En una línea: `--status-danger-solid` vale `#ef4444` en oscuro y blanco encima da **3.76:1**, un valor que el propio `themeContrast.test.ts:71` ya tiene congelado como falla AA conocida. Tokenizar el badge con él bajaría el contraste de 6.47 a 3.76.

> **RESTRICCIÓN BLOQUEANTE v2 (C13): PROHIBIDO escribir un literal hex en un comentario de `App.module.css`.** El v1 dictaba comentarios que citaban `#a5b4fc`, `#6366f1`, `#b91c1c` y `#ef4444` para documentar *por qué* se sacó cada color — y con eso **rompía su propio gate**. Verificado: `uiDebtRatchet.test.ts:21` define `HEX_RE = /#[0-9a-fA-F]{3,8}\b/g` y `:58` lo aplica sobre el **contenido crudo** del `*.module.css`, **sin strip de comentarios**. ⇒ el caso `cero_hex_en_App_module_css` de esta misma fase habría nacido **rojo después del fix**, y el delta declarado "4 hex → 0" habría sido falso (queda en 4, y como `4 > 4` es falso, `uiDebtRatchet` sigue verde y el número inventado entra en la bitácora sin que nada grite). Es la **8ª recurrencia** de "el comentario choca con su propio gate" en este repo. Los comentarios de abajo están reescritos **perifrásticamente**: dicen lo mismo sin un solo `#`. La aritmética con los valores concretos vive en la tabla de esta sección y en §3.7(b), que son Markdown, no CSS.

**Diff ilustrativo — `App.module.css` (comentarios SIN literales de color, C13):**

```diff
  .navTab {
    padding: 10px 20px;
    ...
-   color: rgba(255, 255, 255, 0.45);
+   /* Plan 273 F3 (B-07): era un rgba de blanco al 45% => 1.03:1 sobre --bg-panel
+      en tema claro (invisible) y 4.48:1 en oscuro (falla AA por 0.02). Un literal
+      no lo puede re-apuntar el tema; el token si. Valores: ver el plan 273 F3. */
+   color: var(--text-muted);
    ...
  }

  .navTab:hover {
-   color: rgba(255, 255, 255, 0.8);
+   color: var(--text-primary);
  }

  .navTab.active {
-   color: #a5b4fc;
-   border-bottom-color: #6366f1;
+   /* Plan 273 F3 (B-07): eran dos indigos ajenos al design system, que no existen
+      en theme.css. El acento del sistema es --accent. */
+   color: var(--accent);
+   border-bottom-color: var(--accent);
  }

  .navBadge {
    ...
-   background: #b91c1c;
-   color: #ffffff;
+   /* Plan 273 F3 (B-07): el rojo se mueve a theme.css como --nav-badge-bg con el
+      MISMO valor, que da 6.47:1 con el texto. NO se usa --status-danger-solid:
+      su valor en oscuro da 3.76:1, falla AA ya congelada en
+      themeContrast.test.ts. El texto usa el invariante --text-on-solid. */
+   background: var(--nav-badge-bg);
+   color: var(--text-on-solid);
  }
```

**Verificación obligatoria de C13, después de aplicar el fix y antes de cerrar la fase:**
```powershell
cd "Stacky Agents\frontend"; (Select-String -Path src\App.module.css -Pattern '#[0-9a-fA-F]{3,8}').Count   # tiene que dar 0
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273NavCss.test.ts                            # cero_hex_en_App_module_css VERDE
```
Si el conteo da 4, son los comentarios: reescribirlos, **no** relajar el gate ni regenerar el baseline.

**Diff ilustrativo — `theme.css`, los DOS bloques (obligatorio: ver reconciliación abajo).**

> **DÓNDE exactamente, y no es un detalle (C19 + C18).** Medido hoy: el bloque `:root` base es **`:3-164`** y el bloque claro **`:172-244`** (el v1 decía :166; el `:root` cierra en :164). Y `themeContrast.test.ts:16-17` extrae cada bloque con un regex **no-greedy** `([\s\S]*?)\n\}`: captura **solo hasta el primer `\n}`**. ⇒ un token agregado **después** de `:164`, o dentro del bloque `:root[data-density="compacto"]` de `:250`, es **invisible** para el anti-drift y para `themeLightTokens`: los tres gates de tema pasan verde y el token queda sin re-apuntar en claro, que es exactamente el drift que existen para atrapar. **`--nav-badge-bg` va dentro de `:3-164`** (y su gemelo dentro de `:172-244`). Verificación: `Select-String -Path src\theme.css -Pattern "nav-badge-bg"` tiene que devolver **dos** líneas, una en cada rango.

```diff
  /* dentro de :root { ... } */
+ /* Plan 273 F3 (B-07) — contador de la nav v1. Rojo con contraste garantizado
+    (6.47:1 con --text-on-solid) en AMBOS temas, por eso el valor NO cambia entre
+    bloques. Deliberadamente distinto de --status-danger-solid (#ef4444 => 3.76:1). */
+ --nav-badge-bg: #b91c1c;
```
```diff
  /* dentro de :root[data-theme="light"] { ... } */
+ --nav-badge-bg: #b91c1c;   /* Plan 273 F3 — mismo valor a proposito (ver :root) */
```

**Reconciliación OBLIGATORIA de los gates de tema (si se omite, F3 rompe tres tests ajenos).** `themeContrast.test.ts:100-116` es un gate anti-drift: *todo* token de color nuevo en `:root` que no esté re-apuntado en el bloque claro pone el test rojo, y su propio comentario (`:109-114`) dicta los tres pasos. Ejecutarlos **en el mismo commit**:

1. `theme.css`: agregar `--nav-badge-bg` al bloque `:root[data-theme="light"]` (ya está en el diff de arriba), **dentro de `:172-244`** (C19).
2. `themeLightTokens.test.ts`: agregar `["--nav-badge-bg", "#b91c1c"]` al array `REQUIRED` (formato verificado: `["--status-danger-solid", "#cf222e"],` en `:49`).
3. `themeLightTokens.test.ts`: bumpear `expect(REQUIRED.length).toBe(53)` → `.toBe(54)` (en `:94`).
3b. `themeLightTokens.test.ts`: **y el nombre del `it`** (C15/C10): `it("re-apunta los 53 tokens de color con valor exacto")` en `:86` → `"…los 54 tokens…"`. El v1 mandaba bumpear el literal y **se olvidaba del nombre**, que es el mismo patrón "el comentario choca con su gate" de C13. El comentario de `:92-93` ya avisa: *"si F3 obliga a agregar/quitar un token de color en el base, actualizá `REQUIRED` y BUMPEÁ este literal EN EL MISMO commit"*.
4. `themeContrast.test.ts`: agregar `["--text-on-solid", "--nav-badge-bg"],` al array `PAIRS`, y cambiar el nombre del `it` de `"los 24 pares cumplen AA (>= 4.5) en el tema claro"` a `"los 25 pares..."`. **No hay conteo congelado que bumpear en esta suite**: la aserción es sobre `fails`, no sobre `PAIRS.length` (verificado en `:77-80`). El par nuevo da 6.47:1 en ambos temas ⇒ pasa el gate estricto de claro y el de oscuro sin necesitar entrada en `DARK_SHORTFALLS`.
5. `themeTokens.test.ts`: **no se toca.** Su aserción es `FROZEN_TOKENS.length === 69` sobre una lista de tokens que deben **estar presentes**; agregar un token nuevo no la afecta (verificado en `:113-115`).

**Casos borde:**
- `--text-muted` y `--text-primary` ya están re-apuntados en el bloque claro (`theme.css:183` y `:182`) ⇒ el anti-drift no pide nada por ellos.
- `--text-on-solid` (`theme.css:89` = `#ffffff`) es **invariante a propósito** y está en el `INVARIANT` de `themeContrast.test.ts:105` ⇒ no se re-apunta en claro y eso es correcto. **No agregarlo al bloque claro.**
- `--accent` en claro es `#0969da` ⇒ 4.88:1 sobre `--bg-panel` claro. Pasa AA, con **0.38 de holgura**. Es el par más justo de la fase; si un plan futuro oscurece `--bg-panel` claro o aclara `--accent`, el gate de contraste de esta fase lo atrapa. Anotado como el margen más fino de F3.

**Tests PRIMERO.** Archivo: `frontend/src/__tests__/plan273NavCss.test.ts` (test puro: lee `App.module.css` y `theme.css` con `fs`, implementa la fórmula WCAG; sin DOM):

| Caso | Afirma |
|---|---|
| `la_regla_nav_tiene_mecanismo_de_recuperacion_ante_desborde` | (F2) el bloque `.nav` declara `overflow-x` o `flex-wrap` |
| `cero_rgba_de_blanco_en_las_reglas_de_la_nav` | `App.module.css` no contiene `rgba(255, 255, 255` |
| `cero_hex_en_App_module_css` | `App.module.css` no matchea `/#[0-9a-fA-F]{3,8}\b/`. Es el criterio más fuerte y hoy es satisfacible: los 4 hex del archivo (`#a5b4fc`, `#6366f1`, `#b91c1c`, `#ffffff`) se van todos |
| `el_texto_de_tab_cumple_AA_en_los_dos_temas` | Resolver el token de `color` de `.navTab` contra `--bg-panel` en `:root` y en `:root[data-theme="light"]`, y afirmar ratio ≥ 4.5 en **ambos** |
| `el_badge_no_usa_status_danger_solid` | La regla `.navBadge` **no** contiene `--status-danger-solid`. Tripwire contra la recomendación literal de la auditoría (§3.7b); sin él, un plan futuro "corrige" el token y baja el contraste a 3.76:1 sin que nada grite |
| `el_fondo_del_badge_cumple_AA_con_su_texto_en_los_dos_temas` | Ratio(`--text-on-solid`, `--nav-badge-bg`) ≥ 4.5 en ambos bloques |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273NavCss.test.ts
```

**Estado ROTO esperado (ANTES del fix):** **5 de 6 fallan** (el 6º, `el_badge_no_usa_status_danger_solid`, pasa desde el principio porque hoy el badge usa un literal; es un tripwire preventivo y hay que decirlo, no fingir que es un gate contra el defecto actual):
- `cero_rgba_de_blanco_en_las_reglas_de_la_nav` falla: hay 2 ocurrencias (`:24`, `:33`).
- `cero_hex_en_App_module_css` falla: hay 4 hex.
- `el_texto_de_tab_cumple_AA_en_los_dos_temas` falla en **ambos** temas: **1.03:1** en claro y **4.48:1** en oscuro. Este es el corazón del gate y tiene que verse rojo con esos dos números.
- `el_fondo_del_badge_cumple_AA_...` falla porque `--nav-badge-bg` no existe todavía.
- `la_regla_nav_...` falla (F2).

**Criterio de aceptación (binario):** los 6 casos verdes, y los tres gates de tema en el mismo estado que en F0:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273NavCss.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeContrast.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeLightTokens.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeTokens.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
```
Delta esperado en `uiDebtRatchet`: `App.module.css` pasa de 4 hex a 0. **No regenerar el baseline** — `assertNoIncrease` compara `count > allowed` (`:114`), y `0 > 4` es falso. Regenerar con `UI_DEBT_REGEN=1` está **prohibido** en este plan: arrastraría deuda ajena de otros archivos al baseline.

**Flag:** ninguna. Ver §3.6.

**Impacto por runtime:** ninguno / idéntico en los tres. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F4 — B-02: el error conserva el mensaje humano y el `correlation_id`, sin romper a los 7 que ya parsean el string

**Objetivo:** que `request()` lance un error que **preserve** `status`, `errorBody.message`, `errorBody.error`, `errorBody.detail` y `correlation_id`, y ofrecer un helper puro que produzca el texto que ve el operador. **Valor:** es la pieza de la que depende F5, y convierte cada error de red de una consulta de soporte en un próximo paso accionable con referencia correlacionable al log del servidor.

**Archivos a crear:**
- `frontend/src/api/gatewayError.ts`
- `frontend/src/api/__tests__/plan273GatewayError.test.ts`

**Archivos a editar:**
- `frontend/src/api/client.ts` — **solo** el cuerpo del `if (!res.ok)` dentro de `async function request<T>`.
- `frontend/src/components/PageErrorBoundary.tsx` — el render del mensaje.

**LA restricción de diseño de esta fase, y es la más importante del plan.** La auditoría dice que el cambio es *"retrocompatible si `message` sigue siendo legible"*. **Eso es falso tal como está escrito, y verificarlo cambia el diseño.** Hay **7 sitios de producción** que parsean el formato exacto `` `${status} ${statusText}: ${body}` ``:

| Archivo:línea (verificado 2026-07-30) | Qué parsea | De qué depende |
|---|---|---|
| `components/dbcompare/CompareWizard.tsx:30` | `err.message.startsWith("409")` | del **prefijo de status** |
| `components/devops/ProductionFlow.tsx:32` | `e.message.indexOf(': ')` + `JSON.parse` del resto | del **separador `": "`** y del **JSON crudo** |
| `components/devops/SectionDoctorButton.tsx:29` | `e.message.indexOf(': ')` | ídem |
| `components/devops/VariablesSection.tsx:34` | `e.message.indexOf(': ')` + `JSON.parse` del resto | ídem |
| `components/devops/VariablesSection.tsx:43` | `e.message.includes('variables_unavailable')` | del **cuerpo crudo dentro del message** |
| `components/ExecutionErrorAnalysisBlock.tsx:32` | `e.message.match(/^(\d{3})\s/)` | del **status al inicio** |
| `components/AgentLaunchModal.tsx:275` | `String(e).includes("503")` | del status en el string |

`ProductionFlow.tsx:28` incluso **documenta el formato como contrato**: *"un Error PLANO (`${status} ${statusText}: ${rawBody}`), sin `.kind`"*.

Si `message` pasara a ser el texto humano del backend, los 7 dejan de matchear y toman la rama equivocada — **en silencio**: sin error de tipos, sin test rojo, sin excepción. Es el peor modo de falla posible.

⇒ **Diseño obligatorio: estrictamente aditivo.** `GatewayError.message` conserva **byte a byte** el formato actual. Los campos ricos son **propiedades nuevas**. Nada de lo que existe se toca.

**`frontend/src/api/gatewayError.ts` — contrato exacto:**

```ts
import type { GatewayErrorBody } from "./client";

/**
 * Plan 273 F4 (B-02) — error de gateway que PRESERVA el cuerpo estructurado.
 *
 * CONTRATO CONGELADO: `message` mantiene BYTE A BYTE el formato historico
 * `${status} ${statusText}: ${rawText}`. NO es cosmetica: 7 sitios de produccion
 * lo parsean (CompareWizard, ProductionFlow, SectionDoctorButton,
 * VariablesSection x2, ExecutionErrorAnalysisBlock, AgentLaunchModal) y romperlo
 * los hace tomar la rama equivocada EN SILENCIO. Lo que se muestra al operador
 * sale de `userFacingMessage()`, NO de `.message`.
 */
export class GatewayError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly rawText: string;
  readonly errorBody: GatewayErrorBody | null;

  constructor(status: number, statusText: string, rawText: string) { ... }

  get correlationId(): string | undefined { ... }   // errorBody?.correlation_id
  get flag(): string | undefined { ... }            // errorBody?.detail?.flag  (lo consume F5)
}

export interface UserFacingError {
  title: string;
  detail?: string;
  correlationId?: string;
  flag?: string;          // habilita el deep-link a Configuracion -> Flags
  isTimeout: boolean;     // lo pone en true F6
}

export function userFacingMessage(e: unknown): UserFacingError { ... }
```

**Algoritmo de `userFacingMessage`, en orden de prioridad:**

0. **[v2, C14 — paso NUEVO y va PRIMERO]** `e` es un `Error` que **no** es `GatewayError` ni `TimeoutError`, y su `message` **no** matchea `/^\d{3}\s/` ⇒ `title = e.message` **tal cual**. Es un error de **programa**, no de red: un `TypeError` de render, un `RangeError`, un throw de una librería. Sin este paso, el algoritmo del v1 lo mandaba al paso 4 y lo mostraba como *"No se pudo conectar con el servidor."* — **una regresión activa**, porque el único archivo de UI que F4 edita (`PageErrorBoundary`) es precisamente el que recibe crashes de render, no errores de API (el plan mismo cita el crash vivo del 266 en `dbcompare/radarLogic.ts:60`). Hoy ese boundary muestra el `TypeError` real; con el v1 habría empezado a mentir. El saneamiento de `STACKY_*` y de JSON crudo **se aplica igual** a este camino.
1. `e` es `GatewayError` y `e.errorBody.message` es un string no vacío ⇒ `title = errorBody.message`. Es el camino feliz: la frase que el backend redactó.
2. `e` es `GatewayError` sin `message` utilizable ⇒ `title` = una frase por familia de status, **nunca** el status crudo:
   - `403`/`404` ⇒ `"Esta funcionalidad está desactivada."`
   - `409` ⇒ `"Ya hay una operación en curso."`
   - `>= 500` ⇒ `"El servidor tuvo un problema al procesar la solicitud."`
   - otro ⇒ `"No se pudo completar la operación."`
3. `e.isTimeout` (F6) ⇒ `title = "La operación tardó más de lo esperado."`, `isTimeout: true`.
4. `e` es `Error` común ⇒ `title = "No se pudo conectar con el servidor."` (fallo de red).
5. Cualquier otra cosa ⇒ `title = "Error inesperado."`

**Saneamiento obligatorio, aplicado SIEMPRE al `title` y al `detail` de salida.** Es lo que hace que el gate no se pueda burlar y lo que sostiene el criterio de C3:

- Si el candidato matchea `/^\d{3}\s/` ⇒ **descartar** y caer al paso siguiente.
- Si el candidato matchea `/^\s*[{[]/` (JSON crudo) ⇒ **descartar**.
- Si el candidato matchea `/STACKY_[A-Z_]+/` ⇒ **eliminar la ocurrencia** del texto de salida y, si el nombre de la flag se pudo extraer, ponerlo en el campo `flag`. Esto es la red de seguridad de F5: **`userFacingMessage` no filtra `STACKY_*` ni si F5 nunca se implementara.**

`correlationId` viaja siempre en su campo propio, nunca concatenado al `title`.

**Diff exacto en `client.ts`** (anclar por `async function request<T>`; el estado post-267 verificado tiene `reportOutcome(res)` justo antes, y ese orden **se conserva**):

```diff
    reportOutcome(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
-     throw new Error(`${res.status} ${res.statusText}: ${text}`);
+     // Plan 273 F4 (B-02): GatewayError conserva `message` BYTE A BYTE (7 sitios
+     // lo parsean) y agrega status/errorBody/correlation_id como campos.
+     throw new GatewayError(res.status, res.statusText, text);
    }
    return res.json() as Promise<T>;
```

**Alcance explícito de F4 — lo que NO toca:**
- **NO** cambia la firma ni el cuerpo de `rawGet`, `rawPost`, `rawPut`. Siguen devolviendo `{ status, ok, data, errorBody }` (frontera con el plan 263, §4).
- **NO** cambia `reportOutcome`, `isAbortError` ni `reportConnectionFailure` (frontera con el 267).
- **NO** toca los 7 parsers legacy. F4.5 los congela; migrarlos es trabajo futuro (B-09/B-10, fuera de scope).
- **NO** cambia ningún verbo de `api.*` (`get`/`post`/`put`/`patch`/`delete`/`postWithHeaders`/`postAbortable`). **Excepción declarada en v2 (C2), y vale solo para F6:** F6 agrega un parámetro **opcional al final** (`opts?: RequestOptions`) a `post`/`put`/`patch`/`delete` y ensancha el tipo del `init` de `get`. Es lo único que hace alcanzable el override de deadline (ver el bloque de corrección de C2 en F6). Aditivo y retrocompatible: ningún llamador existente cambia. `postWithHeaders`, `postAbortable` y los tres `raw*` siguen intactos.

**`PageErrorBoundary.tsx`** — una edición, anclada por la cadena literal `"Error inesperado"` (hoy en `:62`):

```diff
-  {this.state.error?.message || "Error inesperado"}
+  {/* Plan 273 F4 (B-02): el operador ve la frase del backend, no el string
+      aplanado `403 FORBIDDEN: {...}`. */}
+  {userFacingMessage(this.state.error).title}
```
Y, debajo del `<p className={styles.hint}>` existente, si `correlationId` está presente, un pie discreto `ref. {correlationId}`. **No agregar botones nuevos** en esta fase (el `[Ir a Flags]` es B-10, fuera de scope). **No tocar `PageErrorBoundary.tsx:40`** (`body: String(error?.message || error)` de `publishActivity`): ahí el string crudo es lo correcto, es rastro de diagnóstico, no texto para el operador.

> **Corrección v2 al alcance de esta edición (C1), y hay que leerla antes de creer que F4 cierra C3.** `PageErrorBoundary` es un boundary de errores de **render**: verificado en `PageErrorBoundary.tsx:26-30`, se activa por `getDerivedStateFromError` / `componentDidCatch`. Un rechazo de promesa de `api.*` disparado en un handler o en un efecto **nunca llega ahí** — lo captura el `try/catch` del propio componente. ⇒ **esta edición NO es la que hace legible el error de API.** Es correcta y se hace igual (cubre el caso de un throw en render), pero el camino real del operador se migra en **F4.6**, que el v1 no tenía. Sin F4.6, los smokes 5 y 6 fallan con el plan completo aplicado.

**Tests PRIMERO.** Archivo: `frontend/src/api/__tests__/plan273GatewayError.test.ts` (puro):

| Caso | Entrada | Afirma |
|---|---|---|
| `message_es_byte_identico_al_formato_historico` | `new GatewayError(403, "FORBIDDEN", '{"ok":false}')` | `.message === '403 FORBIDDEN: {"ok":false}'`. **El caso más importante del archivo** |
| `los_7_parsers_legacy_siguen_funcionando` | el mismo error | `.message.startsWith("403")` es `true`; `.message.indexOf(": ") >= 0`; `.message.match(/^(\d{3})\s/)?.[1] === "403"` |
| `preserva_status_y_errorBody` | 403 con `{"error":"feature_disabled","message":"X","correlation_id":"a3f9c1"}` | `.status === 403`, `.errorBody.message === "X"`, `.correlationId === "a3f9c1"` |
| `body_no_json_no_explota` | `new GatewayError(502, "BAD GATEWAY", "<html>502</html>")` | `.errorBody === null`, no lanza |
| `body_vacio_no_explota` | `(500, "INTERNAL SERVER ERROR", "")` | `.errorBody === null` |
| `ufm_prioriza_el_message_del_backend` | 403 con `message: "El Comparador de BD está desactivado."` | `title` es exactamente esa frase |
| `ufm_nunca_devuelve_status_crudo` | 500 sin cuerpo | `title` **no** matchea `/^\d{3} [A-Z ]+:/` |
| `ufm_nunca_devuelve_json_crudo` | 500 con `'{"ok":false,"trace":"..."}'` sin `message` | `title` **no** matchea `/^\s*[{[]/` |
| `ufm_nunca_filtra_STACKY` | 403 con `error: "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."` y **sin** `message` | `title` **no** matchea `/STACKY_[A-Z_]+/`, y `flag === "STACKY_DB_COMPARE_ENABLED"` |
| `ufm_extrae_la_flag_de_detail` | 403 con `detail: { flag: "STACKY_DOCS_GRAPH_ENABLED" }` | `flag` es ese valor |
| `ufm_403_de_flag_usa_message_no_error` | 403 con `error: "feature_disabled"` **y** `message: "El grafo está desactivado."` | `title` es el `message`, **no** `"feature_disabled"` |
| `ufm_error_de_red` | `new Error("Failed to fetch")` | `title === "No se pudo conectar con el servidor."`, `isTimeout === false` |
| **`ufm_un_typeerror_de_render_no_se_disfraza_de_error_de_red`** (v2, C14) | `new TypeError("Cannot read properties of undefined (reading 'summary')")` | `title` es **exactamente** ese mensaje. **NO** es `"No se pudo conectar con el servidor."`. Es el gate contra la regresión de C14, y el caso concreto es el crash vivo del 266 en `dbcompare/radarLogic.ts:60`. **Verificación de que discrimina:** con el algoritmo del v1 (sin el paso 0) este caso sale **rojo**; con el paso 0, verde |
| **`ufm_conserva_el_saneamiento_en_el_paso_0`** (v2, C14) | `new Error('Fallo raro con STACKY_DB_COMPARE_ENABLED adentro')` | `title` **no** matchea `/STACKY_[A-Z_]+/`. El paso 0 devuelve el `message` del programa, **pero saneado**: no es un bypass del saneamiento |
| `ufm_valor_no_error` | `"algo"`, `null`, `undefined`, `42` | devuelve `title` no vacío, no lanza |
| `ufm_correlation_id_no_va_en_el_title` | 500 con `correlation_id: "deadbeef"` | `title` **no** contiene `"deadbeef"`; `correlationId === "deadbeef"` |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/api/__tests__/plan273GatewayError.test.ts
```

**Estado ROTO esperado:** **los 16 casos fallan a la vez** (14 del v1 + los 2 de C14), todos con el mismo error de resolución de módulo: `Failed to resolve import "../gatewayError"`. Eso es correcto y esperado en una fase que crea un módulo nuevo — **pero no es un gate contra el defecto**, y hay que decirlo. El gate contra el defecto de F4 se demuestra distinto, y son **dos** pasos obligatorios:

> **Demostración 1 — el saneamiento.** Después de escribir `gatewayError.ts` y **antes** de tocar `client.ts`, implementar `userFacingMessage` *a propósito* con la versión ingenua `return { title: (e as Error).message, isTimeout: false }` y correr el archivo. Tienen que salir **rojos exactamente 4 casos**: `ufm_nunca_devuelve_status_crudo`, `ufm_nunca_devuelve_json_crudo`, `ufm_nunca_filtra_STACKY` y `ufm_correlation_id_no_va_en_el_title`. Si alguno pasa con la versión ingenua, ese caso no mide nada.
>
> **Demostración 2 (v2, C14) — la regresión del paso 0.** Implementar el algoritmo **sin el paso 0** (o sea, el algoritmo tal como lo definía el v1) y correr el archivo. Tiene que salir **rojo** `ufm_un_typeerror_de_render_no_se_disfraza_de_error_de_red`, con el mensaje mostrando que el `TypeError` se convirtió en `"No se pudo conectar con el servidor."`. Ese rojo es la prueba de que el paso 0 no es decorativo: sin él, F4 **empeora** el único archivo de UI que toca. Recién con los 5 rojos de las dos demostraciones vistos y leídos se escribe la versión real.

**Criterio de aceptación (binario):** los 16 casos verdes con el comando de arriba, **y** `npx tsc --noEmit` desde `Stacky Agents\frontend` sin errores nuevos respecto de la línea base **medida en F0** (C15: F0 ahora la mide; el v1 la exigía sin haberla medido).

**Flag:** ninguna. Ver §3.6 — el diseño es aditivo, no hay comportamiento viejo a preservar.

**Impacto por runtime:** ninguno / idéntico en los tres. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F4.5 — Congelar los 7 parsers legacy antes de que F5 y F6 los pongan en riesgo

**Objetivo:** un gate que falle si alguien cambia el formato de `GatewayError.message` o borra uno de los 7 parsers sin migrarlo. **Valor:** F4 depende de una invariante (el formato del `message`) que hoy solo vive en comentarios. Sin este gate, F5, F6 o cualquier plan futuro la rompe en silencio. Es la fase más corta y la que evita el peor daño.

**Archivos a crear:**
- `frontend/src/__tests__/plan273LegacyErrorParsers.test.ts`

**Archivos a editar:** ninguno de producción.

**Diseño:** un test puro que congela, **por archivo**, los 7 sitios y la invariante del formato:

```ts
/**
 * Plan 273 F4.5 — el formato de GatewayError.message es un CONTRATO con 7
 * consumidores. Este test los enumera. Si migras uno a userFacingMessage(),
 * BORRA su fila aca en el MISMO commit y bajá el conteo: es un ratchet que solo
 * baja. Si el conteo sube, alguien agrego un parser nuevo de string crudo en vez
 * de usar el contrato estructurado.
 */
const LEGACY_PARSERS: Array<[string, string]> = [
  ["components/dbcompare/CompareWizard.tsx",      'message.startsWith("409")'],
  ["components/devops/ProductionFlow.tsx",        "message.indexOf(': ')"],
  ["components/devops/SectionDoctorButton.tsx",   "message.indexOf(': ')"],
  ["components/devops/VariablesSection.tsx",      "message.indexOf(': ')"],
  ["components/devops/VariablesSection.tsx",      "message.includes('variables_unavailable')"],
  ["components/ExecutionErrorAnalysisBlock.tsx",  "message.match(/^(\\d{3})\\s/)"],
  ["components/AgentLaunchModal.tsx",             'String(e).includes("503")'],
];
```

| Caso | Afirma |
|---|---|
| `los_7_parsers_siguen_presentes_o_el_conteo_bajo` | Cada par `[archivo, fragmento]` cuyo archivo existe y contiene el fragmento cuenta 1. El total es `<= 7`. **Solo baja** |
| `el_formato_del_message_esta_congelado` | El fuente de `api/gatewayError.ts` contiene la plantilla literal `` `${status} ${statusText}: ${rawText}` `` (o su equivalente exacto en el constructor). Grep sobre el fuente |
| `request_lanza_GatewayError_no_Error_plano` | El fuente de `api/client.ts` contiene `throw new GatewayError(` y **no** contiene `` throw new Error(`${res.status} `` |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273LegacyErrorParsers.test.ts
```

**Estado ROTO esperado:** correr F4.5 **antes** de F4 (o con F4 a medias). `el_formato_del_message_esta_congelado` y `request_lanza_GatewayError_no_Error_plano` fallan (el módulo no existe / `client.ts` todavía lanza `Error` plano). `los_7_parsers_siguen_presentes...` pasa desde el principio: es un ratchet, no un gate contra un defecto, y hay que decirlo. **Prueba de que el ratchet discrimina, obligatoria:** cambiar temporalmente una fila de `LEGACY_PARSERS` por un fragmento inventado (p. ej. `"message.noExisteEsto"`) y verificar que el conteo baja y el mensaje del test nombra la fila; después revertir. Sin esa comprobación, el ratchet podría estar contando 0 de 7 con un regex mal escrito y pasando **en falso**.

**Criterio de aceptación (binario):** los 3 casos verdes tras F4.

**Flag:** ninguna. Es un test.

**Impacto por runtime:** ninguno — es un test de archivos, corre igual en los tres. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F4.6 — [FASE NUEVA v2, cierra C1] El error legible llega a la pantalla: migrar las 10 superficies gateadas

**Objetivo:** que en las superficies que F5 reescribe del lado backend, el operador vea la frase de `userFacingMessage()` y **no** el string aplanado. **Valor:** es la fase sin la cual **C3 no se cierra y los smokes 5 y 6 fallan con el plan entero aplicado**. El v1 asumía que editar `PageErrorBoundary` alcanzaba; no alcanza (ver la nota de F4).

**El defecto exacto, verificado.** El modismo de la casa para pintar un error de API es:

```
setError(err instanceof Error ? err.message : String(err));
```

`CompareWizard.tsx:94-99` lo hace y lo renderiza en `:108` (`{error && <div className={styles.errorBanner}>{error}</div>}`). Con la flag del Comparador apagada, `api.post` lanza y el banner muestra literalmente:

```
403 FORBIDDEN: {"ok":false,"error":"feature_disabled","message":"El Comparador de BD está desactivado.","detail":{"flag":"STACKY_DB_COMPARE_ENABLED"}}
```

Es decir: status crudo **+** JSON crudo **+** `feature_disabled` **+** `STACKY_DB_COMPARE_ENABLED`. **Las cuatro cosas que el smoke 5 prohíbe explícitamente.** Y nótese que F5 **empeora la legibilidad** de este string mientras no exista F4.6: el nombre de la flag sigue ahí, solo se mudó de `error` a `detail.flag`.

**Censo verificado el 2026-07-30.** El modismo `X instanceof Error ? X.message : String(X)` aparece **42 veces en 26 archivos** (cero en tests). Comando:

```powershell
cd "Stacky Agents\frontend\src"; (Get-ChildItem -Recurse -Include *.ts,*.tsx | Select-String -Pattern 'instanceof Error').Count
```
(la cuenta exacta del modismo completo requiere multilínea; el comando canónico del gate está en F4.7 y es el que manda)

**Alcance de F4.6: las 10 superficies cuyo backend reescribe F5.** Son 14 de las 42 ocurrencias. Lista literal, con el conteo por archivo medido hoy:

| Archivo (relativo a `frontend/src/`) | Ocurrencias |
|---|---|
| `components/dbcompare/CompareWizard.tsx` | 3 |
| `components/dbcompare/DataParitySection.tsx` | 2 |
| `components/dbcompare/SqlViewer.tsx` | 2 |
| `components/dbcompare/DemoSandboxPanel.tsx` | 1 |
| `components/dbcompare/ScriptsPanel.tsx` | 1 |
| `components/dbcompare/useCompareRun.ts` | 1 |
| `evolution/FitnessSection.tsx` | 1 |
| `evolution/KnowledgeSection.tsx` | 1 |
| `evolution/PlansSection.tsx` | 1 |
| `pages/EvolutionCenterPage.tsx` | 1 |
| **Total** | **14** |

**Los otros 16 archivos (28 ocurrencias) NO se tocan en esta fase.** No es descuido: son superficies cuyo backend F5 no reescribe (tickets, PM, devops, agentes, memoria), migrarlas es alcance de B-09/B-10, y tocarlas aumentaría la colisión con los 4 planes en vuelo de §4. Quedan **congeladas por el ratchet de F4.7**, que es lo que garantiza que nadie las empeore y que el resto se pague por concentración.

**Transformación exacta, sin excepciones.** En cada ocurrencia:

```diff
- setError(err instanceof Error ? err.message : String(err));
+ // Plan 273 F4.6 (C1): el operador lee la frase del backend, no el aplanado.
+ setError(userFacingMessage(err).title);
```

Reglas:
1. **Import:** `import { userFacingMessage } from "../../api/gatewayError";` con la profundidad relativa que corresponda al archivo. No usar alias de path (el repo no los tiene configurados).
2. **Si el sitio ya tiene una rama especial, se conserva.** `CompareWizard.tsx:94-99` tiene `isBusyError(err)` (que parsea `message.startsWith("409")`, uno de los 7 de F4.5): la rama del 409 **queda intacta**, solo cambia el `else`. Es decir: `isBusyError(err) ? "Ya hay una comparación…" : userFacingMessage(err).title`. **No borrar ningún parser de F4.5 en esta fase** — si se borra alguno, hay que bajar su fila en `LEGACY_PARSERS` en el MISMO commit (regla de F4.5).
3. **Si el `correlationId` está presente, se muestra** como pie discreto `ref. <id>` donde el componente ya pinta el error. Si el componente no tiene lugar para un pie, se omite: **prohibido** concatenarlo al título.
4. **No cambiar el tipo del estado** (`string | null` sigue siendo `string | null`). No hay refactor de forma en esta fase.

**Tests PRIMERO.** Archivo: `frontend/src/__tests__/plan273ErrorSurface.test.ts` (nombre reservado, verificado libre; test puro de archivos + de función, sin DOM):

| Caso | Afirma |
|---|---|
| `las_10_superficies_gateadas_usan_userFacingMessage` | Cada uno de los 10 archivos de la tabla contiene `userFacingMessage(` |
| `las_10_superficies_gateadas_no_aplanan` | Ninguno de los 10 contiene el modismo `instanceof Error ? ….message : String(` (regex multilínea sobre el fuente). **Este es el gate contra el defecto** |
| `el_banner_del_comparador_no_puede_mostrar_STACKY` | Alimentar `userFacingMessage` con el cuerpo REAL que el backend devolverá tras F5 (`{"ok":false,"error":"feature_disabled","message":"El Comparador de BD está desactivado.","detail":{"flag":"STACKY_DB_COMPARE_ENABLED"}}`, status 403) y afirmar: `title` es exactamente la frase, **no** matchea `/STACKY_[A-Z_]+/`, **no** matchea `/^\d{3}/`, **no** contiene `feature_disabled`, y `flag === "STACKY_DB_COMPARE_ENABLED"` |
| `la_rama_del_409_del_comparador_sobrevive` | `CompareWizard.tsx` sigue conteniendo `isBusyError` y `message.startsWith("409")` (no se rompió un parser de F4.5 al migrar) |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273ErrorSurface.test.ts
```

**Estado ROTO esperado (ANTES del fix):** `las_10_superficies_gateadas_usan_userFacingMessage` falla **nombrando los 10** archivos; `las_10_superficies_gateadas_no_aplanan` falla **enumerando las 14 ocurrencias con `archivo:línea`** (si enumera menos de 14, el regex multilínea está mal y hay que arreglarlo antes de seguir); `la_rama_del_409…` pasa desde el principio (es un tripwire, y hay que decirlo). `el_banner_del_comparador…` falla por módulo inexistente si se corre antes de F4. Total: **2 de 4 rojos contra el código actual**, y son los que importan.

**Criterio de aceptación (binario):** los 4 casos verdes, `npx vitest run src/__tests__/plan273LegacyErrorParsers.test.ts` verde (F4.6 no rompió el contrato ni borró un parser sin bajar el conteo), y `npx tsc --noEmit` sin errores nuevos respecto de F0.

**Depende de F4** (necesita `userFacingMessage`). **Va antes de F5**, no después: así el implementador ve el string crudo en pantalla, lo migra, y recién entonces F5 cambia el cuerpo del backend. Al revés, F5 dejaría una ventana en la que el operador ve `feature_disabled` en pantalla (es exactamente el riesgo R8 del v1, ahora cerrado por orden de fases y no solo por un barrido).

**Flag:** ninguna. Es una corrección de defecto: el lado OFF sería "seguir mostrando JSON crudo".

**Impacto por runtime:** ninguno / idéntico en los tres. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F4.7 — [ADICIÓN ARQUITECTO] Ratchet de superficie de error cruda: el aplanado no vuelve nunca

**Objetivo:** congelar en **28** las ocurrencias restantes del modismo que aplana la excepción, con semántica de ratchet que **solo baja**, y hacer que cualquier plan futuro que agregue un aplanado nuevo se ponga rojo. **Valor:** convierte el arreglo puntual de F4.6 en una propiedad permanente del repo. Sin esto, F4.6 es una limpieza que el próximo plan deshace sin que nada grite — y esa es la historia repetida de este repo (`--status-danger-solid`, `nextEnabledState`, el conteo de `PAIRS`). Es la pieza de mayor vida útil de todo el plan y **no cuesta una sola línea de producción**.

**Por qué es una adición y no scope creep:** no toca producción, no agrega flag, no agrega trabajo al operador, corre igual en los tres runtimes, reusa el patrón de ratchet que el repo ya tiene en tres lugares (`uiDebtRatchet.test.ts`, `test_plan259_ratchet_script_parity.py`, `LEGACY_PARSERS` de F4.5) en vez de inventar mecanismo, y su criterio es delta puro.

**Archivos a crear:**
- `frontend/src/__tests__/plan273RawErrorSurfaceRatchet.test.ts`

**Archivos a editar:** ninguno de producción.

**Diseño:**

```ts
/**
 * Plan 273 F4.7 — RATCHET. El modismo `X instanceof Error ? X.message : String(X)`
 * pinta al operador el string aplanado de client.ts (`403 FORBIDDEN: {...}`).
 * Medido el 2026-07-30: 42 ocurrencias en 26 archivos. F4.6 migra 14 (las 10
 * superficies con gate de flag) => techo 28.
 * ESTE NUMERO SOLO BAJA. Si migras mas sitios a userFacingMessage(), BAJA el techo
 * en el MISMO commit. Si sube, alguien agrego un aplanado nuevo en vez de usar
 * userFacingMessage(): no subas el techo, migra el sitio.
 */
const MAX_RAW_ERROR_SITES = 28;
const RAW_IDIOM = /[A-Za-z_$]+\s+instanceof\s+Error\s*\?\s*[A-Za-z_$]+\.message\s*:\s*String\(/g;
```

| Caso | Afirma |
|---|---|
| `el_censo_no_es_vacio` | El barrido encuentra **>= 20** ocurrencias. **Obligatorio:** un regex que deja de matchear daría 0 y los otros casos pasarían **en falso**. Es el mismo modo de falla que `test_plan259_ratchet_script_parity.py` tapa con `test_las_dos_listas_son_no_vacias` |
| `la_superficie_cruda_no_crece` | `total <= MAX_RAW_ERROR_SITES`, con mensaje que **enumera `archivo:línea` de cada ocurrencia**, no solo el número |
| `las_10_superficies_gateadas_no_estan_en_el_censo` | Ninguna ocurrencia cae en los 10 archivos de F4.6. Prueba que F4.6 de verdad las migró y que el ratchet no está contando fantasmas |
| `el_barrido_recorre_todo_src` | El barrido cubre `src/**/*.ts` + `src/**/*.tsx` excluyendo `__tests__` y `*.test.*`, y el conteo de archivos escaneados es **> 300**. Gate anti-glob-roto: un glob que no matchea nada daría 0 archivos y 0 ocurrencias |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273RawErrorSurfaceRatchet.test.ts
```

**Estado ROTO esperado, y es una demostración obligatoria de que el ratchet discrimina.** Correr este archivo **antes** de F4.6, con `MAX_RAW_ERROR_SITES = 28`: `la_superficie_cruda_no_crece` tiene que fallar con **42 > 28** y enumerar las 42. Ese rojo es la prueba de que el barrido ve los sitios reales. Después de F4.6 baja a 28 y pasa. **Segunda demostración:** agregar temporalmente un `setX(e instanceof Error ? e.message : String(e))` en cualquier `.tsx` de producción, verificar que el test pasa a **29 > 28** y nombra el archivo nuevo, y revertir. Sin las dos comprobaciones el ratchet podría estar contando 0 con un regex mal escrito.

**Criterio de aceptación (binario):** los 4 casos verdes tras F4.6, y el rojo pre-F4.6 anotado con el número **42**.

**Flag:** ninguna. Es un test.

**Impacto por runtime:** ninguno — test de archivos. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F5 — B-06: ningún `message` de error nombra una variable de entorno

**Objetivo:** que las 24 cadenas de error de "funcionalidad desactivada" dejen de nombrar la variable `STACKY_*` en el texto que ve el operador, y que el nombre de la flag viva en `detail.flag`, donde sirve para el deep-link. **Valor:** el riel del producto es que las flags se configuran por UI; decirle al operador el nombre de la variable de entorno es simultáneamente intimidante e inútil, porque no es el camino que debe tomar.

**Depende de F4 y de F4.6** (v2). El v1 decía "depende de F4"; eso era incompleto y es la raíz de C1: sin **F4.6**, mover el texto del backend no cambia nada de lo que se ve, porque el consumidor pinta el string aplanado completo. Correr F5 **antes** de F4.6 abre una ventana en la que el operador lee `feature_disabled` en pantalla (el riesgo R8). El orden **F4 → F4.6 → F4.7 → F5** es obligatorio.

**Verificación de frontera hecha en la crítica v2 (buena noticia):** las 24 ocurrencias / 13 archivos son **idénticas en los 8 worktrees vivos** (`wt-plan-260`, `262`, `263`, `264`, `265`, `266`, `271`, `wt-main-consolidation`). Ningún plan en vuelo agrega cadenas nuevas de este tipo, así que el gate de F5 no se va a poner rojo por deuda ajena al mergear. Si un plan futuro agrega una, el gate lo atrapa — que es lo que se quiere.

**Archivos a editar — los 13 verificados hoy** (§3.7a; la lista de ejemplos de la auditoría omite los dos últimos):

```
backend/api/db_compare.py            backend/api/evolution.py
backend/api/db_compare_demo.py       backend/api/evolution_fitness.py
backend/api/db_compare_masking.py    backend/api/evolution_knowledge.py
backend/api/db_compare_repo.py       backend/api/evolution_optimizer.py
backend/api/db_compare_watch.py      backend/api/migrator.py
backend/api/diag.py                  backend/api/plans_board.py
backend/api/docs.py
```

**Archivos a crear:**
- `backend/tests/test_plan273_error_message_sin_flags.py`

**Archivos a editar (registro del test, los DOS obligatorios — §3.4):**
- `backend/scripts/run_harness_tests.sh` — agregar `  tests/test_plan273_error_message_sin_flags.py` al array `HARNESS_TEST_FILES`, **ruta pelada, una por línea**.
- `backend/scripts/run_harness_tests.ps1` — agregar `  "tests/test_plan273_error_message_sin_flags.py",` al array `$HarnessTestFiles`, **entrecomillada y con coma**.

> **Por qué los dos, y por qué esto no es opcional.** `test_harness_ratchet_meta.py:43-53` exige que todo `tests/test_*.py` esté en `HARNESS_TEST_FILES` del `.sh` **o** en `tests/harness_ratchet_allowlist.txt`. Y `test_plan259_ratchet_script_parity.py:46` fija `_PS1_LAG_MAX = 64` con el lag medido hoy en **exactamente 64: holgura CERO**. Registrar solo en el `.sh` sube el lag a 65 y pone **rojo** el gate de paridad. Registrar solo en el `.ps1` deja rojo el meta-test. **Las dos ediciones o ninguna.** Y ojo con la sintaxis: en el `.ps1` una ruta sin comillas parsea sin error (PowerShell la lee como nombre de comando) y se pierde **muda** — es el modo de falla que ese test existe para tapar.

**Desglose real de las 24, verificado el 2026-07-30 (C9).** No son 24 casos de la misma forma: **14** nombran la flag en la clave `error` y **10** en la clave `message`. Las dos formas necesitan una reescritura distinta, y el v1 mostraba un solo diff que además **inventaba** la forma del ejemplo que citaba (`docs.py:222` es clave `message` con status **404**, no clave `error` con 403). Las dos formas canónicas:

**Forma A — la flag está en `error` (14 casos: los 5 de `db_compare.py`, los 2 de `db_compare_demo.py`, los 2 de `db_compare_masking.py`, los 2 de `db_compare_repo.py`, los 2 de `db_compare_watch.py`, y `migrator.py:101`):**

```diff
- return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
+ return jsonify({
+     "ok": False,
+     "error": "feature_disabled",
+     "message": "El Comparador de BD está desactivado.",
+     "detail": {"flag": "STACKY_DB_COMPARE_ENABLED"},
+ }), 403
```

**Forma B — la flag ya está en `message` y `error` no existe (10 casos: `diag.py:1018`, `diag.py:1058`, `docs.py:222`, `evolution.py:32`, `evolution.py:179`, `evolution.py:242`, `evolution_fitness.py:23`, `evolution_knowledge.py:29`, `evolution_optimizer.py:35`, `plans_board.py:25`):**

```diff
- return jsonify({"ok": False,
-                 "message": "El grafo documental está deshabilitado (STACKY_DOCS_GRAPH_ENABLED)."}), 404
+ return jsonify({
+     "ok": False,
+     "error": "feature_disabled",
+     "message": "El grafo de documentación está desactivado.",
+     "detail": {"flag": "STACKY_DOCS_GRAPH_ENABLED"},
+ }), 404
```

En la forma B se **agrega** la clave `error` (antes no estaba) y **el status no se toca**: `docs.py:222` sigue siendo 404 aunque semánticamente sea lo mismo que un 403 de otro archivo. Unificarlos es B-09 (regla 4 abajo).

**Reglas de la reescritura, sin excepciones:**
1. `message` = frase para el operador. **Sin** nombre de variable, **sin** paréntesis técnico, **sin** jerga de implementación. La auditoría nombra la jerga a traducir: *"arnés de fitness"*, *"flywheel de conocimiento"*, *"ciclo MAPE"*, *"Puente al repo"*, *"Gates de precondición"*, *"Triage del diff"*, *"Masking"*. Traducir al dominio del operador (ej.: *"Masking"* ⇒ *"El enmascarado de datos sensibles está desactivado."*).
2. `error` = clave machine-readable estable. Para todos los gates de flag de esta fase: `"feature_disabled"`.
3. `detail.flag` = el nombre `STACKY_*` **exacto**, que es lo que habilita el deep-link a Configuración → Flags.
4. **No cambiar ningún status HTTP.** Unificarlos es B-09, P1, fuera de scope (§7). Si un endpoint hoy responde 404 y otro 403 para lo mismo, **así queda**.
5. **La clave `ok`: si el cuerpo ya la tiene, se conserva en `False`; si NO la tiene, no se agrega (C17).** El v1 decía *"no cambiar la clave `ok`, sigue siendo `False`"* como si todos la tuvieran, y **`migrator.py:101` no la tiene**: es `return jsonify({"error": "Migrador no habilitado (…)"}), 503`, sin `ok`. Dejarlo ambiguo hacía que un modelo menor decidiera al azar y pudiera romper consumidores del 503. Regla binaria: **no se agrega `ok` donde no está, y no se saca donde está.**
6. **`migrator.py:101` es un caso aparte por TRES razones**, y las tres se respetan a la vez: (a) su texto es `"Migrador no habilitado (STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false)"` — con `=false` pegado; el regex del test lo atrapa igual (`STACKY_[A-Z_]+`), pero al reescribirlo hay que quitar **también** el `=false`; (b) **no tiene clave `ok`** ⇒ no se le agrega (regla 5); (c) responde **503**, no 403/404 ⇒ el status **no se toca** (regla 4).

**Casos borde:**
- Un archivo con **cinco** ocurrencias (`db_compare.py`: `:38`, `:47`, `:57`, `:478`, `:703`). Reescribir las cinco; el gate cuenta sobre el archivo entero.
- Consumidores frontend que hoy leen `errorBody.error` esperando la **frase** en vez de la clave. Después de reescribir, `error` pasa a valer `"feature_disabled"`. **Verificación obligatoria antes de dar F5 por cerrada:**
  ```
  cd "Stacky Agents\frontend"; Select-String -Path src\**\*.ts,src\**\*.tsx -Pattern "errorBody\?\.error|errorBody\.error"
  ```
  Cada resultado se lee y se decide: si mostraba `errorBody.error` como texto al operador, pasa a `errorBody.message` (que es lo que F4 ya sabe priorizar vía `userFacingMessage`). Si lo comparaba contra una clave, ya funciona. **No** hacer este barrido convierte F5 en una regresión visible: el operador vería `"feature_disabled"` en pantalla.
- `VariablesSection.tsx:39` compara `parsed?.kind === 'variables_unavailable'` — usa la clave `kind`, no `error`, y **no** es un gate de flag `STACKY_*` ⇒ fuera del alcance de F5, protegido por F4.5.

**Tests PRIMERO.** Archivo: `backend/tests/test_plan273_error_message_sin_flags.py`.

**Decisión de diseño del gate, y es deliberada:** el gate se corre **sobre el fuente** de `backend/api/*.py`, no levantando la app y recorriendo endpoints. Razón: recorrer endpoints requiere `create_app()`, que fuera de pytest tiene efectos reales (arranca daemons, escribe en la DB viva) y en pytest necesita 24 combinaciones de flags apagadas — costoso, frágil y con contaminación conocida. Sobre el fuente el gate es determinista, corre en los tres runtimes y en Windows y fuera. **Costo declarado:** no detectaría un `message` construido dinámicamente con el nombre de la flag por f-string. Se cubre con un caso extra que prohíbe ese patrón.

| Caso | Afirma |
|---|---|
| `ningun_message_nombra_una_flag` | Recorrer `backend/api/*.py` con `"message":\s*"[^"]*STACKY_[A-Z_]+` ⇒ **0** coincidencias |
| `ningun_error_nombra_una_flag` | Ídem con `"error":\s*"[^"]*STACKY_[A-Z_]+` ⇒ **0** coincidencias |
| `ningun_message_se_arma_por_fstring_con_la_flag` | Ningún `"message"` en `backend/api/*.py` está en una línea con un f-string que contenga `STACKY_`. Tapa el hueco declarado del gate |
| `los_13_archivos_declaran_detail_flag` | Cada uno de los 13 archivos de la lista contiene al menos un `"detail"` con `"flag"`. Prueba que el nombre de la flag **no se perdió**: se movió |
| `el_conteo_de_detail_flag_cubre_las_24` | La suma de ocurrencias de `"flag":\s*"STACKY_` en los 13 archivos es **>= 24**. Prueba que se migraron **todas**, no algunas |

**Sobre el criterio de conteo, explícito:** el caso 1 se escribe afirmando sobre la **lista de coincidencias con `archivo:línea`**, no `assert count == 0`. Un `assert lista == []` con la lista formateada nombra las 24 que faltan; un `assert count == 0` colapsa 24 en "1 != 0" y el implementador arregla una, corre, sigue rojo, y no sabe cuántas quedan. El mensaje del assert **tiene que enumerar** `archivo:línea: <fragmento>`.

Comando exacto:
```
cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_plan273_error_message_sin_flags.py -q
```

**Estado ROTO esperado (ANTES del fix):** `ningun_message_nombra_una_flag` + `ningun_error_nombra_una_flag` fallan sumando **24 coincidencias enumeradas** en **13 archivos**; `los_13_archivos_declaran_detail_flag` falla nombrando los 13; `el_conteo_de_detail_flag_cubre_las_24` falla con `0 >= 24`. Total: **4 de 5 rojos**, y el mensaje del primero tiene que listar las 24 líneas. Si lista menos de 24, el regex del test difiere del de la auditoría y hay que reconciliarlo antes de seguir.

**Criterio de aceptación (binario):**
```
cd "Stacky Agents\backend"; & "...\venv\Scripts\python.exe" -m pytest tests/test_plan273_error_message_sin_flags.py -q
cd "Stacky Agents\backend"; & "...\venv\Scripts\python.exe" -m pytest tests/test_harness_ratchet_meta.py -q
cd "Stacky Agents\backend"; & "...\venv\Scripts\python.exe" -m pytest tests/test_plan259_ratchet_script_parity.py -q
```
Los 5 casos verdes; los dos gates de ratchet en el **mismo** estado que F0 (lag sigue en 64: subió 1 en cada script). Y el barrido de `errorBody.error` del "caso borde" hecho y anotado.

**Flag:** ninguna. Ver §3.6.

**Impacto por runtime:** **ninguno / idéntico en los tres.** Es el cuerpo JSON de respuestas HTTP de Flask; no hay una sola rama por runtime de agente. **Fallback:** no aplica — no se agrega ninguna capacidad que un runtime pudiera no tener. (Honestidad sobre el riel de paridad: en este plan la paridad de runtimes es trivial porque los siete P0 son frontend y contrato HTTP. Fabricar diferencias por runtime sería inventar.)

**Trabajo del operador: ninguno.**

---

### F6 — B-04: ningún request queda esperando para siempre

**Objetivo:** un deadline por defecto en `request()`, con override por llamador para las operaciones legítimamente largas, y un error distinguible como timeout. **Valor:** con el backend vivo pero trabado (lock de SQLite, daemon colgado, red caída sin RST) la pantalla hoy queda cargando para siempre; no hay error, no hay reintento, y la única salida es F5 — que hasta F7 dispara el rebote de H-01.

**Archivos a editar:**
- `frontend/src/api/client.ts` — cuerpo de `async function request<T>` y el tipo del `init`.
- `frontend/src/api/gatewayError.ts` — agregar `TimeoutError` y que `userFacingMessage` la reconozca.

**Archivos a crear:**
- `frontend/src/api/__tests__/plan273RequestTimeout.test.ts`

> **CORRECCIÓN BLOQUEANTE v2 (C2). Leer esto antes de escribir una línea.** El v1 decía que la varianza se cubre "con el override por llamador (`timeoutMs`)". **Ese override no existía y no era construible bajo las propias reglas del v1.** Verificado en `client.ts:213-235`: de los siete verbos de `api`, **solo `api.get` acepta un `init`**; `post`, `put`, `patch` y `delete` construyen el `RequestInit` **adentro** y no reciben nada del llamador; `postWithHeaders` recibe headers; `postAbortable` recibe un `AbortSignal`. Y el "Alcance explícito" de F4 prohibía cambiar cualquier verbo de `api.*`. ⇒ el v1, tal como estaba, imponía un deadline de 20 s **duro y sin escape** a todos los POST, que es justo donde viven las operaciones largas. Además `request()` **no está exportado**, así que el test de esta fase no tenía por dónde inyectar el `fetchImpl` que él mismo exige.
>
> **Las tres consecuencias son obligatorias en v2:** (1) los cuatro verbos reciben un parámetro de opciones **estrictamente aditivo**; (2) los endpoints largos se **enumeran** con `timeoutMs: 0` y un gate lo verifica; (3) `request` se exporta para test. La prohibición de F4 se **relaja explícitamente y solo para esto**: agregar un parámetro opcional al final de una firma es retrocompatible byte a byte para los ~cientos de llamadores existentes, y **no** toca `rawGet`/`rawPost`/`rawPut`, que es donde vive la frontera real con el plan 263.

**Diseño exacto:**

```ts
/** Plan 273 F6 (B-04) — deadline por defecto. NO es una flag: leerla del backend
 *  requeriria la misma llamada HTTP que el deadline protege (dependencia circular:
 *  si el backend cuelga, la lectura de la flag cuelga y no hay timeout). La
 *  varianza real se cubre con el override por llamador, abajo. */
export const DEFAULT_TIMEOUT_MS = 20000;

/** 0 = SIN LIMITE. Convencion ya usada en el repo para deadlines. */
export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
  /** Solo para tests. Se copia el PATRON de ProbeOptions (inyeccion por opcion,
   *  sin estado global, flagHealth.ts:25-32), NO su firma: la de `probeFlagHealth`
   *  es `(path) => Promise<{ json() }>` y NO expone ok/status/statusText/text(),
   *  que es justo lo que request() usa en :205-210. Tipo correcto (C16): */
  fetchImpl?: (input: string, init?: RequestInit) => Promise<Response>;
}
```

**Cambio de firmas — aditivo, un parámetro opcional al final de cada uno (C2):**

```diff
- get: <T,>(path: string, init?: RequestInit) => request<T>(path, init),
+ get: <T,>(path: string, init?: RequestOptions) => request<T>(path, init),
- post: <T,>(path: string, body?: unknown) =>
-   request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
+ // Plan 273 F6 (C2): `opts` al FINAL y opcional => los llamadores existentes
+ // compilan y se comportan igual. Es el unico canal para `timeoutMs: 0`.
+ post: <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
+   request<T>(path, { ...opts, method: "POST", body: body ? JSON.stringify(body) : undefined }),
```
Ídem `put`, `patch`, `delete`. **`postWithHeaders` y `postAbortable` NO se tocan** (siguen sin override; si alguna vez lo necesitan es otro plan). Y:

```diff
- async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
+ /** Exportada SOLO para los tests de F6 (no hay forma de inyectar fetch de otro
+  *  modo). Los consumidores de produccion siguen usando `api.*`. */
+ export async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
```

**Los 10 endpoints que van con `timeoutMs: 0`, enumerados (C2).** Sin esta tabla la fase es una regresión: son operaciones de minutos que a los 20 s mostrarían "la operación tardó más de lo esperado" mientras el backend sigue trabajando, y el operador reintentaría **duplicando** el disparo. Todas verificadas hoy en `frontend/src/api/endpoints.ts`:

| Endpoint | Ancla (contexto) | Por qué |
|---|---|---|
| `POST /api/tickets/sync` | `:237` | Sincronización completa contra ADO/GitLab |
| `POST /api/agents/run` | `:1153` y `:1229` (**dos** sitios) | Ejecución de agente |
| `POST /api/packs/start` | `:1495` | Arranque de pack multi-paso |
| `POST /api/executions/{id}/publish-to-ado` | `:1411` | Publicación en el sistema real del operador |
| `POST /api/config/import` | `:2199` y `:2206` | Importación de bundle de configuración |
| `POST /api/drift/run` | `:1834` | Barrido de drift |
| `POST /api/glossary/scan` | `:1856` | Escaneo de glosario |
| `POST /api/qa-uat/run` | `:2649` | Corrida QA/UAT |
| `POST /api/qa-browser/runs` | `:2839` | Corrida de navegador |
| `POST /api/diag/backup/run` | `:2884` | Backup |

**Regla de cierre de la tabla, obligatoria:** además de los 10, antes de cerrar F6 hay que barrer `endpoints.ts` con el criterio *"¿esta operación puede tardar más de 20 s en el equipo del operador?"* y agregar `timeoutMs: 0` a lo que aparezca, anotándolo en la bitácora. **Ante la duda, `timeoutMs: 0`**: un deadline de más es una regresión visible; uno de menos es el comportamiento de hoy. Comando de barrido:

```powershell
cd "Stacky Agents\frontend"; Select-String -Path src\api\endpoints.ts -Pattern 'api\.(post|put)<' | Select-String -Pattern 'run|sync|start|publish|import|scan|build|graph|compare|migrat|backup|seed|reindex|generate'
```

Dentro de `request()`, envolviendo el `fetch` **sin tocar** `reportOutcome` / `isAbortError` / `reportConnectionFailure` (frontera 267):

```
timeoutMs = init.timeoutMs ?? DEFAULT_TIMEOUT_MS
si timeoutMs > 0:
    ctl = new AbortController()
    timer = setTimeout(() => { timedOut = true; ctl.abort() }, timeoutMs)
    signal = combinar(init.signal, ctl.signal)     # el signal del llamador SIGUE valiendo
finally:
    clearTimeout(timer)                            # SIEMPRE, en exito y en error

en el catch del fetch:
    si timedOut: throw new TimeoutError(path, timeoutMs)
    si no: comportamiento ACTUAL intacto (isAbortError -> no reportar; else reportConnectionFailure; rethrow)
```

**Casos borde, todos con caso de test:**
- **`timeoutMs: 0` ⇒ sin límite.** Es la vía para ejecuciones de agente y publicaciones. No se instala timer.
- **`postAbortable` sigue funcionando.** Hoy pasa el `signal` del llamador (`client.ts:233-234`). El timeout **combina** los dos signals: si el operador cancela, `isAbortError` es true y `timedOut` es false ⇒ se propaga el abort de siempre, **no** un `TimeoutError`. Confundir "el operador canceló" con "el servidor no respondió" sería una regresión de UX peor que el bug original.
- **Cancelación del usuario vs timeout.** Distinguidos por el flag `timedOut`, no por inspeccionar el `AbortError` (los dos producen el mismo `DOMException`).
- **`clearTimeout` en el camino feliz.** Sin él, cada request deja un timer vivo hasta 20s; con navegación intensa se acumulan. El `finally` es obligatorio.
- **`AbortSignal.any` puede no existir** en el runtime del navegador objetivo. Implementar la combinación a mano (un `AbortController` propio que escuche `abort` en los dos) en vez de depender de `AbortSignal.any`.
- **`rawGet`/`rawPost`/`rawPut` NO se tocan** (frontera con el plan 263). Queda declarado como **gap conocido de F6**: los tres `raw*` siguen sin deadline. La auditoría misma lo marca como opcional (*"y opcionalmente `:47-89`, `:96-136`, `:144-186`"`). Extenderlo es trabajo futuro; meterlo acá colisiona con el 263 sin necesidad.

**Tests PRIMERO.** Archivo: `frontend/src/api/__tests__/plan273RequestTimeout.test.ts`. Test **puro** con `fetchImpl` inyectado vía `RequestOptions.fetchImpl` e importando la `request` **exportada** (ver el diff de firmas arriba): sin estado global, sin dependencia del orden de tests. `probeFlagHealth` ya usa este **patrón** (inyección por opción, `ProbeOptions.fetchImpl` / `sleepImpl`, `flagHealth.ts:25-32`, verificado) — **copiar el patrón, NO la firma (C16):** la de `probeFlagHealth` es `(path: string) => Promise<{ json(): Promise<unknown> }>` y no expone `ok`/`status`/`statusText`/`text()`, que es exactamente lo que `request()` usa en `:205-210`; copiada al pie, no compila. El tipo correcto está en `RequestOptions`, arriba.

| Caso | Entrada | Afirma |
|---|---|---|
| `un_fetch_que_nunca_resuelve_rechaza_por_timeout` | `fetchImpl` que devuelve `new Promise(() => {})`, `timeoutMs: 50` | la promesa **rechaza** con `TimeoutError` en < 500 ms reales |
| `timeout_cero_no_instala_deadline` | mismo fetch, `timeoutMs: 0` | no rechaza dentro de una ventana de 100 ms (se verifica con `Promise.race` contra un sleep) |
| `un_fetch_rapido_no_es_afectado` | `fetchImpl` que resuelve 200 + JSON, `timeoutMs: 50` | resuelve con el JSON; **no** lanza |
| `el_abort_del_llamador_no_se_confunde_con_timeout` | `signal` de un `AbortController` que se aborta a los 10 ms, `timeoutMs: 5000` | rechaza con `AbortError`, **no** con `TimeoutError` |
| `el_timeout_no_se_confunde_con_abort_del_llamador` | `signal` que nunca se aborta, `timeoutMs: 20` | rechaza con `TimeoutError` |
| `ufm_de_un_timeout_es_accionable` | `userFacingMessage(new TimeoutError(...))` | `isTimeout === true`; `title` contiene `"tardó"`; **no** matchea `/^\d{3}/` |
| `el_default_es_20000` | — | `DEFAULT_TIMEOUT_MS === 20000` |
| `se_limpia_el_timer_en_el_camino_feliz` | `fetchImpl` que resuelve, con `setTimeout`/`clearTimeout` espiados por contadores locales | `clearTimeout` se llamó exactamente una vez |
| **`los_verbos_aceptan_opts`** (v2, C2) | — | Grep sobre el fuente de `api/client.ts`: `post`, `put`, `patch` y `delete` declaran `opts?: RequestOptions`. **Gate contra el defecto de C2**: sin esto el override no existe y el deadline es inescapable |
| **`los_10_endpoints_largos_declaran_timeout_cero`** (v2, C2) | — | Grep sobre `api/endpoints.ts`: para cada una de las 10 rutas de la tabla, la llamada correspondiente contiene `timeoutMs: 0`. El mensaje del assert **enumera las que faltan**, una por línea. **Es el gate que impide shippear la regresión** |
| **`el_conteo_de_timeout_cero_no_baja`** (v2) | — | Las ocurrencias de `timeoutMs: 0` en `endpoints.ts` son **>= 11** (10 rutas, y `/api/agents/run` y `/api/config/import` aparecen dos veces cada una ⇒ 12 sitios; el umbral se fija en la bitácora con el número real medido al implementar). Ratchet: si alguien borra un `timeoutMs: 0`, se pone rojo |

**Nota de implementación de los tests, obligatoria:** usar `timeoutMs` chicos (20–50 ms) y esperas reales cortas. **No** usar fake timers de vitest: interactúan mal con `await` sobre promesas que nunca resuelven y producen tests que cuelgan la corrida.

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/api/__tests__/plan273RequestTimeout.test.ts
```

**Estado ROTO esperado:** el gate contra el defecto es el caso 1. Escribirlo **antes** del fix e inyectar el `fetchImpl` que nunca resuelve: el test tiene que **fallar por timeout de vitest** (la promesa no se resuelve nunca porque hoy `request()` no tiene deadline). Ese rojo — el test colgándose hasta el límite del runner, no un `expect` fallando — es la prueba de que el bug existe. Anotarlo tal cual. Los casos 2–8 fallan por módulo/símbolo inexistente. Y los tres casos nuevos de v2 fallan **contra el código actual**: `los_verbos_aceptan_opts` porque hoy `post` es `(path, body?)` sin tercer parámetro (`client.ts:215-216`), y `los_10_endpoints_largos_declaran_timeout_cero` enumerando **las 10**. Si `los_verbos_aceptan_opts` pasa antes del fix, el grep está mal: hoy ningún verbo declara `opts`.

**Criterio de aceptación (binario):** los 11 casos verdes, `npx tsc --noEmit` sin errores nuevos respecto de F0, y `npx vitest run src/__tests__/plan273LegacyErrorParsers.test.ts` **verde** (F6 no rompió el contrato del `message`).

**Flag:** **ninguna, y es una decisión, no un descuido.** Ver §3.6 fila F6: un `STACKY_UI_HTTP_TIMEOUT_MS` por UI sería circular. El override vive como parámetro de función (`timeoutMs`), que es donde la varianza real ocurre.

**Impacto por runtime:** ninguno / idéntico en los tres — `AbortController` es del navegador, no del runtime de agente. **Fallback:** si el navegador objetivo no tuviera `AbortController` (no es el caso de ningún target soportado), `timeoutMs` se ignoraría y el comportamiento sería el actual: degradación sin ruptura.

**Trabajo del operador: ninguno.**

---

### F7 — B-01: el gate sin resolver no redirige, y el gate apagado avisa

**Objetivo:** introducir el tercer estado explícito `"unknown" | "on" | "off"` en los gates de tab, y que el efecto de redirección **solo** actúe con `"off"`. **Valor:** el de mayor impacto en percepción de todo el plan. Deep links y reload dejan de rebotar; las URLs de Stacky vuelven a ser compartibles y citables en un ticket.

**Es la fase de mayor esfuerzo. Va última a propósito:** toca el archivo más disputado (`App.tsx`) y se beneficia de que F1 ya haya alineado el shell.

**Archivos a crear:**
- `frontend/src/services/gateState.ts`
- `frontend/src/services/__tests__/plan273GateState.test.ts`

**Archivos a editar:**
- `frontend/src/App.tsx` — declaraciones de estado de los 7 gates de flag, el efecto de los `probeFlagHealth`, el efecto de redirección, la llamada a `initUiSections`, **el JSX de las 7 pantallas con gate (esqueleto, C3)** y **el montaje del aviso (`Toast` + `setToast`, C3)**.

**`frontend/src/services/gateState.ts` — contrato exacto (módulo PURO: sin React, sin CSS, sin DOM):**

```ts
import type { FlagHealthVerdict } from "../utils/flagHealth";

/** Plan 273 F7 (B-01) — tres estados. El booleano confundia "todavia no se" con
 *  "esta apagado", y al montar el valor era `false` = "apagado" ⇒ rebote. */
export type GateState = "unknown" | "on" | "off";

/** El UNICO predicado de redireccion. `unknown` NO redirige: es el fix de H-01. */
export function shouldRedirectAway(state: GateState): boolean {
  return state === "off";
}

/** Traduce el veredicto del health-check a GateState. `unknown` CONSERVA `prev`
 *  (igual que nextEnabledState) pero ahora `prev` puede ser "unknown", que es la
 *  diferencia con el booleano. */
export function gateStateFromVerdict(prev: GateState, v: FlagHealthVerdict): GateState {
  if (v === "enabled") return "on";
  if (v === "disabled") return "off";
  return prev;
}

/** True mientras el gate no resolvio: la pantalla muestra esqueleto, no rebota. */
export function isGateResolving(state: GateState): boolean {
  return state === "unknown";
}
```

**Tabla de decisión completa, que es el criterio de aceptación de la fase:**

| `GateState` | `shouldRedirectAway` | Qué ve el operador | Quién lo implementa |
|---|---|---|---|
| `"unknown"` | **`false`** | Esqueleto de carga en la pantalla pedida. **Este es el fix.** | `isGateResolving()` + `<Skeleton />` de `components/ui` — diff abajo (v2, C3) |
| `"on"` | `false` | La pantalla | el JSX de hoy, sin cambio |
| `"off"` | **`true`** | Redirección a Tickets **con aviso** | `setToast(...)` + `<Toast />` + `publishActivity(...)` — mecanismo abajo (v2, C3) |

**Alcance exacto de F7, y es una decisión de recorte deliberada.** El efecto de redirección tiene 12 ramas, de dos naturalezas distintas:

- **7 ramas de gate por flag** (`migrador`, `devops`, `dbcompare`, `costcenter`, `planes`, `evolution`, `incidencias`): se resuelven por `probeFlagHealth` **después** del montaje, con hasta ~1.2 s de ventana. **F7 las convierte a `GateState`.** Son la totalidad del daño de H-01 medido en tiempo.
- **5 ramas de sección** (`team`, `pm`, `logs`, `docs`, `memory`): vienen del store zustand `useUiSectionsStore`, cuyos defaults verificados son `team: false`, `pm: true`, `logs: true`, `docs: true`, `memory: true` (`store/uiSectionsStore.ts:20-26`), hidratado por `initUiSections()` (llamado fire-and-forget, `App.tsx:136`). ⇒ **de las 5, solo `team` arranca oculta** y rebota; las otras 4 arrancan visibles y **no** rebotan al montar. **F7 NO convierte el store a tri-estado** (sería un refactor de un store compartido, colisión innecesaria); en su lugar agrega **un** booleano `sectionsReady` y **no redirige por sección hasta que la hidratación resolvió**:

```diff
-   initUiSections();
+   void initUiSections().finally(() => { if (alive) setSectionsReady(true); });
```
```diff
- if (tab === "team" && !sections.team) selectTab("tickets");
+ if (!sectionsReady) return;                    // Plan 273 F7: sin hidratar, no se decide
+ if (tab === "team" && !sections.team) selectTab("tickets");
```

**Corrección a la auditoría, menor pero honesta:** H-01 dice "12 de 18 pantallas". Medido sobre el código: rebotan al montar las **7** de flag más `team` = **8**; `pm`/`logs`/`docs`/`memory` tienen default `true` y solo rebotarían si el backend las declara ocultas. El KPI de §1 usa **10 de 18 → 18 de 18** por eso. La severidad del hallazgo no cambia; el número sí, y este plan usa el medido.

**Diff ilustrativo en `App.tsx`** (anclar por `probeFlagHealth`, `nextEnabledState`, `selectTab("tickets")`; **nunca** por línea):

```diff
- const [devopsEnabled, setDevopsEnabled] = useState(false);
+ // Plan 273 F7 (B-01): tres estados. `false` al montar significaba "apagado" y
+ // el efecto de redireccion rebotaba a tickets antes de que el health respondiera.
+ const [devopsGate, setDevopsGate] = useState<GateState>("unknown");
```
```diff
  void probeFlagHealth("/api/devops/health").then((v) => {
-   if (alive) setDevopsEnabled((prev) => nextEnabledState(prev, v));
+   if (alive) setDevopsGate((prev) => gateStateFromVerdict(prev, v));
  });
```
```diff
- else if (tab === "devops" && !devopsEnabled) selectTab("tickets");
+ else if (tab === "devops" && shouldRedirectAway(devopsGate)) selectTab("tickets");
```

**`computeVisibleTabs` sigue tomando booleanos** (`components/shell/shellNav.ts:51-83`, `VisibilityInput`). **No cambiar su firma** (la usa `AppSidebar` y su test `shellNav.test.ts`). En su lugar, adaptar en el sitio de llamada:

```diff
  const visibleTabs = computeVisibleTabs({
    ...
-   devopsEnabled,
+   devopsEnabled: devopsGate === "on",   // Plan 273 F7: un tab se MUESTRA solo si resolvio ON
  });
```
Semántica elegida y por qué: un tab con gate `"unknown"` **no** se muestra en la nav (evita que aparezca y desaparezca), **pero** su ruta **no rebota** (el fix). Las dos cosas son independientes y esta es la combinación correcta: la nav crece hacia arriba (aditivo, sin parpadeo de desaparición) y el deep link sobrevive.

**El esqueleto del caso `"unknown"` — símbolo exacto y diff (v2, C3).** El v1 declaraba en su tabla de decisión que `"unknown"` muestra *"Esqueleto de carga en la pantalla pedida. **Este es el fix**"*, y el smoke 1 lo espera (*"con un esqueleto de carga breve antes"*), pero **no daba archivo, símbolo, diff ni caso de test**: un modelo menor lo habría omitido y el smoke 1 habría fallado por un artefacto que ninguna fase construía. Verificado que la primitiva existe: **`Skeleton`, `frontend/src/components/ui/Skeleton.tsx:33`**, exportada desde el barrel `components/ui/index.ts:19` junto con `skeletonStyle` y el tipo `SkeletonProps`. Se usa esa, no se construye nada:

```diff
+ import { Skeleton } from "./components/ui";
...
  {/* Plan 273 F7 (B-01): con el gate sin resolver la ruta NO rebota; se pinta
      esqueleto en la pantalla pedida hasta que el health conteste. */}
- {tab === "devops" && <DevOpsPage ... />}
+ {tab === "devops" && (isGateResolving(devopsGate)
+   ? <Skeleton />
+   : <DevOpsPage ... />)}
```

Se aplica a las **7** pantallas con gate de flag, con el mismo patrón. **No** se toca el interior de ninguna página (frontera §4): el condicional vive en el JSX de `App.tsx`, que es donde ya se decide qué pantalla se pinta.

**Microcopy del caso `"off"` real — mecanismo exacto (v2, C3).** Hoy no existe ningún mensaje: la redirección es muda. El v1 decía *"reusar el mecanismo de avisos que ya existe en el shell; no construir un componente nuevo"* — y **eso era una premisa falsa que además prohibía la única salida**. Verificado: lo único global montado en el shell es `UndoToastHost` (`App.tsx:28` y `:516`), que es **específico de undo** (se alimenta de `services/undoManager` y está gateado por `STACKY_UNDO_UNIVERSAL_ENABLED`); `components/Toast.tsx` es un componente con estado **local por página**; `publishActivity` (`services/activityCenter.ts:89`) escribe en el Centro de Actividad, que es un log consultable, **no** un aviso visible. **No hay `useToast` ni store global de avisos.** El mecanismo, entonces, se declara así — reusando piezas existentes, sin componente nuevo:

1. **Aviso visible:** el patrón local que ya usan `pages/EvolutionCenterPage.tsx` y `components/AgentHistoryPage.tsx` — `const [toast, setToast] = useState<ToastState | null>(null)` + `<Toast … />` de `components/Toast.tsx` (props `variant: "success" | "warning" | "error"` y `body`, verificadas en `Toast.tsx:9-24`) — **montado en `App.tsx`**, y el efecto de redirección hace `setToast({ variant: "warning", body: <microcopy> })` en la rama `"off"`.
2. **Rastro consultable:** además, `publishActivity({ kind: "error", severity: "warning", title: "Sección desactivada", body: <microcopy>, … })`, que es la pieza que ya usa `PageErrorBoundary.tsx:35-42`. Gratis, y hace el aviso auditable después de que el toast se fue.
3. **`components/ui/` y `components/shell/` tienen presupuesto CERO ABSOLUTO** de hex e inline style (C20, `uiDebtRatchet.test.ts:109-112`): si el aviso necesitara estilo, va por CSS Module, **nunca** `style={{…}}`.

Microcopy (una por sección, con el nombre humano del tab de `TAB_META`):

> **DevOps está desactivado.** Esta sección se activa desde Configuración → Flags del arnés. Te llevamos a Tickets mientras tanto.

El nombre técnico de la flag **no** va en la frase (H-06 / F5): va en el enlace a Flags, vía `detail.flag`. El estado vacío de primera clase con botón `[Ir a Flags]` es **B-10, fuera de scope** (§7).

**Casos borde:**
- El gate resuelve `"off"` **mientras** el operador ya está en la pantalla ⇒ redirige con aviso. Correcto: la flag se apagó de verdad.
- El gate resuelve `"on"` después de que el operador navegó a otra parte ⇒ no se toca la ruta. El efecto depende de `tab`; si `tab` cambió, la rama no aplica.
- `probeFlagHealth` devuelve `"unknown"` tras los 2 reintentos (backend caído) ⇒ el gate queda `"unknown"` **para siempre** en esa sesión ⇒ la pantalla queda en esqueleto y **no** rebota. Es la decisión correcta y hay que declararla: es preferible un esqueleto honesto ("no sé si esto está disponible") a un rebote mudo que el operador lee como "se perdió". El esqueleto debe traer un texto de reintento; usar el `Skeleton` que ya existe en las primitivas.
- **`deepSearchEnabled` NO se convierte.** Es el noveno `useState(false)` (`App.tsx:102`) pero **no tiene rama en el efecto de redirección**: gatea la búsqueda profunda de la paleta, no un tab. Convertirlo sería alcance inventado. **Queda booleano.**
- **`shellV2Enabled` NO se convierte.** Es de F1 y tampoco tiene rama de redirección.

**Tests PRIMERO.** Archivo: `frontend/src/services/__tests__/plan273GateState.test.ts` (puro):

| Caso | Afirma |
|---|---|
| `shouldRedirectAway_tabla_completa` | `"unknown"` ⇒ `false`; `"on"` ⇒ `false`; `"off"` ⇒ `true`. **Los tres, explícitos.** El caso `"unknown" ⇒ false` es *el* gate de H-01 |
| `gateStateFromVerdict_tabla_completa` | 9 combinaciones: `prev` ∈ {unknown,on,off} × `verdict` ∈ {enabled,disabled,unknown}. `enabled`⇒`"on"`, `disabled`⇒`"off"`, `unknown`⇒`prev` (las tres veces) |
| `unknown_desde_unknown_sigue_unknown` | `gateStateFromVerdict("unknown","unknown") === "unknown"`. Es la diferencia exacta con `nextEnabledState`, donde el equivalente colapsaba a `false` |
| `isGateResolving` | solo `"unknown"` ⇒ `true` |
| `App_no_redirige_por_gate_booleano` | Grep sobre el fuente de `App.tsx`: **ninguna** de las 7 ramas de flag del efecto de redirección usa la forma `&& !<algo>Enabled`. Este es el gate de regresión: sin él, un plan futuro reintroduce el booleano y nada grita |
| `App_declara_los_7_gates_como_GateState` | Grep: hay **7** ocurrencias de `useState<GateState>("unknown")` en `App.tsx` |
| `no_se_redirige_por_seccion_sin_hidratar` | Grep: el efecto de redirección contiene `if (!sectionsReady) return;` |
| **`el_gate_sin_resolver_pinta_esqueleto`** (v2, C3) | Grep sobre `App.tsx`: hay **7** ocurrencias de `isGateResolving(` y el archivo importa `Skeleton` de `./components/ui`. Sin este caso, el esqueleto que el smoke 1 espera no lo construye nadie |
| **`el_gate_apagado_avisa`** (v2, C3) | Grep sobre `App.tsx`: el efecto de redirección contiene `setToast(` **y** el archivo contiene la cadena literal `"se activa desde Configuración → Flags del arnés"`. Es el gate del riel de §3.1 (*"redirige **y avisa**, no rebota mudo"*), que en el v1 era una promesa sin mecanismo ni test |
| **`el_aviso_no_nombra_la_flag`** (v2, C3) | El microcopy del punto anterior **no** matchea `/STACKY_[A-Z_]+/`. Coherencia con F5: el nombre técnico va en el enlace, no en la frase |

Comando exacto:
```
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/plan273GateState.test.ts
```

**Estado ROTO esperado:** los 4 primeros fallan por módulo inexistente. Los **6** de grep fallan **contra el código actual**, y son los que importan: `App_no_redirige_por_gate_booleano` tiene que listar las **7** ramas `&& !devopsEnabled`-style que hoy existen (si lista menos de 7, el regex está mal); `el_gate_sin_resolver_pinta_esqueleto` falla con 0 de 7 `isGateResolving(`; `el_gate_apagado_avisa` falla porque hoy la redirección es muda y `App.tsx` no tiene ningún `setToast(`. Total: **10 casos, 6 rojos contra el código actual.**

**Demostración adicional obligatoria de que el gate atrapa el bug.** Antes de escribir el fix, implementar `shouldRedirectAway` a propósito con la versión que replica el bug: `return state !== "on"` (que trata `"unknown"` como apagado, exactamente lo que hace el booleano hoy). Correr. Tiene que salir **rojo** el caso `("unknown") ⇒ false`. Ese rojo es la prueba de que el test discrimina entre el fix y el bug — y no es una formalidad: `state !== "on"` es la implementación que un modelo escribe por descuido y que reintroduce H-01 completo pasando todos los demás casos.

**Criterio de aceptación (binario):**
```
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/plan273GateState.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/components/shell/__tests__/shellNav.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/routes.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/routesDeepLink.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/utils/__tests__/flagHealth.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
Los **10** casos nuevos verdes (7 del v1 + 3 de C3); los cuatro archivos ajenos en el **mismo** estado que F0 (F7 no cambia la firma de `computeVisibleTabs` — verificada en `shellNav.ts:68-83`, con `VisibilityInput` en `:51-60`, C18 —, no toca `routes.ts`, y **no toca `flagHealth.ts`**: `nextEnabledState` sigue existiendo y exportado, porque `setDeepSearchEnabled` lo sigue usando en `App.tsx:166` — verificado).

**Flag:** ninguna. Ver §3.6.

**Impacto por runtime:** ninguno / idéntico en los tres. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F9 — [FASE NUEVA v2, cierra C11] Registrar la huella de regresión

**Objetivo:** dejar en `Stacky Agents/docs/sistema/error_fingerprints.json` la huella de la clase de error que este plan mata con test guardián. **Valor:** es la convención del repo para que una clase de error muerta no vuelva sin que nadie lo note, y el v1 no la mencionaba.

**Estado verificado:** el archivo **existe** (53 KB, `schema_version: 1`, **45** entradas). Esquema de una entrada, leído de la primera (`pipeline_status_404`): `{id, title, class, status, log_pattern, log_guarded, killed_by, killed_commit, date_resolved, guard_test, evidence, note}`, con `status ∈ {resolved, open, by_design}`.

**Honestidad sobre el alcance, y es la razón de que esta fase sea corta:** las huellas de ese archivo son patrones de **log del servidor**, y **6 de los 7 P0 de este plan son del navegador** — no dejan rastro en el log del backend. Solo B-06 tiene una huella genuinamente registrable. **Se registra una entrada, no siete.** Inventar seis huellas sin `log_pattern` real sería ensuciar el archivo para cumplir una formalidad.

**Archivos a editar:**
- `Stacky Agents/docs/sistema/error_fingerprints.json` — **una** entrada nueva.
- `backend/tests/test_plan273_error_message_sin_flags.py` — **un** caso más (no un archivo nuevo: ver §10.1).

**Entrada a agregar** (los campos `killed_commit` y `date_resolved` se completan al commitear F5):

```
id:            error_body_nombra_flag_de_entorno
title:         El cuerpo de error de la API nombra la variable de entorno al operador
class:          http-error-body-leak
status:        resolved
log_pattern:   "(error|message)":\s*"[^"]*STACKY_[A-Z_]+
log_guarded:   false          # el patron se busca en el FUENTE, no en el log
killed_by:     plan 273 F5 (B-06) + F4.6 (superficie de render)
killed_commit: <hash del commit de F5>
date_resolved: <fecha>
guard_test:    tests/test_plan273_error_message_sin_flags.py
evidence:      backend/api/db_compare.py:38; backend/api/migrator.py:101; frontend/src/api/client.ts:208
note:          24 ocurrencias en 13 archivos al momento de matarlo (14 con clave `error`, 10 con `message`). OJO: sacar el nombre de la clave `error` NO lo saca de la pantalla — viaja igual dentro del JSON crudo que client.ts:208 aplana en Error.message; por eso el guardian real son DOS, este y plan273RawErrorSurfaceRatchet.test.ts.
```

**Test (caso a agregar en el archivo de F5):**

| Caso | Afirma |
|---|---|
| `la_huella_de_regresion_esta_registrada` | `docs/sistema/error_fingerprints.json` parsea, y existe una entrada con `id == "error_body_nombra_flag_de_entorno"` cuyo `guard_test` apunta a **este mismo archivo de test** y cuyo `status == "resolved"`. **Auto-referencial a propósito:** si alguien borra el test guardián, la huella queda apuntando a un archivo inexistente y este caso es el que lo grita |

**Estado ROTO esperado:** el caso falla contra el archivo actual con `KeyError`/lista vacía: la entrada no existe entre las 45. Es un gate contra el defecto legítimo (la ausencia de registro), no un tripwire.

**Criterio de aceptación (binario):** el caso verde, `json.load` del archivo sin excepción, y el conteo de entradas pasa de **45** a **46**.

**Flag:** ninguna. Es un archivo de documentación estructurada.

**Impacto por runtime:** ninguno — JSON leído por un test. Fallback: no aplica.

**Trabajo del operador: ninguno.**

---

### F8 — Gate de salida: C1–C6 verificados con smoke manual

**Objetivo:** cerrar los 6 condicionantes del veredicto con evidencia de ejecución, no de código. **Valor:** es el gate que convierte `GO CONDICIONADO` en `GO`. Ver §10, que es la lista enumerada.

**Archivos a editar:** este documento (bitácora de smokes, con resultado por paso).

**Tests:** ninguno automatizado. Por diseño: RTL y jsdom no están instalados (§3.2) y los seis condicionantes son afirmaciones sobre el navegador real (primer paint, contraste percibido, alcance de tabs, spinner). Automatizarlos requeriría infraestructura que este plan no introduce.

**Estado ROTO esperado — corregido en v2 (C4 y C5).** Los **9** smokes tienen que **FALLAR** en la pre-pasada, no 6: el v1 decía *"los smokes 1, 2, 3, 5, 6 y 8"* mientras los **nueve** enunciados de §10.2 cierran con *"Antes del plan: FALLA"* (incluidos el 4 "queda en v1 toda la sesión", el 7 "spinner infinito" y el 9 "1.03:1, texto invisible"). Los siete defectos están vivos: **9 de 9 fallan**. Quien viera 9 fallas contra un criterio que espera 6 no sabría si la medición es válida.

**Y CUÁNDO se corre la pre-pasada — corregido en v2 (C5).** El v1 decía *"correr los 9 smokes sobre el commit anterior a F1"* desde F8, que es el **paso 9** del orden de implementación: para entonces el árbol ya tiene todo aplicado, así que cumplirlo exigiría un `git checkout` — y §9 lo **prohíbe explícitamente** (8 worktrees vivos, trabajo ajeno sin commitear). Contradicción interna con riesgo real de pisar trabajo de otra sesión. Las dos formas admitidas, y solo estas dos:

1. **Preferida:** correr la pre-pasada **en F0**, antes de tocar una línea. El árbol ya está en el commit previo a F1 por definición. Cero riesgo, cero comandos de git.
2. **Alternativa** (si la pre-pasada se olvidó en F0): un **worktree dedicado** en el commit base — `git worktree add ../wt-273-baseline <hash-base>` — y correr los smokes ahí. **Nunca** `checkout` en el árbol compartido. Ojo: un worktree **no tiene venv** y tiene **su propia DB** (`data_dir()` es relativo al árbol), así que para los smokes hay que apuntar el backend a la instancia correcta o aceptar que la DB está vacía (para los smokes 1-4, 8 y 9 da igual; para el 5, 6 y 7 hay que levantar el backend del árbol principal).

**Criterio de aceptación (binario):** los 9 smokes de §10 ejecutados **dos veces** (pre-pasada y build final), cada uno con PASA/FALLA anotado y con la fecha. Pre-pasada: **9 FALLA**. Build final: **9 PASA**. Un FALLA en el build final reabre la fase correspondiente.

**Flag:** ninguna.

**Impacto por runtime:** ninguno — es verificación manual en navegador sobre el backend real.

**Trabajo del operador: SÍ — los 9 smokes de §10 son suyos.** No es configuración ni carga de datos: es la verificación human-in-the-loop del gate de producción, y es exactamente el tipo de decisión que el riel del producto reserva al operador. Ningún otro trabajo del operador en todo el plan.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación (concreta, en el plan) |
|---|---|---|---|---|
| R1 | **F4 rompe los 7 parsers legacy en silencio.** El implementador lee "preservar `message`" como "reemplazar `message`" | **Alta** — es la lectura natural de la auditoría | **Crítico**: 7 componentes toman la rama equivocada sin error ni test rojo | Contrato congelado en `gatewayError.ts` (`message` byte a byte) + caso `message_es_byte_identico_al_formato_historico` + fase entera F4.5 que enumera los 7 y falla si el formato cambia |
| R2 | **F3 tokeniza el badge con `--status-danger-solid`** siguiendo la letra de la auditoría | **Alta** — está escrito así en la fuente | Alto: contraste 6.47 → 3.76 en oscuro, regresión AA sobre un token ya congelado como falla | §3.7(b) con la aritmética; token dedicado `--nav-badge-bg`; y el caso-tripwire `el_badge_no_usa_status_danger_solid` que falla si alguien lo "corrige" |
| R3 | **F5 registra el test nuevo solo en el `.sh`** | **Alta** — es el olvido clásico y la sintaxis del `.ps1` difiere | Medio: pone rojo `test_plan259_ratchet_script_parity` (lag 64→65, holgura CERO) | Instrucción explícita en F5 con la forma exacta de cada array (pelada vs entrecomillada-con-coma) + el criterio de aceptación corre los dos gates |
| R4 | **Colisión con las 4 sesiones paralelas** (263/265/266/267) sobre `App.tsx` / `client.ts` | **Alta** — 8 worktrees vivos | Alto: escrituras perdidas en silencio | §4 completa; regla de anclaje por símbolo (§3.5); F2/F3 evitan `App.tsx` por completo; commits con **pathspec explícito** (§9); prohibido amend/reset/stash/rebase |
| R5 | **F3 rompe los gates de tema ajenos** al agregar un token sin reconciliar | Media | Medio: 2 suites ajenas rojas | Reconciliación de 5 pasos escrita en F3, con el número exacto a bumpear (53→54) y la aclaración de qué **no** tocar (`themeTokens.test.ts`, `--text-on-solid` en el bloque claro) |
| R6 | **F6 confunde cancelación del operador con timeout** | Media | Alto: el operador cancela y ve "el servidor no respondió" | Flag local `timedOut` + combinación de signals; casos `el_abort_del_llamador_no_se_confunde_con_timeout` y su recíproco |
| R7 | **F6 filtra timers**: no se limpia el timeout en el camino feliz | Media | Bajo-Medio: hasta 20 s de timers acumulados con navegación intensa | `clearTimeout` en `finally` + caso `se_limpia_el_timer_en_el_camino_feliz` con `clearTimeout` espiado |
| R8 | **F5 hace visible `"feature_disabled"`** al operador, porque algún consumidor mostraba `errorBody.error` como texto | Media | Medio: regresión de UX introducida por una mejora | Barrido obligatorio de `errorBody.error` en el frontend dentro de F5, con el comando escrito, antes de cerrar la fase |
| R9 | **F7 deja un tab en esqueleto para siempre** si el backend nunca responde | Media | Bajo: es la decisión correcta, pero mal comunicada se lee como "colgado" | Declarado como caso borde en F7 con el requisito de texto de reintento en el esqueleto |
| R10 | **El test de grep de F2 pasa en falso** porque `.shellContent` ya tiene `overflow: auto` | Media | Alto: gate inútil que da falsa confianza | F2 exige extraer el **bloque** de la regla `.nav`, y exige comprobar que el test falla **con** `.shellContent` presente |
| R11 | **Se regenera `uiDebtBaseline.json`** con `UI_DEBT_REGEN=1` "para limpiar" | Baja | Alto: arrastra deuda ajena de otros archivos al baseline | Prohibido explícitamente en F3, con la razón: `count > allowed` ⇒ una baja **nunca** falla, la regeneración es innecesaria |
| R12 | **Se corre la suite completa de vitest** y se interpreta la contaminación cross-file como regresión propia | Media | Medio: tiempo perdido persiguiendo rojo ajeno | §3.2: prohibido; todos los comandos del plan son por archivo |
| R13 | **El implementador "mejora" el alcance**: unifica status HTTP (B-09), retira la nav v1 (B-17), corrige `--text-faint` (B-11) | Media | Medio: plan que no cierra y colisiona con planes futuros | §7 nombra cada uno como plan futuro; F5 regla 4 prohíbe tocar status; F7 declara qué **no** convierte (`deepSearch`, `shellV2`, el store de secciones) |
| **R14** (v2, C13) | **El implementador documenta en un comentario CSS el color que acaba de sacar**, y con eso pone rojo el gate de cero-hex de su propia fase | **Alta** — es el instinto correcto de documentar, y el v1 lo dictaba textualmente | Alto: el gate nuevo nace rojo tras el fix, o peor, se "arregla" relajándolo | Prohibición explícita en F3 + los 4 comentarios ya reescritos perifrásticamente + verificación obligatoria del conteo de hex **después** del fix |
| **R15** (v2, C14) | **F4 empeora el único archivo de UI que toca:** un `TypeError` de render se muestra como "No se pudo conectar con el servidor." | **Alta** — es el comportamiento del algoritmo del v1, no un descuido | Alto: se pierde el diagnóstico real del crash vivo del 266 | Paso 0 del algoritmo + caso `ufm_un_typeerror_de_render_no_se_disfraza_de_error_de_red` + Demostración 2 obligatoria (ver el rojo sin el paso 0) |
| **R16** (v2, C2) | **F6 aborta a los 20 s una sincronización legítima** (`/api/tickets/sync` es síncrono dentro del request) y el operador reintenta, **duplicando** el disparo | **Alta** si no se enumeran los endpoints | **Crítico**: escritura duplicada en el sistema real del operador | Tabla de los 10 endpoints con `timeoutMs: 0` + caso `los_10_endpoints_largos_declaran_timeout_cero` + la regla "ante la duda, `timeoutMs: 0`" |
| **R17** (v2, C1) | **Se declara C3 cerrado con el gate de F5 en verde** mientras `STACKY_*` sigue en pantalla | **Alta** — el gate del backend da 5/5 verde con el defecto vivo | Alto: falso verde en el gate de producción, que es exactamente lo que este repo persigue | F4.6 migra las 14 ocurrencias de las 10 superficies; F4.7 congela el resto; el KPI se reformuló para medir el frontend, no el backend |
| **R18** (v2, C19) | **Se agrega `--nav-badge-bg` fuera de `:root {…}` (`:3-164`)** y los tres gates de tema pasan verde sin haber verificado nada | Media | Medio: el token queda sin re-apuntar en claro y el anti-drift no lo ve | F3 paso 1 exige el rango + verificación con `Select-String` que debe devolver **dos** líneas |

---

## 7. Fuera de scope

Los 17 ítems restantes del backlog de la auditoría (B-08…B-24) **no** están en este plan. La frontera es deliberada: los 7 P0 son el gate de producción; el resto es mejora posterior con dependencias propias. Cada uno es candidato a su propio plan.

**Explícitamente fuera, con el motivo:**

| Ítem | Qué es | Por qué no acá |
|---|---|---|
| **B-09** + **B-10** | Unificar status y `error` de "feature desactivada" (4 códigos para una semántica) + estado vacío de primera clase con `[Ir a Flags]` | Es un **cambio de contrato HTTP** con consumidores; F5 deliberadamente **no toca ningún status** (regla 4). Los dos juntos son un plan propio: convierten 403 flags de fuente de confusión en superficie de descubrimiento |
| **B-15** | Endpoint único de capacidades de UI (≤2 llamadas antes de decidir la nav, en lugar de 10) | Es la **raíz estructural** de H-01/H-02 y depende de B-01 + B-03, que este plan entrega. Hacerlo acá duplicaría el trabajo de F1/F7 y agregaría un contrato nuevo al gate de producción. **Es el plan siguiente natural** |
| **B-17** | Retirar la nav v1 y dejar `TAB_META` como fuente única de las 18 etiquetas | Depende de B-03, B-05 y B-07 (los tres de este plan) **más** confirmar que v2 cubre las 18 pantallas. Retirar v1 volvería F2 y F3 innecesarias — pero mientras v1 exista es el camino de fallo, y en el gate de producción se corrige, no se apuesta a eliminarla |
| **B-19** | Congelar la deuda de estilo con ratchet por archivo (723 inline + 1314 hex) y pagarla por concentración | Alcance grande y transversal. F3 baja `App.module.css` de 4 hex a 0 como efecto lateral; el resto es su propio plan |
| **B-08** | Pasar el `ctx` real en `PipelineYamlPreview` | P1, 1 línea, zona del plan 265/267 |
| **B-11** | `--text-faint` a ≥4.5:1 (hoy 3.77 oscuro / 4.27 claro, 97 usos en 45 archivos) | P1. Un literal que propaga a 97 usos; cambio visual amplio que merece su propia verificación. Medido en esta corrida y coincide con la auditoría |
| **B-12** + **B-13** | Identidad de reserva única (9 sitios, 6 valores) + límite de red documentado y verificado | P1, backend/seguridad. La auditoría es explícita: **no** construir login ni RBAC (riel mono-operador) |
| **B-14** | Aviso de ruta desconocida en lugar de rebote mudo | P2, depende de B-01 |
| **B-16** | Decidir y hacer cumplir el compromiso de responsive | P2. Es la mitad de C6 que **no** es tema claro; ver §10 C6 |
| **B-18** | Constante única de tipos de flag + test de igualdad de conjuntos | P3, backend |
| **B-20** | `onOpenExecution` obligatoria, borrar el fallback a `console.log` | P3 |
| **B-21** | Estado de error visible cuando fallan recomendaciones / sentimiento en PM | P2, depende de B-02 (que este plan entrega) |
| **B-22** | Documentar las 4 pantallas faltantes + gate de paridad doc↔`TAB_PATHS` | P1, documentación |
| **B-23** | Instrumentar los 7 eventos P1 de experiencia (`nav.gate_bounce`, `api.error_shown`, `api.timeout`…) | P1. Es lo que convertiría los KPI de §1 de smoke manual a números continuos. Depende de B-02 y B-04, que este plan entrega |
| **B-24** | Regla única de estado de carga: `Skeleton` / `Spinner` / nunca texto plano solo | P2. F7 usa el `Skeleton` existente para el caso `"unknown"`, sin abrir la regla global |

**También fuera, y no son deuda:** login, registro, roles, RBAC, multiusuario (riel mono-operador; H-08 lo documenta como decisión de producto coherente). Planes comerciales y cuotas (§3.15 de la auditoría: encuadre equivocado del pedido, no defecto). Las áreas que la auditoría **no** cubrió (ciclo de vida del agente, integraciones externas, grafo/RAG) — pueden esconder un bloqueante, y este plan no lo afirma ni lo niega.

---

## 8. Glosario

Términos del dominio Stacky que un modelo implementador puede no conocer. Todos verificados en el código.

| Término | Qué es |
|---|---|
| **Flag del arnés** | Entrada del `FLAG_REGISTRY` de `backend/services/harness_flags.py` (403 flags: 294 `bool`, 64 `int`, 25 `csv`, 10 `str`, 9 `float`, 1 `json`). El panel de Configuración las renderiza **todas**, incluidas las numéricas y de texto. **Este plan no agrega ninguna** |
| **Gate (de tab)** | Booleano que decide si un tab de la nav se muestra. Se resuelve por red al montar, con `probeFlagHealth`. F7 lo convierte en `GateState` de tres valores |
| **`probeFlagHealth`** | `frontend/src/utils/flagHealth.ts:34`. Pega a un endpoint `/health` de feature y devuelve `"enabled" | "disabled" | "unknown"`. 2 reintentos con backoff 400→800 ms ⇒ hasta ~1.2 s |
| **Veredicto vs estado** | *Veredicto* es lo que devuelve un probe (`FlagHealthVerdict`). *Estado* es lo que la app guarda (`GateState`). `gateStateFromVerdict` traduce uno al otro |
| **Nav v1 / shell v2** | Dos navegaciones completas y coexistentes. v1 = lista plana de 18 botones con emoji, en el JSX de `App.tsx`. v2 = sidebar agrupada en 5 grupos (`components/shell/shellNav.ts`), elegida por `STACKY_UI_SHELL_V2_ENABLED` (default backend `true`) |
| **`TAB_META`** | `components/shell/shellNav.ts:16-35`. Etiqueta + nombre de icono de los 18 tabs, para v2. Las mismas etiquetas viven **también** como literales JSX en la nav v1: drift conocido, es B-17 |
| **Ratchet** | Test que congela una métrica de deuda y falla si **empeora**. Nunca exige cero: exige no-aumento. `uiDebtRatchet` compara `count > allowed` por archivo |
| **Criterio delta** | Criterio de aceptación formulado como "mi cambio no empeora el número que medí antes", en vez de "la suite está verde". Obligatorio sobre gates compartidos, porque hay rojo ajeno |
| **Gate contra el defecto** | Un test solo cuenta si se lo vio **rojo** ante el bug que dice atrapar, **antes** del fix. Un test que nace verde no prueba nada |
| **`GatewayErrorBody`** | `frontend/src/api/client.ts:36-41`. `{ error, message, correlation_id, detail }`. Ya lo devuelven `rawGet`/`rawPost`/`rawPut` en su campo `errorBody`; `api.*` lo tiraba |
| **`raw*` vs `api.*`** | `api.get/post/...` **lanzan** en todo non-2xx y (antes de F4) aplanaban el cuerpo en un string. `rawGet/rawPost/rawPut` **no lanzan**: devuelven `{ status, ok, data, errorBody }`. Existen porque un 404 de feature desactivada tiene que llegar como dato, no como excepción |
| **`correlation_id`** | Identificador que el backend pone en el cuerpo de error y que permite correlacionar la queja del operador con el log del servidor. Hoy se pierde en el aplanado |
| **Token (de tema)** | Variable CSS de `frontend/src/theme.css`. El bloque `:root` es el tema oscuro; `:root[data-theme="light"]` re-apunta los valores. Un literal de color **no** lo puede re-apuntar el tema: por eso la nav v1 es ilegible en claro |
| **WCAG AA** | Contraste mínimo 4.5:1 para texto normal. La fórmula usada en este plan es la de luminancia relativa: linealizar cada canal con `((c+0.055)/1.055)^2.4`, `L = 0.2126R + 0.7152G + 0.0722B`, ratio `(L1+0.05)/(L2+0.05)` |
| **HITL / human-in-the-loop** | Riel innegociable: el sistema amplifica al operador, nunca lo reemplaza. Los 9 smokes de §10 son HITL |
| **Mono-operador** | Stacky corre para un operador. `current_user()` es un header sin validar. No hay auth real ⇒ nada de RBAC |
| **Los 3 runtimes** | Codex CLI, Claude Code CLI y GitHub Copilot Pro. Todo cambio debe funcionar en los tres. En este plan el impacto es **idéntico y nulo** en los tres, porque los 7 P0 son frontend y contrato HTTP |
| **Worktree** | Copia de trabajo git con rama propia. Hay 8 vivos. Cada uno tiene **su propia DB** (`data_dir()` es relativo al árbol) y **ninguno** tiene venv: se usa el intérprete del árbol principal por ruta absoluta |

---

## 9. Orden de implementación

1. **F0** — medir la línea base (**8** valores, v2: + `tsc` por C15 y + superficie cruda por C1) y anotar qué gates compartidos ya están rojos. **Y correr la pre-pasada de los 9 smokes acá** (C5): es el único momento en que el árbol está en el commit previo sin necesidad de `checkout`. **No se salta:** sin esto los criterios delta no son verificables. Commit de bitácora, o anotar en el mensaje del commit siguiente.
2. **F1** — B-03, shell v2 alineado + `.catch` que no degrada + `!== false` (C8). Lo más barato; se despliega solo. Commit propio.
3. **F2 + F3** — B-05 y B-07, en **un solo commit**: las dos editan `App.module.css` en reglas disjuntas, y hacerlas en dos pasos con sesiones paralelas en el árbol es riesgo sin beneficio. Incluye la reconciliación de **6** pasos de los gates de tema (v2: 3b por C15/C10) y la verificación de cero-hex **con los comentarios ya escritos** (C13).
4. **F4** — B-02, `GatewayError` + `userFacingMessage` **con el paso 0** (C14), **aditivo**. Incluye las **dos** demostraciones obligatorias (4 rojos del saneamiento + 1 rojo de la regresión del paso 0). Commit propio.
5. **F4.5** — congelar los 7 parsers legacy. **Antes de F5 y F6.** Puede ir en el commit de F4.
6. **F4.6 + F4.7** (v2) — migrar las 14 ocurrencias de las 10 superficies gateadas + el ratchet de superficie cruda (42 → 28). **Antes de F5.** Pueden ir en un solo commit.
7. **F5** — B-06, los 24 cuerpos en 13 archivos (14 forma A + 10 forma B) + registro del test en el `.sh` **y** el `.ps1` + barrido de `errorBody.error`. Commit propio.
8. **F6** — B-04, timeout + `opts?: RequestOptions` aditivo en los 4 verbos + los 10 endpoints en `timeoutMs: 0` (C2). Commit propio.
9. **F7** — B-01, `GateState` + esqueleto + aviso (C3). Toca el archivo más disputado. Commit propio.
10. **F9** (v2) — la huella de regresión, con el hash del commit de F5. Commit propio o junto a F8.
11. **F8** — los 9 smokes de §10 sobre el build final (los 9 deben PASAR), comparados contra la pre-pasada de F0 (los 9 debieron FALLAR). Bitácora en este documento.

**Reglas de commit, no negociables** (el índice git es compartido por 8 worktrees y el árbol tiene trabajo ajeno sin commitear de los planes 217 y 262):

- **Pathspec explícito, siempre:** `git commit -m "..." -- "<ruta1>" "<ruta2>"`.
- **Prohibido** `git add -A`, `git add .`, `git commit -a`.
- **Prohibido** `amend`, `reset`, `stash`, `checkout`, `rebase`, `--no-verify`.
- Si un `git mv` forma parte de un cambio, verificar con `git show HEAD:<ruta>` que la mitad del borrado quedó **commiteada**: un pathspec parcial deja el `D` staged sin commitear.
- **El push es siempre manual del operador.** Ninguna fase pushea.

---

## 10. Definition of Done global

### 10.1 Gates automatizados (comandos exactos, todos por archivo)

```powershell
# Frontend — 8 archivos de test, uno por invocacion
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273ShellV2Default.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273NavCss.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/api/__tests__/plan273GatewayError.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273LegacyErrorParsers.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273ErrorSurface.test.ts              # F4.6 (v2, C1)
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/plan273RawErrorSurfaceRatchet.test.ts    # F4.7 (v2, ADICION)
cd "Stacky Agents\frontend"; npx vitest run src/api/__tests__/plan273RequestTimeout.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/plan273GateState.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit

# Frontend — gates compartidos: criterio DELTA contra F0, NO "verde"
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeContrast.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeLightTokens.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/themeTokens.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/components/shell/__tests__/shellNav.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/routes.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/routesDeepLink.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/utils/__tests__/flagHealth.test.ts

# Backend — uno por invocacion, interprete por ruta absoluta
cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_plan273_error_message_sin_flags.py -q
cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_harness_ratchet_meta.py -q
cd "Stacky Agents\backend"; & "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest tests/test_plan259_ratchet_script_parity.py -q
```

**Condición de cierre de 10.1 — recontada en v2 (C6).** El v1 decía *"los **6** archivos de test nuevos (**43** casos: 3+6+14+3+8+7+5)"*: eran **7** sumandos (⇒ 7 archivos) y la suma da **46**, no 43. Con las fases y casos nuevos del v2, el conteo correcto es:

| Archivo de test | Fase | Casos |
|---|---|---|
| `src/__tests__/plan273ShellV2Default.test.ts` | F1 | **4** (3 + C8) |
| `src/__tests__/plan273NavCss.test.ts` | F2 + F3 (compartido) | **6** |
| `src/api/__tests__/plan273GatewayError.test.ts` | F4 | **16** (14 + 2 de C14) |
| `src/__tests__/plan273LegacyErrorParsers.test.ts` | F4.5 | **3** |
| `src/__tests__/plan273ErrorSurface.test.ts` | F4.6 (v2) | **4** |
| `src/__tests__/plan273RawErrorSurfaceRatchet.test.ts` | F4.7 (v2) | **4** |
| `src/api/__tests__/plan273RequestTimeout.test.ts` | F6 | **11** (8 + 3 de C2) |
| `src/services/__tests__/plan273GateState.test.ts` | F7 | **10** (7 + 3 de C3) |
| `backend/tests/test_plan273_error_message_sin_flags.py` | F5 + F9 | **6** (5 + 1 de C11) |
| **Total** | | **9 archivos · 64 casos** (8 frontend + 1 backend) |

**La suma está verificada a mano: 4+6+16+3+4+4+11+10+6 = 64.** Si al implementar el número real difiere, gana el conteo del implementador y se anota la diferencia en la bitácora — pero no se cierra con un total que no coincide con la suma de las tablas de fase.

**Un solo archivo de test backend, y es deliberado:** F9 agrega su caso al archivo de F5 en vez de crear uno nuevo, para no tener que registrar un **segundo** archivo en los DOS scripts del arnés con el lag en holgura CERO (§3.4). Un archivo nuevo = dos ediciones más y un riesgo más.

Los **8 gates compartidos** en el mismo estado que F0 (delta cero). `tsc --noEmit` sin errores nuevos **respecto de la línea base que F0 mide** (C15). **Prohibido** cerrar con "todo verde" si algún gate compartido ya estaba rojo en F0: se declara el rojo ajeno con su nombre y se demuestra que no lo empeoró este plan.

**Y una condición que no es un comando:** cada fase tiene anotado su **estado ROTO observado**, con el mensaje real del test. Una fase sin rojo observado no está hecha, aunque su test esté verde.

### 10.2 Gate de salida C1–C6 y los 9 smokes manuales

Los seis condicionantes del veredicto de la auditoría, con su verificación. **Los smokes se corren dos veces: la pre-pasada en F0, antes de tocar nada (donde los 9 de 9 deben FALLAR — C4), y sobre el build final (donde los 9 deben PASAR).** La pre-pasada **no** se hace con `checkout` (C5, ver F8).

| # | Condicionante | Cerrado por | Verificación |
|---|---|---|---|
| **C1** | Un deep link / reload a una pantalla con gate aterriza en esa pantalla, no en Tickets | F7 (B-01) | Smokes 1, 2 |
| **C2** | La app no cambia de arquitectura de navegación después del primer paint, y un fallo de health no degrada a la nav vieja | F1 (B-03) | Smokes 3, 4 |
| **C3** | El operador no ve `"500 INTERNAL SERVER ERROR: {...}"` ni nombres `STACKY_*`; se usa el `message` que el backend redacta | F4 (B-02) + **F4.6 (C1)** + **F4.7 (ratchet)** + F5 (B-06) | Smokes 5, 6 |
| **C4** | Timeout en el cliente HTTP | F6 (B-04), **con los 10 endpoints largos en `timeoutMs: 0`** | Smoke 7 |
| **C5** | Ningún tab queda inalcanzable por recorte horizontal de la nav | F2 (B-05) | Smoke 8 |
| **C6** | Decisión explícita y documentada sobre tema claro y sobre responsive | F3 (B-07) **parcial** | Smoke 9 + decisión escrita (ver nota) |

> **Nota honesta sobre C6.** F3 cierra la **mitad de tema claro**: la nav v1 pasa de 1.03:1 a 6.00:1 y el tema claro deja de ser inutilizable, así que **se soporta** y el toggle se queda. La **mitad de responsive** de C6 (H-10, soporte indefinido) es **B-16 y queda fuera de scope** (§7). ⇒ **C6 no se cierra con este plan.** Lo que este plan entrega es: (a) tema claro soportado y verificado, (b) la decisión de responsive **explicitada como pendiente y asignada a B-16**, que es más de lo que hay hoy (indefinido) pero menos de lo que C6 pide. **Declararlo así en el gate de producción**: cinco condicionantes cerrados, uno cerrado a medias con la mitad restante nombrada. Fingir que C6 está cerrado sería exactamente el falso verde que este repo persigue.

**Los 9 smokes manuales, enumerados.** Cada uno: pasos, resultado esperado, y qué condicionante cierra.

1. **Deep link a una pantalla con gate sobrevive el reload.** (C1)
   1. Verificar que la flag de DevOps está activa en Configuración → Flags del arnés.
   2. Navegar en la app hasta DevOps.
   3. Confirmar que la URL es `/devops`.
   4. Pulsar F5.
   5. **Esperado:** la URL sigue siendo `/devops` y la pantalla es DevOps, con un esqueleto de carga breve antes. **Antes del plan: FALLA** (aterriza en Tickets).

2. **Deep link en frío, sin pasar por la app.** (C1)
   1. Cerrar la pestaña.
   2. Abrir una pestaña nueva y pegar la URL `/devops` directamente.
   3. **Esperado:** aterriza en DevOps. **Antes del plan: FALLA.**
   4. Repetir con `/dbcompare`, `/costcenter`, `/planes`, `/evolution`, `/migrador`, `/incidencias`. **Los 7 deben aterrizar.**

3. **La navegación no cambia de forma después del primer paint.** (C2)
   1. Con el backend vivo, recargar la app.
   2. Observar el primer paint: ¿sidebar agrupada (v2) o barra plana de botones con emoji (v1)?
   3. Esperar 3 segundos y volver a observar.
   4. **Esperado:** las dos observaciones son la **misma** nav (sidebar agrupada), sin salto de layout. **Antes del plan: FALLA** (v1 → v2).

4. **Un health caído no degrada la arquitectura de navegación.** (C2)
   1. Detener el backend (o bloquear `/api/diag/health` en las devtools).
   2. Recargar la app.
   3. **Esperado:** la nav sigue siendo la sidebar agrupada. **Antes del plan: FALLA** (queda en v1 toda la sesión, sin aviso).

5. **Un error de feature desactivada es legible.** (C3)
   1. Apagar la flag del Comparador de BD en Configuración → Flags del arnés.
   2. Navegar a Comparador BD y disparar una acción que llame a la API.
   3. **Esperado:** se lee una frase como *"El Comparador de BD está desactivado."* **NO** se lee `403 FORBIDDEN: {...}`, **NO** se lee `STACKY_DB_COMPARE_ENABLED`, **NO** se lee `feature_disabled`. Si hay `correlation_id`, aparece como pie discreto `ref. <id>`. **Antes del plan: FALLA.**

6. **Un 500 no muestra JSON crudo.** (C3)
   1. Provocar un 500 en cualquier endpoint (o interceptarlo en devtools devolviendo 500 con cuerpo `{"ok":false,"trace":"..."}`).
   2. **Esperado:** se lee una frase en castellano. **NO** aparece `INTERNAL SERVER ERROR`, ni una llave `{` de JSON, ni un status de 3 dígitos al inicio del texto. **Antes del plan: FALLA.**

7. **Un backend colgado produce un error accionable, no un spinner eterno.** (C4)
   1. Con la SPA abierta, pausar el proceso del backend con un breakpoint (o suspenderlo) — **pausar, no matar**: matarlo da un error de conexión, que es un caso distinto.
   2. Navegar a una pantalla que cargue datos.
   3. **Esperado:** en ~20 s aparece un estado de error de timeout con opción de reintentar. **NO** queda cargando indefinidamente. **Antes del plan: FALLA** (spinner infinito).
   4. Reanudar el backend y confirmar que un reintento funciona.

8. **Ningún tab queda inalcanzable en la nav v1.** (C5)
   1. Habilitar todas las secciones opcionales.
   2. Forzar la nav v1: `STACKY_UI_SHELL_V2_ENABLED=false`.
   3. Estrechar la ventana a 1280 px de ancho.
   4. **Esperado:** todos los tabs son alcanzables con el mouse (por scroll horizontal de la barra), sin usar teclado ni paleta de comandos. Verificar puntualmente el **último** del orden de v1 (Evolución). **Antes del plan: FALLA** (queda recortado, sin scroll).

9. **La nav se lee en tema claro.** (C6, mitad de tema claro)
   1. Activar el tema claro.
   2. Forzar la nav v1 (paso 2 del smoke 8).
   3. **Esperado:** las etiquetas de tab se leen en reposo, se leen en hover, y el tab activo se distingue con el color de acento del sistema (azul), no con un índigo ajeno. El contador rojo del tab Revisión se lee en blanco sobre rojo. **Antes del plan: FALLA** (1.03:1, texto invisible).

### 10.3 Bitácora obligatoria

Al cerrar, este documento debe contener:

- Los **8** valores de línea base de F0, con su valor real medido (v2: incluidos el conteo de `tsc --noEmit` y las 42 ocurrencias del modismo de aplanado).
- Por cada fase **F1–F7, F4.6, F4.7 y F9**: el **estado roto observado** (mensaje real del test antes del fix) y el comando con el que se vio verde después.
- **Las tres demostraciones obligatorias de que los gates discriminan**, con su rojo transcrito: los 4 rojos de la versión ingenua de `userFacingMessage` (F4), el rojo del algoritmo **sin el paso 0** (F4, C14), y el `42 > 28` del ratchet antes de F4.6 (F4.7).
- **El conteo de hex de `App.module.css` DESPUÉS del fix de F3** (debe ser 0; si es 4, son los comentarios — C13).
- Los 9 smokes, con PASA/FALLA y fecha, **en las dos corridas** (pre-pasada en F0 y build final), con **9 FALLA** en la primera y **9 PASA** en la segunda.
- **El total real de casos verdes**, comparado contra los **64** de la tabla de §10.1.
- Cualquier anclaje de este documento que no coincidiera con el código al implementar, con el símbolo que se usó en su lugar.
- El estado de C1–C6, con C6 declarado explícitamente como **parcial** (§10.2 nota).
- **El número de entrada de `error_fingerprints.json`** (debe pasar de 45 a 46) y el hash de `killed_commit`.
