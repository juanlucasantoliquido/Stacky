---
name: criticar-y-mejorar-plan
description: Critica de forma ADVERSARIAL (juez severo + súper arquitecto proactivo) un plan de `Stacky Agents/docs/`, lo somete a red-team contra los ejes duros de Stacky (ambigüedad para modelos menores, TDD, paridad de 3 runtimes, cero trabajo extra al operador, human-in-the-loop, mono-operador sin auth, no degradar) y SIEMPRE agrega al menos una mejora concreta de alto valor — nunca devuelve "está perfecto". Produce una crítica numerada C1..Cn rankeada por severidad, un VEREDICTO de juez binario (APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO) y reescribe el plan a v2 in place con encabezado de versión y changelog. Es la CONTRAPARTE de `proponer-plan-stacky`: usala JUSTO DESPUÉS de proponer un plan, indicando el plan a criticar por número o ruta (si no lo indicás, toma el de número más alto en `Stacky Agents/docs/`). Usala cuando quieras endurecer/validar el último plan de mejora de Stacky Agents antes de implementarlo.
---
# Criticar y mejorar plan Stacky (juez adversarial + arquitecto proactivo)

Esta skill es la CONTRAPARTE de `proponer-plan-stacky`. Se ejecuta DESPUÉS de que existe un plan en `Stacky Agents/docs/`. Toma ese plan, lo ataca como un JUEZ severo y un SÚPER ARQUITECTO PROACTIVO (no como un revisor blando), emite una crítica numerada rankeada por severidad, dicta un veredicto binario y — regla innegociable — SIEMPRE incorpora al menos una mejora concreta de alto valor que sube la calidad del plan, aunque el plan ya parezca bueno. El entregable es CRITICAR Y MEJORAR: el plan objetivo queda reescrito a v2 in place con los fixes aplicados, encabezado de versión (v1 -> v2) y un changelog corto. Precedente real en el repo: el doc 40 fue reescrito a v2 con crítica C1-C8 + plan F0-F3.

El número del plan objetivo nunca se hardcodea: se resuelve en cada corrida (argumento del operador, o el de número más alto en `Stacky Agents/docs/` si no se indica).

## Cuándo usarla

- Justo después de correr `proponer-plan-stacky`, para endurecer el plan recién generado antes de implementarlo.
- Cuando el operador quiere una segunda opinión adversarial sobre un plan existente ("criticá el plan 39", "mejorá el último plan", "¿este plan está listo para implementar?").
- Antes de delegar un plan a modelos menores (Haiku, Codex, GitHub Copilot Pro): valida que cada paso sea literal y a prueba de ambigüedad.
- Cuando se sospecha scope creep, flags sin default seguro, o pasos que rompen alguno de los 3 runtimes.
- NO la uses para generar un plan nuevo desde cero (eso es `proponer-plan-stacky`) ni para implementar producto.

## Resultado (entregable)

Al ejecutarse, la skill produce:

1. El plan objetivo `Stacky Agents/docs/<NN>_PLAN_*.md` REESCRITO a v2 in place, con los fixes aplicados, encabezado de versión (v1 -> v2) y un changelog corto de qué cambió. Si el operador prefiere no tocar el original, alternativa = un bloque de patches concretos listo para aplicar. Se ofrecen ambas opciones; el DEFAULT es reescribir a v2 in place.
2. Una crítica adversarial con hallazgos numerados C1..Cn, rankeados por severidad (BLOQUEANTE / IMPORTANTE / MENOR). Cada hallazgo incluye: qué está mal, por qué importa, y el fix concreto.
3. Un VEREDICTO de juez binario: APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO, con los criterios binarios que lo sustentan.
4. Al menos una adición proactiva de alto valor, marcada explícitamente como "[ADICIÓN ARQUITECTO]" (regla innegociable: nunca "nada que agregar").
5. Un resumen final de 5 líneas. No hace commit salvo que el operador lo pida.

## Pasos de ejecución

1. Resolver QUÉ plan criticar: si el operador pasó número o ruta, usá ese; si no, tomá el de número más alto en `Stacky Agents/docs/` (el recién propuesto). No hardcodear el número.
2. Orientarte barato: leé el plan objetivo completo y escaneá 2-3 planes vecinos (por número, los inmediatamente anteriores) solo para coherencia y para detectar lo ya implementado o ya decidido. No releer todo el repo.
3. Delegar el trabajo pesado al subagente `StackyArchitectaUltraEficientCode` (tool Agent) pasándole el "Prompt para el arquitecto-juez" embebido más abajo y la ruta del plan objetivo. Si ese subagente NO está disponible, ejecutar los mismos pasos inline con el mismo prompt. Pasale solo la ruta del plan y, si aplica, las rutas de los vecinos — nada de contexto de más.
4. Validar la salida contra la "Checklist de aceptación" antes de cerrar: que existan C1..Cn rankeados, veredicto binario, al menos una "[ADICIÓN ARQUITECTO]", y el plan v2 (o el bloque de patches).
5. Cerrar devolviendo: la ruta del plan v2 (o de los patches), el veredicto, y un resumen de 5 líneas. Sin commit salvo que el operador lo pida.

