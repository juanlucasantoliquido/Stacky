# 07 — Agent Packs (la propuesta diferencial)

> **Tesis:** la queja contra los pipelines automáticos no es la **secuencia**, es la **falta de control**.
> Los Packs devuelven el control sin perder la velocidad.

---

## Por qué Packs

El cambio "pipeline → workbench" elimina la rigidez, pero abre una nueva fricción: el operador que sólo quiere **correr el flujo completo** sobre un ticket nuevo ahora tiene que hacer 4 clicks en lugar de 1.

**Agent Packs** es la respuesta a esa fricción **sin** volver al pipeline:

- Es **una secuencia recetada** de agentes con sus contextos pre-armados.
- **Pausa entre pasos** y espera confirmación humana.
- El operador puede **abandonar, editar el contexto del paso siguiente, o pausar y volver mañana** sin perder progreso.

> Un pack es un **asistente**, no un cron. La diferencia es que el cron decide; el asistente sugiere y espera tu OK.

---

## Anatomía de un Pack

```python
@dataclass
class PackDefinition:
    id: str                          # "desarrollo"
    name: str                        # "Pack Desarrollo"
    description: str
    steps: list[PackStep]

@dataclass
class PackStep:
    agent_type: str                  # "functional", "technical", ...
    chain_from_previous: bool        # auto-include output del paso previo en el contexto
    auto_fill_blocks: list[str]      # bloques que el editor pre-carga
    pause_after: bool = True         # default: True (humano-en-el-loop)
    skip_if_approved_within: str | None = None  # "24h" → si ya hay output aprobado fresco, salta el paso
```

---

## Catálogo inicial de Packs

### 1. Pack Desarrollo (`desarrollo`)

> "Tengo un Epic nuevo, quiero todo el ciclo manual pero guiado."

```
Functional → [pausa] → Technical → [pausa] → Developer → [pausa] → QA
```

**Pasos:**
1. **Functional** — auto-fill: ticket metadata, docs funcionales del módulo. Pausa después.
2. **Technical** — chain del paso 1, auto-fill: docs técnicos selectivos, tablas BD inferidas. Pausa después.
3. **Developer** — chain del paso 2, auto-fill: archivos del repo a tocar. Pausa después.
4. **QA** — chain del paso 3, auto-fill: plan de pruebas funcional + técnico. Pausa después.

**Opciones del pack:**
- ☐ Saltar pasos con output aprobado en las últimas 24h.
- ☑ Detener al primer error.
- ☐ Ejecutar QA en modo "shadow" (no bloqueante).

**Tiempo esperado humano-on-keyboard:** 8–12 minutos para un ticket de complejidad media.

---

### 2. Pack QA Express (`qa-express`)

> "El Developer ya terminó. Sólo quiero validación."

```
QA
```

**Pasos:**
1. **QA** — auto-fill: ticket completo + última exec aprobada de Developer + últimos commits del branch.

**Por qué es un pack si tiene 1 paso:** porque pre-arma un contexto que un click suelto no traería (ej: leer commits del branch, buscar tests existentes, identificar archivos cambiados). Es un **shortcut** con inteligencia de contexto.

---

### 3. Pack Discovery (`discovery`)

> "Llegó un Epic gigante, quiero entender qué pide antes de comprometerme."

```
Functional (modo "exploración") → [pausa] → Technical (sólo análisis, no código)
```

**Pasos:**
1. **Functional** con flag `mode: discovery` — el system prompt enfatiza "qué pide" sobre "qué cambiar".
2. **Technical** con flag `mode: feasibility` — output orientado a estimación de esfuerzo y riesgos, no plan de implementación.

**Diferencial:** los pasos usan el mismo `BaseAgent` que los regulares pero con `mode` distinto en su `build_prompt`. Sin duplicar agentes, ofrecemos perspectivas distintas.

---

### 4. Pack Hotfix (`hotfix`)

> "Hay un bug en prod. Me importa velocidad y trazabilidad."

```
Technical (modo "bug") → [pausa] → Developer → [pausa] → QA (regresión)
```

- Salta Functional (asume el bug es claro o ya hay un report).
- Technical orientado a **localizar** la causa, no a planear feature.
- QA con énfasis en regresión: ¿qué más podría haberse roto?

**Output adicional del pack:** al cerrar, genera un mini "post-mortem.md" con el análisis técnico + cambios + verificación.

---

### 5. Pack Refactor (`refactor`)

> "Quiero mejorar este módulo sin cambiar comportamiento."

```
Technical (análisis de superficie) → [pausa] → Developer (modo "iso-functional") → [pausa] → QA (regresión exhaustiva)
```

- Sin Functional (no hay nuevo requerimiento).
- Developer corre con `iso_functional: true`: enfatiza no cambiar contracts ni comportamiento observable.
- QA: regresión sobre todo lo que toque el área refactoreada.

---

## Ejecución del Pack — máquina de estados

```
                  start pack
                      │
                      ▼
              ┌──────────────┐
              │  step = 1    │
              │  status =    │
              │  running     │
              └──────┬───────┘
                     │
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
  agent error   agent success   user pause
  ┌────────┐   ┌────────────┐  ┌─────────┐
  │ if     │   │ wait for   │  │ status  │
  │ stop_  │   │ user verdict│  │ paused  │
  │ on_err │   └─────┬──────┘  └────┬────┘
  │ → error│         │              │
  │ else   │   approve   discard    │ resume
  │ → wait │      │         │       │
  └────┬───┘      ▼         ▼       │
       │     step++ or   pack       │
       │     completed   abandoned  │
       │          │         │       │
       │          ▼         ▼       │
       │   loop or done   done      │
       └──────────────────────────┐
                                  │
                                  ▼
                            ┌──────────┐
                            │ next step│
                            └──────────┘
```

