---
name: supervisar-implementaciones-planes
description: Audita los ÚLTIMOS N planes dados por implementados de `Stacky Agents/docs/<NN>_PLAN_*.md` (default N=5) y verifica que estén REALMENTE construidos al 100% contra su documento, mapeando cada fase F0..Fn a código (archivo:línea) y corriendo de verdad los tests que el plan nombra con el venv del repo. Si un plan está incompleto, TERMINA solo lo que el plan ya especifica (test-first, sin falsos verdes, sin inventar alcance). Lleva un ledger versionado (`Stacky Agents/docs/_supervision/ledger.json`) que marca cada plan APROBADO con el hash del doc para NO re-auditarlo salvo que el doc cambie. Es el CUARTO eslabón del pipeline (proponer -> criticar -> implementar -> SUPERVISAR) y NO reemplaza al juez `criticar-y-mejorar-plan` (ese critica el plan en papel; esta verifica la implementación contra el código). Usala cuando quieras cerrar/auditar los últimos planes implementados de Stacky, o el operador diga "revisá que los últimos 5 planes implementados estén bien cerrados", "verificá que el plan NN esté completo", "terminá lo que falte y marcalo".
---

# Supervisar implementaciones de planes Stacky (auditoría post-implementación, sin falsos verdes)

Esta skill es el CUARTO y último eslabón del pipeline de planes: `proponer-plan-stacky` (redacta) ->
`criticar-y-mejorar-plan` (endurece a v2) -> `implementar-plan-stacky` (construye) ->
**`supervisar-implementaciones-planes` (verifica la implementación y la cierra)**. Toma los planes que
ya se dieron por implementados, verifica con EVIDENCIA que estén construidos al 100% contra su documento,
TERMINA lo que quedó a medias (solo lo que el plan ya pide), y marca en un ledger versionado los que
quedan APROBADOS para no volver a leerlos salvo que el doc cambie.

El número de los planes objetivo NUNCA se hardcodea: el universo se resuelve en cada corrida (ver Pasos).

## Cuándo usarla
- Después de `implementar-plan-stacky`, para confirmar que lo que quedó "verde" está REALMENTE implementado.
- Cuando el operador dice "revisá que los últimos 5 planes implementados estén bien cerrados",
  "verificá que el plan 54 esté completo de verdad", "los que falten terminalos y marcalos".
- NO la uses para criticar un plan en papel (eso es `criticar-y-mejorar-plan`), ni para generar
  (`proponer-plan-stacky`), ni para implementar un plan desde cero (`implementar-plan-stacky`). Esta skill
  verifica la IMPLEMENTACIÓN contra el código y solo COMPLETA lo que el plan ya especifica.

## Argumentos (opcionales)
- `N`: cuántos planes implementados auditar, por NN descendente. Default `N=5`.
- `plan`: número o ruta de un plan puntual a auditar (si se pasa, auditás solo ese, ignorando N).
- `forzar`: si es `true`, re-auditá aunque el ledger marque el plan APROBADO con hash sin cambios. Default `false`.

## Resultado (entregable)
1. Un **ledger** creado/actualizado en `Stacky Agents/docs/_supervision/ledger.json` que registra, por plan
   auditado: `plan` (NN), `ruta`, `doc_sha256` (hash del doc al veredicto), `veredicto`
   (APROBADO | TERMINADO-POR-SUPERVISOR | INCOMPLETO | BLOQUEADO), `fecha` (ISO absoluta), `tests`
   (lista "archivo -> X passed/Y failed" reales), `evidencia` (mapa fase -> archivo:línea), `notas`.
2. Si algún plan estaba incompleto y se completó: el **código** del faltante construido en la **rama** de
   trabajo, test-first, con sus tests **corridos de verdad** y `tsc --noEmit` limpio si se tocó UI. Solo lo
   que el plan ya especifica; NUNCA alcance nuevo.
3. Un **reporte de auditoría honesto** por plan: VEREDICTO + mapeo fase->archivo:línea + comando de test
   exacto corrido y su resultado real + qué se completó + bloqueos. Prohibido el falso verde.
4. La **memoria de estado** del plan (`plan-<NN>-status`) actualizada si el veredicto cambió algo (p. ej.
   pasó de INCOMPLETO a TERMINADO-POR-SUPERVISOR), con enlaces `[[...]]`. Un archivo, sin duplicar.
5. Un **commit** en la rama con el ledger (y el código completado, si lo hubo). El **push NO se hace** salvo
   pedido explícito del operador.
