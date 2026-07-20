# Plan 197 — UX: hoja de ruta de la serie 164-194 — orden canónico, mapa de colisiones, módulos comunes y gates compuestos

- **Versión:** v2 (CRITICADO — juez adversarial StackyArchitectaUltraEficientCode; veredicto v1: **RECHAZADO** por C1/C2/C3, reescrito in place como superset)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
- **Serie:** UX — capstone de coordinación (precedentes en la casa: plan 184 = hoja de ruta DB Compare; plan 195 = hoja de ruta DevOps 186-193)
- **Planes en scope (10, todos CRITICADOS v2; ESTADO 2026-07-18: 164 F1 y 165 F1-F3 YA implementados — commits 9a57c378 y f49588eb→8619acfd; los otros 8 sin implementar):** 164 (diálogo canónico), 165 (contrato URL), 172 (teclado primero), 173 (vistas guardadas), 174 (rendimiento percibido), 175 (peek + menú contextual), 185 (undo universal), 187 (selección múltiple + lote), 192 (resiliencia de conexión), 194 (portapapeles universal).
- **Periféricos SOLO como restricción de orden (no se re-planifican):** 150 y 151 (IMPLEMENTADOS — `OnboardingTour.tsx` existe en `frontend/src/components/`, verificado 2026-07-18: sus líneas ya movieron anclas), 152 (centro notificaciones — su GATE es 165 F1+F3), 156 (latido único — dueño nominal de `nativeDialogByFile`, ver §6.6; coexistencia con 192 declarada en 192 §3 D11), 159 (catálogo modelos — lo consume el 196, ajeno a esta serie).

**CHANGELOG v1 → v2 (crítica adversarial 2026-07-18; todo re-verificado contra disco/docs corriendo los comandos de verdad):**

- **C1 (BLOQUEANTE — §7bis G4a):** el detector de flags duplicadas de la v1 (`grep -o "STACKY_[A-Z_]*_ENABLED" | uniq -d`) da DECENAS de falsos duplicados con el árbol limpio de HOY (toda flag aparece legítimamente varias veces en `harness_flags.py`: `key=`, categorías, `requires=`, comentarios — verificado ejecutándolo). El gate §7(a) habría bloqueado la serie desde el primer plan. v2: el patrón mira SOLO definiciones `key="STACKY_..."` (217 definiciones, 0 duplicadas — verificado).
- **C2 (BLOQUEANTE — gate S2, §5.3, §6.5, §8.6, §8.8):** la v1 trataba `askConfirm` como API del 164. FALSO: el 164 exporta `useConfirm`/`useAlert`/`useTextPrompt` + `Dialog`/`ConfirmDialog`/`AlertDialog`/`PromptDialog` (164:136 barrel, 164:267; su propio gate grepea `useTextPrompt`, 164:367). `askConfirm` es el campo del ctx/gateway del **175** (175:498 `askConfirm: ConfirmFn`; su `confirmGateway` delega en `useConfirm()` del 164, 175:174 y 175:445) y jerga del 185 (185:236). El gate S2 de la v1 (`grep -c "askConfirm" ui/index.ts` → `>= 1`) habría dado 0 SIEMPRE. v2: S2 grepea `useConfirm`; renombrado en §5.3, §6.5, §8.6(d), §8.8(c); entrada nueva de glosario.
- **C3 (BLOQUEANTE — §7bis G4b):** duplicado REAL preexistente que la v1 no detectó: `tests/test_harness_flags.py` está registrado DOS veces en `run_harness_tests.sh` (`:22` y `:340`) y DOS veces en `run_harness_tests.ps1` (`:15` y `:296`) — el gotcha del merge silencioso YA ocurrió en los runners. G4b daba rojo en el primer uso sin instrucción de saneo. v2: Gate 0.7 (dedup quirúrgico único, anotado en §9).
- **C4 (IMPORTANTE — §7bis G1):** la v1 usaba `python` del PATH (hoy **3.11.9** — exactamente la versión del venv que §4.1 PROHÍBE) y compilaba `backend/` entero incluidos AMBOS venvs (site-packages ajenos: lento y frágil). v2: G1 usa el canónico `.venv\Scripts\python.exe` con exclusión `-x "(\.venv|venv)"`.
- **C5 (IMPORTANTE — KPI-2/G7):** el gate vigilaba solo `services/*.ts`, pero `useUiPerfFlags` (174) vive en **`hooks/`** (174:228), y los paneles de ADMINISTRACIÓN usan `HarnessFlags.list` legítimamente (`components/HarnessFlagsPanel.tsx:360`, `pages/memory/MemoryConfigPanel.tsx:26`). v2: KPI-2 y G7 barren `src/` entero con allowlist explícita.
- **C6 (IMPORTANTE — §6.1):** la v1 llamaba `flagEnabledFrom` al "parser del 187"; el nombre REAL es `resolveBulkActionsEnabled` (187:187). v2: el wrapper conserva ESE export (implementado sobre `flagGate.flagEnabledFrom`) para que `bulkFlags.test.ts` quede intacto de verdad.
- **C7 (IMPORTANTE — §6.1):** faltaba el contrato de tests de `flagGate.ts` (el módulo más compartido de la serie): "con test propio" sin casos = ambigüedad para modelo menor. v2: casos enumerados (5 del 187 K6 generalizados + 2 de cache).
- **C8 (MENOR — §6.6/§8.3):** la v1 presentaba como "regla 197" lo que el doc 164 YA codificó en su pre-check C5 (164:407-409: si el grep da 0, "crear la dimensión ACÁ con EXACTAMENTE la spec del 156-F6"). v2: se cita la fuente; el delta queda como confirmación, no como corrección.
- **C9 (IMPORTANTE — colisión NO mapeada) → [ADICIÓN ARQUITECTO A1] §6.11:** la serie monta 3 capas flotantes nuevas (overlay "?" 172, `UndoToastHost` 185, `ConnectionBanner` 192, menú contextual 175) sobre un viewport que ya tiene Toast local por componente (164:120: SIN provider global), `OnboardingTour` (151) y `HealthBanner`/CommandPalette — y NINGÚN doc fija posiciones/stacking. v2: tabla canónica de hosts flotantes y regla de z-index.
- **C10 (MENOR — §6.7):** faltaba el cruce "165 aterriza DESPUÉS de 173": inofensivo porque el doc 173 es autocondicional (173:495: grep `useLocalStorageState` decide la rama), pero la matriz debe decirlo para la sesión paralela. v2: fila agregada.
- **C11 (MENOR — §3.1):** la regla de precedencia no tenía ejemplo resuelto. v2: ejemplo askConfirm/useConfirm (el caso C2 real).
- **[ADICIÓN ARQUITECTO A2] §6.8:** contrato congelado `visibleIds/rango-Shift = dataset filtrado en memoria, NUNCA la ventana del virtualizador`. Hoy NO hay conflicto real (verificado: 174 KPI-3 virtualiza SOLO LogsPanel/DiffList; History/ReviewInbox reciben solo prefetch+keepPreviousData, 174:28) — se congela para que ningún plan futuro que virtualice tablas con selección (187) o peek (175) rompa sus contratos en silencio.
- **PASE DE COHERENCIA DE SERIE 2026-07-18 (C-1/C-2/R-1 — solo integración, sin re-planificar features):** (C-1) 164 F1 y 165 F1-F3 marcados IMPLEMENTADOS en §1/§5/§9/§12 (commits 9a57c378 y f49588eb→8619acfd) — su casilla pasa a VERIFICAR gate satisfecho. (C-2) §6.1 partido en DOS lectores mecánicamente verdaderos: cockpit 172/173/174/175 leen `/api/diag/health` (`useHealthFlags`, Parte A — preserva el KPI-8 del 172 y el presupuesto 0-req del 174); `flagGate.ts`/`HarnessFlags.list` (Parte B) lo crea el **194** (no el 172) y lo usan 185/187/192/194 (185 también lee `HarnessFlags.list`, 185:173-175); §5/§8/§11/§12 alineados. La premisa de flag-reader del C5 queda superada por esta separación. (R-1) nueva §6.12: `["ticket-detail", id]` es contrato PROPIO del 175 (el 174 prefetchea solo ejecuciones); las queryKeys de ejecución siguen congeladas con el 174.

---

## 1. Título, objetivo y KPIs

**Objetivo (1 párrafo).** Hoy existen 10 planes UX hermanos CRITICADOS v2 y sin implementar que, en orden ingenuo, VAN a chocar entre sí: `ExecutionHistoryPage.tsx` la tocan SEIS (165 F2/F3, 172 F4/F6, 173 F3/F4/F5, 174 F3/F4, 175 F2/F3/F4, 187 F5), `TicketBoard.tsx` CINCO (164 F2/F3/F4, 172 F5, 173 F3, 175 F2, 185 F3), `App.tsx` CUATRO (165 F3, 172 F2, 185 F2, 192 F3), `ReviewInboxPage.tsx` TRES (172 F4, 174 F3, 187 F4); TRES planes replican el mismo lector de flag frontend (187 `bulkFlags.ts`, 192 `connectionFlags.ts`, 194 su equivalente) porque cada uno se escribió autocontenido; DOS definen clipboard propio (175 `services/clipboard.ts`, 187 `copySelectedLinks` inline) mientras 194 crea el canónico `copyService.ts` con ratchet anti-`writeText`; y TRES agregan listeners `keydown` directos (185 Ctrl+Z, 187 Escape, 175 menú) mientras 172 crea el registry central que debería absorber los globales. Además, CINCO docs prescriben un intérprete backend equivocado o inexistente (§8.11 — verificado en disco). Este plan es la hoja de ruta ejecutable que lo previene: **orden canónico** con justificación por arista, **mapa de colisiones por archivo y símbolo** con regla por celda, **módulos comunes** con un creador y N consumidores declarados, **notas de migración por plan** (el delta exacto que corrige lo que quedó obsoleto en cada doc, sin reescribirlos), y **gates compuestos binarios** entre etapas. Cero código de producto acá.

**KPIs (binarios, verificables al ejecutar la ruta; comandos con cwd explícito):**

