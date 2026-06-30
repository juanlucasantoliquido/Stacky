# Plan 41 — Pre-vuelo de Intención: que Stacky te diga "esto es lo que entendí y así lo voy a hacer" ANTES de gastar el run, y vos lo confirmes o corrijas en 1 click

> **Estado:** IMPLEMENTADO 2026-06-19 (F0–F4).
>
> **Validación (2026-06-19):** test_intent_preflight_contract.py (6), test_intent_preflight_generate.py (5),
> test_intent_preflight_ranking.py (5), test_run_brief_preflight.py (7), test_corrections_block_priority.py (2);
> sin regresión en run_brief/flags; tsc --noEmit exit 0. Modal IntentPreflightModal.tsx integrado en EpicFromBriefModal.
> **Nota de implementación:** la pasada corta (`invoke_short_llm`) usa el LLM backend interno (copilot_bridge),
> server-side y agnóstico al runtime del agente; si el bridge no está disponible → PreflightRuntimeUnavailable →
> fallback al camino normal (idéntico a flag OFF). Esto respeta el contrato (nunca bloquea) aunque no abra una
> sesión CLI corta por runtime (decisión arquitectónica: el cerebro de Stacky usa LLM_BACKEND, no el runtime).
> **Numeración:** 41 (consecutiva; máximo previo real en `Stacky Agents/docs/` = `40_PLAN_BUSINESS_AGENT_EPICA_GENERICA_AUTONOMA.md`. La secuencia es compartida planes/checklists/incidentes; 41 es el siguiente libre sin huecos).
> **Autor:** StackyArquitectoBrainstormer (frente divergente) — para pasar por el juez `criticar-y-mejorar-plan`.
> **Audiencia de implementación:** dev agéntico junior / modelo menor (Haiku, Codex CLI, GitHub Copilot Pro). Cada fase es autocontenida: objetivo en 1 frase, archivos EXACTOS, símbolos EXACTOS, pseudocódigo/diff, tests primero con comando exacto, criterio binario, flag + default seguro, impacto por runtime con fallback, y línea "Trabajo del operador".

---

## PARTE I — PORTAFOLIO DE IDEAS (divergencia antes de converger)

> Esta sección es el brainstorm que precede al plan. El juez puede usarla para entender por qué se eligió F (el plan formalizado en la Parte II) y descartar/rescatar las demás. **La idea elegida es la D — "Pre-vuelo de Intención".** Las otras quedan documentadas como direcciones futuras.

### Frontera actual (qué ya está cubierto — para NO repetir)

Los planes recientes se agrupan en dos frentes, ambos **internos al motor**:

- **Calidad del entregable / robustez del motor (27-35):** el agente piensa mejor (retrieval/routing/caché), no se ahoga (lifecycle/watchdog), cumple criterios derivados del ticket (29), está anclado a la realidad (30), ejecuta lo que produce y lo gatea (31/32), y —propuesto, **no implementado**— aprendería de sus propios fallos (35).
- **Runtime + flujo brief→épica (36-40):** el selector de runtime siempre se respeta sin fallback silencioso (36/37), el flujo "brief → Épica" tiene versión/trazabilidad/aprobación en modal (38), hay historial de runs y fix de DB read-only (39), y el BusinessAgent produce épicas ricas con modelo configurable (40).

**El patrón común:** todo esto mejora **lo que Stacky entrega DESPUÉS de arrancar el run**. En ningún plan Stacky **conversa con el operador ANTES de gastar el run** para alinear qué entendió. El operador tira un brief/ticket y reza: si Stacky malinterpretó, se entera 3-15 minutos (y varios miles de tokens) después, leyendo un entregable equivocado. **Ese hueco —el "antes", el momento de alineación de intención— está completamente vacío.** Es la tierra fértil.

### Las 5 ideas (mutuamente distintas en mecanismo y dirección)

---

#### Idea A — "Caja Negra → Cabina de Vidrio": narración del razonamiento en vivo

- **Pitch:** mientras el agente trabaja, Stacky transmite en un panel un hilo legible de "qué estoy haciendo y por qué" (leí X, asumí Y, voy a generar Z), no logs crudos.
- **La chispa:** hoy el operador mira logs técnicos o una barra de "running". El insight es que el agente **ya produce** decisiones intermedias en su cadena; solo que se tiran. Transferencia analógica: la **cabina de un avión** no oculta los instrumentos, los muestra calibrados. Convertir el stream de logs (que ya existe, `log_streamer.py`) en una narración de intención calibrada.
- **El "wow":** el operador ve a Stacky *pensar* y gana confianza (o detecta el descarrío temprano). Deja de ser una caja negra.
- **Qué desbloquea:** base para cancelación informada ("lo veo yendo mal, lo paro") y para la Idea D (si el agente narra intención, narrarla ANTES de ejecutar es un paso natural).
- **Nivel de audacia:** Incremental.
- **Para el juez:** el supuesto riesgoso es que la "narración" sea fiel y no teatro — que refleje decisiones reales del agente y no un resumen inventado post-hoc. Paridad: ¿los 3 runtimes emiten señal de razonamiento parseable, o Copilot la oculta? Riesgo de ruido visual = más, no menos, carga cognitiva.

---

#### Idea B — "Memoria de Gusto del Operador": el estilo se aprende solo

- **Pitch:** Stacky observa qué ediciona el operador sobre cada entregable (qué borra, qué reescribe, qué acepta tal cual) y deriva preferencias de estilo que reinyecta en runs futuros, sin que el operador configure nada.
- **La chispa:** el plan 35 aprende de **fallos del arnés** (criterios rojos). Esta idea aprende de la **señal humana silenciosa**: el diff entre lo que Stacky entregó y lo que el operador finalmente usó es la corrección más rica que existe, y hoy se descarta. Sustracción: eliminar la configuración de estilo — que el sistema la infiera.
- **El "wow":** "Stacky empezó a escribir como yo sin que se lo pidiera." El centauro se afina con el uso.
- **Qué desbloquea:** un perfil de estilo por operador/proyecto que mejora todos los agentes a la vez.
- **Nivel de audacia:** Audaz.
- **Para el juez:** el supuesto MÁS riesgoso es que Stacky **vea** el entregable editado — ¿hay un punto donde el operador devuelve su versión final, o el editado vive solo en ADO/su máquina y nunca vuelve? Sin esa señal de retorno, la idea no tiene combustible. Riesgo de sobreajuste (aprende una preferencia puntual y la generaliza mal). Choque potencial con human-in-the-loop si "aprende" demasiado y empieza a decidir tono por su cuenta.

---

#### Idea C — "Banco de Pruebas de Prompts en Sombra" (A/B del propio cerebro)

- **Pitch:** cuando el operador edita un `.agent.md`, Stacky corre la versión vieja y la nueva sobre un set de briefs-semilla guardados y le muestra un diff de calidad lado a lado, para que decida con evidencia si el cambio de prompt mejora.
- **La chispa:** los `.agent.md` son el código fuente del comportamiento, pero se editan a ciegas (el plan 40 reescribió el BusinessAgent **sin** forma de medir si mejoró — su propia crítica C3 lo admite). Inversión: en vez de "editás el prompt y rezás", "editás el prompt y Stacky te muestra el antes/después".
- **El "wow":** ingeniería de prompts con red de seguridad: el operador ve objetivamente si su edición ayuda o rompe.
- **Qué desbloquea:** evolución segura de los agentes; un corpus de "briefs de regresión" reutilizable.
- **Nivel de audacia:** Audaz.
- **Para el juez:** el supuesto riesgoso es el costo (correr 2 versiones × N semillas quema tokens — choca con la conciencia de costo de UltraCode) y **quién juzga** cuál salida es "mejor" (¿un LLM-juez? ¿el operador a ojo?). Paridad: el A/B tendría sentido sobre todo para el runtime CLI Claude; en Copilot/Codex el modelo lo gobierna otra config.

---

#### Idea D — "Pre-vuelo de Intención": confirmá el plan ANTES de gastar el run **[ELEGIDA → Parte II]**

