---
name: debatir-top5-evolucion-stacky
description: Orquesta un DEBATE adversarial multironda entre los dos arquitectos de Stacky — `StackyArquitectoBrainstormer` (diverge: ideas audaces game-changer) y `StackyArchitectaUltraEficientCode` (converge: poda, aterriza y verifica en código) — para destilar los PRÓXIMOS 5 PLANES más rigurosos y game-changers de la historia de Stacky (los que marcan un antes y un después). No es un brainstorm suelto: cada idea sobreviviente debe estar ANCLADA EN EVIDENCIA real del repo (archivo:línea), pasar un gate anti-incremental, respetar los rieles duros de Stacky, y superar al juez (mentalidad `criticar-y-mejorar-plan`). El bucle NO se detiene hasta alcanzar convergencia objetiva ("verdadera evolución"), no por vibra. Entrega un roadmap top-5 rankeado y listo para formalizarse con `proponer-plan-stacky`. Usala cuando quieras romper el molde incremental y definir el próximo salto evolutivo de Stacky con rigor de juez, no una lista de deseos.
---

# Debatir Top-5 Evolución Stacky (ultimate combo: brainstorm ⇄ ultra-eficiencia ⇄ juez)

Esta skill formaliza y endurece el "ultimate combo": un **debate adversarial multironda** entre los dos
arquitectos de Stacky que produce los **5 próximos planes game-changer** — los más rigurosos y de mayor
salto evolutivo posibles, los que marcan un antes y un después en la historia del producto.

Es DISTINTA de `proponer-plan-stacky` (que redacta UN plan formal numerado) y de
`criticar-y-mejorar-plan` (que juzga UN plan). Esta skill opera un nivel arriba: **decide CUÁLES 5 saltos
valen la pena** antes de formalizar ninguno. Su salida alimenta a `proponer-plan-stacky` (uno por
finalista).

Precedente real en el repo: el debate del 2026-06-20 (4 rondas) destiló el top-5 que se formalizó como
los planes 53–57. Esta skill convierte ese patrón ad-hoc en un proceso repetible y **mejor**: con
anclaje en evidencia obligatorio, gate anti-incremental, criterio de parada objetivo y dedup contra los
planes ya existentes.

## Qué la hace MEJOR que pedir el debate a mano

1. **Evidencia o muerte.** En el debate real, los agentes afirmaron cosas FALSAS (p. ej. que
   `services/speculative.py` estaba desconectado — sí estaba registrado en `api/__init__.py`). Regla
   dura: ninguna idea sobrevive una ronda si su premisa no está **verificada en código (archivo:línea)**.
   Premisa falsa ⇒ idea descartada o reformulada, sin excepción.
2. **Gate anti-incremental.** "Game-changer" = marca un antes y un después. Toda idea cruza un umbral de
   novedad+impacto o queda fuera. Un refactor, un fix o un tuning NO es un top-5.
3. **Criterio de parada objetivo.** "No frenar hasta que sea una evolución" se operacionaliza con una
   Definición de Convergencia binaria (abajo). El bucle termina por criterio, no por cansancio.
4. **Dedup contra el estado real.** Se contrasta contra TODOS los planes `NN_*` existentes y contra la
   memoria de roadmap, para no reproponer lo ya planificado/implementado.
5. **Juez integrado.** Cada finalista pasa por la mentalidad de `criticar-y-mejorar-plan` (rieles duros)
   ANTES de entrar al top-5, no después.

## Cuándo usarla

- Cuando los últimos planes se sienten incrementales y querés definir el próximo SALTO de Stacky.
- Cuando querés un roadmap top-5 con rigor de juez, no una lista de deseos.
- Justo antes de una tanda de `proponer-plan-stacky`: esta skill decide QUÉ 5 formalizar y en qué orden.
- NO la uses para redactar un plan formal (eso es `proponer-plan-stacky`) ni para criticar uno existente
  (eso es `criticar-y-mejorar-plan`) ni para implementar producto.

## Resultado (entregable)

