---
name: proponer-y-criticar-plan
description: Encadena en UNA corrida los dos primeros eslabones del pipeline de planes de Stacky — primero `proponer-plan-stacky` (escribe el siguiente `Stacky Agents/docs/<NN>_PLAN_*.md` con numeración calculada, no hardcodeada) y después `criticar-y-mejorar-plan` sobre ESE MISMO plan, con el número PINNEADO (nunca re-resuelto como "el más alto", para no criticar el plan de una sesión paralela). El juez corre en un subagente NUEVO con contexto limpio y, además del red-team estándar, está OBLIGADO a verificar los anclajes archivo:línea abriendo los archivos reales y a cruzar los criterios de aceptación entre fases buscando contradicciones — porque una crítica de la misma corrida no equivale a revisión independiente. Entrega el plan en v2 con veredicto binario y 2 commits (propuesta + crítica), sin push. Usala cuando digas "proponeme y criticá un plan", "armá el próximo plan ya criticado", "quiero el plan listo para implementar", o cuando ibas a correr `/proponer-plan-stacky` e inmediatamente `/criticar-y-mejorar-plan`. NO la uses para implementar (eso es `implementar-plan-stacky`) ni para criticar un plan viejo ya existente (eso es `criticar-y-mejorar-plan` a secas).
---

# Proponer y criticar plan Stacky (pipeline 1→2 en una corrida)

Corre los dos primeros eslabones del pipeline de planes (`proponer` → `criticar` → `implementar` → `supervisar`)
de forma encadenada y con gates duros entre ellos. El entregable final es **un solo plan nuevo, ya en v2,
con veredicto de juez**, listo para pasarle a `implementar-plan-stacky`.

Esta skill **no reimplementa** la lógica de las skills base: las **invoca** (tool `Skill`) y les agrega
exactamente tres cosas que un encadenado ingenuo hace mal:

1. **Pinnea el número.** El `<NN>` que devuelve la propuesta se le pasa **explícito** al juez. Prohibido
   dejar que el juez re-resuelva "el `NN` más alto": hay sesiones paralelas vivas en este árbol y ya pasó
   tres veces que dos sesiones coticen el mismo número (144-146, 214, 237-238). Si el juez re-resuelve,
   puede terminar criticando el plan de otra sesión.
2. **Fuerza un juez con contexto limpio.** El juez corre en un subagente **nuevo** que recibe SOLO la ruta
   del plan — nada del razonamiento con que se escribió. Un plan "criticado" por el mismo agente que lo
   propuso en la misma corrida **no tuvo revisión independiente**, y el header del v2 tiene que decirlo
   con honestidad.
3. **Agrega dos ejes de red-team obligatorios** que el autoexamen nunca ve (ver "Ejes extra obligatorios").

## Cuándo usarla

- Cuando querés el próximo plan de Stacky **ya endurecido**, sin tener que acordarte de correr las dos
  skills en orden ni de pasarle el número al juez.
- Cuando vas a delegar el plan a un modelo menor (Haiku, Codex, GitHub Copilot Pro) y no querés mandarle
  una v1 sin red-team.
- **NO** la uses para: criticar un plan ya existente (usá `criticar-y-mejorar-plan` a secas), implementar
  (`implementar-plan-stacky`), auditar implementaciones (`supervisar-implementaciones-planes`), ni para
  hacer brainstorming de dirección (`debatir-top5-evolucion-stacky` o el agente
  `StackyArquitectoBrainstormer`).

## Argumentos

- **Tema/necesidad (opcional).** Si el operador dice de qué quiere el plan, pasáselo tal cual a
  `proponer-plan-stacky` como orientación del gap a cerrar. Si no dice nada, la propuesta elige el gap
  ella misma leyendo los últimos planes (comportamiento normal de esa skill).

## Resultado (entregable)

1. Un archivo nuevo `Stacky Agents/docs/<NN>_PLAN_<SLUG>.md`, en **v2**, con encabezado de versión
   `v1 -> v2` y changelog.
2. La crítica adversarial `C1..Cn` rankeada por severidad + el **VEREDICTO** binario
   (APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO).
3. Al menos una `[ADICIÓN ARQUITECTO]` en el plan (regla de oro heredada del juez: nunca "nada que agregar").
4. **Dos commits** en la rama de trabajo: `docs(plan-<NN>): <slug corto>` y luego
   `docs(plan-<NN>): critica v1->v2`. **Sin `git push`** salvo pedido explícito del operador.