| KPI | Criterio binario | Comando (shell) |
|-----|------------------|-----------------|
| KPI-1 | Gate 0 cumplido ANTES del primer plan: intérprete canónico confirmado, baselines anotados en §9 | §4 completo, resultados en la tabla §9 |
| KPI-2 | Al cierre: `flagGate.ts` es el ÚNICO lector de flags de FEATURE que llama `HarnessFlags.list` en TODO `src/` (C5: cubre `services/` Y `hooks/` — `useUiPerfFlags` vive en `hooks/`, 174:228). Allowlist cerrada: `services/flagGate.ts` + los 2 paneles de ADMINISTRACIÓN (`components/HarnessFlagsPanel.tsx:360`, `pages/memory/MemoryConfigPanel.tsx:26` — hacen list+update del panel, no son lectores de feature) + tests | Git Bash, cwd `Stacky Agents/frontend`: `grep -rln "HarnessFlags.list" src --include=*.ts --include=*.tsx \| grep -v "flagGate" \| grep -v "HarnessFlagsPanel" \| grep -v "MemoryConfigPanel" \| grep -v ".test." \| wc -l` → `0` |
| KPI-3 | Al cierre: cero `navigator.clipboard` fuera del canónico | Git Bash, cwd `Stacky Agents/frontend`: `grep -rn "navigator.clipboard" src --include=*.ts --include=*.tsx | grep -v "copyService" | grep -v ".test." | wc -l` → `0` |
| KPI-4 | Al cierre: `App.tsx` sin keydown directo y conteo global bajo techo con lista nominal §5.4 | Git Bash, cwd `Stacky Agents/frontend`: `grep -c 'addEventListener("keydown"' src/App.tsx` → `0` **y** `grep -rn 'addEventListener("keydown"' src | wc -l` → `<= 8` |
| KPI-5 | Tras CADA plan mergeado, el gate compuesto §7 pasó y quedó anotado en §9 | §7 (script + tsc + tests por archivo) |
| KPI-6 | Los 10 planes implementados en el orden canónico §5, o con desvío ANOTADO en §9 aplicando la matriz de escenarios §6.7 | tabla §9 completa |

**Ganancia robusta:** la serie completa (10 planes, ~30 archivos de test nuevos) se vuelve implementable sin pisadas, sin triple implementación del lector de flags, sin dos clipboards, y sin re-migrar listeners — el impuesto que la serie 144-149 pagó con una sesión entera de auditoría.

**Onboarding casi nulo:** es un documento; el implementador (humano o modelo menor vía `implementar-plan-stacky`) lo sigue paso a paso junto al doc del plan que toque.

---

## 2. Por qué ahora / gap que cierra

1. Los 10 planes nacieron en dos tandas (172-175 el 2026-07-18 en loop propio; 164/165 antes; 185/187/192/194 en loop paralelo) y CADA UNO se escribió asumiendo que los otros NO estaban implementados: 192 §3 D9 dice literalmente que duplica el patrón de flag del 187 "de forma AUTOCONTENIDA (los planes 185/187 NO están implementados: PROHIBIDO importar código de ellos)" (192:155); 185 §2 pone el Ctrl+Z como "listener directo sin dependencias" con nota de migrar al 172 "cuando exista" (185:180); 175 §4 declara fallback de deep-link literal "sin esperar al plan 165" (175:91-93); 194 §7.5 difiere el atajo de copiado al 172 (194:745). Implementarlos en orden arbitrario materializa TODOS los fallbacks a la vez y deja 3 lectores de flag, 2 clipboards y 3 listeners que después alguien tiene que consolidar.
2. El gotcha del **merge duplicado silencioso** (git 3-way no marca conflicto cuando dos ramas agregan la misma línea de cierre) ya mordió en la consolidación de 16 ramas del 2026-07-16, y las superficies compartidas de esta serie (`harness_flags.py`, `run_harness_tests.sh`/`.ps1`, montajes en `App.tsx`) son exactamente ese patrón.
3. Cinco docs de la serie llevan comandos de intérprete backend rotos o inconsistentes entre sí (§8.11): 172 KPI-7 y 173 F5 dicen `venv/Scripts/python.exe`; 174 §KPIs dice "usar `venv`"; 185 §3.6 dice `venv\Scripts\python.exe`; 187 K1/K2 ídem; y 194 G1 apunta a `N:\GIT\RS\STACKY\Stacky\.venv` que **NO existe**. Verificado en disco 2026-07-18: `Stacky Agents\backend\.venv\pyvenv.cfg` → `version = 3.13.5` (canónico) y `Stacky Agents\backend\venv\pyvenv.cfg` → `version = 3.11.9` (WIP ajeno untracked de la sesión paralela). Solo el 192 C1 lo dice bien.
4. 185 F0 registra su test backend "en `Stacky Agents/backend/tests/test_harness.py`" (185:51,63) — pero `HARNESS_TEST_FILES` vive en `backend/scripts/run_harness_tests.sh` (grep 2026-07-18: los únicos archivos backend con ese símbolo son `scripts/run_harness_tests.sh`, `tests/test_harness_ratchet_meta.py`, `tests/test_plan76_ratchet_byteidentical.py`, `tests/test_plan70_smoke_gitlab.py`, `tests/harness_ratchet_allowlist.txt`). Sin esta corrección, el meta-test rompe igual tras seguir el doc al pie de la letra.
5. Precedente de formato: planes 184 (DB Compare) y 195 (DevOps). Mismo problema, misma solución, otra serie.

---

## 3. Principios y guardarraíles

1. **Este plan NO agrega features NI reescribe los 10 planes.** Es capa 0 de integración. Cada plan se implementa según SU doc v2 **más** su nota de migración §8. **Regla de precedencia EXPLÍCITA:** en materia de INTEGRACIÓN (orden, módulos comunes, qué archivo registra qué, intérprete, convivencia de listeners/columnas/montajes) manda el 197; en materia de FEATURE (API interna, semántica, tests propios, KPIs propios) manda el plan origen. Discrepancia nueva → se anota en §9 y se resuelve ANTES de seguir. **Ejemplo resuelto (C11, caso real de esta crítica):** el nombre de la API de confirmación es FEATURE del 164 → manda su doc: `useConfirm`/`ConfirmDialog` (no "askConfirm", que otros docs usan como jerga); QUÉ canal usan 175/185 para confirmar es INTEGRACIÓN → manda el 197 (§6.5): el gateway del 175 y las conversiones del 185 se implementan sobre `useConfirm()` del 164.
2. **Cero flags nuevas.** Verificado y declarado: el 197 no crea ninguna flag; las flags de la serie las crean sus planes (172, 173, 174 con alta doble, 175, 185, 187, 192, 194 — cada F0 respectivo). Cero trabajo del operador.
3. **Human-in-the-loop: N/A** — este plan no toca runtime ni acciones de negocio; hereda el HITL de cada plan.
4. **3 runtimes: N/A-por-diseño global** — la serie es frontend + flags de arnés; ningún plan toca el camino de ejecución/publicación de Codex/Claude Code/Copilot (cada doc lo declara por fase).
5. **Paralelismo casi nulo.** A diferencia de la serie DevOps (grupos disjuntos), acá las superficies calientes se encadenan: **secuencial estricto** por defecto. Única excepción permitida: **192** puede implementarse en paralelo con cualquier plan que NO esté editando `App.tsx` en ese momento (192 solo comparte `App.tsx` — montaje del banner — y `client.ts` que nadie más toca; verificado por grep: `client.ts` aparece SOLO en el doc 192; el prefetch del 174 va por `queryClient`, no por `client.ts`).
6. **Tras cada merge, gates compuestos §7 SIEMPRE** — mitigación del gotcha del duplicado silencioso.
7. **Releer estado fresco antes de CADA plan:** `git log --oneline -10` + `git status` + pre-flight `git status -- "<ruta>"` por archivo caliente (la sesión paralela sigue activa; HOY hay 10 archivos de WIP ajeno en el árbol). Anclas de los docs por TEXTO, no por número de línea (150/151 ya movieron líneas: p.ej. el keydown de `App.tsx` que el doc 172 cita en `:173-200` hoy está en `App.tsx:212`).
8. **El implementador NO commitea archivos fuera de la lista de su fase** — staging quirúrgico por path explícito (regla heredada de los docs 165/173/187).

---

## 4. Gate 0 — saneo de entorno y baselines (ANTES de implementar cualquier plan)

Todos los resultados se anotan en §9 (KPI-1).

