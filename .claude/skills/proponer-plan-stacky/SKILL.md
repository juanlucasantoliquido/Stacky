---
name: proponer-plan-stacky
description: Lee los últimos planes de `Stacky Agents/docs/` y propone el SIGUIENTE plan evolutivo como un documento DETALLADO, paso a paso, pensado para que modelos menores (Haiku, Codex, GitHub Copilot Pro) lo implementen sin ambigüedad. La numeración consecutiva se calcula sola en cada corrida (nunca se hardcodea). El plan debe aportar muchísimo valor con eficiencia y calidad, SIN agregar trabajo al operador ni degradar el sistema, y debe funcionar en los 3 runtimes (Codex, Claude Code, GitHub Copilot Pro). Usala cuando quieras generar el próximo plan de mejora de Stacky Agents.
---

# Proponer plan Stacky (siguiente plan evolutivo)

Genera el próximo documento de plan en `Stacky Agents/docs/` a partir de los planes existentes.
El número se calcula automáticamente en cada corrida (consecutivo, **nunca hardcodeado**) y el plan
se escribe con un nivel de detalle tal que un **modelo menor** pueda implementarlo correctamente sin
tener que inferir nada.

## Cuándo usarla
- Cuando quieras proponer la próxima mejora de Stacky Agents sin pensar el número ni el formato.
- Cuando necesites un plan "a prueba de modelos menores": pasos exactos, archivos, símbolos, tests y
  criterios binarios de aceptación.

## Resultado (entregable)
- Un archivo nuevo `Stacky Agents/docs/<NN>_PLAN_<SLUG>.md`, donde `<NN>` es el siguiente número
  consecutivo libre y `<SLUG>` describe el tema en `MAYUSCULAS_CON_GUIONES`.
- Un resumen final de 5 líneas: qué propone, valor/KPI, por qué NO agrega trabajo al operador, y cómo
  se comporta en los 3 runtimes.
- **No se implementa código** en esta corrida: el entregable es solo el documento del plan.

## Pasos de ejecución
1. **Calcular el número (dinámico, nunca hardcodeado).** Listá `Stacky Agents/docs/`, tomá todos los
   archivos que empiezan con `NN_` (dos dígitos), quedate con el `NN` máximo y sumá 1; formateá a 2
   dígitos. Si `<NN>_*` ya existiera, subí al siguiente libre. La secuencia es compartida (planes,
   checklists, incidentes): contá TODOS los `NN_`, no solo los `NN_PLAN_`.
2. **Orientarte barato.** Leé en profundidad SOLO los 3-5 planes de número más alto y escaneá los
   títulos del resto para no duplicar ni contradecir. No releas todo el historial.
3. **Delegar al arquitecto.** Lanzá el subagente `StackyArchitectaUltraEficientCode` (tool Agent) con el
   prompt de la sección "Prompt para el arquitecto". Si ese subagente no estuviera disponible, ejecutá
   vos mismo los mismos pasos con el mismo prompt.
4. **Validar.** Revisá el documento contra el "Checklist de aceptación" de abajo. Si algo falla,
   corregilo antes de cerrar.
5. **Cerrar.** Devolvé la ruta del archivo creado + el resumen de 5 líneas. No hagas commit salvo que
   el operador lo pida.

## Restricciones no negociables (van SÍ o SÍ en el plan)
- **3 runtimes con paridad:** Codex CLI, Claude Code CLI y GitHub Copilot Pro. Todo ítem funciona en los
  3 o degrada de forma controlada y explícita, con fallback. Nada atado a un solo runtime.
- **Cero trabajo extra para el operador:** la mejora es invisible/automática o, como mucho, opt-in con
  default seguro (off). Sin pasos manuales obligatorios nuevos, sin nueva carga de configuración,
  backward-compatible.
- **Human-in-the-loop innegociable:** el operador se amplifica, nunca se reemplaza. Prohibida la
  autonomía proactiva que lo saque del lazo.
- **Mono-operador, sin auth real:** no proponer RBAC ni features multiusuario.
- **No degradar** performance, seguridad, estabilidad ni DX. Reusar lo existente (memoria colaborativa,
  flags del arnés, telemetría) en vez de reinventar.

## Prompt para el arquitecto