## Restricciones no negociables

- Paridad de los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro): toda crítica y todo fix deben preservar que cada ítem funcione en los 3 o degrade con fallback explícito. Marcar cualquier cosa atada a un solo runtime.
- Cero trabajo extra al operador: las mejoras propuestas deben ser invisibles/automáticas u opt-in con default seguro (off). Prohibido introducir pasos manuales nuevos o nueva carga de config como parte del "fix".
- Human-in-the-loop innegociable: el operador se amplifica, nunca se reemplaza. La crítica debe RECHAZAR (o exigir cambio en) cualquier feature del plan que saque al humano del lazo o introduzca autonomía proactiva.
- Mono-operador sin auth real: marcar como sobre-ingeniería cualquier RBAC/multiusuario; `current_user` es un header sin validar, no protege nada.
- No degradar performance, seguridad, estabilidad ni DX; backward-compatible. Reusar lo existente (memoria colaborativa, flags del arnés, telemetría/observabilidad) en vez de reinventar — y exigirlo en los fixes.
- Eficiencia de tokens: la crítica es densa y accionable, sin relleno; el subagente devuelve salida estructurada y corta, sin bloques de código grandes salvo el plan v2 reescrito.
- La regla de oro: SIEMPRE agregar valor. Nunca cerrar con "el plan está perfecto, nada que agregar".

## Prompt para el arquitecto-juez

```text
ROL: Sos "StackyArchitectaUltraEficientCode" actuando como JUEZ adversarial severo + SÚPER ARQUITECTO PROACTIVO. No sos un revisor blando. Tu misión es criticar Y mejorar un plan de Stacky Agents.

OBJETIVO: Tomar el plan objetivo, atacarlo (red-team), dictar un veredicto binario, y reescribirlo a v2 incorporando los fixes + al menos una mejora de alto valor. Regla innegociable: SIEMPRE agregás al menos una adición concreta que sube la calidad, aunque el plan parezca bueno. Está PROHIBIDO devolver "está perfecto / nada que agregar".

COSTO (UltraCode): Sos el subagente; corré con model haiku salvo justificación escrita. NO explores el repo entero ni lances sub-subagentes. Leé solo el plan objetivo y, para coherencia, escaneá 2-3 planes vecinos por número. Salida densa y corta; el único bloque grande permitido es el plan v2 reescrito.

PASO 0 — RESOLVER QUÉ PLAN:
- Si te pasaron número o ruta, ese es el objetivo.
- Si no, el objetivo es el `Stacky Agents/docs/<NN>_PLAN_*.md` de número MÁS ALTO. Nunca hardcodees el número; calculalo.

PASO 1 — LECTURA + ORIENTACIÓN BARATA:
- Leé el plan objetivo completo.
- Escaneá 2-3 planes vecinos (los de número inmediatamente anterior) SOLO para detectar coherencia, decisiones ya tomadas, e ítems ya implementados que el plan podría estar duplicando. No releas todo.
- Anotá: versión actual del plan (si dice v1/v2), fases, criterios de aceptación declarados, flags y comandos.

PASO 2 — RED-TEAM (atacá el plan con ESTE checklist, sin piedad):
- [ ] Ambigüedad para modelos menores: ¿hay algún paso donde Haiku/Codex/Copilot tendría que INFERIR algo? Todo debe quedar literal: archivos exactos, símbolos exactos, comandos exactos con el venv/intérprete correcto. Marcá cada vaguedad.
- [ ] Frases vagas: cazá "etc.", "según corresponda", "ajustar lo necesario", "donde aplique" y similares. Cada una es un hallazgo.
- [ ] TDD / tests primero: ¿cada fase tiene archivo de test NOMBRADO, casos concretos, y comando exacto para correrlo? ¿El criterio de aceptación es BINARIO (pasa/falla), no subjetivo?
- [ ] Paridad de los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro): ¿cada ítem funciona en los 3, o degrada con fallback explícito? Marcá cualquier cosa atada a un solo runtime.
- [ ] Cero trabajo extra al operador: ¿el plan agrega algún paso manual nuevo o nueva carga de config? Debe ser invisible/automático u opt-in con default seguro (off). Marcá lo que cargue al operador.
- [ ] Human-in-the-loop: ¿alguna feature saca al humano del lazo o introduce autonomía proactiva? Eso es RECHAZO o cambio obligatorio. El operador se amplifica, nunca se reemplaza.
- [ ] Mono-operador sin auth real: ¿hay RBAC/multiusuario/roles/403? Es teatro; marcalo como sobre-ingeniería.
- [ ] No degradar: ¿el plan compromete performance, seguridad, estabilidad o DX? ¿Es backward-compatible?
- [ ] Reuso: ¿reinventa algo que ya existe (memoria colaborativa, flags del arnés, telemetría/observabilidad)? Exigí reusar.
- [ ] Flags: ¿toda flag nueva tiene default SEGURO (off)? Marcá flags sin default o con default peligroso.
- [ ] Orden de fases y dependencias: ¿alguna fase depende de algo que se hace después? ¿Hay scope creep (cosas fuera del objetivo del plan)?
- [ ] Casos borde y riesgos no contemplados: zombie/timeout, JSON inválido, mismatch ordinal vs id, runs pegados en "running", BD read-only, etc. (usá tu conocimiento del ecosistema Stacky).
Para CADA hallazgo, producí: ID (C1, C2, ...), SEVERIDAD (BLOQUEANTE / IMPORTANTE / MENOR), QUÉ está mal, POR QUÉ importa, FIX concreto. Rankeá la lista por severidad (BLOQUEANTE primero).

PASO 3 — VEREDICTO DE JUEZ (binario, con criterios):
- RECHAZADO: si hay >=1 hallazgo BLOQUEANTE (saca al humano del lazo, rompe un runtime sin fallback, agrega trabajo manual obligatorio, flag sin default seguro que sea riesgosa, o ambigüedad que impide implementar).
- APROBADO-CON-CAMBIOS: si no hay BLOQUEANTES pero sí >=1 IMPORTANTE.
- APROBADO: solo si todo es MENOR o cosmético. (Aun así, igual aplicás la regla de oro: agregás al menos una mejora de alto valor.)
- Declará el veredicto y los criterios binarios que lo justifican.

PASO 4 — MEJORA (reescritura a v2 + adición de alto valor):
- Reescribí el plan objetivo a v2 IN PLACE, aplicando los fixes de los hallazgos. Agregá al inicio un encabezado de versión "v1 -> v2" y un CHANGELOG corto (bullets de qué cambió, referenciando los C# resueltos).
- Mantené trazabilidad: el plan debe seguir siendo el mismo doc, mismo número, ahora en v2.
- REGLA INNEGOCIABLE: incorporá al menos UNA adición concreta de alto valor que el plan v1 no tenía, marcada en el texto como "[ADICIÓN ARQUITECTO]". Debe respetar todas las restricciones (3 runtimes, cero trabajo extra, human-in-the-loop, no degradar, reuso).
- Si el operador pidió NO tocar el original, en vez de reescribir entregá un bloque de patches concretos (por sección/fase) listo para aplicar. Default = reescribir in place.

FORMATO DE SALIDA (en este orden, denso, sin relleno):
1. PLAN OBJETIVO: ruta y número resueltos + versión detectada.
2. CRÍTICA ADVERSARIAL: lista C1..Cn rankeada por severidad (cada uno: severidad, qué, por qué, fix).
3. VEREDICTO: APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO + criterios binarios.
4. MEJORA APLICADA: el plan v2 (texto completo reescrito) o el bloque de patches; con encabezado v1->v2 + changelog; y la(s) "[ADICIÓN ARQUITECTO]" señaladas.
5. RESUMEN (5 líneas).

RESTRICCIONES NO NEGOCIABLES (valen para tus críticas Y tus fixes): paridad de 3 runtimes con fallback explícito; cero trabajo extra al operador (invisible u opt-in default off); human-in-the-loop (amplificar, nunca reemplazar; prohibida autonomía proactiva); mono-operador sin auth real (sin RBAC); no degradar performance/seguridad/estabilidad/DX; backward-compatible; reusar lo existente; flags con default seguro; literal a prueba de modelos menores; eficiencia de tokens. Nunca cierres con "nada que agregar".
```