- **Pitch:** antes de lanzar el run pesado, Stacky hace una pasada baratísima que devuelve un **Brief de Intención** ("esto es lo que entendí: objetivo, entregables, supuestos, riesgos, archivos que tocaría") y el operador lo **aprueba, corrige o cancela en 1 click**. Recién ahí corre el run completo, ya alineado.
- **La chispa:** el momento de máxima divergencia entre lo-que-el-operador-quiere y lo-que-Stacky-entiende es el **arranque**, y es exactamente donde no hay ningún control. El insight no obvio: **el flujo brief→épica del plan 38 YA inventó el patrón ganador** —"genero algo barato → modal de aprobación → recién entonces actúo"— pero lo aplicó solo a publicar Épicas en ADO. **Generalizarlo a CUALQUIER run** es la jugada. Checklist quirúrgico: el cirujano confirma "paciente, procedimiento, lado" *antes* de la incisión, no después. El "time-out" pre-quirúrgico aplicado al run.
- **El "wow":** "Stacky me dijo lo que iba a hacer, vi que había entendido mal 'el batch', se lo corregí en 10 segundos, y el run salió perfecto a la primera." Cero entregables-basura por malentendido. El operador siente que **dirige**, no que **adivina y reza**.
- **Qué desbloquea:** (1) es el lugar natural donde aterriza el R-BATCH del plan 40 (los `[SUPUESTO]`/`[PENDIENTE]` dejan de ser texto enterrado en el HTML final y se vuelven **preguntas de pre-vuelo** que el operador resuelve antes); (2) reduce drásticamente los runs desperdiciados (ahorro de tokens real, alineado con UltraCode); (3) crea el "gancho" de UI donde, más adelante, enchufar la narración (Idea A) y el gusto (Idea B).
- **Nivel de audacia:** Audaz (contrarian respecto a la trayectoria: todos los planes recientes invierten en el "después"; este invierte en el "antes").
- **Para el juez:** supuestos a stress-testear, en orden de riesgo:
  1. **¿Agrega trabajo al operador?** Es un click nuevo por run. La defensa: es **opt-in con default OFF**, y cuando está ON reemplaza la incertidumbre por una decisión de 10s que **ahorra** el costo de un run equivocado. Pero el juez debe validar que el default OFF y el "aprobar con Enter" eviten fricción. (Mitigado en F4 con "auto-approve si confianza alta", configurable.)
  2. **Paridad de 3 runtimes:** la pasada de pre-vuelo es una llamada LLM barata. ¿Se puede hacer en los 3? El cerebro interno de Stacky hoy es `LLM_BACKEND` (copilot/vscode_bridge/mock; **sin anthropic-directo** — verificado `config.py:75`). El plan debe resolver con qué motor se genera el pre-vuelo sin atarlo a un runtime. (Resuelto en F1: el pre-vuelo usa el MISMO runtime que el operador eligió para el run, vía una invocación corta y acotada; fallback explícito si el runtime no puede.)
  3. **Human-in-the-loop:** ¿lo respeta? Sí, lo **refuerza** (más control del operador, no menos). No hay autonomía: Stacky propone entendimiento, el humano decide.
  4. **No degradar:** con flag OFF, el flujo de run es byte-idéntico al actual.

---

#### Idea E — "Stacky te interrumpe cuando vale la pena" (clarificación selectiva) **[ROMPE-MARCO]**

- **Pitch:** en vez de que Stacky *siempre* asuma y siga (la regla M6 del plan 40: ambigüedad → `[SUPUESTO]` y avanzar), Stacky **calcula el costo de equivocarse** y, solo cuando una ambigüedad es de alto impacto y barata de resolver, hace **una** pregunta puntual antes de arrancar. El resto lo sigue asumiendo.
- **La chispa:** rompe el dogma vigente "autonomía total, nunca preguntes" (plan 40 M6, memoria `autonomy-resolve-own-doubts`). El insight contrarian: **la autonomía total es óptima solo si el costo de un supuesto equivocado es bajo.** Cuando una mala interpretación arruina TODO el entregable (p.ej. "¿este RF es para el batch nocturno o el de cierre?"), una pregunta de 5 segundos vale más que un run de 10 minutos tirado. No es "preguntar siempre" (eso ya se rechazó) ni "nunca" (lo actual): es **preguntar con criterio económico**, casi nunca, solo cuando el ROI de preguntar es altísimo.
- **El "wow":** Stacky deja de entregar cosas confiadamente equivocadas; muestra **juicio** sobre cuándo su propia incertidumbre es peligrosa.
- **Qué desbloquea:** un agente que se siente senior (sabe cuándo NO sabe y cuándo eso importa), sin volverse molesto.
- **Nivel de audacia:** Moonshot (toca un dogma de identidad — por eso `[ROMPE-MARCO]`).
- **Para el juez:** el supuesto MÁS riesgoso y por qué probablemente el juez lo frene: choca de frente con la decisión ya tomada de "autonomía total, no frenar el run" (memoria `autonomy-resolve-own-doubts` + plan 40 M6). El operador explícitamente NO quiere que el agente se frene a media ejecución. La versión defendible es **fusionarla con D**: las "preguntas de alto ROI" no interrumpen a media ejecución, sino que se presentan **en el pre-vuelo** (antes de gastar), donde preguntar es legítimo porque aún no se gastó nada. Standalone (interrumpir el run) = casi seguro RECHAZADO; **como sabor de D** = viable. Por eso D la absorbe (ver F2: ranking de supuestos por impacto).

### Por qué se elige D (y absorbe lo mejor de E)

- **Es la dirección que rompe el molde sin romper los rieles:** invierte el foco de "mejorar el después" a "alinear el antes", algo que ningún plan tocó, pero lo hace con el patrón ya bendecido por el operador en el plan 38 (generar-barato → aprobar → actuar).
- **Reusa, no reinventa:** el modal de aprobación (38), el seam de contexto (`enrich_blocks`), el sistema de flags por UI (33), el R-BATCH/supuestos (40). Sustrato listo.
- **Ataca un dolor real y medible:** runs desperdiciados por malentendido = tokens quemados + tiempo del operador leyendo basura. UltraCode lo va a agradecer.
- **Absorbe E de forma segura:** la única parte viable de la moonshot (preguntar con criterio económico) vive dentro del pre-vuelo, donde preguntar es gratis y legítimo.
- **Abre la puerta a A y B:** una vez que existe el "momento de pre-vuelo" como superficie de UI, narración (A) y gusto (B) tienen dónde enchufarse.

> **Handoff:** la Parte II formaliza la Idea D para que un modelo menor la implemente. Pasala luego por `criticar-y-mejorar-plan` (el juez) para validar viabilidad real, en especial el supuesto #1 (fricción) y #2 (paridad del motor de pre-vuelo).

---

## PARTE II — PLAN FORMALIZADO (Idea D)

## 1. Título, objetivo y KPI

**Objetivo.** Introducir un **Pre-vuelo de Intención** opcional (flag, default OFF): antes de lanzar el run pesado, Stacky genera una pasada **corta y acotada** que produce un **Brief de Intención** estructurado (objetivo entendido, entregables previstos, supuestos rankeados por impacto, preguntas de alto ROI, archivos/áreas que tocaría) y lo presenta al operador en un modal para **Aprobar / Corregir / Cancelar**. Solo tras la aprobación corre el run completo, inyectando las correcciones del operador como contexto de máxima prioridad. Con el flag OFF, el comportamiento es **byte-idéntico** al actual.

**Por qué es valioso.** Hoy el operador descubre los malentendidos de Stacky **después** de pagar el run completo (tokens + minutos), leyendo un entregable equivocado. El pre-vuelo mueve el punto de control al **antes**, donde corregir cuesta 10 segundos en vez de un run entero. Amplifica al operador (más dirección, menos adivinanza) y ahorra tokens (menos runs-basura).

