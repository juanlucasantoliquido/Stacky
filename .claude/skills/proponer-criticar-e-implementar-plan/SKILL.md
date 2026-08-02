---
name: proponer-criticar-e-implementar-plan
description: Corre el pipeline COMPLETO de planes de Stacky en UNA corrida — `proponer-plan-stacky` → `criticar-y-mejorar-plan` → `implementar-plan-stacky` — con doce gates duros del ORQUESTADOR que ninguna de las tres skills base tiene sola: `<NN>` pinneado de punta a punta (nunca "el más alto": hay sesión paralela viva), veredicto leído del ARCHIVO commiteado y no de la prosa del subagente, UNA sola ronda de remediación que se decide recién con la lista completa de bloqueantes (juez + pre-flight), LÍNEA BASE DE TESTS medida por el orquestador ANTES de implementar — así la mitad de contraste se mide y no se le cree al implementador —, re-corrida propia de los tests al cerrar, y los guardianes del arnés que el plan nunca nombra (flags del arnés y ratchets) corridos igual, porque son trampa de COMMIT y con `--no-verify` prohibido tumban la corrida en el último paso. Commitea con pathspec explícito (nunca `git add -A`: robaría el trabajo de la sesión paralela) y NUNCA pushea. Usala cuando digas "proponé, criticá e implementá un plan", "armá el próximo plan y construilo", "el ciclo completo", "de punta a punta", "hacé todo el pipeline", "plan nuevo y dejámelo implementado", o cuando ibas a encadenar a mano las tres skills. NO la uses para: solo papel (`proponer-y-criticar-plan`), un plan ya criticado que solo falta construir (`implementar-plan-stacky` a secas), criticar un plan viejo (`criticar-y-mejorar-plan` a secas), auditar implementaciones (`supervisar-implementaciones-planes`), definir una SERIE de planes (`debatir-top5-evolucion-stacky`), ni corrida nocturna desatendida (`fragua-nocturna`: esta escribe código y NUNCA corre desatendida).
---

# Proponer, criticar e implementar plan Stacky (pipeline 1→2→3 en una corrida)

Corre los tres primeros eslabones del pipeline de planes (`proponer` → `criticar` → `implementar` →
`supervisar`) de forma encadenada, con gates duros entre eslabones. El entregable final es **un plan nuevo
en v2 (o v3) con veredicto, MÁS el código implementado y verificado**, en una rama, sin push.

Es la **extensión natural de `proponer-y-criticar-plan`**: hereda sus tres gates (número pinneado,
independencia del juez, colisión de numeración) y sus dos ejes de red-team obligatorios **E1** (verificar
cada anclaje `archivo:línea` abriendo el archivo real y clasificándolo OK / DESFASADO / INEXISTENTE) y
**E2** (cruce de criterios de aceptación entre fases). **No los dupliques acá: copiá textual el bloque
"Ejes extra obligatorios para el juez" de `.claude/skills/proponer-y-criticar-plan/SKILL.md` y pegalo al
prompt del juez. Son OBLIGATORIOS y no se relajan.**

Esta skill **no reimplementa** la lógica de las tres skills base: las **invoca** con la tool `Skill`. Lo que
agrega son (a) los **gates entre eslabones** y (b) los **overrides** de los defectos de las bases que, si no
se sobrescriben por escrito, un modelo menor hereda y rompe cosas (ver "Overrides duros").

## Cuándo usarla

- Cuando querés el próximo plan de Stacky **escrito, endurecido e implementado** sin tener que acordarte de
  correr tres skills en orden, pinnear el número, ni verificar vos los tests.
- Cuando el operador dice "hacé todo", "de punta a punta", "el ciclo completo", "armá el plan y construilo".
- Cuando vas a delegar a un modelo menor y necesitás que la verificación quede en el hilo principal.
- **NO** la uses para: solo papel (`proponer-y-criticar-plan`), solo construir un plan ya criticado
  (`implementar-plan-stacky`), criticar un plan viejo (`criticar-y-mejorar-plan`), auditar implementaciones
  (`supervisar-implementaciones-planes`), definir una serie de planes (`debatir-top5-evolucion-stacky`),
  ideación de dirección (agente `StackyArquitectoBrainstormer`), ni corrida nocturna desatendida
  (`fragua-nocturna`, que es solo papel). **Esta skill escribe código: NUNCA corre desatendida.**

## Argumentos

- **Tema/necesidad (opcional).** Si el operador dice de qué quiere el plan, pasáselo tal cual a
  `proponer-plan-stacky` como orientación del gap a cerrar. Si no dice nada, la propuesta elige el gap sola.
- **Ruta de un plan YA existente (opcional) — REANUDABILIDAD.** Si el operador pasa
  `Stacky Agents/docs/<NN>_PLAN_<SLUG>.md`, **salteá el eslabón 1** y usá ese `<NN>` como pinneado. Además,
  abrí el archivo y buscá el header de versión: si ya dice `v1 -> v2`, el eslabón 2 **ya corrió** —
  salteálo también y entrá directo por el gate G4. Esto permite retomar una corrida cortada a mitad sin
  duplicar commits ni volver a pagar subagentes.
  **Reanudar DENTRO del eslabón 3 (corte durante la implementación):** el header del doc no dice nada del
  código, así que la fuente de verdad es la memoria `plan-<NN>-status`, que **se escribe incrementalmente,
  una vez por fase cerrada** (paso 19), no solo al final. Al reanudar: leela, tomá la última fase con
  estado registrado, y arrancá el eslabón 3 en la **siguiente**. Si esa memoria no existe (corrida cortada
  antes de cerrar la primera fase), reconstruí el estado comparando `git status --porcelain` contra la
  línea base de G0b y **decilo en el cierre como estado reconstruido**, no como estado registrado.

## Resultado (entregable)

1. Un archivo `Stacky Agents/docs/<NN>_PLAN_<SLUG>.md` en **v2** (o **v3** si hubo remediación), con header
   de versión acumulado y changelog, y su VEREDICTO.
2. El **código del plan implementado** fase por fase en la rama de trabajo, con los tests **re-corridos por
   el orquestador** y su resultado real.
3. **3 commits** en el camino feliz (`docs(plan-<NN>): <slug>` → `docs(plan-<NN>): critica v1->v2` →
   `feat(plan-<NN>): <slug> — F0..Fn implementadas`), **4 si hubo remediación**. Todos con pathspec
   explícito. **Sin `git push`, nunca.**
4. La memoria `plan-<NN>-status` escrita/actualizada **por el orquestador** (un archivo, sin duplicar).
5. Un **cierre de ≤16 líneas** con hashes, estado real por fase con conteos reales, resultado de los
   guardianes del arnés, fases sin contraste desde la línea base, pendientes del operador y rojos previos
   (ver "Cierre").

## Overrides duros de las skills base (NO se heredan — sobrescribilos por escrito)

Heredar una skill base **no es gratis**: también se heredan sus defectos. Estos cinco puntos se
**sobrescriben** en esta corrida. Si los omitís, un modelo menor los copia tal cual.

1. **`git add -A` NO se hereda.** `implementar-plan-stacky` manda `git add -A` (su línea 115 y su PASO 5).
   En este árbol eso **roba trabajo ajeno**: hay una sesión paralela viva con decenas de archivos
   modificados y untracked. En esta skill **el implementador NO commitea** (prohibiéndoselo por escrito en
   su prompt) y el commit lo hace el **orquestador** con pathspec explícito (ver "Commits").