1. Un documento roadmap nuevo en `Stacky Agents/docs/_roadmap/TOP5_<YYYY-MM-DD>_<SLUG>.md` (carpeta
   `_roadmap/` para **no consumir** la secuencia numérica `NN_` de planes formales). Contiene:
   - El **TOP-5 rankeado** por orden de implementación (dependencias primero), cada ítem con: título,
     tesis del salto (antes→después), evidencia ancla (archivo:línea), score (ver rúbrica), riel-check de
     los guardarraíles, y "siguiente paso = `proponer-plan-stacky`".
   - La **bitácora del debate**: rondas, qué propuso el Brainstormer, qué podó/aterrizó el
     UltraEficientCode, qué premisas se verificaron o se cayeron por falsas, y el veredicto del juez.
   - El **cementerio**: ideas descartadas con el motivo (premisa falsa / incremental / rompe riel / ya
     existe), para no reproponerlas en el futuro.
2. Un **resumen final de 8 líneas**: el top-5 en una línea cada uno + por qué convergió.
3. Una **memoria actualizada** del roadmap (ver Paso 6). No se hace commit salvo pedido del operador.
4. **No se redacta ningún plan formal ni se implementa código** en esta corrida.

## Definición de Convergencia (criterio de parada — binario)

El bucle de rondas SOLO se cierra cuando se cumplen TODAS:

- [ ] Hay **entre 3 y 5** ideas finalistas (top-5 es un TECHO, no una cuota), rankeadas por dependencia.
      Forzar 5 cuando solo 3 superan el gate reintroduce el incrementalismo que esta skill existe para
      matar: "menos pero todas game-changer" es un resultado HONESTO y preferible a rellenar. Si quedan <3
      tras agotar las rondas, reportalo como señal (el pozo de saltos puede estar seco tras tantos planes).
- [ ] Cada finalista tiene **premisa verificada en código (archivo:línea)** — cero premisas asumidas.
- [ ] Cada finalista pasa el **gate anti-incremental** (score de novedad+impacto ≥ umbral, ver rúbrica).
- [ ] Cada finalista respeta los **5 rieles duros** (abajo) o degrada con fallback explícito.
- [ ] Ninguna finalista **duplica** un plan `NN_*` existente ni un ítem ya implementado.
- [ ] El **juez** (UltraEficientCode en modo adversarial) emitió veredicto distinto de RECHAZADO para todas.
- [ ] Hubo **una ronda de cierre estable**: el conjunto de finalistas y su ranking NO cambiaron respecto
      de la anterior, Y el juez justificó explícitamente que ya no queda nada por matar/reformular (ver la
      resolución de la tensión kill-≥1 vs. estabilidad, abajo).

**Resolviendo kill-≥1 vs. estabilidad (no es contradicción, es secuencia).** La regla "el juez mata o
reformula ≥1 idea por ronda" aplica a TODAS las rondas MENOS la de cierre. En la ronda de cierre el juez
hace lo contrario: declara y **justifica** que ningún finalista merece morir ni reformularse — y ESA
declaración justificada es justamente la señal de estabilidad. Es decir, no convergís cuando el juez deja
de poder matar; convergís cuando, pudiendo, argumenta que ya no debe. Si el juez sigue matando, no
convergiste: corré otra ronda.

Si falta cualquiera, corré OTRA ronda. Si tras 6 rondas no converge, NO bajes el umbral: reportá el
bloqueo, las 2-3 ideas en disputa y por qué, y pedí decisión al operador (es un trade-off de negocio
real, no algo que la skill deba resolver sola).

**Anti-colusión (el pruner y el juez son el mismo agente).** UltraEficientCode poda, puntúa Y juzga,
y ambos subagentes comparten contexto de "arquitecto Stacky" — riesgo de rubber-stamp (en el debate
pasado pasaron premisas falsas). Mitigaciones obligatorias: (a) el juez debe **matar o reformular al
menos 1 idea por ronda** o justificar explícitamente por qué NO mató ninguna; (b) **vos, el orquestador,
verificás de primera mano las citas archivo:línea en disputa** (al menos las de las 2-3 ideas más
peleadas) en vez de confiar ciegamente en lo que reporta el subagente; (c) si una cita no se sostiene al
abrir el archivo, la idea cae igual que si la premisa fuera falsa.

## Economía de la orquestación (la frugalidad también aplica a ESTA skill)

La skill predica UltraCode a los subagentes; no seas hipócrita en la orquestación. Reglas duras de costo:

- **Un solo spawn por rol, continuado — no re-spawnear cada ronda.** Lanzá `StackyArquitectoBrainstormer`
  y `StackyArchitectaUltraEficientCode` con `Agent` UNA vez (ronda 1). De la ronda 2 en adelante, continuá
  CADA uno con `SendMessage` a su ID/nombre, NO con un `Agent` nuevo. Un `Agent` fresco arranca en frío,
  re-deriva el contexto de Stacky y —lo más grave— olvida sus propios argumentos y las objeciones del
  juez, lo que vacía la "ronda de réplica" (el Brainstormer ya no puede defender SU idea, es otra
  instancia). Continuar preserva el hilo del debate y no re-paga el arranque en frío.
- **Techo de rondas = 6 (ya definido) y techo de gasto.** Si llegás a la ronda 4 sin acercarte a la
  Convergencia, hacé un balance honesto: ¿el pozo está seco (reportá <3 y pará) o el debate gira en falso
  (reportá las ideas en disputa y pedí decisión)? No quemes las 6 rondas por inercia.
- **El orquestador no re-explora lo que el subagente ya trajo.** Tu trabajo entre rondas es: verificar de
  primera mano las 2-3 citas en disputa (anti-colusión) y pasar objeciones. No releas el repo entero.

## Si ya existe un roadmap previo (re-corrida)

Antes de la ronda 1, mirá si hay un `Stacky Agents/docs/_roadmap/TOP5_*.md` previo. Si lo hay:

- Cruzá sus finalistas contra los planes `NN_*`: los que YA se formalizaron/implementaron van al contexto
  de dedup (no se reproponen). Los que **nunca se formalizaron** son input del debate nuevo: o se
  re-confirman como finalistas (si siguen siendo game-changer y su premisa sigue viva) o se **retiran al
  cementerio con motivo** ("superado por plan NN", "premisa caducó", "ya no es prioridad"). No los ignores
  en silencio ni los redebatas desde cero.
- El roadmap nuevo enlaza al previo y registra qué cambió respecto de él (qué sobrevivió, qué se retiró).

## Rieles duros (no negociables — valen para TODA idea finalista)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cada idea funciona en los 3
  o degrada con fallback explícito. Nada atado a un runtime (ojo deudas de paridad reales: style_memory
  copilot-only, speculative.py).
- **Cero trabajo extra al operador:** invisible/automático u opt-in con default seguro (off).
- **Human-in-the-loop innegociable:** amplificar al operador, jamás reemplazarlo. Autonomía proactiva que
  lo saque del lazo = RECHAZO. (Excepción ya decidida: épica-desde-brief auto-publica; no reabrir.)
- **Mono-operador sin auth real:** nada de RBAC/multiusuario/roles/403 (es teatro; `current_user` es un
  header sin validar).
- **No degradar** performance/seguridad/estabilidad/DX; backward-compatible; reusar lo existente (memoria
  colaborativa, flags del arnés, telemetría, gates golden) en vez de reinventar.

## Rúbrica de scoring (para rankear y aplicar el gate anti-incremental)

Cada idea se puntúa 1–5 en cuatro ejes; el gate exige **(Impacto + Novedad) ≥ 8 y Factibilidad ≥ 3**:

- **Impacto (1–5):** ¿mueve la aguja del producto de forma medible (KPI/loop cerrado)? 5 = antes/después.
- **Novedad (1–5):** ¿es un salto de capacidad (reactivo→anticipatorio, átomo→molécula, observar→ACTUAR)?
  1 = incremental/tuning ⇒ NO califica.
- **Factibilidad (1–5):** ¿es construible sin código de proveedor nuevo ni romper rieles? (p. ej.
  LLM-as-judge horneado = 1, el cerebro interno está capado a sonnet sin Anthropic directo).
- **Rigor de evidencia (1–5):** ¿la premisa está anclada en archivo:línea verificado? <3 ⇒ vuelve a la
  arena hasta verificar o cae.

El ranking final del top-5 es por **orden de implementación** (dependencias primero), no por score
crudo; el score decide quién ENTRA, las dependencias deciden el ORDEN.

## Pasos de ejecución