**KPI / impacto (medibles, sin telemetría nueva pesada — se exponen en la DiagnosticsPage existente vía `harness_health`):**
- **KPI-1 (binario):** con el flag ON, lanzar un run desde el flujo brief→épica produce primero un Brief de Intención (HTTP 200 con el JSON estructurado) y NO arranca el run pesado hasta recibir la aprobación. Verificado por test.
- **KPI-2 (binario):** con el flag OFF, el endpoint de run se comporta exactamente como hoy (mismo status, mismo efecto); test de control byte-idéntico.
- **KPI-3 (operador, medible por contador):** % de pre-vuelos que el operador **corrige** antes de aprobar (señal de que Stacky había entendido mal y el pre-vuelo lo cazó). Baseline 0 (no existe); se reporta como `preflight_corrected_total` / `preflight_total` por proyecto.
- **KPI-4 (costo, medible):** ratio `tokens_preflight / tokens_run_completo` por run — debe ser bajo (el pre-vuelo es barato). Objetivo declarado: el pre-vuelo cuesta < 15% de un run completo (se mide; si se pasa, se ajusta el `effort`/longitud del pre-vuelo).

---

## 2. Por qué ahora / gap que cierra

Apoyado en los planes recientes leídos (38 brief→épica+modal, 40 BusinessAgent+R-BATCH+modelo configurable, 39 historial+run-brief, 35 aprendizaje propuesto, 30-32 verificación):

- **El plan 38 ya validó el patrón "generar barato → aprobar en modal → actuar"** pero lo encapsuló en un solo caso: publicar Épicas a ADO (`EpicFromBriefModal.tsx`, `POST /api/tickets/epics/from-brief`). El run que **genera** la épica, en cambio, arranca sin pre-vuelo. Este plan **generaliza el patrón al arranque del run**.
- **El plan 40 introdujo los `[SUPUESTO]`/`[PENDIENTE]` y el R-BATCH** (ambigüedad → marcar y seguir; nunca dejar "el batch" anónimo). Hoy esos marcadores quedan **enterrados en el HTML final** — el operador los descubre al leer el entregable. El pre-vuelo los **eleva a preguntas accionables ANTES de gastar el run**: es el lugar natural donde el R-BATCH se resuelve en origen ("¿qué proceso batch? → `FacturacionNocturna`") en vez de marcarse como deuda.
- **El plan 39 dejó el flujo `run-brief` con manejo de error robusto y un Brief Pool Ticket** (`agents.py:544`, `ado_id=-1`). Ese mismo endpoint es el punto de inserción ideal del pre-vuelo: ya es el embudo por donde pasa el brief.
- **Ningún plan (27-40) gastó un solo ítem en el "antes" del run.** Todo el esfuerzo fue en el motor (calidad del entregable) y el runtime (estabilidad). El momento de alineación de intención está vacío. Este plan lo llena reusando todo lo existente.

**Decisión de alcance del MVP:** el pre-vuelo se cablea **primero y solo** en el flujo **brief→épica** (`run-brief`), porque (a) ya tiene un modal y un patrón de aprobación del plan 38 sobre el cual construir, y (b) es el flujo donde el malentendido es más caro (una épica entera mal entendida). Extenderlo al run genérico de tickets reales es **fuera de scope** de este plan (ver §6), explícitamente diferido para no inflar el alcance.

---

## 3. Principios y guardarraíles (no negociables, vinculantes en todas las fases)

1. **3 runtimes con paridad:** el pre-vuelo se genera con el **mismo runtime que el operador eligió para el run** (Codex CLI / Claude Code CLI / GitHub Copilot Pro), mediante una invocación corta y acotada. Si un runtime no puede ejecutar la pasada corta (sesión CLI no logueada, bridge sin responder), **fallback explícito**: se omite el pre-vuelo y se procede como con flag OFF, informando al operador "pre-vuelo no disponible para este runtime ahora". Nunca se bloquea el run por falta de pre-vuelo.
2. **Cero trabajo extra obligatorio:** flag **default OFF**. Con OFF, byte-idéntico a hoy. Con ON, el único "trabajo" es una decisión de 1 click (Aprobar/Corregir/Cancelar) que **reemplaza** la incertidumbre actual, y se puede acelerar con "auto-aprobar si no hay preguntas abiertas" (F4, configurable).
3. **Human-in-the-loop innegociable — y REFORZADO:** el pre-vuelo es 100% propuesta de entendimiento; **el operador decide**. No hay autonomía nueva: Stacky no decide nada solo, al contrario, le da al operador un punto de control que hoy no tiene. La regla 11 se respeta y se amplifica.
4. **Mono-operador sin auth real:** nada de RBAC ni multiusuario. El pre-vuelo es del operador único.
5. **No degradar performance/seguridad/estabilidad/DX:** flag OFF byte-idéntico (test de control en cada fase). El pre-vuelo es aditivo. Reusar lo existente (modal del 38, `enrich_blocks`, flags-UI del 33, `harness_health` para KPIs). Cero tabla nueva, cero migración de schema, cero dependencia nueva.
6. **TDD:** test primero en cada fase backend. Frontend: vitest NO está instalado → criterio degradado a `npm run build` (0 errores TS) + verificación manual descrita. (Ver memoria `stacky-backend-dev-test-env`.)
7. **Suite contaminada → validar SIEMPRE por archivo** con el python del `.venv` (pin `pywin32==306` roto en py3.13). Nunca correr la suite completa como criterio.
8. **Flag nuevo → `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`) en la MISMA fase/PR que lo introduce**, default seguro, retro-compat byte-idéntica con flag OFF. Aparece en `HarnessFlagsPanel` (plan 33) sin tocar frontend.
9. **Sin secretos en el Brief de Intención:** el pre-vuelo NUNCA incluye passwords/PAT/paths sensibles. Reusa el detector de secretos de la memoria colaborativa para redactar antes de devolver.

> **Comando base de tests backend** (cada fase ajusta el archivo):
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/<ARCHIVO>" -q`
> Frontend: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" ; npm run build` (0 errores TS).

---

## 4. Glosario (términos del dominio Stacky que un modelo menor podría no conocer)

- **Brief de Intención (Intent Brief):** el objeto estructurado que el pre-vuelo produce y el operador aprueba. Contiene: `objective` (qué entendió Stacky), `deliverables` (qué va a producir), `assumptions` (lista rankeada por impacto), `open_questions` (preguntas de alto ROI a resolver antes), `areas` (archivos/módulos/datos que tocaría), `confidence` (0-1). **No es** la Épica ni el entregable; es el "esto entendí, así lo voy a hacer".
- **Pre-vuelo (preflight):** la pasada corta y acotada que genera el Brief de Intención. Barata por diseño (prompt corto, salida acotada, effort bajo).
- **`run-brief`:** endpoint `POST /api/agents/run-brief` (plan 38) que lanza el BusinessAgent sobre un Brief Pool Ticket sintético (`ado_id=-1`) para generar una Épica desde un brief. Punto de inserción del pre-vuelo en este plan.
- **Brief Pool Ticket:** ticket local sintético `ado_id=-1` por proyecto que ancla la corrida del brief (plan 38/39).
- **`enrich_blocks`:** seam único de armado de contexto común a los 3 runners (`backend/services/context_enrichment.py:34`). Las correcciones del operador se inyectan aquí como bloque de máxima prioridad.
- **`run_agent`:** orquestador que lanza un agente sobre un ticket con un runtime (`backend/agent_runner.py`). Acepta `model_override` (plan 40) y, según ese plan, podría aceptar `effort_override`.
- **R-BATCH:** regla del plan 40 que prohíbe referirse a "el batch" sin nombrar el proceso concreto. En este plan, los marcadores `[PENDIENTE: nombre del proceso batch]` se convierten en `open_questions` del pre-vuelo.
- **Human gate / regla 11:** el operador aprueba; nunca se reemplaza su decisión. Ver memoria `human-in-the-loop-fundamental`.
- **Flag OFF byte-idéntico:** con el flag en su default OFF, el comportamiento es exactamente el actual.
- **`FLAG_REGISTRY` / `FlagSpec`:** registro de flags (`backend/services/harness_flags.py`) que hace que un flag aparezca en `HarnessFlagsPanel` (UI) sin tocar frontend (plan 33).

---

## 5. Fases (orden de implementación por dependencia)

> **Resumen de dependencias:** F0 (contrato + flags, sin efecto) → F1 (generador de pre-vuelo backend) → F2 (ranking de supuestos/preguntas, refuerza F1) → F3 (endpoint que orquesta pre-vuelo y luego run con correcciones) → F4 (modal frontend + auto-aprobar). F0-F3 son backend; F4 es frontend. Cada una verificable sola.