2. **El trailer de co-autoría NO se copia literal, y esto alcanza también a los commits de las bases.**
   Las **tres** bases tienen hardcodeado `Claude Opus 4.8 (1M context)` (`proponer-plan-stacky:38-39`,
   `criticar-y-mejorar-plan:35`, `implementar-plan-stacky:118` y `:226`) y **ya caducó**. Usá el nombre del
   **modelo ACTIVO de la corrida**, resuelto en runtime. Cualquier literal de modelo escrito en una skill
   caduca.
   **Ojo con la contradicción fácil:** los pasos 4 y 6 te dicen que dejes a las bases hacer *todo* su
   trabajo, **incluido su propio commit** — y ese commit se lo llevaría el literal caducado. Al invocarlas
   con la tool `Skill`, pasales en los `args`, textual:
   `TRAILER: usá el modelo ACTIVO de esta corrida en el Co-Authored-By, NO el literal de la skill.`
   El override vale para los **cuatro** commits, no solo para los dos del orquestador.
3. **`criticar-y-mejorar-plan` ofrece DOS formas de entrega** (reescritura in place —el default— **o** un
   bloque de patches). Si el juez elige patches, **NO hay v2 en disco** y el implementador construiría la
   **v1** sin que nada lo detecte. Al invocarla, **FORZÁ la reescritura in place** diciéndoselo textual:
   `ENTREGA OBLIGATORIA: reescritura v2 IN PLACE del archivo. La alternativa de patches está PROHIBIDA en
   esta corrida.` G4 lo verifica leyendo el header en el archivo.
4. **`implementar-plan-stacky` resuelve "el `NN_PLAN_*` más alto" si no recibe argumento** (su línea 125).
   Es el mismo agujero que la hermana ya cerró para el juez: en una corrida larga con sesión paralela,
   implementaría el plan de **otra** sesión. **Pasale SIEMPRE la ruta exacta.**
5. **El paso 7 de `proponer-y-criticar-plan` NO se hereda.** Esa skill, ante un RECHAZADO, **pregunta** al
   operador si correr otra pasada. Acá esa pregunta se **sustituye** por la ronda automática acotada de
   "Qué hacer con el veredicto". Si copiás su paso 7 tal cual, la skill se detiene en el caso **más
   frecuente** del repo (los 5 planes de la serie 286-292 fueron RECHAZADOS y se implementaron igual y bien)
   y no construye nunca nada.

## Pasos de ejecución

### 1. GATE G0 — RAMA

Corré `git rev-parse --abbrev-ref HEAD`.
- Si devuelve `main`: **creá la rama ANTES del eslabón 1** (el eslabón 1 ya commitea). Nombre:
  `plan/<slug-del-tema>` si hay tema, o `plan/auto-YYYYMMDD-HHMM` si no.
- Si devuelve cualquier otra cosa: **seguí en esa rama**. No la renombres nunca durante la corrida.

### 2. GATE G0b — FOTO EN FRÍO DEL ÁRBOL

Corré `git status --porcelain` y **guardá el set de rutas sucias como LÍNEA BASE**. Todo lo que ya estaba
sucio es **AJENO** y no entra en ningún commit de esta corrida. Tomá también la foto de
`Stacky Agents/docs/` (lista de `NN_`): es la línea base de G3.

### 3. Reanudabilidad

Si el operador pasó la ruta de un plan existente: salteá el eslabón 1, tomá su `<NN>` como pinneado y andá
al **paso 5 (G1)** para verificarlo. Si además el archivo ya tiene header `v1 -> v2`, salteá el eslabón 2 y
andá directo al **paso 8 (G4)**. Si el archivo ya tiene `v2 -> v3`, la ronda **ya se usó**: anotalo, porque
no queda otra (paso 10).

Si además existe la memoria `plan-<NN>-status`, la corrida se cortó **dentro** del eslabón 3: leela, tomá
la última fase con estado registrado y arrancá en la siguiente (ver "Argumentos"). Volvé a tomar la línea
base de tests (paso 13) **solo de los archivos de las fases que faltan** — los de las fases ya cerradas
están verdes y su contraste ya quedó registrado.

### 4. Eslabón 1 — PROPONER

Invocá la skill `proponer-plan-stacky` (tool `Skill`), pasándole el tema del operador si lo hubo. Dejala
hacer TODO su trabajo tal como está definida, **incluido su propio commit**. El orquestador **no duplica**
ese commit. **Inmediatamente después**, capturá el hash con `git rev-parse HEAD` (nunca por posición: ver
R3). Emitú una línea de progreso: `[1/3] propuesta commiteada <hash> — <ruta>`.

### 5. GATE G1 — NN PINNEADO (heredado)

De la salida del eslabón 1, extraé la **ruta exacta** y el `<NN>`. Verificá en disco que ese archivo existe
y que hay **UN SOLO** `<NN>_*` con ese número. Si el archivo no existe, o hay dos con el mismo `NN`, o la
propuesta no commiteó: **PARÁ** y reportá. Ese `<NN>` y esa ruta se usan de punta a punta: **ni el juez ni
el implementador re-resuelven nada**.

### 6. Eslabón 2 — CRITICAR, con el número PINNEADO

Invocá `criticar-y-mejorar-plan` (tool `Skill`) pasándole **la ruta exacta** del paso 5. Agregale al prompt:
(a) el bloque **"Ejes extra obligatorios para el juez" (E1 + E2)** copiado textual de
`.claude/skills/proponer-y-criticar-plan/SKILL.md`; (b) la línea de **entrega in place obligatoria** del
override 3. Capturá el hash con `git rev-parse HEAD` justo después. Progreso:
`[2/3] critica commiteada <hash>`.

### 7. GATE G2 — INDEPENDENCIA DEL JUEZ (heredado)

El juez DEBE correr en un subagente **nuevo** que reciba solo la ruta del plan (+ 2-3 vecinos). No le
resumas tu razonamiento, no le pases el borrador. El sello del header del v2 tiene que ser **honesto**:
`Juez v2: subagente independiente, misma corrida, contexto limpio` o, si corrió inline,
`Juez v2: mismo agente en rol adversarial (misma corrida) — NO es revisión independiente`. **Prohibido**
fingir una independencia que no hubo.

### 8. GATE G4 — VEREDICTO (leído del ARCHIVO, nunca de la prosa)

Abrí el `.md` commiteado y buscá con grep: (i) la línea `VEREDICTO` y (ii) el header de versión `v1 -> v2`.
- **Si el archivo no tiene veredicto NI header de versión ⇒ el eslabón 2 FALLÓ. PARÁ.** No es "aprobado por
  defecto": puede que el juez haya muerto a mitad de la reescritura, o que haya entregado patches.
- El gate **no decide por la etiqueta**: extraé la lista de **BLOQUEANTES** (`C#` marcados BLOQUEANTE) y
  verificá que cada uno tenga su entrada de resolución en el **CHANGELOG del v2**.
  **Bloqueante sin línea de changelog = BLOQUEANTE VIVO.**
- **Contá los bloqueantes vivos y ANOTALOS. NO decidas todavía si hay ronda:** primero corré el pre-flight
  del paso 9, que puede sumar más. La ronda es **una sola** y se decide con la lista **completa**.