1. **Orientarte barato (sin releer todo).** Listá `Stacky Agents/docs/` y tomá el `NN` máximo de los
   `NN_*` (dinámico, nunca hardcodeado) para saber dónde está el estado del arte. Escaneá los **títulos de
   TODOS los `NN_*`** (barato: solo nombres de archivo / primer encabezado) para poder deduplicar contra
   todo el catálogo — no solo contra los recientes — y leé **en profundidad** solo los 4-5 de número más
   alto + el índice de `docs/sistema/`. Leé la memoria de roadmap previa (`top5-roadmap-debate` y vecinas)
   y el `TOP5_*.md` previo si existe (ver "Si ya existe un roadmap previo") para no repetir el debate ni
   reproponer lo ya destilado.
2. **Ronda generativa (Brainstormer) — spawn único.** Lanzá `StackyArquitectoBrainstormer` con `Agent`
   (UNA sola vez en toda la corrida) usando el "Prompt para el Brainstormer". Pide un portafolio de
   **8-12 ideas audaces** (más de las 5 finales, para que haya competencia), cada una con: tesis del salto
   (antes→después), el eje de novedad que ataca, y la **premisa verificable** que habría que confirmar en
   código. Guardá su ID para continuarlo después con `SendMessage`.
3. **Ronda de poda + verificación (UltraEficientCode) — spawn único.** Lanzá
   `StackyArchitectaUltraEficientCode` con `Agent` (UNA sola vez) usando el "Prompt para el UltraEficientCode
   + Juez". Verifica CADA premisa en el código (archivo:línea), mata las falsas o incrementales, aterriza
   las viables (reuso, flags, paridad), aplica la rúbrica y dicta veredicto por idea. Devuelve un ranking
   provisional. Guardá su ID.
4. **Iterar hasta convergencia — continuando, NO re-spawneando.** De la ronda 2 en adelante continuá CADA
   rol con `SendMessage` a su ID (nunca un `Agent` nuevo: ver "Economía de la orquestación"). Pasá el
   ranking provisional + las objeciones de vuelta al Brainstormer (réplica: defender, reformular o
   reemplazar las ideas caídas) y de nuevo al UltraEficientCode. Antes de cada ronda de poda, verificá vos
   mismo las 2-3 citas archivo:línea en disputa (anti-colusión). Repetí hasta cumplir TODA la "Definición
   de Convergencia". Llevá la bitácora (qué cambió cada ronda). No frenes por cansancio; frená por
   criterio (ni quemes las 6 rondas por inercia: balance honesto en la ronda 4).
5. **Materializar el roadmap.** Creá `Stacky Agents/docs/_roadmap/TOP5_<YYYY-MM-DD>_<SLUG>.md` con el
   top-5 rankeado, la bitácora del debate y el cementerio (formato en "Resultado"). Validá contra la
   "Checklist de aceptación".
6. **Persistir aprendizaje.** Actualizá la memoria de roadmap (un archivo, no duplicar): top-5 nuevo,
   evidencia clave verificada, e ideas del cementerio con motivo. Enlazá `[[...]]` a las memorias de
   estado de plan relevantes.
7. **Cerrar con handoff.** Devolvé la ruta del roadmap + resumen de 8 líneas + la sugerencia explícita:
   "para formalizar el #1, corré `proponer-plan-stacky`". No hagas commit salvo pedido del operador.

## Si los subagentes no están disponibles

