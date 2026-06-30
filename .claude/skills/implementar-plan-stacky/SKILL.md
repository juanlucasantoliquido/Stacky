---
name: implementar-plan-stacky
description: Implementa un plan ya escrito de `Stacky Agents/docs/<NN>_PLAN_*.md` fase por fase, test-first (TDD), respetando los rieles duros de Stacky y SIN falsos verdes. Resuelve el plan objetivo dinámicamente (argumento del operador o el `NN` más alto), hace un pre-flight que rechaza implementar planes ambiguos (los rebota a `criticar-y-mejorar-plan`), implementa cada fase F0..Fn con sus tests nombrados corriéndolos de verdad con el intérprete/venv correcto del repo, verifica criterios binarios, y reporta honestamente qué quedó verde y qué no. REGLA DURA: si el plan introduce flags o configuración que el operador deba setear, TODO debe quedar activable/configurable desde la UI (no solo env var). Es el PASO SIGUIENTE de `criticar-y-mejorar-plan`: usala cuando el plan ya está endurecido y querés construirlo. NO genera planes (eso es `proponer-plan-stacky`) ni los critica (eso es `criticar-y-mejorar-plan`).
---

# Implementar plan Stacky (TDD, rieles duros, sin falsos verdes)

Esta skill es el TERCER eslabón del pipeline de planes: `proponer-plan-stacky` (redacta) →
`criticar-y-mejorar-plan` (endurece a v2) → **`implementar-plan-stacky` (construye)**. Toma un plan ya
escrito y endurecido en `Stacky Agents/docs/<NN>_PLAN_*.md` y lo IMPLEMENTA fase por fase, test-first,
respetando los guardarraíles de Stacky, corriendo los tests de verdad, y reportando el estado real sin
maquillarlo.

El número del plan objetivo nunca se hardcodea: se resuelve en cada corrida (argumento del operador, o el
`NN_PLAN_*.md` de número más alto en `Stacky Agents/docs/` si no se indica).

## Cuándo usarla

- Justo después de `criticar-y-mejorar-plan`, cuando el plan ya está en v2 y querés construirlo.
- Cuando el operador dice "implementá el plan 53", "construí el último plan", "hacelo".
- NO la uses para generar un plan (eso es `proponer-plan-stacky`) ni para criticarlo
  (eso es `criticar-y-mejorar-plan`). Si el plan objetivo todavía es ambiguo, esta skill NO lo implementa:
  lo rebota a `criticar-y-mejorar-plan` (ver Pre-flight).

## Resultado (entregable)

1. El código del plan implementado fase por fase en una **rama** (nunca directo en `main`), con los tests
   de cada fase **corridos de verdad** y en verde, y el typecheck del frontend limpio si se tocó UI.
2. Un **reporte de implementación honesto** (al cerrar): por fase F0..Fn → IMPLEMENTADA / PARCIAL /
   BLOQUEADA, con el comando de test exacto que se corrió y su resultado real (nº de tests, pass/fail).
   Prohibido el falso verde: si un test falla o se saltó, se dice — no se maquilla.
3. Una **memoria de estado** actualizada (`plan-<NN>-status`): qué fases quedaron implementadas, flags
   nuevos con su default, y los enlaces `[[...]]` a memorias relacionadas. Un archivo, sin duplicar.
4. Un **commit** en la rama de trabajo con lo implementado del plan (ver "Commit tras implementar"). El
   **push NO se hace salvo pedido explícito del operador.**
5. Un **resumen final de 6 líneas** + handoff: qué se construyó, qué quedó pendiente/bloqueado, el hash
   del commit, y el siguiente paso.

## Rieles duros (no negociables — valen para TODA la implementación)

- **Configuración SIEMPRE por UI (regla dura de este skill).** Si el plan introduce CUALQUIER flag o
  parámetro que el **operador** deba activar o ajustar, ese control tiene que quedar **activable/editable
  desde la UI** — no solo como variable de entorno. Concretamente: backend que lee el valor + endpoint
  para leerlo/setearlo + control en el frontend, **reusando las superficies de configuración que ya
  existen** (p. ej. `api/client_profile.py` + su panel, el modal de settings de Claude Code, o el panel de
  flags del arnés `services/harness_flags.py`) en vez de inventar una pantalla nueva. Default seguro (off).
  ÚNICA excepción: un kill-switch puramente INTERNO que el operador nunca toca (telemetría, defaults de
  arnés horneados) puede quedar env-only — pero si hay duda de si el operador querría tocarlo, va a la UI.