### 9. GATE G5 — PRE-FLIGHT DE IMPLEMENTABILIDAD (lo corre el ORQUESTADOR, ANTES de gastar la ronda)

**Se corre IGUAL, siempre, aunque el veredicto sea APROBADO, y lo corre el orquestador — no el
implementador.** No es redundante con el veredicto: el juez responde *"¿es un buen plan?"*; el pre-flight
responde *"¿es ejecutable sin inferir?"*. Son ejes distintos: los 5 planes de la serie 286-292 fueron
RECHAZADOS por **supuesto de capacidad**, ninguno por ambigüedad — un plan puede estar RECHAZADO y ser
perfectamente ejecutable, y al revés. Lo corre el orquestador porque si lo corre el implementador (como
manda su PASO 0), rebota **después** de haberlo pagado.

**Va ANTES de la ronda a propósito.** Si primero gastás la ronda con los bloqueantes del juez y recién
después descubrís que a una fase le falta el criterio binario, tenés que parar por algo que el remediador
habría arreglado en la misma pasada, gratis. Las dos listas se **fusionan** y se atacan juntas.

Cuatro ítems **binarios** sobre el documento final:
- (i) ¿Tiene fases `F0..Fn` **ordenadas por dependencia**? SÍ / NO.
- (ii) ¿Cada fase nombra **archivos y símbolos EXACTOS**? SÍ / NO.
- (iii) ¿Cada fase declara **cómo se verifica, con el comando exacto**? SÍ / NO. Vale un archivo de test de
  pytest **o** `npx tsc --noEmit` para una fase de solo-frontend **o** un comando de verificación
  determinístico para una fase que no ejecuta código (p. ej. un `grep`/censo sobre el archivo que la fase
  escribe). Una fase de solo-documentación puede declarar **"sin test"** SI dice con qué comando se
  comprueba que quedó hecha. Lo que reprueba este ítem es la fase **sin forma de verificarse**, no la fase
  sin pytest — no gastes la ronda en una fase de UI legítima.
- (iv) ¿Cada fase tiene un **criterio de aceptación BINARIO**? SÍ / NO.

Cualquier NO ⇒ esos faltantes son **BLOQUEANTES SINTÉTICOS**. Sumalos a los bloqueantes vivos de G4 y pasá
al paso 10 con la lista **fusionada**.

### 10. Ronda de remediación ÚNICA (CONDICIONAL — ver "Qué hacer con el veredicto")

Corré la ronda si la lista fusionada (bloqueantes vivos de G4 **+** bloqueantes sintéticos de G5) tiene
**≥1 elemento** y **todavía no se usó la ronda**. Ver "Ronda de remediación (v2 → v3)": el remediador
recibe la lista completa, de una sola vez. Termina con el **commit 3** (v3 + veredicto del juez 2 en el
MISMO commit).

Es la **ÚNICA** ronda de toda la corrida. **Si la lista fusionada no queda vacía después de la ronda
⇒ PARÁ** y devolvé la decisión al operador (H1).

### 11. GATE G3 — COLISIÓN DE NUMERACIÓN, primera pasada

Relectura **en frío** de `Stacky Agents/docs/` y comparación contra la foto de G0b. Si apareció otro archivo
con el mismo `NN` (sesión paralela): gana **el primero commiteado**; reportalo y no toques untracked ajenos.
**Post-implementación NO se renumera nada** (los commits ya citan el `<NN>`): se reporta y punto.

### 12. GATE G6 — ALCANCE DE ESCRITURA

Barré el documento final buscando: publicar / commitear / pushear a ADO, GitLab o repo remoto **del
operador**; DDL o DML sobre una BD suya; deploy o rollback; borrado o purga; o criterios de aceptación que
exijan **credenciales reales**.

Por cada hit:
- Si la capacidad **se puede partir**: implementá la parte inerte (ver / planear / diffear) **en ON** y la
  parte que escribe **detrás de flag OFF citando (B) POR ESCRITO en el comentario de la `FlagSpec`**. El
  smoke real queda **PENDIENTE DEL OPERADOR** y **nunca se ejecuta** en la corrida.
- La fase se reporta `BLOQUEADA-POR-CREDENCIALES` y **la corrida SIGUE**. En este repo ese estado es lo
  **normal**, no una excepción (precedentes: 276 F12, 279, 287 §9.2). Un gate que parara acá mataría la
  skill.
- Si el criterio **CENTRAL** del plan es **inseparable** de la escritura real ⇒ **H4** (única pregunta).

### 13. GATE G6b — LÍNEA BASE DE TESTS (medida por el ORQUESTADOR, ANTES de implementar)

**Este gate es el que vuelve real la mitad de contraste.** Sin él, G7 re-corre el verde pero se come el
rojo **de palabra**, contada por el implementador — es decir, le cree exactamente a quien declaró que no
le iba a creer.

Antes de lanzar el eslabón 3, corré **vos** cada archivo de test que el plan nombra, con el comando de G7,
y **guardá el resultado como LÍNEA BASE**. Es barato: un plan nombra pocos archivos.

Interpretación de cada resultado inicial:

| Resultado en la línea base | Qué significa | Qué hacer |
|---|---|---|
| **exit 4** (archivo inexistente) | El test todavía no existe ⇒ **contraste probado por construcción**. Es el caso normal en TDD. | Anotá `CONTRASTE-OK (no existía)`. |
| **exit 1** con `X failed` | Rojo real medido por vos. | Anotá `CONTRASTE-OK (rojo medido)` + la última línea. |
| **exit 5** (no collected) | Archivo vacío o sin tests. | `CONTRASTE-OK`, pero avisalo: el plan nombra un archivo hueco. |
| **exit 0** con `X passed`, X > 0 | **El test que el plan nombra YA PASA antes de escribir una línea de código.** La fase es un no-op, o el test es vacuo (assert de ausencia, `any()`, criterio que no toca lo que la fase construye). | **HALLAZGO.** Anotá `SIN-CONTRASTE-DESDE-LA-BASE`. Esa fase **no puede** reportarse `IMPLEMENTADA` al final, por más verde que salga. Decilo en el cierre. |

**Sin esta foto, un test vacuo sale `IMPLEMENTADA` y nadie se entera.** La línea base también es el
**delta objetivo de los rojos ajenos**: lo que ya estaba rojo acá no cuenta contra el plan, y deja de ser
una opinión del cierre.

Nunca tomes la línea base con `stash`, `reset` ni `checkout -- <ruta>`: la tomás **antes** de tocar nada,
que es justo el momento en que no hace falta ninguno de los tres.

### 14. Eslabón 3 — IMPLEMENTAR, con la RUTA EXACTA

Invocá `implementar-plan-stacky` (tool `Skill`) **pasándole la ruta exacta** del documento final (override
4: jamás la dejes resolver "el más alto"). Delega en el subagente `StackyArchitectaUltraEficientCode`, que
recibe **SOLO la ruta del doc final** — nada de tu razonamiento (R1). Agregale al prompt, textual, el bloque
"Overrides para el implementador" de más abajo. Progreso: `[3/3] implementación en curso — F<k>`.

**CORTE DURO:** si **dos fases consecutivas** quedan `BLOQUEADA`, **parás**: commiteás lo verde y reportás.
**`BLOQUEADA-POR-CREDENCIALES` NO cuenta para el corte.** G6 ya declaró que ese estado es lo *normal* en
este repo (276 F12, 279, 287 §9.2); si sumara, un plan con dos humos seguidos se abortaría solo, y estarías
matando la corrida por comportarse exactamente como fue diseñada.