1. **Intérprete backend canónico (cierra la divergencia §2.3):** PowerShell, `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` → `.venv\Scripts\python.exe --version` → esperado `Python 3.13.5`. Regla para TODA la serie: los comandos pytest de los 10 planes se corren con `.venv\Scripts\python.exe` desde `Stacky Agents\backend`, POR ARCHIVO. **PROHIBIDO** usar `venv\Scripts\python.exe` (py3.11.9, WIP ajeno untracked: ni usarlo ni borrarlo ni recrearlo — es de la sesión paralela). **PROHIBIDO** buscar `.venv` en la raíz del repo (no existe; el comando del 194 G1 está roto, §8.10).
2. **Baseline meta-ratchet:** `.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q` → anotar verde o rojo-preexistente con causa (criterio NO-EMPEORAR para toda la serie: el fallo no debe mencionar archivos de tests de estos 10 planes).
3. **Baseline tsc:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` → `npx tsc --noEmit` → anotar verde o los errores preexistentes exactos.
4. **Baseline de listeners keydown (para KPI-4):** Git Bash, cwd frontend → `grep -rn 'addEventListener("keydown"' src` → anotar el conteo y la lista. Medido 2026-07-18: **6** (`App.tsx:212`, `hooks/useKeyboardShortcuts.ts:43` — hook sin caller real: solo `ShortcutsCheatsheet.tsx` importa su lista `DEFAULT_SHORTCUTS`, nadie invoca el hook —, `pages/PlansBoardPage.tsx:111`, `components/dbcompare/ObjectDrilldown.tsx:63`, `components/OnboardingTour.tsx:56`, `components/TeamManageDrawer.tsx:140`).
5. **Baseline de ratchets frontend existentes (los 4, por archivo):** `npx vitest run src/__tests__/uiDebtRatchet.test.ts`; ídem `formDebtRatchet.test.ts`, `motionDebtRatchet.test.ts`, `formatDebtRatchet.test.ts` → anotar estado (verde / rojo preexistente con causa; el uiDebtRatchet tiene deuda ajena conocida). Verificado 2026-07-18: los 4 tests y sus baselines existen en `src/__tests__/`; los ratchets de 185 (F5) y 194 (F5) NO existen aún y los crean esos planes.
6. **Baseline de superficie limpia (anti-sorpresa):** verificado 2026-07-18 y re-verificar en frío: `ExecutionHistoryPage.tsx` tiene **0** ocurrencias de checkbox; `Toast.tsx` NO tiene prop `action` (contrato actual `ToastState { variant, title?, body, correlationId? }`, `Toast.tsx:11-17`); NO existen `src/services/clipboard.ts`, `copyService.ts`, `routes.ts`, `shortcuts.ts`, `bulkFlags.ts`, `connectionFlags.ts`, `flagGate.ts`, `peekLinks.ts`, `savedViews.ts`; `nativeDialogByFile` tiene **0** hits en todo `frontend/` (la dimensión del ratchet no existe: su dueño nominal, el 156, no está implementado — ver §6.6).
7. **Saneo del duplicado preexistente en los runners (C3 — el gotcha del merge silencioso YA ocurrió acá):** verificado 2026-07-18: `tests/test_harness_flags.py` está registrado DOS veces en `run_harness_tests.sh` (`:22` y `:340`) y DOS veces en `run_harness_tests.ps1` (`:15` y `:296`). ANTES del primer uso del script §7bis: pre-flight `git status -- "Stacky Agents/backend/scripts/run_harness_tests.sh" "Stacky Agents/backend/scripts/run_harness_tests.ps1"` (WIP ajeno ⇒ STOP y avisar); eliminar SOLO la segunda ocurrencia en cada runner (hoy `:340` del `.sh` y `:296` del `.ps1` — anclar por texto, las líneas pueden haberse movido); commit propio quirúrgico de esos 2 paths. Sin este saneo, G4b da rojo con el árbol limpio. Anotar en §9. (Es tooling de tests, no producto: no viola el "cero código de producto" de §1.)

---

## 5. Orden canónico (con justificación por arista)

| # | Plan | Por qué en este lugar (aristas) |
|---|------|--------------------------------|
| 1 | **165** contrato URL | **F1-F3 YA IMPLEMENTADAS (commits f49588eb→8619acfd): `routes.ts`, filtros persistentes (`useLocalStorageState`) y subestado en la URL ya existen ⇒ su casilla en §9 es VERIFICAR gate satisfecho, no implementar desde cero.** Es el que reescribe `App.tsx` más invasivamente (router como estado + `navigateToRoute` + borrar defs locales): fue PRIMERO, con el árbol más limpio. Entrega `routes.ts` que 175 (peekLinks) y 187 (links de lote) consumen, destraba el GATE del periférico 152, y su receptor canónico `?exec=` (alias `execution`) blinda los deep-links que 175/187/194 arman después. Nadie de la serie depende de nada anterior a él. |
| 2 | **172** teclado primero | Segundo toque a `App.tsx` (mata el useEffect keydown y monta el listener del registry): SECUENCIAL ESTRICTO después de 165 (mismo archivo). Crea `shortcutRegistry` ANTES de que 185 (Ctrl+Z) llegue — elimina la migración futura que el propio 185 §2 anuncia (decisión de costo total: §6.4). Además lee su flag por el campo aditivo de `/api/diag/health` (§6.1 Parte A — NO crea `flagGate.ts`; ese lo crea el 194 en la Parte B) y aplica el foco roving a History/ReviewInbox antes de que 174/175/187 recarguen esos `<tr>`. |
| 3 | **164** diálogo canónico | **F1 (primitiva `Dialog` + hooks `useConfirm`/`useAlert`/`useTextPrompt`) YA IMPLEMENTADA (commit 9a57c378, `ui/index.ts`); pendiente F2+ (migración de ~32 nativos + dimensión `nativeDialogByFile`).** Superficie propia (`main.tsx` + `ui/` + modales): NO choca con `App.tsx` de 165/172. Entrega `useConfirm()`/`ConfirmDialog` (su API real — C2: el 164 NO define ningún `askConfirm`; ese nombre es el gateway del 175 y jerga del 185) que 175 consume en su gateway (175:174: "se cambia SOLO la implementación de ese módulo a `useConfirm()`") y 187 declara compatible. Su F2 baja los ~32 diálogos nativos ANTES de que el 185 F5 mida el baseline `confirmCallCount` (nace bajo y estable) y evita la doble migración de los mismos call-sites (§6.5). Crea la dimensión `nativeDialogByFile` si 156 sigue ausente (§6.6 — rama que su propio pre-check C5 ya trae, 164:407-409). |
| 4 | **194** portapapeles | Crea `copyService.ts` + ratchet `copyDebtRatchet` **y el módulo común `flagGate.ts`** (§6.1 Parte B: primer plan del orden que lee flag por `HarnessFlags.list`) ANTES de que 175/187 escriban clipboard propio: 175 deja de crear `services/clipboard.ts` y 187 deja de escribir `writeText` inline (§6.2). No toca `App.tsx` ni los `<tr>` calientes (su F4 agrega `CopyAsButton` a toolbars). Ya sabe convivir con 164 (Toast de la casa) y difirió su atajo al 172 (194 §4.11) — que ya está. |
| 5 | **173** vistas guardadas | Consume 165 en blando (su F6 detecta claves de filtro en URL "solo posible con el 165 implementado", 173:494 — ya está, la rama funciona completa) y entrega el backend `sort`+`total` (su F5 = backlog declarado del 165). Toca History/SystemLogs/TicketBoard DESPUÉS de que 165/172 estabilizaron filtros y filas, y ANTES de que 174 ajuste las queries cuyas prefs de columnas este plan persiste. |
| 6 | **174** rendimiento percibido | Sus `getPrefetchProps` se esparcen sobre `<tr>` que YA tienen el roving del 172 (acumulación de props, regla §6.8); su `keepPreviousData` toca las MISMAS queries que 173 F5 acaba de extender con `total` (mejor tocarlas una vez estabilizadas). Virtualiza SOLO `LogsPanel` y `DiffList` (vírgenes en la serie) — verificado: NO virtualiza la tabla del historial (su KPI-3 lo fija), así que no hay conflicto estructural con checkbox 187 ni menú 175. |
| 7 | **185** undo universal | Su F3 (pilotos TicketBoard/EpicChildrenPanel) corre DESPUÉS del 164 F2 sobre call-sites ya migrados (delta §8.6); su F5 congela `confirmCallCount` con el conteo ya minimizado; su Ctrl+Z se registra en el `shortcutRegistry` del 172 (ya existe — delta §8.6); su diff de `Toast.tsx` (prop opcional `action`) no rompe a nadie (§6.3). Tercer toque a `App.tsx` (montar `UndoToastHost`). |
| 8 | **187** selección múltiple | Mete la columna checkbox PRIMERA en History/ReviewInbox cuando esas tablas ya recibieron roving (172), prefs de columnas (173) y prefetch (174) — reglas de inserción §6.9. Consume: armado two-step compatible 164 (ya está), `copyText` del 194 (delta §8.7), URL canónica del 165 (delta §8.7). Su Escape queda LOCAL por decisión §6.4 (no migra al registry). |
| 9 | **175** peek + menú contextual | El MÁXIMO consumidor de la serie: `askConfirm` (164), `routes.ts` vía `peekLinks` (165), `copyService` (194), convive con roving (172) y checkbox (187) en los mismos `<tr>`. Al ir anteúltimo, TODOS sus fallbacks declarados se resuelven a favor del módulo canónico (deltas §8.8) y su F5 ("verificación transversal, cierre de la serie" del cockpit) verifica el estado real final de las tablas. |
| 10 | **192** resiliencia de conexión | El más independiente (único dueño de `client.ts`; verificado que 174 no lo toca). Va último: (a) `App.tsx` ya está quieto para montar `ConnectionBanner`; (b) su F4 (invalidateQueries global al recuperar) se prueba contra TODAS las queries que la serie dejó cableadas — máxima cobertura de la rehidratación; (c) su `connectionFlags` se reduce a wrapper del `flagGate` ya existente (delta §8.9). Coexistencia con 156 ya declarada en su D11. |

**Regla de adopción de módulos comunes (anti-desvío):** el orden es recomendación fuerte; los módulos comunes §6 son OBLIGACIÓN. Si la sesión paralela (u operador) implementa fuera de orden, el PRIMER plan que aterrice y necesite el módulo LO CREA con el contenido/regla congelados en §6, y los demás consumen; el desvío + delta aplicado se anota en §9 (matriz de escenarios en §6.7).

---

## 6. Mapa de colisiones y módulos comunes

### 6.1 Lectores de flag de UI — DOS mecanismos con dueños distintos (C-2, nota de integración reversible)

**Corrección de coherencia 2026-07-18 (C-2 — nota de integración REVERSIBLE):** la v2 trataba a `flagGate.ts` (lee `HarnessFlags.list`, `GET /api/harness-flags`) como ÚNICO lector para los 10 planes. Es MECÁNICAMENTE FALSO para los 4 cockpit: 172 (KPI-8: la flag sale del `fetch("/api/diag/health")` que `App.tsx` YA hace), 173 (§"Mecanismo EXACTO…": campo aditivo de `/api/diag/health`), 174 (C7: hook `useHealthFlags` sobre `/api/diag/health`) y 175 (`useUiFlags` sobre `/api/diag/health`) leen su flag del **campo booleano ADITIVO de `GET /api/diag/health`** (mecanismo del plan 139), NO de `HarnessFlags.list`. Forzarlos a `HarnessFlags.list` rompería el KPI-8 del 172 (cero requests nuevos) y el presupuesto 0-requests-extra del 174. Por eso hay DOS lectores con familias disjuntas (si un plan futuro unifica ambos endpoints, se colapsa sin tocar features).

**Parte A — Cockpit (172/173/174/175): flag por el campo aditivo de `/api/diag/health` (hook común `useHealthFlags`).**
- **Mecanismo (plan 139):** cada plan agrega su campo booleano al dict de `health()` (`backend/api/diag.py`, patrón `bool(getattr(_config.config, "STACKY_…", True))`, junto a `local_llm_enabled`/`shell_v2_enabled`) y lo lee en el frontend.
- **Regla congelada (unificación anti-doble-fetch):** UN solo fetch de health por sesión. Hook canónico = **`useHealthFlags`** (spec del 174 C7: react-query, `staleTime: Infinity`, `r.ok` antes de `r.json()`). Los cockpit convergen en ese hook y en UNA sola queryKey: 172 ya exige el fetch único (KPI-8, lee en el effect de `App.tsx`), 174 formaliza `useHealthFlags`, y 173/175 se suman a la misma key en vez de abrir la suya (hoy 174 usa `["ui-perf-flags"]` y 175 `["diag-health-ui-cockpit"]` — al integrar, una sola). KPI que lo protege: `grep -c 'fetch("/api/diag/health")' src/App.tsx` → `1`.
- **Consumidores:** 172 (`ui_shortcuts_enabled` → `isUiShortcutsEnabled`), 173 (`saved_views_enabled` → `useSavedViewsEnabled`), 174 (`ui_virtualization`/`ui_prefetch`/`ui_instant_nav` → `useUiPerfFlags` montado sobre `useHealthFlags`; 174:228 vive en `hooks/`), 175 (`peek`/`context_menu` → `useUiFlags`). NINGUNO llama `HarnessFlags.list` ⇒ ninguno cuenta para el gate de la Parte B.

**Parte B — `frontend/src/services/flagGate.ts`: flag por `HarnessFlags.list` (`GET /api/harness-flags`).**

**Problema:** 185 lee su flag con `HarnessFlags.list()` (185:173-175), 187 crea `bulkFlags.ts` (`resolveBulkActionsEnabled`, 187:185-200), 192 crea `connectionFlags.ts`, y 194 lee `STACKY_COPY_EXPORT_ENABLED` — cada doc autocontenido. Sin regla: 4 réplicas del mismo lookup + cache.

**Regla congelada:** el PRIMER plan del orden canónico que lee por `HarnessFlags.list` = **194** (puesto 4; 185/187/192 vienen después) crea `flagGate.ts` con EXACTAMENTE esta API (semántica = la más especificada de la serie, el 187 K6, + cache anti-flash del 192 F2):

```ts
// frontend/src/services/flagGate.ts — Plan 197 (serie UX). Lector de flags servidas por
// GET /api/harness-flags (HarnessFlags.list). Los cockpit 172/173/174/175 NO usan este módulo:
// leen /api/diag/health (Parte A). Consumidores: 185/187/192/194.
// Semántica fail-open (187 K6): OFF ⇔ value === false literal; key ausente / lista vacía /
// error de red / value string "false" ⇒ ON. Cache localStorage "stacky.flag.<key>" anti-flash (192 F2).
import { HarnessFlags } from "../api/endpoints";