- **Test-first de verdad (TDD) y CERO falsos verdes.** Por cada fase: primero el test nombrado en el plan,
  después el código, y se **corre el test realmente** con el intérprete/venv correcto del repo. Un test que
  no se corrió NO está verde. Si falla y no lo podés arreglar, se reporta BLOQUEADA con el output real; no
  se comenta el test, no se hace `xfail`/`skip` silencioso, no se declara hecho lo que no se verificó.
  (Lección del repo: hubo "falsos verdes" donde se declaró arreglado un 500 que seguía fallando.)
- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. La implementación preserva
  que cada cosa funcione en los 3 o degrade con fallback explícito. Nada nuevo atado a un solo runtime
  (ojo deudas reales de paridad: style_memory copilot-only).
- **Cero trabajo extra al operador:** la feature es invisible/automática u opt-in con default off; sin
  pasos manuales nuevos. (No confundir con la regla de UI: "configurable por UI" ≠ "obligatorio
  configurar"; el default debe funcionar sin que el operador toque nada.)
- **Human-in-the-loop innegociable:** amplificar al operador, jamás reemplazarlo. Sin autonomía proactiva.
- **Mono-operador sin auth real:** nada de RBAC/multiusuario/roles/403 (`current_user` es un header sin
  validar).
- **No degradar** performance/seguridad/estabilidad/DX; backward-compatible; reusar lo existente (memoria
  colaborativa, flags del arnés, telemetría, gates golden, client_profile) en vez de reinventar.

## Comandos del repo (usá EXACTAMENTE estos, no inventes)

- **Tests backend (por archivo, con el venv del repo):**
  `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest "Stacky Agents/backend/tests/<archivo>.py" -q`
  Corré los archivos de test que nombra el plan, fase por fase. (El venv es py3.13; correr por archivo
  evita el pin roto de pywin32. Vitest del frontend NO está instalado: no intentes correr tests JS.)
- **Typecheck frontend (si se tocó UI):** en `Stacky Agents/frontend/` → `npx tsc --noEmit`
  (es lo que hace `npm run build` antes de compilar). Debe terminar con 0 errores.
- **Rama:** si estás en `main`, creá una rama antes de tocar nada. Si ya estás en una rama de trabajo,
  seguí en ella.
- **Commit (tras implementar):** `git add -A` de lo del plan y un commit en la rama de trabajo. Mensaje:
  `feat(plan-<NN>): <slug corto> — F0..Fn implementadas` (ajustá tipo `feat`/`fix`/`docs` según el plan).
  El mensaje DEBE terminar con la línea de co-autoría:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
  **NO `git push`** salvo pedido explícito del operador. NUNCA `--no-verify` (si un hook falla, arreglá la
  causa). Si quedaron fases BLOQUEADAS, igual commiteá lo verde y dejalo explícito en el mensaje + reporte.

## Pasos de ejecución

1. **Resolver QUÉ plan.** Si el operador pasó número/ruta, ese es el objetivo. Si no, listá
   `Stacky Agents/docs/`, tomá el `NN_PLAN_*.md` de número más alto. Nunca hardcodees el número.
2. **Pre-flight (gate de implementabilidad).** Leé el plan completo. Verificá que tenga: fases F0..Fn
   ordenadas por dependencia, archivos y símbolos EXACTOS, tests nombrados con comando, y criterios de
   aceptación BINARIOS. Si el plan es vago en algún paso (un modelo tendría que INFERIR), **NO lo
   implementes**: reportá qué falta y recomendá correr `criticar-y-mejorar-plan` primero. Implementar un
   plan ambiguo produce basura.
3. **Chequeo de configuración por UI.** Recorré el plan buscando flags/config. Por cada uno, decidí: ¿el
   operador necesita setearlo? Si sí y el plan solo lo define como env var, **ampliá el alcance**: agregá
   el wiring de UI (backend+endpoint+control de frontend, reusando una superficie existente) como parte de
   la implementación. Anotá esto explícitamente antes de codear.
4. **Preparar el terreno.** Asegurá rama (paso "Comandos"). Orientación barata: leé SOLO los archivos que
   el plan toca + sus tests vecinos. No releas el repo entero.
5. **Implementar fase por fase (TDD).** Para CADA fase F0..Fn, en orden:
   a. Escribí/ajustá el test nombrado en el plan (primero).
   b. Implementá el código mínimo de la fase (archivos/símbolos exactos del plan; flags con default off;
      config del operador con su control de UI).
   c. **Corré el test de esa fase** con el comando exacto del backend (y `tsc --noEmit` si tocaste UI).
   d. Verificá el criterio binario de la fase. Si pasa, seguí; si no, arreglá o marcá BLOQUEADA con el
      output real y seguí a lo que no dependa de ella. Nunca avances declarando verde lo que no corriste.
6. **Verificación global.** Corré los archivos de test de todas las fases tocadas (no solo la última) +
   `tsc --noEmit` si hubo UI. Confirmá el DoD global del plan. Reportá el conteo real de tests.
7. **Persistir estado.** Actualizá/creá la memoria `plan-<NN>-status` (un archivo): fases implementadas,
   flags nuevos + default, controles de UI agregados, y lo que quedó pendiente/bloqueado. Enlazá `[[...]]`.
8. **Commitear lo implementado.** Hacé el commit en la rama de trabajo según "Commit tras implementar"
   (mensaje con prefijo `plan-<NN>` + trailer de co-autoría). **No `push`** salvo pedido del operador.
9. **Cerrar con handoff.** Devolvé: rama, hash del commit, reporte por fase con comandos+resultados reales,
   resumen de 6 líneas, y lo pendiente.

## Delegación y costo

Delegá el grueso al subagente `StackyArchitectaUltraEficientCode` (o `stacky-agents-architect`) con el
"Prompt para el implementador". Conciencia de costo extrema: scope cerrado, exploración mínima, subagente
Haiku solo si hay fan-out real. **PERO la verificación final (correr los tests y leer el resultado real)
hacela vos, el orquestador, en el hilo principal** — no confíes en un "pasó todo" reportado sin el output:
es justo donde nacen los falsos verdes. Si el subagente no está disponible, ejecutá los pasos inline con
el mismo prompt.

## Prompt para el implementador

```text
ROL: Sos StackyArchitectaUltraEficientCode implementando un plan ya escrito de Stacky Agents. Senior, TDD,
conciencia de costo extrema (UltraCode): scope cerrado, exploración mínima, subagente Haiku solo si hay
fan-out real. No improvisás arquitectura: el plan ya decidió; vos lo construís fiel y verificable.

CONTEXTO: Te paso la ruta del plan objetivo `Stacky Agents/docs/<NN>_PLAN_*.md`. Leelo COMPLETO.

PASO 0 — PRE-FLIGHT: confirmá que el plan tiene fases F0..Fn, archivos/símbolos exactos, tests nombrados
con comando y criterios binarios. Si algún paso es ambiguo (habría que INFERIR), PARÁ y reportá que el
plan no está listo para implementar (que el operador lo pase por criticar-y-mejorar-plan). No implementes
basura sobre un plan vago.

PASO 1 — CONFIG POR UI (regla dura): por cada flag/parámetro del plan que el OPERADOR deba activar o
ajustar, NO basta una env var: tiene que quedar activable/editable desde la UI. Wiring = backend que lee
el valor + endpoint leer/setear + control en el frontend, REUSANDO una superficie existente
(api/client_profile.py + su panel, el modal de settings de Claude Code, o el panel de flags del arnés
services/harness_flags.py). Default seguro (off). Solo un kill-switch puramente interno que el operador
nunca toca puede quedar env-only; ante la duda, va a la UI. Listá qué controles de UI vas a agregar antes
de codear.

PASO 2 — IMPLEMENTAR FASE POR FASE (TDD, en orden de dependencia):
- Por CADA fase: (a) test nombrado del plan PRIMERO; (b) código mínimo (archivos/símbolos EXACTOS del
  plan; flags default off); (c) CORRÉ el test de esa fase de verdad; (d) verificá el criterio binario.
- Tests backend (por archivo, venv del repo):
  Stacky Agents/backend/.venv/Scripts/python.exe -m pytest "Stacky Agents/backend/tests/<archivo>.py" -q
- Frontend (si tocaste UI): en Stacky Agents/frontend/ -> npx tsc --noEmit (0 errores). Vitest NO está
  instalado: no corras tests JS.
- CERO FALSOS VERDES: un test que no corriste no está verde. Si falla y no lo podés arreglar, marcá la
  fase BLOQUEADA con el OUTPUT REAL del test; no comentes el test, no hagas skip/xfail silencioso, no
  declares hecho lo no verificado. (En este repo ya hubo "falsos verdes": un 500 declarado arreglado que
  seguía roto. No repitas eso.)

PASO 3 — RIELES DUROS (respetalos en el código que escribís):
- 3 runtimes con paridad o fallback explícito (nada atado a un runtime; ojo style_memory copilot-only).
- Cero trabajo extra al operador (default off, sin pasos manuales nuevos; configurable por UI ≠ obligatorio
  configurar).
- Human-in-the-loop (sin autonomía proactiva). Mono-operador sin auth (sin RBAC). No degradar; reusar lo
  existente (memoria colaborativa, flags del arnés, telemetría, gates golden, client_profile).

PASO 4 — VERIFICACIÓN GLOBAL: corré los archivos de test de TODAS las fases tocadas + tsc si hubo UI.
Confirmá el DoD del plan. Reportá conteo real (X passed / Y failed por archivo).

PASO 5 — COMMIT: tras la verificación, hacé el commit en la rama de trabajo:
  git add -A && git commit -m "feat(plan-<NN>): <slug> — F0..Fn implementadas" (con co-autoría).
El mensaje DEBE terminar con: Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
NO hagas git push (solo si el operador lo pide). NUNCA --no-verify. Si quedaron fases BLOQUEADAS,
commiteá lo verde y dejalo claro en el mensaje.

COSTO/FORMA: salida densa, sin relleno. El único contenido largo permitido es el diff/código necesario.

ENTREGABLE: por fase -> IMPLEMENTADA/PARCIAL/BLOQUEADA + comando de test corrido + resultado real;
controles de UI agregados; lista de flags + default; hash del commit; pendientes/bloqueos; resumen de 6 líneas.
```

## Checklist de aceptación

- [ ] El plan objetivo se resolvió dinámicamente (argumento del operador o `NN_PLAN_*` de número más alto);
      el número NO se hardcodeó.
- [ ] Pre-flight: el plan tenía fases/archivos/símbolos/tests/criterios binarios; si era ambiguo, NO se
      implementó y se rebotó a `criticar-y-mejorar-plan`.
- [ ] **Toda flag/config que el operador deba setear quedó activable/editable desde la UI** (backend +
      endpoint + control de frontend, reusando una superficie existente), con default seguro off. Solo
      kill-switches internos quedaron env-only, justificados.
- [ ] Se trabajó en una rama (no en `main`).
- [ ] Tras la implementación se hizo un commit en la rama (mensaje `plan-<NN>` + trailer de co-autoría
      `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`, sin `--no-verify`); el `push`
      NO se hizo salvo pedido del operador; el hash quedó en el reporte.
- [ ] Cada fase se implementó test-first y su test se CORRIÓ de verdad con
      `…/.venv/Scripts/python.exe -m pytest <archivo> -q`; el reporte trae el resultado real (pass/fail),
      no un "debería pasar".
- [ ] Si se tocó UI, `npx tsc --noEmit` terminó con 0 errores.
- [ ] CERO falsos verdes: lo que falló o se saltó se reportó como PARCIAL/BLOQUEADA con el output real;
      nada se declaró hecho sin verificar; no hubo skip/xfail silencioso.
- [ ] La implementación respeta los rieles: 3 runtimes con fallback, cero trabajo extra al operador,
      human-in-the-loop, mono-operador sin auth, no degradar, reuso.
- [ ] Se actualizó/creó la memoria `plan-<NN>-status` (un archivo, sin duplicar) con fases, flags+default,
      controles de UI y pendientes; con enlaces `[[...]]`.
- [ ] El trabajo pesado se delegó al subagente implementador (o inline con el mismo prompt), pero la
      verificación final (correr tests + leer output real) la hizo el orquestador.
- [ ] Se devolvió el reporte por fase + resumen de 6 líneas + hash del commit + handoff con lo pendiente.