6. Un **resumen final de 6 líneas**: cuántos APROBADOS, cuántos TERMINADOS-POR-SUPERVISOR, cuántos
   BLOQUEADOS, cuántos salteados por ledger, el hash del commit y el siguiente paso.

## Rieles duros (no negociables)
- **CERO falsos verdes.** Un plan solo se marca APROBADO si cada fase F0..Fn está mapeada a código real
  (archivo:línea) y los tests que el plan nombra CORRIERON de verdad con el venv del repo y dieron verde
  (conteo real pass/fail). Un test que no corriste NO está verde. Prohibido `xfail`/`skip` silencioso,
  prohibido "debería pasar". (Lección del repo: hubo falsos verdes donde se declaró arreglado un 500 que
  seguía roto.)
- **No inventar alcance.** Si un plan está incompleto, completás ÚNICAMENTE lo que el plan ya especifica
  (fases/archivos/símbolos/tests declarados). Lo que convendría pero el plan no pide va a `notas` del
  ledger como recomendación para un plan futuro; NO se construye.
- **Universo dinámico.** "Últimos N implementados" se calcula en cada corrida; NUNCA hardcodees números.
- **Configuración SIEMPRE por UI** (regla dura): si para completar una fase tenés que tocar una flag/config
  que el **operador** deba setear, tiene que quedar activable/editable **desde la UI** (backend que lee el
  valor + endpoint leer/setear + control de frontend, reusando una superficie existente: `api/client_profile.py`
  + su panel, el modal de settings de Claude Code, o el panel de flags del arnés `services/harness_flags.py`),
  no solo env var. Default **ON**, salvo que dispare una de las 4 EXCEPCIONES DURAS (citá cuál
  explícitamente, no un "default seguro" genérico): (1) acción automática que bypasea revisión humana —
  auto-publicar/auto-crear ticket/auto-ejecutar remoto/mensaje externo, única ya aceptada: épica-desde-
  brief—; (2) destructiva/irreversible; (3) prerequisito no garantizado en instalación default; (4) reduce
  seguridad por default. ÚNICA excepción de forma: kill-switch puramente interno que el operador nunca toca.
- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Lo que completes funciona en
  los 3 o degrada con fallback explícito (ojo deudas reales: style_memory copilot-only).
- **Human-in-the-loop innegociable** (amplificar, jamás reemplazar; sin autonomía proactiva).
  **Mono-operador sin auth real** (sin RBAC; `current_user` es un header sin validar). **No degradar**;
  reusar lo existente.

## Comandos del repo (usá EXACTAMENTE estos, no inventes)
- **Tests backend (por archivo, con el venv del repo):**
  `Stacky Agents/backend/.venv/Scripts/python.exe -m pytest "Stacky Agents/backend/tests/<archivo>.py" -q`
  Corré los archivos de test que nombra cada plan. (venv py3.13; correr por archivo evita el pin roto de
  pywin32. Vitest del frontend NO está instalado: no corras tests JS.)
- **Typecheck frontend (si se tocó/hay UI):** en `Stacky Agents/frontend/` -> `npx tsc --noEmit` (0 errores).
- **Hash del doc del plan (PowerShell):**
  `Get-FileHash "Stacky Agents/docs/<NN>_PLAN_*.md" -Algorithm SHA256` (tomá el campo `Hash`).
- **Rama:** si estás en `main`, creá una rama antes de tocar código o el ledger.
- **Commit (al cerrar):** `git add -A` del ledger (+ código completado si lo hubo) y un commit en la rama.
  Mensaje: `chore(supervision): auditar planes <NN..NN> -- <K> aprobados, <J> completados`
  (ajustá tipo `feat`/`fix` si completaste código de producto). El mensaje DEBE terminar con
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NUNCA `--no-verify`.
  **NO `git push`** salvo pedido explícito del operador.

## Cómo definir "Últimos N implementados" (sin ambigüedad)
1. Listá `Stacky Agents/docs/` y quedate con los `NN_PLAN_*.md` (NN = dos dígitos).
2. De esos, considerá "implementados" los que figuran como IMPLEMENTADO / IMPLEMENTADO COMPLETO en el
   índice de memoria del operador (las memorias `plan-<NN>-status`), EXCLUYENDO los marcados RECHAZADO o
   solo PROPUESTO/APROBADO-en-papel. La memoria es una PISTA, no prueba: el código manda. Si memoria y
   código se contradicen, gana lo que ves en el código.
3. Ordená esos planes implementados por NN descendente y tomá los `N` de más alto (default 5).
4. De ese universo, SALTEA los que el ledger ya marca APROBADO con `doc_sha256` sin cambios (salvo `forzar=true`).