export function flagEnabledFrom(flags: Array<{ key: string; value: unknown }> | null | undefined, key: string): boolean;
export function getBoolFlag(key: string): Promise<boolean>;   // 1 request por sesión (promesa cacheada a nivel módulo), actualiza el cache
export function readCachedBoolFlag(key: string): boolean;     // sincrónico: localStorage o true (fail-open); vitest node no tiene localStorage ⇒ tests con vi.stubGlobal (192 C10)
```

**Tests del módulo (contrato mínimo C7 — los crea el creador en el mismo commit, `src/services/__tests__/flagGate.test.ts`):** los 5 casos del 187 K6 generalizados sobre `flagEnabledFrom` (`off_cuando_value_false_literal`, `on_cuando_value_true`, `on_cuando_key_ausente`, `on_cuando_flags_undefined_o_null`, `on_cuando_value_string_false` — 187:220 tiene los valores exactos; acá parametrizados por `key`) + 2 de cache: (i) `getBoolFlag` hace UNA sola llamada a `HarnessFlags.list` ante N invocaciones (promesa cacheada; `vi.mock` del módulo `../api/endpoints`), (ii) `readCachedBoolFlag` devuelve `true` sin `localStorage` disponible (fail-open; `vi.stubGlobal`, patrón 192 C10). Registro vitest: se corre POR ARCHIVO como todos los de la serie.

**Consumidores de `flagGate` (Parte B) y delta (cada uno conserva su wrapper NOMBRADO para que sus tests/greps/KPIs sigan válidos):**

| Plan | Wrapper que su doc nombra | Delta de migración |
|------|---------------------------|--------------------|
| 194 (creador) | su lectura de `STACKY_COPY_EXPORT_ENABLED` | crea `flagGate.ts` + su test en el mismo commit; su lectura pasa a `getBoolFlag`/`readCachedBoolFlag` |
| 185 | wiring de flag de su F2 | wrapper de 1-3 líneas sobre `flagGate` (su `HarnessFlags.list()` directo, 185:173-175, pasa a `getBoolFlag`) |
| 187 | `bulkFlags.ts` + `bulkFlags.test.ts` (K6) | `bulkFlags.ts` queda como wrapper que SIGUE exportando `resolveBulkActionsEnabled` (nombre REAL de su parser — 187:187; C6) implementado como `(flags) => flagEnabledFrom(flags, "STACKY_BULK_ACTIONS_ENABLED")`, más `useBulkActionsEnabled` con su semántica optimista intacta (primer mount `_last ?? true`, 187:209-210) delegando el fetch en `getBoolFlag`; `bulkFlags.test.ts` NO cambia (importa `resolveBulkActionsEnabled` del wrapper, mismos 5 casos) |
| 192 | `connectionFlags.ts` + test (C10) | ídem 187: wrapper + re-export; su D9 ("PROHIBIDO importar de 185/187") queda OBSOLETO — la prohibición era por planes no implementados; `flagGate` es de la serie, no de 185/187 |

**Gate del módulo (KPI-2, ampliado C5):** cero llamadas a `HarnessFlags.list` en TODO `src/` fuera de la allowlist {`services/flagGate.ts`; `components/HarnessFlagsPanel.tsx` y `pages/memory/MemoryConfigPanel.tsx` (ADMINISTRACIÓN del panel de flags: hacen list+update, no son lectores de feature); archivos `.test.`}. Comando exacto en KPI-2 §1. Los wrappers de Parte B — vivan en `services/` o en `hooks/` — no hacen fetch propio. **Los cockpit (Parte A) NO aparecen en este gate:** leen `/api/diag/health`, no `HarnessFlags.list`, así que el KPI-2 sigue VERDE y mecánicamente correcto tras la corrección C-2 (su presupuesto de red se protege por el KPI-8 del 172, aparte).

### 6.2 Módulo común `frontend/src/services/copyService.ts` (clipboard — creador 194, consumidores 175/187/172-futuro)

- **Creador:** 194 F1 (contrato completo en su doc: `copyText`, `copyRichText`, fallback textarea con foco preservado, strings de feedback §4.3). El ratchet `copyDebtRatchet` (194 F5) congela `navigator.clipboard.writeText` fuera del canónico.
- **175:** NO crea `services/clipboard.ts` (su F1 "Paso 4 — clipboard.ts" queda ANULADO por esta hoja, §8.8): `ctx.copy` del registro de acciones importa `copyText` de `copyService`.
- **187:** `copySelectedLinks` (F5) NO escribe el try/catch `navigator.clipboard.writeText` local (su propio doc lo anticipa en el comentario 187:725): usa `copyText` y su resultado alimenta el Toast (§8.7).
- **172:** sin delta hoy; si a futuro suma un atajo de copiado, invoca `copyText`/`copyRichText` (regla ya escrita en 194 §7.5).
- **Gate (KPI-3):** cero `navigator.clipboard` fuera de `copyService.ts` y tests.

### 6.3 `components/Toast.tsx` — 1 modificador, 3 consumidores (orden libre, declarado)

- **Único plan que lo MODIFICA:** 185 F2 (prop **opcional** `action` + botón `toastAction`; diff exacto en su doc, backward-compatible por diseño — verificado contra `Toast.tsx:11-25` actual: sin prop `action` hoy).
- **Consumidores que NO lo tocan:** 164 (destino de errores migrados, F2), 187 (shape estructuralmente compatible `ToastState`, F2), 194 (canal de feedback, §4.3). Ninguno depende de la prop `action`.
- **Regla:** dependencia BLANDA — cualquier orden funciona; con el orden canónico, 185 lo modifica en el puesto 7 y nadie antes lo necesita distinto. PROHIBIDO que otro plan de la serie edite `Toast.tsx` (si un implementador cree necesitarlo, es un desvío → §9).

### 6.4 Teclado: registry 172 vs listeners directos 185/187/175 (regla de absorción)

Decisión por costo total (fija — no re-decidir en implementación):

| Listener | Regla | Por qué |
|----------|-------|--------|
| Ctrl+Z global (185 F2) | **MIGRA al registry**: como 172 aterriza antes (puesto 2 vs 7), 185 NO monta `window.addEventListener` — registra el atajo en `shortcutRegistry` (172 F1) y el handler sigue llamando al helper puro `shouldHandleUndoKey` como guard (los tests y el grep-gate del 185 F2 `grep -n "shouldHandleUndoKey" src/components/UndoToastHost.tsx` siguen verdes). Es EXACTAMENTE la migración que 185 §2 y §6 anuncian "cuando el 172 exista" — existe. | 1 listener global menos, el atajo aparece gratis en el overlay "?" del 172 F3, cero re-trabajo futuro |
| Escape de selección (187 F3, hook `useRowSelection`) | **NO migra — queda local.** | No es un atajo global: es interacción CONTEXTUAL por página con estado (`escapeDisabled: detailId !== null || bulkRunning`, 187 R7) y guard PROPIO (`shouldClearSelectionOnEscape` permite foco en checkbox — INPUT type checkbox devuelve true, 187 F2), semántica que el supresor del registry (`isEditableTarget`) NO replica. Migrarlo cambiaría comportamiento. |
| keydown del menú contextual (175 F3) | **NO migra — queda local.** | Vive SOLO mientras el menú está abierto (175:694: listener a nivel document "agregado SOLO mientras" — montaje condicional); es navegación interna de un popup, no un atajo. |
| Atajo de copiado (194) | **Ya descartado por el propio 194** (§4.11): no monta listener; diferido al registry del 172. Sin delta. | decisión previa correcta, se conserva |

**Techo KPI-4 (lista nominal cerrada):** baseline 6 (§4.4) − 1 (`App.tsx` migrado por 172 F2) − 1 (`hooks/useKeyboardShortcuts.ts`: 172 F3 mata "la lista que miente" `DEFAULT_SHORTCUTS`/`ShortcutsCheatsheet`; si el hook muerto sobrevive como archivo, cuenta) + 1 (listener único del registry, 172 F2) + 1 (Escape 187) + 1 (menú 175) = **7 ± 1** → techo binario `<= 8`, con `App.tsx = 0` obligatorio. Todo listener keydown NUEVO no listado acá es un desvío (§9).

### 6.5 Confirmaciones: 164 (askConfirm) × 185 (undo + ratchet) × 187 (armado) × 175 (two-step)

- **Árbitro semántico (ya codificado en 185 §3.2 — esta hoja lo eleva a regla de serie):** irreversible o efecto externo → confirmación (canal 164: `useConfirm()`/`ConfirmDialog` — nombre REAL de su API, C2; o armado two-step 175/187 — que NO son diálogos nativos). Reversible con inversa natural → undo con gracia (185), sin confirmación previa.
- **Orden fijado 164 → 185** para que los MISMOS call-sites no se migren dos veces en sentidos cruzados: 164 F2 convierte los ~32 nativos a su canal según su "Regla de destino" (confirmaciones → `useConfirm`/`ConfirmDialog`/`ConfirmButton`; avisos de error → `Toast`); 185 F3 después convierte a `scheduleUndoable` SOLO los reversibles — su doc v2 ya acepta el canal del 164 como fuente de conversión (185:236 "dejala con confirm/askConfirm" — ahí "askConfirm" nombra genéricamente la confirmación de marca del 164; el símbolo real es `useConfirm`, C2). Delta §8.6: el inventario del 185 F3 se rehace grepeando `confirm(` **y** `useConfirm(`.
- **Ratchets sin fricción:** el `confirmCallCount` del 185 F5 NO cuenta `askConfirm(` NI `useConfirm(` (definición exacta 185:279: subcadena `window.confirm(` + regex minúscula `confirm\(` precedido de no-word — en ambos símbolos camelCase la subcadena es `Confirm(` con C mayúscula y no matchea) ⇒ las migraciones del 164 lo BAJAN, nunca lo suben; el armado two-step de 187/175 no usa nativos ⇒ tampoco suma (187 R8 ya lo declara). El gate del 164 (`nativeDialogByFile` en `forcedZero`) y el del 185 son compatibles en cualquier orden, pero el canónico produce el baseline mínimo.

### 6.6 Dimensión `nativeDialogByFile` del uiDebtRatchet — dueño nominal 156 (periférico, NO implementado)

Verificado 2026-07-18: **0 hits** de `nativeDialogByFile` en `frontend/` — la dimensión NO existe (su creador nominal es el 156, "plan del latido único", según 164 §2.4: "la dimensión la crea el plan del latido único; F2 la lleva a 0"). **Regla confirmada (C8 — NO es un delta nuevo del 197: el propio doc 164 ya la codificó en su pre-check C5, 164:407-409):** el 164 NO se bloquea por el 156 — si al implementar 164 el grep de pre-check da 0, **164 F2 la CREA** "con EXACTAMENTE la spec del 156-F6" (cita literal 164:408) en `uiDebtRatchet.test.ts` + baseline, con el criterio de exclusión que el propio 164 fija (`**/__tests__/**` **y** `*.test.*`, su §2.2 — sin esa exclusión el 0 es inalcanzable por el fixture XSS de `src/incidents/incidentModel.test.ts`), la lleva a 0 y la mueve a `forcedZero` (su A1). Cuando el 156 aterrice, encuentra la dimensión creada y su F6 se marca satisfecho — anotarlo en §9. El 197 solo CONFIRMA esa rama y le da visibilidad de serie.

### 6.7 Matriz de escenarios (si el orden se altera — deltas por cruce)

| Cruce | Escenario canónico | Escenario invertido (desvío) |
|-------|--------------------|------------------------------|
| 194 vs 175/187 (clipboard) | 175/187 nacen importando `copyText`; cero `writeText` nuevos | 175/187 implementan su fallback local tal cual sus docs; al aterrizar 194, su F5 los cuenta en el baseline inicial Y la migración (reemplazar `clipboard.ts`/try-catch por `copyText` + bajar el baseline) pasa a ser parte del DoD del 194 — anotar en §9 |
| 172 vs 185 (Ctrl+Z) | 185 registra en `shortcutRegistry` (§6.4) | 185 monta el listener directo (su doc); la migración del listener pasa a ser DoD del 172 (junto a la de `App.tsx` que ya hace su F2) — anotar en §9 |
| 194 vs resto (flagGate, Parte B) | 194 crea `flagGate.ts`; los cockpit 172/173/174/175 NO lo usan (leen `/api/diag/health`, Parte A) | el primer plan del orden que lea por `HarnessFlags.list` (185/187/192/194) lo crea con el contenido §6.1 Parte B tal cual, y los demás lo consumen al llegar |
| 165 vs 175/187 (deep-links) | `peekLinks` delega en `routes.ts`; 187 arma con clave `exec` | 175/187 arman el literal `?execution=` contra el receptor real de HOY (sus fallbacks); al aterrizar 165, los links viejos SIGUEN funcionando (165 F1 canoniza `exec` con alias `execution` — blindado por su C4); migración opcional de 1 línea por módulo, anotar en §9 |
| 164 vs 185 (confirmaciones) | §6.5 | 185 convierte reversibles desde `confirm(`; 164 después migra los restantes; el baseline `confirmCallCount` del 185 quedó medido ANTES del 164 ⇒ tras el 164, re-bajar el baseline en el mismo commit (el ratchet exige bajarlo: mensaje "bajá el baseline", 185:281) |
| 165 vs 173 (persistencia de filtros — C10) | 165 antes: el grep condicional del 173 (`useLocalStorageState` en History, 173:495) MATCHEA ⇒ 173 omite la auto-aplicación de `lastApplied` en esa página y su F6 usa la rama "URL manda" como camino principal | 173 antes: su doc es AUTOCONDICIONAL — el grep no matchea (hoy `useState`, 173:495) ⇒ implementa la auto-aplicación; al aterrizar 165 (que migra `useState` → `useLocalStorageState`), el implementador del 165 re-corre el grep del 173 y DESACTIVA la auto-aplicación redundante en el mismo commit — anotar en §9 |

### 6.8 Regla de acumulación en `<tr>`/filas (History y ReviewInbox)

Los `<tr>` de esas tablas acumulan, en el orden canónico: `tabIndex`/`onKeyDown` roving (172 F4) → `{...getPrefetchProps(id)}` = `onMouseEnter`/`onFocus` (174 F3) → `<td>` checkbox + `onClick` guard (187 F4/F5) → `onContextMenu` + entrada de menú por teclado (175 F3). **Regla dura:** cada plan AGREGA sin reemplazar: si el evento ya tiene handler (p.ej. `onKeyDown` del roving cuando llega 175), se ENCADENA llamando al existente (composición explícita en el JSX), nunca se pisa; los spreads (`getPrefetchProps`) se colocan de modo que no sobreescriban handlers homónimos ya presentes (si colisionara un nombre de prop, envolver ambos en una lambda que invoque a los dos). Verificación por plan: los greps/KPIs del plan ANTERIOR sobre ese archivo (p.ej. `grep withShortcutHint`, `grep getPrefetchProps`) deben seguir pasando — están en el checklist §7.3.

**[ADICIÓN ARQUITECTO A2] Contrato congelado: selección/menú operan sobre el DATASET, nunca sobre la ventana del virtualizador.** Estado verificado 2026-07-18: NO hay conflicto real hoy — el 174 virtualiza SOLO `LogsPanel` y `DiffList` y su KPI-3 lo clava por test de adopción (174:28); History/ReviewInbox reciben únicamente `keepPreviousData` + `getPrefetchProps`, y las superficies de selección (187: History/ReviewInbox) y peek/menú (175: History/TicketBoard) NO se virtualizan. Esta regla se congela para el FUTURO: si algún plan posterior virtualiza una tabla con selección o menú contextual, (a) `visibleIds`/el universo del rango-Shift del 187 y de "seleccionar todo lo visible" se computan del **array filtrado en memoria de la página** (post-filtros, pre-windowing), JAMÁS de las filas montadas por el virtualizador (con windowing, "lo renderizado" es un subconjunto móvil — anclar la selección ahí produce rangos truncados no deterministas); (b) las anclas de selección son **ids de entidad**, no índices de render; (c) los handlers por fila (menú 175, checkbox 187) deben sobrevivir al desmontaje/remontaje de `<tr>` que el windowing produce al scrollear (estado SIEMPRE en el hook/página, nunca en la fila). Todo plan que quiera virtualizar una tabla con selección debe citar y satisfacer este párrafo — de lo contrario es un desvío §9.

### 6.9 Regla de columnas (History/ReviewInbox): checkbox 187 vs prefs 173

- La columna checkbox del 187 va SIEMPRE PRIMERA (su F5) y es **meta-columna**: NO entra en la lista de columnas configurables del 173 F4 (que gobierna las 10 columnas de DATOS de History, 173 §2). El render de 187 la inserta ANTES del mapeo de columnas visibles del 173, de modo que ocultar/mostrar/redimensionar columnas del 173 jamás la afecte.
- La toolbar de History es ADITIVA: `SavedViewsBar` (173 F3) y `CopyAsButton` (194 F4) se agregan al final del bloque de toolbar existente, sin reordenar lo previo — cualquier orden entre 173 y 194 funciona; con el canónico, 194 llega primero.

### 6.10 Mapa de colisiones por archivo (tabla resumen: archivo × planes(fase) en orden de aterrizaje × regla)

| Archivo | Planes (fase) en orden canónico | Regla de resolución |
|---------|---------------------------------|---------------------|
| `frontend/src/App.tsx` | 165 F3 → 172 F2 → 185 F2 (montaje) → 192 F3 (montaje) | SECUENCIAL SIEMPRE (nunca 2 planes a la vez en este archivo). Montajes de hosts globales (`UndoToastHost`, `ConnectionBanner`) = bloque aditivo junto a los hosts existentes, una línea por host. Pre-flight `git status -- ` obligatorio. |
| `frontend/src/main.tsx` | 164 F1 (único: `DialogHost` envuelve `App`) | Nadie más de la serie lo toca; si otro plan cree necesitarlo → desvío §9. |
| `frontend/src/pages/ExecutionHistoryPage.tsx` | 165 F2/F3 → 172 F4/F6 → 194 F4 (toolbar) → 173 F3/F4/F5 → 174 F3/F4 → 187 F5 → 175 F2/F3/F4 | §6.8 (filas acumulan), §6.9 (checkbox primera y fuera de prefs; toolbar aditiva). Anclas por TEXTO (el archivo muta 7 veces). Pre-flight por fase. |
| `frontend/src/pages/ReviewInboxPage.tsx` | 172 F4 → 174 F3 → 187 F4 | §6.8. Verificado por grep: 173 y 175 NO la tocan. |
| `frontend/src/pages/SystemLogsPage.tsx` | 165 F2 → 173 F3/F4 → 174 F4 | filtros (165) antes que presets (173) antes que `keepPreviousData` (174); anclas por texto. |
| `frontend/src/pages/TicketBoard.tsx` | 164 F2 (confirms) + F3/F4 (RunModal → diálogo compartido) → 173 F3 (SavedViewsBar) → 185 F3 (piloto undo) → 175 F2 (peek) | 164 primero REDUCE el archivo (~137 líneas del RunModal fuera) — menos superficie para los 3 siguientes. Archivo caliente histórico: pre-flight SIEMPRE. |
| `frontend/src/components/Toast.tsx` | 185 F2 (único modificador) | §6.3. |
| `frontend/src/api/client.ts` | 192 F2 (único) | Verificado: 174 no lo toca (prefetch vía `queryClient`). |
| `frontend/src/api/endpoints.ts` | 173 F5 (tipos `sort`/`total`) | 192 y 187 solo lo IMPORTAN. Aditivo. |
| `frontend/src/components/CommandPalette.tsx` | 172 F6 (único de la serie) | hints de atajos; aditivo sobre lo del plan 129. |
| `backend/services/harness_flags.py` (+ curado en `tests/test_harness_flags.py` + categorización) | F0 de 172, 173, 174 (alta doble), 175, 185, 187, 192, 194 | Cada plan agrega su FlagSpec al FINAL del bloque UI + `_CURATED_DEFAULTS_ON`; tras cada merge, gate de keys duplicadas (§7 G4) — es el patrón exacto del gotcha del duplicado silencioso. |
| `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1` | 172, 173 (×2 tests), 174, 175, 185, 187, 192 (194 NO: su G5 no crea archivo de test nuevo) | **Regla transversal:** TODO registro va en AMBOS runners (verificado: ambos existen; los docs 172/173/175/187 solo nombran el `.sh` — completar el `.ps1` es parte de su nota §8). Línea propia al final; gate de duplicados §7 G4. |
| `frontend/src/__tests__/uiDebtBaseline.json` (+ ratchet) | 164 (dimensión `nativeDialogByFile` + forcedZero, §6.6); TODOS los demás: cero inline-style nuevos | El baseline solo lo regenera quien el doc del plan indique; deuda ajena preexistente NO se toca (criterio no-empeorar). |

### 6.11 [ADICIÓN ARQUITECTO A1] Hosts flotantes y stacking canónico del viewport (C9)

La serie agrega 4 superficies flotantes a un viewport que YA tiene varias, y ningún doc de la serie fija la convivencia (los docs 185/192 declaran su posición; nadie declara el conjunto). Tabla canónica — todo host nuevo de la serie se ubica según esta tabla y NO se solapa con otra celda ocupada; conflicto = desvío §9:

| Capa (de abajo hacia arriba) | Superficie | Dueño | Región del viewport |
|---|---|---|---|
| 1. Banners de página | `HealthBanner` (existente), `ConnectionBanner` (192 F3) | app / 192 | franja superior, flujo del layout (no flotan sobre contenido); ConnectionBanner debajo/junto a HealthBanner, coexistencia ya declarada en 192 D10 |
| 2. Toasts de acción | `Toast` component-local (existente — SIN provider global, 164:120) y `UndoToastHost` (185 F2: "posición fija esquina inferior derecha, stack vertical, ancho máx 360px", 185:181) | cada componente / 185 | esquina inferior derecha. REGLA: `UndoToastHost` es el ÚNICO stack fijo en esa esquina; los `Toast` locales existentes renderizan dentro de su componente (no fijos a viewport) y no compiten |
| 3. Menú contextual | popup del 175 F3 | 175 | anclado al punto de interacción; se cierra ANTES de abrir cualquier capa 4-5 (su propio contrato de montaje condicional, 175:694) |
| 4. Diálogos modales | `DialogHost` del 164 (montado en `main.tsx` envolviendo `App`) | 164 | overlay centrado con focus-trap; por encima de capas 1-3 |
| 5. Overlays de ayuda/onboarding | overlay "?" (172 F3), `OnboardingTour` (151, existente) | 172 / 151 | pantalla completa. REGLA: mutuamente excluyentes — el overlay "?" NO se abre mientras el tour está activo (el tour captura keydown, `OnboardingTour.tsx:56`); el implementador del 172 agrega el guard "tour activo ⇒ ignorar ?" y lo smoke-testea |

**Regla de z-index:** ningún plan hardcodea valores mayores que los del `DialogHost` del 164; si un doc de la serie necesita un z-index nuevo, lo toma MENOR que el del diálogo (capa 4) salvo la capa 5, y lo anota en su module.css con comentario `/* capa N tabla 197 §6.11 */`. La campana del 152 (futuro, fuera de serie) ocupará capa 2 lado derecho del TopBar — reservado, no flotante.

### 6.12 Propiedad de las queryKeys de cache del peek (174 vs 175) — R-1

El peek del 175 enriquece entidades leyendo el cache de react-query. Registro de dueños (resuelve R-1: el 175 difería `["ticket-detail", id]` al 174, pero el 174 prefetchea SOLO ejecuciones):

| queryKey | Dueño (puebla el cache) | Nota |
|---|---|---|
| `["execution-detail", id]` | **174** (prefetch on-hover, 174 §F3/KPI-3) | CONTRATO COMPARTIDO congelado con 174; 175 la LEE con `queryClient.getQueryData(...)` y cae a `fetchQuery` on-demand solo si el cache está frío (174 ausente). |
| `["ticket-detail", id]` | **175** (contrato PROPIO) | El 174 NO prefetchea tickets (su prefetch cubre History/ReviewInbox = ejecuciones, 174 KPI-3). 175 es su ÚNICO dueño: la puebla on-demand con `fetchQuery({ queryKey: ["ticket-detail", id], queryFn: () => Tickets.byId(id), staleTime: 30_000 })` + `<Spinner size="sm">`. NO se difiere al 174. |

**Regla:** un plan futuro que quiera prefetchear tickets debe CITAR esta fila y coordinar con el 175 (dueño), igual que §6.8 A2 para selección/virtualizador. Las queryKeys de EJECUCIÓN siguen congeladas con el 174.

---

## 7. Gates compuestos (tras CADA plan mergeado)

Ejecutar (a)-(d); cualquier fallo se arregla ANTES de arrancar el siguiente plan; resultado → §9.

- **(a) Script de gates:** `bash "Stacky Agents/backend/scripts/check_serie_ux_gates.sh"` (contenido §7bis; Git Bash desde la raíz del repo; prerrequisito de UNA sola vez: Gate 0.7 — sin él, G4b arranca rojo por el dup preexistente C3) → `GATES SERIE UX OK`.
- **(b) tsc:** cwd `Stacky Agents/frontend` → `npx tsc --noEmit` → sin errores nuevos vs. Gate 0.3.
- **(c) Tests del plan recién mergeado, POR ARCHIVO:** los vitest que su doc nombra (`npx vitest run src/<ruta>` uno por uno) + los pytest que su doc nombra con `.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q` desde `Stacky Agents\backend` + los 4 ratchets frontend de §4.5 (y los nuevos 185 F5/194 F5 cuando existan) + **los greps/KPIs del plan ANTERIOR sobre archivos compartidos** (§6.8: verificar que la fase nueva no pisó `withShortcutHint`, `getPrefetchProps`, `toastAction`, `shouldHandleUndoKey`, la columna checkbox, ni `onContextMenu` previos — el comando exacto es el KPI del plan anterior tal cual su doc).
- **(d) Smoke manual del plan** según su propio doc (cada uno lo trae).

### 7bis. Script ejecutable `Stacky Agents/backend/scripts/check_serie_ux_gates.sh` (lo crea quien ejecuta el Gate 0)

```bash
#!/usr/bin/env bash
# Plan 197 v2 - gates compuestos de la serie UX 164-194. Correr con Git Bash desde la RAIZ del repo.
# Exit 0 = todo limpio. Cada chequeo es tolerante a "todavia no existe" (pre-modulo comun).
# PRERREQUISITO: Gate 0.7 ejecutado una unica vez (dedup preexistente de los runners, C3).
set -u
fail=0
FE="Stacky Agents/frontend"
BE="Stacky Agents/backend"
# G1 compileall backend con el INTERPRETE CANONICO (.venv py3.13.5, seccion 4.1) y excluyendo
# AMBOS venvs (C4: "python" del PATH es hoy 3.11.9 = justo la version prohibida por 4.1, y
# compilar site-packages ajenos es lento y fragil)
"$BE/.venv/Scripts/python.exe" -m compileall "$BE" -q -x "(\.venv|venv)" || { echo "G1 compileall FALLO"; fail=1; }
# G4a flags backend duplicadas - SOLO definiciones FlagSpec (key="...").
# C1: el patron v1 (toda mencion STACKY_*_ENABLED) daba DECENAS de falsos duplicados con el
# arbol limpio (una flag aparece legitimamente en key=, categorias, requires= y comentarios).
# Verificado 2026-07-18: 217 definiciones key=", 0 duplicadas.
dups_flags=$(grep -o 'key="STACKY_[A-Z_0-9]*"' "$BE/services/harness_flags.py" | sort | uniq -d)
[ -n "$dups_flags" ] && { echo "G4a FlagSpec duplicada: $dups_flags"; fail=1; }
# G4b registros de tests duplicados (sh y ps1; patron test_ generico, leccion 195 C2).
# Baseline limpio SOLO tras el Gate 0.7 (hoy tests/test_harness_flags.py esta 2x en ambos, C3).
dups_sh=$(sort "$BE/scripts/run_harness_tests.sh" | uniq -d | grep "test_")
[ -n "$dups_sh" ] && { echo "G4b duplicados en run_harness_tests.sh: $dups_sh"; fail=1; }
dups_ps=$(sort "$BE/scripts/run_harness_tests.ps1" | uniq -d | grep "test_")
[ -n "$dups_ps" ] && { echo "G4b duplicados en run_harness_tests.ps1: $dups_ps"; fail=1; }
# G5 keydown: App.tsx en 0 tras el plan 172; techo global 8 (lista nominal 197 seccion 6.4)
kd_app=$(grep -c 'addEventListener("keydown"' "$FE/src/App.tsx")
if [ -f "$FE/src/services/shortcuts.ts" ] && [ "$kd_app" -ne 0 ]; then
  echo "G5 App.tsx tiene keydown directo ($kd_app) con el registry 172 ya presente"; fail=1
fi
kd_total=$(grep -rn 'addEventListener("keydown"' "$FE/src" | wc -l)
[ "$kd_total" -gt 8 ] && { echo "G5 conteo keydown $kd_total > techo 8"; fail=1; }
# G6 clipboard fuera del canonico (solo aplica cuando copyService existe, plan 194)
if [ -f "$FE/src/services/copyService.ts" ]; then
  cb=$(grep -rn "navigator.clipboard" "$FE/src" --include=*.ts --include=*.tsx | grep -v "copyService" | grep -v ".test." | wc -l)
  [ "$cb" -ne 0 ] && { echo "G6 navigator.clipboard fuera de copyService: $cb"; fail=1; }
fi
# G7 flagGate unico lector de FEATURE (solo aplica cuando flagGate existe).
# C5: barre TODO src/ (useUiPerfFlags del 174 vive en hooks/, no en services/), con allowlist
# de ADMINISTRACION (HarnessFlagsPanel y MemoryConfigPanel hacen list+update del panel).
if [ -f "$FE/src/services/flagGate.ts" ]; then
  readers=$(grep -rln "HarnessFlags.list" "$FE/src" --include=*.ts --include=*.tsx | grep -v "flagGate" | grep -v "HarnessFlagsPanel" | grep -v "MemoryConfigPanel" | grep -v ".test.")
  [ -n "$readers" ] && { echo "G7 lectores de flag fuera de flagGate: $readers"; fail=1; }
fi
[ $fail -eq 0 ] && echo "GATES SERIE UX OK"
exit $fail
```

Sin flag: es tooling de desarrollo, no producto (no toca runtime ni UI).

### 7.3 Gates de etapa (checkpoints S1..S5 — cada uno = (a)+(b)+(c) del tramo más lo listado)

| Etapa | Tras | Chequeo binario adicional |
|-------|------|---------------------------|
| S1 | 165 + 172 | `npx vitest run src/services/routes.test.ts` y `src/services/routesDeepLink.test.ts` verdes; `grep -c 'addEventListener("keydown"' src/App.tsx` → 0; overlay "?" funcional (smoke 172 §9) |
| S2 | 164 + 194 | `uiDebtRatchet` verde con `nativeDialogByFile` = 0 por archivo y en `forcedZero`; `copyDebtRatchet` (194 F5) verde; `grep -c "useConfirm" src/components/ui/index.ts` → `>= 1` (C2: la API real del 164 — su barrel exporta `useConfirm`/`useAlert`/`useTextPrompt`, 164:136; "askConfirm" NO existe ahí y el gate v1 habría dado 0 siempre) |
| S3 | 173 + 174 | `npx vitest run src/__tests__/plan174Adoption.test.ts` verde (KPI-3 del 174); `.venv\Scripts\python.exe -m pytest tests\test_executions_history_sort_total.py -q` verde; tests de `savedViews`/`tablePrefs` (173 F2) verdes |
| S4 | 185 + 187 | tests de `undoManager`/`undoToastModel` (185) y `selectionModel`/`bulkModel`/`bulkFlags` (187) verdes por archivo; ratchet `confirmCallCount` verde (no subió); smoke: armado two-step + undo Ctrl+Z vía overlay |
| S5 | 175 + 192 | KPIs de cierre del 175 F5 y 192 F7 según sus docs + KPI-2/3/4 del 197 + checklist final: los 6 ratchets frontend (uiDebt, formDebt, motionDebt, formatDebt, confirmCallCount-185, copyDebt-194) verdes por archivo + G4a/G4b limpios + tabla §9 sin `_pendiente_` |

---

## 8. Notas de migración por plan (delta EXACTO; cita de la sección origen que queda corregida)

> Estas notas NO reescriben los docs: el 197 es la fuente de verdad de integración. El implementador de cada plan aplica su doc v2 + su fila de acá.

1. **165:** sin correcciones de contenido. Restricción de integración: mientras su F3 esté en curso, `App.tsx` queda BLOQUEADO para cualquier otro plan (§6.10). Sus anclas `:línea` sobre `App.tsx`/`ExecutionHistoryPage.tsx` se re-verifican por TEXTO (150/151 ya movieron líneas).
2. **172:** (a) lee su flag por el campo aditivo de `/api/diag/health` (§6.1 Parte A / KPI-8); **NO crea `flagGate.ts`** (ese es Parte B, lo crea el 194) ni envuelve ese módulo — `isUiShortcutsEnabled` lee el campo del health; (b) intérprete: donde su doc dice `venv/Scripts/python.exe` (KPI-7 §26, §112) usar `.venv\Scripts\python.exe` (§4.1); (c) registro de su test backend en AMBOS runners (`run_harness_tests.sh` **y** `.ps1` — su doc solo nombra el `.sh`, F0 §155).
3. **164:** (a) si `nativeDialogByFile` no existe al implementarlo (hoy: 0 hits, §6.6), aplica la rama de SU PROPIO pre-check C5 (164:407-409): F2 la CREA "con EXACTAMENTE la spec del 156-F6" y las exclusiones de su §2.2 (C8: esto NO es un delta del 197 — es la letra del 164; la fila de su tabla §2.4 "la dimensión la crea el plan del latido único" se lee como "el primero que llegue", tal como su C5 ya codifica); (b) `TicketBoard.tsx` caliente: pre-flight y anclas por texto; (c) recordatorio C2 para quien venga de otros docs de la serie: la API que este plan entrega se llama `useConfirm`/`ConfirmDialog` — NO implementar ningún `askConfirm` (ese nombre pertenece al gateway del 175).
4. **194:** (a) **G1 corregido:** el intérprete NO está en `N:\GIT\RS\STACKY\Stacky\.venv` (esa ruta NO existe — verificado 2026-07-18); es `Stacky Agents\backend\.venv\Scripts\python.exe` (py3.13.5) invocado desde `Stacky Agents\backend` — TODOS sus comandos pytest (K1 §49, §268, §792) cambian solo la ruta del exe; (b) su F4 en la toolbar de History es aditivo (§6.9); (c) sin más deltas: su §4.11 (atajo descartado) y §7.3 (sin "Enlace" de ejecución hasta el 165) ya son correctos — con el orden canónico el 165 estará implementado, pero "Copiar Enlace" de ejecuciones SIGUE fuera de su scope (lo declara su Fuera-de-scope; si se desea, es un plan futuro, no un delta).
5. **173:** (a) intérprete `.venv\Scripts\python.exe` (su F5 §466 dice `venv/Scripts/`); (b) registro de sus 2 tests backend en AMBOS runners (su doc solo nombra el `.sh`, K7 §21, F0 §143); (c) su F4 define columnas configurables SOLO sobre las columnas de DATOS (§6.9: la futura checkbox del 187 queda fuera del sistema de prefs); (d) su F6 usa la rama "URL trae claves de filtro" como camino PRINCIPAL (el 165 ya está — su §494 la describía como condicional); (e) lector de flag por `/api/diag/health` (§6.1 Parte A, hook `useHealthFlags`), NO por `flagGate`.
5-bis. **174 (nota que faltaba en la numeración original — C-3/coherencia 2026-07-18):** (a) intérprete backend CANÓNICO `.venv\Scripts\python.exe` (py3.13.5) en TODOS sus comandos pytest (KPI-4/KPI-7, §3.3 y bloques de comando; su doc v2 usaba `venv\Scripts\python.exe` = py3.11.9, WIP ajeno PROHIBIDO §4.1 — ya corregido en su doc por el pase de coherencia); (b) lector de flag por `/api/diag/health` (§6.1 Parte A, hook `useHealthFlags` — su spec, 174 C7), NO por `flagGate`; (c) su preámbulo §1 ya no da a 165 por no-implementado (F1-F3 mergeadas).
6. **185:** (a) **registro de tests corregido:** sus §3.6-§51 y F0 §63 dicen registrar en `tests/test_harness.py` — el registro REAL es `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh` + lista homóloga en `.ps1` (verificado por grep, §2.4); (b) intérprete `.venv\Scripts\python.exe` (sus §46, §76-77, §338 dicen `venv\Scripts`); (c) **Ctrl+Z vía `shortcutRegistry`** (§6.4): su F2 paso 6 ("listener directo... hasta entonces") se implementa DIRECTAMENTE en la variante registry porque el 172 ya está — `shouldHandleUndoKey` se conserva como guard y su grep-gate sigue válido; su ítem de Fuera-de-scope "integración con el registry (no implementado)" queda obsoleto; (d) su F3 rehace el inventario grepeando `confirm(` **y** `useConfirm(` (post-164, §6.5 — C2: la API real del 164 es `useConfirm`; `askConfirm(` recién existirá como campo del ctx del 175, que llega DESPUÉS del 185 en el orden canónico); (e) su F5 mide `confirmCallCount` DESPUÉS de todo lo anterior (ya lo exige su C7: "medirlo AL IMPLEMENTAR esta fase"); (f) lector de flag vía `flagGate`.
7. **187:** (a) intérprete `.venv\Scripts\python.exe` (K1/K2 §29-30, §91 dicen `venv\Scripts`); (b) `copySelectedLinks` usa `copyText` de `copyService` (194 ya está — su comentario §725 lo anticipa; el try/catch local NO se escribe); (c) el link se arma con la clave canónica `exec` (`url.searchParams.set("exec", String(id))` — el receptor del 165 acepta `exec` y el alias `execution`; su C4 con `new URL(window.location.href)` se conserva); (d) `bulkFlags.ts` queda wrapper de `flagGate` con `bulkFlags.test.ts` intacto (§6.1 — C6: el wrapper CONSERVA el export `resolveBulkActionsEnabled`, nombre real de su parser 187:187, implementado sobre `flagEnabledFrom`); (e) su Escape NO migra al registry (decisión §6.4 — no tocar); (f) checkbox primera y fuera de prefs 173 (§6.9); (g) registro de su test backend en AMBOS runners (K3 §31 solo nombra el `.sh`).
8. **175:** (a) su F1 "Paso 4 — `clipboard.ts`" NO se implementa: `ctx.copy` importa `copyText` de `copyService` (194 ya está) — el archivo `services/clipboard.ts` NO se crea; (b) `peekLinks.ts` delega en `routes.ts` desde el día 1 (el 165 ya está — su tabla §175 preveía exactamente este cambio de 1 archivo; el literal `/history?execution=` queda solo como fallback de test si su doc lo exige); (c) su `confirmGateway` (el campo `askConfirm: ConfirmFn` de su ctx, 175:488-498) se implementa DIRECTAMENTE sobre el `useConfirm()`/DialogHost del 164 (ya está — su propia tabla lo preveía: "se cambia SOLO la implementación de ese módulo a `useConfirm()`", 175:174 y 175:445; su §799-800 ídem); la variante v1 del gateway (two-step `armTransition`) sigue siendo FEATURE de su doc — se implementa lo que su doc pida como lógica pura, pero el CANAL efectivo de confirmación con el 164 presente es `useConfirm()` (precedencia §3.1); (d) convivencia de `<tr>`: encadenar handlers existentes (§6.8) — el roving del 172 y la checkbox del 187 YA están en esas filas; (e) registro de su test backend en AMBOS runners (KPI-10 §58 solo nombra el `.sh`); (f) lector de flag por `/api/diag/health` (§6.1 Parte A, `useUiFlags`/`useHealthFlags`), NO por `flagGate`.
9. **192:** (a) `connectionFlags.ts` queda wrapper de `flagGate` con su test intacto (vi.stubGlobal para localStorage se conserva, C10); su D9 ("duplicar el patrón; PROHIBIDO importar de 185/187") queda OBSOLETO — consumir `flagGate` no es importar de 185/187 (§6.1); (b) montaje del `ConnectionBanner` en `App.tsx` DESPUÉS del host del 185 (bloque aditivo §6.10); (c) sin delta de intérprete (su C1 ya es correcto: `.venv\Scripts\python.exe` desde backend); (d) su §10.8 (anclar por texto si la paralela movió líneas) aplica con más razón al final de la serie.
10. **Transversal — intérprete backend (cierra §2.3):** UNA sola forma canónica para los 10 planes: PowerShell, `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` → `.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`, siempre POR ARCHIVO. Cualquier otra ruta de intérprete que aparezca en un doc de la serie (incluida la raíz inexistente del 194 G1) se reemplaza por esta.
11. **Transversal — doble runner:** todo test backend nuevo se registra en `run_harness_tests.sh` **y** `run_harness_tests.ps1` (ambos existen — verificado). Los docs 172/173/175/187 solo nombran el `.sh`; 174/192 ya nombran ambos; 185 nombraba un archivo equivocado (§8.6a); 194 no registra (su G5).

---

## 9. Registro de ejecución (lo completa quien implementa — vive en este doc)

**Convención de commits del registro:** `docs(plan-197): registro <item>` tocando SOLO esta tabla.

| Ítem | Resultado | Fecha |
|------|-----------|-------|
| Gate 0.1 — intérprete `.venv` = py3.13.5 | _pendiente_ | |
| Gate 0.2 — ratchet_meta (verde/rojo + causa) | _pendiente_ | |
| Gate 0.3 — tsc baseline | _pendiente_ | |
| Gate 0.4 — conteo keydown baseline | _pendiente_ | |
| Gate 0.5 — 4 ratchets frontend baseline | _pendiente_ | |
| Gate 0.6 — superficie limpia re-verificada | _pendiente_ | |
| Gate 0.7 — dedup runners (`test_harness_flags.py` 2x en `.sh:22/:340` y `.ps1:15/:296`, C3) + primer run limpio del script §7bis | _pendiente_ | |
| Plan 165 + gates §7 (F1-F3 YA implementadas, commits f49588eb→8619acfd — VERIFICAR gate satisfecho) | _verificar_ | |
| Plan 172 + gates §7 (lee flag por `/api/diag/health`; NO crea flagGate) | _pendiente_ | |
| Etapa S1 | _pendiente_ | |
| Plan 164 + gates §7 (F1 YA implementada, commit 9a57c378 — VERIFICAR gate; falta F2+ / crea nativeDialogByFile si falta) | _pendiente F2+_ | |
| Plan 194 + gates §7 (crea copyService + copyDebt + flagGate) | _pendiente_ | |
| Etapa S2 | _pendiente_ | |
| Plan 173 + gates §7 | _pendiente_ | |
| Plan 174 + gates §7 | _pendiente_ | |
| Etapa S3 | _pendiente_ | |
| Plan 185 + gates §7 (Toast.action + confirmCallCount) | _pendiente_ | |
| Plan 187 + gates §7 | _pendiente_ | |
| Etapa S4 | _pendiente_ | |
| Plan 175 + gates §7 | _pendiente_ | |
| Plan 192 + gates §7 | _pendiente_ | |
| Etapa S5 + KPI-2/3/4 finales | _pendiente_ | |
| Desvíos del orden (si hubo) + delta §6.7 aplicado | _pendiente_ | |
| Nota al 156 (nativeDialogByFile ya creada por 164) | _pendiente_ | |

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| La sesión paralela implementa 185/187/192/194 en OTRO orden (son planes de su loop) | Regla §5 final + matriz §6.7: quien aterriza primero crea el módulo común con el contenido congelado; el desvío se anota en §9 con su delta. Los gates §7 G6/G7 detectan mecánicamente la réplica que se escapó. |
| Docs v2 quedan desactualizados respecto del 197 | Regla de precedencia §3.1: 197 manda en integración, el plan origen en su feature. NO se editan los 10 docs; el delta vive en §8. |
| Merge duplicado silencioso en `harness_flags.py` / runners | §7 G4a/G4b tras CADA merge (patrón exacto del gotcha documentado — que en los runners YA ocurrió: dup preexistente saneado en Gate 0.7, C3). G4a mira SOLO definiciones `key="` (C1: cualquier patrón más ancho da falsos rojos permanentes). |
| Los overlays/hosts de la serie se pisan visualmente al final (4 capas nuevas) | Tabla canónica §6.11 (A1): región + capa por host, overlay "?" excluyente con el tour del 151, z-index techado por el DialogHost del 164. |
| Anclas `:línea` de los docs ya corridas (150/151 implementados; WIP ajeno hoy) | §3.7: anclar por TEXTO; pre-flight `git status -- ` por archivo caliente; ejemplo real ya detectado: keydown de `App.tsx` citado en `:173-200` hoy vive en `:212`. |
| Un plan pisa el KPI de un plan anterior en un archivo compartido (`<tr>`, toolbar, columnas) | §6.8/§6.9 + §7(c): los greps del plan anterior se re-corren como parte del gate del plan nuevo. |
| El 156 aterriza en el medio de la serie y re-crea `nativeDialogByFile` | §6.6: si 164 ya pasó, la dimensión EXISTE — el implementador del 156 la encuentra, verifica el criterio de exclusión y marca su F6 satisfecho (fila prevista en §9). |
| Entorno roto produce falsos rojos en cadena | Gate 0 obligatorio + criterio NO-EMPEORAR + pytest por archivo con el intérprete canónico §8.10. |

## 11. Fuera de scope

- Implementar los 10 planes (eso es `implementar-plan-stacky`, plan por plan, siguiendo esta ruta).
- Re-criticar los planes (ya están en v2) o editar sus docs.
- Los periféricos 150/151/152/156/159 y las series DevOps (186-193, ruta 195), DB Compare (178-183, ruta 184) y RSI (167-170).
- "Copiar Enlace" de ejecuciones en el 194 (sigue diferido por su propio doc) y la CommandPalette profunda del 165 (su backlog).
- Crear flags, endpoints o componentes nuevos más allá de los módulos comunes (`flagGate.ts` — lo crea el 194, §6.1 Parte B; el hook cockpit `useHealthFlags` — §6.1 Parte A; `copyService.ts` — lo crea el 194) y el script §7bis.

## 12. Glosario + Orden de implementación + DoD

- **Serie UX 164-194:** los 10 planes de §1 (rango NO contiguo: 166-171, 176-184, 186, 188-191, 193, 195-196 NO integran esta serie).
- **Módulo común:** archivo con UN creador declarado y N consumidores por wrapper; regla de adopción §5 final.
- **Fail-open:** semántica de flag del §6.1 — ante duda, la feature queda ON (el kill-switch real es el backend).
- **Armado two-step / confirmación canónica / undo con gracia:** los 3 canales de protección, arbitrados por §6.5.
- **`useConfirm` vs `askConfirm` (C2 — leer antes de implementar 164/175/185):** la API REAL del 164 es `useConfirm()`/`useAlert()`/`useTextPrompt()` + `Dialog`/`ConfirmDialog`/`AlertDialog`/`PromptDialog`, exportada en `components/ui/index.ts` (164:136). **`askConfirm` NO es un export del 164:** es el nombre del campo `ConfirmFn` en el ctx del gateway del 175 (175:498) — que se implementa SOBRE `useConfirm()` — y jerga con la que el 185 se refiere al canal (185:236). Ningún plan crea un símbolo `askConfirm` en `ui/`.
- **Estado 2026-07-18 (pase de coherencia):** 165 F1-F3 y 164 F1 YA implementados (commits f49588eb→8619acfd y 9a57c378) ⇒ su puesto abajo es VERIFICAR gate satisfecho / completar fases restantes (164 F2+), no implementar desde cero. Lector de flag de los cockpit (172/173/174/175) = `useHealthFlags`/`/api/diag/health` (§6.1 Parte A); `flagGate.ts`/`HarnessFlags.list` (§6.1 Parte B) lo crea el 194 y lo usan 185/187/192/194.
- **Orden de implementación:** Gate 0 → 165 → 172 → [S1] → 164 → 194 → [S2] → 173 → 174 → [S3] → 185 → 187 → [S4] → 175 → 192 → [S5], con §7 tras cada plan.
- **DoD global de la ruta:** los 6 KPIs de §1 en verde y la tabla §9 completa sin `_pendiente_`.