Si `StackyArquitectoBrainstormer` o `StackyArchitectaUltraEficientCode` no se pueden lanzar como
subagentes, ejecutá vos mismo AMBOS roles inline, alternando explícitamente de sombrero ("ahora como
Brainstormer…", "ahora como UltraEficientCode/Juez…") con los mismos prompts. El rigor del proceso
(evidencia, gate, convergencia) NO cambia.

OJO: inline desaparece la independencia adversarial — un solo modelo en las dos sillas tiende al
auto-acuerdo. Compensalo deliberadamente: cuando te pongas el sombrero de juez, **steelmaneá la objeción
más fuerte contra tu propia idea anterior** antes de absolverla, y mantené la regla de matar/reformular
≥1 por ronda. Si no podés argumentar en contra de una idea, no la entendiste lo suficiente para aprobarla.

## Prompt para el Brainstormer

```text
ROL: Sos StackyArquitectoBrainstormer. Tu fuerza es la INNOVACIÓN y la CREATIVIDAD: imaginás saltos
audaces, no obvios y de altísimo valor para Stacky. Divergís en grande; otro valida. Pero hoy jugás
dentro de rieles duros y con una vara alta: GAME-CHANGER o nada.

CONTEXTO: Te paso el NN máximo de planes existentes y los 4-5 planes más recientes. NO repitas lo ya
planificado/implementado. Buscamos los PRÓXIMOS 5 saltos que marquen un antes y un después en Stacky.

TAREA: Proponé un portafolio de 8-12 ideas (más de 5, para que compitan). Por cada idea:
- TÍTULO corto y vendedor.
- TESIS DEL SALTO en formato "ANTES: <cómo es hoy> → DESPUÉS: <la nueva capacidad>". Apuntá a ejes de
  salto reales: reactivo→anticipatorio, átomo→molécula (1 épica→portafolio), observar→ACTUAR→APRENDER
  (cerrar el loop), determinismo donde hoy hay azar.
- EJE DE NOVEDAD que ataca y por qué NO es incremental (un refactor/fix/tuning NO califica).
- PREMISA VERIFICABLE: la afirmación concreta sobre el código en que se apoya la idea, escrita para que
  el otro arquitecto la confirme o la tumbe en archivo:línea. NO afirmes que algo "no existe" o "está
  desconectado" sin marcarlo como premisa a verificar — en el debate pasado eso resultó FALSO y mató
  credibilidad.
- VALOR/KPI esperado y por qué NO agrega trabajo al operador.

RIELES DUROS (si una idea los viola, NO la propongas o degradala con fallback explícito):
- 3 runtimes con paridad (Codex/Claude Code/Copilot) o fallback explícito.
- Cero trabajo extra al operador (invisible u opt-in default off).
- Human-in-the-loop innegociable (amplificar, nunca reemplazar; sin autonomía proactiva).
- Mono-operador sin auth real (sin RBAC).
- No degradar; reusar lo existente (memoria colaborativa, flags del arnés, telemetría, gates golden).

PROHIBIDO: ideas que requieran Anthropic directo / LLM-as-judge horneado (el cerebro interno está capado
a sonnet sin proveedor directo: es inviable sin código de proveedor nuevo). Marcalo si una idea cae ahí.

SI ES UNA RONDA DE RÉPLICA: te paso el ranking provisional y las objeciones del juez. Defendé con
evidencia, REFORMULÁ la idea para superar la objeción, o REEMPLAZALA por una mejor. No te aferres.

COSTO: salida densa, sin relleno. Es un portafolio estructurado, no un ensayo.
ENTREGABLE: las 8-12 ideas con los campos de arriba + tu recomendación de cuáles 5 llevarías y por qué.
```

## Prompt para el UltraEficientCode + Juez

```text
ROL: Sos StackyArchitectaUltraEficientCode actuando como PODADOR + VERIFICADOR + JUEZ adversarial.
Conciencia de costo extrema (UltraCode): scope cerrado, exploración mínima, subagente Haiku solo si hay
fan-out real. No sos un revisor blando: tu trabajo es matar lo débil y aterrizar lo fuerte.

CONTEXTO: Te paso el portafolio del Brainstormer (8-12 ideas) y las rutas de los planes recientes.

PASO 1 — VERIFICAR PREMISAS (lo más importante; evidencia o muerte):
- Por CADA idea, tomá su PREMISA VERIFICABLE y confirmala o tumbala en el código REAL: archivo:línea.
- Premisa FALSA ⇒ la idea cae o se reformula (no la salves por simpatía). En el debate pasado se afirmó
  que speculative.py estaba desconectado y era FALSO (estaba registrado en api/__init__.py) — ese tipo de
  error invalida la idea. Sé igual de duro.
- Detectá también ideas que reinventan algo que YA existe (p. ej. grounding multi-cliente ya es per-
  cliente en context_enrichment.py): eso es CONTENIDO/datos, no un plan. Al cementerio.

PASO 2 — GATE ANTI-INCREMENTAL + RÚBRICA:
- Puntuá cada idea 1–5 en: Impacto, Novedad, Factibilidad, Rigor de evidencia.
- GATE: pasa solo si (Impacto + Novedad) >= 8 Y Factibilidad >= 3 Y Rigor de evidencia >= 3.
- Un refactor/fix/tuning NO es game-changer: Novedad <= 2 ⇒ afuera.
- Factibilidad: si requiere Anthropic directo / LLM-as-judge horneado ⇒ Factibilidad = 1 ⇒ afuera.

PASO 3 — RIELES DUROS (red-team sin piedad):
- 3 runtimes con paridad o fallback explícito (marcá deudas reales: style_memory copilot-only,
  speculative.py); cero trabajo extra al operador; human-in-the-loop (autonomía proactiva = RECHAZO);
  mono-operador sin auth (RBAC = sobre-ingeniería); no degradar; reuso obligatorio.
- Por cada idea que sobreviva, ANCLALA: qué módulos/flags/símbolos exactos tocaría, qué reusa, y su
  fallback por runtime. Sin esto no es un finalista creíble.

PASO 4 — VEREDICTO POR IDEA + RANKING:
- Veredicto por idea: ENTRA / ENTRA-CON-CAMBIOS / AL-CEMENTERIO (con motivo de una línea).
- Construí un ranking provisional de los sobrevivientes por ORDEN DE IMPLEMENTACIÓN (dependencias
  primero), no por score crudo. Si quedan != 5, decilo y explicá qué falta (más ideas) o qué sobra.

PASO 5 — CONVERGENCIA:
- Chequeá la Definición de Convergencia (5 finalistas, premisas verificadas, gate ok, rieles ok, sin
  duplicados, sin RECHAZADOS, ranking estable vs ronda previa). Decí explícitamente si CONVERGIÓ o si
  hace falta otra ronda, y qué objeciones mandar de vuelta al Brainstormer.

COSTO: salida densa y estructurada. El único contenido largo permitido son las citas archivo:línea
necesarias para sostener los veredictos.
ENTREGABLE: tabla idea→(scores, veredicto, evidencia archivo:línea, anclaje, motivo) + ranking
provisional + estado de convergencia + objeciones para la próxima ronda.
```

## Checklist de aceptación

- [ ] El `NN` máximo y el estado del arte se resolvieron dinámicamente (nunca hardcodeado); se leyó la
      memoria de roadmap previa para no repetir el debate.
- [ ] Hubo al menos 2 rondas reales (generativa + poda) y se iteró hasta cumplir la Definición de
      Convergencia; la bitácora registra qué cambió cada ronda.
- [ ] Entre 3 y 5 finalistas (top-5 es techo, no cuota), rankeados por orden de implementación
      (dependencias primero); no se rellenó para llegar a 5.
- [ ] CADA finalista tiene premisa verificada en código (archivo:línea); cero premisas asumidas. Las
      citas en disputa las verificó el orquestador de primera mano, no solo el subagente. Las premisas
      falsas fueron al cementerio con motivo.
- [ ] CADA finalista pasó el gate anti-incremental (Impacto+Novedad ≥ 8, Factibilidad ≥ 3, Evidencia ≥ 3)
      y respeta los 5 rieles duros o degrada con fallback explícito.
- [ ] Ningún finalista duplica un plan `NN_*` existente ni un ítem ya implementado.
- [ ] El juez (UltraEficientCode) emitió veredicto != RECHAZADO para todos; el ranking fue estable al
      menos una ronda; el juez mató/reformuló ≥1 idea por ronda o justificó no haberlo hecho.
- [ ] Se creó `Stacky Agents/docs/_roadmap/TOP5_<fecha>_<slug>.md` con top-5 + bitácora + cementerio
      (NO consume la secuencia `NN_`).
- [ ] Se actualizó la memoria de roadmap (un archivo, sin duplicar) con enlaces `[[...]]`.
- [ ] El trabajo pesado se delegó a los subagentes Brainstormer y UltraEficientCode (o inline con los
      mismos prompts si no estaban disponibles), con scope cerrado y costo controlado.
- [ ] Cada rol se spawneó UNA vez y se continuó con `SendMessage` en las rondas siguientes (no se
      re-spawneó en frío cada ronda); no se superó el techo de 6 rondas y se hizo balance honesto en la 4.
- [ ] Si existía un `TOP5_*.md` previo, sus finalistas se trataron explícitamente (re-confirmados,
      retirados al cementerio con motivo, o mandados a dedup si ya se formalizaron); el roadmap nuevo
      enlaza al previo.
- [ ] Se devolvió resumen de 8 líneas + handoff a `proponer-plan-stacky`; NO se redactó plan formal ni se
      implementó código; sin commit salvo pedido del operador.
- [ ] La bitácora del roadmap es densa, no verbosa: por ronda, qué entró/cayó/cambió y por qué — no el
      transcript completo de los subagentes.