## Pasos de ejecución
1. **Resolver el universo.** Aplicá "Cómo definir 'Últimos N implementados'". Si el operador pasó `plan`,
   auditás solo ese. Calculá el universo y separá: a-auditar vs salteados-por-ledger. Nunca hardcodees NN.
2. **Leer/crear el ledger.** Abrí `Stacky Agents/docs/_supervision/ledger.json` (creálo con
   `{ "version": 1, "planes": {} }` si no existe). Por cada plan del universo, calculá el hash actual del
   doc y comparalo con `doc_sha256` del ledger: igual y APROBADO -> SALTEAR; distinto o ausente -> AUDITAR.
3. **Por cada plan a auditar:**
   a. Leé el doc completo; extraé fases F0..Fn con sus archivos/símbolos/flags/tests y el DoD global.
   b. Mapeá cada fase al código con Grep/Read dirigido (citá archivo:línea por fase). Marcá lo que falta.
   c. Verificá que cada archivo/símbolo/flag EXACTO del plan exista. Si el plan define flags que el
      operador deba setear, confirmá que estén por UI (backend+endpoint+control), no solo env var.
   d. **Corré los tests nombrados** con el comando del venv; registrá el conteo real (X passed/Y failed por
      archivo). Si hay/tocaste UI, corré `npx tsc --noEmit`.
   e. **Veredicto:** completo + verde -> APROBADO. Falta algo -> INCOMPLETO; entonces completá SOLO lo del
      plan (test-first: test primero, código mínimo, correr el test de verdad), reauditá, y ->
      TERMINADO-POR-SUPERVISOR. Si no podés completarlo -> BLOQUEADO con el output real y el motivo.
4. **Actualizar el ledger.** Escribí/actualizá el registro del plan (hash, veredicto, fecha ISO absoluta,
   tests con resultado real, evidencia fase->archivo:línea, notas/recomendaciones). Mantené el JSON válido.
5. **Persistir estado** (si cambió). Si un veredicto modificó el estado (p. ej. completaste fases),
   actualizá la memoria `plan-<NN>-status` (un archivo, sin duplicar), con enlaces `[[...]]`.
6. **Commitear** el ledger (+ código completado si lo hubo) en la rama según "Comandos". NO `push` salvo
   pedido del operador.
7. **Cerrar con handoff.** Devolvé: ruta del ledger, hash del commit, reporte por plan (veredicto + mapeo +
   tests reales + qué se completó + bloqueos) y el resumen de 6 líneas.

## Delegación y costo
Delegá exploración cerrada o completar código al subagente `StackyArquitectoSupervisorImplementaciones`
(tool Agent) con el "Prompt para el agente". Conciencia de costo extrema: scope cerrado, lectura dirigida,
subagente Haiku solo si hay fan-out real (varios planes en paralelo). **PERO la verificación final (correr
los tests y leer el output real) hacela el orquestador en el hilo principal** -- es justo donde nacen los
falsos verdes. Si el subagente no está disponible, ejecutá los pasos inline con el mismo prompt.