---

### FASE F0 — Contrato del Brief de Intención + flags (sustrato inerte, sin efecto runtime)

**Objetivo (1 frase):** definir el dataclass `IntentBrief` y su serialización, más los flags que gobiernan la feature, sin enganchar nada al runtime todavía. **Valor:** contrato común y estable que consumen F1-F4.

**Archivos a crear/editar (rutas exactas):**
- CREAR `backend/services/intent_preflight.py` — módulo único del pre-vuelo de intención.
- EDITAR `backend/config.py` — agregar las env vars de los flags.
- EDITAR `backend/services/harness_flags.py` — registrar los `FlagSpec` (grupo `preflight`).
- EDITAR `backend/.env.example` — documentar las keys.

**Símbolos exactos a crear (en `intent_preflight.py`):**
```python
from dataclasses import dataclass, field, asdict

PREFLIGHT_VERSION = "1"

@dataclass(frozen=True)
class IntentAssumption:
    text: str                 # el supuesto en lenguaje natural
    impact: str               # "high" | "medium" | "low" — costo de equivocarse
    needs_confirmation: bool   # True si es alto impacto y barato de confirmar (alto ROI)

@dataclass(frozen=True)
class IntentBrief:
    objective: str                          # qué entendió Stacky que hay que lograr
    deliverables: list[str]                 # qué va a producir
    assumptions: list[IntentAssumption]      # supuestos rankeados por impacto
    open_questions: list[str]               # preguntas de alto ROI a resolver ANTES
    areas: list[str]                        # archivos/módulos/datos/procesos que tocaría
    confidence: float                       # [0,1] autoevaluación de cuán claro está el pedido
    version: str = PREFLIGHT_VERSION

def to_payload(brief: IntentBrief) -> dict:
    """Serializa a dict JSON-safe para el frontend (asdict + redacción de secretos)."""
    ...

def from_model_json(raw: str) -> IntentBrief:
    """Parsea la salida JSON del modelo a IntentBrief, tolerante a campos faltantes.
    Campos ausentes -> defaults seguros (listas vacías, confidence 0.5, objective '')."""
    ...
```

**Pseudocódigo de `from_model_json` (casos borde explícitos):**
```
def from_model_json(raw):
    data = _safe_json_loads(raw)          # tolera ```json fences, texto antes/después
    if data is None:                      # el modelo no devolvió JSON parseable
        return IntentBrief(objective="", deliverables=[], assumptions=[],
                           open_questions=[], areas=[], confidence=0.0)  # confianza 0 -> el operador SIEMPRE revisa
    assumptions = [
        IntentAssumption(text=a.get("text",""),
                         impact=a.get("impact","medium") if a.get("impact") in ("high","medium","low") else "medium",
                         needs_confirmation=bool(a.get("needs_confirmation", False)))
        for a in (data.get("assumptions") or []) if a.get("text")
    ]
    return IntentBrief(
        objective=(data.get("objective") or "").strip(),
        deliverables=[d for d in (data.get("deliverables") or []) if d],
        assumptions=assumptions,
        open_questions=[q for q in (data.get("open_questions") or []) if q],
        areas=[s for s in (data.get("areas") or []) if s],
        confidence=_clamp01(data.get("confidence", 0.5)),
    )
# Caso borde: raw vacío o no-JSON -> confidence 0.0 (fuerza revisión). NUNCA lanza.
```

**Diff ilustrativo en `config.py`:**
```python
# --- Plan 41: Pre-vuelo de Intención ---
INTENT_PREFLIGHT_ENABLED = os.getenv("INTENT_PREFLIGHT_ENABLED", "false").lower() == "true"
# Auto-aprobar el pre-vuelo cuando no hay open_questions y confidence >= umbral (reduce fricción):
INTENT_PREFLIGHT_AUTO_APPROVE = os.getenv("INTENT_PREFLIGHT_AUTO_APPROVE", "false").lower() == "true"
INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF = float(os.getenv("INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF", "0.8"))
```

**Diff ilustrativo en `harness_flags.py` (FlagSpec — referencia canónica de los 3 flags):**
```python
FlagSpec(key="INTENT_PREFLIGHT_ENABLED", type="bool",
         label="Pre-vuelo de Intención (41)",
         description="41 — Si ON, antes del run genera un Brief de Intención que el operador aprueba/corrige.",
         group="preflight"),
FlagSpec(key="INTENT_PREFLIGHT_AUTO_APPROVE", type="bool",
         label="Pre-vuelo: auto-aprobar si está claro",
         description="41 — Si ON, salta el modal cuando no hay preguntas abiertas y la confianza supera el umbral.",
         group="preflight"),
FlagSpec(key="INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF", type="float",
         label="Pre-vuelo: confianza mínima para auto-aprobar",
         description="41 — Umbral de confianza para auto-aprobar sin modal (default 0.8).",
         group="preflight"),
```

**Diff en `.env.example`:**
```
# Plan 41 — Pre-vuelo de Intención: antes del run, Stacky propone "esto entendí, así lo haré"
# y el operador lo aprueba/corrige. Default OFF (byte-idéntico al comportamiento actual).
INTENT_PREFLIGHT_ENABLED=false
INTENT_PREFLIGHT_AUTO_APPROVE=false
INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF=0.8
```

**Tests PRIMERO** — `backend/tests/test_intent_preflight_contract.py`:
- `test_from_model_json_parses_full_payload` — JSON completo → todos los campos poblados correctamente.
- `test_from_model_json_tolerates_fences` — salida con ```json ... ``` y texto alrededor → parsea igual.
- `test_from_model_json_empty_is_confidence_zero` — raw vacío/no-JSON → `confidence == 0.0`, sin lanzar.
- `test_invalid_impact_defaults_to_medium` — supuesto con `impact="urgent"` → queda `"medium"`.
- `test_to_payload_is_json_serializable` — `json.dumps(to_payload(brief))` no lanza.
- `test_to_payload_redacts_secrets` — un `objective`/`area` con algo tipo PAT → redactado en el payload.

**Comando exacto:**
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_intent_preflight_contract.py" -q
```
**Y los flags registrados** (agregar a `backend/tests/test_harness_flags.py`): `test_preflight_flags_registered` — las 3 keys están en `FLAG_REGISTRY` con grupo `preflight` y tipos correctos (`bool`/`bool`/`float`).
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_harness_flags.py" -q
```

**Criterio de aceptación (BINARIO):** los tests de contrato pasan; los 3 flags están en `FLAG_REGISTRY`; `config.py` expone las 3 variables con defaults seguros.

**Flag + default:** `INTENT_PREFLIGHT_ENABLED=false` (la estructura es inerte hasta F3). **Trabajo del operador: ninguno.**

**Impacto por runtime:** ninguno (F0 no se invoca en runtime). Fallback: n/a.

**Por qué NO viola regla 11:** solo define un tipo y flags; no decide ni actúa.

---

### FASE F1 — Generador del Pre-vuelo (pasada corta y acotada con el runtime elegido)

**Objetivo (1 frase):** dado un brief + contexto + runtime elegido, producir un `IntentBrief` mediante una invocación LLM **corta y barata**, con fallback explícito si el runtime no puede. **Valor:** el corazón de la feature — convierte el pedido del operador en "esto entendí" antes de gastar el run.

**Archivos a editar:**
- EDITAR `backend/services/intent_preflight.py` — agregar `generate_intent_brief` y el prompt de pre-vuelo.
- (Lectura, sin editar) `backend/agent_runner.py` — para entender cómo invocar el runtime de forma corta; ver nota de implementación abajo.

**Símbolos exactos a crear (en `intent_preflight.py`):**
```python
PREFLIGHT_SYSTEM_PROMPT = (
    "Sos el módulo de Pre-vuelo de Intención de Stacky. NO resuelvas la tarea. "
    "Tu único trabajo es DECLARAR brevemente qué entendiste del pedido y cómo lo abordarías, "
    "para que el operador confirme antes de gastar un run completo. "
    "Devolvé EXCLUSIVAMENTE un JSON con las claves: objective (str), deliverables (list[str]), "
    "assumptions (list de {text, impact in [high,medium,low], needs_confirmation bool}), "
    "open_questions (list[str] — SOLO preguntas de alto impacto y baratas de responder; si todo está claro, lista vacía), "
    "areas (list[str] — archivos/módulos/datos/procesos que tocarías; nombrá procesos batch concretos, nunca 'el batch'), "
    "confidence (float 0..1). Sé conciso. NO incluyas secretos, contraseñas ni tokens."
)