---

## UI de un pack en curso

### Banner superior (siempre visible cuando hay pack activo)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ 📦 Pack Desarrollo — paso 2/4 — Technical    [Pause] [Abandon]                 │
│                                                                                 │
│   ✓ Functional       ▶ Technical       ○ Developer       ○ QA                  │
│  (15min ago)         (running...)      (pending)         (pending)             │
└────────────────────────────────────────────────────────────────────────────────┘
```

- Stepper con duración real de cada paso completado.
- Hover sobre un paso completo: link "ver exec #N".
- Click en un paso futuro: deshabilitado (no se pueden saltear sin abandonar).

### Decisión entre pasos

Cuando un paso termina, el OutputPanel cambia los CTAs:

```
  [ Approve & Continue ]   ← avanza al siguiente paso del pack
  [ Approve & Pause   ]    ← marca aprobado pero pack en pausa
  [ Edit & Re-run     ]    ← re-corre este mismo paso (no avanza)
  [ Discard & Abandon ]    ← descarta + abandona el pack
```

---

## Diferenciadores no obvios

### 1. **Memoria de packs** — el sistema aprende qué bloques agregás manualmente

Si un operador, al correr Pack Desarrollo, **siempre** agrega manualmente un bloque "consideraciones de auditoría" en el paso Technical, después de N veces el sistema sugiere agregarlo por default en ese paso. No lo agrega solo — lo **propone como sticky** la próxima vez.

Esto se persiste por usuario (preferencias) o por proyecto (patrón compartido).

### 2. **Branching dentro de un pack**

Un pack no tiene que ser lineal. Soportamos `on_output_classification`:

```python
PackStep(
    agent_type="functional",
    on_output_classification={
        "GAP_MENOR": "next",                  # sigue al Technical
        "NUEVA_FUNC": "next",                 # sigue al Technical
        "CUBRE_SIN_MOD": "abandon_with_note", # ya está cubierto, sin sentido seguir
        "BLOCKER": "ask_user",                # decide el humano
    },
)
```

Esto convierte al pack en algo más cerca de un **árbol de decisión asistido**, sin perder el control humano.

### 3. **Packs colaborativos**

Un pack iniciado por el operador A puede ser **transferido** al operador B en un paso intermedio (ej: Functional lo hace ana@, Developer lo toma juan@). Cada paso queda con `started_by` distinto en `agent_executions`.

UX:
- Banner del pack muestra "Iniciado por ana@ • Esperando handoff" cuando el último paso fue aprobado y el siguiente requiere una skill distinta.
- Operador B abre el ticket → ve "Pack en handoff hacia vos" en el banner → click "Tomar pack" → continúa.

### 4. **Packs como template**

Un pack ejecutado puede guardarse como **plantilla** con los bloques manualmente agregados. La próxima vez que se inicie ese pack, el operador puede elegir entre la versión default o la plantilla guardada (`Pack Desarrollo + bloques de auditoría`).

Útil para equipos con políticas internas (compliance, regulado).

### 5. **Dry-run de packs**

Antes de ejecutar, el operador puede pedir "dry-run": el sistema construye los prompts de los 4 pasos pero **no los ejecuta** — sólo muestra el contexto que se mandaría a cada agente. Sirve para auditar antes de gastar tokens.

---

## Métricas de éxito específicas de Packs

| Métrica | Por qué importa |
|---|---|
| % de tickets que usan packs vs runs sueltos | Adopción del modelo guiado |
| Tasa de "pause" durante un pack | Si es alta, el contexto pre-armado no es bueno y el operador necesita salirse |
| Promedio de pasos completados antes de abandonar | Detecta packs mal diseñados |
| Tasa de re-run dentro de un pack | Si es alta en un paso, ese paso necesita más bloques de contexto auto |
| Tiempo total operador-on-keyboard por pack | Comparar con tiempo del pipeline equivalente |

---

## Por qué esto NO es un pipeline disfrazado

| Aspecto | Pipeline | Pack |
|---|---|---|
| ¿Quién dispara? | el sistema, por estado ADO | el humano, click en "Iniciar pack" |
| ¿Quién avanza al siguiente paso? | el sistema, automáticamente | el humano, click en "Approve & Continue" |
| ¿El humano puede pausar a mitad? | no de forma natural | sí, a cualquier paso |
| ¿El humano puede editar el contexto del paso siguiente? | no | sí, antes de cada Run |
| ¿Trazabilidad granular? | parcial (artefactos) | total (cada paso es un row con prompt+output) |
| ¿Permite branching por output? | duro (lógica embebida) | declarativo en `PackDefinition` |
| ¿Reusable / componible? | no | sí (un pack puede invocar otro pack como step compuesto) |

---

## Roadmap de features de Packs

| Feature | Cuándo |
|---|---|
| Catálogo inicial (Desarrollo, QA Express, Discovery, Hotfix, Refactor) | Fase 1 |
| Branching por output classification | Fase 2 |
| Memoria de bloques agregados | Fase 3 |
| Packs colaborativos / handoff | Fase 3 |
| Templates de packs por usuario / proyecto | Fase 3 |
| Dry-run | Fase 2 |
| Métricas en dashboard | Fase 2 |

---

## Conclusión

> Stacky Pipeline ofrecía velocidad a costa de control.
> Stacky Agents ofrece control a costa de velocidad.
> **Stacky Agent Packs ofrece ambos.**

Un pack es un pipeline que respira: corre cuando vos querés, pausa cuando vos querés, ramifica cuando los datos lo piden, y deja un rastro completo de cada decisión.

Es la diferencia entre un **automata** y un **asistente**.
