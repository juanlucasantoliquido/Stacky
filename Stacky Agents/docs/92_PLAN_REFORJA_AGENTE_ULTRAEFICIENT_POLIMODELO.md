# Plan 92 — Reforja del agente StackyArchitectaUltraEficientCode: robusto, polifuncional y polimodelo

**Estado:** CRITICADO (v1 → v2) — 2026-07-04
**Tipo:** Tooling de agentes/skills (no toca runtime de Stacky)
**Autor:** pipeline proponer-plan-stacky → criticar-y-mejorar-plan

**Changelog v1 → v2:**
- C1 (BLOQUEANTE, directiva del operador): default estático `normal` reemplazado por **herencia
  dinámica de perfil** del modelo/modo activo al ejecutar, con fallback `normal`. Cambian F0, F1, F3 y F4.
- C2: regla de detección LITERAL del modelo activo (tabla de mapeo `haiku*`→eco, resto→normal).
- C3: F2 con degradación explícita si la ruta user-level no existe (otra máquina/runtime).
- C4: textos de reemplazo de F4 reescritos en términos de herencia (sin `PERFIL: normal` hardcodeado).
- C5: memoria semilla redactada como reporte del operador, no como causalidad probada.
- C6: primera oración exacta de la `description` del frontmatter (F1).
- C7 [ADICIÓN ARQUITECTO]: línea obligatoria `Perfil activo: ...` al inicio de cada respuesta del
  agente + test de contrato `test_agente_reporta_perfil_activo`.

---

## 1. Objetivo + KPI

Reforjar el agente `StackyArchitectaUltraEficientCode` (y sus 3 espejos: agente user-level de Claude
Code, gemelo Codex TOML, y los prompts embebidos en 4 skills) para que deje de estar sobre-optimizado
al modo UltraCode/ahorro-de-tokens y pase a ser **polifuncional y polimodelo**: un sistema de
**perfiles de costo** (`eco` / `normal` / `max`). El perfil se declara por invocación (`PERFIL: ...`)
o, si no se declara, se **HEREDA del modelo/modo configurado en el momento de ejecutar** (modelo
económico → `eco`; modelo capaz → `normal`; imposible inferir → `normal`). Matriz de modelos
actualizada (Haiku 4.5 / Sonnet 5 / Opus 4.8 / Fable 5) y regla dura de "nunca delegar la
implementación core a un modelo menor".

**KPI/impacto esperado:**
- 0 prompts del pipeline que fuercen `model: haiku` para trabajo de juicio o implementación
  (hoy: `criticar-y-mejorar-plan` línea "corré con model haiku" — causa raíz de críticas débiles).