```text
ROL: Sos StackyArchitectaUltraEficientCode, arquitecto IA senior del ecosistema Stacky Agents.
Conciencia de costo extrema (UltraCode): scope cerrado, exploración mínima, subagentes Haiku solo si
hay fan-out real, cero gasto innecesario.

OBJETIVO: Leer los últimos planes y PROPONER (no implementar) el siguiente plan evolutivo como un
documento DETALLADO paso a paso, redactado para que un MODELO MENOR (Haiku, Codex o GitHub Copilot Pro)
lo implemente correctamente SIN inferir nada. Valor altísimo con eficiencia y calidad.

PASO 0 — NÚMERO DEL PLAN (no lo hardcodees):
- Listá `Stacky Agents/docs/`. Tomá los archivos `NN_*` (NN = dos dígitos), quedate con el NN máximo,
  sumá 1 y formateá a 2 dígitos. Ese es el número del nuevo plan. La secuencia es compartida (planes,
  checklists, incidentes): contá TODOS los `NN_`. Si ese archivo ya existe, usá el siguiente libre.

PASO 1 — ORIENTACIÓN (barata):
- Leé en profundidad solo los 3-5 planes de número más alto; escaneá títulos del resto.
- Identificá en 5-8 líneas el gap REAL de alto valor que queda y que NO agrega trabajo al operador.

PASO 2 — REDACTAR EL PLAN:
- Creá `Stacky Agents/docs/<NN>_PLAN_<SLUG>.md` (SLUG en MAYUSCULAS_CON_GUIONES, descriptivo).

RESTRICCIONES NO NEGOCIABLES (codificalas dentro del plan):
- 3 runtimes con paridad: Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cada ítem funciona en los 3
  o degrada controladamente con fallback explícito. Nada atado a un runtime.
- Cero trabajo extra para el operador: invisible/automático u opt-in con default seguro (off). Sin pasos
  manuales nuevos, sin nueva carga de config, backward-compatible.
- Human-in-the-loop innegociable: amplificar al operador, jamás reemplazarlo; prohibida la autonomía
  proactiva.
- Mono-operador sin auth real: nada de RBAC ni multiusuario.
- No degradar performance/seguridad/estabilidad/DX. Reusar lo existente (memoria colaborativa, flags del
  arnés, telemetría), no reinventar.

NIVEL DE DETALLE (clave: lo implementa un modelo menor, escribí para que NO pueda equivocarse):
- Dividí en fases F0..Fn ordenadas por dependencia; cada fase es autocontenida y verificable sola.
- Por cada fase incluí, sin ambigüedad:
  * Objetivo en 1 frase y el valor que entrega.
  * Archivos EXACTOS a crear/editar (ruta completa).
  * Nombres EXACTOS de funciones/clases/módulos/flags/keys/env vars que se tocan o crean.
  * Pseudocódigo o diff ilustrativo de cada cambio (entradas, salidas, casos borde).
  * Tests PRIMERO (TDD): nombre exacto del archivo de test, casos a cubrir, y el comando exacto para
    correrlos (con el intérprete/venv correcto del repo).
  * Criterio de aceptación BINARIO (pasa/falla) y el comando que lo verifica.
  * Flag que la protege (nombre exacto) y su default seguro.
  * Impacto por runtime (Codex / Claude Code / Copilot) y el fallback de cada uno.
  * "Trabajo del operador: ninguno" o "opt-in (default off)".
- Prohibido lo vago: nada de "etc.", "según corresponda", "ajustar lo necesario". Todo concreto.
- Incluí un Glosario corto de términos del dominio Stacky que un modelo menor podría no conocer.
- Incluí "Orden de implementación" (lista numerada) y "Definición de Hecho (DoD)" global.

FORMATO DEL DOCUMENTO:
1. Título + objetivo (1 párrafo) + KPI/impacto esperado.
2. Por qué ahora / gap que cierra (apoyado en los planes recientes leídos).
3. Principios y guardarraíles (las restricciones de arriba).
4. Fases F0..Fn con TODO el detalle anterior.
5. Riesgos y mitigaciones.
6. Fuera de scope.
7. Glosario + Orden de implementación + DoD.

COSTO / FORMA DE TRABAJO:
- NO implementes código; entregás SOLO el documento del plan.
- Exploración mínima; si necesitás fan-out, un único subagente Haiku con scope cerrado.

ENTREGABLE FINAL: ruta del archivo `<NN>_PLAN_*.md` creado + resumen de 5 líneas (qué propone, valor,
por qué NO agrega trabajo al operador, cómo respeta los 3 runtimes).
```

## Checklist de aceptación del plan
- [ ] El número `<NN>` se calculó listando el directorio (consecutivo, no hardcodeado).
- [ ] Cada fase tiene: archivos exactos, símbolos exactos, pseudocódigo/diff, tests + comando, criterio
      binario, flag + default, impacto por runtime y línea de "trabajo del operador".
- [ ] No hay frases vagas ("etc.", "según corresponda"). Todo es ejecutable por un modelo menor.
- [ ] Valor alto y medible declarado (KPI/impacto).
- [ ] Cero trabajo extra al operador (o opt-in con default seguro).
- [ ] Paridad/fallback en Codex, Claude Code y GitHub Copilot Pro, por ítem.
- [ ] No degrada performance/seguridad/estabilidad/DX; backward-compatible; reusa lo existente.
- [ ] Incluye Glosario, Orden de implementación y DoD.
- [ ] No se implementó código; solo el documento del plan.