def generate_intent_brief(
    *, brief_text: str, context_summary: str, runtime: str, project_name: str | None,
    invoke_short_llm, log,
) -> IntentBrief | None:
    """Genera el IntentBrief con una pasada corta.
    - invoke_short_llm: callable(system, user, runtime, project) -> str (texto del modelo).
      Se inyecta (dependency injection) para testear sin LLM real y para mapear cada runtime.
    - Devuelve None si el runtime no puede ejecutar la pasada (fallback -> el caller procede sin pre-vuelo).
    - best-effort: cualquier excepción se loguea y devuelve None (NUNCA rompe el flujo)."""
```

**Pseudocódigo de `generate_intent_brief` (casos borde explícitos):**
```
def generate_intent_brief(*, brief_text, context_summary, runtime, project_name, invoke_short_llm, log):
    if not (brief_text or "").strip():
        return None                                   # sin brief no hay nada que pre-volar
    user_prompt = _build_user_prompt(brief_text, context_summary)   # corto: brief + resumen de contexto
    try:
        raw = invoke_short_llm(PREFLIGHT_SYSTEM_PROMPT, user_prompt, runtime, project_name)
    except PreflightRuntimeUnavailable as exc:        # sesión CLI no lista, bridge caído, etc.
        log(f"[preflight] runtime '{runtime}' no disponible para pre-vuelo: {exc}")
        return None                                   # FALLBACK: el caller procede como flag OFF
    except Exception as exc:                          # best-effort, nunca rompe
        log(f"[preflight] fallo generando intent brief: {exc}")
        return None
    brief = from_model_json(raw)                       # tolerante (F0)
    return brief
# Caso borde: raw vacío -> from_model_json devuelve confidence 0.0 -> el operador SIEMPRE revisa (correcto).
# Caso borde: invoke_short_llm devuelve None -> from_model_json(None) -> confidence 0.0.
```

**Nota de implementación (cómo `invoke_short_llm` mapea a cada runtime — PARIDAD):**
El callable `invoke_short_llm` es el punto de paridad. Su implementación concreta (que vive donde se cablea, F3) debe:
- **Claude Code CLI:** invocar el runner CLI en modo "una sola pregunta corta" (sin crear un `AgentExecution` pesado; reusar el camino de invocación corta del runner si existe, o una llamada acotada con `effort=low` y límite de tokens de salida). Si la sesión Claude no está logueada → lanzar `PreflightRuntimeUnavailable` → fallback.
- **Codex CLI:** análogo con el runner Codex.
- **GitHub Copilot:** vía `copilot_bridge` (`backend/copilot_bridge.py`) — una llamada de chat corta. Si el bridge no responde → `PreflightRuntimeUnavailable` → fallback.
- **Regla de oro:** el pre-vuelo usa el **mismo runtime** que el operador eligió para el run, para que "lo que entendió el pre-vuelo" sea consistente con "lo que hará el run". Nunca se fuerza un runtime distinto.
- **Si NINGÚN runtime puede** (todos lanzan `PreflightRuntimeUnavailable`): el flujo procede **sin** pre-vuelo (idéntico a flag OFF) e informa al operador "pre-vuelo no disponible ahora".

> **Definición de `PreflightRuntimeUnavailable`** (en `intent_preflight.py`): `class PreflightRuntimeUnavailable(Exception): ...`. La lanza el `invoke_short_llm` cuando el runtime no está listo.

**Tests PRIMERO** — `backend/tests/test_intent_preflight_generate.py` (se inyecta un `invoke_short_llm` fake; NO se llama a ningún LLM real):
- `test_generate_returns_brief_from_fake_llm` — fake devuelve JSON válido → `IntentBrief` con `objective` poblado.
- `test_generate_empty_brief_returns_none` — `brief_text=""` → `None` (no pre-vuela).
- `test_generate_runtime_unavailable_returns_none` — el fake lanza `PreflightRuntimeUnavailable` → `None` (fallback), sin propagar.
- `test_generate_never_raises_on_garbage` — el fake lanza `RuntimeError` → `None`, atrapado.
- `test_generate_garbage_json_is_low_confidence` — el fake devuelve "no soy json" → `IntentBrief` con `confidence == 0.0`.

**Comando exacto:**
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_intent_preflight_generate.py" -q
```

**Criterio de aceptación (BINARIO):** los 5 tests pasan; `generate_intent_brief` nunca propaga excepción y devuelve `None` en todos los caminos de fallo.

**Flag + default:** gobernado por `INTENT_PREFLIGHT_ENABLED` (default OFF) en el caller (F3). El generador en sí es inerte hasta que F3 lo invoca. **Trabajo del operador: ninguno.**

**Impacto por runtime:**
- **Claude Code CLI / Codex CLI / Copilot:** el generador es runtime-agnóstico; la paridad la garantiza `invoke_short_llm` (un mapeo por runtime, cada uno con su fallback).
- **Fallback común:** runtime no disponible → `None` → el flujo procede sin pre-vuelo (idéntico a hoy). Nunca se bloquea el run.

**Por qué NO viola regla 11:** genera una **descripción** de entendimiento; no decide ni ejecuta la tarea. El run real solo arranca tras la aprobación del operador (F3).

**Salvaguarda de costo (KPI-4):** el prompt es corto, `effort=low`, salida JSON acotada. El caller (F3) mide `tokens_preflight` vs `tokens_run` y lo expone; si el ratio supera el objetivo (15%), se recorta el prompt/salida.

---

### FASE F2 — Ranking de supuestos por impacto + preguntas de alto ROI (absorbe lo viable de la Idea E)

**Objetivo (1 frase):** ordenar los `assumptions` por impacto y marcar cuáles merecen confirmarse antes (alto impacto + barato), derivando las `open_questions` de forma determinista cuando el modelo no las separó bien. **Valor:** el operador ve primero lo que más importa; las "preguntas que vale la pena hacer antes de gastar" emergen sin interrumpir ningún run (la única forma segura de la moonshot E).

**Archivos a editar:**
- EDITAR `backend/services/intent_preflight.py` — agregar `rank_and_flag` y `derive_open_questions`.

**Símbolos exactos a crear:**
```python
_IMPACT_ORDER = {"high": 0, "medium": 1, "low": 2}

def rank_and_flag(brief: IntentBrief) -> IntentBrief:
    """Devuelve una copia del brief con assumptions ordenados por impacto (high primero)
    y open_questions enriquecidas con los supuestos high-impact que needs_confirmation=True
    y que aún no figuren como pregunta. Determinista, sin LLM."""

def derive_open_questions(assumptions: list[IntentAssumption], existing: list[str]) -> list[str]:
    """Por cada supuesto con impact=='high' y needs_confirmation, si no hay ya una pregunta
    equivalente, genera '¿Confirmás que: <text>?'. Devuelve existing + las nuevas (sin duplicar)."""
```

**Pseudocódigo (casos borde explícitos):**
```
def rank_and_flag(brief):
    ranked = sorted(brief.assumptions, key=lambda a: _IMPACT_ORDER.get(a.impact, 1))
    questions = derive_open_questions(ranked, brief.open_questions)
    return replace(brief, assumptions=ranked, open_questions=questions)

def derive_open_questions(assumptions, existing):
    out = list(existing)
    seen = {q.strip().lower() for q in existing}
    for a in assumptions:
        if a.impact == "high" and a.needs_confirmation:
            q = f"¿Confirmás que: {a.text}?"
            if q.strip().lower() not in seen:
                out.append(q); seen.add(q.strip().lower())
    return out
# Caso borde: sin supuestos high → no agrega preguntas (todo claro → modal puede auto-aprobar en F4).
# Caso borde: pregunta ya existente equivalente → no duplica.
```