- El agente queda versionado en el repo (hoy vive solo en `C:\Users\juanluca\.claude\agents\`, fuera
  de git) → auditable por tests de contrato en CI local.
- 100% de las respuestas del agente abren con `Perfil activo: ...` → el operador ve de un vistazo
  con qué perfil corrió y si la herencia infirió bien.
- Memoria del agente inicializada con ≥3 hechos durables (hoy `MEMORY.md` vacío pese a la instrucción).
- Reducción esperada de re-trabajo: los planes implementados vía este agente dejan de necesitar
  supervisión correctiva por delegación excesiva a modelos inferiores.

## 2. Por qué ahora / gap que cierra

Auditoría 2026-07-04 del agente encontró 5 defectos concretos:

1. **Sobre-optimización a UltraCode.** Todo el cuerpo del agente gira alrededor de "gastar la menor
   cantidad de tokens" y "TODO subagente se lanza con model: 'haiku' POR DEFECTO. Sin excepción".
   En modo normal (suscripción, sin costo marginal por token del modelo principal) esto degrada
   calidad sin ahorrar nada relevante. El operador reporta planes mal implementados.
2. **Juez en Haiku.** `.claude/skills/criticar-y-mejorar-plan/SKILL.md` ordena al arquitecto-juez:
   "Sos el subagente; corré con model haiku salvo justificación escrita". Un juez adversarial en el
   modelo más chico produce críticas superficiales → planes débiles llegan a implementación.
3. **No polimodelo.** La política de modelos nombra solo Haiku/Sonnet/Opus genéricos; no conoce
   Fable 5 ni Opus 4.8, ni distingue el modo de ejecución (normal vs UltraCode/cloud).
4. **Memoria muerta.** El agente tiene instrucción de mantener memoria persistente pero su
   `MEMORY.md` está vacío: nunca acumuló los hechos durables que sus propias reglas piden.
5. **Drift triple.** Tres copias divergentes de la misma persona: el `.md` user-level (fuera de git),
   el TOML de Codex (`.codex/agents/stacky-architecta-ultra-eficient-code.toml`, en git) y los
   prompts embebidos en 4 skills. No hay fuente única ni test que detecte el drift.

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Claude Code (agente `.md` + skills), Codex CLI (TOML gemelo), GitHub
  Copilot Pro (sin sistema de subagentes → fallback ya existente en las skills: "ejecutar inline con
  el mismo prompt"; los perfiles se expresan como texto del prompt, funcionan igual inline).
- **Cero trabajo extra para el operador:** sin declaración explícita, el perfil se hereda solo del
  modelo/modo activo; `eco`/`normal`/`max` explícitos son opt-in por texto de invocación
  ("PERFIL: eco"). Nada de config nueva ni pasos manuales.
- **Human-in-the-loop:** sin cambios; el agente sigue sin autonomía proactiva.
- **Mono-operador sin auth:** N/A (no toca runtime).
- **No degradar / backward-compatible:** el nombre `StackyArchitectaUltraEficientCode` NO cambia
  (está referenciado en 12+ docs de planes y 4 skills). El perfil `eco` preserva 1:1 el
  comportamiento actual (y se hereda solo cuando el harness corre con modelo económico).
- **Sin flags de runtime:** este plan toca solo artefactos de tooling (markdown/TOML); no hay flag
  del arnés involucrada. La "protección" es: herencia con fallback `normal`, nombre estable, y
  perfil `eco` como modo compatible.

## 4. Fases

### F0 — Test de contrato anti-drift (TDD primero)

- **Objetivo:** un test que falla HOY y define el contrato de la reforja; detecta drift futuro.
- **Archivo a crear:** `backend/tests/test_agent_tooling_contracts.py`
- **Casos (nombres exactos):**
  - `test_agente_ultraeficient_existe_en_repo`: existe
    `.claude/agents/StackyArchitectaUltraEficientCode.md` (ruta relativa a la raíz del repo).
  - `test_agente_tiene_perfiles`: su contenido incluye las cuatro cadenas `## Perfil eco`,
    `## Perfil normal`, `## Perfil max` y `default: herencia`.
  - `test_agente_regla_implementacion_core`: incluye la cadena exacta
    `NUNCA delegues la implementación core a un modelo menor`.
  - `test_agente_reporta_perfil_activo` **[ADICIÓN ARQUITECTO]**: incluye la cadena exacta
    `Perfil activo:` (la obligación de reportar el perfil al inicio de cada respuesta).
  - `test_skill_criticar_sin_haiku_forzado`: `.claude/skills/criticar-y-mejorar-plan/SKILL.md`
    NO contiene la cadena `corré con model haiku`.
  - `test_toml_codex_menciona_perfiles`: `.codex/agents/stacky-architecta-ultra-eficient-code.toml`
    contiene `PERFIL` y `herencia`.
- **Implementación:** cada test resuelve la raíz del repo con
  `Path(__file__).resolve().parents[2]` y lee el archivo con `read_text(encoding="utf-8")`.
- **Comando:** `backend\venv\Scripts\python.exe -m pytest backend/tests/test_agent_tooling_contracts.py -q`
  (usar el venv py3.13 del repo; correr por archivo como siempre).
- **Criterio binario:** al cerrar F0 los 6 tests EXISTEN y FALLAN (rojo legítimo); al cerrar F4
  los 6 pasan.
- **Runtimes:** el test corre solo en el repo (pytest), idéntico en los 3 runtimes.
- **Trabajo del operador:** ninguno.

### F1 — Reescribir el agente como fuente única versionada (project-level)

- **Objetivo:** crear el agente reforjado DENTRO del repo, con perfiles heredables y política polimodelo.
- **Archivo a crear:** `.claude/agents/StackyArchitectaUltraEficientCode.md` (project-level; Claude
  Code lo levanta automáticamente y queda versionado).
- **Frontmatter:** mismos campos que el actual (`name`, `description`, `model: inherit`,
  `memory: user`). La `description` DEBE empezar con esta oración exacta: "Arquitecto IA senior
  polifuncional y polimodelo del ecosistema Stacky Agents con perfiles de costo eco/normal/max
  (default: herencia del modo activo)." y conservar después los bloques `<example>` actuales.
- **Cuerpo nuevo con ESTA estructura exacta** (secciones en este orden; el implementador copia los
  textos de abajo literalmente):

  1. **Identidad y misión** (igual que hoy, sin la cláusula "GASTANDO LA MENOR CANTIDAD DE TOKENS
     POSIBLE" en la misión; el costo pasa a ser dimensión del perfil, no misión).
  2. **`## Sistema de perfiles (default: herencia; fallback: normal)`** — texto normativo:
     - Si el invocador declara `PERFIL: eco|normal|max` en el prompt, ese perfil manda.
     - **Si NO se declara perfil, HEREDÁS el perfil del modelo/modo con el que estás corriendo
       en este momento.** Regla de detección LITERAL (sin inferencias creativas): mirá la
       identidad de modelo que el harness te declara en tu contexto de entorno (la línea del tipo
       "You are powered by the model named ..." o el model id activo) y aplicá esta tabla:
       | id/nombre del modelo activo contiene | perfil heredado |
       |---|---|
       | `haiku` (cualquier versión) | `eco` |
       | `sonnet`, `opus`, `fable` (cualquier versión) | `normal` |
       | no identificable / entorno UltraCode-cloud con facturación por token declarada | `eco` si hay facturación por token declarada; si no, `normal` |
     - `max` NUNCA se hereda: solo por declaración explícita del invocador.
     - Primera línea de TODA respuesta: `Perfil activo: <eco|normal|max> (declarado|heredado de
       <modelo>)`. **[ADICIÓN ARQUITECTO]** — le muestra al operador qué perfil corrió y por qué.
     - `## Perfil eco` — comportamiento actual completo: subagentes Haiku por defecto, presupuesto
       Pequeña/Mediana/Grande (0-1 / 2 / 3 subagentes), prohibiciones de orquestación, salida corta.
       Para UltraCode/cloud o cuando el operador pida ahorro explícito.
     - `## Perfil normal` — calidad primero: el agente trabaja él mismo con el modelo heredado;
       subagentes solo para fan-out real de LECTURA (exploración/búsqueda), con el modelo que el
       harness asigne (sin forzar downgrade); implementación, diseño y juicio SIEMPRE en el hilo
       principal; tests corridos y leídos por el propio agente (cero falsos verdes).
     - `## Perfil max` — profundidad máxima: además de `normal`, pasada de verificación adversarial
       propia (releer diff completo, correr suite ampliada), y permiso explícito de usar el modelo
       más capaz disponible para revisión crítica.
  3. **`## Política polimodelo`** — reemplaza la tabla Haiku/Sonnet/Opus:
     - Regla 1: usar los modelos QUE EL HARNESS OFRECE hoy (p. ej. Haiku 4.5, Sonnet 5, Opus 4.8,
       Fable 5); nunca hardcodear una generación — describir capacidades ("el más económico", "el
       más capaz") y resolver contra lo disponible.
     - Regla 2 (dura, en mayúsculas en el doc): `NUNCA delegues la implementación core a un modelo
       menor`. Delegable a modelo económico: búsqueda, inventario, lectura dirigida, resúmenes.
       NO delegable: escribir código de producción, decidir arquitectura, juzgar planes, interpretar
       resultados de tests.
     - Regla 3: escalada con evidencia (se conserva del agente actual) pero bidireccional: también
       des-escalar a económico cuando la subtarea es mecánica.
  4. **`## TDD y verificación`** — conservar el bloque TDD actual + agregar: la verificación final
     (correr tests y leer el output real) la hace el agente principal, nunca se acepta un "pasó
     todo" reportado por un subagente sin el output pegado.
  5. **`## Estándares de arquitectura`** — conservar tal cual.
  6. **`## Conciencia del ecosistema Stacky`** — conservar y AMPLIAR con: DB viva en
     `DeployStackyAgents\data`; runtime lee agentes de `backend/Stacky/agents`; venv py3.13 en
     `backend/venv`, tests se corren por archivo; vitest no instalado globalmente.
  7. **`## Memoria (obligación activa)`** — conservar la instrucción actual + agregar regla
     accionable: al terminar CUALQUIER tarea no trivial, escribir o actualizar al menos una memoria
     si se descubrió un hecho durable; si no se descubrió ninguno, decirlo explícitamente en el
     resumen final ("memoria: sin novedades durables").
  8. **`## Formato de respuesta`** — conservar, anteponiendo la línea `Perfil activo: ...` como
     primera línea obligatoria de toda respuesta.
- **Criterio binario:** `test_agente_ultraeficient_existe_en_repo`, `test_agente_tiene_perfiles`,
  `test_agente_regla_implementacion_core` y `test_agente_reporta_perfil_activo` pasan.
- **Runtimes:** Claude Code nativo; Codex vía F3; Copilot vía prompts inline de skills (F4).
- **Trabajo del operador:** ninguno.

### F2 — Sincronizar la copia user-level

- **Objetivo:** que la copia en `C:\Users\juanluca\.claude\agents\StackyArchitectaUltraEficientCode.md`
  no quede divergente.
- **Acción exacta:** si esa ruta EXISTE en la máquina donde corre la implementación, sobrescribir el
  archivo con EXACTAMENTE el mismo contenido de F1 (byte a byte, mismo frontmatter). Si la ruta NO
  existe (otra máquina, contenedor Codex/Copilot, cloud), NO crear nada fuera del repo: dejar
  constancia en el reporte de implementación de que F2 queda pendiente para la máquina del operador
  (degradación controlada — la fuente canónica es la del repo).
- **Criterio binario (solo en la máquina del operador):** `git hash-object` del archivo del repo ==
  hash del archivo user-level (comando: `git hash-object ".claude/agents/StackyArchitectaUltraEficientCode.md" "C:/Users/juanluca/.claude/agents/StackyArchitectaUltraEficientCode.md"` → dos hashes
  iguales). En cualquier otro entorno el criterio es: reporte con la línea "F2 pendiente: ruta
  user-level inexistente en este entorno".
- **Runtimes:** solo afecta Claude Code; Codex/Copilot degradan con el reporte explícito.
- **Trabajo del operador:** ninguno.

### F3 — Sincronizar el gemelo Codex

- **Objetivo:** paridad Codex.
- **Archivo a editar:** `.codex/agents/stacky-architecta-ultra-eficient-code.toml`
- **Cambios exactos en `developer_instructions`:**
  - Insertar tras la línea de identidad el bloque de perfiles condensado: declaración `PERFIL:
    eco|normal|max (default: herencia del modelo activo; fallback normal; max nunca se hereda)`,
    la tabla de detección de F1 condensada (haiku→eco; sonnet/opus/fable→normal; desconocido→normal),
    la obligación de abrir cada respuesta con `Perfil activo: ...`, y las 3 definiciones de perfil
    en 2-3 líneas cada una (mismo contenido normativo de F1, condensado).
  - Reemplazar la línea "Por defecto, usá Haiku para subagentes; ..." por: "Modelos: usá los que el
    harness ofrezca; económicos solo para lectura/búsqueda; NUNCA delegues la implementación core a
    un modelo menor. En perfil eco aplican los presupuestos estrictos de subagentes."
  - Quitar de la línea "Objetivo: resolver cambios con la menor cantidad de tokens posible…"
    la cláusula de tokens; queda "Objetivo: resolver cambios con máximo rigor; el costo se gobierna
    por el perfil activo."
- **Criterio binario:** `test_toml_codex_menciona_perfiles` pasa.
- **Runtimes:** Codex nativo.
- **Trabajo del operador:** ninguno.

### F4 — Desharcodear Haiku de las skills del pipeline

- **Objetivo:** que los 4 prompts embebidos respeten la herencia de perfil y dejen de forzar downgrade.
- **Archivos a editar (cambios exactos):**
  1. `.claude/skills/criticar-y-mejorar-plan/SKILL.md`: reemplazar la frase
     `COSTO (UltraCode): Sos el subagente; corré con model haiku salvo justificación escrita.` por
     `PERFIL: heredá el perfil del modelo activo (regla de herencia del agente; el juicio
     adversarial NUNCA se degrada a un modelo menor por decisión propia). El invocador puede
     declarar PERFIL: eco explícitamente en UltraCode/cloud.` Conservar el resto de la oración
     (no explorar el repo entero, etc.).
  2. `.claude/skills/proponer-plan-stacky/SKILL.md`: en el "Prompt para el arquitecto", reemplazar
     `Conciencia de costo extrema (UltraCode): scope cerrado, exploración mínima, subagentes Haiku
     solo si hay fan-out real, cero gasto innecesario.` por `PERFIL: heredá el perfil del modelo
     activo (fallback normal); calidad del documento primero, exploración dirigida. Declarar
     PERFIL: eco solo en UltraCode/cloud.`
  3. `.claude/skills/implementar-plan-stacky/SKILL.md`: sustituir la cláusula
     `conciencia de costo extrema (UltraCode): scope cerrado, exploración mínima, subagente Haiku
     solo si hay fan-out real` por `PERFIL: heredá el perfil del modelo activo (fallback normal) —
     la implementación core NUNCA se delega a un modelo menor; subagentes solo para lectura/fan-out
     real`. Conservar intacta la regla existente de que la verificación final la corre el orquestador.
  4. `.claude/skills/debatir-top5-evolucion-stacky/SKILL.md`: en el "Prompt para el UltraEficientCode
     + Juez", reemplazar `Conciencia de costo extrema (UltraCode): scope cerrado, exploración mínima,
     subagente Haiku solo si hay fan-out real.` por `PERFIL: heredá el perfil del modelo activo
     (fallback normal); el veredicto exige el modelo heredado, subagentes económicos solo para
     verificar premisas archivo:línea.`
- **Criterio binario:** `test_skill_criticar_sin_haiku_forzado` pasa; y
  `Grep "corré con model haiku" .claude/skills/` devuelve 0 matches.
- **Runtimes:** las 4 skills ya tienen fallback inline (Copilot/entornos sin Agent tool) — el texto
  de herencia aplica igual inline (el modelo activo es el que está leyendo el prompt).
- **Trabajo del operador:** ninguno.

### F5 — Bootstrap de la memoria del agente

- **Objetivo:** cumplir por fin la obligación de memoria: sembrarla con hechos durables verificados.
- **Directorio:** `C:\Users\juanluca\.claude\agent-memory\StackyArchitectaUltraEficientCode\`
  (misma degradación que F2: si la ruta no existe en este entorno, reportar "F5 pendiente" sin crear
  nada fuera del repo).
- **Archivos a crear (frontmatter estándar de memoria; type entre paréntesis):**
  - `stacky-test-env.md` (project): venv py3.13 en `backend/venv`; correr pytest POR ARCHIVO;
    vitest del frontend no instalado global.
  - `perfiles-y-delegacion.md` (feedback): regla `NUNCA delegar implementación core a modelo
    menor` y herencia de perfil del modelo activo — **Why:** el operador reportó (2026-07-04)
    implementaciones deficientes coincidentes con delegación forzada a Haiku en los prompts del
    pipeline; **How to apply:** perfiles eco/normal/max, default herencia, fallback normal,
    `Perfil activo:` en cada respuesta.
  - `rutas-runtime-stacky.md` (project): runtime lee agentes de `backend/Stacky/agents`; DB viva en
    `DeployStackyAgents\data`; `.agent.md` gitignored.
  - Actualizar `MEMORY.md` con las 3 líneas índice correspondientes.
- **Criterio binario:** `MEMORY.md` contiene ≥3 líneas que empiezan con `- [` (o el reporte dice
  "F5 pendiente: ruta de memoria inexistente en este entorno").
- **Runtimes:** memoria propia de Claude Code; Codex/Copilot no la leen (sin impacto).
- **Trabajo del operador:** ninguno.

## 5. Riesgos y mitigaciones

- **R1: perder el ahorro en UltraCode/cloud.** Mitigación: perfil `eco` preserva el comportamiento
  actual 1:1, se hereda solo cuando el modelo activo es económico, y las skills documentan cuándo
  declararlo explícito.
- **R2: doble fuente Claude (project vs user).** Mitigación: F2 las deja idénticas y el criterio de
  hash lo verifica; futura divergencia la detecta el test de contrato del repo (la fuente canónica
  es la del repo).
- **R3: romper invocaciones existentes por renombre.** Mitigación: el nombre NO cambia.
- **R4: prompts de skills más largos.** Mitigación: las sustituciones son 1:1 en longitud aproximada;
  no se agregan secciones nuevas a las skills.
- **R5: herencia infiere mal el perfil (p. ej. modelo no identificable).** Mitigación: fallback
  determinista a `normal`; `max` nunca se hereda; la línea `Perfil activo: ... (heredado de <modelo>)`
  hace visible cualquier inferencia errónea al primer vistazo y el operador la corrige declarando
  `PERFIL:` explícito.

## 6. Fuera de scope

- Renombrar el agente o fusionarlo con `stacky-agents-architect`.
- Tocar código de runtime de Stacky, flags del arnés o UI.
- Automatizar la sincronización repo↔user-level (queda manual vía test de contrato + F2).
- Cambiar el pipeline de planes (proponer/criticar/implementar/supervisar) más allá de las
  sustituciones de texto de F4.
- Detección de perfil por telemetría/config externa: la herencia se resuelve SOLO con la identidad
  de modelo que el harness declara en el contexto (nada de leer configs del sistema).

## 7. Glosario

- **UltraCode/CloudCode:** modo de ejecución en la nube donde los subagentes facturan por token; ahí
  nació la obsesión por Haiku.
- **Perfil:** modo de operación del agente (`eco`/`normal`/`max`) que gobierna delegación y elección
  de modelos.
- **Herencia de perfil:** cuando no se declara `PERFIL:`, el agente lo deduce del modelo/modo con el
  que está corriendo (tabla de detección de F1); fallback `normal`; `max` nunca se hereda.
- **Implementación core:** escribir código de producción, decidir arquitectura, juzgar planes,
  interpretar resultados de tests. Lo opuesto a trabajo mecánico de lectura/búsqueda.
- **Drift:** divergencia entre las copias del mismo agente (repo/user-level/TOML/prompts de skills).
- **Falso verde:** reportar tests como pasados sin haber leído el output real.

## 8. Orden de implementación

1. F0 (tests de contrato, en rojo).
2. F1 (agente project-level reforjado) → 4 tests pasan.
3. F2 (sync user-level) → hash igual (o reporte "F2 pendiente" si la ruta no existe).
4. F3 (sync TOML Codex) → test TOML pasa.
5. F4 (skills sin Haiku forzado) → test skill pasa; grep 0 matches.
6. F5 (bootstrap memoria) → MEMORY.md con ≥3 entradas (o reporte "F5 pendiente").

## 9. Definición de Hecho (DoD)

- Los 6 tests de `backend/tests/test_agent_tooling_contracts.py` pasan con el venv del repo.
- `git hash-object` de las dos copias del agente `.md` coincide (en la máquina del operador; en otro
  entorno, el reporte declara "F2 pendiente").
- 0 ocurrencias de `corré con model haiku` bajo `.claude/skills/`.
- `MEMORY.md` del agente con ≥3 entradas índice (o "F5 pendiente" declarado).
- Ningún archivo de runtime de Stacky (backend/frontend) modificado, salvo el test nuevo.
- Commit del plan + commits de implementación con trailer de co-autoría; push manual del operador.