### 15. GATE G7 — ANTI-FALSO-VERDE (el gate que justifica esta skill)

**El orquestador re-corre él mismo, en el hilo principal, los archivos de test que nombra el plan.** No se
acepta ningún "pasó todo" del implementador.

- Comando exacto, **POR ARCHIVO**:
  `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>.py" -q`
- **PROHIBIDO `-k`** en la verificación final: sin match da **exit 0** (falso verde).
- **PROHIBIDO `pytest tests` entero** como veredicto: contaminación cruzada (~2260 errores).
- **Verde válido = exit 0 Y línea de resumen con `X passed`, con X > 0.**
  - **exit 4 = archivo inexistente** ⇒ el test que el plan nombra **no existe** ⇒ la fase **NO está verde**.
    Es el falso verde más barato del pipeline.
  - **exit 5 = no tests collected** ⇒ **rojo**.
- **MITAD DE CONTRASTE — se resuelve contra la LÍNEA BASE de G6b, no contra el reporte del implementador.**
  Una fase es `IMPLEMENTADA` solo si su archivo estaba `CONTRASTE-OK` en la línea base **y** está verde
  ahora. Si en la línea base estaba `SIN-CONTRASTE-DESDE-LA-BASE` (ya pasaba antes), la fase se reporta
  **`VERDE-SIN-CONTRASTE`** por más verde que salga. El output del rojo que reporte el implementador es
  **corroboración, no evidencia**: si contradice tu línea base, gana tu línea base y lo decís en el cierre.
- **Delta, no absoluto:** los rojos que ya estaban rojos en G6b se listan aparte, con su archivo, y **no
  cuentan** contra el plan — pero **tampoco sirven de excusa** para un test que el plan nombra.
- Si se tocó UI: en `Stacky Agents/frontend/` corré `npx tsc --noEmit`, **0 errores**, **corrido por el
  orquestador**. **Vitest NO está instalado**: no intentes correr tests JS.
- El reporte **pega la ÚLTIMA LÍNEA REAL** de cada comando.

### 16. GATE G9 — GUARDIANES IMPLÍCITOS (los que el plan NUNCA nombra)

**Se corre SIEMPRE, antes de commitear código, aunque el plan no los mencione.** Son trampa de **commit**,
no de edición: como esta skill prohíbe `--no-verify` (y hace bien), un guardián en rojo tumba la corrida en
el **último** paso, con todo ya construido y verde. Es el peor lugar posible para enterarse.

- **¿El plan introduce o flipea alguna FLAG?** Entonces corré, sí o sí:
  `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q`
  Recordá la mecánica de "Restricciones no negociables": **default ON = los TRES lugares** (`config.py` con
  `"true"`, `FlagSpec(default=True)`, key en `_CURATED_DEFAULTS_ON`); **default OFF = `"false"` y NINGÚN
  `default=` en la `FlagSpec`** — `default_is_known()` es `spec.default is not None`, así que hasta un
  `default=False` explícito la vuelve "conocida" y pone en rojo `test_default_known_only_for_curated`.
  Si el plan **flipea** una flag existente, buscá los tests que afirman el default viejo con
  `grep -rl "LA_KEY" "Stacky Agents/backend/tests/"` y actualizalos con el motivo escrito.
- **¿El plan agrega un ARCHIVO DE TEST NUEVO?** Hay que **registrarlo en los DOS scripts del ratchet** (el
  `.sh` y el `.ps1`), con la **misma cantidad en ambos** — su sintaxis difiere y ya divergen; el margen de
  la paridad está al límite, así que registrar en uno solo rompe. Después corré los metas:
  `test_harness_ratchet_meta.py` y `test_plan259_ratchet_script_parity.py`. Ojo con los dos escollos
  conocidos: el ratchet **no admite rutas con espacios**, y registrar un test en el ratchet obliga a
  **sacarlo de `harness_ratchet_allowlist.txt`** (hay un tercer estado de registro, no dos).
- **Si un guardián queda en rojo, arreglá la causa. NUNCA `--no-verify`.** Si no podés arreglarlo, no
  commitees código: reportá el guardián rojo con su output y dejá el trabajo en la working copy.
- Estos guardianes **no son fases del plan**: su resultado va en una línea aparte del cierre, no dentro del
  estado por fase.

### 17. Commit de implementación (lo hace el ORQUESTADOR, con pathspec explícito)

Ver "Commits". Construí el pathspec, commiteá, capturá el hash con `git rev-parse HEAD`.

### 18. GATE G8 — HIGIENE DEL COMMIT + segunda pasada de G3

Corré `git show --name-only --stat <hash>` y cruzá contra la foto de G0b. Si aparece una ruta **ajena**,
reportalo **en ALTO** al operador. **No revertir, no resetear, no `amend`** — hay sesión paralela viva.
Después, segunda pasada de **G3** (relectura en frío de `Stacky Agents/docs/`).

### 19. Memoria de estado (INCREMENTAL, una vez por fase)

Escribí/actualizá **vos, el orquestador**, la memoria `plan-<NN>-status` (un archivo, sin duplicar): fases
implementadas, flags nuevas con su default, controles de UI agregados, pendientes y bloqueos, con enlaces
`[[...]]`. **Los subagentes NO escriben memoria** y hay que prohibírselo también **a SUS subagentes**.

**Actualizala apenas cierra CADA fase, no solo al final.** Es lo que hace reanudable el eslabón 3: el header
del doc dice en qué versión quedó el papel, pero **nada** dice en qué fase quedó el código. Sin esta
escritura incremental, una corrida cortada a mitad de la implementación se reanuda desde cero sobre código
a medio escribir.

### 20. Cerrar

Devolvé el cierre de ≤16 líneas de la sección "Cierre".

## Qué hacer con el veredicto

**Clave conceptual:** el veredicto **diagnostica la v1**, pero **lo que se implementa es la v2, que ya trae
los fixes aplicados** — el juez reescribe, no solo dictamina. Exigir APROBADO es pedirle a un diagnóstico
del pasado que describa el presente. **El disparador no es la etiqueta: son los BLOQUEANTES VIVOS en la
v2.**

**La decisión se toma sobre la LISTA FUSIONADA**, nunca sobre la etiqueta sola: bloqueantes vivos de G4
(los `C#` BLOQUEANTE sin entrada de resolución en el changelog) **+** bloqueantes sintéticos de G5 (los
ítems del pre-flight que dieron NO). Por eso G5 corre **antes** de gastar la ronda.

| Veredicto | Lista fusionada (G4 + G5) | Acción |
|---|---|---|
| **APROBADO** | vacía | Implementá. Sin ronda. |
| **APROBADO-CON-CAMBIOS** | vacía | Implementá. Un IMPORTANTE sin entrada en el changelog se anota en el cierre; **no bloquea**. |
| **RECHAZADO (1ª vez)** | **vacía** (todos los bloqueantes con entrada de resolución en el changelog, y el pre-flight en 4/4) | **Implementá igual, sin ronda.** Este es el caso **FRECUENTE**: los 5 de la serie 286-292 cayeron acá y se implementaron bien. |
| **cualquiera** | **≥1 elemento**, ronda **sin usar** | **UNA** ronda de remediación v2 → v3 atacando la lista **completa**, de una sola pasada. |
| **cualquiera** | **≥1 elemento**, ronda **ya usada** | **PARÁ. No implementes.** (H1) |
| El juez 2 encuentra un bloqueante **NUEVO** introducido por la remediación | — | **PARÁ. No implementes.** (H1) |
| La verificación mecánica anti-relajación detecta que bajó el conteo de fases / criterios / tests sin declararlo | — | **PARÁ. No implementes.** (H1) |