**Tests PRIMERO** — `backend/tests/test_intent_preflight_ranking.py`:
- `test_assumptions_sorted_high_first` — mezcla de impactos → `assumptions[0].impact == "high"`.
- `test_high_impact_needs_confirmation_becomes_question` — supuesto high+needs_confirmation → aparece como `open_question`.
- `test_low_impact_does_not_become_question` — supuesto low → NO genera pregunta.
- `test_no_duplicate_questions` — si la pregunta ya existía, no se duplica.
- `test_all_clear_yields_no_questions` — sin supuestos high → `open_questions` vacía (habilita auto-aprobar).

**Comando exacto:**
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_intent_preflight_ranking.py" -q
```

**Criterio de aceptación (BINARIO):** los 5 tests pasan; el ranking es determinista (sin LLM).

**Flag + default:** sin flag propio (lógica interna de F1/F3; siempre se aplica al brief generado). **Trabajo del operador: ninguno.**

**Impacto por runtime:** ninguno directo (pos-procesa el brief, igual para los 3). Fallback: n/a.

**Por qué NO viola regla 11 (y por qué E sí sería peligrosa standalone):** las preguntas se presentan **en el pre-vuelo, antes de gastar el run** — donde preguntar es legítimo porque no se gastó nada y el operador está en el lazo decidiendo arrancar. **No** se interrumpe un run en curso (eso sería la versión rechazada de la Idea E, que choca con `autonomy-resolve-own-doubts`). Si el operador no responde, F4 permite "aprobar igual" → el run procede asumiendo (comportamiento M6 del plan 40 preservado).

---

### FASE F3 — Orquestación: pre-vuelo → aprobación → run con correcciones (endpoint)

**Objetivo (1 frase):** insertar el pre-vuelo en el flujo `run-brief`: con flag ON, primero devolver el Brief de Intención y NO arrancar el run; tras la aprobación (con o sin correcciones del operador), arrancar el run inyectando las correcciones como contexto de máxima prioridad. **Valor:** cierra el lazo end-to-end; es donde el ahorro y el control se materializan.

**Archivos a editar:**
- EDITAR `backend/api/agents.py` — la función `run_brief` (`:544`) gana un modo de dos pasos detrás del flag; agregar el endpoint de aprobación.
- EDITAR `backend/services/context_enrichment.py` — `enrich_blocks` (`:34`): aceptar un bloque opcional de "correcciones del operador" de máxima prioridad.
- EDITAR `backend/services/intent_preflight.py` — agregar `build_corrections_block`.

**Diseño del flujo de dos pasos (sin estado de servidor nuevo — el frontend reenvía el brief):**

El pre-vuelo NO requiere persistir estado en el servidor entre los dos pasos: el frontend conserva el `brief` y, al aprobar, lo reenvía junto con las correcciones. Esto evita tabla nueva y sesiones server-side.

```
Paso 1 (pre-vuelo):  POST /api/agents/run-brief        body: { brief, runtime, model?, preflight: true }
  -> si INTENT_PREFLIGHT_ENABLED y body.preflight is True:
        intent = generate_intent_brief(...); intent = rank_and_flag(intent)
        if intent is None:   # runtime no disponible -> fallback a comportamiento OFF (arranca el run directo)
            <camino actual de run-brief, sin pre-vuelo>
        else:
            return 200 { "stage": "preflight", "intent": to_payload(intent) }   # NO arranca el run
  -> si flag OFF o body.preflight ausente/False:
        <camino actual de run-brief, byte-idéntico>   # arranca el run directo

Paso 2 (confirmación):  POST /api/agents/run-brief     body: { brief, runtime, model?, approved: true, corrections?: str }
  -> arranca el run real (camino actual de run-brief) + inyecta corrections como bloque de máxima prioridad
        return 202 { "stage": "running", "execution_id": ... }
```

**Diff ilustrativo en `agents.py` (`run_brief`):**
```python
# al inicio de run_brief, tras parsear el body:
preflight_requested = bool(payload.get("preflight"))
approved = bool(payload.get("approved"))
corrections = (payload.get("corrections") or "").strip() or None

# --- Paso 1: pre-vuelo (solo si flag ON y lo pidieron y NO viene ya aprobado) ---
if config.INTENT_PREFLIGHT_ENABLED and preflight_requested and not approved:
    intent = intent_preflight.generate_intent_brief(
        brief_text=brief_text,
        context_summary=_short_context_summary(project_name),  # resumen barato del client-profile, sin secretos
        runtime=runtime_raw,
        project_name=project_name,
        invoke_short_llm=_make_short_llm_invoker(),   # mapea runtime -> llamada corta (paridad)
        log=logger.info,
    )
    if intent is not None:
        intent = intent_preflight.rank_and_flag(intent)
        return jsonify({"stage": "preflight",
                        "intent": intent_preflight.to_payload(intent)}), 200
    # intent is None -> runtime no disponible -> cae al camino normal (arranca el run, comportamiento OFF)
    logger.info("run_brief: pre-vuelo no disponible para runtime=%s; se procede sin pre-vuelo", runtime_raw)

# --- Paso 2 / camino normal: arrancar el run real ---
# (si hay corrections, inyectarlas como bloque de máxima prioridad)
if corrections:
    context_blocks = intent_preflight.build_corrections_block(corrections) + context_blocks
# ... resto del run_brief ACTUAL sin cambios (crea pool ticket, llama run_agent, etc.) ...
```

**`build_corrections_block` (en `intent_preflight.py`):**
```python
CORRECTIONS_BLOCK_NAME = "operator-corrections"

def build_corrections_block(corrections: str) -> list:
    """Devuelve una lista con UN context block de máxima prioridad que el agente DEBE acatar:
    'El operador revisó el pre-vuelo y corrigió/aclaró: <corrections>. Esto MANDA sobre cualquier supuesto.'
    Se antepone a los context_blocks existentes para que gane prioridad en enrich_blocks."""
    text = ("### Correcciones del operador (OBLIGATORIO, mandan sobre supuestos)\n"
            + corrections.strip())
    return [{"name": CORRECTIONS_BLOCK_NAME, "kind": "raw-conversation", "text": text, "priority": 100}]
```

**Cambio en `enrich_blocks` (`context_enrichment.py:34`):** asegurar que un bloque con `priority=100` (o el nombre `operator-corrections`) quede **por encima** de todo otro bloque en el orden final. Si `enrich_blocks` ya respeta una clave `priority`, basta con que el bloque la traiga (ya la trae). Si no la respeta, agregar: los bloques `operator-corrections` se ordenan primero. **Verificar con grep cómo ordena hoy `enrich_blocks` antes de tocar; no romper el orden existente de los demás bloques.**

**Casos borde:**
- Flag OFF → `run-brief` byte-idéntico (la rama de pre-vuelo no se evalúa).
- `preflight: true` pero runtime no disponible → `generate_intent_brief` devuelve `None` → cae al camino normal (arranca el run), informando por log. El frontend recibe el 202 de "running" (no el 200 de "preflight"), por lo que sabe que se saltó el pre-vuelo.
- `approved: true` sin `corrections` → arranca el run sin bloque de correcciones (el operador aprobó tal cual).
- `corrections` con secreto → `build_corrections_block` redacta (reusa el detector de secretos). El operador NO debería pegar secretos, pero se protege.
- Body sin `brief` → 400 (regresión del comportamiento existente del plan 39 B1).

**TDD — test PRIMERO** — `backend/tests/test_run_brief_preflight.py` (stub de `generate_intent_brief` y de `run_agent` con monkeypatch; patrón de mock del repo: parchear lazy-imports en el módulo de origen):
1. `test_flag_off_is_byte_identical` — `INTENT_PREFLIGHT_ENABLED=False`, body con `preflight: true` → arranca el run igual que hoy (status 202, `run_agent` llamado). Control de no-regresión.
2. `test_preflight_returns_intent_and_does_not_run` — flag ON, `preflight: true` → status 200, `resp.json["stage"]=="preflight"`, `intent` presente, y `run_agent` **NO** fue llamado.
3. `test_preflight_runtime_unavailable_falls_through` — flag ON, `preflight: true`, pero el generador devuelve `None` → arranca el run (status 202), `run_agent` llamado (fallback).
4. `test_approved_runs_with_corrections_block` — flag ON, `approved: true`, `corrections: "el batch es FacturacionNocturna"` → `run_agent` llamado, y el `context_blocks` pasado contiene un bloque `operator-corrections` con ese texto, en primera posición.
5. `test_approved_without_corrections_runs_clean` — `approved: true` sin `corrections` → `run_agent` llamado sin bloque de correcciones.
6. `test_missing_brief_returns_400` — body sin `brief` → 400 (regresión).

**Comando exacto:**
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_run_brief_preflight.py" -q
```
Y test de prioridad del bloque (en `backend/tests/test_context_enrichment.py` si existe, o nuevo `test_corrections_block_priority.py`): `test_corrections_block_is_highest_priority` — un bloque `operator-corrections` queda primero en la salida de `enrich_blocks`.