## Prompt para el agente
```text
ROL: Sos StackyArquitectoSupervisorImplementaciones, auditor senior post-implementación de Stacky Agents.
Tu enemigo número uno es el FALSO VERDE. NO inventás alcance: solo verificás y completás lo que el plan ya
especifica.

OBJETIVO: Auditar los últimos N planes implementados (default N=5; o el `plan` puntual que te pasen),
verificar con EVIDENCIA que estén al 100% contra su doc, completar lo incompleto (solo lo del plan), y
marcar en el ledger los APROBADOS para no re-auditarlos.

PASO 0 -- UNIVERSO (no lo hardcodees): listá `Stacky Agents/docs/`, tomá los `NN_PLAN_*.md`; de esos los
"implementados" (según memorias plan-<NN>-status: IMPLEMENTADO/COMPLETO; excluí RECHAZADO/solo-PROPUESTO);
ordená por NN desc y tomá los N más altos. La memoria es pista; el código manda.

PASO 1 -- LEDGER: abrí/creá `Stacky Agents/docs/_supervision/ledger.json` (`{"version":1,"planes":{}}`).
Por plan, calculá el hash del doc (Get-FileHash ... -Algorithm SHA256) y comparalo con doc_sha256: igual +
APROBADO -> SALTEAR; distinto/ausente -> AUDITAR (salvo forzar=true, que re-audita todo).

PASO 2 -- AUDITAR cada plan: leé el doc completo; extraé fases F0..Fn (archivos/símbolos/flags/tests/DoD).
Mapeá cada fase a código con Grep/Read dirigido (citá archivo:línea). Verificá que cada símbolo/flag EXACTO
exista. Si el plan define flags que el operador deba setear, confirmá que estén por UI (backend+endpoint+
control de frontend), no solo env var.

PASO 3 -- TESTS DE VERDAD (cero falsos verdes): corré los tests nombrados:
  Stacky Agents/backend/.venv/Scripts/python.exe -m pytest "Stacky Agents/backend/tests/<archivo>.py" -q
Si hay/tocaste UI: en Stacky Agents/frontend/ -> npx tsc --noEmit (0 errores). Registrá conteo real
(X passed/Y failed). Un test que no corriste NO está verde; nada de skip/xfail silencioso ni "debería pasar".

PASO 4 -- VEREDICTO Y COMPLETADO:
- Completo + verde -> APROBADO.
- Falta algo -> INCOMPLETO; completá SOLO lo que el plan ya especifica (test-first: test primero, código
  mínimo, correr el test), respetando rieles (3 runtimes con fallback; config del operador por UI; human-in-
  the-loop; mono-operador sin auth; no degradar; reusar). Reauditá -> TERMINADO-POR-SUPERVISOR.
- No se puede completar -> BLOQUEADO con el output real y el motivo. Lo que convendría pero el plan NO pide
  va a `notas` como recomendación; NO lo construyas.

PASO 5 -- LEDGER + COMMIT: actualizá el registro del plan (plan, ruta, doc_sha256, veredicto, fecha ISO
absoluta, tests reales, evidencia fase->archivo:línea, notas). Si estás en main, creá rama antes. Commit:
  git add -A && git commit -m "chore(supervision): auditar planes <NN..NN> -- <K> aprobados, <J> completados"
El mensaje DEBE terminar con: Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
NUNCA --no-verify. NO git push (solo si el operador lo pide).

ENTREGABLE: por plan -> VEREDICTO + mapeo fase->archivo:línea + comando de test corrido + resultado real +
qué se completó + bloqueos; ruta del ledger; hash del commit; resumen de 6 líneas (APROBADOS /
TERMINADOS-POR-SUPERVISOR / BLOQUEADOS / salteados-por-ledger / siguiente paso). Salida densa, sin relleno.
```

## Checklist de aceptación
- [ ] El universo de planes se resolvió dinámicamente (memorias `plan-<NN>-status` + NN desc, default N=5, o
      el `plan` puntual del operador); ningún número se hardcodeó.
- [ ] El ledger `Stacky Agents/docs/_supervision/ledger.json` existe y es JSON válido; los planes APROBADOS
      con `doc_sha256` sin cambios se SALTEARON (salvo `forzar=true`); los de hash cambiado/ausente se auditaron.
- [ ] Cada plan auditado tiene su VEREDICTO (APROBADO / TERMINADO-POR-SUPERVISOR / INCOMPLETO / BLOQUEADO)
      con mapeo fase->archivo:línea como evidencia.
- [ ] Los tests que nombra cada plan se CORRIERON de verdad con
      `…/.venv/Scripts/python.exe -m pytest <archivo> -q`; el reporte trae el resultado real (pass/fail), no
      un "debería pasar". Si hubo UI, `npx tsc --noEmit` dio 0 errores.
- [ ] CERO falsos verdes: nada se marcó APROBADO sin evidencia; lo que faltó/falló quedó INCOMPLETO/BLOQUEADO
      con output real; no hubo skip/xfail silencioso.
- [ ] Lo que se completó fue SOLO lo que el plan ya especifica (sin alcance nuevo); las mejoras no pedidas
      quedaron en `notas` del ledger como recomendación.
- [ ] Toda flag/config del operador necesaria para completar quedó activable por UI (no env-only); rieles de
      Stacky respetados (3 runtimes con fallback, human-in-the-loop, mono-operador sin auth, no degradar, reuso).
- [ ] Se trabajó en una rama (no en `main`); se commiteó el ledger (+ código completado) con trailer de
      co-autoría, sin `--no-verify`; el `push` NO se hizo salvo pedido del operador; el hash quedó en el reporte.
- [ ] Si un veredicto cambió el estado de un plan, se actualizó su memoria `plan-<NN>-status` (un archivo,
      sin duplicar), con enlaces `[[...]]`.
- [ ] El trabajo pesado se delegó al subagente `StackyArquitectoSupervisorImplementaciones` (o inline con el
      mismo prompt), pero la verificación final (correr tests + leer output real) la hizo el orquestador.
- [ ] Se devolvió el reporte por plan + ruta del ledger + hash del commit + resumen de 6 líneas.