Al parar por segunda vez, devolvé al operador **cada bloqueante sobreviviente** con su `C#` original, por
qué no se resolvió, y **tres opciones**: (a) implementar bajo su responsabilidad con
`implementar-plan-stacky` a secas; (b) acotar el alcance del plan; (c) descartarlo.

## Ronda de remediación (v2 → v3)

**Ejecutor:** un subagente **REMEDIADOR nuevo** (`StackyArchitectaUltraEficientCode`), en rol de
**arquitecto**, no de juez. **No lo hace el juez 1**: ya dio su mejor pasada al escribir la v2 y dejó
bloqueantes vivos.

**Entrada: la LISTA FUSIONADA.** El remediador recibe de una sola vez los bloqueantes vivos del juez
(`C#`) **y** los bloqueantes sintéticos del pre-flight G5 (numeralos `P1..Pn` para distinguirlos: son
defectos de *ejecutabilidad*, no de criterio del juez). Es la única pasada que hay: mandarle media lista y
descubrir la otra mitad después es exactamente el error que el reordenamiento de los pasos 9-10 evita.

**Trazabilidad:** el header **ACUMULA, nunca se pisa** — se conserva `v1 -> v2` y se **agrega** `v2 -> v3`.
Changelog nuevo `## CHANGELOG v2 -> v3` con **UNA entrada por ítem de la lista fusionada**, formato fijo:

```text
C<k> [BLOQUEANTE] — <qué objetaba> → <qué se cambió en el plan> → <fase/sección tocada>
```

Un bloqueante sin entrada = **no resuelto**, por definición.

### Prompt para el remediador

```text
ROL: Sos StackyArchitectaUltraEficientCode en rol de ARQUITECTO REMEDIADOR (no de juez). No re-criticás el
plan: resolvés una lista cerrada de bloqueantes en el documento.

ENTRADA: la ruta exacta del plan en v2 + la LISTA FUSIONADA, en dos bloques:
  - C# = BLOQUEANTES VIVOS del juez (C# + su texto): defectos de criterio.
  - P# = BLOQUEANTES SINTÉTICOS del pre-flight: defectos de EJECUTABILIDAD (falta el archivo/símbolo
    exacto, falta el comando de verificación, falta el criterio binario, fases fuera de orden de
    dependencia). Se arreglan escribiendo lo que falta en el plan, no discutiendo si hace falta.
ALCANCE CERRADO: no toques nada que no sea necesario para resolver esos N ítems. No agregues fases por
gusto, no reescribas el plan entero, no lances sub-subagentes. NO escribas memoria del agente, y
prohibíselo también a cualquier subagente que lances.
ESTA ES LA ÚNICA PASADA: no queda una segunda ronda. Lo que dejes sin resolver para la corrida.

ENTREGA: reescritura IN PLACE del mismo archivo, a v3. El header ACUMULA: conservá la línea `v1 -> v2` y
AGREGÁ `v2 -> v3`. Agregá un `## CHANGELOG v2 -> v3` con UNA entrada por ítem, formato fijo:
C<k> [BLOQUEANTE] — <qué objetaba> → <qué se cambió en el plan> → <fase/sección tocada>
P<k> [PRE-FLIGHT] — <qué faltaba> → <qué se escribió en el plan> → <fase/sección tocada>

ANTI-RELAJACIÓN (reglas duras — el falso verde en papel):
1. PROHIBIDO resolver borrando o debilitando un criterio de aceptación, un test nombrado o un assert. Si el
   criterio era insatisfacible, la resolución es ACOTAR EL ALCANCE explícitamente (decí qué corpus o
   subconjunto) y DECLARARLO; nunca "quitar el criterio".
2. PROHIBIDO mover un bloqueante a "fuera de alcance / trabajo futuro" sin decir qué queda del plan y por
   qué sigue valiendo la pena.
3. PROHIBIDO bajar el número de fases sin declarar el delta en el changelog.
4. CONTRA EL SUPUESTO DE CAPACIDAD (la causa real de los 5 rechazos de la serie 286-292): si el bloqueante
   es "el plan asume que el sistema ya sabe hacer X", la resolución OBLIGATORIA es UNA de dos:
   (a) agregar una fase previa que CONSTRUYE X, con su test nombrado y su criterio binario; o
   (b) rediseñar la fase para no necesitar X.
   Reformular el supuesto con otras palabras NO es una resolución.
5. El v3 CONSERVA todas las `[ADICIÓN ARQUITECTO]` del v2.

RESTRICCIONES: las mismas de criticar-y-mejorar-plan (3 runtimes con fallback, cero trabajo extra al
operador con default ON salvo excepción (A)/(B) citada por escrito, human-in-the-loop, mono-operador sin
auth, no degradar, backward-compatible, reuso). NO commitees: el commit lo hace el orquestador.

SALIDA: una línea por bloqueante (C# → resuelto cómo) + el archivo reescrito en disco. Densa, sin relleno.
```

### Verificación mecánica del anti-relajación (la hace el ORQUESTADOR)

**No se le cree al remediador.** Contá sobre el archivo, **antes y después**:
1. Número de **fases**.
2. Número de **líneas de criterio de aceptación**.
3. Número de **archivos de test nombrados**.

**Si alguno BAJÓ y el changelog no lo declara explícitamente ⇒ el gate FALLA y se trata como segundo
RECHAZADO: PARÁ.** Es objetivo y barato, no una opinión.

### Prompt para el juez 2

Subagente **NUEVO**, distinto del juez 1 y del remediador.

```text
ROL: Sos un JUEZ adversarial con alcance CERRADO. No re-criticás el plan entero.

RECIBÍS: la ruta del plan en v3 + la LISTA FUSIONADA original (los C# BLOQUEANTES del juez 1 y los P#
del pre-flight). Sin IMPORTANTES ni MENORES: no disperses el alcance.

NO RECIBÍS (y no los pidas): el razonamiento del remediador, el diff, el veredicto anterior como etiqueta,
ni nada del proceso de la propuesta.

MANDATO CERRADO: decidí, UNO POR UNO, si cada ítem está RESUELTO en el v3, y si la resolución introdujo un
BLOQUEANTE NUEVO.
- Para los C#: ¿la objeción de criterio quedó atendida, o solo reformulada con otras palabras?
- Para los P#: es una comprobación MECÁNICA sobre el texto del plan, no una opinión. ¿La fase nombra ahora
  el archivo y el símbolo exactos? ¿Declara el comando de verificación? ¿Tiene criterio binario? ¿Las
  fases quedaron en orden de dependencia? Respondé SÍ/NO citando la línea del plan que lo prueba.

Aplicá el eje E1 (verificar anclajes archivo:línea abriendo el archivo real y clasificándolos
OK / DESFASADO / INEXISTENTE) SOLO sobre los anclajes que el v3 AGREGÓ.

NO escribas memoria del agente, y prohibíselo también a cualquier subagente que lances. NO commitees.

SALIDA: por cada C#: RESUELTO / NO RESUELTO + una línea de por qué. Después: BLOQUEANTES NUEVOS (lista o
"ninguno"). Cerrá con VEREDICTO 2: APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO. Denso, sin relleno.
```

## Overrides para el implementador (pegá este bloque a su prompt)

```text
OVERRIDES DE ESTA CORRIDA (tienen prioridad sobre el texto de implementar-plan-stacky):