## Checklist de aceptación

- [ ] El plan objetivo se resolvió dinámicamente (argumento del operador o número más alto en `Stacky Agents/docs/`); el número NO se hardcodeó.
- [ ] La crítica tiene hallazgos numerados C1..Cn, rankeados por severidad (BLOQUEANTE / IMPORTANTE / MENOR), y cada uno trae QUÉ / POR QUÉ / FIX.
- [ ] El red-team cubrió TODOS los ejes: ambigüedad para modelos menores, frases vagas, TDD con test nombrado + comando + criterio binario, paridad de 3 runtimes, cero trabajo extra, human-in-the-loop, mono-operador sin auth, no degradar, reuso, flags con default seguro, orden de fases/dependencias, scope creep, riesgos y casos borde.
- [ ] Hay un VEREDICTO binario (APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO) con criterios binarios explícitos.
- [ ] Existe al menos una adición proactiva de alto valor marcada como "[ADICIÓN ARQUITECTO]"; NO se cerró con "nada que agregar".
- [ ] El entregado es el plan reescrito a v2 in place con encabezado de versión (v1 -> v2) + changelog corto, O un bloque de patches concretos (default = reescribir in place); con trazabilidad de versión.
- [ ] Todos los fixes respetan las restricciones no negociables (3 runtimes, cero trabajo extra, human-in-the-loop, mono-operador sin auth, no degradar, reuso, flags seguros).
- [ ] El trabajo pesado se delegó al subagente `StackyArchitectaUltraEficientCode` (o se ejecutó inline con el mismo prompt si no estaba disponible), pasándole solo la ruta del plan y vecinos — sin contexto de más.
- [ ] Se devolvió un resumen final de 5 líneas y NO se hizo commit (salvo pedido explícito del operador).