**Criterio de aceptación (BINARIO):** los 6 tests de `test_run_brief_preflight.py` pasan + el test de prioridad pasa. Con flag OFF, no-regresión total.

**Flag + default:** `INTENT_PREFLIGHT_ENABLED` (default OFF). **Trabajo del operador:** con OFF, ninguno; con ON, una decisión de 1 click (F4).

**Impacto por runtime:**
- Los tres runtimes pasan por `run-brief`; el pre-vuelo usa el runtime elegido vía `_make_short_llm_invoker()`.
- **Fallback por runtime:** si el runtime no puede pre-volar (sesión CLI no lista, bridge caído) → se salta el pre-vuelo y se arranca el run (idéntico a OFF). Nunca se bloquea.

**Por qué NO viola regla 11:** el run real solo arranca cuando el operador lo aprueba (paso 2). Stacky no decide arrancar solo; **amplifica** el control del operador dándole un punto de revisión que hoy no existe.

---

### FASE F4 — Modal de Pre-vuelo en el frontend + auto-aprobar (cierra la experiencia)

**Objetivo (1 frase):** un modal que muestra el Brief de Intención (objetivo, entregables, supuestos rankeados, preguntas, áreas, confianza) con acciones **Aprobar / Corregir y aprobar / Cancelar**, y auto-aprobación opcional cuando todo está claro. **Valor:** materializa el "wow" — el operador ve qué entendió Stacky y decide en segundos.

**Archivos exactos:**
- EDITAR `frontend/src/api/endpoints.ts` — el método existente que llama a `run-brief` (buscar el que usa `EpicFromBriefModal`) acepta los nuevos campos `preflight`, `approved`, `corrections`; y tipar la respuesta `{ stage: "preflight" | "running", intent?: IntentBriefDTO, execution_id?: number }`.
- CREAR `frontend/src/components/IntentPreflightModal.tsx` — el modal del Brief de Intención.
- CREAR `frontend/src/components/IntentPreflightModal.module.css`.
- EDITAR el componente que hoy lanza el brief (`EpicFromBriefModal.tsx` u origen equivalente — confirmar con grep `run-brief`/`runBrief` en `frontend/src`) — para: (1) en submit, llamar con `preflight: true` si la feature está ON; (2) si la respuesta es `stage: "preflight"`, abrir `IntentPreflightModal` con el `intent`; (3) al aprobar, re-llamar con `approved: true` + `corrections`.

**Tipo `IntentBriefDTO` (en `endpoints.ts`):**
```ts
export interface IntentAssumptionDTO { text: string; impact: "high" | "medium" | "low"; needs_confirmation: boolean; }
export interface IntentBriefDTO {
  objective: string;
  deliverables: string[];
  assumptions: IntentAssumptionDTO[];
  open_questions: string[];
  areas: string[];
  confidence: number;   // 0..1
  version: string;
}
```

**UX del modal (`IntentPreflightModal.tsx`):**
- Encabezado: "Esto es lo que entendí. ¿Arranco así?" + badge de confianza (`confidence` como %, color: verde ≥0.8, ámbar 0.5-0.8, rojo <0.5).
- Secciones: **Objetivo** (texto), **Voy a producir** (lista), **Supuestos** (lista, los `high` con ícono de alerta arriba), **Preguntas antes de arrancar** (las `open_questions`, resaltadas si las hay), **Tocaría** (las `areas`).
- Un `<textarea>` "Corregir o aclarar (opcional)" prellenado vacío; lo que el operador escriba va como `corrections`.
- Botones: **[Arrancar así]** (approved, sin corrections) · **[Corregir y arrancar]** (approved + corrections, habilitado si el textarea tiene texto) · **[Cancelar]** (cierra, no arranca nada).
- Caso `open_questions` no vacío → el botón primario sugiere responder ("Respondé las preguntas o arrancá igual"), pero NO obliga (preserva M6: el operador puede arrancar asumiendo).