5. Un cierre de ≤10 líneas: ruta del plan, los 2 hashes, veredicto, cantidad de BLOQUEANTES/IMPORTANTES,
   y si el plan queda listo para `implementar-plan-stacky` o necesita otra pasada.

## Pasos de ejecución

1. **Foto en frío del directorio.** Listá `Stacky Agents/docs/` y anotá los `NN_` existentes. Esta foto es
   la línea base para detectar colisión al final. Si estás en `main`, creá rama antes de empezar.
2. **Eslabón 1 — proponer.** Invocá la skill `proponer-plan-stacky` (tool `Skill`), pasándole el tema del
   operador si lo hubo. Dejala hacer TODO su trabajo tal como está definida (incluido su propio commit).
3. **GATE 1 — capturar y verificar el `<NN>`.** De la salida del eslabón 1, extraé la **ruta exacta** del
   archivo creado y su `<NN>`. Verificá en disco que ese archivo existe y que **hay un solo** `<NN>_*` con
   ese número. Si el archivo no existe, o hay dos archivos con el mismo `NN`, o la propuesta no commiteó:
   **PARÁ** y reportá el problema; no lances el juez sobre un estado ambiguo. (Colisión de numeración:
   gana el primero commiteado; el `NN` más chico se queda con el número y el otro se renumera hacia arriba.)
4. **Eslabón 2 — criticar, con el número PINNEADO.** Invocá la skill `criticar-y-mejorar-plan` (tool
   `Skill`) pasándole **la ruta exacta** del plan del paso 3 como argumento. Nunca la invoques "a secas"
   dejando que resuelva el más alto. Además, agregale al prompt del arquitecto-juez el bloque
   "Ejes extra obligatorios" de abajo.
5. **GATE 2 — independencia del juez.** El juez DEBE correr en un subagente `Agent` nuevo que reciba solo
   la ruta del plan (+ rutas de 2-3 vecinos). No le resumas tu razonamiento de la propuesta, no le pases el
   borrador, no le digas qué te pareció bien. Si por algún motivo el juez corre inline (subagente no
   disponible), el encabezado del v2 debe decir textualmente:
   `Juez v2: mismo agente en rol adversarial (misma corrida) — NO es revisión independiente`.
   Si corrió en subagente limpio, decir: `Juez v2: subagente independiente, misma corrida, contexto limpio`.
   **Prohibido** escribir un sello que sugiera una independencia que no hubo.
6. **GATE 3 — verificación de numeración antes de cerrar.** Volvé a listar `Stacky Agents/docs/` en frío y
   compará contra la foto del paso 1. Si apareció otro archivo con el mismo `NN` (sesión paralela),
   aplicá la regla "gana el primero commiteado" y reportalo; no toques archivos untracked ajenos.
7. **Cerrar.** Devolvé el cierre de ≤10 líneas descrito en "Resultado". Si el veredicto fue **RECHAZADO**,
   decilo explícito y **preguntá** al operador si querés correr una segunda pasada del juez (v2 → v3) antes
   de implementar. No la corras sola: una segunda pasada automática del mismo agente no agrega
   independencia, agrega tokens.

## Ejes extra obligatorios para el juez (además de su checklist estándar)

Estos dos ejes son la razón de ser de esta skill encadenada. Un plan y su crítica nacidos en la misma
corrida ya cubren razonablemente los ejes genéricos (flags default ON, human-in-the-loop, determinismo,
paridad de runtimes, rollback) porque el autor los tenía a la vista al escribir. Lo que el autoexamen
**no puede ver** es lo fáctico y lo consistente. Pegá este bloque al prompt del arquitecto-juez:

```text
EJES EXTRA OBLIGATORIOS (esta crítica nace en la misma corrida que el plan, así que estos dos ejes
son los de mayor valor y NO son opcionales):

E1 — ANCLAJES VERIFICADOS CONTRA EL CÓDIGO REAL (no de memoria):
- Por CADA cita `archivo:línea`, `nombre_de_función`, `NOMBRE_DE_FLAG`, tabla, endpoint o comando que
  el plan use como evidencia: ABRÍ el archivo y confirmá que el símbolo existe y está donde dice.
- Clasificá cada anclaje: OK / DESFASADO (existe pero en otra línea — decí la línea real) /
  INEXISTENTE (el símbolo no está).
- Un anclaje INEXISTENTE es BLOQUEANTE. Un anclaje DESFASADO es IMPORTANTE, y pasa a BLOQUEANTE si
  sostiene una decisión de alcance (típico: "esto ya existe, no lo escribas" apoyado en una línea que
  ya no dice eso). Precedente real: 4 anclajes desfasados ~77 líneas, uno de ellos recortaba una fase
  entera. Un modelo menor abre el archivo, no encuentra el símbolo y alucina.
- En el v2, corregí los anclajes con la línea real; no los borres.

E2 — CRUCE DE CRITERIOS DE ACEPTACIÓN ENTRE FASES:
- Poné los criterios binarios de TODAS las fases uno al lado del otro y buscá pares mutuamente
  insatisfacibles (una regla prohíbe X como error mientras otro test exige 0 errores sobre un corpus
  que contiene un X real). Un modelo menor "resuelve" esa contradicción borrando un assert ⇒ FALSO VERDE.
  Toda contradicción es BLOQUEANTE.
- Cazá también el "alcance infinito con forma de criterio binario": criterios tipo "N/N y si algo no
  cierra se agrega lo que falte, no se relaja el test" que en realidad exigen construir un sistema
  completo no acotado. Es BLOQUEANTE: acotá el corpus/alcance en el v2.
- Verificá que ningún criterio de la fase Fk dependa de algo que recién se construye en Fk+1.

Reportá E1 y E2 como hallazgos numerados dentro de la misma lista C1..Cn, con su severidad.
```

## Restricciones no negociables

Se heredan íntegras de `proponer-plan-stacky` y `criticar-y-mejorar-plan` (paridad de los 3 runtimes con
fallback explícito; cero trabajo extra al operador — invisible u opt-in con default **ON** salvo que se cite
por escrito cuál de las 2 categorías de excepción aplica, (A) quema tokens en reposo o (B) escribe en un
sistema real del operador / destruye datos / le saca la decisión; human-in-the-loop innegociable;
mono-operador sin auth real; no degradar performance/seguridad/estabilidad/DX; backward-compatible; reusar
lo existente). **No las redefinas ni las relajes acá**: si una skill base cambia, esta hereda el cambio.

Propias de esta skill:

- **Un solo plan por corrida.** Esta skill produce UN plan criticado, no una serie. Para varios, corrémela
  varias veces (o usá `debatir-top5-evolucion-stacky` para definir la serie primero).
- **Número pinneado, siempre.** El juez recibe la ruta exacta. Nunca "el más alto".
- **Sello de independencia honesto.** Ver GATE 2.
- **Sin `push`**, sin `--no-verify`, sin `amend`/`reset`/`rebase`/`stash` — hay sesiones paralelas vivas en
  este árbol y esos comandos roban trabajo ajeno. Commitear con pathspec explícito:
  `git commit -- "Stacky Agents/docs/<NN>_PLAN_*.md"`.
- **No se implementa código.** El entregable es papel: el doc del plan en v2.

## Checklist de aceptación

- [ ] Se corrió `proponer-plan-stacky` primero y creó `Stacky Agents/docs/<NN>_PLAN_*.md` con `<NN>`
      calculado (no hardcodeado), commiteado.
- [ ] GATE 1 pasó: el archivo existe en disco y hay exactamente UN archivo con ese `NN`.
- [ ] A `criticar-y-mejorar-plan` se le pasó la **ruta exacta** del plan (número pinneado); no re-resolvió
      "el más alto".
- [ ] El juez corrió en subagente nuevo con contexto limpio (o, si no, el v2 lo declara textualmente como
      NO independiente). El sello del header es honesto.
- [ ] La crítica incluye E1 (cada anclaje `archivo:línea`/símbolo clasificado OK / DESFASADO / INEXISTENTE
      tras abrir el archivo real) y E2 (cruce de criterios entre fases) como hallazgos numerados.
- [ ] El plan quedó en v2 in place con encabezado `v1 -> v2` + changelog, y al menos una
      `[ADICIÓN ARQUITECTO]`.
- [ ] Hay veredicto binario con criterios explícitos.
- [ ] GATE 3 pasó: relectura en frío de `Stacky Agents/docs/` sin colisión de `NN` (o colisión reportada y
      resuelta por "gana el primero commiteado", sin tocar untracked ajenos).
- [ ] Dos commits en la rama (propuesta + crítica), con trailer de co-autoría del modelo activo, sin
      `--no-verify` y sin `push`.
- [ ] No se implementó código.
- [ ] El cierre de ≤10 líneas incluye ruta, los 2 hashes, veredicto, conteo de BLOQUEANTES/IMPORTANTES y si
      el plan queda listo para `implementar-plan-stacky`.