1. PLAN OBJETIVO: es EXACTAMENTE la ruta que te paso. PROHIBIDO resolver "el NN_PLAN_* más alto": hay una
   sesión paralela viva y podrías implementar el plan de otra sesión.
2. NO COMMITEES y NO uses `git add -A`. El commit lo hace el orquestador con pathspec explícito. Al
   terminar, DEVOLVÉ la lista textual de TODOS los archivos que tocaste (rutas completas).
3. PROHIBIDO: git push, --no-verify, amend, reset, rebase, stash, checkout -- <ruta>, borrar ramas. Ni
   siquiera para "probar el rojo de fábrica" de un test ajeno.
4. SI TENÉS QUE INFERIR ALGO, PARÁ Y REPORTÁ el punto ambiguo con la sección del plan; NO lo resuelvas con
   criterio propio. Vos no sabés "lo que el plan quiso decir".
5. CITÁ POR FASE la línea del plan que la especifica. Una fase sin cita es una fase INFERIDA.
6. MITAD DE CONTRASTE: por cada fase reportá el output del test en ROJO ANTES de escribir el código,
   además del verde posterior. AVISO: el orquestador YA midió él mismo la línea base de todos estos
   archivos antes de lanzarte. Tu rojo es CORROBORACIÓN, no evidencia — si contradice su medición, gana la
   de él. No inventes un rojo: ya está registrado cuál era.
7. ETIQUETAS DE FASE, exactas: `IMPLEMENTADA` / `PARCIAL` / `BLOQUEADA` / `BLOQUEADA-POR-CREDENCIALES`.
   Usá `BLOQUEADA-POR-CREDENCIALES` SOLO cuando lo único que falta es un humo con credenciales reales o
   una escritura en un sistema del operador (ítem 8). Es un estado normal, no un fracaso, y NO cuenta para
   el corte duro — pero mentirle la etiqueta a una fase que en realidad falló SÍ rompe el corte.
8. Antes de editar un archivo, RELEELO. La sesión paralela toca los mismos archivos: nunca apliques un diff
   sobre una foto vieja.
9. NADA de escrituras reales en sistemas del operador: no publicar/pushear a su ADO o GitLab, no DDL/DML en
   su BD, no deploy/rollback, no purgas, no usar credenciales reales. Lo que escriba va detrás de flag OFF
   citando (B) por escrito en la FlagSpec; el smoke queda PENDIENTE DEL OPERADOR.
10. NO escribas memoria del agente, y prohibíselo también a cualquier subagente que lances. La memoria
    plan-<NN>-status la escribe el orquestador.
11. Tests: por archivo, con el venv del repo. Sin -k. Sin `pytest tests` completo. Sin skip/xfail
    silencioso. Sin comentar tests. Sin relajar un criterio para cerrar una fase.
12. GUARDIANES DEL ARNÉS: si creás un archivo de test NUEVO, registralo en los DOS scripts del ratchet
    (.sh y .ps1, la MISMA cantidad en cada uno: su sintaxis difiere y ya divergen) y sacalo de
    harness_ratchet_allowlist.txt si estaba ahí. Si tocás flags, respetá la mecánica de los TRES lugares
    para el default ON. DECLARÁ en tu reporte qué guardianes tocaste: el orquestador los corre igual (G9),
    pero necesita saber cuáles esperar en rojo si no los registraste.