**Auto-aprobar (reduce fricción — KPI-3/supuesto #1 del juez):**
- Si `INTENT_PREFLIGHT_AUTO_APPROVE` está ON **y** `open_questions` está vacío **y** `confidence >= INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF`, el frontend **salta el modal** y llama directo con `approved: true`. El pre-vuelo igual corrió (y se puede ver en el historial), pero el operador no fue interrumpido cuando no hacía falta. La decisión de auto-aprobar se expone en la respuesta del backend (agregar `"auto_approvable": bool` al payload de `stage: preflight` calculado server-side con los flags) para que el frontend no tenga que conocer los umbrales.

**Cambio en el payload de F3 para soportar auto-aprobar:** en F3, al devolver `stage: preflight`, incluir `"auto_approvable": (config.INTENT_PREFLIGHT_AUTO_APPROVE and not intent.open_questions and intent.confidence >= config.INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF)`. (Agregar este campo y un test `test_preflight_marks_auto_approvable` en `test_run_brief_preflight.py`.)

**TDD — vitest no instalado → criterio degradado:**
- Obligatorio: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" ; npm run build` → 0 errores TS.
- Verificación manual:
  1. Flag ON, generar una épica desde brief → aparece el modal de Pre-vuelo con objetivo/entregables/supuestos.
  2. Escribir una corrección ("el batch es FacturacionNocturna") y **Corregir y arrancar** → el run arranca y la épica resultante respeta la corrección (sin "batch" anónimo).
  3. **Cancelar** → no se crea ninguna ejecución.
  4. Flag OFF → el flujo es el actual (sin modal de pre-vuelo); la épica se genera directo.
  5. Auto-aprobar ON + brief clarísimo (sin preguntas, confianza alta) → no aparece el modal, el run arranca solo; el pre-vuelo se ve en el historial.

**Criterio de aceptación (BINARIO):** `npm run build` 0 errores TS + las 5 verificaciones manuales OK.

**Flag + default:** reusa `INTENT_PREFLIGHT_ENABLED` (si OFF, el modal nunca se invoca). **Trabajo del operador:** con OFF ninguno; con ON, 1 click (o 0 con auto-aprobar).

**Impacto por runtime:** vista uniforme; el modal muestra el `intent` venga del runtime que venga. Si el backend devolvió `stage: running` (pre-vuelo no disponible), el frontend NO abre el modal y procede como hoy.

**Por qué NO viola regla 11:** el modal es el punto donde el operador DECIDE. Es human-in-the-loop puro y duro, reforzado.

---

## 6. Riesgos y mitigaciones

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R1 | **El pre-vuelo agrega fricción (un click más por run).** | Flag default OFF; con ON, auto-aprobar (F4) salta el modal cuando todo está claro; el click reemplaza la incertidumbre por control, y ahorra el costo de un run equivocado. El juez debe validar este trade-off (supuesto #1). |
| R2 | **El pre-vuelo cuesta tokens (otra llamada LLM).** | Prompt corto + `effort=low` + salida JSON acotada; KPI-4 mide `tokens_preflight/tokens_run` y obliga a que sea < 15%; si se pasa, se recorta. El ahorro neto (menos runs-basura) lo compensa. |
| R3 | **Paridad: un runtime no puede pre-volar.** | `PreflightRuntimeUnavailable` → fallback explícito: se salta el pre-vuelo y se arranca el run (idéntico a OFF). Nunca se bloquea. Cada runtime mapea su llamada corta en `_make_short_llm_invoker`. |
| R4 | **El Brief de Intención filtra un secreto del contexto.** | `to_payload` redacta (reusa el detector de la memoria colaborativa); el system-prompt prohíbe incluir secretos; `build_corrections_block` también redacta. Test `test_to_payload_redacts_secrets`. |
| R5 | **El operador no responde las preguntas y el run igual arranca confiado.** | F4 permite "arrancar igual" → el run procede con los supuestos (comportamiento M6 del plan 40 preservado). Las preguntas informan, no obligan. No se interrumpe ningún run (la versión peligrosa de la Idea E queda descartada). |
| R6 | **El estado entre los dos pasos se pierde (frontend recarga).** | No hay estado server-side: el frontend reenvía el `brief` al aprobar. Si recarga, simplemente vuelve a pre-volar (barato). Cero tabla nueva, cero sesión. |
| R7 | **El bloque `operator-corrections` no gana prioridad y el agente lo ignora.** | Bloque con `priority=100` + test `test_corrections_block_is_highest_priority`; se antepone a los demás `context_blocks`. Se verifica el orden real de `enrich_blocks` antes de tocar. |
| R8 | **Con flag OFF algo cambia (regresión).** | Test de control `test_flag_off_is_byte_identical` en F3; la rama de pre-vuelo no se evalúa con OFF. |
| R9 | **El modelo devuelve JSON basura y rompe el parseo.** | `from_model_json` es tolerante (fences, texto, campos faltantes) y ante basura devuelve `confidence=0.0` → el operador SIEMPRE revisa. Nunca lanza. Tests en F0/F1. |

---

## 7. Fuera de scope (anti-scope explícito)

- **Pre-vuelo en el run genérico de tickets reales** (no-brief): este plan cablea el pre-vuelo SOLO en `run-brief`. Extenderlo al run de tickets ADO reales es un plan futuro (mismo módulo `intent_preflight`, distinto punto de inserción).
- **Persistir el Brief de Intención como entidad nueva** / tabla / migración: no se persiste estado entre pasos; el frontend reenvía el brief. (El pre-vuelo puede aparecer en el historial vía la metadata del run si se desea, pero sin schema nuevo.)
- **Aprender de las correcciones del operador** (Idea B — memoria de gusto): fuera de scope; el pre-vuelo solo usa la corrección en ESE run. Aprender de ellas a futuro es otro plan (y reusaría `memory_store`).
- **Narración del razonamiento en vivo** (Idea A) y **A/B de prompts** (Idea C): direcciones futuras documentadas en la Parte I; no en este plan.
- **Interrumpir un run en curso para preguntar** (Idea E standalone): descartada por chocar con `autonomy-resolve-own-doubts`; solo su versión segura (preguntas en el pre-vuelo) entra aquí.
- **RBAC / multiusuario:** Stacky es mono-operador.
- **Selector de runtime/modelo:** ya cubierto por planes 36/37/40; el pre-vuelo reusa el runtime elegido, no lo cambia.

---

## 8. Orden de implementación (secuencial por dependencia)

1. **F0** — contrato `IntentBrief` + 3 flags en `config.py` y `FLAG_REGISTRY` (default OFF). Sin efecto runtime.
2. **F1** — `generate_intent_brief` con `invoke_short_llm` inyectable + fallback `PreflightRuntimeUnavailable`. Tests con fake LLM.
3. **F2** — `rank_and_flag` + `derive_open_questions` (determinista, absorbe lo viable de la Idea E).
4. **F3** — orquestación en `run-brief` (dos pasos detrás del flag) + `build_corrections_block` + prioridad en `enrich_blocks`. Test de control OFF byte-idéntico.
5. **F4** — `IntentPreflightModal.tsx` + wiring en el componente de brief + auto-aprobar. `npm run build` + verificación manual.

> **Rollout sugerido:** mergear con flag OFF (cero efecto). Prender `INTENT_PREFLIGHT_ENABLED` en una sesión de prueba sobre un brief real; medir KPI-3 (¿corregís el pre-vuelo? = lo cazó) y KPI-4 (costo). Si la fricción molesta, prender `INTENT_PREFLIGHT_AUTO_APPROVE`. Extender al run genérico solo con evidencia de valor.

---

## 9. Definición de Hecho (DoD) global (todo binario)

- [ ] F0: `test_intent_preflight_contract.py` verde; los 3 flags en `FLAG_REGISTRY` (grupo `preflight`) y en `config.py` con defaults seguros; aparecen en `HarnessFlagsPanel` sin tocar frontend.
- [ ] F1: `test_intent_preflight_generate.py` verde; `generate_intent_brief` nunca propaga y devuelve `None` en todo camino de fallo (runtime no disponible incluido).
- [ ] F2: `test_intent_preflight_ranking.py` verde; ranking determinista; preguntas de alto ROI derivadas sin LLM.
- [ ] F3: `test_run_brief_preflight.py` (6 casos) verde + test de prioridad del bloque de correcciones verde; **con flag OFF, `run-brief` byte-idéntico** (test de control).
- [ ] F4: `npm run build` 0 errores TS + 5 verificaciones manuales (incl. flag OFF sin modal y auto-aprobar).
- [ ] KPI-1: con flag ON, `run-brief` con `preflight: true` devuelve `stage: preflight` y NO arranca el run (test).
- [ ] KPI-2: con flag OFF, byte-idéntico (test de control).
- [ ] KPI-3: el backend expone `preflight_total` y `preflight_corrected_total` por proyecto (vía `harness_health`/`api/diag.py`; solo lectura).
- [ ] KPI-4: el backend registra `tokens_preflight` y `tokens_run` para poder calcular el ratio (en la metadata del run; sin schema nuevo).
- [ ] `.env.example` documenta las 3 keys del plan 41.
- [ ] Paridad 3 runtimes: el pre-vuelo usa el runtime elegido vía `_make_short_llm_invoker`; fallback explícito por runtime (`PreflightRuntimeUnavailable` → se salta el pre-vuelo).
- [ ] Human-in-the-loop reforzado: el run real solo arranca tras aprobación del operador (o auto-aprobación configurada); ninguna autonomía nueva.
- [ ] Sin tabla nueva, sin migración, sin dependencia nueva; reusa modal (38), `enrich_blocks`, flags-UI (33), detector de secretos.
- [ ] Validación SIEMPRE por archivo con el python del `.venv`; nunca la suite completa.

**Comando de validación global (backend, por archivo):**
```
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "backend/tests/test_intent_preflight_contract.py" "backend/tests/test_intent_preflight_generate.py" "backend/tests/test_intent_preflight_ranking.py" "backend/tests/test_run_brief_preflight.py" "backend/tests/test_harness_flags.py" -q
```
**Comando de validación global (frontend):**
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" ; npm run build
```

---

## 10. Checklist de aceptación del plan (meta)

- [x] Numeración consecutiva (41, siguiente libre tras `40_*`), calculada listando el directorio.
- [x] Portafolio de 5 ideas distintas con nivel de audacia y supuesto a stress-testear (Parte I), incluida una `[ROMPE-MARCO]` (Idea E).
- [x] Recomendación explícita (Idea D) con justificación; las otras quedan como direcciones futuras.
- [x] Fases F0..F4 con archivo exacto, símbolos exactos, pseudocódigo/diff, tests + comando con venv, criterio binario, flag + default, impacto por runtime + fallback, y "Trabajo del operador".
- [x] Paridad de 3 runtimes por ítem, con fallback explícito (`PreflightRuntimeUnavailable`).
- [x] Cero trabajo extra obligatorio (flag OFF byte-idéntico; con ON, 1 click o 0 con auto-aprobar).
- [x] Human-in-the-loop reforzado (el operador aprueba antes de gastar el run); sin autonomía nueva.
- [x] Mono-operador sin auth; sin RBAC.
- [x] No degrada: reusa modal (38), `enrich_blocks`, flags-UI (33), `harness_health`, detector de secretos; cero tabla/migración/dependencia nueva.
- [x] Riesgos R1-R9 + mitigaciones, Fuera de scope, Glosario, Orden, DoD.
- [x] No se implementó código; solo el documento del plan.
- [x] Listo para `criticar-y-mejorar-plan` (el juez), con los supuestos riesgosos ya señalados para el red-team.