```

## HITL (dos paradas reales y dos prohibiciones)

- **H1 — Segundo RECHAZADO ⇒ PARAR** y devolver la decisión al operador. Dos rechazos seguidos piden al
  operador, no otra iteración: una tercera pasada del mismo linaje no agrega independencia, agrega tokens.
  **No se implementa.**
- **H2 — Escritura en un sistema real del operador: PROHIBICIÓN, no pregunta.** Publicar/pushear a su ADO o
  GitLab, DDL/DML en su BD, deploy/rollback, purga. **Nunca se ejecuta en la corrida, ni con confirmación**:
  queda como pendiente declarado.
- **H3 — `git push`: prohibición absoluta.** No se pregunta, no se hace.
- **H4 — Única pregunta condicional.** Si G6 detecta que el criterio **CENTRAL** del plan exige credenciales
  o escritura real y **no se puede partir** en flag OFF, preguntá **antes** de implementar, una sola vez,
  con dos opciones: *"¿construyo el código con el smoke pendiente, o paro?"*.
- **NO hay HITL entre propuesta→crítica ni entre crítica→implementación con veredicto favorable.** Una
  parada ahí convierte esta skill en "correr tres skills a mano" y **borra su razón de existir**.

## Commits

Camino feliz: **3**. Con remediación: **4**. Todos con **pathspec explícito**, ninguno con push.

1. `docs(plan-<NN>): <slug>` — **lo hace `proponer-plan-stacky`**. El orquestador no lo duplica; captura el
   hash con `git rev-parse HEAD` inmediatamente después.
2. `docs(plan-<NN>): critica v1->v2` — **lo hace `criticar-y-mejorar-plan`**. Ídem hash.
3. *(condicional)* `docs(plan-<NN>): remediacion v2->v3 y veredicto — <N> bloqueantes atacados` — **lo hace
   el ORQUESTADOR**, con el v3 **y** el bloque de veredicto del juez 2 en el **MISMO** commit, para que el
   doc nunca quede commiteado en estado no juzgado:
   `git commit -- "Stacky Agents/docs/<NN>_PLAN_<SLUG>.md"`
4. `feat(plan-<NN>): <slug> — F0..Fn implementadas` — **lo hace el ORQUESTADOR** (tipo `feat` / `fix` /
   `docs` según el plan).

**PATHSPEC EXPLÍCITO — OVERRIDE DURO.** `implementar-plan-stacky` manda `git add -A`; en este árbol eso
**roba trabajo ajeno**. Construí el pathspec así:

1. Tomá la lista de archivos que el implementador **declaró** haber tocado.
2. Cruzala contra `git status --porcelain` **MENOS la línea base de G0b**.
3. Commiteá: `git commit -- "<ruta1>" "<ruta2>" ...`

Un archivo sucio que **no** está en la lista declarada **NO entra** y se **reporta**. Un archivo untracked
que sí entra necesita `git add -- "<ruta>"` antes.

**Fases BLOQUEADAS: se commitea igual**, con mensaje
`feat(plan-<NN>): <slug> — F0..Fk implementadas, Fj BLOQUEADA (<motivo en 3 palabras>)`. El código verde ya
verificado es valor real. **Excepción:** si **cero** fases quedaron verdes, **no se commitea código** —
quedan solo los commits de papel y se reporta.

**Trailer:** `Co-Authored-By: <modelo ACTIVO de la corrida> <noreply@anthropic.com>`, resuelto en runtime.
**No hardcodees una versión de modelo** (las bases tienen `Claude Opus 4.8` y ya caducó). Nunca
`--no-verify`.

**Por qué no se pushea:** hay una **sesión paralela viva** (pushear publica su trabajo a medio hacer), el
operador revisa el diff antes, y el push manual es un **riel del producto**.

## Riesgos del encadenado (y su mitigación)

- **R1 — Deriva de contexto.** El implementador hereda el sesgo del proponedor, cree saber "lo que el plan
  quiso decir" y rellena ambigüedades por telepatía: se construye el plan **imaginado** y el doc queda como
  evidencia falsa. *Mitigación:* implementador en subagente **nuevo** que recibe **SOLO la ruta** del doc
  final, con el mandato "si tenés que inferir, PARÁ y reportá". Refuerzo objetivo: el reporte **cita por
  fase** la línea del plan que la especifica; **una fase sin cita es una fase inferida**.
- **R2 — Costo, duración y corte a mitad.** Es la corrida más cara del repo. *Mitigaciones:* (a) **corte
  duro** por 2 fases BLOQUEADAS consecutivas ⇒ parar, commitear lo verde y reportar; (b) **checkpoint
  transaccional**: cada eslabón cierra con su commit; (c) **una línea de progreso por eslabón**, para que el
  operador pueda matar la corrida sabiendo dónde quedó; (d) **reanudabilidad** (ver "Argumentos").
- **R3 — Sesión paralela viva.** (i) **Commitea ENTRE tus commits** (precedente real: plan 287) ⇒ `HEAD~1`
  **NO** es tu commit anterior: capturá cada hash con `git rev-parse HEAD` **justo después**, jamás por
  posición. (ii) Toca los **mismos archivos** que el implementador ⇒ releé el archivo antes de editar.
  (iii) `git add -A` (ver "Commits"). (iv) **PROHIBIDO `stash` / `reset` / `amend` / `rebase` /
  `checkout -- <ruta>` durante TODA la corrida**, incluido para "probar el rojo de fábrica".
- **R4 — El mismo linaje escribe el plan Y los tests que lo aprueban.** Si el plan especificó un test débil
  (assert de ausencia, `any()`, criterio sobre un archivo ya rojo), la fase queda verde **sin probar nada**.
  *Mitigación:* la **línea base de G6b**, medida por el orquestador antes de implementar. Un test que ya
  pasaba en la línea base no prueba nada de lo que la fase construyó, y la fase se marca
  `VERDE-SIN-CONTRASTE` por más verde que termine. Pedirle el rojo al implementador **no** alcanza: es la
  misma parte interesada.
- **R7 — Los guardianes que el plan no nombra tumban la corrida en el último paso.** Los ratchets y el
  centinela de flags son trampa de **commit**, no de edición. Con `--no-verify` prohibido, el hook rechaza
  el commit final con todo ya construido y verde: el peor momento y el más caro. *Mitigación:* **G9**, que
  los corre siempre antes de commitear, aunque el plan los ignore.
- **R5 — La ventana de colisión de numeración se ALARGA.** En la hermana dura minutos de papel; acá dura
  toda la implementación. *Mitigación:* **G3 dos veces** + `<NN>` pinneado en todos los mensajes de commit +
  regla explícita de que **un plan ya commiteado NO se renumera**.
- **R6 — Leer el veredicto de la prosa del subagente.** Si el juez murió a mitad de la reescritura, el doc
  puede no tener v2 ni veredicto y el encadenado seguiría con un "APROBADO-CON-CAMBIOS" que solo existió en
  un resumen. *Mitigación:* **G4 lee el ARCHIVO commiteado**.

## Presupuesto y delegación

Subagentes: **máximo 5**; camino feliz **3**. **NUNCA en paralelo** — todos operan sobre el mismo documento
y el mismo árbol.

| # | Subagente | Cuándo | Alcance |
|---|---|---|---|
| S1 | proponedor | siempre | lo lanza `proponer-plan-stacky` |
| S2 | juez 1 | siempre | lo lanza `criticar-y-mejorar-plan`; contexto limpio + E1/E2 sin relajar |
| S3 | remediador | condicional | `StackyArchitectaUltraEficientCode`, cerrado a los bloqueantes vivos |
| S4 | juez 2 | condicional | nuevo, cerrado a los N bloqueantes, E1 solo sobre anclajes nuevos |
| S5 | implementador | siempre | `StackyArchitectaUltraEficientCode`, recibe SOLO la ruta del doc final |

**Inline en el orquestador, JAMÁS delegado:** los doce gates (G0, G0b, G1, G2, G3, G4, G5, G6, **G6b**, G7,
G8, **G9**); leer el veredicto del archivo; el pre-flight de 4 ítems; el conteo anti-relajación; **la línea
base de tests, la re-corrida de los tests, los guardianes del arnés y el `tsc --noEmit`**; la construcción
del pathspec y los commits del orquestador; el cierre; la memoria `plan-<NN>-status`. Razón: **la
verificación es DONDE NACEN LOS FALSOS VERDES**, y el pathspec es **DONDE SE ROBA TRABAJO AJENO**.

**Acotamiento:** un solo plan por corrida · **una sola ronda de remediación**, decidida con la lista
fusionada de G4+G5 para no gastarla antes de conocerla · corte por **2 fases `BLOQUEADA` consecutivas**
(`BLOQUEADA-POR-CREDENCIALES` **no** cuenta) · el orquestador **no relee el repo** (su lectura es el doc +
`git status --porcelain` + el output de los tests) · subagentes **secuenciales**.

**Lo que suma G6b + G9 al presupuesto:** cero subagentes y dos tandas de `pytest` por archivo — la línea
base antes de implementar y los guardianes antes de commitear. Es el gasto más barato de toda la corrida y
cubre los dos modos de falla más caros: el test vacuo que sale verde, y el hook que rechaza el commit final
con todo ya construido.

## Cierre (≤16 líneas, sin adjetivos)

1. Ruta del plan + `<NN>` + versión final (v2 o v3).
2. Veredicto 1 (+ veredicto 2 si hubo) y **la lista fusionada al momento de implementar** (bloqueantes
   vivos de G4 + sintéticos de G5), o "vacía".
3. Los hashes en orden, con su rol.
4-N. **Una línea por fase:** `F# → IMPLEMENTADA | VERDE-SIN-CONTRASTE | PARCIAL | BLOQUEADA |
BLOQUEADA-POR-CREDENCIALES` + archivo de test + **estado en la línea base de G6b** + `X passed, Y failed`
**REAL** al cerrar.
N+1. `tsc --noEmit`: 0 errores / N errores / N-A.
N+2. **Guardianes del arnés (G9):** cuáles se corrieron, con su resultado, o "ninguno aplicaba".
N+3. **Fases sin contraste desde la línea base**, si las hubo, nombradas: el test ya pasaba antes de
     implementar. Si no hubo, decilo.
N+4. Pendientes del operador (humos con credenciales, flags a decidir, purgas).
N+5. Rojos que ya estaban rojos en la línea base, no atribuibles al plan.
N+6. Siguiente paso: `supervisar-implementaciones-planes` sobre el `<NN>`, o la decisión devuelta.

**Prohibido cerrar con "listo" o "todo verde" sin las líneas de evidencia.** Un cierre sin la línea N+2 y
sin la N+3 no es un cierre: son justo las dos que el operador no puede reconstruir solo.

## Restricciones no negociables

Se **heredan íntegras** de `proponer-plan-stacky`, `criticar-y-mejorar-plan` e `implementar-plan-stacky`:
paridad de los **3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro) con fallback explícito · cero
trabajo extra al operador (invisible u opt-in con default **ON**, salvo que se cite **POR ESCRITO** cuál de
las 2 categorías de excepción aplica: **(A)** quema tokens en reposo, **(B)** escribe en un sistema real del
operador / destruye datos / le saca la decisión) · **human-in-the-loop innegociable** · mono-operador sin
auth real · no degradar performance/seguridad/estabilidad/DX · backward-compatible · reusar lo existente ·
la **regla dura de CONFIG POR UI** de `implementar-plan-stacky` (backend + endpoint + control de frontend,
reusando una superficie existente) · la **mecánica exacta del default ON** (los TRES lugares: `config.py`,
la `FlagSpec` y `_CURATED_DEFAULTS_ON`).

**No las redefinas ni las relajes acá:** si una skill base cambia, esta hereda el cambio. Lo único que esta
skill **sobrescribe** son los cinco puntos de "Overrides duros".

## Qué NO debe hacer (y a dónde derivar)

- **Git:** no `push`, no `--no-verify`, no `amend` / `reset` / `rebase` / `stash` /
  `checkout -- <ruta>`, no `git add -A`, no borrar ramas, no renumerar un plan ya commiteado, no implementar
  en `main`.
- **Escrituras reales:** nada de publicar a ADO o GitLab, DDL/DML, deploy/rollback, purga, ni usar
  credenciales reales del operador.
- **Tests:** no `pytest tests` completo como veredicto, no `-k` en la verificación final, no `skip`/`xfail`
  silencioso, no comentar tests, no relajar un criterio para cerrar una fase, no aceptar como contraste el
  rojo que reporta el implementador cuando la línea base de G6b dice otra cosa.
- **Guardianes:** no saltear G9 porque "el plan no los nombra" — son trampa de commit, no de edición. Si un
  guardián queda rojo, se arregla la causa: **jamás `--no-verify`**, jamás desregistrar un test del ratchet
  para que pase, jamás registrar en un solo script de los dos.
- **Memoria:** los subagentes **NO escriben memoria** (mienten sobre haberlo hecho) y hay que prohibírselo
  también **a SUS subagentes**; la memoria `plan-<NN>-status` la escribe el **orquestador**, un archivo, sin
  duplicar.
- **Derivaciones:** más de un plan o definir la serie → `debatir-top5-evolucion-stacky` · criticar un plan
  viejo existente → `criticar-y-mejorar-plan` a secas · auditar planes ya implementados →
  `supervisar-implementaciones-planes` · plan ya escrito y criticado, solo construirlo →
  `implementar-plan-stacky` a secas · solo papel → `proponer-y-criticar-plan` · ideación de dirección →
  agente `StackyArquitectoBrainstormer` · corrida nocturna desatendida → `fragua-nocturna` (solo papel;
  **esta skill NUNCA corre desatendida**: implementa código).

## Checklist de aceptación

- [ ] **G0:** no se trabajó en `main`; si se estaba en `main`, se creó rama **antes** del eslabón 1.
- [ ] **G0b:** se tomó la foto `git status --porcelain` ANTES de empezar y se usó como línea base del
      pathspec.
- [ ] **G1:** el `<NN>` quedó pinneado; hay exactamente un archivo con ese número; al juez **Y AL
      IMPLEMENTADOR** se les pasó la RUTA EXACTA — ninguno re-resolvió "el más alto".
- [ ] **G2:** el juez corrió en subagente nuevo con contexto limpio y el sello del header del v2 es honesto.
- [ ] **G3** se corrió **DOS veces** y no hubo colisión sin reportar.
- [ ] **G4:** el veredicto se leyó del **ARCHIVO commiteado**, no del resumen del subagente; se contaron los
      BLOQUEANTES VIVOS contra el changelog.
- [ ] **G5:** el pre-flight de 4 ítems lo corrió el **orquestador** sobre el doc final, **antes de gastar la
      ronda** y antes de lanzar al implementador; sus faltantes se fusionaron con los bloqueantes de G4 en
      UNA sola lista.
- [ ] El ítem (iii) del pre-flight no rebotó fases legítimas de solo-frontend (`tsc --noEmit`) ni de
      solo-doc con comando de verificación declarado.
- [ ] **G6:** toda escritura en un sistema real quedó detrás de flag OFF citando **(B)** por escrito, o se
      paró en H4; **no se ejecutó ninguna escritura real**.
- [ ] **G6b:** la **línea base de tests** se midió **antes** de implementar, archivo por archivo, y quedó
      registrada con su exit code. Toda fase cuyo test **ya pasaba** en la línea base quedó nombrada en el
      cierre y marcada `VERDE-SIN-CONTRASTE`, no `IMPLEMENTADA`.
- [ ] **G7:** el orquestador **RE-CORRIÓ** los tests **por archivo** con el venv del repo; sin `-k`, sin
      suite completa; verificó exit code **Y** `X passed` con X > 0; exit 4 y exit 5 se trataron como rojo.
- [ ] La mitad de contraste se resolvió **contra la línea base de G6b**, no contra el rojo que reportó el
      implementador (que es corroboración, no evidencia).
- [ ] **G9:** los guardianes implícitos se corrieron **antes de commitear**, aunque el plan no los nombrara:
      `test_harness_flags.py` si hubo flags, y los metas del ratchet + registro en los **DOS** scripts si
      hubo archivo de test nuevo. Ninguno quedó en rojo, y **no** se usó `--no-verify`.
- [ ] Si se tocó UI, `npx tsc --noEmit` lo corrió el orquestador y dio **0 errores**.
- [ ] El corte duro contó solo fases `BLOQUEADA`; `BLOQUEADA-POR-CREDENCIALES` **no** sumó.
- [ ] Como máximo **UNA** ronda de remediación, decidida con la lista fusionada; si la lista no quedó vacía
      después de la ronda se **PARÓ** y se devolvió la decisión al operador con las tres opciones.
- [ ] Si hubo v3: el header **acumula** `v1 -> v2` **Y** `v2 -> v3`, hay una entrada de changelog por
      bloqueante, y el conteo de fases / criterios / tests **NO bajó** sin declararlo.
- [ ] Los commits usan **pathspec explícito**; **no** se usó `git add -A`; `git show --name-only` no trajo
      rutas ajenas a la línea base (G8).
- [ ] **3 commits** (o 4 con remediación), en orden, sin `--no-verify` y **SIN push**; los **cuatro** con
      trailer del **modelo ACTIVO** — incluidos los dos que hacen las skills base, a las que se les pasó el
      override del trailer en los `args`.
- [ ] Si quedaron fases bloqueadas se commiteó lo verde con la deuda en el mensaje; si **nada** quedó verde,
      **no** se commiteó código.
- [ ] Se escribió/actualizó la memoria `plan-<NN>-status` (la escribió el **orquestador**, no un subagente)
      **una vez por fase cerrada**, no solo al final, para que el eslabón 3 quede reanudable.
- [ ] El cierre tiene ≤16 líneas con hashes, estado real por fase con conteos reales, resultado de los
      guardianes (G9), fases sin contraste desde la línea base, pendientes del operador y rojos previos.
